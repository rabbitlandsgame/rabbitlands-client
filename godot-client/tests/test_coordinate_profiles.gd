extends SceneTree

const Profile = preload("res://src/network/coordinate_profile.gd")
const Codec = preload("res://src/network/coordinate_transport.gd")
const Wire = preload("res://src/network/protocol.gd")
var failures := 0
var assertions := 0

func expect(value: bool, label: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error(label)

func _init() -> void:
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/coordinate-profile-v1.json"))
	var expected: Dictionary = {}
	for row: Dictionary in fixture.profiles:
		var parsed := Profile.from_registry(row.descriptor)
		expect(parsed.ok, "registry profile " + str(row.descriptor.mapId))
		if not parsed.ok:
			continue
		var profile: Variant = parsed.profile
		expected[row.descriptor.mapId] = row.descriptor
		expect(profile.canonical_bytes().hex_encode() == row.canonicalHex, "canonical bytes golden")
		expect(profile.record().hex_encode() == row.recordHex, "profile record golden")
		expect(Codec.decode_profile_record(profile.record(), profile.descriptor()).ok, "profile round trip")
		for point: Dictionary in row.points:
			var logical: Array = point.logical
			var wire: Array = point.wire
			var packed: Dictionary = profile.to_wire(int(logical[0]), int(logical[1]))
			var unpacked: Dictionary = profile.to_logical(int(wire[0]), int(wire[1]))
			expect(packed.ok and packed.tile == Vector2i(int(wire[0]), int(wire[1])), "logical to wire golden")
			expect(unpacked.ok and unpacked.tile == Vector2i(int(logical[0]), int(logical[1])), "wire to logical golden")
		var minimum: Array = row.descriptor.serverTileMin
		var cells: Array = row.descriptor.serverCells
		expect(not profile.to_wire(int(minimum[0]) - 1, int(minimum[1])).ok, "logical lower edge")
		expect(not profile.to_wire(int(minimum[0] + cells[0]), int(minimum[1])).ok, "logical upper edge")
		expect(not profile.to_logical(int(cells[0]), 0).ok, "wire upper edge")
		expect(not profile.to_logical(-1, 0).ok, "wire lower edge")
		expect(not profile.to_logical(true, 0).ok and not profile.to_logical(1.0, 0).ok, "typed conversions reject bool/float")
		var exported: Dictionary = profile.descriptor()
		exported.frame.origin[0] = 999
		expect(profile.record().hex_encode() == row.recordHex, "output mutation isolation")
		var source: Dictionary = profile.descriptor()
		var isolated := Profile.parse(source)
		source.serverTileMin[0] += 1
		expect(isolated.ok and isolated.profile.record() == profile.record(), "input mutation isolation")
		for cut: int in range(profile.record().size()):
			expect(not Codec.decode_profile_record(profile.record().slice(0, cut)).ok, "truncated profile")
		var trailing: PackedByteArray = profile.record()
		trailing.append(0)
		expect(not Codec.decode_profile_record(trailing).ok, "profile trailing bytes")
	for case: Dictionary in fixture.invalidRegistry:
		var data: Dictionary = fixture.profiles[0].descriptor.duplicate(true)
		var target: Variant = data
		for key: Variant in case.path.slice(0, -1):
			target = target[int(key) if typeof(key) == TYPE_FLOAT else key]
		var last: Variant = case.path[-1]
		target[int(last) if typeof(last) == TYPE_FLOAT else last] = case.value
		expect(not Profile.from_registry(data).ok, "shared invalid registry " + str(case.path))
	var zero := Profile.from_registry(fixture.profiles[0].descriptor)
	var normalized: Dictionary = zero.profile.descriptor()
	normalized.frame.origin[0] = -0.0
	expect(Profile.parse(normalized).ok, "negative zero normalizes before hashing")
	for bad: float in [NAN, INF, -INF]:
		normalized.frame.origin[0] = bad
		expect(not Profile.parse(normalized).ok, "nonfinite frame rejected")
	var typed: Dictionary = zero.profile.descriptor()
	typed.serverStorageVersion = 1.0
	expect(not Profile.parse(typed).ok and Profile.from_registry(typed).ok, "explicit registry numeric normalization")
	for row: Dictionary in fixture.contexts:
		var value: Dictionary = row.value.duplicate(true)
		value.version = int(value.version)
		if value.has("profiles"):
			for index: int in range(value.profiles.size()):
				value.profiles[index] = Profile.from_registry(value.profiles[index]).profile.descriptor()
		if value.has("epoch"):
			value.epoch = int(value.epoch)
			for handle: Dictionary in value.handles:
				handle.handle = int(handle.handle)
		var payload: PackedByteArray = row.payloadHex.hex_decode()
		var encoded := Codec.encode_context(value)
		expect(encoded.ok and encoded.payload == payload, "context encode golden")
		expect(Codec.decode_context(payload, expected).ok, "context decode golden with registry floats")
		var framed := Wire.coordinate_context(value)
		expect(framed.ok and framed.frame == Wire.encode(208, payload), "context outer frame")
		for cut: int in range(payload.size()):
			expect(not Codec.decode_context(payload.slice(0, cut), expected).ok, "context truncation")
		var trailing := payload.duplicate()
		trailing.append(0)
		expect(not Codec.decode_context(trailing, expected).ok, "context trailing bytes")
		if value.op != "accepted":
			expect(not Codec.decode_context(payload, {}).ok, "unknown expected map rejected")
		if value.op == "activate":
			value.handles[1].handle = 0
			expect(not Codec.encode_context(value).ok, "duplicate activation handle")
	for row: Dictionary in fixture.commands:
		var payload: PackedByteArray = row.payloadHex.hex_decode()
		var body: PackedByteArray = row.bodyHex.hex_decode()
		var encoded := Codec.encode_map_command(int(row.epoch), int(row.command), body)
		expect(encoded.ok and encoded.payload == payload, "command encode golden")
		var decoded := Codec.decode_map_command(payload)
		expect(decoded.ok and decoded.epoch == int(row.epoch) and decoded.command == int(row.command) and decoded.body == body, "command decode golden")
		var framed := Wire.map_command(int(row.epoch), int(row.command), body)
		expect(framed.ok and framed.frame == Wire.encode(204, payload), "command outer frame")
	for payload_hex: String in fixture.invalidCommands:
		expect(not Codec.decode_map_command(payload_hex.hex_decode()).ok, "shared invalid command")
	for value: int in [0, 1023, 1024, 2047]:
		var frame := Wire.move_to(value, value)
		expect(Wire.u16(frame, 3) == value and Wire.u16(frame, 5) == value, "legacy move unsigned bytes")
		var actor := PackedByteArray()
		actor.resize(19)
		actor.encode_u16(2, value)
		actor.encode_u16(4, value)
		var decoded := Wire.decode_actor(actor, false)
		expect(decoded.x == value and decoded.y == value, "legacy actor unsigned decode")
	expect(not Wire.CLIENT_CAPABILITIES.has(Wire.MAP_STORAGE_COORDS_CAPABILITY), "capability remains unadvertised")
	expect(Wire.decode_server(208, PackedByteArray([1, 0])).type == "unknown", "context remains undispatched")
	print("coordinate profile tests: %d assertions, %d failures" % [assertions, failures])
	quit(0 if failures == 0 else 1)
