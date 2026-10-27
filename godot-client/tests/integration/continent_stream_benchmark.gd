extends SceneTree
## Actual production chunk streaming, driven by a wall-clock camera proxy.
## Captures no pixels/mesh buffers and writes nothing during measured phases.
const Graphics := preload("res://src/world/graphics_options.gd")
const TexturePool := preload("res://src/world/external_texture_pool.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
var configuration: Dictionary
var stage: Node3D
var loader: WorldLoader
var stream: ContinentChunkStream
var camera: Camera3D
var position := Vector3.ZERO
var phase := "setup"
var frames: Array = []
var events: Array = []
var phases: Array = []
var memory: Array = []
var failures: Array = []
var origin_usec := 0
var previous_draw := 0
var process_started := 0
var physics_started := 0
var physics_gap_us := 0
var physics_gap_max_us := 0
var physics_steps_since_draw := 0
var process_gap_us := 0
var previous_process_started := 0
var last_memory_usec := 0
var event_cursor := 0
var missing_ground_frames := 0
var missing_resident_frames := 0
var pipeline_enums: Dictionary = {}
var tracing := false
var metadata_setup_us := 0
var last_ground_y := NAN
var coverage := {"selected":0,"missing":[]}
var coverage_sample_usec := 0
var movement_end_us := 0
var main_fixture: RefCounted

func _init() -> void:
	run.call_deferred()

func _position(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))

func _point(value: Vector3) -> Array:
	return [value.x, value.y, value.z]

func _elapsed() -> int:
	return Time.get_ticks_usec()-origin_usec

func _window_context() -> Dictionary:
	return {"window_focused":root.has_focus(),"window_position":[root.position.x,root.position.y],
		"window_resolution":[root.size.x,root.size.y],"window_mode":root.mode,"window_visible":root.visible,
		"low_processor_usage_mode":OS.low_processor_usage_mode,
		"low_processor_usage_sleep_usec":OS.low_processor_usage_mode_sleep_usec,
		"worker_pool_max_threads":ProjectSettings.get_setting("threading/worker_pool/max_threads",-1),
		"worker_pool_low_priority_ratio":ProjectSettings.get_setting("threading/worker_pool/low_priority_thread_ratio",0.3),
		"os_processor_count":OS.get_processor_count(),
		"display_backend":DisplayServer.get_name(),"render_method":RenderingServer.get_current_rendering_method(),
		"render_driver":RenderingServer.call("get_current_rendering_driver_name") if RenderingServer.has_method("get_current_rendering_driver_name") else "unknown"}

func _check(condition: bool, label: String) -> void:
	if not condition: failures.append(label)
	print("CONTINENT_CHECK ", "PASS " if condition else "FAIL ", label)

func _on_process() -> void:
	process_started = Time.get_ticks_usec()
	process_gap_us = process_started-previous_process_started if previous_process_started > 0 else 0
	previous_process_started = process_started

func _on_physics() -> void:
	var now := Time.get_ticks_usec()
	physics_gap_us = now-physics_started if physics_started > 0 else 0
	physics_gap_max_us = maxi(physics_gap_max_us,physics_gap_us)
	physics_steps_since_draw += 1
	physics_started = now

func _on_ready(identity: String, _imported: Node3D) -> void:
	var resident: Dictionary = stream.cells.get(identity, {})
	events.append({"kind":"cell_ready", "at_us":_elapsed(), "phase":phase,
		"cell":identity, "position":_point(position), "cache_status":resident.get("cache_status", ""),
		"phases_us":(resident.get("phases", {}) as Dictionary).duplicate(),
		"resource_timings":preload("res://src/world/resource_diagnostics.gd").snapshot(resident.get("resource_timings", {})),
		"prototype_timings":MeshPool.retention_snapshot().timings})

func _on_retiring(identity: String, _imported: Node3D) -> void:
	events.append({"kind":"cell_retiring", "at_us":_elapsed(), "phase":phase,
		"cell":identity, "position":_point(position)})

func _memory_sample(now: int) -> void:
	if now-last_memory_usec < 500000: return
	last_memory_usec = now
	memory.append({"at_us":_elapsed(), "phase":phase, "resident_estimated_bytes":stream.resident_bytes,
		"active_cells":stream.cells.size(), "retiring_cells":stream._retiring.size(),
		"texture_gpu_bytes":Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED),
		"buffer_gpu_bytes":Performance.get_monitor(Performance.RENDER_BUFFER_MEM_USED),
		"video_gpu_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		"static_bytes":OS.get_static_memory_usage(),
		"mesh_pool_live":MeshPool.live_count(), "texture_pool_live":TexturePool.retention_snapshot().live_entries})

func _coverage() -> Dictionary:
	var selected := stream.selection(position,true)
	var missing := []
	for entry: Dictionary in selected:
		if not stream.cells.has(str(entry.id)): missing.append(str(entry.id))
	return {"selected":selected.size(),"missing":missing,"active_cells":stream.cells.size(),
		"pending_cell":str(stream._pending.get("id","")),"retiring_cells":stream._retiring.size()}

func _on_draw() -> void:
	var now := Time.get_ticks_usec()
	if not tracing:
		previous_draw = now
		return
	if now-coverage_sample_usec >= 250000:
		coverage_sample_usec = now
		coverage = _coverage()
	var resident := stream.arrival_resident(position)
	var ray := PhysicsRayQueryParameters3D.create(position+Vector3.UP*200, position-Vector3.UP*200, 8)
	var ray_began := Time.get_ticks_usec()
	var probe_enabled := bool(configuration.get("ground_probe",true))
	var hit: Dictionary = stage.get_world_3d().direct_space_state.intersect_ray(ray) if probe_enabled else {"position":position}
	var ray_us := Time.get_ticks_usec()-ray_began
	var missing := hit.is_empty()
	if not missing and probe_enabled: last_ground_y = float((hit.position as Vector3).y)
	if missing: missing_ground_frames += 1
	if not resident: missing_resident_frames += 1
	var pipeline := {}
	var pipeline_began := Time.get_ticks_usec()
	for key: String in pipeline_enums:
		pipeline[key] = RenderingServer.get_rendering_info(int(pipeline_enums[key]))
	var pipeline_us := Time.get_ticks_usec()-pipeline_began
	var row := {"at_us":_elapsed(), "phase":phase,
		"frame_ms":float(now-previous_draw)/1000.0 if previous_draw > 0 else 0.0,
		"process_to_draw_ms":float(now-process_started)/1000.0,
		"process_interval_ms":float(process_gap_us)/1000.0,
		"physics_interval_ms":float(physics_gap_us)/1000.0,
		"physics_interval_max_ms":float(physics_gap_max_us)/1000.0,
		"physics_steps":physics_steps_since_draw,
		"process_monitor_ms":Performance.get_monitor(Performance.TIME_PROCESS)*1000.0,
		"physics_monitor_ms":Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)*1000.0,
		"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		"position":_point(position), "camera_focus_y":last_ground_y if is_finite(last_ground_y) else position.y,
		"ground_hit":not missing if probe_enabled else null, "resident":resident,
		"window_focused":root.has_focus(),
		"ground_y":float((hit.get("position", position) as Vector3).y),
		"worker_alive":stream._thread != null and stream._thread.is_alive(),
		"pending_cell":str(stream._pending.get("id", "")),
		"active_cells":stream.cells.size(), "retiring_cells":stream._retiring.size(),
		"selected_cells":int(coverage.selected),"selected_not_ready":(coverage.missing as Array).size(),
		"pipeline_counters":pipeline,"ground_ray_ms":float(ray_us)/1000.0,"pipeline_query_ms":float(pipeline_us)/1000.0}
	while event_cursor < stream.events.size():
		var event: Dictionary = stream.events[event_cursor].duplicate(true)
		event["kind"] = "stream_event"
		event["observed_us"] = _elapsed()
		event["phase"] = phase
		events.append(event)
		event_cursor += 1
	_memory_sample(now)
	if main_fixture != null:
		row["main_surface_work"] = main_fixture.call("surface_work")
	row["diagnostic_callback_ms"] = float(Time.get_ticks_usec()-now)/1000.0
	frames.append(row)
	physics_gap_max_us = 0
	physics_steps_since_draw = 0
	previous_draw = now

func _camera_position() -> void:
	# Match IsometricCameraController defaults and Main's camera, rather than
	# the wider orbit used by the historical rendered_stream_walk fixture.
	var pitch := deg_to_rad(-60.0)
	var offset := Vector3(0,-sin(pitch),cos(pitch))*26.0
	var focus := Vector3(position.x,last_ground_y if is_finite(last_ground_y) else position.y,position.z)
	camera.look_at_from_position(focus+offset,focus+Vector3.UP*1.2)

func _route(points: PackedVector3Array, distance: float) -> Vector3:
	for index in range(1, points.size()):
		var length := points[index-1].distance_to(points[index])
		if distance <= length: return points[index-1].lerp(points[index],distance/length) if length > 0 else points[index]
		distance -= length
	return points[points.size()-1]

func _travel(points: PackedVector3Array, label: String, speed: float) -> void:
	phase = label
	var length := 0.0
	for index in range(1,points.size()): length += points[index-1].distance_to(points[index])
	var began := Time.get_ticks_usec()
	var first_frame := frames.size()
	var missed_before := missing_ground_frames
	while true:
		var distance := float(Time.get_ticks_usec()-began)/1000000.0*speed
		position = _route(points,minf(distance,length))
		if main_fixture != null: main_fixture.call("move",position)
		stream.update_focus(position)
		_camera_position()
		await process_frame
		if distance >= length: break
	phases.append({"id":label,"start_us":began-origin_usec,"end_us":_elapsed(),
		"distance_metres":length,"speed_metres_per_second":speed,"first_frame":first_frame,
		"frames":frames.size()-first_frame,"missing_ground_frames":missing_ground_frames-missed_before,
		"coverage_at_end":_coverage()})

func run() -> void:
	configuration = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_CONTINENT_BENCH_CONFIG")))
	root.size = Vector2i(1280,720)
	OS.low_processor_usage_mode_sleep_usec = 1
	Engine.max_fps = int(configuration.get("fps_limit",60))
	Graphics._texture_skip = int(configuration.get("mip_skip",0))
	_check(DisplayServer.get_name() != "headless", "rendered backend")
	_check(preload("res://src/world/gltf_quantization.gd").ensure_registered()
		and preload("res://src/world/vram_textures.gd").ensure_registered()
		and preload("res://src/world/map_mesh_extension.gd").ensure_registered(), "main initializes importer extensions")
	for enum_name: String in ClassDB.class_get_enum_list("RenderingServer"):
		for name: String in ClassDB.class_get_enum_constants("RenderingServer",enum_name):
			if "PIPELINE_COMPILATIONS" in name: pipeline_enums[name] = ClassDB.class_get_integer_constant("RenderingServer",name)
	var environment: WorldEnvironment
	var sun: DirectionalLight3D
	if bool(configuration.get("main_listeners",false)):
		main_fixture = load("res://tests/integration/continent_stream_benchmark_main_fixture.gd").new()
		var actual: Dictionary = await main_fixture.call("create",self,str(configuration.manifest))
		stage = actual.stage
		loader = actual.loader
		camera = actual.camera
		environment = actual.environment
		sun = actual.sun
	else:
		stage = Node3D.new()
		root.add_child(stage)
		loader = WorldLoader.new()
		stage.add_child(loader)
		camera = Camera3D.new()
		stage.add_child(camera)
		environment = WorldEnvironment.new()
		environment.environment = Environment.new()
		stage.add_child(environment)
		sun = DirectionalLight3D.new()
		sun.shadow_enabled = true
		stage.add_child(sun)
	# Main restores saved presentation settings while entering its scene. The
	# benchmark's explicit options are authoritative in both harness modes.
	Engine.max_fps = int(configuration.get("fps_limit",60))
	Graphics._texture_skip = int(configuration.get("mip_skip",0))
	camera.current = true
	camera.fov = 50
	camera.near = 1
	camera.far = 1800
	camera.cull_mask = 3
	var points := PackedVector3Array()
	for value: Array in configuration.points: points.append(_position(value))
	position = points[0]
	_camera_position()
	var context_start := _window_context()
	origin_usec = Time.get_ticks_usec()
	loader.load_world(str(configuration.manifest),position,true)
	metadata_setup_us = Time.get_ticks_usec()-origin_usec
	stream = loader.world_root as ContinentChunkStream
	_check(stream != null, "production continent stream loaded")
	if stream == null: quit(1); return
	if int(configuration.get("budget_mib",0)) > 0: stream.maximum_resident_bytes = int(configuration.budget_mib)*1048576
	if main_fixture == null: WorldEnvironmentBinder.apply(loader.manifest,environment,sun)
	if main_fixture != null: main_fixture.call("install_proxies",points)
	stream.cell_ready.connect(_on_ready)
	stream.cell_retiring.connect(_on_retiring)
	process_frame.connect(_on_process)
	physics_frame.connect(_on_physics)
	RenderingServer.frame_post_draw.connect(_on_draw)
	phase = "arrival"
	tracing = true
	stream.begin_arrival(position)
	var arrival_radius := float(configuration.get("arrival_radius",36.0))
	var arrival_deadline := Time.get_ticks_msec()+120000
	while not stream.arrival_ready(position,arrival_radius) and Time.get_ticks_msec() < arrival_deadline: await process_frame
	_check(stream.arrival_ready(position,arrival_radius), "arrival ready before timeout")
	await physics_frame
	if main_fixture != null: main_fixture.call("arrival_complete")
	var progress := stream.arrival_progress(position,arrival_radius)
	phases.append({"id":"arrival","start_us":0,"end_us":_elapsed(),"frames":frames.size(),
		"radius_metres":arrival_radius,"radius_ready_cells":progress.x,"radius_total_cells":progress.y,
		"coverage_at_end":_coverage()})
	var reverse := points.duplicate()
	reverse.reverse()
	for repetition in range(int(configuration.get("repeats",2))):
		var prefix := "first" if repetition == 0 else "repeat%d" % repetition
		var order := ["fast","walk"] if str(configuration.get("speed_order","walk-first")) == "fast-first" else ["walk","fast"]
		for mode: String in order:
			var speed := float(configuration.get("walk_speed",5.0)) if mode == "walk" else float(configuration.get("fast_speed",10.0))
			await _travel(points,prefix+"_"+mode+"_out",speed)
			await _travel(reverse,prefix+"_"+mode+"_back",speed)
	movement_end_us = _elapsed()
	phase = "post_route_settle"
	var settle_began := _elapsed()
	var settle_deadline := Time.get_ticks_msec()+60000
	while Time.get_ticks_msec() < settle_deadline:
		var current := _coverage()
		if (current.missing as Array).is_empty() and stream._thread == null and stream._retiring.is_empty() \
				and (main_fixture == null or bool(main_fixture.call("settled"))): break
		stream.update_focus(position)
		await process_frame
	_check((_coverage().missing as Array).is_empty() and stream._thread == null and stream._retiring.is_empty(),
		"all selected terrain finished and workers/retirement idle after route")
	if main_fixture != null: _check(bool(main_fixture.call("settled")),"Main surface followups drained")
	phases.append({"id":"post_route_settle","start_us":settle_began,"end_us":_elapsed(),"coverage_at_end":_coverage()})
	tracing = false
	var context_end := _window_context()
	phase = "teardown"
	var final_diagnostics := stream.diagnostic_snapshot()
	var final_main: Dictionary = main_fixture.call("snapshot") if main_fixture != null else {}
	await ContinentChunkStream.drain_workers(self)
	loader.unload_world()
	if main_fixture != null:
		main_fixture.call("release")
	else:
		stage.queue_free()
	for unused in range(12): await process_frame
	GlbSceneCache.clear()
	# These process-local static caches deliberately keep reusable shaders and
	# class textures during play. The fixture has unloaded every world and
	# drained every worker; release its final owners before renderer shutdown.
	LookGround._biome_shader = null
	LookGround._class_textures.clear()
	preload("res://src/world/season_surfaces.gd")._shaders.clear()
	if RenderingServer.has_method("force_sync"): RenderingServer.call("force_sync")
	# Renderer work submitted by workers can finish after their Node trees are
	# released. This is outside every measured phase and does not hide shutdown
	# errors: the Python runner still rejects any engine error.
	for unused in range(60): await process_frame
	_check(MeshPool.live_count() == 0 and int(TexturePool.retention_snapshot().live_entries) == 0,"all shared resources released")
	var report := {"schema":1,"ok":failures.is_empty(),"failures":failures,"configuration":configuration,
		"configuration_sha256":FileAccess.get_sha256(OS.get_environment("RL_CONTINENT_BENCH_CONFIG")),
		"scope":"Rendered actual Main listener integration fixture; camera proxy; no server, player replay, screenshots or GPU readbacks." if main_fixture != null else "Rendered ContinentChunkStream component; camera proxy, production limits/environment; no Main listeners, server, actors, screenshots or GPU readbacks. Cold process does not imply cold OS/driver caches.",
		"engine":Engine.get_version_info(),"renderer":RenderingServer.get_current_rendering_method(),
		"gpu":RenderingServer.get_video_adapter_name(),"user_dir":OS.get_user_data_dir(),
		"fps_limit":Engine.max_fps,"pipeline_counter_names":pipeline_enums.keys(),
		"window_context":{"start":context_start,"end":context_end},
		"movement_end_us":movement_end_us,
		"territory_metadata_setup_us":metadata_setup_us,
		"physics_separate_thread":ProjectSettings.get_setting("physics/3d/run_on_separate_thread",false),
		"ground_probe":"One navigation-layer PhysicsServer ray per rendered frame; its measured wait is reported separately and can affect the following frame gap.",
		"camera":{"yaw_degrees":0,"pitch_degrees":-60,"distance":26,"focus_height":1.2,"near":1,"far":1800,"fov":50,"cull_mask":3,"ground_following":true},
		"frames":frames,"phases":phases,"events":events,"memory":memory,
		"final_stream":final_diagnostics,"main_integration":final_main,
		"texture_pool":TexturePool.retention_snapshot(),"mesh_pool":MeshPool.retention_snapshot()}
	var file := FileAccess.open(OS.get_environment("RL_CONTINENT_BENCH_REPORT"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"  "))
	file.close()
	print("CONTINENT_BENCH_DONE ",OS.get_environment("RL_CONTINENT_BENCH_REPORT"))
	quit(0 if failures.is_empty() else 1)
