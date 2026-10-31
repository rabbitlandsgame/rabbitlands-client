extends SceneTree
## Rendered, offline arrival followed by three identical camera turns.
## Use an isolated XDG_DATA_HOME and set ELORIA_CAMERA_PROBE_USER_ROOT to it.
## ELORIA_CAMERA_PROBE_REPORT is the output JSON; disable the arrival warm-up
## with ELORIA_CAMERA_SHADER_WARMUP=0 for a matched baseline.
## Defaults to Landfall tile 61,250. Select another registered map with
## ELORIA_CAMERA_PROBE_MAP and an explicit ELORIA_CAMERA_PROBE_TILE=x,y.
## Use ELORIA_CAMERA_PROBE_MINIMAP=show to include the direct 2D minimap.

## Static validation is also usable by a headless test without constructing Main.
static func probe_location(maps: Dictionary, map_text: String, tile_text: String) -> Dictionary:
	var wanted := "landfall" if map_text.is_empty() else map_text
	var entry := MapRegistry.resolve(maps, wanted)
	if entry.is_empty() or str(entry.get("manifest", "")).is_empty():
		return {"error": "ELORIA_CAMERA_PROBE_MAP must name a registered map with a manifest."}
	var map_id := MapRegistry.normalize_server_map_id(str(entry.registryKey))
	var tile := Vector2i(61, 250)
	if tile_text.is_empty():
		if map_id != "landfall":
			return {"error": "ELORIA_CAMERA_PROBE_TILE=x,y is required for a custom map."}
	else:
		var parts := tile_text.split(",")
		if parts.size() != 2 or not parts[0].strip_edges().is_valid_int() \
				or not parts[1].strip_edges().is_valid_int():
			return {"error": "ELORIA_CAMERA_PROBE_TILE must contain two integer server coordinates: x,y."}
		var x := int(parts[0])
		var y := int(parts[1])
		if x < 0 or y < 0 or x > 65535 or y > 65535:
			return {"error": "ELORIA_CAMERA_PROBE_TILE coordinates must fit unsigned 16-bit server fields."}
		tile = Vector2i(x, y)
	return {"map": map_id, "tile": tile, "manifest": str(entry.manifest)}

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var boot_msec := Time.get_ticks_msec()
	var isolated := OS.get_environment("ELORIA_CAMERA_PROBE_USER_ROOT")
	var report := OS.get_environment("ELORIA_CAMERA_PROBE_REPORT")
	if isolated.is_empty() or not OS.get_user_data_dir().begins_with(isolated.trim_suffix("/") + "/") \
			or report.is_empty() or DisplayServer.get_name() == "headless":
		push_error("Use an isolated user root, a report path and a rendered display.")
		quit(1)
		return
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	var maps: Dictionary = registry.get("maps", {}) if registry is Dictionary else {}
	var location := probe_location(maps, OS.get_environment("ELORIA_CAMERA_PROBE_MAP"),
		OS.get_environment("ELORIA_CAMERA_PROBE_TILE"))
	if location.has("error"):
		push_error(str(location.error))
		quit(1)
		return
	var map_id: String = location.map
	var tile: Vector2i = location.tile
	# Only supported Graphics controls may vary. Seed the texture tier before
	# loading main: changing its preference later cannot change this session.
	var overrides: Dictionary = {}
	if OS.has_environment("ELORIA_CAMERA_PROBE_GRAPHICS"):
		var parsed: Variant = JSON.parse_string(OS.get_environment("ELORIA_CAMERA_PROBE_GRAPHICS"))
		if not parsed is Dictionary:
			push_error("ELORIA_CAMERA_PROBE_GRAPHICS must be a JSON object.")
			quit(1)
			return
		overrides = parsed
	for key: String in overrides:
		if key not in ["render_scale", "map_texture_quality", "quality", "shadows",
				"decorative_grass", "crowd_bodies", "swaying_capes", "particles"]:
			push_error("Unsupported camera probe Graphics setting: " + key)
			quit(1)
			return
	var config := ConfigFile.new()
	var preferences := {"renderer": RenderingServer.get_current_rendering_method(),
		"map_texture_quality": overrides.get("map_texture_quality", "half")}
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
	for key: String in overrides:
		var value: Variant = overrides[key]
		if key == "quality":
			value = load("res://src/world/look/look_profile.gd").quality_named(str(value))
		main.call("_on_client_setting_changed", "Graphics", key, value)
	if OS.has_environment("ELORIA_CAMERA_PROBE_MINIMAP"):
		main.call("_on_client_setting_changed", "HUD", "minimap_visible",
			OS.get_environment("ELORIA_CAMERA_PROBE_MINIMAP") == "show")
	var frame_cap := int(OS.get_environment("ELORIA_CAMERA_PROBE_FPS")) \
		if OS.has_environment("ELORIA_CAMERA_PROBE_FPS") else 60
	main.call("_on_client_setting_changed", "Graphics", "fps_limit", frame_cap)
	var vsync := "on" if OS.get_environment("ELORIA_CAMERA_PROBE_VSYNC") == "on" else "off"
	main.call("_on_client_setting_changed", "Graphics", "vsync_mode", vsync)
	var main_ready_msec := Time.get_ticks_msec()
	var rig: Node3D = main.get("camera_rig")
	rig.set("distance", 14.0)
	var pitch := float(OS.get_environment("ELORIA_CAMERA_PROBE_PITCH")) \
		if OS.has_environment("ELORIA_CAMERA_PROBE_PITCH") else -60.0
	rig.set("pitch_degrees", pitch)
	var state := root.get_node("AppState")
	state.set("authenticated", true)
	state.set("connection_state", "connected")
	state.set("current_map", map_id)
	state.set("local_actor_id", 99)
	state.set("game_minute", 600)
	state.set("game_minute_anchor_msec", Time.get_ticks_msec())
	state.set("actors", {99: {"actor_id": 99, "kind": 1, "actor_type": 0,
		"name": "Camera probe", "map": map_id, "x": tile.x, "y": tile.y,
		"rotation": 0, "health": 100, "max_health": 100, "alive": true,
		"appearance": {}, "equipment_visuals": CreationArchetypes.loadout_at(0)}})
	main.call("_set_login_screen_visible", false)
	main.get("creation_panel").hide()
	main.get("game_view").show()
	var curtain: CanvasLayer = main.get("arrival_curtain")
	curtain.call("begin", "Camera test")
	var requested := Time.get_ticks_msec()
	main.call("_load_server_map")
	main.call("_sync_world")
	var started := Time.get_ticks_msec()
	while curtain.visible and Time.get_ticks_msec() - started < 150000:
		await process_frame
	if curtain.visible or not (main.get("_grounded_actors") as Dictionary).has(99) \
			or MapRegistry.normalize_server_map_id(str(main.get("loaded_server_map"))) != map_id:
		push_error("Offline arrival did not complete on loaded ground.")
		var failure := {"map": map_id, "tile": [tile.x, tile.y], "manifest": location.manifest,
			"error": "arrival_not_ready", "teardown": await _tear_down(main, state)}
		FileAccess.open(report, FileAccess.WRITE).store_string(JSON.stringify(failure, "  "))
		if not failure.teardown.ready:
			while true:
				await process_frame
		quit(1)
		return
	var arrival_ms := Time.get_ticks_msec() - started
	var warmup: Dictionary = main.get("camera_shader_warmup").snapshot()
	var restored_cap := Engine.max_fps
	var restored_vsync := DisplayServer.window_get_vsync_mode()
	var rotation_cap := int(OS.get_environment("ELORIA_CAMERA_PROBE_ROTATION_FPS"))
	Engine.max_fps = clampi(rotation_cap, 0, 240) # Default: uncapped frame costs.
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	# Let background scenery finish before attributing a hitch to rotation.
	var load_only := OS.get_environment("ELORIA_CAMERA_PROBE_LOAD_ONLY") == "1"
	var settled := Time.get_ticks_msec()
	while not load_only and Time.get_ticks_msec() - settled < 30000:
		await process_frame
	var viewport: SubViewport = main.get("main_viewport")
	RenderingServer.viewport_set_measure_render_time(viewport.get_viewport_rid(), true)
	for frame: int in 3:
		await process_frame
	var turns := []
	for turn: int in (0 if load_only else 3):
		var times: Array[float] = []
		var gpu_times: Array[float] = []
		var cpu_times: Array[float] = []
		var draw_calls: Array[float] = []
		var primitives: Array[float] = []
		var spikes := []
		for yaw: int in 360:
			var tick := Time.get_ticks_usec()
			rig.set("yaw_degrees", float(yaw))
			rig.call("_update_camera")
			await process_frame
			var elapsed := (Time.get_ticks_usec() - tick) / 1000.0
			times.append(elapsed)
			gpu_times.append(RenderingServer.viewport_get_measured_render_time_gpu(viewport.get_viewport_rid()))
			cpu_times.append(RenderingServer.viewport_get_measured_render_time_cpu(viewport.get_viewport_rid()))
			draw_calls.append(float(viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE,
				Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME)))
			primitives.append(float(viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE,
				Viewport.RENDER_INFO_PRIMITIVES_IN_FRAME)))
			if elapsed > 33.3:
				spikes.append({"yaw": yaw, "ms": elapsed, "at_msec": Time.get_ticks_msec(), "gpu_ms": gpu_times[-1],
					"render_cpu_ms": cpu_times[-1],
					"process_ms": Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
					"physics_ms": Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0})
		times.sort()
		turns.append({"turn": turn, "median_ms": times[179], "p95_ms": times[341],
			"p99_ms": times[356], "max_ms": times[359], "spikes": spikes,
			"mean_ms": _mean(times), "gpu_mean_ms": _mean(gpu_times),
			"render_cpu_mean_ms": _mean(cpu_times), "draw_calls_mean": _mean(draw_calls),
			"primitives_mean": _mean(primitives)})
		print("camera_rotation_probe ", JSON.stringify(turns[-1]))
	config.load("user://eloria_hud.cfg")
	var settings := {}
	for key: String in ["quality", "render_scale", "map_texture_quality", "shadows",
			"decorative_grass", "crowd_bodies", "swaying_capes", "particles"]:
		settings[key] = config.get_value("graphics", key)
	var result := {"renderer": RenderingServer.get_current_rendering_method(),
		"map": map_id, "tile": [tile.x, tile.y], "manifest": location.manifest,
		"loaded_map": str(main.get("loaded_server_map")), "arrival_grounded": true,
		"adapter": RenderingServer.get_video_adapter_name(), "viewport": str(viewport.size),
		"window": str(root.size), "actual_render_scale": viewport.scaling_3d_scale,
		"active_texture_skip": load("res://src/world/graphics_options.gd").active_texture_skip(),
		"settings": settings, "minimap_visible": main.get("minimap_frame").visible,
		"sun_shadows_enabled": main.get("world_sun").shadow_enabled,
		"video_memory_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
		"static_memory_bytes": Performance.get_monitor(Performance.MEMORY_STATIC),
		"main_setup_ms": main_ready_msec - boot_msec,
		"synchronous_map_setup_ms": started - requested,
		"map_request_to_ready_ms": started + arrival_ms - requested,
		"arrival_complete_msec": started + arrival_ms,
		"warmup_enabled": OS.get_environment("ELORIA_CAMERA_SHADER_WARMUP") != "0",
		"arrival_ms": arrival_ms, "warmup": warmup, "requested_fps_cap": frame_cap,
		"restored_fps_cap": restored_cap, "restored_vsync": restored_vsync,
		"requested_vsync": vsync, "pitch": pitch, "turns": turns}
	result["rotation_fps_cap"] = Engine.max_fps
	result["probe_mode"] = "arrival_only" if load_only else "arrival_and_rotation"
	# Snapshot only after timed turns, so cache-path and phase evidence does not
	# add diagnostic work to loading or frame measurements.
	result["world_loader"] = main.get("world_loader").diagnostic_snapshot()
	if ResourceLoader.exists("res://src/actors/wardrobe_dye_cache.gd"):
		result["wardrobe_cache"] = load("res://src/actors/wardrobe_dye_cache.gd").stats()
	# Read back derived atlas bytes only after all timed turns. Comparing these
	# hashes across processes checks the real actor's cache-on/off texture parity.
	var texture_hashes: Array[String] = []
	var seen_textures := {}
	for raw_texture: Variant in ReplicatedActor3D._wardrobe_texture_cache.values():
		var texture := raw_texture as Texture2D
		if texture == null or seen_textures.has(texture.get_instance_id()):
			continue
		seen_textures[texture.get_instance_id()] = true
		var pixels := texture.get_image()
		var digest := HashingContext.new()
		digest.start(HashingContext.HASH_SHA256)
		digest.update(var_to_bytes([pixels.get_width(), pixels.get_height(), pixels.get_format(),
			pixels.has_mipmaps(), pixels.get_mipmap_count()]))
		digest.update(pixels.get_data())
		texture_hashes.append(digest.finish().hex_encode())
	texture_hashes.sort()
	result["wardrobe_texture_hashes"] = texture_hashes
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(report + ".png")
	result["teardown"] = await _tear_down(main, state)
	FileAccess.open(report, FileAccess.WRITE).store_string(JSON.stringify(result, "  "))
	if not result.teardown.ready:
		push_error("Camera probe teardown timed out; owning runner must terminate it.")
		while true:
			await process_frame
	quit()

func _mean(values: Array[float]) -> float:
	return values.reduce(func(total: float, value: float) -> float: return total + value, 0.0) / values.size()

## Like the crowd harness, keep rendering/physics alive until private imports,
## retirements and grounding callbacks drain. Early loading-only exits otherwise
## free the engine while a streamed map worker can still be using its services.
func _tear_down(main: Node, state: Node) -> Dictionary:
	var started := Time.get_ticks_msec()
	var deadline := started + 60000
	Engine.max_fps = 60
	state.set("authenticated", false)
	state.set("local_actor_id", -1)
	state.set("actors", {})
	state.set("current_map", "")
	main.set_process(false)
	main.set_physics_process(false)
	main.set("_world_sync_queued", false)
	main.set("_spawn_backlog", false)
	main.set("_deferred_map_load", false)
	main.get("character_intro").cancel()
	main.get("respawn_prewarm").discard()
	main.get("gauntlet_prewarm").discard()
	RLHeadLibrary.cancel_warm()
	var actor_warmup: RefCounted = main.get("actor_resource_warmup")
	actor_warmup.call("clear")
	var park: Node = main.get("world_park")
	park.call("clear")
	var exterior: Node = main.get("exterior_stream")
	exterior.call("clear")
	var loader: Node = main.get("world_loader")
	var phases := []
	for stage: String in ["workers", "unload", "free"]:
		if stage == "unload":
			main.process_mode = Node.PROCESS_MODE_DISABLED
			main.call("_clear_world_presentation")
			park.call("release_now")
		elif stage == "free":
			main.queue_free()
		var stable := 0
		var pending := 0
		while stable < 2 and Time.get_ticks_msec() < deadline:
			await physics_frame
			await process_frame
			pending = 0
			if is_instance_valid(main):
				for child: Node in main.find_children("*", "", true, false):
					if child is ContinentChunkStream:
						child.pause_streaming()
						pending += int(not child.can_retire()) + (child.get("_retiring") as Array).size()
				pending += int((main.call("surface_work_snapshot") as Dictionary).get("pending", 0))
				pending += int(main.get("_actor_surface_snap_pending"))
			if is_instance_valid(loader):
				pending += int(int(loader.get("_cache_write_countdown")) > 0)
			for raw_thread: Variant in NativeAnimationImporter._prewarming.values():
				var thread := raw_thread as Thread
				pending += int(thread != null and thread.is_alive())
			pending += ContinentChunkStream.reap_orphans()
			pending += int(is_instance_valid(exterior) and not bool(exterior.call("is_idle")))
			pending += int(is_instance_valid(park) and not bool(park.call("is_idle")))
			pending += int(not bool(actor_warmup.call("is_idle"))) + int(RLHeadLibrary.warming())
			pending += int(stage == "free" and is_instance_valid(main))
			stable = stable + 1 if pending == 0 else 0
		phases.append({"stage": stage, "pending": pending, "stable_frames": stable})
		if stable < 2:
			return {"ready": false, "phases": phases, "milliseconds": Time.get_ticks_msec() - started}
	return {"ready": true, "phases": phases, "milliseconds": Time.get_ticks_msec() - started}
