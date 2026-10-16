"""Explicit physical limb intent, independent of legacy semantic bone labels."""
import numpy as np
from scipy.spatial.transform import Rotation


def validate_limb_chains(asset,chains):
    """Reject duplicate joints and sibling helpers masquerading as a serial chain.

    The caller must review which joint is the hip, stifle, hock or wrist.
    Hierarchy alone cannot determine that anatomical correspondence.
    """
    for limb,chain in chains.items():
        if len(chain)<3 or len(set(chain))!=len(chain):
            raise ValueError('A physical limb needs at least three distinct ordered joints')
        if any(n not in asset.joints for n in chain):
            raise ValueError('Physical limb joints must belong to the active skin')
        for parent,child in zip(chain[:-1],chain[1:]):
            node=int(asset.parent[child])
            while node>=0 and node!=parent:node=int(asset.parent[node])
            if node!=parent:raise ValueError('A sibling heel helper is not a serial wrist or hock')


def body_rotation_delta(asset,world,node):
    """Cancel the native rest orientation rather than copying local quaternions."""
    return Rotation.from_matrix(world[...,node,:3,:3]).as_matrix()@Rotation.from_matrix(asset.world_rest[node,:3,:3]).as_matrix().T


def limb_segment_directions(asset,world,chains,body_nodes):
    """Unit segment vectors in each posed, rest-cancelled torso frame.

    Segment lengths remain native. A model with another wrist subdivision
    needs an explicit adapter; matching names or a shared paw endpoint is
    insufficient. This describes a fitted model's 3D pose, not hidden video
    joint measurements.
    """
    result={}
    for limb,chain in chains.items():
        points=np.take(world,chain,axis=-3)[...,:3,3]
        vectors=np.diff(points,axis=-2);length=np.linalg.norm(vectors,axis=-1,keepdims=True)
        if np.any(length<1e-10):raise ValueError('Review zero-length anatomical limb segments')
        delta=body_rotation_delta(asset,world,body_nodes[limb])
        result[limb]=np.einsum('...ji,...kj->...ki',delta,vectors/length)
    return result


def hinge_branch_residual(angles,signs,minimum_degrees=3.):
    """A smooth bend-side guard across the +/-pi representation boundary.

    Sine selects the anatomical half-turn without asking a nearly folded
    hinge to unwind through straight because atan2 changed representation.
    The margin also avoids complete straightening or folding onto itself.
    """
    return np.minimum(0,np.sin(angles)*np.asarray(signs)-np.sin(np.deg2rad(minimum_degrees)))
