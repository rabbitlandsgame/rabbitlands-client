extends SceneTree
## Real keyboard/mouse routing; capture protocol frames without opening a socket.
class CaptureNetwork extends EloriaNetworkClient:
	var outgoing: Array[PackedByteArray] = []
	var result: Error = OK
	func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
		outgoing.append(frame.duplicate())
		return result

var main: Control
var network: Node
var state: Node
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func frames(count := 5) -> void:
	for index: int in count: await process_frame

func press(code: Key) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.pressed = true
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await frames()

func click(control: Control, shift := false, ctrl := false) -> void:
	var point := control.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	root.push_input(motion, true)
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	event.position = point
	event.shift_pressed = shift
	event.ctrl_pressed = ctrl
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await frames()

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	network = root.get_node("Network")
	network.set_script(CaptureNetwork)
	network.block_for_hud_preview()
	state = root.get_node("AppState")
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await frames()
	InputMap.load_from_project_settings()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var workspace: Control = main.hud_workspace
	var chat: Control = main.chat_hud
	for id: String in ["current", "heritage", "classic", "modular", "adventure", "minimal"]:
		workspace.choose_preset(id, true)
		workspace.change_part("chat", "enabled", false)
		chat.input.text = ""
		chat.dismiss()
		root.gui_release_focus()
		await frames()
		expect(not chat.visible, id + ": chat can start disabled")
		await press(KEY_T)
		expect(chat.is_visible_in_tree() and chat.input.has_focus(), id + ": T opens and focuses disabled chat")
		expect(not workspace.model.working.parts.chat.enabled and not chat.options.visible,
			id + ": temporary typing keeps the hidden HUD preference")
		chat.set_destination("pm:Mira")
		chat.input.text = "unfinished private draft"
		main._hide_chat_input()
		await frames()
		await press(KEY_T)
		expect(chat.input.text == "unfinished private draft" and chat.destination_key == "pm:Mira"
			and chat.is_visible_in_tree() and chat.input.has_focus(), id + ": reopening retains draft and recipient")
		chat.input.text = ""
		main._hide_chat_input()
		await frames()
		expect(not chat.visible, id + ": finishing empty temporary chat restores hidden state")
	# Rebound chat shortcuts follow the same route.
	InputMap.action_erase_events("chat_focus")
	var rebound := InputEventKey.new()
	rebound.physical_keycode = KEY_F6
	InputMap.action_add_event("chat_focus", rebound)
	await press(KEY_F6)
	expect(chat.visible and chat.input.has_focus(), "custom chat hotkey also reopens disabled chat")
	chat.dismiss()
	InputMap.load_from_project_settings()
	var actor := Node3D.new()
	root.add_child(actor)
	actor.position = main.adapter.tile_center(130, 214)
	state.local_actor_id = 99
	main.actor_nodes[99] = actor
	main._current_map_display_name = "Landfall"
	state.active_channels.assign([42, 0, 0])
	state.active_channel_index = 0
	for id: String in ["current", "heritage", "classic", "modular", "adventure", "minimal"]:
		workspace.choose_preset(id, true)
		if id in ["modular", "adventure"]: workspace.change_part("compass", "enabled", true)
		root.gui_release_focus()
		await frames()
		var compass: Control = main.compass_face if id == "current" else workspace.modern_compass
		network.outgoing.clear()
		var before: int = state.chat_lines.size()
		await click(compass)
		expect(network.outgoing.is_empty() and state.chat_lines.size() == before + 1
			and str(state.chat_lines.back().text) == "My Position: Landfall (130, 214)",
			id + ": actual compass click prints coordinates locally")
		chat.set_destination("channel:42")
		await click(compass, true)
		expect(network.outgoing.size() == 1 and network.outgoing[0] == EloriaProtocol.chat("@@42 My Position: Landfall (130, 214)"),
			id + ": Shift-click shares to the selected channel")
	# Other chat destinations, including PMs, must use the normal composer routing.
	for destination: String in ["local", "party", "guild", "pm:Mira"]:
		chat.set_destination(destination)
		chat.input.text = "draft stays here"
		network.outgoing.clear()
		await click(workspace.modern_compass, true)
		var message := "My Position: Landfall (130, 214)"
		var expected: PackedByteArray
		match destination:
			"party": expected = EloriaProtocol.chat("#p " + message)
			"guild": expected = EloriaProtocol.chat("#gm " + message)
			"pm:Mira": expected = EloriaProtocol.private_message("Mira " + message)
			_: expected = EloriaProtocol.chat(message)
		expect(network.outgoing.size() == 1 and network.outgoing[0] == expected
			and chat.input.text == "draft stays here" and chat.destination_key == destination,
			"Shift-click routes to " + destination + " without changing the draft")
	chat.set_destination("private")
	network.outgoing.clear()
	await click(workspace.modern_compass, true)
	expect(network.outgoing.is_empty(), "unspecified private recipient cannot receive coordinates")
	chat.set_destination("channel:99")
	await click(workspace.modern_compass, true)
	expect(network.outgoing.is_empty(), "unjoined channel cannot receive coordinates")
	await click(workspace.modern_compass, false, true)
	expect(network.outgoing.size() == 1 and network.outgoing[0] == EloriaProtocol.chat("@My Position: Landfall (130, 214)"),
		"Ctrl-click retains the legacy active numeric channel shortcut")
	network.outgoing.clear()
	main.actor_nodes.erase(99)
	await click(workspace.modern_compass, true)
	expect(network.outgoing.is_empty() and str(state.chat_lines.back().text).contains("not available"),
		"missing player position reports locally without sharing invalid coordinates")
	main.actor_nodes[99] = actor
	chat.set_destination("party")
	network.result = ERR_CONNECTION_ERROR
	await click(workspace.modern_compass, true)
	expect(str(state.chat_lines.back().text).begins_with("Could not share your position"),
		"sharing failures are shown locally")
	network.result = OK
	network.outgoing.clear()
	workspace.choose_preset("heritage", true)
	state.game_minute = 150
	state.game_minute_anchor_msec = 0
	main._update_legacy_clock_and_compass()
	await frames()
	expect(is_equal_approx(workspace.clock_art._angle, deg_to_rad(150)) and main.clock_text.text.begins_with("2:30"),
		"brass dial and digital readout follow the synchronized six-hour game day")
	await click(main.clock_face)
	expect(network.outgoing.size() == 2 and network.outgoing[0] == EloriaProtocol.get_date()
		and network.outgoing[1] == EloriaProtocol.get_time(), "brass clock retains click-to-request server date and time")
	network.outgoing.clear()
	workspace.open_editor()
	workspace.panel.position = Vector2(20, 300)
	await click(workspace.modern_compass, true)
	expect(network.outgoing.is_empty(), "HUD editing never shares coordinates")
	workspace.cancel_edit()
	workspace.choose_preset("current", true)
	await frames()
	expect(not workspace.clock_art.visible and main.clock_face.self_modulate.a == 1 and main.clock_hand.visible,
		"Current restores the original dial and synchronized hand")
	main.actor_nodes.erase(99)
	actor.queue_free()
	main.queue_free()
	await frames(2)
	print("HUD chat/compass: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
