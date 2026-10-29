class_name AppearanceColours
extends RefCounted
## The continuous colour model (colour model spec revision 3, sections 2 and
## 4): a Human's PC/3 colour fields - skin tone slider and undertone, OKHSL
## hair, eye and garment triples - resolved against the palette bytes into the
## colours every quality draws. Pure; nothing here touches a node.
##
## Neutral is develop's palette path, value for value: a non-Human, an all-0
## colour group, a typed value equal to the stored palette entry's frozen
## value (Rule C) and a custom value whose nearest palette entry is not the
## stored legacy byte (the guard: an old client's edit or a rollback) all give
## exactly develop's palette colours, so old saves, NPCs and older peers draw
## byte for byte as on develop. Only custom values meet the limits.
##
## Hair is an apparent colour - what the hair looks like, on the skin
## swatches' scale - and each draw path gets the dye that shows it, from the
## measured response of that path (data/actors/hair_apparent.json, written by
## tests/integration/hair_apparent_calibration.gd and
## tools/colour_calibration/fit_hair.py; spec 4.4): per style, finish position and
## sex, a linear gain and floor for the Low/Medium hairstyles (P1-P3) and beard
## shells (B1, B2), and the classic High hair finish's pigment response (P4).
## The reference path R is P1 on the sex's module slot style (male Parted,
## female Buns). A path the file does not list falls back to R's frozen linear
## response (Appendix C), the interim model before calibration.

const HAIR_FINISH := preload("res://src/actors/hair_finish.gd")
const D_MAX := 1.6
const HUE_STEPS := 240
## Skin tone slider: the six natural palette entries in OKLab lightness order
## at their frozen wire positions (cumulative OKLab arc length, spec 2.1).
const SKIN_STOP_INDEX: Array[int] = [1, 0, 2, 3, 4, 5]
const SKIN_STOP_POSITION: Array[int] = [1, 23, 43, 95, 156, 201]
## Index 0's colour is the body's mean authored skin (never recoloured), per sex.
const SKIN_REFERENCE := {"female": Color(0.8138729394650926, 0.6331850101745203, 0.5323137669781451),
	"male": Color(0.8267734339554071, 0.6364139581297991, 0.5191423802593961)}
## Undertone anchors o(t) in units of the path chroma, added to OKLab (a, b);
## piecewise linear in t (Appendix D): Pink, Rosy, Neutral, Golden, Olive.
const UNDERTONE_T: Array[float] = [-1.0, -0.5, 0.0, 0.5, 1.0]
const UNDERTONE_OFFSET: Array[Vector2] = [Vector2(0.550, 0.150), Vector2(0.384, 0.331),
	Vector2.ZERO, Vector2(-0.100, 0.280), Vector2(-0.450, 0.120)]
const UNDERTONE_HUE_MIN := 30.0
const UNDERTONE_HUE_MAX := 95.0
const UNDERTONE_CHROMA_MAX := 0.11
## Measured Medium response on the neutral stage (Appendix C): the stage's skin
## gain g_ref and the reference hair path R's gain K, linear light.
const SKIN_GAIN := {"female": Vector3(1.3404, 1.3275, 1.3383), "male": Vector3(1.1800, 1.1590, 1.1634)}
const HAIR_GAIN_R := {"female": Vector3(0.3656, 0.3613, 0.3666), "male": Vector3(0.2961, 0.2935, 0.2998)}
## Frozen wire triples of the palette entries (Rule B/C, Appendix A).
const HAIR_FROZEN := {
	"female": [Vector3i(33, 16, 5), Vector3i(29, 71, 9), Vector3i(36, 79, 19), Vector3i(56, 71, 41),
		Vector3i(22, 96, 24), Vector3i(174, 11, 40), Vector3i(71, 5, 55), Vector3i(175, 69, 21),
		Vector3i(109, 77, 27), Vector3i(208, 67, 22), Vector3i(234, 62, 29), Vector3i(140, 90, 30),
		Vector3i(46, 52, 28), Vector3i(192, 6, 19), Vector3i(36, 78, 35), Vector3i(25, 74, 13),
		Vector3i(234, 20, 51), Vector3i(110, 96, 38), Vector3i(70, 65, 51), Vector3i(179, 63, 7)],
	"male": [Vector3i(32, 16, 5), Vector3i(29, 71, 8), Vector3i(36, 79, 18), Vector3i(57, 71, 39),
		Vector3i(22, 96, 23), Vector3i(174, 11, 39), Vector3i(76, 5, 54), Vector3i(175, 70, 20),
		Vector3i(109, 77, 26), Vector3i(208, 67, 21), Vector3i(233, 62, 28), Vector3i(141, 90, 29),
		Vector3i(47, 52, 27), Vector3i(190, 6, 18), Vector3i(36, 77, 34), Vector3i(25, 73, 12),
		Vector3i(232, 19, 49), Vector3i(110, 96, 36), Vector3i(71, 64, 49), Vector3i(179, 63, 6)]}
const EYE_FROZEN: Array[Vector3i] = [Vector3i(168, 71, 58), Vector3i(104, 87, 63), Vector3i(36, 67, 43),
	Vector3i(62, 82, 73), Vector3i(203, 69, 46), Vector3i(133, 85, 71), Vector3i(19, 90, 45),
	Vector3i(192, 12, 80), Vector3i(167, 32, 22), Vector3i(36, 90, 65), Vector3i(88, 82, 74),
	Vector3i(231, 72, 59)]
const DYE_FROZEN_OWN := {"shirt": [Vector3i(143, 74, 49), Vector3i(142, 52, 58), Vector3i(143, 71, 39)],
	"pants": [Vector3i(171, 29, 24), Vector3i(171, 17, 39), Vector3i(171, 27, 19)],
	"boots": [Vector3i(38, 37, 27), Vector3i(39, 21, 42), Vector3i(38, 35, 21)]}
const DYE_FROZEN_SHARED: Array[Vector3i] = [Vector3i(61, 70, 79), Vector3i(19, 84, 37), Vector3i(99, 74, 36),
	Vector3i(180, 56, 25), Vector3i(59, 76, 68), Vector3i(215, 59, 31), Vector3i(37, 71, 44),
	Vector3i(59, 26, 87), Vector3i(192, 6, 24)]
const PARTS := {"shirt": AppearanceVariants.PART_SHIRT, "pants": AppearanceVariants.PART_PANTS,
	"boots": AppearanceVariants.PART_BOOTS}
## Render limits for custom values (4.6).
const EYE_LIGHT_MIN := 0.20
const EYE_LIGHT_MAX := 0.80
const EYE_SAT_MAX := 0.92
const GARMENT_LIGHT_MIN := 0.15
const GARMENT_LIGHT_MAX := 0.92
const GARMENT_CONTRAST := 0.08
const TIE := 1e-6
const HAIR_TABLES_PATH := "res://data/actors/hair_apparent.json"
## The reference path R's hairstyle slot per sex (male Parted, female Buns).
const REFERENCE_STYLE := {"male": 1, "female": 3}
const LUMA := Vector3(0.2126, 0.7152, 0.0722)
## Bisection steps per channel and Gauss-Seidel sweeps of the measured-model
## inverse (deterministic; converges far below 1e-4 for these monotone models).
const SOLVE_STEPS := 32
const SOLVE_SWEEPS := 6

static var _hair_tables: Dictionary = {}
static var _hair_shapes: Dictionary = {}
## "<sex>/<path>/<style>" -> the measured finish positions, ascending.
static var _hair_positions: Dictionary = {}
static var _hair_tables_loaded := false


# ------------------------------------------------------------ colour spaces

static func to_linear(c: Color) -> Vector3:
	return Vector3(_lin(c.r), _lin(c.g), _lin(c.b))

static func to_srgb(v: Vector3) -> Color:
	return Color(_enc(v.x), _enc(v.y), _enc(v.z))

static func _lin(c: float) -> float:
	return c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)

static func _enc(c: float) -> float:
	if c <= 0.0031308:
		return 12.92 * c
	return 1.055 * pow(c, 1.0 / 2.4) - 0.055

static func _cbrt(x: float) -> float:
	return signf(x) * pow(absf(x), 1.0 / 3.0)

static func linear_to_oklab(v: Vector3) -> Vector3:
	var l := _cbrt(0.4122214708 * v.x + 0.5363325363 * v.y + 0.0514459929 * v.z)
	var m := _cbrt(0.2119034982 * v.x + 0.6806995451 * v.y + 0.1073969566 * v.z)
	var s := _cbrt(0.0883024619 * v.x + 0.2817188376 * v.y + 0.6299787005 * v.z)
	return Vector3(0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
		1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
		0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)

static func oklab_to_linear(lab: Vector3) -> Vector3:
	var l := pow(lab.x + 0.3963377774 * lab.y + 0.2158037573 * lab.z, 3.0)
	var m := pow(lab.x - 0.1055613458 * lab.y - 0.0638541728 * lab.z, 3.0)
	var s := pow(lab.x - 0.0894841775 * lab.y - 1.2914855480 * lab.z, 3.0)
	return Vector3(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
		-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
		-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)

static func oklab(c: Color) -> Vector3:
	return linear_to_oklab(to_linear(c))

static func from_oklab(lab: Vector3) -> Color:
	return to_srgb(oklab_to_linear(lab))

static func delta_e(a: Color, b: Color) -> float:
	return oklab(a).distance_to(oklab(b))

## The OKHSL colour of a wire triple (hue 1..240, saturation and lightness 1..101).
static func triple_colour(triple: Vector3i) -> Color:
	return Color.from_ok_hsl(float(triple.x - 1) / HUE_STEPS, float(triple.y - 1) / 100.0,
		float(triple.z - 1) / 100.0)

## The wire triple nearest to a colour: OKHSL quantised (hue 240 steps, the
## rest 100), each byte offset by one so 0 stays "palette".
static func quantise(colour: Color) -> Vector3i:
	var hue := posmod(roundi(colour.ok_hsl_h * HUE_STEPS), HUE_STEPS) + 1
	return Vector3i(hue, clampi(roundi(colour.ok_hsl_s * 100.0), 0, 100) + 1,
		clampi(roundi(colour.ok_hsl_l * 100.0), 0, 100) + 1)

## A material cache key for a dye: Color.to_html() while every channel is in
## 0..1, so palette colours keep develop's keys; a custom dye above 1 (up to
## D_MAX) adds its exact channels, which to_html clamps to ff - two light
## dyes would otherwise share one cached material.
static func colour_key(colour: Color) -> String:
	if colour.r <= 1.0 and colour.g <= 1.0 and colour.b <= 1.0:
		return colour.to_html()
	return "%s+%.5f,%.5f,%.5f" % [colour.to_html(), colour.r, colour.g, colour.b]


# --------------------------------------------------------------- fields

static func is_human(model_config: Dictionary) -> bool:
	return str(model_config.get("culture", "")) == "luminous" \
		and str(model_config.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func body_sex(model_config: Dictionary) -> String:
	return "male" if str(model_config.get("gender", "")) == "male" else "female"

static func _field(appearance: Dictionary, name: String, maximum: int) -> int:
	var value: Variant = appearance.get(name, 0)
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(value)) \
			or floor(float(value)) != float(value):
		return 0
	return clampi(int(value), 0, maximum)

## A colour group's triple, or Vector3i.ZERO for the palette (Rule A).
static func triple(appearance: Dictionary, group: String) -> Vector3i:
	var names: Array = PortraitCustomization.COLOUR_TRIPLES[group]
	var value := Vector3i(_field(appearance, names[0], HUE_STEPS), _field(appearance, names[1], 101),
		_field(appearance, names[2], 101))
	return value if value.x >= 1 and value.y >= 1 and value.z >= 1 else Vector3i.ZERO


# --------------------------------------------------------------- skin

## The skin palette entry at a slider stop's colour (index 0: the reference).
static func skin_stop_colour(index: int, sex: String, model_config: Dictionary = {}) -> Color:
	if index == 0:
		return skin_reference(sex, model_config)
	return AppearanceVariants.skin_color(index)

static func skin_reference(sex: String, model_config: Dictionary = {}) -> Color:
	var references: Array = ((model_config.get("skinPalette", {}) as Dictionary).get("references", {})
		as Dictionary).get("body", []) as Array
	if not references.is_empty() and references[0] is Array and (references[0] as Array).size() >= 3:
		var rgb: Array = references[0]
		return Color(float(rgb[0]), float(rgb[1]), float(rgb[2]))
	return SKIN_REFERENCE.get(sex, SKIN_REFERENCE["female"])

## The slider stop (0..5 along the slider) whose position is nearest to p;
## ties go to the lower position (spec 2.7).
static func nearest_skin_stop(position: float) -> int:
	var best := 0
	for stop: int in range(1, SKIN_STOP_POSITION.size()):
		if absf(position - SKIN_STOP_POSITION[stop]) < absf(position - SKIN_STOP_POSITION[best]) - TIE:
			best = stop
	return best

## The palette skin index older recipients get for slider position p:
## 1-12 -> 1, 13-33 -> 0, 34-69 -> 2, 70-125 -> 3, 126-178 -> 4, 179-201 -> 5.
static func nearest_skin_index(position: float) -> int:
	return SKIN_STOP_INDEX[nearest_skin_stop(position)]

## The slider position of a natural skin index 0..5, else 0.
static func skin_position(index: int) -> int:
	var stop := SKIN_STOP_INDEX.find(index)
	return SKIN_STOP_POSITION[stop] if stop >= 0 else 0

## OKLab colour of the slider path at position p (1..201).
static func skin_path(position: float, sex: String, model_config: Dictionary = {}) -> Vector3:
	position = clampf(position, 1.0, 201.0)
	for stop: int in range(SKIN_STOP_POSITION.size() - 1):
		if position <= SKIN_STOP_POSITION[stop + 1]:
			var u := (position - SKIN_STOP_POSITION[stop]) / float(SKIN_STOP_POSITION[stop + 1] - SKIN_STOP_POSITION[stop])
			return oklab(skin_stop_colour(SKIN_STOP_INDEX[stop], sex, model_config)).lerp(
				oklab(skin_stop_colour(SKIN_STOP_INDEX[stop + 1], sex, model_config)), u)
	return oklab(skin_stop_colour(SKIN_STOP_INDEX[-1], sex, model_config))

## o(t), the undertone offset in units of the path chroma.
static func undertone_offset(t: float) -> Vector2:
	t = clampf(t, -1.0, 1.0)
	for anchor: int in range(UNDERTONE_T.size() - 1):
		if t <= UNDERTONE_T[anchor + 1]:
			var u := (t - UNDERTONE_T[anchor]) / (UNDERTONE_T[anchor + 1] - UNDERTONE_T[anchor])
			return UNDERTONE_OFFSET[anchor].lerp(UNDERTONE_OFFSET[anchor + 1], u)
	return UNDERTONE_OFFSET[-1]

## The wire undertone (0 or 101 neutral; 1..201) as t in [-1, 1].
static func undertone_t(wire: int) -> float:
	return 0.0 if wire <= 0 or wire == 101 else float(clampi(wire, 1, 201) - 101) / 100.0

static func _in_gamut(lab: Vector3) -> bool:
	var rgb := oklab_to_linear(lab)
	return rgb.x >= -1e-6 and rgb.y >= -1e-6 and rgb.z >= -1e-6 \
		and rgb.x <= 1.000001 and rgb.y <= 1.000001 and rgb.z <= 1.000001

## The final OKLab skin at slider position p with undertone t, and whether the
## limits engaged: lightness is never changed; the hue is clamped to 30-95
## degrees, the chroma capped at 0.11, then reduced by 2% steps into sRGB.
static func skin_lab(position: float, t: float, sex: String, model_config: Dictionary = {}) -> Dictionary:
	var lab := skin_path(position, sex, model_config)
	if is_zero_approx(t):
		return {"lab": lab, "limited": false}
	var chroma := Vector2(lab.y, lab.z).length()
	var shifted := Vector2(lab.y, lab.z) + undertone_offset(t) * chroma
	var hue := rad_to_deg(atan2(shifted.y, shifted.x))
	var limited := false
	var held := clampf(hue, UNDERTONE_HUE_MIN, UNDERTONE_HUE_MAX)
	if held != hue:
		limited = true
	var amount := shifted.length()
	if amount > UNDERTONE_CHROMA_MAX:
		amount = UNDERTONE_CHROMA_MAX
		limited = true
	var result := Vector3(lab.x, amount * cos(deg_to_rad(held)), amount * sin(deg_to_rad(held)))
	for _step: int in 60:
		if _in_gamut(result):
			break
		result = Vector3(result.x, result.y * 0.98, result.z * 0.98)
		limited = true
	return {"lab": result, "limited": limited}

## The skin to draw: {"index", "custom", "colour" (sRGB; the palette swatch on
## the palette path), "position", "undertone" (t), "limited"}.
static func skin(appearance: Dictionary, model_config: Dictionary) -> Dictionary:
	var index := int(appearance.get("skin", 0)) if typeof(appearance.get("skin", 0)) in [TYPE_INT, TYPE_FLOAT] else 0
	var result := {"index": index, "custom": false, "colour": AppearanceVariants.skin_color(index),
		"position": float(skin_position(index)), "undertone": 0.0, "limited": false}
	if not is_human(model_config) or index < 0 or index > 5:
		return result
	var tone := _field(appearance, "skin_tone", 201)
	var t := undertone_t(_field(appearance, "skin_undertone", 201))
	var position := tone if tone >= 1 else skin_position(index)
	if tone >= 1 and nearest_skin_index(tone) != index:
		return result
	if position == skin_position(index) and is_zero_approx(t):
		return result
	var sex := body_sex(model_config)
	var final := skin_lab(position, t, sex, model_config)
	result.merge({"custom": true, "colour": from_oklab(final.lab), "position": float(position),
		"undertone": t, "limited": final.limited}, true)
	return result

## The skin colour an appearance shows (sRGB): the custom colour, else the
## palette entry's (index 0: the authored reference). For contrast checks.
static func skin_shown(appearance: Dictionary, model_config: Dictionary) -> Color:
	var resolved := skin(appearance, model_config)
	if resolved.custom:
		return resolved.colour
	var index := int(resolved.index)
	return skin_reference(body_sex(model_config), model_config) if posmod(index, 10) == 0 \
		else AppearanceVariants.skin_color(index)


# --------------------------------------------------------------- hair

## K/g_ref on R: apparent = ratio * dye, linear light.
static func hair_ratio(sex: String) -> Vector3:
	return (HAIR_GAIN_R.get(sex, HAIR_GAIN_R["female"]) as Vector3) / (SKIN_GAIN.get(sex, SKIN_GAIN["female"]) as Vector3)

## A palette hair colour's apparent colour on R (sRGB).
static func palette_apparent(index: int, sex: String) -> Color:
	return to_srgb(hair_ratio(sex) * to_linear(AppearanceVariants.hair_color(posmod(index, 20))))

static func frozen_hair(index: int, sex: String) -> Vector3i:
	return (HAIR_FROZEN.get(sex, HAIR_FROZEN["female"]) as Array)[posmod(index, 20)]

## The palette hair colour (0..19) nearest an apparent colour, by OKLab
## distance to the sex's palette apparent values; ties to the lower index.
static func nearest_hair_index(apparent: Color, sex: String) -> int:
	var target := oklab(apparent)
	var best := 0
	var distance := INF
	for index: int in 20:
		var d := target.distance_to(oklab(palette_apparent(index, sex)))
		if d < distance - TIE:
			best = index
			distance = d
	return best

## The hair to draw: {"index" (colour 0..19), "custom", "apparent" (sRGB),
## "dye" (the reference dye, D_MAX reach), "brow" (dye clamped to 1, for brows
## and stubble), "reach" (the uniform scale applied, 1 in reach)}. On the
## palette path dye and brow are develop's palette colour exactly.
static func hair(appearance: Dictionary, model_config: Dictionary) -> Dictionary:
	var byte := int(appearance.get("hair", 0)) if typeof(appearance.get("hair", 0)) in [TYPE_INT, TYPE_FLOAT] else 0
	var index := AppearanceVariants.hair_color_index(byte)
	var palette := AppearanceVariants.hair_color(byte)
	var result := {"index": index, "custom": false, "apparent": palette, "dye": palette, "brow": palette,
		"reach": 1.0}
	if not is_human(model_config):
		return result
	var wire := triple(appearance, "hair")
	var sex := body_sex(model_config)
	result["apparent"] = palette_apparent(index, sex)
	if wire == Vector3i.ZERO or wire == frozen_hair(index, sex):
		return result
	var apparent := triple_colour(wire)
	if nearest_hair_index(apparent, sex) != index:
		return result
	var dyed := hair_dye_linear(to_linear(apparent), sex, "R")
	result.merge({"custom": true, "apparent": apparent, "dye": to_srgb(dyed.dye),
		"brow": to_srgb(_limit_max(dyed.dye, 1.0)), "reach": dyed.reach}, true)
	return result

static func _limit_max(value: Vector3, ceiling: float) -> Vector3:
	var peak := maxf(value.x, maxf(value.y, value.z))
	return value * (ceiling / peak) if peak > ceiling else value

## The dye (linear) that shows apparent colour A (linear) on hair path `path`
## ("R", "P1".."P4", "B1", "B2", with style and slider position for a measured
## table): {"dye", "reach"}. Out of reach, A is scaled uniformly in linear
## light (hue and saturation kept) to the largest factor that fits D_MAX.
## A path without a measured entry uses R's frozen linear response.
static func hair_dye_linear(apparent: Vector3, sex: String, path: String = "R", style: int = 0,
		s: float = 50.0, length: int = 50, volume: int = 50) -> Dictionary:
	var entry := hair_table(sex, path, style, s)
	var skin_gain: Vector3 = SKIN_GAIN.get(sex, SKIN_GAIN["female"])
	# Length and volume reshape the hairstyle, which changes how much of it is
	# lit: the measured shape factor scales the path's response.
	var shape := Vector3.ONE
	if path in ["P1", "P2", "P3", "P4"]:
		shape = shape_factor(sex, path == "P4", style, length, volume, s)
	var gain: Vector3 = (entry.get("gain", hair_ratio(sex) * skin_gain) as Vector3) * shape
	if entry.has("model"):
		return model_dye(entry, skin_gain * apparent.max(Vector3.ZERO) / shape, entry.floor as Vector3, D_MAX)
	if entry.has("table"):
		return _iterative_dye(apparent / shape, entry, skin_gain)
	var dye := Vector3(apparent.x * skin_gain.x / maxf(gain.x, 1e-6), apparent.y * skin_gain.y / maxf(gain.y, 1e-6),
		apparent.z * skin_gain.z / maxf(gain.z, 1e-6))
	var peak := maxf(dye.x, maxf(dye.y, dye.z))
	var reach := 1.0
	if peak > D_MAX:
		reach = D_MAX / peak
		dye *= reach
	return {"dye": dye.max(Vector3.ZERO), "reach": reach}

## The per-path dye for a hair site (sRGB, as the materials take it): the
## palette dye on the palette path; else the dye that shows the apparent
## colour on that path.
static func hair_dye(appearance: Dictionary, model_config: Dictionary, path: String, style: int = 0,
		s: float = 50.0) -> Color:
	var resolved := hair(appearance, model_config)
	if not resolved.custom:
		return resolved.dye
	# Beards show the apparent colour the hair shows (owner Q-N4): scaled by
	# the reference path's reach, so a light colour beyond the hair's reach
	# does not draw a lighter beard.
	var apparent := to_linear(resolved.apparent) * (float(resolved.reach) if path in ["B1", "B2"] else 1.0)
	return to_srgb(hair_dye_linear(apparent, body_sex(model_config), path, style, s,
		roundi(CharacterProportions.value(appearance, "hair_length")),
		roundi(CharacterProportions.value(appearance, "hair_volume"))).dye)


# --------------------------------------------- measured hair tables (4.4)

## data/actors/hair_apparent.json: {"paths": {"<sex>/<path>/<style>/<s>":
## entry}} where an entry is linear {"gain": [r, g, b], "floor": [r, g, b]}
## (the lit hair mean mu = gain * dye + floor, linear light), a measured model
## {"model": "pigment" | "rl", ...} (see model_mu) or a forward table
## {"nodes": n, "dmax": x, "table": [n^3 apparent rgb triples, index
## (r * n + g) * n + b, dye nodes spaced in sRGB encoding over 0..dmax]}. The
## apparent colour of dye d is (mu(d) - mu(0)) / g_ref (SKIN_GAIN).
static func hair_tables() -> Dictionary:
	if not _hair_tables_loaded:
		_hair_tables_loaded = true
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(HAIR_TABLES_PATH)) \
			if FileAccess.file_exists(HAIR_TABLES_PATH) else null
		_hair_tables = (parsed as Dictionary).get("paths", {}) if parsed is Dictionary else {}
		_hair_shapes = (parsed as Dictionary).get("shapes", {}) if parsed is Dictionary else {}
		_index_positions()
	return _hair_tables

static func _index_positions() -> void:
	_hair_positions = {}
	for key: Variant in _hair_tables:
		var parts := str(key).split("/")
		if parts.size() != 4:
			continue
		var group := "%s/%s/%s" % [parts[0], parts[1], parts[2]]
		if not _hair_positions.has(group):
			_hair_positions[group] = []
		(_hair_positions[group] as Array).append(int(parts[3]))
	for group: Variant in _hair_positions:
		(_hair_positions[group] as Array).sort()

## Test seam: install tables (and shape factors) directly; an empty dictionary
## restores the file.
static func set_hair_tables(paths: Dictionary, shapes: Dictionary = {}) -> void:
	_hair_tables = paths
	_hair_shapes = shapes
	_hair_tables_loaded = not paths.is_empty()
	_index_positions()

## The measured positions either side of s (equal at or beyond the ends), as
## (low, high); the 25-step neighbours when nothing is listed.
static func _bracket(positions: Array, s: float) -> Vector2:
	if positions.is_empty():
		var step := int(floor(clampf(s, 0.0, 100.0) / 25.0)) * 25
		return Vector2(step, mini(step + 25, 100))
	var low := int(positions[0])
	var high := int(positions[-1])
	for value: Variant in positions:
		if float(value) <= s:
			low = int(value)
	for index: int in range(positions.size() - 1, -1, -1):
		if float(positions[index]) >= s:
			high = int(positions[index])
	return Vector2(low, maxi(high, low))

## The measured response scale of a legacy hairstyle at hair length and volume
## (0..100) against 50 / 50 at finish position s: the file's `shapes`
## "<sex>/<medium|high>/<style>/<s>" {"grid": positions, "factor": [rgb per
## (length, volume), length-major]}, bilinear, linear in s between the measured
## positions (the Classic grid, s 50, where no other is measured); 1 where
## nothing is measured.
static func shape_factor(sex: String, high: bool, style: int, length: int, volume: int, s: float = 50.0) -> Vector3:
	hair_tables()
	if length == 50 and volume == 50:
		return Vector3.ONE
	var group := "%s/%s/%d" % [sex, "high" if high else "medium", style]
	var measured: Array = []
	for position: int in [0, 25, 50, 75, 100]:
		if _hair_shapes.has("%s/%d" % [group, position]):
			measured.append(position)
	if measured.is_empty():
		return _shape_grid(_hair_shapes.get(group), length, volume)
	var span := _bracket(measured, s)
	var first := _shape_grid(_hair_shapes.get("%s/%d" % [group, int(span.x)]), length, volume)
	if int(span.y) == int(span.x):
		return first
	var second := _shape_grid(_hair_shapes.get("%s/%d" % [group, int(span.y)]), length, volume)
	return first.lerp(second, (clampf(s, span.x, span.y) - span.x) / (span.y - span.x))

static func _shape_grid(raw: Variant, length: int, volume: int) -> Vector3:
	if raw is not Dictionary:
		return Vector3.ONE
	var grid: Array = (raw as Dictionary).get("grid", [])
	var factors: Array = (raw as Dictionary).get("factor", [])
	var n := grid.size()
	if n < 2 or factors.size() != n * n:
		return Vector3.ONE
	var u := grid_cell(grid, float(length))
	var v := grid_cell(grid, float(volume))
	var result := Vector3.ZERO
	for corner: int in 4:
		var i := int(u.x) + (corner >> 1)
		var j := int(v.x) + (corner & 1)
		var weight := (u.y if corner >> 1 else 1.0 - u.y) * (v.y if corner & 1 else 1.0 - v.y)
		result += _vector(factors[i * n + j], Vector3.ONE) * weight
	return result

## The cell (x) and fraction (y) of `value` on an ascending grid, clamped.
static func grid_cell(grid: Array, value: float) -> Vector2:
	var n := grid.size()
	value = clampf(value, float(grid[0]), float(grid[n - 1]))
	for cell: int in n - 1:
		if value <= float(grid[cell + 1]):
			return Vector2(cell, (value - float(grid[cell])) / maxf(float(grid[cell + 1]) - float(grid[cell]), 1e-6))
	return Vector2(n - 2, 1.0)

## The measured entry for a path, linear and model entries interpolated in s
## between the measured finish positions 0, 25, 50, 75 and 100; {} when none
## is measured. "R" is P1 on the sex's reference style at s 50.
static func hair_table(sex: String, path: String, style: int, s: float) -> Dictionary:
	var paths := hair_tables()
	if paths.is_empty():
		return {}
	if path == "R":
		path = "P1"
		style = int(REFERENCE_STYLE.get(sex, 3))
		s = 50.0
	var exact: Variant = paths.get("%s/%s/%d/%d" % [sex, path, style, roundi(s)])
	if exact is Dictionary:
		return table_entry(exact as Dictionary)
	var span := _bracket(_hair_positions.get("%s/%s/%d" % [sex, path, style], []) as Array, s)
	var low := int(span.x)
	var high := int(span.y)
	var a: Variant = paths.get("%s/%s/%d/%d" % [sex, path, style, low])
	var b: Variant = paths.get("%s/%s/%d/%d" % [sex, path, style, high])
	if a is Dictionary and b is Dictionary:
		var u := 0.0 if high == low else (clampf(s, float(low), float(high)) - low) / float(high - low)
		var blended := lerp_entries(table_entry(a as Dictionary), table_entry(b as Dictionary), u)
		if not blended.is_empty():
			return blended
	var any: Variant = a if a is Dictionary else (b if b is Dictionary else null)
	return table_entry(any as Dictionary) if any is Dictionary else {}

static func _vector(value: Variant, fallback: Vector3) -> Vector3:
	if value is Array and (value as Array).size() >= 3:
		return Vector3(float(value[0]), float(value[1]), float(value[2]))
	return fallback

## The vector parameters of each measured model (model_mu).
const MODEL_TERMS := {"linear": ["gain", "floor"], "pigment": ["matte", "light", "floor"],
	"rl": ["gain", "hue", "floor"]}

## A raw table entry with its arrays as Vector3s.
static func table_entry(raw: Dictionary) -> Dictionary:
	if raw.has("table"):
		return {"table": raw["table"], "nodes": int(raw.get("nodes", 7)), "dmax": float(raw.get("dmax", D_MAX))}
	if raw.has("model") and MODEL_TERMS.has(str(raw.model)):
		var result := {"model": str(raw.model)}
		for term: String in MODEL_TERMS[str(raw.model)]:
			result[term] = _vector(raw.get(term), Vector3.ZERO)
		if raw.has("targetFloor"):
			result["targetFloor"] = _vector(raw.get("targetFloor"), result.floor)
		return result
	return {"gain": _vector(raw.get("gain"), Vector3.ONE), "floor": _vector(raw.get("floor"), Vector3.ZERO)}

## Two measured entries of one kind blended by u (0 = a); {} if their kinds differ.
static func lerp_entries(a: Dictionary, b: Dictionary, u: float) -> Dictionary:
	var kind_a := str(a.get("model", "linear" if a.has("gain") else ""))
	var kind_b := str(b.get("model", "linear" if b.has("gain") else ""))
	if kind_a != kind_b or not MODEL_TERMS.has(kind_a):
		return {}
	var result := {} if not a.has("model") else {"model": kind_a}
	for term: String in MODEL_TERMS[kind_a]:
		result[term] = (a[term] as Vector3).lerp(b[term], u)
	if a.has("targetFloor") and b.has("targetFloor"):
		result["targetFloor"] = (a.targetFloor as Vector3).lerp(b.targetFloor, u)
	return result

## The forward response of a measured path, the lit hair mean (linear) for
## dye d (linear, as the shader sees it), in the functional form of its shader:
##   linear  - gain * d + floor (StandardMaterial, portrait_hair, beard shells);
##   pigment - matte * m(d) + light * l(d) + floor, high_hair_appearance's
##             pigment(): m = mix(d, luma(d), 0.10), l = sqrt(d) warmed by
##             smoothstep(0, 0.35, d.r - max(d.g, d.b)) towards (1, 0.90, 0.73);
##   rl      - gain * d + hue * d / max(d) + floor, rl_hair.gdshader's diffuse
##             and its hue-normalised primary sheen.
## Each term's coefficient is fitted per channel to rendered means
## (calibration probe), so the forms are exact up to clipping and 8-bit output.
static func model_mu(model: Dictionary, dye: Vector3) -> Vector3:
	var d := dye.max(Vector3.ZERO)
	match str(model.get("model", "linear")):
		"pigment":
			var value := d.dot(LUMA)
			var matte := d * 0.9 + Vector3.ONE * (value * 0.1)
			var warm := smoothstep(0.0, 0.35, d.x - maxf(d.y, d.z))
			var light := Vector3(sqrt(d.x), sqrt(d.y), sqrt(d.z)) * Vector3.ONE.lerp(Vector3(1.0, 0.90, 0.73), warm)
			return (model.matte as Vector3) * matte + (model.light as Vector3) * light + (model.floor as Vector3)
		"rl":
			var peak := maxf(maxf(d.x, d.y), maxf(d.z, 1e-4))
			return (model.gain as Vector3) * d + (model.hue as Vector3) * (d / peak) + (model.floor as Vector3)
	return (model.gain as Vector3) * d + (model.floor as Vector3)

## The dye (linear, 0..dmax) whose lit mean is base + rise on a measured
## model: {"dye", "reach"}. A rise out of reach is scaled uniformly (hue and
## saturation kept) to the largest factor the model reaches at dmax on every
## channel; a target below the model's own floor on a channel takes dye 0
## there. Per channel bisection, Gauss-Seidel sweeps: deterministic.
static func model_dye(model: Dictionary, rise: Vector3, base: Vector3, dmax: float) -> Dictionary:
	rise = rise.max(Vector3.ZERO)
	var ceiling := model_mu(model, Vector3.ONE * dmax)
	var reach := 1.0
	for axis: int in 3:
		if base[axis] + rise[axis] > ceiling[axis] and rise[axis] > 0.0:
			reach = minf(reach, maxf(ceiling[axis] - base[axis], 0.0) / rise[axis])
	var dye := _model_solve(model, base + rise * reach, dmax)
	# A model whose channels share terms (the pigment model's luma) can fall
	# short below the all-dmax ceiling: shrink the factor until every channel
	# reaches its target, so the hue holds.
	if _model_short(model, dye, base + rise * reach, dmax):
		var low := 0.0
		var high := reach
		for _step: int in 16:
			var middle := (low + high) * 0.5
			if _model_short(model, _model_solve(model, base + rise * middle, dmax), base + rise * middle, dmax):
				high = middle
			else:
				low = middle
		reach = low
		dye = _model_solve(model, base + rise * reach, dmax)
	return {"dye": dye, "reach": reach}

## Per channel bisection with Gauss-Seidel sweeps for the dye whose lit mean
## is `target` (clamped to 0..dmax).
static func _model_solve(model: Dictionary, target: Vector3, dmax: float) -> Vector3:
	var floor_mu := model_mu(model, Vector3.ZERO)
	var top := model_mu(model, Vector3.ONE * dmax)
	var dye := Vector3.ZERO
	for axis: int in 3:
		var slope := maxf(top[axis] - floor_mu[axis], 1e-6) / dmax
		dye[axis] = clampf((target[axis] - floor_mu[axis]) / slope, 0.0, dmax)
	for _sweep: int in SOLVE_SWEEPS:
		for axis: int in 3:
			var low := 0.0
			var high := dmax
			for _step: int in SOLVE_STEPS:
				var middle := (low + high) * 0.5
				var probe := dye
				probe[axis] = middle
				if model_mu(model, probe)[axis] < target[axis]:
					low = middle
				else:
					high = middle
			dye[axis] = (low + high) * 0.5
	return dye

## Whether a channel sits at dmax and still falls short of its target.
static func _model_short(model: Dictionary, dye: Vector3, target: Vector3, dmax: float) -> bool:
	var shown := model_mu(model, dye)
	for axis: int in 3:
		if dye[axis] >= dmax * (1.0 - 1e-6) and shown[axis] < target[axis] - 1e-6:
			return true
	return false

## A non-linear table's apparent colour for dye d (linear): trilinear over the
## forward table, whose nodes are spaced evenly in sRGB-encoded dye.
static func table_apparent(entry: Dictionary, dye: Vector3) -> Vector3:
	var n := int(entry.nodes)
	var dmax := float(entry.dmax)
	var table: Array = entry.table
	var encoded := Vector3(_enc(clampf(dye.x / dmax, 0.0, 1.0)), _enc(clampf(dye.y / dmax, 0.0, 1.0)),
		_enc(clampf(dye.z / dmax, 0.0, 1.0))) * float(n - 1)
	var base := Vector3i(mini(int(encoded.x), n - 2), mini(int(encoded.y), n - 2), mini(int(encoded.z), n - 2))
	var f := encoded - Vector3(base)
	var result := Vector3.ZERO
	for corner: int in 8:
		var offset := Vector3i(corner >> 2 & 1, corner >> 1 & 1, corner & 1)
		var node := base + offset
		var weight := (f.x if offset.x else 1.0 - f.x) * (f.y if offset.y else 1.0 - f.y) * (f.z if offset.z else 1.0 - f.z)
		result += _vector(table[(node.x * n + node.y) * n + node.z], Vector3.ZERO) * weight
	return result

## Inverse of a forward table: d <- clamp(d * A_target / A(d), 0, dmax), 8
## iterations in linear light from the linear estimate; out of reach, A is
## scaled uniformly to the largest factor the table reaches.
static func _iterative_dye(apparent: Vector3, entry: Dictionary, skin_gain: Vector3) -> Dictionary:
	var dmax := float(entry.dmax)
	var ceiling := table_apparent(entry, Vector3.ONE * dmax)
	var reach := 1.0
	for axis: int in 3:
		if apparent[axis] > ceiling[axis] and apparent[axis] > 0.0:
			reach = minf(reach, ceiling[axis] / apparent[axis])
	var target := apparent * reach
	var probe := table_apparent(entry, Vector3.ONE * dmax * 0.5)
	var dye := Vector3.ZERO
	for axis: int in 3:
		dye[axis] = clampf(target[axis] * dmax * 0.5 / maxf(probe[axis], 1e-6), 0.0, dmax)
	for _iteration: int in 8:
		var shown := table_apparent(entry, dye)
		for axis: int in 3:
			dye[axis] = clampf(dye[axis] * target[axis] / maxf(shown[axis], 1e-6), 0.0, dmax) \
				if shown[axis] > 1e-6 else dye[axis]
	return {"dye": dye, "reach": reach}


# --------------------------------------------------------------- eyes

## The eye palette entry (0..11) nearest a pigment, by OKLab distance.
static func nearest_eye_index(pigment: Color) -> int:
	var target := oklab(pigment)
	var best := 0
	var distance := INF
	for index: int in 12:
		var d := target.distance_to(oklab(AppearanceVariants.eye_color(index)))
		if d < distance - TIE:
			best = index
			distance = d
	return best

## The custom iris pigment within the readability limits: OKHSL lightness
## 0.20-0.80, saturation at most 0.92.
static func limit_eye(pigment: Color) -> Color:
	return Color.from_ok_hsl(pigment.ok_hsl_h, minf(pigment.ok_hsl_s, EYE_SAT_MAX),
		clampf(pigment.ok_hsl_l, EYE_LIGHT_MIN, EYE_LIGHT_MAX))

## The iris pigment: {"index", "custom", "pigment", "limited"}.
static func eyes(appearance: Dictionary, model_config: Dictionary) -> Dictionary:
	var index := int(appearance.get("eyes", 0)) if typeof(appearance.get("eyes", 0)) in [TYPE_INT, TYPE_FLOAT] else 0
	var palette := AppearanceVariants.eye_color(index)
	var result := {"index": index, "custom": false, "pigment": palette, "limited": false}
	if not is_human(model_config):
		return result
	var wire := triple(appearance, "eyes")
	if wire == Vector3i.ZERO or wire == EYE_FROZEN[posmod(index, 12)]:
		return result
	var pigment := triple_colour(wire)
	if nearest_eye_index(pigment) != posmod(index, 12):
		return result
	var limited := limit_eye(pigment)
	result.merge({"custom": true, "pigment": limited,
		"limited": not limited.is_equal_approx(pigment)}, true)
	return result


# --------------------------------------------------------------- garments

static func frozen_dye(part: String, index: int) -> Vector3i:
	index = posmod(index, 12)
	return (DYE_FROZEN_OWN[part] as Array)[index] if index < 3 else DYE_FROZEN_SHARED[index - 3]

## The luminous dye (0..11) for `part` nearest a colour, by OKLab distance.
static func nearest_dye_index(colour: Color, part: String) -> int:
	var target := oklab(colour)
	var best := 0
	var distance := INF
	for index: int in 12:
		var d := target.distance_to(oklab(AppearanceVariants.wardrobe_color("luminous", PARTS[part], index)))
		if d < distance - TIE:
			best = index
			distance = d
	return best

## A custom dye within the limits: OKHSL lightness 0.15-0.92, then for the
## shirt and pants at least GARMENT_CONTRAST (OKLab) from the skin, by
## stepping the lightness away from the skin's (the other way if the window
## runs out first; the farther of the two if neither reaches it).
static func limit_garment(colour: Color, part: String, skin_colour: Color) -> Color:
	var h := colour.ok_hsl_h
	var s := colour.ok_hsl_s
	var l := clampf(colour.ok_hsl_l, GARMENT_LIGHT_MIN, GARMENT_LIGHT_MAX)
	var limited := Color.from_ok_hsl(h, s, l)
	if part == "boots" or delta_e(limited, skin_colour) >= GARMENT_CONTRAST:
		return limited
	var skin_l := oklab(skin_colour).x
	var first := 1.0 if oklab(limited).x >= skin_l else -1.0
	var best := limited
	var best_distance := delta_e(limited, skin_colour)
	for direction: float in [first, -first]:
		var step := l
		while true:
			step += direction * 0.01
			if step < GARMENT_LIGHT_MIN - 1e-9 or step > GARMENT_LIGHT_MAX + 1e-9:
				break
			var candidate := Color.from_ok_hsl(h, s, step)
			var distance := delta_e(candidate, skin_colour)
			if distance >= GARMENT_CONTRAST:
				return candidate
			if distance > best_distance:
				best = candidate
				best_distance = distance
	return best

## A garment's dye: {"index", "custom", "colour", "limited"}; `part` is
## "shirt", "pants" or "boots".
static func garment(appearance: Dictionary, model_config: Dictionary, part: String) -> Dictionary:
	var index := int(appearance.get(part, 0)) if typeof(appearance.get(part, 0)) in [TYPE_INT, TYPE_FLOAT] else 0
	var culture := str(model_config.get("culture", "luminous"))
	var palette := AppearanceVariants.wardrobe_color(culture, PARTS[part], index)
	var result := {"index": index, "custom": false, "colour": palette, "limited": false}
	if not is_human(model_config):
		return result
	var wire := triple(appearance, part)
	if wire == Vector3i.ZERO or wire == frozen_dye(part, index):
		return result
	var dye := triple_colour(wire)
	if nearest_dye_index(dye, part) != posmod(index, 12):
		return result
	var limited := limit_garment(dye, part, skin_shown(appearance, model_config))
	result.merge({"custom": true, "colour": limited, "limited": not limited.is_equal_approx(dye)}, true)
	return result


# --------------------------------------------------------------- whole look

## Everything the renderer draws for one appearance (see the functions above).
static func resolve(appearance: Dictionary, model_config: Dictionary) -> Dictionary:
	return {"human": is_human(model_config), "sex": body_sex(model_config),
		"skin": skin(appearance, model_config), "hair": hair(appearance, model_config),
		"eyes": eyes(appearance, model_config), "shirt": garment(appearance, model_config, "shirt"),
		"pants": garment(appearance, model_config, "pants"), "boots": garment(appearance, model_config, "boots"),
		"finish": HAIR_FINISH.resolve(appearance) if is_human(model_config) \
			else {"enum": _field(appearance, "hair_detail", 2), "s": HAIR_FINISH.enum_slider(_field(appearance, "hair_detail", 2)), "custom": false}}

## The saved form of an edited look (Rule B and spec 2.7): every custom value
## equal to a palette entry's frozen value becomes that palette byte with the
## custom fields 0; every other custom value keeps its fields and writes the
## nearest palette byte into the legacy field (skin, the colour part of hair,
## eyes, shirt, pants, boots), so older recipients and PC/2 servers see the
## nearest palette look. An undertone of 101 is written 0; an Eloria skin
## (6-9) drops tone and undertone. The hair finish slider likewise
## (HairFinish.canonical). `sex` is the body's ("female" / "male").
static func canonical(appearance: Dictionary, sex: String) -> Dictionary:
	var result := appearance.duplicate()
	var tone := _field(appearance, "skin_tone", 201)
	var undertone := _field(appearance, "skin_undertone", 201)
	if undertone == 101:
		undertone = 0
	var skin_index := int(appearance.get("skin", 0))
	if skin_index >= 6:
		tone = 0
		undertone = 0
	elif tone >= 1:
		skin_index = nearest_skin_index(tone)
		if tone == skin_position(skin_index) and undertone == 0:
			tone = 0
	result.merge({"skin": skin_index, "skin_tone": tone, "skin_undertone": undertone}, true)
	var hair_byte := int(appearance.get("hair", 0))
	var wire := triple(appearance, "hair")
	if wire != Vector3i.ZERO:
		var colour := AppearanceVariants.hair_color_index(hair_byte)
		var snapped := (HAIR_FROZEN.get(sex, HAIR_FROZEN["female"]) as Array).find(wire)
		colour = snapped if snapped >= 0 else nearest_hair_index(triple_colour(wire), sex)
		result["hair"] = AppearanceVariants.pack_hair(AppearanceVariants.hair_style(hair_byte), colour)
		if snapped >= 0:
			wire = Vector3i.ZERO
	_write_triple(result, "hair", wire)
	wire = triple(appearance, "eyes")
	if wire != Vector3i.ZERO:
		var snapped := EYE_FROZEN.find(wire)
		result["eyes"] = snapped if snapped >= 0 else nearest_eye_index(triple_colour(wire))
		if snapped >= 0:
			wire = Vector3i.ZERO
	_write_triple(result, "eyes", wire)
	for part: String in PARTS:
		wire = triple(appearance, part)
		if wire != Vector3i.ZERO:
			var snapped := -1
			for index: int in 12:
				if frozen_dye(part, index) == wire:
					snapped = index
					break
			result[part] = snapped if snapped >= 0 else nearest_dye_index(triple_colour(wire), part)
			if snapped >= 0:
				wire = Vector3i.ZERO
		_write_triple(result, part, wire)
	var finish := _field(appearance, "hair_finish", HAIR_FINISH.MAXIMUM)
	if finish >= 1:
		result.merge(HAIR_FINISH.canonical(finish - 1), true)
	return result

## The legacy key each group of custom fields belongs to (spec 3.4): a
## changed legacy identity makes the group's custom values stale.
const CLEARING_GROUPS := {"skin": ["skin_tone", "skin_undertone"],
	"hair": ["hair_hue", "hair_sat", "hair_light"], "eyes": ["eye_hue", "eye_sat", "eye_light"],
	"shirt": ["shirt_hue", "shirt_sat", "shirt_light"], "pants": ["pants_hue", "pants_sat", "pants_light"],
	"boots": ["boots_hue", "boots_sat", "boots_light"], "hair_detail": ["hair_finish"]}

static func _identity(key: String, value: Variant) -> int:
	var number := int(value) if typeof(value) in [TYPE_INT, TYPE_FLOAT] else 0
	return AppearanceVariants.hair_color_index(number) if key == "hair" else number

## The client's mirror of the server's #appearance clearing rule: where an
## edit changed a legacy key's identity (the colour part of hair) and left
## that group's custom fields as they were, those fields become 0, so a
## palette pick replaces a stale custom colour or slider position.
static func clear_replaced(before: Dictionary, after: Dictionary) -> Dictionary:
	var result := after.duplicate()
	for key: String in CLEARING_GROUPS:
		if not after.has(key) or _identity(key, before.get(key, 0)) == _identity(key, after[key]):
			continue
		var touched := false
		for field: String in CLEARING_GROUPS[key]:
			if int(after.get(field, 0)) != int(before.get(field, 0)):
				touched = true
		if not touched:
			for field: String in CLEARING_GROUPS[key]:
				if result.has(field):
					result[field] = 0
	return result

static func _write_triple(result: Dictionary, group: String, wire: Vector3i) -> void:
	var names: Array = PortraitCustomization.COLOUR_TRIPLES[group]
	result[names[0]] = wire.x
	result[names[1]] = wire.y
	result[names[2]] = wire.z
