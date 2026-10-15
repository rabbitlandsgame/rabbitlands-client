extends RefCounted
## Raw payload codecs only. Not connected to decode_server or client capability lists.
const Profile = preload("res://src/network/coordinate_profile.gd")
const MAX_CONTEXT := 32768
const MAX_PROFILES := 64
const POINT_COMMANDS := [1, 6, 51]
const MAGIC_COMMAND := 202
const JSON_TOKEN := '"(?:[^"\\\\\\x00-\\x1f]|\\\\(?:["\\\\/bfnrt]|u[0-9a-fA-F]{4}))*"|-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}\\[\\]:,]|[ \\t\\r\\n]+'

static func _magic_object(payload: PackedByteArray) -> bool:
	var text := payload.get_string_from_utf8()
	if text.to_utf8_buffer() != payload:
		return false
	var lexer := RegEx.new()
	if lexer.compile(JSON_TOKEN) != OK:
		return false
	var position := 0
	var previous := ""
	var depth := 0
	while position < text.length():
		var found := lexer.search(text, position)
		if found == null or found.get_start() != position:
			return false
		var token := found.get_string()
		position = found.get_end()
		if token.strip_edges().is_empty():
			continue
		if token in ["}", "]"] and previous == ",":
			return false
		if token in ["{", "["]:
			depth += 1
			if depth > 64:
				return false
		elif token in ["}", "]"]:
			depth -= 1
		if token[0] in "-0123456789":
			if not is_finite(token.to_float()) or (position < text.length() and not text[position] in " \t\r\n,]}"):
				return false
		previous = token
	var json := JSON.new()
	return json.parse(text) == OK and json.data is Dictionary

class Reader:
	var bytes: PackedByteArray
	var position := 0
	var valid := true
	func _init(value: PackedByteArray) -> void:
		bytes = value
	func take(count: int) -> PackedByteArray:
		if count < 0 or position + count > bytes.size():
			valid = false
			return PackedByteArray()
		var result := bytes.slice(position, position + count)
		position += count
		return result
	func number(size: int, signed_value := false) -> int:
		var part := take(size)
		if not valid:
			return 0
		if size == 1:
			return part[0]
		if size == 2:
			return part.decode_u16(0)
		return part.decode_s32(0) if signed_value else part.decode_u32(0)
	func floating() -> float:
		var part := take(8)
		return part.decode_double(0) if valid else NAN
	func text() -> String:
		var part := take(number(1))
		if part.has(0):
			valid = false
			return ""
		var value := part.get_string_from_utf8()
		if not Profile.map_text(value) or value.to_utf8_buffer() != part:
			valid = false
		return value
	func ended() -> bool:
		return valid and position == bytes.size()

static func decode_profile_record(payload: PackedByteArray, expected: Variant = null) -> Dictionary:
	var reader := Reader.new(payload)
	if reader.take(Profile.magic_bytes().size()) != Profile.magic_bytes():
		return Profile.failure("profile_encoding")
	var map_id := reader.text()
	var version := reader.number(1)
	var minimum := [reader.number(4, true), reader.number(4, true)]
	var cells := [reader.number(2), reader.number(2)]
	var flags := reader.number(1)
	if version != 1 or flags & ~3:
		return Profile.failure("profile_version_flags")
	var values: Array = []
	for _index: int in range(9):
		values.append(reader.floating())
	var frame := {"serverOrigin": values.slice(0, 2), "origin": values.slice(2, 5),
		"metresPerTile": values[5], "continentTranslation": values.slice(6, 9),
		"invertServerY": bool(flags & 1)}
	if flags & 2:
		frame.walkingHeight = reader.floating()
	var collision := reader.take(32).hex_encode()
	var revision := reader.take(32).hex_encode()
	if not reader.ended():
		return Profile.failure("profile_length")
	var parsed := Profile.parse({"mapId": map_id, "serverStorageVersion": version,
		"serverTileMin": minimum, "serverCells": cells, "frame": frame,
		"collisionSha256": collision, "coordinateRevision": revision}, expected)
	if parsed.ok and parsed.profile.record() != payload:
		return Profile.failure("profile_noncanonical")
	return parsed

static func encode_context(context: Variant) -> Dictionary:
	if not context is Dictionary or not Profile.integer(context.get("version"), 1, 1):
		return Profile.failure("context_version")
	var operations := ["accepted", "define", "activate"]
	var operation: int = operations.find(context.get("op"))
	if operation < 0:
		return Profile.failure("context_operation")
	var keys: Array = ["version", "op"]
	if operation > 0:
		keys.append("profiles")
	if operation == 2:
		keys.append_array(["epoch", "mapId", "handles"])
	if not Profile.exact_keys(context, keys):
		return Profile.failure("context_fields")
	var payload := PackedByteArray([1, operation])
	if operation == 0:
		return {"ok": true, "payload": payload}
	if not context.profiles is Array or context.profiles.size() < 1 or context.profiles.size() > MAX_PROFILES:
		return Profile.failure("context_profile_count")
	payload.append_array(Profile.pack_integer(context.profiles.size(), 2))
	var maps: Dictionary = {}
	for descriptor: Variant in context.profiles:
		var parsed := Profile.parse(descriptor)
		if not parsed.ok:
			return parsed
		if maps.has(descriptor.mapId):
			return Profile.failure("context_duplicate_profile")
		maps[descriptor.mapId] = true
		var record: PackedByteArray = parsed.profile.record()
		payload.append_array(Profile.pack_integer(record.size(), 2))
		payload.append_array(record)
	if operation == 2:
		if not Profile.integer(context.epoch, 1, 4294967295) or not Profile.map_text(context.mapId):
			return Profile.failure("activation_identity")
		if not context.handles is Array or context.handles.size() < 1 or context.handles.size() > MAX_PROFILES:
			return Profile.failure("activation_count")
		payload.append_array(Profile.pack_integer(context.epoch, 4))
		payload.append_array(Profile.pack_text(context.mapId))
		payload.append_array(Profile.pack_integer(context.handles.size(), 2))
		var seen: Dictionary = {}
		var handled: Dictionary = {}
		for entry: Variant in context.handles:
			if not entry is Dictionary or not Profile.exact_keys(entry, ["handle", "mapId"]):
				return Profile.failure("activation_handle")
			if not Profile.integer(entry.handle, 0, 65535) or not Profile.map_text(entry.mapId):
				return Profile.failure("activation_handle_value")
			if seen.has(entry.handle) or handled.has(entry.mapId) or not maps.has(entry.mapId):
				return Profile.failure("activation_duplicate_undefined")
			seen[entry.handle] = true
			handled[entry.mapId] = true
			if entry.handle == 0 and entry.mapId != context.mapId:
				return Profile.failure("activation_active_map")
			payload.append_array(Profile.pack_integer(entry.handle, 2))
			payload.append_array(Profile.pack_text(entry.mapId))
		if not seen.has(0) or handled.size() != maps.size():
			return Profile.failure("activation_incomplete")
	if payload.size() > MAX_CONTEXT:
		return Profile.failure("context_size")
	return {"ok": true, "payload": payload}

static func decode_context(payload: PackedByteArray, expected_profiles: Dictionary) -> Dictionary:
	if payload.size() > MAX_CONTEXT:
		return Profile.failure("context_size")
	var reader := Reader.new(payload)
	var version := reader.number(1)
	var operation := reader.number(1)
	if version != 1 or operation not in [0, 1, 2]:
		return Profile.failure("context_version_operation")
	var context := {"version": 1, "op": ["accepted", "define", "activate"][operation]}
	if operation > 0:
		var count := reader.number(2)
		if count < 1 or count > MAX_PROFILES:
			return Profile.failure("context_profile_count")
		var profiles: Array = []
		for _index: int in range(count):
			var parsed := decode_profile_record(reader.take(reader.number(2)))
			if not parsed.ok:
				return parsed
			var descriptor: Dictionary = parsed.profile.descriptor()
			if not expected_profiles.has(descriptor.mapId):
				return Profile.failure("context_unknown_registry_map")
			var expected := Profile.from_registry(expected_profiles[descriptor.mapId])
			if not expected.ok or expected.profile.canonical_bytes() != parsed.profile.canonical_bytes():
				return Profile.failure("context_registry_mismatch")
			profiles.append(descriptor)
		context.profiles = profiles
	if operation == 2:
		context.epoch = reader.number(4)
		context.mapId = reader.text()
		var count := reader.number(2)
		if count < 1 or count > MAX_PROFILES:
			return Profile.failure("activation_count")
		var handles: Array = []
		for _index: int in range(count):
			handles.append({"handle": reader.number(2), "mapId": reader.text()})
		context.handles = handles
	if not reader.ended():
		return Profile.failure("context_length")
	var encoded := encode_context(context)
	if not encoded.ok or encoded.payload != payload:
		return Profile.failure("context_noncanonical")
	return {"ok": true, "context": context}

static func encode_map_command(epoch: Variant, command: Variant, payload: PackedByteArray) -> Dictionary:
	if not Profile.integer(epoch, 1, 4294967295) or not Profile.integer(command, 0, 255):
		return Profile.failure("command_header")
	if command in POINT_COMMANDS:
		if payload.size() != 4 or payload.decode_u16(0) > 2047 or payload.decode_u16(2) > 2047:
			return Profile.failure("command_point")
	elif command == MAGIC_COMMAND:
		if payload.size() < 1 or payload.size() > 4096:
			return Profile.failure("command_magic_size")
		if not _magic_object(payload):
			return Profile.failure("command_magic_object")
	else:
		return Profile.failure("command_not_allowed")
	var result := PackedByteArray([1])
	result.append_array(Profile.pack_integer(epoch, 4))
	result.append(command)
	result.append_array(payload)
	return {"ok": true, "payload": result}

static func decode_map_command(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 6 or payload.size() > 4102 or payload[0] != 1:
		return Profile.failure("command_length_version")
	var epoch := payload.decode_u32(1)
	var command: int = payload[5]
	var body := payload.slice(6)
	var encoded := encode_map_command(epoch, command, body)
	if not encoded.ok:
		return encoded
	return {"ok": true, "epoch": epoch, "command": command, "body": body}
