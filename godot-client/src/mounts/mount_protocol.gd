extends RefCounted
const MountState := preload("res://src/mounts/mount_preview_state.gd")

static func decode(payload: PackedByteArray) -> Dictionary:
	if payload.size() > 65532:
		return {"type": "invalid", "error": "mount_length"}
	var decoded: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not decoded is Dictionary:
		return {"type": "invalid", "error": "mount_json"}
	var data: Dictionary = decoded
	if data.get("schema_version") != 1 or not data.get("map") is String or not data.get("states") is Array or data.states.size() > 256:
		return {"type": "invalid", "error": "mount_header"}
	var states: Dictionary = {}
	for value: Variant in data.states:
		if not value is Dictionary or not value.get("map") is String or not value.get("owner") is String:
			return {"type": "invalid", "error": "mount_row"}
		var row: Dictionary = value.duplicate(true)
		for key: String in ["mode", "gait", "mount_id", "selected_mount_id", "blocked_reason"]:
			if not row.get(key) is String:
				return {"type": "invalid", "error": "mount_field_type"}
		row["kind"] = "mount_preview"
		row["epoch"] = 0
		row["revision"] = 1
		var checker := MountState.new()
		if not MountState._integer(row.get("actor_id"), 0, 65535):
			return {"type": "invalid", "error": "mount_actor"}
		checker.reset(int(row.actor_id), 0)
		if not checker.apply_snapshot(row) or states.has(int(row.actor_id)):
			return {"type": "invalid", "error": "mount_state"}
		states[int(row.actor_id)] = value
	return {"type": "mount_states", "map": data.map, "states": states}
