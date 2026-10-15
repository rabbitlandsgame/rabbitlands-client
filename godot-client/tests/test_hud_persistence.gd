extends SceneTree
## Guards the HUD settings that survive a session.
##
## The minimap's position and scale were persisted but its visibility was not,
## so every session began with the map hidden and Alt+M was the only way back.
## These assertions run two fresh scene instances so the setting is proved to
## travel through the settings file rather than through a live variable.

const SETTINGS_PATH := "user://eloria_hud.cfg"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var saved: Dictionary = _read_settings()
	var original_max_fps: int = Engine.max_fps
	# The look's variables outrank the settings file (LookProfile), and this
	# proves the file: a run with ELORIA_LOOK=0 set would read the variable back.
	var saved_variables := {}
	for variable: String in [LookProfile.ENABLE_VARIABLE, LookProfile.QUALITY_VARIABLE]:
		saved_variables[variable] = OS.get_environment(variable)
		OS.unset_environment(variable)
	# The first instance is a new installation: no settings file at all. The
	# saved copy is written back at the end.
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))

	var first: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(first)
	await process_frame
	var first_minimap: Control = first.get_node("GameView/MinimapFrame") as Control
	_expect(not first_minimap.visible, "the minimap ships hidden")
	var default_border_steps: Array = first.get("MINIMAP_BORDER_STEPS") as Array
	_expect(str(first.get("_minimap_shape")) == "round"
		and str(first.get("_minimap_orientation")) == "viewport_up"
		and is_equal_approx(float(first.get("_minimap_border")),
			float(default_border_steps[0])),
		"a new installation shows a round, minimally bordered, viewport-aligned minimap")
	first.call("_toggle_minimap")
	_expect(first_minimap.visible and bool(first.get("_minimap_visible")),
		"showing the minimap records that it is visible")
	var stored := ConfigFile.new()
	_expect(stored.load(SETTINGS_PATH) == OK
		and bool(stored.get_value("hud", "minimap_visible", false)),
		"showing the minimap writes its visibility to the settings file")
	var first_settings: Control = first.get("settings_window") as Control
	var fps_option: OptionButton = first_settings.find_child("fps_limit", true, false) as OptionButton
	fps_option.select(fps_option.get_item_index(120))
	fps_option.item_selected.emit(fps_option.selected)
	# The painted look and the graphics quality: a new installation has the
	# look on at High, and what the player picks is what the next session reads.
	var first_look: CheckBox = first_settings.find_child("look", true, false) as CheckBox
	var first_quality: OptionButton = first_settings.find_child("quality", true, false) as OptionButton
	_expect(LookProfile.enabled() and LookProfile.quality() == LookProfile.Quality.HIGH
		and first_look.button_pressed
		and first_quality.get_selected_id() == LookProfile.Quality.HIGH,
		"a new installation has the painted look on at High quality")
	first_look.button_pressed = false
	first_quality.select(first_quality.get_item_index(LookProfile.Quality.LOW))
	first_quality.item_selected.emit(first_quality.selected)
	first.queue_free()
	await process_frame
	Engine.max_fps = 0

	# A second instance must come back with the minimap visible without the
	# player pressing Alt+M again.
	var second: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(second)
	await process_frame
	var second_settings: Control = second.get("settings_window") as Control
	var restored_fps: OptionButton = second_settings.find_child("fps_limit", true, false) as OptionButton
	_expect(Engine.max_fps == 120 and restored_fps.get_selected_id() == 120,
		"a new session applies the saved FPS limit and restores the dropdown before login")
	restored_fps.select(restored_fps.get_item_index(0))
	restored_fps.item_selected.emit(restored_fps.selected)
	# The switch lives in LookProfile for the whole process, so it is put back
	# to the defaults first: what the second session shows has to come from
	# the file.
	LookProfile.set_player_look(true)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	second.call("_load_hud_settings")
	var second_look: CheckBox = second_settings.find_child("look", true, false) as CheckBox
	var second_quality: OptionButton = second_settings.find_child("quality", true, false) as OptionButton
	_expect(not LookProfile.enabled() and LookProfile.quality() == LookProfile.Quality.LOW
		and not second_look.button_pressed
		and second_quality.get_selected_id() == LookProfile.Quality.LOW,
		"a new session reads the painted look off and Low quality back, and the window shows them")
	second_look.button_pressed = true
	second_quality.select(second_quality.get_item_index(LookProfile.Quality.MEDIUM))
	second_quality.item_selected.emit(second_quality.selected)
	var second_minimap: Control = second.get_node("GameView/MinimapFrame") as Control
	_expect(bool(second.get("_minimap_visible")),
		"a new session loads the remembered minimap visibility")
	_expect(not second_minimap.visible,
		"the minimap stays hidden while the login screen is up")
	second.call("_on_login_succeeded")
	await process_frame
	_expect(second_minimap.visible,
		"entering the world restores the remembered visible minimap")
	var map_viewport: SubViewport = second.get_node("%MapViewport")
	_expect(map_viewport.render_target_update_mode != SubViewport.UPDATE_ALWAYS,
		"restoring the minimap does not put its viewport back on continuous redraw")
	second.call("_toggle_minimap")
	_expect(not second_minimap.visible and not bool(second.get("_minimap_visible")),
		"hiding the minimap records that it is hidden")
	var rehidden := ConfigFile.new()
	_expect(rehidden.load(SETTINGS_PATH) == OK
		and not bool(rehidden.get_value("hud", "minimap_visible", true)),
		"hiding the minimap is persisted too, not just showing it")
	# The minimap's appearance is a set of choices a player makes once and
	# expects to keep: which marks are drawn, how big they are, and what shape
	# and size the window is. Each is written by the menu that changes it, so
	# they are proved through the file rather than through a live variable.
	second.call("_on_minimap_marker_type_toggled",
		(second.get("MINIMAP_MARKER_TYPES") as Array).find(&"harvest"))
	second.call("_on_minimap_marker_scale_selected", 4)
	# Shape and border are moved off their defaults, or an unwritten file
	# would pass too.
	second.call("_on_minimap_shape_selected", 0)
	second.call("_on_minimap_border_selected", 3)
	second.call("_on_minimap_orientation_selected", 0)
	var appearance := ConfigFile.new()
	var border_steps: Array = second.get("MINIMAP_BORDER_STEPS") as Array
	var marker_scales: Array = second.get("MINIMAP_MARKER_SCALES") as Array
	_expect(appearance.load(SETTINGS_PATH) == OK
		and not bool(appearance.get_value("hud", "minimap_marker_harvest", true))
		and bool(appearance.get_value("hud", "minimap_marker_player", false))
		and str(appearance.get_value("hud", "minimap_shape", "")) == "square"
		and str(appearance.get_value("hud", "minimap_orientation", "")) == "north_up"
		and is_equal_approx(float(appearance.get_value(
			"hud", "minimap_marker_scale", 0.0)), float(marker_scales[-1]))
		and is_equal_approx(float(appearance.get_value(
			"hud", "minimap_border", 0.0)), float(border_steps[-1])),
		"the minimap's marker and appearance choices are written to the file")
	second.queue_free()
	await process_frame
	Engine.max_fps = 144

	var third: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(third)
	await process_frame
	var third_settings: Control = third.get("settings_window") as Control
	var unlimited_fps: OptionButton = third_settings.find_child("fps_limit", true, false) as OptionButton
	_expect(Engine.max_fps == 0 and unlimited_fps.get_selected_id() == 0,
		"Unlimited also survives a new session and removes the engine frame cap")
	_expect(LookProfile.enabled() and LookProfile.quality() == LookProfile.Quality.MEDIUM,
		"switching the look back on at Medium survives a new session too")
	# A file from an older client has neither key; a hand-edited one may hold
	# anything. Both leave the defaults.
	for written: Array in [[null, null], ["maybe", "ultra"], [0, 2]]:
		var edited := ConfigFile.new()
		edited.load(SETTINGS_PATH)
		for pair: Array in [["look", written[0]], ["quality", written[1]]]:
			if pair[1] == null:
				if edited.has_section_key("graphics", str(pair[0])):
					edited.erase_section_key("graphics", str(pair[0]))
			else:
				edited.set_value("graphics", str(pair[0]), pair[1])
		edited.save(SETTINGS_PATH)
		LookProfile.set_player_look(false)
		LookProfile.set_player_quality(LookProfile.Quality.LOW)
		third.call("_load_hud_settings")
		_expect(LookProfile.enabled() and LookProfile.quality() == LookProfile.Quality.HIGH,
			"a settings file holding %s falls back to the look on at High" % str(written))
	var third_overlay: Control = third.get("minimap_marker_overlay") as Control
	_expect(str(third.get("_minimap_shape")) == "square"
		and str(third.get("_minimap_orientation")) == "north_up"
		and is_equal_approx(float(third.get("_minimap_marker_scale")),
			float(marker_scales[-1]))
		and is_equal_approx(float(third.get("_minimap_border")),
			float(border_steps[-1])),
		"a new session comes back with the remembered minimap appearance")
	_expect(third_overlay != null
		and not bool(third_overlay.call("type_enabled", &"harvest"))
		and bool(third_overlay.call("type_enabled", &"creature")),
		"the remembered marker switches reach the overlay that draws them")
	var third_menu: PopupMenu = third.get("_minimap_marker_type_menu") as PopupMenu
	var harvest_index: int = (third.get("MINIMAP_MARKER_TYPES") as Array).find(&"harvest")
	_expect(third_menu != null and not third_menu.is_item_checked(harvest_index)
		and third_menu.is_item_checked(0),
		"the menu opens ticked to what was remembered rather than to the defaults")
	third.queue_free()
	await process_frame

	_restore_settings(saved)
	Engine.max_fps = original_max_fps
	for variable: String in saved_variables:
		if str(saved_variables[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(saved_variables[variable]))
	print("hud persistence tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _read_settings() -> Dictionary:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return {}
	var values: Dictionary = {}
	for section: String in config.get_sections():
		for key: String in config.get_section_keys(section):
			values[section + "/" + key] = config.get_value(section, key)
	return values

func _restore_settings(values: Dictionary) -> void:
	var config := ConfigFile.new()
	for path: String in values:
		config.set_value(path.get_slice("/", 0), path.get_slice("/", 1), values[path])
	config.save(SETTINGS_PATH)

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
