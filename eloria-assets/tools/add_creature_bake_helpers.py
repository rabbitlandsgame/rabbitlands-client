"""Experimental small rigid controls for an explicit corrective reference/bake pair.

Never installs assets. Original node/skin/bone-curve prefixes are preserved;
new world-space controls live under an identity scene wrapper. Measured errors
are approximate authoring evidence, not engine or artistic approval.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.spatial.transform import Rotation
from scipy.spatial import cKDTree

from video_motion.asset import accessor, digest, read_glb, write_glb, DTYPES, COUNTS
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array, compact
from video_motion import creature_bake_fit as fit

_IMPLEMENTATION_SHA = digest(Path(__file__))
_FITTER_SHA = digest(Path(fit.__file__))


def _primitives(asset):
    result, index = [], 0
    for ni, node in enumerate(asset.d['nodes']):
        if 'mesh' not in node:
            continue
        for pi, primitive in enumerate(asset.d['meshes'][node['mesh']]['primitives']):
            result.append((ni, pi, primitive, asset.parts[index]))
            index += 1
    return result


def _curve_signature(asset):
    records = []
    for animation in asset.d['animations']:
        for channel in animation['channels']:
            if channel['target']['path'] == 'weights':
                continue
            sampler = animation['samplers'][channel['sampler']]
            records.append((animation['name'], channel['target'],
                {k: v for k, v in sampler.items() if k not in ('input', 'output')},
                fit._hash_array(accessor(asset.d, asset.b, sampler['input'])),
                fit._hash_array(accessor(asset.d, asset.b, sampler['output']))))
    return records


def _check_pair(reference, baked):
    if len(reference.d['nodes']) != len(baked.d['nodes']):
        raise ValueError('Reference and zero bake must retain the same original node prefix')
    for a, b in zip(reference.d['nodes'], baked.d['nodes']):
        if {k: v for k, v in a.items() if k not in ('mesh', 'weights')} != {
                k: v for k, v in b.items() if k not in ('mesh', 'weights')}:
            raise ValueError('Reference/bake node hierarchy, skin or rest mismatch')
    if _curve_signature(reference) != _curve_signature(baked):
        raise ValueError('Reference/bake original node curves are not identical')
    if list(reference.animations) != list(baked.animations):
        raise ValueError('Clip inventories differ')
    if any(reference.duration(c) != baked.duration(c) for c in reference.animations):
        raise ValueError('Clip durations differ')
    if len(reference.d.get('skins', [])) != len(baked.d.get('skins', [])):
        raise ValueError('Reference/bake skin palettes differ')
    for a, b in zip(reference.d.get('skins', []), baked.d.get('skins', [])):
        if {k: v for k, v in a.items() if k != 'inverseBindMatrices'} != {
                k: v for k, v in b.items() if k != 'inverseBindMatrices'}:
            raise ValueError('Original skin palette changed')
        if fit._hash_array(accessor(reference.d, reference.b, a['inverseBindMatrices'])) != fit._hash_array(
                accessor(baked.d, baked.b, b['inverseBindMatrices'])):
            raise ValueError('Original inverse binds changed')
    a, b = _primitives(reference), _primitives(baked)
    if [(n, p, len(v['position'])) for n, p, _, v in a] != [(n, p, len(v['position'])) for n, p, _, v in b]:
        raise ValueError('Node/primitive/vertex identity changed')
    if any(p.get('targets') for _, _, p, _ in b):
        raise ValueError('Existing bake must contain zero corrective targets')
    for (_, _, original, _), (_, _, current, _) in zip(a, b):
        for field, index in original['attributes'].items():
            if field in ('POSITION', 'NORMAL', 'TANGENT', 'JOINTS_0', 'JOINTS_1', 'WEIGHTS_0', 'WEIGHTS_1'):
                continue
            if field not in current['attributes'] or fit._hash_array(accessor(reference.d, reference.b, index)) != fit._hash_array(
                    accessor(baked.d, baked.b, current['attributes'][field])):
                raise ValueError('Reference/bake static vertex identity differs')
        if original.get('material') != current.get('material'):
            raise ValueError('Reference/bake material identity differs')
        if ('indices' in original) != ('indices' in current) or ('indices' in original and
            fit._hash_array(accessor(reference.d, reference.b, original['indices'])) != fit._hash_array(
                accessor(baked.d, baked.b, current['indices']))):
            raise ValueError('Reference/bake oriented triangle identity differs')


def _states(asset, query_source, training=False):
    if not training:
        # Source STEP clocks must also be queried when the bake has removed
        # their weight channels. Only query scheduling uses the reference;
        # all sampled transforms/defaults come from the asset being measured.
        proxy = SimpleNamespace(d=query_source.d, b=query_source.b,
            animations=query_source.animations, duration=query_source.duration,
            sample=asset.sample, world=asset.world, t=asset.t, q=asset.q, s=asset.s,
            default_weights=asset.default_weights)
        return fit._states(proxy, training=False)
    worlds, morphs, labels, clocks = [], [], [], {}
    for clip in query_source.animations:
        duration = query_source.duration(clip)
        if duration and duration < 1 / 30 - 2e-5:
            raise ValueError('A nonzero clip shorter than one 30-Hz interval needs a declared exception')
        count = 1 if duration == 0 else max(2, int(np.floor(duration * 30 + 1e-6)) + 1)
        times = np.linspace(0, duration, count).astype('f4').astype(float)
        t, q, s, mw = asset.sample(clip, times)
        first = len(worlds)
        for i, time in enumerate(times):
            worlds.append(asset.world(t[i], q[i], s[i]))
            morphs.append({n: w[i] for n, w in mw.items()})
            labels.append(f'{clip}@{time:.12g}')
        clocks[clip] = {'times': times, 'start': first, 'end': len(worlds)}
    worlds.append(asset.rest)
    morphs.append(asset.default_weights)
    labels.append('NEUTRAL')
    return {'world': np.asarray(worlds), 'morph': morphs, 'labels': labels,
            'categories': np.array(['training'] * (len(worlds) - 1) + ['neutral']),
            'clocks': clocks}


def _data(asset, part, primitive):
    data = fit._primitive_data(asset, part, primitive)
    for field in ('POSITION', 'NORMAL', 'TANGENT'):
        if not any(field in t for t in primitive.get('targets', [])):
            data['targets'][field] = np.zeros((0, len(data['base']), 3))
    return data


def _kabsch(points, targets):
    """Proper rigid world transform, no scale/shear or reflected solution."""
    x, y = points.mean(0), targets.mean(0)
    u, singular, vt = np.linalg.svd((points - x).T @ (targets - y))
    if singular[1] < max(singular[0], 1e-30) * 1e-10:
        raise ValueError('Rigid patch has fewer than three noncollinear points')
    correction = np.eye(3)
    correction[2, 2] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ correction @ u.T
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = rotation, y - rotation @ x
    return matrix


def _adjacency(asset, primitive, data):
    count = len(data['base'])
    indices = (accessor(asset.d, asset.b, primitive['indices']).astype(int).ravel()
               if 'indices' in primitive else np.arange(count))
    if len(indices) % 3 or (indices < 0).any() or (indices >= count).any():
        raise ValueError('Invalid triangle indices')
    adjacency = [set() for _ in range(count)]
    for triangle in indices.reshape(-1, 3):
        for vertex in triangle:
            adjacency[vertex].update(int(v) for v in triangle if v != vertex)
    certified = {}
    for vertex in range(count):
        pieces = []
        for values in (data['base'][vertex], data['weights'][vertex], data['targets']['POSITION'][:, vertex]):
            values = values.copy()
            values[values == 0] = 0  # Signed zero does not distinguish trajectories.
            pieces.append(values.tobytes())
        certified.setdefault(b''.join(pieces), []).append(vertex)
    groups = list(certified.values())
    group_of = np.empty(count, dtype=int)
    for gi, ids in enumerate(groups):
        group_of[ids] = gi
        for vertex in ids:
            adjacency[vertex].update(ids)
    return adjacency, groups, group_of


def _patch(record, seed, height):
    base = record['world_base']
    owner = record['owners'][seed]
    maximum = max(12, min(512, int(np.ceil(len(base) * .08))))
    for radius in (height * .15, height * .3, float(np.linalg.norm(np.ptp(base, axis=0))) * .35):
        admitted, todo = set(), [int(seed)]
        while todo:
            vertex = todo.pop(0)
            if vertex in admitted or record['assigned'][vertex] or record['protected'][vertex] or record['owners'][vertex] != owner:
                continue
            if np.linalg.norm(base[vertex] - base[seed]) > radius:
                continue
            ids = record['groups'][record['group_of'][vertex]]
            if any(record['assigned'][i] or record['protected'][i] or record['owners'][i] != owner for i in ids):
                continue
            if len(admitted | set(ids)) > maximum:
                continue
            admitted.update(ids)
            for i in ids:
                todo.extend(sorted(record['adjacency'][i] - admitted))
        ids = np.array(sorted(admitted), dtype=int)
        if len(ids) >= 3:
            unique = np.unique(base[ids], axis=0)
            if len(unique) >= 3 and np.linalg.matrix_rank(unique - unique.mean(0), tol=height * 1e-10) >= 2:
                return ids, int(owner), float(radius)
    return None


def _learn(record, ids, height):
    points, targets = record['world_base'][ids], record['target'][:, ids]
    transforms = np.array([_kabsch(points, pose) for pose in targets])
    candidate = np.einsum('tab,vb->tva', transforms[:, :3], np.c_[points, np.ones(len(points))])
    budget = record['part']['joints'].shape[1]
    original = record['baked_data']['weights'][ids]
    kept = np.argsort(-original, axis=1, kind='stable')[:, :budget - 1]
    reduced = np.zeros_like(original)
    np.put_along_axis(reduced, kept, np.take_along_axis(original, kept, axis=1), axis=1)
    reduced /= reduced.sum(1, keepdims=True)
    blend = fit._blend(reduced, record['skin'])
    predicted = np.einsum('tvab,vb->tva', blend[..., :3], record['baked_data']['base'][ids]) + blend[..., 3]
    direction = candidate - predicted
    alpha = np.clip(np.sum(direction * (targets - predicted), axis=(0, 2)) /
                    np.maximum(np.sum(direction * direction, axis=(0, 2)), 1e-30), 0, 1)
    # Ties include complete raw POSITION columns and original skin, rather
    # than merely rest-coincident points. The input bake must retain them too.
    lookup = {int(v): i for i, v in enumerate(ids)}
    for vertex in ids:
        group = record['groups'][record['group_of'][vertex]]
        local = [lookup[int(i)] for i in group]
        if not np.array_equal(record['baked_data']['base'][group],
                              np.broadcast_to(record['baked_data']['base'][group[0]], (len(group), 3))):
            raise ValueError('Existing bake has already split a certified seam group')
        if not np.array_equal(record['baked_data']['weights'][group],
                              np.broadcast_to(record['baked_data']['weights'][group[0]],
                                              record['baked_data']['weights'][group].shape)):
            raise ValueError('Existing bake seam weights differ')
        a = float(np.clip(np.sum(direction[:, local] * (targets[:, local] - predicted[:, local])) /
                          max(float(np.sum(direction[:, local]**2)), 1e-30), 0, 1))
        alpha[local] = a
    mixed = predicted * (1 - alpha[None, :, None]) + candidate * alpha[None, :, None]
    before = float(np.sum((record['prediction'][:, ids] - targets)**2))
    after = float(np.sum((mixed - targets)**2))
    if after >= before or alpha.max(initial=0) == 0:
        return None
    anchor = np.eye(4)
    anchor[:3, 3] = points.mean(0)
    return {'ids': ids, 'alpha': alpha, 'reduced': reduced,
            'world': transforms @ anchor, 'bind': np.linalg.inv(anchor) @ record['mesh_rest'],
            'prediction': mixed, 'before_squared_error': before, 'after_squared_error': after,
            'anchor': anchor, 'normal_orientation_weight': 0.}


def _raw(document, blob, index):
    spec = document['accessors'][index]
    view = document['bufferViews'][spec['bufferView']]
    dtype = np.dtype('<' + DTYPES[spec['componentType']])
    width = COUNTS[spec['type']]
    return np.ndarray((spec['count'], width), dtype=dtype, buffer=blob,
        offset=view.get('byteOffset', 0) + spec.get('byteOffset', 0),
        strides=(view.get('byteStride', dtype.itemsize * width), dtype.itemsize)).copy()


def _append_typed(document, blob, array, template):
    array = np.ascontiguousarray(array)
    blob.extend(b'\0' * (-len(blob) % 4))
    document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': array.nbytes})
    blob.extend(array.tobytes())
    spec = {k: copy.deepcopy(v) for k, v in template.items()
            if k not in ('bufferView', 'byteOffset', 'min', 'max', 'sparse')}
    spec.update(bufferView=len(document['bufferViews']) - 1, count=len(array))
    document['accessors'].append(spec)
    return len(document['accessors']) - 1


def _write_weights(document, blob, original, primitive, dense, selected):
    attrs = primitive['attributes']
    sets = 2 if 'JOINTS_1' in attrs else 1
    budget = sets * 4
    joints = np.concatenate([_raw(original.d, original.b, attrs[f'JOINTS_{k}']) for k in range(sets)], axis=1)
    weights = np.concatenate([_raw(original.d, original.b, attrs[f'WEIGHTS_{k}']) for k in range(sets)], axis=1)
    joint_specs = [original.d['accessors'][attrs[f'JOINTS_{k}']] for k in range(sets)]
    weight_specs = [original.d['accessors'][attrs[f'WEIGHTS_{k}']] for k in range(sets)]
    if len({(s['componentType'], s.get('normalized', False)) for s in weight_specs}) != 1:
        raise ValueError('Mixed weight storage layouts need a separate authoring stage')
    chosen = np.argsort(-dense[selected], axis=1, kind='stable')[:, :budget]
    if chosen.shape[1] < budget:
        chosen = np.pad(chosen, ((0, 0), (0, budget - chosen.shape[1])))
    values = np.take_along_axis(dense[selected], chosen, axis=1)
    values /= values.sum(1, keepdims=True)
    joint_type = 5123 if max(int(chosen.max(initial=0)), int(joints.max(initial=0))) > 255 else joint_specs[0]['componentType']
    joints = joints.astype('<u2' if joint_type == 5123 else '<u1')
    joints[selected] = chosen
    wt = weight_specs[0]
    if wt['componentType'] == 5126:
        weights[selected] = values.astype('f4')
    elif wt.get('normalized') and wt['componentType'] in (5121, 5123):
        maximum = np.iinfo(weights.dtype).max
        quantized = np.floor(values * maximum).astype(np.int64)
        remainder = maximum - quantized.sum(1)
        for i, amount in enumerate(remainder):
            order = np.argsort(-(values[i] * maximum - quantized[i]), kind='stable')
            quantized[i, order[:int(amount)]] += 1
        weights[selected] = quantized.astype(weights.dtype)
    else:
        raise ValueError('Unsupported original weight storage')
    for k in range(sets):
        js = {**joint_specs[k], 'componentType': joint_type}
        attrs[f'JOINTS_{k}'] = _append_typed(document, blob, joints[:, k * 4:k * 4 + 4], js)
        attrs[f'WEIGHTS_{k}'] = _append_typed(document, blob, weights[:, k * 4:k * 4 + 4], weight_specs[k])
    return {'influence_budget': budget, 'joint_component_type': joint_type,
            'joint_storage_promoted': joint_type != joint_specs[0]['componentType'],
            'modified_vertices': len(selected), 'unselected_joint_values_preserved': True,
            'unselected_weight_storage_bits_preserved': True}


def _append_curve(document, blob, animation, node, path, times, values):
    values = np.asarray(values, dtype='f4')
    # Only newly authored controls may collapse bit-constant tracks.
    if len(values) > 2 and np.all(values.view('u1').reshape(len(values), -1) == values[0].view('u1')):
        times, values = times[[0, -1]], values[[0, -1]]
    sampler = {'input': append_array(document, blob, np.asarray(times)[:, None], 'SCALAR'),
               'output': append_array(document, blob, values, 'VEC4' if path == 'rotation' else 'VEC3'),
               'interpolation': 'LINEAR'}
    animation['samplers'].append(sampler)
    animation['channels'].append({'sampler': len(animation['samplers']) - 1,
                                  'target': {'node': node, 'path': path}})
    return len(times)


def _measure(reference, candidate, query_states, height):
    states = _states(candidate, reference)
    assert states['labels'] == query_states['labels']
    rows = []
    for (ni, pi, primitive, part), (_, _, other, cp) in zip(_primitives(reference), _primitives(candidate)):
        data, target = _data(reference, part, primitive), _data(candidate, cp, other)
        rs, cs = fit._skin(part, query_states), fit._skin(cp, states)
        errors = {}
        for field in ('POSITION', 'NORMAL', 'TANGENT'):
            a = fit._target(data, part, query_states, rs, field)
            b = fit._target(target, cp, states, cs, field)
            if a is None or b is None:
                errors[field] = None
            elif field == 'POSITION':
                errors[field] = np.linalg.norm(a - b, axis=2)
            else:
                angle = np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b), axis=2), np.sum(a * b, axis=2)))
                angle[(np.linalg.norm(a, axis=2) < 1e-12) != (np.linalg.norm(b, axis=2) < 1e-12)] = 180
                errors[field] = angle
        categories = {}
        for category in sorted(set(query_states['categories'])):
            mask = query_states['categories'] == category
            categories[str(category)] = fit._statistics(errors['POSITION'][mask],
                None if errors['NORMAL'] is None else errors['NORMAL'][mask],
                None if errors['TANGENT'] is None else errors['TANGENT'][mask], height)
        rows.append({'node': ni, 'primitive': pi, 'vertices': len(part['position']),
                     'status': 'measured', 'measurement': {'all': fit._statistics(
                         errors['POSITION'], errors['NORMAL'], errors['TANGENT'], height),
                         'categories': categories}})
    result = {'all': fit._summary(rows, len(states['labels']), height, 'measurement')}
    for category in sorted(set(states['categories'])):
        result[str(category)] = fit._summary(rows, int(sum(states['categories'] == category)),
                                            height, 'measurement', str(category))
    return result, states


def _verify_identity(base, candidate, records, old_count):
    for a, b in zip(base.d['nodes'], candidate.d['nodes'][:old_count]):
        assert {k: v for k, v in a.items() if k not in ('mesh', 'skin')} == {
            k: v for k, v in b.items() if k not in ('mesh', 'skin')}
    for i, skin in enumerate(base.d.get('skins', [])):
        other = candidate.d['skins'][i]
        assert {k: v for k, v in skin.items() if k != 'inverseBindMatrices'} == {
            k: v for k, v in other.items() if k != 'inverseBindMatrices'}
        assert fit._hash_array(accessor(base.d, base.b, skin['inverseBindMatrices'])) == fit._hash_array(
            accessor(candidate.d, candidate.b, other['inverseBindMatrices']))
    by_part = {(r['node'], r['primitive']): r for r in records}
    seam_count = 0
    for (ni, pi, a, part), (_, _, b, cp) in zip(_primitives(base), _primitives(candidate)):
        record = by_part.get((ni, pi))
        modified = np.zeros(len(part['position']), bool) if record is None else record['assigned']
        for field, index in a['attributes'].items():
            old, new = accessor(base.d, base.b, index), accessor(candidate.d, candidate.b, b['attributes'][field])
            mask = ~modified if field in ('NORMAL', 'TANGENT', 'JOINTS_0', 'JOINTS_1', 'WEIGHTS_0', 'WEIGHTS_1') else slice(None)
            assert fit._hash_array(old[mask]) == fit._hash_array(new[mask]), field
        if 'indices' in a:
            assert fit._hash_array(accessor(base.d, base.b, a['indices'])) == fit._hash_array(
                accessor(candidate.d, candidate.b, b['indices']))
        assert a.get('material') == b.get('material')
        old_mesh = base.d['meshes'][base.d['nodes'][ni]['mesh']]
        new_mesh = candidate.d['meshes'][candidate.d['nodes'][ni]['mesh']]
        assert old_mesh.get('extras') == new_mesh.get('extras')
        if record is not None:
            data = _data(candidate, cp, b)
            for group in record['groups']:
                if len(group) < 2:
                    continue
                assert np.array_equal(data['base'][group], np.broadcast_to(data['base'][group[0]], (len(group), 3)))
                assert np.array_equal(data['weights'][group], np.broadcast_to(data['weights'][group[0]], data['weights'][group].shape))
                seam_count += 1
    for field in ('materials', 'textures', 'samplers'):
        assert base.d.get(field) == candidate.d.get(field)
    for old, new in zip(base.d.get('images', []), candidate.d.get('images', [])):
        a, b = base.d['bufferViews'][old['bufferView']], candidate.d['bufferViews'][new['bufferView']]
        assert base.b[a.get('byteOffset', 0):a.get('byteOffset', 0) + a['byteLength']] == candidate.b[
            b.get('byteOffset', 0):b.get('byteOffset', 0) + b['byteLength']]
    return {'position_uv_indices_materials_images_logical_bounds_preserved': True,
            'unselected_attributes_preserved': True, 'certified_seam_groups_verified': seam_count}


def helper_bake(reference: Path, baked: Path, output: Path, helper_count=4, report: Path = None) -> dict:
    """Create a separately versioned, unapproved rigid-helper experiment."""
    reference, baked, output = map(lambda p: Path(p).resolve(), (reference, baked, output))
    if output in (reference, baked) or output.exists():
        raise ValueError('Output must be a new version, distinct from both preserved inputs')
    if not isinstance(helper_count, int) or not 1 <= helper_count <= 4:
        raise ValueError('helper_count must be between one and four')
    if report is not None and Path(report).resolve() in (reference, baked, output):
        raise ValueError('Report must not overwrite either input or the output GLB')
    if report is not None and Path(report).exists():
        raise ValueError('Report must be a new version')
    hashes = {'reference': digest(reference), 'baked': digest(baked)}
    source, base = NativeShapeAsset(reference), NativeShapeAsset(baked)
    _check_pair(source, base)
    scenes = base.d.get('scenes', [])
    if not scenes or any(scene.get('nodes', []) != scenes[0].get('nodes', []) for scene in scenes):
        raise ValueError('An explicit scene, or identical scene root sets, is required for the identity wrapper')
    training, independent = _states(source, source, training=True), _states(source, source)
    base_states = _states(base, source, training=True)
    height = float(np.ptp(source.vertices[:, 1]))
    if height <= 1e-12:
        raise ValueError('Nonzero source native Y height is required')
    before, _ = _measure(source, base, independent, height)
    # Unknown near-coincident contacts are excluded, never welded by sampled
    # equality. This preserves cross-part contacts and any seam whose complete
    # trajectory equivalence cannot be certified from raw columns/skin.
    part_ids = np.concatenate([np.full(len(p['position']), i) for i, p in enumerate(source.parts)])
    extent = max(float(np.abs(source.vertices).max()), float(np.ptp(source.vertices, axis=0).max()), 1e-12)
    contact_radius = float(np.spacing(np.float32(extent))) * 4
    cross_part = np.zeros(len(source.vertices), bool)
    for a, b in cKDTree(source.vertices).query_pairs(contact_radius):
        if part_ids[a] != part_ids[b]:
            cross_part[[a, b]] = True
    records = []
    original_offset = 0
    for (ni, pi, primitive, part), (_, _, bp, baked_part) in zip(_primitives(source), _primitives(base)):
        offset = original_offset
        original_offset += len(part['position'])
        if not primitive.get('targets') or 'joints' not in part:
            continue
        mesh = base.d['meshes'][base.d['nodes'][ni]['mesh']]
        if len(mesh['primitives']) != 1:
            raise ValueError('Mixed/multiple primitive body needs an explicit shell-preserving split first')
        data, baked_data = _data(source, part, primitive), _data(base, baked_part, bp)
        rs, skin = fit._skin(part, training), fit._skin(baked_part, base_states)
        target = fit._target(data, part, training, rs, 'POSITION')
        prediction = fit._target(baked_data, baked_part, base_states, skin, 'POSITION')
        adjacency, groups, group_of = _adjacency(source, primitive, data)
        protected = cross_part[offset:offset + len(part['position'])].copy()
        local_extent = max(float(np.abs(data['base']).max()), float(np.ptp(data['base'], axis=0).max()), 1e-12)
        local_radius = float(np.spacing(np.float32(local_extent))) * 4
        for a, b in cKDTree(data['base']).query_pairs(local_radius):
            if group_of[a] != group_of[b]:
                protected[[a, b]] = True
        for ids in groups:
            if protected[ids].any():
                protected[ids] = True
        mesh_rest = base.rest[ni]
        world_base = (mesh_rest @ np.c_[baked_data['base'], np.ones(len(baked_data['base']))].T).T[:, :3]
        records.append({'node': ni, 'primitive': pi, 'part': baked_part,
            'reference_part': part, 'reference_data': data, 'baked_data': baked_data,
            'target': target, 'prediction': prediction, 'skin': skin,
            'mesh_rest': mesh_rest, 'world_base': world_base,
            'owners': np.argmax(data['weights'], axis=1), 'adjacency': adjacency,
            'groups': groups, 'group_of': group_of, 'protected': protected,
            'assigned': np.zeros(len(world_base), bool)})
    controls, rejected = [], []
    for _ in range(helper_count):
        choices = []
        for record in records:
            error = np.linalg.norm(record['prediction'] - record['target'], axis=2).max(0)
            error[record['assigned']] = -1
            error[record['protected']] = -1
            choices.extend((float(error[i]), record, int(i)) for i in np.argsort(-error, kind='stable')[:24] if error[i] > height * 1e-10)
        chosen = None
        for error, record, seed in sorted(choices, key=lambda row: -row[0]):
            patch = _patch(record, seed, height)
            if patch is None:
                continue
            ids, owner, radius = patch
            try:
                learned = _learn(record, ids, height)
            except ValueError as error:
                rejected.append({'node': record['node'], 'seed': seed, 'reason': str(error)})
                continue
            if learned is not None:
                chosen = {**learned, 'record': record, 'owner': owner, 'radius': radius,
                          'seed_error': error}
                break
            rejected.append({'node': record['node'], 'seed': seed, 'reason': 'No training SSE improvement'})
        if chosen is None:
            break
        record, ids = chosen['record'], chosen['ids']
        record['assigned'][ids] = True
        record['prediction'][:, ids] = chosen['prediction']
        controls.append(chosen)
    document, binary = read_glb(baked)
    document = copy.deepcopy(document)
    blob = bytearray(binary)
    old_count = len(document['nodes'])
    wrapper = None
    added_keys = 0
    weight_reports = []
    if controls:
        names = {n.get('name') for n in document['nodes']}
        wrapper_name = 'RL_BakeHelpers_' + hashes['baked'][:8]
        if wrapper_name in names:
            raise ValueError('Helper wrapper name already exists')
        wrapper = len(document['nodes'])
        document['nodes'].append({'name': wrapper_name, 'children': list(scenes[0]['nodes'])})
        for scene in document['scenes']:
            scene['nodes'] = [wrapper]
        for ci, control in enumerate(controls):
            neutral = control['world'][-1]
            rotation = Rotation.from_matrix(control['world'][:, :3, :3]).as_quat()
            for i in range(1, len(rotation)):
                if np.dot(rotation[i - 1], rotation[i]) < 0:
                    rotation[i] *= -1
            node = len(document['nodes'])
            control['node'] = node
            document['nodes'].append({'name': f'{wrapper_name}_{ci + 1}',
                'translation': neutral[:3, 3].tolist(),
                'rotation': Rotation.from_matrix(neutral[:3, :3]).as_quat().tolist(), 'scale': [1., 1., 1.]})
            document['nodes'][wrapper]['children'].append(node)
            for animation in document['animations']:
                clock = training['clocks'][animation['name']]
                span = slice(clock['start'], clock['end'])
                for path, values in (('translation', control['world'][span, :3, 3]),
                                     ('rotation', rotation[span]),
                                     ('scale', np.ones((clock['end'] - clock['start'], 3)))):
                    added_keys += _append_curve(document, blob, animation, node, path, clock['times'], values)
        for record in records:
            relevant = [c for c in controls if c['record'] is record]
            if not relevant:
                continue
            ni = record['node']
            original_skin = base.d['nodes'][ni]['skin']
            skin = copy.deepcopy(base.d['skins'][original_skin])
            old_joints = len(skin['joints'])
            skin['joints'] += [c['node'] for c in relevant]
            skin['skeleton'] = wrapper
            binds = np.concatenate([record['part']['bind'], np.array([c['bind'] for c in relevant])])
            skin['inverseBindMatrices'] = append_array(document, blob, binds.transpose(0, 2, 1).reshape(-1, 16), 'MAT4')
            document['skins'].append(skin)
            document['nodes'][ni]['skin'] = len(document['skins']) - 1
            mesh = copy.deepcopy(base.d['meshes'][base.d['nodes'][ni]['mesh']])
            document['meshes'].append(mesh)
            document['nodes'][ni]['mesh'] = len(document['meshes']) - 1
            primitive = mesh['primitives'][record['primitive']]
            dense = np.pad(record['baked_data']['weights'], ((0, 0), (0, len(relevant))))
            for ci, control in enumerate(relevant):
                ids, alpha = control['ids'], control['alpha']
                dense[ids, :old_joints] = control['reduced'] * (1 - alpha[:, None])
                dense[ids, old_joints + ci] = alpha
            selected = np.flatnonzero(record['assigned'])
            # Source shading targets are fitted independently of rigid poses.
            extended_skin = np.concatenate([record['skin'], np.stack([
                c['world'] @ c['bind'] for c in relevant], axis=1)[:, :, :3]], axis=1)
            normal = fit._fit_directions(extended_skin, dense[selected],
                None if record['reference_data']['normal'] is None else fit._target(
                    record['reference_data'], record['reference_part'], training,
                    fit._skin(record['reference_part'], training), 'NORMAL')[:, selected],
                None if record['baked_data']['normal'] is None else record['baked_data']['normal'][selected])
            tangent = fit._fit_directions(extended_skin, dense[selected],
                None if record['reference_data']['tangent'] is None else fit._target(
                    record['reference_data'], record['reference_part'], training,
                    fit._skin(record['reference_part'], training), 'TANGENT')[:, selected],
                None if record['baked_data']['tangent'] is None else record['baked_data']['tangent'][selected])
            if normal is not None:
                values = record['baked_data']['normal'].copy()
                values[selected] = normal
                primitive['attributes']['NORMAL'] = append_array(document, blob, values, 'VEC3')
            if tangent is not None:
                if normal is not None:
                    tangent = fit._unit(tangent - normal * np.sum(tangent * normal, axis=1, keepdims=True))
                values = record['baked_data']['tangent'].copy()
                values[selected, :3] = tangent
                primitive['attributes']['TANGENT'] = append_array(document, blob, values, 'VEC4')
            weight_reports.append({'node': ni, 'original_skin_retained_index': original_skin,
                **_write_weights(document, blob, base, primitive, dense, selected)})
    if controls:
        used = sorted({n['mesh'] for n in document['nodes'] if 'mesh' in n})
        remap = {old: new for new, old in enumerate(used)}
        document['meshes'] = [document['meshes'][i] for i in used]
        for node in document['nodes']:
            if 'mesh' in node:
                node['mesh'] = remap[node['mesh']]
        document, blob, packing = compact(document, blob, collapse_paths=())
        write_glb(output, document, blob)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(baked.read_bytes())
        packing = {'unchanged_file_copy': True}
    result_asset = NativeShapeAsset(output)
    after, after_states = _measure(source, result_asset, independent, height)
    old_independent = _states(base, source)
    prefix_error = float(np.abs(after_states['world'][:, :old_count] - old_independent['world']).max())
    rest_error = float(np.abs(result_asset.rest[:old_count] - base.rest).max())
    if prefix_error > 1e-12 or rest_error > 1e-12:
        raise AssertionError('Original prefix world motion/rest changed')
    output_signatures = _curve_signature(result_asset)
    original_signatures = _curve_signature(base)
    assert [s for s in output_signatures if s[1]['node'] < old_count] == original_signatures
    identity_proof = _verify_identity(base, result_asset, records, old_count)
    assert digest(reference) == hashes['reference'] and digest(baked) == hashes['baked']
    total_vertices = sum(len(p['position']) for p in base.parts)
    result = {'schema': 1, 'status': 'helper_experiment_requires_client_and_visual_QA' if controls else 'no_beneficial_helper_found',
        'implementation_sha256': _IMPLEMENTATION_SHA, 'fitter_implementation_sha256': _FITTER_SHA,
        'reference': str(reference), 'reference_sha256': hashes['reference'],
        'baked': str(baked), 'baked_sha256': hashes['baked'], 'artifact': str(output), 'sha256': digest(output),
        'reference_bytes': reference.stat().st_size, 'before_bytes': baked.stat().st_size,
        'after_bytes': output.stat().st_size, 'added_bytes': output.stat().st_size - baked.stat().st_size,
        'added_bones': len(controls), 'added_curve_keys': added_keys, 'height': height,
        'before': before, 'after': after, 'weight_reports': weight_reports,
        'original_prefix_nodes': old_count, 'maximum_prefix_world_matrix_error': prefix_error,
        'maximum_prefix_rest_matrix_error': rest_error, 'original_bone_curve_arrays_bit_exact': True,
        'original_skin_resources_retained': True, 'source_inputs_unchanged': True,
        'identity_vertex_mapping': {'output_original_vertex_ids': list(range(total_vertices)),
            'parts': [{'node': ni, 'primitive': pi, 'vertices': len(part['position'])}
                      for ni, pi, _, part in _primitives(base)]},
        'identity_proof': identity_proof,
        'scene_path_change': {'identity_wrapper_node': wrapper, 'original_node_ids_unchanged': True,
                              'original_world_motion_unchanged': True},
        'controls': [{'node': c['node'], 'body_node': c['record']['node'],
            'primitive': c['record']['primitive'], 'original_owner_palette_joint': c['owner'],
            'original_owner_node': int(c['record']['reference_part']['nodes'][c['owner']]),
            'original_vertex_ids': c['ids'].tolist(), 'alpha_minimum': float(c['alpha'].min()),
            'alpha_maximum': float(c['alpha'].max()), 'patch_radius': c['radius'],
            'before_training_squared_error': c['before_squared_error'],
            'after_training_squared_error': c['after_squared_error'],
            'normal_orientation_weight': c['normal_orientation_weight']} for c in controls],
        'rejected': rejected, 'packing': packing, 'acceptance_threshold_assumed': None,
        'conservative_contact_guard': {'radius_world': contact_radius,
            'policy': 'Exclude uncertified near-coincident seams/contacts at four source float32 ULP; not an acceptance tolerance',
            'protected_vertices': sum(int(r['protected'].sum()) for r in records)},
        'actual_client_validated': False,
        'limitations': ['Approximate independent rigid controls; no runtime or artistic approval.',
            'Mixed/multiple primitive body nodes require a shell-preserving split first.',
            'Identical explicit scene root sets required; original prefix is wrapped by identity.',
            'Original metadata retained; mounted shells, effects, attachments and collision need client QA.',
            'Kabsch position controls and shading fits are separate; no helper scale/shear fitting.']}
    if report is not None:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('baked', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--helper-count', type=int, default=4)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = helper_bake(args.reference, args.baked, args.output, args.helper_count, args.report)
    print(json.dumps({k: result[k] for k in ('status', 'sha256', 'before_bytes', 'after_bytes', 'added_bones')}, indent=2))


if __name__ == '__main__':
    main()
