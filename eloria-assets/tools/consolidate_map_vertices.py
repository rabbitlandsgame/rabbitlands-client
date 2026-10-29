#!/usr/bin/env python3
"""Share byte-identical static map vertices without changing triangle corners.

This post-publication pass changes vertex/index storage only. It retains node,
mesh, primitive and material identities, triangle order, every attribute's raw
component bytes, and original position bounds. It never rounds floats or merges
across a UV, normal, tangent, colour or other attribute seam. Run after normal
quantization so equality is measured at the precision the package actually uses.

Unsupported deformation/extension contracts are left untouched. Only complete,
smaller GLB candidates that pass the independent equivalence check are returned.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

DTYPES = {5120: np.dtype('i1'), 5121: np.dtype('u1'), 5122: np.dtype('<i2'),
          5123: np.dtype('<u2'), 5125: np.dtype('<u4'), 5126: np.dtype('<f4')}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
SAFE_EXTENSIONS = {'KHR_mesh_quantization', 'KHR_materials_emissive_strength'}


class ConsolidationError(ValueError):
    pass


def decode(data: bytes) -> tuple[dict, bytes]:
    if len(data) < 20 or struct.unpack_from('<III', data) != (0x46546c67, 2, len(data)):
        raise ConsolidationError('expected one complete GLB 2.0 file')
    length, kind = struct.unpack_from('<II', data, 12)
    if kind != 0x4e4f534a or length % 4 or 20 + length > len(data):
        raise ConsolidationError('invalid JSON chunk')
    document = json.loads(data[20:20 + length])
    if 20 + length == len(data):
        return document, b''
    if 28 + length > len(data):
        raise ConsolidationError('truncated BIN header')
    size, kind = struct.unpack_from('<II', data, 20 + length)
    if kind != 0x004e4942 or 28 + length + size != len(data):
        raise ConsolidationError('expected one terminal BIN chunk')
    return document, data[28 + length:]


def encode(document: dict, binary: bytes) -> bytes:
    text = json.dumps(document, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    text += b' ' * (-len(text) % 4)
    body = binary + b'\0' * (-len(binary) % 4)
    return (struct.pack('<III', 0x46546c67, 2, 28 + len(text) + len(body))
            + struct.pack('<II', len(text), 0x4e4f534a) + text
            + struct.pack('<II', len(body), 0x004e4942) + body)


def accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    a = document['accessors'][index]
    if 'sparse' in a or 'bufferView' not in a:
        raise ConsolidationError('sparse/implicit accessors are not supported')
    if a.get('type') not in WIDTHS or a.get('componentType') not in DTYPES:
        raise ConsolidationError('unsupported accessor element')
    v = document['bufferViews'][a['bufferView']]
    dt = DTYPES[a['componentType']]
    count, width = a['count'], WIDTHS[a['type']]
    element = width * dt.itemsize
    stride = v.get('byteStride', element)
    offset = a.get('byteOffset', 0)
    start = v.get('byteOffset', 0) + offset
    end = offset + (stride * (count - 1) + element if count else 0)
    if v.get('buffer', 0) != 0 or count < 0 or stride < element or stride % dt.itemsize \
            or start % dt.itemsize or offset < 0 or end > v['byteLength'] \
            or v.get('byteOffset', 0) + v['byteLength'] > len(binary):
        raise ConsolidationError('accessor lies outside its buffer view')
    values = np.array(np.ndarray((count, width), dtype=dt, buffer=binary,
                                offset=start, strides=(stride, dt.itemsize)), copy=True)
    if dt.kind == 'f' and not np.isfinite(values).all():
        raise ConsolidationError('non-finite vertex data')
    return values


def _unsupported(document: dict) -> str | None:
    buffers = document.get('buffers', [])
    if len(buffers) != 1 or 'uri' in buffers[0]:
        return 'external_or_multiple_buffers'
    if document.get('skins') or document.get('animations') or any('skin' in n for n in document.get('nodes', [])):
        return 'deformation_or_animation'
    if (set(document.get('extensionsUsed', [])) | set(document.get('extensionsRequired', []))) - SAFE_EXTENSIONS:
        return 'unqualified_extension'
    def extensions(value):
        if isinstance(value, dict):
            if set(value.get('extensions', {})) - SAFE_EXTENSIONS:
                return True
            return any(extensions(v) for v in value.values())
        return isinstance(value, list) and any(extensions(v) for v in value)
    if extensions(document):
        return 'unqualified_extension'
    if any('sparse' in a for a in document.get('accessors', [])):
        return 'sparse_accessor'
    for mesh in document.get('meshes', []):
        if mesh.get('weights'):
            return 'morph_weights'
        for p in mesh.get('primitives', []):
            if p.get('mode', 4) != 4 or p.get('targets'):
                return 'non_triangle_or_morph_primitive'
            if any(s.startswith(('JOINTS_', 'WEIGHTS_')) for s in p.get('attributes', {})):
                return 'skinning_attributes'
    return None


def _indices(document: dict, binary: bytes, primitive: dict, count: int) -> np.ndarray:
    if 'indices' not in primitive:
        values = np.arange(count, dtype=np.int64)
    else:
        a = document['accessors'][primitive['indices']]
        if a.get('componentType') not in (5121, 5123, 5125) or a.get('type') != 'SCALAR' \
                or a.get('normalized', False):
            raise ConsolidationError('invalid triangle indices')
        values = accessor(document, binary, primitive['indices']).reshape(-1).astype(np.int64)
    if len(values) % 3 or (len(values) and (values.min() < 0 or values.max() >= count)):
        raise ConsolidationError('triangle index/count out of range')
    return values


def _retained_vertices(arrays: dict, document: dict, primitive: dict, indices: np.ndarray):
    """Keep bound extrema even when they belong to unused vertices.

    Unused extrema can influence imported AABBs, culling and cutaway decisions.
    Keeping at most two vertices per bounded component avoids that behaviour
    change while still removing other unused or repeated complete records.
    """
    retain = [np.unique(indices)]
    for semantic, values in arrays.items():
        a = document['accessors'][primitive['attributes'][semantic]]
        if semantic == 'POSITION' or 'min' in a or 'max' in a:
            retain.extend((np.argmin(values, axis=0), np.argmax(values, axis=0)))
    used = np.unique(np.concatenate(retain))
    record = np.ascontiguousarray(np.concatenate(
        [values.view(np.uint8).reshape(len(values), -1) for _, values in sorted(arrays.items())], axis=1))
    packed = record.view(np.dtype('V' + str(record.shape[1]))).reshape(len(record))
    _, first, inverse = np.unique(packed[used], return_index=True, return_inverse=True)
    order = np.argsort(first)
    stable = np.empty(len(order), dtype=np.int64)
    stable[order] = np.arange(len(order))
    selected = used[first[order]]
    remap = np.full(len(record), -1, dtype=np.int64)
    remap[used] = stable[inverse]
    return selected, remap[indices]


def _pack(document: dict, binary: bytes, replaced: set[int]) -> tuple[dict, bytes]:
    """Discard only replaced accessors/views, retaining unrelated payloads."""
    referenced = {i for m in document.get('meshes', []) for p in m['primitives']
                  for i in list(p['attributes'].values()) + ([p['indices']] if 'indices' in p else [])}
    keep = [i for i in range(len(document['accessors'])) if i not in replaced or i in referenced]
    mapping = {old: new for new, old in enumerate(keep)}
    removable_views = {document['accessors'][i]['bufferView'] for i in replaced}
    document['accessors'] = [document['accessors'][i] for i in keep]
    used_views = {a['bufferView'] for a in document['accessors'] if 'bufferView' in a}
    used_views.update(i['bufferView'] for i in document.get('images', []) if 'bufferView' in i)
    keep_views = [i for i in range(len(document['bufferViews']))
                  if i not in removable_views or i in used_views]
    view_map = {old: new for new, old in enumerate(keep_views)}
    packed = bytearray()
    aliases = {}
    for old in keep_views:
        view = document['bufferViews'][old]
        key = (view.get('byteOffset', 0), view['byteLength'])
        if key not in aliases:
            packed.extend(b'\0' * (-len(packed) % 4))
            aliases[key] = len(packed)
            packed.extend(binary[key[0]:key[0] + key[1]])
        view['byteOffset'] = aliases[key]
        view['buffer'] = 0
    document['bufferViews'] = [document['bufferViews'][i] for i in keep_views]
    for a in document['accessors']:
        if 'bufferView' in a:
            a['bufferView'] = view_map[a['bufferView']]
    for image in document.get('images', []):
        if 'bufferView' in image:
            image['bufferView'] = view_map[image['bufferView']]
    for mesh in document.get('meshes', []):
        for p in mesh['primitives']:
            p['attributes'] = {s: mapping[i] for s, i in p['attributes'].items()}
            if 'indices' in p:
                p['indices'] = mapping[p['indices']]
    packed.extend(b'\0' * (-len(packed) % 4))
    document['buffers'][0]['byteLength'] = len(packed)
    return document, bytes(packed)


def verify_equivalent(before: bytes, after: bytes) -> dict:
    """Independently compare every expanded triangle and retained contract."""
    left, lb = decode(before)
    right, rb = decode(after)
    mutable = {'accessors', 'bufferViews', 'buffers', 'meshes', 'images'}
    if {k: v for k, v in left.items() if k not in mutable} != \
            {k: v for k, v in right.items() if k not in mutable}:
        raise ConsolidationError('scene/material/placement metadata changed')
    if len(left.get('meshes', [])) != len(right.get('meshes', [])):
        raise ConsolidationError('mesh identity/count changed')
    digest = hashlib.sha256()
    triangles = vertices_before = vertices_after = 0
    for lm, rm in zip(left.get('meshes', []), right.get('meshes', [])):
        if {k: v for k, v in lm.items() if k != 'primitives'} != {k: v for k, v in rm.items() if k != 'primitives'} \
                or len(lm['primitives']) != len(rm['primitives']):
            raise ConsolidationError('mesh metadata changed')
        for lp, rp in zip(lm['primitives'], rm['primitives']):
            if {k: v for k, v in lp.items() if k not in ('attributes', 'indices')} != \
                    {k: v for k, v in rp.items() if k not in ('attributes', 'indices')} \
                    or set(lp['attributes']) != set(rp['attributes']):
                raise ConsolidationError('primitive/material/attribute identity changed')
            ln = left['accessors'][lp['attributes']['POSITION']]['count']
            rn = right['accessors'][rp['attributes']['POSITION']]['count']
            li, ri = _indices(left, lb, lp, ln), _indices(right, rb, rp, rn)
            if len(li) != len(ri):
                raise ConsolidationError('triangle count changed')
            triangles += len(li) // 3
            vertices_before += ln
            vertices_after += rn
            for semantic in sorted(lp['attributes']):
                la = left['accessors'][lp['attributes'][semantic]]
                ra = right['accessors'][rp['attributes'][semantic]]
                contract = lambda a: {k: v for k, v in a.items() if k not in ('bufferView', 'byteOffset', 'count')}
                if contract(la) != contract(ra):
                    raise ConsolidationError('attribute precision/bounds/metadata changed')
                lv, rv = accessor(left, lb, lp['attributes'][semantic]), accessor(right, rb, rp['attributes'][semantic])
                if semantic == 'POSITION' and (not np.array_equal(lv.min(0), rv.min(0))
                                                or not np.array_equal(lv.max(0), rv.max(0))):
                    raise ConsolidationError('position bounds changed')
                digest.update(semantic.encode() + b'\0')
                for start in range(0, len(li), 65536):
                    a = np.ascontiguousarray(lv[li[start:start + 65536]]).tobytes()
                    b = np.ascontiguousarray(rv[ri[start:start + 65536]]).tobytes()
                    if a != b:
                        raise ConsolidationError('triangle-corner attribute bytes changed')
                    digest.update(a)
    if len(left.get('images', [])) != len(right.get('images', [])):
        raise ConsolidationError('images changed')
    for a, b in zip(left.get('images', []), right.get('images', [])):
        if {k: v for k, v in a.items() if k != 'bufferView'} != {k: v for k, v in b.items() if k != 'bufferView'}:
            raise ConsolidationError('image metadata changed')
        if 'bufferView' in a:
            av, bv = left['bufferViews'][a['bufferView']], right['bufferViews'][b['bufferView']]
            if lb[av.get('byteOffset', 0):av.get('byteOffset', 0) + av['byteLength']] != \
                    rb[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]:
                raise ConsolidationError('embedded image bytes changed')
    return {'triangles': triangles, 'verticesBefore': vertices_before, 'verticesAfter': vertices_after,
            'expandedAttributeSha256': digest.hexdigest(), 'positionBoundsUnchanged': True}


def consolidate(data: bytes) -> dict:
    document, binary = decode(data)
    reason = _unsupported(document)
    if reason:
        return {'status': 'skipped', 'reason': reason}
    logical = document['buffers'][0].get('byteLength')
    if not isinstance(logical, int) or logical < 0 or logical > len(binary) \
            or len(binary) - logical > 3 or any(binary[logical:]):
        raise ConsolidationError('invalid buffer length/padding')
    coverage = np.zeros(logical, dtype=np.bool_)
    for v in document.get('bufferViews', []):
        start, size = v.get('byteOffset', 0), v.get('byteLength', -1)
        if v.get('buffer', 0) != 0 or start < 0 or size < 0 or start + size > logical:
            raise ConsolidationError('buffer view outside declared buffer')
        coverage[start:start + size] = True
    if np.any(np.frombuffer(binary[:logical], dtype=np.uint8)[~coverage]):
        return {'status': 'skipped', 'reason': 'unreferenced_binary_payload'}
    original = copy.deepcopy(document)
    body = bytearray(binary)
    replaced = set()
    changed_primitives = 0
    def append(values, template, view_template, *, vertex):
        element = values.dtype.itemsize * values.shape[1]
        stride = (element + 3) // 4 * 4 if vertex else element
        padded = np.zeros((len(values), stride), np.uint8)
        padded[:, :element] = values.view(np.uint8).reshape(len(values), element)
        body.extend(b'\0' * (-len(body) % 4))
        view = copy.deepcopy(view_template)
        view.update(buffer=0, byteOffset=len(body), byteLength=padded.nbytes,
                    target=34962 if vertex else 34963)
        view.pop('byteStride', None)
        if vertex:
            view['byteStride'] = stride
        document['bufferViews'].append(view)
        body.extend(padded.tobytes())
        a = copy.deepcopy(template)
        a.update(bufferView=len(document['bufferViews']) - 1, count=len(values))
        a.pop('byteOffset', None)
        document['accessors'].append(a)
        return len(document['accessors']) - 1
    for mesh in document.get('meshes', []):
        for p in mesh['primitives']:
            attrs = p['attributes']
            # Avoid changing import-generated shading attributes as a side effect.
            material = document.get('materials', [])[p['material']] if 'material' in p else {}
            if 'NORMAL' not in attrs or ('normalTexture' in material and 'TANGENT' not in attrs):
                continue
            arrays = {s: accessor(original, binary, ai) for s, ai in attrs.items()}
            n = len(arrays['POSITION'])
            if not n or any(len(a) != n for a in arrays.values()):
                raise ConsolidationError('vertex attribute counts differ/empty')
            indices = _indices(original, binary, p, n)
            select, new_indices = _retained_vertices(arrays, original, p, indices)
            index_type = 5123 if len(select) <= 65535 else 5125
            new_payload = sum(len(select) * ((a.dtype.itemsize * a.shape[1] + 3) // 4 * 4)
                              for a in arrays.values()) + len(indices) * DTYPES[index_type].itemsize
            old_views = {original['accessors'][ai]['bufferView']
                         for ai in list(attrs.values()) + ([p['indices']] if 'indices' in p else [])}
            old_payload = sum(original['bufferViews'][vi]['byteLength'] for vi in old_views)
            if new_payload >= old_payload:
                continue
            changed_primitives += 1
            for s, ai in list(attrs.items()):
                replaced.add(ai)
                a = original['accessors'][ai]
                attrs[s] = append(arrays[s][select], a, original['bufferViews'][a['bufferView']], vertex=True)
            old_index = p.get('indices')
            if old_index is not None:
                replaced.add(old_index)
            template = copy.deepcopy(original['accessors'][old_index]) if old_index is not None else {'type': 'SCALAR'}
            template.update(componentType=index_type)
            template.pop('normalized', None)
            if 'min' in template:
                template['min'] = [int(new_indices.min())]
            if 'max' in template:
                template['max'] = [int(new_indices.max())]
            index_view = original['bufferViews'][original['accessors'][old_index]['bufferView']] \
                if old_index is not None else {}
            p['indices'] = append(new_indices.astype(DTYPES[index_type]).reshape(-1, 1), template,
                                  index_view, vertex=False)
    if not changed_primitives:
        return {'status': 'unchanged', 'reason': 'no_beneficial_primitive'}
    document, packed = _pack(document, bytes(body), replaced)
    candidate = encode(document, packed)
    if len(candidate) >= len(data):
        return {'status': 'unchanged', 'reason': 'container_not_smaller'}
    proof = verify_equivalent(data, candidate)
    return {'status': 'changed', 'data': candidate, 'oldBytes': len(data), 'newBytes': len(candidate),
            'savedBytes': len(data) - len(candidate), 'primitives': changed_primitives, **proof}


def process(path: Path) -> dict:
    return consolidate(Path(path).read_bytes())
