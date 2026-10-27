extends Node
## Keeps worlds in memory across a building's door, and builds the building
## before the player reaches it.
##
## Parking. Entering an interior from the map it belongs to (its parent:
## registry `interiorOf`/`parentRegion`, or the manifest's
## `asset.parentRegion`) keeps that map's world: `leave` takes the tree from
## the WorldLoader with `release_world`, detached and not freed, and `take`
## hands it back for `WorldLoader.adopt_world` on the way out. Detached, a
## parked tree draws nothing, collides with nothing, processes nothing and is
## outside every walk of the live scene (SecretSections, the cutaway, groups);
## a continent territory's chunk stream pauses itself on leaving the tree
## (ContinentChunkStream._exit_tree) and resumes on re-entering it, with all
## its cells still resident. Leaving the interior for its parent parks the
## interior the same way, so going back and forth costs a re-attach both ways.
## Actors, ground bags and map objects are not parked: they belong to the
## server's session, which sends them again after every CHANGE_MAP
## (KILL_ALL_ACTORS, actors, NPCs, map objects; eloria/world.py _change_map).
##
## Preloading. On a map with doors into an interior flagged
## `preloadOnApproach` in the registry, walking within
## WorldParkPolicy.PRELOAD_RADIUS_TILES of one starts that interior's world on
## a worker (WorldLoader.prepare_detached: manifest, package, collision,
## materials and the scenery's models, all off the tree), then publishes it on
## the main thread in slices of at most `preload_slice_usec`: the worker's
## tree is released, the prepared models are installed one at a time and the
## placed scenery is instanced under the still-detached root
## (interior_scenery_stepper.gd). The map change then adopts it (`take`).
## A preload starts only once the player's own arrival on the map has loaded
## (`observe`'s `settled`), so it never competes with the arrival's chunks.
##
## Shader keys. A preload must not compile shaders on the main thread mid-walk
## (a new material key costs one 70 ms frame cold): binding the parent builds
## and holds every key the interior's shell binds, behind the arrival curtain
## (interior_material_warmup.gd).
##
## Memory. An interior is estimated from its textures, shell and scenery:
## each image's pixels from its header, or its VRAM sidecar's size when the
## client uploads that instead (texture_footprint.gd). Read on a small worker
## when the parent binds; a preload waits for it, and the estimate travels
## with the built world.
##
## Policy, limits and eviction rules: world_park_policy.gd. Every park,
## re-attach, preload start/ready/hit/miss/drop and eviction prints one
## `world_park {...}` line with its timings and is kept in `events`.
## ELORIA_WORLD_PARK=0 turns all of this off (every map change loads cold).
const Policy := preload("res://src/world/world_park_policy.gd")
const SceneryStepper := preload("res://src/world/interior_scenery_stepper.gd")
const UndergroundScenery := preload("res://src/world/underground_scenery.gd")
const ResourceAdmission := preload("res://src/runtime/resource_admission.gd")
const RetirementBudget := preload("res://src/world/resource_retirement_budget.gd")
const MaterialWarmup := preload("res://src/world/interior_material_warmup.gd")
const TextureFootprint := preload("res://src/world/texture_footprint.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")

## Main-thread microseconds a preload may spend publishing in one frame.
const PUBLISH_SLICE_USEC := 4000
## Freeing an evicted tree: nodes and microseconds per frame (shared with the
## streams' retirements through RetirementBudget).
const RETIRE_NODES_PER_FRAME := 64
const RETIRE_BUDGET_USEC := 2000
const SWITCH_ENVIRONMENT := "ELORIA_WORLD_PARK"
const WARMUP_ENVIRONMENT := "ELORIA_INTERIOR_WARMUP"
const EVENT_LIMIT := 100

## The map registry (data/maps/registry.json `maps`).
var registry: Dictionary = {}
var enabled := true
## Interiors whose parking is held (WorldParkPolicy.HELD_INTERIORS).
var held_interiors: Dictionary = Policy.HELD_INTERIORS.duplicate()
var budget_bytes := Policy.BUDGET_BYTES
var preload_slice_usec := PUBLISH_SLICE_USEC
## Build a flagged interior's shader keys when its parent binds
## (ELORIA_INTERIOR_WARMUP=0 turns it off, for measuring).
var warm_materials := true
## The worker's entry point: (path, cache_enabled, visual_paths) -> WorldLoader.
## Tests substitute a builder that needs no package on disk.
var prepare_function: Callable = WorldLoader.prepare_detached
## A test's clock in milliseconds; negative uses the engine's.
var now_override := -1
var events: Array[Dictionary] = []
var counters := {"park": 0, "unpark": 0, "evict": 0, "preload_start": 0,
	"preload_ready": 0, "preload_hit": 0, "preload_miss": 0, "preload_drop": 0, "refresh": 0}

## map id -> {"resident": Dictionary, "at_msec": int, "bytes": int}
var _parked: Dictionary = {}
## The interior building in the background: {} or {"map", "path", "state"
## ("running" | "publishing" | "ready"), "thread", "resident", "stepper",
## "started_usec", "worker_usec", "publish_usec", "max_slice_usec",
## "far_since_msec", "ready_msec", "bytes", "door"}.
var _preload: Dictionary = {}
## Workers whose result nobody wants any more: reaped once they finish, never
## joined while running (a worker may wait on the main thread).
var _orphans: Array[Dictionary] = []
## Evicted trees, freed a slice at a time: {"map", "reason", "stack", "freed"}.
var _retiring: Array[Dictionary] = []
var _draining := false
var _parents: Dictionary = {}
var _parent_pattern: RegEx
## The map whose doors are indexed, its door object ids -> interior map id,
## and each door's fallback tile (the interior manifest's return tile).
var _bound_map := ""
var _doors: Dictionary = {}
var _door_tiles: Dictionary = {}
## interior map id -> {object id: return tile} read from its manifest, and
## its scenery's model paths; read once a session.
var _portal_index: Dictionary = {}
## interior map id -> the materials holding its shell's shader keys for the
## session (_warm_interior).
var _warmed: Dictionary = {}
var _scenery_configs: Dictionary = {}
var _scenery_paths: Dictionary = {}
## interior map id -> its estimated bytes once built (textures by their
## headers or sidecars, the shell GLB, a floor); read once a session.
var _interior_bytes: Dictionary = {}
## interior map id -> {"thread", "began_usec"}: estimates still being read.
var _estimating: Dictionary = {}
## Interiors a kept build of expired while the player stood by: not preloaded
## again until the player has walked away from their doors.
var _stale: Dictionary = {}
var _retry_at: Dictionary = {}
var _waiting_since := -1
## The destination `take` last handed a world for (a preload hit's map).
var _last_taken := ""

func configure(maps: Dictionary) -> void:
	registry = maps
	enabled = OS.get_environment(SWITCH_ENVIRONMENT) != "0"
	warm_materials = OS.get_environment(WARMUP_ENVIRONMENT) != "0"
	_parents.clear()
	_portal_index.clear()
	_scenery_configs.clear()
	_scenery_paths.clear()
	_interior_bytes.clear()
	_stale.clear()

func _now() -> int:
	return now_override if now_override >= 0 else Time.get_ticks_msec()

# --------------------------------------------------------------------------
# Relations
# --------------------------------------------------------------------------

## The map `map_id` is an interior of, or "". Only continent-v2 rows: the
## registry's `parentRegion` or `interiorOf`, else the manifest's
## `asset.parentRegion` for an interior row (read once, by text, not parsed).
func parent_of(map_id: String) -> String:
	map_id = MapRegistry.normalize_server_map_id(map_id)
	if map_id.is_empty():
		return ""
	if _parents.has(map_id):
		return str(_parents[map_id])
	var parent := ""
	var entry := MapRegistry.resolve(registry, map_id)
	var status := str(entry.get("status", ""))
	if status.begins_with("continent-v2"):
		for key: String in ["parentRegion", "interiorOf", "insidesOf"]:
			if not str(entry.get(key, "")).is_empty():
				parent = MapRegistry.normalize_server_map_id(str(entry[key]))
				break
		if parent.is_empty() and status.contains("interior"):
			parent = _manifest_parent(ProjectSettings.globalize_path(str(entry.get("manifest", ""))))
	_parents[map_id] = parent
	return parent

func _manifest_parent(path: String) -> String:
	if path.is_empty() or not FileAccess.file_exists(path):
		return ""
	if _parent_pattern == null:
		_parent_pattern = RegEx.new()
		_parent_pattern.compile("\"parentRegion\"\\s*:\\s*\"([^\"]*)\"")
	var found := _parent_pattern.search(FileAccess.get_file_as_string(path))
	return MapRegistry.normalize_server_map_id(found.get_string(1)) if found != null else ""

func _relations(from: String, to: String) -> Dictionary:
	return {from: parent_of(from), to: parent_of(to)}

func _flagged(map_id: String) -> bool:
	return bool(MapRegistry.resolve(registry, map_id).get("preloadOnApproach", false))

func has_parked(map_id: String) -> bool:
	return _parked.has(MapRegistry.normalize_server_map_id(map_id))

func parked_maps() -> Array:
	return _parked.keys()

func preload_state(map_id := "") -> String:
	if _preload.is_empty() or (not map_id.is_empty() and str(_preload.map) != map_id):
		return ""
	return str(_preload.state)

# --------------------------------------------------------------------------
# Doors
# --------------------------------------------------------------------------

## Indexes the doors on `map_id` that lead into a flagged interior of it.
## Called once a map is bound (Main._on_world_loaded): reads each such
## interior's manifest portals and scenery list the first time only.
func bind_map(map_id: String) -> int:
	_bound_map = MapRegistry.normalize_server_map_id(map_id)
	_doors.clear()
	_door_tiles.clear()
	if not enabled or _bound_map.is_empty():
		return 0
	for key: Variant in registry:
		var entry: Variant = registry[key]
		if entry is not Dictionary or not bool((entry as Dictionary).get("preloadOnApproach", false)):
			continue
		var interior := MapRegistry.normalize_server_map_id(str(key))
		if parent_of(interior) != _bound_map:
			continue
		if not _portal_index.has(interior):
			var manifest := _read_manifest(entry as Dictionary)
			_portal_index[interior] = _portals_of(interior, manifest)
			_read_scenery(interior)
			_warm_interior(interior, manifest)
			_estimate_interior(interior, manifest)
		var portals: Dictionary = _portal_index[interior]
		for object_id: int in (portals.get(_bound_map, {}) as Dictionary):
			_doors[object_id] = interior
			_door_tiles[object_id] = (portals[_bound_map] as Dictionary)[object_id]
	# An interior entered without its parent bound first (signing in inside
	# it) is estimated on its own load frame, for parking it on the way out.
	if _flagged(_bound_map) and not _interior_bytes.has(_bound_map):
		if not _scenery_paths.has(_bound_map):
			_read_scenery(_bound_map)
		_estimate_interior(_bound_map, _read_manifest(MapRegistry.resolve(registry, _bound_map)))
	return _doors.size()

## An interior's manifest, parsed, with its own path under "_path"; {} when
## it is missing or unreadable.
static func _read_manifest(entry: Dictionary) -> Dictionary:
	var path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if parsed is not Dictionary:
		return {}
	(parsed as Dictionary)["_path"] = path
	return parsed

## {exterior map id: {object id: Vector2i return tile}} from an interior's
## manifest `portals` (its exits name the exterior map they lead to; one object
## id serves a door's two ends).
static func _portals_of(interior: String, manifest: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for value: Variant in manifest.get("portals", []) as Array:
		if value is not Dictionary:
			continue
		var portal := value as Dictionary
		var destination := MapRegistry.normalize_server_map_id(str(portal.get("destinationMap", "")))
		var identity: Variant = portal.get("objectId")
		if destination.is_empty() or destination == interior or (identity is not int and identity is not float):
			continue
		var tile: Variant = portal.get("destinationTile", [])
		if not result.has(destination):
			result[destination] = {}
		(result[destination] as Dictionary)[int(identity)] = Vector2i(int(tile[0]), int(tile[1])) \
			if tile is Array and (tile as Array).size() >= 2 else Vector2i(-100000, -100000)
	return result

## Builds the shader of every material key the interior's shell binds, on
## the parent's map-load frame (bind_map: behind the arrival curtain), and
## holds one material per key for the session, so the preload's worker shares
## those shaders instead of compiling them mid-walk
## (interior_material_warmup.gd has the measurements).
func _warm_interior(interior: String, manifest: Dictionary) -> void:
	if not warm_materials or _warmed.has(interior) or manifest.is_empty():
		return
	var relative := str((manifest.get("asset", {}) as Dictionary).get("glb", "")) \
		if manifest.get("asset") is Dictionary else ""
	if relative.is_empty():
		return
	var result := MaterialWarmup.warm(str(manifest._path).get_base_dir().path_join(relative))
	_warmed[interior] = result.materials
	_record("warm", interior, {"keys": int(result.keys), "materials": (result.materials as Array).size(),
		"warm_ms": float(result.usec) / 1000.0, "error": str(result.error)})

## Starts reading an interior's estimated bytes once built (once a session,
## from bind_map): the shell GLB's images and every scenery model's, each
## image counted once, plus the shell's geometry and a floor
## (WorldParkPolicy.interior_estimate). The files are read and the embedded
## images hashed (to find their sidecars) on a worker: ~20 MB for the Town.
func _estimate_interior(interior: String, manifest: Dictionary) -> void:
	if _interior_bytes.has(interior) or _estimating.has(interior) or manifest.is_empty() \
			or manifest.get("asset") is not Dictionary:
		return
	var glb := str(manifest._path).get_base_dir().path_join(str((manifest.asset as Dictionary).get("glb", "world.glb")))
	var sources := PackedStringArray()
	for source: String in _scenery_paths.get(interior, PackedStringArray()) as PackedStringArray:
		sources.append(ProjectSettings.globalize_path(source))
	# Asked on the main thread first: a worker asking first is told none.
	VramTextures.usable_formats()
	var began := Time.get_ticks_usec()
	var thread := Thread.new()
	if thread.start(_measure.bind(glb, sources)) != OK:
		_store_estimate(interior, _measure(glb, sources), began)
		return
	_estimating[interior] = {"thread": thread, "began_usec": began}

## What `_estimate_interior` reads (any thread): texture, image and GLB bytes.
static func _measure(glb: String, sources: PackedStringArray) -> Dictionary:
	var seen: Dictionary = {}
	var shell := TextureFootprint.glb_texture_bytes(glb, seen)
	var scenery := 0
	for source: String in sources:
		scenery += TextureFootprint.glb_texture_bytes(source, seen)
	var file := FileAccess.open(glb, FileAccess.READ)
	return {"shell": shell, "scenery": scenery, "images": seen.size(),
		"glb_bytes": file.get_length() if file != null else 0}

func _store_estimate(interior: String, measured: Dictionary, began_usec: int) -> void:
	var textures := int(measured.get("shell", 0)) + int(measured.get("scenery", 0))
	_interior_bytes[interior] = Policy.interior_estimate(textures, int(measured.get("glb_bytes", 0))) \
		if textures > 0 else Policy.whole_map_estimate(int(measured.get("glb_bytes", 0)))
	_record("estimate", interior, {"shell_texture_mib": _mib(int(measured.get("shell", 0))),
		"scenery_texture_mib": _mib(int(measured.get("scenery", 0))),
		"estimated_mib": _mib(int(_interior_bytes[interior])), "images": int(measured.get("images", 0)),
		"read_ms": float(Time.get_ticks_usec() - began_usec) / 1000.0})

## Collects the estimates whose worker is done; with `wait`, waits for the
## rest (they read files only and never wait on the main thread).
func finish_estimates(wait := false) -> void:
	for interior: String in _estimating.keys():
		var job: Dictionary = _estimating[interior]
		var thread: Thread = job.thread
		if thread.is_alive() and not wait:
			continue
		_store_estimate(interior, thread.wait_to_finish() as Dictionary, int(job.began_usec))
		_estimating.erase(interior)

## Estimates still being read (tests, diagnostics).
func estimates_pending() -> int:
	return _estimating.size()

## An interior's scenery config and model list, read once (on a map-load
## frame, by bind_map) so no gameplay frame parses it.
func _read_scenery(interior: String) -> void:
	var config := UndergroundScenery.config_for(interior)
	_scenery_configs[interior] = config
	_scenery_paths[interior] = UndergroundScenery.asset_paths(interior, config)

## Doors indexed on the bound map: object id -> interior map id.
func doors() -> Dictionary:
	return _doors

## Each frame the player stands on `map_id` at `tile`: starts, keeps or drops
## the preload of the interior whose door is nearest. `map_objects` is the
## server's object list for the map (AppState.map_objects: id -> {x, y, ...});
## a door the server has not listed yet falls back to its return tile.
## `settled` is false while the player's arrival on the map is still loading
## (Main: the curtain is up, or the streamed cells around them are not all
## resident): nothing new starts then, so a preload never competes with the
## arrival's own chunks.
func observe(map_id: String, tile: Vector2i, map_objects: Dictionary = {}, settled := true) -> void:
	if not enabled or MapRegistry.normalize_server_map_id(map_id) != _bound_map:
		return
	var now := _now()
	var nearest: Dictionary = {}
	var nearest_door: Dictionary = {}
	for object_id: int in _doors:
		var at: Vector2i = _door_tiles[object_id]
		var listed: Variant = map_objects.get(object_id)
		if listed is Dictionary:
			at = Vector2i(int((listed as Dictionary).get("x", at.x)), int((listed as Dictionary).get("y", at.y)))
		var interior := str(_doors[object_id])
		var distance := Policy.tile_distance(tile, at)
		if distance < float(nearest.get(interior, INF)):
			nearest[interior] = distance
			nearest_door[interior] = object_id
	for interior: String in nearest:
		if _parked.has(interior):
			# A parked interior is the preload already done. Standing near does
			# not keep it: it expires as any parked world does (then is stale).
			continue
		if not _preload.is_empty() and str(_preload.map) != interior:
			continue # One preload at a time; the other is judged below.
		_judge_preload(interior, float(nearest[interior]), int(nearest_door[interior]), now, settled)
	if not _preload.is_empty() and not nearest.has(str(_preload.map)):
		_judge_preload(str(_preload.map), INF, -1, now, settled)

func _judge_preload(interior: String, distance: float, door: int, now: int, settled := true) -> void:
	var state := {"active": not _preload.is_empty(),
		"far_since_msec": int(_preload.get("far_since_msec", -1)),
		"retry_at_msec": int(_retry_at.get(interior, 0)),
		"stale": _stale.has(interior), "settled": settled}
	if _estimating.has(interior):
		# Its size is still being read: nothing starts before the budget knows it.
		state["settled"] = false
	var action := Policy.preload_action(state, distance, now)
	if not _preload.is_empty():
		_preload["far_since_msec"] = int(state.far_since_msec)
	if not bool(state.stale) and _stale.has(interior):
		_stale.erase(interior)
		_record("stale_cleared", interior, {"distance_tiles": snappedf(distance, 0.1)})
	if action == "start":
		start_preload(interior, door, distance)
	elif action == "drop":
		_drop_preload("far")

# --------------------------------------------------------------------------
# Preloading
# --------------------------------------------------------------------------

## Starts building `interior` on a worker. Returns false when it cannot start
## (no package, a thread error, a preload already running).
func start_preload(interior: String, door := -1, distance := INF) -> bool:
	interior = MapRegistry.normalize_server_map_id(interior)
	if not _preload.is_empty() or _parked.has(interior):
		return false
	var entry := MapRegistry.resolve(registry, interior)
	var path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	if path.is_empty() or not FileAccess.file_exists(path):
		_retry_at[interior] = _now() + Policy.PRELOAD_RETRY_MSEC
		_record("preload_skip", interior, {"reason": "package_missing"})
		return false
	if _estimating.has(interior):
		finish_estimates(true)
	var bytes := int(_interior_bytes.get(interior, _estimate_package(path)))
	var parked_rows := {}
	for map_id: String in _parked:
		parked_rows[map_id] = {"at_msec": int(_parked[map_id].at_msec), "bytes": int(_parked[map_id].bytes)}
	for map_id: String in Policy.over_budget(parked_rows, bytes, budget_bytes):
		_evict(map_id, "budget")
	if not _scenery_paths.has(interior):
		_read_scenery(interior)
	var visuals := GlbSceneCache.missing(_scenery_paths[interior] as PackedStringArray)
	var thread := Thread.new()
	var error := thread.start(prepare_function.bind(path, MapSceneCache.is_enabled(), visuals))
	if error != OK:
		_retry_at[interior] = _now() + Policy.PRELOAD_RETRY_MSEC
		_record("preload_failed", interior, {"error": error_string(error)})
		return false
	_preload = {"map": interior, "path": path, "state": "running", "thread": thread,
		"started_usec": Time.get_ticks_usec(), "worker_usec": 0, "publish_usec": 0,
		"max_slice_usec": 0, "slices": 0, "far_since_msec": -1, "ready_msec": -1,
		"bytes": bytes, "door": door}
	counters.preload_start += 1
	_record("preload_start", interior, {"door": door, "distance_tiles": snappedf(distance, 0.1),
		"models_to_prepare": visuals.size(), "estimated_mib": _mib(bytes)})
	return true

## Collects a finished worker's world, on the main thread. `force` publishes
## even when ResourceAdmission has already granted this frame's publication
## (a map change is waiting for it).
func _poll_preload(force := false) -> void:
	if _preload.is_empty() or str(_preload.state) != "running":
		return
	var thread: Thread = _preload.thread
	if thread == null or thread.is_alive():
		return
	if not force and not ResourceAdmission.can_publish():
		return
	var began := Time.get_ticks_usec()
	var builder := thread.wait_to_finish() as WorldLoader
	_preload.thread = null
	_preload.worker_usec = began - int(_preload.started_usec)
	var interior := str(_preload.map)
	if builder == null:
		_fail_preload("builder_missing")
		return
	var resident := builder.release_world(true, true)
	builder.free()
	var root := resident.get("root") as Node3D
	if root == null:
		_fail_preload("load_failed")
		return
	var visuals: Dictionary = resident.get("visuals", {})
	resident["visuals"] = {}
	_preload.resident = resident
	if bool(resident.get("scenery_pending", false)):
		resident["scenery_pending"] = false
		_preload.stepper = SceneryStepper.new(interior, root, visuals,
			_scenery_configs.get(interior, {}) as Dictionary)
		_preload.state = "publishing"
	else:
		# No scenery to lay: hand any prepared models to the adopter.
		resident["visuals"] = visuals
		_preload.state = "ready"
	var spent := Time.get_ticks_usec() - began
	_preload.publish_usec = int(_preload.publish_usec) + spent
	_preload.max_slice_usec = maxi(int(_preload.max_slice_usec), spent)
	_preload.slices = int(_preload.slices) + 1
	if str(_preload.state) == "ready":
		_ready_preload()

## One slice of the publication (all of it when `budget_usec` is 0).
func _publish_slice(budget_usec: int) -> void:
	if _preload.is_empty() or str(_preload.state) != "publishing":
		return
	var stepper: SceneryStepper = _preload.stepper
	var began := Time.get_ticks_usec()
	var done: bool = stepper.step(budget_usec)
	var spent := Time.get_ticks_usec() - began
	_preload.publish_usec = int(_preload.publish_usec) + spent
	_preload.max_slice_usec = maxi(int(_preload.max_slice_usec), spent)
	_preload.slices = int(_preload.slices) + 1
	if done:
		_preload.state = "ready"
		_ready_preload()

func _ready_preload() -> void:
	counters.preload_ready += 1
	_preload.ready_msec = _now()
	# The estimate travels with the world, for parking it later.
	(_preload.resident as Dictionary)["park_bytes"] = int(_preload.bytes)
	var stepper: SceneryStepper = _preload.get("stepper")
	_record("preload_ready", str(_preload.map), {
		"worker_ms": float(_preload.worker_usec) / 1000.0,
		"publish_ms": float(_preload.publish_usec) / 1000.0,
		"max_slice_ms": float(_preload.max_slice_usec) / 1000.0,
		"slices": int(_preload.slices),
		"placements": int(stepper.count) if stepper != null else 0,
		"placements_failed": int(stepper.failed) if stepper != null else 0,
		"cache": str((_preload.resident as Dictionary).get("cache_status", ""))})

func _fail_preload(reason: String) -> void:
	var interior := str(_preload.map)
	_retry_at[interior] = _now() + Policy.PRELOAD_RETRY_MSEC
	_record("preload_failed", interior, {"reason": reason})
	_preload = {}

func _drop_preload(reason: String) -> void:
	if _preload.is_empty():
		return
	var interior := str(_preload.map)
	var thread: Thread = _preload.get("thread")
	if thread != null:
		if thread.is_alive():
			_orphans.append({"thread": thread, "map": interior})
		else:
			_discard_builder(thread.wait_to_finish() as WorldLoader, interior)
	var resident: Dictionary = _preload.get("resident", {})
	if not resident.is_empty():
		(resident.get("visuals", {}) as Dictionary).clear()
		_retire_tree(resident.get("root") as Node3D, interior, "preload_" + reason)
	counters.preload_drop += 1
	_record("preload_drop", interior, {"reason": reason, "state": str(_preload.state)})
	_preload = {}
	_waiting_since = -1

func _discard_builder(builder: WorldLoader, map_id: String) -> void:
	if builder == null:
		return
	var resident := builder.release_world(true, false)
	builder.free()
	(resident.get("visuals", {}) as Dictionary).clear()
	_retire_tree(resident.get("root") as Node3D, map_id, "orphan")

func _reap_orphans() -> void:
	var remaining: Array[Dictionary] = []
	for orphan: Dictionary in _orphans:
		var thread: Thread = orphan.thread
		if thread.is_alive():
			remaining.append(orphan)
			continue
		_discard_builder(thread.wait_to_finish() as WorldLoader, str(orphan.map))
	_orphans = remaining

# --------------------------------------------------------------------------
# The map change
# --------------------------------------------------------------------------

## The world kept for `map_id` - parked, or preloaded and published - for
## WorldLoader.adopt_world, or {} when there is none ready. A preload still
## publishing is finished here, in one go; one whose worker is still running
## is not ready (see `should_wait`).
func take(map_id: String) -> Dictionary:
	map_id = MapRegistry.normalize_server_map_id(map_id)
	_last_taken = ""
	if not enabled:
		return {}
	if _parked.has(map_id):
		var row: Dictionary = _parked[map_id]
		_parked.erase(map_id)
		counters.unpark += 1
		_last_taken = map_id
		_record("unpark", map_id, {"parked_s": float(_now() - int(row.at_msec)) / 1000.0})
		return row.resident
	if _preload.is_empty() or str(_preload.map) != map_id:
		return {}
	_poll_preload(true)
	if _preload.is_empty():
		return {}
	var state_at_take := str(_preload.state)
	var began := Time.get_ticks_usec()
	if state_at_take == "publishing":
		_publish_slice(0)
	if str(_preload.state) != "ready":
		return {}
	var resident: Dictionary = _preload.resident
	counters.preload_hit += 1
	_last_taken = map_id
	_record("preload_hit", map_id, {"state": state_at_take,
		"finish_ms": float(Time.get_ticks_usec() - began) / 1000.0,
		"waited_ms": float(_now() - _waiting_since) if _waiting_since >= 0 else 0.0})
	_preload = {}
	_waiting_since = -1
	return resident

## Whether the map change to `map_id` should wait (behind the curtain) for a
## preload whose worker is still running. False once it is ready - `take` then
## hands it over - or after WorldParkPolicy.PRELOAD_WAIT_LIMIT_MSEC.
func should_wait(map_id: String) -> bool:
	map_id = MapRegistry.normalize_server_map_id(map_id)
	if not enabled or _preload.is_empty() or str(_preload.map) != map_id:
		_waiting_since = -1
		return false
	# Not collected here: a worker that finished since the caller's `take` is
	# waited for one more frame, and the next `take` collects and hands it over.
	if str(_preload.state) != "running":
		return false
	var now := _now()
	if _waiting_since < 0:
		_waiting_since = now
		_record("preload_wait", map_id, {})
	if now - _waiting_since > Policy.PRELOAD_WAIT_LIMIT_MSEC:
		_record("preload_wait_timeout", map_id, {"waited_ms": now - _waiting_since})
		return false
	return true

## The map change from `from` to `to` is happening now, before the new world
## is adopted or loaded: evicts what this travel ends, and parks the world
## `loader` holds when the policy keeps it (WorldParkPolicy.should_park).
## `loader` is null when the world was already handed elsewhere (a seamless
## crossing). Returns true when the world was parked.
func leave(loader: WorldLoader, from: String, to: String) -> bool:
	from = MapRegistry.normalize_server_map_id(from)
	to = MapRegistry.normalize_server_map_id(to)
	var kept_destination := _last_taken == to
	_last_taken = ""
	_bound_map = ""
	_doors.clear()
	_door_tiles.clear()
	for map_id: String in Policy.evicted_by_travel(_parked.keys(), to):
		_evict(map_id, "travel")
	if not _preload.is_empty():
		if str(_preload.map) == to:
			counters.preload_miss += 1
			_record("preload_miss", to, {"reason": "not_ready", "state": str(_preload.state)})
			_drop_preload("superseded")
		else:
			_drop_preload("travel")
	elif enabled and not kept_destination and _flagged(to) and parent_of(to) == from and not from.is_empty():
		counters.preload_miss += 1
		_record("preload_miss", to, {"reason": "not_started"})
	if not enabled or loader == null or not is_instance_valid(loader.world_root) \
			or not Policy.should_park(from, to, _relations(from, to), held_interiors):
		return false
	var began := Time.get_ticks_usec()
	var resident := loader.release_world(true)
	var root := resident.get("root") as Node3D
	if root == null:
		return false
	var detach_usec := Time.get_ticks_usec() - began
	var bytes := _estimate_resident(resident)
	if bytes > budget_bytes:
		_retire_tree(root, from, "budget")
		_record("park_refused", from, {"into": to, "estimated_mib": _mib(bytes)})
		return false
	if _parked.has(from):
		# A world of this map already parked (one loaded again without being
		# taken back: a seamless crossing's handoff, a character intro) is
		# freed, never overwritten and leaked.
		_evict(from, "replaced")
	_parked[from] = {"resident": resident, "at_msec": _now(), "bytes": bytes}
	counters.park += 1
	_record("park", from, {"into": to, "detach_ms": float(detach_usec) / 1000.0,
		"estimated_mib": _mib(bytes), "streamed": root is ContinentChunkStream})
	return true

## Main reports how long adopting a kept world took on the map-change frame
## (re-attach plus the bind that follows it).
func note_adopted(map_id: String, usec: int) -> void:
	_record("adopted", MapRegistry.normalize_server_map_id(map_id), {"adopt_ms": float(usec) / 1000.0})

## Drops everything kept and building (logout, a closed client).
func clear() -> void:
	for map_id: String in _parked.keys():
		_evict(map_id, "clear")
	_drop_preload("clear")
	_bound_map = ""
	_doors.clear()
	_door_tiles.clear()
	_last_taken = ""

## Frees every evicted tree at once (closing the client: no frame budget then).
func release_now() -> void:
	for job: Dictionary in _retiring:
		var root: Variant = (job.stack as Array).front() if not (job.stack as Array).is_empty() else null
		if is_instance_valid(root):
			(root as Node).free()
	_retiring.clear()

## No worker is running for this park (closing waits for this).
func is_idle() -> bool:
	_reap_orphans()
	finish_estimates()
	var running: Thread = _preload.get("thread") if not _preload.is_empty() else null
	return _orphans.is_empty() and _estimating.is_empty() and (running == null or not running.is_alive())

# --------------------------------------------------------------------------
# Eviction and freeing
# --------------------------------------------------------------------------

func _evict(map_id: String, reason: String) -> void:
	if not _parked.has(map_id):
		return
	var row: Dictionary = _parked[map_id]
	_parked.erase(map_id)
	counters.evict += 1
	_record("evict", map_id, {"reason": reason, "parked_s": float(_now() - int(row.at_msec)) / 1000.0})
	_retire_tree((row.resident as Dictionary).get("root") as Node3D, map_id, reason)

## Frees a tree nobody will show again, a slice at a time. A parked tree is
## already off the tree; anything still attached is detached first.
func _retire_tree(root: Node3D, map_id: String, reason: String) -> void:
	if not is_instance_valid(root):
		return
	ResourceAdmission.retiring(root)
	if root is ContinentChunkStream:
		(root as ContinentChunkStream).pause_streaming()
	if root.get_parent() != null:
		root.get_parent().remove_child(root)
	_retiring.append({"map": map_id, "reason": reason, "stack": [root], "freed": 0,
		"began_usec": Time.get_ticks_usec()})

func _drain_retiring() -> int:
	if _retiring.is_empty() or _draining:
		return 0
	var allowance := RetirementBudget.begin_slice(self, RETIRE_NODES_PER_FRAME, RETIRE_BUDGET_USEC)
	if allowance.is_empty():
		return 0
	_draining = true
	var began := Time.get_ticks_usec()
	var freed := 0
	while not _retiring.is_empty() and freed < int(allowance.nodes) \
			and Time.get_ticks_usec() - began < int(allowance.usec):
		var job: Dictionary = _retiring[0]
		var stack: Array = job.stack
		if stack.is_empty():
			_record("retired", str(job.map), {"reason": str(job.reason), "nodes": int(job.freed),
				"seconds": float(Time.get_ticks_usec() - int(job.began_usec)) / 1000000.0})
			_retiring.pop_front()
			continue
		var node: Variant = stack.back()
		if not is_instance_valid(node):
			stack.pop_back()
		elif (node as Node).get_child_count() > 0:
			# One branch at a time, last child first (no sibling shifting).
			stack.append((node as Node).get_child((node as Node).get_child_count() - 1))
		else:
			stack.pop_back()
			(node as Node).free()
			job.freed = int(job.freed) + 1
			freed += 1
	_draining = false
	RetirementBudget.end_slice(allowance, freed, Time.get_ticks_usec() - began, not _retiring.is_empty())
	return freed

## Trees still being freed (diagnostics, tests).
func retiring_count() -> int:
	return _retiring.size()

# --------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------

func _process(_delta: float) -> void:
	tick()

## One frame's work: reaps finished orphans, collects a finished preload,
## publishes one slice, evicts what has been parked too long, frees a slice of
## evicted trees.
func tick() -> void:
	_reap_orphans()
	if not _estimating.is_empty():
		finish_estimates()
	_poll_preload()
	_publish_slice(preload_slice_usec)
	var now := _now()
	# The parent of the interior the player is in stays parked while they are
	# inside: going back out is the trip the park is for.
	var parent := parent_of(_bound_map) if enabled and not _bound_map.is_empty() else ""
	if not parent.is_empty() and _parked.has(parent):
		var row: Dictionary = _parked[parent]
		if now - int(row.at_msec) >= 1000:
			row["at_msec"] = now
			counters.refresh += 1
	if not _preload.is_empty() and str(_preload.state) == "ready" \
			and Policy.preload_expired(int(_preload.get("ready_msec", -1)), now):
		var interior := str(_preload.map)
		_drop_preload("unentered")
		_mark_stale(interior)
	for map_id: String in Policy.expired(_parked, now):
		_evict(map_id, "ttl")
		_mark_stale(map_id)
	_drain_retiring()

## A kept build of `interior` expired while the player may still stand by one
## of its doors on the bound map: it is not built again until they walk away.
func _mark_stale(interior: String) -> void:
	if _doors.values().has(interior):
		_stale[interior] = true

func _exit_tree() -> void:
	# Nothing parked survives the client; a running worker is left to finish
	# (Main._close_client waits for is_idle before quitting). An estimate's
	# worker only reads files: it is joined here.
	finish_estimates(true)
	for map_id: String in _parked.keys():
		_evict(map_id, "exit")
	if not _preload.is_empty() and _preload.get("resident") is Dictionary:
		_retire_tree((_preload.resident as Dictionary).get("root") as Node3D, str(_preload.map), "exit")
	release_now()

# --------------------------------------------------------------------------
# Estimates and records
# --------------------------------------------------------------------------

## A package's estimate from its GLB's size alone (every continent package
## names its GLB world.glb beside the manifest); the manifest itself is not
## parsed on a gameplay frame.
static func _estimate_package(manifest_path: String) -> int:
	var file := FileAccess.open(manifest_path.get_base_dir().path_join("world.glb"), FileAccess.READ)
	return Policy.whole_map_estimate(file.get_length() if file != null else 0)

## A world about to be parked: a streamed territory's own resident bytes, an
## interior's texture estimate (carried by a preloaded world, or read when its
## parent bound), else the GLB-size guess.
func _estimate_resident(resident: Dictionary) -> int:
	var root := resident.get("root") as Node3D
	if root is ContinentChunkStream:
		return int((root as ContinentChunkStream).resident_bytes)
	if resident.has("park_bytes"):
		return int(resident.park_bytes)
	var manifest := resident.get("manifest") as WorldManifest
	if manifest == null:
		return Policy.whole_map_estimate(0)
	var known: Variant = _interior_bytes.get(MapRegistry.normalize_server_map_id(manifest.asset_id()))
	if known != null:
		resident["park_bytes"] = int(known)
		return int(known)
	var file := FileAccess.open(manifest.glb_path(), FileAccess.READ)
	return Policy.whole_map_estimate(file.get_length() if file != null else 0)

static func _mib(bytes: int) -> float:
	return snappedf(float(bytes) / 1048576.0, 0.1)

func diagnostic_snapshot() -> Dictionary:
	var parked := {}
	for map_id: String in _parked:
		var row: Dictionary = _parked[map_id]
		parked[map_id] = {"parked_s": float(_now() - int(row.at_msec)) / 1000.0,
			"estimated_mib": _mib(int(row.bytes))}
	var building := {}
	if not _preload.is_empty():
		building = {"map": str(_preload.map), "state": str(_preload.state),
			"max_slice_ms": float(_preload.max_slice_usec) / 1000.0}
	var estimates := {}
	for interior: String in _interior_bytes:
		estimates[interior] = _mib(int(_interior_bytes[interior]))
	return {"enabled": enabled, "bound_map": _bound_map, "doors": _doors.size(),
		"parked": parked, "preload": building, "orphans": _orphans.size(),
		"retiring": _retiring.size(), "counters": counters.duplicate(),
		"estimated_mib": estimates, "stale": _stale.keys()}

func _record(kind: String, map_id: String, details: Dictionary) -> void:
	var event := {"event": kind, "map": map_id, "at_ms": Time.get_ticks_msec()}
	event.merge(details)
	events.append(event)
	if events.size() > EVENT_LIMIT:
		events.pop_front()
	print("world_park ", JSON.stringify(event))
