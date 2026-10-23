extends SceneTree
## Real Main subscriptions + pick binding; no map package or authored asset.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)

func _cell(stream: ContinentChunkStream, identity: String) -> Node3D:
	var imported := Node3D.new()
	imported.name = "Cell"
	stream.add_child(imported)
	stream.cells[identity] = {"root": imported, "manifest": WorldManifest.new(),
		"entry": {"id": identity, "estimatedResidentBytes": 1,
			"bounds": {"min": [0, -1, 0], "max": [10, 1, 10]}}}
	return imported

func _run() -> void:
	var main_script := load("res://src/app/main.gd") as GDScript
	if main_script == null or not main_script.can_instantiate():
		_expect(false, "Main compiles for the binding callback integration")
		quit(1)
		return
	# Do not enter the UI scene: wire only this callback's actual dependencies.
	# The four Node helpers are @onready, so this unentered test owns no orphans.
	var main := main_script.new() as Control
	var loader := WorldLoader.new()
	var stage := Node3D.new()
	root.add_child(stage)
	var current := ContinentChunkStream.new()
	var neighbour := ContinentChunkStream.new()
	stage.add_child(current)
	stage.add_child(neighbour)
	current.set_process(false)
	neighbour.set_process(false)
	var current_cell := _cell(current, "repeated-id")
	_cell(neighbour, "repeated-id")
	var placed := MeshInstance3D.new()
	placed.name = "SyntheticBoundPlacement"
	placed.mesh = BoxMesh.new()
	current_cell.add_child(placed)
	var map_object := MapObject3D.new()
	map_object.object_id = 7117
	map_object.bound_node_name = placed.name
	map_object.presentation = {"bind": {"chunk": "repeated-id", "node": str(placed.name)}}
	stage.add_child(map_object)
	_expect(map_object.bind_placement(placed), "active map's synthetic placement has a real pick proxy")
	var proxy := placed.get_node_or_null("MapObjectPickProxy") as StaticBody3D
	_expect(map_object.placement_bound() and proxy != null, "active placement begins bound")
	loader.world_root = current
	main.set("world_loader", loader)
	main.set("map_object_nodes", {7117: map_object})
	main.call("_watch_surface_stream", current)
	main.call("_watch_surface_stream", neighbour)
	var callback := Callable(main, "_on_chunk_cell_retiring")
	_expect(current.cell_retiring.is_connected(callback) and neighbour.cell_retiring.is_connected(callback),
		"Main subscribes the same real retirement callback to current and neighbour streams")
	neighbour._retire_cell("repeated-id")
	_expect(map_object.placement_bound() and is_instance_valid(proxy)
		and not proxy.is_queued_for_deletion() and proxy.collision_layer == MapObject3D.PICK_LAYER,
		"neighbour retirement with a repeated ID preserves the active map's exact live pick binding")
	current._retire_cell("repeated-id")
	_expect(not map_object.placement_bound() and is_instance_valid(proxy) and proxy.is_queued_for_deletion(),
		"retirement of the actual bound current cell still releases its pick proxy")
	main.set("map_object_nodes", {})
	main.free()
	loader.world_root = null
	loader.free()
	stage.free()
	await process_frame
	print("Main chunk binding scope: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)
