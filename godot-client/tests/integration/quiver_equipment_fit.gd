extends SceneTree
## Imported quiver fits use a separate part and the live character skeleton.

var checks := 0
var failures := 0
var review_dir := ""
var camera: Camera3D


func _init() -> void:
	call_deferred("run")


func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)


func run() -> void:
	review_dir = OS.get_environment("RL_QUIVER_REVIEW_DIR")
	if not review_dir.is_empty():
		DirAccess.make_dir_recursive_absolute(review_dir)
		root.size = Vector2i(640, 640)
		var environment := WorldEnvironment.new()
		environment.environment = Environment.new()
		environment.environment.background_mode = Environment.BG_COLOR
		environment.environment.background_color = Color("17232c")
		environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color = Color.WHITE
		environment.environment.ambient_light_energy = 0.75
		root.add_child(environment)
		for rotation: Vector3 in [Vector3(-35, 135, 0), Vector3(-20, -40, 0)]:
			var light := DirectionalLight3D.new()
			light.rotation_degrees = rotation
			light.light_energy = 1.1
			root.add_child(light)
		camera = Camera3D.new()
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 2.4
		root.add_child(camera)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	var races: Array = equipment["bodyTemplates"].keys()
	races.sort()
	for race: String in races:
		var model: Dictionary = models[race]
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			model.get("animationMap", "res://data/animations/luminous.json")))
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 9000, "x": 0, "y": 0,
			"rotation": 0, "kind": 1, "name": "", "appearance": {},
			"equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
			model, animations, equipment)
		expect(errors.is_empty(), race + " configures")
		actor.set_process(false)
		actor.set_physics_process(false)
		for visual: int in range(1, 9):
			var label := "%s quiver %d" % [race, visual]
			actor.apply_equipment_visuals({1: 106, 2: 105, 8: visual})
			await process_frame
			var nodes: Array = actor._equipment_nodes.get(8, [])
			expect(not nodes.is_empty(), label + " creates its own equipment part")
			expect(actor._equipment_nodes.has(1) and actor._equipment_nodes.has(2),
				label + " preserves shield and cape")
			expect(int(actor.equipment_diagnostics().get("fallback", -1)) == 0,
				label + " uses shipped models")
			for node: Node in nodes:
				if not node is MeshInstance3D:
					continue
				var mesh_node := node as MeshInstance3D
				expect(mesh_node.skin != null and mesh_node.visible, label + " has a visible skin")
				for bind: int in range(mesh_node.skin.get_bind_count()):
					expect(actor.get_skeleton().find_bone(mesh_node.skin.get_bind_name(bind)) >= 0,
						label + " keeps each joint name")
			if not review_dir.is_empty() and race in ["luminous_male", "ssarathi_female"]:
				actor.apply_equipment_visuals({0: 164, 3: 159, 4: 230, 5: 225, 6: 226, 8: visual})
				await process_frame
			for action: StringName in [&"idle", &"walk", &"ranged_attack"]:
				actor.play_action(action, true)
				expect(not actor.animation_player.current_animation.is_empty(), label + " plays " + action)
				for phase: float in [0.0, 0.25, 0.6]:
					actor.animation_player.seek(phase, true)
					actor.get_skeleton().force_update_all_bone_transforms()
					for bone: int in range(actor.get_skeleton().get_bone_count()):
						expect(actor.get_skeleton().get_bone_global_pose(bone).is_finite(),
							label + " retains finite animated bones")
					if phase == 0.25 and not review_dir.is_empty() and race in ["luminous_male", "ssarathi_female"]:
						await capture(actor, race, visual, action)
			actor.apply_equipment_visuals({1: 106, 2: 105})
			await process_frame
			expect(not actor._equipment_nodes.has(8) and actor._equipment_nodes.has(1),
				label + " removes independently")
		actor.queue_free()
		await process_frame
	NativeAnimationImporter.clear()
	print("QUIVER_EQUIPMENT_FIT checks=", checks, " failures=", failures, " fits=", races.size() * 8)
	quit(1 if failures else 0)


func capture(actor: ReplicatedActor3D, race: String, visual: int, action: StringName) -> void:
	var bounds := AABB()
	var found := false
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if not mesh_node.visible:
			continue
		var box: AABB = mesh_node.global_transform * mesh_node.get_aabb()
		bounds = box if not found else bounds.merge(box)
		found = true
	var center := bounds.get_center()
	camera.size = maxf(bounds.size.y * 1.12, 1.5)
	for side: int in [1, -1]:
		camera.global_position = center + Vector3(0.6, 0.15, side * 4.0)
		camera.look_at(center)
		for _frame: int in range(3):
			await process_frame
		await RenderingServer.frame_post_draw
		var output := "%s/%s-%d-%s-%d.png" % [review_dir, race, visual, action, side]
		expect(root.get_texture().get_image().save_png(output) == OK, output + " saved")
