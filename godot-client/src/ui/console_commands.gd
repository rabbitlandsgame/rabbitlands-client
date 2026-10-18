class_name ConsoleCommands
extends RefCounted
## The commands this client answers itself.
##
## The console showed text and had no command table at all, so every `#`
## command went out as raw text - including the ones no server has ever
## implemented, which came back as "unknown command" or silence. These are the
## ones that are about the player's own screen: their markers, who they are
## ignoring, what they have filtered out, their aliases, an arithmetic helper,
## and a search over what they have already been told.
##
## Nothing here touches gameplay. Every command either changes something the
## client owns - a marker on the player's own map, a filter on their own chat -
## or reports something the client was already told. Anything else is passed
## through to the server untouched, because deciding locally what the server
## should have answered is exactly the mistake this codebase avoids.

## What running a command produced: lines to show the player, whether the
## client handled it at all, whether anything persistent changed, and whether
## the line still goes on to the server.
class Result:
	var handled: bool
	## Plain `Array` rather than `Array[String]`: a typed array parameter will
	## not accept an untyped literal at a call site, and every call site here
	## builds one inline.
	var lines: Array
	var changed: bool
	## Only `#help` sets this. Each side lists the commands it answers, so
	## the client never has to know the server's table, nor the server the
	## client's.
	var send_on: bool

	func _init(was_handled: bool, output: Array = [],
			state_changed: bool = false, also_send: bool = false) -> void:
		handled = was_handled
		lines = output
		changed = state_changed
		send_on = also_send

const COMMANDS := {
	"#help": "List this client's commands, then the server's.",
	"#calc": "Evaluate arithmetic: #calc 12 * (3 + 4)",
	"#mark": "Mark your current tile: #mark <label>",
	"#markpos": "Mark a tile: #markpos <x> <y> <label>",
	"#unmark": "Remove a mark on this map: #unmark <label>",
	"#marks": "List your marks on this map.",
	"#ignore": "Hide someone's local, channel and private messages: #ignore <name>",
	"#unignore": "Show someone's messages again: #unignore <name>",
	"#ignores": "List who you are ignoring.",
	"#filter": "Hide chat containing a word: #filter <word>",
	"#unfilter": "Stop hiding a word: #unfilter <word>",
	"#filters": "List your chat filters.",
	"#alias": "Make a shorthand: #alias <name> <text>",
	"#unalias": "Remove a shorthand: #unalias <name>",
	"#aliases": "List your shorthands.",
	"#afk": "Set or clear your away message: #afk [reason]",
	"#find": "Search what you have been told: #find <text>",
	"#session_counters": "Show what this session has counted.",
}

## Player-owned state. All of it is about this screen, and all of it persists
## in the client's own settings file rather than on the server.
var marks: Array[Dictionary] = []
var ignored: Array[String] = []
var filters: Array[String] = []
var aliases: Dictionary = {}
var afk_reason := ""

## Set by the owner so location-aware commands can answer. Kept as plain data
## rather than a node reference so this class stays testable on its own.
var current_map := ""
var current_tile: Variant = null

## Every address in a line the server said. Detection only: nothing is opened,
## nothing is fetched, and the text is left exactly as it arrived.
static func urls_in(text: String) -> Array[String]:
	var found: Array[String] = []
	var pattern := RegEx.create_from_string(
		"(?i)(?<![a-z0-9_@/:])(?:https?://|www\\.)[^\\s<>\"\\x00-\\x1f]+")
	for match_value: RegExMatch in pattern.search_all(text):
		var candidate := match_value.get_string()
		# Keep balanced parentheses that belong to a path, while removing
		# surrounding chat/PM brackets and sentence punctuation.
		while not candidate.is_empty():
			var last := candidate.right(1)
			if last in [".", ",", ";", ":", "!", "?", "'", "’", "”"]:
				candidate = candidate.left(-1)
			elif (last == ")" and candidate.count(")") > candidate.count("(")) \
					or (last == "]" and candidate.count("]") > candidate.count("[")) \
					or (last == "}" and candidate.count("}") > candidate.count("{")):
				candidate = candidate.left(-1)
			else:
				break
		if not web_url(candidate).is_empty():
			found.append(candidate)
	return found

## The only addresses we hand to the system browser. Bare www links use HTTPS.
static func web_url(address: String) -> String:
	var url := address.strip_edges()
	if url.to_lower().begins_with("www."):
		url = "https://" + url
	var scheme_end := url.find("://")
	if scheme_end < 0 or url.left(scheme_end).to_lower() not in ["http", "https"]:
		return ""
	var authority := url.substr(scheme_end + 3).get_slice("/", 0).get_slice("?", 0).get_slice("#", 0)
	var host := RegEx.create_from_string("^(?:\\[[0-9a-fA-F:.]+\\]|[\\p{L}\\p{N}_.-]+)(?::[0-9]{1,5})?$")
	if authority.is_empty() or host.search(authority) == null:
		return ""
	return url.left(scheme_end).to_lower() + url.substr(scheme_end)

## Whether a chat line survives the player's own ignore and filter lists.
func allows(speaker: String, text: String) -> bool:
	var lowered_speaker: String = speaker.to_lower()
	for name: String in ignored:
		if lowered_speaker == name or lowered_speaker.begins_with(name + " "):
			return false
	var lowered_text: String = text.to_lower()
	for word: String in filters:
		if lowered_text.contains(word):
			return false
	return true

## Expands a shorthand at the start of a line. Returns the line unchanged when
## nothing matches, so an alias can never eat an ordinary message.
func expand(text: String) -> String:
	var head: String = text.split(" ", false, 1)[0] if not text.is_empty() else ""
	if head.is_empty() or not aliases.has(head):
		return text
	var rest: String = text.substr(head.length()).strip_edges()
	var expansion: String = str(aliases[head])
	return expansion if rest.is_empty() else expansion + " " + rest

## Command names beginning with `prefix`, for tab completion.
func completions(prefix: String) -> Array[String]:
	var found: Array[String] = []
	for name: Variant in COMMANDS:
		if str(name).begins_with(prefix):
			found.append(str(name))
	found.sort()
	return found

func run(text: String, history: Array = []) -> Result:
	var parts: PackedStringArray = text.strip_edges().split(" ", false)
	if parts.is_empty():
		return Result.new(false)
	var command: String = parts[0].to_lower()
	var argument: String = text.strip_edges().substr(command.length()).strip_edges()
	match command:
		"#help":
			return Result.new(true, _help(), false, true)
		"#calc":
			return Result.new(true, [_calculate(argument)])
		"#mark":
			return _mark(current_tile, argument)
		"#markpos":
			return _markpos(parts, argument)
		"#unmark":
			return _unmark(argument)
		"#marks":
			return Result.new(true, _list_marks())
		"#ignore":
			return _add_to("ignore", ignored, argument)
		"#unignore":
			return _remove_from("ignore", ignored, argument)
		"#ignores":
			return Result.new(true, [_joined("Ignoring", ignored)])
		"#filter":
			return _add_to("filter", filters, argument)
		"#unfilter":
			return _remove_from("filter", filters, argument)
		"#filters":
			return Result.new(true, [_joined("Filtering", filters)])
		"#alias":
			return _alias(argument)
		"#unalias":
			return _unalias(argument)
		"#aliases":
			return Result.new(true, _list_aliases())
		"#afk":
			afk_reason = argument
			return Result.new(true, ["Away: " + argument] if not argument.is_empty()
				else ["No longer away."], true)
		"#find":
			return Result.new(true, _find(argument, history))
		"#session_counters":
			return Result.new(true, _session_counters(history))
	return Result.new(false)

func _help() -> Array[String]:
	var lines: Array[String] = ["This client answers these itself:"]
	for name: Variant in COMMANDS:
		lines.append("  %s - %s" % [str(name), str(COMMANDS[name])])
	lines.append("Everything else is sent to the server as you typed it.")
	return lines

## Arithmetic only. `Expression` would happily run any GDScript, so the input
## is refused unless it is digits, spaces, brackets and operators.
func _calculate(argument: String) -> String:
	if argument.is_empty():
		return "Usage: #calc 12 * (3 + 4)"
	for character: String in argument:
		if not character in "0123456789.+-*/%() \t":
			return "#calc takes numbers and + - * / %% ( ) only."
	var expression := Expression.new()
	if expression.parse(argument) != OK:
		return "#calc could not read that: " + expression.get_error_text()
	var value: Variant = expression.execute([], null, false)
	if expression.has_execute_failed():
		return "#calc could not work that out."
	return "%s = %s" % [argument, str(value)]

func _mark(tile: Variant, label: String) -> Result:
	if not tile is Vector2i or current_map.is_empty():
		return Result.new(true, ["There is nowhere to mark yet."])
	return _store_mark(tile, label if not label.is_empty() else "Mark")

func _markpos(parts: PackedStringArray, argument: String) -> Result:
	if parts.size() < 3 or not parts[1].is_valid_int() or not parts[2].is_valid_int():
		return Result.new(true, ["Usage: #markpos <x> <y> <label>"])
	var label: String = argument.substr(
		parts[1].length() + parts[2].length() + 1).strip_edges()
	return _store_mark(Vector2i(int(parts[1]), int(parts[2])),
		label if not label.is_empty() else "Mark")

func _store_mark(tile: Vector2i, label: String) -> Result:
	for mark: Dictionary in marks:
		if str(mark.get("label", "")) == label and str(mark.get("map", "")) == current_map:
			mark["x"] = tile.x
			mark["y"] = tile.y
			return Result.new(true, ["Moved mark %s to %d, %d." % [label, tile.x, tile.y]], true)
	marks.append({"map": current_map, "x": tile.x, "y": tile.y, "label": label})
	return Result.new(true, ["Marked %s at %d, %d." % [label, tile.x, tile.y]], true)

func _unmark(label: String) -> Result:
	for index: int in range(marks.size()):
		if str(marks[index].get("label", "")) == label \
				and str(marks[index].get("map", "")) == current_map:
			marks.remove_at(index)
			return Result.new(true, ["Removed mark %s." % label], true)
	return Result.new(true, ["You have no mark called %s on this map." % label])

func _list_marks() -> Array[String]:
	var lines: Array[String] = []
	for mark: Dictionary in marks:
		if str(mark.get("map", "")) == current_map:
			lines.append("  %s at %d, %d" % [str(mark.get("label", "")),
				int(mark.get("x", 0)), int(mark.get("y", 0))])
	if lines.is_empty():
		return ["You have no marks on this map."]
	lines.push_front("Your marks here:")
	return lines

func _add_to(kind: String, list: Array[String], argument: String) -> Result:
	var value: String = argument.strip_edges().to_lower()
	if value.is_empty():
		return Result.new(true, ["Usage: #%s <name>" % kind])
	if list.has(value):
		return Result.new(true, ["Already on your %s list: %s" % [kind, value]])
	list.append(value)
	list.sort()
	return Result.new(true, ["Added %s to your %s list." % [value, kind]], true)

func _remove_from(kind: String, list: Array[String], argument: String) -> Result:
	var value: String = argument.strip_edges().to_lower()
	if not list.has(value):
		return Result.new(true, ["%s is not on your %s list." % [value, kind]])
	list.erase(value)
	return Result.new(true, ["Removed %s from your %s list." % [value, kind]], true)

func _joined(label: String, list: Array[String]) -> String:
	return "%s: %s" % [label, ", ".join(list) if not list.is_empty() else "nobody"]

func _alias(argument: String) -> Result:
	var parts: PackedStringArray = argument.split(" ", false, 1)
	if parts.size() < 2:
		return Result.new(true, ["Usage: #alias <name> <text>"])
	aliases[parts[0]] = parts[1]
	return Result.new(true, ["%s now means: %s" % [parts[0], parts[1]]], true)

func _unalias(argument: String) -> Result:
	var name: String = argument.strip_edges()
	if not aliases.has(name):
		return Result.new(true, ["You have no shorthand called %s." % name])
	aliases.erase(name)
	return Result.new(true, ["Removed the shorthand %s." % name], true)

func _list_aliases() -> Array[String]:
	if aliases.is_empty():
		return ["You have no shorthands."]
	var lines: Array[String] = ["Your shorthands:"]
	for name: Variant in aliases:
		lines.append("  %s - %s" % [str(name), str(aliases[name])])
	return lines

## Searches what the client has already been told. It reads the chat the
## server sent and answers nothing of its own.
func _find(argument: String, history: Array) -> Array[String]:
	var needle: String = argument.strip_edges().to_lower()
	if needle.is_empty():
		return ["Usage: #find <text>"]
	var found: Array[String] = []
	for line_value: Variant in history:
		var line: String = str((line_value as Dictionary).get("text", ""))
		if line.to_lower().contains(needle):
			found.append("  " + line)
	if found.is_empty():
		return ["Nothing said so far contains %s." % needle]
	found.push_front("%d line(s) contain %s:" % [found.size(), needle])
	return found

func _session_counters(history: Array) -> Array[String]:
	return ["This session: %d chat line(s) received, %d mark(s), %d ignored,"
		% [history.size(), marks.size(), ignored.size()]
		+ " %d filter(s), %d shorthand(s)." % [filters.size(), aliases.size()]]
