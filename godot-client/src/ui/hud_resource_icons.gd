extends RefCounted
## Small vector emblems in the existing UI icon format. Source fallback also
## supports running a checkout before the editor imports its new SVG files.
static var _cache: Dictionary = {}
static var _tinted: Dictionary = {}

static func icon_for(resource: String) -> Texture2D:
	if _cache.has(resource): return _cache[resource]
	var path := "res://assets/ui/resources/%s.svg" % resource
	var texture: Texture2D
	if ResourceLoader.exists(path): texture = load(path) as Texture2D
	if texture == null and FileAccess.file_exists(path):
		var source := Image.new()
		if source.load_svg_from_string(FileAccess.get_file_as_string(path)) == OK:
			texture = ImageTexture.create_from_image(source)
	_cache[resource] = texture
	return texture

static func tinted_icon(resource: String, color: Color) -> Texture2D:
	var key := resource + color.to_html()
	if _tinted.has(key): return _tinted[key]
	var base := icon_for(resource)
	if base == null: return null
	var pixels := base.get_image()
	if pixels.is_compressed(): pixels.decompress()
	pixels.convert(Image.FORMAT_RGBA8)
	for y: int in pixels.get_height():
		for x: int in pixels.get_width():
			var original := pixels.get_pixel(x, y)
			# Keep the emblem's shading, replace its hue rather than multiplying it.
			var light := maxf(original.r, maxf(original.g, original.b))
			var tint := color.darkened((1 - light) * 0.65)
			if minf(original.r, minf(original.g, original.b)) > 0.85: tint = color.lightened(0.3)
			tint.a = original.a * color.a
			pixels.set_pixel(x, y, tint)
	if _tinted.size() >= 128: _tinted.clear()
	var texture := ImageTexture.create_from_image(pixels)
	_tinted[key] = texture
	return texture
