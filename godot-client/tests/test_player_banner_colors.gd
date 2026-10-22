extends SceneTree
## Exercise color ownership through the actual menu, Settings and HUD presets.
const Presets := preload("res://src/ui/hud_presets.gd")
const Colors := preload("res://src/ui/banner_colors.gd")
const SETTINGS := "user://eloria_hud.cfg"
var failures := 0
var checks := 0
var main: Control

func _init() -> void: call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func item_color(item: String) -> Color:
	if item == "name": return main.overhead_player_name.get_theme_color("font_color")
	if item == "mount": return main.mount_status.status.get_theme_color("font_color")
	return main._banner_row(item.capitalize() + "Row").get_node("Number").get_theme_color("font_color")

func expect_color(item: String, color: Color, label: String) -> void:
	expect(item_color(item).is_equal_approx(color), label + " values")
	if item in ["name", "mount"]: return
	var bar: ProgressBar = main._banner_row(item.capitalize() + "Row").get_node("Bar")
	expect(bar.get_theme_stylebox("fill").bg_color.is_equal_approx(color), label + " bar")

func capture(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	for frame: int in 4: await process_frame
	await RenderingServer.frame_post_draw
	var path := "res://test-artifacts/player-banner-colors"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path))
	expect(root.get_texture().get_image().save_png(path.path_join(name)) == OK, "capture " + name)

func run() -> void:
	create_timer(60).timeout.connect(func() -> void: quit(99))
	var had_settings := FileAccess.file_exists(SETTINGS)
	var original := FileAccess.get_file_as_bytes(SETTINGS) if had_settings else PackedByteArray()
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	for frame: int in 4: await process_frame
	main.set_process(false)
	main.login_panel.hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var app := root.get_node("AppState")
	app.authenticated = true
	app.local_actor_id = 99
	app.actors = {99:{"name_colour":0}}
	app.stats = {"health":120, "max_health":150, "ether":45, "max_ether":60,
		"food":42, "action_points":28, "max_action_points":30, "carried":115, "capacity":320}
	main._sync_stats()
	var workspace: Control = main.hud_workspace
	workspace.choose_preset("classic", true)
	expect(not main._banner_option("load_bar") and not main._banner_option("load_numbers"), "load is optional by default")
	main._actor_hud_menu.character_boxes.load_bar.button_pressed = true
	main._actor_hud_menu.character_boxes.load_numbers.button_pressed = true
	expect(main._banner_row("LoadRow").visible and main._banner_row("LoadRow").get_node("Number").text == "115/320", "load uses carried weight and capacity")
	var original_resources: Dictionary = workspace.model.working.resource_colors.duplicate()
	var controls: Control = main._actor_hud_menu.color_controls
	var settings: Control = main.settings_window.panel.find_child("BannerColors", true, false)
	for item: String in Colors.LABELS:
		var color := Color.from_hsv(float(Colors.LABELS.keys().find(item)) / 7.0, 0.65, 0.9)
		controls.pickers[item].color = color
		controls.pickers[item].color_changed.emit(color)
		expect_color(item, color, "independent " + item)
		expect(settings.pickers[item].color.is_equal_approx(color), "Settings reflects menu color " + item)
	expect(workspace.model.working.resource_colors == original_resources, "independent banner edits leave resource colors unchanged")
	settings.pickers.name.color = Color("dacabc")
	settings.pickers.name.color_changed.emit(Color("dacabc"))
	expect_color("name", Color("dacabc"), "Settings can edit independent colors")
	var independent: Dictionary = workspace.model.working.banner_colors.colors.duplicate()
	app.stats.health = 20
	app.stats.carried = 240
	app.state_changed.emit(&"stats")
	expect_color("health", independent.health, "stat updates preserve custom health")
	expect(main._banner_row("LoadRow").get_node("Number").text == "240/320", "load updates from live stats")
	for item: String in Colors.RESOURCES:
		settings.matches[item].button_pressed = true
		var resource: String = Colors.RESOURCES[item]
		expect_color(item, original_resources[resource], "matching " + item)
		expect(controls.pickers[item].disabled and controls.matches[item].button_pressed, "matching disables independent picker " + item)
		var changed := Color.from_hsv(float(Colors.RESOURCES.keys().find(item)) / 6.0, 0.4, 0.75)
		workspace.change_resource_color(resource, changed)
		expect_color(item, changed, "resource changes reach linked " + item)
		settings.matches[item].button_pressed = false
		expect_color(item, independent[item], "unlink restores independent " + item)
		workspace.change_resource_color(resource, original_resources[resource])
	controls.sync_all_changed.emit(true)
	for item: String in Colors.RESOURCES:
		expect(controls.matches[item].button_pressed, "match all includes " + item)
	controls.sync_all_changed.emit(false)
	for item: String in Colors.LABELS:
		expect_color(item, independent[item], "independent all restores " + item)
	settings.matches.ether.button_pressed = true
	settings.matches.load.button_pressed = true
	var saved := Presets.new()
	saved.load_file(SETTINGS)
	expect(saved.working.banner_colors == workspace.model.working.banner_colors, "custom colors and mixed matching survive a file reload")
	var before: Dictionary = workspace.model.working.banner_colors.duplicate(true)
	workspace.open_editor()
	workspace.select_component("nameplate")
	expect(workspace.details.get_node_or_null("BannerColors") != null, "HUD editor includes per-item controls")
	workspace._detail_tabs.current_tab = 1
	workspace._detail_group = "Look"
	workspace._filter_details()
	await capture("colors-editor.png")
	workspace.change_banner_color("health", Color.CORNFLOWER_BLUE)
	workspace.undo_edit()
	expect_color("health", independent.health, "Undo restores independent health")
	workspace.redo_edit()
	expect_color("health", Color.CORNFLOWER_BLUE, "Redo restores edited health")
	workspace.cancel_edit()
	expect(workspace.model.working.banner_colors == before, "Cancel restores colors and matching together")
	workspace.choose_preset("minimal", true)
	expect(workspace.model.working.banner_colors.colors.is_empty(), "another preset has its own banner colors")
	workspace.choose_preset("classic")
	expect(workspace.model.working.banner_colors == before, "returning to a preset restores its colors and matching")
	var invalid := Colors.normalise({"colors":{"health":Color(NAN,0,0), "load":"invalid", "name":Color(2,-1,0)}, "synced":{"ether":true,"load":"yes","unknown":true}})
	expect(not invalid.colors.has("health") and not invalid.colors.has("load") and invalid.colors.name == Color(1,0,0), "invalid colors are rejected and finite colors clamped")
	expect(invalid.synced.ether and not invalid.synced.load and not invalid.synced.has("unknown"), "saved matching flags are validated")
	main.overhead_player_name.text = "Kellan"
	main.actor_resource_overlay.reparent(main.game_view)
	main.actor_resource_overlay.position = Vector2(320, 140)
	main.actor_resource_overlay.show()
	main._sync_banner_context_menu()
	main._actor_hud_menu.open_at(Vector2(490, 130), "Colors")
	await capture("colors-menu.png")
	if DisplayServer.get_name() != "headless":
		var popup: PopupPanel = controls.pickers.health.get_popup()
		popup.popup()
		await process_frame
		var escape := InputEventKey.new()
		escape.physical_keycode = KEY_ESCAPE
		escape.pressed = true
		expect(main._actor_hud_menu.handle_event(escape) and not popup.visible and main._actor_hud_menu.visible,
			"Escape closes a color picker while keeping the banner menu open")
	main._actor_hud_menu.close()
	main.settings_window.open_tab("Banners")
	await capture("colors-settings.png")
	main.settings_window.close()
	controls.reset_requested.emit()
	expect(workspace.model.working.banner_colors.colors.is_empty(), "reset removes custom overrides")
	expect_color("health", main._banner_colour("health", 20.0 / 150.0), "reset restores the original health ramp")
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	if had_settings: FileAccess.open(SETTINGS, FileAccess.WRITE).store_buffer(original)
	else: DirAccess.remove_absolute(SETTINGS)
	print("PLAYER_BANNER_COLOR_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
