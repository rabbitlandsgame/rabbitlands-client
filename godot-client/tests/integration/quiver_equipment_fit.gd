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
	var review_fits := OS.get_environment("RL_QUIVER_REVIEW_FITS")
	if not review_fits.is_empty():
		for visual: int in range(1, 9):
			var row: Dictionary = equipment["models"]["8:%d" % visual]
			for variant: Dictionary in row["variants"].values():
				variant["scene"] = review_fits.path_join("variants").path_join(
					str(variant["authoredFor"])).path_join(
					"rl-quiver-%s.glb" % ["basic", "hunter", "bodkin", "farshot",
						"skirmisher", "ember", "frost", "arcane"][visual - 1])
	var races: Array = equipment["bodyTemplates"].keys()
	races.sort()
	var review_races := OS.get_environment("RL_QUIVER_REVIEW_RACES")
	if not review_races.is_empty():
		races = Array(review_races.split(",", false))
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
			check_chest_layers(actor, visual, label)
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
				var cape_shape := mesh_node.find_blend_shape_by_name("Cape_Clearance")
				if visual != 1:
					expect(cape_shape >= 0, label + " carries its authored cape clearance")
				if cape_shape >= 0:
					expect(is_equal_approx(mesh_node.get_blend_shape_value(cape_shape), 1.0),
						label + " selects the cape-on fit")
				for bind: int in range(mesh_node.skin.get_bind_count()):
					expect(actor.get_skeleton().find_bone(mesh_node.skin.get_bind_name(bind)) >= 0,
						label + " keeps each joint name")
			actor.apply_equipment_visuals({1: 106, 8: visual})
			for node: Node in nodes:
				if node is MeshInstance3D:
					var mesh_node := node as MeshInstance3D
					expect(actor._equipment_nodes[8].has(mesh_node), label + " retains its mesh when cape is removed")
					var shape := mesh_node.find_blend_shape_by_name("Cape_Clearance")
					if shape >= 0:
						expect(is_zero_approx(mesh_node.get_blend_shape_value(shape)), label + " returns to its cape-off fit")
			actor.apply_equipment_visuals({1: 106, 2: 105, 8: visual})
			if not review_dir.is_empty() and race in ["luminous_male", "ssarathi_female"]:
				actor.apply_equipment_visuals({0: 164, 2: 105, 3: 159, 4: 230, 5: 225, 6: 226, 8: visual})
				await process_frame
			for action: StringName in [&"idle", &"walk", &"ranged_attack"]:
				actor.play_action(action, true)
				expect(not actor.animation_player.current_animation.is_empty(), label + " plays " + action)
				for phase: float in [0.0, 0.25, 0.6]:
					actor.animation_player.seek(phase, true)
					actor.get_skeleton().force_update_all_bone_transforms()
					for node: Node in nodes:
						if node is MeshInstance3D:
							var shape := (node as MeshInstance3D).find_blend_shape_by_name("Cape_Clearance")
							if shape >= 0:
								expect(is_equal_approx((node as MeshInstance3D).get_blend_shape_value(shape), 1.0),
									label + " keeps cape clearance during " + action)
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


func check_chest_layers(actor: ReplicatedActor3D, visual: int, label: String) -> void:
	var nodes: Array = actor._equipment_nodes[8].duplicate()
	var cached: Dictionary = {}
	var originals: Dictionary = {}
	for node: Node in nodes:
		if node is MeshInstance3D:
			var source: Mesh = node.get_meta("quiver_authored_mesh") as Mesh
			originals[node] = hash(source.surface_get_arrays(0)[Mesh.ARRAY_VERTEX])
	for armor: int in [0, 225, 200, 225]:
		for cape: int in [0, 105]:
			var outfit := {1: 106, 8: visual}
			if armor: outfit[5] = armor
			if cape: outfit[2] = cape
			actor.apply_equipment_visuals(outfit)
			for node: Node in nodes:
				if not node is MeshInstance3D:
					continue
				var quiver := node as MeshInstance3D
				expect(actor._equipment_nodes[8].has(quiver), label + " retains its quiver while changing clothing")
				var source: Mesh = quiver.get_meta("quiver_authored_mesh") as Mesh
				# The actor's existing body-proportion pass follows strap fitting.
				# Inspect its retained input for the strap-only preservation contract;
				# the live mesh below still checks final geometry and repeated swaps.
				var fitted: Mesh = quiver.get_meta("human_body_refinement_source", quiver.mesh) as Mesh
				if armor == 0 and cape == 0:
					expect(fitted == source, label + " restores its authored bare fit")
				var key := "%d:%d:%d" % [armor, cape, node.get_instance_id()]
				var signature: Array = []
				for surface: int in range(quiver.mesh.get_surface_count()):
					signature.append(hash(quiver.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]))
				if cached.has(key):
					expect(signature == cached[key], label + " restores its fit without accumulating offsets")
				cached[key] = signature
				var preserved := true
				var finite := true
				var cape_neutral := true
				var largest_front_offset := 0.0
				for surface: int in range(source.get_surface_count()):
					var before: PackedVector3Array = source.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
					var after: PackedVector3Array = fitted.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
					var displayed: PackedVector3Array = quiver.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
					for vertex: int in range(before.size()):
						finite = finite and after[vertex].is_finite() and displayed[vertex].is_finite()
						# The short strap crossing the shoulder now also clears the
						# roof of armor. The rear case and attachments remain exact.
						var head := actor.get_skeleton().find_bone("Head")
						var stature := actor.get_skeleton().get_bone_global_rest(head).origin.y / 1.568490028858185
						var shoulder := actor.get_skeleton().get_bone_global_rest(actor.get_skeleton().find_bone("upperarm_r")).origin.y
						var shoulder_band := (before[vertex].z >= -0.10 * stature
							and before[vertex].y >= shoulder - 0.065 * stature
							and before[vertex].y <= shoulder + 0.12 * stature)
						if before[vertex].z <= 0.0 and not shoulder_band:
							preserved = preserved and before[vertex].is_equal_approx(after[vertex])
						else:
							largest_front_offset = maxf(largest_front_offset, after[vertex].z - before[vertex].z)
					if fitted is ArrayMesh and (fitted as ArrayMesh).blend_shape_mode == Mesh.BLEND_SHAPE_MODE_NORMALIZED:
						for shape: Array in fitted.surface_get_blend_shape_arrays(surface):
							var positions: PackedVector3Array = shape[Mesh.ARRAY_VERTEX]
							for vertex: int in range(before.size()):
								if before[vertex].z > 0.06:
									cape_neutral = cape_neutral and after[vertex].is_equal_approx(positions[vertex])
					expect(preserved, label + " preserves its rear case and attachments over clothing")
					expect(finite, label + " keeps finite clothing clearance")
					expect(cape_neutral, label + " keeps chest clearance when selecting the cape shape")
				if armor:
					expect(largest_front_offset > 0.00001, label + " lifts its chest strap over worn armor")
	for node: Node in originals:
		var source: Mesh = node.get_meta("quiver_authored_mesh") as Mesh
		expect(hash(source.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]) == originals[node],
			label + " leaves its shared authored mesh unchanged")
	actor.apply_equipment_visuals({1: 106, 2: 105, 8: visual})


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
