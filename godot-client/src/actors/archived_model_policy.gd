extends RefCounted
## Retired model identities stay reserved; their old visuals are unavailable.
## The index stores paths relative to assets/ instead of loadable scene fields.

const INDEX := "res://data/assets/retired_procedural_models.json"
static var _paths: Dictionary = {}
static var _loaded := false
static var _prototypes: Dictionary = {}
static var _actor_types: Dictionary = {}
static var _equipment_keys: Dictionary = {}
static var _map_copies: Dictionary = {}
static var _verified_copies: Dictionary = {}
static var _verify_mutex := Mutex.new()
static var _token := ""

static func _ensure_loaded() -> void:
	if not _loaded:
		var entries: Dictionary = {}
		var prototypes: Dictionary = {}
		var copies: Dictionary = {}
		var actor_types: Dictionary = {}
		var equipment_keys: Dictionary = {}
		if FileAccess.file_exists(INDEX):
			var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
			if value is Dictionary:
				for relative: String in (value as Dictionary).get("runtimePaths", []):
					entries["assets/" + relative] = true
				for identity: String in (value as Dictionary).get("retiredMapPrototypes", []):
					prototypes[identity] = true
				for identity: Variant in (value as Dictionary).get("retiredActorTypes", []):
					actor_types[int(identity)] = true
				for identity: String in (value as Dictionary).get("retiredEquipmentKeys", []):
					equipment_keys[identity] = true
				copies = (value as Dictionary).get("mapMeshCopies", {})
				_token = "|retired-models:" + FileAccess.get_sha256(INDEX)
		entries.make_read_only()
		prototypes.make_read_only()
		copies.make_read_only()
		actor_types.make_read_only()
		equipment_keys.make_read_only()
		_paths = entries
		_prototypes = prototypes
		_map_copies = copies
		_actor_types = actor_types
		_equipment_keys = equipment_keys
		_loaded = true

static func is_retired_path(path: String) -> bool:
	_ensure_loaded()
	var normalized := path.replace("\\", "/").simplify_path()
	if normalized.begins_with("res://"):
		normalized = normalized.trim_prefix("res://")
	else:
		var at := normalized.find("/godot-client/assets/")
		if at >= 0:
			normalized = normalized.substr(at + "/godot-client/".length())
	return _paths.has(normalized)

static func is_retired_prototype(identity: String) -> bool:
	_ensure_loaded()
	return _prototypes.has(identity)

static func is_retired_actor_type(identity: int) -> bool:
	_ensure_loaded()
	return _actor_types.has(identity)

static func is_retired_equipment(part: int, visual: int) -> bool:
	_ensure_loaded()
	return _equipment_keys.has("%d:%d" % [part, visual])

static func cache_token() -> String:
	_ensure_loaded()
	return _token

static func _repository_path(path: String) -> String:
	var normalized := ProjectSettings.globalize_path(path).replace("\\", "/").simplify_path()
	for prefix: String in ["/eloria-assets/", "/godot-client/"]:
		var at := normalized.find(prefix)
		if at >= 0: return normalized.substr(at + 1)
	return ""

static func apply_to_gltf_state(state: GLTFState, path: String) -> int:
	_ensure_loaded()
	var relative := _repository_path(path)
	var entry: Dictionary = _map_copies.get(relative, {})
	if entry.is_empty(): return 0
	_verify_mutex.lock()
	var known: bool = _verified_copies.has(relative)
	var valid: bool = bool(_verified_copies.get(relative, false))
	_verify_mutex.unlock()
	if not known:
		valid = FileAccess.get_sha256(path) == str(entry.get("sha256", ""))
		_verify_mutex.lock()
		_verified_copies[relative] = valid
		_verify_mutex.unlock()
		if not valid:
			push_warning("Retired model mesh index needs refresh for changed map: " + relative)
	if not valid: return 0
	var retired: Dictionary = {}
	for index: Variant in entry.get("meshes", []): retired[int(index)] = true
	var removed := 0
	for value: Variant in state.get_nodes():
		var node := value as GLTFNode
		if node != null and retired.has(node.mesh):
			node.mesh = -1
			removed += 1
	return removed
