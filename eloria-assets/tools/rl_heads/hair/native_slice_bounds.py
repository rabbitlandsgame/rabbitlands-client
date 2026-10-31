"""Optional outside proof from a complete evaluated fixture's cross-section.

This never supplies distances, normals, placement or a head envelope. Empty,
degenerate and near-coplanar sections provide no proof and preserve raw signs.
"""
import numpy as np


class HorizontalSliceBounds:
    def __init__(self, complete_mesh, epsilon=1e-8, cache_planes=8192):
        assert 0<epsilon<=1e-6 and cache_planes>=0
        self.mesh=complete_mesh;self.triangles=np.asarray(complete_mesh.triangles,float)
        assert len(self.triangles) and np.isfinite(self.triangles).all()
        self.epsilon=float(epsilon);self.cache_planes=int(cache_planes);self.cache={}
        self.volumetric=bool(((complete_mesh.bounds[1]-complete_mesh.bounds[0])>epsilon*2).all())
        self.last_query={}

    def _sections(self, heights):
        lo=np.full((len(heights),2),np.inf);hi=np.full((len(heights),2),-np.inf)
        ambiguous=np.zeros(len(heights),bool);epsilon=self.epsilon
        bounds=self.mesh.bounds
        for start in range(0,len(heights),256):
            y=heights[start:start+256];lower=np.tile(bounds[0]-epsilon,(len(y),1));upper=np.tile(bounds[1]+epsilon,(len(y),1))
            lower[:,1]=y-epsilon;upper[:,1]=y+epsilon
            tree=self.mesh.triangles_tree
            if hasattr(tree,'intersection_v'):
                ids,counts=tree.intersection_v(np.ascontiguousarray(lower),np.ascontiguousarray(upper))
                owners=np.repeat(np.arange(len(y)),counts.astype(int))
            else:
                groups=[list(tree.intersection(np.r_[a,b])) for a,b in zip(lower,upper)]
                ids=np.asarray([i for group in groups for i in group],int)
                owners=np.repeat(np.arange(len(y)),[len(group) for group in groups])
            if not len(ids):continue
            tri=self.triangles[np.asarray(ids,int)];plane=y[owners]
            coplanar=(np.abs(tri[:,:,1]-plane[:,None])<=epsilon).all(1)
            ambiguous[start+owners[coplanar]]=True
            first=tri;second=np.roll(tri,-1,axis=1);dy=second[:,:,1]-first[:,:,1]
            crossing=(np.minimum(first[:,:,1],second[:,:,1])<=plane[:,None]+epsilon)&(np.maximum(first[:,:,1],second[:,:,1])>=plane[:,None]-epsilon)
            sloping=np.abs(dy)>epsilon
            fraction=np.zeros_like(dy);np.divide(plane[:,None]-first[:,:,1],dy,out=fraction,where=sloping)
            fraction=np.clip(fraction,0,1);points=first+(second-first)*fraction[:,:,None]
            edge_owners=np.repeat(start+owners,3)
            def include(values,mask):
                selected=edge_owners[mask.reshape(-1)];xz=values[:,:,[0,2]].reshape(-1,2)[mask.reshape(-1)]
                for axis in range(2):
                    np.minimum.at(lo[:,axis],selected,xz[:,axis]);np.maximum.at(hi[:,axis],selected,xz[:,axis])
            include(points,crossing&sloping)
            # A horizontal edge contributes both endpoints, conservatively.
            flat=crossing&~sloping
            include(first,flat);include(second,flat)
        valid=np.isfinite(lo).all(1)&np.isfinite(hi).all(1)&((hi-lo)>epsilon*2).all(1)&~ambiguous
        return lo,hi,valid,ambiguous

    def outside(self, points):
        points=np.asarray(points,float);assert points.ndim==2 and points.shape[1]==3 and np.isfinite(points).all()
        result=np.zeros(len(points),bool)
        if not len(points) or not self.volumetric:
            self.last_query={'points':len(points),'valid_planes':0,'proven_outside_points':0,'fallback':'empty query or non-volumetric complete mesh'}
            return result
        heights,inverse=np.unique(points[:,1],return_inverse=True);lo=np.empty((len(heights),2));hi=np.empty_like(lo);valid=np.zeros(len(heights),bool);missing=[]
        for at,y in enumerate(heights):
            cached=self.cache.get(float(y))
            if cached is None:missing.append(at)
            else:lo[at],hi[at],valid[at]=cached
        ambiguous=0
        if missing:
            lower,upper,usable,coplanar=self._sections(heights[missing]);ambiguous=int(coplanar.sum())
            lo[missing]=lower;hi[missing]=upper;valid[missing]=usable
            if len(self.cache)+len(missing)>self.cache_planes:self.cache.clear()
            for at,a,b,okay in zip(missing,lower,upper,usable):
                if len(self.cache)<self.cache_planes:self.cache[float(heights[at])]=(a.copy(),b.copy(),bool(okay))
        xz=points[:,[0,2]]
        result=valid[inverse]&((xz<lo[inverse]-self.epsilon)|(xz>hi[inverse]+self.epsilon)).any(1)
        self.last_query={'points':len(points),'distinct_planes':len(heights),'new_planes':len(missing),'valid_planes':int(valid.sum()),'new_coplanar_fallbacks':ambiguous,'proven_outside_points':int(result.sum())}
        return result
