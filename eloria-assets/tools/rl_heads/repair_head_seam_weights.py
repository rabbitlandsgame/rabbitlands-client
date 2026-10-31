"""Restore canonical body weights on an existing RL head's patch and shared rim.

This processes the supplied immutable GLBs. It does not build a head, change
geometry/morphs, or touch fitter inputs. Existing binary bytes are retained as
a prefix; new skin packets and inverse binds are appended. Four influences are
kept, with any interior interpolation approximation measured separately.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import struct
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'hair'))
import rlglb

CORE = ['spine_03', 'neck_01', 'Head']
ADDED = ['clavicle_l', 'clavicle_r']
SKIN_ATTRS = {'JOINTS_0', 'WEIGHTS_0', 'JOINTS_1', 'WEIGHTS_1'}
COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
        5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attributes(g, blob, primitive):
    return {k: rlglb.accessor(g, blob, v, normalize=False)
            for k, v in primitive['attributes'].items()}


def dense_weights(attrs, count):
    result = np.zeros((len(attrs['POSITION']), count))
    for suffix in ['0', '1']:
        if 'JOINTS_' + suffix not in attrs:
            continue
        for slot in range(4):
            np.add.at(result, (np.arange(len(result)), attrs['JOINTS_' + suffix][:, slot].astype(int)),
                      attrs['WEIGHTS_' + suffix][:, slot])
    return result


def primitive_by_material(g, mesh, material):
    return next(p for p in mesh['primitives'] if g['materials'][p['material']]['name'] == material)


def canonical_patch(P, UV, old, body_P, body_UV, triangles, body_W, names):
    """Resolve exact source vertices first, then P+UV-consistent triangle barycentrics."""
    A, B, C = (body_P[triangles[:, k]] for k in range(3))
    e0, e1 = B - A, C - A
    d00 = np.einsum('ij,ij->i', e0, e0)
    d01 = np.einsum('ij,ij->i', e0, e1)
    d11 = np.einsum('ij,ij->i', e1, e1)
    den = d00 * d11 - d01 * d01
    result, records = [], []
    for i, (point, uv) in enumerate(zip(P, UV)):
        hits = np.flatnonzero((np.linalg.norm(body_P - point, axis=1) < 1e-6)
                              & (np.linalg.norm(body_UV - uv, axis=1) < 1e-6))
        if len(hits):
            folded = np.zeros((len(hits), 3))
            folded[:, 1] = body_W[hits, names.index('neck_01')]
            folded[:, 2] = body_W[hits, names.index('Head')]
            folded[:, 0] = body_W[hits].sum(1) - folded[:, 1] - folded[:, 2]
            hit = hits[np.argmin(np.abs(folded - old[i]).sum(1))]
            result.append(body_W[hit])
            records.append({'kind': 'vertex', 'body_vertex': int(hit),
                            'position_error_m': float(np.linalg.norm(body_P[hit] - point)),
                            'uv_error': float(np.linalg.norm(body_UV[hit] - uv))})
            continue
        v = point - A
        d20, d21 = np.einsum('ij,ij->i', v, e0), np.einsum('ij,ij->i', v, e1)
        with np.errstate(divide='ignore', invalid='ignore'):
            q, r = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
        bary = np.c_[1 - q - r, q, r]
        cp = np.einsum('ij,ijk->ik', bary, body_P[triangles])
        cuv = np.einsum('ij,ijk->ik', bary, body_UV[triangles])
        dp, du = np.linalg.norm(cp - point, axis=1), np.linalg.norm(cuv - uv, axis=1)
        valid = (bary.min(1) > -1e-5) & (dp < 2e-6) & (du < 2e-6) & (den > 1e-18)
        hits = np.flatnonzero(valid)
        if not len(hits):
            raise ValueError(f'patch vertex {i}: no canonical POSITION+UV triangle')
        hit = hits[np.argmin(dp[hits] + du[hits])]
        bc = np.maximum(bary[hit], 0)
        bc /= bc.sum()
        result.append(bc @ body_W[triangles[hit]])
        records.append({'kind': 'triangle', 'body_triangle': int(hit), 'barycentric': bc.tolist(),
                        'position_error_m': float(dp[hit]), 'uv_error': float(du[hit])})
    return np.array(result), records


def four_packets(full, mapping, body_names, skin_names):
    packets_J = np.zeros((len(full), 4), np.uint8)
    packets_W = np.zeros((len(full), 4), np.float32)
    lost = []
    for i, weights in enumerate(full):
        ids = np.argsort(-weights, kind='stable')[:4]
        keep = weights[ids].copy()
        lost.append(float(weights.sum() - keep.sum()))
        # An existing canonical body vertex must retain its exact float32 weights.
        # Only newly interpolated cut points may need a four-weight approximation.
        if mapping[i]['kind'] == 'vertex':
            if np.count_nonzero(weights > 0) > 4 or abs(lost[-1]) > 1e-8:
                raise ValueError(f'canonical vertex {i} needs more than four weights; exact retention is unsupported')
        else:
            keep /= keep.sum()
        for k, (body_joint, weight) in enumerate(zip(ids, keep)):
            if weight > 0:
                packets_J[i, k] = skin_names.index(body_names[body_joint])
                packets_W[i, k] = weight
    return packets_J, packets_W, lost


def add_accessor(g, blob, array, template, target=None):
    while len(blob) % 4:
        blob.append(0)
    data = np.ascontiguousarray(array, dtype=COMP[template['componentType']]).tobytes()
    view = {'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data)}
    if target is not None:
        view['target'] = target
    blob.extend(data)
    g['bufferViews'].append(view)
    acc = {k: copy.deepcopy(v) for k, v in template.items()
           if k not in ['bufferView', 'byteOffset', 'sparse']}
    acc['bufferView'] = len(g['bufferViews']) - 1
    acc['count'] = len(array)
    g['accessors'].append(acc)
    return len(g['accessors']) - 1


def raw_accessor(g, blob, index):
    a = g['accessors'][index]
    meta = {k: v for k, v in a.items() if k not in ['bufferView', 'byteOffset', 'sparse']}
    size = np.dtype(COMP[a['componentType']]).itemsize * NCOMP[a['type']]
    data = bytearray()
    if 'bufferView' in a:
        view = g['bufferViews'][a['bufferView']]
        start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = view.get('byteStride', size)
        for row in range(a['count']):
            data.extend(blob[start + row * stride:start + row * stride + size])
    sparse = a.get('sparse')
    extra = []
    if sparse:
        meta['sparse'] = {'count': sparse['count'], 'indexComponentType': sparse['indices']['componentType']}
        for key, width in [('indices', np.dtype(COMP[sparse['indices']['componentType']]).itemsize), ('values', size)]:
            part = sparse[key]
            view = g['bufferViews'][part['bufferView']]
            start = view.get('byteOffset', 0) + part.get('byteOffset', 0)
            extra.append(bytes(blob[start:start + sparse['count'] * width]))
    return meta, bytes(data), extra


def invariant(g, blob, masks, source_nodes):
    """Independent Python proof; the focused Godot helper recomputes its own digest."""
    h = hashlib.sha256()
    def feed(label, value):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()
        h.update(f'{len(label)}:{label}:{len(data)}:'.encode()); h.update(data)
    def acc(label, index, excluded=()):
        meta, data, sparse = raw_accessor(g, blob, index)
        feed(label + '.meta', meta)
        if excluded:
            a = g['accessors'][index]
            stride = np.dtype(COMP[a['componentType']]).itemsize * NCOMP[a['type']]
            skip = set(excluded)
            data = b''.join(data[i * stride:(i + 1) * stride] for i in range(a['count']) if i not in skip)
        feed(label + '.data', data)
        for i, extra in enumerate(sparse):feed(label + '.sparse' + str(i), extra)
    asset = copy.deepcopy(g['asset']); asset.get('extras', {}).get('rlHead', {}).pop('skinRepair', None)
    feed('asset', asset);feed('materials', g.get('materials', []));feed('textures', g.get('textures', []));feed('samplers', g.get('samplers', []))
    feed('scenes', g.get('scenes', []));feed('scene', g.get('scene', 0));feed('masks', masks)
    for i, node in enumerate(g['nodes'][:source_nodes]):
        nd = copy.deepcopy(node)
        if 'children' in nd:nd['children'] = [c for c in nd['children'] if c < source_nodes]
        feed('node' + str(i), nd)
    skin = g['skins'][0]
    feed('skin.prefix', [g['nodes'][j]['name'] for j in skin['joints'][:3]])
    feed('skin.metadata', {k: v for k, v in skin.items() if k not in ['joints', 'inverseBindMatrices']})
    feed('skin.ibm3', rlglb.accessor(g, blob, skin['inverseBindMatrices'], normalize=False)[:3].astype('<f4').tobytes())
    for mi, mesh in enumerate(g['meshes']):
        feed(f'mesh{mi}.metadata', {k: v for k, v in mesh.items() if k != 'primitives'})
        for pi, prim in enumerate(mesh['primitives']):
            label = f'mesh{mi}.prim{pi}'
            feed(label + '.metadata', {k: v for k, v in prim.items() if k not in ['attributes', 'targets', 'indices']})
            feed(label + '.attributes', sorted(prim['attributes']))
            for key, index in sorted(prim['attributes'].items()):
                excluded = masks.get(f'{mi}:{pi}', []) if key in SKIN_ATTRS else []
                acc(label + '.' + key, index, excluded)
            if 'indices' in prim:acc(label + '.indices', prim['indices'])
            feed(label + '.targetCount', len(prim.get('targets', [])))
            for ti, target in enumerate(prim.get('targets', [])):
                feed(label + f'.target{ti}.attributes', sorted(target))
                for key, index in sorted(target.items()):acc(label + f'.target{ti}.' + key, index)
    for i, image in enumerate(g.get('images', [])):
        feed('image' + str(i), {k: v for k, v in image.items() if k != 'bufferView'})
        if 'bufferView' in image:
            view = g['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            feed('imageBytes' + str(i), bytes(blob[start:start + view['byteLength']]))
        elif 'uri' in image:
            raise ValueError('External image input requires an explicit frozen dependency; not supported by this head-only repair')
    return h.hexdigest()


def repair(head_path, body_path, output, report_path):
    head_path, body_path, output, report_path = map(Path, [head_path, body_path, output, report_path])
    inputs = {head_path.resolve(), body_path.resolve()}
    if output.resolve() in inputs or report_path.resolve() in inputs:
        raise ValueError('Output and report must not overwrite an immutable input')
    if output.resolve() == report_path.resolve():
        raise ValueError('Output and report must use distinct paths')
    if output.exists() or report_path.exists():
        raise ValueError('Output or report already exists; preserve every previous take')
    source, old_blob = rlglb.read(head_path)
    body, body_blob = rlglb.read(body_path)
    g, blob = copy.deepcopy(source), bytearray(old_blob)
    skin = g['skins'][0]
    names = [g['nodes'][i]['name'] for i in skin['joints']]
    assert names == CORE
    body_skin = body['skins'][0]
    body_names = [body['nodes'][i]['name'] for i in body_skin['joints']]
    body_node = next(n for n in body['nodes'] if n.get('name') == 'body')
    body_prim = body['meshes'][body_node['mesh']]['primitives'][0]
    ba = attributes(body, body_blob, body_prim)
    BW = dense_weights(ba, len(body_names))
    BT = rlglb.accessor(body, body_blob, body_prim['indices'], normalize=False).astype(int).reshape(-1, 3)
    patch = primitive_by_material(source, source['meshes'][0], 'rl_bodypatch')
    pa = attributes(source, old_blob, patch)
    PW = dense_weights(pa, 3)
    full, mapping = canonical_patch(pa['POSITION'], pa['TEXCOORD_0'], PW, ba['POSITION'], ba['TEXCOORD_0'], BT, BW, body_names)
    required = [body_names[i] for i in np.flatnonzero(full.max(0) > 1e-9) if body_names[i] not in CORE]
    assert set(required) == set(ADDED)
    new_names = CORE + ADDED
    J4, W4, dropped = four_packets(full, mapping, body_names, new_names)
    canonical_ibm = rlglb.accessor(body, body_blob, body_skin['inverseBindMatrices'], normalize=False)
    original_ibm = rlglb.accessor(source, old_blob, source['skins'][0]['inverseBindMatrices'], normalize=False)
    assert np.array_equal(original_ibm, canonical_ibm[[body_names.index(n) for n in CORE]])
    spine = skin['joints'][0]
    parent = {c: i for i, n in enumerate(body['nodes']) for c in n.get('children', [])}
    for name in ADDED:
        ni = body_skin['joints'][body_names.index(name)]
        assert body['nodes'][parent[ni]]['name'] == 'spine_03'
        node = {k: copy.deepcopy(v) for k, v in body['nodes'][ni].items() if k != 'children'}
        skin['joints'].append(len(g['nodes']))
        g['nodes'][spine].setdefault('children', []).append(len(g['nodes']))
        g['nodes'].append(node)
    ibms = np.concatenate([original_ibm, canonical_ibm[[body_names.index(n) for n in ADDED]]])
    template = source['accessors'][source['skins'][0]['inverseBindMatrices']]
    skin['inverseBindMatrices'] = add_accessor(g, blob, ibms, template)
    masks, touched = {}, []
    for mi, mesh in enumerate(g['meshes']):
        for pi, prim in enumerate(mesh['primitives']):
            material = g['materials'][prim['material']]['name']
            if material not in ['rl_bodypatch', 'rl_skin']:continue
            original = source['meshes'][mi]['primitives'][pi]
            a = attributes(source, old_blob, original)
            if material == 'rl_bodypatch':
                assert np.array_equal(a['POSITION'], pa['POSITION']) and np.array_equal(a['TEXCOORD_0'], pa['TEXCOORD_0'])
                ids, near = np.arange(len(a['POSITION'])), np.arange(len(pa['POSITION']))
            else:
                distance = np.linalg.norm(a['POSITION'][:, None] - pa['POSITION'][None], axis=2)
                near = distance.argmin(1)
                ids = np.flatnonzero(distance.min(1) < 1e-6)
                near = near[ids]
            for target in original.get('targets', []):
                assert np.abs(rlglb.accessor(source, old_blob, target['POSITION'])[ids]).max() == 0
            j, w = a['JOINTS_0'].copy(), a['WEIGHTS_0'].copy()
            j[ids], w[ids] = J4[near], W4[near]
            outside = np.ones(len(j), bool);outside[ids] = False
            assert np.array_equal(j[outside], a['JOINTS_0'][outside]) and np.array_equal(w[outside], a['WEIGHTS_0'][outside])
            for key, array in [('JOINTS_0', j), ('WEIGHTS_0', w)]:
                prim['attributes'][key] = add_accessor(g, blob, array, source['accessors'][original['attributes'][key]], 34962)
            masks[f'{mi}:{pi}'] = ids.tolist()
            touched.append({'mesh': mesh['name'], 'primitive': pi, 'material': material, 'vertices': len(ids), 'mask': ids.tolist(), 'patch_rows': near.tolist()})
    invariant_before = invariant(source, old_blob, masks, len(source['nodes']))
    invariant_after = invariant(g, blob, masks, len(source['nodes']))
    assert invariant_before == invariant_after
    repair_meta = {'version': 1, 'sourceHeadSHA256': sha(head_path), 'canonicalBodySHA256': sha(body_path),
                   'tool': 'repair_head_seam_weights.py', 'firstThreeJointsPreserved': CORE,
                   'appendedJoints': ADDED, 'fourInfluences': True}
    g['asset']['extras']['rlHead']['skinRepair'] = repair_meta
    g['buffers'][0]['byteLength'] = len(blob)
    text = json.dumps(g, ensure_ascii=True, separators=(',', ':')).encode()
    text += b' ' * ((-len(text)) % 4)
    binary = bytes(blob) + b'\0' * ((-len(blob)) % 4)
    payload = (struct.pack('<III', 0x46546c67, 2, 28 + len(text) + len(binary))
               + struct.pack('<II', len(text), 0x4e4f534a) + text
               + struct.pack('<II', len(binary), 0x004e4942) + binary)
    output.parent.mkdir(parents=True, exist_ok=True);output.write_bytes(payload)
    report = {'source_head': str(head_path), 'source_head_sha256': sha(head_path), 'canonical_body': str(body_path),
              'canonical_body_sha256': sha(body_path), 'output': str(output), 'output_sha256': sha(output), 'tool_sha256': sha(__file__),
              'python_invariant_sha256': invariant_before, 'source_node_count': len(source['nodes']), 'allowed_weight_masks': masks,
              'touched': touched, 'canonical_patch_mapping': mapping, 'full_patch_weight_counts': (full > 1e-7).sum(1).tolist(),
              'max_four_dropped_weight': max(dropped), 'body_joint_names': body_names,
              'geometry_morphs_materials_images_and_outside_skin_bytes_unchanged': True,
              'original_binary_prefix_unchanged': binary[:len(old_blob)] == bytes(old_blob),
              'first_three_joint_names_and_ibm_bytes_unchanged': True,
              'interior_weight_approximation_note': 'Canonical matched body vertices retain all original weights. Newly interpolated cut vertices may use a measured four-weight approximation; do not claim the entire patch is canonically exact.'}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output_sha256': report['output_sha256'], 'python_invariant_sha256': invariant_before,
                      'touched': [(r['mesh'], r['material'], r['vertices']) for r in touched], 'max_four_dropped_weight': max(dropped)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', required=True);parser.add_argument('--body', required=True)
    parser.add_argument('--output', required=True);parser.add_argument('--report', required=True)
    args = parser.parse_args()
    repair(args.head, args.body, args.output, args.report)
