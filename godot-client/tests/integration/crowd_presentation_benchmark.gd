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
## Headless runs report scene CPU; windowed runs, with vsync off and no frame
## cap, report the rendered frame time and the renderer's own timers.
##
## The crowd is synthetic: actor records and real server packet shapes fed
## through AppState, as the network would, at a fixed cadence (100 ms steps,
## 400 ms combat exchanges). Run it through run_crowd_presentation_benchmark.py,
## which isolates user data and records the machine. Environment:
##
## - RABBITLANDS_CROWD_BENCH_CELLS: comma list of cell ids, or `phase4` (default),
##   `quick` or `all`; see `cells_for`.
## - RABBITLANDS_CROWD_BENCH_MAP: map id (default four_gates; `none` for no map).
## - RABBITLANDS_CROWD_BENCH_CENTRE: `x,y` server tile the player stands on
##   (default: the map's own centre, or the hot spot for landfall and twinbrook).
## - RABBITLANDS_CROWD_BENCH_SAMPLE_MSEC / _WARMUP_MSEC / _CADENCE_MSEC.
## - RABBITLANDS_CROWD_BENCH_OUT: report path (default user://).
## - RABBITLANDS_CROWD_PRESENTATION / RABBITLANDS_CROWD_BODY_CAP: read by Main.

const BENCHMARK_MAIN_PATH := "res://tests/integration/crowd_benchmark_main.tscn"
const TIERS := AnimationGate.Tier
const MODELS := "res://data/actors/models.json"
const FIRST_ACTOR_ID := 14000
const FULL_KIT_A := {0: 114, 1: 106, 2: 0, 3: 117, 4: 171, 5: 184, 6: 192}
const FULL_KIT_B := {0: 164, 1: 111, 2: 1, 3: 109, 4: 172, 5: 185, 6: 193}
const SCHEMA := 1
const MAX_SPAWN_MSEC := 240000
const MAX_READINESS_MSEC := 60000
const MIN_SAMPLE_FRAMES := 60
## Where each hot spot is when the benchmark stands on its map: the Landfall
## market (the mean of the isle's NPC posts, as the server's S3 preset takes it)
## and a Twinbrook invasion wave's authored centre (S2).
const HOT_SPOTS := {"landfall": Vector2i(122, 225), "twinbrook": Vector2i(675, 186)}

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

func _init() -> void:
	call_deferred("_run")


## The cells a profile runs. `phase4` is the exit-criterion set; `quick` is one
## market and one invasion cell for a smoke run.
static func cells_for(profile: String) -> Array:
	var cells: Array = []
	var all := profile in ["all", "phase4"]
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
	if all:
		return cells
	if profile == "quick":
		return cells.filter(func(cell: Dictionary) -> bool:
			return str(cell.id) in ["s3-market-160", "s2-invasion-160"])
	var wanted := profile.split(",", false)
	return cells.filter(func(cell: Dictionary) -> bool: return str(cell.id) in wanted)


func _run() -> void:
	_headless = DisplayServer.get_name() == "headless"
	_fps_cap = _env_int("RABBITLANDS_CROWD_BENCH_FPS_CAP", 60, 0)
	Engine.max_fps = _fps_cap
	OS.low_processor_usage_mode_sleep_usec = 1
	if not _headless:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	root.size = Vector2i(1280, 720)
	var profile := _env("RABBITLANDS_CROWD_BENCH_CELLS", "phase4")
	var cells := cells_for(profile)
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
		"viewport": [root.size.x, root.size.y],
		"presentation": OS.get_environment("RABBITLANDS_CROWD_PRESENTATION"),
		"graphicsQuality": LookProfile.quality_name(LookProfile.quality()),
		"diagnostics": OS.get_environment("RABBITLANDS_CROWD_BENCH_DIAG"),
		"bodyCap": OS.get_environment("RABBITLANDS_CROWD_BODY_CAP"),
		"measurement": {
			"sampleMilliseconds": _env_int("RABBITLANDS_CROWD_BENCH_SAMPLE_MSEC", 6000, 500),
			"warmupMilliseconds": _env_int("RABBITLANDS_CROWD_BENCH_WARMUP_MSEC", 2000, 100),
			"driver": _driver_mode(),
			"cadenceMilliseconds": _env_int("RABBITLANDS_CROWD_BENCH_CADENCE_MSEC",
				50 if _driver_mode() == "live" else 100, 25),
			"driverDescription": ("live: 50 ms server ticks; each mover steps every 600 ms (a "
				+ "walk) and each fighter acts every 2 s (a combat round), staggered across "
				+ "the crowd" if _driver_mode() == "live" else
				"stress: every mover steps every 100 ms and every fighter acts every 400 ms, "
				+ "all on the same tick (the earlier crowd study's driver)"),
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
	_creatures = _creature_actor_types()
	if not _expect(not cells.is_empty(), "profile %s selects at least one cell" % profile) \
			or not _expect(not _creatures.is_empty(), "creature models resolve"):
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
	await _prewarm()
	for cell: Dictionary in cells:
		await _run_cell(cell)
	await _tear_down_main()
	_finish()


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
	var map_id := _env("RABBITLANDS_CROWD_BENCH_MAP", "four_gates")
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
	_app_state.set("local_actor_id", FIRST_ACTOR_ID)
	_app_state.set("actors", {FIRST_ACTOR_ID: _record(0, true, _centre, {})})
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
	var count := int(spec["count"])
	var shape := str(spec["shape"])
	var records := _make_records(count, shape)
	_app_state.set("selected_actor_id", -1)
	var before := _memory_sample()
	_app_state.set("local_actor_id", FIRST_ACTOR_ID)
	_app_state.set("actors", records)
	_app_state.call("mark_all_actors_changed")
	var spawn := await _spawn_and_build(count)
	var readiness := await _wait_for_world_readiness(str(spec["id"]), 300)
	var census_before := _census()
	var spawned_memory := _memory_sample()
	var active := _active_ids(records, str(spec["activity"]))
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
		"halfRateStepMilliseconds": [], "combatPoseMilliseconds": [], "skeletonUpdates": []}
	var sample_started := Time.get_ticks_msec()
	await _drive_for(plan, int((_report["measurement"] as Dictionary)["sampleMilliseconds"]), raw)
	var elapsed := Time.get_ticks_msec() - sample_started
	var census_after := _census()
	var budget: Dictionary = (_main.get("effect_budget") as RefCounted).call("describe") \
		if _main.get("effect_budget") != null else {}
	var crowd: Dictionary = (_main.get("crowd") as RefCounted).call("describe") \
		if _main.get("crowd") != null else {}
	_app_state.set("actors", {FIRST_ACTOR_ID: _record(0, true, _centre, FULL_KIT_A)})
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
	result["plan"] = {"active": active.size(), "moving": (plan["moving"] as Array).size(),
		"fighting": (plan["fighting"] as Array).size()}
	result["packetsPerSecond"] = _round(_sum(raw["packetsPerFrame"] as Array) * 1000.0 / maxf(1.0, elapsed))
	result["spawn"] = spawn
	result["readiness"] = readiness
	result["census"] = {"afterSpawn": census_before, "afterSample": census_after}
	result["effectBudget"] = budget
	result["crowdPolicy"] = crowd
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
	var local := (_main.get("actor_nodes") as Dictionary).get(FIRST_ACTOR_ID) as Node3D
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
func _drive_for(plan: Dictionary, duration: int, raw: Variant) -> void:
	var cadence := int((_report["measurement"] as Dictionary)["cadenceMilliseconds"])
	var started := Time.get_ticks_msec()
	var next_tick := started
	var tick := 0
	var hard_limit := maxi(duration * 4, 60000)
	while Time.get_ticks_msec() - started < duration \
			or (raw != null and (raw["frameMilliseconds"] as Array).size() < MIN_SAMPLE_FRAMES):
		if Time.get_ticks_msec() - started >= hard_limit:
			break
		if raw != null:
			_main.call("benchmark_reset_frame")
		_driver_packets = 0
		_driver_usec = 0
		var frame_started := Time.get_ticks_usec()
		var now := Time.get_ticks_msec()
		while now >= next_tick:
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
## the earlier crowd study did (RABBITLANDS_CROWD_BENCH_DRIVER).
static func _driver_mode() -> String:
	return "stress" if OS.get_environment("RABBITLANDS_CROWD_BENCH_DRIVER").strip_edges() \
		== "stress" else "live"


func _drive_tick(plan: Dictionary, tick: int) -> void:
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
	var local := nodes.get(FIRST_ACTOR_ID) as Node3D
	var out := {"nodes": nodes.size(), "builtBodies": 0, "deferred": 0, "standIns": 0,
		"drawn": 0, "inFrustumAndDrawn": 0, "tierFull": 0, "tierHalf": 0, "tierPaused": 0,
		"skeletons": 0, "skeletonsProcessing": 0, "beyondDrawDistance": 0, "crowdHidden": 0,
		"capeClothActive": 0, "capeSolversActive": 0}
	var planes: Array[Plane] = camera.get_frustum() if camera != null else []
	# The quarter tier by name, so the census also runs against a client
	# without it.
	var quarter: int = int(TIERS.get("QUARTER", -1))
	for value: Variant in nodes.values():
		var actor := value as ReplicatedActor3D
		if actor == null:
			continue
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
				str(actor.call("cape_cloth_allowed")), str(actor.actor_id == FIRST_ACTOR_ID)]
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
	return out


func _live_effects() -> int:
	var count := 0
	for value: Variant in _main.get("world_effects") as Array:
		count += int(is_instance_valid(value) and not (value as Node).is_queued_for_deletion())
	return count


func _wait_for_world_readiness(label: String, minimum_msec: int) -> Dictionary:
	if str(_report.get("map", "")) == "none":
		await _settle_frames(4)
		return {"label": label, "ready": true, "reason": "no map"}
	var started := Time.get_ticks_msec()
	var deadline := started + MAX_READINESS_MSEC
	var stable := 0
	var previous := ""
	while Time.get_ticks_msec() < deadline:
		await physics_frame
		await process_frame
		var loader := _main.get("world_loader") as WorldLoader
		var chunk := loader.world_root as ContinentChunkStream if loader != null else null
		var idle := _streaming_idle(loader, chunk)
		var signature := "%d|%d|%d" % [GlbSceneCache.cached_scene_count(),
			int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT)),
			chunk.cells.size() if chunk != null else -1]
		stable = stable + 1 if signature == previous and idle else 0
		previous = signature
		if Time.get_ticks_msec() - started >= minimum_msec and stable >= 12:
			break
	var ready := stable >= 12
	_expect(ready, "%s reaches stable resources with no map work pending" % label)
	return {"label": label, "ready": ready, "waitMilliseconds": Time.get_ticks_msec() - started}


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
