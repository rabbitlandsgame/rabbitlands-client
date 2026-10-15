extends RefCounted
## Shared, restrained fantasy chrome for the party roster and chat.
const TEXT := Color("eee3c8")
const MUTED := Color("b6aa91")
const BRASS := Color("9d8150")
const SURFACE := Color(0.075, 0.065, 0.05, 0.93)

static func box(background: Color = SURFACE, edge: Color = BRASS,
		margin: float = 8.0) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = background
	result.border_color = edge
	result.set_border_width_all(1)
	result.set_corner_radius_all(4)
	result.set_content_margin_all(margin)
	return result

static func button(control: Button) -> void:
	control.focus_mode = Control.FOCUS_NONE
	control.add_theme_font_size_override("font_size", 12)
	control.add_theme_color_override("font_color", MUTED)
	control.add_theme_color_override("font_pressed_color", TEXT)
	control.add_theme_stylebox_override("normal", box(Color(0.10, 0.085, 0.065, 0.7), Color(0.3, 0.25, 0.17, 0.8), 5))
	control.add_theme_stylebox_override("hover", box(Color("403324"), BRASS, 5))
	control.add_theme_stylebox_override("pressed", box(Color("53281e"), Color("c4a269"), 5))
