"""Actual hull contact, complete water coverage, and decorative-only scope."""
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manymouth_boats as B
from world_layout import World


def world(height=0.):
    obj=World.__new__(World);obj.x0=obj.z0=-6.;obj.cell=2.
    obj.x=obj.z=np.arange(-6.,8.,2.);obj.gx,obj.gz=np.meshgrid(obj.x,obj.z)
    obj.height=np.full(obj.gx.shape,float(height))
    return obj


def rectangle(x0,x1,z0,z1,y):
    a,b,c,d=np.array([[x0,y,z0],[x1,y,z0],[x0,y,z1],[x1,y,z1]],float)
    return np.array([[a,c,b],[b,c,d]])


def test_actual_bank_peak_between_hull_vertices_cannot_bury_boat():
    w=world();w.height[3,3]=1.8
    hull=rectangle(-3.8,3.8,-1.1,1.1,-.6)
    assert np.max(w.height_at(hull[:,:,0],hull[:,:,2]))<.2
    shift,report=B.settle_hull(w,hull,np.empty((0,3,3)))
    assert shift==pytest.approx(2.415)
    assert report['minimumGroundClearance']==pytest.approx(.015)
    assert report['mode']=='hauled-up'
    assert report['terrainIntersectionVertices']>len(np.unique(hull.reshape(-1,3),axis=0))


def test_deep_water_preserves_authored_flotation_line_and_exact_xz():
    w=world(-2.)
    hull=rectangle(-3.2,3.2,-.6,.6,-.6)
    original=hull.copy()
    shift,report=B.settle_hull(w,hull,rectangle(-5,5,-5,5,4.))
    assert shift==4. and report['mode']=='afloat'
    assert report['footprintWaterCoverage']==pytest.approx(1)
    np.testing.assert_array_equal(hull,original)


def test_complete_footprint_rejects_dry_hole_between_wet_hull_corners():
    hull=rectangle(-3,3,-1,1,-.6)
    # Four strips surround a .2m-wide dry ridge through the centre. Every
    # original hull vertex is wet, but its full footprint is not navigable water.
    water=np.concatenate([rectangle(-5,-.1,-5,5,0),rectangle(.1,5,-5,5,0),
        rectangle(-.1,.1,-5,-.1,0),rectangle(-.1,.1,.1,5,0)])
    coverage,_,_=B.water_coverage(hull,water)
    assert coverage==pytest.approx(1-.04/12)
    shift,report=B.settle_hull(world(-2),hull,water)
    assert report['mode']=='hauled-up'
    assert shift==pytest.approx(-1.385)


def test_shallow_or_conflicting_water_levels_ground_hull_without_burial():
    hull=rectangle(-3,3,-1,1,-.6)
    for w,water in ((world(-.65),rectangle(-5,5,-5,5,0)),
        (world(-2),np.concatenate([rectangle(-5,0,-5,5,0),rectangle(0,5,-5,5,1)]))):
        _,report=B.settle_hull(w,hull,water)
        assert report['mode']=='hauled-up'
        assert report['minimumGroundClearance']==pytest.approx(.015)


def test_ferry_and_assembly_boats_are_not_selected():
    w=SimpleNamespace()
    content=SimpleNamespace(objects=[{'region':B.REGION,'node':'FerryBoat_manymouth'},
        {'region':B.REGION,'node':'moored_boat_000','assembly':'working-harbour'},
        {'region':B.REGION,'node':'moored_boat_001','collides':True},
        {'region':B.REGION,'node':'moored_boat_002','walk':True},
        {'region':'westhaven','node':'moored_boat_003'}])
    assert B.apply_manymouth_boats(w,content)['boats']==[]


def test_semantic_gameplay_links_fail_closed_before_mesh_or_terrain_access():
    boat={'region':B.REGION,'node':'moored_boat_003','names':{'moored_boat_003'}}
    content=SimpleNamespace(objects=[boat],templates={B.REGION:{'portals':[{'node':boat['node']} ]}})
    with pytest.raises(ValueError,match='gameplay-linked'):
        B.apply_manymouth_boats(SimpleNamespace(),content)
    assert not B._gameplay_linked({'streamingBorders':[{'sceneNodes':[boat['node']]}]},boat['names'])


def test_actual_mesh_hook_preserves_source_and_mappings_and_is_idempotent(tmp_path):
    import copy
    import landscape as L
    from amberwood import mesh as M,gltf as G
    builder=G.GltfBuilder('retained boat fixture')
    builder.add_material(G.Material('wood'))
    builder.add_mesh('hull',M.box((6.,.6,1.2),center=(0.,-.3,0.),material='wood'))
    index=builder.add_node(G.Node('moored_boat_000',mesh='hull'))
    path=tmp_path/'source.glb';builder.write_glb(str(path))
    doc,body=B.S.GR.load(path);original=path.read_bytes();original_doc=copy.deepcopy(doc)
    low,high=B.S.subtree_bounds(doc,body,index)
    shift=np.array([.3,8.,.1]);key=(B.REGION,'moored_boat_000')
    obj={'region':B.REGION,'node':key[1],'index':index,'indices':[index],
        'names':{key[1]},'shift':shift,'low':low+shift,'high':high+shift}
    w=world();w.plan={'sea_level':0.,'rivers':[],'lakes':[]}
    w.water=L.water_fields(w.gx,w.gz,height=w.height,plan=w.plan)
    content=SimpleNamespace(objects=[obj],templates={B.REGION:{}},documents={B.REGION:(doc,body)},
        mapping={key:shift},bounds_by_name={key:(obj['low'],obj['high'])})
    first=B.apply_manymouth_boats(w,content)
    assert first['hauledUp']==1 and first['boats'][0]['deltaY']< -7.
    final=obj['shift'].copy();second=B.apply_manymouth_boats(w,content)
    assert second['boats'][0]['deltaY']==0
    np.testing.assert_array_equal(obj['shift'],final)
    np.testing.assert_array_equal(obj['shift'][[0,2]],[.3,.1])
    np.testing.assert_array_equal(content.mapping[key],obj['shift'])
    np.testing.assert_array_equal(content.bounds_by_name[key][0],obj['low'])
    assert doc==original_doc and path.read_bytes()==original
    np.testing.assert_array_equal(w.height,np.zeros_like(w.height))
