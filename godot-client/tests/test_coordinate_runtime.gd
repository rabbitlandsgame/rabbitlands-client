extends SceneTree
const Context = preload("res://src/network/coordinate_context.gd")
const Profile = preload("res://src/network/coordinate_profile.gd")
const Wire = preload("res://src/network/protocol.gd")
var failures := 0
var assertions := 0
var catalog: Dictionary = {}
var aliases: Dictionary = {}

func expect(value: bool, label: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error(label)

func _init() -> void:
	call_deferred("run")

func context_packet(op: String, maps: Array = [], epoch := 1, active := "negative-map") -> PackedByteArray:
	var context := {"version": 1, "op": op}
	if op != "accepted":
		context["profiles"] = []
		for name: String in maps:
			context.profiles.append(catalog[name])
	if op == "activate":
		context["epoch"] = epoch
		context["mapId"] = active
		context["handles"] = []
		for index: int in range(maps.size()):
			context.handles.append({"handle": index, "mapId": maps[index]})
	return Wire.coordinate_context(context).frame

func activate(context: RefCounted, maps: Array = ["negative-map", "Étape 1"], epoch := 1) -> void:
	expect(context.receive(context_packet("activate", maps, epoch, maps[0]).slice(3)).ok, "prepare activation")
	expect(not context.ready(), "pending activation blocks intents")
	expect(context.commit("./maps/" + str(maps[0]) + ".elm").ok, "matching explicit name commits")

func prepared() -> RefCounted:
	var context := Context.new()
	expect(context.configure(catalog, aliases).ok, "catalog verified")
	expect(context.prepare_selection().ok, "explicit seam arms selection")
	expect(context.receive(context_packet("accepted").slice(3)).ok, "acceptance")
	return context

func actor_payload(handle: int) -> PackedByteArray:
	return PackedByteArray([1, 0, 3, 0, 2, 0, handle, 0, 0, 0, 6, 0, 50, 0, 50, 0, 1, 65, 0])

func run() -> void:
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/coordinate-profile-v1.json"))
	for row: Dictionary in fixture.profiles:
		var descriptor: Dictionary = Profile.from_registry(row.descriptor).profile.descriptor()
		catalog[descriptor.mapId] = descriptor
		aliases["./maps/" + str(descriptor.mapId) + ".elm"] = descriptor.mapId
	var ctx := prepared()
	expect(not ctx.convert({"type": "map_objects", "first": true, "objects": []}).ok, "empty active-map list still requires activation")
	expect(not ctx.convert({"type": "teleporters", "tiles": []}).ok, "empty teleporter snapshot still requires activation")
	expect(not Context.new().receive(context_packet("accepted").slice(3)).ok, "unsolicited acceptance rejected")
	expect(not Context.new().configure(catalog, {"negative-map": "legacy.zero"}).ok, "ambiguous canonical alias rejected")
	expect(not Context.new().configure(catalog, {"unknown": "missing"}).ok, "unknown alias target rejected")
	activate(ctx)
	var before: Dictionary = ctx.token()
	var actor: Dictionary = ctx.convert({"type": "actor_spawn", "map_handle": 1, "x": 0, "y": 0, "actor_id": 1}).event
	expect(actor.x == 10 and actor.y == 20 and actor.map == "Étape 1", "adjacent actor uses its profile before scenery")
	expect(not ctx.convert({"type": "actor_spawn", "map_handle": 99, "x": 0, "y": 0}).ok, "unknown handle fails closed")
	for kind: String in ["ground_bag", "teleport", "fire", "play_sound", "ground_missile"]:
		var row := {"type": kind, "x": 3, "y": 2, "kind": 42, "gain": 0.5, "source_actor_id": 65535}
		var converted: Dictionary = ctx.convert(row)
		expect(converted.ok and converted.event.x == -1 and converted.event.y == -1, kind + " signed point")
		expect(row.x == 3 and converted.event.kind == 42 and converted.event.gain == 0.5, kind + " only point changes")
	for kind: String in ["ground_bags", "map_objects", "world_object"]:
		var key := "bags" if kind == "ground_bags" else "objects"
		var row := {"type": kind, "first": true, "replace": true}
		row[key] = [{"x": 0, "y": 0, "object_id": 65535, "rotation": 12}]
		var converted: Dictionary = ctx.convert(row)
		expect(converted.ok and converted.event[key][0].x == -4 and converted.event[key][0].rotation == 12 and converted.event.first, kind + " list semantics")
		row[key].append({"x": 6, "y": 0})
		expect(not ctx.convert(row).ok and row[key][0].x == 0, "list rejection atomic " + kind)
	var portals: Array[Vector2i] = [Vector2i(3, 2)]
	expect(ctx.convert({"type": "teleporters", "tiles": portals}).event.tiles[0] == Vector2i(-1, -1), "teleporter list")
	for kind: String in ["navigation", "map_marker"]:
		var result: Dictionary = ctx.convert({"type": kind, "active": true, "x": 1, "y": 2, "distance": 555, "map_id": "Étape 1", "marker_id": 55})
		expect(result.ok and result.event.x == 11 and result.event.y == 22 and result.event.distance == 555, "named remote " + kind)
	expect(ctx.convert({"type": "navigation", "active": false, "x": 0, "y": 0, "map_id": ""}).event.x == 0, "inactive waypoint untouched")
	expect(not ctx.convert({"type": "map_marker", "map_id": "Étape 1", "map_reference": "other/Étape 1.elm", "x": 0, "y": 0}).ok, "untrusted basename does not authenticate map")
	var members: Array = [{"online": true, "map_id": "Étape 1", "x": 0, "y": 0, "health": 2047, "ether": 50}, {"online": false, "map_id": "", "x": 0, "y": 0}]
	var party: Dictionary = ctx.convert({"type": "party", "members": members})
	expect(party.ok and party.event.members[0].x == 10 and party.event.members[0].health == 2047 and party.event.members[1].x == 0, "party per row profile and offline sentinel")
	expect(ctx.convert({"type": "magic_state", "data": {"kind": "burst", "x": -1, "y": -1}}).event.data.x == -1, "JSON logical position is not offset")
	expect(not ctx.convert({"type": "magic_state", "data": {"kind": "burst", "x": -1, "y": -1, "map": "Étape 1"}}).ok, "old-map pulse cannot become current-map pulse")
	expect(not ctx.convert({"type": "magic_state", "data": {"kind": "burst", "x": -1, "y": -1, "map": "negative-map", "coordinateRevision": "wrong"}}).ok, "wrong-revision pulse rejected")
	var pulse := {"kind": "burst", "x": -1, "y": -1, "map": "negative-map", "coordinateRevision": catalog["negative-map"].coordinateRevision}
	expect(ctx.convert({"type": "magic_state", "data": pulse}).event.data == pulse, "valid associated negative pulse unchanged")
	var tutorial := {"version": 1, "active": true, "stage": 1, "total": 1, "scene": 0, "count": 0, "required": 0,
		"key": "fixture", "title": "fixture", "hint": "fixture", "control": "fixture", "item": "", "map": "negative-map", "target_id": "", "target": [-1, -1],
		"flags": {"crafted": false, "prepared": false, "repaired": false, "lit": false}}
	var tutorial_bytes := JSON.stringify(tutorial).to_utf8_buffer()
	expect(Wire.decode_lantern(tutorial_bytes).type == "invalid", "legacy tutorial unsigned validation unchanged")
	var tutorial_event := Wire.decode_lantern(tutorial_bytes, true)
	expect(tutorial_event.type == "lantern_tutorial" and ctx.convert(tutorial_event).ok, "selected tutorial logical negative validated")
	expect(ctx.convert({"type": "magic_state", "data": {"kind": "recall", "entries": [{"map": "Étape 1", "x": 10, "y": 20, "key": "opaque"}]}}).ok, "recall stays logical")
	expect(not ctx.convert({"type": "magic_state", "data": {"kind": "recall", "entries": [{"map": "legacy.zero", "x": 1, "y": 2}]}}).ok, "remote requires prior verified definition")
	expect(ctx.receive(context_packet("define", ["legacy.zero"]).slice(3)).ok and ctx.token() == before, "resync define does not change epoch")
	activate(ctx, ["legacy.zero", "negative-map"], 2)
	expect(actor.x == 10 and actor.map == "Étape 1", "carried actor unchanged by handle reuse")
	expect(not ctx.matches(before), "old epoch stale")
	for value: int in [0, 1023, 1024, 2047]:
		expect(ctx.convert({"type": "ground_bag", "x": value, "y": value}).event.x == value, "zero min preserves unsigned " + str(value))
	activate(ctx, ["negative-map"], 3)
	activate(ctx, ["negative-map"], 4)
	expect(ctx.epoch == 4, "A B A and same-map teleport distinct epochs")
	expect(not ctx.receive(context_packet("activate", ["negative-map"], 4).slice(3)).ok, "duplicate epoch rejected")
	var pending := prepared()
	expect(pending.receive(context_packet("activate", ["negative-map"]).slice(3)).ok, "pending pair")
	expect(not pending.before_packet(Wire.ServerMessage.ADD_ACTOR_COMMAND, Wire.ServerMessage.CHANGE_MAP).ok, "native reducer cannot bypass boundary")
	expect(not pending.commit("negative-map.elm").ok, "guessed alias rejected")
	var legacy := Context.new()
	expect(legacy.configure(catalog, aliases).ok and not legacy.commit("negative-map").ok, "legacy cannot enter declared offset map")
	var network = load("res://tests/helpers/coordinate_capture_network.gd").new()
	network.coordinates = prepared()
	expect(network.move_to(Vector2i.ZERO) == ERR_UNCONFIGURED and network.magic_request({"op": "options"}) == ERR_UNCONFIGURED and network.sent.is_empty(), "no point or magic before committed activation")
	network.coordinates = ctx
	for command: int in [1, 6, 51]:
		var error: int = network.fire_missile_at_object(-1, -1) if command == 51 else network.move_to(Vector2i(-1, -1), command == 6)
		var frame: PackedByteArray = network.sent.back()
		var decoded := Wire.decode_map_command(frame.slice(3))
		expect(error == OK and frame[0] == 204 and decoded.command == command and decoded.epoch == 4 and decoded.body.decode_u16(0) == 3 and decoded.body.decode_u16(2) == 2, "framed outgoing " + str(command))
	expect(network.magic_request({"op": "cast", "x": -1, "y": -1}) == OK, "signed magic sends")
	var magic: Dictionary = JSON.parse_string(Wire.decode_map_command(network.sent.back().slice(3)).body.get_string_from_utf8())
	expect(magic.x == -1 and magic.y == -1, "magic remains logical on wire")
	var count: int = network.sent.size()
	expect(network.move_to(Vector2i(2, 0)) == ERR_INVALID_PARAMETER and network.sent.size() == count, "bounds reject before unsigned packing")
	network.begin_magic_selection({"op": "cast"}, "location")
	activate(ctx, ["negative-map"], 5)
	expect(network.move_to(Vector2i(-1, -1)) != OK and network.sent.size() == count, "stale pending selection cannot transmit")
	network.disconnect_from_server()
	expect(not ctx.selected and ctx.epoch == 0 and ctx.profiles.is_empty() and network.magic_pending.is_empty(), "disconnect clears session")
	expect(not ctx.matches(before) and ctx.expected.size() == 3, "reconnect invalidates captured intent while retaining verified local catalog")
	network.free()
	# Actual autoload reduction and burst drain: commit precedes map signal;
	# fatal unknown handle cannot allow a following packet to update state.
	var live: Node = root.get_node("Network")
	var state: Node = root.get_node("AppState")
	live.coordinates = prepared()
	var observed: Array = []
	var on_change := func(path: StringName):
		if path == &"map": observed.append(live.coordinates.ready() and live.coordinates.epoch == 1)
	state.state_changed.connect(on_change)
	var burst := context_packet("activate", ["negative-map"])
	burst.append_array(Wire.encode(Wire.ServerMessage.CHANGE_MAP, "./maps/negative-map.elm".to_utf8_buffer()))
	burst.append_array(Wire.encode(Wire.ServerMessage.GET_NEW_BAG, PackedByteArray([3, 0, 2, 0, 7])))
	live.set("_rx", burst)
	live.call("_drain_packets")
	expect(observed == [true] and state.ground_bags[7].x == -1, "live map signal observes committed context and signed bag")
	burst = context_packet("activate", ["negative-map"], 2)
	burst.append_array(Wire.encode(Wire.ServerMessage.CHANGE_MAP, "bad-name".to_utf8_buffer()))
	burst.append_array(Wire.encode(Wire.ServerMessage.LOG_IN_OK))
	live.set("_rx", burst)
	live.call("_drain_packets")
	expect(not state.authenticated and not live.coordinates.selected and (live.get("_rx") as PackedByteArray).is_empty(), "fatal pair stops drain before following login")
	state.state_changed.disconnect(on_change)
	# Named rows require a definition; rejected chunks never replace even
	# the first existing row, and no subsequent packet in a burst is applied.
	live.coordinates = prepared()
	activate(live.coordinates, ["negative-map", "Étape 1"])
	state.call("_on_packet", Wire.ServerMessage.ADD_NEW_ACTOR, actor_payload(1))
	expect(state.actors[1].x == 13 and state.actors[1].y == 22 and state.actors[1].map == "Étape 1", "raw adjacent actor decode uses neighbor frame")
	state.call("_on_packet", Wire.ServerMessage.MISSILE_AIM_A_AT_XYZ, PackedByteArray([1, 0, 3, 0, 2, 0]))
	expect(state.actors[1].aiming_at_tile == Vector2i(-1, -1), "real negative aim has presence")
	state.call("_on_packet", Wire.ServerMessage.MISSILE_FIRE_A_TO_XYZ, PackedByteArray([1, 0, 3, 0, 2, 0]))
	expect(not state.actors[1].has("aiming_at_tile"), "fired aim removes presence")
	state.call("_on_packet", Wire.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([1, 0, 22]))
	expect(state.actors[1].x == 14 and state.actors[1].map == "Étape 1", "actor deltas retain actor map")
	var carried: Dictionary = state.actors[1].duplicate(true)
	state.call("_on_packet", 208, context_packet("activate", ["negative-map"], 2).slice(3))
	state.call("_on_packet", Wire.ServerMessage.CHANGE_MAP, "./maps/negative-map.elm".to_utf8_buffer())
	expect(state.actors[1] == carried, "actual AppState carries actor unchanged across handle replacement")
	state.map_objects = {99: {"x": -1, "y": -1}}
	var bad_rows := PackedByteArray([1, 2, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 2, 0, 1, 6, 0, 0, 0, 0, 0])
	state.call("_on_packet", Wire.ServerMessage.ELORIA_MAP_OBJECTS, bad_rows)
	expect(state.map_objects == {99: {"x": -1, "y": -1}} and not live.coordinates.selected, "rejected first chunk never clears or partly applies existing objects")
	live.coordinates = prepared()
	activate(live.coordinates, ["negative-map"])
	burst = Wire.encode(Wire.ServerMessage.ADD_NEW_ACTOR, actor_payload(99))
	burst.append_array(Wire.encode(Wire.ServerMessage.LOG_IN_OK))
	live.set("_rx", burst)
	state.authenticated = false
	live.call("_drain_packets")
	expect(not state.authenticated and not live.coordinates.selected, "unknown handle fatal stops subsequent packet")
	var admin_context := prepared()
	activate(admin_context, ["negative-map"])
	var admin: Dictionary = admin_context.convert({"type": "invasion_assistant", "state": {"kind": "map", "map": {"id": "Étape 1", "width": 6, "height": 6}, "players": [{"x": 10, "y": 20}]}})
	expect(admin.ok and admin.event.state.map.serverTileMin == [10, 20] and admin.event.state.players[0].x == 10, "admin remote expected catalog verifies logical JSON without binary define")
	expect(not admin_context.convert({"type": "invasion_assistant", "state": {"kind": "map", "map": {"id": "negative-map", "width": 7}}}).ok, "admin conflicting dimensions rejected")
	expect(not admin_context.convert({"type": "invasion_assistant", "state": {"kind": "map", "map": {"id": "negative-map", "serverTileMin": [0, 0]}}}).ok, "admin conflicting minimum rejected")
	admin = admin_context.convert({"type": "invasion_assistant", "state": {"kind": "map", "map": {"id": "unknown"}, "players": [{"x": -1, "y": -1}]}})
	expect(admin.ok and not admin.event.state.coordinatesSupported and admin.event.state.players.is_empty(), "unknown admin map unsupported, no fabricated origin")
	admin = admin_context.convert({"type": "invasion_assistant", "state": {"kind": "map", "coordinatesSupported": false, "map": {"id": "negative-map"}, "players": [{"x": -1, "y": -1}]}})
	expect(admin.ok and not admin.event.state.coordinatesSupported and admin.event.state.players.is_empty(), "server unsupported flag cannot be upgraded by local catalog")
	admin = admin_context.convert({"type": "invasion_assistant", "state": {"kind": "map", "map": {"id": "negative-map", "coordinatesSupported": false}, "players": [{"x": -1, "y": -1}]}})
	expect(admin.ok and not admin.event.state.coordinatesSupported and admin.event.state.players.is_empty(), "nested map unsupported flag cannot be upgraded by local catalog")
	expect(not admin_context.admin_bounds({"id": "negative-map", "coordinatesSupported": 1}).ok, "map support flag must be boolean")
	expect(not admin_context.admin_bounds({"id": "negative-map", "coordinateRevision": "wrong"}).ok, "admin metadata revision must match expected descriptor")
	expect(admin_context.admin_bounds({"id": "negative-map", "coordinateRevision": catalog["negative-map"].coordinateRevision, "coordinatesSupported": true}).ok, "matching supported admin metadata accepted")
	live.coordinates = admin_context
	var admin_window = load("res://src/ui/invasion_assistant.gd").new()
	admin_window.coordinate_context = admin_context
	admin_window.selected_map_id = "negative-map"
	admin_window.map_state = {"map": {"id": "negative-map", "width": 6, "height": 9}}
	admin_window.apply_update({"kind": "map", "map": {"id": "Étape 1", "width": 6, "height": 6}})
	expect(admin_window.selected_map_id == "negative-map" and admin_window.map_state.map.id == "negative-map", "delayed old selection does not change admin map bounds")
	expect(admin_window.call("_valid_logical_tile", "negative-map", Vector2i(-1, -1)), "admin selected bounds accept negative tile")
	expect(not admin_window.call("_valid_logical_tile", "unknown", Vector2i.ZERO), "admin unknown bounds reject submissions")
	admin_window.index_state = {"maps": [{"id": "Étape 1", "width": 6, "height": 6, "coordinatesSupported": false}]}
	expect(not admin_window.call("_valid_logical_tile", "Étape 1", Vector2i(10, 20)), "server unsupported index map cannot borrow local catalog bounds")
	var unsupported_group := {"name": "fixture", "map_id": "negative-map", "coordinatesSupported": false, "locations": [{"x": -1, "y": -1}]}
	expect(admin_window.call("_spawn_location_for_group", unsupported_group) == null, "unsupported group rejects otherwise valid selected-map location")
	var group_menu := OptionButton.new()
	group_menu.add_item("fixture")
	group_menu.set_item_metadata(0, unsupported_group)
	var group_status := Label.new()
	admin_window.monster_group = group_menu
	admin_window.status = group_status
	admin_window.selected_monster = {"type": "fixture", "name": "fixture"}
	var group_commands: Array[String] = []
	admin_window.command_requested.connect(func(command: String) -> void: group_commands.append(command))
	admin_window.call("_add_monster_to_group")
	expect(group_commands.is_empty() and group_status.text.contains("unavailable"), "unsupported group emits no coordinate submission")
	group_menu.free()
	group_status.free()
	admin_window.free()
	var invalid_network = load("res://tests/helpers/coordinate_capture_network.gd").new()
	expect(not invalid_network.configure_coordinate_profiles({}, {}, {"offset": {"coordinateTransform": {"serverTileMin": [-1, 0]}}}).ok, "locally declared offset requires published profile")
	expect(invalid_network.login("fixture", "fixture") != OK and invalid_network.sent.is_empty(), "invalid registry blocks login before credentials sent")
	invalid_network.free()
	# The registry is JSON, so its numbers arrive as floats: an explicit [0, 0] is no offset,
	# and a real one still needs its published profile.
	var json_network = load("res://tests/helpers/coordinate_capture_network.gd").new()
	var json_maps: Dictionary = JSON.parse_string('{"origin": {"coordinateTransform": {"serverTileMin": [0, 0]}}}')
	expect(json_network.configure_coordinate_profiles({}, {}, json_maps).ok, "a registry's explicit JSON [0, 0] is no offset")
	json_maps = JSON.parse_string('{"offset": {"coordinateTransform": {"serverTileMin": [-1, 0]}}}')
	expect(not json_network.configure_coordinate_profiles({}, {}, json_maps).ok, "a registry's JSON offset still requires a published profile")
	json_network.free()
	# The shipped registry must configure, or every login is refused before credentials are sent.
	var shipped: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	var shipped_network = load("res://tests/helpers/coordinate_capture_network.gd").new()
	var shipped_result: Dictionary = shipped_network.configure_coordinate_profiles(
		shipped.get("coordinateProfiles", {}), shipped.get("coordinateMapNames", {}), shipped.get("maps", {}))
	expect(shipped_result.ok, "the shipped map registry configures (%s)" % str(shipped_result.get("error", "")))
	shipped_network.free()
	expect(not "map_storage_coords_v1" in Wire.CLIENT_CAPABILITIES, "runtime integration does not advertise incomplete transport")
	# Signed consumer seams have no dependency on imported scenery.
	var stream = load("res://src/world/exterior_region_stream.gd").new()
	expect(stream.tile_inside({"serverTileMin": [-4, -3], "serverCells": [6, 9]}, Vector2i(-1, -1)), "signed click bounds accept real negative tile")
	expect(not stream.tile_inside({"serverTileMin": [-4, -3], "serverCells": [6, 9]}, Vector2i(2, -1)), "signed click bounds reject upper edge")
	var route_context := prepared()
	activate(route_context, ["negative-map"])
	stream.coordinate_context = route_context
	stream.pending_walk = {"coordinate_token": route_context.token(), "next_map": "Étape 1"}
	activate(route_context, ["Étape 1"], 2)
	expect(stream.call("_walk_context_current", "Étape 1"), "expected next route leg captures committed epoch")
	activate(route_context, ["Étape 1"], 3)
	expect(not stream.call("_walk_context_current", "Étape 1"), "same-map teleport invalidates road continuation")
	stream.pending_walk = {"coordinate_token": route_context.token(), "next_map": "negative-map"}
	activate(route_context, ["negative-map"], 4)
	activate(route_context, ["Étape 1"], 5)
	expect(not stream.call("_walk_context_current", "Étape 1"), "rapid A B A invalidates road continuation")
	route_context.reset()
	expect(not stream.call("_walk_context_current", "Étape 1"), "reconnect cannot inherit capable route")
	stream.free()
	var console = load("res://src/ui/console_commands.gd").new()
	console.current_map = "negative-map"
	expect(console.run("#mark absent").lines[0] == "There is nowhere to mark yet.", "console absent state")
	console.current_tile = Vector2i(-1, -1)
	console.run("#mark signed")
	expect(console.marks.size() == 1 and console.marks[0].x == -1 and console.marks[0].y == -1, "local mark persists logical negative unchanged")
	var canvas = load("res://src/ui/invasion_map_canvas.gd").new()
	canvas.size = Vector2(400, 300)
	canvas.set_map_state({"map": {"id": "negative-map", "serverTileMin": [-4, -3], "width": 6, "height": 9}})
	var drawn: Vector2 = canvas.call("_point", Vector2(-1, -1))
	expect(canvas.call("_tile", drawn) == Vector2i(-1, -1), "admin canvas signed tile roundtrip")
	canvas.selected_tile = Vector2i(-1, -1)
	canvas.set_map_state({"map": {"id": "negative-map", "serverTileMin": [-4, -3], "width": 6, "height": 9}})
	expect(canvas.selected_tile == Vector2i(-1, -1), "admin selection presence independent of sign")
	canvas.set_map_state({"coordinatesSupported": false, "map": {"id": "unknown"}})
	expect(canvas.selected_tile == null and not canvas.coordinates_supported, "unsupported admin bounds disable selection")
	canvas.free()
	var audio = load("res://src/audio/audio_director.gd").new()
	var steps: Array[Vector2i] = []
	audio.surface_at_tile = func(tile: Vector2i) -> String:
		steps.append(tile)
		return "dirt"
	state.local_actor_id = 99
	state.actors = {99: {"x": -1, "y": -1}}
	audio.call("_on_local_actor_moved")
	expect(steps.is_empty() and audio.get("_has_local_tile"), "first sighting at negative tile stays silent with explicit presence")
	state.actors[99].x = 0
	audio.call("_on_local_actor_moved")
	expect(steps == [Vector2i(0, -1)], "step away from negative sentinel tile plays normally")
	audio.call("_on_local_actor_moved")
	expect(steps.size() == 1, "restated actor does not play another step")
	audio.call("_on_state_changed", &"map")
	audio.call("_on_local_actor_moved")
	expect(steps.size() == 1, "first sighting after map reset stays silent")
	state.connection_state = "disconnected"
	audio.call("_on_state_changed", &"connection")
	expect(not audio.get("_has_local_tile"), "disconnect clears previous tile presence")
	audio.free()
	expect(load("res://src/app/main.gd") != null and load("res://src/ui/magic_selection.gd") != null, "modified runtime consumers parse")
	print("coordinate runtime: %d assertions, %d failures" % [assertions, failures])
	quit(0 if failures == 0 else 1)
