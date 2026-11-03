class_name GlbSceneCache

extends RefCounted
## Loads each glTF scene exactly once and hands out instances of the cached
## result.
##
## In-project actor assets prefer Godot's imported PackedScene. Besides avoiding
## a runtime parse, that path retains the importer's generated mesh LODs, shadow
## meshes, compression and texture mip chains. External authoring/test files and
## lean checkouts without an import cache keep the raw GLTFDocument fallback.
##
## Instances share their mesh, skin and material resources, which also removes
## the duplicate GPU uploads the per-actor parse produced. Per-actor tinting
## goes through `material_override`, so sharing the source materials cannot leak
## one actor's appearance into another.
##
## Threads: every actor glTF (race, hair, equipment, held prop, mount,
## creature, RL head) is parsed by `_parse_generate`, which enables the actor
## image extension (actor_images.gd) on its GLTFState. A packaged client
## imports the textures the equipment glTFs name by URI
## (tools/package_client.py), and plain GLTFDocument takes such a texture
## through ResourceLoader and then reads it back with get_image(). Outside the
## editor that is a RenderingServer texture read: on the main thread it stalls
## the GPU once per image, and on a worker it waits for the main thread to
## serve it, so a main thread that joins the worker (wait_to_finish) never
## returns. The extension takes the same texture without the read, so an actor
## parse and generate_scene() wait for nothing.
##
## PackedScene.pack() still waits: it asks each MeshInstance3D for its property
## list, a synchronous RenderingServer call (on a worker, about one main frame
## per mesh). So actor files reach a worker only through `prepare_actor`, which
## parses and generates and returns the scene unpacked, and main publishes it
## with `install_actor_prepared`, which packs. `prepare` packs on its worker; it
## serves the map preloaders' visualScenes (no actor file), creature warmup and
## the RL head library, and tests/test_package_actor_worker_contract.py and the
## packaging tests hold every caller to that. With ELORIA_ACTOR_IMAGES=legacy
## the extension is off and an equipment parse belongs on the main thread again
## (`prepare_actor` records "actor_images": false).

## World objects (harvest nodes, interactives) also come through here, and
## GLTFDocument builds their textures at runtime with no mip chain. Seen from the
## gameplay camera a node's 256-512 px texture is minified several times over, so
## without mips it aliases and swims as the camera moves - the reason
## world_loader rebuilds the chains of every map chunk. Models under this root
## get the same chains and the same anisotropic filter as the map around them.
## Actors are left as they were: their load time is why this cache exists.
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const ActorImages := preload("res://src/actors/actor_images.gd")
const GltfAnimationFidelity := preload("res://src/actors/gltf_animation_fidelity.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
const WorldObjectImages := preload("res://src/world/world_object_images.gd")
const SceneryImages := preload("res://src/world/scenery_image_sources.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const PreparedContent := preload("res://src/world/prepared_content.gd")
const PreparedLifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const GeometryCache := preload("res://src/world/map_geometry_cache.gd")
const GeometrySources := preload("res://src/world/map_geometry_texture_sources.gd")
const MapSceneCache := preload("res://src/world/map_scene_cache.gd")
const MapMaterialPreparation := preload("res://src/world/map_material_preparation.gd")
const WORLD_ASSET_ROOT := "res://assets/world/"
## glTF files under this root are actor documents (see "Threads").
const ACTOR_ASSET_ROOT := "res://assets/actors/"
const BOUND_MAIN_ENVIRONMENT := "ELORIA_UNDERGROUND_BOUND_PREPARE"
const EARLY_WORLD_FILTER_ENVIRONMENT := "ELORIA_EARLY_WORLD_OBJECT_FILTER"

static var _scenes: Dictionary = {}
static var _failed: Dictionary = {}
static var _prepared_entries: Dictionary = {}
static var _geometry_entries: Dictionary = {}
static var _direct_raw_scenes: Dictionary = {}
static var _diagnostics_mutex := Mutex.new()
static var _resource_timings: Dictionary = {}
static var _lookup_hits := 0
static var _lookup_misses := 0

static func missing(paths: PackedStringArray) -> PackedStringArray:
	var out := PackedStringArray()
	for path: String in paths:
		path = _canonical_path(path)
		if not _scenes.has(path) and not _failed.has(path):
			out.append(path)
	return out

static func prepare(paths: PackedStringArray) -> Dictionary:
	# Worker-owned resources. The main thread publishes them only on arrival.
	# It packs on the worker: never an equipment glTF (prepare_actor is the
	# actor worker path), see "Threads" above.
	var result: Dictionary = {}
	for path: String in paths:
		path = _canonical_path(path)
		var scenery := _scenery_inputs(path)
		if not scenery.is_empty() and not bool(scenery.get("ok", false)):
			continue
		if not GeometryCache.cooking and PreparedContent.selected_mode() != "require-pilot" and GeometryCache.eligible("asset",path):
			var geometry := GeometryCache.acquire("asset",path,_source_sha(path, scenery),{},MapSceneCache.is_enabled())
			if str(geometry.status) == "hit":
				result[path] = {"geometry_record":geometry}
				continue
		if PreparedContent.selected_mode() != "raw":
			var record := PreparedContent.acquire("scene", path, _source_sha(path, scenery),
				PreparedContent.scene_texture_token(path, scenery))
			if str(record.status) == "hit":
				result[path] = record # Immutable native Resources, never Nodes.
				continue
			if str(record.status) == "reject":
				continue
		var scene := _build(path, scenery)
		if scene != null:
			result[path] = {"raw_scene": scene, "source_sha256": _source_sha(path, scenery),
				"closure_token": str(scenery.get("closure_token", ""))} if not scenery.is_empty() else scene
	return result

static func install_prepared(scenes: Dictionary) -> void:
	for path: String in scenes:
		# A browser file may have been retired while this worker finished.
		if OS.has_feature("web") and not FileAccess.file_exists(path): continue
		if not _scenes.has(path):
			var prepared: Variant = scenes[path]
			if prepared is Dictionary:
				var scenery := _scenery_inputs(path)
				if not scenery.is_empty() and not bool(scenery.get("ok", false)):
					continue
				if prepared.has("raw_scene"):
					if str(prepared.get("source_sha256", "")) == _source_sha(path, scenery) \
							and str(prepared.get("closure_token", "")) == str(scenery.get("closure_token", "")):
						_scenes[path] = prepared.raw_scene
					else:
						var current := _build(path, scenery)
						if current != null: _scenes[path] = current
					continue
				if prepared.has("geometry_record"):
					var geometry: Dictionary = prepared.geometry_record
					if GeometryCache.revalidate(geometry):
						_scenes[path] = geometry.resource
						_geometry_entries[path] = geometry
					else:
						var raw := _build(path, scenery)
						if raw != null: _scenes[path] = raw
					continue
				# Revalidate the current bytes/policy before publishing a worker record.
				var began := Time.get_ticks_usec()
				var verified := PreparedContent.acquire("scene", path, _source_sha(path, scenery),
					PreparedContent.scene_texture_token(path, scenery))
				_record_operation(&"prepared_completion_verify", began)
				if str(verified.status) == "hit":
					_scenes[path] = verified.resource
					_prepared_entries[path] = verified.entry
				elif str(verified.status) == "miss":
					var raw := _build(path, scenery)
					if raw != null:
						_scenes[path] = raw
			else:
				_scenes[path] = prepared

## Prepares one actor glTF for `install_actor_prepared`, on any thread once
## GltfQuantization.ensure_registered() has run on the main thread. It parses
## and generates and never packs, so it waits for nothing on the main thread
## (see "Threads"). Returns {"path", "actor_images"} plus one of:
##   "root"      the generated scene, unowned and unpacked, with "stamp" (the
##               file's modification time and length when it was read);
##   "packed"    the editor's imported PackedScene (checkouts only);
##   "prepared"  the result of `prepare`, when prepared content or the geometry
##               cache serve this file (immutable resources, as today);
##   "error"     why nothing was prepared ("unregistered", "not_actor_document",
##               "retired", "parse_failed"); the main thread builds as today.
## "actor_images" is false under ELORIA_ACTOR_IMAGES=legacy, when an equipment
## parse waits for the main thread again. A record holding a root owns a Node:
## hand it to install_actor_prepared or discard_actor_prepared, exactly once.
## Several actor parses never run at once (one preparer thread).
static func prepare_actor(path: String) -> Dictionary:
	var canonical := _canonical_path(path)
	var record := {"path": canonical, "actor_images": false}
	# Main's registration also publishes the actor image switch: a worker reads
	# it only after that, never while main writes it.
	if not GltfQuantization.ensure_registered():
		record["error"] = "unregistered"
		return record
	record["actor_images"] = ActorImages.active()
	if not is_actor_document(canonical):
		record["error"] = "not_actor_document"
		return record
	if ArchivedModelPolicy.is_retired_path(canonical):
		record["error"] = "retired"
		return record
	if PreparedContent.selected_mode() != "raw" \
			or (not GeometryCache.cooking and GeometryCache.eligible("asset", canonical)):
		record["prepared"] = prepare(PackedStringArray([canonical]))
		return record
	if not GeometryCache.cooking:
		var imported := _imported_actor_scene(canonical)
		if imported != null:
			record["packed"] = imported
			return record
	record["stamp"] = _source_stamp(canonical)
	var root := _parse_generate(canonical, {}, true)
	if root == null:
		record["error"] = "parse_failed"
		return record
	record["root"] = root
	return record

## Main thread: publishes a `prepare_actor` record into the session cache and
## returns whether its path is cached afterwards. A raw root is packed here
## (a race scene packs in 1-2 ms on main, against about one main frame per
## mesh on a worker) and freed. A root whose file changed since it was read,
## whose browser file was retired, or whose path is already cached is freed
## unpublished; the cache keeps, or later builds, the current scene as today.
static func install_actor_prepared(record: Dictionary) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		push_error("glb cache: install_actor_prepared is main-thread only")
		return false
	var path := str(record.get("path", ""))
	if record.get("prepared") is Dictionary:
		install_prepared(record.prepared)
		return _scenes.has(path)
	var root := _take_root(record)
	var publish := not path.is_empty() and not _scenes.has(path) \
		and not (OS.has_feature("web") and not FileAccess.file_exists(path))
	if record.get("packed") is PackedScene:
		if publish:
			_scenes[path] = record.packed
			_failed.erase(path)
		return _scenes.has(path)
	if root == null:
		return _scenes.has(path)
	if not publish or record.get("stamp") != _source_stamp(path):
		root.free()
		return _scenes.has(path)
	var began := Time.get_ticks_usec()
	var packed := _pack_generated(path, root)
	_record_operation(&"actor_prepared_install", began)
	if packed == null:
		return false
	_scenes[path] = packed
	_failed.erase(path)
	return true

## Frees a record's unpublished root (a cancelled or stale job). Any thread;
## a second call does nothing.
static func discard_actor_prepared(record: Dictionary) -> void:
	var root := _take_root(record)
	if root != null:
		root.free()

static func _take_root(record: Dictionary) -> Node3D:
	var value: Variant = record.get("root")
	record.erase("root")
	if typeof(value) != TYPE_OBJECT or not is_instance_valid(value):
		return null
	return value as Node3D

## Whether `path` is an actor glTF: under ACTOR_ASSET_ROOT, in the same
## globalized form the cache keys use.
static func is_actor_document(path: String) -> bool:
	var canonical := _canonical_path(path)
	return not canonical.is_empty() and canonical.begins_with(_canonical_path(ACTOR_ASSET_ROOT)) \
		and not is_world_asset(canonical)

static func _source_stamp(path: String) -> Array:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return []
	var length := file.get_length()
	file.close()
	return [FileAccess.get_modified_time(path), length]

## Underground's synchronous Main arrival can bind each asset before opening
## the next, instead of retaining every asset's decoded Images simultaneously.
## Worker preparation/publication and non-geometry consumers keep their path.
## True means handled (individual failures retain the ordinary raw fallback).
static func prepare_bound_main(paths: PackedStringArray) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or OS.get_environment(BOUND_MAIN_ENVIRONMENT) == "0" \
			or GeometryCache.cooking or OS.get_environment("ELORIA_NO_GEOMETRY_CACHE") == "1" \
			or not MapSceneCache.is_enabled() or PreparedContent.selected_mode() == "require-pilot": return false
	# Preflight before publishing anything, so an unrelated caller cannot partly
	# switch its preparation strategy merely by including one scoped asset.
	for path: String in paths:
		if not GeometryCache.eligible("asset",path): return false
	for source: String in paths:
		var path := _canonical_path(source)
		if not _scenes.has(path) and not _failed.has(path):
			var prepared := prepare(PackedStringArray([path]))
			install_prepared(prepared) # Full source/payload/current-entry revalidation.
			prepared.clear()
		var geometry: Dictionary = _geometry_entries.get(path,{})
		if geometry.is_empty(): continue
		# Installed worker completions retain their first-use revalidation.
		var verify_again := not bool(geometry.get("bound",false)) and not bool(geometry.get("prepared_on_main",false))
		if GeometryCache.bind(geometry,verify_again): continue
		_geometry_entries.erase(path)
		_scenes.erase(path)
		var raw := _build(path)
		if raw != null: _scenes[path] = raw
	return true

## Returns the shared scene for `path`, or null when unavailable. Treat this
## scene and its subresources as immutable. Like instantiate(), call only on the
## main thread; worker preparation retains its separate build/publication path.
static func packed_scene(path: String) -> PackedScene:
	# Direct PackedScene callers own their legacy instantiate behavior. Never
	# expose a native template that requires the prepared lifecycle adapter.
	return _packed_scene(path, false)

static func _packed_scene(path: String, allow_prepared: bool) -> PackedScene:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	path = _canonical_path(path)
	if path.is_empty() or _failed.has(path):
		return null
	if _geometry_entries.has(path):
		if allow_prepared: return _scenes.get(path) as PackedScene
		var raw := _direct_raw_scenes.get(path) as PackedScene
		if raw == null:
			raw = _build(path)
			if raw != null: _direct_raw_scenes[path] = raw
		return raw
	# An installed in-memory template owns already verified immutable Resources.
	# Verify loose inputs for a new disk/cache acquisition, never per placement.
	var scenery: Dictionary = {}
	if not _scenes.has(path) or _prepared_entries.has(path):
		scenery = _scenery_inputs(path)
		if not scenery.is_empty() and not bool(scenery.get("ok", false)):
			return null
	if allow_prepared and not _scenes.has(path) and not GeometryCache.cooking \
			and PreparedContent.selected_mode() != "require-pilot" and GeometryCache.eligible("asset",path):
		var geometry := GeometryCache.acquire("asset",path,_source_sha(path, scenery),{},MapSceneCache.is_enabled())
		if str(geometry.status) == "hit":
			_scenes[path] = geometry.resource
			_geometry_entries[path] = geometry
			return geometry.resource as PackedScene
	if allow_prepared and (PreparedContent.selected_mode() != "raw" or _prepared_entries.has(path)):
		var verification_began := Time.get_ticks_usec()
		var verified := PreparedContent.acquire("scene", path, _source_sha(path, scenery),
			PreparedContent.scene_texture_token(path, scenery))
		_record_operation(&"prepared_publication_verify", verification_began)
		if str(verified.status) == "hit":
			_scenes[path] = verified.resource
			_prepared_entries[path] = verified.entry
		elif str(verified.status) == "reject":
			return null
		elif _prepared_entries.has(path):
			_prepared_entries.erase(path)
			_scenes.erase(path)
	var packed: PackedScene = _scenes.get(path) as PackedScene
	if not allow_prepared and _prepared_entries.has(path):
		var raw := _direct_raw_scenes.get(path) as PackedScene
		if raw == null:
			raw = _build(path, scenery)
			if raw != null:
				_direct_raw_scenes[path] = raw
		return raw
	if packed == null:
		_lookup_misses += 1
		var miss_began := Time.get_ticks_usec()
		packed = _build(path, scenery)
		_record_operation(&"cache_miss_build", miss_began, false)
		if packed == null:
			_failed[path] = true
			return null
		_scenes[path] = packed
	else:
		_lookup_hits += 1
	return packed

## The cached scene for `path` when it is the plain runtime glTF parse of that
## file: not imported, prepared, geometry-bound or given the world-object image
## pass. Null otherwise; never builds. Main thread, like the cache itself.
static func runtime_parse(path: String) -> PackedScene:
	path = _canonical_path(path)
	if is_world_asset(path) or _prepared_entries.has(path) or _geometry_entries.has(path):
		return null
	var packed := _scenes.get(path) as PackedScene
	return packed if packed != null and packed.resource_path.is_empty() else null

## Returns a fresh instance of `path`, or null when the file cannot be imported.
static func instantiate(path: String) -> Node3D:
	var packed := _packed_scene(path, true)
	if packed == null:
		return null
	var instantiate_began := Time.get_ticks_usec()
	var entry: Dictionary = _prepared_entries.get(_canonical_path(path), {})
	var instance: Node3D
	var geometry: Dictionary = _geometry_entries.get(_canonical_path(path),{})
	if not geometry.is_empty():
		instance = GeometryCache.instantiate(geometry,not bool(geometry.get("bound",false)) and not bool(geometry.get("prepared_on_main",false)))
		if instance == null:
			_geometry_entries.erase(_canonical_path(path))
			_scenes.erase(_canonical_path(path))
			packed = _build(_canonical_path(path))
			if packed != null:
				_scenes[_canonical_path(path)] = packed
				instance = packed.instantiate() as Node3D
	elif entry.is_empty():
		instance = packed.instantiate() as Node3D
	else:
		instance = PreparedLifecycle.instantiate({"status": "hit", "resource": packed, "entry": entry})
		if instance == null and PreparedContent.selected_mode() == "auto":
			_prepared_entries.erase(_canonical_path(path))
			packed = _build(_canonical_path(path))
			if packed != null:
				_scenes[_canonical_path(path)] = packed
				instance = packed.instantiate() as Node3D
	_record_operation(&"scene_instantiate", instantiate_began)
	return instance

## Drops every cached scene. Call when leaving a session so the next map is not
## charged for models it no longer uses.
static func clear() -> void:
	_scenes.clear()
	_failed.clear()
	_prepared_entries.clear()
	_geometry_entries.clear()
	_direct_raw_scenes.clear()

static func cached_scene_count() -> int:
	return _scenes.size() + _direct_raw_scenes.size()

static func _file_key(path: String) -> String:
	var value := _canonical_path(path)
	if value.begins_with("res://"): value = value.trim_prefix("res://")
	if not value.is_absolute_path(): value = "/".path_join(value)
	return value.simplify_path()

## Main-thread retirement of memoized templates, not their live instances.
static func release_sources(paths: PackedStringArray) -> void:
	var wanted := {}
	for path: String in paths: wanted[_file_key(path)] = true
	for cache: Dictionary in [_scenes, _direct_raw_scenes, _failed, _prepared_entries, _geometry_entries]:
		for source: String in cache.keys():
			if wanted.has(_file_key(source)): cache.erase(source)

## Read on the main thread, where cache publication/clearing already lives.
## Worker builds only update timing data behind the separate mutex. Counts do
## not attempt expensive resource walks or imply measured CPU/GPU allocation.
static func retention_snapshot() -> Dictionary:
	_diagnostics_mutex.lock()
	var timings := ResourceDiagnostics.snapshot(_resource_timings)
	_diagnostics_mutex.unlock()
	return {"strong_scene_entries": _scenes.size() + _direct_raw_scenes.size(),
		"direct_raw_scene_entries": _direct_raw_scenes.size(), "failed_paths": _failed.size(),
		"lookup_hits": _lookup_hits, "lookup_misses": _lookup_misses,
		"bytes_estimate_available": false, "timings": timings,
		"actor_images": ActorImages.totals()}

static func _record_operation(operation: StringName, started: int, atomic := true) -> void:
	var elapsed := Time.get_ticks_usec() - started
	_diagnostics_mutex.lock()
	ResourceDiagnostics.record_elapsed(_resource_timings, operation, elapsed, atomic)
	_diagnostics_mutex.unlock()

static func _canonical_path(path: String) -> String:
	# Export templates may globalize res:// to a relative name. Scenery's
	# external file closure is rooted beside the executable, independent of cwd.
	if path.begins_with(WORLD_ASSET_ROOT):
		return PreparedContent._runtime_absolute(path)
	return ProjectSettings.globalize_path(path) if path.begins_with("res://") else path

static func _scenery_inputs(path: String) -> Dictionary:
	if not is_world_asset(path): return {}
	var began := Time.get_ticks_usec()
	var verified := SceneryImages.verify(path)
	_record_operation(&"scenery_source_verify", began)
	if not bool(verified.get("ok", false)):
		push_error("scenery image source rejected: %s (%s)" % [path, str(verified.get("error", "invalid"))])
	return verified

static func _source_sha(path: String, scenery: Dictionary) -> String:
	return str(scenery.source_sha256) if not scenery.is_empty() and scenery.get("source_sha256") is String \
		else CreaturePayload.source_sha256(path)

static func _build(path: String, scenery: Dictionary = {}) -> PackedScene:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	if is_world_asset(path) and scenery.is_empty(): scenery = _scenery_inputs(path)
	if not scenery.is_empty() and not bool(scenery.get("ok", false)): return null
	if GeometryCache.cooking: return _build_raw(path, scenery)
	var imported := _imported_actor_scene(path)
	if imported != null:
		return imported
	return _build_raw(path, scenery)

## ResourceLoader resolves the `.import` remap in an editor checkout and the
## equivalent remap in an exported PCK. Restricting this preference to actor
## assets leaves the world-authoring cache's external-file semantics unchanged.
static func _imported_actor_scene(path: String) -> PackedScene:
	var resource_path := ProjectSettings.localize_path(path)
	if not resource_path.begins_with("res://assets/actors/"):
		return null
	var extension := resource_path.get_extension().to_lower()
	if extension != "glb" and extension != "gltf":
		return null
	if OS.has_feature("editor"):
		if _editor_import_path(resource_path).is_empty():
			return null
	if not ResourceLoader.exists(resource_path, "PackedScene"):
		return null
	var began := Time.get_ticks_usec()
	var imported := ResourceLoader.load(resource_path, "PackedScene",
		ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	_record_operation(&"imported_scene_read", began)
	return imported

## An ignored loose-native folder can retain import files from an older
## checkout. ResourceLoader still follows those remaps, even though an editor
## scan now excludes their source. Honor the active folder policy first.
## Kept separate from the actor whitelist for small ignored import fixtures.
static func _editor_import_path(resource_path: String) -> String:
	var directory := resource_path.get_base_dir()
	while directory.begins_with("res://") or directory.begins_with("user://"):
		if FileAccess.file_exists(directory.path_join(".gdignore")):
			return ""
		if directory in ["res://", "user://"]: break
		var parent := directory.get_base_dir()
		if parent == directory: break
		directory = parent
	# ResourceLoader.exists() also accepts skipped or unfinished editor imports.
	var import_settings := ConfigFile.new()
	if import_settings.load(resource_path + ".import") != OK \
			or str(import_settings.get_value("remap", "importer", "")) != "scene":
		return ""
	var imported_path := str(import_settings.get_value("remap", "path", ""))
	return imported_path if not imported_path.is_empty() and FileAccess.file_exists(imported_path) else ""

static func _build_raw(path: String, scenery: Dictionary = {}) -> PackedScene:
	var generated := _parse_generate(path, scenery, is_actor_document(path))
	return _pack_generated(path, generated) if generated != null else null

## The one runtime glTF parse, shared by `_build_raw` (main) and
## `prepare_actor` (any thread): the file's generated scene, unowned and
## unpacked, or null. An actor document gets the actor image extension, a
## world asset its image pass. Steps that change the parsed state for both
## paths (AT-C2's sidecars, ALOD-C1h's cooked geometry) go here, after the
## parse and before generate_scene().
static func _parse_generate(path: String, scenery: Dictionary, actor_document: bool) -> Node3D:
	if not GltfQuantization.ensure_registered():
		push_error("raw glTF parse requires main-thread extension initialization")
		return null
	var document: GLTFDocument = GLTFDocument.new()
	var state: GLTFState = GLTFState.new()
	var world_asset := is_world_asset(path)
	if world_asset:
		if scenery.is_empty(): scenery = _scenery_inputs(path)
		if not bool(scenery.get("ok", false)): return null
		state.set_additional_data(WorldObjectImages.ENABLED, true)
		state.set_additional_data(SceneryImages.VERIFIED_KEY, scenery)
	elif actor_document:
		ActorImages.enable(state, path)
	var operation_began := Time.get_ticks_usec()
	var parse_error: Error
	if world_asset and scenery.get("bytes") is PackedByteArray:
		state.filename = path.get_file().get_basename()
		parse_error = document.append_from_buffer(scenery.bytes, path.get_base_dir().trim_suffix("/") + "/", state)
	else:
		parse_error = CreaturePayload.append(document, path, state)
	# Texture extension jobs are complete; do not retain a second source blob.
	state.set_additional_data(SceneryImages.VERIFIED_KEY, null)
	scenery = {}
	_record_operation(&"gltf_parse", operation_began)
	if parse_error != OK or (world_asset and WorldObjectImages.has_source_errors(state)):
		return null
	if world_asset and int(state.get_additional_data(WorldObjectImages.PREPARED)) < state.get_images().size():
		build_texture_mipmaps(state)
	var early_filter := world_asset and OS.get_environment(EARLY_WORLD_FILTER_ENVIRONMENT) != "0" and MapMaterialPreparation.enabled()
	if early_filter: MapMaterialPreparation.prepare(state)
	GeometrySources.note(state,path)
	operation_began = Time.get_ticks_usec()
	var generated: Node = document.generate_scene(state, GltfAnimationFidelity.bake_fps(state))
	_record_operation(&"gltf_generate_scene", operation_began)
	if generated == null:
		return null
	if generated is not Node3D:
		generated.free()
		return null
	if world_asset:
		_filter_anisotropic(generated,early_filter)
	return generated as Node3D

## Packs a `_parse_generate` root and frees it. On a worker pack() waits for
## the main thread about once per mesh (see "Threads"): `prepare` accepts
## that, `install_actor_prepared` packs on main instead.
static func _pack_generated(path: String, generated: Node3D) -> PackedScene:
	_claim(generated, generated)
	var packed: PackedScene = PackedScene.new()
	var operation_began := Time.get_ticks_usec()
	var packed_error: Error = packed.pack(generated)
	_record_operation(&"scene_pack", operation_began)
	operation_began = Time.get_ticks_usec()
	generated.free()
	_record_operation(&"temporary_scene_free", operation_began)
	if packed_error != OK:
		push_warning("glb cache: pack failed for %s (%s)" % [
			path, error_string(packed_error)])
		return null
	return packed

static func is_world_asset(path: String) -> bool:
	return _canonical_path(path).begins_with(_canonical_path(WORLD_ASSET_ROOT))

## Gives every image the state carries a mip chain. The images are the objects
## the generated materials will reference, so this must run before
## generate_scene(). Returns how many images were rebuilt.
static func build_texture_mipmaps(state: GLTFState) -> int:
	var rebuilt := 0
	for texture_value: Variant in state.get_images():
		var texture: ImageTexture = texture_value as ImageTexture
		if texture == null:
			continue
		var image: Image = texture.get_image()
		if image == null or image.is_empty() or image.has_mipmaps():
			continue
		if image.is_compressed() and image.decompress() != OK:
			continue
		image.generate_mipmaps()
		texture.set_image(image)
		rebuilt += 1
	return rebuilt

static func _filter_anisotropic(root: Node, early_filter := false) -> void:
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (node as MeshInstance3D).mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			# Either opt-out restores the old unconditional late setter, so timing
			# controls include its shader-dirty ordering as well as its final value.
			if material != null and (not early_filter or material.texture_filter != MapMaterialPreparation.FILTER):
				material.texture_filter = MapMaterialPreparation.FILTER

# PackedScene.pack() only stores nodes owned by the packed root.
static func _claim(node: Node, scene_owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = scene_owner
		_claim(child, scene_owner)
