extends ScrollContainer
## Song title and source credit have separate sizes and never merge or wrap.
const Slate := preload("res://src/ui/jukebox_style.gd")
signal item_selected(index: int)
signal item_activated(index: int)
var fixed_icon_size := Vector2i(48, 48)
var item_count: int:
	get: return _rows.size()
var _rows: Array[Button] = []
var _metadata: Array = []
var _titles: Array[String] = []
var _column: VBoxContainer
var _selected := -1

func _ready() -> void:
	horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	follow_focus = true
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	custom_minimum_size.y = 90
	_column = VBoxContainer.new()
	_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_column.add_theme_constant_override("separation", 3)
	add_child(_column)

func clear() -> void:
	for row: Button in _rows:
		_column.remove_child(row)
		row.queue_free()
	_rows.clear()
	_metadata.clear()
	_titles.clear()
	_selected = -1

func add_item(text: String, texture: Texture2D = null) -> int:
	var index := _rows.size()
	var row := Button.new()
	row.custom_minimum_size.y = fixed_icon_size.y + 12
	row.clip_contents = true
	row.add_theme_stylebox_override("normal", Slate.box(Color("132332"), Color("263d4f"), 7, 3))
	row.pressed.connect(func() -> void: select(index); item_selected.emit(index))
	row.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.double_click:
			select(index)
			item_activated.emit(index)
		elif event is InputEventKey and event.pressed and event.keycode == KEY_ENTER:
			item_activated.emit(index))
	_column.add_child(row)
	_rows.append(row)
	_metadata.append(null)
	_titles.append(text)
	var content := HBoxContainer.new()
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_theme_constant_override("separation", 12)
	row.add_child(content)
	content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	content.offset_left = 7
	content.offset_top = 6
	content.offset_right = -8
	content.offset_bottom = -6
	if texture != null: content.add_child(Slate.texture_rect(texture, Vector2(fixed_icon_size)))
	var words := VBoxContainer.new()
	words.mouse_filter = Control.MOUSE_FILTER_IGNORE
	words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	words.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	words.add_theme_constant_override("separation", 3)
	content.add_child(words)
	var lines := text.split("\n", false)
	for line: int in lines.size():
		var label := Label.new()
		label.text = lines[line]
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		label.add_theme_font_size_override("font_size", 15 if line == 0 else 12)
		label.add_theme_color_override("font_color", Slate.TEXT if line == 0 else Slate.MUTED)
		words.add_child(label)
	return index

func set_item_metadata(index: int, value: Variant) -> void:
	_metadata[index] = value

func get_item_metadata(index: int) -> Variant:
	return _metadata[index]

func get_item_text(index: int) -> String:
	return _titles[index]

func set_item_tooltip(index: int, text: String) -> void:
	_rows[index].tooltip_text = text

func select(index: int) -> void:
	_selected = index
	for position: int in _rows.size():
		_rows[position].add_theme_stylebox_override("normal", Slate.selected() if position == index else Slate.box(Color("132332"), Color("263d4f"), 7, 3))

func get_selected_items() -> PackedInt32Array:
	return PackedInt32Array([_selected]) if _selected >= 0 else PackedInt32Array()
