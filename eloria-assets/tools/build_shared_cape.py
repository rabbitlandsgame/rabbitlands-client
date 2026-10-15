"""Build the shared cape GLB (2026-10-05) from a Blender mesh dump on the canonical rig.

    python eloria-assets/tools/build_shared_cape.py <cape_mesh.npz> <texture.jpg> <out.glb>
        [--normal cape_normal.png] [--template godot-client/assets/actors/native/equipment/generic_cape.glb]

Every cape item renders one mesh: `generic_cape.glb`, dyed per item by the
equipment registry's `tint` ([base, trim, detail] sRGB bytes, matched to the
material-name suffixes "Base", "Trim", "Detail").  The 2026-10-05 cape replaces
the builder's flat sheet with a sculpted one (concept art -> Meshy -> fitted in
Blender behind the canonical body, collar cut to a back arc, cleared to the
old cape's armour-safe inner line, bound to spine_03 and the twelve cape_*
chains with equipment_authoring.cape_weights' scheme).

Input `cape_mesh.npz` is what the Blender session dumps: rest positions in
the armature's Blender space (z up, -y forward), loop UVs, triangles with
material index 0/1/2 (cloth / woven trim / inner lining) and split normals,
and up to four (group name, weight) pairs per vertex.  The template supplies
the skeleton nodes, joint order and inverse binds, so the cape carries the
same 77-joint skin as every other cape.  The single greyscale texture is
shared by the three materials; the tint colours each.  So is the normal map,
derived from that texture's own relief by shared_cape/cape_normal.py.
"""
from __future__ import annotations

import argparse
import copy
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies' / 'vendor'))
import glbkit as g  # noqa: E402

MATERIALS = (('Cape Base', 0.9, 0.0), ('Cape Trim', 0.7, 0.04), ('Cape Detail', 0.9, 0.0))


def build(dump: Path, texture: Path, out: Path, template: Path, normal: Path | None = None) -> dict:
    d = np.load(dump)
    co, uv = d['co'], d['uv']
    tri_mat, tri_v, tri_l, tri_n = d['tri_mat'], d['tri_v'], d['tri_l'], d['tri_n']
    jw, ww, names = d['jw'], d['ww'], [str(n) for n in d['names']]
    gltf, blob = g.read(template)
    gltf = copy.deepcopy(gltf)
    joint_names = [gltf['nodes'][j]['name'] for j in gltf['skins'][0]['joints']]
    remap = np.array([joint_names.index(n) for n in names], np.int32)
    to_gltf = lambda p: np.stack([p[..., 0], p[..., 2], -p[..., 1]], -1)  # noqa: E731
    binary = bytearray()

    def add(array, ctype, atype, target=None, minmax=False):
        nonlocal binary
        while len(binary) % 4:
            binary.append(0)
        data = np.ascontiguousarray(array).tobytes()
        view = {'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data)}
        if target:
            view['target'] = target
        binary += data
        views.append(view)
        acc = {'bufferView': len(views) - 1, 'componentType': ctype, 'count': int(len(array)), 'type': atype}
        if minmax:
            acc['min'] = [float(x) for x in array.min(0)]
            acc['max'] = [float(x) for x in array.max(0)]
        accessors.append(acc)
        return len(accessors) - 1

    views, accessors = [], []
    # Smooth normals from the geometry itself, shared by every split copy of a
    # vertex: the split normals a decimated Meshy mesh carries are torn into
    # dark facets once the engine lights them.
    _, weld = np.unique(np.round(co, 5), axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    lining = tri_mat == 2

    def smooth_normals(tris, layer):
        # one layer of the shell at a time: where the cloth and its lining
        # share a border vertex, their normals point opposite ways and summed
        # together they cancel into noise
        corners = co[tris]
        face = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        summed = np.zeros_like(co)
        for k in range(3):
            np.add.at(summed, tris[layer, k], face[layer])
        welded = np.zeros((weld.max() + 1, 3))
        np.add.at(welded, weld, summed)
        normals = welded[weld]
        return face, normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    # A triangle in a tight fold faces against the smooth normal its corners
    # carry. The cloth is double-sided, and Godot shades a back face with its
    # normal turned round, so seen from behind such a triangle is lit from
    # inside the cape: a dark slit across the cloth. Wind every cloth and trim
    # triangle to face the way its corners' shading normal does (twice:
    # turning a fold round also steadies the normals it shares with its
    # neighbours).
    tri_v = tri_v.copy(); tri_l = tri_l.copy()
    against = np.zeros(len(tri_v), bool)
    for _ in range(2):
        face_n, outer_n = smooth_normals(tri_v, ~lining)
        turn = ~lining & ((face_n * outer_n[tri_v].sum(1)).sum(1) < 0)
        tri_v[turn] = tri_v[turn][:, ::-1]
        tri_l[turn] = tri_l[turn][:, ::-1]
        against ^= turn
    # The lining is single-sided and faces the body (Blender space: the trunk
    # is the z axis, the cape hangs at +y). Swung back by the cloth solver over
    # a bulky torso, the coarse inner face of this thin shell cuts through the
    # outer one in places; facing the body, it is culled wherever it does, and
    # it is only ever seen from between the cape and the back.
    face_n, _ = smooth_normals(tri_v, ~lining)
    centre = co[tri_v].mean(1)
    inward = -np.stack([centre[:, 0], centre[:, 1], np.zeros(len(centre))], 1)
    turn = lining & ((face_n * inward).sum(1) < 0)
    tri_v[turn] = tri_v[turn][:, ::-1]
    tri_l[turn] = tri_l[turn][:, ::-1]
    face_n, outer_n = smooth_normals(tri_v, ~lining)
    _, lining_n = smooth_normals(tri_v, lining)
    # Keep the template's inverse binds byte for byte.
    ibm = g.accessor(gltf, blob, gltf['skins'][0]['inverseBindMatrices']).astype('<f4')
    ibm_index = add(ibm, 5126, 'MAT4')
    prims = []
    counts = {}
    for m in range(3):
        sel = np.flatnonzero(tri_mat == m)
        keys = {}
        pos, nrm, tex, jnt, wgt, idx = [], [], [], [], [], []
        for t in sel:
            for k in range(3):
                v, l = int(tri_v[t, k]), int(tri_l[t, k])
                n = lining_n[v] if m == 2 else outer_n[v]
                key = (v, round(float(uv[l, 0]), 6), round(float(uv[l, 1]), 6))
                if key not in keys:
                    keys[key] = len(pos)
                    pos.append(co[v]); nrm.append(n); tex.append((uv[l, 0], 1.0 - uv[l, 1]))
                    jnt.append(remap[jw[v]]); wgt.append(ww[v])
                idx.append(keys[key])
        pos = to_gltf(np.array(pos, np.float32)).astype('<f4')
        nrm = to_gltf(np.array(nrm, np.float32))
        nrm = (nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)).astype('<f4')
        attributes = {
            'POSITION': add(pos, 5126, 'VEC3', 34962, True),
            'NORMAL': add(nrm, 5126, 'VEC3', 34962),
            'TEXCOORD_0': add(np.array(tex, '<f4'), 5126, 'VEC2', 34962),
            'JOINTS_0': add(np.array(jnt, '<u2'), 5123, 'VEC4', 34962),
            'WEIGHTS_0': add(np.array(wgt, '<f4'), 5126, 'VEC4', 34962),
        }
        prims.append({'attributes': attributes, 'indices': add(np.array(idx, '<u4'), 5125, 'SCALAR', 34963),
                      'material': m})
        counts[MATERIALS[m][0]] = {'vertices': len(pos), 'triangles': len(sel)}
    gltf['images'], gltf['textures'] = [], []
    for name, mime, path in (('cape_cloth', 'image/jpeg', texture), ('cape_normal', 'image/png', normal)):
        if path is None:
            continue
        image = path.read_bytes()
        while len(binary) % 4:
            binary.append(0)
        views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(image)})
        binary += image
        gltf['images'].append({'name': name, 'mimeType': mime, 'bufferView': len(views) - 1})
        gltf['textures'].append({'source': len(gltf['images']) - 1})
    gltf.pop('samplers', None)
    gltf['materials'] = [{'name': name, 'doubleSided': name != 'Cape Detail',
                          'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': metal,
                                                   'roughnessFactor': rough, 'baseColorTexture': {'index': 0}}}
                         for name, rough, metal in MATERIALS]
    if normal is not None:
        # one relief map (shared_cape/cape_normal.py) under all three tint slots
        for material in gltf['materials']:
            material['normalTexture'] = {'index': 1}
    mesh_node = next(n for n in gltf['nodes'] if 'mesh' in n)
    gltf['meshes'] = [{'name': 'Cape', 'primitives': prims}]
    mesh_node['mesh'] = 0
    gltf['skins'][0]['inverseBindMatrices'] = ibm_index
    gltf['accessors'] = accessors
    gltf['bufferViews'] = views
    gltf['buffers'] = [{'byteLength': len(binary)}]
    gltf.pop('animations', None)
    gltf['asset'] = {'version': '2.0', 'generator': 'Eloria build_shared_cape',
                     'extras': {'eloriaSharedCape': {'version': 1, 'tintSlots': ['Base', 'Trim', 'Detail']}}}
    out.parent.mkdir(parents=True, exist_ok=True)
    g.write(out, gltf, bytes(binary))
    return {'out': str(out), 'bytes': out.stat().st_size, 'primitives': counts, 'rewound': int(against.sum())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dump', type=Path)
    ap.add_argument('texture', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--template', type=Path, default=Path(__file__).resolve().parents[2] /
                    'godot-client/assets/actors/native/equipment/generic_cape.glb')
    ap.add_argument('--normal', type=Path, help='tangent-space normal map PNG (shared_cape/cape_normal.py)')
    args = ap.parse_args()
    print(json.dumps(build(args.dump, args.texture, args.out, args.template, args.normal), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
