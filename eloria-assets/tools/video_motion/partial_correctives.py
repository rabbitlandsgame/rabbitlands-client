"""Partition complete corrective-free/rigid islands without changing other data.

Profiles select source-local vertices and an existing skin joint, never invent
bones or resample motion. Independent source/engine/render checks are still
required before installing an ownership change.
"""
import copy
import hashlib

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
    additionally requires owner_joint or owner_joints (one per selected vertex)
    and independent equivalence evidence. Each connected welded island must
    have a single owner, even when several islands share the new surface.
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
    selected_triangles = np.flatnonzero(membership == 3).tolist()
    if not selected_triangles:
        raise ValueError('Selected vertices have no complete rendered triangles')
    # Weld positions conservatively so UV/normal seams cannot be split across
    # imported tangent generation or visibly adjacent pieces.
    positions = raw_array(document, binary, primitive['attributes']['POSITION'])
    _, inverse = np.unique(positions, axis=0, return_inverse=True)
    if np.intersect1d(inverse[selected], inverse[remainder]).size:
        raise ValueError('Selection divides coincident source vertices')
    mode = profile['mode']
    if mode not in ('preserve_skin', 'rigid'):
        raise ValueError('Unknown partition mode')
    bake_defaults = profile.get('bake_selected_defaults', False)
    if type(bake_defaults) is not bool or (bake_defaults and mode != 'rigid'):
        raise ValueError('Default baking requires an explicit rigid candidate profile')
    preserve_weights = profile.get('preserve_rigid_weight_bits', False)
    if type(preserve_weights) is not bool or (preserve_weights and mode != 'rigid'):
        raise ValueError('Rigid weight preservation requires an explicit rigid candidate profile')
    if preserve_weights:
        joint_sets = {key.removeprefix('JOINTS_') for key in primitive['attributes'] if key.startswith('JOINTS_')}
        weight_sets = {key.removeprefix('WEIGHTS_') for key in primitive['attributes'] if key.startswith('WEIGHTS_')}
        if joint_sets != weight_sets:
            raise ValueError('Rigid weight preservation requires paired influence sets')
    defaults = np.asarray(node.get('weights', mesh.get('weights', [0.] * len(primitive.get('targets', [])))))
    for target_index, target in enumerate(primitive.get('targets', [])):
        if set(target) - {'POSITION', 'NORMAL', 'TANGENT'}:
            raise ValueError('Unsupported corrective attribute')
        for field, index in target.items():
            values = raw_array(document, binary, index)[selected]
            if mode == 'preserve_skin' and np.any(values != 0):
                raise ValueError('Preserved-skin partition contains nonzero corrective data')
            if mode == 'rigid' and defaults[target_index] != 0 and np.any(values != 0) and not bake_defaults:
                raise ValueError('Non-neutral source defaults need a separately qualified base bake')
    baked, bake_report = {}, []
    if bake_defaults:
        # A general positional rebase would also need original secondary-effect
        # geometry. This narrowly scoped bake retains POSITION bits exactly;
        # only roundoff-scale default direction corrections may be baked here.
        if not np.isfinite(defaults).all() or len(defaults) != len(primitive['targets']):
            raise ValueError('Invalid source corrective defaults')
        fields = {field for target in primitive['targets'] for field in target}
        for field in sorted(fields):
            if field not in primitive['attributes']:
                raise ValueError('Default bake requires an explicit source base attribute')
            index = primitive['attributes'][field]
            if document['accessors'][index]['componentType'] != 5126:
                raise ValueError('Default bake requires float32 base attributes')
            original = raw_array(document, binary, index)[selected]
            corrections = np.stack([raw_array(document, binary, target[field])[selected]
                                    if field in target else np.zeros((len(selected), 3))
                                    for target in primitive['targets']])
            values = original.copy()
            values[:, :3] = (original[:, :3].astype(float) + np.einsum('m,mvc->vc', defaults, corrections)).astype('<f4')
            if not np.isfinite(values).all():
                raise ValueError('Default bake produced a non-finite base')
            same = original.tobytes() == values.tobytes()
            difference = float(np.max(np.abs(values.astype(float) - original.astype(float))))
            if field == 'POSITION' and not same:
                raise ValueError('Default bake may not change POSITION bits without original secondary geometry')
            extent = max(float(np.abs(original[:, :3]).max()), float(np.abs(values[:, :3]).max()))
            limit = 4 * float(np.spacing(np.float32(extent)))
            if not np.isfinite(limit) or limit <= 0:
                raise ValueError('Default bake has an unsupported source direction magnitude')
            if field != 'POSITION' and difference > limit:
                raise ValueError('Default direction bake exceeds four float32 ULPs')
            baked[field] = values
            bake_report.append({'field': field, 'retained_bits_identical': same,
                                'maximum_component_change': difference,
                                'direction_component_limit': limit if field != 'POSITION' else None})
    height = float(profile['coat_pattern_height'])
    if not np.isfinite(height) or height <= 0:
        raise ValueError('Invalid original coat pattern height')
    owner = int(profile.get('owner_joint', 0))
    owners = np.full(len(selected), owner, dtype=np.int64)
    if 'owner_joints' in profile:
        values = profile['owner_joints']
        if mode != 'rigid' or 'owner_joint' in profile or not isinstance(values, list) or len(values) != len(selected) or any(type(v) is not int for v in values):
            raise ValueError('Per-vertex rigid owners must match the selected vertices without an ambiguous single owner')
        owners = np.asarray(values, dtype=np.int64)
    if mode == 'rigid':
        if 'skin' not in node or np.any(owners < 0) or np.any(owners >= len(document['skins'][node['skin']]['joints'])):
            raise ValueError('Rigid owner must be an existing skin joint')
        if not {'JOINTS_0', 'WEIGHTS_0'} <= set(primitive['attributes']):
            raise ValueError('Rigid ownership requires an explicit source skin encoding')
        joint_spec = document['accessors'][primitive['attributes']['JOINTS_0']]
        if joint_spec['componentType'] not in (5121, 5123) or joint_spec.get('normalized'):
            raise ValueError('Rigid joints require unsigned integer skin storage')
        if np.any(owners > np.iinfo(np.dtype(DTYPES[joint_spec['componentType']])).max):
            raise ValueError('Rigid owner exceeds the retained source joint storage')
        full_owners = np.full(count, -1, dtype=np.int64)
        full_owners[selected] = owners
        triangle_owners = full_owners[triangles[membership == 3]]
        if np.any(triangle_owners != triangle_owners[:, :1]):
            raise ValueError('One rigid island cannot have different triangle owners')
        for welded in np.unique(inverse[selected]):
            if len(np.unique(full_owners[inverse == welded])) != 1:
                raise ValueError('Coincident rigid vertices must retain one island owner')
    reference = copy.deepcopy(profile.get('reference_skin', profile.get('mount_skin')))
    if reference is not None:
        slots = {'godot-four-influences-u16-v1': 4, 'godot-eight-influences-u16-v1': 8}.get(reference.get('layout'))
        if slots is None: raise ValueError('Unsupported original secondary-effect skin layout')
        payload = bytes.fromhex(reference['skin_hex'])
        if len(payload) != len(selected) * slots * 4: raise ValueError('Original secondary-effect skin length differs')
        values = np.frombuffer(payload, '<u2').reshape(-1, slots * 2)
        skin = document['skins'][node['skin']]
        names = [document['nodes'][joint]['name'] for joint in skin['joints']]
        if reference['bind_names'] != names or np.any(values[:, :slots] >= len(names)):
            raise ValueError('Original secondary-effect skin bindings differ')
        sets = sorted(int(key.split('_')[1]) for key in primitive['attributes'] if key.startswith('JOINTS_'))
        old_joints = np.concatenate([raw_array(document, binary, primitive['attributes'][f'JOINTS_{i}'])[selected] for i in sets], axis=1)
        old_weights = np.concatenate([accessor(document, binary, primitive['attributes'][f'WEIGHTS_{i}'])[selected] for i in sets], axis=1)
        if old_joints.shape[1] != slots or not np.array_equal(values[:, :slots], old_joints):
            raise ValueError('Original secondary-effect joint rows differ')
        if np.max(np.abs(values[:, slots:] / 65535. - old_weights)) > 2 / 65535.:
            raise ValueError('Original secondary-effect weights differ')

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
            if not corrective and field in baked: values = baked[field]
            component = None
            if not corrective and mode == 'rigid' and field.startswith('JOINTS_'):
                if preserve_weights:
                    weight_field = field.replace('JOINTS_', 'WEIGHTS_')
                    if weight_field not in primitive['attributes']:
                        raise ValueError('Missing paired source weight set')
                    weights = accessor(document, binary, primitive['attributes'][weight_field])[ids]
                    if not np.isfinite(weights).all() or np.any(weights < 0):
                        raise ValueError('Invalid retained rigid weights')
                    desired = np.broadcast_to(owners[:, None], values.shape)
                    active = weights > 0
                    if values.dtype.kind != 'u' or np.any(desired[active] > np.iinfo(values.dtype).max):
                        raise ValueError('Rigid owner exceeds retained joint set storage')
                    values[active] = desired[active]
                else:
                    values = np.zeros_like(values)
                    if field == 'JOINTS_0': values[:, 0] = owners
            if not corrective and mode == 'rigid' and field.startswith('WEIGHTS_') and not preserve_weights:
                values = np.zeros_like(values)
                if field == 'WEIGHTS_0':
                    spec = document['accessors'][index]
                    values[:, 0] = np.iinfo(values.dtype).max if spec.get('normalized') else 1.
            if not corrective and mode == 'rigid' and field.startswith(('JOINTS_', 'WEIGHTS_')) and reference is None:
                if values.tobytes() != raw_array(document, binary, index)[ids].tobytes():
                    raise ValueError('Changed skin needs its original packed reference for secondary effects')
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
    group = profile.get('source_sha256', hashlib.sha256(bytes(binary)).hexdigest()) + ':' + str(node_index) + ':' + str(primitive_index)
    layout = {'group': group, 'source_vertices': count, 'source_triangles': len(triangles),
              'selected_triangles': selected_triangles}
    result['meshes'][mesh_index]['extras']['rabbitlands_surface_partition_v1'] = dict(layout, role='remainder', surface=primitive_index)
    free['extras']['rabbitlands_surface_partition_v1'] = dict(layout, role='selected', surface=0)
    if mode == 'rigid' and reference is not None:
        free['extras']['rabbitlands_surface_partition_v1']['reference_skin'] = reference
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
    rigid_weight_sums = None
    if preserve_weights:
        fields = [index for name, index in primitive['attributes'].items() if name.startswith('WEIGHTS_')]
        rigid_weight_sums = sum(accessor(document, binary, index)[selected].sum(1) for index in fields).tolist()
    return result, blob, {'mode': mode, 'source_node': node_index, 'new_node': new_node,
                          'source_vertices': count, 'corrective_vertices': len(remainder),
                          'source_triangles': len(triangles), 'selected_triangles': selected_triangles,
                          'corrective_free_vertices': len(selected), 'owner_joint': owner if mode == 'rigid' and 'owner_joints' not in profile else None,
                          'owner_joints': owners.tolist() if mode == 'rigid' and 'owner_joints' in profile else None,
                          'selected_default_bake': bake_report,
                          'preserved_rigid_weight_bits': preserve_weights,
                          'rigid_weight_sums': rigid_weight_sums,
                          'all_candidate_original_vertex_ids': global_ids, 'packing': packing}
