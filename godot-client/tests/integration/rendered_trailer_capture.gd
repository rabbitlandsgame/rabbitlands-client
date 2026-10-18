extends SceneTree
## Trailer capture in the live client (main.gd `_configure_trailer_capture`).
## Without `-- --trailer-capture` F9 does nothing. With it, F9 cycles the HUD,
## a clean feed of the world alone, and the clean feed without nameplates; a
## window opened under the clean feed never reaches the frame, and the feed
## leaves with the game view. Writes the three looks to ELORIA_ARTIFACT_DIR.
##
## Run (needs a display): Godot_v4.7.2-stable_win64.exe --path . \
##     --script res://tests/integration/rendered_trailer_capture.gd

const SCREEN_SIZE := Vector2i(1280, 720)
const OTHER_ACTOR := 100

var _artifact_directory := ""
var _failures := 0
var _main: Control

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path("res://test-artifacts/trailer-capture")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		_finish()
		return
	_main = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("LoginBackground") as TextureRect).hide()
	(_main.get_node("LoginPanel") as Control).hide()
	(_main.get_node("GameView") as Control).show()
	var app_state: Node = root.get_node("AppState")
	app_state.set("authenticated", true)
	app_state.set("local_actor_id", 99)
	app_state.set("current_map", "four_gates")
	app_state.set("actors", {
		99: {"actor_id": 99, "x": 58, "y": 58, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Ari", "health": 72, "max_health": 100,
			"alive": true, "sitting": false},
		OTHER_ACTOR: {"actor_id": OTHER_ACTOR, "x": 61, "y": 60, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Bram", "health": 100, "max_health": 100,
			"alive": true, "sitting": false}})
	app_state.set("stats", {"health": 72, "max_health": 100, "ether": 33, "max_ether": 50,
		"food": 42, "carried": 205, "capacity": 320})
	var chat_lines: Array = app_state.get("chat_lines") as Array
	chat_lines.clear()
	chat_lines.append({"channel": 3, "text": "Welcome to Four Gates."})
	app_state.set("game_minute", 150)
	app_state.set("game_minute_anchor_msec", Time.get_ticks_msec())
	_main.call("_load_server_map")
	_main.call("_sync_world")
	_main.call("_sync_stats")
	_main.call("_sync_chat")
	_main.call("_reveal_chat_messages")
	# The map binds and its ground streams in over frames; film it, not the
	# placeholder ground main.gd hides once a map is bound.
	var deadline := Time.get_ticks_msec() + 60000
	while Time.get_ticks_msec() < deadline and not _map_settled():
		await process_frame
	for unused: int in range(12):
		await process_frame

	await _press_capture_key()
	_expect(int(_main.get("_trailer_capture_level")) == 0,
		"without --trailer-capture the key does nothing")
	_expect(_main.find_child("TrailerCaptureFeed", false, false) == null,
		"and no clean feed exists")

	_main.call("_configure_trailer_capture", PackedStringArray(["--trailer-capture"]))
	var hud := await _capture("trailer-capture-0-hud.png")
	_expect(bool(_main.call("_nameplate_visible_for", OTHER_ACTOR)), "nameplates are drawn with the HUD")

	await _press_capture_key()
	_expect(int(_main.get("_trailer_capture_level")) == 1, "the key moves to the clean feed")
	var clean := await _capture("trailer-capture-1-clean.png")
	_expect(_changed_fraction(clean, _world_frame()) < 0.01, "the clean feed is the world view alone")
	_expect(_changed_fraction(hud, clean) > 0.03, "the HUD is gone from the clean feed (%.3f changed)" % [
		_changed_fraction(hud, clean)])
	_expect(bool(_main.call("_nameplate_visible_for", OTHER_ACTOR)), "the clean feed keeps nameplates")
	_main.call("_on_inventory_button_pressed")
	var with_window := await _capture("")
	_expect((_main.get("inventory_panel") as Control).visible, "a window opens under the clean feed")
	_expect(_changed_fraction(with_window, _world_frame()) < 0.01,
		"and stays out of the frame")
	_main.call("_on_inventory_button_pressed")

	await _press_capture_key()
	_expect(int(_main.get("_trailer_capture_level")) == 2, "the key moves on to the feed without nameplates")
	_expect(not bool(_main.call("_nameplate_visible_for", OTHER_ACTOR)), "nameplates are hidden")
	await _capture("trailer-capture-2-no-nameplates.png")

	await _press_capture_key()
	var feed := _main.find_child("TrailerCaptureFeed", false, false) as CanvasLayer
	_expect(int(_main.get("_trailer_capture_level")) == 0 and not feed.visible, "and back to the HUD")
	_expect(bool(_main.call("_nameplate_visible_for", OTHER_ACTOR)), "with nameplates again")

	await _press_capture_key()
	(_main.get_node("GameView") as Control).hide()
	_expect(not feed.visible, "the clean feed leaves with the game view")
	(_main.get_node("GameView") as Control).show()
	_expect(feed.visible, "and returns with it")
	_finish()

## True once the world view draws the map: the placeholder is gone and the
## frame has scene detail, as the region renders judge it.
func _map_settled() -> bool:
	if (_main.get("fallback_ground") as Node3D).visible:
		return false
	var image := _world_frame()
	var colours := {}
	for y: int in range(0, image.get_height(), 24):
		for x: int in range(0, image.get_width(), 24):
			colours[image.get_pixel(x, y).to_html()] = true
	return colours.size() >= 64

func _press_capture_key() -> void:
	var key := InputEventKey.new()
	key.physical_keycode = KEY_F9
	key.keycode = KEY_F9
	key.pressed = true
	root.push_input(key)
	var release := key.duplicate() as InputEventKey
	release.pressed = false
	root.push_input(release)
	for unused: int in range(3):
		await process_frame

func _capture(file_name: String) -> Image:
	for unused: int in range(6):
		await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	if not file_name.is_empty():
		_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK, "saved " + file_name)
	return image

## The world viewport's own frame, at the screen's size.
func _world_frame() -> Image:
	var image := (_main.get("main_viewport") as SubViewport).get_texture().get_image()
	image.resize(SCREEN_SIZE.x, SCREEN_SIZE.y, Image.INTERPOLATE_BILINEAR)
	return image

## The share of sampled pixels that differ clearly between two frames.
func _changed_fraction(a: Image, b: Image) -> float:
	if a.get_size() != b.get_size():
		return 1.0
	var changed := 0
	var sampled := 0
	for y: int in range(0, a.get_height(), 6):
		for x: int in range(0, a.get_width(), 6):
			var p := a.get_pixel(x, y)
			var q := b.get_pixel(x, y)
			sampled += 1
			if absf(p.r - q.r) + absf(p.g - q.g) + absf(p.b - q.b) > 0.12:
				changed += 1
	return float(changed) / float(maxi(sampled, 1))

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("rendered trailer capture: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	# As rendered_legacy_hud.gd quits: stop the map's neighbour streams and let
	# every import finish (never join one: ContinentChunkStream.drain_workers).
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
