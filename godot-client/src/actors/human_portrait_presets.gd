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
## Develop's study palettes. Renderer fixtures and the RL High parity tool draw
## these looks (appearance()), so they stay as they are.
const PALETTES := {
	"Rowan": {"style": 1, "hair_color": 1, "eyes": 2, "skin": 0},
	"Mira": {"style": 3, "hair_color": 4, "eyes": 1, "skin": 1},
	"Tavi": {"style": 1, "hair_color": 1, "eyes": 2, "skin": 0},
}
## What the preset buttons pick (colour model spec section 5): the palette
## entries nearest the concept art - the skin stop nearest its slider position,
## the hair colour nearest its apparent colour. These are the legacy bytes the
## custom colours below save with, and what a PC/1 or PC/2 session picks.
const NEAREST := {
	"Rowan": {"style": 1, "hair_color": 2, "eyes": 2, "skin": 2},
	"Mira": {"style": 3, "hair_color": 14, "eyes": 1, "skin": 1},
	"Tavi": {"style": 1, "hair_color": 12, "eyes": 2, "skin": 2},
}
## The concept art's colours (colour model spec section 5), applied only while
## custom colours are offered (PC/3, Human): skin slider position and
## undertone, and the hair's apparent colour as an OKHSL wire triple. Eyes and
## clothes keep the palette; the finishes are the LOOKS enums (Tousled, Swept).
const COLOURS := {
	"Rowan": {"skin_tone": 38, "skin_undertone": 90, "hair_hue": 35, "hair_sat": 45, "hair_light": 19},
	"Mira": {"skin_tone": 10, "skin_undertone": 51, "hair_hue": 25, "hair_sat": 86, "hair_light": 39},
	"Tavi": {"skin_tone": 68, "skin_undertone": 95, "hair_hue": 38, "hair_sat": 40, "hair_light": 24},
}
## PC/3 High face detail (PC/3 spec 8.4), applied only while the More face
## detail section is offered. Rowan and Mira are the RL base heads, so their
## offsets stay 50; Tavi's are RLHeadPortraitMap's inverse of the RL tavi
## preset (to_portrait_fields, Appendix A), frozen. Rowan's stubble follows
## the RL head (61); develop's Rowan has no facial hair at Low and Medium.
const DETAILS := {
	"Rowan": {"brow_style": 5, "brow_thickness": 81, "freckles": 1, "liner": 16,
		"liner_wing": 1, "stubble": 61, "lip_tint": 4},
	"Mira": {"brow_style": 1, "brow_thickness": 61, "freckles": 66, "liner": 71,
		"liner_wing": 81, "stubble": 0, "lip_tint": 2},
	"Tavi": {"brow_style": 5, "brow_thickness": 91, "freckles": 1, "liner": 21,
		"liner_wing": 1, "stubble": 51, "lip_tint": 3,
		"eyelid": 30, "brow_height": 53, "nose_length": 70, "nose_bridge": 70, "nose_tip": 50,
		"mouth_width": 65, "cupid_bow": 50, "cheek_fullness": 65, "chin_projection": 50,
		"chin_width": 58, "ear_size": 50},
}

static func shape(name: String) -> Dictionary:
	return (LOOKS.get(name, {}) as Dictionary).duplicate(true)

static func palette(name: String) -> Dictionary:
	return _packed(PALETTES.get(name, {}) as Dictionary)

static func appearance(name: String) -> Dictionary:
	return shape(name).merged(palette(name))

## The PC/3 detail values of a preset: every V3 control and detail field,
## neutral where the preset says nothing.
static func detail(name: String) -> Dictionary:
	var result := {}
	var listed: Dictionary = DETAILS.get(name, {})
	for field: String in PortraitCustomization.V3_CONTROLS + PortraitCustomization.V3_DETAILS:
		if field != "hair_finish":
			result[field] = int(listed.get(field, PortraitCustomization.DEFAULTS[field]))
	return result

## What a preset button picks: the nearest palette bytes (hair, eyes, skin)
## plus, under "colours", the concept colours for a PC/3 session.
static func pick(name: String) -> Dictionary:
	var result := _packed(NEAREST.get(name, {}) as Dictionary)
	if not result.is_empty():
		result["colours"] = (COLOURS.get(name, {}) as Dictionary).duplicate()
	return result

static func _packed(entry: Dictionary) -> Dictionary:
	if entry.is_empty():
		return {}
	return {"hair": AppearanceVariants.pack_hair(entry.style, entry.hair_color),
		"eyes": entry.eyes, "skin": entry.skin}
