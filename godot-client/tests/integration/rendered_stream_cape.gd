extends "res://tests/integration/rendered_cape_over_armour.gd"
## Observe walking and running independently on the current approved cape.
func _run() -> void:
	root.size = Vector2i(900,720)
	Engine.max_fps = 60
	_artifacts = ProjectSettings.globalize_path("res://test-artifacts/stream-cape")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	_main = load("res://src/app/main.tscn").instantiate()
	root.add_child(_main)
	await process_frame
	_main.hide()
	_model_config = _main.models.luminous_male
	_animation_config = _main._animation_for_model(_model_config)
	_equipment_config = _main.equipment_config
	_adapter = CoordinateAdapter.new({"walkingHeight":0})
	_stage = Node3D.new()
	root.add_child(_stage)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color("586a78")
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_energy = .9
	_stage.add_child(env)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-30,30,0)
	_stage.add_child(light)
	_camera = Camera3D.new()
	_camera.cull_mask = 3
	_camera.current = true
	_stage.add_child(_camera)
	for action: StringName in [&"walk",&"run"]:
		var actor := _spawn({"2":5,"5":225})
		actor.set_physics_process(false)
		var speed := 1.67 if action == &"walk" else 5.0
		actor.set_cinematic_presentation(Vector3.ZERO,0,action,speed)
		actor.set_physics_process(false)
		for frame in range(180):
			actor.global_position.z -= speed*minf(root.get_process_delta_time(),1.0/30.0)
			_camera.look_at_from_position(actor.global_position+Vector3(-1.8,1.7,2.9),actor.global_position+Vector3(0,1,0))
			await process_frame
			if frame in [60,90,120,150]:
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png(_artifacts.path_join("%s-%03d.png" % [action,frame]))
		actor.queue_free()
		for i in range(3): await process_frame
	Input.set_custom_mouse_cursor(null,Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null,Input.CURSOR_IBEAM)
	_main.queue_free()
	_stage.queue_free()
	for i in range(8): await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	for i in range(4): await process_frame
	print("STREAM_CAPE_RENDER_COMPLETE")
	quit()
