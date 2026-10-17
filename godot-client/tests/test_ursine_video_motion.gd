extends SceneTree

const CLIPS := ["Idle_A", "Fighting_Idle", "Hit_Chest", "Death_A", "Sword_Attack", "Walk", "Jog"]
var failures: Array[String] = []
func _init() -> void:
	_run.call_deferred()
func check(ok: bool, label: String) -> void:
	if not ok:
		failures.append(label)
		push_error(label)
func snapshot(sk: Skeleton3D) -> Array[Transform3D]:
	var poses: Array[Transform3D] = []
	for bone in sk.get_bone_count(): poses.append(sk.get_bone_pose(bone))
	return poses
func difference(sk: Skeleton3D, poses: Array[Transform3D]) -> float:
	var error := 0.0
	for bone in sk.get_bone_count():
		var actual := sk.get_bone_pose(bone)
		error = maxf(error, actual.origin.distance_to(poses[bone].origin))
		for axis in 3: error = maxf(error, actual.basis[axis].distance_to(poses[bone].basis[axis]))
	return error
func _run() -> void:
	var witness: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/ursine_motion_worlds.json"))
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = registry.models.moss_bear
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var resolver := AnimationResolver.new(mapping)
	check(config.scene == config.animationLibrary, "scene and library use the same approved model")
	for action: String in ["walk", "run"]:
		check(resolver.stride_speed_for_action(action) > 0.0, "measured stride " + action)
		check(is_equal_approx(resolver.stride_speed_for_action(action, 2.0), 2.0 * resolver.stride_speed_for_action(action)), "scaled stride " + action)
	check(resolver.clip_for_action(&"attack_primary") == &"Sword_Attack", "attack mapping")
	check(resolver.clip_for_action(&"death") == &"Death_A", "death mapping")
	check(resolver.action_for_command(46) == &"attack_primary", "server attack command")
	check(resolver.action_for_command(3) == &"death", "server death command")
	var path: String = config.scene
	check(FileAccess.get_sha256(path) == witness.sha256, "bound candidate hash")
	check(ResourceLoader.load(path, "PackedScene") != null, "fresh imported runtime scene available")
	var policy := ConfigFile.new()
	check(policy.load(path + ".import") == OK, "tracked import policy")
	check(is_equal_approx(float(policy.get_value("params", "animation/fps", 30.0)), 1536.0), "dense import cadence")
	var model := GlbSceneCache.instantiate(path)
	check(model != null, "actual in-project scene cache loading path")
	if model == null:
		quit(1)
		return
	root.add_child(model)
	var sk := model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var source := model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	source.stop()
	source.active = false
	source.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var reference_model := GlbSceneCache.instantiate(path)
	root.add_child(reference_model)
	var reference_sk := reference_model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	source = reference_model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	source.stop()
	source.deterministic = true
	source.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var skin_formats: Array = []
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var arrays: Array = mesh.mesh.surface_get_arrays(surface)
			var weights: Variant = arrays[Mesh.ARRAY_WEIGHTS]
			if weights == null or weights.size() == 0: continue
			var count: int = weights.size() / arrays[Mesh.ARRAY_VERTEX].size()
			skin_formats.append(count)
			check(count == 4, "original four-influence skin retained")
	var imported := NativeAnimationImporter.import_library(model, path, sk, {}, PackedStringArray(CLIPS), PackedStringArray(mapping.loopingClips))
	check(imported.errors.is_empty(), "actual native animation importer: " + str(imported.errors))
	var player: AnimationPlayer = imported.player
	check(player != null and player.has_animation("RESET"), "native RESET generated")
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.play("Idle_A", 0.0)
	player.advance(.2)
	var idle := snapshot(sk)
	var actions: Array = []
	for clip: String in CLIPS:
		check(player.has_animation(clip), "clip discovered " + clip)
		var animation := player.get_animation(clip)
		check((animation.loop_mode == Animation.LOOP_LINEAR) == mapping.loopingClips.has(clip), "loop mapping " + clip)
		var witness_error := 0.0
		var import_error := 0.0
		var finite := true
		for entry: Dictionary in witness.clips[clip]:
			player.stop()
			source.stop()
			reference_sk.reset_bone_poses()
			source.play(clip, 0.0)
			source.seek(float(entry.time), true)
			var expected := snapshot(reference_sk)
			source.stop()
			player.play(clip, 0.0)
			player.seek(float(entry.time), true)
			import_error = maxf(import_error, difference(sk, expected))
			for name: String in entry.bones:
				var bone := sk.find_bone(name)
				check(bone >= 0, "bone present " + name)
				if bone < 0: continue
				var actual := sk.global_transform * sk.get_bone_global_pose(bone)
				finite = finite and actual.origin.is_finite() and actual.basis.is_finite()
				var matrix: Array = entry.bones[name]
				for row in 3:
					witness_error = maxf(witness_error, absf(actual.origin[row] - float(matrix[row * 4 + 3])))
					for column in 3:
						witness_error = maxf(witness_error, absf(actual.basis[column][row] - float(matrix[row * 4 + column])))
		check(finite, "finite native playback " + clip)
		check(import_error < .0001, "native/imported agreement " + clip + " " + str(import_error))
		check(witness_error < .0001, "independent off-grid GLB witness " + clip + " " + str(witness_error))
		var terminal_hold_error := 0.0
		if clip in ["Sword_Attack", "Death_A"]:
			player.stop()
			player.play(clip, 0.0)
			player.seek(animation.length - .05, true)
			var held := snapshot(sk)
			player.advance(.2)
			terminal_hold_error = difference(sk, held)
			check(not player.is_playing() and terminal_hold_error < .0001, "one-shot end hold " + clip)
		player.play("Sword_Attack", 0.0)
		player.seek(.6, true)
		player.play(clip, 0.0)
		player.seek(animation.length * .393, true)
		var switched := snapshot(sk)
		player.play("RESET", 0.0)
		player.seek(0.0, true)
		player.play(clip, 0.0)
		player.seek(animation.length * .393, true)
		var switch_error := difference(sk, switched)
		check(switch_error < .0001, "posed attack switch restoration " + clip)
		player.play("Idle_A", 0.0)
		player.seek(.2, true)
		var idle_error := difference(sk, idle)
		check(idle_error < .0001, "idle restoration " + clip)
		actions.append({"clip":clip,"duration_seconds":animation.length,"finite":finite,
			"native_import_max_error":import_error,"independent_glb_world_max_error":witness_error,
			"attack_switch_error":switch_error,"idle_restore_error":idle_error})
		actions[-1]["terminal_hold_error"] = terminal_hold_error
	var report := {"passed":failures.is_empty(),"failures":failures,"candidate_sha256":witness.sha256,
		"engine":Engine.get_version_info(),"clips":actions,"skin_influences":skin_formats,
		"scope":"Current runtime asset and dedicated map; imported scene cache and native library, all seven clips. Focused component integration, not a full client/server session."}
	report["preservation_note"] = "All seven slots pass independent GLB world-pose witnesses. Exact inherited Walk/Jog and three old idle/hit clip payloads are checked separately in promotion.json."
	var report_path := "user://ursine-motion-playback.json"
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="): report_path = argument.trim_prefix("--report=")
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	model.free()
	reference_model.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("MOSS_BEAR_GODOT ", "PASS" if failures.is_empty() else "FAIL", " failures=", failures.size())
	quit(0 if failures.is_empty() else 1)
