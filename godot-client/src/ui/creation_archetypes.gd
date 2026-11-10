class_name CreationArchetypes
extends RefCounted
## The four creation-screen callings.
##
## A calling chooses the server-owned starter inventory and gives the client a
## representative equipment silhouette: the whole starting outfit (head, body,
## legs, feet) and the gear in hand, as the server grants it.  It does not restrict skills or
## progression, and it is deliberately independent of race and sex.

const CLASSES: Array[Dictionary] = [
	{
		"id": 0,
		"key": "vanguard",
		"label": "Vanguard",
		"tagline": "Hold the line",
		"description": "A steady front-line adventurer equipped to meet danger face to face.",
		"starting_items": "Militia sword and round shield, Bloodbound Cape, Leather Helm, Studded Jack, Leather Kneecops and Banded Warboots",
		"equipment_visuals": {0: 114, 1: 106, 2: 147, 3: 134, 4: 220, 5: 209, 6: 249},
	},
	{
		"id": 1,
		"key": "ranger",
		"label": "Ranger",
		"tagline": "Choose the distant path",
		"description": "A mobile hunter who reads the land and strikes before danger closes in.",
		"starting_items": "Amberwood longbow and reusable Basic Quiver, Eagle Eye Cape, Feathered Cap, Scout Vest, Fangbelt Breeches and Furcuff Boots",
		"equipment_visuals": {0: 164, 2: 148, 3: 158, 4: 228, 5: 225, 6: 233, 8: 1},
	},
	{
		"id": 2,
		"key": "arcanist",
		"label": "Arcanist",
		"tagline": "Shape the unseen",
		"description": "A student of tomes and ether prepared to solve threats with careful magic.",
		"starting_items": "Arcane focus wand, Conjurer's Cape, Acolyte Hood, Tunic, Legguards and Boots, and 3 mana potions",
		"equipment_visuals": {0: 142, 2: 146, 3: 115, 4: 185, 5: 222, 6: 198},
	},
	{
		"id": 3,
		"key": "warden",
		"label": "Warden",
		"tagline": "Guard the old roads",
		"description": "A resilient trail-keeper who pairs practical arms with woodland craft.",
		"starting_items": "Fighting quarterstaff, Cape of Renewal (Fast Regeneration), Antler Hood, Furtrim Coat, Legguards and Boots",
		"equipment_visuals": {0: 163, 2: 142, 3: 122, 4: 176, 5: 189, 6: 205},
	},
]


static func count() -> int:
	return CLASSES.size()


static func at(index: int) -> Dictionary:
	if CLASSES.is_empty():
		return {}
	return CLASSES[posmod(index, CLASSES.size())].duplicate(true)


static func id_at(index: int) -> int:
	return int(at(index).get("id", 0))


static func loadout_at(index: int) -> Dictionary:
	return (at(index).get("equipment_visuals", {}) as Dictionary).duplicate()
