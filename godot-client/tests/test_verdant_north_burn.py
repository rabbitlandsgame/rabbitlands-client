"""Physical drainage and built crossing checks, independent of full exports."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np

REG=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REG/'verdant_stair/source'),str(REG/'_toolkit'),str(REG/'_finishing')]
import build_verdant_stair
import north_burn as W
from amberwood import mesh as M


def test_water_surface_has_upward_faces_and_downhill_stations():
    assert np.all(np.diff(W.CONTROLS[:,1])<0)
    p=np.array([[0.,4.,0.],[10.,3.,0.],[14.,2.,4.]])
    d=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p[:,[0,2]],axis=0),axis=1))]
    m=W._ribbon(p,d);t=m.positions[m.indices.reshape(-1,3)]
    assert np.all(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])[:,1]>0)


def test_fully_clipped_water_has_no_stale_export_or_streaming_reference():
    kept = M.box((2., .1, 3.), material='water_stream')
    clipped = W.F.R._clip_scalar(kept, np.full(len(kept.positions), 1.))
    assert clipped.triangle_count == 0
    build = SimpleNamespace(water_meshes={'upper-fall':clipped, 'lower-pool':kept},
        streaming_borders=[{'sceneNodes':['upper-fall', 'lower-pool', 'unrelated-reference']}])
    assert W._discard_empty_water(build, ['upper-fall', 'lower-pool']) == ['upper-fall']
    assert list(build.water_meshes) == ['lower-pool']
    assert build.water_meshes['lower-pool'] is kept
    assert build.streaming_borders[0]['sceneNodes'] == ['lower-pool', 'unrelated-reference']


def test_channel_bed_seats_water_without_changing_distant_soil():
    curve=np.array([[0.,4.,0.],[10.,3.,0.]])
    points=np.array([[5.,8.,0.],[5.,1.,0.],[5.,8.,20.]])
    actual=W._cut(points,curve,np.array([0.,10.]))
    np.testing.assert_allclose(actual[:2,1],3.32)
    np.testing.assert_array_equal(actual[2],points[2])


def test_deep_receiving_banks_are_broad_and_culvert_banks_stay_bounded():
    curve=np.array([[-24.,33.,-250.],[-24.,32.,-210.]])
    p=np.array([[-16.,56.,-230.],[-4.,56.,-230.]])
    shaped=W._cut(p,curve,np.array([0.,40.]))
    assert 35.<shaped[0,1]<53.  # eight metres from centre still slopes to the bed
    np.testing.assert_array_equal(shaped[1],p[1])
    cross=np.array([[9.,33.5,-240.],[24.,34.3,-240.]])
    roadbank=np.array([[17.5,35.,-246.],[17.5,35.,-234.]])
    np.testing.assert_array_equal(W._cut(roadbank,cross,np.array([0.,15.])),roadbank)


def test_rock_is_a_replacement_substrate_with_exact_face_coverage():
    p=np.array([[0.,0.,0.],[0.,2.,1.],[1.,0.,0.],[1.,2.,1.],[2.,2.,1.]])
    faces=np.array([[0,1,2],[2,1,3],[3,1,4]])
    mesh=M.Mesh(positions=p,normals=np.zeros_like(p),uvs=p[:,[0,2]],indices=faces.ravel(),material='grass')
    b=SimpleNamespace(terrain_meshes={'Terrain_Grass':mesh},streaming_borders=[{'sceneNodes':['Terrain_Grass']}])
    before=p[faces].copy();old_y=p[:,1]+np.array([2.,0.,2.,0.,0.])
    assert W._rock_banks(b,{'Terrain_Grass':old_y})==2
    after=np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in b.terrain_meshes.values()])
    canonical=lambda a:sorted(tuple(row) for row in np.round(a.reshape(-1,9),10))
    assert canonical(after)==canonical(before)
    rock=b.terrain_meshes['Terrain_NorthBurn_RockBank_Terrain_Grass']
    assert rock.material=='verdant_wet_limestone'
    assert 'Terrain_NorthBurn_RockBank_Terrain_Grass' in b.streaming_borders[0]['sceneNodes']
    t=rock.positions[rock.indices.reshape(-1,3)];uv=rock.uvs[rock.indices.reshape(-1,3)]
    normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])
    u,v=uv[:,1]-uv[:,0],uv[:,2]-uv[:,0]
    uv_area=abs(u[:,0]*v[:,1]-u[:,1]*v[:,0])
    np.testing.assert_allclose(uv_area,abs(normal).max(axis=1)*.26**2)


def test_collinear_station_reduction_preserves_projection():
    controls=np.array([[0.,4.,0.],[10.,3.,0.],[14.,2.,4.]])
    points,along=W.F.R._stations(controls,.1)
    q=np.array([[3.,2.],[9.,-1.],[11.,2.],[14.,5.]])
    expected=W.F.G._road_coordinates(q,points[:,[0,2]])
    d,s,_,_=W._coordinates(q,points,along)
    np.testing.assert_allclose(d,expected[0],atol=1e-12)
    np.testing.assert_allclose(s,expected[1]*along[-1],atol=1e-12)


def crossing_build():
    xs=np.arange(148.,175.01,.5);zs=np.arange(-188.25,-179.74,.5)
    x,z=np.meshgrid(xs,zs);p=np.c_[x.ravel(),np.full(x.size,58.),z.ravel()]
    a=np.arange(len(zs)-1)[:,None]*len(xs)+np.arange(len(xs)-1)
    faces=np.stack([a,a+len(xs),a+len(xs)+1,a,a+len(xs)+1,a+1],axis=-1).reshape(-1,3)
    m=M.Mesh(positions=p,normals=np.tile([0.,1.,0.],(len(p),1)),uvs=p[:,[0,2]],indices=faces.ravel(),material='ashlar')
    water=M.box((5.,.01,30.),center=(159.5,57.795,-184.),material='water_stream')
    return SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_sunmane-verdant':m},water_meshes={'Water_Stream_EastBrook':water},
                           geography_roads=[{'id':'sunmane-verdant','stations':[[148.,57.97,-184.],[159.5,57.97,-184.],[175.,57.97,-184.]]}],
                           streaming_borders=[{'id':'sunmane-verdant','sceneNodes':[]}])


def test_stone_span_is_open_over_actual_water_and_joins_unchanged_endpoints():
    b=crossing_build();m=b.terrain_meshes['Walk_ContinentRoad_sunmane-verdant'];before=m.positions.copy()
    report=W._east_brook_crossing(b)
    assert report['minimumSoffitWaterClearance']>.3
    assert report['maximumActualFaceGrade']<.14
    ends=(before[:,0]<=149.)|(before[:,0]>=174.)
    np.testing.assert_array_equal(m.positions[ends],before[ends])
    structure=b.terrain_meshes['Structure_EastBrook_RoadSpan']
    tri=structure.positions[structure.indices.reshape(-1,3)]
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    # A construction mesh must not add another upward walking top.
    assert np.all(normal[:,1]<1e-8)
    side=abs(normal[:,1])<1e-8
    outward=tri.mean(axis=1)[:,[0,2]]-np.array([161.5,-184.])
    assert np.all(np.sum(normal[side][:,[0,2]]*outward[side],axis=1)>=-1e-8)


def test_north_culvert_has_open_flow_under_its_single_existing_road_top():
    m=W._culvert();tri=m.positions[m.indices.reshape(-1,3)]
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert not np.any(normal[:,1]>1e-8)
    below=W.F.VerticalRayIndex(tri).top_hit(17.5,-240.)
    assert abs(below-34.48)<1e-6
    assert below-33.75>.7
