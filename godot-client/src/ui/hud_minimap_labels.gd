extends Control
## Annotations stay above the map mask, so labels and arrowheads can sit
## outside the radius without clipping the live map or its markers.
var source: Control
var config: Dictionary = {}
var _signature: Array = []

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	resized.connect(queue_redraw)

func configure(owner_main: Control, value: Dictionary) -> void:
	source = owner_main
	config = value.duplicate(true)
	_signature.clear()
	queue_redraw()

func _process(_delta: float) -> void:
	if source == null or config.is_empty(): return
	var state: Array = [source.map_camera.rotation.y, source._current_map_display_name, size]
	if state != _signature:
		_signature = state
		queue_redraw()

func markers() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if source == null or config.is_empty() or config.map_directions == "none": return result
	var radius := maxf(12, minf(size.x, size.y) * 0.5 - 1.5 + float(config.direction_offset))
	for index: int in (1 if config.map_directions == "north" else 4):
		var angle: float = -PI * 0.5 + index * PI * 0.5 - source.map_camera.rotation.y
		var direction := Vector2(cos(angle), sin(angle))
		result.append({"position":size * 0.5 + direction * radius, "direction":direction,
			"label":["N", "E", "S", "W"][index], "arrow":index == 0 and config.north_marker == "arrow"})
	return result

func _plaque(rect: Rect2) -> void:
	if not config.map_label_frame: return
	if config.show_background: draw_style_box(_label_style(), rect)
	elif config.show_border: draw_rect(rect, config.border_color, false, 1)

func _label_style() -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = config.background_color
	box.border_color = config.border_color
	box.set_border_width_all(1 if config.show_border else 0)
	box.set_corner_radius_all(3)
	return box

func _draw() -> void:
	if source == null or config.is_empty(): return
	var font := ThemeDB.fallback_font
	var color: Color = config.text_color
	for marker: Dictionary in markers():
		var point: Vector2 = marker.position
		_plaque(Rect2(point - Vector2(12, 12), Vector2(24, 24)))
		if marker.arrow:
			var direction: Vector2 = marker.direction
			var tangent := direction.orthogonal()
			var points := PackedVector2Array([point + direction * 10, point - direction * 7 + tangent * 6,
				point - direction * 3, point - direction * 7 - tangent * 6])
			draw_colored_polygon(points, color)
			points.append(points[0])
			draw_polyline(points, config.border_color, 1.2, true)
		else:
			var width := font.get_string_size(marker.label, HORIZONTAL_ALIGNMENT_LEFT, -1, 18).x
			draw_string_outline(font, point + Vector2(-width / 2, 6), marker.label, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, 3, Color("161a1def"))
			draw_string(font, point + Vector2(-width / 2, 6), marker.label, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, color)
	if config.map_title:
		var title: String = source._current_map_display_name
		var width := minf(size.x + 60, font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 21).x + 24)
		var rect := Rect2(Vector2((size.x - width) * 0.5, -maxf(36, float(config.direction_offset) + 38)), Vector2(width, 28))
		_plaque(rect)
		draw_string_outline(font, rect.position + Vector2(6, 21), title, HORIZONTAL_ALIGNMENT_CENTER, width - 12, 21, 4, Color("161a1def"))
		draw_string(font, rect.position + Vector2(6, 21), title, HORIZONTAL_ALIGNMENT_CENTER, width - 12, 21, color)
