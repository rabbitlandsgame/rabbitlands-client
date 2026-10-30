extends RefCounted
## Preview-only loadout state. The source sets and actor registry stay immutable.

var by_part: Dictionary = {}
var by_id: Dictionary = {}
var by_key: Dictionary = {}
var selected: Dictionary = {}
var disabled: Dictionary = {}
var selected_part := 5


func configure(equipment: Dictionary, catalog: Dictionary) -> void:
	by_part.clear()
	by_id.clear()
	by_key.clear()
	var models: Dictionary = equipment.get("models", {})
	for raw: Dictionary in catalog.get("items", []):
		if models.has(str(raw.get("key", ""))):
			_add(raw.duplicate(true))
	# Registry-only visuals (e.g. colour capes) remain inspectable, with an
	# explicit absence of game facts instead of borrowing another item's stats.
	for key: String in models:
		if by_key.has(key):
			continue
		var model: Dictionary = models[key]
		var label := str(model.get("name", ""))
		if label.is_empty():
			label = "%s %s" % [str((equipment.get("parts", {}) as Dictionary).get(key.get_slice(":", 0), {}).get("name", "Piece")).capitalize(), key.get_slice(":", 1)]
		_add({"id": "visual:" + key, "key": key, "part": int(key.get_slice(":", 0)),
			"visual": int(key.get_slice(":", 1)), "name": label, "canonical_name": label,
			"image_id": -1, "stats": {}, "description": "This client visual has no matching equippable item definition.",
			"visual_only": true})
	for part: int in by_part:
		(by_part[part] as Array).sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			return str(a.name).naturalnocasecmp_to(str(b.name)) < 0)


func _add(piece: Dictionary) -> void:
	var part := int(piece.part)
	by_id[str(piece.id)] = piece
	if not by_part.has(part):
		by_part[part] = []
	(by_part[part] as Array).append(piece)
	if not by_key.has(str(piece.key)):
		by_key[str(piece.key)] = piece


func use_set(visuals: Dictionary) -> void:
	selected.clear()
	disabled.clear()
	for raw: Variant in visuals:
		var part := int(raw)
		var piece: Dictionary = by_key.get("%d:%d" % [part, int(visuals[raw])], {})
		if not piece.is_empty():
			selected[part] = str(piece.id)
	if piece_at(selected_part).is_empty() and not selected.is_empty():
		selected_part = int(selected.keys()[0])


func choose(part: int, id: String) -> void:
	selected_part = part
	if id.is_empty():
		selected.erase(part)
	elif by_id.has(id) and int((by_id[id] as Dictionary).part) == part:
		selected[part] = id
		disabled.erase(part)


func piece_at(part: int) -> Dictionary:
	return by_id.get(str(selected.get(part, "")), {})


func visuals() -> Dictionary:
	var result := {}
	for part: int in selected:
		if not bool(disabled.get(part, false)):
			result[part] = int(piece_at(part).visual)
	return result


func snapshot() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var parts := selected.keys()
	parts.sort()
	for part: int in parts:
		var piece := piece_at(part).duplicate(true)
		piece["enabled"] = not bool(disabled.get(part, false))
		result.append(piece)
	return result


func restore(pieces: Array) -> void:
	selected.clear()
	disabled.clear()
	for piece: Dictionary in pieces:
		var id := str(piece.get("id", ""))
		if not by_id.has(id):
			id = str((by_key.get(str(piece.get("key", "")), {}) as Dictionary).get("id", ""))
		if by_id.has(id):
			var part := int((by_id[id] as Dictionary).part)
			selected[part] = id
			disabled[part] = not bool(piece.get("enabled", true))
