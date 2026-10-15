extends SceneTree
## Renders the Sunmane Steppe minimap and full-map image from the exported
## geometry, orthographically and axis-aligned, so map pixels and world metres
## have an exact linear relationship the client can invert.

const PACKAGE := "res://../eloria-assets/maps/nymara-regions/sunmane_steppe/"
const MANIFEST := PACKAGE + "world.json"
const SIZE := 1024

var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# Render into an explicitly sized SubViewport: the OS window cannot be
	# relied on to take a square size, and a non-square capture would break the
	# pixels-per-metre relationship the minimap transform depends on.
	var viewport := SubViewport.new()
	viewport.size = Vector2i(SIZE, SIZE)
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)
	var stage := Node3D.new()
	viewport.add_child(stage)

	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	stage.add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = false
	stage.add_child(sun)

	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	stage.add_child(loader)
	loader.load_world(ProjectSettings.globalize_path(MANIFEST))
	var deadline := Time.get_ticks_msec() + 120000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(loader.world_root != null, "world loads for minimap capture")
	if loader.world_root == null:
		_finish()
		return
	WorldEnvironmentBinder.apply(loader.manifest, world_environment, sun)
	# Flat, shadowless top light: a minimap should read as a plan, not a render.
	sun.rotation_degrees = Vector3(-72, 150, 0)
	sun.light_energy = 0.75
	sun.light_color = Color("fff4e2")
	var environment := world_environment.environment
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("14313c")
	environment.fog_enabled = false
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("b9c3cc")
	environment.ambient_light_energy = 0.42
	# Linear, slightly under-exposed: a plan should hold its mid-tones, and the
	# filmic curve used for gameplay washes a top-down view to white.
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	environment.tonemap_exposure = 0.78
	environment.tonemap_white = 1.0

	var bounds: Dictionary = loader.manifest.data["asset"]["bounds"]
	var minimum: Array = bounds["min"]
	var maximum: Array = bounds["max"]
	var span: float = float(maximum[0]) - float(minimum[0])
	var centre := Vector3((float(minimum[0]) + float(maximum[0])) * 0.5, 0.0,
		(float(minimum[2]) + float(maximum[2])) * 0.5)

	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = span
	camera.near = 1.0
	camera.far = 900.0
	camera.current = true
	stage.add_child(camera)
	# Looking straight down with -Z up in the image, so image +Y is world +Z and
	# north (-Z) is at the top of the picture.
	camera.global_position = centre + Vector3(0, 400, 0)
	camera.rotation_degrees = Vector3(-90, 0, 0)

	for unused: int in range(12):
		await process_frame
	RenderingServer.force_draw(false)
	viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	await process_frame
	RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	_expect(image.get_size() == Vector2i(SIZE, SIZE), "minimap render is square")

	var directory := ProjectSettings.globalize_path(PACKAGE)
	var minimap := image.duplicate() as Image
	minimap.resize(int(round(span)), int(round(span)), Image.INTERPOLATE_LANCZOS)
	_expect(minimap.save_webp(directory.path_join("minimap.webp"), true, 0.92) == OK,
		"saved minimap.webp")
	var full := image.duplicate() as Image
	_expect(full.save_webp(directory.path_join("full-map.webp"), true, 0.95) == OK,
		"saved full-map.webp")
	# A half-size preview for reviewers, beside the two runtime images.
	var preview := image.duplicate() as Image
	preview.resize(512, 512, Image.INTERPOLATE_LANCZOS)
	_expect(preview.save_webp(directory.path_join("minimap-preview.webp"), true, 0.9) == OK,
		"saved minimap-preview.webp")
	print("minimap span=%.1f m pixelsPerMetre=%.4f" % [span, float(minimap.get_width()) / span])
	_finish()

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("sunmane minimap: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
