extends SceneTree
## Capture the production HUD with representative joined channels and roster.
var failures := 0
var artifacts := ""
var main: Control
var app: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path("res://test-artifacts/party-chat-ui")
	DirAccess.make_dir_recursive_absolute(artifacts)
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	main.get_node("GameView/ChatWindow").set("preferences_path", artifacts.path_join("render-settings.cfg"))
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	app = root.get_node("AppState")
	app.set("authenticated", true)
	root.content_scale_factor = 1.0
	await _settle()
	app.call("_on_packet", 71, PackedByteArray([0, 1, 0, 0, 0, 4, 0, 0, 0, 12, 0, 0, 0]))
	(app.get("chat_lines") as Array).clear()
	_chat(3, "Welcome to Landfall. Your party is ready.", 5)
	_chat(0, "Mira: Meet at Rellan for the gauntlet.")
	_chat(5, "Tavi: Heading to the bridge.", 7)
	_chat(0, "[Party] Rowan: Ready when you are.", 4)
	_chat(0, "[Party] Nash: I have the sigils.", 4)
	_chat(6, "Ari: Buying Sunleaf at the market.", 2)
	_chat(1, "Mira: Save a place for me.", 1)
	var members: Array = []
	var names := ["Kellan", "Mira", "Rowan", "Nash", "Tavi", "Ilse"]
	for index in range(names.size()):
		members.append({"name": names[index], "leader": index == 0, "is_self": index == 0,
			"online": index < 5, "health": [180, 135, 36, 170, 150, 0][index], "max_health": 180,
			"ether": [60, 45, 16, 54, 20, 0][index], "max_ether": 60,
			"map_id": "landfall", "x": 139 + index, "y": 219})
	app.set("party", {"in_party": true, "members": members, "invited_by": "", "invite_seconds": 0})
	app.emit_signal("state_changed", &"party")
	var chat: PanelContainer = main.get("chat_hud")
	var windows: Control = main.get("extension_windows")
	chat.position = Vector2(12, 418)
	chat.resize_window(Vector2(430, 250))
	windows.party_panel.position = Vector2(12, 56)
	windows.set("_party_collapsed", false)
	windows.call("_layout_party")
	main.call("_on_chat_tab_pressed", "all")
	await _capture("party-chat-default.png")
	windows.resize_party_window(Vector2(164, 320))
	await _capture("party-narrow-bars.png")
	windows.party_options.get_popup().id_pressed.emit(0)
	await _capture("party-narrow-numbers.png")
	windows.resize_party_window(Vector2(280, 400))
	windows.party_panel.position = Vector2(470, 56)
	await _capture("party-wide-numbers.png")
	windows.party_panel.position = Vector2(12, 56)
	windows.resize_party_window(Vector2(164, 180))
	await _settle()
	windows.party_scroll.ensure_control_visible(windows.party_rows.get_child(5))
	await _capture("party-short-scrolled.png")
	windows.party_options.get_popup().id_pressed.emit(0)
	windows.party_options.get_popup().id_pressed.emit(1)
	main.call("_on_chat_tab_pressed", "party")
	windows.party_collapse.pressed.emit()
	await _capture("party-chat-collapsed.png")
	windows.party_collapse.pressed.emit()
	chat.position = Vector2(350, 250)
	chat.resize_window(Vector2(600, 360))
	main.call("_on_chat_tab_pressed", "all")
	await _capture("party-chat-moved-resized.png")
	root.size = Vector2i(1024, 600)
	chat.position = Vector2(12, 430)
	chat.resize_window(Vector2(320, 210))
	await _capture("party-chat-small-window.png")
	main.set_process(false)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_IBEAM)
	main.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("rendered party/chat HUD: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _chat(channel: int, message: String, colour: int = 0) -> void:
	var payload := PackedByteArray([channel, 128 + colour])
	payload.append_array(message.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _settle() -> void:
	for frame in range(6):
		await process_frame

func _capture(filename: String) -> void:
	await _settle()
	print("layout: chat=", main.chat_hud.get_global_rect(), " party=", main.extension_windows.party_panel.get_global_rect())
	await RenderingServer.frame_post_draw
	var captured: Image = root.get_texture().get_image()
	if captured == null or captured.get_size() != root.size:
		failures += 1
		push_error("FAIL: full rendered framebuffer: " + filename)
		return
	var low := 1.0
	var high := 0.0
	for y in range(0, captured.get_height(), 8):
		for x in range(0, captured.get_width(), 8):
			var value := captured.get_pixel(x, y).get_luminance()
			low = minf(low, value)
			high = maxf(high, value)
	if high - low < 0.05 or captured.save_png(artifacts.path_join(filename)) != OK:
		failures += 1
		push_error("FAIL: rendered capture: " + filename)
	print("capture: ", filename)
