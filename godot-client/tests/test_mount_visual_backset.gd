extends SceneTree
## A creature-only offset must move the complete riding assembly together.
var failures := 0
var checks := 0
var worst_error := 0.0
var worst_position_error := 0.0
var worst_rein_error := 0.0
var mount_id := "moor_pony"

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func make_rider(models: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var config: Dictionary = models.luminous_male
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var errors := actor.configure({"actor_id": 42, "kind": 1, "x": 0, "y": 0, "rotation": 0,
		"appearance": {"hair": 0}}, CoordinateAdapter.new({"walkingHeight": 0.0}), config, mapping)
	expect(errors.is_empty(), "rider imports: " + str(errors))
	actor.position = Vector3.ZERO
	actor.set_process(false)
	actor.set_physics_process(false)
	actor._presentation_speed = 3.75
	actor.set_mount_state({"mode": "mounted", "mount_id": mount_id, "gait": "walk"}, models)
	expect(is_instance_valid(actor._mount_visual), "production mounted visual imports")
	actor._mount_visual.set_process(false)
	return actor

func check_rig(actual: Skeleton3D, reference: Skeleton3D, shift: Vector3) -> void:
	for bone: int in actual.get_bone_count():
		var a := actual.global_transform * actual.get_bone_global_pose(bone)
		var b := reference.global_transform * reference.get_bone_global_pose(bone)
		var error := (a.origin - b.origin).distance_to(shift)
		worst_position_error = maxf(worst_position_error, error)
		error = maxf(error, a.basis.x.distance_to(b.basis.x))
		error = maxf(error, a.basis.y.distance_to(b.basis.y))
		error = maxf(error, a.basis.z.distance_to(b.basis.z))
		worst_error = maxf(worst_error, error)
		# Near-extended IK chains amplify float rounding after a world shift.
		# One millimetre / .06 degrees still detects detached seats or grips.
		expect(error < 0.001, "saddle/rider pose translates together: " + str(actual.get_bone_name(bone)))

func run() -> void:
	if "--horse" in OS.get_cmdline_user_args(): mount_id = "golden_plains_horse"
	if "--tortoise" in OS.get_cmdline_user_args(): mount_id = "crystalback_tortoise"
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var baseline := models.duplicate(true)
	baseline[mount_id].import.visualBacksetMetres = 0.0
	var rider := make_rider(models)
	var reference := make_rider(baseline)
	var player_rest: Transform3D = rider._mount_visual.pose.visual_rest
	for yaw: float in [0.0, PI * .5, PI, PI * 1.5]:
		rider.rotation.y = yaw
		reference.rotation.y = yaw
		var authoritative := rider.global_transform
		var mount_scale: float = rider._mount_visual.pony.get("_small_creature_scale") * rider._mount_visual.pony.server_scale
		var shift := rider.global_basis * Vector3(0, 0, float(models[mount_id].import.visualBacksetMetres) * mount_scale)
		for gait: String in ["idle", "walk", "trot", "gallop"]:
			for actor: ReplicatedActor3D in [rider, reference]:
				actor.mount_state.gait = {"idle": "walk", "walk": "walk", "trot": "cruise", "gallop": "burst"}[gait]
				actor.current_action = &"idle" if gait == "idle" else &"run"
				actor._mount_visual.upper.ground_action = actor.current_action
				actor._mount_visual.action = gait
			var visual: Variant = rider._mount_visual
			var other: Variant = reference._mount_visual
			var duration: float = visual.pony.animation_player.get_animation(visual.profile.clips[gait]).length
			for frame: int in 17:
				visual.elapsed = duration * float(frame) / 17.0
				other.elapsed = visual.elapsed
				visual._process(0.0)
				other._process(0.0)
				check_rig(visual.pony.get_skeleton(), other.pony.get_skeleton(), shift)
				check_rig(rider.get_skeleton(), reference.get_skeleton(), shift)
				expect(rider.global_transform.is_equal_approx(authoritative), "mounted setback preserves server transform")
				for side: String in ["l", "r"]:
					var a: PackedVector3Array = visual.reins.last_points[side]
					var b: PackedVector3Array = other.reins.last_points[side]
					for i: int in a.size():
						var delta: Vector3 = visual.reins.to_global(a[i]) - other.reins.to_global(b[i])
						worst_rein_error = maxf(worst_rein_error, delta.distance_to(shift))
						expect(delta.distance_to(shift) < 0.001, "rein bridle/grip/strap follows saddle setback")
					expect(absf(visual.reins.last_lengths[side] - other.reins.last_lengths[side]) < 0.001, "rein length/contact preserved")
		rider.set_mount_state({}, models)
		reference.set_mount_state({}, baseline)
		expect((rider.get_node("NativeModel") as Node3D).transform.is_equal_approx(player_rest), "dismount restores the player visual origin")
		if yaw != PI * 1.5:
			for pair: Array in [[rider, models], [reference, baseline]]:
				pair[0].set_mount_state({"mode": "mounted", "mount_id": mount_id, "gait": "walk"}, pair[1])
				pair[0]._mount_visual.set_process(false)
	rider.free()
	reference.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("MOUNT_BACKSET ", mount_id, " ", "PASS" if failures == 0 else "FAIL", " checks=", checks, " failures=", failures,
		" max_basis_error=", worst_error, " max_position_error_m=", worst_position_error, " max_rein_error_m=", worst_rein_error)
	quit(1 if failures else 0)
