extends ScrollContainer
## Live rule rows: selectable, keyboard navigable, and individually enabled.
const Slate := preload("res://src/ui/jukebox_style.gd")
signal item_selected(index: int)
signal rule_toggled(index: int, enabled: bool)
signal rule_moved(from: int, to: int)
var item_count: int:
	get: return _rows.size()
var _column: VBoxContainer
var _rows: Array[Button] = []
var _selected := -1
var _drag_index := -1
var _drop_index := -1
var _drag_origin := Vector2.ZERO
var _dragged := false

func _ready() -> void:
	horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_column = VBoxContainer.new()
	_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_column.add_theme_constant_override("separation", 7)
	add_child(_column)
	custom_minimum_size.y = 164
	size_flags_vertical = Control.SIZE_EXPAND_FILL

func clear() -> void:
	for row: Button in _rows:
		_column.remove_child(row)
		row.queue_free()
	_rows.clear()
	_selected = -1
	_drag_index = -1
	_drop_index = -1

func add_rule(condition: String, action: String, enabled: bool) -> void:
	var index := _rows.size()
	var row := Button.new()
	row.name = "Rule%d" % (index + 1)
	row.custom_minimum_size.y = 50
	row.button_down.connect(func() -> void: select(index); item_selected.emit(index))
	row.gui_input.connect(_on_row_input.bind(index))
	_column.add_child(row)
	_rows.append(row)
	var content := HBoxContainer.new()
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(content)
	content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	content.offset_left = 8
	content.offset_right = -8
	content.add_theme_constant_override("separation", 9)
	content.add_child(Slate.texture_rect(Slate.icon("grip", Slate.MUTED, 13), Vector2(10, 20)))
	var number := _label(content, str(index + 1), 18)
	number.add_theme_color_override("font_color", Slate.MUTED)
	_label(content, condition, 70).size_flags_stretch_ratio = 0.9
	_label(content, "→", 18)
	_label(content, action, 90).size_flags_stretch_ratio = 1.15
	var toggle := CheckButton.new()
	toggle.name = "RuleEnabled"
	toggle.tooltip_text = "Enable rule %d" % (index + 1)
	toggle.set_pressed_no_signal(enabled)
	toggle.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	toggle.toggled.connect(func(value: bool) -> void: rule_toggled.emit(index, value))
	content.add_child(toggle)
	row.tooltip_text = "%d. %s → %s" % [index + 1, condition, action]

func _on_row_input(event: InputEvent, index: int) -> void:
	if index >= _rows.size(): return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed and event.position.x < 28:
			_drag_index = index
			_drop_index = index
			_drag_origin = _rows[index].get_global_transform() * event.position
			_dragged = false
		elif not event.pressed and _drag_index >= 0:
			var source := _drag_index
			var destination := _drop_index
			var moved := _dragged and source != destination and destination >= 0
			_drag_index = -1
			_dragged = false
			for row: Button in _rows: row.modulate.a = 1.0
			if moved:
				accept_event()
				rule_moved.emit(source, destination)
	elif event is InputEventMouseMotion and _drag_index >= 0:
		var pointer: Vector2 = _rows[index].get_global_transform() * event.position
		if pointer.distance_to(_drag_origin) < 6: return
		_dragged = true
		_rows[_drag_index].modulate.a = 0.6
		for position: int in _rows.size():
			if _rows[position].get_global_rect().has_point(pointer):
				_drop_index = position
				_rows[position].add_theme_stylebox_override("normal", Slate.selected())
		accept_event()

func _label(parent: Node, value: String, minimum: float) -> Label:
	var label := Label.new()
	label.text = value
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.custom_minimum_size.x = minimum
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	if minimum >= 70: label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(label)
	return label

func select(index: int) -> void:
	_selected = index
	for position: int in _rows.size():
		_rows[position].add_theme_stylebox_override("normal", Slate.selected() if position == index else Slate.box(Color("192b3a"), Color("415a6f"), 7))

func deselect_all() -> void:
	select(-1)

func get_selected_items() -> PackedInt32Array:
	return PackedInt32Array([_selected]) if _selected >= 0 else PackedInt32Array()
