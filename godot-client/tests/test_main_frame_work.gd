extends SceneTree
## Main's per-frame and per-packet work that waits for something to change:
## the weather's registry lookup, the inventory window's redraw while it is
## closed, the cooldown shades with no cooldown running, the minimap marks
## beyond its view, the campaign scenery's re-application, bursts of settings
## saves, and the console's bounded history.

const SETTINGS_PATH := "user://eloria_hud.cfg"
var failures := 0
var checks := 0
var app_state: Node

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, message: String) -> void:
	checks += 1
	if value:
		print("PASS: ", message)
		return
	failures += 1
	push_error("FAIL: " + message)

func _run() -> void:
	root.size = Vector2i(1280, 720)
	app_state = root.get_node("AppState")
	root.get_node("Network").call("block_for_hud_preview")
	# Settings below are written to the player's file; it is copied and put back.
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings else PackedByteArray()
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	await process_frame
	# Only the calls below drive Main: no frame may flush or refresh behind them.
	main.set_process(false)
	var previous_map: String = app_state.get("current_map")

	_check_weather_registry(main)
	_check_inventory_gate(main)
	_check_cooldown_shades(main)
	_check_minimap_reach(main)
	_check_campaign_world(main)
	_check_settings_bursts(main)
	_check_chat_history_bound(main)

	app_state.set("current_map", previous_map)
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("Main frame work: %d checks, %d failures" % [checks, failures])
	quit(failures)

func _check_weather_registry(main: Control) -> void:
	app_state.set("current_map", "landfall")
	_expect(bool(main.call("_current_map_outdoors")), "Landfall is outdoors")
	app_state.set("current_map", "landfall_town")
	_expect(not bool(main.call("_current_map_outdoors")), "a map's interior is not, once the map changes")
	app_state.set("current_map", "./maps/LANDFALL.elm")
	_expect(bool(main.call("_current_map_outdoors")), "a legacy reference resolves as before")
	var registry: Dictionary = main.get("map_registry")
	main.set("map_registry", {})
	_expect(not bool(main.call("_current_map_outdoors")), "a replaced registry is resolved again")
	main.set("map_registry", registry)
	_expect(bool(main.call("_current_map_outdoors")), "and the original registry once more")

func _check_inventory_gate(main: Control) -> void:
	var panel: Control = main.get("inventory_panel")
	var card: Control = (main.get("extension_windows") as Node).get("detail_panel")
	panel.hide()
	card.hide()
	var button: Button = (main.get("inventory_slot_buttons") as Array)[2]
	var quick: Button = (main.get("quick_slot_buttons") as Array)[2]
	var inventory: Dictionary = app_state.get("inventory")
	var was_authenticated: bool = app_state.get("authenticated")
	# Main follows inventory packets only for a signed-in session.
	app_state.set("authenticated", true)
	inventory.erase(2)
	main.call("_sync_inventory")
	var empty_tooltip := button.tooltip_text
	main.set("selected_inventory_slot", 5)
	inventory[2] = {"image_id": 3, "quantity": 7}
	app_state.emit_signal("state_changed", &"inventory")
	_expect(bool(main.get("_inventory_view_stale")) and button.tooltip_text == empty_tooltip,
		"a packet while the inventory is closed leaves its window for later")
	_expect((quick.get_node("Quantity") as Label).text == "7", "the HUD's quick slots follow the packet at once")
	_expect(int(main.get("selected_inventory_slot")) == -1, "a selection whose item is gone is still dropped")
	panel.show()
	_expect(not bool(main.get("_inventory_view_stale")) and button.tooltip_text != empty_tooltip
		and (button.get_node("Quantity") as Label).text == "7", "opening the inventory draws what arrived")
	inventory[2] = {"image_id": 3, "quantity": 9}
	app_state.emit_signal("state_changed", &"inventory")
	_expect((button.get_node("Quantity") as Label).text == "9", "an open inventory follows each packet")
	panel.hide()
	inventory.erase(2)
	app_state.emit_signal("state_changed", &"inventory")
	card.show()
	_expect(not bool(main.get("_inventory_view_stale")) and button.tooltip_text == empty_tooltip,
		"showing the item card alone also draws what arrived")
	card.hide()
	app_state.set("authenticated", was_authenticated)

func _check_cooldown_shades(main: Control) -> void:
	var cooldowns: Dictionary = app_state.get("inventory_cooldowns")
	cooldowns.clear()
	var quick: Button = (main.get("quick_slot_buttons") as Array)[0]
	main.call("_update_cooldown_overlays")
	var shade := quick.get_node("Cooldown") as ColorRect
	_expect(shade != null and not shade.visible and bool(main.get("_cooldown_shades_idle")),
		"with no cooldown the shades rest")
	cooldowns[0] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 5000}
	main.call("_update_cooldown_overlays")
	_expect(shade.visible and (quick.get_node("Seconds") as Label).text == "5"
		and not bool(main.get("_cooldown_shades_idle")), "a new cooldown wakes the shades")
	(cooldowns[0] as Dictionary)["end_msec"] = Time.get_ticks_msec() - 1
	main.call("_update_cooldown_overlays")
	_expect(not shade.visible and bool(main.get("_cooldown_shades_idle")), "an expired cooldown puts them back to rest")
	shade.visible = true
	main.call("_update_cooldown_overlays")
	_expect(shade.visible, "resting shades are not walked every frame")
	shade.visible = false
	cooldowns[0] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 2000}
	main.call("_update_cooldown_overlays")
	_expect(shade.visible, "a cooldown written into the same table wakes them again")
	cooldowns.clear()
	main.call("_update_cooldown_overlays")

func _check_minimap_reach(main: Control) -> void:
	var camera: Camera3D = main.get("map_camera")
	var viewport: SubViewport = main.get("map_viewport")
	if not camera.is_inside_tree():
		_expect(false, "the minimap camera is in the tree")
		return
	var saved_transform := camera.global_transform
	var saved_size := camera.size
	var saved_viewport := viewport.size
	viewport.size = Vector2i(264, 264)
	camera.global_position = Vector3(100, 220, 100)
	camera.rotation = Vector3(-PI * 0.5, 0.7, 0)
	camera.size = 80.0
	main.call("_begin_minimap_mark_cull")
	# Half the 80 m square's diagonal is 56.6 m; a quarter more is 70.7 m.
	_expect(bool(main.call("_within_minimap_reach", Vector3(150, 0, 100)))
		and bool(main.call("_within_minimap_reach", Vector3(145, 9, 145))),
		"marks on the minimap, at any heading, are collected")
	_expect(not bool(main.call("_within_minimap_reach", Vector3(175, 0, 100)))
		and not bool(main.call("_within_minimap_reach", Vector3(100, 0, 20))),
		"marks well beyond its corners are not")
	# The camera is put over the local player after the marks are collected,
	# so a player who has just jumped is where the cull is centred.
	var actors: Dictionary = main.get("actor_nodes")
	var local_id: int = app_state.get("local_actor_id")
	var displaced: Variant = actors.get(local_id)
	var player := Node3D.new()
	root.add_child(player)
	player.global_position = Vector3(400, 0, 100)
	actors[local_id] = player
	main.call("_begin_minimap_mark_cull")
	_expect(bool(main.call("_within_minimap_reach", Vector3(440, 0, 100)))
		and not bool(main.call("_within_minimap_reach", Vector3(150, 0, 100))),
		"the cull is centred on the player the camera is about to follow")
	if displaced == null:
		actors.erase(local_id)
	else:
		actors[local_id] = displaced
	player.free()
	main.set("_minimap_mark_reach", INF)
	_expect(bool(main.call("_within_minimap_reach", Vector3(9000, 0, 9000))), "the full map's collection is not culled")
	camera.rotation = Vector3(-PI * 0.3, 0, 0)
	main.call("_begin_minimap_mark_cull")
	_expect(bool(main.call("_within_minimap_reach", Vector3(9000, 0, 9000))), "a tilted camera is never culled")
	main.set("_minimap_mark_reach", INF)
	camera.global_transform = saved_transform
	camera.size = saved_size
	viewport.size = saved_viewport

func _check_campaign_world(main: Control) -> void:
	var saved: Dictionary = app_state.get("campaign")
	app_state.set("campaign", {"active": false, "kind": "rescue", "run_id": ""})
	main.set("_campaign_world_key", [])
	main.call("_apply_campaign_world")
	var key: Array = main.get("_campaign_world_key")
	_expect(not key.is_empty(), "the campaign scenery is applied on first sight")
	main.set("_campaign_world_applied_msec", Time.get_ticks_msec() - 10)
	var marker: int = main.get("_campaign_world_applied_msec")
	main.call("_apply_campaign_world")
	_expect(int(main.get("_campaign_world_applied_msec")) == marker, "an unchanged campaign is not applied again at once")
	(app_state.get("campaign") as Dictionary)["run_id"] = "edited-in-place"
	main.call("_apply_campaign_world")
	_expect(int(main.get("_campaign_world_applied_msec")) != marker
		and main.get("_campaign_world_key") != key, "a campaign changed in place is applied again")
	main.set("_campaign_world_applied_msec", Time.get_ticks_msec() - 1000)
	marker = main.get("_campaign_world_applied_msec")
	main.call("_apply_campaign_world")
	_expect(int(main.get("_campaign_world_applied_msec")) != marker,
		"an unchanged campaign is still applied again after a quarter second (late ground)")
	app_state.set("campaign", saved)

func _notes_on_disk() -> String:
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	return str(config.get_value("notes", "text", ""))

func _check_settings_bursts(main: Control) -> void:
	main.set("_hud_settings_saved_msec", -1)
	main.call("_on_notes_changed", "first note")
	_expect(_notes_on_disk() == "first note", "the first change after a quiet interval is written at once")
	main.call("_on_notes_changed", "first note, then more")
	main.call("_on_notes_changed", "first note, then more typing")
	_expect(_notes_on_disk() == "first note" and bool(main.get("_hud_settings_dirty")),
		"the rest of a burst waits")
	main.call("_flush_hud_settings_save")
	_expect(_notes_on_disk() == "first note", "and is not written before its interval has passed")
	main.set("_hud_settings_saved_msec", Time.get_ticks_msec() - 1000)
	main.call("_flush_hud_settings_save")
	_expect(_notes_on_disk() == "first note, then more typing" and not bool(main.get("_hud_settings_dirty")),
		"the burst's last change is written once the interval has passed")
	main.call("_on_notes_changed", "edited again")
	_expect(_notes_on_disk() == "first note, then more typing", "a change inside the next interval waits")
	main.call("_save_hud_settings")
	_expect(_notes_on_disk() == "edited again" and not bool(main.get("_hud_settings_dirty")),
		"any direct save writes the waiting change with the rest")
	main.call("_on_notes_changed", "closing")
	main.call("_flush_hud_settings_save", true)
	_expect(_notes_on_disk() == "closing", "closing the client writes a waiting change")
	main.call("_on_notes_changed", "")
	main.call("_save_hud_settings")
	_check_presets_in_one_save(main)

## Main's settings save carries the HUD presets in its own write instead of the
## workspace loading and saving the whole file again after it: what the
## workspace captures live (here the minimap switch) is in the file after one
## save, and the presets file path decides whether it may join.
func _check_presets_in_one_save(main: Control) -> void:
	var workspace: Control = main.get("hud_workspace") as Control
	var model: Variant = workspace.get("model")
	if not bool(workspace.get("ready_to_layout")) or bool(workspace.call("is_open")) \
			or (not bool(model.get("loaded")) and bool((model.get("working") as Dictionary).get("legacy", false))):
		_expect(false, "the HUD workspace can store presets in this fixture")
		return
	_expect(not bool(workspace.call("sync_settings_into", ConfigFile.new(), "user://another_settings.cfg")),
		"presets kept in another file never join Main's write")
	var shown: bool = main.get("_minimap_visible")
	for value: bool in [not shown, shown]:
		main.set("_minimap_visible", value)
		main.call("_save_hud_settings")
		var config := ConfigFile.new()
		config.load(SETTINGS_PATH)
		var working: Variant = config.get_value("hud_presets", "working", {})
		_expect(working is Dictionary and bool(((working as Dictionary).get("parts", {}) as Dictionary)
				.get("minimap", {}).get("enabled", not value)) == value,
			"one Main save writes the presets as captured (minimap %s)" % ("shown" if value else "hidden"))

func _check_chat_history_bound(main: Control) -> void:
	# A detached AppState: Main is not listening to this one.
	var script := load("res://src/state/app_state.gd") as GDScript
	var state: Node = script.new()
	var limit: int = int(script.get_script_constant_map()["CHAT_HISTORY_LIMIT"])
	for index: int in range(limit + 25):
		state.call("append_local_line", "line %d" % index)
	var history: Array = state.get("chat_history")
	var recent: Array = state.get("chat_lines")
	_expect(history.size() == limit and str((history[0] as Dictionary).text) == "line 25"
		and str((history.back() as Dictionary).text) == "line %d" % (limit + 24),
		"the console keeps the newest %d lines" % limit)
	_expect(is_same(recent.back(), history.back()), "the recent lines still share the history's line records")
	state.free()
	# The console renders no more than that bound however many lines it is given.
	var saved: Array = app_state.get("chat_history")
	var lines: Array[Dictionary] = []
	for index: int in range(limit + 40):
		lines.append({"channel": 254, "text": "history %d" % index, "stamp": "00:00:00"})
	app_state.set("chat_history", lines)
	main.call("_sync_console")
	var console: RichTextLabel = main.get("console_output")
	_expect(console.get_paragraph_count() <= limit + 1, "the console shows at most %d lines (%d)" % [
		limit, console.get_paragraph_count()])
	app_state.set("chat_history", saved)
	main.call("_sync_console")
