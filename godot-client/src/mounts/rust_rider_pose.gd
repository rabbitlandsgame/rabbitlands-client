extends RefCounted
## Optional Moor Pony solver. No authoritative actor field is owned here.
const Batch := preload("res://src/mounts/rust_rider_pose_batch.gd")
const RuntimeController := preload("res://src/runtime/client_runtime.gd")
const GAITS := {"idle": 0, "walk": 1, "trot": 2, "gallop": 3}
static var _next_generation := 1
static var _batch_ref: WeakRef

var _legacy
var _controller: WeakRef
var _app_ref: WeakRef
var _native
var _rig := 0
var _rider := 0
var _epoch := 0
var _generation := 0
var _frame := 0
var _disabled := false
var _supported := false
var _mode_override := ""
var _profile_id := ""
var comparisons := 0
var applications := 0
var failures := 0
var maximum_position_error := 0.0
var maximum_angle_error := 0.0
var maximum_scale_error := 0.0
var maximum_visual_error := 0.0

func configure(legacy: RefCounted, mount_id: String, controller_override: RefCounted = null,
		native_override: RefCounted = null, mode_override := "") -> void:
	close()
	_legacy = legacy
	_profile_id = mount_id
	var tree: SceneTree = _legacy.actor.get_tree() if is_instance_valid(_legacy.actor) else null
	var app: Node = tree.root.get_node_or_null("AppState") if tree != null else null
	_app_ref = weakref(app) if app != null else null
	_supported = mount_id == "moor_pony"
	_disabled = not _supported or _legacy.visual_root == null
	# Other profiles and gait-dependent pelvis adapters remain on the qualified path.
	_disabled = _disabled or _legacy.profile.has("normalPelvisLeanDegrees") or _legacy.profile.has("gallopPelvisLeanDegrees")
	var controller = controller_override if controller_override != null else RuntimeController.current()
	if controller != null:
		_controller = weakref(controller)
	_native = native_override
	_mode_override = mode_override
	if controller != null and controller.has_method("allocate_instance_generation"):
		_generation = int(controller.allocate_instance_generation())
	else:
		_generation = _next_generation
		_next_generation += 1

func _mode() -> String:
	if not _mode_override.is_empty():
		return _mode_override
	var controller = _controller.get_ref() if _controller != null else null
	if controller == null:
		return "legacy"
	if controller.wants_rust_pose():
		return "rust"
	return "compare" if controller.is_compare_mode() else "legacy"

func _current_epoch() -> int:
	var controller = _controller.get_ref() if _controller != null else null
	return int(controller.current_epoch()) if controller != null else 1

func _ensure_registered() -> bool:
	if _mode() == "legacy":
		close()
		_native = null
		return false
	if _disabled or not is_instance_valid(_legacy.actor) or not is_instance_valid(_legacy.skeleton):
		return false
	var controller = _controller.get_ref() if _controller != null else null
	if controller != null:
		_native = controller.native_runtime()
	if _native == null or not _native.has_method("solve_mounted_batch"):
		return false
	var epoch := _current_epoch()
	if _rider != 0 and epoch == _epoch:
		return true
	close()
	_epoch = epoch
	var skeleton: Skeleton3D = _legacy.skeleton
	var parents := PackedInt32Array()
	var rests := PackedFloat64Array()
	var poses := PackedFloat64Array()
	for bone: int in skeleton.get_bone_count():
		parents.append(skeleton.get_bone_parent(bone))
		_append_affine(rests, skeleton.get_bone_rest(bone))
		var pose: Transform3D = _legacy.neutral[bone]
		_append_vector(poses, pose.origin)
		_append_quaternion(poses, pose.basis.get_rotation_quaternion())
		_append_vector(poses, pose.basis.get_scale())
	_rig = int(_native.register_rig(parents, rests, poses))
	if _rig <= 0:
		_disabled = true
		return false
	var bones := PackedInt32Array([skeleton.find_bone("pelvis"), skeleton.find_bone("spine_01")])
	for side: String in ["l", "r"]:
		for stem: String in ["thigh", "calf", "foot", "upperarm", "lowerarm", "hand"]:
			bones.append(skeleton.find_bone(stem + "_" + side))
		for finger: String in ["index", "middle", "ring", "pinky"]:
			for joint: int in range(1, 4):
				bones.append(skeleton.find_bone("%s_%02d_%s" % [finger, joint, side]))
	var values := PackedFloat64Array()
	_append_vector(values, _legacy.baseline_pelvis)
	_append_affine(values, _legacy.visual_rest)
	_append_affine(values, _legacy.visual_root.global_transform.affine_inverse() * skeleton.global_transform)
	for side: String in ["l", "r"]:
		_append_basis(values, _legacy.end_bases["foot_" + side])
	for side: String in ["l", "r"]:
		_append_vector(values, _legacy.hand_directions[side])
	for side: String in ["l", "r"]:
		_append_vector(values, _legacy.palm_normals[side])
	for side: String in ["l", "r"]:
		for finger: String in ["index", "middle", "ring", "pinky"]:
			_append_vector(values, _legacy.curl_axes[finger + "_" + side])
	var profile: Dictionary = _legacy.profile
	values.append(float(profile.get("pelvisLeanDegrees", 3.0)))
	values.append(float(profile.get("torsoStabilization", 0.55)))
	values.append(float(profile.get("fingerGripWeight", 0.7)))
	for angle: Variant in profile.fingerCurlDegrees:
		values.append(float(angle))
	values.append(float(profile.get("footToeOutDegrees", 8.0)))
	for key: String in ["handOffsetMetres", "elbowPoleOffsetMetres", "footOffsetMetres", "kneePoleOffsetMetres"]:
		for value: Variant in profile[key]:
			values.append(float(value))
	var motion: Dictionary = profile.get("armMotion", {})
	values.append(float(motion.get("weight", 1.0)))
	for gait: String in ["idle", "walk", "trot", "gallop"]:
		var tuning: Dictionary = motion.get(gait, {})
		values.append(float(tuning.get("handFollowMetres", 0.0)))
		values.append(float(tuning.get("elbowGiveMetres", 0.0)))
		values.append(float(tuning.get("beatsPerCycle", 1.0)))
	var thumbs := PackedInt32Array()
	var grips := PackedFloat64Array()
	for finger: Array in _legacy.finger_grips:
		if skeleton.get_bone_name(int(finger[0])).begins_with("thumb_"):
			thumbs.append(int(finger[0]))
			_append_quaternion(grips, finger[1])
	_rider = int(_native.register_mounted_rider(_rig, bones, values, thumbs, grips))
	var owner = _legacy.actor.get("_mount_visual")
	if _rider <= 0 or owner == null or not _native.bind_mounted_rider(_rider, skeleton, _legacy.visual_root, owner, _legacy.actor.actor_id, _generation):
		close()
		_disabled = true
		return false
	return true

## True means this call owns fit + finish, including synchronous compare.
func try_fit(seat: Transform3D, gait: String, seconds: float, cycle: float, finish: Callable) -> bool:
	if not GAITS.has(gait) or not _ensure_registered():
		return false
	_frame += 1
	if _mode() == "compare":
		var records := record(gait)
		var samples := sample(seat, seconds, cycle)
		var ok: bool = _native.solve_mounted_batch(records, samples, _epoch, false)
		_legacy.fit(seat, gait, seconds, cycle)
		if ok:
			var metadata: PackedInt64Array = _native.mounted_pose_metadata()
			var values: PackedFloat64Array = _native.mounted_pose_values()
			if metadata.size() == 6:
				compare_output(values, int(metadata[4]))
		else:
			failures += 1
		finish.call()
		return true
	var batch = _batch_ref.get_ref() if _batch_ref != null else null
	if batch == null:
		batch = Batch.new()
		_legacy.actor.get_tree().root.add_child(batch)
		_batch_ref = weakref(batch)
	batch.submit(self, seat, gait, seconds, cycle, finish)
	return true

func record(gait: String) -> PackedInt64Array:
	return PackedInt64Array([_legacy.actor.actor_id, _generation, _rider, int(GAITS[gait]), _frame])

func sample(seat: Transform3D, seconds: float, cycle: float) -> PackedFloat64Array:
	var values := PackedFloat64Array()
	_append_affine(values, seat)
	values.append(seconds)
	values.append(cycle)
	return values

func snapshot() -> Dictionary:
	return {"requested": _mode(), "registered": _rider > 0, "disabled": _disabled, "supported": _supported,
		"profile": _profile_id,
		"epoch": _epoch, "generation": _generation, "comparisons": comparisons,
		"applications": applications, "failures": failures, "maxPositionError": maximum_position_error,
		"maxAngleError": maximum_angle_error, "maxScaleError": maximum_scale_error,
		"maxVisualError": maximum_visual_error}

## On demand only; no per-frame diagnostic dictionary or complete pose copy.
func contact_errors() -> PackedFloat64Array:
	if _native == null or _rider <= 0:
		return PackedFloat64Array()
	return _native.mounted_contact_errors(_legacy.actor.actor_id, _generation, _frame)

func still_valid(epoch: int) -> bool:
	if _disabled or _rider <= 0 or _native == null or _mode() != "rust" or _epoch != epoch or _current_epoch() != epoch:
		return false
	if not is_instance_valid(_legacy.actor) or not is_instance_valid(_legacy.skeleton) or not is_instance_valid(_legacy.visual_root):
		return false
	var controller = _controller.get_ref() if _controller != null else null
	if controller != null and controller.native_runtime() != _native:
		return false
	if not _legacy.actor.is_inside_tree() or _legacy.actor.is_queued_for_deletion() or _legacy.skeleton.is_queued_for_deletion() or _legacy.visual_root.is_queued_for_deletion():
		return false
	if not _legacy.visual_root.is_ancestor_of(_legacy.skeleton):
		return false
	var mount = _legacy.actor.get("_mount_visual")
	return mount != null and not bool(mount.get("_parked"))

func frame_identity() -> Array:
	# A continuous map handoff retains both actor and rig, and does not reset
	# the session epoch. Reject a prepared seat from its previous coordinate frame.
	var app: Variant = _app_ref.get_ref() if _app_ref != null else null
	var map_id := str(app.get("current_map")) if is_instance_valid(app) else ""
	return [_legacy.actor.get_instance_id(), _legacy.actor.global_transform,
		_legacy.visual_root.transform, map_id]

func matches_frame_identity(identity: Array) -> bool:
	return identity == frame_identity()

func fallback_fit(seat: Transform3D, gait: String, seconds: float, cycle: float) -> void:
	failures += 1
	_legacy.fit(seat, gait, seconds, cycle)
	close()
	_native = null
	# A failed complete batch is not retried every frame; remount/reconfigure
	# is the explicit new lifetime boundary for this pilot.
	_disabled = true

func compare_output(values: PackedFloat64Array, offset: int) -> void:
	var skeleton: Skeleton3D = _legacy.skeleton
	if offset < 0 or values.size() < offset + 17 + skeleton.get_bone_count() * 10:
		failures += 1
		return
	comparisons += 1
	var expected_visual := _read_affine(values, offset)
	maximum_visual_error = maxf(maximum_visual_error, expected_visual.origin.distance_to(_legacy.visual_root.global_position))
	maximum_visual_error = maxf(maximum_visual_error, expected_visual.basis.x.distance_to(_legacy.visual_root.global_basis.x))
	maximum_visual_error = maxf(maximum_visual_error, expected_visual.basis.y.distance_to(_legacy.visual_root.global_basis.y))
	maximum_visual_error = maxf(maximum_visual_error, expected_visual.basis.z.distance_to(_legacy.visual_root.global_basis.z))
	for bone: int in skeleton.get_bone_count():
		var at := offset + 12 + bone * 10
		var position := Vector3(values[at], values[at + 1], values[at + 2])
		var rotation := Quaternion(values[at + 3], values[at + 4], values[at + 5], values[at + 6])
		var scale := Vector3(values[at + 7], values[at + 8], values[at + 9])
		maximum_position_error = maxf(maximum_position_error, position.distance_to(skeleton.get_bone_pose_position(bone)))
		maximum_angle_error = maxf(maximum_angle_error, rotation_error(rotation, skeleton.get_bone_pose_rotation(bone)))
		maximum_scale_error = maxf(maximum_scale_error, scale.distance_to(skeleton.get_bone_pose_scale(bone)))

func close() -> void:
	if _native != null:
		if _rider > 0:
			_native.unregister_mounted_rider(_rider)
		if _rig > 0:
			_native.unregister_rig(_rig)
	_rider = 0
	_rig = 0

static func close_batches() -> void:
	var batch = _batch_ref.get_ref() if _batch_ref != null else null
	if batch != null:
		batch.close()
	_batch_ref = null

static func batch_snapshot() -> Dictionary:
	var batch: Variant = _batch_ref.get_ref() if _batch_ref != null else null
	return batch.diagnostic_snapshot() if batch != null else {"present": false, "batches": 0, "poses": 0, "fallbacks": 0}

## Explicit fixture-only frame boundary for tests which call mount._process.
static func flush_pending() -> void:
	var batch = _batch_ref.get_ref() if _batch_ref != null else null
	if batch != null:
		batch.flush()

## Use f64 normalization before acos. Engine real_t quaternion dot products can
## give a nonzero angle even for the same slightly non-unit stored rotation.
static func rotation_error(a: Quaternion, b: Quaternion) -> float:
	var aa: float = float(a.x) * float(a.x) + float(a.y) * float(a.y) + float(a.z) * float(a.z) + float(a.w) * float(a.w)
	var bb: float = float(b.x) * float(b.x) + float(b.y) * float(b.y) + float(b.z) * float(b.z) + float(b.w) * float(b.w)
	if aa < 0.000000000001 or bb < 0.000000000001:
		return INF
	var dot: float = float(a.x) * float(b.x) + float(a.y) * float(b.y) + float(a.z) * float(b.z) + float(a.w) * float(b.w)
	return 2.0 * acos(clampf(absf(dot / sqrt(aa * bb)), 0.0, 1.0))

static func _append_vector(values: PackedFloat64Array, vector: Vector3) -> void:
	values.append(vector.x)
	values.append(vector.y)
	values.append(vector.z)

static func _append_quaternion(values: PackedFloat64Array, rotation: Quaternion) -> void:
	values.append(rotation.x)
	values.append(rotation.y)
	values.append(rotation.z)
	values.append(rotation.w)

static func _append_basis(values: PackedFloat64Array, basis: Basis) -> void:
	_append_vector(values, basis.x)
	_append_vector(values, basis.y)
	_append_vector(values, basis.z)

static func _append_affine(values: PackedFloat64Array, frame: Transform3D) -> void:
	_append_basis(values, frame.basis)
	_append_vector(values, frame.origin)

static func _read_affine(values: PackedFloat64Array, offset: int) -> Transform3D:
	return Transform3D(Basis(Vector3(values[offset], values[offset + 1], values[offset + 2]), Vector3(values[offset + 3], values[offset + 4], values[offset + 5]), Vector3(values[offset + 6], values[offset + 7], values[offset + 8])), Vector3(values[offset + 9], values[offset + 10], values[offset + 11]))
