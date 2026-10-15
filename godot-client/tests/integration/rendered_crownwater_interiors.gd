extends SceneTree
## Renders Crownwater's four interiors through the client's own world loader,
## capturing one screenshot per authored space.
##
## The region harness (`rendered_crownwater.gd`) reads its framings from a
## `camera-views.json` the region build emits. Interiors do not have one: each
## package's `world.json` already lists its spaces with extents and floor
## heights, so the framings are derived here from the spaces themselves. That
## keeps a new room automatically covered instead of needing a hand-written view.
##
## Every image these produce is a real client frame, not an offline preview.

## The four insides now share ONE map with blackspace between them, so there is
## one package and its sections are read from the manifest.
const PACKAGES := ["crownwater_insides"]
const ROOT := "res://../eloria-assets/maps/nymara-regions/interiors/"
const SCREEN_SIZE := Vector2i(1280, 720)
const EYE := 1.7

var _artifacts := ""
var _failures := 0
var _camera: Camera3D
var _sun: DirectionalLight3D
var _world_environment: WorldEnvironment
var _stage: Node3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/crownwater-interiors")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	for package: String in PACKAGES:
		await _render_package(package)
	_finish()

func _render_package(package: String) -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	_world_environment = WorldEnvironment.new()
	_world_environment.environment = Environment.new()
	_stage.add_child(_world_environment)
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	_stage.add_child(_sun)
	_camera = Camera3D.new()
	_camera.far = 400.0
	_camera.near = 0.1
	_camera.current = true
	_stage.add_child(_camera)

	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	_stage.add_child(loader)
	var manifest_path := ProjectSettings.globalize_path(
		ROOT + package + "/world.json")
	loader.load_world(manifest_path)
	var deadline := Time.get_ticks_msec() + 120000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(loader.world_root != null, package + ": GLB imports into the scene")
	if loader.world_root == null:
		_stage.queue_free()
		return
	# The FOUR-argument form. Without a light parent the binder applies sky,
	# sun and fog but never spawns the manifest's own point lights - and an
	# interior lit only by a directional sun it has a ceiling against is black.
	# The first run of this harness produced eight near-unreadable frames for
	# exactly that reason.
	_expect(WorldEnvironmentBinder.apply(loader.manifest, _world_environment,
			_sun, _stage),
		package + ": manifest environment and lights bind")
	var lights := _stage.get_tree().get_nodes_in_group(
		WorldEnvironmentBinder.MANIFEST_LIGHT_GROUP).size()
	_expect(lights > 0, "%s: manifest spawned %d lights" % [package, lights])
	for unused: int in range(6):
		await process_frame

	var spaces: Variant = loader.manifest.data.get("spaces")
	if spaces is not Dictionary or (spaces as Dictionary).is_empty():
		_expect(false, package + ": manifest lists no spaces to frame")
		_stage.queue_free()
		return

	# Every section's arrival, so a section that failed to place is visible as a
	# black frame rather than being lost among the rooms.
	var sections: Variant = loader.manifest.data.get("sections", [])
	if sections is Array:
		for raw: Variant in sections as Array:
			var section: Dictionary = raw as Dictionary
			var arrival: Array = section["arrival"] as Array
			var at := Vector3(float(arrival[0]), float(arrival[1]),
				float(arrival[2]))
			await _capture_at("section-" + str(section["id"]),
				at + Vector3(0.0, EYE, 0.0),
				at + Vector3(6.0, EYE + 1.0, 6.0), 66.0)

	var count := 0
	for key: Variant in (spaces as Dictionary).keys():
		var space: Dictionary = (spaces as Dictionary)[key] as Dictionary
		if not _framable(space):
			continue
		await _capture(package + "-" + str(key), space)
		count += 1
	# One framable space is correct for the campanile, which is a single 26 m
	# shaft by design; requiring three was an assumption about room count, not a
	# contract. What matters is that every framable space got a frame.
	_expect(count >= 1, "%s: framed %d spaces" % [package, count])

	# A tower is not described by one waist-height shot. Three explicit extra
	# framings walk it: the foot of the stair, the ringing floor and the belfry.
	if package == "crownwater_insides":
		for entry: Array in [
				["campanile-foot", Vector3(56.8, 1.7, 296.8), Vector3(62.4, 6.0, 302.4), 66.0],
				["campanile-ringing-floor", Vector3(57.0, 21.2, 297.0), Vector3(60.0, 24.0, 300.0), 62.0],
				["campanile-belfry", Vector3(56.8, 27.4, 296.8), Vector3(60.6, 23.5, 300.6), 70.0]]:
			await _capture_at(package + "-" + str(entry[0]),
				entry[1] as Vector3, entry[2] as Vector3, float(entry[3]))
	_stage.queue_free()
	await process_frame

func _framable(space: Dictionary) -> bool:
	# Passages are recorded as spaces too, and a 3 m wide run makes a poor
	# photograph; frame the rooms.
	var width: float = float(space.get("x1", 0.0)) - float(space.get("x0", 0.0))
	var depth: float = float(space.get("z1", 0.0)) - float(space.get("z0", 0.0))
	return minf(width, depth) >= 6.0

func _capture(name: String, space: Dictionary) -> void:
	var x0: float = float(space["x0"])
	var x1: float = float(space["x1"])
	var z0: float = float(space["z0"])
	var z1: float = float(space["z1"])
	var floor_y: float = float(space["floor"])
	var height: float = float(space.get("height", 4.0))
	var centre := Vector3((x0 + x1) * 0.5, floor_y, (z0 + z1) * 0.5)

	# Stand in a corner at eye height, looking at the far upper corner. A camera
	# at the centre of a room sees its own walls; a corner sees the volume.
	var inset := 1.6
	var eye := Vector3(x0 + inset, floor_y + EYE, z0 + inset)
	var target := Vector3(centre.x, floor_y + minf(height * 0.5, 3.0), centre.z)
	if eye.distance_to(target) < 1.5:
		eye = centre + Vector3(0.0, floor_y + height * 0.6, 0.0)
	await _capture_at(name, eye, target, 62.0)

func _capture_at(name: String, eye: Vector3, target: Vector3, fov: float) -> void:
	_camera.fov = fov
	_camera.look_at_from_position(eye, target, Vector3.UP)
	for unused: int in range(6):
		await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		name + ": screenshot has the reference dimensions")
	# An interior that renders as one flat colour is a lighting or a camera bug,
	# and it is invisible unless something counts.
	var colors := {}
	for y: int in range(0, image.get_height(), 12):
		for x: int in range(0, image.get_width(), 12):
			colors[image.get_pixel(x, y).to_html()] = true
	_expect(colors.size() >= 24,
		"%s: frame contains scene detail (%d colours)" % [name, colors.size()])
	_expect(image.save_png(_artifacts.path_join(name + ".png")) == OK,
		"saved " + name)

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("rendered Crownwater interiors: ",
		"PASS" if _failures == 0 else "FAIL")
	quit(_failures)
