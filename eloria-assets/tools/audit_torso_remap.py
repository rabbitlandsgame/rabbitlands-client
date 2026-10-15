"""Measure shipped torso front coverage on a fixed, unmasked body grid.

The raster uses triangle barycentrics, independently of the fitter's radial
contact rays. Absolute proud cells retain the original body denominator even
when the runtime hides clothing. Remaining-body cells separately detect any
body triangles that survive the coverage mask and win the depth test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import conform_equipment as ce
import equipment_authoring as ea
import import_generated_equipment as batch


def depth(points, triangles, xy):
    result = np.full(len(xy), -np.inf)
    for a, b, c in points[triangles]:
        ab, ac = b[:2] - a[:2], c[:2] - a[:2]
        det = ab[0] * ac[1] - ab[1] * ac[0]
        if abs(det) < 1e-12:
            continue
        near = np.flatnonzero(np.all(xy >= np.minimum(np.minimum(a[:2], b[:2]), c[:2]) - 1e-9, axis=1)
                             & np.all(xy <= np.maximum(np.maximum(a[:2], b[:2]), c[:2]) + 1e-9, axis=1))
        d = xy[near] - a[:2]
        u = (d[:, 0] * ac[1] - d[:, 1] * ac[0]) / det
        v = (ab[0] * d[:, 1] - ab[1] * d[:, 0]) / det
        hit = (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        z = a[2] + u[hit] * (b[2] - a[2]) + v[hit] * (c[2] - a[2])
        result[near[hit]] = np.maximum(result[near[hit]], z)
    return result


#: The shipped torsos fitted to the Human male body (luminous_male.glb). The
#: old-male base scenes equipment/<slug>.glb were deleted in the race
#: programme's P7 cleanup (2026-10); each piece's base scene is now this file.
HUMAN_MALE = batch.EQUIPMENT / 'variants' / 'human_male'


def audit(directory: Path = HUMAN_MALE):
    rig = ea.load_rig(ce.RACES / 'luminous_male.glb', ce.BODY_MESH)
    x, y = np.meshgrid(np.linspace(-.23, .23, 185), np.linspace(1.05, 1.48, 87))
    xy = np.column_stack((x.ravel(), y.ravel()))
    body = depth(rig.positions, rig.faces, xy)
    skin = np.isfinite(body)
    chest = skin & (xy[:, 1] >= 1.28 - 1e-8) & (xy[:, 1] <= 1.32 + 1e-8)
    centers = rig.positions[rig.faces].mean(axis=1)
    covered = ((centers[:, 1] > .95) & (centers[:, 1] < 1.535)
               & (np.abs(centers[:, 0]) < .665))
    remainder = depth(rig.positions, rig.faces[~covered], xy)
    records = {}
    for piece in batch.roster():
        if piece.part != 5:
            continue
        path = directory / (piece.slug + '.glb')
        surface, _ = ce.read_source(path)
        armour = depth(surface.positions, surface.indices.reshape(-1, 3), xy)
        proud = skin & (armour >= body)
        records[piece.slug] = {
            'proud_cells': int(proud.sum()),
            'chest_covered_width': float(proud[chest].mean()),
            'remaining_body_cells': int((skin & np.isfinite(remainder) & (remainder > armour)).sum()),
            'chest_silhouette': float(np.isfinite(armour[chest]).mean()),
        }
        print(piece.slug, records[piece.slug], flush=True)
    return {
        'authoring_race': 'luminous_male',
        'measurement': {
            'view': 'orthographic front (+Z), rest pose',
            'x_grid': [-.23, .23, 185], 'y_grid': [1.05, 1.48, 87],
            'chest_band': [1.28, 1.32], 'body_cells_per_piece': int(skin.sum()),
            'proud_cells': 'armour stands in front of the ORIGINAL, unmasked body',
            'remaining_body_cells': 'remaining body wins depth after the runtime mask',
            'limitations': 'Front rest geometry; visual sheets and runtime tests check design and attachment separately.'},
        'summary': {
            'pieces': len(records),
            'median_chest_covered_width': float(np.median([r['chest_covered_width'] for r in records.values()])),
            'minimum_chest_covered_width': min(r['chest_covered_width'] for r in records.values()),
            'proud_cells': sum(r['proud_cells'] for r in records.values()),
            'remaining_body_cells': sum(r['remaining_body_cells'] for r in records.values())},
        'pieces': records}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--directory', type=Path, default=HUMAN_MALE)
    args = ap.parse_args()
    report = audit(args.directory)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(report['summary'])
