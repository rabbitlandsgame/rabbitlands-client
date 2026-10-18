extends RefCounted
const KeyBindings := preload("res://src/ui/key_bindings.gd")

static func request_for_event(event: InputEvent, state: Dictionary) -> String:
	if state.is_empty() or not event is InputEventKey or not event.pressed or (event as InputEventKey).echo:
		return ""
	if event.is_action_pressed("toggle_mount", false, true):
		return "#mount"
	if state.get("mode") == "mounted" and event.is_action_pressed("toggle_gallop", false, true):
		return "#gallop"
	return ""

static func key_hint(action: String) -> String:
	for event: InputEvent in InputMap.action_get_events(action):
		var key := KeyBindings.describe(event)
		if not key.is_empty():
			return " [" + key.capitalize() + "]"
	return ""
