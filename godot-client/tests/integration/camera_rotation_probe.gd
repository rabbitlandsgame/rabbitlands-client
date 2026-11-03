extends SceneTree
## Rendered, offline arrival followed by three identical camera turns.
## Use an isolated XDG_DATA_HOME and set ELORIA_CAMERA_PROBE_USER_ROOT to it.
## ELORIA_CAMERA_PROBE_REPORT is the output JSON; disable the arrival warm-up
## with ELORIA_CAMERA_SHADER_WARMUP=0 for a matched baseline.
## Defaults to Landfall tile 61,250. Select another registered map with
## ELORIA_CAMERA_PROBE_MAP and an explicit ELORIA_CAMERA_PROBE_TILE=x,y.
## Use ELORIA_CAMERA_PROBE_MINIMAP=show to include the direct 2D minimap.
##
## World-distance baseline (wave 2 WD-C0): ELORIA_CAMERA_PROBE_DISTANCE and
## ELORIA_CAMERA_PROBE_PITCH take one value or a comma list (defaults 14 m and
## -60 degrees, unchanged); every distance x pitch pose after the first is
## settled for ELORIA_CAMERA_PROBE_POSE_SETTLE_MSEC (default 2000) and turned
## ELORIA_CAMERA_PROBE_TURNS times (default 3). ELORIA_CAMERA_PROBE_MINUTE sets
## the game minute (default 600, mid-morning with sun shadows; 0 is midnight).
## Each turn also records shadow-pass draws and primitives; each pose records
## the camera near/far planes, the fitted sun shadow distance and the world
## distance state. `poses` holds every pose; the top-level `turns`, `pitch`
## and `distance` are the first pose's, as before.

## Camera rig limits (IsometricCameraController min/max_distance, pitch clamp).
const DISTANCE_RANGE := Vector2(1.5, 90.0)
const PITCH_RANGE := Vector2(-80.0, -15.0)
const MAX_POSES := 24
## Main's before-login world geometry preparation in a fresh user root.
const PREPARATION_LIMIT_MSEC := 1800000
const GRAPHICS_KEYS: Array[String] = ["render_scale", "map_texture_quality", "quality", "shadows",
	"decorative_grass", "crowd_bodies", "swaying_capes", "particles", "appearance"]

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

## Every distance x pitch pose, distance-major, from ELORIA_CAMERA_PROBE_DISTANCE
## and ELORIA_CAMERA_PROBE_PITCH (one number or a comma list each).
static func probe_poses(distance_text: String, pitch_text: String) -> Dictionary:
	var distances := _number_list(distance_text, 14.0, DISTANCE_RANGE, "ELORIA_CAMERA_PROBE_DISTANCE")
	if distances.has("error"):
		return distances
	var pitches := _number_list(pitch_text, -60.0, PITCH_RANGE, "ELORIA_CAMERA_PROBE_PITCH")
	if pitches.has("error"):
		return pitches
	var poses: Array[Dictionary] = []
	for distance: float in distances["numbers"]:
		for pitch: float in pitches["numbers"]:
			poses.append({"distance": distance, "pitch": pitch})
	if poses.size() > MAX_POSES:
		return {"error": "At most %d distance x pitch poses per probe run." % MAX_POSES}
	return {"poses": poses}

## The game minute the probe pins (0-1439); 600 keeps the calibrated daylight.
static func probe_minute(text: String) -> Dictionary:
	return _integer_setting(text, 600, 0, 1439, "ELORIA_CAMERA_PROBE_MINUTE")

## Timed 360-degree turns per pose.
static func probe_turns(text: String) -> Dictionary:
	return _integer_setting(text, 3, 1, 10, "ELORIA_CAMERA_PROBE_TURNS")

## Settling before each pose after the first, for streaming and the shadow fit.
static func probe_pose_settle(text: String) -> Dictionary:
	return _integer_setting(text, 2000, 0, 120000, "ELORIA_CAMERA_PROBE_POSE_SETTLE_MSEC")

## Supported Graphics controls (ELORIA_CAMERA_PROBE_GRAPHICS, a JSON object).
## `quality` and `appearance` must name a quality and an appearance mode.
static func probe_graphics(text: String) -> Dictionary:
	if text.is_empty():
		return {"overrides": {}}
	var json := JSON.new()
	var parsed: Variant = json.data if json.parse(text) == OK else null
	if not (parsed is Dictionary):
		return {"error": "ELORIA_CAMERA_PROBE_GRAPHICS must be a JSON object."}
	var look: Variant = load("res://src/world/look/look_profile.gd")
	for key: Variant in parsed:
		if not (key is String) or str(key) not in GRAPHICS_KEYS:
			return {"error": "Unsupported camera probe Graphics setting: " + str(key)}
		if key == "quality" and look.quality_named(str(parsed[key])) < 0:
			return {"error": "Unknown camera probe quality: " + str(parsed[key])}
		if key == "appearance" and look.mode_named(str(parsed[key])) < 0:
			return {"error": "Unknown camera probe appearance: " + str(parsed[key])}
	return {"overrides": parsed}

static func _number_list(text: String, fallback: float, limits: Vector2, variable: String) -> Dictionary:
	if text.strip_edges().is_empty():
		return {"numbers": [fallback]}
	var values: Array[float] = []
	for part: String in text.split(","):
		var item := part.strip_edges()
		if not item.is_valid_float():
			return {"error": "%s must be a number or a comma list of numbers." % variable}
		var value := float(item)
		if not is_finite(value) or value < limits.x or value > limits.y:
			return {"error": "%s values must lie in %s..%s." % [variable, limits.x, limits.y]}
		if values.has(value):
			return {"error": "%s repeats %s." % [variable, item]}
		values.append(value)
	return {"numbers": values}

static func _integer_setting(text: String, fallback: int, low: int, high: int, variable: String) -> Dictionary:
	var item := text.strip_edges()
	if item.is_empty():
		return {"value": fallback}
	if not item.is_valid_int() or int(item) < low or int(item) > high:
		return {"error": "%s must be an integer in %d..%d." % [variable, low, high]}
	return {"value": int(item)}

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
	var graphics := probe_graphics(OS.get_environment("ELORIA_CAMERA_PROBE_GRAPHICS"))
	var pose_plan := probe_poses(OS.get_environment("ELORIA_CAMERA_PROBE_DISTANCE"),
		OS.get_environment("ELORIA_CAMERA_PROBE_PITCH"))
	var minute := probe_minute(OS.get_environment("ELORIA_CAMERA_PROBE_MINUTE"))
	var turn_count := probe_turns(OS.get_environment("ELORIA_CAMERA_PROBE_TURNS"))
	var pose_settle := probe_pose_settle(OS.get_environment("ELORIA_CAMERA_PROBE_POSE_SETTLE_MSEC"))
	for setting: Dictionary in [graphics, pose_plan, minute, turn_count, pose_settle]:
		if setting.has("error"):
			push_error(str(setting.error))
			quit(1)
			return
	var overrides: Dictionary = graphics.overrides
	var poses: Array[Dictionary] = pose_plan.poses
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
	# In a user root without prepared world geometry (every fresh isolated root)
	# Main cooks it before login and finishes _ready() only afterwards; settings
	# applied earlier reach half-built windows and an empty map registry.
	var preparation_started := Time.get_ticks_msec()
	var prepared_geometry := bool(main.get("_geometry_maintenance_active"))
	while bool(main.get("_geometry_maintenance_active")) \
			and Time.get_ticks_msec() - preparation_started < PREPARATION_LIMIT_MSEC:
		await process_frame
	var preparation_ms := Time.get_ticks_msec() - preparation_started
	if bool(main.get("_geometry_maintenance_active")):
		push_error("Main's world geometry preparation did not finish in time.")
		quit(1)
		return
	await process_frame
	main.call("_apply_performance_preset")
	for key: String in overrides:
		var value: Variant = overrides[key]
		if key == "quality":
			value = load("res://src/world/look/look_profile.gd").quality_named(str(value))
		elif key == "appearance":
			value = load("res://src/world/look/look_profile.gd").mode_named(str(value))
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
	rig.set("distance", float(poses[0].distance))
	var pitch := float(poses[0].pitch)
	rig.set("pitch_degrees", pitch)
	var state := root.get_node("AppState")
	state.set("authenticated", true)
	state.set("connection_state", "connected")
	state.set("current_map", map_id)
	state.set("local_actor_id", 99)
	state.set("game_minute", int(minute.value))
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
		# Awaited on its own line: a teardown that fails must still leave a report
		# and the documented wait for the owning runner, not abort this coroutine.
		var teardown: Variant = await _tear_down(main, state)
		var failure := {"map": map_id, "tile": [tile.x, tile.y], "manifest": location.manifest,
			"error": "arrival_not_ready", "teardown": teardown}
		FileAccess.open(report, FileAccess.WRITE).store_string(JSON.stringify(failure, "  "))
		if not (teardown is Dictionary and bool((teardown as Dictionary).get("ready", false))):
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
	var pose_results := []
	for pose_index: int in (0 if load_only else poses.size()):
		var pose: Dictionary = poses[pose_index]
		if pose_index > 0:
			rig.set("distance", float(pose.distance))
			rig.set("pitch_degrees", float(pose.pitch))
			rig.call("_update_camera")
			var pose_started := Time.get_ticks_msec()
			while Time.get_ticks_msec() - pose_started < int(pose_settle.value):
				await process_frame
		var pose_turns := []
		for turn: int in int(turn_count.value):
			pose_turns.append(await _turn(rig, viewport, turn))
			print("camera_rotation_probe ", JSON.stringify(pose_turns[-1]))
		pose_results.append(_pose_result(main, rig, pose, pose_turns))
	var turns: Array = pose_results[0].turns if not pose_results.is_empty() else []
	config.load("user://eloria_hud.cfg")
	var settings := {}
	for key: String in GRAPHICS_KEYS:
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
	result["geometry_preparation"] = {"ran": prepared_geometry, "milliseconds": preparation_ms}
	result["distance"] = float(poses[0].distance)
	result["poses"] = pose_results
	result["game_minute"] = int(minute.value)
	result["turns_per_pose"] = int(turn_count.value)
	result["pose_settle_msec"] = int(pose_settle.value)
	result["graphics_overrides"] = overrides
	result["appearance"] = load("res://src/world/look/look_profile.gd").mode_name(
		load("res://src/world/look/look_profile.gd").mode())
	result["world_distance_variable"] = OS.get_environment("ELORIA_WORLD_DISTANCE")
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

## One timed 360-degree turn at the rig's current distance and pitch. Shadow
## draws and primitives are the world viewport's shadow passes (all cascades
## and lights) in the same frame as the visible ones.
func _turn(rig: Node3D, viewport: SubViewport, turn: int) -> Dictionary:
	var times: Array[float] = []
	var gpu_times: Array[float] = []
	var cpu_times: Array[float] = []
	var draw_calls: Array[float] = []
	var primitives: Array[float] = []
	var objects: Array[float] = []
	var shadow_draw_calls: Array[float] = []
	var shadow_primitives: Array[float] = []
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
		objects.append(float(viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE,
			Viewport.RENDER_INFO_OBJECTS_IN_FRAME)))
		shadow_draw_calls.append(float(viewport.get_render_info(Viewport.RENDER_INFO_TYPE_SHADOW,
			Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME)))
		shadow_primitives.append(float(viewport.get_render_info(Viewport.RENDER_INFO_TYPE_SHADOW,
			Viewport.RENDER_INFO_PRIMITIVES_IN_FRAME)))
		if elapsed > 33.3:
			spikes.append({"yaw": yaw, "ms": elapsed, "at_msec": Time.get_ticks_msec(), "gpu_ms": gpu_times[-1],
				"render_cpu_ms": cpu_times[-1],
				"process_ms": Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
				"physics_ms": Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0})
	var mean_gpu := _mean(gpu_times)
	times.sort()
	gpu_times.sort()
	return {"turn": turn, "median_ms": times[179], "p95_ms": times[341],
		"p99_ms": times[356], "max_ms": times[359], "spikes": spikes,
		"mean_ms": _mean(times), "gpu_mean_ms": mean_gpu, "gpu_p95_ms": gpu_times[341],
		"render_cpu_mean_ms": _mean(cpu_times), "draw_calls_mean": _mean(draw_calls),
		"primitives_mean": _mean(primitives), "objects_mean": _mean(objects),
		"shadow_draw_calls_mean": _mean(shadow_draw_calls),
		"shadow_primitives_mean": _mean(shadow_primitives)}

## A pose's camera planes, sun shadow fit and world-distance state, read after
## its timed turns. WorldDistance (WD-C3) is read when Main has one.
func _pose_result(main: Node, rig: Node3D, pose: Dictionary, pose_turns: Array) -> Dictionary:
	var camera := rig.get("camera") as Camera3D
	var sun := main.get("world_sun") as DirectionalLight3D
	var distance_state: Variant = main.get("world_distance")
	var world_distance := {"present": false}
	if distance_state is Object and is_instance_valid(distance_state) \
			and (distance_state as Object).has_method("snapshot"):
		var snapshot: Variant = (distance_state as Object).call("snapshot")
		world_distance = (snapshot as Dictionary).duplicate(true) if snapshot is Dictionary else {}
		world_distance["present"] = true
	return {"distance": float(pose.distance), "pitch": float(pose.pitch), "turns": pose_turns,
		"camera_near": camera.near if camera != null else null,
		"camera_far": camera.far if camera != null else null,
		"camera_fov": camera.fov if camera != null else null,
		"sun_shadows_enabled": sun.shadow_enabled if sun != null else null,
		"sun_shadow_max_distance": sun.directional_shadow_max_distance if sun != null else null,
		"world_distance": world_distance}

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
