extends SceneTree
## Guards the tabbed settings window and the key-rebinding UI.
##
## The client had one flat panel and 26 fixed input actions that could not be
## rebound at all. Everything here is about this machine and this screen: the
## gameplay tab sends the server's own commands rather than deciding anything,
## and nothing else leaves the client.

const SETTINGS_PATH := "user://eloria_hud.cfg"
const Settings := preload("res://src/ui/settings_window.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	# Every switch below is saved to the player's own settings file; it is
	# copied here and put back at the end.
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings \
		else PackedByteArray()
	var saved_look := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var saved_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var window: Control = main.get("settings_window") as Control
	var panel: PanelContainer = window.get("panel") as PanelContainer
	var resource_rail: Control = main.get_node("GameView/ResourceHud") as Control
	await process_frame

	_expect(not panel.visible, "the settings window starts closed")
	_expect(window.get("_cache_size_thread") == null,
		"a closed settings window does not inventory disk caches during login")
	main.call("_on_more_settings_pressed")
	await process_frame
	await _wait_cache_size(window)
	_expect(panel.visible, "the settings button opens it")
	_expect((window.call("tab_titles") as Array)
			== ["HUD", "Chat", "Text colors", "Minimap", "Banners", "Graphics", "Camera", "Audio", "Inventory", "Spells", "Gameplay", "Controls"],
		"it is tabbed: %s" % str(window.call("tab_titles")))
	var rect: Rect2 = panel.get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 and rect.end.y <= 720.0
		and not rect.intersects(resource_rail.get_global_rect()),
		"it fits 1280x720 clear of the resource rail: %s" % rect)
	_test_fps_limit(main, window)
	_test_vsync_mode(main, window)
	_test_window_mode(main, window)
	var emblems := preload("res://src/actors/cape_emblems.gd")
	var cape_toggle := panel.find_child("cape_emblems", true, false) as CheckBox
	_expect(cape_toggle != null, "Graphics has a cape emblem preference")
	if cape_toggle != null:
		cape_toggle.button_pressed = false
		await process_frame
		var cape_settings := ConfigFile.new()
		cape_settings.load(SETTINGS_PATH)
		_expect(not emblems.enabled and not bool(cape_settings.get_value(
			"graphics", "cape_emblems", true)), "the emblem preference applies and saves")
		emblems.set_enabled(true)
		main.call("_load_hud_settings")
		_expect(not emblems.enabled and not cape_toggle.button_pressed,
			"the saved emblem preference restores")
		cape_toggle.button_pressed = true
	await _test_look_and_quality(main, window, panel, resource_rail)
	await _test_unified_settings(main, window, panel)

	# The map cache row. It is the only setting in this window that spends the
	# player's disk, so it carries three controls rather than one: the switch,
	# what the cache is using, and a way to be rid of it. All three are checked
	# because a row that silently lost its button would look fine.
	var cache_toggle: CheckBox = (window.get("panel") as Node).find_child("map_cache", true, false) as CheckBox
	var cache_size: Label = (window.get("panel") as Node).find_child("MapCacheSize", true, false) as Label
	var cache_clear: Button = (window.get("panel") as Node).find_child("map_cache_clear", true, false) as Button
	_expect(cache_toggle != null and cache_size != null and cache_clear != null,
		"the graphics tab carries a map cache switch, a size and a clear button")
	if cache_toggle != null and cache_size != null and cache_clear != null:
		_expect(cache_toggle.button_pressed == MapSceneCache.is_enabled(),
			"the switch opens showing what the client actually has")
		_expect(not cache_size.text.is_empty(),
			"the row says what the cache is using: %s" % cache_size.text)
		# Through the signal a click sends, not by calling the handler.
		cache_toggle.button_pressed = false
		await process_frame
		_expect(not MapSceneCache.is_enabled(),
			"turning it off turns the cache off")
		cache_toggle.button_pressed = true
		await process_frame
		_expect(MapSceneCache.is_enabled(), "and back on")
		cache_clear.pressed.emit()
		await _wait_cache_size(window)
		_expect(MapSceneCache.total_bytes() == 0
				and cache_size.text.begins_with("empty"),
			"clearing empties it and says so: %s" % cache_size.text)

	# Every bindable action exists, so no row can be dead.
	for group: Variant in window.get("BINDABLE"):
		for action: Variant in (window.get("BINDABLE") as Dictionary)[group]:
			_expect(InputMap.has_action(str(action)),
				"%s is a real action" % str(action))

	# Rebinding, through the same path a key press takes.
	var original: Array[InputEvent] = InputMap.action_get_events("toggle_sit")
	window.call("begin_capture", "toggle_sit")
	_expect(str(window.get("capturing")) == "toggle_sit",
		"the window is waiting for a key")
	var pressed := InputEventKey.new()
	pressed.pressed = true
	pressed.physical_keycode = KEY_F9
	pressed.shift_pressed = true
	main.call("_unhandled_input", pressed)
	await process_frame
	_expect(str(window.get("capturing")).is_empty(),
		"the capture ends when a key arrives")
	var rebound: Array[InputEvent] = InputMap.action_get_events("toggle_sit")
	_expect(rebound.size() == 1
		and (rebound[0] as InputEventKey).physical_keycode == KEY_F9
		and (rebound[0] as InputEventKey).shift_pressed,
		"the action now answers the key that was pressed, modifiers included")
	var stored: Dictionary = window.call("stored_bindings") as Dictionary
	_expect(str(stored.get("toggle_sit", "")) == "Shift+F9",
		"the binding is stored as text a settings file can hold: %s"
			% str(stored.get("toggle_sit", "")))

	# Escape keeps what was there.
	window.call("begin_capture", "toggle_sit")
	var escape := InputEventKey.new()
	escape.pressed = true
	escape.physical_keycode = KEY_ESCAPE
	main.call("_unhandled_input", escape)
	await process_frame
	_expect((InputMap.action_get_events("toggle_sit")[0] as InputEventKey
			).physical_keycode == KEY_F9,
		"Escape keeps the binding rather than clearing it")

	# And a stored set comes back.
	InputMap.action_erase_events("toggle_sit")
	InputMap.action_add_event("toggle_sit", original[0] if not original.is_empty()
		else InputEventKey.new())
	window.call("restore_bindings", {"toggle_sit": "Ctrl+F8"})
	var restored: InputEventKey = InputMap.action_get_events(
		"toggle_sit")[0] as InputEventKey
	_expect(restored.physical_keycode == KEY_F8 and restored.ctrl_pressed
		and not restored.shift_pressed,
		"a stored binding is read back exactly")
	_expect(int(window.call("restore_bindings", {"not_an_action": "F1"})) == 0,
		"a stored binding for an action that no longer exists is skipped")
	# A settings file an older build wrote could hold something this build
	# cannot read. That must leave the action alone, not unbind it.
	window.call("restore_bindings", {"toggle_sit": "", "toggle_map": "nonsense"})
	_expect(not InputMap.action_get_events("toggle_sit").is_empty()
		and not InputMap.action_get_events("toggle_map").is_empty(),
		"an unreadable stored binding leaves the action exactly as it was")

	# The spell quick slots moved from Shift+number to Alt+number. A settings
	# file records every bound action, not only chosen ones, so restoring a
	# stored Shift+1 would hand the old default back to somebody who never
	# picked it. It is dropped; a binding that is not the old default stands.
	_expect(int(window.call("restore_bindings", {"quick_spell_1": "Shift+1"})) == 0,
		"the superseded spell-slot default is not restored")
	var spell_slot: InputEventKey = InputMap.action_get_events(
		"quick_spell_1")[0] as InputEventKey
	_expect(spell_slot.alt_pressed and not spell_slot.shift_pressed
			and spell_slot.physical_keycode == KEY_1,
		"quick_spell_1 keeps the current Alt+1 default")
	window.call("restore_bindings", {"quick_spell_1": "Ctrl+1"})
	spell_slot = InputMap.action_get_events("quick_spell_1")[0] as InputEventKey
	_expect(spell_slot.ctrl_pressed and not spell_slot.alt_pressed,
		"a spell slot the player actually rebound is still restored")
	InputMap.action_erase_events("quick_spell_1")
	var alt_one := InputEventKey.new()
	alt_one.physical_keycode = KEY_1
	alt_one.alt_pressed = true
	InputMap.action_add_event("quick_spell_1", alt_one)

	# The presentation switches actually change what is drawn.
	var effects_before: int = (main.get("world_effects") as Array).size()
	main.call("_on_client_setting_changed", "Graphics", "particles", false)
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	app_state.call("_on_packet", 51, _hex(
		"5b00020004000000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	main.call("_sync_world")
	await process_frame
	app_state.call("_on_packet", 79, PackedByteArray([17, 0x5b, 0]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() == effects_before,
		"turning effects off stops them being drawn at all")
	main.call("_on_client_setting_changed", "Graphics", "particles", true)
	app_state.call("_on_packet", 79, PackedByteArray([17, 0x5b, 0]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() > effects_before,
		"and turning them back on restores them")

	main.call("_on_client_setting_changed", "Camera", "rotation_sensitivity", 0.5)
	_expect(is_equal_approx(
		float((main.get("camera_rig") as Node).get("rotation_sensitivity")), 0.5),
		"a camera slider reaches the camera")

	# Put the key back and save, so the next suite starts where this one did.
	InputMap.action_erase_events("toggle_sit")
	for event: InputEvent in original:
		InputMap.action_add_event("toggle_sit", event)
	main.call("_save_hud_settings")

	# Cancel closes it like every other window.
	var cancel: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	cancel.pressed = true
	main.call("_unhandled_input", cancel)
	await process_frame
	_expect(not panel.visible, "cancel closes the settings window")

	print("settings window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	for pair: Array in [[LookProfile.ENABLE_VARIABLE, saved_look],
			[LookProfile.QUALITY_VARIABLE, saved_quality]]:
		if str(pair[1]).is_empty():
			OS.unset_environment(str(pair[0]))
		else:
			OS.set_environment(str(pair[0]), str(pair[1]))
	quit(failures)

## The painted look's switch and the graphics quality: both on the graphics
## tab, opening on what the client has, applied and saved the moment they
## change, and greyed out (still showing the player's own choice) while the
## environment variable decides for the session.
func _test_look_and_quality(main: Control, window: Control, panel: PanelContainer,
		resource_rail: Control) -> void:
	var look: OptionButton = (window.get("panel") as Node).find_child("look", true, false) as OptionButton
	var quality: OptionButton = (window.get("panel") as Node).find_child("quality", true, false) as OptionButton
	if not _expect(look != null and quality != null,
			"the graphics tab offers the painted look and the graphics quality"):
		return
	var tabs: TabContainer = window.get("tabs") as TabContainer
	tabs.current_tab = window.call("tab_index_for", look)
	await process_frame
	var rect: Rect2 = panel.get_global_rect()
	_expect(tabs.current_tab == int(window.call("tab_index_for", look))
		and rect.end.y <= 720.0 and not rect.intersects(resource_rail.get_global_rect()),
		"the graphics tab with its two new rows still fits 1280x720: %s" % rect)
	_expect(quality.item_count == 3 and quality.get_item_text(0) == "Low"
		and quality.get_item_text(1) == "Medium" and quality.get_item_text(2) == "High"
		and quality.get_item_id(0) == LookProfile.Quality.LOW
		and quality.get_item_id(2) == LookProfile.Quality.HIGH,
		"the quality reads Low, Medium, High, each its LookProfile.Quality")
	_expect(look.get_selected_id() == LookProfile.player_mode()
		and quality.get_selected_id() == LookProfile.player_quality()
		and not look.disabled and not quality.disabled,
		"both open showing what the client has")
	var original_look := LookProfile.player_mode()
	var original_quality := LookProfile.player_quality()
	var path: String = str(main.get("SETTINGS_PATH"))

	var stored := ConfigFile.new()
	_expect(look.item_count == 3 and look.get_item_text(0) == "Original"
		and look.get_item_text(1) == "Painted ground" and look.get_item_text(2) == "Full painted",
		"appearance offers Original, Painted ground and Full painted")
	for mode: int in [LookProfile.Mode.ORIGINAL, LookProfile.Mode.FULL_PAINTED,
			LookProfile.Mode.PAINTED_GROUND]:
		look.select(look.get_item_index(mode))
		look.item_selected.emit(look.selected)
		await process_frame
		_expect(LookProfile.mode() == mode and stored.load(path) == OK
			and stored.get_value("graphics", "appearance", "") == LookProfile.mode_name(mode),
			"appearance applies and saves " + LookProfile.mode_name(mode))
	for level: int in [LookProfile.Quality.LOW, LookProfile.Quality.MEDIUM, LookProfile.Quality.HIGH]:
		quality.select(quality.get_item_index(level))
		quality.item_selected.emit(quality.selected)
		stored.load(path)
		_expect(LookProfile.quality() == level
			and str(stored.get_value("graphics", "quality", "")) == LookProfile.quality_name(level),
			"choosing %s applies it and saves it by name" % LookProfile.quality_name(level))

	# The variables decide for the session; the window says so and keeps the
	# player's own choice on show.
	LookProfile.set_player_look(false)
	main.call("_save_hud_settings")
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "1")
	OS.set_environment(LookProfile.QUALITY_VARIABLE, "low")
	main.call("_load_hud_settings")
	_expect(look.disabled and look.get_selected_id() == LookProfile.Mode.ORIGINAL and LookProfile.full_painted()
		and look.tooltip_text.contains(LookProfile.ENABLE_VARIABLE),
		"with ELORIA_LOOK set the switch is greyed out, says why, and shows the player's Off")
	_expect(quality.disabled and quality.get_selected_id() == LookProfile.Quality.HIGH
		and LookProfile.quality() == LookProfile.Quality.LOW
		and quality.tooltip_text.contains(LookProfile.QUALITY_VARIABLE),
		"with ELORIA_LOOK_QUALITY set the quality is greyed out and shows the player's own")
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	main.call("_load_hud_settings")
	_expect(not look.disabled and not quality.disabled and not LookProfile.enabled(),
		"unset, the player's choice decides again and both can be changed")

	main.call("_on_client_setting_changed", "Graphics", "appearance", original_look)
	main.call("_on_client_setting_changed", "Graphics", "quality", original_quality)
	main.call("_load_hud_settings")
	tabs.current_tab = 0

func _test_fps_limit(main: Control, window: Control) -> void:
	var option: OptionButton = (window.get("panel") as Node).find_child("fps_limit", true, false) as OptionButton
	if not _expect(option != null, "the graphics tab offers an FPS limit"):
		return
	var original: int = int(main.get("_fps_limit"))
	var physics_ticks: int = Engine.physics_ticks_per_second
	var time_scale: float = Engine.time_scale
	_expect(option.get_selected_id() == Engine.max_fps,
		"the dropdown shows the active frame cap")
	_expect(option.get_item_text(option.get_item_index(0)) == "Unlimited",
		"zero is presented as Unlimited")
	for limit: int in [30, 60, 75, 90, 120, 144, 165, 240, 360, 0]:
		var index: int = option.get_item_index(limit)
		if not _expect(index >= 0, "%d FPS is available" % limit):
			continue
		option.select(index)
		option.item_selected.emit(index)
		_expect(Engine.max_fps == limit,
			"selecting %d applies the frame cap immediately" % limit)
		var stored := ConfigFile.new()
		_expect(stored.load(str(main.get("SETTINGS_PATH"))) == OK
			and stored.get_value("graphics", "fps_limit", -1) == limit,
			"selecting %d saves the frame cap" % limit)
	_expect(Engine.physics_ticks_per_second == physics_ticks
		and Engine.time_scale == time_scale,
		"frame limits preserve physics timing and game speed")

	var config := ConfigFile.new()
	var path: String = str(main.get("SETTINGS_PATH"))
	config.load(path)
	for invalid: Variant in [-1, 1, 9999, "60", null, true, 60.5]:
		config.set_value("graphics", "fps_limit", invalid)
		config.save(path)
		Engine.max_fps = 60
		main.call("_load_hud_settings")
		_expect(Engine.max_fps == 0 and option.get_selected_id() == 0,
			"an invalid saved limit falls back to Unlimited: %s" % str(invalid))
	config.erase_section_key("graphics", "fps_limit")
	config.save(path)
	Engine.max_fps = 60
	main.call("_load_hud_settings")
	_expect(Engine.max_fps == 0 and option.get_selected_id() == 0,
		"settings from an older client default to Unlimited")
	main.call("_on_client_setting_changed", "Graphics", "fps_limit", original)

## The selector keeps the player's semantic choice even on headless or a
## renderer whose effective mode falls back to On. Real-backend timing is
## covered separately; this guards the actual UI, persistence and mapping.
func _test_vsync_mode(main: Control, window: Control) -> void:
	var option := (window.get("panel") as Node).find_child("vsync_mode", true, false) as OptionButton
	if not _expect(option != null, "Graphics offers vertical sync"):
		return
	var original: String = main.get("_vsync_preference")
	var frame_cap := Engine.max_fps
	var physics_ticks := Engine.physics_ticks_per_second
	var time_scale := Engine.time_scale
	_expect(option.item_count == 3, "vertical sync has three supported choices")
	var labels := ["Low latency", "On", "Off"]
	var modes := [DisplayServer.VSYNC_MAILBOX, DisplayServer.VSYNC_ENABLED, DisplayServer.VSYNC_DISABLED]
	for index: int in Settings.VSYNC_PREFERENCES.size():
		var preference: String = Settings.VSYNC_PREFERENCES[index]
		_expect(option.get_item_text(index) == labels[index]
			and option.get_item_metadata(index) == preference
			and Settings.vsync_mode(preference) == modes[index],
			"vertical sync choice maps to its actual backend mode: " + preference)
		option.select(index)
		option.item_selected.emit(index)
		var stored := ConfigFile.new()
		_expect(main.get("_vsync_preference") == preference
			and stored.load(SETTINGS_PATH) == OK
			and stored.get_value("graphics", "vsync_mode", "") == preference,
			"selecting vertical sync applies and saves: " + preference)
		main.call("_apply_vsync_mode", "off" if preference != "off" else "on")
		main.call("_load_hud_settings")
		_expect(main.get("_vsync_preference") == preference
			and option.get_item_metadata(option.selected) == preference,
			"saved vertical sync restores without overwriting explicit choice: " + preference)
	_expect(Engine.max_fps == frame_cap and Engine.physics_ticks_per_second == physics_ticks
		and Engine.time_scale == time_scale, "vertical sync preserves frame cap and game timing")
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	for invalid: Variant in [null, true, 3, 0, 1.0, "On", "adaptive", "", {}, []]:
		config.set_value("graphics", "vsync_mode", invalid)
		config.save(SETTINGS_PATH)
		main.call("_load_hud_settings")
		_expect(main.get("_vsync_preference") == "on"
			and option.get_item_metadata(option.selected) == "on"
			and Settings.vsync_mode(invalid) == DisplayServer.VSYNC_ENABLED,
			"invalid vertical sync uses On: " + str(invalid))
	config.erase_section_key("graphics", "vsync_mode")
	config.save(SETTINGS_PATH)
	main.call("_load_hud_settings")
	_expect(main.get("_vsync_preference") == "on"
		and option.get_item_metadata(option.selected) == "on",
		"new and older-client settings preserve the On default")
	var diagnostic: Dictionary = main.call("client_diagnostic_snapshot")
	_expect(diagnostic.vsync_preference == "on"
		and diagnostic.vsync_mode == DisplayServer.window_get_vsync_mode()
		and diagnostic.window_focused == main.get_window().has_focus()
		and diagnostic.low_processor_usage_mode == OS.low_processor_usage_mode
		and diagnostic.low_processor_usage_mode_sleep_usec == OS.low_processor_usage_mode_sleep_usec
		and diagnostic.max_fps == Engine.max_fps,
		"diagnostics distinguish preference, actual sync, focus and idle settings")
	main.call("_on_client_setting_changed", "Graphics", "vsync_mode", original)

func _test_window_mode(main: Control, window: Control) -> void:
	var option := (window.get("panel") as Node).find_child("window_mode", true, false) as OptionButton
	if not _expect(option != null, "Graphics offers display mode"):
		return
	var original: String = main.get("_window_mode_preference")
	var frame_cap := Engine.max_fps
	var vsync: String = main.get("_vsync_preference")
	var quality := LookProfile.player_quality()
	var labels := ["Windowed", "Fullscreen"]
	var modes := [DisplayServer.WINDOW_MODE_WINDOWED, DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN]
	_expect(option.item_count == 2, "display mode has two supported choices")
	for index: int in Settings.WINDOW_PREFERENCES.size():
		var preference: String = Settings.WINDOW_PREFERENCES[index]
		_expect(option.get_item_text(index) == labels[index]
			and option.get_item_metadata(index) == preference
			and Settings.display_mode(preference) == modes[index],
			"display choice maps to its actual backend mode: " + preference)
		option.select(index)
		option.item_selected.emit(index)
		var stored := ConfigFile.new()
		_expect(main.get("_window_mode_preference") == preference
			and not main.get("_window_mode_launch_override")
			and stored.load(SETTINGS_PATH) == OK
			and stored.get_value("graphics", "window_mode", "") == preference,
			"display selection applies immediately, supersedes launch flag and saves: " + preference)
		main.call("_apply_window_mode", "windowed" if preference == "fullscreen" else "fullscreen")
		main.call("_load_hud_settings")
		_expect(main.get("_window_mode_preference") == preference
			and option.get_item_metadata(option.selected) == preference,
			"saved display preference restores: " + preference)
	_expect(Engine.max_fps == frame_cap and main.get("_vsync_preference") == vsync
		and LookProfile.player_quality() == quality,
		"display changes preserve frame cap, vertical sync and quality")
	for arguments: PackedStringArray in [PackedStringArray(["--windowed"]), PackedStringArray(["-w"]),
			PackedStringArray(["--fullscreen"]), PackedStringArray(["-f"]),
			PackedStringArray(["--path", "game", "--fullscreen", "--resolution", "1280x720"])]:
		_expect(Settings.has_display_argument(arguments), "explicit window launch mode wins at startup: " + str(arguments))
	for arguments: PackedStringArray in [PackedStringArray(), PackedStringArray(["--headless"]),
			PackedStringArray(["--resolution", "1280x720"]), PackedStringArray(["--fullscreen-extra"])]:
		_expect(not Settings.has_display_argument(arguments), "other launch arguments retain the saved display mode: " + str(arguments))
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	for invalid: Variant in [null, true, 4, 0, 1.0, "Fullscreen", "maximized", "", {}, []]:
		config.set_value("graphics", "window_mode", invalid)
		config.save(SETTINGS_PATH)
		main.call("_load_hud_settings")
		_expect(main.get("_window_mode_preference") == "windowed"
			and option.get_item_metadata(option.selected) == "windowed"
			and Settings.display_mode(invalid) == DisplayServer.WINDOW_MODE_WINDOWED,
			"invalid display preference uses Windowed: " + str(invalid))
	config.erase_section_key("graphics", "window_mode")
	config.save(SETTINGS_PATH)
	main.call("_load_hud_settings")
	_expect(main.get("_window_mode_preference") == "windowed"
		and option.get_item_metadata(option.selected) == "windowed",
		"new and older-client settings preserve the Windowed default")
	var diagnostic: Dictionary = main.call("client_diagnostic_snapshot")
	_expect(diagnostic.window_mode_preference == "windowed"
		and diagnostic.window_mode == DisplayServer.window_get_mode()
		and diagnostic.root_viewport_size == str(root.size)
		and diagnostic.window_size == str(main.get_window().size)
		and diagnostic.viewport_size == str(main.get("main_viewport").size),
		"diagnostics report actual display mode and all presentation dimensions")
	main.call("_on_client_setting_changed", "Graphics", "window_mode", original)

## The audit guards the full preference inventory, not just the original
## graphics controls. Exercise actual UI signals and saved values as well as
## each context shortcut, so a decorative or disconnected row cannot pass.
func _test_unified_settings(main: Control, window: Control, panel: PanelContainer) -> void:
	_expect(main.get("settings_panel") == panel
		and main.get_node_or_null("GameView/SettingsPanel") == null
		and main.get_node_or_null("GameView/ActorHudMenu") == null
		and main.get_node_or_null("HudLayoutMenu") == null,
		"all settings entry points share one window; the popup shells are gone")
	var keys: Array[String] = ["UiScale", "MinimapSize", "SoundEnabled", "SoundVolume",
		"ShowThroughObstacles", "EquipmentSide", "combat_hud_pinned", "timer_stopwatch",
		"timer_start_seconds", "minimap_visible", "minimap_orientation", "minimap_shape",
		"minimap_border", "minimap_marker_scale", "minimap_zoom", "inventory_scale",
		"ground_bag_scale", "storage_docked", "selected_quantity", "spell_bar_expanded",
		"spell_bar_docked", "CastingMode", "QuickSlotCount", "RingSize", "start_backdrop",
		"start_animated", "invasion_assistant_scale", "rotation_sensitivity",
		"shadows", "particles", "nameplates"]
	_expect((window.get("panel") as Node).find_child("pan_sensitivity", true, false) == null
		and (window.get("panel") as Node).find_child("follow_player", true, false) == null,
		"camera settings cannot detach the view from the player")
	for key: String in (main.get("BANNER_OPTION_NODES") as Dictionary).values():
		keys.append(key)
	for type: StringName in main.get("MINIMAP_MARKER_TYPES"):
		keys.append("minimap_marker_" + str(type))
	for index: int in 6:
		keys.append("quantity_%d" % index)
	for kind: String in ["store", "drop"]:
		for index: int in 4:
			keys.append("protect_%s_%d" % [kind, index])
	for key: String in keys:
		var control := (window.get("panel") as Node).find_child(key, true, false) as Control
		_expect(control != null and int(window.call("tab_index_for", control)) >= 0,
			"the unified window includes " + key)
	_expect(main.get("_hud_layout_list") is ItemList and (window.get("panel") as Node).is_ancestor_of(
		main.get("_hud_layout_list")), "HUD bar order and visibility live on the HUD tab")
	_expect((window.get("panel") as Node).is_ancestor_of(main.get("_hud_skill_selector")),
		"the watched experience skill is included")
	var bindable: Array[String] = []
	for group: Array in (window.get("BINDABLE") as Dictionary).values():
		for action: String in group:
			bindable.append(action)
	# The retired camera action must not reclaim Space from gallop.
	for action: StringName in InputMap.get_actions():
		if not str(action).begins_with("ui_") and str(action) != "recenter_viewport":
			_expect(str(action) in bindable, "every client key can be rebound: " + str(action))

	window.call("close")
	main.call("_on_options_pressed")
	_expect(panel.visible and main.chat_hud.options_button.button_pressed,
		"Options opens the unified window and lights its HUD button")
	main.call("_open_actor_hud_menu", Vector2.ZERO)
	_expect((main.get("_actor_hud_menu") as Control).visible,
		"the character shortcut opens the banner context menu")
	(main.get("_actor_hud_menu") as Control).hide()
	main.get("_actor_hud_menu").settings_requested.emit()
	_expect(panel.visible and (window.get("tabs") as TabContainer).get_current_tab_control().name == "Banners",
		"the context menu can open all banner settings")
	(main.get("casting_bar") as Control).call("_dock_menu_action", 2)
	_expect((window.get("tabs") as TabContainer).get_current_tab_control().name == "Spells",
		"the spell bar shortcut opens the Spells tab")
	window.call("close")
	_expect(not main.chat_hud.options_button.button_pressed,
		"closing the window clears the HUD button")
	window.call("open_tab", "Minimap")
	var orientation := (window.get("panel") as Node).find_child("minimap_orientation", true, false) as OptionButton
	orientation.item_selected.emit(orientation.get_item_index(1))
	var marker := (window.get("panel") as Node).find_child("minimap_marker_npc", true, false) as CheckBox
	marker.button_pressed = false
	var timer := (window.get("panel") as Node).find_child("timer_start_seconds", true, false) as SpinBox
	timer.value = 123
	var protect := (window.get("panel") as Node).find_child("protect_drop_2", true, false) as CheckBox
	protect.button_pressed = true
	var quantity := (window.get("panel") as Node).find_child("quantity_4", true, false) as SpinBox
	quantity.value = 321
	_expect((window.get("panel") as Node).find_child("secure", true, false) == null,
		"settings cannot disable TLS")
	await process_frame
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	_expect(str(main.get("_minimap_orientation")) == "player_up"
		and config.get_value("hud", "minimap_orientation") == "player_up"
		and config.get_value("hud", "minimap_marker_npc") == false,
		"orientation and marker controls apply and save")
	_expect(config.get_value("hud", "timer_start_seconds") == 123
		and config.get_value("inventory", "quantities")[4] == 321
		and config.get_value("inventory", "bulk_exclusions")["drop"][2] == true
		and config.get_value("connection", "secure") == true,
		"timer, quantities and bulk protection save while TLS remains enabled")
	main.call("_load_hud_settings")
	_expect(timer.value == 123 and quantity.value == 321 and protect.button_pressed
		and orientation.get_item_metadata(orientation.selected) == "player_up",
		"reloading preferences restores every new control without changing its value")
	main.call("_on_minimap_orientation_selected", 0)
	_expect(orientation.get_item_metadata(orientation.selected) == "north_up",
		"HUD context changes immediately refresh the open settings window")
	var sensitivity := (window.get("panel") as Node).find_child("rotation_sensitivity", true, false) as HSlider
	main.call("_on_client_setting_changed", "Camera", "rotation_sensitivity", 0.4)
	window.call("open_tab", "Camera")
	_expect(is_equal_approx(sensitivity.value, 0.4),
		"camera sensitivity restores its live value instead of the built-in default")
	# Tab changes and close cancel captures; reopening must not show stale text.
	window.call("begin_capture", "toggle_sit")
	window.call("open_tab", "HUD")
	_expect(str(window.get("capturing")).is_empty()
		and not (window.get("capture_label") as Label).visible,
		"switching tabs cancels key capture")
	for dimensions: Vector2i in [Vector2i(960, 600), Vector2i(1280, 720)]:
		root.size = dimensions
		for scale: float in [1.0, 1.5, 0.5]:
			main.call("_on_ui_scale_changed", scale)
			for frame: int in 4:
				await process_frame
			window.call("open_tab", "Inventory")
			await process_frame
			var bounds := panel.get_viewport_rect()
			_expect(bounds.encloses(panel.get_global_rect())
				and panel.get_global_rect().end.x <= bounds.end.x - WindowDrag.RESERVED_RIGHT_RAIL + 1.0
				and panel.get_global_rect().end.y <= bounds.end.y - WindowDrag.RESERVED_BOTTOM_BAR + 1.0,
				"settings fit %s at UI scale %.1f: %s" % [dimensions, scale, panel.get_global_rect()])
	main.call("_on_ui_scale_changed", 1.0)
	root.size = Vector2i(1280, 720)
	window.call("open_tab", "Graphics")

func _wait_cache_size(window: Control) -> void:
	var deadline := Time.get_ticks_msec() + 5000
	while window.get("_cache_size_thread") != null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(window.get("_cache_size_thread") == null,
		"the read-only cache size inventory completes without blocking UI frames")

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
