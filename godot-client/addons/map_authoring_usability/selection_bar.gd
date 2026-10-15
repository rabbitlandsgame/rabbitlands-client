@tool
extends HBoxContainer
## The bar under the 3D view while placed objects are selected: what is
## selected, its territory-local position, turn and size as editable fields,
## and one-click tools. The plugin applies every edit as one undo step.
##
## One object shows absolute values. Several show their centre; Turn and Size
## then act on the whole selection (turn about the centre by the degrees typed,
## scale about it by the factor typed) and reset to 0 and 1 afterwards.

signal field_edited(field: String, value: float)
signal tool_pressed(tool: String)

const FIELDS := ["x", "y", "z", "turn", "size"]

var _name: Label
var _spins := {}
var _labels := {}
var _buttons := {}
var _shown: Dictionary = {}


func _init() -> void:
	name = "MapAuthoringSelectionBar"
	add_theme_constant_override("separation", 6)
	_name = Label.new()
	_name.custom_minimum_size = Vector2(150, 0)
	_name.clip_text = true
	_name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	add_child(_name)
	for field: String in FIELDS:
		var label := Label.new()
		label.text = {"x": "X", "y": "Y", "z": "Z", "turn": "Turn", "size": "Size"}[field]
		add_child(label)
		_labels[field] = label
		var spin := SpinBox.new()
		spin.allow_greater = true
		spin.allow_lesser = true
		spin.select_all_on_focus = true
		spin.update_on_text_changed = false
		spin.custom_minimum_size = Vector2(88 if field != "size" else 70, 0)
		match field:
			"turn":
				spin.step = 0.5
				spin.suffix = "°"
				spin.min_value = -360.0
				spin.max_value = 360.0
			"size":
				spin.step = 0.01
				spin.min_value = 0.05
				spin.max_value = 20.0
				spin.allow_lesser = false
			_:
				spin.step = 0.01
				spin.suffix = "m"
				spin.min_value = -10000.0
				spin.max_value = 10000.0
		spin.value_changed.connect(_on_value_changed.bind(field))
		add_child(spin)
		_spins[field] = spin
	add_child(VSeparator.new())
	for pair: Array in [["drop", "Drop", "Drop the selection onto the ground"],
			["rotate", "Rotate 90°", "Rotate each object 90° about its own pivot"],
			["copy", "Duplicate", "Copy the selection beside itself with fresh ids (or Alt+drag it)"],
			["group", "Group", "Group the selection (Ctrl+G): clicking one member selects all"],
			["ungroup", "Ungroup", "Ungroup (Ctrl+Shift+G)"],
			["open_group", "Edit members", "Pick single members of this group until you select outside it"],
			["prefab", "Save prefab", "Save the selection as a prefab in the Map Assets palette"]]:
		var button := Button.new()
		button.text = String(pair[1])
		button.tooltip_text = String(pair[2])
		button.flat = true
		button.pressed.connect(func() -> void: tool_pressed.emit(String(pair[0])))
		add_child(button)
		_buttons[pair[0]] = button


## Shows `summary` (see selection_tools.gd) plus group state; hides when empty.
func show_summary(summary: Dictionary, grouped: bool, open_group: String) -> void:
	var count := int(summary.get("count", 0))
	visible = count > 0
	if count == 0:
		_shown = {}
		return
	_shown = summary.duplicate()
	var text := String(summary.get("name", ""))
	if not open_group.is_empty():
		text += "  (editing %s)" % open_group
	_name.text = text
	_name.tooltip_text = text
	var position: Vector3 = summary.position
	for field: String in FIELDS:
		var spin: SpinBox = _spins[field]
		if spin.get_line_edit().has_focus():
			continue
		var value := 0.0
		match field:
			"x": value = position.x
			"y": value = position.y
			"z": value = position.z
			"turn": value = float(summary.turn)
			"size": value = float(summary.size)
		spin.set_value_no_signal(value)
	(_labels["turn"] as Label).text = "Turn" if count == 1 else "Turn by"
	(_labels["size"] as Label).text = "Size" if count == 1 else "Scale by"
	(_buttons["group"] as Button).disabled = count < 2
	(_buttons["ungroup"] as Button).disabled = not grouped
	(_buttons["open_group"] as Button).disabled = not grouped or not open_group.is_empty()


func spin(field: String) -> SpinBox:
	return _spins.get(field) as SpinBox


func button(tool: String) -> Button:
	return _buttons.get(tool) as Button


func name_text() -> String:
	return _name.text


func _on_value_changed(value: float, field: String) -> void:
	if _shown.is_empty():
		return
	field_edited.emit(field, value)
