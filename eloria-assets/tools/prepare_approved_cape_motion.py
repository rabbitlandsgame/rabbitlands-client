#!/usr/bin/env python3
"""Rebuild Rabbit Lands approved cape fits and native-time bone motion data.

Uses only the portable approved-v100 source package. It never modifies actor
meshes, skeletons, body clips, materials, textures or private authoring files.
Requires NumPy. All binary arrays are little endian; descriptor counts are
scalar elements. The runtime supplies transition inertialization and guards.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DTYPES={'float32':'<f4','int32':'<i4'}
ACTIVE=np.array([j for j in range(12) if j%4!=0])

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def lerp_samples(times:np.ndarray,values:np.ndarray,query:np.ndarray)->np.ndarray:
 flat=values.reshape(len(times),-1)
 return np.stack([np.interp(query,times,flat[:,j]) for j in range(flat.shape[1])],axis=1).reshape(len(query),12,3)
def basis(phase:np.ndarray,harmonics:int=3)->np.ndarray:
 columns=[np.ones(len(phase))]
 for k in range(1,harmonics+1):columns.extend([np.cos(2*np.pi*k*phase),np.sin(2*np.pi*k*phase)])
 return np.stack(columns,axis=1)
def regions(C:np.ndarray,height:np.ndarray)->dict:
 masks={'hem':height<.65,'mid':(height>=.65)&(height<1.2),'free':height<1.3}
 return {name:C[mask][::max(1,int(mask.sum()/600))] for name,mask in masks.items()}
def fields(C:np.ndarray,T:np.ndarray)->np.ndarray:return np.einsum('vj,tjk->tvk',C,T,optimize=True)
def metrics(C:dict,reference:np.ndarray,predicted:np.ndarray)->dict:
 result={}
 for name,W in C.items():
  a=fields(W,reference);b=fields(W,predicted);a95=float(np.quantile(np.linalg.norm(a,axis=2),.95));b95=float(np.quantile(np.linalg.norm(b,axis=2),.95));ad=a-a.mean(0);bd=b-b.mean(0);den=float(np.sqrt(np.sum(ad*ad)*np.sum(bd*bd)));result[name]={'approved_p95_m':a95,'periodic_p95_m':b95,'p95_ratio':b95/max(a95,1e-12),'temporal_correlation':float(np.sum(ad*bd)/den) if den>1e-20 else 1.,'rms_error_m':float(np.sqrt(np.mean((a-b)**2)))}
 return result

def periodic(times,T,C,height,clip,start,window,peak_window):
 mask=(times>=window[0])&(times<=window[1]);native_time=(times[mask]-start)/30.*clip['playback_speed'];phase=(native_time/clip['duration'])%1;design=basis(phase);coef=np.linalg.lstsq(design,T[mask].reshape(mask.sum(),36),rcond=None)[0];raw=(design@coef).reshape(-1,12,3);W=regions(C,height);raw_metrics=metrics(W,T[mask],raw)
 def gain_values(values,gain):
  a=values.copy();a[:,ACTIVE]*=gain;return a
 def target_ratio(gain):
  m=metrics(W,T[mask],gain_values(raw,gain));return min(m['hem']['p95_ratio'],m['mid']['p95_ratio'])
 lo,hi=1.,1.10
 if target_ratio(lo)<.95:
  for _ in range(22):
   mid=(lo+hi)/2
   if target_ratio(mid)<.95:lo=mid
   else:hi=mid
  gain=hi
 else:gain=1.
 intervals=max(8,int(round(clip['duration']*120)));sample_phase=np.linspace(0,1,intervals+1);table=(basis(sample_phase)@coef).reshape(-1,12,3);table=gain_values(table,gain)
 # Never exceed the accepted steady source's peak excursion in any free band.
 pmask=(times>=peak_window[0])&(times<=peak_window[1]);source_peak={name:float(np.linalg.norm(fields(weights,T[pmask]),axis=2).max()) for name,weights in W.items()}
 def peak_ok(values):return all(float(np.linalg.norm(fields(weights,values),axis=2).max())<=source_peak[name]*1.005+1e-7 for name,weights in W.items())
 if not peak_ok(table):
  lo,hi=1.,gain
  for _ in range(22):
   mid=(lo+hi)/2;candidate=gain_values((basis(sample_phase)@coef).reshape(-1,12,3),mid)
   if peak_ok(candidate):lo=mid
   else:hi=mid
  gain=lo;table=gain_values((basis(sample_phase)@coef).reshape(-1,12,3),gain)
 # Duplicate the endpoint and make the adjacent finite slopes agree as well.
 table[-1]=table[0];step=.5*(table[1]-table[-2]);table[1]=table[0]+step;table[-2]=table[0]-step;table=np.asarray(table,dtype='<f4');table[-1]=table[0]
 predicted=gain_values(raw,gain);m=metrics(W,T[mask],predicted);dt=clip['duration']/intervals;velocity_error=float(np.linalg.norm((table[1]-table[0])-(table[-1]-table[-2]),axis=1).max()/dt);report={'method':'three-harmonic average by original body-clip phase','fit_source_frames':window,'peak_source_frames':peak_window,'harmonics':3,'lower9_gain':gain,'row0_gain':1.,'amplitude_before_gain':raw_metrics,'amplitude_after_gain':m,'target_min_hem_mid_p95_ratio':.95,'gain_limit':1.10,'source_peak_limit_factor':1.005,'source_peak_m':source_peak,'periodic_peak_m':{name:float(np.linalg.norm(fields(weights,table),axis=2).max()) for name,weights in W.items()},'endpoint_position_error_m':float(np.abs(table[-1]-table[0]).max()),'endpoint_native_velocity_error_m_s':velocity_error,'projection_is_not_exact_whole_episode':True}
 assert np.isfinite(table).all() and np.array_equal(table[0],table[-1])
 return table,report

def build(source:Path)->tuple[dict,dict]:
 raw_catalog=(source/'source-catalog.json').read_bytes();src=json.loads(raw_catalog);episode=source/src['motion_source']['file'];assert sha(episode.read_bytes())==src['motion_source']['sha256']
 with np.load(episode,allow_pickle=False) as f:E={k:f[k] for k in f.files}
 t=E['times'].astype(float);blob=bytearray();files={};catalog={'schema_version':1,'bones':src['bones'],'space':src['space'],'binary':src['binary'],'reference_rig':src['reference_rig'],'reference_rest':src['reference_rest'],'materials':src['materials'],'fits':{},'motion':{'file':'motion.bin','profiles':{}},'source':{'package':'eloria-assets/source/capes/approved-v100','catalog_sha256':sha(raw_catalog),'episode_sha256':src['motion_source']['sha256'],'approved':src['approved_source'],'generator':'eloria-assets/tools/prepare_approved_cape_motion.py','generator_sha256':sha(Path(__file__).read_bytes())},'transition_policy':{'inertialization_tau_seconds':.12,'idle_to_locomotion_seconds':11/30.,'locomotion_to_idle_seconds':.6,'unrecognized_state':'bridged legacy writer on approved fit for unsupported or cinematic states','inactive_quality_or_crowd':'hold complete approved idle pose','mounted_state':'qualified legacy geometry, skin and solver','montage_source_body_animations_replaced':False},'provenance':src['provenance']}
 def append(values):
  a=np.asarray(values,dtype='<f4');offset=len(blob);blob.extend(a.tobytes());return {'offset':offset,'count':int(a.size)}
 for look in ['wardrobe','armour']:
  fit=copy.deepcopy(src['fits'][look]);data=(source/fit['file']).read_bytes();assert sha(data)==fit['sha256'];fit['file']=look+'-fit.bin';files[fit['file']]=data;catalog['fits'][look]=fit
  approved=E[look+'_approved_translations'].astype(float);intrinsic=E[look+'_intrinsic_translations'].astype(float);entry=E[look+'_entry_corrections'].astype(float);C=E[look+'_control_weights'];height=E[look+'_reference_height'];idle=lerp_samples(t,approved,np.array([150.]))[0];profile={'idle':idle.astype('<f4').reshape(-1).tolist(),'clips':{}}
  for clip in src['clips'][look]:
   action=clip['action'];duration=float(clip['duration']);n=max(2,int(round(duration*120))+1);native_t=np.linspace(0,duration,n);report=None
   if action=='idle':values=np.repeat(idle[None],2,axis=0);n=2;loop=True
   elif action in ['walk','run']:
    start=src['motion_source']['phase_starts'][action];values,report=periodic(t,approved,C,height,clip,start,src['motion_source']['fit_windows'][action],src['motion_source']['peak_windows'][action]);n=len(values);loop=True
   else:
    start=src['motion_source']['phase_starts'][action];frame_query=start+native_t/clip['playback_speed']*30;values=lerp_samples(t,intrinsic,frame_query);loop=False
   info={'duration':duration,'loop':loop,'samples':n,'values':append(values),'action':action,'reference_playback_rate':clip['playback_speed'],'clock':'original native clip seconds','all12_controls_written':True}
   if report:info['validation']=report
   if action in ['walk','run']:
    # Entry-only hand clearance is not part of a repeating gait. It is applied
    # after state blending and follows unwrapped native time from action entry.
    real_duration=.6;entry_duration=real_duration*clip['playback_speed'];count=max(2,int(round(entry_duration*120))+1);nt=np.linspace(0,entry_duration,count);query=src['motion_source']['phase_starts'][action]+nt/clip['playback_speed']*30;values_entry=lerp_samples(t,entry,query);values_entry[-1]=0;info['entry']={'duration':entry_duration,'loop':False,'samples':count,'values':append(values_entry),'clock':'unwrapped native seconds since action entry','composition':'add after state blend; never repeat on body loop'}
   profile['clips'][clip['clip']]=info
  catalog['motion']['profiles'][look]=profile
 files['motion.bin']=bytes(blob);catalog['motion']['bytes']=len(blob);catalog['motion']['sha256']=sha(bytes(blob));files['catalog.json']=(json.dumps(catalog,indent=2)+chr(10)).encode();return catalog,files

def main()->int:
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,default=ROOT/'eloria-assets/source/capes/approved-v100');parser.add_argument('--output',type=Path,default=ROOT/'godot-client/data/actors/cape_motion');parser.add_argument('--check',action='store_true');args=parser.parse_args();catalog,files=build(args.source)
 if args.check:
  different=[name for name,data in files.items() if not (args.output/name).exists() or (args.output/name).read_bytes()!=data]
  if different:raise SystemExit('Cape motion outputs differ: '+', '.join(different))
  print('Approved cape motion outputs match portable sources.')
 else:
  args.output.mkdir(parents=True,exist_ok=True)
  for name,data in files.items():
   if name=='catalog.json':continue
   (args.output/name).write_bytes(data)
  target=args.output/'catalog.json';temp=args.output/'catalog.json.tmp';temp.write_bytes(files['catalog.json']);temp.replace(target)
  print('Prepared approved cape fits and native-time motion:',len(files['motion.bin']),'motion bytes')
 for look,profile in catalog['motion']['profiles'].items():
  for name,clip in profile['clips'].items():
   if 'validation'in clip:
    m=clip['validation'];print(look,name,'gain',round(m['lower9_gain'],5),'hem/mid p95',round(m['amplitude_after_gain']['hem']['p95_ratio'],4),round(m['amplitude_after_gain']['mid']['p95_ratio'],4))
 return 0
if __name__=='__main__':raise SystemExit(main())
