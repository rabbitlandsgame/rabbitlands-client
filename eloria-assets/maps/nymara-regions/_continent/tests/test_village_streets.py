"""Real floor contacts, architectural clearance, and encoded actor support."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manymouth_village_streets as V


def rectangle(lo,hi,y):
    a,b,c,d=np.array([[lo[0],y,lo[1]],[hi[0],y,lo[1]],
        [lo[0],y,hi[1]],[hi[0],y,hi[1]]],float)
    return np.array([[a,c,b],[b,c,d]])


def world():
    return SimpleNamespace(ids=[V.REGION],
        height_at=lambda x,z:np.full(np.broadcast(x,z).shape,-1.),
        owner_at=lambda x,z:np.zeros(np.broadcast(x,z).shape,int))


def fixture(monkeypatch,distance=12):
    objects=[];nodes=[]
    for name,x,y in (('low',0,1.75),('high',distance,4.)):
        faces=rectangle([x-1,-1.5],[x+1,1.5],y)
        objects.append(dict(region=V.REGION,node=name,floors=faces,
            low=faces.min(axis=(0,1)),high=faces.max(axis=(0,1))))
        nodes.append(dict(name=name,xz=np.array([x,0.]),y=y,faces=faces))
    content=SimpleNamespace(objects=objects)
    monkeypatch.setattr(V.D,'_triangles',lambda content,obj,**kwargs:obj['floors'])
    monkeypatch.setattr(V,'structural_parts',lambda content:[])
    monkeypatch.setattr(V.C,'water_samples',lambda world,x,z:(np.ones_like(x,bool),np.zeros_like(x,float)))
    return world(),content,nodes


def test_sloping_street_meets_both_real_floors_and_all_four_actor_subcells(monkeypatch):
    w,c,nodes=fixture(monkeypatch)
    before=[o['floors'].copy() for o in c.objects]
    faces,report=V.street_faces(w,c,[np.array([[0.,0.],[12.,0.]])],nodes,{})
    assert report['maximumGrade']<=.65 and report['maximumContactLift']<=.04
    all_faces=np.concatenate([faces,*before])
    x=np.arange(-.5,13.,1)[:,None]+np.array([-.25,.25])[None,:]
    xx,zz=np.broadcast_arrays(x[:,:,None],np.array([-.25,.25])[None,None,:])
    heights=V.floor_samples(all_faces,xx,zz)
    assert np.isfinite(heights).all()
    assert heights.min()>=1.75 and heights.max()<=4.015001
    # The old porches remain exact, with no generated coplanar floor over them.
    for obj,old in zip(c.objects,before):
        np.testing.assert_array_equal(obj['floors'],old)
        point=old.mean(axis=(0,1))
        assert not np.isfinite(V.floor_samples(faces,point[0],point[2]))
    np.testing.assert_allclose(V.floor_samples(all_faces,np.array([0.,12.]),0),[1.75,4.])


def test_impossible_floor_separation_fails_instead_of_lifting_the_porch(monkeypatch):
    w,c,nodes=fixture(monkeypatch,distance=4)
    with pytest.raises(ValueError,match='more grade length'):
        V.street_faces(w,c,[np.array([[0.,0.],[4.,0.]])],nodes,{})


def test_binary_planar_weld_preserves_an_actor_sample_on_a_clipped_cell_diagonal():
    a=np.array([460.473849,1245.526151]);b=np.array([460.802881,1245.197119])
    xz=np.array([[a,b,[460.,1245.]],[b,a,[461.,1246.]]])
    points=V.encoded_planar_points(xz.reshape(-1,2))
    faces=np.c_[points[:,0],np.full(len(points),1.765),points[:,1]].reshape(-1,3,3)
    for face in faces:
        if np.cross(face[1]-face[0],face[2]-face[0])[1]<0:face[[1,2]]=face[[2,1]]
    q=np.array([460.75,1245.25])
    assert V.floor_samples(faces,*q)==pytest.approx(1.765)
    # Both rounded endpoints retain the same exact grid diagonal.
    np.testing.assert_array_equal(points[:2].sum(axis=1),[1706.,1706.])
    assert np.max(abs(points-xz.reshape(-1,2)))<.0001


def test_actual_actor_band_keeps_an_open_arch_beneath_its_high_beam(monkeypatch):
    def box(lo,hi):
        a=rectangle(lo[[0,2]],hi[[0,2]],lo[1]);b=rectangle(lo[[0,2]],hi[[0,2]],hi[1])
        # Corner/edge clipping supplies an exact convex solid footprint.
        return np.concatenate([a,b])
    parts=[]
    for lo,hi in (([-.3,0,-4],[.3,5,-3]),([-.3,0,3],[.3,5,4]),([-.3,3.9,-4],[.3,5,4])):
        lo,hi=np.array(lo,float),np.array(hi,float);parts.append((box(lo,hi),lo,hi))
    monkeypatch.setattr(V,'structural_parts',lambda content:parts)
    nodes=[dict(name=str(x),xz=np.array([x,0.]),y=1.,faces=rectangle([x-1,-1],[x+1,1],1.)) for x in (-5,5)]
    path=V.route(world(),None,*nodes)
    assert path is not None
    np.testing.assert_array_equal(path,np.array([[-5.,0.],[5.,0.]]))
    assert V.actor_band_polygon(parts[2][0],1.06,3.1) is None


def test_exact_triangle_floor_sampling_ignores_a_lower_reversed_surface():
    slope=np.array([[[0.,2.,0.],[0.,4.,2.],[2.,3.,0.]]])
    ceiling=rectangle([0,0],[2,2],8.)[:,::-1]
    assert V.floor_samples(np.concatenate([slope,ceiling]),.5,.5)==pytest.approx(2.75)
    assert not np.isfinite(V.floor_samples(slope,2.,2.))
