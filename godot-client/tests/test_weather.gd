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

	print("weather tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
