extends SceneTree

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifact_directory := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path("res://test-artifacts/four-gates")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main HUD scene loads")
	if not scene_resource is PackedScene:
		await _finish()
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("LoginBackground") as TextureRect).hide()
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).show()
	var app_state: Node = root.get_node("AppState")
	app_state.set("authenticated", true)
	app_state.set("local_actor_id", 99)
	app_state.set("current_map", "four_gates")
	app_state.set("actors", {99: {
		"actor_id": 99, "x": 58, "y": 58, "rotation": 0, "actor_type": 1,
		"kind": 1, "name": "Ari", "health": 72, "max_health": 100,
		"alive": true, "sitting": false}})
	app_state.set("stats", {
		"health": 72, "max_health": 100, "ether": 33, "max_ether": 50,
		"action_points": 18, "max_action_points": 30, "food": 42,
		"carried": 205, "capacity": 320,
		"physique": 52, "physique_base": 52, "coordination": 52, "coordination_base": 52,
		"reasoning": 40, "reasoning_base": 40, "will": 52, "will_base": 52,
		"instinct": 52, "instinct_base": 52, "vitality": 4, "vitality_base": 4,
		"human_nexus": 9, "animal_nexus": 6, "vegetal_nexus": 4,
		"inorganic_nexus": 6, "artificial_nexus": 6, "magic_nexus": 2,
		"attack": 24, "defense": 21, "harvesting": 8, "alchemy": 12,
		"magic": 17, "potion": 9, "summoning": 4, "manufacturing": 14,
		"crafting": 11, "engineering": 3, "tailoring": 6, "ranging": 19,
		"overall": 4, "overall_base": 22, "overall_level": 22,
		"harvesting_base": 8, "harvesting_exp": 1480,
		"harvesting_exp_next": 2066})
	app_state.set("inventory", {
		0: {"image_id": 3, "quantity": 9, "slot": 0, "inventory_usable": true},
		1: {"image_id": 31, "quantity": 2, "slot": 1, "inventory_usable": true},
		2: {"image_id": 35, "quantity": 1, "slot": 2, "inventory_usable": true},
		3: {"image_id": 42, "quantity": 4, "slot": 3, "inventory_usable": true}})
	app_state.set("active_channels", [1, 4, 12])
	app_state.set("active_channel_index", 1)
	var chat_lines: Array = app_state.get("chat_lines") as Array
	chat_lines.clear()
	chat_lines.append({"channel": 3, "text": "Welcome to Four Gates."})
	chat_lines.append({"channel": 0, "text": "Legacy HUD layout ready."})
	app_state.set("game_minute", 91)
	app_state.set("game_minute_anchor_msec", Time.get_ticks_msec())
	main.call("_load_server_map")
	main.call("_sync_world")
	main.call("_sync_stats")
	main.call("_sync_inventory")
	main.call("_sync_channel_tabs")
	main.call("_sync_chat")
	main.call("_reveal_chat_messages")
	for unused_frame: int in range(12):
		await process_frame
	var bottom_meters: HBoxContainer = main.get_node("%BottomMeters") as HBoxContainer
	_expect(bottom_meters.get_child(0).name == "ManaMeter"
		and bottom_meters.get_child(1).name == "FoodMeter"
		and bottom_meters.get_child(5).name == "ExperienceMeter",
		"lower HUD uses EL meter order")
	_expect((main.get_node("%FoodBottom") as ProgressBar).value == 42.0,
		"food meter is server driven")
	_expect((main.get_node("%OverheadPlayerName") as Label).text == "Ari",
		"zoom-stable player name is above overhead meters")
	main.call("_on_floating_feedback_requested", {
		"kind": "experience", "skill": "harvesting", "amount": 12})
	await _capture("legacy-hud.png")
	main.call("_open_actor_hud_menu", Vector2(510.0, 300.0))
	await _capture("legacy-hud-context-menu.png")
	main.call("_close_settings")
	main.call("_toggle_minimap")
	await _capture("legacy-hud-minimap.png")
	main.call("_toggle_minimap")
	main.call("_on_inventory_button_pressed")
	await _capture("legacy-inventory.png")
	main.call("_on_inventory_button_pressed")
	main.call("_on_stats_button_pressed")
	await _capture("legacy-statistics.png")
	(main.get_node("GameView/StatsPanel/Content/StatsTabs") as TabContainer).current_tab = 2
	main.call("_sync_counters")
	await _capture("legacy-counters.png")
	(main.get_node("GameView/StatsPanel/Content/StatsTabs") as TabContainer).current_tab = 3
	main.call("_sync_session_experience")
	await _capture("legacy-session-experience.png")
	# The pick-point spending this client adds: the "+" beside a raisable
	# line on the statistics tab, and the perks the server offers on its own.
	var app_state_perks: Node = root.get_node("AppState")
	app_state_perks.call("_on_packet", 215, ("02000500c8000000457863617661746f72005477696365206173206d616e79206974656d732e0000fdff00000000506f7765722048756e677279004c6f7365203320666f6f6420706572206d696e7574652e00596f7520616c726561647920686176652074686174207065726b2e00").hex_decode())
	(main.get_node("GameView/StatsPanel/Content/StatsTabs")
		as TabContainer).current_tab = 4
	for unused_perk_frame: int in range(3):
		await process_frame
	await _capture("legacy-perks.png")
	(main.get_node("GameView/StatsPanel/Content/StatsTabs")
		as TabContainer).current_tab = 0
	main.call("_on_stats_meta_clicked", "spend:attribute:physique")
	for unused_confirm_frame: int in range(3):
		await process_frame
	var confirm_button: Button = main.get("stats_pickpoint_confirm") as Button
	_expect(confirm_button.is_visible_in_tree() and not confirm_button.disabled,
		"the draft has a visible Confirm button")
	await _capture("legacy-spend-pickpoint.png")
	main.call("_adjust_pickpoint", "attribute", "physique", -1)
	(main.get_node("GameView/StatsPanel") as Control).hide()
	main.call("_toggle_full_map")
	for unused_frame: int in range(4):
		await process_frame
	var map_image: TextureRect = main.get_node(
		"GameView/FullMap/MapLayout/MapImage") as TextureRect
	var map_motion: InputEventMouseMotion = InputEventMouseMotion.new()
	map_motion.position = map_image.size * 0.5
	main.call("_on_full_map_gui_input", map_motion)
	await _capture("legacy-full-map.png")
	main.call("_show_continent_view")
	await _capture("legacy-continent-map.png")
	main.call("_preview_region", 1)
	await _capture("legacy-region-preview.png")
	(main.get_node("GameView/FullMap") as Control).hide()
	main.call("_toggle_console")
	await _capture("legacy-chat-console.png")
	main.call("_toggle_console")
	main.call("_on_options_pressed")
	await _capture("legacy-hud-settings.png")
	await _finish()

func _capture(file_name: String) -> void:
	for unused_frame: int in range(4):
		await process_frame
	RenderingServer.force_draw(false)
	var image_value: Variant = root.get_texture().get_image()
	if not image_value is Image:
		_expect(false, "rendered HUD screenshot is available")
		return
	var image: Image = image_value as Image
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		"rendered HUD screenshot has reference dimensions")
	var sampled_colors: Dictionary = {}
	for y: int in range(0, image.get_height(), 16):
		for x: int in range(0, image.get_width(), 16):
			sampled_colors[image.get_pixel(x, y).to_html()] = true
	_expect(sampled_colors.size() >= 48, "rendered HUD contains visual detail")
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"saved " + file_name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	var app_state: Node = root.get_node_or_null("AppState")
	if app_state != null:
		app_state.set("authenticated", false)
		app_state.set("local_actor_id", -1)
		app_state.set("current_map", "")
		app_state.set("active_channels", [0, 0, 0])
		app_state.set("active_channel_index", 0)
		(app_state.get("actors") as Dictionary).clear()
		(app_state.get("stats") as Dictionary).clear()
		(app_state.get("inventory") as Dictionary).clear()
		(app_state.get("chat_lines") as Array).clear()
	print("rendered legacy HUD: ", "PASS" if _failures == 0 else "FAIL")
	# The HUD's map streams its neighbours and their chunks on workers.
	# Quitting under a live import tears the scripts down beneath it: a crash
	# at exit, or script errors from the half-built map. Stop the exterior
	# stream and let every import finish first, as main.gd's _close_client
	# does (never join one: ContinentChunkStream.drain_workers).
	# Collected first: clearing a stream frees nodes this walk would visit.
	var streams: Array[ExteriorRegionStream] = []
	for node: Node in root.find_children("*", "", true, false):
		if node is ExteriorRegionStream:
			streams.append(node as ExteriorRegionStream)
	for stream: ExteriorRegionStream in streams:
		stream.clear()
		var deadline := Time.get_ticks_msec() + 30000
		while is_instance_valid(stream) and not stream.is_idle() and Time.get_ticks_msec() < deadline:
			await process_frame
	await ContinentChunkStream.drain_workers(self)
	quit(_failures)
