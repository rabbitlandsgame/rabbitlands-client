"""Physical outer-apron regressions; no packaged GLB is an input."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import sys
import numpy as np
import pytest

REGIONS=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'_toolkit'),str(REGIONS/'_outer')]
from amberwood import mesh as M
from verify_runtime import VerticalRayIndex
import outer_aprons as O


def plane(lo,hi,y=10,material='meadow_grass'):
    a,b=lo;c,d=hi
    m=M.quad([[a,y,b],[a,y,d],[c,y,d],[c,y,b]],material=material)
    m.uvs=m.positions[:,[0,2]]*.09+np.array([.2,.7])
    return m


def build(region='amberwood', placements=()):
    gx,gz=np.meshgrid(np.arange(-40,142,2.),np.arange(-40,142,2.))
    return NS(terrain_meshes={'Terrain_Base':plane([-40,-40],[140,140])},
        water_meshes={} if region=='whitehorn_range' else {'Water_Sea':plane([-40,-40],[140,140],0,'water_sea')},
        placements=list(placements),meshes={'prop':plane([-1,-1],[1,1],0)},
        landmarks=[],interactives=[],npc_markers=[],harvestables=[],portals=[],spawns=[],
        geography_roads=[],streaming_borders=[],notes=[],terrain=NS(gx=gx,gz=gz,height=gx*0+10,tree_block=gx< -1000))


def prop(name,x,z,kind='tree',landmark=None):
    return NS(node=name,mesh='prop',position=(x,10.4,z),scale=1.,rotation_y=0.,kind=kind,landmark=landmark,collides=True)


@pytest.fixture
def geography():
    plan={'regions':{r:{'nativePlayableBounds':[[0,0],[100,100]],'translation':[0,0,0],
        'ownershipPolygon':[[-40,-40],[140,-40],[140,140],[-40,140]]} for r in O.CURVES}}
    with patch.object(O.G,'plan',return_value=plan),patch.object(O.G,'boundary_sample',side_effect=lambda r,p,**k:(np.full(len(p),np.inf),np.zeros(len(p)))):
        yield


def rays(b):
    return VerticalRayIndex(np.concatenate([m.positions[m.indices].reshape(-1,3,3) for m in b.terrain_meshes.values() if m.triangle_count]))


def test_signed_perimeter_excludes_internal_island_edges():
    edges=O._perimeter([plane([-5,-5],[105,105]),plane([20,20],[30,30],90)],np.array([0,0]),np.array([100,100]))
    assert len(edges)==4
    assert np.max(edges[:,:,1])==10


def test_extension_uses_actual_submerged_native_apron_before_perimeter(geography):
    b=build();b.terrain_meshes['Terrain_Base']=plane([-40,-40],[140,140],-4)
    s=O.capture(b,'amberwood')
    shaped,_=O._reshape(b,s,np.array([[-15.,90.,40.]]),extension=True)
    assert shaped[0,1]<0
    assert shaped[0,1]>=-7


def test_long_face_cannot_tilt_native_playable_ground_and_heightfield(geography):
    b=build();s=O.capture(b,'amberwood');O.apply(b,'amberwood',s)
    ray=rays(b)
    for x,z in ((0,0),(.1,50),(50,.1),(99.9,99.9),(50,50)):
        assert ray.top_hit(x,z)==pytest.approx(10,abs=1e-8)
    assert b.terrain.height[0,0]<0
    assert b.terrain.height[45,45]==10
    assert b.outer_apron_audit['nativePlayableVerticesChanged']==0


def test_shared_bands_roads_and_structural_footings_are_preserved(geography):
    b=build(placements=[prop('house',-15,80,'building')]);s=O.capture(b,'amberwood')
    points=np.array([[-15.,10.,80.],[-15.,10.,30.],[-15.,10.,50.]])
    with patch.object(O.G,'boundary_sample',return_value=(np.array([999.,20.,999.]),None)),patch.object(O,'_road_distance',return_value=np.array([999.,999.,2.])):
        shaped,_=O._reshape(b,s,points,extension=True)
    np.testing.assert_array_equal(shaped,points)


def test_outer_scatter_follows_contact_and_underwater_scatter_is_removed(geography):
    b=build(placements=[prop('near-tree',-6,20),prop('drowned-tree',-30,20),prop('core-tree',20,20),prop('story-rock',-25,80,'rock','lore')])
    original={p.node:p.position for p in b.placements};s=O.capture(b,'amberwood');O.apply(b,'amberwood',s)
    after={p.node:p.position for p in b.placements};ray=rays(b)
    assert 'drowned-tree' not in after
    assert after['near-tree'][1]==pytest.approx(ray.top_hit(-6,20)+.4)
    assert after['near-tree'][1]<original['near-tree'][1]
    assert after['core-tree']==original['core-tree']
    assert after['story-rock']==original['story-rock']


def test_dry_whitehorn_cuts_physical_edge_without_inventing_water(geography):
    b=build('whitehorn_range',placements=[prop('past-edge',-35,20)])
    s=O.capture(b,'whitehorn_range');O.apply(b,'whitehorn_range',s)
    assert not b.water_meshes
    assert 'Terrain_OuterEscarpment_whitehorn_range' in b.terrain_meshes
    assert rays(b).top_hit(-35,20) is None
    assert rays(b).top_hit(50,50)==pytest.approx(10)
    assert not b.placements


def test_water_replacement_preserves_native_uv_and_has_no_double_surface(geography):
    b=build();s=O.capture(b,'amberwood');O.apply(b,'amberwood',s)
    sea=b.water_meshes.get('Water_OuterApron_amberwood',b.water_meshes['Water_Sea'])
    np.testing.assert_allclose(sea.uvs,sea.positions[:,[0,2]]*.09+[.2,.7],atol=1e-8)
    for x,z in ((-15.3,20.1),(-30.3,25.1),(30.3,50.1)):
        covering=sum(VerticalRayIndex(m.positions[m.indices].reshape(-1,3,3)).top_hit(x,z) is not None for m in b.water_meshes.values())
        assert covering==1


def test_deterministic_and_double_finish_fails_closed(geography):
    a,b=build(),build()
    O.apply(a,'amberwood',O.capture(a,'amberwood'));O.apply(b,'amberwood',O.capture(b,'amberwood'))
    assert a.outer_apron_audit==b.outer_apron_audit
    for name in a.terrain_meshes:np.testing.assert_array_equal(a.terrain_meshes[name].positions,b.terrain_meshes[name].positions)
    with pytest.raises(ValueError,match='already finished'):O.apply(a,'amberwood',O.capture(build(),'amberwood'))


def test_piecewise_water_uvs_preserve_compacted_texture_phase():
    west=plane([-20,-20],[0,20],0,'water_sea')
    east=plane([0,-20],[20,20],0,'water_sea')
    east.uvs[:,0]=east.positions[:,0]*.04+.2
    mesh=M.merge([west,east],'water_sea');sampler=O.WaterUV(mesh)
    actual=sampler.sample(np.array([[-10.,3.],[10.,3.],[0.,3.]]))
    np.testing.assert_allclose(actual,[[-.7,.97],[.6,.97],[.2,.97]],atol=1e-8)


def test_native_tidal_mangrove_retains_wet_habitat_and_root_offset(geography):
    b=build('manymouth_delta',placements=[prop('mangrove_0028',50,103.6),prop('mangrove_mat_0001',60,103.6)])
    b.terrain_meshes['Terrain_Base']=plane([-40,-40],[140,140],-.35)
    for p in b.placements:p.position=(p.position[0],-.8,p.position[2])
    s=O.capture(b,'manymouth_delta');O.apply(b,'manymouth_delta',s)
    assert len(b.placements)==2
    for p in b.placements:
        assert p.position[1]==pytest.approx(rays(b).top_hit(p.position[0],p.position[2])-.45)


def test_complete_existing_water_sheet_is_preserved_without_uv_retriangulation(geography):
    b=build();west=plane([-40,-40],[0,140],0,'water_sea');east=plane([0,-40],[140,140],0,'water_sea')
    east.uvs[:,0]=east.positions[:,0]*.04+.2
    b.water_meshes['Water_Sea']=M.merge([west,east],'water_sea')
    positions=b.water_meshes['Water_Sea'].positions.copy();uvs=b.water_meshes['Water_Sea'].uvs.copy()
    O.apply(b,'amberwood',O.capture(b,'amberwood'))
    assert list(b.water_meshes)==['Water_Sea']
    np.testing.assert_array_equal(b.water_meshes['Water_Sea'].positions,positions)
    np.testing.assert_array_equal(b.water_meshes['Water_Sea'].uvs,uvs)
