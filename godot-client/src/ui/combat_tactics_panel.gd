extends VBoxContainer
## Ordered drafts stay local until Save. One shared editor follows selection.
const UI := preload("res://src/ui/action_book_ui.gd")
const Style := preload("res://src/ui/combat_tactics_style.gd")
const RuleRow := preload("res://src/ui/combat_tactics_rule_row.gd")
const TARGETS := ["self", "ally", "leader_target", "current_target", "party_attacker", "lowest_enemy", "nearest_enemy"]
const TARGET_LABELS := ["Self", "Ally: lowest health", "Leader's opponent", "Current opponent", "Party's opponents", "Enemy: lowest health", "Enemy: nearest"]
const CONDITIONS := ["always", "health_below", "ether_below", "has_status", "missing_status"]
const CONDITION_LABELS := ["Always", "Health below %", "Ether below %", "Has status", "Missing status"]
const STATUSES := ["poison", "shield", "regeneration", "magic_protection", "magic_immunity", "haste", "accuracy"]
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
var _action_picker: OptionButton
var _value_picker: SpinBox
var _status_picker: OptionButton
var _power_picker: SpinBox
var _up: Button
var _down: Button
var _delete: Button
var _request: Callable
var _short := false

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
	_run.tooltip_text = "Start or resume my combat tactics for this session."
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
	_help = Style.label("Manual actions pause tactics.", 12, true)
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
	_count = Style.label("0 / 6 rules")
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
	AppState.state_changed.connect(_on_state)
	AppState.combat_tactics_received.connect(set_state)
	_render()
	set_state(AppState.combat_tactics)

func refresh() -> void:
	_send({"op":"get"})

func _send(data: Dictionary) -> void:
	if not _state.is_empty():
		data.merge({"subject":_state.subject, "revision":_state.plan.revision, "context":_state.context}, false)
	_request.call(data)

func _choose_subject(index: int) -> void:
	if _dirty:
		_notice("Save or Refresh before switching.")
		_select(_subjects, str(_state.get("subject", "self")))
		return
	_send({"op":"get", "subject":str(_subjects.get_item_metadata(index))})

func _choose_profile(index: int) -> void:
	_sync_profiles()
	if _dirty:
		_notice("Save or Refresh before switching.")
		return
	_send({"op":"select", "selected":index})

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

func _sync_runtime(value: Dictionary) -> void:
	var own: bool = value.subject == "self"
	_run.visible = own
	_pause.visible = own
	_run.disabled = bool(value.active)
	_pause.disabled = not bool(value.active)
	_status.text = "Running" if bool(value.active) else "Paused"
	_status.tooltip_text = str(value.status)
	_status.add_theme_stylebox_override("normal", Style.box(Style.MOSS if bool(value.active) else Color("423016"), Style.BRASS, 4))
	_help.text = "Manual actions pause tactics." if own and not bool(value.active) else str(value.status)

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
	_add.disabled = _state.is_empty() or _rules.size() >= int(_state.get("max_rules", 6))
	_add.text = "＋ Add rule (6/6)" if _rules.size() >= 6 else "＋ Add rule"
	_count.text = "%d / %d rules" % [_rules.size(), int(_state.get("max_rules", 6))]
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
		row.pressed.connect(_select_rule.bind(index))
		row.enabled_changed.connect(func(on: bool) -> void:
			entry.enabled = on
			_changed()
			row.summary_label.modulate.a = 1.0 if on else 0.55)
		row.reorder_requested.connect(_move_rule)
		_rows.add_child(row)
	if _rules.is_empty():
		var empty := Style.label("No rules yet.\nAdd a rule to get started.", 14, true)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_rows.add_child(empty)

func _select_rule(index: int) -> void:
	if index < 0 or index >= _rules.size(): return
	_selected = index
	for item: Node in _rows.get_children():
		if item is Button: item.set_pressed_no_signal(item.get_index() == index)
	_render_editor()

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
	_editor_title = Style.label("Edit Rule %d" % (_selected + 1) if _selected >= 0 else "Rule editor", 19)
	_editor_title.add_theme_font_override("font", Style.heading_font())
	_editor.add_child(_editor_title)
	_editor.add_child(Style.line())
	if _selected < 0 or _selected >= _rules.size():
		var empty := Style.label("Select a rule to edit its target, condition and action.", 14, true)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_editor.add_child(empty)
		return
	var entry: Dictionary = _rules[_selected]
	_target_picker = _picker(TARGETS, TARGET_LABELS, str(entry.target), func(key: String) -> void:
		entry.target = key; _changed(); _render_rows())
	_field("Target", _target_picker)
	_condition_picker = _picker(CONDITIONS, CONDITION_LABELS, str(entry.condition), func(key: String) -> void:
		entry.condition = key; _changed(); _render_rows(); _render_editor())
	_field("Condition", _condition_picker)
	if entry.condition in ["health_below", "ether_below"]:
		_value_picker = _spin(int(entry.value), 100)
		_value_picker.suffix = "%"
		_value_picker.value_changed.connect(func(amount: float) -> void: entry.value = int(amount); _changed(); _render_rows())
		_field("Value", _value_picker)
	elif entry.condition in ["has_status", "missing_status"]:
		var labels: Array = []
		for status: String in STATUSES: labels.append(status.replace("_", " ").capitalize())
		_status_picker = _picker(STATUSES, labels, str(entry.status), func(key: String) -> void: entry.status = key; _changed(); _render_rows())
		_field("Status", _status_picker)
	var ids: Array = []; var labels: Array = []
	for action: Dictionary in _state.actions:
		ids.append(str(action.id)); labels.append(str(action.name))
	_action_picker = _picker(ids, labels, str(entry.action), func(key: String) -> void:
		entry.action = key
		for action: Dictionary in _state.actions:
			if action.id != key: continue
			if action.get("scope", "") == "self": entry.target = "self"
			elif action.get("hostile", false) or key in ["attack", "guard"]: entry.target = "current_target"
			else: entry.target = "ally"
		_changed(); _render_rows(); _render_editor())
	_field("Action", _action_picker)
	if str(entry.action).begins_with("spell:"):
		_power_picker = _spin(int(entry.power), 10)
		_power_picker.value_changed.connect(func(amount: float) -> void: entry.power = int(amount); _changed())
		_field("Power", _power_picker)
	var space := Control.new()
	space.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_editor.add_child(space)
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

func _action_name(entry: Dictionary) -> String:
	for action: Dictionary in _state.get("actions", []):
		if action.id == entry.action: return str(action.name)
	return "Unavailable: " + str(entry.action)

func _summary(entry: Dictionary) -> String:
	var target_index := TARGETS.find(str(entry.target))
	var target: String = TARGET_LABELS[target_index] if target_index >= 0 else str(entry.target)
	if entry.target == "ally": target = "Ally"
	elif entry.target == "nearest_enemy": target = "Nearest engaged foe"
	var condition := ""
	match str(entry.condition):
		"health_below": condition = "Health < %d%%" % int(entry.value)
		"ether_below": condition = "Ether < %d%%" % int(entry.value)
		"has_status": condition = "Poisoned" if entry.status == "poison" else str(entry.status).replace("_", " ").capitalize()
		"missing_status": condition = str(entry.status).replace("_", " ").capitalize() + " missing"
	return target + (" · " + condition if not condition.is_empty() else "") + " → " + _action_name(entry)

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
	if _state.is_empty() or _rules.size() >= int(_state.get("max_rules", 6)): return
	_rules.append({"enabled":true, "target":"current_target", "condition":"always", "value":50,
		"status":"poison", "action":"attack", "power":1})
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
