extends SceneTree
## Production-scene checks for separated/combined feeds, destinations,
## full-log filters, independent dragging, settings and restart persistence.
var failures := 0
var main: Control
var app: Node
var settings_path := "res://test-artifacts/split-chat-ui/settings.cfg"

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(settings_path.get_base_dir()))
	var config := ConfigFile.new()
	config.set_value("unrelated", "keep", 42)
	config.save(settings_path)
	await _mount()
	var chat: PanelContainer = main.chat_hud
	var system: PanelContainer = main.system_chat_hud
	_expect(chat.visible and system.visible, "both feeds start visible and separate")
	_expect(chat.position.y < 100 and system.position.y > 400, "conversation starts upper left and system lower left")
	_expect(chat.get_theme_stylebox("panel") is StyleBoxEmpty
		and system.get_theme_stylebox("panel") is StyleBoxEmpty, "both surfaces have no solid frame")
	_expect(chat.get_node("Frame/SoftFade").material is ShaderMaterial, "the backdrop is a feathered shader")
	chat.set_option("idle_fade", 1)
	chat.set("_last_message_msec", Time.get_ticks_msec() - 5000)
	chat.call("_process", 0.2)
	_expect(is_equal_approx(chat.output.modulate.a, 0.35), "optional idle dimming reduces text without hiding the window")
	chat.input.grab_focus()
	chat.call("_process", 0.2)
	_expect(is_equal_approx(chat.output.modulate.a, 1.0), "typing restores full text opacity")
	chat.input.release_focus()
	chat.set_option("idle_fade", 0)
	_expect(not system.input.visible and system.destination == null, "system has no public-send composer")
	app.call("_on_packet", 71, PackedByteArray([2, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 4, 0, 0, 0]))
	(app.get("chat_lines") as Array).clear()
	main.call("_sync_chat")
	_chat(0, "Entered Four Gates.")
	_chat(0, "Torch crafted x3.")
	_chat(0, "Tavi: Meet at the bridge.")
	_chat(0, "[Party] Rowan: Ready when you are.")
	_chat(2, "Nash: guild message")
	_chat(7, "[4] Ari: Buying Sunleaf.")
	_chat(1, "[PM from Mira: Save a place for me.]")
	await _settle()
	_expect(chat.output.get_parsed_text().contains("Tavi:")
		and chat.output.get_parsed_text().contains("Rowan:")
		and not chat.output.get_parsed_text().contains("Torch crafted"), "conversation feed excludes routine game messages")
	_expect(system.output.get_parsed_text().contains("Torch crafted")
		and not system.output.get_parsed_text().contains("Tavi:"), "system feed excludes player conversations")
	_expect(chat.channel_buttons.has(4) and main.call("_chat_channel_number", (app.get("chat_lines") as Array)[5]) == 4,
		"the fourth joined channel has its own identity and tab")
	await _capture("01-separate.png")
	main.call("_on_client_setting_changed", "Chat", "chat_combined", true)
	_expect(not system.visible and chat.output.get_parsed_text().contains("Torch crafted")
		and chat.output.get_parsed_text().contains("Tavi:"), "combined mode shows both feeds once in the conversation surface")
	_chat(3, "A new system notice")
	_expect(not system.visible and chat.output.get_parsed_text().contains("new system notice"), "new system messages do not reopen the merged-away window")
	await _capture("02-combined.png")
	main.call("_on_client_setting_changed", "Chat", "chat_combined", false)
	_expect(system.visible and not chat.output.get_parsed_text().contains("new system notice"), "separating restores both filtered feeds")
	main.call("_on_chat_tab_pressed", "party")
	_expect(main.call("_chat_message_for_tab", "ready") == "#p ready", "the visible Party destination sends party chat")
	var target: String = chat.destination_key
	main.call("_toggle_console")
	for spec: Array in [["all", "Torch crafted", ""], ["system", "Torch crafted", "Tavi:"],
			["chat", "Tavi:", "Torch crafted"], ["local", "Tavi:", "Rowan:"],
			["party", "Rowan:", "Tavi:"], ["guild", "guild message", "Rowan:"],
			["private", "Save a place", "Buying Sunleaf"], ["channel:4", "Buying Sunleaf", "Save a place"],
			["pm:mira", "Save a place", "Rowan:"]]:
		main.chat_log_tabs.buttons[str(spec[0])].pressed.emit()
		var shown: String = main.console_output.get_parsed_text()
		_expect(shown.contains(str(spec[1])) and (str(spec[2]).is_empty() or not shown.contains(str(spec[2]))),
			"log filter: " + str(spec[0]))
		_expect(chat.destination_key == target, "log browsing never retargets the composer")
	main.chat_log_tabs.buttons["all"].pressed.emit()
	await _capture("03-log-all.png")
	main.call("_toggle_console")
	main.call("_on_chat_tab_pressed", "private")
	chat.input.text = "keep this draft private"
	main.call("_on_chat_submitted", chat.input.text)
	_expect(chat.input.text == "keep this draft private", "Private without a recipient preserves the draft and refuses public fallback")
	chat.set_destination("pm:mira")
	_chat(1, "[PM from Other: new arrival]")
	_expect(main.call("_chat_message_for_tab", "hello") == "/mira hello", "a new PM never changes a pinned recipient")
	chat.set_destination("channel:4")
	_expect(main.call("_chat_message_for_tab", "hello") == "@@4 hello", "numbered sending uses the actual channel ID")
	app.call("_on_packet", 71, PackedByteArray([0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0]))
	_expect(main.call("_chat_message_for_tab", "hello").is_empty(), "a departed channel cannot silently send to Local")
	_expect(main.chat_log_tabs.buttons.has("channel:4"), "a departed channel retains its session log section")
	main.call("_on_chat_tab_pressed", "all")
	chat.input.clear()
	chat.set_destination("local")
	var system_before := system.position
	await _drag(chat.get_node("Frame/Layout/Header/Title"), Vector2(70, 25))
	_expect(chat.position.is_equal_approx(Vector2(88, 73)) and system.position == system_before, "dragging conversations leaves system position alone")
	var chat_before := chat.position
	await _drag(system.get_node("Frame/Layout/Header/Title"), Vector2(80, -35))
	_expect(system.position.is_equal_approx(system_before + Vector2(80, -35)) and chat.position == chat_before,
		"dragging system leaves conversation position alone")
	var old_size := system.size
	await _drag(system.grip, Vector2(55, -15))
	_expect(system.size.is_equal_approx(old_size + Vector2(55, -15)), "the system window also resizes through its real grip")
	(main.settings_window.find_child("chat_font_size", true, false) as SpinBox).value = 19
	(main.settings_window.find_child("system_chat_font_size", true, false) as SpinBox).value = 13
	(main.settings_window.find_child("system_chat_background_opacity", true, false) as SpinBox).value = 0.45
	(main.settings_window.find_child("chat_line_spacing", true, false) as SpinBox).value = 4
	main.call("_on_client_setting_changed", "Chat", "chat_locked", true)
	_expect(chat.output.get_theme_font_size("normal_font_size") == 19
		and system.output.get_theme_font_size("normal_font_size") == 13, "text sizes are independent")
	_expect(is_equal_approx(system.get_node("Frame/SoftFade").material.get_shader_parameter("opacity"), 0.45),
		"system fade opacity applies immediately")
	var locked_where := chat.position
	await _drag(chat.get_node("Frame/Layout/Header/Title"), Vector2(50, 30))
	_expect(chat.position == locked_where and not chat.grip.visible, "locking prevents dragging and hides resizing")
	main.call("_on_client_setting_changed", "Chat", "chat_locked", false)
	system.dismiss()
	_chat(3, "system while closed")
	_expect(not system.visible, "messages respect a dismissed system window")
	main.call("_on_client_setting_changed", "Chat", "system_chat_visible", true)
	chat.dismiss()
	_chat(0, "Tavi: chat while closed")
	_expect(not chat.visible, "messages respect a dismissed conversation window")
	main.call("_show_chat_input")
	_expect(chat.visible and chat.input.has_focus(), "T reopens and focuses conversations")
	main.call("_hide_chat_input")
	chat.options_button.pressed.emit()
	_expect(main.settings_window.tabs.get_current_tab_control().name == "Chat", "the window shortcut opens its dedicated Chat settings")
	await _capture("04-chat-settings.png")
	main.settings_window.close()
	var chat_rect := Rect2(chat.position, chat.size)
	var system_rect := Rect2(system.position, system.size)
	chat.save_layout()
	system.save_layout()
	config.load(settings_path)
	_expect(int(config.get_value("unrelated", "keep", 0)) == 42, "saving the feeds preserves unrelated preferences")
	await _unmount()
	await _mount()
	chat = main.chat_hud
	system = main.system_chat_hud
	_expect(Rect2(chat.position, chat.size) == chat_rect and Rect2(system.position, system.size) == system_rect,
		"both window positions and sizes restore after a fresh scene")
	_expect(int(chat.options.font_size) == 19 and int(system.options.font_size) == 13
		and int(chat.options.line_spacing) == 4, "independent appearance options survive restart")
	root.size = Vector2i(1024, 600)
	await _settle()
	for surface: PanelContainer in [chat, system]:
		_expect(surface.get_global_rect().end.x <= root.get_visible_rect().size.x - 96
			and surface.get_global_rect().end.y <= main.get_node("GameView/Quickbar").global_position.y,
			"a smaller viewport keeps both windows recoverable and above the action bar")
	await _capture("05-small-window.png")
	await _unmount()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("split chat HUD tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _mount() -> void:
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	main.get_node("GameView/ChatWindow").preferences_path = settings_path
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	app = root.get_node("AppState")
	app.set("authenticated", true)
	root.content_scale_factor = 1.0
	await _settle()

func _unmount() -> void:
	await _settle()
	main.queue_free()
	await _settle()

func _chat(channel: int, text: String) -> void:
	var payload := PackedByteArray([channel])
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _settle() -> void:
	for frame in range(8):
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

func _capture(filename: String) -> void:
	var folder := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if folder.is_empty() or DisplayServer.get_name() == "headless":
		return
	DirAccess.make_dir_recursive_absolute(folder)
	await _settle()
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join(filename))
	print("capture: ", filename)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
