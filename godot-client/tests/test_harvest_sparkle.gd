extends SceneTree
## The glitter around a harvesting player follows the server's harvest-state
## packet: it starts with a run, stops with one, respects the particles
## setting, and waits for the player's own node when the run arrives first.

const SETTINGS_PATH := "user://eloria_hud.cfg"

var failures: int = 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# The particles toggle saves the player's settings file; put it back after.
	var saved_settings: Variant = (FileAccess.get_file_as_bytes(SETTINGS_PATH)
		if FileAccess.file_exists(SETTINGS_PATH) else null)
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		quit(failures)
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)

	# The run arrives before the player's own node exists: nothing to glitter
	# around yet, and no guess at a position.
	app_state.set("local_actor_id", 91)
	app_state.call("_on_packet", 237, _started("Reed"))
	await process_frame
	_expect(main.get("harvest_sparkle") == null,
		"no glitter is drawn before the harvester has a node")

	# The player's node arrives, mid-run.
	app_state.call("_on_packet", 51, _hex(
		"5b00020004000000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var actor: Node3D = (main.get("actor_nodes") as Dictionary).get(91) as Node3D
	_expect(actor != null, "the harvester is on screen")
	var sparkle: HarvestSparkle3D = main.get("harvest_sparkle") as HarvestSparkle3D
	_expect(sparkle != null and sparkle.is_following(actor),
		"the glitter starts around the harvester once they are on screen")
	var particles: GPUParticles3D = sparkle.get_node_or_null(
		"HarvestSparkles") as GPUParticles3D if sparkle != null else null
	_expect(particles != null and particles.emitting and not particles.one_shot
		and particles.amount > 0 and particles.process_material != null
		and particles.draw_pass_1 != null,
		"it is a continuous particle emitter, not a one-shot burst")
	_expect(sparkle != null
		and sparkle.global_position.is_equal_approx(actor.global_position),
		"it stands where the harvester stands")

	# A second state packet for the same run does not restart the glitter.
	app_state.call("_on_packet", 237, _started("Reed"))
	await process_frame
	_expect(main.get("harvest_sparkle") == sparkle,
		"a repeated harvest state keeps the glitter already running")

	# The server stops the run: the flares in the air finish, then it goes.
	app_state.call("_on_packet", 237, PackedByteArray([0, 0, 0, 0]))
	await process_frame
	_expect(main.get("harvest_sparkle") == null and is_instance_valid(sparkle)
		and sparkle.is_stopping() and not particles.emitting,
		"a server stop stops emitting without cutting off live flares")
	sparkle._process(HarvestSparkle3D.LIFETIME_SECONDS + 0.1)
	await process_frame
	_expect(not is_instance_valid(sparkle), "and the glitter frees itself after")

	# The particles setting turns it off mid-run and back on.
	app_state.call("_on_packet", 237, _started("Reed"))
	await process_frame
	var restarted: HarvestSparkle3D = main.get("harvest_sparkle") as HarvestSparkle3D
	_expect(restarted != null, "a new run glitters again")
	main.call("_on_client_setting_changed", "graphics", "particles", false)
	_expect(main.get("harvest_sparkle") == null and is_instance_valid(restarted)
		and restarted.is_stopping(),
		"turning particles off stops the glitter")
	main.call("_on_client_setting_changed", "graphics", "particles", true)
	_expect(main.get("harvest_sparkle") != null,
		"turning particles back on mid-run brings it back")
	main.call("_on_client_setting_changed", "graphics", "particles", false)
	app_state.call("_on_packet", 237, PackedByteArray([0, 0, 0, 0]))
	app_state.call("_on_packet", 237, _started("Reed"))
	await process_frame
	_expect(main.get("harvest_sparkle") == null,
		"with particles off a run starts no glitter")
	main.call("_on_client_setting_changed", "graphics", "particles", true)

	# The harvester's node goes away before the server says the run ended.
	var orphan: HarvestSparkle3D = main.get("harvest_sparkle") as HarvestSparkle3D
	app_state.call("_on_packet", 6, PackedByteArray([0x5b, 0]))
	await process_frame
	main.call("_sync_world")
	for _settle: int in range(3):
		await process_frame
	_expect(orphan != null and is_instance_valid(orphan) and orphan.is_stopping(),
		"a harvester who vanishes mid-run takes the glitter with them")

	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame
	if saved_settings is PackedByteArray:
		var restore := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		restore.store_buffer(saved_settings as PackedByteArray)
		restore.close()
	elif FileAccess.file_exists(SETTINGS_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("harvest sparkle: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _started(resource: String) -> PackedByteArray:
	var bytes := PackedByteArray([1, 0xf0, 0x01])
	bytes.append_array(resource.to_utf8_buffer())
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
