"""Re-skin the regenerated Human hands without changing geometry or the rig.

Finger tips come from the welded surface, not the (older, longer) rig. Lanes
through those tips separate the four fingers even where the sculpt bridges
them. Smooth knuckle bands bind the free fingers to their existing joint
pivots; the palm and cuff keep their old weights. Only JOINTS_0/WEIGHTS_0
bytes are patched, retaining the u8 joint accessor and every other buffer.
"""
from __future__ import annotations
import argparse, json, struct
from pathlib import Path
import numpy as np
import equipment_authoring as ea
import race_hands as rh


def smoothstep(lo, hi, value):
    t = np.clip((value-lo)/(hi-lo), 0, 1)
    return t*t*(3-2*t)


def hand_weights(p, faces, joints, weights, names, origins, side):
    hand = names.index('hand_'+side)
    old = ((joints == hand)*weights).sum(1)
    eligible = old > .5
    hand_faces, wrist, axis = rh.human_hand({'POSITION':p,'faces':faces},origins,side)
    label, own, segmentation = rh.geodesic_fingers(p, hand_faces, wrist, axis, np.array([0.,0.,1.]))
    tips = np.array(segmentation['tips'])
    outward = (p-wrist)@axis
    tip_outward = (tips-wrist)@axis
    dense = np.zeros((len(p),len(names)))
    np.add.at(dense,(np.arange(len(p))[:,None],joints),weights)
    # Four lanes, sorted thumb to little finger by the sculpt's tip depth.
    roots = np.array([origins[f'{finger}_01_{side}'] for finger in rh.FINGERS])
    # The tips are more reliable lateral centres than the longer donor rig.
    lane = np.abs(p[:,None,2]-tips[None,1:,2])
    finger = lane.argmin(1)+1
    # Thumb has a separate ray from its first joint to its tip. A nearest-ray
    # decision separates its free part; smooth blending seats it in the palm.
    ray = tips[0]-roots[0]; ray_length=np.linalg.norm(ray); ray/=ray_length
    thumb_t = (p-roots[0])@ray
    thumb_dist = np.linalg.norm(p-(roots[0]+np.clip(thumb_t,0,ray_length)[:,None]*ray),axis=1)
    thumb_region = (thumb_dist < .024) & (p[:,2] > tips[1,2]+.012)
    finger[thumb_region]=0
    proposal = np.zeros_like(dense); proposal[:,hand]=1
    for k,name in enumerate(rh.FINGERS):
        region = eligible & (finger==k) & (label>0)
        ids = [names.index(f'{name}_{j:02d}_{side}') for j in (1,2,3)]
        if k==0:
            coordinate=thumb_t
            starts=np.array([(origins[f'{name}_{j:02d}_{side}']-roots[k])@ray for j in (1,2,3)])
            palm=smoothstep(.007,.030,coordinate)
        else:
            coordinate=outward
            starts=np.array([(origins[f'{name}_{j:02d}_{side}']-wrist)@axis for j in (1,2,3)])
            palm=smoothstep(starts[0]-.018,starts[0]+.007,coordinate)
        second=smoothstep(starts[1]-.010,starts[1]+.010,coordinate)
        third=smoothstep(starts[2]-.010,starts[2]+.010,coordinate)
        proposal[region,hand]=1-palm[region]
        proposal[region,ids[0]]=palm[region]*(1-second[region])
        proposal[region,ids[1]]=palm[region]*(second[region]-third[region])
        proposal[region,ids[2]]=palm[region]*third[region]
    proposal=rh.smooth_weights(p,hand_faces,proposal,passes=12)
    changed = eligible & (label>0) & (proposal[:,hand]<.999)
    dense[changed,hand]=0
    dense[changed]+=proposal[changed]*old[changed,None]
    order=np.argsort(-dense,axis=1,kind='stable')[:,:4]
    values=np.take_along_axis(dense,order,axis=1); values/=values.sum(1,keepdims=True)
    result_j=joints.copy(); result_w=weights.copy()
    result_j[changed]=order[changed]; result_w[changed]=values[changed]
    return result_j,result_w,{'side':side,'changedVertices':int(changed.sum()),'segmentation':segmentation,
      'fingerVertices':{name:int((np.isin(order,[names.index(f'{name}_{j:02d}_{side}') for j in (1,2,3)]) & (values>1e-4)).any(1).sum()) for name in rh.FINGERS}}


def patch_accessor(d, binary, index, values):
    a=d['accessors'][index]; v=d['bufferViews'][a['bufferView']]
    width=values.shape[1]*values.dtype.itemsize
    start=v.get('byteOffset',0)+a.get('byteOffset',0); stride=v.get('byteStride',width)
    for row in range(len(values)):
        offset=start+row*stride; binary[offset:offset+width]=values[row].tobytes()


def reskin(source, target):
    source,target=Path(source),Path(target)
    d,b=ea.read_glb(source); edited=bytearray(b)
    names=[d['nodes'][i]['name'] for i in d['skins'][0]['joints']]
    world=ea.global_matrices(d); origins={name:world[i][:3,3] for name,i in zip(names,d['skins'][0]['joints'])}
    if source.resolve()==target.resolve():
        raise ValueError('Use a separate output; the source must remain available for verification')
    finger_ids={i for i,name in enumerate(names) if name.startswith(('thumb_','index_','middle_','ring_','pinky_'))}
    reports=[]; groups={}
    for mesh in d['meshes']:
        for prim in mesh['primitives']:
            a=prim['attributes']
            if not {'JOINTS_0','WEIGHTS_0'} <= a.keys(): continue
            key=tuple(a[k] for k in ('POSITION','JOINTS_0','WEIGHTS_0'))
            groups.setdefault(key,[]).append(ea.accessor_array(d,b,prim['indices']).reshape(-1,3))
    for (pi,ji,wi),f in groups.items():
        p=ea.accessor_array(d,b,pi); j=ea.accessor_array(d,b,ji).copy(); w=ea.accessor_array(d,b,wi).copy()
        if np.any(np.isin(j,list(finger_ids)) & (w>1e-5)):
            raise ValueError('Source already has finger weights; use the unskinned regenerated Human input')
        if not any(((j==names.index('hand_'+s))*w).sum(1).max()>.5 for s in ('r','l')): continue
        assert d['accessors'][ji]['componentType']==5121
        for side in ('r','l'):
            if not (((j==names.index('hand_'+side))*w).sum(1)>.5).any(): continue
            j,w,report=hand_weights(p,np.vstack(f),j,w,names,origins,side); reports.append(report)
        patch_accessor(d,edited,ji,j.astype('u1')); patch_accessor(d,edited,wi,w.astype('<f4'))
    # Preserve the original GLB JSON chunk, including image/geometry metadata.
    raw=bytearray(source.read_bytes()); offset=12
    while offset<len(raw):
        length,kind=struct.unpack_from('<II',raw,offset)
        if kind==0x004E4942: raw[offset+8:offset+8+length]=edited
        offset+=8+length
    target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('source',type=Path); parser.add_argument('target',type=Path)
    args=parser.parse_args(); print(json.dumps(reskin(args.source,args.target),indent=2))

if __name__=='__main__': main()