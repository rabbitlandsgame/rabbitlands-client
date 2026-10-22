extends "res://tests/integration/rendered_actor_footprints.gd"
## Real actor rendering, with a player body as the size reference.
## RL_SPIDER_SPEC is exported from the current server definitions by the QA run.

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN_SIZE
	_adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	var stage := Node3D.new()
	root.add_child(stage)
	_light(stage)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 45.0
	stage.add_child(camera)
	var subjects: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_SPIDER_SPEC"))) as Array
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")) as Dictionary
	var readings: Array = []
	for i: int in range(subjects.size()):
		var spec: Dictionary = subjects[i] as Dictionary
		var anchor: int = [4, 13, 23][i]
		var shape := Vector2i(int(spec["footprint"][0]), int(spec["footprint"][1]))
		_draw_reserved_ground(stage, anchor, 0, shape)
		var dto: Dictionary = main.call("_presentation_dto", {
			"actor_id": 100 + i, "x": anchor, "y": 0, "rotation": 180,
			"actor_type": int(spec["actor_type"]), "kind": 1 if i < 2 else 0,
			"name": spec["name"], "health": 100, "max_health": 100, "frame": 0,
			"scale": float(spec["scale"]), "appearance": {}}) as Dictionary
		dto["footprint"] = shape
		var model_key: String = str((registry["actorTypes"] as Dictionary)[str(int(spec["actor_type"]))])
		var config: Dictionary = (registry["models"] as Dictionary)[model_key] as Dictionary
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors: Array[String] = actor.configure(dto, _adapter, config,
			main.call("_animation_for_model", config) as Dictionary, main.get("equipment_config") as Dictionary)
		_expect(errors.is_empty(), "%s builds from the current model (%d errors): %s" % [
			spec["name"], errors.size(), errors.slice(0, 3)])
		actor.apply_server_state(dto, _adapter, true)
		for overlay: String in ["MapDot", "Nameplate"]:
			var node := actor.get_node_or_null(overlay) as Node3D
			if node != null: node.hide()
		actor.set_nameplate_visible(false)
		# Corrective shapes enlarge Godot's culling AABB to cover animation
		# extremes. Measure the imported standing geometry for body size;
		# the nameplate may sit higher to clear those animated poses.
		var height: float = _standing_body_bounds(actor).size.y
		if i < 2:
			_expect(absf(height - float(spec["height"])) < 0.15, str(spec["name"]) + " renders at the measured giant height")
			_expect(actor.head_height() >= height, "overhead labels clear the giant body")
			_expect(is_equal_approx(float(actor.get("_small_creature_scale")), 1.0), "giant spider has no tiny-model display boost")
			# An actor rescaled in place must lose the tiny boost again.
			actor.set_server_scale(1.0)
			actor.set_server_scale(float(spec["scale"]))
			_expect(absf(_standing_body_bounds(actor).size.y - height) < 0.01, "size stays correct after an in-place scale update")
		var label := Label3D.new()
		label.text = str(spec["name"]) + "\n" + (str(spec["ad"]) if i < 2 else "Player size reference")
		label.font_size = 52
		label.pixel_size = 0.012
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = actor.position + Vector3(0.0, height + 0.8, 0.0)
		stage.add_child(label)
		readings.append({"name": spec["name"], "rendered_height_m": height, "server_scale": actor.server_scale, "footprint": [shape.x, shape.y]})
	camera.position = Vector3(12.0, 15.0, 24.0)
	camera.look_at(Vector3(12.0, 1.5, 0.0), Vector3.UP)
	for frame: int in range(24): await process_frame
	await _capture("giant-spiders-player-comparison.png", "current spider models at authored size, compared with a player body")
	var report := FileAccess.open(_artifacts.path_join("rendered-sizes.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"failures": _failures, "subjects": readings}, "  "))
	print("giant spider rendering: ", "PASS" if _failures == 0 else "FAIL")
	stage.queue_free()
	main.queue_free()
	for frame: int in range(4): await process_frame
	quit(_failures)

func _standing_body_bounds(actor: Node3D) -> AABB:
	var bounds := AABB()
	var started := false
	var to_actor := actor.global_transform.affine_inverse()
	for node: Node in actor.get_node("NativeModel").find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		var placement := to_actor * mesh_node.global_transform
		for surface: int in mesh_node.mesh.get_surface_count():
			var arrays := mesh_node.mesh.surface_get_arrays(surface)
			for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array:
				var point := placement * vertex
				bounds = bounds.expand(point) if started else AABB(point, Vector3.ZERO)
				started = true
	return bounds
