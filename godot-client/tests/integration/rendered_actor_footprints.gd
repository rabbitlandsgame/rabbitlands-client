extends SceneTree
## Rendered evidence that a large creature stands in the middle of its ground.
##
## The server reserves a box of tiles around the tile an actor reports, and
## measures reach from the edges of that box. The client's whole job here is
## to draw the model in the middle of it - and the tile an actor reports is
## *not* the middle whenever an extent is even, so getting this wrong puts a
## two-by-two creature half a tile off the ground it holds.
##
## Assertions can only check the arithmetic. What they cannot check is whether
## the model looks like it is standing on the highlighted squares, which is
## the thing a person has to be able to see - so each footprint is drawn with
## its reserved tiles marked underneath it, from a camera high enough to read
## the grid.
##
## The footprints below are the ones the profile actually authors, taken from
## `tools/measure_creature_footprints.py`, not sizes invented for a picture.

const SCREEN_SIZE := Vector2i(1280, 720)
const TILE := 1.0

# actor type, name, footprint. One of each size the shipped profile uses.
const SUBJECTS: Array = [
	[568, "Amber Lantern Moth", Vector2i(1, 1), 1.0],
	[416, "Amberhart", Vector2i(2, 2), 1.0],
	[469, "Algae Alligator", Vector2i(3, 3), 1.0],
	[464, "Crownwater Wyvern", Vector2i(4, 4), 1.0],
	[541, "Verdant Stair Dragon", Vector2i(5, 5), 1.0],
	# The same alligator at twice its model size, carrying the footprint
	# it measures at that scale. Side by side with the row above, this is
	# what `scale:` in creatures.txt buys and what it obliges: the model
	# grows and the ground it holds grows with it.
	[469, "Algae Alligator (scale 2)", Vector2i(6, 6), 2.0],
]

var _artifacts := ""
var _failures := 0
var _adapter: CoordinateAdapter
## The union of every reserved box, which is what the camera frames.
var _ground_bounds := AABB()
var _ground_started := false
## Where the three-by-three landed, for the close-up.
var _close_up_anchor := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/footprints")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	_adapter = CoordinateAdapter.new({"metresPerTile": TILE, "walkingHeight": 0.0})

	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	await process_frame

	# The footprint table as the server sends it, decoded by the client's own
	# protocol code and stored where the actor build path reads it from. That
	# is the whole delivery route, so a break anywhere along it shows up here
	# rather than being bypassed by a hand-set field.
	var listed: Array = SUBJECTS.filter(func(row: Variant) -> bool:
		return float((row as Array)[3]) == 1.0)
	var payload := PackedByteArray([listed.size() & 0xFF, 0])
	for row: Variant in listed:
		var entry: Array = row as Array
		var actor_type: int = int(entry[0])
		var size: Vector2i = entry[2] as Vector2i
		payload.append_array(PackedByteArray([actor_type & 0xFF,
			(actor_type >> 8) & 0xFF, size.x, size.y]))
	var state: Node = root.get_node("/root/AppState")
	state.call("_on_packet",
		EloriaProtocol.ServerMessage.ELORIA_ACTOR_FOOTPRINTS, payload)
	await process_frame
	for row: Variant in listed:
		var entry: Array = row as Array
		var expected_size: Vector2i = entry[2] as Vector2i
		_expect(state.call("footprint_for_actor_type", int(entry[0]))
			== expected_size,
			"%s arrives from the wire as %s" % [entry[1], expected_size])
	_expect(state.call("footprint_for_actor_type", 9999) == Vector2i.ONE,
		"an actor type the table does not mention stands on one tile")

	var stage := Node3D.new()
	root.add_child(stage)
	_light(stage)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 50.0
	stage.add_child(camera)

	var models: Dictionary = main.get("models") as Dictionary
	var equipment_config: Dictionary = main.get("equipment_config") as Dictionary
	var anchor_x := 0
	for row: Variant in SUBJECTS:
		var entry: Array = row as Array
		var actor_type: int = int(entry[0])
		var size: Vector2i = entry[2] as Vector2i
		# Spaced so no two boxes touch, whatever their size.
		anchor_x += size.x + 3
		var anchor_y := 0
		_draw_reserved_ground(stage, anchor_x, anchor_y, size)
		var scale: float = float(entry[3])
		var dto: Dictionary = main.call("_presentation_dto", {
			"actor_id": actor_type, "x": anchor_x, "y": anchor_y, "rotation": 0,
			"actor_type": actor_type, "kind": 1, "name": str(entry[1]),
			"health": 100, "max_health": 100, "frame": 0, "scale": scale,
			"appearance": {}}) as Dictionary
		if scale != 1.0:
			dto["footprint"] = size
		else:
			_expect((dto.get("footprint") as Vector2i) == size,
				"%s reaches the actor build path as %s" % [entry[1], size])
		var model_id: String = str(main.call("_model_for_actor", dto))
		var model_config: Dictionary = models.get(model_id, {}) as Dictionary
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors: Array[String] = actor.configure(dto, _adapter, model_config,
			main.call("_animation_for_model", model_config) as Dictionary,
			equipment_config)
		_expect(errors.is_empty(), "%s builds: %s" % [entry[1], errors])
		actor.apply_server_state(dto, _adapter, true)
		# The map dot is a six-metre disc meant for a top-down camera that
		# culls everything else, and the nameplate floats above the model.
		# Both would swamp a picture whose subject is where the model's feet
		# are, so this capture hides what the map camera would have drawn.
		for overlay: String in ["MapDot", "Nameplate"]:
			var node: Node3D = actor.get_node_or_null(overlay) as Node3D
			if node != null:
				node.hide()
		actor.set_nameplate_visible(false)
		_expect(is_equal_approx(actor.server_scale, scale),
			"%s is drawn at scale %s" % [entry[1], scale])
		# The ground marker is what this capture is now also for: it should
		# outline the same tiles that are shaded underneath it.
		actor.set_selected(true)

		# The claim the picture is evidence for, stated as arithmetic too: the
		# model sits at the centre of the tiles marked underneath it.
		var expected: Vector3 = _reserved_centre(anchor_x, anchor_y, size)
		_expect(Vector2(actor.global_position.x, actor.global_position.z)
			.is_equal_approx(Vector2(expected.x, expected.z)),
			"%s stands at the centre of its %s box" % [entry[1], size])
		if size == Vector2i(3, 3) and scale == 1.0:
			_close_up_anchor = anchor_x
		anchor_x += size.x

	for _settle: int in range(16):
		await process_frame
	var bounds: AABB = _ground_bounds
	var radius: float = maxf(2.0, bounds.size.length() * 0.5)
	var centre: Vector3 = bounds.get_center()
	camera.global_position = centre + Vector3(
		0.0, radius * 0.85, radius * 1.05)
	camera.look_at(centre, Vector3.UP)
	for _settle: int in range(4):
		await process_frame
	await _capture("actor-footprints.png",
		"one creature of each size the profile authors, each standing centred"
			+ " on the tiles the server reserves for it, with the selection"
			+ " marker outlining that same box")

	# And one close enough to check the marker against the tile edges it is
	# claiming, which the wide shot is too small to settle.
	var subject: Vector3 = _reserved_centre(_close_up_anchor, 0, Vector2i(3, 3))
	camera.global_position = subject + Vector3(0.0, 4.6, 5.4)
	camera.look_at(subject, Vector3.UP)
	for _settle: int in range(4):
		await process_frame
	await _capture("actor-footprint-marker.png",
		"the three-by-three marker against the tiles it claims: the outline"
			+ " traces the whole reserved box, not the anchor tile")

	main.queue_free()
	await process_frame
	print("rendered actor footprints: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

## The centre of the reserved box, derived here from the server's own bounds
## rule rather than from the adapter under test - so the two agreeing means
## something.
func _reserved_centre(anchor_x: int, anchor_y: int, size: Vector2i) -> Vector3:
	var min_x: int = anchor_x - (size.x - 1) / 2
	var max_x: int = anchor_x + size.x / 2
	var min_y: int = anchor_y - (size.y - 1) / 2
	var max_y: int = anchor_y + size.y / 2
	return _adapter.server_to_godot(
		(float(min_x) + float(max_x) + 1.0) * 0.5,
		(float(min_y) + float(max_y) + 1.0) * 0.5)

## Mark every tile the box covers, and outline the anchor tile inside it, so
## the picture shows both what was reserved and which single tile the actor
## reports as its position.
func _draw_reserved_ground(stage: Node3D, anchor_x: int, anchor_y: int,
		size: Vector2i) -> void:
	var min_x: int = anchor_x - (size.x - 1) / 2
	var min_y: int = anchor_y - (size.y - 1) / 2
	for dx: int in range(size.x):
		for dy: int in range(size.y):
			var tile_x: int = min_x + dx
			var tile_y: int = min_y + dy
			var is_anchor: bool = tile_x == anchor_x and tile_y == anchor_y
			var quad := MeshInstance3D.new()
			var plane := PlaneMesh.new()
			plane.size = Vector2(TILE * 0.94, TILE * 0.94)
			var material := StandardMaterial3D.new()
			material.albedo_color = (Color(0.98, 0.72, 0.24, 0.95) if is_anchor
				else Color(0.30, 0.52, 0.72, 0.85))
			material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			plane.material = material
			quad.mesh = plane
			quad.position = _adapter.tile_center(tile_x, tile_y)
			quad.position.y = 0.01
			stage.add_child(quad)
			var box := AABB(quad.position - Vector3(0.5, 0.0, 0.5),
				Vector3(1.0, 1.0, 1.0))
			_ground_bounds = box if not _ground_started else _ground_bounds.merge(box)
			_ground_started = true

func _light(stage: Node3D) -> void:
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.44, 0.47, 0.52)
	environment.environment.ambient_light_energy = 1.15
	stage.add_child(environment)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-42.0, 138.0, 0.0)
	key.light_energy = 1.4
	stage.add_child(key)

func _visible_bounds(node: Node) -> AABB:
	var bounds := AABB()
	var started := false
	for child: Node in node.get_children():
		if child is VisualInstance3D:
			var visual: VisualInstance3D = child as VisualInstance3D
			var box: AABB = visual.global_transform * visual.get_aabb()
			bounds = box if not started else bounds.merge(box)
			started = true
		var nested: AABB = _visible_bounds(child)
		if nested.size != Vector3.ZERO:
			bounds = nested if not started else bounds.merge(nested)
			started = true
	return bounds

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK, "%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
