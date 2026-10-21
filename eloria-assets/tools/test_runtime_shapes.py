"""Regression coverage for runtime corrective packing, including >8 influences."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import write_glb
from video_motion.packing import append_array
from video_motion.runtime_shapes import positive_affine_basis, append_joints, export_runtime
from video_motion.runtime_validation import compare_runtime


def test_positive_affine_basis_preserves_signed_fields_and_defaults():
    rng=np.random.default_rng(47);basis=rng.normal(size=(4,7,3));weights=rng.normal(size=(31,4))
    values=np.einsum('km,mvc->kvc',weights,basis)
    targets,amounts,error=positive_affine_basis(values,1e-9)
    assert np.min(amounts)>=-1e-12 and np.max(amounts)<=1+1e-12
    assert np.all(amounts[:,0]==1)
    assert np.max(abs(np.einsum('km,mvc->kvc',amounts,targets)-values))<1e-9
    assert error<1e-9


def test_compensated_skin_keeps_all_native_curves_and_surface(tmp_path):
    d={'asset':{'version':'2.0'},'bufferViews':[],'accessors':[],'buffers':[{'byteLength':0}],'scene':0,'scenes':[{'nodes':list(range(13))}],
       'nodes':[{'name':f'joint_{i}'} for i in range(12)]+[{'name':'body','mesh':0,'skin':0}], 'meshes':[], 'skins':[], 'animations':[]}
    b=bytearray();pos=np.array([[0,0,0],[1,0,0],[0,1,0]],float);at={'POSITION':append_array(d,b,pos,'VEC3'),'NORMAL':append_array(d,b,np.tile([0,0,1],(3,1)),'VEC3')}
    for i in range(3):
        at[f'JOINTS_{i}']=append_joints(d,b,np.tile(np.arange(4*i,4*i+4),(3,1)))
        at[f'WEIGHTS_{i}']=append_array(d,b,np.full((3,4),1/12),'VEC4')
    targets=[{'POSITION':append_array(d,b,np.tile([0,.02,0],(3,1)),'VEC3'),'NORMAL':append_array(d,b,np.tile([.02,0,0],(3,1)),'VEC3')}]
    d['meshes']=[{'primitives':[{'attributes':at,'targets':targets}],'weights':[.3]}]
    d['skins']=[{'joints':list(range(12)),'inverseBindMatrices':append_array(d,b,np.tile(np.eye(4).reshape(1,16),(12,1)),'MAT4')}]
    clock=append_array(d,b,np.array([0,.5,1])[:,None],'SCALAR')
    for name,sign in [('Walk',1),('Attack',-1)]:
        d['animations'].append({'name':name,'channels':[{'target':{'node':10,'path':'translation'},'sampler':0},{'target':{'node':12,'path':'weights'},'sampler':1}],
            'samplers':[{'input':clock,'output':append_array(d,b,np.array([[0,0,0],[sign*.3,.1,0],[0,0,0]]),'VEC3')},{'input':clock,'output':append_array(d,b,np.array([.3,1,.3])[:,None],'SCALAR')}]})
    source=tmp_path/'source.glb';runtime=tmp_path/'runtime.glb';write_glb(source,d,b)
    report=export_runtime(source,runtime,1,packing_hz=48)
    assert report['parts'][0]['packing_compensated'] and report['parts'][0]['skin_slots']==8
    assert compare_runtime(source,runtime,1)['passed']


def test_zero_shape_basis_is_empty():
    targets,weights,error=positive_affine_basis(np.zeros((3,7,3)),1e-8)
    assert targets.shape==(0,7,3) and weights.shape==(3,0) and error==0


def test_prefix_reduction_enforces_field_error_and_default_pose(tmp_path):
    from video_motion.runtime_shapes import reduce_affine_basis
    d={'asset':{'version':'2.0'},'bufferViews':[],'accessors':[],'buffers':[{'byteLength':0}],'nodes':[{'mesh':0,'weights':[1,.2,1.]}],'meshes':[],'animations':[]};b=bytearray()
    zero=np.zeros((3,3));bx=zero.copy();by=zero.copy();bx[:,0]=.1;by[:,1]=.01
    targets=[{'POSITION':append_array(d,b,x,'VEC3')} for x in [zero,bx,by]]
    d['meshes']=[{'primitives':[{'attributes':{'POSITION':append_array(d,b,zero,'VEC3')},'targets':targets}],'weights':[1,.2,1.],'extras':{'targetNames':['bias','x','y']}}]
    d['animations']=[{'name':'Idle','channels':[{'target':{'node':0,'path':'weights'},'sampler':0}],'samplers':[{'input':append_array(d,b,np.array([0,1])[:,None],'SCALAR'),'output':append_array(d,b,np.array([[1,.2,0],[1,.3,0]]).reshape(-1,1),'SCALAR')}]}]
    source=tmp_path/'basis.glb';out=tmp_path/'smaller.glb';write_glb(source,d,b)
    with pytest.raises(ValueError,match='Prefix error'): reduce_affine_basis(source,out,1,1,0,.001)
    assert not out.exists()
    report=reduce_affine_basis(source,out,1,1,0,.02)
    assert abs(report['prefix_added_local_error_over_height']-.01)<1e-8 and out.exists()
