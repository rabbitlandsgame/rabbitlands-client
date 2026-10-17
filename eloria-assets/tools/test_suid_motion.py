"""Audit installed boar/tapir skin contact, serial lengths, interpolation and witnesses."""
from pathlib import Path
import sys,json,argparse
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import accessor,digest
from video_motion.native_shapes import NativeShapeAsset as Native
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--report",type=Path);args=p.parse_args()
profiles=json.loads((ROOT/"docs/qa/suid-motion/actors.json").read_text(encoding="utf-8"))
expected=json.loads((ROOT/"godot-client/tests/fixtures/suid_motion_worlds.json").read_text(encoding="utf-8"))
assert len(profiles)==len(expected)==5
report={"passed":True,"actors":{}}
for actor,profile in profiles.items():
 a=Native(ROOT/profile["runtime_path"]);assert digest(a.path)==profile["sha256"]==expected[actor]["sha256"];assert a.d["asset"]["extras"]["rabbitlands_animation_bake_fps"]==3072
 row={"sha256":digest(a.path),"clips":{}}
 witness={'sha256':digest(a.path),'clips':{}}
 for clip in a.animations:
  duration=a.duration(clip);off=np.array([.01317,.11337,.29381,.53119,.76347,.95131])*duration;t,q,sc,mw=a.sample(clip,off);entries=[]
  for i,tt in enumerate(off):
   w=a.world(t[i],q[i],sc[i]);entries.append({'time':float(tt),'bones':{a.names[n]:w[n].reshape(-1).tolist() for n in profile['primary_joint_ids']},'morph_weights':{str(n):x[i].tolist() for n,x in mw.items()}})
  witness['clips'][clip]=entries
 for clip in ['Walk','Jog']:
  duration=a.duration(clip);stride=profile['gaits'][clip]['stride'];speed=stride/duration;keys=np.unique(np.r_[*[accessor(a.d,a.b,sm['input']).ravel() for sm in a.animations[clip]['samplers']]]);ts=np.unique(np.r_[keys,(keys[:-1]+keys[1:])/2,np.linspace(0,duration,round(duration*384)+1)]);t,q,sc,mw=a.sample(clip,ts);sole={l:[] for l in profile['sole_vertices']};minimum=1e9;length_error=0.;poses=[]
  for i,tt in enumerate(ts):
   w=a.world(t[i],q[i],sc[i]);v=a.skin(w,{n:x[i] for n,x in mw.items()});minimum=min(minimum,float(v[:,1].min()));poses.append(w)
   for l,ids in profile['sole_vertices'].items():sole[l].append(v[ids].mean(0))
   for l,chain in profile['serial_chains'].items():length_error=max(length_error,float(np.max(abs(np.linalg.norm(np.diff(w[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)))))
  contacts={};slide=0.
  for l,points in sole.items():
   points=np.array(points);points[:,2]+=speed*ts;td=profile['gaits'][clip]['touchdown'][l];st=profile['gaits'][clip]['stance_fraction'];phase=(ts/duration-td)%1;phase[np.abs(phase-1)<1e-6]=0;mask=phase<=st+1e-6;valid=mask[:-1]&mask[1:]&(np.diff(ts)>1e-7);vel=np.linalg.norm(np.diff(points,axis=0),axis=1)[valid]/np.diff(ts)[valid];mx=float(vel.max(initial=0));slide=max(slide,mx);contacts[l]={'max_supported_surface_speed':mx,'stance_samples':int(mask.sum())}
  seam=float(np.max(abs(poses[0]-poses[-1])));rotation_step=float((Rotation.from_quat(q[1:].reshape(-1,4))*Rotation.from_quat(q[:-1].reshape(-1,4)).inv()).magnitude().max());passed=rotation_step<.025 and minimum>=-.0005 and slide<=.005 and length_error<5e-6 and seam<2e-6;row['clips'][clip]={'passed':passed,'duration':duration,'native_forward_speed':speed,'export_keys':len(keys),'audit_samples':len(ts),'floor_min':minimum,'max_paw_slide':slide,'native_length_error':length_error,'world_loop_seam_error':seam,'max_adjacent_rotation_radians':rotation_step,'contacts':contacts};report['passed'] &= passed

 for clip in ['Sword_Attack','Death_A']:
  duration=a.duration(clip);keys=np.unique(np.r_[*[accessor(a.d,a.b,sm['input']).ravel() for sm in a.animations[clip]['samplers']]]);ts=np.unique(np.r_[keys,(keys[:-1]+keys[1:])/2,np.linspace(0,duration,round(duration*192)+1)]);t,q,sc,mw=a.sample(clip,ts);minimum=1e9;length_error=0.;sole={l:[] for l in profile['sole_vertices']};terminal=[];max_rotation_step=0.;previous=None
  for i,tt in enumerate(ts):
   w=a.world(t[i],q[i],sc[i]);v=a.skin(w,{n:x[i] for n,x in mw.items()});minimum=min(minimum,float(v[:,1].min()))
   for l,ids in profile['sole_vertices'].items():sole[l].append(v[ids].mean(0))
   for l,chain in profile['serial_chains'].items():length_error=max(length_error,float(np.max(abs(np.linalg.norm(np.diff(w[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)))))
   if previous is not None:max_rotation_step=max(max_rotation_step,float((Rotation.from_quat(q[i])*Rotation.from_quat(previous).inv()).magnitude().max()))
   previous=q[i]
   if tt>=(1.45 if clip=='Sword_Attack' else 2.05)+1e-6:terminal.append(w)
  slide=0.;contacts={}
  for l,points in sole.items():
   fore=l.startswith('fore');points=np.array(points)
   if clip=='Death_A':mask=ts<=(.50 if fore else .67)+1e-6
   else:
    event=profile.get('attack_contacts',{}).get('fore' if fore else 'hind',{});release=event.get('release',.25 if fore else .60);land=event.get('land',.55 if fore else .85);start=event.get('recover_start',1.05 if fore else 1.15);end=event.get('recover_end',1.32 if fore else 1.43);mask=(ts<=release+1e-6)|((ts>=land-1e-6)&(ts<=start+1e-6))|(ts>=end-1e-6)
   valid=mask[:-1]&mask[1:]&(np.diff(ts)>1e-7);vel=np.linalg.norm(np.diff(points,axis=0),axis=1)[valid]/np.diff(ts)[valid];mx=float(vel.max(initial=0));slide=max(slide,mx);contacts[l]={'max_supported_surface_speed':mx,'stance_samples':int(mask.sum())}
  hold=max(float(np.max(abs(w-terminal[0]))) for w in terminal);passed=minimum>=-.0005 and slide<=.005 and length_error<5e-6 and hold<2e-6 and max_rotation_step<.025
  metrics={'passed':passed,'duration':duration,'export_keys':len(keys),'audit_samples':len(ts),'floor_min':minimum,'max_paw_slide':slide,'native_length_error':length_error,'terminal_hold_world_error':hold,'max_adjacent_rotation_radians':max_rotation_step,'contacts':contacts}
  st,sq,ss,sm=a.sample(clip,[0,.57,duration]);wv=[a.world(st[k],sq[k],ss[k]) for k in range(3)];vv=[a.skin(wv[k],{n:x[k] for n,x in sm.items()}) for k in range(3)];muzzle=np.array(profile['muzzle_vertex_ids'])
  if clip=='Death_A':
   metrics['fallen_muzzle_minimum_height']=float(vv[-1][muzzle,1].min());body=np.array(profile['body_support_vertex_ids']);metrics['fallen_body_and_proximal_limb_minimum_height']=float(vv[-1][body,1].min());metrics['native_head_yaw_degrees']=profile['death_head_angles'][0];metrics['fallen_upper_snout_minimum_height']=float(vv[-1][profile['true_muzzle_vertex_ids'],1].min());metrics['body_roll_degrees']=profile.get('death_body_roll_degrees',88);metrics['support_scope']=[profile['head_support_kind'],profile['body_support_kind']];passed &= metrics['fallen_muzzle_minimum_height']<.015*profile['height'] and metrics['fallen_body_and_proximal_limb_minimum_height']<.015*profile['height']
  else:metrics['muzzle_forward_reach_at_strike']=float(vv[1][muzzle,2].mean()-vv[0][muzzle,2].mean());passed &= metrics['muzzle_forward_reach_at_strike']>.06*profile['height']
  metrics['passed']=passed;row['clips'][clip]=metrics;report['passed'] &= passed
 for clip,entries in witness["clips"].items():
  for actual,prior in zip(entries,expected[actor]["clips"][clip]):
   assert abs(actual["time"]-prior["time"])<1e-12
   for bone,matrix in actual["bones"].items():assert np.allclose(matrix,prior["bones"][bone],atol=1e-12,rtol=0)
   for node,values in actual["morph_weights"].items():assert np.allclose(values,prior["morph_weights"][node],atol=1e-12,rtol=0)
 report["actors"][actor]=row;print(actor,{c:v["passed"] for c,v in row["clips"].items()},flush=True)
if args.report:
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
print("SUID_EXPORT","PASS" if report["passed"] else "FAIL","motions=",sum(len(x["clips"]) for x in report["actors"].values()))
raise SystemExit(0 if report["passed"] else 1)
