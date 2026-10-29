extends RefCounted
## Release-only lossless storage. Logical .glb paths, original hashes, parser
## policy and runtime resources stay identical to the authored creature GLBs.
## No decoded-byte cache: scenes/libraries own shared resources, not source blobs.

const MAGIC := "RLCZ0001"
const HEADER_BYTES := 56
const MAX_BYTES := 512 * 1024 * 1024
const MAX_ENCODED_BYTES := MAX_BYTES + (MAX_BYTES >> 7) + 1024

static func eligible(path: String) -> bool:
	var normalized := path.replace("\\", "/").simplify_path()
	return normalized.get_extension().to_lower() == "glb" and (
		normalized.begins_with("res://assets/actors/native/creatures/") or
		normalized.begins_with("assets/actors/native/creatures/") or
		normalized.contains("/assets/actors/native/creatures/"))

static func is_compressed(path: String) -> bool:
	if not eligible(path): return false
	var file := FileAccess.open(path, FileAccess.READ)
	return file != null and file.get_buffer(4).get_string_from_ascii() == MAGIC.substr(0,4)

static func _failure(path: String, reason: String) -> Dictionary:
	push_error("Creature payload rejected (%s): %s" % [reason, path])
	return {}

static func _read_compressed(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() < HEADER_BYTES or file.get_length() > MAX_ENCODED_BYTES + HEADER_BYTES:
		return _failure(path, "file length")
	file.big_endian = false
	if file.get_buffer(8).get_string_from_ascii() != MAGIC:
		return _failure(path, "magic")
	var size := file.get_64()
	var encoded_size := file.get_64()
	var expected := file.get_buffer(32)
	if size < 20 or size > MAX_BYTES or encoded_size <= 0 or encoded_size > MAX_ENCODED_BYTES \
			or encoded_size != file.get_length() - HEADER_BYTES:
		return _failure(path, "header or size")
	var encoded := file.get_buffer(encoded_size)
	file.close()
	var decoded := encoded.decompress(size, FileAccess.COMPRESSION_ZSTD)
	encoded.clear()
	if decoded.size() != size:
		return _failure(path, "decode size")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(decoded)
	var actual := context.finish()
	if actual != expected:
		return _failure(path, "decoded SHA-256")
	if decoded.slice(0,4).get_string_from_ascii() != "glTF" or decoded.decode_u32(4) != 2 \
			or decoded.decode_u32(8) != size:
		return _failure(path, "GLB header")
	return {"bytes":decoded,"sha256":actual.hex_encode()}

static func read_bytes(path: String) -> PackedByteArray:
	if not is_compressed(path): return FileAccess.get_file_as_bytes(path)
	return _read_compressed(path).get("bytes",PackedByteArray())

static func source_sha256(path: String) -> String:
	if not is_compressed(path): return FileAccess.get_sha256(path)
	# Verify actual decoded bytes on every prepared-content lookup, just as raw
	# source verification does. A stored hash alone never authorizes a cache hit.
	return str(_read_compressed(path).get("sha256",""))

static func append(document: GLTFDocument, path: String, state: GLTFState) -> Error:
	if not is_compressed(path): return document.append_from_file(path, state)
	var bytes: PackedByteArray = _read_compressed(path).get("bytes",PackedByteArray())
	if bytes.is_empty(): return ERR_FILE_CORRUPT
	state.filename = path.get_file().get_basename()
	return document.append_from_buffer(bytes, path.get_base_dir(), state)
