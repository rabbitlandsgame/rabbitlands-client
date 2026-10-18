extends SceneTree
var failures := 0
var checks := 0
var report: Array[Dictionary] = []
var geometry: Array[Dictionary] = []
var motion: Array[Dictionary] = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func posed_mesh(mesh: MeshInstance3D, rig: Skeleton3D, arrays: Array) -> PackedVector3Array:
	var transforms: Array[Transform3D] = []
	for bind: int in mesh.skin.get_bind_count():
		var bone := mesh.skin.get_bind_bone(bind)
		var bind_name := mesh.skin.get_bind_name(bind)
		if not bind_name.is_empty():
			bone = rig.find_bone(bind_name)
		if bone < 0 or bone >= rig.get_bone_count():
			failures += 1
			push_error("Invalid mesh skin binding: %s %s %d" % [mesh.name, bind_name, bone])
			transforms.append(Transform3D.IDENTITY)
			continue
		transforms.append(rig.global_transform * rig.get_bone_global_pose(bone) * mesh.skin.get_bind_pose(bind))
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var count := bones.size() / vertices.size()
	var out := PackedVector3Array()
	for vertex: int in vertices.size():
		var point := Vector3.ZERO
		var total := 0.0
		for influence: int in count:
			var at := vertex * count + influence
			if weights[at] > 0.0:
				point += transforms[bones[at]] * vertices[vertex] * weights[at]
				total += weights[at]
		out.append(point / maxf(.001, total))
	return out

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models[body]
		var errors := actor.configure({"actor_id": 42, "x": 20, "y": 30, "rotation": 0,
			"kind": 1, "name": "", "appearance": {}, "equipment_visuals": {"2": 1, "5": 184}}, CoordinateAdapter.new(), config,
			JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)), equipment)
		expect(errors.is_empty(), "equipped character loads")
		actor.set_physics_process(false)
		actor.rotation.y = .7
		actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "walk", "step_us": 600000}, models)
		var visual: Node3D = actor._mount_visual
		var rig := actor.get_skeleton()
		var cloth := actor._cape_cloth
		expect(cloth != null and not cloth.active, "one manually ordered cloth pass when mounted")
		var cape_meshes: Array[MeshInstance3D] = []
		for node: Node in rig.get_children():
			if node is MeshInstance3D and node.name.begins_with("EquipmentSkin_2_"):
				cape_meshes.append(node)
		expect(not cape_meshes.is_empty(), "actual worn cape is present")
		var stages: Array[String] = ["idle", "walk", "cruise", "burst", "cruise"]
		for stage: int in stages.size():
			var gait := stages[stage]
			actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": gait, "step_us": 200000}, models)
			actor.current_action = &"idle" if gait == "idle" else &"run"
			actor._presentation_speed = {"idle": 0.0, "walk": 1.67, "cruise": 5.0, "burst": 7.5}[gait]
			var deepest := 0.0
			var max_stretch := 0.0
			var max_link_error := 0.0
			for frame: int in range(120):
				if gait != "idle":
					actor.global_position += actor.global_basis * Vector3(0.0, 0.0, -actor._presentation_speed / 60.0)
				visual.call("_process", 1.0 / 60.0)
				# Include the lift/settle transition, not only settled gaits.
				if not ((frame >= 60 and frame % 10 == 0) or (stage > 0 and frame in [12, 24])):
					continue
				var surface: RefCounted = visual.get("cape_surface")
				for chain: int in range(3):
					var points: PackedVector3Array = cloth.get("_points")[chain]
					var lengths: PackedFloat32Array = cloth.get("_lengths")[chain]
					for i: int in range(1, points.size()):
						max_link_error = maxf(max_link_error, absf(points[i].distance_to(points[i - 1]) - lengths[i - 1]))
				for mesh: MeshInstance3D in cape_meshes:
					for index: int in mesh.mesh.get_surface_count():
						var arrays := mesh.mesh.surface_get_arrays(index)
						var actual := posed_mesh(mesh, rig, arrays)
						if body == "luminous_male":
							var pony: ReplicatedActor3D = visual.get("pony")
							for node: Node in pony.get_skeleton().get_children():
								if not node is MeshInstance3D or (node as MeshInstance3D).skin == null:
									continue
								var pony_mesh := node as MeshInstance3D
								var pony_arrays := pony_mesh.mesh.surface_get_arrays(0)
								var horse := posed_mesh(pony_mesh, pony.get_skeleton(), pony_arrays)
								var native_vertices: PackedVector3Array = pony_arrays[Mesh.ARRAY_VERTEX]
								var horse_indices: PackedInt32Array = pony_arrays[Mesh.ARRAY_INDEX]
								var body_faces: Array[int] = []
								for triangle: int in range(0, horse_indices.size(), 3):
									var center := (native_vertices[horse_indices[triangle]] + native_vertices[horse_indices[triangle+1]] + native_vertices[horse_indices[triangle+2]]) / 3.0
									if center.y > .85 and center.z < .33 and center.z > -.97:
										body_faces.append_array([horse_indices[triangle], horse_indices[triangle+1], horse_indices[triangle+2]])
								geometry.append({"gait": gait, "stage": stage, "frame": frame,
									"cape": vectors(actual), "cape_rest": vectors(arrays[Mesh.ARRAY_VERTEX]),
									"cape_indices": Array(arrays[Mesh.ARRAY_INDEX]), "pony": vectors(horse), "body_indices": body_faces})
						for point: Vector3 in actual:
							var outside: Vector3 = surface.call("project", point)
							deepest = maxf(deepest, point.distance_to(outside))
						var rest: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
						var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
						for triangle: int in range(0, indices.size(), 3):
							for edge: int in range(3):
								var a := indices[triangle + edge]
								var b := indices[triangle + (edge + 1) % 3]
								var length := rest[a].distance_to(rest[b])
								if length > .005:
									max_stretch = maxf(max_stretch, actual[a].distance_to(actual[b]) / length)
			var row := {"body": body, "gait": gait, "stage": stage, "cloth_inside_envelope_m": deepest,
				"maximum_edge_ratio": max_stretch, "material_link_error_m": max_link_error}
			report.append(row)
			print("MOUNT_CAPE_SAMPLE ", JSON.stringify(row))
			# Contact envelopes are deliberately inflated to cover chord sag
			# between the four existing joints. Actual mesh clearance is checked
			# independently from the exported geometry samples.
			expect(max_stretch < 1.8, body + " " + gait + " no cloth spikes")
			expect(max_link_error < .02, body + " " + gait + " cloth links preserve length")
		check_motion(actor, visual, body)
		actor.set_mount_state({}, models)
		expect(cloth.get("_mount_surface") == null and cloth.active, "dismount restores ordinary cape cloth")
		actor.free()
	var file := FileAccess.open("res://../.local/qa/mounted-cape-checks.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"samples": report, "motion": motion, "checks": checks, "failures": failures}, "  "))
	var samples := FileAccess.open("res://../.local/qa/mounted-cape-geometry.json", FileAccess.WRITE)
	samples.store_string(JSON.stringify(geometry))
	print("MOUNT_CAPE_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)

func check_motion(actor: ReplicatedActor3D, visual: Node3D, body: String) -> void:
	# Freeze the pony/rider pose to distinguish fabric flow from pony bobbing.
	actor.current_action = &"idle"
	actor._presentation_speed = 0.0
	visual.call("_process", 0.0)
	var cloth := actor._cape_cloth
	var surface: RefCounted = visual.get("cape_surface")
	var rig := actor.get_skeleton()
	var heights: Dictionary = {}
	var trot_points := PackedVector3Array()
	var gallop_points := PackedVector3Array()
	var return_points := PackedVector3Array()
	var idle_points := PackedVector3Array()
	var largest_step := 0.0
	var collar_drift := 0.0
	var previous := Vector3.ZERO
	var collar := Vector3.ZERO
	for stage: String in ["trot", "gallop", "return_trot", "idle"]:
		var sum := 0.0
		for frame: int in range(300):
			surface.call("update", 1.0 / 60.0, "trot" if stage == "return_trot" else stage)
			cloth.call("_process_modification_with_delta", 1.0 / 60.0)
			rig.force_update_all_bone_transforms()
			var points: PackedVector3Array = cloth.get("_points")[1]
			if stage == "trot" and frame == 0:
				collar = points[0]
			collar_drift = maxf(collar_drift, points[0].distance_to(collar))
			var hem := points[points.size() - 1] - points[0]
			if previous != Vector3.ZERO and (stage != "trot" or frame > 180):
				largest_step = maxf(largest_step, hem.distance_to(previous))
			previous = hem
			if frame >= 180:
				sum += hem.y
				if stage == "trot":
					trot_points.append(hem)
				elif stage == "gallop":
					gallop_points.append(hem)
				elif stage == "return_trot":
					return_points.append(hem)
				else:
					idle_points.append(hem)
		heights[stage] = sum / 120.0
	var trot_span := span(trot_points)
	var flow_span := span(gallop_points)
	var return_span := span(return_points)
	var quiet_span := span(idle_points)
	var lift := float(heights.gallop) - float(heights.trot)
	var row := {"body": body, "frozen_pose_gallop_lift_m": lift,
		"steady_trot_hem_motion_m": trot_span, "steady_gallop_hem_motion_m": flow_span,
		"return_trot_hem_motion_m": return_span, "settled_idle_hem_motion_m": quiet_span,
		"largest_hem_frame_step_m": largest_step, "collar_drift_m": collar_drift}
	motion.append(row)
	print("MOUNT_CAPE_MOTION ", JSON.stringify(row))
	expect(lift > .1, body + " trot hangs closer down the back on the same frozen pony pose")
	# Twice v3's reviewed ~16.6 mm trot displacement on this frozen pose.
	expect(trot_span > .030 and trot_span < .037, body + " trot ripple is twice the previous reviewed displacement")
	expect(flow_span > trot_span * 1.8 and flow_span < trot_span * 2.4, body + " gallop ripple is about twice the trot displacement")
	expect(quiet_span < .005, body + " ripple settles when standing still")
	expect(largest_step < .055, body + " drape changes without a hem snap")
	expect(collar_drift < .0001, body + " collar remains attached while hem flows")
	expect(absf(float(heights.return_trot) - float(heights.trot)) < .015, body + " returns to the lower trot hang")
	expect(return_span > trot_span * .5 and return_span < trot_span * 1.5, body + " returns to the gentle trot ripple")

func span(points: PackedVector3Array) -> float:
	var largest := 0.0
	for a: Vector3 in points:
		for b: Vector3 in points:
			largest = maxf(largest, a.distance_to(b))
	return largest

func vectors(points: PackedVector3Array) -> Array:
	var out: Array = []
	for p: Vector3 in points:
		out.append([p.x, p.y, p.z])
	return out
