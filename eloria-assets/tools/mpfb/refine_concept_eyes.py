"""Widen authored eye openings with their lids/sclera in Head rest space.

The bounded static field preserves the midline, skull, mouth, ears, neck,
canonical body, rig, weights and animation. It adds no vertices or runtime work.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from scipy.spatial.transform import Rotation
from match_neck_tone import Glb


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0., 1.)
    return t * t * (3. - 2. * t)


def world_matrices(doc):
    parents = {c: i for i, n in enumerate(doc['nodes']) for c in n.get('children', [])}
    cache = {}
    def world(i):
        if i in cache: return cache[i]
        n = doc['nodes'][i]
        if 'matrix' in n:
            m = np.array(n['matrix']).reshape(4, 4).T
        else:
            m = np.eye(4)
            m[:3, :3] = Rotation.from_quat(n.get('rotation', [0, 0, 0, 1])).as_matrix() @ np.diag(n.get('scale', [1, 1, 1]))
            m[:3, 3] = n.get('translation', [0, 0, 0])
        cache[i] = world(parents[i]) @ m if i in parents else m
        return cache[i]
    return [world(i) for i in range(len(doc['nodes']))]


def transform(points, matrix):
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def warp(points, centers, factor):
    out = points.copy()
    center = np.where((points[:, 0] >= 0)[:, None], centers[1], centers[0])
    dx = points[:, 0] - center[:, 0]
    dy = points[:, 1] - center[:, 1]
    window = (1. - smooth(.018, .050, np.abs(dx))) * (1. - smooth(.013, .029, np.abs(dy)))
    window *= smooth(.001, .020, np.abs(points[:, 0]))
    window *= smooth(center[:, 2] - .045, center[:, 2] - .015, points[:, 2])
    out[:, 0] += dx * (factor - 1.) * window
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--fit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--factor', type=float, default=1.30)
    a = p.parse_args()
    if a.input.resolve() == a.output.resolve(): raise ValueError('Preserve source stage')
    g = Glb(a.input)
    doc = copy.deepcopy(g.doc)
    binary = bytearray(g.binary)
    worlds = world_matrices(doc)
    head = worlds[next(i for i, n in enumerate(doc['nodes']) if n.get('name') == 'Head')]
    frame = json.loads(a.fit.read_text())['face_frame_head_local']
    centers = np.array(sorted([frame['eye_left'], frame['eye_right']], key=lambda v: v[0]))
    changes = {}
    allowed = set()
    for name in ['body', 'eyes']:
        ni = next(i for i, n in enumerate(doc['nodes']) if n.get('name') == name)
        attrs = doc['meshes'][doc['nodes'][ni]['mesh']]['primitives'][0]['attributes']
        pi, no = attrs['POSITION'], attrs['NORMAL']
        old = g.read(pi)
        to_head = np.linalg.inv(head) @ worlds[ni]
        local = transform(old, to_head)
        result = warp(local, centers, a.factor)
        step = 1e-5
        jac = np.stack([(warp(local + np.eye(3)[k] * step, centers, a.factor) - warp(local - np.eye(3)[k] * step, centers, a.factor)) / (2 * step) for k in range(3)], axis=2)
        det = np.linalg.det(jac)
        if det.min() < .15: raise ValueError(f'Non-positive or collapsed eye field: {det.min()}')
        pos = transform(result, np.linalg.inv(to_head)).astype('<f4')
        normal = g.read(no) @ np.linalg.inv(to_head[:3, :3])
        normal = np.linalg.solve(jac.transpose(0, 2, 1), normal[..., None])[:, :, 0]
        normal = normal @ to_head[:3, :3]
        normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-12)
        for index, values in [(pi, pos), (no, normal.astype('<f4'))]:
            accessor = doc['accessors'][index]
            view = doc['bufferViews'][accessor['bufferView']]
            if view.get('byteStride'): raise ValueError('Expected packed authoring arrays')
            start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
            data = values.tobytes()
            binary[start:start + len(data)] = data
            if 'min' in accessor or index == pi:
                accessor['min'] = values.min(0).tolist()
                accessor['max'] = values.max(0).tolist()
            allowed.add(index)
        changes[name] = {'moved_vertices': int(np.sum(np.linalg.norm(pos - old, axis=1) > 1e-7)),
            'max_displacement_m': float(np.linalg.norm(pos - old, axis=1).max()),
            'minimum_field_jacobian_determinant': float(det.min())}
    js = json.dumps(doc, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    binary += b'\0' * (-len(binary) % 4)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(struct.pack('<4sII', b'glTF', 2, 28 + len(js) + len(binary)) + struct.pack('<I4s', len(js), b'JSON') + js + struct.pack('<I4s', len(binary), b'BIN\0') + binary)
    check = Glb(a.output)
    assert all(np.array_equal(g.read(i), check.read(i)) for i in range(len(doc['accessors'])) if i not in allowed)
    report = {'factor': a.factor, 'changed_accessors': sorted(allowed), 'all_other_accessors_exact': True,
        'source_sha256': hashlib.sha256(a.input.read_bytes()).hexdigest(),
        'output_sha256': hashlib.sha256(a.output.read_bytes()).hexdigest(), 'parts': changes,
        'added_geometry_materials_maps_runtime_work': 0, 'scope': 'Static width-only eye opening, coherent lids/sclera; protects central nose, skull, ears, mouth and neck.'}
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps(report))


if __name__ == '__main__': main()
