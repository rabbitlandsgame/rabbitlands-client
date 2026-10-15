extends RefCounted

const VramTextures := preload("res://src/world/vram_textures.gd")

## External PNGs are immutable, content-addressed build products. Weak entries
## share actual GPU textures across separately imported chunks without keeping
## a continent's textures alive after its last resident cell is retired.
static var _textures: Dictionary = {}
static var _mutex := Mutex.new()

## Runtime-owned shared maps use the same weak content cache as glTF textures.
## Loading directly keeps this available before an editor PNG import exists.
static func load_image(path: String) -> ImageTexture:
	var key := FileAccess.get_sha256(path)
	if key.is_empty():
		return null
	var shared := _published(key)
	if shared != null:
		return shared
	# Decode and upload outside the lock: texture creation is a rendering-server
	# round trip that only the main thread can serve, so a worker holding the
	# lock across it would deadlock a main thread waiting for the lock.
	var image := Image.load_from_file(path)
	if image == null or image.is_empty():
		return null
	if not image.has_mipmaps():
		image.generate_mipmaps()
	return _publish_or_adopt(key, ImageTexture.create_from_image(image))


static func _published(key: String) -> ImageTexture:
	_mutex.lock()
	var reference: WeakRef = _textures.get(key)
	var shared: ImageTexture = reference.get_ref() as ImageTexture if reference != null else null
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
	_mutex.unlock()
	return shared

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
