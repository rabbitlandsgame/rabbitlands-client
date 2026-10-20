extends "res://src/ui/picture_marker_overlay.gd"
## The boat network on a north-up continent picture: each route a dashed sea
## line between its two docks, each dock a ringed dot. Hovering a dock lifts
## its routes and names where its boats sail. The marks are the cartography's
## boatNetwork docks and the routes its routes, both in the picture's metres
## (_continent_v2/publish_cartography.py writes them from boat-network.json).

## The legend's boat-route dashes (continent_map.gd) are these.
const ROUTE_COLOUR := Color(0.51, 0.80, 0.87)
const ROUTE_LIFTED := Color(0.88, 0.98, 1.0)
const ROUTE_SHADOW := Color(0.04, 0.04, 0.05, 0.55)
const ROUTE_WIDTH := 2.0
const DASH := 6.0
const DOCK_RADIUS := 5.0
const DOCK_CENTRE := Color(0.97, 0.99, 1.0)
const OUTLINE_COLOUR := Color(0.04, 0.04, 0.05, 0.9)
## How near the cursor must come to a dock to name it.
const HIT_RADIUS := 12.0
const LABEL_SIZE := 14
const TEXT_COLOUR := Color(0.96, 0.96, 0.98)
const PANEL_COLOUR := Color(0.05, 0.07, 0.09, 0.86)

var _routes: Array = []
var _hovered := -1
var _label_layer: Control

func _ready() -> void:
	super()
	# The hovered dock's name sits above the entrance names (one layer over
	# this one), so it is never hidden under a mine's label.
	_label_layer = Control.new()
	_label_layer.name = "DockLabel"
	_label_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_label_layer.z_index = 2
	add_child(_label_layer)
	_label_layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_label_layer.draw.connect(_draw_hover_label)
	_label_layer.resized.connect(_label_layer.queue_redraw)

func configure(minimum: Vector2, maximum: Vector2, image_size: Vector2, marks: Array) -> void:
	_hovered = -1
	super(minimum, maximum, image_size, marks)
	_redraw_label()

## Each route is {"docks": [a, b], "points": [[x, z], ...]} in the picture's metres.
func set_routes(routes: Array) -> void:
	_routes = routes
	queue_redraw()

func dock_count() -> int:
	return _marks.size()

func route_count() -> int:
	return _routes.size()

## Where a dock is drawn in this control, or null off the picture.
func dock_point(index: int) -> Variant:
	if index < 0 or index >= _marks.size():
		return null
	return mark_point(_marks[index] as Dictionary)

## The dock nearest a point of this control within reach, or -1.
func dock_at(at: Vector2) -> int:
	var best := -1
	var nearest := HIT_RADIUS
	for index: int in range(_marks.size()):
		var point: Variant = dock_point(index)
		if point is Vector2 and at.distance_to(point as Vector2) <= nearest:
			nearest = at.distance_to(point as Vector2)
			best = index
	return best

func hovered_dock() -> int:
	return _hovered

func set_hovered_dock(index: int) -> void:
	if index == _hovered:
		return
	_hovered = index
	queue_redraw()
	_redraw_label()

## "Boats to Boarsend, Greenlight and Stagheath", or "Boat to Hornmere".
static func destinations_text(dock: Dictionary) -> String:
	var names := PackedStringArray()
	for value: Variant in dock.get("boats", []):
		names.append(str((value as Dictionary).get("destination", "")))
	if names.is_empty():
		return ""
	if names.size() == 1:
		return "Boat to " + names[0]
	return "Boats to " + ", ".join(names.slice(0, names.size() - 1)) + " and " + names[names.size() - 1]

## What the sidebar says while the cursor is on a dock, or "" off every dock.
func hover_text() -> String:
	if _hovered < 0 or _hovered >= _marks.size():
		return ""
	var dock: Dictionary = _marks[_hovered] as Dictionary
	var destinations := destinations_text(dock)
	return "%s — %s" % [str(dock.get("label", "")), destinations.left(1).to_lower() + destinations.substr(1)]

## A dock's mark, shared with the continent legend.
static func draw_dock(canvas: CanvasItem, point: Vector2, lifted: bool = false) -> void:
	var radius := DOCK_RADIUS + (1.5 if lifted else 0.0)
	canvas.draw_circle(point, radius + 1.5, OUTLINE_COLOUR)
	canvas.draw_circle(point, radius, ROUTE_LIFTED if lifted else ROUTE_COLOUR)
	canvas.draw_circle(point, radius * 0.45, DOCK_CENTRE)

func _route_points(route: Dictionary) -> PackedVector2Array:
	var points := PackedVector2Array()
	for value: Variant in route.get("points", []):
		var point: Variant = mark_point({"position": value})
		if point is Vector2:
			points.append(point as Vector2)
	return points

func _draw() -> void:
	var lifted_dock := ""
	if _hovered >= 0 and _hovered < _marks.size():
		lifted_dock = str((_marks[_hovered] as Dictionary).get("id", ""))
	# The hovered dock's routes are drawn last, over any they cross.
	for lifted_pass: bool in [false, true]:
		for value: Variant in _routes:
			var route: Dictionary = value as Dictionary
			var lifted: bool = not lifted_dock.is_empty() and (route.get("docks", []) as Array).has(lifted_dock)
			if lifted != lifted_pass:
				continue
			var points := _route_points(route)
			for index: int in range(points.size() - 1):
				draw_dashed_line(points[index], points[index + 1], ROUTE_SHADOW,
					ROUTE_WIDTH + 2.0, DASH, true, true)
				draw_dashed_line(points[index], points[index + 1], ROUTE_LIFTED if lifted else ROUTE_COLOUR,
					ROUTE_WIDTH + (1.0 if lifted else 0.0), DASH, true, true)
	for index: int in range(_marks.size()):
		var point: Variant = dock_point(index)
		if point is Vector2:
			draw_dock(self, point as Vector2, index == _hovered)

func _redraw_label() -> void:
	if is_instance_valid(_label_layer):
		_label_layer.queue_redraw()

func _draw_hover_label() -> void:
	var point: Variant = dock_point(_hovered)
	var font: Font = get_theme_default_font()
	if not point is Vector2 or font == null:
		return
	var dock: Dictionary = _marks[_hovered] as Dictionary
	var lines := PackedStringArray([str(dock.get("label", "")), destinations_text(dock)])
	var width := 0.0
	for line: String in lines:
		width = maxf(width, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, LABEL_SIZE).x)
	var line_height: float = font.get_height(LABEL_SIZE)
	var box := Vector2(width + 16.0, line_height * lines.size() + 10.0)
	var at := (point as Vector2) + Vector2(DOCK_RADIUS + 10.0, -box.y * 0.5)
	if at.x + box.x > size.x - 4.0:
		at.x = (point as Vector2).x - DOCK_RADIUS - 10.0 - box.x
	at = Vector2(clampf(at.x, 4.0, maxf(4.0, size.x - box.x - 4.0)),
		clampf(at.y, 4.0, maxf(4.0, size.y - box.y - 4.0)))
	_label_layer.draw_rect(Rect2(at, box), PANEL_COLOUR)
	_label_layer.draw_rect(Rect2(at, box), ROUTE_COLOUR, false, 1.0)
	var baseline := at + Vector2(8.0, 5.0 + font.get_ascent(LABEL_SIZE))
	for index: int in range(lines.size()):
		_label_layer.draw_string(font, baseline, lines[index], HORIZONTAL_ALIGNMENT_LEFT, -1, LABEL_SIZE,
			TEXT_COLOUR if index == 0 else ROUTE_LIFTED)
		baseline.y += line_height
