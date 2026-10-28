extends SceneTree
## Headless contract for RLHeadPortraitMap: develop's saved appearance
## (PortraitCustomization fields and palette indices) to the RL head at High.
##
##   Godot --headless --path godot-client --script res://tests/test_rl_head_portrait_map.gd
##
## Face (D3, recentred offset-linear): Rowan and Mira reproduce the authored RL
## heads (every control 0); every field is monotonic with the sign of (v - c),
## reaches its clamp at the far end, and is the formula exactly; missing or
## invalid fields count as 50. Grooming: every hair style x sex (D5 modules,
## legacy names, bald), every facial_hair x sex (beards by name, none and no
## stubble on women), every palette index (skin, eyes, hair). The hl_ hair
## shapes and the hair finish's fine-detail level centre on each module's
## preset; PC/3 fields slot in over the derived
## values; the inverse map round-trips the presets.

const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
## The direction each field drives its RL control (plan 2.1 sign table, checked
## by tests/rl_head_gain_probe.gd against the Low/Medium sculpt): RL eye_tilt +
## raises the inner corners where the slider raises the outer ones.
const EXPECTED_SIGN := {"jaw": 1.0, "cheekbones": 1.0, "nose": 1.0, "face_length": 1.0, "eye_size": 1.0,
	"eye_tilt": -1.0, "eye_spacing": 1.0, "nose_width": 1.0, "lip_fullness": 1.0, "brow_depth": 1.0}
const Map := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")

var _checks := 0
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures += 1
		push_error("rl head portrait map: " + message)


func _run() -> void:
	_check_data()
	_check_centres()
	_check_fields()
	_check_missing()
	_check_hair()
	_check_facial_hair()
	_check_palettes()
	_check_details()
	_check_hair_shapes()
	_check_v3()
	_check_inverse()
	print("rl head portrait map: %d checks, %d failures" % [_checks, _failures])
	print("rl head portrait map: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


func _check_data() -> void:
	var data := Map.data()
	_expect(not data.is_empty(), "wire defaults load from " + Map.DATA_PATH)
	for field: String in Map.FACE_FIELDS:
		for sex: String in ["female", "male"]:
			var g := Map.gain(field, sex)
			_expect(signf(g) == float(EXPECTED_SIGN[field]) and absf(g) >= 0.2 and absf(g) <= 3.0,
				"%s %s gain %.3f has the expected sign and a bounded size" % [sex, field, g])
		_expect(Map.primary_control(field) == Map.PRIMARY[field], "%s drives %s" % [field, Map.PRIMARY[field]])
	var controls: PackedStringArray = RLHeadLibrary.head("female").get("control_names", PackedStringArray())
	_expect(controls.size() == 21, "the head declares 21 controls (%d)" % controls.size())
	for field: String in Map.FACE_FIELDS:
		_expect(controls.has(Map.primary_control(field)), "primary control %s exists on the head" % Map.primary_control(field))
	for control: String in Map.V3_CONTROLS:
		_expect(controls.has(control), "PC/3 control %s exists on the head" % control)
	for coupling: Dictionary in Map.secondaries():
		_expect(controls.has(str(coupling.control)), "secondary control %s exists" % coupling.control)


func _check_centres() -> void:
	for pair: Array in [["male", "Rowan"], ["female", "Mira"]]:
		var appearance := PRESETS.appearance(pair[1])
		var values := Map.controls(appearance, pair[0])
		_expect(values.is_empty(), "%s on a %s body maps to the authored head (all controls 0) %s" % [pair[1], pair[0], values])
		for field: String in Map.FACE_FIELDS:
			_expect(is_equal_approx(Map.centre(field, pair[0]), float(PRESETS.shape(pair[1])[field])),
				"%s centre for %s is %s's value" % [pair[0], field, pair[1]])
	# Tavi lands near the RL tavi preset's broad jaw and heavy brow.
	var tavi := Map.controls(PRESETS.appearance("Tavi"), "male")
	_expect(float(tavi.get("jaw_width", 0.0)) > 0.2 and float(tavi.get("brow_ridge", 0.0)) > 0.0
		and float(tavi.get("eye_tilt", 0.0)) > 0.0,
		"Tavi maps to a broader jaw and a heavier brow than Rowan %s" % tavi)


func _check_fields() -> void:
	# The primary controls take no coupling from another field, so with one
	# field set (the rest at 50) the control is exactly the formula.
	for sex: String in ["female", "male"]:
		for field: String in Map.FACE_FIELDS:
			var control := Map.primary_control(field)
			var c := Map.centre(field, sex)
			var g := Map.gain(field, sex)
			var previous := -INF
			var monotonic := true
			var exact := true
			var signs := true
			for v: int in range(0, 101):
				var x := float(Map.controls({field: v}, sex).get(control, 0.0))
				exact = exact and absf(x - clampf(g * (float(v) - c) / 50.0, -1.0, 1.0)) < 1e-5
				var oriented := x * signf(g)
				monotonic = monotonic and oriented >= previous - 1e-6
				previous = oriented
				signs = signs and (signf(x) == signf(g) * signf(float(v) - c) or (is_zero_approx(x) and absf(float(v) - c) < 1e-3))
			_expect(monotonic, "%s %s is monotonic over 0..100" % [sex, field])
			_expect(exact, "%s %s is g*(v-c)/50 clamped (g %.3f, c %.0f)" % [sex, field, g, c])
			_expect(signs, "%s %s has the sign of g * (v - c)" % [sex, field])
			var low := float(Map.controls({field: 0}, sex).get(control, 0.0)) * signf(g)
			var high := float(Map.controls({field: 100}, sex).get(control, 0.0)) * signf(g)
			_expect(low < 0.0 and high > 0.0 or (c <= 0.0 and low == 0.0) or (c >= 100.0 and high == 0.0),
				"%s %s endpoints straddle the authored head (%.3f, %.3f)" % [sex, field, low, high])
			_expect(absf(low) <= 1.0 and absf(high) <= 1.0, "%s %s endpoints stay within [-1, 1]" % [sex, field])


func _check_missing() -> void:
	for sex: String in ["female", "male"]:
		var neutral := {}
		for field: String in PortraitCustomization.FIELDS:
			neutral[field] = PortraitCustomization.DEFAULTS[field]
		_expect(Map.controls({}, sex) == Map.controls(neutral, sex), "%s: missing fields count as 50" % sex)
		var junk := {"jaw": "wide", "nose": 50.5, "eye_size": null, "brow_depth": true, "cheekbones": -40,
			"lip_fullness": 400}
		var expected := neutral.duplicate()
		expected["cheekbones"] = 0
		expected["lip_fullness"] = 100
		_expect(Map.controls(junk, sex) == Map.controls(expected, sex),
			"%s: invalid fields count as 50, out-of-range ones clamp" % sex)
		var face := Map.face({}, sex)
		_expect(face.sex == sex and face.hair == RLHeadAppearance.NONE and face.beard == RLHeadAppearance.NONE,
			"%s: an empty appearance is a bald, clean-shaven head of the body's sex" % sex)


func _check_hair() -> void:
	var names := ["Bald", "Parted", "Long", "Buns", "Buzzcut", "Bob", "Ponytail", "Long braid", "Topknot", "Mohawk"]
	for sex: String in ["female", "male"]:
		for style: int in 10:
			for colour: int in [0, 7, 19]:
				var appearance := {"hair": AppearanceVariants.pack_hair(style, colour)}
				var hair := Map.hair(appearance, sex)
				var expected := RLHeadAppearance.NONE
				if style == 1 and sex == "male":
					expected = "rowan_shag"
				elif style == 3 and sex == "female":
					expected = "mira_bun"
				elif style > 0:
					expected = RLHeadLibrary.LEGACY_PREFIX + RLHeadLibrary.LEGACY_HAIR_STYLES[style - 1]
				_expect(hair == expected, "%s %s (style %d, colour %d) -> %s (got %s)" % [sex, names[style],
					style, colour, expected, hair])
				if hair.begins_with(RLHeadLibrary.LEGACY_PREFIX):
					_expect(Map.legacy_style(hair) == style, "%s round-trips to style %d" % [hair, style])
					_expect(FileAccess.file_exists(RLHeadLibrary.legacy_hair_path(sex,
						hair.trim_prefix(RLHeadLibrary.LEGACY_PREFIX))), "%s's fitted file exists for %s" % [hair, sex])
				elif Map.is_module(hair):
					_expect(FileAccess.file_exists(RLHeadLibrary.hair_path(hair)), "module %s exists" % hair)
	# Legacy packed values (0-19) and the extended range decode the same way.
	_expect(Map.hair({"hair": 1}, "male") == "rowan_shag" and Map.hair({"hair": 0}, "male") == RLHeadAppearance.NONE,
		"legacy hair bytes decode through AppearanceVariants.hair_style")


func _check_facial_hair() -> void:
	var expected := ["none", "stubble", "moustache", "goatee", "short_beard", "full_beard"]
	for value: int in 6:
		var male := Map.face({"facial_hair": value}, "male")
		var female := Map.face({"facial_hair": value}, "female")
		_expect(male.beard == expected[value], "male facial_hair %d -> %s (%s)" % [value, expected[value], male.beard])
		if value >= 2:
			_expect(FileAccess.file_exists(RLHeadLibrary.beard_path(male.beard)), "beard %s exists" % male.beard)
		var stubble := [0.0, 0.6, 0.3, 0.3, 0.3, 0.3][value] as float
		_expect(is_equal_approx(male.stubble_amount(), stubble), "male facial_hair %d paints stubble %.1f (%.2f)"
			% [value, stubble, male.stubble_amount()])
		_expect(female.beard == RLHeadAppearance.NONE and female.stubble_amount() == 0.0,
			"female facial_hair %d draws no beard and no stubble at High" % value)
	_expect(Map.face({"facial_hair": 9}, "male").beard == "full_beard", "facial_hair above 5 clamps")


func _check_palettes() -> void:
	for sex: String in ["female", "male"]:
		var seen := {}
		for index: int in 10:
			var colour := Map.face({"skin": index}, sex).skin
			_expect(colour == Map.skin_color(index, sex), "%s skin %d through the table" % [sex, index])
			_expect(_in_unit(colour), "%s skin %d is a colour (%s)" % [sex, index, colour])
			seen[colour.to_html()] = true
		_expect(seen.size() == 10, "%s: ten distinct skin colours" % sex)
		seen.clear()
		for index: int in 20:
			var face := Map.face({"hair": AppearanceVariants.pack_hair(2, index)}, sex)
			_expect(face.hair_color == Map.hair_color(index, sex) and _in_unit(face.hair_color),
				"%s hair colour %d through the table" % [sex, index])
			var brow := face.hair_color * Map.BROW_FROM_HAIR
			_expect(face.brow_color.is_equal_approx(Color(brow.r, brow.g, brow.b)),
				"%s brows follow hair colour %d" % [sex, index])
			seen[face.hair_color.to_html()] = true
		_expect(seen.size() == 20, "%s: twenty distinct hair colours" % sex)
	for sex: String in ["female", "male"]:
		var eyes := {}
		for index: int in 12:
			var colour := Map.face({"eyes": index}, sex).eyes
			_expect(colour == Map.eye_color(index, sex) and _in_unit(colour), "%s eye colour %d through the table" % [sex, index])
			eyes[colour.to_html()] = true
		_expect(eyes.size() == 12, "%s: twelve distinct eye colours" % sex)
	for category: String in ["skin", "hair", "eyes"]:
		for sex: String in ["female", "male"]:
			_expect(Map._table(category, sex).size() == {"skin": 10, "hair": 20, "eyes": 12}[category],
				"%s %s colours come from the calibrated table" % [sex, category])
	_expect(Map._table("beard", "male").size() == 20, "male beard colours come from their own calibrated table")
	for index: int in 20:
		var face := Map.face({"facial_hair": 5, "hair": AppearanceVariants.pack_hair(1, index)}, "male")
		_expect(face.beard_color_set and face.beard_color == Map._colour(Map._table("beard", "male")[index], Color.BLACK),
			"male beard colour %d through its table" % index)
	_expect(Map.skin_color(13, "male") == Map.skin_color(3, "male"), "palette indices wrap as AppearanceVariants does")


func _in_unit(colour: Color) -> bool:
	return colour.r >= 0.0 and colour.g >= 0.0 and colour.b >= 0.0 \
		and colour.r <= 1.0 and colour.g <= 1.0 and colour.b <= 1.0


func _check_details() -> void:
	for sex: String in ["female", "male"]:
		var seeds := Map.defaults(sex)
		for skin: int in 10:
			var face := Map.face({"skin": skin}, sex)
			_expect(is_equal_approx(face.freckles, float((seeds.freckles as Array)[skin]))
				and is_equal_approx(face.liner, float((seeds.liner as Array)[skin])),
				"%s skin %d takes its freckle and liner defaults" % [sex, skin])
			_expect(face.lip_tint == Map.lip_tint_color(int((seeds.lip_tint as Array)[skin])),
				"%s skin %d takes its lip tint" % [sex, skin])
		var face := Map.face({}, sex)
		_expect(is_equal_approx(face.brow_style, float(seeds.brow_style))
			and is_equal_approx(face.brow_thickness, float(seeds.brow_thickness)),
			"%s brow style and thickness defaults" % sex)


func _check_hair_shapes() -> void:
	for pair: Array in [["male", 1, "rowan_shag", "Rowan"], ["female", 3, "mira_bun", "Mira"]]:
		var preset := PRESETS.shape(pair[3])
		var at_preset := Map.face({"hair": AppearanceVariants.pack_hair(pair[1], 0),
			"hair_length": preset.hair_length, "hair_volume": preset.hair_volume,
			"hair_detail": preset.hair_detail}, pair[0])
		_expect(at_preset.hair == pair[2] and at_preset.hair_length == 0.0 and at_preset.hair_volume == 0.0
			and at_preset.hair_detail == RLHeadAppearance.DEFAULT_HAIR_DETAIL,
			"%s at %s's length, volume and finish draws the module as authored" % [pair[2], pair[3]])
		var longer := Map.face({"hair": AppearanceVariants.pack_hair(pair[1], 0), "hair_length": 100,
			"hair_volume": 0}, pair[0])
		_expect(longer.hair_length > 0.0 and longer.hair_volume < 0.0,
			"%s: longer and thinner move the hl_ shapes (%.2f, %.2f)" % [pair[2], longer.hair_length,
				longer.hair_volume])
		for field: String in ["hair_length", "hair_volume"]:
			var edges := []
			for value: int in [0, 50, 100]:
				var face := Map.face({"hair": AppearanceVariants.pack_hair(pair[1], 0), field: value}, pair[0])
				edges.append(face.get(field))
			var expected := []
			for value: int in [0, 50, 100]:
				expected.append(clampf((float(value) - float(preset[field])) / 50.0, -1.0, 1.0))
			_expect(edges == expected, "%s: %s 0/50/100 is (v - %d) / 50 clamped %s" % [pair[2], field,
				preset[field], edges])
		var default := Map.face({"hair": AppearanceVariants.pack_hair(pair[1], 0)}, pair[0])
		_expect(default.hair_length < 0.0, "%s: the default 50 is shorter than the preset (%.2f)" % [pair[2], default.hair_length])
	# The finish -> fine-detail level (data hair.detail; owner decision, colour
	# model spec revision 3, 4.7): the saved finishes sit at slider positions
	# Swept 25, Classic 50, Tousled 75, mapped piecewise linearly through
	# (0, 0), (the module's preset finish, 50) and (100, 100).
	_expect(Map.finish_slider(0) == 50 and Map.finish_slider(1) == 75 and Map.finish_slider(2) == 25,
		"the saved finishes sit at slider positions Classic 50, Tousled 75, Swept 25")
	for row: Array in [["male", 1, "rowan_shag", "Rowan", [33, 50, 17]], ["female", 3, "mira_bun", "Mira", [67, 83, 50]]]:
		var levels := []
		for finish: int in 3:
			levels.append(Map.face({"hair": AppearanceVariants.pack_hair(row[1], 0), "hair_detail": finish},
				row[0]).hair_detail)
		_expect(levels == row[4], "%s: Classic, Tousled, Swept give detail levels %s" % [row[2], levels])
		var preset_finish := Map.finish_slider(int(PRESETS.shape(row[3]).hair_detail))
		var listed: Variant = ((Map.data().get("hair", {}) as Dictionary).get("detail", {}) as Dictionary).get("sliderPresetFinish")
		_expect(listed is Dictionary and int((listed as Dictionary).get(row[2], -1)) == preset_finish,
			"%s: the data's preset finish is %s's own (slider %d)" % [row[2], row[3], preset_finish])
		var curve: Array[int] = []
		for s: int in 101:
			curve.append(Map.detail_level(s, row[2]))
		var steady := true
		for s: int in 100:
			steady = steady and curve[s + 1] >= curve[s] and curve[s + 1] - curve[s] <= 2
		_expect(curve[0] == 0 and curve[preset_finish] == RLHeadAppearance.DEFAULT_HAIR_DETAIL and curve[100] == 100
			and steady, "%s: slider 0, the preset finish and 100 give 0, 50 and 100, rising without a jump" % row[2])
	_expect(Map.face({"hair": AppearanceVariants.pack_hair(1, 0), "hair_detail": 7}, "male").hair_detail == 17
		and Map.face({"hair": AppearanceVariants.pack_hair(1, 0), "hair_detail": 1.5}, "male").hair_detail == 33,
		"an out-of-range finish clamps and a non-integer one counts as Classic")
	var legacy := Map.face({"hair": AppearanceVariants.pack_hair(2, 0), "hair_length": 100, "hair_detail": 2}, "male")
	_expect(legacy.hair_length == 0.0 and legacy.hair_detail == RLHeadAppearance.DEFAULT_HAIR_DETAIL,
		"a game hairstyle is groomed by the actor, not by hl_ shapes or the detail level")
	var rl_face := RLHeadAppearance.from_dict({"preset": "rowan", "hair_detail": 140})
	_expect(rl_face.hair_detail == 100 and RLHeadAppearance.from_dict(rl_face.to_dict()).hair_detail == 100
		and RLHeadAppearance.from_preset("mira").hair_detail == RLHeadAppearance.DEFAULT_HAIR_DETAIL,
		"the RL face's detail level is 0..100, 50 unless set, and survives the dictionary form")


func _check_v3() -> void:
	for sex: String in ["female", "male"]:
		var base := Map.face({}, sex)
		var neutral := {}
		for control: String in Map.V3_CONTROLS:
			neutral[control] = 50
		for detail: String in Map.V3_DETAILS:
			neutral[detail] = 0
		_expect(Map.face(neutral, sex).to_dict() == base.to_dict(), "%s: neutral PC/3 fields change nothing" % sex)
		var derived := Map.controls({}, sex)
		var raised := Map.controls({"ear_size": 100, "eyelid": 0}, sex)
		var lid := clampf(float(derived.get("eyelid", 0.0)) - 1.0, -1.0, 1.0)
		_expect(float(raised.get("ear_size", 0.0)) > 0.99 and absf(float(raised.get("eyelid", 0.0)) - lid) < 1e-4,
			"%s: PC/3 control offsets add to the derived controls %s" % [sex, raised])
		var explicit := Map.face({"freckles": 51, "liner": 1, "brow_style": 13, "brow_thickness": 1,
			"lip_tint": 9, "stubble": 101}, sex)
		_expect(is_equal_approx(explicit.freckles, 0.5) and explicit.liner == 0.0 and explicit.brow_style == 3.0
			and explicit.brow_thickness == -1.0 and explicit.lip_tint == Map.lip_tint_color(9),
			"%s: explicit PC/3 details win over the defaults" % sex)
		_expect(is_equal_approx(explicit.stubble_amount(), 1.0 if sex == "male" else 0.0),
			"%s: explicit stubble only on a male head" % sex)
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(1, 0), "hair_module": 1}, "male") == "legacy:parted",
		"hair_module 1 forces the game hairstyle")
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(2, 0), "hair_module": 2}, "male") == "rowan_shag",
		"hair_module 2 draws rowan_shag on a male head")
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(2, 0), "hair_module": 2}, "female") == "legacy:long",
		"a module of the other sex falls back to the rule")
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(3, 0), "hair_module": 17}, "female") == "mira_bun",
		"an unknown module id is the rule")
	_expect(Map.hair({"hair": AppearanceVariants.pack_hair(0, 0), "hair_module": 3}, "female") == RLHeadAppearance.NONE,
		"Bald stays bald whatever the module")


func _check_inverse() -> void:
	for pair: Array in [["male", "Rowan"], ["female", "Mira"], ["male", "Tavi"]]:
		var appearance := PRESETS.appearance(pair[1])
		var face := Map.face(appearance, pair[0])
		var back := Map.to_portrait_fields(face, pair[0])
		var exact := true
		for field: String in Map.FACE_FIELDS:
			var x := face.control(Map.primary_control(field))
			if absf(x) >= 0.999:
				continue  # clamped: the inverse gives the clamp's edge
			exact = exact and absf(int(back[field]) - int(appearance[field])) <= 1
		_expect(exact, "%s's face fields round-trip through the inverse map %s" % [pair[1], back])
		_expect(int(back.facial_hair) == int(appearance.facial_hair), "%s facial hair round-trips" % pair[1])
		_expect(int(back.hair_style) == AppearanceVariants.hair_style(int(appearance.hair)),
			"%s hair style round-trips" % pair[1])
