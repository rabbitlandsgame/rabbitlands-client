extends SceneTree
## Real Main/network client against the runner's disposable loopback server.
const Readiness := preload("res://tests/integration/client_world_readiness.gd")
var main: Control
var state: Node
var network: Node
var directory := ""
var pending: Dictionary = {}
var pings: Array[float] = []
var sequence := 0
var failures := 0
var startup_started_usec := 0
var startup_last_usec := 0
var startup_recording := false
var startup_frames: Array[float] = []
var startup_ui_actions: Array[String] = []

func _record_startup_frame() -> void:
	if not startup_recording: return
	var now := Time.get_ticks_usec()
	startup_frames.append((now - startup_last_usec) / 1000.0)
	startup_last_usec = now

func _record_readiness(ready: bool, snapshot: Dictionary, stable: int,
		resource_started: int, reason := "") -> void:
	startup_recording = false
	if process_frame.is_connected(_record_startup_frame):
		process_frame.disconnect(_record_startup_frame)
	write_json("readiness.json", {"ready": ready,
		"waitMilliseconds": (Time.get_ticks_usec() - startup_started_usec) / 1000.0,
		"resourceWaitMilliseconds": Time.get_ticks_msec() - resource_started,
		"startup_frame_interval_ms": stats(startup_frames),
		"startup_frame_intervals_ms": startup_frames,
		"state": snapshot, "stableFrames": stable,
		"requiredStableFrames": Readiness.STABLE_RESOURCE_FRAMES,
		"minimumResourceWaitMilliseconds": Readiness.MINIMUM_READINESS_MSEC,
		"startupTimeoutMilliseconds": Readiness.STARTUP_TIMEOUT_MSEC,
		"reason": reason,
		"startup_ui_actions": startup_ui_actions,
		"scope": "Entire startup from before Main instantiation; map/resource warmup is separate from spawn windows."})

func _remaining_startup_seconds() -> float:
	return maxf(0.0, (Readiness.STARTUP_TIMEOUT_MSEC -
		(Time.get_ticks_usec() - startup_started_usec) / 1000.0) / 1000.0)

func _wait_for_resource_readiness() -> bool:
	var started := Time.get_ticks_msec()
	var stable := Readiness.StableResources.new(started)
	var snapshot: Dictionary = Readiness.snapshot(main)
	var ready := false
	while _remaining_startup_seconds() > 0:
		await physics_frame
		await process_frame
		snapshot = Readiness.snapshot(main)
		if _remaining_startup_seconds() <= 0: break
		var idle: bool = bool(snapshot.get("ready", false)) and bool(state.authenticated) \
			and str(state.connection_state) == "connected" and main.actor_nodes.has(state.local_actor_id)
		if stable.observe(Readiness.resource_signature(main), idle, Time.get_ticks_msec()):
			ready = true
			break
	_record_readiness(ready, snapshot, stable.stable_frames, started,
		"stable map/resources" if ready else "map/resource startup deadline expired")
	return ready

func _init() -> void:
	run.call_deferred()

func write_json(name: String, data: Dictionary) -> void:
	var file := FileAccess.open(directory.path_join(name), FileAccess.WRITE)
	file.store_string(JSON.stringify(data, "  "))
	file.close()

func wait_until(predicate: Callable, seconds := 90.0) -> bool:
	var end := Time.get_ticks_msec() + int(seconds * 1000)
	while Time.get_ticks_msec() < end:
		if predicate.call(): return true
		await process_frame
	return false

func stats(values: Array[float]) -> Dictionary:
	if values.is_empty(): return {"count": 0}
	var sorted := values.duplicate()
	sorted.sort()
	return {"count": sorted.size(), "median": sorted[sorted.size() / 2],
		"p95": sorted[mini(sorted.size() - 1, int(sorted.size() * 0.95))], "max": sorted[-1]}

func run() -> void:
	directory = OS.get_environment("RL_SPAWN_TEST_OUT")
	startup_started_usec = Time.get_ticks_usec()
	startup_last_usec = startup_started_usec
	startup_recording = true
	process_frame.connect(_record_startup_frame)
	Engine.max_fps = int(OS.get_environment("RL_SPAWN_TEST_FPS_CAP")) if OS.has_environment("RL_SPAWN_TEST_FPS_CAP") else 60
	root.size = Vector2i(1280, 720)
	var profiling := OS.get_environment("RL_SPAWN_TEST_PROFILE") == "1"
	main = (load("res://tests/integration/crowd_benchmark_main.tscn" if profiling else "res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	network = root.get_node("Network")
	network.packet_received.connect(func(command: int, payload: PackedByteArray) -> void:
		if command == EloriaProtocol.ServerMessage.PONG and payload.size() >= 4:
			var token := payload.decode_u32(0)
			if pending.has(token):
				pings.append((Time.get_ticks_usec() - int(pending[token])) / 1000.0)
				pending.erase(token))
	network.connect_to_server("127.0.0.1", int(OS.get_environment("RL_SPAWN_TEST_PORT")), false)
	if not await wait_until(func() -> bool: return str(state.connection_state) == "connected",
			minf(90.0, _remaining_startup_seconds())):
		_record_readiness(false, Readiness.snapshot(main), 0, Time.get_ticks_msec(), "connection timeout")
		push_error("spawn probe connection timeout"); quit(1); return
	network.login(OS.get_environment("RL_SPAWN_TEST_USER"), OS.get_environment("RL_SPAWN_TEST_PASSWORD"))
	if not await wait_until(func() -> bool:
		return bool(state.authenticated) and main.world_loader.world_root != null \
			and main.actor_nodes.has(state.local_actor_id) and not main._deferred_map_load,
			_remaining_startup_seconds()):
		_record_readiness(false, Readiness.snapshot(main), 0, Time.get_ticks_msec(), "initial world timeout")
		push_error("spawn probe world readiness timeout"); quit(1); return
	# Continue into ordinary gameplay, as a person does after first login.
	# Never accept an update; only dismiss the source-build instructions.
	for node: Node in main.find_children("*", "AcceptDialog", true, false):
		var dialog := node as AcceptDialog
		if dialog.visible and dialog.title == "Update your custom build":
			dialog.confirmed.emit()
			dialog.hide()
			startup_ui_actions.append("Continue playing on custom-build update notice")
	if main.popup_panel.visible:
		main._on_popup_dismiss_pressed()
		startup_ui_actions.append("Dismiss first-login welcome")
	network.send_chat("#demigod")
	if not await _wait_for_resource_readiness():
		push_error("spawn probe map/resource readiness timeout"); quit(1); return
	Engine.max_fps = int(OS.get_environment("RL_SPAWN_TEST_FPS_CAP")) if OS.has_environment("RL_SPAWN_TEST_FPS_CAP") else 60
	var dto: Dictionary = state.actors[state.local_actor_id]
	write_json("ready.json", {"map": state.current_map, "x": dto.x, "y": dto.y,
		"actor": state.local_actor_id, "network": state.connection_state,
		"fps_cap": Engine.max_fps, "display": DisplayServer.get_name(),
		"vsync": DisplayServer.window_get_vsync_mode(),
		"window_mode": DisplayServer.window_get_mode(),
		"window_size": str(root.size), "world_viewport_size": str(main.main_viewport.size),
		"startup_ui_actions": startup_ui_actions})
	var completed := ""
	var control: Dictionary = {}
	var results: Array = []
	while true:
		await create_timer(0.1).timeout
		if FileAccess.file_exists(directory.path_join("control.json")):
			var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(directory.path_join("control.json")))
			if parsed is Dictionary: control = parsed
		if control.get("stop", false): break
		var id := str(control.get("id", ""))
		if id.is_empty() or id == completed: continue
		pings.clear(); pending.clear()
		network.reset_dispatch_statistics()
		var frames: Array[float] = []
		var profile_values: Dictionary = {}
		if profiling: main.benchmark_reset_frame()
		var changes := 0
		var start_tile := Vector2i(int(dto.x), int(dto.y))
		var previous_tile := start_tile
		var peak_actors: int = state.actors.size()
		var until := Time.get_ticks_msec() + int(control.get("duration_ms", 5000))
		var next_ping := 0
		var next_move := Time.get_ticks_msec() + 500
		var moving_out := true
		var last := Time.get_ticks_usec()
		write_json("phase-ready.json", {"id": id})
		while Time.get_ticks_msec() < until:
			await process_frame
			var now := Time.get_ticks_usec()
			frames.append((now - last) / 1000.0); last = now
			if profiling:
				var measured: Dictionary = main.benchmark_take_frame().microseconds
				for key: Variant in measured:
					if not profile_values.has(key): profile_values[key] = [] as Array[float]
					profile_values[key].append(float(measured[key]) / 1000.0)
				main.benchmark_reset_frame()
			var now_ms := Time.get_ticks_msec()
			if now_ms >= next_ping:
				sequence += 1
				var payload := PackedByteArray(); payload.resize(4); payload.encode_u32(0, sequence)
				pending[sequence] = now
				network.send_frame(EloriaProtocol.encode(EloriaProtocol.ClientMessage.PING, payload))
				next_ping = now_ms + 100
			if now_ms >= next_move:
				var target := start_tile + (Vector2i(-1, 0) if moving_out else Vector2i.ZERO)
				network.send_frame(EloriaProtocol.move_to(target.x, target.y, true))
				moving_out = not moving_out; next_move = now_ms + 700
			dto = state.actors.get(state.local_actor_id, {})
			var tile := Vector2i(int(dto.get("x", -1)), int(dto.get("y", -1)))
			if tile != previous_tile: changes += 1; previous_tile = tile
			peak_actors = maxi(peak_actors, state.actors.size())
		# Let pings sent at the sample boundary return; do not count this grace
		# period as part of the measured frame window.
		await create_timer(0.25).timeout
		var unpresented := 0
		for actor_id: Variant in state.actors:
			if not main.actor_nodes.has(actor_id):
				unpresented += 1
		var row := {"id": id, "ping_ms": stats(pings), "frame_interval_ms": stats(frames),
			"frame_intervals_ms": frames,
			"window_mode": DisplayServer.window_get_mode(),
			"vsync": DisplayServer.window_get_vsync_mode(),
			"packet_dispatch": network.dispatch_statistics(),
			"unpresented_actor_records": unpresented, "presented_actor_nodes": main.actor_nodes.size(),
			"built_actor_bodies": main._built_bodies,
			"unanswered_pings": pending.size(), "movement_updates": changes,
			"peak_actor_records": peak_actors, "connected": str(state.connection_state) == "connected",
			"map": state.current_map}
		if profiling:
			var profile_summary := {}
			for key: Variant in profile_values: profile_summary[key] = stats(profile_values[key])
			row["profile_ms"] = profile_summary
		results.append(row); write_json(id + ".json", row)
		completed = id
	network.disconnect_from_server()
	main.actor_resource_warmup.clear()
	while not main.actor_resource_warmup.is_idle():
		await process_frame
	main.queue_free()
	await process_frame
	write_json("client-results.json", {"scope": "real Godot Main and TCP, isolated local server", "scenarios": results})
	quit(failures)
