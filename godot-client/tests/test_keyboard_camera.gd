extends SceneTree
## Exercises real key events, camera timing, settings persistence and rebinding.

const Keys := preload("res://src/ui/key_bindings.gd")
const SETTINGS_PATH := "user://eloria_hud.cfg"
const ACTIONS := ["camera_rotate_left", "camera_rotate_right", "camera_tilt_up", "camera_tilt_down"]
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	Input.use_accumulated_input = false
	var backups := {}
	for path: String in [SETTINGS_PATH, Keys.PATH]:
		backups[path] = FileAccess.get_file_as_bytes(path) if FileAccess.file_exists(path) else null
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	main.set_process(false) # Advance camera time explicitly, independent of test frame rate.
	await process_frame
	main.game_view.show()
	main.login_panel.hide()
	var window: Control = main.settings_window
	var rig: IsometricCameraController = main.camera_rig
	Keys.reset_to_defaults(ACTIONS)
	_expect(main.call("_keyboard_camera_allowed"), "camera accepts keys in the world")
	var defaults := [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN]
	for index: int in ACTIONS.size():
		var events := InputMap.action_get_events(ACTIONS[index])
		_expect(events.size() == 1 and (events[0] as InputEventKey).physical_keycode == defaults[index],
			"arrow default for " + ACTIONS[index])
		_expect(ACTIONS[index] in window.bindable_actions(), "Controls offers " + ACTIONS[index])

	rig.keyboard_speed = 90.0
	rig.yaw_degrees = 0.0
	rig.pitch_degrees = -45.0
	var focus := rig.focus
	var distance := rig.distance
	_send_key(KEY_LEFT, true)
	await process_frame
	_expect(root.gui_get_focus_owner() == null, "world arrow press does not start GUI navigation")
	main.call("_update_keyboard_camera", 0.25)
	_expect(is_equal_approx(rig.yaw_degrees, 22.5), "held Left rotates at degrees per second")
	_send_key(KEY_RIGHT, true)
	main.call("_update_keyboard_camera", 0.25)
	_expect(is_equal_approx(rig.yaw_degrees, 22.5), "opposite keys cancel")
	_send_key(KEY_LEFT, false)
	main.call("_update_keyboard_camera", 0.25)
	_expect(is_equal_approx(rig.yaw_degrees, 0.0), "Right rotates in the other direction")
	_send_key(KEY_RIGHT, false)
	main.call("_update_keyboard_camera", 1.0)
	_expect(is_equal_approx(rig.yaw_degrees, 0.0), "release stops camera motion")
	_send_key(KEY_LEFT, true)
	main.notification(MainLoop.NOTIFICATION_APPLICATION_FOCUS_OUT)
	main.call("_update_keyboard_camera", 1.0)
	_expect(is_equal_approx(rig.yaw_degrees, 0.0), "losing window focus releases held camera keys")
	_send_key(KEY_LEFT, false)
	_send_key(KEY_UP, true)
	main.call("_update_keyboard_camera", 0.1)
	_expect(is_equal_approx(rig.pitch_degrees, -54.0), "Up raises the viewing angle")
	main.call("_update_keyboard_camera", 5.0)
	_expect(is_equal_approx(rig.pitch_degrees, -80.0), "Up stops at the upper tilt limit")
	_send_key(KEY_UP, false)
	_send_key(KEY_DOWN, true)
	main.call("_update_keyboard_camera", 5.0)
	_expect(is_equal_approx(rig.pitch_degrees, -15.0), "Down stops at the lower tilt limit")
	_send_key(KEY_DOWN, false)
	_expect(rig.focus.is_equal_approx(focus) and is_equal_approx(rig.distance, distance),
		"keyboard orbit preserves player focus and zoom")
	rig.yaw_degrees = 0.0
	rig.handle_keyboard(Vector2.RIGHT, 1.0)
	var one_frame := rig.yaw_degrees
	rig.yaw_degrees = 0.0
	for frame: int in 120:
		rig.handle_keyboard(Vector2.RIGHT, 1.0 / 120.0)
	_expect(is_equal_approx(rig.yaw_degrees, one_frame), "rotation is independent of frame rate")

	# A held key must become inert as soon as a text field or modal owns input.
	_send_key(KEY_LEFT, true)
	var yaw := rig.yaw_degrees
	main.chat_input.grab_focus()
	main.call("_update_keyboard_camera", 1.0)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "typing pauses a held camera key")
	main.chat_input.release_focus()
	for panel: Control in [main.full_map, main.console_panel, main.trade_panel,
			main.dialogue_panel, main.popup_panel, main.purchase_confirm]:
		panel.show()
		main.call("_update_keyboard_camera", 1.0)
		_expect(is_equal_approx(rig.yaw_degrees, yaw), "menu pauses camera: " + panel.name)
		panel.hide()
	window.open_tab("Controls")
	window.begin_capture("camera_rotate_left")
	main.call("_update_keyboard_camera", 1.0)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "key capture pauses held camera motion")
	_send_key(KEY_LEFT, false)
	var rebound := InputEventKey.new()
	rebound.physical_keycode = KEY_F8
	rebound.ctrl_pressed = true
	rebound.pressed = true
	_expect(window.apply_capture(rebound), "camera key can be rebound with modifiers")
	_expect(FileAccess.get_file_as_string(Keys.PATH).contains("#K_CAMERA_ROTATE_LEFT = CTRL F8"),
		"camera rebind is saved to keys.ini")
	Keys.reset_to_defaults(ACTIONS)
	window.load_keys_file()
	_expect(Keys.describe(InputMap.action_get_events("camera_rotate_left")[0]) == "CTRL F8",
		"camera rebind survives loading keys.ini")
	window.close()
	_send_key(KEY_LEFT, true)
	main.call("_update_keyboard_camera", 0.25)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "old key stops driving a rebound action")
	_send_key(KEY_LEFT, false)
	_send_key(KEY_F8, true)
	main.call("_update_keyboard_camera", 0.25)
	_expect(is_equal_approx(rig.yaw_degrees, yaw), "modified rebind ignores the bare key")
	_send_key(KEY_F8, false)
	_send_key(KEY_F8, true, true)
	main.call("_update_keyboard_camera", 0.25)
	_expect(is_equal_approx(rig.yaw_degrees, yaw + 22.5), "modified camera rebind drives the camera")
	_send_key(KEY_F8, false, true)
	window.reset_keys()
	_expect(Keys.describe(InputMap.action_get_events("camera_rotate_left")[0]) == "LEFT",
		"Reset all keys restores camera defaults")

	window.open_tab("Camera")
	var speed := window.panel.find_child("keyboard_speed", true, false) as SpinBox
	_expect(speed != null, "Camera tab offers keyboard camera speed")
	if speed != null:
		speed.value = 120.0
		var config := ConfigFile.new()
		config.load(SETTINGS_PATH)
		_expect(is_equal_approx(rig.keyboard_speed, 120.0)
			and is_equal_approx(float(config.get_value("camera", "keyboard_speed")), 120.0),
			"changing the speed control applies and saves immediately")
		rig.keyboard_speed = 30.0
		main.call("_load_hud_settings")
		_expect(is_equal_approx(rig.keyboard_speed, 120.0) and is_equal_approx(speed.value, 120.0),
			"saved speed reloads into the camera and control")
		window.close()
		rig.yaw_degrees = 0.0
		_send_key(KEY_LEFT, true)
		main.call("_update_keyboard_camera", 0.25)
		_send_key(KEY_LEFT, false)
		_expect(is_equal_approx(rig.yaw_degrees, 30.0), "new speed changes actual held-key motion")
		config.erase_section_key("camera", "keyboard_speed")
		config.save(SETTINGS_PATH)
		main.call("_load_hud_settings")
		_expect(is_equal_approx(rig.keyboard_speed, 90.0), "older settings receive the default speed")
		for invalid: float in [-10.0, 9999.0, NAN, INF]:
			config.set_value("camera", "keyboard_speed", invalid)
			config.save(SETTINGS_PATH)
			main.call("_load_hud_settings")
			_expect(is_finite(rig.keyboard_speed) and rig.keyboard_speed >= 15.0 and rig.keyboard_speed <= 180.0,
				"invalid saved speed stays within safe finite limits")

	main.queue_free()
	await process_frame
	for path: String in backups:
		if backups[path] == null:
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
		else:
			var file := FileAccess.open(path, FileAccess.WRITE)
			file.store_buffer(backups[path])
			file.close()
	print("keyboard camera tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _send_key(code: Key, pressed: bool, ctrl := false) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.keycode = code
	event.pressed = pressed
	event.ctrl_pressed = ctrl
	Input.parse_input_event(event)
	Input.flush_buffered_events()

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
