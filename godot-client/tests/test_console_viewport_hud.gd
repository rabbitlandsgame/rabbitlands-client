extends SceneTree
const Presets := preload("res://src/ui/hud_presets.gd")
const PATH := "res://test-artifacts/console-viewport/hud.cfg"
var failures := 0
var main: Control

func _init() -> void: call_deferred("run")
func expect(value: bool, label: String) -> void:
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
func frames() -> void:
	for i: int in 6: await process_frame
func check_bounds() -> void:
	var workspace: Control = main.hud_workspace
	var console: Rect2 = main.console_panel.get_global_rect()
	expect(console.end.x <= workspace._visual_rect("rail_panel").position.x + 0.5,
		"console stays left of Classic rail")
	expect(console.end.y <= workspace._visual_rect("resources").position.y + 0.5,
		"console stays above Classic bottom meters")
	expect(console.size.x > 500 and console.size.y > 200, "console fills the remaining view")
	expect(workspace._root("utilities").is_visible_in_tree() and workspace._root("skills").is_visible_in_tree(),
		"HUD menu and statistics remain open")
func run() -> void:
	root.size = Vector2i(1280, 720)
	create_timer(90).timeout.connect(func() -> void: quit(99))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(PATH.get_base_dir()))
	var model := Presets.new()
	expect(model.working.console_fit_viewport, "Classic fits console by default")
	model.working.console_fit_viewport = false
	model.save_file(PATH)
	model.load_file(PATH)
	expect(not model.working.console_fit_viewport, "console option survives saving and reloading")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = PATH
	root.add_child(main)
	await frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var workspace: Control = main.hud_workspace
	workspace.choose_preset("heritage", true)
	await frames()
	main._toggle_console()
	await frames()
	check_bounds()
	root.size = Vector2i(1600, 900)
	await frames()
	check_bounds()
	workspace.open_editor()
	workspace.console_fit_toggle.button_pressed = false
	await frames()
	expect(main.console_panel.size.is_equal_approx(main.game_view.size), "turning option off restores full window console")
	workspace.undo_edit()
	await frames()
	expect(workspace.console_fit_toggle.button_pressed, "Undo restores checkbox and fitted console")
	check_bounds()
	workspace.redo_edit()
	workspace.cancel_edit()
	await frames()
	expect(workspace.model.working.console_fit_viewport, "Cancel restores original console option")
	check_bounds()
	main._toggle_console()
	await frames()
	expect(not main.console_panel.visible and workspace._root("utilities").is_visible_in_tree(), "closing console keeps HUD open")
	main.queue_free()
	await frames()
	print("CONSOLE VIEWPORT HUD: ", failures, " failures")
	quit(0 if failures == 0 else 1)
