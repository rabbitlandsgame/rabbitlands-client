extends RefCounted
## Experimental opt-in, lossless cache of the existing neutral wardrobe atlas.
## This caches CPU image bytes only. It never skips rendering warm-up or owns a
## GPU texture, and failed reads/writes always retain the original computation.
## Like the map collision cache, entries use bounded framing, SHA-256 checks
## and a same-directory temporary file before publication. No Resource/Variant
## deserialization or image codec is used for cached pixel data.

const ROOT := "user://wardrobe-dye-cache/v1"
const POLICY := "wardrobe-average-luminance-rgba8-mips-v1"
const VERSION := 1
const HEADER_BYTES := 16
const MAX_METADATA_BYTES := 4096
const MAX_SIDE := 4096
const MAX_SOURCE_BYTES := 128 * 1024 * 1024
const MAX_PIXEL_BYTES := 96 * 1024 * 1024
static var _sequence := 0
static var _sequence_mutex := Mutex.new()
static var _loads := 0
static var _hits := 0
static var _invalid := 0
static var _writes := 0
static var _write_failures := 0

static func enabled() -> bool:
	return OS.get_environment("ELORIA_WARDROBE_TEXTURE_CACHE") == "1"

static func stats() -> Dictionary:
	return {"enabled": enabled(), "loads": _loads, "hits": _hits, "misses": _loads - _hits,
		"invalid": _invalid, "writes": _writes, "write_failures": _write_failures}

static func _digest(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()

static func _hash(value: Variant) -> bool:
	if not value is String or value.length() != 64:
		return false
	for character: String in value:
		if not character in "0123456789abcdef":
			return false
	return true

## Content identity includes source mip bytes, layout and engine generation.
## Resource IDs and paths are deliberately absent, so a fresh process can hit.
static func source_key(source: Image) -> String:
	if source == null or source.is_empty() or source.get_width() > MAX_SIDE \
			or source.get_height() > MAX_SIDE:
		return ""
	# Float/half-float source atlases retain the original path. Reject these
	# before get_data(), bounding the copy even for a maximum-sized source.
	if source.get_format() >= Image.FORMAT_RF and source.get_format() <= Image.FORMAT_RGBAH:
		return ""
	var bytes := source.get_data()
	if bytes.is_empty() or bytes.size() > MAX_SOURCE_BYTES:
		return ""
	var engine := Engine.get_version_info()
	var identity := [POLICY, VERSION, str(engine.get("hash", "")),
		str(engine.get("string", "")), OS.get_name(), source.get_width(), source.get_height(),
		source.get_format(), source.has_mipmaps(), source.get_mipmap_count(), _digest(bytes)]
	return _digest(JSON.stringify(identity).to_utf8_buffer())

static func _mipmap_count(width: int, height: int) -> int:
	var count := 0
	var side := maxi(width, height)
	while side > 1:
		side >>= 1
		count += 1
	return count

static func _pixel_bytes(width: int, height: int, mipmaps: bool) -> int:
	var bytes := width * height * 4
	while mipmaps and (width > 1 or height > 1):
		width = maxi(1, width >> 1)
		height = maxi(1, height >> 1)
		bytes += width * height * 4
	return bytes

static func _integer(value: Variant, minimum: int, maximum: int) -> int:
	if (not value is int and not value is float) or not is_finite(float(value)) \
			or float(value) < minimum or float(value) > maximum or float(value) != floorf(float(value)):
		return -1
	return int(value)

static func _reject() -> Image:
	_invalid += 1
	return null

static func load_image(source: Image) -> Image:
	if not enabled():
		return null
	_loads += 1
	var key := source_key(source)
	if key.is_empty():
		return null
	var path := ROOT.path_join(key + ".rwd")
	if not FileAccess.file_exists(path):
		return null
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return null
	var length := file.get_length()
	if length < HEADER_BYTES or length > HEADER_BYTES + MAX_METADATA_BYTES + MAX_PIXEL_BYTES:
		return _reject()
	var header := file.get_buffer(HEADER_BYTES)
	if header.size() != HEADER_BYTES or header.slice(0, 4).get_string_from_ascii() != "RLDY" \
			or header.decode_u32(4) != VERSION:
		return _reject()
	var metadata_size := header.decode_u32(8)
	var payload_size := header.decode_u32(12)
	if metadata_size < 2 or metadata_size > MAX_METADATA_BYTES or payload_size < 4 \
			or payload_size > MAX_PIXEL_BYTES or length != HEADER_BYTES + metadata_size + payload_size:
		return _reject()
	var parser := JSON.new()
	if parser.parse(file.get_buffer(metadata_size).get_string_from_utf8()) != OK \
			or not parser.data is Dictionary:
		return _reject()
	var metadata: Dictionary = parser.data
	var width := _integer(metadata.get("width"), 1, MAX_SIDE)
	var height := _integer(metadata.get("height"), 1, MAX_SIDE)
	var levels := _mipmap_count(source.get_width(), source.get_height())
	if metadata.get("policy") != POLICY or metadata.get("key") != key \
			or width != source.get_width() or height != source.get_height() \
			or _integer(metadata.get("format"), 0, Image.FORMAT_MAX - 1) != Image.FORMAT_RGBA8 \
			or not metadata.get("mipmaps") is bool \
			or (levels > 0 and not bool(metadata.mipmaps)) \
			or _integer(metadata.get("mipmap_count"), 0, 16) != levels \
			or _integer(metadata.get("bytes"), 4, MAX_PIXEL_BYTES) != payload_size \
			or _pixel_bytes(width, height, bool(metadata.mipmaps)) != payload_size \
			or not _hash(metadata.get("sha256")):
		return _reject()
	# Only allocate the bounded, exact RGBA8 mip-chain size after all layout
	# checks. Checksum all levels, including alpha, before creating an Image.
	var payload := file.get_buffer(payload_size)
	if payload.size() != payload_size or _digest(payload) != metadata.sha256:
		return _reject()
	var image := Image.create_from_data(width, height, metadata.mipmaps, Image.FORMAT_RGBA8, payload)
	if image == null or image.is_empty():
		return _reject()
	_hits += 1
	return image

static func store_image(source: Image, neutral: Image) -> bool:
	if not enabled():
		return false
	var key := source_key(source)
	if key.is_empty() or neutral == null or neutral.is_empty() \
			or neutral.get_width() != source.get_width() or neutral.get_height() != source.get_height() \
			or neutral.get_format() != Image.FORMAT_RGBA8 \
			or neutral.get_mipmap_count() != _mipmap_count(source.get_width(), source.get_height()) \
			or (_mipmap_count(source.get_width(), source.get_height()) > 0 and not neutral.has_mipmaps()):
		return false
	var payload := neutral.get_data()
	if payload.size() > MAX_PIXEL_BYTES \
			or payload.size() != _pixel_bytes(neutral.get_width(), neutral.get_height(), neutral.has_mipmaps()):
		return false
	var metadata := {"policy": POLICY, "key": key, "width": neutral.get_width(),
		"height": neutral.get_height(), "format": Image.FORMAT_RGBA8,
		"mipmaps": neutral.has_mipmaps(), "mipmap_count": neutral.get_mipmap_count(),
		"bytes": payload.size(), "sha256": _digest(payload)}
	var metadata_bytes := JSON.stringify(metadata, "", true, true).to_utf8_buffer()
	if metadata_bytes.size() > MAX_METADATA_BYTES:
		return false
	var header := "RLDY".to_ascii_buffer()
	header.resize(HEADER_BYTES)
	header.encode_u32(4, VERSION)
	header.encode_u32(8, metadata_bytes.size())
	header.encode_u32(12, payload.size())
	var path := ROOT.path_join(key + ".rwd")
	var new_directory := not DirAccess.dir_exists_absolute(ROOT)
	if DirAccess.make_dir_recursive_absolute(ROOT) != OK:
		_write_failures += 1
		return false
	if new_directory and OS.get_name() == "Linux":
		FileAccess.set_unix_permissions(ROOT, 448) # owner rwx
	_sequence_mutex.lock()
	_sequence += 1
	var temporary := path + "." + str(OS.get_process_id()) + "." + str(_sequence) + ".tmp"
	_sequence_mutex.unlock()
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		_write_failures += 1
		return false
	if OS.get_name() == "Linux":
		FileAccess.set_unix_permissions(temporary, 384) # owner rw
	file.store_buffer(header)
	file.store_buffer(metadata_bytes)
	file.store_buffer(payload)
	file.flush()
	var error := file.get_error()
	file.close()
	# A same-directory rename atomically publishes complete entries on Linux.
	# Platforms unable to replace an existing entry simply retain the fallback.
	if error != OK or DirAccess.rename_absolute(temporary, path) != OK:
		DirAccess.remove_absolute(temporary)
		_write_failures += 1
		return false
	_writes += 1
	return true
