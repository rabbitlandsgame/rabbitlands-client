extends SceneTree
## Guards the sky and the fires the server places.
##
## `SEND_WEATHER(100)`, `START_RAIN(15)`, `STOP_RAIN(16)`, `THUNDER(17)`,
## `FIRE_PARTICLES(61)` and `REMOVE_FIRE_AT(62)` were all unallocated, so this
## client had a particle system with nothing to point at.
##
## Nothing here decides anything. What is falling and how hard arrives on the
## wire, because two players standing together have to see the same sky.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene
		).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var layer: Weather3D = main.get("weather_layer") as Weather3D
	await process_frame

	_expect(layer != null, "the world carries a weather layer")
	if layer == null:
		quit(1)
		return
	_expect(not layer.is_raining() and layer.fire_count() == 0,
		"nothing falls and nothing burns until the server says so")

	# The decoders, including what they refuse.
	_expect(EloriaProtocol.decode_server(100, PackedByteArray([2, 80])).type
			== "weather",
		"a sky frame decodes")
	_expect(EloriaProtocol.decode_server(100, PackedByteArray([1])).type
			== "invalid",
		"a truncated sky frame is rejected")
	_expect(EloriaProtocol.decode_server(100, PackedByteArray([1, 200])).type
			== "invalid",
		"an intensity past 100 is rejected rather than clamped into a lie")
	_expect(EloriaProtocol.decode_server(17, PackedByteArray([])).type
			== "invalid",
		"a thunder frame with no severity is rejected")
	_expect(EloriaProtocol.decode_server(61, PackedByteArray([1, 0, 2, 0])).type
			== "invalid",
		"a fire frame of the wrong length is rejected")

	# Rain, and how hard.
	app_state.call("_on_packet", 100, PackedByteArray([1, 30]))
	await process_frame
	_expect(layer.is_raining(), "a rain frame makes it rain")
	var shower: int = layer.rain_particles()
	app_state.call("_on_packet", 100, PackedByteArray([1, 90]))
	await process_frame
	_expect(layer.rain_particles() > shower,
		"heavier rain is more rain, not the same rain: %d then %d"
			% [shower, layer.rain_particles()])
	app_state.call("_on_packet", 100, PackedByteArray([2, 90]))
	await process_frame
	_expect(layer.rain_particles() > shower and layer.kind == 2,
		"a storm is its own kind of sky")

	# Stopping, both ways round.
	app_state.call("_on_packet", 100, PackedByteArray([0, 0]))
	await process_frame
	_expect(not layer.is_raining(), "a clear sky stops the rain")
	app_state.call("_on_packet", 15, PackedByteArray([40]))
	await process_frame
	_expect(layer.is_raining(),
		"the legacy start-rain signal alone still makes it rain, for a server"
			+ " that sends no whole-sky frame")
	app_state.call("_on_packet", 16, PackedByteArray([]))
	await process_frame
	_expect(not layer.is_raining(), "and the legacy stop signal stops it")

	# A legacy start-rain must not invent a storm the sky frame did not state.
	app_state.call("_on_packet", 100, PackedByteArray([2, 70]))
	await process_frame
	app_state.call("_on_packet", 15, PackedByteArray([10]))
	await process_frame
	_expect(int((app_state.get("weather") as Dictionary).get("kind", 0)) == 2,
		"the legacy signal confirms the stated sky rather than overruling it")

	# Fires.
	app_state.call("_on_packet", 61, PackedByteArray([0x3c, 0, 0x46, 0, 1]))
	await process_frame
	_expect(layer.fire_count() == 1 and layer.has_fire_at(Vector2i(60, 70)),
		"a fire is placed at the tile the server named")
	app_state.call("_on_packet", 61, PackedByteArray([0x3c, 0, 0x46, 0, 2]))
	await process_frame
	_expect(layer.fire_count() == 1,
		"the same tile stated twice is one fire, not two in one place")
	app_state.call("_on_packet", 61, PackedByteArray([0x50, 0, 0x50, 0, 9]))
	await process_frame
	_expect(layer.fire_count() == 2,
		"a kind this client does not know is still a fire that is there")
	app_state.call("_on_packet", 62, PackedByteArray([0x3c, 0, 0x46, 0]))
	await process_frame
	_expect(layer.fire_count() == 1 and not layer.has_fire_at(Vector2i(60, 70)),
		"a fire the server puts out goes out")

	# Turning effects off takes the weather with them.
	main.set("_effects_enabled", false)
	app_state.call("_on_packet", 100, PackedByteArray([2, 80]))
	await process_frame
	_expect(not layer.is_raining(),
		"with effects off the sky is not drawn either")
	main.set("_effects_enabled", true)
	app_state.call("_on_packet", 100, PackedByteArray([2, 80]))
	await process_frame
	_expect(layer.is_raining(), "and turning them back on restores it")

	# A legacy pair is drawn as the nearest look: the rain falls exactly as
	# hard as the pair says, and a storm is darker than a shower.
	var light_shower: Array = Weather3D.legacy_look(1, 30)
	var downpour: Array = Weather3D.legacy_look(1, 90)
	var storm: Array = Weather3D.legacy_look(2, 60)
	_expect(Weather3D.legacy_look(0, 0) == [0, 0, 0, 0, 0, 0, 0]
		and int(light_shower[0]) == 1 and int(light_shower[1]) == 30 and int(downpour[1]) == 90
		and int(storm[6]) > 0 and int(storm[4]) > int(Weather3D.legacy_look(1, 60)[4]),
		"a legacy pair is the look a whole-sky server would have sent: %s %s" % [light_shower, storm])
	layer.set_weather(2, 60, false, false)
	_expect(not layer.is_raining() and layer.has_weather() and layer.gloom() > 0.05
		and is_equal_approx(float(layer.look().precipitation), 0.6) and not layer.settling(),
		"the particle switch turns the drops off, not the sky; a sky met on arrival is already there")
	layer.set_weather(0, 0)
	_expect(layer.settling() and layer.has_weather(),
		"a sky that clears while the player stays eases out rather than cutting")
	await _settle(layer, 8.0)
	_expect(not layer.has_weather(), "and it does arrive at a clear sky")

	# A whole-sky server: the look now and the look it is becoming, eased over
	# the seconds it gives. A sky met on arrival starts where the server's is.
	var fog_bank: Array = [0, 0, 55, 85, 18, 5, 0]
	var snowfall: Array = [2, 90, 100, 55, 35, 50, 0]
	layer.set_state(fog_bank, snowfall, 0.6, true, true, "heavy_snow")
	_expect(is_equal_approx(float(layer.look().fog), 0.85) and layer.settling()
		and layer.state_name == "heavy_snow",
		"arriving mid-change starts from the sky as it is")
	await _settle(layer, 3.0)
	_expect(is_equal_approx(float(layer.look().precipitation), 0.9)
		and int(layer.look().fall) == 2 and layer.falling("snow") > 0
		and layer.falling("rain") == 0 and not layer.is_raining(),
		"and eases to the snow it is becoming: %s" % [layer.look()])
	var quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.set_environment(LookProfile.QUALITY_VARIABLE, "low")
	layer.set_state(snowfall, snowfall, 0.0)
	var low := layer.falling("snow")
	OS.set_environment(LookProfile.QUALITY_VARIABLE, "high")
	layer.set_state(snowfall, snowfall, 0.0)
	_expect(low > 0 and low < layer.falling("snow"), "low graphics quality draws less of it")
	if quality.is_empty():
		OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	else:
		OS.set_environment(LookProfile.QUALITY_VARIABLE, quality)
	layer.set_state(snowfall, [4, 80, 40, 70, 30, 95, 0], 0.0)
	_expect(layer.falling("sand") > 0 and layer.falling("snow") == 0,
		"a kind of sky the server adds (a sandstorm) is drawn by what falls, not by its name")
	layer.set_state([3, 45, 90, 45, 40, 15, 0], [3, 45, 90, 45, 40, 15, 0], 0.0)
	_expect(layer.falling("ash") > 0, "and ash falls as ash")

	# The frame itself, through AppState to the layer.
	var frame := PackedByteArray([1, 0, 0, 0, 0, 0, 10, 0, 1, 85, 100, 40, 45, 55, 0, 200, 0, 10])
	frame.append_array("heavy_rain".to_ascii_buffer())
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_WEATHER_STATE, frame)
	await process_frame
	var told: Dictionary = app_state.get("weather_state")
	_expect(str(told.get("name", "")) == "heavy_rain" and is_equal_approx(float(told.seconds), 20.0)
		and int((app_state.get("weather") as Dictionary).kind) == 1
		and layer.state_name == "heavy_rain" and layer.settling() and layer.is_raining(),
		"a whole-sky frame reaches the layer and eases over its own time: %s" % told)
	# Walking into another map: its sky is as it is (no seconds left), and is
	# still eased into rather than cut at the border.
	await _settle(layer, 25.0)
	app_state.set("current_map", "a_neighbour")
	var still := PackedByteArray([1, 0, 0, 55, 85, 18, 5, 0, 0, 0, 55, 85, 18, 5, 0, 0, 0, 3])
	still.append_array("fog".to_ascii_buffer())
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_WEATHER_STATE, still)
	await process_frame
	_expect(layer.settling() and layer.is_raining() == false and layer.state_name == "fog",
		"a sky met by crossing into another map eases in over a few seconds")
	app_state.call("_on_packet", 100, PackedByteArray([0, 0]))
	await process_frame
	_expect((app_state.get("weather_state") as Dictionary).is_empty() and not layer.is_raining(),
		"a legacy frame after it is the whole story again")

	# What the overcast does to the light (WeatherSky): the binders read the
	# weathered copy exactly as they read the manifest.
	var lit := WorldManifest.new()
	lit.data = {"asset": {"id": "isle"}, "continentGeography": {}, "environment": {
		"sky": {"zenith": [0.16, 0.42, 0.72], "horizon": [0.72, 0.87, 0.92]},
		"sun": {"enabled": true, "energy": 1.1, "color": [1.0, 0.94, 0.83]},
		"ambient": {"energy": 0.6, "color": [0.6, 0.67, 0.72]},
		"fog": {"enabled": true, "color": [0.62, 0.8, 0.86], "density": 0.0004},
		"saturation": 1.3,
		"variants": {"dusk": {"sun": {"color": [1.0, 0.6, 0.4]}},
			"night": {"sky": {"zenith": [0.1, 0.17, 0.32]}}}}}
	var before := lit.data.duplicate(true)
	_expect(WeatherSky.weathered(lit, 0.0) == lit,
		"a dry sky is the manifest itself, not a copy")
	var wet := WeatherSky.weathered(lit, 1.0)
	var dry_env: Dictionary = lit.data.environment
	var wet_env: Dictionary = wet.data.environment
	var dry_zenith := DayNightBinder._colour(dry_env.sky.zenith, Color.BLACK)
	var wet_zenith := DayNightBinder._colour(wet_env.sky.zenith, Color.BLACK)
	_expect(wet_zenith.s < dry_zenith.s * 0.5 and wet_zenith.v < dry_zenith.v,
		"a storm's sky is grey and darker: s %.2f -> %.2f" % [dry_zenith.s, wet_zenith.s])
	_expect(float(wet_env.sun.energy) < float(dry_env.sun.energy) * 0.5
		and float(wet_env.fog.density) > float(dry_env.fog.density) * 2.0
		and float(wet_env.saturation) < float(dry_env.saturation),
		"under a storm the sun dims, the haze thickens and the colours flatten")
	var wet_dusk := DayNightBinder._colour(wet_env.variants.dusk.sun.color, Color.BLACK)
	_expect(wet_dusk.s < 0.4 and DayNightBinder._colour(
			wet_env.variants.night.sky.zenith, Color.BLACK).s
			< DayNightBinder._colour(dry_env.variants.night.sky.zenith, Color.BLACK).s,
		"a wet dusk does not glow orange, and a wet night is greyer too")
	_expect(LookSky.clearness(wet, wet_env.sky, Color.BLACK)
			< LookSky.clearness(lit, dry_env.sky, Color.BLACK) * 0.5,
		"the painted sky reads the weathered zenith as overcast")
	_expect(lit.data == before and wet.source_path == lit.source_path,
		"the manifest itself is left as it was")
	# Each part of a look does its own work.
	var partly := WeatherSky.weathered_look(lit, {"clouds": 0.45})
	_expect(DayNightBinder._colour(partly.data.environment.sky.zenith, Color.BLACK).s
			> dry_zenith.s * 0.9,
		"a partly cloudy sky keeps its blue: the painted sky draws the clouds")
	var fogged: Dictionary = WeatherSky.weathered_look(lit, {"clouds": 0.55, "fog": 0.85,
		"darkness": 0.18}).data.environment
	_expect(float(fogged.fog.density) > float(dry_env.fog.density) * 6.0
		and float(fogged.sun.energy) > float(dry_env.sun.energy) * 0.7,
		"a fog bank closes the view without putting the sun out")
	var grey: Dictionary = WeatherSky.weathered_look(lit, {"clouds": 0.92}).data.environment
	_expect(float(grey.sun.shadowOpacity)
			< WorldEnvironmentBinder.sun_shadow_opacity(dry_env.sun) * 0.4,
		"an overcast sky softens the shadows: flat light, not a grey noon")
	_expect(is_equal_approx(float(fogged.fog.weather), 0.85),
		"the weather's fog travels with the haze for the look pass")
	var haze_test := Environment.new()
	LookSky._haze(haze_test, WeatherSky.weathered_look(lit, {"fog": 0.85}), Color.GRAY)
	var clear_haze := Environment.new()
	LookSky._haze(clear_haze, lit, Color.GRAY)
	_expect(haze_test.fog_depth_begin < 20.0 and haze_test.fog_depth_end < 200.0
		and haze_test.fog_density > clear_haze.fog_density
		and is_equal_approx(clear_haze.fog_depth_begin, LookProfile.HAZE_BEGIN),
		"a fog bank closes the painted haze in; a clear day keeps it far off")
	var dusty: Dictionary = WeatherSky.weathered_look(lit, {"fall": 4, "precipitation": 0.8,
		"fog": 0.7}).data.environment
	var dust := DayNightBinder._colour(dusty.fog.color, Color.BLACK)
	_expect(dust.r > dust.b, "a sandstorm's haze is sand-coloured")
	var dark: Dictionary = WeatherSky.weathered_look(lit, {"darkness": 0.6}).data.environment
	_expect(float(dark.sun.energy) < float(dry_env.sun.energy) * 0.5
		and float(dark.ambient.energy) < float(dry_env.ambient.energy),
		"darkness dims the sun and the ambient")

	print("weather tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

## Lets the layer ease (real seconds, as the game runs), up to `limit`.
func _settle(layer: Weather3D, limit: float) -> void:
	var deadline := Time.get_ticks_msec() + int(limit * 1000.0)
	while layer.settling() and Time.get_ticks_msec() < deadline:
		await process_frame

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
