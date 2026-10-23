extends SceneTree
## Phase 4 crowd presentation benchmark.
##
## How long a frame takes with the crowd the server's interest caps will send:
## 100, 160, 200 and 300 actors, a third of them active (half walking, half
## fighting), laid out like the capacity audit's two hot spots - S3, a market
## crowd of equipped players within 40 tiles, and S2, an invasion of creatures
## within 30 tiles - and a continuous-combat crowd where everyone fights. An
## `aoi` cell spreads its crowd to the 88-tile edge of the player area of
## interest, where bodies are built on approach rather than up front.
##
## Each cell reports frame time (mean, p50, p95, p99, max) and p5 FPS, the
## component timers of the benchmark Main subclass, memory before and after the
## crowd, and what the presentation did: bodies built and deferred, stand-ins,
## animation tiers, skeletons processing, live effects and the effect budget.
## Headless runs report scene CPU. Windowed runs disable vsync and retain an
## explicit frame cap (60 by default); frame-work excludes its sleep, while
## delivered frame intervals and the renderer's own timers stay separate.
## Phase1 adds a mixed equipped crowd with80 approved mounts, explicit authored
## herd availability, and client-driven southern traversal. No server service
## or private session recording is required for these synthetic workloads.
##
## The `live` and `stress` crowds are synthetic: actor records and real server
## packet shapes fed through AppState, as the network would, at a fixed cadence.
## The `replay` driver plays one connection of a server session recording
## (the server's eloria/session_recorder.py, format RLREC1) instead: Main
## becomes that player (YOU_ARE) on its map (CHANGE_MAP), everything the server
## sent before the start offset is applied fast, and from there every outbound
## frame reaches AppState at its recorded time, as the socket would have
## delivered it. Recordings hold player data: keep them out of this repository.
## Run it through run_crowd_presentation_benchmark.py, which isolates user data
## and records the machine. Environment:
##
## - RABBITLANDS_CROWD_BENCH_CELLS: comma list of cell ids, or `phase4` (default),
##   `quick`, `phase1` or `all`; see `cells_for`. A replay runs its one cell.
## - RABBITLANDS_CROWD_BENCH_MAP: map id (default four_gates, or the recording's
##   map for a replay; `none` for no map).
## - RABBITLANDS_CROWD_BENCH_CENTRE: `x,y` server tile the player stands on
##   (default: the map's own centre, or the hot spot for landfall and twinbrook).
## - RABBITLANDS_CROWD_BENCH_SAMPLE_MSEC / _WARMUP_MSEC / _CADENCE_MSEC.
## - RABBITLANDS_CROWD_BENCH_DRIVER: `live` (default), `stress` or `replay`.
## - RABBITLANDS_CROWD_BENCH_REPLAY: the .rlrec file a replay plays.
## - RABBITLANDS_CROWD_BENCH_REPLAY_START_MSEC: where the replay's warmup starts,
##   in ms after the recording's YOU_ARE (default 30000).
## - RABBITLANDS_CROWD_BENCH_OUT: report path (default user://).
## - RABBITLANDS_CROWD_PRESENTATION / RABBITLANDS_CROWD_BODY_CAP: read by Main.
## - RABBITLANDS_CROWD_BENCH_PRESENCE: send ELORIA_PRESENCE once a second with
##   this many players beyond the area of interest (82-139 tiles away, each
##   walking a tile a second around the player), as a server with player
##   interest does. Default 0: none.
## - RABBITLANDS_CROWD_BENCH_SERVER_TIME=1: open every tick with an
##   ELORIA_SERVER_TIME stamp, so remote steps are paced by server time.

const BENCHMARK_MAIN_PATH := "res://tests/integration/crowd_benchmark_main.tscn"
const TIERS := AnimationGate.Tier
const MODELS := "res://data/actors/models.json"
const FIRST_ACTOR_ID := 14000
const FULL_KIT_A := {0: 114, 1: 106, 2: 0, 3: 117, 4: 171, 5: 184, 6: 192}
const FULL_KIT_B := {0: 164, 1: 111, 2: 1, 3: 109, 4: 172, 5: 185, 6: 193}
const SCHEMA := 1
const Workloads := preload("res://tests/integration/performance_workloads.gd")
const MAX_SPAWN_MSEC := 240000
const MAX_READINESS_MSEC := 60000
const MIN_SAMPLE_FRAMES := 60
## Where each hot spot is when the benchmark stands on its map: the Landfall
## market (the mean of the isle's NPC posts, as the server's S3 preset takes it)
## and a Twinbrook invasion wave's authored centre (S2).
const HOT_SPOTS := {"landfall": Vector2i(122, 225), "twinbrook": Vector2i(675, 186)}
const REPLAY_MAGIC := "RLREC1\n"
## A recording record: kind (1 byte), monotonic nanoseconds (u64), length (u32).
const REPLAY_RECORD_HEADER := 13
const REPLAY_DEFAULT_START_MSEC := 30000
## Frames the replay's fast prologue never applies. The setup has already
## logged Main in, and effects, animations and numbers from before the start
## would be long gone by then in play; applying them all at once would only
## leave a burst of effect nodes behind.
const REPLAY_LOGIN_FRAMES := [EloriaProtocol.ServerMessage.LOG_IN_OK,
	EloriaProtocol.ServerMessage.LOG_IN_NOT_OK, EloriaProtocol.ServerMessage.CREATE_CHAR_OK,
	EloriaProtocol.ServerMessage.CREATE_CHAR_NOT_OK]
const REPLAY_TRANSIENT_FRAMES := [EloriaProtocol.ServerMessage.SEND_SPECIAL_EFFECT,
	EloriaProtocol.ServerMessage.ADD_ACTOR_ANIMATION, EloriaProtocol.ServerMessage.GET_ACTOR_DAMAGE,
	EloriaProtocol.ServerMessage.GET_ACTOR_HEAL, EloriaProtocol.ServerMessage.MISSILE_AIM_A_AT_B,
	EloriaProtocol.ServerMessage.MISSILE_AIM_A_AT_XYZ, EloriaProtocol.ServerMessage.MISSILE_FIRE_A_TO_B,
	EloriaProtocol.ServerMessage.MISSILE_FIRE_A_TO_XYZ, EloriaProtocol.ServerMessage.PLAY_SOUND,
	EloriaProtocol.ServerMessage.THUNDER]
## Recorded time the prologue applies per frame, so Main presents it in steps.
const REPLAY_PROLOGUE_STEP_NSEC := 1000000000

var _failures := 0
var _headless := false
var _main: Control
var _app_state: Node
var _adapter: CoordinateAdapter
var _creatures: Array = []
var _report: Dictionary = {}
var _centre := Vector2i.ZERO
var _driver_packets := 0
var _driver_usec := 0
var _fps_cap := 60
## RABBITLANDS_CROWD_BENCH_ATTRIBUTION=1: every body's update_pose is timed and
## its skeleton updates counted (crowd_benchmark_main.gd), which adds a call
## per skeleton update; for attribution, not for a comparison.
var _attribution := false
var _attributed: Dictionary = {}
## Frame work: from the first physics step (or the process step) of an engine
## iteration to the end of its draw, so the frame cap's sleep is not counted.
## A capped run keeps the share of frames that carry a packet tick what it is
## on a 60 Hz display; an uncapped one would thin it out and flatter p95.
var _iteration_started_usec := -1
var _last_iteration_usec := -1.0
var _process_started_usec := -1
var _process_ended_usec := -1
var _draw_started_usec := -1
var _last_phases: Dictionary = {}
var _frame_marker: Node
## The player Main presents: FIRST_ACTOR_ID for a synthetic crowd, the
## recording's YOU_ARE for a replay.
var _local_id := FIRST_ACTOR_ID
## The replay: the file's bytes and, for each outbound frame in order, its
## offset, length and recorded time. `_replay_origin_ns` is the recorded time
## the warmup starts at, `_replay_index` the next frame to deliver.
var _replay_bytes := PackedByteArray()
var _replay_offsets := PackedInt64Array()
var _replay_sizes := PackedInt32Array()
var _replay_times := PackedInt64Array()
var _replay_index := 0
var _replay_origin_ns := 0
var _replay_you_are_ns := 0
var _replay_started_usec := 0
var _replay_map := ""
var _replay_spawn := Vector2i(-1, -1)
var _replay_stats: Dictionary = {}
## Protocol v2 inputs (RABBITLANDS_CROWD_BENCH_PRESENCE / _SERVER_TIME).
var _presence_dots := 0
var _server_time := false
var _route_capture := false
var _route_frame_series: Array[float] = []
var _route_wall_series: Array[float] = []
var _route_last_frame_usec := 0
var _route_primed := false
var _route_peak_static_bytes := 0

func _init() -> void:
	call_deferred("_run")


## The cells a profile runs. `phase4` is the exit-criterion set; `quick` is one
## market and one invasion cell for a smoke run.
static func cells_for(profile: String) -> Array:
	var cells: Array = []
	var legacy_all := profile == "phase4"
	for count: int in [100, 160, 200, 300]:
		cells.append({"id": "s3-market-%d" % count, "count": count, "shape": "market",
			"activity": "third_active"})
		cells.append({"id": "s2-invasion-%d" % count, "count": count, "shape": "invasion",
			"activity": "third_active"})
	for count: int in [100, 160]:
		cells.append({"id": "combat-%d" % count, "count": count, "shape": "melee",
			"activity": "all_combat"})
	cells.append({"id": "aoi-160", "count": 160, "shape": "aoi", "activity": "third_active"})
	# The map and the player alone: what every other cell's frame is built on.
	cells.append({"id": "empty", "count": 1, "shape": "market", "activity": "idle"})
	if legacy_all:
		return cells
	cells.append({"id": "mixed-mounted-160", "count": 160, "shape": "mounted",
		"mountedCount": 80, "activity": "third_active"})
	cells.append({"id": "authored-herd", "count": 1, "shape": "herd", "activity": "idle"})
	for visit: String in ["cold", "warm"]:
		cells.append({"id": "traversal-southern-" + visit, "count": 1,
			"shape": "traversal", "activity": "route", "visit": visit})
	if profile == "all":
		return cells
	if profile == "phase1":
		var phase_one := ["s3-market-160", "s2-invasion-160", "mixed-mounted-160",
			"combat-160", "empty", "traversal-southern-cold", "traversal-southern-warm"]
		var selected: Array = []
		for wanted_id: String in phase_one:
			for cell: Dictionary in cells:
				if str(cell.id) == wanted_id:
					selected.append(cell)
		return selected
	if profile == "quick":
		return cells.filter(func(cell: Dictionary) -> bool:
			return str(cell.id) in ["s3-market-160", "s2-invasion-160"])
	var wanted := profile.split(",", false)
	return cells.filter(func(cell: Dictionary) -> bool: return str(cell.id) in wanted)


func _run() -> void:
	if not _write_startup_handshake():
		quit(1)
		return
	_headless = DisplayServer.get_name() == "headless"
	_fps_cap = _env_int("RABBITLANDS_CROWD_BENCH_FPS_CAP", 60, 0)
	Engine.max_fps = _fps_cap
	OS.low_processor_usage_mode_sleep_usec = 1
	if not _headless:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var requested_resolution := Workloads.resolution(_env("RABBITLANDS_CROWD_BENCH_RESOLUTION", "1280x720"))
	root.size = requested_resolution
	var replay := _driver_mode() == "replay"
	var profile := "replay" if replay else _env("RABBITLANDS_CROWD_BENCH_CELLS", "phase4")
	var cells := [] if replay else cells_for(profile)
	_presence_dots = _env_int("RABBITLANDS_CROWD_BENCH_PRESENCE", 0, 0)
	_server_time = OS.get_environment("RABBITLANDS_CROWD_BENCH_SERVER_TIME").strip_edges() == "1"
	_report = {
		"schemaVersion": SCHEMA,
		"benchmark": "crowd_presentation",
		"label": OS.get_environment("RABBITLANDS_CROWD_BENCH_LABEL"),
		"profile": profile,
		"headless": _headless,
		"display": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"videoAdapter": RenderingServer.get_video_adapter_name(),
		"videoVendor": RenderingServer.get_video_adapter_vendor(),
		"processor": OS.get_processor_name(),
		"processorCount": OS.get_processor_count(),
		"memoryInfo": OS.get_memory_info(),
		"godot": Engine.get_version_info(),
		"runtimeBuild": {"standalone": OS.has_feature("standalone"), "editor": OS.has_feature("editor"),
			"userDataDir": OS.get_user_data_dir(),
			"template": OS.has_feature("template"), "debug": OS.has_feature("debug"),
			"release": OS.has_feature("release"), "executablePath": OS.get_executable_path()},
		"viewport": [root.size.x, root.size.y],
		"presentation": OS.get_environment("RABBITLANDS_CROWD_PRESENTATION"),
		"graphicsQuality": LookProfile.quality_name(LookProfile.quality()),
		"diagnostics": OS.get_environment("RABBITLANDS_CROWD_BENCH_DIAG"),
		"bodyCap": OS.get_environment("RABBITLANDS_CROWD_BODY_CAP"),
		"presenceDots": _presence_dots,
		"serverTime": _server_time,
		"measurement": {
			"sampleMilliseconds": _env_int("RABBITLANDS_CROWD_BENCH_SAMPLE_MSEC", 6000, 500),
			"warmupMilliseconds": _env_int("RABBITLANDS_CROWD_BENCH_WARMUP_MSEC", 2000, 100),
			"driver": _driver_mode(),
			"cadenceMilliseconds": null if replay else _env_int("RABBITLANDS_CROWD_BENCH_CADENCE_MSEC",
				50 if _driver_mode() == "live" else 100, 25),
			"driverDescription": _driver_description(),
			"vsync": "disabled" if not _headless else "n/a",
			"fpsCap": _env_int("RABBITLANDS_CROWD_BENCH_FPS_CAP", 60, 0),
			"frameMetric": ("frame work: first physics step (or process) to frame_post_draw "
				+ "(windowed) or to a deferred call queued by the last node to process, after "
				+ "Main's deferred world sync (headless, which draws nothing); the frame-cap "
				+ "sleep is excluded"),
			"wallMetric": "process_frame to process_frame, including the frame-cap sleep",
		},
		"cells": [],
		"failures": [],
		"unixTime": int(Time.get_unix_time_from_system()),
	}
	if replay:
		var recording := _load_replay(OS.get_environment("RABBITLANDS_CROWD_BENCH_REPLAY").strip_edges())
		_report["replay"] = recording
		if bool(recording.get("ok", false)):
			cells.append({"id": "replay-%s" % _replay_map, "count": 0, "shape": "replay",
				"activity": "recorded"})
	else:
		_creatures = _creature_actor_types()
	if not _expect(not cells.is_empty(), "profile %s selects at least one cell" % profile) \
			or not _expect(replay or not _creatures.is_empty(), "creature models resolve"):
		_finish()
		return
	await _set_up_main()
	if _main == null:
		_finish()
		return
	Engine.max_fps = _fps_cap
	physics_frame.connect(_on_iteration_started)
	process_frame.connect(_on_process_started)
	# The last node to process marks where node processing ends and the
	# deferred flush (Main's world sync, every skeleton's update: modifiers,
	# skeleton_updated listeners, skins) begins. Nothing is drawn headless and
	# frame_post_draw never fires: there the frame ends at a deferred call the
	# marker queues, which runs after Main's own deferred world sync.
	var marker_script := GDScript.new()
	marker_script.source_code = ("extends Node\nsignal processed\nsignal process_ended\n"
		+ "func _process(_delta: float) -> void:\n"
		+ "\tprocess_ended.emit()\n"
		+ "\tcall_deferred(\"emit_signal\", \"processed\")\n")
	marker_script.reload()
	_frame_marker = Node.new()
	_frame_marker.set_script(marker_script)
	_frame_marker.process_priority = 1 << 30
	root.add_child(_frame_marker)
	_frame_marker.connect("process_ended", _on_process_ended)
	if _headless:
		_frame_marker.connect("processed", _on_iteration_drawn)
	else:
		RenderingServer.frame_pre_draw.connect(_on_draw_started)
		RenderingServer.frame_post_draw.connect(_on_iteration_drawn)
	_report["crowdPolicy"] = (_main.get("crowd") as RefCounted).call("describe") \
		if _main.get("crowd") != null else {"available": false}
	_record_effective_runtime()
	# A replay warms nothing: what the recording shows is built in its prologue,
	# and a model first seen during the sample costs what it costs in play.
	if not replay:
		await _prewarm()
	for cell: Dictionary in cells:
		if str(cell.shape) == "traversal":
			await _run_traversal_cell(cell)
		else:
			await _run_cell(cell)
	await _tear_down_main()
	_finish()


## A release template ignores --script. Prove that the intended workload loop
## started before imports/map loads, binding the acknowledgement to this run.
func _write_startup_handshake() -> bool:
	var execution_mode := _env("RABBITLANDS_CROWD_BENCH_EXECUTION_MODE", "project")
	if execution_mode not in ["project", "exported"]:
		push_error("Invalid crowd benchmark execution mode: " + execution_mode)
		return false
	var report_path := _env("RABBITLANDS_CROWD_BENCH_OUT", "user://crowd_presentation_benchmark.json")
	var destination := ProjectSettings.globalize_path(report_path + ".started.json")
	var temporary := destination + ".tmp-" + str(OS.get_process_id())
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write crowd benchmark startup acknowledgement: " + temporary)
		return false
	file.store_string(JSON.stringify({"schemaVersion": 1, "benchmark": "crowd_presentation",
		"pid": OS.get_process_id(), "executablePath": OS.get_executable_path(),
		"executionMode": execution_mode, "userDataDir": OS.get_user_data_dir(),
		"startToken": OS.get_environment("RABBITLANDS_CROWD_BENCH_START_TOKEN")}, "  "))
	file.flush()
	file.close()
	var error := DirAccess.rename_absolute(temporary, destination)
	if error != OK:
		DirAccess.remove_absolute(temporary)
		push_error("Cannot publish crowd benchmark startup acknowledgement: %s" % error_string(error))
		return false
	return true


func _set_up_main() -> void:
	var scene := load(BENCHMARK_MAIN_PATH) as PackedScene
	if not _expect(scene != null, "benchmark Main scene loads"):
		return
	_main = scene.instantiate() as Control
	root.add_child(_main)
	await process_frame
	_app_state = root.get_node_or_null("/root/AppState")
	if not _expect(_app_state != null, "AppState is available"):
		_main = null
		return
	_app_state.set("authenticated", true)
	(_main.get("login_panel") as Control).hide()
	(_main.get("creation_panel") as Control).hide()
	(_main.get("game_view") as Control).show()
	var map_id := _env("RABBITLANDS_CROWD_BENCH_MAP", _replay_map if not _replay_map.is_empty()
		else "four_gates")
	_report["map"] = map_id
	if map_id != "none":
		_app_state.set("current_map", map_id)
		_main.call("_load_server_map")
		var loader := _main.get("world_loader") as WorldLoader
		var deadline := Time.get_ticks_msec() + MAX_SPAWN_MSEC
		while loader.world_root == null and Time.get_ticks_msec() < deadline:
			await process_frame
		_expect(loader.world_root != null, "benchmark map loads")
	_adapter = _main.get("adapter") as CoordinateAdapter
	var centre_text := OS.get_environment("RABBITLANDS_CROWD_BENCH_CENTRE")
	if centre_text.contains(","):
		var parts := centre_text.split(",")
		_centre = Vector2i(int(parts[0]), int(parts[1]))
	elif _replay_spawn.x >= 0:
		# Where the recorded player last arrived before the start.
		_centre = _replay_spawn
	elif HOT_SPOTS.has(map_id):
		_centre = HOT_SPOTS[map_id]
	else:
		_centre = Vector2i(roundi(_adapter.server_origin.x), roundi(_adapter.server_origin.y))
	_report["centreTile"] = [_centre.x, _centre.y]
	# The minimap is part of what a crowd costs once its marks are drawn
	# (`mapViewportsMilliseconds`); RABBITLANDS_CROWD_BENCH_MINIMAP=1 shows it,
	# =0 hides it, unset leaves the saved HUD setting.
	var minimap := _main.get("minimap_frame") as Control
	var wanted_minimap := OS.get_environment("RABBITLANDS_CROWD_BENCH_MINIMAP").strip_edges()
	if minimap != null and wanted_minimap in ["0", "1"] \
			and minimap.visible != (wanted_minimap == "1"):
		_main.call("_toggle_minimap")
	_report["minimapVisible"] = minimap != null and minimap.visible
	var rig := _main.get("camera_rig") as Node3D
	rig.set("distance", 26.0)
	rig.set("pitch_degrees", -60.0)
	rig.call("_update_camera")
	_report["camera"] = {"distance": 26.0, "pitchDegrees": -60.0,
		"fieldOfView": (_main.get("gameplay_camera") as Camera3D).fov}
	if not _headless:
		RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
		var world_viewport := _main.get("main_viewport") as SubViewport
		if world_viewport != null:
			RenderingServer.viewport_set_measure_render_time(world_viewport.get_viewport_rid(), true)
	# The player stands on the centre tile for the map's own readiness wait, so
	# the streamed ground around the crowd is resident before any cell starts.
	var standing := _record(0, true, _centre, {})
	standing["actor_id"] = _local_id
	_app_state.set("local_actor_id", _local_id)
	_app_state.set("actors", {_local_id: standing})
	_app_state.call("mark_all_actors_changed")
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	_report["worldReadiness"] = await _wait_for_world_readiness("initial map", 1500)


func _prewarm() -> void:
	# One equipped humanoid and one of every creature model the cells use, so a
	# cell's timings never include a model's first glTF parse.
	var records: Dictionary = {FIRST_ACTOR_ID: _record(0, true, _centre, FULL_KIT_A)}
	for index: int in range(_creatures.size()):
		var id := FIRST_ACTOR_ID + 1 + index
		records[id] = _record(id - FIRST_ACTOR_ID, false, _centre + Vector2i(index + 2, 2), {})
	records[FIRST_ACTOR_ID + 40] = _record(40, true, _centre + Vector2i(-2, -2), FULL_KIT_B)
	_app_state.set("actors", records)
	_app_state.call("mark_all_actors_changed")
	await _spawn_and_build(records.size())
	await _settle_frames(10)
	_report["prewarmed"] = {"models": GlbSceneCache.cached_scene_count(),
		"animationLibraries": NativeAnimationImporter.cached_library_count()}
	_app_state.set("actors", {FIRST_ACTOR_ID: _record(0, true, _centre, FULL_KIT_A)})
	_main.call("_sync_world")
	await _settle_frames(20)


func _run_cell(spec: Dictionary) -> void:
	var replay := str(spec["shape"]) == "replay"
	if str(spec.shape) == "herd":
		await _prepare_authored_herd(spec)
		if str(spec.get("status", "")) == "unavailable_content":
			(_report.cells as Array).append(spec)
			return
	var count := int(spec["count"])
	var records: Dictionary = {} if replay else _make_records(count, str(spec["shape"]))
	_app_state.set("actor_mounts", {})
	if str(spec.shape) == "mounted":
		var mounts := Workloads.mount_rows(records, int(spec.mountedCount), str(_app_state.get("current_map")))
		_app_state.set("actor_mounts", mounts)
		spec["mountProfiles"] = Workloads.mount_profile_counts(mounts)
	_app_state.set("selected_actor_id", -1)
	var before := _memory_sample()
	var spawn: Dictionary
	if replay:
		spawn = await _replay_prologue()
		count = (_app_state.get("actors") as Dictionary).size()
		spec["count"] = count
	else:
		_app_state.set("local_actor_id", FIRST_ACTOR_ID)
		_app_state.set("actors", records)
		_app_state.call("mark_all_actors_changed")
		spawn = await _spawn_and_build(count)
	var readiness := await _wait_for_world_readiness(str(spec["id"]), 300)
	var census_before := _census()
	if str(spec.shape) == "mounted":
		_expect(int(census_before.mountedActors) == int(spec.mountedCount),
			"mixed-mounted fixture builds all %d mounted actors" % int(spec.mountedCount))
	var spawned_memory := _memory_sample()
	var active: Array[int] = []
	if not replay:
		active = _active_ids(records, str(spec["activity"]))
	var plan := _plan(active, str(spec["activity"]))
	# Attribution diagnostics, never an acceptance configuration: the benchmark
	# Main subclass freezes every AnimationPlayer, hides the overhead block or
	# skips the ground rays (RABBITLANDS_CROWD_BENCH_DIAG=no_animation,...).
	var diagnostics := OS.get_environment("RABBITLANDS_CROWD_BENCH_DIAG").split(",", false)
	_main.set("benchmark_animation_enabled", not diagnostics.has("no_animation"))
	_main.set("benchmark_overhead_enabled", not diagnostics.has("no_overhead"))
	_main.set("benchmark_ground_enabled", not diagnostics.has("no_ground"))
	_attribution = OS.get_environment("RABBITLANDS_CROWD_BENCH_ATTRIBUTION").strip_edges() == "1"
	if _attribution:
		# Bodies kept from an earlier cell (the player) are timed already.
		var fresh: Dictionary = {}
		var nodes := _main.get("actor_nodes") as Dictionary
		for id: Variant in nodes:
			if is_instance_valid(nodes[id]) and not _attributed.has((nodes[id] as Object).get_instance_id()):
				fresh[id] = nodes[id]
				_attributed[(nodes[id] as Object).get_instance_id()] = true
		_report["attribution%s" % str(spec["id"])] = _main.call("benchmark_attach_attribution", fresh)
	if replay:
		_replay_begin()
	else:
		await _prime(plan)
	await _drive_for(plan, int((_report["measurement"] as Dictionary)["warmupMilliseconds"]), null)
	var raw := {"frameMilliseconds": [], "wallMilliseconds": [], "tickFrameMilliseconds": [],
		"syncWorldMilliseconds": [], "presentMilliseconds": [],
		"groundMilliseconds": [], "overheadMilliseconds": [], "animationGateMilliseconds": [],
		"modelBuildMilliseconds": [], "mapViewportsMilliseconds": [], "rootRenderCpuMilliseconds": [],
		"rootRenderGpuMilliseconds": [], "worldRenderCpuMilliseconds": [],
		"worldRenderGpuMilliseconds": [], "drawCalls": [], "liveEffects": [],
		"packetsPerFrame": [], "packetDispatchMilliseconds": [], "sceneNodes": [], "engineProcessMilliseconds": [], "enginePhysicsMilliseconds": [],
		"processPhaseMilliseconds": [], "flushPhaseMilliseconds": [], "drawPhaseMilliseconds": [],
		"physicsPhaseMilliseconds": [], "mainProcessMilliseconds": [],
		"gateSweepEndMilliseconds": [], "declutterMilliseconds": [],
		"halfRateStepMilliseconds": [], "combatPoseMilliseconds": [], "skeletonUpdates": [],
		"actorRecords": [], "actorNodes": []}
	var sample_started := Time.get_ticks_msec()
	var window_started := _replay_stats.duplicate(true)
	if replay:
		# The sample's own slowest frames and largest apply times.
		_replay_stats["slowest"] = []
		var commands := _replay_stats["commands"] as Dictionary
		for command: int in commands:
			var row: PackedInt64Array = commands[command]
			row[3] = 0
			commands[command] = row
	await _drive_for(plan, int((_report["measurement"] as Dictionary)["sampleMilliseconds"]), raw)
	var elapsed := Time.get_ticks_msec() - sample_started
	var census_after := _census()
	var sampled_runtime := _main.call("benchmark_runtime_snapshot") as Dictionary
	var budget: Dictionary = (_main.get("effect_budget") as RefCounted).call("describe") \
		if _main.get("effect_budget") != null else {}
	var crowd: Dictionary = (_main.get("crowd") as RefCounted).call("describe") \
		if _main.get("crowd") != null else {}
	var remaining: Dictionary = {FIRST_ACTOR_ID: _record(0, true, _centre, FULL_KIT_A)}
	if replay:
		var actors := _app_state.get("actors") as Dictionary
		remaining = {_local_id: actors[_local_id]} if actors.has(_local_id) else {}
	_app_state.set("actors", remaining)
	_main.call("_sync_world")
	await _settle_frames(12)
	var after := _memory_sample()
	var frames := (raw["frameMilliseconds"] as Array).size()
	_expect(frames >= MIN_SAMPLE_FRAMES, "%s samples at least %d frames (got %d)" % [
		spec["id"], MIN_SAMPLE_FRAMES, frames])
	var summary: Dictionary = {}
	for key: String in raw:
		summary[key] = _distribution(raw[key] as Array)
	var frame_summary: Variant = summary["frameMilliseconds"]
	var result := spec.duplicate(true)
	result["frames"] = frames
	result["sampleMilliseconds"] = elapsed
	result["frameTime"] = frame_summary
	# In order, so a pattern across frames (a step every other frame) shows.
	var series: Array = []
	for value: Variant in raw["frameMilliseconds"] as Array:
		series.append(_round(float(value)))
	result["frameSeries"] = series
	result["fpsP5"] = _round(1000.0 / float((frame_summary as Dictionary)["p95"])) \
		if frame_summary is Dictionary and float((frame_summary as Dictionary)["p95"]) > 0.0 else null
	result["fpsMean"] = _round(1000.0 / float((frame_summary as Dictionary)["mean"])) \
		if frame_summary is Dictionary and float((frame_summary as Dictionary)["mean"]) > 0.0 else null
	result["summary"] = summary
	if replay:
		result["replayWindow"] = _replay_window(window_started, elapsed)
	else:
		result["plan"] = {"active": active.size(), "moving": (plan["moving"] as Array).size(),
			"fighting": (plan["fighting"] as Array).size()}
	result["packetsPerSecond"] = _round(_sum(raw["packetsPerFrame"] as Array) * 1000.0 / maxf(1.0, elapsed))
	result["spawn"] = spawn
	result["readiness"] = readiness
	result["census"] = {"afterSpawn": census_before, "afterSample": census_after}
	result["effectBudget"] = budget
	result["crowdPolicy"] = crowd
	result["effectiveRuntime"] = sampled_runtime
	result["memory"] = {"before": before, "withCrowd": spawned_memory, "afterDespawn": after,
		"crowdDelta": _memory_delta(before, spawned_memory),
		"perActorStaticBytes": int((int(spawned_memory.staticBytes) - int(before.staticBytes))
			/ maxi(1, count - 1))}
	(_report["cells"] as Array).append(result)
	print("crowd-presentation %s: %d actors, %d bodies, %d deferred, mean %.2f ms, p95 %.2f ms, p5 %.1f FPS" % [
		spec["id"], count, int(census_before["builtBodies"]), int(census_before["deferred"]),
		float((frame_summary as Dictionary).get("mean", 0.0)) if frame_summary is Dictionary else -1.0,
		float((frame_summary as Dictionary).get("p95", 0.0)) if frame_summary is Dictionary else -1.0,
		float(result["fpsP5"]) if result["fpsP5"] != null else -1.0])


## The crowd's records. The player stands on the centre tile; the others take
## unique tiles inside the shape's half-width, seeded so every run and every
## variant gets the same layout.
func _make_records(count: int, shape: String) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7741 + count
	var records: Dictionary = {}
	var taken: Dictionary = {_centre: true}
	records[FIRST_ACTOR_ID] = _record(0, true, _centre, FULL_KIT_A)
	for index: int in range(1, count):
		var humanoid := false
		var half := 40
		match shape:
			"mounted":
				humanoid = true
				half = 25
			"market":
				humanoid = index % 10 != 0
				half = 40
			"invasion":
				humanoid = index % 7 == 0
				half = 50 if humanoid else 30
			"melee":
				humanoid = index % 2 == 0
				half = 25
			"aoi":
				humanoid = index % 2 == 0
				half = 88
		var tile := _centre
		for attempt: int in range(64):
			tile = _centre + Vector2i(rng.randi_range(-half, half), rng.randi_range(-half, half))
			if not taken.has(tile) and tile.x >= 0 and tile.y >= 0:
				break
		taken[tile] = true
		var kit: Dictionary = {}
		if humanoid:
			kit = FULL_KIT_A if index % 4 < 2 else FULL_KIT_B
		records[FIRST_ACTOR_ID + index] = _record(index, humanoid, tile, kit)
	return records


func _record(index: int, humanoid: bool, tile: Vector2i, kit: Dictionary) -> Dictionary:
	# Kind 1 with actor type 1 is how a player arrives (main.gd `_model_for_actor`).
	var actor_type := 1
	var name := "Crowd player %d" % index
	var kind := 1
	if not humanoid:
		var pick: Dictionary = _creatures[index % _creatures.size()] as Dictionary
		actor_type = int(pick["actorType"])
		name = str(pick["model"])
		kind = 5
	var id := FIRST_ACTOR_ID + index
	return {"actor_id": id, "x": tile.x, "y": tile.y,
		"map": str(_app_state.get("current_map")) if _app_state != null else "",
		"rotation": (index * 977) % 65536, "actor_type": actor_type,
		"kind": kind, "name": name, "health": 5000, "max_health": 5000,
		"alive": true, "appearance": {}, "equipment_visuals": kit.duplicate(),
		"equipment_fallback_parts": []}


## Gives Main the crowd and waits until it is presented: every actor has a node
## and no deferred actor inside the build radius is still waiting for its body.
func _spawn_and_build(count: int) -> Dictionary:
	var started := Time.get_ticks_usec()
	var nodes := _main.get("actor_nodes") as Dictionary
	var deadline := Time.get_ticks_msec() + MAX_SPAWN_MSEC
	var passes := 0
	var all_nodes_msec := -1.0
	while Time.get_ticks_msec() < deadline:
		_main.call("_sync_world", _app_state.call("take_changed_actors"))
		passes += 1
		await process_frame
		nodes = _main.get("actor_nodes") as Dictionary
		if nodes.size() < count:
			continue
		if all_nodes_msec < 0.0:
			all_nodes_msec = _round(float(Time.get_ticks_usec() - started) / 1000.0)
		if _waiting_bodies() == 0:
			break
	var waiting := _waiting_bodies()
	_expect(nodes.size() == count and waiting == 0,
		"crowd of %d is presented before the timeout (%d nodes, %d bodies waiting)" % [
			count, nodes.size(), waiting])
	return {"passes": passes, "allNodesMilliseconds": all_nodes_msec,
		"presentedMilliseconds": _round(float(Time.get_ticks_usec() - started) / 1000.0)}


## Deferred actors inside the build radius: bodies the queue still owes.
func _waiting_bodies() -> int:
	var crowd: Variant = _main.get("crowd")
	if crowd == null or not bool((crowd as RefCounted).get("lazy")):
		return 0
	var radius := float(((crowd as RefCounted).get_script() as Script) \
		.get_script_constant_map().get("BUILD_RADIUS_METRES", 88.0))
	var local := (_main.get("actor_nodes") as Dictionary).get(_local_id) as Node3D
	if local == null:
		return 0
	var waiting := 0
	for value: Variant in (_main.get("actor_nodes") as Dictionary).values():
		var actor := value as ReplicatedActor3D
		if actor == null or not actor.has_method("is_model_deferred") \
				or not bool(actor.call("is_model_deferred")) or bool(actor.call("corpse_faded")):
			continue
		var ground := Vector2(actor.global_position.x - local.global_position.x,
			actor.global_position.z - local.global_position.z).length()
		if ground <= radius and not bool(actor.call("crowd_hidden")):
			waiting += 1
	return waiting


func _active_ids(records: Dictionary, activity: String) -> Array[int]:
	var ids: Array = records.keys()
	ids.sort()
	var active: Array[int] = []
	if activity == "idle":
		return active
	for index: int in range(1, ids.size()):
		# Every third remote actor, so the active third is spread through the
		# crowd rather than packed at one end of it.
		if activity == "all_combat" or index % 3 == 1:
			active.append(int(ids[index]))
	return active


func _plan(active: Array[int], activity: String) -> Dictionary:
	var moving: Array[int] = []
	var fighting: Array[int] = []
	for index: int in range(active.size()):
		if activity == "all_combat" or index % 2 == 1:
			fighting.append(active[index])
		else:
			moving.append(active[index])
	return {"moving": moving, "fighting": fighting}


func _prime(plan: Dictionary) -> void:
	var fighting: Array[int] = plan["fighting"]
	if not fighting.is_empty():
		_send_actor_commands(fighting, 18)
	await process_frame
	await process_frame


## Drives the plan for `duration` ms of real time. With `raw`, records each
## frame. Moves alternate one step east and back every cadence tick; fights
## exchange every fourth tick in four roles - a spell between neighbours, a
## drawn bow, and two melee strikes - and each exchange costs its target a
## little health, so health bars and floating numbers move as they do in play.
## A replay instead delivers every recorded frame that has fallen due, and ends
## early when the recording does.
func _drive_for(plan: Dictionary, duration: int, raw: Variant) -> void:
	var replay := not _replay_times.is_empty()
	var cadence_value: Variant = (_report["measurement"] as Dictionary)["cadenceMilliseconds"]
	var cadence := int(cadence_value) if cadence_value != null else 0
	var started := Time.get_ticks_msec()
	var next_tick := started
	var tick := 0
	var hard_limit := maxi(duration * 4, 60000)
	while Time.get_ticks_msec() - started < duration \
			or (raw != null and (raw["frameMilliseconds"] as Array).size() < MIN_SAMPLE_FRAMES):
		if Time.get_ticks_msec() - started >= hard_limit:
			break
		if replay and _replay_index >= _replay_times.size():
			_replay_stats["exhausted"] = true
			break
		if raw != null:
			_main.call("benchmark_reset_frame")
		_driver_packets = 0
		_driver_usec = 0
		var frame_started := Time.get_ticks_usec()
		var now := Time.get_ticks_msec()
		if replay:
			_replay_due()
		while not replay and now >= next_tick:
			_drive_tick(plan, tick)
			tick += 1
			next_tick += cadence
		var work: float = await _next_drawn_frame()
		await process_frame
		if raw == null:
			continue
		# The packets this loop just fed are handled in the frame drawn next:
		# AppState applies them now, Main presents them in its deferred sync.
		(raw["frameMilliseconds"] as Array).append(work)
		(raw["wallMilliseconds"] as Array).append(float(Time.get_ticks_usec() - frame_started) / 1000.0)
		if _driver_packets > 0:
			(raw["tickFrameMilliseconds"] as Array).append(work)
		var measured: Dictionary = _main.call("benchmark_take_frame") as Dictionary
		var usec: Dictionary = measured.get("microseconds", {}) as Dictionary
		(raw["syncWorldMilliseconds"] as Array).append(float(usec.get("sync_world_inclusive", 0)) / 1000.0)
		(raw["presentMilliseconds"] as Array).append(float(usec.get("present_excluding_ground", 0)) / 1000.0)
		(raw["groundMilliseconds"] as Array).append(float(usec.get("ground", 0)) / 1000.0)
		(raw["overheadMilliseconds"] as Array).append(float(usec.get("overhead", 0)) / 1000.0)
		(raw["animationGateMilliseconds"] as Array).append(float(usec.get("animation_gate", 0)) / 1000.0)
		(raw["modelBuildMilliseconds"] as Array).append(float(usec.get("model_builds", 0)) / 1000.0)
		(raw["mapViewportsMilliseconds"] as Array).append(float(usec.get("map_viewports", 0)) / 1000.0)
		(raw["packetsPerFrame"] as Array).append(_driver_packets)
		(raw["packetDispatchMilliseconds"] as Array).append(float(_driver_usec) / 1000.0)
		(raw["liveEffects"] as Array).append(_live_effects())
		(raw["sceneNodes"] as Array).append(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)))
		# The engine's own split of the last frame: idle processing (scripts, animation,
		# skeletons, deferred calls) and physics steps.
		(raw["engineProcessMilliseconds"] as Array).append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
		(raw["enginePhysicsMilliseconds"] as Array).append(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0)
		(raw["processPhaseMilliseconds"] as Array).append(_last_phases.get("process"))
		(raw["flushPhaseMilliseconds"] as Array).append(_last_phases.get("flush"))
		(raw["drawPhaseMilliseconds"] as Array).append(_last_phases.get("draw"))
		(raw["physicsPhaseMilliseconds"] as Array).append(_last_phases.get("physics"))
		(raw["mainProcessMilliseconds"] as Array).append(float(usec.get("main_process_inclusive", 0)) / 1000.0)
		(raw["gateSweepEndMilliseconds"] as Array).append(float(usec.get("gate_sweep_end", 0)) / 1000.0)
		(raw["declutterMilliseconds"] as Array).append(float(usec.get("declutter", 0)) / 1000.0)
		(raw["halfRateStepMilliseconds"] as Array).append(float(usec.get("half_rate_step", 0)) / 1000.0)
		var calls: Dictionary = measured.get("calls", {}) as Dictionary
		if _attribution:
			(raw["combatPoseMilliseconds"] as Array).append(float(usec.get("combat_pose_from_skeleton", 0)) / 1000.0)
			(raw["skeletonUpdates"] as Array).append(int(calls.get("skeleton_updated", 0)))
		# The crowd this frame: what AppState knows and the nodes Main presents.
		(raw["actorRecords"] as Array).append((_app_state.get("actors") as Dictionary).size())
		(raw["actorNodes"] as Array).append((_main.get("actor_nodes") as Dictionary).size())
		_append_render_sample(raw)


func _on_iteration_started() -> void:
	if _iteration_started_usec < 0:
		_iteration_started_usec = Time.get_ticks_usec()


## The idle step begins: what came before it in the iteration was physics.
func _on_process_started() -> void:
	_on_iteration_started()
	if _process_started_usec < 0:
		_process_started_usec = Time.get_ticks_usec()


func _on_process_ended() -> void:
	if _iteration_started_usec >= 0 and _process_ended_usec < 0:
		_process_ended_usec = Time.get_ticks_usec()


func _on_draw_started() -> void:
	if _iteration_started_usec >= 0 and _draw_started_usec < 0:
		_draw_started_usec = Time.get_ticks_usec()


func _on_iteration_drawn() -> void:
	var now := Time.get_ticks_usec()
	_last_phases = {}
	if _iteration_started_usec >= 0:
		_last_iteration_usec = float(now - _iteration_started_usec)
		# Physics and node processing (Main, the animation players, the
		# half-rate steps); the deferred flush up to the draw (skeleton updates
		# and their listeners, Main's world sync); the draw itself.
		if _process_ended_usec >= _iteration_started_usec:
			var flush_end := _draw_started_usec if _draw_started_usec >= _process_ended_usec else now
			_last_phases = {"process": float(_process_ended_usec - _iteration_started_usec) / 1000.0,
				"physics": float(maxi(0, _process_started_usec - _iteration_started_usec)) / 1000.0,
				"flush": float(flush_end - _process_ended_usec) / 1000.0,
				"draw": float(now - flush_end) / 1000.0 if flush_end != now else null}
	if _route_capture and _last_iteration_usec >= 0.0:
		_route_frame_series.append(_round(_last_iteration_usec / 1000.0))
		if _route_last_frame_usec > 0:
			_route_wall_series.append(_round(float(now - _route_last_frame_usec) / 1000.0))
		_route_last_frame_usec = now
		_route_peak_static_bytes = maxi(_route_peak_static_bytes, OS.get_static_memory_usage())
	_iteration_started_usec = -1
	_process_started_usec = -1
	_process_ended_usec = -1
	_draw_started_usec = -1


## Waits for the end of this frame and returns its work in milliseconds.
func _next_drawn_frame() -> float:
	_last_iteration_usec = -1.0
	if _headless:
		await Signal(_frame_marker, &"processed")
	else:
		await RenderingServer.frame_post_draw
	return _last_iteration_usec / 1000.0


## The driver: `live` (default) paces the crowd as the game does, `stress` as
## the earlier crowd study did, `replay` plays a session recording
## (RABBITLANDS_CROWD_BENCH_DRIVER).
static func _driver_mode() -> String:
	var wanted := OS.get_environment("RABBITLANDS_CROWD_BENCH_DRIVER").strip_edges()
	return wanted if wanted in ["stress", "replay"] else "live"


static func _driver_description() -> String:
	match _driver_mode():
		"replay":
			return ("replay: one connection of a server session recording (RLREC1). Everything "
				+ "recorded before the start offset is applied in 1-s steps of recorded time, "
				+ "without the login answers or that time's effects, animations, numbers and "
				+ "sounds; from the start every outbound frame reaches AppState in the first "
				+ "frame after its recorded time")
		"stress":
			return ("stress: every mover steps every 100 ms and every fighter acts every 400 ms, "
				+ "all on the same tick (the earlier crowd study's driver)")
	return ("live: 50 ms server ticks; each mover steps every 600 ms (a walk) and each fighter "
		+ "acts every 2 s (a combat round), staggered across the crowd")


## Reads a session recording (the server's eloria/session_recorder.py): the
## outbound frames, the player it was (YOU_ARE), and the map and tile it stood
## on at the start offset. Inbound frames are what that player sent; a replay
## has no use for them.
func _load_replay(path: String) -> Dictionary:
	var out := {"ok": false, "file": path.get_file()}
	if not _expect(not path.is_empty() and FileAccess.file_exists(path),
			"replay recording exists (RABBITLANDS_CROWD_BENCH_REPLAY=%s)" % path):
		return out
	_replay_bytes = FileAccess.get_file_as_bytes(path)
	var magic := REPLAY_MAGIC.to_ascii_buffer()
	var header_end := _replay_bytes.find(10, magic.size())
	if not _expect(_replay_bytes.slice(0, magic.size()) == magic and header_end > 0,
			"replay file is an RLREC1 session recording"):
		return out
	var header: Variant = JSON.parse_string(
		_replay_bytes.slice(magic.size(), header_end).get_string_from_utf8())
	var start_msec := _env_int("RABBITLANDS_CROWD_BENCH_REPLAY_START_MSEC", REPLAY_DEFAULT_START_MSEC, 0)
	var you_are := -1
	var maps: Array = []
	var inbound := 0
	var truncated := false
	var offset := header_end + 1
	while offset + REPLAY_RECORD_HEADER <= _replay_bytes.size():
		var kind := _replay_bytes[offset]
		var nsec := _replay_bytes.decode_u64(offset + 1)
		var length := _replay_bytes.decode_u32(offset + 9)
		var at := offset + REPLAY_RECORD_HEADER
		offset = at + length
		if offset > _replay_bytes.size() or kind == "T".unicode_at(0):
			truncated = true
			break
		if kind == "I".unicode_at(0):
			inbound += 1
		if (kind != "O".unicode_at(0) and kind != "o".unicode_at(0)) or length < 3:
			continue
		_replay_offsets.append(at)
		_replay_sizes.append(length)
		_replay_times.append(nsec)
		var command := _replay_bytes[at]
		if command == EloriaProtocol.ServerMessage.YOU_ARE and you_are < 0 and length >= 5:
			you_are = _replay_bytes.decode_u16(at + 3)
			_replay_you_are_ns = nsec
			_replay_origin_ns = nsec + start_msec * 1000000
		elif command == EloriaProtocol.ServerMessage.CHANGE_MAP:
			var event := EloriaProtocol.decode_server(command, _replay_bytes.slice(at + 3, at + length))
			maps.append([nsec, str(event.get("map_name", ""))])
		elif you_are >= 0 and nsec <= _replay_origin_ns and length >= 9 and command in [
				EloriaProtocol.ServerMessage.ADD_NEW_ACTOR, EloriaProtocol.ServerMessage.ADD_NEW_ENHANCED_ACTOR,
				EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED] \
				and _replay_bytes.decode_u16(at + 3) == you_are:
			_replay_spawn = Vector2i(_replay_bytes.decode_u16(at + 5) & 0x7ff,
				_replay_bytes.decode_u16(at + 7) & 0x7ff)
	if not _expect(you_are >= 0, "replay recording holds a YOU_ARE") \
			or not _expect(_replay_origin_ns < _replay_times[-1],
				"replay start (%d ms after YOU_ARE) is inside the recording" % start_msec):
		_replay_times.clear()
		return out
	_local_id = you_are
	var changes: Array = []
	for entry: Array in maps:
		if int(entry[0]) <= _replay_origin_ns:
			_replay_map = str(entry[1])
		changes.append([_round(float(int(entry[0]) - _replay_you_are_ns) / 1e6), entry[1]])
	_expect(not _replay_map.is_empty(), "replay recording names a map before its start")
	out.merge({"ok": not _replay_map.is_empty(),
		"header": {"version": (header as Dictionary).get("version") if header is Dictionary else null,
			"tls": (header as Dictionary).get("tls") if header is Dictionary else null,
			"gateway": (header as Dictionary).get("gateway") if header is Dictionary else null},
		"outboundFrames": _replay_times.size(), "inboundFrames": inbound, "truncated": truncated,
		"recordedSeconds": _round(float(_replay_times[-1] - _replay_times[0]) / 1e9),
		"youAreMilliseconds": _round(float(_replay_you_are_ns - _replay_times[0]) / 1e6),
		"startMilliseconds": start_msec, "localActorId": you_are, "map": _replay_map,
		"spawnTile": [_replay_spawn.x, _replay_spawn.y],
		"mapChangesMillisecondsAfterYouAre": changes,
		"secondsAfterStart": _round(float(_replay_times[-1] - _replay_origin_ns) / 1e9)}, true)
	return out


## Applies everything recorded before the start offset, a second of recorded
## time per frame, then waits until Main presents the crowd: every actor has a
## node, nothing in build range waits for its body, and that holds for ten
## frames. The recording's clock stands still meanwhile.
func _replay_prologue() -> Dictionary:
	var started := Time.get_ticks_usec()
	_app_state.set("actors", {})
	_main.call("_sync_world")
	var applied := 0
	var skipped := 0
	var frames := 0
	var cursor := _replay_times[0]
	while _replay_index < _replay_times.size() and _replay_times[_replay_index] < _replay_origin_ns:
		cursor = mini(cursor + REPLAY_PROLOGUE_STEP_NSEC, _replay_origin_ns)
		while _replay_index < _replay_times.size() and _replay_times[_replay_index] < cursor:
			var at := _replay_offsets[_replay_index]
			var command := _replay_bytes[at]
			if command in REPLAY_LOGIN_FRAMES or command in REPLAY_TRANSIENT_FRAMES:
				skipped += 1
			else:
				_app_state.call("_on_packet", command,
					_replay_bytes.slice(at + 3, at + _replay_sizes[_replay_index]))
				applied += 1
			_replay_index += 1
		_main.call("_sync_world", _app_state.call("take_changed_actors"))
		frames += 1
		await process_frame
	var applied_msec := _round(float(Time.get_ticks_usec() - started) / 1000.0)
	var deadline := Time.get_ticks_msec() + MAX_SPAWN_MSEC
	var steady := 0
	var nodes := -1
	while Time.get_ticks_msec() < deadline and steady < 10:
		_main.call("_sync_world", _app_state.call("take_changed_actors"))
		await process_frame
		var now_nodes := (_main.get("actor_nodes") as Dictionary).size()
		steady = steady + 1 if now_nodes == nodes and _waiting_bodies() == 0 else 0
		nodes = now_nodes
	var actors := _app_state.get("actors") as Dictionary
	_expect(int(_app_state.get("local_actor_id")) == _local_id and actors.has(_local_id),
		"the recorded player (%d) stands in its own view after the prologue" % _local_id)
	_expect(steady >= 10, "the replayed crowd is presented before the timeout (%d nodes, %d bodies waiting)"
		% [nodes, _waiting_bodies()])
	return {"prologueFramesApplied": applied, "prologueFramesSkipped": skipped,
		"prologueEngineFrames": frames, "prologueMilliseconds": applied_msec,
		"presentedMilliseconds": _round(float(Time.get_ticks_usec() - started) / 1000.0),
		"actorRecords": actors.size(), "actorNodes": nodes}


## Starts the recording's clock: from here a frame recorded `t` after the start
## offset is due `t` after this call.
func _replay_begin() -> void:
	_replay_started_usec = Time.get_ticks_usec()
	_replay_stats = {"delivered": 0, "spawns": 0, "removals": 0, "clears": 0, "mapChanges": 0,
		"recordedNs": _replay_origin_ns, "exhausted": false, "commands": {}, "slowest": []}


## Delivers every frame whose recorded time has passed, as one socket read
## would after a long frame: a burst, in order.
func _replay_due() -> void:
	var due := _replay_origin_ns + (Time.get_ticks_usec() - _replay_started_usec) * 1000
	_replay_stats["recordedNs"] = due
	while _replay_index < _replay_times.size() and _replay_times[_replay_index] <= due:
		var at := _replay_offsets[_replay_index]
		var size := _replay_sizes[_replay_index]
		var command := _replay_bytes[at]
		_replay_index += 1
		if command in REPLAY_LOGIN_FRAMES:
			continue
		if command in [EloriaProtocol.ServerMessage.ADD_NEW_ACTOR,
				EloriaProtocol.ServerMessage.ADD_NEW_ENHANCED_ACTOR,
				EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED]:
			_replay_stats["spawns"] += 1
		elif command == EloriaProtocol.ServerMessage.REMOVE_ACTOR:
			_replay_stats["removals"] += (size - 3) / 2
		elif command == EloriaProtocol.ServerMessage.KILL_ALL_ACTORS:
			_replay_stats["clears"] += 1
		elif command == EloriaProtocol.ServerMessage.CHANGE_MAP:
			_replay_stats["mapChanges"] += 1
		_replay_stats["delivered"] += 1
		var started := Time.get_ticks_usec()
		_send_packet(command, _replay_bytes.slice(at + 3, at + size))
		# What each kind of frame costs to apply: AppState's reducer and every
		# handler its signals reach synchronously (Main's included).
		var spent := Time.get_ticks_usec() - started
		var commands := _replay_stats["commands"] as Dictionary
		var row: PackedInt64Array = commands.get(command, PackedInt64Array([0, 0, 0, 0]))
		row[0] += 1
		row[1] += size
		row[2] += spent
		row[3] = maxi(row[3], spent)
		commands[command] = row
		var slowest := _replay_stats["slowest"] as Array
		if slowest.size() < 5 or spent > int((slowest[-1] as Array)[1]):
			slowest.append([command, spent, _replay_times[_replay_index - 1], size])
			slowest.sort_custom(func(a: Array, b: Array) -> bool: return int(a[1]) > int(b[1]))
			slowest.resize(mini(slowest.size(), 5))


static func _command_name(command: int) -> String:
	var name: Variant = EloriaProtocol.ServerMessage.find_key(command)
	return str(name) if name != null else str(command)


## What the recording did during the sample that began at `started`.
func _replay_window(started: Dictionary, elapsed_msec: int) -> Dictionary:
	var out := {}
	for key: String in ["delivered", "spawns", "removals", "clears", "mapChanges"]:
		out[key] = int(_replay_stats.get(key, 0)) - int(started.get(key, 0))
	out["fromMillisecondsAfterYouAre"] = _round(
		float(int(started.get("recordedNs", 0)) - _replay_you_are_ns) / 1e6)
	out["toMillisecondsAfterYouAre"] = _round(
		float(int(_replay_stats.get("recordedNs", 0)) - _replay_you_are_ns) / 1e6)
	out["exhausted"] = bool(_replay_stats.get("exhausted", false))
	out["framesPerSecond"] = _round(float(out["delivered"]) * 1000.0 / maxf(1.0, elapsed_msec))
	# Per kind of frame during the sample, costliest first: frames, bytes,
	# total and largest apply time.
	var before := started.get("commands", {}) as Dictionary
	var rows: Array = []
	for command: int in _replay_stats.get("commands", {}) as Dictionary:
		var now: PackedInt64Array = (_replay_stats["commands"] as Dictionary)[command]
		var then: PackedInt64Array = before.get(command, PackedInt64Array([0, 0, 0, 0]))
		if now[0] > then[0]:
			rows.append({"command": _command_name(command), "frames": now[0] - then[0],
				"bytes": now[1] - then[1], "applyMilliseconds": _round(float(now[2] - then[2]) / 1000.0),
				"largestApplyMilliseconds": _round(float(now[3]) / 1000.0)})
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return float(a["applyMilliseconds"]) > float(b["applyMilliseconds"]))
	out["byCommand"] = rows
	var slowest: Array = []
	for entry: Array in _replay_stats.get("slowest", []) as Array:
		if int(entry[2]) >= int(started.get("recordedNs", 0)):
			slowest.append({"command": _command_name(int(entry[0])),
				"applyMilliseconds": _round(float(entry[1]) / 1000.0),
				"recordedMillisecondsAfterYouAre": _round(float(int(entry[2]) - _replay_you_are_ns) / 1e6),
				"bytes": entry[3]})
	out["slowestFrames"] = slowest
	_expect(int(out["mapChanges"]) == 0, "the replayed player stays on one map during the sample")
	_expect(not bool(out["exhausted"]), "the recording outlasts the sample")
	return out


func _drive_tick(plan: Dictionary, tick: int) -> void:
	var cadence := int((_report["measurement"] as Dictionary)["cadenceMilliseconds"])
	if _server_time:
		var stamp := PackedByteArray()
		stamp.resize(4)
		stamp.encode_u32(0, tick * cadence)
		_send_packet(EloriaProtocol.ServerMessage.ELORIA_SERVER_TIME, stamp)
	if _presence_dots > 0 and tick % maxi(1, 1000 / cadence) == 0:
		_send_packet(EloriaProtocol.ServerMessage.ELORIA_PRESENCE,
			_presence_payload(float(tick * cadence) / 1000.0))
	var moving: Array[int] = plan["moving"]
	var fighting: Array[int] = plan["fighting"]
	var live := _driver_mode() == "live"
	if live:
		# One frame of what the server sends each 50 ms tick: the movers whose
		# 600 ms step falls due, in one command packet, and the fighters whose
		# 2 s round falls due. Each actor's phase is its place in the crowd.
		var east: Array[int] = []
		var west: Array[int] = []
		for index: int in range(moving.size()):
			if (tick + index) % 12 == 0:
				(east if ((tick + index) / 12) % 2 == 0 else west).append(moving[index])
		_send_actor_commands(east, 22)
		_send_actor_commands(west, 26)
		var due: Array[int] = []
		for index: int in range(fighting.size()):
			if (tick + index * 7) % 40 == 0:
				due.append(index)
		_drive_combat(fighting, due, tick)
		return
	if not moving.is_empty():
		_send_actor_commands(moving, 22 if tick % 2 == 0 else 26)
	if fighting.is_empty() or tick % 4 != 0:
		return
	var everyone: Array[int] = []
	for index: int in range(fighting.size()):
		everyone.append(index)
	_drive_combat(fighting, everyone, tick)


## One ELORIA_PRESENCE snapshot: `_presence_dots` players on rings 82-139
## tiles from the player, each walking a tile a second around it, with a few
## near actors held back by a cap of 160 ("+12 nearby").
func _presence_payload(seconds: float) -> PackedByteArray:
	var payload := PackedByteArray([1, 1, 80, 88])
	for value: int in [160, 7, 5, _presence_dots]:
		_append_u16(payload, value)
	for index: int in range(_presence_dots):
		var radius: float = 82.0 + float((index * 37) % 58)
		var angle: float = TAU * float(index) / float(_presence_dots) + seconds / radius
		_append_u16(payload, 40000 + index)
		_append_u16(payload, clampi(_centre.x + roundi(cos(angle) * radius), 0, 2047))
		_append_u16(payload, clampi(_centre.y + roundi(sin(angle) * radius), 0, 2047))
		payload.append(0)
	return payload


## The fighters at `due` (indexes into `fighting`) act on their neighbour.
func _drive_combat(fighting: Array[int], due: Array[int], tick: int) -> void:
	var melee: Array[int] = []
	for index: int in due:
		var id := fighting[index]
		var other := fighting[(index + 1) % fighting.size()]
		match index % 4:
			0:
				var payload := PackedByteArray([tick % 6])
				_append_u16(payload, id)
				_append_u16(payload, other)
				payload.append(10)
				_send_packet(EloriaProtocol.ServerMessage.SEND_SPECIAL_EFFECT, payload)
			1:
				var payload := PackedByteArray()
				_append_u16(payload, id)
				payload.append_array("ranged_draw".to_utf8_buffer())
				payload.append(0)
				_send_packet(EloriaProtocol.ServerMessage.ADD_ACTOR_ANIMATION, payload)
			_:
				melee.append(id)
		var health := PackedByteArray()
		_append_u16(health, other)
		_append_u16(health, 3)
		_send_packet(EloriaProtocol.ServerMessage.GET_ACTOR_DAMAGE if (tick / 4) % 8 != 7
			else EloriaProtocol.ServerMessage.GET_ACTOR_HEAL, health)
	_send_actor_commands(melee, 46)


func _send_actor_commands(ids: Array, command: int) -> void:
	if ids.is_empty():
		return
	var payload := PackedByteArray()
	for id: int in ids:
		_append_u16(payload, id)
		payload.append(command & 0xff)
	_send_packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, payload)


func _send_packet(command: int, payload: PackedByteArray) -> void:
	var started := Time.get_ticks_usec()
	_app_state.call("_on_packet", command, payload)
	_driver_usec += Time.get_ticks_usec() - started
	_driver_packets += 1


func _append_u16(payload: PackedByteArray, value: int) -> void:
	payload.append(value & 0xff)
	payload.append((value >> 8) & 0xff)


func _append_render_sample(raw: Dictionary) -> void:
	if _headless:
		return
	var world_viewport := _main.get("main_viewport") as SubViewport
	(raw["rootRenderCpuMilliseconds"] as Array).append(
		RenderingServer.viewport_get_measured_render_time_cpu(root.get_viewport_rid()))
	(raw["rootRenderGpuMilliseconds"] as Array).append(
		RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid()))
	if world_viewport != null:
		var rid := world_viewport.get_viewport_rid()
		(raw["worldRenderCpuMilliseconds"] as Array).append(
			RenderingServer.viewport_get_measured_render_time_cpu(rid))
		(raw["worldRenderGpuMilliseconds"] as Array).append(
			RenderingServer.viewport_get_measured_render_time_gpu(rid))
		(raw["drawCalls"] as Array).append(RenderingServer.viewport_get_render_info(rid,
			RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,
			RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))


## What the crowd looks like to the presentation right now.
func _census() -> Dictionary:
	var camera := _main.get("gameplay_camera") as Camera3D
	var nodes := _main.get("actor_nodes") as Dictionary
	var local := nodes.get(_local_id) as Node3D
	var out := {"nodes": nodes.size(), "builtBodies": 0, "deferred": 0, "standIns": 0,
		"drawn": 0, "inFrustumAndDrawn": 0, "tierFull": 0, "tierHalf": 0, "tierPaused": 0,
		"skeletons": 0, "skeletonsProcessing": 0, "beyondDrawDistance": 0, "crowdHidden": 0,
		"capeClothActive": 0, "capeSolversActive": 0, "mountedActors": 0,
		"mountSkeletons": 0, "mountedVisualsProcessing": 0,
		"mountedWornCapes": 0, "ambientAnimals": 0}
	var planes: Array[Plane] = camera.get_frustum() if camera != null else []
	# The quarter tier by name, so the census also runs against a client
	# without it.
	var quarter: int = int(TIERS.get("QUARTER", -1))
	for value: Variant in nodes.values():
		var actor := value as ReplicatedActor3D
		if actor == null:
			continue
		if is_instance_valid(actor._mount_visual):
			out["mountedActors"] += 1
			out["mountSkeletons"] += actor._mount_visual.find_children("*", "Skeleton3D", true, false).size()
			out["mountedVisualsProcessing"] += int(actor._mount_visual.is_processing())
			# Mounted cloth is called manually even though its automatic modifier
			# is inactive. Keep this separate from capeSolversActive, not a claim
			# that automatic-modifier counts include those manual calls.
			out["mountedWornCapes"] += int(actor.wears_cape_cloth())
		var deferred: bool = actor.has_method("is_model_deferred") \
			and bool(actor.call("is_model_deferred"))
		out[("deferred" if deferred else "builtBodies")] += 1
		if actor.has_method("stand_in_visible") and bool(actor.call("stand_in_visible")):
			out["standIns"] += 1
		if actor.has_method("crowd_hidden") and bool(actor.call("crowd_hidden")):
			out["crowdHidden"] += 1
		if actor.is_drawn():
			out["drawn"] += 1
			var inside := true
			for plane: Plane in planes:
				if plane.distance_to(actor.global_position + Vector3.UP) > actor.view_radius():
					inside = false
					break
			out["inFrustumAndDrawn"] += int(inside)
		if local != null and local.global_position.distance_to(actor.global_position) > 80.0:
			out["beyondDrawDistance"] += 1
		var tier := actor.animation_tier()
		if tier == AnimationGate.Tier.FULL:
			out["tierFull"] += 1
		elif tier == AnimationGate.Tier.HALF:
			out["tierHalf"] += 1
		elif tier == quarter:
			out["tierQuarter"] = int(out.get("tierQuarter", 0)) + 1
		else:
			out["tierPaused"] += 1
		if actor.has_method("cape_cloth_active") and bool(actor.call("cape_cloth_active")):
			out["capeClothActive"] += 1
			var why := "tier%d-allowed%s-local%s" % [actor.animation_tier(),
				str(actor.call("cape_cloth_allowed")), str(actor.actor_id == _local_id)]
			out[why] = int(out.get(why, 0)) + 1
		var skeleton := actor.get_skeleton()
		if skeleton != null:
			out["skeletons"] += 1
			for modifier: Node in skeleton.get_children():
				if modifier.name == &"CapeCloth" and (modifier as SkeletonModifier3D).active:
					out["capeSolversActive"] += 1
			# A paused body's model subtree is disabled (feature clients only).
			if not actor.has_method("model_processing") or bool(actor.call("model_processing")):
				out["skeletonsProcessing"] += 1
	var gate := _main.get("animation_gate") as AnimationGate
	if gate != null and gate.has_method("group_sizes"):
		out["halfGroups"] = gate.call("group_sizes", AnimationGate.Tier.HALF)
		out["quarterGroups"] = gate.call("group_sizes", quarter)
	# What the protocol v2 inputs left behind: presence dots, "+N nearby", and
	# rows carrying a server-time step stamp.
	var presence: Variant = _app_state.get("presence")
	if presence is RefCounted:
		out["presenceDots"] = int((presence as RefCounted).call("dot_count"))
		out["nearbyHidden"] = int((presence as RefCounted).get("nearby_hidden"))
	var stamped := 0
	for record: Variant in (_app_state.get("actors") as Dictionary).values():
		if record is Dictionary and (record as Dictionary).has("step_local_msec"):
			stamped += 1
	out["stampedRows"] = stamped
	var ambient := _main.get("ambient_population") as AmbientPopulation
	if is_instance_valid(ambient):
		out["ambientAnimals"] = (ambient.get("_spawned") as Array).size()
	return out


func _live_effects() -> int:
	var count := 0
	for value: Variant in _main.get("world_effects") as Array:
		count += int(is_instance_valid(value) and not (value as Node).is_queued_for_deletion())
	return count


func _wait_for_world_readiness(label: String, minimum_msec: int) -> Dictionary:
	if str(_report.get("map", "")) == "none" and str(_app_state.get("current_map")) in ["", "none"]:
		await _settle_frames(4)
		return {"label": label, "ready": true, "reason": "no map"}
	var started := Time.get_ticks_msec()
	var deadline := started + MAX_READINESS_MSEC
	var stable := 0
	var previous := ""
	var last_state: Dictionary = {}
	while Time.get_ticks_msec() < deadline:
		await physics_frame
		await process_frame
		var loader := _main.get("world_loader") as WorldLoader
		var chunk := loader.world_root as ContinentChunkStream if loader != null else null
		last_state = _main.call("benchmark_readiness_snapshot") as Dictionary
		var idle := _streaming_idle(loader, chunk) and bool(last_state.get("ready", false))
		var signature := "%d|%d|%d" % [GlbSceneCache.cached_scene_count(),
			int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT)),
			chunk.cells.size() if chunk != null else -1]
		stable = stable + 1 if signature == previous and idle else 0
		previous = signature
		if Time.get_ticks_msec() - started >= minimum_msec and stable >= 12:
			break
	var ready := stable >= 12
	_expect(ready, "%s reaches stable resources with no map work pending" % label)
	return {"label": label, "ready": ready, "waitMilliseconds": Time.get_ticks_msec() - started,
		"stableFrames": stable, "state": last_state}


func _streaming_idle(loader: WorldLoader, chunk: ContinentChunkStream) -> bool:
	if loader == null or loader.world_root == null:
		return false
	if int(loader.get("_cache_write_countdown")) > 0:
		return false
	if chunk != null:
		if chunk.get("_thread") != null or not (chunk.get("_retiring") as Array).is_empty():
			return false
		if ContinentChunkStream.orphans_pending() > 0:
			return false
	var exterior := _main.get("exterior_stream") as ExteriorRegionStream
	return exterior == null or exterior.is_idle()


func _record_effective_runtime() -> void:
	var runtime := _main.call("benchmark_runtime_snapshot") as Dictionary
	_report["effectiveSettings"] = runtime.get("effectiveSettings", {})
	_report["activeBackends"] = runtime.get("activeBackends", {})
	_report["viewport"] = [root.size.x, root.size.y]


func _prepare_authored_herd(spec: Dictionary) -> void:
	var map_id := _env("RABBITLANDS_CROWD_BENCH_HERD_MAP", "sunmane_steppe")
	var entry := MapRegistry.resolve(_main.get("map_registry") as Dictionary, map_id)
	var groups: Array = []
	if not entry.is_empty():
		var manifest := WorldManifest.load_file(ProjectSettings.globalize_path(str(entry.get("manifest", ""))))
		groups = manifest.data.get("ambientPopulation", {}).get("groups", []) as Array
	var declared := 0
	for group: Dictionary in groups:
		declared += maxi(0, int(group.get("count", 0)))
	spec["map"] = map_id
	spec["declaredAmbientAnimals"] = declared
	if declared == 0:
		spec.merge({"status": "unavailable_content", "qualification": "pending",
			"reason": "Published map has no authored ambient herd; no animals were invented or restored.",
			"frames": 0, "sampleMilliseconds": 0, "readiness": {"ready": false},
			"fixtureSource": "current published ambientPopulation.groups"})
		return
	await _route_place(map_id, Vector2i(137, 95), true)
	_adapter = _main.get("adapter") as CoordinateAdapter
	var center: Array = (groups[0] as Dictionary).get("center", [0, 0, 0])
	var point := Vector3(float(center[0]), float(center[1]), float(center[2]))
	var loader := _main.get("world_loader") as WorldLoader
	if is_instance_valid(loader.world_root):
		point = loader.world_root.global_transform * point
	_centre = _adapter.godot_to_server(point)
	await _route_place(map_id, _centre, false)
	var ambient := _main.get("ambient_population") as AmbientPopulation
	var actual := (ambient.get("_spawned") as Array).size() if is_instance_valid(ambient) else 0
	spec["spawnedAmbientAnimals"] = actual
	_expect(actual > 0, "authored-herd has real published animals before sampling")


## A client-only route, using the real Main/AppState loader and packet handlers.
## It intentionally does not claim server navigation or cold OS/storage caches.
func _run_traversal_cell(spec: Dictionary) -> void:
	var primer: Array[Dictionary] = []
	if str(spec.visit) == "warm" and not _route_primed:
		primer = await _traverse_southern_route()
		_route_primed = primer.size() == Workloads.southern_route().size() and primer.all(
			func(leg: Dictionary) -> bool: return bool(leg.get("success", false)))
	_route_frame_series.clear()
	_route_wall_series.clear()
	_route_last_frame_usec = Time.get_ticks_usec()
	_route_peak_static_bytes = OS.get_static_memory_usage()
	var before := _memory_sample()
	var started := Time.get_ticks_msec()
	_route_capture = true
	var legs: Array[Dictionary] = await _traverse_southern_route()
	var wanted_duration := int((_report.measurement as Dictionary).sampleMilliseconds)
	while Time.get_ticks_msec() - started < wanted_duration or _route_frame_series.size() < MIN_SAMPLE_FRAMES:
		await _next_drawn_frame()
	_route_capture = false
	var elapsed := Time.get_ticks_msec() - started
	var success := legs.size() == Workloads.southern_route().size() and legs.all(
		func(leg: Dictionary) -> bool: return bool(leg.get("success", false)))
	_route_primed = success
	var readiness := await _wait_for_world_readiness(str(spec.id) + " final", 300)
	var census := _census()
	var result := spec.duplicate(true)
	result.merge({"status": "complete" if success else "failed", "frames": _route_frame_series.size(),
		"sampleMilliseconds": elapsed, "frameSeries": _route_frame_series.duplicate(),
		"frameTime": _distribution(_route_frame_series), "wallFrameSeries": _route_wall_series.duplicate(),
		"wallFrameTime": _distribution(_route_wall_series), "readiness": readiness,
		"plan": {"active": 1, "moving": 1, "fighting": 0},
		"census": {"afterSpawn": census.duplicate(true), "afterSample": census},
		"route": {"kind": "synthetic_client_streaming", "legs": legs,
			"sources": ["southern-streaming-walk.json", "southern-region-routes.json"],
			"serverNavigationCertified": false, "unmeasuredPrimer": primer,
			"cacheCondition": ("repeat in this process" if str(spec.visit) == "warm" else "first route pass in this process")
				+ "; OS caches uncontrolled; preceding crowd cells can share assets"},
		"memory": {"before": before, "after": _memory_sample(), "peakStaticBytes": _route_peak_static_bytes},
		"effectiveRuntime": _main.call("benchmark_runtime_snapshot")})
	(_report.cells as Array).append(result)
	_expect(success, "%s completes every deterministic route leg" % str(spec.id))


func _traverse_southern_route() -> Array[Dictionary]:
	var results: Array[Dictionary] = []
	_app_state.set("actor_mounts", {})
	_app_state.set("selected_actor_id", -1)
	for leg: Dictionary in Workloads.southern_route():
		var start_readiness: Dictionary = await _route_place(str(leg.map), Workloads.tile(leg.start), true)
		if not bool(start_readiness.get("ready", false)):
			results.append({"id": leg.id, "success": false, "startReadiness": start_readiness})
			break
		await _route_walk_to(Workloads.tile(leg.approach))
		var actor := (_main.get("actor_nodes") as Dictionary).get(FIRST_ACTOR_ID) as Node3D
		var old_identity := actor.get_instance_id() if is_instance_valid(actor) else -1
		var began := Time.get_ticks_msec()
		var frames_before := _route_frame_series.size()
		var arrival: Dictionary = await _route_place(str(leg.destination), Workloads.tile(leg.arrival),
			str(leg.kind) != "border")
		var arrived_actor := (_main.get("actor_nodes") as Dictionary).get(FIRST_ACTOR_ID) as Node3D
		var handoff := (_main.get("exterior_stream") as ExteriorRegionStream).last_handoff
		var success := bool(arrival.get("ready", false)) \
			and str(_app_state.get("current_map")) == str(leg.destination) and is_instance_valid(arrived_actor)
		results.append({"id": leg.id, "kind": leg.kind, "from": leg.map, "to": leg.destination,
			"success": success, "milliseconds": Time.get_ticks_msec() - began,
			"sampledFrames": _route_frame_series.size() - frames_before, "readiness": arrival,
			"travellerRetained": is_instance_valid(arrived_actor) and arrived_actor.get_instance_id() == old_identity,
			"continuousHandoff": str(handoff.get("from", "")) == str(leg.map) \
				and str(handoff.get("to", "")) == str(leg.destination) and bool(handoff.get("continuous", false))})
		if not success:
			break
	return results


func _route_place(map_id: String, tile: Vector2i, clear_roster: bool) -> Dictionary:
	_local_id = FIRST_ACTOR_ID
	_app_state.set("local_actor_id", FIRST_ACTOR_ID)
	if map_id != str(_app_state.get("current_map")):
		if clear_roster:
			_send_packet(EloriaProtocol.ServerMessage.KILL_ALL_ACTORS, PackedByteArray())
		_send_packet(EloriaProtocol.ServerMessage.CHANGE_MAP, map_id.to_utf8_buffer() + PackedByteArray([0]))
	_centre = tile
	var record := _record(0, true, tile, FULL_KIT_A)
	_app_state.set("actors", {FIRST_ACTOR_ID: record})
	_app_state.call("mark_all_actors_changed")
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	await _spawn_and_build(1)
	_adapter = _main.get("adapter") as CoordinateAdapter
	return await _wait_for_world_readiness("route " + map_id, 300)


func _route_walk_to(destination: Vector2i) -> void:
	var deadline := Time.get_ticks_msec() + 30000
	var next_step := 0
	while Time.get_ticks_msec() < deadline:
		var dto := (_app_state.get("actors") as Dictionary).get(FIRST_ACTOR_ID, {}) as Dictionary
		if dto.is_empty():
			_expect(false, "route retains its synthetic local actor")
			return
		var tile := Vector2i(int(dto.x), int(dto.y))
		if tile == destination:
			return
		if Time.get_ticks_msec() >= next_step:
			var step := Vector2i(signi(destination.x - tile.x), signi(destination.y - tile.y))
			for command: int in range(20, 28):
				if EloriaProtocol.actor_command_step(command) == step:
					_send_actor_commands([FIRST_ACTOR_ID], command)
					break
			next_step = Time.get_ticks_msec() + 600
		await _next_drawn_frame()
	_expect(false, "route movement reaches its authored approach")


func _tear_down_main() -> void:
	if _main == null:
		return
	_app_state.set("actors", {})
	_main.call("_sync_world")
	var loader := _main.get("world_loader") as WorldLoader
	var chunk: ContinentChunkStream = loader.world_root as ContinentChunkStream if loader != null else null
	if chunk != null:
		chunk.pause_streaming()
	var exterior := _main.get("exterior_stream") as ExteriorRegionStream
	if exterior != null:
		exterior.clear()
	var deadline := Time.get_ticks_msec() + MAX_READINESS_MSEC
	while Time.get_ticks_msec() < deadline:
		var idle := (chunk == null or (chunk.get("_thread") == null
			and (chunk.get("_retiring") as Array).is_empty()
			and ContinentChunkStream.orphans_pending() == 0)) \
			and (exterior == null or exterior.is_idle())
		if idle:
			break
		await process_frame
	_main.call("_clear_world_presentation")
	await _settle_frames(2)
	_main.queue_free()
	await _settle_frames(4)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()


func _memory_sample() -> Dictionary:
	return {
		"staticBytes": OS.get_static_memory_usage(),
		"objects": int(Performance.get_monitor(Performance.OBJECT_COUNT)),
		"cachedModels": GlbSceneCache.cached_scene_count(),
		"nodes": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
		"videoBytes": null if _headless else int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)),
		"textureBytes": null if _headless else int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED)),
		"bufferBytes": null if _headless else int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_BUFFER_MEM_USED)),
	}


func _memory_delta(before: Dictionary, after: Dictionary) -> Dictionary:
	var out: Dictionary = {}
	for key: Variant in after:
		out[key] = null if after[key] == null or before.get(key) == null \
			else int(after[key]) - int(before[key])
	return out


func _distribution(values: Array) -> Variant:
	var numbers: Array[float] = []
	for value: Variant in values:
		if value != null:
			numbers.append(float(value))
	if numbers.is_empty():
		return null
	numbers.sort()
	return {"count": numbers.size(), "mean": _round(_sum(numbers) / numbers.size()),
		"p5": _round(_percentile(numbers, 0.05)), "p50": _round(_percentile(numbers, 0.5)),
		"p95": _round(_percentile(numbers, 0.95)), "p99": _round(_percentile(numbers, 0.99)),
		"max": _round(numbers[-1])}


func _percentile(sorted: Array[float], fraction: float) -> float:
	var index := clampi(ceili(fraction * sorted.size()) - 1, 0, sorted.size() - 1)
	return sorted[index]


func _sum(values: Array) -> float:
	var total := 0.0
	for value: Variant in values:
		if value != null:
			total += float(value)
	return total


func _round(value: float) -> float:
	return snappedf(value, 0.001)


func _creature_actor_types() -> Array:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(MODELS))
	if not parsed is Dictionary:
		return []
	var models: Dictionary = (parsed as Dictionary).get("models", {}) as Dictionary
	var actor_types: Dictionary = (parsed as Dictionary).get("actorTypes", {}) as Dictionary
	var candidates: Array = []
	for raw_type: Variant in actor_types:
		var actor_type := int(str(raw_type))
		if actor_type < 200:
			continue
		var model := models.get(str(actor_types[raw_type]), {}) as Dictionary
		var scene := str(model.get("scene", ""))
		if not scene.is_empty() and FileAccess.file_exists(scene) and not bool(model.get("retired", false)):
			candidates.append({"actorType": actor_type, "model": str(actor_types[raw_type]),
				"scale": float((model.get("import", {}) as Dictionary).get("scale", 1.0))})
	candidates.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if float(a["scale"]) != float(b["scale"]):
			return float(a["scale"]) < float(b["scale"])
		return int(a["actorType"]) < int(b["actorType"]))
	var chosen: Array = []
	if candidates.is_empty():
		return chosen
	# Ten models spread across the size range, as the earlier crowd study chose.
	for step: int in range(10):
		chosen.append((candidates[int(floor(float(step) * float(candidates.size() - 1) / 9.0))]
			as Dictionary).duplicate())
	return chosen


func _settle_frames(frames: int) -> void:
	for unused: int in range(frames):
		await process_frame


func _env(key: String, fallback: String) -> String:
	var value := OS.get_environment(key).strip_edges()
	return fallback if value.is_empty() else value


func _env_int(key: String, fallback: int, minimum: int) -> int:
	var value := OS.get_environment(key).strip_edges()
	return maxi(minimum, int(value)) if value.is_valid_int() else fallback


func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		(_report["failures"] as Array).append(label)
		push_error("FAIL: " + label)
	return value


func _finish() -> void:
	_report["failureCount"] = _failures
	var out := _env("RABBITLANDS_CROWD_BENCH_OUT", "user://crowd_presentation_benchmark.json")
	var file := FileAccess.open(out, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(_report, "  "))
		file.close()
	print("crowd-presentation report: ", ProjectSettings.globalize_path(out) if out.begins_with("user://") else out,
		" failures=", _failures)
	quit(_failures)
