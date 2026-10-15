extends SceneTree
## The third performance pass's measuring instrument: map load, memory across a
## tour of the regions, a hundred-creature scene, and a burst of packets.
##
## Four things the first two passes never put a number on:
##
##   maps     - how long each of the eleven exteriors and Four Gates takes to
##              come off disk and into the tree, and what it costs in resident,
##              texture, buffer and video memory while it is up;
##   memory   - what is left behind after each one is unloaded, and whether
##              returning to the first region costs what it cost the first
##              time (anything else is a leak between maps);
##   actors   - scene CPU and render cost with a hundred creatures of the mixed
##              sizes the roster now uses, spread over sixty tiles square,
##              standing still and walking, with the animation gate running;
##   packets  - decoding and reducing a burst of five hundred mixed packets
##              through EloriaProtocol and the AppState reducer.
##
## How to run it, and why in two goes:
##
##   headless, for scene CPU. The engine pads every headless frame to
##   `OS.low_processor_usage_mode_sleep_usec` (6.9 ms by default) because no
##   window can draw; with the pad removed and `Engine.max_fps` at zero, wall
##   time per frame is the scene tree's own CPU cost and nothing else.
##
##       Godot --headless --path . --script res://tests/integration/client_benchmarks.gd
##
##   windowed, for GPU and video memory. The renderer's own timers
##   (`viewport_set_measure_render_time`) are the only frame numbers worth
##   having here - a windowed run's wall clock is the compositor's refresh
##   steps, not the scene's cost - and `RENDERING_INFO_*` is zero under the
##   headless dummy driver, so texture, buffer and video memory only mean
##   anything in this run.
##
##       Godot --audio-driver Dummy --rendering-method gl_compatibility \
##             --path . --script res://tests/integration/client_benchmarks.gd
##
## Environment:
##   ELORIA_ARTIFACT_DIR   where the JSON goes (default res://test-artifacts/benchmarks)
##   ELORIA_BENCH_SECTIONS comma list of maps,memory,actors,packets (default all)
##   ELORIA_BENCH_MAP      the map the actor scene stands on ("" for none)
##   ELORIA_BENCH_LABEL    a name for the run, written into the report
##   ELORIA_BENCH_OUTPUT   the file name inside the artifact directory
##   ELORIA_PACKET_BENCH_REPEATS packet timing repeats (default 8)

## The eleven exteriors and the city, in the order a tour would take them. The
## ids are registry keys; the manifests are resolved through MapRegistry, which
## is the path the client itself uses.
const REGIONS: Array[String] = [
	"four_gates", "mirrorhold", "crownwater", "whitehorn_range",
	"amethyst_barrens", "sunmane_steppe", "amberwood", "grey_moors",
	"westhaven", "verdant_stair", "ssarathi_ruins", "manymouth_delta",
]

const REGISTRY := "res://data/maps/registry.json"
const MODELS := "res://data/actors/models.json"

## A hundred creatures over sixty tiles square is the scene the roadmap asks
## for: enough bodies to be worth measuring, spread widely enough that the gate
## has something to classify rather than a single clump either wholly in view
## or wholly out of it.
const ACTOR_COUNT := 100
const FIELD_TILES := 60
const FIRST_ACTOR_ID := 4000

const PACKET_BURST := 500
## Frames per timed sample, and the frames thrown away before one starts.
const SAMPLE_FRAMES := 120
const SETTLE_FRAMES := 24
## How many `_sync_world` passes the spawn budget needs for a hundred actors,
## with headroom. Main builds ACTOR_SPAWN_BUDGET of them per pass on purpose.
const SPAWN_PASSES := 60

var _failures := 0
var _artifacts := ""
var _headless := false
var _report: Dictionary = {}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var expected_user_root := OS.get_environment(
		"ELORIA_CROWD_EXPECT_USER_ROOT").replace("\\", "/")
	while expected_user_root.ends_with("/"):
		expected_user_root = expected_user_root.left(-1)
	var actual_user_dir := OS.get_user_data_dir().replace("\\", "/")
	if not expected_user_root.is_empty() \
			and actual_user_dir != expected_user_root \
			and not actual_user_dir.begins_with(expected_user_root + "/"):
		push_error("client benchmark user data escaped its isolated root: "
			+ actual_user_dir)
		quit(1)
		return
	_headless = DisplayServer.get_name() == "headless"
	# Headless frames are padded to the idle sleep, which is the whole frame
	# time at this scale. Removing it is what makes headless wall time mean
	# scene CPU.
	OS.low_processor_usage_mode_sleep_usec = 1
	Engine.max_fps = 0
	root.size = Vector2i(1280, 720)
	# What a region costs to build, which is the question this file answers and
	# is not the same question as what it costs to read one back. The map cache
	# would turn every repeat after the first into a warm load and quietly
	# rewrite this table; `map_load_phases.gd` reports the warm numbers, beside
	# the cold ones, on purpose.
	OS.set_environment(MapSceneCache.DISABLE_ENVIRONMENT, "1")

	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/benchmarks")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")

	var sections: PackedStringArray = _sections()
	_report = {
		"label": OS.get_environment("ELORIA_BENCH_LABEL"),
		"display": DisplayServer.get_name(),
		"headless": _headless,
		"renderer": str(ProjectSettings.get_setting(
			"rendering/renderer/rendering_method")),
		"adapter": RenderingServer.get_video_adapter_name(),
		"godot": "%d.%d.%d" % [Engine.get_version_info()["major"],
			Engine.get_version_info()["minor"], Engine.get_version_info()["patch"]],
		"viewport": [root.size.x, root.size.y],
		"userDataDir": actual_user_dir,
		"sections": sections,
		"unixTime": int(Time.get_unix_time_from_system()),
	}

	if sections.has("maps") or sections.has("memory"):
		_report["maps"] = await _measure_maps(sections.has("memory"))
	if sections.has("actors"):
		_report["actors"] = await _measure_actors()
	if sections.has("packets"):
		_report["packets"] = _measure_packets()

	var report_name: String = OS.get_environment("ELORIA_BENCH_OUTPUT")
	if report_name.is_empty():
		report_name = "client-benchmarks-headless.json" if _headless \
			else "client-benchmarks-windowed.json"
	var file := FileAccess.open(_artifacts.path_join(report_name), FileAccess.WRITE)
	_expect(file != null, "the report is writable")
	if file != null:
		file.store_string(JSON.stringify(_report, "  "))
		file.close()
		print("wrote ", _artifacts.path_join(report_name))
	print("client benchmarks: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _sections() -> PackedStringArray:
	var raw: String = OS.get_environment("ELORIA_BENCH_SECTIONS")
	if raw.strip_edges().is_empty():
		return PackedStringArray(["maps", "memory", "actors", "packets"])
	var out := PackedStringArray()
	for part: String in raw.split(",", false):
		out.append(part.strip_edges().to_lower())
	return out

# ---------------------------------------------------------------- (a) and (b)

## Loads every region in turn into a bare stage - a WorldEnvironment, a sun and
## a camera, which is what the client wraps its WorldLoader in - timing the
## load and reading memory with the map up and again after it is unloaded. The
## first region is then loaded a second time at the end: a second visit that
## costs more than the first is the signature of something the unload did not
## give back.
func _measure_maps(with_memory: bool) -> Dictionary:
	var registry: Dictionary = _json(REGISTRY).get("maps", {}) as Dictionary
	var stage := Node3D.new()
	root.add_child(stage)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	stage.add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	var camera := Camera3D.new()
	camera.far = 900.0
	camera.current = true
	stage.add_child(camera)
	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	stage.add_child(loader)

	await _settle(SETTLE_FRAMES)
	var results: Dictionary = {
		"baseline": _memory_sample(),
		"regions": [],
		"withMemory": with_memory,
	}
	# The machine this runs on is shared, so one load's wall time is noise as
	# much as cost. Each region is loaded `repeats` times and the median kept;
	# every sample is written out beside it.
	var repeats: int = maxi(1, int(OS.get_environment("ELORIA_BENCH_MAP_REPEATS")))
	results["repeats"] = repeats
	for region: String in REGIONS:
		var measured: Dictionary = await _load_region(loader, registry, region,
			world_environment, sun)
		var samples := PackedFloat64Array([float(measured.get("loadMilliseconds", 0.0))])
		for extra: int in range(repeats - 1):
			var again: Dictionary = await _load_region(loader, registry, region,
				world_environment, sun)
			samples.append(float(again.get("loadMilliseconds", 0.0)))
		var ordered := samples.duplicate()
		ordered.sort()
		measured["loadSamples"] = samples
		measured["loadMedianMilliseconds"] = snappedf(
			ordered[ordered.size() / 2], 0.1)
		(results["regions"] as Array).append(measured)
	# The leak check: back to the first region after the whole tour.
	results["revisit"] = await _load_region(loader, registry, REGIONS[0],
		world_environment, sun)
	loader.unload_world()
	await _settle(SETTLE_FRAMES)
	results["afterTour"] = _memory_sample()
	stage.queue_free()
	await _settle(4)
	return results

func _load_region(loader: WorldLoader, registry: Dictionary, region: String,
		world_environment: WorldEnvironment, sun: DirectionalLight3D) -> Dictionary:
	var entry: Dictionary = MapRegistry.resolve(registry, region)
	if entry.is_empty():
		_expect(false, region + " resolves in the map registry")
		return {"id": region, "error": "registry_miss"}
	var manifest_path: String = ProjectSettings.globalize_path(
		str(entry.get("manifest", "")))
	var before: Dictionary = _memory_sample()
	var started: int = Time.get_ticks_usec()
	loader.load_world(manifest_path)
	var deadline: int = Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	var load_ms: float = float(Time.get_ticks_usec() - started) / 1000.0
	if not _expect(loader.world_root != null, region + " loads"):
		return {"id": region, "error": "load_failed"}
	WorldEnvironmentBinder.apply(loader.manifest, world_environment, sun)
	await _settle(SETTLE_FRAMES)
	var mesh_instances: Array[Node] = loader.world_root.find_children(
		"*", "MeshInstance3D", true, false)
	var batches: Array[Node] = loader.world_root.find_children(
		"*", "MultiMeshInstance3D", true, false)
	var bodies: Array[Node] = loader.world_root.find_children(
		"*", "StaticBody3D", true, false)
	var drawn: int = 0
	for node: Node in mesh_instances:
		if (node as MeshInstance3D).visible:
			drawn += 1
	var loaded: Dictionary = _memory_sample()
	var result: Dictionary = {
		"id": region,
		"asset": loader.manifest.asset_id(),
		"glbBytes": _file_size(loader.manifest.glb_path()),
		"loadMilliseconds": snappedf(load_ms, 0.1),
		"meshInstances": mesh_instances.size(),
		"drawnMeshInstances": drawn,
		"staticBatches": batches.size(),
		"collisionBodies": bodies.size(),
		"nodes": _count_nodes(loader.world_root),
		"before": before,
		"loaded": loaded,
		"delta": _memory_delta(before, loaded),
	}
	loader.unload_world()
	await _settle(SETTLE_FRAMES)
	var unloaded: Dictionary = _memory_sample()
	result["unloaded"] = unloaded
	result["retained"] = _memory_delta(before, unloaded)
	print("%-18s %8.1f ms  %5d meshes (%4d drawn, %3d batches)  +%6.1f MB static  +%6.1f MB texture  retained %+7.2f MB static %+7.2f MB texture" % [
		region, result["loadMilliseconds"], mesh_instances.size(), drawn,
		batches.size(),
		float((result["delta"] as Dictionary)["staticBytes"]) / 1048576.0,
		float((result["delta"] as Dictionary)["textureBytes"]) / 1048576.0,
		float((result["retained"] as Dictionary)["staticBytes"]) / 1048576.0,
		float((result["retained"] as Dictionary)["textureBytes"]) / 1048576.0])
	return result

# -------------------------------------------------------------------- (c)

## A hundred creatures through the client's own build path: AppState holds the
## records, `_sync_world` builds the nodes a budget at a time, `_process` runs
## the animation gate over them. Idle is the scene standing still; walking
## feeds every actor a step command a frame through the real packet path, so
## the reducer, the interpolation and the animation crossfade are all in the
## number.
func _measure_actors() -> Dictionary:
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	# The per-frame work this measures - the animation gate, the camera follow,
	# the map viewports - all hangs off `game_view.visible` in `_process`, so
	# the scene has to be in the world rather than on the login panel. This is
	# what `_on_login_succeeded` does; there is no server here to say so.
	(main.get("login_panel") as Control).hide()
	(main.get("creation_panel") as Control).hide()
	(main.get("game_view") as Control).show()
	await process_frame

	var results: Dictionary = {"actorCount": ACTOR_COUNT, "fieldTiles": FIELD_TILES}
	var map_id: String = OS.get_environment("ELORIA_BENCH_MAP")
	if map_id.strip_edges().is_empty():
		map_id = "four_gates"
	if map_id != "none":
		app_state.set("current_map", map_id)
		main.call("_load_server_map")
		var loader: WorldLoader = main.get("world_loader") as WorldLoader
		var deadline: int = Time.get_ticks_msec() + 180000
		while loader.world_root == null and Time.get_ticks_msec() < deadline:
			await process_frame
		_expect(loader.world_root != null, "the actor scene's map loads")
		results["map"] = map_id
	else:
		results["map"] = ""
	await _settle(SETTLE_FRAMES)

	results["empty"] = await _sample_frames(main, "empty")

	# The field is laid out around the map's arrival tile, so it stands on the
	# ground rather than off the edge of it, and the first of the pack is made
	# the local actor: that is what puts the gameplay camera in the crowd, which
	# is the only place a hundred creatures cost what they cost in play. Left
	# looking somewhere else the gate pauses all hundred and the measurement is
	# of nothing.
	var adapter: CoordinateAdapter = main.get("adapter") as CoordinateAdapter
	var centre := Vector2i(180, 180)
	if adapter != null:
		centre = Vector2i(roundi(adapter.server_origin.x),
			roundi(adapter.server_origin.y))
	var origin: Vector2i = centre - Vector2i(FIELD_TILES / 2, FIELD_TILES / 2)
	results["fieldOrigin"] = [origin.x, origin.y]

	var chosen: Array = _creature_actor_types()
	results["actorTypes"] = chosen.size()
	var actors: Dictionary = {}
	for index: int in range(ACTOR_COUNT):
		var pick: Dictionary = chosen[index % chosen.size()] as Dictionary
		var id: int = FIRST_ACTOR_ID + index
		actors[id] = {
			"actor_id": id,
			"x": origin.x + (index % 10) * (FIELD_TILES / 10),
			"y": origin.y + (index / 10) * (FIELD_TILES / 10),
			"rotation": (index * 36) % 360,
			"actor_type": int(pick["actorType"]),
			"kind": 1,
			"name": str(pick["model"]),
			"health": 40, "max_health": 60,
			"alive": true,
		}
	# One of the pack is the player, standing in the middle of it.
	var local_id: int = FIRST_ACTOR_ID + ACTOR_COUNT / 2
	(actors[local_id] as Dictionary)["x"] = centre.x
	(actors[local_id] as Dictionary)["y"] = centre.y
	app_state.set("local_actor_id", local_id)
	# The spawn cost of the pack, and the cost of the pack once it is standing.
	var spawn_started: int = Time.get_ticks_usec()
	app_state.set("actors", actors)
	app_state.call("mark_all_actors_changed")
	var passes: int = 0
	var nodes: Dictionary = main.get("actor_nodes") as Dictionary
	while nodes.size() < ACTOR_COUNT and passes < SPAWN_PASSES:
		main.call("_sync_world")
		passes += 1
		await process_frame
		nodes = main.get("actor_nodes") as Dictionary
	results["spawnMilliseconds"] = snappedf(
		float(Time.get_ticks_usec() - spawn_started) / 1000.0, 0.1)
	results["spawnPasses"] = passes
	results["spawnedNodes"] = nodes.size()
	_expect(nodes.size() == ACTOR_COUNT,
		"every fixture creature got a node (%d of %d)" % [nodes.size(), ACTOR_COUNT])
	results["cachedScenes"] = GlbSceneCache.cached_scene_count()
	results["cachedLibraries"] = NativeAnimationImporter.cached_library_count()
	# Ten species between a hundred bodies: if the cache is sharing what it
	# hands out, the distinct mesh and material counts under the model nodes
	# stay near what ten species carry, not a hundred copies of them.
	results["meshes"] = _resource_census(nodes)
	await _settle(SETTLE_FRAMES)

	results["idle"] = await _sample_frames(main, "idle")
	var gate: AnimationGate = main.get("animation_gate") as AnimationGate
	results["idle"]["halfRatePlayers"] = gate.half_rate_count() if gate != null else -1
	results["idle"]["drawn"] = _drawn_count(nodes)
	results["idle"]["tiers"] = _tier_census(nodes)

	results["walking"] = await _sample_walking(main, app_state, actors)

	app_state.set("actors", {})
	main.call("_sync_world")
	main.queue_free()
	await _settle(4)
	return results

## Every actor takes a step command a frame, the way a moving crowd arrives:
## one ADD_ACTOR_COMMAND packet carrying the whole pack, decoded and reduced by
## AppState, then one `_sync_world` over the change set.
func _sample_walking(main: Node, app_state: Node, actors: Dictionary) -> Dictionary:
	var ids: Array = actors.keys()
	# Steps 22 (+x) and 26 (-x) in the legacy movement set, alternated, so every
	# actor always has a segment to interpolate and a walk cycle to blend into
	# while the pack stays inside the field it was laid out on.
	var payloads: Array[PackedByteArray] = []
	for step: int in [22, 26]:
		var payload := PackedByteArray()
		for id_value: Variant in ids:
			var id: int = int(id_value)
			payload.append(id & 0xff)
			payload.append((id >> 8) & 0xff)
			payload.append(step)
		payloads.append(payload)
	for turn: int in range(8):
		app_state.call("_on_packet",
			EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, payloads[turn % 2])
		main.call("_sync_world", app_state.call("take_changed_actors"))
		await process_frame
	# The frame is split three ways so the answer names a function rather than a
	# scene: the packet's own reduce, the re-presentation of the actors it
	# named, and everything the tree does on its own behind those two.
	var reduce_usec: int = 0
	var present_usec: int = 0
	var started: int = Time.get_ticks_usec()
	for turn: int in range(SAMPLE_FRAMES):
		var mark: int = Time.get_ticks_usec()
		app_state.call("_on_packet",
			EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, payloads[turn % 2])
		var reduced: int = Time.get_ticks_usec()
		main.call("_sync_world", app_state.call("take_changed_actors"))
		present_usec += Time.get_ticks_usec() - reduced
		reduce_usec += reduced - mark
		await process_frame
	var elapsed: float = float(Time.get_ticks_usec() - started) / 1000.0
	var frames: float = float(SAMPLE_FRAMES)
	var sample: Dictionary = {
		"frames": SAMPLE_FRAMES,
		"sceneMillisecondsPerFrame": snappedf(elapsed / frames, 0.001),
		"reduceMillisecondsPerFrame": snappedf(
			float(reduce_usec) / frames / 1000.0, 0.001),
		"presentMillisecondsPerFrame": snappedf(
			float(present_usec) / frames / 1000.0, 0.001),
	}
	sample["restMillisecondsPerFrame"] = snappedf(
		float(sample["sceneMillisecondsPerFrame"])
		- float(sample["reduceMillisecondsPerFrame"])
		- float(sample["presentMillisecondsPerFrame"]), 0.001)
	sample.merge(_render_sample(_world_viewport(main)))
	print("  walking  %7.3f ms scene = %.3f reduce + %.3f present + %.3f rest" % [
		sample["sceneMillisecondsPerFrame"], sample["reduceMillisecondsPerFrame"],
		sample["presentMillisecondsPerFrame"], sample["restMillisecondsPerFrame"]])
	return sample

## The 3D SubViewport by its full path: two nodes in main.tscn are called
## "Viewport" (the world and the character-creation preview), so the unique
## name would be ambiguous.
func _world_viewport(main: Node) -> SubViewport:
	return main.get_node_or_null("GameView/ViewportContainer/Viewport") as SubViewport

## Wall time per frame with the idle pad removed (scene CPU, headless), and the
## renderer's own CPU and GPU timers for the root viewport and the 3D
## SubViewport (windowed).
func _sample_frames(main: Node, label: String) -> Dictionary:
	var viewport_rid: RID = root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(viewport_rid, true)
	var sub: SubViewport = _world_viewport(main)
	if sub != null:
		RenderingServer.viewport_set_measure_render_time(sub.get_viewport_rid(), true)
	await _settle(SETTLE_FRAMES)
	var started: int = Time.get_ticks_usec()
	for unused: int in range(SAMPLE_FRAMES):
		await process_frame
	var elapsed: float = float(Time.get_ticks_usec() - started) / 1000.0
	var sample: Dictionary = {
		"id": label,
		"frames": SAMPLE_FRAMES,
		"sceneMillisecondsPerFrame": snappedf(elapsed / float(SAMPLE_FRAMES), 0.001),
	}
	sample.merge(_render_sample(sub))
	print("  %-8s %7.3f ms scene, %6.3f ms render CPU, %6.3f ms GPU, %d draw calls" % [
		label, sample["sceneMillisecondsPerFrame"], sample["renderCpuMilliseconds"],
		sample["renderGpuMilliseconds"], sample["drawCalls"]])
	return sample

func _render_sample(sub: SubViewport = null) -> Dictionary:
	var viewport_rid: RID = root.get_viewport_rid()
	var out: Dictionary = {
		"renderCpuMilliseconds": snappedf(
			RenderingServer.viewport_get_measured_render_time_cpu(viewport_rid), 0.001),
		"renderGpuMilliseconds": snappedf(
			RenderingServer.viewport_get_measured_render_time_gpu(viewport_rid), 0.001),
		"drawCalls": int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)),
		"primitives": int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)),
	}
	if sub != null:
		out["worldRenderCpuMilliseconds"] = snappedf(
			RenderingServer.viewport_get_measured_render_time_cpu(
				sub.get_viewport_rid()), 0.001)
		out["worldRenderGpuMilliseconds"] = snappedf(
			RenderingServer.viewport_get_measured_render_time_gpu(
				sub.get_viewport_rid()), 0.001)
	out.merge(_memory_sample())
	return out

## Creature actor types spread across the size range the roster now uses: the
## smallest, the largest, and eight steps between, so a hundred bodies are a
## mixture rather than a hundred copies of one mesh.
func _creature_actor_types() -> Array:
	var catalogue: Dictionary = _json(MODELS)
	var models: Dictionary = catalogue.get("models", {}) as Dictionary
	var actor_types: Dictionary = catalogue.get("actorTypes", {}) as Dictionary
	var candidates: Array = []
	for raw_type: Variant in actor_types:
		var actor_type: int = int(str(raw_type))
		# The creature range; below 200 are the playable races.
		if actor_type < 200:
			continue
		var model_id: String = str(actor_types[raw_type])
		var model: Dictionary = models.get(model_id, {}) as Dictionary
		var scene: String = str(model.get("scene", ""))
		if scene.is_empty() or not FileAccess.file_exists(scene):
			continue
		candidates.append({
			"actorType": actor_type, "model": model_id,
			"scale": float((model.get("import", {}) as Dictionary).get("scale", 1.0)),
		})
	candidates.sort_custom(func(a: Variant, b: Variant) -> bool:
		return float((a as Dictionary)["scale"]) < float((b as Dictionary)["scale"]))
	if candidates.is_empty():
		_expect(false, "the catalogue offers creature models with scenes on disk")
		return [{"actorType": 1, "model": "luminous_male", "scale": 1.0}]
	# Ten evenly spaced picks across the sorted size range; the caller lays them
	# out in ten columns of ten, each column one species.
	var chosen: Array = []
	for step: int in range(10):
		var index: int = int(floor(float(step) * float(candidates.size() - 1) / 9.0))
		chosen.append((candidates[index] as Dictionary).duplicate())
	return chosen

## What a pack of actors holds in resources: how many MeshInstance3D nodes,
## how many distinct Mesh and Material objects behind them, and the same three
## counted only under the species model, where sharing is supposed to happen.
func _resource_census(nodes: Dictionary) -> Dictionary:
	var meshes: Dictionary = {}
	var materials: Dictionary = {}
	var model_meshes: Dictionary = {}
	var model_materials: Dictionary = {}
	var instances: int = 0
	var model_instances: int = 0
	for value: Variant in nodes.values():
		if not is_instance_valid(value):
			continue
		var model: Node = (value as Node).get_node_or_null("NativeModel")
		for child: Node in (value as Node).find_children("*", "MeshInstance3D", true, false):
			var instance: MeshInstance3D = child as MeshInstance3D
			instances += 1
			var under_model: bool = model != null and model.is_ancestor_of(instance)
			if under_model:
				model_instances += 1
			var mesh: Mesh = instance.mesh
			if mesh != null:
				meshes[mesh.get_instance_id()] = true
				if under_model:
					model_meshes[mesh.get_instance_id()] = true
			for surface: int in range(mesh.get_surface_count() if mesh != null else 0):
				var material: Material = instance.get_active_material(surface)
				if material == null:
					continue
				materials[material.get_instance_id()] = true
				if under_model:
					model_materials[material.get_instance_id()] = true
	return {
		"meshInstances": instances,
		"distinctMeshes": meshes.size(),
		"distinctMaterials": materials.size(),
		"modelMeshInstances": model_instances,
		"distinctModelMeshes": model_meshes.size(),
		"distinctModelMaterials": model_materials.size(),
	}

## How the gate has classified the pack: what a frame is actually paying for.
func _tier_census(nodes: Dictionary) -> Dictionary:
	var census: Dictionary = {"full": 0, "half": 0, "paused": 0}
	for value: Variant in nodes.values():
		if not is_instance_valid(value):
			continue
		match (value as ReplicatedActor3D).animation_tier():
			AnimationGate.Tier.HALF:
				census["half"] += 1
			AnimationGate.Tier.PAUSED:
				census["paused"] += 1
			_:
				census["full"] += 1
	return census

func _drawn_count(nodes: Dictionary) -> int:
	var drawn: int = 0
	for value: Variant in nodes.values():
		if is_instance_valid(value) and (value as ReplicatedActor3D).is_drawn():
			drawn += 1
	return drawn

# -------------------------------------------------------------------- (d)

## Five hundred packets in one buffer, the shape a busy second looks like:
## actor steps for a screenful of creatures, the partial stats that follow
## every hit, and chat. Decoding is timed on its own, then decoding with the
## AppState reducer behind it, so the two halves of the cost are separable.
func _measure_packets() -> Dictionary:
	# AppState is an autoload, so it is standing whether or not main.tscn is.
	var app_state: Node = root.get_node_or_null("/root/AppState")
	if not _expect(app_state != null, "AppState is available to the reducer benchmark"):
		return {}
	var native_crowd_active := bool(app_state.call(
		"native_crowd_reducer_active")) \
		if app_state.has_method("native_crowd_reducer_active") else false
	if OS.get_environment("ELORIA_NATIVE_CROWD") == "1":
		_expect(native_crowd_active,
			"the requested native AppState reducer is active")

	var burst := PackedByteArray()
	var counts: Dictionary = {"actor_commands": 0, "partial_stats": 0, "chat": 0}
	var actor_ids: Array[int] = []
	for index: int in range(24):
		actor_ids.append(FIRST_ACTOR_ID + index)
	for index: int in range(PACKET_BURST):
		match index % 5:
			0, 1, 2:
				# A move packet carrying eight actors' steps, which is what a
				# populated map sends every server tick.
				var payload := PackedByteArray()
				for slot: int in range(8):
					var id: int = actor_ids[(index + slot) % actor_ids.size()]
					payload.append(id & 0xff)
					payload.append((id >> 8) & 0xff)
					# 20-27 are the eight walk steps.
					payload.append(20 + (slot % 8))
				burst.append_array(EloriaProtocol.encode(
					EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, payload))
				counts["actor_commands"] += 1
			3:
				var stats := PackedByteArray()
				for slot: int in [5, 6, 7]:
					stats.append(slot)
					var value: int = 100 + index
					stats.append(value & 0xff)
					stats.append((value >> 8) & 0xff)
					stats.append((value >> 16) & 0xff)
					stats.append((value >> 24) & 0xff)
				burst.append_array(EloriaProtocol.encode(
					EloriaProtocol.ServerMessage.SEND_PARTIAL_STAT, stats))
				counts["partial_stats"] += 1
			_:
				var text := PackedByteArray([0])
				text.append_array(("Anonymous %d: the burst carries chat too"
					% index).to_utf8_buffer())
				text.append(0)
				burst.append_array(EloriaProtocol.encode(
					EloriaProtocol.ServerMessage.RAW_TEXT, text))
				counts["chat"] += 1

	# Seed the actors the move packets name, so the reducer does real work
	# rather than skipping ids it does not hold.
	var seeded: Dictionary = {}
	for id: int in actor_ids:
		seeded[id] = {"actor_id": id, "x": 100, "y": 100, "rotation": 0,
			"actor_type": 1, "kind": 1, "name": "Burst", "health": 5,
			"max_health": 9, "alive": true}

	var decode_usec: int = 0
	var full_usec: int = 0
	var repeats: int = max(1, int(OS.get_environment(
		"ELORIA_PACKET_BENCH_REPEATS"))) if not OS.get_environment(
		"ELORIA_PACKET_BENCH_REPEATS").is_empty() else 8
	var decoded: int = 0
	for repeat: int in range(repeats):
		var offset: int = 0
		var started: int = Time.get_ticks_usec()
		decoded = 0
		while offset < burst.size():
			var frame: Dictionary = EloriaProtocol.try_decode(burst, offset)
			if str(frame.get("status", "")) != "ok":
				break
			offset += int(frame["consumed"])
			decoded += 1
		decode_usec += Time.get_ticks_usec() - started

	for repeat: int in range(repeats):
		app_state.set("actors", seeded.duplicate(true))
		app_state.call("take_changed_actors")
		var offset: int = 0
		var started: int = Time.get_ticks_usec()
		while offset < burst.size():
			var frame: Dictionary = EloriaProtocol.try_decode(burst, offset)
			if str(frame.get("status", "")) != "ok":
				break
			offset += int(frame["consumed"])
			app_state.call("_on_packet", int(frame["command"]),
				frame["payload"] as PackedByteArray)
		full_usec += Time.get_ticks_usec() - started

	# The same burst again, one packet kind at a time, so the total names the
	# branch that owns it rather than only the sum.
	var by_kind: Dictionary = {}
	for kind: Array in [
			["actor_commands", EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND],
			["partial_stats", EloriaProtocol.ServerMessage.SEND_PARTIAL_STAT],
			["chat", EloriaProtocol.ServerMessage.RAW_TEXT]]:
		var command: int = int(kind[1])
		var kind_usec: int = 0
		for repeat: int in range(repeats):
			app_state.set("actors", seeded.duplicate(true))
			app_state.call("take_changed_actors")
			var offset: int = 0
			var started: int = Time.get_ticks_usec()
			while offset < burst.size():
				var frame: Dictionary = EloriaProtocol.try_decode(burst, offset)
				if str(frame.get("status", "")) != "ok":
					break
				offset += int(frame["consumed"])
				if int(frame["command"]) == command:
					app_state.call("_on_packet", command,
						frame["payload"] as PackedByteArray)
			kind_usec += Time.get_ticks_usec() - started
		by_kind[str(kind[0])] = snappedf(
			float(kind_usec) / float(repeats) / 1000.0
			- float(decode_usec) / float(repeats) / 1000.0, 0.001)

	app_state.set("actors", {})
	app_state.call("take_changed_actors")

	_expect(decoded == PACKET_BURST,
		"the burst drains to %d packets (got %d)" % [PACKET_BURST, decoded])
	var results: Dictionary = {
		"nativeCrowdReducerActive": native_crowd_active,
		"packets": PACKET_BURST,
		"bytes": burst.size(),
		"mix": counts,
		"repeats": repeats,
		"decodeMilliseconds": snappedf(
			float(decode_usec) / float(repeats) / 1000.0, 0.001),
		"decodeAndReduceMilliseconds": snappedf(
			float(full_usec) / float(repeats) / 1000.0, 0.001),
		"reduceMillisecondsByKind": by_kind,
	}
	results["reduceMilliseconds"] = snappedf(
		float(results["decodeAndReduceMilliseconds"])
		- float(results["decodeMilliseconds"]), 0.001)
	results["microsecondsPerPacket"] = snappedf(
		float(results["decodeAndReduceMilliseconds"]) * 1000.0
		/ float(PACKET_BURST), 0.01)
	print("packets: %d in %d bytes - decode %.3f ms, decode+reduce %.3f ms (%.2f us each)" % [
		PACKET_BURST, burst.size(), results["decodeMilliseconds"],
		results["decodeAndReduceMilliseconds"], results["microsecondsPerPacket"]])
	return results

# ------------------------------------------------------------------ helpers

func _memory_sample() -> Dictionary:
	return {
		"staticBytes": OS.get_static_memory_usage(),
		"monitorStaticBytes": int(Performance.get_monitor(Performance.MEMORY_STATIC)),
		"textureBytes": int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED)),
		"bufferBytes": int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_BUFFER_MEM_USED)),
		"videoBytes": int(RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)),
		"objects": int(Performance.get_monitor(Performance.OBJECT_COUNT)),
		"resources": int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT)),
		"nodes": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
	}

func _memory_delta(before: Dictionary, after: Dictionary) -> Dictionary:
	var out: Dictionary = {}
	for key: Variant in after:
		out[key] = int(after[key]) - int(before.get(key, 0))
	return out

func _count_nodes(node: Node) -> int:
	var total: int = 1
	for child: Node in node.get_children():
		total += _count_nodes(child)
	return total

func _file_size(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return 0
	var size: int = file.get_length()
	file.close()
	return size

func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_expect(false, path + " is readable")
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed as Dictionary if parsed is Dictionary else {}

func _settle(frames: int) -> void:
	for unused: int in range(frames):
		await process_frame

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
