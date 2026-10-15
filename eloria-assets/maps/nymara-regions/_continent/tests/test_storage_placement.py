"""Array-boundary proofs on tiny folds from the explicitly paired server codec.

Set ELORIA_TEST_SERVER to a server checkout to exercise its actual requantisation,
stage selection and movement functions. No map files are read or generated there.
"""
import copy
import importlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import crossings as C
import crossing_contracts as X
import export_contracts as E
from storage_bounds import StorageBounds as Bounds
from test_partition_pipeline import FlatWorld
from test_crossing_contracts import package, floor_mesh


@pytest.fixture(scope='module')
def server_math():
    configured = os.environ.get('ELORIA_TEST_SERVER')
    if not configured:
        pytest.skip('ELORIA_TEST_SERVER must name the paired checkout for actual fold/movement semantics')
    server = Path(configured).resolve()
    original_path = list(sys.path)
    sys.path.insert(0, str(server / 'tools'))
    sys.path.insert(0, str(server))
    try:
        modules = [importlib.import_module(name) for name in ('collision_sources', 'sync_authored_collision')]
        for module in modules:
            assert Path(module.__file__).resolve().is_relative_to(server), 'mixed server checkouts'
        yield tuple(modules)
    finally:
        sys.path[:] = original_path


class StoredWorld(FlatWorld):
    def __init__(self, bounds, shift=0):
        self.envelopes = bounds
        self.shift = shift

    def storage(self, region):
        return self.envelopes[region]

    def address(self, region):
        bounds = self.storage(region)
        return [24 + self.shift, 24 + self.shift], [bounds.width, bounds.height]


def folded(bounds, server_math, *, region=None, pattern='open', shift=0):
    """Fixed logical terrain and blocked padding; half-cell relief forces stage >1."""
    sources, sync = server_math
    iy, ix = np.indices((bounds.height * 2, bounds.width * 2))
    tx, ty = ix // 2 + bounds.min_x - shift, iy // 2 + bounds.min_y - shift
    walk = (tx >= 8) & (tx < 40) & (ty >= 8) & (ty < 40)
    if region == 'west':
        walk &= tx < 35
    if region == 'east':
        walk &= tx >= 13
    if pattern in ('west-wall', 'both-walls') and region == 'west':
        walk &= tx != 30
    if pattern == 'both-walls' and region == 'east':
        walk &= tx != 17
    if pattern == 'trap' and region == 'west':
        walk &= ~((tx >= 30) & (tx <= 33) & (ty >= 19) & (ty < 30)) | ((tx == 33) & (ty == 24))
    # A single blocked subcell closes the logical tile in the real 2x2 fold.
    walk &= ~((tx == 34) & (ty == 12) & (ix % 2 == 0) & (iy % 2 == 0))
    encoded = np.where(walk, 20 + 3 * (ty - 8) + ix % 2 + iy % 2, 0).astype(np.uint8)
    heights = (20 + 3 * (ty - 8) + ix % 2 + iy % 2) * .2 + 2.5
    result = {'grid': encoded, 'heights': heights.astype(np.float32), 'collision': {
        'serverCells': [bounds.width, bounds.height], **bounds.metadata(),
        'heightEncoding': {'origin': 2.5, 'step': .2}}}
    grid, factor, largest, detail = E.fold_server_grid(result, sources, sync)
    assert factor > 1
    assert grid.max() <= sources.MAX_HEIGHT
    return result, grid, largest, factor, detail


def logical_mask(bounds, mask):
    return {bounds.logical_xy(int(x), int(y)) for y, x in zip(*np.nonzero(mask))}


def seam_run(bounds, server_math, pattern, shift=0):
    world = StoredWorld(bounds, shift)
    sources, _ = server_math
    served = {}
    stages = []
    for region in world.ids:
        _, grid, _, stage, _ = folded(bounds[region], server_math, region=region, pattern=pattern, shift=shift)
        served[region] = C.own_ground(world, region, grid)
        stages.append(stage)
    step = lambda h,y,x,dy,dx: sources.walk_step_ok(h,y,x,dy,dx,2)
    C.prepare_contracts(world)
    connections = world.publication_connections
    C.widen_seams(world, connections, served, step, gated=())
    before = copy.deepcopy(connections)
    hubs = {'west': [20 + shift, 24 + shift], 'east': [28 + shift, 24 + shift]}
    withdrawn = C.prune_lanes(world, connections, served, hubs, 2)
    return world, served, before, connections, withdrawn, stages


@pytest.mark.parametrize('pattern', ['open', 'west-wall', 'both-walls', 'trap'])
@pytest.mark.parametrize('shift', [0, -24])
def test_signed_storage_preserves_logical_lanes_reach_and_no_bounce(server_math, pattern, shift):
    base = {region: Bounds(48,48,shift,shift) for region in ('west','east')}
    padded = {'west': Bounds(60,60,shift-6,shift-4), 'east': Bounds(60,60,shift+3,shift+2)}
    old = seam_run(base, server_math, pattern, shift)
    new = seam_run(padded, server_math, pattern, shift)
    assert old[2:] == new[2:]  # complete logical endpoints/lanes, report and stage choices
    for region in ('west','east'):
        assert logical_mask(base[region],old[1][region]['grid']) == logical_mask(padded[region],new[1][region]['grid'])
    world, served, _, connections, withdrawn, _ = new
    if pattern == 'both-walls':
        assert withdrawn > 0 and all(not end['lanes'] for end in connections[0]['ends'])
    else:
        assert all(end['lanes'] for end in connections[0]['ends'])
    ends = connections[0]['ends']
    departures = [{tuple(C.global_tile(world,end['region'],lane['tile'])) for lane in end['lanes']} for end in ends]
    assert not (departures[0] & departures[1])
    for end, other in (ends, ends[::-1]):
        far_terminals = {tuple(lane['tile']) for lane in other['lanes']}
        for lane in end['lanes']:
            assert C.departs_outward(world,end['region'],lane)
            point = C.global_tile(world,end['region'],lane['tile'])
            far = tuple(map(int,C.tiles_at(world,other['region'],*point)))
            index = world.storage(other['region']).index_xy(*far)
            assert index is not None and served[other['region']]['grid'][index[1],index[0]]
            grid = served[other['region']]['grid']
            assert any(server_math[0].walk_step_ok(grid,index[1],index[0],dy,dx,2)
                       and (far[0]+dx,far[1]+dy) not in far_terminals for dy,dx in C.STEPS)


@pytest.mark.parametrize('minimum', [(-6,-4),(3,2),(-30,-28)])
def test_flood_indices_match_server_reach_and_logical_terminal_barrier(server_math, minimum):
    shift = -24 if minimum[0] < -20 else 0
    bounds = Bounds(60,60,*minimum)
    sources, _ = server_math
    _, grid, _, _, _ = folded(bounds,server_math,shift=shift)
    start = bounds.index_xy(20+shift,24+shift)
    seen = np.zeros(grid.shape,bool)
    C.flood(C.step_bits(grid,2),seen,[start],set())
    np.testing.assert_array_equal(seen,sources.reachable_from(grid,start,2))
    logical_terminals = {(25+shift,y+shift) for y in range(8,40)}
    terminals = {bounds.index_xy(*tile) for tile in logical_terminals}
    stopped = np.zeros(grid.shape,bool)
    C.flood(C.step_bits(grid,2),stopped,[start],terminals)
    logical = logical_mask(bounds,stopped)
    assert logical_terminals <= logical
    assert all(x <= 25+shift for x,y in logical)


def placement(bounds,server_math,shift=0,throat=False):
    world = StoredWorld({'west':bounds,'east':bounds},shift)
    result, grid, largest, _, _ = folded(bounds,server_math,shift=shift)
    if throat:
        for y in range(8,40):
            if y != 20:
                x,y_index = bounds.index_xy(20+shift,y+shift)
                grid[y_index,x] = 0
        largest = server_math[1].largest_component(grid,2)
    origin, cells = world.address('west')
    content = SimpleNamespace(templates={'west':{}},mapped_point=lambda r,p,*args:np.asarray(p)+[10,0,10])
    spec = {'serverOrigin':origin,'serverCells':cells,**bounds.metadata(),'previousServerOrigin':origin,
            'arrival':origin,'tilePositions':{}}
    report = {'placements':[],'failures':[],'regions':{'west':{}}}
    p = E.RegionPlacement(world,content,'west',spec,result,grid,server_math[0],report)
    p.connect_hub(origin,largest)
    return p


def placement_run(bounds,server_math,shift=0):
    p = placement(bounds,server_math,shift)
    tile = lambda x,y:[x+shift,y+shift]
    assert p.spec['arrival'] == tile(23,23)
    p.hold(tile(33,22))
    assert p.check_fixed(tile(16,25),'fixture fixed')
    body = p.place_body(np.asarray(tile(18,18)),3,(2,2),'fixture body')
    assert body == tile(18,18)
    p.stamp_storage([tile(29,30)])
    p.place(tile(17,31),'fixture resource',3,reserve=True)
    assert p.nearest(tile(33,22),0) is None
    assert p.nearest(tile(33,22),0,allow_reserved=True) == tile(33,22)
    assert not p.valid(tile(29,30),allow_reserved=True)
    assert not p.report['failures']
    return p


@pytest.mark.parametrize('shift', [0,-24])
def test_placement_body_access_held_and_heights_preserve_logical_results(server_math,shift):
    base = Bounds(48,48,shift,shift)
    old = placement_run(base,server_math,shift)
    for bounds in (Bounds(60,60,shift-6,shift-4),Bounds(60,60,shift+3,shift+2)):
        new = placement_run(bounds,server_math,shift)
        for name in ('held','fixed','bodies','storage','records','failures'):
            assert getattr(new,name) == getattr(old,name)
        assert new.spec['arrival'] == old.spec['arrival']
        assert new.spec['tilePositions'] == old.spec['tilePositions']
        for name in ('grid','reachable','reserved'):
            assert logical_mask(bounds,getattr(new,name)) == logical_mask(base,getattr(old,name))
        point = [17+shift,31+shift]
        assert new.local_position(point) == old.local_position(point)
        assert new.local_position(point)[0::2] == [-6.5,-7.5]
        assert not new.in_grid([bounds.min_x-1,bounds.min_y])
        with pytest.raises(ValueError,match='outside storage'):
            new.local_position([bounds.max_x,bounds.max_y-1])


@pytest.mark.parametrize('shift',[0,-24])
def test_body_that_seals_held_ground_is_relocated_identically(server_math,shift):
    records = []
    for bounds in (Bounds(48,48,shift,shift),Bounds(60,60,shift-6,shift-4),Bounds(60,60,shift+3,shift+2)):
        p = placement(bounds,server_math,shift,throat=True)
        held = [16+shift,20+shift]
        p.hold(held)
        body = p.place_body(np.asarray([20+shift,20+shift]),4,(1,1),'mouth')
        assert body is not None and body != [20+shift,20+shift]
        x,y = p.array_tile(held)
        assert p.reachable[y,x]
        rejected = p.report['regions']['west']['bodyRelocations']
        assert rejected[0]['rejectedTile'] == [20+shift,20+shift]
        records.append((body,rejected,logical_mask(bounds,p.reachable)))
    assert records[0] == records[1] == records[2]


@pytest.mark.parametrize('shift', [0,-24])
def test_declared_crossing_raster_and_logical_endpoints_survive_padding(server_math,shift):
    document,body = package({'Walk_ContinentalBridgeUnion_004_west':floor_mesh(-12,10,-3,-1,5.)})
    baseline = None
    for bounds in (Bounds(48,48,shift,shift),Bounds(60,60,shift-6,shift-4),Bounds(60,60,shift+3,shift+2)):
        result,grid,_,_,_ = folded(bounds,server_math,shift=shift)
        value = X.declare_crossings(document,body,'west',grid,2,[24+shift,24+shift],
            [bounds.width,bounds.height],result['heights'],bounds=bounds)
        assert value[0] and not value[2]
        assert value[1][0]['endTiles'][0][0] >= shift+12
        if baseline is None:
            baseline = value
        else:
            assert value == baseline


def test_outside_lanes_and_hubs_do_not_wrap_negative_indices(server_math):
    bounds = {'west':Bounds(60,60,-6,-4),'east':Bounds(60,60,3,2)}
    world,served,_,connections,_,_ = seam_run(bounds,server_math,'open')
    end = connections[0]['ends'][0]
    end['lanes'].append({'tile':[-7,-4],'arrival':[-6,-4]})
    assert C.prune_lanes(world,connections,served,{'west':[-999,0],'east':[28,24]},2) >= 1
    assert all(lane['tile'] != [-7,-4] for lane in end['lanes'])


def test_mismatched_storage_fails_before_array_reads(server_math):
    p = placement(Bounds(48,48),server_math)
    p.spec.update(Bounds(48,48,-1,0).metadata())
    with pytest.raises(ValueError,match='World storage'):
        E.RegionPlacement(p.world,p.content,'west',p.spec,p.collision,p.grid,p.sources,p.report)
    with pytest.raises(ValueError,match='dimensions'):
        C.own_ground(p.world,'west',np.ones((4,4),np.uint8))
    with pytest.raises(ValueError,match='dimensions'):
        X.declare_crossings({},b'','west',p.grid,2,[24,24],[48,48],p.collision['heights'],bounds=Bounds(50,50))
