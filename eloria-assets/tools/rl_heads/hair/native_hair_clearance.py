"""Local authoring clearance against the retained native Human head.

This is a bind-space baseline. Real native face-control and posed client checks
remain separate; it is never a substitute for the RL head's morph gate.
"""
from pathlib import Path
import hashlib
import numpy as np
import trimesh
import headref,rlglb,paths

class NativeFaceGuardFailure(ValueError):
    def __init__(self,message,points,receipt):
        super().__init__(message);self.points=points.copy();self.receipt=receipt

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
            separation=Q[bad]-cp[bad];distance=np.linalg.norm(separation,axis=1)
            direction=headref.unit(separation)*np.where(sd[bad]<0,-1.,1.)[:,None]
            direction[distance<1e-10]=normal[bad][distance<1e-10]
            Q[bad]=cp[bad]+direction*(margin+.0002)
            assert np.linalg.norm(Q-original,axis=1).max()*1000<=max_shift_mm,'Native contact correction exceeded its local displacement limit'
        final,_,_=self.signed(Q)
        assert not (final<margin-1e-8).any(),'Unresolved native head contact'
        assert np.array_equal(Q[~active],original[~active]),'Clear native-head points must remain unchanged'
        displacement=np.linalg.norm(Q-original,axis=1)*1000
        return Q,{'contact_vertices':int(active.sum()),'maximum_shift_mm':float(displacement.max()),'minimum_clearance_mm':float(final.min()*1000),'initial_minimum_mm':float(initial.min()*1000),'noncontact_positions_exact':True,**self.source}

    def push_faces(self,P,T,ranges,parts=('shell','backing'),margin=.0028,
                   minimum_edge_mm=5,max_shift_mm=14,iterations=12):
        """Opt-in local face support; never moves painted exterior vertices.

        Probes match the native fixture gate. Each changed vertex records the
        limiting face/probe that drove it; over-limit or unresolved proposals
        raise with the private diagnostic points and receipt attached.
        """
        assert set(parts)<=set(['shell','backing'])
        original=np.asarray(P);Q=original.astype(float,copy=True);T=np.asarray(T,int)
        selected=[];labels={}
        for part in parts:
            if part not in ranges:continue
            start,end=ranges[part]
            for face in np.flatnonzero((T>=start).all(1)&(T<end).all(1)):
                selected.append(face);labels[int(face)]=part
        selected=np.array(selected,int)
        bary=np.array([[1/3,1/3,1/3],[.5,.5,0],[.5,0,.5],[0,.5,.5]])
        history=[];touched=np.zeros(len(Q),bool);clearance=float('inf')
        receipt={'parts':list(parts),'margin_mm':margin*1000,'minimum_edge_mm':minimum_edge_mm,
                 'max_shift_mm':max_shift_mm,'iterations':history,'qualified':False,**self.source}
        for iteration in range(iterations+1):
            triangle=Q[T[selected]]
            lengths=np.linalg.norm(triangle-np.roll(triangle,1,axis=1),axis=2)
            active=selected[lengths.max(1)*1000>=minimum_edge_mm]
            if not len(active):break
            probes=np.einsum('pc,fcv->fpv',bary,Q[T[active]]).reshape(-1,3)
            signed,closest,normal=self.signed(probes);clearance=float(signed.min()*1000)
            bad=np.flatnonzero(signed<margin-1e-8)
            if not len(bad):break
            if iteration==iterations:
                receipt.update(passed=False,minimum_clearance_mm=clearance)
                raise NativeFaceGuardFailure('Unresolved native face probes',Q,receipt)
            separation=probes-closest;distance=np.linalg.norm(separation,axis=1)
            direction=separation*np.sign(signed)[:,None]/np.maximum(distance[:,None],1e-12)
            direction[distance<1e-10]=normal[distance<1e-10]
            correction=np.zeros_like(Q);size=np.zeros(len(Q));drivers={}
            for probe in bad:
                face=int(active[probe//4]);weights=bary[probe%4];amount=margin+.0003-signed[probe]
                field=direction[probe]*amount;scale=float(weights@weights)
                for vertex,weight in zip(T[face],weights):
                    if weight==0:continue
                    proposed=field*weight/scale;magnitude=float(np.linalg.norm(proposed))
                    if magnitude>size[vertex]:
                        correction[vertex]=proposed;size[vertex]=magnitude
                        drivers[int(vertex)]={'vertex':int(vertex),'part':labels[face],'face':face,
                            'probe':int(probe%4),'clearance_mm':float(signed[probe]*1000),
                            'correction_mm':(proposed*1000).tolist()}
            moved=size>0;proposal=Q+correction;maximum=float(np.linalg.norm(proposal-original,axis=1).max()*1000)
            history.append({'iteration':iteration,'bad_probes':len(bad),'minimum_clearance_mm':clearance,
                            'changed_vertices':int(moved.sum()),'proposal_max_shift_mm':maximum,
                            'drivers':list(drivers.values())})
            if maximum>max_shift_mm:
                receipt.update(passed=False,maximum_shift_mm=maximum)
                raise NativeFaceGuardFailure('Native face correction exceeded its local displacement limit',proposal,receipt)
            Q=proposal;touched|=moved
            # Face support may expose a different nearest native surface at a
            # corner. Re-seat only vertices of the selected hidden parts.
            ids=np.unique(T[selected]);seated,_=self.push_out(Q[ids],margin,max_shift_mm=max_shift_mm)
            touched[ids[np.linalg.norm(seated-Q[ids],axis=1)>0]]=True;Q[ids]=seated
            maximum=float(np.linalg.norm(Q-original,axis=1).max()*1000)
            if maximum>max_shift_mm:
                receipt.update(passed=False,maximum_shift_mm=maximum)
                raise NativeFaceGuardFailure('Native face/corner correction exceeded its local displacement limit',Q,receipt)
        assert np.array_equal(Q[~touched],original[~touched])
        if 'exterior' in ranges:
            start,end=ranges['exterior'];assert np.array_equal(Q[start:end],original[start:end])
        receipt.update(passed=True,minimum_clearance_mm=clearance,changed_vertices=int(touched.sum()),
                       maximum_shift_mm=float(np.linalg.norm(Q-original,axis=1).max()*1000),
                       exterior_positions_exact=True,unaffected_positions_exact=True)
        return Q,receipt
