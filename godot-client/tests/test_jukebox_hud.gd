extends SceneTree
## Production HUD integration, including persisted placement and shared controls.
const Presets := preload("res://src/ui/hud_presets.gd")
const PATH := "res://test-artifacts/jukebox/hud.cfg"
var failures := 0
var main: Control

func _init() -> void:
	call_deferred("_run")

func expect(value: bool, description: String) -> void:
	if not value:
		failures += 1
		push_error(description)

func frames(count := 5) -> void:
	for frame: int in count: await process_frame

func _run() -> void:
	create_timer(45).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	var saved_geometry_override := OS.get_environment("ELORIA_NO_GEOMETRY_CACHE")
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", "1")
	root.size = Vector2i(1440, 900)
	root.content_scale_size = Vector2i.ZERO
	var settings_path := "user://eloria_hud.cfg"
	var had_settings := FileAccess.file_exists(settings_path)
	var saved_settings := FileAccess.get_file_as_bytes(settings_path) if had_settings else PackedByteArray()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(PATH.get_base_dir()))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = PATH
	root.add_child(main)
	var deadline := Time.get_ticks_msec() + 20000
	while (main.hud_workspace == null or not main.hud_workspace.ready_to_layout) and Time.get_ticks_msec() < deadline:
		await process_frame
	await frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.get_node("CreationPanel").hide()
	main.game_view.show()
	await frames()
	var workspace: Control = main.hud_workspace
	var box: Node = main.audio_director.jukebox
	box.storage_path = "res://test-artifacts/jukebox/hud-music.cfg"
	main.audio_director.enabled = true
	var compact: PanelContainer = workspace.parts.jukebox
	expect(compact.jukebox == box, "The HUD player uses the production jukebox")
	for key: String in Presets.BUILT_INS:
		expect(not Presets.preset(key).parts.jukebox.enabled, "The new component preserves the saved/default " + key + " layout")
	var old := Presets.preset("heritage")
	old.parts.erase("jukebox")
	var migrated := Presets.normalise(old)
	expect(not migrated.parts.jukebox.enabled and migrated.parts.jukebox.anchor == "bottom_center", "Older HUD profiles gain a disabled player with a usable default position")
	workspace.choose_preset("heritage", true)
	workspace.open_editor()
	workspace.select_component("jukebox")
	var found := false
	for index: int in workspace.component_picker.item_count:
		if workspace.component_picker.get_item_metadata(index) == "jukebox": found = true
	expect(found, "Music player is listed in the HUD editor")
	for row: Control in workspace.details.get_children():
		if row.get_meta("option_caption", "") == "Show Music player":
			var toggle := row as CheckBox
			if toggle != null: toggle.button_pressed = true
	await frames()
	expect(workspace.model.working.parts.jukebox.enabled and compact.is_visible_in_tree(), "The HUD editor's Show Music player control enables the live component")
	box.create_playlist("HUD journey")
	box.edit_playlist("HUD journey", ["rising_moon", "home_town", "cave_theme"])
	box.choose("playlist", "HUD journey")
	await frames()
	var source_width: float = compact.source.get_theme_font("font").get_string_size(compact.source.text, HORIZONTAL_ALIGNMENT_LEFT, -1, compact.source.get_theme_font_size("font_size")).x
	expect(compact.source.size.x >= source_width and compact.source.text == "Playlist", "The compact source badge keeps its text readable")
	compact.next_button.pressed.emit()
	expect(box.current_track() == "home_town", "Next in the compact HUD controls real playback")
	compact.previous_button.pressed.emit()
	expect(box.current_track() == "rising_moon", "Previous in the compact HUD controls real playback")
	compact.pause_button.pressed.emit()
	expect(box.paused, "The compact Pause control pauses the jukebox")
	compact.expand_button.pressed.emit()
	await frames()
	var window: AcceptDialog = main.settings_window.get_node_or_null("JukeboxWindow")
	expect(window != null and window.visible and window.jukebox == box, "Expand opens the full live jukebox")
	window.transport.pause_button.pressed.emit()
	expect(not box.paused, "The full menu resumes the same player")
	compact.volume.value = 0.23
	expect(is_equal_approx(float(main.audio_director.category_volumes.music), 0.23) and is_equal_approx(float(window.transport.volume.value), 0.23), "Music volume stays synchronized between the two modes and the audio mixer")
	var settings := ConfigFile.new()
	settings.load(settings_path)
	expect(is_equal_approx(float(settings.get_value("audio", "music_volume", -1.0)), 0.23), "HUD music volume persists through the existing audio settings")
	compact.shuffle_button.pressed.emit()
	expect(box.shuffle, "The compact shuffle control changes playlist order")
	compact.repeat_button.pressed.emit()
	expect(box.repeat_mode == "one", "The compact repeat control cycles repeat modes")
	window.hide()
	await frames()
	var origin: Vector2 = compact.get_global_rect().get_center()
	var before: Vector2 = compact.position
	var track_before: String = box.current_track()
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = origin
	workspace.handle_input(click)
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.position = origin + Vector2(90, -85)
	workspace.handle_input(motion)
	click.pressed = false
	click.position = motion.position
	workspace.handle_input(click)
	await frames()
	expect(compact.position.distance_to(before) > 40 and box.current_track() == track_before, "HUD editing moves the component without activating playback buttons")
	workspace.change_part("jukebox", "scale", 0.85)
	workspace.change_part("jukebox", "dimensions", Vector2(600, 68))
	workspace.commit_and_close()
	await frames()
	var saved := Presets.new()
	saved.load_file(PATH)
	expect(saved.working.parts.jukebox.enabled and saved.working.parts.jukebox.position.distance_to(workspace.model.working.parts.jukebox.position) < 0.001, "Saving the HUD preserves the player and its chosen position")
	expect(is_equal_approx(float(saved.working.parts.jukebox.scale), 0.85) and saved.working.parts.jukebox.dimensions == Vector2(600, 68), "Music-player size and scale survive the saved HUD profile")
	workspace.open_editor()
	workspace.change_part("jukebox", "enabled", false)
	workspace.cancel_edit()
	expect(compact.visible and workspace.model.working.parts.jukebox.enabled, "Cancel restores the compact player")
	workspace.change_part("jukebox", "enabled", false)
	box.hud_player_requested.emit()
	expect(workspace.model.working.parts.jukebox.enabled, "The full menu's compact-player action enables the same HUD component")
	if DisplayServer.get_name() != "headless":
		await _capture(workspace, compact)
	main.queue_free()
	await frames()
	if had_settings:
		var file := FileAccess.open(settings_path, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(settings_path))
	if saved_geometry_override.is_empty(): OS.unset_environment("ELORIA_NO_GEOMETRY_CACHE")
	else: OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", saved_geometry_override)
	print("Jukebox HUD integration: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)

func _capture(workspace: Control, compact: Control) -> void:
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty(): output = ProjectSettings.globalize_path("res://test-artifacts/jukebox")
	DirAccess.make_dir_recursive_absolute(output)
	await frames()
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join("moonlit-slate-hud-gameplay.png"))
	workspace.open_editor()
	workspace.select_component("jukebox")
	workspace.panel.position = Vector2(20, 20)
	await frames()
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join("moonlit-slate-hud-editor.png"))
	workspace.cancel_edit()
