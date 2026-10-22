extends "res://tests/integration/rendered_giant_spiders.gd"
## RL_GIANT_SPEC contains sizes exported from the current server definitions.
## Groups of up to four creatures beside the same player body.
## RL_GIANT_CAPTURE_PREFIX optionally names a separate comparison artifact.

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN_SIZE
	_adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	var subjects: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_GIANT_SPEC"))) as Array
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")) as Dictionary
	var readings: Array = []
	var prefix := OS.get_environment("RL_GIANT_CAPTURE_PREFIX")
	if prefix.is_empty(): prefix = "giant-creatures"
	for batch: int in range(ceili(float(subjects.size()) / 4.0)):
		var stage := Node3D.new()
		root.add_child(stage)
		_light(stage)
		var camera := Camera3D.new()
		camera.current = true
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 16.0
		stage.add_child(camera)
		var group: Array = subjects.slice(batch * 4, batch * 4 + 4)
		var creature_count := group.size()
		group.append({"name": "Adventurer", "actor_type": 1, "scale": 1.0, "footprint": [1,1]})
		for index: int in range(group.size()):
			var spec: Dictionary = group[index] as Dictionary
			var creature := index < creature_count
			var anchor := 3 + index * 5
			var shape := Vector2i(int(spec["footprint"][0]), int(spec["footprint"][1]))
			_draw_reserved_ground(stage, anchor, 0, shape)
			var dto: Dictionary = main.call("_presentation_dto", {
				"actor_id": 100 + index, "x": anchor, "y": 0, "rotation": 0,
				"actor_type": int(spec["actor_type"]), "kind": 1 if creature else 0,
				"name": spec["name"], "health": 100, "max_health": 100, "frame": 0,
				"scale": float(spec["scale"]), "appearance": {}}) as Dictionary
			dto["footprint"] = shape
			var model_key: String = str((registry["actorTypes"] as Dictionary)[str(int(spec["actor_type"]))])
			var config: Dictionary = (registry["models"] as Dictionary)[model_key] as Dictionary
			var actor := ReplicatedActor3D.new()
			stage.add_child(actor)
			var errors := actor.configure(dto, _adapter, config,
				main.call("_animation_for_model", config) as Dictionary, main.get("equipment_config") as Dictionary)
			_expect(errors.is_empty(), "%s builds (%d errors): %s" % [spec["name"], errors.size(), errors.slice(0,3)])
			actor.apply_server_state(dto, _adapter, true)
			actor.set_nameplate_visible(false)
			for overlay: String in ["MapDot", "Nameplate"]:
				var node := actor.get_node_or_null(overlay) as Node3D
				if node != null: node.hide()
			var size := _standing_body_bounds(actor).size
			if creature:
				var expected: Dictionary = spec["dimensions"] as Dictionary
				_expect(absf(size.x-float(expected["width"])) < 0.05 and
					absf(size.y-float(expected["height"])) < 0.05 and
					absf(size.z-float(expected["depth"])) < 0.05, str(spec["name"]) + " matches authored dimensions")
				_expect(is_equal_approx(float(actor.get("_small_creature_scale")),1.0), "large creature loses the tiny-body boost")
				actor.set_server_scale(1.0)
				actor.set_server_scale(float(spec["scale"]))
				_expect(_standing_body_bounds(actor).size.is_equal_approx(size), "size survives an in-place update")
			var label := Label3D.new()
			label.text = str(spec["name"]) + "\n" + (str(spec["ad"]) if creature else "Player size reference")
			label.font_size = 42
			label.pixel_size = 0.012
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.position = actor.position + Vector3(0.0,size.y+1.0,0.0)
			stage.add_child(label)
			readings.append({"name":spec["name"],"width":size.x,"height":size.y,"depth":size.z,"scale":actor.server_scale})
		camera.position = Vector3(13.0,12.0,22.0)
		camera.look_at(Vector3(13.0,1.0,0.0),Vector3.UP)
		for frame: int in range(24): await process_frame
		await _capture("%s-%d.png" % [prefix,batch+1],"current enlarged creatures beside a player")
		stage.queue_free()
		for frame: int in range(3): await process_frame
	var report := FileAccess.open(_artifacts.path_join("rendered-sizes.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"failures":_failures,"subjects":readings},"  "))
	main.queue_free()
	for frame: int in range(4): await process_frame
	print("giant creature rendering: ","PASS" if _failures == 0 else "FAIL")
	quit(_failures)
