class_name NpcCharacterLooks
extends RefCounted
## Story-led NPC presentation. Names are also indexed by the server's 29-byte
## display spelling, but the NPC kind and authored actor type must still match.

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

static func present(dto: Dictionary, person: Dictionary) -> Dictionary:
	var result := dto.duplicate(false)
	if person.is_empty():
		return result
	# Extended native NPC spawns contain a name and type but no wardrobe bytes.
	# Supply the authored dyes here while leaving the replicated state intact.
	var appearance: Dictionary = (dto.get("appearance", {}) as Dictionary).duplicate()
	appearance.merge(person.get("appearance", {}) as Dictionary, true)
	result["appearance"] = appearance
	return result
