extends SceneTree
## Renders a trail gauntlet package through the client's own world loader and
## environment binder, one screenshot per view in the route's camera-views.json
## (overviews, each section from the arriving road and at the game rig's pitch,
## and approach shots along the road).
##
## ELORIA_TRAIL_ROUTE picks the route (default harrowcrag_gauntlet);
## ELORIA_ARTIFACT_DIR is where the PNGs go.

const GAUNTLETS := "res://../eloria-assets/maps/gauntlets/"
const SCREEN_SIZE := Vector2i(1600, 900)

var _artifacts := ""
var _failures := 0
var _camera: Camera3D
var _sun: DirectionalLight3D
var _world_environment: WorldEnvironment
var _loader: WorldLoader
var _fog_wanted := true

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var route := OS.get_environment("ELORIA_TRAIL_ROUTE")
	if route.is_empty():
		route = "harrowcrag_gauntlet"
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/" + route)
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK, "artifact directory is writable")
	root.size = SCREEN_SIZE

	var stage := Node3D.new()
	root.add_child(stage)
	_world_environment = WorldEnvironment.new()
	_world_environment.environment = Environment.new()
	stage.add_child(_world_environment)
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	_sun.directional_shadow_max_distance = 400.0
	stage.add_child(_sun)
	_camera = Camera3D.new()
	_camera.far = 2000.0
	_camera.current = true
	stage.add_child(_camera)

	_loader = WorldLoader.new()
	_loader.name = "WorldLoader"
	stage.add_child(_loader)
	_loader.load_world(ProjectSettings.globalize_path(GAUNTLETS + route + "/client/world.json"))
	var deadline := Time.get_ticks_msec() + 180000
	while _loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(_loader.world_root != null, route + " GLB imports into the scene")
	if _loader.world_root == null:
		_finish(route)
		return
	_expect(WorldEnvironmentBinder.apply(_loader.manifest, _world_environment, _sun),
		"manifest environment binds through WorldEnvironmentBinder")
	# The game's look pass, as main.gd binds a map outside the continent: the ground paint,
	# the painted sky, the hour's light (ELORIA_TRAIL_MINUTE, default mid-afternoon) and the grade.
	LookGround.paint_bound(_loader.world_root, _loader.manifest)
	LookSky.install(_loader.manifest, _world_environment)
	var minute := float(OS.get_environment("ELORIA_TRAIL_MINUTE")) if OS.has_environment("ELORIA_TRAIL_MINUTE") else 900.0
	DayNightBinder.apply(_loader.manifest, _world_environment, _sun, minute)
	LookGrade.apply(_loader.manifest, _world_environment, _sun)
	LookSky.apply(_loader.manifest, _world_environment, minute)
	_fog_wanted = _world_environment.environment.fog_enabled
	for unused: int in range(4):
		await process_frame

	var views_file := FileAccess.open(ProjectSettings.globalize_path(GAUNTLETS + route + "/source/camera-views.json"),
		FileAccess.READ)
	_expect(views_file != null, "camera-views.json is readable")
	if views_file == null:
		_finish(route)
		return
	var parsed: Variant = JSON.parse_string(views_file.get_as_text())
	var views: Array = (parsed as Dictionary).get("views", [])
	_expect(views.size() >= 8, "the view set covers every section")
	for raw_view: Variant in views:
		var view: Dictionary = raw_view as Dictionary
		await _capture(str(view["id"]), view)
	# What a frame costs at the game camera in the densest sections (renderer timers, not
	# TIME_PROCESS, which a throttled window fakes): ELORIA_TRAIL_BENCH=0 skips it.
	if OS.get_environment("ELORIA_TRAIL_BENCH") != "0":
		var viewport_rid := root.get_viewport_rid()
		RenderingServer.viewport_set_measure_render_time(viewport_rid, true)
		for raw_view: Variant in views:
			var view: Dictionary = raw_view as Dictionary
			if not str(view["id"]).ends_with("-game"):
				continue
			_camera.look_at_from_position(_vector(view["position"]), _vector(view["target"]), Vector3.UP)
			for unused: int in range(10):
				await process_frame
			var gpu := 0.0
			var cpu := 0.0
			var primitives := 0
			for unused: int in range(30):
				await process_frame
				gpu += RenderingServer.viewport_get_measured_render_time_gpu(viewport_rid)
				cpu += RenderingServer.viewport_get_measured_render_time_cpu(viewport_rid)
				primitives = maxi(primitives, int(RenderingServer.viewport_get_render_info(viewport_rid,
					RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME)))
			print("frame %s gpu_ms=%.2f cpu_ms=%.2f primitives=%d" % [view["id"], gpu / 30.0, cpu / 30.0, primitives])
	_finish(route)

func _vector(value: Variant) -> Vector3:
	var values: Array = value as Array
	return Vector3(float(values[0]), float(values[1]), float(values[2]))

func _capture(name: String, view: Dictionary) -> void:
	# a review overview is hundreds of metres out: the map's own fog would hide it
	_world_environment.environment.fog_enabled = not bool(view.get("noFog", false)) and _fog_wanted
	_camera.fov = float(view.get("fov", 50.0))
	_camera.look_at_from_position(_vector(view["position"]), _vector(view["target"]), Vector3.UP)
	for unused: int in range(8):
		await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE, name + ": screenshot size")
	var colors := {}
	for y: int in range(0, image.get_height(), 12):
		for x: int in range(0, image.get_width(), 12):
			colors[image.get_pixel(x, y).to_html()] = true
	_expect(colors.size() >= 64, "%s: screenshot contains scene detail (%d colours)" % [name, colors.size()])
	_expect(image.save_png(_artifacts.path_join(name + ".png")) == OK, "saved " + name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish(route: String) -> void:
	print("rendered ", route, ": ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
