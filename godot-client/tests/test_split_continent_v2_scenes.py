"""Conservation, failure modes and exact curve/ground preservation for the split."""
from pathlib import Path
import copy
import json
import re
import sys
import numpy as np
import pytest
from shapely.geometry import Polygon,Point
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import split_continent_v2_scenes as S
import freeze_continent_v2_terrain as F
import continent_v2_territories as T

class Region:
    def __init__(self,name,ring):self.id=name;self.shape=Polygon(ring)

def test_cubic_crossing_retains_full_curve_handles_height_width_and_tilt():
    left=Region('left',[[-10,-10],[0,-10],[0,10],[-10,10]])
    right=Region('right',[[0,-10],[10,-10],[10,10],[0,10]])
    data=np.array([[[0,0,0],[6,8,2],[-8,1,-2]],[[-6,-2,-1],[0,0,0],[8,7,2]]],float)
    original=np.array([data[0,2],data[0,2]+data[0,1],data[1,2]+data[1,0],data[1,2]])
    runs=S.split_curve(data,np.array([2.,4.]),np.array([3.,9.]),np.eye(4),[left,right])
    assert [r['owner'] for r in runs]==['left','right']
    for run in runs:
        seg,lo,hi,ta,tb,wa,wb=run['segments'][0]
        for t in np.linspace(0,1,101):
            assert np.max(abs(S.bezier(seg,t)-S.bezier(original,lo+(hi-lo)*t)))<1e-11
        points,tilts,widths=S.run_arrays(run)
        assert np.linalg.norm(points[0,1])>0 and np.linalg.norm(points[-1,0])>0
        assert np.allclose(tilts,[2+2*lo,2+2*hi]) and np.allclose(widths,[3+6*lo,3+6*hi])
    assert np.allclose(runs[0]['segments'][-1][0][-1],runs[1]['segments'][0][0][0],atol=1e-12)

def test_owner_uses_exact_priority_on_edge_and_refuses_gap():
    left=Region('first',[[0,0],[10,0],[10,10],[0,10]])
    right=Region('second',[[10,0],[20,0],[20,10],[10,10]])
    assert S.owner([10,5],[left,right]).id=='first'
    with pytest.raises(S.SplitError,match='unassigned'):S.owner([30,5],[left,right])

def test_road_along_boundary_refuses_ambiguous_assignment():
    left=Region('left',[[-10,-10],[0,-10],[0,10],[-10,10]])
    control=np.array([[0,0,-5],[0,0,-3],[0,0,3],[0,0,5]],float)
    with pytest.raises(S.SplitError,match='along'):S.cuts(control,[left])

def test_ground_mask_uses_exact_analytic_ellipse_and_inverse_transform():
    matrix=np.eye(4);matrix[:3,:3]=[[0,0,-1],[0,1,0],[1,0,0]];matrix[:3,3]=[5,4,5]
    node=T.Section('node',{'name':'ground'},{'size':'Vector2(20, 10)','transform':S.matrix_text(matrix)})
    scene=T.Scene(Path('unused'),{}, {},{'Ground/Regions/g':node})
    source=S.Source('old','s0',scene,[],np.zeros(3),Polygon([[-20,-20],[20,-20],[20,20],[-20,20]]),{}, {})
    left=Region('left',[[-20,-20],[5,-20],[5,20],[-20,20]])
    right=Region('right',[[5,-20],[20,-20],[20,20],[5,20]])
    result=list(S.ground_masks(source,'Ground/Regions/g',[left,right]))
    assert len(result)==2
    for d,ring in result:
        world=ring@matrix[np.ix_([0,2],[0,2])].T+matrix[[0,2],3]
        assert Polygon(world).symmetric_difference(source.ownership.intersection(d.shape)).area<1e-9
    assert node.properties['size']=='Vector2(20, 10)' and len(result[0][1])==4

def test_nonfinite_transform_fails_authority_assignment():
    node=T.Section('node',{'name':'x'},{'transform':'Transform3D(nan,0,0,0,1,0,0,0,1,0,0,0)'})
    scene=T.Scene(Path('unused'),{}, {},{'x':node})
    source=S.Source('old','s0',scene,[],np.zeros(3),None,{}, {})
    with pytest.raises(S.SplitError,match='nonfinite'):source.continent_matrix('x')

@pytest.fixture(scope='module')
def built():return S.build()

def test_all_pinned_source_nodes_and_payload_counts_are_conserved(built):
    outputs,proof=built
    c=proof['conservation']
    assert (c['placements'],c['markers'],c['spawnRows'],c['groundRecords'])==(17401,254,1027,253)
    assert c['maxPlacementMatrixErrorMetres']<.001
    assert max(m.get('grounds',0) for m in c['perMap'].values())==35
    assert len(proof['entries'])==254 and len({e['newMarkerId'] for e in proof['entries']})==254
    assert all(e['newMarkerId'].startswith(e['newRegion']+'--') for e in proof['entries'])
    assert len([p for p in outputs if p.endswith('.tscn')])==15
    assert len([p for p in outputs if p.endswith('/content/spawns.json')])==15
    assert all(c['accountedSourceNodes'][r]>0 for r in ('sw_isle','tollholms','gull_skerries'))

def test_replay_is_deterministic_and_corrupt_scene_detected(built,tmp_path):
    outputs,proof=built
    again,_=S.build()
    assert outputs==again
    pilot=outputs['godot-client/world_authoring/regions/spindle_hill/spindle_hill.tscn']
    assert F.parse_scene(pilot).node('Terrain').properties['sculpt_layer'].startswith('SubResource')
    corrupt=pilot.replace(b'collision_role = "solid"',b'collision_role = "none"',1)
    path=tmp_path/'scene.tscn'
    path.write_bytes(pilot)
    S.verify_outputs({'scene.tscn':pilot},tmp_path)
    path.write_bytes(corrupt)
    with pytest.raises(S.SplitError,match='corrupt'):S.verify_outputs({'scene.tscn':pilot},tmp_path)
    path.unlink()
    with pytest.raises(S.SplitError,match='stale'):S.verify_outputs({'scene.tscn':pilot},tmp_path)

def test_payload_spawn_rows_preserve_source_fields_and_continent_position(built):
    outputs,proof=built
    reader=F.GitInputs(F.CHECKOUT)
    old={}
    for region in ('sw_isle','tollholms','gull_skerries'):
        raw=json.loads(reader.read(f'eloria-assets/maps/continent-v2/{region}/content/spawns.json'))
        scene=F.parse_scene(reader.read(f'{S.REGION_ROOT}/{region}/{region}.tscn'))
        trans=F.numbers(scene.node('.').properties['continent_translation'],'Vector3')[[0,2]]
        for row in raw['spawns']:old[row['id']]=(row,trans)
    found=set()
    for path,blob in outputs.items():
        if not path.endswith('/content/spawns.json'):continue
        content=json.loads(blob);rid=content['map']
        scene=F.parse_scene(outputs[f'{S.REGION_ROOT}/{rid}/{rid}.tscn'])
        trans=F.numbers(scene.node('.').properties['continent_translation'],'Vector3')[[0,2]]
        for row in content['spawns']:
            previous,old_trans=old[row['id']]
            assert {k:v for k,v in row.items() if k!='local'}=={k:v for k,v in previous.items() if k!='local'}
            assert np.max(abs(np.array(row['local'])+trans-np.array(previous['local'])-old_trans))<1e-9
            assert row['id'] not in found;found.add(row['id'])
    assert found==set(old)


def test_unknown_light_or_group_node_cannot_silently_disappear(monkeypatch):
    original=S.Source.load.__func__
    def inject(cls,*args):
        source=original(cls,*args)
        if source.namespace=='s0':
            source.scene.nodes['UndeclaredLight']=T.Section('node',{'name':'UndeclaredLight','type':'OmniLight3D','parent':'.'},{'omni_range':'20'})
        return source
    monkeypatch.setattr(S.Source,'load',classmethod(inject))
    with pytest.raises(S.SplitError,match='unknown/unassigned.*UndeclaredLight'):S.build()


def test_all_authored_repair_wrappers_survive_with_none_collision(built):
    outputs,proof=built
    repairs=[]
    for path,raw in outputs.items():
        if not path.endswith('.tscn'):continue
        scene=F.parse_scene(raw)
        for node in scene.nodes.values():
            model=node.properties.get('scene_path','')
            if 'causeway-support' in model or 'causeway-joint' in model:
                assert json.loads(node.properties['collision_role'])=='none'
                repairs.append(json.loads(node.properties['asset_id']))
    assert len(repairs)==267 and len(set(repairs))==267


def test_serialized_resource_ids_are_accepted_by_godot(built):
    for path,raw in built[0].items():
        if path.endswith('.tscn'):
            for section in S.sections(raw):
                if section.kind in ('ext_resource','sub_resource'):
                    assert re.fullmatch(r'[A-Za-z0-9_]+',section.attributes['id']), (path,section.attributes['id'])
