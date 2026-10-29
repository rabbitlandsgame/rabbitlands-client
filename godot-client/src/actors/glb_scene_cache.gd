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
## Threads: parse an equipment glTF on the main thread only, or on a worker the
## main thread never waits on. A packaged client imports the textures the
## equipment glTFs name by URI (tools/package_client.py), and GLTFDocument
## takes such a texture through ResourceLoader and then reads it back with
## get_image(). Outside the editor that is a RenderingServer texture read: on
## the main thread it stalls the GPU once per image, and on a worker it waits
## for the main thread to serve it, so a main thread that joins the worker
## (wait_to_finish) never returns. Today only the main thread parses equipment:
## `prepare` runs on a map preloader's worker for the exterior links'
## visualScenes, which name no actor file, and the packaging tests hold them
## and the prewarmed animation libraries to that.

## World objects (harvest nodes, interactives) also come through here, and
## GLTFDocument builds their textures at runtime with no mip chain. Seen from the
## gameplay camera a node's 256-512 px texture is minified several times over, so
## without mips it aliases and swims as the camera moves - the reason
## world_loader rebuilds the chains of every map chunk. Models under this root
## get the same chains and the same anisotropic filter as the map around them.
## Actors are left as they were: their load time is why this cache exists.
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const GltfAnimationFidelity := preload("res://src/actors/gltf_animation_fidelity.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
const WorldObjectImages := preload("res://src/world/world_object_images.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const PreparedContent := preload("res://src/world/prepared_content.gd")
const PreparedLifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const GeometryCache := preload("res://src/world/map_geometry_cache.gd")
const GeometrySources := preload("res://src/world/map_geometry_texture_sources.gd")
const MapSceneCache := preload("res://src/world/map_scene_cache.gd")
const MapMaterialPreparation := preload("res://src/world/map_material_preparation.gd")
const WORLD_ASSET_ROOT := "res://assets/world/"
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
	# Never an equipment glTF: see "Threads" above.
	var result: Dictionary = {}
	for path: String in paths:
		path = _canonical_path(path)
		if not GeometryCache.cooking and PreparedContent.selected_mode() != "require-pilot" and GeometryCache.eligible("asset",path):
			var geometry := GeometryCache.acquire("asset",path,CreaturePayload.source_sha256(path),{},MapSceneCache.is_enabled())
			if str(geometry.status) == "hit":
				result[path] = {"geometry_record":geometry}
				continue
		if PreparedContent.selected_mode() != "raw":
			var record := PreparedContent.acquire("scene", path, CreaturePayload.source_sha256(path),
				PreparedContent.scene_texture_token(path))
			if str(record.status) == "hit":
				result[path] = record # Immutable native Resources, never Nodes.
				continue
			if str(record.status) == "reject":
				continue
		var scene := _build(path)
		if scene != null:
			result[path] = scene
	return result

static func install_prepared(scenes: Dictionary) -> void:
	for path: String in scenes:
		if not _scenes.has(path):
			var prepared: Variant = scenes[path]
			if prepared is Dictionary:
				if prepared.has("geometry_record"):
					var geometry: Dictionary = prepared.geometry_record
					if GeometryCache.revalidate(geometry):
						_scenes[path] = geometry.resource
						_geometry_entries[path] = geometry
					else:
						var raw := _build(path)
						if raw != null: _scenes[path] = raw
					continue
				# Revalidate the current bytes/policy before publishing a worker record.
				var began := Time.get_ticks_usec()
				var verified := PreparedContent.acquire("scene", path, CreaturePayload.source_sha256(path),
					PreparedContent.scene_texture_token(path))
				_record_operation(&"prepared_completion_verify", began)
				if str(verified.status) == "hit":
					_scenes[path] = verified.resource
					_prepared_entries[path] = verified.entry
				elif str(verified.status) == "miss":
					var raw := _build(path)
					if raw != null:
						_scenes[path] = raw
			else:
				_scenes[path] = prepared

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
	if allow_prepared and not _scenes.has(path) and not GeometryCache.cooking \
			and PreparedContent.selected_mode() != "require-pilot" and GeometryCache.eligible("asset",path):
		var geometry := GeometryCache.acquire("asset",path,CreaturePayload.source_sha256(path),{},MapSceneCache.is_enabled())
		if str(geometry.status) == "hit":
			_scenes[path] = geometry.resource
			_geometry_entries[path] = geometry
			return geometry.resource as PackedScene
	if allow_prepared and (PreparedContent.selected_mode() != "raw" or _prepared_entries.has(path)):
		var verification_began := Time.get_ticks_usec()
		var verified := PreparedContent.acquire("scene", path, CreaturePayload.source_sha256(path),
			PreparedContent.scene_texture_token(path))
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
			raw = _build(path)
			if raw != null:
				_direct_raw_scenes[path] = raw
		return raw
	if packed == null:
		_lookup_misses += 1
		var miss_began := Time.get_ticks_usec()
		packed = _build(path)
		_record_operation(&"cache_miss_build", miss_began, false)
		if packed == null:
			_failed[path] = true
			return null
		_scenes[path] = packed
	else:
		_lookup_hits += 1
	return packed

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
		"bytes_estimate_available": false, "timings": timings}

static func _record_operation(operation: StringName, started: int, atomic := true) -> void:
	var elapsed := Time.get_ticks_usec() - started
	_diagnostics_mutex.lock()
	ResourceDiagnostics.record_elapsed(_resource_timings, operation, elapsed, atomic)
	_diagnostics_mutex.unlock()

static func _canonical_path(path: String) -> String:
	return ProjectSettings.globalize_path(path) if path.begins_with("res://") else path

static func _build(path: String) -> PackedScene:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	if GeometryCache.cooking: return _build_raw(path)
	var imported := _imported_actor_scene(path)
	if imported != null:
		return imported
	return _build_raw(path)

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
		# ResourceLoader.exists() also accepts skipped or unfinished editor
		# imports. Loading those emits errors before the raw fallback succeeds.
		var import_settings := ConfigFile.new()
		if import_settings.load(resource_path + ".import") != OK \
				or str(import_settings.get_value("remap", "importer", "")) != "scene":
			return null
		var imported_path := str(import_settings.get_value("remap", "path", ""))
		if imported_path.is_empty() or not FileAccess.file_exists(imported_path):
			return null
	if not ResourceLoader.exists(resource_path, "PackedScene"):
		return null
	var began := Time.get_ticks_usec()
	var imported := ResourceLoader.load(resource_path, "PackedScene",
		ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	_record_operation(&"imported_scene_read", began)
	return imported

static func _build_raw(path: String) -> PackedScene:
	if not GltfQuantization.ensure_registered():
		push_error("raw glTF parse requires main-thread extension initialization")
		return null
	var document: GLTFDocument = GLTFDocument.new()
	var state: GLTFState = GLTFState.new()
	var world_asset := is_world_asset(path)
	if world_asset: state.set_additional_data(WorldObjectImages.ENABLED, true)
	var operation_began := Time.get_ticks_usec()
	var parse_error := CreaturePayload.append(document, path, state)
	_record_operation(&"gltf_parse", operation_began)
	if parse_error != OK:
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
	_claim(generated, generated)
	var packed: PackedScene = PackedScene.new()
	operation_began = Time.get_ticks_usec()
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
	return _canonical_path(path).begins_with(ProjectSettings.globalize_path(WORLD_ASSET_ROOT))

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
