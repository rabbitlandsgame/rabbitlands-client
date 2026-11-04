extends RefCounted
## Explicit local visual profiles. Server ownership and unlocks stay authoritative.
const PATHS := {
	"moor_pony": "res://data/mounts/moor_pony.json",
	"golden_plains_horse": "res://data/mounts/golden_plains_horse.json",
	"crystalback_tortoise": "res://data/mounts/crystalback_tortoise.json",
	"rabbit": "res://data/mounts/meadow_rabbit.json",
	"jadefeather_raptor": "res://data/mounts/jadefeather_raptor.json",
	"giant_rat": "res://data/mounts/giant_rat.json",
	"cave_salamander": "res://data/mounts/cave_salamander.json",
	"lantern_stag": "res://data/mounts/lantern_stag.json",
	"cheetah": "res://data/mounts/cheetah.json"}
const NAMES := {"moor_pony": "Moor Pony", "golden_plains_horse": "Golden Plains Horse",
	"crystalback_tortoise":"Crystalback Tortoise", "rabbit":"Giant Meadow Rabbit",
	"jadefeather_raptor":"Jadefeather Raptor", "giant_rat":"Giant Rat",
	"cave_salamander":"Cave Salamander", "lantern_stag":"Lantern Stag", "cheetah":"Cheetah"}

## Each profile as parsed, once per process (avatar-worker AW-07): a mount bind
## read and parsed its profile file every time (NET-STATE-05). `read` hands
## out deep copies, so a caller may change what it gets. Main thread.
static var _parsed: Dictionary = {}
## Profile files read from disk this process (one per species).
static var file_reads := 0

static func display_name(id: String) -> String:
	return str(NAMES.get(id, "Mount"))

static func supports(id: String) -> bool:
	return PATHS.has(id)

static func read(id: String) -> Dictionary:
	if not supports(id):
		return {}
	var parsed: Variant = _parsed.get(id)
	if not parsed is Dictionary:
		file_reads += 1
		parsed = JSON.parse_string(FileAccess.get_file_as_string(PATHS[id]))
		if not parsed is Dictionary:
			return {}
		_parsed[id] = parsed
	return (parsed as Dictionary).duplicate(true)

## Forgets the parsed profiles (tests and tools that rewrite a profile file).
static func clear_cache() -> void:
	_parsed.clear()
