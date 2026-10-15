@tool
extends RefCounted
## The server's 16-bit served walk grid ("ESCG version 2"), read for the editor.
##
## Version 1 served maps keep one byte per one-metre tile: zero is blocked, the
## low six bits are a height in a per-map stage of 0.2 m multiples, and a step
## is legal when two codes differ by at most two. The continent-v2 maps carry a
## 16-bit code per tile instead: 50 mm a code above one continent datum, with
## the climb rule stated in metres in the grid's own header. Only those new maps
## use it; every older map keeps its version 1 grid.
##
## Written against eloria-server docs/served-grid.md and pinned to the server's
## codec (eloria/served_grid.py) by the golden fixture
## res://tests/fixtures/served_grid_golden.escg.gz, whose SHA-256 is a literal
## in both repos' tests.
##
## The rule: a tile is walkable when its code is not 0 (never `code & 0x3F`:
## 64, 128, 4,096 and 32,704 are ordinary ground); a step is legal when both
## tiles are walkable and the codes differ by at most climb_mm / unit_mm (20);
## a diagonal also needs both orthogonal steps from its start.
##
## The file: a 32-byte little-endian header (magic "ESCG", version 2, header
## size 32, width, height, datum_mm i32, unit_mm u16, climb_mm u16, filter u8,
## flags u8, reserved u16, crc32 of the decoded payload), then width * height
## u16 codes, row-major, row 0 the minimum server y. Filter 1 stores each code
## as its difference from the one before it in the row, modulo 2^16. A package
## ships it gzipped as served-grid.escg.gz and declares it in world.json as
## collision.servedGrid {binary, format "ESCG-v2", unitMetres, climbMetres,
## originMetres (the datum), sha256}.
##
## Integrity: the file's SHA-256 is checked against servedGrid.sha256 (the
## server's sync refuses the same mismatch), and the header's CRC-32 against
## the decoded codes. Godot has no CRC-32 function, but its gzip writer ends
## every stream with the CRC-32 of what it compressed (RFC 1952), so the check
## compresses the decoded payload natively and reads that trailer.

const MAGIC := "ESCG"
const VERSION := 2
const HEADER_SIZE := 32
const FORMAT_NAME := "ESCG-v2"
const FILTER_RAW := 0
const FILTER_ROW_DELTA := 1
## Walkable codes lie in 1..32767, so every signed 16-bit path stays safe.
const MAX_CODE := 32767
## The server's constants (eloria/served_grid.py, tools/sync_authored_collision.py):
## code 0 is -100 m, 50 mm a code, 1.0 m climb for all eight steps.
const DATUM_MM := -100000
const UNIT_MM := 50
const CLIMB_MM := 1000
## The largest uncompressed file decoded: a 4096 x 4096 grid, twice the 2,048
## tiles a map can address.
const MAX_FILE_BYTES := HEADER_SIZE + 2 * 4096 * 4096


## Decodes a served grid's uncompressed bytes (header and payload, nothing
## after it). Returns {width, height, datum_mm, unit_mm, climb_mm, climb_units,
## filter, crc32, codes (PackedInt32Array, 0 blocked)} or {error}. The
## header's CRC is checked unless `verify_crc` is false.
static func decode(raw: PackedByteArray, verify_crc := true) -> Dictionary:
	var header := read_header(raw)
	if header.has("error"):
		return header
	var width := int(header.width)
	var height := int(header.height)
	# Two u32 dimensions can multiply past int64 and wrap negative, which would
	# pass the size checks below. Bound them by the payload's bytes first.
	if height > (raw.size() - HEADER_SIZE) / 2 / width:
		return {"error": "the served grid's payload is truncated"}
	var count := width * height
	if raw.size() < HEADER_SIZE + 2 * count:
		return {"error": "the served grid's payload is truncated"}
	if raw.size() != HEADER_SIZE + 2 * count:
		return {"error": "the served grid has bytes after its payload"}
	var unpacked := _unpack(raw.slice(HEADER_SIZE), width, count,
		int(header.filter) == FILTER_ROW_DELTA)
	if int(unpacked.highest) > MAX_CODE:
		return {"error": "a served grid code exceeds %d" % MAX_CODE}
	var codes: PackedInt32Array = unpacked.codes
	if verify_crc and crc32(payload_bytes(codes)) != int(header.crc32):
		return {"error": "the served grid's CRC does not match its codes"}
	header["codes"] = codes
	return header


## Parses and checks the 32-byte header; {error} for anything the server's
## reader refuses.
static func read_header(raw: PackedByteArray) -> Dictionary:
	if raw.size() < HEADER_SIZE:
		return {"error": "the served grid's header is truncated"}
	if raw.slice(0, 4).get_string_from_ascii() != MAGIC:
		return {"error": "not a served grid"}
	var version := raw.decode_u16(4)
	if version != VERSION:
		return {"error": "unsupported served grid version %d" % version}
	if raw.decode_u16(6) != HEADER_SIZE:
		return {"error": "unexpected served grid header size %d" % raw.decode_u16(6)}
	var width := raw.decode_u32(8)
	var height := raw.decode_u32(12)
	var unit_mm := raw.decode_u16(20)
	var climb_mm := raw.decode_u16(22)
	var filter := raw.decode_u8(24)
	if raw.decode_u8(25) != 0:
		return {"error": "served grid flags must be 0, not %d" % raw.decode_u8(25)}
	if raw.decode_u16(26) != 0:
		return {"error": "served grid reserved field must be 0, not %d" % raw.decode_u16(26)}
	if filter != FILTER_RAW and filter != FILTER_ROW_DELTA:
		return {"error": "unknown served grid filter %d" % filter}
	if width == 0 or height == 0:
		return {"error": "served grid dimensions must be positive"}
	if unit_mm == 0 or climb_mm == 0 or climb_mm % unit_mm != 0:
		return {"error": "served grid unit %d mm does not divide its climb %d mm" % [unit_mm,
			climb_mm]}
	return {"width": width, "height": height, "datum_mm": raw.decode_s32(16), "unit_mm": unit_mm,
		"climb_mm": climb_mm, "climb_units": climb_mm / unit_mm, "filter": filter,
		"crc32": raw.decode_u32(28)}


## A served-grid file (gzipped, or its uncompressed content). When
## `expected_sha256` is given, the file's bytes must hash to it first, exactly
## (lowercase hex), as the server's sync compares it.
##
## The gzip is inflated in one call sized from the member's own length field
## (its last four bytes), never with decompress_dynamic: in Godot 4.7 that call
## does not return when any byte follows the gzip stream. A file with padding,
## garbage or a second member after its stream has a length field that is not
## its content's length, so it is refused at once, as the server refuses it.
## (One file the server refuses still reads here: a member followed by an exact
## copy of itself, whose length field is the first member's. Only the first is
## read, it is the same grid, and the server's sync refuses to vendor it.)
static func decode_file(blob: PackedByteArray, expected_sha256 := "", verify_crc := true) -> Dictionary:
	if not expected_sha256.is_empty():
		var digest := sha256_hex(blob)
		if digest != expected_sha256:
			return {"error": "the served grid's SHA-256 is %s, the package declares %s" % [digest,
				expected_sha256]}
	var raw := blob
	if blob.size() >= 2 and blob[0] == 0x1f and blob[1] == 0x8b:
		# 10 header bytes, a deflate stream, then CRC-32 and length (RFC 1952).
		var expected := blob.decode_u32(blob.size() - 4) if blob.size() >= 18 else 0
		if expected < HEADER_SIZE or expected > MAX_FILE_BYTES:
			return {"error": "the served grid is not a readable gzip file"}
		raw = blob.decompress(expected, FileAccess.COMPRESSION_GZIP)
		if raw.size() != expected:
			return {"error": "the served grid is not a readable gzip file"}
	return decode(raw, verify_crc)


## The grid a published package declares in world.json's collision.servedGrid,
## checked as the server's sync checks it: the format, a named binary, the
## file's SHA-256, the header, and the metres world.json states against the
## header's millimetres. (The walker checks the size against the package's
## frame. The sync's last check, the walkable mask against collision.bin's
## all-four fold, is not repeated: it costs seconds in GDScript on a 2 km map,
## and a package that fails it is never vendored.)
## Returns the decode_file result plus {path, sha256}; {} when the manifest
## declares no served grid; {error, missing: true} when it names a file the
## package does not hold.
static func load_declared(manifest_path: String, manifest: Dictionary) -> Dictionary:
	var spec := declared(manifest)
	if spec.is_empty():
		return {}
	if String(spec.get("format", "")) != FORMAT_NAME:
		return {"error": "servedGrid format is %s, not %s" % [String(spec.get("format", "")),
			FORMAT_NAME]}
	var sha := String(spec.get("sha256", ""))
	if sha.is_empty():
		return {"error": "servedGrid declares no sha256"}
	var binary := String(spec.get("binary", ""))
	if binary.is_empty():
		return {"error": "servedGrid names no binary"}
	var path := manifest_path.get_base_dir().path_join(binary)
	if not FileAccess.file_exists(path):
		return {"error": "the published served grid is missing: %s" % path, "missing": true}
	var result := decode_file(FileAccess.get_file_as_bytes(path), sha)
	if result.has("error"):
		return result
	for pair: Array in [["unitMetres", result.unit_mm], ["climbMetres", result.climb_mm],
			["originMetres", result.datum_mm]]:
		if spec.has(pair[0]) and roundi(float(spec[pair[0]]) * 1000.0) != int(pair[1]):
			return {"error": "servedGrid %s %s disagrees with the grid header's %d mm" % [pair[0],
				str(spec[pair[0]]), int(pair[1])]}
	result["path"] = path
	result["sha256"] = sha
	return result


## world.json's collision.servedGrid block, or {} when there is none.
static func declared(manifest: Dictionary) -> Dictionary:
	var collision: Variant = manifest.get("collision")
	if not collision is Dictionary:
		return {}
	var spec: Variant = (collision as Dictionary).get("servedGrid")
	return spec if spec is Dictionary else {}


## A height in millimetres as a code: half up, never half to even
## (served_grid.quantise_mm; the 1e-6 guards a value a hair under a half).
static func quantise_mm(height_mm: float, datum_mm := DATUM_MM, unit_mm := UNIT_MM) -> int:
	return floori((height_mm - float(datum_mm)) / float(unit_mm) + 0.5 + 1e-6)


## A code's height in metres.
static func metres(code: int, datum_mm := DATUM_MM, unit_mm := UNIT_MM) -> float:
	return float(datum_mm + code * unit_mm) / 1000.0


## Codes as the little-endian u16 payload (what the header's CRC covers).
static func payload_bytes(codes: PackedInt32Array) -> PackedByteArray:
	var pairs := PackedInt32Array()
	pairs.resize((codes.size() + 1) / 2)
	var last := codes.size() - 1
	for pair in pairs.size():
		var index := 2 * pair
		pairs[pair] = (codes[index] & 0xFFFF) | \
			((codes[index + 1] & 0xFFFF) << 16 if index < last else 0)
	var bytes := pairs.to_byte_array()
	bytes.resize(2 * codes.size())
	return bytes


## CRC-32 (zlib / IEEE) of `bytes`, read from the trailer Godot's gzip writer
## appends (RFC 1952: CRC-32, then the length, both little-endian).
static func crc32(bytes: PackedByteArray) -> int:
	var stream := bytes.compress(FileAccess.COMPRESSION_GZIP)
	return stream.decode_u32(stream.size() - 8) if stream.size() >= 18 else -1


static func sha256_hex(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()


## The stored u16 values as codes, undoing the row delta when `row_delta`.
## Reads the payload as 32-bit words, two values each, which is several times
## faster in GDScript than decoding one u16 at a time.
static func _unpack(payload: PackedByteArray, width: int, count: int, row_delta: bool) -> Dictionary:
	if payload.size() % 4 != 0:
		payload.append(0)
		payload.append(0)
	var words := payload.to_int32_array()
	var codes := PackedInt32Array()
	codes.resize(count)
	var index := 0
	var column := 0
	var previous := 0
	var highest := 0
	for word: int in words:
		var value := word & 0xFFFF
		if row_delta and column != 0:
			value = (previous + value) & 0xFFFF
		codes[index] = value
		previous = value
		if value > highest:
			highest = value
		index += 1
		column += 1
		if column == width:
			column = 0
		if index == count:
			break
		value = (word >> 16) & 0xFFFF
		if row_delta and column != 0:
			value = (previous + value) & 0xFFFF
		codes[index] = value
		previous = value
		if value > highest:
			highest = value
		index += 1
		column += 1
		if column == width:
			column = 0
	return {"codes": codes, "highest": highest}
