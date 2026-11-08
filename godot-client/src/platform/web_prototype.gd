class_name WebPrototype
extends RefCounted
## Browser-only build configuration; no credentials or connection URLs in storage.

static var _configuration: Dictionary = {}
static var _loaded := false
static var _mount_group_cache: Dictionary = {}
static var _model_sources: Dictionary = {}
static var _model_sources_loaded := false
static var _source_path_lists: Dictionary = {}

static func configuration() -> Dictionary:
	if _loaded: return _configuration
	_loaded = true
	var path := "res://data/web_prototype.json"
	if not FileAccess.file_exists(path): return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_configuration = value if value is Dictionary else {}
	if OS.has_feature("web"):
		# This performance switch changes scheduling only. A private benchmark
		# can compare the same export without changing its package or art.
		var preparation: Variant = JSON.parse_string(str(JavaScriptBridge.eval(
			"JSON.stringify(window.RL_BROWSER_ASSETS?.browser_actor_preparation ?? null)")))
		if typeof(preparation) == TYPE_BOOL:
			_configuration["browser_actor_preparation"] = preparation
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

static func source_paths(prefix: String) -> PackedStringArray:
	if not _source_path_lists.has(prefix):
		var paths := PackedStringArray()
		for source: String in configuration().get("source_groups", {}):
			if source.begins_with(prefix): paths.append(source)
		paths.sort()
		_source_path_lists[prefix] = paths
	return (_source_path_lists[prefix] as PackedStringArray).duplicate()

static func file_groups(paths: PackedStringArray) -> Array:
	var groups: Array = []
	var catalog: Dictionary = configuration().get("source_groups", {})
	for source: String in paths:
		for group: String in catalog.get(source, []):
			if not groups.has(group): groups.append(group)
	return groups

static func appearance_groups(model_config: Dictionary, appearance: Dictionary, quality: int) -> Array:
	# Potential paths come from the same selection policy as the body, before
	# the lazy source files exist. Older catalogs keep these files in startup.
	var paths := ReplicatedActor3D.rl_hair_only_files_for(model_config, appearance, quality, false)
	paths.append_array(ReplicatedActor3D.rl_head_files_for(model_config, appearance, quality, false))
	return file_groups(paths)

static func group_failure(ids: Array, state: Dictionary = {}) -> String:
	if state.is_empty(): state = asset_snapshot()
	var failed: Array = state.get("failed_groups", [])
	if failed.is_empty(): return ""
	var queue := ids.duplicate()
	var seen := {}
	var groups: Dictionary = configuration().get("groups", {})
	while not queue.is_empty():
		var id := str(queue.pop_back())
		if seen.has(id): continue
		seen[id] = true
		if failed.has(id):
			var message := str(state.get("error", ""))
			return message if not message.is_empty() else "Game files could not be prepared."
		queue.append_array((groups.get(id, {}) as Dictionary).get("dependencies", []))
	return ""

static func _load_model_sources() -> void:
	if _model_sources_loaded: return
	_model_sources_loaded = true
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	if registry is Dictionary:
		for id: String in registry.get("models", {}):
			var scene := str(registry.models[id].get("scene", ""))
			if not model_groups(id).is_empty() and not _model_sources.has(scene): _model_sources[scene] = id

static func scene_groups(source: String) -> Array:
	_load_model_sources()
	return model_groups(str(_model_sources.get(source, "")))

static func mount_groups(mount_id: String) -> Array:
	if _mount_group_cache.has(mount_id): return _mount_group_cache[mount_id]
	var out := model_groups(mount_id).duplicate()
	var profile: Dictionary = preload("res://src/mounts/mount_profiles.gd").read(mount_id)
	var source := str((profile.get("borrowedTack", {}) as Dictionary).get("source", ""))
	if not source.is_empty():
		for group: String in scene_groups(source):
			if not out.has(group): out.append(group)
	_mount_group_cache[mount_id] = out
	return out

static func equipment_groups(visuals: Dictionary) -> Array:
	var out: Array = []
	var catalog: Dictionary = configuration().get("equipment_groups", {})
	for part: Variant in visuals:
		for group: String in catalog.get("%s:%s" % [part, visuals[part]], []):
			if not out.has(group): out.append(group)
	return out

static func ensure_groups(ids: Array, owner := "", priority := -1) -> bool:
	if not OS.has_feature("web"): return true
	var service := _service()
	return service != null and bool(service.call("ensure_groups", ids, owner, priority))

static func pin_groups(owner: String, ids: Array) -> void:
	if not OS.has_feature("web"): return
	var service := _service()
	if service != null: service.call("pin_groups", owner, ids)

static func release_groups(owner: String) -> void:
	var service := _service() if OS.has_feature("web") else null
	if service != null: service.call("release_groups", owner)

static func retire_groups(owner: String) -> void:
	# A portrait node can retire before the head library finishes reading files.
	# The static coroutine survives that node and owns only its unique pin name.
	if not OS.has_feature("web"): return
	var tree := Engine.get_main_loop() as SceneTree
	while tree != null and RLHeadLibrary.warming():
		await tree.create_timer(0.1).timeout
	release_groups(owner)

static func map_groups(map_id: String) -> Array:
	var maps: Variant = configuration().get("maps", {})
	var normalized := MapRegistry.normalize_server_map_id(map_id)
	return maps.get(normalized, []) if maps is Dictionary else ["startup"]

static func ensure_map(map_id: String, owner := "") -> bool:
	return ensure_groups(map_groups(map_id), owner)

static func map_ready(map_id: String) -> bool:
	if not OS.has_feature("web"): return true
	var service := _service()
	return service != null and bool(service.call("groups_ready", map_groups(map_id)))

static func pin_maps(owner: String, ids: Array) -> void:
	var out: Array = []
	for map_id: String in ids:
		for group: String in map_groups(map_id):
			if not out.has(group): out.append(group)
	pin_groups(owner, out)

static func asset_snapshot() -> Dictionary:
	var service := _service() if OS.has_feature("web") else null
	return service.call("snapshot") if service != null else {}

static func retry_failed() -> int:
	var service := _service() if OS.has_feature("web") else null
	return int(service.call("retry_failed")) if service != null else 0
