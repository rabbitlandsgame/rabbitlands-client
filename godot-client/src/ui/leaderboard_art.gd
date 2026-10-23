extends RefCounted
## Shared retained artwork and native, scalable gilded borders.
const ROOT := "res://assets/ui/leaderboards/"
static var _textures: Dictionary = {}
static var _font: SystemFont

static func texture(path: String) -> Texture2D:
	var source := path if path.begins_with("res://") else ROOT + path + ".png"
	if _textures.has(source):
		return _textures[source]
	var result: Texture2D
	if ResourceLoader.exists(source, "Texture2D"):
		result = load(source) as Texture2D
	else:
		var image := Image.load_from_file(source)
		if image != null and not image.is_empty():
			image.generate_mipmaps()
			result = ImageTexture.create_from_image(image)
	_textures[source] = result
	return result

static func title_font() -> Font:
	if _font == null:
		_font = SystemFont.new()
		_font.font_names = PackedStringArray(["Georgia", "DejaVu Serif"])
		_font.font_weight = 700
	return _font

static func subject(key: String) -> Texture2D:
	var icon := SubjectIcons.icon_for(key)
	if icon is AtlasTexture:
		var inset := AtlasTexture.new()
		inset.atlas = icon.atlas
		inset.region = icon.region.grow(-3)
		return inset
	return icon

static func frame(canvas: Control, metal: Color, elaborate := true) -> void:
	var bounds := Rect2(Vector2(3, 3), canvas.size - Vector2(6, 6))
	if bounds.size.x < 20 or bounds.size.y < 20:
		return
	canvas.draw_rect(bounds, Color(metal, 0.35), false, 1)
	for corner: Vector2 in [bounds.position, Vector2(bounds.end.x, bounds.position.y), bounds.end, Vector2(bounds.position.x, bounds.end.y)]:
		var direction := Vector2(1 if corner.x == bounds.position.x else -1, 1 if corner.y == bounds.position.y else -1)
		var p := corner + direction * 2
		canvas.draw_polyline(PackedVector2Array([p + Vector2(0, direction.y * 23), p, p + Vector2(direction.x * 23, 0)]), metal, 1.7, true)
		if elaborate:
			canvas.draw_colored_polygon(PackedVector2Array([p, p + Vector2(direction.x * 11, direction.y * 4),
				p + direction * 8, p + Vector2(direction.x * 4, direction.y * 11)]), metal.darkened(0.13))
			canvas.draw_arc(p + direction * 15, 7, 0, TAU * 0.73, 16, Color(metal, 0.65), 1.0, true)
