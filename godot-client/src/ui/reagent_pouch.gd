extends Control
## Eight weightless supply types and a separate coin balance, using server references.
const ItemNames := preload("res://src/state/item_names.gd")
const Chrome := preload("res://src/ui/compact_hud_style.gd")
var main: Control
var contents: VBoxContainer
var auxiliary: VBoxContainer
var gold_count: Label
var action_grid: GridContainer
var mix_button: Button
var heading: Label
var grid: GridContainer
var slots: Array[Button] = []
var counts: Array[Label] = []
var gold: Button
var look_button: Button
var store_button: Button
var drop_button: Button
var grab_button: Button
var selected := -1
var references: Array[int] = []

func configure(owner_main: Control) -> void:
	main = owner_main
	# Match the bag with unframed, painted object art for every pouch action.
	grab_button.icon = main._external_texture("res://assets/ui/cursors/cursor_grab.png")
	look_button.icon = main._external_texture("res://assets/ui/cursors/cursor_eye.png")
	store_button.icon = main._external_texture("res://assets/ui/inventory-actions/store-painted.png")
	drop_button.icon = main._external_texture("res://assets/ui/cursors/cursor_pick.png")
	mix_button.icon = main._external_texture("res://assets/ui/inventory-actions/mix-painted.png")
	sync()

func _ready() -> void:
	contents = VBoxContainer.new()
	contents.add_theme_constant_override("separation", 3)
	add_child(contents)
	auxiliary = VBoxContainer.new()
	auxiliary.add_theme_constant_override("separation", 3)
	add_child(auxiliary)
	heading = Label.new()
	contents.add_child(heading)
	grid = GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 3)
	grid.add_theme_constant_override("v_separation", 3)
	contents.add_child(grid)
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
	gold.custom_minimum_size.y = 44
	gold.expand_icon = true
	gold.add_theme_constant_override("icon_max_width", 24)
	gold.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
	gold.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
	gold.pressed.connect(_select.bind(127))
	auxiliary.add_child(gold)
	gold_count = Label.new()
	gold_count.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	gold_count.offset_top = -15
	gold_count.offset_bottom = -1
	gold_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	gold_count.mouse_filter = Control.MOUSE_FILTER_IGNORE
	gold_count.add_theme_font_size_override("font_size", 10)
	gold.add_child(gold_count)
	action_grid = GridContainer.new()
	action_grid.columns = 2
	action_grid.add_theme_constant_override("h_separation", 3)
	action_grid.add_theme_constant_override("v_separation", 3)
	auxiliary.add_child(action_grid)
	look_button = _button(action_grid, "Look · Inspect the selected pouch item", func() -> void: Network.look_at_inventory_item(selected))
	store_button = _button(action_grid, "Store · Deposit the selected quantity; open storage first", func() -> void: Network.deposit_storage(selected, _quantity()))
	drop_button = _button(action_grid, "Bag · Get all from the bag at your feet", _get_bag)
	grab_button = _button(action_grid, "Grab · Click an item to carry it, then storage or the ground to put it down", _grab)
	grab_button.toggle_mode = true
	mix_button = _button(action_grid, "Mix · Open crafting", _open_mix)
	for pair: Array in [[store_button, "store"], [drop_button, "drop"], [mix_button, "mix"]]:
		var button: Button = pair[0]
		button.gui_input.connect(_action_shortcut_input.bind(pair[1], button))
	store_button.tooltip_text = "Store · Left: selected quantity · Right: store all · Middle: protection options"
	drop_button.tooltip_text = "Bag · Left: open the bag at your feet and get all · Right: drop all · Middle: drop protection options"
	mix_button.tooltip_text = "Mix · Left: crafting · Right: mix all · Middle: mixing options"

	AppState.state_changed.connect(_changed)
	sync()

static func grouped(value: int) -> String:
	var text := str(value)
	var result := ""
	for index: int in text.length():
		if index > 0 and (text.length() - index) % 3 == 0: result += ","
		result += text[index]
	return result

func extent(part: Dictionary, gap: int, side_width: float = 75) -> Vector2:
	return Vector2(maxf(224, part.columns * (part.cell + gap) - gap) + maxf(75, side_width) + 10, maxf(149, 20 + ceili(8.0 / part.columns) * (part.cell + gap) - gap))

func apply_style(config: Dictionary, side_width: float = 75, actions_right := false) -> void:
	var part: Dictionary = config.parts.pouch
	var auxiliary_width := maxf(75, side_width)
	var supply_width := size.x - auxiliary_width - 10
	contents.position = Vector2.ZERO if actions_right else Vector2(auxiliary_width + 10, 0)
	contents.size = Vector2(supply_width, size.y)
	auxiliary.position = Vector2(supply_width + 10, 0) if actions_right else Vector2.ZERO
	auxiliary.size = Vector2(auxiliary_width, size.y)
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
	for button: Button in [look_button, store_button, drop_button, mix_button, grab_button]:
		Chrome.button(button)
		if button != drop_button:
			# Give these smaller silhouettes more room inside the same button footprint.
			for state: String in ["normal", "hover", "pressed"]:
				button.get_theme_stylebox(state).set_content_margin_all(3)
		# A disabled action keeps the same frame; the icon still conveys availability.
		button.add_theme_stylebox_override("disabled", button.get_theme_stylebox("normal"))
	# Preserve the chest's warm wood and gold fittings instead of the default heavy fade.
	store_button.add_theme_color_override("icon_disabled_color", Color(1, 1, 1, 0.9))
	gold_count.visible = part.show_quantity
	_sync_actions()

func _button(parent: Node, caption: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = ""
	button.tooltip_text = caption
	button.expand_icon = true
	button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
	button.add_theme_constant_override("icon_max_width", 30)
	button.custom_minimum_size = Vector2(32, 32)
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
		if main._inventory_tool == "grab" and main._carry_enabled():
			if main._storage_carried_position >= 0:
				main._withdraw_storage_carry()
			else:
				main._begin_carry(reference)
		else:
			main._describe_slot(reference, false)
		main._sync_inventory()
		main.inventory_workspace.queue_layout()
	_sync_actions()

func _changed(path: StringName) -> void:
	if path in [&"inventory", &"inventory_names", &"storage", &"trade"]: sync()
	elif path in [&"ground_bags", &"actors"]: _sync_actions()

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
	gold_count.text = grouped(int(coins.get("quantity", 0)))
	gold.disabled = coins.is_empty()
	gold.icon = main.item_atlas.icon_for(int(coins.get("image_id", 0))) if main != null else null
	gold.tooltip_text = "Gold Coins ×%s · No load · Dedicated coin slot" % gold_count.text
	if not AppState.inventory.has(selected): selected = -1
	_sync_actions()

func _get_bag() -> void:
	if main != null and not drop_button.disabled:
		main._on_inventory_get_all_pressed()

func _grab() -> void:
	if main == null or grab_button.disabled: return
	# Arm the tool without lifting the previously selected item.
	main._cancel_carry()
	main._reset_world_action()
	_sync_actions()

func _open_mix() -> void:
	if main != null and not mix_button.disabled:
		main._on_manufacturing_button_pressed()

func _sync_actions() -> void:
	var editing: bool = main != null and main.inventory_workspace != null and main.inventory_workspace.is_editing()
	var held := int(AppState.inventory.get(selected, {}).get("quantity", 0))
	look_button.disabled = held <= 0 or editing
	drop_button.disabled = main == null or editing or main._ground_bag_below_player() < 0
	grab_button.disabled = main == null or editing
	grab_button.set_pressed_no_signal(main != null and main._inventory_tool == "grab" and main._carry_enabled())
	store_button.disabled = held <= 0 or editing or not AppState.storage.get("open", false) or AppState.storage.get("read_only", false)
	mix_button.disabled = main == null or editing or AppState.trade.get("open", false) or AppState.storage.get("open", false)

func _action_shortcut_input(event: InputEvent, action: String, button: Button) -> void:
	if main == null or main.inventory_workspace == null: return
	main.inventory_workspace.bulk_actions.shortcut_input(event, action, button)
