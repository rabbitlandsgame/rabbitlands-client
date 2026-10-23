extends Control
## Generated metalwork surrounds a real, cached character portrait. Initials
## remain the honest fallback when the server has no appearance to provide.
const Art := preload("res://src/ui/leaderboard_art.gd")
const Circle := preload("res://src/ui/leaderboard_circle.gdshader")
var player_name := ""
var rank := 1
var metal := Color("e1b862")
var look: Dictionary = {}
var portraits: Node
var _portrait: TextureRect
var _frame: TextureRect
var _number: Label
var _key := ""

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if custom_minimum_size == Vector2.ZERO:
		custom_minimum_size = Vector2(116, 116)
	_portrait = TextureRect.new()
	_portrait.name = "PlayerPortrait"
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.stretch_mode = TextureRect.STRETCH_SCALE
	_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var mask := ShaderMaterial.new()
	mask.shader = Circle
	_portrait.material = mask
	add_child(_portrait)
	_frame = TextureRect.new()
	_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_frame.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_frame.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	if rank in [1, 2, 3]:
		_frame.texture = Art.texture(["gold-medallion-v2", "silver-medallion-v2", "bronze-medallion-v2"][rank - 1])
	add_child(_frame)
	_number = Label.new()
	_number.text = str(rank) if rank > 0 else ""
	_number.add_theme_font_override("font", Art.title_font())
	_number.add_theme_color_override("font_color", Color("fff0ca") if rank != 2 else Color("f0f5ff"))
	_number.add_theme_color_override("font_outline_color", Color("241c18"))
	_number.add_theme_constant_override("outline_size", 3)
	_number.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_number.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_number.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_number)
	resized.connect(_layout)
	if portraits != null and not look.is_empty():
		_key = portraits.cache_key(look)
		portraits.portrait_ready.connect(_on_portrait_ready)
		_portrait.texture = portraits.request(look)
	_layout()

func _on_portrait_ready(key: String, texture: Texture2D) -> void:
	if key == _key:
		_portrait.texture = texture
		queue_redraw()

func _layout() -> void:
	if _portrait == null:
		return
	var side := minf(size.x, size.y)
	var origin := Vector2((size.x - side) * 0.5, 0)
	var center := origin + Vector2(side * 0.5, side * 0.44)
	var radius: float = side * ([0.307, 0.292, 0.298][rank - 1] if rank in [1, 2, 3] else 0.48)
	if rank == 0:
		center.y = side * 0.5
	_portrait.position = center - Vector2.ONE * radius
	_portrait.size = Vector2.ONE * radius * 2
	_frame.position = origin
	_frame.size = Vector2.ONE * side
	_number.add_theme_font_size_override("font_size", maxi(17, int(side * 0.17)))
	_number.position = origin + Vector2(side * 0.35, side * 0.755)
	_number.size = Vector2(side * 0.30, side * 0.15)
	queue_redraw()

func _draw() -> void:
	var side := minf(size.x, size.y)
	var center := Vector2(size.x * 0.5, side * (0.5 if rank == 0 else 0.44))
	var radius := side * (0.48 if rank == 0 else 0.303)
	draw_circle(center, radius, Color("17212d"))
	if rank == 0:
		draw_arc(center, radius, 0, TAU, 40, metal, 1.0, true)
	if _portrait == null or _portrait.texture == null:
		var font := ThemeDB.fallback_font
		var initials := player_name.left(2).to_upper() if not player_name.is_empty() else "—"
		var font_size := maxi(9, int(side * (0.36 if rank == 0 else 0.19)))
		var width := font.get_string_size(initials, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
		draw_string(font, center + Vector2(-width / 2, font_size * 0.32), initials,
			HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color("e9dec6"))
