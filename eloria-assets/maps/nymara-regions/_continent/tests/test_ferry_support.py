"""Full bank/hull terrain support remains buildable after real road settling."""
from pathlib import Path
import sys
import numpy as np
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import ferry_support as S
import ferry_export as F
import landscape as L
from world_layout import World


def shore():
    world=World.__new__(World)
    world.x=np.arange(-100.,102.,2.);world.z=np.arange(-60.,62.,2.)
    world.gx,world.gz=np.meshgrid(world.x,world.z)
    world.x0=world.x[0];world.z0=world.z[0]
    world.plan={'sea_level':0.,'rivers':[],'lakes':[]}
    world.height=-world.gx*.15
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    world.regions={'a':{'center':[-50.,0.]}};world.ids=['a']
    world.connections=[{'id':'test','type':'ferry','regions':['a','a'],'landings':[[-12.,0.],[-12.,0.]]}]
    world.quay_contacts=[]
    world.prepare_quay_court([-12.,0.])
    world.assembly_target=world.height.copy();world.assembly_weight=np.zeros_like(world.height)
    world.road_target=np.full_like(world.height,-4.)
    world.road_distance=np.maximum(abs(world.gz)-2.5,0)
    world.roads=[{'points':[[-70.,4.,0.],[-12.,1.8,0.]]}]
    world.restore_drainage_corridor=lambda stage:None
    return world


def test_full_triangle_footprints_survive_road_shoulder_drift():
    unprotected=shore();initial=F.fit_landing(unprotected,[-12.,0.],'a')
    banks=initial['centres'][:,None,:]+np.array([-F.HALF_WIDTH,0,F.HALF_WIDTH])[None,:,None]*initial['side']
    previous_bank=unprotected.height_at(banks[...,0],banks[...,1])
    unprotected.settle_roads()
    assert np.max(abs(previous_bank-unprotected.height_at(banks[...,0],banks[...,1])))>.16
    world=shore();fit=F.fit_landing(world,[-12.,0.],'a')
    S.remember_ferry_fit(world,fit)
    before=world.height.copy();world.settle_roads()
    np.testing.assert_array_equal(world.height[world.ferry_shore_mask],before[world.ferry_shore_mask])
    final=F.fit_landing(world,[-12.,0.],'a')
    assert final['contactError']<=.16 and final['maximumGrade']<=.45
    assert final['minimumBoatDepth']>=.65
    report=S.validate_final_ferries(world)
    assert len(report['finalFits'])==1 and report['maximumProtectedHeightChange']==0.


def test_rotated_rectangle_covers_every_corner_of_intersecting_sample_cells():
    world=shore();forward=np.array([np.cos(.37),np.sin(.37)]);side=np.array([-forward[1],forward[0]])
    centre=np.array([-12.45,3.1]);mask=S.rectangle_vertices(world,centre,forward,9.13,1.35)
    rng=np.random.default_rng(108)
    points=centre+rng.uniform(-9.13,9.13,(2000,1))*forward+rng.uniform(-1.35,1.35,(2000,1))*side
    ix=np.floor((points[:,0]-world.x0)/2).astype(int);iz=np.floor((points[:,1]-world.z0)/2).astype(int)
    for dx,dz in ((0,0),(1,0),(0,1),(1,1)):assert mask[iz+dz,ix+dx].all()
    assert not mask[0,0] and mask.sum()<250


def test_restore_protects_full_hull_and_keeps_distant_terrain_untouched():
    world=shore();fit=F.fit_landing(world,[-12.,0.],'a');S.remember_ferry_fit(world,fit)
    hull=F.boat_points(fit['boatCenter'],fit['forward'],fit['side'])
    before=world.height_at(hull[:,0],hull[:,1]).copy()
    world.height+=4.
    distant=world.height[0,0]
    S.restore_graded_shores(world,np.zeros_like(world.height,bool))
    np.testing.assert_allclose(world.height_at(hull[:,0],hull[:,1]),before,atol=0,rtol=0)
    assert world.height[0,0]==distant
    assert F.fit_landing(world,[-12.,0.],'a')['minimumBoatDepth']>=.65


def test_future_forecourt_trial_restores_existing_fit_without_altering_its_target():
    world=shore();fit=F.fit_landing(world,[-12.,0.],'a');S.remember_ferry_fit(world,fit)
    target=world.ferry_shore_target.copy();world.height[world.ferry_shore_mask]+=2.
    S.restore_selected_shores(world)
    np.testing.assert_array_equal(world.height[world.ferry_shore_mask],target[world.ferry_shore_mask])
    np.testing.assert_array_equal(world.ferry_shore_target,target)


def test_changed_protected_ground_fails_final_readback_even_if_fit_still_exists():
    world=shore();fit=F.fit_landing(world,[-12.,0.],'a');S.remember_ferry_fit(world,fit)
    world.height[world.ferry_shore_mask]+=.01
    with pytest.raises(ValueError,match='moved fitted ferry terrain'):S.validate_final_ferries(world)


def test_final_readback_ignores_only_the_group_owned_quay(monkeypatch):
    world=shore();seen=[]
    original=F.fit_landing
    def fit(candidate,landing,region,**kwargs):
        seen.append(list(kwargs.get('ignore_connection_ids',())))
        return original(candidate,landing,region,**kwargs)
    monkeypatch.setattr(F,'fit_landing',fit)
    report=S.validate_final_ferries(world)
    assert len(report['finalFits'])==1
    assert seen==[F.landing_groups(world)[0]['connections']]
