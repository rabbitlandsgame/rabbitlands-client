class_name HumanPortraitPresets
extends RefCounted
## Editable starting points guided by the archived Human player studies.
## These contain cosmetic values only, never a body/sex or starting class.

const LOOKS := {
	"Rowan": {"facial_hair": 0, "jaw": 65, "cheekbones": 80, "nose": 55,
		"height": 55, "build": 48, "hair_detail": 1,
		"face_length": 75, "eye_size": 35, "eye_tilt": 58, "eye_spacing": 45,
		"nose_width": 40, "lip_fullness": 30, "brow_depth": 85,
		"hair_length": 75, "hair_volume": 76},
	"Mira": {"facial_hair": 0, "jaw": 30, "cheekbones": 70, "nose": 32,
		"height": 50, "build": 38, "hair_detail": 2,
		"face_length": 35, "eye_size": 65, "eye_tilt": 67, "eye_spacing": 42,
		"nose_width": 22, "lip_fullness": 65, "brow_depth": 75,
		"hair_length": 70, "hair_volume": 72},
	"Tavi": {"facial_hair": 5, "jaw": 88, "cheekbones": 64, "nose": 68,
		"height": 62, "build": 78, "hair_detail": 1,
		"face_length": 55, "eye_size": 30, "eye_tilt": 45, "eye_spacing": 46,
		"nose_width": 65, "lip_fullness": 42, "brow_depth": 100,
		"hair_length": 68, "hair_volume": 68},
}
const PALETTES := {
	"Rowan": {"style": 1, "hair_color": 1, "eyes": 2, "skin": 0},
	"Mira": {"style": 3, "hair_color": 4, "eyes": 1, "skin": 1},
	"Tavi": {"style": 1, "hair_color": 1, "eyes": 2, "skin": 0},
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
