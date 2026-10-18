extends SceneTree
## Starts the ordinary game scene against the disposable local test server.
var game: Node
var smoke := false
var failures := 0

func mount_key(code: Key) -> bool:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.pressed = true
	return bool(game.call("_handle_bound_action", event))

func _init() -> void:
	call_deferred("run")

func wait_for(predicate: Callable, seconds := 30.0) -> bool:
	var until := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < until:
		if predicate.call():
			return true
		await process_frame
	return false

func run() -> void:
	var config: Dictionary = {}
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--mount-session="):
			config = JSON.parse_string(FileAccess.get_file_as_string(arg.trim_prefix("--mount-session=")))
		smoke = smoke or arg == "--mount-smoke"
	if config.get("host") != "127.0.0.1":
		push_error("The Moor Pony launcher requires a local test session")
		quit(1)
		return
	game = load("res://src/app/main.tscn").instantiate()
	root.add_child(game)
	await process_frame
	game.set("_dev_plain_tcp", true)
	game.get("host_edit").text = "127.0.0.1"
	game.get("port_edit").value = int(config.port)
	game.call("_on_connect_pressed")
	if not await wait_for(func() -> bool: return root.get_node("AppState").connection_state == "connected"):
		push_error("Local mount server did not connect")
		quit(1)
		return
	game.get("user_edit").text = str(config.username)
	game.get("password_edit").text = str(config.password)
	game.call("_on_login_pressed")
	var state := root.get_node("AppState")
	if not await wait_for(func() -> bool: return state.authenticated and state.actor_mounts.has(state.local_actor_id) and game.get("actor_nodes").has(state.local_actor_id), 90):
		push_error("Real game did not receive its player and mount state")
		quit(1)
		return
	var network := root.get_node("Network")
	await create_timer(3.0).timeout
	# Start close enough to judge the seat; all ordinary camera controls work.
	var camera := game.get("camera_rig") as IsometricCameraController
	camera.distance = 7.0
	camera.pitch_degrees = -35.0
	camera.yaw_degrees = -35.0
	camera.set_focus(camera.focus)
	print("MOOR_PONY_GAME_READY")
	if not smoke:
		return
	# Give terrain streaming and initial UI windows time to settle.
	await create_timer(3.0).timeout
	var typing := game.get("chat_input") as LineEdit
	typing.show()
	typing.grab_focus()
	if mount_key(KEY_R):
		push_error("Mount shortcut claimed a typed character")
		failures += 1
	typing.release_focus()
	game.call("_hide_chat_input")
	if not mount_key(KEY_R):
		push_error("Mount shortcut did not handle R")
		failures += 1
	if not await wait_for(func() -> bool: return state.actor_mounts.get(state.local_actor_id, {}).get("mode") == "mounted", 8):
		push_error("Game summon failed: " + str(state.actor_mounts))
		quit(1)
		return
	await process_frame
	var actor: ReplicatedActor3D = game.get("actor_nodes")[state.local_actor_id]
	if not is_instance_valid(actor._mount_visual):
		push_error("Server mount state did not create the pony on the real player")
		quit(1)
		return
	if not mount_key(KEY_SPACE):
		push_error("Mounted Space shortcut was not handled")
		failures += 1
	await create_timer(.3).timeout
	if state.actor_mounts[state.local_actor_id].gait != "burst":
		push_error("Space did not start galloping")
		failures += 1
	mount_key(KEY_SPACE)
	await create_timer(2.0).timeout
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://../.local/qa/moor-pony-game/mounted-game.png")
	for gait: String in ["walk", "cruise", "burst"]:
		network.send_chat("#walk" if gait == "walk" else "#run")
		network.send_chat("#gallop on" if gait == "burst" else "#gallop off")
		await create_timer(.2).timeout
		var dto: Dictionary = state.actors[state.local_actor_id]
		var destination := Vector2i(int(dto.x) + (-2 if gait == "cruise" else 2), int(dto.y))
		network.move_to(destination, gait != "walk")
		if not await wait_for(func() -> bool: return int(state.actors[state.local_actor_id].x) == destination.x, 5):
			push_error("Mounted " + gait + " did not reach its server destination")
			failures += 1
		await create_timer(.06).timeout
		if not is_instance_valid(actor._mount_visual):
			push_error("Mounted route unexpectedly dismounted")
			failures += 1
		elif actor._mount_visual.get("action") != {"walk": "walk", "cruise": "trot", "burst": "gallop"}[gait]:
			push_error("Wrong live riding gait: " + str(actor._mount_visual.get("action")))
			failures += 1
		if DisplayServer.get_name() != "headless":
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png("res://../.local/qa/moor-pony-game/" + gait + "-game.png")
		await create_timer(.8).timeout
	network.send_chat("#gallop on")
	await create_timer(.5).timeout
	if state.actor_mounts[state.local_actor_id].gait != "burst":
		failures += 1
	mount_key(KEY_R)
	if not await wait_for(func() -> bool: return state.actor_mounts.get(state.local_actor_id, {}).get("mode") == "on_foot", 3):
		failures += 1
	await process_frame
	if is_instance_valid(actor._mount_visual):
		failures += 1
	print("MOOR_PONY_REAL_GAME_SMOKE failures=", failures)
	network.disconnect_from_server()
	game.queue_free()
	await process_frame
	quit(1 if failures else 0)
