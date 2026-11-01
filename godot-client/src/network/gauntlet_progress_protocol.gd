extends RefCounted
## A complete, map-scoped encounter snapshot. Durations are upper bounds;
## the server can release a pulse sooner at its remaining-enemy threshold.
const MAX_COUNT := 2147483647

static func integer(value: Variant, minimum := 0) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) \
		and float(value) == floor(float(value)) and value >= minimum and value <= MAX_COUNT

static func decode(payload: PackedByteArray) -> Dictionary:
	var state: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not state is Dictionary or not integer(state.get("version"), 1) or state.version != 1 \
			or not state.get("active") is bool:
		return {"type":"invalid", "error":"gauntlet_progress_shape"}
	if not state.active:
		var inactive := {"version":1, "active":false}
		if state.has("run_id") or state.has("map_id"):
			for field: String in ["run_id", "map_id"]:
				if not state.get(field) is String or state[field].is_empty() or state[field].length() > 160:
					return {"type":"invalid", "error":"gauntlet_progress_identity"}
				inactive[field] = state[field]
		return {"type":"gauntlet_progress", "data":inactive}
	for field: String in ["run_id", "map_id", "title"]:
		if not state.get(field) is String or state[field].is_empty() or state[field].length() > 160:
			return {"type":"invalid", "error":"gauntlet_progress_identity"}
	if not state.get("phase") is String or state.phase not in ["waiting", "fighting"]:
		return {"type":"invalid", "error":"gauntlet_progress_phase"}
	for field: String in ["wave", "waves", "enemies", "pulses_landed", "pulses_total", "pulses_pending", "arrival_serial"]:
		if not integer(state.get(field), 1 if field in ["wave", "waves"] else 0):
			return {"type":"invalid", "error":"gauntlet_progress_count"}
	if state.wave > state.waves or state.pulses_landed > state.pulses_total \
			or state.pulses_pending != state.pulses_total - state.pulses_landed \
			or state.arrival_serial != state.pulses_landed:
		return {"type":"invalid", "error":"gauntlet_progress_order"}
	for field: String in ["release_remaining_ms", "release_enemy_threshold"]:
		if not state.has(field) or (state[field] != null and not integer(state[field])):
			return {"type":"invalid", "error":"gauntlet_progress_release"}
	if state.release_remaining_ms != null and state.release_enemy_threshold == null:
		return {"type":"invalid", "error":"gauntlet_progress_release"}
	if (state.pulses_pending == 0 or state.phase == "waiting") \
			and (state.release_remaining_ms != null or state.release_enemy_threshold != null):
		return {"type":"invalid", "error":"gauntlet_progress_release"}
	return {"type":"gauntlet_progress", "data":state}
