extends SceneTree
## Held keyboard directions (keyboard_intent_v1): MOVE_TO until the server
## says it takes them, then the direction on change, on a new epoch and as a
## keep-alive, and a release when the keys go up.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _intent_state(enabled: bool, epoch: int) -> PackedByteArray:
	var payload := PackedByteArray([1, 1 if enabled else 0, epoch, 0xe8, 0x03, 0xb8, 0x0b])
	return payload

func _press_north(main: Control) -> void:
	Input.action_press("move_north")
	main.call("_update_keyboard_movement")

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
	var frames: Array = network.get("sent_frames")

	# Before the server says anything: today's MOVE_TO, four tiles ahead.
	_press_north(main)
	_expect(frames.size() == 1 and int(frames[0][0]) == EloriaProtocol.ClientMessage.MOVE_TO,
		"without the server's word a held key sends MOVE_TO")
	Input.action_release("move_north")
	main.call("_update_keyboard_movement")
	frames.clear()

	# The server takes held directions, epoch 2.
	state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT, _intent_state(true, 2))
	_expect(bool(network.get("move_intent_enabled")) and int(network.get("move_intent_epoch")) == 2,
		"the intent state is applied")
	_press_north(main)
	_expect(frames.size() == 1, "a held key sends one intent")
	var held: PackedByteArray = frames[0] if frames.size() > 0 else PackedByteArray()
	_expect(held.size() == 6 and int(held[0]) == 254 and int(held[3]) == 2 and int(held[4]) < 8,
		"the intent carries the epoch and one of the eight directions")
	main.call("_update_keyboard_movement")
	_expect(frames.size() == 1, "the same direction is not sent again before the keep-alive")
	_expect(not frames.any(func(f: PackedByteArray) -> bool:
			return int(f[0]) == EloriaProtocol.ClientMessage.MOVE_TO),
		"no MOVE_TO while the server steps held directions")

	# A map change: the server's new epoch, and the direction goes again under it.
	state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT, _intent_state(true, 3))
	main.call("_update_keyboard_movement")
	_expect(frames.size() == 2 and int(frames[1][3]) == 3 and int(frames[1][4]) == int(held[4]),
		"a new epoch re-sends the held direction under it")

	# Keys up: a release.
	Input.action_release("move_north")
	main.call("_update_keyboard_movement")
	_expect(frames.size() == 3 and int(frames[2][0]) == 254 and int(frames[2][4]) == 255,
		"releasing the key sends a release")
	_expect(not bool(main.get("_keyboard_moving")), "and the keyboard is no longer walking")

	# A trade window stops the walk with a release too.
	_press_north(main)
	var trade: Control = main.get("trade_panel") as Control
	trade.show()
	main.call("_update_keyboard_movement")
	_expect(int(frames[frames.size() - 1][4]) == 255, "an open trade releases the direction")
	trade.hide()
	Input.action_release("move_north")
	main.call("_update_keyboard_movement")

	# A server that switches intents off: back to MOVE_TO.
	frames.clear()
	state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_MOVE_INTENT, _intent_state(false, 3))
	main.call("_clear_keyboard_movement_tracking")
	_press_north(main)
	_expect(frames.size() == 1 and int(frames[0][0]) == EloriaProtocol.ClientMessage.MOVE_TO,
		"intents off: the keyboard sends MOVE_TO again")
	Input.action_release("move_north")
	main.call("_update_keyboard_movement")

	main.queue_free()
	await process_frame
	print("Keyboard intent tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
