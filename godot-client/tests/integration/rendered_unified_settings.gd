extends SceneTree
## Render every unified settings tab, including its final control. This fixture
## needs no server or map load and uses an isolated user directory in CI/local QA.

var failures := 0
const SETTINGS_PATH := "user://eloria_hud.cfg"

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings else PackedByteArray()
	root.size = Vector2i(1280, 720)
	var out := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/unified-settings")
	DirAccess.make_dir_recursive_absolute(out)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	for frame: int in 4:
		await process_frame
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get_node("LoginBackground").hide()
	main.get("game_view").show()
	var window := main.get("settings_window") as Control
	var panel := window.get("panel") as PanelContainer
	for section: String in window.get("pages"):
		window.call("open_tab", section)
		for frame: int in 4:
			await process_frame
		var body := window.call("page_body", section) as VBoxContainer
		var scroll := body.get_parent() as ScrollContainer
		_expect(root.get_visible_rect().encloses(panel.get_global_rect()), section + " fits the screen")
		_expect(not panel.get_global_rect().intersects(
			(main.get_node("GameView/ResourceHud") as Control).get_global_rect()), section + " clears the rail")
		_save(out.path_join(section.to_lower() + ".png"))
		var last := body.get_child(body.get_child_count() - 1) as Control
		scroll.ensure_control_visible(last)
		for frame: int in 4:
			await process_frame
		_expect(last.is_visible_in_tree() and scroll.get_global_rect().intersects(last.get_global_rect()),
			section + " reaches its last row")
		_save(out.path_join(section.to_lower() + "-end.png"))
	window.call("open_tab", "HUD")
	root.size = Vector2i(960, 600)
	main.call("_on_ui_scale_changed", 1.5)
	for frame: int in 6:
		await process_frame
	_expect(panel.get_viewport_rect().encloses(panel.get_global_rect()), "high UI scale fits a smaller screen")
	_save(out.path_join("hud-large-ui.png"))
	main.call("_on_ui_scale_changed", 1.0)
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("rendered unified settings: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _save(path: String) -> void:
	RenderingServer.force_draw(false)
	var screenshot := root.get_texture().get_image()
	_expect(screenshot != null and screenshot.save_png(path) == OK, "saved " + path.get_file())

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
