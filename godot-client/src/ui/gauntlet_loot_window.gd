extends Control
## Party ledger: all quantities and deliveries are server-owned snapshots.

const Art := preload("res://src/ui/leaderboard_art.gd")
const Portraits := preload("res://src/ui/leaderboard_portraits.gd")
const Medallion := preload("res://src/ui/party_medallion.gd")
const GOLD := Color("e9bd83")
const TEXT := Color("e9e1cf")
const MUTED := Color("9eaaa6")
const CYAN := Color("7cc6d4")
const BRONZE := Color("896234")
const GREEN := Color("94d789")

var panel: PanelContainer
var reopen: Button
var announcement: PanelContainer
var announcement_text: Label
var heading: Label
var route: Label
var hint: Label
var table: VBoxContainer
var deliveries: VBoxContainer
var split_button: Button
var clear_button: Button
var send_button: Button
var approve_button: Button
var status: Label
var pager: Label
var previous_button: Button
var next_button: Button
var editor: ConfirmationDialog
var confirmation: ConfirmationDialog
var price_dialog: ConfirmationDialog
var sale_dialog: ConfirmationDialog
var price_amount: SpinBox
var sale_amount: SpinBox
var sale_description: Label
var editor_total: Label
var editor_fields: Dictionary = {}
var portraits: Node
var _portrait_nodes: Dictionary = {}
var _state: Dictionary = {}
var _atlas: ItemAtlas
var _send: Callable
var _content: VBoxContainer
var _columns: HBoxContainer
var _ledger: PanelContainer
var _storage: PanelContainer
var _editing: Dictionary = {}
var _edit_revision := -1
var _confirm_revision := -1
var _pending_since := 0
var _last_notice := ""
var _compact_view := true
var _priced_row: Dictionary = {}
var _sold_row: Dictionary = {}
var _price_revision := -1
var _sale_revision := -1

func _ready() -> void:
	name = "GauntletLootLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_send = func(text: String) -> Error: return Network.send_chat(text)
	portraits = Portraits.new()
	add_child(portraits)
	portraits.portrait_ready.connect(_portrait_ready)
	_build()
	AppState.state_changed.connect(_on_state_changed)
	get_viewport().size_changed.connect(_layout)
	set_process(false)
	apply_snapshot(AppState.gauntlet_loot)

func configure(atlas: ItemAtlas, registry: Dictionary = {}, equipment: Dictionary = {}) -> void:
	_atlas = atlas
	if not registry.is_empty(): portraits.configure(registry, equipment)

func configure_sender(sender: Callable) -> void:
	_send = sender

static func style(border := BRONZE, background := Color("080f10"), margin := 10) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = background
	box.border_color = border
	box.set_border_width_all(1)
	box.set_corner_radius_all(3)
	box.set_content_margin_all(margin)
	return box

func _label(parent: Node, text: String, font_size := 14, color := TEXT) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, action: Callable, primary := false) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 34
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", Color("071316") if primary else GOLD)
	button.add_theme_color_override("font_hover_color", TEXT)
	button.add_theme_stylebox_override("normal", style(CYAN if primary else BRONZE,
		Color("80c4d2") if primary else Color("0c1719"), 9))
	button.add_theme_stylebox_override("hover", style(CYAN, Color("23383d"), 9))
	button.add_theme_stylebox_override("pressed", style(CYAN, Color("162a2f"), 9))
	button.add_theme_stylebox_override("disabled", style(Color("454d4a"), Color("171e1f"), 9))
	button.add_theme_stylebox_override("focus", style(CYAN, Color(0, 0, 0, 0), 9))
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _build() -> void:
	reopen = _button(self, "Gauntlet loot", _open)
	reopen.hide()
	announcement = PanelContainer.new()
	announcement.add_theme_stylebox_override("panel", style(BRONZE, Color("081314"), 10))
	announcement.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(announcement)
	announcement_text = _label(announcement, "", 15, GOLD)
	announcement_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	announcement_text.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	announcement.hide()
	panel = PanelContainer.new()
	panel.name = "GauntletLootWindow"
	panel.add_theme_stylebox_override("panel", style(BRONZE, Color("050d0e"), 17))
	add_child(panel)
	panel.draw.connect(func() -> void: Art.frame(panel, GOLD.darkened(0.15)))
	panel.resized.connect(func() -> void: panel.queue_redraw())
	panel.visibility_changed.connect(func() -> void: portraits.set_active(panel.visible))
	_content = VBoxContainer.new()
	_content.add_theme_constant_override("separation", 7)
	panel.add_child(_content)
	var title_row := HBoxContainer.new()
	_content.add_child(title_row)
	var title_spacer := Control.new()
	title_spacer.custom_minimum_size.x = 32
	title_row.add_child(title_spacer)
	heading = _label(title_row, "GAUNTLET COMPLETE", 27, GOLD)
	heading.add_theme_font_override("font", Art.title_font())
	heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_button(title_row, "×", close)
	route = _label(_content, "", 19, GOLD)
	route.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	route.add_theme_font_override("font", Art.title_font())
	hint = _label(_content, "All creature drops held until completion.", 13, MUTED)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_columns = HBoxContainer.new()
	_columns.add_theme_constant_override("separation", 12)
	_columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_child(_columns)
	_ledger = PanelContainer.new()
	_ledger.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_ledger.size_flags_stretch_ratio = 2.2
	_ledger.add_theme_stylebox_override("panel", style())
	_columns.add_child(_ledger)
	var left := VBoxContainer.new()
	left.add_theme_constant_override("separation", 8)
	_ledger.add_child(left)
	var header := HBoxContainer.new()
	left.add_child(header)
	var item_header := _label(header, "Item", 15, GOLD)
	item_header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item_header.size_flags_stretch_ratio = 1.25
	_label(header, "Total", 14, GOLD).custom_minimum_size.x = 54
	var recipient_header := _label(header, "Recipient / allocation", 14, GOLD)
	recipient_header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	recipient_header.size_flags_stretch_ratio = 1.0
	_label(header, "Quantity", 14, GOLD).custom_minimum_size.x = 64
	_label(header, "Gold value / NPC", 12, GOLD).custom_minimum_size.x = 126
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	left.add_child(scroll)
	table = VBoxContainer.new()
	table.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	table.add_theme_constant_override("separation", 4)
	scroll.add_child(table)
	var page_row := HBoxContainer.new()
	left.add_child(page_row)
	previous_button = _button(page_row, "‹", func() -> void: _page(-1))
	pager = _label(page_row, "", 12, MUTED)
	pager.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	next_button = _button(page_row, "›", func() -> void: _page(1))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 8)
	left.add_child(tools)
	split_button = _button(tools, "Split common equally", func() -> void: _request("split"))
	split_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	clear_button = _button(tools, "Clear assignments", func() -> void: _request("clear"))
	_storage = PanelContainer.new()
	_storage.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_storage.size_flags_stretch_ratio = 1.0
	_storage.add_theme_stylebox_override("panel", style())
	_columns.add_child(_storage)
	var right := VBoxContainer.new()
	_storage.add_child(right)
	_label(right, "Storage deliveries", 20, GOLD).add_theme_font_override("font", Art.title_font())
	var delivery_scroll := ScrollContainer.new()
	delivery_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	delivery_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(delivery_scroll)
	deliveries = VBoxContainer.new()
	deliveries.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	deliveries.add_theme_constant_override("separation", 8)
	delivery_scroll.add_child(deliveries)
	status = _label(_content, "", 13, MUTED)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	_content.add_child(footer)
	var reserved := _label(footer, "Unsent items remain in escrow.", 12, MUTED)
	reserved.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	approve_button = _button(footer, "Approve my payment", _approve_payment)
	approve_button.hide()
	_button(footer, "Refresh", _open)
	_button(footer, "Save & close", close)
	send_button = _button(footer, "CONFIRM & SEND TO STORAGE", _confirm_send, true)
	editor = ConfirmationDialog.new()
	editor.title = "Allocate item quantities"
	editor.ok_button_text = "Apply allocation"
	editor.confirmed.connect(_apply_editor)
	add_child(editor)
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Send gauntlet loot to storage"
	confirmation.ok_button_text = "Send to storage"
	confirmation.confirmed.connect(func() -> void: _request("send", {}, _confirm_revision))
	add_child(confirmation)
	price_dialog = ConfirmationDialog.new()
	price_dialog.title = "Rare item value"
	price_dialog.ok_button_text = "Apply gold value"
	add_child(price_dialog)
	var price_body := VBoxContainer.new()
	price_dialog.add_child(price_body)
	_label(price_body, "Gold Coins per item · 0 means no payment", 14, GOLD)
	price_amount = SpinBox.new()
	price_amount.step = 1
	price_body.add_child(price_amount)
	_label(price_body, "The recipient pays from storage. Everyone shares the payment, including the buyer.", 12, MUTED).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	price_dialog.confirmed.connect(func() -> void:
		price_amount.apply()
		_request("price", {"row_id": _priced_row.id, "price_gold": int(price_amount.value)}, _price_revision))
	sale_dialog = ConfirmationDialog.new()
	sale_dialog.title = "Sell unwanted loot to the NPC"
	sale_dialog.ok_button_text = "Stage NPC sale"
	add_child(sale_dialog)
	var sale_body := VBoxContainer.new()
	sale_dialog.add_child(sale_body)
	sale_description = _label(sale_body, "", 14, GOLD)
	sale_description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sale_amount = SpinBox.new()
	sale_body.add_child(sale_amount)
	_label(sale_body, "The server sets this price. Proceeds are shared equally.\n0 cancels the sale. Items are sold only when the final delivery is confirmed.", 12, MUTED).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sale_dialog.confirmed.connect(func() -> void:
		sale_amount.apply()
		_request("sell", {"row_id": _sold_row.id, "quantity": int(sale_amount.value)}, _sale_revision))
	panel.hide()
	_layout()

func _layout() -> void:
	var viewport := get_viewport_rect().size
	var compact := viewport.y < 800
	if compact != _compact_view:
		_compact_view = compact
		if panel.visible and not _state.is_empty(): _render.call_deferred()
	var target := Vector2(clampf(viewport.x - 114, 640, 1460), clampf(viewport.y - 112, 380, 830))
	panel.size = target
	panel.position = Vector2(maxf(8, (viewport.x - 92 - target.x) / 2), maxf(48, (viewport.y - target.y) / 2))
	announcement.position = Vector2(panel.position.x + 60, maxf(4, panel.position.y - 43))
	announcement.size = Vector2(maxf(300, panel.size.x - 120), 34)
	reopen.position = Vector2(maxf(8, viewport.x - 270), 100)
	reopen.size.x = 165
	panel.queue_redraw()

func _on_state_changed(path: StringName) -> void:
	if path == &"gauntlet_loot": apply_snapshot(AppState.gauntlet_loot)
	elif path == &"connection" and AppState.connection_state == "disconnected":
		_state.clear()
		panel.hide()
		reopen.hide()
		announcement.hide()
		editor.hide()
		confirmation.hide()
		price_dialog.hide()
		sale_dialog.hide()
		portraits.clear()

func apply_snapshot(state: Dictionary) -> void:
	if state.is_empty(): return
	var changed_run := str(_state.get("run_id", "")) != str(state.run_id)
	if int(state.revision) != int(_state.get("revision", -1)):
		editor.hide()
		confirmation.hide()
		price_dialog.hide()
		sale_dialog.hide()
	_state = state.duplicate(true)
	_pending_since = 0
	set_process(false)
	reopen.visible = state.phase != "sent" or bool(state.get("other_pending", false))
	reopen.text = "More reserved loot" if state.phase == "sent" else "Gauntlet loot (%d)" % int(state.total)
	if not str(state.announcement).is_empty():
		var key := "%s:%d" % [state.run_id, int(state.announcement_id)]
		announcement_text.text = "RARE FOUND: %s   ·   Party notified · Held for distribution" % state.announcement
		if _last_notice != key:
			_last_notice = key
			announcement.show()
			get_tree().create_timer(9).timeout.connect(func() -> void:
				if _last_notice == key and not panel.visible: announcement.hide())
	if state.open:
		panel.show()
		if panel.has_meta(WindowStack.STACK_META): WindowStack.activate(panel)
		else: panel.move_to_front()
	if panel.visible:
		portraits.set_active(true)
		_render()
		if not str(state.get("error", "")).is_empty(): status.text = str(state.error)
	elif changed_run:
		portraits.begin_batch()
	_layout.call_deferred()

func _clear(parent: Node) -> void:
	for child: Node in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func _editable() -> bool:
	return bool(_state.get("is_leader", false)) and _state.get("phase", "") in ["complete", "ended"] and _pending_since == 0

func _render() -> void:
	heading.text = "GAUNTLET COMPLETE" if _state.phase == "complete" else ("LOOT DELIVERED" if _state.phase == "sent" else ("GAUNTLET IN PROGRESS" if _state.phase == "active" else "GAUNTLET ENDED"))
	route.text = str(_state.route)
	hint.text = "All creature drops held until completion. Personal cache rewards stay with their owner."
	_clear(table)
	for row: Dictionary in _state.rows: _item_row(row)
	if _state.rows.is_empty(): _label(table, "No creature drops collected yet.", 15, MUTED)
	_clear(deliveries)
	_portrait_nodes.clear()
	portraits.begin_batch()
	for member: Dictionary in _state.members: _delivery_card(member)
	split_button.disabled = not _editable()
	clear_button.disabled = not _editable()
	send_button.disabled = not _editable() or not bool(_state.can_send)
	send_button.text = "DELIVERED TO STORAGE" if _state.phase == "sent" else "CONFIRM & SEND TO STORAGE"
	approve_button.hide()
	for member: Dictionary in _state.members:
		if member.self and int(member.charge_gold) > 0 and _state.phase in ["complete", "ended"]:
			approve_button.show()
			approve_button.text = "Revoke payment approval" if member.payment_approved else "Approve %d GC payment" % int(member.charge_gold)
			approve_button.disabled = _pending_since > 0 or not bool(member.payment_ready)
	pager.text = "%d of %d item types assigned  ·  Page %d / %d" % [int(_state.assigned), int(_state.total), int(_state.page) + 1, int(_state.pages)]
	previous_button.disabled = int(_state.page) == 0 or _pending_since > 0
	next_button.disabled = int(_state.page) + 1 >= int(_state.pages) or _pending_since > 0
	previous_button.visible = int(_state.pages) > 1
	next_button.visible = int(_state.pages) > 1
	status.text = str(_state.reason)
	if _state.phase == "sent": status.text = "Every assigned share was delivered directly to personal storage."
	elif _state.phase == "active": status.text = "Loot is reserved. Finish the run to distribute it."
	elif not bool(_state.is_leader): status.text = "The party leader is assigning loot. Your storage preview updates with every change."
	elif status.text.is_empty(): status.text = "Review recipients and quantities, then confirm delivery. Remainders go in roster order."
	for member: Dictionary in _state.members:
		if not bool(member.payment_ready):
			status.text = "%s needs enough Gold Coins in storage to pay %d GC. Refresh after funding storage." % [member.name, int(member.charge_gold)]
			break
		if not bool(member.payment_approved):
			status.text = "%s must approve the %d GC storage payment. Rare payments and NPC proceeds are split across everyone." % [member.name, int(member.charge_gold)]

func _icon(parent: Node, image_id: int, side := 38) -> TextureRect:
	var icon := TextureRect.new()
	icon.custom_minimum_size = Vector2(side, side)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if _atlas != null: icon.texture = _atlas.icon_for(image_id)
	parent.add_child(icon)
	return icon

func _member_name(username: String) -> String:
	for member: Dictionary in _state.members:
		if member.username == username: return str(member.name)
	return username

func _item_row(row: Dictionary) -> void:
	var surround := PanelContainer.new()
	surround.add_theme_stylebox_override("panel", style(CYAN.darkened(0.45) if row.rare else Color("253636"), Color("0a1619") if row.rare else Color("070f10"), 4))
	table.add_child(surround)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 8)
	line.custom_minimum_size.y = 34
	surround.add_child(line)
	var item := HBoxContainer.new()
	item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.size_flags_stretch_ratio = 1.25
	line.add_child(item)
	_icon(item, int(row.image_id), 32)
	var item_text := VBoxContainer.new()
	item_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.add_child(item_text)
	var item_title := "Rare payments" if row.source == "compensation" else ("NPC sale proceeds" if row.source == "npc_sales" else str(row.name))
	var item_name := _label(item_text, item_title, 14, CYAN if row.rare else GOLD)
	item_name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	item_name.tooltip_text = str(row.name)
	if row.rare: _label(item_text, "RARE", 10, GOLD)
	if not str(row.owner).is_empty(): _label(item_text, "Personal cache", 10, MUTED)
	if row.source == "compensation": _label(item_text, "Gold Coins · shared equally", 10, MUTED)
	if int(row.sell_quantity) > 0: _label(item_text, "NPC: %d → %d GC" % [int(row.sell_quantity), int(row.sale_proceeds)], 10, GREEN)
	var total := _label(line, str(int(row.quantity)), 16, GOLD)
	total.custom_minimum_size.x = 46
	total.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var allocation_box := VBoxContainer.new()
	allocation_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	allocation_box.size_flags_stretch_ratio = 1.0
	line.add_child(allocation_box)
	var amounts: Array[String] = []
	var quantities: Array[int] = []
	for username: String in row.allocations:
		amounts.append("%s ×%d" % [_member_name(username), int(row.allocations[username])])
		quantities.append(int(row.allocations[username]))
	var recipient := OptionButton.new()
	recipient.add_item("Unassigned")
	recipient.add_item("Split equally" if not row.rare else "Edit allocation…")
	for member: Dictionary in _state.members: recipient.add_item(str(member.name))
	recipient.add_item("Edit quantities…")
	recipient.fit_to_longest_item = false
	recipient.custom_minimum_size.x = 135
	recipient.add_theme_font_size_override("font_size", 13)
	recipient.add_theme_stylebox_override("normal", style(BRONZE, Color("0d1b1d"), 6))
	recipient.add_theme_color_override("font_color", GOLD)
	recipient.tooltip_text = ", ".join(amounts)
	if quantities.size() > 1:
		recipient.set_item_text(1, "Shared · %d players" % quantities.size())
		recipient.select(1)
	elif quantities.size() == 1:
		for i: int in range(_state.members.size()):
			if row.allocations.has(str(_state.members[i].username)): recipient.select(i + 2)
	recipient.disabled = not _editable() or bool(row.locked) or int(row.available_quantity) == 0
	recipient.item_selected.connect(func(index: int) -> void:
		if index == recipient.item_count - 1 or index == 1 and row.rare:
			_edit_item(row)
		elif index == 1: _request("split", {"row_id": row.id})
		elif index == 0: _request("allocate", {"row_id": row.id, "allocations": {}})
		else: _request("allocate", {"row_id": row.id, "allocations": {str(_state.members[index - 2].username): int(row.available_quantity)}}))
	allocation_box.add_child(recipient)
	var summary := _label(allocation_box, ", ".join(amounts) if not amounts.is_empty() else "Choose a recipient", 10, MUTED)
	summary.visible = get_viewport_rect().size.y >= 800
	summary.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	summary.tooltip_text = ", ".join(amounts)
	var quantity_text := "—"
	if int(row.sell_quantity) == int(row.quantity): quantity_text = "NPC sale"
	if quantities.size() == 1: quantity_text = str(quantities[0])
	elif quantities.size() > 1:
		quantity_text = "%d each" % quantities[0] if quantities.min() == quantities.max() else "%d split" % int(row.quantity)
	var amount_label := _label(line, quantity_text, 13, TEXT)
	amount_label.custom_minimum_size.x = 64
	amount_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var price_cell := HBoxContainer.new()
	price_cell.custom_minimum_size.x = 126
	price_cell.alignment = BoxContainer.ALIGNMENT_CENTER
	line.add_child(price_cell)
	if row.rare and not bool(row.locked):
		var value_button := _button(price_cell, "%d GC" % int(row.price_gold), func() -> void: _edit_price(row))
		value_button.clip_text = true
		value_button.custom_minimum_size.x = 66
		value_button.tooltip_text = "%d Gold Coins per item. Paid from storage and shared equally, including the buyer." % int(row.price_gold)
		value_button.disabled = not _editable() or int(row.available_quantity) == 0
	if not bool(row.locked) and int(row.npc_gold) > 0:
		var npc_button := _button(price_cell, "NPC", func() -> void: _edit_sale(row))
		npc_button.tooltip_text = "Sell unwanted items: %d GC per %d item(s). Server price." % [int(row.npc_gold), int(row.npc_bundle)]
		npc_button.disabled = not _editable()
	elif not row.rare:
		_label(price_cell, "Reserved" if not str(row.owner).is_empty() else "—", 11, MUTED)

func _delivery_card(member: Dictionary) -> void:
	var compact := get_viewport_rect().size.y < 800
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", style(Color("304b4c"), Color("081315"), 4 if compact else 6))
	deliveries.add_child(card)
	var body := VBoxContainer.new()
	card.add_child(body)
	var top := HBoxContainer.new()
	body.add_child(top)
	var portrait_box := PanelContainer.new()
	portrait_box.add_theme_stylebox_override("panel", style(BRONZE, Color("1a2421"), 2))
	portrait_box.custom_minimum_size = Vector2(28, 30) if compact else Vector2(36, 38)
	top.add_child(portrait_box)
	var portrait := _icon(portrait_box, -1, 26 if compact else 34)
	portrait.texture = portraits.request(member.portrait)
	var key: String = Portraits.cache_key(member.portrait)
	if not _portrait_nodes.has(key): _portrait_nodes[key] = []
	(_portrait_nodes[key] as Array).append(portrait)
	if portrait.texture == null:
		var initials := Medallion.new()
		initials.configure({"name": member.name, "leader": member.username == _state.leader})
		portrait_box.add_child(initials)
	var who := VBoxContainer.new()
	who.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(who)
	_label(who, str(member.name), 14 if compact else 17, GOLD)
	_label(who, "Personal storage" + (" · Offline" if not member.online else ""), 10, MUTED)
	_label(top, "✓" if _state.phase == "sent" else "→", 21, GREEN if _state.phase == "sent" else CYAN)
	var grid := GridContainer.new()
	grid.columns = 4 if compact else 2
	grid.add_theme_constant_override("h_separation", 10)
	body.add_child(grid)
	for item: Dictionary in member.preview:
		var stack := HBoxContainer.new()
		stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		grid.add_child(stack)
		_icon(stack, int(item.image_id), 14 if compact else 16)
		stack.tooltip_text = "%d %s" % [int(item.quantity), str(item.name)]
		var label := _label(stack, str(int(item.quantity)) if compact else stack.tooltip_text, 10 if compact else 11)
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		label.tooltip_text = stack.tooltip_text
	if int(member.more) > 0: _label(body, "+ %d more item types" % int(member.more), 11, MUTED)
	if member.preview.is_empty(): _label(body, "No items assigned", 11, MUTED)
	if compact and (int(member.charge_gold) > 0 or int(member.rebate_gold) > 0 or int(member.sale_share_gold) > 0):
		var compact_payment := _label(body, "Pay %d · Back %d · NPC %d GC" % [int(member.charge_gold), int(member.rebate_gold), int(member.sale_share_gold)], 10, CYAN if member.payment_ready else Color("ed9475"))
		compact_payment.tooltip_text = "Storage payment: %d GC\nShare of rare payments (including buyer): %d GC\nShare of NPC proceeds: %d GC" % [int(member.charge_gold), int(member.rebate_gold), int(member.sale_share_gold)]
	elif int(member.charge_gold) > 0 or int(member.rebate_gold) > 0:
		var payment := "Pays %d GC · receives %d GC" % [int(member.charge_gold), int(member.rebate_gold)]
		if _state.phase == "sent": payment = "Paid %d GC · received %d GC" % [int(member.charge_gold), int(member.rebate_gold)]
		var payment_label := _label(body, payment, 10, CYAN if member.payment_ready else Color("ed9475"))
		payment_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		payment_label.tooltip_text = "Rare-item payments are split equally among all admitted party members, including each buyer. Paid from storage before any loot is credited."
	if not compact and int(member.sale_share_gold) > 0: _label(body, "+%d GC from NPC sales" % int(member.sale_share_gold), 10, GREEN)
	if int(member.charge_gold) > 0 and _state.phase != "sent":
		_label(body, "Payment approved ✓" if member.payment_approved else "Awaiting buyer approval", 10, GREEN if member.payment_approved else GOLD)

func _portrait_ready(key: String, texture: Texture2D) -> void:
	for target: TextureRect in _portrait_nodes.get(key, []):
		if is_instance_valid(target):
			target.texture = texture
			for child: Node in target.get_parent().get_children():
				if child != target: child.queue_free()

func _open() -> void:
	_request("open", {"page": int(_state.get("page", 0))}, -1, _state.get("phase", "") != "sent")

func close() -> void:
	panel.hide()
	announcement.hide()
	editor.hide()
	confirmation.hide()
	price_dialog.hide()
	sale_dialog.hide()

func _page(direction: int) -> void:
	_request("open", {"page": int(_state.page) + direction})

func _request(action: String, extra: Dictionary = {}, revision := -1, current_run := true) -> void:
	if _state.is_empty() or _pending_since > 0: return
	var data := {"action": action, "run_id": str(_state.run_id),
		"revision": int(_state.revision) if revision < 0 else revision}
	if not current_run: data.erase("run_id")
	data.merge(extra, true)
	var error: Error = _send.call("#gauntletloot " + JSON.stringify(data))
	if error != OK:
		status.text = "Could not send your choice. Check the connection and try again."
		return
	_pending_since = Time.get_ticks_msec()
	set_process(true)
	if panel.visible:
		_render()
		status.text = "Waiting for the server…"

func _process(_delta: float) -> void:
	if _pending_since > 0 and Time.get_ticks_msec() - _pending_since > 5000:
		_pending_since = 0
		set_process(false)
		if panel.visible:
			_render()
			status.text = "No update received. Reopen the ledger to refresh before retrying."

func _edit_item(row: Dictionary) -> void:
	_editing = row.duplicate(true)
	_edit_revision = int(_state.revision)
	editor_fields.clear()
	var old := editor.get_node_or_null("AllocationFields")
	if old != null:
		editor.remove_child(old)
		old.queue_free()
	var body := VBoxContainer.new()
	body.name = "AllocationFields"
	body.add_theme_constant_override("separation", 10)
	editor.add_child(body)
	_label(body, "%s · %d available" % [row.name, int(row.available_quantity)], 16, GOLD)
	for member: Dictionary in _state.members:
		var line := HBoxContainer.new()
		body.add_child(line)
		_label(line, str(member.name)).size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var quantity := SpinBox.new()
		quantity.min_value = 0
		quantity.max_value = int(row.available_quantity)
		quantity.step = 1
		quantity.allow_greater = false
		quantity.value = int(row.allocations.get(str(member.username), 0))
		quantity.custom_minimum_size.x = 130
		quantity.value_changed.connect(func(_value: float) -> void: _editor_changed())
		line.add_child(quantity)
		editor_fields[str(member.username)] = quantity
	editor_total = _label(body, "", 13, MUTED)
	_editor_changed()
	editor.popup_centered(Vector2i(440, 180 + _state.members.size() * 40))

func _editor_changed() -> void:
	var amount := 0
	for field: SpinBox in editor_fields.values(): amount += int(field.value)
	editor.get_ok_button().disabled = amount > int(_editing.available_quantity)
	editor_total.text = "%d / %d assigned · %d left in escrow" % [amount, int(_editing.available_quantity), maxi(0, int(_editing.available_quantity) - amount)]
	editor_total.add_theme_color_override("font_color", Color("ed9475") if amount > int(_editing.available_quantity) else MUTED)

func _apply_editor() -> void:
	var allocation := {}
	for username: String in editor_fields:
		var field: SpinBox = editor_fields[username]
		field.apply()
		allocation[username] = int(field.value)
	_request("allocate", {"row_id": _editing.id, "allocations": allocation}, _edit_revision)

func _confirm_send() -> void:
	if not _editable() or not bool(_state.can_send): return
	_confirm_revision = int(_state.revision)
	confirmation.dialog_text = "Send all %d allocated item types directly to the %d party members' personal storage?\n\nReview the storage preview before confirming. This delivery can only happen once." % [int(_state.total), _state.members.size()]
	for member: Dictionary in _state.members:
		if int(member.charge_gold) > 0:
			confirmation.dialog_text += "\n%s pays %d GC from storage and receives %d GC back." % [member.name, int(member.charge_gold), int(member.rebate_gold)]
	confirmation.dialog_text += "\nRare-item payments are shared equally, including the buyer."
	var npc_total := 0
	for member: Dictionary in _state.members: npc_total += int(member.sale_share_gold)
	if npc_total > 0: confirmation.dialog_text += "\nStaged NPC sales add %d GC, split equally across the party." % npc_total
	confirmation.popup_centered(Vector2i(480, 180))

func _edit_price(row: Dictionary) -> void:
	_priced_row = row.duplicate(true)
	_price_revision = int(_state.revision)
	price_dialog.title = "Rare value · " + str(row.name)
	price_amount.max_value = floori(2000000000.0 / int(row.quantity))
	price_amount.value = int(row.price_gold)
	price_dialog.popup_centered(Vector2i(460, 200))

func _edit_sale(row: Dictionary) -> void:
	_sold_row = row.duplicate(true)
	_sale_revision = int(_state.revision)
	sale_description.text = "%s · %d available\nNPC price: %d Gold Coins per %d item(s)" % [row.name, int(row.quantity), int(row.npc_gold), int(row.npc_bundle)]
	sale_amount.max_value = int(row.quantity) - int(row.quantity) % int(row.npc_bundle)
	sale_amount.step = int(row.npc_bundle)
	sale_amount.value = int(row.sell_quantity) if int(row.sell_quantity) > 0 else int(sale_amount.max_value)
	sale_dialog.popup_centered(Vector2i(480, 230))

func _approve_payment() -> void:
	for member: Dictionary in _state.members:
		if member.self:
			_request("revoke_payment" if member.payment_approved else "approve_payment")
			return
