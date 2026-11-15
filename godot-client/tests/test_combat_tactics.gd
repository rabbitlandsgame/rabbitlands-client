extends SceneTree
var failures := 0
var requests: Array[Dictionary] = []
const Protocol := preload("res://src/network/combat_tactics_protocol.gd")

func _init() -> void: run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func fixture() -> Dictionary:
	var path := OS.get_environment("RL_TACTICS_FIXTURE")
	if not path.is_empty(): return JSON.parse_string(FileAccess.get_file_as_string(path))
	var entry := {"enabled":true,"target":"self","condition":"health_below","value":40,"status":"poison","action":"spell:7","power":1}
	return {"kind":"combat_tactics","version":1,"subject":"self","context":"fixture","role":"self","active":false,"player_active":false,"status":"Paused","notice":"","max_rules":20,
		"subjects":[{"id":"self","name":"My combat actions"}],"actions":[{"id":"attack","name":"Weapon attack"},{"id":"spell:7","name":"Heal","scope":"self","hostile":false},{"id":"item:1653","name":"Use Potion of Mana","scope":"self","item_group":"Ether"}],
		"statuses":[{"id":"shield","name":"Shield","kind":"buff"},{"id":"magic_protection","name":"Magic ward","kind":"buff"},{"id":"poison","name":"Poisoned","kind":"debuff"}],
		"plan":{"revision":0,"selected":0,"profiles":[{"name":"Balanced","rules":[entry]},{"name":"Defensive","rules":[]},{"name":"Offensive","rules":[]}]}}

func run() -> void:
	root.content_scale_size = Vector2i.ZERO
	root.size = Vector2i(1024, 720)
	var state := fixture()
	check(Protocol.valid(state), "actual server tactics state passes the client contract")
	var app := root.get_node("AppState")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(state).to_utf8_buffer())
	check(app.combat_tactics.plan == JSON.parse_string(JSON.stringify(state.plan)), "the real protocol reducer receives the server plan")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify({"kind":"combat_tactics_status", "subject":"self", "active":true, "player_active":true, "status":"Healing", "revision":state.plan.revision}).to_utf8_buffer())
	check(app.player_tactics_active and app.combat_tactics.status == "Healing", "compact status messages update runtime state without replacing the plan")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(state).to_utf8_buffer())
	var invalid: Dictionary = state.duplicate(true)
	invalid.plan.selected = 0.5
	check(not Protocol.valid(invalid), "fractional preset is rejected")
	invalid = state.duplicate(true); invalid.plan.profiles[0].rules[0].enabled = "yes"
	check(not Protocol.valid(invalid), "untyped rule enable is rejected")
	invalid = state.duplicate(true); invalid.plan.profiles[0].rules.resize(21)
	check(not Protocol.valid(invalid), "oversized rule lists are rejected")
	invalid = state.duplicate(true); invalid.plan.profiles[0].rules[0].combat = "unknown"
	check(not Protocol.valid(invalid), "unknown combat filters are rejected")
	var background := ColorRect.new()
	background.color = Color("100d09")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 18)
	root.add_child(margin)
	var panel = load("res://src/ui/combat_tactics_panel.gd").new()
	margin.add_child(panel)
	panel._request = func(data: Dictionary) -> void: requests.append(data.duplicate(true))
	panel.set_state(state)
	check(panel._rules == state.plan.profiles[0].rules, "editor uses authoritative ordered rules")
	check(panel._action_picker.selected_id == panel._rules[0].action, "the displayed action matches the saved spell identity")
	panel._profile_buttons[1].pressed.emit()
	check(requests[-1].revision is int and requests[-1].selected == 1, "preset requests serialize an integer revision after loading JSON")
	var response: Dictionary = state.duplicate(true)
	for index: int in [1, 2, 0]:
		panel._profile_buttons[index].pressed.emit()
		response.plan.selected = index
		response.plan.revision += 1
		app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(response).to_utf8_buffer())
		check(panel._profile_buttons[index].button_pressed and panel._rules == JSON.parse_string(JSON.stringify(response.plan.profiles[index].rules)), "preset acknowledgment updates both the selected button and displayed rules")
	panel.set_state(state)
	var menu_actions: Array[String] = []
	for menu: PopupMenu in panel._action_picker.menus.values():
		for index: int in menu.item_count:
			var key: Variant = menu.get_item_metadata(index)
			if key is String: menu_actions.append(key)
	for action: Dictionary in state.actions:
		check(menu_actions.count(str(action.id)) == 1, "every authoritative action appears in exactly one submenu")
	check(panel._action_picker.menus.has("Standard actions") and panel._action_picker.menus.has("Spells/Healing"), "standard actions and categorized spells have separate menus")
	check_expanded_controls(panel, state)
	panel._saving = true
	panel.set_state(state)
	check_encounter_controls(panel, state)
	panel._saving = true
	panel.set_state(state)
	requests.clear()
	panel._condition_picker.select(3)
	panel._condition_picker.item_selected.emit(3)
	panel._select(panel._status_picker, "shield")
	panel._status_picker.item_selected.emit(panel._status_picker.selected)
	check(panel._rules[0].condition == "has_status" and panel._rules[0].status == "shield", "the shared condition and status controls edit the selected rule")
	panel._action_picker.action_selected.emit("attack")
	check(panel._rules[0].action == "attack" and panel._rules[0].target == "current_target", "changing an action normalizes its target")
	check(panel._editor.find_children("*", "SpinBox", true, false).is_empty(), "weapon attacks do not expose spell Power")
	check(requests.is_empty(), "shared form controls only edit the local draft")
	panel._saving = true
	panel.set_state(state)
	panel._run.pressed.emit()
	check(requests[-1].op == "run" and requests[-1].active, "Start sends an explicit opt-in")
	requests.clear()
	panel._add_rule()
	check(requests.is_empty() and panel._dirty, "editing does not execute or publish actions")
	var draft: Array = panel._rules.duplicate(true)
	var live: Dictionary = state.duplicate(true); live.status = "Waiting for ether"
	panel.set_state(live)
	check(panel._rules == draft, "live status preserves unsaved edits")
	panel._save.pressed.emit()
	check(requests[-1].op == "save" and requests[-1].revision is int and JSON.parse_string(JSON.stringify(requests[-1].rules)) == JSON.parse_string(JSON.stringify(draft)), "Save includes complete rules and an integer authoritative revision")
	for entry: Dictionary in requests[-1].rules:
		check(entry.value is int and entry.power is int, "Save serializes every rule's threshold and power as integers")
	live.plan.profiles[0].rules = draft
	live.plan.revision += 1
	panel.set_state(live)
	check(not panel._dirty and panel._save.disabled, "acknowledged save clears dirty state")
	for index in range(25): panel._add_rule()
	check(panel._rules.size() == int(state.max_rules) and panel._add.disabled, "editor bounds the rule list to the server's rule limit")
	panel._select_rule(1)
	check(panel._selected == 1 and panel._editor_title.text == "Edit Rule 2", "summary selection changes the single shared editor")
	var selected: Dictionary = panel._rules[1].duplicate(true)
	panel._move_rule(1, 0)
	check(panel._selected == 0 and panel._rules[0] == selected and panel._up.disabled, "reordering keeps selection attached to the moved rule")
	check(panel._rows.get_child(0)._can_drop_data(Vector2.ZERO, {"tactics_editor":panel.get_instance_id(), "index":1}), "a rule accepts reordering from its own editor")
	check(not panel._rows.get_child(0)._can_drop_data(Vector2.ZERO, {"tactics_editor":-1, "index":1}), "a rule rejects another editor's drag")
	panel._select_rule(1)
	panel._delete_rule()
	check(panel._rules.size() == int(state.max_rules) - 1 and not panel._add.disabled and panel._dirty, "Delete updates the shared editor and frees a rule slot")
	panel._add_rule()
	check(panel._selected == int(state.max_rules) - 1 and panel._down.disabled, "Add selects the new rule at the lowest priority")
	var dirty_copy: Array = panel._rules.duplicate(true)
	panel._choose_profile(1)
	check(panel._rules == dirty_copy and not panel._profile_buttons[1].button_pressed, "preset switching preserves a dirty draft and authoritative selection")
	check(panel._switch_dialog.visible, "switching a dirty preset offers Save, Discard or Cancel")
	panel._switch_dialog.canceled.emit()
	panel._switch_dialog.hide()
	var conflict: Dictionary = live.duplicate(true)
	conflict.plan.revision += 1
	panel.set_state(conflict)
	panel._changed()
	check(panel._save.disabled and panel._rules == dirty_copy, "further edits cannot re-enable Save for a stale revision")
	panel._more_action(panel.REFRESH)
	check(panel._rules == dirty_copy and requests[-1].op == "get", "Refresh retains the draft until a response arrives")
	var editor_id: int = panel._action_picker.get_instance_id()
	app.combat_tactics = live.duplicate(true)
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify({"kind":"combat_tactics_status", "subject":"self", "active":true, "player_active":true, "status":"Healing", "revision":live.plan.revision}).to_utf8_buffer())
	check(panel._saving and panel._rules == dirty_copy and panel._action_picker.get_instance_id() == editor_id, "runtime ticks cannot acknowledge Refresh, replace the draft or rebuild the editor")
	check(panel._run.disabled and not panel._pause.disabled, "runtime ticks update the explicit Start and Pause controls")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(conflict).to_utf8_buffer())
	check(not panel._dirty and not panel._conflicted, "Refresh replaces the draft and clears the conflict")
	while panel._rules.size() < int(state.max_rules): panel._add_rule()
	var full_request := Protocol.request_payload({"op":"save", "rules":panel._rules}, state)
	check(JSON.stringify(full_request).to_utf8_buffer().size() <= 8192, "all twenty rules fit the server request budget")
	live.plan.profiles[0].rules = panel._rules.duplicate(true)
	for frame in range(8): await process_frame
	check(root.get_visible_rect().encloses(panel._save.get_global_rect()), "Save remains inside the supported viewport")
	app._on_connection_state_changed("disconnected")
	check(not panel._dirty and panel._state.is_empty(), "disconnect clears another account's unsaved draft")
	margin.queue_free(); background.queue_free()
	await process_frame
	var book = load("res://src/ui/spells_window.gd").new()
	root.add_child(book)
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	book.configure(catalog, func(_id: int) -> void: pass)
	book.tactics_panel._request = func(data: Dictionary) -> void: requests.append(data.duplicate(true))
	book.tactics_panel.set_state(live)
	book.open_tab("tactics")
	for dimensions: Vector2i in [Vector2i(1024, 720), Vector2i(960, 540), Vector2i(800, 450)]:
		root.size = dimensions
		book._fit_panel()
		book.tactics_panel._select_rule(int(state.max_rules) - 1)
		for frame in range(8): await process_frame
		check(root.get_visible_rect().encloses(book.panel.get_global_rect()), "Tactics fits the real action book at %s" % dimensions)
		check(book.panel.get_global_rect().encloses(book.tactics_panel._save.get_global_rect()), "Save stays inside the real action book at %s" % dimensions)
		check(book.tactics_panel._inspector.global_position.x >= book.tactics_panel._browser.get_global_rect().end.x, "the shared editor stays beside the list at %s" % dimensions)
		check(book.panel.get_global_rect().encloses(book.tactics_panel._delete.get_global_rect()), "editor actions remain visible at %s" % dimensions)
		var selected_row: Control = book.tactics_panel._rows.get_child(int(state.max_rules) - 1)
		check(book.tactics_panel._rules_scroll.get_global_rect().encloses(selected_row.get_global_rect()), "the last rule scrolls into view at %s: row %s in %s" % [dimensions, selected_row.get_global_rect(), book.tactics_panel._rules_scroll.get_global_rect()])
		check(book.tactics_panel._rules_scroll.scroll_vertical > 0, "twenty rules scroll within the compact window")
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1.5
	book._fit_panel()
	for frame in range(8): await process_frame
	check(root.get_visible_rect().encloses(book.panel.get_global_rect()), "Tactics fits at 150 percent UI scale")
	check(book.panel.get_global_rect().encloses(book.tactics_panel._delete.get_global_rect()), "shared editor actions fit at 150 percent UI scale")
	root.content_scale_factor = 1.0
	var view = book.tactics_panel
	view._rows.get_child(0).enabled_toggle.button_pressed = not view._rules[0].enabled
	view._choose_profile(1)
	view._switch_dialog.hide()
	view._save_and_switch()
	check(requests[-1].op == "save", "Save and switch saves the current draft first")
	var saved_response: Dictionary = live.duplicate(true)
	saved_response.plan.profiles[0].rules = requests[-1].rules.duplicate(true)
	saved_response.plan.revision += 1
	view.set_state(saved_response)
	check(requests[-1].op == "select" and requests[-1].selected == 1 and requests[-1].revision == saved_response.plan.revision, "Save acknowledgment switches using the new revision")
	saved_response.plan.selected = 1
	saved_response.plan.revision += 1
	view.set_state(saved_response)
	check(view._state.plan.selected == 1 and not view._dirty, "Save and switch shows the acknowledged destination preset")
	view._changed()
	view._choose_profile(0)
	view._discard_and_switch()
	check(requests[-1].op == "get", "Discard and switch refreshes the authoritative revision first")
	view.set_state(saved_response)
	check(requests[-1].op == "select" and requests[-1].selected == 0, "Discard acknowledgment proceeds to the chosen preset")
	saved_response.plan.selected = 0
	saved_response.plan.revision += 1
	view.set_state(saved_response)
	var companion: Dictionary = live.duplicate(true)
	companion.subject = "2"; companion.role = "warden"; companion.context = "companion-fixture"; companion.active = true
	companion.subjects.append({"id":"2", "name":"Warden 2"})
	book.tactics_panel.set_state(companion)
	check(not book.tactics_panel._run.visible and not book.tactics_panel._pause.visible and book.tactics_panel._status.text == "Running", "companion configuration preserves role automation without player Start controls")
	companion.plan.profiles[0].rules = []
	book.tactics_panel.set_state(companion)
	check(book.tactics_panel._selected == -1 and not book.tactics_panel._add.disabled, "an empty preset remains usable")
	root.size = Vector2i(1024, 720)
	book._fit_panel()
	book.tactics_panel.set_state(state)
	for frame in range(8): await process_frame
	var evidence := OS.get_environment("RL_TACTICS_SCREENSHOT")
	if not evidence.is_empty():
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(evidence)
	book.queue_free()
	await process_frame
	print("Combat tactics editor: %d failures" % failures)
	quit(1 if failures else 0)

func check_expanded_controls(panel: Control, state: Dictionary) -> void:
	panel._select(panel._condition_picker, "missing_buff")
	panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
	check(panel._rules[0].condition == "missing_buff" and panel._rules[0].status != "poison", "Missing buff normalizes a previously selected debuff")
	for index: int in panel._status_picker.item_count:
		check(panel._status_picker.get_item_metadata(index) != "poison", "the buff picker excludes harmful effects")
	panel._select(panel._status_picker, "shield")
	panel._status_picker.item_selected.emit(panel._status_picker.selected)
	panel._select(panel._target_picker, "ally")
	panel._target_picker.item_selected.emit(panel._target_picker.selected)
	check("Shield missing" in panel._summary(panel._rules[0]) and panel._rules[0].target == "ally", "missing buffs summarize the selected ally and named effect")
	panel._select(panel._condition_picker, "missing_debuff")
	panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
	check(panel._rules[0].status == "poison", "Missing debuff selects a harmful effect")
	for index: int in panel._status_picker.item_count:
		check(panel._status_picker.get_item_metadata(index) != "shield", "the debuff picker excludes beneficial effects")
	panel._select(panel._target_picker, "ally_target")
	panel._target_picker.item_selected.emit(panel._target_picker.selected)
	panel._action_picker.action_selected.emit("attack")
	check(panel._rules[0].target == "ally_target", "choosing another hostile action preserves the ally's opponent selector")
	for action: Dictionary in state.actions:
		if action.id != "technique:intercept": continue
		panel._select(panel._target_picker, "self")
		panel._target_picker.item_selected.emit(panel._target_picker.selected)
		panel._action_picker.action_selected.emit("technique:intercept")
		check(panel._rules[0].target == "ally", "Intercept always selects an ally")
	panel._select(panel._combat_picker, "out_of_combat")
	panel._combat_picker.item_selected.emit(panel._combat_picker.selected)
	check(panel._rules[0].combat == "out_of_combat", "the caster's combat filter is independent of the target condition")
	check(panel._action_picker.menus.has("Items/Ether"), "ether consumables have an Items submenu")
	var menu: PopupMenu = panel._action_picker.menus["Items/Ether"]
	var chosen := str(menu.get_item_metadata(0))
	menu.id_pressed.emit(menu.get_item_id(0))
	check(panel._rules[0].action == chosen and panel._rules[0].target == "self", "item selection uses stable item identity and normalizes to the consumer")
	panel._select(panel._condition_picker, "ether_below")
	panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
	panel._value_picker.value = 25
	panel._save.pressed.emit()
	var saved_request: Dictionary = requests[-1]
	check(saved_request.rules[0].action == chosen and saved_request.rules[0].combat == "out_of_combat" and saved_request.rules[0].value == 25, "Save includes the item, combat filter and threshold")
	var response: Dictionary = state.duplicate(true)
	response.plan.profiles[0].rules = JSON.parse_string(JSON.stringify(saved_request.rules))
	response.plan.revision += 1
	panel.set_state(response)
	panel._more_action(panel.REFRESH)
	panel.set_state(response)
	check(panel._action_picker.selected_id == chosen and panel._combat_picker.get_item_metadata(panel._combat_picker.selected) == "out_of_combat" and panel._rules == response.plan.profiles[0].rules, "a save acknowledgment and Refresh preserve all expanded rule fields")

func check_encounter_controls(panel: Control, state: Dictionary) -> void:
	for condition: String in Protocol.AP_CONDITIONS:
		panel._select(panel._condition_picker, condition)
		panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
		check(panel._value_picker.suffix == " AP" and panel._value_picker.max_value == 65535, "action-point thresholds use point counts")
		panel._value_picker.value = 500
		check(panel._rules[0].value == 500 and "AP" in panel._summary(panel._rules[0]), "AP thresholds above 100 retain their integer point value")
		panel._save.pressed.emit()
		var response: Dictionary = state.duplicate(true)
		response.plan.profiles[0].rules = requests[-1].rules.duplicate(true)
		response.plan.revision += 1
		check(Protocol.valid(response), "server snapshots accept raw AP thresholds above 100")
		panel.set_state(response)
		panel._more_action(panel.REFRESH)
		panel.set_state(response)
		check(panel._rules[0].condition == condition and panel._rules[0].value == 500, "AP comparisons survive Save and Refresh")
	panel._select(panel._condition_picker, "health_below")
	panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
	check(panel._rules[0].value == 100 and panel._value_picker.suffix == "%", "switching from AP to percentages clamps the old point value")
	for condition: String in panel.OPPONENT_CONDITIONS:
		panel._select(panel._condition_picker, condition)
		panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
		check(panel._rules[0].value == 2 and panel._value_picker.suffix.is_empty(), "opponent comparisons start with two opponents and use a count")
		check("Opponents" in panel._summary(panel._rules[0]), "summaries identify the encounter count")
	panel._select(panel._condition_picker, "focused_on_ally")
	panel._condition_picker.item_selected.emit(panel._condition_picker.selected)
	check(panel._rules[0].target == "current_target" and "Focused on another ally" in panel._summary(panel._rules[0]), "focus conditions choose an enemy selector")
	check(panel._editor.find_children("*", "SpinBox", true, false).size() <= 1, "focus conditions do not expose a threshold")
	for action: Dictionary in state.actions:
		if action.id != "technique:provoke": continue
		panel._action_picker.action_selected.emit("technique:provoke")
		check(panel._rules[0].condition == "focused_on_ally" and panel._rules[0].target == "current_target", "Provoke preserves the enemy-focus condition")
	panel._save.pressed.emit()
	var response: Dictionary = state.duplicate(true)
	response.plan.profiles[0].rules = requests[-1].rules.duplicate(true)
	response.plan.revision += 1
	panel.set_state(response)
	panel._more_action(panel.REFRESH)
	panel.set_state(response)
	check(panel._rules[0].condition == "focused_on_ally", "focus conditions survive Save and Refresh")
