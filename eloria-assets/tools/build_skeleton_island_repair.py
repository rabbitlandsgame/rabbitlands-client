"""Skeleton-specific compact rigid-island motion candidate. Never installs it.

This keeps the source skeleton and its original node curves, adds one explicit
rigid control per welded anatomical bone island, and replaces the corrective
cache. It is an approximate repair with measured residuals, not lossless packing.
"""
from pathlib import Path
import argparse, copy, json
import numpy as np
from scipy.spatial.transform import Rotation
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array, compact
from video_motion import creature_bake_fit as fit
from add_creature_bake_helpers import _append_typed, _append_curve, _curve_signature, _kabsch


def prove_coincident_motion(position, joints, weights, targets):
    """Fail closed before welding rest contacts with different full trajectories.

    Equal dense skin coefficients and every POSITION delta imply equal position
    for arbitrary original bone poses and arbitrary corrective coefficients.
    Hard-normal/UV seams may still have different shading attributes.
    """
    _, first, inverse, counts = np.unique(position, axis=0, return_index=True,
                                         return_inverse=True, return_counts=True)
    dense = np.zeros((len(position), int(np.max(joints)) + 1))
    for slot in range(joints.shape[1]):
        np.add.at(dense, (np.arange(len(position)), joints[:, slot]), weights[:, slot])
    if not np.array_equal(dense, dense[first[inverse]]):
        raise ValueError('Coincident source vertices have different skin motion')
    if len(targets) and not np.array_equal(targets, targets[:, first[inverse]]):
        raise ValueError('Coincident source vertices have divergent corrective motion')
    return {'coincident_groups': int(np.count_nonzero(counts > 1)),
            'skin_coefficients_exact': True, 'all_position_targets_exact': True,
            'scope': 'All coefficients, including neutral, off-grid and blended poses.'}


def components(asset, primitive):
    points = accessor(asset.d, asset.b, primitive['attributes']['POSITION'])
    parent = np.arange(len(points))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        a, b = find(int(a)), find(int(b))
        if a != b: parent[b] = a
    triangles = accessor(asset.d, asset.b, primitive['indices']).astype(int).reshape(-1, 3)
    for triangle in triangles:
        union(triangle[0], triangle[1]); union(triangle[0], triangle[2])
    _, representative, inverse = np.unique(points, axis=0, return_index=True, return_inverse=True)
    for vertex, group in enumerate(inverse): union(vertex, representative[group])
    groups = {}
    for vertex in range(len(points)): groups.setdefault(find(vertex), []).append(vertex)
    return sorted([np.array(ids) for ids in groups.values()], key=lambda ids: -len(ids))


def training_states(asset, fps):
    world, morph, clocks = [], [], {}
    for clip in asset.animations:
        duration = asset.duration(clip)
        count = max(2, int(np.floor(duration * fps + 1e-6)) + 1) if duration else 1
        times = np.linspace(0, duration, count).astype('f4').astype(float)
        t, q, s, mw = asset.sample(clip, times)
        first = len(world)
        for k in range(len(times)):
            world.append(asset.world(t[k], q[k], s[k]))
            morph.append({node: value[k] for node, value in mw.items()})
        clocks[clip] = {'times': times, 'start': first, 'end': len(world)}
    world.append(asset.rest); morph.append(asset.default_weights)
    return {'world': np.array(world), 'morph': morph, 'clocks': clocks}


def build(source, output, *, fps=30, bounds_source=None, report=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output == source: raise ValueError('A new versioned output is required')
    if fps not in (30, 60, 120): raise ValueError('Explicit supported control cadence required')
    source_hash = digest(source)
    asset = NativeShapeAsset(source)
    if len(asset.parts) != 1 or len(asset.d.get('skins', [])) != 1:
        raise ValueError('Explicit one-body Skeleton source correspondence required')
    part = asset.parts[0]; node_id = part['node']
    names = {asset.names[n] for n in part['nodes']}
    if not {'hips', 'leg_a_l_01', 'leg_a_r_01', 'head'} <= names:
        raise ValueError('This recipe is specific to the audited Skeleton rig')
    node = asset.d['nodes'][node_id]; mesh = asset.d['meshes'][node['mesh']]
    if len(mesh['primitives']) != 1: raise ValueError('Single primitive required')
    primitive = mesh['primitives'][0]
    weld_proof = prove_coincident_motion(part['position'][:, :3], part['joints'],
                                         part['weights'], part['targets'])
    groups = components(asset, primitive)
    if len(groups) != 38: raise ValueError('Audited 38-island topology changed')
    data = fit._primitive_data(asset, part, primitive)
    states = training_states(asset, fps)
    source_skin = fit._skin(part, states)
    targets = fit._target(data, part, states, source_skin, 'POSITION')
    normals = fit._target(data, part, states, source_skin, 'NORMAL')
    tangents = fit._target(data, part, states, source_skin, 'TANGENT')
    neutral = targets[-1]
    mesh_rest = asset.rest[node_id]
    inverse_mesh = np.linalg.inv(mesh_rest)
    position = (inverse_mesh @ np.c_[neutral, np.ones(len(neutral))].T).T[:, :3]
    # Inverse-transpose normal transport inverted back into mesh-local space.
    normal = fit._unit(normals[-1] @ mesh_rest[:3, :3])
    document = copy.deepcopy(asset.d); blob = bytearray(asset.b)
    document.setdefault('asset', {}).setdefault('extras', {})['rabbitlands_animation_bake_fps'] = max(
        fps, int(document['asset'].get('extras', {}).get('rabbitlands_animation_bake_fps', 30)))
    output_mesh = document['meshes'][node['mesh']]
    output_primitive = output_mesh['primitives'][0]
    attrs = output_primitive['attributes']
    attrs['POSITION'] = append_array(document, blob, position, 'VEC3')
    attrs['NORMAL'] = append_array(document, blob, normal, 'VEC3')
    if tangents is not None:
        tangent = fit._unit(tangents[-1] @ np.linalg.inv(mesh_rest[:3, :3]).T)
        attrs['TANGENT'] = append_array(document, blob, np.c_[tangent, data['tangent'][:, 3]], 'VEC4')
    output_primitive.pop('targets', None)
    output_mesh.pop('weights', None)
    output_mesh.get('extras', {}).pop('targetNames', None)
    document['nodes'][node_id].pop('weights', None)
    if bounds_source is not None:
        bd, _ = read_glb(bounds_source)
        bound = next(m['extras']['rabbitlands_actor_bounds_v1'] for m in bd['meshes']
                     if m.get('extras', {}).get('rabbitlands_actor_bounds_v1'))
    else:
        bound = fit._original_mesh_bounds(asset.d, asset.b, mesh)
    output_mesh.setdefault('extras', {})['rabbitlands_actor_bounds_v1'] = copy.deepcopy(bound)
    roots = document.get('scenes', [])[0]['nodes']
    if any(scene['nodes'] != roots for scene in document['scenes']):
        raise ValueError('Differing scene root sets require explicit authoring')
    old_nodes = len(document['nodes']); wrapper = old_nodes
    document['nodes'].append({'name': 'RL_SkeletonIslandRig', 'children': list(roots)})
    for scene in document['scenes']: scene['nodes'] = [wrapper]
    for animation in document['animations']:
        animation['channels'] = [c for c in animation['channels'] if c['target']['path'] != 'weights']
    new_skin = copy.deepcopy(document['skins'][0])
    new_skin['skeleton'] = wrapper
    matrices, rows, ids_by_vertex = [], [], np.zeros(len(neutral), int)
    keys = 0
    for gi, ids in enumerate(groups):
        anchor = np.eye(4); anchor[:3, 3] = neutral[ids].mean(0)
        poses = np.array([_kabsch(neutral[ids], target[ids]) @ anchor for target in targets])
        foot = float(neutral[ids, 1].mean()) < .08 * float(np.ptp(neutral[:, 1]))
        pin_max = 0.
        residual_max = 0.
        for k, pose in enumerate(poses):
            predicted = (pose @ np.linalg.inv(anchor) @ np.c_[neutral[ids], np.ones(len(ids))].T).T[:, :3]
            if foot:
                delta = float(targets[k, ids, 1].min() - predicted[:, 1].min())
                poses[k, 1, 3] += delta; predicted[:, 1] += delta
                pin_max = max(pin_max, abs(delta))
            residual_max = max(residual_max, float(np.linalg.norm(predicted - targets[k, ids], axis=1).max()))
        # Default is the measured source neutral, not a training compromise.
        poses[-1] = anchor
        control = len(document['nodes'])
        document['nodes'].append({'name': f'RL_SkeletonIsland_{gi:02d}',
            'translation': anchor[:3, 3].tolist(), 'rotation': [0., 0., 0., 1.], 'scale': [1., 1., 1.]})
        document['nodes'][wrapper]['children'].append(control)
        new_skin['joints'].append(control)
        matrices.append(np.linalg.inv(anchor) @ mesh_rest)
        ids_by_vertex[ids] = len(part['nodes']) + gi
        quaternion = Rotation.from_matrix(poses[:, :3, :3]).as_quat()
        for k in range(1, len(quaternion)):
            if quaternion[k - 1] @ quaternion[k] < 0: quaternion[k] *= -1
        for animation in document['animations']:
            clock = states['clocks'][animation['name']]; span = slice(clock['start'], clock['end'])
            for path, value in [('translation', poses[span, :3, 3]), ('rotation', quaternion[span]),
                                ('scale', np.ones((clock['end'] - clock['start'], 3)))]:
                keys += _append_curve(document, blob, animation, control, path, clock['times'], value)
        rows.append({'island': gi, 'vertices': len(ids), 'vertex_ids': ids.tolist(),
                     'control_node': control, 'foot_support_pinned_to_source_minimum': foot,
                     'maximum_vertical_pin': pin_max, 'maximum_training_position_residual': residual_max})
    binds = np.concatenate([part['bind'], np.array(matrices)])
    new_skin['inverseBindMatrices'] = append_array(document, blob, binds.transpose(0, 2, 1).reshape(-1, 16), 'MAT4')
    document['skins'].append(new_skin)
    document['nodes'][node_id]['skin'] = 1
    sets = 2 if 'JOINTS_1' in attrs else 1
    for k in range(sets):
        spec = asset.d['accessors'][primitive['attributes'][f'JOINTS_{k}']]
        joint = np.zeros((len(neutral), 4), dtype='<u2' if spec['componentType'] == 5123 else '<u1')
        weight = np.zeros((len(neutral), 4))
        if k == 0: joint[:, 0] = ids_by_vertex; weight[:, 0] = 1
        attrs[f'JOINTS_{k}'] = _append_typed(document, blob, joint, spec)
        attrs[f'WEIGHTS_{k}'] = append_array(document, blob, weight, 'VEC4')
    # Only discarded corrective drivers become unreachable. Keep all original
    # nonweight sampler arrays unchanged and all old skin resources intact.
    for animation in document['animations']:
        used = sorted({c['sampler'] for c in animation['channels']})
        remap = {old: i for i, old in enumerate(used)}
        animation['samplers'] = [animation['samplers'][i] for i in used]
        for channel in animation['channels']: channel['sampler'] = remap[channel['sampler']]
    document, binary, packing = compact(document, blob, collapse_paths=())
    write_glb(output, document, binary)
    result_asset = NativeShapeAsset(output)
    original_curves = _curve_signature(asset)
    assert [c for c in _curve_signature(result_asset) if c[1]['node'] < old_nodes] == original_curves
    assert np.max(abs(result_asset.rest[:old_nodes] - asset.rest)) == 0
    assert {cl: result_asset.duration(cl) for cl in asset.animations} == {
        cl: asset.duration(cl) for cl in asset.animations}
    packed_primitive = document['meshes'][document['nodes'][node_id]['mesh']]['primitives'][0]
    for field in primitive['attributes']:
        if field.startswith(('JOINTS_', 'WEIGHTS_')) or field in ('POSITION', 'NORMAL', 'TANGENT'):
            continue
        assert np.array_equal(accessor(asset.d, asset.b, primitive['attributes'][field]),
            accessor(document, binary, packed_primitive['attributes'][field]))
    assert digest(source) == source_hash
    result = {'schema': 1, 'status': 'unapproved_rigid_island_repair_candidate',
        'source_sha256': source_hash, 'candidate_sha256': digest(output),
        'source_bytes': source.stat().st_size, 'candidate_bytes': output.stat().st_size,
        'original_bones': len(part['nodes']), 'added_controls': len(groups),
        'palette_bones': len(new_skin['joints']), 'source_vertices': len(neutral),
        'control_fps': fps, 'added_curve_keys': keys, 'corrective_targets': 0,
        'original_node_prefix': old_nodes, 'original_curves_bit_exact': True,
        'original_rest_worlds_exact': True, 'logical_bounds': bound,
        'vertex_mapping': list(range(len(neutral))), 'coincident_motion_proof': weld_proof,
        'islands': rows, 'packing': packing,
        'limitations': ['Approximate fit of original corrected trajectories, not approved or installed.',
            'Rigid shape deliberately removes inherited intrabone skin distortion.',
            'Requires actual client off-grid/default/RESET/switch, fresh Blender and visual qualification.',
            'Extra bone/palette CPU and storage cost must be reported; no FPS claim.']}
    if report is not None: Path(report).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path); parser.add_argument('output', type=Path)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--bounds-source', type=Path); parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, fps=args.fps,
        bounds_source=args.bounds_source, report=args.report), indent=2))
