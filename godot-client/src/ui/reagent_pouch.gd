extends AcceptDialog
## Separate supplies list; its item references never occupy the backpack grid.
const ItemNames := preload("res://src/state/item_names.gd")
var supplies: ItemList
var quantity: SpinBox
var store_button: Button
var drop_button: Button
var look_button: Button

func _ready() -> void:
	title = "Reagent pouch"
	get_ok_button().text = "Close"
	min_size = Vector2i(300, 280)
	var column := VBoxContainer.new()
	add_child(column)
	var note := Label.new()
	note.text = "Weightless · No backpack slots"
	column.add_child(note)
	supplies = ItemList.new()
	supplies.name = "PouchSupplies"
	supplies.custom_minimum_size = Vector2(280, 210)
	supplies.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(supplies)
	quantity = SpinBox.new()
	quantity.min_value = 1
	quantity.max_value = 4294967295
	quantity.step = 1
	quantity.prefix = "Quantity "
	column.add_child(quantity)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	look_button = _button(actions, "Look", func() -> void: Network.look_at_inventory_item(selected_reference()))
	store_button = _button(actions, "Store", func() -> void: Network.deposit_storage(selected_reference(), int(quantity.value)))
	drop_button = _button(actions, "Drop", func() -> void: Network.drop_inventory_item(selected_reference(), int(quantity.value)))
	store_button.tooltip_text = "Open storage to deposit pouch supplies."
	supplies.item_selected.connect(func(_index: int) -> void: _sync_actions())
	AppState.state_changed.connect(_changed)
	sync()

func _button(parent: Node, caption: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = caption
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func selected_reference() -> int:
	var selected := supplies.get_selected_items()
	return int(supplies.get_item_metadata(selected[0])) if not selected.is_empty() else -1

func _changed(path: StringName) -> void:
	if path in [&"inventory", &"inventory_names", &"storage"]: sync()

func sync() -> void:
	if supplies == null: return
	var selected := selected_reference()
	supplies.clear()
	var references: Array = AppState.inventory.keys()
	references.sort()
	for reference: int in references:
		if reference < 128: continue
		var entry: Dictionary = AppState.inventory[reference]
		var label := ItemNames.display(str(AppState.inventory_names.get(reference, "Reagent")))
		supplies.add_item("%s ×%s" % [label, str(int(entry.get("quantity", 0)))])
		var index := supplies.item_count - 1
		supplies.set_item_metadata(index, reference)
		if reference == selected: supplies.select(index)
	_sync_actions()

func _sync_actions() -> void:
	var reference := selected_reference()
	var held := int(AppState.inventory.get(reference, {}).get("quantity", 0))
	quantity.max_value = maxi(1, held)
	look_button.disabled = held <= 0
	drop_button.disabled = held <= 0
	store_button.disabled = held <= 0 or not AppState.storage.get("open", false) or AppState.storage.get("read_only", false)
