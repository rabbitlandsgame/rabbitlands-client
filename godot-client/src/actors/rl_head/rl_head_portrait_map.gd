class_name RLHeadPortraitMap
extends RefCounted
## The RL head a Human's saved appearance asks for: develop's PortraitCustomization
## fields (PC/1 and PC/2) and palette bytes in, an RLHeadAppearance out. Pure;
## nothing here touches a node. ReplicatedActor3D draws the result at High.
##
## Face (owner decision D3, recentred offset-linear): each of the ten face
## fields drives its RL control by
##     x = clamp(g * (v - c) / 50, -1, 1)
## where c is the field's value in the body sex's own likeness preset
## (HumanPortraitPresets Rowan for male, Mira for female), so those presets
## reproduce the authored RL heads exactly, and g is the field's gain,
## calibrated near the centre against the Low/Medium face sculpt
## (data/actors/rl_head_wire_defaults.json, tests/rl_head_gain_probe.gd). A few
## fields also move a second control (`secondary`). The other RL controls have
## no field and stay at the authored head plus those couplings; a later PC/3
## field (`eyelid` .. `ear_size`, 50 neutral) adds g3 * (v - 50) / 50 on top.
##
## Grooming: facial_hair 0..5 is none, stubble, moustache, goatee, short beard,
## full beard by name; women draw no beard and no stubble at High (the saved
## value is kept; owner decision). Hair style (D5): male Parted is the
## rowan_shag module, female Buns the mira_bun module, every other style and
## sex the game's own fitted hairstyle (`legacy:<style>`, drawn by the actor
## with its High finish), Bald is none. hair_length / hair_volume drive an RL
## module's hl_ shapes centred on its own preset's values; the hair finish
## (hair_detail 0 Classic, 1 Tousled, 2 Swept) becomes the module's fine-detail
## level, centred the same way (`detail_level`).
##
## Colours: skin, eye and hair palette indices through calibrated RL-side
## tables, so a lit RL head matches what Low/Medium show for the same index;
## freckles, liner, brows and lip tint from per-sex defaults keyed by skin
## index. A missing or invalid field counts as its neutral value (50 for the
## sliders, 0 for facial_hair and hair_detail), as PortraitCustomization does.

const DATA_PATH := "res://data/actors/rl_head_wire_defaults.json"
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const SEX_PRESETS := {"female": "Mira", "male": "Rowan"}
const FACE_FIELDS: Array[String] = ["jaw", "cheekbones", "nose", "face_length", "eye_size",
	"eye_tilt", "eye_spacing", "nose_width", "lip_fullness", "brow_depth"]
## The face field -> RL control map, used when the data does not say.
const PRIMARY := {"jaw": "jaw_width", "cheekbones": "cheekbones", "nose": "nose_depth",
	"face_length": "chin_length", "eye_size": "eye_size", "eye_tilt": "eye_tilt",
	"eye_spacing": "eye_spacing", "nose_width": "nose_width", "lip_fullness": "lip_fullness",
	"brow_depth": "brow_ridge"}
## PC/3 (planned): one offset per RL control without a field, 50 neutral, and
## the detail fields, 0 = Auto (the derived value below).
const V3_CONTROLS: Array[String] = ["eyelid", "brow_height", "nose_length", "nose_bridge",
	"nose_tip", "mouth_width", "cupid_bow", "cheek_fullness", "chin_projection", "chin_width",
	"ear_size"]
const V3_DETAILS: Array[String] = ["brow_style", "brow_thickness", "freckles", "liner",
	"liner_wing", "stubble", "lip_tint", "hair_module"]
const V3_MAXIMA := {"brow_style": 13, "brow_thickness": 101, "freckles": 101, "liner": 101,
	"liner_wing": 101, "stubble": 101, "lip_tint": 12, "hair_module": 31}
## facial_hair -> RL beard, by name (the RL registry orders them differently).
const BEARDS: Array[String] = ["none", "stubble", "moustache", "goatee", "short_beard", "full_beard"]
## PC/3 hair_module ids: 0 the rule below, 1 the game's own hairstyle, 2 and up
## an RL module (append-only; an unknown id or one of the other sex is 0).
const HAIR_MODULES := {2: {"name": "rowan_shag", "sex": "male"}, 3: {"name": "mira_bun", "sex": "female"}}
## D5: the style slots an RL module draws, per body sex.
const HAIR_RULES := {"male": {1: "rowan_shag"}, "female": {3: "mira_bun"}}
## Each RL module's length and volume are centred on its own likeness preset.
const MODULE_PRESETS := {"rowan_shag": "Rowan", "mira_bun": "Mira"}
const BROW_FROM_HAIR := 0.65

static var _data: Dictionary = {}
static var _loaded := false


static func data() -> Dictionary:
	if not _loaded:
		_loaded = true
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH)) \
			if FileAccess.file_exists(DATA_PATH) else null
		_data = parsed if parsed is Dictionary else {}
	return _data


static func reload() -> void:
	_loaded = false
	_data = {}


## The RL head for `appearance` on a body of `sex` ("female" / "male").
static func face(appearance: Dictionary, sex: String) -> RLHeadAppearance:
	sex = "male" if sex == "male" else "female"
	var result := RLHeadAppearance.new()
	result.sex = sex
	result.preset = ""
	result.label = ""
	var values := controls(appearance, sex)
	for control: String in values:
		result.set_control(control, float(values[control]))
	var skin_index := palette_index(appearance, "skin", 10)
	result.skin = skin_color(skin_index, sex)
	result.eyes = eye_color(palette_index(appearance, "eyes", 12), sex)
	result.hair_color = hair_color(AppearanceVariants.hair_color_index(int(appearance.get("hair", 0))), sex)
	result.brow_color = result.hair_color * BROW_FROM_HAIR
	result.brow_color.a = 1.0
	var beard_table := _table("beard", sex)
	if not beard_table.is_empty():
		var hair_index := posmod(AppearanceVariants.hair_color_index(int(appearance.get("hair", 0))), 20)
		result.beard_color = _colour(beard_table[mini(hair_index, beard_table.size() - 1)], result.hair_color)
		result.beard_color_set = true
	var detail := details(appearance, sex)
	result.brow_style = float(detail["brow_style"])
	result.brow_thickness = float(detail["brow_thickness"])
	result.freckles = float(detail["freckles"])
	result.liner = float(detail["liner"])
	result.liner_wing = float(detail["liner_wing"])
	result.lip_tint = detail["lip_tint"] as Color
	result.hair = hair(appearance, sex)
	result.beard = beard(appearance, sex)
	result.stubble = float(detail["stubble"])
	var shapes := hair_shapes(appearance, result.hair)
	result.hair_length = float(shapes["length"])
	result.hair_volume = float(shapes["volume"])
	result.hair_detail = int(shapes["detail"])
	return result


# ---------------------------------------------------------------- fields

## A 0..100 slider (or another field up to `maximum`), PortraitCustomization's
## way: a missing or non-integer value is `fallback`, the rest clamped.
static func field(appearance: Dictionary, name: String, fallback: int = 50, maximum: int = 100) -> int:
	var value: Variant = appearance.get(name, fallback)
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(value)) \
			or floor(float(value)) != float(value):
		return fallback
	return clampi(int(value), 0, maximum)


static func palette_index(appearance: Dictionary, name: String, size: int) -> int:
	return posmod(field(appearance, name, 0, 1 << 30), size)


## The field's value in the body sex's likeness preset: the face as authored.
static func centre(field_name: String, sex: String) -> float:
	var shape := PRESETS.shape(str(SEX_PRESETS.get(sex, "Mira")))
	return clampf(float(shape.get(field_name, 50)), 0.0, 100.0)


## The field's gain for a body sex: a number, or one per sex.
static func gain(field_name: String, sex: String = "female") -> float:
	var primary: Dictionary = (data().get("controls", {}) as Dictionary).get("primary", {}) as Dictionary
	var value: Variant = (primary.get(field_name, {}) as Dictionary).get("gain", 1.0)
	if value is Dictionary:
		value = (value as Dictionary).get(sex, 1.0)
	return float(value)


static func primary_control(field_name: String) -> String:
	var primary: Dictionary = (data().get("controls", {}) as Dictionary).get("primary", {}) as Dictionary
	return str((primary.get(field_name, {}) as Dictionary).get("control", PRIMARY.get(field_name, "")))


## [{field, control, gain}] couplings of a field to a second control.
static func secondaries() -> Array:
	var listed: Variant = (data().get("controls", {}) as Dictionary).get("secondary")
	if listed is Array:
		return listed as Array
	return [{"field": "jaw", "control": "chin_width", "gain": 0.3},
		{"field": "nose", "control": "nose_bridge", "gain": 0.4},
		{"field": "face_length", "control": "nose_length", "gain": 0.5},
		{"field": "brow_depth", "control": "brow_height", "gain": -0.2}]


static func cap() -> float:
	return clampf(float((data().get("controls", {}) as Dictionary).get("cap", 1.0)), 0.0, 1.0)


## RL control -> value in [-1, 1], zeros left out.
static func controls(appearance: Dictionary, sex: String) -> Dictionary:
	var raw := {}
	var limit := cap()
	for field_name: String in FACE_FIELDS:
		var offset := (float(field(appearance, field_name)) - centre(field_name, sex)) / 50.0
		var control := primary_control(field_name)
		if not control.is_empty():
			raw[control] = float(raw.get(control, 0.0)) + clampf(gain(field_name, sex) * offset, -limit, limit)
	for coupling: Variant in secondaries():
		if coupling is not Dictionary:
			continue
		var entry := coupling as Dictionary
		var field_name := str(entry.get("field", ""))
		if not FACE_FIELDS.has(field_name):
			continue
		var control := str(entry.get("control", ""))
		var offset := (float(field(appearance, field_name)) - centre(field_name, sex)) / 50.0
		raw[control] = float(raw.get(control, 0.0)) + float(entry.get("gain", 0.0)) * offset
	# PC/3: an explicit offset on each control without a field (50 = none).
	var v3_gains: Dictionary = (data().get("controls", {}) as Dictionary).get("v3Gains", {}) as Dictionary
	for control: String in V3_CONTROLS:
		if appearance.has(control):
			var offset := (float(field(appearance, control)) - 50.0) / 50.0
			raw[control] = float(raw.get(control, 0.0)) + float(v3_gains.get(control, 1.0)) * offset
	var result := {}
	for control: Variant in raw:
		var value := clampf(float(raw[control]), -limit, limit)
		if not is_zero_approx(value):
			result[str(control)] = value
	return result


# ---------------------------------------------------------------- grooming

## The RL hairstyle: "none", an RL module name, or `legacy:<style>` for the
## game's own fitted hairstyle (drawn by the actor).
static func hair(appearance: Dictionary, sex: String) -> String:
	var style := AppearanceVariants.hair_style(int(field(appearance, "hair", 0, 1 << 30)))
	if style <= 0:
		return RLHeadAppearance.NONE
	var module := field(appearance, "hair_module", 0, int(V3_MAXIMA["hair_module"])) \
		if appearance.has("hair_module") else 0
	if module == 1:
		return legacy_name(style)
	if HAIR_MODULES.has(module) and str((HAIR_MODULES[module] as Dictionary)["sex"]) == sex:
		return str((HAIR_MODULES[module] as Dictionary)["name"])
	var rules: Dictionary = HAIR_RULES.get(sex, {}) as Dictionary
	if rules.has(style):
		return str(rules[style])
	return legacy_name(style)


## `legacy:<style>` for a hair style slot 1..9.
static func legacy_name(style: int) -> String:
	var names := RLHeadLibrary.LEGACY_HAIR_STYLES
	if style <= 0 or style > names.size():
		return RLHeadAppearance.NONE
	return RLHeadLibrary.LEGACY_PREFIX + names[style - 1]


## The hair style slot a `legacy:<style>` name stands for, 0 for none.
static func legacy_style(hair_name: String) -> int:
	if not hair_name.begins_with(RLHeadLibrary.LEGACY_PREFIX):
		return 0
	return RLHeadLibrary.LEGACY_HAIR_STYLES.find(hair_name.trim_prefix(RLHeadLibrary.LEGACY_PREFIX)) + 1


static func is_module(hair_name: String) -> bool:
	return hair_name != RLHeadAppearance.NONE and not hair_name.begins_with(RLHeadLibrary.LEGACY_PREFIX)


## Length, volume (-1..1, 0 at the module's preset) and the fine-detail level
## (0..100, RLHeadAppearance.DEFAULT_HAIR_DETAIL at the module's preset) for an
## RL module; the neutral values for the game's own hairstyles, which the
## actor grooms.
static func hair_shapes(appearance: Dictionary, hair_name: String) -> Dictionary:
	var result := {"length": 0.0, "volume": 0.0, "detail": RLHeadAppearance.DEFAULT_HAIR_DETAIL}
	if not is_module(hair_name):
		return result
	var preset := PRESETS.shape(str(MODULE_PRESETS.get(hair_name, "Rowan")))
	var hair_gain := float((data().get("hair", {}) as Dictionary).get("shapeGain", 1.0))
	for pair: Array in [["length", "hair_length"], ["volume", "hair_volume"]]:
		var offset := (float(field(appearance, pair[1])) - float(preset.get(pair[1], 50))) / 50.0
		result[pair[0]] = clampf(hair_gain * offset, -1.0, 1.0)
	result["detail"] = detail_level(field(appearance, "hair_detail", 0, 2),
		clampi(int(preset.get("hair_detail", 0)), 0, 2))
	return result


## The fine-detail level (0..100) for a saved hair finish on a module whose
## likeness preset has `preset_finish`:
##     clamp(50 + step * (rank[finish] - rank[preset_finish]), 0, 100)
## with the finishes ranked by how much loose hair they suggest (data
## `hair.detail.finishRank`, by finish 0 Classic, 1 Tousled, 2 Swept; default
## Swept 0 < Classic 1 < Tousled 2) and `hair.detail.step` (default 25). The
## preset's own finish is the authored look, as for length and volume.
static func detail_level(finish: int, preset_finish: int) -> int:
	var entry: Dictionary = (data().get("hair", {}) as Dictionary).get("detail", {}) as Dictionary
	var listed: Variant = entry.get("finishRank")
	var ranks: Array = listed as Array if listed is Array and (listed as Array).size() >= 3 else [1, 2, 0]
	var step := float(entry.get("step", 25.0))
	var difference := float(ranks[clampi(finish, 0, 2)]) - float(ranks[clampi(preset_finish, 0, 2)])
	return clampi(roundi(RLHeadAppearance.DEFAULT_HAIR_DETAIL + step * difference), 0, 100)


## The RL beard; none on a female head at High.
static func beard(appearance: Dictionary, sex: String) -> String:
	if sex != "male":
		return RLHeadAppearance.NONE
	return BEARDS[field(appearance, "facial_hair", 0, 5)]


# ---------------------------------------------------------------- colours

static func _colour(value: Variant, fallback: Color) -> Color:
	if value is Array and (value as Array).size() >= 3:
		var rgb: Array = value
		return Color(float(rgb[0]), float(rgb[1]), float(rgb[2]))
	return fallback


static func _table(category: String, sex: String) -> Array:
	var colours: Dictionary = data().get("colours", {}) as Dictionary
	var entry: Variant = colours.get(category)
	if entry is Dictionary:
		entry = (entry as Dictionary).get(sex, (entry as Dictionary).get("all"))
	return entry as Array if entry is Array else []


## The RL skin colour (sRGB) for skin index `index`: the calibrated table,
## else the body's own tone - the palette colour the body is recoloured to,
## or for index 0 (the authored tone, never recoloured) its calibrated
## reference.
static func skin_color(index: int, sex: String) -> Color:
	index = posmod(index, 10)
	var table := _table("skin", sex)
	if index < table.size():
		return _colour(table[index], Color.WHITE)
	if index == 0:
		var reference := RLHeadLibrary.body_skin_reference(sex)
		return _colour(reference, Color(0.814, 0.633, 0.532))
	return AppearanceVariants.skin_color(index)


## The RL hair colour (sRGB) for hair colour index 0..19.
static func hair_color(index: int, sex: String) -> Color:
	index = posmod(index, 20)
	var table := _table("hair", sex)
	if index < table.size():
		return _colour(table[index], Color.WHITE)
	return AppearanceVariants.hair_color(index)


## The RL eye colour (sRGB) for eye index 0..11: the calibrated table, else the
## palette through the Low/Medium Human iris treatment (face_appearance's
## natural_iris), which mutes the pigment a little towards its own grey.
static func eye_color(index: int, sex: String = "female") -> Color:
	index = posmod(index, 12)
	var table := _table("eyes", sex)
	if index < table.size():
		return _colour(table[index], Color.WHITE)
	return natural_iris(AppearanceVariants.eye_color(index))


static func natural_iris(tint: Color) -> Color:
	var value := tint.r * 0.2126 + tint.g * 0.7152 + tint.b * 0.0722
	return Color(lerpf(tint.r, value, 0.12), lerpf(tint.g, value, 0.12), lerpf(tint.b, value, 0.12))


## The lip palette entry for a lip tint wire value 1..12 (PC/3 spec 2.4).
static func lip_tint_color(wire: int) -> Color:
	var tints: Array = data().get("lipTints", []) as Array
	var fallback := [[0.76, 0.52, 0.52], [0.80, 0.44, 0.38], [0.70, 0.46, 0.42], [0.70, 0.44, 0.36],
		[0.62, 0.36, 0.33], [0.50, 0.31, 0.27], [0.41, 0.24, 0.22], [0.60, 0.40, 0.45],
		[0.56, 0.22, 0.30], [0.64, 0.28, 0.22], [0.40, 0.20, 0.28], [0.66, 0.58, 0.74]]
	if tints.size() < 12:
		tints = fallback
	return _colour(tints[clampi(wire, 1, 12) - 1], Color(0.75, 0.45, 0.42))


# ---------------------------------------------------------------- details

## Seed values (owner review) when the data file says nothing.
const FALLBACK_DEFAULTS := {
	"female": {"brow_style": 0.0, "brow_thickness": 0.2,
		"freckles": [0.30, 0.35, 0.25, 0.10, 0.0, 0.0, 0.10, 0.10, 0.10, 0.10],
		"liner": [0.30, 0.30, 0.30, 0.30, 0.40, 0.40, 0.30, 0.30, 0.30, 0.30],
		"liner_wing": 0.0, "stubble": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
		"lip_tint": [2, 1, 2, 5, 6, 7, 12, 8, 8, 8]},
	"male": {"brow_style": 1.0, "brow_thickness": 0.6,
		"freckles": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
		"liner": [0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15],
		"liner_wing": 0.0, "stubble": [0.0, 0.6, 0.3, 0.3, 0.3, 0.3],
		"lip_tint": [4, 3, 4, 4, 6, 7, 8, 8, 8, 8]},
}


static func defaults(sex: String) -> Dictionary:
	var listed: Variant = (data().get("defaults", {}) as Dictionary).get(sex)
	return listed as Dictionary if listed is Dictionary else FALLBACK_DEFAULTS[sex] as Dictionary


static func _indexed(value: Variant, index: int, fallback: float) -> float:
	if value is Array:
		var list := value as Array
		return float(list[clampi(index, 0, list.size() - 1)]) if not list.is_empty() else fallback
	return float(value) if value != null else fallback


## The painted details: brow style 0..3 and thickness -1..1, freckles, liner,
## liner wing and stubble 0..1, and the lip tint (Color). Derived per sex and
## skin (and facial_hair for stubble); a PC/3 field other than 0 (Auto) wins.
static func details(appearance: Dictionary, sex: String) -> Dictionary:
	var seeds := defaults(sex)
	var skin := palette_index(appearance, "skin", 10)
	var facial := field(appearance, "facial_hair", 0, 5)
	var result := {
		"brow_style": _indexed(seeds.get("brow_style"), 0, 2.0),
		"brow_thickness": _indexed(seeds.get("brow_thickness"), 0, 0.0),
		"freckles": _indexed(seeds.get("freckles"), skin, 0.0),
		"liner": _indexed(seeds.get("liner"), skin, 0.0),
		"liner_wing": _indexed(seeds.get("liner_wing"), skin, 0.0),
		"stubble": _indexed(seeds.get("stubble"), facial, 0.0),
		"lip_tint": lip_tint_color(int(_indexed(seeds.get("lip_tint"), skin, 2.0))),
	}
	var explicit := func(name: String) -> int:
		return field(appearance, name, 0, int(V3_MAXIMA[name])) if appearance.has(name) else 0
	if explicit.call("brow_style") > 0:
		result["brow_style"] = float(explicit.call("brow_style") - 1) / 4.0
	if explicit.call("brow_thickness") > 0:
		result["brow_thickness"] = float(explicit.call("brow_thickness") - 51) / 50.0
	for name: String in ["freckles", "liner", "liner_wing", "stubble"]:
		if explicit.call(name) > 0:
			result[name] = float(explicit.call(name) - 1) / 100.0
	if explicit.call("lip_tint") > 0:
		result["lip_tint"] = lip_tint_color(explicit.call("lip_tint"))
	if sex != "male":
		# No stubble on a female head at High; the saved value is kept.
		result["stubble"] = 0.0
	return result


# ---------------------------------------------------------------- inverse

## Develop fields for an RL face (the lab, preset freezing, tests): the ten
## face fields from the primary controls (secondary couplings are what they
## derive), facial_hair and the hair style from the beard and hairstyle.
## Colours are left out: palette indices are chosen, not derived.
static func to_portrait_fields(rl_face: RLHeadAppearance, sex: String) -> Dictionary:
	var result := {}
	for field_name: String in FACE_FIELDS:
		var g := gain(field_name, sex)
		var x := rl_face.control(primary_control(field_name))
		var value := centre(field_name, sex) + 50.0 * x / (g if absf(g) > 1e-4 else 1.0)
		result[field_name] = clampi(roundi(value), 0, 100)
	result["facial_hair"] = maxi(0, BEARDS.find(rl_face.beard))
	if rl_face.hair == RLHeadAppearance.NONE:
		result["hair_style"] = 0
	elif is_module(rl_face.hair):
		for style: Variant in (HAIR_RULES.get(sex, {}) as Dictionary):
			if str((HAIR_RULES[sex] as Dictionary)[style]) == rl_face.hair:
				result["hair_style"] = int(style)
	else:
		result["hair_style"] = legacy_style(rl_face.hair)
	return result
