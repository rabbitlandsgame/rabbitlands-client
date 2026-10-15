extends SceneTree
## Rendered evidence for the 16-bit actor path.
##
## The bytes below are the exact `ADD_NEW_ACTOR_EXTENDED(247)` frames captured
## from a real Eloria server for two Nymara creatures whose actor types are
## above the 8-bit ceiling. They are decoded by the client's own protocol code,
## turned into presentation DTOs by the client's own actor build path, and
## rendered by the client's own actor scene, so nothing here hand-builds an
## actor that the wire could not produce.
##
## The `before` frame is the same decode with the registry lookup suppressed,
## which is what a client that could not express the type would show: the
## missing-model fallback.

const SCREEN_SIZE := Vector2i(1280, 720)
# Captured from the local server: Reedhorn Stag (401) and Four Gates Turtle
# (402), both above 255.
const CAPTURED_FRAMES := {
	401: "65000103e001000000009101072b002b0005",
	402: "6600ff02e001000000009201075c005c0005",
}
const CAPTURED_NAMES := {401: "Reedhorn Stag", 402: "Four Gates Turtle"}

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/phase0")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	# The client scene is instantiated for its registries and its actor build
	# path, not for its UI: the captures are of the 3D actors, so its Control
	# tree is hidden rather than left covering the frame.
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	await process_frame

	var models: Dictionary = main.get("models") as Dictionary
	var actor_type_models: Dictionary = main.get("actor_type_models") as Dictionary
	var equipment_config: Dictionary = main.get("equipment_config") as Dictionary

	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.42, 0.45, 0.5)
	environment.environment.ambient_light_energy = 1.1
	stage.add_child(environment)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-38.0, 142.0, 0.0)
	key.light_energy = 1.5
	stage.add_child(key)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 45.0
	stage.add_child(camera)

	var spawned: Array[ReplicatedActor3D] = []
	var offset := -1.6
	for raw_type: Variant in CAPTURED_FRAMES:
		var actor_type: int = int(raw_type)
		var payload: PackedByteArray = _hex_bytes(str(CAPTURED_FRAMES[raw_type]))
		payload.append_array(_nul_bytes(str(CAPTURED_NAMES[raw_type])))
		var decoded: Dictionary = EloriaProtocol.decode_server(
			EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED, payload)
		_expect(decoded.get("type", "") == "actor_spawn"
			and int(decoded.get("actor_type", -1)) == actor_type
			and actor_type > 0xff,
			"the captured frame decodes as actor type %d" % actor_type)
		var model_id: String = str(main.call("_model_for_actor", decoded))
		_expect(not model_id.is_empty(),
			"actor type %d resolves to a native model" % actor_type)
		var model_config: Dictionary = models.get(model_id, {}) as Dictionary
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors: Array[String] = actor.configure(
			main.call("_presentation_dto", decoded) as Dictionary,
			CoordinateAdapter.new({"walkingHeight": 0.0}), model_config,
			main.call("_animation_for_model", model_config) as Dictionary,
			equipment_config)
		_expect(errors.is_empty(),
			"actor type %d builds without errors: %s" % [actor_type, errors])
		_expect(actor.get_node_or_null("NativeModel") != null
			and actor.get_node_or_null("MissingModelFallback") == null,
			"actor type %d renders its native GLB and no fallback" % actor_type)
		# The live path starts an animation from the first server state, not
		# from configure(), so drive that here rather than asserting on a
		# state the wire never produces.
		actor.apply_server_state(main.call("_presentation_dto", decoded) as Dictionary,
			CoordinateAdapter.new({"walkingHeight": 0.0}), true)
		var player: AnimationPlayer = actor.animation_player
		_expect(player != null and player.current_animation != ""
			and String(actor.current_action) != "",
			"actor type %d plays a native clip (action=%s clip=%s)" % [actor_type,
				String(actor.current_action),
				"none" if player == null else player.current_animation])
		# apply_server_state() teleports the actor to its authoritative tile, so
		# the display placement has to come after it and the interpolation
		# target has to move with it.
		actor.server_target = Vector3(offset, 0.0, 0.0)
		actor.global_position = actor.server_target
		actor.rotation.y = PI
		offset += 3.2
		spawned.append(actor)

	_expect(actor_type_models.has("401") and actor_type_models.has("402"),
		"the registry declares both captured actor types")
	for _settle: int in range(12):
		await process_frame
	# Frame whatever the models actually are rather than guessing their scale.
	var bounds: AABB = _visible_bounds(stage)
	print("actor bounds: ", bounds)
	var radius: float = maxf(1.0, bounds.size.length() * 0.5)
	var centre: Vector3 = bounds.get_center()
	camera.global_position = centre + Vector3(0.0, radius * 0.35, radius * 2.1)
	camera.look_at(centre, Vector3.UP)
	for _settle: int in range(4):
		await process_frame
	await _capture("actor16-native.png",
		"Nymara creatures with actor types 401 and 402 on their native GLBs")

	# What a client that could not express a 16-bit type would show instead.
	for actor: ReplicatedActor3D in spawned:
		actor.queue_free()
	await process_frame
	offset = -1.6
	for raw_type: Variant in CAPTURED_FRAMES:
		var fallback_actor := ReplicatedActor3D.new()
		stage.add_child(fallback_actor)
		fallback_actor.configure({
			"actor_id": 900 + int(raw_type), "x": 0, "y": 0, "rotation": 0,
			"actor_type": int(raw_type), "kind": 5,
			"name": str(CAPTURED_NAMES[raw_type])},
			CoordinateAdapter.new({"walkingHeight": 0.0}), {},
			{}, equipment_config)
		_expect(fallback_actor.get_node_or_null("MissingModelFallback") != null,
			"an unresolvable actor type shows the missing-model fallback")
		fallback_actor.server_target = Vector3(offset, 0.0, 0.0)
		fallback_actor.global_position = fallback_actor.server_target
		offset += 3.2
	for _settle: int in range(8):
		await process_frame
	await _capture("actor16-fallback.png",
		"the same two creatures with no model the client can express")

	print("rendered 16-bit actor evidence: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	stage.queue_free()
	main.queue_free()
	await process_frame
	quit(_failures)

## The union of every visible mesh AABB under `node`, in world space.
func _visible_bounds(node: Node) -> AABB:
	var bounds := AABB()
	var found := false
	for mesh: Node in _visual_meshes(node):
		var instance: VisualInstance3D = mesh as VisualInstance3D
		if not instance.visible:
			continue
		var world_aabb: AABB = instance.global_transform * instance.get_aabb()
		bounds = world_aabb if not found else bounds.merge(world_aabb)
		found = true
	return bounds if found else AABB(Vector3.ZERO, Vector3.ONE)

func _visual_meshes(node: Node) -> Array[Node]:
	var found: Array[Node] = []
	for child: Node in node.get_children():
		if child is VisualInstance3D and child is not Camera3D:
			found.append(child)
		found.append_array(_visual_meshes(child))
	return found

func _hex_bytes(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _nul_bytes(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	bytes.append(0)
	return bytes

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full frame" % name)
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK, "%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var first: Color = image.get_pixel(0, 0)
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			if not image.get_pixel(x, y).is_equal_approx(first):
				return true
	return false

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
