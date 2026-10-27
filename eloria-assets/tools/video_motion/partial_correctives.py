"""Partition complete corrective-free/rigid islands without changing other data.

Profiles select source-local vertices and an existing skin joint, never invent
bones or resample motion. Independent source/engine/render checks are still
required before installing an ownership change.
"""
import copy

import numpy as np

from .asset import accessor
from .packing import compact

DTYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def raw_array(document, binary, index):
    """Read stored values without converting normalized integers or float bits."""
    spec = document['accessors'][index]
    if spec.get('sparse'):
        raise ValueError('Sparse attributes require a separately qualified reader')
    dtype = np.dtype(DTYPES[spec['componentType']])
    count, width = int(spec['count']), WIDTHS[spec['type']]
    if 'bufferView' not in spec:
        return np.zeros((count, width), dtype=dtype)
    view = document['bufferViews'][spec['bufferView']]
    if view.get('buffer', 0) != 0 or view.get('extensions'):
        raise ValueError('Unsupported attribute storage')
    offset = int(view.get('byteOffset', 0)) + int(spec.get('byteOffset', 0))
    stride = int(view.get('byteStride', width * dtype.itemsize))
    if offset < 0 or stride < width * dtype.itemsize or offset + max(0, count - 1) * stride + width * dtype.itemsize > len(binary):
        raise ValueError('Attribute exceeds embedded storage')
    return np.ndarray((count, width), dtype=dtype, buffer=binary, offset=offset,
                      strides=(stride, dtype.itemsize)).copy()


def split_corrective_partition(document, binary, profile):
    """Split one source primitive's complete islands into one additional mesh.

    Required profile: source_node, primitive, vertex_ids, mode and
    coat_pattern_height (the original Godot mesh AABB height, including morphs).
    Modes: preserve_skin requires exactly zero selected morph fields; rigid
    additionally requires owner_joint and independent equivalence evidence.
    Optional mount_skin is an exact packed restoration record for rigid mode.
    Returns original-global vertex IDs in the output node/primitive order.
    """
    result, blob = copy.deepcopy(document), bytearray(binary)
    node_index = int(profile['source_node'])
    node = document['nodes'][node_index]
    mesh_index = node['mesh']
    if sum(n.get('mesh') == mesh_index for n in document['nodes']) != 1:
        raise ValueError('Instanced source meshes need an explicit per-instance profile')
    primitive_index = int(profile.get('primitive', 0))
    mesh = document['meshes'][mesh_index]
    primitive = mesh['primitives'][primitive_index]
    if not primitive.get('targets'):
        raise ValueError('Source primitive has no corrective storage to remove')
    count = document['accessors'][primitive['attributes']['POSITION']]['count']
    selected = np.asarray(profile['vertex_ids'], dtype=np.int64)
    if selected.ndim != 1 or not len(selected) or np.any(selected < 0) or np.any(selected >= count) or np.any(np.diff(selected) <= 0):
        raise ValueError('Selected source-local IDs must be sorted, unique and valid')
    remainder = np.setdiff1d(np.arange(count), selected)
    if not len(remainder):
        raise ValueError('Full-mesh elimination needs a separately qualified duration/weight-channel policy')
    marked = np.zeros(count, bool)
    marked[selected] = True
    if 'indices' not in primitive or primitive.get('mode', 4) != 4:
        raise ValueError('Partition requires indexed triangles')
    triangles = raw_array(document, binary, primitive['indices']).astype(np.int64).reshape(-1, 3)
    membership = marked[triangles].sum(1)
    if np.any((membership != 0) & (membership != 3)):
        raise ValueError('Selection splits a triangle')
    # Weld positions conservatively so UV/normal seams cannot be split across
    # imported tangent generation or visibly adjacent pieces.
    positions = raw_array(document, binary, primitive['attributes']['POSITION'])
    _, inverse = np.unique(positions, axis=0, return_inverse=True)
    if np.intersect1d(inverse[selected], inverse[remainder]).size:
        raise ValueError('Selection divides coincident source vertices')
    mode = profile['mode']
    if mode not in ('preserve_skin', 'rigid'):
        raise ValueError('Unknown partition mode')
    defaults = np.asarray(node.get('weights', mesh.get('weights', [0.] * len(primitive.get('targets', [])))))
    for target_index, target in enumerate(primitive.get('targets', [])):
        if set(target) - {'POSITION', 'NORMAL', 'TANGENT'}:
            raise ValueError('Unsupported corrective attribute')
        for field, index in target.items():
            values = raw_array(document, binary, index)[selected]
            if mode == 'preserve_skin' and np.any(values != 0):
                raise ValueError('Preserved-skin partition contains nonzero corrective data')
            if mode == 'rigid' and defaults[target_index] != 0 and np.any(values != 0):
                raise ValueError('Non-neutral source defaults need a separately qualified base bake')
    height = float(profile['coat_pattern_height'])
    if not np.isfinite(height) or height <= 0:
        raise ValueError('Invalid original coat pattern height')
    owner = int(profile.get('owner_joint', 0))
    if mode == 'rigid' and ('skin' not in node or not 0 <= owner < len(document['skins'][node['skin']]['joints'])):
        raise ValueError('Rigid owner must be an existing skin joint')

    def add(values, index, component=None):
        spec = copy.deepcopy(document['accessors'][index])
        spec.pop('byteOffset', None)
        spec.pop('sparse', None)
        if component is not None:
            spec['componentType'] = component
        values = np.ascontiguousarray(values, dtype=DTYPES[spec['componentType']])
        blob.extend(b'\0' * (-len(blob) % 4))
        result['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': values.nbytes})
        blob.extend(values.tobytes())
        spec.update(bufferView=len(result['bufferViews']) - 1, count=len(values))
        if 'min' in spec:
            spec['min'], spec['max'] = values.min(0).tolist(), values.max(0).tolist()
        result['accessors'].append(spec)
        return len(result['accessors']) - 1

    def subset(ids, corrective):
        output = copy.deepcopy(primitive)
        lookup = np.full(count, -1)
        lookup[ids] = np.arange(len(ids))
        component = 5123 if len(ids) <= 65536 else 5125
        indices = lookup[triangles[membership == (0 if corrective else 3)]].reshape(-1, 1)
        output['indices'] = add(indices, primitive['indices'], component)
        for field, index in primitive['attributes'].items():
            values = raw_array(document, binary, index)[ids]
            component = None
            if not corrective and mode == 'rigid' and field.startswith('JOINTS_'):
                values = np.zeros_like(values)
                if field == 'JOINTS_0': values[:, 0] = owner
            if not corrective and mode == 'rigid' and field.startswith('WEIGHTS_'):
                values = np.zeros_like(values)
                if field == 'WEIGHTS_0':
                    spec = document['accessors'][index]
                    values[:, 0] = np.iinfo(values.dtype).max if spec.get('normalized') else 1.
            output['attributes'][field] = add(values, index, component)
        if corrective:
            output['targets'] = [{field: add(raw_array(document, binary, index)[ids], index)
                                  for field, index in target.items()} for target in primitive.get('targets', [])]
        else:
            output.pop('targets', None)
        return output

    result['meshes'][mesh_index]['primitives'][primitive_index] = subset(remainder, True)
    name = 'RL_CorrectiveFree_' + str(node_index) + '_' + str(primitive_index)
    free = {'name': name, 'primitives': [subset(selected, False)]}
    free['extras'] = {key: copy.deepcopy(value) for key, value in mesh.get('extras', {}).items() if key != 'targetNames'}
    free['extras']['rabbitlands_coat_pattern_height'] = height
    result['meshes'][mesh_index].setdefault('extras', {})['rabbitlands_coat_pattern_height'] = height
    if mode == 'rigid' and profile.get('mount_skin'):
        free['extras']['rabbitlands_mount_skin_v1'] = copy.deepcopy(profile['mount_skin'])
    result['meshes'].append(free)
    free_node = copy.deepcopy(node)
    free_node.update(name=name, mesh=len(result['meshes']) - 1)
    free_node.pop('weights', None)
    new_node = len(result['nodes'])
    result['nodes'].append(free_node)
    parents = [n for n in result['nodes'][:-1] if node_index in n.get('children', [])]
    if parents:
        if len(parents) != 1: raise ValueError('Multiple source parents')
        parents[0]['children'].append(new_node)
    else:
        for scene in result.get('scenes', []):
            if node_index in scene.get('nodes', []): scene['nodes'].append(new_node)
    global_ids, cursor, original_start = [], 0, None
    for ni, original_node in enumerate(document['nodes']):
        if 'mesh' not in original_node: continue
        for pi, pr in enumerate(document['meshes'][original_node['mesh']]['primitives']):
            length = document['accessors'][pr['attributes']['POSITION']]['count']
            if ni == node_index and pi == primitive_index:
                original_start = cursor
                global_ids.extend((remainder + cursor).tolist())
            else: global_ids.extend(range(cursor, cursor + length))
            cursor += length
    global_ids.extend((selected + original_start).tolist())
    result, blob, packing = compact(result, blob)
    return result, blob, {'mode': mode, 'source_node': node_index, 'new_node': new_node,
                          'source_vertices': count, 'corrective_vertices': len(remainder),
                          'corrective_free_vertices': len(selected), 'owner_joint': owner if mode == 'rigid' else None,
                          'all_candidate_original_vertex_ids': global_ids, 'packing': packing}
