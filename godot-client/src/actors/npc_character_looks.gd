class_name NpcCharacterLooks
extends RefCounted
## Story-led NPC presentation. Names are also indexed by the server's 29-byte
## display spelling, but the NPC kind and authored actor type must still match.

const FACE_FIELDS := ["facial_hair", "jaw", "cheekbones", "nose", "face_length",
	"eye_size", "eye_tilt", "eye_spacing", "nose_width", "lip_fullness", "brow_depth",
	"eyelid", "eye_style", "eye_depth", "brow_height", "nose_length", "nose_bridge",
	"nose_tip", "mouth_width", "cupid_bow", "cheek_fullness", "chin_projection",
	"chin_width", "ear_size", "brow_style", "brow_thickness", "freckles", "liner",
	"liner_wing", "stubble", "lip_tint"]
static var _archetypes: Dictionary = {}

static func face(dto: Dictionary, catalogue: Dictionary) -> Dictionary:
	if int(dto.get("kind", -1)) != 2:
		return {}
	var key := str(dto.get("name", "")).strip_edges().to_lower()
	var people: Dictionary = catalogue.get("npcs", {})
	if not people.has(key):
		key = str((catalogue.get("wireNames", {}) as Dictionary).get(key, ""))
	for row: Dictionary in people.get(key, []):
		if int(row.get("actorType", -1)) == int(dto.get("actor_type", -2)) \
				and str(row.get("model", "")) in ["luminous_female", "luminous_male"]:
			return row
	return {}

## Head identity only. Keep garment dyes, body proportions, skin/eye colours
## and existing grooming; an explicitly authored hairstyle keeps its hair dye.
static func face_appearance(profile: Dictionary, appearance: Dictionary) -> Dictionary:
	if profile.is_empty():
		return {}
	if _archetypes.is_empty():
		var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			"res://data/actors/rl_head_archetypes.json"))
		for row: Dictionary in data.get("archetypes", []):
			_archetypes[str(row.id)] = row
	var id := str(profile.get("archetype", ""))
	var source: Dictionary = _archetypes.get(id, {})
	if str(source.get("body_template", "")) != str(profile.get("model", "")):
		return {}
	var values: Dictionary = source.get("appearance_pc3", {})
	var result := {"npc_face": id}
	for field: String in FACE_FIELDS:
		result[field] = int(values.get(field, PortraitCustomization.DEFAULTS[field]))
	for field: String in ["skin_age", "hair_grey"]:
		result[field] = clampi(int(profile.get(field, 0)), 0, 100)
	if profile.has("hairStyle"):
		result["hair"] = AppearanceVariants.pack_hair(int(profile.hairStyle),
			AppearanceVariants.hair_color_index(int(appearance.get("hair", 0))))
	return result

static func find(dto: Dictionary, catalogue: Dictionary) -> Dictionary:
	if int(dto.get("kind", -1)) != 2:
		return {}
	var key := str(dto.get("name", "")).strip_edges().to_lower()
	var people: Dictionary = catalogue.get("npcs", {}) as Dictionary
	if not people.has(key):
		key = str((catalogue.get("wireNames", {}) as Dictionary).get(key, ""))
	var person: Dictionary = people.get(key, {}) as Dictionary
	if int(person.get("actorType", -1)) != int(dto.get("actor_type", -2)):
		return {}
	return person

static func present(dto: Dictionary, person: Dictionary, profile: Dictionary = {}) -> Dictionary:
	var result := dto.duplicate(false)
	if int(dto.get("kind", -1)) != 2:
		return result
	if person.is_empty() and profile.is_empty():
		return result
	# Extended native NPC spawns contain a name and type but no wardrobe bytes.
	# Supply the authored dyes here while leaving the replicated state intact.
	var appearance: Dictionary = (dto.get("appearance", {}) as Dictionary).duplicate()
	appearance.merge(person.get("appearance", {}) as Dictionary, true)
	appearance.merge(face_appearance(profile, appearance), true)
	result["appearance"] = appearance
	return result
