extends RefCounted

const VramTextures := preload("res://src/world/vram_textures.gd")
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")

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

static var _meshes: Dictionary = {}
static var _indexes: Dictionary = {}
static var _mutex := Mutex.new()

## Statistics for the load report, keyed as `load_phases` counters.
static var last_parsed := 0
static var last_shared := 0


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
static func acquire(key: String, path: String) -> Mesh:
	if ArchivedModelPolicy.is_retired_prototype(key):
		return null
	var shared := _published(key)
	if shared != null:
		last_shared += 1
		return shared
	if not FileAccess.file_exists(path):
		push_error("shared_mesh missing prototype=%s path=%s" % [key, path])
		return null
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	GltfQuantization.ensure_registered()
	VramTextures.ensure_registered()
	var entry: Dictionary = index_for(path).get(key, {})
	var images: Variant = entry.get("images")
	if images is Dictionary and not (images as Dictionary).is_empty():
		var plan: Dictionary = VramTextures.plan_for({"externalResources": images})
		if not plan.is_empty():
			state.set_additional_data(VramTextures.PLAN_KEY, plan)
	if document.append_from_file(path, state) != OK:
		push_error("shared_mesh parse failed prototype=%s path=%s" % [key, path])
		return null
	if images is Dictionary:
		ExternalTexturePool.share(state, images)
	var meshes: Array[Mesh] = []
	for imported: Variant in state.get_meshes():
		var importer := imported as GLTFMesh
		if importer == null:
			continue
		var mesh: Mesh = importer.mesh.get_mesh() if importer.mesh != null else null
		if mesh != null:
			meshes.append(mesh)
	if meshes.is_empty():
		push_error("shared_mesh holds no mesh prototype=%s path=%s" % [key, path])
		return null
	last_parsed += 1
	return _publish_or_adopt(key, meshes[0])


static func _published(key: String) -> Mesh:
	_mutex.lock()
	var reference: WeakRef = _meshes.get(key)
	var shared: Mesh = reference.get_ref() as Mesh if reference != null else null
	_mutex.unlock()
	return shared


## Publishes `candidate` for `key` unless another sharer got there first, in
## which case the earlier mesh wins and the candidate is dropped.
static func _publish_or_adopt(key: String, candidate: Mesh) -> Mesh:
	_mutex.lock()
	var reference: WeakRef = _meshes.get(key)
	var shared: Mesh = reference.get_ref() as Mesh if reference != null else null
	if shared == null:
		_meshes[key] = weakref(candidate)
		shared = candidate
	_mutex.unlock()
	return shared


## The meta a resolved placement carries, naming the prototype it draws. The
## loader's material passes test for it rather than asking the pool, because
## they run per mesh instance and the answer must cost nothing.
const POOLED_META := &"shared_prototype"


static func is_pooled(node: Node) -> bool:
	return node != null and node.has_meta(POOLED_META)


static func reset_counters() -> void:
	last_parsed = 0
	last_shared = 0


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
