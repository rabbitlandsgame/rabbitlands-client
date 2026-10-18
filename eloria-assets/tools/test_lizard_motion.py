"""Check the installed reviewed lizard family against independent native witnesses."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from scipy.spatial import ConvexHull
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset
ROOT=Path(__file__).resolve().parents[2]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
 profiles=json.loads((ROOT/'docs/qa/lizard-motion/actors.json').read_text())
 witnesses=json.loads((ROOT/'godot-client/tests/fixtures/lizard_motion_worlds.json').read_text())
 registry=json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
 assert len(profiles)==len(witnesses)==4
 patches=json.loads((ROOT/'docs/qa/lizard-motion/skin-patches.json').read_text())
 contact_frames=json.loads((ROOT/'docs/qa/lizard-motion/paw-frames.json').read_text())
 report={'passed':True,'actors':{}}
 for actor,p in profiles.items():
  a=NativeShapeAsset(ROOT/p['runtime_path']);witness=witnesses[actor];assert digest(a.path)==p['sha256']==witness['sha256'];assert len(a.animations)==7
  mapping=json.loads((ROOT/'godot-client'/registry[actor]['animationMap'].removeprefix('res://')).read_text());row={'sha256':p['sha256'],'clips':{}}
  for clip,entries in witness['clips'].items():
   ts=[e['time'] for e in entries];t,q,sc,mw=a.sample(clip,ts);bone_error=shape_error=surface_error=0.
   for i,e in enumerate(entries):
    world=a.world(t[i],q[i],sc[i]);surface=a.skin(world,{n:v[i] for n,v in mw.items()})
    for name,matrix in e['bones'].items():bone_error=max(bone_error,float(abs(world[a.ids[name]]-np.array(matrix).reshape(4,4)).max()))
    for n,values in e['morph_weights'].items():shape_error=max(shape_error,float(abs(mw[int(n)][i]-values).max(initial=0)))
    surface_error=max(surface_error,float(abs(surface[witness['surface_vertex_ids']]-np.array(e['surface'])).max()))
   assert bone_error<1e-12 and shape_error<1e-12 and surface_error<1e-12,(actor,clip,bone_error,shape_error,surface_error)
   row['clips'][clip]={'independent_bone_error':bone_error,'shape_error':shape_error,'surface_error':surface_error}
  for clip,g in p['gaits'].items():
   duration=a.duration(clip);ts=np.linspace(0,duration,round(duration*384)+1);t,q,sc,mw=a.sample(clip,ts);points={leg:[] for leg in p['sole_vertices']};floor=1e9;length_error=0.;ends=[]
   for i,tt in enumerate(ts):
    world=a.world(t[i],q[i],sc[i]);surface=a.skin(world,{n:v[i] for n,v in mw.items()});floor=min(floor,float(surface[:,1].min()))
    for leg,ids in p['sole_vertices'].items():points[leg].append(surface[ids].mean(0))
    for chain in p['serial_chains'].values():length_error=max(length_error,float(abs(np.linalg.norm(np.diff(world[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)).max()))
    if i in (0,len(ts)-1):ends.append(world)
   slide=0.
   for leg,v in points.items():
    v=np.array(v);v[:,2]+=g['stride']/duration*ts;phase=(ts/duration-g['touchdown'][leg])%1;phase[abs(phase-1)<1e-6]=0;mask=phase<=g['stance_fraction']+1e-6;valid=mask[1:]&mask[:-1];speed=np.linalg.norm(np.diff(v,axis=0),axis=1)/np.diff(ts);slide=max(slide,float(speed[valid].max(initial=0)))
   seam=float(abs(ends[0]-ends[-1]).max());assert floor>=-.0005 and slide<.005 and length_error<5e-6 and seam<2e-6,(actor,clip,floor,slide,length_error,seam)
   action={'Walk':'walk','Jog':'run','Gallop':'gallop'}[clip];assert mapping['actions'][action]==clip and clip in mapping['loopingClips'];assert abs(mapping['strideMetresPerSecond'][action]-g['stride']/duration*registry[actor]['import']['scale'])<1e-6
   row['clips'][clip].update(minimum_surface_height=floor,max_supported_paw_speed=slide,native_length_error=length_error,loop_error=seam)
  for clip in ['Sword_Attack','Death_A']:
   duration=a.duration(clip);ts=np.linspace(0,duration,round(duration*384)+1);t,q,sc,mw=a.sample(clip,ts);points={leg:[] for leg in p['sole_vertices']};floor=1e9;length_error=0.
   for i,tt in enumerate(ts):
    world=a.world(t[i],q[i],sc[i]);surface=a.skin(world,{n:v[i] for n,v in mw.items()});floor=min(floor,float(surface[:,1].min()))
    for leg,ids in p['sole_vertices'].items():points[leg].append(surface[ids].mean(0))
    for chain in p['serial_chains'].values():length_error=max(length_error,float(abs(np.linalg.norm(np.diff(world[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)).max()))
   slide=0.
   for leg,vs in points.items():
    if clip=='Death_A':mask=ts<=(.50 if leg.startswith('fore') else .67)+1e-6
    else:
     e=p['attack_contacts']['fore' if leg.startswith('fore') else 'hind'];mask=(ts<=e['release']+1e-6)|((ts>=e['land']-1e-6)&(ts<=e['recover_start']+1e-6))|(ts>=e['recover_end']-1e-6)
    speed=np.linalg.norm(np.diff(vs,axis=0),axis=1)/np.diff(ts);slide=max(slide,float(speed[mask[1:]&mask[:-1]].max(initial=0)))
   start=1.45 if clip=='Sword_Attack' else 2.05;ht,hq,hs,_=a.sample(clip,[start,(start+duration)/2,duration]);hw=[a.world(ht[i],hq[i],hs[i]) for i in range(3)];held=max(float(abs(w-hw[0]).max()) for w in hw)
   assert floor>=-.0005 and slide<.005 and length_error<5e-6 and held<2e-6,(actor,clip,floor,slide,length_error,held)
   row['clips'][clip].update(minimum_surface_height=floor,max_supported_paw_speed=slide,native_length_error=length_error,terminal_hold_error=held)
  patch=patches[actor];core=patch['abdomen_vertex_ids'];head=patch['rigid_face_vertex_ids'];rest_volume=ConvexHull(a.vertices[core]).volume;head_error=attachment_error=0.;vol=[]
  assert a.parts[0]['joints'].shape[1]==8
  for clip in ['Walk','Jog','Sword_Attack','Death_A']:
   ts=np.linspace(0,a.duration(clip),49);tt,qq,ss,mm=a.sample(clip,ts)
   for i in range(len(ts)):
    world=a.world(tt[i],qq[i],ss[i]);surface=a.skin(world,{n:v[i] for n,v in mm.items()});vol.append(ConvexHull(surface[core]).volume/rest_volume);expected=(world[patch['head_node']]@np.linalg.inv(a.rest[patch['head_node']])@np.c_[a.vertices[head],np.ones(len(head))].T).T[:,:3];head_error=max(head_error,float(abs(expected-surface[head]).max()))
    if 'attachment_node' in patch:
     ids=patch['attachment_vertex_ids'];n=patch['attachment_node'];expected=(world[n]@np.linalg.inv(a.rest[n])@np.c_[a.vertices[ids],np.ones(len(ids))].T).T[:,:3];attachment_error=max(attachment_error,float(abs(expected-surface[ids]).max()))
  assert .98<min(vol)<=max(vol)<1.02 and head_error<3e-6 and attachment_error<3e-6,(actor,min(vol),max(vol),head_error,attachment_error)
  row['skin_patches']={'abdomen_volume_range':[min(vol),max(vol)],'rigid_face_error':head_error,'attachment_error':attachment_error}
  contact_report={}
  for clip in ['Walk','Jog','Sword_Attack','Death_A']:
   duration=a.duration(clip);ts=np.linspace(0,duration,round(duration*192)+1);tt,qq,ss,mm=a.sample(clip,ts);surfaces=[];worlds=[]
   for i in range(len(ts)):
    world=a.world(tt[i],qq[i],ss[i]);worlds.append(world);surfaces.append(a.skin(world,{n:v[i] for n,v in mm.items()}))
   surfaces=np.array(surfaces);metrics={}
   for leg,frame in contact_frames[actor].items():
    if clip in p['gaits']:
     g=p['gaits'][clip];phase=(ts/duration-g['touchdown'][leg])%1;phase[abs(phase-1)<1e-8]=0;support=phase<=g['stance_fraction']+1e-8;speed=g['stride']/duration
    elif clip=='Death_A':support=ts<=(.50 if leg.startswith('fore') else .67)+1e-8;speed=0.
    else:
     e=p['attack_contacts']['fore' if leg.startswith('fore') else 'hind'];support=(ts<=e['release']+1e-8)|((ts>=e['land']-1e-8)&(ts<=e['recover_start']+1e-8))|(ts>=e['recover_end']-1e-8);speed=0.
    ids=frame['rigid_contact_vertices'];normal=np.array(frame['native_up']);wrist=p['chains'][leg][-1];tilt=0.
    for i in np.flatnonzero(support):
     n=(worlds[i][wrist]@np.linalg.inv(a.rest[wrist]))[:3,:3]@normal;tilt=max(tilt,float(np.rad2deg(np.arccos(np.clip(n[1]/np.linalg.norm(n),-1,1)))))
    supported=surfaces[support];lows=np.array([supported[:,v,1].min(1) for v in frame['digit_contact_groups'].values()]).T;spread=float(np.ptp(lows,axis=1).max());gap=float(lows.max()-p['floor']);low=float(supported[:,ids,1].min());points=surfaces[:,ids].copy();points[:,:,2]+=speed*ts[:,None];valid=support[:-1]&support[1:];velocity=np.linalg.norm(np.diff(points,axis=0),axis=2)/np.diff(ts)[:,None];slide=float(velocity[valid].max(initial=0));transition=frame['wrist_transition_vertices'];clearance=float(supported[:,transition,1].min()-p['floor']) if transition else None
    assert tilt<.01 and spread<.006*p['height'] and gap<.010*p['height'] and low>p['floor']-.00001 and slide<.005,(actor,clip,leg,tilt,spread,gap,low,slide)
    if transition:assert clearance>.07*p['height'],(actor,clip,leg,'wrist transition entered contact',clearance)
    metrics[leg]={'palm_tilt_degrees':tilt,'toe_underside_spread':spread,'highest_toe_pad_gap':gap,'full_contact_surface_speed':slide,'wrist_transition_clearance':clearance,'digit_patches':len(frame['digit_contact_groups'])}
   contact_report[clip]=metrics
  row['all_paw_contact']=contact_report
  report['actors'][actor]=row;print(actor,'PASS all seven slots and two gaits',flush=True)
 if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
 print('LIZARD_NATIVE PASS 28 slots, 16 authored actions')
if __name__=='__main__':main()
