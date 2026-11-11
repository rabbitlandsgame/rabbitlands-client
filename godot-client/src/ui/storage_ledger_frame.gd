extends Node2D
## Beveled bronze edging stays independent of layout and input.
func _ready() -> void:
	(get_parent() as Control).resized.connect(queue_redraw)

func _draw() -> void:
	var bounds: Vector2 = (get_parent() as Control).size
	var brass := Color("b08a59")
	var dark := Color("3c2e20")
	var shine := Color("e1bd81")
	for inset: float in [2.0, 5.0]:
		var a := Vector2(inset, inset)
		var b := bounds - Vector2.ONE * inset
		var corners := PackedVector2Array([a + Vector2(7, 0), Vector2(b.x - 7, a.y),
			Vector2(b.x, a.y + 7), Vector2(b.x, b.y - 7), b - Vector2(7, 0),
			Vector2(a.x + 7, b.y), Vector2(a.x, b.y - 7), a + Vector2(0, 7), a + Vector2(7, 0)])
		draw_polyline(corners, brass if inset == 2 else dark, 1, true)
	for corner: Vector2 in [Vector2.ZERO, Vector2(1, 0), Vector2(0, 1), Vector2.ONE]:
		var p := bounds * corner
		var inward := Vector2.ONE - corner * 2
		draw_line(p + inward * 7 + Vector2(0, inward.y * 12), p + inward * 7, shine, 1, true)
		draw_line(p + inward * 7, p + inward * 7 + Vector2(inward.x * 12, 0), brass, 1, true)
