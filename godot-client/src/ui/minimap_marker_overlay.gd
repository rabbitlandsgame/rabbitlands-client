extends Control
## Draws the minimap's marks at a fixed size on screen, whatever the zoom.
##
## Every mark on both maps used to be a disc modelled in the world on the
## map-marker visual layer, which both top-down cameras rendered. A disc
## measured in metres is a different number of pixels at every zoom, so zooming
## the minimap out shrank the actor dots to specks and zooming in swelled them
## into saucers that ran into each other - and a player reading a minimap is
## reading the marks, not the ground under them.
##
## So the minimap camera stopped rendering that layer. Everything it marks is
## projected through that camera and drawn here in pixels instead, at the size
## the player asked for and nothing else. The full map also uses this overlay
## for live dots so small interiors and large regions share a marker size.
##
## The overlay owns no marker state. `main.gd` hands it the marks each time the
## minimap render is refreshed, and it projects them through the same camera
## that rendered the image underneath, so a mark cannot drift off the ground it
## is standing on.

## A mark's radius in pixels at marker size "Normal", before the player's
## scale. Small enough that a crowded town is still a map rather than a mass of
## overlapping circles, big enough to pick a colour out of at a glance.
const BASE_RADIUS := 4.0
## The player's own mark, and the server's placed markers, are drawn a size up:
## the first is the one mark a player looks for deliberately, and the second is
## a waypoint the server went out of its way to place.
const SELF_RADIUS := 5.5
const PIN_RADIUS := 5.5
## The dark ring every mark carries. The ground under the marks is parkland,
## water and roof, so a mark that shares a tone with what it stands on is a
## texture rather than a mark. Modelled discs solve this the same way; see
## `map_marker_disc.gd`.
const OUTLINE_WIDTH := 1.5
const OUTLINE_COLOUR := Color(0.04, 0.04, 0.05, 0.9)
## Circles are drawn as polygons rather than with `draw_circle`, so the outline
## and the fill are the same shape at these radii.
const CIRCLE_SEGMENTS := 16
## That polygon round the unit circle, worked out once rather than with a sine
## and a cosine per point of every dot of every redraw, and the triangle fan
## that fills one circle, repeated for as many as a redraw has needed.
static var _unit_circle: PackedVector2Array = _make_unit_circle()
static var _fan := PackedInt32Array()
## A glyph mark - a portal's P, an exit's X - is drawn this many times the
## dot radius tall, and no smaller than a letter can be read at.
const GLYPH_SCALE := 2.8
const GLYPH_MINIMUM_SIZE := 9
const EntranceOverlayScript := preload("res://src/ui/entrance_map_overlay.gd")

var _camera: Camera3D
var _viewport_size := Vector2i.ZERO
var _marks: Array[Dictionary] = []
var _enabled_types: Dictionary = {}
var _marker_scale := 1.0
var _round := false
## The region boundaries in metres of the current map (see map_marker_overlay).
var _boundaries: Array[Dictionary] = []
const BOUNDARY_COLOUR := Color(1.0, 1.0, 1.0, 0.7)
## Dots in a row are gathered into one draw: each dot's ring and then its fill,
## in mark order, so a dot's ring still lies over the dot beneath it exactly as
## when every circle was its own draw. A map with a crowd on it - or, with
## player interest, the dots of everyone beyond it - drew hundreds of
## polygons a redraw; this is one call (`_flush_dots`).
var _dot_points := PackedVector2Array()
var _dot_colours := PackedColorArray()
var _dot_circles := 0
## A circle's worth of one colour, per colour.
var _circle_colours: Dictionary = {}

func configure(camera: Camera3D, viewport_size: Vector2i) -> void:
	_camera = camera
	_viewport_size = viewport_size
	queue_redraw()

## The marks on the minimap right now, as `main.gd` collected them: each one a
## world position, the marker type it can be switched off by, and the colour
## the node that owns it draws itself in.
func set_boundaries(boundaries: Array[Dictionary]) -> void:
	_boundaries = boundaries
	queue_redraw()

## Whether a texture point lies within the round mask, when the map is round.
func _within_mask(point: Vector2) -> bool:
	if not _round:
		return true
	var centre: Vector2 = size * 0.5
	return point.distance_to(centre) <= minf(size.x, size.y) * 0.5 - 1.0

## The seams between regions as dashed lines, kept inside the round mask.
func _draw_boundaries() -> void:
	for boundary: Dictionary in _boundaries:
		var points: PackedVector3Array = boundary.get("points", PackedVector3Array()) as PackedVector3Array
		var previous: Variant = null
		for index: int in range(points.size() + 1):
			var world: Vector3 = points[index % points.size()]
			var point: Variant = null if _camera.is_position_behind(world) else _texture_position(_camera.unproject_position(world))
			if point is Vector2 and not _within_mask(point as Vector2):
				point = null
			if previous is Vector2 and point is Vector2:
				draw_dashed_line(previous as Vector2, point as Vector2, BOUNDARY_COLOUR, 1.2, 5.0)
			previous = point

func set_marks(marks: Array[Dictionary]) -> void:
	_marks = marks
	queue_redraw()

## Which marker types the player left switched on. A type missing from the
## dictionary is drawn, so a type added later shows up until it is switched off
## rather than being invisible until the settings file learns about it.
func set_enabled_types(enabled: Dictionary) -> void:
	_enabled_types = enabled
	queue_redraw()

func set_marker_scale(marker_scale: float) -> void:
	_marker_scale = maxf(0.1, marker_scale)
	queue_redraw()

## A round minimap is masked to the circle inscribed in its frame, so a mark
## outside that circle would be drawn on the black border rather than on the
## map. This is the overlay's half of that mask.
func set_round(is_round: bool) -> void:
	_round = is_round
	queue_redraw()

func type_enabled(type: StringName) -> bool:
	return bool(_enabled_types.get(type, true))

## The radius a mark is drawn at, in pixels on screen. The camera is not one of
## the terms, which is the whole point of drawing the marks here: this is the
## same number at every zoom.
func mark_radius(mark: Dictionary) -> float:
	return float(mark.get("radius", BASE_RADIUS)) * _marker_scale

## Where a mark lands on this control, or null when it falls outside the drawn
## image - off the edge, or off the circle a round minimap is masked to. Public
## alongside `mark_radius` so that what a mark is drawn over and how big it is
## drawn can both be read rather than only seen.
func mark_point(mark: Dictionary) -> Variant:
	if not is_instance_valid(_camera):
		return null
	var world: Vector3 = mark.get("position", Vector3.ZERO) as Vector3
	if _camera.is_position_behind(world):
		return null
	return _texture_position(_camera.unproject_position(world))

## The marks in the order they are drawn, later ones on top. The player's own
## mark goes last whatever order it was handed over in: it is the one mark a
## player looks for, and in a crowd of NPCs or a field of harvest nodes the
## dots standing next to it would otherwise cover it.
func draw_order(marks: Array[Dictionary]) -> Array[Dictionary]:
	var others: Array[Dictionary] = []
	var own: Array[Dictionary] = []
	for mark: Dictionary in marks:
		if mark.get("type", &"") == &"self":
			own.append(mark)
		else:
			others.append(mark)
	return others + own

func _draw() -> void:
	if not is_instance_valid(_camera):
		return
	_draw_boundaries()
	if _marks.is_empty():
		return
	for mark: Dictionary in draw_order(_marks):
		var type: StringName = mark.get("type", &"") as StringName
		if not type_enabled(type):
			continue
		var point_value: Variant = mark_point(mark)
		if not point_value is Vector2:
			continue
		var point: Vector2 = point_value as Vector2
		var colour: Color = mark.get("colour", Color.WHITE) as Color
		var radius: float = mark_radius(mark)
		var glyph: String = str(mark.get("glyph", ""))
		if type == &"entrance":
			_flush_dots()
			EntranceOverlayScript.draw_marker(self, point, str(mark.get("label", "Entrance")), 11, radius)
		elif not glyph.is_empty():
			_flush_dots()
			_draw_glyph(point, radius, colour, glyph)
		elif type == &"marker":
			_flush_dots()
			_draw_pin(point, radius, colour)
		else:
			_queue_dot(point, radius, colour)
	_flush_dots()

## A letter rather than a shape, the way the legend writes it, outlined in
## the same dark ring the dots carry so it reads on parkland and on roof.
func _draw_glyph(point: Vector2, radius: float, colour: Color, glyph: String) -> void:
	var font: Font = get_theme_default_font()
	if font == null:
		return
	var size: int = maxi(GLYPH_MINIMUM_SIZE, roundi(radius * GLYPH_SCALE))
	var extent: Vector2 = font.get_string_size(glyph, HORIZONTAL_ALIGNMENT_LEFT, -1, size)
	var baseline := Vector2(point.x - extent.x * 0.5,
		point.y + (font.get_ascent(size) - font.get_descent(size)) * 0.5)
	draw_string_outline(font, baseline, glyph, HORIZONTAL_ALIGNMENT_LEFT, -1, size,
		maxi(2, roundi(OUTLINE_WIDTH * 2.0)), OUTLINE_COLOUR)
	draw_string(font, baseline, glyph, HORIZONTAL_ALIGNMENT_LEFT, -1, size, colour)

func _queue_dot(point: Vector2, radius: float, colour: Color) -> void:
	_dot_points.append_array(_circle(point, radius + OUTLINE_WIDTH))
	_dot_colours.append_array(_colours_of(OUTLINE_COLOUR))
	_dot_points.append_array(_circle(point, radius))
	_dot_colours.append_array(_colours_of(colour))
	_dot_circles += 2

## Draws the dots gathered since the last flush, in one call.
func _flush_dots() -> void:
	if _dot_circles == 0:
		return
	var triangles: int = CIRCLE_SEGMENTS - 2
	var needed: int = _dot_circles * triangles * 3
	if _fan.size() < needed:
		var circles: int = _dot_circles * 2
		_fan.resize(circles * triangles * 3)
		var at := 0
		for circle: int in range(circles):
			var first: int = circle * CIRCLE_SEGMENTS
			for step: int in range(triangles):
				_fan[at] = first
				_fan[at + 1] = first + step + 1
				_fan[at + 2] = first + step + 2
				at += 3
	RenderingServer.canvas_item_add_triangle_array(get_canvas_item(),
		_fan.slice(0, needed), _dot_points, _dot_colours)
	_dot_points.clear()
	_dot_colours.clear()
	_dot_circles = 0

func _colours_of(colour: Color) -> PackedColorArray:
	var colours: Variant = _circle_colours.get(colour)
	if colours == null:
		var filled := PackedColorArray()
		filled.resize(CIRCLE_SEGMENTS)
		filled.fill(colour)
		_circle_colours[colour] = filled
		colours = filled
	return colours as PackedColorArray

## The server's own markers are diamonds on the full map, and they stay
## diamonds here: a waypoint the server placed is not the same kind of thing as
## somebody standing on a tile, and shape says so without a second colour.
func _draw_pin(point: Vector2, radius: float, colour: Color) -> void:
	draw_colored_polygon(_diamond(point, radius + OUTLINE_WIDTH), OUTLINE_COLOUR)
	draw_colored_polygon(_diamond(point, radius), colour)

func _circle(point: Vector2, radius: float) -> PackedVector2Array:
	return Transform2D(0.0, Vector2(radius, radius), 0.0, point) * _unit_circle

static func _make_unit_circle() -> PackedVector2Array:
	var points := PackedVector2Array()
	for step: int in range(CIRCLE_SEGMENTS):
		var angle: float = TAU * float(step) / float(CIRCLE_SEGMENTS)
		points.append(Vector2(cos(angle), sin(angle)))
	return points

func _diamond(point: Vector2, radius: float) -> PackedVector2Array:
	return PackedVector2Array([
		point + Vector2(0.0, -radius), point + Vector2(radius, 0.0),
		point + Vector2(0.0, radius), point + Vector2(-radius, 0.0)])

## Viewport pixels to a position on this control, matching the minimap image's
## keep-aspect-centred stretch. Returns null for a point off the drawn image,
## and - on a round minimap - for one off the circle the image is masked to.
func _texture_position(viewport_position: Vector2) -> Variant:
	var target := Vector2(_viewport_size)
	if size.x <= 0.0 or size.y <= 0.0 or target.x <= 0.0 or target.y <= 0.0:
		return null
	var image_scale: float = minf(size.x / target.x, size.y / target.y)
	var displayed_size: Vector2 = target * image_scale
	var displayed_origin: Vector2 = (size - displayed_size) * 0.5
	var point: Vector2 = displayed_origin + viewport_position * image_scale
	if not Rect2(displayed_origin, displayed_size).has_point(point):
		return null
	if _round:
		var centre: Vector2 = displayed_origin + displayed_size * 0.5
		var radius: float = minf(displayed_size.x, displayed_size.y) * 0.5
		if point.distance_to(centre) > radius:
			return null
	return point
