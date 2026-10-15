extends SceneTree
## Real production controls and input routing. The browser is replaced only
## at its final OS boundary; rendered runs exercise the native clipboard.
var failures := 0
var main: Control
var app: Node
var opened: Array[String] = []
var settings_path := "res://test-artifacts/chat-clipboard-urls/settings.cfg"

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(settings_path.get_base_dir()))
	var config := ConfigFile.new()
	config.save(settings_path)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	main.get_node("GameView/ChatWindow").preferences_path = settings_path
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	app = root.get_node("AppState")
	app.authenticated = true
	root.content_scale_factor = 1.0
	await _settle()
	var reference: Control = main.reference_window
	reference.url_opener = func(url: String) -> Error:
		opened.append(url)
		return OK
	_expect(reference.call("open_last_url") == ERR_DOES_NOT_EXIST and opened.is_empty(),
		"an empty session never launches the browser")
	_expect(InputMap.action_get_events("open_last_url")[0].physical_keycode == KEY_F2,
		"F2 is the default latest URL binding")
	_expect((main.settings_window.BINDABLE.Actions as Array).has("open_last_url"),
		"the latest URL shortcut can be rebound")
	_expect(ConsoleCommands.urls_in("[PM from Ada: (HTTPS://rabbitlandsgame.com/wiki/A_(B)).]\nwww.rabbitlandsgame.com/news, next")
		== ["HTTPS://rabbitlandsgame.com/wiki/A_(B)", "www.rabbitlandsgame.com/news"],
		"URL detection handles PM brackets, punctuation, newlines and balanced paths")
	_expect(ConsoleCommands.urls_in("file:///tmp/foo javascript:alert(1) ftp://example.com https:// www. https:///bad").is_empty(),
		"invalid addresses and non-web schemes are not collected")
	_expect(ConsoleCommands.web_url("javascript:alert(1)").is_empty()
		and ConsoleCommands.web_url("file:///tmp/foo").is_empty()
		and ConsoleCommands.web_url("www.rabbitlandsgame.com") == "https://www.rabbitlandsgame.com",
		"the system browser receives only web URLs, and www uses HTTPS")

	_chat(0, "Ada: First https://rabbitlandsgame.com/first.")
	_chat(3, "News https://rabbitlandsgame.com/notice")
	_chat(1, "[PM from Bea: www.rabbitlandsgame.com/private]")
	_expect(opened.is_empty() and (reference.known_links() as Array).size() == 3,
		"chat, system and PM URLs collect while the window is closed without opening anything")
	main.chat_input.grab_focus()
	main.chat_input.text = "draft stays here"
	_key(KEY_F2)
	_expect(opened == ["https://www.rabbitlandsgame.com/private"]
		and main.chat_input.text == "draft stays here", "F2 opens the last URL while preserving a focused draft")
	_key(KEY_F2, false, true)
	_expect(opened.size() == 1, "holding F2 does not repeatedly launch the browser")
	_chat(0, "Ada: Again https://rabbitlandsgame.com/first")
	_key(KEY_F2)
	_expect(opened.back() == "https://rabbitlandsgame.com/first"
		and (reference.known_links() as Array).size() == 3, "a repeated URL becomes latest without duplicate rows")
	main.console_commands.ignored.append("ignoredplayer")
	_chat(0, "IgnoredPlayer: https://rabbitlandsgame.com/ignored")
	_chat(1, "[PM from IgnoredPlayer: https://rabbitlandsgame.com/ignored-pm]")
	main.console_commands.filters.append("filteredword")
	_chat(0, "Ada: filteredword https://rabbitlandsgame.com/filtered")
	_expect((reference.known_links() as Array).size() == 3, "unseen ignored and filtered links never become the F2 target")
	main.console_commands.ignored.clear()
	main.console_commands.filters.clear()

	# Rotate the capped chat buffer without doing a thousand UI rebuilds.
	var history: Array = app.chat_lines
	for index: int in range(app.CHAT_LINE_LIMIT + 5):
		history.append({"channel": 0, "text": "Ada: ordinary %d" % index})
		if history.size() > app.CHAT_LINE_LIMIT:
			history.pop_front()
	app.state_changed.emit(&"chat")
	_expect((reference.known_links() as Array).size() == 3
		and not str(history).contains("https://"), "session URLs survive removal of their messages from the bounded log")
	main.chat_input.release_focus()
	main.chat_hud.get_node("Frame/Layout/Header/URLs").pressed.emit()
	await _settle()
	_expect(reference.is_open() and reference.tabs.current_tab == reference.URLS_TAB,
		"the HUD URLs button opens the session URL view")
	_expect(reference.links_list.get_item_text(0) == "https://rabbitlandsgame.com/first",
		"the URL list displays the latest link first")
	reference.links_list.select(1)
	reference.links_list.item_selected.emit(1)
	reference.open_link_button.pressed.emit()
	_expect(opened.back() == "https://www.rabbitlandsgame.com/private", "Open uses the selected historical URL")
	reference.links_list.select(2)
	reference.links_list.item_activated.emit(2)
	_expect(opened.back() == "https://rabbitlandsgame.com/notice", "double-click opens a historical URL")
	await _capture("urls.png")
	if DisplayServer.get_name() != "headless":
		var previous := DisplayServer.clipboard_get()
		reference.copy_link_button.pressed.emit()
		_expect(DisplayServer.clipboard_get() == "https://rabbitlandsgame.com/notice", "Copy URL writes the selected address")
		DisplayServer.clipboard_set(previous)
	reference.close()
	main.call("_toggle_console")
	main.console_panel.get_node("Content/Header/URLs").pressed.emit()
	await _settle()
	_expect(reference.panel.z_index > main.console_panel.z_index and reference.is_open(),
		"URLs remain accessible above the full log")
	reference.close()
	main.call("_toggle_console")

	_chat(0, "Ada: Select this line, then copy it.")
	_chat(3, "System line to copy.")
	await _settle()
	for output: RichTextLabel in [main.chat_output, main.system_chat_hud.output, main.console_output]:
		if output == main.console_output:
			main.call("_toggle_console")
		await _settle()
		# A virtual pointer keeps the drag check independent of desktop mouse
		# movement. Rendered runs check the native clipboard and menus below.
		if DisplayServer.get_name() == "headless":
			main.chat_input.grab_focus()
			await _select_with_mouse(output)
			_expect(output.has_focus() and not output.get_selected_text().is_empty(),
				"dragging selects text and takes keyboard focus: " + str(output.name))
		output.grab_focus()
		_key(KEY_A, true)
		_expect(output.get_selected_text() == output.get_parsed_text()
			and not main.stats_panel.visible, "Ctrl+A selects the chat text without opening statistics")
		_expect(output.selection_enabled and output.focus_mode == Control.FOCUS_ALL
			and output.context_menu_enabled and output.shortcut_keys_enabled
			and not output.get_selected_text().is_empty(), "selectable output has keyboard and right-click copying: " + str(output.name))
		if DisplayServer.get_name() != "headless":
			await _check_native_copy(output)
	if main.console_panel.visible:
		main.call("_toggle_console")
	main.chat_input.grab_focus()
	_expect(main.chat_input.selecting_enabled and main.chat_input.shortcut_keys_enabled
		and main.chat_input.context_menu_enabled, "chat input retains native selection, copy and paste")
	if DisplayServer.get_name() != "headless":
		var previous := DisplayServer.clipboard_get()
		DisplayServer.clipboard_set("pasted reply with a URL https://rabbitlandsgame.com")
		main.chat_input.text = "replace this"
		main.chat_input.select_all()
		_key(KEY_V, true)
		_expect(main.chat_input.text == DisplayServer.clipboard_get(), "Ctrl+V pastes into the composer without triggering a game action")
		DisplayServer.clipboard_set(previous)
	var before := opened.size()
	main.chat_input.release_focus()
	main.settings_window.binding_changed.disconnect(main._on_binding_changed)
	main.settings_window.begin_capture("open_last_url")
	_key(KEY_F8)
	_expect(opened.size() == before and main.settings_window.capturing.is_empty(),
		"rebinding owns the captured key without opening a browser")
	_key(KEY_F2)
	_expect(opened.size() == before, "rebinding releases the original F2 shortcut")
	_key(KEY_F8)
	_expect(opened.size() == before + 1, "the new binding opens the latest URL")
	app.call("_on_connection_state_changed", "disconnected")
	_expect((reference.known_links() as Array).is_empty()
		and reference.open_last_url() == ERR_DOES_NOT_EXIST
		and reference.open_link_button.disabled, "disconnect clears session URLs and disables stale opens")
	main.queue_free()
	await _settle()
	print("chat clipboard and URL tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_native_copy(output: RichTextLabel) -> void:
	var previous := DisplayServer.clipboard_get()
	var selected := output.get_selected_text()
	_key(KEY_C, true)
	# Native Windows copy uses CRLF; the RichTextLabel model uses LF.
	_expect(DisplayServer.clipboard_get().replace("\r\n", "\n") == selected, "Ctrl+C copies selected " + str(output.name))
	# Right-click the real label, preserving its selection, and use its menu.
	var click := InputEventMouseButton.new()
	click.position = output.get_global_rect().position + Vector2(12, 12)
	click.global_position = click.position
	click.button_index = MOUSE_BUTTON_RIGHT
	click.pressed = true
	root.push_input(click, true)
	click.pressed = false
	root.push_input(click, true)
	await _settle()
	var menu := output.get_menu()
	var index := menu.get_item_index(RichTextLabel.MENU_COPY)
	_expect(menu.visible and index >= 0 and not menu.is_item_disabled(index)
		and output.get_selected_text() == selected, "right-click preserves selection and offers Copy")
	DisplayServer.clipboard_set("sentinel")
	menu.id_pressed.emit(RichTextLabel.MENU_COPY)
	_expect(DisplayServer.clipboard_get().replace("\r\n", "\n") == selected, "the right-click Copy action copies selected text")
	await _capture("copy-menu.png")
	menu.hide()
	DisplayServer.clipboard_set(previous)

func _select_with_mouse(output: RichTextLabel) -> void:
	var start := output.get_global_rect().position + Vector2(4, 8)
	var hover := InputEventMouseMotion.new()
	hover.position = start
	hover.global_position = start
	Input.parse_input_event(hover)
	await _settle()
	var click := InputEventMouseButton.new()
	click.position = start
	click.global_position = start
	click.button_index = MOUSE_BUTTON_LEFT
	click.button_mask = MOUSE_BUTTON_MASK_LEFT
	click.pressed = true
	Input.parse_input_event(click)
	await _settle()
	var motion := InputEventMouseMotion.new()
	motion.position = start + Vector2(135, 0)
	motion.global_position = motion.position
	motion.relative = Vector2(135, 0)
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(motion)
	await _settle()
	click.position = motion.position
	click.global_position = motion.position
	click.button_mask = 0
	click.pressed = false
	Input.parse_input_event(click)
	await _settle()

func _key(code: Key, ctrl := false, echo := false) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.keycode = code
	event.ctrl_pressed = ctrl
	event.pressed = true
	event.echo = echo
	root.push_input(event, true)
	event.pressed = false
	event.echo = false
	root.push_input(event, true)

func _chat(channel: int, text: String) -> void:
	var payload := PackedByteArray([channel])
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _settle() -> void:
	for frame: int in range(5):
		await process_frame

func _capture(filename: String) -> void:
	var folder := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if folder.is_empty() or DisplayServer.get_name() == "headless":
		return
	DirAccess.make_dir_recursive_absolute(folder)
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join(filename))

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
