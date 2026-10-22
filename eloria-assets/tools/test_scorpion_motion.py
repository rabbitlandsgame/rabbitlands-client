"""Check the installed scorpion motion using independent native surface witnesses."""
from pathlib import Path
import sys,json,argparse
import numpy as np
from scipy.spatial import ConvexHull
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset
from video_motion.runtime_validation import surface_sampler
ROOT=Path(__file__).resolve().parents[2]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def poses(a,cl,times,ids=None):
 sample=surface_sampler(a,ids);t,q,s,m=a.sample(cl,times)
 for k,tm in enumerate(times):
  w=a.world(t[k],q[k],s[k]);mm={n:v[k] for n,v in m.items()};yield float(tm),w,mm,sample(w,mm)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path);args=ap.parse_args();profiles=read(ROOT/'docs/qa/scorpion-motion/actors.json');registry=read(ROOT/'godot-client/data/actors/models.json')['models'];report={'passed':True,'scope':'Seven installed slots: off-grid native bone, morph and surface witnesses; complete sharp-tip contacts, mirrored touchdown advances, native segment lengths, floor clearance, supported death and held/loop endpoints. No flat paw metric is applied to pointed claws.','actors':{}}
 assert set(profiles)=={'amethyst_scorpion'}
 for actor,p in profiles.items():
  a=NativeShapeAsset(ROOT/p['runtime_path']);witness=read(ROOT/f'godot-client/tests/fixtures/scorpion-motion/{actor}.json');entry=registry[actor];mapping=read(ROOT/'godot-client'/entry['animationMap'].removeprefix('res://'));h=p['height'];assert digest(a.path)==p['sha256']==witness['sha256'];assert a.d['asset']['extras']['rabbitlands_animation_bake_fps']==4096
  assert entry['scene']==entry['animationLibrary'];assert all(n in a.ids for n in entry['attachments'].values());assert entry['attachments']['body']=='RL_Scorpion_Body' and entry['attachments']['head']=='RL_Scorpion_Head';policy=Path(str(a.path)+'.import').read_text(encoding='utf-8');assert 'animation/fps=4096' in policy and 'meshes/force_disable_compression=true' in policy and '"optimizer/enabled": false' in policy and '"compression/enabled": false' in policy
  row={'sha256':digest(a.path),'clips':{},'contacts':{}};assert len(a.animations)==len(witness['clips'])==7
  for clip,entries in witness['clips'].items():
   bone_error=morph_error=surface_error=0.
   for e,(_,w,m,v) in zip(entries,poses(a,clip,[e['time'] for e in entries],witness['surface_vertex_ids'])):
    for name,expected in e['bones'].items():bone_error=max(bone_error,float(abs(w[a.ids[name]]-np.array(expected).reshape(4,4)).max()))
    for node,expected in e['morph_weights'].items():morph_error=max(morph_error,float(abs(m[int(node)]-expected).max()))
    surface_error=max(surface_error,float(abs(v-e['surface']).max()));assert np.linalg.norm(v-e['reviewed_surface'],axis=1).max()/h<.00015
   assert max(bone_error,morph_error,surface_error)<2e-12,(actor,clip,bone_error,morph_error,surface_error)
   floor=1.;length=0.;rigid=0.;dur=a.duration(clip)
   for tm,w,m,v in poses(a,clip,np.linspace(0,dur,241)):
    floor=min(floor,float(v[:,1].min()/h))
    for chain in [*p['chains'].values(),*p['prepared_anatomy']['pincers'].values(),*p['prepared_anatomy']['palps'].values(),p['prepared_anatomy']['tail']]:length=max(length,float(abs(np.linalg.norm(np.diff(w[chain,:3,3],axis=0),axis=1)-np.linalg.norm(np.diff(a.rest[chain,:3,3],axis=0),axis=1)).max()/h))
    for ids in p['paw_vertices'].values():
     ids=np.array(ids,int);rest=a.vertices[ids];vv=v[ids];rigid=max(rigid,float(abs(np.linalg.norm(vv-vv[0],axis=1)-np.linalg.norm(rest-rest[0],axis=1)).max()/h))
    for piece in p['rigid_pieces']:
     ids=np.array(piece['vertices'],int);node=piece['owner'];expected=(w[node]@np.linalg.inv(a.rest[node])@np.c_[a.vertices[ids],np.ones(len(ids))].T).T[:,:3];rigid=max(rigid,float(np.linalg.norm(v[ids]-expected,axis=1).max()/h))
    back=(a.rest[p['body_node']]@np.linalg.inv(w[p['body_node']])@np.c_[v[p['tail_vertices']],np.ones(len(p['tail_vertices']))].T).T[:,:3];assert abs(back[:,0].mean()-a.rest[p['body_node'],0,3])/h<.02
    if clip in ['Sword_Attack','Death_A']:
     head=a.vertices[p['head_vertices']];hull=ConvexHull(head);headnode=p['prepared_anatomy']['ids']['Head'];back=(a.rest[headnode]@np.linalg.inv(w[headnode])@np.c_[v,np.ones(len(v))].T).T[:,:3]
     for ids in [p['stinger_vertices'],*p['pincer_vertices'].values()]:assert ((back[ids]@hull.equations[:,:3].T+hull.equations[:,3]).max(1)>=-.01*h).all(),(actor,clip,tm,'head intrusion')
   assert floor>-.00003 and length<3e-5 and rigid<.00015,(actor,clip,floor,length,rigid)
   row['clips'][clip]={'witness_bone_error':bone_error,'witness_morph_error':morph_error,'witness_surface_error':surface_error,'minimum_floor_over_height':floor,'native_length_error_over_height':length,'complete_blade_rigid_error_over_height':rigid}
  for clip,g in p['gaits'].items():
   dur=g['duration'];speed=g['stride']/dur;times=np.linspace(0,dur,513);allvalues=[];margins=[];minimum_contacts=6;maximum_stance_y=maximum_speed=0.;previous=None
   for tm,w,m,v in poses(a,clip,times):
    active=[leg for leg in p['chains'] if (tm/dur-g['touchdown'][leg])%1<=g['stance_fraction']];minimum_contacts=min(minimum_contacts,len(active));assert len(active)>=3
    points=np.array([v[p['tip_patches'][leg]].mean(0)[[0,2]] for leg in active]);hull=ConvexHull(points);center=w[p['body_node'],[0,2],3];margins.append(float(-(hull.equations[:,:2]@center+hull.equations[:,2]).max()/h));assert margins[-1]>0
    for leg in active:
     ix=p['tip_patches'][leg];maximum_stance_y=max(maximum_stance_y,float(abs(v[ix,1].mean()/h-.001)))
     if previous:
      pt,pv=previous;phase=(tm/dur-g['touchdown'][leg])%1;pp=(pt/dur-g['touchdown'][leg])%1
      if pp<=g['stance_fraction'] and phase>=pp:
       delta=(v[ix]-pv[ix])/(tm-pt);delta[:,2]+=speed;maximum_speed=max(maximum_speed,float(np.linalg.norm(delta,axis=1).max()/h))
    previous=(tm,v)
   assert maximum_stance_y<.00015 and maximum_speed<.02,(actor,clip,maximum_stance_y,maximum_speed)
   balance={}
   for pair in ['fore','mid','hind']:
    events=[]
    for tm,leg in sorted((dur*(g['touchdown'][leg]+cycle),leg) for cycle in [0,1] for leg in [pair+'_left',pair+'_right']):
     _,_,_,v=next(poses(a,clip,[tm%dur]));events.append(float(v[p['tip_patches'][leg],2].mean()+speed*tm))
    advances=np.diff(events);ratio=float(advances.min()/advances.max());assert advances.min()>0 and ratio>.90;balance[pair]={'world_tip_advances':advances.tolist(),'balance':ratio}
   action='walk' if clip=='Walk' else 'run';assert abs(mapping['strideMetresPerSecond'][action]-speed*entry['import']['scale'])<1e-8;assert mapping['playbackSpeeds'][action]==1.;row['contacts'][clip]={'minimum_supporting_legs':minimum_contacts,'minimum_support_margin_over_height':min(margins),'maximum_tip_height_error':maximum_stance_y,'maximum_stance_speed_error':maximum_speed,'mirrored_advances':balance}
  _,_,_,last=next(poses(a,'Death_A',[a.duration('Death_A')]))
  _,_,_,held=next(poses(a,'Death_A',[a.duration('Death_A')*.9]));assert abs(last-held).max()/h<2e-5
  for region,ids in p['body_support_regions'].items():assert last[ids,1].min()/h<.015,(actor,region,'unsupported corpse')
  ys=[w[p['body_node'],1,3] for _,w,_,_ in poses(a,'Death_A',np.linspace(0,a.duration('Death_A'),241))];assert (max(ys)-ys[0])/h<.015
  for clip in ['Walk','Jog','Idle_A','Fighting_Idle']:
   v=list(poses(a,clip,[0.,a.duration(clip)]));assert abs(v[0][-1]-v[-1][-1]).max()/h<.00015
  report['actors'][actor]=row;print(actor,'PASS',flush=True)
 if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
 print('SCORPION_NATIVE PASS 7 slots',flush=True)
if __name__=='__main__':main()
