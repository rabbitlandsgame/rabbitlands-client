extends SceneTree

const Wardrobe := preload("res://tools/equipment_review/review_wardrobe.gd")
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var source := equipment.duplicate(true)
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tools/equipment_review/item_catalog.json"))
	var wardrobe := Wardrobe.new()
	wardrobe.configure(equipment, catalog)
	_expect(wardrobe.by_key.size() == (equipment.models as Dictionary).size(), "every registered visual retains its identity for replay")
	_expect(wardrobe.available_visual_count() == (equipment.models as Dictionary).size() - 8, "the eight legendary Sabatons are disabled")
	for piece: Dictionary in wardrobe.by_part[6]:
		_expect(str(piece.key) not in Wardrobe.DISABLED_LEGENDARY_SABATONS, "legendary Sabatons cannot be selected in the feet list")
	for piece: Dictionary in catalog.items:
		_expect(wardrobe.by_id.has(str(piece.id)), "catalog choice is available: " + str(piece.id))
		_expect(not str(piece.name).is_empty() and not (piece.stats as Dictionary).is_empty(), "item has game name and stats")
	var covered := {}
	for entry: Dictionary in CreationArchetypes.CLASSES:
		wardrobe.use_set(entry.equipment_visuals)
		_expect(wardrobe.visuals() == entry.equipment_visuals, "starter set is complete including weapons and quiver")
		for part: int in wardrobe.selected:
			covered[str(wardrobe.piece_at(part).key)] = true
	var sets: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tools/equipment_review/review_sets.json"))
	for entry: Dictionary in sets.sets:
		wardrobe.use_set(entry.visuals)
		if str(entry.name) == "Phoenix legendary set" or str(entry.name).begins_with("Audit Legendary "):
			var foot := wardrobe.piece_at(6)
			_expect(int(foot.visual) in range(208, 216) and str(foot.name).ends_with(" Boots"), "legendary outfit uses matching Boots: " + str(entry.name))
		for part: String in entry.visuals:
			_expect(wardrobe.visuals().get(int(part), -1) == int(entry.visuals[part]), "set resolves " + str(entry.name))
			covered["%s:%d" % [part, int(entry.visuals[part])]] = true
	# Every active armor design is represented; Sabatons remain disabled.
	for key: String in equipment.models:
		if key.get_slice(":", 0) in ["3", "4", "5", "6"] and key not in Wardrobe.DISABLED_LEGENDARY_SABATONS:
			_expect(covered.has(key), "every armour design appears in a set: " + key)
	var sabatons: Dictionary = wardrobe.by_key["6:107"]
	wardrobe.restore([sabatons])
	_expect(wardrobe.visuals().get(6) == 107, "historical notes can still replay their original Sabatons")
	wardrobe.use_set(CreationArchetypes.CLASSES[0].equipment_visuals)
	var original := wardrobe.snapshot()
	wardrobe.selected_part = 5
	wardrobe.cycle_piece(1)
	_expect(wardrobe.selected_part == 6, "Down selects the next equipped slot")
	wardrobe.cycle_piece(1)
	_expect(wardrobe.selected_part == 0, "selection wraps and skips empty slots")
	wardrobe.cycle_piece(-1)
	_expect(wardrobe.selected_part == 6, "Up wraps to the last equipped slot")
	wardrobe.disabled[5] = true
	wardrobe.cycle_piece(-1)
	_expect(wardrobe.selected_part == 5, "hidden equipped pieces remain inspectable")
	wardrobe.disabled.erase(5)
	_expect(wardrobe.snapshot() == original, "inspecting does not change the loadout")
	wardrobe.selected_part = 8
	wardrobe.cycle_piece(1)
	_expect(wardrobe.selected_part == 0, "Down from an empty slot selects the first piece")
	wardrobe.selected_part = 8
	wardrobe.cycle_piece(-1)
	_expect(wardrobe.selected_part == 6, "Up from an empty slot selects the last piece")
	wardrobe.use_set({})
	wardrobe.cycle_piece(1)
	_expect(wardrobe.selected.is_empty(), "empty outfits are safe to navigate")
	wardrobe.restore(original)
	var torso: Dictionary = wardrobe.by_key["5:192"]
	wardrobe.choose(5, str(torso.id))
	_expect(wardrobe.visuals()[5] == 192 and wardrobe.visuals()[4] == 220, "cross-set replacement changes only its slot")
	wardrobe.disabled[5] = true
	_expect(not wardrobe.visuals().has(5) and wardrobe.piece_at(5).id == torso.id, "hiding keeps the selected item")
	var mixed := wardrobe.snapshot()
	wardrobe.use_set({})
	wardrobe.restore(mixed)
	_expect(wardrobe.snapshot() == mixed and not wardrobe.visuals().has(5), "snapshot restores replacements and visibility")
	wardrobe.disabled[5] = false
	_expect(wardrobe.visuals()[5] == 192, "reenabling restores the replacement")
	wardrobe.restore(original)
	_expect(wardrobe.snapshot() == original, "restoring a set removes replacements")
	wardrobe.choose(5, "")
	_expect(wardrobe.piece_at(5).is_empty() and not wardrobe.visuals().has(5), "empty slot removes only that piece")
	_expect(equipment == source, "previewing never modifies the actor registry")
	print("EQUIPMENT_WARDROBE_OK" if failures == 0 else "EQUIPMENT_WARDROBE_FAILED: %d" % failures)
	quit(0 if failures == 0 else 1)


func _expect(condition: bool, label: String) -> void:
	if not condition:
		failures += 1
		push_error(label)
