extends SceneTree
## Exercise settings migration and the actual socket selected by the login flow.

const SETTINGS_PATH := "user://eloria_hud.cfg"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings else PackedByteArray()
	var config := ConfigFile.new()
	config.set_value("connection", "secure", false)
	config.set_value("notes", "text", "keep this player preference")
	_expect(config.save(SETTINGS_PATH) == OK, "legacy settings fixture is saved")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	_expect(not bool(main.get("_dev_plain_tcp")) and main.port_edit.value == 2001
		and main.host_edit.text == "game.rabbitlandsgame.com", "new launches default to TLS on public port 2001")
	_expect(main.get_node_or_null("LoginPanel/Content/Secure") == null
		and main.settings_window.find_child("secure", true, false) == null,
		"neither login nor settings offers an encryption switch")
	config.load(SETTINGS_PATH)
	_expect(config.get_value("connection", "secure") == true,
		"loading old preferences immediately migrates TLS from false to true")
	_expect(config.get_value("notes", "text") == "keep this player preference",
		"migration preserves unrelated preferences")
	config.erase_section_key("connection", "secure")
	config.save(SETTINGS_PATH)
	main.call("_load_hud_settings")
	config.load(SETTINGS_PATH)
	_expect(config.get_value("connection", "secure", false) == true,
		"settings from before the TLS preference also migrate")
	var migrated := FileAccess.get_file_as_bytes(SETTINGS_PATH)
	main.call("_load_hud_settings")
	_expect(FileAccess.get_file_as_bytes(SETTINGS_PATH) == migrated,
		"reloading migrated preferences is idempotent")

	main.call("_apply_connection_launch_options", PackedStringArray(["--dev-plain-tcp"]))
	_expect(bool(main.get("_dev_plain_tcp")) and main.host_edit.text == "127.0.0.1"
		and main.port_edit.value == 2000, "developer TCP defaults to the local server")
	for arguments: PackedStringArray in [
		PackedStringArray(["--port=2036", "--dev-plain-tcp", "--server=localhost"]),
		PackedStringArray(["--dev-plain-tcp", "--server=localhost", "--port=2036"])]:
		main.call("_apply_connection_launch_options", arguments)
		_expect(bool(main.get("_dev_plain_tcp")) and main.host_edit.text == "localhost"
			and main.port_edit.value == 2036, "developer endpoint overrides work in either argument order")
	main.call("_save_hud_settings")
	config.load(SETTINGS_PATH)
	_expect(config.get_value("connection", "secure") == true,
		"saving during a developer TCP session keeps TLS as the persisted default")
	main.call("_apply_connection_launch_options", PackedStringArray(["--port=0", "--port=65536", "--port=bad"]))
	_expect(not bool(main.get("_dev_plain_tcp")) and main.port_edit.value == 2001,
		"a later launch returns to TLS and invalid port overrides are ignored")
	main.call("_apply_connection_launch_options", PackedStringArray(["--server=127.0.0.1", "--port=2000"]))
	_expect(not bool(main.get("_dev_plain_tcp")),
		"a local address or port 2000 alone cannot disable TLS")

	await _test_socket(main, false)
	await _test_socket(main, true)
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("connection defaults tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _test_socket(main: Control, plain: bool) -> void:
	var network := root.get_node("Network")
	var app_state := root.get_node("AppState")
	var listener := TCPServer.new()
	if listener.listen(0, "127.0.0.1") != OK:
		_expect(false, "local socket fixture opens")
		return
	var arguments := PackedStringArray(["--server=127.0.0.1", "--port=%d" % listener.get_local_port()])
	if plain:
		arguments.append("--dev-plain-tcp")
	main.call("_apply_connection_launch_options", arguments)
	main.call("_on_connect_pressed")
	var deadline := Time.get_ticks_msec() + 5000
	while not listener.is_connection_available() and Time.get_ticks_msec() < deadline:
		await process_frame
	var peer := listener.take_connection()
	if peer == null:
		_expect(false, "login flow connects to the local socket fixture")
		network.disconnect_from_server()
		listener.stop()
		return
	deadline = Time.get_ticks_msec() + 5000
	while peer.get_available_bytes() < 3 and Time.get_ticks_msec() < deadline:
		peer.poll()
		await process_frame
	var available := peer.get_available_bytes()
	_expect(available >= 3, "login flow sends its opening bytes")
	if available >= 3:
		var data: PackedByteArray = peer.get_data(available)[1]
		if plain:
			_expect(app_state.connection_state == "connected" and not network.is_secure(),
				"the explicit developer option opens a usable plain TCP connection")
			_expect(data[0] == EloriaProtocol.ClientMessage.SEND_VERSION,
				"the developer connection carries the normal game protocol")
		else:
			_expect(data[0] == 0x16 and data[1] == 0x03,
				"normal login starts a TLS handshake even with a custom port")
			_expect(app_state.connection_state == "securing"
				and network.login("fixture", "unused") == ERR_UNCONFIGURED,
				"credentials cannot be sent before TLS completes")
			peer.disconnect_from_host()
			deadline = Time.get_ticks_msec() + 5000
			while app_state.connection_state != "disconnected" and Time.get_ticks_msec() < deadline:
				await process_frame
			_expect(app_state.connection_state == "disconnected" and bool(network.get("_secure"))
				and not network.is_reconnecting() and not listener.is_connection_available(),
				"an incomplete TLS handshake fails without retrying in plain TCP")
	network.disconnect_from_server()
	peer.disconnect_from_host()
	listener.stop()
	await process_frame

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
