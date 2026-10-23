extends SceneTree
## Exercise production click dispatch and inspect the frames sent to a local
## socket. Picking is deterministic so these checks need no rendered map.

const Keys := preload("res://src/ui/key_bindings.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# Restore the HUD and binding files touched by these checks.
	var originals := {}
	for path: String in ["user://eloria_hud.cfg", Keys.PATH]:
		originals[path] = FileAccess.get_file_as_bytes(path) if FileAccess.file_exists(path) else null
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.set_script(load("res://tests/fixtures/range_lock_main.gd"))
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	main.chat_input.release_focus()
	var state := root.get_node("AppState")
	state.local_actor_id = 91
	state.actors = {
		91: {"actor_id": 91, "x": 10, "y": 20, "health": 50,
			"sitting": false, "appearance": {"weapon": 66}},
		77: {"actor_id": 77, "kind": 3, "health": 30, "alive": true},
	}
	var lock_box: CheckBox = main._banner_option_boxes.ranging_lock
	lock_box.set_pressed_no_signal(false)
	main._banner_option_boxes.sit_lock.set_pressed_no_signal(false)
	var hotkey := Keys.parse("ALT R")
	hotkey.pressed = true
	_expect(hotkey.is_action_pressed("toggle_range_lock", false, true), "Alt+R is the shipped default")
	_expect("toggle_range_lock" in main.settings_window.bindable_actions(), "range lock is rebindable")
	_expect(main._handle_bound_action(hotkey) and lock_box.button_pressed, "Alt+R enables the existing lock")
	_expect(main._indicator_labels.R.tooltip_text == "Ranging Lock On", "R indicator follows the shortcut")
	var saved := ConfigFile.new()
	saved.load("user://eloria_hud.cfg")
	_expect(saved.get_value("banner", "ranging_lock", false), "range lock is saved")
	lock_box.set_pressed_no_signal(false)
	main._load_hud_settings()
	_expect(lock_box.button_pressed, "saved range lock reloads")

	var mount_state := {"mode": "mounted"}
	_expect(preload("res://src/mounts/mount_hotkeys.gd").request_for_event(hotkey, mount_state).is_empty(),
		"Alt+R does not mount or dismount")
	for spec: String in ["R", "CTRL R", "ALT SHIFT R"]:
		var other := Keys.parse(spec)
		other.pressed = true
		_expect(not other.is_action_pressed("toggle_range_lock", false, true), "%s does not toggle range lock" % spec)
	main.chat_input.grab_focus()
	_expect(not main._handle_bound_action(hotkey) and lock_box.button_pressed, "typing owns the shortcut")
	main.chat_input.release_focus()
	main.settings_window.capturing = "toggle_range_lock"
	_expect(not main._handle_bound_action(hotkey), "binding capture owns the shortcut")
	main.settings_window.capturing = ""
	main._input(hotkey)
	_expect(not lock_box.button_pressed, "second Alt+R disables the lock")
	hotkey.echo = true
	main._input(hotkey)
	_expect(not lock_box.button_pressed, "key repeat does not toggle again")
	hotkey.echo = false
	InputMap.action_erase_events("toggle_range_lock")
	InputMap.action_add_event("toggle_range_lock", Keys.parse("ALT Y"))
	_expect(not main._handle_bound_action(hotkey), "old key stops toggling after rebinding")
	var rebound := Keys.parse("ALT Y")
	rebound.pressed = true
	_expect(main._handle_bound_action(rebound) and lock_box.button_pressed, "rebound shortcut toggles the lock")
	Keys.reset_to_defaults(["toggle_range_lock"])

	var network := root.get_node("Network")
	network.set_process(false)
	network._secure = false # This fixture talks only to its loopback TCP server.
	var server := TCPServer.new()
	_expect(server.listen(0, "127.0.0.1") == OK, "packet fixture listens")
	var peer := StreamPeerTCP.new()
	network._peer = peer
	var connect_error := peer.connect_to_host("127.0.0.1", server.get_local_port())
	_expect(connect_error == OK, "packet fixture starts connecting: %s" % error_string(connect_error))
	for attempt: int in range(100):
		peer.poll()
		if server.is_connection_available():
			break
		OS.delay_usec(2000)
		await process_frame
	var receiver := server.take_connection()
	_expect(receiver != null, "packet fixture connects (status %d)" % peer.get_status())
	if receiver != null:
		peer.poll()
		var click := InputEventMouseButton.new()
		click.button_index = MOUSE_BUTTON_LEFT
		click.pressed = true
		main._interaction_mode = "walk"
		main._handle_world_click(click, Vector2(320, 240))
		_expect(_take(receiver).is_empty(), "locked bow ground click sends no movement")
		click.shift_pressed = true
		main._handle_world_click(click, Vector2(320, 240))
		_expect(_take(receiver).is_empty(), "Shift cannot turn a locked click into a run")
		click.shift_pressed = false
		main._handle_map_gui_input(click, main.minimap, main.map_viewport, main.map_camera, "test")
		_expect(_take(receiver).is_empty(), "locked minimap click sends no movement")
		main.picked_actor = 77
		main._handle_world_click(click, Vector2(320, 240))
		_expect(_take(receiver) == EloriaProtocol.attack_actor(77), "range lock permits target attacks")
		main.picked_actor = -1
		lock_box.button_pressed = false
		for weapon: int in [0, 66, 69]:
			state.actors[91].appearance.weapon = weapon
			click.alt_pressed = true
			main._handle_world_click(click, Vector2(320, 240))
			_expect(_take(receiver).is_empty(), "Alt ground miss stays still with weapon %d" % weapon)
			main.picked_actor = 77
			main._handle_world_click(click, Vector2(320, 240))
			_expect(_take(receiver) == EloriaProtocol.attack_actor(77), "Alt target click attacks with weapon %d" % weapon)
			main.picked_actor = -1
		click.alt_pressed = false
		main._handle_world_click(click, Vector2(320, 240))
		_expect(not _take(receiver).is_empty(), "releasing Alt restores ground movement")
		lock_box.button_pressed = true
		state.actors[91].appearance.weapon = 0
		main._handle_world_click(click, Vector2(320, 240))
		_expect(not _take(receiver).is_empty(), "range lock permits movement without a ranged weapon")
		state.actors[91].appearance.weapon = 66
		main.picked_actor = 77
		state.actors[91].sitting = true
		main._banner_option_boxes.sit_lock.set_pressed_no_signal(true)
		main._handle_world_click(click, Vector2(320, 240))
		_expect(_take(receiver).is_empty(), "sit lock still blocks an attack")
		click.ctrl_pressed = true
		main._handle_world_click(click, Vector2(320, 240))
		_expect(_take(receiver) == EloriaProtocol.attack_actor(77), "Ctrl overrides sit lock for an attack")
		state.actors[91].health = 0
		main._handle_world_click(click, Vector2(320, 240))
		_expect(_take(receiver).is_empty(), "dead actors cannot attack through range lock")
		receiver.disconnect_from_host()
	peer.disconnect_from_host()
	server.stop()
	_expect(MouseCursors.choose({"over_world": true, "alt": true}) == MouseCursors.ATTACK,
		"Alt shows the sword on empty ground")
	# Let deferred layout callbacks finish before destroying their controls.
	await process_frame
	await process_frame
	main.free()
	for path: String in originals:
		if originals[path] == null:
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
		else:
			var file := FileAccess.open(path, FileAccess.WRITE)
			file.store_buffer(originals[path])
	print("RANGE_LOCK_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)

func _take(receiver: StreamPeerTCP) -> PackedByteArray:
	for attempt: int in range(25):
		receiver.poll()
		if receiver.get_available_bytes() > 0:
			return receiver.get_data(receiver.get_available_bytes())[1] as PackedByteArray
		OS.delay_usec(2000)
	return PackedByteArray()

func _expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("FAIL: " + label)
