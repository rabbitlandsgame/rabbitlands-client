extends SceneTree
## Guards the Summoning window and the two seams it depends on.
##
## The window is a view of two honest sources: the client's own compiled
## recipe catalog, and the server's state in AppState - inventory, skills,
## nexus, ether. It lists the summons alone, dims what the client can see no
## way to call, writes the first blocking reason where the ingredients would
## go, and its rows only ask: a click hands the ingredient picks to a
## Callable and the server decides whether anything is standing there
## afterwards.
##
## The last section is not about the window. It is the wire fact the window
## exists to be reachable from: a summon's actor packet says "summon" only in
## the colour byte on its name, and it now also carries the summoner's guild
## tag. Both are decoded here through the client's real decoder, because the
## click that opens the behaviour popup is gated on the first and the
## nameplate is drawn from the second.

var failures := 0
var summoned: Array = []
var behavior_requests := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var app_state: Node = root.get_node("/root/AppState")
	var stats: Dictionary = app_state.get("stats") as Dictionary
	var inventory: Dictionary = app_state.get("inventory") as Dictionary
	var slot_names: Dictionary = app_state.get("inventory_names") as Dictionary
	stats.clear()
	inventory.clear()
	slot_names.clear()

	var catalog := ManufacturingCatalog.new()
	catalog.configure(_json("res://data/manufacturing/recipes.json"))
	var atlas := ItemAtlas.new()
	atlas.configure(_json("res://data/items/atlases.json"))

	var window: Control = (load("res://src/ui/summoning_window.gd")
		as GDScript).new() as Control
	root.add_child(window)
	await process_frame
	window.call("configure", catalog, atlas,
		func(selection: Array[Dictionary]) -> void: summoned.append(selection),
		func() -> void: behavior_requests += 1)
	var panel: PanelContainer = window.get_node("SummoningWindow") as PanelContainer

	_expect(not panel.visible, "the summoning window starts closed")
	window.call("toggle")
	await process_frame
	_expect(panel.visible and bool(window.call("is_open")), "toggle opens it")
	var rect: Rect2 = panel.get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 - float(window.get("RESERVED_RIGHT_RAIL"))
		and rect.end.y <= 720.0,
		"it fits 1280x720 clear of the resource rail: %s" % rect)

	# Only the summons, and every one of them. The catalog holds five hundred
	# and thirty-two recipes across seven skills; the window is not another
	# manufacture list.
	var listed: Array[int] = window.call("summon_recipes") as Array[int]
	var names: Array[String] = []
	for index: int in listed:
		names.append(str(catalog.recipe(index).get("output", "")))
	_expect(names == ["Otter", "Crown Stag", "Crystalback Tortoise"],
		"the three profile summons are listed, cheapest first: %s" % str(names))
	for index: int in range(catalog.count()):
		if str(catalog.recipe(index).get("skill", "")) != "summoning":
			_expect(not listed.has(index),
				"recipe %d is not a summon and is not listed" % index)

	var rows: VBoxContainer = window.get_node(
		"SummoningWindow/SummoningBody/SummoningScroll/SummonRows") as VBoxContainer
	_expect(rows.get_child_count() == 3, "one row per summon: %d"
		% rows.get_child_count())
	var otter: Button = rows.get_node("SummonRow%d" % listed[0]) as Button
	var turtle: Button = rows.get_node("SummonRow%d" % listed[2]) as Button

	# The row reads left to right: icon, name, then what it asks for.
	var icon: TextureRect = otter.get_node("Row/Icon") as TextureRect
	_expect(icon.texture is Texture2D,
		"a summon leaves no item behind, so the row falls back to the atlas glyph")
	_expect(str((otter.get_node("Row/Name") as Label).text)
		== "Otter", "the name sits beside the icon")
	var otter_cost: Label = otter.get_node("Row/Asks/Cost") as Label
	_expect(otter_cost.text.contains("Mana 5")
		and otter_cost.text.contains("Summoning 0"),
		"the costs are written to the right: " + otter_cost.text)
	var turtle_cost: Label = turtle.get_node("Row/Asks/Cost") as Label
	_expect(turtle_cost.text.contains("Animal Nexus 2")
		and turtle_cost.text.contains("Mana 14"),
		"a nexus requirement is stated where there is one: " + turtle_cost.text)
	_expect(not otter_cost.text.contains("Animal Nexus"),
		"and left off where there is none: " + otter_cost.text)

	# With nothing owned, nothing can be summoned: dimmed, not hidden, with
	# the reason where the ingredients would be.
	window.call("sync")
	var blocked_alpha: float = float(window.get("BLOCKED_ALPHA"))
	_expect(otter.disabled and is_equal_approx(otter.modulate.a, blocked_alpha),
		"an unaffordable summon is dimmed and unclickable: %f" % otter.modulate.a)
	var otter_note: Label = otter.get_node("Row/Asks/Requirements") as Label
	_expect(otter_note.text == "Waiting for server statistics",
		"and says why: " + otter_note.text)
	otter.pressed.emit()
	_expect(summoned.is_empty(),
		"a blocked row asks for nothing: %s" % str(summoned))

	# The server grants the skill and the ingredients; the window follows.
	stats["summoning"] = 20
	stats["animal_nexus"] = 0
	stats["food"] = 40
	stats["ether"] = 60
	# Stocked from the catalog's own image ids rather than from a list written
	# out here. The ids are the server's, and it renumbered 43 of them once
	# already: a fixture that spells them out goes on passing against artwork
	# the server stopped using, which is exactly how the shipped catalog came
	# to hunt for an Aether Salt nobody had.
	var slot_of_ingredient: Dictionary = _stock(inventory, slot_names, catalog, listed)
	window.call("sync")
	_expect(not otter.disabled and is_equal_approx(otter.modulate.a, 1.0),
		"a summon the client can see no obstacle to is lit and clickable")
	_expect(otter_note.text.contains("Bones x1")
		and otter_note.text.contains("Reed x2"),
		"and lists what it will spend: " + otter_note.text)

	# The nexus is the requirement the manufacture window never asked about,
	# and the server refuses the mix without it.
	var turtle_note: Label = turtle.get_node("Row/Asks/Requirements") as Label
	_expect(turtle.disabled and turtle_note.text == "Needs Animal Nexus 2",
		"the turtle is held back by its nexus: " + turtle_note.text)
	stats["animal_nexus"] = 2
	window.call("sync")
	_expect(not turtle.disabled,
		"and released once the server says the nexus is there")
	stats["summoning"] = 19
	window.call("sync")
	_expect(turtle.disabled and turtle_note.text == "Needs summoning level 20",
		"the skill level is checked too: " + turtle_note.text)
	stats["summoning"] = 20
	window.call("sync")

	# Clicking only asks, and it asks with the slots the catalog picked.
	otter.pressed.emit()
	_expect(summoned.size() == 1, "clicking a summon asks once: %d" % summoned.size())
	var request: Array = summoned[0] as Array
	var slots: Array[int] = []
	var quantities: Array[int] = []
	for pick_value: Variant in request:
		var pick: Dictionary = pick_value as Dictionary
		slots.append(int(pick.get("slot", -1)))
		quantities.append(int(pick.get("quantity", 0)))
	var wanted_slots: Array[int] = []
	var wanted_quantities: Array[int] = []
	for ingredient_value: Variant in catalog.recipe(listed[0]).get("ingredients", []) as Array:
		var ingredient: Dictionary = ingredient_value as Dictionary
		wanted_slots.append(int(slot_of_ingredient[str(ingredient.get("name", ""))]))
		wanted_quantities.append(int(ingredient.get("quantity", 0)))
	_expect(slots == wanted_slots and quantities == wanted_quantities,
		"with the inventory slots holding each ingredient: %s %s, wanted %s %s"
		% [str(slots), str(quantities), str(wanted_slots), str(wanted_quantities)])

	# The stag's Medium Hide shares its picture with five other hides and furs and its
	# Sage with Rosemary. Before the server named the slots there was
	# no honest way to pick either, and the window refused. With the names it
	# is an ordinary summon.
	var stag: Button = rows.get_node("SummonRow%d" % listed[1]) as Button
	_expect(not stag.disabled,
		"the server's slot names make the stag summonable: %s"
			% str(window.call("blocking_reasons", listed[1])))
	slot_names.clear()
	window.call("sync")
	_expect(stag.disabled
		and str((stag.get_node("Row/Asks/Requirements") as Label).text)
			.contains("shares legacy artwork"),
		"and without them it refuses rather than guessing")
	_stock(inventory, slot_names, catalog, listed)
	window.call("sync")

	# Directing companions is a core feature, available from the first summon.
	var behavior: Button = window.get_node(
		"SummoningWindow/SummoningBody/SummoningHeader/SummoningBehavior") as Button
	_expect(not behavior.disabled,
		"the behaviour button is available below summoning 30")
	stats["summoning"] = 30
	window.call("sync")
	_expect(not behavior.disabled, "and on at 30")
	behavior.pressed.emit()
	_expect(behavior_requests == 1,
		"pressing it asks the server: %d" % behavior_requests)

	window.call("close")
	_expect(not panel.visible and not bool(window.call("is_open")),
		"close hides it")

	_check_summon_actor_packets()

	# Leave AppState as this suite found it.
	stats.clear()
	inventory.clear()
	slot_names.clear()

	print("summoning window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	window.queue_free()
	await process_frame
	quit(failures)

## The wire, decoded by the client's own decoder.
##
## A summon is a creature the server coloured EL blue1, and that colour byte
## is the only thing on an actor packet that says so - which is what the world
## click is gated on, because touching your own summon is how the behaviour
## popup opens. The guild tag is appended the way the enhanced player packet
## appends one, with its own colour marker: a creature name routinely contains
## a space, so the marker is the only separator the decoder can trust.
func _check_summon_actor_packets() -> void:
	var summon := _creature_packet(400, _display_name(4, "Mirrorfin Otter", 6, "ELO"))
	_expect(str(summon.get("type", "")) == "actor_spawn",
		"the summon packet decodes: " + str(summon))
	_expect(int(summon.get("name_colour", 0)) == 4,
		"a summon's name carries EL blue1: %d" % int(summon.get("name_colour", 0)))
	_expect(str(summon.get("name", "")) == "Mirrorfin Otter",
		"the creature's own name survives the tag: " + str(summon.get("name", "")))
	_expect(str(summon.get("guild_tag", "")) == "ELO",
		"and it wears the summoner's guild tag: " + str(summon.get("guild_tag", "")))
	_expect(int(summon.get("guild_colour", 0)) == 6,
		"with the colour the server chose for it")
	_expect(ReplicatedActor3D.is_summon(summon),
		"so the client knows a summon when it is clicked")

	# Wildlife is the same packet without the colour byte, and it must not
	# open a behaviour popup.
	var wildlife := _creature_packet(400, _display_name(0, "Mirrorfin Otter"))
	_expect(str(wildlife.get("name", "")) == "Mirrorfin Otter"
		and str(wildlife.get("guild_tag", "")).is_empty(),
		"a two-word creature name is never split into a guild tag: "
		+ str(wildlife.get("name", "")) + "/" + str(wildlife.get("guild_tag", "")))
	_expect(not ReplicatedActor3D.is_summon(wildlife),
		"and wildlife is not a summon")

	# An invasion creature is coloured too, in a different colour.
	var invasion := _creature_packet(400, _display_name(14, "Mirrorfin Otter"))
	_expect(not ReplicatedActor3D.is_summon(invasion),
		"nor is an invasion creature, which is red rather than blue")

## The bytes the server's `creature_display_name()` writes: an optional colour
## marker, the name, and - for a summon wearing one - a space, the tag's own
## marker and the tag. Assembled as bytes rather than as a String because both
## markers are above 127, which `to_ascii_buffer()` cannot carry.
func _display_name(name_colour: int, creature: String,
		guild_colour: int = 0, guild_tag: String = "") -> PackedByteArray:
	var bytes := PackedByteArray()
	if name_colour > 0:
		bytes.append(127 + name_colour)
	bytes.append_array(creature.to_ascii_buffer())
	if not guild_tag.is_empty():
		bytes.append(32)
		bytes.append(127 + guild_colour)
		bytes.append_array(guild_tag.to_ascii_buffer())
	return bytes

## The bytes the server's `actor_packet()` writes for a creature whose actor
## type is above the 8-bit ceiling: ADD_NEW_ACTOR_EXTENDED, name terminated.
func _creature_packet(actor_type: int, display_name: PackedByteArray) -> Dictionary:
	var payload := PackedByteArray()
	payload.resize(17)
	payload.encode_u16(0, 4242)          # actor id
	payload.encode_u16(2, 100)           # x
	payload.encode_u16(4, 120)           # y
	payload.encode_u16(6, 0)             # unused
	payload.encode_s16(8, 0)             # rotation
	payload.encode_u16(10, actor_type)
	payload.encode_u8(12, 0)             # frame
	payload.encode_u16(13, 22)           # max health
	payload.encode_u16(15, 22)           # health
	payload.append(5)                    # PKABLE_COMPUTER_CONTROLLED
	payload.append_array(display_name)
	payload.append(0)
	return EloriaProtocol.decode_actor(payload, false, true)

## Puts every ingredient the listed summons need into its own inventory slot,
## keyed by the image id the catalog actually carries. Returns image id to
## slot, so the assertions can name an ingredient without naming a number.
func _stock(inventory: Dictionary, names: Dictionary,
		catalog: ManufacturingCatalog, listed: Array[int]) -> Dictionary:
	var slot_of: Dictionary = {}
	for index: int in listed:
		for ingredient_value: Variant in catalog.recipe(index).get("ingredients", []) as Array:
			var ingredient: Dictionary = ingredient_value as Dictionary
			var item: String = str(ingredient.get("name", ""))
			if slot_of.has(item):
				continue
			var slot: int = slot_of.size()
			slot_of[item] = slot
			# Generous, so a shortfall is never what a test is measuring.
			inventory[slot] = {
				"image_id": int(ingredient.get("imageId", -1)), "quantity": 20}
			# The server names every slot it sends, which is what lets two
			# items sharing one picture be told apart.
			names[slot] = item
	return slot_of

func _json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed as Dictionary if parsed is Dictionary else {}

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
