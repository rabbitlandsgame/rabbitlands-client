extends SceneTree
## Rain is a continuous ambience voice, independent of event voices and graphics.

const AudioMix := preload("res://src/audio/audio_mix.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var director: Node = (load("res://src/audio/audio_director.gd") as GDScript).new()
	root.add_child(director)
	director.set_process(false)
	director.set_weather({"fall": 1, "precipitation": 0.35})
	director._process(0.2)
	var rain := director.get_node_or_null("RainAmbience") as AudioStreamPlayer
	_expect(rain != null and rain.playing, "rain starts a dedicated ambience voice")
	if rain == null:
		quit(failures)
		return
	_expect(rain.bus == AudioMix.CATEGORIES.ambience.bus,
		"rain respects the world ambience volume")
	var wav := rain.stream as AudioStreamWAV
	_expect(wav != null and wav.loop_mode == AudioStreamWAV.LOOP_FORWARD
		and wav.loop_end == roundi(wav.get_length() * wav.mix_rate),
		"the recording loops over its complete decoded frame range")
	var start_gain: float = db_to_linear(rain.volume_db)
	director._process(0.2)
	_expect(db_to_linear(rain.volume_db) > start_gain,
		"rain fades in instead of starting at full gain")
	director._process(2.0)
	var shower_gain: float = db_to_linear(rain.volume_db)
	director.set_weather({"fall": 1, "precipitation": 0.95})
	director._process(2.0)
	_expect(db_to_linear(rain.volume_db) > shower_gain
		and director.get_node("RainAmbience") == rain,
		"heavier rain raises the continuous voice rather than stacking loops")
	director.set_weather({"fall": 2, "precipitation": 1.0})
	director._process(0.1)
	_expect(rain.playing, "a change away from rain fades the old bed")
	director._process(2.0)
	_expect(not rain.playing, "snow has no rain sound")
	var weather := Weather3D.new()
	root.add_child(weather)
	weather.set_weather(1, 75, false, false)
	director.set_weather(weather.look())
	director._process(2.0)
	_expect(rain.playing and not weather.is_raining(),
		"hiding rain particles leaves the server's rain audible")
	director.set_weather({})
	director._process(2.0)
	_expect(not rain.playing, "indoors and inactive play have no outdoor rain bed")
	director.set_weather(weather.look())
	director._process(2.0)
	director.enabled = false
	_expect(not rain.playing, "disabling sound stops rain immediately")
	director.set_weather(weather.look())
	director._process(2.0)
	_expect(not rain.playing, "weather updates stay silent while sound is disabled")
	director.enabled = true
	director.set_weather(weather.look())
	director._process(2.0)
	_expect(rain.playing, "enabling sound resumes the current rain")
	root.get_node("AppState").set("connection_state", "disconnected")
	director._on_state_changed(&"connection")
	director._process(2.0)
	_expect(not rain.playing, "disconnect clears the continuous rain voice")
	director.queue_free()
	weather.queue_free()
	await process_frame
	print("rain audio tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
