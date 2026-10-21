extends Node2D
## Paint the outside of connected HUD panels. A Node2D never participates in
## Container sizing, scrolling, focus or input handling.
var config: Dictionary = {}
var neighbours: Array[Rect2] = []
var background_exclusions: Array[Rect2] = []
var shape := "rectangle"
var circle_inset := 1.5

func _ready() -> void:
	show_behind_parent = true
	(get_parent() as Control).resized.connect(queue_redraw)

static func edge_segments(rect: Rect2, side: int, adjacent: Array[Rect2]) -> Array[Vector2]:
	var horizontal := side in [SIDE_TOP, SIDE_BOTTOM]
	var begin := rect.position.x if horizontal else rect.position.y
	var finish := rect.end.x if horizontal else rect.end.y
	var segments: Array[Vector2] = [Vector2(begin, finish)]
	for other: Rect2 in adjacent:
		var touches := false
		match side:
			SIDE_TOP: touches = other.position.y < rect.position.y - 0.1 and other.end.y >= rect.position.y - 1.1
			SIDE_BOTTOM: touches = other.end.y > rect.end.y + 0.1 and other.position.y <= rect.end.y + 1.1
			SIDE_LEFT: touches = other.position.x < rect.position.x - 0.1 and other.end.x >= rect.position.x - 1.1
			SIDE_RIGHT: touches = other.end.x > rect.end.x + 0.1 and other.position.x <= rect.end.x + 1.1
		if not touches: continue
		var cut := Vector2(other.position.x, other.end.x) if horizontal else Vector2(other.position.y, other.end.y)
		var remaining: Array[Vector2] = []
		for segment: Vector2 in segments:
			if cut.y <= segment.x or cut.x >= segment.y: remaining.append(segment)
			else:
				if cut.x > segment.x: remaining.append(Vector2(segment.x, cut.x))
				if cut.y < segment.y: remaining.append(Vector2(cut.y, segment.y))
		segments = remaining
	return segments

static func uncovered_rects(rect: Rect2, masks: Array[Rect2]) -> Array[Rect2]:
	var remaining: Array[Rect2] = [rect]
	for mask: Rect2 in masks:
		var next: Array[Rect2] = []
		for piece: Rect2 in remaining:
			var overlap := piece.intersection(mask)
			if not overlap.has_area():
				next.append(piece)
				continue
			for patch: Rect2 in [Rect2(piece.position, Vector2(piece.size.x, overlap.position.y - piece.position.y)),
				Rect2(Vector2(piece.position.x, overlap.end.y), Vector2(piece.size.x, piece.end.y - overlap.end.y)),
				Rect2(Vector2(piece.position.x, overlap.position.y), Vector2(overlap.position.x - piece.position.x, overlap.size.y)),
				Rect2(Vector2(overlap.end.x, overlap.position.y), Vector2(piece.end.x - overlap.end.x, overlap.size.y))]:
				if patch.has_area(): next.append(patch)
		remaining = next
	return remaining

func background_patches() -> Array[Rect2]:
	var control := get_parent() as Control
	var inverse := control.get_global_transform().affine_inverse()
	var patches: Array[Rect2] = []
	for patch: Rect2 in uncovered_rects(control.get_global_rect(), background_exclusions): patches.append(inverse * patch)
	return patches

func _draw() -> void:
	if config.is_empty(): return
	var control := get_parent() as Control
	var rect := Rect2(Vector2.ZERO, control.size)
	var design: String = config.get("hud_border_style", "plain")
	if shape == "circle":
		var radius := maxf(2, minf(rect.size.x, rect.size.y) * 0.5 - circle_inset)
		if config.show_background: draw_circle(rect.get_center(), radius, config.background_color)
		if config.show_border: draw_circle_border(self, rect.get_center(), radius, config.border_color, design)
		return
	if config.show_background:
		for patch: Rect2 in background_patches(): draw_rect(patch, config.background_color)
	if not config.show_border: return
	var global_rect := control.get_global_rect()
	var inverse := control.get_global_transform().affine_inverse()
	for side: int in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
		for segment: Vector2 in edge_segments(global_rect, side, neighbours):
			var a: Vector2
			var b: Vector2
			if side in [SIDE_TOP, SIDE_BOTTOM]:
				var y := global_rect.position.y if side == SIDE_TOP else global_rect.end.y
				a = Vector2(segment.x, y)
				b = Vector2(segment.y, y)
			else:
				var x := global_rect.position.x if side == SIDE_LEFT else global_rect.end.x
				a = Vector2(x, segment.x)
				b = Vector2(x, segment.y)
			var start := inverse * a
			var finish := inverse * b
			var edge: Color = config.border_color
			if design == "plain": draw_line(start, finish, edge, 1)
			else:
				var inward: Vector2 = {SIDE_LEFT:Vector2.RIGHT, SIDE_RIGHT:Vector2.LEFT, SIDE_TOP:Vector2.DOWN, SIDE_BOTTOM:Vector2.UP}[side]
				draw_line(start + inward, finish + inward, edge.darkened(0.6), 3)
				draw_line(start + inward, finish + inward, edge.lightened(0.35) if side in [SIDE_TOP, SIDE_LEFT] else edge.darkened(0.25), 1)
				draw_line(start + inward * 3, finish + inward * 3, edge.darkened(0.4), 1)
	if design == "ornate":
		for corner: Vector2 in [Vector2.ZERO, Vector2(1, 0), Vector2(0, 1), Vector2.ONE]:
			var global_corner := global_rect.position + global_rect.size * corner
			var horizontal := SIDE_TOP if corner.y == 0 else SIDE_BOTTOM
			var vertical := SIDE_LEFT if corner.x == 0 else SIDE_RIGHT
			if not _exposed_corner(global_rect, horizontal, global_corner.x) or not _exposed_corner(global_rect, vertical, global_corner.y): continue
			var point := rect.position + rect.size * corner
			var inward := Vector2.ONE - corner * 2
			var edge: Color = config.border_color
			draw_line(point + Vector2(inward.x * 3, inward.y * 12), point + inward * 3, edge.lightened(0.35), 2, true)
			draw_line(point + inward * 3, point + Vector2(inward.x * 12, inward.y * 3), edge.lightened(0.35), 2, true)
			draw_circle(point + inward * 6, 2.5, edge.darkened(0.45))
			draw_circle(point + inward * 6, 1.3, edge.lightened(0.45))

func _exposed_corner(rect: Rect2, side: int, value: float) -> bool:
	for segment: Vector2 in edge_segments(rect, side, neighbours):
		if value >= segment.x - 0.1 and value <= segment.y + 0.1: return true
	return false

static func draw_circle_border(canvas: CanvasItem, center: Vector2, radius: float, color: Color, design: String) -> void:
	if design == "plain":
		canvas.draw_arc(center, radius, 0, TAU, 128, color, 1.5, true)
		return
	canvas.draw_arc(center, radius - 1, 0, TAU, 128, color.darkened(0.6), 5, true)
	canvas.draw_arc(center, radius, 0, TAU, 128, color, 1.5, true)
	canvas.draw_arc(center, radius - 3, 0, TAU, 128, color.lightened(0.25), 1, true)
	canvas.draw_arc(center, radius - 0.5, PI, TAU + PI * 0.1, 80, color.lightened(0.5), 1, true)
	if design == "ornate":
		for index: int in 8:
			var direction := Vector2.from_angle(index * TAU / 8)
			var tangent := direction.orthogonal()
			var point := center + direction * (radius - 2)
			var width := 3.5 if index % 2 == 0 else 2.5
			canvas.draw_colored_polygon(PackedVector2Array([point + direction * 3, point + tangent * width, point - direction * 4, point - tangent * width]), color.lightened(0.25))
			canvas.draw_circle(point - direction, 1.2, color.darkened(0.65))
