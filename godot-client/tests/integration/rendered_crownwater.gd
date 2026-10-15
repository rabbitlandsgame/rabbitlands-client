extends SceneTree
## Renders the Crownwater package through the client's own world loader and
## environment binder, capturing one screenshot per concept-art viewpoint.
##
## Framings come from `camera-views.json`, which the region build emits from
## `source/views.py` - the same table that drives the offline preview renderer -
## so an offline preview and a real client frame are the same shot and can be
## compared honestly.
##
## Unlike Amberwood's, Crownwater's reference captures are real client frames:
## this harness is what makes that claim true, and anything it does not produce
## is labelled an offline preview in the comparison report.

const PACKAGE := "res://../eloria-assets/maps/nymara-regions/crownwater/"
const MANIFEST := PACKAGE + "world.json"
const VIEWS := PACKAGE + "camera-views.json"
const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0
var _camera: Camera3D
var _sun: DirectionalLight3D
var _world_environment: WorldEnvironment
var _loader: WorldLoader

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/crownwater")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var stage := Node3D.new()
	root.add_child(stage)
	_world_environment = WorldEnvironment.new()
	_world_environment.environment = Environment.new()
	stage.add_child(_world_environment)
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	stage.add_child(_sun)
	_camera = Camera3D.new()
	# The lagoon plane runs 420 m past the authored terrain so the horizon is
	# water; the far plane has to reach it or the sea ends in mid-air.
	_camera.far = 1600.0
	_camera.current = true
	stage.add_child(_camera)

	_loader = WorldLoader.new()
	_loader.name = "WorldLoader"
	stage.add_child(_loader)
	_loader.load_world(ProjectSettings.globalize_path(MANIFEST))
	var deadline := Time.get_ticks_msec() + 180000
	while _loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(_loader.world_root != null, "Crownwater GLB imports into the scene")
	if _loader.world_root == null:
		_finish()
		return
	_expect(WorldEnvironmentBinder.apply(_loader.manifest, _world_environment, _sun),
		"manifest environment binds through WorldEnvironmentBinder")
	for unused: int in range(8):
		await process_frame

	var views_file := FileAccess.open(ProjectSettings.globalize_path(VIEWS),
		FileAccess.READ)
	_expect(views_file != null, "camera-views.json is readable")
	if views_file == null:
		_finish()
		return
	var parsed: Variant = JSON.parse_string(views_file.get_as_text())
	_expect(parsed is Dictionary, "camera-views.json parses")
	var views: Array = (parsed as Dictionary).get("views", [])
	_expect(views.size() >= 21, "view set covers every reference panel")

	var panels_seen := {}
	for raw_view: Variant in views:
		var view: Dictionary = raw_view as Dictionary
		if view.get("panel") != null:
			panels_seen[int(view["panel"])] = true
		await _capture(str(view["id"]), view)
	_expect(panels_seen.size() == 10,
		"all ten detail-board panels have a framing (%d)" % panels_seen.size())
	_finish()

func _vector(value: Variant) -> Vector3:
	var values: Array = value as Array
	return Vector3(float(values[0]), float(values[1]), float(values[2]))

func _capture(name: String, view: Dictionary) -> void:
	_camera.fov = float(view.get("fov", 50.0))
	var eye := _vector(view["position"])
	var target := _vector(view["target"])
	if eye.distance_to(target) < 0.05:
		_expect(false, name + ": degenerate framing, eye is on the target")
		return
	_camera.look_at_from_position(eye, target, Vector3.UP)
	for unused: int in range(8):
		await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		name + ": screenshot has the reference dimensions")
	# A frame that is all sky, or all water, is a framing bug rather than a
	# render bug, and it is invisible unless something counts colours.
	var colors := {}
	for y: int in range(0, image.get_height(), 12):
		for x: int in range(0, image.get_width(), 12):
			colors[image.get_pixel(x, y).to_html()] = true
	_expect(colors.size() >= 64, "%s: screenshot contains scene detail (%d colours)" % [
		name, colors.size()])
	_expect(image.save_png(_artifacts.path_join(name + ".png")) == OK, "saved " + name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("rendered Crownwater: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
