from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest
REGIONS=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'_toolkit'),str(REGIONS/'_finishing')]
import connector_finish as F
from amberwood import mesh as M
from regionbuild import RegionBuild,Placement
from verify_runtime import VerticalRayIndex


def test_higher_slope_foot_is_protected_without_roof_overhang():
    b=RegionBuild(None)
    b.terrain_meshes['Terrain_slope']=M.quad([[-10,-2,-10],[-10,-2,10],[10,2,10],[10,2,-10]])
    b.add_mesh('building',M.merge([M.box((1,6,1)).translate(-5,2,0),
        M.box((1,4,1)).translate(5,3,0),M.box((18,1,6)).translate(0,5.5,0)]))
    b.place(Placement('Bridge','building',(0,0,0),collides=True))
    polygons=F._footing_polygons(b)
    for x in (-5.,5.):assert min(F._footing_distance(np.array([[x,0.]]),p)[0] for p in polygons)==0.
    assert min(F._footing_distance(np.array([[0.,0.]]),p)[0] for p in polygons)>4.
    assert min(F._footing_distance(np.array([[8.,2.]]),p)[0] for p in polygons)>2.


def bank_case(ground_y=.5,causeway=False,narrow=False):
    gx,gz=np.meshgrid(np.arange(-9.,10.),np.arange(-9.,10.))
    b=RegionBuild(SimpleNamespace(gx=gx,gz=gz,height=np.full(gx.shape,ground_y)))
    b.terrain_meshes['Terrain_bank']=M.quad([[-9,ground_y,-9],[-9,ground_y,9],[9,ground_y,9],[9,ground_y,-9]])
    b.water_meshes['Water']=M.quad([[-9,0,-9],[-9,0,9],[9,0,9],[9,0,-9]])
    deck=M.quad([[-3.2,4,-1.9],[3.2,4,-1.9],[3.2,4,1.9],[-3.2,4,1.9]])
    deck.rotate_y(0. if narrow else .23)
    b.terrain_meshes['Walk_native']=deck
    whole=M.quad([[-8,4,-4.25],[8,4,-4.25],[8,4,4.25],[-8,4,4.25]])
    b.terrain_meshes['Walk_ContinentRoad_test']=F._subtract_native(whole,F._triangles([deck]))
    points=np.array([[-8.,3.97,0.],[8.,3.97,0.]])
    spec={'profile':'causeway','anchor':[8,4,0],'outward':[1,0]} if causeway else {'profile':'land'}
    item={'road':{'id':'test','stations':points.tolist()},'names':['Walk_ContinentRoad_test'],'points':points,
          'length':np.array([0.,16.]),'bridge':np.ones(2,bool),'spec':spec}
    if narrow:
        points=np.array([[-20.,3.97,0.],[80.,3.97,0.]])
        item.update(points=points,length=np.array([0.,100.]),widthDistances=np.array([0.,50.,58.,100.]),halfWidths=np.array([1.9,1.9,4.25,4.25]))
        item['road']['stations']=points.tolist()
    before=deck.positions.copy();water=b.water_meshes['Water'].positions.copy()
    F._seat(b,'test',[item]);np.testing.assert_array_equal(deck.positions,before)
    np.testing.assert_array_equal(b.water_meshes['Water'].positions,water)
    return b,VerticalRayIndex(F._triangles([b.terrain_meshes['Terrain_bank']]))


def test_dry_bank_exact_native_edge_meets_road_without_filling_bridge_interior():
    b,ray=bank_case()
    native=b.terrain_meshes['Walk_native'];rotation=M.rotation_y(.23)[:3,:3]
    for x in np.linspace(-3.1,3.1,31):
        for z in (-1.901,1.901):
            p=np.array([x,0,z])@rotation.T
            assert abs(ray.top_hit(*p[[0,2]])-3.97)<.065
    assert abs(ray.top_hit(0,0)-.5)<1e-8
    t=F._triangles([b.terrain_meshes['Terrain_bank']]);cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])
    assert abs(np.sum(abs(cross[:,1]))*.5-18*18)<1e-7


def test_native_wet_channel_and_causeway_bed_remain_below_deck():
    _,ray=bank_case(-.5,True)
    for x in np.linspace(-3,3,13):assert abs(ray.top_hit(x,0)+.5)<1e-8


def test_causeway_landing_excavates_only_protruding_soil():
    _,ray=bank_case(4.8,True)
    for x in np.linspace(-3,3,13):assert abs(ray.top_hit(x,0)-3.97)<1e-8


def test_nearest_road_shoulder_sample_resolves_a_native_subtraction_hole():
    road=M.quad([[-5,4,-5],[-5,4,5],[5,4,5],[5,4,-5]])
    native=M.quad([[-2,4,-3],[-2,4,3],[4.2,4,3],[4.2,4,-3]])
    ray=VerticalRayIndex(F._triangles([F._subtract_native(road,F._triangles([native]))]))
    assert ray.top_hit(4.,0) is None
    assert F._nearest_road_height(ray,[4.,0])==4.


def test_native_cut_conforms_neighboring_material_meshes_across_old_centroid_cutoff():
    def face(points):
        p=np.asarray(points,float)
        return M.Mesh(positions=p,normals=np.zeros_like(p),uvs=p[:,[0,2]],indices=np.arange(3))
    a=face([[-.3,0,5.],[.3,0,5.6],[-.6,0,4.5]])
    b=face([[.3,0,5.6],[-.3,0,5.],[.6,0,6.1]])
    native=M.quad([[-2,4,4],[-2,4,7],[0,4,7],[0,4,4]])
    road={'stations':[[-10,4,0],[10,4,0]]}
    shaped=[]
    for mesh in (a,b):
        out=F._split_native_landing(mesh,F._triangles([native]),[road],None)
        out.positions[:,1]=out.positions[:,2]**2
        shaped.append(VerticalRayIndex(F._triangles([out])))
    for x in np.linspace(-.3,.3,61):
        z=x+5.3
        assert abs(shaped[0].top_hit(x,z)-shaped[1].top_hit(x,z))<1e-9


def test_authored_timber_width_retains_native_span_and_full_shared_collar(monkeypatch):
    road=M.quad([[0,4,-3.5],[100,4,-3.5],[100,4,3.5],[0,4,3.5]])
    native=M.merge([M.quad([[0,4,-1.9],[58,4,-1.9],[58,4,1.9],[0,4,1.9]]),
                    M.quad([[58,4,-3.5],[100,4,-3.5],[100,4,3.5],[58,4,3.5]])])
    ground=M.quad([[-10,0,-12],[110,0,-12],[110,0,12],[-10,0,12]])
    b=SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_test':road})
    item={'road':{'id':'test'},'names':['Walk_ContinentRoad_test'],
          'points':np.array([[0.,3.97,0.],[100.,3.97,0.]]),'length':np.array([0.,100.]),
          'bridge':np.ones(2,bool),'spec':{'id':'test','profile':'causeway','anchor':[100,4,0],'outward':[1,0]},
          'widthDistances':np.array([0.,40.,52.,58.,100.]),'halfWidths':np.array([1.9,1.9,1.9,4.25,4.25])}
    monkeypatch.setattr(F.G,'plan',lambda:{'regions':{'test':{'ownershipPolygon':[[-10,-12],[110,-12],[110,12],[-10,12]],'translation':[0,0,0]}}})
    output=F._union_grid(b,'test',[item],F._triangles([native]),VerticalRayIndex(F._triangles([ground])))[0]
    new=VerticalRayIndex(F._triangles([output]));both=VerticalRayIndex(np.concatenate([F._triangles([output]),F._triangles([native])]))
    for x in np.arange(1.,50.,.5):
        assert new.top_hit(x,2.) is None
        assert both.top_hit(x,0)==4.
    for x in np.arange(58.,100.,.5):
        for z in (-3.75,0,3.75):assert abs(both.top_hit(x,z)-4.)<1e-8


def test_default_and_explicit_full_width_have_identical_meshes(monkeypatch):
    import copy
    road=M.quad([[0,4,-3.5],[20,4,-3.5],[20,4,3.5],[0,4,3.5]])
    b=SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_test':road})
    item={'road':{'id':'test'},'names':['Walk_ContinentRoad_test'],
          'points':np.array([[0.,3.97,0.],[20.,3.97,0.]]),'length':np.array([0.,20.]),
          'bridge':np.zeros(2,bool),'spec':{'id':'test','profile':'land'}}
    monkeypatch.setattr(F.G,'plan',lambda:{'regions':{'test':{'ownershipPolygon':[[-10,-12],[30,-12],[30,12],[-10,12]],'translation':[0,0,0]}}})
    implicit=F._union_grid(b,'test',[item])[0]
    explicit=copy.deepcopy(item);explicit.update(widthDistances=np.array([0.,20.]),halfWidths=np.array([4.25,4.25]))
    default=F._union_grid(b,'test',[explicit])[0]
    for field in ('positions','normals','uvs','indices'):np.testing.assert_array_equal(getattr(implicit,field),getattr(default,field))


def test_width_controls_keep_original_survey_and_require_widening_before_collar():
    road=M.quad([[0,4,-3.5],[100,4,-3.5],[100,4,3.5],[0,4,3.5]])
    survey=[[0,3.97,0],[100,3.97,0]]
    record={'id':'test','stations':survey,'contactStations':[[0,3.97,0],[52,3.97,0],[58,3.97,0],[100,3.97,0]],
            'contactWidths':[3.8,3.8,8.5,8.5]}
    b=SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_test':road},streaming_borders=[{'id':'test','profile':'land'}])
    ground=VerticalRayIndex(F._triangles([road]))
    item=F._road_inputs(b,'test',[record],ground,None)[0]
    assert record['originalSurveyStations']==survey
    np.testing.assert_array_equal(F._half_width(item,np.array([20.,58.,100.])),[1.9,4.25,4.25])
    record['contactWidths']=[3.8,3.8,3.8,8.5]
    with pytest.raises(ValueError,match='before the last 42'):
        F._road_inputs(b,'test',[record],ground,None)


def test_measured_causeway_is_the_contact_floor_after_buried_soil_is_cut():
    native=M.quad([[-42,4,-3.5],[0,4,-3.5],[0,4,3.5],[-42,4,3.5]])
    old=M.quad([[-42,2,-4.5],[0,2,-4.5],[0,2,4.5],[-42,2,4.5]])
    soil=M.quad([[-45,6,-8],[3,6,-8],[3,6,8],[-45,6,8]])
    points=np.array([[-41.5,0,3.5],[-41.5,0,3.6],[-41.5,0,3.8]])
    tri=F._triangles([native,old]);ground=VerticalRayIndex(F._triangles([soil]))
    before,_,_=F._native_contact(points,np.ones(3,bool),tri,ground)
    assert np.isnan(before).all()
    after,_,_=F._native_contact(points,np.ones(3,bool),tri,ground,
                               visible_causeways=[(VerticalRayIndex(F._triangles([native])),4.)])
    np.testing.assert_array_equal(after,np.full(3,4.))
    # The lower buried layer itself never becomes authoritative.
    unrelated,_,_=F._native_contact(points,np.ones(3,bool),F._triangles([old]),ground,
                                   visible_causeways=[(VerticalRayIndex(F._triangles([native])),4.)])
    assert np.isnan(unrelated).all()


def test_exact_width_boundary_is_not_projected_into_native_hole_by_roundoff(monkeypatch):
    original=F.G._road_coordinates
    def rounded(points,stations):
        distance,along=original(points,stations)
        distance=np.where(np.abs(distance-1.9)<1e-8,distance+1e-12,distance)
        return distance,along
    # Ordinary dry bank at the exact generated/native edge still receives
    # the visible road height under a conservative distance-roundoff input.
    monkeypatch.setattr(F.G,'_road_coordinates',rounded)
    b,ray=bank_case(narrow=True)
    for z in (-1.9,1.9):
        for x in np.arange(-3.,3.1,.2):assert abs(ray.top_hit(x,z)-3.97)<.07


@pytest.mark.parametrize('height,expected',[(25.,3.97),(-.5,-.5)])
def test_clipped_bend_seats_dry_nominal_band_but_does_not_fill_a_missing_wet_floor(height,expected):
    gx,gz=np.meshgrid(np.arange(-8.,9.),np.arange(-8.,9.))
    b=RegionBuild(SimpleNamespace(gx=gx,gz=gz,height=np.full(gx.shape,height)))
    b.terrain_meshes['Terrain_bank']=M.quad([[-8,height,-8],[-8,height,8],[8,height,8],[8,height,-8]])
    b.water_meshes['Water']=M.quad([[-8,0,-8],[-8,0,8],[8,0,8],[8,0,-8]])
    p=np.array([[-4.,4.,-4.],[4.,4.,-4.],[0.,4.,4.]])
    b.terrain_meshes['Walk_ContinentRoad_test']=M.Mesh(positions=p,normals=np.zeros_like(p),uvs=p[:,[0,2]],indices=np.arange(3))
    points=np.array([[0.,3.97,-4.],[0.,3.97,4.]])
    item={'road':{'id':'test','stations':points.tolist()},'names':['Walk_ContinentRoad_test'],
          'points':points,'length':np.array([0.,8.]),'bridge':np.zeros(2,bool),'spec':{'profile':'land'}}
    F._seat(b,'test',[item]);ray=VerticalRayIndex(F._triangles([b.terrain_meshes['Terrain_bank']]))
    assert abs(ray.top_hit(2.5,2.5)-expected)<.01
