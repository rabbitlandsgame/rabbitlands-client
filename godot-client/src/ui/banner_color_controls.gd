extends VBoxContainer
## The menu, Settings and HUD editor share the same per-item controls.
signal color_changed(item: String, color: Color)
signal sync_changed(item: String, enabled: bool)
signal sync_all_changed(enabled: bool)
signal reset_requested
const Colors := preload("res://src/ui/banner_colors.gd")
var pickers: Dictionary = {}
var matches: Dictionary = {}

func _ready() -> void:
	add_theme_constant_override("separation", 6)
	var hint := Label.new()
	hint.text = "Choose each item's color, or match its resource window color. Bar and values use the same color."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_font_size_override("font_size", 12)
	add_child(hint)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 4)
	add_child(grid)
	for caption: String in ["Item", "Color", "Match"]:
		var label := Label.new()
		label.text = caption
		label.add_theme_font_size_override("font_size", 12)
		grid.add_child(label)
	for item: String in Colors.LABELS:
		var label := Label.new()
		label.text = Colors.LABELS[item]
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.add_theme_font_size_override("font_size", 13)
		grid.add_child(label)
		var picker := ColorPickerButton.new()
		picker.name = "BannerColor_" + item
		picker.color = Colors.DEFAULTS[item]
		picker.edit_alpha = false
		picker.custom_minimum_size = Vector2(52, 24)
		picker.tooltip_text = "Independent " + Colors.LABELS[item].to_lower() + " color"
		picker.color_changed.connect(func(color: Color) -> void: color_changed.emit(item, color))
		grid.add_child(picker)
		pickers[item] = picker
		if Colors.RESOURCES.has(item):
			var box := CheckBox.new()
			box.name = "BannerColorSync_" + item
			box.tooltip_text = "Follow the resource window. Turn off to restore this item's independent color."
			box.toggled.connect(func(enabled: bool) -> void: sync_changed.emit(item, enabled))
			grid.add_child(box)
			matches[item] = box
		else:
			var empty := Label.new()
			empty.text = "—"
			grid.add_child(empty)
	var actions := HBoxContainer.new()
	add_child(actions)
	for caption: String in ["Match all", "Independent", "Reset colors"]:
		var button := Button.new()
		button.text = caption
		button.add_theme_font_size_override("font_size", 12)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.pressed.connect(func() -> void:
			if caption == "Reset colors": reset_requested.emit()
			else: sync_all_changed.emit(caption == "Match all"))
		actions.add_child(button)

func sync_colors(options: Dictionary, resources: Dictionary) -> void:
	for item: String in pickers:
		var linked: bool = options.get("synced", {}).get(item, false)
		var picker: ColorPickerButton = pickers[item]
		picker.color = Colors.resolve(item, options, resources, Colors.DEFAULTS[item])
		picker.disabled = linked
		if matches.has(item): (matches[item] as CheckBox).set_pressed_no_signal(linked)

func open_picker() -> PopupPanel:
	for picker: ColorPickerButton in pickers.values():
		if picker.get_popup().visible: return picker.get_popup()
	return null

func close_pickers() -> void:
	for picker: ColorPickerButton in pickers.values(): picker.get_popup().hide()
