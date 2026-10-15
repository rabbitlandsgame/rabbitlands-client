extends SceneTree
## Deterministic actual-client contact sheets. ELORIA_PALETTE_MODE is skin or
## hair; ELORIA_PALETTE_SLUGS optionally restricts the roster (comma separated).

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(400, 400)
	var folder := OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(folder)
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.13, 0.16, 0.19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.9, 0.93, 1)
	environment.environment.ambient_light_energy = 0.65
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.2
	stage.add_child(light)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = .64
	stage.add_child(camera)
	camera.current = true
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var mode := OS.get_environment("ELORIA_PALETTE_MODE")
	var selected := OS.get_environment("ELORIA_PALETTE_SLUGS").split(",", false)
	var manifest: Array = []
	for slug: String in models:
		var config: Dictionary = models[slug]
		if not config.has("bodyTemplate") or (not selected.is_empty() and not slug in selected):
			continue
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id": 9010, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), config, JSON.parse_string(FileAccess.get_file_as_string(config["animationMap"])), equipment)
		if not errors.is_empty():
			push_error(str(errors))
			quit(1)
			return
		actor.server_target = Vector3.ZERO
		actor.global_position = Vector3.ZERO
		actor.rotation.y = PI
		actor.set_process(false)
		actor.set_physics_process(false)
		for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
			(marker as MeshInstance3D).hide()
		actor._advance_facing_offset(1.0)
		actor.animation_player.play("Idle_Subtle")
		actor.animation_player.seek(.3, true)
		actor.animation_player.pause()
		await process_frame
		var skeleton := actor.get_skeleton()
		var focus := (skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Head"))).origin + Vector3(0, .025, 0)
		var choices := AppearanceChoices.options("hair" if mode == "hair" else "skin")
		for choice: Dictionary in choices:
			var appearance := {"skin": 1, "hair": AppearanceVariants.pack_hair(0, 2), "eyes": 0}
			appearance["skin" if mode != "hair" else "hair"] = int(choice.id) if mode != "hair" else AppearanceVariants.pack_hair(int(choice.id), 2)
			actor.apply_appearance_variants(appearance)
			for angle: String in (["front", "back"] if mode == "hair" else ["front"]):
				camera.position = focus + (Vector3(.6, .12, 1) if angle == "front" else Vector3(-.6, .12, -1))
				camera.look_at(focus)
				await process_frame
				await RenderingServer.frame_post_draw
				var name := "%s-%s-%02d-%s.png" % [slug, mode, choice.id, angle]
				root.get_texture().get_image().save_png(folder.path_join(name))
				manifest.append({"file": name, "slug": slug, "mode": mode, "id": choice.id, "label": choice.label, "angle": angle, "color": (choice.color as Color).to_html(false) if choice.has("color") else ""})
		actor.free()
		await process_frame
		print("PALETTE_PREVIEW ", slug, " ", mode)
	FileAccess.open(folder.path_join("manifest-" + mode + ".json"), FileAccess.WRITE).store_string(JSON.stringify(manifest, "\t"))
	NativeAnimationImporter.clear()
	quit()
