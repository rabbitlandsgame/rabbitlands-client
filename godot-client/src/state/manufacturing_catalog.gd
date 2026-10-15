class_name ManufacturingCatalog
extends RefCounted

## Returned when the client cannot honestly tell which slot holds the item:
## its artwork is shared and no name table has arrived to settle it. Distinct
## from -1, which means the item is simply not there.
const AMBIGUOUS := -2

var _recipes: Array[Dictionary] = []

func configure(config: Dictionary) -> void:
	_recipes.clear()
	var recipes_value: Variant = config.get("recipes", [])
	if not recipes_value is Array:
		return
	for recipe_value: Variant in recipes_value as Array:
		if recipe_value is Dictionary:
			_recipes.append((recipe_value as Dictionary).duplicate(true))

func count() -> int:
	return _recipes.size()

func recipe(index: int) -> Dictionary:
	if index < 0 or index >= _recipes.size():
		return {}
	return _recipes[index]

## What the client can see standing between the player and this recipe, and
## which slots it would spend.
##
## `names` is the server's slot-to-name table when the session has one. With
## it, an ingredient is found by identity and shared artwork stops mattering.
## Without it - an older server, or before the first table arrives - matching
## falls back to the image id, and an ingredient whose picture is shared by
## another item is refused rather than guessed at, because picking the wrong
## slot spends the wrong item.
func availability(index: int, inventory: Dictionary, known_knowledge: Array[int],
		stats: Dictionary, names: Dictionary = {}) -> Dictionary:
	var definition: Dictionary = recipe(index)
	if definition.is_empty():
		return {"selection": [], "reasons": ["Unknown recipe"]}
	var selection: Array[Dictionary] = []
	var reasons: Array[String] = []
	var ingredients_value: Variant = definition.get("ingredients", [])
	if ingredients_value is Array:
		for ingredient_value: Variant in ingredients_value as Array:
			if not ingredient_value is Dictionary:
				continue
			var ingredient: Dictionary = ingredient_value as Dictionary
			var name: String = str(ingredient.get("name", "ingredient"))
			var required: int = maxi(1, int(ingredient.get("quantity", 1)))
			var slot: int = _inventory_slot_for(inventory, names, name,
				int(ingredient.get("imageId", -1)), required, false,
				bool(ingredient.get("ambiguousImage", false)))
			if slot == AMBIGUOUS:
				reasons.append("%s shares legacy artwork; automatic selection is unavailable" % name)
				continue
			if slot < 0:
				reasons.append("Missing %s ×%d" % [name, required])
			else:
				selection.append({"slot": slot, "quantity": required})
	var tools_value: Variant = definition.get("tools", [])
	if tools_value is Array:
		for tool_value: Variant in tools_value as Array:
			if not tool_value is Dictionary:
				continue
			var tool: Dictionary = tool_value as Dictionary
			var tool_name: String = str(tool.get("name", "tool"))
			var tool_slot: int = _inventory_slot_for(inventory, names, tool_name,
				int(tool.get("imageId", -1)), 1, true,
				bool(tool.get("ambiguousImage", false)))
			if tool_slot == AMBIGUOUS:
				reasons.append("%s shares legacy artwork; tool identity is uncertain" % tool_name)
			elif tool_slot < 0:
				reasons.append("Required tool: %s" % tool_name)
	var knowledge_index: int = int(definition.get("knowledgeIndex", -1))
	if knowledge_index >= 0 and not known_knowledge.has(knowledge_index):
		reasons.append("Unread knowledge: %s" % str(definition.get("knowledge", "required book")))
	if stats.is_empty():
		reasons.append("Waiting for server statistics")
	else:
		if int(stats.get("food", 0)) <= 0:
			reasons.append("Food must be above zero")
		var mana: int = int(definition.get("mana", 0))
		if int(stats.get("ether", 0)) < mana:
			reasons.append("Need %d ethereal points" % mana)
	return {"selection": selection, "reasons": reasons}

## Each tool a recipe calls for, and whether it is to hand.
##
## `availability` folds a missing tool into a sentence among the other reasons
## a recipe is blocked, which is enough to refuse a mix and not enough to offer
## to fix it. A window that means to put a "take one from storage" button
## beside a worn-out hatchet needs the tools one at a time.
##
## `held` is false when the tool is neither carried nor worn; `ambiguous` when
## the client cannot honestly say, because the artwork is shared and no name
## table has arrived to settle it. Those are different answers and a button
## should only be offered for the first.
func tool_state(index: int, inventory: Dictionary,
		names: Dictionary = {}) -> Array[Dictionary]:
	var states: Array[Dictionary] = []
	var tools_value: Variant = recipe(index).get("tools", [])
	if not tools_value is Array:
		return states
	for tool_value: Variant in tools_value as Array:
		if not tool_value is Dictionary:
			continue
		var tool: Dictionary = tool_value as Dictionary
		var slot: int = _inventory_slot_for(inventory, names,
			str(tool.get("name", "tool")), int(tool.get("imageId", -1)), 1,
			true, bool(tool.get("ambiguousImage", false)))
		states.append({
			"name": str(tool.get("name", "tool")),
			"imageId": int(tool.get("imageId", -1)),
			"held": slot >= 0,
			"ambiguous": slot == AMBIGUOUS,
		})
	return states

## The slot holding enough of one item, by name where the server has named the
## slots and by artwork where it has not.
func _inventory_slot_for(inventory: Dictionary, names: Dictionary, name: String,
		image_id: int, quantity: int, include_equipment: bool,
		shares_artwork: bool) -> int:
	if not names.is_empty():
		var slot: int = _inventory_slot_for_name(inventory, names, name,
			quantity, include_equipment)
		# A name table that does not mention the item is a table that says the
		# player is not carrying it, which is an answer rather than a gap.
		if slot >= 0 or _names_cover(names, inventory, include_equipment):
			return slot
	if shares_artwork:
		return AMBIGUOUS
	return _inventory_slot_for_image(inventory, image_id, quantity,
		include_equipment)

## Whether the name table accounts for every slot the grid says is occupied.
## Until it does, the two packets have not met yet and the image id is still
## the better answer.
func _names_cover(names: Dictionary, inventory: Dictionary,
		include_equipment: bool) -> bool:
	for slot_value: Variant in inventory:
		var slot: int = int(slot_value)
		if slot < 0 or slot >= (44 if include_equipment else 36):
			continue
		if not names.has(slot):
			return false
	return true

func _inventory_slot_for_name(inventory: Dictionary, names: Dictionary,
		name: String, quantity: int, include_equipment: bool) -> int:
	var slots: Array = inventory.keys()
	slots.sort()
	for slot_value: Variant in slots:
		var slot: int = int(slot_value)
		if slot < 0 or slot >= (44 if include_equipment else 36):
			continue
		if str(names.get(slot, "")) != name:
			continue
		var item_value: Variant = inventory.get(slot)
		if not item_value is Dictionary:
			continue
		if int((item_value as Dictionary).get("quantity", 0)) >= quantity:
			return slot
	return -1

func _inventory_slot_for_image(inventory: Dictionary, image_id: int, quantity: int,
		include_equipment: bool) -> int:
	var slots: Array = inventory.keys()
	slots.sort()
	for slot_value: Variant in slots:
		var slot: int = int(slot_value)
		if slot < 0 or slot >= (44 if include_equipment else 36):
			continue
		var item_value: Variant = inventory.get(slot)
		if not item_value is Dictionary:
			continue
		var item: Dictionary = item_value as Dictionary
		if int(item.get("image_id", -1)) == image_id and int(item.get("quantity", 0)) >= quantity:
			return slot
	return -1
