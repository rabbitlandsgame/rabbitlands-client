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
	state.actor_mounts = {1: {"mode": "mounted", "gait": "cruise", "endurance_ms": 8000,
		"mount_id": "moor_pony", "selected_mount_id": "moor_pony", "blocked_reason": "",
		"owned_mount_ids": ["moor_pony", "golden_plains_horse", "crystalback_tortoise", "rabbit", "jadefeather_raptor"]}}
	state.state_changed.emit(&"mount_states")
	var controls: Variant = main.game_view.get_node("MountControls")
	var window: Variant = main.settings_window
	var artifacts := ProjectSettings.globalize_path("res://").path_join("../.local/qa/mount-banner-settings").simplify_path()
	for key: String in controls.OPTION_LABELS:
		var box := window.panel.find_child("mount_banner_" + key, true, false) as CheckBox
		expect(box != null, "Banners settings include " + key)
		box.button_pressed = true
	var menu: Variant = main._actor_hud_menu
	(main._banner_option_boxes.menu_disabled as CheckBox).button_pressed = false
	main.picked_actor = 1
	main._interaction_mode = "walk"
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_RIGHT
	click.pressed = true
	click.position = Vector2(500, 300)
	main._on_world_gui_input(click)
	expect(menu.visible and main._interaction_mode == "walk", "right-clicking self opens banner menu without cycling actions")
	expect(menu.mount_boxes.size() == controls.OPTION_LABELS.size(), "one popover includes all mount settings")
	expect(menu.tabs.current_tab == 0, "right-clicking the character opens Character settings")
	if DisplayServer.get_name() != "headless":
		menu.tabs.current_tab = 1
		await process_frame
		await process_frame
		await RenderingServer.frame_post_draw
		expect(DirAccess.make_dir_recursive_absolute(artifacts) == OK, "review output directory is writable")
		expect(root.get_texture().get_image().save_png(artifacts.path_join("context.png")) == OK, "context menu screenshot saved")
	menu.hide()
	(menu.mount_boxes.endurance as CheckBox).button_pressed = false
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
	expect(not controls.gallop.visible and not menu.mount_boxes.gallop_button.button_pressed, "Settings change updates popover checkmark and control")
	var config := ConfigFile.new()
	expect(config.load(path) == OK and config.get_value("mount_banner", "endurance", true) == false \
		and config.get_value("mount_banner", "gallop_button", true) == false, "mount choices persist to player settings")
	controls.set_options({})
	main._load_hud_settings()
	expect(not controls.gallop.visible and controls.status.text == "Trot", "saved choices restore on settings load")
	var name_box: CheckBox = main._banner_option_boxes.show_names
	name_box.button_pressed = true
	(menu.character_boxes.show_names as CheckBox).button_pressed = false
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
	# The same panel is reachable directly from the mount controls and own name.
	controls.choose.gui_input.emit(click)
	expect(menu.visible and menu.tabs.current_tab == 1, "right-clicking mount controls opens the Mount tab directly")
	(menu.mount_boxes.status as CheckBox).button_pressed = false
	expect(menu.visible, "changing an option keeps the popover open")
	var escape := InputEventKey.new()
	escape.physical_keycode = KEY_ESCAPE
	escape.pressed = true
	main._input(escape)
	expect(not menu.visible, "Escape dismisses the popover before other windows")
	main.overhead_player_name.gui_input.emit(click)
	expect(menu.visible and menu.tabs.current_tab == 0, "right-clicking own name opens Character settings")
	menu.open_at(Vector2(1270,710), "Mount")
	for frame: int in 4: await process_frame
	expect(menu.panel.get_global_rect().end.x <= main.game_view.size.x - 96 + 1 \
		and menu.panel.get_global_rect().end.y <= main.game_view.size.y - 86 + 1, "popover stays inside the game and clear of the HUD")
	var outside := InputEventMouseButton.new()
	outside.button_index = MOUSE_BUTTON_LEFT
	outside.pressed = true
	outside.position = Vector2(2,2)
	main._input(outside)
	expect(not menu.visible and main._interaction_mode == "walk", "outside click dismisses without starting world actions")
	menu.open_at(Vector2(500,300))
	main._on_state_changed(&"npc_dialogue")
	expect(not menu.visible, "server dialogue takes precedence over the banner popover")
	var mount_button := main.get_node("%MountsButton") as Button
	expect(mount_button.icon != null, "bottom HUD has a mount icon")
	mount_button.pressed.emit()
	expect(main.mounts_window.is_open() and mount_button.button_pressed, "HUD mount icon opens selection and highlights")
	mount_button.pressed.emit()
	expect(not main.mounts_window.is_open() and not mount_button.button_pressed, "HUD mount icon closes selection and clears highlight")
	root.size = Vector2i(800,720)
	root.content_scale_size = Vector2i(800,720)
	for frame: int in 8: await process_frame
	main._fit_hud_action_buttons()
	for frame: int in 4: await process_frame
	expect(mount_button.get_global_rect().end.x <= main.game_view.size.x - 96 + 1,
		"mount shortcut stays reachable in a smaller HUD")
	var disconnect_button := main.get_node("%DisconnectButton") as Button
	expect(disconnect_button.get_global_rect().end.x <= main.game_view.size.x - 96 + 1,
		"adding a mount shortcut keeps the existing HUD icons on screen")
	expect((main.get_node("%WalkButton") as Control).get_global_rect().position.x >= 0,
		"the first HUD icon stays on screen at smaller widths")
	main.picked_actor = 2
	main._on_world_gui_input(click)
	expect(not menu.visible and main._interaction_mode == "trade", "right-clicking another player still cycles world actions")
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	if had_settings:
		FileAccess.open(path, FileAccess.WRITE).store_buffer(original)
	else:
		DirAccess.remove_absolute(path)
	print("MOUNT_BANNER_SETTINGS_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
