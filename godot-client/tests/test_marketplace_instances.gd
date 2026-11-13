extends SceneTree
## market_instance_tiers_v1: which equipment copy an Exchange listing holds.
##
## Plain and enchanted copies share a name and an icon, so without this a buyer
## could not tell a magic Phoenix Helm from a plain one. The fixtures are real
## server marketplace_state packets (eloria/marketplace_window.state_packet,
## frozen clock), one with the capability and one without:
##   1 Slate x5 (a stackable: no copies)    2 Phoenix Helm, plain
##   3 Phoenix Helm, magic (Emberstrike)    4 Phoenix Helm, rare (3 effects)
##   5 Phoenix Helm x3: one magic copy, then two plain, as a purchase takes them

const InstanceTiers := preload("res://src/state/item_instance_tiers.gd")
const EMBER := "Emberstrike: 100% chance on a landed hit to deal 8 bonus damage."

var failures := 0
var windows: Control
var state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var fixtures: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://tests/fixtures/marketplace_instances.json")) as Dictionary
	var browse: PackedByteArray = str(fixtures.browse).hex_decode()
	var without: PackedByteArray = str(fixtures.without_capability).hex_decode()
	_check_decoder(browse, without)
	state = root.get_node("/root/AppState")
	windows = (load("res://src/ui/extension_windows.gd") as GDScript).new() as Control
	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")) as Dictionary)
	windows.configure(atlas)
	root.add_child(windows)
	await process_frame
	await _check_window(browse, without)
	windows.queue_free()
	await process_frame
	print("marketplace instance tiers: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_decoder(browse: PackedByteArray, without: PackedByteArray) -> void:
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("market_instance_tiers_v1"),
		"the client asks for listing copies")
	var decoded: Dictionary = EloriaProtocol.decode_marketplace(browse)
	_expect(decoded.type == "marketplace" and int(decoded.version) == 3,
		"a v3 packet carrying copies decodes")
	var rows: Dictionary = _by_id(decoded)
	_expect(not (rows[1] as Dictionary).has("instance_tier")
		and not (rows[1] as Dictionary).has("copies"), "a stackable has no copies")
	_expect(str(rows[2].instance_tier) == "normal"
		and _same(rows[2].copies, [{"tier": "normal", "quantity": 1, "effects": []}])
		and int(rows[2].more_copies) == 0, "a plain listing says it is plain")
	_expect(str(rows[3].instance_tier) == "magic"
		and _same(rows[3].copies, [{"tier": "magic", "quantity": 1, "effects": [EMBER]}]),
		"a magic listing carries its tier and effect line")
	_expect(str(rows[4].instance_tier) == "rare"
		and _same(rows[4].copies[0].effects, ["Plated: +20 armor.",
			"Vital: +30 maximum health.", EMBER]), "a rare listing carries every effect line")
	_expect(str(rows[5].instance_tier) == "magic" and _same(rows[5].copies, [
		{"tier": "magic", "quantity": 1, "effects": [EMBER]},
		{"tier": "normal", "quantity": 2, "effects": []}]),
		"a mixed listing keeps its best tier and its copies in purchase order")
	var old: Dictionary = EloriaProtocol.decode_marketplace(without)
	_expect(old.type == "marketplace" and int(old.version) == 3
		and (old.listings as Array).size() == 5,
		"the same page without the capability decodes as before")
	for listing: Dictionary in old.listings:
		_expect(not listing.has("instance_tier") and not listing.has("copies"),
			"no copies are invented for listing %d" % int(listing.listing_id))
	# Malformed copies refuse the packet rather than show a wrong tier.
	var broken: Array[Callable] = [
		func(copies: Dictionary) -> void: copies["3"]["tier"] = "legendary",
		func(copies: Dictionary) -> void: copies["3"]["copies"][0]["quantity"] = 0,
		func(copies: Dictionary) -> void: copies["3"]["copies"][0]["quantity"] = 1.5,
		func(copies: Dictionary) -> void: copies["3"]["copies"][0]["effects"] = [7],
		func(copies: Dictionary) -> void: copies["3"]["more"] = -1,
		func(copies: Dictionary) -> void: copies["three"] = copies["3"],
		func(copies: Dictionary) -> void: copies["3"] = "magic"]
	for index: int in range(broken.size()):
		_expect(str(EloriaProtocol.decode_marketplace(_with_copies(browse, broken[index])).type) == "invalid",
			"malformed copies case %d is refused" % index)
	_expect(str(EloriaProtocol.decode_marketplace(_with_copies(browse,
		func(copies: Dictionary) -> void: copies["999"] = copies["3"])).type) == "marketplace",
		"copies for a listing not on the page are ignored")
	_expect(str(EloriaProtocol.decode_marketplace(browse.slice(0, browse.size() - 1)).type) == "invalid",
		"a truncated packet is refused")

func _check_window(browse: PackedByteArray, without: PackedByteArray) -> void:
	state.call("_on_packet", 222, browse)
	await _settle()
	var list: ItemList = windows.market_list
	_expect(windows.market_panel.visible and list.item_count == 5, "the page shows five rows")
	var plain: int = _row(2)
	var magic: int = _row(3)
	var rare: int = _row(4)
	var mixed: int = _row(5)
	var slate: int = _row(1)
	_expect(list.get_item_text(magic).begins_with("Phoenix Helm (Magic)  ×1")
		and list.get_item_text(rare).begins_with("Phoenix Helm (Rare)  ×1")
		and list.get_item_text(mixed).begins_with("Phoenix Helm (Magic)  ×3"),
		"enchanted rows name their tier")
	_expect(list.get_item_text(plain).begins_with("Phoenix Helm  ×1")
		and list.get_item_text(slate).begins_with("Slate  ×5"), "plain rows read as before")
	_expect(list.get_item_custom_fg_color(magic) == InstanceTiers.color("magic")
		and list.get_item_custom_fg_color(rare) == InstanceTiers.color("rare")
		and list.get_item_custom_fg_color(mixed) == InstanceTiers.color("magic"),
		"enchanted rows take their tier colour")
	for row: int in [plain, slate]:
		_expect(list.get_item_custom_fg_color(row) != InstanceTiers.color("magic")
			and list.get_item_custom_fg_color(row) != InstanceTiers.color("rare"),
			"row %d keeps the ordinary colour" % row)
	_expect(list.get_item_tooltip(magic).ends_with("Magic copy: " + EMBER),
		"the row tooltip lists the effects")
	await _select(magic)
	_expect(windows.market_copies.visible
		and windows.market_copies.text == "Magic copy: " + EMBER
		and windows.market_copies.get_theme_color("font_color") == InstanceTiers.color("magic"),
		"selecting a magic listing shows its effects in the magic colour")
	await _select(rare)
	_expect(windows.market_copies.text == "Rare copy: Plated: +20 armor.  ·  Vital: +30 maximum health.  ·  " + EMBER
		and windows.market_copies.get_theme_color("font_color") == InstanceTiers.color("rare"),
		"a rare listing shows every effect")
	_expect(windows.market_panel.size.x <= 840 and windows.market_panel.size.y <= 600,
		"the Exchange keeps its size with the longest copy detail")
	_expect(windows.market_copies.size.y <= 40.0 and windows.market_list.size.y >= 180.0,
		"a rare copy's effects take two lines at most, leaving the list its rows")
	await _capture("auction-instance-tiers.png")
	await _select(plain)
	_expect(windows.market_copies.visible and windows.market_copies.text == "Plain copy: no enchantments.",
		"a plain listing says so")
	await _select(mixed)
	_expect(windows.market_copies.text == "Copies, in the order a purchase takes them:\n1 magic: "
		+ EMBER + "\n2 plain", "a mixed listing lists its copies in purchase order")
	await _select(slate)
	_expect(not windows.market_copies.visible, "a stackable has no copy line")
	# A server without the capability: the window looks exactly as it did.
	state.call("_on_packet", 222, without)
	await _settle()
	_expect(list.get_item_text(_row(3)).begins_with("Phoenix Helm  ×1")
		and list.get_item_custom_fg_color(_row(3)) != InstanceTiers.color("magic"),
		"without copies the row carries no tier")
	await _select(_row(3))
	_expect(not windows.market_copies.visible, "without copies there is no copy line")

func _by_id(decoded: Dictionary) -> Dictionary:
	var rows: Dictionary = {}
	for listing: Dictionary in decoded.listings:
		rows[int(listing.listing_id)] = listing
	return rows

func _row(listing_id: int) -> int:
	var list: ItemList = windows.market_list
	for row: int in range(list.item_count):
		if int(list.get_item_metadata(row)) == listing_id:
			return row
	_expect(false, "listing %d has a row" % listing_id)
	return 0

func _select(row: int) -> void:
	windows.market_list.select(row)
	windows._on_market_selected(row)
	await _settle()

## The browse fixture with its v3 JSON's "copies" changed by `change`.
func _with_copies(packet: PackedByteArray, change: Callable) -> PackedByteArray:
	var start: int = _json_start(packet)
	var details: Dictionary = JSON.parse_string(packet.slice(start, packet.size() - 1)
		.get_string_from_utf8()) as Dictionary
	change.call(details.copies)
	var result: PackedByteArray = packet.slice(0, start)
	result.append_array(JSON.stringify(details).to_utf8_buffer())
	result.append(0)
	return result

## Where the v3 JSON object begins (a "{" byte may also occur in the rows).
func _json_start(packet: PackedByteArray) -> int:
	var marker: String = '{"view":'.to_utf8_buffer().hex_encode()
	var text: String = packet.hex_encode()
	var at: int = text.find(marker)
	while at >= 0 and at % 2 != 0:
		at = text.find(marker, at + 1)
	return at / 2

## Godot compares array element types; JSON text compares the values.
func _same(actual: Variant, expected: Variant) -> bool:
	return JSON.stringify(actual) == JSON.stringify(expected)

func _settle() -> void:
	for _frame: int in range(5):
		await process_frame

func _capture(filename: String) -> void:
	var directory: String = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if directory.is_empty():
		return
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(directory)
	var picture: Image = root.get_texture().get_image()
	_expect(picture != null and picture.save_png(directory.path_join(filename)) == OK,
		"the rendered preview is saved")

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
