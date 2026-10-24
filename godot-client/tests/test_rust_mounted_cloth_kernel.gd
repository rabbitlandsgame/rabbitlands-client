extends "res://tests/test_rust_mounted_cloth.gd"
## Kernel-only attribution on one actual legacy-posed mounted actor. The fork
## runs native on private copies of the exact incoming arrays, then deliberately
## rejects so the production wrapper computes its one current Script fallback
## on the untouched originals. The fixture explicitly re-arms this test-only
## rejection each step; it does not qualify fallback-free end-to-end execution.
const KERNEL_EPSILON := 0.000001

class ForkKernel extends RefCounted:
	var backend: RefCounted
	var predicted_points: Array = []
	var predicted_previous: Array = []
	var succeeded := false
	var caller_unchanged := false
	var calls := 0
	var surface_step := -1.0
	var last_arguments: Array = []
	func step_mounted_cape(points: Array, previous: Array, rests: Array, lengths: Array,
			world: PackedVector3Array, pairs: Array, axes: PackedVector3Array,
			spans: PackedFloat64Array, radii: PackedFloat64Array, reaches: Array,
			fall: Vector3, damping: float, forward: Vector3, plane: float, anchor: float,
			frame: Transform3D, settled: bool, surface: PackedFloat64Array) -> bool:
		var original_points := points.duplicate(true)
		var original_previous := previous.duplicate(true)
		predicted_points = points.duplicate(true)
		predicted_previous = previous.duplicate(true)
		surface_step = surface[16] if surface.size() >= 17 else -1.0
		last_arguments = [rests.duplicate(true), lengths.duplicate(true), world.duplicate(),
			pairs.duplicate(true), axes.duplicate(), spans.duplicate(), radii.duplicate(),
			reaches.duplicate(true), fall, damping, forward, plane, anchor, frame, settled, surface.duplicate()]
		succeeded = bool(backend.call("step_mounted_cape", predicted_points, predicted_previous,
			rests, lengths, world, pairs, axes, spans, radii, reaches, fall, damping,
			forward, plane, anchor, frame, settled, surface))
		caller_unchanged = points == original_points and previous == original_previous
		calls += 1
		return false # Intentional fork: run current Script once on the originals.

class ForkPose extends "res://src/mounts/rust_rider_pose.gd":
	var fork: RefCounted
	func try_fit(_seat: Transform3D, _gait: String, _seconds: float, _cycle: float, _finish: Callable) -> bool:
		return false # Same real legacy rider/body pose supplies both kernel paths.
	func mounted_constraint_backend() -> RefCounted:
		return fork

func _pair(body: String, scale: float, changed_rest: bool) -> void:
	if changed_rest:
		return # The full pose test separately qualifies altered-rest/native pose.
	var actor := _actor(body, 2950, scale, false)
	if actor == null:
		return
	actor.apply_render_quality(ActorRenderQuality.Quality.HIGH, false)
	var visual = actor.get("_mount_visual")
	visual.rust_pose.close()
	var fork := ForkKernel.new()
	fork.backend = _controller.native
	var driver := ForkPose.new()
	driver.configure(visual.pose, _mount_id, null, null, "legacy")
	driver.fork = fork
	visual.rust_pose = driver
	var cloth: SkeletonModifier3D = actor._cape_cloth
	expect(cloth != null and actor.wears_cape_cloth() and not cloth.active,
		"exact-input fork owns one real manual mounted cape")
	for gait: String in ["idle", "walk", "cruise", "burst", "cruise", "idle"]:
		visual.state.gait = gait
		actor.play_action(&"idle" if gait == "idle" else &"run", true)
		actor._presentation_speed = 0.0 if gait == "idle" else 5.0
		for frame: int in 24:
			if frame == 8:
				actor.play_action(&"cast_aggressive", true)
			if frame == 16:
				cloth.call("reset")
			if gait != "idle":
				actor.global_position += Vector3(0.013, 0, -0.04)
			_probe_step(actor, fork, 1.0 / 60.0, true, body + " " + gait + " frame%d" % frame)
		actor.global_position += Vector3(123, -4, 88)
		cloth.call("reset")
		_probe_step(actor, fork, 1.0 / 30.0, true, body + " teleport/reset")
	# These directly exercise the production cape delta clamp against the last
	# actual sampled animated surface, with no second pose/surface computation.
	for delta: float in [-0.25, 0.0, 0.25, 1.0 / 60.0]:
		_probe_step(actor, fork, delta, false, body + " direct delta " + str(delta))
	# Invalid new payload deltas are rejected atomically, not clamped natively.
	for invalid_step: float in [-0.001, 1.0 / 30.0 + 0.001]:
		var points: Array = (cloth.get("_points") as Array).duplicate(true)
		var previous: Array = (cloth.get("_previous") as Array).duplicate(true)
		var before_points := points.duplicate(true)
		var before_previous := previous.duplicate(true)
		var invalid_surface: PackedFloat64Array = visual.cape_surface.native_snapshot(invalid_step).duplicate()
		var arguments: Array = [points, previous]
		arguments.append_array(fork.last_arguments.duplicate(true))
		arguments[arguments.size() - 1] = invalid_surface
		# All other inputs are the last successful real sampled call, so bad
		# step validation cannot be masked by malformed rest/collision arrays.
		var rejected := bool(_controller.native.callv("step_mounted_cape", arguments))
		expect(not rejected and points == before_points and previous == before_previous,
			"out-of-range sampled step rejects without point/history publication")
	driver.fork = null
	fork.backend = null
	await _retire([actor])

func _probe_step(actor: ReplicatedActor3D, fork: ForkKernel, delta: float, drive_visual: bool, label: String) -> void:
	var cloth: SkeletonModifier3D = actor._cape_cloth
	var before: Dictionary = cloth.call("native_presentation_stats")
	var native_before: Dictionary = _controller.native.runtime_info()
	var calls_before := fork.calls
	# Intentional-fallback test only: permit another fork after the production
	# wrapper correctly disabled the previous rejected test backend.
	cloth.set("_native_mounted_constraint_disabled", false)
	cloth.call("set_native_mounted_constraint_kernel", fork)
	if drive_visual:
		actor.get("_mount_visual")._step_visual(delta)
	else:
		cloth.call("_process_modification_with_delta", delta)
	var after: Dictionary = cloth.call("native_presentation_stats")
	var native_after: Dictionary = _controller.native.runtime_info()
	expect(fork.calls == calls_before + 1 and fork.succeeded and fork.caller_unchanged,
		label + " real native fork solves exact inputs and leaves Script originals untouched")
	expect(int(native_after.mounted_cape_calls) == int(native_before.mounted_cape_calls) + 1,
		label + " records exactly one real native solve")
	expect(int(after.mountedCalls) == int(before.mountedCalls)
		and int(after.mountedFallbackCalls) == int(before.mountedFallbackCalls) + 1,
		label + " records exactly one intentionally rejected fork/current Script fallback")
	expect(absf(fork.surface_step - clampf(delta, 0.0, 1.0 / 30.0)) < 1e-15,
		label + " payload retains original clamped delta rather than squared delta")
	_compare_exact_states(cloth.get("_points"), fork.predicted_points, label + " points")
	_compare_exact_states(cloth.get("_previous"), fork.predicted_previous, label + " history")

func _compare_exact_states(script: Array, native: Array, label: String) -> void:
	expect(script.size() == 3 and native.size() == 3, label + " all chains")
	if script.size() != 3 or native.size() != 3:
		return
	var maximum := 0.0
	for chain: int in 3:
		var left: PackedVector3Array = script[chain]
		var right: PackedVector3Array = native[chain]
		expect(left.size() == 5 and right.size() == 5, label + " all links")
		if left.size() != 5 or right.size() != 5:
			return
		for point: int in 5:
			maximum = maxf(maximum, left[point].distance_to(right[point]))
	expect(maximum <= KERNEL_EPSILON, label + " exact-input error=" + str(maximum))
