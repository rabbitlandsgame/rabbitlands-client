extends SceneTree

## A harvestable the server lists before the streamed chunk beneath it is
## resident finds no navigation surface, and stayed recorded as ungrounded
## until the next map change (Crownwater's Riverflax on the live proof). Each
## chunk arrival now places the map objects and markers again.
var failures := 0
var main: Control

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func settle() -> void:
	await physics_frame
	await process_frame
	await physics_frame
	await process_frame

func navigation_floor(top: float) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40.0, 1.0, 40.0)
	shape.shape = box
	body.add_child(shape)
	body.position = Vector3(0.0, top - 0.5, 0.0)
	return body

func run() -> void:
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var state: Node = root.get_node("AppState")
	root.get_node("Network").set_process(false)
	# The active territory streams its chunks; the object's own is not resident.
	var chunks := ContinentChunkStream.new()
	main.world_root.add_child(chunks)
	main.world_loader.world_root = chunks
	main._watch_chunk_surfaces()
	expect(chunks.cell_ready.is_connected(main._on_chunk_surface_ready), "chunk arrivals of the active territory are watched")
	main._watch_chunk_surfaces()
	expect(chunks.cell_ready.get_connections().size() == 1, "watching again does not duplicate the connection")
	state.current_map = "crownwater"
	state.map_objects = {68: {"object_id": 68, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
		"x": 278, "y": 80, "label": "Riverflax", "detail": ""}}
	main._sync_map_objects()
	await settle()
	var object: MapObject3D = main.map_object_nodes[68]
	expect(main._ungrounded_map_objects.has(68), "an object above an absent chunk is recorded as ungrounded")
	var before: float = object.global_position.y
	# The chunk attaches with its navigation surface at 7.2 m.
	var floor := navigation_floor(7.2)
	chunks.add_child(floor)
	floor.global_position = Vector3(object.global_position.x, 7.2 - 0.5, object.global_position.z)
	chunks.cell_ready.emit("02_16", floor)
	await settle()
	await settle()
	expect(not main._ungrounded_map_objects.has(68), "the object is grounded once its chunk attaches")
	expect(absf(object.global_position.y - 7.25) < 0.01,
		"it stands on the attached surface (%.2f -> %.2f)" % [before, object.global_position.y])
	print("map object regrounding test: %d failures" % failures)
	quit(1 if failures > 0 else 0)
