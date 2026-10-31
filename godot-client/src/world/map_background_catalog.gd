extends RefCounted
## Prerendered navigation images. Secret rooms never fall back to an aggregate
## image; an unknown room produces no background until its section is known.

const INDEX := "res://data/maps/map-backgrounds.json"
const CACHE_ENTRIES := 3
var _loaded := false
var _index: Dictionary = {}
var _textures: Dictionary = {}

static func select_entry(index: Dictionary, map_id: String, section := "") -> Dictionary:
	var alias_value: Variant = index.get("aliases", {})
	var map_value: Variant = index.get("maps", {})
	if not alias_value is Dictionary or not map_value is Dictionary:
		return {}
	var aliases: Dictionary = alias_value
	var name := MapRegistry.normalize_server_map_id(map_id)
	var seen := {}
	while aliases.has(name):
		if seen.has(name):
			return {}
		seen[name] = true
		name = str(aliases[name])
	var value: Variant = map_value.get(name, {})
	if not value is Dictionary:
		return {}
	var row: Dictionary = value
	var sections: Variant = row.get("sections", {})
	if not sections is Dictionary:
		return {}
	if bool(row.get("sectioned", false)) or not sections.is_empty():
		var selected: Variant = sections.get(section, {})
		if not selected is Dictionary:
			return {}
		row = selected
	return row if not str(row.get("path", "")).is_empty() else {}

func picture(map_id: String, section: String, height: float) -> Dictionary:
	if not _loaded:
		_loaded = true
		if FileAccess.file_exists(INDEX):
			var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
			if parsed is Dictionary and parsed.get("schemaVersion") == 1:
				_index = parsed
	var row := select_entry(_index, map_id, section)
	if row.is_empty():
		return {}
	var low: Array = row.get("worldMin", [])
	var high: Array = row.get("worldMax", [])
	if low.size() != 2 or high.size() != 2:
		return {}
	var extent := Rect2(Vector2(float(low[0]), float(low[1])),
		Vector2(float(high[0]) - float(low[0]), float(high[1]) - float(low[1])))
	if extent.size.x <= 0.0 or extent.size.y <= 0.0:
		return {}
	var path := str(row.path)
	var texture: Texture2D
	if _textures.has(path):
		texture = _textures[path]
		_textures.erase(path)
	else:
		var image := Image.new()
		if image.load(ProjectSettings.globalize_path(path)) != OK or image.is_empty():
			return {}
		image.generate_mipmaps()
		texture = ImageTexture.create_from_image(image)
	_textures[path] = texture
	while _textures.size() > CACHE_ENTRIES:
		_textures.erase(_textures.keys()[0])
	return {"texture": texture, "extent": extent, "height": height,
		"transform": Transform3D.IDENTITY}
