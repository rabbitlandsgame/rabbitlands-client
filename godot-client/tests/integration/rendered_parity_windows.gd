extends SceneTree
## Renders the Eternal Lands parity windows this client opens from its icon
## row - the spell book, the emote picker and the ranging readout - plus the
## settings window's HUD tab, and saves each as a PNG for visual review.
##
## Follows rendered_legacy_hud.gd: fixture state is injected into AppState,
## nothing touches the network, and a PASS line is evidence of rendering only.

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
		_finish()
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
	app_state.set("stats", {"health": 72, "max_health": 100, "ether": 33,
		"max_ether": 50, "magic": 17, "food": 42})
	# AppState.known_knowledge is a typed Array[int]; an untyped literal is
	# silently rejected by set(), so the value must be typed to land. Two
	# books and one spell tome read, by the server's knowledge indices.
	var fixture_knowledge: Array[int] = [0, 3, 16]
	app_state.set("known_knowledge", fixture_knowledge)
	# One of Heal's three reagents, so the spell book's reagent line is
	# captured with both states it can draw: what is carried, and what is not.
	app_state.set("inventory", {0: {"image_id": 16, "quantity": 4}})
	main.call("_sync_stats")
	for unused_frame: int in range(8):
		await process_frame

	var spells_window: Control = main.get("spells_window") as Control
	spells_window.call("toggle")
	_expect(bool(spells_window.call("is_open")), "the spells window opens")
	# The detail block is the half of this window worth reviewing - the
	# requirements it writes out - and it is blank until a spell is picked.
	var embermend := spells_window.find_child("SpellButton0", true, false) as Button
	_expect(embermend != null, "Heal has a button to select")
	if embermend != null:
		embermend.pressed.emit()
		await process_frame
	await _capture("parity-spells-window.png")
	spells_window.call("close")

	var emotes_window: Control = main.get("emotes_window") as Control
	emotes_window.call("toggle")
	_expect(bool(emotes_window.call("is_open")), "the emotes window opens")
	await _capture("parity-emotes-window.png")
	emotes_window.call("close")

	var ranging_window: Control = main.get("ranging_window") as Control
	ranging_window.call("toggle")
	_expect(bool(ranging_window.call("is_open")), "the ranging window opens")
	await _capture("parity-ranging-window.png")
	ranging_window.call("close")

	var settings_window: Control = main.get("settings_window") as Control
	settings_window.call("toggle")
	(settings_window.get("tabs") as TabContainer).current_tab = 0
	await _capture("parity-settings-hud-tab.png")
	settings_window.call("close")
	_finish()

func _capture(file_name: String) -> void:
	for unused_frame: int in range(4):
		await process_frame
	RenderingServer.force_draw(false)
	var image_value: Variant = root.get_texture().get_image()
	if not image_value is Image:
		_expect(false, "rendered screenshot is available")
		return
	var image: Image = image_value as Image
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		"rendered screenshot has reference dimensions")
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
		(app_state.get("stats") as Dictionary).clear()
	print("rendered parity windows: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
