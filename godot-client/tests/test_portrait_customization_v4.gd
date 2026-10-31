extends SceneTree
## Append-only PC/4, old-server edit preservation, age carrier and form behavior.
const PC := preload("res://src/actors/portrait_customization.gd")
const AGE := preload("res://src/actors/character_age.gd")
const MAP := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const FORM := preload("res://src/ui/portrait_customization_form.gd")
const WIRE := preload("res://src/network/protocol.gd")
const PC3_HEX := "50430305461e3c5a55020c17222d38434e596400571564194b283c0a5a2142630d6501331a4c0c1f58c901f06565a8473a01010178323c3d1a0d"
const FIXTURE := {31: {"name": "fixture_tie", "tie_height": true, "variants": {
	"female": "fixture_tie_female", "male": {"name": "fixture_tie_male", "tie_height": false}}}}
class FixtureForm extends "res://src/ui/portrait_customization_form.gd":
	func _module_entries() -> Dictionary:
		return FIXTURE
var checks := 0
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	var legacy := PC.decode(PC3_HEX.hex_decode(), 0)
	var look := legacy.merged({"skin_age": 73, "hair_grey": 42, "hair_tie_height": 17}, true)
	var bytes := PC.encode(look, 4)
	expect(bytes.size() == 61 and bytes.hex_encode() == "504304" + PC3_HEX.substr(6) + "492a11", "shared PC/4 fixture, frozen PC/3 prefix")
	expect(PC.decode(bytes, 0) == look, "PC/4 round-trip")
	expect(PC.encode(look, 3).hex_encode() == PC3_HEX, "PC/3 encoding unchanged")
	expect(legacy.skin_age == 0 and legacy.hair_grey == 0 and legacy.hair_tie_height == 50, "old saves get neutral new fields")
	for field: String in PC.V4_FIELDS:
		for invalid: Variant in [-1, 101, true, 0.5, "30", null]:
			expect(not PC.validate({field: invalid}, 4).ok, field + " rejects invalid edits")
		var single := {field: 17}
		expect(PC.validate(single, 3).message == PC.V4_MESSAGE, field + " old-server gate explains preservation")
		expect(PC.validate({field: PC.DEFAULTS[field]}, 3).ok, field + " neutral allowed on old server")
	for age: int in 101:
		for grey: int in 101:
			var packed := AGE.packed(age / 100.0, grey / 100.0)
			expect(AGE.unpacked(packed).is_equal_approx(Vector2(age, grey) / 100.0), "exact packed age/grey %d/%d" % [age, grey])
	expect(AGE.packed(0, 0) == 1.0 and AGE.unpacked(1).is_zero_approx(), "neutral carrier stays exactly legacy alpha 1")
	expect(AGE.packed(NAN, INF) == 1.0, "invalid direct authoring values are neutral")
	for sex: String in ["female", "male"]:
		var face := MAP.face(look, sex)
		var inverse := MAP.to_portrait_fields(face, sex)
		expect(is_equal_approx(face.skin_age, .73) and is_equal_approx(face.hair_grey, .42) and is_equal_approx(face.hair_tie_height, -.66), "age mapping " + sex)
		for field: String in PC.V4_FIELDS:
			expect(inverse[field] == look[field], "inverse " + field)
		var copy := RLHeadAppearance.from_dict(face.to_dict())
		expect(copy.to_dict() == face.to_dict(), "authoring dictionary preserves age " + sex)
	await _form(look)
	await _network(look)
	print("Portrait customization v4: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _form(look: Dictionary) -> void:
	var form := FixtureForm.new()
	root.add_child(form)
	form.set_hair_style(2)
	form.set_body(0)
	form.set_values(look.merged({"hair_module": 31}, true))
	await process_frame
	expect(not form.age_enabled() and form.age_notice.visible and not form.age_box.visible, "old-server notice with saved edits")
	expect(form.values().skin_age == 73 and form.values().hair_grey == 42, "hidden values preserved")
	form.set_detail_enabled(true)
	form.set_age_enabled(true)
	expect(form.age_box.visible and not form.age_notice.visible, "PC/4 exposes age controls")
	expect((form.controls.skin_age as HSlider).editable and (form.controls.hair_grey as HSlider).editable, "independent age sliders enabled")
	expect((form.controls.hair_tie_height as HSlider).get_parent().visible, "qualified female tie height shown")
	form.set_body(1)
	expect(not (form.controls.hair_tie_height as HSlider).get_parent().visible, "unqualified male tie height hidden")
	form.set_body(0)
	form.set_hair_style(0)
	expect(not (form.controls.hair_tie_height as HSlider).get_parent().visible, "bald hides tie height")
	form.set_age_enabled(false)
	expect(form.values().skin_age == 73 and form.values().hair_grey == 42, "protocol fallback preserves edits")
	var before := form.values()
	form.reset_age()
	var after := form.values()
	for field: String in PC.FIELDS:
		expect(after[field] == (PC.DEFAULTS[field] if field in PC.V4_FIELDS else before[field]), "age reset scope " + field)
	form.free()

func _network(look: Dictionary) -> void:
	var recorder := GDScript.new()
	recorder.source_code = "extends \"res://src/network/network_client.gd\"\nvar sent: Array[PackedByteArray] = []\nfunc send_frame(frame: PackedByteArray, _sensitive := false) -> Error:\n\tsent.append(frame)\n\treturn OK\n"
	expect(recorder.reload() == OK, "recording network compiles")
	var network: Node = recorder.new()
	root.add_child(network)
	var full := look.merged({"actor_type": 1, "skin": 1, "hair": 1, "eyes": 1, "head": 0, "shirt": 1, "pants": 1, "boots": 1, "class_id": 0}, true)
	for version: int in [2, 3]:
		network.call("_reset_coordinate_session")
		network.set("_rx", WIRE.encode(190, PackedByteArray([80, 67, version])))
		network.call("_drain_packets")
		expect(network.create_character("Agedraft", "secret", full) == ERR_UNAVAILABLE, "old server blocks age-bearing creation " + str(version))
		expect(network.sent.is_empty(), "refused creation sends nothing")
		expect(network.send_chat("#appearance skin_age=73") == ERR_UNAVAILABLE and network.appearance_error == PC.V4_MESSAGE, "old server edit refusal")
	network.set("_rx", WIRE.encode(190, PackedByteArray([80, 67, 4])))
	network.call("_drain_packets")
	expect(network.appearance_protocol_version() == 4, "PC/4 negotiated")
	expect(network.create_character("Agedraft", "secret", full) == OK and network.sent[-1].slice(-61) == PC.encode(look, 4), "PC/4 creation carries new fields")
	expect(network.send_chat("#appearance skin_age=73 hair_grey=42 hair_tie_height=17") == OK, "PC/4 atomic edit")
	network.free()
