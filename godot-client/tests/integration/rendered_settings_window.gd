extends SceneTree
## The settings window's Graphics tab over a real map, as a player opens it:
## the graphics quality and the painted look beside the frame cap and the
## other switches. Writes settings_window.png to ELORIA_ARTIFACT_DIR and checks
## that both new rows are on screen, inside the window, and the window clear
## of the resource rail.
##
## ELORIA_SETTINGS_MAP names the map behind it (lantern_reach by default).
## Main reads and may write user://eloria_hud.cfg; the player's file is copied
## first and put back after.

const SCREEN_SIZE := Vector2i(1280, 720)
const SETTINGS_PATH := "user://eloria_hud.cfg"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var out := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/four-gates")
	DirAccess.make_dir_recursive_absolute(out)
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings \
		else PackedByteArray()
	root.size = SCREEN_SIZE
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var state: Node = root.get_node("AppState")
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	(main.get_node("LoginBackground") as Control).hide()
	main.get("game_view").show()
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	var map_id := OS.get_environment("ELORIA_SETTINGS_MAP")
	if map_id.is_empty():
		map_id = "lantern_reach"
	state.set("current_map", map_id)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(loader.world_root != null, "%s loads behind the window" % map_id)
	var adapter: CoordinateAdapter = main.get("adapter")
	var tile: Vector2i = adapter.godot_to_server(Vector3(17.0, 0.0, -20.0))
	state.set("local_actor_id", 1)
	state.set("actors", {1: {"actor_id": 1, "x": tile.x, "y": tile.y, "rotation": 0,
		"actor_type": 0, "kind": 1, "name": "Traveller", "health": 100, "max_health": 100,
		"alive": true, "appearance": {}}})
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	for frame: int in 90:
		await physics_frame
		await process_frame

	main.call("_on_more_settings_pressed")
	var window: Control = main.get("settings_window") as Control
	var panel := window.get_node("SettingsWindow") as PanelContainer
	var tabs := window.get("tabs") as TabContainer
	var look := window.find_child("look", true, false) as CheckBox
	var quality := window.find_child("quality", true, false) as OptionButton
	tabs.current_tab = window.call("tab_index_for", look)
	for frame: int in 10:
		await process_frame
	var rect := panel.get_global_rect()
	_expect(panel.visible and Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).encloses(rect),
		"the window is open and on screen: %s" % rect)
	for control: Control in [look, quality]:
		_expect(control.is_visible_in_tree() and rect.encloses(control.get_global_rect()),
			"%s is shown inside the window: %s" % [control.name, control.get_global_rect()])
	var rail: Control = main.get_node("GameView/ResourceHud") as Control
	_expect(not rect.intersects(rail.get_global_rect()), "clear of the resource rail")
	RenderingServer.force_draw(false)
	var path := out.path_join("settings_window.png")
	root.get_texture().get_image().save_png(path)
	print("SETTINGS_WINDOW saved ", path, " look=", look.button_pressed,
		" quality=", quality.get_item_text(quality.selected))

	main.call("_on_disconnect_pressed")
	main.get("exterior_stream").clear()
	while not main.get("exterior_stream").is_idle():
		await process_frame
	for frame: int in 6:
		await process_frame
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("rendered settings window: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
