"""Fit the shared hairstyles to a regenerated Human head (2026-10-05 bodies).

    python eloria-assets/tools/fit_human_hair.py <body.glb> --styles <hair dir> --out <scratch dir> [--sex male]

`fit_character_appearance.fit_hair` does the real work - crown height, a 10 mm
radial clearance over the skull, weights sampled from the head skin - but it
reads the head from primitives tagged `race_head` by the shared-body assembly,
and its starting placement from the model's `hairFit`.  The regenerated bodies
are not assembled that way and carry an empty `hairFit`, so this driver:

* takes the skull as the faces of the body/scalp/eyes/eyebrows surfaces whose
  vertices are mostly Head-weighted, expressed in Head-local space;
* computes one starting scale/offset for every style from the measured skull
  above the brow against the buzz cut's cap (width and depth, plus a small
  margin), as the shared-body build used one reviewed fit for all styles; the
  radial push then settles each style over the skull.

Output: one fitted GLB per style (styles 1..N of the model's list; style 0 is
the unfitted buzz cut every body shares) and a report with each style's
starting fit and largest correction.  Nothing is written into the client.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies' / 'vendor'))
import equipment_authoring as ea  # noqa: E402
import fit_character_appearance as fca  # noqa: E402
import glbkit as g  # noqa: E402
from shared_player_bodies import dense_weights  # noqa: E402
from verify_shared_player_bodies import primitives  # noqa: E402

STYLES = ('parted', 'long', 'buns', 'buzzed', 'bob', 'ponytail', 'braid', 'topknot', 'mohawk')
HEAD_SURFACES = ('body', 'scalp', 'eyes', 'eyebrows')


def head_data(d, b):
    names = [d['nodes'][j]['name'] for j in d['skins'][0]['joints']]
    head_slot = names.index('Head')
    verts = None
    faces = []
    for name, _role, attrs, f in primitives(d, b):
        if name not in HEAD_SURFACES:
            continue
        verts = attrs
        w = dense_weights(attrs)
        head_w = w[:, head_slot] + w[:, names.index('neck_01')] * 0.0
        keep = head_w[f].mean(1) > 0.5
        faces.append(f[keep])
    f = np.concatenate(faces)
    used = np.unique(f)
    remap = -np.ones(len(verts['POSITION']), int)
    remap[used] = np.arange(len(used))
    hi = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'Head')
    matrix = ea.global_matrices(d)[hi]
    v = (verts['POSITION'][used] - matrix[:3, 3]) @ matrix[:3, :3]
    mesh = trimesh.Trimesh(v, remap[f], process=False)
    return mesh, dense_weights(verts)[used], matrix


def base_fit(skull: trimesh.Trimesh, style: Path, margin: float = 1.03) -> dict:
    v = skull.vertices
    top = np.percentile(v[(abs(v[:, 0]) < .045)][:, 1], 99)
    band = v[(v[:, 1] > top - .11) & (v[:, 1] < top - .04)]       # skull above the brow
    sd, sb = g.read(style)
    raw = np.concatenate([g.accessor(sd, sb, p['attributes']['POSITION'])
                          for m in sd['meshes'] for p in m['primitives']])
    cap_top = raw[(abs(raw[:, 0]) < .04)][:, 1].max()
    cap = raw[(raw[:, 1] > cap_top - .11) & (raw[:, 1] < cap_top - .04)]
    def extent(p, axis):
        return np.percentile(p[:, axis], 97) - np.percentile(p[:, axis], 3)
    def centre(p, axis):
        return (np.percentile(p[:, axis], 97) + np.percentile(p[:, axis], 3)) / 2
    sx = margin * extent(band, 0) / max(extent(cap, 0), 1e-6)
    sz = margin * extent(band, 2) / max(extent(cap, 2), 1e-6)
    return {'scale': [float(sx), 1.0, float(sz)],
            'offset': [float(centre(band, 0) - centre(cap, 0) * sx), 0.0,
                       float(centre(band, 2) - centre(cap, 2) * sz)]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('body', type=Path)
    ap.add_argument('--styles', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--sex', choices=('male', 'female'), required=True)
    args = ap.parse_args()
    if 'godot-client' in args.out.resolve().parts:
        raise SystemExit('write to scratch; installing is a separate reviewed step')
    args.out.mkdir(parents=True, exist_ok=True)
    d, b = g.read(args.body)
    head = head_data(d, b)
    report = {}
    # One starting fit for every style, measured on the skull-hugging buzz
    # cut: a style's own cap band includes its buns, braids or long locks and
    # would squeeze or stretch the style to make them match the skull.
    fit = base_fit(head[0], args.styles / f'buzzed_{args.sex}.glb')
    for style in STYLES:
        source = args.styles / f'{style}_{args.sex}.glb'
        target = args.out / f'{args.body.stem}_{source.name}'
        result = fca.fit_hair(source, target, head, fit, json.loads(json.dumps(d)), b)
        report[style] = {'fit': fit, **result}
        print(style, json.dumps(fit), round(result['maxRadialCorrectionM'], 4), flush=True)
    (args.out / f'{args.body.stem}.hair.json').write_text(json.dumps(report, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
