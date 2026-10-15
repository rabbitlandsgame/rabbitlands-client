extends SceneTree

const Looks := preload("res://src/actors/npc_character_looks.gd")
var failures := 0
var checks := 0

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func _init() -> void:
	var catalogue: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/npc_characters.json"))
	for key: String in catalogue["npcs"]:
		var person: Dictionary = catalogue["npcs"][key]
		var dto := {"kind": 2, "name": person["name"], "actor_type": person["actorType"],
			"appearance": {"shirt": 0, "eyes": 0}, "equipment_visuals": {0: 0}}
		expect(Looks.find(dto, catalogue) == person, key + " full identity")
		var presented := Looks.present(dto, person)
		expect(presented["appearance"] == person["appearance"], key + " receives authored dyes")
		expect(dto["appearance"] == {"shirt": 0, "eyes": 0}, key + " preserves authoritative state")
		dto["name"] = str(person["name"]).left(29)
		expect(Looks.find(dto, catalogue) == person, key + " shortened wire name")
		dto["kind"] = 1
		expect(Looks.find(dto, catalogue).is_empty(), key + " cannot outfit a player")
		dto["kind"] = 3
		expect(Looks.find(dto, catalogue).is_empty(), key + " cannot outfit a creature")
		dto["kind"] = 2
		dto["actor_type"] = -1
		expect(Looks.find(dto, catalogue).is_empty(), key + " rejects a different actor type")
	expect(Looks.find({"kind": 2, "name": "Somebody new", "actor_type": 300},
		catalogue).is_empty(), "unlisted NPC uses its ordinary presentation")
	print("NPC LOOKS: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)
