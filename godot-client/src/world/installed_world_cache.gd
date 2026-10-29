extends RefCounted
## SHA-bound, read-only release preparation. Loose metadata never establishes
## source/payload acceptance: existing family readers still verify those bytes.
const Vram := preload("res://src/world/vram_textures.gd")
const POLICY := "rabbitlands-installed-world-v1"
const DESCRIPTOR := "res://data/maps/prepared-world.json"
const ROOT := "res://prepared-world"
const MAX_METADATA_BYTES := 16777216
const FAMILIES := ["geometry", "collision", "paving"]
static var _loaded := false
static var _catalogs: Array[Dictionary] = []
static var _mutex := Mutex.new()

static func _hash(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

static func _digest(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()

static func compatibility(geometry_policy: String, collision_policy: String,
		paving_policy: String, platform := OS.get_name()) -> String:
	return _digest(JSON.stringify([POLICY, geometry_policy, collision_policy,
		paving_policy, platform], "", true, true).to_utf8_buffer())

static func declared() -> bool:
	return FileAccess.file_exists(DESCRIPTOR)

static func release_blob_directory(path: String, expected_policy := "") -> bool:
	var prefix := ROOT + "/"
	if not path.begins_with(prefix) or path != path.replace("\\", "/").simplify_path(): return false
	var parts := path.substr(prefix.length()).split("/")
	return parts.size() == 4 and _hash(parts[0]) and parts[1] == "geometry" and _hash(parts[2]) \
		and parts[3] == "blobs" and (expected_policy.is_empty() or parts[2] == expected_policy)

static func _relative(value: Variant) -> bool:
	if not value is String or value.is_empty() or value.is_absolute_path() \
			or ":" in value or "\\" in value or "%" in value: return false
	if value != value.simplify_path(): return false
	for part: String in value.split("/"):
		if part in ["", ".", ".."]: return false
	return true

static func _read(path: String, expected := "", expected_bytes := -1) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() > MAX_METADATA_BYTES \
			or (expected_bytes >= 0 and file.get_length() != expected_bytes): return {}
	var bytes := file.get_buffer(file.get_length())
	if not expected.is_empty() and _digest(bytes) != expected: return {}
	var value: Variant = JSON.parse_string(bytes.get_string_from_utf8())
	return value if value is Dictionary else {}

static func _engine() -> Dictionary:
	var info := Engine.get_version_info()
	return {"hash": str(info.get("hash", "")), "string": str(info.get("string", ""))}

static func _file_path(relative: String, family: String, policy: String, folder: String) -> bool:
	if not _relative(relative): return false
	var parts := relative.split("/")
	if parts.size() != 4 or parts[0] != family or parts[1] != policy or parts[2] != folder: return false
	if not _hash(parts[3].get_basename()): return false
	return parts[3].get_extension() in (["json"] if folder == "entries" else (["rlc"] if family == "collision" else (["res"] if family == "paving" else ["res", "scn"])))

static func _validate_catalog(value: Dictionary, identity: String) -> bool:
	if value.get("schema") != 1 or value.get("policy") != POLICY \
			or value.get("compatibility") != identity or value.get("platform") != OS.get_name() \
			or value.get("renderer") != RenderingServer.get_current_rendering_method() \
			or value.get("engine") != _engine(): return false
	for family: String in FAMILIES:
		if not _hash(value.get(family + "_policy")): return false
	if compatibility(value.geometry_policy, value.collision_policy, value.paving_policy) != identity: return false
	if not _hash(value.get("scope_sha256")) or not _hash(value.get("registry_sha256")): return false
	var targets: Variant = value.get("targets")
	var files: Variant = value.get("files")
	var keys: Variant = value.get("target_keys")
	if not targets is Dictionary or targets.is_empty() or targets.size() > 8192 \
			or not files is Dictionary or files.is_empty() or files.size() > 65536 or not keys is Array: return false
	var actual: Array = targets.keys()
	actual.sort()
	if keys != actual: return false
	for name: Variant in files:
		if not name is String or not _relative(name): return false
		var item: Variant = files[name]
		if not item is Dictionary or not _hash(item.get("sha256")) \
				or (not item.get("bytes") is float and not item.get("bytes") is int): return false
		if not is_finite(float(item.bytes)) or float(item.bytes) <= 0 or float(item.bytes) > 2147483648.0 \
				or float(item.bytes) != float(int(item.bytes)): return false
		var parts: PackedStringArray = name.split("/")
		if parts.size() != 4 or not parts[0] in FAMILIES \
				or not _file_path(name, parts[0], str(value[parts[0] + "_policy"]), parts[2]) \
				or not parts[2] in ["entries", "blobs"]: return false
		if parts[2] == "blobs" and parts[3].get_basename() != str(item.sha256): return false
	for key: Variant in targets:
		if not key is String or key.get_slice_count("|") != 2 \
				or not key.get_slice("|", 0) in ["world", "asset"]: return false
		var source: String = key.get_slice("|", 1)
		if not _relative(source) or not source.begins_with("eloria-assets/") and not source.begins_with("godot-client/"): return false
		var row: Variant = targets[key]
		if not row is Dictionary or not row.has("geometry"): return false
		for family: Variant in row:
			if not family in FAMILIES or not row[family] is String \
					or not _file_path(row[family], family, str(value[family + "_policy"]), "entries") \
					or not files.has(row[family]): return false
			if key.begins_with("asset|") and family != "geometry": return false
	return true

static func _bound_catalogs(descriptor: String, directory: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var document := _read(descriptor)
	if document.get("schema") != 1 or document.get("policy") != POLICY or not document.get("variants") is Dictionary: return result
	var variants: Dictionary = document.variants
	if variants.size() > 16: return result
	for identity: Variant in variants:
		if not _hash(identity): continue
		var row: Variant = variants[identity]
		if not row is Dictionary or row.get("catalog") != str(identity) + "/catalog.json" or not _hash(row.get("sha256")): continue
		var path := directory.path_join(row.catalog)
		var catalog := _read(path, row.sha256)
		if not _validate_catalog(catalog, identity): continue
		catalog["_directory"] = directory.path_join(identity)
		result.append(catalog)
	return result

static func _available() -> Array[Dictionary]:
	# Descriptor lives in the immutable application PCK. Its exact catalog SHA
	# binds this call-owned metadata snapshot; sources and blobs are not memoized.
	_mutex.lock()
	if not _loaded:
		_catalogs = _bound_catalogs(DESCRIPTOR, Vram.runtime_absolute(ROOT))
		_loaded = true
	var result := _catalogs
	_mutex.unlock()
	return result

static func complete(policies: Dictionary, scope_sha: String, registry_sha: String, target_keys: Array) -> bool:
	for catalog: Dictionary in _available():
		var matches: bool = catalog.scope_sha256 == scope_sha and catalog.registry_sha256 == registry_sha and catalog.target_keys == target_keys
		for family: String in FAMILIES:
			matches = matches and catalog.get(family + "_policy") == policies.get(family)
		if matches: return true
	return false

static func _expand(catalog: Dictionary, relative: Variant, family: String, folder: String, expected := "") -> String:
	if not relative is String or not _file_path(relative, family, str(catalog[family + "_policy"]), folder): return ""
	var record: Variant = catalog.files.get(relative)
	if not record is Dictionary or (not expected.is_empty() and record.sha256 != expected): return ""
	return str(catalog._directory).path_join(relative)

static func _entry(catalog: Dictionary, family: String, target_key: String) -> Dictionary:
	var row: Variant = catalog.targets.get(target_key)
	if not row is Dictionary or not row.has(family): return {}
	var name: String = row[family]
	var file := _expand(catalog, name, family, "entries")
	if file.is_empty(): return {}
	var record: Dictionary = catalog.files[name]
	var value := _read(file, record.sha256, int(record.bytes))
	if value.is_empty() or value.get("source") != target_key.get_slice("|", 1) \
			or value.get("policy") != catalog[family + "_policy"]: return {}
	if family == "geometry":
		if value.get("kind") != target_key.get_slice("|", 0) or not value.get("payloads") is Dictionary or not value.get("shared_meshes", {}) is Dictionary: return {}
		var payloads := {}
		for path: Variant in value.payloads:
			if not _hash(value.payloads[path]): return {}
			var expanded := _expand(catalog, path, family, "blobs", value.payloads[path])
			if expanded.is_empty(): return {}
			payloads[expanded] = value.payloads[path]
		var primary := _expand(catalog, value.get("primary"), family, "blobs")
		if primary.is_empty() or not payloads.has(primary): return {}
		var meshes := {}
		for path: Variant in value.get("shared_meshes", {}):
			var expanded := _expand(catalog, path, family, "blobs")
			if expanded.is_empty() or not payloads.has(expanded): return {}
			meshes[expanded] = value.shared_meshes[path]
		value.primary = primary
		value.payloads = payloads
		value.shared_meshes = meshes
	elif family == "collision":
		var expanded := _expand(catalog, value.get("blob"), family, "blobs", str(value.get("sha256", "")))
		if expanded.is_empty(): return {}
		value.blob = expanded
	else:
		if not value.get("meshes") is Dictionary: return {}
		for path: Variant in value.meshes:
			var item: Variant = value.meshes[path]
			if not item is Dictionary: return {}
			var expanded := _expand(catalog, item.get("blob"), family, "blobs", str(item.get("sha256", "")))
			if expanded.is_empty(): return {}
			item.blob = expanded
	return value

static func entry(family: String, target_key: String, policy: String) -> Dictionary:
	if not family in FAMILIES: return {}
	var found := {}
	for catalog: Dictionary in _available():
		if catalog.get(family + "_policy") != policy: continue
		var candidate := _entry(catalog, family, target_key)
		if candidate.is_empty(): continue
		if not found.is_empty(): return {} # No ambiguous installed representations.
		found = candidate
	return found

static func owns_blob(path: String, family: String, policy: String, extension: String) -> bool:
	if not family in FAMILIES or path != path.replace("\\", "/").simplify_path() or path.get_extension() != extension: return false
	for catalog: Dictionary in _available():
		if catalog.get(family + "_policy") != policy: continue
		var prefix := str(catalog._directory) + "/"
		if path.begins_with(prefix) and not _expand(catalog, path.substr(prefix.length()), family, "blobs").is_empty(): return true
	return false

static func logical_blob(path: String, family: String, policy: String) -> String:
	for catalog: Dictionary in _available():
		if catalog.get(family + "_policy") != policy: continue
		var prefix := str(catalog._directory) + "/"
		if path.begins_with(prefix):
			var relative := path.substr(prefix.length())
			if not _expand(catalog, relative, family, "blobs").is_empty():
				return ROOT.path_join(catalog.compatibility).path_join(relative)
	return ""
