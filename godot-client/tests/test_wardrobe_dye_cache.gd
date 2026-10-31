extends SceneTree
## CPU-only persistent image contracts. Run with an isolated XDG_DATA_HOME and
## ELORIA_WARDROBE_TEST_ROOT set to that same root. No player settings or GPU
## resources are read, modified or created.
const Cache := preload("res://src/actors/wardrobe_dye_cache.gd")
var checks := 0
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("wardrobe dye cache: " + message)

func _source(offset := 0) -> Image:
	var image := Image.create(5, 3, false, Image.FORMAT_RGBA8)
	for y: int in 3:
		for x: int in 5:
			image.set_pixel(x, y, Color(float((x * 43 + offset) % 255) / 255.0,
				float((y * 71 + offset) % 255) / 255.0, float((x + y) * 19) / 255.0,
				float((x + 2 * y) % 4) / 3.0))
	return image

## Frozen pre-cache calculation, independent of cached framing/serialization.
func _reference(original: Image) -> Image:
	var neutral := original.duplicate() as Image
	if neutral.is_compressed():
		neutral.decompress()
	neutral.convert(Image.FORMAT_RGBA8)
	var reference := 0.0
	var count := 0
	for y: int in neutral.get_height():
		for x: int in neutral.get_width():
			var pixel := neutral.get_pixel(x, y)
			if pixel.a > 0.0:
				reference += pixel.get_luminance()
				count += 1
	reference = maxf(0.01, reference / maxi(1, count))
	for y: int in neutral.get_height():
		for x: int in neutral.get_width():
			var pixel := neutral.get_pixel(x, y)
			var value := clampf(pixel.get_luminance() / reference, 0.0, 1.0)
			neutral.set_pixel(x, y, Color(value, value, value, pixel.a))
	neutral.generate_mipmaps()
	return neutral

func _path(source: Image) -> String:
	return Cache.ROOT.path_join(Cache.source_key(source) + ".rwd")

func _bytes(path: String) -> PackedByteArray:
	return FileAccess.get_file_as_bytes(path)

func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	_check(file != null, "owned test file opens")
	if file != null:
		file.store_buffer(bytes)
		file.close()

func _same(actual: Image, expected: Image, message: String) -> void:
	_check(actual != null, message + " image exists")
	if actual == null:
		return
	_check(actual.get_size() == expected.get_size() and actual.get_format() == expected.get_format(),
		message + " layout is exact")
	_check(actual.has_mipmaps() == expected.has_mipmaps()
		and actual.get_mipmap_count() == expected.get_mipmap_count(), message + " complete mip metadata is exact")
	_check(actual.get_data() == expected.get_data(), message + " all pixel/alpha/mip bytes are exact")

func _mutate_metadata(valid: PackedByteArray, changes: Dictionary) -> PackedByteArray:
	var size := valid.decode_u32(8)
	var metadata: Dictionary = JSON.parse_string(valid.slice(Cache.HEADER_BYTES, Cache.HEADER_BYTES + size).get_string_from_utf8())
	metadata.merge(changes, true)
	var encoded := JSON.stringify(metadata, "", true, true).to_utf8_buffer()
	var bytes := valid.slice(0, Cache.HEADER_BYTES)
	bytes.encode_u32(8, encoded.size())
	bytes.append_array(encoded)
	bytes.append_array(valid.slice(Cache.HEADER_BYTES + size))
	return bytes

func _run() -> void:
	var isolated := OS.get_environment("ELORIA_WARDROBE_TEST_ROOT").trim_suffix("/")
	if isolated.is_empty() or not OS.get_user_data_dir().begins_with(isolated + "/"):
		push_error("Use isolated XDG_DATA_HOME and matching ELORIA_WARDROBE_TEST_ROOT")
		quit(1)
		return
	var prior_switch := OS.get_environment("ELORIA_WARDROBE_TEXTURE_CACHE")
	var source := _source()
	var original_bytes := source.get_data()
	var reference := _reference(source)
	var path := _path(source)
	DirAccess.remove_absolute(path)
	OS.set_environment("ELORIA_WARDROBE_TEXTURE_CACHE", "0")
	_check(not Cache.enabled(), "cache is explicitly disabled")
	_check(Cache.load_image(source) == null and not Cache.store_image(source, reference), "off uses ordinary computation")
	_check(not FileAccess.file_exists(path), "disabled feature writes no cache entry")
	OS.set_environment("ELORIA_WARDROBE_TEXTURE_CACHE", "1")
	_check(Cache.load_image(source) == null, "fresh source is a cache miss")
	_check(Cache.store_image(source, reference), "computed neutral atlas persists")
	var copy := source.duplicate() as Image
	_check(copy.get_instance_id() != source.get_instance_id()
		and Cache.source_key(copy) == Cache.source_key(source), "identity survives a new Image resource")
	_same(Cache.load_image(copy), reference, "fresh-resource hit")
	_check(source.get_data() == original_bytes, "source atlas was never modified")
	var valid := _bytes(path)
	var changed := source.duplicate() as Image
	changed.set_pixel(0, 0, Color(1, 0, 1, 0.5))
	_check(Cache.source_key(changed) != Cache.source_key(source) and Cache.load_image(changed) == null,
		"changed source bytes cannot reuse an old entry")
	var reshaped := Image.create_from_data(3, 5, false, Image.FORMAT_RGBA8, original_bytes)
	_check(Cache.source_key(reshaped) != Cache.source_key(source), "dimensions participate in identity")
	var with_mips := source.duplicate() as Image
	with_mips.generate_mipmaps()
	_check(Cache.source_key(with_mips) != Cache.source_key(source), "source mip layout and bytes participate in identity")
	var source_mips := with_mips.get_data()
	source_mips[source_mips.size() - 1] ^= 1
	var changed_mip := Image.create_from_data(5, 3, true, Image.FORMAT_RGBA8, source_mips)
	_check(Cache.source_key(changed_mip) != Cache.source_key(with_mips), "a changed non-base source mip invalidates identity")
	_check(Cache.source_key(Image.create(Cache.MAX_SIDE + 1, 1, false, Image.FORMAT_RGBA8)).is_empty(),
		"oversized source rejected before hashing")
	_check(Cache.source_key(Image.create(2, 2, false, Image.FORMAT_RGBAF)).is_empty(),
		"large-channel source formats retain bounded fallback")
	var bad_payload := valid.duplicate()
	bad_payload[bad_payload.size() - 1] ^= 1
	_write(path, bad_payload)
	_check(Cache.load_image(source) == null, "checksum catches a changed last mip/alpha byte")
	var bad_header := valid.duplicate()
	bad_header.encode_u32(4, Cache.VERSION + 1)
	_write(path, bad_header)
	_check(Cache.load_image(source) == null, "unknown cache generation rejected")
	bad_header = valid.duplicate()
	bad_header.encode_u32(8, Cache.MAX_METADATA_BYTES + 1)
	_write(path, bad_header)
	_check(Cache.load_image(source) == null, "metadata allocation bound enforced")
	bad_header = valid.duplicate()
	bad_header.encode_u32(12, Cache.MAX_PIXEL_BYTES + 1)
	_write(path, bad_header)
	_check(Cache.load_image(source) == null, "pixel allocation bound enforced")
	for changes: Dictionary in [{"width": 999999999}, {"format": Image.FORMAT_RGB8},
			{"mipmaps": false}, {"mipmap_count": 0}, {"bytes": 1}, {"sha256": "invalid"},
			{"policy": "older-recipe"}, {"key": "0".repeat(64)}]:
		_write(path, _mutate_metadata(valid, changes))
		_check(Cache.load_image(source) == null, "invalid metadata safely misses: " + str(changes.keys()[0]))
	_write(path, valid.slice(0, valid.size() - 1))
	_check(Cache.load_image(source) == null, "truncated payload safely misses")
	var trailing := valid.duplicate()
	trailing.append(0)
	_write(path, trailing)
	_check(Cache.load_image(source) == null, "trailing bytes rejected")
	# Invalid cached bytes must be replaceable by the ordinary fresh result.
	_check(Cache.store_image(source, reference), "fallback calculation replaces a corrupt entry")
	_same(Cache.load_image(source), reference, "recomputed replacement")
	# A directory occupying an entry's destination makes publication fail after
	# its temporary write. It must not affect generated pixels or leave debris.
	DirAccess.remove_absolute(path)
	_check(DirAccess.make_dir_absolute(path) == OK, "owned blocked-publication fixture created")
	_check(not Cache.store_image(source, reference), "unwritable destination is a harmless cache failure")
	_check(DirAccess.remove_absolute(path) == OK, "owned blocked-publication fixture removed")
	var directory := DirAccess.open(Cache.ROOT)
	for name: String in directory.get_files():
		_check(not name.ends_with(".tmp"), "failed/successful publication leaves no temporary entry")
	_check(Cache.store_image(source, reference), "subsequent writable publication recovers")
	_same(Cache.load_image(source), reference, "publication recovery")
	var one_pixel := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	one_pixel.set_pixel(0, 0, Color(0.2, 0.3, 0.5, 0.4))
	var one_reference := _reference(one_pixel)
	_check(Cache.store_image(one_pixel, one_reference), "single-pixel terminal mip supported")
	_same(Cache.load_image(one_pixel), one_reference, "single-pixel round trip")
	OS.set_environment("ELORIA_WARDROBE_TEXTURE_CACHE", prior_switch)
	print("wardrobe dye cache: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
