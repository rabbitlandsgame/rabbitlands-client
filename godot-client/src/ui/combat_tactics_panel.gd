extends VBoxContainer
## Ordered drafts stay local until Save. One shared editor follows selection.
const UI := preload("res://src/ui/action_book_ui.gd")
const Style := preload("res://src/ui/combat_tactics_style.gd")
const RuleRow := preload("res://src/ui/combat_tactics_rule_row.gd")
const ActionPicker := preload("res://src/ui/combat_tactics_action_picker.gd")
const Protocol := preload("res://src/network/combat_tactics_protocol.gd")
const TARGETS := ["self", "ally", "leader_target", "current_target", "party_attacker", "lowest_enemy", "nearest_enemy", "ally_target"]
const TARGET_LABELS := ["Self", "Ally: lowest health", "Leader's opponent", "Current opponent", "Opponent attacking party", "Engaged foe: lowest health", "Nearest engaged foe", "Ally's opponent"]
const COMBAT_STATES := ["any", "in_combat", "out_of_combat"]
const COMBAT_LABELS := ["Any state", "In combat", "Out of combat"]
const CONDITIONS := ["always", "health_below", "ether_below", "has_status", "missing_status", "missing_buff", "missing_debuff", "action_points_below", "action_points_at_least", "opponents_below", "opponents_at_least", "focused_on_ally"]
const CONDITION_LABELS := ["Always", "Health below %", "Ether below %", "Has status", "Missing status", "Missing buff", "Missing debuff", "Action points below", "Action points at least", "Opponents fewer than", "Opponents at least", "Enemy focused on ally"]
const CONDITION_SHORT_LABELS := ["Always", "Health <", "Ether <", "Has status", "Missing status", "Missing buff", "Missing debuff", "AP below", "AP at least", "Opponents <", "Opponents ≥", "Focus on ally"]
const OPPONENT_CONDITIONS := ["opponents_below", "opponents_at_least"]
const STATUSES := ["poison", "shield", "regeneration", "magic_protection", "magic_immunity", "haste", "accuracy"]
const STATUS_LABELS := ["Poisoned", "Shield", "Regeneration", "Magic ward", "Magic immunity", "Haste", "Accuracy"]
const REFRESH := 0
const RESTORE := 1
var _state: Dictionary = {}
var _rules: Array = []
var _dirty := false
var _saving := false
var _conflicted := false
var _selected := -1
var _subjects: OptionButton
var _profile_buttons: Array[Button] = []
var _run: Button
var _pause: Button
var _status: Label
var _message: Label
var _rows: VBoxContainer
var _rules_scroll: ScrollContainer
var _follow_pending := false
var _save: Button
var _add: Button
var _more: MenuButton
var _count: Label
var _editor: VBoxContainer
var _editor_title: Label
var _panes: HBoxContainer
var _browser: VBoxContainer
var _inspector: PanelContainer
var _help: Label
var _hint: Label
var _target_picker: OptionButton
var _condition_picker: OptionButton
var _condition_pickers: Array[OptionButton] = []
var _condition_inputs: Array[Control] = []
var _condition_remove_buttons: Array[Button] = []
var _condition_scroll: ScrollContainer
var _condition_list: VBoxContainer
var _condition_focus := 0
var _add_if: Button
var _combat_picker: OptionButton
var _action_picker: MenuButton
var _value_picker: SpinBox
var _status_picker: OptionButton
var _power_picker: SpinBox
var _up: Button
var _down: Button
var _delete: Button
var _request: Callable
var _short := false
var _switch_dialog: ConfirmationDialog
var _switch_target: Dictionary = {}
var _after_ack_switch: Dictionary = {}

func _ready() -> void:
	name = "CombatTactics"
	theme = Style.theme()
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 7)
	_request = func(data: Dictionary) -> void: Network.send_chat("#tactics " + JSON.stringify(data))
	var top := HBoxContainer.new()
	top.name = "TacticsToolbar"
	top.add_theme_constant_override("separation", 6)
	add_child(top)
	_subjects = OptionButton.new()
	_subjects.name = "TacticsSubject"
	_subjects.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_subjects.fit_to_longest_item = false
	_subjects.clip_text = true
	_subjects.custom_minimum_size.x = 170
	_subjects.item_selected.connect(_choose_subject)
	top.add_child(_subjects)
	var profiles := HBoxContainer.new()
	profiles.name = "TacticsPresets"
	profiles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	profiles.size_flags_stretch_ratio = 1.05
	profiles.add_theme_constant_override("separation", 0)
	top.add_child(profiles)
	for index: int in 3:
		var button := Style.button(["Balanced", "Defensive", "Offensive"][index])
		button.toggle_mode = true
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.pressed.connect(_choose_profile.bind(index))
		profiles.add_child(button)
		_profile_buttons.append(button)
	_run = Style.button("▶ Start", true)
	_run.name = "StartTactics"
	_run.custom_minimum_size.x = 80
	_run.tooltip_text = "Start or resume my combat tactics. Attack and Charge keep tactics running. During combat, Ctrl-click ground to retreat; Escape or Pause stops tactics."
	_run.pressed.connect(func() -> void: _send({"op":"run", "active":true}))
	top.add_child(_run)
	_pause = Style.button("Ⅱ Pause")
	_pause.name = "PauseTactics"
	_pause.custom_minimum_size.x = 80
	_pause.pressed.connect(func() -> void: _send({"op":"run", "active":false}))
	top.add_child(_pause)
	var status_row := HBoxContainer.new()
	status_row.add_theme_constant_override("separation", 10)
	add_child(status_row)
	_status = Style.label("Not connected", 13)
	_status.name = "TacticsStatus"
	_status.add_theme_stylebox_override("normal", Style.box(Color("423016"), Style.BRASS, 4))
	status_row.add_child(_status)
	_help = Style.label("Attack and Charge keep tactics running.", 12, true)
	_help.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_help.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	status_row.add_child(_help)
	_message = Style.label("", 12)
	_message.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_message.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_message.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	status_row.add_child(_message)
	add_child(Style.line())
	_panes = HBoxContainer.new()
	_panes.name = "TacticsPanes"
	_panes.add_theme_constant_override("separation", 10)
	_panes.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(_panes)
	_browser = VBoxContainer.new()
	_browser.name = "PriorityList"
	_browser.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_browser.size_flags_stretch_ratio = 1.38
	_browser.add_theme_constant_override("separation", 7)
	_panes.add_child(_browser)
	var scroll := UI.scroll("TacticsRules")
	_rules_scroll = scroll
	_browser.add_child(scroll)
	_rows = VBoxContainer.new()
	_rows.name = "RuleSummaries"
	_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_rows.add_theme_constant_override("separation", 1)
	scroll.add_child(_rows)
	var list_footer := HBoxContainer.new()
	_browser.add_child(list_footer)
	_add = Style.button("＋ Add rule")
	_add.pressed.connect(_add_rule)
	list_footer.add_child(_add)
	_hint = Style.label("First usable rule wins.\nTop priority first.", 12, true)
	_hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	list_footer.add_child(_hint)
	_inspector = PanelContainer.new()
	_inspector.name = "TacticsInspector"
	_inspector.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_inspector.size_flags_stretch_ratio = 1.0
	_inspector.add_theme_stylebox_override("panel", Style.box(Style.SURFACE, Style.BRASS, 10, 0))
	_panes.add_child(_inspector)
	_editor = VBoxContainer.new()
	_editor.name = "SharedRuleEditor"
	_editor.add_theme_constant_override("separation", 6)
	_inspector.add_child(_editor)
	add_child(Style.line())
	var footer := HBoxContainer.new()
	footer.name = "TacticsFooter"
	footer.add_theme_constant_override("separation", 10)
	add_child(footer)
	_count = Style.label("0 / %d rules" % Protocol.MAX_RULES)
	_count.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(_count)
	_more = MenuButton.new()
	_more.name = "TacticsMore"
	_more.text = "More ▾"
	_more.flat = false
	_more.custom_minimum_size = Vector2(85, 30)
	_more.get_popup().add_item("Refresh · discard changes", REFRESH)
	_more.get_popup().add_item("Restore preset", RESTORE)
	_more.get_popup().id_pressed.connect(_more_action)
	footer.add_child(_more)
	_save = Style.button("Save", true)
	_save.name = "SaveTactics"
	_save.custom_minimum_size.x = 88
	_save.pressed.connect(func() -> void:
		if _save.disabled: return
		_saving = true
		_send({"op":"save", "rules":_rules.duplicate(true)}))
	footer.add_child(_save)
	_switch_dialog = ConfirmationDialog.new()
	_switch_dialog.title = "Unsaved tactics"
	_switch_dialog.ok_button_text = "Save & switch"
	_switch_dialog.add_button("Discard & switch", false, "discard")
	_switch_dialog.confirmed.connect(_save_and_switch)
	_switch_dialog.custom_action.connect(func(action: StringName) -> void:
		if action == &"discard": _discard_and_switch())
	_switch_dialog.canceled.connect(func() -> void: _switch_target.clear())
	add_child(_switch_dialog)
	AppState.state_changed.connect(_on_state)
	AppState.combat_tactics_received.connect(set_state)
	_render()
	set_state(AppState.combat_tactics)

func refresh() -> void:
	_send({"op":"get"})

func _send(data: Dictionary) -> void:
	_request.call(Protocol.request_payload(data, _state))

func _choose_subject(index: int) -> void:
	var request := {"op":"get", "subject":str(_subjects.get_item_metadata(index))}
	if _dirty:
		_offer_switch(request, _subjects.get_item_text(index))
		_select(_subjects, str(_state.get("subject", "self")))
		return
	_send(request)

func _choose_profile(index: int) -> void:
	_sync_profiles()
	if _state.is_empty() or index == int(_state.plan.selected): return
	if _dirty:
		_offer_switch({"op":"select", "selected":index}, str(_state.plan.profiles[index].name))
		return
	_notice("Loading %s…" % _state.plan.profiles[index].name)
	_send({"op":"select", "selected":index})

func _offer_switch(request: Dictionary, destination: String) -> void:
	_switch_target = request.duplicate(true)
	_switch_dialog.dialog_text = "Save changes to %s before switching to %s?" % [_state.plan.profiles[int(_state.plan.selected)].name, destination]
	_switch_dialog.get_ok_button().disabled = _conflicted
	_switch_dialog.popup_centered(Vector2i(460, 140))

func _save_and_switch() -> void:
	if _switch_target.is_empty() or _conflicted: return
	_after_ack_switch = _switch_target.duplicate(true)
	_switch_target.clear()
	_saving = true
	_send({"op":"save", "rules":_rules.duplicate(true)})

func _discard_and_switch() -> void:
	if _switch_target.is_empty(): return
	_after_ack_switch = _switch_target.duplicate(true)
	_switch_target.clear()
	_switch_dialog.hide()
	_saving = true
	# Refresh first, so a conflict can still be discarded using the latest
	# authoritative revision. Keep the draft if that request fails.
	_send({"op":"get"})

func _sync_profiles() -> void:
	for index: int in _profile_buttons.size():
		var button := _profile_buttons[index]
		button.disabled = _state.is_empty()
		button.set_pressed_no_signal(not _state.is_empty() and index == int(_state.plan.selected))

func _more_action(id: int) -> void:
	if _state.is_empty(): return
	if id == REFRESH:
		# Keep the draft until its replacement arrives (including a failed request).
		_saving = true
		_send({"op":"get"})
	elif id == RESTORE:
		_saving = true
		_send({"op":"reset"})

func _on_state(path: StringName) -> void:
	if path == &"connection" and AppState.connection_state == "disconnected":
		_state.clear(); _rules.clear(); _dirty = false; _saving = false; _conflicted = false
		_switch_target.clear(); _after_ack_switch.clear(); _switch_dialog.hide()
		_selected = -1
		_subjects.clear()
		_render()
		_status.text = "Disconnected"
		_notice("Sign in to configure tactics.")
	# Runtime ticks must not replace controls, move focus, or acknowledge Save/
	# Refresh. Only a complete editor response replaces the authoritative plan.
	if path == &"combat_tactics" and not _state.is_empty():
		var value: Dictionary = AppState.combat_tactics
		if value.get("subject") == _state.subject and value.get("context") == _state.context:
			_sync_runtime(value)

func set_state(value: Dictionary) -> void:
	if not is_node_ready() or value.is_empty(): return
	var same: bool = not _state.is_empty() and value.subject == _state.subject and value.context == _state.context
	var revision_changed: bool = same and value.plan.revision != _state.plan.revision
	_sync_runtime(value)
	if same and _dirty and not _saving:
		if revision_changed:
			_conflicted = true
			_save.disabled = true
			_notice("Changed elsewhere. Refresh before saving.")
		return
	if _saving and not str(value.notice).is_empty():
		_saving = false
		_after_ack_switch.clear()
		_notice(str(value.notice))
		return
	var preserve_selection := same and int(value.plan.selected) == int(_state.plan.selected)
	_state = value.duplicate(true)
	_rules = _state.plan.profiles[int(_state.plan.selected)].rules.duplicate(true)
	_selected = clampi(_selected, 0, _rules.size() - 1) if preserve_selection and not _rules.is_empty() else 0 if not _rules.is_empty() else -1
	_dirty = false
	_saving = false
	_conflicted = false
	_subjects.clear()
	for subject: Dictionary in value.subjects:
		_subjects.add_item(str(subject.name))
		_subjects.set_item_metadata(_subjects.item_count - 1, str(subject.id))
	_select(_subjects, str(value.subject))
	_subjects.tooltip_text = _subjects.get_item_text(_subjects.selected)
	for index: int in _profile_buttons.size(): _profile_buttons[index].text = str(value.plan.profiles[index].name)
	_notice(str(value.notice))
	_render()
	if not _after_ack_switch.is_empty():
		var request := _after_ack_switch.duplicate(true)
		_after_ack_switch.clear()
		_send(request)

func _sync_runtime(value: Dictionary) -> void:
	var own: bool = value.subject == "self"
	_run.visible = own
	_pause.visible = own
	_run.disabled = bool(value.active)
	_pause.disabled = not bool(value.active)
	_status.text = "Running" if bool(value.active) else "Paused"
	_status.tooltip_text = str(value.status)
	_status.add_theme_stylebox_override("normal", Style.box(Style.MOSS if bool(value.active) else Color("423016"), Style.BRASS, 4))
	_help.text = "Attack and Charge keep tactics running." if own and not bool(value.active) else str(value.status)

func _notice(text: String) -> void:
	_message.text = text
	_message.tooltip_text = text
	_message.visible = not text.is_empty()

func _select(picker: OptionButton, key: String) -> void:
	for index: int in picker.item_count:
		if str(picker.get_item_metadata(index)) == key:
			picker.select(index)
			return
	# A removed/unknown action must never look like a different saved action.
	if not key.is_empty():
		picker.add_item("Unavailable: " + key)
		picker.set_item_metadata(picker.item_count - 1, key)
		picker.select(picker.item_count - 1)

func _changed() -> void:
	_dirty = true
	_save.disabled = _conflicted
	_notice("Changed elsewhere. Refresh before saving." if _conflicted else "Unsaved changes")

func _picker(keys: Array, labels: Array, selected: String, callback: Callable) -> OptionButton:
	var picker := OptionButton.new()
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.fit_to_longest_item = false
	picker.clip_text = true
	picker.custom_minimum_size = Vector2(100, 28)
	for index: int in keys.size():
		picker.add_item(str(labels[index]))
		picker.set_item_metadata(index, str(keys[index]))
	_select(picker, selected)
	picker.item_selected.connect(func(index: int) -> void: callback.call(str(picker.get_item_metadata(index))))
	return picker

func _render() -> void:
	_render_rows()
	_render_editor()
	_sync_profiles()
	_save.disabled = not _dirty or _conflicted or _state.is_empty()
	var limit := int(_state.get("max_rules", Protocol.MAX_RULES))
	_add.disabled = _state.is_empty() or _rules.size() >= limit
	_add.text = "＋ Add rule (%d/%d)" % [_rules.size(), limit] if _rules.size() >= limit else "＋ Add rule"
	_count.text = "%d / %d rules" % [_rules.size(), limit]
	_more.disabled = _state.is_empty()
	if _state.is_empty():
		_run.hide(); _pause.hide()

func _render_rows() -> void:
	UI.clear(_rows)
	for index: int in _rules.size():
		var entry: Dictionary = _rules[index]
		var row := RuleRow.new()
		row.name = "Rule%d" % (index + 1)
		row.configure(index, get_instance_id(), _summary(entry), bool(entry.enabled), _glyph(entry), index == _selected, _short)
		var warnings := _rule_warnings(index)
		if not warnings.is_empty():
			row.summary_label.text = "⚠ " + row.summary_label.text
			row.summary_label.add_theme_color_override("font_color", Style.GOLD)
			row.tooltip_text = "\n".join(warnings) + "\n\n" + row.tooltip_text
		row.pressed.connect(_select_rule.bind(index))
		row.enabled_changed.connect(func(on: bool) -> void:
			entry.enabled = on
			_changed()
			_render_rows.call_deferred())
		row.reorder_requested.connect(_move_rule)
		_rows.add_child(row)
	if _rules.is_empty():
		var empty := Style.label("No rules yet.\nAdd a rule to get started.", 14, true)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_rows.add_child(empty)
	_follow_selection.call_deferred()

## Compare execution-relevant fields; unused threshold/status defaults do
## not make two Always rules different. Warnings never rewrite a saved plan.
func _rule_warnings(index: int) -> PackedStringArray:
	var warnings := PackedStringArray()
	var entry: Dictionary = _rules[index]
	if not bool(entry.enabled): return warnings
	if entry.action in ["flee", "technique:step_back"] and str(entry.condition) == "always" \
			and entry.get("and_conditions", []).is_empty():
		warnings.append("This rule retreats whenever available. Add a condition to limit automatic fleeing.")
	for earlier: int in index:
		var other: Dictionary = _rules[earlier]
		if not bool(other.enabled) or entry.target != other.target: continue
		if other.get("combat", "any") != "any" and other.get("combat", "any") != entry.get("combat", "any"): continue
		var same_action: bool = entry.action == other.action and int(entry.get("power", 1)) == int(other.get("power", 1))
		if same_action and (_condition_key(entry) == _condition_key(other) \
				or (other.condition == "always" and other.get("and_conditions", []).is_empty())):
			warnings.append("Rule %d already covers this action when usable. Remove the duplicate or change its conditions." % (earlier + 1))
			break
		if entry.target == "self" and entry.condition == "health_below" and other.condition == "health_below" \
				and int(other.value) > int(entry.value) and entry.get("and_conditions", []).is_empty() \
				and other.get("and_conditions", []).is_empty():
			warnings.append("Rule %d also matches below %d%% health and runs first when usable. Put emergency actions above it." % [earlier + 1, int(entry.value)])
	return warnings

func _condition_key(entry: Dictionary) -> String:
	var keys := PackedStringArray()
	for check: Dictionary in _conditions(entry):
		var condition := str(check.condition)
		var value := ""
		if condition in ["health_below", "ether_below", "action_points_below", "action_points_at_least", "opponents_below", "opponents_at_least"]:
			value = str(check.value)
		elif condition in ["has_status", "missing_status", "missing_buff", "missing_debuff"]: value = str(check.status)
		keys.append(condition + ":" + value)
	keys.sort()
	return "|".join(keys)

func _follow_selection() -> void:
	if _follow_pending: return
	_follow_pending = true
	# The new rows and a resized inspector need their final container layout
	# before the scroll position can be calculated reliably.
	await get_tree().process_frame
	await get_tree().process_frame
	_follow_pending = false
	if _selected >= 0 and _selected < _rows.get_child_count():
		_rules_scroll.ensure_control_visible(_rows.get_child(_selected))

func _select_rule(index: int) -> void:
	if index < 0 or index >= _rules.size(): return
	_selected = index
	_condition_focus = 0
	for item: Node in _rows.get_children():
		if item is Button: item.set_pressed_no_signal(item.get_index() == index)
	_render_editor()
	_follow_selection.call_deferred()

func _field(title: String, control: Control) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var label := Style.label(title, 13)
	label.custom_minimum_size.x = 66
	row.add_child(label)
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(control)
	_editor.add_child(row)

func _spin(value: int, maximum: int) -> SpinBox:
	var result := SpinBox.new()
	result.min_value = 1; result.max_value = maximum
	result.value = value
	result.custom_minimum_size.y = 28
	return result

func _render_editor() -> void:
	UI.clear(_editor)
	var heading := HBoxContainer.new()
	_editor.add_child(heading)
	_editor_title = Style.label("Edit Rule %d" % (_selected + 1) if _selected >= 0 else "Rule editor", 19)
	_editor_title.add_theme_font_override("font", Style.heading_font())
	_editor_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(_editor_title)
	_editor.add_child(Style.line())
	if _selected < 0 or _selected >= _rules.size():
		var empty := Style.label("Select a rule to edit its target, condition and action.", 14, true)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_editor.add_child(empty)
		return
	var entry: Dictionary = _rules[_selected]
	_combat_picker = _picker(COMBAT_STATES, COMBAT_LABELS, str(entry.get("combat", "any")), func(key: String) -> void:
		entry.combat = key; _changed(); _render_rows())
	_combat_picker.custom_minimum_size.x = 128
	_combat_picker.size_flags_horizontal = Control.SIZE_SHRINK_END
	_combat_picker.tooltip_text = "Only run this rule when this character is in combat, out of combat, or either."
	heading.add_child(_combat_picker)
	_target_picker = _picker(TARGETS, TARGET_LABELS, str(entry.target), func(key: String) -> void:
		entry.target = key; _changed(); _render_rows())
	_field("Target", _target_picker)
	_action_picker = ActionPicker.new()
	_action_picker.configure(_state.actions, str(entry.action))
	_action_picker.action_selected.connect(func(key: String) -> void:
		entry.action = key
		for action: Dictionary in _state.actions:
			if action.id != key: continue
			if key == "technique:intercept": entry.target = "ally"
			elif action.get("scope", "") == "self": entry.target = "self"
			elif action.get("hostile", false) or key in ["attack", "guard"]:
				if entry.target in ["self", "ally"]: entry.target = "current_target"
			elif entry.target not in ["self", "ally"]: entry.target = "ally"
		_changed(); _render_rows(); _render_editor())
	_field("Action", _action_picker)
	if str(entry.action).begins_with("spell:"):
		_power_picker = _spin(int(entry.power), 10)
		_power_picker.value_changed.connect(func(amount: float) -> void: entry.power = int(amount); _changed())
		_field("Power", _power_picker)
	_render_conditions(entry)
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 6)
	_editor.add_child(tools)
	_up = Style.button("↑ Up")
	_up.disabled = _selected == 0
	_up.pressed.connect(func() -> void: _move_rule(_selected, _selected - 1))
	tools.add_child(_up)
	_down = Style.button("↓ Down")
	_down.disabled = _selected == _rules.size() - 1
	_down.pressed.connect(func() -> void: _move_rule(_selected, _selected + 1))
	tools.add_child(_down)
	var gap := Control.new()
	gap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tools.add_child(gap)
	_delete = Style.button("Delete")
	_delete.add_theme_color_override("font_color", Color("ddba91"))
	_delete.pressed.connect(_delete_rule)
	tools.add_child(_delete)
	_apply_density()

func _conditions(entry: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = [entry]
	for check: Dictionary in entry.get("and_conditions", []): result.append(check)
	return result

func _add_condition() -> void:
	if _selected < 0 or _selected >= _rules.size(): return
	var entry: Dictionary = _rules[_selected]
	if _conditions(entry).size() >= int(_state.get("max_conditions", 1)): return
	if not entry.has("and_conditions"): entry.and_conditions = []
	entry.and_conditions.append({"condition":"always", "value":50, "status":"poison"})
	_condition_focus = entry.and_conditions.size()
	_changed(); _render_rows(); _render_editor()

func _remove_condition(index: int) -> void:
	if _selected < 0 or _selected >= _rules.size(): return
	var entry: Dictionary = _rules[_selected]
	var checks := _conditions(entry)
	if checks.size() <= 1 or index < 0 or index >= checks.size(): return
	if index == 0:
		var first: Dictionary = entry.and_conditions.pop_front()
		for key: String in ["condition", "value", "status"]: entry[key] = first[key]
	else: entry.and_conditions.remove_at(index - 1)
	if entry.and_conditions.is_empty(): entry.erase("and_conditions")
	_condition_focus = maxi(0, index - 1)
	_changed(); _render_rows(); _render_editor()

func _render_conditions(entry: Dictionary) -> void:
	_condition_pickers.clear(); _condition_inputs.clear(); _condition_remove_buttons.clear()
	var checks := _conditions(entry)
	var limit := int(_state.get("max_conditions", 1))
	var heading := HBoxContainer.new()
	var label := Style.label("All conditions (%d/%d)" % [checks.size(), limit], 13)
	label.tooltip_text = "All conditions must pass before this action runs."
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(label)
	_add_if = Style.button("＋ If")
	_add_if.tooltip_text = "Add another condition. All conditions must match (AND)."
	_add_if.disabled = checks.size() >= limit
	_add_if.pressed.connect(_add_condition)
	heading.add_child(_add_if)
	_editor.add_child(heading)
	_condition_scroll = UI.scroll("ActionConditions")
	_condition_scroll.follow_focus = true
	_condition_scroll.custom_minimum_size.y = 32
	_editor.add_child(_condition_scroll)
	_condition_list = VBoxContainer.new()
	_condition_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_condition_list.add_theme_constant_override("separation", 4)
	_condition_scroll.add_child(_condition_list)
	for index: int in checks.size():
		var check: Dictionary = checks[index]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 3)
		row.add_child(Style.label("IF" if index == 0 else "AND", 11, true))
		var picker := _picker(CONDITIONS, CONDITION_SHORT_LABELS, str(check.condition), func(key: String) -> void:
			if key in OPPONENT_CONDITIONS and check.condition not in OPPONENT_CONDITIONS: check.value = 2
			check.condition = key
			check.value = clampi(int(check.value), 1, Protocol.value_maximum(key))
			if key == "focused_on_ally" and entry.target in ["self", "ally"]: entry.target = "current_target"
			if key in ["missing_buff", "missing_debuff"]:
				var ids: Array = _status_choices(key).map(func(status: Dictionary): return str(status.id))
				if check.status not in ids and not ids.is_empty(): check.status = ids[0]
			_condition_focus = index
			_changed(); _render_rows(); _render_editor())
		var title_index := CONDITIONS.find(str(check.condition))
		picker.custom_minimum_size.x = 80
		picker.tooltip_text = CONDITION_LABELS[title_index] if title_index >= 0 else str(check.condition)
		if check.condition in Protocol.AP_CONDITIONS: picker.tooltip_text += "\nChecks this character's current action points."
		if check.condition in OPPONENT_CONDITIONS: picker.tooltip_text += "\nCounts distinct engaged party opponents within tactics range."
		if check.condition == "focused_on_ally": picker.tooltip_text += "\nThe selected enemy is attacking another party member."
		row.add_child(picker)
		_condition_pickers.append(picker)
		if index == 0: _condition_picker = picker
		var input: Control = null
		if check.condition in ["health_below", "ether_below"] or check.condition in Protocol.AP_CONDITIONS or check.condition in OPPONENT_CONDITIONS:
			var value := _spin(int(check.value), Protocol.value_maximum(str(check.condition)))
			value.custom_minimum_size.x = 84
			value.suffix = " AP" if check.condition in Protocol.AP_CONDITIONS else "" if check.condition in OPPONENT_CONDITIONS else "%"
			value.value_changed.connect(func(amount: float) -> void: check.value = int(amount); _changed(); _render_rows())
			input = value
			if index == 0: _value_picker = value
		elif check.condition in ["has_status", "missing_status", "missing_buff", "missing_debuff"]:
			var choices := _status_choices(str(check.condition))
			var ids: Array = choices.map(func(status: Dictionary): return str(status.id))
			var labels: Array = choices.map(func(status: Dictionary): return str(status.name))
			var status := _picker(ids, labels, str(check.status), func(key: String) -> void: check.status = key; _changed(); _render_rows())
			status.size_flags_horizontal = Control.SIZE_SHRINK_END
			status.custom_minimum_size.x = 84
			input = status
			if index == 0: _status_picker = status
		if input != null: row.add_child(input)
		_condition_inputs.append(input)
		var remove := Style.button("×")
		remove.custom_minimum_size.x = 22
		remove.tooltip_text = "Remove this condition"
		remove.disabled = checks.size() == 1
		remove.pressed.connect(_remove_condition.bind(index))
		row.add_child(remove)
		_condition_remove_buttons.append(remove)
		_condition_list.add_child(row)
	_reveal_condition.call_deferred()

func _reveal_condition() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	if is_instance_valid(_condition_scroll) and _condition_focus < _condition_list.get_child_count():
		_condition_scroll.ensure_control_visible(_condition_list.get_child(_condition_focus))

func _action_name(entry: Dictionary) -> String:
	for action: Dictionary in _state.get("actions", []):
		if action.id == entry.action: return str(action.name)
	return "Unavailable: " + str(entry.action)

func _status_choices(condition: String) -> Array:
	var choices: Array = _state.get("statuses", [])
	if choices.is_empty():
		for index: int in STATUSES.size():
			choices.append({"id":STATUSES[index], "name":STATUS_LABELS[index], "kind":"debuff" if STATUSES[index] == "poison" else "buff"})
	if condition == "missing_buff": return choices.filter(func(status: Dictionary): return status.kind == "buff")
	if condition == "missing_debuff": return choices.filter(func(status: Dictionary): return status.kind == "debuff")
	return choices

func _condition_summary(entry: Dictionary) -> String:
	var condition := ""
	match str(entry.condition):
		"health_below": condition = "Health < %d%%" % int(entry.value)
		"ether_below": condition = "Ether < %d%%" % int(entry.value)
		"action_points_below": condition = "AP < %d" % int(entry.value)
		"action_points_at_least": condition = "AP ≥ %d" % int(entry.value)
		"opponents_below": condition = "Opponents < %d" % int(entry.value)
		"opponents_at_least": condition = "Opponents ≥ %d" % int(entry.value)
		"focused_on_ally": condition = "Focused on another ally"
		"has_status", "missing_status", "missing_buff", "missing_debuff":
			condition = str(entry.status).replace("_", " ").capitalize()
			for status: Dictionary in _status_choices("has_status"):
				if status.id == entry.status: condition = str(status.name)
			if entry.condition != "has_status": condition += " missing"
	return condition

func _summary(entry: Dictionary) -> String:
	var target_index := TARGETS.find(str(entry.target))
	var target: String = TARGET_LABELS[target_index] if target_index >= 0 else str(entry.target)
	if entry.target == "ally": target = "Ally"
	elif entry.target == "nearest_enemy": target = "Nearest engaged foe"
	var descriptions: PackedStringArray = []
	for check: Dictionary in _conditions(entry):
		var description := _condition_summary(check)
		if not description.is_empty(): descriptions.append(description)
	var condition := " AND ".join(descriptions)
	var combat := str(entry.get("combat", "any"))
	var prefix := ("In combat · " if combat == "in_combat" else "Out of combat · ") if combat != "any" else ""
	return prefix + target + (" · " + condition if not condition.is_empty() else "") + " → " + _action_name(entry)

func _glyph(entry: Dictionary) -> String:
	var action := _action_name(entry).to_lower()
	if "heal" in action: return "heal"
	if "shield" in action or "ward" in action: return "shield"
	if "dispel" in action: return "dispel"
	return "target" if entry.target == "nearest_enemy" else "attack"

func _move_rule(source: int, destination: int) -> void:
	if source < 0 or destination < 0 or source >= _rules.size() or destination >= _rules.size() or source == destination: return
	var entry: Dictionary = _rules.pop_at(source)
	_rules.insert(destination, entry)
	_selected = destination
	_changed(); _render()

func _delete_rule() -> void:
	if _selected < 0 or _selected >= _rules.size(): return
	_rules.remove_at(_selected)
	_selected = mini(_selected, _rules.size() - 1)
	_changed(); _render()

func _add_rule() -> void:
	if _state.is_empty() or _rules.size() >= int(_state.get("max_rules", Protocol.MAX_RULES)): return
	_rules.append({"enabled":true, "target":"current_target", "condition":"always", "value":50,
		"status":"poison", "action":"attack", "power":1, "combat":"any"})
	_selected = _rules.size() - 1
	_changed(); _render()

func set_short(short: bool) -> void:
	if short == _short: return
	_short = short
	theme = Style.theme(short)
	add_theme_constant_override("separation", 3 if short else 7)
	_editor.add_theme_constant_override("separation", 3 if short else 6)
	_hint.text = "First usable rule wins." if short else "First usable rule wins.\nTop priority first."
	_render_rows()
	_apply_density()

func _apply_density() -> void:
	for control: Node in find_children("*", "Control", true, false):
		if control is Button and control.get_parent() != _rows:
			control.custom_minimum_size.y = 26 if _short else 30
		elif control is SpinBox:
			control.custom_minimum_size.y = 26 if _short else 28
