extends SceneTree
const HAIR := preload("res://src/actors/high_hair_appearance.gd")
var failures:=0
var checks:=0
var records:Array=[]
var stage:Node3D
var camera:Camera3D
var output:=""
func _init()->void:call_deferred("run")
func expect(ok:bool,label:String)->void:
	checks+=1
	if not ok:
		failures+=1
		push_error(label)
func capture(name:String)->void:
	for frame:int in 6:await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name+".png"))==OK,"save "+name)
func snapshot(hair:MeshInstance3D)->Dictionary:
	var mats:Array=[]
	for i:int in hair.mesh.get_surface_count():mats.append(hair.get_surface_override_material(i))
	return {"mesh":hair.mesh,"override":hair.material_override,"mats":mats,"skin":hair.skin,"skeleton":hair.skeleton,"transform":hair.transform,"hash":hash(var_to_bytes(hair.mesh.surface_get_arrays(0)))}
func inspect(hair:MeshInstance3D,label:String,original:Dictionary)->void:
	expect(hair.skin==original.skin and hair.skeleton==original.skeleton and hair.transform==original.transform,label+" same binding and transform")
	expect(hash(var_to_bytes(original.mesh.surface_get_arrays(0)))==original.hash,label+" source untouched")
	var beforev:=0
	var beforetri:=0
	var afterv:=0
	var aftertri:=0
	var max_error:=0.0
	for surface:int in hair.mesh.get_surface_count():
		var a:=hair.mesh.surface_get_arrays(surface)
		var source:Array=original.mesh.surface_get_arrays(surface)
		var p:PackedVector3Array=a[Mesh.ARRAY_VERTEX]
		var n:PackedVector3Array=a[Mesh.ARRAY_NORMAL]
		var idx:PackedInt32Array=a[Mesh.ARRAY_INDEX]
		var weights:PackedFloat32Array=a[Mesh.ARRAY_WEIGHTS]
		var bones:PackedInt32Array=a[Mesh.ARRAY_BONES]
		var stride:int=weights.size()/p.size()
		beforev+=source[Mesh.ARRAY_VERTEX].size()
		beforetri+=source[Mesh.ARRAY_INDEX].size()/3
		afterv+=p.size()
		aftertri+=idx.size()/3
		expect(stride in [4,8],label+" skin stride")
		for i:int in p.size():
			expect(p[i].is_finite() and n[i].is_finite() and n[i].length()>0.98,label+" finite geometry")
			var total:=0.0
			for j:int in stride:
				total+=weights[i*stride+j]
				expect(bones[i*stride+j]>=0 and bones[i*stride+j]<77,label+" valid joint")
			max_error=maxf(max_error,absf(total-1.0))
		for i:int in idx:expect(i>=0 and i<p.size(),label+" index bounds")
		for slot:int in [Mesh.ARRAY_TEX_UV,Mesh.ARRAY_TEX_UV2,Mesh.ARRAY_COLOR,Mesh.ARRAY_BONES,Mesh.ARRAY_WEIGHTS]:
			if source[slot]!=null:expect(a[slot].slice(0,source[slot].size())==source[slot],label+" original channel unchanged "+str(slot))
	expect(max_error<0.0001,label+" normalized weights")
	records.append({"look":label,"before_vertices":beforev,"before_triangles":beforetri,"after_vertices":afterv,"after_triangles":aftertri,"max_weight_error":max_error})
func run()->void:
	output=OS.get_environment("RL_HIGH_HAIR_OUTPUT")
	if output.is_empty():output=ProjectSettings.globalize_path("res://test-artifacts/high-hair")
	DirAccess.make_dir_recursive_absolute(output)
	var network:=root.get_node_or_null("Network")
	if network!=null:network.block_for_hud_preview()
	var render:=DisplayServer.get_name()!="headless"
	root.size=Vector2i(900,900)
	stage=Node3D.new()
	root.add_child(stage)
	var env:=WorldEnvironment.new()
	env.environment=Environment.new()
	env.environment.background_mode=Environment.BG_COLOR
	env.environment.background_color=Color("1b242b")
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
	camera.projection=Camera3D.PROJECTION_ORTHOGONAL
	camera.size=0.50
	camera.current=true
	camera.cull_mask=3
	stage.add_child(camera)
	var models:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var presets:Array[Dictionary]=[{"id":"rowan","sex":"male","style":1,"detail":1,"color":1},{"id":"mira","sex":"female","style":3,"detail":2,"color":4},{"id":"tavi","sex":"male","style":1,"detail":2,"color":1}]
	for preset:Dictionary in presets:
		var actor:=ReplicatedActor3D.new()
		stage.add_child(actor)
		actor.apply_render_quality(1,false)
		var look:Dictionary={"hair":AppearanceVariants.pack_hair(preset.style,preset.color),"hair_detail":preset.detail,"skin":2,"eyes":2,"facial_hair":5 if preset.id=="tavi" else 0}
		var config:Dictionary=models["luminous_"+preset.sex]
		var errors:=actor.configure({"actor_id":9800,"kind":1,"x":0,"y":0,"rotation":0,"name":"","appearance":look,"equipment_visuals":{}},CoordinateAdapter.new(),config,animations,equipment)
		expect(errors.is_empty(),"actor configures "+preset.id)
		actor.rotation.y=PI
		actor._advance_facing_offset(1.0)
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.play_action(&"idle",true)
		actor.animation_player.seek(0.4,true)
		actor.animation_player.pause()
		actor.get_skeleton().force_update_all_bone_transforms()
		var native:=actor._native_model
		var hair:MeshInstance3D=HAIR._hair_nodes(native)[0]
		var original:=snapshot(hair)
		for mode:String in ["medium","high"]:
			if mode=="high":
				var began:=Time.get_ticks_usec()
				HAIR.apply(native,actor.get_skeleton(),look,config,2)
				records.append({"look":preset.id,"cold_apply_usec":Time.get_ticks_usec()-began})
				inspect(hair,preset.id,original)
			if render:
				var rig:=actor.get_skeleton()
				var focus:=rig.to_global(rig.get_bone_global_pose(rig.find_bone("Head")).origin)+Vector3(0,0.075,0)
				for angle:String in ["front","threequarter","profile"]:
					camera.position=focus+{"front":Vector3(0,0.055,1),"threequarter":Vector3(0.40,0.055,1),"profile":Vector3(0.95,0.055,0.02)}[angle]
					camera.look_at(focus)
					await capture(preset.id+"-"+mode+"-"+angle)
		records.append({"look":preset.id,"active_cache":HAIR.cache_metrics()})
		var cached:=hair.mesh
		var began:=Time.get_ticks_usec()
		HAIR.apply(native,actor.get_skeleton(),look,config,2)
		records.append({"look":preset.id,"cached_apply_usec":Time.get_ticks_usec()-began})
		expect(hair.mesh==cached,preset.id+" cached mesh reused")
		# Colour changes share the geometry and retain every existing palette value.
		var authored:Mesh=hair.get_meta(PortraitGroom.SOURCE_META)
		var base_material:=authored.surface_get_material(0) as StandardMaterial3D
		for color_index:int in 20:
			var recolored:=look.duplicate()
			recolored.hair=AppearanceVariants.pack_hair(preset.style,color_index)
			HAIR.apply(native,actor.get_skeleton(),recolored,config,2)
			var mat:=hair.get_surface_override_material(0) as ShaderMaterial
			var expected:=AppearanceVariants.hair_color(recolored.hair)*base_material.albedo_color
			expect(mat.get_shader_parameter("hair_color")==expected,preset.id+" all colour controls "+str(color_index))
			expect(hair.mesh==cached,preset.id+" recolour shares geometry")
		HAIR.apply(native,actor.get_skeleton(),look,config,2)
		HAIR.apply(native,actor.get_skeleton(),look,config,1)
		expect(hair.mesh==original.mesh and hair.material_override==original.override,preset.id+" exact Medium resource restoration")
		for i:int in original.mats.size():expect(hair.get_surface_override_material(i)==original.mats[i],preset.id+" exact Medium surface restore")
		expect(int(HAIR.cache_metrics().mesh_entries)==0,preset.id+" last Medium user frees extra hair meshes")
		HAIR.apply(native,actor.get_skeleton(),look,config,2)
		var active_mesh:=hair.mesh
		for action:StringName in [&"walk",&"run",&"idle"]:
			actor.play_action(action,true)
			actor.animation_player.seek(0.55,true)
			actor.animation_player.pause()
			actor.get_skeleton().force_update_all_bone_transforms()
			expect(hair.mesh==active_mesh and hair.skin==original.skin,preset.id+" stable bound mesh "+str(action))
			if render and action!=&"idle":
				var rig:=actor.get_skeleton()
				var focus:=rig.to_global(rig.get_bone_global_pose(rig.find_bone("Head")).origin)+Vector3(0,0.075,0)
				camera.position=focus+Vector3(0.4,0.055,1)
				camera.look_at(focus)
				await capture(preset.id+"-high-"+str(action))
		HAIR.release(native)
		hair.get_parent().hide()
		HAIR.apply(native,actor.get_skeleton(),look,config,2)
		expect(hair.mesh==original.mesh and int(HAIR.cache_metrics().mesh_entries)==0,preset.id+" helmet-hidden hair skips extra meshes")
		hair.get_parent().show()
		actor.free()
		await process_frame
	if not render and OS.get_environment("RL_HIGH_HAIR_FULL_AUDIT") == "1":
		# Every original style/finish remains supported on both Human skeletons.
		for sex:String in ["male","female"]:
			var actor:=ReplicatedActor3D.new()
			stage.add_child(actor)
			actor.apply_render_quality(1,false)
			var config:Dictionary=models["luminous_"+sex]
			actor.configure({"actor_id":9870,"kind":1,"x":0,"y":0,"rotation":0,"name":"","appearance":{},"equipment_visuals":{}},CoordinateAdapter.new(),config,animations,equipment)
			actor.set_process(false)
			actor.set_physics_process(false)
			for style:int in range(1,10):
				for detail:int in 3:
					var look:Dictionary={"hair":AppearanceVariants.pack_hair(style,style+detail),"hair_detail":detail}
					actor.apply_appearance_variants(look)
					var hair:MeshInstance3D=HAIR._hair_nodes(actor._native_model)[0]
					var original:=snapshot(hair)
					HAIR.apply(actor._native_model,actor.get_skeleton(),look,config,2)
					inspect(hair,sex+" style"+str(style)+" finish"+str(detail),original)
					HAIR.release(actor._native_model)
					expect(hair.mesh==original.mesh,sex+" style restores "+str(style))
			actor.free()
		expect(int(HAIR.cache_metrics().mesh_entries)==0,"all High memory released")
	records.append({"cache":HAIR.cache_metrics()})
	FileAccess.open(output.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"checks":checks,"failures":failures,"records":records},"  "))
	print("HIGH_HAIR_RESULT ",checks," checks ",failures," failures ",HAIR.cache_metrics())
	HAIR.clear()
	quit(1 if failures else 0)
