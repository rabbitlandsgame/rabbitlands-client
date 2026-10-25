extends SceneTree
## Test-only readiness cannot confuse a loaded root with completed map work.
const Readiness := preload("res://tests/integration/client_world_readiness.gd")
var failures := 0
var checks := 0

class Stream:
	extends ExteriorRegionStream
	var idle := true
	func is_idle() -> bool: return idle

class Ambient:
	extends Node
	var _pending_cells: Dictionary = {}

class Owner:
	extends Node
	var world_loader := WorldLoader.new()
	var exterior_stream := Stream.new()
	var camera_rig: Node3D
	var ambient_population: Node
	var loaded_server_map := "landfall"
	var _deferred_map_load := false
	var _actor_surface_snap_pending := false

class Hooks:
	extends Owner
	var pending_ambient := 0
	var pending_surface := 0
	func ambient_creation_pending_count() -> int: return pending_ambient
	func surface_work_snapshot() -> Dictionary: return {"pending": pending_surface}

class Camera:
	extends Node3D
	var focus := Vector3.ZERO

class Chunk:
	extends ContinentChunkStream
	var views_ok := true
	var views_error := false
	var prefetch_ok := true
	var arrival_ok := true
	func views_ready() -> bool: return views_ok
	func views_failed() -> bool: return views_error
	func prefetch_ready() -> bool: return prefetch_ok
	func arrival_ready(_position: Vector3, _radius := ARRIVAL_FRAME_METRES) -> bool: return arrival_ok

func _init() -> void: run.call_deferred()

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func run() -> void:
	var app := root.get_node("AppState")
	var prior_map := str(app.get("current_map"))
	app.set("current_map", "landfall")
	var owner := Hooks.new()
	root.add_child(owner)
	owner.add_child(owner.world_loader)
	owner.add_child(owner.exterior_stream)
	owner.camera_rig = Camera.new()
	owner.add_child(owner.camera_rig)
	var ground := Node3D.new()
	owner.world_loader.add_child(ground)
	owner.world_loader.world_root = ground
	expect(Readiness.snapshot(owner).ready, "an idle loaded world is ready")
	for field: String in ["_deferred_map_load", "_actor_surface_snap_pending"]:
		owner.set(field, true)
		expect(not Readiness.snapshot(owner).ready, field + " blocks readiness")
		owner.set(field, false)
	owner.loaded_server_map = "another_map"
	expect(not Readiness.snapshot(owner).ready, "a root for the wrong map is insufficient")
	owner.loaded_server_map = "landfall"
	owner.world_loader.set("_cache_write_countdown", 2)
	expect(not Readiness.snapshot(owner).ready, "pending cache work blocks readiness")
	owner.world_loader.set("_cache_write_countdown", 0)
	owner.exterior_stream.idle = false
	expect(not Readiness.snapshot(owner).ready, "neighbor streaming blocks readiness")
	owner.exterior_stream.idle = true
	owner.pending_ambient = 1
	expect(not Readiness.snapshot(owner).ready, "pending ambient creation blocks readiness")
	owner.pending_ambient = 0
	owner.pending_surface = 1
	expect(not Readiness.snapshot(owner).ready, "pending surface follow-up blocks readiness")
	owner.pending_surface = 0
	var neighbor := Chunk.new()
	owner.add_child(neighbor)
	owner.exterior_stream.residents = {"neighbor": {"root": neighbor}}
	neighbor._preload_views.assign([{"id": "view"}])
	for field: String in ["views_ok", "prefetch_ok"]:
		neighbor.set(field, false)
		expect(not Readiness.snapshot(owner).ready, "resident " + field + " blocks readiness")
		neighbor.set(field, true)
	neighbor.views_error = true
	expect(not Readiness.snapshot(owner).ready, "failed resident views block readiness")
	neighbor.views_error = false
	neighbor.set("_thread", Thread.new())
	expect(not Readiness.snapshot(owner).ready, "resident worker blocks readiness")
	neighbor.set("_thread", null)
	neighbor._retiring.assign([{}])
	expect(not Readiness.snapshot(owner).ready, "resident retirement blocks readiness")
	neighbor._retiring.clear()
	owner.world_loader.world_root = neighbor
	neighbor.arrival_ok = false
	expect(not Readiness.snapshot(owner).ready, "active chunk arrival must complete")
	neighbor.arrival_ok = true
	expect(Readiness.snapshot(owner).ready, "all completed chunks become ready")
	var stable := Readiness.StableResources.new(0)
	for frame: int in 13: expect(not stable.observe("same", true, frame * 10), "minimum resource wait is retained")
	expect(stable.observe("same", true, 1000), "stable resources need both 12 frames and one second")
	expect(not stable.observe("new-resource", true, 1010) and stable.stable_frames == 0, "new resources reset the stable frame count")
	for frame: int in 11: stable.observe("new-resource", true, 1020 + frame * 10)
	expect(not stable.observe("new-resource", false, 1200) and stable.stable_frames == 0, "new world work resets stability")
	for frame: int in 11: stable.observe("new-resource", true, 1210 + frame * 10)
	expect(not stable.observe("other", true, 1400), "stability never spans changed resources")
	var fresh := Readiness.StableResources.new(0)
	fresh.observe("same", true, 1000)
	for frame: int in 11: fresh.observe("same", true, 1010 + frame * 10)
	expect(fresh.stable_frames == 11 and not fresh.observe("same", false, 1200),
		"elapsed time alone cannot replace 12 stable resource frames")
	for frame: int in 11: fresh.observe("same", true, 1210 + frame * 10)
	expect(fresh.observe("same", true, 1400), "12 ready resource frames allow the sample to start")
	# Parse the actual consumers without instantiating or connecting a client.
	for path: String in ["res://tests/integration/crowd_benchmark_main.gd", "res://tests/integration/live_spawn_responsiveness.gd"]:
		var script := load(path) as GDScript
		expect(script != null and script.can_instantiate(), path + " loads cleanly")
	owner.free()
	app.set("current_map", prior_map)
	print("CLIENT WORLD READINESS: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)
