extends SceneTree
## Real actor, animation, appearance and helmet transitions. Optional candidate
## directory and rendered evidence via ELORIA_APPEARANCE_CANDIDATES / _ARTIFACTS.

var failures := 0
var checks := 0
var stage: Node3D
var camera: Camera3D
var output := ""

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func hairs(actor: ReplicatedActor3D) -> Array[Node]:
	return actor.get_skeleton().get_children().filter(func(n: Node) -> bool:
		return n.name.begins_with("AppearanceHair_"))

func capture(actor: ReplicatedActor3D, name: String, back: bool, clip := "Idle_Subtle", time := 0.3) -> void:
	if output.is_empty():
		return
	camera.position = Vector3(1.8, 2.0, -3.8) if back else Vector3(0, 1.2, 4)
	camera.look_at(Vector3(0, 1.25, 0))
	actor.animation_player.play(clip)
	actor.animation_player.seek(time, true)
	actor.animation_player.pause()
	await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name + ".png")) == OK, name + " captured")

func run() -> void:
	output = OS.get_environment("ELORIA_APPEARANCE_ARTIFACTS")
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(700, 800)
	stage = Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.16, 0.19, 0.22)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.75
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.2
	stage.add_child(light)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 1.65
	camera.current = true
	stage.add_child(camera)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var candidates := OS.get_environment("ELORIA_APPEARANCE_CANDIDATES")
	var count := 0
	for slug: String in models:
		var config: Dictionary = models[slug].duplicate(true)
		if not config.has("bodyTemplate"):
			continue
		if not candidates.is_empty():
			config["scene"] = candidates.path_join(slug + ".glb")
			config.merge(JSON.parse_string(FileAccess.get_file_as_string(candidates.path_join(slug + ".config.json"))), true)
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config["animationMap"]))
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id": 993, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({"walkingHeight": 0.0}), config, animations, equipment)
		expect(errors.is_empty(), slug + " configures: " + str(errors))
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.global_position = Vector3.ZERO
		actor.rotation.y = PI
		actor._advance_facing_offset(1.0)
		for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
			marker.hide()
		for style: int in [0, 1, 2, 3, 0, 1, 0, 4]:
			actor.apply_appearance_variants({"hair": style})
			var bald := AppearanceVariants.hair_style(style) == 0
			expect(hairs(actor).size() == (0 if bald else 1), slug + " immediate hair transition " + str(style))
			for n: Node in actor.find_children("wardrobe_shirt", "MeshInstance3D", true, false):
				var mesh := n as MeshInstance3D
				for surface in range(mesh.mesh.get_surface_count()):
					var mat := mesh.get_active_material(surface) as StandardMaterial3D
					expect(mat != null and not mat.grow, slug + " baked shirt is not grown twice")
			if style < 4:
				await capture(actor, "%s-%d-back" % [slug, style], true)
				await capture(actor, "%s-%d-front" % [slug, style], false)
			actor.apply_equipment_visuals({3: 133})
			for attachment: Node in hairs(actor):
				expect(not (attachment as Node3D).visible, slug + " helmet covers hair")
			for headgear: int in [122, 159]:
				actor.apply_equipment_visuals({3: headgear})
				for scalp: Node in actor.find_children("scalp", "MeshInstance3D", true, false):
					expect((scalp as MeshInstance3D).visible, slug + " headgear preserves the scalp " + str(headgear))
			actor.apply_equipment_visuals({})
			expect(hairs(actor).size() == (0 if bald else 1), slug + " helmet removal preserves bald choice")
			for attachment: Node in hairs(actor):
				expect((attachment as Node3D).visible, slug + " helmet restores hair")
		actor.apply_appearance_variants({"hair": 1})
		await capture(actor, slug + "-walk-back", true, "Walk", 0.3)
		await capture(actor, slug + "-run-back", true, "Run_Female", 0.2)
		actor.free()
		await process_frame
		count += 1
		print("APPEARANCE: ", slug, " complete, ", failures, " failures")
	expect(count == 16, "all sixteen character variants")
	print("APPEARANCE: %d variants, %d checks, %d failures" % [count, checks, failures])
	NativeAnimationImporter.clear()
	quit(1 if failures else 0)
