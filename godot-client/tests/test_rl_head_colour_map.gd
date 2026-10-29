extends SceneTree
## RLHeadPortraitMap with PC/3 colour fields and the hair finish slider (colour
## model spec revision 3, 4.3 and 4.7; R1 and R3 at RL High): the palette path -
## neutral, typed frozen, guarded - is the table path exactly; custom skin,
## eyes, hair and beard colours change the head through the calibrated data
## (skinTone, eyeLut, hairLut, beardLut: exact at the skin stops and the
## palette irises, within 0.02 of the hair table near palette colours, R6),
## whose source files are unchanged; the RL skin moves smoothly along the
## slider and the undertone (R6); a custom skin tone interpolates freckles,
## liner and lip tint; hair_finish sets the module's detail level. Pure.
const Map = preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const Colours = preload("res://src/actors/appearance_colours.gd")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
const Finish = preload("res://src/actors/hair_finish.gd")
var failures := 0
var checks := 0

func _init() -> void:
	run.call_deferred()

func expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(label)

func run() -> void:
	check_palette_path()
	check_custom_colours()
	check_calibration_data()
	check_skin_continuity()
	check_details()
	check_finish()
	print("RL head colour map: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _dict(appearance: Dictionary, sex: String) -> Dictionary:
	return Map.face(appearance, sex).to_dict()

# R1, R3: every palette look, with neutral, typed frozen or guarded colour
# fields, maps to exactly the same RL head.
func check_palette_path() -> void:
	for sex: String in ["female", "male"]:
		for skin: int in 10:
			for colour: int in 20:
				var eyes := (skin + colour) % 12
				var hair := AppearanceVariants.pack_hair(1 + colour % 9, colour)
				var base := {"skin": skin, "eyes": eyes, "hair": hair, "facial_hair": colour % 6, "hair_detail": colour % 3}
				var want := _dict(base, sex)
				var neutral := base.merged(_neutral_colours(), true)
				expect(_dict(neutral, sex) == want, "%s skin %d colour %d: neutral PC/3 is the table path" % [sex, skin, colour])
				var frozen := Colours.frozen_hair(colour, sex)
				var eye: Vector3i = Colours.EYE_FROZEN[eyes]
				var typed := base.merged({"hair_hue": frozen.x, "hair_sat": frozen.y, "hair_light": frozen.z,
					"eye_hue": eye.x, "eye_sat": eye.y, "eye_light": eye.z,
					"skin_tone": Colours.skin_position(skin), "hair_finish": [51, 76, 26][colour % 3]}, true)
				expect(_dict(typed, sex) == want, "%s skin %d colour %d: typed frozen values are the table path" % [sex, skin, colour])
				var other := Colours.frozen_hair((colour + 7) % 20, sex)
				var guarded := base.merged({"hair_hue": other.x, "hair_sat": other.y, "hair_light": other.z, "skin_undertone": 0 if skin > 5 else 0}, true)
				expect(_dict(guarded, sex) == want, "%s skin %d colour %d: a guarded hair colour is the table path" % [sex, skin, colour])
	for preset: String in ["Rowan", "Mira", "Tavi"]:
		var sex := "female" if preset == "Mira" else "male"
		var look := PRESETS.appearance(preset)
		expect(_dict(look.merged(_neutral_colours(), true), sex) == _dict(look, sex), "%s: neutral PC/3 unchanged" % preset)

func _neutral_colours() -> Dictionary:
	var result := {}
	for field: String in PortraitCustomization.V3_COLOURS:
		result[field] = 0
	result["hair_finish"] = 0
	return result

func check_custom_colours() -> void:
	for sex: String in ["female", "male"]:
		# Skin: an undertone on a stop changes the head's skin; at a stop with no
		# undertone the custom model meets the table (exact at the stops).
		var base := {"skin": 2, "eyes": 1, "hair": AppearanceVariants.pack_hair(1, 2)}
		var palette := Map.face(base, sex)
		var shifted := Map.face(base.merged({"skin_undertone": 40}, true), sex)
		expect(not shifted.skin.is_equal_approx(palette.skin), "%s: an undertone changes the RL skin" % sex)
		for index: int in 6:
			var resolved := {"position": float(Colours.skin_position(index)), "colour": Colours.skin_stop_colour(index, sex)}
			var custom := Map.custom_skin_color(resolved, sex)
			var table := Map.skin_color(index, sex)
			expect(absf(custom.r - table.r) < 1e-4 and absf(custom.g - table.g) < 1e-4 and absf(custom.b - table.b) < 1e-4,
				"%s: the calibrated skin model is exact at stop %d (%s vs %s)" % [sex, index, custom, table])
		# Eyes: exact at every palette pigment.
		for index: int in 12:
			var custom := Map.custom_eye_color(AppearanceVariants.eye_color(index), sex)
			var table := Map.eye_color(index, sex)
			expect(absf(custom.r - table.r) < 1e-4 and absf(custom.g - table.g) < 1e-4 and absf(custom.b - table.b) < 1e-4,
				"%s: the eye LUT is exact at eye %d" % [sex, index])
		# Hair (R6): the LUT near the palette colours matches the hair table
		# (each palette colour's apparent value on the module's authored level).
		var module: String = "rowan_shag" if sex == "male" else "mira_bun"
		var worst := 0.0
		for index: int in 20:
			var resolved := {"apparent": Colours.palette_apparent(index, sex), "dye": AppearanceVariants.hair_color(index)}
			var custom := Map.custom_table_color("hair", resolved, sex, module, 50)
			var table := Map.hair_color(index, sex)
			worst = maxf(worst, maxf(absf(custom.r - table.r), maxf(absf(custom.g - table.g), absf(custom.b - table.b))))
		expect(worst <= 0.02, "%s: the hair LUT meets the table within 0.02 at the palette colours (%.4f)" % [sex, worst])
		print("RL hair LUT against the table at the palette colours, %s: %.4f sRGB" % [sex, worst])
		var wire := Vector3i(40, 60, 30)
		var hair_index := Colours.nearest_hair_index(Colours.triple_colour(wire), sex)
		var look := {"skin": 1, "eyes": 0, "hair": AppearanceVariants.pack_hair(1, hair_index), "hair_hue": wire.x,
			"hair_sat": wire.y, "hair_light": wire.z, "facial_hair": 5}
		var face := Map.face(look, sex)
		var plain := Map.face(look.merged({"hair_hue": 0, "hair_sat": 0, "hair_light": 0}, true), sex)
		expect(not face.hair_color.is_equal_approx(plain.hair_color), "%s: a custom hair colour changes the RL hair" % sex)
		expect(face.brow_color.is_equal_approx(Color(face.hair_color.r * Map.BROW_FROM_HAIR, face.hair_color.g * Map.BROW_FROM_HAIR,
			face.hair_color.b * Map.BROW_FROM_HAIR)), "%s: RL brows stay the hair x 0.65" % sex)
		if sex == "male":
			expect(face.beard_color_set and not face.beard_color.is_equal_approx(plain.beard_color), "a custom colour changes the RL beard")
		var eye_wire := Vector3i(110, 80, 55)
		var eye_index := Colours.nearest_eye_index(Colours.triple_colour(eye_wire))
		var eyes := Map.face({"eyes": eye_index, "eye_hue": eye_wire.x, "eye_sat": eye_wire.y, "eye_light": eye_wire.z}, sex)
		expect(not eyes.eyes.is_equal_approx(Map.face({"eyes": eye_index}, sex).eyes), "%s: a custom iris changes the RL eyes" % sex)

# The calibrated data is present and its source files are unchanged.
func check_calibration_data() -> void:
	for name: String in ["skinTone", "eyeLut", "hairLut", "beardLut"]:
		expect(not Map.calibration(name).is_empty(), "rl_head_wire_defaults.json has colours.%s" % name)
	var sources: Dictionary = Map.calibration("customSources")
	expect(sources.size() >= 10, "the calibration records its source files (%d)" % sources.size())
	for path: String in sources:
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		context.update(FileAccess.get_file_as_bytes(path))
		expect(context.finish().hex_encode() == str(sources[path]),
			"%s is unchanged since the RL colour calibration (re-run rl_head_colour_calibration --part=skin/eyes and hair_apparent_calibration)" % path)
	for sex: String in ["female", "male"]:
		var knots := Map.calibration("skinTone")
		expect((knots[sex] as Array).size() == (knots.positions as Array).size() * (knots.undertones as Array).size(),
			"%s: a skin knot per position and undertone" % sex)
		expect(((Map.calibration("eyeLut")[sex] as Dictionary).table as Array).size() == 343, "%s: a 7^3 eye LUT" % sex)
	for level: int in [0, 17, 33, 50, 100]:
		expect(not Map.hair_lut("hair", "male", "rowan_shag", level).is_empty(), "rowan_shag hair LUT at level %d" % level)
	for level: int in [0, 50, 67, 83, 100]:
		expect(not Map.hair_lut("hair", "female", "mira_bun", level).is_empty(), "mira_bun hair LUT at level %d" % level)
	for beard: String in ["moustache", "goatee", "short_beard", "full_beard"]:
		expect(not Map.hair_lut("beard", "male", beard, 50).is_empty(), "%s beard LUT" % beard)
	# A legacy-style head (brows only) uses the sex's module.
	expect(not Map.hair_lut("hair", "female", "legacy:long", 50).is_empty(), "a legacy-style head uses the module's LUT")


# R6: adjacent slider and undertone steps move the RL skin by at most 0.006
# (OKLab, on the RL colour), the Soft tan seam at 23 reported.
func check_skin_continuity() -> void:
	for sex: String in ["female", "male"]:
		var config := Map.human_config(sex)
		var worst := 0.0
		var seam := 0.0
		for wire: int in [0, 21, 51, 81, 121, 151, 181, 201]:
			var previous := Color()
			for p: int in range(1, 202):
				var look := {"skin": Colours.nearest_skin_index(p), "skin_tone": p, "skin_undertone": wire}
				var resolved := Colours.skin(look, config)
				var colour := Map.custom_skin_color(resolved, sex) if resolved.custom else Map.skin_color(int(resolved.index), sex)
				if p > 1:
					var step := Colours.delta_e(previous, colour)
					if p == 23 or p == 24:
						seam = maxf(seam, step)
					else:
						worst = maxf(worst, step)
				previous = colour
		for p: int in [5, 23, 60, 120, 180]:
			var previous := Color()
			for wire: int in range(1, 202):
				var look := {"skin": Colours.nearest_skin_index(p), "skin_tone": p, "skin_undertone": wire}
				var resolved := Colours.skin(look, config)
				var colour := Map.custom_skin_color(resolved, sex) if resolved.custom else Map.skin_color(int(resolved.index), sex)
				if wire > 1:
					worst = maxf(worst, Colours.delta_e(previous, colour))
				previous = colour
		expect(worst <= 0.006, "%s: adjacent RL skin steps move at most 0.006 (%.4f)" % [sex, worst])
		print("RL skin continuity %s: worst step %.4f, Soft tan seam %.4f" % [sex, worst, seam])


# A custom skin tone interpolates the derived freckles, liner and lip tint
# between the neighbouring stops by position; the undertone leaves them.
func check_details() -> void:
	for sex: String in ["female", "male"]:
		var seeds := Map.defaults(sex)
		# Soft tan saved as its stop on golden tan's byte is the RL head's skin 0.
		var authored_face := Map.face({"skin": 0}, sex)
		var stop_face := Map.face({"skin": 2, "skin_tone": 23}, sex)
		expect(str(Map.details({"skin": 0}, sex)) == str(Map.details({"skin": 2, "skin_tone": 23}, sex))
			and authored_face.skin == stop_face.skin and authored_face.freckles == stop_face.freckles
			and authored_face.lip_tint == stop_face.lip_tint, "%s: the Soft tan stop draws the RL head's skin 0" % sex)
		var between := Map.details({"skin": 2, "skin_tone": 33}, sex)
		var u := (33.0 - 23.0) / 20.0
		var want := lerpf(float(seeds.freckles[0]), float(seeds.freckles[2]), u)
		expect(is_equal_approx(float(between.freckles), want), "%s: freckles between Soft tan and Golden tan (%.3f)" % [sex, between.freckles])
		var stop := Map.details({"skin": 3, "skin_undertone": 180}, sex)
		var palette := Map.details({"skin": 3}, sex)
		expect(is_equal_approx(float(stop.freckles), float(palette.freckles)) and is_equal_approx(float(stop.liner), float(palette.liner))
			and (stop.lip_tint as Color).is_equal_approx(palette.lip_tint), "%s: the undertone leaves freckles, liner and lip tint" % sex)

func check_finish() -> void:
	for pair: Array in [["male", "rowan_shag", AppearanceVariants.pack_hair(1, 2)], ["female", "mira_bun", AppearanceVariants.pack_hair(3, 4)]]:
		for wire: int in [0, 1, 11, 26, 37, 51, 64, 76, 90, 101]:
			for detail: int in 3:
				var look := {"hair": pair[2], "hair_detail": detail, "hair_finish": wire}
				var finish := Finish.resolve(look)
				var level := Map.face(look, pair[0]).hair_detail
				expect(level == Map.detail_level(float(finish.s), pair[1]),
					"%s finish %d / %d -> level %d" % [pair[1], wire, detail, level])
		expect(Map.face({"hair": pair[2], "hair_detail": 1, "hair_finish": 101}, pair[0]).hair_detail == 100,
			"%s: the messiest slider position is level 100" % pair[1])
		expect(Map.face({"hair": pair[2], "hair_detail": 2, "hair_finish": 1}, pair[0]).hair_detail == 0,
			"%s: the sleekest slider position is level 0" % pair[1])
