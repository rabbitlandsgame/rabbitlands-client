class_name PortraitCustomization
extends RefCounted
## Compact appearance extension; order is shared with the server PC/1 trailer.

const FIELDS := ["facial_hair", "jaw", "cheekbones", "nose", "height", "build", "hair_detail"]
const DEFAULTS := {"facial_hair": 0, "jaw": 50, "cheekbones": 50, "nose": 50,
	"height": 50, "build": 50, "hair_detail": 0}
const TAG := [80, 67, 1]

static func maximum(field: String) -> int:
	return 5 if field == "facial_hair" else (2 if field == "hair_detail" else 100)

static func normalized(appearance: Dictionary) -> Dictionary:
	var result := {}
	for field: String in FIELDS:
		result[field] = clampi(int(appearance.get(field, DEFAULTS[field])), 0, maximum(field))
	return result

static func encode(appearance: Dictionary) -> PackedByteArray:
	var result := PackedByteArray(TAG)
	var values := normalized(appearance)
	for field: String in FIELDS:
		result.append(values[field])
	return result

static func decode(payload: PackedByteArray, offset: int) -> Dictionary:
	if payload.size() < offset + 10 or payload.slice(offset, offset + 3) != PackedByteArray(TAG):
		return {}
	var result := {}
	for index: int in FIELDS.size():
		var field: String = FIELDS[index]
		var value := int(payload[offset + 3 + index])
		if value > maximum(field):
			return {}
		result[field] = value
	return result
