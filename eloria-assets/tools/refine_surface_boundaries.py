"""Cut a rigged body's triangles along its painted skin/shirt/trouser/boot borders.

    python eloria-assets/tools/refine_surface_boundaries.py <rigged.glb> <out.glb> [--samples 17]

tpose_bodies/surfaces.py assigns whole triangles to the tintable surfaces, so a
border such as the shirt's neckline follows triangle edges, not the paint: a
dyed shirt shows a saw-tooth collar and cuffs (each tooth a triangle of skin
painted shirt or the reverse).  This pre-pass moves the border onto the paint.

Every vertex is given the painted class nearest its texel (skin, shirt,
trousers, boots - colours learned from unambiguous body regions, as the
splitter does).  Every edge whose two ends differ is split where the texture
along it changes class (the edge's UV segment is sampled), and each triangle is
re-cut through its split points (marching triangles: one, two or three cut
edges).  A split point is computed once per geometric edge - welded by
position, so both sides of a UV seam take the same point and no crack opens -
and every attribute is interpolated: position, normal, UV, and skin weights
(the two ends' joints merged, the four largest kept, renormalised).

The surface shape is unchanged (new vertices lie on the original edges); only
the triangulation along the borders gets finer.  Run surfaces.py on the result.
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
from surfaces import texture  # noqa: E402
import glbkit as g  # noqa: E402

CLASSES = ('skin', 'shirt', 'pants', 'boots')


def class_colours(v, rgb, head_y, used):
    seeds = {
        'boots': v[:, 1] < 0.30,
        'pants': (v[:, 1] > 0.50) & (v[:, 1] < 0.80),
        'shirt': (v[:, 1] > 1.05) & (v[:, 1] < 1.30) & (np.abs(v[:, 0]) < 0.14),
        'skin': (v[:, 1] > head_y + 0.02) & (v[:, 1] < head_y + 0.07) & (v[:, 2] > 0.03) & (np.abs(v[:, 0]) < 0.05),
    }
    return np.stack([np.median(rgb[seeds[c] & used], axis=0) for c in CLASSES])


def classify(rgb, colours, radius=0.30):
    d = np.linalg.norm(rgb[:, None, :] - colours[None], axis=2)
    cls = d.argmin(1)
    cls[d.min(1) > radius] = -1          # far from every class colour: leave its edges alone
    return cls


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--samples', type=int, default=17)
    ap.add_argument('--colours', help='JSON {skin,shirt,pants,boots: [r,g,b]} (0-1) when the body regions cannot be sampled reliably')
    args = ap.parse_args()
    if 'godot-client' in args.out.resolve().parts:
        raise SystemExit('write to scratch')
    d, b = split.read_glb(args.source)
    nodes = [n for n in d['nodes'] if 'mesh' in n]
    if len(nodes) != 1 or len(d['meshes'][nodes[0]['mesh']]['primitives']) != 1:
        raise SystemExit('expected one unsplit primitive')
    node = nodes[0]
    prim = d['meshes'][node['mesh']]['primitives'][0]
    attrs = {k: split.accessor_array(d, b, i) for k, i in prim['attributes'].items()}
    faces = split.accessor_array(d, b, prim['indices']).astype(np.int64).reshape(-1, 3)
    v = attrs['POSITION']; uv = attrs['TEXCOORD_0']
    world = g.globals_of(d); skin = d['skins'][node['skin']]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    head_y = world[skin['joints'][names.index('Head')]][1, 3]
    tex = np.asarray(texture(d, b, prim)).astype(np.float32) / 255.0
    H, W = tex.shape[:2]

    def sample(u):
        x = np.clip((u[..., 0] % 1) * (W - 1), 0, W - 1).astype(int)
        y = np.clip((u[..., 1] % 1) * (H - 1), 0, H - 1).astype(int)
        return tex[y, x]

    # Sample just inside each triangle: on remeshed Meshy atlases a vertex sits
    # on its UV island's border, where the texel is island padding, not paint.
    cen = uv[faces].mean(1)
    inner = uv[faces] * 0.7 + cen[:, None, :] * 0.3            # (F, 3, 2)
    corner_rgb = sample(inner)                                  # (F, 3, 3)
    rgb_v = np.zeros((len(v), 3)); cnt = np.zeros(len(v))
    for k in range(3):
        np.add.at(rgb_v, faces[:, k], corner_rgb[:, k]); np.add.at(cnt, faces[:, k], 1)
    rgb_v /= np.maximum(cnt, 1)[:, None]
    colours = class_colours(v, rgb_v, head_y, cnt > 0)   # vertices no triangle uses carry no paint
    if args.colours:
        given = json.loads(args.colours)
        colours = np.array([given[c] if c in given else colours[i] for i, c in enumerate(CLASSES)], dtype=np.float64)
    votes = np.zeros((len(v), len(CLASSES) + 1))
    corner_cls = classify(corner_rgb.reshape(-1, 3), colours).reshape(-1, 3)
    for k in range(3):
        np.add.at(votes, (faces[:, k], corner_cls[:, k]), 1)     # -1 lands in the last column
    vcls = votes[:, :len(CLASSES)].argmax(1)
    vcls[votes[:, :len(CLASSES)].max(1) < votes[:, -1]] = -1
    third = {}
    for f in faces:
        for i in range(3):
            third[(int(f[i]), int(f[(i + 1) % 3]))] = int(f[(i + 2) % 3])
            third[(int(f[(i + 1) % 3]), int(f[i]))] = int(f[(i + 2) % 3])
    # geometric edge identity across UV seams
    _, weld = np.unique(np.round(v, 6), axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    split_t = {}            # welded (lo, hi) -> t measured from lo
    edge_new = {}           # (va, vb) unwelded ordered -> new vertex index
    new_rows = {k: [] for k in attrs}
    n0 = len(v)
    ts = np.linspace(0.0, 1.0, args.samples)

    def crossing(a, c):
        """t along a->c where the texture leaves a's class, or None."""
        if vcls[a] < 0 or vcls[c] < 0 or vcls[a] == vcls[c]:
            return None
        key = (weld[a], weld[c]) if weld[a] <= weld[c] else (weld[c], weld[a])
        if key not in split_t:
            pts = uv[a][None] * (1 - ts[:, None]) + uv[c][None] * ts[:, None]
            o = third.get((a, c))
            if o is not None:                     # nudge the probe line 15% into the triangle
                pts = pts * 0.85 + uv[o][None] * 0.15
            cls = classify(sample(pts), colours)
            change = np.flatnonzero(cls != vcls[a])
            k = int(change[0]) if len(change) else len(ts) - 1
            t = 0.5 * (ts[max(k - 1, 0)] + ts[k])
            t = float(np.clip(t, 0.05, 0.95))
            split_t[key] = t if weld[a] <= weld[c] else 1.0 - t
        t = split_t[key]
        return t if weld[a] <= weld[c] else 1.0 - t

    def new_vertex(a, c, t):
        if (a, c) in edge_new:
            return edge_new[(a, c)]
        if (c, a) in edge_new:
            return edge_new[(c, a)]
        idx = n0 + len(new_rows['POSITION'])
        for k, arr in attrs.items():
            if k in ('JOINTS_0', 'WEIGHTS_0'):
                continue
            val = arr[a] * (1 - t) + arr[c] * t
            if k == 'NORMAL':
                val = val / max(np.linalg.norm(val), 1e-12)
            new_rows[k].append(val)
        acc = {}
        for j, w in ((attrs['JOINTS_0'][a], attrs['WEIGHTS_0'][a] * (1 - t)), (attrs['JOINTS_0'][c], attrs['WEIGHTS_0'][c] * t)):
            for jj, ww in zip(j.astype(int), w):
                if ww > 0:
                    acc[jj] = acc.get(jj, 0.0) + float(ww)
        top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
        s = sum(w for _, w in top) or 1.0
        jrow = np.zeros(4); wrow = np.zeros(4)
        for i, (jj, ww) in enumerate(top):
            jrow[i] = jj; wrow[i] = ww / s
        new_rows['JOINTS_0'].append(jrow); new_rows['WEIGHTS_0'].append(wrow)
        edge_new[(a, c)] = idx
        return idx

    out_faces = []
    cut = {1: 0, 2: 0, 3: 0}
    for f in faces:
        a, bb, c = (int(x) for x in f)
        m_ab = crossing(a, bb); m_bc = crossing(bb, c); m_ca = crossing(c, a)
        splits = [m is not None for m in (m_ab, m_bc, m_ca)]
        n = sum(splits)
        if n == 0:
            out_faces.append((a, bb, c)); continue
        cut[n] += 1
        p = new_vertex(a, bb, m_ab) if splits[0] else None
        q = new_vertex(bb, c, m_bc) if splits[1] else None
        r = new_vertex(c, a, m_ca) if splits[2] else None
        if n == 3:
            out_faces += [(a, p, r), (p, bb, q), (r, q, c), (p, q, r)]
        elif n == 2:
            if not splits[1]:      # a is the odd vertex: cuts on ab and ca
                out_faces += [(a, p, r), (p, bb, c), (p, c, r)]
            elif not splits[2]:    # b is odd: cuts on ab and bc
                out_faces += [(bb, q, p), (q, c, a), (q, a, p)]
            else:                  # c is odd: cuts on bc and ca
                out_faces += [(c, r, q), (r, a, bb), (r, bb, q)]
        else:
            if splits[0]:
                out_faces += [(a, p, c), (p, bb, c)]
            elif splits[1]:
                out_faces += [(a, bb, q), (a, q, c)]
            else:
                out_faces += [(a, bb, r), (r, bb, c)]
    # write: new accessors for every attribute and the index buffer
    bb_ = bytearray(b)
    for k, arr in attrs.items():
        full = np.concatenate([arr, np.array(new_rows[k]).reshape(-1, arr.shape[1])]) if new_rows[k] else arr
        acc0 = d['accessors'][prim['attributes'][k]]
        if k == 'JOINTS_0':
            prim['attributes'][k] = append(d, bb_, full.astype('<u2' if acc0['componentType'] == 5123 else '<u1'),
                                           acc0['componentType'], 'VEC4', 34962)
        elif k == 'WEIGHTS_0':
            prim['attributes'][k] = append(d, bb_, full.astype('<f4'), 5126, 'VEC4', 34962)
        else:
            prim['attributes'][k] = append(d, bb_, full.astype('<f4'), 5126, acc0['type'], 34962)
    prim['indices'] = append(d, bb_, np.array(out_faces, '<u4').reshape(-1), 5125, 'SCALAR', 34963)
    pos_acc = d['accessors'][prim['attributes']['POSITION']]
    allpos = np.concatenate([v, np.array(new_rows['POSITION'])]) if new_rows['POSITION'] else v
    pos_acc['min'] = allpos.min(0).tolist(); pos_acc['max'] = allpos.max(0).tolist()
    d.setdefault('asset', {}).setdefault('extras', {})['eloriaBoundaryRefine'] = {
        'version': 1, 'classes': list(CLASSES), 'colours': colours.round(4).tolist()}
    # split.read_glb keeps the BIN chunk's 8-byte header in front of the payload
    d, blob = g.compact(d, bytes(bb_[8:]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    g.write(args.out, d, blob)
    print(json.dumps({'faces_in': int(len(faces)), 'faces_out': len(out_faces), 'new_vertices': len(new_rows['POSITION']),
                      'cut_triangles': cut, 'colours': dict(zip(CLASSES, colours.round(3).tolist()))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
