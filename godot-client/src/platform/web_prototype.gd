class_name WebPrototype
extends RefCounted
## Browser-only build configuration; no credentials or connection URLs in storage.

static func configuration() -> Dictionary:
	var path := "res://data/web_prototype.json"
	if not FileAccess.file_exists(path): return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return value if value is Dictionary else {}

static func endpoint() -> String:
	return str(configuration().get("endpoint", ""))

static func prepare_preferences() -> void:
	var path := "user://eloria_hud.cfg"
	if FileAccess.file_exists(path): return
	var config := ConfigFile.new()
	config.set_value("graphics", "quality", "medium")
	config.set_value("graphics", "map_texture_quality", "half")
	config.set_value("graphics", "fps_limit", 60)
	config.set_value("graphics", "decorative_grass", false)
	config.save(path)

static func valid_endpoint(url: String) -> bool:
	if "@" in url or "#" in url or "\n" in url or "\r" in url: return false
	if url.begins_with("wss://"):
		return not url.trim_prefix("wss://").get_slice("/", 0).is_empty()
	if url.begins_with("ws://"):
		var authority := url.trim_prefix("ws://").get_slice("/", 0)
		return authority.get_slice(":", 0) in ["127.0.0.1", "localhost"] or authority.begins_with("[::1]:")
	return false

static func supports_map(map_id: String) -> bool:
	return not OS.has_feature("web") or MapRegistry.normalize_server_map_id(map_id) in configuration().get("maps", [])
