extends Node2D
## Brass day/night dial driven by the existing synchronized six-hour game day.
const Chrome := preload("res://src/ui/hud_panel_chrome.gd")
var source: Control
var config: Dictionary = {}
var _angle := INF
var _native_face_flags := -1

func _ready() -> void:
	(get_parent() as Control).resized.connect(queue_redraw)

func configure(owner_main: Control, appearance: Dictionary, legacy: bool) -> void:
	source = owner_main
	if _native_face_flags < 0: _native_face_flags = source.clock_face.size_flags_vertical
	source.clock_face.size_flags_vertical = _native_face_flags if legacy else Control.SIZE_EXPAND_FILL
	config = appearance.duplicate(true)
	visible = not legacy
	source.clock_face.self_modulate.a = 1.0 if legacy else 0.0
	source.clock_hand.visible = legacy
	queue_redraw()

func _process(_delta: float) -> void:
	if source == null or not is_visible_in_tree(): return
	if not is_equal_approx(_angle, source.clock_hand.rotation):
		_angle = source.clock_hand.rotation
		queue_redraw()

func _draw() -> void:
	if source == null or config.is_empty(): return
	var face := get_parent() as Control
	var center := face.size * 0.5
	var radius := minf(face.size.x, face.size.y) * 0.5 - 2
	var edge: Color = config.border_color
	var text: Color = config.text_color
	var ink: Color = config.background_color
	ink.a = 1
	draw_circle(center, radius, ink.darkened(0.25))
	var daylight := PackedVector2Array([center])
	for step: int in 49: daylight.append(center + Vector2.from_angle(-PI / 2 + PI * step / 48.0) * (radius - 4))
	draw_colored_polygon(daylight, Color("39301e"))
	Chrome.draw_circle_border(self, center, radius, edge, "beveled")
	var font := ThemeDB.fallback_font
	for tick: int in 24:
		var direction := Vector2.from_angle(-PI / 2 + tick * TAU / 24)
		draw_line(center + direction * (radius - (7 if tick % 4 == 0 else 4)), center + direction * (radius - 2), edge, 1, true)
		if tick % 4 == 0:
			var at := center + direction * radius * 0.68
			draw_string(font, at + Vector2(-7, 3), str(tick / 4), HORIZONTAL_ALIGNMENT_CENTER, 14, maxi(8, roundi(radius * 0.28)), text)
	var sun := center + Vector2(radius * 0.31, 0)
	draw_circle(sun, radius * 0.09, edge.lightened(0.25))
	for ray: int in 8:
		var direction := Vector2.from_angle(ray * TAU / 8)
		draw_line(sun + direction * radius * 0.13, sun + direction * radius * 0.18, edge, 1, true)
	var moon := center - Vector2(radius * 0.31, 0)
	draw_circle(moon, radius * 0.14, text.darkened(0.2))
	draw_circle(moon + Vector2(radius * 0.07, -radius * 0.04), radius * 0.13, ink.darkened(0.25))
	var angle: float = source.clock_hand.rotation - PI / 2
	var direction := Vector2.from_angle(angle)
	var tangent := direction.orthogonal()
	draw_colored_polygon(PackedVector2Array([center + direction * radius * 0.79,
		center + tangent * radius * 0.065, center - direction * radius * 0.22,
		center - tangent * radius * 0.065]), text)
	draw_circle(center, radius * 0.09, edge)
	draw_circle(center, radius * 0.04, ink)
