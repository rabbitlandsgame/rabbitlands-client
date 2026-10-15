extends SceneTree
## Renders both Sunmane cave interiors through the client's own world loader,
## environment binder and light-marker binder, capturing an eye-level view in
## every chamber and writing each package's minimap from the exported geometry.
##
## The captures are what a player sees: the same manifest environment, the same
## brazier lights, the same renderer. Nothing here lights the scene by hand.

const INTERIORS := ["sunmane_wind_caves", "sunmane_crystal_hollow"]
const ROOT := "res://../eloria-assets/maps/nymara-regions/interiors/"
const SCREEN_SIZE := Vector2i(1280, 720)
const MINIMAP_SIZE := 512

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/sunmane-caves")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	for identifier: String in INTERIORS:
		await _render(identifier)
	print("rendered Sunmane caves: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

func _render(identifier: String) -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	stage.add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	var camera := Camera3D.new()
	camera.far = 400.0
	camera.current = true
	stage.add_child(camera)
	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	stage.add_child(loader)
	loader.load_world(ProjectSettings.globalize_path(
		ROOT + identifier + "/world.json"))
	var deadline := Time.get_ticks_msec() + 120000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(loader.world_root != null, identifier + " imports"):
		stage.queue_free()
		return
	_expect(WorldEnvironmentBinder.apply(loader.manifest, world_environment, sun),
		identifier + ": manifest environment binds")
	var lights := Node3D.new()
	lights.name = "MapLights"
	stage.add_child(lights)
	var bound := LightMarkerBinder.apply(loader.manifest, lights)
	_expect(bound > 0, "%s: %d brazier lights bound from the manifest"
		% [identifier, bound])
	for unused: int in range(6):
		await process_frame

	for raw: Variant in loader.manifest.data["chambers"]:
		var chamber: Dictionary = raw
		var position: Array = chamber["position"]
		var centre := Vector3(float(position[0]), float(position[1]),
			float(position[2]))
		var radius := float(chamber["radius"])
		# Stand near the chamber wall at eye height and look across the room,
		# which is the view a player walking in actually gets. The eye is put on
		# the side of the chamber furthest from its passages, so a timber set is
		# never right against the lens.
		var heading := _open_heading(loader, chamber)
		var eye := centre + Vector3(cos(heading), 0.0, sin(heading)) * radius * 0.72
		eye.y = centre.y + 1.65
		camera.fov = 62.0
		camera.near = 0.12
		camera.look_at_from_position(eye,
			centre + Vector3(0.0, 1.1, 0.0)
			- Vector3(cos(heading), 0.0, sin(heading)) * radius * 0.35, Vector3.UP)
		await _capture("%s-%s" % [identifier, str(chamber["id"])])

	await _render_minimap(identifier, loader, camera, stage)
	stage.queue_free()
	await process_frame

func _open_heading(loader: WorldLoader, chamber: Dictionary) -> float:
	## The direction from a chamber centre that is furthest from any other
	## chamber, which is the side its passages do not run out of.
	var position: Array = chamber["position"]
	var centre := Vector2(float(position[0]), float(position[2]))
	var best := 0.0
	var best_clearance := -1.0
	for raw: Variant in loader.manifest.data["chambers"]:
		pass
	for step in range(24):
		var angle := TAU * float(step) / 24.0
		var direction := Vector2(cos(angle), sin(angle))
		var nearest := 1e9
		for raw: Variant in loader.manifest.data["chambers"]:
			var other: Dictionary = raw
			if str(other["id"]) == str(chamber["id"]):
				continue
			var other_position: Array = other["position"]
			var offset := Vector2(float(other_position[0]),
				float(other_position[2])) - centre
			if offset.length() < 0.001:
				continue
			nearest = min(nearest, offset.normalized().dot(direction))
		if nearest > -1e8 and -nearest > best_clearance:
			best_clearance = -nearest
			best = angle
	return best

func _render_minimap(identifier: String, loader: WorldLoader, camera: Camera3D,
		stage: Node3D) -> void:
	var minimap: Dictionary = loader.manifest.data["minimap"]
	var world_min: Array = minimap["worldMin"]
	var world_max: Array = minimap["worldMax"]
	var span := float(world_max[0]) - float(world_min[0])
	var previous := root.size
	root.size = Vector2i(MINIMAP_SIZE, MINIMAP_SIZE)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = span
	camera.far = 400.0
	var centre_x := (float(world_min[0]) + float(world_max[0])) * 0.5
	var centre_z := (float(world_min[1]) + float(world_max[1])) * 0.5
	# Looking straight down with -Z toward the top of the image, which is the
	# orientation the manifest transform documents.
	camera.look_at_from_position(Vector3(centre_x, 120.0, centre_z),
		Vector3(centre_x, 0.0, centre_z), Vector3(0.0, 0.0, -1.0))
	# The roof is between the camera and the floor, so it is hidden for the
	# overhead pass exactly as a floor plan omits the ceiling.
	var hidden: Array[Node3D] = []
	for node: Node in loader.world_root.find_children("Structure_CaveRoof*",
			"Node3D", true, false):
		(node as Node3D).visible = false
		hidden.append(node as Node3D)
	for unused: int in range(8):
		await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	_expect(image.get_size() == Vector2i(MINIMAP_SIZE, MINIMAP_SIZE),
		identifier + ": minimap has the declared image size")
	var target := ProjectSettings.globalize_path(
		ROOT + identifier + "/minimap.webp")
	_expect(image.save_webp(target, false) == OK,
		identifier + ": minimap.webp written")
	for node: Node3D in hidden:
		node.visible = true
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	root.size = previous

func _capture(name: String) -> void:
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
	_expect(colors.size() >= 40,
		"%s: screenshot contains scene detail (%d colours)" % [name, colors.size()])
	_expect(image.save_png(_artifacts.path_join(name + ".png")) == OK, "saved " + name)

func _expect(condition: bool, message: String) -> bool:
	if condition:
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
