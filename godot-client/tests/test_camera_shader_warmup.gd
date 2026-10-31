extends SceneTree

const Warmup := preload("res://src/world/camera_shader_warmup.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var source := Camera3D.new()
	world.add_child(source)
	source.position = Vector3(0, 12, 8)
	source.look_at(Vector3.ZERO)
	source.fov = 61.0
	source.near = 0.5
	source.cull_mask = 3
	source.make_current()
	var original := source.global_transform
	var warm := Warmup.new()
	expect(warm.begin(world, source, Vector3.ZERO), "starts for the current gameplay camera")
	expect(root.get_camera_3d() != source and source.global_transform == original,
		"temporary camera draws without changing the player's framing")
	var camera: Camera3D = root.get_camera_3d()
	expect(camera.fov == source.fov and camera.near == source.near and camera.cull_mask == source.cull_mask,
		"warm-up uses the gameplay camera's projection and visual layers")
	var before := camera.global_transform
	warm.advance(warm._last_draw)
	expect(camera.global_transform == before and warm._view == 0, "skipped draws do not advance warm-up")
	var first := warm._last_draw
	for view: int in range(1, Warmup.PITCHES.size() * (360 / Warmup.YAW_STEP) + 1):
		warm.advance(first + view * Warmup.FRAMES_PER_VIEW)
	expect(not warm.active() and root.get_camera_3d() == source,
		"completion restores the gameplay camera")
	expect(source.global_transform == original and warm.completed(world, Vector3.ZERO),
		"completion retains framing and records the warmed arrival")
	expect(not warm.begin(world, source, Vector3.ZERO), "same arrival does not warm repeatedly")
	var destination := Vector3(100, 0, 0)
	expect(warm.begin(world, source, destination), "far teleport on the same map warms its new scenery")
	warm.cancel()
	expect(root.get_camera_3d() == source and not warm.completed(world, destination),
		"cancellation restores the camera without marking unseen views complete")
	expect(warm.begin(world, source, destination), "cancelled work can retry")
	var cutscene := Camera3D.new()
	world.add_child(cutscene)
	cutscene.make_current()
	warm.advance(warm._last_draw + 2)
	expect(not warm.active() and root.get_camera_3d() == cutscene,
		"cutscene takeover cancels without stealing its camera")
	source.make_current()
	expect(warm.begin(world, source, destination), "starts after a camera takeover ends")
	warm._started = Time.get_ticks_msec() - Warmup.LIMIT_MSEC - 1
	warm.advance()
	expect(not warm.active() and root.get_camera_3d() == source,
		"time limit cannot strand the arrival on the temporary camera")
	world.free()
	warm.cancel()
	await process_frame
	await _small_viewport()
	print("camera shader warmup tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)

func _small_viewport() -> void:
	var previous_mode := OS.get_environment("ELORIA_CAMERA_WARMUP_VIEWPORT")
	var previous_uncap := OS.get_environment("ELORIA_CAMERA_WARMUP_UNCAP")
	OS.set_environment("ELORIA_CAMERA_WARMUP_VIEWPORT", "small")
	OS.set_environment("ELORIA_CAMERA_WARMUP_UNCAP", "1")
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1280, 720)
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var source := Camera3D.new()
	world.add_child(source)
	source.position = Vector3(0, 12, 8)
	source.look_at(Vector3.ZERO)
	source.make_current()
	var cap := Engine.max_fps
	Engine.max_fps = 60
	var warm := Warmup.new()
	expect(warm.begin(world, source, Vector3.ZERO), "offscreen warm-up starts")
	expect(Engine.max_fps == 0 and viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"offscreen warm-up removes the cap and suspends full-resolution 3D rendering")
	expect(viewport.get_camera_3d() == source and warm._viewport.world_3d == source.get_world_3d(),
		"offscreen camera shares the world without taking over the gameplay camera")
	expect(warm._viewport.size == Vector2i(192, 108) and warm._viewport.mesh_lod_threshold == 0.0,
		"small viewport preserves aspect and retains full mesh formats")
	warm.cancel()
	expect(Engine.max_fps == 60 and viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"cancellation restores the frame cap and gameplay rendering")
	expect(warm.begin(world, source, Vector3.ZERO), "offscreen warm-up can restart")
	var cutscene := Camera3D.new()
	world.add_child(cutscene)
	cutscene.make_current()
	warm.advance(warm._last_draw + 2)
	expect(not warm.active() and viewport.get_camera_3d() == cutscene and Engine.max_fps == 60,
		"offscreen cancellation preserves a cutscene takeover and restores the cap")
	source.make_current()
	expect(warm.begin(world, source, Vector3.ZERO), "offscreen completion can be tested after cancellation")
	var first := warm._last_draw
	for view: int in range(1, Warmup.PITCHES.size() * (360 / Warmup.YAW_STEP) + 1):
		warm.advance(first + view * Warmup.FRAMES_PER_VIEW)
	expect(not warm.active() and Engine.max_fps == 60 and viewport.get_camera_3d() == source
		and viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"offscreen completion restores the frame cap, gameplay camera and render updates")
	expect(warm.begin(world, source, Vector3(100, 0, 0)), "offscreen warm-up starts at a new destination")
	source.free()
	warm.advance()
	expect(not warm.active() and Engine.max_fps == 60
		and viewport.render_target_update_mode == SubViewport.UPDATE_ALWAYS,
		"destroying the source camera still restores its surviving viewport and frame cap")
	viewport.free()
	await process_frame
	Engine.max_fps = cap
	OS.set_environment("ELORIA_CAMERA_WARMUP_VIEWPORT", previous_mode)
	OS.set_environment("ELORIA_CAMERA_WARMUP_UNCAP", previous_uncap)
