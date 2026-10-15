class_name InvasionMapCanvas
extends Control

signal coordinate_selected(tile: Vector2i)

const PAD := 16.0
const GRID_COLOR := Color("324454")
const LOCATION_COLOR := Color("c8a8ff")
const PORTAL_COLOR := Color("55cfee")
const PLAYER_COLOR := Color("68e7ff")
const INVASION_COLOR := Color("ff6b63")
const BOSS_COLOR := Color("ffc94f")
const MARKER_FONT_SIZE := 10
const MAX_LOCATION_LABELS := 6
const CLUSTER_PIXELS := 28.0

var state: Dictionary = {}
var selected_tile: Variant = null
var coordinates_supported := true
var background: Texture2D
var _hover_text := ""
var _adapter: CoordinateAdapter
var _world_rect := Rect2()


func _ready() -> void:
	custom_minimum_size = Vector2(238, 188)
	mouse_default_cursor_shape = Control.CURSOR_CROSS
	# A marker near the right edge draws its name past the canvas, where the
	# roster is; unclipped, the two read as one smeared column.
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_process(false)


func set_map_state(value: Dictionary, texture: Texture2D = null,
		projection: Dictionary = {}) -> void:
	var previous_map := str((state.get("map", {}) as Dictionary).get("id", ""))
	var next_map := str((value.get("map", {}) as Dictionary).get("id", ""))
	state = value.duplicate(true)
	coordinates_supported = bool(value.get("coordinatesSupported", true))
	background = texture
	_adapter = null
	_world_rect = Rect2()
	var minimap: Dictionary = projection.get("minimap", {})
	var low: Array = minimap.get("worldMin", [])
	var high: Array = minimap.get("worldMax", [])
	if texture != null and low.size() == 2 and high.size() == 2:
		_world_rect = Rect2(Vector2(float(low[0]), float(low[1])),
			Vector2(float(high[0]) - float(low[0]), float(high[1]) - float(low[1])))
		if _world_rect.size.x > 0.0 and _world_rect.size.y > 0.0:
			_adapter = CoordinateAdapter.new(projection.get("coordinateTransform", {}))
	if previous_map != next_map or not coordinates_supported:
		selected_tile = null
	_hover_text = ""
	tooltip_text = "Click the tactical map to select teleport coordinates."
	queue_redraw()


func _map_rect() -> Rect2:
	return Rect2(Vector2(PAD, PAD), Vector2(
		maxf(1.0, size.x - PAD * 2.0), maxf(1.0, size.y - PAD * 2.0)))


func _bounds() -> Vector2:
	var map: Dictionary = state.get("map", {}) as Dictionary
	return Vector2(maxf(1.0, float(map.get("width", 2048))),
		maxf(1.0, float(map.get("height", 2048))))

func _minimum() -> Vector2:
	var minimum: Array = state.get("map", {}).get("serverTileMin", [0, 0])
	return Vector2(float(minimum[0]), float(minimum[1]))


func _point(tile: Vector2) -> Vector2:
	var rect := _map_rect()
	var bounds := _bounds()
	# Server Y increases north; image Y increases south. Use the image's
	# authored world bounds, which can include scenery outside the server grid.
	var relative := (tile - _minimum() + Vector2(0.5, 0.5)) / bounds
	relative.y = 1.0 - relative.y
	if _adapter != null:
		var world := _adapter.server_to_godot(tile.x + 0.5, tile.y + 0.5)
		relative = (Vector2(world.x, world.z) - _world_rect.position) / _world_rect.size
	return rect.position + relative * rect.size


func _tile(point: Vector2) -> Vector2i:
	var rect := _map_rect()
	var bounds := _bounds()
	var relative := (point - rect.position) / rect.size
	var minimum := Vector2i(_minimum())
	var tile := minimum + Vector2i(floori(relative.x * bounds.x),
		floori((1.0 - relative.y) * bounds.y))
	if _adapter != null:
		var world := _world_rect.position + relative * _world_rect.size
		tile = _adapter.godot_to_server(Vector3(world.x, 0.0, world.y))
	return Vector2i(clampi(tile.x, minimum.x, minimum.x + int(bounds.x) - 1),
		clampi(tile.y, minimum.y, minimum.y + int(bounds.y) - 1))


## Keep a handful of readable names; every location still has a hover label
## and remains available in the teleport picker. Portals and landmarks come
## before the many individual invasion spawn points.
func _location_labels(font: Font) -> Array[Dictionary]:
	var labels: Array[Dictionary] = []
	var occupied: Array[Rect2] = []
	var rect := _map_rect()
	for kind: String in ["portal", "landmark", "invasion_spawn"]:
		for location: Dictionary in state.get("locations", []):
			if str(location.get("kind", "landmark")) != kind:
				continue
			var point := _point(Vector2(float(location.get("x", 0)), float(location.get("y", 0))))
			if not rect.has_point(point):
				continue
			var label := str(location.get("name", "Location"))
			var extent := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, MARKER_FONT_SIZE)
			var baseline := point + Vector2(6, -4)
			if baseline.x + extent.x > rect.end.x:
				baseline.x = point.x - extent.x - 6
			var area := Rect2(baseline - Vector2(0, font.get_ascent(MARKER_FONT_SIZE)), extent)
			if not rect.encloses(area):
				continue
			var overlaps := false
			for previous: Rect2 in occupied:
				if previous.grow(8).intersects(area):
					overlaps = true
					break
			if overlaps:
				continue
			labels.append({"text": label, "position": baseline, "rect": area})
			occupied.append(area)
			if labels.size() == MAX_LOCATION_LABELS:
				return labels
	return labels


func _draw() -> void:
	var rect := _map_rect()
	draw_rect(Rect2(Vector2.ZERO, size), Color("101820"), true)
	if background != null:
		draw_texture_rect(background, rect, false, Color(1, 1, 1, 0.68))
	else:
		draw_rect(rect, Color("182734"), true)
	for step: int in range(1, 8):
		var fraction := float(step) / 8.0
		draw_line(Vector2(rect.position.x + rect.size.x * fraction, rect.position.y),
			Vector2(rect.position.x + rect.size.x * fraction, rect.end.y), GRID_COLOR, 1.0)
		draw_line(Vector2(rect.position.x, rect.position.y + rect.size.y * fraction),
			Vector2(rect.end.x, rect.position.y + rect.size.y * fraction), GRID_COLOR, 1.0)
	draw_rect(rect, Color("7392a6"), false, 2.0)

	var font: Font = ThemeDB.fallback_font
	_draw_creatures(font)
	for raw_location: Variant in state.get("locations", []):
		var location := raw_location as Dictionary
		var point := _point(Vector2(float(location.get("x", 0)), float(location.get("y", 0))))
		var color := PORTAL_COLOR if str(location.get("kind", "")) == "portal" else LOCATION_COLOR
		draw_rect(Rect2(point - Vector2(3, 3), Vector2(6, 6)), color, true)
	for label: Dictionary in _location_labels(font):
		draw_string(font, label.position, label.text,
			HORIZONTAL_ALIGNMENT_LEFT, -1.0, MARKER_FONT_SIZE, Color.WHITE)
	for raw_player: Variant in state.get("players", []):
		var player := raw_player as Dictionary
		var point := _point(Vector2(float(player.get("x", 0)), float(player.get("y", 0))))
		draw_circle(point, 4.5, PLAYER_COLOR)
		draw_circle(point, 1.5, Color.WHITE)
		draw_string(font, point + Vector2(6, 3), str(player.get("name", "Player")),
			HORIZONTAL_ALIGNMENT_LEFT, -1.0, MARKER_FONT_SIZE, PLAYER_COLOR)
	if selected_tile is Vector2i:
		var selected_point := _point(Vector2(selected_tile))
		draw_circle(selected_point, 7.0, Color("f4ef7a"), false, 2.0)
		draw_line(selected_point - Vector2(10, 0), selected_point + Vector2(10, 0),
			Color("f4ef7a"), 1.0)
		draw_line(selected_point - Vector2(0, 10), selected_point + Vector2(0, 10),
			Color("f4ef7a"), 1.0)

func _creature_clusters() -> Array[Dictionary]:
	var cells: Dictionary = {}
	for creature: Dictionary in state.get("creatures", []):
		if bool(creature.get("boss", false)):
			continue
		var point := _point(Vector2(float(creature.get("x", 0)), float(creature.get("y", 0))))
		if not _map_rect().has_point(point):
			continue
		var cell := Vector2i(floori(point.x / CLUSTER_PIXELS), floori(point.y / CLUSTER_PIXELS))
		if not cells.has(cell):
			cells[cell] = {"position": Vector2.ZERO, "count": 0, "names": {}}
		var cluster: Dictionary = cells[cell]
		cluster.position += point
		cluster.count += 1
		var creature_name := str(creature.get("name", "Creature"))
		cluster.names[creature_name] = int(cluster.names.get(creature_name, 0)) + 1
	var clusters: Array[Dictionary] = []
	for cluster: Dictionary in cells.values():
		cluster.position /= cluster.count
		clusters.append(cluster)
	return clusters

func _draw_creatures(font: Font) -> void:
	for cluster: Dictionary in _creature_clusters():
		if cluster.count > 1:
			draw_circle(cluster.position, 12.0, Color("182734"))
			draw_circle(cluster.position, 12.0, INVASION_COLOR, false, 1.5)
			var text := str(cluster.count)
			var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
			draw_string(font, cluster.position + Vector2(-width * 0.5, 3), text,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color.WHITE)
		else:
			draw_circle(cluster.position, 4.0, INVASION_COLOR)
	for creature: Dictionary in state.get("creatures", []):
		if not bool(creature.get("boss", false)):
			continue
		var point := _point(Vector2(float(creature.get("x", 0)), float(creature.get("y", 0))))
		draw_colored_polygon(PackedVector2Array([point + Vector2(0, -5), point + Vector2(5, 0),
			point + Vector2(0, 5), point + Vector2(-5, 0)]), BOSS_COLOR)


func _gui_input(event: InputEvent) -> void:
	if not coordinates_supported:
		return
	if event is InputEventMouseButton:
		var button := event as InputEventMouseButton
		if button.button_index == MOUSE_BUTTON_LEFT and button.pressed \
				and _map_rect().has_point(button.position):
			selected_tile = _tile(button.position)
			coordinate_selected.emit(selected_tile)
			queue_redraw()
			accept_event()
	elif event is InputEventMouseMotion:
		_update_hover((event as InputEventMouseMotion).position)


func _update_hover(position: Vector2) -> void:
	if not _map_rect().has_point(position):
		tooltip_text = "Click the tactical map to select teleport coordinates."
		return
	var nearest_text := ""
	var nearest_distance := 10.0
	for cluster: Dictionary in _creature_clusters():
		var distance: float = cluster.position.distance_to(position)
		if distance < nearest_distance:
			nearest_distance = distance
			var entries: Array[String] = []
			for creature_name: String in cluster.names:
				entries.append("%s ×%d" % [creature_name, cluster.names[creature_name]])
			nearest_text = "%d creatures\n%s" % [cluster.count, "\n".join(entries)]
	for key: String in ["creatures", "locations", "players"]:
		for raw_marker: Variant in state.get(key, []):
			var marker := raw_marker as Dictionary
			if key == "creatures" and not bool(marker.get("boss", false)):
				continue
			var marker_point := _point(Vector2(float(marker.get("x", 0)),
				float(marker.get("y", 0))))
			var distance := marker_point.distance_to(position)
			if distance <= nearest_distance:
				nearest_distance = distance
				nearest_text = "%s — %d, %d" % [str(marker.get("name", key)),
					int(marker.get("x", 0)), int(marker.get("y", 0))]
	var tile := _tile(position)
	tooltip_text = nearest_text if not nearest_text.is_empty() else "%d, %d" % [tile.x, tile.y]
