"""An origin expansion changes server addresses, never authored standing places."""
from pathlib import Path
import json
import sys

import pytest

TOOLKIT = Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions/_toolkit'
sys.path.insert(0, str(TOOLKIT))
import contentposts as C


@pytest.fixture
def authored(tmp_path, monkeypatch):
    toolkit = tmp_path / 'regions/_toolkit'
    toolkit.mkdir(parents=True)
    monkeypatch.setattr(C, '__file__', str(toolkit / 'contentposts.py'))
    (toolkit.parent / 'continent-geography.json').write_text(json.dumps({
        'regions': {'four_gates': {'nativeServerOrigin': [198, 198]}}}))
    package = tmp_path / 'four-gates'
    (package / 'source').mkdir(parents=True)
    return package


def manifest(origin):
    return {'coordinateTransform': {'serverOrigin': origin, 'metresPerTile': 1.},
            'npcs': [{'id': 'miller', 'position': [0, 0, 0]}],
            'resources': [{'id': 'flax', 'center': [0, 0, 0]}]}


def test_authored_posts_keep_world_place_when_server_origin_changes(authored, monkeypatch):
    observed = []
    class Ground:
        def __init__(self, *args, **kwargs): pass
        def top_hit(self, x, z):
            observed.append((x, z))
            return 12.5
    monkeypatch.setattr(C.G, 'load', lambda path: ({}, b''))
    monkeypatch.setattr(C.G, 'named', lambda document, prefix: [])
    monkeypatch.setattr(C.G, 'triangles', lambda *args: [])
    monkeypatch.setattr(C, 'VerticalRayIndex', Ground)
    posts = {'npcs': {'miller': [220, 201]}, 'resources': {'flax': [195, 190]}}
    native, expanded = manifest([198, 198]), manifest([203, 210])
    C.apply(native, authored, posts)
    C.apply(expanded, authored, posts)
    assert observed == [(22., -3.), (-3., 8.)] * 2
    assert native['npcs'][0]['position'] == expanded['npcs'][0]['position'] == [22., 12.5, -3.]
    assert native['resources'][0]['center'] == expanded['resources'][0]['center'] == [-3., 12.5, 8.]
    assert expanded['npcs'][0]['serverTile'] == [225, 213]
    assert expanded['resources'][0]['serverTile'] == [200, 202]
    assert posts['npcs']['miller'] == [220, 201]


def test_runtime_roster_publication_does_not_accumulate_origin_shift(authored):
    roster = {'npcs': [{'id': 31, 'serverTile': [220, 201]}],
              'resources': [{'id': 82, 'serverTile': [195, 190]}],
              'encounters': [{'id': 9, 'serverTile': [230, 240]}]}
    source = authored / 'source/runtime-content.json'
    source.write_text(json.dumps(roster))
    before = source.read_bytes()
    native, expanded = manifest([198, 198]), manifest([203, 210])
    C.apply_runtime(native, authored)
    C.apply_runtime(expanded, authored)
    first = json.dumps(expanded, sort_keys=True)
    C.apply_runtime(expanded, authored)
    assert json.dumps(expanded, sort_keys=True) == first
    assert native['runtimePopulation'] == roster
    assert expanded['runtimePopulation']['encounters'][0]['serverTile'] == [235, 252]
    assert source.read_bytes() == before


def test_interior_without_geographic_entry_retains_its_native_frame(authored):
    assert C.native_tile_delta(manifest([20, 30]), authored.parent / 'forge-interior') == [0., 0.]
