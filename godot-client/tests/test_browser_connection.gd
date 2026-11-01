extends SceneTree
## Local integration probe for the real autoloads, packet decoder and server.
## Credentials are supplied by the isolated test runner through environment.
var network: Node
var state: Node
var failed := false

func _initialize() -> void:
	_run.call_deferred()

func _wait_for(predicate: Callable, seconds := 15.0) -> bool:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while not predicate.call() and Time.get_ticks_msec() < deadline and not failed:
		await create_timer(0.05).timeout
	return predicate.call() and not failed

func _run() -> void:
	network = root.get_node("Network")
	state = root.get_node("AppState")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	var configured: Dictionary = network.configure_coordinate_profiles(registry.get("coordinateProfiles", {}),
		registry.get("coordinateMapNames", {}), registry.get("maps", {}))
	if not configured.ok:
		_finish(false, "coordinate registry")
		return
	state.login_failed.connect(func(_message: String): failed = true)
	var websocket := "--probe-websocket" in OS.get_cmdline_user_args()
	var error: Error = (network.connect_to_websocket("ws://127.0.0.1:2002", "http://127.0.0.1:8060") if websocket
		else network.connect_to_server("127.0.0.1", 22000, false))
	if error != OK or not await _wait_for(func(): return state.connection_state == "connected"):
		_finish(false, "connect")
		return
	if network.login(OS.get_environment("RL_QA_USER"), OS.get_environment("RL_QA_PASSWORD")) != OK \
			or not await _wait_for(func(): return state.authenticated):
		_finish(false, "login")
		return
	network.send_client_capabilities()
	if not await _wait_for(func(): return state.local_actor_id >= 0 and state.actors.has(state.local_actor_id) and (not network.coordinates.selected or network.coordinates.ready())):
		_finish(false, "world snapshot")
		return
	network.send_chat("#arrived " + str(state.current_map))
	var actor: Dictionary = state.actors[state.local_actor_id]
	var start := Vector2i(int(actor.x), int(actor.y))
	var target := start + Vector2i(1, 0)
	network.move_to(target)
	if not await _wait_for(func():
		var current: Dictionary = state.actors.get(state.local_actor_id, {})
		return int(current.get("x", -1)) == target.x and int(current.get("y", -1)) == target.y):
		_finish(false, "authoritative movement")
		return
	var marker := "Browser transport integration probe"
	network.send_chat(marker)
	if not await _wait_for(func(): return str(state.chat_lines).contains(marker)):
		_finish(false, "chat echo")
		return
	network.disconnect_from_server()
	_finish(true, "WebSocket" if websocket else "desktop TCP")

func _finish(ok: bool, stage: String) -> void:
	print("browser_connection_probe ", "PASS " if ok else "FAIL ", stage)
	quit(0 if ok else 1)
