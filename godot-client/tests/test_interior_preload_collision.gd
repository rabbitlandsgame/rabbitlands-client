extends SceneTree
## A whole interior built on a worker (WorldPark's preload,
## WorldLoader.prepare_detached) takes its collision faces from the parsed
## glTF's CPU arrays instead of reading every generated mesh back from the GPU
## through the main thread (world_loader.gd `_cpu_collision_wanted`), and gets
## the same collision as the main thread's own build, shape for shape:
##
##   godot --headless --path godot-client --script res://tests/test_interior_preload_collision.gd
##
## Uses the real Landfall Town package (skipped when it is not on disk).

const TOWN := "landfall_town"
const TOLERANCE := 0.002
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

static func _build_on_worker(path: String) -> WorldLoader:
	return WorldLoader.prepare_detached(path, false)

## Collision faces by the body's path under the world root.
static func _collision(root: Node) -> Dictionary:
	var result := {}
	for node: Node in root.find_children("*", "CollisionShape3D", true, false):
		var shape := (node as CollisionShape3D).shape as ConcavePolygonShape3D
		if shape != null:
			# The shape node's own name is generated (@CollisionShape3D@n): key
			# by its body's path and its place under the body.
			result["%s#%d" % [root.get_path_to(node.get_parent()), node.get_index()]] = shape.get_faces()
	return result

func _run() -> void:
	var registry: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")) as Dictionary).get("maps", {})
	var path := ProjectSettings.globalize_path(str(MapRegistry.resolve(registry, TOWN).get("manifest", "")))
	if not FileAccess.file_exists(path):
		print("SKIP: the Landfall Town package is not on disk")
		quit(0)
		return
	preload("res://src/world/gltf_quantization.gd").ensure_registered()
	preload("res://src/world/vram_textures.gd").ensure_registered()
	preload("res://src/world/map_mesh_extension.gd").ensure_registered()
	var thread := Thread.new()
	thread.start(_build_on_worker.bind(path))
	while thread.is_alive():
		await process_frame
	var worker: WorldLoader = thread.wait_to_finish()
	var worker_phases: Dictionary = worker.load_phases.duplicate()
	var worker_root: Node3D = worker.release_world(true, true).get("root")
	worker.free()
	var main_loader := WorldLoader.prepare_detached(path, false)
	var main_phases: Dictionary = main_loader.load_phases.duplicate()
	var main_root: Node3D = main_loader.release_world(true, true).get("root")
	main_loader.free()
	_expect(int(worker_phases.get(&"cpuCollisionShapes", 0)) > 0 and int(worker_phases.get(&"rawCollisionShapes", 0)) == 0,
		"the worker's build reads no mesh back from the GPU for its collision (%s CPU, %s read back)"
			% [worker_phases.get(&"cpuCollisionShapes", 0), worker_phases.get(&"rawCollisionShapes", 0)])
	_expect(int(main_phases.get(&"rawCollisionShapes", 0)) > 0 and int(main_phases.get(&"cpuCollisionShapes", 0)) == 0,
		"a main-thread build keeps the generated meshes' path")
	var on_worker := _collision(worker_root)
	var on_main := _collision(main_root)
	_expect(on_worker.size() == on_main.size() and on_worker.size() > 0,
		"both builds stand the same collision bodies (%d, %d)" % [on_worker.size(), on_main.size()])
	var differing: Array = []
	for key: String in on_main:
		var a: PackedVector3Array = on_main[key]
		var b: PackedVector3Array = on_worker.get(key, PackedVector3Array())
		var same := a.size() == b.size()
		if same:
			for index: int in a.size():
				if not a[index].is_equal_approx(b[index]) and a[index].distance_to(b[index]) > TOLERANCE:
					same = false
					break
		if not same:
			differing.append(key)
	_expect(differing.is_empty(), "every collision shape has the same faces, in the same order (%s)" % [differing.slice(0, 5)])
	worker_root.free()
	main_root.free()
	for frame: int in 3:
		await process_frame
	print("Interior preload collision: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)
