extends SceneTree
## Rendered evidence that a held prop sits in the fist rather than beside it.
##
## The registry test can only measure the mesh: it knows the grip band is
## centred across the socket, which catches a weapon riding out to one side.
## What it cannot see is a prop that is the right way round but held in the
## wrong PLACE along its own length -- the hand closed on a blade with the
## haft sticking out behind, which is what a sickle looked like.  That is a
## picture, so this takes the picture: every generated weapon in a real hand,
## framed on the hand bone close enough to read.
##
## ELORIA_PROP_VISUALS is a comma-separated list of visuals to shoot; the
## default is every held weapon in the registry.  ELORIA_PROP_PART picks the
## hand: 0 is the right, 1 the left, which draws the same meshes from the
## off-hand bank.

const SCREEN_SIZE := Vector2i(1280, 720)
const CELL := Vector2i(320, 360)
const COLUMNS := 6

var _artifacts := ""
var _failures := 0
var _main: Control
var _stage: Node3D
var _camera: Camera3D
var _adapter: CoordinateAdapter
var _model_config: Dictionary
var _animation_config: Dictionary
var _equipment_config: Dictionary
var _next_id := 9500
var _part := 0
var _eye := EYE

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/held-props")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_main.hide()
	await process_frame

	var models: Dictionary = _main.get("models") as Dictionary
	_equipment_config = _main.get("equipment_config") as Dictionary
	_model_config = models.get("luminous_male", {}) as Dictionary
	_expect(not _model_config.is_empty(), "luminous_male is in the model registry")
	_animation_config = _main.call("_animation_for_model", _model_config) as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})
	var part: String = OS.get_environment("ELORIA_PROP_PART")
	_part = int(part) if not part.is_empty() else 0
	var eye: String = OS.get_environment("ELORIA_PROP_EYE")
	_eye = float(eye) if not eye.is_empty() else EYE

	_stage = Node3D.new()
	root.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.82, 0.84, 0.88)
	environment.environment.ambient_light_energy = 1.3
	_stage.add_child(environment)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-38.0, 142.0, 0.0)
	key.light_energy = 1.5
	_stage.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20.0, -40.0, 0.0)
	fill.light_energy = 0.6
	_stage.add_child(fill)
	_camera = Camera3D.new()
	_camera.current = true
	_camera.fov = 40.0
	_camera.cull_mask = 3
	_stage.add_child(_camera)

	for visual: int in _visuals():
		var actor: ReplicatedActor3D = _spawn({str(_part): visual})
		var diag: Dictionary = actor.equipment_diagnostics()
		_expect(int(diag.get("socket", 0)) == 1 and int(diag.get("fallback", 0)) == 0,
			"%d:%d hangs off its socket" % [_part, visual])
		actor.play_action(&"idle")
		for _f: int in range(24):
			await process_frame
		var hand: Node3D = _hand(actor)
		if _expect(hand != null, "0:%d has a hand attachment" % visual):
			await _shoot(visual, hand)
		actor.queue_free()
		await process_frame

	print("rendered held prop evidence: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	_stage.queue_free()
	_main.queue_free()
	await process_frame
	quit(_failures)

func _visuals() -> Array:
	var wanted: String = OS.get_environment("ELORIA_PROP_VISUALS")
	if not wanted.is_empty():
		var picked: Array = []
		for piece: String in wanted.split(",", false):
			picked.append(int(piece.strip_edges()))
		return picked
	var all: Array = []
	var registry: Dictionary = _equipment_config.get("models", {}) as Dictionary
	for key: String in registry:
		var parts: PackedStringArray = key.split(":")
		if parts.size() != 2 or parts[0] != str(_part):
			continue
		var model: Dictionary = registry[key] as Dictionary
		if str(model.get("attach", "")) != "socket":
			continue
		all.append(int(parts[1]))
	all.sort()
	return all

func _spawn(visuals: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	_next_id += 1
	actor.configure({
		"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "grip", "appearance": {}, "equipment_visuals": visuals,
	}, _adapter, _model_config, _animation_config, _equipment_config)
	actor.server_target = Vector3.ZERO
	actor.global_position = Vector3.ZERO
	actor.rotation.y = 0.0
	return actor

func _hand(actor: ReplicatedActor3D) -> Node3D:
	var pattern: String = "EquipmentPart_%d_Visual_*" % _part
	for node: Node in actor.find_children(pattern, "BoneAttachment3D", true, false):
		return node as Node3D
	return null

## Three looks at one hand, because one is not enough: a blade is a plate, and
## seen edge-on a fist closed on the flat of it looks like a fist closed on a
## haft.  Front, side and above between them always catch it.
const VIEWS := {
	"front": Vector3(0.0, 0.0, 1.0),
	"side": Vector3(1.0, 0.0, 0.0),
	"above": Vector3(0.0, 1.0, 0.001),
}
## Close enough to read the fist by default.  ELORIA_PROP_EYE pulls back when
## the question is the whole weapon rather than the grip -- a polearm at 0.85 m
## is all haft.
const EYE := 0.85

func _shoot(visual: int, hand: Node3D) -> void:
	var centre: Vector3 = hand.global_position
	var name: String = str(_equipment_config.get("models", {}).get(
		"%d:%d" % [_part, visual], {}).get("name", "?"))
	for view: String in VIEWS:
		var eye: Vector3 = VIEWS[view] as Vector3
		_camera.global_position = centre + eye.normalized() * _eye
		_camera.look_at(centre, Vector3.UP if view != "above" else Vector3.FORWARD)
		for _f: int in range(3):
			await process_frame
		await _capture("prop-%d-%03d-%s.png" % [_part, visual, view],
			"%d:%d %s (%s)" % [_part, visual, name, view])

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full frame" % name)
	if image == null:
		return
	_expect(image.save_png(_artifacts.path_join(name)) == OK, "%s is written" % name)
	print("capture ", name, ": ", description)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
