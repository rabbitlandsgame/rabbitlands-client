class_name HumanPortraitPresets
extends RefCounted
## Editable starting points guided by the archived Human player studies.
## These contain cosmetic values only, never a body/sex or starting class.

const LOOKS := {
	"Rowan": {"facial_hair": 0, "jaw": 38, "cheekbones": 70, "nose": 42,
		"height": 55, "build": 48, "hair_detail": 1,
		"face_length": 65, "eye_size": 15, "eye_tilt": 58, "eye_spacing": 45,
		"nose_width": 35, "lip_fullness": 44, "brow_depth": 70,
		"hair_length": 75, "hair_volume": 76},
	"Mira": {"facial_hair": 0, "jaw": 30, "cheekbones": 70, "nose": 32,
		"height": 50, "build": 38, "hair_detail": 2,
		"face_length": 35, "eye_size": 25, "eye_tilt": 67, "eye_spacing": 50,
		"nose_width": 18, "lip_fullness": 85, "brow_depth": 45,
		"hair_length": 70, "hair_volume": 72},
	"Tavi": {"facial_hair": 5, "jaw": 88, "cheekbones": 64, "nose": 68,
		"height": 62, "build": 78, "hair_detail": 2,
		"face_length": 55, "eye_size": 15, "eye_tilt": 45, "eye_spacing": 46,
		"nose_width": 65, "lip_fullness": 42, "brow_depth": 85,
		"hair_length": 68, "hair_volume": 68},
}
const PALETTES := {
	"Rowan": {"style": 1, "hair_color": 1, "eyes": 2, "skin": 2},
	"Mira": {"style": 3, "hair_color": 4, "eyes": 1, "skin": 1},
	"Tavi": {"style": 1, "hair_color": 1, "eyes": 2, "skin": 3},
}

static func shape(name: String) -> Dictionary:
	return (LOOKS.get(name, {}) as Dictionary).duplicate(true)

static func palette(name: String) -> Dictionary:
	var entry: Dictionary = PALETTES.get(name, {})
	if entry.is_empty():
		return {}
	return {"hair": AppearanceVariants.pack_hair(entry.style, entry.hair_color),
		"eyes": entry.eyes, "skin": entry.skin}

static func appearance(name: String) -> Dictionary:
	return shape(name).merged(palette(name))
