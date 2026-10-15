extends "res://tests/integration/rendered_cape_over_armour.gd"
## Compares the optimized cloth solver with a frozen copy of its reviewed
## predecessor. The comparison uses a real equipped rig and real animation
## clips, then repeats the edge deltas on a minimal rig without optional body
## capsules.

const BASELINE := "res://tests/fixtures/cape_cloth_baseline.gd"
const BASELINE_BODY_SHA256 := "b253940492529c94ee1d116607dc054994479f33538748f788d3b4005e1ba84c"
const STEP := 1.0 / 60.0
const EPSILON := 0.000001
const CAPE_CHAINS := ["l", "c", "r"]
const BODY_INPUTS := ["spine_03", "spine_01", "neck_01", "pelvis",
	"thigh_l", "calf_l", "thigh_r", "calf_r"]


func _run() -> void:
	_check_baseline_provenance()
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_main.hide()
	_equipment_config = _main.get("equipment_config") as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})
	_stage = Node3D.new()
	root.add_child(_stage)
	var models: Dictionary = _main.get("models")
	_model_config = models["luminous_male"]
	_animation_config = _main.call("_animation_for_model", _model_config)

	var optimized_actor := super._spawn({str(2): CAPE_VISUAL, str(5): 184})
	var baseline_actor := super._spawn({str(2): CAPE_VISUAL, str(5): 184})
	for actor: ReplicatedActor3D in [optimized_actor, baseline_actor]:
		actor.set_process(false)
		actor.set_physics_process(false)
	var optimized_skeleton := super._skeleton_of(optimized_actor)
	var baseline_skeleton := super._skeleton_of(baseline_actor)
	var optimized_cloth: SkeletonModifier3D = optimized_skeleton.get_node("CapeCloth")
	var baseline_cloth := _replace_with_baseline(baseline_actor, baseline_skeleton)
	optimized_cloth.active = false
	baseline_cloth.active = false

	_check_rig_ownership(optimized_skeleton)
	var optimized_player := optimized_actor.animation_player
	var baseline_player := baseline_actor.animation_player
	for clip: StringName in [&"Walk", &"Sword_Attack"]:
		_check(optimized_player != null and optimized_player.has_animation(clip),
			"optimized rig has animation %s" % clip)
		_check(baseline_player != null and baseline_player.has_animation(clip),
			"baseline rig has animation %s" % clip)
	if _failures == 0:
		_run_real_sequence(optimized_actor, baseline_actor,
			optimized_skeleton, baseline_skeleton,
			optimized_cloth, baseline_cloth,
			optimized_player, baseline_player)
	_run_missing_optional_sequence()
	if OS.get_environment("ELORIA_CAPE_PERF") == "1" and _failures == 0:
		_measure_pair(optimized_cloth, baseline_cloth)

	print("cape pose-cache parity: ", "PASS" if _failures == 0
		else "FAIL (%d)" % _failures)
	_main.queue_free()
	await process_frame
	quit(1 if _failures else 0)


func _check_baseline_provenance() -> void:
	var source := FileAccess.get_file_as_string(_baseline_path())
	var body_at := source.find("extends SkeletonModifier3D")
	_check(body_at >= 0, "frozen baseline contains the original script body")
	if body_at < 0:
		return
	var normalized := source.substr(body_at).replace("\r\n", "\n")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(normalized.to_utf8_buffer())
	var digest := context.finish().hex_encode()
	_check(digest == _baseline_body_sha256(),
		"frozen baseline source matches reviewed SHA-256")


func _baseline_path() -> String:
	return BASELINE


func _baseline_body_sha256() -> String:
	return BASELINE_BODY_SHA256


func _comparison_label() -> String:
	return "frozen original solver vs cached pose solver"


func _replace_with_baseline(actor: ReplicatedActor3D,
		skeleton: Skeleton3D) -> SkeletonModifier3D:
	var original: SkeletonModifier3D = skeleton.get_node("CapeCloth")
	var torso: PackedFloat32Array = original.get("_torso_reach")
	var lumbar: PackedFloat32Array = original.get("_lumbar_reach")
	original.active = false
	skeleton.remove_child(original)
	original.free()
	var replacement: SkeletonModifier3D = (load(_baseline_path()) as Script).new()
	replacement.name = "CapeCloth"
	skeleton.add_child(replacement)
	replacement.call("set_torso_reach", torso, lumbar)
	replacement.active = false
	actor.set("_cape_cloth", replacement)
	return replacement


func _check_rig_ownership(skeleton: Skeleton3D) -> void:
	var anchor := skeleton.find_bone("spine_03")
	var cape := PackedInt32Array()
	for chain: String in CAPE_CHAINS:
		var parent := anchor
		for link: int in range(1, 5):
			var bone := skeleton.find_bone("cape_%s_%02d" % [chain, link])
			cape.append(bone)
			_check(bone >= 0, "%s cape bone %d exists" % [chain, link])
			if bone >= 0:
				_check(skeleton.get_bone_parent(bone) == parent,
					"%s cape bone %d descends from the anchor chain" % [chain, link])
				parent = bone
	for name: String in BODY_INPUTS:
		var input := skeleton.find_bone(name)
		_check(input >= 0, "body input %s exists" % name)
		_check(not cape.has(input), "body input %s is not a cape output" % name)


func _run_real_sequence(optimized_actor: ReplicatedActor3D,
		baseline_actor: ReplicatedActor3D,
		optimized_skeleton: Skeleton3D, baseline_skeleton: Skeleton3D,
		optimized_cloth: SkeletonModifier3D, baseline_cloth: SkeletonModifier3D,
		optimized_player: AnimationPlayer, baseline_player: AnimationPlayer) -> void:
	optimized_cloth.call("reset")
	baseline_cloth.call("reset")
	_step_pair(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, -0.25, "negative delta")
	_step_pair(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, 0.0, "zero delta")
	_step_pair(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, 0.25, "clamped hitch delta")

	optimized_player.play(&"Walk")
	baseline_player.play(&"Walk")
	var walk_start := _input_poses(optimized_skeleton)
	for frame: int in range(72):
		optimized_actor.position = Vector3(sin(frame * 0.09) * 0.12, 0.0,
			-frame * 0.018)
		baseline_actor.position = optimized_actor.position
		optimized_actor.rotation.y = sin(frame * 0.06) * 0.35
		baseline_actor.rotation.y = optimized_actor.rotation.y
		optimized_player.advance(STEP)
		baseline_player.advance(STEP)
		if frame == 24:
			var empty := PackedFloat32Array()
			optimized_cloth.call("set_torso_reach", empty, empty)
			baseline_cloth.call("set_torso_reach", empty, empty)
		elif frame == 45:
			var trunk := PackedFloat32Array([0.19, 0.21, 0.25, 0.29, 0.28,
				0.26, 0.23, 0.21, 0.20])
			var lumbar := PackedFloat32Array([0.20, 0.22, 0.25, 0.27, 0.26,
				0.24, 0.22, 0.20, 0.19])
			optimized_cloth.call("set_torso_reach", trunk, lumbar)
			baseline_cloth.call("set_torso_reach", trunk, lumbar)
		_step_pair(optimized_skeleton, baseline_skeleton,
			optimized_cloth, baseline_cloth, STEP, "walk frame %d" % frame)
	_check(_pose_arrays_differ(walk_start, _input_poses(optimized_skeleton)),
		"Walk advances the real rig body pose")

	optimized_player.play(&"Sword_Attack")
	baseline_player.play(&"Sword_Attack")
	var attack_start := _input_poses(optimized_skeleton)
	for frame: int in range(42):
		optimized_player.advance(STEP)
		baseline_player.advance(STEP)
		_step_pair(optimized_skeleton, baseline_skeleton,
			optimized_cloth, baseline_cloth, STEP, "attack frame %d" % frame)
	_check(_pose_arrays_differ(attack_start, _input_poses(optimized_skeleton)),
		"Sword_Attack advances the real rig body pose")

	optimized_actor.position += Vector3(2.1, 0.4, -1.8)
	baseline_actor.position = optimized_actor.position
	_step_pair(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, STEP, "teleport")
	optimized_cloth.call("reset")
	baseline_cloth.call("reset")
	_step_pair(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, STEP, "explicit reset")


func _step_pair(optimized_skeleton: Skeleton3D, baseline_skeleton: Skeleton3D,
		optimized_cloth: SkeletonModifier3D, baseline_cloth: SkeletonModifier3D,
		delta: float, label: String) -> void:
	var optimized_before := _input_poses(optimized_skeleton)
	var baseline_before := _input_poses(baseline_skeleton)
	_compare_pose_arrays(optimized_before, baseline_before,
		label + " paired body inputs")
	optimized_cloth.call("_process_modification_with_delta", delta)
	baseline_cloth.call("_process_modification_with_delta", delta)
	_compare_pose_arrays(optimized_before, _input_poses(optimized_skeleton),
		label + " optimized inputs")
	_compare_pose_arrays(baseline_before, _input_poses(baseline_skeleton),
		label + " baseline inputs")
	_compare_cloth(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, label)


func _input_poses(skeleton: Skeleton3D) -> Array[Transform3D]:
	var poses: Array[Transform3D] = []
	for name: String in BODY_INPUTS:
		var bone := skeleton.find_bone(name)
		if bone >= 0:
			poses.append(skeleton.get_bone_global_pose(bone))
	return poses


func _compare_pose_arrays(before: Array[Transform3D], after: Array[Transform3D],
		label: String) -> void:
	_check(before.size() == after.size(), label + " keep their count")
	for index: int in range(mini(before.size(), after.size())):
		_check(_transform_close(before[index], after[index]),
			"%s pose %d is unchanged" % [label, index])


func _pose_arrays_differ(before: Array[Transform3D], after: Array[Transform3D]) -> bool:
	if before.size() != after.size():
		return true
	for index: int in range(before.size()):
		if not _transform_close(before[index], after[index]):
			return true
	return false


func _compare_cloth(optimized_skeleton: Skeleton3D,
		baseline_skeleton: Skeleton3D, optimized_cloth: SkeletonModifier3D,
		baseline_cloth: SkeletonModifier3D, label: String) -> void:
	_compare_nested_points(optimized_cloth.get("_points"),
		baseline_cloth.get("_points"), label + " points")
	_compare_nested_points(optimized_cloth.get("_previous"),
		baseline_cloth.get("_previous"), label + " previous")
	_check(bool(optimized_cloth.get("_settled")) == bool(baseline_cloth.get("_settled")),
		label + " settled state matches")
	_check((optimized_cloth.get("_last_anchor") as Vector3).distance_to(
		baseline_cloth.get("_last_anchor") as Vector3) <= EPSILON,
		label + " anchor state matches")
	for chain: String in CAPE_CHAINS:
		for link: int in range(1, 5):
			var name := "cape_%s_%02d" % [chain, link]
			var optimized := optimized_skeleton.get_bone_global_pose(
				optimized_skeleton.find_bone(name))
			var baseline := baseline_skeleton.get_bone_global_pose(
				baseline_skeleton.find_bone(name))
			_check(_transform_close(optimized, baseline),
				"%s %s pose matches" % [label, name])


func _compare_nested_points(optimized: Array, baseline: Array, label: String) -> void:
	_check(optimized.size() == baseline.size(), label + " chain count matches")
	for chain: int in range(mini(optimized.size(), baseline.size())):
		var left: PackedVector3Array = optimized[chain]
		var right: PackedVector3Array = baseline[chain]
		_check(left.size() == right.size(), "%s chain %d count matches" % [label, chain])
		for point: int in range(mini(left.size(), right.size())):
			_check(left[point].distance_to(right[point]) <= EPSILON,
				"%s chain %d point %d matches" % [label, chain, point])


func _transform_close(left: Transform3D, right: Transform3D) -> bool:
	return left.origin.distance_to(right.origin) <= EPSILON and \
		left.basis.x.distance_to(right.basis.x) <= EPSILON and \
		left.basis.y.distance_to(right.basis.y) <= EPSILON and \
		left.basis.z.distance_to(right.basis.z) <= EPSILON


func _run_missing_optional_sequence() -> void:
	var optimized_skeleton := _minimal_skeleton()
	var baseline_skeleton := _minimal_skeleton()
	root.add_child(optimized_skeleton)
	root.add_child(baseline_skeleton)
	var optimized: SkeletonModifier3D = (load(
		"res://src/actors/cape_cloth.gd") as Script).new()
	var baseline: SkeletonModifier3D = (load(_baseline_path()) as Script).new()
	optimized_skeleton.add_child(optimized)
	baseline_skeleton.add_child(baseline)
	optimized.active = false
	baseline.active = false
	for delta: float in [-0.25, 0.0, 0.25, STEP, STEP]:
		_step_pair(optimized_skeleton, baseline_skeleton,
			optimized, baseline, delta, "minimal rig delta %.6f" % delta)
	optimized_skeleton.queue_free()
	baseline_skeleton.queue_free()


func _minimal_skeleton() -> Skeleton3D:
	var skeleton := Skeleton3D.new()
	skeleton.add_bone("spine_03")
	skeleton.set_bone_rest(0, Transform3D(Basis.IDENTITY, Vector3(0, 1.2, 0)))
	for chain_index: int in range(CAPE_CHAINS.size()):
		var parent := 0
		for link: int in range(1, 5):
			var bone := skeleton.get_bone_count()
			skeleton.add_bone("cape_%s_%02d" % [CAPE_CHAINS[chain_index], link])
			skeleton.set_bone_parent(bone, parent)
			var x := (chain_index - 1) * 0.16 if link == 1 else 0.0
			skeleton.set_bone_rest(bone,
				Transform3D(Basis.IDENTITY, Vector3(x, -0.22, -0.08 if link == 1 else 0.0)))
			parent = bone
	return skeleton


func _measure_pair(optimized: SkeletonModifier3D,
		baseline: SkeletonModifier3D) -> void:
	const ITERATIONS := 1500
	var optimized_trials := PackedFloat64Array()
	var baseline_trials := PackedFloat64Array()
	var ordered_trials: Array[Dictionary] = []
	for trial: int in range(7):
		optimized.call("reset")
		baseline.call("reset")
		for _warm: int in range(20):
			optimized.call("_process_modification_with_delta", STEP)
			baseline.call("_process_modification_with_delta", STEP)
		var optimized_usec := 0.0
		var baseline_usec := 0.0
		var order := "baseline_first" if trial % 2 == 0 else "optimized_first"
		if trial % 2 == 0:
			baseline_usec = _time_solver(baseline, ITERATIONS)
			optimized_usec = _time_solver(optimized, ITERATIONS)
		else:
			optimized_usec = _time_solver(optimized, ITERATIONS)
			baseline_usec = _time_solver(baseline, ITERATIONS)
		optimized_trials.append(optimized_usec)
		baseline_trials.append(baseline_usec)
		ordered_trials.append({"trial": trial, "order": order,
			"baselineMicrosecondsPerCall": baseline_usec,
			"optimizedMicrosecondsPerCall": optimized_usec})
	var optimized_sorted := optimized_trials.duplicate()
	var baseline_sorted := baseline_trials.duplicate()
	optimized_sorted.sort()
	baseline_sorted.sort()
	var optimized_median := optimized_sorted[optimized_sorted.size() / 2]
	var baseline_median := baseline_sorted[baseline_sorted.size() / 2]
	print("  cape solver focused cost: baseline %.2f us, optimized %.2f us, ratio %.3f" % [
		baseline_median, optimized_median, optimized_median / baseline_median])
	print("  ordered paired trials: ", JSON.stringify(ordered_trials))
	var evidence := {
		"schemaVersion": 1,
		"comparison": _comparison_label(),
		"iterationsPerMeasurement": ITERATIONS,
		"warmupCallsPerSolver": 20,
		"orderedTrials": ordered_trials,
		"median": {
			"baselineMicrosecondsPerCall": baseline_median,
			"optimizedMicrosecondsPerCall": optimized_median,
			"optimizedToBaselineRatio": optimized_median / baseline_median,
		},
	}
	var artifacts := OS.get_environment("ELORIA_ARTIFACT_DIR")
	_check(not artifacts.is_empty(),
		"focused performance run declares ELORIA_ARTIFACT_DIR")
	if not artifacts.is_empty():
		DirAccess.make_dir_recursive_absolute(artifacts)
		var output := FileAccess.open(artifacts.path_join("cape-solver-paired.json"),
			FileAccess.WRITE)
		_check(output != null, "focused performance artifact opens")
		if output != null:
			output.store_string(JSON.stringify(evidence, "  "))
			output.close()


func _time_solver(cloth: SkeletonModifier3D, iterations: int) -> float:
	var started := Time.get_ticks_usec()
	for _step: int in range(iterations):
		cloth.call("_process_modification_with_delta", STEP)
	return float(Time.get_ticks_usec() - started) / iterations


func _check(ok: bool, label: String) -> void:
	if not ok:
		_failures += 1
		push_error("cape pose cache: " + label)
