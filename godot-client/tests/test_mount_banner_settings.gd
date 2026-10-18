extends SceneTree
## Settings, the character shortcut and the floating banner share one preference.
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	root.size = Vector2i(1280, 720)
	var path := "user://eloria_hud.cfg"
	var had_settings := FileAccess.file_exists(path)
	var original := FileAccess.get_file_as_bytes(path) if had_settings else PackedByteArray()
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.set_script(load("res://tests/fixtures/viewport_actions_main.gd"))
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.game_view.show()
	main.login_panel.hide()
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 1
	state.actors = {1: {"actor_id": 1, "kind": 1, "alive": true},
		2: {"actor_id": 2, "kind": 1, "alive": true}}
	state.actor_mounts = {1: {"mode": "mounted", "gait": "cruise", "endurance_ms": 8000}}
	state.state_changed.emit(&"mount_states")
	var controls: Variant = main.game_view.get_node("MountControls")
	var window: Variant = main.settings_window
	var artifacts := ProjectSettings.globalize_path("res://").path_join("../.local/qa/mount-banner-settings").simplify_path()
	for key: String in controls.OPTION_LABELS:
		var box := window.panel.find_child("mount_banner_" + key, true, false) as CheckBox
		expect(box != null, "Banners settings include " + key)
		box.button_pressed = true
	var menu: PopupMenu = main._actor_hud_menu
	(main._banner_option_boxes.menu_disabled as CheckBox).button_pressed = false
	main.picked_actor = 1
	main._interaction_mode = "walk"
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_RIGHT
	click.pressed = true
	click.position = Vector2(500, 300)
	main._on_world_gui_input(click)
	expect(menu.visible and main._interaction_mode == "walk", "right-clicking self opens banner menu without cycling actions")
	expect(main._mount_banner_menu.item_count == controls.OPTION_LABELS.size(), "character menu includes all mount settings")
	if DisplayServer.get_name() != "headless":
		main._mount_banner_menu.position = menu.position + Vector2i(menu.size.x, 0)
		main._mount_banner_menu.popup()
		await process_frame
		await process_frame
		await RenderingServer.frame_post_draw
		expect(DirAccess.make_dir_recursive_absolute(artifacts) == OK, "review output directory is writable")
		expect(root.get_texture().get_image().save_png(artifacts.path_join("context.png")) == OK, "context menu screenshot saved")
	menu.hide()
	main._mount_banner_menu.hide()
	var endurance_index: int = controls.OPTION_LABELS.keys().find("endurance")
	main._mount_banner_menu.id_pressed.emit(endurance_index)
	var endurance_box := window.panel.find_child("mount_banner_endurance", true, false) as CheckBox
	window.open_tab("Banners")
	expect(not endurance_box.button_pressed and controls.status.text == "Trot", "context change updates Settings and visible mount contents")
	if DisplayServer.get_name() != "headless":
		await process_frame
		await process_frame
		await RenderingServer.frame_post_draw
		expect(root.get_texture().get_image().save_png(artifacts.path_join("settings.png")) == OK, "Settings screenshot saved")
	var gallop_box := window.panel.find_child("mount_banner_gallop_button", true, false) as CheckBox
	gallop_box.button_pressed = false
	var gallop_index: int = controls.OPTION_LABELS.keys().find("gallop_button")
	expect(not controls.gallop.visible and not main._mount_banner_menu.is_item_checked(gallop_index), "Settings change updates context checkmark and control")
	var config := ConfigFile.new()
	expect(config.load(path) == OK and config.get_value("mount_banner", "endurance", true) == false \
		and config.get_value("mount_banner", "gallop_button", true) == false, "mount choices persist to player settings")
	controls.set_options({})
	main._load_hud_settings()
	expect(not controls.gallop.visible and controls.status.text == "Trot", "saved choices restore on settings load")
	var name_box: CheckBox = main._banner_option_boxes.show_names
	name_box.button_pressed = true
	main._character_banner_menu.id_pressed.emit(0)
	expect(not name_box.button_pressed, "character banner settings are also adjustable from context menu")
	for row: Array in main.BANNER_ROWS:
		(main._banner_option_boxes[row[1]] as CheckBox).button_pressed = false
		(main._banner_option_boxes[row[2]] as CheckBox).button_pressed = false
	expect(main._banner_has_content(), "mount controls keep their anchor when character names and bars are hidden")
	var master := window.panel.find_child("mount_banner_show_banner", true, false) as CheckBox
	master.button_pressed = false
	expect(not controls.wants_banner(), "master setting hides banner without changing mount state")
	expect(state.actor_mounts[1].mode == "mounted", "banner preferences leave riding unchanged")
	window.close()
	main.picked_actor = 2
	main._on_world_gui_input(click)
	expect(not menu.visible and main._interaction_mode == "trade", "right-clicking another player still cycles world actions")
	main.queue_free()
	await process_frame
	if had_settings:
		FileAccess.open(path, FileAccess.WRITE).store_buffer(original)
	else:
		DirAccess.remove_absolute(path)
	print("MOUNT_BANNER_SETTINGS_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
