class_name WebPrototype
extends RefCounted
## Browser-only build configuration; no credentials or connection URLs in storage.

static var _configuration: Dictionary = {}
static var _loaded := false

static func configuration() -> Dictionary:
	if _loaded: return _configuration
	_loaded = true
	var path := "res://data/web_prototype.json"
	if not FileAccess.file_exists(path): return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_configuration = value if value is Dictionary else {}
	return _configuration

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

static func _service() -> Node:
	var tree := Engine.get_main_loop() as SceneTree
	return tree.root.get_node_or_null("BrowserAssetService") if tree != null else null

static func model_groups(model_id: String) -> Array:
	return configuration().get("model_groups", {}).get(model_id, [])

static func equipment_groups(visuals: Dictionary) -> Array:
	var out: Array = []
	var catalog: Dictionary = configuration().get("equipment_groups", {})
	for part: Variant in visuals:
		for group: String in catalog.get("%s:%s" % [part, visuals[part]], []):
			if not out.has(group): out.append(group)
	return out

static func ensure_groups(ids: Array, owner := "") -> bool:
	if not OS.has_feature("web"): return true
	var service := _service()
	return service != null and bool(service.call("ensure_groups", ids, owner))

static func pin_groups(owner: String, ids: Array) -> void:
	if not OS.has_feature("web"): return
	var service := _service()
	if service != null: service.call("pin_groups", owner, ids)

static func release_groups(owner: String) -> void:
	var service := _service() if OS.has_feature("web") else null
	if service != null: service.call("release_groups", owner)

static func map_groups(map_id: String) -> Array:
	var maps: Variant = configuration().get("maps", {})
	var normalized := MapRegistry.normalize_server_map_id(map_id)
	return maps.get(normalized, []) if maps is Dictionary else ["startup"]

static func ensure_map(map_id: String, owner := "") -> bool:
	return ensure_groups(map_groups(map_id), owner)

static func pin_maps(owner: String, ids: Array) -> void:
	var out: Array = []
	for map_id: String in ids:
		for group: String in map_groups(map_id):
			if not out.has(group): out.append(group)
	pin_groups(owner, out)

static func asset_snapshot() -> Dictionary:
	var service := _service() if OS.has_feature("web") else null
	return service.call("snapshot") if service != null else {}
