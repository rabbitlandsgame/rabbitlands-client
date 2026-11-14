extends HBoxContainer
## One location owns the equipment, materials, fees and resulting items.
signal location_changed(location: String)
signal page_changed(offset: int)
var picker: OptionButton
var previous: Button
var next: Button
var page_label: Label
var offset := 0

func _init() -> void:
	picker = OptionButton.new()
	picker.name = "CraftingLocation"
	picker.add_item("Backpack")
	picker.add_item("Storage")
	picker.custom_minimum_size.y = 42
	picker.tooltip_text = "Equipment, materials, gold fees and results use this location."
	add_child(picker)
	picker.item_selected.connect(func(index: int) -> void: location_changed.emit("storage" if index == 1 else "backpack"))
	previous = Button.new()
	previous.text = "‹"
	previous.custom_minimum_size = Vector2(36, 42)
	previous.tooltip_text = "Previous copies"
	add_child(previous)
	previous.pressed.connect(func() -> void: page_changed.emit(maxi(0, offset - 24)))
	page_label = Label.new()
	add_child(page_label)
	next = Button.new()
	next.text = "›"
	next.custom_minimum_size = Vector2(36, 42)
	next.tooltip_text = "More copies"
	add_child(next)
	next.pressed.connect(func() -> void: page_changed.emit(offset + 24))

func render(snapshot: Dictionary, location: String, locked: bool, paging: bool = true) -> void:
	picker.select(1 if location == "storage" else 0)
	picker.disabled = locked
	picker.set_item_disabled(1, not bool(snapshot.get("storage_supported", false)) or not bool(snapshot.get("storage_available", false)))
	picker.set_item_tooltip(1, "Uses stored equipment and materials; results stay in storage. Open storage at a nearby keeper or chest.")
	offset = int(snapshot.get("offset", 0))
	var total := int(snapshot.get("total", 0))
	previous.visible = paging and total > 24
	next.visible = paging and total > 24
	page_label.visible = paging and total > 24
	page_label.text = "%d/%d" % [offset / 24 + 1, ceili(total / 24.0)]
	previous.disabled = locked or offset == 0
	next.disabled = locked or offset + 24 >= total
