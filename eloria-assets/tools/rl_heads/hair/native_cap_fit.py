"""Optional Native-only cap fitting; High attributes remain a refined surface.

This utility does not write assets or register a runtime style. The caller must
still qualify evaluated Native controls/poses, High identities and coverage.
"""
import numpy as np
import headref
from native_hair_clearance import NativeFaceGuardFailure
from refine_cap_triangles import refine_cap

BARY=np.array([[1/3,1/3,1/3],[.5,.5,0],[.5,0,.5],[0,.5,.5]])

def cap_probes(P,T,minimum_edge_mm=5):
    triangle=P[T];edges=np.linalg.norm(triangle-np.roll(triangle,1,axis=1),axis=2)
    selected=np.flatnonzero(edges.max(1)*1000>=minimum_edge_mm)
    return np.einsum('pc,fcv->fpv',BARY,triangle[selected]).reshape(-1,3),selected

def radial_seat(native,P,center,stand_off_mm=2.3,vertex_margin_mm=2.2,max_shift_mm=14):
    """Use the outermost radial branch consistently across the ear crease."""
    P=np.asarray(P);center=np.asarray(center,float);direction=headref.unit(P-center)
    origin=np.repeat(center[None],len(P),0)
    locations,rays,faces=native.mesh.ray.intersects_location(origin,direction,multiple_hits=True)
    distance=((locations-origin[rays])*direction[rays]).sum(1);best={}
    for index,(ray,value) in enumerate(zip(rays,distance)):
        if value>0 and (ray not in best or value>distance[best[ray]]):best[int(ray)]=index
    assert len(best)==len(P),'Native cap rays must all hit the retained head surface'
    ids=np.array([best[index] for index in range(len(P))]);hit=locations[ids]
    triangle=native.T[faces[ids]]
    bc=headref.barycentric(hit,native.P[triangle[:,0]],native.P[triangle[:,1]],native.P[triangle[:,2]])
    normal=headref.unit((native.N[triangle]*bc[:,:,None]).sum(1))
    target=hit+normal*(stand_off_mm/1000)
    active=np.linalg.norm(P-center,axis=1)<np.linalg.norm(target-center,axis=1)
    Q=P.astype(float,copy=True);Q[active]=target[active]
    Q,seating=native.push_out(Q,vertex_margin_mm/1000,max_shift_mm=max_shift_mm)
    displacement=np.linalg.norm(Q-P,axis=1)*1000
    assert displacement.max()<=max_shift_mm,'Native radial cap fit exceeded its total displacement bound'
    return Q,{'changed_vertices':int((displacement>0).sum()),'maximum_shift_mm':float(displacement.max()),'vertex_seating':seating}

def fit_cap(native,attributes,triangles,center,max_extra_triangles,max_shift_mm=14,
            refinement_rounds=3,deep_clearance_mm=1,face_margin_mm=2.15,
            radial_stand_off_mm=2.3,vertex_margin_mm=2.2):
    """Return refined High arrays/triangles, Native POSITION delta and receipt.

    ``attributes`` and ``triangles`` describe the shell only. All existing ID,
    grooming and normal targets must be included so midpoint interpolation can
    preserve their High surface. An explicit style-local limit may be passed;
    the generic default remains 14 mm. No exterior or backing is accepted here.
    """
    assert 0<max_shift_mm<=20 and 0<=refinement_rounds<=6
    assert 0<=deep_clearance_mm<2 and 2<face_margin_mm<=3
    assert 2<=vertex_margin_mm<=radial_stand_off_mm<=5
    arrays={key:np.asarray(value).copy() for key,value in attributes.items()};T=np.asarray(triangles,int).copy()
    original_triangles=len(T);records=[];original_prefix={key:value.copy() for key,value in arrays.items()}
    for iteration in range(refinement_rounds+1):
        Q,seating=radial_seat(native,arrays['P'],center,max_shift_mm=max_shift_mm,
                             stand_off_mm=radial_stand_off_mm,vertex_margin_mm=vertex_margin_mm)
        probes,faces=cap_probes(Q,T)
        signed=native.signed(probes)[0] if len(probes) else np.empty(0)
        worst=signed.reshape(-1,4).min(1);deep=faces[worst<deep_clearance_mm/1000]
        record={'iteration':iteration,'triangles':len(T),'deep_faces':len(deep),
                'minimum_probe_clearance_mm':float(signed.min()*1000) if len(signed) else None,'seating':seating};records.append(record)
        if not len(deep) or iteration==refinement_rounds:break
        arrays,T,proof=refine_cap(arrays,T,deep,max_extra_triangles-(len(T)-original_triangles))
        record['refinement']=proof
    Q,face_proof=native.push_faces(Q,T,{'shell':[0,len(Q)]},parts=('shell',),
                                 margin=face_margin_mm/1000,max_shift_mm=max_shift_mm)
    displacement=np.linalg.norm(Q-arrays['P'],axis=1)*1000
    assert displacement.max()<=max_shift_mm,'Native cap support exceeded its total displacement bound'
    probes,_=cap_probes(Q,T);signed,_,_=native.signed(np.vstack([Q,probes]))
    assert (signed>=.002).all(),'Native cap fitting must retain the actual 2 mm gate'
    for key,value in original_prefix.items():assert np.array_equal(arrays[key][:len(value)],value)
    return arrays,T,(Q-arrays['P']).astype('f4'),{'iterations':records,'face_support':face_proof,
        'maximum_shift_mm':float(displacement.max()),'limit_mm':max_shift_mm,
        'radial_stand_off_mm':radial_stand_off_mm,'vertex_margin_mm':vertex_margin_mm,
        'minimum_clearance_mm':float(signed.min()*1000),
        'clearance_percentiles_mm':np.percentile(signed*1000,[0,1,5,50,95,99,100]).tolist(),
        'old_high_attribute_prefix_exact':True,'extra_triangles':len(T)-original_triangles,
        'scope':'Native-only cap position field; High surface retained by interpolation',
        'qualified':False}
