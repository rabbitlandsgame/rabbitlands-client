extends SceneTree
## Compare the real creature bodies with their original import size and check
## that health/name anchors follow the larger body through server scale changes.
var failures := 0
var models: Dictionary
var stage: Node3D
var adapter := CoordinateAdapter.new()

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	models = (JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json")) as Dictionary).models
	stage = Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("665b46")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.7
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	stage.add_child(light)
	var camera := Camera3D.new()
	camera.fov = 50.0
	camera.cull_mask = 3
	camera.position = Vector3(0, 6, 12)
	stage.add_child(camera)
	camera.look_at(Vector3(0, 0.8, 0))
	camera.current = true
	var index := 0
	for species: String in ["rabbit", "gecko", "dormouse", "shrew", "red_fox", "black_bear"]:
		var original := _actor(species, 2)
		var enlarged := _actor(species, 5)
		original.position = Vector3(-5.5 + index * 2.2, 0, -1.5)
		enlarged.position = Vector3(-5.5 + index * 2.2, 0, 1.5)
		var original_model := original.get_node("NativeModel") as Node3D
		var enlarged_model := enlarged.get_node("NativeModel") as Node3D
		var multiplier := 1.0 if species == "black_bear" else 2.0
		if species in ["gecko", "dormouse", "shrew"]:
			var authored_bounds: AABB = original.get("_native_body_bounds")
			var original_size := authored_bounds.size * original_model.scale
			multiplier = 0.7 / maxf(original_size.x, maxf(original_size.y, original_size.z))
		_expect(enlarged_model.scale.is_equal_approx(original_model.scale * multiplier),
			"%s body scale: %.1fx" % [species, multiplier])
		var initial_height := enlarged.head_height()
		enlarged.set_server_scale(3.0)
		_expect(enlarged_model.scale.is_equal_approx(original_model.scale * multiplier * 3),
			"%s server scaling preserves the species boost" % species)
		enlarged.set_server_scale(1.0)
		_expect(is_equal_approx(initial_height, enlarged.head_height()),
			"%s restores its body height without compounding the boost" % species)
		var nameplate := enlarged.get_node("Nameplate") as Label3D
		_expect(is_equal_approx(nameplate.position.y,
			enlarged.head_height() + ReplicatedActor3D.NAMEPLATE_CLEARANCE),
			"%s label clears its enlarged body" % species)
		_expect(nameplate.modulate == Color.YELLOW and not nameplate.shaded,
			"%s uses full-bright yellow text" % species)
		_expect(nameplate.outline_size == 0, "%s uses the reference's plain letters" % species)
		var health := enlarged.get_node("HealthNumbers") as Label3D
		var fill := (enlarged.get_node("HealthBarFill") as MeshInstance3D).mesh as QuadMesh
		_expect(health.modulate == Color.GREEN, "full health numbers use saturated green")
		_expect(health.offset.x > 0.0 and fill.center_offset.x < 0.0,
			"health numbers sit beside the bar")
		_expect(is_equal_approx(health.offset.y * health.pixel_size,
			fill.center_offset.y), "health numbers and bar share one row")
		_expect((enlarged.get_node("OverheadBackground") as MeshInstance3D).visible,
			"the name and health share a dark backing")
		var original_left: float = fill.center_offset.x - fill.size.x * 0.5
		enlarged.apply_vitals(5, 10)
		_expect(is_equal_approx(fill.center_offset.x - fill.size.x * 0.5, original_left),
			"the health bar drains from the right without jumping at digit boundaries")
		_expect(health.modulate.is_equal_approx(Color(1.0, 0.8, 0.0)),
			"half health uses the Eternal Lands yellow-orange ramp")
		_expect(health.modulate.is_equal_approx(
			(fill.material as StandardMaterial3D).albedo_color),
			"health numbers match their bar at partial health")
		enlarged.apply_vitals(10, 10)
		enlarged.set_overhead_fade(0.5)
		_expect(is_equal_approx(nameplate.modulate.a, 0.5), "distance fade still applies")
		_expect(is_equal_approx(((enlarged.get_node("OverheadBackground")
			as MeshInstance3D).mesh as QuadMesh).material.albedo_color.a, 0.225),
			"the dark backing fades with its text")
		enlarged.set_overhead_fade(1.0)
		index += 1
	var invasion := _actor("rabbit", 5, 14)
	_expect((invasion.get_node("Nameplate") as Label3D).modulate
		== EloriaProtocol.el_text_colour(14), "invasion names retain their server color")
	invasion.queue_free()
	if DisplayServer.get_name() != "headless":
		for frame: int in range(16):
			await process_frame
		await RenderingServer.frame_post_draw
		var picture := root.get_texture().get_image()
		var bright_pixels := 0
		for y: int in range(picture.get_height()):
			for x: int in range(picture.get_width()):
				var color := picture.get_pixel(x, y)
				if color.r > 0.9 and color.g > 0.9 and color.b < 0.2:
					bright_pixels += 1
		_expect(bright_pixels > 100, "render contains bright yellow creature lettering")
		var path := OS.get_environment("ELORIA_ARTIFACT_DIR")
		if not path.is_empty():
			DirAccess.make_dir_recursive_absolute(path)
			picture.save_png(path.path_join("small-creatures.png"))
	print("small creature presentation: ", "PASS" if failures == 0 else "FAIL")
	stage.queue_free()
	await process_frame
	quit(failures)

func _actor(species: String, kind: int, name_colour := 0) -> ReplicatedActor3D:
	var config: Dictionary = models[species]
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure({"actor_id": stage.get_child_count(), "x": 0,
		"y": 0, "rotation": 0, "kind": kind, "name_colour": name_colour,
		"name": species.capitalize(), "health": 10, "max_health": 10}, adapter,
		config, JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
	_expect(errors.is_empty(), "%s loads: %s" % [species, errors])
	actor.set_physics_process(false)
	actor.set_health_visible(true)
	return actor

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
