extends SceneTree

const LaunchOptions = preload("res://src/updates/launch_options.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var defaults := PackedStringArray(["--server=play.example.org", "--port=2000"])
	var plain := LaunchOptions.game_arguments([], defaults, "C:/Game Folder", false)
	_expect(plain == PackedStringArray(["--", "--server=play.example.org", "--port=2000"]),
		"normal launch preserves server defaults")
	for flag: String in ["--client-debug", "--client-compatibility", "--client-safe-mode"]:
		var args := LaunchOptions.game_arguments([flag, "--port=2001"], defaults, "C:/Game Folder", true)
		var separator := args.find("--")
		_expect(args[0] == "--headless", "headless startup is preserved")
		_expect(args.find("--log-file") < separator and args.find("--verbose") < separator,
			"diagnostic engine flags precede the user-argument separator")
		_expect(args.slice(separator + 1) == PackedStringArray(
			["--server=play.example.org", "--port=2000", flag, "--port=2001"]),
			"launch mode and game arguments survive for an updater restart")
		if flag != "--client-debug":
			_expect(args.find("--rendering-method") < separator and "gl_compatibility" in args
				and "opengl3" in args, "compatibility forces OpenGL before engine startup")
		_expect(args[args.find("--log-file") + 1].begins_with("C:/Game Folder/"),
			"log path stays a single argument even with spaces")
	var previous := {}
	for key: String in ["ELORIA_LOOK", "ELORIA_LOOK_QUALITY", "ELORIA_VRAM_TEXTURES", "ELORIA_NO_MAP_CACHE"]:
		previous[key] = OS.get_environment(key) if OS.has_environment(key) else null
	LaunchOptions.apply_environment(["--client-safe-mode"])
	_expect(OS.get_environment("ELORIA_LOOK") == "0", "safe mode bypasses the painted look")
	_expect(OS.get_environment("ELORIA_LOOK_QUALITY") == "low", "safe mode uses low quality")
	_expect(OS.get_environment("ELORIA_VRAM_TEXTURES") == "0", "safe mode uses original map textures")
	_expect(OS.get_environment("ELORIA_NO_MAP_CACHE") == "1", "safe mode bypasses the map cache")
	for key: String in previous:
		if previous[key] == null:
			OS.unset_environment(key)
		else:
			OS.set_environment(key, previous[key])

	var main := load("res://src/app/main.tscn").instantiate() as Control
	if main.get_script() == null:
		main.free()
		quit(1)
		return
	root.add_child(main)
	await process_frame
	await process_frame
	var snapshot: Dictionary = main.client_diagnostic_snapshot()
	_expect(snapshot.get("camera_present", false), "snapshot finds the gameplay camera")
	_expect(snapshot.get("viewport_texture_bound", false), "snapshot checks the displayed viewport texture")
	_expect(snapshot.has("draw_calls") and snapshot.has("actors_received") and snapshot.has("map_cache_status"),
		"snapshot captures rendering, server state and map loading")
	if DisplayServer.get_name() != "headless":
		main._set_login_screen_visible(false)
		main.game_view.show()
		for _frame: int in range(8):
			await process_frame
		snapshot = main.client_diagnostic_snapshot()
		_expect(snapshot.get("game_visible", false) and int(snapshot.get("draw_calls", 0)) > 0,
			"visible gameplay viewport reports actual draw submissions")
	# These values must never appear in captured output, including failed login.
	main.user_edit.text = "DIAGNOSTIC_PRIVATE_USERNAME"
	main.password_edit.text = "DIAGNOSTIC_PRIVATE_PASSWORD"
	root.get_node("Network").login(main.user_edit.text, main.password_edit.text)
	main._on_login_failed("DIAGNOSTIC_PRIVATE_REPLY")
	main._record_client_snapshot()
	main.queue_free()
	await process_frame
	await process_frame
	print("compatibility diagnostics tests: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
