extends SceneTree
## PC/3 data and wire (PC/3 spec: private server handbook
## docs/wiki/Human-Character-Customization.md; checks C1-C13, and C14, C15, C19
## and C23's data checks from colour model revision 3). Protocol only:
## no native actor asset is imported or drawn.
const Wire = preload("res://src/network/protocol.gd")
const Custom = preload("res://src/actors/portrait_customization.gd")
const Ranking = preload("res://src/network/leaderboard_codec.gd")
const Finish = preload("res://src/actors/hair_finish.gd")
const PC2_VALUES := [5, 70, 30, 60, 90, 85, 2, 12, 23, 34, 45, 56, 67, 78, 89, 100]
## The V3 values in field order: eyelid 0, eye_style 87, eye_depth 21, the other ten
## offsets, the nine details (hair_finish 88) and the 17 colour values.
const V3_VALUES := [0, 87, 21, 100, 25, 75, 40, 60, 10, 90, 33, 66, 99, 13, 101, 1, 51, 26, 76, 12, 31,
	88, 201, 1, 240, 101, 101, 168, 71, 58, 1, 1, 1, 120, 50, 60, 61, 26, 13]
## The shared cross-language fixtures (the server's test_player_customization_v3.py
## asserts the same bytes): eye_style 87 and eye_depth 21 are trailer bytes 20 and 21.
const LOOK3_HEX := "50430305461e3c5a55020c17222d38434e596400571564194b283c0a5a2142630d6501331a4c0c1f58c901f06565a8473a01010178323c3d1a0d"
const NEUTRAL_HEX := "50430300323232323200323232323232323232323232323232323232323232320000000000000000000000000000000000000000000000000000"
const UPGRADE_HEX := "50430305461e3c5a55020c17222d38434e5964323232323232323232323232320000000000000000000000000000000000000000000000000000"
const PC2_HEX := "50430205461e3c5a55020c17222d38434e5964"
## The maxima literal the server's test asserts (pc3 spec 3.4, colour model
## spec 3.3); every other field is 100.
const MAXIMA := {"facial_hair": 5, "hair_detail": 2, "brow_style": 13, "brow_thickness": 101,
	"freckles": 101, "liner": 101, "liner_wing": 101, "stubble": 101, "lip_tint": 12,
	"hair_module": 31, "hair_finish": 101, "skin_tone": 201, "skin_undertone": 201,
	"hair_hue": 240, "hair_sat": 101, "hair_light": 101, "eye_hue": 240, "eye_sat": 101,
	"eye_light": 101, "shirt_hue": 240, "shirt_sat": 101, "shirt_light": 101,
	"pants_hue": 240, "pants_sat": 101, "pants_light": 101, "boots_hue": 240,
	"boots_sat": 101, "boots_light": 101}
const NEW_FIELDS := ["hair_finish", "skin_tone", "skin_undertone", "hair_hue", "hair_sat", "hair_light",
	"eye_hue", "eye_sat", "eye_light", "shirt_hue", "shirt_sat", "shirt_light", "pants_hue",
	"pants_sat", "pants_light", "boots_hue", "boots_sat", "boots_light"]
var failures := 0
var checks := 0

func _init() -> void:
	run.call_deferred()

func expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(label)

func look2() -> Dictionary:
	var result := {}
	for index: int in Custom.V2_FIELDS.size():
		result[Custom.V2_FIELDS[index]] = PC2_VALUES[index]
	return result

func look3() -> Dictionary:
	var result := look2()
	for index: int in Custom.V3_FIELDS.size():
		result[Custom.V3_FIELDS[index]] = V3_VALUES[index]
	return result

func run() -> void:
	check_fields()
	check_fixtures()
	check_rejections()
	check_validation()
	check_rule_a()
	check_hair_finish()
	check_creation_and_spawns()
	check_ranking()
	check_probes()
	check_sending()
	await check_real_connection_probe()
	print("Portrait customization v3: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

# C14: the field table.
func check_fields() -> void:
	expect(Custom.FIELDS.size() == 55 and Custom.V2_FIELDS.size() == 16 and Custom.V3_FIELDS.size() == 39,
		"55 fields: 16 PC/2 and 39 V3 (%d, %d, %d)" % [Custom.FIELDS.size(), Custom.V2_FIELDS.size(), Custom.V3_FIELDS.size()])
	expect(Custom.V3_CONTROLS.size() == 13 and Custom.V3_DETAILS.size() == 9 and Custom.V3_COLOURS.size() == 17,
		"13 offsets, 9 details, 17 colour fields")
	# The offsets follow the head's rlHead.controls order: eye_style and eye_depth
	# come right after eyelid (fields 17 and 18, trailer bytes 20 and 21).
	expect(Custom.V3_CONTROLS.slice(0, 4) == ["eyelid", "eye_style", "eye_depth", "brow_height"]
		and Custom.FIELDS.find("eye_style") == 17 and Custom.FIELDS.find("eye_depth") == 18,
		"eye_style and eye_depth are fields 17 and 18, after eyelid")
	for field: String in ["eye_style", "eye_depth"]:
		expect(Custom.maximum(field) == 100 and Custom.DEFAULTS[field] == 50 and Custom.field_version(field) == 3,
			"%s: 0-100, 50 = the authored eye, version 3" % field)
	expect(Custom.V3_DETAILS[-1] == "hair_finish" and Custom.V3_COLOURS[0] == "skin_tone",
		"hair_finish ends the details; the colours follow (field 37, 38)")
	expect(Custom.FIELDS.find("hair_finish") == 37 and Custom.FIELDS.find("skin_tone") == 38
		and Custom.FIELDS.find("boots_light") == 54, "field numbers 37, 38 and 54")
	for field: String in Custom.FIELDS:
		expect(Custom.maximum(field) == int(MAXIMA.get(field, 100)), "%s maximum %d" % [field, Custom.maximum(field)])
		expect(Custom.DEFAULTS.has(field), "%s has a neutral value" % field)
	expect(Custom.DEFAULTS.size() == 55, "55 neutral values")
	for field: String in NEW_FIELDS:
		expect(Custom.field_version(field) == 3 and Custom.DEFAULTS[field] == 0, "%s is a version 3 field, neutral 0" % field)
	for field: String in Custom.V3_CONTROLS:
		expect(Custom.field_version(field) == 3 and Custom.DEFAULTS[field] == 50, "%s is a version 3 offset, neutral 50" % field)
	for field: String in Custom.V1_FIELDS:
		expect(Custom.field_version(field) == 1, "%s is version 1" % field)
	for field: String in Custom.EXTRA_FIELDS:
		expect(Custom.field_version(field) == 2, "%s is version 2" % field)
	expect(Custom.field_version("skin") == 0 and Custom.field_version("future_field") == 0, "palette and unknown keys have no version")
	expect(Custom.fields_for(0).is_empty() and Custom.fields_for(1) == Custom.V1_FIELDS
		and Custom.fields_for(2) == Custom.V2_FIELDS and Custom.fields_for(3) == Custom.FIELDS
		and Custom.fields_for(4).is_empty(), "fields_for(0..4)")
	for version: int in [1, 2]:
		var shorter: Array = Custom.fields_for(version)
		expect(Custom.fields_for(version + 1).slice(0, shorter.size()) == shorter, "fields_for(%d) is a prefix" % (version + 1))
	expect(Custom.tag(1) == [80, 67, 1] and Custom.tag(2) == [80, 67, 2] and Custom.tag(3) == [80, 67, 3]
		and Custom.tag(4).is_empty() and Custom.LATEST == 3, "tags and LATEST")
	var names := {}
	for field: String in Custom.FIELDS:
		expect(not names.has(field), "%s is unique" % field)
		names[field] = true
		expect(field not in ["skin", "hair", "eyes", "head", "shirt", "pants", "boots"], "%s is no palette key" % field)

# C1, C2, C14: fixtures and round trips.
func check_fixtures() -> void:
	var look := look3()
	var encoded := Custom.encode(look, 3)
	expect(encoded.hex_encode() == LOOK3_HEX and encoded.size() == 58, "PC/3 LOOK3 fixture (58 bytes)")
	expect(encoded[20] == 87 and encoded[21] == 21 and look.eye_style == 87 and look.eye_depth == 21,
		"the shared fixture carries eye_style 87 and eye_depth 21 at trailer bytes 20 and 21")
	expect(Custom.decode(encoded, 0) == Custom.normalized(look) and Custom.normalized(look) == look,
		"PC/3 LOOK3 round trip")
	expect(Custom.encode({}, 3).hex_encode() == NEUTRAL_HEX, "PC/3 neutral fixture")
	expect(Custom.decode(Custom.encode({}, 3), 0) == Custom.DEFAULTS, "neutral round trip")
	var pc2 := Custom.encode(look2(), 2)
	expect(pc2.hex_encode() == PC2_HEX and pc2.size() == 19, "PC/2 LOOK fixture unchanged")
	expect(Custom.encode(Custom.decode(pc2, 0), 3).hex_encode() == UPGRADE_HEX, "PC/2 -> PC/3 upgrade fixture")
	expect(Custom.encode(look, 2) == pc2, "encoding a PC/3 look at version 2 drops V3")
	for version: int in [1, 2, 3]:
		expect(Custom.decode(Custom.encode({}, version), 0) == Custom.DEFAULTS, "version %d neutral round trip" % version)
		var decoded := Custom.decode(Custom.encode(look, version), 0)
		for field: String in Custom.FIELDS:
			var expected: int = look[field] if Custom.field_version(field) <= version else Custom.DEFAULTS[field]
			expect(decoded[field] == expected, "version %d carries %s" % [version, field])
	expect(Custom.encode(look, 4).is_empty() and Custom.encode(look, 0).is_empty(), "no encoding for versions 0 or 4")

# C3: rejections.
func check_rejections() -> void:
	var valid := Custom.encode(look3(), 3)
	expect(Custom.decode(valid.slice(0, valid.size() - 1), 0).is_empty(), "PC/3 one byte short")
	expect(Custom.decode(valid + PackedByteArray([0]), 0).is_empty(), "PC/3 one byte long")
	expect(Custom.decode(PackedByteArray([80, 67, 3]) + Custom.encode(look2(), 2).slice(3), 0).is_empty(), "PC/3 tag with a PC/2 body")
	expect(Custom.decode(PackedByteArray([80, 67, 2]) + valid.slice(3), 0).is_empty(), "PC/2 tag with a PC/3 body")
	expect(Custom.decode(PackedByteArray([80, 67, 4]) + valid.slice(3), 0).is_empty(), "PC/4 tag")
	expect(Custom.decode(PackedByteArray([90, 90, 3]) + valid.slice(3), 0).is_empty(), "ZZ tag")
	expect(Custom.decode(PackedByteArray([80, 67, 3]) + valid.slice(3, 41), 0).is_empty(), "rev 1 PC/3 length (38) rejected")
	for index: int in range(3, valid.size()):
		var bad := valid.duplicate()
		bad[index] = 255
		expect(Custom.decode(bad, 0).is_empty(), "byte %d at 255 rejected" % index)
	for index: int in Custom.V3_FIELDS.size():
		var field: String = Custom.V3_FIELDS[index]
		var bad := valid.duplicate()
		bad[19 + index] = Custom.maximum(field) + 1
		expect(Custom.decode(bad, 0).is_empty(), "%s at max + 1 (%d) rejected" % [field, Custom.maximum(field) + 1])
		bad[19 + index] = Custom.maximum(field)
		expect(not Custom.decode(bad, 0).is_empty(), "%s at its maximum accepted" % field)
	expect(Custom.decode(valid, -1).is_empty(), "negative offset rejected")

# C4, C5, C14: validation and the version gate.
func check_validation() -> void:
	for field: String in Custom.V3_FIELDS:
		for invalid: Variant in [-1, Custom.maximum(field) + 1, true, "50", null, 50.5]:
			expect(not Custom.validate({field: invalid}).ok, "%s rejects %s" % [field, str(invalid)])
		expect(Custom.validate({field: Custom.maximum(field)}).ok, "%s accepts its maximum" % field)
		expect(Custom.normalized({field: true})[field] == Custom.DEFAULTS[field]
			and Custom.normalized({field: "7"})[field] == Custom.DEFAULTS[field], "%s: a bad saved type is neutral" % field)
		expect(Custom.normalized({field: 1000})[field] == Custom.maximum(field) or field in Custom.V3_COLOURS,
			"%s: out of range clamps" % field)
		expect(Custom.normalized({field: -5})[field] == 0, "%s: negative clamps to 0" % field)
	var look := look3()
	for version: int in [1, 2]:
		for field: String in Custom.V3_FIELDS:
			var single := {field: look[field]}
			if look[field] == Custom.DEFAULTS[field]:
				continue
			var result := Custom.validate(single, version)
			var message: String = Custom.COLOUR_MESSAGE if field in Custom.V3_COLOURS else Custom.V3_DETAIL_MESSAGE
			expect(not result.ok and result.error == "unsupported" and result.message == message,
				"%s refused at version %d with its message" % [field, version])
		expect(Custom.validate(Custom.DEFAULTS, version).ok, "neutral PC/3 passes at version %d" % version)
	expect(Custom.validate(look, 3).ok and Custom.validate(look).ok, "LOOK3 passes at version 3 (the default)")
	expect(Custom.validate({"eye_tilt": 70}, 1).message == Custom.V2_MESSAGE, "the V2 message is unchanged")
	expect(Custom.COLOUR_MESSAGE == "This server cannot save custom colours yet. Pick a palette colour (or press Use nearest palette colours), or use an updated server.",
		"colour gate message (colour model spec 3.3)")
	expect(Custom.validate({"hair_finish": 60}, 2).message == Custom.V3_DETAIL_MESSAGE,
		"a custom hair finish is refused with the V3 detail message")

# C15: Rule A on every pattern of the five triples.
func check_rule_a() -> void:
	for group: String in Custom.COLOUR_TRIPLES:
		var names: Array = Custom.COLOUR_TRIPLES[group]
		for pattern: int in 8:
			var values := {}
			for bit: int in 3:
				values[names[bit]] = (7 + bit * 30) if pattern & (1 << bit) else 0
			var normalized := Custom.normalized(values)
			for bit: int in 3:
				var expected: int = values[names[bit]] if pattern == 7 else 0
				expect(normalized[names[bit]] == expected, "Rule A %s pattern %d %s" % [group, pattern, names[bit]])
		# A set triple with one corrupt value: the corrupt value is neutral (0),
		# so the whole triple is palette.
		var corrupt := Custom.normalized({names[0]: 10, names[1]: "x", names[2]: 10})
		expect(corrupt[names[0]] == 0 and corrupt[names[2]] == 0, "Rule A after a bad type, %s" % group)
		# Decoding applies Rule A too.
		var look := look3()
		look[names[1]] = 0
		var bytes := Custom.encode(look3(), 3)
		bytes[3 + Custom.FIELDS.find(names[1])] = 0
		var decoded := Custom.decode(bytes, 0)
		expect(decoded[names[0]] == 0 and decoded[names[2]] == 0, "decode applies Rule A to %s" % group)
	# Shared vectors with the server's read(): bounding, then Rule A.
	var shared := [
		[{"skin_tone": 300, "hair_hue": 241, "hair_sat": 50, "hair_light": 50}, {"skin_tone": 201, "hair_hue": 240, "hair_sat": 50, "hair_light": 50}],
		[{"eye_hue": 12, "eye_sat": -3, "eye_light": 40}, {"eye_hue": 0, "eye_sat": 0, "eye_light": 0}],
		[{"shirt_hue": 1, "shirt_sat": 1, "shirt_light": 1, "pants_hue": 5}, {"shirt_hue": 1, "shirt_sat": 1, "shirt_light": 1, "pants_hue": 0}],
		[{"boots_hue": 10.0, "boots_sat": 20, "boots_light": true}, {"boots_hue": 0, "boots_sat": 0, "boots_light": 0}],
		[{"hair_finish": 500, "skin_undertone": 101}, {"hair_finish": 101, "skin_undertone": 101}],
	]
	for pair: Array in shared:
		var result := Custom.normalized(pair[0] as Dictionary)
		for key: String in (pair[1] as Dictionary):
			expect(result[key] == (pair[1] as Dictionary)[key], "shared vector %s -> %s" % [str(pair[0]), key])

# C23 (data): the hair finish slider.
func check_hair_finish() -> void:
	expect(Custom.maximum("hair_finish") == 101 and Custom.field_version("hair_finish") == 3, "hair_finish 0..101, version 3")
	expect(Finish.canonical(25) == {"hair_detail": 2, "hair_finish": 0}
		and Finish.canonical(50) == {"hair_detail": 0, "hair_finish": 0}
		and Finish.canonical(75) == {"hair_detail": 1, "hair_finish": 0}, "25, 50, 75 save as the enum with hair_finish 0")
	expect(Finish.canonical(0) == {"hair_detail": 2, "hair_finish": 1}
		and Finish.canonical(100) == {"hair_detail": 1, "hair_finish": 101}
		and Finish.canonical(49) == {"hair_detail": 0, "hair_finish": 50}, "other positions keep s + 1 and the nearest enum")
	for pair: Array in [[0, 2], [37, 2], [38, 0], [62, 0], [63, 1], [100, 1]]:
		expect(Finish.nearest_enum(pair[0]) == pair[1], "nearest enum of %d is %d" % pair)
	var guarded := Finish.resolve({"hair_detail": 0, "hair_finish": 91})
	expect(not guarded.custom and guarded.enum == 0 and guarded.s == 50, "a disagreeing hair_detail wins (guard)")
	var typed := Finish.resolve({"hair_detail": 1, "hair_finish": 76})
	expect(not typed.custom and typed.s == 75, "a typed enum position draws the enum (Rule C)")
	var custom := Finish.resolve({"hair_detail": 1, "hair_finish": 91})
	expect(custom.custom and custom.s == 90 and custom.enum == 1, "a custom position is drawn")
	expect(not Finish.resolve({"hair_detail": 2}).custom and Finish.resolve({"hair_detail": 2}).s == 25, "Auto uses the enum's position")
	# w_swept = clamp((50 - s) / 25, 0, 1) * e(s), w_tousled likewise (spec 2.9).
	var expected := {0: Vector2(1.6, 0.0), 24: Vector2(1.024, 0.0), 25: Vector2(1.0, 0.0),
		26: Vector2(0.96, 0.0), 49: Vector2(0.04, 0.0), 50: Vector2.ZERO, 51: Vector2(0.0, 0.04),
		74: Vector2(0.0, 0.96), 75: Vector2(0.0, 1.0), 76: Vector2(0.0, 1.024), 100: Vector2(0.0, 1.6)}
	for s: int in expected:
		var w := Finish.weights(s)
		var want: Vector2 = expected[s]
		expect(absf(w.x - want.x) < 1e-5 and absf(w.y - want.y) < 1e-5, "weights at %d: %s (want %s)" % [s, w, want])
	expect(is_equal_approx(Finish.gain(0), 1.6) and is_equal_approx(Finish.gain(100), 1.6)
		and Finish.gain(25) == 1.0 and Finish.gain(50) == 1.0 and Finish.gain(75) == 1.0, "e(s) ends at E_MAX 1.6")
	var levels := {"rowan_shag": [17, 33, 50, 0, 100], "mira_bun": [50, 67, 83, 0, 100]}
	for module: String in levels:
		var got: Array = []
		for s: int in [25, 50, 75, 0, 100]:
			got.append(RLHeadPortraitMap.detail_level(s, module))
		expect(got == levels[module], "%s levels at 25/50/75/0/100: %s" % [module, got])
		var previous := -1
		for s: int in 101:
			var level := RLHeadPortraitMap.detail_level(s, module)
			expect(level >= previous, "%s level monotonic at %d" % [module, s])
			previous = level

# C6, C7: creation suffix and spawn trailers.
func check_creation_and_spawns() -> void:
	var look := look3()
	for version: int in [1, 2, 3]:
		var packet := Wire.create_character("Portrait", "secret", look.merged({"actor_type": 1, "hair": 299}), 2, version)
		var nul := packet.find(0, 3)
		var suffix := packet.slice(nul + 1)
		expect(suffix[8] == 2 and suffix.size() == [0, 19, 28, 67][version], "version %d suffix %d bytes, class at 8" % [version, suffix.size()])
		expect(suffix.slice(9, 12) == PackedByteArray(Custom.tag(version)), "version %d trailer at suffix 9" % version)
		if version == 3:
			expect(suffix[49] == 88 and suffix[50] == 201 and suffix[66] == 13 and suffix[28] == 0
				and suffix[29] == 87 and suffix[30] == 21 and suffix[48] == 31,
				"V3 at suffix 28-66: eye_style 29, eye_depth 30, hair_finish 49, skin_tone 50, boots_light 66")
		for wardrobe: bool in [false, true]:
			var body := PackedByteArray()
			body.resize(28)
			body[10] = 1
			body.append_array("Portrait".to_ascii_buffer())
			body.append_array(PackedByteArray([0, 0, 0, 255, 3, 0]))
			if wardrobe:
				body.append_array(PackedByteArray([87, 65, 1, 7, 8, 9, 0]))
			body.append_array(Custom.encode(look, version))
			var actor := Wire.decode_actor(body, true)
			for field: String in Custom.FIELDS:
				var expected: int = look[field] if Custom.field_version(field) <= version else Custom.DEFAULTS[field]
				expect(actor.appearance.get(field) == expected, "spawn v%d wardrobe %s %s" % [version, wardrobe, field])

# C8: the leaderboard codec.
func check_ranking() -> void:
	var portrait := {"actor_type": 1, "appearance": look3().merged({"skin": 2, "hair": 111, "eyes": 3}), "equipment_visuals": {"0": 20}}
	expect(Ranking._valid_portrait(portrait), "a portrait with all 55 fields is valid")
	for field: String in Custom.V3_FIELDS:
		var corrupt := portrait.duplicate(true)
		corrupt.appearance[field] = Custom.maximum(field) + 1
		expect(not Ranking._valid_portrait(corrupt), "ranking bounds %s" % field)
	for version: int in [1, 2]:
		var trimmed := {"actor_type": 0, "appearance": {"skin": 1}, "equipment_visuals": {}}
		for field: String in Custom.fields_for(version):
			trimmed.appearance[field] = look3()[field]
		expect(Ranking._valid_portrait(trimmed), "a V%d-only portrait is valid" % version)
	var unknown := portrait.duplicate(true)
	unknown.appearance["future_field"] = 1
	expect(not Ranking._valid_portrait(unknown), "an unknown key still invalidates the portrait")

# C9, C10: capabilities and probes.
func check_probes() -> void:
	var capabilities: Array = Wire.CLIENT_CAPABILITIES
	var v2 := capabilities.find("actor_customization_v2")
	expect(capabilities.has("actor_customization_v1") and v2 >= 0 and capabilities.find("actor_customization_v3") == v2 + 1,
		"v1, v2 and v3 capabilities, v3 right after v2")
	expect(Wire.appearance_protocol_probe() == PackedByteArray([190, 4, 0, 80, 67, 2]), "the default probe stays PC/2")
	expect(Wire.appearance_protocol_probe(2) == PackedByteArray([190, 4, 0, 80, 67, 2])
		and Wire.appearance_protocol_probe(3) == PackedByteArray([190, 4, 0, 80, 67, 3]), "PC/2 and PC/3 probes")
	expect(Wire.decode_server(190, PackedByteArray([80, 67, 2])).get("version") == 2
		and Wire.decode_server(190, PackedByteArray([80, 67, 3])).get("version") == 3, "PC/2 and PC/3 replies")
	for bad: PackedByteArray in [PackedByteArray([80, 67, 1]), PackedByteArray([80, 67, 4]), PackedByteArray([80, 67, 3, 0]),
			PackedByteArray(), PackedByteArray([90, 90, 3])]:
		expect(Wire.decode_server(190, bad).type == "invalid", "probe reply %s is invalid" % bad.hex_encode())

func _recording_network() -> Node:
	var recorder := GDScript.new()
	recorder.source_code = "extends \"res://src/network/network_client.gd\"\nvar sent: Array[PackedByteArray] = []\nfunc send_frame(frame: PackedByteArray, _sensitive := false) -> Error:\n\tif offline_hud_preview: return ERR_UNAVAILABLE\n\tsent.append(frame)\n\treturn OK\n"
	if recorder.reload() != OK:
		expect(false, "recording network compiles")
		return null
	var network: Node = recorder.new()
	root.add_child(network)
	network.set_process(false)
	return network

func _reply(network: Node, version: int) -> void:
	network.set("_rx", Wire.encode(190, PackedByteArray([80, 67, version])))
	network.call("_drain_packets")

# C11, C12, C19: creation, Apply stripping and negotiation through a recording network.
func check_sending() -> void:
	var network := _recording_network()
	if network == null:
		return
	var changed: Array[int] = []
	network.appearance_protocol_changed.connect(func(version: int) -> void: changed.append(version))
	var neutral := Custom.normalized({})
	var look2_full := Custom.normalized(look2())
	var look := look3()
	# Version 1.
	expect(network.appearance_protocol_version() == 1, "starts at version 1")
	expect(network.create_character("Portrait", "secret", look) == ERR_UNAVAILABLE and network.sent.is_empty(),
		"non-neutral V2/V3 creation refused at version 1, nothing sent")
	expect(network.create_character("Portrait", "secret", neutral) == OK
		and network.sent[-1].slice(network.sent[-1].size() - 10) == Custom.encode(neutral, 1), "neutral creation sends PC/1 at version 1")
	var everything := PackedStringArray()
	for field: String in Custom.FIELDS:
		everything.append("%s=%d" % [field, neutral[field]])
	expect(network.send_chat("#appearance skin=2 " + " ".join(everything)) == OK, "neutral full Apply at version 1")
	var text := Wire.nul_string(network.sent[-1].slice(3))
	for field: String in Custom.EXTRA_FIELDS + Custom.V3_FIELDS:
		expect(not text.contains(field + "="), "version 1 strips neutral %s" % field)
	expect(text.contains("skin=2") and text.contains("jaw=50"), "version 1 keeps palette and PC/1 tokens")
	# Version 2.
	_reply(network, 2)
	expect(network.appearance_protocol_version() == 2 and changed == [2], "PC/2 reply gives version 2")
	var count: int = network.sent.size()
	expect(network.create_character("Portrait", "secret", look) == ERR_UNAVAILABLE and network.sent.size() == count,
		"non-neutral V3 creation refused at version 2")
	expect(network.appearance_error == Custom.V3_DETAIL_MESSAGE, "the refusal explains the V3 detail options")
	expect(network.create_character("Portrait", "secret", look2_full.merged({"hair_hue": 30, "hair_sat": 40, "hair_light": 50}, true)) == ERR_UNAVAILABLE
		and network.appearance_error == Custom.COLOUR_MESSAGE, "a custom colour is refused at version 2 with the colour message")
	expect(network.create_character("Portrait", "secret", look2_full) == OK
		and network.sent[-1].slice(network.sent[-1].size() - 19).hex_encode() == PC2_HEX, "a PC/3 client saves V2 data on a PC/2 server")
	everything = PackedStringArray()
	for field: String in Custom.FIELDS:
		everything.append("%s=%d" % [field, look2_full[field]])
	expect(network.send_chat("#appearance " + " ".join(everything)) == OK, "PC/2 Apply with neutral V3 at version 2")
	text = Wire.nul_string(network.sent[-1].slice(3))
	for field: String in Custom.V3_FIELDS:
		expect(not text.contains(field + "="), "version 2 strips neutral %s" % field)
	expect(text.contains("eye_tilt=34") and text.contains("hair_detail=2"), "version 2 keeps PC/2 tokens")
	count = network.sent.size()
	expect(network.send_chat("#appearance eye_tilt=40 skin_tone=50") == ERR_UNAVAILABLE and network.sent.size() == count,
		"a non-neutral colour token refuses the whole command at version 2")
	expect(network.appearance_error == Custom.COLOUR_MESSAGE, "with the colour message")
	expect(network.send_chat("#appearance hair_finish=60") == ERR_UNAVAILABLE and network.appearance_error == Custom.V3_DETAIL_MESSAGE,
		"a custom hair finish is refused at version 2")
	expect(network.send_chat("#appearance eyelid=60") == ERR_UNAVAILABLE, "a V3 offset is refused at version 2")
	expect(network.send_chat("#appearance skin_tone=1 skin_tone=0") == ERR_INVALID_DATA, "a duplicate V3 token is invalid")
	expect(network.send_chat("#appearance skin_tone=x") == ERR_INVALID_DATA, "a non-integer V3 token is invalid")
	expect(network.send_chat("#appearance skin_tone=202") == ERR_INVALID_DATA, "an out-of-range V3 token is invalid")
	# Version 3.
	_reply(network, 3)
	expect(network.appearance_protocol_version() == 3 and changed == [2, 3], "PC/3 reply gives version 3")
	expect(network.create_character("Portrait", "secret", look) == OK
		and network.sent[-1].slice(network.sent[-1].size() - 58).hex_encode() == LOOK3_HEX, "version 3 creation sends PC/3")
	expect(network.create_character("Portrait", "secret", neutral) == OK
		and network.sent[-1].slice(network.sent[-1].size() - 58).hex_encode() == NEUTRAL_HEX, "version 3 sends PC/3 even when neutral")
	everything = PackedStringArray()
	for field: String in Custom.FIELDS:
		everything.append("%s=%d" % [field, look[field]])
	expect(network.send_chat("#appearance " + " ".join(everything)) == OK
		and Wire.nul_string(network.sent[-1].slice(3)).contains("boots_light=13"), "version 3 passes everything")
	_reply(network, 2)
	expect(network.appearance_protocol_version() == 3 and changed == [2, 3], "a later PC/2 reply never lowers the version")
	network.call("_reset_coordinate_session")
	expect(network.appearance_protocol_version() == 1 and changed == [2, 3, 1], "a reset returns to version 1")
	_reply(network, 3)
	_reply(network, 2)
	expect(network.appearance_protocol_version() == 3 and changed == [2, 3, 1, 3], "[PC/3, PC/2] stays at 3 with one change")
	network.call("_reset_coordinate_session")
	_reply(network, 2)
	expect(network.appearance_protocol_version() == 2, "PC/2 alone gives 2")
	network.queue_free()

# C13: real loopback probes.
func check_real_connection_probe() -> void:
	var listener := TCPServer.new()
	if listener.listen(0, "127.0.0.1") != OK:
		expect(false, "loopback fixture starts")
		return
	var network = (load("res://src/network/network_client.gd") as GDScript).new()
	root.add_child(network)
	# Peers: echo PC/2 only (a PC/2 server), echo both (V3), silent (pre-PC).
	for peer_kind: String in ["pc2", "v3", "silent"]:
		expect(network.connect_to_server("127.0.0.1", listener.get_local_port(), false) == OK, "%s: connection starts" % peer_kind)
		var peer: StreamPeerTCP
		var deadline := Time.get_ticks_msec() + 5000
		var received := PackedByteArray()
		var probes: Array[PackedByteArray] = []
		while Time.get_ticks_msec() < deadline and probes.size() < 2:
			network.call("_process", 0.0)
			if peer == null and listener.is_connection_available():
				peer = listener.take_connection()
			if peer != null:
				peer.poll()
				if peer.get_available_bytes() > 0:
					received.append_array(peer.get_data(peer.get_available_bytes())[1])
				while not received.is_empty():
					var decoded := Wire.try_decode(received)
					if decoded.status != "ok": break
					if decoded.command == 190:
						probes.append(decoded.payload)
					received = received.slice(decoded.consumed)
			await process_frame
		expect(probes == [PackedByteArray([80, 67, 2]), PackedByteArray([80, 67, 3])],
			"%s: the PC/2 probe, then the PC/3 probe (%s)" % [peer_kind, str(probes)])
		var want := {"pc2": 2, "v3": 3, "silent": 1}[peer_kind] as int
		if peer != null:
			if peer_kind != "silent":
				peer.put_data(Wire.encode(190, PackedByteArray([80, 67, 2])))
			if peer_kind == "v3":
				peer.put_data(Wire.encode(190, PackedByteArray([80, 67, 3])))
		deadline = Time.get_ticks_msec() + (2000 if want > 1 else 400)
		while network.appearance_protocol_version() != want and Time.get_ticks_msec() < deadline:
			network.call("_process", 0.0)
			await process_frame
		for _frame: int in 3:
			network.call("_process", 0.0)
			await process_frame
		expect(network.appearance_protocol_version() == want, "%s peer gives version %d (%d)" % [peer_kind, want,
			network.appearance_protocol_version()])
		network.disconnect_from_server()
		expect(network.appearance_protocol_version() == 1, "%s: a disconnect returns to version 1" % peer_kind)
		if peer != null: peer.disconnect_from_host()
	listener.stop()
	network.queue_free()
	await process_frame
