"""Later terrain shaping follows the road that border grading actually emits."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

REGIONS=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'_toolkit'),str(REGIONS/'_northern')]
from amberwood import mesh as M
import road_profiles as R
from regionbuild import RegionBuild
from verify_runtime import VerticalRayIndex


def build_with(quad):
    road={'id':'whitehorn-amethyst','stations':[[-20,3.,0],[0,10.,0]],
          'length':20.,'maximumGrade':.35,'portal':'north-pass'}
    other={'id':'amethyst-sunmane','stations':[[0,12,0],[1,12,0]]}
    return SimpleNamespace(geography_roads=[road,other],terrain_meshes={
        'Walk_ContinentRoad_whitehorn-amethyst_StreamCell_north':quad})


def test_later_profile_uses_actual_raised_road_not_original_low_stations():
    quad=M.quad([[-20,8.03,-3.5],[0,10.03,-3.5],[0,10.03,3.5],[-20,8.03,3.5]])
    b=build_with(quad);before=b.geography_roads[1].copy()
    audit=R.refresh(b,'amethyst_barrens');p=np.array(b.geography_roads[0]['stations'])
    assert len(p)==21
    np.testing.assert_allclose(p[:,1],8+(p[:,0]+20)*.1,atol=1e-8)
    assert b.geography_roads[0]['length']==20 and b.geography_roads[0]['maximumGrade']==.35
    assert b.geography_roads[1]==before
    assert audit[0]['maximumBedChange']==pytest.approx(5)


def test_visible_half_cell_cut_uses_surveyed_endpoint_but_inland_gap_fails():
    quad=M.quad([[-20,8.03,-3.5],[-.5,10.03,-3.5],[-.5,10.03,3.5],[-20,8.03,3.5]])
    b=build_with(quad);audit=R.refresh(b,'amethyst_barrens')
    assert audit[0]['thresholdTailSamples']==[20]
    assert b.geography_roads[0]['stations'][-1]==[0,10,0]
    bad=M.quad([[-18,8.03,-3.5],[0,10.03,-3.5],[0,10.03,3.5],[-18,8.03,3.5]])
    with pytest.raises(ValueError,match='inland station'):R.refresh(build_with(bad),'amethyst_barrens')


def test_near_identical_original_knots_do_not_create_zero_length_grade_samples():
    points,distance=R._stations([[0,0,0],[1+1e-12,1,0],[4,2,0]])
    assert np.diff(distance).min()>.99
    assert len(points)==5


def test_repair_real_seven_lane_road_but_keep_native_walk_and_surveyed_contour(monkeypatch):
    from verify_runtime import VerticalRayIndex
    xs=np.arange(-20.,1.)
    ys=np.minimum(np.maximum((xs+14)*1.2,0.),4.)+6.
    parts=[M.quad([[a,ya+.03,-3.5],[b,yb+.03,-3.5],
                   [b,yb+.03,3.5],[a,ya+.03,3.5]])
           for a,b,ya,yb in zip(xs[:-1],xs[1:],ys[:-1],ys[1:])]
    mesh=M.merge(parts);b=build_with(mesh)
    native=M.quad([[-20,4,-3],[0,4,-3],[0,4,3],[-20,4,3]])
    b.terrain_meshes['Walk_NativeEntry']=native
    before_native=native.positions.copy();before_road=mesh.positions.copy()
    monkeypatch.setattr(R,'_protected_distance',lambda build,region,xz:np.maximum(-xz[:,0],0.))
    monkeypatch.setattr(R,'_edge_distance',lambda build,region,xz:np.maximum(-xz[:,0],0.))
    audit=R.refresh(b,'amethyst_barrens')
    assert audit[0]['maximumUncorrectedGrade']>1
    assert audit[0]['maximumActualGrade']<=.380001
    np.testing.assert_array_equal(native.positions,before_native)
    for p in before_road[before_road[:,0]>=-3]:
        assert np.any(np.all(mesh.positions==p,axis=1))
    ray=VerticalRayIndex(mesh.positions[mesh.indices.reshape(-1,3)])
    for lane in range(-3,4):
        levels=[ray.top_hit(float(x),float(lane)) for x in np.arange(-20,0.01,.25)]
        assert all(y is not None for y in levels)
        assert np.max(np.abs(np.diff(levels))/.25)<=.380001


def test_infeasible_protected_profile_is_rejected_instead_of_moving_entry():
    with pytest.raises(ValueError,match='longer approach'):
        R._limit_profile(np.arange(4.),np.array([0.,0.,3.,3.]),np.array([True,False,False,True]))


def test_single_corridor_fills_outer_bend_without_duplicate_surface():
    from verify_runtime import VerticalRayIndex
    mesh=M.merge([M.quad([[-12,4.03,-3.5],[0,4.03,-3.5],[0,4.03,3.5],[-12,4.03,3.5]]),
                  M.quad([[-3.5,4.03,0],[3.5,4.03,0],[3.5,4.03,12],[-3.5,4.03,12]])])
    b=build_with(mesh);b.geography_roads[0]['stations']=[[-12,4,0],[0,4,0],[0,4,12]]
    R.refresh(b,'amethyst_barrens');tri=mesh.positions[mesh.indices.reshape(-1,3)]
    ray=VerticalRayIndex(tri)
    # Former independent quads leave this outside corner completely empty.
    assert ray.top_hit(2.,-2.)==pytest.approx(4.03)
    for x,z in ((2.,-2.),(0.,0.),(-5.,0.),(0.,5.)):
        assert ray.top_hit(x,z)==pytest.approx(4.03)
    area=np.abs(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]).sum()/2
    assert 195<area<260  # A union, not both overlapping original rectangles.


def test_grotto_bridge_has_literal_soffit_and_grounded_clear_width_abutments():
    from regionbuild import RegionBuild
    b=RegionBuild(None)
    b.terrain_meshes['Terrain_Test']=M.quad([[-120,1,-245],[-40,1,-245],[-40,1,-210],[-120,1,-210]])
    b.terrain_meshes['Walk_ContinentRoad_mirrorhold-amethyst']=M.quad([[-110,24.08,-231],[-50,24.08,-231],[-50,24.08,-222],[-110,24.08,-222]])
    original=b.terrain_meshes['Terrain_Test'].positions.copy()
    R.add_supports(b,'amethyst_barrens')
    np.testing.assert_array_equal(b.terrain_meshes['Terrain_Test'].positions,original)
    arches=[p for p in b.placements if p.kind=='bridge'];feet=[p for p in b.placements if p.collides]
    assert len(arches)==1 and len(feet)==4
    lo,hi=b.meshes[arches[0].mesh].bounds()
    assert hi[1]<24.08 and hi[1]>23.9 and lo[1]<2
    for p in feet:
        low,high=b.meshes[p.mesh].bounds();low+=p.position;high+=p.position
        assert low[1]==pytest.approx(.95)
        assert abs(p.position[2]+226.5)-.55>=3.8


def test_replaced_partition_names_keep_each_border_membership():
    a=M.quad([[-20,8.03,-3.5],[-10,9.03,-3.5],[-10,9.03,3.5],[-20,8.03,3.5]])
    z=M.quad([[-10,9.03,-3.5],[0,10.03,-3.5],[0,10.03,3.5],[-10,9.03,3.5]])
    b=build_with(a);first=next(iter(b.terrain_meshes));second='Walk_ContinentRoad_whitehorn-amethyst_StreamCell_east'
    b.terrain_meshes[second]=z;b.streaming_borders=[{'sceneNodes':[first]},{'sceneNodes':[second]}]
    R.refresh(b,'amethyst_barrens')
    assert second not in b.terrain_meshes
    assert all(spec['sceneNodes']==[first] for spec in b.streaming_borders)


def test_grotto_fold_support_and_existing_discovery_floor_are_disjoint():
    from verify_runtime import VerticalRayIndex
    mesh=M.quad([[-105,24.08,-230],[-60,24.08,-230],[-60,24.08,-223],[-105,24.08,-223]])
    b=SimpleNamespace(geography_roads=[{'id':'mirrorhold-amethyst','stations':[[-105,24.05,-226.5],[-60,24.05,-226.5]],'length':45.}],
        terrain_meshes={'Walk_ContinentRoad_mirrorhold-amethyst':mesh})
    R.refresh(b,'amethyst_barrens');ray=VerticalRayIndex(mesh.positions[mesh.indices.reshape(-1,3)])
    assert ray.top_hit(-81.5,-222.75)==pytest.approx(24.08) # outer lane + .75m fold
    assert ray.top_hit(-81.5,-222.5) is None # real existing standing tile
    assert ray.top_hit(-81.5432,-222.3607) is None # native discovery root


def test_grade_budget_follows_connected_detour_without_crossing_empty_centre():
    columns=11;mask=np.zeros((11,11),bool)
    mask[:,0]=True;mask[-1,:]=True;mask[:,-1]=True
    raw=np.zeros((11,11));raw[:,10]=3.
    pins=np.zeros((11,11),bool);pins[0,0]=pins[0,10]=True
    fixed=R._grid_grade(raw.ravel(),mask.ravel(),pins.ravel(),columns).reshape(11,11)
    assert fixed[0,0]==0 and fixed[0,10]==3
    assert np.abs(np.diff(fixed[:,0])).max()<=.175001
    assert np.abs(np.diff(fixed[-1,:])).max()<=.175001
    assert np.abs(np.diff(fixed[:,10])).max()<=.175001


def test_actual_triangle_seating_preserves_native_footing_and_walk():
    from regionbuild import RegionBuild,Placement
    from verify_runtime import VerticalRayIndex
    gx,gz=np.meshgrid(np.arange(-6.,7.),np.arange(-6.,7.))
    terrain=SimpleNamespace(gx=gx,gz=gz,height=np.full(gx.shape,2.))
    b=RegionBuild(terrain);b.geography_protected_disks=[]
    b.geography_roads=[{'id':'whitehorn-amethyst','stations':[[-6,5,0],[6,5,0]]}]
    parts=[M.quad([[x,2,z],[x+1,2,z],[x+1,2,z+1],[x,2,z+1]]) for x in range(-6,6) for z in range(-6,6)]
    b.terrain_meshes['Terrain_Test']=M.merge(parts)
    b.terrain_meshes['Walk_ContinentRoad_whitehorn-amethyst']=M.quad([[-6,5.03,-4.25],[6,5.03,-4.25],[6,5.03,4.25],[-6,5.03,4.25]])
    native=M.quad([[-1,3,3],[1,3,3],[1,3,5],[-1,3,5]])
    b.terrain_meshes['Walk_NativeEntry']=native;before=native.positions.copy()
    b.add_mesh('Building',M.box((2,2,2)));b.place(Placement('Native_Building','Building',(0,3,4),collides=True,kind='building'))
    R.seat_ground(b,'whitehorn_range')
    mesh=b.terrain_meshes['Terrain_Test'];ray=VerticalRayIndex(mesh.positions[mesh.indices.reshape(-1,3)])
    assert ray.top_hit(0,0)==pytest.approx(5.)
    assert ray.top_hit(0,4)==pytest.approx(2.)
    np.testing.assert_array_equal(native.positions,before)


def test_coarse_footing_triangle_does_not_extend_into_public_lane():
    from regionbuild import RegionBuild,Placement
    from verify_runtime import VerticalRayIndex
    gx,gz=np.meshgrid(np.arange(-8.,9.),np.arange(-8.,9.))
    b=RegionBuild(SimpleNamespace(gx=gx,gz=gz,height=np.full(gx.shape,12.)))
    b.geography_protected_disks=[]
    b.geography_roads=[{'id':'mirrorhold-amethyst','stations':[[-8,5,0],[8,5,0]]}]
    b.terrain_meshes['Terrain_Coarse']=M.quad([[-8,12,-8],[8,12,-8],[8,12,8],[-8,12,8]])
    b.terrain_meshes['Walk_ContinentRoad_mirrorhold-amethyst']=M.quad([[-8,5.03,-4.25],[8,5.03,-4.25],[8,5.03,4.25],[-8,5.03,4.25]])
    b.add_mesh('Slab',M.box((3,1,3)))
    b.place(Placement('Secret_Slab','Slab',(0,12.5,6),collides=True,kind='monument'))
    R.seat_ground(b,'mirrorhold')
    terrain=b.terrain_meshes['Terrain_Coarse'];ray=VerticalRayIndex(terrain.positions[terrain.indices.reshape(-1,3)])
    assert ray.top_hit(0,3)==pytest.approx(5.,abs=.001)
    assert ray.top_hit(0,6)==pytest.approx(12.)


def test_face_solver_limits_diagonal_saddles_not_only_grid_edges():
    columns=9;z,x=np.mgrid[:9,:9]
    values=(.6*np.sin(x*.8)*np.cos(z*.6)).ravel()
    allowed=np.ones(len(values),bool);pins=((x==0)|(x==8)|(z==0)|(z==8)).ravel()
    values[pins]=0.
    result=R._grid_grade(values,allowed,pins,columns).reshape(9,9)
    np.testing.assert_array_equal(result.ravel()[pins],values[pins])
    # Each of the two actual triangles has a different perpendicular pair.
    dx0=(result[:-1,1:]-result[:-1,:-1])/.5
    dz0=(result[1:,1:]-result[:-1,1:])/.5
    dz1=(result[1:,:-1]-result[:-1,:-1])/.5
    dx1=(result[1:,1:]-result[1:,:-1])/.5
    assert np.sqrt(dx0*dx0+dz0*dz0).max()<=.380001
    assert np.sqrt(dx1*dx1+dz1*dz1).max()<=.380001


def test_unequal_adjacent_triangles_stay_watertight_after_seating():
    gx,gz=np.meshgrid(np.arange(-8,9.),np.arange(-8,10.))
    b=RegionBuild(SimpleNamespace(gx=gx,gz=gz,height=gx*0+12));b.geography_protected_disks=[]
    b.geography_roads=[{'id':'whitehorn-amethyst','stations':[[-8,5,0],[8,5,0]]}]
    points=np.array([[0,12,6.2],[0,12,6.8],[-3,12,6.5],[.2,12,6.5]])
    mesh=M.Mesh(positions=points,normals=np.tile([0,1.,0],(4,1)),uvs=points[:,[0,2]],indices=np.array([0,1,2,1,0,3]))
    b.terrain_meshes['Terrain_Test']=mesh
    b.terrain_meshes['Walk_ContinentRoad_whitehorn-amethyst']=M.quad([[-8,5.03,-4.25],[-8,5.03,4.25],[8,5.03,4.25],[8,5.03,-4.25]])
    R.seat_ground(b,'whitehorn_range')
    ray=VerticalRayIndex(mesh.positions[mesh.indices.reshape(-1,3)])
    # Old red-face refinement yields 5.569240 vs 5.615647: a 4.64cm crack.
    assert abs(ray.top_hit(-1e-6,6.5)-ray.top_hit(1e-6,6.5))<1e-5


def test_all_fixed_faces_must_obey_actual_gradient_budget():
    # Each graph edge obeys the retained .25m/half-cell rule, but the actual
    # non-retained face has gradient hypot(.35,.35)=.49497, above .38.
    with pytest.raises(ValueError):
        R._grid_grade(np.array([0.,.175,.175,.35]),np.ones(4,bool),np.ones(4,bool),2,
            retained=np.ones(4,bool),face_retained=np.zeros(4,bool))


def test_infeasible_fixed_rows_are_not_discarded_when_other_vertices_are_free():
    values=np.array([0.,.175,0.,.175,.35,0.,0.,0.,0.])
    allowed=np.zeros(9,bool);allowed[[0,1,3,4,8]]=True
    pins=allowed.copy();pins[8]=False
    with pytest.raises(ValueError):
        R._grid_grade(values,allowed,pins,3,retained=pins,face_retained=np.zeros(9,bool))


def test_separate_material_streamcells_share_the_same_shaped_edge():
    gx,gz=np.meshgrid(np.arange(-8,9.),np.arange(-8,10.))
    b=RegionBuild(SimpleNamespace(gx=gx,gz=gz,height=gx*0+12));b.geography_protected_disks=[]
    b.geography_roads=[{'id':'whitehorn-amethyst','stations':[[-8,5,0],[8,5,0]]}]
    a=[0,12,6.2];z=[0,12,6.8]
    meshes=[]
    for label,points,material in [('left',[a,z,[-3,12,6.5]],'alpine_bedrock_ground'),('right',[z,a,[.2,12,6.5]],'alpine_turf_ground')]:
        points=np.array(points)
        mesh=M.Mesh(positions=points,normals=np.tile([0,1.,0],(3,1)),uvs=points[:,[0,2]],indices=np.arange(3),material=material)
        b.terrain_meshes['Terrain_Test_StreamCell_'+label]=mesh;meshes.append(mesh)
    b.terrain_meshes['Walk_ContinentRoad_whitehorn-amethyst']=M.quad([[-8,5.03,-4.25],[-8,5.03,4.25],[8,5.03,4.25],[8,5.03,-4.25]])
    R.seat_ground(b,'whitehorn_range')
    left,right=[VerticalRayIndex(m.positions[m.indices.reshape(-1,3)]) for m in meshes]
    for z in np.linspace(6.22,6.78,15):
        assert abs(left.top_hit(-1e-7,float(z))-right.top_hit(1e-7,float(z)))<1e-5


def test_grotto_front_cut_does_not_remove_separate_inland_approach():
    segments=[M.quad([[-105,24.08,-230],[-60,24.08,-230],[-60,24.08,-223],[-105,24.08,-223]]),
        M.quad([[-63.5,24.08,-226.5],[-56.5,24.08,-226.5],[-56.5,24.08,-200],[-63.5,24.08,-200]]),
        M.quad([[-105,24.08,-203.5],[-60,24.08,-203.5],[-60,24.08,-196.5],[-105,24.08,-196.5]])]
    mesh=M.merge(segments)
    b=SimpleNamespace(geography_roads=[{'id':'mirrorhold-amethyst','stations':[[-105,24.05,-226.5],[-60,24.05,-226.5],[-60,24.05,-200],[-105,24.05,-200]]}],terrain_meshes={'Walk_ContinentRoad_mirrorhold-amethyst':mesh})
    R.refresh(b,'amethyst_barrens');ray=VerticalRayIndex(mesh.positions[mesh.indices.reshape(-1,3)])
    assert ray.top_hit(-81.5,-222.5) is None
    assert ray.top_hit(-81.5,-200)==pytest.approx(24.08)
