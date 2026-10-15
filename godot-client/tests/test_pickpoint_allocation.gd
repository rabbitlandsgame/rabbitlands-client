extends SceneTree

var failures := 0
var main: Control
var state: Node
var network: Node
var listener := TCPServer.new()
var receiver: StreamPeerTCP

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	create_timer(30).timeout.connect(func(): push_error("pickpoint fixture timed out"); quit(1))
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	state = root.get_node("AppState")
	network = root.get_node("Network")
	network.set_process(false)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	state.authenticated = true
	state.stats = {"health": 20, "max_health": 20, "ether": 32, "max_ether": 32,
		"pickpoints_earned": 8, "pickpoints_spent": 0, "overall": 8}
	state.attributes.clear()
	for key: String in ["matter", "toughness", "carry", "charm", "reaction", "perception",
			"rationality", "magic_offense", "magic_defense", "dexterity", "ethereality", "might"]:
		state.attributes.append({"key": key, "label": key.capitalize(), "value": 4, "maximum": 100})
	main.stats_panel.show()
	main._sync_stats()
	for i in range(4): await process_frame
	var body: VBoxContainer = main.stats_character
	var scroll: ScrollContainer = body.get_parent()
	var first: Control = body.get_node("Rowmatter")
	var plus: Button = first.get_node("Spend")
	var minus: Button = first.get_node("Remove")
	var summary: Label = main.stats_pickpoint_summary
	var confirm: Button = main.stats_pickpoint_confirm
	expect(minus.disabled and not plus.disabled and confirm.disabled, "fresh draft has only plus available")
	expect(minus.get_index() < first.get_node("Value").get_index() and plus.get_index() > first.get_node("Value").get_index(), "minus and plus flank the value")
	plus.pressed.emit()
	plus.pressed.emit()
	expect(state.attributes[0].value == 4 and state.stats.pickpoints_spent == 0, "preview does not change authoritative values")
	expect(first.get_node("Value").text == "6 / 6" and summary.text.ends_with("6"), "preview and budget reflect two selected points")
	expect(not main.purchase_confirm.visible and not confirm.disabled, "plus uses one shared Confirm button without a popup")
	minus.pressed.emit()
	minus.pressed.emit()
	main._adjust_pickpoint("attribute", "matter", -1)
	expect(main._pickpoint_draft.is_empty() and minus.disabled, "minus cannot remove committed points")
	for i in range(7): main._adjust_pickpoint("attribute", "magic_defense", 1)
	main._adjust_pickpoint("nexus", "animal_nexus", 1)
	main._adjust_pickpoint("attribute", "matter", 1)
	expect(main._draft_pickpoints() == 8 and summary.text.ends_with("0"), "all available points can be assigned without overspending")
	for row: Node in body.get_children():
		if row.has_meta("allocation"): expect(row.get_node("Spend").disabled, "all plus buttons stop at the shared budget")
	main._adjust_pickpoint("attribute", "magic_defense", -1)
	expect(not plus.disabled, "minus frees a point for another attribute")
	var guide: Control = main.lantern_guide
	guide.apply_state({"active": true, "key": "attribute", "control": "stats", "title": "Choose your strength",
		"hint": "Assign two pickpoints to any attributes, then click Confirm.", "required": 2, "count": 0})
	var header_y := summary.global_position.y
	scroll.scroll_vertical = 190
	for i in range(3): await process_frame
	var old_scroll := scroll.scroll_vertical
	main._adjust_pickpoint("attribute", "magic_defense", 1)
	await process_frame
	expect(scroll.scroll_vertical == old_scroll, "adjusting a value does not jump the scroll position")
	expect(summary.global_position.y == header_y, "available points stay at the top while scrolling")
	expect(guide.control_for_step() == confirm, "tutorial points to Confirm once a draft is ready")
	await capture("pickpoints-preview.png")
	# Clear the draft to exercise the attribute highlight while scrolling.
	main._pickpoint_draft.clear()
	main._refresh_pickpoint_controls()
	for offset: int in [0, 40, 190, 300, 600]:
		scroll.scroll_vertical = offset
		for i in range(3): await process_frame
		var rect: Rect2 = guide._highlight_rect(plus)
		expect(not rect.has_area() or scroll.get_global_rect().encloses(rect), "highlight stays clipped to the scrolling viewport")
		if offset == 190:
			expect(not rect.has_area(), "offscreen attribute has no floating outline")
			var target: Control = guide.control_for_step()
			expect(target != plus, "tutorial selects a visible attribute after scrolling")
			expect(guide._highlight_rect(target).has_area(), "replacement highlight is visible")
	scroll.scroll_vertical = 190
	for i in range(3): await process_frame
	await capture("pickpoints-scrolled.png")
	# Server changes preserve the draft and enforce updated affordability.
	main._adjust_pickpoint("attribute", "magic_defense", 1)
	main._adjust_pickpoint("attribute", "magic_defense", 1)
	state.stats.pickpoints_spent = 7
	main._sync_stats()
	expect(confirm.disabled and main._draft_pickpoints() == 2, "a stale unaffordable draft stays editable but cannot commit")
	main._adjust_pickpoint("attribute", "magic_defense", -1)
	expect(not confirm.disabled, "reducing a stale draft makes it affordable")
	state.stats.pickpoints_spent = 0
	main._sync_stats()
	# A real loopback transport proves Confirm sends exactly one batch.
	expect(listener.listen(0, "127.0.0.1") == OK, "loopback listener starts")
	network._peer.connect_to_host("127.0.0.1", listener.get_local_port())
	var deadline := Time.get_ticks_msec() + 2000
	while not listener.is_connection_available() and Time.get_ticks_msec() < deadline:
		network._peer.poll()
		await process_frame
	if not listener.is_connection_available():
		expect(false, "loopback transport connects")
		finish()
		return
	receiver = listener.take_connection()
	network._peer.poll()
	confirm.pressed.emit()
	main._confirm_pickpoints()
	expect(main._pickpoint_submitting and confirm.disabled, "confirmation locks the draft against duplicate submission")
	await create_timer(.1).timeout
	receiver.poll()
	var data: PackedByteArray = receiver.get_data(receiver.get_available_bytes())[1]
	var expected := EloriaProtocol.chat("#spend batch attribute:magic_defense:1")
	expect(data == expected, "one confirmation sends exactly one batch frame")
	for attribute: Dictionary in state.attributes:
		if attribute.key == "magic_defense": attribute.value = 5
	state.stats.pickpoints_spent = 1
	state.chat_lines.append({"channel": 0, "text": "Pickpoint allocation confirmed: Spent 1 pickpoints."})
	main._on_pickpoint_reply()
	expect(not main._pickpoint_submitting and main._pickpoint_draft.is_empty(), "server acceptance clears the committed draft")
	expect(main.stats_character.get_node("Rowmagic_defense/Remove").disabled, "confirmed points cannot be undone with minus")
	main._adjust_pickpoint("attribute", "magic_defense", 1)
	main._confirm_pickpoints()
	state.chat_lines.append({"channel": 0, "text": "Pickpoint allocation rejected: You do not have enough pick points."})
	main._on_pickpoint_reply()
	expect(not main._pickpoint_submitting and main._draft_pickpoints() == 1, "rejection preserves the draft for editing")
	main._pickpoint_draft.clear()
	state.attributes[0].value = 99
	state.stats.animal_nexus = 9
	main._sync_stats()
	for i in range(2):
		main._adjust_pickpoint("attribute", "matter", 1)
		main._adjust_pickpoint("nexus", "animal_nexus", 1)
	expect(main._draft_pickpoints() == 2, "attribute and nexus previews stop at their separate caps")
	main._pickpoint_draft.clear()
	state.attributes[0].value = 105
	main._sync_stats()
	main._adjust_pickpoint("attribute", "carry", 1)
	expect(not confirm.disabled, "an unrelated buff above a cap does not prevent spending elsewhere")
	network._peer.disconnect_from_host()
	main._on_connection_state_changed("disconnected")
	expect(main._pickpoint_draft.is_empty(), "disconnect clears the draft for the next character")
	finish()

func capture(filename: String) -> void:
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty() or DisplayServer.get_name() == "headless": return
	DirAccess.make_dir_recursive_absolute(output)
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(filename))

func finish() -> void:
	listener.stop()
	print("pickpoint allocation: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)
