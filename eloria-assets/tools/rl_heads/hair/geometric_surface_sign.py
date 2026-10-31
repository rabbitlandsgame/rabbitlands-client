"""Geometric sign normals for explicit authoring collision checks.

Distances and closest triangles still come from the original skin. Lighting
normals are not used to classify which side of that skin contains a point.
"""
import numpy as np


def unit(values):
    return values/np.maximum(np.linalg.norm(values,axis=-1,keepdims=True),1e-20)


class GeometricSurfaceSign:
    def __init__(self,positions,triangles,weld=None):
        P=np.asarray(positions,float);T=np.asarray(triangles,int)
        assert P.ndim==2 and P.shape[1]==3 and T.ndim==2 and T.shape[1]==3
        assert len(T) and np.isfinite(P).all() and T.min()>=0 and T.max()<len(P)
        if weld is None:_,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
        weld=np.asarray(weld,int);assert weld.shape==(len(P),) and weld.min()>=0
        self.T=T;self.weld=weld;X=P[T]
        self.face=unit(np.cross(X[:,1]-X[:,0],X[:,2]-X[:,0]))
        vertex=np.zeros((weld.max()+1,3))
        for corner in range(3):
            first=X[:,(corner+1)%3]-X[:,corner];second=X[:,(corner+2)%3]-X[:,corner]
            cosine=(first*second).sum(1)/np.maximum(np.linalg.norm(first,axis=1)*np.linalg.norm(second,axis=1),1e-20)
            angle=np.arccos(np.clip(cosine,-1,1))
            np.add.at(vertex,weld[T[:,corner]],self.face*angle[:,None])
        self.vertex=unit(vertex)[weld]
        edges=np.sort(weld[T][:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
        unique,inverse=np.unique(edges,axis=0,return_inverse=True)
        edge=np.zeros((len(unique),3));np.add.at(edge,inverse,np.repeat(self.face,3,axis=0))
        self.edge=unit(edge)[inverse].reshape(-1,3,3)

    def normals(self,triangles,barycentric,tolerance=1e-7):
        indices=np.asarray(triangles,int);bc=np.asarray(barycentric,float)
        assert indices.ndim==1 and bc.shape==(len(indices),3) and np.isfinite(bc).all()
        result=self.face[indices].copy();corner=bc.argmax(1);vertex=bc.max(1)>=1-tolerance
        rows=np.flatnonzero(vertex)
        result[rows]=self.vertex[self.T[indices[rows],corner[rows]]]
        edge=(~vertex)&(bc.min(1)<=tolerance);rows=np.flatnonzero(edge)
        opposite=bc[rows].argmin(1)
        result[rows]=self.edge[indices[rows],(opposite+1)%3]
        return result
