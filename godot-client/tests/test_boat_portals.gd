extends SceneTree
## Actual authored hull/sail geometry through the production hover and click
## rays, with outgoing use requests captured by a loopback socket.

var failures := 0
var main: Control
var lantern: Node3D
var camera: Camera3D
var state: Node
var network: Node
var receiver: StreamPeerTCP
var server := TCPServer.new()
var ferry: MapObject3D

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func settle() -> void:
	await physics_frame
	await process_frame
	await physics_frame
	await process_frame

func screen_at(point: Vector3, direction := Vector3(0, 0, 1)) -> Vector2:
	camera.global_position = point + direction * 18.0
	camera.look_at(point)
	return camera.unproject_position(point)

func check_pick(point: Vector3, direction: Vector3, available: bool, label: String) -> Vector2:
	var screen := screen_at(point, direction)
	var picked: MapObject3D = main._pick_map_object(screen)
	expect((picked == ferry) if available else (picked == null), label + " pick")
	var cursor := MouseCursors.choose(main._cursor_context_at(screen))
	expect(cursor == (MouseCursors.ENTER if available else MouseCursors.WALK), label + " cursor")
	return screen

func click_and_check(screen: Vector2, label: String, inspect := false) -> void:
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.alt_pressed = inspect
	main._handle_world_click(click, screen)
	var expected := EloriaProtocol.look_at_map_object(ferry.object_id) if inspect else EloriaProtocol.use_map_object(ferry.object_id)
	var deadline := Time.get_ticks_msec() + 2000
	while receiver.get_available_bytes() < expected.size() and Time.get_ticks_msec() < deadline:
		receiver.poll()
		await process_frame
	var actual := receiver.get_data(receiver.get_available_bytes())
	expect(actual[0] == OK and actual[1] == expected, label + " sends the boarding object's expected request")

func run() -> void:
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.get_node("GameView").show()
	camera = main.camera_rig.get_node("Camera")
	state = root.get_node("AppState")
	network = root.get_node("Network")
	network.set_process(false)
	expect(server.listen(0, "127.0.0.1") == OK, "loopback listener starts")
	network._peer.connect_to_host("127.0.0.1", server.get_local_port())
	var deadline := Time.get_ticks_msec() + 2000
	while not server.is_connection_available() and Time.get_ticks_msec() < deadline:
		network._peer.poll()
		await process_frame
	if not server.is_connection_available():
		expect(false, "loopback connection succeeds")
		finish()
		return
	receiver = server.take_connection()
	network._peer.poll()

	lantern = load("res://src/world/lantern_scene.gd").new()
	main.world_root.add_child(lantern)
	main.lantern_scene = lantern
	lantern.set_process(false)
	var imported := Node3D.new()
	main.world_root.add_child(imported)
	lantern.configure(imported, WorldManifest.new())
	state.current_map = "lantern_reach"
	var ferry_id := -1
	for target: Dictionary in lantern.layout.targets:
		if target.id == "ferry":
			ferry_id = int(target.objectId)
			state.map_objects = {ferry_id: {"object_id": ferry_id, "kind": 2,
				"x": target.tile[0], "y": target.tile[1], "label": "Information", "detail": ""}}
	main._sync_map_objects()
	ferry = main.map_object_nodes[ferry_id]
	var saved_tile := ferry.server_tile
	lantern.apply_state({"active": true, "key": "arrival", "flags": {}})
	await settle()
	check_pick(lantern.boat.global_position + Vector3(.7, 4.2, .6), Vector3(0, 0, 1), false, "offshore boat")
	expect(not ferry.offers_map_change(), "boarding point does not promise early departure")

	lantern.apply_state({"active": true, "key": "depart", "flags": {"lit": true}})
	await settle()
	check_pick(lantern.boat.global_position + Vector3(.7, 4.2, .6), Vector3(0, 0, 1), false, "boat still approaching")
	lantern._process(30.0)
	await settle()
	var sail: Vector3 = lantern.boat.global_position + Vector3(.7, 4.2, .6)
	var hull: Vector3 = lantern.boat.global_position + Vector3(1.8, 1.0, -1.0)
	await click_and_check(check_pick(sail, Vector3(0, 0, 1), true, "sail front"), "sail front")
	await click_and_check(check_pick(sail, Vector3(0, 0, -1), true, "sail back"), "sail back")
	await click_and_check(check_pick(hull, Vector3(1, 0, 0), true, "hull"), "hull")
	main._alt_attack_preview = true
	var inspect_screen := screen_at(sail)
	expect(MouseCursors.choose(main._cursor_context_at(inspect_screen)) == MouseCursors.EYE, "Alt shows inspection over the sail")
	await click_and_check(inspect_screen, "Alt sail click", true)
	main._alt_attack_preview = false
	check_pick(lantern.boat.global_position + Vector3(3.5, 4.2, 0), Vector3(0, 0, 1), false, "empty space beside sail")
	expect(ferry.server_tile == saved_tile, "clicks retain the walkable boarding tile")
	var dock_screen := screen_at(ferry.global_position + Vector3(0, .6, 0))
	expect(main._pick_map_object(dock_screen) == ferry, "existing boarding point remains clickable")
	expect(MouseCursors.choose(main._cursor_context_at(dock_screen)) == MouseCursors.ENTER, "boarding point also offers door cursor")

	var original_body: StaticBody3D = lantern.boat_pick_body
	main._sync_map_objects()
	expect(lantern.boat_pick_body == original_body, "object refresh does not duplicate boat colliders")
	lantern.apply_state({"active": true, "key": "buy", "flags": {"lit": true}})
	await settle()
	check_pick(sail, Vector3(0, 0, 1), false, "unfinished dock lesson")
	lantern.apply_state({"active": false, "key": "depart", "flags": {"lit": true}})
	await settle()
	check_pick(sail, Vector3(0, 0, 1), false, "inactive tutorial")
	lantern.initialized = false
	lantern.apply_state({"active": true, "key": "depart", "flags": {"lit": true}})
	await settle()
	check_pick(sail, Vector3(0, 0, 1), true, "reconnected departure")
	state.map_objects = {}
	main._sync_map_objects()
	await settle()
	expect(not is_instance_valid(original_body), "withdrawn server object removes its boat collider")
	expect(main._pick_map_object(screen_at(sail)) == null, "removed departure is no longer clickable")
	finish()

func finish() -> void:
	network._peer.disconnect_from_host()
	server.stop()
	main.queue_free()
	await process_frame
	print("test_boat_portals: ", "all checks passed" if failures == 0 else "%d failures" % failures)
	quit(failures)
