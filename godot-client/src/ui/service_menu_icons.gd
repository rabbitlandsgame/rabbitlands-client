extends RefCounted
## Painted 32px tiles match the original HUD's palette and brass frames.
static var _textures: Dictionary = {}

static func texture(storage: bool) -> Texture2D:
	var key := "storage" if storage else "exchange"
	if not _textures.has(key):
		var path := "res://assets/ui/menu-icons/%s.png" % key
		# Exported builds use the imported texture; fresh checkouts can read PNGs.
		var tile: Texture2D
		if ResourceLoader.exists(path):
			tile = ResourceLoader.load(path) as Texture2D
		else:
			var image := Image.load_from_file(path)
			if image != null and not image.is_empty():
				tile = ImageTexture.create_from_image(image)
		if tile == null:
			push_error("Missing service menu icon: %s" % path)
			return null
		_textures[key] = tile
	return _textures[key] as Texture2D
