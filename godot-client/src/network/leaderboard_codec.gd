extends RefCounted
## The podium uses integer strings so large XP values survive JSON decoding.

static func decode(payload: PackedByteArray) -> Dictionary:
	var invalid := {"type": "invalid", "error": "leaderboard_state"}
	var value: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not value is Dictionary:
		return invalid
	if value.get("version") != 1 or not value.get("categories") is Array or not value.get("rows") is Array or not value.get("self") is Dictionary:
		return {"type":"invalid", "error":"leaderboard_shape"}
	if not value.get("category") is String or not _integer(value.get("days"), 0) or int(value.days) not in [0, 30] or not _integer(value.get("request_id"), 0):
		return {"type":"invalid", "error":"leaderboard_selection"}
	if value.categories.size() > 64 or value.rows.size() > 10:
		return invalid
	var keys: Array[String] = []
	for raw: Variant in value.categories:
		if not raw is Dictionary:
			return invalid
		for field: String in ["key", "label", "group", "unit", "icon"]:
			if not raw.get(field) is String or str(raw[field]).is_empty():
				return invalid
		if raw.key in keys:
			return {"type":"invalid", "error":"leaderboard_duplicate_category"}
		keys.append(raw.key)
	if value.category not in keys:
		return invalid
	var expected_rank := 1
	for raw: Variant in value.rows:
		if not _valid_row(raw) or raw.get("rank") != expected_rank or not raw.get("is_self") is bool:
			return {"type":"invalid", "error":"leaderboard_row", "rank":expected_rank}
		if raw.has("portrait") and not _valid_portrait(raw.portrait):
			return {"type":"invalid", "error":"leaderboard_portrait"}
		expected_rank += 1
	if not _valid_row(value.self):
		return {"type":"invalid", "error":"leaderboard_personal_row"}
	return {"type": "leaderboard", "data": value}

static func _valid_row(raw: Variant) -> bool:
	if not raw is Dictionary or not raw.get("name") is String or not raw.get("value") is String:
		return false
	var score: String = raw.value
	if not score.is_valid_int() or score.begins_with("-") or score.begins_with("+"):
		return false
	var rank: Variant = raw.get("rank")
	if rank != null and not _integer(rank, 1):
		return false
	var level: Variant = raw.get("level")
	return level == null or _integer(level, 0)

static func _integer(value: Variant, minimum: int) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and value >= minimum and floor(float(value)) == value

static func _valid_portrait(value: Variant) -> bool:
	if not value is Dictionary or not _integer(value.get("actor_type"), 0) or value.actor_type > 1023:
		return false
	if not value.get("appearance") is Dictionary or not value.get("equipment_visuals") is Dictionary:
		return false
	for key: Variant in value.appearance:
		if key not in ["skin", "hair", "eyes", "head", "shirt", "pants", "boots"] or not _integer(value.appearance[key], 0):
			return false
		if value.appearance[key] > (299 if key == "hair" else 255):
			return false
	if value.equipment_visuals.size() > 32:
		return false
	for key: Variant in value.equipment_visuals:
		if not key is String or not key.is_valid_int() or int(key) < 0 or int(key) > 31:
			return false
		if not _integer(value.equipment_visuals[key], 0) or value.equipment_visuals[key] > 65535:
			return false
	return true
