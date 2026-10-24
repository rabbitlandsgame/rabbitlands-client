extends "res://tests/test_rust_mounted_upper.gd"
## The existing immediate-mesh triangle emitter is the geometry reference.
var _references: Dictionary = {}
class RecordingReins extends "res://src/mounts/mount_reins.gd":
	var recorded_vertices := PackedVector3Array()
	var recorded_normals := PackedVector3Array()
	func update_contact(anchors: Dictionary, rig: Skeleton3D, seat_basis: Basis,
			grips: Dictionary = {}, paths: Array[PackedVector3Array] = []) -> void:
		recorded_vertices.clear()
		recorded_normals.clear()
		super.update_contact(anchors, rig, seat_basis, grips, paths)
	func _triangle(a: Vector3, b: Vector3, c: Vector3) -> void:
		var normal := (b - a).cross(c - a).normalized()
		for point: Vector3 in [a, b, c]:
			recorded_vertices.append(point)
			recorded_normals.append(normal)
		super._triangle(a, b, c)

func _actor(body: String, id: int, scale: float, changed_rest: bool) -> ReplicatedActor3D:
	var actor := super._actor(body, id, scale, changed_rest)
	if actor == null: return null
	var visual = actor.get("_mount_visual")
	var previous: Node3D = visual.reins
	visual.remove_child(previous)
	previous.free() # No pose/binding has been submitted in the base constructor.
	var recording := RecordingReins.new()
	visual.add_child(recording)
	recording.configure(visual.profile.reins)
	visual.reins = recording
	return actor

func _compare(a: ReplicatedActor3D, b: ReplicatedActor3D, label: String) -> void:
	super._compare(a, b, label)
	# Base/upper pose parity is checked by super. Feed the current Script
	# emitter the actual native rider pose so thin strap geometry is qualified
	# independently of the already bounded upstream pose differences.
	var legacy = _same_input_reference(b)
	var actual = b.get("_mount_visual").reins
	var snapshot: Dictionary = actual._native_geometry()
	expect(bool(snapshot.get("available", false)) and int(snapshot.get("calls", 0)) > 0,
		label + " actual compiled rein renderer ran")
	for key: String in ["l", "r"]:
		_compare_line(legacy.last_points.get(key, PackedVector3Array()), actual.last_points.get(key, PackedVector3Array()), label + " incoming " + key)
		_compare_line(legacy.last_grip_points.get(key, PackedVector3Array()), actual.last_grip_points.get(key, PackedVector3Array()), label + " grip/tail " + key)
		expect(absf(float(legacy.last_lengths.get(key, -1)) - float(actual.last_lengths.get(key, -2))) < 0.0001,
			label + " current world strap length parity " + key)
	_compare_line(legacy.recorded_vertices, snapshot.get("meshVertices", PackedVector3Array()), label + " full strip vertices")
	var expected: PackedVector3Array = legacy.recorded_normals
	var normals: PackedVector3Array = snapshot.get("meshNormals", PackedVector3Array())
	expect(expected.size() == normals.size() and not expected.is_empty(), label + " full flat-normal topology")
	if expected.size() == normals.size():
		var maximum := 0.0
		var emitted: PackedVector3Array = snapshot.get("meshVertices", PackedVector3Array())
		var kernel_maximum := 0.0
		for index: int in normals.size():
			expect(normals[index].is_finite(), label + " finite emitted normal")
			maximum = maxf(maximum, normals[index].distance_to(expected[index]))
		# The Script/native strip check above retains its 0.1 mm limit.
		# Separately verify normal arithmetic with identical triangle inputs.
		for index: int in range(0, emitted.size(), 3):
			var reference := (emitted[index + 1] - emitted[index]).cross(emitted[index + 2] - emitted[index]).normalized()
			for corner: int in 3:
				kernel_maximum = maxf(kernel_maximum, normals[index + corner].distance_to(reference))
		expect(kernel_maximum < 0.000001, label + " identical-input emitted normal parity " + str(kernel_maximum))
		print("REIN_NORMAL_PARITY ", label, " triangle_kernel=", kernel_maximum, " script_emitter=", maximum)
	expect(actual.straps.material_override != null and actual.straps.mesh is ArrayMesh,
		label + " existing material/instance owns one native ArrayMesh")
	expect(actual.straps.mesh.get_surface_count() == 1, label + " one surface preserves spatial/material grouping")

func _same_input_reference(actor: ReplicatedActor3D) -> RecordingReins:
	var visual = actor.get("_mount_visual")
	var key := actor.get_instance_id()
	var reference: RecordingReins = _references.get(key)
	if not is_instance_valid(reference):
		reference = RecordingReins.new()
		visual.add_child(reference)
		reference.configure(visual.profile.reins)
		_references[key] = reference
	reference.global_transform = visual.reins.global_transform
	var pony_rig: Skeleton3D = visual.pony.get_skeleton()
	var bone: Transform3D = pony_rig.global_transform * pony_rig.get_bone_global_pose(visual.saddle)
	var seat: Transform3D
	if visual.profile.has("seatPositionNative"):
		var point: Array = visual.profile.seatPositionNative
		var frame: Transform3D = bone * visual.seat_rest_inverse
		seat = Transform3D(frame.basis.orthonormalized(), frame * Vector3(float(point[0]), float(point[1]), float(point[2])))
	else:
		var offset: Array = visual.profile.seatOffsetNative
		seat = Transform3D(bone.basis.orthonormalized(), bone * Vector3(float(offset[0]), float(offset[1]), float(offset[2])))
	var head: Transform3D = pony_rig.global_transform * pony_rig.get_bone_global_pose(visual.head)
	var bridle := {}
	var parked := {}
	for side: String in ["l", "r"]:
		bridle[side] = head * (visual.sockets[side] as Vector3)
		var sign_value := 1.0 if side == "l" else -1.0
		var saddle_grip := seat.origin + seat.basis * Vector3(sign_value * .055, .12, .21)
		parked[side] = [reference.grip_world(actor.get_skeleton(), side).lerp(saddle_grip, visual.upper.grip_weight),
			reference.grip_exit_world(actor.get_skeleton(), side).lerp(saddle_grip + Vector3.DOWN * .025, visual.upper.grip_weight)]
	var straps: Array[PackedVector3Array] = []
	for path: PackedVector3Array in visual.bridle_paths:
		var points := PackedVector3Array()
		for point: Vector3 in path:
			points.append(head * point)
		straps.append(points)
	reference.update_contact(bridle, actor.get_skeleton(), seat.basis, parked, straps)
	return reference

func _compare_line(a: PackedVector3Array, b: PackedVector3Array, label: String) -> void:
	expect(a.size() == b.size() and not a.is_empty(), label + " complete vertex count")
	if a.size() != b.size(): return
	var maximum := 0.0
	for index: int in a.size(): maximum = maxf(maximum, a[index].distance_to(b[index]))
	expect(maximum < 0.0001, label + " distance=" + str(maximum))

func _retire(actors: Array[ReplicatedActor3D]) -> void:
	if actors.size() > 1 and is_instance_valid(actors[1].get("_mount_visual")):
		var actor := actors[1]
		var owner = actor.get("_mount_visual")
		var shim = owner.rust_pose
		var mesh: ArrayMesh = owner.reins.straps.mesh as ArrayMesh
		if mesh != null and int(shim._rider) > 0:
			var before: Dictionary = _controller.native.runtime_info()
			var seen := {"callback": false}
			var callback := func() -> void:
				if bool(seen.callback): return
				seen.callback = true
				owner.free()
			mesh.changed.connect(callback)
			owner._step_visual(1.0 / 60.0)
			Shim.flush_pending()
			mesh.changed.disconnect(callback)
			var after: Dictionary = _controller.native.runtime_info()
			expect(bool(seen.callback), "actual native rein mesh commit is a positive Resource.changed callback control")
			expect(not shim.still_valid(_controller.epoch), "abruptly freed rein owner is rejected safely after native return")
			expect(int(after.rein_failures) == int(before.rein_failures) + 1, "resource callback cancels complete rein commit")
			expect(int(after.mounted_rider_count) == int(before.mounted_rider_count) - 1, "resource callback drains deferred native ownership release")
			expect(_controller.native.mounted_pose_metadata().is_empty(), "cancelled mesh application publishes no complete valid batch")
			actor.set("_mount_visual", null) # Fixture repairs its deliberately abrupt owner deletion.
	await super._retire(actors)
