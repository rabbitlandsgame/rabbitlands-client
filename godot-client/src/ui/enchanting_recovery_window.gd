extends PanelContainer
## Quotes identify one exact object. Only the server commits costs and returns.
const Parts := preload("res://src/ui/crafting_window_parts.gd")
const Tiers := preload("res://src/state/item_instance_tiers.gd")
const IVORY := Color("eee3c8")
const MUTED := Color("ada98f")
const BRONZE := Color("9d7951")
const CYAN := Color("62e7e5")
var main: Node
var tabs: TabBar
var copies: ItemList
var recipes: ItemList
var quantity: SpinBox
var salvage_body: HBoxContainer
var refine_body: HBoxContainer
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
var _hero: Dictionary
var _refine_details: VBoxContainer
var _heading: Label
var _purpose: Label
var _totals: Label
var _review_requested := false
var _quantity_buttons: Array[Button] = []

func configure(owner_main: Node) -> void:
	main = owner_main
	name = "EnchantingRecovery"
	theme = main.theme.duplicate() as Theme if main.theme != null else Theme.new()
	theme.default_font_size = 16
	theme.set_color("font_color", "Label", IVORY)
	add_theme_stylebox_override("panel", Parts.style(BRONZE, Color("071213"), 14))
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	add_child(content)
	var header := HBoxContainer.new()
	content.add_child(header)
	_heading = Parts.label(header, "Break Down", 26)
	_font = SystemFont.new()
	_font.font_names = PackedStringArray(["Georgia", "Noto Serif", "serif"])
	_heading.add_theme_font_override("font", _font)
	Parts.button(header, "Refresh", _refresh)
	Parts.button(header, "×", hide).tooltip_text = "Close crafting window"
	var dragger := WindowDrag.attach(self, header)
	dragger.reserved_bottom = 88
	dragger.moved.connect(func(_to: Vector2) -> void: _placed = true)
	tabs = Parts.navigation(content, 0, _navigate)
	_purpose = Parts.label(content, "", 14)
	_purpose.modulate = MUTED
	salvage_body = HBoxContainer.new()
	salvage_body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	salvage_body.add_theme_constant_override("separation", 16)
	content.add_child(salvage_body)
	var selection := VBoxContainer.new()
	selection.custom_minimum_size.x = 220
	salvage_body.add_child(selection)
	Parts.label(selection, "Backpack copies", 17)
	copies = Parts.ledger(selection)
	copies.name = "Copies"
	copies.item_selected.connect(func(index: int) -> void:
		if _pending_op == "confirm": return
		selected_id = int(copies.get_item_metadata(index))
		_invalidate()
		_update_details())
	detail_scroll = ScrollContainer.new()
	detail_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	detail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	salvage_body.add_child(detail_scroll)
	var selected := VBoxContainer.new()
	selected.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	selected.add_theme_constant_override("separation", 12)
	detail_scroll.add_child(selected)
	_hero = Parts.hero(selected)
	selected_title = _hero.title
	details = VBoxContainer.new()
	details.add_theme_constant_override("separation", 8)
	selected.add_child(details)
	refine_body = HBoxContainer.new()
	refine_body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	refine_body.add_theme_constant_override("separation", 16)
	content.add_child(refine_body)
	var recipe_selection := VBoxContainer.new()
	recipe_selection.custom_minimum_size.x = 220
	refine_body.add_child(recipe_selection)
	Parts.label(recipe_selection, "Enriched essences", 17)
	recipes = Parts.ledger(recipe_selection)
	recipes.item_selected.connect(func(_index: int) -> void:
		if _rendering or _pending_op == "confirm": return
		_invalidate()
		_update_details())
	var refine_scroll := ScrollContainer.new()
	refine_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	refine_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	refine_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	refine_body.add_child(refine_scroll)
	var refine_content := VBoxContainer.new()
	refine_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	refine_content.add_theme_constant_override("separation", 12)
	refine_scroll.add_child(refine_content)
	var amount_row := HBoxContainer.new()
	refine_content.add_child(amount_row)
	Parts.label(amount_row, "Quantity", 18)
	var less := Parts.button(amount_row, "−", func() -> void: quantity.value -= 1)
	less.custom_minimum_size.x = 44
	_quantity_buttons.append(less)
	quantity = SpinBox.new()
	quantity.min_value = 1
	quantity.max_value = 100
	quantity.value = 1
	quantity.custom_minimum_size = Vector2(94, 42)
	quantity.get_line_edit().alignment = HORIZONTAL_ALIGNMENT_CENTER
	amount_row.add_child(quantity)
	var more := Parts.button(amount_row, "+", func() -> void: quantity.value += 1)
	more.custom_minimum_size.x = 44
	_quantity_buttons.append(more)
	quantity.value_changed.connect(func(_value: float) -> void:
		if _rendering or _pending_op == "confirm": return
		_invalidate()
		_update_details())
	_refine_details = VBoxContainer.new()
	_refine_details.add_theme_constant_override("separation", 12)
	refine_content.add_child(_refine_details)
	status = Parts.label(content, "", 13)
	status.custom_minimum_size.y = 30
	var footer := Parts.card(content)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 12)
	footer.add_child(actions)
	_totals = Parts.label(actions, "", 15)
	preview_button = Parts.button(actions, "Check returns", _preview)
	confirm_button = Parts.button(actions, "Review breakdown", _review, true)
	confirm_button.custom_minimum_size.x = 190
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Review breakdown"
	confirmation.confirmed.connect(_confirm)
	add_child(confirmation)
	add_child(preload("res://src/ui/storage_ledger_frame.gd").new())
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	minimum_size_changed.connect(func() -> void: _fit.call_deferred())
	visibility_changed.connect(func() -> void:
		if not visible: _invalidate())
	hide()

func open(tab: int = 0, preferred_slot: int = -1) -> void:
	# Every way in is offered only then; this keeps a stale one from asking a
	# server that never answers.
	if not AppState.enchanting_recovery_available:
		return
	main.inventory_workspace.close_inspection()
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
	_review_requested = false
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
	if request.op == "confirm":
		for index: int in copies.item_count: copies.set_item_disabled(index, true)
		for index: int in recipes.item_count: recipes.set_item_disabled(index, true)
		for index: int in tabs.tab_count: tabs.set_tab_disabled(index, true)
		for button: Button in _quantity_buttons: button.disabled = true
		quantity.editable = false
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
		var review := _review_requested
		_review_requested = false
		if review and not quote.is_empty(): _ask_confirmation()

func _render() -> void:
	_rendering = true
	copies.clear()
	var found := false
	copies.set_meta("copy_notes", {})
	for raw: Dictionary in snapshot.get("items", []):
		var index := copies.add_item(Parts.copy_text(raw), main.call("_named_icon", int(raw.image_id), str(raw.name)))
		copies.set_item_metadata(index, int(raw.instance_id))
		Parts.copy_note(copies, raw)
		copies.set_item_custom_fg_color(index, Tiers.color(str(raw.tier)))
		copies.set_item_tooltip(index, str(raw.name) + "\n" + "\n".join(raw.effects))
		if int(raw.instance_id) == selected_id or (_preferred_slot >= 0 and int(raw.slot) == _preferred_slot):
			copies.select(index)
			selected_id = int(raw.instance_id)
			found = true
	if not found: selected_id = 0
	if snapshot.has("items"): _preferred_slot = -1
	var selected := recipes.get_selected_items()
	var chosen := recipes.get_item_text(selected[0]) if not selected.is_empty() else ""
	recipes.clear()
	for raw: Dictionary in snapshot.get("recipes", []):
		var index := recipes.add_item(str(raw.result), main.call("_named_icon", int(raw.image_id), str(raw.result)))
		if raw.result == chosen or (chosen.is_empty() and index == 0): recipes.select(index)
	quantity.editable = true
	for button: Button in _quantity_buttons: button.disabled = false
	tabs.set_tab_disabled(0, false)
	tabs.set_tab_disabled(1, false)
	tabs.set_tab_disabled(2, not AppState.enchanting_available)
	quantity.max_value = maxi(1, int(snapshot.get("max_batch", 100)))
	_rendering = false
	status.text = str(snapshot.get("error", ""))
	if status.text.is_empty(): status.text = str(snapshot.get("message", ""))
	if status.text.is_empty() and not quote.is_empty():
		status.text = "Exact returns checked. Ready to review." if tabs.current_tab == 0 else "Costs and result checked. Ready to refine."
	if not snapshot.is_empty() and not bool(snapshot.get("enabled", false)):
		status.text = "Enchanting recovery is unavailable in this world."
	_update_details()
	_fit.call_deferred()

func _copy() -> Dictionary:
	for raw: Dictionary in snapshot.get("items", []):
		if int(raw.instance_id) == selected_id: return raw
	return {}

func _recipe() -> Dictionary:
	var rows: Array = snapshot.get("recipes", [])
	var selected := recipes.get_selected_items()
	return rows[selected[0]] if not selected.is_empty() and selected[0] < rows.size() else {}

func _update_details() -> void:
	salvage_body.visible = tabs.current_tab == 0
	refine_body.visible = tabs.current_tab == 1
	_heading.text = "Break Down" if tabs.current_tab == 0 else "Refine"
	_purpose.text = "Recover materials from one enchanted copy. Backpack only · unequip or withdraw items first." if tabs.current_tab == 0 else "Combine shards and normal essences into enriched essence. Uses materials in your backpack."
	_purpose.modulate = MUTED
	preview_button.text = "Check returns" if tabs.current_tab == 0 else "Check costs"
	confirm_button.text = "Review breakdown" if tabs.current_tab == 0 else "Refine %d…" % int(quantity.value)
	var chosen := _copy() if tabs.current_tab == 0 else _recipe()
	var blocked := _busy or _stale or _pending_op == "confirm" or chosen.is_empty() or not bool(snapshot.get("enabled", false))
	preview_button.disabled = blocked
	confirm_button.disabled = blocked
	if tabs.current_tab == 0:
		_clear(details)
		Parts.show_hero(_hero, main, chosen)
		if chosen.is_empty():
			Parts.label(details, "Select an individual copy to see its effects and exact returns.")
			_totals.text = "No copy selected"
		else:
			_purpose.text = "Backpack slot %d · This individual copy will be destroyed." % (int(chosen.slot) + 1)
			_purpose.modulate = Parts.AMBER
			Parts.label(details, "Current effects", 18)
			var grid := GridContainer.new()
			grid.columns = 2 if get_viewport_rect().size.x >= 1100 else 1
			grid.add_theme_constant_override("h_separation", 8)
			grid.add_theme_constant_override("v_separation", 8)
			details.add_child(grid)
			for effect: String in chosen.effects: Parts.effect(grid, effect)
			var returns := Parts.card(details, "You receive")
			for row: Dictionary in chosen.outputs: Parts.material(returns, main, row)
			Parts.label(details, "This copy will be destroyed.", 16).modulate = Parts.AMBER
			_totals.text = "Returns\n" + Parts.summary(chosen.outputs)
	else:
		_clear(_refine_details)
		if chosen.is_empty():
			refining_text = Parts.label(_refine_details, "Choose an essence recipe.")
			_totals.text = "No recipe selected"
		else:
			var costs := Parts.card(_refine_details, "Input materials")
			Parts.cost_heading(costs)
			var count := int(quantity.value)
			var rows := [
				{"name": snapshot.get("shard_item", "Enchanting Shards"), "quantity": count * int(chosen.shard_cost), "owned": int(snapshot.get("shard_available", 0))},
				{"name": chosen.normal, "quantity": count * int(chosen.normal_cost), "owned": int(chosen.normal_available)},
				{"name": "Gold Coins", "quantity": count * int(chosen.gold_fee), "owned": int(snapshot.get("gold_available", 0))}]
			for row: Dictionary in rows: Parts.material(costs, main, row, int(row.owned))
			for row: Dictionary in rows:
				if int(row.quantity) > int(row.owned):
					preview_button.disabled = true
					confirm_button.disabled = true
					if not _busy and not _stale and status.text.is_empty(): status.text = "Not enough materials for this quantity. Reduce it or gather more."
			var result := Parts.card(_refine_details, "Result")
			Parts.material(result, main, {"name": chosen.result, "quantity": count, "image_id": chosen.image_id})
			refining_text = Parts.label(result, "Guaranteed result · no failure roll", 14)
			refining_text.modulate = CYAN
			_totals.text = "Total cost\n" + Parts.summary(rows)
	if status.text.is_empty(): status.text = "Review checks the selected copy, materials and room for your result."
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
	confirmation.title = "Review breakdown" if quote.action == "disenchant" else "Review refining"
	confirmation.ok_button_text = "Break down this copy" if quote.action == "disenchant" else "Refine"
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
	custom_minimum_size = Vector2(minf(1000, maxf(560, viewport.x - 112)), 0)
	size = Vector2(custom_minimum_size.x, minf(700, maxf(350, viewport.y - 112)))
	var desired := position if _placed else (viewport - size - Vector2(96, 88)) / 2
	position = Vector2(clampf(desired.x, 8, maxf(8, viewport.x - size.x - 104)), clampf(desired.y, 8, maxf(8, viewport.y - size.y - 96)))

func _clear(parent: Node) -> void:
	for child: Node in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func _review() -> void:
	if confirm_button.disabled: return
	if not quote.is_empty():
		_ask_confirmation()
		return
	_preview()
	_review_requested = _busy

func _navigate(index: int) -> void:
	if index == 2:
		var selected := _copy()
		hide()
		main.inventory_workspace.enchanting_window.open(int(selected.get("slot", -1)))
		return
	_invalidate()
	_update_details()
