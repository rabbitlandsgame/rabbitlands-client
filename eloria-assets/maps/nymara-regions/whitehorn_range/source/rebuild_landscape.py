"""Rebuild Whitehorn and synchronise its server contracts, without other regions.

python rebuild_landscape.py --server <server checkout> --data <generated data>
Use --skip-build after a geometry iteration, or --passes-only for client QA.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

SOURCE=Path(__file__).resolve().parent
REGIONS=SOURCE.parents[1]
CLIENT=SOURCE.parents[4]


def run(cwd,*args):
    print("RUN", *map(str,args),flush=True)
    subprocess.run([sys.executable,*map(str,args)],cwd=cwd,check=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server',type=Path)
    ap.add_argument('--data',type=Path)
    ap.add_argument('--skip-build',action='store_true')
    ap.add_argument('--passes-only',action='store_true')
    args=ap.parse_args()
    if not args.passes_only and (not args.server or not args.data):
        ap.error('--server and --data are required for contract sync')
    if not args.skip_build:
        for script in ['build_whitehorn.py','build_interiors.py','export_insides_collision.py']:
            run(SOURCE,SOURCE/script)
    for script in ['refine_walk_heights.py','open_walk_surfaces.py','stamp_solid_landmarks.py']:
        run(REGIONS,REGIONS/'_toolkit'/script,'whitehorn_range')
    run(REGIONS,REGIONS/'_toolkit/secrets_build.py','whitehorn_range')
    if args.passes_only:return
    server=args.server.resolve();data=args.data.resolve()
    from migrate_compact_server import migrate
    migrate(server)
    for region in ['whitehorn_range','whitehorn_glacier_temple','whitehorn_range_secrets']:
        run(server,server/'tools/sync_authored_collision.py','--client',CLIENT/'eloria-assets/maps','--region',region)
    run(server,server/'tools/generate_nymara_maps.py',data)
    run(server,CLIENT/'eloria-assets/tools/continent_portals.py','--server',server,'--maps',data,'--region','whitehorn_range','--apply')
    run(server,server/'tools/author_region_content.py','all','--maps',data,'--client',CLIENT,'--region','whitehorn_range','--apply')
    sys.path[:0]=[str(server/'tools'),str(server)]
    try:  # base content tables only, never the continent-v2 overlay (serve plan CV13)
        from eloria import content_overlay
    except ImportError:  # an older server checkout has no continent-v2 overlay, so nothing to switch off
        pass
    else:
        content_overlay.configure(False)
    import relocate_map_content as relocate
    profile=server/'config/eloria'
    maps,portals=relocate.load_maps(profile/'maps.txt');cache={}
    def mask_for(map_id):
        if map_id not in ('whitehorn_range','whitehorn_glacier_temple','whitehorn_range_secrets'):return None,0
        if map_id not in cache:
            collision=relocate.load_elm_collision(data/maps[map_id].file)
            cache[map_id]=(relocate.standable(collision.heights,collision.width,
                          relocate.arrivals_for(map_id,portals)),collision.width)
        return cache[map_id]
    moves=[];taken={};resolved={};pending=[]
    for name in relocate.COORDINATE_FIELDS:
        path=profile/name
        if path.exists():
            original=path.read_bytes()
            text=relocate.rewrite(path,mask_for,moves,taken,resolved)
            pending.append((path,text.replace('\n','\r\n' if b'\r\n' in original else '\n').encode()))
    print(json.dumps({'relocations':moves},indent=2),flush=True)
    if any(m[4] is None or max(abs(m[3][i]-m[4][i]) for i in (0,1))>12 for m in moves):
        raise SystemExit('A moved post needs a designed approach; inspect relocations before writing')
    for path,payload in pending:
        if path.read_bytes()!=payload:path.write_bytes(payload)
    text,_=relocate.follow_manifest(profile,moves)
    if text is not None:
        (profile/'client_content_manifest.json').write_text(text,encoding='utf-8')
    from server_posts import sync
    sync(server)
    # Publish only this pilot's package identities after all metadata is final.
    # The generic --digests command updates every region in the checkout.
    sys.path.insert(0,str(CLIENT/'eloria-assets/tools'))
    import sync_package_content as packages
    manifest_path=profile/'client_content_manifest.json'
    content=json.loads(manifest_path.read_text())
    registry=packages.registry_packages()
    for entry in content.get('maps',[]):
        name=entry.get('id')
        if name in ('whitehorn_range','whitehorn_glacier_temple','whitehorn_range_secrets') and name in registry:
            entry['packageSha256']=packages.digest_for(registry[name])
            if name=='whitehorn_range':
                entry['arrival']=[106,69];entry['server_cells']=396
                entry['portals']=[{'server_tile':[p.x,p.y],'destination':p.destination} for p in portals if p.source==name]
    manifest_path.write_text(json.dumps(content,indent=2)+'\n',encoding='utf-8')
    run(CLIENT,CLIENT/'eloria-assets/tools/build_exterior_streaming.py','--server',server)


if __name__=='__main__':main()
