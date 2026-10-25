"""Real Godot Main/TCP spawn probe, isolated from deployed servers and saves."""
from __future__ import annotations
import argparse
import asyncio
import json
import hashlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

from local_server import LocalServer, login, packet, read_packet, clean_text

CLIENT = Path(__file__).resolve().parents[2]
SERVER = CLIENT.parent.parent / 'rabbitlands-server'


def write(path, value):
    temporary = path.with_suffix('.partial')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


async def wait_json(path, predicate=lambda d: True, timeout=100):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
            if predicate(value): return value
        except (FileNotFoundError,json.JSONDecodeError): pass
        await asyncio.sleep(.05)
    raise TimeoutError(f'No expected probe result: {path.name}')


class FixtureServer(LocalServer):
    async def _wait_for_listener(self):
        for _ in range(240):
            if self._process.poll() is not None:
                raise RuntimeError('Probe server exited during startup:\n' + self.recent_log())
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', self.port), .25)
                writer.close()
                await writer.wait_closed()
                return
            except (OSError, TimeoutError):
                await asyncio.sleep(.05)
        raise RuntimeError('Probe listener timeout:\n' + self.recent_log())

    def __init__(self, terrain, users, server_root=SERVER):
        self.users=users
        server_root=Path(server_root).resolve()
        settings=(server_root/'config/eloria/server.txt').read_text(encoding='utf-8')
        settings=re.sub(r'^map_data_directory\s*=.*$',f'map_data_directory = {terrain.as_posix()}',settings,flags=re.M)
        settings=re.sub(r'^invasion_masters\s*=.*$',f'invasion_masters = {",".join(users)}',settings,flags=re.M)
        super().__init__(server_root,prefix='rl-spawn-probe-',overrides={'--settings':settings})

    def _prepare_config(self):
        root=super()._prepare_config()
        # The explicit checkout is known only after parsing the CLI. Keep this
        # lazy so --help needs neither a sibling server nor its dependencies.
        sys.path.insert(0, str(self.server_root))
        from eloria.database import Database
        from eloria.items import configure_items
        configure_items(self.server_root / 'config/eloria/items.txt')
        database=Database(str(Path(self._workdir.name)/'eloria.sqlite3'))
        try:
            for name,password in self.users.items():
                database.create(name,password,start=('landfall',122,225))
        finally:
            database.db.close()
        return root


def validate_display(ready, args):
    if ready.get('fps_cap') != args.fps_cap:
        raise AssertionError(f'Unexpected live-client FPS cap: {ready}')
    # Headless DisplayServer has no native window mode. Rendered runs must
    # still attest the actual requested window/exclusive-fullscreen mode.
    if args.rendered and ready.get('window_mode') != (4 if args.window_mode == 'fullscreen' else 0):
        raise AssertionError(f'Unexpected live-client display mode: {ready}')


async def probe(server,args,users):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    def source_identity():
        paths=['src/app/main.gd','src/actors/actor_resource_warmup.gd',
               'src/actors/native_animation_importer.gd','src/network/network_client.gd',
               'src/world/animation_gate.gd',
               'tests/integration/live_spawn_responsiveness.gd',
               'tests/integration/client_world_readiness.gd',
               'tests/integration/live_spawn_responsiveness.py']
        return {path:hashlib.sha256((CLIENT/path).read_bytes()).hexdigest() for path in paths}
    identity_before=source_identity()
    name=list(users)[1]
    env=os.environ.copy()
    for key in list(env):
        if key.startswith(('RABBITLANDS_', 'ELORIA_')): env.pop(key)
    env.update(APPDATA=str(out/'userdata'),XDG_DATA_HOME=str(out/'userdata'),
        RL_SPAWN_TEST_OUT=str(out),RL_SPAWN_TEST_PORT=str(server.port),
        RL_SPAWN_TEST_USER=name,RL_SPAWN_TEST_PASSWORD=users[name])
    # Select ordinary saved settings in this disposable user's profile.
    # Never replace the developer's or a player's preferences.
    settings=out/'userdata/Godot/app_userdata/Eloria/eloria_hud.cfg'
    settings.parent.mkdir(parents=True,exist_ok=True)
    content=f'[graphics]\n\nwindow_mode="{args.window_mode}"\nfps_limit={args.fps_cap}\n'
    with settings.open('x',encoding='utf-8') as stream:
        stream.write(content)
    settings_seed={'window_mode':args.window_mode,'fps_cap':args.fps_cap,'path':str(settings),
                   'sha256':hashlib.sha256(content.encode()).hexdigest()}
    env['RL_SPAWN_TEST_PROFILE']='1' if args.profile else '0'
    env['RL_SPAWN_TEST_FPS_CAP']=str(args.fps_cap)
    command=[str(args.godot),*([] if args.rendered else ['--headless']),'--path',str(CLIENT),'--script',
        'res://tests/integration/live_spawn_responsiveness.gd','--log-file',str(out/'client.log')]
    log=(out/'launch.log').open('w',encoding='utf-8')
    process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    reader=writer=None
    pump=None
    texts=[]
    scenarios=[]
    async def drain():
        while True:
            code,payload=await read_packet(reader,120)
            if code==0: texts.append(clean_text(payload)[1])
    async def send(text):
        writer.write(packet(0,text.encode()+b'\0')); await writer.drain()
    async def wait_text(prefix,start,timeout=30):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            for text in texts[start:]:
                if text.startswith(prefix): return text
            if pump.done(): await pump
            await asyncio.sleep(.01)
        raise TimeoutError(f'No operator reply: {prefix}; last messages: {texts[-3:]}')
    try:
        ready=await wait_json(out/'ready.json',timeout=210)
        validate_display(ready, args)
        readiness=await wait_json(out/'readiness.json',timeout=5)
        if (not readiness.get('ready') or readiness.get('stableFrames',0)<12
                or readiness.get('resourceWaitMilliseconds',0)<1000):
            raise AssertionError(f'Client map/resource readiness failed: {readiness}')
        if args.ui_gate:
            write(out/'ui-review-ready.json', {'stage':'before samples','ready':ready})
            await wait_json(out/'ui-review-done.json', timeout=180)
            await asyncio.sleep(1)
        admin=list(users)[0]
        reader,writer,_=await login(server.port,admin,users[admin])
        pump=asyncio.create_task(drain())
        await send('#clientcaps continent_v2_maps_v1')
        await send('#demigod')
        for label,map_id,count in [('baseline','',0),('same-100','landfall',100),
                ('other-100','four_gates',100),('same-500','landfall',500),('other-500','four_gates',500)]:
            write(out/'control.json',{'id':label,'duration_ms':6000})
            await wait_json(out/'phase-ready.json',lambda d:d.get('id')==label)
            started=time.perf_counter()
            reply='baseline'
            if count:
                x,y=(int(ready['x'])+18,int(ready['y'])) if map_id=='landfall' else (309,162)
                mark=len(texts)
                await send(f'#invasion {x} {y} {map_id} rabbit {count}')
                reply=await wait_text('Invasion spawned:',mark)
            elapsed=(time.perf_counter()-started)*1000
            row=await wait_json(out/(label+'.json'))
            row.update(requested=count,spawn_map=map_id,command_completion_ms=round(elapsed,3),reply=reply)
            if (not row['connected'] or row['ping_ms']['count']<10 or row['movement_updates']<1
                    or row['unpresented_actor_records']):
                raise AssertionError(f'Client responsiveness failed: {row}')
            if count:
                mark=len(texts);await send('#clear_invasion')
                cleared=await wait_text('Okay, all invasion monsters cleared!',mark)
                row['clear_reply']=cleared
                # The server reports the actual count removed, over the wire.
                if not cleared.endswith(f'({count})'):
                    raise AssertionError(f'Wave count mismatch: {cleared}')
            scenarios.append(row)
            print(json.dumps(row),flush=True)
            await asyncio.sleep(1)
        if args.ui_gate:
            write(out/'ui-after-ready.json', {'stage':'after samples','scenarios':len(scenarios)})
            await wait_json(out/'ui-after-done.json', timeout=180)
        write(out/'control.json',{'stop':True})
        await wait_json(out/'client-results.json',timeout=20)
        await asyncio.to_thread(process.wait,20)
        errors=[line for line in (out/'launch.log').read_text(encoding='utf-8',errors='replace').splitlines()
                if line.startswith(('ERROR:','SCRIPT ERROR:'))]
        result={'scope':'real Godot Main/TCP against fresh loopback server; current authored terrain for both tested maps',
            'rendered':args.rendered,
            'profiled':args.profile,'source_identity_before':identity_before,
            'readiness':readiness,
            'ui_review_gate':args.ui_gate,
            'settings_seed':settings_seed,'requested_window_mode':args.window_mode,'requested_fps_cap':args.fps_cap,
            'source_identity_after':source_identity(),
            'terrain':str(args.terrain.resolve()),'server_root':str(server.server_root),'scenarios':scenarios,'exit':process.returncode,'client_errors':errors}
        result['source_identity_stable']=result['source_identity_before']==result['source_identity_after']
        write(out/'summary.json',result)
        if process.returncode or errors or not result['source_identity_stable']:
            raise AssertionError(f'Client errors or source changed: {errors[:5]}')
        return result
    finally:
        if pump: pump.cancel()
        if writer: writer.close()
        if process.poll() is None:
            process.terminate()
            try: await asyncio.to_thread(process.wait,10)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        log.close()
        (out/'server-tail.log').write_text(server.recent_log(200),encoding='utf-8')


def arguments(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root',type=Path,default=SERVER,
                        help='Server checkout; defaults to the sibling rabbitlands-server repository')
    parser.add_argument('--godot',type=Path,required=True)
    parser.add_argument('--terrain',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--rendered',action='store_true',help='Show and render the actual client window')
    parser.add_argument('--profile',action='store_true',help='Use the existing Main timing subclass for attribution')
    parser.add_argument('--window-mode',choices=['windowed','fullscreen'],default='windowed',
                        help='Use the ordinary saved fullscreen choice in disposable client settings')
    parser.add_argument('--fps-cap',type=int,choices=[0,30,60,75,90,120,144,165,240,360],default=60,
                        help='Normal saved FPS limit; zero tests the client default without a cap')
    parser.add_argument('--ui-gate',action='store_true',
                        help='Pause before/after samples for explicit UI-review acknowledgements')
    return parser.parse_args(argv)


if __name__=='__main__':
    args=arguments()
    args.out.mkdir(parents=True,exist_ok=True)
    tempfile.tempdir=str(args.out.resolve())
    users={name:secrets.token_urlsafe(24) for name in ('SpawnAdmin','SpawnViewer')}
    with FixtureServer(args.terrain.resolve(),users,args.server_root.resolve()) as server:
        asyncio.run(probe(server,args,users))
