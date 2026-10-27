import json
from pathlib import Path

from pack_creature_storage import prepare
from test_crystalback_correctives import source_fixture
from update_creature_storage_metadata import update


def test_only_current_actor_bindings_change_and_observations_remain(tmp_path):
    source, _ = source_fixture(tmp_path)
    root = tmp_path/'repo'
    candidate = root/'assets/wolf.glb'
    report = prepare(source, candidate)
    old, new = report['source_sha256'], report['candidate_sha256']
    qa = root/'docs/qa/family/actors.json'; qa.parent.mkdir(parents=True)
    qa.write_text(json.dumps({'wolf': {'sha256': old, 'runtime_path': 'assets/wolf.glb', 'bytes': 1, 'sole_vertices': {'left': [0, 1]}},
                              'other': {'sha256': old, 'runtime_path': 'assets/other.glb', 'bytes': 1}}))
    fixture = root/'godot-client/tests/fixtures/worlds.json'; fixture.parent.mkdir(parents=True)
    observation = {'sha256': old, 'surface_vertex_ids': [1], 'surface_rest': [[9., 8., 7.]],
                   'clips': {'Walk': [{'time': .123, 'surface': [[4., 5., 6.]], 'bones': {'Root': [1, 2]}, 'morph_weights': {'1': [0]}}]}}
    fixture.write_text(json.dumps({'wolf': observation, 'other': {'sha256': old}}))
    roster = root/'eloria-assets/source/model-development-roster.json'; roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps({'creatures': [{'id': 'wolf', 'sha256': old, 'status': 'current reviewed model'},
                                               {'id': 'other', 'sha256': old, 'status': 'current model'}]}))
    changed = update(root, 'wolf', source, candidate, report, 'docs/qa/storage/wolf.json', backup=tmp_path/'backup')
    current = json.loads(qa.read_text())
    assert current['wolf']['sha256'] == new and current['other']['sha256'] == old
    assert current['wolf']['bytes'] == candidate.stat().st_size
    after = json.loads(fixture.read_text())
    assert after['wolf']['sha256'] == new and after['other']['sha256'] == old
    assert after['wolf']['surface_rest'] == observation['surface_rest']
    assert after['wolf']['clips']['Walk'][0]['surface'] == observation['clips']['Walk'][0]['surface']
    assert after['wolf']['clips']['Walk'][0]['morph_weights']['1'] == []
    assert json.loads(roster.read_text())['creatures'][1]['sha256'] == old
    assert len(changed) == 3
    assert (tmp_path/'backup/godot-client/tests/fixtures/worlds.json').is_file()
