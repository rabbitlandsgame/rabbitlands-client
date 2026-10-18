extends SceneTree
const Correction := preload("res://src/mounts/mount_hind_leg_pose.gd")
var failures := 0
var checks := 0
var max_contact_error := 0.0
var max_length_error := 0.0
var baseline_length_error := 0.0
var max_thigh_angle := 0.0
var baseline_thigh_angle := 0.0
var max_hock_step := 0.0
var max_rotation_step := 0.0

func _init() -> void: call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		if failures < 12: push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var horse := ReplicatedActor3D.new()
	root.add_child(horse)
	var config: Dictionary = models.golden_plains_horse
	expect(horse.configure({"actor_id": 1, "x": 0, "y": 0, "rotation": 0, "kind": 5, "name": ""}, CoordinateAdapter.new(), config,
		JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))).is_empty(), "actual horse rig loads")
	horse.set_physics_process(false)
	horse.set_process(false)
	var sk := horse.get_skeleton()
	var profile: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/mounts/golden_plains_horse.json"))
	var correction := Correction.new()
	expect(correction.configure(sk, profile.hindLegPose).is_empty(), "horse's physical serial hind chains resolve")
	var modified: Array[int] = []
	for chain: Dictionary in correction.chains:
		for bone: int in chain.bones: modified.append(bone)
	for clip: String in ["Walk", "Jog", "Gallop"]:
		var duration := horse.animation_player.get_animation(clip).length
		var samples := ceili(duration * 480.0)
		var first: Array[Transform3D] = []
		var previous: Array[Transform3D] = []
		for sample: int in range(samples + 1):
			horse.animation_player.play(clip, 0.0)
			horse.animation_player.seek(duration * sample / samples, true)
			horse.animation_player.pause()
			sk.force_update_all_bone_transforms()
			var before := snapshot(sk)
			var frame := sk.get_bone_global_pose(correction.body) * correction.body_rest_inverse
			var inverse := frame.affine_inverse()
			for chain: Dictionary in correction.chains:
				var femur := inverse.basis * (before[chain.bones[1]].origin - before[chain.bones[0]].origin)
				baseline_thigh_angle = maxf(baseline_thigh_angle, rad_to_deg(atan2(femur.z, -femur.y)))
			correction.apply({"Walk":"walk", "Jog":"trot", "Gallop":"gallop"}[clip])
			var after := snapshot(sk)
			for bone: int in sk.get_bone_count():
				if bone not in modified:
					expect(after[bone].is_equal_approx(before[bone]), "body/front legs/tail retain the authored pose")
			for chain: Dictionary in correction.chains:
				var bones: PackedInt32Array = chain.bones
				var foot := sk.get_bone_children(bones[3])[0]
				for bone: int in [bones[3], foot]:
					max_contact_error = maxf(max_contact_error, after[bone].origin.distance_to(before[bone].origin))
					expect(after[bone].origin.distance_to(before[bone].origin) < .00002, "authored fetlock/hoof path retained")
					expect(after[bone].basis.is_equal_approx(before[bone].basis), "authored hoof pitch and sole contact retained")
				var femur := inverse.basis * (after[bones[1]].origin - after[bones[0]].origin)
				var angle := rad_to_deg(atan2(femur.z, -femur.y))
				max_thigh_angle = maxf(max_thigh_angle, angle)
				expect(angle <= 55.001 and femur.y < 0.0, "stifle stays below the hip through every gait")
				expect(absf(femur.x - float(chain.side)) < .00001, "thigh does not kick outward from the rump")
				for i: int in 3:
					var error := absf(after[bones[i]].origin.distance_to(after[bones[i + 1]].origin) - float(chain.lengths[i]))
					baseline_length_error = maxf(baseline_length_error, absf(before[bones[i]].origin.distance_to(before[bones[i + 1]].origin) - float(chain.lengths[i])))
					max_length_error = maxf(max_length_error, error)
					expect(error < .000005, "hind-leg segments retain their native lengths within float/import precision")
				if not previous.is_empty():
					max_hock_step = maxf(max_hock_step, after[bones[2]].origin.distance_to(previous[bones[2]].origin))
					for bone: int in bones:
						max_rotation_step = maxf(max_rotation_step, after[bone].basis.get_rotation_quaternion().angle_to(previous[bone].basis.get_rotation_quaternion()))
			if sample == 0: first = after
			if sample == samples:
				for bone: int in modified: expect(after[bone].is_equal_approx(first[bone]), "corrected gait closes without a pose seam")
			previous = after
	# Loading an empty profile must leave the Moor Pony and ordinary actors alone.
	var pony := Correction.new()
	expect(pony.configure(sk, {}).is_empty() and pony.chains.is_empty(), "adapter is opt-in per mount profile")
	expect(baseline_thigh_angle > 100.0, "probe includes the formerly folded thigh poses")
	expect(max_hock_step < .08 and max_rotation_step < .30, "dense playback contains no joint/pole flips")
	var report := {"checks":checks, "failures":failures, "max_hoof_position_error_metres":max_contact_error,
		"max_segment_length_error_metres":max_length_error, "max_thigh_degrees":max_thigh_angle,
		"baseline_segment_length_error_metres":baseline_length_error,
		"baseline_max_thigh_degrees":baseline_thigh_angle, "max_hock_step_at_480hz":max_hock_step,
		"max_rotation_step_radians_at_480hz":max_rotation_step}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="): FileAccess.open(argument.trim_prefix("--report="), FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print("MOUNT_HIND_LEG_CHECKS ", JSON.stringify(report))
	horse.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)

func snapshot(sk: Skeleton3D) -> Array[Transform3D]:
	var result: Array[Transform3D] = []
	for bone: int in sk.get_bone_count(): result.append(sk.get_bone_global_pose(bone))
	return result
