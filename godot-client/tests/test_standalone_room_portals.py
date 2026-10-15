"""A shop's entry, arrival, exit and exterior return remain distinct and usable."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/tools'))
import continent_portals as C


@pytest.fixture
def shop(monkeypatch):
    doors = {'lantern-door': {'destination': 'four-gates-lantern-row',
                            'spawn': 'arrival', 'tile': (160, 120)}}
    outside = {'coordinateTransform': {'serverOrigin': [198, 198]}}
    room = {'asset': {'interior': True},
            'coordinateTransform': {'serverOrigin': [18, 18]},
            'spawnPoints': [{'id': 'arrival', 'position': [0, 0, 5.3]}],
            'portals': [{'id': 'exit', 'position': [0, 0, 6.6],
                         'targetPosition': [-38, 31, 74]}]}
    monkeypatch.setattr(C, 'load_portals', lambda region: doors)
    monkeypatch.setattr(C, 'read_manifest', lambda path:
                        outside if path.parent.name == 'four-gates' else room)
    return room


def test_publishes_explicit_exit_and_return_without_arrival_bounce(shop):
    errors = []
    lines, count = C.standalone_interior_lines({}, {},
        lambda _: SimpleNamespace(walkable=lambda x, y: True), errors, 'four_gates')
    assert errors == []
    assert count == 2
    assert lines[1:] == [
        'portal | four_gates | 160 | 120 | four-gates-lantern-row | 18 | 13',
        'portal | four-gates-lantern-row | 18 | 11 | four_gates | 160 | 124']


def test_blocked_door_fails_without_silently_relocating_it(shop):
    errors = []
    _, count = C.standalone_interior_lines({}, {}, lambda _: SimpleNamespace(
        walkable=lambda x, y: (x, y) != (18, 11)), errors, 'four_gates')
    assert count == 0
    assert errors == ['lantern-door: blocked exit four-gates-lantern-row (18, 11)']


def test_arrival_on_exit_is_rejected(shop):
    shop['spawnPoints'][0]['position'] = shop['portals'][0]['position']
    errors = []
    _, count = C.standalone_interior_lines({}, {},
        lambda _: SimpleNamespace(walkable=lambda x, y: True), errors, 'four_gates')
    assert count == 0
    assert errors == ['lantern-door: arrival overlaps its return trigger']


def test_unrelated_region_does_not_load_or_rewrite_shop_routes():
    def forbidden(_):
        raise AssertionError('Unrelated region loaded a Four Gates room')
    assert C.standalone_interior_lines({}, {}, forbidden, [], 'westhaven') == ([], 0)


def test_sunmane_caves_follow_explicit_section_arrivals_and_exterior_returns(monkeypatch):
    doors={'cave-wind_caves':dict(destination='sunmane_wind_caves',spawn='wind-caves-mouth',tile=(239,294)),
           'cave-crystal_hollow':dict(destination='sunmane_wind_caves',spawn='crystal-hollow-adit',tile=(322,273))}
    monkeypatch.setattr(C,'load_portals',lambda region:doors)
    monkeypatch.setattr(C,'load_arrivals',lambda package:{'wind-caves-mouth':(43,27),'crystal-hollow-adit':(169,28)})
    room={'coordinateTransform':{'serverOrigin':[0,0]},'portals':[
        dict(id='exit-wind-caves-mouth',serverTile=[43,27],destinationTile=[239,291]),
        dict(id='exit-crystal-hollow-adit',serverTile=[169,28],destinationTile=[319,274])]}
    monkeypatch.setattr(C,'read_manifest',lambda path:room)
    monkeypatch.setattr(C,'nearest_open',lambda *args:(999,999))
    errors=[]
    lines,count=C.interior_lines({}, {},lambda _:SimpleNamespace(walkable=lambda x,y:True),errors,'sunmane_steppe')
    assert not errors and count==4
    assert 'portal | sunmane_steppe | 322 | 273 | sunmane_wind_caves | 169 | 28' in lines
    assert 'portal | sunmane_wind_caves | 43 | 27 | sunmane_steppe | 239 | 291' in lines
    assert 'portal | sunmane_wind_caves | 169 | 28 | sunmane_steppe | 319 | 274' in lines


def test_legacy_cave_removal_preserves_definitions_other_regions_and_object_portals():
    text=('map | sunmane_wind_caves | Sunmane Insides | cave.elm | SWC\n'
          'portal | sunmane_steppe | 128 | 175 | sunmane_wind_caves | 43 | 27\n'
          'portal | sunmane_wind_caves | 43 | 27 | sunmane_steppe | 128 | 175\n'
          'portal | sunmane_steppe | 501 | 2 | 3 | sunmane_steppe_secrets | 8 | 9\n'
          'portal | verdant_stair | 4 | 5 | ssarathi_ruins | 6 | 7\n')
    result=C.remove_legacy_cave_links(text)
    assert result==''.join(line for line in text.splitlines(keepends=True) if '| 128 | 175' not in line)
    assert C.remove_legacy_cave_links(result)==result
