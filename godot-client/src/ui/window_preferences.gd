class_name WindowPreferences
extends RefCounted
## Remembered sizes for the windows a player is allowed to resize.
##
## The inventory and ground-bag panels already kept their scale in the HUD
## settings file, under their own sections. The floating windows had nowhere to
## put theirs, so every open reset them to the size they shipped at and a
## resize lasted only until the window was closed. Scales recorded here go to
## the same file, so a window reopens at the size it was left in this session
## and in the next one.

const SETTINGS_PATH := "user://eloria_hud.cfg"
const SECTION := "windows"


static func stored_scale(key: String, fallback: float, minimum: float,
		maximum: float) -> float:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return fallback
	# Clamped on the way in as well as on the way out: a settings file carried
	# over from a wider screen must not open a window larger than this one.
	return clampf(float(config.get_value(SECTION, key + "_scale", fallback)),
		minimum, maximum)


static func store_scale(key: String, scale: float) -> void:
	var config := ConfigFile.new()
	# Loaded first so writing one window's scale keeps every other setting the
	# HUD holds in this file.
	config.load(SETTINGS_PATH)
	config.set_value(SECTION, key + "_scale", scale)
	var error: Error = config.save(SETTINGS_PATH)
	if error != OK:
		push_warning("Window scale save failed: " + error_string(error))

static func stored_rect(key: String, fallback: Rect2, path: String = SETTINGS_PATH) -> Rect2:
	var config := ConfigFile.new()
	if config.load(path) != OK:
		return fallback
	var value: Variant = config.get_value(SECTION, key + "_rect", fallback)
	if value is Rect2:
		var rect: Rect2 = value
		if rect.position.is_finite() and rect.size.is_finite() and rect.size.x > 0 and rect.size.y > 0:
			return rect
	return fallback

static func stored_collapsed(key: String, fallback: bool = false, path: String = SETTINGS_PATH) -> bool:
	var config := ConfigFile.new()
	return bool(config.get_value(SECTION, key + "_collapsed", fallback)) if config.load(path) == OK else fallback

static func stored_options(key: String, fallback: Dictionary = {}, path: String = SETTINGS_PATH) -> Dictionary:
	var config := ConfigFile.new()
	if config.load(path) != OK:
		return fallback.duplicate()
	var value: Variant = config.get_value(SECTION, key + "_options", fallback)
	return (value as Dictionary).duplicate() if value is Dictionary else fallback.duplicate()

static func store_layout(key: String, rect: Rect2, collapsed: bool = false, path: String = SETTINGS_PATH, options: Dictionary = {}) -> void:
	var config := ConfigFile.new()
	config.load(path)
	config.set_value(SECTION, key + "_rect", rect)
	config.set_value(SECTION, key + "_collapsed", collapsed)
	if not options.is_empty():
		config.set_value(SECTION, key + "_options", options)
	var error := config.save(path)
	if error != OK:
		push_warning("HUD layout save failed: " + error_string(error))
