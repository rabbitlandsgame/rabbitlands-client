extends SceneTree
## Guards the audio layer.
##
## Every sound is answered to an authoritative event: a harvest the server
## started, an item it put in the backpack, a combat outcome it reported, an
## effect it announced. Nothing plays on a guess, and a snapshot that restates
## what was already true is not a new event.

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

	var names: Array = director.call("sound_names") as Array
	_expect(names.size() == 31 and names.has("harvest_start")
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
	var toggle: CheckButton = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Audio/Audio/SoundRow/SoundEnabled") as CheckButton
	var slider: HSlider = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Audio/Audio/SoundRow/SoundVolume") as HSlider
	var readout: Label = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Audio/Audio/SoundRow/SoundVolumeValue") as Label
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
		and is_equal_approx(db_to_linear(music_player.volume_db), 0.35 * 0.35),
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

	var credits_button := main.get_node("GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Audio/Audio/AudioCreditsButton") as Button
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

	print("audio director tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

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
