extends SceneTree
## Real message snapshots, membership changes, layout persistence and compact
## non-modal party controls, driven through the production scene.
var failures := 0
var main: Control
var app: Node
var settings_path := ProjectSettings.globalize_path("res://test-artifacts/party-chat-ui/test-settings.cfg")

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(settings_path.get_base_dir())
	var config := ConfigFile.new()
	config.set_value("unrelated", "keep", 42)
	config.save(settings_path)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	var chat: PanelContainer = main.get_node("GameView/ChatWindow")
	chat.set("preferences_path", settings_path)
	root.add_child(main)
	await process_frame
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).show()
	app = root.get_node("AppState")
	app.set("authenticated", true)
	(app.get("chat_lines") as Array).clear()
	main.call("_sync_chat")
	app.call("_on_packet", 71, PackedByteArray([1, 1, 0, 0, 0, 4, 0, 0, 0, 12, 0, 0, 0]))
	await process_frame
	_expect(chat.channel_buttons.size() == 3 and chat.buttons.has("all")
		and chat.buttons.has("general") and chat.buttons.has("party")
		and main.chat_log_tabs.buttons.has("system"), "All, category and every joined-channel tab exist")
	_chat(0, "Ari: local message")
	_chat(0, "[Party] Mira: party message", 4)
	_chat(3, "system message")
	_chat(2, "guild message")
	_chat(1, "private message")
	_chat(6, "channel four message")
	_chat(7, "channel twelve message")
	await process_frame
	var output: RichTextLabel = main.get("chat_output")
	_expect(output.get_parsed_text().contains("local message")
		and output.get_parsed_text().contains("channel four message"), "All includes all message categories")
	for spec: Array in [["general", "local message", "party message"],
			["party", "party message", "local message"],
			["guild", "guild message", "system message"], ["private", "private message", "channel four message"],
			["channel:4", "channel four message", "channel twelve message"]]:
		main.call("_on_chat_tab_pressed", str(spec[0]))
		_expect(output.get_parsed_text().contains(str(spec[1]))
			and not output.get_parsed_text().contains(str(spec[2])), "filter works: " + str(spec[0]))
	_expect(main.system_chat_hud.output.get_parsed_text().contains("system message"), "system messages use their own feed")
	_expect(main.call("_chat_message_for_tab", "hello") == "@@4 hello", "a channel tab addresses its numbered destination")
	_expect(main.call("_chat_message_for_tab", "#party status") == "#party status", "commands stay commands on channel tabs")
	main.call("_on_chat_tab_pressed", "party")
	_expect(main.call("_chat_message_for_tab", "hello") == "#p hello", "Party sends to the party")
	_expect(main.call("_chat_message_for_tab", "/Mira hello") == "/Mira hello", "explicit private addressing stays intact")
	main.call("_on_chat_tab_pressed", "guild")
	_expect(main.call("_chat_message_for_tab", "hello") == "#gm hello", "Guild sends to the guild")
	main.call("_on_chat_tab_pressed", "channel:4")
	app.call("_on_packet", 71, PackedByteArray([0, 4, 0, 0, 0, 12, 0, 0, 0, 0, 0, 0, 0]))
	_expect(main.get("_chat_tab") == "channel:4" and output.get_parsed_text().contains("[#4]"),
		"channel identity and old labels survive slot reordering")
	(chat.channel_buttons[4] as Button).pressed.emit()
	_expect(app.get("active_channel_index") == 0, "a channel button uses its current server slot")
	app.call("_on_packet", 71, PackedByteArray([0, 12, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
	_expect(main.get("_chat_tab") == "all" and not chat.channel_buttons.has(4), "leaving the selected channel returns to All")
	_chat(0, "Ari: [b]literal markup[/b]")
	_expect(output.get_parsed_text().contains("[b]literal markup[/b]"), "message markup is never interpreted")
	await _check_mix_reports(chat, output)
	for index in range(110):
		_chat(0, "background local message %d" % index)
	main.call("_on_chat_tab_pressed", "private")
	_expect(output.get_parsed_text().contains("private message"), "a quiet channel keeps its messages when other channels fill the recent log")
	main.call("_on_chat_tab_pressed", "all")
	chat.dismiss()
	_chat(0, "message while closed")
	_expect(not chat.visible, "incoming messages respect an explicit chat dismissal")
	main.call("_show_chat_input")
	_expect(chat.visible and chat.input.has_focus(), "T reopens and focuses the same chat window")
	main.call("_hide_chat_input")
	_expect(not chat.visible and not chat.input.has_focus(), "leaving empty input restores the dismissed chat window")
	chat.open_chat()
	chat.position = Vector2(180, 220)
	chat.resize_window(Vector2(520, 310))
	chat.save_layout()
	var remembered := WindowPreferences.stored_rect("chat_soft", Rect2(), settings_path)
	_expect(remembered == Rect2(chat.position, chat.size), "chat position and size are saved together")
	config.load(settings_path)
	_expect(int(config.get_value("unrelated", "keep", 0)) == 42, "saving the layout preserves other preferences")
	await _settle()
	var size_before := chat.size
	await _drag(chat.grip, Vector2(70, 45))
	_expect(chat.size.is_equal_approx(size_before + Vector2(70, 45)), "dragging the corner resizes the real chat surface")
	var position_before := chat.position
	await _drag(chat.get_node("Frame/Layout/Header/Title"), Vector2(60, -70))
	_expect(chat.position.is_equal_approx(position_before + Vector2(60, -70)), "dragging the header moves the real chat surface")
	remembered = WindowPreferences.stored_rect("chat_soft", Rect2(), settings_path)
	_expect(remembered == Rect2(chat.position, chat.size), "mouse release saves the changed layout")
	chat.position = Vector2(4000, 4000)
	chat.resize_window(Vector2(4000, 4000))
	_expect(chat.get_global_rect().end.x <= 1184 and chat.get_global_rect().end.y <= 680,
		"resizing and dragging cannot lose chat offscreen or cover the resource rail")
	root.size = Vector2i(1024, 600)
	await _settle()
	var canvas_bounds := root.get_visible_rect().size
	_expect(chat.get_global_rect().end.x <= canvas_bounds.x - 96 and chat.get_global_rect().end.y <= canvas_bounds.y - 40,
		"shrinking the game window also clamps the chat size and position")
	root.size = Vector2i(1280, 720)
	chat.position = remembered.position
	chat.resize_window(remembered.size)
	await _settle()
	await _check_sending()
	var windows: Control = main.get("extension_windows")
	windows.set("preferences_path", settings_path)
	windows.set("_party_collapsed", false)
	windows.set("_party_custom_size", false)
	windows.set("_party_expanded_size", Vector2(244, 0))
	app.call("_on_packet", 240, _hex("0102037800b40028003c000003e0014b656c6c616e00666f75725f676174657300045a0096000a0037009a00b6004d6172656e006d6972726f72686f6c6400000000"))
	await process_frame
	_expect(windows.party_panel.size.x <= 246 and not windows.has_open_window(), "party roster is narrow and does not act as a modal window")
	_expect(windows.party_rows.get_child(0).get_node("Portrait").get("leader"), "the leader's medallion carries a crown")
	var expanded: float = windows.party_panel.size.y
	windows.party_collapse.pressed.emit()
	await process_frame
	_expect(windows.party_panel.visible and not windows.party_scroll.visible
		and windows.party_panel.size.y < expanded, "collapse leaves only the compact party header")
	windows.party_collapse.pressed.emit()
	await process_frame
	_expect(windows.party_scroll.visible and windows.party_rows.get_child_count() == 2, "expand restores the live roster")
	windows.party_panel.position = Vector2(28, 80)
	windows.party_collapse.pressed.emit()
	var restored_party: Control = (load("res://src/ui/extension_windows.gd") as GDScript).new()
	restored_party.set("preferences_path", settings_path)
	root.add_child(restored_party)
	await _settle()
	_expect(not restored_party.party_scroll.visible and restored_party.party_panel.position.is_equal_approx(Vector2(28, 80)),
		"a fresh party surface restores its position and collapsed state")
	restored_party.free()
	windows.close_all()
	main.queue_free()
	await process_frame
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	chat = main.get_node("GameView/ChatWindow")
	chat.set("preferences_path", settings_path)
	root.add_child(main)
	await _settle()
	_expect(chat.position.is_equal_approx(remembered.position) and chat.size.is_equal_approx(remembered.size),
		"a fresh client scene restores the saved chat position and size")
	main.free()
	await process_frame
	print("party/chat HUD tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## The inventory and manufacturing windows show each finished mix as item
## text, so with either open the server's chat copy of it stays out of chat.
func _check_mix_reports(chat: PanelContainer, output: RichTextLabel) -> void:
	output = main.system_chat_hud.output
	var inventory: Control = main.get("inventory_panel")
	var manufacturing: Control = main.get("manufacturing_panel")
	var console: RichTextLabel = main.get("console_output")
	inventory.hide()
	manufacturing.hide()
	_chat(0, "You successfully mixed Torch.", 10)
	_expect(output.get_parsed_text().contains("mixed Torch."), "a mix report reaches chat while neither window is open")
	inventory.show()
	chat.hide()
	_chat(0, "You successfully mixed Bone Powder.", 10)
	_expect(not output.get_parsed_text().contains("Bone Powder"), "an open inventory keeps its mix reports out of chat")
	_expect(not chat.visible, "a mix report the inventory shows does not bring chat up")
	inventory.hide()
	manufacturing.show()
	_chat(0, "You successfully mixed Fire Essence.", 10)
	_chat(0, "Ari: still talking")
	_expect(not output.get_parsed_text().contains("Fire Essence")
		and main.chat_output.get_parsed_text().contains("still talking"),
		"an open manufacturing window keeps its mix reports out of chat, and nothing else")
	_expect(chat.visible, "other lines still bring chat up while a window is open")
	manufacturing.hide()
	main.call("_sync_chat")
	_expect(not output.get_parsed_text().contains("Bone Powder")
		and not output.get_parsed_text().contains("Fire Essence"),
		"closing the window does not bring the held reports back into chat")
	_expect(console.get_parsed_text().contains("Bone Powder")
		and console.get_parsed_text().contains("Fire Essence"), "the console still keeps every mix report")

func _chat(channel: int, message: String, colour: int = 0) -> void:
	var payload := PackedByteArray([channel, 128 + colour])
	payload.append_array(message.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _settle() -> void:
	for frame in range(4):
		await process_frame

func _check_sending() -> void:
	var network: Node = root.get_node("Network")
	var old_peer: StreamPeerTCP = network.get("_peer")
	var was_secure: bool = network.get("_secure")
	var peer := StreamPeerTCP.new()
	var listener := TCPServer.new()
	if listener.listen(0, "127.0.0.1") != OK:
		_expect(false, "the local sending fixture listens")
		return
	main.set_process(false)
	network.set_process(false)
	network.set("_secure", false)
	network.set("_peer", peer)
	peer.connect_to_host("127.0.0.1", listener.get_local_port())
	for attempt in range(30):
		peer.poll()
		if listener.is_connection_available():
			break
		await create_timer(0.01).timeout
	var receiver: StreamPeerTCP = listener.take_connection()
	if receiver == null:
		_expect(false, "the local sending fixture connects")
	else:
		peer.poll()
		app.call("_on_packet", 71, PackedByteArray([0, 4, 0, 0, 0, 12, 0, 0, 0, 0, 0, 0, 0]))
		(main.chat_hud.channel_buttons[12] as Button).pressed.emit()
		_expect(await _received(receiver) == EloriaProtocol.set_active_channel(1), "channel clicks send the actual server slot")
		main.call("_on_chat_submitted", "hello channel")
		_expect(await _received(receiver) == EloriaProtocol.chat("@@12 hello channel"), "channel text reaches the wire with channel addressing")
		app.call("_on_packet", 71, PackedByteArray([1, 12, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0]))
		main.call("_on_chat_submitted", "after reorder")
		var expected := EloriaProtocol.chat("@@12 after reorder")
		_expect(await _received(receiver) == expected, "sending after slot reordering retains the channel number")
		for spec: Array in [["party", "ready", "#p ready"], ["guild", "hello", "#gm hello"],
				["channel:12", "#party status", "#party status"]]:
			main.call("_on_chat_tab_pressed", str(spec[0]))
			main.call("_on_chat_submitted", str(spec[1]))
			_expect(await _received(receiver) == EloriaProtocol.chat(str(spec[2])), "tab sends the expected protocol frame: " + str(spec[0]))
		main.chat_hud.set_destination("local")
		main.chat_hud.dismiss()
		main.call("_show_chat_input")
		main.chat_input.text = "resumed hidden draft"
		main.call("_hide_chat_input")
		main.call("_show_chat_input")
		main.chat_input.text_submitted.emit(main.chat_input.text)
		_expect(await _received(receiver) == EloriaProtocol.chat("resumed hidden draft"),
			"a resumed draft reaches the local test connection")
		_expect(not main.chat_hud.visible and not main.chat_input.has_focus() and main.chat_input.text.is_empty(),
			"sending a resumed draft restores the previously hidden window")
		main.chat_hud.open_chat()
		receiver.disconnect_from_host()
	peer.disconnect_from_host()
	listener.stop()
	network.set("_peer", old_peer)
	network.set("_secure", was_secure)
	network.set_process(true)
	main.set_process(true)

func _received(receiver: StreamPeerTCP) -> PackedByteArray:
	await _settle()
	receiver.poll()
	return receiver.get_data(receiver.get_available_bytes())[1]

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
