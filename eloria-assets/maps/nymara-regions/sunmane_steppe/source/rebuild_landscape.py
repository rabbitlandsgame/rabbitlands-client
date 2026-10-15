"""Rebuild Sunmane's authored exterior, rooms and collision through shared tools.

Server publication stays in the continent coordinator. No editor imports or
server-profile writes are performed by this package entry point.
"""
from pathlib import Path
import argparse,json,subprocess,sys
SOURCE=Path(__file__).resolve().parent
REGIONS=SOURCE.parents[1]

def sync_cave_returns():
    """Keep the unchanged cave rooms tied to their surveyed surface mouths."""
    exterior=json.loads((SOURCE.parent/'world.json').read_text(encoding='utf-8'))
    doors={p['id']:p for p in exterior['portals']}
    package=REGIONS/'interiors/sunmane_insides'
    path=package/'world.json'
    room=json.loads(path.read_text(encoding='utf-8'))
    mapping={'sunmane_wind_caves':'cave-wind_caves','sunmane_crystal_hollow':'cave-crystal_hollow'}
    for section in room.get('sections',[]):
        key=section.get('id')
        if key not in mapping:continue
        door=doors[mapping[key]]
        x,_,z=door['position'];px,_,pz=door['propPosition']
        length=max(.001,((x-px)**2+(z-pz)**2)**.5)
        tile=[round(x+(x-px)/length*3+116),round(116-z-(z-pz)/length*3)]
        section['returnMap']='sunmane_steppe';section['returnTile']=tile
        for portal in room.get('portals',[]):
            if portal.get('section')==key or portal.get('id')=='exit-'+section.get('spawn',''):
                portal['destinationMap']='sunmane_steppe';portal['destinationTile']=tile
    path.write_text(json.dumps(room,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--skip-build',action='store_true')
    ap.add_argument('--skip-interiors',action='store_true')
    ap.add_argument('--skip-secrets',action='store_true')
    a=ap.parse_args()
    def run(*command):
        print('RUN',*map(str,command),flush=True)
        subprocess.run([sys.executable,*map(str,command)],cwd=REGIONS,check=True)
    if not a.skip_build:run(SOURCE/'build_landscape.py')
    for name in ('refine_walk_heights.py','open_walk_surfaces.py','stamp_solid_landmarks.py'):
        run(REGIONS/'_toolkit'/name,'sunmane_steppe')
    run(REGIONS/'_toolkit/guard_actor_surfaces.py','--package',SOURCE.parent)
    if not a.skip_interiors:run(SOURCE/'insides.py')
    sync_cave_returns()
    if not a.skip_secrets:run(REGIONS/'_toolkit/secrets_build.py','sunmane_steppe')
    run(REGIONS/'_toolkit/verify_runtime.py','--package',SOURCE.parent,
        '--report',SOURCE.parent/'runtime-validation.json')

if __name__=='__main__':main()
