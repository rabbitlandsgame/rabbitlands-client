extends SceneTree
## Exercises real music resources, queue transitions, persistence, rule priority,
## audio-director integration, and the controls the player uses.

const MusicPlayer := preload("res://src/audio/music_program_player.gd")
const Jukebox := preload("res://src/audio/jukebox.gd")
const JukeboxWindow := preload("res://src/ui/jukebox_window.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func expect(value: bool, description: String) -> void:
	if not value:
		failures += 1
		push_error(description)

func _run() -> void:
	root.size = Vector2i(1280, 800)
	root.content_scale_size = Vector2i.ZERO
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/audio/catalog.json"))
	var player := MusicPlayer.new()
	root.add_child(player)
	player.configure(catalog.music)
	var box := Jukebox.new()
	box.storage_path = "user://jukebox-test.cfg"
	DirAccess.remove_absolute(ProjectSettings.globalize_path(box.storage_path))
	root.add_child(box)
	box.configure(catalog.music, player)
	expect(box.mode == "game" and player.current_track().is_empty(), "Fresh settings keep game-directed music and start quietly")
	expect(box.library().size() == 39, "Every client music track is in the library")
	var files := DirAccess.get_files_at("res://assets/audio")
	for file: String in files:
		if file.begins_with("music_") and file.ends_with(".ogg"):
			expect(catalog.music.any(func(entry: Dictionary) -> bool: return entry.file == file), "The catalog includes " + file)
	expect(box.library("randommind").size() > 1, "Search finds artist credits")
	expect(box.library("town", "town_day").size() > 0, "Search combines with a game-context filter")
	expect(box.library("no such song 9483").is_empty(), "Search can return a clear empty result")
	for entry: Dictionary in catalog.music:
		expect(player.play_track(str(entry.name)), "The client can load and play " + str(entry.name))
	expect((player.get("_cache") as Dictionary).size() <= 4, "Browsing every song keeps the compressed-resource cache bounded")
	player.stop()
	box.request_game("@town_day")
	expect(player.current_track() == "town_theme_rpg", "The default follows the server's authored music")
	box.choose("song", "rising_moon")
	expect(player.current_track() == "rising_moon", "An individual song is playable")
	var voices: Array = player.get("_players")
	var slot: int = player.get("_active")
	var stream: AudioStream = voices[slot].stream
	expect(not (stream as AudioStreamOggVorbis).loop, "Personal music advances through completion instead of resource loops")
	box.request_game("@invasion_boss")
	expect(voices[slot].stream == stream, "A world cue cannot interrupt personal music without a matching rule")
	box.create_playlist("Journey")
	box.edit_playlist("Journey", ["home_town", "rising_moon", "cave_theme", "bad_track", "home_town"])
	expect(box.playlists.Journey.size() == 3, "Playlists reject unknown songs and duplicate entries")
	box.set_options(false, "off", 0.0, true)
	box.choose("playlist", "Journey")
	expect(player.current_track() == "home_town", "An ordered playlist begins with its first song")
	box.call("_on_finished")
	expect(player.current_track() == "rising_moon", "A finished playlist song advances to the next")
	box.call("_on_finished")
	box.call("_on_finished")
	expect(player.current_track().is_empty(), "Repeat off stops after the last song")
	box.request_game("@town_day")
	expect(player.current_track().is_empty(), "A restated world cue does not restart an exhausted personal playlist")
	box.set_available(false)
	box.set_available(true)
	expect(player.current_track().is_empty(), "Toggling audio does not restart a completed queue with repeat off")
	box.toggle_pause()
	expect(player.current_track() == "home_town", "Play again restarts an exhausted playlist")
	box.set_options(false, "one", 0.0, true)
	box.call("_on_finished")
	expect(player.current_track() == "home_town", "Repeat one repeats the current song")
	box.skip()
	expect(player.current_track() == "rising_moon", "Next skips even when repeat one is selected")
	box.skip(-1)
	expect(player.current_track() == "home_town", "Previous follows playlist order")
	slot = player.get("_active")
	stream = voices[slot].stream
	box.create_playlist("A second playlist")
	expect(box.active_playlist == "Journey" and voices[slot].stream == stream, "Creating another playlist does not interrupt the playing playlist")
	box.edit_playlist("Journey", ["rising_moon", "home_town", "cave_theme"])
	expect(voices[slot].stream == stream and box.get("_index") == 1, "Reordering a playing playlist preserves its current song and position")
	box.rename_playlist("Journey", "Renamed journey")
	expect(box.active_playlist == "Renamed journey" and voices[slot].stream == stream, "Renaming a playing playlist preserves playback")
	box.rename_playlist("Renamed journey", "Journey")
	box.toggle_pause()
	slot = player.get("_active")
	expect(voices[slot].stream_paused, "Pause preserves the active stream")
	box.toggle_pause()
	expect(not voices[slot].stream_paused, "Resume unpauses playback")
	box.set_options(true, "all", 2.0, true)
	box.choose("playlist", "Journey")
	var heard: Array[String] = []
	for index: int in 3:
		heard.append(player.current_track())
		box.call("_on_finished")
	expect(heard.size() == 3 and heard[0] != heard[1] and heard[1] != heard[2] and heard[0] != heard[2], "Shuffle plays every playlist song before repeating")
	expect(player.current_track() != heard[2], "Shuffle avoids an immediate repeat between rounds")
	box.choose("shuffle")
	expect((box.get("_queue") as Array).size() == 39, "Shuffle all includes every client song")
	box.choose("playlist", "Journey")
	player.call("_process", 10.0)
	slot = player.get("_active")
	var ending := player.current_track()
	voices[slot].seek(voices[slot].stream.get_length() - 0.5)
	player.call("_process", 0.001)
	expect(player.current_track() != ending, "The player ending signal advances a personal queue before the track ends")
	var next_track := player.current_track()
	player.call("_on_finished", slot)
	expect(player.current_track() == next_track, "The outgoing crossfade voice cannot advance the queue twice")
	player.call("_process", 0.2)
	var gains: Array = player.get("_gains")
	expect(voices[0].playing and voices[1].playing and gains[0] > 0 and gains[1] > 0, "Personal crossfades overlap both audible voices")
	box.choose("shuffle")
	box.set_rules([
		{"context": "invasion_boss", "mode": "song", "target": "epic_boss_battle", "enabled": true},
		{"context": "encounter", "mode": "silent", "target": "", "enabled": true},
		{"context": "night", "mode": "playlist", "target": "Journey", "enabled": true}])
	box.request_game("@invasion_boss")
	expect(player.current_track() == "epic_boss_battle" and box.active_rule == 0, "The first enabled matching rule wins")
	box.request_game("@invasion_waves")
	expect(player.current_track().is_empty() and box.active_rule == 1, "Encounter-group rules can choose silence")
	box.request_game("@town_night")
	expect(box.effective_selection().mode == "playlist" and box.active_rule == 2, "Night-group rules can choose a named playlist")
	box.request_game("@town_day")
	expect(box.effective_selection().mode == "shuffle" and box.active_rule == -1, "Leaving a rule returns to the player's music mode")
	box.rename_playlist("Journey", "Travels")
	expect(box.rules[2].target == "Travels", "Renaming a playlist preserves its rule references")
	box.set_available(false)
	expect(player.current_track().is_empty(), "Disabling audio stops personal music")
	box.request_game("@town_night")
	expect(player.current_track().is_empty(), "World cues remain silent while audio is disabled")
	box.set_available(true)
	expect(box.active_rule == 2 and not player.current_track().is_empty(), "Enabling audio uses the latest world context and matching rule")
	var restored := Jukebox.new()
	restored.storage_path = box.storage_path
	root.add_child(restored)
	var other := MusicPlayer.new()
	root.add_child(other)
	other.configure(catalog.music)
	restored.configure(catalog.music, other)
	expect(restored.playlists == box.playlists and restored.rules == box.rules and restored.mode == box.mode, "Playlists, rules and playback options survive reopening the client")
	expect(other.current_track().is_empty(), "Loading preferences does not start music before a session or user action")
	box.delete_playlist("Travels")
	expect(not bool(box.rules[2].enabled), "Deleting a referenced playlist disables its rules")
	box.disconnect_session()
	box.set_available(false)
	box.set_available(true)
	expect(player.current_track().is_empty() and box.game_cue.is_empty(), "Disconnect clears playback and pending context without losing preferences")
	await _test_ui(box)
	await _test_director()
	restored.queue_free()
	other.queue_free()
	box.queue_free()
	player.queue_free()
	await process_frame
	stream = null
	await create_timer(0.2).timeout
	print("Jukebox checks: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)

func _test_ui(box: Node) -> void:
	var window := JukeboxWindow.new()
	window.jukebox = box
	root.add_child(window)
	window.open()
	await process_frame
	await process_frame
	expect(window.library_list.item_count == 39, "The Library displays all client tracks")
	window.search.text = "Rising Moon"
	window.search.text_changed.emit(window.search.text)
	expect(window.library_list.item_count == 1, "The search control filters the visible library")
	window.library_list.select(0)
	window.library_list.item_selected.emit(0)
	window.play_song.pressed.emit()
	expect(box.mode == "song" and box.current_track() == "rising_moon", "The Play song control reaches real playback")
	window.playlist_name.text = "Evening"
	for button: Button in window.find_children("*", "Button", true, false):
		if button.text == "Create":
			button.pressed.emit()
			break
	expect(box.playlists.has("Evening") and window.get("_selected_playlist") == "Evening", "The Create control selects the new playlist for adding songs")
	window.library_list.select(0)
	window.add_button.pressed.emit()
	expect(box.playlists.Evening == ["rising_moon"], "The Add button adds the selected song to the chosen playlist")
	window.tabs.current_tab = 2
	window.call("_select", window.condition, "night")
	window.call("_select", window.action, "playlist")
	window.call("_refresh_targets")
	window.call("_select", window.target, "Evening")
	window.rule_save.pressed.emit()
	expect(box.rules.back().context == "night" and box.rules.back().target == "Evening", "The rule editor saves the selected condition, action and target")
	var rule_toggle := window.rules_list.find_child("RuleEnabled", true, false) as CheckButton
	window.call("_edit_rule", 0)
	var was_enabled: bool = box.rules[0].enabled
	rule_toggle.button_pressed = not was_enabled
	expect(bool(box.rules[0].enabled) != was_enabled, "A rule row can be enabled or disabled without editing its form")
	expect(window.rule_enabled.button_pressed == bool(box.rules[0].enabled), "The rule's enable switch and edit form stay synchronized")
	await process_frame
	await process_frame
	var first: Button = window.rules_list.find_child("Rule1", true, false)
	var second: Button = window.rules_list.find_child("Rule2", true, false)
	var first_context: String = box.rules[0].context
	var origin := first.get_global_rect().position + Vector2(13, 24)
	var destination := second.get_global_rect().position + Vector2(13, 24)
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = origin
	window.push_input(press, true)
	await process_frame
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.position = destination
	motion.relative = destination - origin
	window.push_input(motion, true)
	await process_frame
	press.pressed = false
	press.position = destination
	window.push_input(press, true)
	await process_frame
	expect(str(box.rules[1].context) == first_context, "Dragging a rule grip changes its actual first-match priority")
	for size: Vector2i in [Vector2i(1280, 800), Vector2i(800, 600)]:
		root.size = size
		window.open()
		for frame: int in 8:
			await process_frame
		expect(window.size.x <= size.x and window.size.y <= size.y, "The jukebox (%s) fits a %s viewport" % [window.size, size])
		expect(window.tabs.position.y + window.tabs.size.y < window.size.y, "Tab content stays inside the popup after its initial layout")
		expect(Rect2(Vector2.ZERO, Vector2(window.size)).encloses(window.transport.get_global_rect()), "The complete transport footer %s fits inside the popup %s at %s" % [window.transport.get_global_rect(), window.size, size])
		for tab: int in 3:
			window.tabs.current_tab = tab
			await process_frame
			expect(window.panels[tab].get_combined_minimum_size().x <= window.columns.size.x, "Panel %d fits the available width at %s" % [tab, size])
	window.hide()
	window.queue_free()
	await process_frame

func _test_director() -> void:
	var had_preferences := FileAccess.file_exists(Jukebox.DEFAULT_PATH)
	var saved_preferences := FileAccess.get_file_as_bytes(Jukebox.DEFAULT_PATH) if had_preferences else PackedByteArray()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(Jukebox.DEFAULT_PATH))
	var director: Node = load("res://src/audio/audio_director.gd").new()
	root.add_child(director)
	var state := root.get_node("AppState")
	state.music_requested.emit("@town_day")
	expect(director.current_music() == "town_theme_rpg", "Server music events reach game-directed playback through the real director")
	director.jukebox.choose("song", "rising_moon")
	state.music_requested.emit("@invasion_boss")
	expect(director.current_music() == "rising_moon", "Personal playback overrides server cues in the director")
	director.enabled = false
	state.music_requested.emit("@coast_day")
	expect(director.current_music().is_empty(), "Master audio off silences jukebox playback")
	director.enabled = true
	expect(director.current_music() == "rising_moon", "Master audio on resumes personal playback")
	director.jukebox.choose("game")
	expect(director.current_music() == "sunshine_coast", "Returning to game music restores the latest server context")
	state.music_requested.emit("settlement")
	expect(director.current_music() == "settlement", "Legacy music requests still play")
	director.jukebox.toggle_pause()
	expect(director.get("_music_player").stream_paused, "Pause includes legacy game music")
	director.jukebox.choose("song", "home_town")
	expect(not director.get("_music_player").playing, "Personal music stops the legacy voice")
	state.connection_state = "disconnected"
	state.state_changed.emit(&"connection")
	director.enabled = false
	director.enabled = true
	expect(director.current_music().is_empty(), "Disconnect cannot restart music when audio is toggled")
	# Mount the production Audio page as main does, without loading a world.
	var settings: Control = load("res://src/ui/settings_window.gd").new()
	root.add_child(settings)
	var credits := Button.new()
	credits.name = "AudioCreditsButton"
	settings.page_body("Audio").add_child(credits)
	settings.add_audio_controls()
	var button: Button = settings.panel.find_child("JukeboxButton", true, false)
	button.pressed.emit()
	await process_frame
	var dialog: AcceptDialog = settings.get_node_or_null("JukeboxWindow")
	expect(dialog != null and dialog.visible and dialog.jukebox == director.jukebox, "Audio settings opens a jukebox connected to real playback")
	if dialog != null:
		dialog.hide()
		button.pressed.emit()
		expect(settings.get_node("JukeboxWindow") == dialog, "Reopening the jukebox reuses its window")
		dialog.hide()
	settings.queue_free()
	director.queue_free()
	await process_frame
	if had_preferences:
		var file := FileAccess.open(Jukebox.DEFAULT_PATH, FileAccess.WRITE)
		file.store_buffer(saved_preferences)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(Jukebox.DEFAULT_PATH))
