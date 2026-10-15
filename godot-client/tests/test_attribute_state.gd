extends SceneTree
## The attributes a character can buy, as the server names them.
##
## This client used to hold the list itself: six attributes drawn from fixed
## slots of the stats packet, and nine more it derived from those six by
## averaging pairs. Both halves are now wrong - the six were deleted and the
## nine are bought directly - and the window showed them anyway, because
## nothing in a positional packet can say that a name has stopped existing.
##
## So the names travel with the values. What is tested here is mostly that:
## that the client reads the set rather than knowing it, that a ceiling is the
## server's to state, and that the six-slot fallback is reached only by a
## server old enough for those six names to still be true.

const P := preload("res://src/network/protocol.gd")

var _failures := 0

func _init() -> void:
	_decoding()
	_rejects_a_short_packet()
	_the_window_reads_the_server()
	print("attribute state: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

# --- the packet -------------------------------------------------------------

func _row(key: String, label: String, value: int, maximum: int) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.append(value & 0xFF)
	bytes.append((value >> 8) & 0xFF)
	bytes.append(maximum & 0xFF)
	bytes.append((maximum >> 8) & 0xFF)
	bytes.append_array(key.to_utf8_buffer())
	bytes.append(0)
	bytes.append_array(label.to_utf8_buffer())
	bytes.append(0)
	return bytes

func _payload(rows: Array) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append(rows.size() & 0xFF)
	payload.append((rows.size() >> 8) & 0xFF)
	for row: Variant in rows:
		payload.append_array(row as PackedByteArray)
	return payload

func _decoding() -> void:
	var payload := _payload([_row("matter", "Matter", 12, 100),
		_row("magic_offense", "Magic Offense", 4, 100)])
	var decoded: Dictionary = P.decode_server(
		P.ServerMessage.ELORIA_ATTRIBUTE_STATE, payload)
	_expect(decoded.type == "attribute_state",
		"the packet decodes (%s)" % str(decoded.get("error", decoded.type)))
	var rows: Array = decoded.get("attributes", [])
	_expect(rows.size() == 2, "both attributes arrive")
	if rows.size() != 2:
		return
	var first: Dictionary = rows[0]
	_expect(str(first.key) == "matter", "the key is the one the server spends on")
	_expect(int(first.value) == 12, "the value is the character's")
	_expect(int(first.maximum) == 100, "the ceiling comes from the server")
	# `magic_offense`.capitalize() is "Magic offense" and .title()-ing the key
	# gives "Magic_Offense". Neither is a name to show, so the server sends one.
	_expect(str((rows[1] as Dictionary).label) == "Magic Offense",
		"the label is written, not derived from the key")

func _rejects_a_short_packet() -> void:
	# A row cut off mid-name has to fail rather than decode to a blank
	# attribute, which the window would draw as a nameless buyable line.
	var truncated := _payload([_row("matter", "Matter", 12, 100)])
	truncated.resize(truncated.size() - 3)
	var decoded: Dictionary = P.decode_server(
		P.ServerMessage.ELORIA_ATTRIBUTE_STATE, truncated)
	_expect(decoded.type == "invalid", "a truncated row is refused")
	var trailing := _payload([_row("matter", "Matter", 12, 100)])
	trailing.append(0)
	_expect(P.decode_server(P.ServerMessage.ELORIA_ATTRIBUTE_STATE,
		trailing).type == "invalid", "a row the count did not promise is refused")

# --- the window -------------------------------------------------------------

func _the_window_reads_the_server() -> void:
	# Read as source rather than driven: the statistics document is built
	# inside a scene this suite does not stand up. What matters is that no
	# copy of the attribute list survives outside the fallback.
	var source: String = FileAccess.get_file_as_string("res://src/app/main.gd")
	_expect(not source.is_empty(), "main.gd is readable")
	_expect(source.contains("AppState.attributes"),
		"the window draws the attributes the server sent")
	_expect(not source.contains("_cross_pair"),
		"the client no longer averages two attributes into a third")
	for gone: String in ["\"physique\"", "\"coordination\"", "\"reasoning\"",
			"\"vitality\"", "\"instinct\""]:
		var occurrences: int = source.count(gone)
		_expect(occurrences <= 1,
			"%s survives only in the legacy fallback (%d uses)" % [gone, occurrences])
	_expect(source.contains("LEGACY_ATTRIBUTES"),
		"the six fixed slots are still readable from a server that sends no more")

# --- harness ----------------------------------------------------------------

func _expect(condition: bool, description: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("attribute state: %s" % description)
	printerr("FAIL ", description)
