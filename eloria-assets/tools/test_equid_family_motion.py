"""Check the installed reviewed equid family against independent native witnesses."""
from pathlib import Path
import argparse,json,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset
ROOT=Path(__file__).resolve().parents[2]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
 profiles=json.loads((ROOT/'docs/qa/equid-family-motion/actors.json').read_text())
 witnesses=json.loads((ROOT/'godot-client/tests/fixtures/equid_family_motion_worlds.json').read_text())
 registry=json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
 assert len(profiles)==len(witnesses)==6
 report={'passed':True,'actors':{}}
 for actor,p in profiles.items():
  a=NativeShapeAsset(ROOT/p['runtime_path']);witness=witnesses[actor];assert digest(a.path)==p['sha256']==witness['sha256'];assert len(a.animations)==8
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
   row['clips'][clip].update(minimum_surface_height=floor,max_supported_hoof_speed=slide,native_length_error=length_error,loop_error=seam)
  report['actors'][actor]=row;print(actor,'PASS all eight slots and three gaits',flush=True)
 if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
 print('EQUID_FAMILY_NATIVE PASS 48 slots, 18 gaits')
if __name__=='__main__':main()
