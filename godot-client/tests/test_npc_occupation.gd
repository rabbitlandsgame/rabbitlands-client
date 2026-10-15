extends SceneTree
## An NPC's occupation, drawn the way other MMORPGs draw "<Innkeeper>": a second,
## smaller, muted line under the name.
##
## The owner's rule (2026-10-14) is to keep NPC names simple and put what a
## person does on a line of its own. The server sends it on its own packet,
## ELORIA_ACTOR_OCCUPATIONS (210), to a client that declares
## actor_occupations_v1, after the actor packets it describes. The payloads
## below are the exact output of eloria/protocol.py's `actor_occupations`.
##
## main.gd is loaded at run time, not preloaded: it reads the autoload
## singletons, which a SceneTree script is compiled before.

var MainScript: GDScript
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	MainScript = load("res://src/app/main.gd") as GDScript
	if not _expect(MainScript != null and MainScript.can_instantiate(), "main.gd compiles"):
		quit(failures)
		return
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("actor_occupations_v1"),
		"the client declares that it draws occupations")
	await _test_actor()
	_test_declutter_and_header()
	await _test_main()
	print("npc occupation tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _test_actor() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	# No body: the overhead block is the thing under test, and a stand-in model
	# carries one exactly as a native body does.
	actor.configure({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"kind": 2, "name": "Ammet Sorrel", "name_colour": 0, "scale": 1.0,
		"health": 20, "max_health": 20}, adapter, {}, {})
	actor.set_physics_process(false)
	await process_frame
	var plate := actor.get_node("Nameplate") as Label3D
	_expect(actor.get_node_or_null("OccupationLine") == null and actor.occupation() == "",
		"an actor with no occupation carries no label for one")
	var bare_drop: float = actor.health_drop()

	actor.set_occupation("Grove-Keeper")
	var line := actor.get_node_or_null("OccupationLine") as Label3D
	if not _expect(line != null, "an occupation builds its line"):
		return
	_expect(line.text == "<Grove-Keeper>" and line.visible and actor.occupation() == "Grove-Keeper",
		"the line reads <Grove-Keeper> and shows")
	_expect(plate.text == "Ammet Sorrel", "the name itself stays simple")
	_expect(line.position.y == plate.position.y and line.offset.y < 0.0,
		"it hangs under the name rather than over it")
	_expect(line.font_size < plate.font_size, "smaller than the name")
	_expect(line.modulate.r < 0.9 and line.modulate.g < 0.9 and line.modulate.b < 0.9
		and line.modulate.r > 0.5, "in a muted colour, not the name's white")
	_expect(line.fixed_size and is_equal_approx(line.pixel_size, plate.pixel_size),
		"in the same screen pixels as the rest of the block")
	_expect(line.layers == plate.layers, "on the gameplay camera's layer, like the name")

	# A health bar, where one is worn, moves down a line to make room.
	actor.set_health_visible(true)
	await process_frame
	var bar := actor.get_node("HealthBarBackground") as MeshInstance3D
	var numbers := actor.get_node("HealthNumbers") as Label3D
	var line_bottom: float = (-line.offset.y / WORLD_LABEL_RASTER()
		+ ReplicatedActor3D.OCCUPATION_FONT_SIZE * 0.5)
	var bar_top: float = (-(bar.mesh as QuadMesh).center_offset.y / ReplicatedActor3D.OVERHEAD_PIXEL
		- (ReplicatedActor3D.HEALTH_BAR_THICKNESS + ReplicatedActor3D.HEALTH_BAR_BORDER) * 0.5)
	_expect(is_equal_approx(actor.health_drop(), bare_drop + ReplicatedActor3D.OCCUPATION_DROP),
		"the health row drops a line under an occupation")
	_expect(bar_top >= line_bottom - 0.01,
		"and the bar starts below the occupation's letters (%.1f >= %.1f)" % [bar_top, line_bottom])
	_expect(is_equal_approx(-numbers.offset.y / WORLD_LABEL_RASTER(), actor.health_drop()),
		"its numbers move with it")
	var backing := actor.get_node("OverheadBackground") as MeshInstance3D
	var quad := backing.mesh as QuadMesh
	var backing_bottom: float = (-quad.center_offset.y / ReplicatedActor3D.OVERHEAD_PIXEL
		+ quad.size.y / ReplicatedActor3D.OVERHEAD_PIXEL * 0.5)
	_expect(backing_bottom >= actor.health_drop(), "the backing still holds the whole block")
	actor.set_health_visible(false)
	await process_frame
	backing_bottom = (-quad.center_offset.y / ReplicatedActor3D.OVERHEAD_PIXEL
		+ quad.size.y / ReplicatedActor3D.OVERHEAD_PIXEL * 0.5)
	_expect(backing_bottom >= line_bottom, "with no bar the backing still holds the occupation")

	# Fading, hiding and decluttering take the line with the name.
	actor.set_overhead_fade(0.5)
	_expect(line.visible and is_equal_approx(line.modulate.a, 0.5)
		and is_equal_approx(plate.modulate.a, 0.5), "it fades with the name")
	_expect(Color(line.modulate, 1.0).is_equal_approx(
		Color(ReplicatedActor3D.OCCUPATION_COLOUR, 1.0)), "without losing its colour")
	actor.set_overhead_fade(0.0)
	_expect(not line.visible and not plate.visible, "past the name distance it goes with the name")
	actor.set_overhead_fade(1.0)
	actor.set_nameplate_visible(false)
	_expect(not line.visible, "names switched off take it off too")
	actor.set_nameplate_visible(true)
	actor.set_overhead_crowded(true)
	_expect(not line.visible, "a decluttered name takes its occupation with it")
	actor.set_overhead_crowded(false)
	actor.set_drawn(false)
	_expect(not line.visible, "out of the draw distance nothing floats")
	actor.set_drawn(true)
	_expect(line.visible, "and back in range it returns with the name")

	actor.set_server_scale(2.0)
	_expect(is_equal_approx(line.position.y, plate.position.y),
		"a bigger body lifts the line with the name")

	actor.set_occupation("")
	_expect(not line.visible and actor.occupation() == "" and
		is_equal_approx(actor.health_drop(), bare_drop),
		"an empty occupation takes the line off and the bar back up")
	actor.queue_free()
	await process_frame

func _test_declutter_and_header() -> void:
	var plain: Rect2 = MainScript.overhead_block_rect(Vector2(400, 300), "Ammet Sorrel")
	var occupied: Rect2 = MainScript.overhead_block_rect(Vector2(400, 300), "Ammet Sorrel",
		"Grove-Keeper of the Old Palace")
	_expect(is_equal_approx(occupied.size.y, plain.size.y + ReplicatedActor3D.OCCUPATION_DROP)
		and is_equal_approx(occupied.position.y, plain.position.y),
		"decluttering reserves the occupation's line under the name")
	_expect(occupied.size.x > plain.size.x,
		"and an occupation wider than the name claims its own width")

	var actors := {30001: {"name": "Ammet Sorrel"}, 30002: {"name": "Tavi Unhar"},
		30003: {"name": "Somebody With A Long Name"}}
	var occupations := {30001: "Grove-Keeper", 30003: "Archivist"}
	_expect(MainScript.dialogue_occupation({"name": "Ammet Sorrel",
			"options": [{"actor_id": 30001, "response_id": 1}]}, actors, occupations)
		== "Grove-Keeper", "the dialogue header finds its person by the options' actor")
	_expect(MainScript.dialogue_occupation({"name": "Ammet Sorrel", "options": []},
			actors, occupations) == "Grove-Keeper", "or by name before any option arrives")
	_expect(MainScript.dialogue_occupation({"name": "Somebody With A Lon", "options": []},
			actors, occupations) == "Archivist", "even when the info packet cut the name")
	_expect(MainScript.dialogue_occupation({"name": "Tavi Unhar",
			"options": [{"actor_id": 30002}]}, actors, occupations) == "",
		"and a person with no occupation has none")

func _test_main() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	await process_frame

	# Bob, an enhanced actor, then the occupations packet naming him: the order
	# the server sends them in.
	app_state.call("_on_packet", 51, _hex(
		"5c000203e1010000000001000001020304050b001e14071400"
		+ "12000190426f62000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var actors: Dictionary = main.get("actor_nodes") as Dictionary
	var bob: Node3D = actors.get(92) as Node3D
	if not _expect(bob != null, "the actor the occupation belongs to exists"):
		main.queue_free()
		return
	app_state.call("_on_packet", 210, _hex("01005c00" + "47726f76652d4b6565706572" + "00"))
	await process_frame
	var line := bob.get_node_or_null("OccupationLine") as Label3D
	_expect(line != null and line.text == "<Grove-Keeper>",
		"an occupation that lands after its actor is drawn under the name")
	_expect(str((app_state.get("actor_occupations") as Dictionary).get(92, "")) == "Grove-Keeper",
		"and kept for the actor")

	# The dialogue header names it too.
	app_state.set("npc_dialogue", {"open": true, "name": "Bob", "text": "Well met.",
		"options": [{"actor_id": 92, "response_id": 1, "label": "Farewell"}],
		"quest": false, "quest_id": 0})
	app_state.emit_signal("state_changed", &"npc_dialogue")
	await process_frame
	var header := main.get("dialogue_name") as Label
	_expect(header != null and header.text == "Bob  <Grove-Keeper>",
		"the dialogue header follows the name with the occupation: %s"
			% (header.text if header != null else "<none>"))
	app_state.set("npc_dialogue", {"open": false, "name": "", "text": "", "options": [],
		"quest": false, "quest_id": 0})
	app_state.emit_signal("state_changed", &"npc_dialogue")

	# An occupation goes with its actor: the server describes people afresh
	# every time it shows them, so a re-shown actor waits for its own row.
	app_state.call("_on_packet", 6, _hex("5c00"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	_expect(not (app_state.get("actor_occupations") as Dictionary).has(92),
		"removing an actor forgets its occupation")
	app_state.call("_on_packet", 51, _hex(
		"5c000203e1010000000001000001020304050b001e14071400"
		+ "12000190426f62000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	actors = main.get("actor_nodes") as Dictionary
	bob = actors.get(92) as Node3D
	if _expect(bob != null, "the actor comes back"):
		var again := bob.get_node_or_null("OccupationLine") as Label3D
		_expect(again == null or not again.visible,
			"without the occupation it was removed with")
	app_state.call("_on_packet", 210, _hex("01005c00" + "47726f76652d4b6565706572" + "00"))
	await process_frame
	app_state.call("_on_packet", 9, PackedByteArray())
	await process_frame
	_expect((app_state.get("actor_occupations") as Dictionary).is_empty(),
		"clearing every actor clears every occupation")
	main.queue_free()
	await process_frame

static func WORLD_LABEL_RASTER() -> float:
	return float(preload("res://src/ui/world_label_style.gd").RASTER_SCALE)

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error(label)
	return value
