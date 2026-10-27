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
