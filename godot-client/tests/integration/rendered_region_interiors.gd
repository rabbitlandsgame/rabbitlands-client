extends SceneTree

## Renders each Nymara region interior from the isometric rig's own angle, with
## and without the manifest's cutaway applied.
##
## These maps are closed rooms under a camera that looks down into them, so the
## lid is between the player and everything they need to navigate by. Each
## package names its lids in `cutaway.hideNodes`; this checks that the block is
## there, that it actually takes those nodes out of the picture, and that the
## collision the world loader built from them survives being hidden.

const SIZE := Vector2i(1280, 720)

const InteriorCutawayScript := preload("res://src/world/interior_cutaway.gd")

const MAPS := [
	"nymara-regions/interiors/amethyst_barrens_insides",
	"nymara-regions/interiors/westhaven_insides",
	"nymara-regions/interiors/crownwater_insides",
	"nymara-regions/interiors/manymouth_delta_insides",
	"nymara-regions/interiors/whitehorn_insides",
	"nymara-regions/interiors/mirrorhold_interiors",
	"nymara-regions/interiors/ssarathi_insides",
	"nymara-regions/interiors/grey_moors_insides",
	"nymara-regions/interiors/verdant_stair_insides",
	"nymara-regions/interiors/amberwood_amber_hall",
	"nymara-regions/interiors/amberwood_cinder_chapel",
	"nymara-regions/interiors/amberwood_motherroot",
	"nymara-regions/interiors/amberwood_gate_undercroft",
]

# The isometric rig's defaults, so a shot here frames what a player sees.
const PITCH_DEGREES := -60.0
const DISTANCE := 26.0

var _failures := 0
var _artifacts := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/region-interiors")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SIZE
	for path: String in MAPS:
		await _render(path)
	print("region interiors: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

func _render(package: String) -> void:
	var ident: String = package.get_file()
	var scene: Node3D = (load("res://src/dev/world_validation.tscn") as PackedScene
		).instantiate() as Node3D
	root.add_child(scene)
	var loader: WorldLoader = scene.get_node("WorldLoader") as WorldLoader
	loader.load_world(ProjectSettings.globalize_path(
		"res://../eloria-assets/maps/%s/world.json" % package))
	var deadline: int = Time.get_ticks_msec() + 120000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if loader.world_root == null:
		_fail(ident + ": did not load")
		scene.queue_free()
		return
	WorldEnvironmentBinder.apply(loader.manifest,
		scene.get_node("Environment") as WorldEnvironment,
		scene.get_node("Sun") as DirectionalLight3D, loader.world_root)
	(scene.get_node("UI") as CanvasLayer).visible = false

	var lids: Array[Node3D] = _lids(loader.world_root)
	_expect(not lids.is_empty(), "%s: %d lid nodes in the package" % [ident, lids.size()])
	var solid_before: int = _collision_bodies(lids)

	var camera: Camera3D = scene.get_node("Camera") as Camera3D
	camera.fov = 50.0
	camera.near = 1.0
	camera.far = 1800.0
	var focus: Vector3 = _spawn(loader.manifest)
	var pitch: float = deg_to_rad(PITCH_DEGREES)
	camera.global_position = focus + Vector3(0.0, -sin(pitch), cos(pitch)) * DISTANCE
	camera.look_at(focus, Vector3.UP)
	await _shoot(ident + "-roofed.png")

	var cutaway: RefCounted = InteriorCutawayScript.new()
	var hidden: int = cutaway.configure(loader.manifest, loader.world_root)
	_expect(hidden >= lids.size(),
		"%s: cutaway took control of %d nodes" % [ident, hidden])
	var still_drawn: int = 0
	for lid: Node3D in lids:
		if lid.visible:
			still_drawn += 1
	_expect(still_drawn == 0, "%s: every lid is cut away" % ident)
	_expect(_collision_bodies(lids) == solid_before,
		"%s: cut-away lids keep their %d collision bodies" % [ident, solid_before])
	await _shoot(ident + "-open.png")

	cutaway.reset()
	scene.queue_free()
	await process_frame

## The lids the package declares, resolved against the loaded scene.
static func _lids(world_root: Node3D) -> Array[Node3D]:
	var found: Array[Node3D] = []
	for node: Node in world_root.find_children("Roof_*", "MeshInstance3D", true, false):
		found.append(node as Node3D)
	return found

static func _collision_bodies(nodes: Array[Node3D]) -> int:
	var found: int = 0
	for node: Node3D in nodes:
		for child: Node in node.get_children():
			if child is StaticBody3D:
				found += 1
	return found

static func _spawn(manifest: WorldManifest) -> Vector3:
	var points: Variant = manifest.data.get("spawnPoints", [])
	if points is Array and not (points as Array).is_empty():
		var first: Dictionary = (points as Array)[0] as Dictionary
		var position: Variant = first.get("position", [])
		if position is Array and (position as Array).size() >= 3:
			var values: Array = position as Array
			return Vector3(float(values[0]), float(values[1]) + 1.2,
				float(values[2]))
	return Vector3.ZERO

func _shoot(filename: String) -> void:
	for _frame: int in range(6):
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
