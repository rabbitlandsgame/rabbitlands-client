extends Control
## Party ledger: all quantities and deliveries are server-owned snapshots.

const Art := preload("res://src/ui/leaderboard_art.gd")
const LedgerArt := preload("res://src/ui/gauntlet_loot_art.gd")
const Portraits := preload("res://src/ui/leaderboard_portraits.gd")
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
var _selected_row := ""
var _row_panels: Dictionary = {}
var exchange_dialog: ConfirmationDialog
var exchange_amount: SpinBox
var exchange_price: SpinBox
var reprice_dialog: ConfirmationDialog
var reprice_amount: SpinBox
var _reprice_description: Label
var _reprice_listing: Dictionary = {}
var _reprice_run := ""
var _exchange_row: Dictionary = {}
var _exchange_revision := -1
var _tabs: HBoxContainer
var _exchange_view: VBoxContainer
var _exchange_cards: VBoxContainer
var _exchange_tab: Button
var _distribution_tab: Button
var _run_picker: OptionButton
var _run_previous: Button
var _run_next: Button
var _exchange_pager: Label
var _exchange_heading: Label
var _exchange_previous: Button
var _exchange_next: Button
var _show_exchange := false
var _editor_run := ""
var _price_run := ""
var _sale_run := ""
var _exchange_run := ""
var _confirmation_run := ""

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
	box.set_corner_radius_all(4)
	box.set_content_margin_all(margin)
	return box

func _label(parent: Node, text: String, font_size := 14, color := TEXT) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label

func _surface(control: Control, opacity := 0.55) -> void:
	control.draw.connect(func() -> void: LedgerArt.surface(control, opacity))
	control.resized.connect(func() -> void: control.queue_redraw())

func _rule(parent: Node) -> void:
	var line := Control.new()
	line.custom_minimum_size.y = 5
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(line)
	line.draw.connect(func() -> void: LedgerArt.rule(line))
	line.resized.connect(func() -> void: line.queue_redraw())

func _wrap_dialog_label(label: Label, width: int) -> void:
	# Give wrapping its width before the dialog measures its first minimum.
	label.custom_minimum_size.x = width
	label.size.x = width
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

func _button(parent: Node, text: String, action: Callable, primary := false) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 34
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", Color("071316") if primary else GOLD)
	button.add_theme_color_override("font_hover_color", TEXT)
	var normal := style(CYAN if primary else BRONZE,
		Color("8ed8e5") if primary else Color("0b191b"), 9)
	normal.border_color = Color("d5f9ff") if primary else BRONZE
	normal.shadow_color = Color(0.12, 0.65, 0.77, 0.2) if primary else Color(0, 0, 0, 0)
	normal.shadow_size = 5 if primary else 0
	button.add_theme_stylebox_override("normal", normal)
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
	_surface(announcement)
	announcement_text = _label(announcement, "", 15, GOLD)
	announcement_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	announcement_text.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	announcement.hide()
	panel = PanelContainer.new()
	panel.name = "GauntletLootWindow"
	panel.add_theme_stylebox_override("panel", style(BRONZE, Color("040c0d"), 20))
	add_child(panel)
	panel.draw.connect(func() -> void: LedgerArt.frame(panel))
	panel.resized.connect(func() -> void: panel.queue_redraw())
	panel.visibility_changed.connect(func() -> void:
		portraits.set_active(panel.visible)
		reopen.visible = not panel.visible and not _state.is_empty() and (_state.get("phase", "") != "sent" or int(_state.get("exchange_total", 0)) > 0 or bool(_state.get("other_pending", false))))
	_content = VBoxContainer.new()
	_content.add_theme_constant_override("separation", 7)
	panel.add_child(_content)
	var title_row := HBoxContainer.new()
	_content.add_child(title_row)
	var title_spacer := Control.new()
	title_spacer.custom_minimum_size.x = 32
	title_row.add_child(title_spacer)
	heading = _label(title_row, "GAUNTLET COMPLETE", 30, GOLD)
	heading.add_theme_font_override("font", Art.title_font())
	heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_button(title_row, "×", close)
	route = _label(_content, "", 20, GOLD)
	route.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	route.add_theme_font_override("font", Art.title_font())
	hint = _label(_content, "All creature drops held until completion.", 13, MUTED)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_tabs = HBoxContainer.new()
	_content.add_child(_tabs)
	_tabs.hide()
	_distribution_tab = _button(_tabs, "Distribute loot", func() -> void: _show_exchange = false; _render())
	_exchange_tab = _button(_tabs, "Party exchange", func() -> void: _show_exchange = true; _render())
	var tab_spacer := Control.new()
	tab_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_tabs.add_child(tab_spacer)
	_run_previous = _button(_tabs, "‹", func() -> void: _ledger_page(-1))
	_run_picker = OptionButton.new()
	_run_picker.custom_minimum_size.x = 220
	_run_picker.fit_to_longest_item = false
	_run_picker.clip_text = true
	_run_picker.add_theme_stylebox_override("normal", style(BRONZE, Color("0b191b"), 5))
	_run_picker.add_theme_color_override("font_color", GOLD)
	_tabs.add_child(_run_picker)
	_run_picker.item_selected.connect(func(index: int) -> void:
		var run_id: Variant = _run_picker.get_item_metadata(index)
		if run_id is String and not run_id.is_empty():
			_request("open", {"run_id": run_id, "ledger_page": int(_state.get("ledger_page", 0))}))
	_run_next = _button(_tabs, "›", func() -> void: _ledger_page(1))
	_columns = HBoxContainer.new()
	_columns.add_theme_constant_override("separation", 12)
	_columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_child(_columns)
	_ledger = PanelContainer.new()
	_ledger.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_ledger.size_flags_stretch_ratio = 2.2
	_ledger.add_theme_stylebox_override("panel", style())
	_columns.add_child(_ledger)
	_surface(_ledger, 0.22)
	var left := VBoxContainer.new()
	left.add_theme_constant_override("separation", 8)
	_ledger.add_child(left)
	var header_box := PanelContainer.new()
	header_box.add_theme_stylebox_override("panel", style(Color("345052"), Color("0a1d22"), 4))
	left.add_child(header_box)
	_surface(header_box)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	header.custom_minimum_size.y = 24
	header_box.add_child(header)
	var item_header := _label(header, "Item", 15, TEXT)
	item_header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item_header.size_flags_stretch_ratio = 0.85
	_label(header, "Found", 13, TEXT).custom_minimum_size.x = 46
	var recipient_header := _label(header, "Recipient / allocation", 13, TEXT)
	recipient_header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	recipient_header.size_flags_stretch_ratio = 1.15
	recipient_header.custom_minimum_size.x = 135
	_label(header, "Quantity", 13, TEXT).custom_minimum_size.x = 64
	_label(header, "Value / sell", 12, TEXT).custom_minimum_size.x = 126
	header_box.draw.connect(func() -> void: LedgerArt.columns(header_box, header, BRONZE))
	header.sort_children.connect(func() -> void: header_box.queue_redraw())
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	left.add_child(scroll)
	table = VBoxContainer.new()
	table.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	table.size_flags_vertical = Control.SIZE_EXPAND_FILL
	table.add_theme_constant_override("separation", 3)
	scroll.add_child(table)
	var page_row := HBoxContainer.new()
	left.add_child(page_row)
	previous_button = _button(page_row, "‹", func() -> void: _page(-1))
	pager = _label(page_row, "", 12, MUTED)
	pager.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	next_button = _button(page_row, "›", func() -> void: _page(1))
	split_button = _button(page_row, "Split common equally", func() -> void: _request("split"))
	clear_button = _button(page_row, "Clear assignments", func() -> void: _request("clear"))
	_storage = PanelContainer.new()
	_storage.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_storage.size_flags_stretch_ratio = 1.0
	_storage.add_theme_stylebox_override("panel", style())
	_columns.add_child(_storage)
	_surface(_storage, 0.3)
	var right := VBoxContainer.new()
	_storage.add_child(right)
	_label(right, "Storage deliveries", 20, GOLD).add_theme_font_override("font", Art.title_font())
	_rule(right)
	var delivery_scroll := ScrollContainer.new()
	delivery_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	delivery_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(delivery_scroll)
	deliveries = VBoxContainer.new()
	deliveries.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	deliveries.add_theme_constant_override("separation", 8)
	delivery_scroll.add_child(deliveries)
	_exchange_view = VBoxContainer.new()
	_exchange_view.add_theme_constant_override("separation", 8)
	_exchange_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_child(_exchange_view)
	_exchange_view.hide()
	_exchange_heading = _label(_exchange_view, "Owned by the original gauntlet team", 19, GOLD)
	_exchange_heading.add_theme_font_override("font", Art.title_font())
	var exchange_rules := _label(_exchange_view, "Sale proceeds go equally to the original members' storage. Request a vote to change the price or withdraw an item. Any No blocks the proposal; abstentions are neutral. Unanswered votes are ignored after 14 days.", 13, MUTED)
	exchange_rules.size.x = 800
	exchange_rules.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var exchange_scroll := ScrollContainer.new()
	exchange_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	exchange_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_exchange_view.add_child(exchange_scroll)
	_exchange_cards = VBoxContainer.new()
	_exchange_cards.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_exchange_cards.add_theme_constant_override("separation", 10)
	exchange_scroll.add_child(_exchange_cards)
	var exchange_pages := HBoxContainer.new()
	_exchange_view.add_child(exchange_pages)
	_exchange_previous = _button(exchange_pages, "‹ Previous", func() -> void: _exchange_page(-1))
	_exchange_pager = _label(exchange_pages, "", 12, MUTED)
	_exchange_pager.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_exchange_pager.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_exchange_next = _button(exchange_pages, "Next ›", func() -> void: _exchange_page(1))
	status = _label(_content, "", 13, MUTED)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_rule(_content)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	_content.add_child(footer)
	var reserved := _label(footer, "◇  Unsent items remain in escrow.", 12, MUTED)
	reserved.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	reserved.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	reserved.tooltip_text = "Unsent items remain in escrow. Close and reopen the ledger whenever you need."
	approve_button = _button(footer, "Approve my payment", _approve_payment)
	approve_button.hide()
	_button(footer, "↻", _open).tooltip_text = "Refresh the loot ledger"
	var save_button := _button(footer, "Save & close", close)
	save_button.custom_minimum_size.x = 132
	send_button = _button(footer, "CONFIRM & SEND TO STORAGE", _confirm_send, true)
	send_button.add_theme_font_override("font", Art.title_font())
	send_button.add_theme_font_size_override("font_size", 15)
	send_button.custom_minimum_size = Vector2(280, 42)
	editor = ConfirmationDialog.new()
	editor.title = "Allocate item quantities"
	editor.ok_button_text = "Apply allocation"
	editor.confirmed.connect(_apply_editor)
	add_child(editor)
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Send gauntlet loot to storage"
	confirmation.ok_button_text = "Send to storage"
	_wrap_dialog_label(confirmation.get_label(), 440)
	confirmation.confirmed.connect(func() -> void: _request("send", {"run_id": _confirmation_run}, _confirm_revision))
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
	_wrap_dialog_label(_label(price_body, "The recipient pays from storage. Everyone shares the payment, including the buyer.", 12, MUTED), 400)
	price_dialog.confirmed.connect(func() -> void:
		price_amount.apply()
		_request("price", {"run_id": _price_run, "row_id": _priced_row.id, "price_gold": int(price_amount.value)}, _price_revision))
	sale_dialog = ConfirmationDialog.new()
	sale_dialog.title = "Sell unwanted loot to the NPC"
	sale_dialog.ok_button_text = "Stage NPC sale"
	add_child(sale_dialog)
	var sale_body := VBoxContainer.new()
	sale_dialog.add_child(sale_body)
	sale_description = _label(sale_body, "", 14, GOLD)
	_wrap_dialog_label(sale_description, 420)
	sale_amount = SpinBox.new()
	sale_body.add_child(sale_amount)
	_wrap_dialog_label(_label(sale_body, "The server sets this price. Proceeds are shared equally.\n0 cancels the sale. Items are sold only when the final delivery is confirmed.", 12, MUTED), 420)
	sale_dialog.confirmed.connect(func() -> void:
		sale_amount.apply()
		_request("sell", {"run_id": _sale_run, "row_id": _sold_row.id, "quantity": int(sale_amount.value)}, _sale_revision))
	exchange_dialog = ConfirmationDialog.new()
	exchange_dialog.title = "List drops on the exchange"
	exchange_dialog.ok_button_text = "Stage party listing"
	add_child(exchange_dialog)
	var exchange_body := VBoxContainer.new()
	exchange_dialog.add_child(exchange_body)
	_label(exchange_body, "Quantity · 0 cancels the staged listing", 13, GOLD)
	exchange_amount = SpinBox.new()
	exchange_amount.step = 1
	exchange_body.add_child(exchange_amount)
	_label(exchange_body, "Gold Coins per item", 13, GOLD)
	exchange_price = SpinBox.new()
	exchange_price.step = 1
	exchange_price.min_value = 1
	exchange_price.max_value = 2000000000
	exchange_body.add_child(exchange_price)
	exchange_amount.value_changed.connect(func(value: float) -> void: exchange_price.max_value = floori(2000000000.0 / maxf(1, value)))
	_wrap_dialog_label(_label(exchange_body, "The original team shares sale proceeds equally. Listings remain until sold or withdrawn by a party vote. They are posted only when you confirm distribution.", 12, MUTED), 420)
	exchange_dialog.confirmed.connect(func() -> void:
		exchange_amount.apply()
		exchange_price.apply()
		_request("exchange", {"run_id": _exchange_run, "row_id": _exchange_row.id, "quantity": int(exchange_amount.value), "unit_price": int(exchange_price.value)}, _exchange_revision))
	reprice_dialog = ConfirmationDialog.new()
	reprice_dialog.title = "Propose a party price change"
	reprice_dialog.ok_button_text = "Propose price · Vote Yes"
	add_child(reprice_dialog)
	var reprice_body := VBoxContainer.new()
	reprice_body.add_theme_constant_override("separation", 12)
	reprice_dialog.add_child(reprice_body)
	_reprice_description = _label(reprice_body, "", 14, GOLD)
	_wrap_dialog_label(_reprice_description, 420)
	_label(reprice_body, "Proposed Gold Coins per item", 13, GOLD)
	reprice_amount = SpinBox.new()
	reprice_amount.step = 1
	reprice_amount.update_on_text_changed = true
	reprice_amount.min_value = 1
	reprice_body.add_child(reprice_amount)
	reprice_amount.value_changed.connect(func(value: float) -> void: reprice_dialog.get_ok_button().disabled = int(value) == int(_reprice_listing.get("price_gold", 0)))
	_wrap_dialog_label(_label(reprice_body, "Your proposal starts with your Yes vote. Any No blocks the change; abstentions are neutral. Unanswered votes are ignored after 14 days. Buyers pay the current price until approval. The approved price applies only to unsold items.", 12, MUTED), 420)
	reprice_dialog.confirmed.connect(func() -> void:
		reprice_amount.apply()
		_request("request_price_change", {"run_id": _reprice_run, "listing_id": int(_reprice_listing.listing_id), "unit_price": int(reprice_amount.value)}))
	for dialog: ConfirmationDialog in [editor, confirmation, price_dialog, sale_dialog, exchange_dialog, reprice_dialog]:
		_style_dialog(dialog)
	panel.hide()
	_layout()

func _style_dialog(dialog: ConfirmationDialog) -> void:
	var look := Theme.new()
	look.set_stylebox("panel", "AcceptDialog", style(BRONZE, Color("081719"), 16))
	var border := style(BRONZE, Color("081719"), 8)
	border.expand_margin_top = 32
	border.expand_margin_bottom = 5
	border.expand_margin_left = 5
	border.expand_margin_right = 5
	look.set_stylebox("embedded_border", "Window", border)
	look.set_color("title_color", "Window", GOLD)
	look.set_font("title_font", "Window", Art.title_font())
	look.set_font_size("title_font_size", "Window", 17)
	look.set_color("font_color", "Label", TEXT)
	look.set_color("font_color", "Button", GOLD)
	look.set_color("font_hover_color", "Button", TEXT)
	look.set_color("font_color", "LineEdit", TEXT)
	look.set_color("caret_color", "LineEdit", CYAN)
	look.set_stylebox("normal", "Button", style(BRONZE, Color("0b2024"), 8))
	look.set_stylebox("hover", "Button", style(CYAN, Color("173039"), 8))
	look.set_stylebox("pressed", "Button", style(CYAN, Color("102228"), 8))
	look.set_stylebox("focus", "Button", style(CYAN, Color(0, 0, 0, 0), 8))
	look.set_stylebox("normal", "LineEdit", style(BRONZE, Color("030d10"), 8))
	look.set_stylebox("focus", "LineEdit", style(CYAN, Color(0, 0, 0, 0), 8))
	dialog.theme = look

func _layout() -> void:
	var viewport := get_viewport_rect().size
	var compact := viewport.y < 800
	heading.add_theme_font_size_override("font_size", 25 if compact else 30)
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
		exchange_dialog.hide()
		reprice_dialog.hide()
		portraits.clear()

func apply_snapshot(state: Dictionary) -> void:
	if state.is_empty(): return
	var changed_run := str(_state.get("run_id", "")) != str(state.run_id)
	if changed_run and not _state.is_empty() and panel.visible and not state.open:
		for key: String in ["ledgers", "ledger_page", "ledger_pages"]:
			if state.has(key): _state[key] = state[key].duplicate(true) if state[key] is Array else state[key]
		_state["other_pending"] = true
		_render_exchange()
		if _pending_since == 0: status.text = "Another gauntlet ledger was updated. Choose its run above to review loot or votes."
		return
	if changed_run: _selected_row = ""
	if changed_run or state.phase == "sent" and _state.get("phase", "") != "sent":
		_show_exchange = state.phase == "sent" and int(state.get("exchange_total", 0)) > 0
	if changed_run or int(state.revision) != int(_state.get("revision", -1)):
		editor.hide()
		confirmation.hide()
		price_dialog.hide()
		sale_dialog.hide()
		exchange_dialog.hide()
		reprice_dialog.hide()
	_state = state.duplicate(true)
	_pending_since = 0
	set_process(false)
	reopen.visible = not panel.visible and (state.phase != "sent" or int(state.get("exchange_total", 0)) > 0 or bool(state.get("other_pending", false)))
	reopen.text = "Party exchange (%d)" % int(state.exchange_total) if int(state.get("exchange_total", 0)) > 0 and state.phase == "sent" else ("More reserved loot" if state.phase == "sent" else "Gauntlet loot (%d)" % int(state.total))
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
	if not bool(_state.get("exchange_enabled", false)): _show_exchange = false
	_tabs.visible = bool(_state.get("exchange_enabled", false))
	_columns.visible = not _show_exchange
	_exchange_view.visible = _show_exchange
	hint.visible = not _show_exchange or not _compact_view
	_exchange_heading.visible = not _compact_view
	heading.text = "GAUNTLET COMPLETE" if _state.phase == "complete" else ("LOOT DELIVERED" if _state.phase == "sent" else ("GAUNTLET IN PROGRESS" if _state.phase == "active" else "GAUNTLET ENDED"))
	route.text = str(_state.route)
	hint.text = "All creature drops held until completion. Personal cache rewards stay with their owner."
	_portrait_nodes.clear()
	_row_panels.clear()
	portraits.begin_batch()
	if _selected_row.is_empty():
		for row: Dictionary in _state.rows:
			if row.rare:
				_selected_row = str(row.id)
				break
	_clear(table)
	for row: Dictionary in _state.rows: _item_row(row)
	if _state.rows.is_empty(): _label(table, "No creature drops collected yet.", 15, MUTED)
	_clear(deliveries)
	for member: Dictionary in _state.members: _delivery_card(member)
	split_button.disabled = not _editable()
	clear_button.disabled = not _editable()
	send_button.disabled = not _editable() or not bool(_state.can_send)
	send_button.text = "DELIVERED TO STORAGE" if _state.phase == "sent" else "CONFIRM & SEND TO STORAGE"
	for row: Dictionary in _state.rows:
		if int(row.get("exchange_quantity", 0)) > 0:
			send_button.text = "DISTRIBUTION CONFIRMED" if _state.phase == "sent" else "CONFIRM DISTRIBUTION"
			break
	send_button.visible = not _show_exchange
	approve_button.hide()
	for member: Dictionary in _state.members:
		if member.self and int(member.charge_gold) > 0 and _state.phase in ["complete", "ended"]:
			approve_button.show()
			approve_button.text = "Revoke payment approval" if member.payment_approved else "Approve %d GC payment" % int(member.charge_gold)
			approve_button.disabled = _pending_since > 0 or not bool(member.payment_ready)
	pager.text = "%d of %d assigned" % [int(_state.assigned), int(_state.total)]
	if int(_state.pages) > 1: pager.text += " · %d / %d" % [int(_state.page) + 1, int(_state.pages)]
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
	_render_exchange()
	if int(_state.get("exchange_plan_quantity", 0)) > 0 and not bool(_state.get("exchange_can_withdraw", false)) and _state.phase in ["complete", "ended"]:
		status.text = "Exchange listings are staged. Visit an Exchange NPC within four tiles to confirm distribution and post them."
	if _show_exchange:
		heading.text = "PARTY EXCHANGE"
		hint.text = "The original gauntlet team keeps ownership, even after the party changes."
		status.text = "Listings stay available at their current price during a vote. Approved changes apply to unsold items."
		approve_button.hide()

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

func _row_style(rare: bool, selected: bool) -> StyleBoxFlat:
	var box := style(CYAN if selected else (Color("31585d") if rare else Color("203438")),
		Color("0b2228") if selected else (Color("09171b") if rare else Color("050f11")), 4)
	box.shadow_color = Color(0.2, 0.8, 0.95, 0.2)
	box.shadow_size = 4 if selected else 0
	return box

func _select_row(row_id: String) -> void:
	_selected_row = row_id
	for key: String in _row_panels:
		var target: PanelContainer = _row_panels[key]
		target.add_theme_stylebox_override("panel", _row_style(bool(target.get_meta("rare")), key == row_id))

func _portrait_box(parent: Node, member: Dictionary, dimensions: Vector2) -> PanelContainer:
	var box := PanelContainer.new()
	box.add_theme_stylebox_override("panel", style(BRONZE, Color("142225"), 2))
	box.custom_minimum_size = dimensions
	parent.add_child(box)
	var portrait := _icon(box, -1, 0)
	portrait.texture = portraits.request(member.portrait)
	var key: String = Portraits.cache_key(member.portrait)
	if not _portrait_nodes.has(key): _portrait_nodes[key] = []
	(_portrait_nodes[key] as Array).append(portrait)
	if portrait.texture == null:
		var initials := _label(box, str(member.name).left(1), 12 if dimensions.x < 30 else 22, GOLD)
		initials.add_theme_font_override("font", Art.title_font())
		initials.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		initials.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		initials.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.tooltip_text = str(member.name)
	return box

func _item_row(row: Dictionary) -> void:
	var surround := PanelContainer.new()
	surround.set_meta("rare", row.rare)
	surround.add_theme_stylebox_override("panel", _row_style(bool(row.rare), str(row.id) == _selected_row))
	surround.size_flags_vertical = Control.SIZE_EXPAND_FILL if _state.rows.size() >= 6 else Control.SIZE_FILL
	_row_panels[str(row.id)] = surround
	table.add_child(surround)
	_surface(surround, 0.2)
	surround.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			_select_row(str(row.id)))
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 8)
	line.custom_minimum_size.y = 32 if _compact_view else 46
	surround.add_child(line)
	surround.draw.connect(func() -> void: LedgerArt.columns(surround, line, CYAN if row.rare else Color("597275")))
	line.sort_children.connect(func() -> void: surround.queue_redraw())
	var item := HBoxContainer.new()
	item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.size_flags_stretch_ratio = 0.85
	line.add_child(item)
	var icon_plate := PanelContainer.new()
	icon_plate.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	icon_plate.add_theme_stylebox_override("panel", style(Color("2e484a"), Color("091719"), 2))
	item.add_child(icon_plate)
	_icon(icon_plate, int(row.image_id), 30 if _compact_view else 42)
	var item_text := VBoxContainer.new()
	item_text.alignment = BoxContainer.ALIGNMENT_CENTER
	item_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.add_child(item_text)
	var item_title := "Rare payments" if row.source == "compensation" else ("NPC sale proceeds" if row.source == "npc_sales" else str(row.name))
	var item_name := _label(item_text, item_title, 14 if get_viewport_rect().size.x < 1400 else 16, CYAN if row.rare else GOLD)
	item_name.add_theme_font_override("font", Art.title_font())
	item_name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	item_name.tooltip_text = str(row.name)
	if row.rare:
		var rare_badge := PanelContainer.new()
		rare_badge.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		rare_badge.add_theme_stylebox_override("panel", style(BRONZE, Color("11170f"), 2))
		item_text.add_child(rare_badge)
		_label(rare_badge, "RARE", 9, GOLD)
	if not str(row.owner).is_empty(): _label(item_text, "Personal cache", 10, MUTED)
	if row.source == "compensation": _label(item_text, "Gold Coins · shared equally", 10, MUTED)
	if int(row.sell_quantity) > 0: _label(item_text, "NPC: %d → %d GC" % [int(row.sell_quantity), int(row.sale_proceeds)], 10, GREEN)
	if int(row.get("exchange_quantity", 0)) > 0: _label(item_text, "Exchange: %d × %d GC" % [int(row.exchange_quantity), int(row.exchange_price)], 10, CYAN)
	var total := _label(line, str(int(row.quantity)), 16, GOLD)
	total.add_theme_font_override("font", Art.title_font())
	total.custom_minimum_size.x = 46
	total.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var allocation_box := VBoxContainer.new()
	allocation_box.alignment = BoxContainer.ALIGNMENT_CENTER
	allocation_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	allocation_box.size_flags_stretch_ratio = 1.15
	line.add_child(allocation_box)
	var allocation_controls := HBoxContainer.new()
	allocation_box.add_child(allocation_controls)
	var amounts: Array[String] = []
	var quantities: Array[int] = []
	for username: String in row.allocations:
		amounts.append("%s ×%d" % [_member_name(username), int(row.allocations[username])])
		quantities.append(int(row.allocations[username]))
	var recipient := OptionButton.new()
	recipient.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	recipient.add_item("Unassigned")
	recipient.add_item("Split evenly" if not row.rare else "Edit allocation…")
	for member: Dictionary in _state.members: recipient.add_item(str(member.name))
	recipient.add_item("Edit quantities…")
	recipient.fit_to_longest_item = false
	recipient.custom_minimum_size.x = 135
	recipient.add_theme_font_size_override("font_size", 13)
	recipient.add_theme_stylebox_override("normal", style(BRONZE, Color("0d1b1d"), 4))
	recipient.add_theme_stylebox_override("hover", style(CYAN, Color("173038"), 4))
	recipient.add_theme_stylebox_override("focus", style(CYAN, Color(0, 0, 0, 0), 4))
	recipient.add_theme_stylebox_override("disabled", style(Color("293c3e"), Color("091215"), 4))
	recipient.add_theme_color_override("font_color", GOLD)
	recipient.tooltip_text = ", ".join(amounts)
	var show_portraits := not _compact_view and get_viewport_rect().size.x >= 1400 and not bool(row.locked)
	if quantities.size() > 1:
		var equal: bool = quantities.min() == quantities.max() and quantities.size() == _state.members.size()
		recipient.set_item_text(1, "Split evenly" if equal and show_portraits else ("Split evenly · %d players" if equal else "Shared · %d players") % quantities.size())
		recipient.select(1)
	elif quantities.size() == 1:
		for i: int in range(_state.members.size()):
			if row.allocations.has(str(_state.members[i].username)): recipient.select(i + 2)
	if int(row.sell_quantity) == int(row.quantity): recipient.set_item_text(0, "NPC buyback · staged")
	if int(row.get("exchange_quantity", 0)) == int(row.quantity): recipient.set_item_text(0, "Exchange listing · staged")
	recipient.disabled = not _editable() or bool(row.locked) or int(row.available_quantity) == 0
	recipient.item_selected.connect(func(index: int) -> void:
		_select_row(str(row.id))
		if index == recipient.item_count - 1 or index == 1 and row.rare:
			_edit_item(row)
		elif index == 1: _request("split", {"row_id": row.id})
		elif index == 0: _request("allocate", {"row_id": row.id, "allocations": {}})
		else: _request("allocate", {"row_id": row.id, "allocations": {str(_state.members[index - 2].username): int(row.available_quantity)}}))
	allocation_controls.add_child(recipient)
	if show_portraits and quantities.size() > 1:
		var shares := HBoxContainer.new()
		shares.add_theme_constant_override("separation", 9)
		allocation_controls.add_child(shares)
		for member: Dictionary in _state.members:
			if not row.allocations.has(str(member.username)): continue
			var chip := VBoxContainer.new()
			chip.add_theme_constant_override("separation", 1)
			shares.add_child(chip)
			_portrait_box(chip, member, Vector2(26, 28))
			_label(chip, str(member.name), 9, MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			chip.tooltip_text = "%s · %d %s" % [member.name, int(row.allocations[member.username]), row.name]
	elif show_portraits and quantities.size() == 1:
		for member: Dictionary in _state.members:
			if row.allocations.has(str(member.username)):
				var face := _portrait_box(allocation_controls, member, Vector2(32, 38))
				allocation_controls.move_child(face, 0)
	else:
		var summary := _label(allocation_box, ", ".join(amounts) if not amounts.is_empty() else ("Staged for exchange" if int(row.get("exchange_quantity", 0)) > 0 else ("Staged for NPC sale" if int(row.sell_quantity) > 0 else "Choose a recipient")), 10, MUTED)
		summary.visible = not _compact_view
		summary.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		summary.tooltip_text = ", ".join(amounts)
	var quantity_text := "—"
	if int(row.sell_quantity) == int(row.quantity): quantity_text = "NPC sale"
	if int(row.get("exchange_quantity", 0)) == int(row.quantity): quantity_text = "Exchange"
	if quantities.size() == 1: quantity_text = str(quantities[0])
	elif quantities.size() > 1:
		quantity_text = "%d each" % quantities[0] if quantities.min() == quantities.max() else "%d split" % int(row.quantity)
	var amount_label := _label(line, quantity_text, 13, TEXT)
	amount_label.custom_minimum_size.x = 64
	amount_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var price_cell := HBoxContainer.new()
	price_cell.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	price_cell.custom_minimum_size.x = 126
	price_cell.alignment = BoxContainer.ALIGNMENT_CENTER
	line.add_child(price_cell)
	if row.rare and not bool(row.locked) and int(row.available_quantity) > 0:
		var value_button := _button(price_cell, "%d GC" % int(row.price_gold), func() -> void: _edit_price(row))
		value_button.add_theme_font_size_override("font_size", 12)
		value_button.clip_text = true
		value_button.custom_minimum_size.x = 66
		value_button.tooltip_text = "%d Gold Coins per item. Paid from storage and shared equally, including the buyer." % int(row.price_gold)
		value_button.disabled = not _editable() or int(row.available_quantity) == 0
	if not bool(row.locked) and (int(row.npc_gold) > 0 or bool(row.get("exchange_allowed", false))):
		_sale_menu(price_cell, row)
	elif not row.rare:
		_label(price_cell, "Reserved" if not str(row.owner).is_empty() else "—", 11, MUTED)

func _delivery_card(member: Dictionary) -> void:
	var compact := _compact_view
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", style(Color("35585e"), Color("050f12"), 4 if compact else 7))
	deliveries.add_child(card)
	_surface(card, 0.32)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 4)
	card.add_child(body)
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 8)
	body.add_child(top)
	var who := VBoxContainer.new()
	who.add_theme_constant_override("separation", 3)
	who.alignment = BoxContainer.ALIGNMENT_CENTER
	who.custom_minimum_size.x = 38 if compact else 64
	top.add_child(who)
	var portrait := _portrait_box(who, member, Vector2(34, 34) if compact else Vector2(60, 66))
	portrait.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var player_name := _label(who, str(member.name), 12 if compact else 15, GOLD)
	player_name.add_theme_font_override("font", Art.title_font())
	player_name.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if not member.online: _label(who, "Offline", 10, MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var contents := VBoxContainer.new()
	contents.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	contents.alignment = BoxContainer.ALIGNMENT_CENTER
	top.add_child(contents)
	var grid := GridContainer.new()
	grid.columns = (2 if get_viewport_rect().size.x < 1160 else 4) if compact else 1
	grid.add_theme_constant_override("h_separation", 7)
	grid.add_theme_constant_override("v_separation", 1)
	contents.add_child(grid)
	for item: Dictionary in member.preview:
		var stack := HBoxContainer.new()
		stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		grid.add_child(stack)
		_icon(stack, int(item.image_id), 14 if compact else 17)
		stack.tooltip_text = "%d %s" % [int(item.quantity), str(item.name)]
		var label := _label(stack, str(int(item.quantity)) if compact else stack.tooltip_text, 10 if compact else 12)
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		label.tooltip_text = stack.tooltip_text
	if int(member.more) > 0: _label(contents, "+ %d more item types" % int(member.more), 10, MUTED)
	if member.preview.is_empty(): _label(contents, "No items assigned", 11, MUTED)
	var ready: bool = _state.phase in ["complete", "ended", "sent"] and bool(member.payment_ready) and bool(member.payment_approved) and int(_state.assigned) == int(_state.total)
	var badge := PanelContainer.new()
	badge.add_theme_stylebox_override("panel", style(Color("284d4b") if ready else BRONZE, Color("061516"), 4))
	badge.custom_minimum_size = Vector2(44, 40) if compact else Vector2(58, 76)
	top.add_child(badge)
	var badge_body := VBoxContainer.new()
	badge_body.alignment = BoxContainer.ALIGNMENT_CENTER
	badge.add_child(badge_body)
	if not compact: _label(badge_body, "Storage", 10, CYAN).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label(badge_body, "✓" if ready or _state.phase == "sent" else "…", 20 if compact else 25, GREEN if ready else GOLD).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label(badge_body, "Sent" if _state.phase == "sent" else ("Ready" if ready else "Waiting"), 10 if compact else 11, GREEN if ready else GOLD).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	badge.tooltip_text = "Direct to personal storage" + (" · Payment approved" if int(member.charge_gold) > 0 and member.payment_approved else "")
	if int(member.charge_gold) > 0 or int(member.rebate_gold) > 0 or int(member.sale_share_gold) > 0:
		var payment := "Pay %d · Rebate +%d · NPC +%d GC" % [int(member.charge_gold), int(member.rebate_gold), int(member.sale_share_gold)]
		if _state.phase == "sent": payment = "Paid %d · Rebate +%d · NPC +%d GC" % [int(member.charge_gold), int(member.rebate_gold), int(member.sale_share_gold)]
		var payment_label := _label(body, payment, 10, CYAN if member.payment_ready else Color("ed9475"))
		payment_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		payment_label.tooltip_text = "Storage payment: %d GC\nShare of rare payments (including buyer): %d GC\nShare of NPC proceeds: %d GC" % [int(member.charge_gold), int(member.rebate_gold), int(member.sale_share_gold)]
	if int(member.charge_gold) > 0 and not member.payment_approved and _state.phase != "sent":
		_label(body, "Awaiting buyer approval", 10, GOLD)

func _portrait_ready(key: String, texture: Texture2D) -> void:
	for target: TextureRect in _portrait_nodes.get(key, []):
		if is_instance_valid(target):
			target.texture = texture
			for child: Node in target.get_parent().get_children():
				if child != target: child.queue_free()

func _open() -> void:
	_request("open", {"page": int(_state.get("page", 0)), "exchange_page": int(_state.get("exchange_page", 0)), "ledger_page": int(_state.get("ledger_page", 0))}, -1, _state.get("phase", "") != "sent" or int(_state.get("exchange_total", 0)) > 0)

func close() -> void:
	panel.hide()
	announcement.hide()
	editor.hide()
	confirmation.hide()
	price_dialog.hide()
	sale_dialog.hide()
	exchange_dialog.hide()
	reprice_dialog.hide()

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
	_editor_run = str(_state.run_id)
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
	_request("allocate", {"run_id": _editor_run, "row_id": _editing.id, "allocations": allocation}, _edit_revision)

func _confirm_send() -> void:
	if not _editable() or not bool(_state.can_send): return
	_confirm_revision = int(_state.revision)
	_confirmation_run = str(_state.run_id)
	confirmation.dialog_text = "Send all %d allocated item types directly to the %d party members' personal storage?\n\nReview the storage preview before confirming. This delivery can only happen once." % [int(_state.total), _state.members.size()]
	for member: Dictionary in _state.members:
		if int(member.charge_gold) > 0:
			confirmation.dialog_text += "\n%s pays %d GC from storage and receives %d GC back." % [member.name, int(member.charge_gold), int(member.rebate_gold)]
	confirmation.dialog_text += "\nRare-item payments are shared equally, including the buyer."
	var npc_total := 0
	for member: Dictionary in _state.members: npc_total += int(member.sale_share_gold)
	if npc_total > 0: confirmation.dialog_text += "\nStaged NPC sales add %d GC, split equally across the party." % npc_total
	if int(_state.get("exchange_plan_types", 0)) > 0:
		confirmation.dialog_text += "\nExchange: %d item types, %d items, at the selected prices (%d GC total asking value). Future sale proceeds are shared with the original team." % [int(_state.exchange_plan_types), int(_state.exchange_plan_quantity), int(_state.exchange_plan_gold)]
	confirmation.popup_centered(Vector2i(480, 180))

func _edit_price(row: Dictionary) -> void:
	_priced_row = row.duplicate(true)
	_price_run = str(_state.run_id)
	_price_revision = int(_state.revision)
	price_dialog.title = "Rare value · " + str(row.name)
	price_amount.max_value = floori(2000000000.0 / int(row.quantity))
	price_amount.value = int(row.price_gold)
	price_dialog.popup_centered(Vector2i(460, 200))

func _edit_sale(row: Dictionary) -> void:
	_sold_row = row.duplicate(true)
	_sale_run = str(_state.run_id)
	_sale_revision = int(_state.revision)
	sale_description.text = "%s · %d available\nNPC price: %d Gold Coins per %d item(s)" % [row.name, int(row.quantity), int(row.npc_gold), int(row.npc_bundle)]
	var available := int(row.quantity) - int(row.get("exchange_quantity", 0))
	sale_amount.max_value = available - available % int(row.npc_bundle)
	sale_amount.step = int(row.npc_bundle)
	sale_amount.value = int(row.sell_quantity) if int(row.sell_quantity) > 0 else int(sale_amount.max_value)
	sale_dialog.popup_centered(Vector2i(480, 230))

func _sale_menu(parent: Node, row: Dictionary) -> void:
	var sell := MenuButton.new()
	sell.flat = false
	sell.text = "Exchange" if int(row.get("exchange_quantity", 0)) > 0 else ("NPC · %d GC" % int(row.sale_proceeds) if int(row.sell_quantity) == int(row.quantity) else "Sell…")
	sell.add_theme_font_size_override("font_size", 12)
	sell.add_theme_color_override("font_color", GOLD)
	sell.add_theme_stylebox_override("normal", style(BRONZE, Color("0b191b"), 7))
	sell.add_theme_stylebox_override("hover", style(CYAN, Color("173038"), 7))
	sell.add_theme_stylebox_override("pressed", style(CYAN, Color("102228"), 7))
	sell.custom_minimum_size.y = 34
	sell.disabled = not _editable()
	parent.add_child(sell)
	var menu := sell.get_popup()
	if int(row.npc_gold) > 0: menu.add_item("NPC buyback · %d GC / %d item(s)" % [int(row.npc_gold), int(row.npc_bundle)], 0)
	if bool(row.get("exchange_allowed", false)): menu.add_item("List on party exchange…", 1)
	menu.id_pressed.connect(func(id: int) -> void:
		if id == 0: _edit_sale(row)
		elif id == 1: _edit_exchange(row))
	sell.tooltip_text = "Choose an NPC buyback or a party-owned exchange listing. Sales are staged until final confirmation."

func _edit_exchange(row: Dictionary) -> void:
	_exchange_row = row.duplicate(true)
	_exchange_run = str(_state.run_id)
	_exchange_revision = int(_state.revision)
	exchange_dialog.title = "Party exchange · " + str(row.name)
	exchange_amount.max_value = int(row.quantity) - int(row.sell_quantity)
	exchange_amount.value = int(row.get("exchange_quantity", 0)) if int(row.get("exchange_quantity", 0)) > 0 else int(exchange_amount.max_value)
	exchange_price.value = maxi(1, int(row.get("exchange_price", 0)) if int(row.get("exchange_price", 0)) > 0 else int(row.price_gold))
	exchange_dialog.popup_centered(Vector2i(480, 300))

func _ledger_page(direction: int) -> void:
	_request("open", {"ledger_page": int(_state.get("ledger_page", 0)) + direction, "exchange_page": int(_state.get("exchange_page", 0))})

func _exchange_page(direction: int) -> void:
	_request("open", {"exchange_page": int(_state.get("exchange_page", 0)) + direction, "ledger_page": int(_state.get("ledger_page", 0))})

func _propose_price(listing: Dictionary) -> void:
	_reprice_listing = listing.duplicate(true)
	_reprice_run = str(_state.run_id)
	reprice_dialog.title = "Propose price · " + str(listing.name)
	_reprice_description.text = "Listing #%d · %d remaining\nCurrent price: %d GC per item" % [int(listing.listing_id), int(listing.quantity), int(listing.price_gold)]
	reprice_amount.max_value = floori(float(2000000000 - int(listing.gold_sold)) / maxi(1, int(listing.quantity)))
	reprice_amount.value = int(listing.price_gold)
	reprice_dialog.get_ok_button().disabled = true
	reprice_dialog.popup_centered(Vector2i(480, 330))

func _render_exchange() -> void:
	_exchange_tab.text = "Party exchange (%d)" % int(_state.get("exchange_total", 0))
	_distribution_tab.disabled = _pending_since > 0
	_exchange_tab.disabled = _pending_since > 0
	_distribution_tab.add_theme_stylebox_override("normal", style(BRONZE if _show_exchange else CYAN, Color("0b191b") if _show_exchange else Color("123137"), 9))
	_exchange_tab.add_theme_stylebox_override("normal", style(CYAN if _show_exchange else BRONZE, Color("123137") if _show_exchange else Color("0b191b"), 9))
	_run_picker.clear()
	_run_picker.add_item("Choose a gauntlet run…")
	_run_picker.set_item_disabled(0, true)
	var ledgers: Array = _state.get("ledgers", [])
	for entry: Dictionary in ledgers:
		var index := _run_picker.item_count
		_run_picker.add_item("%s · %s" % [entry.route, str(entry.phase).capitalize()])
		_run_picker.set_item_metadata(index, str(entry.run_id))
		if entry.run_id == _state.run_id: _run_picker.select(index)
	_run_picker.visible = ledgers.size() > 1 or int(_state.get("ledger_pages", 1)) > 1
	_run_picker.disabled = _pending_since > 0
	_run_previous.visible = int(_state.get("ledger_pages", 1)) > 1
	_run_next.visible = _run_previous.visible
	_run_previous.disabled = int(_state.get("ledger_page", 0)) == 0 or _pending_since > 0
	_run_next.disabled = int(_state.get("ledger_page", 0)) + 1 >= int(_state.get("ledger_pages", 1)) or _pending_since > 0
	_clear(_exchange_cards)
	for listing: Dictionary in _state.get("exchange", []): _exchange_card(listing)
	if _exchange_cards.get_child_count() == 0:
		_exchange_wrap(_label(_exchange_cards, "No party listings for this run. Choose Sell… on a shared drop to stage an exchange listing.", 14, MUTED))
	_exchange_pager.text = "%d listings · Page %d / %d" % [int(_state.get("exchange_total", 0)), int(_state.get("exchange_page", 0)) + 1, int(_state.get("exchange_pages", 1))]
	_exchange_previous.disabled = int(_state.get("exchange_page", 0)) == 0 or _pending_since > 0
	_exchange_next.disabled = int(_state.get("exchange_page", 0)) + 1 >= int(_state.get("exchange_pages", 1)) or _pending_since > 0
	_exchange_previous.visible = int(_state.get("exchange_pages", 1)) > 1
	_exchange_next.visible = _exchange_previous.visible

func _exchange_wrap(label: Label) -> void:
	label.size.x = 700
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

func _exchange_card(listing: Dictionary) -> void:
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", style(Color("34575b"), Color("071417"), 8 if _compact_view else 12))
	_exchange_cards.add_child(card)
	_surface(card, 0.3)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 8)
	card.add_child(body)
	var title := HBoxContainer.new()
	title.add_theme_constant_override("separation", 10)
	body.add_child(title)
	_icon(title, int(listing.image_id), 44)
	var text := VBoxContainer.new()
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_child(text)
	var item_name := _label(text, str(listing.name), 20, GOLD)
	item_name.add_theme_font_override("font", Art.title_font())
	item_name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var details := _label(text, "Listing #%d · %d remaining · %d GC each · %s" % [int(listing.listing_id), int(listing.quantity), int(listing.price_gold), str(listing.state).capitalize()], 13, TEXT)
	details.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	if listing.state == "active" and listing.vote_state not in ["open", "ready"]:
		var actions := VBoxContainer.new()
		title.add_child(actions)
		var reprice := _button(actions, "Propose price…", func() -> void: _propose_price(listing))
		reprice.disabled = _pending_since > 0
		var withdraw := _button(actions, "Request withdrawal", func() -> void: _request("request_withdrawal", {"listing_id": int(listing.listing_id)}))
		withdraw.disabled = _pending_since > 0
	if not str(listing.withdrawal_run_id).is_empty():
		_button(title, "Open returned loot", func() -> void: _request("open", {"run_id": str(listing.withdrawal_run_id)})).disabled = _pending_since > 0
	if listing.state == "active" and listing.vote_state == "ready":
		var collect := _button(title, "Collect approved withdrawal", func() -> void: _request("withdraw_approved", {"listing_id": int(listing.listing_id), "request_id": int(listing.request_id)}))
		collect.disabled = _pending_since > 0 or not bool(_state.get("exchange_can_withdraw", false))
		collect.tooltip_text = "Visit an Exchange NPC within four tiles to return the unsold items to shared escrow."
	var payouts: Array[String] = []
	for payout: Dictionary in listing.payouts:
		payouts.append("%s: %d GC%s" % [_member_name(str(payout.username)), int(payout.gold), " (%d pending)" % int(payout.pending_gold) if int(payout.pending_gold) > 0 else ""])
	var proceeds := _label(body, "%d GC sold · %s" % [int(listing.gold_sold), ", ".join(payouts)] if not payouts.is_empty() else "Sale proceeds will be shared equally with the original team.", 12, CYAN)
	_exchange_wrap(proceeds)
	if listing.vote_state != "none":
		_rule(body)
		var veto := false
		var votes: Array[String] = []
		for voter: Dictionary in listing.votes:
			votes.append("%s: %s" % [voter.name, "No response" if voter.vote == "none" else str(voter.vote).capitalize()])
			if voter.vote == "no": veto = true
		var price_vote: bool = listing.get("vote_kind", "withdrawal") == "price_change"
		var purpose := "Price change" if price_vote else "Withdrawal"
		var summary := "%s %s" % [purpose, str(listing.vote_state).capitalize()]
		if listing.vote_state == "ready": summary = "Withdrawal approved · Awaiting collection at an Exchange NPC."
		if listing.vote_state == "open":
			var deadline := Time.get_datetime_string_from_unix_time(int(listing.deadline)).replace("T", " ")
			summary = ("A No vote blocks this %s." % purpose.to_lower() if veto else purpose + " vote is open.") + " Closes " + deadline + " UTC."
		if price_vote:
			summary += "\nProposed price: %d GC per item" % int(listing.proposed_price)
			if listing.vote_state == "open": summary += " · Current: %d GC until approval" % int(listing.price_gold)
		_exchange_wrap(_label(body, summary, 14, Color("ed9475") if veto else GOLD))
		_exchange_wrap(_label(body, " · ".join(votes), 12, MUTED))
		if listing.vote_state == "open" and listing.state == "active":
			var choices := HBoxContainer.new()
			body.add_child(choices)
			for choice: String in ["yes", "no", "abstain"]:
				var vote := _button(choices, choice.capitalize() + (" ✓" if listing.own_vote == choice else ""), func() -> void: _request("vote_price_change" if price_vote else "vote_withdrawal", {"listing_id": int(listing.listing_id), "request_id": int(listing.request_id), "vote": choice}), listing.own_vote == choice)
				vote.custom_minimum_size.x = 110
				vote.disabled = _pending_since > 0
			_exchange_wrap(_label(body, "Votes can be updated until this request resolves. Any No blocks the proposal; abstentions do not count against it.", 11, MUTED))

func _approve_payment() -> void:
	for member: Dictionary in _state.members:
		if member.self:
			_request("revoke_payment" if member.payment_approved else "approve_payment")
			return
