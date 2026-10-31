extends RefCounted
## Moonlit Slate: shared live controls, with artwork from the approved UI atlas.
## Atlas regions contain illustration only; labels and controls remain native.

const TEXT := Color("eee9dc")
const MUTED := Color("a6b6c5")
const EDGE := Color("526a7e")
const TEAL := Color("65c8df")
const SURFACE := Color("101b27")
const ATLAS := "res://assets/ui/jukebox/moonlit-slate.png"
const COVERS := {
	"rising_moon": Rect2(268, 332, 48, 48),
	"home_town": Rect2(238, 396, 54, 52),
	"the_bard_s_tale": Rect2(238, 462, 54, 51),
	"a_warm_fireplace": Rect2(238, 528, 54, 51),
	"cave_theme": Rect2(238, 594, 54, 49),
}
static var _art: Texture2D
static var _icons: Dictionary = {}

static func box(color := SURFACE, edge := EDGE, margin := 9.0, radius := 4) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = edge
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.set_content_margin_all(margin)
	return style

static func frame() -> StyleBoxFlat:
	var style := box(Color("0b141e"), Color("6b8295"), 7.0, 6)
	style.set_border_width_all(2)
	style.shadow_color = Color(0, 0, 0, 0.65)
	style.shadow_size = 8
	return style

static func selected() -> StyleBoxFlat:
	return box(Color("1d4052"), TEAL, 7.0)

static func theme() -> Theme:
	var value := Theme.new()
	value.default_font_size = 15
	for kind: String in ["Label", "Button", "OptionButton", "CheckBox", "CheckButton", "LineEdit", "SpinBox", "PopupMenu", "ItemList"]:
		value.set_color("font_color", kind, TEXT)
		value.set_color("font_hover_color", kind, Color.WHITE)
		value.set_color("font_pressed_color", kind, Color.WHITE)
		value.set_color("font_disabled_color", kind, Color("647482"))
	for kind: String in ["Button", "OptionButton", "LineEdit", "SpinBox"]:
		value.set_stylebox("normal", kind, box(Color("172532"), Color("4b6073"), 8))
		value.set_stylebox("hover", kind, box(Color("223a4a"), Color("7b9bae"), 8))
		value.set_stylebox("pressed", kind, selected())
		value.set_stylebox("disabled", kind, box(Color("14212b"), Color("2b3d4b"), 8))
		var focus := box(Color.TRANSPARENT, TEAL, 0)
		focus.draw_center = false
		value.set_stylebox("focus", kind, focus)
	value.set_stylebox("panel", "AcceptDialog", frame())
	value.set_stylebox("panel", "PanelContainer", box())
	value.set_stylebox("panel", "PopupMenu", box(Color("142432"), EDGE, 8))
	value.set_stylebox("hover", "PopupMenu", selected())
	value.set_color("font_uneditable_color", "LineEdit", MUTED)
	value.set_color("font_placeholder_color", "LineEdit", MUTED)
	value.set_color("caret_color", "LineEdit", TEAL)
	value.set_color("font_color", "ItemList", MUTED)
	value.set_color("font_selected_color", "ItemList", Color.WHITE)
	value.set_stylebox("panel", "ItemList", box(Color("101c29"), Color("263a4b"), 4))
	value.set_stylebox("selected", "ItemList", selected())
	value.set_stylebox("selected_focus", "ItemList", selected())
	value.set_stylebox("hovered", "ItemList", box(Color("1a3041"), Color("385365"), 7))
	value.set_constant("v_separation", "ItemList", 10)
	value.set_constant("icon_margin", "ItemList", 12)
	value.set_constant("line_separation", "ItemList", 3)
	value.set_stylebox("scroll", "VScrollBar", box(Color("0c1722"), Color.TRANSPARENT, 2))
	value.set_stylebox("grabber", "VScrollBar", box(Color("526779"), Color.TRANSPARENT, 3, 3))
	value.set_stylebox("grabber_highlight", "VScrollBar", box(TEAL, Color.TRANSPARENT, 3, 3))
	value.set_constant("scroll_border", "VScrollBar", 2)
	value.set_stylebox("slider", "HSlider", box(Color("08111b"), Color("3c5263"), 2, 2))
	value.set_stylebox("grabber_area", "HSlider", box(Color("4f9cb5"), TEAL, 2, 2))
	value.set_icon("grabber", "HSlider", icon("knob", TEAL, 14))
	value.set_icon("grabber_highlight", "HSlider", icon("knob", Color.WHITE, 14))
	value.set_icon("arrow", "OptionButton", icon("down", MUTED, 16))
	value.set_icon("checked", "CheckButton", toggle_icon(true))
	value.set_icon("unchecked", "CheckButton", toggle_icon(false))
	value.set_icon("checked_disabled", "CheckButton", toggle_icon(false))
	value.set_icon("unchecked_disabled", "CheckButton", toggle_icon(false))
	for kind: String in ["CheckBox", "CheckButton"]:
		for state: String in ["normal", "hover", "pressed", "disabled", "hover_pressed"]:
			value.set_stylebox(state, kind, StyleBoxEmpty.new())
	return value

static func serif() -> Font:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Georgia", "Noto Serif", "DejaVu Serif", "serif"])
	font.font_weight = 600
	return font

static func art(region: Rect2) -> Texture2D:
	if _art == null:
		_art = load(ATLAS) as Texture2D
	var texture := AtlasTexture.new()
	texture.atlas = _art
	texture.region = region
	return texture

static func cover(track: String) -> Texture2D:
	var region: Rect2 = COVERS.get(track, COVERS.rising_moon)
	if track.contains("town") or track in ["settlement", "bazaar"]: region = COVERS.home_town
	elif track.contains("dungeon") or track in ["depths", "forgoten_tomb_ambience"]: region = COVERS.cave_theme
	elif track in ["the_old_tower_inn", "king_s_feast"]: region = COVERS.the_bard_s_tale
	return art(region)

static func icon(key: String, color := TEXT, pixels := 22) -> Texture2D:
	var cache_key := "%s:%s:%d" % [key, color.to_html(), pixels]
	if _icons.has(cache_key): return _icons[cache_key]
	var paths := {
		"play": '<path d="M8 5L19 12L8 19Z" fill="currentColor" stroke="none"/>',
		"pause": '<path d="M8 6V18M16 6V18" stroke-width="4"/>',
		"previous": '<path d="M6 5V19M18 6L8 12L18 18Z"/><path d="M18 6L8 12L18 18Z" fill="currentColor" stroke="none"/>',
		"next": '<path d="M18 5V19M6 6L16 12L6 18Z"/><path d="M6 6L16 12L6 18Z" fill="currentColor" stroke="none"/>',
		"shuffle": '<path d="M3 6H6C10 6 14 18 18 18H21M17 14L21 18L17 22M3 18H6C8 18 9 15 10 13M14 8C16 6 17 6 21 6M17 2L21 6L17 10"/>',
		"repeat": '<path d="M5 8C6 5 9 5 17 5H20M16 1L20 5L16 9M19 16C18 19 15 19 7 19H4M8 15L4 19L8 23"/>',
		"one": '<path d="M5 8C6 5 9 5 17 5H20M16 1L20 5L16 9M19 16C18 19 15 19 7 19H4M8 15L4 19L8 23M11 10L13 9V15"/>',
		"volume": '<path d="M3 9H7L12 5V19L7 15H3ZM16 8C19 10 19 14 16 16M19 5C24 9 24 15 19 19"/>',
		"muted": '<path d="M3 9H7L12 5V19L7 15H3ZM17 9L23 15M23 9L17 15"/>',
		"expand": '<path d="M14 3H21V10M21 3L13 11M10 21H3V14M3 21L11 13"/>',
		"search": '<circle cx="10" cy="10" r="6.5"/><path d="M15 15L21 21"/>',
		"library": '<path d="M9 17V5L20 3V15M9 8L20 6"/><ellipse cx="6" cy="18" rx="3" ry="2" fill="currentColor"/><ellipse cx="17" cy="16" rx="3" ry="2" fill="currentColor"/>',
		"playlist": '<path d="M8 5H21M8 11H21M8 17H17M3 4V6M3 10V12M3 16V18"/>',
		"rules": '<path d="M9 3L15 3L16 6L19 7L22 11L20 14L18 14L17 19L13 22L9 20L8 18L4 17L2 12L5 8L7 8Z"/><circle cx="12" cy="12" r="3.5"/>',
		"game": '<path d="M7 7H17C21 7 23 18 20 18L16 14H8L4 18C1 18 3 7 7 7ZM6 9V13M4 11H8M16 10H16.1M19 12H19.1"/>',
		"moon": '<path d="M18 3C13 5 12 12 16 16C18 18 20 18 22 17C19 23 10 24 5 18C0 12 4 3 10 2C9 8 11 13 16 14"/>',
		"close": '<path d="M5 5L19 19M19 5L5 19"/>',
		"up": '<path d="M5 15L12 8L19 15"/>',
		"down": '<path d="M5 9L12 16L19 9"/>',
		"plus": '<path d="M12 4V20M4 12H20"/>',
		"remove": '<path d="M4 12H20"/>',
		"check": '<path d="M4 12L9 17L21 5"/>',
		"grip": '<path d="M8 5H8.1M16 5H16.1M8 12H8.1M16 12H16.1M8 19H8.1M16 19H16.1" stroke-width="3.5"/>',
		"dots": '<path d="M4 12H4.1M12 12H12.1M20 12H20.1" stroke-width="3"/>',
		"knob": '<circle cx="12" cy="12" r="9" fill="currentColor" stroke="#bfd8e2"/>',
	}
	var ink := "#" + color.to_html(false)
	var svg := '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 24 24"><g fill="none" stroke="%s" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">%s</g></svg>' % [pixels, pixels, ink, paths.get(key, paths.playlist)]
	svg = svg.replace("currentColor", ink)
	var image := Image.new()
	image.load_svg_from_string(svg)
	var texture := ImageTexture.create_from_image(image)
	_icons[cache_key] = texture
	return texture

static func toggle_icon(on: bool) -> Texture2D:
	var image := Image.new()
	image.load_svg_from_string('<svg xmlns="http://www.w3.org/2000/svg" width="36" height="20"><rect x="1" y="2" width="34" height="16" rx="8" fill="%s" stroke="#78a6b8"/><circle cx="%d" cy="10" r="7" fill="#eef0e7"/></svg>' % ["#17819a" if on else "#2b3c49", 26 if on else 10])
	return ImageTexture.create_from_image(image)

static func texture_rect(texture: Texture2D, minimum: Vector2) -> TextureRect:
	var control := TextureRect.new()
	control.texture = texture
	control.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	control.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	control.custom_minimum_size = minimum
	control.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return control

static func button(parent: Node, text: String, glyph: String, callback: Callable, primary := false) -> Button:
	var control := Button.new()
	control.text = text
	if not glyph.is_empty(): control.icon = icon(glyph)
	control.add_theme_constant_override("h_separation", 8)
	control.custom_minimum_size.y = 34
	control.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	control.pressed.connect(callback)
	if primary: control.add_theme_stylebox_override("normal", selected())
	parent.add_child(control)
	return control
