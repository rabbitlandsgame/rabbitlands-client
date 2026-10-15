extends SceneTree
## Rendered evidence for the generated armour set, on its own.
##
## Every generated visual is worn by a luminous_male through the client's own
## actor build and runtime retarget, at the relaxed idle the set is meant to be
## seen in, and captured front and three-quarter.  A full generated kit is
## shown together at the end.  Nothing here involves the older authored pieces:
## the deliverable is the generated set standing correctly by itself.
##
## Set ELORIA_FIT_RACE to check the same set on another body (ssarathi_male,
## stoneborn_male); it defaults to luminous_male.

const SCREEN_SIZE := Vector2i(1280, 720)

## slot -> [part, [generated visuals...]]
const SLOTS := {
	"body": [5, [184, 185, 186, 187, 188, 189, 190, 191]],
	"legs": [4, [171, 172, 173, 174, 179, 180, 187, 188]],
	"boots": [6, [192, 193, 194, 200, 201, 202]],
	"helm": [3, [109, 110, 111, 117, 118, 119]],
}
## A representative head-to-toe kit, all generated.
const KIT := {5: 184, 4: 171, 6: 192, 3: 117}

var _artifacts := ""
var _failures := 0
var _main: Control
var _stage: Node3D
var _camera: Camera3D
var _adapter: CoordinateAdapter
var _model_config: Dictionary
var _animation_config: Dictionary
var _equipment_config: Dictionary
var _next_id := 9000

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/equipment-fit")
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
	var race: String = OS.get_environment("ELORIA_FIT_RACE")
	if race.is_empty():
		race = "luminous_male"
	_model_config = models.get(race, {}) as Dictionary
	_expect(not _model_config.is_empty(), race + " is in the model registry")
	_animation_config = _main.call("_animation_for_model", _model_config) as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})

	_stage = Node3D.new()
	root.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.8, 0.82, 0.86)
	environment.environment.ambient_light_energy = 1.2
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

	var prefix: String = "" if race == "luminous_male" else race + "-"
	for slot: String in SLOTS:
		var spec: Array = SLOTS[slot] as Array
		var part: int = int(spec[0])
		var visuals: Array = spec[1] as Array
		var actors: Array[ReplicatedActor3D] = []
		var offset := 0.0
		for visual: int in visuals:
			var actor := _spawn({str(part): visual}, offset)
			var diag: Dictionary = actor.equipment_diagnostics()
			_expect(int(diag.get("native", 0)) > 0 and int(diag.get("fallback", 0)) == 0,
				"%d:%d attaches natively" % [part, visual])
			actors.append(actor)
			offset += 1.6
		await _settle(actors)
		await _capture_row(actors, "%sfit-%s.png" % [prefix, slot],
			"%s: generated %d:%s at idle" % [slot, part, str(visuals)])
		for actor: ReplicatedActor3D in actors:
			actor.queue_free()
		await process_frame

	# A full generated kit, framed close, front and three-quarter.
	var worn := {}
	for part_key: int in KIT:
		worn[str(part_key)] = KIT[part_key]
	var hero := _spawn(worn, 0.0)
	await _settle([hero])
	for angle_name: String in ["front", "threequarter", "side"]:
		var yaw: float = PI
		if angle_name == "threequarter":
			yaw = PI - deg_to_rad(35.0)
		elif angle_name == "side":
			yaw = PI / 2.0
		await _frame_hero(hero, yaw, "%skit-%s.png" % [prefix, angle_name],
			"full generated kit (%s)" % angle_name)

	print("rendered equipment fit evidence: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	_stage.queue_free()
	_main.queue_free()
	await process_frame
	quit(_failures)

func _spawn(visuals: Dictionary, x: float) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	_next_id += 1
	actor.configure({
		"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "fit", "appearance": {}, "equipment_visuals": visuals,
	}, _adapter, _model_config, _animation_config, _equipment_config)
	actor.server_target = Vector3(x, 0.0, 0.0)
	actor.global_position = actor.server_target
	actor.rotation.y = 0.0  # faces the +z camera on this rig
	return actor

func _settle(actors: Array) -> void:
	for actor: ReplicatedActor3D in actors:
		actor.play_action(&"idle")
	for _f: int in range(24):
		await process_frame

func _bounds(actors: Array) -> AABB:
	var bounds := AABB()
	var found := false
	for actor: ReplicatedActor3D in actors:
		var model: Node = actor.get_node_or_null("NativeModel")
		if model == null:
			continue
		for mesh: Node in model.find_children("*", "MeshInstance3D", true, false):
			var vi := mesh as VisualInstance3D
			if vi == null or not vi.visible:
				continue
			var box: AABB = vi.global_transform * vi.get_aabb()
			bounds = box if not found else bounds.merge(box)
			found = true
	return bounds if found else AABB(Vector3.ZERO, Vector3.ONE)

func _capture_row(actors: Array, name: String, description: String) -> void:
	var b: AABB = _bounds(actors)
	var centre: Vector3 = b.get_center()
	var radius: float = maxf(b.size.x, b.size.y) * 0.62
	_camera.global_position = centre + Vector3(0.0, 0.0, radius) + Vector3(0.0, 0.1, 0.0)
	_camera.look_at(centre, Vector3.UP)
	for _f: int in range(3):
		await process_frame
	await _capture(name, description)

func _frame_hero(actor: ReplicatedActor3D, yaw: float, name: String,
		description: String) -> void:
	# Actor faces the +z camera; the three-quarter orbits the camera, not the
	# actor, so the idle pose is seen from the front-ish.
	var b: AABB = _bounds([actor])
	var centre: Vector3 = b.get_center()
	var radius: float = maxf(b.size.length() * 0.5, 0.9)
	_camera.global_position = centre + Vector3(sin(yaw), 0.12, cos(yaw)) * radius * 2.1
	_camera.look_at(centre, Vector3.UP)
	for _f: int in range(3):
		await process_frame
	await _capture(name, description)

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
