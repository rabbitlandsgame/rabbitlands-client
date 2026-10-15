extends Control
## Initials identify remote members without inventing a portrait the server
## never sent. The leader's crown is drawn in the same brass as the frame.
var initials := "?"
var leader := false

func configure(member: Dictionary) -> void:
	var player_name := str(member.get("name", "?"))
	initials = player_name.left(2).to_upper()
	leader = bool(member.get("leader", false))
	custom_minimum_size = Vector2(30, 34)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	tooltip_text = player_name
	queue_redraw()

func _draw() -> void:
	var center := Vector2(15, 19)
	draw_circle(center, 13, Color("252019"))
	draw_arc(center, 13, 0, TAU, 36, Color("bda16a"), 1.2, true)
	var font := ThemeDB.fallback_font
	var width := font.get_string_size(initials, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x
	draw_string(font, Vector2(center.x - width * 0.5, 23), initials,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color("eee3c8"))
	if leader:
		draw_colored_polygon(PackedVector2Array([
			Vector2(9, 6), Vector2(8, 1), Vector2(12, 4), Vector2(15, 0),
			Vector2(18, 4), Vector2(22, 1), Vector2(21, 6)]), Color("e5bc67"))
