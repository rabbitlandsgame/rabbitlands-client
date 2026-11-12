extends PanelContainer
const Parts := preload("res://src/ui/crafting_window_parts.gd")
const Tiers := preload("res://src/state/item_instance_tiers.gd")
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
var tabs: TabBar
var _hero: Dictionary
var _totals: Label
var _summary: VBoxContainer
var _purpose: Label
var _review_requested := false
var _advanced: VBoxContainer
var _advanced_toggle: CheckButton
var _advanced_open := false
var _odds: HBoxContainer
var _operation_label: Label
var _primary_family := ""
var _primary_picker: OptionButton
var _primary_line: HBoxContainer
var _family_rows: Dictionary = {}
var _combine_toggle: CheckButton
var _combined: VBoxContainer
var _last_params: Dictionary = {}

func configure(owner_main: Node) -> void:
	main = owner_main
	name = "EquipmentEnchanting"
	theme = main.theme.duplicate() as Theme if main.theme != null else Theme.new()
	theme.default_font_size = 16
	theme.set_color("font_color", "Label", Parts.IVORY)
	add_theme_stylebox_override("panel", Parts.style(Parts.BRONZE, Color("071213"), 14))
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 10)
	add_child(body)
	var header := HBoxContainer.new()
	body.add_child(header)
	heading = Parts.label(header, "Enchant", 26)
	var serif := SystemFont.new()
	serif.font_names = PackedStringArray(["Georgia", "Noto Serif", "serif"])
	heading.add_theme_font_override("font", serif)
	Parts.button(header, "Refresh", _refresh)
	Parts.button(header, "×", hide).tooltip_text = "Close crafting window"
	var dragger := WindowDrag.attach(self, header)
	dragger.reserved_bottom = 88
	dragger.moved.connect(func(_to: Vector2) -> void: _placed = true)
	tabs = Parts.navigation(body, 2, _navigate)
	_purpose = Parts.label(body, "Imbue an individual copy with effects. Backpack only · unequip or withdraw items first.", 14)
	_purpose.modulate = Parts.MUTED
	columns = HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 16)
	body.add_child(columns)
	var left := VBoxContainer.new()
	left.custom_minimum_size.x = 220
	columns.add_child(left)
	Parts.label(left, "Backpack copies", 17)
	copies = Parts.ledger(left)
	copies.name = "EquipmentCopies"
	copies.item_selected.connect(_selection_changed)
	copies.multi_selected.connect(func(index: int, chosen: bool) -> void:
		var selected := copies.get_selected_items()
		_selection_changed(index if chosen else int(selected[0]) if not selected.is_empty() else -1))
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_child(scroll)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 12)
	scroll.add_child(right)
	_hero = Parts.hero(right)
	selected_title = _hero.title
	effects = VBoxContainer.new()
	effects.add_theme_constant_override("separation", 8)
	right.add_child(effects)
	_operation_label = Parts.label(right, "Operation", 17)
	action_picker = OptionButton.new()
	action_picker.custom_minimum_size.y = 42
	action_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_child(action_picker)
	action_picker.item_selected.connect(func(index: int) -> void:
		if _reading: return
		_action = str(action_picker.get_item_metadata(index))
		_locks = {}
		_build_options()
		_changed())
	explanation = Parts.label(right, "", 14)
	explanation.modulate = Parts.MUTED
	options = VBoxContainer.new()
	options.add_theme_constant_override("separation", 10)
	right.add_child(options)
	_summary = VBoxContainer.new()
	_summary.add_theme_constant_override("separation", 12)
	right.add_child(_summary)
	status = Parts.label(body, "", 13)
	status.custom_minimum_size.y = 30
	var footer := Parts.card(body)
	_odds = HBoxContainer.new()
	_odds.add_theme_constant_override("separation", 8)
	footer.add_child(_odds)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 12)
	footer.add_child(actions)
	_totals = Parts.label(actions, "Select an equipment copy", 15)
	preview_button = Parts.button(actions, "Check costs", _preview)
	confirm_button = Parts.button(actions, "Review enchantment", _review, true)
	confirm_button.custom_minimum_size.x = 190
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Review enchantment"
	confirmation.ok_button_text = "Apply enchantment"
	confirmation.confirmed.connect(_confirm)
	add_child(confirmation)
	add_child(preload("res://src/ui/storage_ledger_frame.gd").new())
	AppState.state_changed.connect(_state_changed)
	get_viewport().size_changed.connect(_fit)
	minimum_size_changed.connect(func() -> void: _fit.call_deferred())
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
	main.inventory_workspace.close_inspection()
	tabs.current_tab = 2
	Parts.show_hero(_hero, main, {})
	_clear(_summary)
	_clear(_odds)
	_odds.visible = false
	_totals.text = "Select an equipment copy"
	action_picker.hide()
	_operation_label.hide()
	snapshot = {}
	selected_id = 0
	_placed = false
	_stale = false
	_locks = {}
	copies.clear()
	_clear(effects)
	_clear(options)
	explanation.text = "Select an equipment copy to inspect its saved effects and available operations."
	heading.text = "Enchant" if _craft_recipe.is_empty() else "Choose copies · " + str(_craft_recipe.output)
	copies.select_mode = ItemList.SELECT_SINGLE if _craft_recipe.is_empty() else ItemList.SELECT_MULTI
	preview_button.visible = _craft_recipe.is_empty()
	confirm_button.text = "Review enchantment" if _craft_recipe.is_empty() else "Craft one…"
	show()
	main.window_stack.register(self)
	WindowStack.activate(self)
	_refresh()
	_fit.call_deferred()

func _invalidate(cancel_pending: bool = true) -> void:
	quote = {}
	_review_requested = false
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
		for index: int in tabs.tab_count: tabs.set_tab_disabled(index, true)
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
		var review := _review_requested
		_review_requested = false
		if review and not quote.is_empty(): _ask_confirmation()

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
	copies.set_meta("copy_notes", {})
	var needed := _needed()
	for row: Dictionary in snapshot.get("items", []):
		if not _craft_recipe.is_empty() and not needed.has(row.name): continue
		var index := copies.add_item(Parts.copy_text(row), main.call("_named_icon", int(row.image_id), str(row.name)))
		copies.set_item_metadata(index, int(row.instance_id))
		Parts.copy_note(copies, row)
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
		explanation.text = str(quote.summary)
		status.text = "Costs checked. The random result is rolled only after confirmation."
	tabs.visible = _craft_recipe.is_empty()
	tabs.set_tab_disabled(2, false)
	tabs.set_tab_disabled(0, not AppState.enchanting_recovery_available)
	tabs.set_tab_disabled(1, not AppState.enchanting_recovery_available)
	_update_summary()
	_update_buttons()
	_fit.call_deferred()

func _show_copy() -> void:
	_clear(effects)
	var row := _copy()
	Parts.show_hero(_hero, main, row)
	if not row.is_empty() and not row.effects.is_empty():
		Parts.label(effects, "Current effects", 17)
		var grid := GridContainer.new()
		grid.columns = 2 if get_viewport_rect().size.x >= 1100 else 1
		grid.add_theme_constant_override("h_separation", 8)
		grid.add_theme_constant_override("v_separation", 8)
		effects.add_child(grid)
		for text: String in row.effects: Parts.effect(grid, text)
	_reading = true
	action_picker.clear()
	action_picker.disabled = false
	action_picker.visible = _craft_recipe.is_empty() and not row.is_empty() and row.tier != "normal"
	_operation_label.visible = action_picker.visible
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
	_advanced = null
	_advanced_toggle = null
	_primary_picker = null
	_primary_line = null
	_primary_family = ""
	_family_rows = {}
	_combine_toggle = null
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
		_label(options, "Choose enriched essences · 1–%d total" % int(config.initial.max_essences), 14).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_initial_essences()
	elif _action == "promote":
		_label(options, "Keep both existing effects and their values. Add one new effect.", 14).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	elif _action == "remove":
		target = OptionButton.new()
		target.custom_minimum_size.y = 42
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
		dose.custom_minimum_size = Vector2(76, 42)
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
		_advanced_toggle = CheckButton.new()
		_advanced_toggle.text = "More options · favor an effect theme"
		_advanced_toggle.custom_minimum_size.y = 42
		_advanced_toggle.button_pressed = _advanced_open
		options.add_child(_advanced_toggle)
		_advanced = VBoxContainer.new()
		_advanced.visible = _advanced_open
		options.add_child(_advanced)
		_advanced_toggle.toggled.connect(func(expanded: bool) -> void:
			_advanced_open = expanded
			_advanced.visible = expanded)
		_family_grid(config.get("catalysts", []), false, _advanced)
	_reading = false
	_local_explanation()
	_fit.call_deferred()

func _family_grid(families: Array, initial: bool, parent: Node = null) -> void:
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 8)
	(parent if parent != null else options).add_child(grid)
	var initial_family := str(families[0]) if not families.is_empty() else ""
	if initial:
		for family: String in families:
			if int(snapshot.get("available", {}).get(family, 0)) > 0:
				initial_family = family
				break
	for family: String in families:
		var card := Parts.card(grid)
		var line := HBoxContainer.new()
		card.add_child(line)
		if initial: _family_rows[family] = line
		var family_rules: Dictionary = snapshot.get("rules", {}).get("essences", {}).get(family, {})
		var item := str(family_rules.get("item", "Enriched " + family + " Essence"))
		Parts.icon(line, Parts.material_icon(main, {"name": item}), 28)
		var caption := Parts.label(line, "%s\n%d owned" % [family, int(snapshot.get("available", {}).get(family, 0))], 14)
		caption.tooltip_text = "Favors: " + ", ".join(family_rules.get("favored_effects", []))
		var amount := SpinBox.new()
		amount.min_value = 0
		var settings: Dictionary = snapshot.get("rules", {})
		amount.max_value = int(settings.get("initial", {}).get("max_essences", 5)) if initial else int(settings.get("max_catalysts", 5))
		amount.custom_minimum_size = Vector2(72, 42)
		amount.value = 1 if initial and family == initial_family else 0
		line.add_child(amount)
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
	if _action == "enchant":
		var first := ""
		for family: String in selected:
			if first.is_empty(): first = family
		if not first.is_empty(): _select_primary(first, false)
		_combine_toggle.button_pressed = selected.size() > 1
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
		"enchant": text = "Each essence favors its theme. More essences improve the odds of additional effects."
		"promote": text = "Both existing effects and their values stay. Adds a third effect and turns the name yellow."
		"add": text = "Keep existing rolls and add new effects. A full blue copy needs promotion first."
		"remove": text = "Remove one random or chosen effect. Removing the last effect makes the copy plain."
		"values": text = "Keep the effects; reroll their numbers. Values can go down. More Water keeps the best new roll."
		"reroll": text = "Replace unlocked effects and numbers. Color, effect count and locked rolls stay."
	explanation.text = text
	_update_summary()

func _update_buttons() -> void:
	var blocked := _busy or _stale or _pending == "confirm" or _copy().is_empty() or not bool(snapshot.get("enabled", false))
	var issue := _selection_issue() if _craft_recipe.is_empty() and not _copy().is_empty() else ""
	blocked = blocked or not issue.is_empty()
	if not issue.is_empty() and not _busy and not _stale and (status.text.is_empty() or status.text.begins_with("Preview the costs")): status.text = issue
	preview_button.disabled = blocked
	if not _craft_recipe.is_empty():
		var selected := {}
		for index: int in copies.get_selected_items():
			var identity := int(copies.get_item_metadata(index))
			for row: Dictionary in snapshot.get("items", []):
				if int(row.instance_id) == identity: selected[row.name] = int(selected.get(row.name, 0)) + 1
		confirm_button.disabled = _busy or _stale or selected != _needed()
	else:
		confirm_button.disabled = blocked
		confirm_button.text = {"enchant":"Review enchantment", "promote":"Review promotion", "add":"Review added effects", "remove":"Review removal", "values":"Review number reroll", "reroll":"Review effect reroll"}.get(_action, "Review changes")

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

func _fit() -> void:
	if not visible or not is_inside_tree(): return
	var viewport := get_viewport_rect().size
	custom_minimum_size = Vector2(minf(1000, maxf(560, viewport.x - 112)), 0)
	size = Vector2(custom_minimum_size.x, minf(700, maxf(350, viewport.y - 112)))
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

func _review() -> void:
	if confirm_button.disabled: return
	if not _craft_recipe.is_empty() or not quote.is_empty():
		_ask_confirmation()
		return
	_preview()
	_review_requested = _busy

func _navigate(index: int) -> void:
	if index == 2: return
	var row := _copy()
	hide()
	main.inventory_workspace.recovery_window.open(index, int(row.get("slot", -1)))

func _update_summary() -> void:
	_clear(_summary)
	_clear(_odds)
	_odds.visible = false
	if not _craft_recipe.is_empty():
		_totals.text = "Craft one · selected copies may be consumed"
		return
	if _copy().is_empty():
		_totals.text = "Select an equipment copy"
		return
	var rows: Array = quote.get("inputs", []) if not quote.is_empty() else _estimated_costs()
	var config: Dictionary = snapshot.get("rules", {})
	var fee := int(quote.get("gold_fee", config.get("operations", {}).get(_action, {}).get("gold_fee", 0)))
	var costs := Parts.card(_summary, "Materials to spend")
	Parts.cost_heading(costs)
	for row: Dictionary in rows:
		var owned := -1
		for family: String in config.get("essences", {}):
			if str(config.essences[family].item) == str(row.name): owned = int(snapshot.get("available", {}).get(family, 0))
		Parts.material(costs, main, row, owned)
	if fee > 0: Parts.material(costs, main, {"name":"Gold Coins", "quantity":fee}, int(snapshot.get("gold_available", -1)))
	if rows.is_empty(): Parts.label(costs, "Choose enriched essences to see the cost.", 14)
	_totals.text = "Total cost\n" + Parts.summary(rows, fee)
	var chances: Array = quote.get("chances", [])
	if quote.is_empty() and _action == "enchant":
		var weights: Array = config.get("initial", {}).get("weights", [])
		var count := 0
		for amount: SpinBox in _families.values(): count += int(amount.value)
		if count > 0 and weights.size() == 4:
			var total := float(weights[0]) + float(weights[1]) + float(weights[2]) + float(weights[3])
			var cumulative := 0.0
			var previous := 0.0
			if total > 0:
				for index: int in 4:
					cumulative += float(weights[index])
					var probability := pow(cumulative / total, count)
					chances.append({"count":index + 1, "chance":probability - previous})
					previous = probability
	_odds.visible = not chances.is_empty()
	Parts.odds_inline(_odds, chances)

func _initial_essences() -> void:
	var body := Parts.card(options)
	_primary_line = HBoxContainer.new()
	_primary_line.add_theme_constant_override("separation", 10)
	body.add_child(_primary_line)
	_primary_picker = OptionButton.new()
	_primary_picker.custom_minimum_size.y = 42
	_primary_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_primary_line.add_child(_primary_picker)
	for family: String in FAMILIES:
		var item := str(snapshot.get("rules", {}).get("essences", {}).get(family, {}).get("item", "Enriched " + family + " Essence"))
		_primary_picker.add_icon_item(Parts.material_icon(main, {"name":item}), "%s · %d owned" % [family, int(snapshot.get("available", {}).get(family, 0))])
	_combine_toggle = CheckButton.new()
	_combine_toggle.text = "More options · combine essence themes"
	_combine_toggle.custom_minimum_size.y = 38
	options.add_child(_combine_toggle)
	_combined = VBoxContainer.new()
	_combined.visible = false
	options.add_child(_combined)
	_combine_toggle.toggled.connect(func(expanded: bool) -> void: _combined.visible = expanded)
	_family_grid(FAMILIES, true, _combined)
	var first := FAMILIES[0]
	for family: String in FAMILIES:
		if (_families[family] as SpinBox).value > 0:
			first = family
			break
	_select_primary(first, false)
	_primary_picker.item_selected.connect(func(index: int) -> void:
		_select_primary(FAMILIES[index], true)
		_changed())

func _select_primary(family: String, transfer: bool) -> void:
	var amount := 1.0
	if not _primary_family.is_empty():
		var previous := _families[_primary_family] as SpinBox
		amount = previous.value
		previous.reparent(_family_rows[_primary_family])
		(_family_rows[_primary_family] as HBoxContainer).get_parent().get_parent().show()
		if transfer: previous.set_value_no_signal(0)
	_primary_family = family
	var current := _families[family] as SpinBox
	if transfer: current.set_value_no_signal(maxf(1, amount))
	current.reparent(_primary_line)
	(_family_rows[family] as HBoxContainer).get_parent().get_parent().hide()
	_primary_picker.select(FAMILIES.find(family))

func _selection_issue() -> String:
	var config: Dictionary = snapshot.get("rules", {})
	var total := 0
	for amount: SpinBox in _families.values(): total += int(amount.value)
	var maximum := int(config.get("initial", {}).get("max_essences", 5)) if _action == "enchant" else int(config.get("max_catalysts", 5))
	if (_action == "enchant" and total < 1) or total > maximum:
		return "Choose 1–%d enriched essences in total." % maximum if _action == "enchant" else "Use no more than %d themed catalysts." % maximum
	var rows: Array = quote.get("inputs", []) if not quote.is_empty() else _estimated_costs()
	for row: Dictionary in rows:
		for family: String in config.get("essences", {}):
			if str(config.essences[family].item) == str(row.name) and snapshot.get("available", {}).has(family):
				if int(row.quantity) > int(snapshot.available[family]): return "Not enough %s. Choose fewer or gather more." % row.name
	var fee := int(quote.get("gold_fee", config.get("operations", {}).get(_action, {}).get("gold_fee", 0)))
	if snapshot.has("gold_available") and fee > int(snapshot.gold_available): return "Not enough gold for this operation."
	return ""

func _estimated_costs() -> Array:
	var config: Dictionary = snapshot.get("rules", {})
	var costs := {}
	if _action == "promote": costs = config.get("promotion", {}).get("costs", {}).duplicate()
	elif _action in ["add", "remove", "values", "reroll"]:
		var family: String = {"add":"Life", "remove":"Death", "values":"Water", "reroll":"Magic"}[_action]
		var amount := _quantity()
		if _action == "remove" and target != null and target.selected > 0: amount = 3
		if _action == "add":
			amount = 0
			var count: int = _copy().get("effects", []).size()
			var prices: Dictionary = config.get("add_costs", {}).get(_copy().get("tier", "normal"), {})
			for slot: int in range(count + 1, count + _quantity() + 1): amount += int(prices.get(str(slot), 0))
		var item := str(config.get("essences", {}).get(family, {}).get("item", "Enriched " + family + " Essence"))
		if amount > 0: costs[item] = amount
	for family: String in _families:
		var amount := int((_families[family] as SpinBox).value)
		if amount <= 0: continue
		var item := str(config.get("essences", {}).get(family, {}).get("item", "Enriched " + family + " Essence"))
		costs[item] = int(costs.get(item, 0)) + amount
	var rows: Array = []
	for item: String in costs: rows.append({"name":item, "quantity":int(costs[item])})
	return rows
