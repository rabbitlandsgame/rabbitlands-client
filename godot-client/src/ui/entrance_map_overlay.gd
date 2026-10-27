extends "res://src/ui/picture_marker_overlay.gd"
## Permanent tan entrance dots and names on north-up map pictures.
## Live map overlays share draw_marker so colour, outline and labels agree.
##
## A building's door (cartography `kind` "building") is a round dot in the
## colour of the shop behind it - the mark's `colour`, which main.gd sets from
## ServiceOverlay.door_colour - or tan, and carries no permanent name: a town's
## doors stand a few metres apart, so they are named on hover (label_at) only.
## A cave keeps its permanent name.

const DOT_COLOUR := Color("e8d09b")
const TEXT_COLOUR := Color("f2e4b7")
const TEXT_OUTLINE := Color(0.04, 0.04, 0.05, 0.95)
const LABEL_SIZE := 13
const TextColors := preload("res://src/ui/text_colors.gd")
var _region_names: Array = []

## Whether a door record or mark is a building's door rather than a cave's.
static func is_building(mark: Dictionary) -> bool:
	return str(mark.get("kind", "")) == "building"

## An unlabelled door dot, outlined as the labelled one is.
static func draw_dot(canvas: Control, point: Vector2, colour: Color, radius: float = 4.0) -> void:
	canvas.draw_circle(point, radius + 1.5, TEXT_OUTLINE)
	canvas.draw_circle(point, radius, colour)

func _ready() -> void:
	super._ready()
	TextColors.events().changed.connect(_on_text_colors_changed)

func _on_text_colors_changed(_role: String) -> void:
	queue_redraw()

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
	# Building doors first, so a cave's name is never drawn under a door dot.
	for buildings: bool in [true, false]:
		for value: Variant in _marks:
			var mark: Dictionary = value as Dictionary
			if is_building(mark) != buildings:
				continue
			var point: Variant = mark_point(mark)
			if not point is Vector2:
				continue
			if buildings:
				draw_dot(self, point as Vector2, mark.get("colour", DOT_COLOUR) as Color)
			else:
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
		canvas.draw_string(font, at, line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, TextColors.color("map_service", TEXT_COLOUR))
		at.y += line_height
