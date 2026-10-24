"""Fresh Blender import and independent off-grid bone/surface probes.
Run with blender --background --factory-startup --python this_file -- --root REPO --report FILE.
Normal conformance is covered by the Godot check, not this Blender surface check.
"""
import bpy,json,sys,argparse,hashlib
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.kdtree import KDTree

args=sys.argv[sys.argv.index('--')+1:]
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--actor');a=p.parse_args(args)
profiles=json.loads((a.root/'docs/qa/completed-creature-motion/actors.json').read_text());result={'passed':True,'blender':bpy.app.version_string,'actors':{},'scope':'Fresh imports: independent off-grid bone heads and posed surfaces, every available clip. Normals checked separately in current Godot.'}
for actor,profile in profiles.items():
 if a.actor and a.actor!=actor:continue
 bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=240
 path=a.root/profile['runtime_path'];w=json.loads((a.root/'godot-client/tests/fixtures/completed-creature-motion'/(actor+'.json')).read_text());assert hashlib.sha256(path.read_bytes()).hexdigest()==w['sha256']
 bpy.ops.import_scene.gltf(filepath=str(path));objects=list(bpy.data.objects);actions=list(bpy.data.actions)
 clips={cl:next(x for x in actions if x.name==cl or x.name.startswith(cl+'.')) for cl in w['clips']}
 for ob in objects:
  if ob.type=='MESH' and ob.data.shape_keys:
   for block in list(ob.data.shape_keys.key_blocks)[1:]:block.slider_min=-10.;block.slider_max=10.
  if ob.animation_data:
   ob.animation_data.action=None
   for track in ob.animation_data.nla_tracks:track.mute=True
 bone_names=list(next(iter(w['clips'].values()))[0]['bones']);arms=[o for o in objects if o.type=='ARMATURE' and set(bone_names).issubset(o.pose.bones.keys())];assert len(arms)==1,(actor,'physical armature');arm=arms[0]
 def select(cl):
  action=clips[cl]
  for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
  arm.animation_data_create();arm.animation_data.action=action;arm.animation_data.action_slot=next(s for s in action.slots if s.target_id_type=='OBJECT')
  for ob in objects:
   if ob.type!='MESH' or not ob.data.shape_keys:continue
   key=ob.data.shape_keys;key.animation_data_create();key.animation_data.action=None
   for tr in key.animation_data.nla_tracks:tr.mute=True
   for block in list(key.key_blocks)[1:]:block.value=0.
   slots=[s for s in action.slots if s.target_id_type=='KEY']
   if slots:key.animation_data.action=action;key.animation_data.action_slot=slots[0]
 def pose(tm):
  frame=tm*240;scene.frame_set(int(frame),subframe=frame-int(frame));bpy.context.view_layer.update();return bpy.context.evaluated_depsgraph_get()
 def convert(x):return Vector((x[0],-x[2],x[1]))
 mapping_clip=next(iter(w['clips']));entry=w['clips'][mapping_clip][0];select(mapping_clip);deps=pose(entry['time']);points=[]
 for ob in objects:
  if ob.type!='MESH':continue
  ev=ob.evaluated_get(deps)
  for v in ev.data.vertices:points.append((ob,v.index,ev.matrix_world@v.co))
 kd=KDTree(len(points))
 for j,(_,_,v) in enumerate(points):kd.insert(v,j)
 kd.balance();bindings=[];h=w['height']
 for probe,x in enumerate(entry['surface']):
  expected=convert(x);candidates=kd.find_range(expected,.00015*h);best=float('inf');chosen=None
  source_skin=w['surface_skin_influences'][probe];signature=w['surface_source_morph_positions'][probe]
  for _,j,dist in candidates:
   ob,vi,_=points[j];actual={ob.vertex_groups[g.group].name:g.weight for g in ob.data.vertices[vi].groups if g.weight>1e-8};skin_error=sum(abs(actual.get(k,0.)-source_skin.get(k,0.)) for k in set(actual)|set(source_skin));morph_error=0.
   if signature:
    keys=ob.data.shape_keys.key_blocks
    for shape_index,delta in enumerate(signature):
     local=keys[shape_index+1].data[vi].co-keys[0].data[vi].co;morph_error=max(morph_error,(ob.matrix_world.to_3x3()@local-convert(delta)).length/h)
   score=dist/h+skin_error+morph_error
   if score<best:best=score;chosen=j;errors=(skin_error,morph_error)
  assert chosen is not None and errors[0]<.0003 and errors[1]<.0002,(actor,'skin/morph identity',probe,chosen,errors if chosen is not None else None)
  bindings.append(points[chosen][:2])
 metrics={};maxbone=0.;maxsurface=0.
 for clip,entries in w['clips'].items():
  select(clip);be=0.;se=0.
  for entry in entries:
   deps=pose(entry['time'])
   for (ob,vi),x in zip(bindings,entry['surface']):
    ev=ob.evaluated_get(deps);se=max(se,(ev.matrix_world@ev.data.vertices[vi].co-convert(x)).length/h)
   for name,values in entry['bones'].items():
    expected=convert((values[3],values[7],values[11]));be=max(be,(arm.matrix_world@arm.pose.bones[name].head-expected).length/h)
  assert se<.00020 and be<.00015,(actor,clip,se,be)
  metrics[clip]={'surface_error_over_height':se,'bone_head_error_over_height':be,'poses':len(entries)};maxbone=max(maxbone,be);maxsurface=max(maxsurface,se)
 result['actors'][actor]={'passed':True,'sha256':w['sha256'],'clips':metrics,'surface_probes':len(bindings),'max_surface_error_over_height':maxsurface,'max_bone_head_error_over_height':maxbone}
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print('BLENDER_CREATURE_PASS',actor,maxsurface,maxbone,flush=True)
print('COMPLETED_CREATURE_BLENDER_PASS',len(result['actors']),flush=True)
