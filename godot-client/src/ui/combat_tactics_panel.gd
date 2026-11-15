extends VBoxContainer
## Ordered instructions for the player or one admitted party companion.
const UI := preload("res://src/ui/action_book_ui.gd")
const TARGETS := ["self", "ally", "leader_target", "current_target", "party_attacker", "lowest_enemy", "nearest_enemy"]
const TARGET_LABELS := ["Self", "Ally: lowest health", "Leader's opponent", "Current opponent", "Party's opponents", "Enemy: lowest health", "Enemy: nearest"]
const CONDITIONS := ["always", "health_below", "ether_below", "has_status", "missing_status"]
const CONDITION_LABELS := ["Always", "Health below %", "Ether below %", "Has status", "Missing status"]
const STATUSES := ["poison", "shield", "regeneration", "magic_protection", "magic_immunity", "haste", "accuracy"]
var _state: Dictionary = {}
var _rules: Array = []
var _dirty := false
var _saving := false
var _subjects: OptionButton
var _profiles: OptionButton
var _run: Button
var _status: Label
var _rows: VBoxContainer
var _save: Button
var _add: Button
var _request: Callable

func _ready() -> void:
	name = "CombatTactics"
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_request = func(data: Dictionary) -> void: Network.send_chat("#tactics " + JSON.stringify(data))
	var top := HBoxContainer.new()
	add_child(top)
	_subjects = OptionButton.new()
	_subjects.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_subjects.item_selected.connect(func(index: int) -> void:
		if _dirty:
			_status.text = "Save or Refresh your changes before switching."
			_select(_subjects, str(_state.get("subject", "self")))
			return
		_send({"op":"get", "subject":str(_subjects.get_item_metadata(index))}))
	top.add_child(_subjects)
	_profiles = OptionButton.new()
	_profiles.item_selected.connect(func(index: int) -> void:
		if _dirty:
			_status.text = "Save or Refresh your changes before switching."
			_profiles.select(int(_state.plan.selected))
			return
		_send({"op":"select", "selected":index}))
	top.add_child(_profiles)
	_run = UI.button("Start my tactics")
	_run.pressed.connect(func() -> void: _send({"op":"run", "active":not bool(_state.get("active", false))}))
	top.add_child(_run)
	var help := UI.label("Read from top to bottom. The first usable action wins. Manual movement or combat commands pause your own tactics; Resume starts them again.", 12, true)
	add_child(help)
	_status = UI.label("Refresh to load tactics from the server.", 12, true)
	add_child(_status)
	var scroll := UI.scroll("TacticsRules")
	add_child(scroll)
	_rows = VBoxContainer.new()
	_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_rows.add_theme_constant_override("separation", 8)
	scroll.add_child(_rows)
	var footer := HBoxContainer.new()
	add_child(footer)
	_add = UI.button("Add rule")
	_add.pressed.connect(_add_rule)
	footer.add_child(_add)
	_save = UI.button("Save tactics")
	_save.pressed.connect(func() -> void:
		_saving = true
		_send({"op":"save", "rules":_rules.duplicate(true)}))
	footer.add_child(_save)
	var refresh := UI.button("Refresh")
	refresh.pressed.connect(func() -> void:
		_dirty = false
		_send({"op":"get"}))
	footer.add_child(refresh)
	var reset := UI.button("Restore preset")
	reset.pressed.connect(func() -> void:
		_saving = true
		_send({"op":"reset"}))
	footer.add_child(reset)
	AppState.state_changed.connect(_on_state)
	set_state(AppState.combat_tactics)

func refresh() -> void:
	_send({"op":"get"})

func _send(data: Dictionary) -> void:
	if not _state.is_empty():
		data.merge({"subject":_state.subject, "revision":_state.plan.revision, "context":_state.context}, false)
	_request.call(data)

func _on_state(path: StringName) -> void:
	if path == &"connection" and AppState.connection_state == "disconnected":
		_state.clear(); _rules.clear(); _dirty = false; _saving = false
		UI.clear(_rows); _subjects.clear(); _profiles.clear()
		_save.disabled = true; _add.disabled = true; _run.hide()
		_status.text = "Sign in to configure tactics."
	if path == &"combat_tactics": set_state(AppState.combat_tactics)

func set_state(value: Dictionary) -> void:
	if not is_node_ready() or value.is_empty(): return
	var same: bool = not _state.is_empty() and value.subject == _state.subject and value.context == _state.context
	var revision_changed: bool = same and value.plan.revision != _state.plan.revision
	_status.text = str(value.notice) if not str(value.notice).is_empty() else str(value.status)
	_run.visible = value.subject == "self"
	_run.text = "Pause my tactics" if value.active else "Start / Resume my tactics"
	if same and _dirty and not _saving:
		if revision_changed:
			_status.text = "Tactics changed elsewhere. Refresh to load the current plan."
			_save.disabled = true
		return
	if _saving and not str(value.notice).is_empty():
		_saving = false
		return
	_state = value.duplicate(true)
	_rules = _state.plan.profiles[int(_state.plan.selected)].rules.duplicate(true)
	_dirty = false
	_saving = false
	_subjects.clear()
	for subject: Dictionary in value.subjects:
		_subjects.add_item(str(subject.name))
		_subjects.set_item_metadata(_subjects.item_count - 1, str(subject.id))
	_select(_subjects, str(value.subject))
	_profiles.clear()
	for profile: Dictionary in value.plan.profiles: _profiles.add_item(str(profile.name))
	_profiles.select(int(value.plan.selected))
	_render()

func _select(picker: OptionButton, key: String) -> void:
	for index: int in picker.item_count:
		if str(picker.get_item_metadata(index)) == key:
			picker.select(index)
			return

func _changed() -> void:
	_dirty = true
	_save.disabled = false
	_status.text = "Unsaved changes"

func _picker(keys: Array, labels: Array, selected: String, callback: Callable) -> OptionButton:
	var picker := OptionButton.new()
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.clip_text = true
	for index: int in keys.size():
		picker.add_item(str(labels[index]))
		picker.set_item_metadata(index, str(keys[index]))
	_select(picker, selected)
	picker.item_selected.connect(func(index: int) -> void: callback.call(str(picker.get_item_metadata(index))))
	return picker

func _render() -> void:
	UI.clear(_rows)
	_save.disabled = not _dirty
	_add.disabled = _rules.size() >= int(_state.get("max_rules", 6))
	for index: int in _rules.size():
		var entry: Dictionary = _rules[index]
		var card := PanelContainer.new()
		card.add_theme_stylebox_override("panel", UI.box(Color("17120d"), Color("80623b"), 6))
		_rows.add_child(card)
		var column := VBoxContainer.new()
		card.add_child(column)
		var first := HBoxContainer.new()
		column.add_child(first)
		var enabled := CheckBox.new()
		enabled.text = str(index + 1)
		enabled.button_pressed = bool(entry.enabled)
		enabled.toggled.connect(func(on: bool) -> void: entry.enabled = on; _changed())
		first.add_child(enabled)
		first.add_child(_picker(TARGETS, TARGET_LABELS, str(entry.target), func(key: String) -> void: entry.target = key; _changed()))
		first.add_child(_picker(CONDITIONS, CONDITION_LABELS, str(entry.condition), func(key: String) -> void: entry.condition = key; _changed(); _render()))
		if entry.condition in ["health_below", "ether_below"]:
			var value := SpinBox.new()
			value.min_value = 1; value.max_value = 100; value.value = int(entry.value)
			value.custom_minimum_size.x = 78
			value.value_changed.connect(func(amount: float) -> void: entry.value = int(amount); _changed())
			first.add_child(value)
		elif entry.condition in ["has_status", "missing_status"]:
			first.add_child(_picker(STATUSES, STATUSES, str(entry.status), func(key: String) -> void: entry.status = key; _changed()))
		var second := HBoxContainer.new()
		column.add_child(second)
		second.add_child(UI.label("Then", 12))
		var ids: Array = []; var labels: Array = []
		for action: Dictionary in _state.actions:
			ids.append(str(action.id)); labels.append(str(action.name))
		second.add_child(_picker(ids, labels, str(entry.action), func(key: String) -> void:
			entry.action = key
			for action: Dictionary in _state.actions:
				if action.id != key: continue
				if action.get("scope", "") == "self": entry.target = "self"
				elif action.get("hostile", false) or key in ["attack", "guard"]: entry.target = "current_target"
				else: entry.target = "ally"
			_changed(); _render()))
		if str(entry.action).begins_with("spell:"):
			second.add_child(UI.label("Power", 12))
			var power := SpinBox.new()
			power.min_value = 1; power.max_value = 10; power.value = int(entry.power)
			power.value_changed.connect(func(amount: float) -> void: entry.power = int(amount); _changed())
			second.add_child(power)
		for direction: int in [-1, 1]:
			var move := UI.button("Up" if direction == -1 else "Down")
			move.disabled = index + direction < 0 or index + direction >= _rules.size()
			move.pressed.connect(func() -> void:
				var other: Variant = _rules[index + direction]
				_rules[index + direction] = _rules[index]; _rules[index] = other
				_changed(); _render())
			second.add_child(move)
		var remove := UI.button("Remove")
		remove.pressed.connect(func() -> void: _rules.remove_at(index); _changed(); _render())
		second.add_child(remove)

func _add_rule() -> void:
	if _rules.size() >= int(_state.get("max_rules", 6)): return
	_rules.append({"enabled":true, "target":"current_target", "condition":"always", "value":50,
		"status":"poison", "action":"attack", "power":1})
	_changed()
	_render()
