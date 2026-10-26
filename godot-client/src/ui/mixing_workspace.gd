extends Control
## Reuses the live recipe list, search, quantity and manufacture buttons.
const Presets := preload("res://src/ui/mixing_presets.gd")
const Chrome := preload("res://src/ui/compact_hud_style.gd")
const Frame := preload("res://src/ui/hud_panel_chrome.gd")
const ItemNames := preload("res://src/state/item_names.gd")
const BROWSER_SECTION := "mixing_browser"
var model := Presets.new()
var main: Control
var preferences_path := WindowPreferences.SETTINGS_PATH
var ready_to_layout := false
var canvas: Control
var groups: Dictionary = {}
var header: HBoxContainer
var more: MenuButton
var preset_menu: PopupMenu
var tabs: TabBar
var skill: OptionButton
var ingredients_only: Button
var sort_order: Button
var selector: OptionButton
var details: VBoxContainer
var detail_scroll: ScrollContainer
var queue_body: VBoxContainer
var queue_scroll: ScrollContainer
var queue_toggle: Button
var queue_start: Button
var inventory_source: Button
var storage_source: Button
var source_row: HBoxContainer
var quantity_row: HBoxContainer
var quantity_controls: Array[Control] = []
var pin: Button
var _pinned := false
var editor: Control
var dragger: WindowDrag
var settings_pickers: Array[OptionButton] = []
var _tab := 1
var _browse := false
var _sync_pending := false
var _layout_pending := false
var _syncing := false
var _display_recipe := -2
var _before: Dictionary = {}
var _undo: Array[Dictionary] = []
var _redo: Array[Dictionary] = []
var _was_visible := false
var _drag_group := ""
var _drag_mouse := Vector2.ZERO
var _drag_origin := Vector2.ZERO
var _drag_dimensions := Vector2.ZERO
var _resizing := false

func configure(owner_main: Control) -> void:
	main = owner_main
	name = "MixingWorkspace"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	z_index = 290
	preferences_path = main.chat_hud.preferences_path
	model.load_file(preferences_path)
	_load_browser_preferences()
	(main.manufacturing_panel.get_node("Content") as Control).hide()
	canvas = Control.new()
	canvas.name = "CustomMixing"
	main.manufacturing_panel.add_child(canvas)
	for key: String in Presets.PARTS:
		var group := Control.new()
		group.name = key.to_pascal_case()
		canvas.add_child(group)
		groups[key] = group
	header = HBoxContainer.new()
	header.name = "MixingHeader"
	canvas.add_child(header)
	var title := _label("Mixing")
	title.name = "Title"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	pin = _button("◇", func() -> void:
		_pinned = not _pinned
		pin.text = "◆" if _pinned else "◇")
	pin.tooltip_text = "Keep this quick-mix card open when clicking the world"
	header.add_child(pin)
	header.add_child(_button("⌕", func() -> void:
		_browse = not _browse
		_tab = 0
		apply_layout()
		if _browse or model.working.recipe == "tabbed": main.manufacturing_filter.grab_focus()))
	more = MenuButton.new()
	more.name = "MixingMore"
	more.text = "•••"
	Chrome.button(more)
	header.add_child(more)
	header.add_child(_button("×", func() -> void: main.manufacturing_panel.hide()))
	dragger = WindowDrag.attach(main.manufacturing_panel, header)
	dragger.moved.connect(func(_at: Vector2) -> void: remember_position())
	tabs = TabBar.new()
	tabs.add_theme_stylebox_override("tab_selected", Chrome.box(Color("514026"), Color("dcb75e"), 4))
	tabs.add_theme_stylebox_override("tab_unselected", Chrome.box(Color("181713"), Color("4b422b"), 4))
	for caption: String in ["Recipes", "Mix", "Queue"]: tabs.add_tab(caption)
	tabs.tab_changed.connect(func(index: int) -> void:
		_tab = index
		apply_layout())
	canvas.add_child(tabs)
	_build_recipes()
	detail_scroll = _scroll(groups.details)
	groups.details.clip_contents = true
	details = VBoxContainer.new()
	details.name = "RecipeContent"
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	details.add_theme_constant_override("separation", 3)
	detail_scroll.add_child(details)
	_build_controls()
	var actions := HBoxContainer.new()
	actions.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	groups.actions.add_child(actions)
	for button: Button in [main.manufacturing_mix_one, main.manufacturing_mix_all]:
		button.reparent(actions)
		button.custom_minimum_size = Vector2.ZERO
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.text = "Mix now" if button == main.manufacturing_mix_one else "Add to queue"
		Chrome.button(button)
	main.manufacturing_status.reparent(groups.status)
	main.manufacturing_status.custom_minimum_size = Vector2.ZERO
	main.manufacturing_status.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	main.manufacturing_status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	main.manufacturing_status.set_meta("mix_semantic_color", true)
	main.manufacturing_status.autowrap_mode = TextServer.AUTOWRAP_OFF
	main.manufacturing_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_build_queue()
	_build_menu()
	editor = preload("res://src/ui/mixing_editor.gd").new()
	main.game_view.add_child(editor)
	editor.configure(self)
	main.window_stack.register(editor, true)
	_build_settings()
	main.manufacturing_quantity.text_changed.connect(func(_text: String) -> void: queue_sync())
	main.manufacturing_ready_only.toggled.connect(func(_pressed: bool) -> void:
		_save_browser_preferences()
		queue_sync())
	main.manufacturing_list.item_selected.connect(func(_index: int) -> void:
		_tab = 1
		_browse = false
		queue_sync())
	main.manufacturing_panel.visibility_changed.connect(queue_layout)
	get_viewport().size_changed.connect(queue_layout)
	ready_to_layout = true
	sync()
	apply_layout()

func _label(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label

func _button(text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	Chrome.button(button)
	button.pressed.connect(callback)
	return button

func _scroll(parent: Control) -> ScrollContainer:
	var scroll := ScrollContainer.new()
	scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	parent.add_child(scroll)
	return scroll

func _build_recipes() -> void:
	var column := VBoxContainer.new()
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	column.add_theme_constant_override("separation", 3)
	groups.recipes.add_child(column)
	var toolbar := HBoxContainer.new()
	toolbar.add_theme_constant_override("separation", 2)
	column.add_child(toolbar)
	skill = OptionButton.new()
	skill.fit_to_longest_item = false
	skill.clip_text = true
	skill.name = "MixingSkill"
	skill.add_item("All")
	skill.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	skill.set_item_metadata(0, "")
	for value: String in main._manufacturing_skills():
		skill.add_item(value.capitalize())
		skill.set_item_metadata(skill.item_count - 1, value)
	skill.item_selected.connect(func(index: int) -> void:
		if _syncing: return
		main.manufacturing_skill = str(skill.get_item_metadata(index))
		main._sync_manufacturing())
	toolbar.add_child(skill)
	ingredients_only = _button("i", func() -> void:
		main.manufacturing_ready_only.button_pressed = not main.manufacturing_ready_only.button_pressed)
	ingredients_only.name = "MixingIngredientsOnly"
	ingredients_only.toggle_mode = true
	ingredients_only.set_meta("mix_compact_toggle", true)
	ingredients_only.custom_minimum_size = Vector2(22, 24)
	toolbar.add_child(ingredients_only)
	sort_order = _button("A", func() -> void: set_sort_mode("level" if main.manufacturing_sort_mode == "name" else "name"))
	sort_order.name = "MixingSortOrder"
	sort_order.set_meta("mix_compact_toggle", true)
	sort_order.custom_minimum_size = Vector2(22, 24)
	toolbar.add_child(sort_order)
	main.manufacturing_filter.reparent(column)
	main.manufacturing_filter.placeholder_text = "Find recipe…"
	main.manufacturing_filter.custom_minimum_size = Vector2.ZERO
	main.manufacturing_filter.tooltip_text = "Search by recipe, ingredient or tool"
	main.manufacturing_list.reparent(column)
	main.manufacturing_list.custom_minimum_size = Vector2.ZERO
	main.manufacturing_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	main.manufacturing_list.fixed_icon_size = Vector2i(24, 24)
	main.manufacturing_list.icon_mode = ItemList.ICON_MODE_LEFT
	main.manufacturing_list.add_theme_constant_override("v_separation", 2)
	main.manufacturing_list.add_theme_stylebox_override("panel", Chrome.box(Color("12120f"), Color("4b422b"), 2))
	main.manufacturing_list.add_theme_stylebox_override("selected", Chrome.box(Color("514026"), Color("dcb75e"), 2))
	main.manufacturing_list.add_theme_stylebox_override("selected_focus", Chrome.box(Color("514026"), Color("dcb75e"), 2))

func _load_browser_preferences() -> void:
	var config := ConfigFile.new()
	if config.load(preferences_path) != OK: return
	var mode: String = str(config.get_value(BROWSER_SECTION, "sort", "name"))
	main.manufacturing_sort_mode = mode if mode in ["name", "level"] else "name"
	main.manufacturing_ready_preference = config.get_value(BROWSER_SECTION, "ingredients_only", true) == true
	main.manufacturing_ready_only.set_pressed_no_signal(main.manufacturing_ready_preference)

func _save_browser_preferences() -> void:
	var config := ConfigFile.new()
	config.load(preferences_path)
	config.set_value(BROWSER_SECTION, "sort", main.manufacturing_sort_mode)
	config.set_value(BROWSER_SECTION, "ingredients_only", main.manufacturing_ready_preference)
	var error := config.save(preferences_path)
	if error != OK: push_warning("Could not save mixing browser preferences: " + error_string(error))

func set_sort_mode(mode: String) -> void:
	if mode not in ["name", "level"]: return
	main.manufacturing_sort_mode = mode
	_display_recipe = -2
	main._sync_manufacturing()
	_save_browser_preferences()

func _build_controls() -> void:
	var column := VBoxContainer.new()
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	column.add_theme_constant_override("separation", 3)
	groups.controls.add_child(column)
	source_row = HBoxContainer.new()
	source_row.add_theme_constant_override("separation", 2)
	column.add_child(source_row)
	quantity_row = HBoxContainer.new()
	quantity_row.add_theme_constant_override("separation", 2)
	column.add_child(quantity_row)
	inventory_source = _button("Inventory", func() -> void: main.manufacturing_source.button_pressed = false)
	inventory_source.toggle_mode = true
	inventory_source.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	source_row.add_child(inventory_source)
	storage_source = _button("Storage", func() -> void: main.manufacturing_source.button_pressed = true)
	storage_source.toggle_mode = true
	storage_source.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	source_row.add_child(storage_source)
	var caption := _label("Qty")
	var decrease := _button("−", func() -> void: main._set_manufacturing_quantity(main._manufacturing_quantity_value() - 1))
	decrease.custom_minimum_size = Vector2(24, 24)
	source_row.add_child(caption)
	source_row.add_child(decrease)
	main.manufacturing_quantity.reparent(source_row)
	main.manufacturing_quantity.custom_minimum_size = Vector2(40, 0)
	main.manufacturing_quantity.size_flags_horizontal = Control.SIZE_FILL
	var increase := _button("+", func() -> void: main._set_manufacturing_quantity(main._manufacturing_quantity_value() + 1))
	increase.custom_minimum_size = Vector2(24, 24)
	source_row.add_child(increase)
	quantity_controls.assign([caption, decrease, main.manufacturing_quantity, increase])
	_arrange_controls(false)

func _arrange_controls(narrow: bool) -> void:
	var target: Control = quantity_row if narrow else source_row
	for control: Control in quantity_controls:
		if control.get_parent() != target: control.reparent(target)
	quantity_row.visible = narrow

func _build_queue() -> void:
	var column := VBoxContainer.new()
	column.name = "QueueBody"
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	column.add_theme_constant_override("separation", 3)
	groups.queue.add_child(column)
	var head := HBoxContainer.new()
	column.add_child(head)
	queue_toggle = _button("Queue", func() -> void: change_option("queue_expanded", not model.working.queue_expanded))
	queue_toggle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(queue_toggle)
	queue_start = _button("Start", func() -> void: main._on_manufacturing_queue_start_pressed())
	head.add_child(queue_start)
	queue_scroll = ScrollContainer.new()
	queue_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	queue_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(queue_scroll)
	queue_body = VBoxContainer.new()
	queue_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	queue_body.add_theme_constant_override("separation", 2)
	queue_scroll.add_child(queue_body)

func _build_menu() -> void:
	var popup := more.get_popup()
	preset_menu = PopupMenu.new()
	preset_menu.name = "MixingDesigns"
	popup.add_child(preset_menu)
	popup.add_submenu_item("Mixing design", "MixingDesigns", 10)
	popup.add_item("Customize mixing…", 11)
	popup.add_separator()
	popup.add_check_item("Has ingredients only", 12)
	popup.add_check_item("Full recipe requirements", 13)
	popup.add_item("Clear production queue", 14)
	popup.about_to_popup.connect(func() -> void:
		popup.set_item_checked(popup.get_item_index(12), main.manufacturing_ready_only.button_pressed)
		popup.set_item_disabled(popup.get_item_index(12), main.manufacturing_ready_only.disabled)
		popup.set_item_checked(popup.get_item_index(13), model.working.show_requirements))
	popup.id_pressed.connect(func(id: int) -> void:
		if id == 11: open_editor()
		elif id == 12: main.manufacturing_ready_only.button_pressed = not main.manufacturing_ready_only.button_pressed
		elif id == 13:
			change_option("show_requirements", not model.working.show_requirements)
			queue_sync()
		elif id == 14: main._on_manufacturing_queue_clear_pressed())
	preset_menu.id_pressed.connect(func(index: int) -> void: choose_preset(str(preset_menu.get_item_metadata(index))))

func _build_settings() -> void:
	var body: VBoxContainer = main.settings_window.page_body("HUD")
	if body == null: return
	var row := HBoxContainer.new()
	row.name = "MixingDesigns"
	body.add_child(row)
	row.add_child(_label("Mixing design"))
	var picker := OptionButton.new()
	picker.name = "MixingPresetPicker"
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(picker)
	settings_pickers.append(picker)
	picker.item_selected.connect(func(index: int) -> void: choose_preset(str(picker.get_item_metadata(index))))
	row.add_child(_button("Edit mixing…", open_editor))
	_refresh_pickers()

func _refresh_pickers() -> void:
	var ids: Array = Presets.BUILT_INS.keys() + model.custom.keys()
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

func queue_sync() -> void:
	if _sync_pending or not ready_to_layout: return
	_sync_pending = true
	sync.call_deferred()

func sync() -> void:
	_sync_pending = false
	if not ready_to_layout: return
	_syncing = true
	for index: int in skill.item_count:
		if skill.get_item_metadata(index) == main.manufacturing_skill: skill.select(index)
	skill.tooltip_text = "Skill: " + ("All skills" if main.manufacturing_skill.is_empty() else main.manufacturing_skill.capitalize())
	ingredients_only.set_pressed_no_signal(main.manufacturing_ready_only.button_pressed)
	ingredients_only.disabled = main.manufacturing_ready_only.disabled
	ingredients_only.tooltip_text = "i · Ingredients available\nIngredients for at least one mix in your pack, regardless of tools, food or skill level.\n" + main.manufacturing_ready_only.tooltip_text
	sort_order.text = "L" if main.manufacturing_sort_mode == "level" else "A"
	sort_order.tooltip_text = "L · Required level, low to high\nClick to sort alphabetically." if main.manufacturing_sort_mode == "level" else "A · Alphabetical\nClick to sort by required level."
	for row: int in main.manufacturing_list.item_count:
		var definition: Dictionary = main.manufacturing_catalog.recipe(int(main.manufacturing_list.get_item_metadata(row)))
		var output := str(definition.get("output", "Unknown"))
		main.manufacturing_list.set_item_text(row, ("%d · " % int(definition.get("level", 0)) if main.manufacturing_sort_mode == "level" else "") + ItemNames.display(output))
		main.manufacturing_list.set_item_icon(row, main._slot_icon(int(definition.get("outputImageId", 0)), -1))
		main.manufacturing_list.set_item_tooltip(row, ItemNames.tooltip(output) + "\n%s level %d\n%s" % [str(definition.get("skill", "")).capitalize(), int(definition.get("level", 0)), str(main._manufacturing_availability(int(main.manufacturing_list.get_item_metadata(row))).reasons)])
	if _display_recipe != main.selected_manufacturing_recipe:
		_display_recipe = main.selected_manufacturing_recipe
		for row: int in main.manufacturing_list.item_count:
			if int(main.manufacturing_list.get_item_metadata(row)) == _display_recipe:
				main.manufacturing_list.select(row)
				main.manufacturing_list.ensure_current_is_visible.call_deferred()
				break
	inventory_source.set_pressed_no_signal(not main._manufacturing_from_storage())
	storage_source.set_pressed_no_signal(main._manufacturing_from_storage())
	storage_source.disabled = not bool(AppState.mix_state.get("near_storage", false))
	storage_source.tooltip_text = main.manufacturing_source.tooltip_text
	_render_detail()
	_render_queue()
	tabs.set_tab_title(2, "Queue %d" % main.manufacturing_queue.size())
	var reasons: Array = main._manufacturing_availability(main.selected_manufacturing_recipe).reasons
	var server_status: String = main.manufacturing_server_status
	if main.selected_manufacturing_recipe >= 0 and server_status in ["Ready for server validation.", "Select a recipe."]:
		server_status = "Ready for storage check." if main._manufacturing_from_storage() else "Ready to mix."
	var failed := server_status.to_lower().contains("fail") or server_status.to_lower().contains("interrupted")
	main.manufacturing_status.text = ItemNames.in_text(str(reasons[0]) if not failed and not main._manufacturing_from_storage() and not reasons.is_empty() else server_status)
	main.manufacturing_status.add_theme_color_override("font_color", Color("f49b79") if failed else (Color("e1b67f") if not reasons.is_empty() else model.working.text))
	main.manufacturing_status.tooltip_text = server_status + "\n" + "; ".join(reasons)
	_syncing = false
	apply_layout()

func _clear(parent: Node) -> void:
	for child: Node in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func _icon(image: int, parent: Node, extent := 22) -> TextureRect:
	var icon := TextureRect.new()
	icon.texture = main._slot_icon(image, -1)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.custom_minimum_size = Vector2.ONE * extent
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(icon)
	return icon

func _render_detail() -> void:
	_clear(details)
	var definition: Dictionary = main.manufacturing_catalog.recipe(main.selected_manufacturing_recipe)
	var title := HBoxContainer.new()
	title.add_theme_constant_override("separation", 3)
	details.add_child(title)
	if not definition.is_empty(): _icon(int(definition.get("outputImageId", 0)), title, 28)
	var title_column := VBoxContainer.new()
	title_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_column.add_theme_constant_override("separation", 0)
	title.add_child(title_column)
	selector = OptionButton.new()
	selector.fit_to_longest_item = false
	selector.clip_text = true
	selector.name = "MixingRecipeSelector"
	selector.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	selector.add_theme_constant_override("arrow_margin", 1)
	selector.add_theme_constant_override("h_separation", 2)
	selector.tooltip_text = ItemNames.tooltip(str(definition.get("output", "Choose a recipe…")))
	selector.resized.connect(_fit_selector)
	selector.add_item(ItemNames.display(str(definition.get("output", "Choose a recipe…"))))
	selector.set_item_metadata(0, main.selected_manufacturing_recipe)
	for row: int in main.manufacturing_list.item_count:
		var index := int(main.manufacturing_list.get_item_metadata(row))
		if index == main.selected_manufacturing_recipe: continue
		selector.add_item(ItemNames.display(str(main.manufacturing_catalog.recipe(index).get("output", "Unknown"))))
		selector.set_item_tooltip(selector.item_count - 1, ItemNames.tooltip(str(main.manufacturing_catalog.recipe(index).get("output", "Unknown"))))
		selector.set_item_metadata(selector.item_count - 1, index)
	selector.item_selected.connect(func(index: int) -> void:
		var recipe_index := int(selector.get_item_metadata(index))
		for row: int in main.manufacturing_list.item_count:
			if int(main.manufacturing_list.get_item_metadata(row)) == recipe_index:
				main.manufacturing_list.select(row)
				main._on_manufacturing_selected(row)
				_browse = false
				_tab = 1
				break)
	title_column.add_child(selector)
	if definition.is_empty():
		details.add_child(_label("No matching recipes.\nChange search or ingredient filter."))
		return
	var meta := _label("%s %d · %d XP · Food %d" % [str(definition.get("skill", "")).capitalize(), int(definition.get("level", 0)), int(definition.get("experience", 0)), int(definition.get("food", 0))])
	meta.clip_text = true
	meta.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	meta.tooltip_text = meta.text
	meta.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	meta.set_meta("mix_small_text", true)
	meta.add_theme_font_size_override("font_size", maxi(11, model.working.font_size - 1))
	if model.working.recipe == "tray": title.add_child(meta)
	else: title_column.add_child(meta)
	var storage: bool = main._manufacturing_from_storage()
	var heading := _label("Ingredients     %s / Need ×%d" % ["Storage ?" if storage else "Have", main._manufacturing_quantity_value()])
	heading.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	heading.add_theme_font_size_override("font_size", 11)
	details.add_child(heading)
	for ingredient: Dictionary in definition.get("ingredients", []):
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 4)
		details.add_child(row)
		_icon(int(ingredient.get("imageId", 0)), row, 20)
		var caption := _label("%s ×%d" % [ItemNames.display(str(ingredient.name)), int(ingredient.quantity)])
		caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		caption.tooltip_text = "%s ×%d per item" % [ingredient.name, int(ingredient.quantity)]
		row.add_child(caption)
		var have: int = main._carried_count(str(ingredient.name))
		var need: int = int(ingredient.quantity) * main._manufacturing_quantity_value()
		var count := _label("%s / %d" % ["?" if storage or have < 0 else str(have), need])
		count.add_theme_color_override("font_color", Color("d7b875") if storage or have < 0 else (Color("9ade78") if have >= need else Color("f49b79")))
		count.set_meta("mix_semantic_color", true)
		row.add_child(count)
	for tool: Dictionary in main.manufacturing_catalog.tool_state(main.selected_manufacturing_recipe, AppState.inventory, AppState.inventory_names):
		var row := HBoxContainer.new()
		details.add_child(row)
		_icon(int(tool.imageId), row, 20)
		var tool_label: String = ItemNames.display(str(tool.name))
		if tool.held: tool_label += " ✓"
		elif tool.ambiguous: tool_label += " · unknown"
		else: tool_label = "⚠ " + ("Mortar" if tool.name == "Mortar and Pestle" else str(tool.name)) + " missing"
		var caption := _label(tool_label)
		caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		caption.tooltip_text = str(tool.name) + (" held, not consumed" if tool.held else " must be held in inventory")
		caption.add_theme_color_override("font_color", Color("9ade78") if tool.held else Color("ef947b"))
		caption.set_meta("mix_semantic_color", true)
		row.add_child(caption)
		if not tool.held and not tool.ambiguous:
			var take := _button("Take" if groups.details.size.x < 260 else "Take from storage", main._on_manufacturing_take_tool_pressed.bind(str(tool.name)))
			take.tooltip_text = "Take one %s from storage" % tool.name
			take.disabled = not bool(AppState.mix_state.get("near_storage", false))
			row.add_child(take)
	var reasons: Array = main._manufacturing_availability(main.selected_manufacturing_recipe).reasons
	if storage:
		var note := _label("Storage checked when mixing")
		note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		note.add_theme_font_size_override("font_size", 11)
		note.add_theme_color_override("font_color", Color("e1b67f"))
		note.set_meta("mix_semantic_color", true)
		details.add_child(note)
	if model.working.show_requirements:
		var full := RichTextLabel.new()
		full.bbcode_enabled = true
		full.fit_content = true
		full.scroll_active = false
		full.text = ItemNames.in_text(main.manufacturing_detail.text)
		details.add_child(full)

func _render_queue() -> void:
	_clear(queue_body)
	queue_toggle.text = "Queue · %d batches %s" % [main.manufacturing_queue.size(), "⌃" if model.working.queue_expanded else "›"]
	queue_start.text = "Stop" if main.manufacturing_queue_running else "Start"
	queue_start.disabled = main.manufacturing_queue.is_empty()
	if main.manufacturing_queue.is_empty(): queue_body.add_child(_label("Nothing queued."))
	for index: int in main.manufacturing_queue.size():
		var batch: Dictionary = main.manufacturing_queue[index]
		var recipe: Dictionary = main.manufacturing_catalog.recipe(int(batch.recipe))
		var row := HBoxContainer.new()
		queue_body.add_child(row)
		_icon(int(recipe.get("outputImageId", 0)), row, 20)
		var caption := _label("%s ×%d" % [ItemNames.display(str(recipe.get("output", "Unknown"))), int(batch.wanted)])
		caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		caption.tooltip_text = caption.text
		row.add_child(caption)
		row.add_child(_label("%d/%d" % [int(batch.made), int(batch.wanted)]))
		var remove := _button("×", main._on_manufacturing_queue_remove_pressed.bind(index))
		remove.tooltip_text = "Remove this batch"
		remove.disabled = main.manufacturing_queue_running and main.manufacturing_queue_index == index
		row.add_child(remove)
	var clear := _button("Clear queue", main._on_manufacturing_queue_clear_pressed)
	clear.disabled = main.manufacturing_queue.is_empty()
	queue_body.add_child(clear)

func queue_layout() -> void:
	if _layout_pending or not ready_to_layout: return
	_layout_pending = true
	apply_layout.call_deferred()

func apply_layout() -> void:
	_layout_pending = false
	if not ready_to_layout: return
	var config: Dictionary = model.working
	var recipe: String = config.recipe
	_arrange_controls(float(config.parts.controls.dimensions.x) < 260)
	pin.visible = recipe == "popover"
	var completed_result: bool = recipe == "tray" and bool(AppState.mix_state.get("served", false)) and not bool(AppState.mix_state.get("running", false)) and not str(AppState.mix_state.get("output", "")).is_empty()
	tabs.visible = recipe == "tabbed"
	tabs.set_current_tab(_tab)
	var extent := Vector2(240, 40)
	for key: String in Presets.PARTS:
		var part: Dictionary = config.parts[key]
		var at: Vector2 = part.position + part.offset
		var dimensions: Vector2 = part.dimensions
		groups[key].visible = part.enabled
		if key == "status" and completed_result: groups[key].show()
		if key == "recipes" and recipe in ["tabbed", "popover"]: groups[key].visible = part.enabled and (_tab == 0 if recipe == "tabbed" else _browse)
		if key == "details" and recipe in ["tabbed", "popover"]: groups[key].visible = part.enabled and (_tab == 1 if recipe == "tabbed" else not _browse)
		if recipe == "tabbed" and key in ["controls", "actions", "status"]: groups[key].visible = _tab == 1
		if key == "queue":
			if recipe == "tabbed" and _tab == 2:
				at = Vector2(8, 65) + part.offset
				dimensions.y = 290
			elif config.queue_expanded: dimensions.y = maxf(dimensions.y, 105)
		groups[key].position = at.max(Vector2(4, 33))
		groups[key].size = dimensions
		# Keep a stable tabbed footprint while switching pages.
		if recipe == "tabbed":
			extent = extent.max((part.position + part.offset).max(Vector2(4, 33)) + part.dimensions + Vector2(8, 8))
		elif groups[key].visible: extent = extent.max(groups[key].position + dimensions + Vector2(8, 8))
	queue_scroll.visible = config.queue_expanded or recipe == "tabbed" and _tab == 2
	main.manufacturing_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	main.manufacturing_panel.custom_minimum_size = Vector2.ZERO
	main.manufacturing_panel.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	main.manufacturing_panel.size = extent
	canvas.size = extent
	header.position = Vector2(8, 3)
	header.size = Vector2(extent.x - 16, 28)
	tabs.position = Vector2(8, 34)
	tabs.size = Vector2(extent.x - 16, 25)
	var frame := main.manufacturing_panel.get_node_or_null("MixingFrame") as Node2D
	if frame == null:
		frame = Frame.new()
		frame.name = "MixingFrame"
		main.manufacturing_panel.add_child(frame)
	frame.config = {"show_background": true, "background_color": config.background, "show_border": true, "border_color": config.border, "hud_border_style": config.border_style}
	frame.queue_redraw()
	_tint(canvas)
	_fit_selector.call_deferred()
	var available := _available_rect()
	var fit: float = minf(float(config.scale), minf(available.size.x / extent.x, available.size.y / extent.y))
	main.manufacturing_panel.scale = Vector2.ONE * fit
	var travel := (available.size - extent * fit).max(Vector2.ZERO)
	var position_ratio: Vector2 = config.position
	if config.anchor == "right": position_ratio = Vector2(1, 0.35)
	elif config.anchor == "bottom_right": position_ratio = Vector2.ONE
	elif config.anchor == "bottom_center": position_ratio = Vector2(0.5, 1)
	main.manufacturing_panel.position = available.position + travel * position_ratio
	dragger.reserved_right = main.game_view.size.x - available.end.x
	dragger.reserved_bottom = main.game_view.size.y - available.end.y
	dragger.enabled = not is_editing()
	queue_redraw()

func _tint(control: Control) -> void:
	control.add_theme_font_size_override("font_size", maxi(10, model.working.font_size - 1) if control.get_meta("mix_small_text", false) else model.working.font_size)
	if not control.get_meta("mix_semantic_color", false): control.add_theme_color_override("font_color", model.working.text)
	if control is Button:
		var padding := 2 if control == selector else 3
		control.add_theme_stylebox_override("normal", Chrome.box(Color("181713"), model.working.border.darkened(0.3), padding))
		control.add_theme_stylebox_override("hover", Chrome.box(Color("32291b"), model.working.border.lightened(0.3), padding))
		control.add_theme_stylebox_override("pressed", Chrome.box(Color("514026"), Color("dcb75e"), padding))
		if control == main.manufacturing_mix_one: control.add_theme_stylebox_override("normal", Chrome.box(Color("745025"), Color("c79c50"), 3))
		if control.get_meta("mix_compact_toggle", false):
			control.add_theme_color_override("font_color", Color("d7c8a5"))
			control.add_theme_color_override("font_disabled_color", Color("857d6b"))
			control.add_theme_color_override("font_pressed_color", Color("b7f191"))
			control.add_theme_color_override("font_hover_pressed_color", Color("d3ffb8"))
			control.add_theme_stylebox_override("pressed", Chrome.box(Color("27391e"), Color("739b51"), 2))
	for child: Node in control.get_children():
		if child is Control: _tint(child)

func _selector_text_width() -> float:
	var style := selector.get_theme_stylebox("normal")
	var arrow := selector.get_theme_icon("arrow")
	return maxf(0, selector.size.x - style.get_minimum_size().x - arrow.get_width() - selector.get_theme_constant("arrow_margin") - selector.get_theme_constant("h_separation") - 1)

func _fit_selector() -> void:
	if not is_instance_valid(selector) or selector.size.x <= 0 or selector.item_count == 0: return
	var font := selector.get_theme_font("font")
	var fitted: int = model.working.font_size
	var available := _selector_text_width()
	var text := selector.get_item_text(selector.selected)
	while fitted > 8 and font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fitted).x > available: fitted -= 1
	if selector.get_theme_font_size("font_size") != fitted: selector.add_theme_font_size_override("font_size", fitted)

func _available_rect() -> Rect2:
	# Reuse the inventory workspace's actual HUD edge reservations.
	if main.inventory_workspace != null and main.inventory_workspace.ready_to_layout: return main.inventory_workspace._available_rect()
	return Rect2(Vector2(8, 8), (main.game_view.size - Vector2(112, 88)).max(Vector2(240, 240)))

func remember_position() -> void:
	var available := _available_rect()
	var travel: Vector2 = (available.size - main.manufacturing_panel.size * main.manufacturing_panel.scale).max(Vector2.ONE)
	model.working.anchor = "free"
	model.working.position = ((main.manufacturing_panel.position - available.position) / travel).clamp(Vector2.ZERO, Vector2.ONE)
	if not is_editing(): store()

func choose_preset(id: String, factory := false) -> void:
	checkpoint()
	model.select(id, factory)
	_tab = 1
	_browse = false
	sync()
	main.manufacturing_list.ensure_current_is_visible.call_deferred()
	_refresh_pickers()
	if is_editing(): editor.refresh()
	else: store()

func change_option(key: String, value: Variant) -> void:
	checkpoint()
	model.working[key] = value
	model.working = Presets.normalise(model.working)
	sync()
	if not is_editing(): store()

func change_part(key: String, field: String, value: Variant) -> void:
	checkpoint()
	model.working.parts[key][field] = value
	model.working = Presets.normalise(model.working)
	apply_layout()
	if not is_editing(): store()

func store() -> bool:
	var error := model.save_file(preferences_path)
	if error != OK:
		if editor != null: editor.message.text = "Could not save. Your edits are still open."
		push_warning("Mixing design save failed: " + error_string(error))
	return error == OK

func is_editing() -> bool:
	return editor != null and editor.visible

func open_editor() -> void:
	if is_editing(): return
	if main.inventory_workspace != null and main.inventory_workspace.is_editing(): main.inventory_workspace.finish_edit(false)
	if main.hud_workspace != null and main.hud_workspace.is_open(): main.hud_workspace.cancel_edit()
	_before = model.snapshot()
	_undo.clear()
	_redo.clear()
	_was_visible = main.manufacturing_panel.visible
	main.settings_window.close()
	main._cancel_carry()
	main.manufacturing_panel.show()
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
	sync()
	editor.refresh()

func finish_edit(save: bool) -> void:
	if save and not store(): return
	if not save: model.restore(_before)
	editor.hide()
	_drag_group = ""
	main.manufacturing_panel.visible = _was_visible
	sync()
	_refresh_pickers()

func handle_editor_input(event: InputEvent) -> void:
	if not is_editing(): return
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_ESCAPE: finish_edit(false)
		elif event.ctrl_pressed and event.keycode == KEY_Z: undo_edit(event.shift_pressed)
		elif event.ctrl_pressed and event.keycode == KEY_Y: undo_edit(true)
		elif event.keycode in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN] and not main._text_entry_active():
			var movement := Vector2(float(event.keycode == KEY_RIGHT) - float(event.keycode == KEY_LEFT), float(event.keycode == KEY_DOWN) - float(event.keycode == KEY_UP)) * (10 if event.shift_pressed else 1)
			change_part(editor.selected, "offset", model.working.parts[editor.selected].offset + movement)
		else: return
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if not event.pressed:
			_drag_group = ""
			return
		if editor.get_global_rect().has_point(event.position): return
		if header.get_global_rect().has_point(event.position):
			checkpoint()
			_drag_group = "window"
			_drag_mouse = event.position
			_drag_origin = main.manufacturing_panel.position
			get_viewport().set_input_as_handled()
			return
		for key: String in groups:
			var group: Control = groups[key]
			if not group.is_visible_in_tree(): continue
			var rect: Rect2 = group.get_global_rect()
			if not rect.grow(6).has_point(event.position): continue
			checkpoint()
			editor.select_component(key)
			_drag_group = key
			_drag_mouse = event.position
			_drag_origin = model.working.parts[key].offset
			_drag_dimensions = model.working.parts[key].dimensions
			_resizing = Rect2(rect.end - Vector2(10, 10), Vector2(16, 16)).has_point(event.position)
			get_viewport().set_input_as_handled()
			break
	elif event is InputEventMouseMotion and not _drag_group.is_empty():
		if _drag_group == "window":
			main.manufacturing_panel.position = _drag_origin + (event.position - _drag_mouse) / main.game_view.get_global_transform().get_scale()
			remember_position()
		else:
			var delta: Vector2 = (event.position - _drag_mouse) / main.manufacturing_panel.get_global_transform().get_scale()
			if _resizing: model.working.parts[_drag_group].dimensions = (_drag_dimensions + delta).clamp(Vector2(100, 18), Vector2(1000, 650))
			else: model.working.parts[_drag_group].offset = _drag_origin + delta
			apply_layout()
		get_viewport().set_input_as_handled()

func _draw() -> void:
	if not is_editing(): return
	for key: String in groups:
		var group: Control = groups[key]
		if not group.is_visible_in_tree(): continue
		var rect := get_global_transform().affine_inverse() * group.get_global_rect()
		var color := Color("75d1df") if key == editor.selected else Color("72928b80")
		draw_rect(rect.grow(2), color, false, 2)
		if key == editor.selected: draw_rect(Rect2(rect.end - Vector2(5, 5), Vector2(10, 10)), color)

func _unhandled_input(event: InputEvent) -> void:
	if not ready_to_layout or is_editing() or _pinned or model.working.recipe != "popover": return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if main.manufacturing_panel.visible and not main.manufacturing_panel.get_global_rect().has_point(event.position): main.manufacturing_panel.hide()
