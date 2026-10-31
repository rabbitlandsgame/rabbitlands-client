"""Explicit, unqualified coherent seeds for a Native cap's ear regions.

This changes no input or asset. It supplies only an initial delta for a caller's
complete-fixture vertex/interior fitting and independent qualification gates.
"""
import numpy as np


def coherent_ear_seed(points,bands,shift_mm,max_shift_mm=14):
    """Return a bilateral local seed, with the side component mirrored.

    ``bands`` requires x=[start,full], y=[full,end], and
    z=[start,full,fade,end], all in the caller's bind-space metres. No style or
    sex is selected automatically. ``shift_mm`` is [outward,up,forward], where
    positive outward means +X on the left and -X on the right.
    """
    P=np.asarray(points,float);shift=np.asarray(shift_mm,float)
    assert P.ndim==2 and P.shape[1]==3 and np.isfinite(P).all()
    assert shift.shape==(3,) and np.isfinite(shift).all()
    assert set(bands)=={'x','y','z'}
    x=np.asarray(bands['x'],float);y=np.asarray(bands['y'],float);z=np.asarray(bands['z'],float)
    assert x.shape==(2,) and y.shape==(2,) and z.shape==(4,)
    assert np.isfinite(np.r_[x,y,z]).all() and 0<=x[0]<x[1] and y[0]<y[1] and z[0]<z[1]<=z[2]<z[3]
    assert 0<max_shift_mm<=20 and np.linalg.norm(shift)<=max_shift_mm,'Seed exceeds its explicit displacement bound'
    weight=(np.clip((np.abs(P[:,0])-x[0])/(x[1]-x[0]),0,1)
        *np.clip((y[1]-P[:,1])/(y[1]-y[0]),0,1)
        *np.clip((P[:,2]-z[0])/(z[1]-z[0]),0,1)
        *np.clip((z[3]-P[:,2])/(z[3]-z[2]),0,1))
    direction=np.tile(shift,(len(P),1));direction[:,0]*=np.sign(P[:,0])
    D=weight[:,None]*direction/1000
    return D,{'qualified':False,'seed_only':True,'bands_m':{key:np.asarray(value).tolist() for key,value in bands.items()},
        'shift_mm':shift.tolist(),'limit_mm':max_shift_mm,
        'changed_vertices':int((weight>0).sum()),'maximum_shift_mm':float(np.linalg.norm(D,axis=1).max()*1000) if len(D) else 0.,
        'high_input_unchanged':True,'requires_complete_fixture_and_face_checks':True}
