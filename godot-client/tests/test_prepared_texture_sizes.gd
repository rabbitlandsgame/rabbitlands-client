extends SceneTree
## Real renderer/tool build: preserve NPOT logical size through compressed GPU
## readback, conversion, duplicate and binary native save/load, without changing
## actual compressed format/mip/data bytes. No tolerance weakening.
const Sizes := preload("res://src/world/prepared_texture_sizes.gd")
var failures := 0
func _init() -> void:
	_run.call_deferred()
func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("prepared texture size: " + message)
func _signature(image: Image) -> Dictionary:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(image.get_data())
	return {"width": image.get_width(), "height": image.get_height(), "format": image.get_format(),
		"mipmaps": image.get_mipmap_count(), "bytes": image.get_data_size(),
		"sha256": hashing.finish().hex_encode()}
func _run() -> void:
	var image := Image.create(1254, 126, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.2, 0.6, 0.4, 1))
	image.generate_mipmaps()
	var compressed := image.compress(Image.COMPRESS_S3TC)
	_expect(compressed == OK and image.is_compressed(), "real compressed NPOT source exists")
	if compressed != OK:
		quit(1)
		return
	var source := ImageTexture.create_from_image(image)
	# Compression has already padded the Image. Model the original texture's
	# separately retained authored extent, as in an imported NPOT texture.
	source.set_size_override(Vector2i(1254, 126))
	var readback := source.get_image()
	_expect(source.get_width() == 1254 and source.get_height() == 126 and readback != null,
		"source retains authored logical dimensions")
	if readback == null:
		quit(1)
		return
	var storage := _signature(readback)
	var logical := Vector2i(source.get_width(), source.get_height())
	# Exercise the non-ImageTexture conversion operation as well as duplicate:
	# both are the producer's actual creation paths, sharing the same helper.
	var converted := ImageTexture.create_from_image(readback)
	var duplicated := source.duplicate(false) as ImageTexture
	_expect(Sizes.prepare(source, converted) and Sizes.prepare(source, duplicated),
		"both conversion and duplication receive the explicit source logical size")
	for candidate: ImageTexture in [converted, duplicated]:
		_expect(candidate.get_width() == logical.x and candidate.get_height() == logical.y
			and _signature(candidate.get_image()) == storage,
			"logical override preserves exact compressed storage format/mips/data")
		var path := "user://prepared-npot-%d.res" % candidate.get_instance_id()
		_expect(ResourceSaver.save(candidate, path) == OK, "native texture payload saves")
		var loaded := ResourceLoader.load(path, "ImageTexture", ResourceLoader.CACHE_MODE_IGNORE) as ImageTexture
		_expect(loaded != null and loaded.has_meta(Sizes.LOGICAL_SIZE)
			and not loaded.has_meta(Sizes.PUBLISHED_SIZE), "logical data persists; runtime publication marker does not")
		if loaded == null:
			continue
		_expect(Sizes.restore_verified(loaded) and loaded.get_width() == logical.x and loaded.get_height() == logical.y
			and _signature(loaded.get_image()) == storage, "verified native reload restores exact logical and storage identity")
		_expect(Sizes.restore_verified(loaded), "repeated lookup is idempotent after first publication")
		loaded.set_size_override(logical + Vector2i.ONE)
		_expect(not Sizes.restore_verified(loaded) and loaded.get_width() == logical.x + 1,
			"later mutation is rejected without rewriting an already published shared texture")
	await process_frame
	await process_frame
	print("prepared texture size tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)
