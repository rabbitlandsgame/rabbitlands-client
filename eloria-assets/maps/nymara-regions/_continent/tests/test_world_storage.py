"""Small source-driven World/EWCG fixtures; no generated continent dependencies."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import authoring_catalog as A
import collision_export as C
import export_contracts as E
import ownership_contract as O
import world_layout as W
from storage_bounds import StorageBounds as Bounds
from test_ownership_authoring import fixture_checkout, write
from test_ownership_contract import fixture_document
from test_collision_export import TwoTerritories, write_geometry, quad


def source_world(tmp_path, monkeypatch, *, minimum=(-2, -4), cells=(12, 12), selected=True, walking_height=None):
    document = fixture_document()
    for record in document['regions'].values():
        record['coordinateFrame']['serverOrigin'] = [3, 3]
        record['baselineStorage'] = {'serverCells': [6, 6], 'serverTileMin': [0, 0],
                                     'collisionOriginMetres': [-3, 3]}
    client, plan_path, _, plan = fixture_checkout(tmp_path, document)
    if not selected:
        plan.pop('ownership_contract')
        write(plan_path, plan)
    monkeypatch.setattr(A, 'CLIENT', client)
    monkeypatch.setattr(O, 'SOURCE_ROOT', plan_path.parent)
    monkeypatch.setattr(W.L, 'height_at', lambda x,z,plan: np.zeros(np.broadcast_arrays(x,z)[0].shape))
    monkeypatch.setattr(W.L, 'water_fields', lambda x,z,**kw: {
        'mask': np.zeros(x.shape, bool), 'surface': np.zeros(x.shape)})
    contracts = {}
    for region in ('west', 'east'):
        frame = document['regions'][region]['coordinateFrame']
        bounds = Bounds(*cells, *minimum) if region == 'west' else Bounds(6, 6)
        base = f'godot-client/world_authoring/regions/{region}'
        scene = client / base / (region + '.tscn')
        scene.parent.mkdir(parents=True)
        scene.write_text('[gd_scene format=3]\n')
        manifest = f'eloria-assets/maps/nymara-regions/{region}/world.json'
        write(client / manifest, {})
        server = {'origin': frame['serverOrigin'], 'cells': [bounds.width, bounds.height],
                  'collisionOriginMetres': list(bounds.physical_origin(frame['serverOrigin']))}
        if minimum != (0, 0) and region == 'west':
            server.update(bounds.metadata())
        if walking_height is not None:
            server['walkingHeight'] = walking_height
        spec = {'schema': A.SPEC_SCHEMA, 'regionId': region, 'label': region, 'adapter': 'fixture-v1',
            'paths': {'scene': scene.relative_to(client).as_posix(), 'manifest': manifest,
                      'snapshot': f'eloria-assets/maps/nymara-regions/{region}/authoring/continent-authoring.json'},
            'continentTranslation': frame['continentTranslation'], 'server': server,
            'terrain': {'origin': [0, 0], 'vertices': [2, 2], 'cellMetres': 2},
            'authority': {'ownedRouteIds': [], 'requiredRouteIds': [], 'ownedPlanFeatureIds': []},
            'gameplay': {'runtimeBindingCount': 0, 'runtimePointCount': 0, 'existingMarkerBindingCount': 0}}
        path = client / base / 'region-authoring-spec.json'
        write(path, spec)
        contracts[region] = A.load_region_spec(path, ownership_plan_path=plan_path)
    world = W.World(plan, region_contracts=contracts, require_authored_storage=True)
    return world, plan, contracts


@pytest.mark.parametrize('selected', [False, True])
def test_source_storage_wins_without_rebasing_logical_world_identity(tmp_path, monkeypatch, selected):
    world, _, contracts = source_world(tmp_path, monkeypatch, selected=selected)
    assert world.address('west') == ([3, 3], [12, 12])
    assert world.storage('west') == Bounds(12, 12, -2, -4)
    frame = contracts['west'].continent_translation
    for tile in ((0, 0), (5, 5), (2, 3), (-2, -4), (9, 7)):
        at = world.storage('west').index_xy(*tile)
        recovered = world.storage('west').logical_xy(*at)
        point = (tile[0] + .5 - 3 + frame[0], 3 - tile[1] - .5 + frame[2])
        assert point == (recovered[0] + .5 - 3 + frame[0], 3 - recovered[1] - .5 + frame[2])
    assert world.storage('west').index_xy(-3, -4) is None
    assert world.storage('west').index_xy(10, 7) is None
    exported = world.storage_contract('west')
    assert exported['authoringSpecSha256'] == contracts['west'].spec_sha256
    exported['serverOrigin'][0] = 999
    assert world.address('west')[0] == [3, 3]


def test_positive_minima_and_implicit_zero_are_independent_of_voronoi_bounds(tmp_path, monkeypatch):
    world, _, _ = source_world(tmp_path, monkeypatch, minimum=(7, 13), cells=(6, 12), selected=False)
    assert world.storage('west') == Bounds(6, 12, 7, 13)
    assert world.address('west')[0] == [3, 3]
    assert world.storage('east') == Bounds(6, 6)
    assert world.address('east') == ([3, 3], [6, 6])


def test_selected_production_requires_complete_hash_bound_sources_before_sampling(tmp_path, monkeypatch):
    _, plan, contracts = source_world(tmp_path, monkeypatch)
    monkeypatch.setattr(W.L, 'height_at', lambda *a,**k: pytest.fail('must fail before sampling'))
    with pytest.raises(ValueError, match='requires authored storage'):
        W.World(plan, region_contracts={'west': contracts['west']}, require_authored_storage=True)
    with pytest.raises(ValueError, match='hash-bound'):
        W.World(plan, region_contracts={'west': None})
    with pytest.raises(ValueError, match='unknown'):
        W.World(plan, region_contracts={'unknown': contracts['west']})
    bad = dict(contracts, west=replace(contracts['west'], server_origin=(4, 3)))
    with pytest.raises(ValueError, match='differs from validated'):
        W.World(plan, region_contracts=bad)
    path = contracts['west'].spec_path
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='changed before World'):
        W.World(plan, region_contracts=contracts)


def test_source_drift_cannot_reuse_a_world_or_collision_certificate(tmp_path, monkeypatch):
    world, _, contracts = source_world(tmp_path, monkeypatch)
    old = E.collision_world_digest(world)
    assert old == E.collision_world_digest(world)
    path = contracts['west'].spec_path
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='storage source changed'):
        world.storage_contract('west')
    with pytest.raises(ValueError, match='storage source changed'):
        E.collision_world_digest(world)


def test_baseline_only_synthetic_world_and_procedural_fallback_stay_explicit(tmp_path, monkeypatch):
    _, plan, _ = source_world(tmp_path, monkeypatch)
    synthetic = W.World(plan)
    assert synthetic.storage('west') == Bounds(6, 6)
    assert synthetic.address('west') == ([3, 3], [6, 6])
    legacy = copy.deepcopy(plan)
    legacy.pop('ownership_contract')
    procedural = W.World(legacy)
    origin, cells = procedural.address('west')
    assert procedural.storage('west') == Bounds(*cells)
    assert procedural.storage_contract('west')['serverOrigin'] == origin
    assert 'authoringSpecSha256' not in procedural.storage_contract('west')


def test_prepare_injects_validated_contracts_before_any_address_consumer(tmp_path, monkeypatch):
    import build_continent as B
    _, plan, contracts = source_world(tmp_path, monkeypatch)
    directory = O.SOURCE_ROOT
    write(directory / 'legacy-contracts.json', {'west':{},'east':{}})
    write(directory / 'legacy-geography.json', {})
    profile = directory / 'legacy-server-profile/config/eloria/maps.txt'
    profile.parent.mkdir(parents=True)
    profile.write_text('')
    snapshots = tuple(SimpleNamespace(contract=contract, document={'regionId':region},
        bound_sources=lambda: {}) for region,contract in contracts.items())
    monkeypatch.setattr(B, 'HERE', directory)
    monkeypatch.setattr(B, 'SHAPING_SOURCES', ())
    monkeypatch.setattr(B, 'composition_certificate_paths', lambda: ())
    monkeypatch.setattr(B.AUTHORING, 'load_snapshots', lambda: snapshots)
    monkeypatch.setattr(B.AUTHORING, 'apply_gameplay', lambda template,snapshot:template)
    monkeypatch.setattr(B.AUTHORING, 'apply_plans', lambda original,snapshots:original)
    monkeypatch.setattr(B.L, 'load_plan', lambda: plan)
    class ReachedWorld(Exception):
        pass
    def constructor(actual_plan, **kwargs):
        assert kwargs == {'region_contracts':contracts, 'require_authored_storage':True}
        world = W.World(actual_plan, **kwargs)
        assert world.address('west') == ([3,3],[12,12])
        assert world.storage('west').index_xy(-2,-4) == (0,0)
        raise ReachedWorld()
    monkeypatch.setattr(B, 'World', constructor)
    with pytest.raises(ReachedWorld):
        B.prepare(tmp_path/'unused-library', tmp_path/'unused-output')


def test_manifest_storage_metadata_preserves_explicit_frame_and_changes_only_bounds(tmp_path, monkeypatch):
    import build_continent as B
    world, _, contracts = source_world(tmp_path, monkeypatch, walking_height=42.25)
    world.authoring_snapshots = {'west':True}
    center = np.array([10,0,20])
    content = SimpleNamespace(templates={'west':{'asset':{}, 'spawnPoints':[
        {'id':'spawn','default':True,'position':[0,2,0]}]}}, objects=[],
        mapped_point=lambda region,point,*a: np.asarray(point)+center)
    monkeypatch.setattr(B, 'apply_manifest', lambda *a:None)
    manifest = B.manifest_for(world,content,'west')
    assert manifest['coordinateTransform'] == {'metresPerTile':1.,'serverOrigin':[3,3],
        'serverCells':[12,12],'origin':[0,0,0],'walkingHeight':42.25,'invertServerY':True,
        'serverStorageVersion':1,'serverTileMin':[-2,-4],
        'authoringSpecSha256':contracts['west'].spec_sha256,
        'addressableWorldBounds':{'min':[-5,-5],'max':[7,7]}}
    assert manifest['collision']['originMetres'] == [-5,7]
    assert manifest['collision']['authoringSpecSha256'] == contracts['west'].spec_sha256
    assert manifest['spawnPoints'][0]['position'] == [0.,2.,0.]


class OffsetWorld(TwoTerritories):
    def __init__(self, minimum, cells=(6, 6)):
        super().__init__()
        self.minimum = minimum
        self.cells = cells
        self.ids = ['west']
        self.regions = {'west': {'center': [0, 0]}}
        self.height = (self.gx * .1 + self.gz * .05 + 2).astype(float)
        self.owner = np.zeros((10, 10), np.uint8)

    def address(self, region):
        return [3, 3], list(self.cells)

    def storage(self, region):
        return Bounds(*self.cells, *self.minimum)

    def owner_at(self, x, z):
        return np.zeros(np.broadcast_arrays(x,z)[0].shape, int)


def export(tmp_path, world, *, meshes=(), transform=None):
    glb = tmp_path / 'world.glb'
    write_geometry(glb, meshes)
    origin, cells = world.address('west')
    manifest = {'coordinateTransform': transform or {'serverOrigin': origin, 'serverCells': cells,
                **world.storage('west').metadata()}, 'collision': {},
                'navigation': {'surfaceNodePrefixes': ['Terrain_', 'Walk_']}}
    return C.export_collision(world, 'west', manifest, glb, tmp_path / 'collision.bin')


@pytest.mark.parametrize('minimum', [(-2, -4), (1, 2), (0, 0)])
def test_half_metre_sampling_uses_exactly_one_offset(tmp_path, minimum):
    world = OffsetWorld(minimum)
    result = export(tmp_path, world)
    bounds = world.storage('west')
    assert result['heights'].shape == (12, 12)
    for tile in ((bounds.min_x, bounds.min_y), (bounds.max_x - 1, bounds.max_y - 1)):
        column, row = bounds.index_xy(*tile)
        for dy in range(2):
            for dx in range(2):
                lx = tile[0] + (dx + .5) * .5 - 3
                lz = 3 - tile[1] - (dy + .5) * .5
                expected = lx * .1 + lz * .05 + 2
                assert result['heights'][row * 2 + dy, column * 2 + dx] == pytest.approx(expected, abs=2e-7)
    assert result['collision']['serverTileMin'] == list(minimum)
    assert result['collision']['serverCells'] == [6, 6]
    assert result['collision']['originMetres'] == list(bounds.physical_origin([3, 3]))
    raw = (tmp_path / 'collision.bin').read_bytes()
    assert struct.unpack_from('<4sHHII', raw) == (b'EWCG', 2, 0, 12, 12)
    assert raw[16:] == result['grid'].tobytes()


def test_old_half_cells_keep_world_heights_when_storage_grows(tmp_path):
    old = OffsetWorld((0, 0))
    old_result = export(tmp_path, old)
    expanded = OffsetWorld((-2, -4), (12, 12))
    expanded_result = export(tmp_path, expanded)
    np.testing.assert_array_equal(old_result['heights'], expanded_result['heights'][8:20, 4:16])
    np.testing.assert_array_equal(old_result['walkable'], expanded_result['walkable'][8:20, 4:16])


def test_implicit_zero_manifest_retains_identical_ewcg_bytes(tmp_path):
    world = OffsetWorld((0,0))
    explicit = export(tmp_path, world)
    payload = (tmp_path/'collision.bin').read_bytes()
    legacy = export(tmp_path, world, transform={'serverOrigin':[3,3],'serverCells':[6,6]})
    assert (tmp_path/'collision.bin').read_bytes() == payload
    np.testing.assert_array_equal(explicit['heights'], legacy['heights'])


def test_geometry_raster_uses_physical_storage_origin_and_padding_stays_blocked(tmp_path):
    world = OffsetWorld((-2, -4), (18, 18))
    result = export(tmp_path, world, meshes=[('Walk_Platform', quad(-1, -1, 1, 1, 4))])
    # Same authored local platform now occupies a shifted array rectangle.
    assert result['heights'][12, 8] == pytest.approx(4)
    assert result['walkable'][12, 8]
    assert not result['walkable'][:, 30:].any()  # Physical x >= 10 is outside domain.


@pytest.mark.parametrize('change', [
    {'serverTileMin': [0, 0]}, {'serverOrigin': [4, 3]}, {'serverCells': [12, 12]},
    {'origin': [0, 1, 0]}, {'metresPerTile': 2}, {'invertServerY': False},
])
def test_bad_frame_rejects_before_reading_geometry_or_writing_collision(tmp_path, change):
    world = OffsetWorld((-2, -4))
    frame = {'serverOrigin': [3, 3], 'serverCells': [6, 6], **world.storage('west').metadata()}
    frame.update(change)
    with pytest.raises(ValueError):
        C.export_collision(world, 'west', {'coordinateTransform': frame}, tmp_path/'missing.glb', tmp_path/'collision.bin')
    assert not (tmp_path/'collision.bin').exists()


@pytest.mark.parametrize('minimum', [(-2, -4), (7, 13), (0, 0)])
def test_fold_is_zero_indexed_and_only_carries_logical_metadata(minimum):
    grid = np.arange(1, 65, dtype=np.uint8).reshape(8, 8)
    grid[2, 5] = 0
    sources = SimpleNamespace(GridTransform=lambda **kw: SimpleNamespace(**kw), requantise=lambda g,t:g)
    sync = SimpleNamespace(choose_stage=lambda g:(1,g!=0,{}),rescale=lambda g,f:g)
    collision = {'heightEncoding': {'origin':0, 'step':.2}, 'serverCells':[4,4],
                 **Bounds(4,4,*minimum).metadata(), 'authoringSpecSha256':'1'*64}
    folded, _, _, detail = E.fold_server_grid({'grid':grid,'collision':collision},sources,sync)
    expected = np.array([[10,12,14,16],[26,28,0,32],[42,44,46,48],[58,60,62,64]],np.uint8)
    np.testing.assert_array_equal(folded, expected)
    assert detail['storage']['serverTileMin'] == list(minimum)
    assert detail['storage']['authoringSpecSha256'] == '1'*64
    collision['serverCells'] = [6,6]
    with pytest.raises(ValueError, match='dimensions differ'):
        E.fold_server_grid({'grid':grid,'collision':collision},sources,sync)


def test_cache_identity_changes_for_minimum_and_raw_source_hash(tmp_path, monkeypatch):
    world = OffsetWorld((0,0))
    base = E.collision_world_digest(world)
    world.minimum = (-1,0)
    assert E.collision_world_digest(world) != base
    world.minimum = (0,0)
    world.storage_contract = lambda r: {'serverOrigin':[3,3], 'serverCells':[6,6],
        **world.storage(r).metadata(), 'authoringSpecSha256':'1'*64}
    with_source = E.collision_world_digest(world)
    assert with_source != base
    world.storage_contract = lambda r: {'serverOrigin':[3,3], 'serverCells':[6,6],
        **world.storage(r).metadata(), 'authoringSpecSha256':'2'*64}
    assert E.collision_world_digest(world) != with_source


def test_collision_cache_rejects_stale_minima_and_spec_even_with_reused_world_digest(tmp_path, monkeypatch):
    for name in ('collision_export.py','world_layout.py','storage_bounds.py',
                 'terrain_export.py','landscape.py','crossings.py'):
        (tmp_path/name).write_text('fixture source')
    monkeypatch.setattr(E,'HERE',tmp_path)
    world = OffsetWorld((-1,-2))
    current_sha = ['1'*64]
    world.storage_contract = lambda r: {'serverOrigin':[3,3], 'serverCells':[6,6],
        **world.storage(r).metadata(), 'authoringSpecSha256':current_sha[0]}
    calls = []
    def raster(w,r,m,g,p):
        calls.append(w.storage(r))
        return {'grid':np.ones((12,12),np.uint8),'heights':np.ones((12,12),np.float32),
                'walkable':np.ones((12,12),bool),'collision':{'serverCells':[6,6],
                    **w.storage(r).metadata(),'authoringSpecSha256':current_sha[0]}}
    monkeypatch.setattr(C,'export_collision',raster)
    glb = tmp_path/'world.glb'
    glb.write_bytes(b'test geometry identity')
    def run():
        manifest = {'coordinateTransform':{'serverOrigin':[3,3],'serverCells':[6,6],
                    **world.storage('west').metadata()}}
        return E.cached_collision(world,'west',manifest,glb,tmp_path/'collision.bin',tmp_path,'reused-world-digest')
    run()
    run()
    assert len(calls) == 1
    world.minimum = (-2,-2)
    shifted = run()
    assert len(calls) == 2 and shifted['collision']['serverTileMin'] == [-2,-2]
    current_sha[0] = '2'*64
    rebound = run()
    assert len(calls) == 3 and rebound['collision']['authoringSpecSha256'] == '2'*64
    manifest = {'coordinateTransform':{'serverOrigin':[3,3],'serverCells':[6,6],
                **Bounds(6,6,-1,-2).metadata()}}
    with pytest.raises(ValueError, match='storage minima differ'):
        E.cached_collision(world,'west',manifest,glb,tmp_path/'collision.bin',tmp_path,'reused-world-digest')
    assert len(calls) == 3
