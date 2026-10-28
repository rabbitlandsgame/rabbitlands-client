import json
import pytest
from pathlib import Path

from pack_creature_storage import prepare
from test_crystalback_correctives import source_fixture
from update_creature_storage_metadata import update


@pytest.mark.parametrize('profile', [None, {'numeric_budget': {
    'position_absolute_limit': 4.76837158203125e-7,
    'normal_direction_vector_limit': 4.76837158203125e-7}}])
def test_only_current_actor_bindings_change_and_observations_remain(tmp_path, profile):
    source, _ = source_fixture(tmp_path)
    root = tmp_path/'repo'
    candidate = root/'assets/wolf.glb'
    report = prepare(source, candidate)
    old, new = report['source_sha256'], report['candidate_sha256']
    qa = root/'docs/qa/family/actors.json'; qa.parent.mkdir(parents=True)
    qa.write_text(json.dumps({'wolf': {'sha256': old, 'runtime_path': 'assets/wolf.glb', 'bytes': 1, 'sole_vertices': {'left': [0, 1]}},
                              'other': {'sha256': old, 'runtime_path': 'assets/other.glb', 'bytes': 1}}))
    fixture = root/'godot-client/tests/fixtures/worlds.json'; fixture.parent.mkdir(parents=True)
    observation = {'sha256': old, 'height': 2., 'surface_numeric_tolerance_over_height': 1e-8,
                   'normal_numeric_tolerance': 1e-8, 'surface_vertex_ids': [1], 'surface_rest': [[9., 8., 7.]],
                   'clips': {'Walk': [{'time': .123, 'surface': [[4., 5., 6.]], 'bones': {'Root': [1, 2]}, 'morph_weights': {'1': [0]}}]}}
    fixture.write_text(json.dumps({'wolf': observation, 'other': {'sha256': old}}))
    roster = root/'eloria-assets/source/model-development-roster.json'; roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps({'creatures': [{'id': 'wolf', 'sha256': old, 'status': 'current reviewed model'},
                                               {'id': 'other', 'sha256': old, 'status': 'current model'}]}))
    changed = update(root, 'wolf', source, candidate, report, 'docs/qa/storage/wolf.json', profile=profile, backup=tmp_path/'backup')
    current = json.loads(qa.read_text())
    assert current['wolf']['sha256'] == new and current['other']['sha256'] == old
    assert current['wolf']['bytes'] == candidate.stat().st_size
    after = json.loads(fixture.read_text())
    assert after['wolf']['sha256'] == new and after['other']['sha256'] == old
    assert after['wolf']['surface_rest'] == observation['surface_rest']
    assert after['wolf']['clips']['Walk'][0]['surface'] == observation['clips']['Walk'][0]['surface']
    assert after['wolf']['clips']['Walk'][0]['morph_weights']['1'] == []
    assert after['wolf']['surface_numeric_tolerance_over_height'] == 1e-8
    assert after['wolf']['normal_numeric_tolerance'] == 1e-8
    assert 'representation_numeric_budget' not in after['wolf']
    assert json.loads(roster.read_text())['creatures'][1]['sha256'] == old
    assert len(changed) == 3
    assert (tmp_path/'backup/godot-client/tests/fixtures/worlds.json').is_file()


def test_stale_roster_fails_before_writing_current_receipts(tmp_path):
    source, _ = source_fixture(tmp_path)
    root = tmp_path/'repo'
    candidate = root/'assets/wolf.glb'
    report = prepare(source, candidate)
    qa = root/'docs/qa/family/actors.json'; qa.parent.mkdir(parents=True)
    original = json.dumps({'wolf': {'sha256': report['source_sha256'], 'runtime_path': 'assets/wolf.glb'}})
    qa.write_text(original)
    roster = root/'eloria-assets/source/model-development-roster.json'; roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps({'creatures': [{'id': 'wolf', 'sha256': 'unrelated'}]}))
    with pytest.raises(ValueError, match='newer/unrelated'):
        update(root, 'wolf', source, candidate, report, 'receipt.json')
    assert qa.read_text() == original


def test_humanoid_embedded_receipts_keep_measurements_and_chain_binding(tmp_path):
    source, _ = source_fixture(tmp_path)
    root = tmp_path/'repo'; candidate = root/'assets/wolf.glb'
    report = prepare(source, candidate); old, new = report['source_sha256'], report['candidate_sha256']
    manifest = root/'docs/qa/humanoid-motion-baseline/manifest.json'; manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'actors': [{'actor': 'wolf', 'runtime_path': 'assets/wolf.glb', 'sha256': old,
        'native_conformance': {'runtime_sha256': old, 'max_error': 0.123},
        'packing': {'runtime_sha256': old, 'runtime_bytes': 1, 'source_sha256': 'authoring-source', 'samples': [1, 2, 3]}}]}))
    (root/'godot-client/tests/fixtures').mkdir(parents=True)
    roster = root/'eloria-assets/source/model-development-roster.json'; roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps({'creatures': [{'id': 'wolf', 'sha256': old, 'status': 'reviewed'}]}))
    update(root, 'wolf', source, candidate, report, 'receipt.json')
    row = json.loads(manifest.read_text())['actors'][0]
    assert row['sha256'] == new
    assert row['native_conformance']['max_error'] == 0.123
    assert row['packing']['source_sha256'] == 'authoring-source'
    assert row['packing']['samples'] == [1, 2, 3]
    assert row['packing']['runtime_bytes'] == candidate.stat().st_size
    for field in ['native_conformance', 'packing']:
        assert row[field]['runtime_sha256'] == new
        assert row[field]['storage_rebind']['previous_runtime_sha256'] == old
