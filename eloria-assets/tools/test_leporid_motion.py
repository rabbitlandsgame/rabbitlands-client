"""Audit installed Rabbit/Jackalope surfaces, contact, native lengths and holds."""
from pathlib import Path
import sys,json,argparse
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import accessor,digest
from video_motion.native_shapes import NativeShapeAsset as Native
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--report',type=Path);args=p.parse_args()
profiles=json.loads((ROOT/'docs/qa/leporid-motion/actors.json').read_text(encoding='utf-8'))
expected=json.loads((ROOT/'godot-client/tests/fixtures/leporid_motion_worlds.json').read_text(encoding='utf-8'))
report={'passed':True,'actors':{}}
for actor,profile in profiles.items():
 a=Native(ROOT/f'godot-client/assets/actors/native/creatures/basic_expansion/{actor}.glb');assert digest(a.path)==profile['sha256'];assert a.d['asset']['extras']['rabbitlands_animation_bake_fps']==3072
 assert len(a.joints)==25 and max((len(x['targets']) for x in a.parts),default=0)==(25 if actor=='jackalope' else 0)
 row={'sha256':digest(a.path),'clips':{}}
 witness={'sha256':digest(a.path),'clips':{}}
 for clip in a.animations:
  duration=a.duration(clip);off=np.array([.01317,.11337,.29381,.53119,.76347,.95131])*duration;t,q,sc,mw=a.sample(clip,off);entries=[]
  for i,tt in enumerate(off):
   w=a.world(t[i],q[i],sc[i]);entries.append({'time':float(tt),'bones':{a.names[n]:w[n].reshape(-1).tolist() for n in a.joints},'morph_weights':{str(n):x[i].tolist() for n,x in mw.items()}})
  witness['clips'][clip]=entries
 for clip in ['Walk','Jog']:
  duration=a.duration(clip);stride=.27 if clip=='Walk' else .43;speed=stride/duration;keys=np.unique(np.r_[*[accessor(a.d,a.b,sm['input']).ravel() for sm in a.animations[clip]['samplers']]]);ts=np.unique(np.r_[keys,(keys[:-1]+keys[1:])/2,np.linspace(0,duration,round(duration*384)+1)]);t,q,sc,mw=a.sample(clip,ts);sole={l:[] for l in profile['sole_vertices']};minimum=1e9;length_error=0.;poses=[]
  for i,tt in enumerate(ts):
   w=a.world(t[i],q[i],sc[i]);v=a.skin(w,{n:x[i] for n,x in mw.items()});minimum=min(minimum,float(v[:,1].min()));poses.append(w)
   for l,ids in profile['sole_vertices'].items():sole[l].append(v[ids].mean(0))
   for l,chain in profile['chains'].items():length_error=max(length_error,float(np.max(abs(np.linalg.norm(np.diff(w[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)))))
  contacts={};slide=0.
  for l,points in sole.items():
   points=np.array(points);points[:,2]+=speed*ts;td=0 if l.startswith('fore') else .18;st=.31 if l.startswith('fore') else .28;phase=(ts/duration-td)%1;phase[np.abs(phase-1)<1e-6]=0;mask=phase<=st+1e-6;valid=mask[:-1]&mask[1:]&(np.diff(ts)>1e-7);vel=np.linalg.norm(np.diff(points,axis=0),axis=1)[valid]/np.diff(ts)[valid];mx=float(vel.max(initial=0));slide=max(slide,mx);contacts[l]={'max_supported_surface_speed':mx,'stance_samples':int(mask.sum())}
  seam=float(np.max(abs(poses[0]-poses[-1])));passed=minimum>=-.0005 and slide<=.005 and length_error<5e-6 and seam<2e-6;row['clips'][clip]={'passed':passed,'duration':duration,'native_forward_speed':speed,'export_keys':len(keys),'audit_samples':len(ts),'floor_min':minimum,'max_paw_slide':slide,'native_length_error':length_error,'world_loop_seam_error':seam,'contacts':contacts};report['passed'] &= passed

 for clip in ['Sword_Attack','Death_A']:
  duration=a.duration(clip);keys=np.unique(np.r_[*[accessor(a.d,a.b,sm['input']).ravel() for sm in a.animations[clip]['samplers']]]);ts=np.unique(np.r_[keys,(keys[:-1]+keys[1:])/2,np.linspace(0,duration,round(duration*192)+1)]);t,q,sc,mw=a.sample(clip,ts);minimum=1e9;length_error=0.;sole={l:[] for l in profile['sole_vertices']};terminal=[];max_rotation_step=0.;previous=None
  for i,tt in enumerate(ts):
   w=a.world(t[i],q[i],sc[i]);v=a.skin(w,{n:x[i] for n,x in mw.items()});minimum=min(minimum,float(v[:,1].min()))
   for l,ids in profile['sole_vertices'].items():sole[l].append(v[ids].mean(0))
   for l,chain in profile['chains'].items():length_error=max(length_error,float(np.max(abs(np.linalg.norm(np.diff(w[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)))))
   if previous is not None:max_rotation_step=max(max_rotation_step,float((Rotation.from_quat(q[i])*Rotation.from_quat(previous).inv()).magnitude().max()))
   previous=q[i]
   if tt>=(1.50 if clip=='Sword_Attack' else 1.90)+1e-6:terminal.append(w)
  slide=0.;contacts={}
  for l,points in sole.items():
   fore=l.startswith('fore');points=np.array(points)
   if clip=='Death_A':mask=ts<=(.50 if fore else .66)+1e-6
   else:
    release=.22 if fore else .38;land=.74 if fore else .91;start=1. if fore else 1.17;end=1.28 if fore else 1.45;mask=(ts<=release+1e-6)|((ts>=land-1e-6)&(ts<=start+1e-6))|(ts>=end-1e-6)
   valid=mask[:-1]&mask[1:]&(np.diff(ts)>1e-7);vel=np.linalg.norm(np.diff(points,axis=0),axis=1)[valid]/np.diff(ts)[valid];mx=float(vel.max(initial=0));slide=max(slide,mx);contacts[l]={'max_supported_surface_speed':mx,'stance_samples':int(mask.sum())}
  hold=max(float(np.max(abs(w-terminal[0]))) for w in terminal);passed=minimum>=-.0005 and slide<=.005 and length_error<5e-6 and hold<2e-6 and max_rotation_step<.25
  metrics={'passed':passed,'duration':duration,'export_keys':len(keys),'audit_samples':len(ts),'floor_min':minimum,'max_paw_slide':slide,'native_length_error':length_error,'terminal_hold_world_error':hold,'max_adjacent_rotation_radians':max_rotation_step,'contacts':contacts}
  st,sq,ss,sm=a.sample(clip,[0,duration*.37,duration]);wv=[a.world(st[k],sq[k],ss[k]) for k in range(3)];vv=[a.skin(wv[k],{n:x[k] for n,x in sm.items()}) for k in range(3)];muzzle=np.array(profile['muzzle_vertex_ids'])
  if clip=='Death_A':
   metrics['fallen_muzzle_minimum_height']=float(vv[-1][muzzle,1].min());body=np.array(profile['body_support_vertex_ids']);metrics['fallen_torso_minimum_height']=float(vv[-1][body,1].min());metrics['native_head_yaw_degrees']=profile['death_native_head_yaw_degrees'];passed &= metrics['fallen_muzzle_minimum_height']<.012 and metrics['fallen_torso_minimum_height']<.015
  else:metrics['muzzle_forward_reach_at_strike']=float(vv[1][muzzle,2].mean()-vv[0][muzzle,2].mean());passed &= metrics['muzzle_forward_reach_at_strike']>.12
  metrics['passed']=passed;row['clips'][clip]=metrics;report['passed'] &= passed
 for clip,entries in witness['clips'].items():
  for actual,prior in zip(entries,expected[actor]['clips'][clip]):
   assert abs(actual['time']-prior['time'])<1e-12
   for bone,matrix in actual['bones'].items():assert np.allclose(matrix,prior['bones'][bone],atol=1e-12,rtol=0)
   for node,values in actual['morph_weights'].items():assert np.allclose(values,prior['morph_weights'][node],atol=1e-12,rtol=0)
 report['actors'][actor]=row
if args.report:
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
print('LEPORID_EXPORT', 'PASS' if report['passed'] else 'FAIL', 'motions=',sum(len(x['clips']) for x in report['actors'].values()))
raise SystemExit(0 if report['passed'] else 1)
