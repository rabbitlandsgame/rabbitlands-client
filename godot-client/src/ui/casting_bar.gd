extends Control
signal cast_slot(index: int)
signal edit_slot(index: int)
signal open_book
signal open_wheel
signal layout_changed
signal settings_requested
const SpellButton := preload("res://src/ui/prepared_spell_button.gd")
const TechniqueIcons := preload("res://src/ui/technique_icons.gd")
const SCOPE_BADGES := {"self": "Self", "target": "Target", "allies": "Allies", "burst": "Burst", "location": "Ground", "inventory": "Item", "destination": "Recall"}
const CORNER_BADGES := {"self": "S", "target": "T", "allies": "A", "burst": "B", "location": "G", "inventory": "I", "destination": "R"}
const SLOT_SIZE := 44.0
const DEFAULT_VISIBLE_SLOTS := 6
const SLOT_BACKGROUNDS := {"normal": Color(0.11, 0.10, 0.07), "hover": Color(0.27, 0.22, 0.12), "pressed": Color(0.35, 0.27, 0.13)}
const EDGE := 6.0
const DOCK_INSET := 2.0
var loadout
var panel: PanelContainer
var mode_picker: OptionButton
var wheel_button: Button
var ring_size_picker: OptionButton
var slot_count_picker: OptionButton
var orientation_picker: OptionButton
var horizontal := false
var visible_slot_count := DEFAULT_VISIBLE_SLOTS
var start_expanded := true
var launcher: Button
var reserved_right_width := 8.0
## Dock controls share the HUD canvas, including its user-selected scale.
var dock_anchor: Control
var item_slots: GridContainer
var dock_rail: Control
var dock_top: Control
var dock_bottom: Control
var dock_footer: Control
var bottom_hud: Control
var docked := true
var buttons: Array[Button] = []
var menu: PopupMenu
var grip: Label
var dock_menu: MenuButton
var settings_body: VBoxContainer
var _scroll: ScrollContainer
var _column: GridContainer
var _menu_slot := -1
var _floating_position := Vector2(680, 80)
var _dragging := false
var _drag_moved := false
var _grab_mouse := Vector2.ZERO
var _grab_panel := Vector2.ZERO
var _last_layout_size := Vector3(-1, -1, -1)
var _last_compact := false
var _selected_actor := -2
var _item_header_height := 0.0
var _item_view_height := 0.0

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel = PanelContainer.new()
	panel.name = "PreparedCastingBar"
	panel.add_theme_stylebox_override("panel", _style(Color(0.16, 0.12, 0.075), 4))
	add_child(panel)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 2)
	panel.add_child(body)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 0)
	body.add_child(header)
	grip = Label.new()
	grip.name = "DragGrip"
	grip.text = "···"
	grip.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	grip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grip.add_theme_font_size_override("font_size", 13)
	grip.mouse_filter = Control.MOUSE_FILTER_STOP
	grip.mouse_default_cursor_shape = Control.CURSOR_MOVE
	grip.gui_input.connect(_grip_input)
	header.add_child(grip)
	dock_menu = MenuButton.new()
	dock_menu.text = "⋮"
	_compact_button(dock_menu)
	header.add_child(dock_menu)
	var popup := dock_menu.get_popup()
	popup.add_item("Detach from HUD", 0)
	popup.add_item("Spellbook", 1)
	popup.add_item("Ring / casting settings", 2)
	popup.add_separator()
	popup.add_item("Hide spell bar", 3)
	popup.about_to_popup.connect(_refresh_dock_menu)
	popup.id_pressed.connect(_dock_menu_action)
	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(_scroll)
	_column = GridContainer.new()
	_column.add_theme_constant_override("v_separation", 2)
	_column.add_theme_constant_override("h_separation", 2)
	_scroll.add_child(_column)
	for index in range(loadout.slots.size()):
		var cell := HBoxContainer.new()
		cell.add_theme_constant_override("separation", 2)
		_column.add_child(cell)
		var key := Label.new()
		key.name = "Key"
		key.custom_minimum_size.x = 12
		key.mouse_filter = Control.MOUSE_FILTER_IGNORE
		key.add_theme_font_size_override("font_size", 11)
		key.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cell.add_child(key)
		var button := SpellButton.new()
		button.name = "PreparedSpell%d" % index
		button.accepts_spells = true
		button.expand_icon = true
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.custom_minimum_size = Vector2.ONE * SLOT_SIZE
		button.add_theme_constant_override("icon_max_width", 36)
		button.focus_mode = Control.FOCUS_NONE
		button.add_theme_stylebox_override("normal", _style(Color(0.11, 0.10, 0.07), 2))
		button.add_theme_stylebox_override("hover", _style(Color(0.27, 0.22, 0.12), 2))
		button.add_theme_stylebox_override("pressed", _style(Color(0.35, 0.27, 0.13), 2))
		button.pressed.connect(func(): cast_slot.emit(index))
		button.spell_dropped.connect(func(id: int, power: int): loadout.assign_slot(index, id, power))
		button.technique_dropped.connect(func(key: String): loadout.assign_technique(index, key))
		button.gui_input.connect(_slot_input.bind(index))
		cell.add_child(button)
		for corner in ["Target", "Power"]:
			var badge := Label.new()
			badge.name = corner
			badge.add_theme_font_size_override("font_size", 11)
			badge.add_theme_color_override("font_color", Color(1.0, 0.94, 0.80))
			badge.add_theme_stylebox_override("normal", _style(Color(0.065, 0.075, 0.055), 1))
			badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
			badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			button.add_child(badge)
			badge.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT if corner == "Power" else Control.PRESET_TOP_LEFT)
			badge.offset_left = -20 if corner == "Power" else 1
			badge.offset_right = -1 if corner == "Power" else 15
			badge.offset_top = 1
			badge.offset_bottom = 17
		var shortcut := Label.new()
		shortcut.name = "Shortcut"
		shortcut.mouse_filter = Control.MOUSE_FILTER_IGNORE
		shortcut.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		shortcut.add_theme_font_size_override("font_size", 8)
		shortcut.add_theme_color_override("font_color", Color(0.78, 0.70, 0.53))
		button.add_child(shortcut)
		shortcut.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
		shortcut.offset_left = -6
		shortcut.offset_right = 2
		shortcut.offset_top = 1
		shortcut.offset_bottom = 12
		buttons.append(button)
	wheel_button = Button.new()
	wheel_button.text = "Ring"
	wheel_button.tooltip_text = "Hold Left Shift to browse spells. Alt + key casts a quick slot."
	_compact_button(wheel_button)
	wheel_button.pressed.connect(func(): open_wheel.emit())
	body.add_child(wheel_button)
	_build_settings()
	launcher = Button.new()
	launcher.name = "QuickbarLauncher"
	launcher.text = "Spells"
	launcher.focus_mode = Control.FOCUS_NONE
	launcher.tooltip_text = "Show spell shortcuts. Left Shift and Alt shortcuts also work while hidden."
	launcher.pressed.connect(func(): set_expanded(true))
	add_child(launcher)
	menu = PopupMenu.new()
	menu.add_item("Edit spell / power", 0)
	menu.add_item("Clear slot", 1)
	menu.id_pressed.connect(func(id: int):
		if id == 0: edit_slot.emit(_menu_slot)
		else: loadout.assign_slot(_menu_slot, -1, 1))
	add_child(menu)
	loadout.changed.connect(refresh)
	AppState.magic_state_received.connect(func(_data: Dictionary): refresh())
	AppState.state_changed.connect(func(path: StringName):
		if path == &"techniques": refresh())
	refresh()
	set_expanded(start_expanded)
	_layout()

func _style(background: Color, margin: float) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = Color(0.44, 0.38, 0.25)
	style.set_border_width_all(1)
	style.set_content_margin_all(margin)
	return style

func _compact_button(button: Button) -> void:
	button.focus_mode = Control.FOCUS_NONE
	button.add_theme_font_size_override("font_size", 11)
	button.add_theme_stylebox_override("normal", _style(Color(0.13, 0.105, 0.065), 1))
	button.add_theme_stylebox_override("hover", _style(Color(0.27, 0.22, 0.12), 1))
	button.add_theme_stylebox_override("pressed", _style(Color(0.35, 0.27, 0.13), 1))

func _build_settings() -> void:
	var body := VBoxContainer.new()
	body.name = "SpellBarSettings"
	settings_body = body
	# Main mounts these controls on the unified settings window's Spells tab.
	# Standalone casting-bar fixtures still own them until that happens.
	add_child(body)
	body.hide()
	var heading := Label.new()
	heading.text = "Spell bar settings"
	body.add_child(heading)
	mode_picker = OptionButton.new()
	mode_picker.name = "CastingMode"
	# Target spells always wait for a click on the recipient, so there is
	# no separate "aimed" mode any more: a saved "aimed" reads as Quick bar.
	mode_picker.add_item("Quick bar and book · click each target")
	mode_picker.add_item("Ring · hold Left Shift")
	mode_picker.item_selected.connect(func(index: int): loadout.set_mode(["prepared", "wheel"][index]))
	body.add_child(mode_picker)
	slot_count_picker = OptionButton.new()
	slot_count_picker.name = "QuickSlotCount"
	slot_count_picker.tooltip_text = "Choose how many quick spell icons to show. Extra saved slots keep their spells and keyboard shortcuts."
	for count in range(1, loadout.slots.size() + 1):
		slot_count_picker.add_item("Quick spell icons: %d" % count, count)
	slot_count_picker.item_selected.connect(func(index: int): set_visible_slot_count(slot_count_picker.get_item_id(index)))
	body.add_child(slot_count_picker)
	orientation_picker = OptionButton.new()
	orientation_picker.name = "QuickBarOrientation"
	orientation_picker.add_item("Vertical spell bar")
	orientation_picker.add_item("Horizontal spell bar")
	orientation_picker.item_selected.connect(func(index: int): set_horizontal(index == 1))
	body.add_child(orientation_picker)
	ring_size_picker = OptionButton.new()
	ring_size_picker.name = "RingSize"
	ring_size_picker.tooltip_text = "Magic ring size, saved per character."
	for percent in [75, 90, 100, 110, 125]:
		ring_size_picker.add_item("Ring size %d%%" % percent, percent)
	ring_size_picker.item_selected.connect(func(index: int): loadout.set_ring_size(ring_size_picker.get_item_id(index)))
	body.add_child(ring_size_picker)

func set_expanded(expanded: bool) -> void:
	var changed := panel.visible != expanded
	panel.visible = expanded
	launcher.visible = not expanded
	if not expanded:
		menu.hide()
		dock_menu.get_popup().hide()
		mode_picker.get_popup().hide()
		ring_size_picker.get_popup().hide()
	_layout()
	if changed: layout_changed.emit()

func set_docked(value: bool) -> void:
	if value and horizontal: set_horizontal(false)
	if docked == value: return
	_finish_drag()
	if not docked: _floating_position = panel.position
	docked = value
	if not docked:
		# A menu detach keeps the bar beside the rail until it is dragged.
		_floating_position = panel.position
	_layout()
	layout_changed.emit()

func hud_layout() -> Dictionary:
	return {"docked": docked, "position": _floating_position, "expanded": panel.visible, "slot_count": visible_slot_count, "horizontal": horizontal}

func set_horizontal(value: bool) -> void:
	if horizontal == value: return
	horizontal = value
	_last_layout_size = Vector3(-1, -1, -1)
	if horizontal:
		docked = false
		_floating_position = Vector2(maxf(EDGE, (size.x - visible_slot_count * 60) / 2), maxf(EDGE, _bottom_edge() - 110))
	_layout()
	layout_changed.emit()

func set_visible_slot_count(count: int) -> void:
	count = clampi(count, 1, buttons.size())
	if visible_slot_count == count: return
	visible_slot_count = count
	_scroll.scroll_vertical = 0
	_layout()
	layout_changed.emit()

func restore_hud_layout(value: Dictionary) -> void:
	docked = bool(value.get("docked", true))
	horizontal = bool(value.get("horizontal", false))
	if horizontal: docked = false
	_last_layout_size = Vector3(-1, -1, -1)
	visible_slot_count = clampi(int(value.get("slot_count", DEFAULT_VISIBLE_SLOTS)), 1, buttons.size())
	var where: Variant = value.get("position", _floating_position)
	if where is Vector2 and (where as Vector2).is_finite():
		_floating_position = where
	panel.visible = bool(value.get("expanded", true))
	launcher.visible = not panel.visible
	_layout()

func _refresh_dock_menu() -> void:
	dock_menu.get_popup().set_item_text(0, "Detach from HUD" if docked else "Attach to HUD")

func _dock_menu_action(id: int) -> void:
	match id:
		0: set_docked(not docked)
		1: open_book.emit()
		2:
			settings_requested.emit()
		3: set_expanded(false)

func _bottom_edge() -> float:
	if is_instance_valid(bottom_hud):
		return minf(size.y - EDGE, _local_position(bottom_hud).y - EDGE)
	return size.y - EDGE

func _local_position(control: Control) -> Vector2:
	return get_global_transform().affine_inverse() * control.global_position

func _dock_origin() -> Vector2:
	if _has_hud_dock(): return _dock_bounds().position
	if is_instance_valid(dock_anchor):
		var anchor := _local_position(dock_anchor)
		# The item column is narrower than the meters and clock below it.
		# Join the rail's outer edge so the twelve spells cannot cover them.
		var right := minf(anchor.x - 4, _local_position(dock_rail).x) if is_instance_valid(dock_rail) else anchor.x - 4
		return Vector2(right - panel.size.x, maxf(EDGE, anchor.y - 24))
	return Vector2(size.x - reserved_right_width - panel.size.x, EDGE)

func _has_hud_dock() -> bool:
	return is_instance_valid(dock_anchor) and is_instance_valid(dock_rail) \
		and is_instance_valid(dock_top) and is_instance_valid(dock_bottom)

func _dock_bounds() -> Rect2:
	var left := _local_position(dock_rail).x + DOCK_INSET
	var top := _local_position(dock_top).y + dock_top.size.y + 4
	var right := _local_position(dock_anchor).x - 4
	var bottom := minf(_local_position(dock_bottom).y - 4, _bottom_edge())
	if is_instance_valid(dock_footer): bottom = minf(bottom, _local_position(dock_footer).y - 4)
	return Rect2(Vector2(left, top), Vector2(maxf(0, right - left), maxf(0, bottom - top)))

func _layout() -> void:
	if panel == null or launcher == null: return
	var compact := docked and _has_hud_dock()
	var top := _dock_origin().y if docked else EDGE
	var available := maxf(80, _dock_bounds().size.y if compact else _bottom_edge() - top)
	var layout_size := Vector3(_dock_bounds().size.x if compact else size.x, available, visible_slot_count)
	if layout_size != _last_layout_size or compact != _last_compact:
		_last_layout_size = layout_size
		_last_compact = compact
		panel.add_theme_stylebox_override("panel", _style(Color(0.16, 0.12, 0.075), 1 if compact else 4))
		var body: VBoxContainer = _scroll.get_parent()
		body.add_theme_constant_override("separation", 1 if compact else 2)
		_column.add_theme_constant_override("v_separation", 1 if compact else 2)
		_column.columns = visible_slot_count if horizontal else 1
		orientation_picker.select(1 if horizontal else 0)
		grip.add_theme_font_size_override("font_size", 10 if compact else 13)
		dock_menu.add_theme_font_size_override("font_size", 9 if compact else 11)
		wheel_button.visible = not compact and loadout.mode == "wheel"
		_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER if compact else ScrollContainer.SCROLL_MODE_AUTO
		_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO if horizontal else ScrollContainer.SCROLL_MODE_DISABLED
		slot_count_picker.select(slot_count_picker.get_item_index(visible_slot_count))
		# Give the artwork its own square below the badges. Keep it readable
		# when more slots are shown by scrolling, rather than shrinking it.
		var width := minf(SLOT_SIZE, layout_size.x - 2) if compact else SLOT_SIZE
		var badge_height := 15 if compact else 20
		var icon_size := width - (6 if compact else 4)
		var slot_height := icon_size + badge_height + 2
		for index in range(buttons.size()):
			var button := buttons[index]
			button.custom_minimum_size = Vector2(width, slot_height)
			button.add_theme_constant_override("icon_max_width", int(icon_size))
			button.add_theme_font_size_override("font_size", 10 if compact else 16)
			for state in SLOT_BACKGROUNDS:
				var style := _style(SLOT_BACKGROUNDS[state], 2)
				style.content_margin_top = badge_height
				button.add_theme_stylebox_override(state, style)
			var cell: HBoxContainer = button.get_parent()
			cell.visible = index < visible_slot_count
			cell.add_theme_constant_override("separation", 1 if compact else 2)
			var key: Label = cell.get_node("Key")
			key.visible = not compact
			button.get_node("Shortcut").visible = compact
			key.custom_minimum_size.x = 8 if compact else 12
			key.add_theme_font_size_override("font_size", 8 if compact else 11)
			for corner in ["Target", "Power"]:
				var badge: Label = button.get_node(corner)
				badge.add_theme_font_size_override("font_size", 8 if compact else 11)
				badge.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT if corner == "Power" else Control.PRESET_TOP_LEFT)
				badge.offset_left = (-13 if compact else -20) if corner == "Power" else 1
				badge.offset_right = -1 if corner == "Power" else (10 if compact else 15)
				badge.offset_top = 1
				badge.offset_bottom = 12 if compact else 17
		var content_height := visible_slot_count * slot_height + (visible_slot_count - 1) * (1 if compact else 2)
		_scroll.custom_minimum_size = Vector2(width + (0 if compact else 14), minf(content_height, available - (18 if compact else 50)))
		if horizontal:
			_scroll.custom_minimum_size = Vector2(minf(visible_slot_count * (width + 16), maxf(100, size.x - reserved_right_width - EDGE * 2 - 8)), slot_height + 14)
		if compact:
			_sync_item_slot_layout(width, slot_height, icon_size)
		launcher.add_theme_font_size_override("font_size", 9 if compact else 16)
		launcher.add_theme_stylebox_override("normal", _style(Color(0.13, 0.105, 0.065), 1 if compact else 4))
		launcher.reset_size()
		panel.reset_size()
	if docked:
		panel.position = _dock_origin()
	else:
		panel.position = _clamp_position(_floating_position)
	grip.tooltip_text = "Drag to detach from the HUD" if docked else "Drag to move. Use the menu to attach to the HUD."
	dock_menu.tooltip_text = "Spell bar: detach, spellbook and ring settings" if docked else "Spell bar: attach to HUD, spellbook and ring settings"
	var launch_position := _dock_origin() if docked else _clamp_position(_floating_position)
	if docked and is_instance_valid(dock_anchor) and not compact:
		launch_position = Vector2(_dock_origin().x + panel.size.x - launcher.size.x, _local_position(dock_anchor).y)
	launcher.position = launch_position.clamp(Vector2.ONE * EDGE, (size - launcher.size - Vector2.ONE * EDGE).max(Vector2.ONE * EDGE))
	_layout_item_bar()

func _sync_item_slot_layout(width: float, height: float, icon_size: float) -> void:
	if not is_instance_valid(item_slots): return
	var body: VBoxContainer = _scroll.get_parent()
	var header: Control = body.get_child(0)
	_item_header_height = panel.get_theme_stylebox("panel").get_content_margin(SIDE_TOP) \
		+ header.get_combined_minimum_size().y + body.get_theme_constant("separation")
	_item_view_height = _scroll.custom_minimum_size.y
	item_slots.add_theme_constant_override("v_separation", _column.get_theme_constant("v_separation"))
	# Both columns reserve the same header space and artwork square. Item
	# shortcuts use that header so their numbers never reduce the icon size.
	for child in item_slots.get_children():
		var item := child as Button
		if item == null: continue
		item.custom_minimum_size = Vector2(width, height)
		item.add_theme_constant_override("icon_max_width", int(icon_size))
		for state: String in ["normal", "hover", "pressed", "disabled", "focus"]:
			var source: String = "normal" if state in ["disabled", "focus"] else state
			item.add_theme_stylebox_override(state, buttons[0].get_theme_stylebox(source).duplicate())
	if dock_anchor is ScrollContainer:
		(dock_anchor as ScrollContainer).get_v_scroll_bar().custom_step = height + 1.0

func _layout_item_bar() -> void:
	if not is_instance_valid(item_slots) or not _has_hud_dock(): return
	if docked and panel.visible:
		var header_height := _scroll.global_position.y - panel.global_position.y
		if header_height > 0.0:
			_item_header_height = header_height
	# Keep all eight items in the rail when the spell bar is moved or hidden.
	# The item viewport follows the dock, while retaining its compact cells.
	var bounds := _dock_bounds()
	var top := bounds.position.y + _item_header_height
	dock_anchor.position.y = top
	dock_anchor.size.y = minf(_item_view_height, maxf(0.0, bounds.end.y - top - 1.0))

func _clamp_position(where: Vector2) -> Vector2:
	var limit := Vector2(maxf(EDGE, size.x - reserved_right_width - panel.size.x),
		maxf(EDGE, _bottom_edge() - panel.size.y))
	return where.clamp(Vector2.ONE * EDGE, limit)

func _grip_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			_dragging = true
			_drag_moved = false
			_grab_mouse = get_global_transform().affine_inverse() * event.global_position
			_grab_panel = panel.position
			panel.move_to_front()
		else:
			_finish_drag()
		grip.accept_event()
	elif event is InputEventMouseMotion and _dragging:
		var delta: Vector2 = get_global_transform().affine_inverse() * event.global_position - _grab_mouse
		if not _drag_moved and delta.length() < 4: return
		_drag_moved = true
		docked = false
		_floating_position = _clamp_position(_grab_panel + delta)
		_layout()
		grip.accept_event()

func _input(event: InputEvent) -> void:
	# Release can happen outside the grip after a resize or a fast drag.
	if _dragging and event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
		_finish_drag()

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT: _finish_drag()

func _finish_drag() -> void:
	if not _dragging: return
	_dragging = false
	if _drag_moved:
		_floating_position = panel.position
		_drag_moved = false
		layout_changed.emit()

func refresh() -> void:
	if mode_picker == null: return
	mode_picker.select(["prepared", "wheel"].find(loadout.mode))
	wheel_button.visible = loadout.mode == "wheel" and not (docked and _has_hud_dock())
	ring_size_picker.visible = loadout.mode == "wheel"
	ring_size_picker.select(ring_size_picker.get_item_index(loadout.ring_size))
	ring_size_picker.text = "Ring size %d%%" % loadout.ring_size
	_selected_actor = AppState.selected_actor_id
	_technique_cooling = false
	for index in range(buttons.size()):
		var slot: Dictionary = loadout.slots[index]
		var button = buttons[index]
		button.technique = str(slot.get("technique", ""))
		if not button.technique.is_empty():
			_refresh_technique_slot(index, button)
			continue
		button.spell_id = int(slot.id)
		button.power = int(slot.power)
		var definition: Dictionary = loadout.catalog.spell(int(slot.id))
		button.icon = loadout.catalog.icon_for(int(slot.id)) if int(slot.id) >= 0 else null
		button.text = "+" if int(slot.id) < 0 else ""
		var scope := str(definition.get("scope", ""))
		var limit: Dictionary = AppState.spell_power.get(loadout.catalog.effect_for(int(slot.id)), {})
		var effective_power := mini(int(slot.power), maxi(1, int(limit.get("limit", 1))))
		button.get_node("Target").text = str(CORNER_BADGES.get(scope, ""))
		button.get_node("Power").text = str(int(slot.power)) if int(slot.id) >= 0 else ""
		button.get_node("Target").visible = int(slot.id) >= 0
		button.get_node("Power").visible = int(slot.id) >= 0
		var keys: Array[InputEvent] = InputMap.action_get_events("quick_spell_%d" % (index + 1))
		var shortcut := keys[0].as_text() if not keys.is_empty() else "Unbound"
		var key_label: Label = button.get_parent().get_node("Key")
		# Keep the full binding in the tooltip, with the familiar Alt gutter.
		key_label.text = str(index + 1) if index < 9 else ["0", "-", "="][index - 9]
		key_label.tooltip_text = shortcut
		button.get_node("Shortcut").text = key_label.text
		var target_label := str(SCOPE_BADGES.get(scope, ""))
		if scope == "target":
			target_label += ": click the recipient"
		button.tooltip_text = "%s · %s · Power %d\n%s\nUses the last cast target type and power for this family.\nRight click to edit; drag a spell here." % [definition.get("name", "Empty slot"), target_label, int(slot.power), shortcut]
		if effective_power != int(slot.power): button.tooltip_text += "\nSaved P%d; currently limited to P%d." % [int(slot.power), effective_power]
		var reasons: Array[String] = []
		if int(slot.id) >= 0:
			reasons = loadout.catalog.unavailable_reasons(int(slot.id), AppState.known_knowledge, AppState.stats, AppState.inventory)
		# Dim only the button's art. Its child badges must remain legible.
		button.self_modulate.a = 1.0 if reasons.is_empty() else 0.55
		if not reasons.is_empty(): button.tooltip_text += "\n" + reasons[0]

## Whether any technique slot is counting down, so `_process` keeps redrawing.
var _technique_cooling := false
var _next_cooldown_refresh := 0

## A technique in a quick slot: its painted icon, its action-point cost in the
## top-right badge where a spell shows power, and its cooldown in seconds in
## the top-left badge where a spell shows its target type. The art dims while
## it cannot be used, as a spell's does.
func _refresh_technique_slot(index: int, button) -> void:
	var key: String = button.technique
	var row: Dictionary = {}
	for raw: Variant in AppState.techniques.get("techniques", []):
		if raw is Dictionary and str(raw.get("key", "")) == key:
			row = raw
			break
	button.spell_id = -1
	button.icon = TechniqueIcons.icon_for(key)
	button.text = "" if button.icon != null else str(row.get("name", key)).left(4)
	var elapsed := float(Time.get_ticks_msec() - int(AppState.techniques.get("received_msec", 0))) / 1000.0
	var waiting := maxf(0.0, float(row.get("ready_in", 0.0)) - elapsed)
	var cost := int(row.get("ap", 0))
	var target_badge: Label = button.get_node("Target")
	var power_badge: Label = button.get_node("Power")
	target_badge.text = str(ceili(waiting)) if waiting > 0.05 else ""
	target_badge.visible = waiting > 0.05
	power_badge.text = str(cost) if cost > 0 else ""
	power_badge.visible = cost > 0
	_technique_cooling = _technique_cooling or waiting > 0.05
	var keys: Array[InputEvent] = InputMap.action_get_events("quick_spell_%d" % (index + 1))
	var shortcut := keys[0].as_text() if not keys.is_empty() else "Unbound"
	var key_label: Label = button.get_parent().get_node("Key")
	key_label.text = str(index + 1) if index < 9 else ["0", "-", "="][index - 9]
	key_label.tooltip_text = shortcut
	button.get_node("Shortcut").text = key_label.text
	var blocker := str(row.get("blocker", ""))
	var reason := ("Unknown on this server." if row.is_empty()
		else "Read the %s to learn it." % str(row.get("manual", "manual")) if not bool(row.get("known", false))
		else blocker if not blocker.is_empty()
		else "Ready in %ds." % ceili(waiting) if waiting > 0.05 else "")
	button.tooltip_text = "%s · technique%s\n%s\n%s\nRight click to clear; drag a spell or technique here." % [
		str(row.get("name", key)), (" · %d AP" % cost) if cost > 0 else "", str(row.get("description", "")), shortcut]
	if not reason.is_empty():
		button.tooltip_text += "\n" + reason
	button.self_modulate.a = 1.0 if reason.is_empty() else 0.55

func _slot_input(event: InputEvent, index: int) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
		_menu_slot = index
		menu.position = Vector2i(get_global_mouse_position())
		menu.popup()
		buttons[index].accept_event()

func _process(_delta: float) -> void:
	if AppState.selected_actor_id != _selected_actor: refresh()
	elif _technique_cooling and Time.get_ticks_msec() >= _next_cooldown_refresh:
		_next_cooldown_refresh = Time.get_ticks_msec() + 250
		refresh()
	_layout()
