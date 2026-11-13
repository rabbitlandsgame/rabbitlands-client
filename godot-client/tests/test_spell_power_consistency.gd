extends SceneTree
## Exercise book quotes, quick badges/drag payloads and the real cast entry point.
var failures := 0

func _init() -> void:
	create_timer(60).timeout.connect(func(): push_error("Spell power consistency timed out"); quit(98))
	call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	var main = load("res://src/app/main.tscn").instantiate()
	main.set_script(load("res://tests/fixtures/offline_ui_main.gd"))
	root.add_child(main)
	for frame in range(8): await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.stats = {"magic": 32, "magic_nexus": 2, "ether": 1000}
	state.spell_power = {"heat_bolt": {"limit": 5, "preferred": 1}}
	state.known_knowledge.assign(range(256))
	main.spell_loadout.profile = ""
	main.spell_loadout.assign_slot(0, 69, 3)
	var bar = main.casting_bar
	state.state_changed.emit(&"stats")
	await process_frame
	check(main.spell_catalog.cast_power_limit(69, state.spell_power, state.stats) == 1, "Fire Burst retains its own Nexus gate below the family ceiling")
	check(main.spell_catalog.cast_power_limit(69, {}, state.stats) == 1, "an older server without power state retains the existing quick-cast fallback")
	check(bar.buttons[0].get_node("Power").text == "1" and bar.buttons[0].power == 1, "quick badge and drag payload show the executable power")
	check(bar.buttons[0].tooltip_text.contains("Saved P3; currently limited to P1"), "quick inspection explains the saved tier reduction")
	main._cast_spell_slot(0)
	check(main.magic_selection.pending.get("power") == 1, "quick cast submits the same tier as its badge")
	main.magic_selection.cancel()
	state.stats.magic_nexus = 4
	state.state_changed.emit(&"stats")
	await process_frame
	check(bar.buttons[0].get_node("Power").text == "3" and bar.buttons[0].power == 3, "gaining Nexus refreshes the badge and drag tier")
	main._cast_spell_slot(0)
	check(main.magic_selection.pending.get("power") == 3, "quick cast uses the newly available saved tier")
	main.magic_selection.cancel()
	state.stats.magic_nexus = 1
	state.state_changed.emit(&"stats")
	await process_frame
	main._cast_spell_slot(0)
	check(main.magic_selection.pending.is_empty(), "an unavailable delivery variant does not arm a misleading cast")
	check(main.magic_selection._feedback.contains("Magic Nexus 2"), "a refused quick cast names its Nexus blocker")
	state.stats.magic_nexus = 2
	var book = main.spells_window
	book.open_tab("magic")
	book._on_spell_pressed(69)
	book.requested_power = 3
	book.power_picker.set_value_no_signal(3)
	book._quote_state({"kind": "preview", "id": 69, "requested": 3, "power": 1, "limit": 1,
		"mana": 75, "ready": false, "reason": "Not enough ether.", "reagents": [],
		"power_reason": "Power 3 requires Magic Nexus 4 (current 2)."})
	check(book.requested_power == 1 and int(book.power_picker.value) == 1, "book picker agrees with the effective quote")
	check(book.status_label.text.contains("Magic Nexus 4") and book.status_label.text.contains("Not enough ether"), "tier and supply blockers remain independently visible")
	var output := OS.get_environment("RL_SPELL_POWER_UI_OUT")
	if not output.is_empty() and DisplayServer.get_name() != "headless":
		for frame in range(8): await process_frame
		await RenderingServer.frame_post_draw
		DirAccess.make_dir_recursive_absolute(output)
		check(root.get_texture().get_image().save_png(output.path_join("spell-power-gate.png")) == OK, "captured the effective tier and both blockers")
	book.slot_picker.select(0)
	book._assign_button.pressed.emit()
	check(main.spell_loadout.slots[0].power == 1 and main.spell_loadout.power_for(69) == 1, "book assignment and cast preference save the quoted tier")
	book._quote_state({"kind": "preview", "id": 69, "requested": 3, "power": 3, "limit": 5, "ready": true})
	check(book.cast_button.disabled and book.requested_power == 1, "late quote cannot restore the old request")
	book._quote_state({"kind": "preview", "id": 69, "requested": 1, "power": 1, "limit": 0,
		"ready": false, "reason": "Requires Magic Nexus 2.", "reagents": []})
	check(book._assign_button.disabled and book._assign_button.tooltip_text == "Requires Magic Nexus 2.", "an unavailable base tier cannot be assigned and names its blocker")
	main.spell_loadout.assign_slot(0, -1, 1)
	book._assign_button.pressed.emit()
	check(main.spell_loadout.slots[0].id == -1, "a disabled assignment cannot save a nonexistent tier")
	# Recall's former high tier must not survive in any saved casting surface.
	state.stats = {"magic": 30, "magic_nexus": 2, "ether": 30}
	state.spell_power["recall"] = {"limit": 10, "preferred": 5}
	main.spell_loadout.powers[9] = 5
	main.spell_loadout.assign_slot(0, 9, 10)
	check(main.spell_loadout.slots[0].power == 1 and main.spell_loadout.power_for(9) == 1, "Recall normalizes old slot and book tiers")
	check(main.spell_catalog.cast_power_limit(9, state.spell_power, state.stats) == 1, "Recall stays single-level even with stale server power state")
	state.state_changed.emit(&"stats")
	await process_frame
	check(not bar.buttons[0].get_node("Power").visible and not bar.buttons[0].tooltip_text.contains("Power"), "Recall quickbar has no tier badge or power tooltip")
	book._on_spell_pressed(9)
	check(book.requested_power == 1 and not book.power_picker.visible, "Recall book hides the power control")
	book._quote_state({"kind":"preview", "id":9, "requested":1, "power":1, "limit":1,
		"mana":30, "ready":true, "unlock_level":30, "reagents":[]})
	check(not book.numbers_label.text.contains("Power") and book.numbers_label.text.contains("30"), "Recall quote shows its fixed cost")
	await capture_recall(output, "recall-book.png")
	book.close()
	var requests: Array[Dictionary] = []
	main.magic_selection.request_sender = func(data: Dictionary) -> Error:
		requests.append(data.duplicate(true))
		return OK
	main.magic_selection.begin(9, 10)
	check(requests.back() == {"op":"options", "id":9} and main.magic_selection.pending.power == 1, "Recall always requests destinations, including an old high-tier cast")
	main.magic_selection._receive({"kind":"recall", "id":9, "entries":[
		{"key":"forest:20:21", "map":"forest", "name":"Forest", "x":20, "y":21}]})
	check(main.magic_selection.popup.visible and not main.magic_selection.description.text.contains("Power"), "Recall presents its destination without tiers")
	await capture_recall(output, "recall-destination.png")
	main.magic_selection._confirm()
	check(requests.back() == {"op":"cast", "id":9, "power":1, "entry":"forest:20:21"}, "Recall confirmation submits the chosen destination at its only level")
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("spell power consistency: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func capture_recall(output: String, filename: String) -> void:
	if output.is_empty() or DisplayServer.get_name() == "headless": return
	for frame in range(4): await process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(output)
	check(root.get_texture().get_image().save_png(output.path_join(filename)) == OK, "captured " + filename)
