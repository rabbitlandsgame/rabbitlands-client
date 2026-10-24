extends PanelContainer
## Live inventory design editor. All mutations go through the workspace's history.
const Chrome := preload("res://src/ui/compact_hud_style.gd")
const Presets := preload("res://src/ui/inventory_presets.gd")
var workspace: Control
var selected := "backpack"
var picker: OptionButton
var component: OptionButton
var options: VBoxContainer
var design_name: LineEdit
var message: Label
var _refreshing := false

func configure(owner_workspace: Control) -> void:
	workspace = owner_workspace
	name = "InventoryEditor"
	custom_minimum_size = Vector2(350, 0)
	add_theme_stylebox_override("panel", Chrome.box(Color("141310fa"), Chrome.BRASS, 12))
	var column := VBoxContainer.new()
	column.name = "EditorBody"
	column.add_theme_constant_override("separation", 8)
	add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var title := Label.new()
	title.text = "Inventory editor"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	header.add_child(_button("Save", func() -> void: workspace.finish_edit(true)))
	header.add_child(_button("Cancel", func() -> void: workspace.finish_edit(false)))
	var dragger := WindowDrag.attach(self, header)
	dragger.reserved_right = 6
	dragger.reserved_bottom = 6
	var hint := Label.new()
	hint.text = "Select a section, then drag it or its corner to resize.\nArrow keys move 1px; Shift moves 10px."
	hint.add_theme_font_size_override("font_size", 12)
	column.add_child(hint)
	picker = OptionButton.new()
	picker.name = "InventoryEditorPresets"
	picker.item_selected.connect(func(index: int) -> void:
		if not _refreshing: workspace.choose_preset(str(picker.get_item_metadata(index))))
	column.add_child(picker)
	var history := HBoxContainer.new()
	column.add_child(history)
	history.add_child(_button("Undo", func() -> void: workspace.undo_edit()))
	history.add_child(_button("Redo", func() -> void: workspace.undo_edit(true)))
	history.add_child(_button("Restore default", func() -> void:
		workspace.checkpoint()
		workspace.model.working = Presets.preset(workspace.model.working.recipe)
		workspace.apply_layout()
		refresh()))
	var save_row := HBoxContainer.new()
	column.add_child(save_row)
	design_name = LineEdit.new()
	design_name.name = "InventoryDesignName"
	design_name.placeholder_text = "Name your custom design"
	design_name.max_length = 48
	design_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	save_row.add_child(design_name)
	save_row.add_child(_button("Save as new", func() -> void:
		workspace.checkpoint()
		var id: String = workspace.model.save_custom(design_name.text)
		message.text = "Five custom designs are saved. Update or delete one to make room." if id.is_empty() else "Custom design created. Save keeps it; Cancel discards it."
		refresh()))
	var custom_actions := HBoxContainer.new()
	column.add_child(custom_actions)
	custom_actions.add_child(_button("Update custom", func() -> void:
		if not workspace.model.custom.has(workspace.model.active): return
		workspace.checkpoint()
		workspace.model.save_custom(design_name.text, workspace.model.active)
		refresh()))
	custom_actions.add_child(_button("Delete custom", func() -> void:
		workspace.checkpoint()
		workspace.model.delete_custom(workspace.model.active)
		workspace.apply_layout()
		refresh()))
	custom_actions.name = "CustomActions"
	component = OptionButton.new()
	component.name = "InventoryEditorComponent"
	for key: String in Presets.PARTS:
		component.add_item(Presets.PARTS[key])
		component.set_item_metadata(component.item_count - 1, key)
	component.item_selected.connect(func(index: int) -> void: select_component(str(component.get_item_metadata(index))))
	column.add_child(component)
	var scroll := ScrollContainer.new()
	scroll.name = "InventoryEditorOptions"
	scroll.custom_minimum_size = Vector2(0, 250)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	options = VBoxContainer.new()
	options.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	options.add_theme_constant_override("separation", 6)
	scroll.add_child(options)
	message = Label.new()
	message.text = "Preview only · Save keeps edits; Cancel restores your design."
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message.custom_minimum_size.x = 320
	message.add_theme_font_size_override("font_size", 12)
	column.add_child(message)
	position = Vector2(24, 100)
	hide()

func _button(text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	Chrome.button(button)
	button.pressed.connect(callback)
	return button

func refresh() -> void:
	_refreshing = true
	picker.clear()
	var ids: Array = Presets.BUILT_INS.keys() + workspace.model.custom.keys()
	for id: String in ids:
		picker.add_item(str(Presets.BUILT_INS.get(id, workspace.model.custom.get(id, {}).get("name", id))))
		picker.set_item_metadata(picker.item_count - 1, id)
		if id == workspace.model.active: picker.select(picker.item_count - 1)
	design_name.text = str(workspace.model.custom.get(workspace.model.active, {}).get("name", ""))
	_refreshing = false
	for button: Button in get_node("EditorBody/CustomActions").get_children():
		button.disabled = not workspace.model.custom.has(workspace.model.active)
	select_component(selected)
	var screen: Vector2 = workspace.main.game_view.size
	var scroll: ScrollContainer = get_node("EditorBody/InventoryEditorOptions")
	scroll.custom_minimum_size.y = clampf(screen.y - 380, 80, 250)
	reset_size()
	position = position.clamp(Vector2(6, 6), (screen - size - Vector2(6, 6)).max(Vector2(6, 6)))
	workspace._refresh_pickers()

func select_component(key: String) -> void:
	selected = key
	for index: int in component.item_count:
		if component.get_item_metadata(index) == key: component.select(index)
	for child: Node in options.get_children():
		options.remove_child(child)
		child.queue_free()
	var config: Dictionary = workspace.model.working
	var part: Dictionary = config.parts[key]
	_heading("Layout")
	_choice("Window position", ["right", "bottom_right", "bottom_center", "free"], config.anchor, func(value: String) -> void: workspace.change_option("anchor", value))
	_number("Window scale", config.scale, 0.75, 1.75, 0.05, func(value: float) -> void: workspace.change_option("scale", value))
	_choice("Equipment location", ["left", "right", "top"], config.equipment_side, func(value: String) -> void: workspace.change_option("equipment_side", value))
	_choice("Inspection layout", Presets.PLACEMENTS, config.inspection_mode, func(value: String) -> void: workspace.change_option("inspection_mode", value))
	if key != "backpack": _toggle("Show " + Presets.PARTS[key], part.enabled, func(value: bool) -> void: workspace.change_part(key, "enabled", value))
	for axis: String in ["x", "y"]:
		_number("Section offset " + axis.to_upper(), part.offset.x if axis == "x" else part.offset.y, -300, 800, 1, func(value: float) -> void:
			var offset: Vector2 = workspace.model.working.parts[key].offset
			if axis == "x": offset.x = value
			else: offset.y = value
			workspace.change_part(key, "offset", offset))
	if key in ["backpack", "equipment"]:
		_number("Columns", part.columns, 1, 12 if key == "backpack" else 8, 1, func(value: float) -> void: workspace.change_part(key, "columns", int(value)))
		_number("Slot size", part.cell, 28, 64, 1, func(value: float) -> void: workspace.change_part(key, "cell", int(value)))
		_number("Slot spacing", config.gap, 0, 10, 1, func(value: float) -> void: workspace.change_option("gap", int(value)))
		if key == "backpack": _toggle("Show stack quantities", part.show_quantity, func(value: bool) -> void: workspace.change_part(key, "show_quantity", value))
		_number("Icon opacity", part.icon_opacity * 100, 25, 100, 1, func(value: float) -> void: workspace.change_part(key, "icon_opacity", value / 100))
	else:
		_number("Section height", part.height, 32 if key == "preview" else 140, 400, 1, func(value: float) -> void: workspace.change_part(key, "height", int(value)))
		if key == "inspection":
			_number("Card width", part.width, 200, 500, 1, func(value: float) -> void: workspace.change_part(key, "width", int(value)))
			for field: String in ["description", "stats", "comparison"]:
				_toggle("Show " + field, config["show_" + field], func(value: bool) -> void:
					workspace.change_option("show_" + field, value)
					workspace._render_detail())
	options.add_child(_button("Reset this section", func() -> void:
		workspace.checkpoint()
		workspace.model.working.parts[key] = Presets.preset(workspace.model.working.recipe).parts[key].duplicate(true)
		workspace.apply_layout()
		select_component(key)))
	_heading("Appearance")
	_number("Text size", config.font_size, 11, 20, 1, func(value: float) -> void: workspace.change_option("font_size", int(value)))
	_choice("Border design", ["plain", "beveled", "ornate"], config.border_style, func(value: String) -> void: workspace.change_option("border_style", value))
	for field: String in ["background", "border", "text"]:
		var row := _row(field.capitalize() + " color")
		var color := ColorPickerButton.new()
		color.custom_minimum_size = Vector2(90, 24)
		color.color = config[field]
		color.color_changed.connect(func(value: Color) -> void: workspace.change_option(field, value))
		row.add_child(color)
	_number("Background opacity", config.background.a * 100, 0, 100, 1, func(value: float) -> void:
		var color: Color = workspace.model.working.background
		color.a = value / 100
		workspace.change_option("background", color))
	workspace.queue_redraw()

func _heading(text: String) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", Color("d7b875"))
	options.add_child(label)

func _row(caption: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	var label := Label.new()
	label.text = caption
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(label)
	options.add_child(row)
	return row

func _number(caption: String, value: float, low: float, high: float, step: float, callback: Callable) -> void:
	var row := _row(caption)
	var number := SpinBox.new()
	number.min_value = low
	number.max_value = high
	number.step = step
	number.value = value
	number.custom_minimum_size.x = 100
	number.value_changed.connect(callback)
	row.add_child(number)

func _choice(caption: String, choices: Array, value: String, callback: Callable) -> void:
	var row := _row(caption)
	var choice := OptionButton.new()
	for entry: String in choices:
		choice.add_item(entry.replace("_", " ").capitalize())
		if entry == value: choice.select(choice.item_count - 1)
	choice.item_selected.connect(func(index: int) -> void: callback.call(choices[index]))
	row.add_child(choice)

func _toggle(caption: String, value: bool, callback: Callable) -> void:
	var toggle := CheckBox.new()
	toggle.text = caption
	toggle.button_pressed = value
	toggle.toggled.connect(callback)
	options.add_child(toggle)
