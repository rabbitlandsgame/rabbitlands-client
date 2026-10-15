"""Remove the hidden inner wall of a thickened Meshy shell from a rigged body.

    python eloria-assets/tools/drop_inner_shell.py <rigged.glb> <mask.npz> <out.glb>

Some Meshy deliveries model clothing (and even the head) as a solid shell a
few millimetres thick: the regenerated Human male (2026-10-05) arrived with
7,038 of its 19,999 triangles on the inside wall, ~4 mm under the visible
surface and facing inward, unpainted.  The material is double-sided, so the
wall is drawn for nothing, competes with the outer surface when a bend
squeezes the two together, and confuses anything that samples "the body".

`mask.npz` comes from a Blender pass over the same file (outside-in visibility
from 60 directions; a hidden face whose back side reaches a visible face
within 15 mm is inner wall) and carries `inner` (bool per triangle) and `cen`
(the triangle centroids in glTF axes).  The centroids are checked against this
file's own triangles before anything is removed, so a mask made for another
file or a reordered import cannot be applied.  Vertices are kept; only the
index buffer shrinks, then unused data is compacted away.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'tpose_bodies'))
sys.path.insert(0, str(HERE / 'tpose_bodies' / 'vendor'))
from build import split, append  # noqa: E402
import glbkit as g  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('mask', type=Path)
    ap.add_argument('out', type=Path)
    args = ap.parse_args()
    d, b = split.read_glb(args.source)
    node = next(n for n in d['nodes'] if 'mesh' in n)
    prim = d['meshes'][node['mesh']]['primitives'][0]
    v = split.accessor_array(d, b, prim['attributes']['POSITION'])
    faces = split.accessor_array(d, b, prim['indices']).astype(np.int64).reshape(-1, 3)
    m = np.load(args.mask)
    inner, cen = m['inner'], m['cen']
    if len(inner) != len(faces):
        raise SystemExit(f'mask has {len(inner)} triangles, file has {len(faces)}')
    err = np.abs(v[faces].mean(1) - cen).max()
    if err > 1e-4:
        raise SystemExit(f'triangle order differs from the mask (max centroid error {err:.6f} m)')
    keep = faces[~inner]
    bb = bytearray(b)
    prim['indices'] = append(d, bb, keep.astype('<u4').reshape(-1), 5125, 'SCALAR', 34963)
    d.setdefault('asset', {}).setdefault('extras', {})['eloriaInnerShellDropped'] = {
        'version': 1, 'removed': int(inner.sum()), 'kept': int(len(keep))}
    d, blob = g.compact(d, bytes(bb[8:]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    g.write(args.out, d, blob)
    print(json.dumps({'triangles_in': int(len(faces)), 'removed': int(inner.sum()), 'triangles_out': int(len(keep)),
                      'centroid_check_m': float(err)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
