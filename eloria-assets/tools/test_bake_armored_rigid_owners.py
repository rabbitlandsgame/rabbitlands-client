"""Whole-island ownership keeps seams/corners and original motion bits intact."""
import copy
import json

import numpy as np
import pytest

from bake_armored_rigid_owners import build, physical_components
from video_motion.asset import read_glb, write_glb, digest
from video_motion.creature_storage import _append, _array
from video_motion.packing import append_array


def fixture(tmp_path, eight=False):
    d = {'asset': {'version': '2.0', 'extras': {'rabbitlands_animation_bake_fps': 30, 'human_approved': False}},
         'buffers': [{'byteLength': 0}], 'accessors': [], 'bufferViews': [], 'scene': 0,
         'scenes': [{'nodes': [0]}], 'nodes': [{'name': 'RL_Spider_Body', 'children': [1]},
             {'name': 'Mesh', 'mesh': 0, 'skin': 0, 'weights': [0.]}],
         'materials': [{'name': 'Material', 'doubleSided': True}]}
    b = bytearray()
    # Two hard-normal/UV faces share exact geometric endpoints, not indices.
    pos = append_array(d, b, [[0,0,0],[1,0,0],[0,1,0],[0,0,0],[1,0,0],[0,0,1]], 'VEC3')
    normal = append_array(d, b, [[0,0,1]]*3 + [[0,1,0]]*3, 'VEC3')
    uv = append_array(d, b, [[0,0],[1,0],[0,1],[.2,.2],[.8,.2],[.2,.8]], 'VEC2')
    attrs = {'POSITION':pos,'NORMAL':normal,'TEXCOORD_0':uv}
    for i in range(2 if eight else 1):
        attrs[f'JOINTS_{i}'] = _append(d, b, np.zeros((6,4), '<u2'), {'componentType':5123,'type':'VEC4'})
        attrs[f'WEIGHTS_{i}'] = append_array(d, b, np.full((6,4), 1/(8 if eight else 4)), 'VEC4')
    indices = _append(d,b,np.arange(6,dtype='<u2')[:,None],{'componentType':5123,'type':'SCALAR'})
    delta = append_array(d,b,np.zeros((6,3)), 'VEC3')
    d['meshes'] = [{'name':'Original','weights':[0.],'extras':{'targetNames':['Zero']},'primitives':[
        {'attributes':attrs,'indices':indices,'targets':[{'POSITION':delta,'NORMAL':delta}],'material':0}]}]
    bind = append_array(d,b,np.eye(4).reshape(1,16),'MAT4')
    d['skins'] = [{'joints':[0],'inverseBindMatrices':bind,'name':'OriginalSkin'}]
    clock = append_array(d,b,[[0],[1]],'SCALAR')
    trans = append_array(d,b,[[0,0,0],[.1,0,0]],'VEC3')
    weight = append_array(d,b,[[0],[0]],'SCALAR')
    d['animations'] = [{'name':'Jog','extras':{'event':.3},'channels':[
        {'target':{'node':0,'path':'translation'},'sampler':0},
        {'target':{'node':1,'path':'weights'},'sampler':1}],
        'samplers':[{'input':clock,'output':trans},{'input':clock,'output':weight}]}]
    source = tmp_path/'source.glb';write_glb(source,d,b)
    bounds = copy.deepcopy(d)
    bounds['meshes'][0]['extras']['rabbitlands_actor_bounds_v1'] = {'position':[0,0,0],'size':[1,1,1]}
    bounds_path=tmp_path/'bounds.glb';write_glb(bounds_path,bounds,b)
    profile=tmp_path/'profile.json';profile.write_text(json.dumps({'fixture':{'rigid_components':[{'component':0,'vertices':6,'owner':0}]}}))
    return source,profile,bounds_path


@pytest.mark.parametrize('eight',[False,True])
def test_skin_controls_replace_zero_fields_without_geometry_or_motion_edits(tmp_path,eight):
    source,profile,bounds=fixture(tmp_path,eight)
    old=source.read_bytes()
    output=tmp_path/'baked.glb'
    r=build(source,source,profile,bounds,output,actor='fixture',report=tmp_path/'report.json',
            owner_position_limit=1e-8,owner_normal_limit_degrees=1e-6)
    assert source.read_bytes()==old and r['added_nodes']==0 and r['corrective_targets']==0
    assert r['maximum_owner_position_error']<1e-12
    a,ab=read_glb(source);c,cb=read_glb(output)
    assert c['asset']['extras']['human_approved'] is False
    op=a['meshes'][0]['primitives'][0];cp=c['meshes'][0]['primitives'][0]
    assert 'targets' not in cp and c['skins'][0]['joints']==[0]
    for key in ['POSITION','NORMAL','TEXCOORD_0']:
        assert _array(a,ab,op['attributes'][key]).tobytes()==_array(c,cb,cp['attributes'][key]).tobytes()
    assert _array(c,cb,cp['indices']).ravel().tolist()==list(range(6))
    weights=np.concatenate([_array(c,cb,cp['attributes'][f'WEIGHTS_{i}']) for i in range(2 if eight else 1)],axis=1)
    assert np.array_equal(weights[:,0],np.ones(6)) and not weights[:,1:].any()
    for key in ['input','output']:
        assert _array(a,ab,a['animations'][0]['samplers'][0][key]).tobytes()==_array(c,cb,c['animations'][0]['samplers'][0][key]).tobytes()
    assert r['clip_active_ends']=={'Jog':1.}
    assert len(r['component_owners'])==1 and r['component_owners'][0]['vertices']==6


def test_position_welding_is_analysis_only_and_does_not_join_separate_gaps():
    p=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,0],[1,0,0],[0,0,1],[2,0,0],[3,0,0],[2,1,0]],float)
    groups=physical_components(p,np.arange(9).reshape(-1,3))
    assert [g.tolist()for g in groups]==[list(range(6)),[6,7,8]]


@pytest.mark.parametrize('fault',['role_count','owner_missing','nonrigid','hash','overwrite'])
def test_uncertified_ownership_fails_closed(tmp_path,fault):
    source,profile,bounds=fixture(tmp_path)
    extra={}
    if fault=='role_count':
        p=json.loads(profile.read_text());p['fixture']['rigid_components'][0]['vertices']=5;profile.write_text(json.dumps(p))
    elif fault=='owner_missing':
        p=json.loads(profile.read_text());p['fixture']['rigid_components'][0]['owner']=99;profile.write_text(json.dumps(p))
    elif fault=='nonrigid':
        d,b=read_glb(source);b=bytearray(b);p=d['meshes'][0]['primitives'][0]
        p['targets'][0]['POSITION']=append_array(d,b,[[.1,0,0]]*6,'VEC3')
        d['animations'][0]['samplers'][1]['output']=append_array(d,b,[[0],[1]],'SCALAR');write_glb(source,d,b)
    elif fault=='hash':extra['expected_source_sha256']='0'*64
    output=tmp_path/'baked.glb'
    if fault=='overwrite':output.write_bytes(b'keep')
    with pytest.raises(ValueError):
        build(source,source,profile,bounds,output,actor='fixture',report=tmp_path/'report.json',
              owner_position_limit=1e-8,owner_normal_limit_degrees=1e-6,**extra)
    assert not output.exists() or output.read_bytes()==b'keep'
