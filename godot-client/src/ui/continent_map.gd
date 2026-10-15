extends Control
## Geographic region footprints share the picture's north-up projection.
## Labels and hover outlines remain readable without drawing a permanent grid
## over the continuous landscape. Older cartography can still use rectangles.

signal region_selected(region_index: int)
## -1 when the cursor is over none of them, or has left the map.
signal region_hovered(region_index: int)

const LABEL_SIZE := 15
const LABEL_OUTLINE := 4
const LABEL_COLOUR := Color(0.96, 0.96, 0.98)
const CURRENT_COLOUR := Color(0.98, 0.78, 0.22)
const HOVER_COLOUR := Color(1.0, 0.92, 0.55)
const CURRENT_WIDTH := 2.0
const HOVER_WIDTH := 3.0
## Legacy rectangular atlases enlarge very small targets for the mouse.
## Geographic atlases use their actual polygons to avoid selecting a neighbor.
const MIN_HIT_SIZE := 44.0

var _image_size := Vector2.ZERO
var _regions: Array[Dictionary] = []
var _current_index := -1
var _hovered_index := -1
var _marker_positions: Array[Vector2] = []

## Region names, bounds and polygons use the picture's own pixels.
func configure(image_size: Vector2, regions: Array[Dictionary]) -> void:
	_image_size = image_size
	_regions = regions
	_marker_positions.clear()
	_hovered_index = -1
	queue_redraw()

func set_marker_positions(points: Array[Vector2]) -> void:
	_marker_positions = points
	queue_redraw()

func region_count() -> int:
	return _regions.size()

func set_current_region(index: int) -> void:
	_current_index = index
	queue_redraw()

func hovered_region() -> int:
	return _hovered_index

## Where the picture lands within this control: the keep-aspect, centred fit
## the TextureRect underneath uses.
func display_rect() -> Rect2:
	if _image_size.x <= 0.0 or _image_size.y <= 0.0 or size.x <= 0.0 or size.y <= 0.0:
		return Rect2()
	var scale_factor: float = minf(size.x / _image_size.x, size.y / _image_size.y)
	var displayed: Vector2 = _image_size * scale_factor
	return Rect2((size - displayed) * 0.5, displayed)

## A region's rectangle in this control's pixels.
func region_rect(index: int) -> Rect2:
	var display: Rect2 = display_rect()
	if index < 0 or index >= _regions.size() or display.size.x <= 0.0:
		return Rect2()
	var rect: Rect2 = _regions[index].get("rect", Rect2()) as Rect2
	var scale_factor: float = display.size.x / _image_size.x
	return Rect2(display.position + rect.position * scale_factor, rect.size * scale_factor)

## The rectangle a click has to land in, never smaller than a mouse can aim at.
func hit_rect(index: int) -> Rect2:
	var rect: Rect2 = region_rect(index)
	if rect.size.x <= 0.0:
		return rect
	var grown := Vector2(maxf(rect.size.x, MIN_HIT_SIZE), maxf(rect.size.y, MIN_HIT_SIZE))
	return Rect2(rect.get_center() - grown * 0.5, grown)

## Keep the original single-ring API for callers using legacy cartography.
func region_polygon(index: int) -> PackedVector2Array:
	var rings := region_polygons(index)
	return rings[0] if not rings.is_empty() else PackedVector2Array()

func region_polygons(index: int) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	var display := display_rect()
	if index < 0 or index >= _regions.size() or display.size.x <= 0.0:
		return result
	var scale_factor: float = display.size.x / _image_size.x
	var source: Array = _regions[index].get("polygons", [_regions[index].get("polygon", [])]) as Array
	for ring: Array in source:
		var points := PackedVector2Array()
		for point: Array in ring:
			points.append(display.position + Vector2(float(point[0]), float(point[1])) * scale_factor)
		if points.size() >= 3:
			result.append(points)
	if result.is_empty():
		var rect := region_rect(index)
		result.append(PackedVector2Array([rect.position, Vector2(rect.end.x, rect.position.y),
			rect.end, Vector2(rect.position.x, rect.end.y)]))
	return result

func region_label_position(index: int) -> Vector2:
	var label: Array = _regions[index].get("label", [])
	if label.size() == 2:
		var display := display_rect()
		return display.position + Vector2(float(label[0]), float(label[1])) * display.size.x / _image_size.x
	return region_rect(index).get_center()

## The region under a point, or -1. A small region's grown target can sit
## inside a large neighbour's rectangle; the smaller one wins, being the one
## that would otherwise be unreachable.
func region_at(local_position: Vector2) -> int:
	var best := -1
	var best_area := INF
	for index: int in range(_regions.size()):
		var rect: Rect2 = hit_rect(index)
		var contains := false
		if _regions[index].has("polygons") or (_regions[index].get("polygon", []) as Array).size() >= 3:
			for polygon: PackedVector2Array in region_polygons(index):
				if Geometry2D.is_point_in_polygon(local_position, polygon):
					contains = true
					break
		else:
			contains = rect.has_point(local_position)
		if rect.size.x > 0.0 and contains and rect.get_area() < best_area:
			best = index
			best_area = rect.get_area()
	return best

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		_set_hovered(region_at((event as InputEventMouseMotion).position))
		return
	if not event is InputEventMouseButton:
		return
	var button: InputEventMouseButton = event as InputEventMouseButton
	if not button.pressed or button.button_index != MOUSE_BUTTON_LEFT:
		return
	var index: int = region_at(button.position)
	if index < 0:
		return
	accept_event()
	region_selected.emit(index)

func _notification(what: int) -> void:
	if what == NOTIFICATION_MOUSE_EXIT or what == NOTIFICATION_VISIBILITY_CHANGED:
		_set_hovered(-1)

func _set_hovered(index: int) -> void:
	if index == _hovered_index:
		return
	_hovered_index = index
	queue_redraw()
	region_hovered.emit(index)

func _draw() -> void:
	if display_rect().size.x <= 0.0:
		return
	for index: int in range(_regions.size()):
		var rect: Rect2 = region_rect(index)
		if rect.size.x <= 0.0:
			continue
		for points: PackedVector2Array in region_polygons(index):
			if index == _hovered_index:
				draw_colored_polygon(points, Color(HOVER_COLOUR, 0.09))
				points.append(points[0])
				draw_polyline(points, HOVER_COLOUR, HOVER_WIDTH, true)
			elif index == _current_index:
				points.append(points[0])
				draw_polyline(points, CURRENT_COLOUR, CURRENT_WIDTH, true)
	var font: Font = get_theme_default_font()
	if font == null:
		return
	var legend := display_rect().position + Vector2(18, 28)
	draw_line(legend, legend + Vector2(30, 0), Color(0.85, 0.76, 0.54), 3.0)
	draw_string(font, legend + Vector2(40, 5), "Road / causeway", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, LABEL_COLOUR)
	legend.y += 23.0
	for part: int in range(4):
		draw_line(legend + Vector2(part * 8, 0), legend + Vector2(part * 8 + 4, 0), Color(0.51, 0.80, 0.87), 2.0)
	draw_string(font, legend + Vector2(40, 5), "Ferry", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, LABEL_COLOUR)
	for index: int in range(_regions.size()):
		var rect: Rect2 = region_rect(index)
		if rect.size.x <= 0.0:
			continue
		if (_regions[index].get("label", []) as Array).size() == 2:
			rect = Rect2(region_label_position(index) - Vector2(rect.size.x * 0.5, 16), Vector2(rect.size.x, 32))
		_draw_label(font, rect, str(_regions[index].get("name", "")),
			CURRENT_COLOUR if index == _current_index else LABEL_COLOUR)

## The name sits along the bottom edge of a region big enough to leave its
## map readable above it, and across the middle of one that is not. It is
## Long names wrap inside their own region so adjacent labels stay distinct.
func _label_lines(font: Font, text: String, width: float) -> PackedStringArray:
	var lines := PackedStringArray()
	var current := ""
	for word: String in text.split(" ", false):
		var candidate: String = word if current.is_empty() else current + " " + word
		if not current.is_empty() and font.get_string_size(candidate, HORIZONTAL_ALIGNMENT_LEFT, -1, LABEL_SIZE).x > width:
			lines.append(current)
			current = word
		else:
			current = candidate
	if not current.is_empty():
		lines.append(current)
	return lines

func _draw_label(font: Font, rect: Rect2, text: String, colour: Color) -> void:
	if text.is_empty():
		return
	var ascent: float = font.get_ascent(LABEL_SIZE)
	var descent: float = font.get_descent(LABEL_SIZE)
	var baseline_y: float
	if rect.size.y > (ascent + descent) * 3.0:
		baseline_y = rect.end.y - descent - 4.0
	else:
		baseline_y = rect.get_center().y + (ascent - descent) * 0.5
	var lines := _label_lines(font, text, maxf(72.0, rect.size.x - 8.0))
	baseline_y -= float(lines.size()-1) * (ascent + descent)
	# Keep region names clear of permanent storage dots at any image size.
	var width := 0.0
	for line: String in lines:
		width = maxf(width, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, LABEL_SIZE).x)
	var text_rect := Rect2(Vector2(rect.get_center().x - width * 0.5, baseline_y - ascent),
		Vector2(width, float(lines.size()) * (ascent + descent)))
	var display := display_rect()
	for point: Vector2 in _marker_positions:
		var pixel := display.position + point * (display.size / _image_size)
		if text_rect.intersects(Rect2(pixel - Vector2(10, 10), Vector2(20, 20))):
			baseline_y -= 24.0
			text_rect.position.y -= 24.0
	for line: String in lines:
		var extent: Vector2 = font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, LABEL_SIZE)
		var baseline := Vector2(rect.get_center().x - extent.x * 0.5, baseline_y)
		draw_string_outline(font, baseline, line, HORIZONTAL_ALIGNMENT_LEFT, -1,
			LABEL_SIZE, LABEL_OUTLINE, Color(0.04, 0.04, 0.05, 0.95))
		draw_string(font, baseline, line, HORIZONTAL_ALIGNMENT_LEFT, -1, LABEL_SIZE, colour)
		baseline_y += ascent + descent
