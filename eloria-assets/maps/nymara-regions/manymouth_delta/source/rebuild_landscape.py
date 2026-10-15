"""Reproduce the compact delta, physical collision, and shared cartography.

This never publishes server configuration. --server only reads its production
height and movement rules for the final route audit.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

SOURCE=Path(__file__).resolve().parent
PACKAGE=SOURCE.parent
ROOT=PACKAGE.parents[3]
TOOLKIT=PACKAGE.parent/'_toolkit'
sys.path[:0]=[str(TOOLKIT),str(ROOT/'eloria-assets/tools')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=PACKAGE)
    parser.add_argument('--server',type=Path)
    parser.add_argument('--correct-only',action='store_true')
    args=parser.parse_args();package=args.out.resolve()
    inputs=sorted({PACKAGE.parent/'continent-geography.json',
        *TOOLKIT.rglob('*.py'),*SOURCE.glob('*.py')})
    def source_hashes():
        return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    before=source_hashes()
    if not args.correct_only:
        subprocess.run([sys.executable,'-X','utf8','-u',str(SOURCE/'build_manymouth_delta.py'),
            '--out',str(package),'--skip-minimap'],check=True,cwd=SOURCE)
        if before!=source_hashes():
            raise RuntimeError('Authored source changed during the geometry build; repeat after it is frozen')
    import expand_continent_collision as E
    import refine_walk_heights as R
    import open_walk_surfaces as O
    import stamp_solid_landmarks as S
    import guard_actor_surfaces as G
    import render_region_cartography as C
    import audit_compact as A
    geography=(PACKAGE.parent/'continent-geography.json').read_bytes()
    E.expand(package,'manymouth_delta',json.loads(geography),hashlib.sha256(geography).hexdigest(),apply=True)
    R.refine(package,True);O.open_package(package,True);S.stamp(package);G.guard(package)
    if not args.correct_only:
        path=package/'world.json';manifest=json.loads(path.read_text(encoding='utf-8'))
        manifest['authoredGeometry']={'generator':'eloria-assets/maps/nymara-regions/manymouth_delta/source/rebuild_landscape.py','inputs':before}
        path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    audit=A.audit(package,args.server)
    (package/'compact-access-report.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    if audit['failedRoutes'] or audit['failedPortals'] or audit['failedSecrets'] or any(v['missing'] for v in audit['ids'].values()):
        raise RuntimeError('Compact route or identity audit failed; see compact-access-report.json')
    subprocess.run([sys.executable,'-X','utf8',str(TOOLKIT/'verify_runtime.py'),
        '--package',str(package)],check=True,cwd=SOURCE)
    temporary=package/'cartography-build'
    result=C.render_region('manymouth_delta',package/'world.json',temporary)
    C.apply_outputs(result,temporary)
    print('Manymouth compact package reproduced; server files were not changed.')


if __name__=='__main__':main()
