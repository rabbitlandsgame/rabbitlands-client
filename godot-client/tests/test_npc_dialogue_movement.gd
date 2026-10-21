extends SceneTree
## Exercise real movement dispatch while the NPC dialogue panel is visible.

var failures := 0
var sent_moves: Array[Vector2i] = []

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var network: Node = root.get_node("Network")
	network.set_script(load("res://tests/fixtures/map_movement_network_probe.gd"))
	network.set_process(false)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	var state: Node = root.get_node("AppState")
	network.movement_requested.connect(func(tile: Vector2i) -> void: sent_moves.append(tile))
	(main.get("game_view") as Control).show()
	(main.get("login_panel") as Control).hide()
	state.authenticated = true
	state.local_actor_id = 7
	state.actors = {7: {"actor_id": 7, "x": 20, "y": 20, "health": 20}}
	var actor := ReplicatedActor3D.new()
	(main.get("world_root") as Node3D).add_child(actor)
	(main.get("actor_nodes") as Dictionary)[7] = actor
	var focus := root.gui_get_focus_owner()
	if focus != null:
		focus.release_focus()

	state.call("_on_packet", EloriaProtocol.ServerMessage.NPC_TEXT, "Hello.".to_utf8_buffer())
	var dialogue: Control = main.get("dialogue_panel") as Control
	_expect(dialogue.visible, "NPC dialogue is visible")
	Input.action_press("move_north")
	main.call("_update_keyboard_movement")
	Input.action_release("move_north")
	_expect(sent_moves.size() == 1 and bool(main.get("_keyboard_moving")),
		"keyboard movement sends a walking target while dialogue is open")
	_expect(dialogue.visible, "starting a walk keeps the dialogue open")
	main.call("_clear_keyboard_movement_tracking")
	var intro: Node = main.get("character_intro")
	for phase: StringName in [&"conversation", &"return"]:
		intro.set("greeting_phase", phase)
		sent_moves.clear()
		Input.action_press("move_north")
		main.call("_update_keyboard_movement")
		Input.action_release("move_north")
		_expect(sent_moves.size() == 1, "Nash's %s phase permits walking" % phase)
		main.call("_clear_keyboard_movement_tracking")
	intro.set("greeting_phase", &"")

	# Dispatch an actual world click through the same handler as the viewport.
	sent_moves.clear()
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = (main.get("viewport_container") as Control).size * 0.5
	main.call("_on_world_gui_input", click)
	_expect(sent_moves.size() == 1, "a world click still walks with dialogue open")
	_expect(dialogue.visible, "clicking a walking destination keeps dialogue open")

	_expect(not bool(main.call("_map_input_blocked")),
		"dialogue allows movement from the maps")
	var trade: Control = main.get("trade_panel") as Control
	trade.show()
	_expect(bool(main.call("_map_input_blocked")), "trade continues to block map movement")
	sent_moves.clear()
	Input.action_press("move_north")
	main.call("_update_keyboard_movement")
	Input.action_release("move_north")
	_expect(sent_moves.is_empty(), "trade continues to block keyboard movement")
	trade.hide()

	state.call("_on_packet", EloriaProtocol.ServerMessage.CLOSE_NPC_MENU, PackedByteArray())
	_expect(not dialogue.visible and not bool((state.get("npc_dialogue") as Dictionary).get("open")),
		"the server's out-of-range close hides the dialogue")
	main.queue_free()
	await process_frame
	print("NPC dialogue movement tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
