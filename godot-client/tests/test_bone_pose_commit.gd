extends SceneTree
## Engine API parity for complete-transform vs separate TRS writes.
var checks := 0
var failures := 0
var pose_callbacks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	var rig := Skeleton3D.new()
	root.add_child(rig)
	rig.modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	for bone: int in 4:
		rig.add_bone("commit_%d" % bone)
		if bone > 0:
			rig.set_bone_parent(bone, bone - 1)
		rig.set_bone_rest(bone, Transform3D(Basis(Vector3.UP, 0.2 * bone), Vector3(0.2, 0.3, -0.1)))
	rig.force_update_all_bone_transforms()
	var callback := func() -> void: pose_callbacks += 1
	rig.pose_updated.connect(callback)
	var cases: Array = [
		[Vector3.ZERO, Quaternion.IDENTITY, Vector3.ONE],
		[Vector3(1.25, -2.5, 9.5), Quaternion(Vector3.UP, 1.7), Vector3(0.8, 1.1, 1.3)],
		[Vector3(-7.5, 0.3, 1.0), Quaternion(Vector3.RIGHT, PI), Vector3.ONE],
		[Vector3(0.01, 0.02, -0.03), Quaternion(Vector3(1.0, 2.0, 3.0).normalized(), 4.5), Vector3(-1.0, -1.0, -1.0)],
		[Vector3(7.0, -3.0, 0.4), Quaternion(Vector3.FORWARD, 0.0001), Vector3(1.4, 0.5, 2.2)],
		[Vector3(1, 2, 3), Quaternion(Vector3.UP, 0.7), Vector3(-1.0, 1.2, 0.8)],
		[Vector3(-1, 2, -3), Quaternion(Vector3.RIGHT, 0.3), Vector3(-1.0, -2.0, 0.7)]]
	for values: Array in cases:
		var position: Vector3 = values[0]
		var rotation: Quaternion = values[1]
		var scale: Vector3 = values[2]
		for bone: int in rig.get_bone_count():
			rig.set_bone_pose_position(bone, position)
			rig.set_bone_pose_rotation(bone, rotation)
			rig.set_bone_pose_scale(bone, scale)
		rig.force_update_all_bone_transforms()
		var expected_local: Array[Transform3D] = []
		var expected_global: Array[Transform3D] = []
		for bone: int in rig.get_bone_count():
			expected_local.append(rig.get_bone_pose(bone))
			expected_global.append(rig.get_bone_global_pose(bone))
		var before := pose_callbacks
		for bone: int in rig.get_bone_count():
			if scale.x > 0.0 and scale.y > 0.0 and scale.z > 0.0:
				rig.set_bone_pose(bone, Transform3D(Basis(rotation).scaled_local(scale), position))
			else:
				rig.set_bone_pose_position(bone, position)
				rig.set_bone_pose_rotation(bone, rotation)
				rig.set_bone_pose_scale(bone, scale)
		expect(pose_callbacks == before, "ordinary selected setter span defers update callbacks")
		rig.force_update_all_bone_transforms()
		expect(pose_callbacks > before, "explicit force is a real callback boundary")
		for bone: int in rig.get_bone_count():
			expect(expected_local[bone].is_equal_approx(rig.get_bone_pose(bone)), "selected setter span preserves composed local transform")
			expect(position.is_equal_approx(rig.get_bone_pose_position(bone)), "selected setter span preserves local position")
			expect(scale.is_equal_approx(rig.get_bone_pose_scale(bone)), "selected setter span preserves each local scale sign")
			var actual := rig.get_bone_pose_rotation(bone)
			var dot := absf(float(actual.x) * rotation.x + float(actual.y) * rotation.y + float(actual.z) * rotation.z + float(actual.w) * rotation.w)
			var denominator := sqrt(float(actual.length_squared()) * float(rotation.length_squared()))
			expect(denominator > 0.0 and dot / denominator > 0.999999, "selected setter span preserves local quaternion orientation")
			expect(expected_global[bone].is_equal_approx(rig.get_bone_global_pose(bone)), "complete setter preserves parent hierarchy")
	rig.pose_updated.disconnect(callback)
	rig.queue_free()
	await physics_frame
	await process_frame
	await process_frame
	print("BONE_POSE_COMMIT_CHECKS ", checks, " failures=", failures,
		" template=", OS.has_feature("template"), " engine=", Engine.get_version_info().hash)
	quit(1 if failures else 0)
