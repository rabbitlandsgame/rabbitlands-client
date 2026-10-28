"""Roundoff-free flat-run reduction, including scalar morph frame layout."""
import copy

import numpy as np
import pytest

from video_motion.asset import accessor
from video_motion.exact_animation_packing import reduce_constant_runs


def fixture(values, path='translation', interpolation='LINEAR', clock=None):
    values = np.asarray(values, dtype='<f4')
    if values.ndim == 1: values = values[:, None]
    clock = np.asarray(np.arange(len(values)) if clock is None else clock, dtype='<f4')[:, None]
    if path == 'weights': stored = values.reshape(-1, 1)
    else: stored = values
    document = {'buffers': [{'byteLength': 0}], 'bufferViews': [], 'accessors': [],
                'animations': [{'name': 'Test', 'channels': [{'sampler': 0, 'target': {'node': 0, 'path': path}}],
                                'samplers': [{'input': 0, 'output': 1, 'interpolation': interpolation}]}]}
    binary = bytearray()
    for array in [clock, stored]:
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': array.nbytes})
        document['accessors'].append({'bufferView': len(document['bufferViews']) - 1, 'componentType': 5126,
                                      'count': len(array), 'type': {1: 'SCALAR', 3: 'VEC3', 4: 'VEC4'}[array.shape[1]]})
        binary.extend(array.tobytes())
    document['buffers'][0]['byteLength'] = len(binary)
    return document, binary


@pytest.mark.parametrize('interpolation', ['LINEAR', 'STEP'])
def test_flat_run_keeps_both_boundaries_and_all_values(interpolation):
    values = np.array([[0, 0, 0], [1, 0, 0], [1, 0, 0], [1, 0, 0],
                       [1, 0, 0], [2, 0, 0], [2, 0, 0], [2, 0, 0]], '<f4')
    d, b = fixture(values, interpolation=interpolation)
    original = copy.deepcopy(d); original_bytes = bytes(b)
    packed, blob, report = reduce_constant_runs(d, b)
    sampler = packed['animations'][0]['samplers'][0]
    times = accessor(packed, blob, sampler['input']).ravel()
    np.testing.assert_array_equal(times, [0, 1, 4, 5, 7])
    retained = accessor(packed, blob, sampler['output'])
    np.testing.assert_array_equal(retained, values[[0, 1, 4, 5, 7]])
    if interpolation == 'LINEAR':
        probe = np.unique(np.r_[np.arange(8), np.arange(7) + .5, [.127, 3.765, 6.314]])
        for axis in range(3):
            np.testing.assert_array_equal(np.interp(probe, times, retained[:, axis]),
                                          np.interp(probe, np.arange(8), values[:, axis]))
    assert report['removed_keys'] == 3
    assert d == original and bytes(b) == original_bytes
    assert bytes(blob[:len(b)]) == bytes(b)


def test_flattened_morph_weights_are_compared_as_complete_frames():
    values = [[1, 0], [1, 0], [1, 0], [0, 1], [0, 1], [0, 1]]
    d, b = fixture(values, path='weights')
    packed, blob, report = reduce_constant_runs(d, b)
    sampler = packed['animations'][0]['samplers'][0]
    np.testing.assert_array_equal(accessor(packed, blob, sampler['input']).ravel(), [0, 2, 3, 5])
    np.testing.assert_array_equal(accessor(packed, blob, sampler['output']).reshape(-1, 2),
                                  np.asarray(values)[[0, 2, 3, 5]])
    assert report['removed_keys'] == 2


@pytest.mark.parametrize('path,expected', [('translation', 0), ('rotation', 0), ('scale', 0), ('weights', 3)])
def test_path_filter_preserves_original_trs_rows(path, expected):
    values = np.ones((5, 4 if path == 'rotation' else 3), '<f4')
    d, b = fixture(values, path=path)
    packed, blob, report = reduce_constant_runs(d, b, paths={'weights'})
    assert report['removed_keys'] == expected
    sampler = packed['animations'][0]['samplers'][0]
    if not expected:
        assert packed == d and bytes(blob) == bytes(b)
        assert sampler['input'] == 0 and sampler['output'] == 1


def test_path_filter_does_not_reduce_sampler_shared_with_joint_path():
    d, b = fixture(np.ones((5, 3), '<f4'), path='translation')
    d['animations'][0]['channels'].append({'sampler': 0, 'target': {'node': 1, 'path': 'weights'}})
    packed, blob, report = reduce_constant_runs(d, b, paths={'weights'})
    assert report['removed_keys'] == 0 and packed == d and bytes(blob) == bytes(b)


def test_signed_zero_transition_is_preserved_bit_for_bit():
    d, b = fixture(np.array([0., 0., -0., -0., -0., 1.], '<f4'))
    packed, blob, report = reduce_constant_runs(d, b)
    sampler = packed['animations'][0]['samplers'][0]
    times = accessor(packed, blob, sampler['input']).ravel()
    np.testing.assert_array_equal(times, [0, 1, 2, 4, 5])
    index = sampler['output']; spec = packed['accessors'][index]
    view = packed['bufferViews'][spec['bufferView']]
    bits = np.frombuffer(blob, '<u4', spec['count'], view['byteOffset'])
    np.testing.assert_array_equal(bits, np.array([0., 0., -0., -0., 1.], '<f4').view('<u4'))
    assert report['removed_keys'] == 1


def test_constant_rotation_keeps_clip_endpoint_timestamps():
    d, b = fixture(np.tile([0, 0, 0, 1], (7, 1)), path='rotation')
    packed, blob, report = reduce_constant_runs(d, b)
    sampler = packed['animations'][0]['samplers'][0]
    np.testing.assert_array_equal(accessor(packed, blob, sampler['input']).ravel(), [0, 6])
    assert report['removed_keys'] == 5


def test_cubic_spline_is_unchanged():
    d, b = fixture(np.zeros((5, 3)), interpolation='CUBICSPLINE')
    packed, blob, report = reduce_constant_runs(d, b)
    assert packed == d and bytes(blob) == bytes(b) and report['removed_keys'] == 0


def test_nonflat_curves_are_unchanged():
    d, b = fixture([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]])
    packed, blob, report = reduce_constant_runs(d, b)
    assert packed == d and bytes(blob) == bytes(b) and report['removed_keys'] == 0


def test_duplicate_key_times_fail_closed():
    d, b = fixture(np.zeros((4, 3)), clock=[0, 1, 1, 2])
    with pytest.raises(ValueError, match='strictly increasing'): reduce_constant_runs(d, b)
