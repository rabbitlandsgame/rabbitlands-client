extends Control
## Draws the server's map markers over the full map.
##
## Terrain is rendered by a top-down camera. Glyphs, pins and live dots are
## drawn in screen pixels, so framing a small room cannot turn them into
## oversized discs. Names are available on hover without covering the map.
##
## It holds no marker state. `main.gd` hands it the markers the server placed on
## the map the player is standing on, and it projects them through the same
## camera the map image is rendered with, so a marker cannot drift away from the
## map underneath it.

const MARKER_COLOUR := Color(0.98, 0.78, 0.22)
const MARKER_RADIUS := 10.0

## How large a portal's P or an exit's X is drawn, in pixels: a glyph is read
## rather than found, so it is bigger than a pin and its outline is heavy.
const GLYPH_SIZE := 18
const GLYPH_OUTLINE := 4
const LiveOverlayScript := preload("res://src/ui/minimap_marker_overlay.gd")
const EntranceOverlayScript := preload("res://src/ui/entrance_map_overlay.gd")
const TextColors := preload("res://src/ui/text_colors.gd")

var _camera: Camera3D
var _adapter: CoordinateAdapter
var _viewport_size := Vector2i.ZERO
var _markers: Array[Dictionary] = []
## Waygates, map exits and storage, each a world `position`, a `glyph`,
## a `colour` and a hover `label`. Storage has no glyph; its live dot is drawn
## by the shared overlay. `main.gd` hands these over
## whenever the map's objects change.
var _waypoints: Array[Dictionary] = []
## The player's own marks. Drawn in a different colour from the server's, so
## nobody mistakes their own annotation for something the world told them.
var _player_marks: Array[Dictionary] = []
## The region boundaries in metres of the current map: `name`, `points`
## (PackedVector3Array), `label` (Vector3, INF for none) and `current`.
var _boundaries: Array[Dictionary] = []
var _live_overlay: Control
var _walk_target: Variant = null
const BOUNDARY_COLOUR := Color(1.0, 1.0, 1.0, 0.8)
const BOUNDARY_LABEL_COLOUR := Color(1.0, 0.95, 0.8, 0.95)

func _ready() -> void:
	TextColors.events().changed.connect(_on_text_colors_changed)
	_live_overlay = LiveOverlayScript.new()
	_live_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_live_overlay.show_behind_parent = true
	add_child(_live_overlay)
	_live_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func _on_text_colors_changed(_role: String) -> void:
	queue_redraw()

## Actors and resources keep the same pixel size on a small interior and a
## large exterior. Portals and pins are drawn by this overlay instead.
func set_live_marks(marks: Array[Dictionary]) -> void:
	var dots: Array[Dictionary] = []
	for mark: Dictionary in marks:
		if str(mark.get("glyph", "")).is_empty() and mark.get("type") not in [&"marker", &"entrance"]:
			dots.append(mark)
	_live_overlay.set_marks(dots)

func configure(camera: Camera3D, adapter: CoordinateAdapter,
		viewport_size: Vector2i) -> void:
	_camera = camera
	_adapter = adapter
	_viewport_size = viewport_size
	if _live_overlay != null:
		_live_overlay.configure(camera, viewport_size)
	queue_redraw()

## The markers on the current map, already filtered by `main.gd`.
func set_markers(markers: Array[Dictionary]) -> void:
	_markers = markers
	queue_redraw()

func set_player_marks(marks: Array[Dictionary]) -> void:
	_player_marks = marks
	queue_redraw()

func set_boundaries(boundaries: Array[Dictionary]) -> void:
	_boundaries = boundaries
	queue_redraw()

func set_waypoints(waypoints: Array[Dictionary]) -> void:
	_waypoints = waypoints
	queue_redraw()

func set_walk_target(position: Variant) -> void:
	_walk_target = position
	queue_redraw()

func walk_target_point() -> Variant:
	if not _walk_target is Vector3 or not is_instance_valid(_camera) \
			or _camera.is_position_behind(_walk_target):
		return null
	return _texture_position(_camera.unproject_position(_walk_target))

func waypoint_count() -> int:
	return _waypoints.size()

const PLAYER_MARK_COLOUR := Color(0.50, 0.83, 1.0)

## Called by the map image, which owns mouse input and click-to-walk.
func label_at(position: Vector2) -> String:
	return str(_label_record_at(position).get("label", ""))

func label_color_at(position: Vector2) -> Color:
	var mark := _label_record_at(position)
	match str(mark.get("text_role", "")):
		"map_personal": return personal_text_color(mark)
		"map_server": return TextColors.color("map_server")
	return TextColors.color("map_service")

## EL retains each saved personal mark's RGB. A global color choice is an
## explicit override; resetting it restores every individual saved color.
static func personal_text_color(mark: Dictionary) -> Color:
	if TextColors.is_overridden("map_personal"):
		return TextColors.color("map_personal")
	var saved: Variant = mark.get("colour", mark.get("color"))
	if saved is Color:
		return saved
	if saved is String and Color.html_is_valid(saved):
		return Color.html(saved)
	if saved is Array and saved.size() >= 3:
		var scale := 255.0 if float(saved[0]) > 1.0 or float(saved[1]) > 1.0 or float(saved[2]) > 1.0 else 1.0
		return Color(float(saved[0]) / scale, float(saved[1]) / scale, float(saved[2]) / scale)
	if mark.has("r") and mark.has("g") and mark.has("b"):
		var scale := 255.0 if float(mark.r) > 1.0 or float(mark.g) > 1.0 or float(mark.b) > 1.0 else 1.0
		return Color(float(mark.r) / scale, float(mark.g) / scale, float(mark.b) / scale)
	return TextColors.color("map_personal")

func _label_record_at(position: Vector2) -> Dictionary:
	if not is_instance_valid(_camera) or _adapter == null:
		return {}
	var nearest := 18.0
	var selected: Dictionary = {}
	var marks: Array[Dictionary] = _waypoints.duplicate()
	for marker: Dictionary in _markers:
		var mark := marker.duplicate()
		mark["position"] = _marker_position(marker)
		mark["text_role"] = "map_server"
		marks.append(mark)
	for marker: Dictionary in _player_marks:
		var mark := marker.duplicate()
		mark["position"] = _marker_position(marker)
		mark["text_role"] = "map_personal"
		marks.append(mark)
	for mark: Dictionary in marks:
		var world: Vector3 = mark.get("position", Vector3.ZERO)
		if _camera.is_position_behind(world):
			continue
		var point: Variant = _texture_position(_camera.unproject_position(world))
		if point is Vector2 and position.distance_to(point) < nearest:
			nearest = position.distance_to(point)
			selected = mark
	return selected

func _draw() -> void:
	if not is_instance_valid(_camera) or _adapter == null:
		return
	if _markers.is_empty() and _player_marks.is_empty() and _waypoints.is_empty() and _boundaries.is_empty() and _walk_target == null:
		return
	var font: Font = get_theme_default_font()
	_draw_boundaries(font)
	_draw_waypoints(font)
	_draw_set(_markers, MARKER_COLOUR)
	_draw_set(_player_marks, PLAYER_MARK_COLOUR)
	var target: Variant = walk_target_point()
	if target is Vector2:
		LiveOverlayScript.draw_walk_target(self, target as Vector2)

## The P of a waygate and the X of a way off the map. Destination names stay
## available on hover. Drawn under the server's own markers, so a pin
## placed on a doorway is still the pin.
func _draw_waypoints(font: Font) -> void:
	if font == null:
		return
	for waypoint: Dictionary in _waypoints:
		var world: Vector3 = waypoint.get("position", Vector3.ZERO) as Vector3
		if _camera.is_position_behind(world):
			continue
		var point_value: Variant = _texture_position(_camera.unproject_position(world))
		if not point_value is Vector2:
			continue
		var point: Vector2 = point_value as Vector2
		if waypoint.get("type") == &"entrance":
			# A building's door is its shop's dot, named on hover only; a cave
			# keeps its permanent name.
			if EntranceOverlayScript.is_building(waypoint):
				EntranceOverlayScript.draw_dot(self, point,
					waypoint.get("colour", EntranceOverlayScript.DOT_COLOUR) as Color,
					LiveOverlayScript.BASE_RADIUS)
			else:
				EntranceOverlayScript.draw_marker(self, point, str(waypoint.get("label", "Entrance")))
			continue
		var glyph: String = str(waypoint.get("glyph", "X"))
		if glyph.is_empty():
			continue
		var colour: Color = waypoint.get("colour", Color.WHITE) as Color
		var extent: Vector2 = font.get_string_size(glyph, HORIZONTAL_ALIGNMENT_LEFT, -1,
			GLYPH_SIZE)
		var baseline := Vector2(point.x - extent.x * 0.5,
			point.y + (font.get_ascent(GLYPH_SIZE) - font.get_descent(GLYPH_SIZE)) * 0.5)
		draw_string_outline(font, baseline, glyph, HORIZONTAL_ALIGNMENT_LEFT, -1,
			GLYPH_SIZE, GLYPH_OUTLINE, Color(0.04, 0.04, 0.05, 0.95))
		draw_string(font, baseline, glyph, HORIZONTAL_ALIGNMENT_LEFT, -1, GLYPH_SIZE, colour)

func _draw_set(marks: Array[Dictionary], colour: Color) -> void:
	for marker: Dictionary in marks:
		var world: Vector3 = _marker_position(marker)
		if _camera.is_position_behind(world):
			continue
		var point_value: Variant = _texture_position(
			_camera.unproject_position(world))
		if not point_value is Vector2:
			continue
		var point: Vector2 = point_value as Vector2
		draw_colored_polygon(PackedVector2Array([
			point + Vector2(0.0, -MARKER_RADIUS),
			point + Vector2(MARKER_RADIUS, 0.0),
			point + Vector2(0.0, MARKER_RADIUS),
			point + Vector2(-MARKER_RADIUS, 0.0)]), colour)

func _marker_position(marker: Dictionary) -> Vector3:
	return marker.get("position", _adapter.tile_center(
		int(marker.get("x", 0)), int(marker.get("y", 0))))

## Viewport pixels to a position on this control, matching the map image's
## keep-aspect-centred stretch. Returns null for a point off the drawn image.
## The seams between regions as dashed lines, and each neighbour's name at
## its cartography label where that lies in view. The current region's own
## outline is drawn too: it is the same line seen from the other side.
func _draw_boundaries(font: Font) -> void:
	for boundary: Dictionary in _boundaries:
		var points: PackedVector3Array = boundary.get("points", PackedVector3Array()) as PackedVector3Array
		var previous: Variant = null
		for index: int in range(points.size() + 1):
			var world: Vector3 = points[index % points.size()]
			var point: Variant = null if _camera.is_position_behind(world) else _texture_position(_camera.unproject_position(world))
			if previous is Vector2 and point is Vector2:
				draw_dashed_line(previous as Vector2, point as Vector2, BOUNDARY_COLOUR, 1.5, 6.0)
			previous = point
		if bool(boundary.get("current", false)):
			continue
		var label: Vector3 = boundary.get("label", Vector3.INF) as Vector3
		if not label.is_finite():
			continue
		var label_point: Variant = _texture_position(_camera.unproject_position(label))
		if not label_point is Vector2:
			continue
		var text: String = str(boundary.get("name", ""))
		var width: float = font.get_string_size(text, HORIZONTAL_ALIGNMENT_CENTER, -1, 15).x
		var at: Vector2 = (label_point as Vector2) - Vector2(width * 0.5, -5.0)
		draw_string(font, at + Vector2(1, 1), text, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0, 0, 0, 0.8))
		draw_string(font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, TextColors.color("map_region", BOUNDARY_LABEL_COLOUR))

func _texture_position(viewport_position: Vector2) -> Variant:
	var target := Vector2(_viewport_size)
	if size.x <= 0.0 or size.y <= 0.0 or target.x <= 0.0 or target.y <= 0.0:
		return null
	var scale: float = minf(size.x / target.x, size.y / target.y)
	var displayed_size: Vector2 = target * scale
	var displayed_origin: Vector2 = (size - displayed_size) * 0.5
	var point: Vector2 = displayed_origin + viewport_position * scale
	if not Rect2(displayed_origin, displayed_size).has_point(point):
		return null
	return point
