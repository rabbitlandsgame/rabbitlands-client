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

func main_surface_connection_count(stream: ContinentChunkStream) -> int:
	var callback := Callable(main, "_on_chunk_surface_ready")
	var count := 0
	for connection: Dictionary in stream.cell_ready.get_connections():
		if connection.get("callable") == callback:
			count += 1
	return count

func cleanup_owned_main(state: Node) -> bool:
	# Intro cancellation must not issue a normal authenticated chat command.
	state.authenticated = false
	state.local_actor_id = -1
	state.selected_actor_id = -1
	state.current_map = ""
	state.actors = {}
	state.map_objects = {}
	state.combat_state = {}
	main.set_process(false)
	main.set_physics_process(false)
	main.set_process_input(false)
	main.set_process_unhandled_input(false)
	main.respawn_prewarm.discard()
	main._clear_world_presentation()
	# Exterior retirement still owns any retained roots. Keep its bounded
	# deferred drainer running until clear and physics follow-ups complete.
	main.exterior_stream.set_process(true)
	var deadline := Time.get_ticks_msec() + 30000
	var stable := 0
	while stable < 3:
		await physics_frame
		await process_frame
		var ready: bool = main.exterior_stream.is_idle() \
			and int(main.surface_work_snapshot().pending) == 0 \
			and not bool(main._actor_surface_snap_pending)
		stable = stable + 1 if ready else 0
		if Time.get_ticks_msec() >= deadline:
			expect(false, "owned terrain and surface follow-ups drain before test shutdown")
			# Preserve a busy owner for the strict runner to stop; never free
			# worker-backed content just to make an incomplete test exit.
			return false
	main.process_mode = Node.PROCESS_MODE_DISABLED
	main.queue_free()
	await settle()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await settle()
	return true

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
	expect(main_surface_connection_count(chunks) == 1, "watching again keeps exactly one Main terrain callback")
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
	var local_center := chunks.to_local(floor.global_position)
	chunks.cells["02_16"] = {"root": floor, "manifest": WorldManifest.new(),
		"entry": {"id": "02_16", "estimatedResidentBytes": 0,
			"bounds": {"min": [local_center.x - 20, 6, local_center.z - 20],
				"max": [local_center.x + 20, 8, local_center.z + 20]}}}
	chunks.cell_ready.emit("02_16", floor)
	await settle()
	await settle()
	expect(not main._ungrounded_map_objects.has(68), "the object is grounded once its chunk attaches")
	expect(absf(object.global_position.y - 7.25) < 0.01,
		"it stands on the attached surface (%.2f -> %.2f)" % [before, object.global_position.y])
	if not await cleanup_owned_main(state):
		return
	print("map object regrounding test: %d failures" % failures)
	quit(1 if failures > 0 else 0)
