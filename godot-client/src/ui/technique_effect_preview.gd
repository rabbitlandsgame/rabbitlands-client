extends Control
## A local diagram of a technique's kind, never a combat simulation or request.
var row: Dictionary = {}
var clock := 0.0

func _ready() -> void:
	custom_minimum_size = Vector2(120, 92)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visibility_changed.connect(_update_processing)
	_update_processing()

func set_technique(value: Dictionary) -> void:
	if row.get("key") != value.get("key"):
		clock = 0.0
	row = value.duplicate(true)
	_update_processing()
	queue_redraw()

func _update_processing() -> void:
	set_process(is_visible_in_tree() and not row.is_empty())

func _process(delta: float) -> void:
	clock = fmod(clock + delta, 2.4)
	queue_redraw()

func _figure(at: Vector2, color: Color) -> void:
	draw_circle(at + Vector2(0, -17), 5, color)
	draw_line(at + Vector2(0, -10), at + Vector2(0, 8), color, 6, true)
	for side in [-1, 1]:
		draw_line(at + Vector2(0, 6), at + Vector2(side * 8, 21), color, 4, true)
		draw_line(at + Vector2(0, -6), at + Vector2(side * 10, 4), color, 4, true)

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("14202a"))
	if row.is_empty():
		return
	var center := size * Vector2(0.5, 0.55)
	var kind := str(row.get("kind", "strike"))
	var key := str(row.get("key", ""))
	var pulse := sin(clampf(clock / 0.8, 0, 1) * PI)
	var actor := center + Vector2(-30 + (pulse * 18 if kind == "charge" else 0), 0)
	_figure(actor, Color("80bddd"))
	if kind == "stance" or (not bool(row.get("targeted", false)) and key != "intercept"):
		draw_arc(actor, 26 + pulse * 3, 0, TAU, 32, Color("e8c77a"), 2, true)
	else:
		var target := center + Vector2(32, 0)
		_figure(target, Color("db9a83") if key != "intercept" else Color("80d7b0"))
		if pulse > 0:
			draw_line(actor + Vector2(10, -5), target + Vector2(-12, -5), Color("e8c77a"), 2 + pulse * 2, true)
		if key == "shield_bash":
			draw_arc(target + Vector2(0, -29), 8, 0, TAU, 20, Color("e8c77a"), 2, true)
