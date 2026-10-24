extends "res://tests/test_rust_mounted_pose.gd"
## Actual equipped content: legacy diagnostic, Rust pose/Script cloth, and
## Rust pose/native cloth. Strict cloth parity uses the same Rust body inputs;
## the separate pose fixture owns the approved legacy-vs-Rust pose tolerance.
var _cape_equipment: Dictionary = {}
var _combined_legacy_maximum: Dictionary = {}

class ObservedClothPose extends "res://src/mounts/rust_rider_pose.gd":
	var cloth_body_inputs: Array = []
	func mounted_constraint_backend() -> RefCounted:
		cloth_body_inputs.clear()
		var skeleton: Skeleton3D = _legacy.actor.get_skeleton()
		cloth_body_inputs.append(skeleton.global_transform)
		for bone: String in ["spine_03", "spine_01", "neck_01", "pelvis", "thigh_l", "calf_l", "thigh_r", "calf_r"]:
			cloth_body_inputs.append(skeleton.get_bone_global_pose(skeleton.find_bone(bone)))
		return super.mounted_constraint_backend()

class ScriptClothPose extends ObservedClothPose:
	func mounted_constraint_backend() -> RefCounted:
		super.mounted_constraint_backend()
		return null

class RejectingMountedKernel extends RefCounted:
	func step_mounted_cape(_points: Array, _previous: Array, _rests: Array,
			_lengths: Array, _world: PackedVector3Array, _pairs: Array,
			_axes: PackedVector3Array, _spans: PackedFloat64Array,
			_radii: PackedFloat64Array, _reaches: Array, _fall: Vector3,
			_damping: float, _forward: Vector3, _plane: float, _anchor: float,
			_frame: Transform3D, _settled: bool, _surface: PackedFloat64Array) -> bool:
		return false

func _fixture_visuals() -> Dictionary:
	return {2: 1, 5: 184}

func _fixture_equipment() -> Dictionary:
	if _cape_equipment.is_empty():
		_cape_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	return _cape_equipment

func _fixture_cloth_allowed() -> bool:
	return true

func _pair(body: String, scale: float, changed_rest: bool) -> void:
	if changed_rest:
		return # Separate base-pose fixture covers altered rest and second scale.
	var actors: Array[ReplicatedActor3D] = []
	for index: int in 3:
		var actor := _actor(body, 2800 + index, scale, false)
		if actor != null:
			actors.append(actor)
	if actors.size() != 3:
		await _retire(actors)
		return
	actors[0].get("_mount_visual").rust_pose.configure(actors[0].get("_mount_visual").pose, _mount_id, null, null, "legacy")
	for index: int in [1, 2]:
		var visual = actors[index].get("_mount_visual")
		visual.rust_pose.close()
		var observed: ObservedClothPose = ObservedClothPose.new() if index == 1 else ScriptClothPose.new()
		observed.configure(visual.pose, _mount_id, _controller)
		visual.rust_pose = observed
	_combined_legacy_maximum = {"_points": 0.0, "_previous": 0.0}
	for actor: ReplicatedActor3D in actors:
		actor.apply_render_quality(ActorRenderQuality.Quality.HIGH, false)
		expect(actor.wears_cape_cloth() and actor._cape_cloth != null and not actor._cape_cloth.active,
			"actual worn cape uses only the mounted manual pass")
	for gait: String in ["idle", "walk", "cruise", "burst", "cruise", "idle"]:
		for actor: ReplicatedActor3D in actors:
			actor.get("_mount_visual").state.gait = gait
			actor.play_action(&"idle" if gait == "idle" else &"run", true)
			actor._presentation_speed = 0.0 if gait == "idle" else 5.0
		for frame: int in 24:
			if frame == 8:
				for actor: ReplicatedActor3D in actors: actor.play_action(&"cast_aggressive", true)
			if frame == 16:
				for actor: ReplicatedActor3D in actors: actor._cape_cloth.call("reset")
			for actor: ReplicatedActor3D in actors:
				if gait != "idle": actor.global_position += Vector3(0.013, 0, -0.04)
				actor.get("_mount_visual")._step_visual(1.0 / 60.0)
			Shim.flush_pending()
			_assert_paired_cloth_inputs(actors, 1.0 / 60.0)
			_compare(actors[2], actors[1], "same Rust pose/equipped cloth " + body + " " + _mount_id + " " + gait)
			_compare_points(actors[2]._cape_cloth, actors[1]._cape_cloth, "same-input mounted point/history states")
			_record_combined_legacy_difference(actors[0]._cape_cloth, actors[1]._cape_cloth)
		var stats: Dictionary = actors[1]._cape_cloth.call("native_presentation_stats")
		expect(int(stats.get("mountedCalls", 0)) > 0 and int(stats.get("mountedFallbackCalls", -1)) == 0,
			"real equipped mounted kernel actually ran without fallback")
		var reference_stats: Dictionary = actors[2]._cape_cloth.call("native_presentation_stats")
		expect(int(reference_stats.mountedCalls) == 0 and int(reference_stats.mountedFallbackCalls) == 0,
			"same-Rust-pose reference runs current Script cloth without native/fallback")
		# A teleport/reset carries both histories before the exact same reseed.
		for actor: ReplicatedActor3D in actors:
			actor.global_position += Vector3(123, -4, 88)
			actor._cape_cloth.call("reset")
			actor.get("_mount_visual")._step_visual(1.0 / 30.0)
		Shim.flush_pending()
		_assert_paired_cloth_inputs(actors, 1.0 / 30.0)
		_compare_points(actors[2]._cape_cloth, actors[1]._cape_cloth, "teleport and explicit reseed")
		_record_combined_legacy_difference(actors[0]._cape_cloth, actors[1]._cape_cloth)
	var cloth = actors[1]._cape_cloth
	var points: Array = cloth.get("_points")
	var previous: Array = cloth.get("_previous")
	var points_before := points.duplicate(true)
	var previous_before := previous.duplicate(true)
	var invalid_surface: PackedFloat64Array = actors[1].get("_mount_visual").cape_surface.native_snapshot(1.0 / 60.0).duplicate()
	invalid_surface[0] = -1.0
	var invalid: bool = _controller.native.step_mounted_cape(points, previous, [], [], PackedVector3Array(), [],
		PackedVector3Array(), PackedFloat64Array(), PackedFloat64Array(), [], Vector3.ZERO, 0.3, Vector3.ZERO,
		0.0, 0.0, Transform3D.IDENTITY, true, invalid_surface)
	expect(not invalid and points == points_before and previous == previous_before,
		"invalid sampled surface cannot partially publish any point/history chain")
	var before: Dictionary = cloth.call("native_presentation_stats")
	for actor: ReplicatedActor3D in actors:
		actor.apply_render_quality(ActorRenderQuality.Quality.LOW, false)
		actor.get("_mount_visual")._step_visual(1.0 / 60.0)
	Shim.flush_pending()
	expect(int((cloth.call("native_presentation_stats") as Dictionary).mountedCalls) == int(before.mountedCalls),
		"remote Low does not execute mounted cloth")
	for actor: ReplicatedActor3D in actors:
		actor.apply_render_quality(ActorRenderQuality.Quality.HIGH, false)
		actor.get("_mount_visual")._step_visual(1.0 / 60.0)
	Shim.flush_pending()
	_assert_paired_cloth_inputs(actors, 1.0 / 60.0)
	_compare_points(actors[2]._cape_cloth, cloth, "quality re-enable resets the same point state")
	# A rejected native call must leave point state untouched until the legacy
	# wrapper performs exactly one replacement step. It stays legacy until remount.
	cloth.call("set_native_mounted_constraint_kernel", RejectingMountedKernel.new())
	actors[2]._cape_cloth.call("_process_modification_with_delta", 1.0 / 60.0)
	cloth.call("_process_modification_with_delta", 1.0 / 60.0)
	_compare_points(actors[2]._cape_cloth, cloth, "complete-component native rejection fallback")
	var rejected: Dictionary = cloth.call("native_presentation_stats")
	expect(int(rejected.mountedFallbackCalls) == 1, "one rejected native step records one fallback")
	cloth.call("set_native_mounted_constraint_kernel", _controller.native)
	expect(not bool((cloth.call("native_presentation_stats") as Dictionary).mountedBackendAvailable),
		"rejected native cloth is not retried every frame within the same mount lifetime")
	print("MOUNTED_CLOTH_COMBINED_LEGACY_DIAGNOSTIC ", JSON.stringify({"body": body, "mount": _mount_id,
		"maximumMetres": _combined_legacy_maximum, "scope": "combined independently-qualified pose and cloth paths; diagnostic only"}))
	await _retire(actors)

func _assert_paired_cloth_inputs(actors: Array[ReplicatedActor3D], step: float) -> void:
	var native_visual = actors[1].get("_mount_visual")
	var script_visual = actors[2].get("_mount_visual")
	expect(native_visual.rust_pose.cloth_body_inputs == script_visual.rust_pose.cloth_body_inputs,
		"native and Script cloth receive bit-identical Rust body/world transforms")
	expect(native_visual.cape_surface.native_snapshot(step) == script_visual.cape_surface.native_snapshot(step),
		"native and Script cloth receive bit-identical animated mount surface inputs")
	for key: String in ["_collision_world", "_collision_axes", "_collision_spans", "_collision_radii", "_collision_reaches"]:
		expect(actors[1]._cape_cloth.get(key) == actors[2]._cape_cloth.get(key), "same cloth input " + key)

func _record_combined_legacy_difference(legacy: SkeletonModifier3D, native: SkeletonModifier3D) -> void:
	for key: String in ["_points", "_previous"]:
		var left: Array = legacy.get(key)
		var right: Array = native.get(key)
		expect(left.size() == 3 and right.size() == 3, "combined diagnostic retains all three chains")
		if left.size() != 3 or right.size() != 3: return
		for chain: int in 3:
			var p: PackedVector3Array = left[chain]
			var q: PackedVector3Array = right[chain]
			expect(p.size() == 5 and q.size() == 5, "combined diagnostic retains complete chains")
			if p.size() != 5 or q.size() != 5: return
			for point: int in 5:
				_combined_legacy_maximum[key] = maxf(float(_combined_legacy_maximum[key]), p[point].distance_to(q[point]))

func _compare_points(a: SkeletonModifier3D, b: SkeletonModifier3D, label: String) -> void:
	for key: String in ["_points", "_previous"]:
		var left: Array = a.get(key)
		var right: Array = b.get(key)
		expect(left.size() == 3 and right.size() == 3, label + " all three chains exist")
		if left.size() != 3 or right.size() != 3: return
		var maximum := 0.0
		for chain: int in 3:
			var p: PackedVector3Array = left[chain]
			var q: PackedVector3Array = right[chain]
			expect(p.size() == 5 and q.size() == 5, label + " complete chain size")
			if p.size() != 5 or q.size() != 5: return
			for point: int in 5: maximum = maxf(maximum, p[point].distance_to(q[point]))
		expect(maximum < 0.0001, label + " " + key + " distance=" + str(maximum))
