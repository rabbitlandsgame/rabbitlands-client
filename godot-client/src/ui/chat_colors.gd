extends RefCounted
## Preserve EL's server-selected runs until a player explicitly overrides a
## category. Sparse override metadata distinguishes untouched defaults from
## a color deliberately chosen by the player, even if its RGB is identical.
const Messages := preload("res://src/ui/chat_messages.gd")
const Protocol := preload("res://src/network/protocol.gd")
const SECTION := "chat_colors"
const VERSION := 2
const DEFAULTS := {
	"local": Color("ffffff"), "party": Color("a9effa"),
	"private": Color("f7c49f"), "guild": Color("7697f8"),
	"channel": Color("fbfabe"), "channel_active": Color("ffffff"),
	"channel_inactive": Color("999999"), "system": Color("ffffff"),
	"harvest": Color("fc7a3a"), "harvest_event": Color("fc7a3a"),
	"special": Color("7697f8"), "gm_prefix": Color("7697f8"),
	"gm": Color("7697f8"), "error": Color("fa5a5a"),
	"connecting": Color("ffb3c1"), "welcome": Color("25c400"),
	"success": Color("05fa9b"), "server_notice": Color("4448d2"),
	"warning": Color("fc7a3a"), "url": Color("ffffff"),
	"moderator": Color("ffffff"), "mod_private": Color("ffffff"),
}
## Version 1 saved every factory color. Migrate only differences so the new
## defaults take effect without erasing saved custom choices.
const LEGACY_DEFAULTS := {
	"local": Color("ffffff"), "party": Color("a9effa"),
	"private": Color("d2b4fb"), "guild": Color("fff7aa"),
	"channel": Color("fff7aa"), "channel_active": Color("ffffff"),
	"channel_inactive": Color("999999"), "system": Color("ccffcc"),
	"harvest": Color("ff7f32"), "harvest_event": Color("ff7f32"),
	"special": Color("8b9dff"), "gm_prefix": Color("8b9dff"),
	"gm": Color("a9effa"), "error": Color("ff4d4d"),
	"connecting": Color("ffb3c1"), "welcome": Color("55ff00"),
	"success": Color("55ff00"), "server_notice": Color("5757ff"),
	"warning": Color("ff7f32"), "url": Color("a9effa"),
}
const LABELS := {
	"local": "Nearby speech", "party": "Party messages",
	"private": "Private messages", "guild": "Guild messages",
	"channel": "Numbered channel bodies", "channel_active": "Active channel heading",
	"channel_inactive": "Inactive channel heading", "system": "Uncolored system messages",
	"harvest": "Harvesting", "harvest_event": "Harvesting events",
	"special": "Special finds", "gm_prefix": "Guild message (GM) heading",
	"gm": "Guild message (GM) text", "error": "Disconnects and errors",
	"connecting": "Connecting and retrying", "welcome": "Server welcome",
	"success": "Success notices", "server_notice": "Server announcements",
	"warning": "Warnings", "url": "Web links",
	"moderator": "Moderator messages", "mod_private": "Moderator private messages",
}
static var _links: RegEx

static func defaults() -> Dictionary:
	var result := DEFAULTS.duplicate()
	result["_overrides"] = []
	return result

static func _color(value: Variant) -> Variant:
	if value is String and Color.html_is_valid(value):
		value = Color.html(value)
	if value is Color:
		var color: Color = value
		if is_finite(color.r) and is_finite(color.g) and is_finite(color.b):
			return Color(clampf(color.r, 0.0, 1.0), clampf(color.g, 0.0, 1.0), clampf(color.b, 0.0, 1.0), 1.0)
	return null

static func _valid_key(key: String) -> bool:
	return DEFAULTS.has(key) or (key.begins_with("channel:") and key.trim_prefix("channel:").is_valid_int() and int(key.trim_prefix("channel:")) > 0)

static func normalise(raw: Dictionary) -> Dictionary:
	var result := defaults()
	var explicit: Array = raw.get("_overrides", [])
	for raw_key: Variant in raw:
		var key := str(raw_key)
		if not _valid_key(key):
			continue
		var color: Variant = _color(raw[raw_key])
		if color == null:
			continue
		result[key] = color
		if key in explicit or not DEFAULTS.has(key) or color != DEFAULTS[key]:
			(result._overrides as Array).append(key)
	return result

static func is_overridden(colors: Dictionary, key: String) -> bool:
	return key in (colors.get("_overrides", []) as Array) or (colors.has(key) and DEFAULTS.has(key) and colors[key] != DEFAULTS[key])

static func set_override(colors: Dictionary, key: String, value: Variant) -> Dictionary:
	var result := normalise(colors)
	var color: Variant = _color(value)
	if _valid_key(key) and color != null:
		result[key] = color
		if not key in (result._overrides as Array):
			(result._overrides as Array).append(key)
	return result

static func reset_override(colors: Dictionary, key: String) -> Dictionary:
	var result := normalise(colors)
	(result._overrides as Array).erase(key)
	if DEFAULTS.has(key):
		result[key] = DEFAULTS[key]
	else:
		result.erase(key)
	return result

static func channel_override_key(number: int) -> String:
	return "channel:%d" % number

static func set_channel_override(colors: Dictionary, number: int, value: Variant) -> Dictionary:
	return set_override(colors, channel_override_key(number), value)

static func load_colors(path: String = WindowPreferences.SETTINGS_PATH) -> Dictionary:
	var config := ConfigFile.new()
	if config.load(path) != OK or not config.has_section(SECTION):
		return defaults()
	var result := defaults()
	var version := int(config.get_value(SECTION, "version", 1))
	var explicit: Array = config.get_value(SECTION, "overrides", []) if version >= VERSION else []
	for key: String in config.get_section_keys(SECTION):
		if not _valid_key(key):
			continue
		var color: Variant = _color(config.get_value(SECTION, key))
		if color == null:
			continue
		if (version >= VERSION and key in explicit) or (version < VERSION and color != LEGACY_DEFAULTS.get(key, DEFAULTS.get(key))):
			result = set_override(result, key, color)
	return result

static func save_colors(colors: Dictionary, path: String = WindowPreferences.SETTINGS_PATH) -> Error:
	var config := ConfigFile.new()
	config.load(path)
	var palette := normalise(colors)
	if config.has_section(SECTION):
		config.erase_section(SECTION)
	config.set_value(SECTION, "version", VERSION)
	config.set_value(SECTION, "overrides", palette._overrides)
	for key: String in palette._overrides:
		config.set_value(SECTION, key, palette[key])
	var error := config.save(path)
	if error != OK:
		push_warning("Chat colors save failed: " + error_string(error))
	return error

static func role(line: Dictionary) -> String:
	var explicit := str(line.get("chat_role", ""))
	if DEFAULTS.has(explicit):
		return explicit
	var category := Messages.kind(line)
	var text := str(line.get("text", "")).to_lower()
	if category in ["guild", "system"] and (text.begins_with("#gm from ") or text.begins_with("gm from ")):
		return "gm"
	if category != "system":
		return category if DEFAULTS.has(category) else "local"
	if text.begins_with("welcome to "):
		return "welcome"
	if text.begins_with("connecting to ") or text.begins_with("reconnecting"):
		return "connecting"
	if text.begins_with("disconnected from ") or text.begins_with("connection lost") or text.begins_with("error:"):
		return "error"
	var harvesting := text.contains("harvest")
	if (harvesting and text.contains("found ")) or (text.contains(" found ") and _wire_colour(line) == 11):
		return "special"
	if (harvesting and (text.contains("bless") or text.contains("bees")
			or text.contains("mother nature") or text.begins_with("while ")
			or text.contains("experience") or text.contains("xp is paused"))) or text.contains("queen of nature") or text.contains(" found a bag of gold"):
		return "harvest_event"
	if harvesting or (text == "you cannot carry any more." and _wire_colour(line) in [1, 8]):
		return "harvest"
	if text.begins_with("warning:"):
		return "warning"
	match _wire_colour(line):
		0: return "connecting"
		1, 8, 15, 22: return "warning"
		7, 14, 21: return "error"
		10, 17, 24: return "success"
		11, 18, 25: return "server_notice"
	return "system"

static func line_color(line: Dictionary, colors: Dictionary = {}) -> Color:
	var rendered := raw_segments(line, colors)
	return rendered[0].color if not rendered.is_empty() else Color.WHITE

static func raw_segments(line: Dictionary, colors: Dictionary = {}) -> Array[Dictionary]:
	return _render(line, str(line.get("text", "")), -1, colors)

static func segments(line: Dictionary, formatted_text: String, active_channel: int = 0,
		colors: Dictionary = {}) -> Array[Dictionary]:
	return _render(line, formatted_text, active_channel, colors)

static func _render(line: Dictionary, formatted_text: String, active_channel: int, colors: Dictionary) -> Array[Dictionary]:
	var palette := normalise(colors)
	var key := role(line)
	var raw := str(line.get("text", ""))
	var runs: Array = line.get("text_runs", [])
	if runs.is_empty():
		runs = [{"text": raw, "colour": _wire_colour(line)}]
	var start := 0
	var end := raw.length()
	var display := raw
	# Main abbreviates wrappers; retain the original run boundaries while
	# applying only those presentation edits.
	if not formatted_text.ends_with(display):
		var category := Messages.kind(line)
		if category == "channel":
			start = raw.length() - raw.trim_prefix("[%d] " % Messages.channel_number(line)).length()
		elif category == "private":
			if raw.begins_with("[PM from "):
				start = "[PM from ".length()
			elif raw.begins_with("[PM to "):
				start = raw.find(": ") + 2
			if raw.ends_with("]"):
				end -= 1
		display = raw.substr(start, end - start)
	var prefix_length := formatted_text.length() - display.length() if formatted_text.ends_with(display) else 0
	if prefix_length == 0 and formatted_text != display:
		return [{"text": formatted_text, "color": _run_color(line, key, 0, _wire_colour(line), palette, active_channel)}]
	var result: Array[Dictionary] = []
	var offset := 0
	var visible_runs: Array[Dictionary] = []
	for index: int in runs.size():
		var run: Dictionary = runs[index]
		var text := str(run.get("text", ""))
		var left := maxi(start - offset, 0)
		var right := mini(end - offset, text.length())
		if right > left:
			var color := _run_color(line, key, index, int(run.get("colour", -1)), palette, active_channel)
			var absolute_left := offset + left
			var split := raw.find(": ") + 2
			var heading_key := "gm_prefix" if key == "gm" else ("channel_inactive" if Messages.channel_number(line) > 0 and Messages.channel_number(line) != active_channel else "channel_active")
			# Explicit custom heading/body colors split a single wire run.
			if (key == "gm" or key == "channel") and split > 1 and (is_overridden(palette, key) or is_overridden(palette, heading_key)):
				var boundary := clampi(split - absolute_left, 0, right - left)
				_add(visible_runs, text.substr(left, boundary), palette[heading_key] if is_overridden(palette, heading_key) else color)
				_add(visible_runs, text.substr(left + boundary, right - left - boundary), palette[key] if is_overridden(palette, key) else color)
			else:
				_add(visible_runs, text.substr(left, right - left), color)
		offset += text.length()
	var first_color: Color = visible_runs[0].color if not visible_runs.is_empty() else palette[key]
	_add(result, formatted_text.substr(0, prefix_length), first_color)
	for run: Dictionary in visible_runs:
		_add(result, run.text, run.color)
	if is_overridden(palette, "url"):
		return _link_segments(result, palette.url)
	return result

static func _run_color(line: Dictionary, key: String, index: int, wire: int, palette: Dictionary, active_channel: int) -> Color:
	var color: Color = Protocol.EL_TEXT_COLOURS[wire] if wire >= 0 and wire < Protocol.EL_TEXT_COLOURS.size() else Color.WHITE
	if wire < 0 and (not str(line.get("chat_role", "")).is_empty() or key in ["error", "connecting"]):
		color = palette[key]
	if key == "channel" and active_channel >= 0:
		var per_channel := channel_override_key(Messages.channel_number(line))
		if index == 0:
			var heading := "channel_inactive" if Messages.channel_number(line) > 0 and Messages.channel_number(line) != active_channel else "channel_active"
			color = palette.get(per_channel, palette[heading])
	elif key != "gm" and is_overridden(palette, key):
		color = palette[key]
	return color

static func _wire_colour(line: Dictionary) -> int:
	var runs: Array = line.get("text_runs", [])
	if not runs.is_empty():
		return int((runs[0] as Dictionary).get("colour", -1))
	var color := int(line.get("colour", 0))
	return color if color > 0 else -1

static func _add(result: Array[Dictionary], text: String, color: Color) -> void:
	if text.is_empty():
		return
	if not result.is_empty() and result.back().color == color:
		result.back().text = str(result.back().text) + text
	else:
		result.append({"text": text, "color": color})

static func _link_segments(input: Array[Dictionary], color: Color) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if _links == null:
		_links = RegEx.new()
		_links.compile("(?i)(?:https?://|www\\.)[^\\s]+")
	for segment: Dictionary in input:
		var text := str(segment.text)
		var offset := 0
		for found: RegExMatch in _links.search_all(text):
			_add(result, text.substr(offset, found.get_start() - offset), segment.color)
			_add(result, found.get_string(), color)
			offset = found.get_end()
		_add(result, text.substr(offset), segment.color)
	return result
