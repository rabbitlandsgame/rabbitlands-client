"""Conservative AABB rejection for High-head contact guards only.

Clear points receive a distance lower bound and unused box witnesses, not an
exact skin closest point. Do not use this adapter for binding or placement.
"""
import numpy as np


class ContactHead:
    def __init__(self,head,margin_mm=3.2,geometric_sign=False):
        assert hasattr(head,'delta') and hasattr(head,'P') and hasattr(head,'T')
        assert 0<margin_mm<=20
        self.head=head;self.margin=float(margin_mm)/1000
        self.geometric_sign=bool(geometric_sign)
        self.statistics={'exact_queries':0,'outside_box_proofs':0,'calls':0}

    def __getattr__(self,name):return getattr(self.head,name)

    def signed(self,points,D=None,mesh=None,with_rim=False,T=None):
        X=np.asarray(points,float);P=self.head.P if D is None else self.head.P+D
        lo,hi=P.min(0),P.max(0)
        cp=np.minimum(np.maximum(X,lo),hi);separation=X-cp
        distance=np.linalg.norm(separation,axis=1)
        # A plane/line fixture does not describe a complete bounded head volume.
        complete=bool(((hi-lo)>1e-6).all())
        proved=distance>self.margin if complete else np.zeros(len(X),bool)
        normal=np.divide(separation,distance[:,None],out=np.zeros_like(separation),where=distance[:,None]>0)
        rim=np.zeros(len(X),bool);query=~proved
        if query.any():
            kwargs={'geometric_sign':True} if self.geometric_sign else {}
            values=self.head.signed(X[query],D=D,mesh=mesh,with_rim=True,T=T,**kwargs)
            distance[query],cp[query],normal[query],rim[query]=values
        self.statistics['calls']+=1;self.statistics['exact_queries']+=int(query.sum())
        self.statistics['outside_box_proofs']+=int(proved.sum())
        return (distance,cp,normal,rim) if with_rim else (distance,cp,normal)
