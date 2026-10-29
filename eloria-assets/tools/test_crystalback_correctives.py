"""Small adversarial fixtures for the partial corrective packer."""
import numpy as np
import pytest
from types import SimpleNamespace

from pack_crystalback_correctives import pack
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.runtime_validation import surface_sampler


def source_fixture(tmp_path):
    document = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}],
                'bufferViews': [], 'accessors': [], 'scenes': [{'nodes': [2]}], 'scene': 0,
                'nodes': [{'name': 'Root'}, {'name': 'Body', 'mesh': 0, 'skin': 0},
                          {'name': 'Armature', 'children': [0, 1]}],
                'skins': [{'joints': [0]}], 'meshes': []}
    buffer = bytearray()

    def add(values, component, kind):
        values = np.ascontiguousarray(values)
        buffer.extend(b'\0' * (-len(buffer) % 4))
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(buffer), 'byteLength': values.nbytes})
        buffer.extend(values.tobytes())
        document['accessors'].append({'bufferView': len(document['bufferViews']) - 1,
                                      'componentType': component, 'type': kind, 'count': len(values)})
        return len(document['accessors']) - 1

    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 2, 0], [1, 2, 0], [0, 3, 0]], '<f4')
    attributes = {'POSITION': add(vertices, 5126, 'VEC3'),
                  'NORMAL': add(np.tile([0, 0, 1], (6, 1)).astype('<f4'), 5126, 'VEC3'),
                  'TEXCOORD_0': add(np.arange(12, dtype='<f4').reshape(6, 2), 5126, 'VEC2'),
                  'JOINTS_0': add(np.zeros((6, 4), 'u1'), 5121, 'VEC4'),
                  'WEIGHTS_0': add(np.tile([1, 0, 0, 0], (6, 1)).astype('<f4'), 5126, 'VEC4')}
    target = add(vertices * .01, 5126, 'VEC3')
    indices = add(np.arange(6, dtype='<u2').reshape(-1, 1), 5123, 'SCALAR')
    document['meshes'] = [{'primitives': [{'attributes': attributes, 'indices': indices,
                                          'targets': [{'POSITION': target}]}]}]
    source = tmp_path / 'source.glb'
    write_glb(source, document, buffer)
    skin = np.tile([0, 0, 0, 0, 65535, 0, 0, 0], (3, 1)).astype('<u2').tobytes()
    profile = {'source_sha256': digest(source), 'root_bone_node': 0, 'mesh_node': 1, 'mesh_parent': 2,
               'rigid_original_vertex_ids': [3, 4, 5], 'coat_pattern_height': 3.0,
               'mount_skin': {'source_sha256': digest(source), 'layout': 'godot-four-influences-u16-v1',
                              'bind_names': ['Root'], 'skin_hex': skin.hex()}}
    return source, profile


def test_split_preserves_storage_topology_and_corrective_subset(tmp_path):
    source, profile = source_fixture(tmp_path)
    output = tmp_path / 'result.glb'
    result = pack(source, profile, output)
    old, ob = read_glb(source)
    new, nb = read_glb(output)
    assert result['all_candidate_original_vertex_ids'] == list(range(6))
    assert new['nodes'][:3] == old['nodes'][:2] + [dict(old['nodes'][2], children=[0, 1, 3])]
    for part, ids in zip(new['meshes'], [np.arange(3), np.arange(3, 6)]):
        primitive = part['primitives'][0]
        for name in ['POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0']:
            index = primitive['attributes'][name]
            original_index = old['meshes'][0]['primitives'][0]['attributes'][name]
            assert new['accessors'][index]['componentType'] == old['accessors'][original_index]['componentType']
            np.testing.assert_array_equal(accessor(new, nb, index), accessor(old, ob, original_index)[ids])
        np.testing.assert_array_equal(accessor(new, nb, primitive['indices']).ravel(), np.arange(3))
        assert part['extras']['rabbitlands_coat_pattern_height'] == 3.0
    assert 'targets' not in new['meshes'][1]['primitives'][0]
    target = new['meshes'][0]['primitives'][0]['targets'][0]['POSITION']
    original_target = old['meshes'][0]['primitives'][0]['targets'][0]['POSITION']
    np.testing.assert_array_equal(accessor(new, nb, target), accessor(old, ob, original_target)[:3])
    assert new['meshes'][1]['extras']['rabbitlands_mount_skin_v1'] == profile['mount_skin']


@pytest.mark.parametrize('change', ['hash', 'duplicate', 'range', 'triangle', 'skin_size', 'skin_joint', 'skin_weight'])
def test_rejects_incompatible_profiles(tmp_path, change):
    source, profile = source_fixture(tmp_path)
    if change == 'hash': profile['source_sha256'] = '0' * 64
    if change == 'duplicate': profile['rigid_original_vertex_ids'] = [3, 3, 5]
    if change == 'range': profile['rigid_original_vertex_ids'] = [3, 4, 6]
    if change == 'triangle': profile['rigid_original_vertex_ids'] = [2, 4, 5]
    if change == 'skin_size': profile['mount_skin']['skin_hex'] = '00'
    if change == 'skin_joint': profile['mount_skin']['skin_hex'] = '0100' + profile['mount_skin']['skin_hex'][4:]
    if change == 'skin_weight': profile['mount_skin']['skin_hex'] = '00' * 48
    with pytest.raises(ValueError): pack(source, profile, tmp_path / 'result.glb')


def test_input_cannot_be_overwritten(tmp_path):
    source, profile = source_fixture(tmp_path)
    before = source.read_bytes()
    with pytest.raises(ValueError): pack(source, profile, source)
    assert source.read_bytes() == before


def test_physical_probe_order_survives_a_mesh_split():
    asset = SimpleNamespace(parts=[
        {'node': 0, 'position': np.array([[0, 0, 0, 1], [1, 0, 0, 1], [2, 0, 0, 1]], float), 'targets': []},
        {'node': 1, 'position': np.array([[3, 0, 0, 1], [4, 0, 0, 1]], float), 'targets': []}])
    world = np.array([np.eye(4), np.eye(4)])
    result = surface_sampler(asset, [4, 0, 3, 2])(world, {})
    np.testing.assert_array_equal(result[:, 0], [4, 0, 3, 2])
    with pytest.raises(ValueError): surface_sampler(asset, [5])
    with pytest.raises(ValueError): surface_sampler(asset, [-1])
