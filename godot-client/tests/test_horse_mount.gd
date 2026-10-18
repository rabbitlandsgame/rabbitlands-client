extends SceneTree
var checks := 0
var failures := 0
var max_contact_error := 0.0
var max_cape_link_error := 0.0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models[body]
		var errors := actor.configure({"actor_id": 42, "x": 30, "y": 20, "rotation": 0,
			"kind": 1, "name": "", "appearance": {"hair": 0}, "equipment_visuals": {2: 1}},
			CoordinateAdapter.new(), config, JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)), equipment)
		expect(errors.is_empty(), body + " equipped rider loads")
		actor.set_physics_process(false)
		actor.set_process(false)
		actor.rotation.y = .8
		var authoritative := actor.global_transform
		var native := actor.get_node("NativeModel") as Node3D
		var original := native.transform
		var skeleton := actor.get_skeleton()
		for gait: String in ["walk", "cruise", "burst"]:
			actor.set_mount_state({"mode": "mounted", "mount_id": "golden_plains_horse", "gait": gait}, models)
			expect(is_instance_valid(actor._mount_visual), "horse mounts with " + body)
			var visual: Variant = actor._mount_visual
			visual.set_process(false)
			expect(visual.pony.rig_name() == "golden_plains_horse", "uses the actual imported horse")
			expect(visual.tack.triangle_count == 638, "borrowed saddle matches the independently counted source triangles")
			expect(actor.get_skeleton() == skeleton, "mounted rider retains the same body and equipment rig")
			var fitted := (visual.tack.get_child(0) as MeshInstance3D).mesh
			var normals: PackedVector3Array = fitted.surface_get_arrays(0)[Mesh.ARRAY_NORMAL]
			for normal: Vector3 in normals:
				expect(absf(normal.length() - 1.0) < .0001, "fitted saddle normals stay normalized")
			var bounds := fitted.get_aabb()
			actor._presentation_speed = {"walk": 1.67, "cruise": 5.0, "burst": 7.5}[gait]
			actor.play_action(&"run")
			for frame: int in 120:
				visual._process(1.0 / 60.0)
				expect(actor.global_transform.is_equal_approx(authoritative), "riding preserves server position and camera target")
				for endpoint: String in visual.pose.last_errors:
					var error: float = visual.pose.last_errors[endpoint]
					max_contact_error = maxf(max_contact_error, error)
					expect(error < .06, body + " " + gait + " rider contact " + endpoint + ": " + str(error))
				expect(fitted.get_aabb() == bounds, "saddle and blanket dimensions do not change with gait")
				for side: String in ["l", "r"]:
					var points: PackedVector3Array = visual.reins.last_points[side]
					var grip: Vector3 = visual.reins.grip_world(skeleton, side)
					expect(visual.reins.to_global(points[-1]).distance_to(grip) < .00001, "reins stay in the riding fingers")
				for chain: int in 3:
					var points: PackedVector3Array = actor._cape_cloth.get("_points")[chain]
					var lengths: PackedFloat32Array = actor._cape_cloth.get("_lengths")[chain]
					for link: int in range(1, points.size()):
						max_cape_link_error = maxf(max_cape_link_error, absf(points[link].distance_to(points[link - 1]) - lengths[link - 1]))
				expect(actor._cape_cloth != null and not actor._cape_cloth.active, "cape receives one ordered mounted pass")
			actor.set_mount_state({}, models)
			expect(native.transform.is_equal_approx(original), "dismount restores the rider's native transform")
		actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "cruise"}, models)
		actor.set_mount_state({"mode": "mounted", "mount_id": "golden_plains_horse", "gait": "cruise"}, models)
		expect(actor._mount_visual.pony.rig_name() == "golden_plains_horse", "changing mount replaces its visual and fit")
		actor.set_mount_state({}, models)
		actor.free()
	expect(max_cape_link_error < .02, "horse cape retains material length: " + str(max_cape_link_error))
	print("HORSE_MOUNT_CHECKS ", checks, " failures=", failures, " max_contact_error=", max_contact_error,
		" max_cape_link_error=", max_cape_link_error)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
