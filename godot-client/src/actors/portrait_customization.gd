class_name PortraitCustomization
extends RefCounted
## Compact, versioned appearance; order is shared with the server trailers.

const V1_FIELDS := ["facial_hair", "jaw", "cheekbones", "nose", "height", "build", "hair_detail"]
const EXTRA_FIELDS := ["face_length", "eye_size", "eye_tilt", "eye_spacing", "nose_width",
	"lip_fullness", "brow_depth", "hair_length", "hair_volume"]
const FIELDS := V1_FIELDS + EXTRA_FIELDS
const DEFAULTS := {"facial_hair": 0, "jaw": 50, "cheekbones": 50, "nose": 50,
	"height": 50, "build": 50, "hair_detail": 0, "face_length": 50, "eye_size": 50,
	"eye_tilt": 50, "eye_spacing": 50, "nose_width": 50, "lip_fullness": 50,
	"brow_depth": 50, "hair_length": 50, "hair_volume": 50}
const TAG := [80, 67, 1]
const V2_TAG := [80, 67, 2]

static func maximum(field: String) -> int:
	return 5 if field == "facial_hair" else (2 if field == "hair_detail" else 100)

static func normalized(appearance: Dictionary) -> Dictionary:
	var result := {}
	for field: String in FIELDS:
		var value: Variant = appearance.get(field, DEFAULTS[field])
		result[field] = (clampi(int(value), 0, maximum(field))
			if _integer(value) else DEFAULTS[field])
	return result

static func _integer(value: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) \
		and floor(float(value)) == float(value)

## Sending callers validate first; unsupported choices must never disappear
## through the compatibility encoder. Offline previews need no peer.
static func validate(appearance: Dictionary, version := 2) -> Dictionary:
	for field: String in FIELDS:
		if not appearance.has(field):
			continue
		var value: Variant = appearance[field]
		if not _integer(value) or value < 0 or value > maximum(field):
			return {"ok": false, "error": "invalid", "message": "%s must be an integer from 0 to %d." % [field, maximum(field)]}
		if version < 2 and field in EXTRA_FIELDS and value != DEFAULTS[field]:
			return {"ok": false, "error": "unsupported", "message": "This server does not support the new face, eye and hair controls yet. Return those controls to neutral (50) or use an updated server."}
	return {"ok": true}

static func encode(appearance: Dictionary, version := 1) -> PackedByteArray:
	if version not in [1, 2]:
		return PackedByteArray()
	var result := PackedByteArray(V2_TAG if version == 2 else TAG)
	var values := normalized(appearance)
	for field: String in FIELDS if version == 2 else V1_FIELDS:
		result.append(values[field])
	return result

static func decode(payload: PackedByteArray, offset: int) -> Dictionary:
	if offset < 0 or payload.size() < offset + 3:
		return {}
	var version := int(payload[offset + 2])
	var fields: Array = FIELDS if version == 2 else V1_FIELDS
	if version not in [1, 2] or payload[offset] != 80 or payload[offset + 1] != 67 \
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
