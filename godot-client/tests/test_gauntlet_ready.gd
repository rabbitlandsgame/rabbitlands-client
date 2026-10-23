extends SceneTree

var failures := 0
var sent: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func _record(text: String) -> Error:
	sent.append(text)
	return OK

func _snapshot() -> Dictionary:
	return {"version": 1, "open": true, "check_id": "test-check",
		"route": "The Harrowcrag Road", "difficulty": "A hard road", "level": 60,
		"is_leader": true, "can_start": false, "in_party": true,
		"members": [
			{"name": "Mira", "self": true, "leader": true, "ready": false, "status": "Not ready"},
			{"name": "Rowan", "self": false, "leader": false, "ready": true, "status": "Ready"},
			{"name": "Kellan", "self": false, "leader": false, "ready": false, "status": "Offline"}]}

func _run() -> void:
	create_timer(60).timeout.connect(func() -> void: quit(1))
	root.size = Vector2i(1280, 800)
	var app: Node = root.get_node("AppState")
	root.get_node("Network").block_for_hud_preview()
	var surface := Control.new()
	root.add_child(surface)
	surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var windows: Control = load("res://src/ui/extension_windows.gd").new()
	surface.add_child(windows)
	var window: Control = windows.gauntlet_ready_window
	window.configure(_record)
	var stack := WindowStack.new()
	root.add_child(stack)
	stack.configure(surface)
	stack.register(window.panel)
	var state := _snapshot()
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	await process_frame
	_expect(window.panel.visible and window.panel in stack._windows, "ready check opens in the window stack")
	windows.toggle_quest_journal()
	_expect(window.panel.visible, "opening another window keeps the ready check accessible")
	windows.quest_panel.hide()
	_expect(window.rows.get_child_count() == 3, "all members are shown, including offline members")
	_expect(window.start_button.visible and window.start_button.disabled, "leader waits until all are ready")
	_expect("The Harrowcrag Road" in window.selection.text and "A hard road" in window.selection.text,
		"chosen map and difficulty are shown")
	window.ready_button.pressed.emit()
	_expect(sent.back() == "#gauntlet ready test-check", "Ready sends only the local player's consent")
	_expect(window.ready_button.text == "Ready", "readiness waits for the server's reply")
	for member: Dictionary in state.members:
		member.ready = true
		member.status = "Ready"
	state.can_start = true
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	_expect(not window.start_button.disabled and window.ready_button.text == "Not ready", "all ready enables Start")
	_expect(sent.size() == 1, "all ready does not automatically start")
	window.ready_button.pressed.emit()
	_expect(sent.back() == "#gauntlet unready test-check", "a member can withdraw readiness")
	window.start_button.pressed.emit()
	_expect(sent.back() == "#gauntlet start test-check", "leader explicitly starts")
	window.cancel_button.pressed.emit()
	_expect(sent.back() == "#gauntlet cancel test-check", "Cancel ends the shared check")
	window.leave_button.pressed.emit()
	_expect(sent.back() == "#gauntlet leave test-check", "Leave party uses the checked roster")
	state.is_leader = false
	state.members[0].leader = false
	state.members[1].leader = true
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	_expect(not window.start_button.visible, "ordinary members have no Start button")
	for index: int in range(5):
		state.members.append({"name": "Companion %d" % index, "self": false,
			"leader": false, "ready": false, "status": "Not ready"})
	state.can_start = false
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	root.size = Vector2i(1024, 600)
	await process_frame
	await process_frame
	var bounds: Vector2 = window.get_viewport_rect().size - Vector2(96, 88)
	_expect(window.panel.get_global_rect().end.x <= bounds.x and window.panel.get_global_rect().end.y <= bounds.y,
		"eight-member window fits a compact screen and clears the HUD")
	_expect(window.panel.get_global_rect().encloses(window.leave_button.get_global_rect()), "Leave party stays reachable")
	var capture := OS.get_environment("RL_GAUNTLET_CAPTURE")
	if not capture.is_empty():
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(capture)
	app._on_packet(193, JSON.stringify({"version": 1, "open": false, "reason": "Cancelled"}).to_utf8_buffer())
	_expect(not window.panel.visible, "cancellation closes the window")
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	_expect(windows.close_top() and sent.back() == "#gauntlet cancel test-check", "Escape cancels through the game window cascade")
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	app._on_connection_state_changed("disconnected")
	_expect(not window.panel.visible and app.gauntlet_ready.is_empty(), "disconnect clears the ready check")
	for invalid: Dictionary in [{}, {"version": 1, "open": true}, {"version": 1, "open": "yes"}]:
		_expect(EloriaProtocol.decode_server(193, JSON.stringify(invalid).to_utf8_buffer()).type == "invalid",
			"malformed ready check is rejected")
	_expect("gauntlet_ready_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "client declares the implemented window")
	print("gauntlet ready: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)
