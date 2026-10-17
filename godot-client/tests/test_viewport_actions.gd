extends SceneTree
## Exercise production input routing and command encoding with deterministic
## pick results and a recording transport, without maps or a live server.

class RecordingNetwork extends "res://src/network/network_client.gd":
	var frames: Array[PackedByteArray] = []

	func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
		frames.append(frame)
		return OK

var failures := 0
var main: Control
var state: Node
var network: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	main.set_script(load("res://tests/fixtures/viewport_actions_main.gd"))
	root.add_child(main)
	await process_frame
	main.set_process(false)
	(main.get("game_view") as Control).show()
	(main.get("login_panel") as Control).hide()
	state = root.get_node("AppState")
	network = root.get_node("Network")
	network.set_script(RecordingNetwork)
	network.set_process(false)
	state.set("local_actor_id", 1)
	state.set("actors", {
		1: {"actor_id": 1, "kind": 1, "alive": true},
		2: {"actor_id": 2, "kind": 1, "alive": true},
		3: {"actor_id": 3, "kind": 2, "alive": true},
		4: {"actor_id": 4, "kind": 3, "alive": true},
		5: {"actor_id": 5, "kind": 5, "name_colour": 4, "alive": true},
		6: {"actor_id": 6, "kind": 1, "alive": false},
		7: {"actor_id": 7, "kind": 3, "alive": false},
		8: {"actor_id": 8, "kind": 0, "alive": true}})
	main.set("picked_actor", 2)
	_check_cycle()
	_check_actions()
	_check_camera()
	main.queue_free()
	await process_frame
	print("viewport actions tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _mouse(button: MouseButton, pressed := true,
		position := Vector2(640, 360)) -> InputEventMouseButton:
	var event := InputEventMouseButton.new()
	event.button_index = button
	event.pressed = pressed
	event.position = position
	main.call("_on_world_gui_input", event)
	return event

func _check_cycle() -> void:
	# Selection elsewhere must not determine what is available under the mouse.
	state.set("selected_actor_id", 3)
	_check_cycle_case("player", ["walk", "trade", "attack", "look"])
	main.set("picked_actor", 3)
	_check_cycle_case("NPC", ["walk", "talk"])
	main.set("picked_actor", 4)
	_check_cycle_case("creature", ["walk", "attack"])
	main.set("picked_actor", 5)
	_check_cycle_case("summon", ["walk", "attack", "talk"])
	main.set("picked_actor", 6)
	_check_cycle_case("dead player", ["walk", "look"])
	main.set("picked_actor", 7)
	_check_cycle_case("dead creature", ["walk"])
	main.set("picked_actor", 8)
	_check_cycle_case("unknown actor", ["walk"])
	main.set("picked_actor", 1)
	_check_cycle_case("self", ["walk", "look"])
	state.set("ground_bags", {9: {"x": 10, "y": 20}})
	(state.get("actors") as Dictionary)[1].merge({"x": 10, "y": 20})
	_check_cycle_case("bag at own feet", ["walk", "pick", "look"])
	state.set("ground_bags", {})
	main.set("picked_actor", 2)
	state.set("lantern_tutorial", {
		"active": true, "tutorial": "borrowed_sky", "talk_actor_ids": [2]})
	_check_cycle_case("tutorial companion", ["walk", "talk", "look"])
	state.set("lantern_tutorial", {})
	main.set("picked_actor", -1)
	_check_cycle_case("ground", ["walk"])
	main.set("picked_bag", 9)
	_check_cycle_case("ground bag", ["walk", "pick"])
	var object := MapObject3D.new()
	object.object_id = 17
	object.kind = EloriaProtocol.MAP_OBJECT_HARVEST
	main.set("picked_object", object)
	_check_cycle_case("bag in front of resource", ["walk", "pick"])
	main.set("picked_bag", -1)
	_check_cycle_case("resource", ["walk", "harvest", "look"])
	object.kind = EloriaProtocol.MAP_OBJECT_INTERACTIVE
	_check_cycle_case("interactive object", ["walk", "use", "look"])
	object.kind = EloriaProtocol.MAP_OBJECT_EXIT
	_check_cycle_case("exit", ["walk", "use", "look"])
	main.set("picked_actor", 3)
	_check_cycle_case("NPC in front of object", ["walk", "talk"])
	main.set("picked_object", null)
	object.free()
	# A change of hovered target also skips tools from the old target's cycle.
	main.set("_interaction_mode", "trade")
	_mouse(MOUSE_BUTTON_RIGHT)
	_expect(str(main.get("_interaction_mode")) == "talk",
		"moving from a player to an NPC skips unavailable tools")
	main.set("picked_actor", -1)
	_mouse(MOUSE_BUTTON_RIGHT)
	_expect(str(main.get("_interaction_mode")) == "walk",
		"moving onto ground returns to Move")
	# Input is local to the viewport control and must be scaled before picking.
	var viewport: SubViewport = main.get("main_viewport") as SubViewport
	var original_size: Vector2i = viewport.size
	viewport.size = Vector2i(640, 360)
	var position := Vector2(173, 91)
	var viewport_position: Vector2 = main.call("_local_viewport_position", position)
	main.set("actors_by_position", {viewport_position: 3})
	_mouse(MOUSE_BUTTON_RIGHT, true, position)
	_expect(str(main.get("_interaction_mode")) == "talk", "cycle picks at the click position")
	viewport.size = original_size
	main.set("actors_by_position", {})
	main.set("picked_actor", 2)
	_expect((network.get("frames") as Array).is_empty(), "context changes never send a command")
	main.set("_interaction_mode", "harvest")
	var escape := InputEventAction.new()
	escape.action = "cancel"
	escape.pressed = true
	main.call("_unhandled_input", escape)
	_expect(str(main.get("_interaction_mode")) == "walk", "Escape returns to Move")
	_expect(str(main.get("_inventory_tool")) == "grab", "Escape also puts the inventory tool down")

func _check_cycle_case(label: String, actions: Array[String]) -> void:
	main.set("_interaction_mode", "walk")
	for index: int in actions.size() * 2:
		var wanted: String = actions[(index + 1) % actions.size()]
		_mouse(MOUSE_BUTTON_RIGHT)
		_mouse(MOUSE_BUTTON_RIGHT, false)
		_expect(str(main.get("_interaction_mode")) == wanted,
			"%s: right click selects %s once per click" % [label, wanted])
		_expect((network.get("frames") as Array).is_empty(),
			"cycling %s does not activate the actor" % wanted)
		_expect(MouseCursors.choose({"over_world": true, "mode": wanted})
			== int(MouseCursors.ACTION_CURSORS[wanted]), "%s has its action cursor" % wanted)
		if wanted == "use":
			_expect(str(main.get("_inventory_tool")) == "use", "Use arms item use")
		elif wanted == "look":
			_expect(str(main.get("_inventory_tool")) == "inspect", "Look arms item inspection")

func _check_actions() -> void:
	main.set("_interaction_mode", "trade")
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.trade_with(2), "Trade asks the clicked player")
	_mouse(MOUSE_BUTTON_RIGHT)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.attack_actor(2), "Fight attacks the clicked player")
	_mouse(MOUSE_BUTTON_RIGHT)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.look_at_player(2), "Look inspects the clicked player")
	main.set("_interaction_mode", "use")
	main.call("_set_inventory_tool", "use")
	_mouse(MOUSE_BUTTON_LEFT)
	_expect((network.get("frames") as Array).is_empty(), "Use cannot attack a player")
	state.set("inventory", {0: {"image_id": 1, "quantity": 3, "inventory_usable": true}})
	main.call("_on_inventory_slot_pressed", 0)
	var frames: Array = network.get("frames") as Array
	_expect(frames.has(EloriaProtocol.use_inventory_item(0)), "Use applies the inventory use-item command")
	frames.clear()
	main.set("picked_actor", -1)
	var object := MapObject3D.new()
	object.object_id = 17
	object.kind = EloriaProtocol.MAP_OBJECT_INTERACTIVE
	main.set("picked_object", object)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.use_map_object(17), "Use activates a world object")
	main.set("picked_object", null)
	main.set("picked_bag", 9)
	main.set("_interaction_mode", "walk")
	_mouse(MOUSE_BUTTON_RIGHT)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.inspect_bag(9), "Pick up opens the clicked ground bag")
	state.call("close_ground_bag")
	main.set("picked_bag", -1)
	main.set("picked_object", object)
	object.kind = EloriaProtocol.MAP_OBJECT_HARVEST
	main.set("_interaction_mode", "walk")
	_mouse(MOUSE_BUTTON_RIGHT)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.harvest(17), "Harvest gathers the clicked resource")
	main.set("picked_object", null)
	main.set("picked_actor", 3)
	main.set("_interaction_mode", "walk")
	_mouse(MOUSE_BUTTON_RIGHT)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.touch_actor(3), "Talk greets the clicked NPC")
	main.set("picked_actor", 2)
	main.set("_interaction_mode", "attack")
	_mouse(MOUSE_BUTTON_RIGHT)
	_mouse(MOUSE_BUTTON_LEFT)
	_expect_frame(EloriaProtocol.look_at_player(2), "Look inspects the clicked player")
	main.set("picked_actor", -1)
	for mode: String in MouseCursors.WORLD_ACTIONS:
		if mode == "walk":
			continue
		main.set("_interaction_mode", mode)
		_mouse(MOUSE_BUTTON_LEFT)
		_expect((network.get("frames") as Array).is_empty(), "%s cannot move on a missed target" % mode)
	object.free()

func _check_camera() -> void:
	var rig: IsometricCameraController = main.get("camera_rig") as IsometricCameraController
	rig.set_focus(Vector3(8, 12, -4))
	var yaw := rig.yaw_degrees
	var motion := InputEventMouseMotion.new()
	motion.relative = Vector2(40, -12)
	_mouse(MOUSE_BUTTON_RIGHT)
	main.call("_on_world_gui_input", motion)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "right drag cannot rotate")
	_mouse(MOUSE_BUTTON_MIDDLE)
	main.call("_on_world_gui_input", motion)
	_expect(not is_equal_approx(rig.yaw_degrees, yaw)
		and rig.global_position.is_equal_approx(rig.focus), "middle drag rotates without panning")
	yaw = rig.yaw_degrees
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_MIDDLE
	main.call("_input", release)
	main.call("_on_world_gui_input", motion)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "release over another window ends rotation")
	_mouse(MOUSE_BUTTON_MIDDLE)
	main.notification(MainLoop.NOTIFICATION_APPLICATION_FOCUS_OUT)
	main.call("_on_world_gui_input", motion)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "focus loss ends rotation")
	var distance := rig.distance
	_mouse(MOUSE_BUTTON_WHEEL_UP)
	_expect(rig.distance < distance and rig.global_position.is_equal_approx(rig.focus),
		"wheel scrolling zooms without moving the focus")
	var player := Node3D.new()
	(main.get("world_root") as Node3D).add_child(player)
	main.set("actor_nodes", {1: player})
	for point: Vector3 in [Vector3(16, 20, 4), Vector3(-8, 24, 12)]:
		player.global_position = point
		main.call("_update_local_actor_follow")
		_expect(rig.focus.is_equal_approx(point) and rig.global_position.is_equal_approx(point),
			"the camera follows the player's full position after camera input")

func _expect_frame(wanted: PackedByteArray, label: String) -> void:
	var frames: Array = network.get("frames") as Array
	_expect(frames.size() == 1 and frames[0] == wanted, label + " (got %s)" % str(frames))
	frames.clear()

func _expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
