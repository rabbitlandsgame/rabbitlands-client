from pathlib import Path
import copy
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import crown_support as C
import ferry_export as F


def test_named_shelf_masks_leave_open_channel_and_distant_continent_untouched():
    islands=[{'center':[0,0],'crownShelfRadii':[12,8],'angle':.4},
             {'center':[70,0],'crownShelfRadii':[9,13],'angle':-.2}]
    weights=C.island_influence(np.array([0,35,70,200]),np.zeros(4),islands)
    assert weights.tolist()==[1,0,1,0]
    assert 0<C.island_influence(np.array([19.]),np.array([0.]),islands)[0]<1


def source_bridge():
    positions=np.array([[0,4,-2],[0,4,2],[40,4,-2],[40,4,2]],dtype='<f4')
    normals=np.tile([0,1,0],(4,1)).astype('<f4')
    document={'buffers':[{'byteLength':positions.nbytes+normals.nbytes}],
        'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':positions.nbytes},
                       {'buffer':0,'byteOffset':positions.nbytes,'byteLength':normals.nbytes}],
        'accessors':[{'bufferView':i,'componentType':5126,'count':4,'type':'VEC3'} for i in range(2)],
        'nodes':[{'name':'Causeway_example','translation':[10,0,30],'children':[1]},
                 {'name':'Walk_Causeway_example','mesh':0},
                 {'name':'Unaffected_SharedGeometry','mesh':0}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1}}]}]}
    return document,positions.tobytes()+normals.tobytes()


def test_bridge_shear_preserves_original_buffers_names_and_shared_instances():
    document,body=source_bridge();before=copy.deepcopy(document)
    result,binary=C.reprofile_causeway(document,body,0,[[10,4,30],[50,4,30]],[6,10])
    assert document==before and binary[:len(body)]==body
    assert [n['name'] for n in result['nodes']]==[n['name'] for n in document['nodes']]
    assert result['nodes'][2]['mesh']==0 and result['nodes'][1]['mesh']!=0
    mesh=result['meshes'][result['nodes'][1]['mesh']]['primitives'][0]
    vertices=C.S.GR.accessor(result,binary,mesh['attributes']['POSITION'])
    original=C.S.GR.accessor(document,body,0)
    np.testing.assert_array_equal(vertices[:,[0,2]],original[:,[0,2]])
    np.testing.assert_allclose(vertices[:,1],[6,6,10,10])
    normals=C.S.GR.accessor(result,binary,mesh['attributes']['NORMAL'])
    np.testing.assert_allclose(np.linalg.norm(normals,axis=1),1,atol=1e-6)
    assert np.all(normals[:,0]<0) and np.all(normals[:,1]>.99)
    # Repeated construction serializes identical buffer bytes.
    again,again_body=C.reprofile_causeway(document,body,0,[[10,4,30],[50,4,30]],[6,10])
    assert again==result and again_body==binary


def test_bridge_reprofile_refuses_steep_new_deck():
    document,body=source_bridge()
    with pytest.raises(ValueError,match='comfortable bridge grade'):
        C.reprofile_causeway(document,body,0,[[10,4,30],[50,4,30]],[4,30])


def test_ferry_clearance_checks_full_grid_cells_not_just_nearest_vertex():
    class World:
        x=np.arange(0.,22.,2.);z=np.arange(0.,22.,2.)
        ferry_exclusion=np.zeros((11,11),bool)
    world=World();world.ferry_exclusion[5,5]=True
    assert not F.clear_of_retained_routes(world,[[9,9],[1,1]])
    assert F.clear_of_retained_routes(world,[[1,1],[18,18]])


def test_support_updates_settling_fields_only_inside_named_islands(tmp_path):
    x=np.arange(-40.,182.,2.);z=np.arange(-40.,82.,2.);gx,gz=np.meshgrid(x,z)
    islands=[{'center':[10,30] if i==0 else [50,30] if i==1 else [500+i*60,0],
              'crownSourceIsland':str(i),'crownShelfRadii':[15,15]} for i in range(17)]
    shape=gx.shape
    world=SimpleNamespace(ids=['crownwater'],plan={'islands':islands,'sea_level':0,'rivers':[],
        'lakes':[],'retained_transforms':{'crownwater':[0,0,0]}},gx=gx,gz=gz,
        original_height=np.full(shape,-8.),height=np.full(shape,-8.),
        foundation_weight=np.ones(shape),foundation_target=np.full(shape,99.),
        assembly_target=np.full(shape,99.),assembly_weight=np.ones(shape),road_target=np.full(shape,-8.))
    world.owner_at=lambda x,z:np.zeros(np.broadcast_shapes(np.shape(x),np.shape(z)),int)
    folder=tmp_path/'crownwater';folder.mkdir()
    source_height=np.full(shape,4.)
    np.savez(folder/'foundation-samples.npz',x=x,z=z,height=source_height)
    document,body=source_bridge()
    obj={'node':'Causeway_example','region':'crownwater','index':0,
         'low':np.array([10.,4.,28.]),'high':np.array([50.,4.,32.])}
    content=SimpleNamespace(library=tmp_path,assembly_records={C.ASSEMBLY:{'translation':[0,0,0]}},
        metadata={'crownwater':{'crossings':[{'id':'reach_example','endpoints':[[10,4,30],[50,4,30]]}]}},
        objects=[obj],documents={'crownwater':(document,body)},bounds_by_name={})
    report=C.apply_crown_support(world,content)
    near=(np.abs(gx-10)<.1)&(np.abs(gz-30)<.1)
    far=(gx==160)&(gz==30)
    np.testing.assert_allclose(world.height[near],3.975)
    np.testing.assert_array_equal(world.original_height[near],world.assembly_target[near])
    assert world.assembly_weight[near].item()==1 and world.foundation_weight[near].item()==0
    assert world.original_height[far].item()==-8 and world.foundation_weight[far].item()==1
    assert world.ferry_exclusion[near].item() and not world.ferry_exclusion[far].item()
    assert report['islands']==17 and report['supportedVertices']>0


def test_saved_crownwater_keeps_scene_and_terrain_but_preserves_ferry_exclusion():
    x=np.arange(90.,130.,2.);z=np.arange(190.,230.,2.);gx,gz=np.meshgrid(x,z)
    height=np.full(gx.shape,3.25)
    original=np.full(gx.shape,7.5)
    document={'nodes':[{'name':'SavedCauseway'}]};body=b'saved-binary'
    world=SimpleNamespace(ids=['crownwater'],gx=gx,gz=gz,height=height,
        original_height=original,
        authoring_snapshots={'crownwater':SimpleNamespace(translation=np.array([100.,0.,200.]))})
    quay={'region':'crownwater','node':'Saved_Quay','low':np.array([116.,2.,216.]),
          'high':np.array([118.,4.,218.])}
    content=SimpleNamespace(metadata={'crownwater':{'crossings':[
        {'id':'saved-spoke','endpoints':[[0.,4.,0.],[10.,4.,0.]]}]}},
        objects=[quay],documents={'crownwater':(document,body)})
    before=height.copy();before_original=original.copy()
    report=C.apply_crown_support(world,content)
    np.testing.assert_array_equal(world.height,before)
    np.testing.assert_array_equal(world.original_height,before_original)
    assert content.documents['crownwater']==(document,body)
    assert world.ferry_exclusion[(gz==200.)&(gx==104.)].all()
    assert world.ferry_exclusion[(gz==216.)&(gx==118.)].all()
    assert not world.ferry_exclusion[(gz==228.)&(gx==90.)].any()
    assert report['savedCrossings']==1 and report['savedQuayAssets']==1


def test_saved_quay_exclusion_can_omit_only_its_exact_connection_source():
    x=np.arange(0.,22.,2.);z=np.arange(0.,22.,2.);gx,gz=np.meshgrid(x,z)
    connection='crownwater--westhaven'
    control={'id':'owned','matrix':np.eye(4).reshape(-1,order='F').tolist(),
             'metadata':{'authoredFerryQuay':{'connectionIds':[connection],
                 'walkNode':'Walk_FerryQuay_owned','localLanding':[0.,0.,0.]}}}
    snapshot=SimpleNamespace(translation=np.zeros(3),document={
        'regionId':'crownwater','authority':{'ownedFerryConnectionIds':[connection]},
        'replacements':{'ferryConnectionIds':[connection]},'objects':[control]})
    world=SimpleNamespace(ids=['crownwater'],gx=gx,gz=gz,height=np.ones_like(gx),
        original_height=np.ones_like(gx),ferry_exclusion=np.zeros_like(gx,bool),
        authoring_snapshots={'crownwater':snapshot})
    owned={'region':'crownwater','node':'Walk_FerryQuay_owned','low':np.array([8.,0.,8.]),
           'high':np.array([10.,2.,10.]),'source':{'authoredFerryQuay':{
               'connectionIds':[connection]}}}
    unrelated={'region':'crownwater','node':'Working_Quay_unrelated','low':np.array([12.,0.,8.]),
               'high':np.array([14.,2.,10.]),'source':{}}
    content=SimpleNamespace(metadata={'crownwater':{'crossings':[]}},objects=[owned,unrelated])
    C.apply_crown_support(world,content)
    F.install_saved_ferry_exclusions(world,content)
    complete=F.ferry_exclusion(world)
    without_own=F.ferry_exclusion(world,[connection],ignore_region='crownwater')
    opposing_side=F.ferry_exclusion(world,[connection],ignore_region='westhaven')
    owned_only=(gx==2.)&(gz==2.)
    overlap=(gx==8.)&(gz==8.)
    unrelated_only=(gx==20.)&(gz==8.)
    assert complete[owned_only].all() and not without_own[owned_only].any()
    assert without_own[overlap].all() and without_own[unrelated_only].all()
    np.testing.assert_array_equal(opposing_side,complete)
    np.testing.assert_array_equal(world.height,np.ones_like(gx))


def test_self_exclusion_refuses_unattributed_union_mutation():
    world=SimpleNamespace(ferry_exclusion=np.zeros((3,3),bool),
        ferry_exclusion_base=np.zeros((3,3),bool),
        ferry_exclusion_by_owner={('crownwater','a--b'):np.zeros((3,3),bool)})
    world.ferry_exclusion[1,1]=True
    with pytest.raises(ValueError,match='attribution is stale'):
        F.ferry_exclusion(world,['a--b'],ignore_region='crownwater')
