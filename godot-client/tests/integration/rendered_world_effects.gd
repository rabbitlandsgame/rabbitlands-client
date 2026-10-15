extends SceneTree
## Rendered evidence for the effects the server says happened in the world.
##
## The "before" frame is two actors standing in the world with the effect
## packet already reduced and nothing on screen - which is what every
## `SEND_SPECIAL_EFFECT(79)` looked like, because the client had no decoder for
## it. The "after" frames are the same view with an effect at one actor and an
## effect travelling between two.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/phase2")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)

	var stage: Node3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot") as Node3D
	var ground_mesh := PlaneMesh.new()
	ground_mesh.size = Vector2(40.0, 40.0)
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_color = Color(0.29, 0.35, 0.24)
	ground_mesh.material = ground_material
	var ground := MeshInstance3D.new()
	ground.mesh = ground_mesh
	stage.add_child(ground)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, 38.0, 0.0)
	stage.add_child(sun)

	# Two players, four tiles apart, from the server's own actor builder.
	app_state.call("_on_packet", 51, _hex(
		"5b00020004000000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	app_state.call("_on_packet", 51, _hex(
		"4d00060004000000000001000001020304050b001e1407140012000142657373"
		+ "000040ff0600"))
	for _settle: int in range(6):
		await process_frame
	main.call("_sync_world")
	for _settle: int in range(6):
		await process_frame

	var camera: Camera3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig/Camera") as Camera3D
	camera.global_position = Vector3(4.0, 5.5, 6.0)
	camera.look_at(Vector3(4.0, 1.0, -4.0), Vector3.UP)
	for _settle: int in range(4):
		await process_frame
	await _capture("world-effect-before.png",
		"two players and no effect: what every announced effect looked like")

	# Effect 17, the bee swarm the server sends when a harvest is interrupted.
	app_state.call("_on_packet", 79, PackedByteArray([17, 0x5b, 0]))
	for _settle: int in range(2):
		await process_frame
	_expect((main.get("world_effects") as Array).size() == 1,
		"the effect at one actor is drawn")
	camera.global_position = Vector3(4.0, 5.5, 6.0)
	camera.look_at(Vector3(4.0, 1.0, -4.0), Vector3.UP)
	await _capture("world-effect-at-actor.png",
		"effect 17 at the actor the server named: a harvest interrupted")

	# Effect 2, which the server sends with a second actor: it travelled.
	app_state.call("_on_packet", 79, PackedByteArray([2, 0x5b, 0, 0x4d, 0, 6]))
	var effects: Array = main.get("world_effects") as Array
	var travelled: WorldEffect3D = effects[effects.size() - 1] as WorldEffect3D
	travelled.set_process(false)
	_expect(travelled.power_level == 6 and travelled.flight.power_level == 6,
		"server-stated power survives the full packet to effect path")
	var caster := (main.get("actor_nodes") as Dictionary).get(91) as ReplicatedActor3D
	_expect(caster.combat_presentation.spell_power == 6,
		"caster hand effects use the same power as the projectile")
	_expect(travelled.flight != null and travelled.get_node_or_null("EffectBeam") == null,
		"a targeted effect draws a moving spell rather than a solid bar")
	travelled._process(travelled.release_delay + float(travelled.flight.duration) * 0.5)
	_expect(not travelled.impact_started,
		"the real special-effect packet waits for arrival before target impact")
	# `emitting` is a one-shot trigger that clears as soon as the burst is
	# dispatched, so what is asserted is the burst itself, not the flag.
	var burst: GPUParticles3D = travelled.get_node_or_null(
		"EffectBurst") as GPUParticles3D
	_expect(burst != null and burst.amount > 0 and burst.one_shot
		and burst.process_material != null and burst.draw_pass_1 != null,
		"the effect carries a real particle burst, not only a ring")
	camera.global_position = Vector3(4.0, 5.5, 6.0)
	camera.look_at(Vector3(4.0, 1.0, -4.0), Vector3.UP)
	await _capture("world-effect-between-actors.png",
		"effect 2 from one actor to another, because the server named both")
	travelled._process(float(travelled.flight.duration) * 0.5 + 0.02)
	_expect(travelled.impact_started, "the spell makes contact after traveling")
	await _capture("world-effect-spell-impact.png", "contact follows the spell flight")
	# The production graphics preference suppresses creation of flight geometry.
	var effects_before: int = (main.get("world_effects") as Array).size()
	main.set("_effects_enabled", false)
	app_state.call("_on_packet", 79, PackedByteArray([2, 0x5b, 0, 0x4d, 0]))
	_expect((main.get("world_effects") as Array).size() == effects_before,
		"particles disabled suppresses the entire targeted spell effect")
	main.set("_effects_enabled", true)

	# A real arrow, from the server's own aim-then-fire pair. The effects
	# already on screen are cleared first - they fade on real time, and a
	# headless run gets through far more frames than a second - so the frame
	# shows the arrow rather than the last thing that happened.
	for live: Variant in (main.get("world_effects") as Array):
		if is_instance_valid(live):
			(live as Node).queue_free()
	for _fade: int in range(4):
		await process_frame
	app_state.call("_on_packet", 84, PackedByteArray([0x5b, 0, 0x4d, 0]))
	app_state.call("_on_packet", 86, PackedByteArray([0x5b, 0, 0x4d, 0]))
	# Freeze immediately: flight now scales with distance, and the first bow
	# import can make even a few rendered frames outlive a short flight.
	var shots: Array = main.get("world_effects") as Array
	var arrow: MissileFlight3D = shots[shots.size() - 1] as MissileFlight3D
	if arrow != null:
		arrow.set_process(false)
	for _settle: int in range(3):
		await process_frame
	_expect(arrow != null and arrow.get_node_or_null("Shaft") != null,
		"the arrow is in flight between the two actors")
	# A quarter-second flight is over in a handful of headless frames. The
	# capture advances it to its midpoint so the frame shows the arrow
	# between the two actors rather than at the moment it left the bow.
	arrow._process(arrow.flight_seconds * 0.5)
	await process_frame
	await _capture("world-effect-missile.png",
		"the arrow the server loosed, between the two actors it named")

	# Harvesting is state rather than an event: the glitter lasts the run.
	for live: Variant in (main.get("world_effects") as Array):
		if is_instance_valid(live):
			(live as Node).queue_free()
	app_state.set("local_actor_id", 0x5b)
	var harvesting := PackedByteArray([1, 0xf0, 0x01])
	harvesting.append_array("Reed".to_utf8_buffer())
	harvesting.append(0)
	app_state.call("_on_packet", 237, harvesting)
	for _settle: int in range(20):
		await process_frame
	var sparkle: HarvestSparkle3D = main.get("harvest_sparkle") as HarvestSparkle3D
	_expect(sparkle != null and sparkle.is_following(
		(main.get("actor_nodes") as Dictionary).get(0x5b) as Node3D),
		"the harvesting player glitters")
	camera.global_position = Vector3(4.0, 5.5, 6.0)
	camera.look_at(Vector3(4.0, 1.0, -4.0), Vector3.UP)
	await _capture("world-effect-harvest-sparkle.png",
		"the glitter around a player for as long as they harvest")
	app_state.call("_on_packet", 237, PackedByteArray([0, 0, 0, 0]))
	await process_frame
	_expect(main.get("harvest_sparkle") == null and sparkle.is_stopping(),
		"the glitter stops when the server ends the run")

	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame
	print("rendered world effects: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
