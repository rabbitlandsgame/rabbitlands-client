import pytest

from run_creature_storage_qa import validate_fixture_hashes


def test_native_and_editor_copies_must_match_canonical_proposal(tmp_path):
    source, candidate = tmp_path / 'source.glb', tmp_path / 'candidate.glb'
    source.write_bytes(b'original'); candidate.write_bytes(b'new proposal')
    imported = tmp_path / 'assets' / 'candidate.glb'; imported.parent.mkdir()
    imported.write_bytes(candidate.read_bytes())
    job = {'source': str(source), 'candidate': str(candidate),
           'actor_fixtures': [{'name': 'baseline', 'path': str(source)},
                              {'name': 'candidate', 'path': str(candidate)}],
           'imported_fixtures': [{'name': 'candidate', 'path': 'res://assets/candidate.glb'}]}
    validate_fixture_hashes(job, tmp_path)
    imported.write_bytes(b'old proposal')
    with pytest.raises(ValueError, match='Stale imported_fixtures candidate'):
        validate_fixture_hashes(job, tmp_path)
    imported.write_bytes(candidate.read_bytes())
    job['native_fixtures'] = [{'name': 'candidate', 'path': str(source)}]
    with pytest.raises(ValueError, match='Stale native_fixtures candidate'):
        validate_fixture_hashes(job, tmp_path)
