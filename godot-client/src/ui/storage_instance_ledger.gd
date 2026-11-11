extends PanelContainer
## Selection is local; only the server can move the selected exact object.
const Tiers := preload("res://src/state/item_instance_tiers.gd")
const Icons := preload("res://src/ui/item_effect_icons.gd")
const IVORY := Color("eee3c8")
const MUTED := Color("ada98f")
const BRONZE := Color("9d7951")
const CYAN := Color("62e7e5")
const GOLD := Color("ffc66d")
var main: Node
var item_name := ""
var selected_id := 0
var offset := 0
var snapshot: Dictionary = {}
var heading: Label
var rows: VBoxContainer
var status: Label
var summary: Label
var selected_stats: Label
var selected_icon: TextureRect
var withdraw: Button
var previous: Button
var next: Button
var page: Label
var scroll: ScrollContainer
var _layout_pending := false
var _placed := false
var _withdrawing := false
var _serif: SystemFont
var _serif_bold: SystemFont

func configure(owner_main: Node, window_theme: Theme) -> void:
	main = owner_main
	name = "StorageInstanceLedger"
	theme = window_theme.duplicate() as Theme
	theme.default_font_size = 14
	theme.set_color("font_color", "Label", IVORY)
	theme.set_color("font_color", "Button", IVORY)
	_serif = SystemFont.new()
	_serif.font_names = PackedStringArray(["Georgia", "Noto Serif", "DejaVu Serif", "serif"])
	_serif_bold = _serif.duplicate() as SystemFont
	_serif_bold.font_weight = 700
	z_index = 80
	add_theme_stylebox_override("panel", _style(BRONZE, Color("071213"), 12, 2))
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	add_child(content)
	var header_panel := PanelContainer.new()
	header_panel.add_theme_stylebox_override("panel", _style(Color("3d4c43"), Color("0b2021"), 9))
	content.add_child(header_panel)
	var header := HBoxContainer.new()
	header.mouse_filter = Control.MOUSE_FILTER_IGNORE
	header.add_theme_constant_override("separation", 12)
	header_panel.add_child(header)
	var crest := _icon(header, Icons.texture("Lightweight"), 32)
	crest.modulate = GOLD
	heading = _label(header, "Enchanted equipment", 0, 24, true)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var close := _button(header, "×", hide)
	close.tooltip_text = "Close enchanted equipment"
	close.custom_minimum_size = Vector2(32, 32)
	close.add_theme_font_size_override("font_size", 22)
	var dragger := WindowDrag.attach(self, header_panel)
	dragger.reserved_bottom = 88
	dragger.moved.connect(func(_to: Vector2) -> void: _placed = true)
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 18)
	content.add_child(columns)
	_label(columns, "Item", 116, 16, true)
	_label(columns, "Saved effects", 0, 16, true).size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var condition_heading := _label(columns, "Condition", 96, 16, true)
	condition_heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	content.add_child(scroll)
	rows = VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 6)
	scroll.add_child(rows)
	var pages := HBoxContainer.new()
	content.add_child(pages)
	previous = _button(pages, "‹ Previous", func() -> void: _request_page(maxi(0, offset - 20)))
	page = _label(pages, "", 0, 12)
	page.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	page.modulate = MUTED
	next = _button(pages, "Next ›", func() -> void: _request_page(offset + 20))
	status = _label(content, "", 0, 13)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var footer_panel := PanelContainer.new()
	footer_panel.add_theme_stylebox_override("panel", _style(Color("526353"), Color("0b1b1c"), 10))
	content.add_child(footer_panel)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 12)
	footer_panel.add_child(footer)
	selected_icon = _icon(footer, null, 48)
	var details := VBoxContainer.new()
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(details)
	summary = _label(details, "Select a copy to withdraw.", 0, 16, true)
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	selected_stats = _label(details, "", 0, 13)
	selected_stats.mouse_filter = Control.MOUSE_FILTER_PASS
	selected_stats.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	selected_stats.modulate = MUTED
	withdraw = _button(footer, "Withdraw selected", _withdraw_selected)
	withdraw.custom_minimum_size = Vector2(170, 42)
	withdraw.add_theme_font_override("font", _serif_bold)
	withdraw.add_theme_font_size_override("font_size", 17)
	for state: String in ["normal", "hover", "pressed", "focus"]:
		withdraw.add_theme_stylebox_override(state, _style(CYAN, Color("0e3a3e") if state != "hover" else Color("155259"), 9, 2, true))
	withdraw.disabled = true
	add_child(preload("res://src/ui/storage_ledger_frame.gd").new())
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	minimum_size_changed.connect(_queue_fit)
	hide()

func open(item: String) -> void:
	item_name = item
	selected_id = 0
	_placed = false
	_withdrawing = false
	snapshot = {}
	heading.text = item + " · Enchanted copies"
	status.text = "Loading saved effects…"
	status.show()
	_clear_rows()
	_update_selection()
	show()
	var stack: Node = main.get("window_stack") as Node
	if stack != null: stack.call("register", self)
	preload("res://src/ui/window_stack.gd").activate(self)
	_fit()
	_request_page(0)

func _request_page(start: int) -> void:
	var error: Error = Network.storage_instance_request(item_name, start)
	if error != OK:
		status.text = "Could not load stored copies: " + error_string(error)
		status.show()

func _state_changed(part: StringName) -> void:
	if part == &"storage" and not bool(AppState.storage.get("open", false)):
		hide()
		snapshot = {}
	elif part == &"storage_instances" and visible:
		var incoming: Dictionary = AppState.storage.get("instances", {})
		if str(incoming.get("name", "")) == item_name:
			snapshot = incoming
			offset = int(snapshot.get("offset", 0))
			_withdrawing = false
			_render()

func _clear_rows() -> void:
	for child: Node in rows.get_children():
		rows.remove_child(child)
		child.queue_free()

func _render() -> void:
	_clear_rows()
	var copies: Array = snapshot.get("rows", [])
	var valid_selection := false
	heading.text = "%s · %d enchanted copies" % [item_name, int(snapshot.get("total", 0))]
	for raw_copy: Variant in copies:
		var copy: Dictionary = raw_copy as Dictionary
		valid_selection = valid_selection or int(copy.instance_id) == selected_id
		_add_row(copy)
	if not valid_selection: selected_id = 0
	previous.disabled = offset == 0
	next.disabled = offset + copies.size() >= int(snapshot.get("total", 0))
	page.text = "%d–%d of %d" % [offset + 1 if not copies.is_empty() else 0, offset + copies.size(), int(snapshot.get("total", 0))]
	status.text = str(snapshot.get("error", ""))
	if bool(snapshot.get("read_only", false)):
		status.text = "Storage preview · Visit a keeper or chest to withdraw."
	elif copies.is_empty() and status.text.is_empty():
		status.text = "No enchanted copies remain in storage."
	status.visible = not status.text.is_empty()
	_update_selection()
	_fit()
	_queue_fit()

func _add_row(copy: Dictionary) -> void:
	var panel := PanelContainer.new()
	panel.name = "Copy%d" % int(copy.instance_id)
	panel.set_meta("instance_id", int(copy.instance_id))
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	panel.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			selected_id = int(copy.instance_id)
			_update_selection()
			panel.accept_event())
	rows.add_child(panel)
	var line := HBoxContainer.new()
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line.add_theme_constant_override("separation", 18)
	panel.add_child(line)
	var item := VBoxContainer.new()
	item.custom_minimum_size.x = 104
	item.mouse_filter = Control.MOUSE_FILTER_IGNORE
	item.add_theme_constant_override("separation", 5)
	line.add_child(item)
	var choose := Button.new()
	choose.name = "SelectCopy"
	choose.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	choose.custom_minimum_size = Vector2(72, 68)
	choose.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	choose.icon = main.call("_named_icon", int(snapshot.get("image_id", 0)), item_name) as Texture2D
	choose.expand_icon = true
	choose.add_theme_constant_override("icon_max_width", 56)
	choose.tooltip_text = "Select this " + item_name + "\n" + "\n".join(copy.get("effects", []))
	var portrait_style := _style(Color("716b74"), Color("10131a"), 5)
	portrait_style.shadow_color = Color(0.61, 0.29, 0.86, 0.5)
	portrait_style.shadow_size = 5
	for state: String in ["normal", "hover", "pressed", "focus"]:
		choose.add_theme_stylebox_override(state, portrait_style)
	choose.pressed.connect(func() -> void:
		selected_id = int(copy.instance_id)
		_update_selection())
	item.add_child(choose)
	var tier: String = str(copy.get("tier", "magic"))
	var title := _label(item, Tiers.display_name(item_name, tier), 104, 13, true)
	title.name = "ItemName"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title.add_theme_color_override("font_color", Tiers.color(tier))
	var effects := GridContainer.new()
	effects.name = "Effects"
	effects.columns = 2 if get_viewport_rect().size.x >= 1050 else 1
	effects.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	effects.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	effects.mouse_filter = Control.MOUSE_FILTER_IGNORE
	effects.add_theme_constant_override("h_separation", 18)
	effects.add_theme_constant_override("v_separation", 12)
	line.add_child(effects)
	for effect: Variant in copy.get("effects", []):
		_add_effect(effects, str(effect))
	var condition := VBoxContainer.new()
	condition.custom_minimum_size.x = 84
	condition.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	condition.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line.add_child(condition)
	var current: Variant = copy.get("durability")
	var maximum: Variant = copy.get("max_durability")
	var condition_text := _label(condition, "%s / %s" % ["—" if current == null else str(int(current)),
		"—" if maximum == null else str(int(maximum))], 84, 16)
	condition_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var quality := _label(condition, "Quality %d" % int(copy.get("quality", 100)), 84, 12)
	quality.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	quality.modulate = MUTED
	panel.tooltip_text = "Base: %s\nFinal: %s" % [copy.get("base_stats", ""), copy.get("stats", "")]
	panel.set_meta("item_button", choose)

func _add_effect(parent: GridContainer, description: String) -> void:
	var data: Dictionary = Icons.presentation(description)
	var cell := HBoxContainer.new()
	cell.name = str(data.name).replace(" ", "")
	cell.set_meta("effect", data.name)
	cell.tooltip_text = description
	cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cell.mouse_filter = Control.MOUSE_FILTER_PASS
	cell.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	cell.add_theme_constant_override("separation", 8)
	parent.add_child(cell)
	_icon(cell, Icons.texture(str(data.name)), 30)
	var text := VBoxContainer.new()
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	text.add_theme_constant_override("separation", 3)
	cell.add_child(text)
	var title := RichTextLabel.new()
	title.custom_minimum_size.x = 160
	title.bbcode_enabled = true
	title.fit_content = true
	title.scroll_active = false
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title.add_theme_font_override("normal_font", _serif_bold)
	title.add_theme_font_size_override("normal_font_size", 16)
	title.add_theme_color_override("default_color", IVORY)
	title.text = str(data.name) + (" [color=#ffc66d]— %s[/color]" % data.roll if not str(data.roll).is_empty() else "")
	text.add_child(title)
	var body := _label(text, str(data.body), 160, 14)
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL

func _update_selection() -> void:
	for row: PanelContainer in rows.get_children():
		var selected: bool = int(row.get_meta("instance_id")) == selected_id
		var box := _style(CYAN if selected else Color("34433d"), Color("103134") if selected else Color("091416"), 10, 2 if selected else 1, selected)
		row.add_theme_stylebox_override("panel", box)
	withdraw.disabled = _withdrawing or selected_id <= 0 or bool(snapshot.get("read_only", false))
	summary.text = "Select a copy to withdraw."
	summary.add_theme_color_override("font_color", IVORY)
	selected_stats.text = "Click a row to compare its saved effects."
	selected_icon.texture = main.call("_named_icon", int(snapshot.get("image_id", 0)), item_name) as Texture2D if not snapshot.is_empty() else null
	for copy: Dictionary in snapshot.get("rows", []):
		if int(copy.instance_id) == selected_id:
			summary.text = "%s · %d saved effects" % [Tiers.display_name(item_name, str(copy.get("tier", "magic"))), (copy.effects as Array).size()]
			summary.add_theme_color_override("font_color", Tiers.color(str(copy.get("tier", "magic"))))
			selected_stats.text = "Final: " + str(copy.stats) if copy.has("stats") else "\n".join(copy.effects)
			selected_stats.tooltip_text = "Base: %s\nFinal: %s" % [copy.get("base_stats", ""), copy.get("stats", "")]
	_queue_fit()

func _withdraw_selected() -> void:
	if withdraw.disabled: return
	var error: Error = Network.storage_instance_request(item_name, offset, selected_id)
	status.text = "Withdrawing selected copy…" if error == OK else "Could not withdraw: " + error_string(error)
	status.show()
	_withdrawing = error == OK
	withdraw.disabled = true

func _fit() -> void:
	if not is_inside_tree(): return
	var viewport: Vector2 = get_viewport_rect().size
	for row: Node in rows.get_children():
		(row.find_child("Effects", true, false) as GridContainer).columns = 2 if viewport.x >= 1050 else 1
	set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	custom_minimum_size = Vector2(minf(930, maxf(580, viewport.x - 112)), 0)
	var chrome_height := get_combined_minimum_size().y - scroll.get_combined_minimum_size().y
	var body_height := minf(clampf(rows.get_combined_minimum_size().y, 170, 420), maxf(120, viewport.y - chrome_height - 96))
	scroll.custom_minimum_size = Vector2(0, body_height)
	size = get_combined_minimum_size()
	var desired: Vector2 = position if _placed else Vector2(405, 100)
	position = Vector2(clampf(desired.x, 8, maxf(8, viewport.x - size.x - 104)), clampf(desired.y, 8, maxf(8, viewport.y - size.y - 96)))

func _queue_fit() -> void:
	if _layout_pending or not visible or not is_inside_tree(): return
	_layout_pending = true
	_settle_fit.call_deferred()

func _settle_fit() -> void:
	await get_tree().process_frame
	_layout_pending = false
	if is_inside_tree() and visible: _fit()

func _label(parent: Node, text: String, width: float, font_size: int = 14, bold: bool = false) -> Label:
	var result := Label.new()
	result.text = text
	result.custom_minimum_size.x = width
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	result.add_theme_font_override("font", _serif_bold if bold else _serif)
	result.add_theme_font_size_override("font_size", font_size)
	result.add_theme_color_override("font_color", IVORY)
	parent.add_child(result)
	return result

func _icon(parent: Node, texture: Texture2D, width: float) -> TextureRect:
	var result := TextureRect.new()
	result.texture = texture
	result.custom_minimum_size = Vector2(width, width)
	result.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	result.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	result.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(result)
	return result

func _button(parent: Node, text: String, action: Callable) -> Button:
	var result := Button.new()
	result.text = text
	result.pressed.connect(action)
	result.add_theme_font_size_override("font_size", 13)
	for state: String in ["normal", "hover", "pressed", "focus"]:
		result.add_theme_stylebox_override(state, _style(BRONZE, Color("10272a") if state == "hover" else Color("091718"), 5))
	parent.add_child(result)
	return result

func _style(edge: Color, fill: Color, margin: float, thickness: int = 1, glow: bool = false) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = fill
	result.border_color = edge
	result.set_border_width_all(thickness)
	result.set_corner_radius_all(4)
	result.set_content_margin_all(margin)
	result.shadow_color = Color(0.25, 0.91, 0.9, 0.26) if glow else Color(0, 0, 0, 0.6)
	result.shadow_size = 7 if glow else 2
	return result
