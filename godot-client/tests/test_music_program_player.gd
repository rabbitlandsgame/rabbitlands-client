extends SceneTree

const MusicPlayer := preload("res://src/audio/music_program_player.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func expect(value: bool, description: String) -> void:
	if not value:
		failures += 1
		push_error(description)

func _run() -> void:
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/audio/catalog.json"))
	var player := MusicPlayer.new()
	root.add_child(player)
	player.configure(catalog.music)
	expect(catalog.music.size() == 39, "All three legacy and 36 additional music tracks are available")
	expect(player.request("@town_day"), "The server's town context loads")
	expect(player.current_track() == "town_theme_rpg", "The authored first choice begins the first program")
	var slot: int = player.get("_active")
	var voices: Array = player.get("_players")
	var stream: AudioStream = voices[slot].stream
	player.request("@town_day")
	expect(voices[slot].stream == stream, "Restating a context does not restart or replace the stream")
	player.request("@invasion_boss")
	player.call("_process", 0.5)
	var gains: Array = player.get("_gains")
	expect(voices[0].playing and voices[1].playing and gains[0] > 0 and gains[1] > 0,
		"An encounter crossfade overlaps both audible voices")
	expect(player.current_track() == "epic_boss_battle", "A real boss context takes precedence")
	player.request("@coast_day")
	player.request("@woodland_day")
	expect(str(player.get("_pending")) == "@woodland_day", "Rapid ambient changes are held briefly")
	player.request("@coast_day")
	expect(str(player.get("_pending")).is_empty(), "Returning to the current context cancels a pending detour")
	player.call("_process", 10.0)
	var before := player.current_track()
	slot = int(player.get("_active"))
	voices[slot].seek(voices[slot].stream.get_length() - 0.01)
	player.call("_process", 0.001)
	expect(player.current_track() != before, "A multi-track pool rotates before the end without an immediate repeat")
	player.request("@aftermath|town_day|test-event-1")
	slot = int(player.get("_active"))
	expect(not (voices[slot].stream as AudioStreamOggVorbis).loop, "Aftermath is a finite cue")
	var ending_stream: AudioStream = voices[slot].stream
	player.request("@aftermath|town_night|test-event-1")
	expect(voices[slot].stream == ending_stream, "Dusk changes the return pool without restarting an aftermath")
	player.call("_on_finished", slot)
	expect(str(player.get("_request")) == "@town_night", "Finishing the cue restores its current location/time pool")
	var restored := player.current_track()
	player.request("@aftermath|town_night|test-event-1")
	expect(player.current_track() == restored and str(player.get("_request")) == "@town_night",
		"A repeated completed-event packet cannot replay its victory cue")
	for key: String in ["@temple", "@mystic_cave", "@invasion_surge", "@invasion_boss", "@inn"]:
		player.set("_changed_at", -100.0)
		player.request(key)
	expect((player.get("_cache") as Dictionary).size() <= 4, "Compressed music resources have a bounded cache")
	player.stop()
	expect(not voices[0].playing and not voices[1].playing and player.current_track().is_empty(),
		"Stop silences both voices and pending music")
	player.queue_free()
	await process_frame

	# Exercise the real audio director's mute and disconnect behavior too.
	var director: Node = load("res://src/audio/audio_director.gd").new()
	root.add_child(director)
	var state: Node = root.get_node("AppState")
	var packet := "@town_day".to_utf8_buffer()
	packet.append(0)
	state.call("_on_packet", 54, packet)
	expect(str(director.call("current_music")) == "town_theme_rpg", "PLAY_MUSIC decodes through AppState into the real director")
	director.set("enabled", false)
	var adaptive: Node = director.get("_program_player")
	expect(str(adaptive.call("current_track")).is_empty(), "Disabling audio stops the adaptive layer")
	director.call("play_music", "@coast_day")
	director.set("enabled", true)
	expect(str(director.call("current_music")) == "sunshine_coast", "Enabling resumes the latest server context received while muted")
	state.set("connection_state", "disconnected")
	state.state_changed.emit(&"connection")
	director.set("enabled", false)
	director.set("enabled", true)
	expect(str(director.call("current_music")).is_empty(), "Disconnecting clears the remembered program")
	director.queue_free()
	await process_frame
	stream = null
	ending_stream = null
	# Let the audio mixer release stopped playback resources before engine exit.
	await create_timer(0.2).timeout
	print("Music program playback checks: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)
