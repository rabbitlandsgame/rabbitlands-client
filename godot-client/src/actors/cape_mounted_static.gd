extends RefCounted
## A held mounted fit for actors whose quality budget disables simulation.
## The caller performs a bounded warm fit, then capture validates the result.
## Applying the held pose never advances particles or projects contacts.
const Data := preload("res://src/actors/cape_approved_data.gd")
const COUNT := 12
const MOUNT_FIT_MARGIN_M := .04
const BODY_FIT_MARGIN_M := 0.0
const CARRY := [1.0, 1.0, .95, .85]
const MAX_GAP_M := .006
const MAX_STRAIN := 1.8

var _context: Variant
var _has_context := false
var _dirty := true
var _has_pose := false
var _actor_id := 0
var _skeleton_id := 0
var _spine := -1
var _bones := PackedInt32Array()
var _parents := PackedInt32Array()
var _parent_controls := PackedInt32Array()
var _local_poses: Array[Transform3D] = []
var _actor_poses: Array[Transform3D] = []
var _captured_spine := Transform3D.IDENTITY
var _capture_count := 0
var _apply_count := 0
var _fit_attempts := 0
var _fit_rejections := 0
var _last_fit_gap := 0.0
var _last_fit_strain := 1.0
var _last_fit_error := ""
var _rendered_updates := 0

## The stable key must include mount, fit/profile, equipment revision, gait,
## requested and actual upper action, and upper return state. Do not include
## an advancing clip clock. A changed key invalidates its context certificate;
## the last accepted palette remains available while a replacement is fitted.
## Updating this key is safe while hidden; capture/apply defer until visible.
func request_context(key: Variant) -> bool:
	if not _has_context or key != _context:
		_context = key.duplicate(true) if key is Dictionary or key is Array else key
		_has_context = true
		_dirty = true
	# Upper-body entry and return change the anatomical root frames. Refit
	# through those short blends instead of freezing the lower panel early.
	if key is Dictionary and not str(key.get("upper", "")).is_empty() \
			and (not bool(key.get("blend_settled", true)) or bool(key.get("returning", false))):
		_dirty = true
	return needs_capture()

func needs_capture() -> bool:
	return _dirty or not _has_pose

func has_pose() -> bool:
	return _has_pose

func clear() -> void:
	_context = null
	_has_context = false
	_dirty = true
	_has_pose = false
	_actor_id = 0
	_skeleton_id = 0
	_spine = -1
	_bones = PackedInt32Array()
	_parents = PackedInt32Array()
	_parent_controls = PackedInt32Array()
	_local_poses.clear()
	_actor_poses.clear()
	_captured_spine = Transform3D.IDENTITY
	_capture_count = 0
	_apply_count = 0
	_fit_attempts = 0
	_fit_rejections = 0
	_last_fit_gap = 0.0
	_last_fit_strain = 1.0
	_last_fit_error = ""
	_rendered_updates = 0

func _visible(actor: Node3D, skeleton: Skeleton3D) -> bool:
	return is_instance_valid(actor) and is_instance_valid(skeleton) \
		and actor.is_visible_in_tree() and skeleton.is_visible_in_tree() \
		and (not actor.has_method("is_drawn") or bool(actor.call("is_drawn")))

func _valid(pose: Transform3D) -> bool:
	return pose.origin.is_finite() and pose.basis.x.is_finite() \
		and pose.basis.y.is_finite() and pose.basis.z.is_finite() \
		and absf(pose.basis.determinant()) > .00000001

func _bind(actor: Node3D, skeleton: Skeleton3D) -> bool:
	if actor.get_instance_id() == _actor_id and skeleton.get_instance_id() == _skeleton_id:
		return _bones.size() == COUNT
	_has_pose = false
	_dirty = true
	if not Data.compatible(skeleton):
		return false
	var names := Data.bone_names()
	var bones := PackedInt32Array()
	var parents := PackedInt32Array()
	var parent_controls := PackedInt32Array()
	for i: int in COUNT:
		var bone := skeleton.find_bone(names[i])
		var parent := skeleton.get_bone_parent(bone)
		var rest := skeleton.get_bone_rest(bone)
		if not _valid(rest):
			return false
		bones.append(bone)
		parents.append(parent)
	for i: int in COUNT:
		var parent_control := bones.find(parents[i])
		if parent_control >= i:
			return false
		parent_controls.append(parent_control)
	_actor_id = actor.get_instance_id()
	_skeleton_id = skeleton.get_instance_id()
	_spine = skeleton.find_bone("spine_03")
	_bones = bones
	_parents = parents
	_parent_controls = parent_controls
	return _spine >= 0

## Call after the current body pose and a bounded fit. The caller temporarily
## uses MOUNT_FIT_MARGIN_M extra mount clearance and BODY_FIT_MARGIN_M extra
## body clearance for that fit, restoring ordinary settings afterward.
func capture(actor: Node3D, skeleton: Skeleton3D, fitness: Dictionary,
		keep_dirty := false) -> bool:
	_fit_attempts += 1
	_last_fit_gap = float(fitness.get("gap_m", INF))
	_last_fit_strain = float(fitness.get("strain", INF))
	_last_fit_error = ""
	if not bool(fitness.get("finite", false)) or not is_finite(_last_fit_gap) \
			or not is_finite(_last_fit_strain):
		_last_fit_error = "nonfinite"
	elif _last_fit_gap > MAX_GAP_M or _last_fit_strain > MAX_STRAIN:
		_last_fit_error = "constraints"
	if not _last_fit_error.is_empty():
		_fit_rejections += 1
		_dirty = true
		return false
	if not _store_pose(actor, skeleton, keep_dirty):
		return false
	_capture_count += 1
	return true

## Remember only an accepted full-quality palette. This is a cheap read of
## twelve transforms, not another static fit or a change to its fit budget.
func remember_rendered(actor: Node3D, skeleton: Skeleton3D, fitness: Dictionary) -> bool:
	var gap := float(fitness.get("gap_m", INF))
	var strain := float(fitness.get("strain", INF))
	if not bool(fitness.get("finite", false)) or not is_finite(gap) or not is_finite(strain) \
			or gap > MAX_GAP_M or strain > MAX_STRAIN:
		return false
	if not _store_pose(actor, skeleton, true):
		return false
	_has_context = false
	_rendered_updates += 1
	return true

func invalidate_context() -> void:
	_has_context = false
	_dirty = true

func _store_pose(actor: Node3D, skeleton: Skeleton3D, keep_dirty: bool) -> bool:
	if not _visible(actor, skeleton) or not _bind(actor, skeleton):
		return false
	var actor_world := actor.global_transform
	var skeleton_world := skeleton.global_transform
	if not _valid(actor_world) or not _valid(skeleton_world):
		return false
	var to_actor := actor_world.affine_inverse() * skeleton_world
	var spine := to_actor * skeleton.get_bone_global_pose(_spine)
	if not _valid(spine):
		return false
	var locals: Array[Transform3D] = []
	var globals: Array[Transform3D] = []
	for bone: int in _bones:
		var local := skeleton.get_bone_pose(bone)
		var global_pose := to_actor * skeleton.get_bone_global_pose(bone)
		if not _valid(local) or not _valid(global_pose):
			return false
		locals.append(local)
		globals.append(global_pose)
	_local_poses = locals
	_actor_poses = globals
	_captured_spine = spine
	_has_pose = true
	_dirty = keep_dirty
	return true

## Root overrides are the three current desired cape-root bone transforms
## in Skeleton3D bone-global coordinates, in left/centre/right order. They
## may follow a Spine/Neck support blend independently of the held lower9.
## Without overrides each root retains its captured local pose. Lower poses
## always convert through the desired parent, so changing a root cannot
## accidentally carry or tear the lower panel a second time.
func apply(actor: Node3D, skeleton: Skeleton3D, root_global_overrides: Array = []) -> bool:
	# A dirty context requests a replacement, but the previous accepted pose
	# stays available if the candidate cannot satisfy its constraints.
	if not _visible(actor, skeleton) or not _has_pose:
		return false
	if actor.get_instance_id() != _actor_id or skeleton.get_instance_id() != _skeleton_id:
		_dirty = true
		return false
	if not root_global_overrides.is_empty() and root_global_overrides.size() != 3:
		return false
	for value: Variant in root_global_overrides:
		if not value is Transform3D or not _valid(value):
			return false
	var actor_world := actor.global_transform
	var skeleton_world := skeleton.global_transform
	if not _valid(actor_world) or not _valid(skeleton_world):
		return false
	var to_actor := actor_world.affine_inverse() * skeleton_world
	var to_skeleton := to_actor.affine_inverse()
	var current_spine := to_actor * skeleton.get_bone_global_pose(_spine)
	if not _valid(current_spine):
		return false
	var carry := current_spine * _captured_spine.affine_inverse()
	var globals: Array[Transform3D] = []
	var locals: Array[Transform3D] = []
	for i: int in COUNT:
		var parent := Transform3D.IDENTITY
		if _parent_controls[i] >= 0:
			parent = globals[_parent_controls[i]]
		elif _parents[i] >= 0:
			parent = skeleton.get_bone_global_pose(_parents[i])
		var global_pose: Transform3D
		var local: Transform3D
		if i % 4 == 0:
			if root_global_overrides.is_empty():
				local = _local_poses[i]
				global_pose = parent * local
			else:
				global_pose = root_global_overrides[i / 4]
				local = parent.affine_inverse() * global_pose
		else:
			var captured := _actor_poses[i]
			var held := captured.interpolate_with(carry * captured, CARRY[i % 4])
			global_pose = to_skeleton * held
			local = parent.affine_inverse() * global_pose
		if not _valid(global_pose) or not _valid(local):
			return false
		globals.append(global_pose)
		locals.append(local)
	# Validate the whole frame before the first write; only these12controls
	# belong to this layer. All body poses and bone rests remain untouched.
	for i: int in COUNT:
		var local := locals[i]
		skeleton.set_bone_pose_position(_bones[i], local.origin)
		skeleton.set_bone_pose_rotation(_bones[i], local.basis.get_rotation_quaternion())
		skeleton.set_bone_pose_scale(_bones[i], local.basis.get_scale())
	skeleton.force_update_all_bone_transforms()
	_apply_count += 1
	return true

func stats() -> Dictionary:
	return {"ready": _has_pose, "current_context_valid": _has_pose and not _dirty,
		"needs_capture": needs_capture(),
		"captures": _capture_count, "applications": _apply_count,
		"fit_attempts": _fit_attempts, "fit_rejections": _fit_rejections,
		"rendered_palette_updates": _rendered_updates,
		"last_fit_gap_m": _last_fit_gap, "last_fit_strain": _last_fit_strain,
		"last_fit_error": _last_fit_error,
		"mount_fit_extra_margin_m": MOUNT_FIT_MARGIN_M,
		"body_fit_extra_margin_m": BODY_FIT_MARGIN_M}
