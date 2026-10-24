extends RefCounted
## Stable appearance IDs. A preset can replace albedo textures per material;
## palette and pattern layers retain the imported coat's painted detail.
const IDS := ["original", "ashen", "snow", "dappled", "striped"]
const LABELS := {"original":"Original", "ashen":"Ashen", "snow":"Snow",
	"dappled":"Woodland dapple", "striped":"Ember stripes"}
static var _catalogue: Dictionary = {}

static func catalogue() -> Dictionary:
	if _catalogue.is_empty():
		_catalogue = JSON.parse_string(FileAccess.get_file_as_string("res://data/mounts/coats.json"))
	return _catalogue

static func preset(mount_id: String, coat_id: String) -> Dictionary:
	if coat_id not in IDS or coat_id == "original": return {}
	var data := catalogue()
	var result: Dictionary = data.presets[coat_id].duplicate(true)
	result.merge(data.get("mountOverrides", {}).get(mount_id, {}).get(coat_id, {}), true)
	return result

static func valid(mount_id: String, coat_id: Variant) -> bool:
	return preload("res://src/mounts/mount_profiles.gd").supports(mount_id) and coat_id is String and coat_id in IDS
