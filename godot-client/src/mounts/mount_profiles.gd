extends RefCounted
## Explicit local visual profiles. Server ownership and unlocks stay authoritative.
const PATHS := {
	"moor_pony": "res://data/mounts/moor_pony.json",
	"golden_plains_horse": "res://data/mounts/golden_plains_horse.json"}

static func supports(id: String) -> bool:
	return PATHS.has(id)

static func read(id: String) -> Dictionary:
	if not supports(id):
		return {}
	return JSON.parse_string(FileAccess.get_file_as_string(PATHS[id]))
