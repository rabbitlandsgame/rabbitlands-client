extends RefCounted
## Scoped palette and chrome for the compact tactics editor.
const INK := Color("f0e4c8")
const MUTED := Color("baad94")
const BRASS := Color("a8884d")
const GOLD := Color("e3c477")
const SURFACE := Color("12110d")
const EDGE := Color("5e5541")
const MOSS := Color("3b4820")
static var _heading_font: FontVariation
static var _surfaces: Dictionary = {}

static func surface(fill: Color, edge := EDGE, margin := 6.0, radius := 3) -> StyleBoxTexture:
	# Native UI artwork stays in code: a small shared nine-slice gives the
	# concept's subtle shaded surfaces without external textures or imports.
	var key := "%s/%s/%d" % [fill.to_html(), edge.to_html(), radius]
	if not _surfaces.has(key):
		var svg := '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#%s"/><stop offset="1" stop-color="#%s"/></linearGradient></defs><rect x="0.5" y="0.5" width="63" height="63" rx="%d" fill="url(#g)" stroke="#%s"/></svg>' % [fill.lightened(0.045).to_html(false), fill.darkened(0.14).to_html(false), radius, edge.to_html(false)]
		var image := Image.new()
		image.load_svg_from_string(svg)
		_surfaces[key] = ImageTexture.create_from_image(image)
	var result := StyleBoxTexture.new()
	result.texture = _surfaces[key]
	result.texture_margin_left = 5; result.texture_margin_right = 5
	result.texture_margin_top = 5; result.texture_margin_bottom = 5
	result.set_content_margin_all(margin)
	return result

static func heading_font() -> FontVariation:
	if _heading_font == null:
		_heading_font = FontVariation.new()
		_heading_font.base_font = ThemeDB.fallback_font
		_heading_font.variation_embolden = 0.6
	return _heading_font

static func check_icon(checked: bool, disabled := false) -> Texture2D:
	var fill := "#68704e" if disabled else "#b6cd7d" if checked else "#201f17"
	var check := '<path d="M4 9l3 3 7-7" fill="none" stroke="#263019" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>' if checked else ""
	var svg := '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"><rect x="1" y="1" width="16" height="16" rx="2" fill="%s" stroke="#a5aa83"/>%s</svg>' % [fill, check]
	var image := Image.new()
	image.load_svg_from_string(svg)
	return ImageTexture.create_from_image(image)

static func box(fill: Color, edge := EDGE, margin := 6.0, radius := 3) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = fill
	result.border_color = edge
	result.set_border_width_all(1)
	result.set_corner_radius_all(radius)
	result.set_content_margin_all(margin)
	return result

static func theme(compact := false) -> Theme:
	var result := Theme.new()
	result.default_font_size = 13 if compact else 14
	for type: String in ["Label", "Button", "OptionButton", "MenuButton", "CheckBox", "LineEdit", "PopupMenu"]:
		result.set_color("font_color", type, INK)
		result.set_color("font_hover_color", type, Color.WHITE)
		result.set_color("font_pressed_color", type, INK)
		result.set_color("font_hover_pressed_color", type, Color.WHITE)
		result.set_color("font_disabled_color", type, Color("857e6e"))
		result.set_color("font_focus_color", type, INK)
	for type: String in ["Button", "OptionButton", "MenuButton"]:
		result.set_stylebox("normal", type, surface(Color("1c1b15"), BRASS, 3 if compact else 6))
		result.set_stylebox("hover", type, surface(Color("343522"), GOLD, 3 if compact else 6))
		result.set_stylebox("pressed", type, surface(MOSS, GOLD, 3 if compact else 6))
		result.set_stylebox("hover_pressed", type, surface(Color("4b582a"), GOLD, 3 if compact else 6))
		result.set_stylebox("disabled", type, box(Color("22211c"), EDGE, 3 if compact else 6))
		var focus := box(Color.TRANSPARENT, GOLD, 0)
		focus.set_border_width_all(2)
		result.set_stylebox("focus", type, focus)
	for state: String in ["normal", "hover", "pressed", "hover_pressed", "disabled"]:
		result.set_stylebox(state, "CheckBox", StyleBoxEmpty.new())
	result.set_icon("checked", "CheckBox", check_icon(true))
	result.set_icon("unchecked", "CheckBox", check_icon(false))
	result.set_icon("checked_disabled", "CheckBox", check_icon(true, true))
	result.set_icon("unchecked_disabled", "CheckBox", check_icon(false, true))
	result.set_stylebox("normal", "LineEdit", box(Color("181813"), EDGE, 3 if compact else 6))
	result.set_stylebox("focus", "LineEdit", box(Color("22251a"), GOLD, 3 if compact else 6))
	result.set_stylebox("panel", "PopupMenu", box(Color("1b1b14"), BRASS, 8))
	result.set_stylebox("hover", "PopupMenu", box(MOSS, GOLD))
	result.set_constant("v_separation", "PopupMenu", 10)
	return result

static func label(text := "", font_size := 14, muted := false) -> Label:
	var result := Label.new()
	result.text = text
	result.add_theme_font_size_override("font_size", font_size)
	result.add_theme_color_override("font_color", MUTED if muted else INK)
	return result

static func button(text: String, accent := false) -> Button:
	var result := Button.new()
	result.text = text
	result.custom_minimum_size.y = 30
	if accent: result.add_theme_stylebox_override("normal", surface(MOSS, GOLD))
	return result

static func line() -> HSeparator:
	var result := HSeparator.new()
	var style := StyleBoxLine.new()
	style.color = BRASS
	style.thickness = 1
	result.add_theme_stylebox_override("separator", style)
	return result
