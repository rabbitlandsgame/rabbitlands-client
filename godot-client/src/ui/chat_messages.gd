extends RefCounted
## Shared classification for both HUD feeds and the full session log. The
## legacy wire uses category zero for both nearby speech and game feedback.
## Keep that compatibility parsing here, before any display labels are added.

static func kind(line: Dictionary) -> String:
	if line.has("kind"):
		return str(line.kind)
	var channel := int(line.get("channel", 0))
	if channel == 1:
		return "private"
	if channel == 2:
		return "guild"
	if channel in [5, 6, 7]:
		return "channel"
	if channel != 0:
		return "system"
	var text := str(line.get("text", ""))
	if text.begins_with("[Party] "):
		return "party"
	return "local" if not _plain_speaker(text).is_empty() else "system"

static func _plain_speaker(text: String) -> String:
	var at := text.find(": ")
	if at <= 0 or at > 30:
		return ""
	var candidate := text.substr(0, at)
	for character: String in candidate:
		if not character.to_lower() in "abcdefghijklmnopqrstuvwxyz0123456789_-":
			return ""
	# Common one-word legacy status labels are not player speech.
	if candidate.to_lower() in ["usage", "syntax", "error", "warning", "health",
			"ether", "food", "load", "time", "date", "research", "target"]:
		return ""
	return candidate

static func channel_number(line: Dictionary) -> int:
	if int(line.get("channel", 0)) in [5, 6, 7]:
		var text := str(line.get("text", ""))
		var end := text.find("] ")
		if text.begins_with("[") and end > 1:
			var number := text.substr(1, end - 1)
			if number.is_valid_int():
				return int(number)
	return int(line.get("channel_number", 0))

static func peer(line: Dictionary) -> String:
	if kind(line) != "private":
		return ""
	var text := str(line.get("text", ""))
	for prefix: String in ["[PM from ", "[PM to "]:
		if text.begins_with(prefix):
			return text.trim_prefix(prefix).get_slice(":", 0).strip_edges()
	return _plain_speaker(text)

static func speaker(line: Dictionary) -> String:
	var text := str(line.get("text", ""))
	match kind(line):
		"private":
			return "" if text.begins_with("[PM to ") else peer(line)
		"party":
			text = text.trim_prefix("[Party] ")
		"guild":
			text = text.trim_prefix("[Guild] ").trim_prefix("[GM] ")
		"channel":
			var end := text.find("] ")
			if text.begins_with("[") and end > 0:
				text = text.substr(end + 2)
	return _plain_speaker(text)

static func matches(line: Dictionary, section: String) -> bool:
	var category := kind(line)
	match section:
		"all", "history": return true
		"system": return category == "system"
		"chat": return category != "system"
		"general", "local": return category == "local"
		"party", "guild", "private", "channel": return category == section
	if section.begins_with("channel:"):
		return category == "channel" and channel_number(line) == int(section.trim_prefix("channel:"))
	if section.begins_with("pm:"):
		return category == "private" and peer(line).nocasecmp_to(section.trim_prefix("pm:")) == 0
	return false
