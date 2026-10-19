extends RefCounted
## Explicit local visual profiles. Server ownership and unlocks stay authoritative.
const PATHS := {
	"moor_pony": "res://data/mounts/moor_pony.json",
	"golden_plains_horse": "res://data/mounts/golden_plains_horse.json",
	"crystalback_tortoise": "res://data/mounts/crystalback_tortoise.json",
	"rabbit": "res://data/mounts/meadow_rabbit.json",
	"jadefeather_raptor": "res://data/mounts/jadefeather_raptor.json"}
const NAMES := {"moor_pony": "Moor Pony", "golden_plains_horse": "Golden Plains Horse",
	"crystalback_tortoise":"Crystalback Tortoise", "rabbit":"Giant Meadow Rabbit",
	"jadefeather_raptor":"Jadefeather Raptor"}

static func display_name(id: String) -> String:
	return str(NAMES.get(id, "Mount"))

static func supports(id: String) -> bool:
	return PATHS.has(id)

static func read(id: String) -> Dictionary:
	if not supports(id):
		return {}
	return JSON.parse_string(FileAccess.get_file_as_string(PATHS[id]))
