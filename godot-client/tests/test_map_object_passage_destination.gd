extends SceneTree
## MapObject3D.destination() for the ways on inside an interior map, headless,
## with a synthetic objects.json catalog:
##
##   godot --headless --path godot-client --script res://tests/test_map_object_passage_destination.gd
##
## The Landfall Town stair ends (59221/59222) hover as their own label: their
## server text is that label ("Upstairs: the guest rooms."), not the caves'
## "A way leads on into <section>." phrase. A cave passage end, a cave mouth
## and a waygate hover exactly as before.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func _object(id: int, tile: Vector2i, detail: String, catalog: Dictionary) -> MapObject3D:
	var node := MapObject3D.new()
	node.configure({"object_id": id, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": tile.x, "y": tile.y,
		"label": "Portal", "detail": detail}, CoordinateAdapter.new({}), catalog)
	root.add_child(node)
	return node

func _run() -> void:
	var catalog := {"authoredObjects": {
		"59221": {"passage": true, "height": 3.6, "radius": 1.6, "label": "Upstairs: the guest rooms"},
		"59222": {"passage": true, "height": 3.6, "radius": 1.6, "label": "Downstairs: the taproom"},
		"59223": {"passage": true, "height": 3.6, "radius": 1.6},
		"9300": {"passage": true, "height": 3.6, "radius": 1.6, "label": "Beta Pocket"},
		"59001": {"entrance": true, "exteriorTile": [30, 30], "label": "Lantern Mine", "height": 3.6,
			"radius": 1.6}}}
	var made: Array[MapObject3D] = []
	var up := _object(59221, Vector2i(35, 28), "Upstairs: the guest rooms.", catalog)
	var down := _object(59222, Vector2i(85, 29), "Downstairs: the taproom.", catalog)
	made.append_array([up, down])
	_expect(up.destination() == "Upstairs: the guest rooms", "the stair up hovers as its own label")
	_expect(down.destination() == "Downstairs: the taproom", "the stair down hovers as its own label")
	_expect(up.offers_map_change() and up.map_glyph() == MapObject3D.PORTAL_GLYPH,
		"a stair end is a portal the maps draw as their P")
	_expect(up.get_node_or_null("Ring") == null and up.get_node_or_null("EntranceLabel") == null,
		"a stair end stands no ring and no world label")
	var bare := _object(59223, Vector2i(5, 5), "To the loft. Mind the step.", catalog)
	made.append(bare)
	_expect(bare.destination() == "To the loft",
		"a stair end without a record label hovers as its text's first sentence")
	var silent := _object(59221, Vector2i(35, 28), "", catalog)
	made.append(silent)
	_expect(silent.destination() == "", "a stair end the server stated no text for names nothing")
	var cave := _object(9300, Vector2i(7, 7), "A way leads on into Beta Pocket. Damp.", catalog)
	made.append(cave)
	_expect(cave.destination() == "Beta Pocket", "a cave passage end still hovers as the section it leads into")
	var cave_silent := _object(9300, Vector2i(7, 7), "", catalog)
	made.append(cave_silent)
	_expect(cave_silent.destination() == "", "a cave passage end without its text still names nothing")
	var mouth := _object(59001, Vector2i(30, 30), "Beyond it lies Lantern Mine. Safe.", catalog)
	made.append(mouth)
	_expect(mouth.destination() == "Lantern Mine", "a cave mouth still hovers as where it leads")
	var gate := _object(17, Vector2i(3, 3), "A waygate hums. Beyond it lies Boarsend.", catalog)
	made.append(gate)
	_expect(gate.destination() == "Boarsend", "a waygate still hovers as where it leads")
	var stranger := _object(18, Vector2i(4, 4), "A portal of some other kind.", catalog)
	made.append(stranger)
	_expect(stranger.destination() == "", "a portal with no record and no phrase still names nothing")
	for node: MapObject3D in made:
		node.queue_free()
	for frame: int in 3:
		await process_frame
	print("map object passage destination: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)
