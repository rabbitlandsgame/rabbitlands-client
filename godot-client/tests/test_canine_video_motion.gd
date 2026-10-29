extends SceneTree
## Focused integration check: real scene cache, native library retargeter and maps.
## Run after importing the project. Optional -- --report=user://report.json.
const ACTORS := ["briarhide_wolf", "thornhide_wolf", "thornbark_wolf", "crystal_dire_wolf",
	"moss_armored_hound", "mossbound_hound", "red_fox"]
const CLIPS := ["Idle_A", "Fighting_Idle", "Hit_Chest", "Jog", "Walk", "Sword_Attack", "Death_A"]
var failures: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)

func snapshot(sk: Skeleton3D) -> Array[Transform3D]:
	var poses: Array[Transform3D] = []
	for bone in sk.get_bone_count():
		poses.append(sk.get_bone_pose(bone))
	return poses

func difference(sk: Skeleton3D, poses: Array[Transform3D]) -> float:
	var error := 0.0
	for bone in sk.get_bone_count():
		var actual := sk.get_bone_pose(bone)
		error = maxf(error, actual.origin.distance_to(poses[bone].origin))
		for axis in 3:
			error = maxf(error, actual.basis[axis].distance_to(poses[bone].basis[axis]))
	return error

func _run() -> void:
	var state := GLTFState.new()
	state.json = {}
	check(is_equal_approx(NativeAnimationImporter.GltfAnimationFidelity.bake_fps(state), 30.0), "legacy bake cadence")
	state.json = {"asset": {"extras": {"rabbitlands_animation_bake_fps": 1536}}}
	check(is_equal_approx(NativeAnimationImporter.GltfAnimationFidelity.bake_fps(state), 1536.0), "declared bake cadence")
	state.json = {"asset": {"extras": [1, 2]}}
	check(is_equal_approx(NativeAnimationImporter.GltfAnimationFidelity.bake_fps(state), 30.0), "unrelated extras unchanged")
	state.json = {"asset": {"extras": {"rabbitlands_animation_bake_fps": "invalid"}}}
	check(is_equal_approx(NativeAnimationImporter.GltfAnimationFidelity.bake_fps(state), 30.0), "invalid cadence fallback")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var witnesses: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/canine_motion_worlds.json"))
	var records: Array = []
	for actor: String in ACTORS:
		var config: Dictionary = registry.models[actor]
		check(FileAccess.get_sha256(config.scene) == witnesses[actor].sha256, actor + " bound witness hash")
		var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
		var resolver := AnimationResolver.new(mapping)
		check(resolver.stride_speed_for_action(&"walk") > 0.0, actor + " measured walk stride")
		check(is_equal_approx(resolver.stride_speed_for_action(&"walk", 2.0),
			2.0 * resolver.stride_speed_for_action(&"walk")), actor + " enlarged actor stride")
		var legacy := AnimationResolver.new({"strideMetresPerSecond": {"walk": 2.0}})
		check(is_equal_approx(legacy.stride_speed_for_action(&"walk", 2.0), 2.0), "legacy stride unchanged")
		check(resolver.clip_for_action(&"attack_primary") == &"Sword_Attack", actor + " bite mapping")
		var model := GlbSceneCache.instantiate(config.scene)
		check(model != null, actor + " scene cache")
		if model == null: continue
		root.add_child(model)
		var skeletons := model.find_children("*", "Skeleton3D", true, false)
		check(not skeletons.is_empty(), actor + " skeleton")
		if skeletons.is_empty():
			model.free()
			continue
		var sk := skeletons[0] as Skeleton3D
		var source := model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
		source.stop()
		source.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var skin_formats: Array = []
		for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
			for surface in mesh.mesh.get_surface_count():
				var arrays: Array = mesh.mesh.surface_get_arrays(surface)
				var weights: Variant = arrays[Mesh.ARRAY_WEIGHTS]
				if weights == null or weights.size() == 0: continue
				var count: int = weights.size() / arrays[Mesh.ARRAY_VERTEX].size()
				skin_formats.append(count)
				check(count == 8, actor + " actual eight-influence scene")
		check(not skin_formats.is_empty(), actor + " skinned mesh")
		var imported := NativeAnimationImporter.import_library(model, config.animationLibrary,
			sk, {}, PackedStringArray(CLIPS), PackedStringArray(mapping.loopingClips))
		check(imported.errors.is_empty(), actor + " library: " + str(imported.errors))
		var player: AnimationPlayer = imported.player
		if player == null:
			model.free()
			continue
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		check(player.has_animation("RESET"), actor + " RESET")
		player.play("Idle_A", 0.0)
		player.advance(.2)
		var baseline := snapshot(sk)
		var actions: Array = []
		for clip: String in CLIPS:
			check(player.has_animation(clip), actor + " " + clip)
			if not player.has_animation(clip): continue
			var animation := player.get_animation(clip)
			var looping: bool = mapping.loopingClips.has(clip)
			check((animation.loop_mode == Animation.LOOP_LINEAR) == looping, actor + " loop " + clip)
			var import_error := 0.0
			var witness_error := 0.0
			var checked_witnesses := 0
			var worst_witness := ""
			var finite := true
			for frame in 97:
				# Offset interior samples from the bake grid to expose resampling loss.
				var fraction := (frame + .37) / 96.0 if frame > 0 and frame < 96 else frame / 96.0
				var stamp := animation.length * fraction
				player.stop()
				# Independent queries start from authored neutral poses. Otherwise
				# unkeyed reference bones retain the previous clip's last pose.
				sk.reset_bone_poses()
				source.play(clip, 0.0)
				source.seek(stamp, true)
				var expected := snapshot(sk)
				source.stop()
				sk.reset_bone_poses()
				player.play(clip, 0.0)
				player.seek(stamp, true)
				import_error = maxf(import_error, difference(sk, expected))
				var guide: Dictionary = witnesses[actor].clips.get(clip, {}).get(str(frame), {})
				for bone_name: String in guide:
					var bone := sk.find_bone(bone_name)
					if bone < 0: continue
					var actual := sk.global_transform * sk.get_bone_global_pose(bone)
					var matrix: Array = guide[bone_name]
					for row in 3:
						var position_error := absf(actual.origin[row] - float(matrix[row * 4 + 3]))
						if position_error > witness_error: worst_witness = "%s frame%d position%d" % [bone_name, frame, row]
						witness_error = maxf(witness_error, position_error)
						for column in 3:
							var basis_error := absf(actual.basis[column][row] - float(matrix[row * 4 + column]))
							if basis_error > witness_error: worst_witness = "%s frame%d basis%d,%d" % [bone_name, frame, row, column]
							witness_error = maxf(witness_error, basis_error)
					checked_witnesses += 1
				for pose: Transform3D in snapshot(sk):
					finite = finite and pose.origin.is_finite() and pose.basis.is_finite()
			check(finite and import_error < .0001, actor + " imported/native agreement " + clip + " " + str(import_error))
			if witnesses[actor].clips.has(clip):
				check(checked_witnesses > 70 and witness_error < .00003,
					actor + " GLB world witnesses " + clip + " " + str(witness_error) + " " + worst_witness)
			var hold_error := 0.0
			if clip in ["Sword_Attack", "Death_A"]:
				player.seek(animation.length - .04, true)
				var held := snapshot(sk)
				player.advance(.20)
				hold_error = difference(sk, held)
				check(not player.is_playing() and hold_error < .0001, actor + " terminal hold " + clip)
			player.play("Idle_A", 0.0)
			player.advance(.2)
			var restore_error := difference(sk, baseline)
			check(restore_error < .0001, actor + " idle restoration " + clip)
			actions.append({"clip":clip,"seconds":animation.length,"finite":finite,
				"imported_native_max_error":import_error,"hold_error":hold_error,"idle_restore_error":restore_error,
				"glb_world_witnesses":checked_witnesses,"glb_world_max_error":witness_error})
		records.append({"actor":actor,"skin_influences":skin_formats,"actions":actions})
		model.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	var report := {"passed":failures.is_empty(),"failures":failures,"actors":records,"engine":Engine.get_version_info()}
	var path := "user://canine-motion-runtime.json"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--report="): path = arg.trim_prefix("--report=")
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(report, "\t"))
	print("CANINE_RUNTIME ", "PASS" if failures.is_empty() else "FAIL", " actors=", records.size(), " failures=", failures.size())
	quit(0 if failures.is_empty() else 1)
