extends VBoxContainer
## Eight weightless supply types and a separate coin balance, using server references.
const ItemNames := preload("res://src/state/item_names.gd")
const Chrome := preload("res://src/ui/compact_hud_style.gd")
var main: Control
var heading: Label
var grid: GridContainer
var slots: Array[Button] = []
var counts: Array[Label] = []
var gold: Button
var look_button: Button
var store_button: Button
var drop_button: Button
var selected := -1
var references: Array[int] = []

func configure(owner_main: Control) -> void:
	main = owner_main
	sync()

func _ready() -> void:
	add_theme_constant_override("separation", 3)
	heading = Label.new()
	add_child(heading)
	grid = GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 3)
	grid.add_theme_constant_override("v_separation", 3)
	add_child(grid)
	for index: int in 8:
		var button := Button.new()
		button.expand_icon = true
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.add_theme_constant_override("icon_max_width", 30)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.custom_minimum_size = Vector2(52, 51)
		button.pressed.connect(_select_index.bind(index))
		grid.add_child(button)
		slots.append(button)
		var label := Label.new()
		label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
		label.offset_top = -14
		label.offset_bottom = -1
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		label.add_theme_font_size_override("font_size", 9)
		button.add_child(label)
		counts.append(label)
	gold = Button.new()
	gold.name = "GoldCoins"
	gold.custom_minimum_size.y = 30
	gold.expand_icon = true
	gold.add_theme_constant_override("icon_max_width", 23)
	gold.alignment = HORIZONTAL_ALIGNMENT_LEFT
	gold.pressed.connect(_select.bind(127))
	add_child(gold)
	var actions := HBoxContainer.new()
	add_child(actions)
	look_button = _button(actions, "Look", func() -> void: Network.look_at_inventory_item(selected))
	store_button = _button(actions, "Store", func() -> void: Network.deposit_storage(selected, _quantity()))
	drop_button = _button(actions, "Drop", func() -> void: Network.drop_inventory_item(selected, _quantity()))
	store_button.tooltip_text = "Store the selected pouch item using the inventory quantity."
	drop_button.tooltip_text = "Drop the selected pouch item using the inventory quantity."
	AppState.state_changed.connect(_changed)
	sync()

static func grouped(value: int) -> String:
	var text := str(value)
	var result := ""
	for index: int in text.length():
		if index > 0 and (text.length() - index) % 3 == 0: result += ","
		result += text[index]
	return result

func extent(part: Dictionary, gap: int) -> Vector2:
	return Vector2(maxf(224, part.columns * (part.cell + gap) - gap), 20 + ceili(8.0 / part.columns) * (part.cell + gap) - gap + 60)

func apply_style(config: Dictionary) -> void:
	var part: Dictionary = config.parts.pouch
	grid.columns = part.columns
	grid.add_theme_constant_override("h_separation", config.gap)
	grid.add_theme_constant_override("v_separation", config.gap)
	for index: int in slots.size():
		slots[index].custom_minimum_size = Vector2.ONE * part.cell
		slots[index].add_theme_constant_override("icon_max_width", part.cell - 22)
		counts[index].visible = part.show_quantity
	for button: Button in slots + [gold]:
		button.add_theme_color_override("icon_normal_color", Color(1, 1, 1, part.icon_opacity))
	for button: Button in slots + [gold]:
		Chrome.button(button)
		var active := selected >= 127 and int(button.get_meta("reference", -2)) == selected
		button.add_theme_stylebox_override("normal", Chrome.box(Color("181713"), Color("e2b854") if active else config.border.darkened(0.35), 3))
		button.add_theme_stylebox_override("hover", Chrome.box(Color("30291c"), config.border.lightened(0.3), 3))
		button.add_theme_color_override("font_color", config.text)
	for button: Button in [look_button, store_button, drop_button]: Chrome.button(button)

func _button(parent: Node, caption: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = caption
	button.custom_minimum_size.y = 24
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _quantity() -> int:
	var held := int(AppState.inventory.get(selected, {}).get("quantity", 0))
	return mini(held, int(main._selected_quantity()) if main != null else 1)

func selected_reference() -> int:
	return selected

func _select_index(index: int) -> void:
	if index < references.size(): _select(references[index])

func _select(reference: int) -> void:
	selected = reference
	if main != null:
		main.selected_inventory_slot = reference
		main._describe_slot(reference, false)
		main._sync_inventory()
		main.inventory_workspace.queue_layout()
	_sync_actions()

func _changed(path: StringName) -> void:
	if path in [&"inventory", &"inventory_names", &"storage"]: sync()

func sync() -> void:
	if grid == null: return
	if main != null: selected = main.selected_inventory_slot if main.selected_inventory_slot >= 127 else -1
	references.clear()
	for reference: int in AppState.inventory:
		if reference >= 128 and int(AppState.inventory[reference].get("quantity", 0)) > 0:
			references.append(reference)
	references.sort()
	heading.text = "Pouch · %d/8 types · No load" % references.size()
	for index: int in 8:
		var reference := references[index] if index < references.size() else -1
		var entry: Dictionary = AppState.inventory.get(reference, {})
		var button := slots[index]
		button.set_meta("reference", reference)
		button.disabled = false # Empty slots retain the same visible frame as the backpack.
		button.icon = main.item_atlas.icon_for(int(entry.get("image_id", 0))) if main != null and not entry.is_empty() else null
		counts[index].text = grouped(int(entry.get("quantity", 0))) if not entry.is_empty() else ""
		button.tooltip_text = "%s ×%s" % [ItemNames.display(str(AppState.inventory_names.get(reference, "Reagent"))), counts[index].text] if not entry.is_empty() else "Empty pouch type slot"
	var coins: Dictionary = AppState.inventory.get(127, {})
	gold.set_meta("reference", 127)
	gold.text = "Gold Coins   %s" % grouped(int(coins.get("quantity", 0)))
	gold.disabled = coins.is_empty()
	gold.icon = main.item_atlas.icon_for(int(coins.get("image_id", 0))) if main != null and not coins.is_empty() else null
	gold.tooltip_text = "Dedicated coin slot · No load · Does not use a pouch type"
	if not AppState.inventory.has(selected): selected = -1
	_sync_actions()

func _sync_actions() -> void:
	var held := int(AppState.inventory.get(selected, {}).get("quantity", 0))
	look_button.disabled = held <= 0
	drop_button.disabled = held <= 0
	store_button.disabled = held <= 0 or not AppState.storage.get("open", false) or AppState.storage.get("read_only", false)
