@tool
extends EditorDock

signal open_requested(scene_path: String)
signal references_changed(ids: PackedStringArray)
signal refresh_requested
signal sculpt_toggled(enabled: bool)
signal sculpt_pick_height_requested
signal heightmap_import_requested(path: String, area: Rect2, low: float, high: float,
		replace: bool)
signal heightmap_preview_requested(path: String, area: Rect2, low: float, high: float,
		replace: bool)
signal heightmap_preview_cancelled
signal heightmap_area_pick_requested

var _entries: Array[Dictionary] = []
var _active_id := ""
var _selected_ids := PackedStringArray()
var _active: Label
var _territory: OptionButton
var _open: Button
var _references: ItemList
var _hide: Button
var _refresh: Button
var _status: Label
var _sculpt_toggle: CheckButton
var _sculpt_mode: OptionButton
var _sculpt_radius: SpinBox
var _sculpt_strength: SpinBox
var _sculpt_softness: SpinBox
var _sculpt_flatten: SpinBox
var _sculpt_pick: Button
var _sculpt_status: Label
var _sculpt_allowed := false
var _heightmap_button: Button
var _heightmap_dialog: ConfirmationDialog
var _heightmap_path: LineEdit
var _heightmap_mode: OptionButton
var _heightmap_low: SpinBox
var _heightmap_high: SpinBox
var _heightmap_area: Array[SpinBox] = []
var _heightmap_files: EditorFileDialog
var _browse: Button
var _picker: PopupPanel
var _picker_list: ItemList
var _thumbnails := {}
## Map picker thumbnails: each territory's published minimap, this many pixels.
const PICKER_THUMBNAIL := 160


func configure(entries: Array[Dictionary], active_id: String,
		selected_ids := PackedStringArray()) -> void:
	if _active == null:
		_build_ui()
	_entries = entries.duplicate(true)
	_active_id = active_id
	_selected_ids = selected_ids.duplicate()
	_rebuild()


func show_status(message: String) -> void:
	if _status != null:
		_status.text = message


func selected_reference_ids() -> PackedStringArray:
	return _selected_ids.duplicate()


func set_sculpt_available(available: bool, reason := "") -> void:
	_sculpt_allowed = available
	if _sculpt_toggle == null:
		return
	if not available:
		_sculpt_toggle.set_pressed_no_signal(false)
	_sculpt_toggle.disabled = not available
	if _heightmap_button != null:
		_heightmap_button.disabled = not available
	_sculpt_toggle.tooltip_text = "Paint the active authored terrain in the 3D view." \
		if available else reason
	_set_sculpt_controls_enabled(available and _sculpt_toggle.button_pressed)
	show_sculpt_status("Borders protected. Ctrl+S saves the sculpt layer." \
		if available else reason)


func set_sculpt_active(active: bool) -> void:
	if _sculpt_toggle == null:
		return
	_sculpt_toggle.set_pressed_no_signal(active and _sculpt_allowed)
	_set_sculpt_controls_enabled(_sculpt_toggle.button_pressed)


func sculpt_settings() -> Dictionary:
	return {
		"mode": _sculpt_mode.selected,
		"radius": _sculpt_radius.value,
		"strength": _sculpt_strength.value,
		"softness": _sculpt_softness.value,
		"flatten_target": _sculpt_flatten.value,
	}


func set_flatten_target(height: float) -> void:
	_sculpt_flatten.value = height
	show_sculpt_status("Flatten target sampled: %.2f m. Borders protected." % height)


## Brush index: 0 Raise, 1 Lower, 2 Smooth, 3 Flatten. Used by the 1-4 keys.
func set_sculpt_mode(index: int) -> void:
	if _sculpt_mode == null or index < 0 or index >= _sculpt_mode.item_count or \
			index == _sculpt_mode.selected:
		return
	_sculpt_mode.select(index)
	_mode_changed(index)


## Multiplies the brush radius or strength, clamped to the fields' own ranges.
func scale_sculpt_radius(factor: float) -> float:
	_sculpt_radius.value = clampf(_sculpt_radius.value * factor, _sculpt_radius.min_value,
		_sculpt_radius.max_value)
	return _sculpt_radius.value


func scale_sculpt_strength(factor: float) -> float:
	_sculpt_strength.value = clampf(_sculpt_strength.value * factor,
		_sculpt_strength.min_value, _sculpt_strength.max_value)
	return _sculpt_strength.value


func show_sculpt_status(message: String) -> void:
	if _sculpt_status != null:
		_sculpt_status.text = message


func _build_ui() -> void:
	title = "Territories"
	layout_key = "MapAuthoringWorkspace"
	default_slot = EditorDock.DOCK_SLOT_RIGHT_BL
	icon_name = &"WorldEnvironment"
	name = "MapAuthoringWorkspace"
	var margin := MarginContainer.new()
	for side in ["margin_left", "margin_top", "margin_right", "margin_bottom"]:
		margin.add_theme_constant_override(side, 8)
	add_child(margin)
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	margin.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 6)
	scroll.add_child(column)
	var heading := Label.new()
	heading.text = "Territory workspace"
	heading.add_theme_font_size_override("font_size", 16)
	column.add_child(heading)
	_active = Label.new()
	_active.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_active)
	var row := HBoxContainer.new()
	_territory = OptionButton.new()
	_territory.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_territory.item_selected.connect(func(_index: int) -> void: _update_open())
	row.add_child(_territory)
	_open = Button.new()
	_open.text = "Open"
	_open.pressed.connect(_open_selected)
	row.add_child(_open)
	_browse = Button.new()
	_browse.text = "Browse…"
	_browse.tooltip_text = "Pick a territory from its published minimap."
	_browse.pressed.connect(open_picker)
	row.add_child(_browse)
	column.add_child(row)
	_build_picker()
	_build_sculpt_ui(column)
	var reference_label := Label.new()
	reference_label.text = "Read-only references"
	column.add_child(reference_label)
	_references = ItemList.new()
	_references.select_mode = ItemList.SELECT_MULTI
	_references.custom_minimum_size = Vector2(270, 180)
	_references.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_references.multi_selected.connect(func(_index: int, _selected: bool) -> void:
		_collect_reference_selection())
	column.add_child(_references)
	var actions := HBoxContainer.new()
	_hide = Button.new()
	_hide.text = "Hide all"
	_hide.pressed.connect(_hide_all)
	actions.add_child(_hide)
	_refresh = Button.new()
	_refresh.text = "Refresh sources"
	_refresh.tooltip_text = "Reload the territory catalog and selected saved/published references."
	_refresh.pressed.connect(func() -> void: refresh_requested.emit())
	actions.add_child(_refresh)
	column.add_child(actions)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_status)


func _build_sculpt_ui(column: VBoxContainer) -> void:
	var sculpt_heading := Label.new()
	sculpt_heading.text = "Terrain sculpt"
	sculpt_heading.add_theme_font_size_override("font_size", 15)
	column.add_child(sculpt_heading)
	_sculpt_toggle = CheckButton.new()
	_sculpt_toggle.text = "Sculpt terrain in 3D"
	_sculpt_toggle.disabled = true
	_sculpt_toggle.toggled.connect(func(enabled: bool) -> void:
		_set_sculpt_controls_enabled(enabled)
		sculpt_toggled.emit(enabled))
	column.add_child(_sculpt_toggle)
	var grid := GridContainer.new()
	grid.columns = 2
	column.add_child(grid)
	_sculpt_mode = OptionButton.new()
	for label in ["Raise", "Lower", "Smooth", "Flatten"]:
		_sculpt_mode.add_item(label)
	_sculpt_mode.item_selected.connect(_mode_changed)
	_add_sculpt_field(grid, "Brush", _sculpt_mode)
	_sculpt_radius = _spin(2.0, 64.0, 0.5, 8.0, " metres")
	_add_sculpt_field(grid, "Radius", _sculpt_radius)
	_sculpt_strength = _spin(0.01, 4.0, 0.01, 0.35, " m / stamp")
	_add_sculpt_field(grid, "Strength", _sculpt_strength)
	_sculpt_softness = _spin(0.0, 1.0, 0.05, 0.65, " edge")
	_add_sculpt_field(grid, "Softness", _sculpt_softness)
	var flatten_row := HBoxContainer.new()
	_sculpt_flatten = _spin(-1000.0, 5000.0, 0.1, 0.0, " m")
	_sculpt_flatten.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	flatten_row.add_child(_sculpt_flatten)
	_sculpt_pick = Button.new()
	_sculpt_pick.text = "Pick"
	_sculpt_pick.tooltip_text = "Use the next terrain click as the flatten height."
	_sculpt_pick.pressed.connect(func() -> void: sculpt_pick_height_requested.emit())
	flatten_row.add_child(_sculpt_pick)
	_add_sculpt_field(grid, "Flatten Y", flatten_row)
	_heightmap_button = Button.new()
	_heightmap_button.text = "Import heightmap…"
	_heightmap_button.tooltip_text = ("Write a greyscale image into the sculpt layer: black and " +
		"white map to heights you choose. Borders stay protected; the base heights are never " +
		"rewritten.")
	_heightmap_button.disabled = true
	_heightmap_button.pressed.connect(open_heightmap_dialog)
	column.add_child(_heightmap_button)
	_build_heightmap_dialog()
	_sculpt_status = Label.new()
	_sculpt_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_sculpt_status)
	_mode_changed(0)
	_set_sculpt_controls_enabled(false)


func _build_heightmap_dialog() -> void:
	_heightmap_dialog = ConfirmationDialog.new()
	_heightmap_dialog.title = "Import heightmap"
	_heightmap_dialog.ok_button_text = "Import"
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(430, 0)
	_heightmap_dialog.add_child(column)
	var file_row := HBoxContainer.new()
	_heightmap_path = LineEdit.new()
	_heightmap_path.placeholder_text = "Greyscale image (PNG, EXR, WebP…)"
	_heightmap_path.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	file_row.add_child(_heightmap_path)
	var browse := Button.new()
	browse.text = "Browse…"
	browse.pressed.connect(func() -> void: _heightmap_files.popup_file_dialog())
	file_row.add_child(browse)
	column.add_child(file_row)
	var grid := GridContainer.new()
	grid.columns = 2
	column.add_child(grid)
	_heightmap_mode = OptionButton.new()
	_heightmap_mode.add_item("Replace heights")
	_heightmap_mode.add_item("Offset heights (add)")
	_add_sculpt_field(grid, "Mode", _heightmap_mode)
	_heightmap_low = _spin(-2000.0, 4000.0, 0.1, 0.0, " m")
	_add_sculpt_field(grid, "Black is", _heightmap_low)
	_heightmap_high = _spin(-2000.0, 4000.0, 0.1, 20.0, " m")
	_add_sculpt_field(grid, "White is", _heightmap_high)
	for label in ["Area west X", "Area north Z", "Area width", "Area depth"]:
		var field := _spin(-100000.0, 100000.0, 0.5, 0.0, " m")
		_heightmap_area.append(field)
		_add_sculpt_field(grid, label, field)
	var note := Label.new()
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.text = ("The image's top row is north. The area is in terrain metres and starts as the " +
		"whole terrain grid; Pick area on map drags it out in the 3D view. Preview shows the " +
		"result on the terrain without keeping it. Locked border samples never change, the " +
		"fade band blends, and one undo step reverts an import.")
	column.add_child(note)
	_heightmap_dialog.add_button("Pick area on map", false, "pick")
	_heightmap_dialog.add_button("Preview", false, "preview")
	_heightmap_dialog.custom_action.connect(func(action: StringName) -> void:
		if action == &"preview":
			heightmap_preview_requested.emit(_heightmap_path.text, heightmap_area(),
				_heightmap_low.value, _heightmap_high.value, _heightmap_mode.selected == 0)
		elif action == &"pick":
			_heightmap_dialog.hide()
			heightmap_area_pick_requested.emit())
	_heightmap_dialog.canceled.connect(func() -> void: heightmap_preview_cancelled.emit())
	_heightmap_dialog.confirmed.connect(func() -> void:
		heightmap_import_requested.emit(_heightmap_path.text, heightmap_area(),
			_heightmap_low.value, _heightmap_high.value, _heightmap_mode.selected == 0))
	add_child(_heightmap_dialog)
	_heightmap_files = EditorFileDialog.new()
	_heightmap_files.file_mode = EditorFileDialog.FILE_MODE_OPEN_FILE
	_heightmap_files.access = EditorFileDialog.ACCESS_FILESYSTEM
	_heightmap_files.filters = PackedStringArray(["*.png, *.exr, *.webp, *.jpg, *.jpeg, *.hdr ; Images"])
	_heightmap_files.file_selected.connect(func(path: String) -> void: _heightmap_path.text = path)
	add_child(_heightmap_files)


func open_heightmap_dialog() -> void:
	if is_inside_tree():
		_heightmap_dialog.popup_centered()


## The terrain-local rectangle the heightmap covers (from the dialog's fields).
func heightmap_area() -> Rect2:
	return Rect2(_heightmap_area[0].value, _heightmap_area[1].value,
		_heightmap_area[2].value, _heightmap_area[3].value)


func set_heightmap_area(area: Rect2) -> void:
	if _heightmap_area.size() != 4:
		return
	for pair: Array in [[0, area.position.x], [1, area.position.y], [2, area.size.x],
			[3, area.size.y]]:
		(_heightmap_area[pair[0]] as SpinBox).value = float(pair[1])


func _add_sculpt_field(grid: GridContainer, label: String, field: Control) -> void:
	var caption := Label.new()
	caption.text = label
	grid.add_child(caption)
	grid.add_child(field)


func _spin(minimum: float, maximum: float, increment: float, value: float,
		suffix_text: String) -> SpinBox:
	var spin := SpinBox.new()
	spin.min_value = minimum
	spin.max_value = maximum
	spin.step = increment
	spin.value = value
	spin.suffix = suffix_text
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return spin


func _mode_changed(index: int) -> void:
	var blend_mode := index >= 2
	_sculpt_strength.max_value = 1.0 if blend_mode else 4.0
	_sculpt_strength.value = 0.3 if blend_mode else 0.35
	_sculpt_strength.suffix = " blend" if blend_mode else " m / stamp"
	_sculpt_flatten.editable = index == 3
	_sculpt_pick.disabled = not _sculpt_toggle.button_pressed or index != 3


func _set_sculpt_controls_enabled(enabled: bool) -> void:
	if _sculpt_mode != null:
		_sculpt_mode.disabled = not enabled
	for control in [_sculpt_radius, _sculpt_strength, _sculpt_softness]:
		if control != null:
			control.editable = enabled
	if _sculpt_flatten != null:
		_sculpt_flatten.editable = enabled and _sculpt_mode.selected == 3
	if _sculpt_pick != null:
		_sculpt_pick.disabled = not enabled or _sculpt_mode.selected != 3


func _rebuild() -> void:
	_active.text = "Active: %s" % (_label(_active_id) if not _active_id.is_empty() \
		else "Open an authored territory scene")
	_territory.clear()
	for entry in _entries:
		_territory.add_item("%s — %s" % [String(entry.label),
			"editable" if bool(entry.editable) else "published reference only"])
		_territory.set_item_metadata(_territory.item_count - 1, String(entry.id))
		_territory.set_item_tooltip(_territory.item_count - 1, _tooltip(entry))
		if String(entry.id) == _active_id:
			_territory.select(_territory.item_count - 1)
	_references.clear()
	for entry in _entries:
		if String(entry.id) == _active_id:
			continue
		_references.add_item("%s — %s" % [String(entry.label), String(entry.source_label)])
		var index := _references.item_count - 1
		_references.set_item_metadata(index, String(entry.id))
		_references.set_item_tooltip(index, _tooltip(entry))
		if String(entry.id) in _selected_ids:
			_references.select(index, false)
	_update_open()
	_hide.disabled = _selected_ids.is_empty()
	_status.text = "Choose neighbours to compare in the active territory's local frame." \
		if not _active_id.is_empty() else "Open an authored territory scene first."


func _update_open() -> void:
	var entry := _selected_entry()
	_open.disabled = entry.is_empty() or not bool(entry.editable) or \
		String(entry.id) == _active_id
	_open.tooltip_text = "Open this saved authored scene in its native editor tab." \
		if not _open.disabled else "This territory has no complete authored source yet."


func _build_picker() -> void:
	_picker = PopupPanel.new()
	_picker.title = "Open territory"
	_picker_list = ItemList.new()
	_picker_list.max_columns = 0
	_picker_list.icon_mode = ItemList.ICON_MODE_TOP
	_picker_list.fixed_column_width = PICKER_THUMBNAIL + 16
	_picker_list.fixed_icon_size = Vector2i(PICKER_THUMBNAIL, PICKER_THUMBNAIL)
	_picker_list.same_column_width = true
	# Four columns by three rows shows every territory without scrolling.
	_picker_list.custom_minimum_size = Vector2(4 * (PICKER_THUMBNAIL + 44) + 24, 3 * (PICKER_THUMBNAIL + 60))
	_picker_list.item_activated.connect(_open_picked)
	_picker_list.item_clicked.connect(func(index: int, _at: Vector2, button: int) -> void:
		if button == MOUSE_BUTTON_LEFT:
			_open_picked(index))
	_picker.add_child(_picker_list)
	add_child(_picker)


## Shows every territory as its published minimap; clicking an editable one
## opens its authored scene.
func open_picker() -> void:
	_fill_picker()
	if is_inside_tree():
		_picker.popup_centered()


## The picker's items, for tests: [{label, id, editable, thumbnail}].
func picker_items() -> Array[Dictionary]:
	_fill_picker()
	var result: Array[Dictionary] = []
	for index in _picker_list.item_count:
		var entry: Dictionary = _picker_list.get_item_metadata(index)
		result.append({"label": _picker_list.get_item_text(index), "id": String(entry.id),
			"editable": not _picker_list.is_item_disabled(index),
			"thumbnail": _picker_list.get_item_icon(index)})
	return result


func pick(index: int) -> void:
	_open_picked(index)


func _fill_picker() -> void:
	_picker_list.clear()
	for entry in _entries:
		var text := String(entry.label)
		if String(entry.id) == _active_id:
			text += " (open)"
		elif not bool(entry.editable):
			text += " (reference only)"
		var index := _picker_list.add_item(text, _thumbnail(entry))
		_picker_list.set_item_metadata(index, entry)
		_picker_list.set_item_tooltip(index, _tooltip(entry))
		_picker_list.set_item_disabled(index, not bool(entry.editable) or
			String(entry.id) == _active_id)


func _thumbnail(entry: Dictionary) -> Texture2D:
	var manifest := String(entry.get("manifest_path", ""))
	if manifest.is_empty():
		return null
	var path := manifest.get_base_dir().path_join("minimap.webp")
	if _thumbnails.has(path):
		return _thumbnails[path]
	var texture: Texture2D = null
	var absolute := ProjectSettings.globalize_path(path)
	if FileAccess.file_exists(absolute):
		var image := Image.load_from_file(absolute)
		if image != null and not image.is_empty():
			var longest := maxi(image.get_width(), image.get_height())
			var factor := float(PICKER_THUMBNAIL) / float(longest)
			image.resize(maxi(roundi(image.get_width() * factor), 1),
				maxi(roundi(image.get_height() * factor), 1), Image.INTERPOLATE_LANCZOS)
			texture = ImageTexture.create_from_image(image)
	_thumbnails[path] = texture
	return texture


func _open_picked(index: int) -> void:
	if index < 0 or index >= _picker_list.item_count or _picker_list.is_item_disabled(index):
		return
	var entry: Dictionary = _picker_list.get_item_metadata(index)
	_picker.hide()
	open_requested.emit(String(entry.scene_path))


func _open_selected() -> void:
	var entry := _selected_entry()
	if not entry.is_empty() and bool(entry.editable):
		open_requested.emit(String(entry.scene_path))


func _selected_entry() -> Dictionary:
	if _territory.selected < 0:
		return {}
	var id := String(_territory.get_item_metadata(_territory.selected))
	for entry in _entries:
		if String(entry.id) == id:
			return entry
	return {}


func _collect_reference_selection() -> void:
	_selected_ids.clear()
	for index in _references.get_selected_items():
		_selected_ids.append(String(_references.get_item_metadata(index)))
	_hide.disabled = _selected_ids.is_empty()
	references_changed.emit(_selected_ids.duplicate())


func _hide_all() -> void:
	_references.deselect_all()
	_selected_ids.clear()
	_hide.disabled = true
	references_changed.emit(PackedStringArray())


func _label(id: String) -> String:
	for entry in _entries:
		if String(entry.id) == id:
			return String(entry.label)
	return id


func _tooltip(entry: Dictionary) -> String:
	return "%s\n%s\nrevision %s\n%s" % [String(entry.source_label),
		String(entry.source_path), String(entry.revision), String(entry.source_sha256)]
