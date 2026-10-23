class_name ClassicStorageWorkspace
extends Node
## Classic storage and named favorite sets share the existing server state.
## Docking temporarily groups the real inventory, preserving its tools.

const BACKGROUND := Color("05090a")
const AMBER := Color("896234")
const GOLD := Color("e9bd83")
const CELL := 40
const INVENTORY_ICON_MARGIN := 4
const STORAGE_SIZE := Vector2(CELL * 6 + 134, CELL * 6 + 158)

var main: Node
var bank: PanelContainer
var inventory: Control
var lists: PanelContainer
var body: Control
var storage_content: VBoxContainer
var list_content: VBoxContainer
var storage_grid: GridContainer
var _transfer_buttons: Array[Button] = []
var favorite_grid: GridContainer
var filter: LineEdit
var description: Label
var list_status: Label
var list_names: ItemList
var list_name: LineEdit
var entry_name: Label
var entry_quantity: SpinBox
var entry_remove: Button
var layout_menu: PopupMenu
var add_menu: PopupMenu
var favorite_menu: PopupMenu
var entry_editor: HBoxContainer
var active_list := ""
var docked := false
var _open := false
var _attached := false
var _inventory_parent: Node
var _inventory_z_index := 20
var _bank_dragger: WindowDrag
var _inventory_position := Vector2.ZERO
var _inventory_was_visible := false
var _selected_position := -1
var _selected_entry := -1
var _category_id := -1
var _updating := false
var _fitting_lists := false
var _pending_withdrawals: Dictionary = {}
## One frame style for every cell and one for a lit cell, shared rather than
## six new StyleBoxFlat per cell per refresh.
var _plain_cell: StyleBoxFlat
var _lit_cell: StyleBoxFlat
## The storage cell showing each stored position, so a selection restyles two
## cells instead of refreshing the grid.
var _storage_cells: Dictionary = {}

func configure(owner_main: Node) -> void:
	main = owner_main
	_plain_cell = style_box(AMBER, 0)
	_lit_cell = style_box(Color("7cc6d4"), 0)
	bank = main.get("storage_panel") as PanelContainer
	inventory = main.get("inventory_panel") as Control
	lists = main.get("item_lists_panel") as PanelContainer
	main.set("_item_lists", SavedItemLists.normalize(main.get("_item_lists") as Dictionary))
	var config := ConfigFile.new()
	if config.load(main.get("SETTINGS_PATH")) == OK:
		docked = bool(config.get_value("storage", "docked", false))
		active_list = str(config.get_value("storage", "active_list", ""))
	_build_bank()
	_build_lists()
	_style_inventory()
	if config.has_section_key("storage", "position"):
		var stored_position: Variant = config.get_value("storage", "position")
		if stored_position is Vector2:
			bank.position = stored_position as Vector2
	refresh_favorites()
	get_viewport().size_changed.connect(_viewport_changed)

static func style_box(border: Color = AMBER, margin: float = 2) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = BACKGROUND
	style.border_color = border
	style.set_border_width_all(1)
	style.set_content_margin_all(margin)
	return style

static func classic_theme() -> Theme:
	var result := Theme.new()
	result.default_font_size = 13
	result.set_stylebox("panel", "PanelContainer", style_box())
	for kind: String in ["Button", "LineEdit", "SpinBox", "ItemList"]:
		result.set_stylebox("normal" if kind != "ItemList" else "panel", kind, style_box())
		result.set_color("font_color", kind, GOLD)
	var highlight: StyleBoxFlat = style_box(Color("7cc6d4"))
	highlight.bg_color = Color("172326")
	result.set_stylebox("disabled", "Button", style_box())
	result.set_color("font_disabled_color", "Button", Color("737979"))
	for state: String in ["hover", "pressed", "hover_pressed", "focus"]:
		result.set_stylebox(state, "Button", highlight)
	result.set_stylebox("selected", "ItemList", highlight)
	result.set_stylebox("selected_focus", "ItemList", highlight)
	result.set_color("font_selected_color", "ItemList", Color("7cc6d4"))
	result.set_color("font_color", "Label", GOLD)
	result.set_constant("separation", "VBoxContainer", 4)
	result.set_constant("separation", "HBoxContainer", 4)
	return result

func _build_bank() -> void:
	(bank.get_node("Content") as Control).hide()
	bank.theme = classic_theme()
	bank.add_theme_stylebox_override("panel", style_box(Color("171b1c"), 4))
	bank.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	bank.position = Vector2(30, 90)
	body = Control.new()
	body.name = "ClassicWorkspace"
	body.custom_minimum_size = STORAGE_SIZE
	bank.add_child(body)
	storage_content = VBoxContainer.new()
	storage_content.name = "ClassicStorage"
	storage_content.position = Vector2.ZERO
	storage_content.size = STORAGE_SIZE
	body.add_child(storage_content)
	var header := ClassicTitle.new("Storage")
	header.name = "ClassicHeader"
	storage_content.add_child(header)
	_button(header, "×", _close_bank, "Close storage")
	_bank_dragger = WindowDrag.attach(bank, header)
	_bank_dragger.moved.connect(func(_position: Vector2) -> void: persist())
	header.gui_input.connect(_layout_input.bind(header))
	bank.gui_input.connect(_layout_input.bind(bank))
	var columns := HBoxContainer.new()
	storage_content.add_child(columns)
	var categories: ItemList = main.get("storage_categories") as ItemList
	categories.reparent(columns)
	categories.custom_minimum_size = Vector2(112, CELL * 6)
	categories.size_flags_vertical = Control.SIZE_EXPAND_FILL
	categories.add_theme_constant_override("v_separation", 1)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(CELL * 6 + 14, CELL * 6)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	columns.add_child(scroll)
	storage_grid = GridContainer.new()
	storage_grid.name = "StorageGrid"
	storage_grid.columns = 6
	storage_grid.add_theme_constant_override("h_separation", 0)
	storage_grid.add_theme_constant_override("v_separation", 0)
	scroll.add_child(storage_grid)
	filter = LineEdit.new()
	filter.placeholder_text = "Type to filter items…"
	filter.clear_button_enabled = true
	filter.text_changed.connect(func(_text: String) -> void: _refresh_grid())
	storage_content.add_child(filter)
	var organizers := HBoxContainer.new()
	storage_content.add_child(organizers)
	for selector: Control in [main.get("storage_type"), main.get("storage_sort")]:
		selector.reparent(organizers)
		selector.custom_minimum_size = Vector2.ZERO
		selector.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	description = Label.new()
	description.name = "StorageDescription"
	description.custom_minimum_size = Vector2(0, 36)
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	description.add_theme_stylebox_override("normal", style_box(AMBER, 4))
	description.size_flags_vertical = Control.SIZE_EXPAND_FILL
	storage_content.add_child(description)
	var actions := HBoxContainer.new()
	storage_content.add_child(actions)
	_transfer_buttons.append(_button(actions, "Withdraw", withdraw_selected, "Withdraw the selected quantity; double-click an item to withdraw"))
	_transfer_buttons.append(_button(actions, "Deposit", deposit_selected, "Deposit the selected inventory item using the quantity shortcuts"))
	_button(actions, "Look", inspect_selected, "Ask for the selected stored item's description")
	_button(actions, "+ List", add_selected_storage, "Add the selected stored item to the active favorite list")
	_button(actions, "⋮", _popup_layout, "Storage layout; also available by right-clicking the title")
	layout_menu = PopupMenu.new()
	layout_menu.name = "StorageLayoutMenu"
	layout_menu.add_radio_check_item("Faithful classic", 0)
	layout_menu.add_radio_check_item("Docked bank", 1)
	layout_menu.id_pressed.connect(func(id: int) -> void: set_docked(id == 1))
	add_child(layout_menu)
	bank.size = STORAGE_SIZE + Vector2(8, 8)

func _build_lists() -> void:
	(lists.get_node("Content") as Control).hide()
	lists.theme = classic_theme()
	lists.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	lists.add_theme_stylebox_override("panel", style_box(Color("171b1c"), 4))
	list_content = VBoxContainer.new()
	list_content.name = "ClassicItemLists"
	list_content.custom_minimum_size = Vector2(CELL * 6 + 30, 340)
	lists.add_child(list_content)
	var header := ClassicTitle.new("Item lists")
	list_content.add_child(header)
	_button(header, "×", func() -> void: lists.hide(), "Close item lists")
	WindowDrag.attach(lists, header)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0, CELL * 3)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	list_content.add_child(scroll)
	favorite_grid = GridContainer.new()
	favorite_grid.name = "FavoritesGrid"
	favorite_grid.columns = 6
	favorite_grid.add_theme_constant_override("h_separation", 0)
	favorite_grid.add_theme_constant_override("v_separation", 0)
	scroll.add_child(favorite_grid)
	var actions := HBoxContainer.new()
	list_content.add_child(actions)
	_button(actions, "+", _popup_add, "Add a selected item, or capture your backpack")
	_button(actions, "New list", create_list, "Create a new favorite set")
	_transfer_buttons.append(_button(actions, "Get list", collect_list, "Top up the list's quantities from the open storage category"))
	list_names = main.get("saved_item_lists") as ItemList
	list_names.reparent(list_content)
	list_names.custom_minimum_size = Vector2(0, 95)
	list_names.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list_names.allow_reselect = true
	list_names.tooltip_text = "Click a name to instantly switch your favorite set"
	var naming := HBoxContainer.new()
	list_content.add_child(naming)
	list_name = main.get("item_list_name") as LineEdit
	list_name.reparent(naming)
	list_name.max_length = 48
	list_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list_name.text_submitted.connect(func(_text: String) -> void: rename_list())
	_button(naming, "Rename", rename_list, "Rename the active list")
	_button(naming, "×", delete_list, "Delete the active favorite set")
	entry_name = Label.new()
	entry_name.clip_text = true
	entry_name.text = "Select an item to edit its quantity"
	list_content.add_child(entry_name)
	entry_editor = HBoxContainer.new()
	list_content.add_child(entry_editor)
	var quantity_caption := Label.new()
	quantity_caption.text = "Quantity"
	entry_editor.add_child(quantity_caption)
	entry_quantity = SpinBox.new()
	entry_quantity.min_value = 1
	entry_quantity.max_value = 9999999
	entry_quantity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	entry_quantity.value_changed.connect(_change_entry_quantity)
	entry_editor.add_child(entry_quantity)
	entry_remove = _button(entry_editor, "Remove", remove_entry, "Remove the selected favorite")
	list_status = main.get("item_list_status") as Label
	list_status.reparent(list_content)
	list_status.custom_minimum_size.y = 30
	list_status.text = "Create a list, then add items with +."
	add_menu = PopupMenu.new()
	add_menu.add_item("Add selected stored item", 0)
	add_menu.add_item("Add selected inventory item", 1)
	add_menu.add_item("Add all backpack items", 2)
	add_menu.id_pressed.connect(_on_add_menu)
	add_child(add_menu)
	favorite_menu = PopupMenu.new()
	favorite_menu.add_item("Edit quantity", 0)
	favorite_menu.add_item("Remove from list", 1)
	favorite_menu.id_pressed.connect(func(id: int) -> void:
		if id == 1:
			remove_entry()
		else:
			entry_quantity.get_line_edit().grab_focus()
			entry_quantity.get_line_edit().select_all())
	add_child(favorite_menu)
	lists.size = Vector2(254, 410)
	lists.position = Vector2(770, 90)
	_fit_lists.call_deferred()

func _button(parent: Node, text: String, action: Callable, tooltip: String) -> Button:
	var button := Button.new()
	button.text = text
	button.tooltip_text = tooltip
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _style_inventory() -> void:
	inventory.theme = classic_theme()
	inventory.add_theme_stylebox_override("panel", style_box(Color("171b1c"), 4))
	var title: Label = inventory.get_node("Content/Header/Title") as Label
	title.text = ""
	var rail := ClassicTitle.new("Inventory")
	rail.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title.add_child(rail)
	rail.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# Leave a visible gutter inside the grid even when expand_icon fills the
	# content rectangle. Use the same inset in every state to avoid icon jumps.
	var pack_cell: StyleBoxFlat = style_box(AMBER, INVENTORY_ICON_MARGIN)
	var worn_cell: StyleBoxFlat = style_box(Color("6d854e"), INVENTORY_ICON_MARGIN)
	var active_cell: StyleBoxFlat = style_box(Color("7cc6d4"), INVENTORY_ICON_MARGIN)
	for grid: GridContainer in [main.get("inventory_grid"), main.get("equipment_grid")]:
		grid.add_theme_constant_override("h_separation", 0)
		grid.add_theme_constant_override("v_separation", 0)
		for slot: Button in grid.get_children():
			slot.custom_minimum_size = Vector2(CELL, CELL)
			slot.add_theme_stylebox_override("normal",
				worn_cell if grid == main.get("equipment_grid") else pack_cell)
			slot.add_theme_stylebox_override("disabled",
				worn_cell if grid == main.get("equipment_grid") else pack_cell)
			for state: String in ["hover", "pressed", "hover_pressed", "focus"]:
				slot.add_theme_stylebox_override(state, active_cell)
	var equipment: Control = main.get("equipment_column") as Control
	for quantity: Label in main.get("inventory_quantity_labels"):
		quantity.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
		quantity.offset_left = 1
		quantity.offset_top = 0
		quantity.offset_right = -1
		quantity.offset_bottom = 14
		quantity.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
		quantity.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	equipment.custom_minimum_size.x = CELL * 2
	var equipment_title: Label = equipment.get_node("EquipmentTitle") as Label
	equipment_title.text = "Equipment"
	equipment_title.add_theme_color_override("font_color", Color("6d854e"))
	var pack: Control = inventory.get_node("Content/InventoryBody/BackpackColumn") as Control
	(pack.get_node("Scroll") as Control).custom_minimum_size = Vector2(CELL * 6, CELL * 6)
	var short_description: Control = main.get("inventory_description") as Control
	short_description.custom_minimum_size = Vector2(CELL * 6, 34)
	# Item replies scroll inside the status area rather than growing the window.
	(short_description as RichTextLabel).fit_content = false
	(short_description as RichTextLabel).scroll_active = true
	var side: Control = inventory.get_node("Content/InventoryBody/SideActions") as Control
	side.custom_minimum_size.x = 34
	(inventory.get_node("Content/Header/InventoryClose") as Control).custom_minimum_size = Vector2(22, 22)
	(main.get("inventory_resize_grip") as Control).custom_minimum_size = Vector2(20, 20)
	(main.get("inventory_item_lists") as Button).tooltip_text = "Switch or create named favorite sets"
	for pair: Array in [["inventory_use_button", "Use"], ["inventory_equip_button", "Wear"],
			["inventory_unequip_button", "Off"], ["inventory_inspect_button", "Look"]]:
		(main.get(str(pair[0])) as Button).text = str(pair[1])
	for shortcut: Button in main.get("inventory_quantity_buttons"):
		shortcut.custom_minimum_size.y = 20
		shortcut.add_theme_color_override("font_color", Color("78a7ff"))
		shortcut.add_theme_color_override("font_pressed_color", Color("6cdf7b"))
		shortcut.add_theme_stylebox_override("normal", style_box(Color("4275b8"), 0))
	# This editor floats over a shortcut; it must not add a row to the layout.
	var quantity_edit: Control = main.get("inventory_quantity_edit") as Control
	quantity_edit.set_as_top_level(true)
	quantity_edit.z_as_relative = false
	quantity_edit.z_index = 31
	inventory.reset_size()

func refresh() -> void:
	for button: Button in _transfer_buttons:
		button.disabled = bool(AppState.storage.get("read_only", false))
	var is_open: bool = (bool(AppState.storage.get("open", false))
		and not bool(AppState.trade.get("open", false)))
	if is_open != _open:
		_open = is_open
		if is_open:
			_inventory_was_visible = inventory.visible
			_inventory_position = inventory.position
			inventory.show()
			if docked:
				_attach_inventory()
			else:
				_place_inventory_beside_bank()
		else:
			_pending_withdrawals.clear()
			_detach_inventory()
			if not _inventory_was_visible:
				inventory.hide()
	if not is_open:
		return
	var category_id: int = int(AppState.storage.get("category_id", -1))
	if category_id != _category_id:
		_category_id = category_id
		_selected_position = -1
	_refresh_grid()
	if docked:
		layout_dock()
	refresh_favorites()

## Grid cells are built once and refilled in place. Freeing and rebuilding them
## for every server reply cost about half a millisecond a cell - a tenth of a
## second for a full category, three times per deposit - and freed the very
## button a click was still pressing, which lost the click.
func _grid_cell(grid: GridContainer, index: int, on_pressed: Callable, on_input: Callable) -> Button:
	while grid.get_child_count() <= index:
		var cell := Button.new()
		cell.custom_minimum_size = Vector2(CELL, CELL)
		cell.focus_mode = Control.FOCUS_NONE
		# Acted on at the press, as the reference client does.
		cell.action_mode = BaseButton.ACTION_MODE_BUTTON_PRESS
		cell.expand_icon = true
		cell.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cell.add_theme_stylebox_override("normal", _plain_cell)
		cell.add_theme_stylebox_override("disabled", _plain_cell)
		for state: String in ["hover", "pressed", "hover_pressed", "focus"]:
			cell.add_theme_stylebox_override(state, _plain_cell)
		cell.set_meta("filled", false)
		# Matches nothing a refresh shows, so the first refresh fills it.
		cell.set_meta("shown", [-1])
		var count := Label.new()
		count.name = "Count"
		count.mouse_filter = Control.MOUSE_FILTER_IGNORE
		count.position = Vector2(1, 0)
		count.add_theme_font_size_override("font_size", 10)
		count.add_theme_color_override("font_color", Color.WHITE)
		count.add_theme_color_override("font_outline_color", Color.BLACK)
		count.add_theme_constant_override("outline_size", 2)
		cell.add_child(count)
		var cell_index: int = grid.get_child_count()
		cell.pressed.connect(on_pressed.bind(cell_index))
		cell.gui_input.connect(on_input.bind(cell_index))
		grid.add_child(cell)
	var found: Button = grid.get_child(index) as Button
	found.visible = true
	return found

## Writes one cell's item, or empties it. An empty cell stays enabled, because
## a click anywhere on the storage grid deposits the item in hand, but it does
## not light up under the pointer.
func _fill_cell(cell: Button, entry: Dictionary, item_name: String, tooltip: String) -> void:
	var count: Label = cell.get_child(0) as Label
	cell.tooltip_text = tooltip
	var filled: bool = not entry.is_empty()
	if filled:
		cell.icon = crop_icon(main.call("_named_icon", int(entry.get("image_id", 0)), item_name) as Texture2D)
		var text: String = str(int(entry.get("quantity", 0)))
		if count.text != text:
			count.text = text
			count.add_theme_font_size_override("font_size", 10 if text.length() < 5 else 8)
	else:
		cell.icon = null
		count.text = ""
	if bool(cell.get_meta("filled", false)) != filled:
		cell.set_meta("filled", filled)
		for state: String in ["hover", "pressed", "hover_pressed", "focus"]:
			cell.add_theme_stylebox_override(state, _lit_cell if filled else _plain_cell)

func _light_cell(cell: Button, lit: bool) -> void:
	if bool(cell.get_meta("lit", false)) == lit:
		return
	cell.set_meta("lit", lit)
	cell.add_theme_stylebox_override("normal", _lit_cell if lit else _plain_cell)

func _hide_cells_from(grid: GridContainer, first: int) -> void:
	for index: int in range(first, grid.get_child_count()):
		var cell: Button = grid.get_child(index) as Button
		cell.visible = false
		cell.set_meta("storage_position", -1)

func crop_icon(texture: Texture2D) -> Texture2D:
	# The atlas now contains unframed artwork. Preserve the complete item and
	# worn marker; button content margins provide the space inside the grid.
	return texture

func _refresh_grid() -> void:
	var adapter: ItemList = main.get("storage_items") as ItemList
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	var described: Dictionary = AppState.storage.get("described", {}) as Dictionary
	var needle: String = filter.text.to_lower()
	var used := 0
	_storage_cells.clear()
	if _stock_ready():
		for index: int in range(adapter.item_count):
			var position: int = int(adapter.get_item_metadata(index))
			var entry: Dictionary = items.get(position, {}) as Dictionary
			var row: Variant = described.get(position)
			var name: String = str((row as Dictionary).get("name", "")) if row is Dictionary else ""
			if name.is_empty():
				name = "Item #%d" % int(entry.get("image_id", 0))
			if not needle.is_empty() and not name.to_lower().contains(needle):
				continue
			var cell: Button = _grid_cell(storage_grid, used, _on_storage_cell_pressed, _storage_cell_input)
			used += 1
			cell.set_meta("storage_position", position)
			# A reply usually changes one stack; the rest are left as drawn.
			var shown: Array = [int(entry.get("image_id", 0)), int(entry.get("quantity", 0)),
				name, AppState.is_degraded_item(name)]
			if cell.get_meta("shown", []) != shown:
				cell.set_meta("shown", shown)
				_fill_cell(cell, entry, name,
					"%s ×%d\nClick: carry to the backpack · Double-click: withdraw · Right-click: select"
					% [name, int(entry.get("quantity", 0))])
			_light_cell(cell, position == _selected_position)
			_storage_cells[position] = cell
	var total: int = maxi(36, ceili(used / 6.0) * 6)
	for index: int in range(used, total):
		var empty: Button = _grid_cell(storage_grid, index, _on_storage_cell_pressed, _storage_cell_input)
		empty.set_meta("storage_position", -1)
		if not (empty.get_meta("shown", []) as Array).is_empty():
			empty.set_meta("shown", [])
			_fill_cell(empty, {}, "", "Empty slot")
		_light_cell(empty, false)
	_hide_cells_from(storage_grid, total)
	if not _storage_cells.has(_selected_position):
		_selected_position = -1
	_describe_selection()

func _describe_selection() -> void:
	if bool(AppState.storage.get("read_only", false)):
		description.text = "Storage preview · View only. Visit a storage keeper or chest to transfer items."
		return
	if not _stock_ready():
		description.text = "Loading category…"
		return
	var server_text: String = str(AppState.storage.get("text", ""))
	description.text = server_text if not server_text.is_empty() else (
		str(main.call("_storage_name_of", _selected_position)) if _storage_cells.has(_selected_position)
		else "Click an item to carry it to the backpack · Double-click to withdraw")

func _stock_ready() -> bool:
	return bool(main.call("_storage_stock_ready"))

## Selecting restyles the old cell and the new one; nothing is rebuilt.
func _select_storage(position: int) -> void:
	var previous: Button = _storage_cells.get(_selected_position) as Button
	if previous != null:
		_light_cell(previous, false)
	_selected_position = position
	var current: Button = _storage_cells.get(position) as Button
	if current != null:
		_light_cell(current, true)
	var adapter: ItemList = main.get("storage_items") as ItemList
	for index: int in range(adapter.item_count):
		if int(adapter.get_item_metadata(index)) == position:
			adapter.select(index)
			main.call("_on_storage_item_selected", index)
			break
	_describe_selection()

## A left click on the grid, taken at the press as in the reference client.
## With a backpack item in hand any cell deposits the selected quantity, and
## the item stays in hand until the stack runs out. Otherwise the stored item
## is selected and lifted onto the cursor, to be withdrawn by clicking the
## backpack.
func _on_storage_cell_pressed(cell_index: int) -> void:
	var position: int = int(storage_grid.get_child(cell_index).get_meta("storage_position", -1))
	if bool(AppState.storage.get("read_only", false)):
		if position >= 0: _select_storage(position)
		return
	if int(main.get("_carried_slot")) >= 0:
		main.call("_deposit_carry")
		return
	if position < 0:
		return
	_select_storage(position)
	main.call("_begin_storage_carry", position)

func _storage_cell_input(event: InputEvent, cell_index: int) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse := event as InputEventMouseButton
	if not mouse.pressed:
		return
	var cell: Button = storage_grid.get_child(cell_index) as Button
	var position: int = int(cell.get_meta("storage_position", -1))
	if mouse.button_index == MOUSE_BUTTON_RIGHT:
		# Whatever is in hand goes back first; an empty hand selects the item
		# and updates its description.
		if bool(main.call("_has_carry")):
			main.call("_cancel_carry")
		elif position >= 0:
			_select_storage(position)
		cell.accept_event()
	elif (mouse.button_index == MOUSE_BUTTON_LEFT and mouse.double_click and position >= 0
			and int(main.get("_carried_slot")) < 0):
		# A double click withdraws at once. Its first click lifted the stack,
		# and the second is not another pick-up, so the hand empties.
		_select_storage(position)
		main.call("_cancel_carry")
		withdraw_selected()
		cell.accept_event()

func withdraw_selected() -> void:
	if not _stock_ready():
		return
	var item: Dictionary = (AppState.storage.get("items", {}) as Dictionary).get(_selected_position, {}) as Dictionary
	if item.is_empty():
		description.text = "Select a stored item first."
		return
	var quantity: int = mini(int(main.call("_selected_quantity")), int(item.get("quantity", 0)))
	var error: Error = Network.withdraw_storage(_selected_position, quantity)
	description.text = "Requested %d." % quantity if error == OK else "Could not withdraw: " + error_string(error)

func deposit_selected() -> void:
	var slot: int = int(main.get("selected_inventory_slot"))
	var item: Dictionary = AppState.inventory.get(slot, {}) as Dictionary
	if slot < 0 or slot >= 36 or item.is_empty():
		description.text = "Select a backpack item first."
		return
	var quantity: int = mini(int(main.call("_selected_quantity")), int(item.get("quantity", 0)))
	var error: Error = Network.deposit_storage(slot, quantity)
	if error == OK:
		main.call("_cancel_carry")
	description.text = "Requested deposit of %d." % quantity if error == OK else "Could not deposit: " + error_string(error)

func inspect_selected() -> void:
	if not _stock_ready() or _selected_position < 0:
		description.text = "Select a stored item first."
		return
	var error: Error = Network.look_at_storage_item(_selected_position)
	if error != OK:
		description.text = "Could not inspect: " + error_string(error)

func show_lists() -> void:
	refresh_favorites()
	lists.show()
	lists.move_to_front()
	_clamp_lists()

func _fit_lists() -> void:
	if _fitting_lists:
		return
	_fitting_lists = true
	# Reparented scene controls settle their minimum sizes after layout.
	await get_tree().process_frame
	await get_tree().process_frame
	lists.size = list_content.get_combined_minimum_size() + Vector2(8, 8)
	_clamp_lists()
	_fitting_lists = false

func _all_lists() -> Dictionary:
	return main.get("_item_lists") as Dictionary

func entries() -> Array:
	return _all_lists().get(active_list, []) as Array

func refresh_favorites() -> void:
	if list_names == null:
		return
	var names: Array = _all_lists().keys()
	names.sort_custom(func(a: Variant, b: Variant) -> bool: return str(a).naturalnocasecmp_to(str(b)) < 0)
	var previous_active: String = active_list
	if not names.has(active_list):
		active_list = str(names[0]) if not names.is_empty() else ""
	list_names.clear()
	for list_title: String in names:
		var index: int = list_names.item_count
		list_names.add_item(list_title)
		list_names.set_item_metadata(index, list_title)
		if list_title == active_list:
			list_names.select(index)
	if not list_name.has_focus() or previous_active != active_list:
		list_name.text = active_list
	var current: Array = entries()
	var total: int = maxi(18, ceili(current.size() / 6.0) * 6)
	for index: int in range(total):
		var cell: Button = _grid_cell(favorite_grid, index, _select_entry, _favorite_input)
		if index < current.size():
			var entry: Dictionary = current[index] as Dictionary
			_fill_cell(cell, entry, str(entry.get("name", "")),
				"%s ×%d\nDouble-click: get item · Right-click: edit or remove"
				% [_entry_label(entry), int(entry.get("quantity", 1))])
			_light_cell(cell, index == _selected_entry)
		else:
			_fill_cell(cell, {}, "", "Empty slot")
			_light_cell(cell, false)
	_hide_cells_from(favorite_grid, total)
	_update_editor()

func activate_list(list_title: String) -> void:
	if not _all_lists().has(list_title):
		return
	active_list = list_title
	list_name.text = list_title
	_selected_entry = -1
	refresh_favorites()
	list_status.text = "Active: %s" % active_list
	persist()

func create_list() -> void:
	var number := 1
	var title := "New list"
	while _all_lists().has(title):
		number += 1
		title = "New list %d" % number
	_all_lists()[title] = []
	activate_list(title)
	list_name.grab_focus()
	list_name.select_all()
	list_status.text = "Name your list, then add items with +."

func rename_list() -> void:
	var title: String = list_name.text.strip_edges()
	if title.is_empty() or active_list.is_empty():
		list_status.text = "Create a list and give it a name."
		return
	if title != active_list and _all_lists().has(title):
		list_status.text = "A list with that name already exists."
		return
	var saved_entries: Array = entries()
	_all_lists().erase(active_list)
	_all_lists()[title] = saved_entries
	activate_list(title)

func delete_list() -> void:
	if _all_lists().erase(active_list):
		active_list = ""
		_selected_entry = -1
		refresh_favorites()
		persist()
		list_status.text = "List deleted."

func add_selected_storage() -> void:
	if not _stock_ready():
		return
	var item: Dictionary = (AppState.storage.get("items", {}) as Dictionary).get(_selected_position, {}) as Dictionary
	if item.is_empty():
		show_lists()
		list_status.text = "Select a stored item first."
		return
	var entry: Dictionary = item.duplicate()
	entry["name"] = str(main.call("_storage_name_of", _selected_position))
	entry["category_id"] = int(AppState.storage.get("category_id", -1))
	entry["quantity"] = int(main.call("_selected_quantity"))
	_add_entry(entry)

func add_inventory_slot(slot: int, capture_quantity: bool = false) -> void:
	var item: Dictionary = AppState.inventory.get(slot, {}) as Dictionary
	if slot < 0 or slot >= 36 or item.is_empty():
		list_status.text = "Select a backpack item first."
		return
	var entry: Dictionary = item.duplicate()
	entry["name"] = str(AppState.inventory_names.get(slot, ""))
	entry["category_id"] = -1
	entry["quantity"] = int(item.get("quantity", 1)) if capture_quantity else int(main.call("_selected_quantity"))
	_add_entry(entry)

func _add_entry(entry: Dictionary) -> void:
	if str(entry.get("name", "")).is_empty():
		list_status.text = "Inspect this item first so its name can be saved."
		return
	if active_list.is_empty():
		create_list()
	entry["quantity"] = clampi(int(entry.get("quantity", 1)), 1, 9999999)
	var current: Array = entries()
	var existing_index := -1
	for index: int in range(current.size()):
		if SavedItemLists.same_item(current[index] as Dictionary, entry):
			existing_index = index
			break
	if existing_index < 0:
		current.append(entry)
		_selected_entry = current.size() - 1
	else:
		if int(entry.get("category_id", -1)) < 0:
			entry["category_id"] = int((current[existing_index] as Dictionary).get("category_id", -1))
		current[existing_index] = entry
		_selected_entry = existing_index
	refresh_favorites()
	persist()
	show_lists()
	list_status.text = "Added %s to %s." % [_entry_label(entry), active_list]

func _on_add_menu(id: int) -> void:
	match id:
		0: add_selected_storage()
		1: add_inventory_slot(int(main.get("selected_inventory_slot")))
		2:
			var captured: Dictionary = {}
			for slot: int in range(36):
				if not AppState.inventory.has(slot):
					continue
				var item: Dictionary = AppState.inventory[slot] as Dictionary
				var item_name: String = str(AppState.inventory_names.get(slot, ""))
				if item_name.is_empty():
					continue
				var key: String = "%d:%s" % [int(item.get("image_id", -1)), item_name.to_lower()]
				if not captured.has(key):
					captured[key] = {"image_id": int(item.get("image_id", 0)),
						"name": item_name, "quantity": 0, "category_id": -1}
				(captured[key] as Dictionary)["quantity"] += int(item.get("quantity", 0))
			for entry: Dictionary in captured.values():
				_add_entry(entry)
			if captured.is_empty():
				list_status.text = "Your backpack has no named items to add."

func _select_entry(index: int) -> void:
	if index >= entries().size():
		return
	_selected_entry = index
	refresh_favorites()

func _update_editor() -> void:
	var current: Array = entries()
	var valid: bool = _selected_entry >= 0 and _selected_entry < current.size()
	entry_editor.visible = valid
	_fit_lists.call_deferred()
	entry_name.text = _entry_label(current[_selected_entry]) if valid else "Select an item to edit its quantity"
	if valid:
		_updating = true
		entry_quantity.value = int((current[_selected_entry] as Dictionary).get("quantity", 1))
		_updating = false

func _change_entry_quantity(value: float) -> void:
	if _updating or _selected_entry < 0 or _selected_entry >= entries().size():
		return
	(entries()[_selected_entry] as Dictionary)["quantity"] = clampi(int(value), 1, 9999999)
	refresh_favorites()
	persist()

func remove_entry() -> void:
	if _selected_entry < 0 or _selected_entry >= entries().size():
		return
	entries().remove_at(_selected_entry)
	_selected_entry = -1
	refresh_favorites()
	persist()

func _favorite_input(event: InputEvent, index: int) -> void:
	if not event is InputEventMouseButton or index >= entries().size():
		return
	var mouse := event as InputEventMouseButton
	if not mouse.pressed:
		return
	var slot: Button = favorite_grid.get_child(index) as Button
	if mouse.button_index == MOUSE_BUTTON_RIGHT:
		_selected_entry = index
		_update_editor()
		favorite_menu.position = Vector2i(get_viewport().get_mouse_position())
		favorite_menu.popup()
		slot.accept_event()
	elif mouse.button_index == MOUSE_BUTTON_LEFT and mouse.double_click:
		_selected_entry = index
		collect_entry(index)
		slot.accept_event()

func _entry_label(entry: Dictionary) -> String:
	var item_name: String = str(entry.get("name", ""))
	return item_name if not item_name.is_empty() else "Item #%d" % int(entry.get("image_id", 0))

func collect_entry(index: int) -> void:
	if index < 0 or index >= entries().size():
		return
	if not bool(AppState.storage.get("open", false)):
		list_status.text = "Open storage to get this item."
		return
	var entry: Dictionary = entries()[index] as Dictionary
	var category: int = int(entry.get("category_id", -1))
	if category >= 0 and category != int(AppState.storage.get("category_id", -1)):
		var error: Error = Network.get_storage_category(category)
		list_status.text = "Opening the item's category. Click again when it loads." if error == OK else "Could not open category: " + error_string(error)
		return
	_request_entries([entry])

func collect_list() -> void:
	if not bool(AppState.storage.get("open", false)):
		list_status.text = "Open storage to get your list."
		return
	_request_entries(entries())

func _request_entries(wanted: Array) -> void:
	if not _stock_ready():
		list_status.text = "Wait for the category to finish loading."
		return
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	var described: Dictionary = AppState.storage.get("described", {}) as Dictionary
	var remaining_stock: Dictionary = {}
	for raw_position: Variant in items:
		remaining_stock[int(raw_position)] = int((items[raw_position] as Dictionary).get("quantity", 0))
	var requested := 0
	var awaiting := 0
	var transfer_error: Error = OK
	var pending: Array[String] = []
	for raw_entry: Variant in wanted:
		var entry: Dictionary = raw_entry as Dictionary
		var carried: int = SavedItemLists.carried_quantity(entry, AppState.inventory, AppState.inventory_names)
		var in_flight: int = _outstanding_quantity(entry, carried)
		awaiting += in_flight
		var needed: int = maxi(0, int(entry.get("quantity", 1)) - carried - in_flight)
		var category_id: int = int(entry.get("category_id", -1))
		if category_id >= 0 and category_id != int(AppState.storage.get("category_id", -1)):
			if needed > 0:
				pending.append(_entry_label(entry))
			continue
		for position: int in SavedItemLists.matching_positions(entry, items, described):
			var amount: int = mini(needed, int(remaining_stock.get(position, 0)))
			if amount <= 0:
				continue
			var error: Error = Network.withdraw_storage(position, amount)
			if error == OK:
				needed -= amount
				remaining_stock[position] = int(remaining_stock[position]) - amount
				requested += amount
				in_flight += amount
				_pending_withdrawals[_entry_key(entry)] = {"quantity": in_flight,
					"carried": carried, "sent_at": Time.get_ticks_msec()}
			else:
				transfer_error = error
		if needed > 0:
			pending.append(_entry_label(entry))
	list_status.text = "Requested %d items." % requested
	if transfer_error != OK:
		list_status.text += " Could not transfer: " + error_string(transfer_error) + "."
	elif not pending.is_empty():
		list_status.text += " Unavailable here: %s. Open their category and try again." % ", ".join(pending)
	elif awaiting > 0:
		list_status.text = "Waiting for the requested items to arrive."
	elif requested == 0:
		list_status.text = "Your backpack already has this list's quantities." if not wanted.is_empty() else "Add items to this list with +."

func _entry_key(entry: Dictionary) -> String:
	return "%d:%s" % [int(entry.get("image_id", -1)), str(entry.get("name", "")).to_lower()]

func _outstanding_quantity(entry: Dictionary, carried: int) -> int:
	var key: String = _entry_key(entry)
	var pending: Dictionary = _pending_withdrawals.get(key, {}) as Dictionary
	if pending.is_empty():
		return 0
	# A rejected request can be retried; successful replies acknowledge it by
	# increasing the named backpack total. Repeated clicks cannot send it twice.
	if Time.get_ticks_msec() - int(pending.get("sent_at", 0)) > 10000:
		_pending_withdrawals.erase(key)
		return 0
	var outstanding: int = maxi(0, int(pending.get("quantity", 0))
		- maxi(0, carried - int(pending.get("carried", 0))))
	if outstanding == 0:
		_pending_withdrawals.erase(key)
	return outstanding

func _layout_input(event: InputEvent, handle: Control) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed \
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_RIGHT:
		_popup_layout()
		handle.accept_event()

func _popup_layout() -> void:
	layout_menu.set_item_checked(0, not docked)
	layout_menu.set_item_checked(1, docked)
	layout_menu.position = Vector2i(get_viewport().get_mouse_position())
	layout_menu.popup()

func _popup_add() -> void:
	add_menu.set_item_disabled(0, _selected_position < 0)
	var slot: int = int(main.get("selected_inventory_slot"))
	add_menu.set_item_disabled(1, slot < 0 or slot >= 36 or not AppState.inventory.has(slot))
	add_menu.position = Vector2i(get_viewport().get_mouse_position())
	add_menu.popup()

func set_docked(value: bool) -> void:
	docked = value
	if _open:
		if docked:
			_attach_inventory()
		else:
			_detach_inventory()
			_place_inventory_beside_bank()
	persist()

func _attach_inventory() -> void:
	if _attached:
		return
	_inventory_parent = inventory.get_parent()
	_inventory_position = inventory.position
	_inventory_z_index = inventory.z_index
	inventory.reparent(body)
	inventory.z_index = 0
	inventory.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	_attached = true
	(main.get("inventory_resize_grip") as Control).hide()
	layout_dock()

func _detach_inventory() -> void:
	if not _attached:
		return
	inventory.reparent(_inventory_parent)
	inventory.z_index = _inventory_z_index
	inventory.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	inventory.position = _inventory_position
	_attached = false
	bank.scale = Vector2.ONE
	(main.get("inventory_resize_grip") as Control).show()
	body.custom_minimum_size = STORAGE_SIZE
	bank.size = STORAGE_SIZE + Vector2(8, 8)
	(storage_content.get_child(0) as ClassicTitle).title.text = "Storage"
	main.call("_clamp_inventory_window_to_viewport")

func layout_dock() -> void:
	if not _attached:
		return
	inventory.position = Vector2(STORAGE_SIZE.x + 8, 0)
	var inventory_size: Vector2 = inventory.size * inventory.scale
	body.custom_minimum_size = Vector2(STORAGE_SIZE.x + 8 + inventory_size.x,
		maxf(STORAGE_SIZE.y, inventory_size.y))
	bank.size = body.custom_minimum_size + Vector2(8, 8)
	var available: Vector2 = get_viewport().get_visible_rect().size - Vector2(112, 16)
	bank.scale = Vector2.ONE * minf(1, minf(available.x / bank.size.x, available.y / bank.size.y))
	(storage_content.get_child(0) as ClassicTitle).title.text = "Docked bank"
	_clamp_bank()

func is_inventory_docked() -> bool:
	return _attached

func drag_docked_header(event: InputEvent) -> void:
	var handle: Control = main.get("inventory_header") as Control
	_bank_dragger.call("_on_handle_input", event, handle)
	_layout_input(event, handle)

func standalone_inventory_position() -> Vector2:
	return _inventory_position if _attached else inventory.position

func _place_inventory_beside_bank() -> void:
	_clamp_bank()
	inventory.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	inventory.position = bank.position + Vector2(bank.size.x + 12, 0)
	main.call("_clamp_inventory_window_to_viewport")
	lists.position = inventory.position + Vector2(inventory.size.x * inventory.scale.x + 12, 0)
	_clamp_lists()

func _clamp_bank() -> void:
	var limit: Vector2 = get_viewport().get_visible_rect().size - bank.size * bank.scale - Vector2(96, 8)
	bank.position = bank.position.clamp(Vector2(8, 8), limit.max(Vector2(8, 8)))

func _clamp_lists() -> void:
	var limit: Vector2 = get_viewport().get_visible_rect().size - lists.size - Vector2(96, 8)
	lists.position = lists.position.clamp(Vector2(8, 8), limit.max(Vector2(8, 8)))

func _viewport_changed() -> void:
	if _attached:
		layout_dock()
	else:
		_clamp_bank()
	_clamp_lists()

func _close_bank() -> void:
	main.call("_on_storage_close_pressed")

func persist() -> void:
	main.call("_save_hud_settings")
	var config := ConfigFile.new()
	config.load(main.get("SETTINGS_PATH"))
	config.set_value("storage", "docked", docked)
	config.set_value("storage", "active_list", active_list)
	config.set_value("storage", "position", bank.position)
	var error: Error = config.save(main.get("SETTINGS_PATH"))
	if error != OK:
		list_status.text = "Could not save preferences: " + error_string(error)
