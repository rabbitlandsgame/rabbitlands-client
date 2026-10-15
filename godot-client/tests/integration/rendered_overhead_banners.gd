extends SceneTree
## Rendered evidence for the overhead block: the name, and the health bar the
## player's target wears.
##
## Two claims, neither of which a normal assertion can see on its own.
##
## The first is that a name is the same size to read wherever the actor is
## standing and whatever the camera's zoom is. Your own name and health are a
## 2D panel projected over your head, so they have always been a fixed size on
## screen; a creature's were a Label3D, which shrinks with distance like the
## creature does. A name is text, not scenery - it should be as legible across
## the field as it is underfoot. The arithmetic behind that is checked below
## against the camera's own projection, and the pictures are what show it
## reading as one size rather than merely measuring as one.
##
## The second is who wears a bar. Every actor packet carries a health pair -
## the server gives a shopkeeper 20 of 20 like everybody else - so the client
## drew one over every trader and gate warden in a market, a row of bars that
## never move and say nothing. Anything that can fight keeps its bar: another
## player, and every creature. Scenery keeps a bare name unless you have
## picked a fight with it.

const SCREEN_SIZE := Vector2i(1280, 720)
const TILE := 1.0
## The gameplay camera, as main.tscn and the rig set it up.
const CAMERA_FOV := 50.0
const CAMERA_PITCH := -60.0

# Actor type, EL actor kind, name, and the tile it stands on - a line running
# away from the camera, so one row of names spans the depths a crowded field
# covers. Kind 5 is PKABLE_COMPUTER_CONTROLLED, every creature; kind 1 is
# HUMAN, another player; kind 2 is NPC, the scenery a market is full of, and
# the server hands it a health pair like everybody else.
const SUBJECTS: Array = [
	[416, 5, "Amberhart", Vector2i(0, 0)],
	[568, 5, "Amber Lantern Moth", Vector2i(0, 8)],
	[1, 1, "Ceridwen", Vector2i(0, 16)],
	[246, 2, "Salina the Trader", Vector2i(0, 24)],
	[464, 5, "Crownwater Wyvern", Vector2i(0, 32)],
]
## Which of them the player is fighting, which is the other player, and which
## is the scenery that should carry nothing but its name.
const TARGET_INDEX := 1
const PLAYER_INDEX := 2
const SCENERY_INDEX := 3

var _artifacts := ""
var _failures := 0
var _adapter: CoordinateAdapter

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/overhead-banners")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	_adapter = CoordinateAdapter.new({"metresPerTile": TILE, "walkingHeight": 0.0})

	var main: Control = (load("res://src/app/main.tscn") as PackedScene
		).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	await process_frame

	var stage := Node3D.new()
	root.add_child(stage)
	_light(stage)
	_ground(stage)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = CAMERA_FOV
	# Layers 1 and 2, as the gameplay camera does: layer 4 is the map dot, a
	# six-metre disc drawn for a top-down camera that culls everything else.
	camera.cull_mask = 3
	camera.near = 1.0
	camera.far = 1800.0
	stage.add_child(camera)

	var models: Dictionary = main.get("models") as Dictionary
	var equipment_config: Dictionary = main.get("equipment_config") as Dictionary
	var actors: Array[ReplicatedActor3D] = []
	for index: int in range(SUBJECTS.size()):
		var entry: Array = SUBJECTS[index] as Array
		var tile: Vector2i = entry[3] as Vector2i
		var dto: Dictionary = main.call("_presentation_dto", {
			"actor_id": 100 + index, "x": tile.x, "y": tile.y, "rotation": 0,
			"actor_type": int(entry[0]), "kind": int(entry[1]),
			"name": str(entry[2]),
			"health": 62, "max_health": 100, "frame": 0, "scale": 1.0,
			"appearance": {}}) as Dictionary
		var model_id: String = str(main.call("_model_for_actor", dto))
		var model_config: Dictionary = models.get(model_id, {}) as Dictionary
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors: Array[String] = actor.configure(dto, _adapter, model_config,
			main.call("_animation_for_model", model_config) as Dictionary,
			equipment_config)
		_expect(errors.is_empty(), "%s builds: %s" % [entry[2], errors])
		actor.apply_server_state(dto, _adapter, true)
		actor.set_nameplate_visible(true)
		actors.append(actor)

	# Who wears a bar is main.gd's rule, asked here rather than restated: the
	# fixture drives it through `_overhead_health_for` with the same target id
	# the combat packets would have named.
	for index: int in range(actors.size()):
		var entry: Array = SUBJECTS[index] as Array
		actors[index].set_health_visible(bool(main.call(
			"_overhead_health_for", 100 + index,
			{"kind": int(entry[1]), "name_colour": 0},
			100 + TARGET_INDEX)))
	for _settle: int in range(16):
		await process_frame

	_check_block_hangs_together(actors)
	_check_matches_the_players_banner(main, camera, actors)
	_check_who_wears_a_bar(main, actors)

	# The middle of the line, framed the way the rig frames the player: the
	# first actor is about where you stand and the last is across the field.
	var focus: Vector3 = actors[0].global_position.lerp(
		actors[actors.size() - 1].global_position, 0.5)
	await _frame(camera, focus, 26.0)
	await _capture("overhead-banners.png",
		"a row of actors at the camera's default zoom: every name is the same"
			+ " size to read, every creature and the other player carry a bar,"
			+ " and the trader carries nothing but a name")

	await _frame(camera, focus, 70.0)
	await _capture("overhead-banners-zoomed-out.png",
		"the same row with the camera pulled back to 70 m: the actors shrink"
			+ " and the names do not")

	main.queue_free()
	await process_frame
	print("rendered overhead banners: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

## Nothing in the block may hang from a world height of its own: the pieces
## are spaced inside their own local space, which is what keeps the gaps
## between them the size the text is as the camera moves.
func _check_block_hangs_together(actors: Array[ReplicatedActor3D]) -> void:
	var actor: ReplicatedActor3D = actors[0]
	for piece: String in ["Nameplate", "HealthBarBackground", "HealthBarFill",
			"HealthNumbers"]:
		var node: Node3D = actor.get_node_or_null(piece) as Node3D
		if not _expect(node != null, "the actor carries a %s" % piece):
			continue
		_expect(is_equal_approx(node.position.y,
			(actor.get_node("Nameplate") as Node3D).position.y),
			"%s hangs from the nameplate's height, not one of its own" % piece)

## The claim itself, checked against the thing it claims to match rather than
## against the constants that made it. `fixed_size` scales a billboard by its
## own view depth, cancelling the perspective divide, so a local unit covers
## `render_height / (2 * tan(fov / 2))` device pixels at every depth; the 2D
## layer the player's banner is drawn in covers `render_height / 720` of them.
## Both are recomputed here from the camera and from project.godot, so that a
## change to either shows up as a failure rather than as a drifting nameplate.
func _check_matches_the_players_banner(main: Control, camera: Camera3D,
		actors: Array[ReplicatedActor3D]) -> void:
	var design_height: float = float(ProjectSettings.get_setting(
		"display/window/size/viewport_height", 720))
	var render_height: float = float(SCREEN_SIZE.y)
	# Device pixels one local unit of a fixed-size billboard covers, and device
	# pixels one pixel of the 2D layer covers.
	var per_local: float = render_height / (2.0 * tan(deg_to_rad(camera.fov * 0.5)))
	var per_canvas: float = render_height / design_height
	_expect(absf(ReplicatedActor3D.OVERHEAD_PIXEL - per_canvas / per_local)
		<= 0.000002,
		"a block pixel is the 2D layer's pixel: %.7f against %.7f"
			% [ReplicatedActor3D.OVERHEAD_PIXEL, per_canvas / per_local])
	# And the sizes themselves are the banner's own, read off the banner.
	var banner_name: Label = main.get_node(
		"%OverheadPlayerName") as Label
	var banner_number: Label = main.get_node(
		"%ActorResourceOverlay").get_node("Rows/HealthRow/Number") as Label
	var banner_bar: ProgressBar = main.get_node(
		"%ActorResourceOverlay").get_node("Rows/HealthRow/Bar") as ProgressBar
	var actor_name := actors[0].get_node("Nameplate") as Label3D
	var actor_numbers := actors[0].get_node("HealthNumbers") as Label3D
	_expect(is_equal_approx(actor_name.font_size * actor_name.pixel_size
		/ ReplicatedActor3D.OVERHEAD_PIXEL,
		float(banner_name.get_theme_font_size("font_size"))),
		"a name over a creature is the size of the player's own name")
	_expect(is_equal_approx(actor_numbers.font_size * actor_numbers.pixel_size
		/ ReplicatedActor3D.OVERHEAD_PIXEL,
		float(banner_number.get_theme_font_size("font_size"))),
		"the numbers are the size of the player's own")
	_expect(actor_name.font == banner_name.get_theme_font("font"),
		"world names use the player's typeface")
	_expect(actor_name.outline_size == 0 and actor_numbers.outline_size == 0,
		"world banners use the reference's plain letters over a dark backing")
	_expect(is_equal_approx(-actor_numbers.offset.y * actor_numbers.pixel_size,
		ReplicatedActor3D.HEALTH_LABEL_DROP * ReplicatedActor3D.OVERHEAD_PIXEL),
		"higher resolution preserves the gap between name and health numbers")
	_expect(is_equal_approx(ReplicatedActor3D.HEALTH_BAR_THICKNESS,
		banner_bar.custom_minimum_size.y),
		"the bar is as thick as the player's own: %.1f against %.1f"
			% [ReplicatedActor3D.HEALTH_BAR_THICKNESS,
				banner_bar.custom_minimum_size.y])
	# The banner stretches its own bar to the widest number beside it, so the
	# width is only held to its floor rather than to whatever it is right now.
	_expect(ReplicatedActor3D.HEALTH_BAR_WIDTH >= banner_bar.custom_minimum_size.x,
		"the bar is no narrower than the player's own")
	# Every name is drawn through the same pixel size, whatever its depth is:
	# there is no depth in the size at all any more.
	var near_label: Label3D = actors[0].get_node("Nameplate") as Label3D
	var far_label: Label3D = actors[actors.size() - 1].get_node(
		"Nameplate") as Label3D
	for index: int in range(actors.size()):
		var subject: String = str((SUBJECTS[index] as Array)[2])
		var label: Label3D = actors[index].get_node_or_null(
			"Nameplate") as Label3D
		if not _expect(label != null, "%s carries a nameplate" % subject):
			continue
		_expect(label.fixed_size, "%s's name is drawn at a fixed size" % subject)
		_expect(is_equal_approx(label.pixel_size, near_label.pixel_size)
			and label.font_size == near_label.font_size,
			"%s's name is drawn the size every other name is" % subject)
	var near_depth: float = camera.global_position.distance_to(
		near_label.global_position)
	var far_depth: float = camera.global_position.distance_to(
		far_label.global_position)
	_expect(far_depth > near_depth * 1.5,
		"the row spans depths a distance-scaled name would have varied over:"
			+ " %.1f m to %.1f m" % [near_depth, far_depth])

## Who carries a bar: anything that can fight - another player and every
## creature - and, of the scenery, only what the player has picked a fight
## with. However much health the server reports for the rest of it.
func _check_who_wears_a_bar(main: Control,
		actors: Array[ReplicatedActor3D]) -> void:
	for index: int in range(actors.size()):
		var entry: Array = SUBJECTS[index] as Array
		var subject: String = str(entry[2])
		var barred: bool = index != SCENERY_INDEX
		var reason: String = ("the player is fighting it" if index == TARGET_INDEX
			else "another player" if index == PLAYER_INDEX
			else "scenery the player is not fighting" if index == SCENERY_INDEX
			else "a creature")
		for piece: String in ["HealthBarBackground", "HealthBarFill",
				"HealthNumbers"]:
			var node: Node3D = actors[index].get_node_or_null(piece) as Node3D
			if not _expect(node != null, "the actor carries a %s" % piece):
				continue
			_expect(node.visible == barred,
				"%s is %s, so its %s is %s" % [subject, reason, piece,
					"drawn" if barred else "not drawn"])
		_expect((actors[index].get_node("Nameplate") as Node3D).visible,
			"%s keeps its name either way" % subject)
	# The rule itself, asked directly: a player and a creature carry a bar at
	# any target id at all, and scenery only at the one it is.
	var creature: Dictionary = {"kind": 5, "name_colour": 0}
	var other_player: Dictionary = {"kind": 1, "name_colour": 0}
	var scenery: Dictionary = {"kind": 2, "name_colour": 0}
	_expect(bool(main.call("_overhead_health_for", 7, other_player, -1)),
		"another player carries a bar with no fight open at all")
	_expect(bool(main.call("_overhead_health_for", 7, creature, -1)),
		"a creature carries one with no fight open")
	_expect(not bool(main.call("_overhead_health_for", 7, scenery, -1)),
		"a shopkeeper carries none, health pair or no health pair")
	_expect(bool(main.call("_overhead_health_for", 7, scenery, 7)),
		"a shopkeeper carries one once the fight names it")
	# And the bar moves with the fight rather than being fixed at spawn.
	actors[SCENERY_INDEX].set_health_visible(true)
	_expect((actors[SCENERY_INDEX].get_node(
		"HealthBarBackground") as Node3D).visible,
		"scenery the player turns on picks up the bar")
	actors[SCENERY_INDEX].set_health_visible(false)
	_expect(not (actors[SCENERY_INDEX].get_node(
		"HealthBarBackground") as Node3D).visible,
		"and loses it again when the fight ends")

func _frame(camera: Camera3D, focus: Vector3, distance: float) -> void:
	var pitch: float = deg_to_rad(CAMERA_PITCH)
	camera.global_position = focus + Vector3(
		0.0, -sin(pitch), cos(pitch)) * distance
	camera.look_at(focus + Vector3.UP * 1.2, Vector3.UP)
	for _settle: int in range(4):
		await process_frame

func _ground(stage: Node3D) -> void:
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(160.0, 160.0)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.26, 0.34, 0.24)
	plane.material = material
	floor_mesh.mesh = plane
	floor_mesh.position = _adapter.tile_center(0, 14)
	stage.add_child(floor_mesh)

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

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
