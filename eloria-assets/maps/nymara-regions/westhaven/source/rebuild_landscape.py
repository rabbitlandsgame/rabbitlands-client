"""Rebuild Westhaven geometry and its authored collision in dependency order.

Server content and continent links are synchronized by the integration checkout.
The accompanying migrate_compact_server.py must run once before that sync.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parent
TOOLKIT=PACKAGE.parent/'_toolkit'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build',action='store_true')
    parser.add_argument('--skip-lod2',action='store_true')
    args=parser.parse_args()
    def run(script,*arguments):
        subprocess.run([sys.executable,str(script),*map(str,arguments)],cwd=HERE,check=True)
    if not args.skip_build:
        run(HERE/'build_westhaven.py',*(['--skip-lod2'] if args.skip_lod2 else []))
    run(TOOLKIT/'refine_walk_heights.py','westhaven')
    run(TOOLKIT/'open_walk_surfaces.py','westhaven')
    run(TOOLKIT/'stamp_solid_landmarks.py','westhaven')
    run(TOOLKIT/'guard_actor_surfaces.py','--package',PACKAGE)
    run(TOOLKIT/'verify_runtime.py','--package',PACKAGE,'--report',PACKAGE/'verification-report.json')

if __name__=='__main__':main()
