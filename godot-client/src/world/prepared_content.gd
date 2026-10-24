extends RefCounted
const OptimizationProfile := preload("res://src/runtime/optimization_profile.gd")
## Optional native-resource path. This is an exact-variant catalog, not a
## claim that a PackedScene containing textures is independent of texture policy.
## Every consumed source/payload is hashed on each lookup. No timestamp cache,
## source-hash bypass, or sealed-generation claim is introduced here.
const MapCache := preload("res://src/world/map_scene_cache.gd")
const Archived := preload("res://src/actors/archived_model_policy.gd")
const Diagnostics := preload("res://src/world/resource_diagnostics.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const TextureSizes := preload("res://src/world/prepared_texture_sizes.gd")
const AnimationKeys := preload("res://src/world/prepared_animation_keys.gd")
static func node_policy() -> String:
	var policy := OptimizationProfile.selected("prepared_node_policy")
	return "lazy-source-v1" if policy == "lazy-source-v1" else "retain"

const SCHEMA := 1
const COOK_POLICY := "rabbitlands-native-prepared-v2"
const CATALOG := "res://prepared-content/index.json"
const ENVIRONMENT := "RABBITLANDS_PREPARED_CONTENT"
const ARGUMENT := "--prepared-content="
const MODES := ["raw", "auto", "require-pilot"]
static var _mutex := Mutex.new()
static var _timings: Dictionary = {}
static var _hits := 0
static var _misses: Dictionary = {}
static var _consumed: Dictionary = {}

static func selected_mode() -> String:
	var selected := OptimizationProfile.selected("prepared_content")
	return selected if selected in MODES else "raw"

static func engine_policy() -> Dictionary:
	var version := Engine.get_version_info()
	return {"major": int(version.major), "minor": int(version.minor),
		"patch": int(version.patch), "hash": str(version.get("hash", "")),
		"cook_policy": COOK_POLICY, "map_cache_format": MapCache.CACHE_FORMAT_VERSION,
		"retired_policy": Archived.cache_token()}

static func _canonical_json(value: Variant) -> String:
	# Outer entry fields contain integers/strings only. Rig/animation float
	# metadata remains an opaque metadata_json String across all serializers.
	var wire: Variant = JSON.parse_string(JSON.stringify(value, "", true, true))
	return JSON.stringify(wire, "", true, true)

static func encode_metadata(metadata: Dictionary) -> String:
	# This exact String is authoritative. Python merge/install must never parse
	# and reserialize its numbers into a different entry identity.
	return JSON.stringify(metadata, "", true, true)

static func entry_identity(entry: Dictionary) -> String:
	var identity := entry.duplicate(true)
	identity.erase("entry_id")
	# acquire() rejects a stored alias before hashing. Only a verified returned
	# entry may carry this decoded convenience view for existing consumers.
	if identity.has("metadata_json"):
		if identity.has("metadata"):
			var parser := JSON.new()
			if not identity.metadata_json is String or parser.parse(str(identity.metadata_json)) != OK \
					or not parser.data is Dictionary or identity.metadata != parser.data:
				return ""
		identity.erase("metadata")
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(_canonical_json(identity).to_utf8_buffer())
	return hashing.finish().hex_encode()

static func scene_texture_token(source: String) -> String:
	# Imported equipment products are verified through the explicit input
	# closure. Embedded actor/world-image policy differs from map sidecars.
	var world := logical_source(source).begins_with("godot-client/assets/world/")
	return "scene-images-v1|%s|skip=%d|formats=%d|mode=%s" % [
		"world-preupload-mips" if world else "actor-runtime-import",
		Graphics.active_texture_skip(), Vram.usable_formats(), Vram.mode_name()]

static func _resource_root(globalized: String, executable: String) -> String:
	# A template mounted from its PCK can have an empty resource_path. Godot
	# then globalizes res://foo to relative foo, unlike an editor project.
	var root := globalized.replace("\\", "/").simplify_path()
	if root.is_empty() or not root.is_absolute_path() or root.begins_with("res://"):
		root = executable.replace("\\", "/").get_base_dir().simplify_path()
	return root.trim_suffix("/")

static func _project_root() -> String:
	return _resource_root(ProjectSettings.globalize_path("res://"), OS.get_executable_path())

static func _runtime_absolute(path: String) -> String:
	var project_root := _project_root()
	if path.begins_with("res://"):
		return project_root.path_join(path.trim_prefix("res://")).replace("\\", "/").simplify_path()
	var absolute := ProjectSettings.globalize_path(path).replace("\\", "/").simplify_path()
	return absolute if absolute.is_absolute_path() else project_root.path_join(absolute).simplify_path()

static func logical_source(path: String) -> String:
	# Isolated user storage may physically live inside a project during tests.
	# Preserve its explicit logical namespace before checking physical roots.
	if path.begins_with("user://"):
		return path
	var absolute := _runtime_absolute(path)
	var asset_root := _runtime_absolute("res://../eloria-assets")
	var project_root := _project_root()
	if absolute.begins_with(asset_root + "/"):
		return "eloria-assets/" + absolute.substr(asset_root.length() + 1)
	if absolute.begins_with(project_root + "/"):
		return "godot-client/" + absolute.substr(project_root.length() + 1)
	return path if path.begins_with("user://") else ""

static func source_path(logical: String) -> String:
	if logical.begins_with("eloria-assets/"):
		return "res://../" + logical
	if logical.begins_with("godot-client/"):
		return "res://" + logical.substr("godot-client/".length())
	return logical if logical.begins_with("user://") else ""

static func _hex_digest(value: Variant) -> bool:
	if not value is String or value.length() != 64:
		return false
	var digest: String = value
	for index: int in digest.length():
		var character := digest.substr(index, 1)
		if not character in "0123456789abcdef":
			return false
	return true

static func _contained(path: String, directory: String) -> bool:
	var candidate := _runtime_absolute(path)
	var parent := _runtime_absolute(directory).trim_suffix("/")
	return candidate.begins_with(parent + "/")

static func _safe_source(logical: String, catalog_path: String) -> String:
	if "\\" in logical or ":" in logical.trim_prefix("user://"):
		return ""
	var actual := source_path(logical)
	if actual.is_empty():
		return ""
	if logical.begins_with("user://"):
		# Only explicit isolated fixture catalogs can use fixture inputs.
		return actual if catalog_path.begins_with("user://") \
			and _contained(actual, catalog_path.get_base_dir()) else ""
	var scope := "res://../eloria-assets" if logical.begins_with("eloria-assets/") else "res://"
	return actual if _contained(actual, scope) else ""

static func _record(label: StringName, started: int, atomic := false) -> void:
	_mutex.lock()
	Diagnostics.record(_timings, label, started, atomic)
	_mutex.unlock()

static func _miss(reason: String, required: bool, details := "") -> Dictionary:
	_mutex.lock()
	_misses[reason] = int(_misses.get(reason, 0)) + 1
	_mutex.unlock()
	return {"status": "reject" if required else "miss", "reason": reason,
		"details": details, "resource": null}

## Returns an immutable PackedScene/Mesh Resource, never an instantiated Node.
## Worker callers must not instantiate it; publish to a main-thread adapter.
## require-pilot applies only to listed source/kind entries, leaving other
## content on validated raw fallback. Explicit qualification checks hit counts.
static func acquire(kind: String, source: String, source_digest: String,
		texture_token: String, mode := "", catalog_path := CATALOG) -> Dictionary:
	if mode.is_empty():
		mode = selected_mode()
	if mode == "raw":
		return _miss("disabled", false)
	if not mode in MODES or kind not in ["world", "scene", "mesh"]:
		return _miss("unsupported_request", false)
	var requested := logical_source(source)
	if requested.is_empty() or not _hex_digest(source_digest):
		return _miss("invalid_source_identity", false)
	if Archived.is_retired_path(source):
		return _miss("retired_source", mode == "require-pilot")
	if kind == "mesh" and Archived.is_retired_prototype(source.get_file().get_basename()):
		return _miss("retired_source", mode == "require-pilot")
	if not FileAccess.file_exists(catalog_path):
		return _miss("catalog_missing", mode == "require-pilot")
	var began := Time.get_ticks_usec()
	var parser := JSON.new()
	var parse_error := parser.parse(FileAccess.get_file_as_string(catalog_path))
	_record(&"catalog_read", began)
	if parse_error != OK or not parser.data is Dictionary:
		return _miss("catalog_invalid", mode == "require-pilot")
	var catalog: Dictionary = parser.data
	if int(catalog.get("schema_version", -1)) != SCHEMA \
			or str(catalog.get("policy", "")) != COOK_POLICY \
			or not catalog.get("entries") is Array:
		return _miss("catalog_schema", mode == "require-pilot")
	var matches: Array[Dictionary] = []
	var listed := false
	for value: Variant in catalog.entries:
		if not value is Dictionary:
			return _miss("catalog_entry_invalid", mode == "require-pilot")
		var entry: Dictionary = value
		if str(entry.get("kind", "")) != kind or str(entry.get("source", "")) != requested:
			continue
		listed = true
		if str(entry.get("source_digest", "")) == source_digest \
				and str(entry.get("texture_token", "")) == texture_token \
				and str(entry.get("node_policy", "retain")) == (node_policy() if kind == "world" else "retain"):
			matches.append(entry)
	var required := mode == "require-pilot" and listed
	if not listed:
		return _miss("not_listed", false)
	if matches.size() != 1:
		return _miss("variant_missing" if matches.is_empty() else "variant_ambiguous", required)
	var selected: Dictionary = matches[0]
	if _canonical_json(selected.get("engine_policy")) != _canonical_json(engine_policy()):
		return _miss("engine_or_cook_policy", required)
	if selected.has("metadata") or not selected.get("metadata_json") is String:
		return _miss("catalog_metadata_representation", required)
	if not _hex_digest(selected.get("entry_id")):
		return _miss("invalid_entry_id", required)
	if entry_identity(selected) != str(selected.entry_id):
		return _miss("entry_identity_mismatch", required)
	# Decode only after the exact authoritative String has been identity-bound.
	var metadata_parser := JSON.new()
	if metadata_parser.parse(str(selected.metadata_json)) != OK or not metadata_parser.data is Dictionary:
		return _miss("metadata_json_invalid", required)
	var decoded_metadata: Dictionary = metadata_parser.data
	var inputs: Variant = selected.get("inputs")
	var payloads: Variant = selected.get("payloads")
	if not inputs is Array or inputs.is_empty() or not payloads is Array or payloads.is_empty():
		return _miss("closure_incomplete", required)
	var seen: Dictionary = {}
	var input_digests: Dictionary = {}
	var shader_inputs: Dictionary = {}
	var prototype_keys: Dictionary = {}
	began = Time.get_ticks_usec()
	for value: Variant in inputs:
		if not value is Dictionary:
			return _miss("input_record_invalid", required)
		var record: Dictionary = value
		var logical := str(record.get("path", ""))
		var actual := _safe_source(logical, catalog_path)
		if actual.is_empty() or seen.has(logical) or not _hex_digest(record.get("sha256")):
			return _miss("input_path_or_digest", required, logical)
		seen[logical] = true
		input_digests[str(record.sha256)] = true
		if actual.get_extension() in ["gdshader", "gdshaderinc"]:
			shader_inputs[actual] = true
		if logical.get_extension() == "glb":
			prototype_keys[logical.get_file().get_basename()] = true
		if FileAccess.get_sha256(actual) != str(record.sha256):
			return _miss("input_hash_mismatch", required, logical)
	_record(&"source_verify", began)
	if not seen.has(requested):
		return _miss("source_not_in_closure", required)
	seen.clear()
	var primary := str(selected.get("resource", ""))
	began = Time.get_ticks_usec()
	for value: Variant in payloads:
		if not value is Dictionary:
			return _miss("payload_record_invalid", required)
		var record: Dictionary = value
		var path := str(record.get("path", ""))
		if not path.begins_with(catalog_path.get_base_dir() + "/") \
				or not _contained(path, catalog_path.get_base_dir()) or seen.has(path) \
				or not _hex_digest(record.get("sha256")) \
				or path.get_extension() not in ["scn", "res"] \
				or path.get_file().get_basename() != str(record.get("sha256", "")):
			return _miss("payload_path_or_digest", required, path)
		seen[path] = true
		if FileAccess.get_sha256(path) != str(record.sha256):
			return _miss("payload_hash_mismatch", required, path)
	_record(&"payload_verify", began)
	if not seen.has(primary) or primary.get_extension() not in ["scn", "res"]:
		return _miss("primary_not_in_closure", required)
	var shared_images: Variant = selected.get("shared_images", {})
	var shared_meshes: Variant = selected.get("shared_meshes", {})
	if not shared_images is Dictionary or not shared_meshes is Dictionary:
		return _miss("shared_resource_record", required)
	for path: Variant in shared_images:
		if not seen.has(path) or not input_digests.has(str(shared_images[path])):
			return _miss("shared_image_not_in_closure", required)
	for path: Variant in shared_meshes:
		var key := str(shared_meshes[path])
		if not seen.has(path) or not prototype_keys.has(key) or Archived.is_retired_prototype(key):
			return _miss("shared_mesh_not_in_closure", required)
	# Native resources can themselves name other resources. Hashing a primary
	# alone is insufficient. Require every observed dependency in this verified
	# closure; content-addressed payload paths also prevent stale REUSE hits.
	for path: String in seen:
		for dependency: String in ResourceLoader.get_dependencies(path):
			var dependency_path := dependency.get_slice("::", dependency.get_slice_count("::") - 1)
			if not seen.has(dependency_path) and not shader_inputs.has(dependency_path):
				return _miss("dependency_not_in_closure", required, dependency)
	# Native ImageTexture serializes image storage only, not its logical
	# size override. Restore verified payload metadata before any native
	# Resource/mesh/template can be exposed to a caller, including workers.
	began = Time.get_ticks_usec()
	# ResourceLoader's cache is weak. Keep every restored child alive until
	# its primary has loaded and owns that same dependency graph; otherwise a
	# later parent load can reload an earlier child from its unrestored bytes.
	var verified_payloads: Array[Resource] = []
	for path: String in seen:
		var payload: Resource = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REUSE)
		if payload == null:
			return _miss("native_payload_invalid", required, path)
		verified_payloads.append(payload)
		if payload is ImageTexture and not TextureSizes.restore_verified(payload as ImageTexture):
			return _miss("native_texture_logical_size", required, path)
		if payload is Animation:
			var clocks_began := Time.get_ticks_usec()
			var clocks_valid := AnimationKeys.restore_verified(payload as Animation)
			_record(&"native_animation_clock_publish", clocks_began, true)
			if not clocks_valid:
				return _miss("native_animation_clocks", required, path)
	_record(&"native_resource_state_publish", began, true)
	var expected_type := "Mesh" if kind == "mesh" else "PackedScene"
	began = Time.get_ticks_usec()
	var resource: Resource = ResourceLoader.load(primary, expected_type, ResourceLoader.CACHE_MODE_REUSE)
	_record(&"native_resource_read", began, true)
	if resource == null or (kind == "mesh" and not resource is Mesh) \
			or (kind != "mesh" and not resource is PackedScene):
		return _miss("native_resource_invalid", required)
	_mutex.lock()
	_hits += 1
	var consumed_id := str(selected.entry_id)
	if _consumed.has(consumed_id):
		_consumed[consumed_id]["hits"] += 1
	else:
		_consumed[consumed_id] = {"entry_id": consumed_id, "kind": kind, "source": requested,
			"texture_token": texture_token, "node_policy": str(selected.get("node_policy", "retain")),
			"hits": 1}
	_mutex.unlock()
	selected["metadata"] = decoded_metadata
	return {"status": "hit", "reason": "verified_exact_variant", "resource": resource,
		"entry": selected, "source": requested, "entry_id": str(selected.entry_id)}

static func snapshot() -> Dictionary:
	_mutex.lock()
	var consumed: Array = []
	var identities: Array = _consumed.keys()
	identities.sort()
	for identity: String in identities:
		consumed.append((_consumed[identity] as Dictionary).duplicate())
	var result := {"mode": selected_mode(), "active": _hits > 0,
		"hits": _hits, "misses": _misses.duplicate(), "consumed_entries": consumed,
		"timings": Diagnostics.snapshot(_timings), "strong_resource_entries": 0,
		"verification_reuse": false, "estimate_kind": "declared_content_not_allocation"}
	_mutex.unlock()
	return result
