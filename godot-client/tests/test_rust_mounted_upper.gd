extends "res://tests/test_rust_mounted_pose.gd"
## Uses the base fixture's actual rigs, optional-library validation, complete
## pose comparison, isolated mount lifecycle and drained resource cleanup.

func _pair(body: String, scale: float, changed_rest: bool) -> void:
	# The base pose fixture separately covers both scales and altered rest.
	if changed_rest:
		return
	var actors: Array[ReplicatedActor3D] = []
	for index: int in 3:
		var actor := _actor(body, 1800 + index, scale, false)
		if actor != null:
			actors.append(actor)
	if actors.size() != 3:
		await _retire(actors)
		return
	actors[0].get("_mount_visual").rust_pose.configure(actors[0].get("_mount_visual").pose, _mount_id, null, null, "legacy")
	for index: int in [1, 2]:
		actors[index]._mount_visual.rust_pose.configure(actors[index]._mount_visual.pose, _mount_id, _controller)
	for requested: StringName in actors[0].get("_mount_visual").upper.ACTIONS:
		for actor: ReplicatedActor3D in actors:
			actor.play_action(requested, true)
		var upper = actors[0].get("_mount_visual").upper
		expect(upper.action == requested, "actual approved action clip available: " + str(requested))
		var rate := actors[0].resolver.playback_speed_for_action(requested)
		if requested == &"ranged_draw":
			rate = float(upper.duration()) / 0.25
		var duration := float(upper.duration()) / maxf(rate, 0.001)
		for delta: float in [0.0, 0.04, 0.1, duration + 0.03, 0.2]:
			var before: Dictionary = _controller.native.runtime_info()
			for actor: ReplicatedActor3D in actors:
				actor.get("_mount_visual")._step_visual(delta)
			Shim.flush_pending()
			var after: Dictionary = _controller.native.runtime_info()
			expect(int(after.pose_calls) == int(before.pose_calls) + 1, "upper actions keep one native batch")
			expect(int(after.upper_applied) == int(before.upper_applied) + 2, "both native upper poses were actually committed")
			for index: int in [1, 2]:
				_compare(actors[0], actors[index], body + " " + _mount_id + " " + str(requested))
				var other = actors[index]._mount_visual.upper
				expect(other.action == upper.action and other.ground_action == upper.ground_action
					and is_equal_approx(float(other.time), float(upper.time))
					and is_equal_approx(float(other.weight), float(upper.weight))
					and is_equal_approx(float(other.grip_weight), float(upper.grip_weight)),
					"compiled pose path preserves exact legacy action and grip clocks")
		# Explicit idle closes a held draw/channel; one-shot completion remains
		# controlled by its current clip rather than by movement packets.
		for actor: ReplicatedActor3D in actors:
			actor.play_action(&"idle", true)
			actor.get("_mount_visual")._step_visual(duration + 0.3)
		Shim.flush_pending()
		for actor: ReplicatedActor3D in actors:
			actor.get("_mount_visual")._step_visual(0.3)
		Shim.flush_pending()
		for index: int in [1, 2]:
			_compare(actors[0], actors[index], "explicit idle and recovery " + str(requested))
	await _retire(actors)
