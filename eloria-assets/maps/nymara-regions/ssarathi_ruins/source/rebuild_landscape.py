"""Rebuild Ssarathi's compact geometry and final actor-supported collision."""
import argparse,json,subprocess,sys
from pathlib import Path
SOURCE=Path(__file__).resolve().parent
REGIONS=SOURCE.parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if not args.skip_build:
        subprocess.run([sys.executable,str(SOURCE/'build_ssarathi.py')],cwd=SOURCE,check=True)
    for script in ('refine_walk_heights.py','open_walk_surfaces.py','stamp_solid_landmarks.py'):
        subprocess.run([sys.executable,str(REGIONS/'_toolkit'/script),'ssarathi_ruins'],cwd=REGIONS,check=True)
    subprocess.run([sys.executable,str(REGIONS/'_toolkit/guard_actor_surfaces.py'),
                    '--package',str(SOURCE.parent)],cwd=REGIONS,check=True)
    manifest=json.loads((SOURCE.parent/'world.json').read_text())
    main_stats=manifest['performance'];lod_stats=main_stats['lod2']
    rows=[('# Ssarathi Ruins package budgets\n\n'
           'Each approach surface and prop is exported once; resident scenes share those nodes. Collision values in '
           '`world.json` describe the corrected, actor-guarded grid.\n\n'
           '| Metric | Main | LOD2 |\n| --- | ---: | ---: |\n')]
    for label,key in [('GLB bytes','glbBytes'),('Nodes','nodes'),
                      ('Unique triangles','uniqueTriangles'),('Instanced triangles','instancedTriangles')]:
        rows.append(f'| {label} | {main_stats[key]:,} | {lod_stats[key]:,} |\n')
    rows.append(f'\nLOD2 reduces instanced triangles by {lod_stats["triangleReductionPercent"]}%. '
                'The region survey records actual local frame samples; these are not '
                'a hardware-independent frame-rate guarantee.\n')
    (SOURCE.parent/'performance-summary.md').write_text(''.join(rows),encoding='utf-8')
    if args.verify:
        subprocess.run([sys.executable,str(REGIONS/'_toolkit/verify_runtime.py'),
                        '--report','verification-report.json'],cwd=SOURCE.parent,check=True)

if __name__=='__main__':main()
