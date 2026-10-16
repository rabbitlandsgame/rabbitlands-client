extends SceneTree
## Creature beacons follow rendered motion through the packet/state/UI path.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var state: Node = root.get_node("AppState")
	state.set("authenticated", true)
	state.set("current_map", "four_gates")
	main.set("loaded_server_map", "four_gates")
	var adapter := CoordinateAdapter.new()
	main.set("adapter", adapter)
	var world: Node3D = main.get("world_root")
	var slope := StaticBody3D.new()
	slope.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	slope.collision_mask = 0
	slope.position.y = 2.0
	slope.rotation.z = deg_to_rad(10.0)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(30, 0.1, 30)
	collision.shape = shape
	slope.add_child(collision)
	world.add_child(slope)
	await physics_frame
	var nodes: Dictionary = main.get("actor_nodes")
	var actors: Dictionary = state.get("actors")
	var dto := {"actor_id": 60000, "x": 2, "y": 3, "rotation": 0,
		"command": 0, "map": "four_gates", "footprint": Vector2i(3, 2)}
	actors[60000] = dto
	# A real replicated actor exercises its movement interpolation and footprint
	# centre without loading a creature model or changing the animation system.
	var actor := ReplicatedActor3D.new()
	world.add_child(actor)
	actor.actor_id = 60000
	actor.set_footprint(Vector2i(3, 2))
	actor.apply_server_state(dto, adapter, true)
	actor._physics_process(0.016)
	actor.set_physics_process(false)
	nodes[60000] = actor

	state.call("_on_packet", 90, _marker(520, 2, 3, 60000))
	var markers: Dictionary = main.get("map_marker_nodes")
	var marker: MapMarker3D = markers[520]
	var sparks_id: int = marker.get_node("RisingSparks").get_instance_id()
	_expect(marker.target_actor_id == 60000 and marker.global_position.is_equal_approx(actor.global_position),
		"an explicit actor16 link centres the beacon on a large creature")
	_expect((state.get("map_markers") as Dictionary)[520].actor_id == 60000,
		"packet reduction preserves the target identity")

	actor.apply_server_state({"x": 5, "y": 3, "rotation": 90, "command": 22}, adapter)
	actor.set_physics_process(false)
	for frame: int in range(4):
		actor._physics_process(0.05)
		main.call("_update_attached_map_markers")
		_expect(marker.global_position.is_equal_approx(actor.global_position),
			"the beacon follows interpolated feet at movement frame %d" % frame)
		if frame == 0:
			_expect(not marker.global_position.is_equal_approx(actor.server_target),
				"the beacon does not jump ahead to the next server tile")
	actor.rotation.y = 1.7
	actor.scale = Vector3.ONE * 2.0
	main.call("_update_attached_map_markers")
	_expect(marker.rotation == Vector3.ZERO and marker.scale == Vector3.ONE,
		"creature facing and model scale do not rotate or stretch the beacon")
	var projected: Array = main.call("_current_map_markers")
	_expect(projected[0].position.is_equal_approx(actor.global_position),
		"the full map uses the same moving world position")
	var overlay: Control = main.get("map_marker_overlay")
	_expect((overlay.call("_marker_position", projected[0]) as Vector3).is_equal_approx(actor.global_position),
		"the full-map pin and hover label project the moving position")
	var glow: MeshInstance3D = marker.get_node("GroundGlow")
	var vertices: PackedVector3Array = glow.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for vertex: Vector3 in vertices:
		var point: Vector3 = glow.global_transform * vertex
		var ground: Variant = GroundDrape.surface_height(world.get_world_3d().direct_space_state, point.x, point.z)
		_expect(ground != null and absf(point.y - float(ground) - GroundDrape.CLEARANCE) < 0.002,
			"the moving glow stays on the slope around its whole circumference")
	var minimap: Array = main.call("_collect_minimap_marks")
	var pins: Array = minimap.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"marker")
	_expect(pins.size() == 1 and pins[0].position.is_equal_approx(actor.global_position),
		"the minimap follows the same creature")

	# Refreshes preserve particles and can retarget before the new actor spawns.
	state.call("_on_packet", 90, _marker(520, 8, 9, 60001))
	_expect(marker.server_tile == Vector2i(8, 9) and _same_horizontal(marker.global_position, adapter.tile_center(8, 9)),
		"a target arriving later uses its authoritative tile in the meantime")
	var second := Node3D.new()
	world.add_child(second)
	second.position = Vector3(10.25, 2.0, 12.75)
	nodes[60001] = second
	actors[60001] = {"map": "four_gates"}
	main.call("_update_attached_map_markers")
	_expect(marker.global_position == second.global_position and marker.get_node("RisingSparks").get_instance_id() == sparks_id,
		"late actor arrival reattaches the existing particle stream")
	actors[60001] = {"map": "mirrorhold"}
	second.position.x += 4.0
	main.call("_update_attached_map_markers")
	_expect(marker.global_position != second.global_position,
		"an actor on a neighbouring map cannot pull the beacon away")
	second.free()
	main.call("_update_attached_map_markers")
	_expect(is_instance_valid(marker), "a despawned target cannot break marker updates")
	nodes.erase(60001)
	actors.erase(60001)

	state.call("_on_packet", 90, _marker(520, 4, 5))
	main.call("_update_attached_map_markers")
	_expect(marker.target_actor_id == -1 and _same_horizontal(marker.global_position, adapter.tile_center(4, 5)),
		"a location marker clears the previous attachment and remains fixed")
	for suffix: PackedByteArray in [PackedByteArray([1]), PackedByteArray([1, 2, 3])]:
		_expect(EloriaProtocol.decode_map_marker(_marker(521, 1, 2) + suffix).type == "invalid",
			"truncated or oversized actor links are rejected")
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	await create_timer(0.3).timeout
	await process_frame
	_expect(markers.is_empty(), "server removal clears the attached effect")
	state.set("authenticated", false)
	main.queue_free()
	await process_frame
	print("map marker attachment: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _marker(id: int, x: int, y: int, actor_id := -1) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(6)
	payload.encode_u16(0, id)
	payload.encode_u16(2, x)
	payload.encode_u16(4, y)
	payload.append_array("four_gates".to_utf8_buffer() + PackedByteArray([0]))
	payload.append_array("Protect the runner".to_utf8_buffer() + PackedByteArray([0]))
	if actor_id >= 0:
		payload.resize(payload.size() + 2)
		payload.encode_u16(payload.size() - 2, actor_id)
	return payload

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)

func _same_horizontal(a: Vector3, b: Vector3) -> bool:
	return Vector2(a.x, a.z).is_equal_approx(Vector2(b.x, b.z))
