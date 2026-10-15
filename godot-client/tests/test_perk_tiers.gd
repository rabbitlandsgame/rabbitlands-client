extends SceneTree
## Perks bought a tier at a time.
##
## A perk used to be one purchase, and the catalogue row was the whole perk:
## its price, its description, and a Take button. It is now up to three, and
## the row is an *offer* - the price and the description belong to the tier
## this character would buy next, not to the perk.
##
## Which is why the two tier bytes have to be on the wire and cannot be
## inferred here. "3 pp" against a perk already held reads as a bug unless the
## window can say which step those three points buy.

const P := preload("res://src/network/protocol.gd")

var _failures := 0

func _init() -> void:
	_decoding()
	_refuses_a_row_without_its_tiers()
	_the_window_shows_the_shelf()
	_the_category_is_decoded()
	print("perk tiers: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _row(pickpoints: int, gold: int, owned: int, maximum: int,
		perk_name: String, description: String, blocker: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.append(pickpoints & 0xFF)
	bytes.append((pickpoints >> 8) & 0xFF)
	for shift: int in [0, 8, 16, 24]:
		bytes.append((gold >> shift) & 0xFF)
	bytes.append(owned)
	bytes.append(maximum)
	for text: String in [perk_name, description, blocker, "Combat"]:
		bytes.append_array(text.to_utf8_buffer())
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
	var payload := _payload([
		_row(4, 3000, 1, 3, "Lucky Hitter", "Fourteen percent more land.", ""),
		_row(-3, 0, 0, 1, "Power Hungry", "Lose 3 food per minute.",
			"You do not have enough pick points.")])
	var decoded: Dictionary = P.decode_server(
		P.ServerMessage.ELORIA_PERK_CATALOG, payload)
	_expect(decoded.type == "perk_catalog",
		"the catalogue decodes (%s)" % str(decoded.get("error", decoded.type)))
	var perks: Array = decoded.get("perks", [])
	_expect(perks.size() == 2, "both rows arrive")
	if perks.size() != 2:
		return
	var tiered: Dictionary = perks[0]
	_expect(int(tiered.tier) == 1 and int(tiered.max_tier) == 3,
		"a tiered perk carries what is held and what there is to hold")
	_expect(int(tiered.pickpoints) == 4,
		"the price is the next tier's, not the perk's first")
	var flat: Dictionary = perks[1]
	_expect(int(flat.tier) == 0 and int(flat.max_tier) == 1,
		"a one-tier perk reads as one tier")
	_expect(int(flat.pickpoints) == -3,
		"a perk that pays pick points out survives the signed field")
	_expect(str(flat.blocker) == "You do not have enough pick points.",
		"the refusal is the server's own sentence")

func _refuses_a_row_without_its_tiers() -> void:
	# The tier bytes sit between the price and the strings, so a payload cut
	# there would otherwise read a name out of the middle of a number.
	var truncated := _payload([_row(4, 3000, 1, 3, "A", "B", "")])
	truncated.resize(8)
	_expect(P.decode_server(P.ServerMessage.ELORIA_PERK_CATALOG,
		truncated).type == "invalid", "a row cut at its tier bytes is refused")
	var trailing := _payload([_row(4, 3000, 1, 3, "A", "B", "")])
	trailing.append(0)
	_expect(P.decode_server(P.ServerMessage.ELORIA_PERK_CATALOG,
		trailing).type == "invalid", "a byte the count did not promise is refused")

func _the_window_shows_the_shelf() -> void:
	var source: String = FileAccess.get_file_as_string("res://src/app/main.gd")
	_expect(not source.is_empty(), "main.gd is readable")
	_expect(source.contains("max_tier"),
		"the perk row reads the tier the server sent")
	# The tier strip is the whole system at a glance, which a sentence
	# saying "tier 1 of 3" is not.
	_expect(source.contains("func _perk_pips("),
		"a row draws one box per tier")
	_expect(source.contains("\"%d / %d\""),
		"and the count under them")
	# A perk with nothing left to sell stops offering to sell it.
	_expect(source.contains("\"OWNED\"") and source.contains("\"TAKE\""),
		"the button says TAKE until there is nothing left, then OWNED")
	_expect(source.contains("func _sync_perk_filters("),
		"the tabs are built from the categories the server sent")
	_expect(source.contains("perk.get(\"category\", \"\")"),
		"and a row is filtered by the category it arrived with")
	_expect(P.CLIENT_CAPABILITIES.has("perk_catalog_v3"),
		"the layout carrying the category is what this client asks for")
	_expect(not P.CLIENT_CAPABILITIES.has("perk_catalog_v2"),
		"and it does not also claim a layout it no longer decodes")

func _the_category_is_decoded() -> void:
	var payload := _payload([_row(4, 3000, 1, 3, "Closer", "Nearer.", "")])
	var decoded: Dictionary = P.decode_server(
		P.ServerMessage.ELORIA_PERK_CATALOG, payload)
	var perks: Array = decoded.get("perks", [])
	_expect(perks.size() == 1 and str((perks[0] as Dictionary).get(
		"category", "")) == "Combat", "the row carries its tab")

func _expect(condition: bool, description: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("perk tiers: %s" % description)
	printerr("FAIL ", description)
