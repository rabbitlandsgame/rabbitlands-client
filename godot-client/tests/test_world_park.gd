extends SceneTree
## WorldPark (src/world/world_park.gd) and its policy, headless, with no map
## package: synthetic worlds stand in for the loader's, and an injected
## builder stands in for the worker's WorldLoader.prepare_detached.
##
##   godot --headless --path godot-client --script res://tests/test_world_park.gd
##
## Covers: the parking rules (enter/leave a parent's interior, held interiors,
## travel and TTL eviction, the memory budget), a parked world re-attached as
## the very same tree, preload start/keep/drop by distance and time, a preload
## hit (ready and still publishing), a miss, waiting on a running worker,
## sliced freeing of evicted trees, the interior scenery table, the map camera
## restore and the building door's label, ring and pick. Fix wave
## (2026-10-27): a parent kept while the player is inside its interior, a
## second park of one map frees the first, no preload before the arrival has
## loaded, the interiors' memory estimate from texture headers, pick-only
## lore objects and stair ends picked toward their stair. Polish (final
## review 2026-10-27): an unentered preload (or a parked interior) is kept
## while the player stays in its area - no timer - and let go only under
## memory-budget pressure, then built again once the player is back within
## 8 tiles of a door; no preload starts while its shell's shader keys are
## still being warmed over frames (a walk-over bind); exit labels stand at
## their door at lintel height and are lifted on screen only when they would
## fall under the bottom HUD bar.
const Policy := preload("res://src/world/world_park_policy.gd")
const WorldParkScript := preload("res://src/world/world_park.gd")
const SceneryStepper := preload("res://src/world/interior_scenery_stepper.gd")
const UndergroundScenery := preload("res://src/world/underground_scenery.gd")
const Controller := preload("res://src/camera/isometric_camera_controller.gd")
const TextureFootprint := preload("res://src/world/texture_footprint.gd")
const MaterialWarmup := preload("res://src/world/interior_material_warmup.gd")
const SCRATCH := "user://world-park-test"
const DOOR := 59201

var failures := 0
var stage: Node3D
var registry: Dictionary = {}

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func _run() -> void:
	stage = Node3D.new()
	root.add_child(stage)
	_write_fixtures()
	_test_policy()
	_test_relations()
	_test_production_relations()
	await _test_parking()
	await _test_streamed_parking()
	await _test_eviction()
	await _test_preload()
	await _test_anticipated_travel()
	await _test_wait_and_miss()
	await _test_parent_kept_inside()
	await _test_replaced_park()
	await _test_settled_and_stale()
	await _test_spread_warmup()
	_test_texture_footprint()
	_test_scenery_table()
	_test_camera_restore()
	await _test_building_doors()
	stage.queue_free()
	for frame: int in 4:
		await process_frame
	print("World park: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

func _write_fixtures() -> void:
	DirAccess.make_dir_recursive_absolute(SCRATCH.path_join("interior"))
	DirAccess.make_dir_recursive_absolute(SCRATCH.path_join("exterior"))
	var interior := {"schemaVersion": "1.0.0", "asset": {"id": "interior", "name": "Interior",
		"glb": "world.glb", "interiorClass": "insides", "parentRegion": "exterior"},
		"portals": [{"objectId": DOOR, "role": "portal", "destinationMap": "exterior",
			"destinationTile": [10, 15], "serverTile": [40, 40]},
			{"objectId": 59221, "role": "portal", "destinationMap": "interior",
			"destinationTile": [80, 80], "serverTile": [42, 42]}]}
	var file := FileAccess.open(SCRATCH.path_join("interior/world.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(interior))
	file.close()
	# A held interior whose parent is named only by its manifest.
	DirAccess.make_dir_recursive_absolute(SCRATCH.path_join("cellar"))
	file = FileAccess.open(SCRATCH.path_join("cellar/world.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"asset": {"id": "cellar", "parentRegion": "exterior"}}))
	file.close()
	registry = {
		"exterior": {"manifest": SCRATCH.path_join("exterior/world.json"), "status": "continent-v2-served"},
		"interior": {"manifest": SCRATCH.path_join("interior/world.json"),
			"status": "continent-v2-interior-served", "interiorOf": "exterior", "preloadOnApproach": true},
		"cellar": {"manifest": SCRATCH.path_join("cellar/world.json"), "status": "continent-v2-interior-served"},
		"elsewhere": {"manifest": SCRATCH.path_join("elsewhere/world.json"), "status": "continent-v2-served"},
		"legacy_insides": {"manifest": "res://nowhere.json", "status": "served", "interiorOf": "exterior"},
	}

func _park() -> Node:
	var park: Node = WorldParkScript.new()
	park.name = "WorldPark"
	stage.add_child(park)
	park.configure(registry)
	park.enabled = true
	park.prepare_function = _fake_prepare
	return park

## A loader holding a synthetic world for `map_id`, as Main's holds a map.
func _loader_with(map_id: String) -> WorldLoader:
	var loader := WorldLoader.new()
	stage.add_child(loader)
	_give_world(loader, map_id)
	return loader

func _give_world(loader: WorldLoader, map_id: String) -> Node3D:
	var world := Node3D.new()
	world.name = "ImportedWorld_" + map_id
	for index: int in 40:
		var child := Node3D.new()
		child.name = "Piece_%d" % index
		child.add_child(MeshInstance3D.new())
		world.add_child(child)
	loader.world_root = world
	loader.add_child(world)
	loader.manifest = _manifest(map_id)
	loader.coordinate_adapter = loader.manifest.coordinate_adapter()
	return world

static func _manifest(map_id: String) -> WorldManifest:
	var manifest := WorldManifest.new()
	manifest.source_path = ProjectSettings.globalize_path(SCRATCH.path_join(map_id + "/world.json"))
	manifest.data = {"asset": {"id": map_id, "glb": "world.glb"},
		"coordinateTransform": {"metresPerTile": 1.0, "serverOrigin": [0, 100], "origin": [0, 0, 0],
			"walkingHeight": 0.0, "invertServerY": true, "serverCells": [100, 100]}}
	return manifest

## The worker's stand-in: a detached builder holding a small private tree.
static func _fake_prepare(path: String, _cache_enabled: bool, _visuals: PackedStringArray) -> WorldLoader:
	OS.delay_msec(120)
	var builder := WorldLoader.new()
	builder.detached_build = true
	var world := Node3D.new()
	world.name = "ImportedWorld_interior"
	for index: int in 12:
		world.add_child(Node3D.new())
	builder.world_root = world
	builder.add_child(world)
	builder.manifest = _manifest(path.get_base_dir().get_file())
	builder.load_phases = {&"total": 120000}
	return builder

static func _slow_prepare(path: String, cache_enabled: bool, visuals: PackedStringArray) -> WorldLoader:
	OS.delay_msec(600)
	return _fake_prepare(path, cache_enabled, visuals)

func _frames(count: int) -> void:
	for frame: int in count:
		await process_frame

func _until(predicate: Callable, limit := 240) -> bool:
	for frame: int in limit:
		if predicate.call():
			return true
		await process_frame
	return predicate.call()

# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

func _test_policy() -> void:
	var parents := {"town": "landfall", "landfall_insides": "landfall"}
	_expect(Policy.relation("landfall", "town", parents) == "enter"
		and Policy.relation("town", "landfall", parents) == "leave"
		and Policy.relation("landfall", "four_gates", parents) == ""
		and Policy.relation("town", "town", parents) == ""
		and Policy.relation("", "town", parents) == "",
		"entering and leaving an interior are told apart from other travel")
	_expect(Policy.should_park("landfall", "town", parents, {})
		and Policy.should_park("town", "landfall", parents, {})
		and not Policy.should_park("landfall", "four_gates", parents, {})
		and not Policy.should_park("town", "four_gates", parents, {}),
		"the map left is parked across an interior's door, both ways, and never otherwise")
	_expect(Policy.should_park("landfall", "landfall_insides", parents)
		and Policy.should_park("landfall_insides", "landfall", parents),
		"Landfall Underground parks in both directions by default")
	_expect(not Policy.should_park("landfall", "landfall_insides", parents, {"landfall_insides": "test"}),
		"an explicit diagnostic hold still prevents parking")
	_expect(Policy.evicted_by_travel(["town"], "landfall") == ["town"]
		and Policy.evicted_by_travel(["landfall"], "landfall").is_empty(),
		"travel evicts every parked world except the destination")
	_expect(Policy.expired({"a": {"at_msec": 0}, "b": {"at_msec": 500000}}, 600001) == ["a"],
		"a world parked longer than ten minutes expires")
	var over := Policy.over_budget({"old": {"at_msec": 1, "bytes": 600}, "new": {"at_msec": 9, "bytes": 300}}, 200, 600)
	_expect(over == ["old"], "the budget evicts the oldest parked world first (%s)" % [over])
	_expect(Policy.over_budget({"a": {"at_msec": 1, "bytes": 100}}, 100, 600).is_empty(),
		"nothing is evicted inside the budget")
	var state := {"active": false, "far_since_msec": -1, "retry_at_msec": 0}
	_expect(Policy.preload_action(state, 30.0, 0) == "none"
		and Policy.preload_action(state, 24.0, 0) == "start",
		"a preload starts within 24 tiles of a door, not before")
	_expect(Policy.preload_action({"active": false, "retry_at_msec": 5000}, 10.0, 1000) == "none",
		"a failed preload waits for its retry time")
	state = {"active": true, "far_since_msec": -1}
	_expect(Policy.preload_action(state, 40.0, 0) == "keep" and int(state.far_since_msec) == -1,
		"a preload is kept while the player is within 48 tiles")
	_expect(Policy.preload_action(state, 60.0, 1000) == "keep" and int(state.far_since_msec) == 1000,
		"wandering past 48 tiles starts the clock")
	_expect(Policy.preload_action(state, 60.0, 61000) == "keep",
		"a minute away is not yet enough")
	_expect(Policy.preload_action(state, 60.0, 61001) == "drop",
		"more than a minute past 48 tiles drops the preload")
	_expect(Policy.preload_action(state, 20.0, 70000) == "keep" and int(state.far_since_msec) == -1,
		"coming back near resets the clock")
	_expect(is_equal_approx(Policy.tile_distance(Vector2i(0, 0), Vector2i(3, 4)), 5.0),
		"tile distances are straight lines")
	_expect(Policy.preload_action({"active": false, "settled": false}, 10.0, 0) == "none"
		and Policy.preload_action({"active": false, "settled": true}, 10.0, 0) == "start",
		"no preload starts while the player's arrival is still loading")
	state = {"active": false, "stale": true}
	_expect(Policy.preload_action(state, 10.0, 0) == "none" and bool(state.stale),
		"a stale interior is not built again while the player lingers between 8 and 24 tiles")
	_expect(Policy.preload_action(state, 30.0, 0) == "none" and not bool(state.stale)
		and Policy.preload_action(state, 10.0, 0) == "start",
		"walking away clears it, and coming back builds it again")
	state = {"active": false, "stale": true}
	_expect(Policy.preload_action(state, Policy.PRELOAD_REARM_TILES, 0) == "start" and not bool(state.stale)
		and Policy.PRELOAD_REARM_TILES == 8.0,
		"coming within 8 tiles of a door re-arms a stale interior")
	state = {"active": false, "stale": true, "settled": false}
	_expect(Policy.preload_action(state, 3.0, 0) == "none" and not bool(state.stale),
		"re-armed at a door, it still waits for whatever holds a start")
	state = {"active": true, "far_since_msec": -1}
	_expect(Policy.preload_action(state, 2.0, 100000000) == "keep",
		"a preload is never dropped by time alone while the player stays in its area")
	_expect(not Policy.under_pressure({"a": {"bytes": 600}, "preload": {"bytes": 400}}, 1000)
		and Policy.under_pressure({"a": {"bytes": 600}, "preload": {"bytes": 401}}, 1000)
		and Policy.BUDGET_BYTES == 1792 * 1048576,
		"memory-budget pressure is the kept worlds over the 1.75 GiB budget together")
	_expect(Policy.interior_estimate(1565 * 1048576, 22 * 1048576) <= Policy.BUDGET_BYTES,
		"the complete underground fits even when unavailable compression requires source textures")
	_expect(Policy.interior_estimate(400 * 1048576, 1048576) == 401 * 1048576 + Policy.INTERIOR_FLOOR_BYTES,
		"an interior's estimate is its textures, its shell and a floor")

func _test_relations() -> void:
	var park := _park()
	_expect(park.parent_of("interior") == "exterior", "a registry interiorOf names the parent")
	_expect(park.parent_of("cellar") == "exterior", "an interior row's manifest parentRegion names the parent")
	_expect(park.parent_of("exterior") == "" and park.parent_of("elsewhere") == "",
		"an exterior has no parent")
	_expect(park.parent_of("legacy_insides") == "exterior",
		"a declared interior relationship does not depend on the publication status")
	_expect(park.parent_of("maps/nymara/interior.elm") == "exterior",
		"the server's map reference is normalised")
	_expect(park.bind_map("exterior") == 1 and park.doors().get(DOOR) == "interior",
		"the exterior's doors into a flagged interior are indexed from the interior's portals")
	_expect(park.bind_map("elsewhere") == 0, "a map without such doors indexes none")
	park.queue_free()

func _test_production_relations() -> void:
	var maps: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")).maps
	var park := _park()
	park.configure(maps)
	for map_id: String in maps:
		var entry := MapRegistry.resolve(maps, map_id)
		var parent := ""
		for key: String in ["parentRegion", "interiorOf", "insidesOf"]:
			if not str(entry.get(key, "")).is_empty():
				parent = MapRegistry.normalize_server_map_id(str(entry[key]))
				break
		if not parent.is_empty():
			_expect(park.parent_of(map_id) == parent
				and Policy.should_park(parent, map_id, {map_id: parent})
				and Policy.should_park(map_id, parent, {map_id: parent}),
				"production interior %s retains worlds across its parent door, including aliases" % map_id)
	_expect(park.parent_of("landfall_insides") == "landfall",
		"Landfall Underground retains its manifest-only parent relationship")
	park.queue_free()

# --------------------------------------------------------------------------
# Parking
# --------------------------------------------------------------------------

func _test_parking() -> void:
	var park := _park()
	var loader := _loader_with("exterior")
	var exterior: Node3D = loader.world_root
	var exterior_id := exterior.get_instance_id()
	# exterior -> interior: the exterior is parked, detached and alive.
	var parked: bool = park.leave(loader, "exterior", "interior")
	_expect(parked and park.has_parked("exterior"), "entering an interior parks its parent map")
	_expect(is_instance_valid(exterior) and exterior.get_parent() == null and not exterior.is_inside_tree(),
		"the parked world is detached, not freed")
	_expect(loader.world_root == null and loader.manifest == null,
		"the loader no longer holds the parked world")
	var interior := _give_world(loader, "interior")
	await _frames(2)
	_expect(is_instance_valid(exterior), "the parked world survives frames in the interior")
	# interior -> exterior: the exterior comes back as the same tree, and the
	# interior is parked in its place (the last interior is kept too).
	var resident: Dictionary = park.take("exterior")
	_expect(not resident.is_empty() and (resident.root as Node3D).get_instance_id() == exterior_id,
		"returning hands back the very tree that was parked")
	_expect(park.leave(loader, "interior", "exterior") and park.has_parked("interior"),
		"leaving an interior for its parent parks the interior")
	loader.adopt_world(resident)
	_expect(loader.world_root == exterior and exterior.is_inside_tree() and loader.loaded_by_adoption,
		"the parked world is re-attached by adoption")
	_expect(loader.manifest.asset_id() == "exterior", "its manifest returns with it")
	_expect(is_instance_valid(interior) and interior.get_parent() == null,
		"the interior waits detached for the next visit")
	# And straight back in again: the parked interior is the same tree.
	var again: Dictionary = park.take("interior")
	_expect(not again.is_empty() and again.root == interior, "the parked interior comes back too")
	park.leave(loader, "exterior", "interior")
	loader.adopt_world(again)
	_expect(loader.world_root == interior and park.has_parked("exterior"),
		"back and forth keeps exactly one parked world")
	_expect(int(park.counters.park) == 3 and int(park.counters.unpark) == 2,
		"every park and re-attach is counted (%s)" % [park.counters])
	var kinds: Array = []
	for event: Dictionary in park.events:
		kinds.append(str(event.event))
	_expect(kinds.count("park") == 3 and kinds.count("unpark") == 2,
		"every park and re-attach is logged with its timings")
	var park_event: Dictionary = {}
	for event: Dictionary in park.events:
		if str(event.event) == "park":
			park_event = event
	_expect(park_event.has("detach_ms") and park_event.has("estimated_mib"),
		"a park records how long the detach took and what it is estimated to hold")
	# A held interior parks nothing: the loader keeps the map left, to free it
	# on the load as it always has.
	park.held_interiors = {"cellar": "test"}
	var held_loader := _loader_with("exterior")
	var before: int = int(park.counters.park)
	_expect(not park.leave(held_loader, "exterior", "cellar") and int(park.counters.park) == before
		and held_loader.world_root != null,
		"a held interior's parent is not parked")
	held_loader.unload_world()
	held_loader.queue_free()
	park.clear()
	loader.unload_world()
	loader.queue_free()
	park.release_now()
	park.queue_free()
	await _frames(2)

## Real chunk-stream ownership with synthetic resident geometry: a missing
## resident would need a disk import. Keep exact nodes and collision across
## repeated doors, including a stay longer than the ordinary parking TTL.
func _test_streamed_parking() -> void:
	var park := _park()
	var loader := _loader_with("exterior")
	loader.unload_world()
	var stream := ContinentChunkStream.new()
	stream.territory = _manifest("exterior")
	var chunk := Node3D.new()
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	shape.shape = BoxShape3D.new()
	body.add_child(shape)
	chunk.add_child(body)
	stream.add_child(chunk)
	var entry := {"id": "resident", "estimatedResidentBytes": 1024,
		"bounds": {"min": [-1, -1, -1], "max": [1, 1, 1]}}
	stream.cells["resident"] = {"root": chunk, "entry": entry}
	stream.entries.append(entry)
	stream.resident_bytes = 1024
	loader.world_root = stream
	loader.manifest = stream.territory
	loader.add_child(stream)
	var identity := chunk.get_instance_id()
	var interior: Node3D
	for visit: int in 3:
		_expect(park.leave(loader, "exterior", "legacy_insides"),
			"regional interior visit %d parks the loaded chunk stream" % visit)
		if visit == 0:
			interior = _give_world(loader, "legacy_insides")
		else:
			loader.adopt_world(park.take("legacy_insides"))
		park.bind_map("legacy_insides")
		park.now_override = (visit + 1) * (Policy.PARK_TTL_MSEC + 1000)
		park.tick()
		await physics_frame
		await physics_frame
		_expect(not stream.is_inside_tree() and stream.cells.size() == 1
			and _chunk_hit().is_empty(), "parked chunks stay resident with no exterior collision inside")
		var kept: Dictionary = park.take("exterior")
		_expect(not kept.is_empty(), "the parent survives a long interior stay")
		if kept.is_empty():
			break
		park.leave(loader, "legacy_insides", "exterior")
		loader.adopt_world(kept)
		park.bind_map("exterior")
		await physics_frame
		await physics_frame
		_expect(loader.world_root == stream and chunk.get_instance_id() == identity
			and stream.cells.size() == 1 and stream.arrival_ready(Vector3.ZERO)
			and stream.events.is_empty(), "return restores identical ready chunks with no import or retirement")
		_expect(_chunk_hit().get("collider") == body, "return restores the original chunk collision")
		_expect(park.has_parked("legacy_insides") and is_instance_valid(interior),
			"the interior stays resident for the next visit")
	park.clear()
	park.release_now()
	loader.unload_world()
	loader.queue_free()
	park.queue_free()
	await _frames(2)

func _chunk_hit() -> Dictionary:
	return stage.get_world_3d().direct_space_state.intersect_ray(
		PhysicsRayQueryParameters3D.create(Vector3(0, 2, 0), Vector3(0, -2, 0)))

func _test_eviction() -> void:
	var park := _park()
	var loader := _loader_with("exterior")
	var exterior: Node3D = loader.world_root
	park.leave(loader, "exterior", "interior")
	_give_world(loader, "interior")
	# Travel anywhere else lets go of the parked world, freed a slice at a time.
	park.leave(loader, "interior", "elsewhere")
	_expect(not park.has_parked("exterior") and int(park.counters.evict) == 1,
		"travel to another map evicts the parked world")
	_expect(park.retiring_count() == 1 and is_instance_valid(exterior),
		"an evicted world is freed over frames, not on the travel frame")
	var freed: bool = await _until(func() -> bool: return park.retiring_count() == 0)
	_expect(freed and not is_instance_valid(exterior), "the evicted world is freed within the frame budget")
	# Ten minutes away evicts too.
	loader.unload_world()
	var outside := _give_world(loader, "exterior")
	park.now_override = 1000
	park.leave(loader, "exterior", "interior")
	park.now_override = 1000 + Policy.PARK_TTL_MSEC + 1
	park.tick()
	_expect(not park.has_parked("exterior"), "a world parked for more than ten minutes is evicted")
	await _until(func() -> bool: return park.retiring_count() == 0)
	_expect(not is_instance_valid(outside), "and freed")
	# The budget: a world estimated above it is not parked at all.
	park.now_override = -1
	loader.unload_world()
	_give_world(loader, "exterior")
	park.budget_bytes = 1
	_expect(not park.leave(loader, "exterior", "interior") and not park.has_parked("exterior"),
		"a world over the memory budget is freed, not parked")
	park.release_now()
	loader.queue_free()
	park.queue_free()
	await _frames(2)

# --------------------------------------------------------------------------
# Preloading
# --------------------------------------------------------------------------

func _test_preload() -> void:
	var park := _park()
	park.bind_map("exterior")
	# The interior's size is read on a worker; nothing starts before it is in.
	var objects := {DOOR: {"object_id": DOOR, "x": 12, "y": 18, "label": "Portal"}}
	if park.estimates_pending() > 0:
		park.observe("exterior", Vector2i(12, 30), objects)
		_expect(park.preload_state() == "", "no preload starts while its interior's size is still being read")
	park.finish_estimates(true)
	_expect(park.estimates_pending() == 0 and park._interior_bytes.has("interior"),
		"binding the parent reads its interior's estimate")
	# Far from the door: nothing starts.
	park.observe("exterior", Vector2i(60, 60), {})
	_expect(park.preload_state() == "", "nothing preloads far from every door")
	# The server's object list places the door; walking within 24 tiles starts it.
	park.observe("exterior", Vector2i(12, 40), objects)
	_expect(park.preload_state("interior") == "running" and int(park.counters.preload_start) == 1,
		"walking within 24 tiles of a door starts its interior on a worker")
	park.observe("exterior", Vector2i(12, 39), objects)
	_expect(int(park.counters.preload_start) == 1, "a running preload is not started twice")
	var ready: bool = await _until(func() -> bool: return park.preload_state("interior") == "ready")
	_expect(ready, "the worker's world is collected and published on the main thread")
	var event: Dictionary = {}
	for row: Dictionary in park.events:
		if str(row.event) == "preload_ready":
			event = row
	_expect(event.has("worker_ms") and event.has("max_slice_ms") and float(event.worker_ms) >= 100.0,
		"preload_ready records the worker's time and the longest main-thread slice (%s)" % [event])
	_expect(float(event.get("max_slice_ms", 999.0)) < 50.0,
		"no preload slice holds the main thread for 50 ms")
	var resident: Dictionary = park.take("interior")
	_expect(not resident.is_empty() and is_instance_valid(resident.root)
		and (resident.root as Node3D).get_parent() == null,
		"the map change takes the preloaded world, still off the tree")
	_expect(int(park.counters.preload_hit) == 1 and park.preload_state() == "",
		"a preload hit is counted once and the preload is handed over")
	var loader := _loader_with("exterior")
	park.leave(loader, "exterior", "interior")
	_expect(int(park.counters.preload_miss) == 0, "a hit is not also a miss")
	loader.adopt_world(resident)
	_expect(loader.world_root == resident.root and loader.world_root.is_inside_tree(),
		"the preloaded interior is adopted like any resident world")
	# Back outside, the parked interior is the preload: none starts again.
	var exterior_back: Dictionary = park.take("exterior")
	park.leave(loader, "interior", "exterior")
	loader.adopt_world(exterior_back)
	park.bind_map("exterior")
	park.observe("exterior", Vector2i(12, 20), objects)
	_expect(park.preload_state() == "" and park.has_parked("interior"),
		"a parked interior stands in for its preload")
	# Dropped after a minute more than 48 tiles away.
	park.clear()
	await _until(func() -> bool: return park.retiring_count() == 0)
	park.bind_map("exterior")
	park.now_override = 10000
	park.observe("exterior", Vector2i(12, 30), objects)
	_expect(park.preload_state("interior") == "running", "(fixture) a second preload starts")
	park.now_override = 20000
	park.observe("exterior", Vector2i(12, 90), objects)
	_expect(park.preload_state("interior") != "", "far for no time at all, it is kept")
	park.now_override = 20000 + Policy.PRELOAD_DROP_MSEC + 1
	park.observe("exterior", Vector2i(12, 90), objects)
	_expect(park.preload_state() == "" and int(park.counters.preload_drop) == 1,
		"a minute more than 48 tiles away drops the preload")
	# The dropped worker is reaped once it finishes, never joined while running.
	park.now_override = -1
	var idle: bool = await _until(func() -> bool: return park.is_idle())
	_expect(idle, "a dropped preload's worker is reaped when it finishes")
	park.clear()
	park.release_now()
	loader.unload_world()
	loader.queue_free()
	park.queue_free()
	await _frames(2)

func _test_anticipated_travel() -> void:
	var park := _park()
	park.bind_map("exterior")
	park.finish_estimates(true)
	var destination := PackedStringArray(["interior"])
	park.observe("exterior", Vector2i(200, 200), {}, false, destination)
	_expect(park.preload_state() == "", "a quest cannot compete with the current map's arrival")
	park.observe("exterior", Vector2i(200, 200), {}, true, PackedStringArray(["elsewhere", "cellar"]))
	_expect(park.preload_state() == "", "only flagged interiors of this parent may be anticipated")
	park.observe("exterior", Vector2i(200, 200), {}, true, destination)
	_expect(park.preload_state("interior") == "running", "a quest prepares its destination before walking to its door")
	var ready: bool = await _until(func() -> bool: return park.preload_state("interior") == "ready")
	_expect(ready, "the anticipated destination finishes in the background")
	park.now_override = 10000
	park.observe("exterior", Vector2i(200, 200), {}, true, destination)
	park.now_override += Policy.PRELOAD_DROP_MSEC + 1
	park.observe("exterior", Vector2i(200, 200), {}, true, destination)
	_expect(park.preload_state("interior") == "ready", "a long dialogue keeps its destination ready away from the door")
	var resident: Dictionary = park.take("interior")
	_expect(not resident.is_empty() and int(park.counters.preload_hit) == 1,
		"the quest map change adopts the prepared world without loading it again")
	if is_instance_valid(resident.get("root")): resident.root.free()
	park.clear()
	park.release_now()
	park.queue_free()
	await _frames(2)

func _test_wait_and_miss() -> void:
	var park := _park()
	var loader := _loader_with("exterior")
	# Entering with no preload at all is a miss "not_started".
	park.leave(loader, "exterior", "interior")
	_expect(int(park.counters.preload_miss) == 1, "an unprepared entry is recorded as a miss")
	var resident: Dictionary = park.take("exterior")
	_give_world(loader, "interior")
	park.leave(loader, "interior", "exterior")
	loader.adopt_world(resident)
	park.clear()
	await _until(func() -> bool: return park.retiring_count() == 0)
	# A map change while the worker still runs waits for it, then takes it.
	park.prepare_function = _slow_prepare
	park.bind_map("exterior")
	_expect(park.start_preload("interior", DOOR, 3.0), "(fixture) a slow preload starts")
	_expect(park.take("interior").is_empty() and park.should_wait("interior"),
		"a map change waits for a preload whose worker is still running")
	var taken: Dictionary = {}
	for frame: int in 240:
		taken = park.take("interior")
		if not taken.is_empty() or not park.should_wait("interior"):
			break
		await process_frame
	_expect(not taken.is_empty() and int(park.counters.preload_hit) == 1,
		"once the worker is done the waiting map change takes its world")
	_expect(not park.should_wait("interior"), "nothing is left to wait for")
	(taken.root as Node).free()
	# A preload superseded by the change (taken too late) is a miss.
	park.prepare_function = _slow_prepare
	_expect(park.start_preload("interior", DOOR, 3.0), "(fixture) another slow preload starts")
	var misses: int = int(park.counters.preload_miss)
	park.leave(loader, "exterior", "interior")
	_expect(int(park.counters.preload_miss) == misses + 1 and park.preload_state() == "",
		"a change that did not take a running preload counts a miss and drops it")
	var idle: bool = await _until(func() -> bool: return park.is_idle())
	_expect(idle, "its worker is reaped afterwards")
	park.clear()
	park.release_now()
	loader.unload_world()
	loader.queue_free()
	park.queue_free()
	await _frames(2)

# --------------------------------------------------------------------------
# Fix wave: parent kept inside, replaced parks, settled arrivals, stale builds
# --------------------------------------------------------------------------

func _test_parent_kept_inside() -> void:
	var park := _park()
	var loader := _loader_with("exterior")
	park.now_override = 1000
	park.leave(loader, "exterior", "interior")
	_give_world(loader, "interior")
	park.bind_map("interior")
	# Inside for twenty minutes: the parent's clock is refreshed every tick.
	for minute: int in range(1, 21):
		park.now_override = 1000 + minute * 60000
		park.tick()
	_expect(park.has_parked("exterior") and int(park.counters.refresh) >= 20,
		"the parent stays parked while the player is inside its interior (%s)" % [park.counters])
	# Back outside (another map bound), the parent's clock runs again.
	var resident: Dictionary = park.take("exterior")
	park.leave(loader, "interior", "exterior")
	loader.adopt_world(resident)
	park.bind_map("exterior")
	park.now_override += Policy.PARK_TTL_MSEC + 1
	park.tick()
	_expect(not park.has_parked("interior"), "the interior parked outside still expires after ten minutes")
	park.now_override = -1
	park.clear()
	park.release_now()
	loader.unload_world()
	loader.queue_free()
	park.queue_free()
	await _frames(2)

func _test_replaced_park() -> void:
	var park := _park()
	var first := _loader_with("exterior")
	var first_world: Node3D = first.world_root
	park.leave(first, "exterior", "interior")
	# The same map loaded again without taking the parked world back, then
	# parked again: the first parked tree is freed, not overwritten.
	var second := _loader_with("exterior")
	var second_world: Node3D = second.world_root
	var evicted: int = int(park.counters.evict)
	_expect(park.leave(second, "exterior", "interior") and int(park.counters.evict) == evicted + 1,
		"parking a map already parked evicts the older world first")
	_expect(park.parked_maps() == ["exterior"], "one world of the map stays parked")
	var freed: bool = await _until(func() -> bool: return park.retiring_count() == 0)
	_expect(freed and not is_instance_valid(first_world) and is_instance_valid(second_world),
		"the older world is freed in slices and the newer one stays parked")
	var resident: Dictionary = park.take("exterior")
	_expect(resident.get("root") == second_world, "taking the map back hands over the newer world")
	(second_world as Node).free()
	park.clear()
	park.release_now()
	first.queue_free()
	second.queue_free()
	park.queue_free()
	await _frames(2)

func _test_settled_and_stale() -> void:
	var park := _park()
	park.bind_map("exterior")
	park.finish_estimates(true)
	var objects := {DOOR: {"object_id": DOOR, "x": 12, "y": 18, "label": "Portal"}}
	park.observe("exterior", Vector2i(12, 22), objects, false)
	_expect(park.preload_state() == "" and int(park.counters.preload_start) == 0,
		"standing by a door while the arrival still loads starts nothing")
	park.now_override = 5000
	park.observe("exterior", Vector2i(12, 22), objects, true)
	_expect(park.preload_state("interior") == "running", "once the arrival has loaded the preload starts")
	var ready: bool = await _until(func() -> bool: return park.preload_state("interior") == "ready")
	_expect(ready, "(fixture) the preload is ready")
	var ready_at := int(park._preload.get("ready_msec", -1))
	_expect(ready_at == 5000, "the preload records when it was ready")
	# Standing by the door for an hour, unentered: kept (no timer).
	for minute: int in range(1, 61):
		park.now_override = ready_at + minute * 60000
		park.observe("exterior", Vector2i(12, 22), objects, true)
		park.tick()
	_expect(park.preload_state("interior") == "ready" and int(park.counters.preload_drop) == 0,
		"a finished preload nobody entered stays while the player stays near its doors (an hour)")
	# Memory-budget pressure lets it go, and it is stale while the player stays by.
	var budget: int = park.budget_bytes
	park.budget_bytes = int(park._preload.bytes) - 1
	park.tick()
	_expect(park.preload_state() == "" and int(park.counters.preload_drop) == 1
		and park.diagnostic_snapshot().stale.has("interior"),
		"under memory-budget pressure the unentered preload is dropped and marked stale")
	var drops: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "preload_drop")
	_expect(not drops.is_empty() and str(drops.back().reason) == "budget", "the drop is recorded as the budget's")
	# Still over budget at a door: re-armed, but nothing is built that could not be kept.
	park.observe("exterior", Vector2i(12, 20), objects, true)
	_expect(park.preload_state() == "" and int(park.counters.preload_start) == 1
		and park.events.any(func(e: Dictionary) -> bool: return str(e.event) == "preload_skip" and str(e.get("reason", "")) == "budget"),
		"a preload over the whole budget is refused at the door, never built and dropped")
	park.budget_bytes = budget
	park._retry_at.clear()
	park._stale["interior"] = true
	park.observe("exterior", Vector2i(12, 30), objects, true)
	_expect(park.preload_state() == "" and park.diagnostic_snapshot().stale.has("interior"),
		"with the pressure gone, lingering 8-24 tiles from the doors does not rebuild it")
	park.observe("exterior", Vector2i(12, 25), objects, true)
	_expect(park.preload_state("interior") == "running" and int(park.counters.preload_start) == 2
		and not park.diagnostic_snapshot().stale.has("interior")
		and park.events.any(func(e: Dictionary) -> bool: return str(e.event) == "rearmed"),
		"coming within 8 tiles of a door builds it again (re-armed)")
	await _until(func() -> bool: return park.preload_state("interior") == "ready")
	# A parked interior is kept likewise while the player stays in its area.
	var loader := _loader_with("exterior")
	var resident: Dictionary = park.take("interior")
	park.leave(loader, "exterior", "interior")
	loader.adopt_world(resident)
	var outside: Dictionary = park.take("exterior")
	park.leave(loader, "interior", "exterior")
	loader.adopt_world(outside)
	park.bind_map("exterior")
	var parked_at: int = park._now()
	for step: int in 30:
		park.now_override = parked_at + step * 60000
		park.observe("exterior", Vector2i(12, 20 + step), objects, true)
		park.tick()
	_expect(park.has_parked("interior") and park.preload_state() == "",
		"a parked interior stays parked for half an hour while the player stays within 48 tiles of its doors")
	var left_at: int = park.now_override
	park.now_override = left_at + 60000
	park.observe("exterior", Vector2i(12, 90), objects, true)
	park.tick()
	_expect(park.has_parked("interior"), "leaving its area starts its clock")
	park.now_override = left_at + 60000 + Policy.PARK_TTL_MSEC + 1
	park.observe("exterior", Vector2i(12, 90), objects, true)
	park.tick()
	_expect(not park.has_parked("interior"), "ten minutes away from its area evict it")
	park.observe("exterior", Vector2i(12, 60), objects, true)
	park.observe("exterior", Vector2i(12, 30), objects, true)
	_expect(park.preload_state("interior") == "running",
		"and coming back near its doors builds it again")
	# The estimate a preload carries is the one it is parked with.
	_expect(int(resident.get("park_bytes", -1)) == int(park._interior_bytes.get("interior", -2)),
		"a preloaded world carries its interior's estimate for parking")
	park.now_override = -1
	park.clear()
	await _until(func() -> bool: return park.is_idle() and park.retiring_count() == 0)
	park.release_now()
	loader.unload_world()
	loader.queue_free()
	park.queue_free()
	await _frames(2)

## A parent bound with no curtain up (a walk over its border) spreads its
## interior's shader warm-up over frames, and the interior's preload waits for it.
func _test_spread_warmup() -> void:
	# The interior fixture's shell: a small materials-only GLB.
	var document := {"asset": {"version": "2.0"},
		"samplers": [{"wrapS": 10497, "wrapT": 10497}, {"wrapS": 33071, "wrapT": 33071}],
		"images": [{"uri": "a.png"}, {"uri": "b.png"}],
		"textures": [{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}],
		"materials": [{"name": "wall", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
			{"name": "decal", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
			{"name": "spill", "emissiveFactor": [0.3, 0.2, 0.1], "alphaMode": "BLEND"}]}
	var file := FileAccess.open(SCRATCH.path_join("interior/world.glb"), FileAccess.WRITE)
	file.store_buffer(MaterialWarmup.materials_glb(document))
	file.close()
	var park := _park()
	park.warm_materials = true
	park.bind_map("exterior", false)
	park.finish_estimates(true)
	_expect(park.warming() == ["interior"] and not park.events.any(func(e: Dictionary) -> bool: return str(e.event) == "warm"),
		"a bind with no curtain warms nothing on its own frame: the warm-up is spread")
	var objects := {DOOR: {"object_id": DOOR, "x": 12, "y": 18, "label": "Portal"}}
	park.observe("exterior", Vector2i(12, 20), objects, false)
	for frame: int in 20:
		park.tick()
		await process_frame
	_expect(park.warming() == ["interior"] and int((park._warming["interior"] as Dictionary).frames) == 0,
		"nothing of it is built while the player's arrival is still loading")
	park.observe("exterior", Vector2i(12, 20), objects, true)
	_expect(park.preload_state() == "", "the interior's preload waits while its keys are still being warmed")
	var frames := 0
	while not park.warming().is_empty() and frames < 240:
		park.tick()
		frames += 1
		await process_frame
	var warms: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "warm")
	_expect(warms.size() == 1 and bool(warms[0].spread) and int(warms[0].materials) >= 3
		and int(warms[0].frames) >= int(warms[0].materials) and str(warms[0].error).is_empty(),
		"the spread warm-up builds one material a frame (%s)" % [warms])
	park.observe("exterior", Vector2i(12, 20), objects, true)
	_expect(park.preload_state("interior") == "running", "once warmed, the preload starts")
	park.bind_map("exterior", false)
	_expect(park.warming().is_empty(), "a warmed interior is not warmed again in the session")
	# Travel cuts a spread warm-up short; the next bind starts it again.
	var other := _park()
	other.warm_materials = true
	other.bind_map("exterior", false)
	var loader := _loader_with("exterior")
	other.leave(loader, "exterior", "elsewhere")
	_expect(other.warming().is_empty() and other.events.any(func(e: Dictionary) -> bool: return str(e.event) == "warm_cancelled"),
		"travel cancels a spread warm-up")
	var idle: bool = await _until(func() -> bool: return other.is_idle())
	_expect(idle, "its plan worker is reaped")
	other.bind_map("exterior", true)
	_expect(other.events.any(func(e: Dictionary) -> bool: return str(e.event) == "warm" and not bool(e.spread)),
		"behind a curtain the next bind warms it at once")
	for one: Node in [park, other]:
		one.clear()
	await _until(func() -> bool: return park.is_idle() and other.is_idle())
	for one: Node in [park, other]:
		one.release_now()
		one.queue_free()
	loader.unload_world()
	loader.queue_free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SCRATCH.path_join("interior/world.glb")))
	await _frames(2)

func _test_texture_footprint() -> void:
	var image := Image.create(48, 20, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.4, 0.5, 0.6, 1.0))
	_expect(TextureFootprint.header_size(image.save_png_to_buffer()) == Vector2i(48, 20),
		"a PNG's size is read from its header")
	_expect(TextureFootprint.header_size(image.save_jpg_to_buffer()) == Vector2i(48, 20),
		"a JPEG's size is read from its frame header")
	_expect(TextureFootprint.header_size(image.save_webp_to_buffer(false)) == Vector2i(48, 20)
		and TextureFootprint.header_size(image.save_webp_to_buffer(true, 0.8)) == Vector2i(48, 20),
		"a WebP's size is read, lossless and lossy")
	_expect(TextureFootprint.header_size(PackedByteArray([1, 2, 3])) == Vector2i.ZERO,
		"anything else has no size")
	_expect(TextureFootprint.texture_bytes(Vector2i(1024, 1024)) == 1024 * 1024 * 4 * 4 / 3,
		"a texture holds four bytes a pixel and a third more for its mips")
	# A GLB with two embedded images and one beside it by URI.
	var picture := Image.create(64, 32, false, Image.FORMAT_RGBA8)
	picture.save_png(SCRATCH.path_join("beside.png"))
	var document := {"asset": {"version": "2.0"}, "images": [{"bufferView": 0, "mimeType": "image/png"},
		{"bufferView": 0, "mimeType": "image/png"}, {"uri": "beside.png"}]}
	var glb := MaterialWarmup.materials_glb({"asset": {"version": "2.0"}, "images": [{}, {}]})
	# materials_glb embeds one 1x1 picture shared by every image; add a URI image.
	var stream := StreamPeerBuffer.new()
	stream.data_array = glb
	stream.seek(12)
	var json_length := stream.get_u32()
	var parsed: Dictionary = JSON.parse_string(glb.slice(20, 20 + json_length).get_string_from_utf8())
	parsed.images = document.images
	var rebuilt := _with_json(glb, parsed, json_length)
	var path := SCRATCH.path_join("probe.glb")
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(rebuilt)
	file.close()
	var seen := {}
	var total := TextureFootprint.glb_texture_bytes(ProjectSettings.globalize_path(path), seen)
	_expect(total == 2 * TextureFootprint.texture_bytes(Vector2i(1, 1)) + TextureFootprint.texture_bytes(Vector2i(64, 32))
		and seen.size() == 3, "a GLB's embedded and neighbouring images are each counted (%d)" % total)
	_expect(TextureFootprint.glb_texture_bytes(ProjectSettings.globalize_path(path), seen) == 0,
		"images already counted are not counted again")
	_expect(TextureFootprint.glb_texture_bytes("user://none.glb") == 0, "a missing GLB counts nothing")

## `glb` with its JSON chunk replaced by `document` (BIN chunk kept).
static func _with_json(glb: PackedByteArray, document: Dictionary, old_length: int) -> PackedByteArray:
	var json := JSON.stringify(document).to_utf8_buffer()
	while json.size() % 4 != 0:
		json.append(0x20)
	var binary := glb.slice(20 + old_length)
	var stream := StreamPeerBuffer.new()
	stream.put_u32(0x46546C67)
	stream.put_u32(2)
	stream.put_u32(20 + json.size() + binary.size())
	stream.put_u32(json.size())
	stream.put_u32(0x4E4F534A)
	stream.put_data(json)
	stream.put_data(binary)
	return stream.data_array

# --------------------------------------------------------------------------
# Scenery, camera, doors
# --------------------------------------------------------------------------

func _test_scenery_table() -> void:
	_expect(UndergroundScenery.config_path("landfall_insides") == "res://data/world/underground-scenery.json"
		and UndergroundScenery.config_path("landfall_town") == "res://data/world/town-scenery.json"
		and UndergroundScenery.config_path("four_gates") == "",
		"each interior names its own scenery config")
	_expect(UndergroundScenery.applies_to("landfall_insides") and not UndergroundScenery.applies_to("four_gates"),
		"the underground's scenery still applies, and nothing applies to other maps")
	_expect(UndergroundScenery.floor_default("landfall_insides", {}) == "packed_earth"
		and UndergroundScenery.floor_default("landfall_town", {}) == "authored"
		and UndergroundScenery.floor_default("landfall_town", {"floorDefault": "flagstone"}) == "flagstone",
		"caves default to packed earth, rooms keep their own floors, a config may say otherwise")
	_expect(UndergroundScenery.asset_paths("x", {"assets": {"a": "res://a.glb", "b": "res://b.glb"},
		"placements": [{"asset": "a"}, {"asset": "b"}, {"asset": "a"}]}) == PackedStringArray(["res://a.glb", "res://b.glb"]),
		"a config's models are listed once each")
	var room := Node3D.new()
	var floor_mesh := MeshInstance3D.new()
	floor_mesh.name = "Walk_tavern_ground_oak"
	floor_mesh.mesh = PlaneMesh.new()
	var planks := StandardMaterial3D.new()
	floor_mesh.set_surface_override_material(0, planks)
	room.add_child(floor_mesh)
	var stepper := SceneryStepper.new("landfall_town", room, {},
		{"map": "landfall_town", "assets": {}, "placements": [], "surfaces": {}})
	var steps := 0
	while not stepper.step(1000) and steps < 100:
		steps += 1
	_expect(stepper.done() and room.has_node(UndergroundScenery.NODE_NAME),
		"the sliced stepper dresses an interior root off the tree")
	_expect(floor_mesh.material_override == null,
		"a town room's floor keeps the shell's own material when its section is not styled")
	var cave := MeshInstance3D.new()
	cave.name = "Walk_unknown_rock"
	cave.mesh = PlaneMesh.new()
	var bare := Node3D.new()
	bare.add_child(cave)
	UndergroundScenery.style_surfaces(bare, {}, "packed_earth")
	_expect(cave.material_override is StandardMaterial3D,
		"a cave floor no section styles is packed earth, as before")
	var again := SceneryStepper.new("landfall_town", room, {}, {"map": "landfall_town"})
	_expect(again.step(0) and room.get_children().filter(
		func(node: Node) -> bool: return node.name == UndergroundScenery.NODE_NAME).size() == 1,
		"an already dressed root is never dressed twice")
	room.free()
	bare.free()
	# Process-owned class textures, released before the renderer goes.
	LookGround._class_textures.clear()

func _test_camera_restore() -> void:
	var fresh: Node3D = Controller.new()
	var defaults := WorldEnvironmentBinder.RIG_DEFAULTS
	_expect(is_equal_approx(fresh.distance, float(defaults.distance))
		and is_equal_approx(fresh.min_distance, float(defaults.min_distance))
		and is_equal_approx(fresh.max_distance, float(defaults.max_distance))
		and is_equal_approx(fresh.pitch_degrees, float(defaults.pitch_degrees))
		and is_equal_approx(fresh.zoom_step, float(defaults.zoom_step)),
		"the binder's fallback defaults are the controller's own")
	fresh.free()
	var rig: Node3D = Controller.new()
	rig.distance = 40.0
	rig.pitch_degrees = -45.0
	var town := WorldManifest.new()
	town.data = {"camera": {"distance": 12, "minDistance": 6, "maxDistance": 26,
		"pitchDegrees": -50, "zoomStep": 1.2}}
	var upstairs := WorldManifest.new()
	upstairs.data = {"camera": {"distance": 10, "minDistance": 6, "maxDistance": 20}}
	var outside := WorldManifest.new()
	outside.data = {"asset": {"id": "landfall"}}
	_expect(WorldEnvironmentBinder.apply_camera(town, rig) and is_equal_approx(rig.distance, 12.0)
		and is_equal_approx(rig.max_distance, 26.0) and is_equal_approx(rig.pitch_degrees, -50.0),
		"an interior's camera block frames the rig")
	WorldEnvironmentBinder.apply_camera(upstairs, rig)
	_expect(WorldEnvironmentBinder.apply_camera(outside, rig) == false
		and is_equal_approx(rig.min_distance, 1.5) and is_equal_approx(rig.max_distance, 90.0)
		and is_equal_approx(rig.zoom_step, 2.5),
		"a map without a block restores the default zoom limits and step")
	_expect(is_equal_approx(rig.distance, 40.0) and is_equal_approx(rig.pitch_degrees, -45.0),
		"and the distance and pitch the player had before the first interior")
	rig.distance = 33.0
	WorldEnvironmentBinder.apply_camera(outside, rig)
	_expect(is_equal_approx(rig.distance, 33.0),
		"between maps without blocks the player's zoom carries over")
	rig.max_distance = 26.0
	rig.distance = 20.0
	WorldEnvironmentBinder.restore_camera(rig)
	_expect(is_equal_approx(rig.max_distance, 90.0) and is_equal_approx(rig.distance, 20.0),
		"limits left by anything else are put back without moving the camera")
	rig.free()

func _test_building_doors() -> void:
	var catalog := {"authoredObjects": {
		str(DOOR): {"entrance": true, "building": true, "exteriorTile": [10, 12],
			"label": "The Unlit Boat", "exitLabel": "The avenue", "category": "tavern",
			"height": 3.0, "radius": 1.2, "modelOffset": [0.0, 0.0, -2.0], "exitOffset": [0.0, 0.0, 1.0]},
		"59001": {"entrance": true, "exteriorTile": [30, 30], "label": "Lantern Mine",
			"height": 3.6, "radius": 1.6}}}
	var adapter := CoordinateAdapter.new({})
	var door := MapObject3D.new()
	door.configure({"object_id": DOOR, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 10, "y": 12,
		"label": "Portal", "detail": "The Unlit Boat. Open to all."}, adapter, catalog)
	stage.add_child(door)
	var title := door.get_node_or_null("EntranceLabel") as Label3D
	_expect(door.building_door and not door.building_exit and door.offers_map_change(),
		"a building's street door is a clickable portal")
	_expect(door.get_node_or_null("Ring") == null, "a building door draws no ground ring")
	_expect(title != null and title.text.begins_with("The Unlit Boat") and not title.visible,
		"its label names the building and is hidden by default")
	var pick := door.get_node("PickShape") as CollisionShape3D
	_expect(pick.shape is CylinderShape3D and (pick.shape as CylinderShape3D).radius >= 1.6
		and is_equal_approx(pick.position.z, -1.0) and door.collision_layer == MapObject3D.PICK_LAYER,
		"its pick reaches from the step to the painted door")
	_expect(door.destination() == "The Unlit Boat", "its hover name is the building's")
	_expect(door.wants_label_focus(), "main keeps its label in step with the player")
	door.update_label_focus(door.global_position + Vector3(30, 0, 0), false)
	_expect(not title.visible, "the label stays hidden for a player 30 m away")
	door.update_label_focus(door.global_position + Vector3(8, 0, -2), false)
	_expect(title.visible, "the label shows within 12 m of the door")
	door.update_label_focus(Vector3.INF, true)
	_expect(title.visible, "the label shows under the pointer")
	door.update_label_focus(Vector3.INF, false)
	_expect(not title.visible, "and hides again when neither holds")
	var exit := MapObject3D.new()
	exit.configure({"object_id": DOOR, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 40, "y": 40,
		"label": "Portal", "detail": "The avenue."}, adapter, catalog)
	stage.add_child(exit)
	var exit_title := exit.get_node_or_null("EntranceLabel") as Label3D
	_expect(exit.building_exit and not exit.building_door and exit.get_node_or_null("Ring") == null
		and exit_title != null and exit_title.text.begins_with("The avenue") and not exit_title.visible,
		"the same object on the interior's exit tile is the way out, named by exitLabel")
	_expect(exit.destination() == "The avenue", "the exit hovers as its street")
	_expect(is_equal_approx(exit_title.position.x, 0.0) and is_equal_approx(exit_title.position.z, 1.0)
		and is_equal_approx(exit_title.position.y, MapObject3D.EXIT_LABEL_HEIGHT)
		and MapObject3D.EXIT_LABEL_HEIGHT >= 2.2 and MapObject3D.EXIT_LABEL_HEIGHT <= 2.4,
		"the exit's label stands at its door in the wall (exitOffset), at lintel height")
	exit.update_label_focus(exit.global_position + Vector3(0, 0, 1.0 - 5.5), false)
	_expect(exit_title.visible, "the exit names itself within 6 m of its door")
	exit.update_label_focus(exit.global_position + Vector3(0, 0, 1.0 - 6.5), false)
	_expect(not exit_title.visible, "but not from farther than 6 m")
	await _test_exit_label_screen(catalog, adapter)
	var cave := MapObject3D.new()
	cave.configure({"object_id": 59001, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 30, "y": 30,
		"label": "Portal", "detail": "Beyond it lies Lantern Mine. Safe."}, adapter, catalog)
	stage.add_child(cave)
	_expect(not cave.building_door and not cave.wants_label_focus()
		and (cave.get_node("EntranceLabel") as Label3D).visible and cave.get_node_or_null("Ring") != null,
		"a cave mouth keeps its permanent label and ring")
	_expect(cave.destination() == "Lantern Mine", "a cave mouth still hovers as where it leads")
	# A lore object (pickOnly): no ring, no model, no map mark; a pick centred
	# on the prop the room already stands, named under the pointer.
	var lore_catalog := {"authoredObjects": {"59251": {"interactive": true, "pickOnly": true,
			"label": "The unlit boat", "modelOffset": [0.5, 0.0, -1.25], "height": 1.1, "radius": 0.7},
		"59221": {"passage": true, "height": 3.6, "radius": 1.6, "label": "Upstairs: the guest rooms",
			"modelOffset": [0.0, 0.0, -2.4]}},
		"interactives": {"roles": {"Information": "notice_board"},
			"models": {"notice_board": {"scene": "res://assets/world/does-not-matter.glb", "height": 2.0}}}}
	var lore := MapObject3D.new()
	lore.configure({"object_id": 59251, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 20, "y": 20,
		"label": "Information", "detail": "A painting of a dark boat."}, adapter, lore_catalog)
	stage.add_child(lore)
	var lore_pick := lore.get_node("PickShape") as CollisionShape3D
	_expect(lore.pick_only and lore.get_node_or_null("Ring") == null and lore.get_node_or_null("Model") == null
		and lore.get_node_or_null("MapMarker") == null,
		"a pick-only lore object draws no ring, no catalog model and no map mark")
	_expect(is_equal_approx(lore_pick.position.x, 0.5) and is_equal_approx(lore_pick.position.z, -1.25)
		and is_equal_approx((lore_pick.shape as CylinderShape3D).radius, 0.7)
		and lore.collision_layer == MapObject3D.PICK_LAYER,
		"its pick is centred on the prop it describes, at the record's radius")
	var lore_title := lore.get_node_or_null("ObjectLabel") as Label3D
	_expect(lore_title != null and lore_title.text == "The unlit boat" and not lore_title.visible
		and lore.wants_label_focus(), "it carries its short name, hidden until pointed at")
	lore.update_label_focus(lore.global_position, false)
	_expect(not lore_title.visible, "standing beside it does not name it")
	lore.update_label_focus(Vector3.INF, true)
	_expect(lore_title.visible, "the pointer names it")
	var stair := MapObject3D.new()
	stair.configure({"object_id": 59221, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 35, "y": 28,
		"label": "Portal", "detail": "Upstairs: the guest rooms."}, adapter, lore_catalog)
	stage.add_child(stair)
	var stair_pick := stair.get_node("PickShape") as CollisionShape3D
	_expect(stair.is_passage_end() and is_equal_approx(stair_pick.position.z, -1.2)
		and (stair_pick.shape as CylinderShape3D).radius >= 1.8 and stair.get_node_or_null("Ring") == null,
		"a stair end's pick reaches from its tile to the stair drawn beside it")
	_expect(stair.is_stair_end() and not door.is_passage_end() and not cave.is_passage_end(),
		"doors and cave mouths are not passage ends; a stair drawn beside its tile is a stair end")
	var tunnel := MapObject3D.new()
	tunnel.configure({"object_id": 59101, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 9, "y": 9,
		"label": "Portal", "detail": "A way leads on into Beta Pocket. Damp."}, adapter,
		{"authoredObjects": {"59101": {"passage": true, "height": 3.6, "radius": 1.6, "label": "Beta Pocket"}}})
	stage.add_child(tunnel)
	_expect(tunnel.is_passage_end() and not tunnel.is_stair_end()
		and is_equal_approx((tunnel.get_node("PickShape") as CollisionShape3D).position.z, 0.0),
		"a cave passage end is no stair end and keeps its pick on its tile (the caves unchanged)")
	tunnel.queue_free()
	lore.queue_free()
	stair.queue_free()
	door.queue_free()
	exit.queue_free()
	cave.queue_free()

## The highest vertex of a label's text mesh (NAN when it offers none).
static func _label_top(title: Label3D) -> float:
	var triangles: TriangleMesh = title.generate_triangle_mesh()
	if triangles == null:
		return NAN
	var top := -INF
	for point: Vector3 in triangles.get_faces():
		top = maxf(top, point.y)
	return top if is_finite(top) else NAN

## An exit on the camera's side of a room, seen through the town's camera
## (-50 degrees, 12 m, fov 50) in a 1600x900 view whose HUD bar starts at
## y = 800: its label is lifted on screen just clear of the bar, only as far
## as it would fall under it, and its anchor never leaves the door.
func _test_exit_label_screen(catalog: Dictionary, adapter: CoordinateAdapter) -> void:
	var view := SubViewport.new()
	view.size = Vector2i(1600, 900)
	view.own_world_3d = true
	view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(view)
	var camera := Camera3D.new()
	camera.fov = 50.0
	view.add_child(camera)
	camera.current = true
	var exit := MapObject3D.new()
	exit.configure({"object_id": DOOR, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 40, "y": 40,
		"label": "Portal", "detail": "The avenue."}, adapter, catalog)
	view.add_child(exit)
	var title := exit.get_node("EntranceLabel") as Label3D
	title.visible = true
	await process_frame
	var door := exit.global_position + Vector3(0.0, 0.0, 1.0)
	var floor_y := 800.0
	var place := func(player: Vector3) -> void:
		var pitch := deg_to_rad(-50.0)
		camera.global_position = player + Vector3(0.0, -sin(pitch), cos(pitch)) * 12.0
		camera.look_at(player + Vector3.UP * 1.2, Vector3.UP)
	var bottom_of := func() -> float:
		var per_unit := MapObject3D.screen_pixels_per_unit(camera)
		return camera.unproject_position(title.global_position).y - title.offset.y * title.pixel_size * per_unit \
			+ MapObject3D.label_half_height(title) * per_unit
	var half_px := MapObject3D.label_half_height(title) * MapObject3D.screen_pixels_per_unit(camera)
	_expect(half_px > 10.0 and half_px < 60.0,
		"(fixture) the exit label's two lines are %.1f px from centre to edge on this screen" % half_px)
	var top_plain := _label_top(title)
	# The player 5.5 m into the room from the camera-side door (inside the 6 m
	# rule): the label at the door's lintel reaches under the bar.
	place.call(door + Vector3(0.0, 0.0, -5.5))
	var anchor_before := title.global_position
	var unlifted: float = float(bottom_of.call())
	var lift := exit.keep_label_above(camera, floor_y)
	_expect(unlifted > floor_y and lift > 0.0 and title.offset.y > 0.0,
		"a camera-side door's label that would reach under the HUD bar (to %.0f px) is lifted %.0f px" % [unlifted, lift])
	_expect(absf(float(bottom_of.call()) + MapObject3D.LABEL_HUD_MARGIN - floor_y) < 1.0
		and title.global_position == anchor_before,
		"just clear of the bar (to %.1f px), while its anchor stays at the door" % [float(bottom_of.call())])
	await process_frame
	var top_lifted := _label_top(title)
	_expect(is_nan(top_plain) or top_lifted > top_plain + 0.0001,
		"(the lift is the label's offset, drawn upward: its mesh top %.4f -> %.4f)" % [top_plain, top_lifted])
	# Nearer the door the label is higher on the screen; within the room's
	# depth it is lifted only as far as the bar needs, and not at all by the door.
	var previous := lift
	for metres: float in [4.5, 3.5]:
		place.call(door + Vector3(0.0, 0.0, -metres))
		var now := exit.keep_label_above(camera, floor_y)
		_expect(now <= previous and float(bottom_of.call()) <= floor_y - MapObject3D.LABEL_HUD_MARGIN + 1.0,
			"%.1f m from the door it is lifted %.0f px (no more), still above the bar" % [metres, now])
		previous = now
	place.call(door + Vector3(0.0, 0.0, -1.0))
	_expect(exit.keep_label_above(camera, floor_y) == 0.0 and is_equal_approx(title.offset.y, 0.0),
		"a label already well above the bar is not lifted (anchor at %.0f px)" % [camera.unproject_position(title.global_position).y])
	# Hidden labels are not lifted.
	place.call(door + Vector3(0.0, 0.0, -5.5))
	title.visible = false
	_expect(exit.keep_label_above(camera, floor_y) == 0.0 and is_equal_approx(title.offset.y, 0.0),
		"a hidden label is left alone")
	_expect(exit.label_span(camera) == Vector2(-INF, INF), "and spans the whole screen's width (no part is skipped)")
	# Its floor is the topmost bottom HUD part under the label's own width
	# (final review 2026-10-27, finding 2): the default layout's resource strip
	# above the quickbar, not the quickbar.
	title.visible = true
	var span := exit.label_span(camera)
	var anchor_x := camera.unproject_position(title.global_position).x
	_expect(span.x < anchor_x and span.y > anchor_x and absf((anchor_x - span.x) - (span.y - anchor_x)) < 0.01
		and span.y - span.x > 2.0 * half_px,
		"a shown label spans %.0f..%.0f px, centred on its anchor and wider than tall" % [span.x, span.y])
	var hud := [Rect2(0.0, 845.0, 1290.0, 55.0), Rect2(0.0, 795.0, 1495.0, 50.0), Rect2(1495.0, 795.0, 105.0, 105.0)]
	_expect(MapObject3D.label_floor(hud, span.x, span.y, 900.0) == 795.0,
		"over a strip standing on a bar, the floor is the strip's top")
	_expect(MapObject3D.label_floor([Rect2(0.0, 845.0, 1600.0, 55.0), Rect2(span.y + 1.0, 600.0, 200.0, 300.0)],
			span.x, span.y, 900.0) == 845.0,
		"a taller part beside the label, not under it, sets no floor")
	_expect(MapObject3D.label_floor([], span.x, span.y, 900.0) == 900.0
		and MapObject3D.label_floor(["not a rect"], span.x, span.y, 900.0) == 900.0,
		"with no part under it the floor is the screen's bottom")
	exit.keep_label_above(camera, MapObject3D.label_floor(hud, span.x, span.y, 900.0))
	_expect(absf(float(bottom_of.call()) + MapObject3D.LABEL_HUD_MARGIN - 795.0) < 1.0,
		"so the label is lifted just clear of the strip (to %.1f px)" % [float(bottom_of.call())])
	title.visible = false
	exit.keep_label_above(camera, floor_y)
	_expect(MapObject3D.label_lift(1050.0, 20.0, 800.0, 900.0) == 0.0
		and is_equal_approx(MapObject3D.label_lift(950.0, 20.0, 800.0, 900.0), 176.0)
		and is_equal_approx(MapObject3D.label_lift(780.0, 20.0, 800.0, 900.0), 6.0)
		and MapObject3D.label_lift(500.0, 20.0, 800.0, 900.0) == 0.0,
		"a door more than the bar's height below the screen is not pinned to it; nearer ones are lifted to the margin")
	view.queue_free()
	await process_frame
