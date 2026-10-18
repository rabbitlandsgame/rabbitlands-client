extends SceneTree
const Trail := preload("res://src/world/quest_trail_3d.gd")
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var ground := StaticBody3D.new()
	ground.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	ground.rotation.z = 0.1
	ground.position.y = 2.0
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(120, 0.1, 120)
	collision.shape = box
	ground.add_child(collision)
	world.add_child(ground)
	var trail := Trail.new()
	world.add_child(trail)
	await physics_frame
	var adapter := CoordinateAdapter.new()
	var route: Array = []
	for x: int in range(35):
		route.append([x, 0])
	var state := {"active": true, "tutorial": "watchpost", "map": "landfall", "route": route}
	trail.apply_state(state, adapter, "landfall")
	trail.update_trail(0.3, adapter.tile_center(0, 0))
	expect(trail._visible.size() > 3 and trail.points.size() == 35, "accepted quest lays a spaced ground trail")
	for arrow: MeshInstance3D in trail._visible.values():
		var vertices: PackedVector3Array = arrow.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		for vertex: Vector3 in vertices:
			var point := arrow.global_transform * vertex
			var height: Variant = GroundDrape.surface_height(world.get_world_3d().direct_space_state, point.x, point.z)
			expect(height != null and absf(point.y - float(height) - 0.12) < 0.003, "chevron follows the sloped ground")
		break
	var before := trail.map_marks().size()
	trail.update_trail(0.3, adapter.tile_center(20, 0))
	expect(trail.map_marks().size() < before, "both maps retain the path ahead as the player progresses")
	trail.apply_state(state, adapter, "crownwater")
	expect(trail.points.is_empty() and trail.map_marks().is_empty(), "trail cannot leak onto another map")
	state.paused = true
	trail.apply_state(state, adapter, "landfall")
	expect(trail.points.is_empty(), "paused quest has no trail")
	trail.apply_state({"active": false}, adapter, "landfall")
	expect(trail.map_marks().is_empty() and trail._visible.is_empty(), "declining or completing clears ground and map markers")
	# The wire parser rejects malformed route coordinates before the trail sees them.
	var dto := {"version": 1, "active": true, "tutorial": "watchpost", "stage": 2, "total": 4,
		"chapter": "HELP FOR THE WATCHPOST", "paused": false,
		"scene": 2, "count": 0, "required": 2, "key": "sage", "title": "Gather Sage", "hint": "Follow the trail",
		"control": "world", "item": "Sage", "map": "landfall", "target_id": "sage_meadow", "target": [34, 0],
		"flags": {"crafted": false, "prepared": false, "repaired": false, "lit": false}, "route": route}
	expect(EloriaProtocol.decode_lantern(JSON.stringify(dto).to_utf8_buffer()).type == "lantern_tutorial", "valid route survives packet decoding")
	for invalid: Variant in [[[1]], [[0, INF]], [[0, 0.5]], "bad"]:
		dto.route = invalid
		expect(EloriaProtocol.decode_lantern(JSON.stringify(dto).to_utf8_buffer()).type == "invalid", "malformed route is rejected")
	world.queue_free()
	await process_frame
	print("quest trail: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
