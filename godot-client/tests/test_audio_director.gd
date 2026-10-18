extends SceneTree
## Guards the audio layer.
##
## Every sound is answered to an authoritative event: a harvest the server
## started, an item it put in the backpack, a combat outcome it reported, an
## effect it announced. Nothing plays on a guess, and a snapshot that restates
## what was already true is not a new event.

const AudioMix := preload("res://src/audio/audio_mix.gd")

var failures := 0
var played: Array[String] = []

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var director: Node = main.get("audio_director") as Node
	if not _expect(director != null, "the audio director is built"):
		quit(failures)
		return
	await process_frame
	_expect(is_equal_approx(float(director.get("volume_linear")), AudioMix.MASTER_DEFAULT)
		and is_equal_approx(float(director.get("category_volumes").interface), 0.2),
		"fresh settings start with a softer master and quiet HUD sounds")

	var names: Array = director.call("sound_names") as Array
	_expect(names.size() == 32 and names.has("rain") and names.has("harvest_start")
		and names.has("combat_hit") and names.has("world_effect")
		and names.has("footstep") and names.has("civic_crowd")
		and names.has("waterfall"),
		"the whole licensed sound set loaded: %s" % str(names))

	# Harvesting. The server states it started; a restatement is not a new one.
	director.set("enabled", true)
	_expect(bool(director.call("play", "ui_click")),
		"a sound the catalog has can be played")
	director.call("stop_all")
	var harvest_started := PackedByteArray([1, 0xf0, 0x01])
	harvest_started.append_array(_nul("Sunleaf"))
	app_state.call("_on_packet", 237, harvest_started)
	await process_frame
	_expect(bool(director.call("is_playing")),
		"the server starting a harvest is heard")
	director.call("stop_all")
	app_state.call("_on_packet", 237, harvest_started)
	await process_frame
	_expect(not bool(director.call("is_playing")),
		"restating the same harvest is not a second start")
	app_state.call("_on_packet", 237, PackedByteArray([0, 0, 0, 0]))
	await process_frame

	# Combat outcomes.
	director.call("stop_all")
	app_state.call("_on_packet", 227, _hex(
		"016600120014001e002c00050052656564686f726e205374616700"))
	await process_frame
	_expect(bool(director.call("is_playing")),
		"a hit the server reported is heard")
	director.call("stop_all")
	app_state.call("_on_packet", 227, _hex(
		"016600120014001e002c00050052656564686f726e205374616700"))
	await process_frame
	_expect(not bool(director.call("is_playing")),
		"the same outcome restated is not a second hit")

	# Footsteps. A step is heard when the server says the player is standing
	# somewhere else, and the first sighting after login is not a step.
	director.call("stop_all")
	# The server's own actor packet, then its own movement command: nothing
	# here pokes state directly.
	app_state.call("_on_packet", 3, PackedByteArray([0x5b, 0]))
	app_state.call("_on_packet", 51, _hex(
		"5b00020004000000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	await process_frame
	_expect(not bool(director.call("is_playing")),
		"seeing the player for the first time is not a step")
	# Command 22 is the east one-tile move in the legacy actor-command table.
	app_state.call("_on_packet", 2, PackedByteArray([0x5b, 0, 22]))
	await process_frame
	_expect(bool(director.call("is_playing")),
		"the server moving the player a tile is heard")
	director.call("stop_all")
	app_state.call("_on_packet", 51, _hex(
		"5b00030004000000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	await process_frame
	_expect(not bool(director.call("is_playing")),
		"restating the tile the player already stands on is not another step")

	# An effect the server announced.
	director.call("stop_all")
	app_state.call("_on_packet", 79, PackedByteArray([17, 0x5b, 0]))
	await process_frame
	_expect(bool(director.call("is_playing")),
		"an effect the server announced is heard")

	# Off means off, and stays off across events.
	director.call("stop_all")
	director.set("enabled", false)
	_expect(not bool(director.call("play", "ui_click")),
		"nothing plays while sound is off")
	app_state.call("_on_packet", 79, PackedByteArray([17, 0x5b, 0]))
	await process_frame
	_expect(not bool(director.call("is_playing")),
		"an announced effect stays silent while sound is off")
	director.set("enabled", true)

	# The setting is the player's own, and it is kept.
	var toggle := main.get("sound_enabled") as CheckButton
	var slider := main.get("sound_volume") as HSlider
	var readout := main.get("sound_volume_value") as Label
	main.call("_on_sound_volume_changed", 0.35)
	await process_frame
	_expect(is_equal_approx(float(director.get("volume_linear")), 0.35)
		and readout.text == "35%",
		"the volume the player chose is applied and shown: " + readout.text)
	main.call("_on_sound_enabled_toggled", false)
	await process_frame
	_expect(not bool(director.get("enabled")),
		"the toggle turns sound off")
	var config := ConfigFile.new()
	_expect(config.load(str(main.get("SETTINGS_PATH"))) == OK
		and not bool(config.get_value("audio", "enabled", true))
		and is_equal_approx(float(config.get_value("audio", "volume", 1.0)), 0.35),
		"both settings are written to the settings file")
	main.call("_on_sound_enabled_toggled", true)
	main.call("_on_sound_volume_changed", 0.7)
	_expect(toggle != null and slider != null,
		"the settings panel exposes both controls")

	# Sounds and music the server placed. Everything else this director plays
	# is its own answer to authoritative state; these two are things the
	# client could not have known - what somebody else is doing, and what the
	# map sounds like.
	_expect(director.call("sound_names").has("harvest_start"),
		"the catalog carries the sounds the server can name")
	var beds: Array = director.call("music_names") as Array
	_expect(beds.size() >= 3 and beds.has("settlement") and beds.has("wilds")
		and beds.has("depths"),
		"and the music beds the server can name: %s" % str(beds))

	var music_streams: Dictionary = director.get("_music_streams") as Dictionary
	for bed_name: String in ["settlement", "wilds", "depths"]:
		var stream := music_streams.get(bed_name) as AudioStreamOggVorbis
		_expect(stream != null and stream.loop and stream.get_length() > 10.0,
			"licensed music loads and loops: " + bed_name)

	app_state.call("_on_packet", 14, _sound_bytes("harvest_start", 60, 70, 100))
	await process_frame
	_expect(bool(director.call("is_playing")),
		"a sound the server placed is played")
	director.call("stop_all")
	app_state.call("_on_packet", 14, _sound_bytes("no_such_sound", 1, 1, 100))
	await process_frame
	_expect(not bool(director.call("is_playing")),
		"a sound this client does not have is silence, not a substitute")

	_expect(str(director.call("current_music")).is_empty(),
		"no music is playing before the server says any")
	app_state.call("_on_packet", 54, _nul("settlement"))
	await process_frame
	_expect(str(director.call("current_music")) == "settlement",
		"the map's music bed plays: " + str(director.call("current_music")))
	app_state.call("_on_packet", 54, _nul("settlement"))
	await process_frame
	_expect(str(director.call("current_music")) == "settlement",
		"the same bed restated does not restart it")
	var music_player := director.get("_music_player") as AudioStreamPlayer
	main.call("_on_sound_volume_changed", 0.35)
	_expect(music_player != null and music_player.playing
		and is_equal_approx(_output_gain(music_player), 0.35 * 0.55),
		"volume changes apply to music already playing")
	main.call("_on_sound_volume_changed", 0.7)
	app_state.call("_on_packet", 54, _nul(""))
	await process_frame
	_expect(str(director.call("current_music")).is_empty(),
		"an empty track is the server saying the map is quiet")
	app_state.call("_on_packet", 54, _nul("no_such_bed"))
	await process_frame
	_expect(str(director.call("current_music")).is_empty(),
		"and a bed this client does not have stays quiet rather than guessing")

	var credits_button := main.find_child("AudioCreditsButton", true, false) as Button
	credits_button.pressed.emit()
	await process_frame
	var dialog := main.get_node_or_null("AudioCredits") as AcceptDialog
	_expect(dialog != null and dialog.visible, "settings opens audio credits")
	if dialog != null:
		var text := (dialog.get_node("CreditsText") as RichTextLabel).get_parsed_text()
		_expect(text.contains("Creator: kurt") and text.contains("CC-BY-3.0")
			and text.contains("The Cynic Project / pixelsphere.org / cynicmusic.com")
			and text.contains("https://opengameart.org/content/stream-sounds")
			and text.contains("excerpt from 1 to 21 seconds"),
			"offline credits contain attribution, links, and modification notices")
		dialog.hide()
		credits_button.pressed.emit()
		_expect(main.get_node("AudioCredits") == dialog, "reopening credits reuses the window")
		dialog.hide()

	await _test_audio_mix(main, director, app_state)
	_test_rain_map_gating(main, director, app_state)

	print("audio director tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

func _test_rain_map_gating(main: Control, director: Node, state: Node) -> void:
	var saved_map: String = state.get("current_map")
	var weather: Weather3D = main.get("weather_layer")
	weather.set_weather(1, 80, false, false)
	state.set("authenticated", true)
	state.set("current_map", "four_gates")
	director.set("enabled", true)
	main.call("_process", 0.016)
	director.call("_process", 2.0)
	var rain := director.get_node_or_null("RainAmbience") as AudioStreamPlayer
	_expect(rain != null and rain.playing,
		"the client feeds outdoor rain to the director with particles hidden")
	var registry: Dictionary = main.get("map_registry")
	var inside := ""
	for map_id: String in registry:
		var entry: Dictionary = registry[map_id]
		if entry.has("interiorOf") or entry.has("insidesOf"):
			inside = map_id
			break
	_expect(not inside.is_empty(), "the shipped registry includes interior maps")
	state.set("current_map", inside)
	main.call("_process", 0.016)
	director.call("_process", 2.0)
	_expect(rain != null and not rain.playing,
		"entering an interior suppresses the outdoor rain bed")
	state.set("current_map", "four_gates")
	state.set("authenticated", false)
	main.call("_process", 0.016)
	director.call("_process", 2.0)
	_expect(rain != null and not rain.playing, "rain stays silent outside authenticated play")
	weather.clear()
	state.set("current_map", saved_map)
	director.call("stop_all")

func _test_audio_mix(main: Control, director: Node, state: Node) -> void:
	var window := main.get("settings_window") as Control
	var panel := window.get("panel") as PanelContainer
	window.call("open_tab", "Audio")
	await process_frame
	var cases := {"ui_click": "interface", "ui_close": "interface",
		"footstep_stone_1": "footsteps", "combat_hit": "combat",
		"spell_cast": "combat", "world_effect": "combat",
		"harvest_start": "activity", "item_pickup": "activity",
		"level_up": "activity", "civic_crowd": "ambience"}
	for sound: String in cases:
		director.call("play", sound)
		var voices: Array = director.get("_voices")
		var index := (int(director.get("_next_voice")) + voices.size() - 1) % voices.size()
		_expect((voices[index] as AudioStreamPlayer).bus == AudioMix.CATEGORIES[cases[sound]].bus,
			"the correct category controls " + sound)

	director.call("stop_all")
	state.call("_on_packet", 54, _nul("settlement"))
	var music := director.get("_music_player") as AudioStreamPlayer
	var position := music.get_playback_position()
	state.call("_on_packet", 54, _nul("settlement"))
	_expect(music.get_playback_position() >= position,
		"repeating the current music request preserves playback position")
	for category: String in AudioMix.CATEGORIES:
		var slider := panel.find_child("audio_" + category, true, false) as HSlider
		var readout := panel.find_child("audio_" + category + "_value", true, false) as Label
		_expect(slider != null and readout != null, category + " has a volume control")
		if slider == null or readout == null:
			continue
		slider.value = 0.31
		var config := ConfigFile.new()
		config.load(str(main.get("SETTINGS_PATH")))
		_expect(readout.text == "31%"
			and is_equal_approx(float(config.get_value("audio", category + "_volume", -1)), 0.31),
			category + " applies and saves the player's slider choice")
		var bus := AudioServer.get_bus_index(AudioMix.CATEGORIES[category].bus)
		_expect(is_equal_approx(db_to_linear(AudioServer.get_bus_volume_db(bus)), 0.31),
			category + " updates the live mix")
		slider.value = 0.0
		_expect(AudioServer.is_bus_mute(bus), category + " at zero is fully muted")
		slider.value = 0.31
	_expect(music.playing and is_equal_approx(_output_gain(music), 0.7 * 0.31),
		"adjusting categories keeps the map music playing at the chosen level")
	main.call("_load_hud_settings")
	for category: String in AudioMix.CATEGORIES:
		_expect(is_equal_approx(float(director.get("category_volumes")[category]), 0.31),
			category + " is restored from saved settings")

	main.call("_on_sound_enabled_toggled", false)
	_expect(not music.playing, "disabling audio stops music immediately")
	state.call("_on_packet", 54, _nul("wilds"))
	main.call("_on_sound_enabled_toggled", true)
	_expect(music.playing and str(director.call("current_music")) == "wilds",
		"enabling audio starts the latest map track received while muted")
	main.call("_on_sound_enabled_toggled", false)
	state.call("_on_packet", 54, _nul(""))
	main.call("_on_sound_enabled_toggled", true)
	_expect(not music.playing, "a quiet map stays quiet after enabling audio")
	state.call("_on_packet", 54, _nul("settlement"))
	main.call("_on_sound_enabled_toggled", false)
	state.call("_on_connection_state_changed", "disconnected")
	main.call("_on_sound_enabled_toggled", true)
	_expect(not music.playing, "disconnecting forgets the previous map's music")

	state.call("_on_packet", 14, _sound_bytes("harvest_start", 1, 1, 50))
	var voices: Array = director.get("_voices")
	var last := (int(director.get("_next_voice")) + voices.size() - 1) % voices.size()
	_expect(is_equal_approx(db_to_linear((voices[last] as AudioStreamPlayer).volume_db), 0.5),
		"server sound gain is preserved beneath the player's category volume")

	# Existing profiles keep the master choice and acquire the softer categories.
	var legacy := ConfigFile.new()
	legacy.set_value("audio", "enabled", true)
	legacy.set_value("audio", "volume", 0.85)
	legacy.save(str(main.get("SETTINGS_PATH")))
	main.call("_load_hud_settings")
	window.call("open_tab", "Audio")
	_expect(is_equal_approx(float(director.get("volume_linear")), 0.85)
		and is_equal_approx(float(director.get("category_volumes").interface), 0.2)
		and (panel.find_child("audio_interface_value", true, false) as Label).text == "20%",
		"legacy settings retain their master volume and receive softer category defaults")

func _output_gain(player: AudioStreamPlayer) -> float:
	var gain := db_to_linear(player.volume_db)
	var bus := AudioServer.get_bus_index(player.bus)
	while bus >= 0:
		if AudioServer.is_bus_mute(bus):
			return 0.0
		gain *= db_to_linear(AudioServer.get_bus_volume_db(bus))
		if bus == 0:
			break
		bus = AudioServer.get_bus_index(AudioServer.get_bus_send(bus))
	return gain

func _nul(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	bytes.append(0)
	return bytes

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

func _sound_bytes(name: String, x: int, y: int, gain: int) -> PackedByteArray:
	var payload := PackedByteArray([x & 0xFF, (x >> 8) & 0xFF,
		y & 0xFF, (y >> 8) & 0xFF, gain])
	payload.append_array(_nul(name))
	return payload
