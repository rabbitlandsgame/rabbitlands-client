"""Exact removal of corrective targets which no current pose can activate.

This module never reduces animation precision or changes retained key times.
The caller must still qualify the new file in the actual renderer before use.
"""
from __future__ import annotations

import copy
import json

import numpy as np

_DTYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2',
           5125: '<u4', 5126: '<f4'}
_WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4,
           'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
_EXTENSIONS = {'KHR_materials_unlit', 'KHR_materials_specular',
               'KHR_materials_ior', 'KHR_materials_transmission',
               'KHR_materials_clearcoat', 'KHR_texture_transform',
               'KHR_materials_emissive_strength', 'KHR_mesh_quantization'}


def _check_extensions(value):
    if isinstance(value, dict):
        if set(value.get('extensions', {})) - _EXTENSIONS:
            raise ValueError('Review extension references before pruning targets')
        for child in value.values():
            _check_extensions(child)
    elif isinstance(value, list):
        for child in value:
            _check_extensions(child)


def _array(document, binary, index):
    """Read stored values without float conversion, including signed zero bits."""
    spec = document['accessors'][index]
    if spec.get('sparse'):
        raise ValueError('Sparse accessors require an explicit expansion proof')
    dtype = np.dtype(_DTYPES[spec['componentType']])
    count, width = spec['count'], _WIDTHS[spec['type']]
    if 'bufferView' not in spec:
        return np.zeros((count, width), dtype=dtype)
    view = document['bufferViews'][spec['bufferView']]
    if view.get('buffer', 0) != 0:
        raise ValueError('An embedded single buffer is required')
    offset = view.get('byteOffset', 0) + spec.get('byteOffset', 0)
    stride = view.get('byteStride', dtype.itemsize * width)
    required = (count - 1) * stride + dtype.itemsize * width if count else 0
    if count < 0 or stride < dtype.itemsize * width or spec.get('byteOffset', 0) < 0 or offset < 0 or offset + required > len(binary) or spec.get('byteOffset', 0) + required > view['byteLength']:
        raise ValueError('Accessor exceeds its buffer view')
    return np.ndarray((count, width), dtype, binary, offset=offset,
                      strides=(stride, dtype.itemsize)).copy()


def _append(document, binary, values, specification):
    values = np.ascontiguousarray(values)
    binary.extend(b'\0' * (-len(binary) % 4))
    document['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary),
                                    'byteLength': values.nbytes})
    binary.extend(values.tobytes())
    spec = copy.deepcopy(specification)
    for key in ['byteOffset', 'sparse']:
        spec.pop(key, None)
    spec['bufferView'] = len(document['bufferViews']) - 1
    spec['count'] = len(values)
    if 'min' in spec:
        spec['min'] = values.min(0).tolist()
    if 'max' in spec:
        spec['max'] = values.max(0).tolist()
    document['accessors'].append(spec)
    return len(document['accessors']) - 1


def _compact_reachable(document, binary):
    """Copy reachable views verbatim, without constant-key reduction."""
    refs = []
    for mesh in document.get('meshes', []):
        for primitive in mesh['primitives']:
            refs.extend((primitive['attributes'], key) for key in primitive['attributes'])
            if 'indices' in primitive:
                refs.append((primitive, 'indices'))
            for target in primitive.get('targets', []):
                refs.extend((target, key) for key in target)
    for skin in document.get('skins', []):
        if 'inverseBindMatrices' in skin:
            refs.append((skin, 'inverseBindMatrices'))
    for animation in document.get('animations', []):
        for sampler in animation.get('samplers', []):
            refs.extend([(sampler, 'input'), (sampler, 'output')])
    kept = sorted({container[key] for container, key in refs})
    accessor_map = {old: new for new, old in enumerate(kept)}
    accessors = [document['accessors'][index] for index in kept]
    views = [(spec, 'bufferView') for spec in accessors if 'bufferView' in spec]
    for image in document.get('images', []):
        if 'uri' in image or 'bufferView' not in image:
            raise ValueError('Embedded images are required')
        views.append((image, 'bufferView'))
    view_ids = sorted({container[key] for container, key in views})
    result, new_views, view_map, dedup = bytearray(), [], {}, {}
    for index in view_ids:
        view = copy.deepcopy(document['bufferViews'][index])
        if view.get('buffer', 0) != 0 or view.get('extensions'):
            raise ValueError('Unsupported binary view')
        offset, length = view.get('byteOffset', 0), view['byteLength']
        if offset < 0 or length < 0 or offset + length > len(binary):
            raise ValueError('Buffer view exceeds embedded storage')
        payload = bytes(binary[offset:offset + length])
        metadata = {k: v for k, v in view.items() if k not in ('byteOffset', 'buffer')}
        key = (json.dumps(metadata, sort_keys=True), payload)
        if key not in dedup:
            result.extend(b'\0' * (-len(result) % 4))
            view.update(buffer=0, byteOffset=len(result))
            result.extend(payload)
            dedup[key] = len(new_views)
            new_views.append(view)
        view_map[index] = dedup[key]
    for container, key in refs:
        container[key] = accessor_map[container[key]]
    for container, key in views:
        container[key] = view_map[container[key]]
    document['accessors'], document['bufferViews'] = accessors, new_views
    document['buffers'][0]['byteLength'] = len(result)
    return document, result


def _neutral_duration_anchor(document, binary, animation, start, end, animated):
    """Use only a default property which is static across the entire clip set."""
    for node_index, node in enumerate(document.get('nodes', [])):
        if 'matrix' in node:
            continue
        for path, default in [('scale', [1., 1., 1.]),
                              ('translation', [0., 0., 0.]),
                              ('rotation', [0., 0., 0., 1.])]:
            if (node_index, path) in animated or path not in node:
                continue
            original_value = np.asarray(node[path], dtype=float)
            value = np.asarray(node[path], dtype='<f4')
            if not np.isfinite(value).all() or value.shape != (len(default),) or not np.array_equal(value.astype(float), original_value):
                continue
            times = np.asarray([[start], [end]], dtype='<f4')
            values = np.tile(value, (2, 1))
            input_index = _append(document, binary, times,
                                  {'type': 'SCALAR', 'componentType': 5126})
            output_index = _append(document, binary, values,
                                   {'type': 'VEC4' if path == 'rotation' else 'VEC3', 'componentType': 5126})
            animation['samplers'].append({'input': input_index, 'output': output_index,
                                           'interpolation': 'LINEAR'})
            animation['channels'].append({'sampler': len(animation['samplers']) - 1,
                                           'target': {'node': node_index, 'path': path}})
            return {'node': node_index, 'path': path, 'start': start, 'end': end}
    raise ValueError('Removing final weight clocks needs a globally static TRS duration anchor')


def prune_zero_targets(document, buffer):
    """Remove only targets with exactly zero defaults and LINEAR/STEP keys.

    Every node instancing each mesh is considered. Shared animation samplers are
    cloned when channels require different retained columns. Retained accessors,
    names and non-weight curves keep their original bits and timestamps. Unknown
    storage extensions, sparse accessors, malformed or non-finite weight data and
    cubic weight tracks are rejected before output. The input objects are intact.
    """
    if len(document.get('buffers', [])) != 1 or document['buffers'][0].get('uri'):
        raise ValueError('An embedded single buffer is required')
    if set(document.get('extensionsUsed', [])) - _EXTENSIONS:
        raise ValueError('Review extension references before pruning targets')
    _check_extensions(document)
    if any(spec.get('sparse') for spec in document.get('accessors', [])):
        raise ValueError('Sparse accessors require an explicit expansion proof')
    result, binary = copy.deepcopy(document), bytearray(buffer)
    masks, details = {}, []
    nodes = document.get('nodes', [])
    for mesh_index, mesh in enumerate(document.get('meshes', [])):
        counts = {len(primitive.get('targets', [])) for primitive in mesh['primitives']}
        if len(counts) != 1:
            raise ValueError('All primitives of a mesh must have equal target counts')
        count = counts.pop()
        if not count:
            continue
        active = np.zeros(count, dtype=bool)
        for obj in [mesh] + [node for node in nodes if node.get('mesh') == mesh_index]:
            values = np.asarray(obj.get('weights', [0.] * count), dtype=float)
            if values.shape != (count,) or not np.isfinite(values).all():
                raise ValueError('Invalid target default weights')
            active |= values != 0
        for animation in document.get('animations', []):
            for channel in animation.get('channels', []):
                target = channel['target']
                if target.get('path') != 'weights':
                    continue
                node = nodes[target['node']]
                if node.get('mesh') != mesh_index:
                    continue
                sampler = animation['samplers'][channel['sampler']]
                if sampler.get('interpolation', 'LINEAR') not in ('LINEAR', 'STEP'):
                    raise ValueError('Only LINEAR/STEP weight tracks can prove zero activation')
                spec = document['accessors'][sampler['output']]
                if spec['componentType'] != 5126 or spec['type'] != 'SCALAR' or spec.get('normalized'):
                    raise ValueError('Weight outputs must be unnormalized float32 scalars')
                values = _array(document, buffer, sampler['output'])
                clock_spec = document['accessors'][sampler['input']]
                if clock_spec['componentType'] != 5126 or clock_spec['type'] != 'SCALAR' or clock_spec.get('normalized'):
                    raise ValueError('Weight timestamps must be unnormalized float32 scalars')
                times = _array(document, buffer, sampler['input'])
                if times.shape[1:] != (1,) or len(times) == 0 or not np.isfinite(times).all() or np.any(np.diff(times[:, 0]) <= 0):
                    raise ValueError('Invalid weight key timestamps')
                if values.size != len(times) * count or not np.isfinite(values).all():
                    raise ValueError('Invalid target weight key dimensions/values')
                active |= np.any(values.reshape(-1, count) != 0, axis=0)
        keep, removed = np.flatnonzero(active).tolist(), np.flatnonzero(~active).tolist()
        masks[mesh_index] = keep
        details.append({'mesh': mesh_index, 'targets_before': count, 'targets_after': len(keep),
                        'removed_target_indices': removed, 'retained_target_indices': keep})
    report = {'changed': any(row['removed_target_indices'] for row in details),
              'meshes': details, 'removed_weight_values': 0, 'duration_anchors': [],
              'source_buffer_bytes': len(buffer)}
    if not report['changed']:
        report['packed_buffer_bytes'] = len(buffer)
        return result, binary, report
    original_weight_outputs = {animation['samplers'][channel['sampler']]['output']
                               for animation in document.get('animations', [])
                               for channel in animation.get('channels', [])
                               if channel['target'].get('path') == 'weights'}
    original_weight_values = sum(document['accessors'][i]['count'] for i in original_weight_outputs)
    for row in details:
        if not row['removed_target_indices']:
            continue
        mesh_index, keep = row['mesh'], masks[row['mesh']]
        mesh = result['meshes'][mesh_index]
        for primitive in mesh['primitives']:
            if keep:
                primitive['targets'] = [primitive['targets'][i] for i in keep]
            else:
                primitive.pop('targets', None)
        for obj in [mesh] + [node for node in result.get('nodes', []) if node.get('mesh') == mesh_index]:
            if 'weights' in obj:
                if keep:
                    obj['weights'] = [obj['weights'][i] for i in keep]
                else:
                    obj.pop('weights')
        names = mesh.get('extras', {}).get('targetNames')
        if names is not None:
            if len(names) != row['targets_before']:
                raise ValueError('Target name count differs from corrective targets')
            if keep:
                mesh['extras']['targetNames'] = [names[i] for i in keep]
            else:
                mesh['extras'].pop('targetNames')
    animated = {(ch['target'].get('node'), ch['target'].get('path'))
                for animation in document.get('animations', []) for ch in animation.get('channels', [])}
    changed_meshes = {row['mesh']: row for row in details if row['removed_target_indices']}
    for animation_index, animation in enumerate(result.get('animations', [])):
        original = document['animations'][animation_index]
        clocks = [_array(document, buffer, sampler['input']) for sampler in original.get('samplers', [])]
        start = min(float(clock.min()) for clock in clocks)
        end = max(float(clock.max()) for clock in clocks)
        channels, replacements = [], {}
        for channel in animation.get('channels', []):
            target = channel['target']
            mesh_index = nodes[target['node']].get('mesh') if target.get('path') == 'weights' else None
            if mesh_index not in changed_meshes:
                channels.append(channel)
                continue
            keep = masks[mesh_index]
            if not keep:
                continue
            key = (channel['sampler'], tuple(keep))
            if key not in replacements:
                sampler = copy.deepcopy(original['samplers'][channel['sampler']])
                count = changed_meshes[mesh_index]['targets_before']
                values = _array(document, buffer, sampler['output']).reshape(-1, count)
                sampler['output'] = _append(result, binary, values[:, keep].reshape(-1, 1),
                                             document['accessors'][sampler['output']])
                animation['samplers'].append(sampler)
                replacements[key] = len(animation['samplers']) - 1
            channel['sampler'] = replacements[key]
            channels.append(channel)
        animation['channels'] = channels
        used = sorted({channel['sampler'] for channel in channels})
        remaining_end = max((float(_array(result, binary, animation['samplers'][i]['input']).max()) for i in used), default=-np.inf)
        if remaining_end < end:
            anchor = _neutral_duration_anchor(result, binary, animation, start, end, animated)
            report['duration_anchors'].append({'animation': animation_index, **anchor})
            used.append(len(animation['samplers']) - 1)
        remap = {old: new for new, old in enumerate(used)}
        animation['samplers'] = [animation['samplers'][i] for i in used]
        for channel in animation['channels']:
            channel['sampler'] = remap[channel['sampler']]
    result, binary = _compact_reachable(result, binary)
    final_weight_outputs = {animation['samplers'][channel['sampler']]['output']
                            for animation in result.get('animations', [])
                            for channel in animation.get('channels', [])
                            if channel['target'].get('path') == 'weights'}
    report['removed_weight_values'] = original_weight_values - sum(result['accessors'][i]['count'] for i in final_weight_outputs)
    report['packed_buffer_bytes'] = len(binary)
    return result, binary, report
