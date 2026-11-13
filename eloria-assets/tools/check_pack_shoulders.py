"""Check posed pack/body contact independently of the fitting calculation.

Exports the finished engine meshes, then checks the visible shoulder roof at
strap vertices, edge midpoints and face centres. Bare/wardrobe bodies are the
numeric gate: armor overhangs need rendered review rather than this roof test.
Raw samples and reports remain in a fresh ignored --out directory.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def contacts(points, triangles):
    """Visible shoulder roof depth, including hollow clothing shells."""
    if not len(triangles):return np.zeros(len(points))
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    determinant = (b[:, 2]-c[:, 2])*(a[:, 0]-c[:, 0])+(c[:, 0]-b[:, 0])*(a[:, 2]-c[:, 2])
    valid = abs(determinant) > 1e-12
    if not valid.any():return np.zeros(len(points))
    a, b, c, determinant = a[valid], b[valid], c[valid], determinant[valid]
    depth = np.zeros(len(points))
    for start in range(0, len(points), 64):
        p = points[start:start+64, None, :]
        u = ((b[:, 2]-c[:, 2])*(p[:, :, 0]-c[:, 0])+
             (c[:, 0]-b[:, 0])*(p[:, :, 2]-c[:, 2]))/determinant
        v = ((c[:, 2]-a[:, 2])*(p[:, :, 0]-c[:, 0])+
             (a[:, 0]-c[:, 0])*(p[:, :, 2]-c[:, 2]))/determinant
        hit = (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1.00000001)
        y = np.where(hit, u*a[:, 1]+v*b[:, 1]+(1-u-v)*c[:, 1], np.inf)
        roof=np.max(np.where(np.isfinite(y),y,-np.inf),axis=1)
        depth[start:start+len(p)]=np.where(np.isfinite(roof),np.maximum(0.,roof-p[:,0,1]),0.)
    return depth


def analyse(path):
    record = json.loads(path.read_bytes())
    samples = []
    for mesh in record['packs']:
        p = np.asarray(mesh['positions'])
        faces = np.asarray(mesh['faces'])
        triangles = p[faces]
        sample = np.concatenate([p, triangles.mean(1),
            (triangles[:, 0]+triangles[:, 1])*.5,
            (triangles[:, 1]+triangles[:, 2])*.5,
            (triangles[:, 2]+triangles[:, 0])*.5])
        band = ((sample[:, 1] > record['shoulderY']-.10)
                & (sample[:, 1] < record['shoulderY']+.18)
                & (abs(sample[:, 0]) > .055) & (abs(sample[:, 0]) < .28)
                & (sample[:, 2] > -.14) & (sample[:, 2] < .10))
        samples.append(sample[band])
    samples = np.unique(np.round(np.concatenate(samples), 6), axis=0)
    worst = np.zeros(len(samples))
    for mesh in record['body']:
        vertices = np.asarray(mesh['positions'])
        triangles = vertices[np.asarray(mesh['faces'])]
        keep = ((triangles[:,:,1].max(1)<record['shoulderY']+.10)
                & (triangles[:,:,1].max(1)>record['shoulderY']-.13)
                & (triangles[:, :, 0].max(1) >= samples[:, 0].min())
                & (triangles[:, :, 0].min(1) <= samples[:, 0].max())
                & (triangles[:, :, 2].max(1) >= samples[:, 2].min())
                & (triangles[:, :, 2].min(1) <= samples[:, 2].max()))
        worst = np.maximum(worst, contacts(samples, triangles[keep]))
    return {'case': record['label'], 'samples': len(samples),
            'samplesBelowShoulderRoofOver1mm': int((worst > .001).sum()),
            'maximumRoofIntrusionMetres': float(worst.max()),
            'worstPoints': samples[np.argsort(worst)[-8:]].tolist() if worst.max() else []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--races', default='luminous_male,luminous_female')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for name in ['APPDATA', 'LOCALAPPDATA']:
        profile = args.out/'profile'/name
        profile.mkdir(parents=True)
        env[name] = str(profile.resolve())
    command = [str(args.engine.resolve()), '--headless', '--path', str(ROOT/'godot-client'),
        '--script', 'res://tests/integration/pack_shoulder_samples.gd', '--',
        '--out', str(args.out.resolve()), '--races', args.races]
    if args.baseline: command.extend(['--baseline', str(args.baseline.resolve())])
    startup = None
    if os.name == 'nt':
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    with (args.out/'engine.log').open('w') as stream:
        run = subprocess.run(command, env=env, startupinfo=startup, stdout=stream,
                             stderr=subprocess.STDOUT, timeout=240)
    log = (args.out/'engine.log').read_text(errors='replace')
    if run.returncode or 'SCRIPT ERROR:' in log or '\nERROR:' in log:
        raise RuntimeError('Engine sampling failed; see retained log')
    cases = json.loads((args.out/'cases.json').read_bytes())
    records = [analyse(args.out/(case+'.json')) for case in cases]
    report = {'method': 'independent posed shoulder-roof triangle rays; vertices, edge midpoints, face centres',
              'toleranceMetres': .001, 'cases': records,
              'samplesBelowShoulderRoofOver1mm': sum(r['samplesBelowShoulderRoofOver1mm'] for r in records)}
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
    raise SystemExit(1 if report['samplesBelowShoulderRoofOver1mm'] else 0)


if __name__ == '__main__':
    main()
