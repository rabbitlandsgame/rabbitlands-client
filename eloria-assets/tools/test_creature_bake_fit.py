"""Authoring bake invariants and independent-error reporting (no engine mocks)."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.creature_bake_fit import bake, _allowed
from video_motion.packing import append_array


def fixture(path, *, influences=4, correctives=True, dense=False, shared=False):
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}],
           'bufferViews': [], 'accessors': [],
           'nodes': [{'name': 'root', 'children': [1, 2]},
                     {'name': 'head', 'translation': [0, 1, 0]},
                     {'name': 'body', 'mesh': 0, 'skin': 0}],
           'skins': [{'joints': [0, 1]}], 'animations': [],
           'materials': [{'name': 'original', 'extras': {'never': 'change'}}]}
    blob = bytearray()
    pos = np.array([[0, 0, 0], [0, 1, 0], [.5, .5, 0]])
    attrs = {'POSITION': append_array(doc, blob, pos, 'VEC3'),
             'NORMAL': append_array(doc, blob, np.tile([0, 0, 1.], (3, 1)), 'VEC3'),
             'TANGENT': append_array(doc, blob, np.tile([1., 0, 0, -1], (3, 1)), 'VEC4'),
             'TEXCOORD_0': append_array(doc, blob, pos[:, :2], 'VEC2')}
    for k in range(influences // 4):
        values = np.tile([0, 1, 0, 0], (3, 1)).astype('<u2')
        blob.extend(b'\0' * (-len(blob) % 4))
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': values.nbytes})
        blob.extend(values.tobytes())
        doc['accessors'].append({'bufferView': len(doc['bufferViews']) - 1,
                                 'componentType': 5123, 'count': 3, 'type': 'VEC4'})
        attrs[f'JOINTS_{k}'] = len(doc['accessors']) - 1
        weights = np.tile([.7, .3, 0, 0] if not k else [0, 0, 0, 0], (3, 1))
        attrs[f'WEIGHTS_{k}'] = append_array(doc, blob, weights, 'VEC4')
    binds = np.tile(np.eye(4), (2, 1, 1))
    binds[1, 1, 3] = -1
    doc['skins'][0]['inverseBindMatrices'] = append_array(doc, blob,
        binds.transpose(0, 2, 1).reshape(2, 16), 'MAT4')
    soft = {'attributes': attrs, 'material': 0}
    if correctives:
        soft['targets'] = [{'POSITION': append_array(doc, blob,
            np.tile([.01, 0, 0], (3, 1)), 'VEC3')}]
    # Same mesh, an untouched morph-free primitive with its own attribute graph.
    shell = copy.deepcopy(soft)
    shell.pop('targets', None)
    shell['attributes']['POSITION'] = append_array(doc, blob, pos + [0, 0, .3], 'VEC3')
    doc['meshes'] = [{'primitives': [soft, shell], 'extras': {
        'rabbitlands_actor_bounds_v1': {'position': [0, 0, 0], 'size': [.5, 1, .3]},
        'rabbitlands_mount_skin_v1': {'must': 'survive'}}}]
    if correctives:
        doc['meshes'][0]['weights'] = [1.]
        doc['meshes'][0]['extras']['targetNames'] = ['corrective']
    if shared:
        doc['nodes'].append({'name': 'second_body', 'mesh': 0, 'skin': 0})
    times = append_array(doc, blob, np.array([0, 1, 2])[:, None] / (60 if dense else 30), 'SCALAR')
    for name in ('Fly', 'Gallop'):
        outputs = append_array(doc, blob, np.array([[0, 1, 0], [.1, 1, 0], [0, 1, 0]]), 'VEC3')
        samplers = [{'input': times, 'output': outputs}]
        channels = [{'target': {'node': 1, 'path': 'translation'}, 'sampler': 0}]
        if correctives:
            samplers.append({'input': times, 'output': append_array(doc, blob,
                np.ones((3, 1)), 'SCALAR')})
            for node in (2, 3) if shared else (2,):
                channels.append({'target': {'node': node, 'path': 'weights'}, 'sampler': 1})
        doc['animations'].append({'name': name, 'samplers': samplers, 'channels': channels})
    write_glb(path, doc, blob)
    return path


@pytest.mark.parametrize('influences', [4, 8])
def test_fit_removes_shapes_preserves_shell_curves_and_unsigned_palette(tmp_path, influences):
    source = fixture(tmp_path / 'source.glb', influences=influences)
    before = digest(source)
    result = bake(source, tmp_path / 'candidate.glb', iterations=1,
                  report=tmp_path / 'report.json')
    assert digest(source) == before
    assert result['source_preserved'] and not result['actual_engine_validated']
    assert result['acceptance_threshold_assumed'] is None
    assert result['whole_surface']['independent']['maximum_position'] < 1e-6
    assert result['whole_surface']['neutral']['maximum_position'] < 1e-6
    assert result['whole_surface']['crossfade']['maximum_position'] < 1e-6
    assert any('Fly->Gallop' in label for label in result['independent_labels'])
    assert result['primitive_reports'][1]['status'] == 'morph_free_untouched'
    doc, blob = read_glb(tmp_path / 'candidate.glb')
    mesh = doc['meshes'][doc['nodes'][2]['mesh']]
    assert not mesh['primitives'][0].get('targets')
    assert mesh['extras']['rabbitlands_mount_skin_v1'] == {'must': 'survive'}
    assert 'targetNames' not in mesh['extras']
    attrs = mesh['primitives'][0]['attributes']
    weights = []
    for k in range(influences // 4):
        assert doc['accessors'][attrs[f'JOINTS_{k}']]['componentType'] == 5123
        assert accessor(doc, blob, attrs[f'JOINTS_{k}']).shape == (3, 4)
        weights.append(accessor(doc, blob, attrs[f'WEIGHTS_{k}']))
    weights = np.concatenate(weights, axis=1)
    assert np.all(weights >= 0) and np.allclose(weights.sum(1), 1)
    assert all(c['target']['path'] != 'weights' for a in doc['animations'] for c in a['channels'])
    with pytest.raises(FileExistsError):
        bake(source, tmp_path / 'candidate.glb')


def test_already_baked_is_an_exact_copy_without_skin_recomputation(tmp_path):
    source = fixture(tmp_path / 'source.glb', correctives=False, dense=True)
    result = bake(source, tmp_path / 'copy.glb')
    assert result['status'] == 'already_baked'
    assert not result['skin_recomputed']
    assert source.read_bytes() == (tmp_path / 'copy.glb').read_bytes()


def test_dense_source_rejected_without_silent_resampling(tmp_path):
    source = fixture(tmp_path / 'dense.glb', dense=True)
    with pytest.raises(ValueError, match='already-30-Hz'):
        bake(source, tmp_path / 'candidate.glb')
    assert not (tmp_path / 'candidate.glb').exists()


def test_shared_mesh_instances_and_original_skin_fallback(tmp_path):
    source = fixture(tmp_path / 'source.glb', shared=True)
    report = bake(source, tmp_path / 'candidate.glb', iterations=0, fit_skin=False)
    doc, blob = read_glb(tmp_path / 'candidate.glb')
    original, raw = read_glb(source)
    assert doc['nodes'][2]['mesh'] != doc['nodes'][3]['mesh']
    for ni in (2, 3):
        attrs = doc['meshes'][doc['nodes'][ni]['mesh']]['primitives'][0]['attributes']
        old = original['meshes'][0]['primitives'][0]['attributes']
        for field in ('JOINTS_0', 'WEIGHTS_0'):
            assert np.array_equal(accessor(doc, blob, attrs[field]), accessor(original, raw, old[field]))
    assert report['whole_surface']['independent']['maximum_position'] < 1e-6


def test_rest_coincidence_does_not_weld_different_corrected_trajectories(tmp_path):
    source = fixture(tmp_path / 'source.glb')
    doc, raw = read_glb(source)
    blob = bytearray(raw)
    prim = doc['meshes'][0]['primitives'][0]
    # Two rest-coincident vertices have different full POSITION-delta columns.
    prim['attributes']['POSITION'] = append_array(doc, blob, np.array([[0, 0, 0], [0, 0, 0], [0, 1, 0]]), 'VEC3')
    prim['targets'][0]['POSITION'] = append_array(doc, blob, np.array([[.01, 0, 0], [-.01, 0, 0], [0, 0, 0]]), 'VEC3')
    write_glb(source, doc, blob)
    report = bake(source, tmp_path / 'candidate.glb', iterations=0)
    assert report['primitive_reports'][0]['fit']['independent_fit_groups'] == 3
    candidate, raw = read_glb(tmp_path / 'candidate.glb')
    prim = candidate['meshes'][candidate['nodes'][2]['mesh']]['primitives'][0]
    positions = accessor(candidate, raw, prim['attributes']['POSITION'])
    assert np.linalg.norm(positions[0] - positions[1]) > .019


def test_local_weight_fit_reproduces_a_dynamic_corrective(tmp_path):
    source = fixture(tmp_path / 'source.glb')
    doc, raw = read_glb(source)
    blob = bytearray(raw)
    prim = doc['meshes'][0]['primitives'][0]
    prim['attributes']['WEIGHTS_0'] = append_array(doc, blob, np.tile([1., 0, 0, 0], (3, 1)), 'VEC4')
    prim['targets'][0]['POSITION'] = append_array(doc, blob, np.tile([.02, 0, 0], (3, 1)), 'VEC3')
    doc['meshes'][0]['weights'] = [0.]
    for animation in doc['animations']:
        sampler = animation['samplers'][1]
        sampler['output'] = append_array(doc, blob, np.array([[0.], [1.], [0.]]), 'SCALAR')
    write_glb(source, doc, blob)
    report = bake(source, tmp_path / 'candidate.glb', iterations=4)
    fit = report['primitive_reports'][0]
    assert fit['independent']['all']['maximum_position'] < .1 * fit['original_skin_fallback']['all']['maximum_position']
    candidate, raw = read_glb(tmp_path / 'candidate.glb')
    attrs = candidate['meshes'][candidate['nodes'][2]['mesh']]['primitives'][0]['attributes']
    joints = accessor(candidate, raw, attrs['JOINTS_0'])
    weights = accessor(candidate, raw, attrs['WEIGHTS_0'])
    child_share = (weights * (joints == 1)).sum(1)
    assert np.allclose(child_share, .2, atol=.02)


def test_report_cannot_overwrite_source_or_output(tmp_path):
    source = fixture(tmp_path / 'source.glb')
    before = source.read_bytes()
    with pytest.raises(ValueError, match='Report must differ'):
        bake(source, tmp_path / 'candidate.glb', report=source)
    assert source.read_bytes() == before


def test_dense_step_opt_in_preserves_guard_clock_and_tests_both_boundary_sides(tmp_path):
    source = fixture(tmp_path / 'source.glb')
    doc, raw = read_glb(source)
    blob = bytearray(raw)
    times = np.array([[0], [.001], [1 / 30], [2 / 30]])
    for animation in doc['animations']:
        sampler = animation['samplers'][0]
        sampler['input'] = append_array(doc, blob, times, 'SCALAR')
        sampler['output'] = append_array(doc, blob, np.array([[0, 1, 0], [.1, 1, 0], [0, 1, 0], [.1, 1, 0]]), 'VEC3')
        sampler['interpolation'] = 'STEP'
    write_glb(source, doc, blob)
    with pytest.raises(ValueError, match='already-30-Hz'):
        bake(source, tmp_path / 'strict.glb')
    report = bake(source, tmp_path / 'candidate.glb', iterations=0, allow_step_exceptions=True)
    assert len(report['sampling']['step_exceptions']) == 2
    assert not report['sampling']['all_source_keys_at_most_30_hz']
    assert report['whole_surface']['step_boundary']['observations'] > 0
    candidate, raw = read_glb(tmp_path / 'candidate.glb')
    for animation in candidate['animations']:
        sampler = animation['samplers'][0]
        assert sampler['interpolation'] == 'STEP'
        assert np.array_equal(accessor(candidate, raw, sampler['input']), times.astype('f4'))


def test_static_corrective_and_zero_normals_are_reported_without_invented_directions(tmp_path):
    source = fixture(tmp_path / 'source.glb')
    doc, raw = read_glb(source)
    blob = bytearray(raw)
    doc['animations'] = []
    doc['meshes'][0]['primitives'][0]['attributes']['NORMAL'] = append_array(doc, blob, np.zeros((3, 3)), 'VEC3')
    write_glb(source, doc, blob)
    report = bake(source, tmp_path / 'candidate.glb', iterations=0)
    assert report['whole_surface']['off_grid']['observations'] == 0
    assert report['whole_surface']['neutral']['maximum_normal_degrees'] == 0
    candidate, raw = read_glb(tmp_path / 'candidate.glb')
    attrs = candidate['meshes'][candidate['nodes'][2]['mesh']]['primitives'][0]['attributes']
    assert not np.any(accessor(candidate, raw, attrs['NORMAL']))


def test_nearest_bone_segments_are_measured_in_mesh_local_space():
    from types import SimpleNamespace
    rest = np.tile(np.eye(4), (6, 1, 1))
    rest[:, 0, 3] = [102, 103, 104, .2, 20, 100]
    rest[5, :3, :3] *= 10
    asset = SimpleNamespace(parent=np.full(6, -1), rest=rest)
    part = {'node': 5, 'nodes': np.arange(5), 'position': np.array([[.2, 0, 0, 1]])}
    allowed = _allowed(asset, part, np.array([[0., 0, 0, 0, 1.]]))[0]
    assert set(allowed) == {0, 1, 2, 4}


def test_new_logical_bounds_include_original_morph_endpoint_envelope(tmp_path):
    source = fixture(tmp_path / 'source.glb')
    doc, raw = read_glb(source)
    blob = bytearray(raw)
    mesh = doc['meshes'][0]
    mesh['extras'].pop('rabbitlands_actor_bounds_v1')
    mesh['primitives'][0]['targets'][0]['POSITION'] = append_array(doc, blob,
        np.tile([.01, -.3, 0], (3, 1)), 'VEC3')
    write_glb(source, doc, blob)
    bake(source, tmp_path / 'candidate.glb', iterations=0)
    candidate, _ = read_glb(tmp_path / 'candidate.glb')
    mesh = candidate['meshes'][candidate['nodes'][2]['mesh']]
    bounds = mesh['extras']['rabbitlands_actor_bounds_v1']
    assert bounds['position'][1] == float(np.float32(-.3))
    assert bounds['size'][1] == float(np.float32(1.3))
