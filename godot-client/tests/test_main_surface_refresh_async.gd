extends SceneTree
## Actual Main scheduler/flush/clear, synthetic terrain only. This deliberately
## enters Main.tscn so its real @onready dependencies and teardown are owned.
var failures := 0
var main: Control
var state: Node

signal deferred_checkpoint

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, label: String) -> void:
	if value:
		print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func _checkpoint() -> void:
	deferred_checkpoint.emit()

func _after_deferred_flush_started() -> void:
	# Scheduled after Main's deferred flush, without advancing to another frame.
	# The flush must enter its physics await before this checkpoint runs.
	_checkpoint.call_deferred()
	await deferred_checkpoint

func _drain() -> void:
	for _frame: int in range(3):
		await physics_frame
		await process_frame

func _wait_idle(label: String) -> void:
	for _frame: int in range(12):
		await physics_frame
		await process_frame
		var snapshot: Dictionary = main.surface_work_snapshot()
		if int(snapshot.pending) == 0 and not bool(snapshot.running):
			return
	_expect(false, label + " completes within twelve physics frames")

func _spatial() -> Dictionary:
	return (main.surface_work_snapshot().spatial as Dictionary).duplicate()

func _stream() -> ContinentChunkStream:
	var stream := ContinentChunkStream.new()
	main.world_root.add_child(stream)
	stream.set_process(false)
	main._watch_surface_stream(stream)
	return stream

func _cell(stream: ContinentChunkStream, identity: String, top: float) -> Node3D:
	var imported := Node3D.new()
	stream.add_child(imported)
	var floor := StaticBody3D.new()
	floor.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	floor.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(10, 1, 10)
	shape.shape = box
	floor.add_child(shape)
	floor.position = Vector3(5, top - 0.5, 5)
	imported.add_child(floor)
	stream.cells[identity] = {"root": imported, "manifest": WorldManifest.new(),
		"entry": {"id": identity, "estimatedResidentBytes": 0,
			"bounds": {"min": [0, -10, 0], "max": [10, 20, 10]}}}
	return imported

func _actor(identity: int, at: Vector3) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	actor.actor_id = identity
	main.world_root.add_child(actor)
	actor.server_target = at
	actor.global_position = at
	actor.set_process(false)
	actor.set_physics_process(false)
	main.actor_nodes[identity] = actor
	state.actors[identity] = {"actor_id": identity, "map": state.current_map}
	# Both actors begin as grounded/cached. Only actual affected bounds or a
	# deliberate priority exception may force a new placement in this fixture.
	main._grounded_actors[identity] = true
	main._actor_surface_samples[identity] = Vector2(at.x, at.z)
	return actor

func _object(identity: int, at: Vector3) -> MapObject3D:
	var object := MapObject3D.new()
	object.object_id = identity
	object.collision_layer = 0
	object.collision_mask = 0
	main.world_root.add_child(object)
	object.global_position = at
	main.map_object_nodes[identity] = object
	return object

func _marker(identity: int, at: Vector3) -> MapMarker3D:
	var marker := MapMarker3D.new()
	main.world_root.add_child(marker)
	marker.configure({"marker_id": identity, "x": 0, "y": 0}, main.adapter, false)
	marker.global_position = at
	main.map_marker_nodes[identity] = marker
	return marker

func _placement(imported: Node3D, top: float) -> MeshInstance3D:
	var placed := MeshInstance3D.new()
	placed.name = "BoundPlacement"
	placed.mesh = BoxMesh.new()
	placed.position = Vector3(5, top + 0.5, 5)
	imported.add_child(placed)
	return placed

func _bind_hint(object: MapObject3D, identity: String) -> void:
	object.bound_node_name = "BoundPlacement"
	object.presentation = {"bind": {"chunk": identity, "node": "BoundPlacement"}}

func _expect_pick(object: MapObject3D, at: Vector3, label: String) -> void:
	var query := PhysicsRayQueryParameters3D.create(at + Vector3.UP * 20,
		at - Vector3.UP * 20, MapObject3D.PICK_LAYER)
	var hit: Dictionary = main.gameplay_world.direct_space_state.intersect_ray(query)
	_expect(MapObject3D.from_pick_collider(hit.get("collider")) == object, label)

func _run() -> void:
	main = load("res://src/app/main.tscn").instantiate() as Control
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	state.authenticated = false
	state.local_actor_id = -1
	state.selected_actor_id = -1
	state.combat_state = {}
	state.actors = {}
	root.get_node("Network").set_process(false)
	main.set_process(false)
	main.set_physics_process(false)
	main.set_process_input(false)
	main.set_process_unhandled_input(false)
	main.exterior_stream.set_process(false)
	main._clear_world_presentation()
	await _drain()
	state.current_map = "four_gates"
	main.adapter = CoordinateAdapter.new({"invertServerY": false})
	main.world_loader.manifest = WorldManifest.new()
	main._local_placement_logged = true
	var current := _stream()
	main.world_loader.world_root = current
	main._watch_chunk_surfaces()
	_expect(main.exterior_stream.residents_changed.is_connected(main._on_resident_surfaces_changed),
		"ordinary Main wiring retains the whole-root resident fallback beside chunk-specific callbacks")
	var near_actor := _actor(7101, Vector3(5, 100, 5))
	var far_actor := _actor(7102, Vector3(40, 91, 40))
	var near_object := _object(7201, Vector3(5, 100, 5))
	var far_object := _object(7202, Vector3(40, 81, 40))
	var near_marker := _marker(7301, Vector3(5, 100, 5))
	var far_marker := _marker(7302, Vector3(40, 71, 40))
	# Attach and signal in one turn: no manual settle may make terrain ready on
	# behalf of Main. The only barrier before placement is its production await.
	var cell := _cell(current, "same-id", 7.0)
	_placement(cell, 7.0)
	_bind_hint(near_object, "same-id")
	var before := _spatial()
	current.cell_ready.emit("same-id", cell)
	current.cell_ready.emit("same-id", cell)
	current.cell_ready.emit("same-id", cell)
	var queued: Dictionary = main.surface_work_snapshot()
	_expect(int(queued.pending) == 3 and bool(queued.running)
		and int(queued.queued.regions) == 1,
		"three live arrivals expose pending readiness and one coalesced region immediately")
	await _after_deferred_flush_started()
	_expect(int(main.surface_work_snapshot().pending) == 3
		and int(_spatial().batches) == int(before.batches)
		and is_equal_approx(near_actor.server_target.y, 100.0),
		"deferred dispatch keeps pending readiness and performs no batch before physics")
	await _wait_idle("arrival burst")
	var after := _spatial()
	_expect(int(after.batches) - int(before.batches) == 1
		and int(after.notifications) - int(before.notifications) == 3
		and int(after.full_batches) == int(before.full_batches),
		"chunk signals coalesce into one spatial batch without a connected fallback upgrading it to full")
	_expect(absf(near_actor.server_target.y - 7.02) < 0.01
		and absf(near_object.global_position.y - 7.05) < 0.01
		and absf(near_marker.global_position.y - 7.0) < 0.01,
		"newly registered physics grounds the actual actor, object and marker")
	_expect(is_equal_approx(far_actor.server_target.y, 91.0)
		and is_equal_approx(far_object.global_position.y, 81.0)
		and is_equal_approx(far_marker.global_position.y, 71.0),
		"grounded bystanders outside arriving bounds are not placed")
	_expect(int(after.actor_placement_attempts) - int(before.actor_placement_attempts) == 1
		and int(after.object_placement_attempts) - int(before.object_placement_attempts) == 2,
		"diagnostics count helper placement attempts rather than claiming physics rays")
	_expect(near_object.placement_bound(), "changed current-map cell binds its real scenery pick proxy")
	await _drain()
	_expect_pick(near_object, Vector3(5, 7.5, 5), "bound scenery resolves to the actual map object when picked")
	before = _spatial()
	main.exterior_stream.residents_changed.emit()
	_expect(bool(main.surface_work_snapshot().queued.full),
		"an actual whole-root resident signal deliberately requests the full fallback")
	await _wait_idle("whole-root fallback")
	_expect(int(_spatial().full_batches) - int(before.full_batches) == 1,
		"whole-root fallback completes independently of chunk-specific spatial batches")
	# Queue a neighbour arrival, then make that exact stream the active map and
	# rebase it before the physics flush. Repeated cell IDs must use live roots.
	var arriving := _stream()
	arriving.position = Vector3(60, 0, 0)
	var arriving_cell := _cell(arriving, "same-id", 13.0)
	_placement(arriving_cell, 13.0)
	var handoff_object := _object(7203, Vector3(105, 100, 5))
	_bind_hint(handoff_object, "same-id")
	arriving.cell_ready.emit("same-id", arriving_cell)
	arriving.position = Vector3(100, 0, 0)
	main.world_loader.world_root = arriving
	state.current_map = "whitehorn_range"
	state.actors[7101].map = state.current_map
	near_actor.server_target = Vector3(105, 100, 5)
	near_actor.global_position = near_actor.server_target
	main._actor_surface_samples[7101] = Vector2(105, 5)
	# A map handoff clears its old object/marker tables; the traveller survives.
	for object: MapObject3D in [near_object, far_object]:
		object.release_placement()
		main.map_object_nodes.erase(object.object_id)
		object.queue_free()
	for marker: MapMarker3D in [near_marker, far_marker]:
		main.map_marker_nodes.erase(marker.marker_id)
		marker.queue_free()
	main.exterior_stream.residents["four_gates"] = {"root": current,
		"manifest": WorldManifest.new()}
	await _wait_idle("rebased handoff")
	_expect(absf(near_actor.server_target.y - 13.02) < 0.01
		and absf(handoff_object.global_position.y - 13.05) < 0.01,
		"queued arrival uses the current stream transform and actor map at handoff")
	_expect(handoff_object.placement_bound(), "binding resolves the current root after a repeated-ID handoff")
	await _drain()
	_expect_pick(handoff_object, Vector3(105, 13.5, 5), "handoff picking binds the arriving map's actual placement")
	# An identity can leave the resident table after ready but before flush.
	before = _spatial()
	arriving.cell_ready.emit("same-id", arriving_cell)
	arriving.cells.erase("same-id")
	await _wait_idle("invalidated root")
	after = _spatial()
	_expect(int(after.invalidated_regions) - int(before.invalidated_regions) == 1
		and int(after.actor_placement_attempts) == int(before.actor_placement_attempts),
		"a no-longer-resident queued identity drains readiness without touching live actors")
	# The next ready restores a live identity. Arm the real old coroutine first,
	# then exercise Main's actual world clear and requeue before physics resumes.
	arriving.cells["same-id"] = {"root": arriving_cell, "manifest": WorldManifest.new(),
		"entry": {"id": "same-id", "estimatedResidentBytes": 0,
			"bounds": {"min": [0, -10, 0], "max": [10, 20, 10]}}}
	arriving.cell_ready.emit("same-id", arriving_cell)
	await _after_deferred_flush_started()
	var old_epoch: int = main._surface_refresh_epoch
	before = _spatial()
	main._clear_world_presentation()
	_expect(main._surface_refresh_epoch == old_epoch + 1
		and int(main.surface_work_snapshot().pending) == 0
		and not bool(main.surface_work_snapshot().running),
		"actual world clear cancels queued and physics-waiting surface readiness")
	state.current_map = "four_gates"
	state.actors = {}
	var replacement := _stream()
	replacement.position = Vector3(200, 0, 0)
	main.world_loader.world_root = replacement
	main.world_loader.manifest = WorldManifest.new()
	var replacement_cell := _cell(replacement, "same-id", 19.0)
	var new_actor := _actor(7103, Vector3(205, 100, 5))
	replacement.cell_ready.emit("same-id", replacement_cell)
	await _after_deferred_flush_started()
	_expect(int(main.surface_work_snapshot().pending) == 1
		and bool(main.surface_work_snapshot().running),
		"new session retains its own pending flush while the cancelled coroutine still waits")
	await _wait_idle("clear then requeue")
	after = _spatial()
	_expect(int(after.batches) - int(before.batches) == 1
		and int(after.notifications) - int(before.notifications) == 1
		and absf(new_actor.server_target.y - 19.02) < 0.01,
		"old epoch cannot consume or clear the replacement session's batch or placement")
	# All synthetic roots have no workers. Drain the final callback, then use
	# normal Main clear/free ownership before clearing remaining static caches.
	main._clear_world_presentation()
	await _drain()
	main.process_mode = Node.PROCESS_MODE_DISABLED
	main.queue_free()
	await _drain()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await _drain()
	print("Main async surface refresh: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)
