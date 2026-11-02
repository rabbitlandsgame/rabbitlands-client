extends SceneTree
## The neutral wardrobe atlas (ReplicatedActor3D._neutral_wardrobe_image) is
## byte for byte what the per-pixel get_pixel/set_pixel loop it replaced made:
## on the real TintableAtlas of both luminous race GLBs (as decoded, and with a
## mip chain), on images with partial and zero alpha, a fully transparent one
## (the 0.01 floor), a block-compressed one, one with uneven bands, and an
## alpha-bearing atlas large enough for several bands. Its luminance tables
## give Color.get_luminance for every one of the 2^24 RGB values. The neutral
## atlas is shared by content:
## byte-identical sources from different textures (each race GLB, each parse
## after a session released them) make it once, bounded.
##
##   Godot --headless --path godot-client --script res://tests/test_wardrobe_dye_neutral.gd

const RACES := "res://assets/actors/native/races/"
var checks := 0
var failures := 0


func _init() -> void:
	_run.call_deferred()


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("wardrobe dye neutral: " + message)


## The calculation as it stood before the tables (frozen copy).
static func _reference(original: Image) -> Image:
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


## The embedded TintableAtlas of a race GLB, decoded as GLTFDocument decodes it.
static func _tintable_atlas(file: String) -> Image:
	var bytes := FileAccess.get_file_as_bytes(ProjectSettings.globalize_path(RACES + file))
	if bytes.size() < 28:
		return null
	var json_length := bytes.decode_u32(12)
	var document: Variant = JSON.parse_string(bytes.slice(20, 20 + json_length).get_string_from_utf8())
	if document is not Dictionary:
		return null
	var binary := 20 + json_length + 8
	for material: Dictionary in document.get("materials", []):
		if str(material.get("name", "")) != "TintableAtlas":
			continue
		var texture: Dictionary = document.textures[int(material.pbrMetallicRoughness.baseColorTexture.index)]
		var view: Dictionary = document.bufferViews[int(document.images[int(texture.source)].bufferView)]
		var start := binary + int(view.get("byteOffset", 0))
		var image := Image.new()
		if image.load_jpg_from_buffer(bytes.slice(start, start + int(view.byteLength))) != OK:
			return null
		return image
	return null


func _same(actual: Image, expected: Image, message: String) -> void:
	_check(actual != null, message + ": made")
	if actual == null:
		return
	_check(actual.get_size() == expected.get_size() and actual.get_format() == expected.get_format()
		and actual.get_mipmap_count() == expected.get_mipmap_count(), message + ": same layout")
	var ours := actual.get_data()
	var theirs := expected.get_data()
	var differing := 0
	if ours.size() == theirs.size():
		for index: int in ours.size():
			differing += 1 if ours[index] != theirs[index] else 0
	_check(ours.size() == theirs.size() and differing == 0,
		message + ": every byte identical (%d differ)" % differing)


func _compare(source: Image, message: String) -> void:
	var began := Time.get_ticks_usec()
	var expected := _reference(source)
	var old_ms := (Time.get_ticks_usec() - began) / 1000.0
	began = Time.get_ticks_usec()
	var actual := ReplicatedActor3D._neutral_wardrobe_image(source)
	var new_ms := (Time.get_ticks_usec() - began) / 1000.0
	print("wardrobe dye neutral: %s %dx%d: per-pixel loop %.0f ms, tables in bands %.0f ms"
		% [message, source.get_width(), source.get_height(), old_ms, new_ms])
	_same(actual, expected, message)


func _run() -> void:
	# Tables first, so the timings below are the per-atlas work.
	ReplicatedActor3D._neutral_wardrobe_image(Image.create(1, 1, false, Image.FORMAT_RGBA8))
	_check_luminance_tables()
	var atlases := {}
	for file: String in ["luminous_male.glb", "luminous_female.glb"]:
		var atlas := _tintable_atlas(file)
		_check(atlas != null and atlas.get_width() >= 1024, "%s has its TintableAtlas" % file)
		if atlas == null:
			continue
		atlases[file] = atlas
		_compare(atlas, file)
	if atlases.has("luminous_female.glb"):
		var mipped := (atlases["luminous_female.glb"] as Image).duplicate() as Image
		mipped.generate_mipmaps()
		_compare(mipped, "female atlas with mipmaps")
		var small := (atlases["luminous_female.glb"] as Image).duplicate() as Image
		small.resize(256, 256)
		small.convert(Image.FORMAT_RGBA8)
		var compressed := small.duplicate() as Image
		if compressed.compress(Image.COMPRESS_S3TC) == OK and compressed.is_compressed():
			_compare(compressed, "block-compressed atlas")
		var uneven := (atlases["luminous_female.glb"] as Image).duplicate() as Image
		uneven.resize(1024, 777)
		_compare(uneven, "uneven bands")
		# Alpha in several bands: the mean over the pixels with alpha only.
		var holes := (atlases["luminous_female.glb"] as Image).duplicate() as Image
		holes.resize(512, 512)
		holes.convert(Image.FORMAT_RGBA8)
		holes.fill_rect(Rect2i(0, 100, 512, 37), Color(0.9, 0.2, 0.1, 0.0))
		holes.fill_rect(Rect2i(300, 0, 12, 512), Color(0.1, 0.8, 0.3, 0.5))
		_compare(holes, "alpha across bands")
	_compare(_synthetic(37, 23, 0), "partial and zero alpha")
	_compare(_synthetic(5, 3, 1), "odd size")
	var clear := Image.create(9, 7, false, Image.FORMAT_RGBA8)
	clear.fill(Color(0.4, 0.3, 0.2, 0.0))
	_compare(clear, "fully transparent (0.01 floor)")
	var dark := Image.create(16, 16, false, Image.FORMAT_RGB8)
	dark.fill(Color(1.0 / 255.0, 0.0, 2.0 / 255.0))
	dark.set_pixel(3, 3, Color(1, 1, 1))
	_compare(dark, "near black with one white pixel")
	await _check_sharing(atlases.get("luminous_male.glb"))
	print("wardrobe dye neutral: %d checks, %d failures" % [checks, failures])
	print("wardrobe dye neutral: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures else 0)


static func _synthetic(width: int, height: int, seed_value: int) -> Image:
	var image := Image.create(width, height, false, Image.FORMAT_RGBA8)
	var random := RandomNumberGenerator.new()
	random.seed = 9271 + seed_value
	for y: int in height:
		for x: int in width:
			var alpha: int = [0, 1, 37, 128, 254, 255][random.randi_range(0, 5)]
			image.set_pixel(x, y, Color8(random.randi_range(0, 255), random.randi_range(0, 255),
				random.randi_range(0, 255), alpha))
	return image


## The red-green and blue tables against Color.get_luminance for every RGB.
func _check_luminance_tables() -> void:
	var tables: Array = ReplicatedActor3D._wardrobe_luminance
	var red_green: PackedFloat64Array = tables[0]
	var blue: PackedFloat64Array = tables[1]
	var rounded := PackedFloat32Array()
	rounded.resize(1)
	var bytes := PackedByteArray()
	bytes.resize(65536 * 4)
	bytes.fill(255)
	for index: int in 65536:
		bytes[index * 4] = index & 0xFF
		bytes[index * 4 + 1] = index >> 8
	var mismatched := 0
	var began := Time.get_ticks_msec()
	for level: int in 256:
		for index: int in 65536:
			bytes[index * 4 + 2] = level
		var image := Image.create_from_data(256, 256, false, Image.FORMAT_RGBA8, bytes)
		for index: int in 65536:
			rounded[0] = red_green[index] + blue[level]
			if rounded[0] != image.get_pixel(index & 0xFF, index >> 8).get_luminance():
				mismatched += 1
	_check(mismatched == 0, "the tables give get_luminance for all 2^24 RGB values (%d differ, %d ms)"
		% [mismatched, Time.get_ticks_msec() - began])


func _check_sharing(atlas: Image) -> void:
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	var small := atlas.duplicate() as Image if atlas != null else _synthetic(64, 64, 2)
	small.resize(128, 128)
	var first := ImageTexture.create_from_image(small)
	var twin := ImageTexture.create_from_image(small.duplicate() as Image)
	var neutral := ReplicatedActor3D._wardrobe_dye_texture(first)
	_check(neutral != null and neutral != first, "a neutral atlas is made")
	_check(ReplicatedActor3D._wardrobe_dye_texture(twin) == neutral,
		"a byte-identical source in another texture shares the same neutral atlas")
	_check(ReplicatedActor3D._wardrobe_dye_texture(neutral) == neutral, "a neutral atlas is its own neutral atlas")
	_check(ReplicatedActor3D._wardrobe_texture_cache.size() == 1, "one entry for one content")
	var other := ImageTexture.create_from_image(_synthetic(32, 32, 3))
	_check(ReplicatedActor3D._wardrobe_dye_texture(other) != neutral, "different content, a different atlas")
	if neutral != null:
		_same(neutral.get_image(), _reference(small), "shared texture's pixels")
	for index: int in ReplicatedActor3D.WARDROBE_TEXTURE_CACHE_LIMIT + 3:
		ReplicatedActor3D._wardrobe_dye_texture(ImageTexture.create_from_image(_synthetic(8, 8, 10 + index)))
	_check(ReplicatedActor3D._wardrobe_texture_cache.size() == ReplicatedActor3D.WARDROBE_TEXTURE_CACHE_LIMIT,
		"the cache holds at most WARDROBE_TEXTURE_CACHE_LIMIT atlases (%d)"
		% ReplicatedActor3D._wardrobe_texture_cache.size())
	first = null
	twin = null
	other = null
	await process_frame
	for index: int in ReplicatedActor3D.WARDROBE_TEXTURE_KEY_LIMIT + 8:
		ReplicatedActor3D._wardrobe_dye_texture(ImageTexture.create_from_image(_synthetic(4, 4, 100 + index % 3)))
	_check(ReplicatedActor3D._wardrobe_texture_keys.size() <= ReplicatedActor3D.WARDROBE_TEXTURE_KEY_LIMIT,
		"remembered texture ids stay bounded (%d)" % ReplicatedActor3D._wardrobe_texture_keys.size())
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	_check(ReplicatedActor3D._wardrobe_texture_cache.is_empty() and ReplicatedActor3D._wardrobe_texture_keys.is_empty(),
		"clear_wardrobe_texture_cache empties both")
