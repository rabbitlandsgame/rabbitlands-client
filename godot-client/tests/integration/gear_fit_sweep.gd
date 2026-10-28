extends SceneTree
## Render the whole shared torso wardrobe and the four complete starter kits.
## ELORIA_GEAR_REGISTRY can select a candidate registry before installation.
## ELORIA_GEAR_ARTIFACTS enables images; headless runs still check bindings.

var stage: Node3D
var camera: Camera3D
var output := ""
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func capture(actor: ReplicatedActor3D, name: String, side := false, clip := "Idle_Subtle", full := false) -> void:
	actor.animation_player.play(clip)
	actor.animation_player.seek(.30, true)
	actor.animation_player.pause()
	if output.is_empty():
		return
	var focus := Vector3(0., .95 if full else 1.28, 0.)
	camera.size = 2.25 if full else 1.10
	camera.position = focus + (Vector3(4., .05, 0.) if side else Vector3(0., .05, 4.))
	camera.look_at(focus)
	await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name + ".png")) == OK, name + " captures")

func make_actor(slug: String, model: Dictionary, animations: Dictionary, equipment: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure({"actor_id": 902, "kind": 1, "name": "", "x": 0, "y": 0,
		"rotation": 0, "appearance": {"hair": 1}, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.}), model, animations, equipment)
	expect(errors.is_empty(), slug + " configures " + str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.global_position = Vector3.ZERO
	actor.rotation.y = PI
	actor._advance_facing_offset(1.)
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	return actor

## Whether this run draws the RL head for a Human at High (the renderer
## supports it and RL_HEADS is not classic). Otherwise develop's expectations
## hold unchanged, whatever the actor built.
static func rl_heads_on() -> bool:
	return ReplicatedActor3D.rl_heads_renderer_supported() and not ReplicatedActor3D.rl_heads_classic()

func run() -> void:
	output = OS.get_environment("ELORIA_GEAR_ARTIFACTS")
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(640, 760)
	stage = Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(.13, .16, .19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = .75
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.2
	stage.add_child(light)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.current = true
	stage.add_child(camera)
	var registry_path := OS.get_environment("ELORIA_GEAR_REGISTRY")
	if registry_path.is_empty():
		registry_path = "res://data/actors/equipment.json"
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(registry_path))
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var kits := [
		["vanguard", {0: 114, 1: 106, 3: 134, 4: 220, 5: 209, 6: 249}],
		["ranger", {0: 164, 3: 159, 4: 230, 5: 225, 6: 226}],
		["arcanist", {0: 142, 3: 115, 4: 185, 5: 222, 6: 198}],
		["warden", {0: 163, 3: 122, 4: 176, 5: 189, 6: 205}]]
	var torso_visuals: Array[int] = []
	for key: String in equipment["models"]:
		var model: Dictionary = equipment["models"][key]
		if key.begins_with("5:") and model.get("fitProfile", "") == "canonical":
			torso_visuals.append(int(key.get_slice(":", 1)))
	torso_visuals.sort()
	expect(torso_visuals.size() == 64, "all 64 generated torso designs")
	for slug: String in models:
		if not models[slug].has("bodyTemplate"):
			continue
		for kit: Array in kits:
			# Starter characters begin fresh. Class props from the previous
			# preview (such as the ranger bow) must not enter the next image.
			var actor := make_actor(slug, models[slug], animations, equipment)
			actor.apply_equipment_visuals(kit[1])
			var diagnostics := actor.equipment_diagnostics()
			expect(diagnostics["visuals"] == kit[1] and diagnostics["fallback"] == 0,
				slug + " complete " + str(kit[0]) + " kit")
			if equipment["models"]["3:" + str(kit[1][3])].get("raceFeatures", "") == "show":
				# Under the RL head (a Human at High) its cranium closes the head.
				var rl_head: RLHeadRig = actor.rl_head() if rl_heads_on() else null
				for scalp: Node in actor.find_children("scalp", "MeshInstance3D", true, false):
					expect((scalp as MeshInstance3D).visible != (rl_head != null), slug + " " + str(kit[0]) + " preserves the head")
				if rl_head != null:
					var head: Array = rl_head.mesh_nodes()["head"]
					expect(not head.is_empty() and (head[0][0] as MeshInstance3D).is_visible_in_tree(),
						slug + " " + str(kit[0]) + " keeps the RL cranium")
			for hair: Node in actor.get_skeleton().get_children():
				if hair.name.begins_with("AppearanceHair_"):
					expect(not (hair as Node3D).visible, slug + " headgear covers hair")
			if slug.begins_with("luminous_"):
				await capture(actor, "kit-" + slug + "-" + str(kit[0]), false, "Idle_Subtle", true)
				await capture(actor, "kit-" + slug + "-" + str(kit[0]) + "-side", true, "Idle_Subtle", true)
				await capture(actor, "kit-" + slug + "-" + str(kit[0]) + "-walk", false, "Walk", true)
			actor.free()
			await process_frame
		if slug.begins_with("luminous_"):
			var actor := make_actor(slug, models[slug], animations, equipment)
			for visual: int in torso_visuals:
				actor.apply_equipment_visuals({5: visual})
				var diagnostics := actor.equipment_diagnostics()
				expect(diagnostics["visuals"] == {5: visual} and diagnostics["fallback"] == 0,
					slug + " torso " + str(visual) + " binds")
				await capture(actor, "torso-" + slug + "-" + str(visual))
				await capture(actor, "torso-" + slug + "-" + str(visual) + "-walk-side", true, "Walk")
			actor.free()
			await process_frame
		print("GEAR FIT: ", slug, ", ", failures, " failures")
	NativeAnimationImporter.clear()
	print("GEAR FIT: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)
