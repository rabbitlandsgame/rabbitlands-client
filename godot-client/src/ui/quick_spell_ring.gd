extends "res://src/ui/spell_wheel.gd"
## Default spell ring. Orbit remains available in the comparison practice scene.
signal preferences_changed
signal tutorial_action(action: int)
const HOVER_DELAY := 0.18
const TARGET_SCOPES := ["self", "target", "allies", "burst"]
var variant := "quick"
var preferences := {"scopes": {}, "powers": {}, "pins": {}}
var target_validator: Callable
var last_spell := -1
var last_power := 1
var _frozen_center := Vector2.ZERO
var _preview: Label
var _scope_bar: GridContainer
var _scope_buttons: Array[Button] = []
var _pin: Button
var _class_buttons: Array[Button] = []
var _hover_class := ""
var _hover_started := 0
var _more := false
var _changing := false
var _casting := false

class SectorButton extends Button:
	var inner := 130.0
	var outer := 236.0
	var angle := 0.0
	var spread := PI / 3
	var selected := false
	var caption: Label
	var art: TextureRect
	func setup(title: String, texture: Texture2D) -> void:
		focus_mode = Control.FOCUS_NONE
		for state in ["normal", "hover", "pressed", "focus", "disabled"]:
			add_theme_stylebox_override(state, StyleBoxEmpty.new())
		caption = Label.new()
		caption.text = title
		caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		caption.add_theme_font_size_override("font_size", 12)
		caption.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(caption)
		if texture != null:
			art = TextureRect.new()
			art.texture = texture
			art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			art.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(art)
	func _has_point(point: Vector2) -> bool:
		var offset := point - Vector2.ONE * outer
		return offset.length() >= inner and offset.length() <= outer and absf(wrapf(offset.angle() - angle, -PI, PI)) < spread / 2 - 0.015
	func _process(_delta: float) -> void:
		var point := Vector2.ONE * outer + Vector2.from_angle(angle) * (inner + outer) / 2
		caption.position = point + Vector2(-64, -8 if art != null else -17)
		caption.size = Vector2(128, 36)
		if art != null:
			art.position = point + Vector2(-11, -33)
			art.size = Vector2(22, 22)
		queue_redraw()
	func _draw() -> void:
		var polygon := PackedVector2Array()
		var origin := Vector2.ONE * outer
		for step in range(17): polygon.append(origin + Vector2.from_angle(angle - spread / 2 + 0.02 + (spread - 0.04) * step / 16) * outer)
		for step in range(16, -1, -1): polygon.append(origin + Vector2.from_angle(angle - spread / 2 + 0.02 + (spread - 0.04) * step / 16) * inner)
		var active := is_hovered() or selected
		draw_colored_polygon(polygon, Color(0.24, 0.18, 0.085, 0.97) if active else Color(0.055, 0.046, 0.034, 0.94))
		polygon.append(polygon[0])
		draw_polyline(polygon, Color(0.95, 0.76, 0.39) if active else Color(0.50, 0.38, 0.22), 1.2, true)

func _ready() -> void:
	super._ready()
	_preview = Label.new()
	_preview.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_preview.add_theme_font_size_override("font_size", 12)
	_preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_preview)
	_scope_bar = GridContainer.new()
	_scope_bar.columns = 2
	add_child(_scope_bar)
	for scope in TARGET_SCOPES:
		var button := _small_button(scope.capitalize(), func(): select_scope(scope))
		remove_child(button)
		_scope_bar.add_child(button)
		button.toggle_mode = true
		button.custom_minimum_size = Vector2(52, 23)
		button.add_theme_font_size_override("font_size", 11)
		var style := button.get_theme_stylebox("normal", "Button").duplicate() as StyleBox
		style.set_content_margin_all(3)
		for state in ["normal", "hover", "pressed", "disabled"]: button.add_theme_stylebox_override(state, style)
		var selected_style := style.duplicate() as StyleBoxFlat
		selected_style.bg_color = Color(0.24, 0.18, 0.085)
		selected_style.border_color = Color(0.95, 0.76, 0.39)
		button.add_theme_stylebox_override("pressed", selected_style)
		button.add_theme_stylebox_override("hover_pressed", selected_style)
		_scope_buttons.append(button)
	_pin = _small_button("Unpin", toggle_pin)
	_pin.tooltip_text = "Keep up to six pinned families per class. Unpin one before adding another from More."
	_hint.text = ""

func open_wheel(held := false) -> void:
	if loadout.mode != "wheel" or (can_open.is_valid() and not can_open.call()): return
	var anchor: Vector2 = anchor_provider.call() if anchor_provider.is_valid() else get_global_rect().get_center()
	_frozen_center = get_global_transform().affine_inverse() * anchor
	_hover_class = ""
	_more = false
	super.open_wheel(held)
	if variant == "orbit": enter_class("Healing")

func handle_event(event: InputEvent) -> bool:
	if visible and event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		if event.pressed: cycle_scope()
		return true
	if visible and event is InputEventKey and event.pressed and not event.echo:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if event.ctrl_pressed or event.alt_pressed or key == KEY_ALT: return super.handle_event(event)
		if key == KEY_SPACE:
			repeat_last()
			return true
		if variant == "orbit" and key in [KEY_Q, KEY_W, KEY_E, KEY_R, KEY_T]:
			enter_class(CLASSES[[KEY_Q, KEY_W, KEY_E, KEY_R, KEY_T].find(key)])
			return true
	var was_visible := visible
	var handled := super.handle_event(event)
	if was_visible and not visible and event is InputEventKey and not event.pressed:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if key == KEY_SHIFT and event.location == KEY_LOCATION_LEFT: tutorial_action.emit(22)
	return handled

func dismiss() -> void:
	var cancelled := visible and not _casting
	super.dismiss()
	if cancelled: tutorial_action.emit(22)

func enter_class(value: String) -> void:
	if value not in CLASSES: return
	category = value
	stage = "effects"
	_more = false
	page = 0
	effect = ""
	_hover_class = ""
	_rebuild()
	tutorial_action.emit(21)

func pinned_families(value: String) -> Array[String]:
	var available := effects_for(value)
	var saved: Variant = preferences.pins.get(value, available.slice(0, 6))
	var result: Array[String] = []
	if saved is Array:
		for family in saved:
			if family in available and family not in result and result.size() < 6: result.append(str(family))
	return result

func resolve_spell(family: String) -> int:
	var variants := variants_for(family)
	var wanted := str(preferences.scopes.get(family, ""))
	for id in variants:
		if str(loadout.catalog.spell(id).scope) == wanted: return id
	for id in variants:
		if loadout.catalog.spell(id).scope == "target" and target_validator.is_valid() and target_validator.call(id, AppState.selected_actor_id): return id
	for scope in ["self", "target", "allies", "burst", "location", "inventory", "destination"]:
		for id in variants:
			if loadout.catalog.spell(id).scope == scope: return id
	return -1

func power_for(id: int) -> int:
	var family: String = loadout.catalog.effect_for(id)
	return clampi(int(preferences.powers.get(family, loadout.wheel_power)), 1, _power_limit(family))

func change_power(delta: int) -> void:
	if not visible: return
	if effect.is_empty():
		loadout.set_wheel_power(int(loadout.wheel_power) + delta)
		return
	var id := resolve_spell(effect)
	if id < 0: return
	preferences.powers[effect] = clampi(power_for(id) + delta, 1, _power_limit(effect))
	preferences_changed.emit()
	_update_details()

func select_scope(scope: String) -> void:
	if not visible or effect.is_empty(): return
	for id in variants_for(effect):
		if loadout.catalog.spell(id).scope == scope:
			preferences.scopes[effect] = scope
			preferences_changed.emit()
			_update_details()
			return

func cycle_scope() -> void:
	if not visible or effect.is_empty(): return
	var available: Array[String] = []
	for scope in TARGET_SCOPES:
		for id in variants_for(effect):
			if loadout.catalog.spell(id).scope == scope:
				available.append(scope)
				break
	if available.size() < 2: return
	var current := str(loadout.catalog.spell(resolve_spell(effect)).scope)
	select_scope(available[(available.find(current) + 1) % available.size()])

func toggle_pin() -> void:
	if effect.is_empty(): return
	var pins := pinned_families(category)
	if effect in pins: pins.erase(effect)
	elif pins.size() < 6: pins.append(effect)
	else: return
	preferences.pins[category] = pins
	preferences_changed.emit()
	_rebuild()

func choose(index: int) -> void:
	if not visible or index < 0 or index >= entries.size(): return
	var entry := entries[index]
	if stage == "classes": enter_class(str(entry.value))
	elif entry.get("more", false):
		_more = not _more
		page = 0
		_rebuild()
	else:
		effect = str(entry.value)
		var id := resolve_spell(effect)
		if id >= 0: _cast(id, power_for(id))

func _cast(id: int, power: int) -> void:
	last_spell = id
	last_power = clampi(power, 1, _power_limit(loadout.catalog.effect_for(id)))
	preferences.scopes[loadout.catalog.effect_for(id)] = str(loadout.catalog.spell(id).scope)
	preferences.powers[loadout.catalog.effect_for(id)] = last_power
	preferences_changed.emit()
	_casting = true
	dismiss()
	_casting = false
	spell_chosen.emit(id, last_power)

func repeat_last() -> void:
	if not visible or last_spell < 0: return
	_cast(last_spell, last_power)

func go_back() -> void:
	if _more:
		_more = false
		page = 0
		_rebuild()
	elif variant == "quick" and stage == "effects":
		stage = "classes"
		category = ""
		effect = ""
		_rebuild()
	else: dismiss()

func change_page(delta: int) -> void:
	if stage != "effects": return
	var count := ceili(_remaining().size() / 6.0)
	_more = true
	page = posmod(page + delta, maxi(count, 1))
	_rebuild()

func _remaining() -> Array[String]:
	var result := effects_for(category)
	for family in pinned_families(category): result.erase(family)
	return result

func _add_sector(title: String, index: int, count: int, inner: float, outer: float, action: Callable, texture: Texture2D = null) -> Button:
	var button := SectorButton.new()
	button.inner = inner
	button.outer = outer
	button.angle = -PI / 2 + TAU * index / count
	button.spread = TAU / count
	button.setup(title, texture)
	button.pressed.connect(action)
	add_child(button)
	return button

func _rebuild() -> void:
	if _preview == null or _changing: return
	_changing = true
	for button in buttons + _class_buttons:
		remove_child(button)
		button.queue_free()
	buttons.clear()
	_class_buttons.clear()
	entries.clear()
	if stage == "classes":
		for value in CLASSES: entries.append({"value": value, "label": value})
	else:
		var families := _remaining().slice(page * 6, (page + 1) * 6) if _more else pinned_families(category)
		for family in families: entries.append({"value": family, "label": Book.EFFECT_LABELS.get(family, family.capitalize())})
		if _more or not _remaining().is_empty(): entries.append({"more": true, "label": "Pinned" if _more else "More"})
		if effect.is_empty() or not families.has(effect): effect = str(families[0]) if not families.is_empty() else ""
	for index in range(entries.size()):
		var entry := entries[index]
		var texture: Texture2D = null
		if stage == "effects" and entry.has("value"): texture = loadout.catalog.icon_for(variants_for(str(entry.value))[0])
		var title := "%d %s" % [index + 1, str(entry.label).replace(" ", "\n")]
		var button := _add_sector(title, index, entries.size(), 182 if variant == "orbit" else 145, 252, choose.bind(index), texture)
		if stage == "classes":
			button.mouse_entered.connect(func():
				_hover_class = str(entry.value)
				_hover_started = Time.get_ticks_msec())
			button.mouse_exited.connect(func():
				if _hover_class == str(entry.value): _hover_class = "")
		elif entry.has("value"):
			button.mouse_entered.connect(func():
				effect = str(entry.value)
				_update_details())
		buttons.append(button)
	if variant == "orbit":
		for index in range(CLASSES.size()):
			var value: String = CLASSES[index]
			var button := _add_sector("%s %s" % [["Q", "W", "E", "R", "T"][index], value], index, 5, 124, 174, enter_class.bind(value))
			button.selected = category == value
			button.mouse_entered.connect(func():
				if category != value:
					_hover_class = value
					_hover_started = Time.get_ticks_msec())
			button.mouse_exited.connect(func():
				if _hover_class == value: _hover_class = "")
			_class_buttons.append(button)
	_previous.visible = _more and _remaining().size() > 6
	_next.visible = _previous.visible
	_back.hide()
	_close.hide()
	_hint.show()
	_hint.text = "Left Shift+Space repeats · Release / Esc closes"
	_pin.visible = not effect.is_empty()
	_scope_bar.visible = not effect.is_empty()
	_changing = false
	_update_details()
	_layout()

func _update_details() -> void:
	if _preview == null: return
	_heading.text = "Hover a class" if stage == "classes" else category + (" · More %d" % (page + 1) if _more else " · Pinned")
	var id := resolve_spell(effect) if not effect.is_empty() else -1
	_preview.text = "Left Shift+Space · repeat" if last_spell >= 0 else "Choose a spell"
	_power_label.text = "Power %d · Scroll" % int(loadout.wheel_power)
	if id >= 0:
		var definition: Dictionary = loadout.catalog.spell(id)
		var scope := str(definition.scope)
		var recipient := scope.capitalize()
		if scope == "target":
			recipient = str(AppState.actors.get(AppState.selected_actor_id, {}).get("name", "Pick target")) if target_validator.is_valid() and target_validator.call(id, AppState.selected_actor_id) else "Pick target"
		elif scope == "self": recipient = "You"
		elif scope in ["burst", "location"]: recipient = "Pick ground"
		_preview.text = "%s\n→ %s · %s" % [Book.EFFECT_LABELS.get(effect, effect.capitalize()), recipient, scope.capitalize()]
		_power_label.text = "Power %d / %d · Scroll" % [power_for(id), _power_limit(effect)]
		for index in range(_scope_buttons.size()):
			var wanted: String = TARGET_SCOPES[index]
			_scope_buttons[index].disabled = not variants_for(effect).any(func(spell_id: int): return loadout.catalog.spell(spell_id).scope == wanted)
			_scope_buttons[index].set_pressed_no_signal(scope == wanted)
		var pins := pinned_families(category)
		_pin.text = "Unpin" if effect in pins else ("Pins full" if pins.size() >= 6 else "Pin")
		_pin.disabled = effect not in pins and pins.size() >= 6
	for index in range(buttons.size()):
		var entry := entries[index]
		buttons[index].selected = entry.get("value", "") == effect
		if stage == "effects" and entry.has("value"):
			var spell_id := resolve_spell(str(entry.value))
			buttons[index].tooltip_text = "%s · P%d\nClick or %d casts; right click cycles target type." % [loadout.catalog.spell(spell_id).name, power_for(spell_id), index + 1]

func _process(_delta: float) -> void:
	if not visible: return
	if can_open.is_valid() and not can_open.call():
		reset()
		return
	if not _hover_class.is_empty() and Time.get_ticks_msec() - _hover_started >= HOVER_DELAY * 1000:
		enter_class(_hover_class)
	_layout()

func _layout() -> void:
	if _preview == null: return
	var factor := display_scale()
	center = _frozen_center.clamp(Vector2(270,265)*factor, size-Vector2(270,318)*factor)
	for button in buttons + _class_buttons:
		button.position = center - Vector2.ONE * button.outer
		button.size = Vector2.ONE * button.outer * 2
	_heading.position = center + Vector2(-106, -104)
	_heading.size = Vector2(212, 22)
	_preview.position = center + Vector2(-105, -78)
	_preview.size = Vector2(210, 42)
	_power_label.position = center + Vector2(-108, 31)
	_power_label.size = Vector2(216, 22)
	_scope_bar.position = center + Vector2(-54, 57)
	_hint.position = center + Vector2(-145, 260)
	_hint.size = Vector2(290, 20)
	_pin.position = center + Vector2(-35, 286)
	_pin.size = Vector2(70, 24)
	_previous.position = center + Vector2(-120, 286)
	_previous.size = Vector2(80, 24)
	_next.position = center + Vector2(40, 286)
	_next.size = Vector2(80, 24)
	_scale_controls()
	# Center controls stay above the geometric sectors' bounding rectangles.
	for control in [_heading, _preview, _power_label, _scope_bar, _pin, _previous, _next, _hint]: move_child(control, -1)
	queue_redraw()

func get_ring_bounds() -> Rect2:
	var factor := display_scale()
	return get_global_transform() * Rect2(center-Vector2(252,252)*factor, Vector2(504,562)*factor)

func _draw() -> void:
	draw_set_transform(center, 0, Vector2.ONE * display_scale())
	var outer := 124.0 if variant == "orbit" else 145.0
	for step in range(64):
		var a := Vector2.from_angle(TAU * step / 64)
		var b := Vector2.from_angle(TAU * (step + 1) / 64)
		draw_colored_polygon(PackedVector2Array([a * 29, a * outer, b * outer, b * 29]), Color(0.04, 0.035, 0.024, 0.96))
	draw_arc(Vector2.ZERO, 29, 0, TAU, 48, Color(0.83, 0.65, 0.32), 1, true)
