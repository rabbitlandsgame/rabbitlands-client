"""Anatomical binding for reconstructed trouser linings and source cut panels."""
import numpy as np


def smoothstep(value, low, high):
    t = np.clip((value-low)/(high-low), 0., 1.)
    return t*t*(3.-2.*t)


def leg_lining_weights(points, rig):
    """A continuous seat/knee field for lining reshaped inside the artwork.

    The new lining has moved away from the source body surface: copying the
    former weights can give a high trouser cuff the wearer's toe-off motion.
    The centre seat blends continuously across x=0 instead of switching legs.
    """
    p=np.asarray(points);fit=rig.fit_scale
    dense=np.zeros((len(p),len(rig.joint_names)))
    hip_y=np.mean([rig.origin('thigh_'+s)[1] for s in ('l','r')])
    knee_y=np.mean([rig.origin('calf_'+s)[1] for s in ('l','r')])
    hip=smoothstep(p[:,1],hip_y-.18*fit,hip_y+.01*fit)
    dense[:,rig.joint_names.index('pelvis')]=hip
    seat=smoothstep(p[:,1],hip_y-.16*fit,hip_y-.07*fit)
    left=smoothstep(p[:,0],-.065*fit,.065*fit)*seat+(p[:,0]>=0)*(1.-seat)
    shin=1.-smoothstep(p[:,1],knee_y-.085*fit,knee_y+.085*fit)
    for side,share in [('l',left),('r',1.-left)]:
        share=share*(1.-hip)
        dense[:,rig.joint_names.index('thigh_'+side)]=share*(1.-shin)
        dense[:,rig.joint_names.index('calf_'+side)]=share*shin
    j=np.argsort(-dense,axis=1)[:,:4]
    w=np.take_along_axis(dense,j,axis=1)
    w/=np.maximum(w.sum(axis=1,keepdims=True),1e-12)
    return j.astype(np.uint16),w


def constrain_legs(points, joints, weights, rig):
    """Keep adjacency smoothing within the anatomical reach of each joint.

    Long source triangles can connect the calf directly to a belt vertex.
    A topology-only average then gives that belt calf motion. Taper those
    impossible influences out above the knee; preserve the inherited blends
    inside their joint regions and normalize the remaining influences.
    """
    w=weights.copy();y=points[:,1];fit=rig.fit_scale
    knee=np.mean([rig.origin('calf_'+s)[1] for s in ('l','r')])
    hip=np.mean([rig.origin('thigh_'+s)[1] for s in ('l','r')])
    for slot in range(4):
        for side in ('l','r'):
            own=joints[:,slot]==rig.joint_names.index('calf_'+side)
            w[own,slot]*=1.-smoothstep(y[own],knee+.08*fit,knee+.25*fit)
        own=joints[:,slot]==rig.joint_names.index('pelvis')
        w[own,slot]*=smoothstep(y[own],knee-.02*fit,hip-.16*fit)
    empty=w.sum(axis=1)<1e-8
    if empty.any():
        j,w0=leg_lining_weights(points[empty],rig);joints=joints.copy();joints[empty]=j;w[empty]=w0
    w/=w.sum(axis=1,keepdims=True)
    return joints,w
