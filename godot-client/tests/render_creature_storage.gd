extends SceneTree
## Ignored job inputs select immutable source and candidate copies. This check
## uses the complete Actor so display boosts, grounding and material setup run.
var job: Dictionary
var panels: Array[Dictionary] = []

func _init() -> void:
	run.call_deferred()

func vector(value: Vector3) -> Array:
	return [value.x,value.y,value.z]

func transform(value: Transform3D) -> Array:
	return [vector(value.origin),vector(value.basis.x),vector(value.basis.y),vector(value.basis.z)]

func pose(p: Dictionary, entry: Dictionary) -> void:
	p.player.play("RESET",0.0)
	p.player.seek(0.0,true)
	p.player.play(entry.clip,0.0)
	p.player.seek(p.player.get_animation(entry.clip).length*entry.fraction,true)
	p.skeleton.force_update_all_bone_transforms()

func geometry(p: Dictionary) -> Array[Dictionary]:
	var groups: Array[Dictionary] = []
	for mesh: MeshInstance3D in p.model.find_children("*","MeshInstance3D",true,false):
		if mesh.mesh == null or not mesh.is_visible_in_tree() or mesh.layers & 1 == 0: continue
		var skeleton := mesh.get_node_or_null(mesh.skeleton) as Skeleton3D
		var bones := []
		if skeleton != null and mesh.skin != null:
			for bind in mesh.skin.get_bind_count():
				var bone := skeleton.find_bone(mesh.skin.get_bind_name(bind))
				bones.append(bone if bone >= 0 else mesh.skin.get_bind_bone(bind))
		for surface in mesh.mesh.get_surface_count():
			groups.append({"mesh":mesh,"skeleton":skeleton,"bones":bones,"arrays":mesh.mesh.surface_get_arrays(surface),"shapes":mesh.mesh.surface_get_blend_shape_arrays(surface),"relative":mesh.mesh.blend_shape_mode == Mesh.BLEND_SHAPE_MODE_RELATIVE})
	return groups

func posed_bounds(groups: Array[Dictionary], initial: AABB) -> AABB:
	var bounds := initial
	for group: Dictionary in groups:
		var mesh: MeshInstance3D = group.mesh
		var arrays: Array = group.arrays
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var active := []
		for shape in group.shapes.size():
			var weight := mesh.get_blend_shape_value(shape)
			if absf(weight) >= .0001: active.append({"vertices":group.shapes[shape][Mesh.ARRAY_VERTEX],"weight":weight})
		var transforms: Array[Transform3D] = []
		for bind in group.bones.size():
			transforms.append(group.skeleton.global_transform * group.skeleton.get_bone_global_pose(group.bones[bind]) * mesh.skin.get_bind_pose(bind))
		var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES] != null else PackedInt32Array()
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS] != null else PackedFloat32Array()
		var stride := joints.size()/vertices.size() if not vertices.is_empty() else 0
		for index in vertices.size():
			var point := vertices[index]
			for shape: Dictionary in active:
				point += (shape.vertices[index] if group.relative else shape.vertices[index]-vertices[index])*shape.weight
			var world := mesh.global_transform * point
			if not transforms.is_empty():
				world = Vector3.ZERO
				for slot in stride:
					var at := index*stride+slot
					world += (transforms[joints[at]]*point)*weights[at]
			bounds = bounds.expand(world)
	return bounds

func panel(fixture: Dictionary) -> Dictionary:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(512,512)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(.14,.17,.21)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(.85,.9,1.0)
	environment.environment.ambient_light_energy = .65
	world.add_child(environment)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-40,-35,0)
	key.light_energy = 1.4
	world.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-15,145,0)
	fill.light_energy = .45
	world.add_child(fill)
	var config: Dictionary = job.config.duplicate(true)
	config.scene = fixture.path
	config.animationLibrary = fixture.path
	var actor := ReplicatedActor3D.new()
	world.add_child(actor)
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var errors := actor.configure({"actor_id":5,"x":0,"y":0,"rotation":0,"kind":5,"name":job.actor},CoordinateAdapter.new(),config,mapping)
	assert(errors.is_empty(),str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	var model := actor.get_node("NativeModel") as Node3D
	var skeleton := model.find_children("*","Skeleton3D",true,false)[0] as Skeleton3D
	var player := actor.animation_player
	assert(player != null)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.cull_mask = 1
	camera.current = true
	world.add_child(camera)
	var bounds: AABB = model.global_transform * actor._native_body_bounds
	var placement := {"name":fixture.name,"sha256":FileAccess.get_sha256(fixture.path),"model_global":transform(model.global_transform),"body_bounds_position":vector(actor._native_body_bounds.position),"body_bounds_size":vector(actor._native_body_bounds.size),"overhead_height":actor.banner_head_height(),"nameplate_global":vector(actor._nameplate.global_position),"selection_size":vector(actor._selection_ring.mesh.get_aabb().size)}
	return {"viewport":viewport,"actor":actor,"model":model,"skeleton":skeleton,"player":player,"camera":camera,"name":fixture.name,"bounds":bounds,"placement":placement}

func run() -> void:
	job = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var output: String = str(job.output).path_join("actual-render")
	DirAccess.make_dir_recursive_absolute(output)
	for fixture: Dictionary in job.actor_fixtures:
		panels.append(panel(fixture))
	var placements := []
	for p: Dictionary in panels:
		placements.append(p.placement)
	for property: String in ["model_global","overhead_height","nameplate_global","selection_size"]:
		assert(placements[0][property] == placements[1][property],"Actor placement differs: "+property)
	var entries := []
	var views := [{"name":"game","yaw":0.0,"pitch":30.0},{"name":"side","yaw":90.0,"pitch":10.0},{"name":"rear","yaw":180.0,"pitch":25.0},{"name":"under","yaw":30.0,"pitch":-30.0}]
	for clip: StringName in panels[0].player.get_animation_list():
		if clip == &"RESET": continue
		for fraction in [0.0,.37,.79,1.0]:
			for view: Dictionary in views:
				entries.append({"clip":clip,"fraction":fraction,"view":view,"video":false})
		var duration: float = panels[0].player.get_animation(clip).length
		for frame in range(ceili(duration*24.0)+1):
			entries.append({"clip":clip,"fraction":minf(frame/24.0/duration,1.0),"frame":frame,"view":views[0],"video":true})
	var fit_path: String = str(job.output).path_join("render-fit.json")
	if "--fit-only" in OS.get_cmdline_user_args():
		var bounds: AABB = panels[0].bounds
		var groups := geometry(panels[0])
		var seen := {}
		for entry: Dictionary in entries:
			var signature := str(entry.clip)+"@"+str(entry.fraction)
			if seen.has(signature): continue
			seen[signature] = true
			pose(panels[0],entry)
			bounds = posed_bounds(groups,bounds)
		var fit := {"source_sha256":placements[0].sha256,"model_global":placements[0].model_global,"position":vector(bounds.position),"size":vector(bounds.size),"poses":seen.size(),"scope":"Every vertex of every visible body surface, all native full-cycle render frames plus each view-still pose. Uses actual Godot mesh arrays, active renderer morph cutoff, current skeleton/binds, four/eight influences and complete Actor transform."}
		FileAccess.open(fit_path,FileAccess.WRITE).store_string(JSON.stringify(fit,"\t"))
		for p: Dictionary in panels: p.viewport.free()
		NativeAnimationImporter.clear(); GlbSceneCache.clear()
		print("CREATURE_STORAGE_FIT_PASS ",job.actor," ",seen.size())
		quit(); return
	assert(FileAccess.file_exists(fit_path),"Run the headless --fit-only all-vertex prepass before rendering")
	var fit: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fit_path))
	assert(fit.source_sha256 == placements[0].sha256,"Render fit does not match source hash")
	for row in 4:
		for column in 3:
			assert(absf(float(fit.model_global[row][column])-float(placements[0].model_global[row][column])) < 1e-12,"Render fit does not match Actor transform (beyond JSON float roundtrip)")
	var low := Vector3(float(fit.position[0]),float(fit.position[1]),float(fit.position[2]))
	var extent := Vector3(float(fit.size[0]),float(fit.size[1]),float(fit.size[2]))
	var bounds := AABB(low,extent)
	var target := bounds.get_center()
	var size := maxf(bounds.size.x,maxf(bounds.size.y,bounds.size.z))*1.3
	for p: Dictionary in panels: p.camera.size = size
	for index in 5: await process_frame
	var labels := []
	for entry: Dictionary in entries:
		for p: Dictionary in panels:
			pose(p,entry)
			var yaw := deg_to_rad(float(entry.view.yaw))
			var pitch := deg_to_rad(float(entry.view.pitch))
			p.camera.look_at_from_position(Vector3(sin(yaw)*cos(pitch),sin(pitch),cos(yaw)*cos(pitch))*10.0+target,target)
		await process_frame
		await RenderingServer.frame_post_draw
		var label: String = str(entry.clip)+"-"+str(entry.view.name)+"-"+("frame-%04d" % int(entry.frame) if entry.video else str(int(entry.fraction*100)))
		for p: Dictionary in panels:
			var picture: Image = p.viewport.get_texture().get_image()
			assert(picture != null and not picture.is_empty())
			picture.save_png(output.path_join(str(p.name)+"-"+label+".png"))
		labels.append(label)
		if labels.size()%50 == 0: print("CREATURE_STORAGE_RENDER ",job.actor," ",labels.size(),"/",entries.size())
	FileAccess.open(output.path_join("render.json"),FileAccess.WRITE).store_string(JSON.stringify({"passed":true,"actor":job.actor,"frames":labels,"placements":placements,"engine":Engine.get_version_info(),"gpu":RenderingServer.get_video_adapter_name(),"method":RenderingServer.get_current_rendering_method(),"camera_size":size,"camera_target":vector(target),"scope":"Complete ReplicatedActor3D setup with actual display scale, grounding and body materials; identical cameras for source/candidate, four views and every full native cycle at24Hz. Numeric playback and pixel comparisons are separate reports."},"\t"))
	for p: Dictionary in panels: p.viewport.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("CREATURE_STORAGE_RENDER_PASS ",job.actor," ",labels.size())
	quit()
