extends Control
## The spell_ring key (Left Shift by default) owns ring input until released.
## Alt remains available to quick slots.
signal spell_chosen(id: int, power: int)
signal opened
const Book := preload("res://src/ui/spells_window.gd")
const HoldKeys := preload("res://src/ui/hold_keys.gd")
const CLASSES := ["Healing", "Defense", "Offense", "Support", "Utility"]
const SCOPES := ["self", "target", "allies", "burst", "utility"]
const PAGE_SIZE := 8
const RADIUS := 204.0
const NODE_SIZE := Vector2(132, 58)
var loadout
var anchor_provider: Callable
var can_open: Callable
var stage := "classes"
var category := ""
var effect := ""
var page := 0
var entries: Array[Dictionary] = []
var buttons: Array[Button] = []
var center := Vector2.ZERO
var _ring_held := false
var _latched := false
var _heading: Label
var _power_label: Label
var _hint: Label
var _back: Button
var _close: Button
var _previous: Button
var _next: Button

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	_heading = Label.new()
	_heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_heading.add_theme_font_size_override("font_size", 15)
	_heading.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_heading)
	_power_label = Label.new()
	_power_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_power_label.add_theme_font_size_override("font_size", 14)
	_power_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_power_label)
	_hint = Label.new()
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.add_theme_font_size_override("font_size", 11)
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_hint)
	_back = _small_button("Back", go_back)
	_close = _small_button("Close", dismiss)
	_previous = _small_button("[ Previous", func(): change_page(-1))
	_next = _small_button("Next ]", func(): change_page(1))
	loadout.changed.connect(func():
		if loadout.mode != "wheel": reset()
		elif visible: _rebuild())
	AppState.magic_state_received.connect(func(_data: Dictionary):
		if visible: _rebuild())
	hide()

func _small_button(title: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = title
	button.focus_mode = Control.FOCUS_NONE
	button.add_theme_font_size_override("font_size", 12)
	button.pressed.connect(action)
	add_child(button)
	return button

func open_wheel(held := false) -> void:
	if loadout.mode != "wheel" or (can_open.is_valid() and not can_open.call()): return
	_ring_held = held
	_latched = false
	stage = "classes"
	category = ""
	effect = ""
	page = 0
	opened.emit()
	show()
	_rebuild()

func dismiss() -> void:
	hide()
	_latched = _ring_held

func reset() -> void:
	hide()
	_ring_held = false
	_latched = false

func handle_event(event: InputEvent) -> bool:
	if loadout.mode != "wheel": return false
	if event is InputEventKey:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		# Alt belongs to the quickbar and operating system, even while a ring is open.
		var ring_key := HoldKeys.matches("spell_ring", event)
		if (event.ctrl_pressed or event.alt_pressed or key == KEY_ALT) and not ring_key:
			reset()
			return false
		if ring_key:
			if event.pressed:
				if event.echo: return visible or _latched
				if can_open.is_valid() and not can_open.call(): return false
				if visible: _ring_held = true
				else: open_wheel(true)
				return visible
			var owned := _ring_held or _latched
			reset()
			return owned
		if _latched: return true
		if not visible: return false
		if not event.pressed or event.echo: return true
		if key == KEY_ESCAPE: dismiss()
		elif key == KEY_BACKSPACE: go_back()
		elif key == KEY_BRACKETLEFT: change_page(-1)
		elif key == KEY_BRACKETRIGHT: change_page(1)
		elif key >= KEY_1 and key <= KEY_8: choose(int(key - KEY_1))
		return true
	if _latched: return true
	if visible and event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			go_back()
			return true
		if event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			change_power(1 if event.button_index == MOUSE_BUTTON_WHEEL_UP else -1)
			return true
	# Left clicks must reach the actual ring buttons through normal GUI routing.
	return false

func category_for(value: String) -> String:
	if value in ["blink", "transmute", "recall"]: return "Utility"
	return str({"Health": "Healing", "Defense": "Defense", "Attack": "Offense"}.get(Book.EFFECT_GROUPS.get(value, "General"), "Support"))

func effects_for(value: String) -> Array[String]:
	var result: Array[String] = []
	for id in loadout.catalog.spell_ids():
		var family: String = loadout.catalog.effect_for(id)
		if category_for(family) == value and family not in result: result.append(family)
	# Catalog ID order keeps learned paths stable when proficiency changes.
	return result

func variants_for(value: String) -> Array[int]:
	var result: Array[int] = []
	for id in loadout.catalog.spell_ids():
		if loadout.catalog.effect_for(id) == value: result.append(id)
	return result

func choose(index: int) -> void:
	if not visible or index < 0 or index >= entries.size(): return
	var entry := entries[index]
	if entry.get("disabled", false): return
	if entry.has("id"):
		dismiss()
		spell_chosen.emit(int(entry.id), power_for(int(entry.id)))
	elif stage == "classes":
		category = str(entry.value)
		stage = "effects"
		page = 0
		_rebuild()
	else:
		effect = str(entry.value)
		var variants := variants_for(effect)
		if variants.size() == 1:
			dismiss()
			spell_chosen.emit(variants[0], power_for(variants[0]))
		else:
			stage = "targets"
			_rebuild()

func go_back() -> void:
	if stage == "targets": stage = "effects"
	elif stage == "effects":
		stage = "classes"
		page = 0
	else:
		dismiss()
		return
	_rebuild()

func change_page(delta: int) -> void:
	if stage != "effects": return
	var count := ceili(effects_for(category).size() / float(PAGE_SIZE))
	page = posmod(page + delta, maxi(1, count))
	_rebuild()

func _power_limit(family: String) -> int:
	var stated: Dictionary = AppState.spell_power.get(family, {})
	return clampi(int(stated.get("limit", 1)), 1, 10)

func power_for(id: int) -> int:
	return mini(int(loadout.wheel_power), _power_limit(loadout.catalog.effect_for(id)))

func change_power(delta: int) -> void:
	if not visible: return
	var limit := _power_limit(effect) if stage == "targets" else 10
	var current := mini(int(loadout.wheel_power), limit)
	# Scroll from the effective power, even if this family caps a higher setting.
	var next := clampi(current + delta, 1, limit)
	if next != current: loadout.set_wheel_power(next)

func _rebuild() -> void:
	for button in buttons:
		remove_child(button)
		button.queue_free()
	buttons.clear()
	entries.clear()
	if stage == "classes":
		for value in CLASSES:
			var families := effects_for(value)
			entries.append({"label": value, "value": value, "icon_id": variants_for(families[0])[0]})
	elif stage == "effects":
		var families := effects_for(category)
		for index in range(page * PAGE_SIZE, mini((page + 1) * PAGE_SIZE, families.size())):
			var family := families[index]
			var id := variants_for(family)[0]
			entries.append({"label": Book.EFFECT_LABELS.get(family, family.capitalize()), "value": family, "icon_id": id, "power": power_for(id)})
	else:
		var variants := variants_for(effect)
		for scope in SCOPES:
			var entry := {"label": scope.capitalize(), "disabled": true}
			for id in variants:
				var definition: Dictionary = loadout.catalog.spell(id)
				var target := str(definition.get("scope", "self"))
				if target not in SCOPES: target = "utility"
				if target != scope: continue
				var power := power_for(id)
				entry = {"label": "%s · P%d" % [scope.capitalize(), power], "id": id, "icon_id": id}
			entries.append(entry)
	for index in range(entries.size()):
		var entry := entries[index]
		var button := Button.new()
		var title := str(entry.label).replace(" ", "\n") if stage == "effects" else str(entry.label)
		if entry.has("power"): title += "\nP%d" % int(entry.power)
		button.text = "%d  %s" % [index + 1, title]
		button.add_theme_font_size_override("font_size", 12)
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		button.expand_icon = true
		button.add_theme_constant_override("icon_max_width", 23)
		button.focus_mode = Control.FOCUS_NONE
		button.disabled = bool(entry.get("disabled", false))
		button.tooltip_text = str(entry.label)
		if entry.has("power"): button.tooltip_text += "\nPower %d · scroll up/down to adjust." % int(entry.power)
		if entry.has("icon_id"): button.icon = loadout.catalog.icon_for(int(entry.icon_id))
		if entry.has("id"):
			button.tooltip_text = "%s\nPower %d · scroll up/down to adjust." % [loadout.catalog.spell(int(entry.id)).name, power_for(int(entry.id))]
			var reasons: Array[String] = loadout.catalog.unavailable_reasons(int(entry.id), AppState.known_knowledge, AppState.stats, AppState.inventory)
			if not reasons.is_empty():
				button.modulate.a = 0.6
				button.tooltip_text += "\n" + reasons[0]
		button.pressed.connect(choose.bind(index))
		add_child(button)
		buttons.append(button)
	_heading.text = "Choose a class" if stage == "classes" else category
	if stage == "targets": _heading.text = str(Book.EFFECT_LABELS.get(effect, effect.capitalize()))
	var limit := _power_limit(effect) if stage == "targets" else 10
	_power_label.text = "Power %d / %d · Scroll" % [mini(int(loadout.wheel_power), limit), limit]
	_hint.text = "1–%d or click\nRelease Left Shift to close" % entries.size() if _ring_held else "1–%d or click\nEsc to close" % entries.size()
	_back.visible = stage != "classes"
	var paged := stage == "effects" and effects_for(category).size() > PAGE_SIZE
	_previous.visible = paged
	_next.visible = paged
	if paged: _heading.text += " · %d/%d" % [page + 1, ceili(effects_for(category).size() / float(PAGE_SIZE))]
	_layout()

func _process(_delta: float) -> void:
	if visible:
		if can_open.is_valid() and not can_open.call(): reset()
		else: _layout()

func _layout() -> void:
	var anchor: Vector2 = anchor_provider.call() if anchor_provider.is_valid() else get_global_rect().get_center()
	center = get_global_transform().affine_inverse() * anchor
	var margin := Vector2(RADIUS + NODE_SIZE.x / 2 + 10, RADIUS + NODE_SIZE.y / 2 + 12) * display_scale()
	center = center.clamp(margin.min(size / 2), (size - margin).max(size / 2))
	for index in range(buttons.size()):
		var angle := -PI / 2 + TAU * index / buttons.size()
		buttons[index].position = center + Vector2.from_angle(angle) * RADIUS - NODE_SIZE / 2
		buttons[index].size = NODE_SIZE
	_heading.position = center + Vector2(-110, -108)
	_heading.size = Vector2(220, 24)
	_power_label.position = center + Vector2(-110, 46)
	_power_label.size = Vector2(220, 20)
	_hint.position = center + Vector2(-95, 68)
	_hint.size = Vector2(190, 32)
	_back.position = center + Vector2(-76, 104)
	_back.size = Vector2(70, 24)
	_close.position = center + Vector2(6 if _back.visible else -35, 104)
	_close.size = Vector2(70, 24)
	_previous.position = center + Vector2(-94, -76)
	_previous.size = Vector2(88, 28)
	_next.position = center + Vector2(6, -76)
	_next.size = Vector2(88, 28)
	_scale_controls()
	queue_redraw()

func display_scale() -> float:
	# This footprint includes the largest ring and its footer controls.
	return maxf(0.1, minf(float(loadout.ring_size) / 100.0, minf((size.x-16)/560.0, (size.y-16)/583.0)))

func _scale_controls() -> void:
	var factor := display_scale()
	for child in get_children():
		if child is Control and child.visible:
			child.position = center + (child.position-center) * factor
			child.scale = Vector2.ONE * factor

func get_ring_bounds() -> Rect2:
	var margin := Vector2(RADIUS + NODE_SIZE.x/2, RADIUS + NODE_SIZE.y/2) * display_scale()
	return get_global_transform() * Rect2(center-margin, margin*2)

func _draw() -> void:
	# An annulus leaves the character visible in the middle of the wheel.
	draw_set_transform(center, 0, Vector2.ONE * display_scale())
	var fill := Color(0.035, 0.03, 0.022, 0.32)
	for step in range(64):
		var a := Vector2.from_angle(TAU * step / 64)
		var b := Vector2.from_angle(TAU * (step + 1) / 64)
		draw_colored_polygon(PackedVector2Array([a * 44, a * 236, b * 236, b * 44]), fill)
	draw_arc(Vector2.ZERO, 236, 0, TAU, 96, Color(0.75, 0.56, 0.29, 0.8), 1.5, true)
	draw_arc(Vector2.ZERO, 44, 0, TAU, 48, Color(0.75, 0.56, 0.29, 0.65), 1, true)

func _notification(what: int) -> void:
	if what in [NOTIFICATION_APPLICATION_FOCUS_OUT, NOTIFICATION_WM_WINDOW_FOCUS_OUT]: reset()
