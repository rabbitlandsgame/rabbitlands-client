"""Split measured root-rigid shell islands from Crystalback's corrective mesh.

The hash-bound profile contains the selected source vertices and the original
Godot 4.7 four-influence skin bytes needed by the separate mounted gait.
Keep the input immutable; qualify the output before runtime replacement.
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np

from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.packing import compact

DTYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2',
          5125: '<u4', 5126: '<f4'}


def pack(source, profile, output):
    if source.resolve() == output.resolve():
        raise ValueError('Keep the source immutable')
    if digest(source) != profile['source_sha256']:
        raise ValueError('Profile does not match the source SHA256')
    original, original_buffer = read_glb(source)
    document, buffer = copy.deepcopy(original), bytearray(original_buffer)
    if len(document['meshes']) != 1 or len(document['meshes'][0]['primitives']) != 1:
        raise ValueError('Pilot requires the original single-primitive source')
    primitive = original['meshes'][0]['primitives'][0]
    positions = accessor(original, original_buffer, primitive['attributes']['POSITION'])
    count = len(positions)
    rigid = np.asarray(profile['rigid_original_vertex_ids'], dtype=int)
    if not len(rigid) or len(rigid) != len(np.unique(rigid)) or np.any(rigid < 0) or np.any(rigid >= count):
        raise ValueError('Invalid or repeated rigid vertex IDs')
    if np.any(np.diff(rigid) <= 0):
        raise ValueError('Rigid IDs must be sorted in retained-skin order')
    soft = np.setdiff1d(np.arange(count), rigid)
    if not len(soft):
        raise ValueError('Pilot must retain the deforming body')
    if max(len(soft), len(rigid)) > 65536:
        raise ValueError('Pilot output exceeds its uint16 index format')
    marked = np.zeros(count, bool)
    marked[rigid] = True
    triangles = accessor(original, original_buffer, primitive['indices']).astype(int).reshape(-1, 3)
    membership = marked[triangles].sum(1)
    if np.any((membership != 0) & (membership != 3)):
        raise ValueError('Selected vertices split a triangle')
    skin = original['skins'][0]
    owner = skin['joints'].index(profile['root_bone_node'])
    bind_names = [original['nodes'][joint]['name'] for joint in skin['joints']]
    if profile['mount_skin'].get('layout') != 'godot-four-influences-u16-v1' or profile['mount_skin'].get('source_sha256') != profile['source_sha256']:
        raise ValueError('Retained mount skin source/layout differs')
    if bind_names != profile['mount_skin']['bind_names']:
        raise ValueError('Retained mount bindings differ')
    packed = bytes.fromhex(profile['mount_skin']['skin_hex'])
    if len(packed) != len(rigid) * 16:
        raise ValueError('Retained mount skin length differs')
    packed_values = np.frombuffer(packed, '<u2').reshape(-1, 8)
    old_joints = accessor(original, original_buffer, primitive['attributes']['JOINTS_0'])[rigid]
    old_weights = accessor(original, original_buffer, primitive['attributes']['WEIGHTS_0'])[rigid]
    if not np.array_equal(packed_values[:, :4], old_joints):
        raise ValueError('Retained mount joint indices differ')
    if np.max(np.abs(packed_values[:, 4:] / 65535.0 - old_weights)) > 2 / 65535.0:
        raise ValueError('Retained mount weights differ from the source')

    def add(values, specification):
        values = np.ascontiguousarray(values)
        specification = copy.deepcopy(specification)
        specification.pop('byteOffset', None)
        specification.pop('sparse', None)
        buffer.extend(b'\0' * (-len(buffer) % 4))
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(buffer), 'byteLength': values.nbytes})
        buffer.extend(values.tobytes())
        specification['bufferView'] = len(document['bufferViews']) - 1
        specification['count'] = len(values)
        if 'min' in specification:
            specification['min'] = values.min(0).tolist()
            specification['max'] = values.max(0).tolist()
        document['accessors'].append(specification)
        return len(document['accessors']) - 1

    def subset(ids, corrective):
        result = copy.deepcopy(primitive)
        remap = np.full(count, -1)
        remap[ids] = np.arange(len(ids))
        picked = triangles[membership == (0 if corrective else 3)]
        specification = copy.deepcopy(original['accessors'][primitive['indices']])
        specification['componentType'] = 5123
        result['indices'] = add(remap[picked].reshape(-1, 1).astype('<u2'), specification)
        for name, index in primitive['attributes'].items():
            specification = original['accessors'][index]
            values = accessor(original, original_buffer, index)[ids].astype(DTYPES[specification['componentType']])
            if not corrective and name == 'JOINTS_0':
                values = np.zeros_like(values)
                values[:, 0] = owner
            if not corrective and name == 'WEIGHTS_0':
                values = np.zeros_like(values)
                values[:, 0] = 1.0
            result['attributes'][name] = add(values, specification)
        if corrective:
            result['targets'] = [{name: add(accessor(original, original_buffer, index)[ids].astype('<f4'), original['accessors'][index])
                                  for name, index in target.items()} for target in primitive['targets']]
        else:
            result.pop('targets', None)
        return result

    document['meshes'][0]['primitives'] = [subset(soft, True)]
    document['meshes'].append({'name': 'RL_RigidShell', 'primitives': [subset(rigid, False)],
                              'extras': {'rabbitlands_mount_skin_v1': copy.deepcopy(profile['mount_skin'])}})
    node = copy.deepcopy(document['nodes'][profile['mesh_node']])
    node.update(name='RL_RigidShell', mesh=1)
    node.pop('weights', None)
    document['nodes'].append(node)
    document['nodes'][profile['mesh_parent']]['children'].append(len(document['nodes']) - 1)
    # Coat shaders use the unsplit model's height as their pattern scale.
    height = float(profile['coat_pattern_height'])
    if not np.isfinite(height) or height <= 0:
        raise ValueError('Invalid source coat pattern height')
    for mesh in document['meshes']:
        mesh.setdefault('extras', {})['rabbitlands_coat_pattern_height'] = height
    selected_triangles = np.flatnonzero(membership == 3).tolist()
    layout = {'group': profile['source_sha256'] + ':' + str(profile['mesh_node']) + ':0', 'source_vertices': count,
              'source_triangles': len(triangles), 'selected_triangles': selected_triangles}
    document['meshes'][0]['extras']['rabbitlands_surface_partition_v1'] = dict(layout, role='remainder', surface=0)
    document['meshes'][1]['extras']['rabbitlands_surface_partition_v1'] = dict(
        layout, role='selected', surface=0, reference_skin=copy.deepcopy(profile['mount_skin']))
    document['asset'].setdefault('extras', {})['rabbitlands_storage_pilot'] = (
        'Root-rigid source islands split; mounted original skin retained as metadata; source ' + profile['source_sha256'])
    document, buffer, packing = compact(document, buffer)
    write_glb(output, document, buffer)
    return {'source_sha256': digest(source), 'candidate_sha256': digest(output),
            'source_bytes': source.stat().st_size, 'candidate_bytes': output.stat().st_size,
            'original_vertices': count, 'soft_vertices': len(soft), 'rigid_vertices': len(rigid),
            'targets': len(primitive['targets']), 'packing': packing,
            'all_candidate_original_vertex_ids': np.r_[soft, rigid].tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = pack(args.source, json.loads(args.profile.read_text()), args.output)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('CRYSTALBACK_PACKED', report['source_bytes'], report['candidate_bytes'])


if __name__ == '__main__':
    main()
