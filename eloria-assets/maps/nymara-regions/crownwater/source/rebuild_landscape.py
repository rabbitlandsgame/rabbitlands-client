"""Rebuild Crownwater geometry, LOD, minimap and final collision corrections."""
import argparse,subprocess,sys
from pathlib import Path
SOURCE=Path(__file__).resolve().parent
REGIONS=SOURCE.parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--skip-build',action='store_true');ap.add_argument('--verify',action='store_true')
    args=ap.parse_args()
    if not args.skip_build:
        subprocess.run([sys.executable,str(SOURCE/'build_crownwater.py')],cwd=SOURCE,check=True)
    for script in ('refine_walk_heights.py','open_walk_surfaces.py','stamp_solid_landmarks.py'):
        subprocess.run([sys.executable,str(REGIONS/'_toolkit'/script),'crownwater'],cwd=REGIONS,check=True)
    subprocess.run([sys.executable,str(REGIONS/'_toolkit/guard_actor_surfaces.py'),
                    '--package',str(SOURCE.parent)],cwd=REGIONS,check=True)
    if args.verify:
        subprocess.run([sys.executable,str(REGIONS/'_toolkit/verify_runtime.py'),
                        '--report','verification-report.json'],cwd=SOURCE.parent,check=True)
if __name__=='__main__':main()
