extends SceneTree
## Set ELORIA_FACE_ARTIFACTS to capture all sixteen native actors, with exact
## default/reset pairs, side views, source-atlas comparisons and exposed hands.

var stage: Node3D
var camera: Camera3D
var output := OS.get_environment("ELORIA_FACE_ARTIFACTS")

func _init() -> void:
	call_deferred("run")

func capture(actor: ReplicatedActor3D, slug: String, mode: String, angle: float) -> void:
	var focus := actor.get_skeleton().global_transform * actor.get_skeleton().get_bone_global_pose(actor.get_skeleton().find_bone("Head")).origin + Vector3(0, 0.085, 0)
	camera.position = focus + Vector3(sin(angle) * 3, 0, cos(angle) * 3)
	camera.look_at(focus)
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join("%s-%s-%d.png" % [slug, mode, roundi(rad_to_deg(angle))]))

func run() -> void:
	if output.is_empty():
		push_error("Set ELORIA_FACE_ARTIFACTS to the output directory")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(700, 800)
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color(0.16, 0.19, 0.22)
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color.WHITE
	world.environment.ambient_light_energy = 0.65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-25, -20, 0)
	light.light_energy = 0.85
	stage.add_child(light)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 0.42
	camera.current = true
	stage.add_child(camera)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for slug: String in models:
		var selected := OS.get_environment("ELORIA_FACE_MODELS")
		if not selected.is_empty() and not slug in selected.split(","):
			continue
		var config: Dictionary = models[slug].duplicate(true)
		if not config.has("bodyTemplate"):
			continue
		var candidates := OS.get_environment("ELORIA_FACE_CANDIDATES")
		if not candidates.is_empty():
			config["scene"] = candidates.path_join(slug + ".glb")
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id": 993, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), config, JSON.parse_string(FileAccess.get_file_as_string(config["animationMap"])), equipment)
		if not errors.is_empty():
			push_error(str(errors))
			quit(1)
			return
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.global_position = Vector3.ZERO
		actor.rotation.y = PI
		actor._advance_facing_offset(1.0)
		actor.animation_player.play("Idle_Subtle")
		actor.animation_player.seek(0.3, true)
		actor.animation_player.pause()
		await process_frame
		for angle: float in [0.0, -0.7, 0.7]:
			await capture(actor, slug, "default", angle)
		if OS.get_environment("ELORIA_FACE_PROFILES") == "1":
			await capture(actor, slug, "default", -PI / 2)
			await capture(actor, slug, "default", PI / 2)
		actor.apply_appearance_variants({"skin": 5, "eyes": 6})
		await capture(actor, slug, "dark", 0)
		actor.apply_appearance_variants({"skin": 0, "eyes": 0})
		await capture(actor, slug, "reset", 0)
		# Inspect skin below the head too: both hands in the canonical rest pose.
		actor.animation_player.play("Rest_Pose")
		actor.animation_player.seek(0, true)
		actor.animation_player.pause()
		await process_frame
		var sk := actor.get_skeleton()
		for hand: String in ["hand_l", "hand_r"]:
			var focus := sk.global_transform * sk.get_bone_global_pose(sk.find_bone(hand)).origin
			camera.size = 0.36
			camera.position = focus + Vector3(0, 0.8, 2)
			camera.look_at(focus)
			await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(output.path_join(slug + "-" + hand + ".png"))
		camera.size = 0.42
		actor.animation_player.play("Idle_Subtle")
		actor.animation_player.seek(0.3, true)
		actor.animation_player.pause()
		await process_frame
		var body := actor.find_child("body", true, false) as MeshInstance3D
		var spec: Dictionary = config["faceAppearance"]
		var surface := int(spec["sourceSurface"])
		body.material_override = null
		body.set_surface_override_material(surface, body.mesh.surface_get_material(surface))
		for n: Node in actor.find_children("*", "MeshInstance3D", true, false):
			if n.name in ["eyes", "eyebrows", "scalp"]:
				var mesh := n as MeshInstance3D
				mesh.material_override = mesh.mesh.surface_get_material(0) if spec.has("groups") else body.mesh.surface_get_material(surface)
		await capture(actor, slug, "source", 0)
		actor.free()
		await process_frame
		print("FACE_CAPTURE ", slug)
	NativeAnimationImporter.clear()
	quit()
