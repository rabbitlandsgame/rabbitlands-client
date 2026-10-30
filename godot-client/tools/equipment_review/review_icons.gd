extends RefCounted
## Full-resolution component renders are read directly, without editor imports.

var _textures: Dictionary = {}
var _atlas := ItemAtlas.new()


func _init() -> void:
	_atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))


func icon_for(piece: Dictionary) -> Texture2D:
	var path := str(piece.get("icon", ""))
	var worn := bool(piece.get("worn", false))
	var key := path + (":worn" if worn else "")
	if _textures.has(key):
		return _textures[key] as Texture2D
	if not path.is_empty() and FileAccess.file_exists(path):
		var image := Image.load_from_file(ProjectSettings.globalize_path(path))
		if image != null and not image.is_empty():
			if worn:
				image.flip_x()
				_atlas._stamp_worn_mark(image)
			var texture := ImageTexture.create_from_image(image)
			_textures[key] = texture
			return texture
	var image_id := int(piece.get("image_id", -1))
	return (_atlas.worn_icon_for(image_id) if worn else _atlas.icon_for(image_id)) if image_id >= 0 else _atlas.placeholder_icon()


func clear() -> void:
	_textures.clear()
