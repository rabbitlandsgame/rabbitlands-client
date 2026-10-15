extends RefCounted
## Pure immutable profile; no connection, scene or AppState dependency.

const MAGIC_TEXT := "ELORIA-COORDINATE-PROFILE"
const KEYS := ["mapId", "serverStorageVersion", "serverTileMin", "serverCells", "frame", "collisionSha256", "coordinateRevision"]
const FRAME_KEYS := ["serverOrigin", "origin", "metresPerTile", "invertServerY", "continentTranslation"]
var _data: Dictionary = {}
var _canonical := PackedByteArray()

static func failure(reason: String) -> Dictionary:
	return {"ok": false, "error": reason}

static func integer(value: Variant, low: int, high: int) -> bool:
	return typeof(value) == TYPE_INT and value >= low and value <= high

static func number(value: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value))

static func vector(value: Variant, count: int) -> bool:
	if not value is Array or value.size() != count:
		return false
	for item: Variant in value:
		if not number(item):
			return false
	return true

static func map_text(value: Variant) -> bool:
	if not value is String or value.to_utf8_buffer().size() not in range(1, 256):
		return false
	for index: int in range(value.length()):
		if value.unicode_at(index) == 0:
			return false
	return true

static func magic_bytes() -> PackedByteArray:
	var result := MAGIC_TEXT.to_utf8_buffer()
	result.append_array(PackedByteArray([0, 1]))
	return result

static func digest(value: Variant) -> bool:
	if not value is String or value.length() != 64:
		return false
	for character: String in value:
		if not character in "0123456789abcdef":
			return false
	return true

static func exact_keys(data: Dictionary, keys: Array) -> bool:
	if data.size() != keys.size():
		return false
	for key: Variant in keys:
		if not data.has(key):
			return false
	return true

static func pack_integer(value: int, length: int, signed_value := false) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(length)
	if length == 2:
		bytes.encode_u16(0, value)
	elif signed_value:
		bytes.encode_s32(0, value)
	else:
		bytes.encode_u32(0, value)
	return bytes

static func pack_number(value: Variant) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(8)
	bytes.encode_double(0, float(value) if value != 0 else 0.0)
	return bytes

static func pack_text(value: String) -> PackedByteArray:
	var text := value.to_utf8_buffer()
	var result := PackedByteArray([text.size()])
	result.append_array(text)
	return result

static func _freeze(value: Variant) -> void:
	if value is Dictionary:
		for item: Variant in value.values():
			_freeze(item)
		value.make_read_only()
	elif value is Array:
		for item: Variant in value:
			_freeze(item)
		value.make_read_only()

static func parse(data: Variant, expected: Variant = null) -> Dictionary:
	if not data is Dictionary or not exact_keys(data, KEYS):
		return failure("profile_fields")
	if not map_text(data.mapId) or not integer(data.serverStorageVersion, 1, 1):
		return failure("profile_identity")
	for key: String in ["serverTileMin", "serverCells"]:
		if not data[key] is Array or data[key].size() != 2:
			return failure("profile_vector")
	for axis: int in range(2):
		var minimum: Variant = data.serverTileMin[axis]
		var extent: Variant = data.serverCells[axis]
		if not integer(minimum, -2147483648, 2147483647) or not integer(extent, 1, 2048):
			return failure("profile_bounds")
		if minimum + extent - 1 > 2147483647:
			return failure("profile_logical_overflow")
	var frame: Variant = data.frame
	if not frame is Dictionary:
		return failure("profile_frame")
	var frame_keys: Array = FRAME_KEYS.duplicate()
	if frame.has("walkingHeight"):
		frame_keys.append("walkingHeight")
		if not number(frame.walkingHeight):
			return failure("profile_walking_height")
	if not exact_keys(frame, frame_keys) or not vector(frame.serverOrigin, 2) or not vector(frame.origin, 3) or not vector(frame.continentTranslation, 3):
		return failure("profile_frame_fields")
	if not number(frame.metresPerTile) or frame.metresPerTile <= 0 or not frame.invertServerY is bool:
		return failure("profile_frame_scale")
	if not digest(data.collisionSha256) or not digest(data.coordinateRevision):
		return failure("profile_digest")
	var body := magic_bytes()
	body.append_array(pack_text(data.mapId))
	body.append(1)
	for value: int in data.serverTileMin:
		body.append_array(pack_integer(value, 4, true))
	for value: int in data.serverCells:
		body.append_array(pack_integer(value, 2))
	body.append((1 if frame.invertServerY else 0) | (2 if frame.has("walkingHeight") else 0))
	var values: Array = frame.serverOrigin + frame.origin + [frame.metresPerTile] + frame.continentTranslation
	if frame.has("walkingHeight"):
		values.append(frame.walkingHeight)
	for value: Variant in values:
		body.append_array(pack_number(value))
	body.append_array(data.collisionSha256.hex_decode())
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(body)
	if hashing.finish().hex_encode() != data.coordinateRevision:
		return failure("profile_revision")
	if expected != null:
		var wanted := parse(expected)
		if not wanted.ok or wanted.profile.canonical_bytes() != body:
			return failure("profile_registry_mismatch")
	# Instantiate this already-loaded script without requiring an editor class
	# cache/import pass merely to use the pure codec in a headless test.
	var profile: Variant = load("res://src/network/coordinate_profile.gd").new()
	profile._data = data.duplicate(true)
	_freeze(profile._data)
	profile._canonical = body
	return {"ok": true, "profile": profile}

## JSON represents numbers as floats in Godot. Normalize only exact integral
## schema fields at this boundary; never round, coerce strings or accept bools.
static func from_registry(data: Variant) -> Dictionary:
	if not data is Dictionary:
		return failure("registry_profile")
	var typed: Dictionary = data.duplicate(true)
	if not number(typed.get("serverStorageVersion")) or typed.serverStorageVersion != 1:
		return failure("registry_version")
	typed.serverStorageVersion = 1
	for key: String in ["serverTileMin", "serverCells"]:
		if not typed.get(key) is Array or typed[key].size() != 2:
			return failure("registry_vector")
		for axis: int in range(2):
			var value: Variant = typed[key][axis]
			if not number(value) or value < -2147483648 or value > 2147483647 or floor(float(value)) != value:
				return failure("registry_integer")
			typed[key][axis] = int(value)
	return parse(typed)

func descriptor() -> Dictionary:
	return _data.duplicate(true)

func canonical_bytes() -> PackedByteArray:
	return _canonical.duplicate()

func record() -> PackedByteArray:
	var result := _canonical.duplicate()
	result.append_array(str(_data.coordinateRevision).hex_decode())
	return result

func to_wire(x: Variant, y: Variant) -> Dictionary:
	if not integer(x, -2147483648, 2147483647) or not integer(y, -2147483648, 2147483647):
		return failure("logical_integer")
	var wx: int = x - _data.serverTileMin[0]
	var wy: int = y - _data.serverTileMin[1]
	if not integer(wx, 0, _data.serverCells[0] - 1) or not integer(wy, 0, _data.serverCells[1] - 1):
		return failure("logical_bounds")
	return {"ok": true, "tile": Vector2i(wx, wy)}

func to_logical(x: Variant, y: Variant) -> Dictionary:
	if not integer(x, 0, _data.serverCells[0] - 1) or not integer(y, 0, _data.serverCells[1] - 1):
		return failure("wire_bounds")
	return {"ok": true, "tile": Vector2i(x + _data.serverTileMin[0], y + _data.serverTileMin[1])}
