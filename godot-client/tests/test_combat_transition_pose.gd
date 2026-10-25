extends SceneTree
## Sample production combat recovery at 240 Hz, including each player's
## equipment swaps. An all-rest frame is a defect even if both endpoints play.
var failures := 0
var samples := 0
var minimum_rest_distance := INF
func _init() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
func pose(skeleton: Skeleton3D) -> Array[Transform3D]:
	var result: Array[Transform3D] = []
	for bone: int in skeleton.get_bone_count(): result.append(skeleton.get_bone_pose(bone))
	return result
func distance(a: Array[Transform3D], b: Array[Transform3D]) -> float:
	var value := 0.0
	for i: int in a.size():
		value += a[i].origin.distance_to(b[i].origin)
		value += a[i].basis.get_rotation_quaternion().angle_to(b[i].basis.get_rotation_quaternion())
	return value
func run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for option: Dictionary in registry.creationOptions:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 900, "kind": 1, "x": 0, "y": 0, "rotation": 0,
			"health": 100, "max_health": 100, "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({}), registry.models[option.model], mapping, equipment)
		check(errors.is_empty(), "production rig imports: " + str(option.model))
		actor.set_physics_process(false)
		var player := actor.animation_player
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		player.play("RESET", 0)
		player.advance(0)
		var rest := pose(actor.get_skeleton())
		# End the reference probe explicitly; RESET is not a gameplay action.
		player.play(actor.resolver.clip_for_action(&"idle"), 0)
		player.advance(.3)
		for weapon: int in [-1, 64, 164]:
			actor.apply_equipment_visuals({} if weapon < 0 else {0: weapon})
			actor.play_action(&"idle")
			player.advance(.3)
			# A sparse fade consumed by the first frame used to produce a full
			# bind pose. Verify actual hand locations, not only RESET distance.
			for next: StringName in [&"walk", &"run", &"combat_idle", &"idle"]:
				actor.play_action(next)
				player.advance(.3)
				var sk := actor.get_skeleton()
				var left := sk.get_bone_global_pose(sk.find_bone("hand_l")).origin
				var right := sk.get_bone_global_pose(sk.find_bone("hand_r")).origin
				check(absf(left.x - right.x) < 1.2, "large first step %s/%s/%d hands=%s/%s" % [option.model, next, weapon, left, right])
				for frame: int in 24: player.advance(1.0 / 240)
			for action: StringName in [&"attack_primary", &"attack_secondary", &"pain", &"ranged_attack"]:
				actor.play_action(action, true)
				var duration := player.current_animation_length
				# Reach the final 0.15s, then sample every transition frame.
				player.advance(maxf(0, duration / player.speed_scale - .15))
				for frame: int in 144:
					player.advance(1.0 / 240.0)
					var delta := distance(pose(actor.get_skeleton()), rest)
					minimum_rest_distance = minf(minimum_rest_distance, delta)
					check(delta > .01, "no RESET flash: %s/%s/%d/%d" % [option.model, action, weapon, frame])
					check(player.is_playing(), "recovery retains a playing clip")
					samples += 1
		actor.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("combat recovery 240Hz samples=", samples, " minimum_rest_distance=", minimum_rest_distance, " failures=", failures)
	quit(failures)
