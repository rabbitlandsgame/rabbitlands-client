"""Contract placement tests use synthetic ground, never a live server profile."""
import importlib.util
import copy
import json
from pathlib import Path
import sys
import types
import unittest
import tempfile
from unittest import mock
import struct

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import export_contracts as E
import content as C
import landscape as L
import authoring as A
import crossings as X


def _authored_crossing_fixture(monkeypatch, kind='walk', terrain_y=27.712074279785156,
                               source_y=27.742361068725586):
    """Tiny geometry/marker split, including the actual Sunmane height regression."""
    link = {'id': 'west--east', 'type': kind, 'regions': ['west', 'east'],
            'anchor': [10., 0.], 'normal': [1., 0.],
            'edgeSegments': [[[10., -4.], [10., 4.]]],
            'landings': [[9., 0.], [11., 0.]]}
    world = types.SimpleNamespace(
        connections=[link], regions={'west': {'center': [0., 0.]}, 'east': {'center': [20., 0.]}},
        address=lambda region: ([30, 30], [60, 60]), height_at=lambda x, z: terrain_y,
        adjacent_edges=lambda: {},
        ferry_shore_report={'finalFits': [
            {'region': region, 'connections': ['west--east'], 'landing': landing,
             'forward': forward}
            for region, landing, forward in [('west', [9., 0.], [1., 0.]),
                                             ('east', [11., 0.], [-1., 0.])]]})
    monkeypatch.setattr(X, 'open_borders', lambda world: [])
    monkeypatch.setattr(X, 'open_border_contracts', lambda world: [])
    derived = copy.deepcopy(X.prepare_contracts(world))
    world.authoring_snapshots = {}
    for end in derived[0]['ends']:
        region = end['region']
        other = next(e for e in derived[0]['ends'] if e['region'] != region)
        record = {'id': end['portal'], 'name': 'Existing name', 'label': 'Saved custom label',
                  'position': [end['position'][0], source_y, end['position'][2]],
                  'serverTile': end['tile'], 'destinationMap': other['region'],
                  'destinationTile': other['arrival'], 'type': kind,
                  'customMetadata': {'preserve': [1, 2]}}
        center = world.regions[region]['center']
        world.authoring_snapshots[region] = types.SimpleNamespace(document={
            'regionId': region, 'coordinateSpace': 'territory-local',
            'axes': {'x': 'east', 'y': 'up', 'z': 'south'},
            'continentTranslation': [center[0], 0., center[1]],
            'server': {'origin': [30, 30], 'metresPerTile': 1.},
            'gameplay': {'portals': [record]}})
    return world, derived


@pytest.mark.parametrize('kind,terrain_y,source_y', [
    ('walk', 27.712074279785156, 27.742361068725586),
    ('walk', 35.09055709838867, 34.9501838684082),
    ('ferry', 2., 2.125),
])
def test_authored_crossing_export_preserves_xyz_labels_without_changing_lanes(
        monkeypatch, kind, terrain_y, source_y):
    world, derived = _authored_crossing_fixture(monkeypatch, kind, terrain_y, source_y)
    saved = {r: copy.deepcopy(s.document) for r, s in world.authoring_snapshots.items()}
    exported = X.prepare_contracts(world)
    assert exported == derived  # Runtime positions, frames, lanes and tiles all unchanged.
    for region in ('west', 'east'):
        manifest = {}
        X.apply_manifest(world, region, manifest)
        assert manifest['portals'] == saved[region]['gameplay']['portals']
        assert manifest['portals'][0]['position'][1] == source_y
        manifest['portals'][0]['customMetadata']['preserve'].append(3)
        assert world.authoring_snapshots[region].document == saved[region]
    assert world.height_at(10., 0.) == terrain_y


@pytest.mark.parametrize('field,value', [
    ('missing', None), ('duplicate', None), ('id', 'unrelated'), ('type', 'ferry'),
    ('destinationMap', 'unknown'), ('serverTile', [1, 2]),
    ('position', [13.5, 27., -.5]), ('position', [11.5, float('nan'), -.5]),
    ('regionId', 'other'), ('coordinateSpace', 'continent'),
    ('continentTranslation', [0., 1., 0.]), ('axes', {'x': 'east', 'y': 'down', 'z': 'south'}),
    ('server', {'origin': [31, 30], 'metresPerTile': 1.}),
    ('server', {'origin': [30, 30], 'metresPerTile': 2.}),
])
def test_authored_crossing_export_rejects_stale_or_ambiguous_source(monkeypatch, field, value):
    world, _ = _authored_crossing_fixture(monkeypatch)
    doc = world.authoring_snapshots['west'].document
    records = doc['gameplay']['portals']
    if field == 'missing':
        records.clear()
    elif field == 'duplicate':
        records.append(copy.deepcopy(records[0]))
    elif field in ('regionId', 'coordinateSpace', 'continentTranslation', 'axes', 'server'):
        doc[field] = value
    else:
        records[0][field] = value
    with pytest.raises(ValueError, match='authored crossing portal'):
        X.prepare_contracts(world)


def test_authored_crossing_rejects_duplicate_generated_identity(monkeypatch):
    world, _ = _authored_crossing_fixture(monkeypatch)
    world.connections.append(copy.deepcopy(world.connections[0]))
    with pytest.raises(ValueError, match='authored crossing'):
        X.prepare_contracts(world)


def test_crossing_export_without_authored_snapshots_retains_legacy_generation(monkeypatch):
    world, derived = _authored_crossing_fixture(monkeypatch)
    del world.authoring_snapshots
    assert X.prepare_contracts(world) == derived
    manifest = {}
    X.apply_manifest(world, 'west', manifest)
    portal = manifest['portals'][0]
    assert portal['position'] == derived[0]['ends'][0]['position']
    assert portal['name'] == 'Road to East'
    assert 'label' not in portal


@pytest.mark.parametrize('kind', ['walk', 'ferry'])
def test_settled_trigger_tiles_preserve_marker_and_runtime_positions_independently(monkeypatch, kind):
    world, _ = _authored_crossing_fixture(monkeypatch, kind)
    X.prepare_contracts(world)
    settled = copy.deepcopy(world.publication_connections)
    end, other = settled[0]['ends']
    end['tile'][0] -= 1
    end['position'][0] -= 1.
    if kind == 'walk':
        end['lanes'] = [{'tile': list(end['tile']), 'arrival': list(end['arrival'])}]
    # The opposite lane's return partner need not be this departure's physical
    # cell. Walking uses same-cell mapping; a ferry uses this explicit arrival.
    other['arrival'][1] += 3
    before = copy.deepcopy(settled)
    doc = world.authoring_snapshots['west'].document
    original = copy.deepcopy(doc)
    markers = X.authored_portals(world, 'west', settled)
    record = markers[end['portal']]
    saved = doc['gameplay']['portals'][0]
    assert record['position'] == saved['position']
    assert record['label'] == saved['label']
    assert record['serverTile'] == end['tile']
    actual_arrival = list(map(int, X.tiles_at(world, 'east', *X.global_tile(world, 'west', end['tile']))))
    assert actual_arrival != other['arrival']
    assert record['destinationTile'] == (actual_arrival if kind == 'walk' else other['arrival'])
    assert settled == before  # Client fallback/preload XYZ stays on the derived endpoint.
    assert doc == original
    monkeypatch.syspath_prepend(str(E.TOOLS))
    publisher = importlib.import_module('publish_diagonal_continent')
    specs = {r: {'serverOrigin': [30, 30], 'serverCells': [60, 60],
                 'translation': [value['center'][0], 0., value['center'][1]]}
             for r, value in world.regions.items()}
    runtime = copy.deepcopy(settled)
    if kind == 'walk':
        for endpoint in runtime[0]['ends']:
            endpoint['lanes'] = [{'tile': endpoint['tile'], 'arrival': endpoint['arrival']}]
    _, rows = publisher.connection_rows(runtime, specs)
    row = next(row for row in rows if row[:3] == ('west', *end['tile']))
    assert list(row[4:6]) == record['destinationTile']
    if kind == 'walk':
        worlds = {r: {'coordinateTransform': {'serverOrigin': [30, 30]}} for r in specs}
        _, streaming = publisher.connection_manifests(
            {'revision': 'fixture', 'connections': runtime}, worlds, specs)
        streamed = next(e for e in streaming['connections'][0]['ends'] if e['map'] == 'west')
        assert streamed['position'] == end['position']
        assert streamed['position'] != record['position']
        assert streamed['crossingRuns'] == publisher.crossing_runs([end['tile']])
    record['customMetadata']['preserve'].append(3)
    assert doc == original


@pytest.mark.parametrize('change', [
    'missing', 'duplicate', 'identity', 'type', 'destination', 'tile_type', 'withdrawn', 'runtime_xz'])
def test_settled_marker_join_rejects_missing_ambiguous_or_invalid_connection(monkeypatch, change):
    world, _ = _authored_crossing_fixture(monkeypatch)
    X.prepare_contracts(world)
    settled = copy.deepcopy(world.publication_connections)
    if change == 'missing':
        settled.clear()
    elif change == 'duplicate':
        settled.append(copy.deepcopy(settled[0]))
    elif change == 'identity':
        settled[0]['ends'][0]['portal'] = 'unrelated'
    elif change == 'type':
        settled[0]['type'] = 'ferry'
    elif change == 'destination':
        settled[0]['ends'][1]['region'] = 'unknown'
    elif change == 'withdrawn':
        settled[0]['ends'][0]['lanes'].clear()
    elif change == 'runtime_xz':
        settled[0]['ends'][0]['position'][0] += 1.
    else:
        settled[0]['ends'][0]['tile'][0] = 1.5
    # A generated roadless border has no saved portal and is not a named pin.
    border = {'id': 'roadless', 'road': False, 'type': 'walk', 'ends': []}
    settled.append(copy.deepcopy(border))
    with pytest.raises(ValueError, match='authored crossing'):
        X.authored_portals(world, 'west', settled)


def test_inherited_destination_metadata_is_replaced_without_changing_the_source(monkeypatch):
    world, _ = _authored_crossing_fixture(monkeypatch)
    doc = world.authoring_snapshots['west'].document
    doc['gameplay']['portals'][0]['destinationTile'] = [999, 888]
    original = copy.deepcopy(doc)
    X.prepare_contracts(world)
    manifest = {}
    X.apply_manifest(world, 'west', manifest)
    assert manifest['portals'][0]['destinationTile'] != [999, 888]
    assert doc == original


@pytest.mark.parametrize('kind', ['walk', 'ferry'])
def test_update_markers_preserves_authored_crossing_but_reseats_ordinary_portal(monkeypatch, kind):
    world, _ = _authored_crossing_fixture(monkeypatch, kind)
    X.prepare_contracts(world)
    manifest = {'coordinateTransform': {}, 'spawnPoints': [
        {'id': 'spawn', 'default': True, 'position': [0., 5., 0.]}]}
    X.apply_manifest(world, 'west', manifest)
    pin = copy.deepcopy(manifest['portals'][0])
    ordinary = {'id': 'cave', 'serverTile': [1, 1], 'position': [-28.5, 4., 28.5]}
    manifest['portals'].append(copy.deepcopy(ordinary))
    settled = copy.deepcopy(world.publication_connections)
    settled[0]['ends'][0]['tile'][0] -= 1
    settled[0]['ends'][0]['position'][0] -= 1
    if kind == 'walk':
        settled[0]['ends'][0]['lanes'] = [{
            'tile': list(settled[0]['ends'][0]['tile']),
            'arrival': list(settled[0]['ends'][0]['arrival'])}]
    crossing_markers = X.authored_portals(world, 'west', settled)
    placement = types.SimpleNamespace(
        world=world, region='west', content=types.SimpleNamespace(
            authored_regions={'west'}, templates={'west': {'portals': [pin, ordinary]}}),
        spec={'previousServerOrigin': [30, 30],
              'tilePositions': {E.key(pin['serverTile']): [50, 50], '1:1': [2, 2]}},
        local_position=lambda tile: [tile[0] - 29.5, 99., 29.5 - tile[1]],
        report={'regions': {'west': {}}})
    E.update_markers(placement, manifest, crossing_markers)
    published = manifest['portals'][0]
    assert published == crossing_markers[pin['id']]
    assert published['position'] == pin['position']
    assert published['serverTile'] == settled[0]['ends'][0]['tile']
    assert published['serverTile'] != pin['serverTile']
    assert manifest['portals'][1]['serverTile'] == [2, 2]
    assert manifest['portals'][1]['position'] == [-27.5, 99., 27.5]
    assert placement.report['regions']['west']['updatedAuthoredMarkers'] == 1


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'position', 'label'])
def test_update_markers_rejects_corrupted_generated_authored_pin(monkeypatch, change):
    world, _ = _authored_crossing_fixture(monkeypatch)
    X.prepare_contracts(world)
    manifest = {}
    X.apply_manifest(world, 'west', manifest)
    if change == 'missing':
        manifest['portals'].clear()
    elif change == 'duplicate':
        manifest['portals'].append(copy.deepcopy(manifest['portals'][0]))
    else:
        manifest['portals'][0][change] = None
    placement = types.SimpleNamespace(world=world, region='west')
    with pytest.raises(E.PlacementError, match='authored crossing portal changed'):
        E.update_markers(placement, manifest)


class Sources:
    @staticmethod
    def reachable_from(grid, start, limit):
        # Small independent 4-neighbour flood is sufficient for the fixtures.
        result = np.zeros_like(grid, dtype=bool)
        x, y = start
        if not (0 <= x < grid.shape[1] and 0 <= y < grid.shape[0]) or not grid[y, x]:
            return result
        pending = [(x, y)]; result[y, x] = True
        for x, y in pending:
            for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0 <= nx < grid.shape[1] and 0 <= ny < grid.shape[0] and not result[ny,nx] and grid[ny,nx] and abs(int(grid[y,x])-int(grid[ny,nx])) <= limit:
                    result[ny,nx] = True; pending.append((nx,ny))
        return result


def test_runtime_binding_placement_uses_exact_identity_and_shared_marker_aliases():
    grid = np.ones((30, 30), dtype=np.uint8)
    world = types.SimpleNamespace(regions={'sunmane_steppe': {'center': [100, 200]}})
    bindings = {
        'door': {'marker': {'section': 'interactives', 'id': 'shared'},
                 'targetOffset': [0., 0., 0.]},
        'door-alias': {'marker': {'section': 'interactives', 'id': 'shared'},
                       'targetOffset': [0., 0., 0.]},
        'return': {'marker': {'section': 'interactives', 'id': 'shared'},
                   'targetOffset': [3., 0., 1.]},
        'first': {'marker': {'section': 'runtimePoints', 'id': 'first'},
                  'targetOffset': [0., 0., 0.]},
        'second': {'marker': {'section': 'runtimePoints', 'id': 'second'},
                   'targetOffset': [0., 0., 0.]},
    }
    authored = {
        ('sunmane_steppe', 'door'): np.array([100., 10., 200.]),
        ('sunmane_steppe', 'door-alias'): np.array([100., 10., 200.]),
        ('sunmane_steppe', 'return'): np.array([103., 10., 201.]),
        ('sunmane_steppe', 'first'): np.array([96., 10., 200.]),
        ('sunmane_steppe', 'second'): np.array([104., 10., 200.]),
    }
    content = types.SimpleNamespace(
        templates={'sunmane_steppe': {'coordinateTransform': {'serverOrigin': [15, 15]}}},
        runtime_bindings=bindings, authored_runtime_points=authored,
        mapped_point=lambda *args: (_ for _ in ()).throw(AssertionError('tile fallback used')))
    spec = {'serverOrigin': [15, 15], 'previousServerOrigin': [15, 15],
            'tilePositions': {}, 'runtimeBindingPositions': {}, 'runtimeBindingSourceTiles': {},
            'runtimeMarkerPositions': {},
            'portalPositions': {}, 'arrival': [15, 15]}
    report = {'placements': [], 'failures': [], 'regions': {'sunmane_steppe': {}}}
    collision = {'heights': np.full((60, 60), 10, dtype=np.float32)}
    p = E.RegionPlacement(world, content, 'sunmane_steppe', spec, collision, grid, Sources, report)
    p.connect_hub([15, 15])

    door = p.place([1, 1], 'door', 5, identity='door')
    assert p.place([1, 1], 'door-alias', 5, identity='door-alias') == door
    returned = p.place([2, 2], 'return', 5, identity='return')
    assert returned != door
    first = p.place([9, 9], 'first', 5, identity='first')
    second = p.place([9, 9], 'second', 5, identity='second')
    assert first != second
    assert spec['runtimeBindingPositions'] == {
        'door': door, 'door-alias': door, 'return': returned,
        'first': first, 'second': second}
    assert spec['runtimeBindingSourceTiles'] == {
        'door': [1, 1], 'door-alias': [1, 1], 'return': [2, 2],
        'first': [9, 9], 'second': [9, 9]}


def test_cross_region_profile_record_uses_qualified_target_marker_and_publishes_at_source():
    """A Whitehorn door may be authored by a saved Amethyst portal marker."""
    identity = 'maps.txt:531:door:amethyst_barrens->resonant_vault@315:227'
    binding = {
        'id': identity,
        'marker': {'section': 'portals', 'id': 'resonant_vault'},
        'targetOffset': [2., 0., -3.],
        'source': {'path': 'config/eloria/maps.txt', 'line': 531,
                   'oldTile': [315, 227]},
    }
    grid = np.ones((40, 40), dtype=np.uint8)
    world = types.SimpleNamespace(regions={
        'whitehorn_range': {'center': [0., 0.]},
        'amethyst_barrens': {'center': [100., 200.]},
    })
    authored_point = np.array([4., 12., 7.])
    content = types.SimpleNamespace(
        templates={'whitehorn_range': {'coordinateTransform': {'serverOrigin': [20, 20]}}},
        runtime_bindings={identity: binding},
        runtime_bindings_by_region={'amethyst_barrens': {identity: binding}},
        authored_runtime_points={('amethyst_barrens', identity): authored_point},
        mapped_point=lambda *args: (_ for _ in ()).throw(AssertionError('tile fallback used')))
    spec = {'serverOrigin': [20, 20], 'previousServerOrigin': [20, 20],
            'tilePositions': {}, 'runtimeBindings': {},
            'runtimeBindingPositions': {}, 'runtimeBindingSourceTiles': {},
            'runtimeMarkerPositions': {}, 'portalPositions': {}, 'arrival': [20, 20]}
    report = {'placements': [], 'failures': [], 'regions': {'whitehorn_range': {}}}
    collision = {'heights': np.full((80, 80), 12, dtype=np.float32)}
    placement = E.RegionPlacement(
        world, content, 'whitehorn_range', spec, collision, grid, Sources, report)
    placement.connect_hub([20, 20])

    tile = placement.place([315, 227], 'whitehorn to resonant vault', 20, identity=identity)

    assert tile == [23, 12]
    assert spec['runtimeBindings'] == {identity: binding}
    assert spec['runtimeBindingPositions'][identity] == tile
    assert spec['runtimeBindingSourceTiles'][identity] == [315, 227]
    # Region qualification is fail-closed if producer data ever names two owners.
    content.runtime_bindings_by_region['whitehorn_range'] = {identity: binding}
    with pytest.raises(E.PlacementError, match='ambiguous region owners'):
        placement.expected([315, 227], identity)


def test_territory_profile_consumes_authored_binding_for_already_seated_arrival(tmp_path):
    """The actual territories.txt path must bind connect_hub's existing tile."""
    identity = 'territories.txt@149:95'
    binding = {
        'id': identity,
        'source': {'path': 'config/eloria/territories.txt', 'line': 36,
                   'oldTile': [149, 95]},
        'marker': {'section': 'spawnPoints', 'id': 'continent-arrival'},
        'role': 'territory',
        'targetOffset': [0., 0., 0.],
    }
    grid = np.ones((30, 30), dtype=np.uint8)
    world = types.SimpleNamespace(
        regions={'amethyst_barrens': {'center': [100., 200.]}},
        hub=lambda region: np.array([100.5, 199.5]))
    content = types.SimpleNamespace(
        templates={'amethyst_barrens': {
            'coordinateTransform': {'serverOrigin': [15, 15]}}},
        runtime_bindings={identity: binding},
        runtime_binding_source_tiles={
            ('config/eloria/territories.txt', (149, 95)): [identity]},
        authored_runtime_points={
            ('amethyst_barrens', identity): np.array([100.5, 10., 199.5])},
        mapped_point=lambda *args: (_ for _ in ()).throw(
            AssertionError('territory binding used a generic tile fallback')))
    spec = {'serverOrigin': [15, 15], 'previousServerOrigin': [15, 15],
            'tilePositions': {}, 'runtimeBindings': {},
            'runtimeBindingPositions': {}, 'runtimeBindingSourceTiles': {},
            'runtimeMarkerPositions': {}, 'portalPositions': {}, 'arrival': [15, 15]}
    report = {'placements': [], 'failures': [], 'regions': {'amethyst_barrens': {}}}
    placement = E.RegionPlacement(
        world, content, 'amethyst_barrens', spec,
        {'heights': np.full((60, 60), 10, dtype=np.float32)},
        grid, Sources, report)
    placement.connect_hub([149, 95], grid.astype(bool))
    seated = list(spec['arrival'])

    def rewrite_profile(text, rule, mappings):
        mapped = mappings['amethyst_barrens']['_native_mapper']([149, 95])
        assert mapped == seated
        return text, 1

    shared = types.SimpleNamespace(
        RULES={'territories.txt': object()}, rewrite_profile=rewrite_profile,
        rewrite_definition=lambda text, mappings: (text, 0))
    publisher = types.SimpleNamespace(
        CONTENT={}, transform_tile=lambda old, spec: old,
        remap_metadata=lambda *args: None,
        rewrite_gameplay_source=lambda text, kind, mappings: text)
    E.collect_gameplay_points(
        tmp_path, {
            'territories.txt': ('amethyst_barrens | Amethyst Barrens | amethyst_barrens | '
                                'magic | 40 | 95 | 231 | 95 | 149 | 95 |\n'),
            'client_content_manifest.json': '{"maps": []}',
        }, {'amethyst_barrens': placement},
        {group: {'amethyst_barrens': []}
         for group in ('npcs', 'harvest', 'spawns', 'interactives')},
        shared, publisher)

    assert spec['arrival'] == seated
    assert spec['runtimeBindings'] == {identity: binding}
    assert spec['runtimeBindingPositions'][identity] == seated
    assert spec['runtimeBindingSourceTiles'][identity] == [149, 95]
    assert report['failures'] == []


def test_preexisting_source_tile_does_not_collapse_distinct_marker_offsets():
    bindings = {
        'first': {
            'marker': {'section': 'interactives', 'id': 'shared'},
            'targetOffset': [0., 0., 0.]},
        'second': {
            'marker': {'section': 'interactives', 'id': 'shared'},
            'targetOffset': [2., 0., 0.]},
    }
    world = types.SimpleNamespace(regions={'amethyst_barrens': {'center': [100., 200.]}})
    content = types.SimpleNamespace(
        templates={'amethyst_barrens': {
            'coordinateTransform': {'serverOrigin': [15, 15]}}},
        runtime_bindings=bindings,
        authored_runtime_points={
            ('amethyst_barrens', 'first'): np.array([100.5, 10., 199.5]),
            ('amethyst_barrens', 'second'): np.array([102.5, 10., 199.5]),
        })
    spec = {'serverOrigin': [15, 15], 'previousServerOrigin': [15, 15],
            'tilePositions': {}, 'runtimeBindings': {},
            'runtimeBindingPositions': {}, 'runtimeBindingSourceTiles': {},
            'runtimeMarkerPositions': {}, 'portalPositions': {}, 'arrival': [15, 15]}
    report = {'placements': [], 'failures': [], 'regions': {'amethyst_barrens': {}}}
    placement = E.RegionPlacement(
        world, content, 'amethyst_barrens', spec,
        {'heights': np.full((60, 60), 10, dtype=np.float32)},
        np.ones((30, 30), dtype=np.uint8), Sources, report)

    first = placement.place([149, 95], 'first', 5, identity='first')
    second = placement.place([149, 95], 'second', 5, identity='second')
    assert first != second
    assert spec['runtimeBindingPositions'] == {'first': first, 'second': second}
    assert report['failures'] == []


def test_two_authored_regions_publish_only_their_qualified_bindings_and_spawns():
    sun_aliases = {
        'sun-door': {'marker': {'section': 'interactives', 'id': 'shared'},
                     'targetOffset': [0., 0., 0.]},
        'sun-return': {'marker': {'section': 'interactives', 'id': 'shared'},
                       'targetOffset': [3., 0., 1.]},
    }
    amethyst_bindings = {
        'amethyst-secret': {'marker': {'section': 'runtimePoints', 'id': 'secret'},
                            'targetOffset': [0., 0., 0.]},
    }
    content = types.SimpleNamespace(
        authored_regions={'sunmane_steppe', 'amethyst_barrens'},
        runtime_bindings={**sun_aliases, **amethyst_bindings},
        runtime_bindings_by_region={
            'sunmane_steppe': sun_aliases,
            'amethyst_barrens': amethyst_bindings,
        },
        templates={
            'sunmane_steppe': {'coordinateTransform': {'serverOrigin': [194, 292]}},
            'amethyst_barrens': {'coordinateTransform': {'serverOrigin': [182, 166]}},
        })

    published_sun = E.region_runtime_bindings(content, 'sunmane_steppe')
    published_amethyst = E.region_runtime_bindings(content, 'amethyst_barrens')
    assert set(published_sun) == {'sun-door', 'sun-return'}
    assert published_sun['sun-door']['marker'] == published_sun['sun-return']['marker']
    assert published_sun['sun-door']['targetOffset'] != published_sun['sun-return']['targetOffset']
    assert set(published_amethyst) == {'amethyst-secret'}
    published_sun['sun-door']['targetOffset'][0] = 99.
    assert sun_aliases['sun-door']['targetOffset'] == [0., 0., 0.]

    report = {'regions': {'sunmane_steppe': {}, 'amethyst_barrens': {}}}
    cases = (
        ('sunmane_steppe', [
            {'id': 'sun-secondary', 'position': [1., 7., 2.]},
            {'id': 'sun-primary', 'default': True, 'position': [3., 9., 4.]},
        ], 'sun-primary', 9.),
        ('amethyst_barrens', [
            {'id': 'amethyst-first', 'position': [5., 11., 6.]},
            {'id': 'amethyst-second', 'position': [7., 13., 8.]},
        ], 'amethyst-first', 11.),
    )
    for region, spawns, expected_default, expected_height in cases:
        placement = types.SimpleNamespace(
            region=region, content=content,
            spec={'previousServerOrigin': content.templates[region]['coordinateTransform']['serverOrigin'],
                  'tilePositions': {}}, report=report)
        manifest = {'spawnPoints': copy.deepcopy(spawns), 'coordinateTransform': {}}
        E.update_markers(placement, manifest)
        assert manifest['navigation']['defaultSpawn'] == expected_default
        assert manifest['coordinateTransform']['walkingHeight'] == expected_height


def test_authored_spawn_contract_rejects_missing_or_multiple_defaults():
    region = 'amethyst_barrens'
    content = types.SimpleNamespace(
        authored_regions={region},
        templates={region: {'coordinateTransform': {'serverOrigin': [182, 166]}}})
    placement = types.SimpleNamespace(
        region=region, content=content,
        spec={'previousServerOrigin': [182, 166], 'tilePositions': {}},
        report={'regions': {region: {}}})
    with pytest.raises(E.PlacementError, match='lost every spawn point'):
        E.update_markers(placement, {'coordinateTransform': {}})
    with pytest.raises(E.PlacementError, match='multiple default spawns'):
        E.update_markers(placement, {
            'coordinateTransform': {},
            'spawnPoints': [
                {'id': 'one', 'default': True, 'position': [0., 1., 0.]},
                {'id': 'two', 'default': True, 'position': [1., 2., 1.]},
            ],
        })


def test_unbound_authored_default_spawn_moves_and_restores_contract_arrival():
    """A visible default control seats the hub without a fabricated binding."""
    region = 'whitehorn_range'

    def publish(source_tile):
        world = types.SimpleNamespace(
            regions={region: {'center': [0., 0.]}},
            hub=lambda _region: np.array([99., 99.]))
        template = {
            'coordinateTransform': {'serverOrigin': [15, 15]},
            'spawnPoints': [{
                'id': 'continent-arrival', 'default': True,
                'position': [source_tile[0] - 14.5, 10., 14.5 - source_tile[1]],
                'serverTile': list(source_tile),
            }],
        }
        content = types.SimpleNamespace(
            authored_regions={region}, templates={region: template}, runtime_bindings={})
        spec = {'serverOrigin': [15, 15], 'previousServerOrigin': [15, 15],
                'tilePositions': {}, 'runtimeBindings': {},
                'runtimeBindingPositions': {}, 'runtimeBindingSourceTiles': {},
                'runtimeMarkerPositions': {}, 'portalPositions': {}, 'arrival': [15, 15]}
        report = {'placements': [], 'failures': [], 'regions': {region: {}}}
        placement = E.RegionPlacement(
            world, content, region, spec,
            {'heights': np.full((60, 60), 10., dtype=np.float32)},
            np.ones((30, 30), dtype=np.uint8), Sources, report)
        placement.connect_hub([112, 78], np.ones((30, 30), dtype=bool))
        manifest = copy.deepcopy(template)
        E.update_markers(placement, manifest)
        return spec, manifest, report

    original_spec, original_manifest, original_report = publish([7, 8])
    moved_spec, moved_manifest, moved_report = publish([9, 10])
    restored_spec, restored_manifest, restored_report = publish([7, 8])

    assert original_spec['arrival'] == [7, 8]
    assert moved_spec['arrival'] == [9, 10]
    assert restored_spec['arrival'] == original_spec['arrival']
    assert moved_manifest['spawnPoints'][0]['serverTile'] == [9, 10]
    assert moved_manifest['spawnPoints'][0]['position'] == [-5.5, 10., 4.5]
    assert moved_manifest['navigation']['defaultSpawn'] == 'continent-arrival'
    assert not moved_spec['runtimeBindings']
    assert original_manifest == restored_manifest
    assert original_report['failures'] == moved_report['failures'] == restored_report['failures'] == []


def test_legacy_flat_runtime_bindings_are_sunmane_only_and_never_override_a_qualified_map():
    aliases = {
        'door': {'marker': {'section': 'interactives', 'id': 'shared'}},
        'return': {'marker': {'section': 'interactives', 'id': 'shared'}},
    }
    legacy = types.SimpleNamespace(runtime_bindings=aliases)
    assert E.region_runtime_bindings(legacy, 'sunmane_steppe') == aliases
    assert E.region_runtime_bindings(legacy, 'amethyst_barrens') == {}

    qualified = types.SimpleNamespace(
        runtime_bindings=aliases,
        runtime_bindings_by_region={'amethyst_barrens': {'amethyst': {'marker': {}}}})
    assert E.region_runtime_bindings(qualified, 'sunmane_steppe') == {}
    assert set(E.region_runtime_bindings(qualified, 'amethyst_barrens')) == {'amethyst'}

    legacy_content = types.SimpleNamespace(
        templates={'sunmane_steppe': {'coordinateTransform': {'serverOrigin': [194, 292]}}})
    legacy_placement = types.SimpleNamespace(
        region='sunmane_steppe', content=legacy_content,
        spec={'previousServerOrigin': [194, 292], 'tilePositions': {}},
        report={'regions': {'sunmane_steppe': {}}})
    legacy_manifest = {
        'coordinateTransform': {},
        'spawnPoints': [{'id': 'legacy', 'position': [0., 4., 0.]}],
    }
    E.update_markers(legacy_placement, legacy_manifest)
    assert legacy_manifest['navigation']['defaultSpawn'] == 'legacy'
    assert legacy_manifest['coordinateTransform']['walkingHeight'] == 4.


def test_saved_runtime_edits_reach_normal_placement_with_distinct_endpoint_offsets():
    artifacts = A.CLIENT / 'godot-client/test-artifacts/sunmane-edit-regression'
    cave_ids = [
        'maps.txt:297:door:sunmane_steppe->sunmane_wind_caves@330:282',
        'maps.txt:298:return:sunmane_wind_caves->sunmane_steppe@327:283',
    ]
    runtime_id = 'maps.txt:1255:return:sunmane_gauntlet_2->sunmane_steppe@183:142'

    def placed(snapshot):
        content = types.SimpleNamespace(
            templates={A.SUNMANE: {'coordinateTransform': {'serverOrigin': [194, 292]}}})
        A.apply_runtime_bindings(content, snapshot)
        world = types.SimpleNamespace(regions={A.SUNMANE: {'center': [1200, 720]}})
        grid = np.ones((792, 792), dtype=np.uint8)
        spec = {'serverOrigin': [194, 292], 'previousServerOrigin': [194, 292],
                'tilePositions': {}, 'runtimeBindingPositions': {},
                'runtimeBindingSourceTiles': {}, 'runtimeMarkerPositions': {},
                'portalPositions': {}, 'arrival': [194, 292]}
        report = {'placements': [], 'failures': [], 'regions': {A.SUNMANE: {}}}
        collision = {'heights': np.zeros((1584, 1584), dtype=np.float32)}
        placement = E.RegionPlacement(
            world, content, A.SUNMANE, spec, collision, grid, Sources, report)
        for identity in cave_ids + [runtime_id]:
            source = content.runtime_bindings[identity]['source']
            assert placement.place(source['oldTile'], identity, 5, identity=identity) is not None
        assert report['failures'] == []
        return {identity: np.asarray(spec['runtimeBindingPositions'][identity], dtype=int)
                for identity in cave_ids + [runtime_id]}

    # Frozen edit fixtures predate the current production source digests and
    # persistent route claims. Reuse their immutable gameplay data for this
    # endpoint-offset test without representing them as buildable snapshots.
    def runtime_fixture(path):
        document = json.loads(path.read_text(encoding='utf-8'))
        return A.Snapshot(path, document, {}, path, path, 0, 0)
    before = placed(runtime_fixture(artifacts / 'before/continent-authoring.json'))
    after = placed(runtime_fixture(artifacts / 'after/continent-authoring.json'))
    assert not np.array_equal(before[cave_ids[0]], before[cave_ids[1]])
    assert np.array_equal(after[cave_ids[0]] - before[cave_ids[0]], [4, 3])
    assert np.array_equal(after[cave_ids[1]] - before[cave_ids[1]], [4, 3])
    assert np.array_equal(after[runtime_id] - before[runtime_id], [-5, -4])


def test_repeat_publication_resolves_prior_bound_tile_and_records_new_source_tile():
    identity = 'maps.txt:9:return:test_cave->sunmane_steppe@183:142'
    other_identity = 'maps.txt:9:door:sunmane_steppe->test_cave@184:143'
    binding = {
        'id': identity,
        'source': {'path': 'config/eloria/maps.txt', 'line': 9, 'oldTile': [183, 142]},
        'marker': {'section': 'runtimePoints', 'id': 'point'},
        'targetOffset': [0., 0., 0.],
    }
    other_binding = {
        'id': other_identity,
        # This seed tile intentionally collides with the first binding's prior
        # served tile. Prior publication identity must win on the next pass.
        'source': {'path': 'config/eloria/maps.txt', 'line': 9, 'oldTile': [201, 301]},
        'marker': {'section': 'runtimePoints', 'id': 'other'},
        'targetOffset': [0., 0., 0.],
    }
    content = types.SimpleNamespace(
        templates={'sunmane_steppe': {'coordinateTransform': {'serverOrigin': [194, 292]}}},
        runtime_bindings={identity: binding, other_identity: other_binding},
        runtime_binding_source_lines={('config/eloria/maps.txt', 9): [identity, other_identity]},
        runtime_binding_source_tiles={('config/eloria/maps.txt', (183, 142)): [identity],
                                      ('config/eloria/maps.txt', (201, 301)): [other_identity]},
        authored_runtime_points={('sunmane_steppe', identity): np.array([1207., 2., 713.])})
    world = types.SimpleNamespace(regions={'sunmane_steppe': {'center': [1200, 720]}})
    spec = {'serverOrigin': [194, 292], 'previousServerOrigin': [194, 292],
            'tilePositions': {}, 'runtimeBindingPositions': {},
            'runtimeBindingSourceTiles': {}, 'runtimeMarkerPositions': {},
            'portalPositions': {}, 'arrival': [194, 292]}
    previous = {'regions': {'sunmane_steppe': {
        'runtimeBindingPositions': {identity: [201, 301], other_identity: [205, 305]},
        'runtimeBindingSourceTiles': {identity: [183, 142], other_identity: [201, 301]},
    }}}
    report = {'placements': [], 'failures': [], 'regions': {'sunmane_steppe': {}}}
    p = E.RegionPlacement(
        world, content, 'sunmane_steppe', spec,
        {'heights': np.zeros((1584, 1584), dtype=np.float32)},
        np.ones((792, 792), dtype=np.uint8), Sources, report, previous=previous)

    # The live profile now contains the prior publication's output tile. The
    # exact prior binding identity carries it forward without a tile heuristic.
    assert p.runtime_identity('config/eloria/maps.txt', [201, 301], line=9) == identity
    assert p.runtime_identity('config/eloria/maps.txt', [201, 301]) == identity
    assert p.place([201, 301], identity, 5, identity=identity) is not None
    assert spec['runtimeBindingSourceTiles'][identity] == [201, 301]
    second_source = spec['runtimeBindingPositions'][identity]
    p.previous = {'regions': {'sunmane_steppe': {
        'runtimeBindingPositions': copy.deepcopy(spec['runtimeBindingPositions'])}}}
    assert p.runtime_identity('config/eloria/maps.txt', second_source, line=9) == identity
    assert p.runtime_identity('config/eloria/maps.txt', second_source) == identity


def test_runtime_binding_source_rewrite_distinguishes_shared_old_portal_tile():
    original = {
        'maps.txt': ('portal|sunmane_gauntlet|800|1|2|sunmane_steppe|183|142\n'
                     'portal|sunmane_gauntlet|799|1|2|sunmane_steppe|183|142\n'),
        'territories.txt': 'sunmane_steppe | Steppe | id | skill | 49 | 102 | 156 | 98 | 145 | 109 |\n',
    }
    rewritten = copy.deepcopy(original)
    bindings = {
        'return-a': {'source': {'path': 'config/eloria/maps.txt', 'line': 1, 'oldTile': [183, 142]},
                     'role': 'return'},
        'return-b': {'source': {'path': 'config/eloria/maps.txt', 'line': 2, 'oldTile': [183, 142]},
                     'role': 'return'},
        'territory': {'source': {'path': 'config/eloria/territories.txt', 'line': 1,
                                 'oldTile': [145, 109]}, 'role': 'territory'},
    }
    spec = {'runtimeBindings': bindings,
            'runtimeBindingPositions': {'return-a': [201, 301], 'return-b': [205, 305],
                                        'territory': [210, 310]},
            'runtimeBindingSourceTiles': {'return-a': [183, 142], 'return-b': [183, 142],
                                          'territory': [145, 109]}}
    shared = types.SimpleNamespace(
        integer_pair=lambda value, where: tuple(map(int, value)),
        field_number=lambda old, value: str(value))
    with mock.patch.object(E, 'server_modules'):
        pass
    # The publisher owns this source-line rewrite helper; load it with a tiny
    # shared stub so this unit never touches a live server checkout.
    publisher_path = HERE.parents[2] / 'tools/publish_diagonal_continent.py'
    module_spec = importlib.util.spec_from_file_location('publisher_runtime_binding_test', publisher_path)
    publisher = importlib.util.module_from_spec(module_spec)
    old_shared = sys.modules.get('publish_continent_geography')
    sys.modules['publish_continent_geography'] = shared
    try:
        module_spec.loader.exec_module(publisher)
        publisher.shared = shared
        publisher.rewrite_runtime_binding_sources(original, rewritten, {'sunmane_steppe': spec})
        certified = {
            'maps.txt': ('portal | sunmane_gauntlet | 800 | 31 | 315 | sunmane_steppe | 183 | 142\n'
                         'portal | sunmane_gauntlet | 799 | 26 | 11 | sunmane_steppe | 183 | 142\n'),
            'territories.txt': ('sunmane_steppe | Steppe | id | skill | 49 | 102 | 156 | 98 | '
                                '145 | 109 |\n'),
        }
        current = {
            'maps.txt': ('portal | whitehorn_range | 644 | 156 | amethyst_barrens | 64 | 142\n'
                         'portal | sunmane_gauntlet | 800 | 31 | 315 | sunmane_steppe | 226 | 319\n'
                         'portal | sunmane_gauntlet | 799 | 26 | 11 | sunmane_steppe | 227 | 319\n'),
            'territories.txt': ('sunmane_steppe | Steppe | id | skill | 119 | 292 | 210 | 281 | '
                                '199 | 292 |\n'),
        }
        current_rewritten = copy.deepcopy(current)
        republished = {
            'runtimeBindings': {
                'gauntlet-return': {
                    'source': {'path': 'config/eloria/maps.txt', 'line': 1,
                               'recordId': '800', 'oldTile': [183, 142]},
                    'role': 'return'},
                'gauntlet-vault-return': {
                    'source': {'path': 'config/eloria/maps.txt', 'line': 2,
                               'recordId': '799', 'oldTile': [183, 142]},
                    'role': 'return'},
                'territory': {
                    'source': {'path': 'config/eloria/territories.txt', 'line': 1,
                               'oldTile': [145, 109]},
                    'role': 'territory'},
            },
            'runtimeBindingPositions': {'gauntlet-return': [227, 320],
                                        'gauntlet-vault-return': [225, 321],
                                        'territory': [201, 293]},
            'runtimeBindingSourceTiles': {'gauntlet-return': [183, 142],
                                          'gauntlet-vault-return': [183, 142],
                                          'territory': [145, 109]},
        }
        previous = {'sunmane_steppe': {'baselineTilePositions': {
            '183:142': [226, 319], '145:109': [199, 292]},
            'runtimeBindingPositions': {'gauntlet-return': [226, 319],
                                        'gauntlet-vault-return': [227, 319]}}}
        publisher.rewrite_runtime_binding_sources(
            current, current_rewritten, {'sunmane_steppe': republished},
            previous_placements=previous, certified_texts=certified)
    finally:
        if old_shared is None:
            sys.modules.pop('publish_continent_geography', None)
        else:
            sys.modules['publish_continent_geography'] = old_shared
    assert rewritten['maps.txt'].splitlines() == [
        'portal|sunmane_gauntlet|800|1|2|sunmane_steppe|201|301',
        'portal|sunmane_gauntlet|799|1|2|sunmane_steppe|205|305']
    assert '|210|310|' in rewritten['territories.txt']
    assert current_rewritten['maps.txt'].splitlines() == [
        'portal | whitehorn_range | 644 | 156 | amethyst_barrens | 64 | 142',
        'portal | sunmane_gauntlet | 800 | 31 | 315 | sunmane_steppe |227|320',
        'portal | sunmane_gauntlet | 799 | 26 | 11 | sunmane_steppe |225|321']
    assert '|201|293|' in current_rewritten['territories.txt']


def placement(grid=None, preferred=None, hub=None):
    grid = np.ones((30, 30), dtype=np.uint8) if grid is None else grid
    template = {'coordinateTransform': {'serverOrigin': [15, 15]}}
    world = types.SimpleNamespace(regions={'test': {'center': [100, 200]}})
    if hub is not None:world.hub=lambda region:np.asarray(hub,float)
    content = types.SimpleNamespace(templates={'test': template},
        mapped_point=lambda region, point, node=None, landmark=None: np.array(point)+[100, 10, 200])
    spec = {'serverOrigin': [15,15], 'previousServerOrigin': [15,15], 'tilePositions': {},
            'portalPositions': {}, 'arrival': [15,15]}
    report = {'placements': [], 'failures': [], 'regions': {'test': {}}}
    collision = {'heights': np.full((60,60),10,dtype=np.float32)}
    p = E.RegionPlacement(world, content, 'test', spec, collision, grid, Sources, report)
    p.connect_hub([15,15],preferred)
    return p


def test_only_build_regenerated_invasion_profile_skips_static_point_remapping(tmp_path):
    seen = []
    p = placement()
    original_place = p.place

    def record_place(old, label, *args, **kwargs):
        seen.append((label, list(old)))
        return original_place(old, label, *args, **kwargs)

    p.place = record_place
    shared = types.SimpleNamespace(
        RULES={}, rewrite_profile=lambda text, rule, mappings: (text, 0),
        rewrite_definition=lambda text, mappings: (
            mappings['test']['_native_mapper']([6, 7]), 1))
    publisher = types.SimpleNamespace(
        CONTENT={}, transform_tile=lambda old, spec: old,
        remap_metadata=lambda *args: None,
        rewrite_gameplay_source=lambda text, kind, mappings: text)

    E.collect_gameplay_points(
        tmp_path,
        {
            'spawn_groups/invasion/invasion_nymara.def': '[spawn]\\n',
            'spawn_groups/ordinary.def': '[spawn]\\n',
            'client_content_manifest.json': '{"maps": []}',
        }, {'test': p},
        {group: {'test': []} for group in ('npcs', 'harvest', 'spawns', 'interactives')},
        shared, publisher)

    assert seen == [('spawn_groups/ordinary.def', [6, 7])]


class ServedProfileTests(unittest.TestCase):
    def test_repeat_profile_reconstructs_the_explicit_runtime_portal_alias_used_by_definitions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); server = root/'server'; baseline = root/'baseline'
            relative = 'config/eloria/instances/sunmane_gauntlet_low.def'
            for base, tile in ((baseline, [183, 142]), (server, [225, 320])):
                path = base/relative; path.parent.mkdir(parents=True)
                path.write_text(f'exit_map: sunmane_steppe\nexit_x: {tile[0]}\nexit_y: {tile[1]}\n')
            identity = 'maps.txt:1266:return:sunmane_gauntlet_3->sunmane_steppe@183:142'
            previous = {'connections': [], 'regions': {'sunmane_steppe': {
                'baselineTilePositions': {'183:142': [226, 319]},
                'baselineServerOrigin': [124, 125], 'serverOrigin': [194, 292],
                'baselineContentTransform': {'scale': 1., 'sourceCenter': [0, 0], 'targetCenter': [0, 0]},
                'baselineRemovedInteractiveIds': [],
                'runtimeBindingSourceTiles': {identity: [183, 142]},
                'portalPositions': {
                    'first-return': {'oldTile': [226, 319], 'tile': [226, 319], 'runtimeBindingId': 'first'},
                    'gauntlet-return': {'oldTile': [226, 319], 'tile': [225, 320], 'runtimeBindingId': identity},
                },
            }}}
            # The earlier alias also needs complete provenance; its value is
            # deliberately overwritten by the later, certified gauntlet alias.
            previous['regions']['sunmane_steppe']['runtimeBindingSourceTiles']['first'] = [183, 142]
            def transform(point, spec):
                return spec['tilePositions'].get(f'{point[0]}:{point[1]}', point)
            def rewrite_definition(text, mappings):
                tile = mappings['sunmane_steppe']['_native_mapper']([183, 142])
                lines = text.splitlines()
                lines[1] = f'exit_x: {tile[0]}'; lines[2] = f'exit_y: {tile[1]}'
                return '\n'.join(lines) + '\n', 1
            shared = types.SimpleNamespace(RULES={}, rewrite_definition=rewrite_definition)
            publisher = types.SimpleNamespace(CONTENT={}, transform_tile=transform)
            E.verify_current_profile(server, baseline, {'files': {relative: 'immutable'}},
                                     previous, shared, publisher)
            (server/relative).write_text('exit_map: sunmane_steppe\nexit_x: 225\nexit_y: 319\n')
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, {'files': {relative: 'immutable'}},
                                         previous, shared, publisher)

    def test_repeat_profile_reconstructs_distinct_record_bound_portal_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); server = root/'server'; baseline = root/'baseline'
            relative = 'config/eloria/maps.txt'
            original = ('portal | sunmane_gauntlet | 800 | 31 | 315 | sunmane_steppe | 183 | 142\n'
                        'portal | sunmane_gauntlet | 799 | 26 | 11 | sunmane_steppe | 183 | 142\n')
            served = ('portal | sunmane_gauntlet | 800 | 31 | 315 | sunmane_steppe | 226 | 319\n'
                      'portal | sunmane_gauntlet | 799 | 26 | 11 | sunmane_steppe | 225 | 320\n')
            for base, text in ((baseline, original), (server, served)):
                path = base/relative; path.parent.mkdir(parents=True); path.write_text(text)
            bindings = {
                'return-800': {'source': {'path': relative, 'line': 1}},
                'return-799': {'source': {'path': relative, 'line': 2}},
            }
            previous = {'connections': [], 'regions': {'sunmane_steppe': {
                'baselineTilePositions': {'183:142': [226, 319]},
                'baselineServerOrigin': [124, 125], 'serverOrigin': [194, 292],
                'baselineContentTransform': {'scale': 1., 'sourceCenter': [0, 0], 'targetCenter': [0, 0]},
                'baselineRemovedInteractiveIds': [], 'runtimeBindings': bindings,
                'runtimeBindingSourceTiles': {'return-800': [183, 142], 'return-799': [183, 142]},
                'runtimeBindingPositions': {'return-800': [226, 319], 'return-799': [225, 320]},
                'portalPositions': {
                    'return-800': {'oldTile': [226, 319], 'tile': [226, 319], 'runtimeBindingId': 'return-800'},
                    'return-799': {'oldTile': [226, 319], 'tile': [225, 320], 'runtimeBindingId': 'return-799'},
                },
            }}}
            def transform(point, spec):
                return spec['tilePositions'].get(f'{point[0]}:{point[1]}', point)
            def rewrite_profile(text, rules, mappings):
                tile = mappings['sunmane_steppe']['_native_mapper']([183, 142])
                return text.replace('183 | 142', f'{tile[0]} | {tile[1]}'), 2
            def rewrite_bound(originals, rewritten, specs, **unused):
                lines = rewritten['maps.txt'].splitlines()
                for identity, binding in bindings.items():
                    tile = specs['sunmane_steppe']['runtimeBindingPositions'][identity]
                    fields = lines[binding['source']['line'] - 1].split('|')
                    fields[-2:] = [f' {tile[0]} ', f' {tile[1]}']
                    lines[binding['source']['line'] - 1] = '|'.join(fields)
                rewritten['maps.txt'] = '\n'.join(lines) + '\n'
            shared = types.SimpleNamespace(RULES={'maps.txt': object()}, rewrite_profile=rewrite_profile)
            publisher = types.SimpleNamespace(
                CONTENT={}, transform_tile=transform,
                rewrite_runtime_binding_sources=rewrite_bound,
                replace_crossings=lambda text, connections, specs: (text, []))
            E.verify_current_profile(server, baseline, {'files': {relative: 'immutable'}},
                                     previous, shared, publisher)
            (server/relative).write_text(served.replace('225 | 320', '225 | 319'))
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, {'files': {relative: 'immutable'}},
                                         previous, shared, publisher)

    def test_build_regenerated_invasion_file_is_accepted_only_when_its_own_check_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); server = root/'server'; baseline = root/'baseline'
            relative = 'config/eloria/spawn_groups/invasion/invasion_nymara.def'
            for base, text in ((baseline, 'old waves'), (server, 'regenerated waves')):
                (base/relative).parent.mkdir(parents=True); (base/relative).write_text(text)
            (server/'tools').mkdir(); tool = server/'tools/generate_nymara_invasion_spawns.py'
            tool.write_text('import sys; sys.exit(0)')
            certificate = {'files': {relative: 'x'}}; previous = {'regions': {}, 'connections': []}
            shared = types.SimpleNamespace(RULES={}, rewrite_definition=lambda text, mappings: (text, None))
            publisher = types.SimpleNamespace(CONTENT={}, transform_tile=None)
            E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
            tool.write_text('import sys; sys.exit(1)')
            with self.assertRaisesRegex(ValueError, 'deterministic regeneration'):
                E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
            # Any other edited authored file is still rejected, even when the regenerator agrees.
            tool.write_text('import sys; sys.exit(0)')
            other = 'config/eloria/spawn_groups/invasion/bosses.def'
            (baseline/other).write_text('a'); (server/other).write_text('b'); certificate['files'][other] = 'y'
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)


    def test_a_coordinate_padded_by_an_earlier_publication_is_not_a_content_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); server = root/'server'; baseline = root/'baseline'
            relative = 'config/eloria/harvesting.txt'
            (baseline/relative).parent.mkdir(parents=True); (server/relative).parent.mkdir(parents=True)
            (baseline/relative).write_text('node | four_gates | 2506 | 240 | 110 | Sage\n')
            # The tenth publication padded 79 to the width of 110; the eleventh rewrote that text in place.
            (server/relative).write_text('node | four_gates | 2506 | 329 |  115 | Sage\n')
            certificate = {'files': {relative: 'x'}}; previous = {'regions': {}, 'connections': []}
            shared = types.SimpleNamespace(RULES={}, rewrite_definition=lambda text, mappings: (text, None))
            publisher = types.SimpleNamespace(CONTENT={'harvesting.txt': None}, transform_tile=None,
                content_source_tile_counts=lambda texts: {},
                rewrite_content=lambda text, name, specs, flag, counts: ('node | four_gates | 2506 | 329 | 115 | Sage\n', None))
            E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
            (server/relative).write_text('node | four_gates | 2506 | 329 |  116 | Sage\n')
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)


class StaticBodyTests(unittest.TestCase):
    def test_a_static_body_never_seals_a_pocket_and_withdraws_only_its_own_tile(self):
        grid = np.ones((30, 30), dtype=np.uint8); grid[:, 20] = 0; grid[10, 20] = 1  # one-tile mouth at (20, 10)
        p = placement(grid)
        before = p.reachable.copy(); self.assertTrue(before[15, 25], 'the pocket is hub-connected through its mouth')
        tile = p.place([20, 10], 'npcs.txt:1:Guard', 12, reserve=True, identity='Guard', body=True)
        self.assertEqual(tile, [19, 9])
        self.assertTrue(p.reachable[15, 25], 'the pocket stays connected'); self.assertFalse(p.reachable[9, 19])
        self.assertEqual(int(before.sum()) - int(p.reachable.sum()), 1)
        rejected = [row['rejectedTile'] for row in p.report['regions']['test']['bodyRelocations']]
        self.assertEqual(rejected, [[20, 10], [19, 10], [21, 10]], 'the mouth and both tiles that guard it are rejected in distance order')
        self.assertEqual(p.records[-1]['tile'], [19, 9]); self.assertIn((19, 9), p.bodies)
        # Open ground keeps the exact expected tile and loses exactly that tile.
        p = placement(); before = p.reachable.copy()
        self.assertEqual(p.place([5, 5], 'npcs.txt:2:Reeve', 12, reserve=True, identity='Reeve', body=True), [5, 5])
        self.assertEqual(int(before.sum()) - int(p.reachable.sum()), 1)
        self.assertNotIn('bodyRelocations', p.report['regions']['test'])


class PlacementTests(unittest.TestCase):
    def test_named_actor_relocation_does_not_move_other_content_on_the_old_tile(self):
        p = placement()
        p.content.authored_actor_points = {('test','Quay Master Belen Tarr'): [103.5,19.,201.5]}
        np.testing.assert_array_equal(p.expected([12,17],identity='Quay Master Belen Tarr'),[18,13])
        np.testing.assert_array_equal(p.expected([12,17],identity='Other NPC'),[12,17])
        np.testing.assert_array_equal(p.expected([12,17]),[12,17])

    def test_explicit_relocated_door_and_return_use_exact_semantic_overrides(self):
        p = placement()
        p.content.authored_server_points = {('test', (12, 17)): np.array([103.5, 19., 201.5]),
                                           ('test', (12, 19)): np.array([102.5, 18.9, 202.5])}
        p.entry_by_identity['door'] = {'node': 'FormerDoor'}
        with mock.patch.object(p.content, 'mapped_point', side_effect=AssertionError('stale architectural mapping')):
            np.testing.assert_array_equal(p.expected([12, 17], identity='door'), [18, 13])
            np.testing.assert_array_equal(p.expected([12, 19]), [17, 12])
        # Adjacent coordinates and another region's override remain ordinary.
        p.content.authored_server_points[('neighbour', (13, 17))] = [900, 10, 900]
        np.testing.assert_array_equal(p.expected([13, 17]), [13, 17])

    def test_invalid_authored_semantic_position_is_not_silently_remapped(self):
        p = placement()
        p.content.authored_server_points = {('test', (12, 17)): [float('nan'), 1, 2]}
        with self.assertRaisesRegex(ValueError, 'invalid authored semantic position'):
            p.expected([12, 17])

    def test_parent_and_child_revision_metadata_agree_without_early_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);child_path = root/'chunks/00_01/world.json'
            child_path.parent.mkdir(parents=True)
            child_path.write_text('{"terrainRevision":"old","asset":{"glb":"world.glb"},"coordinateTransform":{"walkingHeight":1.0,"serverOrigin":[2,4]}}')
            original = child_path.read_bytes()
            collision = root/'collision.bin';collision.write_bytes(b'collision')
            manifest = {'terrainRevision': 'old', 'coordinateTransform': {'walkingHeight': 2.5, 'serverOrigin': [2, 4]},
                        'streamingChunks': {'chunks': [{'manifest': 'chunks/00_01/world.json'}]}}
            spec = {'terrainRevision': 'diagonal-spine-v1:'+'a'*64, 'collisionPath': str(collision)}
            children = E.revision_metadata(root/'world.json', manifest, spec, 'b'*64)
            self.assertEqual(child_path.read_bytes(), original)
            self.assertEqual(manifest['terrainRevision'], spec['terrainRevision'])
            self.assertEqual(manifest['streamingChunks']['terrainRevision'], spec['terrainRevision'])
            self.assertEqual(children[0][1]['terrainRevision'], spec['terrainRevision'])
            self.assertEqual(children[0][1]['continentPublication'], manifest['continentPublication'])
            self.assertEqual(children[0][1]['asset']['glb'], 'world.glb')
            # Contracts refine the arrival walking height after export; chunks follow the parent frame exactly.
            self.assertEqual(children[0][1]['coordinateTransform'], manifest['coordinateTransform'])
            self.assertIsNot(children[0][1]['coordinateTransform'], manifest['coordinateTransform'])

    def test_terrain_revision_is_stable_but_tracks_geometry_collision_and_occupancy(self):
        with tempfile.TemporaryDirectory() as folder:
            collision_path = Path(folder)/'collision.bin'
            collision_path.write_bytes(b'original exact collision')
            spec = {'serverOrigin': [15,15], 'serverCells': [30,30], 'translation': [100,0,200],
                    'arrival': [15,15], 'contentPositions': {'npcs': {'Nesh': [16,15]}},
                    'collisionPath': str(collision_path)}
            collision = {'collision': {'sourceGlbSha256': 'a'*64, 'heightEncoding': {'origin': 0, 'step': .2}}}
            grid = np.full((30,30),10,np.uint8)
            original = E.terrain_revision(spec, collision, grid)
            self.assertRegex(original, r'^diagonal-spine-v1:[a-f0-9]{64}$')
            same = dict(reversed(list(spec.items())))
            same.update(previousServerOrigin=[2,3], sourcePublicationSha256='republication', baselineTilePositions={'1:2':[3,4]})
            self.assertEqual(original, E.terrain_revision(same, collision, np.asfortranarray(grid)))
            changed = copy.deepcopy(collision);changed['collision']['sourceGlbSha256'] = 'b'*64
            self.assertNotEqual(original, E.terrain_revision(spec, changed, grid))
            changed = copy.deepcopy(spec);changed['contentPositions']['npcs']['Nesh'] = [17,15]
            self.assertNotEqual(original, E.terrain_revision(changed, collision, grid))
            changed_grid = grid.copy();changed_grid[15,18] = 0
            self.assertNotEqual(original, E.terrain_revision(spec, collision, changed_grid))
            collision_path.write_bytes(b'revised half-cell collision')
            self.assertNotEqual(original, E.terrain_revision(spec, collision, grid))

    def test_arrival_uses_real_main_ground_near_isolated_upper_floor(self):
        grid=np.ones((30,30),np.uint8);grid[14:16,14:16]=25
        p=placement(grid,preferred=grid==1)
        self.assertEqual(int(p.reachable.sum()),896)
        self.assertLess(p.report['regions']['test']['arrivalSelection']['displacementMetres'],2)
        self.assertFalse(p.report['failures'])

    def test_inhabited_hub_uses_unchanged_geographic_server_frame(self):
        grid=np.zeros((30,30),np.uint8);grid[:8,:9]=1;grid[14:16,14:16]=1
        preferred=np.zeros_like(grid,bool);preferred[:8,:9]=True
        p=placement(grid,preferred,hub=[89.5,211.5])
        self.assertEqual(p.spec['arrival'],[4,3])
        self.assertEqual(p.report['regions']['test']['arrivalSelection']['displacementMetres'],0)
        self.assertEqual(int(p.reachable.sum()),72)
        self.assertEqual(p.world.regions['test']['center'],[100,200])
        self.assertEqual(p.spec['serverOrigin'],[15,15])
        np.testing.assert_array_equal(p.expected([15,15]),[15,15])
        self.assertFalse(p.report['failures'])

    def test_inhabited_hub_keeps_twelve_metre_arrival_budget(self):
        grid=np.zeros((30,30),np.uint8);grid[:8,:9]=1
        p=placement(grid,grid!=0,hub=[115,185])
        self.assertFalse(p.reachable.any())
        self.assertEqual(p.report['failures'][0]['maximumDisplacementMetres'],12)
        self.assertIn('within 12 m',p.report['failures'][0]['reason'])

    def test_actual_world_hub_preserves_seed_and_default_for_other_regions(self):
        from world_layout import World
        world=World.__new__(World)
        world.plan={'inhabited_hubs':{'mirrorhold':[773.5,802.5]}}
        world.regions={'mirrorhold':{'center':[840,650]},'other':{'center':[100,200]}}
        np.testing.assert_array_equal(world.hub('mirrorhold'),[773.5,802.5])
        np.testing.assert_array_equal(world.hub('other'),[100,200])
        self.assertEqual(world.regions['mirrorhold']['center'],[840,650])

    def test_fold_requires_each_of_four_actual_subcells(self):
        class Transform:
            def __init__(self, **kwargs): self.__dict__.update(kwargs)
        sources = types.SimpleNamespace(GridTransform=Transform, requantise=lambda g,t:g.astype(np.int32))
        sync = types.SimpleNamespace(choose_stage=lambda g:(1,g!=0,{}),rescale=lambda g,f:g.astype(np.uint8))
        for dy, dx in ((0,0),(0,1),(1,0),(1,1)):
            grid = np.full((8,8),7,dtype=np.uint8)
            grid[2+dy,4+dx] = 0
            result, _, _, _ = E.fold_server_grid({'grid': grid, 'collision': {'heightEncoding': {'origin':0,'step':.2}}},sources,sync)
            self.assertEqual(result[1,2],0)
            self.assertEqual(int((result==0).sum()),1)

    def test_half_cell_coordinates_round_trip(self):
        p=placement()
        np.testing.assert_array_equal(p.expected([8,20]),[8,20])
        self.assertEqual(p.local_position([8,20]),[-6.5,10.,-5.5])

    def test_doors_cannot_jump_to_a_disconnected_island(self):
        grid=np.ones((30,30),dtype=np.uint8);grid[:,19]=0
        p=placement(grid)
        self.assertIsNone(p.place([25,15],'isolated doorway',5))
        self.assertEqual(len(p.report['failures']),1)
        self.assertNotIn('25:15',p.spec['tilePositions'])

    def test_a_nearby_door_is_resolved_once_for_bound_interactive(self):
        p=placement();p.grid[4,4]=0;p.reachable[4,4]=False
        first=p.place([4,4],'door',5,reserve=True)
        second=p.place([4,4],'interactive',12,reserve=True)
        self.assertEqual(first,second)
        self.assertEqual(p.spec['tilePositions']['4:4'],first)
        self.assertFalse(p.report['failures'])

    def test_even_creature_footprint_leans_positive(self):
        p=placement();p.reachable[6,7]=False
        self.assertFalse(p.valid((6,6),(2,1)))
        self.assertTrue(p.valid((5,6),(2,1)))

    def test_storage_body_cannot_cut_the_only_door_route(self):
        grid=np.zeros((30,30),dtype=np.uint8);grid[10:20,2:18]=1;grid[14,18:28]=1
        p=placement(grid)
        p.check_fixed([26,14],'door')
        self.assertFalse(p.report['failures'])
        p.stamp_storage([[21,14]])
        self.assertTrue(any('fixed route' in e['record'] for e in p.report['failures']))
        self.assertFalse(p.reachable[14,26])

    def test_map_records_preserve_interior_local_coordinates(self):
        p=placement();p.reserved[:]=False
        text='portal | test | 4 | 5 | room | 91 | 92\nportal | room | 93 | 94 | test | 6 | 7\nportal | test | 28 | 15 | other | 1 | 15\n'
        other=placement();other.region='other'
        E.place_doors(text,{'test':p,'other':other},[])
        self.assertEqual(set(p.spec['tilePositions']),{'15:15','4:5','6:7'})
        self.assertNotIn('91:92',p.spec['tilePositions'])
        self.assertNotIn('28:15',p.spec['tilePositions'])

    def test_marker_update_keeps_target_room_and_uses_final_floor(self):
        p=placement();p.content.templates['test']['portals']=[{'id':'door','serverTile':[4,5],'targetMap':'room','destinationTile':[91,92]}]
        p.spec['tilePositions']['4:5']=[6,7]
        manifest={'portals':[{'id':'door','serverTile':[4,5],'position':[1,2,3],'targetMap':'room','destinationTile':[91,92]}], 'coordinateTransform': {}}
        E.update_markers(p,manifest)
        self.assertEqual(manifest['portals'][0]['position'],[-8.5,10.,7.5])
        self.assertEqual(manifest['portals'][0]['destinationTile'],[91,92])
        self.assertEqual(manifest['spawnPoints'][0]['serverTile'],p.spec['arrival'])

    def test_reexport_maps_current_tiles_through_original_baseline(self):
        first={'regions':{'test':{'tilePositions':{'4:5':[14,15],'6:7':[16,17]},
            'previousServerOrigin':[15,15],'serverOrigin':[25,25],
            'contentTransform':{'scale':.78,'sourceCenter':[0,0],'targetCenter':[0,0]},
            'removedInteractiveIds':['20'],'portalPositions':{'door':{'oldTile':[4,5],'tile':[14,15]}}}}}
        E.rebase_publication(first,None)
        second={'regions':{'test':{'tilePositions':{'4:5':[24,25],'6:7':[26,27]},
            'previousServerOrigin':[15,15],'serverOrigin':[35,35],
            'contentTransform':{'scale':.78,'sourceCenter':[0,0],'targetCenter':[0,0]},
            'removedInteractiveIds':['20'],'portalPositions':{'door':{'oldTile':[4,5],'tile':[24,25]}}}}}
        E.rebase_publication(second,first)
        spec=second['regions']['test']
        self.assertEqual(spec['tilePositions'],{'14:15':[24,25],'16:17':[26,27]})
        self.assertEqual(spec['baselineTilePositions'],{'4:5':[24,25],'6:7':[26,27]})
        self.assertEqual(spec['previousServerOrigin'],[25,25])
        self.assertEqual(spec['portalPositions']['door']['oldTile'],[14,15])
        self.assertEqual(spec['removedInteractiveIds'],[])
        self.assertEqual(spec['baselineRemovedInteractiveIds'],['20'])

    def test_reexport_rejects_ambiguous_previously_collapsed_points(self):
        prior={'regions':{'test':{'baselineTilePositions':{'4:5':[14,15],'6:7':[14,15]},'serverOrigin':[25,25]}}}
        new={'regions':{'test':{'tilePositions':{'4:5':[24,25],'6:7':[26,27]},
            'previousServerOrigin':[15,15],'serverOrigin':[35,35],
            'contentTransform':{},'removedInteractiveIds':[],'portalPositions':{}}}}
        with self.assertRaisesRegex(ValueError,'collapsed'):
            E.rebase_publication(new,prior)

    def test_a_record_the_baseline_gained_is_rebased_from_its_content_transform_estimate(self):
        # The previous publication never placed 6:7; the reconciled profile serves it at that
        # publication's content transform of the original cell (16,17), where the rewrite finds it.
        prior={'regions':{'test':{'baselineTilePositions':{'4:5':[14,15]},'serverOrigin':[25,25],'baselineServerOrigin':[15,15],
            'baselineContentTransform':{'sourceCenter':[0,0],'targetCenter':[0,0],'scale':1}}}}
        new={'regions':{'test':{'tilePositions':{'4:5':[24,25],'6:7':[26,27]},
            'previousServerOrigin':[15,15],'serverOrigin':[35,35],
            'contentTransform':{},'removedInteractiveIds':[],'portalPositions':{}}}}
        E.rebase_publication(new,prior)
        spec=new['regions']['test']
        self.assertEqual(spec['tilePositions'],{'14:15':[24,25],'16:17':[26,27]})
        self.assertEqual(spec['estimatedSourceTiles'],['6:7'])
        self.assertEqual(spec['baselineTilePositions'],{'4:5':[24,25],'6:7':[26,27]})

    def test_published_server_without_baseline_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'config/eloria/client_content_manifest.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'diagonalContinent':{'publicationSha256':'a'*64}}))
            with self.assertRaisesRegex(ValueError,'already uses diagonal'):
                E.frozen_profile(root,types.SimpleNamespace(RULES={}),root/'baseline')

    def test_snapshot_rejects_original_coordinate_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'config/eloria/client_content_manifest.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'maps':[]}))
            npc=root/'config/eloria/npcs.txt';npc.write_text('npc | Keeper | test | 4 | 5')
            baseline,_,_=E.frozen_profile(root,types.SimpleNamespace(RULES={'npcs.txt':[]}),root/'baseline')
            (baseline/'config/eloria/npcs.txt').write_text('npc | Keeper | test | 99 | 99')
            with self.assertRaisesRegex(ValueError,'Immutable baseline changed'):
                E.frozen_profile(root,types.SimpleNamespace(RULES={'npcs.txt':[]}),root/'baseline')


class ExportTests(unittest.TestCase):
    def test_collision_cache_reuses_only_identical_geometry_and_world_fields(self):
        import collision_export
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);glb=root/'world.glb';glb.write_bytes(b'synthetic geometry')
            for name in ('collision_export.py','world_layout.py','storage_bounds.py','terrain_export.py','landscape.py','crossings.py'):(root/name).write_text('source')
            world=types.SimpleNamespace(ids=['test'],regions={'test':{'center':[0,0]}},connections=[],
                address=lambda r:([2,2],[4,4]),height=np.ones((3,3)),owner=np.zeros((2,2),np.uint8),
                water={'mask':np.zeros((3,3),bool),'surface':np.zeros((3,3))},x0=0,z0=0,x1=4,z1=4)
            manifest={'collision':{'nodeNames':['wall']},'navigation':{'surfaceNodePrefixes':['Walk_']}}
            result={'grid':np.ones((8,8),np.uint8),'heights':np.ones((8,8),np.float32),
                    'walkable':np.ones((8,8),bool),'collision':{'authoredSurfaceExport':True}}
            with mock.patch.object(E,'HERE',root),mock.patch.object(collision_export,'export_collision',return_value=result) as raster:
                E.cached_collision(world,'test',manifest,glb,root/'collision.bin',root,E.collision_world_digest(world))
                reread=E.cached_collision(world,'test',manifest,glb,root/'collision.bin',root,E.collision_world_digest(world))
                self.assertEqual(raster.call_count,1)
                np.testing.assert_array_equal(reread['heights'],result['heights'])
                world.water['mask'][1,1]=True
                E.cached_collision(world,'test',manifest,glb,root/'collision.bin',root,E.collision_world_digest(world))
                self.assertEqual(raster.call_count,2)
                glb.write_bytes(b'changed structural mesh')
                E.cached_collision(world,'test',manifest,glb,root/'collision.bin',root,E.collision_world_digest(world))
                self.assertEqual(raster.call_count,3)
                (root/'terrain_export.py').write_text('changed physical shoreline')
                E.cached_collision(world,'test',manifest,glb,root/'collision.bin',root,E.collision_world_digest(world))
                self.assertEqual(raster.call_count,4)
                world.plan={'sea_level':1.,'rivers':[],'lakes':[]}
                E.cached_collision(world,'test',manifest,glb,root/'collision.bin',root,E.collision_world_digest(world))
                self.assertEqual(raster.call_count,5)

    def fixture(self, root, doorway=False):
        sys.path.insert(0,str(E.TOOLS))
        import publish_continent_geography as shared
        import publish_diagonal_continent as publisher
        profile=root/'config/eloria';profile.mkdir(parents=True)
        for name in shared.RULES:
            (profile/name).write_text('')
        (profile/'creatures.txt').write_text('')
        if doorway:
            (profile/'maps.txt').write_text('portal | test | 25 | 15 | room | 4 | 5\n')
        source={'maps':[{'id':'test','arrival':[15,15]}],
                'continentGeography':{'regions':{'test':{'serverOrigin':[15,15]}}}}
        E.write_json(profile/'client_content_manifest.json',source)
        files={p.relative_to(root).as_posix():E.sha(p) for p in profile.iterdir()}
        baseline=root/'snapshot.json';E.write_json(baseline,{'files':files})
        manifest={'asset':{'glb':'world.glb'},'coordinateTransform':{'serverOrigin':[15,15],'serverCells':[30,30]}}
        package=root/'client/test';package.mkdir(parents=True)
        E.write_json(package/'world.json',manifest)
        output=root/'output';output.mkdir()
        (output/'continent.glb').write_bytes(b'synthetic-master')
        E.write_json(output/'export.json',{'masterPath':str(output/'continent.glb'),'masterSha256':E.sha(output/'continent.glb'),
            'regions':{'test':{'world':str(package/'world.json')}}})
        half=np.ones((60,60),dtype=np.uint8)
        if doorway:half[:,38:40]=0
        (package/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,60,60)+half.tobytes())
        # The contracts stage declares crossings from the package's own floors; this one has none.
        sys.path.insert(0,str(HERE.parent/'_toolkit'))
        from amberwood import gltf as G
        G.GltfBuilder().write_glb(str(package/'world.glb'))
        collision={'grid':half,'heights':np.full((60,60),10,np.float32),
                   'collision':{'sourceGlbSha256':'a'*64,'heightEncoding':{'origin':9.8,'step':.2},'gridAlignment':'tile-centres-v1','authoredSurfaceExport':True}}
        world=types.SimpleNamespace(ids=['test'],regions={'test':{'center':[0,0]}},publication_connections=[],
            collision_exports={'test':collision},address=lambda r:([15,15],[30,30]))
        content=types.SimpleNamespace(templates={'test':copy.deepcopy(manifest)},scales={'test':1},source_centers={'test':[0,0]},
            transforms={'test':None},world=world,mapped_point=lambda r,p,node=None,landmark=None:np.array(p,float))
        # The published contentTransform is read off Content's own mapping; here it is the identity.
        content.mapped_xz=lambda region,points:C.Content.mapped_xz(content,region,points)
        class Transform:
            def __init__(self,**kwargs):self.__dict__.update(kwargs)
        sources=types.SimpleNamespace(GridTransform=Transform,requantise=lambda g,t:g.astype(np.int32),reachable_from=Sources.reachable_from)
        sync=types.SimpleNamespace(choose_stage=lambda g:(1,g!=0,{}),rescale=lambda g,f:g.astype(np.uint8),CLIMB_LIMIT=2)
        modules={'collision_sources':sources,'sync_authored_collision':sync,'publish_continent_geography':shared,
                 'publish_diagonal_continent':publisher,'eloria.creatures':types.SimpleNamespace(load_creatures=lambda p:{})}
        patches=[mock.patch.object(E,'HERE',root/'authored'),mock.patch.object(E,'server_modules',return_value=modules),
                 mock.patch.object(E,'frozen_profile',return_value=(root,{'files':files},source)),
                 mock.patch.object(E,'freeze_return_targets',return_value=[])]
        return world,content,{'test':manifest},output,patches

    def test_complete_export_installs_matching_manifest_and_hash_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            world,content,manifests,output,patches=self.fixture(root)
            with patches[0],patches[1],patches[2],patches[3]:
                publication=E.export_contracts(world,content,manifests,output,root)
            self.assertTrue((output/'publication.json').exists())
            spec=publication['regions']['test']
            self.assertRegex(spec['terrainRevision'], r'^diagonal-spine-v1:[a-f0-9]{64}$')
            self.assertEqual(manifests['test']['terrainRevision'], spec['terrainRevision'])
            self.assertEqual(manifests['test']['continentPublication']['terrainRevision'], spec['terrainRevision'])
            self.assertIn('baselineTilePositions',spec)
            self.assertEqual(spec['tileHeights'][E.key(spec['arrival'])],10)
            self.assertEqual(manifests['test']['spawnPoints'][0]['serverTile'],spec['arrival'])
            history=root/'authored/publication-history'/f'{E.sha(output/"publication.json")}.json'
            self.assertEqual(history.read_bytes(),(output/'publication.json').read_bytes())

    def test_disconnected_door_writes_diagnostic_and_no_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            world,content,manifests,output,patches=self.fixture(root,doorway=True)
            before=copy.deepcopy(manifests)
            with patches[0],patches[1],patches[2],patches[3]:
                with self.assertRaises(E.PlacementError):
                    E.export_contracts(world,content,manifests,output,root)
            self.assertFalse((output/'publication.json').exists())
            self.assertEqual(manifests,before)
            report=json.loads((output/'contract-placement-report.json').read_text())
            self.assertFalse(report['ready'])
            self.assertIn('maps.txt',report['failures'][0]['record'])


if __name__=='__main__': unittest.main()

class ServedTileContinuityTests(unittest.TestCase):
    # Tiles away from the hub at (15,15), whose surroundings connect_hub reserves.
    def previous(self, tile, old='5:5'):
        return {'regions': {'test': {'baselineTilePositions': {old: list(tile)}}}}

    def test_a_point_keeps_its_previously_served_tile_within_budget(self):
        p = placement(); p.previous = self.previous([7, 7])
        self.assertEqual(p.place([5, 5], 'spawn', 5), [7, 7])
        self.assertEqual(p.records[-1]['tile'], [7, 7])

    def test_unbound_authored_territory_uses_certified_served_frame_and_still_requires_walkable_budget(self):
        p = placement(); p.content.authored_regions = {'test'}
        p.previous = self.previous([7, 7])
        p.content.mapped_point = lambda *args: np.array([1000., 0., 1000.])
        self.assertEqual(p.place([5, 5], 'territories.txt', 5), [7, 7])
        self.assertEqual(p.records[-1]['oldTile'], [5, 5])
        grid = np.zeros((30, 30), dtype=np.uint8); grid[15, 15] = 1
        p = placement(grid); p.content.authored_regions = {'test'}
        p.previous = self.previous([7, 7])
        p.content.mapped_point = lambda *args: np.array([1000., 0., 1000.])
        self.assertIsNone(p.place([5, 5], 'territories.txt', 5))
        self.assertTrue(any(f['record'] == 'territories.txt' for f in p.failures))
        p = placement(); p.content.authored_regions = {'test'}
        p.previous = self.previous([20, 5])
        self.assertEqual(p.place([5, 5], 'territories.txt', 5), [5, 5])
        p = placement(); p.content.authored_regions = {'test'}
        p.previous = self.previous([7, 7], old='other:key')
        p.content.mapped_point = lambda *args: np.array([1000., 0., 1000.])
        self.assertIsNone(p.place([5, 5], 'territories.txt', 5))
        p = placement(); p.content.authored_regions = {'test'}
        p.previous = self.previous([7, 7])
        p.content.runtime_bindings = {'bound': {'marker': {'section': 'runtimePoints', 'id': 'bound'},
            'targetOffset': [0., 0., 0.]}}
        p.content.authored_runtime_points = {('test', 'bound'): np.array([94.5, 10., 205.5])}
        p.spec.update(runtimeBindingPositions={}, runtimeBindingSourceTiles={}, runtimeMarkerPositions={})
        self.assertEqual(p.place([5, 5], 'territories.txt', 5, identity='bound'), [9, 9])

    def test_a_blocked_or_distant_served_tile_falls_back_to_the_nearest_standing_point(self):
        grid = np.ones((30, 30), dtype=np.uint8); grid[7, 7] = 0
        p = placement(grid); p.previous = self.previous([7, 7])
        self.assertEqual(p.place([5, 5], 'spawn', 5), [5, 5])
        p = placement(); p.previous = self.previous([20, 5])
        self.assertEqual(p.place([5, 5], 'spawn', 5), [5, 5])

    def test_two_points_that_shared_a_served_tile_keep_sharing_it(self):
        p = placement(); p.previous = {'regions': {'test': {'baselineTilePositions': {'5:5': [7, 7], '6:5': [7, 7]}}}}
        self.assertEqual(p.place([5, 5], 'invasion a', 5), [7, 7])
        self.assertEqual(p.place([6, 5], 'invasion b', 5), [7, 7])

    def test_a_reserved_served_tile_is_not_reused_and_bodies_ignore_continuity(self):
        p = placement(); p.previous = self.previous([7, 7]); p.reserve([7, 7])
        self.assertEqual(p.place([5, 5], 'spawn', 5), [5, 5])
        p = placement(); p.previous = self.previous([7, 7])
        self.assertEqual(p.place([5, 5], 'npc', 5, body=True), [5, 5])

    def test_points_that_lose_their_shared_served_tile_move_together(self):
        p = placement(); p.previous = {'regions': {'test': {'baselineTilePositions': {'5:5': [7, 7], '6:5': [7, 7]}}}}
        p.reserve([7, 7])   # taken this publication by a reserving record
        first = p.place([5, 5], 'invasion a', 5)
        self.assertNotEqual(first, [7, 7])
        p.reserve(first)    # even if something reserves the new tile meanwhile
        self.assertEqual(p.place([6, 5], 'invasion b', 5), first)
class ContentTransformTests(unittest.TestCase):
    """The published source-frame mapping, carried by Content's own mapped_xz."""

    PROBES = [[12., -7.], [-30., 45.], [210., 180.]]
    TURNED = {'translation': [760., 0., 640.], 'about_x': 40., 'about_z': -60.,
              'yaw_degrees': -34., 'squeeze_x': .92, 'squeeze_z': .74}

    def content(self, transform, source_center=(40., -60.), scale=.78, center=(900., 500.)):
        """A stand-in seated exactly as Content.load seats a territory, with Content's own mapped_xz."""
        fake = types.SimpleNamespace(transforms={'test': transform}, source_centers={}, scales={},
            world=types.SimpleNamespace(regions={'test': {'center': list(center)}}))
        fake.mapped_xz = lambda region, points: C.Content.mapped_xz(fake, region, points)
        if transform is None:
            fake.source_centers['test'], fake.scales['test'] = np.asarray(source_center, float), scale
        else:
            fake.source_centers['test'], fake.scales['test'] = C.retained_source_center(transform, center)
        return fake

    def mapped(self, published, points):
        """The published affine read as the contract states it: continent metres from source metres."""
        a, b, c, d, e, f = published['affine']
        points = np.asarray(points, float)
        return np.c_[a * points[:, 0] + b * points[:, 1] + e, c * points[:, 0] + d * points[:, 1] + f]

    def test_a_territory_on_the_centre_and_scale_rule_keeps_its_published_fields(self):
        content = self.content(None)
        published = E.content_transform(content, 'test')
        self.assertEqual(published['scale'], .78)
        self.assertEqual(published['sourceCenter'], [40., -60.])
        self.assertEqual(published['targetCenter'], [0, 0])
        self.assertNotIn('yawDegrees', published)
        self.assertNotIn('squeeze', published)
        np.testing.assert_allclose(published['affine'], [.78, 0., 0., .78, 900. - 40. * .78, 500. + 60. * .78], atol=1e-9)
        np.testing.assert_allclose(self.mapped(published, self.PROBES), content.mapped_xz('test', self.PROBES), atol=1e-7)

    def test_a_rigid_translation_keeps_the_old_fields_and_publishes_an_identity_affine(self):
        transform = [760., 0., 640.]
        published = E.content_transform(self.content(transform), 'test')
        self.assertEqual(published['scale'], 1.)
        np.testing.assert_allclose(published['sourceCenter'], [140., -140.])
        np.testing.assert_allclose(published['affine'], [1., 0., 0., 1., 760., 640.], atol=1e-9)
        self.assertNotIn('yawDegrees', published)
        self.assertNotIn('squeeze', published)
        np.testing.assert_allclose(self.mapped(published, self.PROBES), L.retained_map_xz(transform, self.PROBES), atol=1e-7)

    def test_a_turned_and_squeezed_territory_publishes_the_exact_affine_and_no_scalar(self):
        content = self.content(self.TURNED)
        # The old line asked float() of a two-axis scale, which is the TypeError this replaces.
        with self.assertRaises(TypeError):
            float(content.scales['test'])
        published = E.content_transform(content, 'test')
        self.assertIsNone(published['scale'])
        self.assertEqual(published['yawDegrees'], -34.)
        self.assertEqual(published['squeeze'], [.92, .74])
        self.assertEqual(len(published['sourceCenter']), 2)
        self.assertTrue(all(np.isfinite(published['affine'])))
        np.testing.assert_allclose(self.mapped(published, self.PROBES), L.retained_map_xz(self.TURNED, self.PROBES), atol=1e-7)
        self.assertEqual(json.loads(json.dumps(published)), published)

    def test_a_squeeze_without_a_turn_is_still_no_single_scale(self):
        transform = {'translation': [760., 0., 640.], 'about_z': -60., 'squeeze_z': .74}
        published = E.content_transform(self.content(transform), 'test')
        self.assertIsNone(published['scale'])
        self.assertEqual(published['squeeze'], [1., .74])
        self.assertEqual(published['yawDegrees'], 0.)
        a, b, c, d = published['affine'][:4]
        np.testing.assert_allclose([a, b, c, d], [1., 0., 0., .74], atol=1e-9)
        np.testing.assert_allclose(self.mapped(published, self.PROBES), L.retained_map_xz(transform, self.PROBES), atol=1e-7)

    def test_the_rebase_estimate_of_a_turned_territory_reads_its_published_affine(self):
        # A record the baseline gained after a publication that turned its territory is served where that
        # publication's exact mapping put its original cell: continent metres less the territory's centre.
        published = E.content_transform(self.content(self.TURNED), 'test')
        self.assertIsNone(published['scale'])
        prior = {'serverOrigin': [400, 300], 'baselineServerOrigin': [120, 120], 'translation': [900., 0., 500.],
                 'baselineContentTransform': published}
        for old in ([130, 110], [250, 40], [90, 300]):
            source = [old[0] + .5 - 120, 120 - old[1] - .5]
            x, z = np.asarray(L.retained_map_xz(self.TURNED, [source]), float).reshape(2)
            expected = [int(np.floor(x - 900. + 400)), int(np.floor(300 - (z - 500.)))]
            self.assertEqual(E.estimated_served_tile(f'{old[0]}:{old[1]}', prior), expected)

    def test_a_uniform_squeeze_keeps_the_number_the_old_rule_reads(self):
        transform = {'translation': [760., 0., 640.], 'about_x': 40., 'about_z': -60., 'squeeze_x': .8, 'squeeze_z': .8}
        published = E.content_transform(self.content(transform), 'test')
        self.assertEqual(published['scale'], .8)
        # The old fields and the affine name the same ground: the affine is absolute continent
        # metres, the old rule is relative to the territory's centre.
        source = np.asarray(published['sourceCenter'], float)
        old = (np.asarray(self.PROBES, float) - source) * published['scale'] + [900., 500.]
        np.testing.assert_allclose(old, self.mapped(published, self.PROBES), atol=1e-7)
        np.testing.assert_allclose(old, L.retained_map_xz(transform, self.PROBES), atol=1e-7)


def bind_instance_fixture(p, tmp_path, monkeypatch, identities=('a', 'b'), old=(6, 7)):
    monkeypatch.syspath_prepend(str(E.TOOLS))
    import publish_diagonal_continent as publisher
    monkeypatch.setattr(publisher, 'CLIENT', tmp_path)
    source = {'path': 'config/eloria/instances/a.def', 'spawnName': 'arena', 'fields': ['exit_x','exit_y'],
              'line': 5, 'originalTile': list(old), 'map': 'test', 'sha256': 'a'*64}
    marker = {'section': 'runtimePoints', 'id': 'independent-return'}
    report = {'schema': 'eloria-instance-exit-binding-amendment-v1', 'records': [
        {'id': identity, 'region': 'test', 'marker': marker,
         'source': {'path': source['path'], 'recordId': 'arena', 'fields': source['fields'],
                    'line': 5, 'oldTile': list(old), 'sha256': source['sha256']}}
        for identity in identities]}
    path = tmp_path/'amendment.json'; path.write_text(json.dumps(report))
    bindings = {identity: {'id': identity, 'role': 'return', 'roads': 'marker', 'targetOffset': [0,0,0], 'aliases': [],
        'marker': marker, 'source': {**row['source'], 'amendmentReport': {'path': 'amendment.json', 'sha256': E.sha(path)}},
        'provenance': {'sourceProfileSha256': source['sha256']}} for identity,row in zip(identities,report['records'])}
    for binding in bindings.values(): binding['source'].pop('sha256')
    p.content.runtime_bindings = bindings
    p.content.runtime_bindings_by_region = {'test': bindings}
    p.content.authored_runtime_points = {('test', identity): np.array([old[0]+.5-15+100, 10.,15-old[1]-.5+200]) for identity in identities}
    p.spec['translation'] = [100.,0.,200.]
    return source


def test_instance_exit_placement_ignores_generic_cache_and_preserves_shared_returns(tmp_path, monkeypatch):
    p = placement(); p.reserved[:] = False
    p.spec['tilePositions']['6:7'] = [28, 28]
    source = bind_instance_fixture(p, tmp_path, monkeypatch)
    generic = copy.deepcopy(p.spec['tilePositions'])
    tile = p.place_instance_exit('a', source, [28, 28])
    assert tile == [6, 7]
    assert p.spec['tilePositions'] == generic
    assert p.place_instance_exit('b', source, [28, 28]) == tile
    assert tuple(tile) in p.fixed and p.reserved[7, 6]
    p.validate_instance_exits(set())
    assert p.spec['instanceExitPositions']['a']['postContent']['hubAccessible']
    assert p.spec['instanceExitPositions']['a']['previousTile'] == [28, 28]
    with pytest.raises(E.PlacementError, match='duplicate'):
        p.place_instance_exit('a', source, [28, 28])


def test_instance_exit_budget_and_postcontent_checks_are_not_waived(tmp_path, monkeypatch):
    source = {'originalTile': [6, 7], 'map': 'test'}
    p = placement(); p.reserved[:] = True
    source = bind_instance_fixture(p, tmp_path, monkeypatch)
    assert p.place_instance_exit('a', source, [28, 28]) is None
    assert p.failures[-1]['maximumDisplacementMetres'] == 5
    for kind in ('blocked', 'disconnected', 'trigger'):
        p = placement(); p.reserved[:] = False
        source = bind_instance_fixture(p, tmp_path, monkeypatch)
        p.place_instance_exit('a', source, [6, 7])
        if kind == 'blocked': p.grid[7, 6] = 0
        if kind == 'disconnected': p.grid[10, :] = 0
        with pytest.raises(E.PlacementError, match='post-content'):
            p.validate_instance_exits({(6, 7)} if kind == 'trigger' else set())


def test_instance_exit_fixed_destination_survives_storage_and_body_policy(tmp_path, monkeypatch):
    p = placement(); p.reserved[:] = False
    source = bind_instance_fixture(p, tmp_path, monkeypatch)
    p.place_instance_exit('a', source, [6, 7])
    assert not p.valid([6, 7])
    # A malicious later body write is caught even if it bypassed reservation.
    p.stamp_storage([[6, 7]])
    assert any('fixed route' in row['record'] for row in p.failures)


def test_qualified_portal_rebase_uses_each_prior_record_not_collapsed_tile():
    def current(a, b):
        return {'regions': {'test': {'tilePositions': {'4:5': a}, 'previousServerOrigin': [15,15],
            'serverOrigin': [15,15], 'contentTransform': {}, 'removedInteractiveIds': [],
            'runtimeBindingPositions': {'a': a, 'b': b},
            'runtimeBindingSourceTiles': {'a': [4,5], 'b': [4,5]},
            'portalPositions': {'first': {'oldTile': [4,5], 'tile': a, 'runtimeBindingId': 'a'},
                                'second': {'oldTile': [4,5], 'tile': b, 'runtimeBindingId': 'b'}}}}}
    first = current([10,11], [12,13]); E.rebase_publication(first, None)
    second = current([11,11], [13,13]); E.rebase_publication(second, first)
    third = current([11,12], [13,14]); E.rebase_publication(third, second)
    assert second['regions']['test']['portalPositions']['second']['oldTile'] == [12,13]
    assert third['regions']['test']['portalPositions']['second']['oldTile'] == [13,13]
    broken = current([11,11], [13,13]); del first['regions']['test']['runtimeBindingPositions']['b']
    with pytest.raises(ValueError, match='qualified portal provenance'):
        E.rebase_publication(broken, first)


def test_instance_guard_and_predecessor_read_exact_record_history_across_publications(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(E.TOOLS))
    import publish_diagonal_continent as publisher
    shared = publisher.shared
    monkeypatch.setattr(publisher, 'CONTENT', {})
    server, baseline = tmp_path/'server', tmp_path/'baseline'
    relative = 'config/eloria/instances/example.def'
    def definition(tile):
        return '[instance]\nspawn_name: arena\nexit_map: test\nexit_x: %d\nexit_y: %d\n' % tuple(tile)
    for base, tile in ((baseline, [4,5]), (server, [16,17])):
        target = base/relative; target.parent.mkdir(parents=True); target.write_text(definition(tile))
    digest = E.sha(baseline/relative)
    identity, source = next(iter(publisher.instance_exit_records(relative, definition([4,5]), {'test': {}}).items()))
    source['sha256'] = digest
    entry = {'source': source, 'previousTile': [10,11], 'expectedTile': [16.,17.], 'tile': [16,17],
             'maximumDisplacementMetres': 5,
             'postContent': {'standing': True, 'hubAccessible': True, 'noPortalTrigger': True}}
    previous = {'instanceExitSchema': 1, 'connections': [], 'regions': {'test': {
        'baselineTilePositions': {'4:5': [1,2]}, 'baselineServerOrigin': [15,15],
        'serverOrigin': [15,15], 'baselineContentTransform': {}, 'baselineRemovedInteractiveIds': [],
        'runtimeBindingSourceTiles': {'a': [4,5], 'b': [4,5]},
        'portalPositions': {'a': {'runtimeBindingId': 'a', 'tile': [1,2]},
                            'b': {'runtimeBindingId': 'b', 'tile': [2,3]}},
        'instanceExitPositions': {identity: entry}}}}
    certificate = {'files': {relative: digest}}
    E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
    predecessors = E.instance_exit_predecessors(server, baseline, certificate, previous['regions'], publisher)
    assert predecessors[identity] == (source, [16,17])
    # Second coordinated publication has its own previous/final record history.
    entry.update(previousTile=[16,17], tile=[17,17])
    (server/relative).write_text(definition([17,17]))
    E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
    for changed in (definition([2,3]), definition([17,18]), definition([17,17])+'name: edited\n'):
        (server/relative).write_text(changed)
        with pytest.raises(ValueError, match='beyond the previous coordinated'):
            E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
    (server/relative).write_text(definition([17,17]))
    for invalid_schema in (None, 3, True):
        previous['instanceExitSchema'] = invalid_schema
        with pytest.raises(ValueError, match='schema'):
            E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)
    previous['instanceExitSchema'] = 1
    previous['regions']['test']['instanceExitPositions'].clear()
    with pytest.raises(ValueError, match='incomplete'):
        E.verify_current_profile(server, baseline, certificate, previous, shared, publisher)


def test_authored_instance_binding_rejects_missing_wrong_region_and_source(tmp_path, monkeypatch):
    for fault in ('missing', 'region', 'digest', 'line', 'name', 'marker', 'alias', 'report'):
        p = placement(); p.reserved[:] = False
        source = bind_instance_fixture(p, tmp_path, monkeypatch)
        binding = p.content.runtime_bindings['a']
        if fault == 'missing':
            p.content.runtime_bindings = {}; p.content.runtime_bindings_by_region = {}
        elif fault == 'region': p.content.runtime_bindings_by_region = {'other': {'a': binding}}
        elif fault == 'digest': binding['provenance']['sourceProfileSha256'] = 'b'*64
        elif fault == 'line': binding['source']['line'] += 1
        elif fault == 'name': binding['source']['recordId'] = 'different'
        elif fault == 'marker': binding['marker'] = {'section':'runtimePoints','id':'keeper'}
        elif fault == 'alias': binding['aliases'] = ['shared-tile']
        else: (tmp_path/'amendment.json').write_text('{}')
        with pytest.raises(ValueError):
            p.place_instance_exit('a', source, [6,7])




def test_authored_instances_reject_conflicting_full_inventory_reports(tmp_path, monkeypatch):
    p = placement(); p.reserved[:] = False
    source = bind_instance_fixture(p, tmp_path, monkeypatch)
    p.place_instance_exit('a', source, [6,7])
    # Both reports contain every id and certify their own binding; the second
    # contradicts the first binding and must not become a second authority.
    report = json.loads((tmp_path/'amendment.json').read_text())
    report['records'][0]['marker'] = {'section':'runtimePoints','id':'other'}
    alternate = tmp_path/'alternate.json'; alternate.write_text(json.dumps(report))
    p.content.runtime_bindings['b']['source']['amendmentReport'] = {'path':'alternate.json','sha256':E.sha(alternate)}
    p.place_instance_exit('b', source, [6,7]); p.validate_instance_exits(set())
    import publish_diagonal_continent as publisher
    with pytest.raises(ValueError, match='one identical amendment'):
        publisher.validate_instance_exit_table({'test':p.spec},{'a':source,'b':source},client=tmp_path,require_authored=True)


def test_moving_authored_instance_marker_one_metre_moves_preferred_exit(tmp_path, monkeypatch):
    p = placement(); p.reserved[:] = False
    source = bind_instance_fixture(p, tmp_path, monkeypatch)
    assert p.place_instance_exit('a', source, [6,7]) == [6,7]
    p = placement(); p.reserved[:] = False
    source = bind_instance_fixture(p, tmp_path, monkeypatch)
    p.content.authored_runtime_points[('test','a')][0] += 1
    assert p.place_instance_exit('a', source, [6,7]) == [7,7]
    assert p.spec['instanceExitPositions']['a']['previousTile'] == [6,7]
    assert p.spec['runtimeBindingPositions']['a'] == [7,7]
    assert '6:7' not in p.spec['tilePositions']
