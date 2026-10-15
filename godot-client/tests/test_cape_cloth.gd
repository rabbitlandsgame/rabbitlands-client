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

var failures := 0


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
	var packed := load(RIG) as PackedScene
	if packed == null:
		push_error("cape cloth: cannot load " + RIG)
		quit(1)
		return
	var actor := packed.instantiate()
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

	print("cape cloth tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures > 0 else 0)
