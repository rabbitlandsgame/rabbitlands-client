extends SceneTree

var failures := 0
var sent: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func _record(command: String) -> Error:
	sent.append(command)
	return OK

func _row(flags: int, player_name: String, map_id: String = "") -> PackedByteArray:
	var result := PackedByteArray([flags])
	for number: int in [80, 100, 20, 40, 0, 0]:
		result.append(number & 255)
		result.append(number >> 8)
	result.append_array(player_name.to_utf8_buffer())
	result.append(0)
	result.append_array(map_id.to_utf8_buffer())
	result.append(0)
	return result

func _run() -> void:
	create_timer(45).timeout.connect(func() -> void: quit(1))
	root.size = Vector2i(1024, 600)
	var app: Node = root.get_node("AppState")
	root.get_node("Network").block_for_hud_preview()
	var surface := Control.new()
	root.add_child(surface)
	surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var windows: Control = load("res://src/ui/extension_windows.gd").new()
	windows.preferences_path = "res://test-artifacts/gauntlet-bots-window.cfg"
	surface.add_child(windows)
	var stack := WindowStack.new()
	root.add_child(stack)
	stack.configure(surface)
	stack.register(windows.party_panel)
	stack.register(windows.gauntlet_ready_window.panel)
	var payload := PackedByteArray([1, 2])
	payload.append_array(_row(7, "Leader", "four_gates"))
	payload.append_array(_row(1 | 8 | (3 << 4), "Warden 1 (Bot)"))
	payload.append_array(PackedByteArray([0, 0, 0]))
	app._on_packet(240, payload)
	await process_frame
	_expect(app.party.members[1].is_bot and app.party.members[1].class_id == 3, "party flags retain bot class")
	_expect(windows.party_add_bot.visible and windows.party_add_bot.get_popup().item_count == 4,
		"party leader can choose any of four classes")
	_expect(windows.party_rows.get_child(1).get_node("Vitals/Identity/Name").text == "Warden 1 (Bot)",
		"bot appears below humans with its marker")
	_expect(windows.party_rows.get_child(1).has_node("RemoveBot"), "leader can dismiss a bot")
	_expect(windows.party_rows.get_child(1).get_node("Vitals/Identity/Standing").text == "standby",
		"unspawned bot is shown as standby")
	var window: Control = windows.gauntlet_ready_window
	window.configure(_record)
	var state := {"version": 1, "open": true, "check_id": "bots-ready", "route": "The Resin Road",
		"difficulty": "A fair fight", "level": 30, "is_leader": true, "can_start": false, "in_party": true,
		"members": [{"name": "Leader", "self": true, "leader": true, "ready": false, "status": "Not ready"},
			{"name": "Warden 1 (Bot)", "self": false, "leader": false, "ready": true,
			"status": "Ready · Healer", "bot": true, "class_id": 3, "id": "!bot_1_1"}]}
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	window.add_bot.get_popup().id_pressed.emit(0)
	_expect(sent.back() == "#gauntlet addbot bots-ready 0", "prepare picker sends class and current consent token")
	(window.rows.get_child(1).get_child(2) as Button).pressed.emit()
	_expect(sent.back() == "#gauntlet removebot bots-ready !bot_1_1", "dismissal uses server bot identity")
	_expect(window.start_button.disabled, "automatic bot readiness never consents for a human")
	for class_id: int in range(6):
		state.members.append({"name": "Companion %d (Bot)" % class_id, "self": false, "leader": false,
			"ready": true, "status": "Ready", "bot": true, "class_id": class_id % 4, "id": "bot%d" % class_id})
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	root.size = Vector2i(1024, 600)
	for frame: int in range(8): await process_frame
	_expect(window.add_bot.disabled, "bots share the eight-member limit")
	var available: Vector2 = window.get_viewport_rect().size - Vector2(96, 88)
	_expect(window.panel.get_global_rect().end.y <= available.y
		and window.panel.get_global_rect().encloses(window.add_bot.get_global_rect()), "eight-member prepare controls fit a compact screen")
	state.is_leader = false
	app._on_packet(193, JSON.stringify(state).to_utf8_buffer())
	_expect(not window.add_bot.visible and window.rows.get_child(1).get_child_count() == 2,
		"ordinary members cannot manage prepare bots")
	payload = PackedByteArray([1, 2])
	payload.append_array(_row(4 | 1, "Member", "four_gates"))
	payload.append_array(_row(1 | 8 | (3 << 4), "Warden 1 (Bot)"))
	payload.append_array(PackedByteArray([0, 0, 0]))
	app._on_packet(240, payload)
	_expect(not windows.party_add_bot.visible and not windows.party_rows.get_child(1).has_node("RemoveBot"),
		"ordinary party members have no bot controls")
	state.members[1].erase("id")
	_expect(EloriaProtocol.decode_gauntlet_ready(JSON.stringify(state).to_utf8_buffer()).type == "invalid",
		"invalid bot metadata is rejected")
	print("gauntlet bots UI: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
