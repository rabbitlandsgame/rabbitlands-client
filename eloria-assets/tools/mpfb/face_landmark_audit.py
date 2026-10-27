"""Measure final MPFB GLB face landmarks for multi-view reference registration.

Landmarks are model-space evidence, not a face-recognition result. Eye corners
come from actual welded eyelid boundary loops where available; feature proxies
are explicitly recorded. No mesh, rest, skin or texture is modified.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from fit_canonical import Glb, node_worlds


def boundary_loops(points, triangles):
    _, first, inverse = np.unique(np.round(points*1e6).astype(np.int64),axis=0,
                                  return_index=True,return_inverse=True)
    counts={}
    for tri in inverse[triangles]:
        for a,b in zip(tri,np.roll(tri,-1)):
            if a==b: continue
            edge=tuple(sorted((int(a),int(b))))
            counts[edge]=counts.get(edge,0)+1
    adj={}
    for (a,b),count in counts.items():
        if count==1: adj.setdefault(a,[]).append(b);adj.setdefault(b,[]).append(a)
    seen=set();loops=[]
    for start in adj:
        if start in seen: continue
        pending=[start];component=set()
        while pending:
            current=pending.pop()
            if current in component: continue
            component.add(current);pending.extend(adj[current])
        seen.update(component)
        if not all(len(adj[v])==2 for v in component): continue
        loops.append(first[np.array(sorted(component))])
    return loops


def audit(path, fit_path):
    glb=Glb(path);d=glb.doc;world=node_worlds(d)
    node=next(n for n in d['nodes'] if n.get('name')=='body')
    primitive=d['meshes'][node['mesh']]['primitives'][0]
    points=glb.read(primitive['attributes']['POSITION']).astype(float)
    head=np.linalg.inv(world['Head'])@world['body']
    local=points@head[:3,:3].T+head[:3,3]
    triangles=glb.read(primitive['indices']).reshape(-1,3)
    used=np.unique(triangles);tree=cKDTree(local[used])
    frame=json.loads(Path(fit_path).read_text())['face_frame_head_local']
    eye_node=next(n for n in d['nodes'] if n.get('name')=='eyes')
    eye_primitive=d['meshes'][eye_node['mesh']]['primitives'][0]
    eye_points=glb.read(eye_primitive['attributes']['POSITION']).astype(float)
    eye_transform=np.linalg.inv(world['Head'])@world['eyes']
    eye_points=eye_points@eye_transform[:3,:3].T+eye_transform[:3,3]
    eye_uv=glb.read(eye_primitive['attributes']['TEXCOORD_0'])
    material=d['materials'][eye_primitive['material']]['pbrMetallicRoughness']
    image=d['images'][d['textures'][material['baseColorTexture']['index']]['source']]
    view=d['bufferViews'][image['bufferView']];raw=glb.binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
    atlas=np.asarray(Image.open(io.BytesIO(raw)).convert('RGBA'))/255.
    pixel=np.column_stack((np.clip(eye_uv[:,0]*atlas.shape[1],0,atlas.shape[1]-1),np.clip(eye_uv[:,1]*atlas.shape[0],0,atlas.shape[0]-1))).astype(int)
    samples=atlas[pixel[:,1],pixel[:,0]];dark=samples[:,:3]@np.array([.2126,.7152,.0722])
    loops=boundary_loops(local,triangles)
    landmarks={};types={};vertex_ids={}
    def vector(name,value,kind):
        landmarks[name]=np.asarray(value).tolist();types[name]=kind
    def actual(name,index,kind):
        vector(name,local[index],kind);vertex_ids[name]=int(index)
    def nearest(name,value,kind='nearest surface feature proxy'):
        _,i=tree.query(value);actual(name,used[i],kind)
    eye_y=float(frame['eye_y']);eye_z=float(frame['eye_z']);mouth=np.array(frame['mouth'])
    for sign,label in [(-1,'left'),(1,'right')]:
        center=np.array(frame['eye_'+label]);vector('eye_center_'+label,center,'measured fitted eyeball center')
        pupil=(eye_points[:,0]*sign>0)&(samples[:,3]>.5)&(dark<.12)&(eye_points[:,2]>center[2]+.004)
        image_point=eye_points[pupil].mean(0) if pupil.any() else center+np.array([0,0,.011])
        vector('eye_image_'+label,image_point,'opaque forward pupil geometry; clear cornea excluded' if pupil.any() else 'front-iris pole proxy')
        candidates=[ids for ids in loops if np.linalg.norm(local[ids].mean(0)-center)<.035]
        if candidates:
            ids=min(candidates,key=lambda ids:np.linalg.norm(local[ids].mean(0)-center))
            side=local[ids,0]*sign
            actual('eye_outer_'+label,ids[np.argmax(side)],'actual welded eyelid aperture')
            actual('eye_inner_'+label,ids[np.argmin(side)],'actual welded eyelid aperture')
            actual('eye_top_'+label,ids[np.argmax(local[ids,1])],'actual welded eyelid aperture')
            actual('eye_bottom_'+label,ids[np.argmin(local[ids,1])],'actual welded eyelid aperture')
        else:
            for part,x in [('inner',-.014),('outer',.014)]:
                nearest('eye_'+part+'_'+label,center+np.array([sign*x,0,.004]))
            for part,y in [('top',.006),('bottom',-.006)]:
                nearest('eye_'+part+'_'+label,center+np.array([0,y,.006]))
        for part,x in [('inner',-.012),('outer',.018)]:
            nearest('brow_'+part+'_'+label,center+np.array([sign*x,.014,.009]))
    vector('mouth_center',mouth,'mean actual MPFB lip ownership group')
    bounds=frame.get('mouth_bounds')
    for sign,label in [(-1,'left'),(1,'right')]:
        x=bounds[0 if sign<0 else 1][0] if bounds else sign*.027
        nearest('mouth_'+label,[x,mouth[1],mouth[2]-.006])
        nearest('nose_ala_'+label,[sign*.013,eye_y-.036,mouth[2]+.002])
        nearest('jaw_'+label,[sign*.058,mouth[1]-.016,mouth[2]-.040])
    nose=used[(abs(local[used,0])<.017)&(local[used,1]>mouth[1]+.015)&(local[used,1]<eye_y-.012)]
    actual('nose_tip',nose[np.argmax(local[nose,2])],'central face maximum projection')
    nearest('nasion',[0,eye_y-.003,eye_z+.012])
    nearest('nose_bridge',[0,eye_y-.020,eye_z+.024])
    nearest('cupid_bow',[0,mouth[1]+.004,mouth[2]+.008])
    nearest('lower_lip',[0,mouth[1]-.004,mouth[2]+.010])
    nearest('upper_lip_profile',[0,mouth[1]+.003,mouth[2]+.010])
    nearest('lower_lip_profile',[0,mouth[1]-.005,mouth[2]+.011])
    nearest('subnasale',[0,mouth[1]+.014,mouth[2]+.002])
    chin=used[(abs(local[used,0])<.020)&(local[used,1]<mouth[1]-.016)&(local[used,1]>mouth[1]-.060)&(local[used,2]>mouth[2]-.016)]
    lowest=local[chin,1].min()
    chin_band=chin[local[chin,1]<lowest+.001]
    vector('chin',local[chin_band].mean(0),'mean symmetric front lower-chin extent; avoids left/right tie bias')
    vector('chin_profile',landmarks['chin'],'same lower-chin surface extent')
    nearest('forehead',[0,eye_y+.047,eye_z-.005])
    for sign in [-1,1]:
        label='left' if sign<0 else 'right'
        nearest('ear_tragus_'+label,[sign*.076,eye_y-.010,eye_z-.038])
        nearest('ear_top_'+label,[sign*.083,eye_y+.011,eye_z-.047])
        nearest('ear_lobe_'+label,[sign*.074,eye_y-.040,eye_z-.036])
    return {'source':str(path),'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'coordinate_system':'canonical Head rest-local metres: X right, Y up, Z forward',
            'landmarks':landmarks,'methods':types,'vertex_ids':vertex_ids,
            'closed_boundary_loop_count':len(loops),
            'eye_aperture_loops':{label:{'width_m':abs(landmarks['eye_outer_'+label][0]-landmarks['eye_inner_'+label][0]),
                                       'height_m':landmarks.get('eye_top_'+label,[0,0,0])[1]-landmarks.get('eye_bottom_'+label,[0,0,0])[1]}
                                  for label in ['left','right']},
            'limitations':['Surface proxies are measured geometric anchors, not semantic ground truth.',
                           'Painted reference landmarks require manual visual registration and uncertainty bounds.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True,help='Directory with male/female fitted prototype subfolders')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result={'schema':'RL MPFB measured face anchors 1','models':{}}
    for sex in ['male','female']:
        result['models'][sex]=audit(args.root/sex/f'luminous_{sex}.glb',args.root/sex/'fit.json')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({s:{k:v for k,v in r.items() if k in ['closed_boundary_loop_count','eye_aperture_loops']} for s,r in result['models'].items()}))


if __name__=='__main__': main()
