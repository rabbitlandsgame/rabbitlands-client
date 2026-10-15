extends SceneTree
## One garment, one frame, saved on its own. A composite sheet hides where a
## render went wrong; this shows a single cell exactly as the camera saw it.

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var out := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("user://torso-sheets")
	DirAccess.make_dir_recursive_absolute(out)
	var models: Dictionary = (_json("res://data/actors/models.json").get(
		"models", {}) as Dictionary)
	var equipment: Dictionary = _json("res://data/actors/equipment.json")
	var config: Dictionary = models.get("luminous_male", {}) as Dictionary
	var animations: Dictionary = _json(str(config.get("animationMap",
		"res://data/animations/luminous.json")))

	var viewport := SubViewport.new()
	viewport.size = Vector2i(640, 900)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var stage := Node3D.new()
	viewport.add_child(stage)
	var camera := Camera3D.new()
	camera.cull_mask = ~2
	camera.fov = 42.0
	stage.add_child(camera)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-38.0, 34.0, 0.0)
	key.light_energy = 1.6
	stage.add_child(key)
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color(0.10, 0.10, 0.12)
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color(0.44, 0.46, 0.52)
	settings.ambient_light_energy = 1.0
	environment.environment = settings
	# Also on the camera: the project ships a default environment with a sky,
	# and in an own-world SubViewport that sky was still drawn behind the
	# garment as a blue band across the top of every cell.
	camera.environment = settings
	stage.add_child(environment)

	for visual: int in [128, 168, 120]:
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		actor.configure({"actor_id": 1, "x": 0, "y": 0, "rotation": 0, "name": "",
			"appearance": {"skin": 1, "hair": 2, "eyes": 3, "shirt": 1,
				"pants": 2, "boots": 3, "head": 1},
			"equipment_visuals": {5: visual}},
			CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true}),
			config, animations, equipment)
		# The coordinate adapter puts the actor where the server would; frame
		# whatever that turns out to be rather than assuming the origin.
		var focus := actor.position + Vector3(0.0, 1.10, 0.0)
		camera.position = focus + Vector3(0.0, 0.0, 2.30)
		camera.look_at(focus, Vector3.UP)
		camera.make_current()
		for _settle: int in range(12):
			await process_frame
		var image := viewport.get_texture().get_image()
		print("visual %d rendered %s  actor pos %s" % [
			visual, image.get_size(), actor.position])
		image.save_png(out.path_join("one-shot-%d.png" % visual))
		actor.queue_free()
		await process_frame
	quit(0)

func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed as Dictionary if parsed is Dictionary else {}
