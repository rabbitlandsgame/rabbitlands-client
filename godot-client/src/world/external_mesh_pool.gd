extends RefCounted

const VramTextures := preload("res://src/world/vram_textures.gd")
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const PreparedContent := preload("res://src/world/prepared_content.gd")
const PreparedSharing := preload("res://src/world/prepared_material_sharing.gd")
const GeometrySources := preload("res://src/world/map_geometry_texture_sources.gd")
const MapMaterialPreparation := preload("res://src/world/map_material_preparation.gd")
const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")
const DistanceClasses := preload("res://src/world/world_distance_classes.gd")
const BrowserPrototypeLods := preload("res://src/world/browser_prototype_lods.gd")

## Prototype meshes that map packages name instead of carrying.
##
## A kit prop baked once per placement cost the shipped maps 1.9 GB of
## byte-identical geometry: glTF can share a mesh between nodes of one file,
## but has no way to reach another file's mesh, so every chunk carried its own
## copy of the same tree. `eloria-assets/tools/shared_meshes.py` publishes each
## repeated mesh once as `maps/_shared/meshes/<sha>.glb`, lists it in the
## manifest's `externalMeshes`, and leaves the placement as a node with the
## same name and transform and `extras.eloria.prototype`.
##
## This pool is to those meshes what `ExternalTexturePool` is to the shared
## images: weak, content-addressed entries, so the hundred chunks that place a
## tree share one `ArrayMesh`, and a continent's prototypes die with its last
## resident cell rather than living for the session.
##
## Prototypes are IMMUTABLE. A pooled mesh is drawn by every placement in every
## resident chunk, so a pass that writes to one (`surface_set_material`, or a
## material property) changes every map at once. `WorldLoader` applies its
## material passes per instance for a pooled mesh; see `_apply_material_passes`.
##
## Images: a prototype's own images are prepared through `VramTextures` exactly
## as a map's are, from the `images` map the pool index records for it. That is
## not an optimisation but the thread rule: outside the editor GLTFDocument
## hands a URI image to ResourceLoader and then calls `get_image()` on it, an
## RD read-back that waits for the main thread, so a chunk worker parsing a
## prototype the main thread is waiting on would deadlock
## (eloria-chunk-streaming-client-traps).
##
## LODs (wave 2 WD-C5; the world-distance plan, section 3.7): before the
## parsed mesh becomes an ArrayMesh, a prototype large and dense enough
## (WorldDistanceClasses.generates_lods) gets meshoptimizer levels from
## ImporterMesh.generate_lods. They are the "cheap impostors": the vertices and
## the full index list stay exactly as parsed, so collision, paving, the look
## passes and every reader of the surfaces see the same mesh, and a level is
## drawn only where the node's lod_bias (the distance pass sets it per
## quality) and Godot's 1 px screen-error threshold allow. The geometry cook
## parses prototypes through `acquire`, so cooked prototype blobs carry the
## same levels (MapGeometryPolicy 5); a raw background chunk generates them on
## its worker, once per prototype while any placement keeps it alive. The work
## is timed as `prototype_lod_gate` / `prototype_lod_generate` and counted in
## `retention_snapshot().prototype_lods`.

static var _meshes: Dictionary = {}
static var _indexes: Dictionary = {}
static var _mutex := Mutex.new()
static var _resource_timings: Dictionary = {}
static var _lookup_hits := 0
static var _lookup_misses := 0
static var _publications := 0
static var _adoptions := 0
## Byte ledger (memory census): prototype key -> the published mesh's
## estimated GPU bytes (ResourceBytes.mesh_bytes, its shadow mesh included),
## written at publication and counted while the weak entry is alive. Only the
## geometry: a prototype's images are ExternalTexturePool's.
static var _bytes: Dictionary = {}
static var _published_bytes := 0
## Generated LODs this session (`retention_snapshot().prototype_lods`):
## prototypes given levels, prototypes the rule left whole, prototypes that
## qualified but meshoptimizer found no level for, the levels made, and their
## index bytes.
static var _lod_generated := 0
static var _lod_sidecar_hits := 0
static var _lod_sidecar_misses := 0
static var _lod_skipped := 0
static var _lod_empty := 0
static var _lod_levels := 0
static var _lod_index_bytes := 0

## Statistics for the load report, keyed as `load_phases` counters.
static var last_parsed := 0
static var last_shared := 0
## Prototypes this load gave generated LODs (`sharedMeshLods`).
static var last_lods := 0

## The index bytes a prototype's generated LODs add (an int, on the published
## ArrayMesh). The renderer keeps the levels but an ArrayMesh does not expose
## them without a read-back, so the figure is taken from the ImporterMesh as
## they are made and travels with the mesh (a cooked blob keeps it) for the
## byte ledger (`mesh_bytes`).
const LOD_BYTES_META := &"rl_lod_index_bytes"


## The pool index beside the prototypes, read once per pool directory.
static func index_for(prototype_path: String) -> Dictionary:
	var directory := prototype_path.get_base_dir()
	_mutex.lock()
	var known: Variant = _indexes.get(directory)
	_mutex.unlock()
	if known is Dictionary:
		return known
	var parsed: Dictionary = {}
	var text := FileAccess.get_file_as_string(directory.path_join("index.json"))
	if not text.is_empty():
		var data: Variant = JSON.parse_string(text)
		if data is Dictionary and (data as Dictionary).get("prototypes") is Dictionary:
			parsed = (data as Dictionary)["prototypes"]
	_mutex.lock()
	_indexes[directory] = parsed
	_mutex.unlock()
	return parsed


## The shared mesh for `key`, parsed from `path` if this is its first sharer.
##
## Safe on a worker thread: nothing here touches the scene tree, and the images
## take the prepared path rather than ResourceLoader's.
static func acquire(key: String, path: String, verified_source_sha256 := "") -> Mesh:
	if ArchivedModelPolicy.is_retired_prototype(key):
		return null
	var shared := _published(key)
	if shared != null:
		last_shared += 1
		return shared
	if not FileAccess.file_exists(path):
		push_error("shared_mesh missing prototype=%s path=%s" % [key, path])
		return null
	var entry: Dictionary = index_for(path).get(key, {})
	var image_manifest := _image_manifest(entry)
	var policy_errors := VramTextures.image_policy_errors(image_manifest, path.get_base_dir())
	if not policy_errors.is_empty():
		push_error("shared_mesh image policy invalid prototype=%s: %s" % [key, "; ".join(policy_errors)])
		return null
	if not GeometrySources.is_recording() and PreparedContent.selected_mode() != "raw":
		var token := VramTextures.cache_token(image_manifest, path.get_base_dir())
		var record := PreparedContent.acquire("mesh", path, FileAccess.get_sha256(path), token)
		if str(record.status) == "hit":
			var mesh := PreparedSharing.mesh_resource(record)
			if mesh != null:
				return _publish_or_adopt(key, mesh)
		if str(record.status) == "reject":
			return null
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if not GltfQuantization.ensure_registered():
		push_error("shared_mesh parse requires main-thread extension initialization")
		return null
	VramTextures.ensure_registered()
	var images: Variant = entry.get("images")
	if images is Dictionary and not (images as Dictionary).is_empty():
		var plan: Dictionary = VramTextures.plan_for(image_manifest)
		if not plan.is_empty():
			state.set_additional_data(VramTextures.PLAN_KEY, plan)
	var operation_began := Time.get_ticks_usec()
	var parse_error := document.append_from_file(path, state)
	_record_operation(&"prototype_gltf_parse", operation_began)
	if parse_error != OK:
		push_error("shared_mesh parse failed prototype=%s path=%s" % [key, path])
		return null
	if images is Dictionary:
		ExternalTexturePool.share(state, images)
	operation_began = Time.get_ticks_usec()
	MapMaterialPreparation.prepare(state)
	_record_operation(&"prototype_early_material_filter", operation_began)
	GeometrySources.note(state,path)
	var meshes: Array[Mesh] = []
	for imported: Variant in state.get_meshes():
		var importer := imported as GLTFMesh
		if importer == null:
			continue
		# Only the mesh the pool publishes (the first) is worth its levels, and
		# they must exist before get_mesh() builds the ArrayMesh.
		var levels := _prepare_lods(importer.mesh, path, verified_source_sha256) \
			if meshes.is_empty() and importer.mesh != null else -1
		operation_began = Time.get_ticks_usec()
		var mesh: Mesh = importer.mesh.get_mesh() if importer.mesh != null else null
		_record_operation(&"prototype_mesh_materialize", operation_began)
		if mesh != null:
			if levels > 0:
				_note_lods(importer.mesh, mesh)
			meshes.append(mesh)
	if meshes.is_empty():
		push_error("shared_mesh holds no mesh prototype=%s path=%s" % [key, path])
		return null
	last_parsed += 1
	return _publish_or_adopt(key, meshes[0])


static func _image_manifest(entry: Dictionary) -> Dictionary:
	return {"externalResources": entry.get("images", {}),
		"externalImagePolicies": entry.get("imagePolicies", {})}


static func _published(key: String) -> Mesh:
	_mutex.lock()
	var reference: WeakRef = _meshes.get(key)
	var shared: Mesh = reference.get_ref() as Mesh if reference != null else null
	if shared == null:
		_lookup_misses += 1
	else:
		_lookup_hits += 1
	_mutex.unlock()
	return shared


## Publishes `candidate` for `key` unless another sharer got there first, in
## which case the earlier mesh wins and the candidate is dropped.
static func _publish_or_adopt(key: String, candidate: Mesh) -> Mesh:
	# Measured outside the lock: CPU-side surface records only, no read-back.
	var bytes := mesh_bytes(candidate)
	_mutex.lock()
	var reference: WeakRef = _meshes.get(key)
	var shared: Mesh = reference.get_ref() as Mesh if reference != null else null
	if shared == null:
		_meshes[key] = weakref(candidate)
		_bytes[key] = bytes
		_published_bytes += bytes
		shared = candidate
		_publications += 1
	else:
		_adoptions += 1
	_mutex.unlock()
	return shared

static func _record_operation(operation: StringName, started: int) -> void:
	var elapsed := Time.get_ticks_usec() - started
	_mutex.lock()
	ResourceDiagnostics.record_elapsed(_resource_timings, operation, elapsed, true)
	_mutex.unlock()

## Gives a parsed prototype `mesh` its generated LODs when the rule
## (WorldDistanceClasses.generates_lods) asks for them; call it before
## `mesh.get_mesh()`. Returns the levels made over all surfaces (0 when
## meshoptimizer found none), or -1 when the rule leaves the mesh whole.
## CPU only (meshoptimizer on copies of the surface arrays): safe on a worker.
static func generate_lods(mesh: ImporterMesh) -> int:
	var began := Time.get_ticks_usec()
	var shape := lod_shape(mesh)
	if not DistanceClasses.generates_lods(int(shape.triangles), float(shape.radius)):
		_record_operation(&"prototype_lod_gate", began)
		_mutex.lock()
		_lod_skipped += 1
		_mutex.unlock()
		return -1
	_record_operation(&"prototype_lod_gate", began)
	began = Time.get_ticks_usec()
	mesh.generate_lods(DistanceClasses.LOD_NORMAL_MERGE_ANGLE, DistanceClasses.LOD_NORMAL_SPLIT_ANGLE, [])
	var levels := 0
	for surface: int in mesh.get_surface_count():
		levels += mesh.get_surface_lod_count(surface)
	_record_operation(&"prototype_lod_generate", began)
	_mutex.lock()
	if levels > 0:
		_lod_generated += 1
		_lod_levels += levels
	else:
		_lod_empty += 1
	_mutex.unlock()
	if levels > 0:
		last_lods += 1
	return levels

## Native generation remains unchanged. The optional browser sidecar travels
## with this exact source group, and never retains a mesh or raw source file.
static func _prepare_lods(mesh: ImporterMesh, path: String, verified_sha256 := "",
		browser := OS.has_feature("web")) -> int:
	if browser:
		var began := Time.get_ticks_usec()
		var result := BrowserPrototypeLods.apply_file(mesh, path, verified_sha256, true)
		_record_operation(&"prototype_lod_sidecar", began)
		_mutex.lock()
		if bool(result.applied): _lod_sidecar_hits += 1
		else: _lod_sidecar_misses += 1
		_mutex.unlock()
		if bool(result.applied):
			last_lods += 1
			return int(result.levels)
	return generate_lods(mesh)

## What the LOD rule reads of a parsed `mesh`: {"triangles": its triangle
## count over its triangle surfaces, "radius": its box's half-diagonal in its
## own space}. The radius is measured only once the mesh is dense enough, and
## only until it reaches the rule's limit (a box only grows).
static func lod_shape(mesh: ImporterMesh) -> Dictionary:
	var triangles := 0
	var vertex_lists: Array[PackedVector3Array] = []
	for surface: int in mesh.get_surface_count():
		if mesh.get_surface_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
			continue
		var arrays := mesh.get_surface_arrays(surface)
		var vertices: Variant = arrays[Mesh.ARRAY_VERTEX] if arrays.size() > Mesh.ARRAY_VERTEX else null
		if not vertices is PackedVector3Array:
			continue
		var indices: Variant = arrays[Mesh.ARRAY_INDEX] if arrays.size() > Mesh.ARRAY_INDEX else null
		triangles += (indices as PackedInt32Array).size() / 3 if indices is PackedInt32Array \
			else (vertices as PackedVector3Array).size() / 3
		vertex_lists.append(vertices)
	if triangles < DistanceClasses.LOD_MIN_TRIANGLES:
		return {"triangles": triangles, "radius": 0.0}
	var enough := pow(DistanceClasses.LOD_MIN_RADIUS * 2.0, 2.0)
	var low := Vector3.INF
	var high := -Vector3.INF
	var seen := 0
	for vertices: PackedVector3Array in vertex_lists:
		for vertex: Vector3 in vertices:
			low = low.min(vertex)
			high = high.max(vertex)
			seen += 1
			if seen % 64 == 0 and (high - low).length_squared() >= enough:
				break
		if (high - low).length_squared() >= enough:
			break
	var size := high - low
	return {"triangles": triangles, "radius": size.length() * 0.5 if size.is_finite() else 0.0}

## Stamps `published`, the ArrayMesh `parsed` became, with the index bytes of
## the generated levels (LOD_BYTES_META), and counts them.
static func _note_lods(parsed: ImporterMesh, published: Mesh) -> void:
	var array_mesh := published as ArrayMesh
	if array_mesh == null:
		return
	var bytes := 0
	for surface: int in mini(parsed.get_surface_count(), array_mesh.get_surface_count()):
		var indices := 0
		for level: int in parsed.get_surface_lod_count(surface):
			indices += parsed.get_surface_lod_indices(surface, level).size()
		if indices > 0:
			bytes += indices * RenderingServer.mesh_surface_get_format_index_stride(
				array_mesh.surface_get_format(surface), array_mesh.surface_get_array_len(surface))
	array_mesh.set_meta(LOD_BYTES_META, bytes)
	_mutex.lock()
	_lod_index_bytes += bytes
	_mutex.unlock()

## The ledger's figure for a prototype mesh: its surfaces and blend shapes,
## those of a distinct shadow mesh (ResourceBytes.mesh_bytes), and the index
## bytes of its generated LODs (LOD_BYTES_META; the levels of an ArrayMesh are
## not exposed otherwise).
static func mesh_bytes(mesh: Mesh) -> int:
	var bytes := ResourceBytes.mesh_bytes(mesh)
	if mesh is ArrayMesh:
		var shadow := (mesh as ArrayMesh).shadow_mesh
		if shadow != null and shadow != mesh:
			bytes += ResourceBytes.mesh_bytes(shadow)
	if mesh != null:
		bytes += int(mesh.get_meta(LOD_BYTES_META, 0))
	return bytes

## "bytes" are the ledger's estimates for the live entries ("entries");
## "published_bytes" totals every publication of the session.
## "prototype_lods" counts this session's generations (generated, skipped,
## empty, levels, index_bytes) and, read from LOD_BYTES_META, the live entries
## that carry levels however they arrived ("live_entries", "live_index_bytes"):
## a cooked arrival generates nothing, so only the live figures tell a cook
## with levels from a stale one without.
static func retention_snapshot() -> Dictionary:
	_mutex.lock()
	var live := 0
	var live_bytes := 0
	var live_lods := 0
	var live_lod_bytes := 0
	for key: String in _meshes:
		var reference: WeakRef = _meshes[key]
		var mesh: Mesh = reference.get_ref() as Mesh if reference != null else null
		if mesh != null:
			live += 1
			live_bytes += int(_bytes.get(key, 0))
			var lod_bytes := int(mesh.get_meta(LOD_BYTES_META, 0))
			if lod_bytes > 0:
				live_lods += 1
				live_lod_bytes += lod_bytes
	var result := {"weak_slots": _meshes.size(), "live_entries": live,
		"expired_slots": _meshes.size() - live, "index_directories": _indexes.size(),
		"lookup_hits": _lookup_hits, "lookup_misses": _lookup_misses,
		"publications": _publications, "concurrent_adoptions": _adoptions,
		"bytes_estimate_available": true, "entries": live, "bytes": live_bytes,
		"published_bytes": _published_bytes,
		"prototype_lods": {"generated": _lod_generated, "skipped": _lod_skipped,
			"browser_sidecar_hits": _lod_sidecar_hits, "browser_sidecar_misses": _lod_sidecar_misses,
			"empty": _lod_empty, "levels": _lod_levels, "index_bytes": _lod_index_bytes,
			"live_entries": live_lods, "live_index_bytes": live_lod_bytes},
		"timings": ResourceDiagnostics.snapshot(_resource_timings)}
	_mutex.unlock()
	return result


## The meta a resolved placement carries, naming the prototype it draws. The
## loader's material passes test for it rather than asking the pool, because
## they run per mesh instance and the answer must cost nothing.
const POOLED_META := &"shared_prototype"


static func is_pooled(node: Node) -> bool:
	return node != null and node.has_meta(POOLED_META)


static func reset_counters() -> void:
	last_parsed = 0
	last_shared = 0
	last_lods = 0


## Entries whose mesh is still alive, for the tests and the memory reports.
static func live_count() -> int:
	var live := 0
	_mutex.lock()
	for key: String in _meshes:
		var reference: WeakRef = _meshes[key]
		if reference != null and reference.get_ref() != null:
			live += 1
	_mutex.unlock()
	return live

static func source_keys() -> Dictionary:
	var result := {}
	_mutex.lock()
	for key: String in _meshes:
		var reference: WeakRef = _meshes[key]
		var mesh: Mesh = reference.get_ref() as Mesh if reference != null else null
		if mesh != null: result[mesh.get_instance_id()] = key
	_mutex.unlock()
	return result
