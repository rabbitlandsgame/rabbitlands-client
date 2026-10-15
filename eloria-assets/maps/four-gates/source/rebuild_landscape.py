"""Reproduce Four Gates, its door contracts and final walking-surface passes."""
from pathlib import Path
import argparse,json,subprocess,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import native_adapter as A
import interior_index as INDEX
from refine_walk_heights import refine
from open_walk_surfaces import open_package
from stamp_solid_landmarks import stamp
from guard_actor_surfaces import guard
from export_interior_collision import export as export_interior_collision

def sync_interiors():
    for entry in INDEX.INTERIORS:
        package=A.ASSETS/'maps'/entry['id'];path=package/'world.json'
        manifest=json.loads(path.read_text(encoding='utf-8'))
        manifest['asset']['parentMap']='four_gates'
        for portal in manifest.get('portals',[]):
            if portal.get('id')=='exit':
                portal.update(targetMap='four_gates',targetPosition=entry['arrival'])
                post=INDEX.ROOM_DOOR_POSTS.get(entry['id'],{})
                if post:portal['position']=post['exit']
                for spawn in manifest.get('spawnPoints',[]):
                    if spawn['id']=='entrance':
                        spawn['position'][2]=min(spawn['position'][2],portal['position'][2]-3.)
                        if post:spawn['position']=post['arrival']
        path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        print(entry['id'],export_interior_collision(package,36),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skip-build',action='store_true')
    p.add_argument('--skip-interiors',action='store_true')
    p.add_argument('--skip-secrets',action='store_true')
    p.add_argument('--rebuild-interiors',action='store_true')
    a=p.parse_args()
    if not a.skip_build:subprocess.run([sys.executable,str(HERE/'build_four_gates.py')],check=True)
    package=HERE.parent
    print('REFINE',refine(package,True),flush=True)
    print('OPEN',open_package(package,True),flush=True)
    stamp(package)
    print('GUARD',guard(package,True),flush=True)
    if not a.skip_interiors:
        if a.rebuild_interiors:
            subprocess.run([sys.executable,str(A.NATIVE/'build_interiors.py'),
                '--cache',str(HERE/'texture-cache')],check=True)
        sync_interiors()
    if not a.skip_secrets:
        subprocess.run([sys.executable,str(A.TOOLKIT/'secrets_build.py'),'four_gates'],check=True)
    subprocess.run([sys.executable,str(A.TOOLKIT/'verify_runtime.py'),'--package',str(package),
                    '--report',str(package/'runtime-validation.json')],check=True)

if __name__=='__main__':main()
