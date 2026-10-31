"""Local authoring clearance against the retained native Human head.

This is a bind-space baseline. Real native face-control and posed client checks
remain separate; it is never a substitute for the RL head's morph gate.
"""
from pathlib import Path
import hashlib
import numpy as np
import trimesh
import headref,rlglb,paths

class NativeHeadSurface:
    def __init__(self,P,N,T):
        self.P=np.asarray(P,float);self.N=headref.unit(N);self.T=np.asarray(T,int)
        assert np.isfinite(self.P).all() and (np.linalg.norm(self.N,axis=1)>.99).all()
        self.mesh=trimesh.Trimesh(self.P,self.T,process=False)
        self.source={}

    @classmethod
    def from_current_head(cls,head):
        path=Path(paths.body_glb(head.sex));digest=hashlib.sha256(path.read_bytes()).hexdigest()
        cut=head.gltf['asset']['extras']['rlHead']['bodyCut'];assert cut['bodySHA256']==digest
        g,b=rlglb.read(str(path));globals_=rlglb.globals_of(g);Ps=[];Ns=[];Ts=[];offset=0
        for node_index,node in enumerate(g['nodes']):
            if 'mesh' not in node:continue
            mesh=g['meshes'][node['mesh']];name=mesh.get('name')
            if name not in ['body','scalp']:continue
            assert np.allclose(globals_[node_index],np.eye(4),atol=1e-6),'Native bind-space transform changed'
            for primitive in mesh['primitives']:
                P=rlglb.accessor(g,b,primitive['attributes']['POSITION']);N=rlglb.accessor(g,b,primitive['attributes']['NORMAL'])
                T=rlglb.accessor(g,b,primitive['indices'],normalize=False).astype(int).reshape(-1,3)
                if name=='body':T=T[np.concatenate([np.arange(start,start+length) for start,length in cut['hiddenBodyTriangles']])]
                used,inverse=np.unique(T,return_inverse=True);Ps.append(P[used]);Ns.append(N[used]);Ts.append(inverse.reshape(-1,3)+offset);offset+=len(used)
        result=cls(np.vstack(Ps),np.vstack(Ns),np.vstack(Ts))
        result.source={'native_body_sha256':digest,'native_head_vertices':len(result.P),'native_head_triangles':len(result.T),'baseline':'unposed bodyCut head plus native scalp, scoped through triangle indices'}
        return result

    def signed(self,X):
        X=np.asarray(X,float);chunks=[trimesh.proximity.closest_point(self.mesh,X[start:start+512]) for start in range(0,len(X),512)]
        cp,dist,tri=(np.concatenate([row[index] for row in chunks],axis=0) for index in range(3))
        bc=headref.barycentric(cp,self.P[self.T[tri,0]],self.P[self.T[tri,1]],self.P[self.T[tri,2]])
        normal=headref.unit((self.N[self.T[tri]]*bc[:,:,None]).sum(1));sign=np.sign(((X-cp)*normal).sum(1));sign[sign==0]=1
        return sign*dist,cp,normal

    def push_out(self,P,margin=.0028,max_shift_mm=14):
        """Move contacting points only; preserve every already-clear row exactly."""
        original=np.asarray(P);Q=original.astype(float,copy=True);initial,_,_=self.signed(Q);active=initial<margin
        for _ in range(8):
            sd,cp,normal=self.signed(Q);bad=sd<margin-1e-8
            if not bad.any():break
            Q[bad]=cp[bad]+normal[bad]*(margin+.0002)
            assert np.linalg.norm(Q-original,axis=1).max()*1000<=max_shift_mm,'Native contact correction exceeded its local displacement limit'
        final,_,_=self.signed(Q)
        assert not (final<margin-1e-8).any(),'Unresolved native head contact'
        assert np.array_equal(Q[~active],original[~active]),'Clear native-head points must remain unchanged'
        displacement=np.linalg.norm(Q-original,axis=1)*1000
        return Q,{'contact_vertices':int(active.sum()),'maximum_shift_mm':float(displacement.max()),'minimum_clearance_mm':float(final.min()*1000),'initial_minimum_mm':float(initial.min()*1000),'noncontact_positions_exact':True,**self.source}
