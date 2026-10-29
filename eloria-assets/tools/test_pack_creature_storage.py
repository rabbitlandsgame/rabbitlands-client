"""Candidate generation safety and exact packing composition."""
import numpy as np
import pytest

from pack_creature_storage import prepare
from test_crystalback_correctives import source_fixture
from video_motion.asset import read_glb, write_glb, accessor
from video_motion.packing import append_array, compact


def test_candidate_generation_keeps_original_immutable(tmp_path):
    source, old_profile = source_fixture(tmp_path)
    original = source.read_bytes()
    output = tmp_path / 'candidate.glb'
    profile = {'source_sha256': old_profile['source_sha256'], 'source_node': 1, 'primitive': 0,
               'vertex_ids': [3, 4, 5], 'mode': 'preserve_skin', 'coat_pattern_height': 3.0}
    report = prepare(source, output, profile)
    assert source.read_bytes() == original
    assert 'skipped' in report['partition']  # all source weights/defaults are zero
    d, _ = read_glb(output)
    assert len(d['meshes']) == 1
    assert 'targets' not in d['meshes'][0]['primitives'][0]
    assert report['source_sha256'] != report['candidate_sha256']
    with pytest.raises(ValueError): prepare(source, source)
    profile['source_sha256'] = '0' * 64
    with pytest.raises(ValueError): prepare(source, output, profile)


def test_compaction_preserves_signed_zero_inside_constant_numeric_values():
    d = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}], 'bufferViews': [], 'accessors': [],
         'nodes': [{'name': 'Root'}], 'animations': []}
    b = bytearray()
    clock = append_array(d, b, np.array([[0], [.5], [1]]), 'SCALAR')
    values = np.array([[0., 0., 0.], [-0., 0., 0.], [0., 0., 0.]], '<f4')
    index = append_array(d, b, values, 'VEC3')
    d['animations'] = [{'name': 'Held', 'channels': [{'target': {'node': 0, 'path': 'translation'}, 'sampler': 0}],
                        'samplers': [{'input': clock, 'output': index}]}]
    packed, binary, report = compact(d, b)
    assert report['constant_samplers_collapsed'] == 0
    output = packed['animations'][0]['samplers'][0]['output']
    assert accessor(packed, binary, output).astype('<f4').tobytes() == values.tobytes()


def test_original_presentation_bounds_are_hash_bound_metadata(tmp_path):
    source, profile = source_fixture(tmp_path)
    bounds = {'source_sha256': profile['source_sha256'], 'meshes': [
        {'source_node': 1, 'position': [-1., -2., -3.], 'size': [4., 5., 6.]}]}
    candidate = tmp_path / 'bounded.glb'
    prepare(source, candidate, bounds=bounds)
    document, _ = read_glb(candidate)
    extras = document['meshes'][0]['extras']
    assert extras['rabbitlands_actor_bounds_v1'] == {'position': [-1., -2., -3.], 'size': [4., 5., 6.]}
    assert extras['rabbitlands_coat_pattern_height'] == 5.
    bounds['source_sha256'] = '0' * 64
    with pytest.raises(ValueError): prepare(source, candidate, bounds=bounds)


def test_invalid_original_presentation_bounds_are_rejected(tmp_path):
    source, profile = source_fixture(tmp_path)
    for span in [[-1, 2, 3], [0, 0, 0], [float('inf'), 1, 1], [True, 1, 1], [1e300, 1, 1]]:
        bounds = {'source_sha256': profile['source_sha256'], 'meshes': [
            {'source_node': 1, 'position': [0, 0, 0], 'size': span}]}
        with pytest.raises(ValueError): prepare(source, tmp_path / 'bad.glb', bounds=bounds)


@pytest.mark.parametrize('use_profile', [False, True])
def test_preserve_trs_option_survives_all_compaction_stages(tmp_path, use_profile):
    from test_partial_correctives import fixture
    from video_motion.asset import digest
    d, b, profile = fixture(tmp_path)
    clock = append_array(d, b, np.arange(5, dtype='<f4')[:, None], 'SCALAR')
    value = append_array(d, b, np.zeros((5, 3), '<f4'), 'VEC3')
    weights = append_array(d, b, np.ones((5, 1), '<f4'), 'SCALAR')
    d['animations'] = [{'name': 'Held', 'channels': [
        {'target': {'node': 0, 'path': 'translation'}, 'sampler': 0},
        {'target': {'node': 1, 'path': 'weights'}, 'sampler': 1}],
        'samplers': [{'input': clock, 'output': value}, {'input': clock, 'output': weights}]}]
    d['buffers'][0]['byteLength'] = len(b)
    source = tmp_path / 'animated.glb'
    write_glb(source, d, b)
    profile['source_sha256'] = digest(source)
    profile['preserve_trs_keys'] = use_profile
    result = tmp_path / 'result.glb'
    report = prepare(source, result, profile, preserve_trs_keys=not use_profile)
    nd, nb = read_glb(result)
    samplers = nd['animations'][0]['samplers']
    assert len(accessor(nd, nb, samplers[0]['input'])) == 5
    assert len(accessor(nd, nb, samplers[1]['input'])) == 2
    assert report['preserve_trs_keys'] and report['partition']
    assert report['partition']['packing']['constant_samplers_collapsed'] == 0
    assert report['packing']['constant_samplers_collapsed'] == 0
    ordinary = tmp_path / 'ordinary.glb'
    profile.pop('preserve_trs_keys')
    prepare(source, ordinary, profile)
    od, ob = read_glb(ordinary)
    assert len(accessor(od, ob, od['animations'][0]['samplers'][0]['input'])) == 2
