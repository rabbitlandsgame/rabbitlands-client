extends SceneTree
## What a player sees of the marker under their character while they run.
##
## Whitehorn Range is the region the flicker was reported on, and this walks a
## selected actor across it through the client's own world loader, camera rig
## and actor, counting the marker's pixels twice at every step: once as the
## depth buffer leaves it, and once with the depth test off, which is the whole
## marker. The share between them is how much of it the ground is eating, and
## the way that share used to jump from step to step is the flicker itself.
##
## Only the terrain is left standing. A rock parked between the camera and the
## marker hides part of it for a good reason; the ground the marker is lying on
## should not.

const PACKAGE := "res://../eloria-assets/maps/nymara-regions/whitehorn_range/"
const MANIFEST := PACKAGE + "world.json"
const SCREEN_SIZE := Vector2i(1280, 720)
## A stretch of open sloping snow, away from the trail's props.
const WALK_START := Vector2(56.0, -55.18)
const WALK_STEPS := 24
const WALK_STEP := 0.15
## The rig the client frames play with.
const CAMERA_DISTANCE := 26.0
const CAMERA_PITCH := -60.0

var _failures := 0
var _artifacts := ""
var _camera: Camera3D
var _loader: WorldLoader
var _actor: ReplicatedActor3D
var _ring: MeshInstance3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/ground-markers")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN_SIZE

	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.light_energy = 1.15
	stage.add_child(sun)
	_camera = Camera3D.new()
	_camera.fov = 50.0
	_camera.near = 1.0
	_camera.far = 1800.0
	_camera.current = true
	stage.add_child(_camera)
	_loader = WorldLoader.new()
	_loader.name = "WorldLoader"
	stage.add_child(_loader)
	_loader.load_world(ProjectSettings.globalize_path(MANIFEST))
	var deadline := Time.get_ticks_msec() + 180000
	while _loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(_loader.world_root != null, "Whitehorn Range loads"):
		await _finish()
		return
	WorldEnvironmentBinder.apply(_loader.manifest, environment, sun)
	for node: Node in _loader.world_root.find_children(
			"*", "GeometryInstance3D", true, false):
		if not (node.name.begins_with("Terrain_") or node.name.begins_with("Walk_")):
			(node as GeometryInstance3D).visible = false
	for unused: int in range(6):
		await physics_frame
		await process_frame

	var adapter: CoordinateAdapter = _loader.coordinate_adapter
	_actor = ReplicatedActor3D.new()
	stage.add_child(_actor)
	_actor.configure({"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"actor_type": 1, "kind": 1, "name": "Runner", "health": 10,
		"max_health": 10}, adapter, {}, {})
	# The model and its nameplate are not what is being measured, and both
	# stand over the marker from this angle.
	for hidden_name: String in ["MissingModelFallback", "Nameplate", "MapDot"]:
		var hidden: Node3D = _actor.get_node_or_null(hidden_name) as Node3D
		if hidden != null:
			hidden.visible = false
	_actor.set_selected(true)
	_ring = _actor.get_node_or_null("SelectionRing") as MeshInstance3D
	if not _expect(_ring != null, "the selected actor carries a ground marker"):
		await _finish()
		return

	var shares: Array[float] = []
	var space: PhysicsDirectSpaceState3D = stage.get_world_3d().direct_space_state
	# One throwaway frame: the first draw after a region loads is the one the
	# renderer spends uploading it, and it comes back empty.
	_frame_on(Vector3(WALK_START.x, 0.0, WALK_START.y))
	await _shoot()
	for step: int in WALK_STEPS:
		var x: float = WALK_START.x + WALK_STEP * float(step)
		var z: float = WALK_START.y
		var ground: Variant = GroundDrape.surface_height(space, x, z)
		if not _expect(ground != null, "step %d stands on the walk surface" % step):
			continue
		# The actor holds itself on the position the server gave it every
		# physics frame, so a walk is driven by moving that.
		_actor.server_target = Vector3(x, float(ground) + 0.02, z)
		_actor.global_position = _actor.server_target
		await physics_frame
		_actor.call("_level_selection_ring")
		_frame_on(Vector3(x, float(ground), z))
		var material: BaseMaterial3D = _ring.material_override as BaseMaterial3D
		material.no_depth_test = false
		var drawn_image: Image = await _shoot()
		var drawn: int = _marker_pixels(drawn_image)
		material.no_depth_test = true
		var whole_image: Image = await _shoot()
		var whole: int = _marker_pixels(whole_image)
		material.no_depth_test = false
		if not _expect(whole > 40, "step %d draws a marker at all (%d px)" % [
				step, whole]):
			continue
		var share: float = float(drawn) / float(whole)
		shares.append(share)
		print("ground_marker step=%d x=%.2f drawn=%d whole=%d share=%.3f" % [
			step, x, drawn, whole, share])
		if step == WALK_STEPS / 2:
			# The depth-tested frame, which is the one a player would be
			# looking at, so the evidence shows the marker they get.
			drawn_image.save_png(_artifacts.path_join("marker_midwalk.png"))

	var lowest := 1.0
	var biggest_jump := 0.0
	for index: int in shares.size():
		lowest = minf(lowest, shares[index])
		if index > 0:
			biggest_jump = maxf(biggest_jump,
				absf(shares[index] - shares[index - 1]))
	_expect(shares.size() == WALK_STEPS, "every step of the walk was measured")
	# Before the marker was draped this ran at about 0.72 of itself along this
	# stretch, and swung by a tenth of the marker from one step to the next.
	_expect(lowest >= 0.95,
		"the ground never swallows the marker (worst %.3f of it drawn)" % lowest)
	_expect(biggest_jump <= 0.05,
		"and what is drawn does not jump between steps (worst %.3f)" % biggest_jump)
	await _finish()

func _frame_on(target: Vector3) -> void:
	var pitch := deg_to_rad(CAMERA_PITCH)
	_camera.global_position = target + Vector3(0.0, -sin(pitch), cos(pitch)) * CAMERA_DISTANCE
	_camera.look_at(target + Vector3.UP * 1.2, Vector3.UP)

func _shoot() -> Image:
	for unused: int in range(2):
		await process_frame
	RenderingServer.force_draw(false)
	return root.get_texture().get_image()

## Pixels the marker's own yellow reached. Nothing else on a snow region is
## this warm, so a colour test finds the marker without knowing where it is.
static func _marker_pixels(image: Image) -> int:
	var count := 0
	var data: PackedByteArray = image.get_data()
	var stride: int = 4 if image.get_format() == Image.FORMAT_RGBA8 else 3
	var index := 0
	while index + stride <= data.size():
		var red: int = data[index]
		var green: int = data[index + 1]
		var blue: int = data[index + 2]
		if red > 150 and green > 110 and red > blue + 70 and green > blue + 40:
			count += 1
		index += stride
	return count

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value

func _finish() -> void:
	print("rendered ground markers: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	# Whitehorn streams its framed chunks on a worker; quitting under a live
	# one crashes the process at exit (ContinentChunkStream.drain_workers).
	await ContinentChunkStream.drain_workers(self)
	quit(_failures)
