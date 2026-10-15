extends SceneTree

const Backdrop := preload("res://src/ui/login_backdrop.gd")
const TEMP_SETTINGS := "user://test_login_backdrop.cfg"
var failures := 0
var checks := 0


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)


func _run() -> void:
	root.size = Vector2i(1280, 720)
	var player_path: String = Backdrop.SETTINGS_PATH
	var had_player_settings := FileAccess.file_exists(player_path)
	var player_settings := FileAccess.get_file_as_bytes(player_path) if had_player_settings else PackedByteArray()
	# A separate file makes persistence assertions safe for the player's settings.
	var config := ConfigFile.new()
	config.set_value("connection", "host", "keep-this-host")
	config.set_value("start_screen", "backdrop", "unknown-scene")
	config.save(TEMP_SETTINGS)
	var backdrop := Backdrop.new()
	backdrop.settings_path = TEMP_SETTINGS
	root.add_child(backdrop)
	await process_frame
	_expect(backdrop.selected_id == "oldcraft_landfall", "unknown saved scene falls back to Landfall")
	_expect(backdrop.animation_enabled and backdrop.animation_toggle.button_pressed, "motion is enabled by default")
	_expect(backdrop.selector.item_count == 6, "all six scenes are available")
	_expect(backdrop.video.stream == null, "an inactive screen has no decoder")
	backdrop.set_active(true)
	await process_frame
	_expect(backdrop.video.is_playing() and backdrop.video.loop, "the active scene loops")
	for index: int in Backdrop.BACKDROPS.size():
		backdrop.selector.item_selected.emit(index)
		await process_frame
		var entry: Dictionary = Backdrop.BACKDROPS[index]
		_expect(backdrop.selected_id == entry.id and backdrop.selector.selected == index,
			"picker selects " + entry.id)
		_expect(backdrop.poster.texture != null, "still fallback exists for " + entry.id)
		_expect(backdrop.video.is_playing() and backdrop.video.stream.file.ends_with(entry.file + ".ogv"),
			"the selected scene is the only active video: " + entry.id)
		config.load(TEMP_SETTINGS)
		_expect(config.get_value("start_screen", "backdrop") == entry.id, "choice is saved")
		_expect(config.get_value("connection", "host") == "keep-this-host", "other settings are preserved")
	backdrop.select_backdrop("invalid")
	_expect(backdrop.selected_id == "amethyst", "invalid selection leaves the current choice intact")
	backdrop.animation_toggle.button_pressed = false
	_expect(backdrop.video.stream == null and not backdrop.video.visible and backdrop.poster.texture != null,
		"the Animate switch explicitly selects the still and releases the decoder")
	config.load(TEMP_SETTINGS)
	_expect(config.get_value("start_screen", "animated") == false, "motion preference is saved")
	backdrop.select_backdrop("whitehorn")
	_expect(backdrop.video.stream == null and backdrop.poster.texture != null, "changing a scene preserves the motion preference")
	backdrop.select_backdrop("amethyst")
	backdrop.animation_toggle.button_pressed = true
	_expect(backdrop.video.is_playing(), "the Animate switch resumes animation")
	backdrop.set_active(false)
	_expect(not backdrop.visible and backdrop.video.stream == null, "leaving entry releases the decoder")
	backdrop.set_active(true)
	_expect(backdrop.video.is_playing(), "returning to entry restarts the chosen loop")
	backdrop.size = Vector2(1600, 700)
	backdrop._fit_video()
	_expect(backdrop.video.size.x == 1600 and backdrop.video.size.y == 900 and backdrop.video.position.y == -100,
		"wide viewport uses a centered cover crop")
	backdrop.size = Vector2(1000, 900)
	backdrop._fit_video()
	_expect(backdrop.video.size == Vector2(1600, 900) and backdrop.video.position.x == -300,
		"tall viewport uses a centered cover crop")
	backdrop.set_animation_enabled(false)
	backdrop.queue_free()
	await process_frame
	var restored := Backdrop.new()
	restored.settings_path = TEMP_SETTINGS
	root.add_child(restored)
	_expect(restored.selected_id == "amethyst" and restored.selector.selected == 5,
		"a new screen restores the saved choice")
	restored.set_active(true)
	_expect(not restored.animation_enabled and not restored.animation_toggle.button_pressed and restored.video.stream == null,
		"a new screen restores the saved still preference")
	restored.queue_free()
	await process_frame
	config.load(TEMP_SETTINGS)
	config.set_value("start_screen", "backdrop", "oldcraft_waygate")
	config.set_value("start_screen", "animated", true)
	config.save(TEMP_SETTINGS)
	var migrated := Backdrop.new()
	migrated.settings_path = TEMP_SETTINGS
	root.add_child(migrated)
	config.load(TEMP_SETTINGS)
	_expect(migrated.selected_id == "oldcraft_landfall" and config.get_value("start_screen", "backdrop") == "oldcraft_landfall",
		"the old Waygate preference migrates to Landfall")
	_expect(config.get_value("connection", "host") == "keep-this-host", "migration preserves other settings")
	migrated.queue_free()
	await process_frame

	# Verify the actual client ties all overlays and playback to entry visibility.
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var integrated: Control = main.get("start_screen_backdrop")
	integrated.settings_path = TEMP_SETTINGS
	integrated.set_animation_enabled(true)
	_expect((main.get_node("LoginBackground") as TextureRect).texture != null,
		"the Landfall fallback loads before or after an editor import")
	_expect(integrated.get_parent() == main.get_node("LoginBackground"), "scenery stays behind the login")
	main.call("_set_login_screen_visible", false)
	_expect(not integrated.visible and integrated.video.stream == null, "client leaves entry without background playback")
	main.call("_set_login_screen_visible", true)
	(main.get_node("LoginPanel") as Control).hide()
	_expect(not integrated.visible and integrated.video.stream == null, "direct card hide also stops animation")
	(main.get_node("LoginPanel") as Control).show()
	_expect(integrated.visible and integrated.video.is_playing(), "direct card show resumes animation")
	if not LookProfile.quality_forced():
		var saved_quality := LookProfile.player_quality()
		for level: int in 3:
			LookProfile.set_player_quality(level)
			main.call("_apply_login_backdrop_quality")
			_expect(integrated.video.is_playing(),
				"entry video plays at graphics quality %d, including Low" % level)
		LookProfile.set_player_quality(saved_quality)
		main.call("_apply_login_backdrop_quality")
	_expect(not integrated.selector.get_global_rect().intersects((main.get_node("LoginPanel") as Control).get_global_rect()),
		"scene picker does not overlap the right-side login")
	var artifact_dir := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not artifact_dir.is_empty():
		DirAccess.make_dir_recursive_absolute(artifact_dir)
		for entry: Dictionary in Backdrop.BACKDROPS:
			var id: String = entry.id
			integrated.select_backdrop(id)
			await create_timer(0.2).timeout
			RenderingServer.force_draw(false)
			var before := root.get_texture().get_image()
			await create_timer(0.9).timeout
			_expect(integrated.video.stream_position > 0.5, "rendered decoder advances: " + id)
			RenderingServer.force_draw(false)
			var after := root.get_texture().get_image()
			var change := _background_change(before, after)
			_expect(change > 0.2, "visible scenery changes at %s quality: %s (%.3f)" % [LookProfile.quality_name(LookProfile.quality()), id, change])
			after.save_png(artifact_dir.path_join(id + ".png"))
			print("entry motion ", id, " quality=", LookProfile.quality_name(LookProfile.quality()), " mean_pixel_change=", change)
		integrated.selector.show_popup()
		await process_frame
		RenderingServer.force_draw(false)
		root.get_texture().get_image().save_png(artifact_dir.path_join("picker.png"))
	integrated.selector.get_popup().hide()
	main.call("_set_login_screen_visible", false)
	main.queue_free()
	for frame: int in 5:
		await process_frame
	DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP_SETTINGS))
	if had_player_settings:
		var file := FileAccess.open(player_path, FileAccess.WRITE)
		file.store_buffer(player_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(player_path))
	print("login backdrops: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)


func _background_change(before: Image, after: Image) -> float:
	# Exclude the form and picker so cursor blinking cannot pass a motion check.
	var region := Rect2i(0, 0, int(before.get_width() * 0.60), before.get_height())
	var first := before.get_region(region)
	var last := after.get_region(region)
	first.resize(320, 180)
	last.resize(320, 180)
	var a := first.get_data()
	var b := last.get_data()
	var difference := 0.0
	for index: int in a.size():
		difference += absi(int(a[index]) - int(b[index]))
	return difference / float(a.size())
