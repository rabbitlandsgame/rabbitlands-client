extends SceneTree
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const HIGH := preload("res://src/actors/high_hair_appearance.gd")
const PROPS := preload("res://src/actors/character_proportions.gd")
const GROOM := preload("res://src/actors/portrait_groom.gd")
var output:=""
var stage:Node3D
var camera:Camera3D
var failures:=0
var checks:=0
var records:Array=[]
var quick:=false
func _init()->void:call_deferred("run")
func expect(ok:bool,label:String)->void:
	checks+=1
	if not ok:
		failures+=1
		push_error(label)
func freeze(actor:ReplicatedActor3D,action:StringName=&"idle",time:float=0.4)->void:
	actor.play_action(action,true)
	actor.animation_player.seek(time,true)
	actor.animation_player.pause()
	actor.get_skeleton().force_update_all_bone_transforms()
func focus(actor:ReplicatedActor3D)->Vector3:
	var rig:=actor.get_skeleton()
	return rig.to_global(rig.get_bone_global_pose(rig.find_bone("Head")).origin)+Vector3(0,0.075,0)
func capture(actor:ReplicatedActor3D,name:String,angle:String)->void:
	if DisplayServer.get_name()=="headless":return
	var target:=focus(actor)
	camera.position=target+{"front":Vector3(0,0.03,1),"side":Vector3(1,0.03,0.002),"threequarter":Vector3(0.40,0.05,1.0),"isometric":Vector3(0.62,0.30,0.9)}[angle]
	camera.look_at(target)
	for frame:int in 6:await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name+"-"+angle+".png"))==OK,"capture "+name)
func geometry(node:MeshInstance3D,name:String)->void:
	var vertices:=0
	var triangles:=0
	var maximum_error:=0.0
	var packed:=0
	for surface:int in node.mesh.get_surface_count():
		var data:=RenderingServer.mesh_get_surface(node.mesh.get_rid(),surface)
		for key:String in ["vertex_data","attribute_data","skin_data","index_data","blend_shape_data"]:
			var buffer:Variant=data.get(key)
			if buffer is PackedByteArray:packed+=buffer.size()
		var a:=node.mesh.surface_get_arrays(surface)
		var p:PackedVector3Array=a[Mesh.ARRAY_VERTEX]
		var n:PackedVector3Array=a[Mesh.ARRAY_NORMAL]
		var idx:PackedInt32Array=a[Mesh.ARRAY_INDEX]
		var weights:PackedFloat32Array=a[Mesh.ARRAY_WEIGHTS]
		var bones:PackedInt32Array=a[Mesh.ARRAY_BONES]
		var stride:int=weights.size()/p.size()
		vertices+=p.size()
		triangles+=idx.size()/3
		for i:int in p.size():
			expect(p[i].is_finite() and n[i].is_finite() and n[i].length()>0.98,name+" finite geometry")
			var total:=0.0
			for j:int in stride:
				total+=weights[i*stride+j]
				expect(bones[i*stride+j]>=0 and bones[i*stride+j]<node.skin.get_bind_count(),name+" bind range")
			maximum_error=maxf(maximum_error,absf(total-1.0))
		for index:int in idx:expect(index>=0 and index<p.size(),name+" index range")
	expect(maximum_error<0.0001,name+" normalized weights")
	records.append({"mesh":name,"vertices":vertices,"triangles":triangles,"weight_error":maximum_error,"packed_buffer_bytes":packed,"surfaces":node.mesh.get_surface_count()})
func run()->void:
	quick=OS.get_environment("RL_GROOM_QUICK_RENDER")=="1"
	output=OS.get_environment("RL_GROOM_REFERENCE_OUTPUT")
	if output.is_empty():output=ProjectSettings.globalize_path("res://test-artifacts/groom-reference")
	DirAccess.make_dir_recursive_absolute(output)
	var network:=root.get_node_or_null("Network")
	if network!=null:network.block_for_hud_preview()
	root.size=Vector2i(900,900)
	stage=Node3D.new()
	root.add_child(stage)
	var env:=WorldEnvironment.new()
	env.environment=Environment.new()
	env.environment.background_mode=Environment.BG_COLOR
	env.environment.background_color=Color("263039")
	env.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color=Color("b8c3d0")
	env.environment.ambient_light_energy=0.62
	stage.add_child(env)
	var key:=DirectionalLight3D.new()
	key.rotation_degrees=Vector3(-32,-28,0)
	key.light_energy=1.15
	key.light_color=Color("ffe9d1")
	stage.add_child(key)
	var fill:=DirectionalLight3D.new()
	fill.rotation_degrees=Vector3(-20,145,0)
	fill.light_energy=0.45
	fill.light_color=Color("a1beca")
	stage.add_child(fill)
	camera=Camera3D.new()
	camera.current=true
	camera.cull_mask=3
	camera.projection=Camera3D.PROJECTION_ORTHOGONAL
	camera.size=0.58
	stage.add_child(camera)
	var models:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var anim:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for name:String in ["Rowan","Mira","Tavi"]:
		var sex:="female" if name=="Mira" else "male"
		var actor:=ReplicatedActor3D.new()
		stage.add_child(actor)
		actor.apply_render_quality(1,true)
		var look:=PRESETS.appearance(name)
		var errors:=actor.configure({"actor_id":9950,"kind":1,"x":0,"y":0,"rotation":0,"name":"","appearance":look,"equipment_visuals":{}},CoordinateAdapter.new(),models["luminous_"+sex],anim,equipment)
		expect(errors.is_empty(),name+" configure")
		actor.rotation.y=PI
		actor._advance_facing_offset(1.0)
		actor.set_process(false)
		actor.set_physics_process(false)
		for child:Node in actor.get_children():
			if child is Node3D and child.name!="NativeModel":(child as Node3D).hide()
		freeze(actor)
		var hair:MeshInstance3D=HIGH._hair_nodes(actor._native_model)[0]
		var medium:=hair.mesh
		for level:int in ([2] if quick else [1,2]):
			var before_fit:int=HIGH.cache_metrics().cold_fit_usec
			var started:=Time.get_ticks_usec()
			actor.apply_render_quality(level,true)
			records.append({"look":name,"level":level,"whole_quality_apply_usec":Time.get_ticks_usec()-started,"hair_beard_fit_usec":int(HIGH.cache_metrics().cold_fit_usec)-before_fit,"cache":HIGH.cache_metrics()})
			if not quick:geometry(hair,name+str(level)+" hair")
			var beard:=actor._native_model.find_child("PortraitFacialHair",true,false) as MeshInstance3D
			if beard!=null and not quick:geometry(beard,name+str(level)+" beard")
			for angle:String in (["front","threequarter"] if quick else ["front","threequarter","side","isometric"]):await capture(actor,name.to_lower()+"-"+str(level),angle)
		if quick:
			actor.free()
			await process_frame
			continue
		for action:StringName in [&"walk",&"run"]:
			freeze(actor,action,0.55)
			await capture(actor,name.to_lower()+"-"+str(action),"isometric")
		actor.apply_render_quality(1,true)
		expect(hair.mesh==medium,name+" exact Medium hair restore")
		# Prime current High source once, then distinguish reused controls from
		# a genuinely new hair-length choice after assets are already warm.
		actor.apply_render_quality(2,true)
		var warm:Array=[]
		for repeat:int in 3:
			var began:=Time.get_ticks_usec()
			actor.apply_appearance_variants(look)
			warm.append(Time.get_ticks_usec()-began)
		var novel:=look.duplicate()
		novel.hair_length=mini(99,int(look.hair_length)+1)
		var began:=Time.get_ticks_usec()
		actor.apply_appearance_variants(novel)
		var new_control_usec:=Time.get_ticks_usec()-began
		began=Time.get_ticks_usec()
		actor.apply_appearance_variants(look)
		records.append({"look":name,"warm_whole_actor_control_usec":warm,"new_length_control_usec":new_control_usec,"return_cached_control_usec":Time.get_ticks_usec()-began})
		if name=="Tavi":
			for field:String in ["face_length","lip_fullness"]:
				for value:int in [0,50,100]:
					var selected:=look.duplicate()
					selected[field]=value
					actor.apply_appearance_variants(selected)
					freeze(actor)
					check_canonical_beard(actor,field+str(value))
					await capture(actor,"tavi-"+field+str(value),"front")
					if value!=50:await capture(actor,"tavi-"+field+str(value),"threequarter")
			actor.apply_appearance_variants(look)
		actor.apply_render_quality(1,true)
		# Low and Medium show size choices without any extra geometry.
		var dimensions:Array=[]
		for value:int in [0,50,100]:
			var selected:=look.duplicate()
			selected.hair_length=value
			selected.hair_volume=value
			var started:=Time.get_ticks_usec()
			actor.apply_appearance_variants(selected)
			freeze(actor)
			var h:MeshInstance3D=HIGH._hair_nodes(actor._native_model)[0]
			dimensions.append({"value":value,"bounds":str(h.mesh.get_aabb()),"vertices":h.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size(),"apply_usec":Time.get_ticks_usec()-started})
			await capture(actor,name.to_lower()+"-medium-size"+str(value),"side")
		records.append({"look":name,"size_choices":dimensions})
		actor.apply_appearance_variants(look)
		actor.apply_render_quality(2,true)
		actor.apply_equipment_visuals({3:143})
		freeze(actor)
		await capture(actor,name.to_lower()+"-helmet","isometric")
		for h:MeshInstance3D in HIGH._hair_nodes(actor._native_model):expect(not h.is_visible_in_tree(),name+" helmet hides every layered lock")
		actor.free()
		await process_frame
	expect(int(HIGH.cache_metrics().mesh_entries)==0,"last High actor releases all grooming derivatives")
	FileAccess.open(output.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"checks":checks,"failures":failures,"records":records},"  "))
	print("GROOM_REFERENCE_RESULT ",checks," checks ",failures," failures")
	quit(1 if failures else 0)

func check_canonical_beard(actor:ReplicatedActor3D,label:String)->void:
	var beard:=actor._native_model.find_child("PortraitFacialHair",true,false) as MeshInstance3D
	expect(beard!=null,label+" beard exists")
	var high_source:Dictionary=beard.get_meta(actor.HIGH_PORTRAIT.META,{})
	var source:Mesh=high_source.get("source",beard.mesh)
	var frame:=PROPS.face_frame(actor._native_model,actor.get_skeleton())
	var eye:=GROOM._eye_height(actor._native_model.find_child("eyes",true,false),actor.get_skeleton(),actor.get_skeleton().get_bone_global_rest(actor.get_skeleton().find_bone("Head")),actor._native_model)
	var witnesses:=0
	var maximum:=0.0
	for surface:int in source.get_surface_count():
		var a:=source.surface_get_arrays(surface)
		var uv:PackedVector2Array=a[Mesh.ARRAY_TEX_UV2]
		var colors:PackedColorArray=a[Mesh.ARRAY_COLOR]
		for i:int in uv.size():
			var p:=Vector3(uv[i].x,uv[i].y,colors[i].b-0.2)
			if p.z<0.025 or absf(p.x)>0.060:continue
			var expected:=GROOM._beard_coverage(p,eye,5,frame.mouth_y)
			var error:=absf(expected-colors[i].r)
			maximum=maxf(maximum,error)
			witnesses+=1
			expect(error<0.006,label+" post-subdivision coverage uses canonical coordinates")
	expect(witnesses>20,label+" enough frontal beard witnesses")
	records.append({"beard_control":label,"canonical_witnesses":witnesses,"max_coverage_error":maximum})
