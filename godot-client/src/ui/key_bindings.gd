extends RefCounted
## keys.ini: every hot key, in a file a player can read and edit, the way
## Eternal Lands keeps key.ini.
##
## One line per action, `#K_<ACTION> = <key>[, <key>...]`, where a key is its
## modifiers then its name: `#K_TOGGLE_MAP = TAB`, `#K_QUICK_SPELL_1 = ALT 1`,
## `#K_QUICK_ITEM_1 = 1, CTRL 1`, `#K_SPELL_RING = LSHIFT`. Lines that are not
## `#K_` entries are comments and are ignored, as are actions this client does
## not have; an action the file leaves out keeps its default. The settings
## window writes the file whenever a key is changed, and its Reset button puts
## every key back to the shipped default.

const PATH := "user://keys.ini"
## The layout `render` writes, kept in the file as `#KEYS_VERSION = 3`. A file
## without that line is version 1.
const VERSION := 3
## Defaults each older version shipped that a later one changed. keys.ini is
## written on the first run, so it lists the defaults of the build that wrote
## it as if the player had chosen them. An entry that still names its old
## default is dropped once, the current default applies, and the file is
## written again at this version, so a key chosen after that is kept.
const SUPERSEDED := {
	1: {"toggle_map": "M", "technique_ring": "TAB"},
	2: {"toggle_leaderboards": "CTRL L"},
}

## Names for keys whose Godot name is not what the file should say.
const NAMES := {
	KEY_ESCAPE: "ESC", KEY_TAB: "TAB", KEY_ENTER: "ENTER", KEY_SPACE: "SPACE",
	KEY_BACKSPACE: "BACKSPACE", KEY_INSERT: "INSERT", KEY_DELETE: "DELETE",
	KEY_HOME: "HOME", KEY_END: "END", KEY_PAGEUP: "PAGEUP", KEY_PAGEDOWN: "PAGEDOWN",
	KEY_UP: "UP", KEY_DOWN: "DOWN", KEY_LEFT: "LEFT", KEY_RIGHT: "RIGHT",
	KEY_MINUS: "-", KEY_EQUAL: "=", KEY_BRACKETLEFT: "[", KEY_BRACKETRIGHT: "]",
	KEY_SEMICOLON: ";", KEY_APOSTROPHE: "'", KEY_COMMA: ",", KEY_PERIOD: ".",
	KEY_SLASH: "/", KEY_BACKSLASH: "\\", KEY_QUOTELEFT: "`",
}
## Modifier keys bound on their own (a ring is held), with their side.
const SIDED := {
	"LSHIFT": [KEY_SHIFT, KEY_LOCATION_LEFT], "RSHIFT": [KEY_SHIFT, KEY_LOCATION_RIGHT],
	"LCTRL": [KEY_CTRL, KEY_LOCATION_LEFT], "RCTRL": [KEY_CTRL, KEY_LOCATION_RIGHT],
	"LALT": [KEY_ALT, KEY_LOCATION_LEFT], "RALT": [KEY_ALT, KEY_LOCATION_RIGHT],
}

## One key as keys.ini writes it, or "" for something that is not a key.
static func describe(event: InputEvent) -> String:
	if not event is InputEventKey:
		return ""
	var key := event as InputEventKey
	var code := key.physical_keycode if key.physical_keycode != 0 else key.keycode
	if code == 0:
		return ""
	if code in [KEY_SHIFT, KEY_CTRL, KEY_ALT]:
		for name: String in SIDED:
			if SIDED[name][0] == code and SIDED[name][1] == key.location:
				return name
		return {KEY_SHIFT: "SHIFT", KEY_CTRL: "CTRL", KEY_ALT: "ALT"}[code]
	var parts: Array[String] = []
	if key.ctrl_pressed:
		parts.append("CTRL")
	if key.alt_pressed:
		parts.append("ALT")
	if key.shift_pressed:
		parts.append("SHIFT")
	parts.append(str(NAMES.get(code, OS.get_keycode_string(code).to_upper())))
	return " ".join(parts)

## The key a keys.ini entry names, or null when it cannot be read.
static func parse(text: String) -> InputEventKey:
	var tokens := text.strip_edges().to_upper().split(" ", false)
	if tokens.is_empty():
		return null
	var event := InputEventKey.new()
	var last: String = tokens[tokens.size() - 1]
	for index in range(tokens.size() - 1):
		match tokens[index]:
			"CTRL": event.ctrl_pressed = true
			"ALT": event.alt_pressed = true
			"SHIFT": event.shift_pressed = true
			_: return null
	if SIDED.has(last):
		event.physical_keycode = SIDED[last][0]
		event.location = SIDED[last][1]
		return event
	if last in ["SHIFT", "CTRL", "ALT"] and tokens.size() == 1:
		event.physical_keycode = {"SHIFT": KEY_SHIFT, "CTRL": KEY_CTRL, "ALT": KEY_ALT}[last]
		return event
	for code: Variant in NAMES:
		if NAMES[code] == last:
			event.physical_keycode = code
			return event
	var code := OS.find_keycode_from_string(last.capitalize())
	if code == KEY_NONE:
		code = OS.find_keycode_from_string(last)
	if code == KEY_NONE:
		return null
	event.physical_keycode = code
	return event

## The file's text for these actions, in the order given.
static func render(actions: Array) -> String:
	var lines: Array[String] = [
		"; Rabbit Lands key bindings. One line per action:",
		";   #K_<ACTION> = <key>[, <another key>]",
		"; A key is its modifiers then its name: M, CTRL S, ALT 1, LSHIFT, TAB.",
		"; Edit with the game closed, or change keys in Settings > Controls.",
		"; Settings > Controls > Reset all keys puts every key back to its default.",
		"; Keep the #KEYS_VERSION line: it says which defaults the file was written with.",
		"#KEYS_VERSION = %d" % VERSION,
		""]
	for action: Variant in actions:
		var name := str(action)
		if not InputMap.has_action(name):
			continue
		var keys: Array[String] = []
		for event: InputEvent in InputMap.action_get_events(name):
			var described := describe(event)
			if not described.is_empty() and described not in keys:
				keys.append(described)
		lines.append("#K_%s = %s" % [name.to_upper(), ", ".join(keys)])
	return "\n".join(lines) + "\n"

static func save(actions: Array, path := PATH) -> Error:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(render(actions))
	file.close()
	return OK

## Reads keys.ini into action -> [InputEventKey]. An entry that cannot be
## read is left out, so the action keeps the key it had rather than losing it.
static func read(text: String, allowed: Array) -> Dictionary:
	var result := {}
	for raw_line: String in text.split("\n"):
		var line := raw_line.strip_edges()
		if not line.begins_with("#K_") or not "=" in line:
			continue
		var action := line.substr(3, line.find("=") - 3).strip_edges().to_lower()
		if action not in allowed:
			continue
		var events: Array[InputEventKey] = []
		for spec: String in line.substr(line.find("=") + 1).split(",", false):
			var event := parse(spec)
			if event != null:
				events.append(event)
		if not events.is_empty():
			result[action] = events
	return result

## The `#KEYS_VERSION` a file was written at; 1 when it has none.
static func version_of(text: String) -> int:
	for raw_line: String in text.split("\n"):
		var line := raw_line.strip_edges()
		if line.begins_with("#KEYS_VERSION") and "=" in line:
			return maxi(1, line.get_slice("=", 1).strip_edges().to_int())
	return 1

## Applies keys.ini to the input map. Returns how many actions it set. A
## file from an older version loses the entries that only repeat that
## version's defaults (SUPERSEDED) and is written again at this one.
static func load_file(allowed: Array, path := PATH) -> int:
	if not FileAccess.file_exists(path):
		return 0
	var text := FileAccess.get_file_as_string(path)
	var parsed := read(text, allowed)
	var version := version_of(text)
	for old_version in range(version, VERSION):
		var old_defaults: Dictionary = SUPERSEDED.get(old_version, {})
		for action: String in old_defaults:
			if parsed.has(action) and _names(parsed[action]) == str(old_defaults[action]):
				parsed.erase(action)
	for action: String in parsed:
		InputMap.action_erase_events(action)
		for event: InputEventKey in parsed[action]:
			InputMap.action_add_event(action, event)
	if version < VERSION:
		save(allowed, path)
	return parsed.size()

## Keys as one keys.ini value: `1, CTRL 1`.
static func _names(events: Array) -> String:
	var names: Array[String] = []
	for event: Variant in events:
		names.append(describe(event as InputEvent))
	return ", ".join(names)

## Puts every listed action back to the key project.godot ships.
static func reset_to_defaults(actions: Array) -> void:
	for action: Variant in actions:
		var name := str(action)
		if not InputMap.has_action(name):
			continue
		var defaults: Dictionary = ProjectSettings.get_setting("input/" + name, {})
		InputMap.action_erase_events(name)
		for event: InputEvent in defaults.get("events", []):
			InputMap.action_add_event(name, event)
