"""Causeway dressing must preserve the served geometry and extend only legs."""
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[5]
SOURCE=ROOT/'eloria-assets/maps/continent-v2/sw_isle/source'
sys.path.insert(0,str(SOURCE))
import repair_causeways as R


def test_ground_sampling_uses_the_rendered_terrain_diagonal():
    h=np.array([[0.,2.],[4.,10.]])
    t={'origin':[0.,0.],'cellMetres':1.}
    np.testing.assert_allclose(R.ground_sample(h,t,[[.25,.25],[.75,.75]]),[1.5,6.5])


def test_extended_legs_reach_the_ground_and_keep_texture_scale():
    doc,body=R.model_soup(R.PROTOS/'kit-sw-causeway-arch-span.glb')
    matrix=np.eye(4);matrix[:3,3]=[0.,30.,0.]
    h=np.full((25,25),-5.)
    t={'origin':[-12.,-12.],'cellMetres':1.}
    soup=R.support_soup(body,matrix,h,t)
    p=soup[:,:,:3]
    assert np.isfinite(soup).all()
    assert p[:,:,1].max()<=22.30001
    assert p[:,:,1].min()<=-5.5999
    # Repeating side bands never recreate a deck or arch across the opening.
    assert np.all(np.abs(p[:,:,0])>3.)
    assert np.all(np.abs(p[:,:,2])>4.)
    assert np.ptp(p[:,:,1],axis=1).max()<=1.70001
    normal=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])
    assert np.all(np.linalg.norm(normal,axis=1)>1e-8)


def test_buried_feet_do_not_generate_an_extra_support():
    _,body=R.model_soup(R.PROTOS/'kit-sw-causeway-arch-span.glb')
    matrix=np.eye(4)
    h=np.full((25,25),0.)
    assert not len(R.support_soup(body,matrix,h,{'origin':[-12.,-12.],'cellMetres':1.}))


def test_dressing_glb_has_no_walk_surface_or_collider():
    doc,body=R.model_soup(R.PROTOS/'kit-sw-causeway-arch-span.glb')
    out,_=R.encode(doc,body,'kit-test-support',np.zeros(3))
    assert len(out['nodes'])==1
    assert not out['nodes'][0]['name'].startswith('Walk_')
    assert out['nodes'][0]['extras']['eloria']['collisionRole']=='none'
    assert 'collider' not in out['nodes'][0]['extras']['eloria']


def test_float32_seam_slivers_are_removed_before_encoding():
    doc,body=R.model_soup(R.PROTOS/'kit-sw-causeway-arch-span.glb')
    good=body[0].copy();good[:,:3]=[[0.,0.,0.],[0.,0.,1.],[1.,0.,0.]]
    sliver=good.copy();sliver[:,:3]=[[1.,0.,0.],[1.+1e-9,0.,0.],[1.,0.,1.]]
    out,_=R.encode(doc,np.stack([good,sliver]),'kit-test-joint',np.zeros(3))
    assert out['accessors'][3]['count']==3


def test_terminal_ends_are_not_connected_across_a_large_gap():
    a=np.eye(4);b=np.eye(4);b[0,3]=40
    assert R.joins([{'matrix':a},{'matrix':b}])==[]
    b[0,3]=12
    assert len(R.joins([{'matrix':a},{'matrix':b}]))==1
