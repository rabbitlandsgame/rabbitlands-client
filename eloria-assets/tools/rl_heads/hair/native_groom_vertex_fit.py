"""Optional Native-only shared vertex corrective across grooming states.

This authors one constant POSITION delta; it never edits the supplied High
positions/targets. It intentionally does not qualify triangle interiors, poses,
coverage or attachment. Those independent gates remain required.
"""
from pathlib import Path
import hashlib
import numpy as np
import headref
from native_hair_fixtures import GROOM_CASES

TOOL_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class NativeVertexFitFailure(AssertionError):
    def __init__(self,message,points,receipt):
        super().__init__(message);self.points=points;self.receipt=receipt


def fit_vertices(native,P,targets,groom_cases=None,margin_mm=3.,max_shift_mm=14.,
                 initial_delta=None,max_iterations=32):
    """Return a bounded shared delta and an explicitly vertex-only receipt."""
    original=np.asarray(P);assert original.ndim==2 and original.shape[1]==3 and np.isfinite(original).all()
    assert 0<max_shift_mm<=20 and margin_mm>=2 and 0<max_iterations<=64
    cases=GROOM_CASES if groom_cases is None else groom_cases
    assert cases
    moves=[];labels=[];seen=set()
    for label,weights in cases.items():
        assert set(weights)<=set(targets),'A requested grooming target is missing'
        move=np.zeros_like(original,dtype=float)
        for name,value in weights.items():
            delta=np.asarray(targets[name]);assert delta.shape==original.shape and np.isfinite(delta).all()
            move+=delta*float(value)
        signature=hashlib.sha256(move.tobytes()).digest()
        if signature in seen:continue
        seen.add(signature);moves.append(move);labels.append(label)
    D=np.zeros_like(original,dtype=float) if initial_delta is None else np.asarray(initial_delta,float).copy()
    assert D.shape==original.shape and np.isfinite(D).all()
    assert np.linalg.norm(D,axis=1).max()*1000<=max_shift_mm
    Q=original.astype(float)+D;_,weld=np.unique(np.round(original/1e-6),axis=0,return_inverse=True)
    history=[]
    for iteration in range(max_iterations):
        worst=np.full(len(Q),np.inf);direction=np.zeros_like(Q)
        for move in moves:
            probes=Q+move;distance,closest,normal=native.signed(probes)
            at=distance<worst;worst[at]=distance[at]
            separation=probes-closest;length=np.linalg.norm(separation,axis=1)
            outward=headref.unit(separation)*np.where(distance<0,-1.,1.)[:,None]
            outward[length<1e-10]=normal[length<1e-10];direction[at]=outward[at]
        bad=worst<margin_mm/1000-1e-8
        history.append({'iteration':iteration,'contacts':int(bad.sum()),'minimum_mm':float(worst.min()*1000)})
        if not bad.any():
            D=Q-original;distance=np.linalg.norm(D,axis=1)*1000
            return D.astype('f4'),{'vertex_only':True,'qualified':False,'tool_sha256':TOOL_SHA256,
                'groom_cases':labels,'margin_mm':margin_mm,'limit_mm':max_shift_mm,'maximum_shift_mm':float(distance.max()),
                'changed_vertices':int((distance>0).sum()),'iterations':history,'high_positions_and_targets_unchanged':True,
                'triangle_interiors_checked':False,'weld_tolerance_mm':.001}
        amount=np.where(bad,margin_mm/1000+.0002-worst,0)
        order=np.argsort(amount,kind='stable');_,reverse=np.unique(weld[order][::-1],return_index=True)
        chosen=order[len(order)-1-reverse];step=np.zeros((weld.max()+1,3))
        step[weld[chosen]]=direction[chosen]*amount[chosen,None]
        proposal=Q+step[weld];D=proposal-original;length=np.linalg.norm(D,axis=1)*1000
        group_max=np.zeros(weld.max()+1);np.maximum.at(group_max,weld,length)
        scale=np.minimum(1.,(max_shift_mm-.0001)/np.maximum(group_max,1e-12))
        D*=scale[weld,None];Q=original+D
        history[-1]['bounded_vertices']=int((scale[weld]<1).sum())
        assert np.linalg.norm(Q-original,axis=1).max()*1000<=max_shift_mm
    raise NativeVertexFitFailure('Native vertex constraints remain unresolved inside the displacement bound',Q,
        {'vertex_only':True,'qualified':False,'tool_sha256':TOOL_SHA256,'groom_cases':labels,
         'margin_mm':margin_mm,'limit_mm':max_shift_mm,'maximum_shift_mm':float(np.linalg.norm(Q-original,axis=1).max()*1000),'iterations':history})
