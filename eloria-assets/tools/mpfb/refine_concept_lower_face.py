"""Static measured lower-face refinement over the reusable MPFB topology.

This changes only head POSITION/NORMAL arrays, retaining the canonical neck
seam, ears, eye openings, scalp, UVs, weights, rig and all other resources.
Inputs remain untouched. No additional geometry or runtime work is introduced.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import itertools

import numpy as np
from scipy.interpolate import PchipInterpolator

from match_neck_tone import Glb
from refine_concept_eyes import smooth, transform, world_matrices


PROFILES = {
    # Front reference estimates have +/-4px semantic uncertainty. These are
    # conservative authoring deltas, not an assertion of exact correspondence.
    'male': {'mouth_lift_m': .0100, 'chin_lift_m': .0155},
    'female': {'mouth_lift_m': .0065, 'chin_lift_m': .0145},
}


def field(points, frame, chin_y, profile, to_mesh):
    eye_y = float(frame['eye_y'])
    mouth_y = float(frame['mouth_y'])
    curve = PchipInterpolator(
        [chin_y - .070, chin_y - .032, chin_y, mouth_y, eye_y - .016, eye_y],
        [0., 0., profile['chin_lift_m'], profile['mouth_lift_m'], 0., 0.],
        extrapolate=False)
    lift = np.nan_to_num(curve(points[:, 1]), nan=0.)
    # Preserve the ears/rear skull and source neckline. Use canonical seam
    # distance as well as Head-local anatomy so face refinement cannot open it.
    front = smooth(float(frame['eye_z']) - .050, float(frame['eye_z']) - .020, points[:, 2])
    sides = 1. - smooth(.062, .083, abs(points[:, 0]))
    canonical = transform(points, to_mesh)
    neck = smooth(.018, .065, (canonical[:, 1] + .6 * canonical[:, 2] - 1.5) / np.sqrt(1.36))
    out = points.copy()
    out[:, 1] += lift * front * sides * neck
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--fit', required=True, type=Path)
    p.add_argument('--landmarks', required=True, type=Path)
    p.add_argument('--sex', required=True, choices=PROFILES)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--receipt', required=True, type=Path)
    a = p.parse_args()
    if a.input.resolve() == a.output.resolve(): raise ValueError('Preserve input stage')
    g = Glb(a.input)
    doc = copy.deepcopy(g.doc)
    binary = bytearray(g.binary)
    worlds = world_matrices(doc)
    hi = next(i for i, n in enumerate(doc['nodes']) if n.get('name') == 'Head')
    ni = next(i for i, n in enumerate(doc['nodes']) if n.get('name') == 'body')
    attrs = doc['meshes'][doc['nodes'][ni]['mesh']]['primitives'][0]['attributes']
    pi, no = attrs['POSITION'], attrs['NORMAL']
    to_head = np.linalg.inv(worlds[hi]) @ worlds[ni]
    from_head = np.linalg.inv(to_head)
    frame = json.loads(a.fit.read_text())['face_frame_head_local']
    chin_y = float(json.loads(a.landmarks.read_text())['models'][a.sex]['landmarks']['chin'][1])
    old = g.read(pi)
    points = transform(old, to_head)
    args = (frame, chin_y, PROFILES[a.sex], from_head)
    result = field(points, *args)
    step = 1e-5
    jac = np.stack([(field(points + np.eye(3)[k] * step, *args) - field(points - np.eye(3)[k] * step, *args)) / (2 * step) for k in range(3)], axis=2)
    det = np.linalg.det(jac)
    if det.min() < .35: raise ValueError(f'Lower-face field collapses: {det.min()}')
    pos = transform(result, from_head).astype('<f4')
    authored_normals = g.read(no)
    normal = authored_normals @ np.linalg.inv(to_head[:3, :3])
    normal = np.linalg.solve(jac.transpose(0, 2, 1), normal[..., None])[:, :, 0]
    normal = normal @ to_head[:3, :3]
    normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-12)
    normal = normal.astype('<f4')
    pinned = (old[:, 1] + .6 * old[:, 2] - 1.5) / np.sqrt(1.36) <= .018
    normal[pinned] = authored_normals[pinned]
    for index, values in [(pi, pos), (no, normal)]:
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        if view.get('byteStride'): raise ValueError('Expected packed authoring arrays')
        start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        binary[start:start + values.nbytes] = values.tobytes()
        if 'min' in accessor or index == pi:
            accessor['min'] = values.min(0).tolist()
            accessor['max'] = values.max(0).tolist()
    encoded = json.dumps(doc, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += b'\0' * (-len(binary) % 4)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary)) + struct.pack('<I4s', len(encoded), b'JSON') + encoded + struct.pack('<I4s', len(binary), b'BIN\0') + binary)
    check = Glb(a.output)
    other_exact = all(np.array_equal(g.read(i), check.read(i)) for i in range(len(doc['accessors'])) if i not in [pi, no])
    assert other_exact
    assert np.array_equal(pos[pinned], old[pinned])
    assert np.array_equal(check.read(no)[pinned], authored_normals[pinned])
    metadata = json.loads(a.fit.read_text())
    updated_frame = metadata['face_frame_head_local']
    mouth = np.array(updated_frame['mouth'], dtype=float)
    shifted_mouth = field(mouth[None, :], *args)[0]
    updated_frame['mouth'] = shifted_mouth.tolist()
    updated_frame['mouth_y'] = float(shifted_mouth[1])
    if 'mouth_bounds' in updated_frame:
        lo, hi = np.array(updated_frame['mouth_bounds'])
        corners = np.array(list(itertools.product(*zip(lo, hi))))
        moved_corners = field(corners, *args)
        updated_frame['mouth_bounds'] = [moved_corners.min(0).tolist(), moved_corners.max(0).tolist()]
    metadata['head_bounds'] = [pos.min(0).tolist(), pos.max(0).tolist()]
    metadata['output_sha256'] = hashlib.sha256(a.output.read_bytes()).hexdigest()
    metadata['lower_face_profile'] = PROFILES[a.sex]
    (a.output.parent / 'fit.json').write_text(json.dumps(metadata, indent=2) + '\n')
    report = {'sex': a.sex, 'profile': PROFILES[a.sex], 'changed_accessors': [pi, no],
        'source_sha256': hashlib.sha256(a.input.read_bytes()).hexdigest(),
        'output_sha256': hashlib.sha256(a.output.read_bytes()).hexdigest(),
        'all_other_accessors_exact': other_exact, 'canonical_seam_band_exact': True,
        'canonical_seam_normals_exact': True,
        'minimum_jacobian_determinant': float(det.min()),
        'moved_vertices': int(np.sum(np.linalg.norm(pos - old, axis=1) > 1e-7)),
        'max_displacement_m': float(np.linalg.norm(pos - old, axis=1).max()),
        'added_geometry_maps_runtime_work': 0}
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__': main()
