"""Exact attribute/skin preservation and conservative partition boundaries."""
import copy

import numpy as np
import pytest

from test_crystalback_correctives import source_fixture
from video_motion.asset import read_glb
from video_motion.partial_correctives import raw_array, split_corrective_partition


def fixture(tmp_path, zero=True):
    path, _ = source_fixture(tmp_path)
    document, binary = read_glb(path)
    binary = bytearray(binary)
    target = document['meshes'][0]['primitives'][0]['targets'][0]['POSITION']
    spec = document['accessors'][target]
    view = document['bufferViews'][spec['bufferView']]
    if zero:
        np.ndarray((6, 3), '<f4', binary, offset=view['byteOffset'])[3:] = 0
    profile = {'source_node': 1, 'primitive': 0, 'vertex_ids': [3, 4, 5],
               'mode': 'preserve_skin', 'coat_pattern_height': 3.125}
    return document, binary, profile


def test_zero_partition_preserves_geometry_skin_and_target_bits(tmp_path):
    d, b, profile = fixture(tmp_path)
    original = copy.deepcopy(d)
    new, blob, report = split_corrective_partition(d, b, profile)
    assert d == original
    assert report['all_candidate_original_vertex_ids'] == list(range(6))
    assert new['nodes'][1] == d['nodes'][1]
    assert new['nodes'][2]['children'] == [0, 1, 3]
    old = d['meshes'][0]['primitives'][0]
    for mesh, ids in zip(new['meshes'], [np.arange(3), np.arange(3, 6)]):
        assert mesh['extras']['rabbitlands_coat_pattern_height'] == 3.125
        primitive = mesh['primitives'][0]
        for field, old_index in old['attributes'].items():
            index = primitive['attributes'][field]
            assert new['accessors'][index]['componentType'] == d['accessors'][old_index]['componentType']
            assert raw_array(new, blob, index).tobytes() == raw_array(d, b, old_index)[ids].tobytes()
    assert 'targets' not in new['meshes'][1]['primitives'][0]
    assert 'weights' not in new['nodes'][3]
    target = new['meshes'][0]['primitives'][0]['targets'][0]['POSITION']
    assert raw_array(new, blob, target).tobytes() == raw_array(d, b, old['targets'][0]['POSITION'])[:3].tobytes()


def test_raw_normalized_integer_storage_is_not_rounded():
    values = np.array([[1, 32768], [65535, 12345]], '<u2')
    d = {'accessors': [{'componentType': 5123, 'count': 2, 'type': 'VEC2', 'normalized': True, 'bufferView': 0}],
         'bufferViews': [{'buffer': 0, 'byteLength': values.nbytes}]}
    assert raw_array(d, values.tobytes(), 0).tobytes() == values.tobytes()


@pytest.mark.parametrize('change', ['nonzero', 'triangle', 'duplicate', 'order', 'whole', 'mode', 'height', 'shared'])
def test_unsafe_partitions_fail_closed(tmp_path, change):
    d, b, p = fixture(tmp_path, zero=change != 'nonzero')
    if change == 'triangle': p['vertex_ids'] = [2, 4, 5]
    if change == 'duplicate': p['vertex_ids'] = [3, 3, 5]
    if change == 'order': p['vertex_ids'] = [5, 4, 3]
    if change == 'whole': p['vertex_ids'] = list(range(6))
    if change == 'mode': p['mode'] = 'guess'
    if change == 'height': p['coat_pattern_height'] = float('nan')
    if change == 'shared': d['nodes'].append(dict(d['nodes'][1]))
    with pytest.raises(ValueError): split_corrective_partition(d, b, p)


def test_arbitrary_existing_owner_keeps_source_hierarchy(tmp_path):
    d, b, p = fixture(tmp_path, zero=False)
    p.update(mode='rigid', owner_joint=0)
    new, blob, _ = split_corrective_partition(d, b, p)
    pr = new['meshes'][1]['primitives'][0]
    assert np.all(raw_array(new, blob, pr['attributes']['JOINTS_0']) == 0)
    np.testing.assert_array_equal(raw_array(new, blob, pr['attributes']['WEIGHTS_0']), np.tile([1, 0, 0, 0], (3, 1)))
    assert new['skins'] == d['skins']


def test_eight_influence_attributes_are_retained(tmp_path):
    d, b, p = fixture(tmp_path)
    pr = d['meshes'][0]['primitives'][0]
    for field, values, component in [('JOINTS_1', np.zeros((6, 4), 'u1'), 5121), ('WEIGHTS_1', np.tile([.5, 0, 0, 0], (6, 1)).astype('<f4'), 5126)]:
        b.extend(b'\0' * (-len(b) % 4))
        d['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': values.nbytes})
        b.extend(values.tobytes())
        d['accessors'].append({'bufferView': len(d['bufferViews']) - 1, 'componentType': component, 'count': 6, 'type': 'VEC4'})
        pr['attributes'][field] = len(d['accessors']) - 1
    new, blob, _ = split_corrective_partition(d, b, p)
    free = new['meshes'][1]['primitives'][0]
    assert raw_array(new, blob, free['attributes']['JOINTS_1']).dtype == np.dtype('u1')
    np.testing.assert_array_equal(raw_array(new, blob, free['attributes']['WEIGHTS_1']), np.tile([.5, 0, 0, 0], (3, 1)))
