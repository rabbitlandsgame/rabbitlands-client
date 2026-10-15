extends SceneTree

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifact_directory := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path("res://test-artifacts/four-gates")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	var scene_resource: Resource = load("res://src/dev/world_validation.tscn")
	_expect(scene_resource is PackedScene, "Four Gates validation scene loads")
	if not scene_resource is PackedScene:
		await _finish()
		return
	var scene: Node3D = (scene_resource as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	var loader: WorldLoader = scene.get_node("WorldLoader") as WorldLoader
	var ready: Callable = func() -> bool:
		return loader.world_root != null
	_expect(await _wait_for(ready, 30.0), "Four Gates GLB imports into the rendered scene")
	if loader.world_root == null:
		await _finish()
		return

	var environment_node: WorldEnvironment = scene.get_node("Environment") as WorldEnvironment
	var sun_node: DirectionalLight3D = scene.get_node("Sun") as DirectionalLight3D
	_expect(WorldEnvironmentBinder.apply(loader.manifest, environment_node, sun_node),
		"manifest environment applied to the rendered scene")
	(scene.get_node("UI") as CanvasLayer).visible = false

	var camera: Camera3D = scene.get_node("Camera") as Camera3D
	camera.position = Vector3(620.0, 610.0, 720.0)
	camera.look_at(Vector3(0.0, 15.0, 0.0), Vector3.UP)
	await _capture("four-gates-aerial.png")
	camera.position = Vector3(0.0, 155.0, 275.0)
	camera.look_at(Vector3(0.0, 42.0, 20.0), Vector3.UP)
	await _capture("four-gates-gameplay.png")
	camera.position = Vector3(145.0, 110.0, 165.0)
	camera.look_at(Vector3(0.0, 40.0, 0.0), Vector3.UP)
	await _capture("four-gates-central-plaza-detail.png")
	camera.position = Vector3(118.0, 125.0, 455.0)
	camera.look_at(Vector3(0.0, 70.0, 345.0), Vector3.UP)
	await _capture("four-gates-south-gate-detail.png")
	camera.position = Vector3(-285.0, 115.0, -10.0)
	camera.look_at(Vector3(-125.0, 40.0, -92.0), Vector3.UP)
	await _capture("four-gates-market-detail.png")
	camera.position = Vector3(285.0, 115.0, 465.0)
	camera.look_at(Vector3(170.0, 5.0, 365.0), Vector3.UP)
	await _capture("four-gates-waterfall-detail.png")
	await _finish()

func _wait_for(predicate: Callable, timeout_seconds: float) -> bool:
	var deadline_msec: int = Time.get_ticks_msec() + roundi(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline_msec:
		if bool(predicate.call()):
			return true
		await process_frame
	return bool(predicate.call())

func _capture(file_name: String) -> void:
	for unused_frame: int in range(6):
		await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		"rendered screenshot has the reference dimensions")
	var sampled_colors: Dictionary = {}
	for y: int in range(0, image.get_height(), 24):
		for x: int in range(0, image.get_width(), 24):
			sampled_colors[image.get_pixel(x, y).to_html()] = true
	_expect(sampled_colors.size() >= 32, "rendered screenshot contains map detail")
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"saved " + file_name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("rendered Four Gates map: ", "PASS" if _failures == 0 else "FAIL")
	# Four Gates streams its framed chunks on a worker; quitting under a live
	# one crashes the process at exit (ContinentChunkStream.drain_workers).
	await ContinentChunkStream.drain_workers(self)
	quit(_failures)
