extends ProgressBar
## Compact side-rail XP: inset track, softly rounded light on the fill and brass edges.
## Remains a ProgressBar so the HUD owns values, tooltips and click handling.

static var _fill_texture: GradientTexture2D
static var _label_font: FontFile
var watched := false:
	set(value):
		if watched == value:
			return
		watched = value
		queue_redraw()
var _hovered := false

func _init() -> void:
	show_percentage = false
	add_theme_stylebox_override("background", StyleBoxEmpty.new())
	add_theme_stylebox_override("fill", StyleBoxEmpty.new())
	mouse_entered.connect(_set_hovered.bind(true))
	mouse_exited.connect(_set_hovered.bind(false))
	if _fill_texture == null:
		var ramp := Gradient.new()
		ramp.offsets = PackedFloat32Array([0.0, 0.16, 0.45, 0.55, 1.0])
		ramp.colors = PackedColorArray([Color("78964a"), Color("567936"),
			Color("3f6429"), Color("355922"), Color("233f18")])
		_fill_texture = GradientTexture2D.new()
		_fill_texture.gradient = ramp
		_fill_texture.width = 2
		_fill_texture.height = 64
		_fill_texture.fill_from = Vector2(0.0, 0.0)
		_fill_texture.fill_to = Vector2(0.0, 1.0)

static func style_label(label: Label) -> void:
	# Rasterize at double resolution so enlarged HUD layouts keep clean letter edges.
	if _label_font == null:
		_label_font = ThemeDB.fallback_font.duplicate() as FontFile
		_label_font.oversampling = 2.0
	label.add_theme_font_override("font", _label_font)
	# Regular weight with a tight dark keyline, like the legacy side stats.
	label.add_theme_font_size_override("font_size", 10)
	label.add_theme_constant_override("outline_size", 2)
	label.add_theme_color_override("font_outline_color", Color("090b07"))
	label.add_theme_constant_override("shadow_offset_x", 0)
	label.add_theme_constant_override("shadow_offset_y", 1)
	label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))

func _set_hovered(value: bool) -> void:
	_hovered = value
	queue_redraw()

func _draw() -> void:
	if size.x < 4.0 or size.y < 4.0:
		return
	var rect := Rect2(Vector2.ZERO, size)
	draw_rect(rect, Color("11120c"))
	var inner := rect.grow(-1.0)
	draw_rect(inner, Color("1c2014"))
	# The fill stays inside the frame, including when a capped skill is full.
	var fraction := clampf((value - min_value) / maxf(0.001, max_value - min_value), 0.0, 1.0)
	var width := inner.size.x * fraction
	if width > 0.0:
		draw_texture_rect(_fill_texture, Rect2(inner.position, Vector2(width, inner.size.y)), false)
		# A fine dark end cap separates the progress from the recessed track.
		if width >= 1.0 and fraction < 1.0:
			draw_rect(Rect2(inner.position + Vector2(width - 1.0, 0.0),
				Vector2(1.0, inner.size.y)), Color("26351a"))
	var light := Color("ae9262") if watched or _hovered else Color("806e49")
	var shade := Color("514125") if watched or _hovered else Color("40371f")
	draw_rect(Rect2(0, 0, size.x, 1), light)
	draw_rect(Rect2(0, 1, 1, size.y - 1), light)
	draw_rect(Rect2(1, size.y - 1, size.x - 1, 1), shade)
	draw_rect(Rect2(size.x - 1, 1, 1, size.y - 2), shade)
