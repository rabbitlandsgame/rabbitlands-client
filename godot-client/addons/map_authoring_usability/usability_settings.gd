@tool
extends RefCounted
## Per-user map editor preferences and rebindable shortcuts.
##
## Everything lives in Godot's EditorSettings, so it appears in
## Editor > Editor Settings under "Map Authoring" (values) and in the Shortcuts
## tab under "Map Authoring" (keys), survives restarts, and never enters a scene.

const PREFIX := "map_authoring/"

enum CursorGrid { OFF, WHILE_PLACING, ALWAYS }

const DEFAULTS := {
	"placement/keep_placing": true,
	"placement/random_rotation": false,
	"placement/size_variation": 0.0,
	"placement/align_to_surface": false,
	"placement/snap_to_grid": false,
	"placement/rotate_step_degrees": 15.0,
	"placement/fine_rotate_step_degrees": 1.0,
	"placement/lift_step": 0.25,
	"placement/fine_lift_step": 0.05,
	"placement/scale_step": 0.1,
	"placement/fine_scale_step": 0.01,
	"grid/step": 1.0,
	"grid/cursor_grid": CursorGrid.WHILE_PLACING,
	"grid/radius_cells": 8,
	"viewport/show_cursor_readout": true,
	"sculpt/radius_factor": 1.25,
	"sculpt/strength_factor": 1.25,
	"time_of_day/minute": 180.0,
	"capture/pixels_per_metre": 2.0,
	"capture/include_references": false,
	"capture/clip_to_ownership": true,
	"markers/show": true,
	"markers/labels": true,
	"performance/low_spec": false,
	"performance/far_asset_metres": 200.0,
	"minimap/pixels_per_metre": 0.5,
	"concept/masters_folder": "",
	"concept/opacity": 0.6,
}

const HINTS := {
	"placement/size_variation": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0,0.9,0.01"],
	"placement/rotate_step_degrees": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.1,180,0.1"],
	"placement/fine_rotate_step_degrees": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.1,45,0.1"],
	"placement/lift_step": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.01,10,0.01"],
	"placement/fine_lift_step": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.001,1,0.001"],
	"placement/scale_step": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.01,1,0.01"],
	"placement/fine_scale_step": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.001,0.2,0.001"],
	"grid/step": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.125,16,0.125"],
	"grid/cursor_grid": [TYPE_INT, PROPERTY_HINT_ENUM, "Off,While placing,Always"],
	"grid/radius_cells": [TYPE_INT, PROPERTY_HINT_RANGE, "2,32,1"],
	"sculpt/radius_factor": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "1.05,2,0.05"],
	"sculpt/strength_factor": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "1.05,2,0.05"],
	"time_of_day/minute": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0,359.75,0.25"],
	"capture/pixels_per_metre": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.25,8,0.25"],
	"performance/far_asset_metres": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "40,2000,10"],
	"minimap/pixels_per_metre": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.1,2,0.05"],
	"concept/masters_folder": [TYPE_STRING, PROPERTY_HINT_GLOBAL_DIR, ""],
	"concept/opacity": [TYPE_FLOAT, PROPERTY_HINT_RANGE, "0.1,1,0.05"],
}

## Shortcut path -> [display name, keycode, shift, ctrl, alt]. KEY_NONE is unbound.
const SHORTCUTS := {
	"rotate_left": ["Placement: turn left", KEY_Q, false, false, false],
	"rotate_right": ["Placement: turn right", KEY_E, false, false, false],
	"raise": ["Placement: raise", KEY_PAGEUP, false, false, false],
	"lower": ["Placement: lower", KEY_PAGEDOWN, false, false, false],
	"scale_up": ["Placement: grow", KEY_HOME, false, false, false],
	"scale_down": ["Placement: shrink", KEY_END, false, false, false],
	"reset": ["Placement: reset turn, height and size", KEY_BACKSPACE, false, false, false],
	"toggle_snap": ["Placement: toggle grid snap", KEY_G, false, false, false],
	"drop_to_ground": ["Selection: drop to ground", KEY_NONE, false, false, false],
	"rotate_each": ["Selection: rotate each 90°", KEY_NONE, false, false, false],
	"save_prefab": ["Selection: save as prefab", KEY_NONE, false, false, false],
	"sculpt_raise": ["Sculpt: Raise brush", KEY_1, false, false, false],
	"sculpt_lower": ["Sculpt: Lower brush", KEY_2, false, false, false],
	"sculpt_smooth": ["Sculpt: Smooth brush", KEY_3, false, false, false],
	"sculpt_flatten": ["Sculpt: Flatten brush", KEY_4, false, false, false],
	"sculpt_smaller": ["Sculpt: smaller brush (Shift: weaker)", KEY_BRACKETLEFT, false, false, false],
	"sculpt_larger": ["Sculpt: larger brush (Shift: stronger)", KEY_BRACKETRIGHT, false, false, false],
	"path_narrower": ["Path drawing: narrower (Shift: fine)", KEY_BRACKETLEFT, false, false, false],
	"path_wider": ["Path drawing: wider (Shift: fine)", KEY_BRACKETRIGHT, false, false, false],
	"draw_road": ["Paths: draw a road", KEY_NONE, false, false, false],
	"draw_river": ["Paths: draw a river", KEY_NONE, false, false, false],
	"group": ["Selection: group", KEY_G, false, true, false],
	"ungroup": ["Selection: ungroup", KEY_G, true, true, false],
	"duplicate_fresh": ["Selection: duplicate with fresh ids", KEY_NONE, false, false, false],
	"play_test": ["Play test: start or stop", KEY_NONE, false, false, false],
	"focus_walker": ["Play test: look at the walker", KEY_F, false, false, false],
}

const KEY_SYMBOLS := {"BracketLeft": "[", "BracketRight": "]", "PageUp": "PgUp",
	"PageDown": "PgDn"}

static var _registered := false


static func editor_settings() -> EditorSettings:
	if not Engine.is_editor_hint():
		return null
	var editor_interface: Object = Engine.get_singleton("EditorInterface")
	return editor_interface.call("get_editor_settings") as EditorSettings \
		if editor_interface != null else null


static func register() -> void:
	var settings := editor_settings()
	if settings == null:
		return
	for key: String in DEFAULTS:
		var path := PREFIX + key
		if not settings.has_setting(path):
			settings.set_setting(path, DEFAULTS[key])
		settings.set_initial_value(path, DEFAULTS[key], false)
		if HINTS.has(key):
			var hint: Array = HINTS[key]
			settings.add_property_info({"name": path, "type": hint[0], "hint": hint[1],
				"hint_string": hint[2]})
	for key: String in SHORTCUTS:
		var path := PREFIX + key
		if settings.has_shortcut(path):
			continue
		var spec: Array = SHORTCUTS[key]
		var shortcut := Shortcut.new()
		shortcut.resource_name = String(spec[0])
		if int(spec[1]) != KEY_NONE:
			var event := InputEventKey.new()
			event.keycode = int(spec[1])
			event.shift_pressed = bool(spec[2])
			event.ctrl_pressed = bool(spec[3])
			event.alt_pressed = bool(spec[4])
			shortcut.events = [event]
		settings.add_shortcut(path, shortcut)
	_registered = true


static func value(key: String) -> Variant:
	var settings := editor_settings()
	var path := PREFIX + key
	if settings != null and settings.has_setting(path):
		return settings.get_setting(path)
	return DEFAULTS.get(key)


static func set_value(key: String, next_value: Variant) -> void:
	var settings := editor_settings()
	if settings != null:
		settings.set_setting(PREFIX + key, next_value)


## True when the key event matches the shortcut. Shift is reserved as the
## "fine step" modifier, so a bound key also matches with Shift held unless the
## binding itself uses Shift.
static func matches(key: String, event: InputEvent) -> bool:
	if not event is InputEventKey or not event.is_pressed():
		return false
	var settings := editor_settings()
	var path := PREFIX + key
	if settings != null and settings.has_shortcut(path):
		if settings.is_shortcut(path, event):
			return true
		if (event as InputEventKey).shift_pressed:
			var plain := (event as InputEventKey).duplicate() as InputEventKey
			plain.shift_pressed = false
			return settings.is_shortcut(path, plain)
		return false
	var spec: Array = SHORTCUTS.get(key, [])
	if spec.is_empty() or int(spec[1]) == KEY_NONE:
		return false
	var key_event := event as InputEventKey
	return key_event.keycode == int(spec[1]) and key_event.ctrl_pressed == bool(spec[3]) and \
		key_event.alt_pressed == bool(spec[4])


static func shortcut_text(key: String) -> String:
	var settings := editor_settings()
	var path := PREFIX + key
	if settings != null and settings.has_shortcut(path):
		var shortcut := settings.get_shortcut(path)
		if shortcut != null and shortcut.has_valid_event():
			return _readable(shortcut.get_as_text())
		return "unbound"
	var spec: Array = SHORTCUTS.get(key, [])
	if spec.is_empty() or int(spec[1]) == KEY_NONE:
		return "unbound"
	return _readable(OS.get_keycode_string(int(spec[1])))


## Godot spells some keys out ("BracketLeft"); hints read better with symbols.
static func _readable(text: String) -> String:
	for spelled: String in KEY_SYMBOLS:
		text = text.replace(spelled, String(KEY_SYMBOLS[spelled]))
	return text
