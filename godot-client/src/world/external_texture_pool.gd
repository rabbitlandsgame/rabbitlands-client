extends RefCounted

const VramTextures := preload("res://src/world/vram_textures.gd")
const GraphicsOptions := preload("res://src/world/graphics_options.gd")

## External PNGs are immutable, content-addressed build products. Weak entries
## share actual GPU textures across separately imported chunks without keeping
## a continent's textures alive after its last resident cell is retired.
static var _textures: Dictionary = {}
static var _mutex := Mutex.new()
static var _lookup_hits := 0
static var _lookup_misses := 0
static var _publications := 0
static var _adoptions := 0
static var _image_paths: Dictionary = {}
static var _image_load_calls := 0
static var _image_path_hits := 0
static var _image_hash_reads := 0
static var _image_decodes := 0
static var _image_resource_fallbacks := 0
static var _image_uploads := 0

## Runtime-owned shared maps use the same weak content cache as glTF textures.
## Assets are immutable for a running session, just like texture quality.
## Weak path aliases avoid rereading/hashing a named image for every chunk.
static func load_image(path: String) -> ImageTexture:
	var path_key := "%s|mip-skip=%d" % [path.simplify_path(), GraphicsOptions.active_texture_skip()]
	_mutex.lock()
	_image_load_calls += 1
	var reference: WeakRef = _image_paths.get(path_key)
	var shared: ImageTexture = reference.get_ref() as ImageTexture if reference != null else null
	if shared != null:
		_image_path_hits += 1
	_mutex.unlock()
	if shared != null:
		return shared
	# Decode and upload outside the lock: texture creation is a rendering-server
	# round trip that only the main thread can serve, so a worker holding the
	# lock across it would deadlock a main thread waiting for the lock.
	var image: Image = null
	var key := "imported-image|" + path_key
	if FileAccess.file_exists(path):
		_note_image_work(&"hash")
		key = FileAccess.get_sha256(path)
		if key.is_empty():
			return null
		shared = _published(key)
		if shared != null:
			return _remember_image_path(path_key, shared)
		# The packager deliberately ships these raw files loose. Decode their
		# bytes using the same mip/tier preparation as other external images;
		# Image.load_from_file(res://...) incorrectly treats this as an import.
		_note_image_work(&"decode")
		image = VramTextures.decode_source(path).image
	elif path.begins_with("res://") and ResourceLoader.exists(path, "Texture2D"):
		# Also support ordinary Godot exports that contain only an imported
		# texture. Read back/prepare it once, never on a live path-cache hit.
		shared = _published(key)
		if shared != null:
			return _remember_image_path(path_key, shared)
		_note_image_work(&"resource")
		var imported := ResourceLoader.load(path, "Texture2D") as Texture2D
		if imported != null:
			image = imported.get_image()
		if image != null and not image.is_empty():
			if image.is_compressed() and image.decompress() != OK:
				return null
			if not image.has_mipmaps():
				image.generate_mipmaps()
			image = GraphicsOptions.reduced_image(image)
	if image == null or image.is_empty():
		return null
	_note_image_work(&"upload")
	return _remember_image_path(path_key, _publish_or_adopt(key, ImageTexture.create_from_image(image)))


static func _remember_image_path(path_key: String, texture: ImageTexture) -> ImageTexture:
	_mutex.lock()
	_image_paths[path_key] = weakref(texture)
	_mutex.unlock()
	return texture


static func _note_image_work(kind: StringName) -> void:
	_mutex.lock()
	match kind:
		&"hash": _image_hash_reads += 1
		&"decode": _image_decodes += 1
		&"resource": _image_resource_fallbacks += 1
		&"upload": _image_uploads += 1
	_mutex.unlock()


static func _published(key: String) -> ImageTexture:
	_mutex.lock()
	var reference: WeakRef = _textures.get(key)
	var shared: ImageTexture = reference.get_ref() as ImageTexture if reference != null else null
	if shared == null:
		_lookup_misses += 1
	else:
		_lookup_hits += 1
	_mutex.unlock()
	return shared


## Publishes `candidate` for `key` unless another sharer got there first, in
## which case the earlier texture wins and the candidate is dropped.
static func _publish_or_adopt(key: String, candidate: ImageTexture) -> ImageTexture:
	_mutex.lock()
	var reference: WeakRef = _textures.get(key)
	var shared: ImageTexture = reference.get_ref() as ImageTexture if reference != null else null
	if shared == null:
		_textures[key] = weakref(candidate)
		shared = candidate
		_publications += 1
	else:
		_adoptions += 1
	_mutex.unlock()
	return shared

## Counts weak slots separately from live GPU resources. No readback, file IO,
## mutation/pruning, or retained strong references are added by this snapshot.
static func retention_snapshot() -> Dictionary:
	_mutex.lock()
	var live := 0
	for reference: WeakRef in _textures.values():
		if reference != null and reference.get_ref() != null:
			live += 1
	var result := {"weak_slots": _textures.size(), "live_entries": live,
		"expired_slots": _textures.size() - live, "lookup_hits": _lookup_hits,
		"lookup_misses": _lookup_misses, "publications": _publications,
		"concurrent_adoptions": _adoptions, "bytes_estimate_available": false,
		"image_path_slots": _image_paths.size(), "image_load_calls": _image_load_calls,
		"image_path_hits": _image_path_hits, "image_hash_reads": _image_hash_reads,
		"image_decodes": _image_decodes, "image_resource_fallbacks": _image_resource_fallbacks,
		"image_uploads": _image_uploads}
	_mutex.unlock()
	return result

static func source_description(texture: Texture2D) -> Dictionary:
	# Offline origin discovery only. Never hold this lock across file IO or
	# rendering-server calls; ordinary texture lookup keeps its existing path.
	var path := ""
	_mutex.lock()
	for key: String in _image_paths:
		var reference: WeakRef = _image_paths[key]
		if reference != null and reference.get_ref() == texture:
			path = key.get_slice("|mip-skip=",0)
			break
	_mutex.unlock()
	return {"path":path,"sha":FileAccess.get_sha256(path)} if not path.is_empty() else {}

static func share(state: GLTFState, resources: Dictionary) -> int:
	if resources.is_empty():
		return 0
	var descriptors: Array = state.get_json().get("images", [])
	var images: Array[Texture2D] = state.get_images()
	var replacements: Dictionary = {}
	var reused := 0
	# Images map_image_extension.gd produced already carry their mip chain
	# (nothing to read back), and the ones it found in this pool are 1x1
	# placeholders it holds the pooled texture for.
	var done_value: Variant = state.get_additional_data(VramTextures.DONE_KEY)
	var done: Dictionary = done_value if done_value is Dictionary else {}
	var pooled_value: Variant = state.get_additional_data(VramTextures.POOLED_KEY)
	var pooled: Dictionary = pooled_value if pooled_value is Dictionary else {}
	# Decoded for this map alone: the pool holds a sidecar of this hash that was
	# encoded for other roles (VramTextures.pooled_fits). Keep it, publish nothing.
	var private_value: Variant = state.get_additional_data(VramTextures.PRIVATE_KEY)
	var private: Dictionary = private_value if private_value is Dictionary else {}
	for index: int in mini(descriptors.size(), images.size()):
		var uri := str(descriptors[index].get("uri", ""))
		if not resources.has(uri) or not images[index] is ImageTexture or private.has(index):
			continue
		var key := str(resources[uri])
		var current := images[index] as ImageTexture
		# The held reference, never a fresh lookup: a placeholder must not be
		# published as the texture for its hash.
		var shared: ImageTexture = pooled.get(index) as ImageTexture
		if shared == null:
			shared = _published(key)
		if shared == null:
			# Finish the mip chain before publishing an immutable shared texture.
			# Parallel region builders must never resize a texture another uses.
			# This uploads through the rendering server, so it happens outside
			# the lock; a concurrent publisher of the same hash wins below.
			var image: Image = null if done.has(index) else current.get_image()
			if image != null and not image.is_empty() and not image.has_mipmaps():
				if not image.is_compressed() or image.decompress() == OK:
					image.generate_mipmaps()
					current.set_image(image)
			shared = _publish_or_adopt(key, current)
		if shared != current:
			replacements[current.get_instance_id()] = shared
			images[index] = shared
			reused += 1
	if replacements.is_empty():
		return 0
	state.set_images(images)
	# append_from_file has already bound the textures to materials. Replacing
	# the state image list alone would leave those original GPU allocations live.
	for material: Material in state.get_materials():
		if not material is BaseMaterial3D:
			continue
		for property: Dictionary in material.get_property_list():
			if not str(property.name).ends_with("_texture"):
				continue
			var texture: Variant = material.get(property.name)
			if texture is Texture2D and replacements.has(texture.get_instance_id()):
				material.set(property.name, replacements[texture.get_instance_id()])
	return reused
