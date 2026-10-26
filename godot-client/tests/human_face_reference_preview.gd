extends SceneTree
## Production actor reference review: central presets, both tiers, three views.
## RL_FACE_REFERENCE_OUTPUT selects ignored output; image aspect stays square.
## RL_FACE_REFERENCE_DETAIL=1 gives close feature views and both light angles;
## RL_FACE_REFERENCE_PALETTE=1 also samples three iris/skin combinations.
const PRESETS=preload("res://src/actors/human_portrait_presets.gd")
var stage:Node3D
var camera:Camera3D
var light:DirectionalLight3D
var output:String
var records:=[]
var detail_review:=false
func _init() -> void:call_deferred("run")
func run() -> void:
 output=OS.get_environment("RL_FACE_REFERENCE_OUTPUT")
 detail_review=OS.get_environment("RL_FACE_REFERENCE_DETAIL")=="1"
 if output.is_empty():output=ProjectSettings.globalize_path("res://test-artifacts/human-face-reference")
 DirAccess.make_dir_recursive_absolute(output)
 root.size=Vector2i(840,840);stage=Node3D.new();root.add_child(stage)
 var env:=WorldEnvironment.new();env.environment=Environment.new();env.environment.background_mode=Environment.BG_COLOR;env.environment.background_color=Color("353b40");env.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR;env.environment.ambient_light_color=Color("c5c9cf");env.environment.ambient_light_energy=.48;stage.add_child(env)
 light=DirectionalLight3D.new();light.rotation_degrees=Vector3(-25,-35,0);light.light_energy=1.1;light.light_color=Color("fff0de");stage.add_child(light)
 var fill:=DirectionalLight3D.new();fill.rotation_degrees=Vector3(-20,145,0);fill.light_energy=.30;fill.light_color=Color("bbcfdb");stage.add_child(fill)
 camera=Camera3D.new();camera.projection=Camera3D.PROJECTION_ORTHOGONAL;camera.size=.25 if detail_review else .46;camera.cull_mask=3;camera.current=true;stage.add_child(camera)
 var models:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
 var equipment:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
 var animations:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
 for name:String in ["Rowan","Mira","Tavi"]:
  var actor:=ReplicatedActor3D.new();actor.apply_render_quality(1,true);stage.add_child(actor)
  var appearance:=PRESETS.appearance(name)
  var source_start:=Time.get_ticks_usec()
  var errors:=actor.configure({"actor_id":9901,"x":0,"y":0,"rotation":0,"kind":1,"name":"","appearance":appearance,"equipment_visuals":{}},CoordinateAdapter.new({"walkingHeight":0.0}),models["luminous_female" if name=="Mira" else "luminous_male"],animations,equipment)
  var source_usec:=Time.get_ticks_usec()-source_start
  actor.set_process(false);actor.set_physics_process(false);actor.rotation.y=PI;actor._advance_facing_offset(1)
  for node:Node in actor.get_children():
   if node is Node3D and node.name!="NativeModel":(node as Node3D).hide()
  for level:int in [1,2]:
   var start:=Time.get_ticks_usec();actor.apply_render_quality(level,true);var usec:=Time.get_ticks_usec()-start
   actor.play_action(&"idle",true);actor.animation_player.seek(.4,true);actor.animation_player.pause();actor.get_skeleton().force_update_all_bone_transforms()
   var skeleton:=actor.get_skeleton();var focus:=skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin)+Vector3(0,.055 if detail_review else .075,0)
   for angle:String in ["front","threequarter","profile"]:
    camera.position=focus+{"front":Vector3(0,0,1),"threequarter":Vector3(.62,.035,1) if detail_review else Vector3(.75,.32,1),"profile":Vector3(1,0,.015)}[angle];camera.look_at(focus)
    await capture(name.to_lower()+"-"+("high" if level==2 else "medium")+"-"+angle)
   if level==2:
    light.rotation_degrees.y=55
    for angle:String in (["front","threequarter","profile"] if detail_review else ["threequarter"]):
     camera.position=focus+{"front":Vector3(0,0,1),"threequarter":Vector3(.62,.035,1) if detail_review else Vector3(.75,.32,1),"profile":Vector3(1,0,.015)}[angle];camera.look_at(focus)
     await capture(name.to_lower()+"-high-alternate-light"+("-"+angle if detail_review else ""))
    light.rotation_degrees.y=-35
    if OS.get_environment("RL_FACE_REFERENCE_PALETTE")=="1":
     for choice:int in [0,1,2]:
      var variant:=appearance.duplicate()
      variant.eyes=choice;variant.skin=[0,3,5][choice]
      actor.apply_appearance_variants(variant)
      actor.play_action(&"idle",true);actor.animation_player.seek(.4,true);actor.animation_player.pause();actor.get_skeleton().force_update_all_bone_transforms()
      camera.position=focus+Vector3(.32,.015,1);camera.look_at(focus)
      await capture(name.to_lower()+"-high-eye-"+str(choice)+"-skin-"+str(variant.skin))
   records.append({"name":name,"appearance":appearance,"level":level,"configure_usec":source_usec,"quality_switch_usec":usec,"errors":errors,"geometry":geometry_metrics(actor),"cache":HighPortraitAppearance.cache_metrics()})
  actor.free();await process_frame
 FileAccess.open(output.path_join("manifest.json"),FileAccess.WRITE).store_string(JSON.stringify({"records":records},"  "))
 quit()
func capture(name:String) -> void:
 for _frame:int in 5:await process_frame
 await RenderingServer.frame_post_draw
 root.get_texture().get_image().save_png(output.path_join(name+".png"));print("FACE REFERENCE ",name)

func geometry_metrics(actor:ReplicatedActor3D) -> Dictionary:
 var result:={};var skeleton:=actor.get_skeleton();var head:=skeleton.find_bone("Head")
 for part:String in ["body","eyes","eyebrows","scalp"]:
  var node:=actor._native_model.find_child(part,true,false) as MeshInstance3D
  var head_bind:=-1
  for bind:int in node.skin.get_bind_count():
   if node.skin.get_bind_bone(bind)==head or node.skin.get_bind_name(bind)==&"Head":head_bind=bind
  var triangles:=0;var head_triangles:=0;var vertices:=0;var array_bytes:=0
  for surface:int in node.mesh.get_surface_count():
   var arrays:=node.mesh.surface_get_arrays(surface);var points:PackedVector3Array=arrays[Mesh.ARRAY_VERTEX];var indices:PackedInt32Array=arrays[Mesh.ARRAY_INDEX];var bones:PackedInt32Array=arrays[Mesh.ARRAY_BONES];var weights:PackedFloat32Array=arrays[Mesh.ARRAY_WEIGHTS];var width:=int(weights.size()/points.size())
   vertices+=points.size();triangles+=indices.size()/3
   for attr:Variant in arrays:
    if attr!=null:array_bytes+=attr.to_byte_array().size()
   for triangle:int in range(0,indices.size(),3):
    var weight:=0.0
    for corner:int in 3:
     var index:=indices[triangle+corner]
     for influence:int in width:
      if bones[index*width+influence]==head_bind:weight+=weights[index*width+influence]
    if weight/3>.45:head_triangles+=1
  result[part]={"triangles":triangles,"head_triangles":head_triangles,"vertices":vertices,"array_bytes":array_bytes}
 return result
