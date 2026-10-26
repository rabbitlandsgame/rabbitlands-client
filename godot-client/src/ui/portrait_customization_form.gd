extends VBoxContainer
## The same controls drive creation and the existing-player dressing room.

signal changed
signal preset_selected(appearance: Dictionary)
const CUSTOMIZATION = preload("res://src/actors/portrait_customization.gd")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
var controls: Dictionary = {}
var _timer: Timer

func _init() -> void:
	name = "PortraitCustomization"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 6)
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.wait_time = 0.12
	add_child(_timer)
	_timer.timeout.connect(func() -> void: changed.emit())
	var title := Label.new()
	title.text = "Face & silhouette"
	add_child(title)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(grid)
	_add_choice(grid, "facial_hair", "Facial hair", ["Clean shaven", "Stubble", "Moustache", "Goatee", "Short beard", "Full beard"])
	_add_choice(grid, "hair_detail", "Hair finish", ["Classic", "Tousled", "Swept"])
	_add_slider(grid, "hair_length", "Hair length", "Shorter", "Longer")
	_add_slider(grid, "hair_volume", "Hair volume", "Close", "Full")
	_add_slider(grid, "jaw", "Jaw width", "Narrow", "Broad")
	_add_slider(grid, "cheekbones", "Cheekbones", "Soft", "Defined")
	_add_slider(grid, "face_length", "Face length", "Shorter", "Longer")
	_add_slider(grid, "nose", "Nose profile", "Delicate", "Strong")
	_add_slider(grid, "nose_width", "Nose width", "Narrow", "Broad")
	_add_slider(grid, "lip_fullness", "Lip fullness", "Fine", "Full")
	_add_slider(grid, "brow_depth", "Brow definition", "Soft", "Strong")
	_add_slider(grid, "eye_size", "Eye size", "Smaller", "Larger")
	_add_slider(grid, "eye_tilt", "Eye angle", "Lower", "Lifted")
	_add_slider(grid, "eye_spacing", "Eye spacing", "Closer", "Wider")
	_add_slider(grid, "height", "Height", "90%", "110%")
	_add_slider(grid, "build", "Body breadth", "85%", "115%")
	var presets := HBoxContainer.new()
	add_child(presets)
	# Keep the starting looks above the longer list of individual controls.
	move_child(presets, 2)
	for preset_name: String in PRESETS.LOOKS:
		var button := Button.new()
		button.text = preset_name
		button.tooltip_text = "Editable face and hair from the Human player studies; keeps your selected sex and class"
		presets.add_child(button)
		button.pressed.connect(func() -> void:
			set_values(PRESETS.shape(preset_name))
			preset_selected.emit(PRESETS.palette(preset_name))
			changed.emit())
	var reset := Button.new()
	reset.text = "Reset shape"
	presets.add_child(reset)
	reset.pressed.connect(func() -> void:
		set_values({})
		changed.emit())
	var hint := Label.new()
	hint.text = "Appearance only. Your movement, reach and equipment stats stay the same."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(hint)

func _label(grid: GridContainer, text: String) -> void:
	var label := Label.new()
	label.text = text
	grid.add_child(label)

func _add_choice(grid: GridContainer, field: String, title: String, entries: Array) -> void:
	_label(grid, title)
	var control := OptionButton.new()
	control.name = field.to_pascal_case()
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for entry: String in entries:
		control.add_item(entry)
	grid.add_child(control)
	controls[field] = control
	control.item_selected.connect(func(_index: int) -> void: changed.emit())

func _add_slider(grid: GridContainer, field: String, title: String, low: String, high: String) -> void:
	_label(grid, title)
	var row := HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(row)
	var slider := HSlider.new()
	slider.name = field.to_pascal_case()
	slider.max_value = 100
	slider.step = 1
	slider.value = 50
	slider.custom_minimum_size.x = 120
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.tooltip_text = low + " — " + high + "; centre keeps the authored proportions"
	row.add_child(slider)
	var readout := Label.new()
	readout.custom_minimum_size.x = 42
	row.add_child(readout)
	controls[field] = slider
	slider.value_changed.connect(func(value: float) -> void:
		readout.text = _readout(field, value)
		_timer.start())
	readout.text = _readout(field, 50)
	slider.set_meta("readout", readout)

func _readout(field: String, value: float) -> String:
	if field == "height":
		return "%d%%" % roundi(90 + value * 0.2)
	if field == "build":
		return "%d%%" % roundi(85 + value * 0.3)
	return str(roundi(value))

func values() -> Dictionary:
	var result := {}
	for field: String in controls:
		var control: Control = controls[field]
		result[field] = (control as OptionButton).selected if control is OptionButton else roundi((control as Range).value)
	return result

func set_values(appearance: Dictionary) -> void:
	var normalized := CUSTOMIZATION.normalized(appearance)
	for field: String in controls:
		var control: Control = controls[field]
		if control is OptionButton:
			(control as OptionButton).select(normalized[field])
		else:
			(control as Range).set_value_no_signal(normalized[field])
			(control.get_meta("readout") as Label).text = _readout(field, normalized[field])
