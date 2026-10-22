extends Control
## The live camera heading, as a round instrument or a heading ribbon.
const Chrome := preload("res://src/ui/hud_panel_chrome.gd")
var source: Control
var config: Dictionary = {}
var _last_heading := INF
var _last_area := ""

func _ready() -> void:
	custom_minimum_size = Vector2(84, 56)
	mouse_filter = Control.MOUSE_FILTER_STOP
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	tooltip_text = "Click for your coordinates; Shift+click shares them to your current chat destination. Ctrl+click shares to the active numeric channel."
	resized.connect(queue_redraw)

func configure(owner_main: Control, value: Dictionary) -> void:
	source = owner_main
	config = value.duplicate(true)
	size = Vector2(380, 58) if config.compass_mode == "ribbon" else Vector2(112, 112)
	queue_redraw()

func _has_point(point: Vector2) -> bool:
	if config.is_empty(): return false
	if config.compass_mode == "round" and has_node("_HudChrome") and get_node("_HudChrome").shape == "circle":
		return point.distance_to(size * 0.5) <= minf(size.x, size.y) * 0.46
	return Rect2(Vector2.ZERO, size).has_point(point)

func _process(_delta: float) -> void:
	if source == null: return
	var heading: float = fposmod(source.camera_rig.yaw_degrees, 360)
	var area: String = source._current_map_display_name
	if not is_equal_approx(_last_heading, heading) or area != _last_area:
		_last_heading = heading
		_last_area = area
		queue_redraw()

func _draw() -> void:
	if config.is_empty(): return
	var heading := 0.0 if not is_finite(_last_heading) else _last_heading
	var font := ThemeDB.fallback_font
	var edge: Color = config.border_color
	var text: Color = config.text_color
	var shared_frame := has_node("_HudChrome")
	if config.compass_mode == "ribbon":
		var box := StyleBoxFlat.new()
		box.bg_color = config.background_color
		box.border_color = edge
		box.border_width_bottom = 1
		if not config.get("show_background", true): box.bg_color.a = 0
		if not config.get("show_border", true): box.set_border_width_all(0)
		if not shared_frame: draw_style_box(box, Rect2(Vector2.ZERO, Vector2(size.x, 34)))
		for delta: int in range(-90, 91, 5):
			var bearing := roundi(heading / 5) * 5 + delta
			var x := size.x * 0.5 + (float(bearing) - heading) * (size.x / 180)
			if x < 12 or x > size.x - 12: continue
			var cardinal: String = {0:"N", 90:"E", 180:"S", 270:"W"}.get(posmod(bearing, 360), "")
			draw_line(Vector2(x, 4), Vector2(x, 10 if bearing % 15 else 15), edge, 1)
			if bearing % 30 == 0:
				draw_string(font, Vector2(x - 18, 29), cardinal if not cardinal.is_empty() else str(posmod(bearing, 360)), HORIZONTAL_ALIGNMENT_CENTER, 36, 12, text)
		draw_colored_polygon(PackedVector2Array([Vector2(size.x / 2 - 4, 0), Vector2(size.x / 2 + 4, 0), Vector2(size.x / 2, 6)]), edge)
		if config.show_labels: draw_string(font, Vector2(0, 53), _last_area, HORIZONTAL_ALIGNMENT_CENTER, size.x, 13, text)
	else:
		var center := size * 0.5
		var radius := minf(size.x, size.y) * 0.46
		if not shared_frame and config.get("show_background", true): draw_circle(center, radius, config.background_color)
		var filled: bool = get_node("_HudChrome").shape == "rectangle" if shared_frame else false
		if config.get("show_border", true) and (not shared_frame or filled):
			Chrome.draw_circle_border(self, center, radius, edge, config.get("hud_border_style", "plain"))
		for bearing: int in range(0, 360, 15):
			var angle := deg_to_rad(bearing - heading - 90)
			var direction := Vector2(cos(angle), sin(angle))
			draw_line(center + direction * (radius - 10), center + direction * (radius - 6), edge, 1)
			if bearing % 90 == 0:
				var point := center + direction * (radius - 21)
				draw_string(font, point + Vector2(-10, 5), ["N", "E", "S", "W"][bearing / 90], HORIZONTAL_ALIGNMENT_CENTER, 20, 13, text)
		draw_colored_polygon(PackedVector2Array([center + Vector2(0, -18), center + Vector2(-7, 10), center, center + Vector2(7, 10)]), Color("6dbdd8"))
		draw_circle(center, 3, edge)
