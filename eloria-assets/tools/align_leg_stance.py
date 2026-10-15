"""Bake the legs of a packed Human body (and everything skinned to it) onto its leg bones.

    python eloria-assets/tools/align_leg_stance.py <body.glb> <out_body.glb>
        [--garments <dir of GLBs> --garments-out <dir>]

The regenerated Human male (2026-10) stands with his legs splayed against
straight leg bones: the mesh's centre runs 1.7 cm outboard of the bone line at
the knee and 3.3 cm at the ankle, and the feet sit about 4 cm outside the foot
joints. Every other body keeps its feet within 2 mm of the joints, and the
race bodies are rebuilt on this one, so the splay would spread to all of them.

The bones are the shared rig and cannot move. The mesh is moved instead: each
leg is turned in about its hip (and the shin about its knee) by the angles
that bring the mesh's centreline at knee, shin and ankle onto the bone line,
solved by least squares. The turn is applied as a pose through the skin
weights - v' = sum_j w_j S_j v with S_j the joint's posed-over-rest transform -
so the hip and knee blend as they would in an animation, and normals and
tangents turn with it. Rest bones and inverse binds stay byte-identical: the
posed shape simply becomes the bind shape.

Garments are moved by the very same pose through their own weights, so a
pair of trousers or boots fitted to the splayed legs lands on the straight
ones without a refit. Pass the variant folder to `--garments`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tpose_bodies' / 'vendor'))
import glbkit as g  # noqa: E402

SECTIONS = (0.53, 0.42, 0.30, 0.18, 0.12)     # heights the mesh centre is held to the bone line
CHAIN = ('thigh', 'calf', 'foot', 'ball', 'ball_leaf')


def rest_globals(d: dict, blob: bytes) -> dict[str, np.ndarray]:
    skin = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    ibm = g.accessor(d, blob, skin['inverseBindMatrices']).reshape(-1, 4, 4)
    return {n: np.linalg.inv(ibm[i].T) for i, n in enumerate(names)}


def about(pivot: np.ndarray, angle: float) -> np.ndarray:
    """Rotation about the forward (z) axis through `pivot`."""
    c, s = np.cos(angle), np.sin(angle)
    m = np.eye(4)
    m[:2, :2] = [[c, -s], [s, c]]
    t = np.eye(4); t[:3, 3] = pivot
    back = np.eye(4); back[:3, 3] = -pivot
    return t @ m @ back


def pose(rest: dict, angles: dict) -> dict[str, np.ndarray]:
    """Skinning matrix per joint name: identity unless it is in a leg chain."""
    out = {}
    for side in ('l', 'r'):
        hip, knee = angles[side]
        m_hip = about(rest[f'thigh_{side}'][:3, 3], hip)
        m_knee = about(rest[f'calf_{side}'][:3, 3], knee)
        out[f'thigh_{side}'] = m_hip
        for name in CHAIN[1:]:
            out[f'{name}_{side}'] = m_hip @ m_knee
    return out


RIGID_PIECE = 0.02   # pieces smaller than this move as one


def skin_attributes(positions, normals, tangents, joints, weights, names, matrices, triangles=None):
    """Linear-blend the given per-joint matrices onto vertices (normals by the rotation part).

    A blend is not a rigid motion: across a few millimetres it can squash a
    near-flat stud or buckle through itself (an Amberwood legguard's stud
    turned inside out). So every connected piece smaller than RIGID_PIECE
    moves by its vertices' mean transform, which keeps its shape.
    """
    idx = np.array([names.index(n) for n in matrices if n in names], int)
    if not len(idx):
        return positions, normals, tangents, 0
    mats = np.tile(np.eye(4), (len(names), 1, 1))
    for n, m in matrices.items():
        if n in names:
            mats[names.index(n)] = m
    blend = np.einsum('vk,vkij->vij', weights, mats[joints])
    total = weights.sum(1)
    blend /= np.where(total > 0, total, 1.0)[:, None, None]
    if triangles is not None and len(triangles):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        # pieces by position, not index: a stud's corners are often split
        # copies (one per face) that share nothing but where they are
        _, weld = np.unique(np.round(positions, 5), axis=0, return_inverse=True)
        weld = weld.reshape(-1)
        e = weld[np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])]
        n_weld = int(weld.max()) + 1
        graph = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n_weld, n_weld))
        _, welded_label = connected_components(graph, directed=False)
        label = welded_label[weld]
        moved_p = np.einsum('vij,vj->vi', blend[:, :3, :3], positions) + blend[:, :3, 3]
        tri_piece = label[triangles[:, 0]]

        def volume(points, faces):
            q = points - points[np.unique(faces)].mean(0)
            return float(np.einsum('ij,ij->i', q[faces[:, 0]], np.cross(q[faces[:, 1]], q[faces[:, 2]])).sum() / 6.0)

        for piece in np.unique(tri_piece):
            faces = triangles[tri_piece == piece]
            members = np.unique(faces)
            extent = positions[members].max(0) - positions[members].min(0)
            # small pieces move whole; so does any piece the blend would turn
            # inside out (a flat two-sided strip encloses almost nothing, and
            # the bend can carry that nothing through zero)
            before, after = volume(positions, faces), volume(moved_p, faces)
            if np.linalg.norm(extent) < RIGID_PIECE or (after < -1e-10 and after < before):
                mean = blend[members].mean(0)
                u, _, vt = np.linalg.svd(mean[:3, :3])
                mean[:3, :3] = u @ vt                # nearest rotation
                blend[members] = mean
    moved = np.isin(joints, idx).any(1) & (total > 0)
    p = positions.copy()
    p[moved] = np.einsum('vij,vj->vi', blend[moved, :3, :3], positions[moved]) + blend[moved, :3, 3]
    n = normals
    if normals is not None:
        n = normals.copy()
        r = np.einsum('vij,vj->vi', blend[moved, :3, :3], normals[moved])
        n[moved] = r / np.maximum(np.linalg.norm(r, axis=1, keepdims=True), 1e-12)
    t = tangents
    if tangents is not None:
        t = tangents.copy()
        r = np.einsum('vij,vj->vi', blend[moved, :3, :3], tangents[moved, :3])
        t[moved, :3] = r / np.maximum(np.linalg.norm(r, axis=1, keepdims=True), 1e-12)
    return p, n, t, int(moved.sum())


def append(d: dict, blob: bytearray, values: np.ndarray, atype: str, minmax: bool = False) -> int:
    while len(blob) % 4:
        blob.append(0)
    data = np.ascontiguousarray(values, '<f4').tobytes()
    d['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data), 'target': 34962})
    blob += data
    acc = {'bufferView': len(d['bufferViews']) - 1, 'componentType': 5126, 'count': int(len(values)), 'type': atype}
    if minmax:
        acc['min'] = [float(v) for v in values.min(0)]
        acc['max'] = [float(v) for v in values.max(0)]
    d['accessors'].append(acc)
    return len(d['accessors']) - 1


def bake(source: Path, out: Path, matrices: dict) -> dict:
    """Apply the leg pose to every skinned primitive of a GLB, sharing work over shared attribute sets."""
    d, blob = g.read(source)
    blob = bytearray(blob)
    done = {}
    moved_total = 0
    for node in d['nodes']:
        if 'mesh' not in node or 'skin' not in node:
            continue
        skin = d['skins'][node['skin']]
        names = [d['nodes'][j]['name'] for j in skin['joints']]
        for prim in d['meshes'][node['mesh']]['primitives']:
            a = prim['attributes']
            if 'JOINTS_0' not in a:
                continue
            key = (a['POSITION'], a.get('NORMAL'), a.get('TANGENT'), node['skin'])
            if key not in done:
                pos = g.accessor(d, bytes(blob), a['POSITION'])
                nor = g.accessor(d, bytes(blob), a['NORMAL']) if 'NORMAL' in a else None
                tan = g.accessor(d, bytes(blob), a['TANGENT']) if 'TANGENT' in a else None
                jnt = g.accessor(d, bytes(blob), a['JOINTS_0']).astype(int)
                wgt = g.accessor(d, bytes(blob), a['WEIGHTS_0'])
                # every primitive drawing from this attribute set, for its pieces
                tris = [g.accessor(d, bytes(blob), q['indices']).astype(int).reshape(-1, 3)
                        for m in d['meshes'] for q in m['primitives']
                        if q['attributes'].get('POSITION') == a['POSITION'] and 'indices' in q]
                p, n, t, moved = skin_attributes(pos, nor, tan, jnt, wgt, names, matrices,
                                                 np.concatenate(tris) if tris else None)
                moved_total += moved
                new = {'POSITION': append(d, blob, p, 'VEC3', minmax=True)}
                if n is not None:
                    new['NORMAL'] = append(d, blob, n, 'VEC3')
                if t is not None:
                    new['TANGENT'] = append(d, blob, t, 'VEC4')
                done[key] = new
            a.update(done[key])
    d.setdefault('asset', {}).setdefault('extras', {})['eloriaLegStance'] = {'version': 1}
    d, out_blob = g.compact(d, bytes(blob))
    out.parent.mkdir(parents=True, exist_ok=True)
    g.write(out, d, out_blob)
    return {'moved_vertices': moved_total}


def leg_points(d: dict, blob: bytes, side: str):
    """Rest positions, joints and weights of the body's skin-and-wardrobe vertices led by one leg."""
    skin = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    leg = [names.index(f'{n}_{side}') for n in CHAIN if f'{n}_{side}' in names]
    seen = set()
    rows = []
    for node in d['nodes']:
        if node.get('name') not in ('body', 'wardrobe_pants', 'wardrobe_boots') or 'mesh' not in node:
            continue
        for prim in d['meshes'][node['mesh']]['primitives']:
            a = prim['attributes']
            idx = np.unique(g.accessor(d, blob, prim['indices']).astype(int).reshape(-1))
            key = a['POSITION']
            pos = g.accessor(d, blob, a['POSITION'])[idx]
            jnt = g.accessor(d, blob, a['JOINTS_0']).astype(int)[idx]
            wgt = g.accessor(d, blob, a['WEIGHTS_0'])[idx]
            lead = jnt[np.arange(len(jnt)), wgt.argmax(1)]
            keep = np.isin(lead, leg)
            for i in np.flatnonzero(keep):
                k = (key, int(idx[i]))
                if k not in seen:
                    seen.add(k)
                    rows.append((pos[i], jnt[i], wgt[i]))
    return (np.array([r[0] for r in rows]), np.array([r[1] for r in rows]), np.array([r[2] for r in rows]), names)


def offsets(points: np.ndarray, rest: dict, side: str) -> np.ndarray:
    """Mesh centre minus bone line, in x, at each section height."""
    chain = [rest[f'{n}_{side}'][:3, 3] for n in ('thigh', 'calf', 'foot')]
    out = []
    for y in SECTIONS:
        band = points[np.abs(points[:, 1] - y) < 0.012]
        if len(band) < 8:
            out.append(0.0)
            continue
        centre = 0.5 * (band[:, 0].min() + band[:, 0].max())
        upper = y >= chain[1][1]
        a, b = (chain[0], chain[1]) if upper else (chain[1], chain[2])
        t = (y - a[1]) / (b[1] - a[1])
        out.append(centre - (a[0] + t * (b[0] - a[0])))
    return np.array(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('body', type=Path)
    ap.add_argument('out_body', type=Path)
    ap.add_argument('--garments', type=Path)
    ap.add_argument('--garments-out', type=Path)
    args = ap.parse_args()
    for path in (args.out_body, args.garments_out):
        if path is not None and 'godot-client' in path.resolve().parts:
            raise SystemExit('write to scratch; install the result separately')
    d, blob = g.read(args.body)
    rest = rest_globals(d, blob)
    angles, report = {}, {}
    for side in ('l', 'r'):
        pts, jnt, wgt, names = leg_points(d, blob, side)
        before = offsets(pts, rest, side)

        def cost(x, side=side, pts=pts, jnt=jnt, wgt=wgt, names=names):
            mats = pose(rest, {side: (x[0], x[1]), ('r' if side == 'l' else 'l'): (0.0, 0.0)})
            p, _, _, _ = skin_attributes(pts, None, None, jnt, wgt, names, mats)
            return float((offsets(p, rest, side) ** 2).sum())

        best = minimize(cost, np.zeros(2), method='Nelder-Mead', options={'xatol': 1e-5, 'fatol': 1e-10})
        angles[side] = (float(best.x[0]), float(best.x[1]))
        mats = pose(rest, {side: angles[side], ('r' if side == 'l' else 'l'): (0.0, 0.0)})
        p, _, _, _ = skin_attributes(pts, None, None, jnt, wgt, names, mats)
        report[side] = {'hip_deg': round(float(np.degrees(best.x[0])), 3), 'knee_deg': round(float(np.degrees(best.x[1])), 3),
                        'offset_before_mm': (before * 1000).round(1).tolist(),
                        'offset_after_mm': (offsets(p, rest, side) * 1000).round(1).tolist()}
    matrices = pose(rest, angles)
    report['body'] = bake(args.body, args.out_body, matrices)
    if args.garments:
        out_dir = args.garments_out
        count, moved = 0, 0
        for path in sorted(args.garments.glob('*.glb')):
            r = bake(path, out_dir / path.name, matrices)
            count += 1
            moved += int(r['moved_vertices'] > 0)
        report['garments'] = {'files': count, 'touched': moved}
    # record what was applied, so a garment fitted later can be moved the same way
    d2, blob2 = g.read(args.out_body)
    d2['asset']['extras']['eloriaLegStance'] = {'version': 1, 'sections': list(SECTIONS),
                                                 'anglesDeg': {s: [round(float(np.degrees(v)), 4) for v in angles[s]] for s in angles}}
    g.write(args.out_body, d2, blob2)
    print(json.dumps(report, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
