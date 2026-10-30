extends SceneTree
## Catalog choices must stay playable, protocol-safe and independent of callers.

const LIBRARY := preload("res://src/ui/creation_base_library.gd")
const PC := preload("res://src/actors/portrait_customization.gd")
const VARIANTS := preload("res://src/actors/appearance_variants.gd")
var failures: Array[String] = []


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var before := JSON.stringify(registry)
	var entries: Array[Dictionary] = LIBRARY.rows(registry)
	check(entries.size() == 22, "All sixteen bodies, three studies and three qualified Humans are offered")
	var ids: Dictionary = {}
	var native_types: Dictionary = {}
	var other_race_seen := false
	var other_native_ids: Array[String] = []
	for row: Dictionary in entries:
		check(not ids.has(row.id), "Unique stable id: " + row.id)
		ids[row.id] = true
		if row.race_id == "luminous":
			check(not other_race_seen, "Human starting points precede the other races")
		else:
			other_race_seen = true
			other_native_ids.append(str(row.id))
		var look: Dictionary = row.look
		var actor_type := int(look.actor_type)
		var model_id := str(registry.actorTypes[str(actor_type)])
		var model: Dictionary = registry.models[model_id]
		check(row.race_id == model.culture and row.sex == model.gender, row.id + " uses its real playable body")
		check(look.equipment_visuals.is_empty() and look.keys().size() == 3, row.id + " contains no calling/account/equipment state")
		check(not str(row.label).is_empty() and not str(row.search_text).is_empty() and not row.hair_tags.is_empty(), row.id + " has searchable labels")
		if str(row.id).begins_with("native_"):
			native_types[actor_type] = true
		var appearance: Dictionary = look.appearance
		check(PC.validate(appearance, 3).get("ok", false), row.id + " is PC/3-valid")
		for field: String in appearance:
			check(field in LIBRARY.LEGACY_FIELDS or (actor_type in [0, 1] and field in PC.FIELDS), row.id + " only includes supported cosmetics: " + field)
		for field: String in ["skin", "eyes", "head", "shirt", "pants", "boots"]:
			check(int(appearance[field]) in range(256), row.id + " has a byte value for " + field)
		var hair := int(appearance.hair)
		check(hair >= 0 and hair < 300 and VARIANTS.hair_style(hair) in range(10) \
			and VARIANTS.hair_color_index(hair) in range(20), row.id + " has valid logical hair")
		check(VARIANTS.hair_from_wire(hair & 255, VARIANTS.hair_wire_head(hair, int(appearance.head))) == hair, row.id + " retains extended hair on the wire")
		if actor_type not in [0, 1]:
			check(appearance.size() == LIBRARY.LEGACY_FIELDS.size() and int(appearance.skin) == 0, row.id + " preserves authored race skin and has no Human fields")
		elif row.sex == "female":
			check(int(appearance.facial_hair) == 0 and not "Facial hair" in row.hair_tags, row.id + " does not offer a male beard on a female base")
		if row.race_id in ["orun", "mycelari"]:
			check(int(appearance.eyes) == 3, row.id + " preserves amber race defaults")
	for option: Dictionary in registry.creationOptions:
		check(native_types.has(int(option.actorType)), "Default exists for playable actor type %d" % option.actorType)
	var expected_other_ids: Array[String] = []
	for option: Dictionary in registry.creationOptions:
		if registry.models[str(option.model)].culture != "luminous":
			expected_other_ids.append("native_" + str(option.model))
	check(other_native_ids == expected_other_ids, "Other race pairs retain their registry order")
	check(native_types.size() == 16, "Exactly sixteen native race/sex bases")
	for sex: String in ["female", "male"]:
		var ssarathi := LIBRARY.find(entries, "native_ssarathi_" + sex)
		check(ssarathi.race_label == "Ssarathi" and "ssarathi" in ssarathi.search_text \
			and "lizardfolk" in ssarathi.search_text, "Ssarathi keeps both public search names for " + sex)
	check(LIBRARY.find(entries, "study_mira").sex == "female", "Mira is a female study")
	check(LIBRARY.find(entries, "study_rowan").sex == "male" and LIBRARY.find(entries, "study_tavi").sex == "male", "Rowan and Tavi are male studies")
	var cornrows := LIBRARY.find(entries, "human_01")
	var afro := LIBRARY.find(entries, "human_20")
	var elder := LIBRARY.find(entries, "human_34")
	check(cornrows.label == "Cornrows and low knot" and afro.label == "Rounded Afro" \
		and elder.label == "Grey beard", "Player labels contain no pilot numbers or authoring status")
	check(cornrows.sex == "female" and "Cornrows" in cornrows.hair_tags and not "Long braid" in cornrows.hair_tags, "Cornrows use their actual female module, not the fallback Long braid byte")
	check(afro.sex == "male" and "Afro" in afro.hair_tags and "Curly" in afro.hair_tags and not "Parted" in afro.hair_tags, "Afro uses its actual male module, not the fallback Parted byte")
	check("Bald" in elder.hair_tags and "Full beard" in elder.hair_tags, "Bald elder retains his full beard")
	var raw: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(LIBRARY.ARCHETYPES_PATH))
	var network := root.get_node("Network")
	var previous_protocol := int(network.call("appearance_protocol_version"))
	for version: int in [0, 1, 2, 3]:
		network.call("_set_appearance_protocol", maxi(1, version))
		var versioned: Array[Dictionary] = LIBRARY.rows(registry, version)
		for row: Dictionary in versioned:
			check(PC.validate(row.look.appearance, version).get("ok", false), "%s is valid on PC/%d" % [row.id, version])
			var creation: Dictionary = row.look.appearance.duplicate(true)
			creation.actor_type = row.look.actor_type
			check(network.call("validate_creation_appearance", creation) == OK, "%s passes real creation validation on PC/%d" % [row.id, version])
			if version < 2:
				check(row.look.appearance.size() == LIBRARY.LEGACY_FIELDS.size(), row.id + " is a legacy-only base before PC/2")
			if version > 0:
				check(PC.decode(PC.encode(row.look.appearance, version), 0) == PC.normalized(row.look.appearance),
					"%s round-trips its PC/%d cosmetic payload" % [row.id, version])
			if version >= 2 and int(row.look.actor_type) in [0, 1]:
				for field: String in PC.FIELDS:
					if PC.field_version(field) > version:
						check(int(row.look.appearance[field]) == int(PC.DEFAULTS[field]), "%s PC/%d neutralizes unsupported %s" % [row.id, version, field])
		for original: Dictionary in raw.archetypes:
			var found := LIBRARY.find(versioned, original.id)
			var expected: Dictionary = original.appearance_pc3 if version >= 3 else original.appearance_pc2
			for field: String in LIBRARY.LEGACY_FIELDS:
				check(int(found.look.appearance[field]) == int(expected.get(field, 0)), "%s PC/%d preserves the saved palette byte %s" % [original.id, version, field])
			for field: String in PC.FIELDS:
				if version >= 2 and PC.field_version(field) <= version:
					check(int(found.look.appearance[field]) == int(expected[field]), "%s PC/%d preserves saved cosmetic %s" % [original.id, version, field])
	network.call("_set_appearance_protocol", previous_protocol)
	check(JSON.stringify(registry) == before, "Catalog does not mutate the registry")
	var pristine: Array[Dictionary] = LIBRARY.rows(registry)
	var selected := LIBRARY.find(entries, "human_01")
	selected.look.appearance.hair_module = 31
	selected.look.equipment_visuals[3] = 999
	selected.hair_tags.append("Changed")
	check(LIBRARY.find(entries, "human_01") == LIBRARY.find(pristine, "human_01"), "find returns a deep copy")
	entries[0].look.appearance.skin = 99
	entries[0].hair_tags.clear()
	check(LIBRARY.rows(registry) == pristine, "Every catalog request returns independent nested data")
	check(LIBRARY.find(entries, "missing").is_empty(), "Unknown base does not select an arbitrary look")
	var incomplete := registry.duplicate(true)
	incomplete.creationOptions = [registry.creationOptions[0], registry.creationOptions[0], {"actorType": -1, "model": "missing"}]
	check(LIBRARY.rows(incomplete).size() == 3, "Missing bodies are skipped instead of inventing selectable bases")
	print("creation base library: %d choices, %d failures" % [pristine.size(), failures.size()])
	quit(0 if failures.is_empty() else 1)
