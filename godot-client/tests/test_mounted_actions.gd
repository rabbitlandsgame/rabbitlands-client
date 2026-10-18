extends SceneTree
## Compare the composed actor to a second, independently advancing rider.
## Every bone below the upper-body mask must keep its exact riding transform.
var failures := 0
var checks := 0
var max_lower_error := 0.0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func make_rider(body: String, models: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var config: Dictionary = models[body]
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var errors := actor.configure({"actor_id": 42, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "", "appearance": {"hair": 0}, "equipment_visuals": {0: 164}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config, animations, equipment)
	expect(errors.is_empty(), body + " loads: " + str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.rotation.y = 1.1
	actor._presentation_speed = 3.75
	return actor

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := make_rider(body, models)
		var baseline := make_rider(body, models)
		var rig := actor.get_skeleton()
		var reference := baseline.get_skeleton()
		var authoritative := actor.global_transform
		for gait: String in ["walk", "cruise", "burst"]:
			for rider: ReplicatedActor3D in [actor, baseline]:
				rider.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": gait, "step_us": 200000}, models)
				rider._mount_visual.set_process(false)
				rider.play_action(&"run")
				rider._mount_visual._process(0.0)
			var visual: Variant = actor._mount_visual
			var comparison: Variant = baseline._mount_visual
			for requested: StringName in [&"ranged_draw", &"ranged_hold", &"ranged_attack",
					&"cast_aggressive", &"cast_defensive", &"heal", &"cast_channel_enter", &"cast_channel", &"cast_exit"]:
				if requested == &"cast_aggressive":
					actor.set_spell_variant(2)
				elif requested == &"cast_defensive":
					actor.set_spell_variant(75)
				elif requested == &"heal":
					actor.set_spell_variant(3)
				expect(visual.upper.clips.has(requested), body + " source clip exists: " + str(requested))
				actor.play_action(requested, true)
				expect(visual.upper.clips[requested] == actor.animation_player.get_animation(actor.resolver.clip_for_action(requested)),
					"uses current spell/technique variant")
				var start := rig.get_bone_pose_rotation(rig.find_bone("upperarm_r"))
				for frame: int in 24:
					if frame == 8:
						actor.play_action(&"run")
						expect(not visual.upper.action.is_empty(), "movement preserves active upper-body action")
					visual._process(1.0 / 60.0)
					comparison._process(1.0 / 60.0)
					expect(actor.global_transform.is_equal_approx(authoritative), "action preserves authoritative actor position")
					var worst := 0.0
					for bone: int in rig.get_bone_count():
						if bone in visual.upper.bones:
							continue
						var current := rig.get_bone_global_pose(bone)
						var target := reference.get_bone_global_pose(bone)
						worst = maxf(worst, current.origin.distance_to(target.origin))
						worst = maxf(worst, current.basis.x.distance_to(target.basis.x))
						worst = maxf(worst, current.basis.y.distance_to(target.basis.y))
						worst = maxf(worst, current.basis.z.distance_to(target.basis.z))
					max_lower_error = maxf(max_lower_error, worst)
					expect(worst < 0.00001, body + " " + gait + " " + str(requested) + " legs remain riding: " + str(worst))
				var end := rig.get_bone_pose_rotation(rig.find_bone("upperarm_r"))
				expect(start.angle_to(end) > .01, "upper body moves for " + str(requested))
				if requested in [&"ranged_draw", &"ranged_hold", &"ranged_attack"]:
					expect(actor.combat_presentation.bow != null and actor.combat_presentation.bow.visible,
						"actual bow is visible while shooting")
					if requested != &"ranged_attack":
						var right := actor.combat_presentation.hand_position(rig.find_bone("hand_r"))
						expect(actor.combat_presentation.bow.nock_position().distance_to(right) < .03,
							"arrow nock stays at the drawing fingers")
				actor.play_action(&"idle")
				baseline.play_action(&"idle")
				for frame: int in 150:
					visual._process(1.0 / 60.0)
					comparison._process(1.0 / 60.0)
				expect(visual.upper.action.is_empty(), "action returns to the reins: " + str(requested))
				expect(visual.upper.grip_weight == 0.0, "rein contact restores after action")
				var recovery_error := 0.0
				for bone: int in rig.get_bone_count():
					var current := rig.get_bone_global_pose(bone)
					var target := reference.get_bone_global_pose(bone)
					recovery_error = maxf(recovery_error, current.origin.distance_to(target.origin))
					recovery_error = maxf(recovery_error, current.basis.x.distance_to(target.basis.x))
					recovery_error = maxf(recovery_error, current.basis.y.distance_to(target.basis.y))
					recovery_error = maxf(recovery_error, current.basis.z.distance_to(target.basis.z))
				expect(recovery_error < 0.00001, "all bones return to the riding pose: " + str(recovery_error))
				expect(actor.combat_presentation.bow == null or not actor.combat_presentation.bow.visible,
					"shooting prop hides after recovery")
				actor.play_action(&"run")
				baseline.play_action(&"run")
			actor.play_action(&"cast_aggressive", true)
			visual._process(.3)
			actor.set_mount_state({}, models)
			baseline.set_mount_state({}, models)
			expect(actor.animation_player.is_playing(), "dismount during action restores normal playback")
		actor.free()
		baseline.free()
	print("MOUNTED_ACTION_CHECKS ", checks, " failures=", failures, " max_lower_error=", max_lower_error)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
