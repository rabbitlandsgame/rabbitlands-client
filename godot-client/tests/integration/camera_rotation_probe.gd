extends SceneTree
## Rendered, offline Landfall arrival followed by three identical camera turns.
## Use an isolated XDG_DATA_HOME and set ELORIA_CAMERA_PROBE_USER_ROOT to it.
## ELORIA_CAMERA_PROBE_REPORT is the output JSON; disable the arrival warm-up
## with ELORIA_CAMERA_SHADER_WARMUP=0 for a matched baseline.

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var isolated := OS.get_environment("ELORIA_CAMERA_PROBE_USER_ROOT")
	var report := OS.get_environment("ELORIA_CAMERA_PROBE_REPORT")
	if isolated.is_empty() or not OS.get_user_data_dir().begins_with(isolated.trim_suffix("/") + "/") \
			or report.is_empty() or DisplayServer.get_name() == "headless":
		push_error("Use an isolated user root, a report path and a rendered display.")
		quit(1)
		return
	var config := ConfigFile.new()
	var preferences := {"renderer": "gl_compatibility", "map_texture_quality": "half"}
	for key: String in preferences:
		config.set_value("graphics", key, preferences[key])
	config.save("user://eloria_hud.cfg")
	load("res://src/world/graphics_options.gd").set("_texture_skip", -1)
	root.get_node("Network").set("offline_hud_preview", true)
	var main: Node = load("res://src/app/main.tscn").instantiate()
	if main.get_script() == null or not main.get_script().can_instantiate():
		main.free()
		quit(1)
		return
	root.add_child(main)
	await process_frame
	main.call("_apply_performance_preset")
	var frame_cap := int(OS.get_environment("ELORIA_CAMERA_PROBE_FPS")) \
		if OS.has_environment("ELORIA_CAMERA_PROBE_FPS") else 60
	main.call("_on_client_setting_changed", "Graphics", "fps_limit", frame_cap)
	var vsync := "on" if OS.get_environment("ELORIA_CAMERA_PROBE_VSYNC") == "on" else "off"
	main.call("_on_client_setting_changed", "Graphics", "vsync_mode", vsync)
	var rig: Node3D = main.get("camera_rig")
	rig.set("distance", 14.0)
	var pitch := float(OS.get_environment("ELORIA_CAMERA_PROBE_PITCH")) \
		if OS.has_environment("ELORIA_CAMERA_PROBE_PITCH") else -60.0
	rig.set("pitch_degrees", pitch)
	var state := root.get_node("AppState")
	state.set("authenticated", true)
	state.set("connection_state", "connected")
	state.set("current_map", "landfall")
	state.set("local_actor_id", 99)
	state.set("game_minute", 600)
	state.set("game_minute_anchor_msec", Time.get_ticks_msec())
	state.set("actors", {99: {"actor_id": 99, "kind": 1, "actor_type": 0,
		"name": "Camera probe", "map": "landfall", "x": 61, "y": 250,
		"rotation": 0, "health": 100, "max_health": 100, "alive": true,
		"appearance": {}, "equipment_visuals": CreationArchetypes.loadout_at(0)}})
	main.call("_set_login_screen_visible", false)
	main.get("creation_panel").hide()
	main.get("game_view").show()
	var curtain: CanvasLayer = main.get("arrival_curtain")
	curtain.call("begin", "Camera test")
	main.call("_load_server_map")
	main.call("_sync_world")
	var started := Time.get_ticks_msec()
	while curtain.visible and Time.get_ticks_msec() - started < 150000:
		await process_frame
	if curtain.visible or not (main.get("_grounded_actors") as Dictionary).has(99):
		push_error("Offline arrival did not complete on loaded ground.")
		quit(1)
		return
	var arrival_ms := Time.get_ticks_msec() - started
	var warmup: Dictionary = main.get("camera_shader_warmup").snapshot()
	var restored_cap := Engine.max_fps
	var restored_vsync := DisplayServer.window_get_vsync_mode()
	Engine.max_fps = 0 # Compare rotation frame costs without the loading cap.
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	# Let background scenery finish before attributing a hitch to rotation.
	var settled := Time.get_ticks_msec()
	while Time.get_ticks_msec() - settled < 30000:
		await process_frame
	var viewport: SubViewport = main.get("main_viewport")
	RenderingServer.viewport_set_measure_render_time(viewport.get_viewport_rid(), true)
	var turns := []
	for turn: int in 3:
		var times: Array[float] = []
		var spikes := []
		for yaw: int in 360:
			var tick := Time.get_ticks_usec()
			rig.set("yaw_degrees", float(yaw))
			rig.call("_update_camera")
			await process_frame
			var elapsed := (Time.get_ticks_usec() - tick) / 1000.0
			times.append(elapsed)
			if elapsed > 33.3:
				spikes.append({"yaw": yaw, "ms": elapsed})
		times.sort()
		turns.append({"turn": turn, "median_ms": times[180], "p95_ms": times[342],
			"p99_ms": times[356], "max_ms": times[359], "spikes": spikes})
		print("camera_rotation_probe ", JSON.stringify(turns[-1]))
	var result := {"renderer": RenderingServer.get_current_rendering_method(),
		"adapter": RenderingServer.get_video_adapter_name(), "viewport": str(viewport.size),
		"warmup_enabled": OS.get_environment("ELORIA_CAMERA_SHADER_WARMUP") != "0",
		"arrival_ms": arrival_ms, "warmup": warmup, "requested_fps_cap": frame_cap,
		"restored_fps_cap": restored_cap, "restored_vsync": restored_vsync,
		"requested_vsync": vsync, "pitch": pitch, "turns": turns}
	FileAccess.open(report, FileAccess.WRITE).store_string(JSON.stringify(result, "  "))
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(report + ".png")
	quit()
