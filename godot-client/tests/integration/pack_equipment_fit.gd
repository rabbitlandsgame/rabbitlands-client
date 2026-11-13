extends SceneTree
## Exercise real cape-slot lifecycle, rebound skins, armor and animation poses.
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var races: Array = equipment["bodyTemplates"].keys()
	races.sort()
	for race: String in races:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
		var errors := actor.configure({"actor_id": 9000, "x": 0, "y": 0,
			"rotation": 0, "kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[race], animations, equipment)
		expect(errors.is_empty(), race + " configures")
		actor.set_process(false)
		actor.set_physics_process(false)
		for visual: int in [151, 152]:
			var label := "%s pack %d" % [race, visual]
			var signatures := {}
			for armor: int in [0, 225, 200, 225, 0]:
				var outfit := {2: visual, 8: 1}
				if armor: outfit[5] = armor
				actor.apply_equipment_visuals(outfit)
				await process_frame
				expect(not actor._cape_cloth_worn and not actor.wears_cape_cloth(), label + " stays rigid")
				expect(actor._equipment_nodes.has(8), label + " retains quiver")
				expect(int(actor.equipment_diagnostics().get("fallback", -1)) == 0, label + " has no fallback")
				var nodes: Array = actor._equipment_nodes.get(2, [])
				expect(not nodes.is_empty(), label + " creates cape-slot geometry")
				var signature := []
				for node: Node in nodes:
					if not node is MeshInstance3D: continue
					var mesh := node as MeshInstance3D
					expect(mesh.skin != null and mesh.visible, label + " has visible skin")
					for bind: int in mesh.skin.get_bind_count():
						expect(actor.get_skeleton().find_bone(mesh.skin.get_bind_name(bind)) >= 0, label + " named bind")
					for surface: int in mesh.mesh.get_surface_count():
						var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
						var finite := true
						for vertex: Vector3 in vertices: finite = finite and vertex.is_finite()
						expect(finite, label + " finite fitted vertices")
						signature.append(hash(vertices))
				if signatures.has(armor): expect(signature == signatures[armor], label + " repeats armor fit without drift")
				signatures[armor] = signature
				for action: StringName in [&"idle", &"walk", &"run", &"ranged_attack", &"attack_primary"]:
					actor.play_action(action, true)
					expect(not actor.animation_player.current_animation.is_empty(), label + " plays " + action)
					for phase: float in [0.0, 0.25, 0.6]:
						actor.animation_player.seek(phase, true)
						actor.get_skeleton().force_update_all_bone_transforms()
						var finite := true
						for bone: int in actor.get_skeleton().get_bone_count():
							finite = finite and actor.get_skeleton().get_bone_global_pose(bone).is_finite()
						expect(finite, label + " finite " + action)
						for node: Node in nodes:
							if node is MeshInstance3D:
								expect(finite_skin(node as MeshInstance3D, actor.get_skeleton()), label + " bounded animated skin " + action)
			actor.apply_equipment_visuals({8: 1})
		await process_frame
		expect(actor._equipment_nodes.has(8) and not actor._equipment_nodes.has(2), race + " removes pack independently")
		actor.apply_equipment_visuals({2: 140})
		expect(actor.wears_cape_cloth(), race + " restores ordinary cape cloth")
		actor.queue_free()
		await process_frame
	NativeAnimationImporter.clear()
	print("PACK_EQUIPMENT_FIT checks=", checks, " failures=", failures, " fits=", races.size()*2)
	quit(1 if failures else 0)

func finite_skin(instance: MeshInstance3D, skeleton: Skeleton3D) -> bool:
	var matrices: Array[Transform3D] = []
	for bind: int in instance.skin.get_bind_count():
		var bone := skeleton.find_bone(instance.skin.get_bind_name(bind))
		matrices.append(skeleton.get_bone_global_pose(bone) * instance.skin.get_bind_pose(bind))
	for surface: int in instance.mesh.get_surface_count():
		var arrays := instance.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var stride := bones.size() / maxi(vertices.size(), 1)
		for vertex: int in range(0, vertices.size(), 137):
			var point := Vector3.ZERO
			var total := 0.0
			for slot: int in stride:
				var at := vertex * stride + slot
				point += (matrices[bones[at]] * vertices[vertex]) * weights[at]
				total += weights[at]
			if not point.is_finite() or point.length() > 4.0 or absf(total - 1.0) > 0.001:
				return false
	return true
