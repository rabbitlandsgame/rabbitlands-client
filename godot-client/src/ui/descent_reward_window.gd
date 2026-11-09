extends Control
const TextColors := preload("res://src/ui/text_colors.gd")
## The boss reward of a descent: three items offered, one to keep (descent_v1,
## server message 188, kind "reward"). The offer is the server's; a click on a
## card answers it with `#descent pick <offer> <index>` and the server closes
## the window (`open` false) once the item is in the pack. A pick that does not
## fit leaves the offer open and the server says so, so the cards come back
## after a moment. Closing the window keeps the offer: the dais offers it again.

## How long the cards wait for the server's answer to a pick before they can
## be clicked again.
const PICK_WAIT_MSEC := 3000
const RARE_COLOUR := Color("ffd27a")
const CARD_WIDTH := 150.0
const ICON_SIDE := 64.0

var panel: PanelContainer
var title: Label
var hint: Label
var cards: HBoxContainer
var close_button: Button
var _state: Dictionary = {}
var _send: Callable
var _atlas: ItemAtlas
var _waiting_until := 0

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_send = func(text: String) -> Error: return Network.send_chat(text)
	panel = PanelContainer.new()
	panel.name = "DescentRewardWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.z_index = 26
	var frame := StyleBoxFlat.new()
	frame.bg_color = Color("29251f")
	frame.border_color = Color("aa8a50")
	frame.set_border_width_all(2)
	frame.set_content_margin_all(16)
	panel.add_theme_stylebox_override("panel", frame)
	add_child(panel)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 12)
	panel.add_child(body)
	title = Label.new()
	title.text = "Choose your reward"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 22)
	TextColors.bind(title, "ready_title")
	body.add_child(title)
	cards = HBoxContainer.new()
	cards.name = "Cards"
	cards.alignment = BoxContainer.ALIGNMENT_CENTER
	cards.add_theme_constant_override("separation", 10)
	body.add_child(cards)
	hint = Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.add_child(hint)
	var actions := HBoxContainer.new()
	actions.alignment = BoxContainer.ALIGNMENT_CENTER
	body.add_child(actions)
	close_button = Button.new()
	close_button.text = "Close"
	close_button.custom_minimum_size = Vector2(100, 36)
	close_button.tooltip_text = "The offer stays open: use the dais again to choose."
	close_button.pressed.connect(close)
	actions.add_child(close_button)
	panel.hide()
	get_viewport().size_changed.connect(_layout)
	AppState.state_changed.connect(_on_state_changed)
	apply_snapshot(AppState.descent_reward)

func configure(sender: Callable) -> void:
	_send = sender

func configure_atlas(atlas: ItemAtlas) -> void:
	_atlas = atlas
	if panel != null and panel.visible:
		apply_snapshot(_state)

func _now_msec() -> int:
	return Time.get_ticks_msec()

func _on_state_changed(path: StringName) -> void:
	if path == &"descent_reward" or path == &"connection":
		apply_snapshot(AppState.descent_reward)

func apply_snapshot(state: Dictionary) -> void:
	_state = state.duplicate(true)
	_waiting_until = 0
	for child: Node in cards.get_children():
		cards.remove_child(child)
		child.queue_free()
	if not bool(state.get("open", false)):
		panel.hide()
		return
	title.text = str(state.get("title", "Choose your reward"))
	for item: Dictionary in state.get("items", []):
		cards.add_child(_card(item))
	hint.text = "Pick one to keep."
	panel.show()
	_layout.call_deferred()
	WindowStack.activate(panel)

func _card(item: Dictionary) -> Button:
	var card := Button.new()
	card.name = "Card%d" % int(item.index)
	card.custom_minimum_size = Vector2(CARD_WIDTH, 150)
	card.tooltip_text = "Take %s" % _item_text(item)
	card.pressed.connect(_pick.bind(int(item.index)))
	var rare := bool(item.get("rare", false))
	if rare:
		var glow := StyleBoxFlat.new()
		glow.bg_color = Color("3a2f1c")
		glow.border_color = RARE_COLOUR
		glow.set_border_width_all(2)
		glow.set_corner_radius_all(4)
		card.add_theme_stylebox_override("normal", glow)
	var column := VBoxContainer.new()
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.alignment = BoxContainer.ALIGNMENT_CENTER
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	column.add_theme_constant_override("separation", 4)
	card.add_child(column)
	var icon := TextureRect.new()
	icon.name = "Icon"
	icon.custom_minimum_size = Vector2(ICON_SIDE, ICON_SIDE)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if _atlas != null:
		icon.texture = _atlas.icon_for(int(item.image_id))
	column.add_child(icon)
	var name_label := _card_label(column, "Name", str(item.item), 14)
	name_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_card_label(column, "Quantity", "× %s" % _grouped(int(item.quantity)), 13) \
		.visible = int(item.quantity) > 1
	var marker := _card_label(column, "Rare", "◆ Rare", 12)
	marker.add_theme_color_override("font_color", RARE_COLOUR)
	marker.visible = rare
	return card

func _card_label(parent: Control, label_name: String, text: String, font_size: int) -> Label:
	var label := Label.new()
	label.name = label_name
	label.text = text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", font_size)
	parent.add_child(label)
	return label

static func _grouped(value: int) -> String:
	var digits := str(absi(value))
	var out := ""
	while digits.length() > 3:
		out = "," + digits.substr(digits.length() - 3) + out
		digits = digits.substr(0, digits.length() - 3)
	return ("-" if value < 0 else "") + digits + out

static func _item_text(item: Dictionary) -> String:
	var quantity := int(item.get("quantity", 1))
	return str(item.get("item", "")) + (" × %s" % _grouped(quantity) if quantity > 1 else "")

func _item(index: int) -> Dictionary:
	for item: Dictionary in _state.get("items", []):
		if int(item.index) == index:
			return item
	return {}

func _pick(index: int) -> void:
	if not bool(_state.get("open", false)) or _now_msec() < _waiting_until:
		return
	var item := _item(index)
	if item.is_empty():
		return
	var error: Error = _send.call("#descent pick %s %d" % [str(_state.offer), index])
	if error != OK:
		hint.text = "Could not send your choice. Please try again."
		return
	hint.text = "Claiming %s…" % _item_text(item)
	_waiting_until = _now_msec() + PICK_WAIT_MSEC
	_set_cards_enabled(false)
	get_tree().create_timer(PICK_WAIT_MSEC / 1000.0).timeout.connect(_end_wait, CONNECT_ONE_SHOT)

## The server kept the offer open (the pack was full, it said why): the
## cards can be clicked again.
func _end_wait() -> void:
	if _waiting_until == 0 or not panel.visible:
		return
	_waiting_until = 0
	_set_cards_enabled(true)
	hint.text = "Pick one to keep."

func _set_cards_enabled(enabled: bool) -> void:
	for child: Node in cards.get_children():
		if child is Button:
			(child as Button).disabled = not enabled

func close() -> void:
	panel.hide()

func _layout() -> void:
	if panel == null or not panel.visible:
		return
	var available := get_viewport_rect().size - Vector2(96, 88)
	panel.reset_size()
	var wanted := panel.get_combined_minimum_size()
	panel.size = Vector2(minf(maxf(wanted.x, 420.0), available.x - 24), minf(wanted.y, available.y - 24))
	panel.position = ((available - panel.size) * 0.5).max(Vector2.ZERO)
