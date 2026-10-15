"""The native Whitehorn doors must work without server floor-opening passes."""
from pathlib import Path
from types import SimpleNamespace
import json,math,sys
import numpy as np
import pytest

PACKAGE=Path(__file__).resolve().parents[1]
CLIENT=PACKAGE.parents[3]
WORKSPACE=CLIENT.parent
SERVER=WORKSPACE/'work-output/southern-rollout/publish/server'
sys.path[:0]=[str(SERVER),str(SERVER/'tools'),str(PACKAGE.parent/'_toolkit')]
import sync_authored_collision as S
import verify_runtime as V
from eloria.world import World
from eloria.collision import CollisionMap,with_step_mask

DOORS={'gate-store-door','snowline-cell-door','west-watch-cave-mouth',
       'whitehorn-barrow-door','whitehorn-glacier-temple-door',
       'whitehorn-ice-cave-mouth','whitehorn-mine-adit'}
APPROACHES={
    'snowline-cell-door':((368,282),16),
    'west-watch-cave-mouth':((29,254),15),
    'whitehorn-glacier-temple-door':((220,341),15),
    'whitehorn-ice-cave-mouth':((40,176),16),
    'whitehorn-mine-adit':((324,254),16),
}

@pytest.fixture(scope='module')
def built():
    manifest=json.loads((PACKAGE/'world.json').read_text())
    cells=int(manifest['asset']['serverCells'])
    raw=S.sources.SOURCES['whitehorn_range'].load(PACKAGE.parent.parent,cells)
    factor,_,_=S.choose_stage(raw);grid=S.rescale(raw,factor)
    world=World.__new__(World);world.settings=SimpleNamespace(max_walk_height_change=2)
    world.sessions=[];world.animals_by_map={};world.animals={}
    world.collision_maps={'whitehorn_range':with_step_mask(CollisionMap(cells,cells,grid.tobytes()),2)}
    doc,blob=V.load_glb(PACKAGE/'world.glb')
    tri,_=V.collect_triangles(doc,blob,lambda n:n.startswith(('Terrain_','Walk_')))
    rays=V.VerticalRayIndex(tri)
    portals={p['id']:p for p in manifest['portals'] if p['id'] in DOORS}
    return manifest,world,rays,portals


def served_tile(manifest,native_tile):
    origin=manifest['coordinateTransform']['serverOrigin']
    native=manifest.get('continentGeography',{}).get('nativeServerOrigin',[120,120])
    return tuple(int(p+o-n) for p,o,n in zip(native_tile,origin,native))


def actor_xz(manifest,tile):
    ox,oy=manifest['coordinateTransform']['serverOrigin']
    return tile[0]-ox+.5,oy-tile[1]-.5


def test_native_core_and_published_address_frame_are_distinct(built):
    manifest,_,_,_=built
    geography=manifest.get('continentGeography')
    if geography:
        assert geography['nativeServerOrigin']==[120,120]
        assert geography['nativeServerCells']==[396,396]
        plan=json.loads((PACKAGE.parent/'continent-geography.json').read_text())['regions']['whitehorn_range']
        assert manifest['coordinateTransform']['serverOrigin']==plan['serverOrigin']
        assert [manifest['asset']['serverCells']]*2==plan['serverCells']
    else:
        assert manifest['coordinateTransform']['serverOrigin']==[120,120]
        assert manifest['asset']['serverCells']==396

def test_all_seven_ordinary_door_identities_are_preserved(built):
    _,_,_,portals=built
    assert set(portals)==DOORS
    assert all(p['destinationMap']=='whitehorn_glacier_temple' for p in portals.values())

@pytest.mark.parametrize('door',sorted(DOORS))
def test_exact_door_reachable_without_server_floor_opening(built,door):
    manifest,world,rays,portals=built;target=tuple(portals[door]['serverTile'])
    path=world.find_path('whitehorn_range',served_tile(manifest,(106,69)),target,set())
    assert path and tuple(path[-1])==target,(door,target)
    surface=rays.top_hit(*actor_xz(manifest,target))
    assert surface is not None
    assert abs(surface-(portals[door]['position'][1]-.1))<.65,(door,surface,portals[door]['position'])

@pytest.mark.parametrize('door',sorted(APPROACHES))
def test_front_approach_is_short_and_physically_grounded(built,door):
    manifest,world,rays,portals=built;start,limit=APPROACHES[door]
    start=served_tile(manifest,start)
    target=tuple(portals[door]['serverTile'])
    path=world.find_path('whitehorn_range',start,target,set())
    assert path and tuple(path[-1])==target,(door,start,target)
    assert sum(math.dist(a,b) for a,b in zip([start]+path,path))<=limit,(door,len(path))
    heights=[rays.top_hit(*actor_xz(manifest,tile)) for tile in [start]+path]
    assert all(y is not None for y in heights)
    assert max(abs(a-b) for a,b in zip(heights,heights[1:]))<.85,(door,heights)

def test_temple_stair_and_deck_share_a_supported_joint(built):
    _,_,rays,_=built
    # Seven broad lanes cross the former0.4m void. A collision-only opening
    # would still expose the lower terrain here and fail this geometry test.
    for x in np.linspace(95.5,103.5,7):
        heights=[rays.top_hit(float(x),float(z)) for z in np.linspace(-224.8,-225.9,24)]
        assert all(y is not None and 69.7<y<70.2 for y in heights),heights
        assert max(abs(a-b) for a,b in zip(heights,heights[1:]))<.3
