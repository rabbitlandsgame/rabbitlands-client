extends Control
## A configurable orb and eight independent curved live resource meters.
const Values := preload("res://src/ui/hud_resource_values.gd")
const Presets := preload("res://src/ui/hud_presets.gd")
const Chrome := preload("res://src/ui/hud_panel_chrome.gd")
static var _textures: Dictionary = {}
var config: Dictionary = Presets.preset("adventure").parts.medallion
var _signature: Array = []
var _refresh := 0.0
var connections: Array = []
var connection_panels: Array[Rect2] = []
var dock_clearance := {"left":0.0, "right":0.0, "top":0.0, "bottom":0.0}

func _ready() -> void:
	custom_minimum_size = Vector2(180, 150)
	size = Vector2(240, 200)
	mouse_filter = Control.MOUSE_FILTER_PASS
	z_index = 20
	resized.connect(queue_redraw)

func configure(value: Dictionary) -> void:
	config = value.duplicate(true)
	var design: String = config.border_design
	if design != "plain" and not _textures.has(design):
		var path := "res://assets/ui/hud-borders/%s.png" % design
		if ResourceLoader.exists(path):
			_textures[design] = load(path)
		else:
			# Test newly generated PNGs before the editor has imported them.
			var source := Image.load_from_file(ProjectSettings.globalize_path(path))
			if source != null: _textures[design] = ImageTexture.create_from_image(source)
	_signature.clear()
	queue_redraw()

func _process(delta: float) -> void:
	_refresh += delta
	if _refresh < 0.1: return
	_refresh = 0
	var state: Array = [Values.read(config.center_resource)]
	var lines: Array[String] = ["Center · " + state[0].label + ": " + Values.value_text(state[0])]
	for index: int in 8:
		var arc: Dictionary = config.arcs[index]
		if not arc.enabled: continue
		var data := Values.read(arc.resource)
		state.append(data)
		lines.append(("Left" if index < 4 else "Right") + " %d · %s: %s" % [index % 4 + 1, data.label, Values.value_text(data)])
	if state != _signature:
		_signature = state
		tooltip_text = "\n".join(lines)
		queue_redraw()

func dock_rect() -> Rect2:
	return core_rect()

func unit_scale() -> float:
	return maxf(0.01, minf(size.x / 240.0, size.y / 200.0))

func center_point() -> Vector2:
	return size * Vector2(0.5, 0.42)

func frame_radius() -> float:
	return float({"plain":53, "laurel":66, "runic":78, "crystal":73}.get(config.border_design, 53)) * unit_scale()

func core_rect() -> Rect2:
	return Rect2(center_point() - Vector2.ONE * frame_radius(), Vector2.ONE * frame_radius() * 2)

func arc_geometry(index: int) -> Dictionary:
	var arc: Dictionary = config.arcs[index]
	var radius := (76 + (index % 4) * 9 + float(arc.get("radius_offset", 0))) * unit_scale()
	var start := deg_to_rad(float(arc.get("start_angle", 100 if index < 4 else 15)))
	var end := start + deg_to_rad(float(arc.get("sweep_angle", 65)))
	# Keep the lower curves clear of attached buttons, including two-row bars.
	var clearance: float = dock_clearance.left if index < 4 else dock_clearance.right
	if clearance > 0:
		var angle := asin(clampf((clearance + 5 * unit_scale()) / maxf(1, radius), 0, 0.98))
		if index < 4 and start >= PI / 2 and end <= PI: end = maxf(start + 0.05, minf(end, PI - angle))
		elif index >= 4 and start >= 0 and end <= PI / 2: start = minf(end - 0.05, maxf(start, angle))
	var bottom: float = dock_clearance.get("bottom", 0.0)
	if bottom > 0:
		var angle := acos(clampf((bottom + 5 * unit_scale()) / maxf(1, radius), 0, 0.98))
		if start >= PI / 2 and end <= PI: start = minf(end - 0.05, maxf(start, PI - angle))
		elif start >= 0 and end <= PI / 2: end = maxf(start + 0.05, minf(end, angle))
	return {"center":center_point(), "radius":radius, "start":start,
		"sweep":maxf(0.05, end - start), "thickness":float(arc.get("thickness", 5)) * unit_scale()}

func arc_points(index: int, segments := 40) -> PackedVector2Array:
	var shape := arc_geometry(index)
	var points := PackedVector2Array()
	for step: int in segments + 1:
		var angle: float = shape.start + shape.sweep * float(step) / segments
		points.append(shape.center + Vector2.from_angle(angle) * float(shape.radius))
	return points

func arc_at(point: Vector2, tolerance := 4.0) -> int:
	var best := -1
	var distance := INF
	for index: int in 8:
		if not config.arcs[index].enabled: continue
		var shape := arc_geometry(index)
		var offset: Vector2 = point - shape.center
		var relative_angle := fposmod(offset.angle() - float(shape.start), TAU)
		var radial := absf(offset.length() - float(shape.radius))
		if relative_angle <= float(shape.sweep) + tolerance / maxf(1, shape.radius) and radial <= float(shape.thickness) / 2 + tolerance and radial < distance:
			best = index
			distance = radial
	return best

func visual_rect() -> Rect2:
	var bounds := core_rect()
	for index: int in 8:
		if not config.arcs[index].enabled: continue
		var points := arc_points(index)
		for point: Vector2 in points: bounds = bounds.expand(point)
	return bounds.grow(3 * unit_scale())

func _has_point(point: Vector2) -> bool:
	# Empty corners of the orb must not eat clicks on docked quick slots.
	return point.distance_to(center_point()) <= frame_radius() or arc_at(point, 1.5) >= 0

func connection_background_patches() -> Array[Dictionary]:
	# Paint each pixel once, so translucent joined backgrounds keep their opacity.
	var patches: Array[Dictionary] = []
	var painted: Array[Rect2] = connection_panels.duplicate()
	for connection: Dictionary in connections:
		if connection.background.a <= 0: continue
		for rect: Rect2 in Chrome.uncovered_rects(connection.rect, painted): patches.append({"rect":rect, "color":connection.background})
		painted.append(connection.rect)
	return patches

func _draw() -> void:
	var center := center_point()
	var factor := unit_scale()
	var radius := 49.0 * factor
	var data := Values.read(config.center_resource)
	var color: Color = config.center_color
	var text: Color = config.text_color
	# Extend docked shells beneath the circular ornament. The orb and ring
	# cover the inner ends, leaving one continuous silhouette at the join.
	for patch: Dictionary in connection_background_patches(): draw_rect(patch.rect, patch.color)
	for connection: Dictionary in connections:
		var rect: Rect2 = connection.rect
		var adjacent: Array[Rect2] = []
		if connection.background.a > 0 and connection.border.a > 0:
			adjacent.assign(connection_panels)
			for other: Dictionary in connections:
				if other != connection and other.background.a > 0 and other.border.a > 0: adjacent.append(other.rect)
		var sides: Array = [SIDE_TOP, SIDE_BOTTOM] if connection.horizontal else [SIDE_LEFT, SIDE_RIGHT]
		for side: int in sides:
			for segment: Vector2 in Chrome.edge_segments(rect, side, adjacent):
				if side in [SIDE_TOP, SIDE_BOTTOM]:
					var y := rect.position.y if side == SIDE_TOP else rect.end.y
					draw_line(Vector2(segment.x, y), Vector2(segment.y, y), connection.border, 1, true)
				else:
					var x := rect.position.x if side == SIDE_LEFT else rect.end.x
					draw_line(Vector2(x, segment.x), Vector2(x, segment.y), connection.border, 1, true)
	draw_circle(center, radius, config.background_color)
	# Horizontal strips keep the liquid fill inside the circle.
	var waterline := radius - 2 * radius * float(data.ratio)
	for row: int in ceili(radius * 2):
		var y := float(row) - radius
		if y < waterline: continue
		var half := sqrt(maxf(0, radius * radius - y * y))
		var fill := color.lerp(color.darkened(0.65), clampf((y + radius) / (2 * radius), 0, 1) * 0.75)
		draw_line(center + Vector2(-half, y), center + Vector2(half, y), fill, 1.5)
	draw_arc(center, radius - 3 * factor, PI * 1.1, PI * 1.7, 32, Color(1, 1, 1, 0.17), 2 * factor, true)
	if config.border_design == "plain":
		draw_arc(center, radius + 3 * factor, 0, TAU, 96, config.border_color, 3 * factor, true)
	elif _textures.has(config.border_design):
		var width: float = {"laurel":136.0, "runic":160.0, "crystal":150.0}[config.border_design] * factor
		var tint := Color.WHITE.lerp(config.border_color, 0.20)
		draw_texture_rect(_textures[config.border_design], Rect2(center - Vector2.ONE * width / 2, Vector2.ONE * width), false, tint)
	for index: int in 8:
		var arc: Dictionary = config.arcs[index]
		if not arc.enabled: continue
		var meter := Values.read(arc.resource)
		var geometry := arc_geometry(index)
		var arc_radius: float = geometry.radius
		var start: float = geometry.start
		var end: float = start + geometry.sweep
		draw_arc(center, arc_radius, start, end, 40, config.background_color, geometry.thickness + 2 * factor, true)
		draw_arc(center, arc_radius, start, end, 40, Color(0.8, 0.8, 0.8, 0.20), 1 * factor, true)
		if meter.ratio > 0:
			draw_arc(center, arc_radius, start, lerpf(start, end, meter.ratio), 40, arc.color, geometry.thickness, true)
	var font := ThemeDB.fallback_font
	if config.show_values:
		draw_string(font, Vector2(0, center.y + 3 * factor), str(int(data.value)) if data.available else "—", HORIZONTAL_ALIGNMENT_CENTER, size.x, maxi(10, int(24 * factor)), text)
		draw_string(font, Vector2(0, center.y + 20 * factor), "/ %d" % data.maximum if data.available else "Unmounted", HORIZONTAL_ALIGNMENT_CENTER, size.x, maxi(9, int(12 * factor)), text)
	if config.show_labels:
		draw_string(font, Vector2(0, center.y - 20 * factor), data.label, HORIZONTAL_ALIGNMENT_CENTER, size.x, maxi(9, int(11 * factor)), text)
