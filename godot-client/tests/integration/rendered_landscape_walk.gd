extends SceneTree

## Walks authored landscape routes with a temporary character on a real server.
## Movement and map changes are authoritative; captures check runtime grounding.

const TIMEOUT := 90.0
const SCREEN := Vector2i(1440, 900)
const GROUND_TOLERANCE := 0.6
# A neighbour chunk still importing when a click route starts attaches moments
# later, as a player sees it; the clicked surface is waited for, never assumed.
const NEIGHBOUR_SURFACE_TIMEOUT := 20.0
# A walk the server ended short of its target (a wandering creature stood on
# the tile or on the last step) is requested again once the actor has stood
# still this long, as a player clicks again; every repeat is recorded and the
# exact target is still required within the same budget.
const REISSUE_AFTER_IDLE := 3.0
# A frame gap this long is recorded as a stall (with its tick time), and a
# liveness line is printed every 30 s, so a client that stops rendering while
# a route waits can be located in the log rather than inferred afterwards.
const STALL_GAP_MS := 2000
const LIVENESS_EVERY_MS := 30000
## A route's start teleport is asked up to this many times, each waited this
## long, when a wandering body on the start tile makes the arrival land beside it.
const START_ATTEMPTS := 3
const START_WAIT_SECONDS := 40.0
## Seconds to wait for a body standing where a neighbour click would land.
const OCCUPIED_TARGET_TIMEOUT := 20.0
const FIXTURE_MINIMAP_ZOOM := 180.0

var _failures := 0
var _artifacts := ""
var _main: Control
var _state: Node
var _network: Node
var _loader: WorldLoader
var _report: Dictionary = {"checks": [], "transitions": []}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/transition")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN
	_watchdog()
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_state = root.get_node("AppState")
	_network = root.get_node("Network")

	var host: String = OS.get_environment("ELORIA_INTEGRATION_HOST")
	if host.is_empty():
		host = "127.0.0.1"
	var port_text: String = OS.get_environment("ELORIA_INTEGRATION_PORT")
	var port: int = int(port_text) if port_text.is_valid_int() else 2000
	var user: String = "LandscapeQA"
	var password: String = "qa_" + str(randi())

	(_main.get_node("LoginPanel/Content/Host") as LineEdit).text = host
	(_main.get_node("LoginPanel/Content/Port") as SpinBox).value = port
	_main.call("_on_connect_pressed")
	_expect(await _wait(func() -> bool:
		return str(_state.get("connection_state")) == "connected", TIMEOUT),
		"connected to the local test server")
	_main.call("_on_new_character_pressed")
	(_main.get("create_name") as LineEdit).text = user
	(_main.get("create_password") as LineEdit).text = password
	(_main.get("create_confirm") as LineEdit).text = password
	_main.call("_on_create_pressed")
	_expect(await _wait(func() -> bool:
		return bool(_state.get("authenticated")), TIMEOUT),
		"temporary character logged in")
	_loader = _main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/WorldLoader") as WorldLoader
	_expect(await _wait(func() -> bool: return not str(_state.get("current_map")).is_empty(), TIMEOUT),
		"initial world arrived")
	# New characters now begin in a private tutorial. Leave through its normal
	# confirmation before the administrator requests an exterior test route.
	if str(_state.get("current_map")).begins_with("lantern_reach"):
		_network.call("send_chat", "#tutorial skip")
		_expect(await _wait(func() -> bool: return int(_state.get("popup").get("popup_id", -1)) == 4100, TIMEOUT),
			"tutorial skip confirmation arrived")
		_main.call("_on_popup_option_pressed", 1, 1)
		_expect(await _wait(func() -> bool: return str(_state.get("current_map")) == "four_gates", TIMEOUT),
			"temporary character left the tutorial")
	_network.call("send_chat", "#demigod")
	var specs: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("ELORIA_WALK_SPEC")))
	for route: Dictionary in specs:
		if not (route.get("requiresItems", {}) as Dictionary).is_empty():
			var items_ready: bool = await _ensure_fixture_items(route.requiresItems as Dictionary)
			_expect(items_ready, str(route.id) + " required inventory received from server")
			if not items_ready: continue
		var map_id: String = str(route.get("map", "amberwood"))
		var start: Array = route.start
		# Admin arrivals may move to a nearby unoccupied tile. Only fixtures
		# that explicitly allow it relax their start; route targets remain exact.
		# A wandering body on the start tile makes the arrival land beside it:
		# the same teleport is asked again once that body has moved on, and
		# every repeat is recorded.
		var arrived := false
		var start_attempts := 0
		while not arrived and start_attempts < START_ATTEMPTS:
			start_attempts += 1
			_network.call("send_chat", "#invasion_assistant teleport %s %d %d" % [map_id, int(start[0]), int(start[1])])
			arrived = await _wait(func() -> bool:
				return _near(map_id, start, int(route.get("startTolerance", 0))), START_WAIT_SECONDS)
		if start_attempts > 1:
			if not _report.has("start_retries"): _report["start_retries"] = []
			(_report["start_retries"] as Array).append({"route": str(route.id), "attempts": start_attempts, "arrived": arrived})
		_expect(arrived, str(route.id) + " start")
		if not arrived: continue
		await _settle(20)
		_main.get("invasion_assistant_window").hide()
		_main.call("_on_popup_dismiss_pressed")
		_configure_route_camera(_main.get("camera_rig"), route)
		var walked := 0
		for step: Dictionary in route.steps:
			var target: Array = step.tile
			var npc_result: Dictionary = {}
			var arrival_result: Dictionary = {}
			var arrival_observation: Dictionary = {}
			var arrival_observer := Callable()
			var arrival_error := _arrival_fixture_error(step, str(route.get("travelMode", "")) == "ferry")
			if not arrival_error.is_empty():
				_expect(false, str(route.id) + " / " + arrival_error)
				break
			if step.has("expectedArrival"):
				arrival_observer = func(command: int, payload: PackedByteArray) -> void:
					_observe_arrival(arrival_observation, EloriaProtocol.decode_server(command, payload),
						int(_state.get("local_actor_id")), str(step.destination))
				_network.connect("packet_received", arrival_observer)
			var walk_timeout: float = float(step.get("walkTimeout", route.get("walkTimeout", 45)))
			var began: int = Time.get_ticks_msec()
			await _issue_walk(step)
			var destination: String = str(step.get("destination", map_id))
			var reached: bool
			if step.has("destination"):
				var ready_to_enter := true
				if step.has("object"):
					ready_to_enter = await _wait(func() -> bool: return _near(map_id, target, 2), walk_timeout)
					if ready_to_enter:
						_network.call("use_map_object", int(step.object))
				reached = await _walk_until(route, step, func() -> bool: return _arrived_on(destination), TIMEOUT) if ready_to_enter else false
				if bool(step.get("clickNeighbor", false)) and reached:
					reached = await _wait(func() -> bool: return _at(destination, target), walk_timeout)
			else:
				reached = await _walk_until(route, step, func() -> bool: return _at(map_id, target), walk_timeout)
			if arrival_observer.is_valid():
				_network.disconnect("packet_received", arrival_observer)
				arrival_result = await _check_arrival(step, arrival_observation) if reached else {
					"ok": false, "error": "destination did not arrive", "packet": arrival_observation}
				reached = reached and bool(arrival_result.get("ok", false))
				_expect(reached, "%s / exact published ferry arrival before further movement" % route.id)
			if reached and step.has("useObject"):
				var chat_cursor: int = (_state.get("chat_lines") as Array).size()
				if bool(step.get("expectStorage", false)):
					_state.call("close_storage")
				_network.call("use_map_object", int(step.useObject))
				if bool(step.get("expectStorage", false)):
					reached = await _wait(func() -> bool:
						return bool((_state.get("storage") as Dictionary).get("open", false)), 10)
					_expect(reached, "%s / %s storage opened" % [route.id, step.get("label", str(walked))])
				if reached and step.has("expectText"):
					reached = await _wait(func() -> bool:
						return _chat_contains_after(chat_cursor, str(step.expectText)), 10)
					_expect(reached, "%s / %s interaction replied" % [route.id, step.get("label", str(walked))])
			if reached and step.has("useNpc"):
				npc_result = await _talk_to_npc(step)
				reached = bool(npc_result.get("ok", false))
				_expect(reached, "%s / %s live NPC dialogue opened, replied and closed" % [route.id, step.get("label", str(walked))])
			if reached and step.has("expectResource"):
				reached = await _wait(func() -> bool: return _resource_present(int(step.expectResource)), 8)
				_expect(reached, "%s / %s resource visible and within reach" % [route.id, step.get("label", str(walked))])
			if reached and step.has("expectCreature"):
				reached = await _wait(func() -> bool: return _creature_present(step.expectCreature), 8)
				_expect(reached, "%s / %s encounter creature visible nearby" % [route.id, step.get("label", str(walked))])
			if not _report.has("walk_steps"): _report["walk_steps"] = []
			(_report["walk_steps"] as Array).append({"route": route.id, "target": target,
				"map": str(_state.get("current_map")), "ok": reached,
				"used_object": int(step.get("useObject", -1)),
				"used_npc": str(step.get("useNpc", "")), "npc_dialogue": npc_result,
				"arrival": arrival_result,
				"storage_open": bool((_state.get("storage") as Dictionary).get("open", false)),
				"seconds": (Time.get_ticks_msec() - began) / 1000.0,
				"actor": (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {}).duplicate(true)})
			_expect(reached, "%s / %s (%d,%d)" % [route.id, step.get("label", str(walked)), int(target[0]), int(target[1])])
			if not reached:
				var current: Dictionary = (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {})
				_report["failure_actor"] = current
				await _capture("failed-" + str(route.id) + "-" + str(walked) + ".png")
				break
			walked += 1
			await _settle(10)
			if step.has("capture"):
				# Network arrival precedes the interpolated body. Measure its final
				# footing once presentation has arrived, without relaxing grounding.
				_expect(await _wait(_presentation_arrived, 3), "presentation arrived: " + str(step.capture))
				var grounding: Dictionary = _ground(str(step.capture))
				_expect(bool(grounding.get("ok", false)), "grounded: " + str(step.capture))
				await _capture(str(step.capture) + ".png")
			if bool(step.get("expectStorage", false)):
				_state.call("close_storage")
			map_id = destination
		_report["routes_completed"] = int(_report.get("routes_completed", 0)) + int(walked == route.steps.size())
		_write_report()
	_write_report()
	print("Landscape route walk: ", "PASS" if _failures == 0 else "FAIL")
	_main.call("_on_disconnect_pressed")
	_main.get("exterior_stream").clear()
	while not _main.get("exterior_stream").is_idle():
		await process_frame
	await _settle(6)
	_main.queue_free()
	await process_frame
	quit(_failures)

static func _arrival_fixture_error(step: Dictionary, ferry_route := false) -> String:
	if not step.has("expectedArrival"):
		return "ferry transition requires expectedArrival" if step.has("destination") and (ferry_route or str(step.get("transitionMode", "")) == "ferry") else ""
	var expected: Variant = step.expectedArrival
	if not expected is Dictionary or not step.has("destination"):
		return "expectedArrival requires a destination transition and dictionary"
	if str(expected.get("map", "")) != str(step.destination) or str(step.destination).is_empty():
		return "expectedArrival map must match the transition destination"
	for key: String in ["tile", "global"]:
		var pair: Variant = expected.get(key)
		if not pair is Array or pair.size() != 2:
			return "expectedArrival requires a two-coordinate " + key
		for value: Variant in pair:
			if not (value is float or value is int) or not is_finite(float(value)):
				return "expectedArrival coordinates must be finite numbers"
			if key == "tile" and (float(value) != floorf(float(value)) or float(value) < 0):
				return "expectedArrival tile must contain nonnegative integers"
	if str(expected.get("units", "")) != "metres" or str(expected.get("point", "")) != "tile-center":
		return "expectedArrival global coordinates require metres at tile-center"
	if bool(step.get("clickNeighbor", false)):
		return "expectedArrival must be checked before a neighbor walk continues"
	return ""

static func _observe_arrival(observation: Dictionary, event: Dictionary, local_id: int, destination: String) -> void:
	if str(event.get("type", "")) == "change_map":
		observation["current_map"] = str(event.get("map_name", ""))
		if not observation.has("maps"): observation["maps"] = []
		(observation.maps as Array).append(observation.current_map)
	elif str(event.get("type", "")) == "actor_spawn" and int(event.get("actor_id", -1)) == local_id:
		if str(observation.get("current_map", "")) == destination and not observation.has("first_actor"):
			# Freeze the first authoritative landing. A later spawn/correction or
			# walking to the expected tile must never repair a failed arrival proof.
			observation["first_actor"] = event.duplicate(true)

static func _arrival_identity(expected: Dictionary, observation: Dictionary, current_map: String,
		actor: Dictionary, manifest: WorldManifest) -> Dictionary:
	var result := {"ok": false, "expected": expected.duplicate(true), "packet": observation.duplicate(true),
		"map": current_map, "actor": actor.duplicate(true)}
	var first: Dictionary = observation.get("first_actor", {})
	var tile: Array = expected.tile
	for candidate: Dictionary in [first, actor]:
		if candidate.is_empty() or int(candidate.get("x", -1)) != int(tile[0]) or int(candidate.get("y", -1)) != int(tile[1]):
			result["error"] = "first arrival packet or current authoritative tile differs from published landing"
			return result
	if current_map != str(expected.map) or str(observation.get("current_map", "")) != current_map or manifest == null:
		result["error"] = "arrival map identity differs from published destination"
		return result
	if manifest.asset_id() != str(expected.map):
		result["error"] = "loaded territory package differs from published destination"
		return result
	var placement: Dictionary = manifest.data.get("continentGeography", {})
	var translation: Array = placement.get("translation", [])
	if translation.size() != 3:
		result["error"] = "destination manifest has no published continent placement"
		return result
	var local := manifest.coordinate_adapter().tile_center(int(tile[0]), int(tile[1]))
	var global_point := Vector2(local.x + float(translation[0]), local.z + float(translation[2]))
	result["local"] = [local.x, local.y, local.z]
	result["global"] = [global_point.x, global_point.y]
	if global_point.distance_to(Vector2(float(expected.global[0]), float(expected.global[1]))) > .001:
		result["error"] = "destination manifest transform disagrees with published global landing"
		return result
	result["ok"] = true
	return result

func _check_arrival(step: Dictionary, observation: Dictionary) -> Dictionary:
	var actor: Dictionary = (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {})
	var result := _arrival_identity(step.expectedArrival, observation, str(_state.get("current_map")), actor, _loader.manifest)
	if not bool(result.ok): return result
	if not _loader.world_root is ContinentChunkStream:
		result["ok"] = false
		result["error"] = "published continent ferry destination did not use chunk streaming"
		return result
	var chunks := _loader.world_root as ContinentChunkStream
	var position: Array = result.local
	var local := Vector3(float(position[0]), float(position[1]), float(position[2]))
	var covering: Array[String] = []
	for identity: String in chunks.cells:
		if ContinentChunkStream.bounds_distance(local, chunks.cells[identity].entry.bounds) <= .01:
			covering.append(identity)
	var cold := not _loader.loaded_by_adoption
	result["chunks"] = {"cold_load": cold, "has_focus": chunks.has_focus,
		"initial_focus": [chunks.initial_focus.x, chunks.initial_focus.y, chunks.initial_focus.z] if chunks.initial_focus.is_finite() else null,
		"focus": [chunks.focus.x, chunks.focus.y, chunks.focus.z],
		"covering": covering, "loaded": chunks.cells.keys(), "events": chunks.events.duplicate(true)}
	if not chunks.has_focus or covering.is_empty() or (cold and chunks.initial_focus.distance_to(local) > .001):
		result["ok"] = false
		result["error"] = "destination chunks were not primed at the authoritative ferry landing"
		return result
	# Observe the production physics result; do not prime chunks or move the
	# actor from the harness. A correct DTO alone cannot prove walkable ground.
	await physics_frame
	await physics_frame
	var space: PhysicsDirectSpaceState3D = _main.get("gameplay_world").direct_space_state
	var query := PhysicsRayQueryParameters3D.create(Vector3(local.x, 400, local.z),
		Vector3(local.x, -200, local.z), WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit := space.intersect_ray(query)
	var collider: Node = hit.get("collider") as Node
	result["active_surface"] = not hit.is_empty() and collider != null and chunks.is_ancestor_of(collider)
	if not bool(result.active_surface):
		result["ok"] = false
		result["error"] = "ferry arrival has no active destination chunk walking surface"
	return result

static func _npc_fixture_error(step: Dictionary) -> String:
	for key: String in ["useNpc", "expectDialogue", "expectDialogueText"]:
		if not step.get(key) is String or str(step[key]).strip_edges().is_empty():
			return "NPC dialogue fixture needs a nonempty " + key
	if step.has("useObject") or step.has("object") or step.has("destination"):
		return "NPC dialogue and object/portal actions must be separate steps"
	return ""

static func _npc_actor_identity(actors: Dictionary, local_id: int, expected: String) -> int:
	var found := -1
	for identity: Variant in actors:
		var actor: Dictionary = actors[identity]
		if int(identity) == local_id or int(actor.get("kind", -1)) != 2: continue
		if str(actor.get("name", "")) != expected: continue
		# Ambiguous names must fail rather than silently talking to another body.
		if found >= 0: return -1
		found = int(identity)
	return found

static func _observe_npc_reply(reply: Dictionary, event: Dictionary) -> void:
	match str(event.get("type", "")):
		"npc_info": reply["name"] = str(event.get("name", ""))
		"npc_text": reply["text"] = str(event.get("text", ""))
		"npc_options": reply["options"] = event.get("options", [])

static func _npc_reply_matches(reply: Dictionary, actor_id: int, step: Dictionary,
		dialogue: Dictionary, panel_visible: bool, rendered_name: String, rendered_text: String) -> bool:
	var expected_name := str(step.expectDialogue)
	var expected_text := str(step.expectDialogueText)
	if str(reply.get("name", "")) != expected_name or not str(reply.get("text", "")).contains(expected_text):
		return false
	var own_options := false
	for option: Dictionary in reply.get("options", []):
		if int(option.get("actor_id", -1)) == actor_id: own_options = true
	if not own_options: return false
	if not bool(dialogue.get("open", false)) or not panel_visible: return false
	if str(dialogue.get("name", "")) != expected_name or not str(dialogue.get("text", "")).contains(expected_text):
		return false
	# The UI may append the speaker's occupation and the ordinary quest number to
	# the exact server speaker.
	var visible_name_ok := (rendered_name == expected_name
		or rendered_name.begins_with(expected_name + "  [Quest ")
		or rendered_name.begins_with(expected_name + "  <"))
	return visible_name_ok and rendered_text.contains(expected_text)

func _npc_ready(expected: String) -> bool:
	var actors: Dictionary = _state.get("actors")
	var identity := _npc_actor_identity(actors, int(_state.get("local_actor_id")), expected)
	if identity < 0: return false
	var actor: Dictionary = actors[identity]
	var player: Dictionary = actors.get(int(_state.get("local_actor_id")), {})
	if player.is_empty(): return false
	var node: Node3D = (_main.get("actor_nodes") as Dictionary).get(identity) as Node3D
	return maxi(absi(int(actor.x)-int(player.x)), absi(int(actor.y)-int(player.y))) <= 4 and _has_visible_model(node)

func _close_npc_dialogue() -> bool:
	if not bool((_state.get("npc_dialogue") as Dictionary).get("open", false)): return true
	# This is the same cancel action a player uses; do not hide the panel or
	# overwrite server dialogue data to manufacture a successful close.
	var cancel := InputEventAction.new()
	cancel.action = "cancel"
	cancel.pressed = true
	_main.call("_unhandled_input", cancel)
	return await _wait(func() -> bool:
		return not bool((_state.get("npc_dialogue") as Dictionary).get("open", false)) and not (_main.get("dialogue_panel") as Control).visible, 2)

func _talk_to_npc(step: Dictionary) -> Dictionary:
	var result := {"ok": false, "requested_name": str(step.get("useNpc", ""))}
	var problem := _npc_fixture_error(step)
	if not problem.is_empty():
		result["error"] = problem
		return result
	if not await _wait(func() -> bool: return _npc_ready(str(step.useNpc)), 8):
		result["error"] = "exact live NPC is missing, ambiguous, invisible or outside dialogue reach"
		return result
	if not await _close_npc_dialogue():
		result["error"] = "prior dialogue did not close normally"
		return result
	var identity := _npc_actor_identity(_state.get("actors"), int(_state.get("local_actor_id")), str(step.useNpc))
	if identity < 0:
		result["error"] = "live NPC disappeared while closing prior dialogue"
		return result
	result["actor_id"] = identity
	result["actor"] = ((_state.get("actors") as Dictionary)[identity] as Dictionary).duplicate(true)
	result["map"] = str(_state.get("current_map"))
	var reply: Dictionary = {}
	var observer := func(command: int, payload: PackedByteArray) -> void:
		if command in [EloriaProtocol.ServerMessage.SEND_NPC_INFO, EloriaProtocol.ServerMessage.NPC_TEXT, EloriaProtocol.ServerMessage.NPC_OPTIONS_LIST]:
			_observe_npc_reply(reply, EloriaProtocol.decode_server(command, payload))
	_network.connect("packet_received", observer)
	var sent: int = int(_network.call("touch_actor", identity))
	result["send_error"] = sent
	var opened := false
	if sent == OK:
		opened = await _wait(func() -> bool:
			return _npc_reply_matches(reply, identity, step, _state.get("npc_dialogue"),
				(_main.get("dialogue_panel") as Control).visible,
				(_main.get("dialogue_name") as Label).text,
				(_main.get("dialogue_text") as RichTextLabel).get_parsed_text()), 10)
	_network.disconnect("packet_received", observer)
	result["fresh_reply"] = reply.duplicate(true)
	result["dialogue"] = (_state.get("npc_dialogue") as Dictionary).duplicate(true)
	result["opened_and_matched"] = opened
	# Keep a failed response visible for the ordinary failure capture.
	result["closed_normally"] = await _close_npc_dialogue() if opened else false
	result["ok"] = opened and bool(result.closed_normally)
	return result

func _has_visible_model(node: Node3D) -> bool:
	if not is_instance_valid(node) or not node.is_visible_in_tree(): return false
	var pending: Array[Node] = [node]
	while not pending.is_empty():
		var child: Node = pending.pop_back()
		if child is MeshInstance3D:
			var mesh := child as MeshInstance3D
			if mesh.mesh != null and mesh.is_visible_in_tree() and (mesh.layers & 1) != 0: return true
		for descendant: Node in child.get_children(): pending.append(descendant)
	return false

func _resource_present(identity: int) -> bool:
	var object: MapObject3D = (_main.get("map_object_nodes") as Dictionary).get(identity) as MapObject3D
	var dto: Dictionary = (_state.get("map_objects") as Dictionary).get(identity, {})
	var player: Dictionary = (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {})
	if dto.is_empty() or player.is_empty() or not is_instance_valid(object): return false
	var distance := Vector2(float(dto.x)-float(player.x),float(dto.y)-float(player.y)).length()
	return object.is_harvestable() and distance <= 5.0 and _has_visible_model(object) and not (_main.get("_ungrounded_map_objects") as Dictionary).has(identity)

func _creature_present(expected: Variant) -> bool:
	var player: Dictionary = (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {})
	if player.is_empty(): return false
	var actors: Dictionary = _state.get("actors")
	for identity: Variant in actors:
		if int(identity) == int(_state.get("local_actor_id")): continue
		var actor: Dictionary = actors[identity]
		var matches: bool = int(actor.get("actor_type",-1)) == int(expected) if expected is float or expected is int else str(actor.get("name","")).to_lower().replace(" ","_").contains(str(expected).to_lower().replace(" ","_"))
		if not matches: continue
		var distance := Vector2(float(actor.x)-float(player.x),float(actor.y)-float(player.y)).length()
		var node: Node3D = (_main.get("actor_nodes") as Dictionary).get(identity) as Node3D
		if distance <= 35.0 and _has_visible_model(node): return true
	return false

static func _configure_route_camera(rig: IsometricCameraController, route: Dictionary) -> void:
	rig.yaw_degrees = float(route.get("yaw", 0))
	rig.pitch_degrees = -60.0
	rig.distance = float(route.get("distance", 26))
	# These fields have no setters. Apply the authored pose before projecting
	# the first click, without waiting for a later actor-follow frame.
	rig.set_focus(rig.focus)

func _issue_walk(step: Dictionary) -> void:
	var target: Array = step.tile
	var map_click_error := map_click_fixture_error(step)
	if not map_click_error.is_empty():
		_expect(false, map_click_error)
		return
	var map_click := str(step.get("mapClick", ""))
	if not map_click.is_empty():
		await _issue_map_walk(step, map_click)
		return
	if not bool(step.get("clickNeighbor", false)):
		_network.call("move_to", Vector2i(int(target[0]), int(target[1])), false)
		return
	var stream: ExteriorRegionStream = _main.get("exterior_stream")
	var resident: Dictionary = stream.residents[str(step.destination)]
	var far_adapter := (resident.manifest as WorldManifest).coordinate_adapter()
	var point: Vector3 = resident.root.transform * far_adapter.server_to_godot(float(target[0]) + .1, float(target[1]) + .1)
	var space: PhysicsDirectSpaceState3D = _main.get("gameplay_world").direct_space_state
	var query := PhysicsRayQueryParameters3D.create(Vector3(point.x, 400, point.z), Vector3(point.x, -200, point.z), ExteriorRegionStream.PREVIEW_SURFACE_LAYER)
	var waited_from := Time.get_ticks_msec()
	var hit := space.intersect_ray(query)
	while hit.is_empty() and Time.get_ticks_msec() - waited_from < roundi(NEIGHBOUR_SURFACE_TIMEOUT * 1000.0):
		await process_frame
		hit = space.intersect_ray(query)
	if not _report.has("surface_waits"): _report["surface_waits"] = []
	(_report["surface_waits"] as Array).append({"destination": str(step.destination), "tile": target,
		"waited_ms": Time.get_ticks_msec() - waited_from, "found": not hit.is_empty()})
	_expect(not hit.is_empty(), "clicked neighbor has an actual rendered walking surface")
	if hit.is_empty(): return
	point = hit.position
	var camera: Camera3D = _main.get("gameplay_camera")
	var screen := camera.unproject_position(point)
	_expect(Rect2(Vector2.ZERO, Vector2(camera.get_viewport().size)).has_point(screen), "neighbor destination is visible in the gameplay camera")
	# A wandering body between the camera and the target takes the click (the
	# client's own picker would attack it). Wait for it to move on, as a player
	# would, and record the wait; the click itself stays the ordinary one.
	var occupied_from := Time.get_ticks_msec()
	var picked: int = int(_main.call("_pick_actor", screen))
	while picked >= 0 and Time.get_ticks_msec() - occupied_from < roundi(OCCUPIED_TARGET_TIMEOUT * 1000.0):
		await process_frame
		picked = int(_main.call("_pick_actor", screen))
	if picked >= 0 or Time.get_ticks_msec() - occupied_from > 0:
		if not _report.has("occupied_waits"): _report["occupied_waits"] = []
		(_report["occupied_waits"] as Array).append({"destination": str(step.destination), "tile": target,
			"waited_ms": Time.get_ticks_msec() - occupied_from, "still_occupied_by": picked})
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = screen
	_main.call("_handle_world_click", click, screen)

## A map fixture goes through the visible TextureRect and its connected
## gui_input handler, exactly as a player click does. Map cameras can see a
## resident neighbour without its preview surface or the gameplay camera being
## able to see the destination, so this path deliberately has neither wait.
func _issue_map_walk(step: Dictionary, source: String) -> void:
	var target_values: Array = step.tile
	var target := Vector2i(int(target_values[0]), int(target_values[1]))
	var destination := str(step.destination)
	var stream: ExteriorRegionStream = _main.get("exterior_stream")
	var resident_value: Variant = stream.residents.get(destination)
	if not resident_value is Dictionary:
		_expect(false, "%s map click destination %s is not resident" % [source, destination])
		return
	var resident: Dictionary = resident_value as Dictionary
	var resident_root: Node3D = resident.get("root") as Node3D
	var resident_manifest: WorldManifest = resident.get("manifest") as WorldManifest
	if not is_instance_valid(resident_root) or resident_manifest == null:
		_expect(false, "%s map click destination %s has no resident root/manifest" % [source, destination])
		return
	var point: Vector3 = resident_root.transform * resident_manifest.coordinate_adapter().tile_center(
		target.x, target.y)
	var map_control: TextureRect
	var map_render_viewport: SubViewport
	var camera: Camera3D
	var opened_for_click := false
	var saved_map_state: Dictionary = {}
	if source == "full_map":
		var full_map_panel: Control = _main.get("full_map") as Control
		opened_for_click = not full_map_panel.visible
		if opened_for_click:
			_main.call("_on_map_button_pressed")
		map_control = _main.get("map_image") as TextureRect
		map_render_viewport = _main.get("full_map_viewport") as SubViewport
		camera = _main.get("full_map_camera") as Camera3D
	else:
		var minimap_panel: Control = _main.get("minimap_frame") as Control
		opened_for_click = not minimap_panel.visible
		if opened_for_click:
			_main.call("_on_minimap_button_pressed")
		# User HUD preferences persist across runs. The fixture uses the ordinary
		# north-up/default-width minimap deterministically, then restores both
		# values before closing it so the test neither depends on nor changes them.
		saved_map_state = {
			"zoom": float(_main.get("_minimap_zoom")),
			"orientation": str(_main.get("_minimap_orientation"))}
		_main.set("_minimap_zoom", FIXTURE_MINIMAP_ZOOM)
		_main.set("_minimap_orientation", "north_up")
		_main.call("_apply_minimap_zoom")
		map_control = _main.get("minimap") as TextureRect
		map_render_viewport = _main.get("map_viewport") as SubViewport
		camera = _main.get("map_camera") as Camera3D
	# Let containers lay out a newly opened map and let actor-follow settle the
	# minimap camera before projecting into its SubViewport.
	await process_frame
	await process_frame
	if (not is_instance_valid(map_control) or not map_control.is_visible_in_tree()
			or not is_instance_valid(map_render_viewport) or not is_instance_valid(camera)):
		_expect(false, "%s map click controls are invalid or hidden" % source)
		_restore_map_click_ui(source, opened_for_click, saved_map_state)
		return
	var viewport_position := camera.unproject_position(point)
	if camera.is_position_behind(point) or not Rect2(Vector2.ZERO,
			Vector2(map_render_viewport.size)).has_point(viewport_position):
		_expect(false, "%s map click target %s projects outside %s" % [
			source, point, map_render_viewport.size])
		_restore_map_click_ui(source, opened_for_click, saved_map_state)
		return
	var local_value: Variant = viewport_to_texture_position(
		viewport_position, map_control, map_render_viewport.size)
	if not local_value is Vector2:
		_expect(false, "%s map click target cannot be placed in the displayed texture" % source)
		_restore_map_click_ui(source, opened_for_click, saved_map_state)
		return
	var local_position: Vector2 = local_value as Vector2
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = local_position
	map_control.gui_input.emit(click)
	var pending: Dictionary = stream.pending_walk.duplicate(true)
	var intended_tile: Variant = pending.get("tile")
	_expect(str(pending.get("map", "")) == destination,
		"%s map click retained intended destination %s" % [source, destination])
	_expect(intended_tile is Vector2i and intended_tile == target,
		"%s map click retained exact intended tile %s" % [source, target])
	if not _report.has("map_clicks"):
		_report["map_clicks"] = []
	(_report["map_clicks"] as Array).append({
		"source": source, "destination": destination, "tile": target_values.duplicate(),
		"projected": [viewport_position.x, viewport_position.y],
		"texture_local": [local_position.x, local_position.y],
		"pending_destination": str(pending.get("map", "")),
		"pending_tile": ([intended_tile.x, intended_tile.y] if intended_tile is Vector2i else null)})
	_restore_map_click_ui(source, opened_for_click, saved_map_state)

func _restore_map_click_ui(source: String, opened_for_click: bool,
		saved_map_state: Dictionary = {}) -> void:
	if source == "minimap" and not saved_map_state.is_empty():
		_main.set("_minimap_zoom", float(saved_map_state.zoom))
		_main.set("_minimap_orientation", str(saved_map_state.orientation))
		_main.call("_apply_minimap_zoom")
	if not opened_for_click:
		return
	if source == "full_map":
		_main.call("_on_map_button_pressed")
	else:
		_main.call("_on_minimap_button_pressed")

## The inverse of Main._texture_to_viewport_position. It mirrors the map
## handler's keep-aspect letterbox calculation so the emitted event lands on
## the same rendered pixel for any control and SubViewport aspect ratio.
static func viewport_to_texture_position(viewport_position: Vector2,
		texture_rect: TextureRect, target_size: Vector2i) -> Variant:
	var control_size := texture_rect.size
	var target := Vector2(target_size)
	if (control_size.x <= 0.0 or control_size.y <= 0.0
			or target.x <= 0.0 or target.y <= 0.0
			or not Rect2(Vector2.ZERO, target).has_point(viewport_position)):
		return null
	if texture_rect.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT_CENTERED:
		var scale := minf(control_size.x / target.x, control_size.y / target.y)
		var displayed_size := target * scale
		var displayed_origin := (control_size - displayed_size) * 0.5
		return displayed_origin + viewport_position * displayed_size / target
	return viewport_position * control_size / target

## Unknown mapClick values are fixture errors. They must never silently fall
## through to the terrain or direct-network movement paths.
static func map_click_fixture_error(step: Dictionary) -> String:
	if not step.has("mapClick"):
		return ""
	var source := str(step.get("mapClick", ""))
	if source not in ["full_map", "minimap"]:
		return "mapClick must be full_map or minimap, got %s" % source
	if not bool(step.get("clickNeighbor", false)):
		return "%s mapClick requires clickNeighbor=true" % source
	if str(step.get("destination", "")).is_empty():
		return "%s mapClick requires a destination" % source
	return ""

func _watchdog() -> void:
	var last: int = Time.get_ticks_msec()
	var spoke: int = last
	while true:
		await process_frame
		var now: int = Time.get_ticks_msec()
		if now - last >= STALL_GAP_MS:
			if not _report.has("stalls"): _report["stalls"] = []
			(_report["stalls"] as Array).append({"at_ms": last, "gap_ms": now - last})
			print("harness_stall ", JSON.stringify({"at_ms": last, "gap_ms": now - last}))
		if now - spoke >= LIVENESS_EVERY_MS:
			print("harness_alive ", JSON.stringify({"at_ms": now, "routes_completed": int(_report.get("routes_completed", 0))}))
			spoke = now
		last = now

func _write_report() -> void:
	_report["failures"] = _failures
	var file := FileAccess.open(_artifacts.path_join("walk-report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_report, "  "))

func _near(map_id: String, tile: Array, tolerance: int) -> bool:
	if str(_state.get("current_map")) != map_id or _loader.world_root == null: return false
	var actor: Dictionary = (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {})
	return not actor.is_empty() and abs(int(actor.get("x", -999))-int(tile[0])) <= tolerance and abs(int(actor.get("y", -999))-int(tile[1])) <= tolerance

func _at(map_id: String, tile: Array) -> bool:
	return _near(map_id, tile, 0)

func _arrived_on(name: String) -> bool:
	return (str(_state.get("current_map")) == name
		and _loader.world_root != null
		and (_main.get("actor_nodes") as Dictionary).has(int(_state.get("local_actor_id"))))

func _on_map(name: String) -> bool:
	return await _wait(func() -> bool: return _arrived_on(name), TIMEOUT)

## Waits for `arrived`, requesting the step's walk again whenever the local
## actor has not changed tile for REISSUE_AFTER_IDLE seconds. Steps that use
## an object to change map keep their single request.
func _walk_until(route: Dictionary, step: Dictionary, arrived: Callable, seconds: float) -> bool:
	var deadline: int = Time.get_ticks_msec() + roundi(seconds * 1000.0)
	var last_tile := Vector2i(-1, -1)
	var idle_since: int = Time.get_ticks_msec()
	var reissued := 0
	while Time.get_ticks_msec() < deadline:
		if bool(arrived.call()):
			break
		var actor: Dictionary = (_state.get("actors") as Dictionary).get(int(_state.get("local_actor_id")), {})
		var tile := Vector2i(int(actor.get("x", -1)), int(actor.get("y", -1)))
		if tile != last_tile:
			last_tile = tile
			idle_since = Time.get_ticks_msec()
		elif not step.has("object") and Time.get_ticks_msec() - idle_since >= roundi(REISSUE_AFTER_IDLE * 1000.0):
			await _issue_walk(step)
			reissued += 1
			idle_since = Time.get_ticks_msec()
		await process_frame
	if reissued > 0:
		if not _report.has("reissued_walks"): _report["reissued_walks"] = []
		(_report["reissued_walks"] as Array).append({"route": str(route.id), "target": step.tile,
			"reissued": reissued, "arrived": bool(arrived.call())})
	return bool(arrived.call())

func _chat_contains_after(cursor: int, expected: String) -> bool:
	var lines: Array = _state.get("chat_lines")
	for index in range(cursor, lines.size()):
		if str((lines[index] as Dictionary).get("text", "")).contains(expected):
			return true
	return false

func _fixture_item_quantity(item_name: String) -> int:
	var total := 0
	for item: Dictionary in (_state.get("inventory_state") as Dictionary).get("items", []):
		if str(item.get("name", "")) == item_name:
			total += int(item.get("quantity", 0))
	return total

func _ensure_fixture_items(required: Dictionary) -> bool:
	# This temporary QA character uses the existing server testing command.
	# The entrance still performs its ordinary authoritative key check.
	for item_name: String in required:
		var quantity: int = int(required[item_name])
		var missing: int = maxi(0, quantity - _fixture_item_quantity(item_name))
		if missing == 0: continue
		var cursor: int = (_state.get("chat_lines") as Array).size()
		_network.call("send_chat", "#give %s %d" % [item_name, missing])
		if not await _wait(func() -> bool:
			return _chat_contains_after(cursor, "Gave %d %s (item ID " % [missing, item_name]), 10):
			return false
		# The organizer packet carries canonical item names and quantities;
		# chat alone does not prove the received authoritative inventory.
		_network.call("send_chat", "#inventory")
		if not await _wait(func() -> bool: return _fixture_item_quantity(item_name) >= quantity, 10):
			return false
	return true

func _presentation_arrived() -> bool:
	var actor: ReplicatedActor3D = (_main.get("actor_nodes") as Dictionary).get(int(_state.get("local_actor_id"))) as ReplicatedActor3D
	return is_instance_valid(actor) and actor.global_position.distance_to(actor.server_target) < 0.01

func _ground(label: String) -> Dictionary:
	var nodes: Dictionary = _main.get("actor_nodes") as Dictionary
	var actor: Node3D = nodes.get(int(_state.get("local_actor_id"))) as Node3D
	var result: Dictionary = {"label": label, "map": str(_state.get("current_map"))}
	if actor == null:
		result["ok"] = false
		(_report["transitions"] as Array).append(result)
		return result
	var space: PhysicsDirectSpaceState3D = _main.get("gameplay_world").direct_space_state
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(actor.global_position.x, 400.0, actor.global_position.z),
		Vector3(actor.global_position.x, -200.0, actor.global_position.z),
		WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit: Dictionary = space.intersect_ray(query)
	result["actor_y"] = actor.global_position.y
	if hit.is_empty():
		result["ok"] = false
		result["error"] = "no navigation surface"
	else:
		result["surface_y"] = (hit["position"] as Vector3).y
		result["delta"] = actor.global_position.y - float(result["surface_y"])
		result["ok"] = absf(result["delta"]) <= GROUND_TOLERANCE
	(_report["transitions"] as Array).append(result)
	return result

func _wait(predicate: Callable, seconds: float) -> bool:
	var deadline: int = Time.get_ticks_msec() + roundi(seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if bool(predicate.call()):
			return true
		await process_frame
	return bool(predicate.call())

func _settle(frames: int) -> void:
	for _i: int in range(frames):
		await physics_frame
		await process_frame

func _capture(name: String) -> void:
	await _settle(4)
	_main.get("invasion_assistant_window").hide()
	await process_frame
	RenderingServer.force_draw(false)
	_expect(root.get_texture().get_image().save_png(_artifacts.path_join(name)) == OK,
		"saved " + name)

func _expect(condition: bool, message: String) -> void:
	(_report["checks"] as Array).append({"ok": condition, "check": message})
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)
