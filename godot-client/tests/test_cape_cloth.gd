extends SceneTree
## Exercises the cape cloth solver on a real rig, and times it.
##
## The defect it exists for is measurable: with the cape rigidly skinned to the
## spine, a leg swung back passes straight through it - 254 mm in a walk and
## 858 mm in a run. This poses a leg back far enough to reach the cape, settles
## the solver, and checks the chain has been pushed clear.

const RIG := "res://assets/actors/native/races/luminous_male.glb"
const CLOTH := "res://src/actors/cape_cloth.gd"
const STEP := 1.0 / 60.0
const LEG_RADIUS := 0.115
const CHAINS := ["l", "c", "r"]
const LINKS := 4
## LAT-L3: a display frame under the 30 FPS cap.
const FRAME_30 := 1.0 / 30.0

var failures := 0


## Counts solver steps and long-step coefficient lookups (LAT-L3).
class CountingCloth extends "res://src/actors/cape_cloth.gd":
	var steps := 0
	var long_steps := 0

	func _simulate_step(delta: float, simulation_world: Transform3D) -> void:
		steps += 1
		super(delta, simulation_world)

	func _long_step_coefficients(damping: float, step_count: float) -> Vector2:
		long_steps += 1
		return super(damping, step_count)


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("cape cloth: " + message)
		print("  FAIL ", message)
	else:
		print("  ok   ", message)


func _joints(skeleton: Skeleton3D) -> PackedVector3Array:
	var out := PackedVector3Array()
	for chain in CHAINS:
		for link in range(LINKS):
			out.append(skeleton.get_bone_global_pose(
				skeleton.find_bone("cape_%s_%02d" % [chain, link + 1])).origin)
	return out


func _leg_clearance(skeleton: Skeleton3D, points: PackedVector3Array) -> float:
	"""Smallest distance from the cloth samples to either leg bone, in metres."""
	var worst := 99.0
	for side in ["l", "r"]:
		var a := skeleton.get_bone_global_pose(skeleton.find_bone("thigh_%s" % side)).origin
		var b := skeleton.get_bone_global_pose(skeleton.find_bone("calf_%s" % side)).origin
		var axis := b - a
		var span := axis.length_squared()
		for point in points:
			var travel := 0.0 if span < 1e-9 else clampf((point - a).dot(axis) / span, 0.0, 1.0)
			worst = minf(worst, point.distance_to(a + axis * travel))
	return worst


func _run() -> void:
	# Native actor shipping folders are deliberately not editor-imported.
	var actor := GlbSceneCache.instantiate(RIG)
	if actor == null:
		push_error("cape cloth: cannot load " + RIG)
		quit(1)
		return
	root.add_child(actor)
	var skeleton: Skeleton3D = null
	for node in actor.find_children("*", "Skeleton3D", true, false):
		skeleton = node as Skeleton3D
		break
	if skeleton == null:
		push_error("cape cloth: the rig has no Skeleton3D")
		quit(1)
		return

	_expect(skeleton.find_bone("cape_c_01") >= 0, "the rig carries the cape chains")
	var cloth: SkeletonModifier3D = (load(CLOTH) as Script).new()
	skeleton.add_child(cloth)
	cloth.active = true
	await process_frame

	# Swing a leg back far enough to reach a cape that hangs from the spine.
	var thigh := skeleton.find_bone("thigh_l")
	skeleton.set_bone_pose_rotation(thigh,
		skeleton.get_bone_rest(thigh).basis.get_rotation_quaternion()
		* Quaternion(Vector3.RIGHT, deg_to_rad(-45.0)))
	await process_frame

	var rest_clearance := _leg_clearance(skeleton, _joints(skeleton))
	for _step in range(90):
		cloth.call("_process_modification_with_delta", STEP)
	# Helper bone origins carry offsets from the fabric's material line;
	# collision and segment lengths belong to the simulated fabric itself.
	var settled := PackedVector3Array()
	for chain: PackedVector3Array in cloth.get("_points"):
		for link: int in range(LINKS):
			settled.append(skeleton.to_local(chain[link]))
	var solved_clearance := _leg_clearance(skeleton, settled)

	print("  leg clearance before solving: %.1f mm" % (rest_clearance * 1000.0))
	print("  leg clearance after solving:  %.1f mm" % (solved_clearance * 1000.0))
	_expect(solved_clearance > LEG_RADIUS - 0.02,
		"the solved cape clears the swung leg")
	_expect(solved_clearance > rest_clearance,
		"solving moves the cape further from the leg than rest does")

	# The chain must keep its length: a Verlet chain that stretches has lost
	# its constraints, and a cape that stretches tears away from the collar.
	var stretched := 0
	for chain_index in range(CHAINS.size()):
		for link in range(1, LINKS):
			var here: Vector3 = settled[chain_index * LINKS + link]
			var above: Vector3 = settled[chain_index * LINKS + link - 1]
			var rest_length := skeleton.get_bone_rest(skeleton.find_bone(
				"cape_%s_%02d" % [CHAINS[chain_index], link + 1])).origin.length()
			if absf(here.distance_to(above) - rest_length) > 0.02:
				stretched += 1
	_expect(stretched == 0, "the chains keep their link lengths (%d stretched)" % stretched)

	# Inactive must mean free: with no cape worn the solver may not touch a bone.
	cloth.active = false
	skeleton.reset_bone_poses()
	await process_frame
	var untouched := _joints(skeleton)
	for _step in range(10):
		await process_frame
	var moved := 0
	var now := _joints(skeleton)
	for index in range(now.size()):
		if now[index].distance_to(untouched[index]) > 1e-5:
			moved += 1
	_expect(moved == 0, "an inactive solver leaves every cape bone at rest")

	# Cost. What matters is the per-actor, per-frame price of the solver.
	cloth.active = true
	for _warm in range(10):
		cloth.call("_process_modification_with_delta", STEP)
	var iterations := 2000
	var started := Time.get_ticks_usec()
	for _step in range(iterations):
		cloth.call("_process_modification_with_delta", STEP)
	var each := float(Time.get_ticks_usec() - started) / float(iterations)
	print("  solver cost: %.1f us per actor per frame" % each)
	print("  at 60 fps that is %.2f%% of one frame per actor" % (each / 16666.0 * 100.0))
	for crowd in [10, 20, 50]:
		print("    %d caped actors: %.2f ms per frame" % [crowd, each * crowd / 1000.0])
	_expect(each < 200.0, "the solver costs under 200 us per actor")

	await _check_step_rate()

	print("cape cloth tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures > 0 else 0)


## A bare rig carrying a counting solver, `hz` steps a second, under its own
## holder so it can travel.
func _spawn_rate_rig(hz: int) -> Dictionary:
	var holder := Node3D.new()
	root.add_child(holder)
	var actor := GlbSceneCache.instantiate(RIG)
	holder.add_child(actor)
	var skeleton: Skeleton3D = null
	for node in actor.find_children("*", "Skeleton3D", true, false):
		skeleton = node as Skeleton3D
		break
	var cloth := CountingCloth.new()
	skeleton.add_child(cloth)
	# Stepped by hand only: the engine's own modifier pass stays out of it.
	cloth.active = false
	cloth.set_step_rate(hz)
	return {"holder": holder, "skeleton": skeleton, "cloth": cloth,
		"anchor": skeleton.find_bone("spine_03")}


## How far behind its anchor the middle hem trails, in degrees from hanging
## straight down (the rig faces +z and walks that way).
func _hem_angle(rig: Dictionary) -> float:
	var skeleton: Skeleton3D = rig.skeleton
	var anchor := skeleton.global_transform * skeleton.get_bone_global_pose(rig.anchor).origin
	var middle: PackedVector3Array = (rig.cloth.get("_points") as Array)[1]
	var hem := middle[middle.size() - 1]
	return rad_to_deg(atan2(anchor.z - hem.z, anchor.y - hem.y))


## One 1/30 s frame of a rig travelling at `speed` m/s: its solver's cost in us.
func _timed_frame(rig: Dictionary, speed: float) -> float:
	(rig.holder as Node3D).position.z += speed * FRAME_30
	var started := Time.get_ticks_usec()
	rig.cloth.call("_process_modification_with_delta", FRAME_30)
	return float(Time.get_ticks_usec() - started)


## Each rig's mean hem angle over the last second of `seconds` at `speed` m/s,
## in 1/30 s frames.
func _travel(rigs: Array, speed: float, seconds: float) -> PackedFloat32Array:
	var frames := roundi(seconds / FRAME_30)
	var sums := PackedFloat32Array()
	sums.resize(rigs.size())
	for frame: int in range(frames):
		for index: int in range(rigs.size()):
			var rig: Dictionary = rigs[index]
			(rig.holder as Node3D).position.z += speed * FRAME_30
			rig.cloth.call("_process_modification_with_delta", FRAME_30)
			if frame >= frames - 30:
				sums[index] += _hem_angle(rig) / 30.0
	return sums


## LAT-L3: the Low actor tier solves the local cape at 30 Hz. Its coefficients
## stand for two 60 Hz steps, so under the 30 FPS cap it steps once per drawn
## frame instead of twice and hangs, trails and settles like the 60 Hz cape.
## The worn-cape half (measured fabric, clips, the approved path) is
## tests/test_cape_step_rate.gd.
func _check_step_rate() -> void:
	print("  -- step rate (LAT-L3)")
	var probe := CountingCloth.new()
	var fixed: float = probe.FIXED_STEP
	_expect(probe.step_rate() == 60 and probe.call("_simulation_step") == fixed,
		"a new solver steps at 60 Hz")
	probe.set_step_rate(30)
	_expect(probe.step_rate() == 30 and probe.call("_simulation_step") == 1.0 / 30.0,
		"set_step_rate(30) steps every 1/30 s")
	probe.set_step_rate(60)
	_expect(probe.call("_simulation_step") == fixed, "set_step_rate(60) is FIXED_STEP exactly")
	var clamped := []
	for hz: int in [45, 10, 0, -5, 120]:
		probe.set_step_rate(hz)
		clamped.append(probe.step_rate())
	_expect(clamped == [45, 30, 60, 60, 60],
		"rates stay within 30-60 Hz and nonsense means 60 (%s)" % [clamped])
	# Mounted cloth keeps its own clock: 60 Hz on desktop (30 Hz only in the
	# browser build), and the static mounted fit always 60 Hz.
	probe.set_step_rate(30)
	probe.set("_mount_surface", RefCounted.new())
	var mounted_step: float = probe.call("_simulation_step")
	probe.set("_mount_surface", null)
	probe.set("_fitting_mounted_static", true)
	var fitting_step: float = probe.call("_simulation_step")
	probe.set("_fitting_mounted_static", false)
	_expect(mounted_step == (1.0 / 30.0 if OS.has_feature("web") else fixed)
		and fitting_step == fixed and probe.step_rate() == 30,
		"a rider's cape and the static mounted fit ignore the unmounted rate")
	var one: Vector2 = probe.call("_long_step_coefficients", 0.42, 1.0)
	var two: Vector2 = probe.call("_long_step_coefficients", 0.30, 2.0)
	_expect(one == Vector2(0.42, 1.0), "one 60 Hz step keeps its damping and gravity")
	_expect(is_equal_approx(two.x, 0.09) and is_equal_approx(two.y, 0.65),
		"a 30 Hz step damps d^2 and scales gravity by (1 + d) / 2 (%s)" % [two])
	_expect(float(probe.call("_long_step_guard_carry", 0.72, 1.0)) == 0.0
		and is_equal_approx(float(probe.call("_long_step_guard_carry", 0.72, 2.0)), 1.0 / 0.72),
		"a 30 Hz step carries a guard's kick a further d / d^2, a 60 Hz step nothing")
	# No chain yet reads as at rest: one 60 Hz step's pull, 1 / (2 (1 + d)).
	_expect(float(probe.call("_long_step_rest_scale", 0.30, 1.0)) == 1.0
		and is_equal_approx(float(probe.call("_long_step_rest_scale", 0.30, 2.0)), 1.0 / 2.6),
		"a still 30 Hz cape at rest takes one 60 Hz step's pull, a 60 Hz step all of it")
	probe.free()

	var fast := _spawn_rate_rig(60)
	var slow := _spawn_rate_rig(30)
	await process_frame
	for rig: Dictionary in [fast, slow]:
		rig.cloth.call("reset")
	# Steps per drawn frame.
	for _frame: int in range(90):
		for rig: Dictionary in [fast, slow]:
			rig.cloth.call("_process_modification_with_delta", FRAME_30)
	_expect(slow.cloth.steps == 90 and fast.cloth.steps == 180,
		"at 1/30 s frames 30 Hz steps once a frame and 60 Hz twice (%d, %d)"
		% [slow.cloth.steps, fast.cloth.steps])
	_expect(fast.cloth.long_steps == 0 and slow.cloth.long_steps == slow.cloth.steps,
		"only the 30 Hz solver uses the long-step coefficients")
	slow.cloth.steps = 0
	for _frame: int in range(90):
		slow.cloth.call("_process_modification_with_delta", STEP)
	_expect(slow.cloth.steps == 45, "at 1/60 s frames 30 Hz steps every other frame (%d)"
		% slow.cloth.steps)
	# An uneven frame rate around the cap: never two steps in one frame, and
	# no time lost or gained beyond the step still owed.
	slow.cloth.steps = 0
	var most := 0
	var seconds := 0.0
	var lcg := 11
	for _frame: int in range(300):
		lcg = (lcg * 1103515245 + 12345) % 2147483648
		var delta := 0.025 + float(lcg % 1000) / 1000.0 * 0.020
		var before: int = slow.cloth.steps
		slow.cloth.call("_process_modification_with_delta", delta)
		most = maxi(most, slow.cloth.steps - before)
		seconds += minf(delta, FRAME_30)
	_expect(most == 1 and absi(slow.cloth.steps - floori(seconds / FRAME_30)) <= 1,
		"25-45 ms frames step at most once each and keep time (%d steps in %.3f s)"
		% [slow.cloth.steps, seconds])

	# Walk, run, stop. The bare chain has no measured fabric, so this is the
	# Verlet arithmetic itself: 30 Hz must trail like 60 Hz.
	for rig: Dictionary in [fast, slow]:
		rig.cloth.call("reset")
	var idle := _travel([fast, slow], 0.0, 3.0)
	var walk := _travel([fast, slow], 1.5, 2.0)
	var run := _travel([fast, slow], 5.0, 2.0)
	var stopped := _travel([fast, slow], 0.0, 3.0)
	print("  hem trail, deg (60 Hz / 30 Hz): idle %.1f / %.1f, walk %.1f / %.1f, run %.1f / %.1f, stopped %.1f / %.1f"
		% [idle[0], idle[1], walk[0], walk[1], run[0], run[1], stopped[0], stopped[1]])
	for phase: Array in [["walking", walk], ["running", run]]:
		var pair: PackedFloat32Array = phase[1]
		var swing60 := pair[0] - idle[0]
		var swing30 := pair[1] - idle[1]
		_expect(absf(swing30 - swing60) <= 0.05 * swing60,
			"a 30 Hz bare chain trails within 5%% of 60 Hz %s (%.1f vs %.1f deg)"
			% [phase[0], swing30, swing60])
	# The bare hem rests on the trunk capsule, where a step's pull decides the
	# hang: with two steps' pull in one it hung 15 mm off. At rest the long
	# step takes one 60 Hz step's pull (`_long_step_rest_scale`).
	var apart := 0.0
	var fast_points: Array = fast.cloth.get("_points")
	var slow_points: Array = slow.cloth.get("_points")
	var offset: Vector3 = (slow.holder as Node3D).position - (fast.holder as Node3D).position
	for chain: int in range(fast_points.size()):
		for index: int in range((fast_points[chain] as PackedVector3Array).size()):
			apart = maxf(apart, ((slow_points[chain] as PackedVector3Array)[index] - offset)
				.distance_to((fast_points[chain] as PackedVector3Array)[index]))
	_expect(apart < 0.002, "the stopped bare chains hang where 60 Hz hangs (%.1f mm apart)" % (apart * 1000.0))

	# Cost per drawn frame at the cap, walking: the two rates timed frame by
	# frame, side by side, and compared by their medians, so a stall on a shared
	# machine does not decide it.
	var fast_frames := PackedFloat32Array()
	var slow_frames := PackedFloat32Array()
	for _frame: int in range(600):
		fast_frames.append(_timed_frame(fast, 1.5))
		slow_frames.append(_timed_frame(slow, 1.5))
	fast_frames.sort()
	slow_frames.sort()
	var costs := PackedFloat32Array([fast_frames[fast_frames.size() / 2],
		slow_frames[slow_frames.size() / 2]])
	print("  bare solver per 1/30 s frame, walking (median): %.1f us at 60 Hz, %.1f us at 30 Hz"
		% [costs[0], costs[1]])
	_expect(costs[1] < costs[0] * 0.8, "30 Hz costs clearly less per frame than 60 Hz")
	for rig: Dictionary in [fast, slow]:
		(rig.holder as Node).queue_free()
	await process_frame
