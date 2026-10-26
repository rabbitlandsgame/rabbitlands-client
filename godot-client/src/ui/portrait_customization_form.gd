extends VBoxContainer
## The same controls drive creation and the existing-player dressing room.

signal changed
signal preset_selected(appearance: Dictionary)
const CUSTOMIZATION = preload("res://src/actors/portrait_customization.gd")
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
	_add_slider(grid, "jaw", "Jaw width", "Narrow", "Broad")
	_add_slider(grid, "cheekbones", "Cheekbones", "Soft", "Defined")
	_add_slider(grid, "nose", "Nose profile", "Delicate", "Strong")
	_add_slider(grid, "height", "Height", "90%", "110%")
	_add_slider(grid, "build", "Body breadth", "85%", "115%")
	var presets := HBoxContainer.new()
	add_child(presets)
	for entry: Dictionary in [
		{"label": "Rowan", "facial_hair": 0, "jaw": 60, "cheekbones": 65, "nose": 45, "height": 55, "build": 48, "hair_detail": 1},
		{"label": "Mira", "facial_hair": 0, "jaw": 35, "cheekbones": 70, "nose": 35, "height": 50, "build": 38, "hair_detail": 2},
		{"label": "Tavi", "facial_hair": 5, "jaw": 80, "cheekbones": 60, "nose": 70, "height": 62, "build": 78, "hair_detail": 2}]:
		var button := Button.new()
		button.text = entry.label
		button.tooltip_text = "Face and silhouette inspired by the leaderboard portrait"
		presets.add_child(button)
		button.pressed.connect(func() -> void:
			set_values(entry)
			var palette := {"Rowan": [1, 1, 2, 2], "Mira": [3, 4, 1, 1], "Tavi": [1, 1, 3, 2]}
			var look: Array = palette[entry.label]
			preset_selected.emit({"hair": AppearanceVariants.pack_hair(look[0], look[1]), "eyes": look[2], "skin": look[3]})
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
