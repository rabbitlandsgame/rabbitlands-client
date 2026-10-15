class_name SavedItemLists
extends RefCounted
## Named favorite sets. Names distinguish items that share the same icon;
## legacy image-only lists are retained, but ambiguous matches are not moved.

static func normalize(raw_lists: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for raw_name: Variant in raw_lists:
		var list_name: String = str(raw_name).strip_edges().left(48)
		if list_name.is_empty():
			continue
		var entries: Array[Dictionary] = []
		var raw: Variant = raw_lists[raw_name]
		if raw is String:
			for line: String in (raw as String).split("\n"):
				var parts: PackedStringArray = line.strip_edges().replace(",", ":").split(":")
				if parts.size() == 2 and parts[0].strip_edges().is_valid_int() and parts[1].strip_edges().is_valid_int():
					_append_valid(entries, {"image_id": int(parts[0].strip_edges()), "quantity": int(parts[1].strip_edges())})
		elif raw is Array:
			for entry: Variant in raw:
				if entry is Dictionary:
					_append_valid(entries, entry as Dictionary)
		result[list_name] = entries
	return result

static func _append_valid(entries: Array[Dictionary], entry: Dictionary) -> void:
	var image_id: int = int(entry.get("image_id", -1))
	var quantity: int = int(entry.get("quantity", 0))
	if image_id < 0 or quantity <= 0:
		return
	var clean: Dictionary = {"image_id": image_id,
		"name": str(entry.get("name", "")).strip_edges(),
		"quantity": clampi(quantity, 1, 9999999),
		"category_id": int(entry.get("category_id", -1))}
	for existing: Dictionary in entries:
		if same_item(existing, clean):
			existing["quantity"] = clean["quantity"]
			return
	entries.append(clean)

static func same_item(left: Dictionary, right: Dictionary) -> bool:
	return int(left.get("image_id", -1)) == int(right.get("image_id", -2)) \
		and str(left.get("name", "")).nocasecmp_to(str(right.get("name", ""))) == 0

static func matching_positions(entry: Dictionary, items: Dictionary,
		descriptions: Dictionary) -> Array[int]:
	var positions: Array[int] = []
	var distinct_names: Dictionary = {}
	var wanted_name: String = str(entry.get("name", ""))
	for raw_position: Variant in items:
		var position: int = int(raw_position)
		var item: Dictionary = items[raw_position] as Dictionary
		if int(item.get("image_id", -1)) != int(entry.get("image_id", -2)):
			continue
		var description: Dictionary = descriptions.get(position, {}) as Dictionary
		var item_name: String = str(description.get("name", ""))
		if not wanted_name.is_empty() and wanted_name.nocasecmp_to(item_name) != 0:
			continue
		positions.append(position)
		distinct_names[item_name.to_lower()] = true
	# Unknown duplicate icons cannot prove identity, either.
	if wanted_name.is_empty() and (distinct_names.size() > 1 \
			or (positions.size() > 1 and distinct_names.has(""))):
		positions.clear()
	positions.sort()
	return positions

static func carried_quantity(entry: Dictionary, inventory: Dictionary,
		names: Dictionary) -> int:
	var total := 0
	var wanted_name: String = str(entry.get("name", ""))
	# An unnamed legacy icon cannot establish how much of that item is carried.
	if wanted_name.is_empty():
		return 0
	for raw_slot: Variant in inventory:
		var slot: int = int(raw_slot)
		if slot < 0 or slot >= 36:
			continue
		var item: Dictionary = inventory[raw_slot] as Dictionary
		if int(item.get("image_id", -1)) == int(entry.get("image_id", -2)) \
				and wanted_name.nocasecmp_to(str(names.get(slot, ""))) == 0:
			total += int(item.get("quantity", 0))
	return total
