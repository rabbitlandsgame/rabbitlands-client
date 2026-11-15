extends RefCounted
const MAX_RULES := 20
const AP_CONDITIONS := ["action_points_below", "action_points_at_least"]

static func value_maximum(condition: String) -> int:
	return 65535 if condition in AP_CONDITIONS else 100

## Reject malformed editor state before constructing controls from it.
static func request_payload(data: Dictionary, state: Dictionary) -> Dictionary:
	var result := data.duplicate(true)
	if not state.is_empty():
		result.merge({"subject":state.subject, "revision":int(state.plan.revision), "context":state.context}, false)
	# Godot parses JSON numbers as floats. Python's tactics contract requires
	# actual integer JSON tokens for revisions, presets and rule values.
	if result.has("revision"): result.revision = int(result.revision)
	if result.has("selected"): result.selected = int(result.selected)
	if result.has("rules"):
		for entry: Dictionary in result.rules:
			entry.value = int(entry.value)
			entry.power = int(entry.power)
	return result

static func valid(state: Dictionary) -> bool:
	if state.get("version") != 1 or not state.get("subject") is String or not state.get("role") is String:
		return false
	if not state.get("context") is String or state.context.length() > 64: return false
	if not state.get("active") is bool or not state.get("player_active") is bool or not state.get("status") is String or not state.get("notice") is String:
		return false
	if not state.get("subjects") is Array or state.subjects.size() > 8 or not state.get("actions") is Array or state.actions.size() > 512:
		return false
	for subject: Variant in state.subjects:
		if not subject is Dictionary or not subject.get("id") is String or not subject.get("name") is String: return false
	for action: Variant in state.actions:
		if not action is Dictionary or not action.get("id") is String or not action.get("name") is String: return false
	if state.has("statuses"):
		if not state.statuses is Array or state.statuses.size() > 64: return false
		for status: Variant in state.statuses:
			if not status is Dictionary or not status.get("id") is String or not status.get("name") is String or status.get("kind") not in ["buff", "debuff"]: return false
	var plan: Variant = state.get("plan")
	if not plan is Dictionary or not _integer(plan.get("revision"), 0, 2147483647) or not _integer(plan.get("selected"), 0, 2): return false
	if not plan.get("profiles") is Array or plan.profiles.size() != 3 or not _integer(state.get("max_rules"), 1, MAX_RULES): return false
	for profile: Variant in plan.profiles:
		if not profile is Dictionary or not profile.get("name") is String or not profile.get("rules") is Array or profile.rules.size() > int(state.max_rules): return false
		for entry: Variant in profile.rules:
			if not entry is Dictionary or not entry.get("enabled") is bool: return false
			if entry.get("combat", "any") not in ["any", "in_combat", "out_of_combat"]: return false
			for key: String in ["target", "condition", "status", "action"]:
				if not entry.get(key) is String or str(entry[key]).length() > 64: return false
			if not _integer(entry.get("power"), 1, 10) or not _integer(entry.get("value"), 1, value_maximum(entry.condition)): return false
	return true

static func _integer(value: Variant, low: int, high: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == float(int(value)) and value >= low and value <= high
