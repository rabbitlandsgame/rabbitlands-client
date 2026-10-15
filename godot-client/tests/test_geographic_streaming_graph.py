"""Physical adjacency supplements the travel graph without inventing crossings."""
from pathlib import Path
import json
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/tools'))
import build_exterior_streaming as B
from build_exterior_streaming import physical_edges


def test_shared_profile_samples_merge_without_bridging_real_gaps():
    data = {'boundaryHeightField': {'segments': [
        {'regions': ['a','b'], 'start': [5,0], 'end': [5,2]},
        {'regions': ['b','a'], 'start': [5,4], 'end': [5,2]},
        {'regions': ['a','b'], 'start': [5,6], 'end': [5,8]},
        {'regions': ['a','b'], 'start': [5,8], 'end': [9,8]},
    ]}}
    assert physical_edges(data) == {('a','b'): [
        [[5,8],[9,8]], [[5,0],[5,4]], [[5,6],[5,8]]
    ]}


def test_shared_continent_rejects_legacy_graph_rebuild_before_any_input_or_write(tmp_path, monkeypatch):
    regions = tmp_path / 'eloria-assets/maps/nymara-regions'
    regions.mkdir(parents=True)
    (regions / 'continent-geography.json').write_text(json.dumps({'geometryMode': 'continent-chunks-v1'}))
    graph = tmp_path / 'godot-client/data/maps/exterior_connections.json'
    graph.parent.mkdir(parents=True)
    graph.write_text('{"preloadDistance":320,"retainDistance":420,"surveyedEdges":"keep"}')
    before = graph.read_bytes()
    monkeypatch.setattr(B, 'CLIENT', tmp_path)
    monkeypatch.setattr(B, 'REGIONS', regions)
    # No legacy connection graph or actor catalog exists. The guard must run
    # before either can be read, and preserve the current canonical graph.
    with pytest.raises(ValueError, match='build_pipeline.py'):
        B.build()
    assert graph.read_bytes() == before


def test_export_waiting_for_canonical_publication_cannot_be_rebuilt_as_legacy():
    with pytest.raises(ValueError, match='surveyed physical preload edges'):
        B.guard_shared_continent({'geometryMode': 'continent-owned-v1'}, [
            {'streamingChunks': {'chunks': [{'id': '00_00'}]}}])
    B.guard_shared_continent({'geometryMode': 'continent-owned-v1'}, [
        {'streamingBorders': [{'geometryMode': 'continent-owned-v1'}]}])


def test_legacy_graph_keeps_reciprocal_walk_join_and_ignores_unloaded_ferry(tmp_path, monkeypatch):
    def write(relative, data):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    regions = tmp_path / 'eloria-assets/maps/nymara-regions'
    write('eloria-assets/maps/nymara-regions/continent-geography.json', {
        'geometryMode': 'continent-owned-v1', 'regions': {
            'a': {'translation': [0, 0, 0]}, 'b': {'translation': [20, 0, 0]}}})
    write('eloria-assets/maps/nymara-regions/region-connections.json', {'connections': [
        {'from': 'a', 'to': 'b', 'from_portal': 'east', 'to_portal': 'west', 'type': 'walk'},
        {'from': 'a', 'to': 'island', 'type': 'ferry'}]})
    write('godot-client/data/maps/registry.json', {'maps': {
        name: {'manifest': 'res://../eloria-assets/maps/nymara-regions/' + name + '/world.json'} for name in ('a', 'b')}})
    write('godot-client/data/actors/models.json', {'actorTypes': {}, 'models': {}})
    write('godot-client/data/world/objects.json', {'harvestables': {'resources': {}, 'models': {}}})
    for name, portal in [('a', 'east'), ('b', 'west')]:
        write('eloria-assets/maps/nymara-regions/' + name + '/world.json', {
            'coordinateTransform': {'serverOrigin': [10, 10]},
            'portals': [{'id': portal, 'position': [0, 2, 0]}],
            'streamingBorders': [{'id': 'legacy-crossing', 'portal': portal}]})
    monkeypatch.setattr(B, 'CLIENT', tmp_path)
    monkeypatch.setattr(B, 'REGIONS', regions)
    result = B.build()
    assert result['preloadDistance'] == 240 and result['retainDistance'] == 320
    assert len(result['connections']) == 1 and result['connections'][0]['seamless']
    assert [end['map'] for end in result['connections'][0]['ends']] == ['a', 'b']
    assert result['visualConnections'] == []
