extends SceneTree
## Renders the Sunmane Steppe package through the client's own world loader and
## environment binder, capturing one screenshot per concept-art viewpoint.
##
## Framings come from `camera-views.json`, which is derived from the exported
## landmark positions using the client's isometric rig convention, so every
## capture is a view a player can actually reach in game.

const PACKAGE := "res://../eloria-assets/maps/nymara-regions/sunmane_steppe/"
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
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/sunmane-steppe")
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
	_camera.far = 900.0
	_camera.current = true
	stage.add_child(_camera)

	_loader = WorldLoader.new()
	_loader.name = "WorldLoader"
	stage.add_child(_loader)
	_loader.load_world(ProjectSettings.globalize_path(MANIFEST))
	var deadline := Time.get_ticks_msec() + 120000
	while _loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(_loader.world_root != null, "Sunmane Steppe GLB imports into the scene")
	if _loader.world_root == null:
		_finish()
		return
	_expect(WorldEnvironmentBinder.apply(_loader.manifest, _world_environment, _sun),
		"manifest environment binds through WorldEnvironmentBinder")

	# Ambient livestock come from the same runtime path the client uses.
	var population := AmbientPopulation.new()
	population.name = "AmbientPopulation"
	stage.add_child(population)
	for unused: int in range(4):
		await physics_frame
	var spawned := population.populate(_loader.manifest,
		stage.get_world_3d().direct_space_state)
	_expect(spawned > 0, "ambient population spawned %d animals" % spawned)
	for unused: int in range(4):
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
	_expect(views.size() >= 15, "view set covers every reference panel")

	for raw_view: Variant in views:
		var view: Dictionary = raw_view as Dictionary
		await _capture(str(view["id"]), view)

	_apply_variant("golden-hour")
	for raw_view: Variant in views:
		var view: Dictionary = raw_view as Dictionary
		if bool(view.get("golden", false)):
			await _capture("golden-" + str(view["id"]), view)
	_finish()

func _apply_variant(name: String) -> void:
	var environment: Variant = _loader.manifest.data.get("environment", {})
	if environment is not Dictionary:
		return
	var variants: Variant = (environment as Dictionary).get("variants", {})
	if variants is not Dictionary or not (variants as Dictionary).has(name):
		return
	var merged: Dictionary = (environment as Dictionary).duplicate(true)
	merged.merge((variants as Dictionary)[name] as Dictionary, true)
	var shim := WorldManifest.new()
	shim.data = {"environment": merged}
	WorldEnvironmentBinder.apply(shim, _world_environment, _sun)

func _vector(value: Variant) -> Vector3:
	var values: Array = value as Array
	return Vector3(float(values[0]), float(values[1]), float(values[2]))

func _capture(name: String, view: Dictionary) -> void:
	_camera.fov = float(view.get("fov", 50.0))
	_camera.look_at_from_position(_vector(view["position"]), _vector(view["target"]),
		Vector3.UP)
	for unused: int in range(8):
		await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		name + ": screenshot has the reference dimensions")
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
	print("rendered Sunmane Steppe: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
