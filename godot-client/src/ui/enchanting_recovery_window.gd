extends PanelContainer
## Quotes identify one exact object. Only the server commits costs and returns.
const Parts := preload("res://src/ui/crafting_window_parts.gd")
const Workbench := preload("res://src/ui/crafting_workbench.gd")
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
var salvage_body: VBoxContainer
var refine_body: VBoxContainer
var details: VBoxContainer
var detail_scroll: ScrollContainer
var selected_title: Label
var refining_text: Label
var status: Label
var _more: MenuButton
var _costs: VBoxContainer
var _refine_hero: Dictionary
var quote_delay := 0.18
var _quote_revision := 0
var _refresh_queued := false
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
var _hero: Dictionary
var _heading: Label
var _purpose: Label
var _totals: Label
var _review_requested := false
var _quantity_buttons: Array[Button] = []
var location_controls: VBoxContainer
var _source := "backpack"
var _offset := 0
var _preferred_id := 0
var _copies_heading: Label

func configure(owner_main: Node) -> void:
	main = owner_main
	name = "EnchantingRecovery"
	var frame := Workbench.build(self, main, 0, _navigate, _refresh, _preview, _review)
	_heading = frame.title
	tabs = frame.tabs
	status = frame.status
	_totals = frame.totals
	confirm_button = frame.confirm
	_more = frame.more
	_costs = frame.costs
	(frame.odds as HBoxContainer).hide()
	detail_scroll = frame.scroll
	(frame.dragger as WindowDrag).moved.connect(func(_to: Vector2) -> void: _placed = true)
	var left: VBoxContainer = frame.left
	location_controls = preload("res://src/ui/crafting_location_controls.gd").new()
	left.add_child(location_controls)
	location_controls.location_changed.connect(func(location: String) -> void:
		_source = location
		_offset = 0
		selected_id = 0
		_preferred_slot = -1
		snapshot = {}
		_render()
		_refresh())
	location_controls.page_changed.connect(func(offset: int) -> void:
		_offset = offset
		selected_id = 0
		_refresh())
	_copies_heading = Parts.label(left, "Backpack copies", 11)
	copies = Parts.ledger(left)
	copies.name = "Copies"
	copies.item_selected.connect(func(index: int) -> void:
		if _pending_op == "confirm": return
		selected_id = int(copies.get_item_metadata(index))
		_invalidate()
		_update_details()
		_queue_quote())
	recipes = Parts.ledger(left)
	recipes.item_selected.connect(func(_index: int) -> void:
		if _rendering or _pending_op == "confirm": return
		_invalidate()
		_update_details()
		_queue_quote())
	var right: VBoxContainer = frame.right
	salvage_body = VBoxContainer.new()
	salvage_body.add_theme_constant_override("separation", 5)
	right.add_child(salvage_body)
	_hero = Parts.hero(salvage_body)
	selected_title = _hero.title
	details = VBoxContainer.new()
	details.custom_minimum_size.y = 128
	details.add_theme_constant_override("separation", 0)
	salvage_body.add_child(details)
	refine_body = VBoxContainer.new()
	refine_body.add_theme_constant_override("separation", 5)
	right.add_child(refine_body)
	_refine_hero = Parts.hero(refine_body)
	var amount_row := HBoxContainer.new()
	amount_row.add_theme_constant_override("separation", 4)
	refine_body.add_child(amount_row)
	Parts.label(amount_row, "Quantity", 11)
	var less := Parts.button(amount_row, "−", func() -> void: quantity.value -= 1)
	_quantity_buttons.append(less)
	quantity = SpinBox.new()
	quantity.min_value = 1
	quantity.max_value = 100
	quantity.value = 1
	quantity.custom_minimum_size = Vector2(64, 26)
	quantity.get_line_edit().alignment = HORIZONTAL_ALIGNMENT_CENTER
	amount_row.add_child(quantity)
	var more := Parts.button(amount_row, "+", func() -> void: quantity.value += 1)
	_quantity_buttons.append(more)
	quantity.value_changed.connect(func(_value: float) -> void:
		if _rendering or _pending_op == "confirm": return
		_invalidate()
		_update_details()
		_queue_quote())
	refining_text = Parts.label(refine_body, "Guaranteed result · no failure roll", 11)
	_purpose = Parts.label(right, "", 11)
	_purpose.hide()
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Review breakdown"
	confirmation.confirmed.connect(_confirm)
	add_child(confirmation)
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	visibility_changed.connect(func() -> void:
		if not visible: _invalidate())
	hide()

func open(tab: int = 0, preferred_slot: int = -1, location: String = "backpack", preferred_id: int = 0) -> void:
	# Every way in is offered only then; this keeps a stale one from asking a
	# server that never answers.
	if not AppState.enchanting_recovery_available:
		return
	main.inventory_workspace.close_inspection()
	snapshot = {}
	selected_id = 0
	_source = location
	_offset = 0
	_preferred_id = preferred_id
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
	_quote_revision += 1
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
	request["source"] = _source
	request["offset"] = _offset
	if request.op == "list" and _preferred_id > 0: request["focus"] = _preferred_id
	location_controls.render(snapshot, _source, true, tabs.current_tab == 0)
	_busy = true
	_pending_op = str(request.op)
	_more.get_popup().set_item_disabled(1, true)
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
		status.text = "No answer yet. Use ••• → Retry connection to check the result."
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
	elif visible and (part == &"inventory" or part == &"storage"):
		# A confirmation sends inventory updates before its final receipt.
		_stale = true
		_invalidate(_pending_op != "confirm")
		status.text = "Updating copies and material costs…"
		if not _refresh_queued:
			_refresh_queued = true
			_refresh_changed_equipment.call_deferred()
		_more.get_popup().set_item_disabled(1, true)
	elif visible and part == &"enchanting_recovery":
		var incoming: Dictionary = AppState.enchanting_recovery
		if int(incoming.get("request_id", -1)) != _serial: return
		if str(incoming.get("source", "backpack")) != _source: return
		var completed := _pending_op
		snapshot = incoming
		_stale = false
		quote = snapshot.get("quote", {}) if snapshot.get("quote") is Dictionary else {}
		_busy = false
		_pending_op = ""
		_render()
		var review := _review_requested
		_review_requested = false
		if review and not quote.is_empty(): _ask_confirmation()
		elif completed == "list": _queue_quote()

func _render() -> void:
	_rendering = true
	_offset = int(snapshot.get("offset", _offset))
	location_controls.render(snapshot, _source, _pending_op == "confirm", tabs.current_tab == 0)
	_copies_heading.text = "Storage copies" if _source == "storage" else "Backpack copies"
	copies.clear()
	var found := false
	copies.set_meta("copy_notes", {})
	for raw: Dictionary in snapshot.get("items", []):
		var index := copies.add_item(Parts.copy_text(raw), main.call("_named_icon", int(raw.image_id), str(raw.name)))
		copies.set_item_metadata(index, int(raw.instance_id))
		Parts.copy_note(copies, raw)
		copies.set_item_custom_fg_color(index, Tiers.color(str(raw.tier)))
		copies.set_item_tooltip(index, str(raw.name) + "\n" + "\n".join(raw.effects))
		if int(raw.instance_id) == selected_id or int(raw.instance_id) == _preferred_id or (_source == "backpack" and _preferred_slot >= 0 and int(raw.slot) == _preferred_slot):
			copies.select(index)
			selected_id = int(raw.instance_id)
			found = true
	if not found: selected_id = 0
	if snapshot.has("items"):
		_preferred_slot = -1
		_preferred_id = 0
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
	location_controls.render(snapshot, _source, _busy or _pending_op == "confirm", tabs.current_tab == 0)
	var breaking := tabs.current_tab == 0
	salvage_body.visible = breaking
	refine_body.visible = not breaking
	copies.visible = breaking
	recipes.visible = not breaking
	_copies_heading.text = ("Storage copies" if _source == "storage" else "Backpack copies") if breaking else "Enriched essences"
	confirm_button.text = "Review breakdown" if breaking else "Review refine ×%d" % int(quantity.value)
	var chosen := _copy() if breaking else _recipe()
	var blocked := _busy or _stale or _pending_op == "confirm" or chosen.is_empty() or not bool(snapshot.get("enabled", false))
	_more.get_popup().set_item_disabled(1, blocked)
	confirm_button.disabled = blocked
	_clear(_costs)
	_totals.text = "Returns" if breaking else "Total cost"
	if breaking:
		_clear(details)
		Parts.show_hero(_hero, main, chosen)
		if chosen.is_empty():
			Parts.label(details, "Select an individual copy to see its effects and exact returns.", 11)
		else:
			for effect: String in chosen.effects: Parts.effect(details, effect)
			Parts.label(details, "This copy will be destroyed.", 11).modulate = Parts.AMBER
			Parts.label(_costs, "You receive", 11)
			var outputs: Array = quote.get("outputs", chosen.outputs)
			for row: Dictionary in outputs: Parts.material(_costs, main, row)
			_totals.tooltip_text = Parts.summary(outputs)
	else:
		(_refine_hero.title as Label).text = str(chosen.get("result", "Choose an essence recipe"))
		(_refine_hero.icon as TextureRect).texture = main.call("_named_icon", int(chosen.image_id), str(chosen.result)) if not chosen.is_empty() else null
		(_refine_hero.condition as Label).text = "Result stays in " + _source
		(_refine_hero.slots as Label).text = "×%d enriched essence" % int(quantity.value)
		if not chosen.is_empty():
			Parts.cost_heading(_costs)
			var count := int(quantity.value)
			var rows := [
				{"name": snapshot.get("shard_item", "Enchanting Shards"), "quantity": count * int(chosen.shard_cost), "owned": int(snapshot.get("shard_available", 0))},
				{"name": chosen.normal, "quantity": count * int(chosen.normal_cost), "owned": int(chosen.normal_available)},
				{"name": "Gold Coins", "quantity": count * int(chosen.gold_fee), "owned": int(snapshot.get("gold_available", 0))}]
			for row: Dictionary in rows:
				Parts.material(_costs, main, row, int(row.owned))
				if int(row.quantity) > int(row.owned):
					_more.get_popup().set_item_disabled(1, true)
					confirm_button.disabled = true
					if not _busy and not _stale and status.text.is_empty(): status.text = "Not enough materials. Reduce the amount or gather more."
			_totals.tooltip_text = Parts.summary(rows)
	if status.text.is_empty(): status.text = "Costs current · Review checks the exact copy and materials."
	status.tooltip_text = status.text
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
	confirmation.dialog_text = warning + "Location: %s\n\nConsumed:\n" % _source.capitalize() + _materials(quote.inputs) + "\nGold fee: %d\n\nYou receive:\n" % int(quote.gold_fee) + _materials(quote.outputs)
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
	Workbench.fit(self, _placed)

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
		var next_position := position
		hide()
		var next: Control = main.inventory_workspace.enchanting_window
		next.open(int(selected.get("slot", -1)), _source, int(selected.get("instance_id", 0)))
		next.position = next_position
		next.set("_placed", true)
		next.call("_fit")
		return
	_invalidate()
	_update_details()
	_queue_quote()

func _refresh_changed_equipment() -> void:
	_refresh_queued = false
	if not visible or not _stale or _pending_op == "confirm": return
	_preferred_id = selected_id
	_refresh()

func _queue_quote() -> void:
	var revision := _quote_revision
	if not visible: return
	get_tree().create_timer(quote_delay).timeout.connect(func() -> void:
		if revision != _quote_revision or not visible or _busy or _stale or _pending_op == "confirm": return
		if _more.get_popup().is_item_disabled(1): return
		_preview())
