extends PanelContainer
## Quotes identify one exact object. Only the server commits costs and returns.
const Tiers := preload("res://src/state/item_instance_tiers.gd")
const Icons := preload("res://src/ui/item_effect_icons.gd")
const IVORY := Color("eee3c8")
const MUTED := Color("ada98f")
const BRONZE := Color("9d7951")
const CYAN := Color("62e7e5")
var main: Node
var tabs: TabBar
var copies: ItemList
var recipes: OptionButton
var quantity: SpinBox
var salvage_body: HBoxContainer
var refine_body: VBoxContainer
var details: VBoxContainer
var detail_scroll: ScrollContainer
var selected_title: Label
var refining_text: Label
var status: Label
var preview_button: Button
var confirm_button: Button
var confirmation: ConfirmationDialog
var snapshot: Dictionary = {}
var selected_id := 0
var quote: Dictionary = {}
var _serial := 0
var _busy := false
var _pending_op := ""
var _rendering := false
var _stale := false
var _preferred_slot := -1
var _placed := false
## How long a request may go unanswered. A server whose copies predate
## recovery, or a practice world (which refuses it with a chat line), never
## replies, and the window must not say "Loading" for ever.
var reply_seconds := 10.0
## Sends a request; returns whether it went out. Tests stand in for the link.
var send_request: Callable = func(request: Dictionary) -> Error: return Network.enchanting_recovery_request(request)
var _font: SystemFont

func configure(owner_main: Node) -> void:
	main = owner_main
	name = "EnchantingRecovery"
	_font = SystemFont.new()
	_font.font_names = PackedStringArray(["Georgia", "Noto Serif", "DejaVu Serif", "serif"])
	theme = main.theme.duplicate() as Theme if main.theme != null else Theme.new()
	theme.default_font_size = 14
	theme.set_color("font_color", "Label", IVORY)
	add_theme_stylebox_override("panel", _style(BRONZE, Color("071213"), 14))
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 12)
	add_child(content)
	var header_panel := PanelContainer.new()
	header_panel.add_theme_stylebox_override("panel", _style(Color("3d4c43"), Color("0b2021"), 8))
	content.add_child(header_panel)
	var header := HBoxContainer.new()
	header_panel.add_child(header)
	var title := _label(header, "Disenchant & Refine", 24)
	title.add_theme_font_override("font", _font)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_button(header, "Refresh", _refresh)
	_button(header, "×", hide).tooltip_text = "Close enchanting recovery"
	var dragger := WindowDrag.attach(self, header_panel)
	dragger.reserved_bottom = 88
	dragger.moved.connect(func(_to: Vector2) -> void: _placed = true)
	tabs = TabBar.new()
	tabs.add_tab("Disenchant")
	tabs.add_tab("Refine essence")
	content.add_child(tabs)
	tabs.tab_changed.connect(func(_index: int) -> void:
		_invalidate()
		_update_details())
	var hint := _label(content, "Uses your backpack. Withdraw stored items first; unequip equipment before disenchanting.", 13)
	hint.modulate = MUTED
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	salvage_body = HBoxContainer.new()
	salvage_body.add_theme_constant_override("separation", 16)
	content.add_child(salvage_body)
	var selection := VBoxContainer.new()
	selection.custom_minimum_size.x = 240
	salvage_body.add_child(selection)
	_label(selection, "Choose an individual copy", 15)
	copies = ItemList.new()
	copies.name = "Copies"
	copies.size_flags_vertical = Control.SIZE_EXPAND_FILL
	copies.fixed_icon_size = Vector2i(42, 42)
	copies.add_theme_stylebox_override("panel", _style(Color("344e4c"), Color("0a191b"), 8))
	selection.add_child(copies)
	copies.item_selected.connect(func(index: int) -> void:
		selected_id = int(copies.get_item_metadata(index))
		_invalidate()
		_update_details())
	var selected := VBoxContainer.new()
	selected.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	salvage_body.add_child(selected)
	selected_title = _label(selected, "Select a copy", 20)
	selected_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	selected_title.add_theme_font_override("font", _font)
	detail_scroll = ScrollContainer.new()
	detail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	detail_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	selected.add_child(detail_scroll)
	details = VBoxContainer.new()
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	details.add_theme_constant_override("separation", 12)
	detail_scroll.add_child(details)
	refine_body = VBoxContainer.new()
	refine_body.add_theme_constant_override("separation", 14)
	content.add_child(refine_body)
	_label(refine_body, "Refine enriched essence", 19)
	var recipe_row := HBoxContainer.new()
	refine_body.add_child(recipe_row)
	recipes = OptionButton.new()
	recipes.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	recipes.custom_minimum_size.y = 40
	recipe_row.add_child(recipes)
	_label(recipe_row, "Quantity", 14)
	quantity = SpinBox.new()
	quantity.min_value = 1
	quantity.max_value = 100
	quantity.value = 1
	quantity.custom_minimum_size.x = 100
	recipe_row.add_child(quantity)
	recipes.item_selected.connect(func(_index: int) -> void:
		if not _rendering:
			_invalidate()
			_update_details())
	quantity.value_changed.connect(func(_value: float) -> void:
		if not _rendering:
			_invalidate()
			_update_details())
	refining_text = _label(refine_body, "", 14)
	refining_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label(refine_body, "Guaranteed result · No manufacturing failure roll", 13).modulate = CYAN
	status = _label(content, "", 14)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.custom_minimum_size.y = 36
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 12)
	content.add_child(footer)
	preview_button = _button(footer, "Preview returns", _preview)
	preview_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	confirm_button = _button(footer, "Disenchant selected…", _ask_confirmation)
	confirm_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	confirm_button.add_theme_stylebox_override("normal", _style(CYAN, Color("0e3a3e"), 10))
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Confirm enchanting recovery"
	confirmation.ok_button_text = "Confirm"
	confirmation.confirmed.connect(_confirm)
	add_child(confirmation)
	add_child(preload("res://src/ui/storage_ledger_frame.gd").new())
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	visibility_changed.connect(func() -> void:
		if not visible: _invalidate())
	hide()

func open(tab: int = 0, preferred_slot: int = -1) -> void:
	# Every way in is offered only then; this keeps a stale one from asking a
	# server that never answers.
	if not AppState.enchanting_recovery_available:
		return
	snapshot = {}
	selected_id = 0
	_preferred_slot = preferred_slot
	_placed = false
	tabs.current_tab = clampi(tab, 0, 1)
	show()
	main.window_stack.register(self)
	WindowStack.activate(self)
	_render()
	_refresh()
	_fit.call_deferred()

func _invalidate(cancel_pending: bool = true) -> void:
	quote = {}
	confirmation.hide()
	status.text = ""
	confirm_button.disabled = true
	if cancel_pending:
		_serial += 1
		_busy = false
		_pending_op = ""

func _send(request: Dictionary) -> void:
	_serial += 1
	request["request_id"] = _serial
	_busy = true
	_pending_op = str(request.op)
	preview_button.disabled = true
	confirm_button.disabled = true
	var error: Error = send_request.call(request)
	if error != OK:
		_busy = false
		status.text = "Could not contact the server: " + error_string(error)
	else:
		_await_reply()

func _await_reply() -> void:
	if is_inside_tree():
		get_tree().create_timer(reply_seconds).timeout.connect(_reply_overdue.bind(_serial))

func _reply_overdue(serial: int) -> void:
	if serial != _serial or not _busy:
		return
	_busy = false
	# A late answer still lands: it carries this request's id. A confirmation
	# stays pending, so the inventory packets the server sends ahead of its
	# receipt do not cancel it, and Preview stays locked until it comes.
	if _pending_op == "confirm":
		status.text = "No answer from the server yet. Refresh to see whether it went through."
		return
	_pending_op = ""
	status.text = ("The server did not answer. Disenchanting and refining are not available here." if snapshot.is_empty()
		else "The server has not answered yet. Try again.")
	_update_details()

func _refresh() -> void:
	_invalidate()
	status.text = "Loading recovery options…"
	_send({"op": "list"})

func _state_changed(part: StringName) -> void:
	if part == &"connection" and not AppState.authenticated:
		hide()
		snapshot = {}
	elif visible and part == &"inventory":
		# A confirmation sends inventory updates before its final receipt.
		_stale = true
		_invalidate(_pending_op != "confirm")
		status.text = "Your inventory changed. Refresh to check the available copies and materials."
		preview_button.disabled = true
	elif visible and part == &"enchanting_recovery":
		var incoming: Dictionary = AppState.enchanting_recovery
		if int(incoming.get("request_id", -1)) != _serial: return
		snapshot = incoming
		_stale = false
		quote = snapshot.get("quote", {}) if snapshot.get("quote") is Dictionary else {}
		_busy = false
		_pending_op = ""
		_render()

func _render() -> void:
	_rendering = true
	copies.clear()
	var found := false
	for raw: Dictionary in snapshot.get("items", []):
		var index := copies.add_item("Slot %d · %s" % [int(raw.slot) + 1, raw.name], main.call("_named_icon", int(raw.image_id), str(raw.name)))
		copies.set_item_metadata(index, int(raw.instance_id))
		copies.set_item_custom_fg_color(index, Tiers.color(str(raw.tier)))
		copies.set_item_tooltip(index, str(raw.name) + "\n" + "\n".join(raw.effects))
		if int(raw.instance_id) == selected_id or (_preferred_slot >= 0 and int(raw.slot) == _preferred_slot):
			copies.select(index)
			selected_id = int(raw.instance_id)
			found = true
	if not found: selected_id = 0
	if snapshot.has("items"): _preferred_slot = -1
	var chosen := recipes.get_item_text(recipes.selected) if recipes.selected >= 0 else ""
	recipes.clear()
	for raw: Dictionary in snapshot.get("recipes", []):
		var index := recipes.item_count
		recipes.add_icon_item(main.call("_named_icon", int(raw.image_id), str(raw.result)), str(raw.result))
		if raw.result == chosen: recipes.select(index)
	quantity.max_value = maxi(1, int(snapshot.get("max_batch", 100)))
	_rendering = false
	status.text = str(snapshot.get("error", ""))
	if status.text.is_empty(): status.text = str(snapshot.get("message", ""))
	if status.text.is_empty() and not quote.is_empty():
		status.text = "Preview checked. Review the returns, then confirm below."
	if not snapshot.is_empty() and not bool(snapshot.get("enabled", false)):
		status.text = "Enchanting recovery is unavailable in this world."
	_update_details()
	_fit.call_deferred()

func _copy() -> Dictionary:
	for raw: Dictionary in snapshot.get("items", []):
		if int(raw.instance_id) == selected_id: return raw
	return {}

func _recipe() -> Dictionary:
	var options: Array = snapshot.get("recipes", [])
	return options[recipes.selected] if recipes.selected >= 0 and recipes.selected < options.size() else {}

func _update_details() -> void:
	salvage_body.visible = tabs.current_tab == 0
	refine_body.visible = tabs.current_tab == 1
	preview_button.text = "Preview returns" if tabs.current_tab == 0 else "Preview costs"
	confirm_button.text = "Disenchant selected…" if tabs.current_tab == 0 else "Refine essence…"
	var chosen := _copy() if tabs.current_tab == 0 else _recipe()
	preview_button.disabled = _busy or _stale or chosen.is_empty() or not bool(snapshot.get("enabled", false))
	confirm_button.disabled = _busy or quote.is_empty()
	if tabs.current_tab == 0:
		for child: Node in details.get_children():
			details.remove_child(child)
			child.queue_free()
		selected_title.text = "Select a copy" if chosen.is_empty() else str(chosen.name)
		selected_title.add_theme_color_override("font_color", Tiers.color(str(chosen.get("tier", "normal"))))
		if chosen.is_empty():
			_label(details, "Choose an enchanted backpack item to see its effects and exact returns.", 14).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		else:
			_label(details, "Quality %d%% · Durability %d / %d" % [chosen.quality, chosen.durability, chosen.max_durability], 13).modulate = MUTED
			for effect: String in chosen.effects:
				var line := HBoxContainer.new()
				line.add_theme_constant_override("separation", 10)
				details.add_child(line)
				var icon := TextureRect.new()
				icon.texture = Icons.texture(str(Icons.presentation(effect).name))
				icon.custom_minimum_size = Vector2(28, 28)
				icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
				icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
				line.add_child(icon)
				var description := _label(line, effect, 14)
				description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			_label(details, "You receive", 16).modulate = CYAN
			_label(details, _materials(chosen.outputs), 14).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	else:
		refining_text.text = "Choose an essence recipe." if chosen.is_empty() else "Cost for %d:\n%s\n\nYou receive: %d %s\n\nIn your backpack: %d shards · %d %s · %d gold" % [int(quantity.value), _refine_cost(chosen), int(quantity.value), chosen.result, int(snapshot.get("shard_available", 0)), int(chosen.normal_available), chosen.normal, int(snapshot.get("gold_available", 0))]
	if status.text.is_empty():
		status.text = ("No enchanted backpack copies available." if chosen.is_empty() else "Disenchanting permanently consumes the selected individual copy.") if tabs.current_tab == 0 else "Preview checks the cost and room for your enriched essence."
	_fit.call_deferred()

func _materials(rows: Array) -> String:
	var lines := PackedStringArray()
	for row: Dictionary in rows: lines.append("%d %s" % [int(row.quantity), str(row.name)])
	return "\n".join(lines)

func _refine_cost(recipe: Dictionary) -> String:
	var count := int(quantity.value)
	return "%d %s\n%d %s\n%d gold fee" % [count * int(recipe.shard_cost), str(snapshot.get("shard_item", "Enchanting Shards")), count * int(recipe.normal_cost), recipe.normal, count * int(recipe.gold_fee)]

func _preview() -> void:
	_invalidate()
	if tabs.current_tab == 0 and selected_id > 0:
		_send({"op": "quote", "action": "disenchant", "instance_id": selected_id})
	elif tabs.current_tab == 1 and not _recipe().is_empty():
		_send({"op": "quote", "action": "refine", "normal": _recipe().normal, "quantity": int(quantity.value)})
	status.text = "Checking the selected copy, costs and room for the result…" if _busy else status.text

func _ask_confirmation() -> void:
	if quote.is_empty() or _busy: return
	var warning := "Permanently consume this individual %s?\n\n%s\n\n" % [quote.name, "\n".join(quote.get("effects", []))] if quote.action == "disenchant" else "Spend these materials?\n\n"
	confirmation.dialog_text = warning + "Consumed:\n" + _materials(quote.inputs) + "\nGold fee: %d\n\nYou receive:\n" % int(quote.gold_fee) + _materials(quote.outputs)
	confirmation.popup_centered(Vector2i(470, 0))

func _confirm() -> void:
	if quote.is_empty() or _busy: return
	var token := str(quote.token)
	quote = {}
	_send({"op": "confirm", "token": token})
	status.text = "Completing recovery…" if _busy else status.text

func _fit() -> void:
	if not is_inside_tree() or not visible: return
	var viewport := get_viewport_rect().size
	custom_minimum_size = Vector2(minf(820, maxf(570, viewport.x - 112)), 0)
	salvage_body.custom_minimum_size.y = minf(360, maxf(170, viewport.y - 375))
	refine_body.custom_minimum_size.y = salvage_body.custom_minimum_size.y
	size = get_combined_minimum_size()
	var desired := position if _placed else (viewport - size - Vector2(96, 88)) / 2
	position = Vector2(clampf(desired.x, 8, maxf(8, viewport.x - size.x - 104)), clampf(desired.y, 8, maxf(8, viewport.y - size.y - 96)))

func _label(parent: Node, text: String, font_size: int) -> Label:
	var result := Label.new()
	result.text = text
	result.add_theme_font_size_override("font_size", font_size)
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(result)
	return result

func _button(parent: Node, text: String, action: Callable) -> Button:
	var result := Button.new()
	result.text = text
	result.custom_minimum_size.y = 34
	result.pressed.connect(action)
	for state: String in ["normal", "hover", "pressed", "focus"]:
		result.add_theme_stylebox_override(state, _style(BRONZE, Color("10272a") if state == "hover" else Color("091718"), 8))
	parent.add_child(result)
	return result

func _style(edge: Color, fill: Color, margin: float) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = fill
	result.border_color = edge
	result.set_border_width_all(1)
	result.set_corner_radius_all(4)
	result.set_content_margin_all(margin)
	return result
