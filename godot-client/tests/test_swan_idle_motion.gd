extends SceneTree
## Off-grid GLB witnesses, continuous idle motion, and production transitions.

var failures := 0
var checks := 0
var maximum_position_error := 0.0
var maximum_basis_error := 0.0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = registry.models.swan.duplicate(true)
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--model="):
			config.scene = argument.trim_prefix("--model=")
			config.animationLibrary = config.scene
	var witness: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/swan-idle-motion.json"))
	expect(FileAccess.get_sha256(config.scene) == witness.sha256, "witness binds the exact Swan revision")
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	var dto := {"actor_id": 901, "actor_type": 717, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
		"x": 0, "y": 0, "rotation": 0, "health": 100, "max_health": 100,
		"alive": true, "appearance": {}, "equipment_visuals": {}, "command_sequence": 0}
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure(dto, adapter, config, mapping)
	expect(errors.is_empty(), "production Swan configures: " + str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	var player := actor.animation_player
	var skeleton := actor.get_skeleton()
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var model := actor.get_node("NativeModel") as Node3D
	for clip: String in witness.clips:
		expect(player.get_animation(clip).loop_mode == Animation.LOOP_LINEAR, clip + " loops")
		for entry: Dictionary in witness.clips[clip]:
			player.stop()
			skeleton.reset_bone_poses()
			player.play(clip, 0.0)
			player.seek(float(entry.time), true)
			skeleton.force_update_all_bone_transforms()
			for name: String in entry.bones:
				var values: Array = entry.bones[name]
				var actual := model.global_transform.affine_inverse() * skeleton.global_transform \
					* skeleton.get_bone_global_pose(skeleton.find_bone(name))
				var position := Vector3(values[3], values[7], values[11])
				maximum_position_error = maxf(maximum_position_error, actual.origin.distance_to(position))
				for axis in 3:
					var expected := Vector3(values[axis], values[4 + axis], values[8 + axis])
					maximum_basis_error = maxf(maximum_basis_error, actual.basis[axis].distance_to(expected))
		# Meaningful changes, rather than exact-float noise from a held pose.
		player.stop()
		player.play(clip, 0.0)
		var neck := skeleton.find_bone("neck_01")
		var start := skeleton.get_bone_pose_rotation(neck)
		var changed := 0
		for sample in 40:
			player.advance(0.05)
			if start.angle_to(skeleton.get_bone_pose_rotation(neck)) > deg_to_rad(0.5):
				changed += 1
		expect(changed > 10, clip + " has sustained visible motion")
		player.advance(player.get_animation(clip).length * 3.0)
		expect(player.is_playing(), clip + " continues beyond a whole loop")
	expect(maximum_position_error < 0.0005, "off-grid independent GLB bone positions")
	expect(maximum_basis_error < 0.001, "off-grid independent GLB bone bases")
	# Real actor commands return attacks and pain to the new alert loop.
	dto = ActorReducer.apply_command(dto, 18)
	actor.apply_server_state(dto, adapter)
	for command in [46, 5]:
		dto = ActorReducer.apply_command(dto, command)
		actor.apply_server_state(dto, adapter)
		player.advance(3.0)
		expect(actor.current_action == &"combat_idle", "one-shot returns to alert idle")
	var gate := AnimationGate.new()
	for tier in [AnimationGate.Tier.HALF, AnimationGate.Tier.QUARTER]:
		actor.set_animation_tier(tier, gate)
		var before := player.current_animation_position
		for frame in 20: gate.advance(0.05)
		expect(not is_equal_approx(before, player.current_animation_position), "gated idle clock advances")
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	expect(not player.active, "offscreen idle pauses")
	actor.set_animation_tier(AnimationGate.Tier.FULL, gate)
	expect(player.active, "returning to view resumes idle")
	dto = ActorReducer.apply_command(dto, 3)
	actor.apply_server_state(dto, adapter)
	player.advance(4.0)
	expect(actor.current_action == &"death" and not player.is_playing(), "death still ends and holds")
	actor.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("SWAN_IDLE_MOTION ", "PASS" if failures == 0 else "FAIL", " checks=", checks,
		" position_error=", maximum_position_error, " basis_error=", maximum_basis_error)
	quit(0 if failures == 0 else 1)
