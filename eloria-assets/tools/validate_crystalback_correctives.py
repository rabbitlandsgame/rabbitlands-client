"""Independent old/new GLB checks: all authored knots, midpoints, and off-grid poses."""
import os
os.environ['OPENBLAS_NUM_THREADS']='4'
os.environ['OMP_NUM_THREADS']='4'
import json,pathlib,sys,time
import numpy as np
from scipy.spatial.transform import Rotation
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=pathlib.Path,required=True)
parser.add_argument('--candidate',type=pathlib.Path,required=True)
parser.add_argument('--profile',type=pathlib.Path,required=True)
parser.add_argument('--report',type=pathlib.Path,required=True)
args=parser.parse_args()
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from video_motion.native_shapes import NativeShapeAsset
from video_motion.asset import accessor,digest
a=NativeShapeAsset(args.source);b=NativeShapeAsset(args.candidate);profile=json.loads(args.profile.read_text());assert digest(a.path)==profile['source_sha256'];rigid=np.array(profile['rigid_original_vertex_ids']);soft=np.setdiff1d(np.arange(len(a.vertices)),rigid);pa=a.parts[0];pb=b.parts[0];pc=b.parts[1];ap=a.d['meshes'][0]['primitives'][0];bp=b.d['meshes'][0]['primitives'][0];cp=b.d['meshes'][1]['primitives'][0]
assert a.names==b.names[:len(a.names)] and np.array_equal(a.rest,b.rest[:len(a.names)]) and np.array_equal(a.parent,b.parent[:len(a.names)])
assert a.d['materials']==b.d['materials']
for old,new in zip(a.d['skins'],b.d['skins']):
 assert old['joints']==new['joints'] and np.array_equal(accessor(a.d,a.b,old['inverseBindMatrices']),accessor(b.d,b.b,new['inverseBindMatrices']))
for old,new in zip(a.d['images'],b.d['images']):
 x=a.d['bufferViews'][old['bufferView']];y=b.d['bufferViews'][new['bufferView']];assert a.b[x.get('byteOffset',0):x.get('byteOffset',0)+x['byteLength']]==b.b[y.get('byteOffset',0):y.get('byteOffset',0)+y['byteLength']]
for name,ix in ap['attributes'].items():
 old=accessor(a.d,a.b,ix);assert np.array_equal(old[soft],accessor(b.d,b.b,bp['attributes'][name]))
 if not name.startswith(('JOINTS_','WEIGHTS_')):assert np.array_equal(old[rigid],accessor(b.d,b.b,cp['attributes'][name]))
for x,y in zip(ap['targets'],bp['targets']):
 for key in x:assert np.array_equal(accessor(a.d,a.b,x[key])[soft],accessor(b.d,b.b,y[key]))
assert len(ap['targets'])==len(bp['targets'])==len(ap['targets']) and not cp.get('targets')
tri=accessor(a.d,a.b,ap['indices']).astype(int).reshape(-1,3);recovered=np.r_[soft[accessor(b.d,b.b,bp['indices']).astype(int).reshape(-1,3)],rigid[accessor(b.d,b.b,cp['indices']).astype(int).reshape(-1,3)]];assert sorted(map(tuple,tri))==sorted(map(tuple,recovered))
assert set(a.animations)==set(b.animations)
for clip,an in a.animations.items():
 bn=b.animations[clip];assert an['channels']==bn['channels']
 for x,y in zip(an['samplers'],bn['samplers']):
  assert x.get('interpolation','LINEAR')==y.get('interpolation','LINEAR')
  for key in ['input','output']:assert np.array_equal(accessor(a.d,a.b,x[key]),accessor(b.d,b.b,y[key]))

def world_batch(t,q,s):
 n=len(t);local=np.broadcast_to(np.eye(4),(n,a.n,4,4)).copy();local[:,:,:3,:3]=Rotation.from_quat(q.reshape(-1,4)).as_matrix().reshape(n,a.n,3,3)*s[:,:,None,:];local[:,:,:3,3]=t;world=np.empty_like(local)
 for node in a.order:world[:,node]=local[:,node] if a.parent[node]<0 else world[:,a.parent[node]]@local[:,node]
 return world
normal=accessor(a.d,a.b,ap['attributes']['NORMAL'])[rigid];nt=np.stack([accessor(a.d,a.b,t['NORMAL'])[rigid] if 'NORMAL'in t else np.zeros_like(normal) for t in ap['targets']]);pt=pa['targets'][:,rigid];position_slots=np.flatnonzero(np.any(pt,axis=(1,2)));normal_slots=np.flatnonzero(np.any(nt,axis=(1,2)));pt=pt[position_slots].reshape(len(position_slots),-1);nt=nt[normal_slots].reshape(len(normal_slots),-1);base=pa['position'][rigid];bone=pa['nodes'][0];height=float(np.ptp(a.vertices[:,1]));results={};beg=time.perf_counter()
for clip,an in a.animations.items():
 knots=np.unique(np.concatenate([accessor(a.d,a.b,s['input']).ravel() for s in an['samplers']]));times=np.unique(np.r_[knots,(knots[:-1]+knots[1:])/2,np.array([.11337,.29381,.53119,.76347,.95131])*a.duration(clip)]);ts,qs,ss,morph=a.sample(clip,times);weights=morph[pa['node']];maximum=0.;normalmax=0.;floor=0.;maxvelocity=0.;previous=None
 for start in range(0,len(times),256):
  end=min(start+256,len(times));world=world_batch(ts[start:end],qs[start:end],ss[start:end]);transforms=world[:,pa['nodes']]@pa['bind'];localpos=base[None,:,:3]+(weights[start:end,position_slots]@pt).reshape(end-start,len(rigid),3);hom=np.concatenate([localpos,np.ones((end-start,len(rigid),1))],axis=2);old=np.zeros_like(localpos);nn=normal[None]+(weights[start:end,normal_slots]@nt).reshape(end-start,len(rigid),3);oldn=np.zeros_like(nn)
  for slot in range(pa['joints'].shape[1]):
   matrix=transforms[:,pa['joints'][rigid,slot]];w=pa['weights'][rigid,slot];old+=np.einsum('svab,svb->sva',matrix[:,:,:3],hom)*w[None,:,None];oldn+=np.einsum('svab,svb->sva',matrix[:,:,:3,:3],nn)*w[None,:,None]
  new=np.einsum('sab,vb->sva',transforms[:,0,:3],base);newn=np.einsum('sab,vb->sva',transforms[:,0,:3,:3],normal);delta=new-old;error=np.linalg.norm(delta,axis=2);maximum=max(maximum,float(error.max()));floor=max(floor,float(np.abs(delta[:,:,1]).max()));unit=lambda n:n/np.maximum(np.linalg.norm(n,axis=2,keepdims=True),1e-30);angles=np.degrees(np.arccos(np.clip(np.einsum('svi,svi->sv',unit(oldn),unit(newn)),-1,1)));normalmax=max(normalmax,float(angles.max()))
  if previous is not None:
   delta=np.concatenate([previous[None],delta]);clock=np.r_[times[start-1],times[start:end]]
  else:clock=times[start:end]
  dt=np.diff(clock);valid=dt>1e-7
  if valid.any():maxvelocity=max(maxvelocity,float((np.linalg.norm(np.diff(delta,axis=0),axis=2)[valid]/dt[valid,None]).max()))
  previous=delta[-1].copy()
 assert maximum/height<1e-7 and normalmax<1e-4,(clip,maximum,normalmax)
 result={'original_knots':len(knots),'keys_midpoints_offgrid_samples':len(times),'max_surface_error_source_units':maximum,'max_surface_error_over_height':maximum/height,'max_normal_angle_degrees':normalmax,'max_height_difference_source_units':floor,'max_added_surface_velocity_source_units_per_second':maxvelocity};results[clip]=result;print(clip,result,flush=True)
 args.report.write_text(json.dumps({'source_sha256':digest(a.path),'candidate_sha256':digest(b.path),'soft_geometry_skin_targets_bit_exact':True,'joint_and_weight_curves_bit_exact':True,'textures_materials_binds_rest_and_hierarchy_preserved':True,'height':height,'rigid_vertices':len(rigid),'clips':results,'elapsed_seconds':time.perf_counter()-beg},indent=2))
print('SOURCE_DONE',time.perf_counter()-beg,flush=True)
