extends SceneTree

# Manual cross-repository smoke test. Start the independent eloria-server
# profile locally, then run this script with ELORIA_INTEGRATION_HOST/PORT.
const NEW_CULTURE_ACTOR_TYPES: Array[int] = [79, 80, 81, 82]
const TIMEOUT_SECONDS := 12.0

var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var host: String = OS.get_environment("ELORIA_INTEGRATION_HOST")
	if host.is_empty():
		host = "127.0.0.1"
	var port_text: String = OS.get_environment("ELORIA_INTEGRATION_PORT")
	var port: int = int(port_text) if port_text.is_valid_int() else 2000
	_validate_client_registry()
	for index: int in range(NEW_CULTURE_ACTOR_TYPES.size()):
		await _verify_round_trip(host, port, NEW_CULTURE_ACTOR_TYPES[index], index)
	print("local server character models: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

func _validate_client_registry() -> void:
	var source := FileAccess.open("res://data/actors/models.json", FileAccess.READ)
	_expect(source != null, "client model registry opens")
	if source == null:
		return
	var parsed: Variant = JSON.parse_string(source.get_as_text())
	_expect(parsed is Dictionary, "client model registry parses")
	if parsed is not Dictionary:
		return
	var actor_types: Dictionary = (parsed as Dictionary).get("actorTypes", {})
	for actor_type: int in NEW_CULTURE_ACTOR_TYPES:
		_expect(actor_types.has(str(actor_type)),
			"client registry contains actor type %d" % actor_type)

func _verify_round_trip(host: String, port: int, actor_type: int, index: int) -> void:
	var suffix: String = str(Time.get_ticks_msec() % 100000)
	var username := "Model%d%s" % [actor_type, suffix]
	var password := "LocalPass%d" % actor_type
	var requested := {
		"skin": index + 1, "hair": index + 2, "shirt": index + 3,
		"pants": index + 4, "boots": index + 5, "actor_type": actor_type,
		"head": index + 6, "eyes": index + 7}
	var state := {"connected": false, "created": false, "logged_in": false,
		"actor": {}, "error": ""}
	var network := EloriaNetworkClient.new()
	network.name = "CharacterModelRoundTrip%d" % actor_type
	network.connection_state_changed.connect(func(value: String) -> void:
		state["connected"] = value == "connected")
	network.protocol_error.connect(func(message: String) -> void:
		state["error"] = message)
	var packet_handler: Callable = func(command: int, payload: PackedByteArray) -> void:
		var event: Dictionary = EloriaProtocol.decode_server(command, payload)
		match str(event.get("type", "")):
			"create_character_ok":
				state["created"] = true
			"create_character_error":
				state["error"] = str(event.get("message", "creation rejected"))
			"login_ok":
				state["logged_in"] = true
			"login_error":
				state["error"] = str(event.get("message", "login rejected"))
			"actor_spawn":
				if str(event.get("name", "")) == username:
					state["actor"] = event.duplicate(true)
			"ping_request":
				network.send_frame(EloriaProtocol.encode(
					EloriaProtocol.ClientMessage.PING_RESPONSE))
	network.packet_received.connect(packet_handler)
	root.add_child(network)
	_expect(network.connect_to_server(host, port) == OK,
		"actor type %d begins TCP connection" % actor_type)
	var connected: Callable = func() -> bool:
		return bool(state.get("connected", false)) or not str(state.get("error", "")).is_empty()
	_expect(await _wait_for(connected), "actor type %d connects" % actor_type)
	if not bool(state.get("connected", false)):
		_fail("actor type %d connection error: %s" % [actor_type, state.get("error", "")])
		network.queue_free()
		return
	_expect(network.create_character(username, password, requested) == OK,
		"actor type %d sends creation request" % actor_type)
	var created: Callable = func() -> bool:
		return bool(state.get("created", false)) or not str(state.get("error", "")).is_empty()
	_expect(await _wait_for(created), "actor type %d creation responds" % actor_type)
	if not bool(state.get("created", false)):
		_fail("actor type %d creation error: %s" % [actor_type, state.get("error", "")])
		network.disconnect_from_server()
		network.queue_free()
		return
	_expect(network.login(username, password) == OK,
		"actor type %d sends login request" % actor_type)
	var actor_received: Callable = func() -> bool:
		return ((bool(state.get("logged_in", false))
			and not (state.get("actor", {}) as Dictionary).is_empty())
			or not str(state.get("error", "")).is_empty())
	_expect(await _wait_for(actor_received),
		"actor type %d receives enhanced actor" % actor_type)
	var actor: Dictionary = state.get("actor", {}) as Dictionary
	_expect(int(actor.get("actor_type", -1)) == actor_type,
		"actor type %d survives server round trip" % actor_type)
	var actual: Dictionary = actor.get("appearance", {}) as Dictionary
	for key: String in ["skin", "hair", "shirt", "pants", "boots", "head", "eyes"]:
		_expect(int(actual.get(key, -1)) == int(requested[key]),
			"actor type %d preserves %s" % [actor_type, key])
	network.disconnect_from_server()
	network.queue_free()
	for unused_frame: int in range(3):
		await process_frame

func _wait_for(predicate: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + int(TIMEOUT_SECONDS * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if predicate.call():
			return true
		await process_frame
	return bool(predicate.call())

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_fail(message)

func _fail(message: String) -> void:
	_failures += 1
	push_error("FAIL: " + message)
