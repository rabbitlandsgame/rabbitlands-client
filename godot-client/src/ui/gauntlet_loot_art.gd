extends RefCounted
## Scalable metalwork and inked surfaces for the party ledger.

const GOLD := Color("c99a58")
const INK := Color("030c0e")
static var _wash: GradientTexture2D

static func wash() -> GradientTexture2D:
	if _wash == null:
		_wash = GradientTexture2D.new()
		_wash.width = 32
		_wash.height = 256
		_wash.fill_from = Vector2(0, 0)
		_wash.fill_to = Vector2(0, 1)
		var gradient := Gradient.new()
		gradient.set_color(0, Color("102327"))
		gradient.set_color(1, INK)
		_wash.gradient = gradient
	return _wash

static func surface(canvas: Control, opacity := 0.55) -> void:
	canvas.draw_texture_rect(wash(), Rect2(Vector2.ONE * 2, canvas.size - Vector2.ONE * 4), false, Color(1, 1, 1, opacity))

static func frame(canvas: Control) -> void:
	surface(canvas, 0.26)
	var bounds := Rect2(Vector2(3, 3), canvas.size - Vector2(6, 6))
	canvas.draw_rect(bounds, Color(GOLD, 0.9), false, 1.0)
	canvas.draw_rect(bounds.grow(-4), Color(GOLD, 0.22), false, 1.0)
	for corner: Vector2 in [bounds.position, Vector2(bounds.end.x, bounds.position.y), bounds.end, Vector2(bounds.position.x, bounds.end.y)]:
		var direction := Vector2(1 if corner.x == bounds.position.x else -1, 1 if corner.y == bounds.position.y else -1)
		var points := PackedVector2Array()
		for point: Vector2 in [Vector2(0, 46), Vector2(0, 17), Vector2(6, 7), Vector2(17, 0), Vector2(46, 0)]:
			points.append(corner + point * direction)
		canvas.draw_polyline(points, GOLD, 1.8, true)
		var curl := Curve2D.new()
		curl.add_point(corner + Vector2(36, 5) * direction, Vector2.ZERO, Vector2(-22, 0) * direction)
		curl.add_point(corner + Vector2(10, 29) * direction, Vector2(0, -19) * direction, Vector2(15, 14) * direction)
		curl.add_point(corner + Vector2(23, 20) * direction, Vector2(10, 5) * direction)
		canvas.draw_polyline(curl.tessellate(), Color(GOLD, 0.75), 1.0, true)
		var center := corner + direction * 10
		canvas.draw_colored_polygon(PackedVector2Array([center + Vector2(-4, 0), center + Vector2(0, -4), center + Vector2(4, 0), center + Vector2(0, 4)]), GOLD)
	var center := canvas.size.x * 0.5
	for side: int in [-1, 1]:
		canvas.draw_line(Vector2(center + side * 190, 68), Vector2(center + side * 310, 68), Color(GOLD, 0.38), 1.0, true)
		canvas.draw_circle(Vector2(center + side * 180, 68), 2, GOLD)

static func rule(canvas: Control, color := GOLD) -> void:
	var y := canvas.size.y * 0.5
	canvas.draw_line(Vector2(0, y), Vector2(canvas.size.x, y), Color(color, 0.6), 1.0, true)
	canvas.draw_line(Vector2(0, y + 3), Vector2(canvas.size.x, y + 3), Color(color, 0.15), 1.0, true)

static func columns(canvas: Control, line: HBoxContainer, color: Color) -> void:
	for i: int in range(1, line.get_child_count()):
		var column := line.get_child(i) as Control
		if column == null: continue
		var x := line.position.x + column.position.x - 4
		canvas.draw_line(Vector2(x, 1), Vector2(x, canvas.size.y - 1), Color(color, 0.2), 1.0)
