extends SceneTree
## Landfall -> Landfall Town -> Landfall -> Landfall Town with the real
## packages, the production WorldLoader and WorldPark, and the production
## environment/camera/section/cutaway controllers. No Main, network or avatar.
##
## Time to ready (the call that changes the map, its controller binding, a
## first draw and three consecutive grounded physics frames at the arrival)
## is measured for each kind of transition:
##   exterior_cold      Landfall from its package (the baseline)
##   interior_preloaded the Town built while "walking up" to its door, adopted
##   exterior_parked    back to Landfall, kept detached while inside
##   interior_parked    into the Town again, kept detached while outside
##   interior_cold      the Town from its package with nothing kept or cached
##                      in GlbSceneCache (OS and driver caches stay warm)
## plus the main thread's frame times while the preload ran, the longest
## preload slice (must stay under 50 ms), WorldPark's park/re-attach timings
## and process memory at each phase.
##
## Run after an import, rendered for meaningful frame times (headless works
## for the functional checks):
##   godot --path godot-client --script res://tests/integration/landfall_town_park.gd
##   godot --path godot-client --script res://tests/integration/landfall_town_park.gd -- --report C:/rabbitlands/.local/lt-park/run1.json
## Options: --interior <map id> (default landfall_town), --door <object id>
## (default: the interior's first door onto Landfall), --report <path>,
## --park-held (lift WorldParkPolicy.HELD_INTERIORS: measures parking with
## --interior landfall_insides, which is held until such a measurement).
## Exit status 0 when every check passed; the report is JSON.
const WorldParkScript := preload("res://src/world/world_park.gd")
const Policy := preload("res://src/world/world_park_policy.gd")
const Rig := preload("res://tests/integration/interior_load_benchmark_rig.tscn")
const EXTERIOR := "landfall"
const HITCH_MSEC := 50.0

var checks: Array = []
var memory: Array = []
var transitions: Array = []
var stage: Node3D
var loader: WorldLoader
var park: Node
var rig: Node3D
var environment: WorldEnvironment
var sun: DirectionalLight3D
var sections := SecretSections.new()
var cutaway := InteriorCutaway.new()
var registry: Dictionary = {}
var rendered := true

func _init() -> void:
	_run.call_deferred()

func _check(ok: bool, label: String, detail: Variant = null) -> void:
	checks.append({"ok": ok, "check": label, "detail": detail})
	print("LANDFALL_TOWN_PARK ", "PASS " if ok else "FAIL ", label, "" if detail == null else " " + str(detail))

func _argument(name: String, fallback: String) -> String:
	var arguments := OS.get_cmdline_user_args()
	var at := arguments.find(name)
	return arguments[at + 1] if at >= 0 and at + 1 < arguments.size() else fallback

func _memory(label: String) -> void:
	memory.append({"phase": label, "static_bytes": OS.get_static_memory_usage(),
		"texture_gpu_bytes": Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED),
		"buffer_gpu_bytes": Performance.get_monitor(Performance.RENDER_BUFFER_MEM_USED),
		"video_gpu_bytes": Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		"objects": Performance.get_monitor(Performance.OBJECT_COUNT),
		"nodes": Performance.get_monitor(Performance.OBJECT_NODE_COUNT)})

func _ground(point: Vector3) -> bool:
	var space := stage.get_world_3d().direct_space_state
	var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(
		point + Vector3.UP * 20.0, point + Vector3.DOWN * 30.0, WorldLoader.NAVIGATION_SURFACE_LAYER))
	return not hit.is_empty()

func _framed(point: Vector3) -> bool:
	var stream := loader.world_root as ContinentChunkStream
	if stream == null:
		return true
	if not stream.arrival_resident(point):
		return false
	for entry: Dictionary in stream.entries:
		if stream.bounds_distance(point, entry.bounds) <= ContinentChunkStream.ARRIVAL_FRAME_METRES \
				and not stream.cells.has(str(entry.id)):
			return false
	return true

## What Main does with a bound world that matters for its first frame.
func _bind(point: Vector3) -> void:
	WorldEnvironmentBinder.apply(loader.manifest, environment, sun, stage)
	WorldEnvironmentBinder.apply_camera(loader.manifest, rig)
	sections.configure(loader.manifest, loader.world_root)
	cutaway.configure(loader.manifest, loader.world_root)
	rig.call("set_focus", point)
	sections.update(point, true)
	cutaway.update(float(rig.get("yaw_degrees")), true, sections.current_section(), point)

## One map change, timed from the call to a grounded first draw.
func _change(kind: String, from: String, to: String, path: String, point: Vector3) -> Dictionary:
	var began := Time.get_ticks_usec()
	var kept: Dictionary = park.take(to)
	park.leave(loader, from, to)
	if not kept.is_empty():
		loader.adopt_world(kept)
	else:
		loader.load_world(path, point)
	var loaded := Time.get_ticks_usec()
	var framed_wait := 0
	while not _framed(point) and framed_wait < 3000:
		framed_wait += 1
		await process_frame
	var resident := Time.get_ticks_usec()
	_bind(point)
	var bound := Time.get_ticks_usec()
	if rendered:
		await RenderingServer.frame_post_draw
	else:
		await process_frame
	var drawn := Time.get_ticks_usec()
	var standing := 0
	for attempt: int in 240:
		await physics_frame
		standing = standing + 1 if _ground(point) else 0
		if standing >= 3:
			break
	var ready := Time.get_ticks_usec()
	var row := {"kind": kind, "from": from, "to": to, "kept": not kept.is_empty(),
		"cache_status": str(loader.cache_status), "loaded_by_adoption": loader.loaded_by_adoption,
		"change_call_ms": float(loaded - began) / 1000.0,
		"until_framed_ms": float(resident - began) / 1000.0,
		"binding_ms": float(bound - resident) / 1000.0,
		"through_first_draw_ms": float(drawn - began) / 1000.0,
		"first_ready_ms": float(ready - began) / 1000.0,
		"grounded": standing >= 3,
		"load_phases_us": loader.load_phases.duplicate()}
	transitions.append(row)
	_check(loader.world_root != null and loader.manifest != null and loader.manifest.asset_id() == to,
		"%s: %s is the bound world" % [kind, to])
	_check(standing >= 3, "%s: three grounded physics frames at the arrival" % kind, point)
	_memory(kind)
	print("LANDFALL_TOWN_PARK transition ", JSON.stringify(row))
	return row

func _run() -> void:
	rendered = DisplayServer.get_name() != "headless"
	var interior := _argument("--interior", "landfall_town")
	var report_path := _argument("--report", "user://landfall_town_park.json")
	_check(preload("res://src/world/gltf_quantization.gd").ensure_registered()
		and preload("res://src/world/vram_textures.gd").ensure_registered()
		and preload("res://src/world/map_mesh_extension.gd").ensure_registered(),
		"main-thread glTF extensions are registered")
	registry = (JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")) as Dictionary).get("maps", {})
	var exterior_entry := MapRegistry.resolve(registry, EXTERIOR)
	var interior_entry := MapRegistry.resolve(registry, interior)
	var exterior_path := ProjectSettings.globalize_path(str(exterior_entry.get("manifest", "")))
	var interior_path := ProjectSettings.globalize_path(str(interior_entry.get("manifest", "")))
	_check(FileAccess.file_exists(exterior_path), "the Landfall package is on disk", exterior_path)
	_check(FileAccess.file_exists(interior_path), "the interior package is on disk", interior_path)
	if not FileAccess.file_exists(exterior_path) or not FileAccess.file_exists(interior_path):
		await _finish(report_path, interior)
		return
	stage = Node3D.new()
	root.add_child(stage)
	rig = Rig.instantiate()
	stage.add_child(rig)
	environment = WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	sun = DirectionalLight3D.new()
	stage.add_child(sun)
	loader = WorldLoader.new()
	stage.add_child(loader)
	park = WorldParkScript.new()
	park.name = "WorldPark"
	root.add_child(park)
	park.configure(registry)
	park.enabled = true
	if OS.get_cmdline_user_args().has("--park-held"):
		park.held_interiors = {}
	_check(park.parent_of(interior) == EXTERIOR, "the interior's parent is Landfall", park.parent_of(interior))
	# The door: its exterior return tile and the interior's exit tile, from the
	# interior's own portal rows (one object id serves both ends).
	var interior_manifest := WorldManifest.load_file(interior_path)
	var door := int(_argument("--door", "-1"))
	var exterior_tile := Vector2i(-1, -1)
	var interior_tile := Vector2i(-1, -1)
	for value: Variant in interior_manifest.data.get("portals", []) as Array:
		var portal: Dictionary = value
		if MapRegistry.normalize_server_map_id(str(portal.get("destinationMap", ""))) != EXTERIOR:
			continue
		if door >= 0 and int(portal.get("objectId", -1)) != door:
			continue
		door = int(portal.objectId)
		exterior_tile = Vector2i(int(portal.destinationTile[0]), int(portal.destinationTile[1]))
		interior_tile = Vector2i(int(portal.serverTile[0]), int(portal.serverTile[1]))
		break
	_check(door >= 0, "the interior has a door onto Landfall", door)
	if door < 0:
		await _finish(report_path, interior)
		return
	var exterior_adapter := CoordinateAdapter.new(exterior_entry.get("coordinateTransform", {}))
	var interior_adapter := CoordinateAdapter.new(interior_entry.get("coordinateTransform", {}))
	var outside := exterior_adapter.tile_center(exterior_tile.x, exterior_tile.y)
	var inside := interior_adapter.tile_center(interior_tile.x, interior_tile.y)
	_memory("start")

	# 1. Landfall, cold, standing at the door.
	await _change("exterior_cold", "", EXTERIOR, exterior_path, outside)
	_check(loader.world_root is ContinentChunkStream, "Landfall streams in chunks")
	# Let Landfall's own streaming settle, so the frames timed below are the
	# preload's and not the territory's late cells.
	var quiet := 0
	var settle_began := Time.get_ticks_msec()
	while quiet < 60 and Time.get_ticks_msec() - settle_began < 30000:
		await process_frame
		var stream := loader.world_root as ContinentChunkStream
		quiet = quiet + 1 if stream == null or stream.can_retire() else 0

	# 2. Walking up to the door: the interior builds in the background. The
	# main thread's frames are timed while it does.
	_check(park.bind_map(EXTERIOR) >= 1 or not bool(interior_entry.get("preloadOnApproach", false)),
		"the door is indexed on Landfall when the interior is flagged", park.doors())
	var approach := exterior_tile + Vector2i(0, 10)
	park.observe(EXTERIOR, approach, {})
	if park.preload_state(interior).is_empty():
		# An interior not flagged (the underground) is preloaded on request.
		park.start_preload(interior, door, 10.0)
	_check(not park.preload_state(interior).is_empty(), "approaching the door starts the preload")
	var frame_ms: Array = []
	var last := Time.get_ticks_usec()
	var preload_began := last
	while park.preload_state(interior) != "ready" and Time.get_ticks_usec() - preload_began < 120000000:
		await process_frame
		var now := Time.get_ticks_usec()
		frame_ms.append(float(now - last) / 1000.0)
		last = now
	var preload_ms := float(Time.get_ticks_usec() - preload_began) / 1000.0
	_check(park.preload_state(interior) == "ready", "the preload is ready", preload_ms)
	var ready_event: Dictionary = {}
	for event: Dictionary in park.events:
		if str(event.event) == "preload_ready":
			ready_event = event
	var worst := 0.0
	var hitches := 0
	for value: float in frame_ms:
		worst = maxf(worst, value)
		hitches += 1 if value > HITCH_MSEC else 0
	_check(float(ready_event.get("max_slice_ms", 999.0)) < HITCH_MSEC,
		"no preload slice holds the main thread for 50 ms", ready_event)
	_check(not rendered or hitches == 0, "no frame over 50 ms while the preload ran",
		{"worst_ms": worst, "frames": frame_ms.size(), "over_50ms": hitches})
	_memory("interior_preloaded_ready")

	# 3. Through the door: the preloaded Town, Landfall parked.
	var entered: Dictionary = await _change("interior_preloaded", EXTERIOR, interior, interior_path, inside)
	_check(bool(entered.kept) and park.has_parked(EXTERIOR), "the preload is taken and Landfall is parked")
	_check(int(park.counters.preload_hit) == 1, "one preload hit", park.counters)
	var scenery := loader.world_root.get_node_or_null(preload("res://src/world/underground_scenery.gd").NODE_NAME)
	var config := preload("res://src/world/underground_scenery.gd").config_for(interior)
	_check(config.is_empty() or (scenery != null and scenery.get_child_count() == (config.get("placements", []) as Array).size()),
		"every scenery placement stands in the preloaded interior",
		{"placed": scenery.get_child_count() if scenery != null else 0,
			"listed": (config.get("placements", []) as Array).size()})

	# 4. Back out: Landfall re-attached, the Town parked.
	var returned: Dictionary = await _change("exterior_parked", interior, EXTERIOR, exterior_path, outside)
	_check(bool(returned.kept) and park.has_parked(interior), "Landfall comes back parked and the Town is kept")

	# 5. In again: the parked Town.
	var again: Dictionary = await _change("interior_parked", EXTERIOR, interior, interior_path, inside)
	_check(bool(again.kept), "the Town comes back parked")
	_check(float(again.first_ready_ms) < float(entered.first_ready_ms) * 1.5 + 50.0,
		"a parked re-entry is no slower than the preloaded entry", [again.first_ready_ms, entered.first_ready_ms])

	# 6. For comparison, the Town cold: back out, drop everything kept, empty
	# the scenery cache, and load the Town from its package.
	await _change("exterior_parked_again", interior, EXTERIOR, exterior_path, outside)
	park.clear()
	while park.retiring_count() > 0:
		await process_frame
	park.enabled = false
	GlbSceneCache.clear()
	_memory("before_interior_cold")
	var cold: Dictionary = await _change("interior_cold", EXTERIOR, interior, interior_path, inside)
	_check(not bool(cold.kept), "the cold load reads the package")
	_check(float(entered.first_ready_ms) < float(cold.first_ready_ms),
		"the preloaded entry is ready sooner than the cold load", [entered.first_ready_ms, cold.first_ready_ms])
	_check(float(returned.first_ready_ms) < float(transitions[0].first_ready_ms),
		"the parked return to Landfall is ready sooner than its cold load",
		[returned.first_ready_ms, transitions[0].first_ready_ms])
	await _finish(report_path, interior, {"preload_ms": preload_ms, "preload_frames_ms": frame_ms,
		"preload_ready_event": ready_event, "worst_preload_frame_ms": worst, "preload_hitches": hitches})

func _finish(report_path: String, interior: String, extra := {}) -> void:
	var park_events: Array = park.events.duplicate() if is_instance_valid(park) else []
	var park_counters: Dictionary = park.counters.duplicate() if is_instance_valid(park) else {}
	if is_instance_valid(park):
		park.enabled = true
		park.clear()
		await ContinentChunkStream.drain_workers(self)
		while not park.is_idle():
			await process_frame
		park.release_now()
	sections.reset()
	cutaway.reset()
	if is_instance_valid(loader):
		loader.unload_world()
	await ContinentChunkStream.drain_workers(self)
	GlbSceneCache.clear()
	if is_instance_valid(stage):
		stage.queue_free()
	if is_instance_valid(park):
		park.queue_free()
	for frame: int in 15:
		await process_frame
	preload("res://src/world/look/look_ground.gd")._class_textures.clear()
	var ok := true
	for check: Dictionary in checks:
		ok = ok and bool(check.ok)
	var report := {"ok": ok, "interior": interior, "rendered": rendered,
		"scope": "WorldLoader + WorldPark + environment/camera/section/cutaway controllers; no Main, network, avatar, occluder fade or curtain. Time to ready = change call + framing + binding + first draw + three grounded physics frames. The cold interior runs last with GlbSceneCache emptied but OS/driver caches warm.",
		"engine": Engine.get_version_info(), "checks": checks, "transitions": transitions,
		"memory": memory, "park_events": park_events, "park_counters": park_counters}
	report.merge(extra)
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "  "))
		file.close()
	print("LANDFALL_TOWN_PARK report ", ProjectSettings.globalize_path(report_path))
	print("LANDFALL_TOWN_PARK DONE ", "PASS" if ok else "FAIL")
	quit(0 if ok else 1)
