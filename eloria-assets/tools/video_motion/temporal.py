"""Batched native FK and exact skin features for temporal fitting.

These calculate world transforms only. Use ActionRig.pose for local T/Q export.
"""
import numpy as np
from scipy.spatial.transform import Rotation


def action_worlds(rig,parameters):
    p=np.asarray(parameters,float)
    if p.ndim!=2 or p.shape[1]!=rig.dof or not np.isfinite(p).all():
        raise ValueError('Batched action parameters must be finite rows of native controls')
    a=rig.asset;b=rig.base;n=len(p);world=np.broadcast_to(a.world_rest,(n,a.n,4,4)).copy()
    delta=Rotation.from_rotvec((p[:,:len(b.controls),None]*rig.axis).reshape(-1,3)).as_matrix().reshape(n,len(b.controls),3,3)
    for node in b.active_order:
        parent=int(a.parent[node]);local=b.local_rest[node]
        posed=np.broadcast_to(local,(n,4,4)).copy() if parent<0 else world[:,parent]@local
        if node==b.height_node:posed[:,:3,3]+=p[:,-1,None]*rig.up
        if node in b.control_nodes:posed[:,:3,:3]=delta[:,b.control_nodes[node]]@posed[:,:3,:3]
        world[:,node]=posed
    for anchor,upper in b.scapula_offsets:
        parent=int(a.parent[anchor]);world[:,anchor]=(np.broadcast_to(b.local_rest[anchor],(n,4,4)) if parent<0 else world[:,parent]@b.local_rest[anchor])
    for helper,foot in b.paw_followers:world[:,helper]=world[:,foot]@b.follow_rest[foot]
    if rig.jaw_arc and rig.jaw_index is not None:
        jaw=rig.roles['jaw'];hinge=rig.roles['jaw_hinge'];d=Rotation.from_rotvec(p[:,rig.jaw_index,None]*rig.axis).as_matrix();shift=world[:,hinge,:3,3]+np.einsum('nab,nb->na',d,world[:,jaw,:3,3]-world[:,hinge,:3,3])-world[:,jaw,:3,3];desc={jaw}
        for node in a.order:
            if a.parent[node] in desc:desc.add(node)
        world[:,:,:3,3][:,sorted(desc)]+=shift[:,None,:]
        for name in rig.profile.get('action_jaw_follow_subtrees',[]):
            node=a.name_to_id[name];desc={node}
            for child in a.order:
                if a.parent[child] in desc:desc.add(child)
            ids=sorted(desc);pivot=world[:,hinge,:3,3];world[:,:,:3,3][:,ids]=np.einsum('nab,nvb->nva',d,world[:,:,:3,3][:,ids]-pivot[:,None,:])+pivot[:,None,:];world[:,:,:3,:3][:,ids]=np.einsum('nab,nvbc->nvac',d,world[:,:,:3,:3][:,ids])
    for k,(node,desc,axis) in enumerate(rig.extra_pose_nodes):
        d=Rotation.from_rotvec(p[:,len(b.controls)+k,None]*axis).as_matrix();pivot=world[:,node,:3,3].copy();world[:,:,:3,3][:,desc]=np.einsum('nab,nvb->nva',d,world[:,:,:3,3][:,desc]-pivot[:,None,:])+pivot[:,None,:];world[:,:,:3,:3][:,desc]=np.einsum('nab,nvbc->nvac',d,world[:,:,:3,:3][:,desc])
    d=Rotation.from_rotvec(p[:,-2,None]*rig.forward).as_matrix();pivot=world[:,rig.roles['hips'],:3,3].copy();ids=rig.roll_nodes;world[:,:,:3,3][:,ids]=np.einsum('nab,nvb->nva',d,world[:,:,:3,3][:,ids]-pivot[:,None,:])+pivot[:,None,:];world[:,:,:3,:3][:,ids]=np.einsum('nab,nvbc->nvac',d,world[:,:,:3,:3][:,ids])
    return world


class SkinFeatures:
    """Exact linear-blend points and centroids, with any number of influences."""
    def __init__(self,asset):
        self.asset=asset;pieces=[];slots=max(p.get('weights',np.ones((1,1))).shape[1] for p in asset.parts)
        for part in asset.parts:
            if 'joints' in part:
                nodes=part['nodes'][part['joints']];bind=np.einsum('vkij,vj->vki',part['inverse_bind'][part['joints']],part['position']);weights=part['weights']
            else:nodes=np.full((len(part['position']),1),part['node'],int);bind=part['position'][:,None,:];weights=np.ones(nodes.shape)
            pieces.append((np.pad(nodes,((0,0),(0,slots-nodes.shape[1]))),np.pad(bind,((0,0),(0,slots-bind.shape[1]),(0,0))),np.pad(weights,((0,0),(0,slots-weights.shape[1])))))
        self.nodes=np.concatenate([p[0] for p in pieces]);self.bind=np.concatenate([p[1] for p in pieces]);self.weights=np.concatenate([p[2] for p in pieces])
    def points(self,world,ids=None):
        ids=np.arange(len(self.nodes)) if ids is None else np.asarray(ids,int);out=np.zeros((len(world),len(ids),3))
        for k in range(self.weights.shape[1]):
            out+=np.einsum('nvab,vb->nva',world[:,self.nodes[ids,k],:3,:],self.bind[ids,k])*self.weights[ids,k][None,:,None]
        return out
    def centroid_coefficients(self,ids):
        ids=np.asarray(ids,int)
        if ids.ndim!=1 or len(ids)==0:raise ValueError('A centroid needs physical vertex IDs')
        coeff=np.zeros((self.asset.n,4))
        for k in range(self.weights.shape[1]):np.add.at(coeff,self.nodes[ids,k],self.bind[ids,k]*self.weights[ids,k,None]/len(ids))
        return coeff
    @staticmethod
    def centroid(world,coefficients):
        return np.einsum('njab,jb->na',world[:,:,:3,:],coefficients)


def motion_quality(asset,clip,fps=48):
    """Physical trajectory diagnostics at review cadence, not a contact verdict."""
    from .asset import digest
    times=np.linspace(0,asset.duration(clip),round(asset.duration(clip)*fps)+1)
    t,q=asset.sample(clip,times);world=np.array([asset.world(ti,qi) for ti,qi in zip(t,q)]);surface=np.array([asset.skin(w) for w in world]);height=asset.height
    velocity=np.linalg.norm(np.diff(surface,axis=0),axis=2)*fps/height
    acceleration=np.linalg.norm(np.diff(surface,n=2,axis=0),axis=2)*fps**2/height
    jerk=np.linalg.norm(np.diff(surface,n=3,axis=0),axis=2)*fps**3/height
    index=np.unravel_index(acceleration.argmax(),acceleration.shape)
    return {'model_sha256':digest(asset.path),'clip':clip,'sampling_fps':fps,
            'maximum_surface_speed_heights_per_second':float(velocity.max()),
            'maximum_surface_acceleration_heights_per_second2':float(acceleration.max()),
            'surface_acceleration_p99':float(np.quantile(acceleration,.99)),
            'surface_jerk_rms_heights_per_second3':float(np.sqrt(np.mean(jerk**2))),
            'maximum_acceleration_time_seconds':float(times[index[0]+1]),
            'maximum_acceleration_vertex_id':int(index[1]),
            'policy':'Compare the same physical vertices and original timestamps. These diagnostics do not replace normal-speed visual review or contact validation.'}
