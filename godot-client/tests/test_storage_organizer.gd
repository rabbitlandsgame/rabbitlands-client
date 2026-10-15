extends SceneTree
## The stored-items organizer: sub-filtering one storage category by the type
## of item, and ordering it by name, strength, or rarity.
##
## Withdrawal is by server position, so the point every check comes back to is
## that reordering and filtering never disturb the position carried as an
## item's metadata - a sorted list that withdrew the wrong item would be worse
## than no sorting at all.

var failures := 0

## Four stored rows in one category, deliberately in no useful order: two
## torso pieces and two greaves, with strength and rarity disagreeing so each
## sort has to prove itself.
const ROWS: Array[Dictionary] = [
	{"position": 0, "image_id": 10, "quantity": 1, "strength": 5, "rarity": 4,
		"name": "Cotton Shirt", "subtype": "Torso"},
	{"position": 1, "image_id": 11, "quantity": 2, "strength": 40, "rarity": 0,
		"name": "Bronze Greaves", "subtype": "Legs"},
	{"position": 2, "image_id": 12, "quantity": 3, "strength": 22, "rarity": 2,
		"name": "Augmented Plate", "subtype": "Torso"},
	{"position": 3, "image_id": 13, "quantity": 4, "strength": 22, "rarity": 1,
		"name": "Zircon Greaves", "subtype": "Legs"},
]


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame

	var app_state: Node = root.get_node("AppState")
	var items: Dictionary = {}
	var described: Dictionary = {}
	for row: Dictionary in ROWS:
		var position: int = int(row["position"])
		items[position] = {"image_id": int(row["image_id"]),
			"quantity": int(row["quantity"]), "position": position}
		described[position] = row
	app_state.storage = {"open": true, "category_id": 4, "items": items,
		"described": described, "text": "",
		"categories": [{"id": 4, "name": "Armor"}]}
	main.call("_sync_storage")
	await process_frame

	var list: ItemList = main.get_node("%StorageItems") as ItemList
	var type_picker: OptionButton = main.get_node("%StorageType") as OptionButton
	var sort_picker: OptionButton = main.get_node("%StorageSort") as OptionButton

	# The Type dropdown is built from what this category actually holds.
	_expect(_option_labels(type_picker) == ["All types", "Legs", "Torso"],
		"the type filter offers exactly the types in this category")
	_expect(not type_picker.disabled, "a mixed category can be filtered")
	_expect(_option_labels(sort_picker) == ["Name", "Strength", "Rarity"],
		"the sort control offers name, strength and rarity")

	# Default order is alphabetical, and every row still carries its position.
	_expect(_names(list) == ["Augmented Plate", "Bronze Greaves",
		"Cotton Shirt", "Zircon Greaves"], "the list starts sorted by name")
	_expect(_positions(list) == [2, 1, 0, 3],
		"sorting by name keeps each row's own server position")

	# Strength: best first, and where two rows tie the name breaks it.
	main.call("_on_storage_sort_selected", 1)
	_expect(_names(list) == ["Bronze Greaves", "Augmented Plate",
		"Zircon Greaves", "Cotton Shirt"], "strength sorts strongest first")
	_expect(_positions(list) == [1, 2, 3, 0],
		"sorting by strength keeps each row's own server position")
	_expect(str(list.get_item_text(0)).contains("strength 40"),
		"a strength-sorted row shows the strength it was ordered by")

	# Rarity: rarest first, independent of strength.
	main.call("_on_storage_sort_selected", 2)
	_expect(_names(list) == ["Cotton Shirt", "Augmented Plate",
		"Zircon Greaves", "Bronze Greaves"], "rarity sorts rarest first")
	_expect(_positions(list) == [0, 2, 3, 1],
		"sorting by rarity keeps each row's own server position")
	_expect(str(list.get_item_text(0)).contains("Legendary"),
		"a rarity-sorted row names the tier it was ordered by")

	# Sub-filtering: one type of the category, order preserved within it.
	var torso_index: int = _option_index(type_picker, "Torso")
	main.call("_on_storage_type_selected", torso_index)
	_expect(_names(list) == ["Cotton Shirt", "Augmented Plate"],
		"filtering to Torso hides the greaves")
	_expect(_positions(list) == [0, 2],
		"a filtered row still carries its unfiltered server position")

	# Filter and sort compose rather than override one another.
	main.call("_on_storage_sort_selected", 1)
	_expect(_names(list) == ["Augmented Plate", "Cotton Shirt"],
		"the type filter survives changing the sort")
	main.call("_on_storage_type_selected", 0)
	_expect(_names(list).size() == 4, "All types restores the whole category")

	# A category holding one type has nothing to filter, and the stale filter
	# must not survive into it and blank the list.
	main.call("_on_storage_type_selected", _option_index(type_picker, "Legs"))
	var single: Dictionary = {}
	var single_described: Dictionary = {}
	single[7] = {"image_id": 20, "quantity": 5, "position": 7}
	single_described[7] = {"position": 7, "image_id": 20, "quantity": 5,
		"strength": 0, "rarity": 0, "name": "Sunflower", "subtype": "Resource"}
	app_state.storage["items"] = single
	app_state.storage["described"] = single_described
	main.call("_sync_storage")
	await process_frame
	_expect(type_picker.disabled, "a single-type category disables the filter")
	_expect(_names(list) == ["Sunflower"],
		"a stale filter never empties the category a player opens next")

	# An undescribed shelf (a server that does not send the organizer) must
	# still list its rows the way it always did.
	app_state.storage["described"] = {}
	main.call("_sync_storage")
	await process_frame
	_expect(list.item_count == 1 and _positions(list) == [7],
		"an undescribed row still lists and keeps its position")

	# The tutorial names the resource to deposit. The backpack column must
	# use the same server identity as Inventory, including shared artwork.
	app_state.inventory = {4:{"image_id":88,"quantity":3}}
	app_state.inventory_names = {4:"Reed"}
	main.call("_sync_storage")
	var backpack: ItemList = main.get_node("%StorageInventory")
	_expect(_names(backpack)==["Reed"] and _positions(backpack)==[4],
		"deposit names come from the server and retain their inventory slots")
	app_state.inventory_names.clear()
	main.call("_sync_storage")
	_expect(backpack.get_item_text(0).contains("item #88"),
		"older servers retain an honest unnamed-item fallback")
	main.queue_free()
	if failures == 0:
		print("storage organizer tests passed")
	quit(failures)


func _names(list: ItemList) -> Array:
	var found: Array = []
	for index: int in range(list.item_count):
		found.append(str(list.get_item_text(index)).split("  ×")[0])
	return found


func _positions(list: ItemList) -> Array:
	var found: Array = []
	for index: int in range(list.item_count):
		found.append(int(list.get_item_metadata(index)))
	return found


func _option_labels(picker: OptionButton) -> Array:
	var found: Array = []
	for index: int in range(picker.item_count):
		found.append(str(picker.get_item_text(index)))
	return found


func _option_index(picker: OptionButton, label: String) -> int:
	for index: int in range(picker.item_count):
		if str(picker.get_item_text(index)) == label:
			return index
	return -1


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("FAIL: " + message)
