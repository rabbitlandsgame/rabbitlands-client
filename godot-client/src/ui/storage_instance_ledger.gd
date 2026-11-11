extends PanelContainer
## Selection is local; only the server can move the selected exact object.
const Tiers := preload("res://src/state/item_instance_tiers.gd")
var main: Node
var item_name := ""
var selected_id := 0
var offset := 0
var snapshot: Dictionary = {}
var heading: Label
var rows: VBoxContainer
var status: Label
var summary: Label
var withdraw: Button
var previous: Button
var next: Button
var page: Label
var scroll: ScrollContainer
var _layout_pending := false
var _placed := false

func configure(owner_main: Node, window_theme: Theme) -> void:
	main = owner_main
	name = "StorageInstanceLedger"
	theme = window_theme
	z_index = 80
	add_theme_stylebox_override("panel", _style(Color("896234"), 12))
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	add_child(content)
	var header := HBoxContainer.new()
	content.add_child(header)
	heading = _label(header, "Enchanted equipment", 0)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_theme_font_size_override("font_size", 18)
	heading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var close := _button(header, "×", hide)
	close.tooltip_text = "Close enchanted equipment"
	close.custom_minimum_size = Vector2(24, 24)
	WindowDrag.attach(self, header)
	var columns := HBoxContainer.new()
	content.add_child(columns)
	_label(columns, "Item", 180)
	_label(columns, "Saved effects", 0).size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_label(columns, "Condition", 100)
	scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	content.add_child(scroll)
	rows = VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 6)
	scroll.add_child(rows)
	var pages := HBoxContainer.new()
	content.add_child(pages)
	previous = _button(pages, "Previous", func() -> void: _request_page(maxi(0, offset - 20)))
	page = _label(pages, "", 0)
	page.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	next = _button(pages, "Next", func() -> void: _request_page(offset + 20))
	status = _label(content, "", 0)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var footer := HBoxContainer.new()
	content.add_child(footer)
	summary = _label(footer, "Select a copy to withdraw.", 0)
	summary.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	withdraw = _button(footer, "Withdraw selected", _withdraw_selected)
	withdraw.custom_minimum_size = Vector2(140, 30)
	withdraw.disabled = true
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	minimum_size_changed.connect(_queue_fit)
	hide()

func open(item: String) -> void:
	item_name = item
	selected_id = 0
	_placed = false
	snapshot = {}
	heading.text = item + " · Enchanted copies"
	status.text = "Loading saved effects…"
	_clear_rows()
	withdraw.disabled = true
	show()
	var stack: Node = main.get("window_stack") as Node
	if stack != null:
		stack.call("register", self)
	preload("res://src/ui/window_stack.gd").activate(self)
	_fit()
	_request_page(0)

func _request_page(start: int) -> void:
	var error: Error = Network.storage_instance_request(item_name, start)
	if error != OK: status.text = "Could not load stored copies: " + error_string(error)

func _state_changed(part: StringName) -> void:
	if part == &"storage" and not bool(AppState.storage.get("open", false)):
		hide()
		snapshot = {}
	elif part == &"storage_instances" and visible:
		var incoming: Dictionary = AppState.storage.get("instances", {})
		if str(incoming.get("name", "")) == item_name:
			snapshot = incoming
			offset = int(snapshot.get("offset", 0))
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
	page.text = "%d–%d of %d" % [offset + 1 if not copies.is_empty() else 0,
		offset + copies.size(), int(snapshot.get("total", 0))]
	status.text = str(snapshot.get("error", ""))
	if bool(snapshot.get("read_only", false)):
		status.text = "Storage preview · Visit a keeper or chest to withdraw."
	elif copies.is_empty() and status.text.is_empty():
		status.text = "No enchanted copies remain in storage."
	_update_selection()
	_fit()
	_queue_fit()

func _add_row(copy: Dictionary) -> void:
	var panel := PanelContainer.new()
	panel.name = "Copy%d" % int(copy.instance_id)
	panel.set_meta("instance_id", int(copy.instance_id))
	panel.add_theme_stylebox_override("panel", _style(Color("896234"), 8))
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			selected_id = int(copy.instance_id)
			_update_selection()
			panel.accept_event())
	rows.add_child(panel)
	var line := HBoxContainer.new()
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line.add_theme_constant_override("separation", 12)
	panel.add_child(line)
	var item := VBoxContainer.new()
	item.custom_minimum_size.x = 164
	item.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line.add_child(item)
	var tier: String = str(copy.get("tier", "magic"))
	var title := _label(item, Tiers.display_name(item_name, tier), 164)
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title.add_theme_color_override("font_color", Tiers.color(tier))
	var choose := Button.new()
	choose.text = "Select copy"
	choose.icon = main.call("_named_icon", int(snapshot.get("image_id", 0)), item_name) as Texture2D
	choose.add_theme_constant_override("icon_max_width", 36)
	choose.pressed.connect(func() -> void:
		selected_id = int(copy.instance_id)
		_update_selection())
	item.add_child(choose)
	var effect_column := VBoxContainer.new()
	effect_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	effect_column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line.add_child(effect_column)
	var effects := GridContainer.new()
	effects.columns = 2 if get_viewport_rect().size.x >= 1050 else 1
	effects.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	effects.mouse_filter = Control.MOUSE_FILTER_IGNORE
	effects.add_theme_constant_override("h_separation", 14)
	effects.add_theme_constant_override("v_separation", 6)
	effect_column.add_child(effects)
	for effect: Variant in copy.get("effects", []):
		var text := _label(effects, str(effect), 175)
		text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if str(copy.get("stats", "")) != str(copy.get("base_stats", "")):
		var final_stats := _label(effect_column, "Final: " + str(copy.get("stats", "")), 175)
		final_stats.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		final_stats.tooltip_text = "Base: %s\nFinal: %s" % [copy.get("base_stats", ""), copy.get("stats", "")]
	var current: Variant = copy.get("durability")
	var maximum: Variant = copy.get("max_durability")
	var condition := _label(line, "%s / %s\nQuality %d" % [
		"—" if current == null else str(int(current)), "—" if maximum == null else str(int(maximum)), int(copy.get("quality", 100))], 88)
	condition.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	condition.tooltip_text = "Condition and quality of this exact copy"

func _update_selection() -> void:
	for row: PanelContainer in rows.get_children():
		var selected: bool = int(row.get_meta("instance_id")) == selected_id
		var box := _style(Color("7cc6d4") if selected else Color("896234"), 8)
		if selected: box.bg_color = Color("101c1e")
		row.add_theme_stylebox_override("panel", box)
	withdraw.disabled = selected_id <= 0 or bool(snapshot.get("read_only", false))
	summary.text = "Select a copy to withdraw."
	for copy: Dictionary in snapshot.get("rows", []):
		if int(copy.instance_id) == selected_id:
			summary.text = "%s · %d saved effects" % [Tiers.display_name(item_name, str(copy.get("tier", "magic"))), (copy.effects as Array).size()]
			summary.add_theme_color_override("font_color", Tiers.color(str(copy.get("tier", "magic"))))

func _withdraw_selected() -> void:
	if withdraw.disabled: return
	var error: Error = Network.storage_instance_request(item_name, offset, selected_id)
	status.text = "Withdrawing selected copy…" if error == OK else "Could not withdraw: " + error_string(error)
	withdraw.disabled = true

func _fit() -> void:
	if not is_inside_tree(): return
	var viewport: Vector2 = get_viewport_rect().size
	set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	custom_minimum_size = Vector2(minf(900, maxf(580, viewport.x - 112)), 0)
	scroll.custom_minimum_size = Vector2(0, minf(370, maxf(150, viewport.y - 240)))
	size = get_combined_minimum_size()
	var desired: Vector2 = position if _placed else Vector2(405, 100)
	position = Vector2(clampf(desired.x, 8, maxf(8, viewport.x - size.x - 104)), clampf(desired.y, 8, maxf(8, viewport.y - size.y - 48)))
	_placed = size.x <= viewport.x - 104 and size.y <= viewport.y - 48

func _queue_fit() -> void:
	if _layout_pending or not visible or not is_inside_tree(): return
	_layout_pending = true
	_settle_fit.call_deferred()

func _settle_fit() -> void:
	await get_tree().process_frame
	_layout_pending = false
	if is_inside_tree() and visible: _fit()

func _label(parent: Node, text: String, width: float) -> Label:
	var result := Label.new()
	result.text = text
	result.custom_minimum_size.x = width
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(result)
	return result

func _button(parent: Node, text: String, action: Callable) -> Button:
	var result := Button.new()
	result.text = text
	result.pressed.connect(action)
	parent.add_child(result)
	return result

func _style(border: Color, margin: float) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = Color("05090a")
	result.border_color = border
	result.set_border_width_all(1)
	result.set_content_margin_all(margin)
	return result
