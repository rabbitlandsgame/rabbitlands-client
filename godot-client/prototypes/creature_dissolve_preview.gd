extends SceneTree
## Loop the actual temporary-creature death presentation. --capture saves stages.

var actors: Array[ReplicatedActor3D] = []
var elapsed := 0.0
var running := false
var caption: Label
const OUTPUT := "res://test-artifacts/death-dissolve"

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.title = "Rabbit Lands - Creature Dissolve Preview"
	root.size = Vector2i(1280, 720)
	var stage := Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("222d36")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("b8c4d2")
	world.environment.ambient_light_energy = 0.65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-50, -25, 0)
	light.light_energy = 1.4
	stage.add_child(light)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(30, 30)
	var ground := StandardMaterial3D.new()
	ground.albedo_color = Color("414842")
	plane.material = ground
	floor_mesh.mesh = plane
	stage.add_child(floor_mesh)
	var camera := Camera3D.new()
	camera.cull_mask = 3
	camera.fov = 39
	stage.add_child(camera)
	camera.look_at_from_position(Vector3(0, 4.2, 8), Vector3(0, 0.5, 0))
	camera.current = true
	caption = Label.new()
	caption.position = Vector2(36, 30)
	caption.add_theme_font_size_override("font_size", 27)
	root.add_child(caption)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var species := ["red_fox", "mossback_boar", "cerberus"]
	for index in species.size():
		var config: Dictionary = models[species[index]]
		var path := ProjectSettings.globalize_path(str(config.scene))
		GlbSceneCache.install_prepared({path: GlbSceneCache._build_raw(path)})
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var dto := {"actor_id": index + 1, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
			"name": "", "x": index * 3 - 3, "y": 0, "rotation": 0, "health": 100,
			"max_health": 100, "appearance": {}, "equipment_visuals": {}}
		var errors := actor.configure(dto, CoordinateAdapter.new({"metresPerTile": 1.0}), config,
			JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
		if not errors.is_empty():
			push_error(str(errors))
			quit(1)
			return
		actor.position = Vector3(index * 3 - 3, 0, 0)
		actor.rotation.y = PI * 0.7
		actor.set_physics_process(false)
		actor.set_health_visible(false)
		actors.append(actor)
	for frame in 4:
		await process_frame
	_restart()
	if "--capture" in OS.get_cmdline_user_args():
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
		var previous := 0.0
		for phase: Dictionary in [{"name": "held", "time": 4.8}, {"name": "breaking", "time": 6.0},
			{"name": "drifting", "time": 6.8}, {"name": "dust", "time": 7.5}, {"name": "clear", "time": 9.1}]:
			for actor: ReplicatedActor3D in actors:
				actor._process(float(phase.time) - previous)
				actor.set_process(false)
			previous = float(phase.time)
			caption.text = "Rabbit Lands  /  Creature dissolve  /  " + str(phase.name).capitalize()
			for frame in 4:
				await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(ProjectSettings.globalize_path(OUTPUT.path_join(str(phase.name) + ".png")))
		stage.queue_free()
		caption.queue_free()
		await process_frame
		GlbSceneCache.clear()
		NativeAnimationImporter.clear()
		print("DISSOLVE_CAPTURE_COMPLETE")
		quit()
	elif "--frames" in OS.get_cmdline_user_args():
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT.path_join("frames")))
		for actor: ReplicatedActor3D in actors:
			actor._process(4.5)
			actor.set_process(false)
		caption.text = "Rabbit Lands  /  Creature dissolve"
		for index in 100:
			for actor: ReplicatedActor3D in actors:
				actor._process(0.05)
				actor.set_process(false)
			await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(ProjectSettings.globalize_path(OUTPUT.path_join("frames/%03d.png" % index)))
		stage.queue_free()
		caption.queue_free()
		await process_frame
		GlbSceneCache.clear()
		NativeAnimationImporter.clear()
		print("DISSOLVE_FRAMES_COMPLETE")
		quit()
	else:
		running = true

func _restart() -> void:
	elapsed = 0.0
	for actor: ReplicatedActor3D in actors:
		var dto := {"x": roundi(actor.position.x), "y": 0, "rotation": 0, "health": 100, "alive": true, "command": 7}
		actor.apply_server_state(dto, CoordinateAdapter.new({"metresPerTile": 1.0}))
		dto.merge({"health": 0, "alive": false, "command": 3,
			"death_presentation": {"temporary": true, "elapsed": 0.0, "animation_seconds": 3.0,
				"hold_seconds": 2.0, "fade_seconds": 4.0, "received_msec": Time.get_ticks_msec()}}, true)
		actor.apply_server_state(dto, CoordinateAdapter.new({"metresPerTile": 1.0}))
		actor.set_physics_process(false)

func _process(delta: float) -> bool:
	if running:
		elapsed += delta
		caption.text = "Rabbit Lands  /  Creature dissolve  /  " + (
			"Death" if elapsed < 3.0 else "Held pose" if elapsed < 5.0 else "Dissolving" if elapsed < 7.5 else "Drifting ash")
		if elapsed >= 10.5:
			_restart()
	return false
