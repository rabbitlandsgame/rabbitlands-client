extends SceneTree
## Production name/type dispatch, exact High identities, cosmetic isolation,
## and short wire names. No native mesh load is needed for these checks.
var failures := 0
var checks := 0
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
func read(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary
func enhanced(name: String, kind: int) -> Dictionary:
	var bytes := PackedByteArray()
	bytes.resize(28)
	bytes[27] = kind
	bytes.append_array(name.to_ascii_buffer())
	bytes.append(0)
	return EloriaProtocol.decode_actor(bytes,true)
func _init() -> void:
	_run.call_deferred()
func _run() -> void:
	var faces := read("res://data/actors/npc_human_faces.json")
	var cast := read("res://data/actors/npc_characters.json")
	var registry := read("res://data/actors/models.json")
	var main = (load("res://src/app/main.gd") as Script).new()
	main.models = registry.models
	main.actor_type_models = registry.actorTypes
	main.npc_looks = registry.npcLooks
	main.npc_characters = cast
	main.npc_human_faces = faces
	for name: String in ["Elen Reed","Liora Reed","Fenna Ash","Ada Vale"]:
		var packet := enhanced(name,2)
		expect(packet.name == name and packet.guild_tag.is_empty(),name + " enhanced full name")
		expect(not NpcCharacterLooks.face(packet,faces).is_empty(),name + " packet resolves its face")
	var player := enhanced("Wayfarer RLG",1)
	expect(player.name == "Wayfarer" and player.guild_tag == "RLG","player guild fallback retained")
	var shapes := {}
	var count := 0
	for key: String in faces.npcs:
		for row: Dictionary in faces.npcs[key]:
			count += 1
			var raw := {"actor_id":100+count,"name":row.name,"kind":2,"actor_type":row.actorType,
				"scale":0.65 if key == "liora reed" else 1.0,"x":57,"y":79,"rotation":0,
				"appearance":{"skin":2,"eyes":3,"hair":107,"shirt":5,"pants":4,"boots":1,"head":0},
				"equipment_visuals":{5:209}}
			var before: Dictionary = raw.duplicate(true)
			var found := NpcCharacterLooks.face(raw, faces)
			expect(found == row, key + " exact identity")
			expect(main._model_for_actor(raw) == row.model, key + " production model")
			var shown: Dictionary = main._presentation_dto(raw)
			var person := NpcCharacterLooks.find(raw, cast)
			var wardrobe: Dictionary = raw.appearance.merged(person.get("appearance", {}), true)
			for part: String in ["skin","eyes","shirt","pants","boots","head"]:
				expect(shown.appearance[part] == wardrobe[part], key + " keeps " + part)
			expect(AppearanceVariants.hair_color_index(int(shown.appearance.hair)) ==
				AppearanceVariants.hair_color_index(int(wardrobe.hair)), key + " keeps hair colour")
			for field: String in ["scale","x","y","actor_type","kind","actor_id"]:
				expect(shown[field] == raw[field], key + " cosmetic " + field)
			expect(raw == before, key + " preserves replicated state")
			var sex := str(row.model).trim_prefix("luminous_")
			var face := RLHeadPortraitMap.face(shown.appearance, sex)
			var preset := RLHeadAppearance.from_preset(row.archetype)
			expect(face.sex == sex and face.preset == row.archetype, key + " updated identity")
			expect(face.controls == preset.controls, key + " exact updated face controls")
			expect(not shown.appearance.has("rl_head"), key + " retains graphics quality policy")
			expect(RLHeadPortraitMap.face(shown.appearance, sex, true).preset.is_empty(),
				key + " native hair keeps the native skull")
			shapes[row.archetype] = true
			var short := raw.duplicate(true)
			short.name = str(row.name).to_ascii_buffer().slice(0,29).get_string_from_ascii()
			expect(NpcCharacterLooks.face(short,faces) == row, key + " wire alias")
			for kind: int in [1,3,4]:
				var wrong := raw.duplicate(true)
				wrong.kind = kind
				expect(NpcCharacterLooks.face(wrong,faces).is_empty(), key + " rejects other actor kind")
				var other: Dictionary = main._presentation_dto(wrong)
				expect(other.appearance == raw.appearance, key + " other kind keeps its choices")
			short.actor_type = -123
			expect(NpcCharacterLooks.face(short,faces).is_empty(), key + " type mismatch")
	for person: Dictionary in cast.npcs.values():
		var raw := {"kind":2,"name":person.name,"actor_type":person.actorType}
		var human := str(person.model) in ["luminous_male","luminous_female"]
		expect(not NpcCharacterLooks.face(raw,faces).is_empty() == human,
			str(person.name) + " covers Humans and retains other peoples")
	expect(count == 94 and shapes.size() == 36, "complete individual face coverage")
	expect(NpcCharacterLooks.face({"kind":2,"name":"Unknown","actor_type":1},faces).is_empty(),
		"unknown legacy NPC is never claimed")
	# Free Main's unattached Node-valued initializers without starting the game.
	for property: Dictionary in main.get_property_list():
		if int(property.usage) & PROPERTY_USAGE_SCRIPT_VARIABLE:
			var value: Variant = main.get(str(property.name))
			if value is Node and is_instance_valid(value) and value != main and value.get_parent() == null:
				value.free()
	main.free()
	print("NPC HUMAN FACES: %d profiles, %d structures, %d checks, %d failures" % [count,shapes.size(),checks,failures])
	quit(1 if failures else 0)
