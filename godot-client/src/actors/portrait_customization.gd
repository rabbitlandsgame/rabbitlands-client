class_name PortraitCustomization
extends RefCounted
## Compact, versioned appearance; order is shared with the server trailers.
##
## PC/1 is 7 fields, PC/2 16 and PC/3 53 (E:/rlw/pc3-spec.md as amended by the
## colour model spec revision 3): PC/2, then the 11 High face offsets (50 =
## none), 9 detail fields (0 = Auto; hair_finish 0 = from hair_detail) and 17
## colour fields (0 = the palette colour; a colour triple is custom only when
## all three of its bytes are set, Rule A). Each version's fields are a strict
## prefix of the next; the neutral values are fixed for all time.

const V1_FIELDS := ["facial_hair", "jaw", "cheekbones", "nose", "height", "build", "hair_detail"]
const EXTRA_FIELDS := ["face_length", "eye_size", "eye_tilt", "eye_spacing", "nose_width",
	"lip_fullness", "brow_depth", "hair_length", "hair_volume"]
const V2_FIELDS := V1_FIELDS + EXTRA_FIELDS
## One offset per RL control without a PC/1 or PC/2 field (rlHead.controls order).
const V3_CONTROLS := ["eyelid", "brow_height", "nose_length", "nose_bridge", "nose_tip",
	"mouth_width", "cupid_bow", "cheek_fullness", "chin_projection", "chin_width", "ear_size"]
const V3_DETAILS := ["brow_style", "brow_thickness", "freckles", "liner", "liner_wing",
	"stubble", "lip_tint", "hair_module", "hair_finish"]
const V3_COLOURS := ["skin_tone", "skin_undertone", "hair_hue", "hair_sat", "hair_light",
	"eye_hue", "eye_sat", "eye_light", "shirt_hue", "shirt_sat", "shirt_light",
	"pants_hue", "pants_sat", "pants_light", "boots_hue", "boots_sat", "boots_light"]
const V3_FIELDS := V3_CONTROLS + V3_DETAILS + V3_COLOURS
const FIELDS := V2_FIELDS + V3_FIELDS
## The five OKHSL triples (hue 1..240, saturation and lightness 1..101).
const COLOUR_TRIPLES := {"hair": ["hair_hue", "hair_sat", "hair_light"],
	"eyes": ["eye_hue", "eye_sat", "eye_light"],
	"shirt": ["shirt_hue", "shirt_sat", "shirt_light"],
	"pants": ["pants_hue", "pants_sat", "pants_light"],
	"boots": ["boots_hue", "boots_sat", "boots_light"]}
const DEFAULTS := {"facial_hair": 0, "jaw": 50, "cheekbones": 50, "nose": 50,
	"height": 50, "build": 50, "hair_detail": 0, "face_length": 50, "eye_size": 50,
	"eye_tilt": 50, "eye_spacing": 50, "nose_width": 50, "lip_fullness": 50,
	"brow_depth": 50, "hair_length": 50, "hair_volume": 50,
	"eyelid": 50, "brow_height": 50, "nose_length": 50, "nose_bridge": 50, "nose_tip": 50,
	"mouth_width": 50, "cupid_bow": 50, "cheek_fullness": 50, "chin_projection": 50,
	"chin_width": 50, "ear_size": 50,
	"brow_style": 0, "brow_thickness": 0, "freckles": 0, "liner": 0, "liner_wing": 0,
	"stubble": 0, "lip_tint": 0, "hair_module": 0, "hair_finish": 0,
	"skin_tone": 0, "skin_undertone": 0, "hair_hue": 0, "hair_sat": 0, "hair_light": 0,
	"eye_hue": 0, "eye_sat": 0, "eye_light": 0, "shirt_hue": 0, "shirt_sat": 0,
	"shirt_light": 0, "pants_hue": 0, "pants_sat": 0, "pants_light": 0, "boots_hue": 0,
	"boots_sat": 0, "boots_light": 0}
## Wire maxima other than 100 (the server asserts the same literal table).
const MAXIMA := {"facial_hair": 5, "hair_detail": 2, "brow_style": 13, "brow_thickness": 101,
	"freckles": 101, "liner": 101, "liner_wing": 101, "stubble": 101, "lip_tint": 12,
	"hair_module": 31, "hair_finish": 101, "skin_tone": 201, "skin_undertone": 201,
	"hair_hue": 240, "hair_sat": 101, "hair_light": 101, "eye_hue": 240, "eye_sat": 101,
	"eye_light": 101, "shirt_hue": 240, "shirt_sat": 101, "shirt_light": 101,
	"pants_hue": 240, "pants_sat": 101, "pants_light": 101, "boots_hue": 240,
	"boots_sat": 101, "boots_light": 101}
const TAG := [80, 67, 1]
const V2_TAG := [80, 67, 2]
const V3_TAG := [80, 67, 3]
const LATEST := 3
const V2_MESSAGE := "This server does not support the new face, eye and hair controls yet. Return those controls to neutral (50) or use an updated server."
const V3_DETAIL_MESSAGE := "This server cannot save the High-detail face options yet. Set them back to Auto (or the centre for shape sliders), or use an updated server."
const COLOUR_MESSAGE := "This server cannot save custom colours yet. Pick a palette colour (or press Use nearest palette colours), or use an updated server."

static func maximum(field: String) -> int:
	return int(MAXIMA.get(field, 100))

## The fields a version encodes: 0 none, 1 PC/1, 2 PC/2, 3 PC/3 (all).
static func fields_for(version: int) -> Array:
	match version:
		1:
			return V1_FIELDS
		2:
			return V2_FIELDS
		3:
			return FIELDS
	return []

## The first version that carries a field, 0 for an unknown name.
static func field_version(field: String) -> int:
	if field in V1_FIELDS:
		return 1
	if field in EXTRA_FIELDS:
		return 2
	if field in V3_FIELDS:
		return 3
	return 0

## The trailer tag for a version, empty for an unknown one.
static func tag(version: int) -> Array:
	match version:
		1:
			return TAG
		2:
			return V2_TAG
		3:
			return V3_TAG
	return []

## Every field, bounded: a missing or non-integer value is neutral, an
## out-of-range integer clamped; then Rule A makes a partly set colour triple
## the palette colour (all three 0). The server's read() does the same.
static func normalized(appearance: Dictionary) -> Dictionary:
	var result := {}
	for field: String in FIELDS:
		var value: Variant = appearance.get(field, DEFAULTS[field])
		result[field] = (clampi(int(value), 0, maximum(field))
			if _integer(value) else DEFAULTS[field])
	for triple: Variant in COLOUR_TRIPLES.values():
		var names: Array = triple
		if int(result[names[0]]) < 1 or int(result[names[1]]) < 1 or int(result[names[2]]) < 1:
			for name: String in names:
				result[name] = 0
	return result

static func _integer(value: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) \
		and floor(float(value)) == float(value)

## Sending callers validate first; unsupported choices must never disappear
## through the compatibility encoder. Offline previews need no peer.
static func validate(appearance: Dictionary, version := LATEST) -> Dictionary:
	for field: String in FIELDS:
		if not appearance.has(field):
			continue
		var value: Variant = appearance[field]
		if not _integer(value) or value < 0 or value > maximum(field):
			return {"ok": false, "error": "invalid", "message": "%s must be an integer from 0 to %d." % [field, maximum(field)]}
		if field_version(field) > version and value != DEFAULTS[field]:
			var message := V2_MESSAGE
			if field in V3_COLOURS:
				message = COLOUR_MESSAGE
			elif field_version(field) == 3:
				message = V3_DETAIL_MESSAGE
			return {"ok": false, "error": "unsupported", "message": message}
	return {"ok": true}

static func encode(appearance: Dictionary, version := 1) -> PackedByteArray:
	if version not in [1, 2, 3]:
		return PackedByteArray()
	var result := PackedByteArray(tag(version))
	var values := normalized(appearance)
	for field: String in fields_for(version):
		result.append(values[field])
	return result

static func decode(payload: PackedByteArray, offset: int) -> Dictionary:
	if offset < 0 or payload.size() < offset + 3:
		return {}
	var version := int(payload[offset + 2])
	var fields: Array = fields_for(version)
	if version not in [1, 2, 3] or payload[offset] != 80 or payload[offset + 1] != 67 \
			or payload.size() != offset + 3 + fields.size():
		return {}
	var result := {}
	for index: int in fields.size():
		var field: String = fields[index]
		var value := int(payload[offset + 3 + index])
		if value > maximum(field):
			return {}
		result[field] = value
	return normalized(result)
