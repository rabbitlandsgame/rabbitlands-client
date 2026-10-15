@tool
extends PopupPanel
## Options for the ground-region and plateau tools (see area_tool.gd) and the
## scatter tool (scatter_tool.gd), opened from Map tools or the toolbar. Start
## closes it and arms the tool.

signal start_requested(kind: String, options: Dictionary)

const GROUND_SCRIPT := preload("res://src/dev/map_authoring_region/ground_region_control.gd")

var kind := "ground"
var _title: Label
var _ground: GridContainer
var _plateau: GridContainer
var _surface: OptionButton
var _surface_choices: Array[Dictionary] = []
var _ground_shape: OptionButton
var _blend: SpinBox
var _opacity: SpinBox
var _priority: SpinBox
var _mode: OptionButton
var _brush: SpinBox
var _brush_label: Label
var _operation: OptionButton
var _plateau_shape: OptionButton
var _height: SpinBox
var _feather: SpinBox
var _height_label: Label
var _scatter: GridContainer
var _scatter_asset: Label
var _scatter_radius: SpinBox
var _scatter_density: SpinBox
var _scatter_spacing: SpinBox
var _scatter_turn: CheckBox
var _scatter_size: SpinBox
var _scatter_seed: SpinBox
var _scatter_mode: OptionButton
var _scatter_avoid: Dictionary = {}
var _scatter_grade: SpinBox
var _note: Label


func _init() -> void:
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(340, 0)
	column.add_theme_constant_override("separation", 6)
	add_child(column)
	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 15)
	column.add_child(_title)
	_ground = GridContainer.new()
	_ground.columns = 2
	column.add_child(_ground)
	_surface = OptionButton.new()
	_surface.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_field(_ground, "Surface", _surface)
	_ground_shape = _shape_picker()
	_field(_ground, "Shape", _ground_shape)
	_blend = _spin(0.0, 16.0, 0.25, 3.0, " m")
	_field(_ground, "Feather", _blend)
	_opacity = _spin(0.05, 1.0, 0.01, 0.9, "")
	_field(_ground, "Opacity", _opacity)
	_priority = _spin(-1000.0, 1000.0, 1.0, 10.0, "")
	_field(_ground, "Priority", _priority)
	_mode = OptionButton.new()
	_mode.add_item("Drag out one region")
	_mode.add_item("Paint along a stroke")
	_mode.item_selected.connect(func(_index: int) -> void: _sync_brush())
	_field(_ground, "Mode", _mode)
	_brush = _spin(1.0, 64.0, 0.5, 6.0, " m")
	_brush_label = _field(_ground, "Brush size", _brush)
	_plateau = GridContainer.new()
	_plateau.columns = 2
	column.add_child(_plateau)
	_operation = OptionButton.new()
	_operation.add_item("Level at a height (Set)")
	_operation.add_item("Raise or lower (Add)")
	_operation.item_selected.connect(func(_index: int) -> void: _sync_height_label())
	_field(_plateau, "Operation", _operation)
	_plateau_shape = _shape_picker()
	_field(_plateau, "Shape", _plateau_shape)
	_height = _spin(-200.0, 400.0, 0.1, 3.0, " m")
	_height_label = _field(_plateau, "Above ground", _height)
	_feather = _spin(0.0, 64.0, 0.5, 6.0, " m")
	_field(_plateau, "Feather", _feather)
	_scatter = GridContainer.new()
	_scatter.columns = 2
	column.add_child(_scatter)
	_scatter_asset = Label.new()
	_scatter_asset.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_field(_scatter, "Asset", _scatter_asset)
	_scatter_mode = OptionButton.new()
	_scatter_mode.add_item("Paint copies")
	_scatter_mode.add_item("Erase copies")
	_field(_scatter, "Mode", _scatter_mode)
	_scatter_radius = _spin(0.5, 64.0, 0.5, 6.0, " m")
	_field(_scatter, "Brush radius", _scatter_radius)
	_scatter_density = _spin(0.5, 400.0, 0.5, 10.0, " per 100 m²")
	_field(_scatter, "Density", _scatter_density)
	_scatter_spacing = _spin(0.1, 32.0, 0.1, 1.5, " m")
	_field(_scatter, "Min spacing", _scatter_spacing)
	_scatter_turn = CheckBox.new()
	_scatter_turn.button_pressed = true
	_scatter_turn.text = "Random turn"
	_field(_scatter, "Turn", _scatter_turn)
	_scatter_size = _spin(0.0, 0.5, 0.01, 0.15, "")
	_field(_scatter, "Size variation (±)", _scatter_size)
	_scatter_seed = _spin(0.0, 999999.0, 1.0, 1.0, "")
	_field(_scatter, "Seed", _scatter_seed)
	var avoid := HFlowContainer.new()
	for pair: Array in [["avoid_water", "Water"], ["avoid_steep", "Steep ground"],
			["avoid_roads", "Roads"], ["avoid_structures", "Structures"]]:
		var check := CheckBox.new()
		check.text = pair[1]
		check.button_pressed = true
		avoid.add_child(check)
		_scatter_avoid[pair[0]] = check
	_field(_scatter, "Avoid", avoid)
	_scatter_grade = _spin(0.05, 3.0, 0.05, 0.65, "")
	_field(_scatter, "Steepest ground", _scatter_grade)
	_note = Label.new()
	_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_note)
	var start := Button.new()
	start.text = "Start drawing"
	start.pressed.connect(func() -> void:
		hide()
		start_requested.emit(kind, current_options()))
	column.add_child(start)


## Opens for "ground", "plateau" or "scatter"; `root` supplies the territory's
## own surfaces, `asset` the Map Assets entry a scatter would place.
func open_for(tool_kind: String, root: Node, anchor: Rect2i, asset: Dictionary = {}) -> void:
	kind = tool_kind
	_title.text = {"ground": "Paint ground regions", "plateau": "Stamp plateaus",
		"scatter": "Scatter assets"}.get(kind, "")
	_ground.visible = kind == "ground"
	_plateau.visible = kind == "plateau"
	_scatter.visible = kind == "scatter"
	_scatter_asset.text = String(asset.get("label", "Select an asset in the Map Assets dock first"))
	_note.text = ("Press and drag in the 3D view to paint copies of the asset, or with Erase to " +
		"remove its copies (X switches); each stroke is one undo step and moves to the next seed. " +
		"Esc discards a stroke; right-click stops.") \
		if kind == "scatter" else ("Press where the centre goes in the 3D view and drag out the " +
		"size (or paint along a stroke); Q/E turn the shape. Esc discards a draft; right-click stops.")
	fill_surfaces(root)
	_sync_height_label()
	_sync_brush()
	if is_inside_tree():
		popup(anchor)


## Surfaces this territory's ground regions already use (a shared surface file
## is reused; an embedded one is copied), then the texture presets.
func fill_surfaces(root: Node) -> void:
	var previous := _surface.get_item_text(_surface.selected) if _surface.item_count > 0 else ""
	_surface.clear()
	_surface_choices.clear()
	var seen := {}
	var regions := root.get_node_or_null("Ground/Regions") if root != null else null
	if regions != null:
		for child in regions.get_children():
			if child.get_script() != GROUND_SCRIPT or child.get("surface") == null:
				continue
			var surface: Resource = child.get("surface")
			var shared := not surface.resource_path.is_empty() and not "::" in surface.resource_path
			var key := surface.resource_path if shared else str(surface.get_instance_id())
			if seen.has(key):
				continue
			seen[key] = true
			_surface_choices.append({"label": surface.resource_path.get_file() if shared else
				"As %s (copy)" % String(child.get("region_id")), "surface": surface,
				"copy": not shared})
	for preset: String in MapAuthoringTexturePresets.PRESET_NAMES:
		if preset != MapAuthoringTexturePresets.CUSTOM:
			_surface_choices.append({"label": "Preset: %s" % preset, "preset": preset})
	for choice in _surface_choices:
		_surface.add_item(String(choice.label))
		if String(choice.label) == previous:
			_surface.select(_surface.item_count - 1)


## The options area_tool.gd (or scatter_tool.gd) expects.
func current_options() -> Dictionary:
	if kind == "scatter":
		var options := {"radius": _scatter_radius.value, "density": _scatter_density.value,
			"spacing": _scatter_spacing.value, "random_turn": _scatter_turn.button_pressed,
			"size_variation": _scatter_size.value, "seed": int(_scatter_seed.value),
			"erase": _scatter_mode.selected == 1, "max_grade": _scatter_grade.value}
		for key: String in _scatter_avoid:
			options[key] = (_scatter_avoid[key] as CheckBox).button_pressed
		return options
	if kind == "ground":
		var choice: Dictionary = _surface_choices[_surface.selected] \
			if _surface.selected >= 0 and _surface.selected < _surface_choices.size() else {}
		var options := {"shape": _ground_shape.selected, "blend_width": _blend.value,
			"opacity": _opacity.value, "priority": int(_priority.value),
			"surface_label": String(choice.get("label", "")), "stroke": _mode.selected == 1,
			"brush": _brush.value}
		if choice.has("surface"):
			options["surface"] = (choice.surface as Resource).duplicate(true) \
				if bool(choice.get("copy", false)) else choice.surface
		elif choice.has("preset"):
			options["preset"] = choice.preset
		return options
	return {"operation": "set" if _operation.selected == 0 else "add",
		"shape": _plateau_shape.selected, "height": _height.value, "feather": _feather.value}


func select_surface(label: String) -> bool:
	for index in _surface.item_count:
		if _surface.get_item_text(index) == label:
			_surface.select(index)
			return true
	return false


func set_stroke(enabled: bool, size := 6.0) -> void:
	_mode.select(1 if enabled else 0)
	_brush.value = size
	_sync_brush()


func _sync_brush() -> void:
	_brush.visible = _mode.selected == 1
	_brush_label.visible = _mode.selected == 1


func _sync_height_label() -> void:
	_height_label.text = "Above ground" if _operation.selected == 0 else "Raise by"


func _shape_picker() -> OptionButton:
	var picker := OptionButton.new()
	picker.add_item("Ellipse")
	picker.add_item("Rectangle")
	return picker


func _field(grid: GridContainer, text: String, control: Control) -> Label:
	var label := Label.new()
	label.text = text
	grid.add_child(label)
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(control)
	return label


func _spin(minimum: float, maximum: float, step: float, value: float, suffix: String) -> SpinBox:
	var spin := SpinBox.new()
	spin.min_value = minimum
	spin.max_value = maximum
	spin.step = step
	spin.value = value
	spin.suffix = suffix
	return spin
