extends RefCounted
## Shared chrome for the action book. Availability always comes from game state.
const TEXT := Color("eee3c8")
const MUTED := Color("b6aa91")
const GOLD := Color("e8c77a")
const GOOD := Color("73df89")
const BAD := Color("ff7979")
const SURFACE := Color("100d09")

static func box(fill: Color, edge := Color.TRANSPARENT, margin := 6.0) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = edge
	style.set_border_width_all(1 if edge.a > 0.0 else 0)
	style.set_content_margin_all(margin)
	return style

static func button(text: String = "") -> Button:
	var result := Button.new()
	result.text = text
	result.custom_minimum_size.y = 28
	result.add_theme_font_size_override("font_size", 13)
	result.add_theme_color_override("font_color", TEXT)
	result.add_theme_stylebox_override("normal", box(Color("17120d"), Color("80623b")))
	result.add_theme_stylebox_override("hover", box(Color("332719"), GOLD))
	result.add_theme_stylebox_override("pressed", box(Color("45331f"), GOLD))
	result.add_theme_stylebox_override("disabled", box(Color("191714"), Color("504630")))
	result.add_theme_stylebox_override("focus", box(Color.TRANSPARENT, GOLD, 0))
	return result

static func icon_button(result: Button) -> void:
	result.custom_minimum_size = Vector2(36, 36)
	result.expand_icon = true
	result.add_theme_constant_override("icon_max_width", 32)
	result.add_theme_stylebox_override("normal", box(Color.TRANSPARENT, Color.TRANSPARENT, 2))
	result.add_theme_stylebox_override("hover", box(Color("302418"), Color("80623b"), 2))
	var selected := box(Color("332819"), GOLD, 2)
	selected.set_border_width_all(2)
	result.add_theme_stylebox_override("pressed", selected)
	result.add_theme_stylebox_override("hover_pressed", selected)
	result.add_theme_stylebox_override("focus", box(Color.TRANSPARENT, GOLD, 0))
	result.size_flags_horizontal = Control.SIZE_SHRINK_CENTER

static func icon_availability(control: Button, ready: bool) -> void:
	# Dim the artwork, not the selection/focus border around an unavailable action.
	control.modulate = Color.WHITE
	var tint := Color(1, 1, 1, 1.0 if ready else 0.45)
	for state: String in ["icon_normal_color", "icon_hover_color", "icon_pressed_color", "icon_hover_pressed_color"]:
		control.add_theme_color_override(state, tint)

static func label(text := "", font_size := 14, wrap := false) -> Label:
	var result := Label.new()
	result.text = text
	result.add_theme_font_size_override("font_size", font_size)
	result.add_theme_color_override("font_color", TEXT)
	if wrap:
		result.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return result

static func scroll(name: String) -> ScrollContainer:
	var result := ScrollContainer.new()
	result.name = name
	result.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	result.size_flags_vertical = Control.SIZE_EXPAND_FILL
	result.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	result.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	return result

static func clear(control: Control) -> void:
	for child in control.get_children():
		control.remove_child(child)
		child.queue_free()

static func requirement(parent: Control, title: String, detail: String, met: Variant,
		icon: Texture2D = null) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.set_meta("requirement", {"label": title, "detail": detail, "met": met})
	row.add_theme_constant_override("separation", 5)
	var color: Color = MUTED if met == null else GOOD if met else BAD
	var marker := label("•" if met == null else "✓" if met else "×", 14)
	marker.add_theme_color_override("font_color", color)
	row.add_child(marker)
	if icon != null:
		var picture := TextureRect.new()
		picture.texture = icon
		picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		picture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		picture.custom_minimum_size = Vector2(18, 18)
		row.add_child(picture)
	var text := label(title, 13, true)
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.add_theme_color_override("font_color", color)
	row.add_child(text)
	var count := label(detail, 12, detail.length() > 20)
	count.custom_minimum_size.x = 78 if detail.length() > 9 else 60
	count.size_flags_horizontal = Control.SIZE_SHRINK_END
	count.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	count.add_theme_color_override("font_color", color)
	row.add_child(count)
	parent.add_child(row)
	return row

static func filters(parent: Control, callback: Callable) -> Dictionary:
	var buttons := {}
	for key: String in ["all", "ready", "learned", "favorites"]:
		var control := button(key.capitalize())
		control.toggle_mode = true
		control.set_pressed_no_signal(key == "all")
		control.pressed.connect(callback.bind(key))
		parent.add_child(control)
		buttons[key] = control
	return buttons

static func slot_picker() -> OptionButton:
	var result := OptionButton.new()
	result.add_theme_font_size_override("font_size", 13)
	for index in range(12):
		result.add_item("Slot %d" % (index + 1))
	result.tooltip_text = "Choose the shared quick slot to assign or replace."
	return result
