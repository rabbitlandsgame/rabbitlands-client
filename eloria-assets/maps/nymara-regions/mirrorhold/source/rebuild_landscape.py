"""Reproducible Mirrorhold-only asset build and walking-surface corrections.

Server integration is deliberately separate: migrate_compact_server.py emits
its coordinate report, and the common continent tooling publishes contracts.
"""
from pathlib import Path
import argparse
import subprocess
import sys

SOURCE=Path(__file__).resolve().parent
REGIONS=SOURCE.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build',action='store_true')
    parser.add_argument('--skip-secrets',action='store_true')
    args=parser.parse_args()
    def run(cwd,*command):
        print('RUN',*map(str,command),flush=True)
        subprocess.run([sys.executable,*map(str,command)],cwd=cwd,check=True)
    if not args.skip_build:run(SOURCE,SOURCE/'build_mirrorhold.py')
    for script in ('refine_walk_heights.py','open_walk_surfaces.py','stamp_solid_landmarks.py'):
        run(REGIONS,REGIONS/'_toolkit'/script,'mirrorhold')
    run(REGIONS,REGIONS/'_toolkit/guard_actor_surfaces.py','--package',SOURCE.parent)
    if not args.skip_secrets:run(REGIONS,REGIONS/'_toolkit/secrets_build.py','mirrorhold')
    run(REGIONS,REGIONS/'_toolkit/verify_runtime.py','--package',SOURCE.parent,
        '--report',SOURCE.parent/'runtime-validation.json')


if __name__=='__main__':main()
