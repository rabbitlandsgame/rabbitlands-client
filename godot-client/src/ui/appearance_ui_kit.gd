class_name AppearanceUiKit
extends RefCounted
## Small shared pieces of the appearance controls (colour model spec 6): notice
## rows that pair an icon with text, tick strips under sliders, a lightness bar
## with marks and hatched bands, swatch icons, gradient slider tracks and the
## PageUp/PageDown/Home/End keys the sliders lack.

const NOTICE_ICON := Color(0.93, 0.62, 0.16)
## Minimum pointer target (colour model spec 6.4).
const TARGET := 24


## A notice: a round "!" icon, wrapping text and an optional button. The row
## starts hidden; `text` and the button are reached through get_meta.
static func notice(text: String, button_text := "", name := "Notice") -> HBoxContainer:
	var row := HBoxContainer.new()
	row.name = name
	row.add_theme_constant_override("separation", 6)
	var icon := NoticeIcon.new()
	row.add_child(icon)
	var label := Label.new()
	label.name = "Text"
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.custom_minimum_size.x = 120
	label.accessibility_live = AccessibilityServer.LIVE_POLITE
	row.add_child(label)
	row.set_meta("label", label)
	if not button_text.is_empty():
		var button := Button.new()
		button.name = "Action"
		button.text = button_text
		button.custom_minimum_size = Vector2(TARGET, TARGET)
		button.accessibility_name = button_text
		row.add_child(button)
		row.set_meta("button", button)
	row.hide()
	return row


## A solid swatch with a thin outline, for option items and toggle buttons.
static func swatch_icon(color: Color, size := 16) -> ImageTexture:
	var image := Image.create(size, size, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.08, 0.08, 0.08))
	image.fill_rect(Rect2i(1, 1, size - 2, size - 2), Color(color.r, color.g, color.b, 1.0).clamp())
	return ImageTexture.create_from_image(image)


## A slider track drawn as a gradient (and no filled part left of the grabber,
## so the whole gradient stays visible).
static func gradient_track(slider: HSlider, colours: PackedColorArray) -> void:
	var gradient := Gradient.new()
	var offsets := PackedFloat32Array()
	for index: int in colours.size():
		offsets.append(float(index) / maxf(1.0, float(colours.size() - 1)))
	gradient.offsets = offsets
	gradient.colors = colours
	var texture := GradientTexture1D.new()
	texture.gradient = gradient
	texture.width = 256
	var style := StyleBoxTexture.new()
	style.texture = texture
	style.content_margin_top = 5.0
	style.content_margin_bottom = 5.0
	slider.add_theme_stylebox_override("slider", style)
	slider.add_theme_stylebox_override("grabber_area", StyleBoxEmpty.new())
	slider.add_theme_stylebox_override("grabber_area_highlight", StyleBoxEmpty.new())


## PageUp/PageDown step by `page`, Home/End go to the ends: the arrow keys are
## the slider's own (colour model spec 6.4).
static func page_keys(slider: Range, page: float) -> void:
	slider.gui_input.connect(func(event: InputEvent) -> void:
		var key := event as InputEventKey
		if key == null or not key.pressed:
			return
		match key.keycode:
			KEY_PAGEUP:
				slider.value += page
			KEY_PAGEDOWN:
				slider.value -= page
			KEY_HOME:
				slider.value = slider.min_value
			KEY_END:
				slider.value = slider.max_value
			_:
				return
		slider.accept_event())


## Pixel x of `value` on a horizontal slider of `width`, matching where Godot
## centres the grabber.
static func slider_x(slider: Range, value: float, width: float) -> float:
	return TickStrip.x_of(slider, value, width)


## The round "!" icon of a notice.
class NoticeIcon extends Control:
	func _init() -> void:
		custom_minimum_size = Vector2(18, 18)
		size_flags_vertical = Control.SIZE_SHRINK_CENTER
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var centre := size * 0.5
		draw_circle(centre, 8.0, NOTICE_ICON)
		var font := get_theme_default_font()
		draw_string(font, centre + Vector2(-2.5, 5.0), "!", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.1, 0.07, 0.02))


## Tick marks (and optional names) under a slider: `ticks` is [[value, name]].
class TickStrip extends Control:
	var slider: Range
	var ticks: Array = []
	var font_size := 11

	func _init(target: Range = null, entries: Array = []) -> void:
		slider = target
		ticks = entries
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var named := entries.any(func(entry: Array) -> bool: return entry.size() > 1 and not str(entry[1]).is_empty())
		custom_minimum_size.y = 6.0 + (font_size + 4.0 if named else 0.0)

	static func x_of(target: Range, value: float, width: float) -> float:
		var grabber := 16.0
		if target != null and target.has_theme_icon("grabber"):
			grabber = float(target.get_theme_icon("grabber").get_width())
		var span := maxf(1.0, target.max_value - target.min_value) if target != null else 100.0
		var low := target.min_value if target != null else 0.0
		return grabber * 0.5 + clampf((value - low) / span, 0.0, 1.0) * maxf(0.0, width - grabber)

	func _draw() -> void:
		var font := get_theme_default_font()
		var colour := get_theme_color("font_color", "Label")
		for entry: Array in ticks:
			var x := x_of(slider, float(entry[0]), size.x)
			draw_line(Vector2(x, 0), Vector2(x, 5), colour, 1.0)
			if entry.size() > 1 and not str(entry[1]).is_empty():
				var text := str(entry[1])
				var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
				var left := clampf(x - width * 0.5, 0.0, maxf(0.0, size.x - width))
				draw_string(font, Vector2(left, 6.0 + font_size), text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


## OKHSL lightness from 0 to 1 at one hue and saturation, with hatched bands
## (out-of-limit ranges), named marks (reach ceilings) and the current value.
class LightBar extends Control:
	var hue := 0.0
	var saturation := 0.0
	var current := 0.5
	## [[from, to]] lightness ranges drawn hatched.
	var bands: Array = []
	## [[lightness, name]] marks.
	var marks: Array = []

	func _init() -> void:
		custom_minimum_size = Vector2(160, 40)
		size_flags_horizontal = Control.SIZE_EXPAND_FILL
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func configure(h: float, s: float, l: float, hatched: Array, named: Array) -> void:
		hue = h
		saturation = s
		current = l
		bands = hatched
		marks = named
		queue_redraw()

	func _draw() -> void:
		var bar := Rect2(0, 0, size.x, 12)
		var steps := 48
		for step: int in steps:
			var l := (float(step) + 0.5) / float(steps)
			draw_rect(Rect2(bar.position.x + bar.size.x * float(step) / steps, 0,
				bar.size.x / steps + 1.0, bar.size.y), Color.from_ok_hsl(hue, saturation, l))
		for band: Array in bands:
			var from := bar.size.x * clampf(float(band[0]), 0.0, 1.0)
			var to := bar.size.x * clampf(float(band[1]), 0.0, 1.0)
			draw_rect(Rect2(from, 0, to - from, bar.size.y), Color(0, 0, 0, 0.35))
			var x := from - bar.size.y
			while x < to:
				var a := Vector2(maxf(x, from), bar.size.y - (maxf(x, from) - x))
				var b := Vector2(minf(x + bar.size.y, to), bar.size.y - (minf(x + bar.size.y, to) - x))
				draw_line(a, b, Color(1, 1, 1, 0.55), 1.0)
				x += 5.0
		draw_rect(bar, Color(0, 0, 0, 0.8), false, 1.0)
		var font := get_theme_default_font()
		var colour := get_theme_color("font_color", "Label")
		# Names under their marks; a name that would overlap the previous one
		# drops to a second line.
		var ordered := marks.duplicate()
		ordered.sort_custom(func(a: Array, b: Array) -> bool: return float(a[0]) < float(b[0]))
		var line_ends := [-INF, -INF]
		for mark: Array in ordered:
			var x := bar.size.x * clampf(float(mark[0]), 0.0, 1.0)
			draw_line(Vector2(x, -1), Vector2(x, bar.size.y + 3), Color(0.95, 0.3, 0.2), 2.0)
			var text := str(mark[1]) if mark.size() > 1 else ""
			if text.is_empty():
				continue
			var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x
			var left := clampf(x - width * 0.5, 0.0, maxf(0.0, size.x - width))
			var line := 0 if left > float(line_ends[0]) + 4.0 else 1
			line_ends[line] = left + width
			draw_string(font, Vector2(left, bar.size.y + 13 + 11 * line), text, HORIZONTAL_ALIGNMENT_LEFT, -1, 10, colour)
		var cx := bar.size.x * clampf(current, 0.0, 1.0)
		draw_colored_polygon(PackedVector2Array([Vector2(cx - 5, -1), Vector2(cx + 5, -1), Vector2(cx, 6)]),
			Color.WHITE)
		draw_polyline(PackedVector2Array([Vector2(cx - 5, -1), Vector2(cx + 5, -1), Vector2(cx, 6), Vector2(cx - 5, -1)]),
			Color.BLACK, 1.0)
