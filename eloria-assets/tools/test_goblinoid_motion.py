"""Verify the installed goblinoids against independent native-rig witnesses."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset
ROOT=Path(__file__).resolve().parents[2]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args();profiles=json.loads((ROOT/'docs/qa/goblinoid-motion/actors.json').read_text(encoding='utf-8'));witnesses=json.loads((ROOT/'godot-client/tests/fixtures/goblinoid_motion_worlds.json').read_text(encoding='utf-8'));registry=json.loads((ROOT/'godot-client/data/actors/models.json').read_text(encoding='utf-8'))['models'];report={'passed':True,'actors':{}};assert len(profiles)==len(witnesses)==4
 for actor,p in profiles.items():
  a=NativeShapeAsset(ROOT/p['runtime_path']);witness=witnesses[actor];assert digest(a.path)==p['sha256']==witness['sha256'];assert set(a.animations)=={'Idle_A','Fighting_Idle','Hit_Chest','Walk','Jog','Sword_Attack','Death_A'};assert a.d['asset']['extras']['rabbitlands_animation_bake_fps']==p['bake_fps'];policy=Path(str(a.path)+'.import').read_text(encoding='utf-8');assert f"animation/fps={p['bake_fps']}" in policy and '"optimizer/enabled": false' in policy and '"compression/enabled": false' in policy;mapping=json.loads((ROOT/'godot-client'/registry[actor]['animationMap'].removeprefix('res://')).read_text(encoding='utf-8'));row={'sha256':digest(a.path),'clips':{}}
  for clip,entries in witness['clips'].items():
   tt,qq,ss,mm=a.sample(clip,[e['time'] for e in entries]);bone_error=shape_error=surface_error=0.
   for i,e in enumerate(entries):
    w=a.world(tt[i],qq[i],ss[i]);v=a.skin(w,{n:x[i] for n,x in mm.items()})
    for name,m in e['bones'].items():bone_error=max(bone_error,float(abs(w[a.ids[name]]-np.array(m).reshape(4,4)).max()))
    for n,x in e['morph_weights'].items():shape_error=max(shape_error,float(abs(mm[int(n)][i]-x).max(initial=0)))
    surface_error=max(surface_error,float(abs(v[witness['surface_vertex_ids']]-e['surface']).max()))
   assert bone_error<1e-12 and shape_error<1e-12 and surface_error<1e-12,(actor,clip,bone_error,shape_error,surface_error);row['clips'][clip]={'independent_bone_error':bone_error,'shape_error':shape_error,'surface_error':surface_error}
  for clip in ['Walk','Jog','Sword_Attack','Death_A']:
   dur=a.duration(clip);events=[x for side in p['support_intervals'].get(clip,{}).values() for r in side for x in r];ts=np.unique(np.r_[np.linspace(0,dur,round(dur*384)+1),events]);tt,qq,ss,mm=a.sample(clip,ts);floor=1e9;length_error=0.;worlds=[];feet={side:[] for side in p['foot_frames']};contacts={side:[] for side in feet};tilts={side:0. for side in feet};spreads=tilts.copy();gaps=tilts.copy();minfeet={s:1e9 for s in feet};seam=0.;_,wi=np.unique(np.round(a.vertices,7),axis=0,return_inverse=True);counts=np.bincount(wi)
   for i,t in enumerate(ts):
    w=a.world(tt[i],qq[i],ss[i]);worlds.append(w);v=a.skin(w,{n:x[i] for n,x in mm.items()});floor=min(floor,float(v[:,1].min()));mean=np.zeros((len(counts),3));np.add.at(mean,wi,v);mean/=counts[:,None];seam=max(seam,float(abs(v-mean[wi]).max()))
    for ch in p['serial_chains'].values():length_error=max(length_error,float(abs(np.linalg.norm(np.diff(w[ch,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[ch,:3,3],axis=0),axis=1)).max()))
    for side,frame in p['foot_frames'].items():
     speed=0.
     if clip in p['gaits']:
      g=p['gaits'][clip];phase=(t/dur-g['touchdown'][side])%1;phase=0 if abs(phase-1)<1e-8 else phase;support=phase<=g['stance_fraction']+1e-8;speed=g['stride']/dur
     else:support=any(lo-1e-8<=t<=hi+1e-8 for lo,hi in p['support_intervals'][clip][side])
     ids=frame['rigid_palm_vertices'];points=v[ids].copy();points[:,2]+=speed*t;feet[side].append(points);contacts[side].append(support)
     if support:
      n=p['chains'][side][-1];normal=(w[n]@np.linalg.inv(a.rest[n]))[:3,:3]@np.array(frame['native_up']);tilts[side]=max(tilts[side],float(np.degrees(np.arccos(np.clip(normal[1]/np.linalg.norm(normal),-1,1)))));lows=np.array([v[j,1].min() for j in frame['digit_contact_groups'].values()]);spreads[side]=max(spreads[side],float(np.ptp(lows)));gaps[side]=max(gaps[side],float(lows.max()-p['floor']));minfeet[side]=min(minfeet[side],float(v[ids,1].min()))
   contact={}
   for side,points in feet.items():
    supported=np.array(contacts[side]);valid=supported[:-1]&supported[1:];velocity=np.linalg.norm(np.diff(points,axis=0),axis=2)/np.diff(ts)[:,None];slide=float(velocity[valid].max(initial=0));limit=max(.006*p['height'],p['foot_frames'][side].get('fit_spread',0)+.00005*p['height']);assert tilts[side]<.01 and spreads[side]<limit and gaps[side]<limit+.0001*p['height'] and minfeet[side]>=p['floor']-.00002 and slide<.005,(actor,clip,side,tilts,spreads,gaps,minfeet,slide);contact[side]={'whole_sole_speed':slide,'tilt_degrees':tilts[side],'underside_spread':spreads[side]}
   if clip in p['gaits']:
    hold=float(abs(worlds[0]-worlds[-1]).max());g=p['gaits'][clip];action='walk' if clip=='Walk' else 'run';assert mapping['actions'][action]==clip and clip in mapping['loopingClips'];assert abs(mapping['strideMetresPerSecond'][action]-g['stride']/dur*registry[actor]['import']['scale'])<1e-6
   else:
    start=p['hold_start'][clip];ht,hq,hs,_=a.sample(clip,[start,(start+dur)/2,dur]);hw=[a.world(ht[i],hq[i],hs[i]) for i in range(3)];hold=max(float(abs(w-hw[0]).max()) for w in hw)
   assert floor>=-.0005 and length_error<5e-6 and hold<2e-6 and seam<8e-6,(actor,clip,floor,length_error,hold,seam);row['clips'][clip].update(floor=floor,native_length_error=length_error,loop_or_hold_error=hold,welded_seam_gap=seam,contacts=contact)
  report['actors'][actor]=row;print(actor,'PASS independent witnesses, native limbs and both whole soles',flush=True)
 if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print('GOBLINOID_NATIVE PASS 28 slots, 16 authored actions',flush=True)
if __name__=='__main__':main()
