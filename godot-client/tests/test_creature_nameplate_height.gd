extends SceneTree
## Exercise the actual Bellwatch models: a scaled fox must not inherit a
## human-sized banner anchor. Optional rendered evidence uses the same scene.

var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1000, 720)
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("233e43")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.7
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45.0, -30.0, 0.0)
	stage.add_child(light)
	var camera := Camera3D.new()
	camera.fov = 50.0
	camera.cull_mask = 3
	stage.add_child(camera)
	camera.position = Vector3(0.0, 4.0, 7.0)
	camera.look_at(Vector3(0.0, 0.8, 0.0))
	camera.current = true
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json")) as Dictionary
	var models: Dictionary = registry.models as Dictionary
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var actors: Array[ReplicatedActor3D] = []
	for entry: Array in [["red_fox", "Red Fox", 2.0, 20],
			["mire_goblin", "Mire Goblin", 1.0, 38]]:
		var config: Dictionary = models[entry[0]] as Dictionary
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			str(config.animationMap))) as Dictionary
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id": actors.size() + 1,
			"x": 0, "y": 0, "rotation": 0, "kind": 5,
			"name": entry[1], "name_colour": 14, "scale": entry[2],
			"health": entry[3], "max_health": entry[3]}, adapter, config, animations)
		_expect(errors.is_empty(), "%s loads: %s" % [entry[0], errors])
		actor.set_physics_process(false)
		actor.position = Vector3(-1.2 + actors.size() * 2.4, 0.0, 0.0)
		actor.set_health_visible(true)
		actors.append(actor)
		_check_clearance(actor)
	var fox: ReplicatedActor3D = actors[0]
	var plate := fox.get_node("Nameplate") as Label3D
	_expect(plate.position.y < 2.0,
		"the scaled fox's banner stays near its small body, not at 4.3 metres")
	var initial_height: float = plate.position.y
	fox.set_title("Orchard scout")
	fox.show_speech_bubble("Here!", 1000)
	var bubble := fox.get_node("SpeechBubble") as Label3D
	_expect(is_equal_approx(bubble.font_size * bubble.pixel_size,
		ReplicatedActor3D.SPEECH_BUBBLE_FONT_SIZE * ReplicatedActor3D.OVERHEAD_PIXEL)
		and is_equal_approx(bubble.width * bubble.pixel_size,
		ReplicatedActor3D.SPEECH_BUBBLE_WIDTH * ReplicatedActor3D.OVERHEAD_PIXEL),
		"speech uses the wider, readable NPC bubble scale")
	_expect(bubble.modulate.is_equal_approx(
			ReplicatedActor3D.SPEECH_BUBBLE_TEXT)
		and bubble.outline_modulate.is_equal_approx(
			ReplicatedActor3D.SPEECH_BUBBLE_SURROUND)
		and (bubble.outline_size * bubble.pixel_size
			>= 6 * ReplicatedActor3D.OVERHEAD_PIXEL
			or is_equal_approx(bubble.outline_size * bubble.pixel_size,
				6 * ReplicatedActor3D.OVERHEAD_PIXEL)),
		"NPC words use cream ink over a low-cost dark surround")
	_check_block(fox)
	fox.set_server_scale(3.0)
	_check_clearance(fox)
	_check_block(fox)
	_expect(plate.position.y > initial_height, "a larger fox lifts its banner")
	_expect(plate.fixed_size and plate.scale.is_equal_approx(Vector3.ONE),
		"scaling the creature preserves the name's screen size")
	fox.set_server_scale(2.0)
	_expect(is_equal_approx(plate.position.y, initial_height),
		"restoring the creature scale restores its banner height")
	fox.set_title("")
	fox.clear_speech_bubble()
	for frame: int in range(12):
		await process_frame
		_expect(is_equal_approx(plate.position.y, initial_height),
			"animation does not make the anchor bob")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		var path := OS.get_environment("ELORIA_ARTIFACT_DIR")
		if not path.is_empty():
			DirAccess.make_dir_recursive_absolute(path)
			_expect(root.get_texture().get_image().save_png(
				path.path_join("orchard-nameplate.png")) == OK, "capture saved")
	print("creature nameplate height: ", "PASS" if _failures == 0 else "FAIL")
	stage.queue_free()
	await process_frame
	await process_frame
	quit(_failures)

func _check_clearance(actor: ReplicatedActor3D) -> void:
	var model := actor.get_node("NativeModel") as Node3D
	var top := -INF
	for child: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh := child as MeshInstance3D
		if mesh.mesh != null:
			var bounds: AABB = mesh.global_transform * mesh.get_aabb()
			top = maxf(top, bounds.end.y)
	var plate := actor.get_node("Nameplate") as Node3D
	var clearance: float = plate.global_position.y - top
	_expect(clearance >= 0.45 and clearance <= 0.75,
		"banner clears the imported body's top by a small gap: %.3f" % clearance)
	print("actor ", actor.actor_id, " body top: ", top,
		"; nameplate: ", plate.global_position.y)

func _check_block(actor: ReplicatedActor3D) -> void:
	var plate := actor.get_node("Nameplate") as Node3D
	for piece: String in ["TitleLine", "SpeechBubble", "HealthBarBackground",
			"HealthBarFill", "HealthNumbers"]:
		var node := actor.get_node(piece) as Node3D
		_expect(is_equal_approx(node.position.y, plate.position.y),
			"%s follows the same anchor" % piece)

func _expect(value: bool, description: String) -> void:
	if not value:
		_failures += 1
		push_error(description)
