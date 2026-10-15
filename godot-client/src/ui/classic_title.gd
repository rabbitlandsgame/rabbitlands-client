class_name ClassicTitle
extends HBoxContainer

var title: Label

func _init(caption: String = "") -> void:
	custom_minimum_size.y = 24
	title = Label.new()
	title.text = caption
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title.add_theme_color_override("font_color", Color("e9bd83"))
	add_child(title)
	resized.connect(queue_redraw)

func _draw() -> void:
	var amber := Color("b58b57")
	var rail_y := 5.0
	draw_line(Vector2(3, rail_y), Vector2(size.x - 3, rail_y), amber, 3)
	draw_line(Vector2(3, rail_y + 3), Vector2(size.x - 3, rail_y + 3), Color("775435"), 1)
	for edge: float in [3.0, size.x - 3.0]:
		draw_polyline(PackedVector2Array([Vector2(edge, 1), Vector2(edge - 3, 5),
			Vector2(edge, 10), Vector2(edge + 3, 5), Vector2(edge, 1)]), amber, 1)
	var text_width: float = title.get_theme_font("font").get_string_size(
		title.text, HORIZONTAL_ALIGNMENT_LEFT, -1, title.get_theme_font_size("font_size")).x + 18
	draw_rect(Rect2((size.x - text_width) * 0.5, 0, text_width, 16), Color("05090a"))
