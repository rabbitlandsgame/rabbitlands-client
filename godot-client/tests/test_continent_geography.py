"""Actual ownership, actor coordinates, protected structures and road geometry."""
from pathlib import Path
import json
import sys
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                     'eloria-assets/maps/nymara-regions/_toolkit'))
import continent_geography as G
from amberwood import mesh as M
from amberwood.terrain import Terrain
from regionbuild import RegionBuild, Placement
from verify_runtime import VerticalRayIndex


@pytest.fixture(autouse=True)
def legacy_coordinate_recipe(monkeypatch):
    """Exercise the retained algorithms against their immutable authored world.

    Current exported geography is independently audited by audit_continent and
    test_stream_cell_packages. These regressions deliberately cover the older
    border synthesis, its 17 crossings and its protected native destinations.
    """
    path = Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions/_continent/legacy-geography.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    monkeypatch.setattr(G, 'plan', lambda: data)


def area(mesh):
    faces = mesh.positions[mesh.indices.reshape(-1,3)]
    return np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1).sum()/2


def square():
    result = M.quad([(0,2,0),(10,2,0),(10,2,10),(0,2,10)], material='test')
    result.uvs = result.positions[:,[0,2]]/10
    result.colors = np.c_[result.uvs, np.full((4,2),.7)]
    return result


def test_concave_ownership_clips_actual_triangles_without_centroid_loss():
    polygon = [[0,0],[10,0],[10,4],[4,4],[4,10],[0,10]]
    a = G.clip_owned_mesh(square(),G.polygon_rectangles(polygon))
    b = G.clip_owned_mesh(square(),np.array([[4,4,10,10]]))
    assert area(a) == pytest.approx(64)
    assert area(b) == pytest.approx(36)
    assert area(a)+area(b) == pytest.approx(100)
    for mesh in (a,b):
        assert np.allclose(mesh.uvs,mesh.positions[:,[0,2]]/10)
        assert np.allclose(mesh.colors[:,:2],mesh.uvs)
        assert np.allclose(mesh.colors[:,2:],.7)
        assert mesh.material == 'test'


def test_native_core_triangle_arrays_remain_unchanged():
    source = square()
    clipped = G.clip_owned_mesh(source,np.array([[-5,-5,15,15]]),[[0,0],[10,10]])
    for name in ('positions','normals','uvs','colors','indices'):
        assert np.array_equal(getattr(source,name),getattr(clipped,name))


def test_all_twelve_native_cores_and_protected_destinations_are_owned():
    regions = G.plan()['regions']
    assert len(regions)==12
    count = 0
    for name,record in regions.items():
        polygon = record['ownershipPolygon']
        lo,hi = np.array(record['coreBounds'])
        points = [[x,z] for x in np.linspace(lo[0],hi[0],19) for z in np.linspace(lo[1],hi[1],19)]
        assert G.inside_polygon(points,polygon).all(),name
        t = np.array(record['translation'])[[0,2]]
        for entry in record['protectedDestinations']:
            assert G.inside_polygon([np.array(entry['position'])[[0,2]]+t],polygon)[0],(name,entry['id'])
            count+=1
    assert count == 1027


def test_native_grid_origins_are_immutable_before_served_padding():
    expected={'whitehorn_range':(120,120),'amberwood':(116,116),
        'mirrorhold':(120,96),'amethyst_barrens':(116,116),
        'grey_moors':(116,116),'westhaven':(120,172),'crownwater':(120,120),
        'four_gates':(198,198),'sunmane_steppe':(116,116),
        'ssarathi_ruins':(116,116),'verdant_stair':(108,108),
        'manymouth_delta':(138,120)}
    for name,origin in expected.items():
        region=G.plan()['regions'][name]
        assert tuple(region['nativeServerOrigin'])==origin
        assert len(region['nativeManifestSha256'])==64
        assert region['nativeManifestSource'].endswith('/world.json')
        assert np.allclose(np.asarray(region['serverOrigin'])-origin,region['serverTileShift'])
    assert G.plan()['regions']['four_gates']['translation']==[1050,-19,1016]


def test_owned_polygons_have_no_overlapping_area():
    regions = list(G.plan()['regions'].items())
    for i,(name,record) in enumerate(regions):
        a = G.polygon_rectangles(record['ownershipPolygon'])
        for other,peer in regions[i+1:]:
            b = G.polygon_rectangles(peer['ownershipPolygon'])
            overlap = np.minimum(a[:,None,2:],b[None,:,2:])-np.maximum(a[:,None,:2],b[None,:,:2])
            assert not np.any((overlap>1e-8).all(axis=2)),(name,other)


def test_all_seventeen_crossings_preserve_exact_actor_coordinates_and_fit_grid():
    p = G.plan()
    assert len(p['connections'])==17
    for connection in p['connections']:
        positions=[]
        for end in connection['ends']:
            record = p['regions'][end['region']]
            translation=np.array(record['translation'])
            anchor=np.array(end['anchor']);n=np.array(end['outward']);side=np.array([-n[1],n[0]])
            assert np.allclose(anchor+translation,connection['globalAnchor'])
            assert np.allclose(np.mod(translation[[0,2]],1),0)
            assert record['serverCells'][0] == record['serverCells'][1]
            assert record['serverCells'][0]%6 == 0
            o=np.array(record['serverOrigin']);size=record['serverCells'][0]
            for depth in (-2,0,1,2):
                for lane in range(-3,4):
                    desired=anchor[[0,2]]+depth*n+lane*side
                    tile=np.floor([desired[0]+o[0],o[1]-desired[1]]).astype(int)
                    actual=np.array([tile[0]+.5-o[0],o[1]-tile[1]-.5])
                    assert np.allclose(actual,desired),(connection['id'],end['region'],depth,lane)
                    assert (tile>=0).all() and (tile<size).all()
            positions.append(n)
        assert np.allclose(positions[0],-positions[1])


def test_full_collar_reserves_every_lane_and_its_folded_collision_width():
    p=G.plan()
    depth,lateral=np.meshgrid(np.arange(-42.5,-.49,.25),np.arange(-3.5,3.51,.25))
    for connection in p['connections']:
        anchor=np.asarray(connection['globalAnchor'])[[0,2]]
        for end in connection['ends']:
            out=np.asarray(end['outward']);side=np.array([-out[1],out[0]])
            points=anchor+depth.ravel()[:,None]*out+lateral.ravel()[:,None]*side
            assert G.inside_polygon(points,p['regions'][end['region']]['ownershipPolygon']).all(),(connection['id'],end['region'])


def test_exact_conservative_fold_uses_owned_geometry_or_emitted_threshold():
    import streaming_borders as SB
    p=G.plan();caps={}
    offsets=[(x,z) for x in(-.5,0.,.5) for z in(-.5,0.,.5)]
    offsets+=[(x,z) for x in(-.75,-.25) for z in(.25,.75)]
    for region in p['regions']:
        build=RegionBuild(Terrain(0,0,2,2))
        for spec in G.region_specs(region):SB._owned_threshold(build,spec)
        translation=np.asarray(p['regions'][region]['translation'])
        triangles=np.concatenate([m.positions[m.indices.reshape(-1,3)]+translation
                                  for m in build.terrain_meshes.values()])
        caps[region]=VerticalRayIndex(triangles)
    for connection in p['connections']:
        a=np.asarray(connection['globalAnchor'])[[0,2]]
        for end in connection['ends']:
            out=np.asarray(end['outward']);side=np.array([-out[1],out[0]])
            points=np.asarray([a+out*depth+side*lane+offset
                for depth in range(-42,0) for lane in range(-3,4) for offset in offsets])
            owned=G.inside_polygon(points,p['regions'][end['region']]['ownershipPolygon'])
            assert all(caps[end['region']].top_hit(*q) is not None for q in points[~owned]),(connection['id'],end['region'])


def test_public_road_routes_around_protected_structure_without_corner_cutting():
    terrain=Terrain(-30,-30,60,60,cell=2)
    path=G._road_path([-20,0],[20,0],[[-30,-30],[30,-30],[30,30],[-30,30]],[(0,0,5)],terrain)
    stations,_=G._sample_polyline(path,.2)
    assert np.min(np.linalg.norm(stations,axis=1))>=9
    assert np.allclose(path[0],[-20,0]) and np.allclose(path[-1],[20,0])


def test_road_profile_preserves_native_junction_and_practical_grade():
    terrain=Terrain(-10,-10,80,40,cell=1)
    terrain.height=8*np.sin(terrain.gx*.15)+2
    points,heights,distance=G._profile(terrain,np.array([[0,0],[20,5],[50,0]]),12)
    assert heights[0]==pytest.approx(terrain.height_at(0,0))
    assert heights[-1]==12
    assert np.max(abs(np.diff(heights))/np.diff(distance))<=.38000001


def test_unbuildable_short_ascent_fails_instead_of_teleport_grade():
    terrain=Terrain(0,0,20,20,cell=1)
    with pytest.raises(ValueError,match='author a longer approach'):
        G._profile(terrain,np.array([[1,1],[11,1]]),30)


def test_full_transformed_building_bound_is_protected(monkeypatch):
    build=RegionBuild(Terrain(0,0,40,40))
    build.meshes['hall']=M.box((20,8,6)).translate(4,0,0)
    build.placements=[Placement('hall','hall',(5,3,6),rotation_y=np.pi/2,scale=2,collides=True)]
    disks=G._structure_disks(build,'grey_moors')
    assert len(disks)==1
    x,z,radius=disks[0]
    assert (x,z)==pytest.approx((5,-2))
    assert radius==pytest.approx(np.hypot(20,6))


def test_extension_fills_real_missing_ground_with_no_native_overlap():
    terrain=Terrain(0,0,10,10,cell=1);terrain.height[:]=2
    build=RegionBuild(terrain)
    build.terrain_meshes['Terrain_native']=square()
    G._extend_ground(build,'test',np.array([[-4,-4],[14,-4],[14,14],[-4,14]]))
    extension=build.terrain_meshes['Terrain_ContinentExtension_test']
    assert area(extension)==pytest.approx(18*18-100)
    assert np.allclose(extension.positions[:,1],2)


def test_finalizer_preserves_authoritative_invisible_threshold(monkeypatch):
    p={'regions':{'test':{'translation':[0,0,0],'ownershipPolygon':[[0,0],[4,0],[4,10],[0,10]],
        'nativePlayableBounds':[[0,0],[4,10]]}}}
    monkeypatch.setattr(G,'plan',lambda:p)
    build=RegionBuild(Terrain(0,0,10,10))
    threshold=square()
    build.terrain_meshes={'Terrain_native':square(),'Walk_StreamThreshold_edge':threshold}
    build.streaming_borders=[{'sceneNodes':['Terrain_native','missing']}]
    G.finalize_geometry(build,'test')
    assert build.terrain_meshes['Walk_StreamThreshold_edge'] is threshold
    assert area(build.terrain_meshes['Terrain_native'])==pytest.approx(40)
    assert build.streaming_borders[0]['sceneNodes']==['Terrain_native']


def test_different_native_tessellations_share_exact_piecewise_boundary(monkeypatch):
    p={'regions':{'a':{'translation':[0,0,0]},'b':{'translation':[0,0,0]}},
       'boundaryHeightField':{'segments':[
           {'regions':['a','b'],'start':[5,0],'end':[5,4],'heights':[2,6]},
           {'regions':['a','b'],'start':[5,4],'end':[5,10],'heights':[6,3]}]}}
    monkeypatch.setattr(G,'plan',lambda:p)
    left=G.clip_owned_mesh(square(),np.array([[0,0,5,10]]))
    right=M.merge([M.quad([(5,20,0),(10,20,0),(10,20,3),(5,20,3)]),
                   M.quad([(5,20,3),(10,20,3),(10,20,10),(5,20,10)])])
    left=G._snap_boundary_mesh(left,'a');right=G._snap_boundary_mesh(right,'b')
    rays=[VerticalRayIndex(m.positions[m.indices.reshape(-1,3)]) for m in (left,right)]
    for z in np.linspace(.01,9.99,117):
        expected=np.interp(z,[0,4,10],[2,6,3])
        assert rays[0].top_hit(5,z)==pytest.approx(expected,abs=1e-8)
        assert rays[1].top_hit(5,z)==pytest.approx(expected,abs=1e-8)


def test_shared_height_field_has_immutable_source_hashes_and_consistent_vertices():
    field=G.plan()['boundaryHeightField']
    assert len(field['sources'])==12
    assert all(len(s['sha256'])==64 and s['sourceCheckout']=='wt-south-client'
               for s in field['sources'].values())
    vertices={}
    for segment in field['segments']:
        assert len(segment['regions'])==2
        for point,height in zip((segment['start'],segment['end']),segment['heights']):
            key=tuple(point)
            assert height==pytest.approx(vertices.setdefault(key,height),abs=1e-9)


def test_boundary_recipe_matches_real_owned_palette_and_is_order_independent():
    import streaming_borders as SB
    connections=G.plan()['connections']
    for connection in connections:
        anchor=np.array(connection['globalAnchor']);normal=np.array(connection['normal'])
        side=np.array([-normal[1],normal[0]])
        spec=dict(connection,geometryMode='continent-owned-v1')
        for lateral in (-109.,-35.,-3.,0.,3.,35.,109.):
            point=anchor[[0,2]]+side*lateral
            expected=(anchor[1]-6 if connection['profile']=='causeway' else
                anchor[1]+SB._shoulder_rise(spec)*(1-np.exp(-(lateral/30)**2)))
            assert G.boundary_road_recipe(point,-123,[connection])==pytest.approx(expected)
            forward=G.boundary_road_recipe(point,-123,connections)
            reverse=G.boundary_road_recipe(point,-123,list(reversed(connections)))
            assert forward==pytest.approx(reverse,abs=1e-10)
            if abs(lateral)<=3:
                assert forward==pytest.approx(expected,abs=1e-10),(connection['id'],lateral)


def test_all_seventeen_authored_boundary_throats_keep_their_own_terrain_recipe():
    import streaming_borders as SB
    for connection in G.plan()['connections']:
        anchor=np.array(connection['globalAnchor']);normal=np.array(connection['normal'])
        side=np.array([-normal[1],normal[0]])
        spec=dict(connection,geometryMode='continent-owned-v1')
        for end in connection['ends']:
            translation=np.array(G.plan()['regions'][end['region']]['translation'])
            for lane in range(-3,4):
                point=anchor[[0,2]]+side*lane
                distance,height=G.boundary_sample(end['region'],[point-translation[[0,2]]],maximum=2)
                # At the perpendicular road corner the nearest owned edge is
                # horizontal: its projected lateral position is half a metre
                # from this sample. Compare its own surveyed profile value.
                nearest=None;best=np.inf
                for segment in G.boundary_segments(end['region']):
                    a,b=np.asarray(segment['start']),np.asarray(segment['end']);vector=b-a
                    projected=a+np.clip((point-a)@vector/(vector@vector),0,1)*vector
                    d=np.linalg.norm(projected-point)
                    if d<best:best=d;nearest=projected
                across=float((nearest-anchor[[0,2]])@side)
                expected=(anchor[1]-6 if connection['profile']=='causeway' else
                    anchor[1]+SB._shoulder_rise(spec)*(1-np.exp(-(across/30)**2)))
                assert distance[0]<=1,(connection['id'],end['region'],lane,distance)
                assert height[0]==pytest.approx(expected,abs=1e-7),(connection['id'],lane,height,expected)


def test_boundary_start_midway_on_cut_edge_inserts_the_t_junction(monkeypatch):
    p={'regions':{'test':{'translation':[0,0,0]}},'boundaryHeightField':{'segments':[
       {'regions':['test','peer'],'start':[3,4],'end':[4,4],'heights':[7,7]}]}}
    monkeypatch.setattr(G,'plan',lambda:p)
    mesh=M.quad([(2,0,3),(4,0,3),(4,0,4),(2,0,4)])
    result=G._snap_boundary_mesh(mesh,'test')
    rays=VerticalRayIndex(result.positions[result.indices.reshape(-1,3)])
    for x in (3.01,3.25,3.5,3.99):
        assert rays.top_hit(x,4)==pytest.approx(7,abs=1e-8)
    assert rays.top_hit(2,4)==pytest.approx(0)


def test_scatter_follows_new_ground_and_preserves_offsets_and_linked_marker():
    t=Terrain(0,0,20,20);t.height[:]=2
    build=RegionBuild(t)
    tree=Placement('tree','tree',(4,2.4,4),kind='tree')
    building=Placement('hall','hall',(8,2,8),kind='building',collides=True)
    protected=Placement('old-tree','tree',(12,2.8,12),kind='tree')
    build.placements=[tree,building,protected]
    shared={'node':'tree','position':[4,2.9,4]}
    build.landmarks=[shared];build.interactives=[shared]
    build.geography_protected_disks=[(12,12,2)]
    def shape(points):
        result=points.copy();result[:,1]+=5;return result
    G._lift_unprotected_scatter(build,shape)
    assert tree.position==(4,7.4,4)
    assert building.position==(8,2,8)
    assert protected.position==(12,2.8,12)
    assert shared['position']==[4,7.9,4]
