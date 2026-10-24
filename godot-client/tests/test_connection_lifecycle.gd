extends SceneTree
## Production console/input/logout controls plus real loopback reauthentication.

var network_client_script: GDScript
var failures := 0
var scene: Control
var network: Node
var app: Node

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	# The retained storage guards reference AppState. Load after autoloads are
	# registered rather than compiling Network while this entry script loads.
	network_client_script = load("res://src/network/network_client.gd")
	if not network_client_script.can_instantiate():
		push_error("Network fixture could not compile")
		quit(1)
		return
	if OS.get_cmdline_user_args().has("--network-only"):
		await _test_loopback_session()
		await _test_stalled_retry()
		await _test_secure_retry()
		print("connection network tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
		quit(failures)
		return
	root.size = Vector2i(1280, 720)
	scene = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(scene)
	await process_frame
	network = root.get_node("Network")
	app = root.get_node("AppState")
	# Synthetic UI sessions do not need a socket. The independent loopback
	# client below exercises the actual TCP lifecycle and login packets.
	network.set_process(false)
	_expect(network.HEARTBEAT_INTERVAL_MSEC == 25000, "heartbeat retains its 25-second cadence")
	_expect(network.RECONNECT_INTERVAL_MSEC == 2000, "reconnect cadence is two seconds")

	_begin_ui_session()
	app.append_local_message("Conversation before the connection dropped.")
	app.active_channels.assign([3, 6, 0])
	app.active_channel_index = 1
	app.actors[42] = {"name": "old actor"}
	scene.popup_panel.show()
	scene.purchase_confirm.show()
	(scene.reference_window.get("panel") as Control).show()
	var announced: Array[Array] = []
	network.reconnect_progress.connect(func(attempt: int, total: int, delay: int) -> void:
		announced.append([attempt, total, delay]))
	network.call("_drop_connection", "socket_error")
	await process_frame
	_expect(scene.game_view.visible and not scene.get_node("LoginPanel").visible
		and scene.console_panel.visible, "a dropped session opens the console and retains the game HUD")
	_expect(bool(scene.get("_disconnect_console_active")) and not app.authenticated
		and app.actors.is_empty(), "the disconnected console blocks gameplay and clears stale actors")
	_expect(not scene.popup_panel.visible and not scene.purchase_confirm.visible
		and not (scene.reference_window.get("panel") as Control).visible,
		"old session popups cannot cover the disconnect console")
	_expect(str(app.chat_lines).contains("Conversation before")
		and str(app.chat_lines).contains("Disconnected from server!")
		and str(app.chat_lines).contains("Press any key"), "console preserves conversation and adds reconnect instructions")
	_expect(app.active_channels == [3, 6, 0] and app.active_channel_index == 1,
		"recoverable drops preserve the channel tabs and selection")
	_expect(not network.is_reconnecting() and announced.is_empty(), "a drop waits for a key without starting retries")
	_expect(bool(scene.get("_resync_after_reconnect")), "the next authenticated session requests fresh world snapshots")
	_expect(scene.connection_banner.visible and scene.connection_banner.text.contains("press any key"),
		"the banner identifies the dormant disconnect state")
	var rail: Control = scene.get_node("GameView/ResourceHud")
	_expect(not scene.connection_banner.get_global_rect().intersects(rail.get_global_rect()),
		"the connection banner leaves the resource rail visible")

	_key(KEY_SPACE)
	_expect(network.is_reconnecting() and announced.size() == 1 and announced[0] == [1, 0, 0],
		"the first key starts an immediate unlimited retry loop")
	_key(KEY_SPACE, true)
	_key(KEY_A)
	_expect(announced.size() == 1, "held and additional keys do not overlap or restart attempts")
	for _attempt: int in range(12):
		network.set("_reconnect_at_msec", 0)
		network.set("_reconnect_started_msec", Time.get_ticks_msec())
		network.call("_schedule_reconnect")
	_expect(network.is_reconnecting() and network.reconnect_attempt() == 13
		and announced.back()[2] >= 1990 and announced.back()[2] <= 2000,
		"subsequent attempts retain the two-second cadence beyond the old retry limit")
	_logout_through_icon()
	_expect(not scene.game_view.visible and scene.get_node("LoginPanel").visible
		and not scene.console_panel.visible, "the disconnect menu icon returns to login during retry")
	_expect(not network.is_reconnecting() and not network.can_resume_session()
		and str(network.get("_session_password")).is_empty() and app.chat_lines.is_empty(),
		"explicit logout cancels retries, forgets credentials and clears the prior session")

	_begin_ui_session()
	scene.call("_on_chat_submitted", "#DiScO")
	_expect(scene.console_panel.visible and bool(scene.get("_disconnect_console_active"))
		and network.can_resume_session() and not network.is_reconnecting()
		and network.last_disconnect_reason == "manual_disconnect", "#disco enters the same dormant console state")
	_logout_through_icon()
	_expect(app.chat_lines.is_empty() and not network.is_session_disconnect(),
		"logout also clears a socket that was already dormant")

	_begin_ui_session()
	app.append_local_message("Keep context for a fatal connection failure.")
	network.fail_coordinate_context("coordinate_registry_invalid")
	_expect(scene.console_panel.visible and network.is_session_disconnect()
		and not network.can_resume_session() and str(app.chat_lines).contains("Keep context"),
		"fatal session failures preserve the console context without reusable credentials")
	_key(KEY_A)
	_expect(not network.is_reconnecting(), "fatal session failure cannot retry with invalid coordinate context")
	_logout_through_icon()
	_expect(app.chat_lines.is_empty(), "logout clears fatal disconnect context even without a transport transition")

	if not OS.get_cmdline_user_args().has("--ui-only"):
		await _test_loopback_session()
		await _test_stalled_retry()
		await _test_secure_retry()
	network.disconnect_from_server()
	scene.queue_free()
	await process_frame
	print("connection lifecycle tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _begin_ui_session() -> void:
	network.disconnect_from_server()
	network.set("_host", "127.0.0.1")
	network.set("_port", 1)
	network.set("_session_username", "fixture")
	network.set("_session_password", "in-memory-fixture")
	network.set("_session_credentials_confirmed", true)
	network.call("_set_state", "connected")
	app.authenticated = true
	scene.get_node("LoginPanel").hide()
	scene.game_view.show()
	scene.console_panel.hide()
	scene.set("_disconnect_console_active", false)

func _key(code: Key, echo := false) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.keycode = code
	event.pressed = true
	event.echo = echo
	root.push_input(event, true)

func _logout_through_icon() -> void:
	# Exercise the production menu icon's connected signal.
	scene.get_node("%DisconnectButton").pressed.emit()

func _test_loopback_session() -> void:
	var client: Variant = network_client_script.new()
	root.add_child(client)
	var listener := TCPServer.new()
	_expect(listener.listen(0, "127.0.0.1") == OK, "loopback server opens")
	_expect(client.connect_to_server("127.0.0.1", listener.get_local_port(), false) == OK,
		"fixture uses an explicitly selected developer TCP connection")
	if not await _until(func() -> bool: return listener.is_connection_available()):
		_expect(false, "loopback server accepts the initial connection")
		client.queue_free()
		listener.stop()
		return
	var peer := listener.take_connection()
	await _until(func() -> bool: return client.get("_state") == "connected")
	_expect(client.login("reconnect-fixture", "process-only-fixture") == OK, "initial login reaches the socket")
	var original_login: PackedByteArray = await _receive_login(peer)
	_expect(not original_login.is_empty(), "loopback receives the initial login packet")
	peer.put_data(EloriaProtocol.encode(EloriaProtocol.ServerMessage.LOG_IN_OK))
	_expect(await _until(func() -> bool: return client.get("_session_credentials_confirmed")),
		"credentials become resumable only after successful server authentication")
	peer.disconnect_from_host()
	_expect(await _until(func() -> bool: return client.get("_state") == "disconnected"),
		"peer closure enters dormant disconnect")
	await create_timer(0.1).timeout
	_expect(client.can_resume_session() and not client.is_reconnecting()
		and not listener.is_connection_available(), "a real authenticated socket drop waits for the first key")
	_expect(client.start_reconnecting(), "a real disconnected session can start retrying")
	if not await _until(func() -> bool: return listener.is_connection_available()):
		_expect(false, "loopback accepts a resumed transport")
		client.disconnect_from_server()
		client.queue_free()
		listener.stop()
		return
	peer = listener.take_connection()
	var resumed_login: PackedByteArray = await _receive_login(peer)
	_expect(resumed_login == original_login and not resumed_login.is_empty(),
		"the new socket automatically authenticates the same account")
	peer.put_data(EloriaProtocol.encode(EloriaProtocol.ServerMessage.LOG_IN_OK))
	_expect(await _until(func() -> bool: return not client.is_reconnecting())
		and not client.can_resume_session(), "successful reauthentication stops the retry loop")

	client.disconnect_for_reconnect()
	client.start_reconnecting()
	await _until(func() -> bool: return listener.is_connection_available())
	peer.disconnect_from_host()
	peer = listener.take_connection()
	if peer != null:
		await _receive_login(peer)
		peer.put_data(EloriaProtocol.encode(EloriaProtocol.ServerMessage.LOG_IN_NOT_OK))
		await _until(func() -> bool: return not client.is_reconnecting())
		_expect(not client.can_resume_session() and str(client.get("_session_password")).is_empty(),
			"a rejected resumed login stops retries and forgets credentials")
		peer.disconnect_from_host()
	else:
		_expect(false, "loopback accepts the authentication rejection fixture")
	client.disconnect_from_server()
	client.queue_free()
	listener.stop()
	await process_frame

func _test_stalled_retry() -> void:
	var client: Variant = network_client_script.new()
	root.add_child(client)
	var listener := TCPServer.new()
	_expect(listener.listen(0, "127.0.0.1") == OK, "stalled retry server opens")
	client.set("_host", "127.0.0.1")
	client.set("_port", listener.get_local_port())
	client.set("_secure", false)
	client.set("_session_username", "stalled-fixture")
	client.set("_session_password", "unused-fixture")
	client.set("_session_credentials_confirmed", true)
	client.disconnect_for_reconnect()
	client.start_reconnecting()
	await _until(func() -> bool: return listener.is_connection_available())
	var peer := listener.take_connection()
	await _until(func() -> bool: return client.get("_state") == "connected")
	# Advance only the retry deadline: the server intentionally never replies
	# to login, so this covers the hung-authentication branch without a sleep.
	client.set("_reconnect_timeout_at_msec", maxi(1, Time.get_ticks_msec() - 1))
	await process_frame
	_expect(client.is_reconnecting() and client.last_disconnect_reason == "reconnect_timeout"
		and client.reconnect_attempt() >= 2, "a stalled login is bounded and schedules another attempt")
	client.disconnect_from_server()
	if peer != null: peer.disconnect_from_host()
	client.queue_free()
	listener.stop()
	await process_frame

func _test_secure_retry() -> void:
	var client: Variant = network_client_script.new()
	root.add_child(client)
	var listener := TCPServer.new()
	_expect(listener.listen(0, "127.0.0.1") == OK, "secure retry server opens")
	client.set("_host", "127.0.0.1")
	client.set("_port", listener.get_local_port())
	client.set("_session_username", "secure-fixture")
	client.set("_session_password", "must-not-be-plaintext")
	client.set("_session_credentials_confirmed", true)
	client.disconnect_for_reconnect()
	client.start_reconnecting()
	await _until(func() -> bool: return listener.is_connection_available())
	var peer := listener.take_connection()
	if peer == null:
		_expect(false, "loopback accepts the secure retry")
		client.disconnect_from_server()
		client.queue_free()
		listener.stop()
		return
	var opening := await _receive_bytes(peer)
	_expect(opening.size() >= 3 and opening[0] == 0x16 and opening[1] == 0x03
		and client.login("secure-fixture", "must-not-be-plaintext") == ERR_UNCONFIGURED,
		"resumed secure sessions send TLS handshake bytes before any credentials")
	peer.disconnect_from_host()
	await _until(func() -> bool: return client.get("_state") == "reconnecting")
	# The next attempt can run immediately in this fixture, but must retain
	# exactly the same certificate verification settings as the first one.
	client.set("_reconnect_at_msec", maxi(1, Time.get_ticks_msec()))
	await _until(func() -> bool: return listener.is_connection_available())
	peer = listener.take_connection()
	if peer != null:
		opening = await _receive_bytes(peer)
		_expect(opening.size() >= 3 and opening[0] == 0x16 and opening[1] == 0x03
			and bool(client.get("_secure")), "a failed secure handshake retries TLS without plaintext fallback")
		peer.disconnect_from_host()
	else:
		_expect(false, "loopback accepts another secure retry")
	client.disconnect_from_server()
	client.queue_free()
	listener.stop()
	await process_frame

func _receive_bytes(peer: StreamPeerTCP) -> PackedByteArray:
	var deadline := Time.get_ticks_msec() + 5000
	while Time.get_ticks_msec() < deadline:
		peer.poll()
		if peer.get_available_bytes() > 0:
			return peer.get_data(peer.get_available_bytes())[1]
		await process_frame
	return PackedByteArray()

func _receive_login(peer: StreamPeerTCP) -> PackedByteArray:
	var buffer := PackedByteArray()
	var deadline := Time.get_ticks_msec() + 5000
	while Time.get_ticks_msec() < deadline:
		peer.poll()
		var available := peer.get_available_bytes()
		if available > 0:
			var result := peer.get_data(available)
			if result[0] != OK: break
			buffer.append_array(result[1])
		while not buffer.is_empty():
			var decoded := EloriaProtocol.try_decode(buffer)
			if decoded.status != "ok": break
			if decoded.command == EloriaProtocol.ClientMessage.LOG_IN:
				return decoded.payload
			buffer = buffer.slice(int(decoded.consumed))
		await process_frame
	return PackedByteArray()

func _until(predicate: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + 5000
	while Time.get_ticks_msec() < deadline:
		if predicate.call(): return true
		await process_frame
	return false

func _expect(value: bool, label: String) -> void:
	if value: return
	failures += 1
	push_error("FAIL: " + label)
