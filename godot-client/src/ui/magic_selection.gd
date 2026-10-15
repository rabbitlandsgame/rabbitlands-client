extends Control
## Server-authored inventory quotes and portal entrances for utility spells.
signal status_changed(message: String)
signal selection_changed
signal cast_submitted(spell_id: int, power: int)
var catalog: SpellCatalog
var pending: Dictionary = {}
var _coordinate_token: Dictionary = {}
var popup: AcceptDialog
var choices: OptionButton
var quantity: SpinBox
var description: Label
var entries: Array = []
var kind := ""
var target_mode := "prepared"
var target_validator: Callable
## The practice scene supplies a local simulation; live play uses Network.
var request_sender: Callable
var _hint: Label
var _feedback := ""
var _feedback_until := 0

func _send(data: Dictionary) -> Error:
	if not request_sender.is_valid() and Network.coordinates.selected and not Network.coordinates.matches(_coordinate_token):
		return ERR_INVALID_PARAMETER
	var error: Error = int(request_sender.call(data)) if request_sender.is_valid() else Network.magic_request(data)
	if error != OK: status_changed.emit("Could not send spell. Check your connection.")
	elif data.get("op") == "cast": cast_submitted.emit(int(data.id), int(data.power))
	return error

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hint = Label.new()
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hint.add_theme_constant_override("outline_size", 5)
	_hint.add_theme_color_override("font_outline_color", Color(0.04, 0.03, 0.02))
	add_child(_hint)
	status_changed.connect(func(message: String):
		_feedback = message
		_feedback_until = Time.get_ticks_msec() + 2500)
	popup = AcceptDialog.new()
	popup.title = "Spell selection"
	popup.min_size = Vector2i(520, 220)
	popup.get_ok_button().text = "Cast"
	popup.add_cancel_button("Cancel")
	add_child(popup)
	var body := VBoxContainer.new()
	popup.add_child(body)
	choices = OptionButton.new()
	choices.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(choices)
	quantity = SpinBox.new()
	quantity.min_value = 1
	quantity.max_value = 1
	quantity.step = 1
	quantity.prefix = "Quantity: "
	body.add_child(quantity)
	description = Label.new()
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	description.custom_minimum_size = Vector2(480, 100)
	body.add_child(description)
	choices.item_selected.connect(func(_index: int) -> void: _update_quote())
	quantity.value_changed.connect(func(_value: float) -> void: _update_quote())
	popup.confirmed.connect(_confirm)
	popup.canceled.connect(cancel)
	AppState.magic_state_received.connect(_receive)
	AppState.state_changed.connect(func(path: StringName) -> void:
		if path == &"map": cancel())
	Network.magic_selection_completed.connect(func() -> void:
		AppState.pending_spell_target = ""
		pending.clear()
		_feedback_until = 0
		selection_changed.emit())
	Network.connection_state_changed.connect(func(state: String) -> void:
		if state == "disconnected": cancel(false))
	Network.coordinate_intents_invalidated.connect(func() -> void: cancel(false))

func _process(_delta: float) -> void:
	var aiming := not pending.is_empty() and not AppState.pending_spell_target.is_empty()
	_hint.visible = aiming or Time.get_ticks_msec() < _feedback_until
	if not _hint.visible: return
	_hint.text = ("%s · P%d\n%s · Esc / right click cancels" % [
		catalog.spell(int(pending.id)).get("name", "Spell"), int(pending.power),
		"Click a recipient" if AppState.pending_spell_target == "actor" else "Click a location"]) if aiming else _feedback
	var pointer := get_global_mouse_position() + Vector2(18, 22)
	_hint.global_position = pointer.min(get_viewport_rect().size - _hint.size - Vector2(8, 8)).max(Vector2(8, 8))

func begin(spell_id: int, power: int, selected_target_id := -1) -> void:
	cancel()
	var spell: Dictionary = catalog.spell(spell_id)
	if spell.is_empty(): return
	pending = {"op": "cast", "id": spell_id, "power": maxi(1, power)}
	_coordinate_token = Network.coordinates.token()
	var scope := str(spell.get("scope", "self"))
	if scope == "inventory" or (spell.get("effect") == "recall" and power >= 5):
		_send({"op": "options", "id": spell_id})
	elif scope in ["target", "burst", "location"]:
		Network.begin_magic_selection(pending, scope)
		AppState.pending_spell_target = "actor" if scope == "target" else "location"
		if scope == "target" and target_mode == "prepared" and selected_target_id >= 0 \
				and target_validator.is_valid() and bool(target_validator.call(spell_id, selected_target_id)):
			confirm_actor(selected_target_id)
			return
		status_changed.emit("Select %s for %s. Escape cancels." % [
			"an actor" if scope == "target" else "a location", spell.name])
		AppState.actor_animation_requested.emit({"actor_id": AppState.local_actor_id,
			"action": &"cast_channel_enter", "power": power})
	else:
		_send(pending)
		pending.clear()
	selection_changed.emit()

func confirm_actor(actor_id: int) -> void:
	if pending.is_empty() or Network.magic_scope != "target": return
	AppState.select_actor(actor_id)
	_finish({"target_id": actor_id})

func confirm_location(tile: Vector2i) -> void:
	if pending.is_empty() or Network.magic_scope not in ["burst", "location"]: return
	_finish({"x": tile.x, "y": tile.y})

func _finish(selection: Dictionary) -> void:
	var request := pending.duplicate()
	request.merge(selection, true)
	pending.clear()
	Network.magic_pending.clear()
	Network.magic_scope = ""
	AppState.pending_spell_target = ""
	_feedback_until = 0
	selection_changed.emit()
	_send(request)

func cancel(notify_server := true) -> void:
	if notify_server and (not pending.is_empty() or not Network.magic_pending.is_empty()):
		_send({"op":"cancel"})
		AppState.actor_animation_requested.emit({"actor_id": AppState.local_actor_id, "action": &"cast_exit"})
	pending.clear()
	Network.magic_pending.clear()
	Network.magic_scope = ""
	AppState.pending_spell_target = ""
	_feedback_until = 0
	if popup != null: popup.hide()
	selection_changed.emit()

func _unhandled_key_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel") and (not pending.is_empty() or not Network.magic_pending.is_empty()):
		cancel()
		get_viewport().set_input_as_handled()

func _receive(data: Dictionary) -> void:
	if data.get("kind") == "error":
		status_changed.emit(str(data.get("message", "Spell rejected")))
		return
	if pending.is_empty() or int(data.get("id", -1)) != int(pending.id): return
	kind = str(data.get("kind", ""))
	if kind not in ["transmute", "recall"]: return
	entries = data.get("entries", [])
	choices.clear()
	for entry: Dictionary in entries:
		choices.add_item("%s — %s" % [entry.name, entry.rarity] if kind == "transmute"
			else "%s — entrance (%d, %d)" % [entry.name, entry.x, entry.y])
	quantity.visible = kind == "transmute"
	popup.title = "Transmute items to gold" if kind == "transmute" else "Recall destination"
	_update_quote()
	popup.popup_centered()

func _update_quote() -> void:
	popup.get_ok_button().disabled = entries.is_empty()
	if entries.is_empty():
		description.text = "No eligible items or portal entrances available."
		return
	var entry: Dictionary = entries[maxi(0, choices.selected)]
	if kind == "transmute":
		quantity.max_value = int(entry.available)
		var required := int(entry.required_power)
		popup.get_ok_button().disabled = int(pending.get("power", 1)) < required
		description.text = "%s requires Power %d. Selected power: %d.\nConsume %d %s → %d Gold Coins." % [
			entry.rarity, required, int(pending.get("power", 1)), int(quantity.value),
			entry.name, int(quantity.value) * int(entry.unit_gold)]
	else:
		description.text = "Recall to the portal entrance of %s at (%d, %d).\nPower %d; your items travel with you." % [
			entry.name, entry.x, entry.y, int(pending.get("power", 1))]

func _confirm() -> void:
	if entries.is_empty() or pending.is_empty(): return
	var entry: Dictionary = entries[maxi(0, choices.selected)]
	if kind == "transmute":
		pending.merge({"slot": int(entry.slot), "item_id": int(entry.item_id), "instance_id": int(entry.get("instance_id", 0)), "quantity": int(quantity.value)}, true)
	else:
		pending["entry"] = str(entry.key)
	_send(pending)
	pending.clear()
	selection_changed.emit()
