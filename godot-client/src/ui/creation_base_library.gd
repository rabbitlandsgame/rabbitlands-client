class_name CreationBaseLibrary
extends RefCounted
## Cosmetic starting points for creation. No calling, account or inventory data.

const PC := preload("res://src/actors/portrait_customization.gd")
const VARIANTS := preload("res://src/actors/appearance_variants.gd")
const CHOICES := preload("res://src/actors/appearance_choices.gd")
const STUDIES := preload("res://src/actors/human_portrait_presets.gd")
const HEAD_MAP := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const ARCHETYPES_PATH := "res://data/actors/rl_head_archetypes.json"
const LEGACY_FIELDS := ["skin", "hair", "eyes", "head", "shirt", "pants", "boots"]
const STUDY_SEX := {"Mira": "female", "Rowan": "male", "Tavi": "male"}
const PUBLIC_LABELS := {"human_01": "Cornrows and low knot", "human_20": "Rounded Afro", "human_34": "Grey beard"}


static func rows(registry: Dictionary, protocol_version: int = 3) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var bodies: Dictionary = {}
	var models: Dictionary = registry.get("models", {})
	var seen: Dictionary = {}
	for option: Dictionary in registry.get("creationOptions", []):
		var model_id := str(option.get("model", ""))
		var model: Dictionary = models.get(model_id, {})
		var race := str(model.get("culture", ""))
		var sex := str(model.get("gender", ""))
		var actor_type := int(option.get("actorType", -1))
		if race.is_empty() or sex not in ["female", "male"] or actor_type < 0 \
				or bool(model.get("retired", false)) or seen.has(actor_type):
			continue
		seen[actor_type] = true
		var label := str(option.get("label", model_id)).trim_suffix(" Female").trim_suffix(" Male")
		if race == "ssarathi":
			label = "Ssarathi"
		bodies[model_id] = {"race": race, "label": label, "sex": sex, "actor_type": actor_type}
		var source := _native_appearance(race, sex)
		result.append(_row("native_" + model_id, label + " " + sex.capitalize(),
			bodies[model_id], _appearance(source, race == "luminous", protocol_version)))
	for study: String in STUDY_SEX:
		var sex := str(STUDY_SEX[study])
		var body: Dictionary = bodies.get("luminous_" + sex, {})
		if body.is_empty():
			continue
		var source: Dictionary = STUDIES.shape(study)
		var palette: Dictionary = STUDIES.pick(study)
		var colours: Dictionary = palette.get("colours", {})
		palette.erase("colours")
		source.merge(palette, true)
		if protocol_version >= 3:
			source.merge(STUDIES.detail(study), true)
			source.merge(colours, true)
		result.append(_row("study_" + study.to_lower(), study, body,
			_appearance(source, true, protocol_version)))
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ARCHETYPES_PATH))
	if parsed is Dictionary:
		for entry: Dictionary in parsed.get("archetypes", []):
			var id := str(entry.get("id", ""))
			var body: Dictionary = bodies.get(str(entry.get("body_template", "")), {})
			if id.is_empty() or body.is_empty() or body.race != "luminous" \
					or str(entry.get("sex", "")) != str(body.sex):
				continue
			var source: Dictionary = entry.get("appearance_pc3" if protocol_version >= 3 else "appearance_pc2", {})
			if source.is_empty():
				continue
			var source_label := str(entry.get("label", id))
			var label := str(PUBLIC_LABELS.get(id, source_label.trim_suffix(" target")))
			var row := _row(id, label, body,
				_appearance(source, true, protocol_version))
			row.search_text += " " + id.to_lower() + " " + source_label.to_lower()
			row.search_text += " " + str(entry.get("age_band", "")).replace("_", " ")
			for tag: Variant in entry.get("tags", []):
				row.search_text += " " + str(tag).to_lower()
			result.append(row)
	return result


static func find(entries: Array[Dictionary], id: String) -> Dictionary:
	for entry: Dictionary in entries:
		if str(entry.get("id", "")) == id:
			return entry.duplicate(true)
	return {}


static func _native_appearance(race: String, sex: String) -> Dictionary:
	# Race-default skin preserves authored markings. Native crests and mushroom
	# caps start without an added hairstyle; the editor still offers fitted hair.
	var style := 3 if sex == "female" else 1
	if race in ["ssarathi", "mycelari"]:
		style = 0
	return {"skin": 1 if race == "luminous" else 0,
		"hair": VARIANTS.pack_hair(style, 1), "eyes": 3 if race in ["orun", "mycelari"] else 2,
		"head": 0, "shirt": 0, "pants": 0, "boots": 0,
		"hair_module": 1 if race == "luminous" else 0}


static func _appearance(source: Dictionary, human: bool, version: int) -> Dictionary:
	var result := {"skin": 0, "hair": VARIANTS.pack_hair(0, 0), "eyes": 2,
		"head": 0, "shirt": 0, "pants": 0, "boots": 0}
	for field: String in LEGACY_FIELDS:
		if source.has(field):
			result[field] = int(source[field])
	if human and version >= 2:
		var normalized: Dictionary = PC.normalized(source)
		for field: String in PC.FIELDS:
			result[field] = int(normalized[field]) if PC.field_version(field) <= clampi(version, 0, 3) \
				else int(PC.DEFAULTS[field])
	return result


static func _row(id: String, label: String, body: Dictionary, appearance: Dictionary) -> Dictionary:
	var tags := _hair_tags(appearance, str(body.sex), str(body.race) == "luminous")
	var words: Array[String] = [label, str(body.label), str(body.race), str(body.sex)]
	words.append_array(tags)
	if body.race == "ssarathi":
		words.append("Lizardfolk")
	return {"id": id, "label": label, "race_id": str(body.race), "race_label": str(body.label),
		"sex": str(body.sex), "hair_tags": tags, "search_text": " ".join(PackedStringArray(words)).to_lower(),
		"look": {"actor_type": int(body.actor_type), "appearance": appearance.duplicate(true),
			"equipment_visuals": {}}}


static func _hair_tags(appearance: Dictionary, sex: String, human: bool) -> Array[String]:
	var style := VARIANTS.hair_style(int(appearance.get("hair", 0)))
	var actual := HEAD_MAP.hair(appearance, sex) if human else ""
	var tags: Array[String] = []
	match actual:
		"rounded_afro": tags.assign(["Short", "Curly", "Afro"])
		"cornrows_low_knot": tags.assign(["Tied", "Braided", "Cornrows"])
		"rowan_shag": tags.assign(["Short", "Wavy", "Shag"])
		"mira_bun": tags.assign(["Tied", "Bun"])
		_:
			var categories := {0: ["Bald"], 1: ["Short"], 2: ["Long"], 3: ["Tied"],
				4: ["Short"], 5: ["Short"], 6: ["Long", "Tied"], 7: ["Long", "Tied", "Braided"],
				8: ["Tied"], 9: ["Short"]}
			tags.assign(categories.get(style, []))
			for choice: Dictionary in CHOICES.options("hair"):
				if int(choice.id) == style and not tags.has(str(choice.label)):
					tags.append(str(choice.label))
	var beard := int(appearance.get("facial_hair", 0))
	if human and sex == "male" and beard > 0:
		tags.append("Facial hair")
		tags.append(["", "Stubble", "Moustache", "Goatee", "Short beard", "Full beard"][clampi(beard, 0, 5)])
	return tags
