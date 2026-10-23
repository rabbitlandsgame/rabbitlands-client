extends SceneTree

var failures := 0
var sent: Array[String] = []
var window: Control
var _categories: Array = []

func _init() -> void:
	_run.call_deferred()

func _record(command: String) -> Error:
	sent.append(command)
	return OK

func _run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("leaderboard test timed out"); quit(1))
	_check_portrait_contract()
	_check_shortcut_migration()
	root.size = Vector2i(1280, 800)
	root.get_node("Network").block_for_hud_preview()
	window = load("res://src/ui/leaderboards_window.gd").new()
	root.add_child(window)
	window.configure(_record)
	await process_frame
	window.toggle()
	_expect(sent.back() == "#leaderboards invasion_kills all 1", "opening requests current rankings")
	_categories = _catalogue()
	var state := _snapshot(1)
	var packet: Dictionary = EloriaProtocol.decode_server(194, JSON.stringify(state).to_utf8_buffer())
	_expect(packet.type == "leaderboard", "structured ranking packet decodes")
	if packet.type != "leaderboard":
		print("DECODE: ", packet)
		print("SNAPSHOT: ", JSON.stringify(state))
		quit(1)
		return
	root.get_node("AppState")._on_packet(194, JSON.stringify(state).to_utf8_buffer())
	await process_frame
	_expect(window.podium.get_child_count() == 3, "three podium cards")
	_expect(window.podium.get_child(0).name == "Place2" and window.podium.get_child(1).name == "Place1", "winner is centered")
	_expect(window.rows.get_child_count() == 7, "ranks four to ten form the table")
	_expect(window.personal.text == "Your rank: 12", "actual personal rank outside the top ten")
	_expect(window._category_buttons.size() == 22, "all categories are reachable")
	window._choose_period(30)
	_expect(sent.back() == "#leaderboards invasion_kills 30 2", "period sends a distinct server request")
	window.apply_snapshot(state)
	_expect(window.personal.text == "Your rank: —", "stale response cannot replace new selection")
	state = _snapshot(2, 30)
	state.rows = []
	state.self = {"name":"Kellan", "rank":null, "value":"0", "level":null}
	window.apply_snapshot(state)
	_expect(window.status.text == "No ranked activity yet." and window.personal.text == "Your rank: Unranked", "empty period has honest placeholders")
	window._choose_category("overall")
	state = _snapshot(3, 30, "overall")
	state.rows[0].value = "9007199254740993"
	state.rows[0].level = null
	var decoded: Dictionary = EloriaProtocol.decode_server(194, JSON.stringify(state).to_utf8_buffer())
	_expect(decoded.data.rows[0].value == "9007199254740993", "large XP is lossless")
	window.apply_snapshot(decoded.data)
	_expect(window.podium.get_child(1).get_node("Card").get_child(0).get_node("Value").text == "9,007,199,254,740,993", "large XP is formatted without floating point")
	window.search.text = "rare"
	window._filter_categories("rare")
	var visible_categories := 0
	for button: Button in window._category_buttons.values():
		if button.visible: visible_categories += 1
	_expect(visible_categories == 2, "search filters all category groups")
	window.search.text = ""
	window._filter_categories("")
	window._choose_category("invasion_kills")
	window.close()
	window.apply_snapshot(_snapshot(4))
	_expect(not window.is_open(), "late reply cannot reopen a closed window")
	state = _snapshot(0)
	window.apply_snapshot(state)
	_expect(window.is_open(), "explicit chat command opens its ranking")
	await process_frame
	await process_frame
	_expect(window.panel.get_global_rect().end.x <= 1184 and window.panel.get_global_rect().end.y <= 712,
		"window respects the right rail and bottom HUD")
	if OS.get_environment("RL_LEADERBOARD_CAPTURE") != "":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(OS.get_environment("RL_LEADERBOARD_CAPTURE"))
	root.size = Vector2i(1024, 600)
	await process_frame
	await process_frame
	var compact_bounds := window.get_viewport_rect().size
	_expect(window.panel.get_global_rect().end.x <= compact_bounds.x - 96 and window.panel.get_global_rect().end.y <= compact_bounds.y - 88,
		"compact window remains within the viewport")
	var close_button: Button = window.panel.get_node("Body/Header/Close")
	_expect(window.panel.get_global_rect().encloses(close_button.get_global_rect()), "Close remains reachable on a smaller screen")
	root.size = Vector2i(1280, 800)
	root.get_node("AppState")._on_connection_state_changed("disconnected")
	_expect(not window.is_open() and root.get_node("AppState").leaderboard.is_empty(), "disconnect removes rankings")
	_expect(EloriaProtocol.decode_server(194, "{}".to_utf8_buffer()).type == "invalid", "malformed snapshot is rejected")
	window.queue_free()
	await process_frame
	if OS.get_environment("RL_LEADERBOARD_MAIN_TEST") == "1":
		await _check_main()
	print("leaderboards: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_main() -> void:
	if OS.get_environment("RL_LEADERBOARD_WIDE_PREVIEW") == "1":
		root.size = Vector2i(1600, 1000)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	_expect(main.get_script() != null, "main scene controller compiles")
	if main.get_script() == null:
		main.free()
		return
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	root.get_node("AppState").authenticated = true
	window = main.leaderboards_window
	window.configure(_record)
	var button := main.get_node("%LeaderboardsButton") as Button
	if button == null:
		_expect(false, "the game exposes a leaderboard HUD button")
		main.queue_free()
		return
	button.pressed.emit()
	_expect(window.is_open(), "HUD button opens the real game window")
	_expect(window.panel in main.window_stack._windows, "window participates in stacking and pointer routing")
	var state := _snapshot(1)
	if OS.get_environment("RL_LEADERBOARD_PORTRAITS") == "1":
		state = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/leaderboards_portraits.json"))
	state.rows[4].is_self = true
	state.self = state.rows[4].duplicate()
	window.apply_snapshot(state)
	await process_frame
	_expect(window.rows.get_child_count() == 7, "real client renders the ranking snapshot")
	if OS.get_environment("RL_LEADERBOARD_PORTRAITS") == "1":
		while not window.portraits.is_idle():
			await process_frame
		_expect(window.portraits.textures.size() == 10, "all ten real appearance portraits bake successfully")
		var pixels: Dictionary = {}
		for texture: Texture2D in window.portraits.textures.values():
			pixels[texture.get_image().get_data().hex_encode().sha256_text()] = true
		_expect(pixels.size() >= 8, "different character appearances produce different portraits")
		var before: int = window.portraits.textures.size()
		window._draw_rankings()
		await process_frame
		_expect(window.portraits.is_idle() and window.portraits.textures.size() == before, "redrawing reuses baked portraits")
	if OS.get_environment("RL_LEADERBOARD_MAIN_CAPTURE") != "":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(OS.get_environment("RL_LEADERBOARD_MAIN_CAPTURE"))
	if OS.get_environment("RL_LEADERBOARD_PORTRAITS") == "1":
		await _check_all_races(window.portraits)
	var escape := InputEventAction.new()
	escape.action = "cancel"
	escape.pressed = true
	main._unhandled_input(escape)
	_expect(not window.is_open(), "Escape closes the real window")
	var shortcut := InputEventAction.new()
	shortcut.action = "toggle_leaderboards"
	shortcut.pressed = true
	main._unhandled_input(shortcut)
	_expect(window.is_open(), "rebindable leaderboard shortcut opens the real window")
	window.close()
	var physical := InputEventKey.new()
	physical.physical_keycode = KEY_L
	physical.ctrl_pressed = true
	physical.shift_pressed = true
	physical.pressed = true
	main._unhandled_input(physical)
	_expect(window.is_open() and not main.extension_windows.mail_panel.visible,
		"Ctrl+Shift+L opens leaderboards without claiming the mail shortcut")
	window.close()
	physical.shift_pressed = false
	main._unhandled_input(physical)
	_expect(main.extension_windows.mail_panel.visible and not window.is_open(), "Ctrl+L keeps opening Mail")
	main.queue_free()
	await process_frame

func _check_all_races(service: Node) -> void:
	var keys: Array[String] = []
	for option: Dictionary in service._registry.get("creationOptions", []):
		var look := {"actor_type":int(option.actorType),
			"appearance":{"skin":0, "hair":104, "eyes":1, "shirt":0, "pants":1, "boots":2, "head":0},
			"equipment_visuals":{}}
		keys.append(service.cache_key(look))
		service.request(look)
	await process_frame
	while not service.is_idle():
		await process_frame
	for key: String in keys:
		_expect(service.textures.has(key), "every character-creation race and sex has a working portrait")
	_expect(keys.size() == 16, "all sixteen playable character models were checked")

func _check_portrait_contract() -> void:
	var state: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/leaderboards_portraits.json"))
	var valid := EloriaProtocol.decode_server(194, JSON.stringify(state).to_utf8_buffer())
	_expect(valid.type == "leaderboard", "real server appearance snapshot decodes")
	var service = load("res://src/ui/leaderboard_portraits.gd")
	var look: Dictionary = state.rows[0].portrait.duplicate(true)
	var key: String = service.cache_key(look)
	look.appearance.hair = 299
	_expect(service.cache_key(look) != key, "appearance changes invalidate portrait cache keys")
	state.rows[0].portrait.appearance.hair = 300
	_expect(EloriaProtocol.decode_server(194, JSON.stringify(state).to_utf8_buffer()).type == "invalid", "invalid appearance is rejected")

func _check_shortcut_migration() -> void:
	var bindings = load("res://src/ui/key_bindings.gd")
	var path := "user://leaderboards_test_keys.ini"
	var actions := ["toggle_leaderboards", "toggle_mail"]
	bindings.reset_to_defaults(actions)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string("#KEYS_VERSION = 2\n#K_TOGGLE_LEADERBOARDS = CTRL L\n#K_TOGGLE_MAIL = CTRL L\n")
	file.close()
	bindings.load_file(actions, path)
	var event := InputEventKey.new()
	event.physical_keycode = KEY_L
	event.ctrl_pressed = true
	event.shift_pressed = true
	event.pressed = true
	_expect(event.is_action_pressed("toggle_leaderboards", false, true), "old conflicting default migrates to Ctrl+Shift+L")
	event.shift_pressed = false
	_expect(event.is_action_pressed("toggle_mail", false, true) and not event.is_action_pressed("toggle_leaderboards", false, true), "mail keeps its existing shortcut")
	file = FileAccess.open(path, FileAccess.WRITE)
	file.store_string("#KEYS_VERSION = 2\n#K_TOGGLE_LEADERBOARDS = ALT K\n")
	file.close()
	bindings.load_file(actions, path)
	var custom: InputEvent = InputMap.action_get_events("toggle_leaderboards")[0]
	_expect(bindings.describe(custom) == "ALT K", "migration retains the player's custom shortcut")
	bindings.reset_to_defaults(actions)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))

func _snapshot(id: int, days := 0, category := "invasion_kills") -> Dictionary:
	var names := ["Mira", "Rowan", "Tavi", "Nash", "Kellan", "Ari", "Ilse", "Bren", "Sera", "Orin"]
	var values := ["8420", "7965", "6218", "4880", "3108", "2794", "2245", "1930", "1482", "1120"]
	var ranked: Array = []
	for i: int in names.size():
		ranked.append({"rank":i + 1, "name":names[i], "value":values[i], "level":null, "is_self":false})
	return {"version":1, "request_id":id, "category":category, "days":days,
		"categories":_categories, "rows":ranked,
		"self":{"name":"Watcher", "rank":12, "value":"987", "level":null}}

func _catalogue() -> Array:
	var result: Array = []
	for skill: String in ["overall", "attack", "defense", "harvesting", "alchemy", "magic", "potion", "summoning", "manufacturing", "crafting", "engineering", "tailoring", "ranging"]:
		result.append({"key":skill, "label":skill.capitalize(), "group":"Progression & Skills", "unit":"XP", "icon":skill})
	for item: Array in [["invasion_kills", "Invasion kills", "Kills", "combat"], ["boss_kills", "Invasion boss kills", "Kills", "combat"], ["instances_completed", "Instances completed", "Instances", "world"], ["ranging_kills", "Ranging kills", "Kills", "ranging"], ["summoning_kills", "Summoning kills", "Kills", "summoning"], ["magic_kills", "Magic kills", "Kills", "magic"], ["harvests", "Harvests", "Harvests", "harvesting"], ["rare_mixes", "Rare mixes", "Mixes", "alchemy"], ["rare_stones", "Rare stone finds", "Finds", "gathering"]]:
		result.append({"key":item[0], "label":item[1], "group":"Activity", "unit":item[2], "icon":item[3]})
	return result

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
