extends SceneTree

## Encodes map texture sidecars for tools/build_vram_textures.py, one batch of
## jobs per process. Not client code: it runs at package time, headless, on
## the 4.7.2 EDITOR binary, because the export templates carry no BC encoder
## (Image.compress returns ERR_UNAVAILABLE there).
##
## env VRAM_JOBS: path of a JSON array of {sha, src, recipe, evt, dds}.
##   recipe  base        opaque base colour / emissive -> BC7 (RGB)
##           base_alpha  base colour whose alpha is used -> BC7 (RGBA)
##           orm         occlusion / roughness / metallic -> BC1 (RGB, forced:
##                       left to channel detection an ORM with an empty
##                       metallic channel comes out BC5, twice the size)
##           orm_bc7     an ORM map BC1 could not keep -> BC7 (RGB)
##           normal      tangent-space normal -> BC5 (RG; Godot rebuilds Z)
##   evt     where the sidecar goes: 16-byte header ('EVT1', raw DDS size,
##           flags bit0 = zstd, reserved) + one zstd frame of the DDS
##   dds     where the raw DDS goes, for the caller's quality check
##
## The image is decoded the way the client decodes it (by its magic bytes) and
## the mip chain is Image.generate_mipmaps() on the decoded image, exactly as
## the client builds it today, so block compression is the only difference a
## player can see. zstd runs at the level the encoder project sets (19).
##
## Prints one "VRAM_RESULT <json>" line per job and "VRAM_DONE <n>" at the end.

const HEADER_BYTES := 16
const FLAG_ZSTD := 1
const FORMAT_NAMES := {Image.FORMAT_DXT1: "bc1", Image.FORMAT_RGTC_RG: "bc5",
	Image.FORMAT_BPTC_RGBA: "bc7"}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("VRAM_JOBS")))
	if not parsed is Array:
		printerr("VRAM_FAIL jobs file unreadable: ", OS.get_environment("VRAM_JOBS"))
		quit(2)
		return
	var done := 0
	for job: Dictionary in parsed:
		var result := _encode(job)
		if not result.has("error"):
			done += 1
		print("VRAM_RESULT ", JSON.stringify(result))
	print("VRAM_DONE ", done)
	quit(0)

func _encode(job: Dictionary) -> Dictionary:
	var result := {"sha": str(job.sha), "recipe": str(job.recipe)}
	var bytes := FileAccess.get_file_as_bytes(str(job.src))
	var image := Image.new()
	var error: Error = FAILED
	if bytes.size() >= 8 and bytes[0] == 0x89 and bytes[1] == 0x50 and bytes[2] == 0x4E and bytes[3] == 0x47:
		error = image.load_png_from_buffer(bytes)
	elif bytes.size() >= 3 and bytes[0] == 0xFF and bytes[1] == 0xD8 and bytes[2] == 0xFF:
		error = image.load_jpg_from_buffer(bytes)
	elif bytes.size() >= 12 and bytes.slice(0, 4).get_string_from_ascii() == "RIFF":
		error = image.load_webp_from_buffer(bytes)
	if error != OK or image.is_empty():
		result.error = "decode_failed"
		return result
	if image.is_compressed():
		image.decompress()
	result.width = image.get_width()
	result.height = image.get_height()
	if image.get_width() % 4 != 0 or image.get_height() % 4 != 0:
		result.error = "size_not_multiple_of_4"
		return result
	var began := Time.get_ticks_usec()
	if not image.has_mipmaps():
		image.generate_mipmaps()
	match str(job.recipe):
		"base":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress_from_channels(Image.COMPRESS_BPTC, Image.USED_CHANNELS_RGB)
		"base_alpha":
			image.convert(Image.FORMAT_RGBA8)
			error = image.compress_from_channels(Image.COMPRESS_BPTC, Image.USED_CHANNELS_RGBA)
		"orm":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress_from_channels(Image.COMPRESS_S3TC, Image.USED_CHANNELS_RGB)
		"orm_bc7":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress_from_channels(Image.COMPRESS_BPTC, Image.USED_CHANNELS_RGB)
		"normal":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_NORMAL)
		_:
			result.error = "unknown_recipe"
			return result
	if error != OK or not FORMAT_NAMES.has(image.get_format()):
		result.error = "compress_failed: %s format %d" % [error_string(error), image.get_format()]
		return result
	var dds := image.save_dds_to_buffer()
	if dds.is_empty():
		result.error = "dds_failed"
		return result
	var body := dds.compress(FileAccess.COMPRESSION_ZSTD)
	var evt := PackedByteArray()
	evt.resize(HEADER_BYTES)
	evt.encode_u8(0, 0x45)  # E
	evt.encode_u8(1, 0x56)  # V
	evt.encode_u8(2, 0x54)  # T
	evt.encode_u8(3, 0x31)  # 1
	evt.encode_u32(4, dds.size())
	evt.encode_u32(8, FLAG_ZSTD)
	evt.encode_u32(12, 0)
	evt.append_array(body)
	if not _write(str(job.evt), evt) or not _write(str(job.dds), dds):
		result.error = "write_failed"
		return result
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(evt)
	result.format = FORMAT_NAMES[image.get_format()]
	result.mipmaps = image.get_mipmap_count()
	result.gpuBytes = image.get_data().size()
	result.rawBytes = dds.size()
	result.fileBytes = evt.size()
	result.sha256 = hashing.finish().hex_encode()
	result.encodeMs = snappedf((Time.get_ticks_usec() - began) / 1000.0, 0.1)
	return result

func _write(path: String, data: PackedByteArray) -> bool:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(data)
	file.close()
	return true
