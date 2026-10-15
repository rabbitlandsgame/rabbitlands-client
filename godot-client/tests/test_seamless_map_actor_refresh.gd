extends SceneTree

## CHANGE_MAP reaches Main before the arrival actor packet. Re-presenting the
## carried source record at that point must not replace its terrain height.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var state: Node = root.get_node("AppState")
	var world: Node3D = main.get_node("%WorldRoot")
	var stream: ExteriorRegionStream = main.get("exterior_stream")
	var source_root := Node3D.new()
	world.add_child(source_root)
	var source_manifest := WorldManifest.new()
	source_manifest.data = {"coordinateTransform": {"walkingHeight": 121.494}}
	stream.residents["landfall"] = {"root": source_root, "manifest": source_manifest}
	main.set("adapter", CoordinateAdapter.new({"walkingHeight": 121.494}))
	main.set("loaded_server_map", "warrenmead")
	main.set("_continuous_map_handoff", true)
	state.set("current_map", "warrenmead")
	state.set("local_actor_id", 4242)
	var record := {"actor_id": 4242, "x": 3, "y": 4, "map": "landfall",
		"rotation": 0, "actor_type": 1, "kind": 1, "name": "Traveller",
		"health": 20, "max_health": 20}
	state.set("actors", {4242: record})
	var actor := ReplicatedActor3D.new()
	actor.actor_id = 4242
	world.add_child(actor)
	actor.set_process(false)
	actor.server_target = Vector3(3.5, 137.02, -4.5)
	actor.global_position = actor.server_target
	var nodes: Dictionary = main.get("actor_nodes")
	nodes[4242] = actor
	var before := actor.global_position
	var camera: IsometricCameraController = main.get("camera_rig")
	camera.set_focus(before)
	state.set("authenticated", true)
	main.call("_on_state_changed", &"map")
	_expect(actor.global_position.is_equal_approx(before),
		"CHANGE_MAP preserves the carried actor position before its arrival packet")
	_expect(is_equal_approx(actor.server_target.y, before.y),
		"a seamless map notification cannot drop the traveller to flat fallback height")
	_expect(camera.focus.is_equal_approx(before),
		"the crossing notification keeps the camera at the carried terrain height")
	_expect((main.get("_actor_surface_samples") as Dictionary).is_empty(),
		"the source record is not grounded again during the map notification")

	# The subsequent actor packet still updates its position and terrain height.
	var ground := StaticBody3D.new()
	ground.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(20, 1, 20)
	shape.shape = box
	ground.add_child(shape)
	world.add_child(ground)
	ground.position = Vector3(4.5, 136.9, -4.5)
	await physics_frame
	await process_frame
	record["map"] = "warrenmead"
	record["x"] = 4
	main.call("_sync_world", {4242: true})
	_expect(is_equal_approx(actor.server_target.x, 4.5)
		and absf(actor.server_target.y - 137.42) < 0.01,
		"the destination actor packet still samples the destination ground")

	# Ordinary changes retain their full refresh, including fallback placement.
	ground.free()
	await physics_frame
	await process_frame
	(main.get("_actor_surface_samples") as Dictionary).clear()
	main.set("_continuous_map_handoff", false)
	main.call("_on_state_changed", &"map")
	_expect(absf(actor.server_target.y - 121.514) < 0.01,
		"an ordinary map change still presents its current actor table")
	state.set("authenticated", false)
	state.set("actors", {})
	stream.residents.clear()
	main.queue_free()
	await process_frame
	print("seamless map actor refresh: %d failures" % failures)
	quit(1 if failures > 0 else 0)

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)
