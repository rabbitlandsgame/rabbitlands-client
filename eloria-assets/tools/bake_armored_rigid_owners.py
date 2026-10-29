"""Bake certified armored islands onto their existing anatomical skin controls.

This candidate-only tool keeps original POSITION/NORMAL/UV/topology, nodes,
rest, inverse binds, materials and every non-weight motion key. It replaces
skin ownership only after measuring complete physical components against the
frozen morph reference, then removes the redundant corrective fields. Source
files and runtime registries are never changed. Crossfades and actual packed
skin/normal behavior still require the independent client and visual checks.
"""
from __future__ import annotations

import os
os.environ['OPENBLAS_NUM_THREADS'] = '2'
os.environ['OMP_NUM_THREADS'] = '2'

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.creature_storage import _array, _append
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import compact
from optimize_creature_sampling import verify_static, _field_sampler


def require(value, message):
    if not value:
        raise ValueError(message)


def physical_components(position, indices):
    """Exact-position weld for analysis only; output vertices are never merged."""
    parent = np.arange(len(position))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        a, b = root(int(i)), root(int(j))
        if a != b:
            parent[max(a, b)] = min(a, b)

    for triangle in indices:
        join(triangle[0], triangle[1])
        join(triangle[0], triangle[2])
    coincident = {}
    for i, point in enumerate(position):
        key = tuple(point)
        if key in coincident:
            join(i, coincident[key])
        else:
            coincident[key] = i
    groups = {}
    for i in range(len(position)):
        groups.setdefault(root(i), []).append(i)
    return sorted([np.array(ids, int) for ids in groups.values()],
                  key=lambda ids: (float(position[ids, 0].min()), int(ids.min())))


def reference_states(asset, extra_queries):
    sample = _field_sampler(asset)
    worlds, positions, normals, labels = [], [], [], []
    for clip in asset.animations:
        duration = asset.duration(clip)
        times = np.unique(np.r_[0., duration, (np.arange(31) + .38196601125) / 31 * duration,
                                np.asarray(extra_queries.get(clip, []), float)])
        require(np.all(times >= 0) and np.all(times <= duration), 'Extra query outside native clip')
        t, q, s, morph = asset.sample(clip, times)
        for k, time in enumerate(times):
            world = asset.world(t[k], q[k], s[k])
            p, n = sample(world, {node: values[k] for node, values in morph.items()})
            worlds.append(world)
            positions.append(p)
            normals.append(n)
            labels.append({'clip': clip, 'seconds': float(time)})
    p, n = sample(asset.rest, asset.default_weights)
    worlds.append(asset.rest)
    positions.append(p)
    normals.append(n)
    labels.append({'clip': 'DEFAULT', 'seconds': 0.})
    return np.asarray(worlds), np.asarray(positions), np.asarray(normals), labels


def owner_error(matrices, position, normal, desired_position, desired_normal):
    predicted = np.einsum('tab,vb->tva', matrices[:, :3, :3], position) + matrices[:, None, :3, 3]
    distance = np.linalg.norm(predicted - desired_position, axis=2)
    n = np.einsum('tab,vb->tva', matrices[:, :3, :3], normal)
    lengths = np.linalg.norm(n, axis=2)
    require(np.all(lengths > 1e-20), 'Degenerate rigid-owner normal')
    n /= lengths[:, :, None]
    angle = np.rad2deg(np.arctan2(np.linalg.norm(np.cross(n, desired_normal), axis=2),
                                 np.sum(n * desired_normal, axis=2)))
    worst = np.unravel_index(np.argmax(distance), distance.shape)
    return {'maximum_position': float(distance.max()),
            'rms_position': float(np.sqrt(np.mean(distance ** 2))),
            'maximum_normal_degrees': float(angle.max()),
            'worst_pose': int(worst[0]), 'worst_local_vertex': int(worst[1])}


def active_ends(d, blob):
    return {a['name']: max(float(accessor(d, blob, a['samplers'][c['sampler']]['input'])[-1, 0])
                           for c in a['channels']) for a in d['animations']}


def build(source: Path, motion: Path, profile: Path, bounds_source: Path, output: Path, *, actor: str,
          report: Path, owner_position_limit: float, owner_normal_limit_degrees: float,
          owner_prefix='RL_Spider_', extra_queries=None,
          expected_source_sha256=None, expected_motion_sha256=None, expected_bounds_sha256=None):
    source, motion, profile, bounds_source, output, report = [Path(p).resolve()
        for p in (source, motion, profile, bounds_source, output, report)]
    require(output not in (source, motion, profile, bounds_source)
            and report not in (source, motion, profile, bounds_source, output), 'Input/output aliases forbidden')
    require(not output.exists() and not report.exists(), 'Versioned output/report already exists')
    require(owner_position_limit > 0 and 0 < owner_normal_limit_degrees < 180, 'Explicit finite owner limits required')
    hashes = {name: digest(path) for name, path in [('source', source), ('motion', motion),
                                                  ('profile', profile), ('bounds', bounds_source)]}
    for name, expected in [('source', expected_source_sha256), ('motion', expected_motion_sha256), ('bounds', expected_bounds_sha256)]:
        require(expected is None or hashes[name] == expected, f'{name} hash changed')
    document, blob = read_glb(motion)
    original, ob = read_glb(source)
    rate = document['asset'].get('extras', {}).get('rabbitlands_animation_bake_fps')
    require(isinstance(rate, (int, float)) and rate > 0, 'Motion bake cadence must be explicit')
    source_static = verify_static(original, ob, document, blob, rate)
    asset = NativeShapeAsset(source)
    require(len(asset.parts) == 1, 'This ownership tool requires one original skinned primitive')
    part = asset.parts[0]
    require('joints' in part, 'An existing skin is required')
    node_index = part['node']
    mesh_index = original['nodes'][node_index]['mesh']
    primitive = original['meshes'][mesh_index]['primitives'][0]
    require('indices' in primitive and 'NORMAL' in primitive['attributes'], 'Indexed mesh and normals required')
    indices = accessor(original, ob, primitive['indices']).astype(int).reshape(-1, 3)
    position = accessor(original, ob, primitive['attributes']['POSITION'])
    normal = accessor(original, ob, primitive['attributes']['NORMAL'])
    groups = physical_components(position, indices)
    actor_profile = json.loads(profile.read_text(encoding='utf-8'))[actor]
    known = {row['component']: row for row in actor_profile['rigid_components']}
    for component, row in known.items():
        require(component < len(groups) and len(groups[component]) == row['vertices'], 'Authored component identity/count changed')
    palette = {int(node): i for i, node in enumerate(part['nodes'])}
    eligible = [i for i, name in enumerate(asset.names) if name.startswith(owner_prefix) and i in palette]
    require(eligible and all(row['owner'] in palette for row in known.values()), 'Authored controls must already exist in the skin')
    worlds, desired_position, desired_normal, labels = reference_states(asset, extra_queries or {})
    ownership = np.empty(len(position), int)
    rows = []
    for component, ids in enumerate(groups):
        owners = [known[component]['owner']] if component in known else eligible
        trials = []
        for owner in owners:
            matrices = worlds[:, owner] @ part['bind'][palette[owner]]
            metrics = owner_error(matrices, position[ids], normal[ids], desired_position[:, ids], desired_normal[:, ids])
            trials.append((metrics['maximum_position'], owner, metrics))
        _, owner, metrics = min(trials, key=lambda r: r[0])
        require(metrics['maximum_position'] <= owner_position_limit
                and metrics['maximum_normal_degrees'] <= owner_normal_limit_degrees,
                f'Component {component} cannot be certified rigid: {metrics}')
        ownership[ids] = palette[owner]
        rows.append({'component': component, 'vertices': len(ids), 'owner_node': owner,
                     'owner_name': asset.names[owner], 'palette_index': palette[owner],
                     'binding': 'authored component owner' if component in known else 'minimum whole-component reference error',
                     **metrics, 'worst_reference_state': labels[metrics['worst_pose']]})
    candidate, binary = copy.deepcopy(document), bytearray(blob)
    attrs = candidate['meshes'][mesh_index]['primitives'][0]['attributes']
    sets = sorted(int(k.split('_')[1]) for k in attrs if k.startswith('JOINTS_'))
    require(sets in ([0], [0, 1]), 'Only original four/eight influence layouts supported')
    for si in sets:
        joint_name, weight_name = f'JOINTS_{si}', f'WEIGHTS_{si}'
        joint_spec, weight_spec = document['accessors'][attrs[joint_name]], document['accessors'][attrs[weight_name]]
        require(joint_spec['componentType'] in (5121, 5123) and not joint_spec.get('normalized'), 'Unsigned joint indices required')
        joints = _array(document, blob, attrs[joint_name])
        weights = _array(document, blob, attrs[weight_name])
        weights[:] = 0
        if si == 0:
            require(ownership.max() <= np.iinfo(joints.dtype).max, 'Owner exceeds stored joint index range')
            joints[:, 0] = ownership
            if np.issubdtype(weights.dtype, np.floating):
                weights[:, 0] = 1
            else:
                require(weight_spec.get('normalized'), 'Integer weights require normalization')
                weights[:, 0] = np.iinfo(weights.dtype).max
        attrs[joint_name] = _append(candidate, binary, joints, joint_spec)
        attrs[weight_name] = _append(candidate, binary, weights, weight_spec)
    baked_bounds, _ = read_glb(bounds_source)
    bounds_nodes = [n for n in baked_bounds['nodes'] if 'mesh' in n]
    require(len(bounds_nodes) == 1, 'One hash-bound bounds source required')
    extras = baked_bounds['meshes'][bounds_nodes[0]['mesh']].get('extras', {})
    bounds = extras.get('rabbitlands_actor_bounds_v1')
    require(bounds is not None, 'Existing original logical bounds metadata required')
    mesh = candidate['meshes'][mesh_index]
    mesh['primitives'][0].pop('targets', None)
    mesh.pop('weights', None)
    candidate['nodes'][node_index].pop('weights', None)
    mesh.setdefault('extras', {}).pop('targetNames', None)
    mesh['extras']['rabbitlands_actor_bounds_v1'] = copy.deepcopy(bounds)
    if 'rabbitlands_coat_pattern_height' in extras:
        mesh['extras']['rabbitlands_coat_pattern_height'] = extras['rabbitlands_coat_pattern_height']
    mesh['extras']['rabbitlands_armored_owner_bake_v1'] = {
        'source_sha256': hashes['source'], 'motion_sha256': hashes['motion'],
        'profile_sha256': hashes['profile'], 'physical_components': len(groups),
        'component_owners': [row['owner_node'] for row in rows], 'status': 'candidate_needs_review'}
    for animation in candidate['animations']:
        channels = [c for c in animation['channels'] if c['target']['path'] != 'weights']
        used = sorted({c['sampler'] for c in channels})
        remap = {old: new for new, old in enumerate(used)}
        for channel in channels:
            channel['sampler'] = remap[channel['sampler']]
        animation['channels'] = channels
        animation['samplers'] = [animation['samplers'][i] for i in used]
    require(active_ends(document, blob) == active_ends(candidate, binary), 'Removing correctives would change clip duration')
    candidate, binary, packing = compact(candidate, binary, collapse_paths=())
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.stem+'-', suffix='.glb', dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        write_glb(temporary, candidate, binary)
        actual, ab = read_glb(temporary)
        require(actual['nodes'] == candidate['nodes'], 'Node data changed in serialization')
        for key in ('materials', 'textures', 'samplers', 'scenes', 'scene'):
            require(actual.get(key) == document.get(key), f'{key} changed')
        require(actual['nodes'] == [{k:v for k,v in n.items() if k != 'weights'} if i==node_index else n
                                    for i,n in enumerate(document['nodes'])], 'Original node/default prefix changed')
        for before, after in zip(document['skins'], actual['skins'], strict=True):
            before, after = copy.deepcopy(before), copy.deepcopy(after)
            bi, ai = before.pop('inverseBindMatrices'), after.pop('inverseBindMatrices')
            require(before == after and _array(document, blob, bi).tobytes() == _array(actual, ab, ai).tobytes(), 'Original skin/rest binds changed')
        old_primitive, new_primitive = document['meshes'][mesh_index]['primitives'][0], actual['meshes'][mesh_index]['primitives'][0]
        for name, old_index in old_primitive['attributes'].items():
            if name.startswith(('JOINTS_', 'WEIGHTS_')):
                continue
            require(_array(document, blob, old_index).tobytes() == _array(actual, ab, new_primitive['attributes'][name]).tobytes(), f'{name} bits changed')
        require(_array(document, blob, old_primitive['indices']).tobytes() == _array(actual, ab, new_primitive['indices']).tobytes(), 'Topology changed')
        curve_proofs = []
        for old, new in zip(document['animations'], actual['animations'], strict=True):
            retained = [c for c in old['channels'] if c['target']['path'] != 'weights']
            require(len(retained) == len(new['channels']) and old['name'] == new['name'], 'Clip/channel inventory changed')
            for before, after in zip(retained, new['channels'], strict=True):
                require(before['target'] == after['target'], 'Target changed')
                bs, ns = old['samplers'][before['sampler']], new['samplers'][after['sampler']]
                require({k:v for k,v in bs.items() if k not in ('input','output')} == {k:v for k,v in ns.items() if k not in ('input','output')}, 'Sampler mode/metadata changed')
                for name in ('input','output'):
                    bits = _array(document, blob, bs[name]).tobytes()
                    require(bits == _array(actual, ab, ns[name]).tobytes(), 'Non-weight animation key bits changed')
                    curve_proofs.append(hashlib.sha256(bits).hexdigest())
        for image, new in zip(document.get('images', []), actual.get('images', []), strict=True):
            v, w = document['bufferViews'][image['bufferView']], actual['bufferViews'][new['bufferView']]
            require(blob[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
                    == ab[w.get('byteOffset',0):w.get('byteOffset',0)+w['byteLength']], 'Image bytes changed')
        require(active_ends(document, blob) == active_ends(actual, ab), 'Clip duration changed')
        require(all(digest(p)==hashes[n] for n,p in [('source',source),('motion',motion),('profile',profile),('bounds',bounds_source)]), 'An input changed')
        with output.open('xb') as f:
            f.write(temporary.read_bytes())
        result = {'actor': actor, 'status':'rigid_owner_candidate_requires_engine_and_visual_review',
                  'source':str(source),'source_sha256':hashes['source'],'motion':str(motion),'motion_sha256':hashes['motion'],
                  'profile_sha256':hashes['profile'],'bounds_source_sha256':hashes['bounds'],
                  'path':str(output),'sha256':digest(output),'bytes':output.stat().st_size,'fps':rate,
                  'corrective_targets':0,'added_nodes':0,'original_skin_bind_bits_preserved':True,
                  'original_geometry_normal_uv_topology_image_bits_preserved':True,
                  'non_weight_curve_bits_preserved':True,'non_weight_array_hashes':curve_proofs,
                  'clip_active_ends':active_ends(actual,ab),'source_static_proof':source_static,
                  'reference_states':labels,'component_order':'exact-position welded adjacency; ascending minimum X',
                  'component_owners':rows,'maximum_owner_position_error':max(r['maximum_position']for r in rows),
                  'maximum_owner_normal_error_degrees':max(r['maximum_normal_degrees']for r in rows),
                  'owner_certification_limits':{'position':owner_position_limit,'normal_degrees':owner_normal_limit_degrees},
                  'packing':packing,'implementation_sha256':digest(Path(__file__)),
                  'scope':'Existing anatomy/control ownership, no new bones/defaults or geometry fit. Native field certificate excludes packed GPU normals and real AnimationMixer crossfades; independent engine/visual qualification required.'}
        report.parent.mkdir(parents=True,exist_ok=True)
        with report.open('x',encoding='utf-8',newline='\n')as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','motion','profile','bounds-source','output','report'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actor',required=True)
    parser.add_argument('--owner-position-limit',type=float,required=True)
    parser.add_argument('--owner-normal-limit-degrees',type=float,required=True)
    parser.add_argument('--owner-prefix',default='RL_Spider_')
    for name in ('source','motion','bounds'):
        parser.add_argument('--expected-'+name+'-sha256')
    parser.add_argument('--extra-query',action='append',default=[],help='clip:seconds')
    args=parser.parse_args();queries={}
    for value in args.extra_query:
        clip,time=value.rsplit(':',1);queries.setdefault(clip,[]).append(float(time))
    result=build(args.source,args.motion,args.profile,args.bounds_source,args.output,actor=args.actor,report=args.report,
                 owner_position_limit=args.owner_position_limit,owner_normal_limit_degrees=args.owner_normal_limit_degrees,
                 owner_prefix=args.owner_prefix,extra_queries=queries,expected_source_sha256=args.expected_source_sha256,
                 expected_motion_sha256=args.expected_motion_sha256,expected_bounds_sha256=args.expected_bounds_sha256)
    print(json.dumps({k:result[k]for k in ('actor','sha256','bytes','fps','maximum_owner_position_error','maximum_owner_normal_error_degrees')}))


if __name__=='__main__':main()
