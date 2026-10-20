"""Verify approved Orc/Kobold humanoids against independent rig/surface witnesses."""
from pathlib import Path
import sys,json,argparse
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset
ROOT=Path(__file__).resolve().parents[2]
def partial(a,w,ids):
 p=a.parts[0];pos=p['position'][ids];mat=w[p['nodes']]@p['bind'];v=np.zeros((len(ids),3))
 for k in range(p['joints'].shape[1]):v+=np.einsum('vab,vb->va',mat[p['joints'][ids,k],:3],pos)*p['weights'][ids,k,None]
 return v

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path);args=ap.parse_args();profiles=json.loads((ROOT/'docs/qa/orc-kobold-motion/actors.json').read_text(encoding='utf-8'));witnesses=json.loads((ROOT/'godot-client/tests/fixtures/orc_kobold_motion_worlds.json').read_text(encoding='utf-8'));reg=json.loads((ROOT/'godot-client/data/actors/models.json').read_text(encoding='utf-8'))['models'];assert len(profiles)==len(witnesses)==2;report={'passed':True,'actors':{},'scope':'Independent bone, morph and surface witnesses in14 slots;4097 support samples per gait and241 full-surface samples per authored action; native lengths, floor, loops, holds, import cadence and measured stride.'}
 for actor,p in profiles.items():
  a=NativeShapeAsset(ROOT/p['runtime_path']);witness=witnesses[actor];assert digest(a.path)==p['sha256']==witness['sha256'];assert a.d['asset']['extras']['rabbitlands_animation_bake_fps']==p['bake_fps'];policy=Path(str(a.path)+'.import').read_text(encoding='utf-8');assert f"animation/fps={p['bake_fps']}" in policy and '"optimizer/enabled": false' in policy and '"compression/enabled": false' in policy;mp=json.loads((ROOT/'godot-client'/reg[actor]['animationMap'].removeprefix('res://')).read_text(encoding='utf-8'));row={'sha256':digest(a.path),'clips':{},'contacts':{}}
  for clip,entries in witness['clips'].items():
   tt,qq,ss,mm=a.sample(clip,[e['time'] for e in entries]);be=se=me=0.
   for k,e in enumerate(entries):
    w=a.world(tt[k],qq[k],ss[k]);v=a.skin(w,{n:x[k] for n,x in mm.items()})
    for name,m in e['bones'].items():be=max(be,float(abs(w[a.ids[name]]-np.array(m).reshape(4,4)).max()))
    for n,m in e['morph_weights'].items():me=max(me,float(abs(mm[int(n)][k]-m).max(initial=0.)))
    se=max(se,float(abs(v[witness['surface_vertex_ids']]-e['surface']).max()))
   assert be<1e-12 and se<1e-12 and me<1e-12,(actor,clip,be,se,me);row['clips'][clip]={'independent_bone_error':be,'surface_error':se,'morph_error':me}
  for clip,g in p['gaits'].items():
   dur=g['duration'];ts=np.linspace(0,dur,4097);tt,qq,ss,_=a.sample(clip,ts);ids=np.unique(np.r_[*[ii for ii in p['sole_vertices'].values()]]);lookup={int(v):i for i,v in enumerate(ids)};values={s:[] for s in p['sole_vertices']};tilts={s:0. for s in values}
   for k,t in enumerate(ts):
    w=a.world(tt[k],qq[k],ss[k]);v=partial(a,w,ids)
    for side,ii in p['sole_vertices'].items():
     values[side].append(v[[lookup[int(i)] for i in ii]].mean(0));phase=(t/dur-g['touchdown'][side])%1
     if phase<g['stance_fraction']:
      n=p['chains'][side][-1];deform=(w[n]@np.linalg.inv(a.rest[n]))[:3,:3];up=deform@np.array(p['foot_neutral_rotations'][side]).T@np.array([0.,1.,0.]);tilts[side]=max(tilts[side],float(np.rad2deg(np.arccos(np.clip(up[1]/np.linalg.norm(up),-1,1)))))
   rows={}
   for side,points in values.items():
    points=np.array(points);phase=(ts/dur-g['touchdown'][side])%1;stable=(phase[:-1]>1e-4)&(phase[1:]<g['stance_fraction']-1e-4)&(abs(np.diff(phase))<.01);vel=np.diff(points,axis=0)/np.diff(ts)[:,None];vel[:,2]+=g['stride']/dur;speed=float(np.linalg.norm(vel[stable],axis=1).max()/p['height']);drift=float(np.ptp(points[phase<g['stance_fraction'],:2],axis=0).max()/p['height']);assert speed<.003 and drift<.00004 and tilts[side]<.01,(actor,clip,side,speed,drift,tilts[side]);rows[side]={'stance_speed_error_heights_per_second':speed,'stance_xy_drift_heights':drift,'sole_frame_tilt_degrees':tilts[side]}
   assert abs(a.world(tt[0],qq[0],ss[0])-a.world(tt[-1],qq[-1],ss[-1])).max()<2e-6;action='walk' if clip=='Walk' else 'run';assert abs(mp['strideMetresPerSecond'][action]-g['stride']/dur*reg[actor]['import']['scale'])<1e-6;row['contacts'][clip]=rows
  for clip,dur in p['durations'].items():
   tt,qq,ss,_=a.sample(clip,np.linspace(0,dur,241));low=1e9;length=0.
   for k in range(len(tt)):
    w=a.world(tt[k],qq[k],ss[k]);v=a.skin(w);low=min(low,float(v[:,1].min()))
    for ch in p['serial_chains'].values():length=max(length,float(abs(np.linalg.norm(np.diff(w[ch,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[ch,:3,3],axis=0),axis=1)).max()))
   assert low>-.00001*p['height'] and length<2e-6,(actor,clip,low,length);row['clips'][clip].update(minimum_surface_y=low,max_native_serial_length_error=length)
  for clip,start in p['hold_start'].items():
   tt,qq,ss,_=a.sample(clip,[start,a.duration(clip)]);assert abs(a.world(tt[0],qq[0],ss[0])-a.world(tt[1],qq[1],ss[1])).max()<2e-6
  report['actors'][actor]=row;print(actor,'PASS',flush=True)
 if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
 print('ORC_KOBOLD_NATIVE PASS14 slots',flush=True)
if __name__=='__main__':main()
