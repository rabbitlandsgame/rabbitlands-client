"""Measure every original-art torso against each current, unmasked wearer.

This is a geometric audit, independent of the runtime body-cover mask. The
before/after comparison on a legacy asset additionally requires actual Godot
bindings; use measure_canonical_coverage.py for that comparison.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import hashlib
from pathlib import Path

import numpy as np
import equipment_authoring as ea
import import_generated_equipment as batch
from measure_canonical_coverage import CLIENT, front_depth, surfaces


def measure_race(args):
    directory, race = args
    body_path = CLIENT / f'assets/actors/native/races/{race}.glb'
    inputs = {str(body_path): hashlib.sha256(body_path.read_bytes()).hexdigest()}
    rig = ea.load_rig(body_path, ea.BODY_SURFACES)
    chest = rig.origin('spine_03')[1]
    xs = np.linspace(-.235, .235, 189)
    ys = np.linspace(chest-.065, chest+.055, 49)
    body = front_depth(rig.positions[rig.faces], xs, ys)
    on_body = np.isfinite(body)
    at_chest = abs(ys-chest) < .011
    rows = []
    for piece in batch.roster():
        if piece.part != 5:
            continue
        path = directory / race / (piece.slug+'.glb')
        inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        meshes = surfaces(path, rig)
        row = {'slug': piece.slug}
        for layer, tri in [('art', meshes[0][1]),
                           ('all', np.concatenate([v for _, v in meshes]))]:
            proud = on_body & (front_depth(tri, xs, ys) > body+.001)
            row[layer] = {'proud_cells': int(proud.sum()),
                'covered_width': float(proud[at_chest].sum()/on_body[at_chest].sum())}
        rows.append(row)
    summary = {layer: {
        'median_covered_width': float(np.median([r[layer]['covered_width'] for r in rows])),
        'minimum_covered_width': min(r[layer]['covered_width'] for r in rows),
        'total_proud_cells': sum(r[layer]['proud_cells'] for r in rows)}
        for layer in ('art', 'all')}
    for filename, expected in inputs.items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Coverage input changed: {filename}')
    print(race, summary, flush=True)
    return race, {'chest_y': float(chest), 'body_cells': int(on_body.sum()),
                  'summary': summary, 'pieces': rows, 'input_sha256': inputs}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--races', default='all')
    p.add_argument('--jobs', type=int, default=2)
    a = p.parse_args()
    races = sorted(q.stem for q in (CLIENT/'assets/actors/native/races').glob('*.glb')) if a.races == 'all' else a.races.split(',')
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        result = dict(pool.map(measure_race, [(a.directory, race) for race in races]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
