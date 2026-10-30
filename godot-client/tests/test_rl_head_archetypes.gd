extends SceneTree
## Focused data/codec checks. No NPC or creation Randomize adoption occurs here.

const PC = preload("res://src/actors/portrait_customization.gd")
const COLOURS = preload("res://src/actors/appearance_colours.gd")
const MAP = preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var path := args[0] if not args.is_empty() else "res://data/actors/rl_head_archetypes.json"
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if raw is not Dictionary:
		push_error("Cannot read archetype library: " + path)
		quit(1)
		return
	var rows: Array = raw.get("archetypes", [])
	check(rows.size() == 3, "Selected library must contain the three qualified human bases")
	var ids: Dictionary = {}
	for row: Dictionary in rows:
		var id: String = row.get("id", "")
		check(not id.is_empty() and not ids.has(id), "Missing or duplicate archetype id " + id)
		ids[id] = true
		check(id in ["human_01", "human_20", "human_34"], "Unaccepted pilot included: " + id)
		var sex: String = row.get("sex", "")
		check(sex in ["female", "male"], id + " invalid sex")
		check(row.get("body_template", "") == "luminous_" + sex, id + " body mismatch")
		for version: int in [2, 3]:
			var appearance: Dictionary = row.get("appearance_pc%d" % version, {})
			check(not appearance.is_empty(), id + " missing PC/%d" % version)
			check(PC.validate(appearance, version).get("ok", false), id + " invalid PC/%d" % version)
			check(PC.decode(PC.encode(appearance, version), 0) == PC.normalized(appearance),
				id + " PC/%d roundtrip" % version)
			var canonical := COLOURS.canonical(appearance, sex)
			check(canonical.size() == appearance.size(), id + " incomplete canonical fields")
			# JSON numbers are floats; canonical fields can be ints. Compare their
			# values individually instead of Dictionary's type-sensitive equality.
			for field: String in appearance:
				check(canonical.get(field) == appearance[field], id + " stale field " + field)
			var face := MAP.face(appearance, sex)
			check(face.sex == sex, id + " decoded head sex")
			for control: String in face.controls:
				check(is_finite(face.control(control)) and absf(face.control(control)) <= 1.0,
					id + " invalid head control " + control)
		var fallback: Dictionary = row.get("appearance_pc2", {})
		for field: String in PC.V3_FIELDS:
			check(fallback.get(field) == PC.DEFAULTS[field], id + " unsupported fallback field " + field)
		check(not str(row.get("hair_gap", "")).is_empty(), id + " missing grooming review note")
		var lab := preload("res://prototypes/rl_heads/rl_head_lab.gd").new()
		lab.face = RLHeadAppearance.from_preset(id)
		lab._sex = sex
		var combined: Dictionary = lab._actor_appearance()
		check(combined.get("shirt_hue") == row.appearance_pc3.get("shirt_hue"), id + " public lab keeps garment colours")
		check(combined.get("rl_head", {}).get("preset") == id, id + " public lab keeps the selected raw face")
		lab.free()
		if row.has("hair_module"):
			var module: Dictionary = row.hair_module
			var app: Dictionary = row.appearance_pc3
			check(MAP.hair(app, sex) == module.name, id + " PC/3 hairstyle selection")
			check(MAP.HAIR_MODULES.has(int(module.id)), id + " hairstyle registry entry")
			var face := MAP.face(app, sex)
			var inverse := MAP.to_portrait_fields(face, sex)
			check(inverse.get("hair_module") == module.id, id + " hairstyle inverse mapping")
			check(is_zero_approx(face.hair_length) and is_zero_approx(face.hair_volume)
				and face.hair_detail == 50, id + " authored neutral grooming")
	for id: String in ["human_08", "human_14", "human_27"]:
		check(not RLHeadAppearance.presets().has(id), "Unaccepted raw preset included: " + id)
	for module_id: int in [6, 7, 8]:
		check(not MAP.HAIR_MODULES.has(module_id), "Unaccepted hairstyle registered")
	print("RL selected archetypes: %d presets, %d failures" % [rows.size(), failures.size()])
	quit(0 if failures.is_empty() else 1)
