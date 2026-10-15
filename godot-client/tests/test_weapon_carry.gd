extends SceneTree

var failures := 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	for option: Dictionary in models.creationOptions:
		var model: Dictionary = models.models[option.model]
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(model.animationMap))
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 901, "x": 0, "y": 0, "rotation": 0,
			"appearance": {}, "equipment_visuals": {0: 114, 1: 160}}, adapter, model, animations, equipment)
		check(errors.is_empty(), "%s: %s" % [option.model, errors])
		actor.set_physics_process(false)
		actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var carry := actor._weapon_carry
		check(carry != null and carry.active, "dual wield enables carry: " + str(option.model))
		actor.play_action(&"walk", true)
		actor.animation_player.advance(0.01)
		await create_timer(actor.action_blend_seconds + 0.05).timeout
		check(is_equal_approx(float(carry.get("_weight")), 1.0), "carry blends in")
		for action: StringName in [&"walk", &"run"]:
			actor.play_action(action, true)
			actor._advance_facing_offset(1.0)
			for heading: float in [0.0, PI * 0.5, PI, -PI * 0.5]:
				actor.rotation.y = heading
				var hand_paths := {0: PackedVector3Array(), 1: PackedVector3Array()}
				for phase: float in [0.05, 0.3, 0.6, 0.9]:
					actor.animation_player.seek(actor.animation_player.current_animation_length * phase, true)
					var skeleton := actor.get_skeleton()
					var animated_arms := {}
					for side: String in ["r", "l"]:
						for segment: String in ["upperarm_", "lowerarm_", "hand_"]:
							var bone := skeleton.find_bone(segment + side)
							animated_arms[bone] = skeleton.get_bone_global_pose(bone)
					carry.call("_process_modification_with_delta", 0.0)
					for side: String in ["r", "l"]:
						for segment: String in ["upperarm_", "lowerarm_"]:
							var bone := skeleton.find_bone(segment + side)
							check((animated_arms[bone] as Transform3D).is_equal_approx(skeleton.get_bone_global_pose(bone)),
								"%s %s retains animated %s%s swing" % [option.model, action, segment, side])
					await process_frame
					await process_frame
					for part: int in [0, 1]:
						var attachment: BoneAttachment3D = actor._equipment_nodes[part][0]
						var prop := attachment.get_child(0) as Node3D
						var hand := skeleton.find_bone("hand_r" if part == 0 else "hand_l")
						var animated_wrist: Vector3 = skeleton.global_transform * (animated_arms[hand] as Transform3D).origin
						check(attachment.global_position.distance_to(animated_wrist) < 0.0001,
							"%s %s hand %d follows the unequipped animation path" % [option.model, action, part])
						hand_paths[part].append(actor.to_local(attachment.global_position))
						check(prop.global_basis.y.normalized().dot(-actor.global_basis.z.normalized()) > 0.98,
							"%s %s %.2f hand %d points forward" % [option.model, action, phase, part])
						check(prop.global_position.distance_to(attachment.global_position) < 0.12 * actor.rig_fit_scale(),
							"weapon stays in its grip: " + str(option.model))
				for part: int in [0, 1]:
					var forward_min := INF
					var forward_max := -INF
					for position: Vector3 in hand_paths[part]:
						forward_min = minf(forward_min, position.z)
						forward_max = maxf(forward_max, position.z)
					check(forward_max - forward_min > 0.08 * actor.rig_fit_scale(),
						"%s %s hand %d swings through the stride" % [option.model, action, part])
		# Fade back out, then compare the whole body with the unmodified clip.
		actor.play_action(&"idle", true)
		actor.animation_player.advance(0.2)
		await create_timer(actor.action_blend_seconds + 0.05).timeout
		check(is_zero_approx(float(carry.get("_weight"))), "carry releases on stopping")
		# At ease the off hand's arm alone is held out from the thigh, by the
		# spread its weapon's idle socket names (WeaponCarryPose._spread):
		# turned at the shoulder, with the rest of the body as the clip has it.
		var skeleton := actor.get_skeleton()
		var spread := float((equipment.models["1:160"].get("idleSocket", {}) as Dictionary).get("armSpread", 0.0))
		var held_out := {}
		if spread > 0.0:
			for bone: int in skeleton.get_bone_count():
				var walk := bone
				while walk >= 0 and skeleton.get_bone_name(walk) != "upperarm_l":
					walk = skeleton.get_bone_parent(walk)
				if walk >= 0:
					held_out[bone] = true
		for action: StringName in [&"idle", &"attack_primary", &"ranged_draw", &"cast_aggressive", &"death"]:
			actor.play_action(action, true)
			actor.animation_player.advance(0.15)
			var before: Array[Transform3D] = []
			var before_local: Array[Transform3D] = []
			var expected_fingers := {}
			for side: String in ["r", "l"]:
				for finger: Array in carry.call("_fist", skeleton, side):
					expected_fingers[finger[0]] = finger[1]
			for bone: int in skeleton.get_bone_count():
				before.append(skeleton.get_bone_global_pose(bone))
				before_local.append(skeleton.get_bone_pose(bone))
			carry.call("_process_modification_with_delta", 1.0)
			for bone: int in skeleton.get_bone_count():
				if action == &"idle" and expected_fingers.has(bone):
					check(skeleton.get_bone_pose_rotation(bone).angle_to(expected_fingers[bone]) < 0.01,
						"%s idle closes %s into the combat fist" % [option.model, skeleton.get_bone_name(bone)])
					continue
				var bone_name := skeleton.get_bone_name(bone)
				if action == &"idle" and bone_name in ["hand_r", "hand_l"]:
					check(before[bone].origin.distance_to(skeleton.get_bone_global_pose(bone).origin) < 0.0001,
						"%s idle wrist keeps its animated position" % option.model)
					var part := 0 if bone_name == "hand_r" else 1
					var prop := actor._equipment_nodes[part][0].get_child(0) as Node3D
					check(prop.transform.is_equal_approx(prop.get_meta(&"fighting_grip")),
						"%s idle socket stays inside the fist" % option.model)
					continue
				var ancestor := skeleton.get_bone_parent(bone)
				var finger_leaf := false
				while ancestor >= 0:
					if skeleton.get_bone_name(ancestor) in ["hand_r", "hand_l"]:
						finger_leaf = true
						break
					ancestor = skeleton.get_bone_parent(ancestor)
				if action == &"idle" and finger_leaf:
					check(before_local[bone].is_equal_approx(skeleton.get_bone_pose(bone)),
						"%s idle retains the local pose of the fingertip leaf" % option.model)
					continue
				check(before[bone].is_equal_approx(skeleton.get_bone_global_pose(bone)),
					"non-travel pose is unchanged: %s %s" % [option.model, action])
			if action == &"idle":
				for arm: String in ["upperarm_r", "lowerarm_r", "upperarm_l", "lowerarm_l"]:
					var bone := skeleton.find_bone(arm)
					check(before[bone].is_equal_approx(skeleton.get_bone_global_pose(bone)),
						"%s closing the idle fist retains %s" % [option.model, arm])
		actor.current_action = &"idle"
		actor.play_action(&"run", true)
		actor.animation_player.advance(0.01)
		var gate := AnimationGate.new()
		actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
		check(not carry.active, "offscreen carry pauses")
		actor.set_animation_tier(AnimationGate.Tier.FULL, gate)
		check(carry.active, "visible carry resumes")
		actor.apply_equipment_visuals({0: 64})
		check(carry.active, "the bow closes its holding hand")
		var bow_hands: Array = carry.get("_hands")
		check(bow_hands.size() == 1 and bow_hands[0].side == "l" and bow_hands[0].get("finger_only", false),
			"the bow keeps its own pose and only closes the holding left hand")
		actor.apply_equipment_visuals({0: 114})
		check(carry.active and (carry.get("_hands") as Array).size() == 1, "swapping back enables main hand only")
		actor.apply_equipment_visuals({})
		check(not carry.active, "unarmed locomotion is unchanged")
		actor.queue_free()
		await process_frame
	print("weapon carry tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	NativeAnimationImporter.clear()
	quit(0 if failures == 0 else 1)
