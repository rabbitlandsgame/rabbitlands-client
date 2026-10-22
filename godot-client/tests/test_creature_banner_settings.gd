extends "res://tests/test_creature_banner_overlap.gd"
## Exercise settings signals, mode changes, actor refreshes and saved profiles.
const Options := preload("res://src/ui/creature_banner_settings.gd")
const ARTIFACTS := "res://test-artifacts/creature-banner-settings"

func toggle(mode: String, option: String, value: bool) -> void:
	var box := main.settings_window.panel.find_child(Options.setting_key(mode, option), true, false) as CheckBox
	expect(box != null, "Banners includes %s %s" % [mode, option])
	if box != null:
		box.button_pressed = value

func expect_parts(actor: ReplicatedActor3D, names: bool, bar: bool,
		values: bool, statuses: bool, background: bool, message: String) -> void:
	for part: Array in [["Nameplate", names], ["HealthBarBackground", bar],
			["HealthBarFill", bar], ["HealthNumbers", values], ["StatusIcons", statuses],
			["OverheadBackground", background]]:
		expect(actor.get_node(part[0]).visible == part[1], message + ": " + str(part[0]))

func _run() -> void:
	root.size = Vector2i(1280, 720)
	state = root.get_node("AppState")
	state.set("local_actor_id", 1)
	var originals := {}
	var settings_path := "user://eloria_hud.cfg"
	originals[settings_path] = FileAccess.get_file_as_bytes(settings_path) if FileAccess.file_exists(settings_path) else null
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var presets_path: String = main.hud_workspace.preferences_path
	originals[presets_path] = FileAccess.get_file_as_bytes(presets_path) if FileAccess.file_exists(presets_path) else null
	main._creature_banner_options = Options.defaults()
	main._nameplates_enabled = true
	main._banner_option_boxes.instance_mode.set_pressed_no_signal(false)
	main._banner_option_boxes.show_names.set_pressed_no_signal(true)
	main.login_panel.hide()
	main.game_view.show()
	var creature := make_actor(901, ReplicatedActor3D.CREATURE_ACTOR_KIND)
	var invasion := make_actor(902, ReplicatedActor3D.CREATURE_ACTOR_KIND, ReplicatedActor3D.INVASION_NAME_COLOUR)
	var player := make_actor(903, 1)
	for actor: ReplicatedActor3D in [creature, invasion, player]:
		actor.set_status_effects(["poison", "shield"])
	main._apply_banner_options()
	expect_parts(creature, true, true, true, true, true, "normal defaults")
	for mode: String in Options.MODES:
		for option: String in Options.OPTION_LABELS:
			var box := main.settings_window.panel.find_child(Options.setting_key(mode, option), true, false) as CheckBox
			expect(box != null and main.settings_window.tab_index_for(box) == main.settings_window.pages.keys().find("Banners"),
				"both profiles live on the Banners tab")
	toggle("normal", "health_bar", false)
	toggle("normal", "health_numbers", false)
	toggle("normal", "status_icons", false)
	toggle("normal", "background", false)
	for actor: ReplicatedActor3D in [creature, invasion]:
		expect_parts(actor, true, false, false, false, false, "name only, including invasion creatures")
	expect_parts(player, true, true, true, true, true, "creature choices do not alter player contents")
	toggle("normal", "names", false)
	toggle("normal", "health_bar", true)
	expect_parts(creature, false, true, false, false, false, "health bar only")
	var quad := creature.get_node("HealthBarBackground").mesh as QuadMesh
	expect(quad.center_offset.is_zero_approx(), "a health-only bar is centred over the creature")
	creature.apply_vitals(7, 10)
	expect_parts(creature, false, true, false, false, false, "health updates preserve the chosen contents")
	toggle("normal", "health_bar", false)
	toggle("normal", "health_numbers", true)
	expect_parts(creature, false, false, true, false, false, "health values only")
	expect((creature.get_node("HealthNumbers") as Label3D).offset.is_zero_approx(),
		"health values are centred without a missing bar or name")
	toggle("normal", "status_icons", true)
	toggle("normal", "background", true)
	creature.set_overhead_fade(0.5)
	expect_parts(creature, false, false, true, true, true, "selected contents share the distance fade")
	expect(is_equal_approx(creature.get_node("HealthNumbers").modulate.a, 0.5), "health values fade")
	creature.set_drawn(false)
	creature.set_drawn(true)
	expect_parts(creature, false, false, true, true, true, "returning to draw range preserves contents")
	toggle("normal", "visible", false)
	expect_parts(creature, false, false, false, false, false, "master switch hides every banner part")
	toggle("normal", "visible", true)
	expect_parts(creature, false, false, true, true, true, "master switch restores the selected parts")
	main._banner_option_boxes.instance_mode.button_pressed = true
	expect_parts(creature, false, false, false, false, false, "instance defaults preserve hidden creature banners")
	toggle("instance", "visible", true)
	toggle("instance", "names", false)
	toggle("instance", "health_numbers", false)
	toggle("instance", "status_icons", false)
	toggle("instance", "background", false)
	expect_parts(creature, false, true, false, false, false, "instance has an independent health-only choice")
	toggle("normal", "names", true)
	expect_parts(creature, false, true, false, false, false, "editing normal choices does not change instance display")
	main._banner_option_boxes.instance_mode.button_pressed = false
	expect_parts(creature, true, false, true, true, true, "leaving instance restores normal choices")
	main._banner_option_boxes.show_names.button_pressed = false
	expect(creature.get_node("Nameplate").visible and not player.get_node("Nameplate").visible,
		"creature name choices are independent of character names")
	main._apply_actor_banner_options(901, creature)
	expect_parts(creature, true, false, true, true, true, "packet refresh preserves creature preferences")
	main._nameplates_enabled = false
	main._apply_banner_options()
	expect_parts(creature, false, false, false, false, false, "the graphics master switch still hides banners")
	main._nameplates_enabled = true
	main._apply_banner_options()
	creature.apply_vitals(0, 10)
	expect_parts(creature, false, false, false, false, false, "dead creatures do not regain banners")
	creature.apply_vitals(10, 10)
	expect_parts(creature, true, false, true, true, true, "revival preserves the profile")
	var directory := ProjectSettings.globalize_path(ARTIFACTS)
	DirAccess.make_dir_recursive_absolute(directory)
	var config := ConfigFile.new()
	Options.write(config, main._creature_banner_options)
	var file := directory.path_join("preferences.cfg")
	expect(config.save(file) == OK, "profiles save to disk")
	var loaded := ConfigFile.new()
	expect(loaded.load(file) == OK and Options.read(loaded) == main._creature_banner_options,
		"all independent profile choices survive a reload")
	var defaults := Options.read(ConfigFile.new())
	expect(defaults.normal.visible and not defaults.instance.visible, "older settings receive compatible defaults")
	for actor: ReplicatedActor3D in [creature, invasion, player]:
		remove_actor(actor)
	main.settings_window.open_tab("Banners")
	for frame: int in 5:
		await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		expect(root.get_texture().get_image().save_png(directory.path_join("banners-settings.png")) == OK,
			"Banners settings preview saved")
	main.queue_free()
	await process_frame
	for path: String in originals:
		var original: Variant = originals[path]
		if original == null:
			if FileAccess.file_exists(path): DirAccess.remove_absolute(path)
		elif FileAccess.get_file_as_bytes(path) != original:
			var handle := FileAccess.open(path, FileAccess.WRITE)
			expect(handle != null, "original preferences can be restored")
			if handle != null: handle.store_buffer(original)
	print("CREATURE_BANNER_SETTINGS checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)
