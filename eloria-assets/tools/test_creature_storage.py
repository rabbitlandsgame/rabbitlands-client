"""Proof-oriented fixtures for exact corrective target pruning."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion.creature_storage import _array, prune_zero_targets


def fixture():
    d = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}],
         'bufferViews': [], 'accessors': [], 'nodes': [], 'meshes': [],
         'animations': [], 'images': [], 'skins': []}
    b = bytearray()

    def add(values, kind='SCALAR', component=5126):
        values = np.ascontiguousarray(values, dtype={5126: '<f4', 5121: 'u1'}[component])
        b.extend(b'\0' * (-len(b) % 4))
        d['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': values.nbytes})
        b.extend(values.tobytes())
        d['accessors'].append({'bufferView': len(d['bufferViews']) - 1,
                               'componentType': component, 'type': kind, 'count': len(values)})
        return len(d['accessors']) - 1

    position = add([[0., -0., 0.], [1., 0., 0.], [0., 1., 0.]], 'VEC3')
    joint = add([[0, 1, 2, 3]] * 3, 'VEC4', 5121)
    normal = add([[0., 0., 1.]] * 3, 'VEC3')
    targets = [{'POSITION': add(np.full((3, 3), amount), 'VEC3'),
                'NORMAL': normal} for amount in [.125, .25, .5]]
    d['meshes'] = [{'weights': [0., 0., 0.], 'extras': {'targetNames': ['unused-a', 'active', 'unused-b'], 'other': 42},
                     'primitives': [{'attributes': {'POSITION': position, 'JOINTS_0': joint, 'NORMAL': normal}, 'targets': targets}]}]
    d['nodes'] = [{'mesh': 0, 'weights': [0., 0., 0.], 'translation': [0., 0., 0.]}]
    clock = add([[0.], [.25], [1.]])
    weight = add([[0.], [0.], [-0.], [0.], [.7], [0.], [0.], [-.2], [0.]])
    move = add([[0., -0., 0.]] * 3, 'VEC3')
    d['animations'] = [{'name': 'Motion', 'samplers': [
        {'input': clock, 'output': weight, 'interpolation': 'LINEAR'},
        {'input': clock, 'output': move, 'interpolation': 'LINEAR'}],
        'channels': [{'sampler': 0, 'target': {'node': 0, 'path': 'weights'}},
                     {'sampler': 1, 'target': {'node': 0, 'path': 'translation'}}]}]
    d['buffers'][0]['byteLength'] = len(b)
    return d, b, add


def channel_values(d, b, animation, path, node=0):
    a = d['animations'][animation]
    ch = next(ch for ch in a['channels'] if ch['target'] == {'node': node, 'path': path})
    sampler = a['samplers'][ch['sampler']]
    return _array(d, b, sampler['input']), _array(d, b, sampler['output'])


def test_exact_zero_removal_preserves_retained_bits_and_original_inputs():
    d, b, _ = fixture()
    original = copy.deepcopy(d), bytes(b)
    nd, nb, report = prune_zero_targets(d, b)
    assert d == original[0] and bytes(b) == original[1]
    assert report['meshes'][0]['removed_target_indices'] == [0, 2]
    assert nd['meshes'][0]['extras'] == {'targetNames': ['active'], 'other': 42}
    assert nd['meshes'][0]['weights'] == nd['nodes'][0]['weights'] == [0.]
    old_times, old_motion = channel_values(d, b, 0, 'translation')
    new_times, new_motion = channel_values(nd, nb, 0, 'translation')
    assert old_times.tobytes() == new_times.tobytes()  # Do not collapse a constant track.
    assert old_motion.tobytes() == new_motion.tobytes()  # Includes negative zero.
    old_clock, old_weights = channel_values(d, b, 0, 'weights')
    new_clock, new_weights = channel_values(nd, nb, 0, 'weights')
    assert old_clock.tobytes() == new_clock.tobytes()
    assert old_weights.reshape(3, 3)[:, [1]].tobytes() == new_weights.tobytes()
    for key, old_index in d['meshes'][0]['primitives'][0]['attributes'].items():
        new_index = nd['meshes'][0]['primitives'][0]['attributes'][key]
        assert _array(d, b, old_index).tobytes() == _array(nd, nb, new_index).tobytes()
        assert d['accessors'][old_index]['componentType'] == nd['accessors'][new_index]['componentType']
    for key, old_index in d['meshes'][0]['primitives'][0]['targets'][1].items():
        new_index = nd['meshes'][0]['primitives'][0]['targets'][0][key]
        assert _array(d, b, old_index).tobytes() == _array(nd, nb, new_index).tobytes()
    assert len(nb) < len(b)


def test_any_instanced_node_or_mesh_default_prevents_removal():
    d, b, _ = fixture()
    d['nodes'].append({'mesh': 0, 'weights': [1., 0., 0.]})
    d['meshes'][0]['weights'][2] = .5
    nd, nb, report = prune_zero_targets(d, b)
    assert not report['changed'] and nd == d and bytes(nb) == bytes(b)


def test_shared_weight_sampler_is_split_for_different_mesh_masks():
    d, b, _ = fixture()
    d['meshes'].append(copy.deepcopy(d['meshes'][0]))
    d['meshes'][0]['weights'][0] = 1.
    d['meshes'][1]['weights'][2] = 1.
    d['nodes'].append({'mesh': 1})
    d['animations'][0]['channels'].append({'sampler': 0, 'target': {'node': 1, 'path': 'weights'}})
    nd, nb, _ = prune_zero_targets(d, b)
    for node, indices in [(0, [0, 1]), (1, [1, 2])]:
        expected = channel_values(d, b, 0, 'weights', node)[1].reshape(3, 3)[:, indices]
        actual = channel_values(nd, nb, 0, 'weights', node)[1]
        assert expected.tobytes() == actual.tobytes()


def test_all_targets_removed_retains_duration_with_exact_static_default():
    d, b, add = fixture()
    a = d['animations'][0]
    a['samplers'][0]['output'] = add(np.zeros((9, 1)))
    a['channels'] = a['channels'][:1]
    a['samplers'] = a['samplers'][:1]
    nd, nb, report = prune_zero_targets(d, b)
    assert 'targets' not in nd['meshes'][0]['primitives'][0]
    assert 'weights' not in nd['meshes'][0] and 'weights' not in nd['nodes'][0]
    assert 'targetNames' not in nd['meshes'][0]['extras']
    assert report['duration_anchors'] == [{'animation': 0, 'node': 0, 'path': 'translation', 'start': 0., 'end': 1.}]
    times, value = channel_values(nd, nb, 0, 'translation')
    np.testing.assert_array_equal(times[:, 0], [0., 1.])
    assert not value.any()
    assert report['removed_weight_values'] == 9


def test_duration_anchor_never_reuses_property_animated_by_another_clip():
    d, b, add = fixture()
    d['animations'][0]['samplers'][0]['output'] = add(np.zeros((9, 1)))
    d['animations'].append(copy.deepcopy(d['animations'][0]))
    d['animations'][1]['channels'] = d['animations'][1]['channels'][1:]
    d['animations'][0]['channels'] = d['animations'][0]['channels'][:1]
    with pytest.raises(ValueError, match='globally static'): prune_zero_targets(d, b)


@pytest.mark.parametrize('change', ['extension', 'undeclared_extension', 'sparse', 'cubic', 'nan', 'dimension', 'name_count', 'default', 'timestamps'])
def test_unsupported_or_invalid_evidence_is_rejected_without_input_mutation(change):
    d, b, add = fixture()
    if change == 'extension': d['extensionsUsed'] = ['EXT_mesh_gpu_instancing']
    if change == 'undeclared_extension': d['nodes'][0]['extensions'] = {'EXT_unknown': {'bufferView': 0}}
    if change == 'sparse': d['accessors'][0]['sparse'] = {'count': 1}
    if change == 'cubic': d['animations'][0]['samplers'][0]['interpolation'] = 'CUBICSPLINE'
    if change == 'nan': d['animations'][0]['samplers'][0]['output'] = add([[0.], [0.], [0.], [0.], [np.nan], [0.], [0.], [0.], [0.]])
    if change == 'dimension': d['animations'][0]['samplers'][0]['output'] = add([[0.], [0.]])
    if change == 'name_count': d['meshes'][0]['extras']['targetNames'] = ['wrong']
    if change == 'default': d['nodes'][0]['weights'] = [0., 1.]
    if change == 'timestamps': d['animations'][0]['samplers'][0]['input'] = add([[0.], [0.], [1.]])
    before = copy.deepcopy(d), bytes(b)
    with pytest.raises(ValueError): prune_zero_targets(d, b)
    assert d == before[0] and bytes(b) == before[1]


def test_multiple_primitives_and_embedded_image_are_retained():
    d, b, _ = fixture()
    d['meshes'][0]['primitives'].append(copy.deepcopy(d['meshes'][0]['primitives'][0]))
    payload = b'embedded image bytes\0\xff'
    b.extend(b'\0' * (-len(b) % 4));d['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': len(payload)})
    b.extend(payload);d['images'] = [{'bufferView': len(d['bufferViews']) - 1, 'mimeType': 'image/png'}]
    nd, nb, _ = prune_zero_targets(d, b)
    assert all(len(p['targets']) == 1 for p in nd['meshes'][0]['primitives'])
    view = nd['bufferViews'][nd['images'][0]['bufferView']]
    assert bytes(nb[view['byteOffset']:view['byteOffset'] + view['byteLength']]) == payload
