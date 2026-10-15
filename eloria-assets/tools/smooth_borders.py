"""Cut a packed Human body's neckline and sleeve cuffs along smooth lines.

    python eloria-assets/tools/smooth_borders.py <body.glb> <out.glb> [--loops neck,wrist_l,wrist_r]
        [--sigma 0.012] [--band 0.03]

refine_surface_boundaries.py moves the skin/shirt border onto the paint, which
cured most of the borders. The necklines and cuffs of the regenerated bodies
(2026-10) are the exception: the shirt is near-white and the skin pale, the
two classes are ambiguous there, and the border zig-zags 1-1.5 cm about every
3 cm - a row of cloth teeth up the nape, down the sides of the V and round
each wrist of every bare-shirted Human.

Here each border is taken from the geometry instead. A skin/shirt border
around a joint axis (the neck, a forearm) is followed as one closed loop,
resampled every 3 mm along its length and smoothed along that length with a
Gaussian of `--sigma` metres: teeth 3 cm apart all but vanish, while the long
sides of a V keep their line and only its point is rounded by about sigma. The
smoothed loop is pulled back onto the surface. Every body and shirt triangle
within `--band` of it is then re-cut along it: the field is the signed
distance across the loop (the direction out from the axis crossed with the
loop's direction, pointing to the skin side), marching triangles over that
field, new vertices on the original edges (positions, normals, UVs and skin
weights interpolated; the four largest weights kept), so the surface shape
does not move and nothing fitted to it needs refitting. Pieces on the skin
side become skin, the rest shirt. Points near the loop that stand off the
surface - the folded placket of a V, the lip of a collar - keep their surface.

The two surfaces read different textures (the skin the colour atlas, the
shirt the greyscale tintable atlas), so a piece that changes side would show
the other side's paint. The texels under, and just past, every re-cut
triangle are repainted on the side they now belong to wherever they still
carry the other class's colour: on the colour atlas cloth is told from skin by
its lack of warmth, on the tintable atlas by its grey value.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tpose_bodies' / 'vendor'))
import glbkit as g  # noqa: E402

BLEED = 2.5        # texels painted past a re-cut piece's edge
STEP = 0.003       # loop resampling, metres

# name: (axis from joint, axis to joint, how far from the axis the border may
# lie, how far along the axis either side of the first joint it may lie, mode).
# A neckline is followed as a loop: it has a V to keep. A cuff is a ring, and
# its border is broken into pieces where the cuff's lip folds over, so it is
# cut by the plane that best fits the border's points.
LOOPS = {
    'neck': ('neck_01', '+y', 0.15, (-0.15, 0.20), 'loop'),
    'wrist_l': ('hand_l', 'lowerarm_l', 0.09, (-0.12, 0.12), 'plane'),
    'wrist_r': ('hand_r', 'lowerarm_r', 0.09, (-0.12, 0.12), 'plane'),
}


def append(d: dict, blob: bytearray, values: np.ndarray, ctype: int, atype: str, target: int | None = None,
           minmax: bool = False) -> int:
    while len(blob) % 4:
        blob.append(0)
    data = np.ascontiguousarray(values).tobytes()
    view = {'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data)}
    if target:
        view['target'] = target
    d['bufferViews'].append(view)
    blob += data
    acc = {'bufferView': len(d['bufferViews']) - 1, 'componentType': ctype, 'count': int(len(values)), 'type': atype}
    if minmax:
        flat = np.asarray(values).reshape(len(values), -1)
        acc['min'] = [float(v) for v in flat.min(0)]
        acc['max'] = [float(v) for v in flat.max(0)]
    d['accessors'].append(acc)
    return len(d['accessors']) - 1


def joint_position(d: dict, blob: bytes, name: str) -> np.ndarray:
    skin = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    ibm = g.accessor(d, blob, skin['inverseBindMatrices']).reshape(-1, 4, 4)
    return np.linalg.inv(ibm[names.index(name)].T)[:3, 3]


def image_of(d: dict, blob: bytes, material: int) -> tuple[int, Image.Image]:
    tex = d['materials'][material]['pbrMetallicRoughness']['baseColorTexture']['index']
    image = d['textures'][tex]['source']
    view = d['bufferViews'][d['images'][image]['bufferView']]
    start = view.get('byteOffset', 0)
    return image, Image.open(io.BytesIO(blob[start:start + view['byteLength']])).convert('RGB')


def closest_on_triangle(p, a, b, c):
    """Closest point to p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return a
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 <= d1 and d3 <= 0:
        return a + ab * (d1 / (d1 - d3))
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 <= d2 and d6 <= 0:
        return a + ac * (d2 / (d2 - d6))
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        return b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6)))
    denom = 1.0 / (va + vb + vc)
    return a + ab * (vb * denom) + ac * (vc * denom)


class Axis:
    """A joint axis: origin, unit direction, and radial / along measures."""

    def __init__(self, origin, toward):
        self.origin = origin
        self.dir = (toward - origin) / np.linalg.norm(toward - origin)

    def along(self, p):
        return (p - self.origin) @ self.dir

    def radial(self, p):
        r = (p - self.origin) - np.outer(self.along(p), self.dir) if p.ndim > 1 else \
            (p - self.origin) - self.along(p) * self.dir
        return r

    def radius(self, p):
        return np.linalg.norm(self.radial(p), axis=-1)


def border_loop(where: np.ndarray, border: set, axis: Axis, reach: float, span) -> np.ndarray:
    """A skin/shirt border around an axis as an ordered closed polyline.

    The border can carry spurs and small islands where a stray patch of skin
    or cloth touches it, and can break for a centimetre or two where the skin
    meets something else. The loop is the longest cycle that winds once
    around the axis; failing that, the longest path between two loose ends a
    short gap apart that does, closed across its gap.
    """
    import networkx as nx
    pts = where
    near = {v for e in border for v in e
            if axis.radius(pts[v]) < reach and span[0] < axis.along(pts[v]) < span[1]}
    graph = nx.Graph()
    for a, c in border:
        if a in near and c in near:
            graph.add_edge(a, c, weight=float(np.linalg.norm(pts[a] - pts[c])))
    # a frame around the axis for the winding count
    ref = np.cross(axis.dir, [0.0, 0.0, 1.0])
    if np.linalg.norm(ref) < 0.1:
        ref = np.cross(axis.dir, [1.0, 0.0, 0.0])
    e1 = ref / np.linalg.norm(ref)
    e2 = np.cross(axis.dir, e1)

    def winding(cycle):
        r = axis.radial(pts[cycle])
        a = np.arctan2(r @ e2, r @ e1)
        step = np.diff(np.concatenate([a, a[:1]]))
        return abs(np.sum((step + np.pi) % (2 * np.pi) - np.pi)) / (2 * np.pi)

    def length(cycle):
        q = pts[cycle + cycle[:1]]
        return float(np.linalg.norm(np.diff(q, axis=0), axis=1).sum())

    cycles = [c for c in nx.cycle_basis(graph) if winding(c) > 0.5]
    if not cycles:
        ends = [v for v, k in graph.degree() if k == 1]
        for i, a in enumerate(ends):
            for c in ends[i + 1:]:
                if np.linalg.norm(pts[a] - pts[c]) > 0.04 or not nx.has_path(graph, a, c):
                    continue
                path = nx.shortest_path(graph, a, c, weight='weight')
                if winding(path) > 0.5:
                    cycles.append(path)
    if not cycles:
        raise SystemExit('no border loop goes around the axis')
    return pts[np.array(max(cycles, key=length))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--loops', default='neck,wrist_l,wrist_r')
    ap.add_argument('--sigma', type=float, default=0.012, help='smoothing along each loop, metres')
    ap.add_argument('--band', type=float, default=0.03, help='re-cut triangles within this distance of a loop')
    ap.add_argument('--quality', type=int, default=92)
    args = ap.parse_args()
    if 'godot-client' in args.out.resolve().parts:
        raise SystemExit('write to scratch; install the result separately')
    d, blob = g.read(args.source)
    nodes = {n['name']: n for n in d['nodes'] if 'mesh' in n}
    body = d['meshes'][nodes['body']['mesh']]['primitives'][0]
    shirt = d['meshes'][nodes['wardrobe_shirt']['mesh']]['primitives'][0]
    if body['attributes'] != shirt['attributes']:
        raise SystemExit('expected the body and shirt to share one vertex buffer (pack_human_body output)')
    keys = list(body['attributes'])
    attrs = {k: g.accessor(d, blob, body['attributes'][k]) for k in keys}
    faces = {name: [tuple(t) for t in g.accessor(d, blob, prim['indices']).astype(np.int64).reshape(-1, 3)]
             for name, prim in (('body', body), ('shirt', shirt))}
    recut = {'body': [], 'shirt': []}            # (triangle, loop index)
    loops_out = []
    stats = {'cut': 0, 'to_skin': 0, 'to_shirt': 0}

    for loop_index, loop_name in enumerate(args.loops.split(',')):
        a_name, b_name, reach, span, mode = LOOPS[loop_name]
        start = joint_position(d, blob, a_name)
        # the neck is measured about the vertical through neck_01: the head
        # joint leans forward, and a low front scoop would fall outside a
        # radius measured from the leaning line
        axis = Axis(start, start + [0.0, 1.0, 0.0] if b_name == '+y' else joint_position(d, blob, b_name))
        P = attrs['POSITION']
        _, weld = np.unique(np.round(P, 5), axis=0, return_inverse=True)
        weld = weld.reshape(-1)

        def edges(f):
            f = np.array(f, np.int64)
            e = weld[np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])]
            e.sort(1)
            return set(map(tuple, e))

        where = np.zeros((weld.max() + 1, 3))
        where[weld] = P
        border = edges(faces['body']) & edges(faces['shirt'])
        if mode == 'plane':
            ring = np.array(sorted({v for e in border for v in e}))
            ring = where[ring]
            ring = ring[(axis.radius(ring) < reach) & (axis.along(ring) > span[0]) & (axis.along(ring) < span[1])]
            centre = ring.mean(0)
            normal = np.linalg.svd(ring - centre)[2][-1]
            if normal @ axis.dir > 0:                 # point to the skin, toward the hand
                normal = -normal

            def field_at(points, centre=centre, normal=normal):
                side = (points - centre) @ normal
                return side, np.abs(side)

            side, dist = field_at(P)
            field = np.where((dist < args.band) & (axis.radius(P) < reach), side, np.nan)
            loop = ring
            total = 0.0
        else:
            loop = border_loop(where, border, axis, reach, span)
            closed = np.vstack([loop, loop[:1]])
            s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))])
            total = float(s[-1])
            dense = np.stack([np.interp(np.arange(0, total, STEP), s, closed[:, k]) for k in range(3)], 1)
            offsets = np.arange(-int(4 * args.sigma / STEP), int(4 * args.sigma / STEP) + 1)
            kernel = np.exp(-0.5 * (offsets * STEP / args.sigma) ** 2)
            kernel /= kernel.sum()
            smooth = np.zeros_like(dense)
            for o, k in zip(offsets, kernel):
                smooth += k * np.roll(dense, -o, axis=0)
            tris = np.array(faces['body'] + faces['shirt'], np.int64)
            _, idx = cKDTree(P[tris].mean(1)).query(smooth, k=16)
            for i in range(len(smooth)):
                best, bestd = smooth[i], 1e9
                for t in idx[i]:
                    q = closest_on_triangle(smooth[i], *P[tris[t]])
                    dd = float(np.linalg.norm(q - smooth[i]))
                    if dd < bestd:
                        best, bestd = q, dd
                smooth[i] = best
            tangent = np.roll(smooth, -1, axis=0) - np.roll(smooth, 1, axis=0)
            tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-12)
            # The surface faces out from the joint axis; that is a steadier normal
            # here than the vertex normals, which turn in where a collar or cuff
            # folds over. No smoothing of `across` along the loop: at the point of
            # a V the loop doubles back and the skin side genuinely swaps hands.
            outward = axis.radial(smooth)
            outward /= np.maximum(np.linalg.norm(outward, axis=1, keepdims=True), 1e-12)
            across = np.cross(outward, tangent)
            across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-12)
            # skin lies toward the head from a neckline, toward the hand from a cuff
            skin_way = axis.dir if loop_name == 'neck' else -axis.dir
            if np.mean(across @ skin_way) < 0:
                across = -across
            tree_l = cKDTree(smooth)

            def field_at(points, tree_l=tree_l, smooth=smooth, across=across):
                dist, near = tree_l.query(points)
                return np.einsum('ij,ij->i', points - smooth[near], across[near]), dist

            side, dist = field_at(P)
            _, near_l = tree_l.query(P)
            off = np.abs(np.einsum('ij,ij->i', P - smooth[near_l], outward[near_l]))
            field = np.where((dist < args.band) & (off <= 0.006 + 0.5 * np.abs(side)), side, np.nan)

        new_rows = {k: [] for k in keys}
        made = {}

        def cut(a, c):
            key = (a, c) if a < c else (c, a)
            if key in made:
                return made[key]
            t = field[a] / (field[a] - field[c])
            for k in keys:
                if k in ('JOINTS_0', 'WEIGHTS_0'):
                    continue
                value = attrs[k][a] * (1 - t) + attrs[k][c] * t
                if k == 'NORMAL':
                    value = value / max(np.linalg.norm(value), 1e-12)
                new_rows[k].append(value)
            weights = {}
            for j, wgt in ((attrs['JOINTS_0'][a], attrs['WEIGHTS_0'][a] * (1 - t)),
                           (attrs['JOINTS_0'][c], attrs['WEIGHTS_0'][c] * t)):
                for jj, ww in zip(j.astype(int), wgt):
                    if ww > 0:
                        weights[jj] = weights.get(jj, 0.0) + float(ww)
            top = sorted(weights.items(), key=lambda kv: -kv[1])[:4]
            total_w = sum(v for _, v in top) or 1.0
            jrow, wrow = np.zeros(4), np.zeros(4)
            for i, (jj, ww) in enumerate(top):
                jrow[i], wrow[i] = jj, ww / total_w
            new_rows['JOINTS_0'].append(jrow)
            new_rows['WEIGHTS_0'].append(wrow)
            made[key] = len(P) + len(new_rows['POSITION']) - 1
            return made[key]

        out = {'body': [], 'shirt': []}
        for name in ('body', 'shirt'):
            for tri in faces[name]:
                f = field[list(tri)]
                if np.isnan(f).any():
                    out[name].append(tri)
                    continue
                above, below = [], []
                for i in range(3):
                    a, c = int(tri[i]), int(tri[(i + 1) % 3])
                    (above if f[i] >= 0 else below).append(a)
                    if (f[i] >= 0) != (f[(i + 1) % 3] >= 0):
                        m = cut(a, c)
                        above.append(m)
                        below.append(m)
                if len(above) >= 3 and len(below) >= 3:
                    stats['cut'] += 1
                # On a cuff, the inside of the sleeve's folded lip lies on the
                # hand's side of the plane but faces in, toward the wrist: it is
                # the sleeve's lining, not skin, whichever surface the paint
                # gave it, so it becomes shirt.
                lining = False
                if mode == 'plane':
                    corners = P[list(tri)]
                    facing = np.cross(corners[1] - corners[0], corners[2] - corners[0])
                    lining = float(facing @ axis.radial(corners.mean(0))) < 0
                for poly, target in ((above, 'shirt' if lining else 'body'), (below, 'shirt')):
                    if len(poly) < 3:
                        continue
                    for k in range(1, len(poly) - 1):
                        piece = (poly[0], poly[k], poly[k + 1])
                        out[target].append(piece)
                        recut[target].append((piece, loop_index))
                    if target != name:
                        stats['to_skin' if target == 'body' else 'to_shirt'] += 1
        for k in keys:
            if new_rows[k]:
                attrs[k] = np.concatenate([attrs[k], np.array(new_rows[k]).reshape(-1, attrs[k].shape[1])])
        faces = out
        loops_out.append({'name': loop_name, 'points': int(len(loop)), 'length': round(total, 3),
                          'newVertices': len(new_rows['POSITION']), 'field': field_at})

    blob = bytearray(blob)
    acc_new = {}
    for k in keys:
        old = d['accessors'][body['attributes'][k]]
        if k == 'JOINTS_0':
            ctype = old['componentType']
            acc_new[k] = append(d, blob, attrs[k].astype('<u2' if ctype == 5123 else 'u1'), ctype, 'VEC4', 34962)
        else:
            acc_new[k] = append(d, blob, attrs[k].astype('<f4'), 5126, old['type'], 34962, minmax=(k == 'POSITION'))
    shared = dict(body['attributes'])
    for mesh in d['meshes']:
        for prim in mesh['primitives']:
            if prim['attributes'] == shared:
                prim['attributes'] = dict(acc_new)
    for name, prim in (('body', body), ('shirt', shirt)):
        prim['indices'] = append(d, blob, np.array(faces[name], '<u4').reshape(-1), 5125, 'SCALAR', 34963)

    PF, UVF = attrs['POSITION'], attrs['TEXCOORD_0']

    def field_of(piece, loop_index, points):
        return loops_out[loop_index]['field'](points)[0]

    def repaint(material, pieces, keep_side, wrong_colour, fill):
        image_index, im = image_of(d, bytes(blob), material)
        px = np.asarray(im, np.float32).copy()
        H, W = px.shape[:2]
        changed = 0
        for tri, loop_index in pieces:
            uv = UVF[list(tri)] * [W, H]
            lo = np.clip(np.floor(uv.min(0) - BLEED - 1).astype(int), 0, [W - 1, H - 1])
            hi = np.clip(np.ceil(uv.max(0) + BLEED + 1).astype(int), 0, [W - 1, H - 1])
            ys, xs = np.mgrid[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
            q = np.stack([xs + 0.5, ys + 0.5], -1).reshape(-1, 2)
            a, b, c = uv
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(den) < 1e-9:
                continue
            l0 = ((b[1] - c[1]) * (q[:, 0] - c[0]) + (c[0] - b[0]) * (q[:, 1] - c[1])) / den
            l1 = ((c[1] - a[1]) * (q[:, 0] - c[0]) + (a[0] - c[0]) * (q[:, 1] - c[1])) / den
            l2 = 1 - l0 - l1
            # BLEED texels past each edge too: a cut piece can be a sliver a
            # texel wide, and filtering (and every mip level) reads its
            # neighbours, so painting the footprint alone leaves the old
            # colour bleeding through at a distance
            reach = [abs(den) / max(float(np.linalg.norm(uv[(i + 1) % 3] - uv[(i + 2) % 3])), 1e-9) for i in range(3)]
            inside = (l0 * reach[0] > -BLEED) & (l1 * reach[1] > -BLEED) & (l2 * reach[2] > -BLEED)
            if not inside.any():
                continue
            lam = np.clip(np.stack([l0, l1, l2], 1)[inside], 0, 1)
            lam /= lam.sum(1, keepdims=True)
            f = field_of(tri, loop_index, lam @ PF[list(tri)])
            xi, yi = xs.reshape(-1)[inside], ys.reshape(-1)[inside]
            sel = wrong_colour(px[yi, xi]) & ((f > -0.006) if keep_side > 0 else (f < 0.006))
            px[yi[sel], xi[sel]] = fill
            changed += int(sel.sum())
        buf = io.BytesIO()
        Image.fromarray(np.clip(px, 0, 255).astype(np.uint8)).save(buf, 'JPEG', quality=args.quality)
        data = buf.getvalue()
        while len(blob) % 4:
            blob.append(0)
        d['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data)})
        blob.extend(data)
        d['images'][image_index]['bufferView'] = len(d['bufferViews']) - 1
        return changed

    def sample(material, pieces, keep_side, margin):
        _, im = image_of(d, bytes(blob), material)
        px = np.asarray(im, np.float32)
        H, W = px.shape[:2]
        values = []
        for tri, loop_index in pieces:
            f = field_of(tri, loop_index, PF[list(tri)].mean(0)[None])[0]
            if (f > margin) if keep_side > 0 else (f < -margin):
                uv = UVF[list(tri)].mean(0) * [W, H]
                values.append(px[int(np.clip(uv[1], 0, H - 1)), int(np.clip(uv[0], 0, W - 1))])
        return np.median(np.array(values), 0) if values else None

    # Skin is warm and the shirt neutral: cloth paint on the colour atlas is
    # told by its lack of warmth (red over blue), so the grey of a shaded fold
    # is caught as well as the white. One fill per border: a wrist is not the
    # colour of a nape.
    painted = 0
    for side_name, keep, material in (('body', +1, body['material']), ('shirt', -1, shirt['material'])):
        for loop_index in range(len(loops_out)):
            mine = [p for p in recut[side_name] if p[1] == loop_index]
            if side_name == 'body':
                skin_colour = sample(material, mine, +1, 0.008)
                if skin_colour is None:
                    continue
                warmth = float(skin_colour[0] - skin_colour[2])
                painted += repaint(material, mine, +1, lambda c, w=warmth: (c[:, 0] - c[:, 2]) < 0.5 * w, skin_colour)
                loops_out[loop_index]['skinColour'] = skin_colour.round(1).tolist()
            else:
                shirt_value = sample(material, mine, -1, 0.008)
                skin_value = sample(material, [p for p in recut['body'] if p[1] == loop_index], +1, 0.008)
                if shirt_value is None or skin_value is None:
                    continue
                painted += repaint(material, mine, -1,
                                   lambda c, s=shirt_value, k=skin_value: np.abs(c.mean(1) - k.mean()) < np.abs(c.mean(1) - s.mean()),
                                   shirt_value)

    summary = [{k: v for k, v in loop.items() if k != 'field'} for loop in loops_out]
    d.setdefault('asset', {}).setdefault('extras', {})['eloriaBorderSmooth'] = {
        'version': 3, 'sigma': args.sigma, 'band': args.band, 'loops': summary,
        'cutTriangles': stats['cut'], 'toSkin': stats['to_skin'], 'toShirt': stats['to_shirt'], 'texelsRepainted': painted}
    d, blob = g.compact(d, bytes(blob))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    g.write(args.out, d, blob)
    print(json.dumps({'loops': summary, **stats, 'texels_repainted': painted}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
