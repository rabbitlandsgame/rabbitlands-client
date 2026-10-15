extends "res://tests/test_cape_cloth_pose_cache.gd"
## Runs the complete cape parity/performance sequence with the optional native
## point solver active, against the immediately preceding GDScript solver.

const CAPSULE_CACHE_BASELINE := \
	"res://tests/fixtures/cape_cloth_capsule_cache_baseline.gd"
const CAPSULE_CACHE_BASELINE_BODY_SHA256 := \
	"76da42459b01cdf535ee37d39dca2f34a26f6d6aebcd5c53408e080fd17e9e30"


class RejectingKernel extends RefCounted:
	func step(_points: Array, _previous: Array, _rests: Array,
			_lengths: Array, _collision_world: PackedVector3Array,
			_collision_pairs: Array, _collision_axes: PackedVector3Array,
			_collision_spans: PackedFloat64Array,
			_collision_radii: PackedFloat64Array, _collision_reaches: Array,
			_fall: Vector3, _damping: float, _forward: Vector3,
			_plane_at: float, _anchor_y: float, _to_world: Transform3D,
			_settled: bool) -> bool:
		return false


func _baseline_path() -> String:
	return CAPSULE_CACHE_BASELINE


func _baseline_body_sha256() -> String:
	return CAPSULE_CACHE_BASELINE_BODY_SHA256


func _comparison_label() -> String:
	return "capsule-cache GDScript solver vs native constraint kernel"


func _check_rig_ownership(skeleton: Skeleton3D) -> void:
	super._check_rig_ownership(skeleton)
	var cloth: SkeletonModifier3D = skeleton.get_node("CapeCloth")
	cloth.call("_initialize_native_constraint_kernel")
	_check(bool(cloth.call("native_constraint_kernel_active")),
		"native constraint kernel is actually active")
	_check_invalid_call_is_atomic()
	_check_wrapper_fallback_parity()


func _step_pair(optimized_skeleton: Skeleton3D,
		baseline_skeleton: Skeleton3D,
		optimized_cloth: SkeletonModifier3D,
		baseline_cloth: SkeletonModifier3D,
		delta: float, label: String) -> void:
	super._step_pair(optimized_skeleton, baseline_skeleton,
		optimized_cloth, baseline_cloth, delta, label)
	var stats: Dictionary = optimized_cloth.call("native_presentation_stats")
	_check(bool(stats.get("active", false)), label + " native backend is active")
	_check(str(stats.get("backend", "")) == "native",
		label + " reports the native backend")
	_check(int(stats.get("nativeCalls", 0)) > 0,
		label + " records a successful native call")
	_check(int(stats.get("fallbackCalls", -1)) == 0,
		label + " does not fall back")


func _check_invalid_call_is_atomic() -> void:
	var kernel: RefCounted = ClassDB.instantiate(&"NativeCapeConstraintKernel")
	_check(kernel != null, "native constraint kernel instantiates directly")
	if kernel == null:
		return
	var points: Array = [
		PackedVector3Array([Vector3(1.0, 2.0, 3.0)]),
		PackedVector3Array([Vector3(4.0, 5.0, 6.0)]),
		PackedVector3Array([Vector3(7.0, 8.0, 9.0)]),
	]
	var before: Array = points.duplicate(true)
	var previous: Array = [
		PackedVector3Array([Vector3(-1.0, -2.0, -3.0)]),
		PackedVector3Array([Vector3(-4.0, -5.0, -6.0)]),
		PackedVector3Array([Vector3(-7.0, -8.0, -9.0)]),
	]
	var previous_before: Array = previous.duplicate(true)
	# Only two rest chains makes the call invalid before any point state can
	# be committed, even though unsettled valid input would reset all chains.
	var malformed_rests: Array = [PackedVector3Array(), PackedVector3Array()]
	var lengths: Array = [PackedFloat32Array(), PackedFloat32Array(),
		PackedFloat32Array()]
	var solved := bool(kernel.call("step", points, previous, malformed_rests,
		lengths, PackedVector3Array(), [], PackedVector3Array(),
		PackedFloat64Array(), PackedFloat64Array(), [], Vector3.ZERO, 0.72,
		Vector3.ZERO, 0.0, 0.0, Transform3D.IDENTITY, false))
	_check(not solved, "native constraint kernel rejects malformed input")
	_compare_nested_points(points, before,
		"rejected native constraint call keeps point state atomic")
	_compare_nested_points(previous, previous_before,
		"rejected native constraint call keeps previous state atomic")

	var rest := PackedVector3Array([
		Vector3.ZERO, Vector3.DOWN, Vector3.DOWN * 2.0,
		Vector3.DOWN * 3.0, Vector3.DOWN * 4.0])
	var valid_rests: Array = [rest, rest, rest]
	var valid_lengths: Array = [
		PackedFloat32Array([1.0, 1.0, 1.0, 1.0]),
		PackedFloat32Array([1.0, 1.0, 1.0, 1.0]),
		PackedFloat32Array([1.0, 1.0, 1.0, 1.0]),
	]
	var read_only_points: Array = points.duplicate(true)
	var read_only_before: Array = read_only_points.duplicate(true)
	read_only_points.make_read_only()
	solved = bool(kernel.call("step", read_only_points, previous, valid_rests,
		valid_lengths, PackedVector3Array(), [], PackedVector3Array(),
		PackedFloat64Array(), PackedFloat64Array(), [], Vector3.ZERO, 0.72,
		Vector3.ZERO, 0.0, 0.0, Transform3D.IDENTITY, false))
	_check(not solved, "native constraint kernel rejects read-only output state")
	_compare_nested_points(read_only_points, read_only_before,
		"read-only native constraint rejection keeps point state atomic")


func _check_wrapper_fallback_parity() -> void:
	var optimized_skeleton := _minimal_skeleton()
	var baseline_skeleton := _minimal_skeleton()
	root.add_child(optimized_skeleton)
	root.add_child(baseline_skeleton)
	var optimized: SkeletonModifier3D = (load(
		"res://src/actors/cape_cloth.gd") as Script).new()
	var baseline: SkeletonModifier3D = (load(_baseline_path()) as Script).new()
	optimized_skeleton.add_child(optimized)
	baseline_skeleton.add_child(baseline)
	optimized.active = false
	baseline.active = false
	optimized.set("_native_constraint_kernel", RejectingKernel.new())
	optimized.set("_native_constraint_kernel_initialized", true)
	optimized.set("_native_constraint_status", "test_rejecting")
	super._step_pair(optimized_skeleton, baseline_skeleton,
		optimized, baseline, STEP, "native rejection wrapper fallback")
	var stats: Dictionary = optimized.call("native_presentation_stats")
	_check(int(stats.get("nativeCalls", -1)) == 0,
		"rejected wrapper records no native success")
	_check(int(stats.get("fallbackCalls", 0)) == 1,
		"rejected wrapper records one GDScript fallback")
	optimized_skeleton.queue_free()
	baseline_skeleton.queue_free()
