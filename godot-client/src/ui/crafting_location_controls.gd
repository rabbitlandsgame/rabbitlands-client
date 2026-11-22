extends VBoxContainer
## One location owns the equipment, materials, fees and resulting items.
signal location_changed(location: String)
signal page_changed(offset: int)
var backpack: Button
var storage: Button
var previous: Button
var next: Button
var page_label: Label
var offset := 0
var _location := "backpack"

func _init() -> void:
	var source_row := HBoxContainer.new()
	source_row.add_theme_constant_override("separation", 3)
	add_child(source_row)
	var group := ButtonGroup.new()
	for location: String in ["backpack", "storage"]:
		var button := Button.new()
		button.text = location.capitalize()
		button.toggle_mode = true
		button.button_group = group
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.add_theme_font_size_override("font_size", 11)
		button.custom_minimum_size.y = 26
		button.tooltip_text = "Equipment, materials, gold fees and results use this location."
		source_row.add_child(button)
		if location == "backpack": backpack = button
		else: storage = button
		button.pressed.connect(func() -> void:
			if _location != location: location_changed.emit(location))
	var pages := HBoxContainer.new()
	pages.add_theme_constant_override("separation", 3)
	add_child(pages)
	previous = Button.new()
	previous.text = "‹"
	previous.custom_minimum_size = Vector2(26, 24)
	previous.tooltip_text = "Previous copies"
	pages.add_child(previous)
	previous.pressed.connect(func() -> void: page_changed.emit(maxi(0, offset - 24)))
	page_label = Label.new()
	page_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	pages.add_child(page_label)
	next = Button.new()
	next.text = "›"
	next.custom_minimum_size = Vector2(26, 24)
	next.tooltip_text = "More copies"
	pages.add_child(next)
	next.pressed.connect(func() -> void: page_changed.emit(offset + 24))

func render(snapshot: Dictionary, location: String, locked: bool, paging: bool = true) -> void:
	_location = location
	backpack.set_pressed_no_signal(location == "backpack")
	storage.set_pressed_no_signal(location == "storage")
	backpack.disabled = locked
	storage.disabled = locked or not bool(snapshot.get("storage_supported", false)) or not bool(snapshot.get("storage_available", false))
	storage.tooltip_text = "Uses stored equipment and materials; results stay in storage. Open storage at a nearby keeper or chest."
	offset = int(snapshot.get("offset", 0))
	var total := int(snapshot.get("total", 0))
	previous.visible = paging and total > 24
	next.visible = paging and total > 24
	page_label.visible = paging and total > 24
	page_label.text = "%d/%d" % [offset / 24 + 1, ceili(total / 24.0)]
	previous.disabled = locked or offset == 0
	next.disabled = locked or offset + 24 >= total
