extends Node2D
## A restrained inlaid edge, separate from layout and input.
var inset := -3.0
func _ready() -> void:
	z_index = 10
	(get_parent() as Control).resized.connect(queue_redraw)

func _draw() -> void:
	var bounds := Rect2(Vector2.ONE * inset, (get_parent() as Control).size - Vector2.ONE * inset * 2)
	var silver := Color("72899c")
	var shadow := Color("1d3040")
	for corner: Vector2 in [Vector2.ZERO, Vector2(1, 0), Vector2(0, 1), Vector2.ONE]:
		var origin := bounds.position + bounds.size * corner
		var inward := Vector2.ONE - corner * 2
		var points := PackedVector2Array()
		for point: Vector2 in [Vector2(2, 23), Vector2(2, 6), Vector2(6, 2), Vector2(23, 2)]:
			points.append(origin + point * inward)
		draw_polyline(points, shadow, 5, true)
		draw_polyline(points, silver, 1, true)
		var center := origin + Vector2(9, 9) * inward
		draw_circle(center, 3, Color("223e52"))
		draw_arc(center, 3, 0, TAU, 14, silver, 1, true)
