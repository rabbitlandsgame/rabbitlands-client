extends SceneTree
## Production input, live packet updates and a fresh surface restore.
var failures := 0
var main: Control
var windows: Control
var app: Node
var settings_path := ProjectSettings.globalize_path("res://test-artifacts/party-resize-ui/test-settings.cfg")

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(settings_path.get_base_dir())
	var config := ConfigFile.new()
	config.set_value("unrelated", "keep", 42)
	config.save(settings_path)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	main.get_node("GameView/ChatWindow").set("preferences_path", settings_path)
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.get_node("GameView").show()
	root.content_scale_factor = 1.0
	await _settle()
	# Exercise the native roster independently of the default preset's hidden
	# party and detailed player card. Modern HUD integration has its own test.
	main.hud_workspace.model.working = main.hud_workspace.Presets._preset_recipe("current")
	main.hud_workspace.apply_layout()
	await _settle()
	windows = main.get("extension_windows")
	windows.set("preferences_path", settings_path)
	windows.set("_party_numbers", false)
	windows.set("_party_custom_size", false)
	windows.set("_party_collapsed", false)
	windows.set("_party_expanded_size", Vector2(244, 0))
	app = root.get_node("AppState")
	app.set("authenticated", true)
	_send_party(120)
	await _settle()
	var panel: Control = windows.party_panel
	var row: Control = windows.party_rows.get_child(0)
	_expect(row.get_node("Vitals/Identity").visible and row.get_node("Vitals/Health").visible,
		"the default roster keeps names and bars")
	var before := panel.size
	await _drag(windows.party_resize_grip, Vector2(-80, 70))
	_expect(panel.size.is_equal_approx(before + Vector2(-80, 70)), "the actual grip resizes both dimensions")
	_expect(not row.get_node("Vitals/Identity").visible and row.get_node("Portrait").visible
		and row.tooltip_text.contains("Kellan"), "narrow rows retain initials and hover identity while hiding names")
	var resized := panel.size
	_send_party(119)
	await _settle()
	_expect(panel.size.is_equal_approx(resized), "health packets preserve the player's custom size")
	windows.party_options.get_popup().id_pressed.emit(0)
	await _settle()
	row = windows.party_rows.get_child(0)
	var health: Label = row.get_node("Vitals/HealthNumber")
	var ether: Label = row.get_node("Vitals/EtherNumber")
	_expect(health.visible and health.text == "119/180" and ether.text == "40/60"
		and not row.get_node("Vitals/Health").visible and not row.get_node("Vitals/Ether").visible,
		"the menu replaces both bars with current/max values from the server")
	_expect(health.get_theme_color("font_color") == Color("479947")
		and ether.get_theme_color("font_color") == Color("4287ac"), "numbers keep health green and ether blue")
	var offline: Control = windows.party_rows.get_child(1)
	_expect(offline.get_node("Vitals/HealthNumber").text == "—/—" and offline.modulate.a < 1,
		"offline members show unknown, dimmed readouts")
	_send_party(20)
	await _settle()
	row = windows.party_rows.get_child(0)
	_expect(row.get_node("Vitals/HealthNumber").text == "20/180"
		and row.get_node("Vitals/HealthNumber").get_theme_color("font_color") == Color("b74935"),
		"live low-health updates turn the health number red")
	windows.resize_party_window(Vector2(280, 240))
	await _settle()
	_expect(row.get_node("Vitals/Identity").visible, "widening the roster restores names")
	var expanded := panel.size
	windows.party_collapse.pressed.emit()
	await _settle()
	_expect(panel.size.y < expanded.y and not windows.party_resize_grip.is_visible_in_tree(), "collapse stays compact")
	windows.party_collapse.pressed.emit()
	await _settle()
	_expect(panel.size.is_equal_approx(expanded), "expanding restores the chosen height and width")
	# Check the widest values allowed by the protocol at the narrowest width.
	var large := _hex("0102037800b40028003c000003e0014b656c6c616e00666f75725f676174657300045a0096000a0037009a00b6004d6172656e006d6972726f72686f6c6400000000")
	for offset in [3, 5, 7, 9]:
		large.encode_u16(offset, 65535)
	app.call("_on_packet", 240, large)
	windows.resize_party_window(Vector2(144, 150))
	await _settle()
	row = windows.party_rows.get_child(0)
	health = row.get_node("Vitals/HealthNumber")
	_expect(panel.size.x <= 145 and panel.get_global_rect().encloses(health.get_global_rect()),
		"maximum numeric values fit at the minimum width")
	windows.party_panel.position = Vector2(32, 80)
	windows.party_collapse.pressed.emit()
	var restored: Control = (load("res://src/ui/extension_windows.gd") as GDScript).new()
	restored.set("preferences_path", settings_path)
	root.add_child(restored)
	await _settle()
	_expect(not restored.party_scroll.visible and restored.party_panel.position.is_equal_approx(Vector2(32, 80)),
		"a fresh party surface restores position and collapse")
	restored.party_collapse.pressed.emit()
	await _settle()
	_expect(restored.party_panel.size.is_equal_approx(Vector2(144, 150))
		and restored.party_rows.get_child(0).get_node("Vitals/HealthNumber").visible,
		"a fresh party surface restores expanded dimensions and numeric mode")
	restored.free()
	windows.party_collapse.pressed.emit()
	windows.party_options.get_popup().id_pressed.emit(0)
	await _settle()
	_expect(windows.party_rows.get_child(0).get_node("Vitals/Health").visible, "the same menu returns to bars")
	windows.party_options.get_popup().id_pressed.emit(1)
	await _settle()
	_expect(panel.size.x == 244 and windows.party_rows.get_child(0).get_node("Vitals/Identity").visible,
		"Reset size restores the default roster width and names")
	# A full party remains reachable when the player reduces the height.
	_send_full_party()
	windows.resize_party_window(Vector2(164, 180))
	await _settle()
	var wheel := InputEventMouseButton.new()
	wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
	wheel.pressed = true
	wheel.position = windows.party_scroll.get_global_rect().get_center()
	wheel.global_position = wheel.position
	root.push_input(wheel, true)
	await _settle()
	_expect(windows.party_scroll.scroll_vertical > 0, "the mouse wheel scrolls a shortened roster")
	windows.party_scroll.ensure_control_visible(windows.party_rows.get_child(7))
	await _settle()
	_expect(windows.party_scroll.get_global_rect().encloses(windows.party_rows.get_child(7).get_global_rect()),
		"the last member stays accessible in a short roster")
	windows.party_collapse.pressed.emit()
	windows.party_options.get_popup().id_pressed.emit(1)
	var reset_rect := WindowPreferences.stored_rect("party_hud", Rect2(), settings_path)
	_expect(reset_rect.position == panel.position and reset_rect.size.y > 0,
		"resetting size while collapsed still saves a valid expanded layout and position")
	(panel.get_node("Body/Header/Close") as Button).pressed.emit()
	_send_party(18)
	await _settle()
	_expect(not panel.visible, "format and resizing changes preserve the close behavior")
	config.load(settings_path)
	_expect(config.get_value("unrelated", "keep") == 42, "party preferences preserve unrelated settings")
	main.free()
	await process_frame
	print("party resize tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _send_party(health: int) -> void:
	app.call("_on_packet", 240, _hex("010203%02x00b40028003c000003e0014b656c6c616e00666f75725f67617465730004" % health
		+ "5a0096000a0037009a00b6004d6172656e006d6972726f72686f6c6400000000"))

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _send_full_party() -> void:
	var packet := PackedByteArray([1, 8])
	for index in range(8):
		var fields := PackedByteArray()
		fields.resize(13)
		fields[0] = 7 if index == 0 else 1
		var values := [120, 180, 40, 60, 139 + index, 219]
		for field in range(values.size()):
			fields.encode_u16(1 + field * 2, int(values[field]))
		packet.append_array(fields)
		packet.append_array(("Companion%d" % index).to_utf8_buffer())
		packet.append(0)
		packet.append_array("landfall".to_utf8_buffer())
		packet.append(0)
	packet.append_array(PackedByteArray([0, 0, 0]))
	app.call("_on_packet", 240, packet)

func _settle() -> void:
	for frame in range(5):
		await process_frame

func _drag(handle: Control, delta: Vector2) -> void:
	var start := handle.get_global_rect().get_center()
	var hover := InputEventMouseMotion.new()
	hover.position = start
	hover.global_position = start
	root.push_input(hover, true)
	_mouse(start, true)
	var motion := InputEventMouseMotion.new()
	motion.position = start + delta
	motion.global_position = motion.position
	motion.relative = delta
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion, true)
	_mouse(motion.position, false)
	await _settle()

func _mouse(where: Vector2, pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.position = where
	event.global_position = where
	event.button_index = MOUSE_BUTTON_LEFT
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
	event.pressed = pressed
	root.push_input(event, true)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
