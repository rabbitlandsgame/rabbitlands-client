extends Control
## Reflows the real inventory controls. Presentation never sends item commands.
signal inspection_requested(slot: int, full: bool)
const Presets := preload("res://src/ui/inventory_presets.gd")
const Chrome := preload("res://src/ui/compact_hud_style.gd")
const Frame := preload("res://src/ui/hud_panel_chrome.gd")
const ItemNames := preload("res://src/state/item_names.gd")
var model := Presets.new()
var main: Control
var preferences_path := WindowPreferences.SETTINGS_PATH
var canvas: Control
var groups: Dictionary = {}
var header: HBoxContainer
var tabs: TabBar
var preview_icon: TextureRect
var inspection_icon: TextureRect
var inspection_title: Label
var inspection_category: Label
var inspection_text: RichTextLabel
var inspection_actions: HBoxContainer
var bulk_actions: GridContainer
var inspection_close: Button
var external_canvas: Control
var footer: HBoxContainer
var quantities: HBoxContainer
var quantity_value: LineEdit
var more: MenuButton
var search: LineEdit
var preset_menu: PopupMenu
var quantity_menu: PopupMenu
var editor: Control
var settings_pickers: Array[OptionButton] = []
var ready_to_layout := false
var _layout_pending := false
var _applying := false
var _tab := 0
var _detail: Dictionary = {}
var _detail_slot := -1
var _detail_cache: Dictionary = {}
var _pending_slot := -1
var _pending_image := -1
var _pending_full := false
var _pinned := false
var _pin: Button
var _inspection_open := false
var _external := false
var _was_visible := false
var _before: Dictionary = {}
var _undo: Array[Dictionary] = []
var _redo: Array[Dictionary] = []
var _drag_group := ""
var _drag_mouse := Vector2.ZERO
var _drag_origin := Vector2.ZERO
var _resizing := false
var _drag_cell := 36.0
var _drag_dimensions := Vector2.ZERO
var reagent_pouch
var _pouch_side_width := 75.0

func configure(owner_main: Control) -> void:
	main = owner_main
	name = "InventoryWorkspace"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	z_index = 290
	preferences_path = main.chat_hud.preferences_path
	model.load_file(preferences_path)
	(main.inventory_panel.get_node("Content") as Control).hide()
	canvas = Control.new()
	canvas.name = "CustomInventory"
	main.inventory_panel.add_child(canvas)
	header = HBoxContainer.new()
	header.name = "InventoryHeader"
	canvas.add_child(header)
	var title := Label.new()
	title.text = "Inventory"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	header.add_child(title)
	reagent_pouch = preload("res://src/ui/reagent_pouch.gd").new()

	search = LineEdit.new()
	search.name = "InventorySearch"
	search.placeholder_text = "Find item…"
	search.custom_minimum_size.x = 80
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.clear_button_enabled = true
	search.text_changed.connect(func(_text: String) -> void: _filter_slots())
	search.hide()
	header.add_child(search)
	header.add_child(_button("⌕", func() -> void:
		search.visible = not search.visible
		if search.visible: search.grab_focus()
		else:
			search.text = ""
			search.release_focus()))
	search.visibility_changed.connect(func() -> void:
		if not search.visible:
			search.text = ""
			_filter_slots())
	more = MenuButton.new()
	more.name = "InventoryMore"
	more.text = "•••"
	more.tooltip_text = "Inventory actions, designs and customization"
	header.add_child(more)
	var close: Button = main.get_node("%InventoryClose")
	close.reparent(header)
	_style_button(close)
	main.inventory_header = header
	header.gui_input.connect(main._on_inventory_header_gui_input)
	header.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
			remember_position())
	tabs = TabBar.new()
	tabs.name = "InventoryTabs"
	for caption: String in ["Pack", "Worn", "Inspect"]: tabs.add_tab(caption)
	tabs.tab_changed.connect(func(index: int) -> void:
		_tab = index
		if index == 2: inspect_selected()
		queue_layout())
	canvas.add_child(tabs)
	for key: String in Presets.PARTS:
		var group := Control.new()
		group.name = key.to_pascal_case()
		group.mouse_filter = Control.MOUSE_FILTER_PASS
		canvas.add_child(group)
		groups[key] = group
	groups.pouch.add_child(reagent_pouch)
	reagent_pouch.configure(main)
	main.inventory_grid.reparent(groups.backpack)
	main.equipment_grid.reparent(groups.equipment)
	for pair: Array in [["backpack", "Backpack"], ["equipment", "Equipment"]]:
		var label := Label.new()
		label.name = "Heading"
		label.text = pair[1]
		groups[pair[0]].add_child(label)
	preview_icon = _icon(groups.preview, 36)
	main.inventory_description.reparent(groups.preview)
	main.inventory_description.custom_minimum_size = Vector2.ZERO
	main.inventory_description.fit_content = false
	main.inventory_description.scroll_active = true
	main.inventory_description.bbcode_enabled = false
	var expand := _button("›", inspect_selected)
	expand.name = "ExpandPreview"
	expand.tooltip_text = "Inspect selected item"
	groups.preview.add_child(expand)
	_build_inspection()
	bulk_actions = preload("res://src/ui/inventory_action_bar.gd").new()
	groups.actions.add_child(bulk_actions)
	bulk_actions.configure(main, self)
	footer = HBoxContainer.new()
	footer.name = "InventoryLoadRow"
	canvas.add_child(footer)
	main.inventory_load.reparent(footer)
	main.inventory_load.clip_text = true
	main.inventory_load.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	main.inventory_resize_grip.reparent(footer)
	quantities = HBoxContainer.new()
	quantities.name = "InventoryQuantities"
	canvas.add_child(quantities)
	var qty := Label.new()
	qty.text = "Qty"
	quantities.add_child(qty)
	quantity_value = LineEdit.new()
	quantity_value.name = "QuantityValue"
	quantity_value.custom_minimum_size.x = 50
	quantity_value.max_length = 10
	quantity_value.tooltip_text = "Amount to pick up, withdraw, deposit or drop"
	quantity_value.text_submitted.connect(_quantity_submitted)
	quantity_value.focus_exited.connect(func() -> void: _quantity_submitted(quantity_value.text))
	quantities.add_child(quantity_value)
	main.inventory_quantity_bar.reparent(quantities)
	main.inventory_quantity_bar.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	for index: int in main.inventory_quantity_buttons.size():
		var button: Button = main.inventory_quantity_buttons[index]
		button.visible = index in [1, 2]
		button.custom_minimum_size = Vector2(23, 24)
		_style_button(button)
	quantities.add_child(_button("All", _quantity_all))
	# The original tools retain their signals and cursor semantics in a compact row.
	var tools := HBoxContainer.new()
	tools.name = "Tools"
	canvas.add_child(tools)
	for pair: Array in [[main.inventory_use_button, "Use"], [main.inventory_equip_button, "Wear"],
		[main.inventory_unequip_button, "Off"], [main.inventory_inspect_button, "Look"]]:
		var button: Button = pair[0]
		button.reparent(tools)
		button.text = pair[1]
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_style_button(button)
	_build_menu()
	_build_settings()
	editor = preload("res://src/ui/inventory_editor.gd").new()
	main.game_view.add_child(editor)
	editor.configure(self)
	main.window_stack.register(editor, true)
	main.extension_windows.item_detail_presenter = present_detail
	main.inventory_panel.visibility_changed.connect(_visibility_changed)
	get_viewport().size_changed.connect(queue_layout)
	ready_to_layout = true
	sync_inventory()
	apply_layout()

func _icon(parent: Node, extent: int) -> TextureRect:
	var icon := TextureRect.new()
	icon.custom_minimum_size = Vector2.ONE * extent
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(icon)
	return icon

func _style_button(button: Button) -> void:
	Chrome.button(button)
	button.custom_minimum_size.y = 24
	button.add_theme_stylebox_override("pressed", Chrome.box(Color("514026"), Color("dcb75e"), 4))

func _button(caption: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = caption
	_style_button(button)
	button.pressed.connect(action)
	return button

func _build_inspection() -> void:
	var root: Control = groups.inspection
	var body := VBoxContainer.new()
	body.name = "InspectionContent"
	root.add_child(body)
	var row := HBoxContainer.new()
	body.add_child(row)
	inspection_icon = _icon(row, 40)
	var heading := VBoxContainer.new()
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(heading)
	inspection_title = Label.new()
	inspection_title.text = "Item details"
	inspection_title.clip_text = true
	inspection_title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	heading.add_child(inspection_title)
	inspection_category = Label.new()
	inspection_category.clip_text = true
	heading.add_child(inspection_category)
	_pin = _button("◇", func() -> void:
		_pinned = not _pinned
		_pin.text = "◆" if _pinned else "◇")
	_pin.tooltip_text = "Pin this item card while browsing other items"
	_pin.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(_pin)
	var close := _button("×", close_inspection)
	inspection_close = close
	close.tooltip_text = "Close item details"
	close.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(close)
	inspection_text = main.extension_windows.detail_text
	inspection_text.reparent(body)
	inspection_text.bbcode_enabled = false
	inspection_text.fit_content = false
	inspection_text.scroll_active = true
	inspection_text.custom_minimum_size = Vector2.ZERO
	inspection_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	inspection_actions = HBoxContainer.new()
	body.add_child(inspection_actions)
	for pair: Array in [["Use", "use"], ["Equip", "equip"], ["Unequip", "unequip"], ["Drop", "drop"]]:
		var button := _button(pair[0], _item_action.bind(pair[1]))
		button.name = pair[1]
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		inspection_actions.add_child(button)
	var back := _button("‹ Back to Pack", func() -> void:
		_tab = 0
		tabs.current_tab = 0
		queue_layout())
	back.name = "BackToPack"
	body.add_child(back)
	var panel: Control = main.extension_windows.detail_panel
	(panel.get_node("Body") as Control).hide()
	var dragger := panel.get_node_or_null("WindowDrag") as WindowDrag
	if dragger != null: dragger.enabled = false
	panel.custom_minimum_size = Vector2.ZERO
	external_canvas = Control.new()
	external_canvas.name = "CompactItemCard"
	panel.add_child(external_canvas)

func _build_menu() -> void:
	var popup := more.get_popup()
	preset_menu = PopupMenu.new()
	preset_menu.name = "Designs"
	popup.add_child(preset_menu)
	popup.add_submenu_item("Inventory design", "Designs", 20)
	quantity_menu = PopupMenu.new()
	quantity_menu.name = "QuantityShortcuts"
	popup.add_child(quantity_menu)
	popup.add_submenu_item("Quantity shortcuts", "QuantityShortcuts", 22)
	quantity_menu.about_to_popup.connect(func() -> void:
		quantity_menu.clear()
		for value: int in main._inventory_quantities: quantity_menu.add_item(str(value)))
	quantity_menu.id_pressed.connect(func(index: int) -> void:
		main._on_quantity_box_pressed(index)
		quantity_value.text = str(main._selected_quantity()))
	popup.add_item("Customize inventory…", 21)
	popup.add_separator()
	for pair: Array in [["Store all", 0], ["Get all", 1], ["Drop all", 2], ["Mix all", 3], ["Item lists…", 4],
		["Store protection…", 5], ["Drop protection…", 6]]: popup.add_item(pair[0], pair[1])
	popup.id_pressed.connect(func(id: int) -> void:
		if id == 21: open_editor()
		elif id in [5, 6]:
			var menu: PopupMenu = main._store_options_menu if id == 5 else main._drop_options_menu
			menu.position = Vector2i(more.global_position)
			menu.popup()
		elif id >= 0 and id <= 4:
			var buttons: Array = [main.inventory_store_all, main.inventory_get_all, main.inventory_drop_all, main.inventory_mix_all, main.inventory_item_lists]
			(buttons[id] as Button).pressed.emit())
	preset_menu.id_pressed.connect(func(index: int) -> void: choose_preset(str(preset_menu.get_item_metadata(index))))
	_refresh_pickers()

func _build_settings() -> void:
	for page: String in ["HUD", "Inventory"]:
		var body: VBoxContainer = main.settings_window.page_body(page)
		if body == null: continue
		var row := HBoxContainer.new()
		row.name = "InventoryDesigns"
		body.add_child(row)
		var label := Label.new()
		label.text = "Inventory design"
		row.add_child(label)
		var picker := OptionButton.new()
		picker.name = "InventoryPresetPicker"
		picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(picker)
		settings_pickers.append(picker)
		picker.item_selected.connect(func(index: int) -> void: choose_preset(str(picker.get_item_metadata(index))))
		row.add_child(_button("Edit inventory…", open_editor))
	_refresh_pickers()

func _refresh_pickers() -> void:
	var ids: Array = Presets.BUILT_INS.keys() + model.custom.keys()
	if preset_menu != null:
		preset_menu.clear()
		for id: String in ids:
			preset_menu.add_radio_check_item(str(Presets.BUILT_INS.get(id, model.custom.get(id, {}).get("name", id))))
			preset_menu.set_item_metadata(preset_menu.item_count - 1, id)
			preset_menu.set_item_checked(preset_menu.item_count - 1, id == model.active)
	for picker: OptionButton in settings_pickers:
		picker.clear()
		for id: String in ids:
			picker.add_item(str(Presets.BUILT_INS.get(id, model.custom.get(id, {}).get("name", id))))
			picker.set_item_metadata(picker.item_count - 1, id)
			if id == model.active: picker.select(picker.item_count - 1)

func choose_preset(id: String, factory := false) -> void:
	checkpoint()
	model.select(id, factory)
	_set_tab(0)
	apply_layout()
	_refresh_pickers()
	if is_editing(): editor.refresh()
	else: store()

func change_option(key: String, value: Variant) -> void:
	checkpoint()
	model.working[key] = value
	model.working = Presets.normalise(model.working)
	apply_layout()
	if not is_editing(): store()

func change_part(key: String, field: String, value: Variant) -> void:
	checkpoint()
	model.working.parts[key][field] = value
	model.working = Presets.normalise(model.working)
	apply_layout()
	if not is_editing(): store()

func queue_layout() -> void:
	if not ready_to_layout or _layout_pending: return
	_layout_pending = true
	apply_layout.call_deferred()

func _grid_extent(key: String, count: int) -> Vector2:
	var options: Dictionary = model.working.parts[key]
	var columns: int = mini(count, options.columns)
	return Vector2(columns, ceili(float(count) / columns)) * (options.cell + model.working.gap) - Vector2.ONE * model.working.gap + Vector2(0, 20)

func _place(key: String, where: Vector2, extent: Vector2) -> void:
	var group: Control = groups[key]
	group.position = where + model.working.parts[key].offset
	group.size = extent

func apply_layout() -> void:
	_layout_pending = false
	if not ready_to_layout or _applying: return
	_applying = true
	var options: Dictionary = model.working
	var tray: bool = options.inspection_mode == "side"
	var footer_parent: Control = header if tray else footer
	for control: Control in [main.inventory_load, main.inventory_resize_grip]:
		if control.get_parent() != footer_parent: control.reparent(footer_parent)
		control.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	if tray:
		header.move_child(main.inventory_load, 1)
		header.move_child(main.inventory_resize_grip, header.get_child_count() - 2)
	footer.visible = not tray
	var pack_grid := _grid_extent("backpack", 24)
	var pack := pack_grid
	var worn := _grid_extent("equipment", 8)
	var replace: bool = options.inspection_mode == "replace"
	tabs.set_tab_disabled(1, not options.parts.equipment.enabled)
	tabs.set_tab_disabled(2, not options.parts.inspection.enabled)
	if _tab == 1 and not options.parts.equipment.enabled or _tab == 2 and not options.parts.inspection.enabled: _set_tab(0)
	var show_detail: bool = _inspection_open or is_editing() or options.inspection_mode == "side"
	var worn_visible: bool = options.parts.equipment.enabled and (not replace or _tab == 1)
	var pack_visible: bool = not replace or _tab == 0
	var top_pouch: bool = options.recipe == "dock" and options.equipment_side == "top" and worn_visible and pack_visible and options.parts.pouch.enabled
	_pouch_side_width = 75.0 if top_pouch else worn.x
	var pouch: Vector2 = reagent_pouch.extent(options.parts.pouch, options.gap, _pouch_side_width)

	var top := 32.0 + (30.0 if replace else 0.0)
	var pack_at := Vector2.ZERO
	var worn_at := Vector2.ZERO
	if worn_visible and pack_visible:
		match options.equipment_side:
			"left": pack_at.x = worn.x + 10
			"right": worn_at.x = pack.x + 10
			"top": pack_at.y = worn.y + 8
	var body_size := pack
	if worn_visible and pack_visible:
		body_size = Vector2(pack.x + worn.x + 10, maxf(pack.y, worn.y)) if options.equipment_side != "top" else Vector2(maxf(pack.x, worn.x), pack.y + worn.y + 8)
	elif worn_visible: body_size = worn
	# All tab pages share the full pack dimensions, so inspecting never grows a tabbed window.
	if replace: body_size = pack.max(Vector2(260, options.parts.inspection.height))
	var pouch_at := Vector2(0, top + body_size.y + 8)
	if top_pouch:
		# Equipment and pouch share the top row; the larger backpack fills the row below.
		pouch_at = Vector2(worn.x + 10, top)
		var top_height := maxf(worn.y, pouch.y)
		pack_at = Vector2(0, top_height + 8)
		body_size = Vector2(maxf(pack.x, worn.x + 10 + pouch.x), top_height + 8 + pack.y)
	elif options.parts.pouch.enabled:
		body_size.x = maxf(body_size.x, pouch.x)
		body_size.y += pouch.y + 8
	body_size.x = maxf(body_size.x, 224)
	if not top_pouch: pouch.x = body_size.x
	_place("backpack", pack_at + Vector2(0, top), pack_grid)
	_place("pouch", pouch_at, pouch)
	groups.pouch.visible = pack_visible and options.parts.pouch.enabled
	_place("equipment", worn_at + Vector2(0, top), worn)
	groups.backpack.visible = pack_visible
	groups.equipment.visible = worn_visible
	var preview_y: float = top + body_size.y + 8
	var preview_size := Vector2(body_size.x, options.parts.preview.height)
	_place("preview", Vector2(0, preview_y), preview_size)
	var inline_detail: bool = options.inspection_mode == "inline" and show_detail and options.parts.inspection.enabled
	groups.preview.visible = options.parts.preview.enabled and (not replace or _tab != 2) and not inline_detail
	var bottom: float = preview_y + (preview_size.y + 6 if groups.preview.visible or replace else 0)
	var width := body_size.x
	var mode: String = options.inspection_mode
	var detail_size := Vector2(options.parts.inspection.width, options.parts.inspection.height)
	_external = mode == "popover" or (not main.inventory_panel.visible and not is_editing()) or _detail_slot < 0 and not _detail.is_empty()
	var detail_root: Control = main.extension_windows.detail_panel
	var detail_parent: Control = external_canvas if _external else canvas
	if groups.inspection.get_parent() != detail_parent: groups.inspection.reparent(detail_parent, false)
	groups.inspection.visible = options.parts.inspection.enabled and show_detail
	if replace and not _external:
		groups.backpack.visible = _tab == 0
		groups.equipment.visible = _tab == 1 and options.parts.equipment.enabled
		groups.inspection.visible = _tab == 2 and options.parts.inspection.enabled
		_place("inspection", Vector2(0, top), body_size)
	elif mode == "side" and not _external:
		detail_size.y = maxf(detail_size.y, body_size.y + preview_size.y + 8)
		_place("inspection", Vector2(body_size.x + 10, top), detail_size)
		width += detail_size.x + 10
	elif not _external:
		detail_size.x = body_size.x
		_place("inspection", Vector2(0, bottom), detail_size)
		if groups.inspection.visible: bottom += detail_size.y + 6
	else:
		groups.inspection.position = Vector2.ZERO
		groups.inspection.size = detail_size
		external_canvas.custom_minimum_size = detail_size
		detail_root.size = detail_size + Vector2(16, 16)
		groups.inspection.visible = show_detail and options.parts.inspection.enabled
	var action_height: int = bulk_actions.apply_options(options.parts.actions)
	groups.actions.visible = options.parts.actions.enabled and action_height > 0
	bulk_actions.position = Vector2.ZERO
	bulk_actions.size = Vector2(body_size.x, action_height)
	_place("actions", Vector2(0, bottom), Vector2(maxf(body_size.x, bulk_actions.get_combined_minimum_size().x), action_height))
	bulk_actions.size.x = groups.actions.size.x
	# Include moved components in the window's real input and background bounds.
	for key: String in ["backpack", "equipment", "pouch", "preview", "inspection", "actions"]:
		var group: Control = groups[key]
		if group.visible and group.get_parent() == canvas:
			group.position = group.position.max(Vector2(0, top))
			width = maxf(width, group.position.x + group.size.x)
			if not (key == "inspection" and mode == "side"):
				bottom = maxf(bottom, group.position.y + group.size.y + 4)
	header.position = Vector2.ZERO
	header.size = Vector2(width, 28)
	tabs.visible = replace
	tabs.position = Vector2(0, 31)
	tabs.size = Vector2(width, 26)
	var tools: HBoxContainer = canvas.get_node("Tools")
	tools.visible = not (inline_detail or replace and _tab == 2 or mode == "side")
	tools.position = Vector2(0, bottom)
	tools.size = Vector2(body_size.x, 25)
	var tools_height := 29 if tools.visible or replace else 0
	quantities.position = Vector2(0, bottom + tools_height)
	quantities.size = Vector2(body_size.x, 25)
	footer.position = Vector2(0, bottom + tools_height + 29)
	footer.size = Vector2(width, 24)
	var final_height: float = bottom + tools_height + 53
	if mode == "side" and not _external:
		# Quantity belongs to the inspection column; the pack's preview stays directly below its grid.
		quantities.position = Vector2(body_size.x + 16, top + detail_size.y - 30)
		quantities.size = Vector2(detail_size.x - 12, 25)
		footer.position.y = maxf(bottom + 2, top + detail_size.y + 4)
		final_height = footer.position.y
	canvas.custom_minimum_size = Vector2(width, final_height)
	main.inventory_panel.custom_minimum_size = Vector2.ZERO
	main.inventory_panel.size = canvas.custom_minimum_size + Vector2(16, 16)
	main.inventory_panel.scale = Vector2.ONE * options.scale
	main._inventory_scale = options.scale
	_style()
	_layout_contents()
	if not _docked():
		var available := _available_rect()
		var extent: Vector2 = main.inventory_panel.size * main.inventory_panel.scale
		var where: Vector2
		match options.anchor:
			"bottom_right": where = available.end - extent
			"bottom_center": where = Vector2(available.get_center().x - extent.x * 0.5, available.end.y - extent.y)
			"free": where = available.position + (available.size - extent).max(Vector2.ZERO) * options.position
			_: where = Vector2(available.end.x - extent.x, available.get_center().y - extent.y * 0.5)
		main.inventory_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
		main.inventory_panel.position = where
		clamp_window()
	else: main.classic_storage.layout_dock()
	if _external and groups.inspection.visible:
		detail_root.show()
		_position_card()
	else: detail_root.hide()
	_applying = false
	queue_redraw()

func _layout_contents() -> void:
	for key: String in ["backpack", "equipment"]:
		var grid: GridContainer = main.inventory_grid if key == "backpack" else main.equipment_grid
		grid.position = Vector2(0, 20)
		grid.columns = model.working.parts[key].columns
		grid.add_theme_constant_override("h_separation", model.working.gap)
		grid.add_theme_constant_override("v_separation", model.working.gap)
		grid.size = _grid_extent(key, 24 if key == "backpack" else 8) - Vector2(0, 20)
		for button: Button in grid.get_children():
			button.custom_minimum_size = Vector2.ONE * model.working.parts[key].cell
			button.add_theme_constant_override("icon_max_width", model.working.parts[key].cell - 6)
			button.add_theme_color_override("icon_normal_color", Color(1, 1, 1, model.working.parts[key].icon_opacity))
		(groups[key].get_node("Heading") as Label).size = Vector2(groups[key].size.x, 18)
	reagent_pouch.position = Vector2.ZERO
	reagent_pouch.size = groups.pouch.size
	reagent_pouch.apply_style(model.working, _pouch_side_width, model.working.equipment_side == "right")
	var preview_size: Vector2 = groups.preview.size
	preview_icon.position = Vector2(4, 4)
	preview_icon.size = Vector2.ONE * minf(36, preview_size.y - 8)
	main.inventory_description.position = Vector2(46, 4)
	main.inventory_description.size = Vector2(maxf(20, preview_size.x - 74), preview_size.y - 8)
	var expand: Button = groups.preview.get_node("ExpandPreview")
	expand.position = Vector2(preview_size.x - 25, 6)
	expand.size = Vector2(24, 26)
	var body: Control = groups.inspection.get_node("InspectionContent")
	body.position = Vector2(6, 6)
	body.size = groups.inspection.size - Vector2(12, 12)
	if model.working.inspection_mode == "side" and not _external: body.size.y -= 32
	(body.get_node("BackToPack") as Control).visible = model.working.inspection_mode == "replace" and not _external
	_pin.visible = model.working.inspection_mode == "popover" or _external
	inspection_close.visible = model.working.inspection_mode != "side" or _external

func _style() -> void:
	var config: Dictionary = model.working
	var theme := Theme.new()
	theme.default_font_size = config.font_size
	for kind: String in ["Label", "Button", "LineEdit", "TabBar"]: theme.set_color("font_color", kind, config.text)
	theme.set_color("default_color", "RichTextLabel", config.text)
	theme.set_stylebox("panel", "PanelContainer", Chrome.box(config.background, config.border, 8))
	main.inventory_panel.theme = theme
	var empty_box := Chrome.box(Color.TRANSPARENT, Color.TRANSPARENT, 8)
	empty_box.set_border_width_all(0)
	main.inventory_panel.add_theme_stylebox_override("panel", empty_box)
	main.extension_windows.detail_panel.theme = theme
	main.extension_windows.detail_panel.add_theme_stylebox_override("panel", empty_box)
	for panel: Control in [main.inventory_panel, main.extension_windows.detail_panel]:
		var ornament := panel.get_node_or_null("InventoryFrame") as Node2D
		if ornament == null:
			ornament = Frame.new()
			ornament.name = "InventoryFrame"
			panel.add_child(ornament)
		ornament.config = {"show_background": true, "background_color": config.background, "show_border": true, "border_color": config.border, "hud_border_style": config.border_style}
		ornament.queue_redraw()
	for label: RichTextLabel in [main.inventory_description, inspection_text]:
		label.add_theme_font_size_override("normal_font_size", config.font_size)
		label.add_theme_color_override("default_color", config.text)
	inspection_title.add_theme_font_size_override("font_size", config.font_size + 2)
	for key: String in ["backpack", "equipment"]:
		var buttons: Array = main.inventory_slot_buttons if key == "backpack" else main.equipment_slot_buttons
		for index: int in buttons.size():
			var button: Button = buttons[index]
			var selected: bool = int(main.selected_inventory_slot) == index + (36 if key == "equipment" else 0)
			button.add_theme_stylebox_override("normal", Chrome.box(Color("181713"), Color("e2b854") if selected else config.border.darkened(0.35), 3))
			button.add_theme_stylebox_override("hover", Chrome.box(Color("30291c"), config.border.lightened(0.3), 3))
			button.add_theme_stylebox_override("pressed", Chrome.box(Color("463b23"), Color("e2b854"), 3))
	for index: int in main.inventory_quantity_labels.size():
		var label: Label = main.inventory_quantity_labels[index]
		label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
		label.offset_top = -16
		label.offset_right = -2
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		label.visible = config.parts.backpack.show_quantity

func _available_rect() -> Rect2:
	# Respect the active HUD's actual edge surfaces, not a hard-coded old rail width.
	var extent: Vector2 = main.game_view.size
	var right := 8.0
	var bottom := 8.0
	if main.hud_workspace != null and main.hud_workspace.ready_to_layout:
		for pass_index: int in 3:
			for key: String in ["rail_panel", "resources", "utilities", "status"]:
				var part: Control = main.hud_workspace._root(key)
				if part == null or not part.is_visible_in_tree(): continue
				var rect: Rect2 = main.game_view.get_global_transform().affine_inverse() * part.get_global_rect()
				if rect.end.x >= extent.x - right - 4 and rect.position.x > extent.x * 0.7 and rect.size.x < extent.x * 0.25 and rect.size.y > extent.y * 0.4:
					right = maxf(right, extent.x - rect.position.x + 8)
				if rect.end.y >= extent.y - bottom - 4 and rect.position.y > extent.y * 0.6 and rect.size.y < extent.y * 0.25 and rect.size.x > extent.x * 0.3:
					bottom = maxf(bottom, extent.y - rect.position.y + 8)
	return Rect2(Vector2(8, 8), (extent - Vector2(right + 8, bottom + 8)).max(Vector2(240, 240)))

func _docked() -> bool:
	return main.classic_storage != null and main.classic_storage.is_inventory_docked()

func clamp_window() -> void:
	if _docked():
		main.classic_storage.layout_dock()
		return
	var available := _available_rect()
	var extent: Vector2 = main.inventory_panel.size * main.inventory_panel.scale
	# Very wide custom layouts fit the viewport without losing any slots.
	var fit := minf(1, minf(available.size.x / maxf(1, extent.x), available.size.y / maxf(1, extent.y)))
	if fit < 1: main.inventory_panel.scale *= fit
	extent = main.inventory_panel.size * main.inventory_panel.scale
	main.inventory_panel.position = main.inventory_panel.position.clamp(available.position, (available.end - extent).max(available.position))
	if _external and _inspection_open: _position_card()

func remember_position() -> void:
	if _docked() or _applying: return
	var available := _available_rect()
	var travel: Vector2 = (available.size - main.inventory_panel.size * main.inventory_panel.scale).max(Vector2.ONE)
	model.working.anchor = "free"
	model.working.position = ((main.inventory_panel.position - available.position) / travel).clamp(Vector2.ZERO, Vector2.ONE)
	if not is_editing(): store()

func _position_card() -> void:
	var card: Control = main.extension_windows.detail_panel
	card.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	card.scale = Vector2.ONE
	var available := _available_rect()
	var inverse: Transform2D = main.game_view.get_global_transform().affine_inverse()
	var inventory_rect: Rect2 = inverse * main.inventory_panel.get_global_rect()
	var target: Rect2 = inventory_rect
	if _detail_slot >= 0:
		var buttons: Array = main.inventory_slot_buttons if _detail_slot < 36 else main.equipment_slot_buttons
		var index := _detail_slot if _detail_slot < 36 else _detail_slot - 36
		if index < buttons.size(): target = inverse * buttons[index].get_global_rect()
	var where := Vector2(inventory_rect.position.x - card.size.x - 10, target.position.y)
	if not main.inventory_panel.visible: where = available.get_center() - card.size * 0.5
	if where.x < available.position.x and main.inventory_panel.visible: where.x = inventory_rect.end.x + 10
	card.position = where.clamp(available.position, (available.end - card.size).max(available.position))

func _quantity_submitted(text: String) -> void:
	if not text.is_valid_int():
		quantity_value.text = str(main._selected_quantity())
		return
	main._inventory_quantity_override = clampi(int(text), 1, 0xffffffff)
	main._sync_inventory_quantity_boxes()
	main._save_hud_settings()
	quantity_value.text = str(main._selected_quantity())

func _quantity_all() -> void:
	var item: Dictionary = AppState.inventory.get(main.selected_inventory_slot, {})
	_quantity_submitted(str(maxi(1, int(item.get("quantity", 1)))))

func request_inspection(slot: int, full: bool) -> void:
	_pending_slot = slot
	_pending_image = int(AppState.inventory.get(slot, {}).get("image_id", -1))
	_pending_full = full
	if full:
		_pinned = false
		_pin.text = "◇"
		_inspection_open = true
		if model.working.inspection_mode == "replace":
			_set_tab(2)
	if full and _detail_cache.has(slot) and int(_detail_cache[slot].get("image_id", -1)) == _pending_image:
		_detail = _detail_cache[slot].duplicate(true)
		_detail_slot = slot
		_render_detail()
	elif full:
		_detail = {}
		_detail_slot = slot
		_render_detail()
	inspection_requested.emit(slot, full)
	queue_layout()

func inspect_selected() -> void:
	if model.working.inspection_mode == "inline" and _inspection_open:
		close_inspection()
		return
	if main.selected_inventory_slot < 0: return
	main._describe_slot(main.selected_inventory_slot, true)

func _set_tab(index: int) -> void:
	_tab = index
	tabs.set_block_signals(true)
	tabs.current_tab = index
	tabs.set_block_signals(false)

func present_detail(value: Dictionary, allowed: bool) -> void:
	if not bool(value.get("open", false)):
		_inspection_open = false
		queue_layout()
		return
	var slot := -1
	if _pending_slot >= 0:
		var current: Dictionary = AppState.inventory.get(_pending_slot, {})
		if int(value.get("image_id", -2)) == _pending_image and int(current.get("image_id", -3)) == _pending_image:
			slot = _pending_slot
			_detail_cache[slot] = value.duplicate(true)
		else:
			# A late reply must never attach actions to an item now occupying another slot.
			_pending_slot = -1
			return
		allowed = _pending_full
	_pending_slot = -1
	if not _pinned or slot < 0:
		_detail = value.duplicate(true)
		_detail_slot = slot
		_inspection_open = allowed
	_render_detail()
	sync_inventory()
	queue_layout()

func _render_detail() -> void:
	inspection_title.text = ItemNames.display(str(_detail.get("name", "Item details")))
	inspection_title.tooltip_text = ItemNames.tooltip(str(_detail.get("name", "Item details")))
	var current: Dictionary = AppState.inventory.get(_detail_slot, {})
	var bound: bool = _detail_slot >= 0 and int(current.get("image_id", -1)) == int(_detail.get("image_id", -2))
	inspection_category.text = "%s · ×%s%s" % [str(_detail.get("category", "")),
		main._grouped(int(current.get("quantity", 0) if bound else _detail.get("quantity", 0))), " · Equipped" if _detail.get("equipped", false) else ""]
	inspection_category.tooltip_text = inspection_category.text
	inspection_icon.texture = main.item_atlas.icon_for(int(_detail.get("image_id", 0))) if not _detail.is_empty() else null
	var lines: Array[String] = []
	if _detail.is_empty(): lines.append("Select an item, then choose Look to inspect it.")
	if model.working.show_stats and not str(_detail.get("stats", "")).is_empty(): lines.append(str(_detail.stats))
	if model.working.show_description and not str(_detail.get("description", "")).is_empty(): lines.append(str(_detail.description))
	if model.working.show_comparison and not str(_detail.get("comparison_name", "")).is_empty():
		lines.append("Compared with %s\n%s" % [ItemNames.display(str(_detail.comparison_name)), _detail.get("comparison", "")])
	inspection_text.text = "\n".join(lines)
	refresh_actions()

func refresh_actions() -> void:
	if not ready_to_layout: return
	var selected: Dictionary = AppState.inventory.get(main.selected_inventory_slot, {})
	main.inventory_use_button.disabled = selected.is_empty() or main.selected_inventory_slot >= 36 or not selected.get("inventory_usable", false) or main._inventory_cooldown_remaining(main.selected_inventory_slot) > 0
	var item: Dictionary = AppState.inventory.get(_detail_slot, {})
	var matches := _detail_slot >= 0 and int(item.get("image_id", -1)) == int(_detail.get("image_id", -2))
	for button: Button in inspection_actions.get_children():
		button.visible = matches and ((button.name == "use" and item.get("inventory_usable", false) and _detail_slot < 36)
			or (button.name == "drop" and (_detail_slot < 24 or _detail_slot >= 127)) or (button.name == "equip" and _detail_slot < 36 and str(_detail.get("equip_type", "")) not in ["", "none"])
			or (button.name == "unequip" and _detail_slot >= 36 and _detail_slot < 44))
		button.disabled = not matches or (button.name == "use" and main._inventory_cooldown_remaining(_detail_slot) > 0)

func _item_action(action: String) -> void:
	var item: Dictionary = AppState.inventory.get(_detail_slot, {})
	if _detail_slot < 0 or int(item.get("image_id", -1)) != int(_detail.get("image_id", -2)): return
	match action:
		"use": main._use_inventory_slot(_detail_slot)
		"equip": main._equip_inventory_slot(_detail_slot)
		"unequip": main._unequip_inventory_slot(_detail_slot)
		"drop":
			# Drop uses the player's chosen amount, rather than the Ctrl+click all-stack command.
			var amount: int = mini(int(item.get("quantity", 0)), main._selected_quantity())
			var error: Error = Network.drop_inventory_item(_detail_slot, amount)
			main.inventory_description.text = "Requested drop of %d." % amount if error == OK else "Could not drop: " + error_string(error)

func close_inspection() -> void:
	_inspection_open = false
	_pinned = false
	_pending_full = false
	_pin.text = "◇"
	if _tab == 2:
		_set_tab(0)
	queue_layout()

func sync_inventory() -> void:
	if not ready_to_layout: return
	reagent_pouch.sync()
	var slot: int = main.selected_inventory_slot
	var item: Dictionary = AppState.inventory.get(slot, {})
	preview_icon.texture = main._slot_icon(int(item.get("image_id", 0)), slot) if not item.is_empty() else null
	var description: Dictionary = main._inventory_description_for(slot) if slot >= 0 else {}
	var cached: Dictionary = _detail_cache.get(slot, {})
	if int(cached.get("image_id", -1)) != int(item.get("image_id", -2)): cached = {}
	var item_name := ItemNames.display(str(cached.get("name", description.get("name", AppState.inventory_names.get(slot, "Item")))))
	var category := str(cached.get("category", description.get("category", "")))
	var status: String = main.inventory_description.text
	if AppState.inventory_text.is_empty() and not status.begins_with("Could not") and not status.begins_with("Requested") and not status.begins_with("Dropped"):
		main.inventory_description.text = "%s%s · ×%s\n%s" % [item_name, " · " + category if not category.is_empty() else "",
			main._grouped(int(item.get("quantity", 0))), str(cached.get("stats", "Weight %s" % description.emu if description.has("emu") else "Choose Look for item details"))] if not item.is_empty() else "Select an item to inspect it."
	main.inventory_description.text = ItemNames.in_text(main.inventory_description.text)
	main.inventory_description.tooltip_text = main.inventory_description.text
	if not quantity_value.has_focus(): quantity_value.text = str(main._selected_quantity())
	main.inventory_use_button.disabled = item.is_empty() or slot >= 36 or not item.get("inventory_usable", false) or main._inventory_cooldown_remaining(slot) > 0
	main.inventory_equip_button.visible = not item.is_empty() and slot < 36 and not item.get("inventory_usable", false)
	main.inventory_equip_button.disabled = item.is_empty() or slot >= 36
	main.inventory_unequip_button.visible = slot >= 36 and slot < 44
	main.inventory_unequip_button.disabled = slot < 36 or slot >= 44
	for index: int in main.inventory_quantity_labels.size():
		var count: int = int(AppState.inventory.get(index, {}).get("quantity", 0))
		if count >= 1000:
			var label: Label = main.inventory_quantity_labels[index]
			label.text = ("%.1fM" % (count / 1000000.0) if count >= 1000000 else "%.1fK" % (count / 1000.0)).replace(".0", "")
			label.add_theme_font_size_override("font_size", 11)
	_render_detail()
	_style()
	_filter_slots()

func _filter_slots() -> void:
	var query := search.text.strip_edges().to_lower()
	for index: int in main.inventory_slot_buttons.size():
		var definition: Dictionary = main._inventory_description_for(index)
		var name_text := str(definition.get("name", AppState.inventory_names.get(index, "")))
		var matches: bool = query.is_empty() or (ItemNames.searchable(name_text) + " " + str(definition.get("category", ""))).to_lower().contains(query)
		main.inventory_slot_buttons[index].self_modulate.a = 1.0 if matches else 0.25

func _visibility_changed() -> void:
	if not main.inventory_panel.visible and _detail_slot >= 0 and not _pinned: close_inspection()
	queue_layout()

func store() -> bool:
	var error := model.save_file(preferences_path)
	if error != OK:
		push_warning("Inventory design save failed: " + error_string(error))
		if editor != null: editor.message.text = "Could not save your design. Your edits are still open."
	return error == OK

func is_editing() -> bool:
	return editor != null and editor.visible

func open_editor() -> void:
	if main.mixing_workspace != null and main.mixing_workspace.is_editing(): main.mixing_workspace.finish_edit(false)
	if is_editing(): return
	if bool(AppState.storage.get("open", false)): AppState.close_storage()
	if main.hud_workspace != null and main.hud_workspace.is_open(): main.hud_workspace.cancel_edit()
	_before = model.snapshot()
	_undo.clear()
	_redo.clear()
	_was_visible = main.inventory_panel.visible
	main.settings_window.close()
	main._cancel_carry()
	main.inventory_panel.show()
	editor.show()
	editor.refresh()
	apply_layout()
	WindowStack.activate(editor)

func checkpoint() -> void:
	if not is_editing(): return
	_undo.append(model.snapshot())
	if _undo.size() > 80: _undo.pop_front()
	_redo.clear()

func undo_edit(redo := false) -> void:
	var source: Array[Dictionary] = _redo if redo else _undo
	var target: Array[Dictionary] = _undo if redo else _redo
	if source.is_empty(): return
	target.append(model.snapshot())
	model.restore(source.pop_back())
	apply_layout()
	editor.refresh()
	_refresh_pickers()

func finish_edit(save: bool) -> void:
	if save and not store(): return
	if not save: model.restore(_before)
	editor.hide()
	_drag_group = ""
	main.inventory_panel.visible = _was_visible
	apply_layout()
	_refresh_pickers()

func resize_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_resizing = event.pressed
		_drag_mouse = event.global_position
		_drag_cell = model.working.scale
		if not event.pressed and not is_editing(): store()
	elif event is InputEventMouseMotion and _resizing:
		model.working.scale = clampf(_drag_cell + (event.global_position.x - _drag_mouse.x) / 350, 0.75, 1.75)
		apply_layout()
	main.inventory_resize_grip.accept_event()

func handle_editor_input(event: InputEvent) -> void:
	if not is_editing(): return
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			finish_edit(false)
			get_viewport().set_input_as_handled()
		elif event.ctrl_pressed and event.keycode == KEY_Z:
			undo_edit(event.shift_pressed)
			get_viewport().set_input_as_handled()
		elif event.keycode in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN] and not main._text_entry_active():
			var delta: Vector2 = {KEY_LEFT: Vector2.LEFT, KEY_RIGHT: Vector2.RIGHT, KEY_UP: Vector2.UP, KEY_DOWN: Vector2.DOWN}[event.keycode]
			change_part(editor.selected, "offset", model.working.parts[editor.selected].offset + delta * (10 if event.shift_pressed else 1))
			get_viewport().set_input_as_handled()
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if editor.get_global_rect().has_point(event.position): return
		if not event.pressed:
			if _drag_group == "window": remember_position()
			_drag_group = ""
			get_viewport().set_input_as_handled()
			return
		if header.get_global_rect().has_point(event.position) or main.inventory_resize_grip.get_global_rect().has_point(event.position):
			checkpoint()
			_drag_group = "window"
			_drag_mouse = event.position
			_drag_origin = main.inventory_panel.position
			_drag_cell = model.working.scale
			_resizing = main.inventory_resize_grip.get_global_rect().has_point(event.position)
			get_viewport().set_input_as_handled()
			return
		for key: String in ["actions", "inspection", "preview", "pouch", "equipment", "backpack"]:
			var control: Control = groups[key]
			if control.is_visible_in_tree() and control.get_global_rect().has_point(event.position):
				editor.select_component(key)
				checkpoint()
				_drag_group = key
				_drag_mouse = event.position
				_drag_origin = model.working.parts[key].offset
				_drag_cell = model.working.parts[key].cell
				_drag_dimensions = control.size
				_resizing = event.position.distance_to(control.get_global_rect().end) < 18
				break
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseMotion and not _drag_group.is_empty():
		if _drag_group == "window":
			if _resizing:
				model.working.scale = clampf(_drag_cell + (event.position.x - _drag_mouse.x) / 350, 0.75, 1.75)
				apply_layout()
			else:
				main.inventory_panel.position = _drag_origin + (event.position - _drag_mouse) / main.game_view.get_global_transform().get_scale()
				clamp_window()
				remember_position()
			get_viewport().set_input_as_handled()
			return
		var delta: Vector2 = (event.position - _drag_mouse) / main.inventory_panel.scale
		var config: Dictionary = model.working.parts[_drag_group]
		if not _resizing: config.offset = _drag_origin + delta
		elif _drag_group in ["backpack", "equipment", "pouch"]: config.cell = clampi(roundi(_drag_cell + delta.x / config.columns), 52 if _drag_group == "pouch" else 28, 80 if _drag_group == "pouch" else 64)
		else:
			config.height = clampi(roundi(_drag_dimensions.y + delta.y), 32 if _drag_group == "preview" else 140, 400)
			config.width = clampi(roundi(_drag_dimensions.x + delta.x), 200, 500)
		apply_layout()
		get_viewport().set_input_as_handled()

func _draw() -> void:
	if ready_to_layout and main.inventory_panel.is_visible_in_tree():
		for key: String in ["preview", "inspection"]:
			var section: Control = groups[key]
			if not section.is_visible_in_tree() or section.get_parent() != canvas: continue
			var rect: Rect2 = get_global_transform().affine_inverse() * section.get_global_rect()
			var color: Color = model.working.border
			color.a *= 0.45
			draw_line(rect.position - Vector2(0, 4), Vector2(rect.end.x, rect.position.y - 4), color, 1)
	if not is_editing(): return
	for key: String in groups:
		var group: Control = groups[key]
		if not group.is_visible_in_tree(): continue
		var rect := get_global_transform().affine_inverse() * group.get_global_rect()
		var color := Color("75d1df") if key == editor.selected else Color("72928b80")
		draw_rect(rect.grow(2), color, false, 2)
		if key == editor.selected: draw_rect(Rect2(rect.end - Vector2(5, 5), Vector2(10, 10)), color)
