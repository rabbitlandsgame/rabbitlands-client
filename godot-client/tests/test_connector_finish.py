"""Actual bridge coverage, connected bends and retained boundary contracts."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

REGIONS=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'_toolkit'),str(REGIONS/'_finishing')]
import connector_finish as F
from amberwood import mesh as M
from verify_runtime import VerticalRayIndex


def area(mesh):
    t=mesh.positions[mesh.indices.reshape(-1,3)]
    return np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1).sum()/2


def test_narrow_bridge_subtraction_keeps_the_road_outside_actual_native_footprint():
    road=M.quad([[-4,0,0],[-4,0,10],[4,0,10],[4,0,0]])
    native=M.quad([[-1.9,0,2],[-1.9,0,8],[1.9,0,8],[1.9,0,2]])
    before=native.positions.copy();result=F._subtract_native(road,F._triangles([native]))
    assert abs(area(result)-(80-3.8*6))<1e-9
    ray=VerticalRayIndex(F._triangles([result]))
    assert ray.top_hit(0,5) is None
    for x,z in ((2.0,5),(-2.,5),(0,1.999),(0,8.001)):
        assert ray.top_hit(x,z)==0.
    np.testing.assert_array_equal(native.positions,before)


def test_rotated_native_span_does_not_leave_half_cell_gaps_at_its_mouth():
    road=M.quad([[-5,0,-5],[-5,0,5],[5,0,5],[5,0,-5]])
    native=M.quad([[-1.9,0,-3],[-1.9,0,3],[1.9,0,3],[1.9,0,-3]])
    native.rotate_y(.23)
    result=F._subtract_native(road,F._triangles([native]))
    assert abs(area(result)-(100-3.8*6))<1e-8
    both=VerticalRayIndex(np.concatenate([F._triangles([result]),F._triangles([native])]))
    for x in np.linspace(-4.9,4.9,41):
        for z in np.linspace(-4.9,4.9,41):assert both.top_hit(x,z)==0.


def test_native_bridge_height_overrides_flawed_generated_height_without_removing_wide_support(monkeypatch):
    road=M.quad([[0,.03,-3.5],[40,.03,-3.5],[40,.03,3.5],[0,.03,3.5]])
    native=M.quad([[15,4,-1.9],[15,4,1.9],[25,4,1.9],[25,4,-1.9]])
    ground=M.quad([[-10,0,-10],[-10,0,10],[50,0,10],[50,0,-10]])
    build=SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_test':road})
    item={'road':{'id':'test'},'names':['Walk_ContinentRoad_test'],
          'points':np.array([[0.,0.,0.],[40.,0.,0.]]),'length':np.array([0.,40.]),
          'bridge':np.array([False,False]),'nativeY':np.array([0.,0.]),
          'spec':{'id':'test','profile':'land'}}
    monkeypatch.setattr(F.G,'plan',lambda:{'regions':{'test':{'ownershipPolygon':[[-10,-10],[50,-10],[50,10],[-10,10]],'translation':[0,0,0]}}})
    result=F._union_grid(build,'test',[item],F._triangles([native]),VerticalRayIndex(F._triangles([ground])))[0]
    ray=VerticalRayIndex(F._triangles([result]))
    assert ray.top_hit(20,0) is None
    assert ray.top_hit(20,3)>3.
    both=VerticalRayIndex(np.concatenate([F._triangles([result]),F._triangles([native])]))
    assert both.top_hit(20,0)==4.
    for x in np.arange(0,40.01,.5):assert both.top_hit(x,0) is not None
    t=result.positions[result.indices.reshape(-1,3)];normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);valid=abs(normal[:,1])>1e-8
    grade=np.linalg.norm(normal[valid][:,[0,2]],axis=1)/abs(normal[valid,1])
    assert grade.max()<.38001


def native_case(monkeypatch,native,points=((-12,4,0),(12,4,0)),causeway=False):
    points=np.asarray(points,float);a,b=points
    road=M.quad([a+[0,.03,-3.5],b+[0,.03,-3.5],b+[0,.03,3.5],a+[0,.03,3.5]])
    ground=M.quad([[-80,0,-20],[-80,0,20],[40,0,20],[40,0,-20]])
    build=SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_test':road})
    item={'road':{'id':'test'},'names':['Walk_ContinentRoad_test'],'points':points,
          'length':np.array([0.,np.linalg.norm(b[[0,2]]-a[[0,2]])]),'bridge':np.zeros(2,bool),'nativeY':np.zeros(2),
          'spec':{'id':'test','profile':'causeway' if causeway else 'land','anchor':b.tolist(),'outward':[1,0]}}
    monkeypatch.setattr(F.G,'plan',lambda:{'regions':{'test':{'ownershipPolygon':[[-80,-20],[40,-20],[40,20],[-80,20]],'translation':[0,0,0]}}})
    before=native.positions.copy()
    result=F._union_grid(build,'test',[item],F._triangles([native]),VerticalRayIndex(F._triangles([ground])))[0]
    np.testing.assert_array_equal(native.positions,before)
    return result,VerticalRayIndex(np.concatenate([F._triangles([result]),F._triangles([native])]))


@pytest.mark.parametrize('gradient',[0.,.15])
def test_actual_non_grid_native_edge_has_no_interpolated_height_lip(monkeypatch,gradient):
    native=M.quad([[-3.2,4-3.2*gradient,-1.9],[3.2,4+3.2*gradient,-1.9],
                   [3.2,4+3.2*gradient,1.9],[-3.2,4-3.2*gradient,1.9]])
    _,ray=native_case(monkeypatch,native)
    for x in (-3.2,3.2):
        for z in np.linspace(-1.8,1.8,19):
            for dx in (-.0001,.0001):assert abs(ray.top_hit(x+dx,z)-(4+(x+dx)*gradient))<1e-8
    for z in (-1.9,1.9):
        for x in np.linspace(-3.,3.,31):
            for dz in (-.0001,.0001):assert abs(ray.top_hit(x,z+dz)-(4+x*gradient))<1e-8


def test_real_causeway_rim_supports_all_conservative_lane_sample_rays(monkeypatch):
    native=M.quad([[-42,4,-3.5],[0,4,-3.5],[0,4,3.5],[-42,4,3.5]])
    result,ray=native_case(monkeypatch,native,((-60,4,0),(0,4,0)),True)
    new_ray=VerticalRayIndex(F._triangles([result]))
    for x in np.arange(-41.,-3.,.5):
        for lane in range(-3,4):
            for dx in (-.75,-.25,.25,.75):
                assert abs(ray.top_hit(x,lane+dx)-4.)<1e-8
        assert new_ray.top_hit(x,0.) is None
        assert new_ray.top_hit(x,3.75)==4.


def test_native_steep_ramp_retains_contact_with_bounded_actual_grade(monkeypatch):
    native=M.quad([[-3,2,-1.9],[3,6,-1.9],[3,6,1.9],[-3,2,1.9]])
    result,ray=native_case(monkeypatch,native)
    for x in np.arange(-12.,12.01,.25):assert ray.top_hit(x,0) is not None
    for x in (-3.,3.):
        for dx in (-.0001,.0001):assert abs(ray.top_hit(x+dx,0)-(4+(x+dx)*2/3))<1e-8
    t=F._triangles([result]);normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);valid=abs(normal[:,1])>1e-8
    grade=np.linalg.norm(normal[valid][:,[0,2]],axis=1)/abs(normal[valid,1])
    assert grade.max()<(2/3)/np.cos(np.pi/8)+1e-7


def test_retained_interface_inserts_original_non_grid_height_knots(monkeypatch):
    # A shallow native crown has a knot that a new half-metre face would bridge.
    old=M.merge([M.quad([[0,0,0],[3,0,0],[3,.002,.3],[0,.002,.3]]),
                 M.quad([[0,.002,.3],[3,.002,.3],[3,0,1],[0,0,1]])])
    new=M.quad([[3,0,0],[4,0,0],[4,0,1],[3,0,1]])
    monkeypatch.setattr(F.R,'_edge_distance',lambda build,region,xz:xz[:,0])
    final=F._conform_boundary(new,[old],None,'test');ray=VerticalRayIndex(F._triangles([final]));original=VerticalRayIndex(F._triangles([old]))
    for z in np.linspace(0,1,101):assert abs(ray.top_hit(3,z)-original.top_hit(3,z))<1e-10


def test_retained_boundary_uses_real_bridge_top_above_hidden_old_road(monkeypatch):
    native=M.quad([[-42,4,-3.5],[0,4,-3.5],[0,4,3.5],[-42,4,3.5]])
    monkeypatch.setattr(F.R,'_edge_distance',lambda build,region,xz:np.maximum(-xz[:,0],0.))
    _,ray=native_case(monkeypatch,native,((-64,-2,0),(0,-2,0)),True)
    for x in np.linspace(-4,-.25,41):
        for z in (-3.75,0,3.75):assert abs(ray.top_hit(x,z)-4.)<1e-8


def test_diagonal_retained_contour_is_not_rejected_by_zero_coefficient_free_corner():
    values=np.array([9.081412690719539,8.95,9.,8.812712113868653])
    retained=np.array([True,False,False,True]);allowed=np.ones(4,bool)
    result=F._contact_grade(values,allowed,retained,2,retained,np.full(4,.38))
    np.testing.assert_array_equal(result[retained],values[retained])
    t=np.array([[0,result[0],0],[.5,result[1],0],[0,result[2],.5],[.5,result[3],.5]])
    faces=t[[[0,2,3],[0,1,3]]];n=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
    assert np.max(np.linalg.norm(n[:,[0,2]],axis=1)/abs(n[:,1]))<.38/np.cos(np.pi/8)+1e-7


def test_footing_protection_does_not_include_a_canopy_or_fill_between_separate_piers():
    from amberwood.stonework import MeshGroup
    from regionbuild import RegionBuild,Placement
    b=RegionBuild(None);tree=MeshGroup();tree.add(M.box((1,8,1)).translate(0,4,0));tree.add(M.box((30,2,30)).translate(0,9,0))
    b.add_mesh('tree',tree);b.place(Placement('Landmark_tree','tree',(0,0,0),collides=True,landmark='tree'))
    polygons=F._footing_polygons(b)
    assert min(F._footing_distance(np.array([[0.,0.]]),p)[0] for p in polygons)==0.
    assert min(F._footing_distance(np.array([[8.,0.]]),p)[0] for p in polygons)>7.
    b.meshes['tree']=M.merge([M.box((1,6,1)).translate(-5,3,0),M.box((1,6,1)).translate(5,3,0),M.box((12,1,3)).translate(0,6.5,0)])
    polygons=F._footing_polygons(b)
    assert len(polygons)==2
    assert min(F._footing_distance(np.array([[0.,0.]]),p)[0] for p in polygons)>4.
    for x in (-5.,5.):assert min(F._footing_distance(np.array([[x,0.]]),p)[0] for p in polygons)==0.


def seat_case(roads):
    from regionbuild import RegionBuild
    gx,gz=np.meshgrid(np.arange(-24.,25.),np.arange(-8.,21.))
    b=RegionBuild(SimpleNamespace(gx=gx,gz=gz,height=np.zeros(gx.shape)))
    b.terrain_meshes['Terrain_Test']=M.quad([[-24,0,-8],[-24,0,20],[24,0,20],[24,0,-8]])
    inputs=[]
    for i,(points,mesh,spec) in enumerate(roads):
        points=np.asarray(points,float);length=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points[:,[0,2]],axis=0),axis=1))]
        name='Walk_ContinentRoad_'+str(i);b.terrain_meshes[name]=mesh
        inputs.append({'road':{'id':str(i),'stations':points.tolist()},'names':[name],'points':points,'length':length,'bridge':np.zeros(len(points),bool),'spec':spec})
    F._seat(b,'test',inputs)
    return VerticalRayIndex(F._triangles([b.terrain_meshes['Terrain_Test']]))


def test_seating_samples_the_full_visible_cross_slope_not_the_inner_fold_width():
    mesh=M.quad([[-4.25,4-.35*4.25,-4],[4.25,4+.35*4.25,-4],[4.25,4+.35*4.25,4],[-4.25,4-.35*4.25,4]])
    ray=seat_case([([[0,3.97,-4],[0,3.97,4]],mesh,{'profile':'land'})])
    road_y=4+.35*4.1875
    assert .0<road_y-ray.top_hit(4.1875,0)<.1


def test_causeway_does_not_disable_soil_contact_on_a_distant_parallel_road():
    a=M.quad([[-20,4,-4.25],[0,4,-4.25],[0,4,4.25],[-20,4,4.25]])
    b=M.quad([[-20,4,7.75],[0,4,7.75],[0,4,16.25],[-20,4,16.25]])
    ray=seat_case([([[-20,3.97,0],[0,3.97,0]],a,{'profile':'causeway','anchor':[0,4,0],'outward':[1,0]}),
                   ([[-20,3.97,12],[0,3.97,12]],b,{'profile':'land'})])
    assert abs(ray.top_hit(-10,12)-3.97)<1e-8
    assert abs(ray.top_hit(-10,0))<1e-8  # actual causeway bed remains below its deck
