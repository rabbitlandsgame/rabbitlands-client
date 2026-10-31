"""Repair only the existing female shirt's collar weights and shoulder openings.

Inputs are explicit immutable GLBs. The body, skeleton, rest transforms, cloth
positions, UVs, normals and materials are never rebuilt. Output is separate.
Requires numpy, trimesh and shapely; these are authoring-only dependencies.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import LineString
from shapely.ops import polygonize, triangulate

import glbwriter
import rlglb


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_mesh(path, name):
    g, blob = rlglb.read(str(path))
    node = next(n for n in g['nodes'] if n.get('name') == name)
    mesh = g['meshes'][node['mesh']]
    skin = g['skins'][node['skin']]
    names = [g['nodes'][i]['name'] for i in skin['joints']]
    return g, blob, mesh, names


def attributes(g, blob, primitive):
    return {key: rlglb.accessor(g, blob, index)
            for key, index in primitive['attributes'].items()}


def dense_weights(attrs, count):
    result = np.zeros((len(attrs['POSITION']), count))
    assert 'JOINTS_1' not in attrs, 'This repair preserves the four-influence format'
    joints = attrs['JOINTS_0'].astype(int)
    for slot in range(4):
        np.add.at(result, (np.arange(len(result)), joints[:, slot]), attrs['WEIGHTS_0'][:, slot])
    return result


def mirror_names(names):
    def opposite(name):
        return name[:-2] + '_r' if name.endswith('_l') else name[:-2] + '_l' if name.endswith('_r') else name
    return np.array([names.index(opposite(name)) for name in names])


def shoulder_closures(g, blob, mesh):
    """Close only original small upper-shoulder boundary components.

    Some are thin slits at rest. They remain part of the boundary audit rather
    than being mistaken for UV splits, which position welding removes here.
    No vertex is moved or added; closure triangles use the existing records.
    """
    all_positions, all_triangles, offset = [], [], 0
    fabric = mesh['primitives'][0]
    fabric_positions = attributes(g, blob, fabric)['POSITION']
    for primitive in mesh['primitives']:
        positions = attributes(g, blob, primitive)['POSITION']
        triangles = rlglb.accessor(g, blob, primitive['indices']).astype(int).reshape(-1, 3)
        all_positions.append(positions)
        all_triangles.append(triangles + offset)
        offset += len(positions)
    positions = np.concatenate(all_positions)
    unique, inverse = np.unique(np.round(positions, 7), axis=0, return_inverse=True)
    triangles = inverse[np.concatenate(all_triangles)]
    edges = np.sort(triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    edges = edges[counts == 1]
    adjacent = {}
    for a, b in edges:
        adjacent.setdefault(int(a), set()).add(int(b))
        adjacent.setdefault(int(b), set()).add(int(a))
    seen, added, reports = set(), [], []
    fabric_normals = attributes(g, blob, fabric)['NORMAL']
    for start in adjacent:
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            vertex = stack.pop()
            if vertex in component:
                continue
            component.add(vertex)
            stack.extend(adjacent[vertex] - component)
        seen.update(component)
        ids = np.array(sorted(component))
        points = unique[ids]
        # These three bounded components are distinct from collar/cuffs/hem.
        if not (points[:, 1].min() > 1.30 and abs(points[:, 0]).min() > .14
                and abs(points[:, 0]).max() < .19):
            continue
        _, _, basis = np.linalg.svd(points - points.mean(0), full_matrices=False)
        projected = (unique - points.mean(0)) @ basis[:2].T
        segments = [(a, b) for a, b in edges if int(a) in component]
        polygons = list(polygonize([LineString([projected[a], projected[b]]) for a, b in segments]))
        before = len(added)
        for polygon in polygons:
            for triangle in triangulate(polygon):
                if not polygon.covers(triangle.representative_point()):
                    continue
                xy = np.array(triangle.exterior.coords)[:3]
                nearest = np.linalg.norm(xy[:, None] - projected[ids][None], axis=2).argmin(1)
                welded = ids[nearest]
                vertex_ids = []
                for vertex in welded:
                    distances = np.linalg.norm(fabric_positions - unique[vertex], axis=1)
                    index = int(distances.argmin())
                    assert distances[index] < 2e-7, 'Shoulder boundary must use an existing fabric vertex'
                    vertex_ids.append(index)
                p = fabric_positions[vertex_ids]
                normal = np.cross(p[1] - p[0], p[2] - p[0])
                if normal @ fabric_normals[vertex_ids].mean(0) < 0:
                    vertex_ids[1], vertex_ids[2] = vertex_ids[2], vertex_ids[1]
                added.append(vertex_ids)
        reports.append({'boundary_vertices': len(ids), 'closure_triangles': len(added) - before,
                        'bounds_min': points.min(0).tolist(), 'bounds_max': points.max(0).tolist()})
    assert len(reports) == 3, 'Unexpected shoulder topology; inspect a new source instead of broadening the mask'
    return np.array(added, dtype=int).reshape(-1, 3), reports


def repair(source, body, destination):
    g, blob, shirt, names = read_mesh(source, 'wardrobe_shirt')
    bg, bb, body_mesh, body_names = read_mesh(body, 'body')
    assert names == body_names, 'The canonical body and shirt must retain the same bind order'
    assert len(shirt['primitives']) == 2, 'Expected the previously repaired two-surface shirt'
    collar = shirt['primitives'][1]
    attrs = attributes(g, blob, collar)
    positions = attrs['POSITION']
    used = np.unique(rlglb.accessor(g, blob, collar['indices']).astype(int))
    angle = np.arctan2(positions[:, 0], positions[:, 2] + .030)
    height = 1.50 + .010 * np.sin(angle)**2 - .075 * np.maximum(np.cos(angle), 0)**4
    rim = np.intersect1d(np.flatnonzero(abs(positions[:, 1] - height) < 1e-5), used)
    assert len(rim) == 192, 'Expected the existing symmetric 192-vertex collar rim'
    original = dense_weights(attrs, len(names))
    bp = body_mesh['primitives'][0]
    ba = attributes(bg, bb, bp)
    bt = rlglb.accessor(bg, bb, bp['indices']).astype(int).reshape(-1, 3)
    body_weights = dense_weights(ba, len(names))
    surface = trimesh.Trimesh(ba['POSITION'], bt, process=False)
    sample = positions[rim].copy()
    radial = sample[:, [0, 2]] - np.array([0, -.030])
    radial /= np.linalg.norm(radial, axis=1)[:, None]
    sample[:, [0, 2]] -= radial * .002
    nearest, distance, triangles = trimesh.proximity.closest_point(surface, sample)
    barycentric = trimesh.triangles.points_to_barycentric(surface.triangles[triangles], nearest)
    target = np.einsum('vi,vij->vj', barycentric, body_weights[bt[triangles]])
    mirrored = positions[rim].copy()
    mirrored[:, 0] *= -1
    mirror_distance = np.linalg.norm(mirrored[:, None] - positions[rim][None], axis=2)
    pairs = mirror_distance.argmin(1)
    assert mirror_distance.min(1).max() < 1e-6
    swap = mirror_names(names)
    target = (target + target[pairs][:, swap]) * .5
    # Exactly four influences. Select one member of each mirrored pair, then
    # mirror its packed weights to the other side so equal-value ties cannot
    # silently select opposite anatomical meanings.
    dense = np.zeros_like(target)
    dropped = []
    for i in range(len(rim)):
        j = int(pairs[i])
        if j < i:
            continue
        keep = np.argsort(-target[i], kind='stable')[:4]
        if i == j:
            # Midline support must contain either both side binds or neither.
            if set(swap[keep]) != set(keep):
                candidates = [k for k in range(len(names)) if swap[k] == k]
                keep = np.array(sorted(candidates, key=lambda k: -target[i, k])[:4])
        dense[i, keep] = target[i, keep]
        dropped.append(float(1 - dense[i].sum()))
        dense[i] /= dense[i].sum()
        dense[j] = dense[i, swap]
    assert np.abs(dense - dense[pairs][:, swap]).max() < 1e-12
    joints, weights = attrs['JOINTS_0'].astype(int).copy(), attrs['WEIGHTS_0'].copy()
    for k, vertex in enumerate(rim):
        order = np.argsort(-dense[k], kind='stable')[:4]
        joints[vertex] = order
        weights[vertex] = dense[k, order]
    extra, closure_report = shoulder_closures(g, blob, shirt)
    writer = glbwriter.GLB()
    writer.g, writer.blob = copy.deepcopy(g), bytearray(blob)
    new_shirt = next(m for m in writer.g['meshes'] if m.get('name') == 'wardrobe_shirt')
    new_collar = new_shirt['primitives'][1]
    new_collar['attributes']['JOINTS_0'] = writer.accessor(joints, 'VEC4', comp=5121, target=34962)
    new_collar['attributes']['WEIGHTS_0'] = writer.accessor(weights, 'VEC4', target=34962)
    old_triangles = rlglb.accessor(g, blob, shirt['primitives'][0]['indices']).astype(int).reshape(-1, 3)
    new_shirt['primitives'][0]['indices'] = writer.accessor(np.concatenate([old_triangles, extra]).reshape(-1), 'SCALAR', comp=5125, target=34963)
    writer.save(str(destination))
    return {'source_sha256': sha(source), 'body_sha256': sha(body), 'output_sha256': sha(destination),
            'tool_sha256': sha(__file__), 'rim_vertices': len(rim), 'four_influence_max_discarded_weight': max(dropped),
            'rim_mirror_weight_max': float(np.abs(dense - dense[pairs][:, swap]).max()),
            'anatomical_sample_distance_max_mm': float(distance.max() * 1000),
            'shoulder_closures': closure_report, 'added_triangles': len(extra),
            'positions_normals_uvs_materials_morphs_skeleton_unchanged': True,
            'outside_rim_weights_unchanged': bool(np.array_equal(weights[np.setdiff1d(np.arange(len(weights)), rim)], attrs['WEIGHTS_0'][np.setdiff1d(np.arange(len(weights)), rim)]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-shirt', required=True, type=Path)
    parser.add_argument('--body', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    assert args.out.resolve() not in [args.source_shirt.resolve(), args.body.resolve()]
    assert not args.out.exists(), 'Use a new versioned output; retain prior takes'
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = repair(args.source_shirt, args.body, args.out)
    args.out.with_suffix('.repair.json').write_bytes((json.dumps(report, ensure_ascii=True, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
