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
	var bounds: AABB = panels[0].bounds
	var target := bounds.get_center()
	var size := maxf(bounds.size.x,maxf(bounds.size.y,bounds.size.z))*1.3
	for p: Dictionary in panels:
		p.camera.size = size
	for index in 5:
		await process_frame
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
	var labels := []
	for entry: Dictionary in entries:
		for p: Dictionary in panels:
			p.player.play("RESET",0.0)
			p.player.seek(0.0,true)
			p.player.play(entry.clip,0.0)
			p.player.seek(p.player.get_animation(entry.clip).length*entry.fraction,true)
			p.skeleton.force_update_all_bone_transforms()
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
