extends "res://src/ui/picture_marker_overlay.gd"
## Permanent tan entrance dots and names on north-up map pictures.
## Live map overlays share draw_marker so colour, outline and labels agree.

const DOT_COLOUR := Color("e8d09b")
const TEXT_COLOUR := Color("f2e4b7")
const TEXT_OUTLINE := Color(0.04, 0.04, 0.05, 0.95)
const LABEL_SIZE := 13
var _region_names: Array = []

func set_region_names(names: Array) -> void:
	_region_names = names
	queue_redraw()

func _draw() -> void:
	var avoid: Array[Rect2] = []
	var font := get_theme_default_font()
	for value: Variant in _region_names:
		var point: Variant = mark_point(value as Dictionary)
		if point is Vector2 and font != null:
			var width := font.get_string_size(str(value.label), HORIZONTAL_ALIGNMENT_LEFT, -1, 15).x
			avoid.append(Rect2((point as Vector2)-Vector2(width*.5+3, 17), Vector2(width+6, 34)))
	for value: Variant in _marks:
		var mark: Dictionary = value as Dictionary
		var point: Variant = mark_point(mark)
		if point is Vector2:
			draw_marker(self, point as Vector2, str(mark.get("label", "Entrance")), LABEL_SIZE, 4.0, avoid)

static func label_lines(font: Font, text: String, font_size: int) -> PackedStringArray:
	var lines := PackedStringArray()
	var line := ""
	for word: String in text.split(" ", false):
		var next := word if line.is_empty() else line + " " + word
		if not line.is_empty() and font.get_string_size(next, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x > 150.0:
			lines.append(line)
			line = word
		else:
			line = next
	if not line.is_empty():
		lines.append(line)
	return lines

static func draw_marker(canvas: Control, point: Vector2, label: String, font_size: int = LABEL_SIZE,
		radius: float = 4.0, avoid: Array[Rect2] = []) -> void:
	canvas.draw_circle(point, radius + 1.5, TEXT_OUTLINE)
	canvas.draw_circle(point, radius, DOT_COLOUR)
	var font := canvas.get_theme_default_font()
	if font == null or label.is_empty():
		return
	var lines := label_lines(font, label, font_size)
	var width := 0.0
	for line: String in lines:
		width = maxf(width, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x)
	var line_height := font.get_height(font_size)
	var at := point + Vector2(radius + 6.0, -2.0)
	var candidates: Array[Vector2] = [at, point+Vector2(-radius-6.0-width, -2.0),
		point+Vector2(radius+6.0, radius+6.0+font.get_ascent(font_size)),
		point+Vector2(radius+6.0, -radius-6.0-line_height*(lines.size()-1)),
		point+Vector2(radius+6.0, radius+34.0+font.get_ascent(font_size)),
		point+Vector2(-radius-6.0-width, radius+34.0+font.get_ascent(font_size))]
	for candidate: Vector2 in candidates:
		candidate.x = clampf(candidate.x, 4.0, maxf(4.0, canvas.size.x-width-4.0))
		candidate.y = clampf(candidate.y, font.get_ascent(font_size)+4.0,
			maxf(font.get_ascent(font_size)+4.0, canvas.size.y-line_height*(lines.size()-1)-4.0))
		at = candidate
		var rect := Rect2(at-Vector2(0, font.get_ascent(font_size)), Vector2(width, line_height*lines.size())).grow(3)
		var crowded := false
		for region: Rect2 in avoid:
			if rect.intersects(region):
				crowded = true
				break
		if not crowded:
			break
	var label_rect := Rect2(at-Vector2(0, font.get_ascent(font_size)), Vector2(width, line_height*lines.size()))
	var nearest := Vector2(clampf(point.x, label_rect.position.x, label_rect.end.x),
		clampf(point.y, label_rect.position.y, label_rect.end.y))
	if point.distance_to(nearest) > 18.0:
		var begin := point + point.direction_to(nearest)*(radius+2.0)
		canvas.draw_line(begin, nearest, TEXT_OUTLINE, 3.0, true)
		canvas.draw_line(begin, nearest, DOT_COLOUR, 1.0, true)
	for line: String in lines:
		canvas.draw_string_outline(font, at, line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, 3, TEXT_OUTLINE)
		canvas.draw_string(font, at, line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, TEXT_COLOUR)
		at.y += line_height
