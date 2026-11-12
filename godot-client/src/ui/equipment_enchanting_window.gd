extends PanelContainer
const Tiers := preload("res://src/state/item_instance_tiers.gd")
const Icons := preload("res://src/ui/item_effect_icons.gd")
const LABELS := {"enchant": "Enchant plain equipment", "promote": "Promote blue → yellow", "add": "Add effects · Life", "remove": "Remove an effect · Death", "values": "Reroll numbers · Water", "reroll": "Reroll effects · Magic"}
const FAMILIES := ["Life", "Death", "Water", "Magic", "Fire", "Frost", "Earth", "Wind"]
var main: Node
var copies: ItemList
var heading: Label
var selected_title: Label
var effects: VBoxContainer
var options: VBoxContainer
var action_picker: OptionButton
var dose: OptionButton
var target: OptionButton
var locks_body: VBoxContainer
var explanation: Label
var status: Label
var columns: HBoxContainer
var preview_button: Button
var confirm_button: Button
var confirmation: ConfirmationDialog
var snapshot: Dictionary = {}
var quote: Dictionary = {}
var selected_id := 0
var send_request: Callable = func(request: Dictionary) -> Error: return Network.enchanting_request(request)
var reply_seconds := 8.0
var _serial := 0
var _pending := ""
var _busy := false
var _stale := false
var _reading := false
var _placed := false
var _preferred_slot := -1
var _craft_recipe: Dictionary = {}
var _craft_callback: Callable
var _families: Dictionary = {}
var _locks: Dictionary = {}
var _action := "enchant"
var _last_params: Dictionary = {}

func configure(owner_main: Node) -> void:
	main = owner_main
	name = "EquipmentEnchanting"
	theme = main.theme.duplicate() as Theme if main.theme != null else Theme.new()
	theme.default_font_size = 14
	theme.set_color("font_color", "Label", Color("eee3c8"))
	add_theme_stylebox_override("panel", _style(Color("9d7951"), Color("071213"), 14))
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 10)
	add_child(body)
	var header_panel := PanelContainer.new()
	header_panel.add_theme_stylebox_override("panel", _style(Color("3d4c43"), Color("0b2021"), 8))
	body.add_child(header_panel)
	var header := HBoxContainer.new()
	header_panel.add_child(header)
	heading = _label(header, "Equipment enchanting", 24)
	var serif := SystemFont.new()
	serif.font_names = PackedStringArray(["Georgia", "Noto Serif", "serif"])
	heading.add_theme_font_override("font", serif)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_button(header, "Refresh", _refresh)
	_button(header, "×", hide)
	var dragger := WindowDrag.attach(self, header_panel)
	dragger.reserved_bottom = 88
	dragger.moved.connect(func(_to: Vector2) -> void: _placed = true)
	_label(body, "Choose an individual, unequipped backpack copy. Stored items must be withdrawn first.", 13).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	columns = HBoxContainer.new()
	columns.add_theme_constant_override("separation", 16)
	body.add_child(columns)
	var left := VBoxContainer.new()
	left.custom_minimum_size.x = 240
	columns.add_child(left)
	_label(left, "Equipment copies", 16)
	copies = ItemList.new()
	copies.name = "EquipmentCopies"
	copies.fixed_icon_size = Vector2i(42, 42)
	copies.size_flags_vertical = Control.SIZE_EXPAND_FILL
	copies.add_theme_stylebox_override("panel", _style(Color("344e4c"), Color("0a191b"), 8))
	left.add_child(copies)
	copies.item_selected.connect(_selection_changed)
	copies.multi_selected.connect(func(index: int, chosen: bool) -> void:
		var selected := copies.get_selected_items()
		_selection_changed(index if chosen else int(selected[0]) if not selected.is_empty() else -1))
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.add_child(scroll)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 12)
	scroll.add_child(right)
	selected_title = _label(right, "Select a copy", 21)
	selected_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	effects = VBoxContainer.new()
	effects.add_theme_constant_override("separation", 8)
	right.add_child(effects)
	action_picker = OptionButton.new()
	action_picker.custom_minimum_size.y = 36
	right.add_child(action_picker)
	action_picker.item_selected.connect(func(index: int) -> void:
		if _reading: return
		_action = str(action_picker.get_item_metadata(index))
		_locks = {}
		_build_options()
		_changed())
	options = VBoxContainer.new()
	options.add_theme_constant_override("separation", 10)
	right.add_child(options)
	explanation = _label(right, "", 14)
	explanation.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	explanation.add_theme_color_override("font_color", Color("62e7e5"))
	status = _label(body, "", 14)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.custom_minimum_size.y = 36
	var footer := HBoxContainer.new()
	body.add_child(footer)
	preview_button = _button(footer, "Preview costs", _preview)
	preview_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	confirm_button = _button(footer, "Apply to selected…", _ask_confirmation)
	confirm_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	confirm_button.add_theme_stylebox_override("normal", _style(Color("62e7e5"), Color("0e3a3e"), 10))
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Confirm equipment operation"
	confirmation.confirmed.connect(_confirm)
	add_child(confirmation)
	add_child(preload("res://src/ui/storage_ledger_frame.gd").new())
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	visibility_changed.connect(func() -> void:
		if not visible: _invalidate())
	hide()

func open(preferred_slot: int = -1) -> void:
	if not AppState.enchanting_available: return
	_craft_recipe = {}
	_craft_callback = Callable()
	_preferred_slot = preferred_slot
	_begin()

func choose_ingredients(recipe: Dictionary, callback: Callable) -> void:
	if not AppState.equipment_mixing_available: return
	_craft_recipe = recipe.duplicate(true)
	_craft_callback = callback
	_preferred_slot = -1
	_begin()

func _begin() -> void:
	snapshot = {}
	selected_id = 0
	_placed = false
	_stale = false
	_locks = {}
	copies.clear()
	_clear(effects)
	_clear(options)
	explanation.text = "Select an equipment copy to inspect its saved effects and available operations."
	heading.text = "Equipment enchanting" if _craft_recipe.is_empty() else "Choose copies · " + str(_craft_recipe.output)
	copies.select_mode = ItemList.SELECT_SINGLE if _craft_recipe.is_empty() else ItemList.SELECT_MULTI
	preview_button.visible = _craft_recipe.is_empty()
	confirm_button.text = "Apply to selected…" if _craft_recipe.is_empty() else "Craft one…"
	show()
	main.window_stack.register(self)
	WindowStack.activate(self)
	_refresh()
	_fit.call_deferred()

func _invalidate(cancel_pending: bool = true) -> void:
	quote = {}
	confirmation.hide()
	confirm_button.disabled = true
	if cancel_pending:
		_serial += 1
		_pending = ""
		_busy = false

func _send(request: Dictionary) -> void:
	_serial += 1
	request["request_id"] = _serial
	_pending = str(request.op)
	_busy = true
	preview_button.disabled = true
	confirm_button.disabled = true
	if request.op == "confirm":
		for index: int in copies.item_count: copies.set_item_disabled(index, true)
		action_picker.disabled = true
		_freeze_options(options)
	var error: Error = send_request.call(request)
	if error != OK:
		_busy = false
		status.text = "Could not contact the server: " + error_string(error)
	else:
		get_tree().create_timer(reply_seconds).timeout.connect(func() -> void:
			if _busy and int(request.request_id) == _serial:
				status.text = "The server has not answered yet. Refresh to check whether the operation completed."
				if _pending != "confirm":
					_busy = false
					_update_buttons())

func _refresh() -> void:
	_invalidate()
	status.text = "Loading equipment copies…"
	_send({"op": "list"})

func _state_changed(part: StringName) -> void:
	if part == &"connection" and not AppState.authenticated:
		hide()
		snapshot = {}
	elif visible and part == &"inventory":
		_stale = true
		_invalidate(_pending != "confirm")
		status.text = "Your backpack changed. Refresh before choosing an equipment operation."
		_update_buttons()
	elif visible and part == &"enchanting":
		var incoming: Dictionary = AppState.enchanting
		if int(incoming.get("request_id", -1)) != _serial: return
		snapshot = incoming
		quote = incoming.quote if incoming.get("quote") is Dictionary else {}
		_stale = false
		_busy = false
		_pending = ""
		_render()

func _needed() -> Dictionary:
	var result := {}
	for row: Dictionary in _craft_recipe.get("equipmentIngredients", []):
		result[row.name] = int(result.get(row.name, 0)) + int(row.quantity)
	return result

func _copy() -> Dictionary:
	for row: Dictionary in snapshot.get("items", []):
		if int(row.instance_id) == selected_id: return row
	return {}

func _selection_changed(index: int) -> void:
	if _reading or _pending == "confirm": return
	selected_id = int(copies.get_item_metadata(index)) if index >= 0 else 0
	_locks = {}
	_changed()
	_show_copy()

func _render() -> void:
	_reading = true
	copies.clear()
	var found := false
	var needed := _needed()
	for row: Dictionary in snapshot.get("items", []):
		if not _craft_recipe.is_empty() and not needed.has(row.name): continue
		var index := copies.add_item("Slot %d · %s" % [int(row.slot) + 1, row.name], main.call("_named_icon", int(row.image_id), str(row.name)))
		copies.set_item_metadata(index, int(row.instance_id))
		copies.set_item_custom_fg_color(index, Tiers.color(str(row.tier)))
		copies.set_item_tooltip(index, str(row.name) + "\n" + "\n".join(row.effects))
		if int(row.instance_id) == selected_id or (_preferred_slot >= 0 and int(row.slot) == _preferred_slot):
			copies.select(index)
			selected_id = int(row.instance_id)
			found = true
	if not found: selected_id = 0
	_preferred_slot = -1
	_reading = false
	status.text = str(snapshot.get("error", ""))
	if status.text.is_empty(): status.text = str(snapshot.get("message", ""))
	_show_copy()
	if not quote.is_empty():
		_restore_options()
		explanation.text = str(quote.summary) + "\nCost: " + _materials(quote.inputs).replace("\n", " + ") + " · Gold fee: %d" % int(quote.gold_fee)
		var odds := PackedStringArray()
		for chance: Dictionary in quote.chances:
			odds.append("%d effect(s): %.2f%%" % [int(chance.count), float(chance.chance) * 100])
		if not odds.is_empty(): explanation.text += "\n" + " · ".join(odds)
		status.text = "Preview checked. The random result is rolled only after you confirm."
	_update_buttons()
	_fit.call_deferred()

func _show_copy() -> void:
	_clear(effects)
	var row := _copy()
	selected_title.text = str(row.get("name", "Select a copy"))
	selected_title.add_theme_color_override("font_color", Tiers.color(str(row.get("tier", "normal"))))
	if not row.is_empty():
		var condition := "Durability unknown" if row.durability == null or row.max_durability == null else "Durability %d / %d" % [int(row.durability), int(row.max_durability)]
		_label(effects, "Quality %d%% · %s" % [int(row.quality), condition], 13)
		var effect_grid := GridContainer.new()
		effect_grid.columns = 2 if get_viewport_rect().size.x >= 1000 else 1
		effect_grid.add_theme_constant_override("h_separation", 12)
		effect_grid.add_theme_constant_override("v_separation", 8)
		effects.add_child(effect_grid)
		for text: String in row.effects:
			var line := HBoxContainer.new()
			line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			effect_grid.add_child(line)
			var icon := TextureRect.new()
			icon.texture = Icons.texture(str(Icons.presentation(text).name))
			icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			icon.custom_minimum_size = Vector2(26, 26)
			line.add_child(icon)
			var label := _label(line, text, 14)
			label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_reading = true
	action_picker.clear()
	action_picker.disabled = false
	action_picker.visible = _craft_recipe.is_empty() and not row.is_empty()
	var actions: Array = []
	if not row.is_empty():
		if row.tier == "normal": actions = ["enchant"]
		else:
			if row.tier == "magic" and row.effects.size() == 2: actions.append("promote")
			if row.effects.size() < (2 if row.tier == "magic" else 4): actions.append("add")
			actions.append_array(["remove", "values", "reroll"])
	if _action not in actions: _action = str(actions[0]) if not actions.is_empty() else "enchant"
	for action: String in actions:
		action_picker.add_item(str(LABELS[action]))
		var index := action_picker.item_count - 1
		action_picker.set_item_metadata(index, action)
		if action == _action: action_picker.select(index)
	_reading = false
	_build_options()
	if not _craft_recipe.is_empty():
		explanation.text = "Select exactly these equipment copies:\n" + _materials(_craft_recipe.get("equipmentIngredients", [])) + "\n\nCrafts one item using normal mixing success, failure and Recycler rules. Selected equipment is lost on success or critical failure when ingredients are consumed."
	_update_buttons()

func _build_options() -> void:
	_reading = true
	_clear(options)
	_families = {}
	dose = null
	target = null
	locks_body = null
	if not _craft_recipe.is_empty() or _copy().is_empty():
		_reading = false
		return
	var settings: Variant = snapshot.get("rules")
	if not settings is Dictionary or settings.is_empty():
		_reading = false
		return
	var config: Dictionary = settings
	var row := _copy()
	if _action == "enchant":
		_label(options, "Enriched essences · 1–%d total · each favors its theme" % int(config.initial.max_essences), 14).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_family_grid(FAMILIES, true)
	elif _action == "promote":
		_label(options, "Preserve both rolls and add a third effect.\nPromotion cost:\n" + _cost_dictionary(config.promotion.costs), 14).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	elif _action == "remove":
		target = OptionButton.new()
		options.add_child(target)
		target.add_item("Random effect · 1 Death")
		target.set_item_metadata(0, "")
		for effect: String in row.effect_names:
			target.add_item(effect + " · 3 Death")
			target.set_item_metadata(target.item_count - 1, effect)
		target.item_selected.connect(func(_index: int) -> void: _changed())
	else:
		var line := HBoxContainer.new()
		options.add_child(line)
		_label(line, "Effects to add" if _action == "add" else "Enriched essences to spend", 14)
		dose = OptionButton.new()
		line.add_child(dose)
		var quantities: Array = [1,3,5] if _action == "reroll" else [1,2,3,4,5]
		if _action == "add": quantities = range(1, (2 if row.tier == "magic" else 4) - row.effects.size() + 1)
		for amount: int in quantities:
			dose.add_item(str(amount))
			dose.set_item_metadata(dose.item_count - 1, amount)
		dose.item_selected.connect(func(_index: int) -> void:
			_locks = {}
			_rebuild_locks()
			_changed())
	if _action == "reroll":
		locks_body = VBoxContainer.new()
		options.add_child(locks_body)
		_rebuild_locks()
	if _action in ["promote", "add", "reroll"] and int(config.get("max_catalysts", 5)) > 0:
		_label(options, "Optional themed catalysts", 14)
		_family_grid(config.get("catalysts", []), false)
	_reading = false
	_local_explanation()
	_fit.call_deferred()

func _family_grid(families: Array, initial: bool) -> void:
	var grid := GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 10)
	options.add_child(grid)
	var initial_family := str(families[0]) if not families.is_empty() else ""
	if initial:
		for family: String in families:
			if int(snapshot.get("available", {}).get(family, 0)) > 0:
				initial_family = family
				break
	for family: String in families:
		_label(grid, "%s · %d held" % [family, int(snapshot.get("available", {}).get(family, 0))], 13)
		var amount := SpinBox.new()
		amount.min_value = 0
		var settings: Dictionary = snapshot.get("rules", {})
		amount.max_value = int(settings.get("initial", {}).get("max_essences", 5)) if initial else int(settings.get("max_catalysts", 5))
		amount.custom_minimum_size.x = 58
		amount.value = 1 if initial and family == initial_family else 0
		grid.add_child(amount)
		_families[family] = amount
		amount.value_changed.connect(func(_value: float) -> void: _changed())

func _rebuild_locks() -> void:
	if locks_body == null: return
	_clear(locks_body)
	var quantity := _quantity()
	var maximum := mini(0 if quantity == 1 else 1 if quantity == 3 else 2, _copy().effects.size() - 1)
	_label(locks_body, "Preserve up to %d effect(s), including their rolled numbers" % maximum, 13).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	for effect: String in _copy().effect_names:
		var button := CheckBox.new()
		button.text = effect
		button.button_pressed = bool(_locks.get(effect, false))
		button.disabled = maximum <= 0
		locks_body.add_child(button)
		button.toggled.connect(func(keep: bool) -> void:
			if keep and _locks.size() >= maximum:
				button.set_pressed_no_signal(false)
				return
			if keep: _locks[effect] = true
			else: _locks.erase(effect)
			_changed())

func _quantity() -> int:
	return int(dose.get_item_metadata(dose.selected)) if dose != null and dose.selected >= 0 else 1

func _restore_options() -> void:
	_reading = true
	if dose != null:
		for index: int in dose.item_count:
			if int(dose.get_item_metadata(index)) == int(_last_params.get("quantity", 1)): dose.select(index)
	var selected: Dictionary = _last_params.get("essences", {}) if _action == "enchant" else _last_params.get("catalysts", {})
	for family: String in _families:
		(_families[family] as SpinBox).set_value_no_signal(int(selected.get(family, 0)))
	if target != null:
		for index: int in target.item_count:
			if str(target.get_item_metadata(index)) == str(_last_params.get("effect", "")): target.select(index)
	_locks = {}
	for effect: String in _last_params.get("locks", []): _locks[effect] = true
	_rebuild_locks()
	_reading = false

func _params() -> Dictionary:
	var request := {"op": "quote", "action": _action, "instance_id": selected_id, "quantity": _quantity()}
	var chosen := {}
	for family: String in _families:
		var amount := int((_families[family] as SpinBox).value)
		if amount > 0: chosen[family] = amount
	request["essences" if _action == "enchant" else "catalysts"] = chosen
	if _action == "remove" and target != null and target.selected > 0:
		request["effect"] = str(target.get_item_metadata(target.selected))
		request["quantity"] = 3
	if _action == "reroll": request["locks"] = _locks.keys()
	return request

func _changed() -> void:
	if _reading or _pending == "confirm": return
	_invalidate()
	status.text = "Preview the costs before applying this operation."
	_local_explanation()
	_update_buttons()

func _local_explanation() -> void:
	if not _craft_recipe.is_empty(): return
	var text := ""
	match _action:
		"enchant":
			var settings: Variant = snapshot.get("rules", {})
			var weights: Array = settings.get("initial", {}).get("weights", []) if settings is Dictionary else []
			if weights.size() == 4:
				var total := float(weights[0]) + float(weights[1]) + float(weights[2]) + float(weights[3])
				text = "With one enriched essence: %.2f%% one effect, %.2f%% two, %.2f%% three, %.2f%% four. More essences roll the count again and keep the highest; numeric limits stay the same." % [100 * float(weights[0]) / total, 100 * float(weights[1]) / total, 100 * float(weights[2]) / total, 100 * float(weights[3]) / total]
		"promote": text = "Guaranteed three effects with a yellow name. Both existing effects and values are preserved."
		"add": text = "Add distinct eligible effects, favoring Life's theme. Blue equipment must be promoted to exceed two effects. Preview shows the Life cost for the slots you are filling."
		"remove": text = "One Death removes a random effect. Three removes the effect you choose. Removing the last effect returns the item to plain."
		"values": text = "Keep effect names and color. Reroll every number once per Water essence and keep its best NEW roll. Existing numbers can go down."
		"reroll": text = "Preserve color and effect count. One Magic rerolls everything; three can lock one effect, five can lock two. Magic and optional catalysts favor their themes."
	explanation.text = text

func _update_buttons() -> void:
	preview_button.disabled = _busy or _stale or _copy().is_empty() or not bool(snapshot.get("enabled", false))
	if not _craft_recipe.is_empty():
		var selected := {}
		for index: int in copies.get_selected_items():
			var identity := int(copies.get_item_metadata(index))
			for row: Dictionary in snapshot.get("items", []):
				if int(row.instance_id) == identity: selected[row.name] = int(selected.get(row.name, 0)) + 1
		confirm_button.disabled = _busy or _stale or selected != _needed()
	else:
		confirm_button.disabled = _busy or _stale or quote.is_empty()

func _preview() -> void:
	_invalidate()
	_last_params = _params().duplicate(true)
	_send(_last_params.duplicate(true))
	if _busy: status.text = "Checking this copy, material costs and possible outcomes…"

func _ask_confirmation() -> void:
	if confirm_button.disabled: return
	if not _craft_recipe.is_empty():
		var text := "Craft one %s?\n\nThese exact equipment copies may be consumed:\n" % _craft_recipe.output
		for index: int in copies.get_selected_items():
			text += copies.get_item_text(index) + "\n" + copies.get_item_tooltip(index) + "\n\n"
		confirmation.dialog_text = text + "Success consumes selected equipment unless Recycler retains the inputs. A critical failure consumes them; an ordinary failure keeps them."
	else:
		confirmation.dialog_text = "%s\n\nChange the selected %s?\nExisting effects:\n%s\n\nCost:\n%s\nGold fee: %d\n\nRandom results are rolled after confirmation." % [quote.summary, quote.name, "\n".join(_copy().effects), _materials(quote.inputs), int(quote.gold_fee)]
	confirmation.popup_centered(Vector2i(520, 0))

func _confirm() -> void:
	if not _craft_recipe.is_empty():
		if _busy or _stale or confirm_button.disabled: return
		var ids: Array = []
		for index: int in copies.get_selected_items(): ids.append(int(copies.get_item_metadata(index)))
		var callback := _craft_callback
		hide()
		if callback.is_valid(): callback.call(ids)
		return
	if quote.is_empty() or _busy: return
	var token := str(quote.token)
	quote = {}
	_send({"op": "confirm", "token": token})
	if _busy: status.text = "Applying the equipment operation…"

func _materials(rows: Array) -> String:
	var values := PackedStringArray()
	for row: Dictionary in rows: values.append("%d %s" % [int(row.quantity), str(row.name)])
	return "\n".join(values)

func _cost_dictionary(values: Dictionary) -> String:
	var result := PackedStringArray()
	for key: String in values: result.append("%d %s" % [int(values[key]), key])
	return "\n".join(result)

func _fit() -> void:
	if not visible or not is_inside_tree(): return
	var viewport := get_viewport_rect().size
	custom_minimum_size = Vector2(minf(900, maxf(600, viewport.x - 112)), 0)
	columns.custom_minimum_size.y = minf(430, maxf(180, viewport.y - 340))
	size = get_combined_minimum_size()
	var desired := position if _placed else (viewport - size - Vector2(96, 88)) / 2
	position = Vector2(clampf(desired.x, 8, maxf(8, viewport.x - size.x - 104)), clampf(desired.y, 8, maxf(8, viewport.y - size.y - 96)))

func _clear(parent: Node) -> void:
	for child: Node in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func _freeze_options(parent: Node) -> void:
	for child: Node in parent.get_children():
		if child is BaseButton: (child as BaseButton).disabled = true
		if child is SpinBox: (child as SpinBox).editable = false
		_freeze_options(child)

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
		result.add_theme_stylebox_override(state, _style(Color("9d7951"), Color("10272a") if state == "hover" else Color("091718"), 8))
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
