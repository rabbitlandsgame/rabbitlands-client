extends SceneTree

## Renders each Four Gates interior through the production WorldLoader with its
## own manifest environment, so the lamps, hearths and crystal fittings that are
## the only light in the room are actually the light in the shot.

const SIZE := Vector2i(1400, 800)

const InteriorCutawayScript := preload("res://src/world/interior_cutaway.gd")

const ROOMS := [
	["four-gates-lantern-row", Vector3(0.0, 3.9, 6.2), Vector3(0.0, 1.5, -6.6), 66.0],
	["four-gates-stormglass-house", Vector3(3.6, 3.0, 4.4), Vector3(-3.0, 1.2, -3.4), 66.0],
	["four-gates-mirrorsmith-forge", Vector3(4.6, 2.6, 4.2), Vector3(-1.0, 1.1, -4.6), 70.0],
	["four-gates-reedworks", Vector3(4.6, 3.2, 5.0), Vector3(-3.6, 1.2, -3.6), 66.0],
	["four-gates-ferrymans-rest", Vector3(4.4, 2.7, 4.6), Vector3(-3.4, 1.1, -3.6), 68.0],
	["four-gates-deposit-four-keys", Vector3(3.8, 2.8, 4.6), Vector3(-3.2, 1.5, -3.4), 70.0],
]

var _failures := 0
var _artifacts := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/interiors")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SIZE
	for room: Array in ROOMS:
		await _render(str(room[0]), room[1] as Vector3, room[2] as Vector3,
			float(room[3]))
	print("four gates interiors: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

func _render(ident: String, eye: Vector3, look: Vector3, fov: float) -> void:
	var scene: Node3D = (load("res://src/dev/world_validation.tscn") as PackedScene
		).instantiate() as Node3D
	root.add_child(scene)
	var loader: WorldLoader = scene.get_node("WorldLoader") as WorldLoader
	loader.load_world(ProjectSettings.globalize_path(
		"res://../eloria-assets/maps/%s/world.json" % ident))
	var deadline: int = Time.get_ticks_msec() + 90000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if loader.world_root == null:
		_fail(ident + ": did not load")
		scene.queue_free()
		return
	_expect(loader.manifest.warnings.is_empty(),
		ident + ": manifest has no warnings")
	var applied: bool = WorldEnvironmentBinder.apply(loader.manifest,
		scene.get_node("Environment") as WorldEnvironment,
		scene.get_node("Sun") as DirectionalLight3D, loader.world_root)
	_expect(applied, ident + ": manifest environment applied")
	var lamps: int = loader.world_root.get_tree().get_nodes_in_group(
		WorldEnvironmentBinder.MANIFEST_LIGHT_GROUP).size()
	_expect(lamps > 0, "%s: %d manifest lights spawned" % [ident, lamps])
	var walk: Node = loader.world_root.find_child("Floor_Deck", true, false)
	_expect(walk != null and walk.get_node_or_null("Floor_Deck_WalkSurfaceCollision") != null,
		ident + ": floor carries the navigation surface")
	(scene.get_node("UI") as CanvasLayer).visible = false
	var camera: Camera3D = scene.get_node("Camera") as Camera3D
	camera.fov = fov
	camera.near = 0.1
	camera.far = 400.0
	camera.global_position = eye
	camera.look_at(look, Vector3.UP)
	await _shoot(camera, ident + ".png")

	# Second pass: the framing the player actually gets -- the manifest's own
	# camera profile with the ceiling and the near wall cut away. Without the
	# cutaway the isometric rig sits above the roof and renders nothing else.
	var cutaway: RefCounted = InteriorCutawayScript.new()
	var hidden: int = cutaway.configure(loader.manifest, loader.world_root)
	_expect(hidden > 0, "%s: cutaway took control of %d nodes" % [ident, hidden])
	cutaway.update(0.0, true)
	var ceiling: Node3D = loader.world_root.find_child(
		"Shell_Ceiling", true, false) as Node3D
	_expect(ceiling != null and not ceiling.visible,
		ident + ": the ceiling is cut away")
	var near_wall: Node3D = loader.world_root.find_child(
		"Shell_Wall_South", true, false) as Node3D
	var far_wall: Node3D = loader.world_root.find_child(
		"Shell_Wall_North", true, false) as Node3D
	_expect(near_wall != null and not near_wall.visible,
		ident + ": the wall between the camera and the room is cut away")
	_expect(far_wall != null and far_wall.visible,
		ident + ": the far wall is still drawn")
	_expect(_wall_bodies(loader.world_root) >= 4,
		ident + ": all four walls keep their collision while cut away")

	var block: Dictionary = loader.manifest.data.get("camera", {}) as Dictionary
	var pitch: float = deg_to_rad(float(block.get("pitchDegrees", -48.0)))
	var span: float = float(block.get("distance", 12.0))
	var focus := Vector3(0.0, 0.9, _spawn_z(loader.manifest))
	camera.fov = 60.0
	camera.global_position = focus + Vector3(0.0, -sin(pitch), cos(pitch)) * span
	camera.look_at(focus + Vector3.UP * 1.2, Vector3.UP)
	await _shoot(camera, ident + "-camera.png")

	cutaway.reset()
	scene.queue_free()
	await process_frame

## Where the player arrives, so the rig shot is framed the way the map opens.
static func _spawn_z(manifest: WorldManifest) -> float:
	var points: Variant = manifest.data.get("spawnPoints", [])
	if points is Array and not (points as Array).is_empty():
		var first: Dictionary = (points as Array)[0] as Dictionary
		var position: Variant = first.get("position", [])
		if position is Array and (position as Array).size() >= 3:
			return float((position as Array)[2])
	return 0.0

## A cut-away wall must still be solid, so count the static bodies the loader
## built for the shell regardless of whether their meshes are drawn.
static func _wall_bodies(world_root: Node3D) -> int:
	var found: int = 0
	for side: String in ["North", "South", "East", "West"]:
		var wall: Node3D = world_root.find_child(
			"Shell_Wall_" + side, true, false) as Node3D
		if wall == null:
			continue
		for child: Node in wall.get_children():
			if child is StaticBody3D:
				found += 1
				break
	return found

func _shoot(camera: Camera3D, filename: String) -> void:
	for _f: int in range(6):
		await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	_expect(image.save_png(_artifacts.path_join(filename)) == OK,
		"saved " + filename)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _fail(message: String) -> void:
	_failures += 1
	push_error("FAIL: " + message)
