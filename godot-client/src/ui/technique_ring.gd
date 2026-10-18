extends Control
## The technique ring: hold Tab (the `technique_ring` action) and choose a
## technique; let go to close it without using anything.
##
## One level deep, unlike the spell ring: techniques have no target type or
## power to choose. It offers the techniques the player has learned and can use
## with what they are holding right now - a shield move appears with a shield
## in hand - dimming one that is cooling down or short of action points. Up to
## eight show at once; [ and ] page through more. A wedge is chosen by clicking
## it or pressing its number, and is used through the Techniques tab, so it is
## aimed exactly as the tab and the quick slots aim it: at the selected
## creature, else the one being fought, else the next creature clicked.
##
## The script declares no `class_name`: it reads `AppState` directly.

signal technique_chosen(key: String)

const QuickRing := preload("res://src/ui/quick_spell_ring.gd")
const HoldKeys := preload("res://src/ui/hold_keys.gd")
const Icons := preload("res://src/ui/technique_icons.gd")
const TechniquesTab := preload("res://src/ui/techniques_panel.gd")
const PAGE_SIZE := 8
const INNER := 140.0
const OUTER := 252.0

## The Techniques tab, which aims and sends a chosen technique.
var techniques: VBoxContainer
var anchor_provider: Callable
var can_open: Callable
var ring_scale := 1.0
var page := 0
var entries: Array[Dictionary] = []
var buttons: Array[Button] = []
var center := Vector2.ZERO
var _held := false
var _heading: Label
var _detail: Label

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	_heading = Label.new()
	_heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_heading.add_theme_font_size_override("font_size", 15)
	_heading.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_heading)
	_detail = Label.new()
	_detail.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_detail.add_theme_font_size_override("font_size", 11)
	_detail.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_detail)
	AppState.state_changed.connect(func(path: StringName) -> void:
		if path == &"techniques" and visible: _rebuild())
	hide()

## What the ring offers: learned and usable with the gear in hand.
func offered() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for raw: Variant in AppState.techniques.get("techniques", []):
		if raw is Dictionary and TechniquesTab.offered(raw):
			result.append(raw)
	return result

func open_ring(held := false) -> void:
	if can_open.is_valid() and not bool(can_open.call()):
		return
	_held = held
	page = 0
	show()
	move_to_front()
	_rebuild()

func dismiss() -> void:
	hide()
	_held = false

## Returns true when the event belongs to the ring and must go no further.
func handle_event(event: InputEvent) -> bool:
	if event is InputEventKey:
		var key_event := event as InputEventKey
		if HoldKeys.matches("technique_ring", event):
			if key_event.pressed:
				if key_event.echo:
					return visible
				if visible:
					_held = true
					return true
				if can_open.is_valid() and not bool(can_open.call()):
					return false
				open_ring(true)
				return visible
			var owned := visible or _held
			dismiss()
			return owned
		if not visible:
			return false
		if not key_event.pressed or key_event.echo:
			return true
		var code := key_event.physical_keycode if key_event.physical_keycode != 0 else key_event.keycode
		if code == KEY_ESCAPE:
			dismiss()
		elif code == KEY_BRACKETLEFT:
			change_page(-1)
		elif code == KEY_BRACKETRIGHT:
			change_page(1)
		elif code >= KEY_1 and code <= KEY_8:
			choose(int(code - KEY_1))
		return true
	if visible and event is InputEventMouseButton and event.pressed \
			and event.button_index == MOUSE_BUTTON_RIGHT:
		dismiss()
		return true
	return false

func change_page(delta: int) -> void:
	var pages := maxi(1, ceili(float(offered().size()) / PAGE_SIZE))
	page = posmod(page + delta, pages)
	_rebuild()

func choose(index: int) -> void:
	if not visible or index < 0 or index >= entries.size():
		return
	var key := str(entries[index].get("key", ""))
	dismiss()
	if techniques != null:
		techniques.call("use", key)
	technique_chosen.emit(key)

func _rebuild() -> void:
	for button: Button in buttons:
		remove_child(button)
		button.queue_free()
	buttons.clear()
	var all := offered()
	entries = all.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
	for index in range(entries.size()):
		var row: Dictionary = entries[index]
		var key := str(row.get("key", ""))
		var waiting := float(techniques.call("ready_in", key)) if techniques != null else 0.0
		var cost := int(row.get("ap", 0))
		var title := "%d %s" % [index + 1, str(row.get("name", key)).replace(" ", "\n")]
		if waiting > 0.05:
			title += "\n%ds" % ceili(waiting)
		elif cost > 0:
			title += "\n%d AP" % cost
		var button := QuickRing.SectorButton.new()
		button.inner = INNER
		button.outer = OUTER
		button.angle = -PI / 2 + TAU * index / maxi(1, entries.size())
		button.spread = TAU / maxi(1, entries.size())
		button.setup(title, Icons.icon_for(key))
		button.name = "Technique_" + key
		var reason := str(techniques.call("unavailable_reason", key)) if techniques != null else ""
		button.modulate = Color(1, 1, 1, 1) if reason.is_empty() else Color(0.75, 0.72, 0.66, 0.6)
		button.tooltip_text = str(techniques.call("tooltip_for", key)) if techniques != null else ""
		button.pressed.connect(choose.bind(index))
		button.mouse_entered.connect(func() -> void:
			_detail.text = str(row.get("description", "")))
		add_child(button)
		buttons.append(button)
	var pages := maxi(1, ceili(float(all.size()) / PAGE_SIZE))
	_heading.text = "Techniques" + ("  %d/%d  [ ]" % [page + 1, pages] if pages > 1 else "")
	_detail.text = ("No technique you know fits what you are holding." if all.is_empty()
		else "Click or press a number. Release %s to close." % TechniquesTab.key_name("technique_ring"))
	_layout()

func _process(_delta: float) -> void:
	if not visible:
		return
	if can_open.is_valid() and not bool(can_open.call()):
		dismiss()
		return
	_layout()

func _layout() -> void:
	var anchor: Vector2 = anchor_provider.call() if anchor_provider.is_valid() else get_global_rect().get_center()
	var local: Vector2 = get_global_transform().affine_inverse() * anchor
	var factor := maxf(0.1, minf(ring_scale, minf((size.x - 16) / 560.0, (size.y - 16) / 560.0)))
	var reach := OUTER * factor
	center = local.clamp(Vector2(reach, reach).min(size / 2), (size - Vector2(reach, reach)).max(size / 2))
	for button: Button in buttons:
		button.position = center - Vector2.ONE * OUTER * factor
		button.size = Vector2.ONE * OUTER * 2
		button.scale = Vector2.ONE * factor
	_heading.position = center + Vector2(-110, -30) * factor
	_heading.size = Vector2(220, 24)
	_detail.position = center + Vector2(-110, -4) * factor
	_detail.size = Vector2(220, 60)
	# The labels stay above the sectors' bounding squares.
	move_child(_heading, -1)
	move_child(_detail, -1)
	queue_redraw()

func get_ring_bounds() -> Rect2:
	var reach := Vector2.ONE * OUTER * maxf(0.1, ring_scale)
	return get_global_transform() * Rect2(center - reach, reach * 2)

func _draw() -> void:
	if not visible:
		return
	var factor := maxf(0.1, minf(ring_scale, minf((size.x - 16) / 560.0, (size.y - 16) / 560.0)))
	draw_set_transform(center, 0, Vector2.ONE * factor)
	var fill := Color(0.035, 0.03, 0.022, 0.90)
	for step in range(64):
		var a := Vector2.from_angle(TAU * step / 64)
		var b := Vector2.from_angle(TAU * (step + 1) / 64)
		draw_colored_polygon(PackedVector2Array([a * 44, a * OUTER, b * OUTER, b * 44]), fill)
	draw_arc(Vector2.ZERO, OUTER, 0, TAU, 96, Color(0.75, 0.56, 0.29, 0.8), 1.5, true)
	draw_arc(Vector2.ZERO, 44, 0, TAU, 48, Color(0.75, 0.56, 0.29, 0.65), 1, true)

func _notification(what: int) -> void:
	if what in [NOTIFICATION_APPLICATION_FOCUS_OUT, NOTIFICATION_WM_WINDOW_FOCUS_OUT]:
		dismiss()
