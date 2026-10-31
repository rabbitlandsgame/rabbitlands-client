extends "res://tests/test_cape_idle.gd"
## Current native assets, real action mapping, fixed 60 Hz cloth steps.
## Covers the bare wardrobe and four torso depths on both Human bodies,
## plus bare and armoured motion for the other fourteen player rigs.
## Optional images: ELORIA_ARTIFACT_DIR plus --cape-review-images.

const OUTFITS := [0, 225, 184, 213, 197]
const SEQUENCE := [["walk", 2.0, 120], ["run", 5.0, 120],
	["attack_primary", 0.0, 90], ["attack_secondary", 0.0, 90]]
var _report: Array = []

func _run() -> void:
	_equipment_config = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})
	_stage = Node3D.new()
	root.add_child(_stage)
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/cape-motion-fit")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	if _images():
		_setup_camera()
	var rigs: Array[String] = ["luminous_male", "luminous_female"]
	for key: String in models:
		if (key.ends_with("_male") or key.ends_with("_female")) and not rigs.has(key):
			rigs.append(key)
	for rig: String in rigs:
		_model_config = models[rig]
		_animation_config = JSON.parse_string(FileAccess.get_file_as_string(str(_model_config.animationMap)))
		for body: int in OUTFITS:
			if not rig.begins_with("luminous_") and body not in [0, 184]:
				continue
			if "--cape-review-quick" in OS.get_cmdline_user_args() and (not rig.begins_with("luminous_") or body not in [0, 184]):
				continue
			await _outfit(rig, body)
	var output := FileAccess.open(_artifacts.path_join("motion-fit.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"failures": _failures, "cases": _report}, "\t"))
	print("cape motion fit: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures else 0)

func _outfit(rig: String, body: int) -> void:
	var gear := {"2": 5}
	if body > 0:
		gear.merge({"0":114, "1":106, "3":117, "4":171, "5":body, "6":192})
	var actor := _spawn(gear)
	actor.set_process(false)
	actor.set_physics_process(false)
	var skeleton := _skeleton_of(actor)
	var cloth := skeleton.get_node("CapeCloth") as SkeletonModifier3D
	cloth.active = false
	var label := "%s-%d" % [rig, body]
	var free_sheet := _free_sheet(skeleton)
	_check((cloth.get("_fabric_rest") as Array).size() == 3, label + " measures all three fabric chains")
	actor.play_action(&"idle")
	actor.animation_player.advance(0.4)
	actor.animation_player.pause()
	cloth.call("reset")
	_step_cloth(cloth, 180)
	_check_rig_hang(skeleton, rig, label + " idle")
	_check_shoulder_attachment(skeleton, label)
	if _images():
		await _capture(actor, label + "-idle-side.png", Vector3(2.8, 0, 0))
		await _capture(actor, label + "-idle-back.png", Vector3(1.8, 0.1, 2.0))
	for entry: Array in SEQUENCE:
		var action := StringName(entry[0])
		actor.play_action(action)
		var clip := actor.animation_player.current_animation
		_check(not clip.is_empty() and actor.animation_player.has_animation(clip), label + " plays " + str(action))
		actor.animation_player.pause()
		var worst_ahead := -INF
		var worst_leg := 0.0
		var photographed_leg := 0.0
		for frame: int in int(entry[2]):
			actor.global_position += skeleton.global_basis * Vector3(0.0, 0.0, float(entry[1]) * STEP)
			actor.animation_player.advance(STEP)
			_step_cloth(cloth, 1)
			if frame % 6 != 0:
				continue
			var cape := _posed(skeleton, 2)
			var transform := skeleton.global_transform
			var anchor := transform * skeleton.get_bone_global_pose(skeleton.find_bone("spine_03")).origin
			var forward: Vector3 = cloth.call("_torso_forward", skeleton, transform)
			var side := (transform.basis * skeleton.get_bone_global_pose(skeleton.find_bone("spine_03")).basis * (cloth.get("_anchor_rest_inverse") as Basis) * Vector3.RIGHT).normalized()
			var shins: PackedVector3Array = cloth.get("_shin_world")
			for index: int in free_sheet:
				var point := transform * cape[index]
				# The collar wraps at the neck. Measure the hanging sheet.
				if point.y < anchor.y - 0.10 and absf((point - anchor).dot(side)) < 0.20:
					worst_ahead = maxf(worst_ahead, (point - anchor).dot(forward))
				if point.y > anchor.y - 0.35:
					continue
				for shin: int in shins.size() / 2:
					var knee := shins[shin * 2]
					var axis := shins[shin * 2 + 1] - knee
					var along := clampf((point - knee).dot(axis) / axis.length_squared(), 0.0, 1.0)
					var away := point - (knee + axis * along)
					var radius: float = cloth.call("_shin_radius", shin, along, away)
					if radius - away.length() > worst_leg:
						worst_leg = radius - away.length()
			if _images() and worst_leg > photographed_leg + 0.005:
				photographed_leg = worst_leg
				await _capture(actor, label + "-" + str(action) + "-contact.png", Vector3(2.8, 0.0, 0.0))
			if _images() and frame == 60:
				await _capture(actor, label + "-" + str(action) + ".png", Vector3(2.5, 0.1, 1.5))
		_report.append({"rig":rig, "torso":body, "action":action, "clip":clip,
			"ahead_mm":worst_ahead * 1000.0, "leg_envelope_penetration_mm":worst_leg * 1000.0})
		_check(worst_ahead <= 0.04, "%s %s keeps the sheet behind the chest (%+.1f mm)" % [label, action, worst_ahead * 1000.0])
		_check(worst_leg <= 0.025, "%s %s clears the leg envelope (%.1f mm)" % [label, action, worst_leg * 1000.0])
	actor.play_action(&"idle")
	actor.animation_player.advance(0.4)
	actor.animation_player.pause()
	_step_cloth(cloth, 180)
	_check_rig_hang(skeleton, rig, label + " after run and attacks")
	actor.queue_free()
	await process_frame

func _images() -> bool:
	return DisplayServer.get_name() != "headless" and "--cape-review-images" in OS.get_cmdline_user_args()

func _setup_camera() -> void:
	root.size = Vector2i(640, 820)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("20262d")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("d9e3e8")
	environment.environment.ambient_light_energy = 0.8
	_stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-25, 30, 0)
	_stage.add_child(light)
	_camera = Camera3D.new()
	_camera.current = true
	_camera.cull_mask = 3
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 1.9
	_stage.add_child(_camera)

# The collar wraps around the shoulders. Select the genuinely free sheet by
# its skin ownership, rather than a world-height cutoff that misclassifies
# the rigid collar when a running or attacking torso leans.
func _free_sheet(skeleton: Skeleton3D) -> PackedInt32Array:
	var out := PackedInt32Array()
	var offset := 0
	for node: Node in skeleton.get_children():
		var mesh := node as MeshInstance3D
		if mesh == null or not mesh.name.begins_with("EquipmentSkin_2_"):
			continue
		for surface: int in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var per := bones.size() / vertices.size()
			for index: int in range(0, vertices.size(), 4):
				var share := 0.0
				for slot: int in per:
					var at := index * per + slot
					if str(mesh.skin.get_bind_name(bones[at])).begins_with("cape_"):
						share += weights[at]
				if share >= 0.99:
					out.append(offset + index)
			offset += vertices.size()
	return out


func _check_rig_hang(skeleton: Skeleton3D, rig: String, label: String) -> void:
	if rig.begins_with("luminous_"):
		_check_hang(skeleton, label)
		return
	if str(_model_config.get("culture", "")) == "ssarathi":
		# The tail holds this cape out behind the calves. A plumb-depth
		# limit would demand that it pass through the tail. Clearance is
		# checked by the body-derived leg envelopes; idle must settle.
		var before := _posed(skeleton, 2)
		_step_cloth(skeleton.get_node("CapeCloth"), 60)
		var after := _posed(skeleton, 2)
		var drift := 0.0
		for index: int in before.size():
			drift = maxf(drift, before[index].distance_to(after[index]))
		_check(drift < 0.008, "%s settles over the tail (%.1f mm drift)" % [label, drift * 1000.0])
		return
	# Other body proportions put the hem at different fractions of the spine
	# height. Measure within their actual fabric extent, rather than treating
	# an empty Human-height band as fabric at depth zero.
	var cape := _posed(skeleton, 2)
	var anchor := skeleton.get_bone_global_pose(skeleton.find_bone("spine_03")).origin
	var low := INF
	var high := -INF
	for point: Vector3 in cape:
		if absf(point.x - anchor.x) < 0.10:
			low = minf(low, point.y)
			high = maxf(high, point.y)
	var depths := PackedFloat32Array()
	for fraction: float in [0.25, 0.55]:
		var total := 0.0
		var count := 0
		for point: Vector3 in cape:
			if absf(point.x - anchor.x) < 0.10 and absf(point.y - lerpf(low, high, fraction)) < 0.06:
				total += point.z
				count += 1
		_check(count > 0, label + " has fabric in its own height band")
		depths.append(total / maxf(count, 1))
	_check(absf(depths[1] - depths[0]) < MAX_IDLE_SLOPE,
		"%s hangs down (%.1f mm depth change)" % [label, absf(depths[1] - depths[0]) * 1000.0])


func _check_shoulder_attachment(skeleton: Skeleton3D, label: String) -> void:
	var source: Mesh = ReplicatedActor3D._equipment_pieces(
		"res://assets/actors/native/equipment/generic_cape.glb")[0].mesh
	var posed := _posed(skeleton, 2)
	var totals: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO]
	var counts := PackedInt32Array([0, 0])
	var offset := 0
	for surface: int in source.get_surface_count():
		var rest: PackedVector3Array = source.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
		for index: int in rest.size():
			var point := rest[index]
			# Existing front ends of the collar, identified in the unchanged
			# source topology, then measured on the actual rebound skin.
			if absf(point.x) < 0.09 or absf(point.x) > 0.16 or point.y < 1.48 or point.y > 1.58 or point.z < -0.065:
				continue
			var side := 0 if point.x > 0.0 else 1
			totals[side] += posed[offset + index]
			counts[side] += 1
		offset += rest.size()
	for side: int in 2:
		_check(counts[side] > 0, label + " has clasp geometry on shoulder " + str(side))
		var clasp := totals[side] / maxi(counts[side], 1)
		var bone := skeleton.find_bone("upperarm_l" if side == 0 else "upperarm_r")
		var shoulder := skeleton.get_bone_global_pose(bone).origin
		var height := clasp.y - shoulder.y
		var forward := clasp.z - shoulder.z
		_check(height >= 0.05 and height <= 0.14,
			"%s clasp %d rests above the shoulder (%.1f mm)" % [label, side, height * 1000.0])
		_check(forward >= 0.04 and forward <= 0.20,
			"%s clasp %d wraps forward over the shoulder (%.1f mm)" % [label, side, forward * 1000.0])
