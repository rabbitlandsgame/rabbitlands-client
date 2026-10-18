extends RefCounted
## Mount-only articulation adapter. Keep the authored fetlock/hoof trajectory
## while limiting the thigh lift that pulls this rig's rump into the saddle.
var skeleton: Skeleton3D
var body := -1
var body_rest_inverse := Transform3D.IDENTITY
var chains: Array[Dictionary] = []
var max_angle := 0.0
var soft_band := 0.0

func configure(rig: Skeleton3D, tuning: Dictionary) -> Array[String]:
	skeleton = rig
	if tuning.is_empty():
		return []
	body = rig.find_bone(str(tuning.bodyBone))
	if body < 0:
		return ["Mount hind-leg body reference missing"]
	body_rest_inverse = rig.get_bone_global_rest(body).affine_inverse()
	max_angle = deg_to_rad(float(tuning.thighMaxDegrees))
	soft_band = deg_to_rad(float(tuning.softLimitDegrees))
	for names: Array in tuning.chains:
		var bones := PackedInt32Array()
		for name: String in names:
			var bone := rig.find_bone(name)
			if bone < 0:
				return ["Mount hind-leg joint missing: " + name]
			bones.append(bone)
		var lengths := PackedFloat32Array()
		for i: int in 3:
			if rig.get_bone_parent(bones[i + 1]) != bones[i]:
				return ["Mount hind-leg chain is not serial"]
			lengths.append(rig.get_bone_global_rest(bones[i]).origin.distance_to(rig.get_bone_global_rest(bones[i + 1]).origin))
		chains.append({"bones": bones, "lengths": lengths,
			"side": rig.get_bone_global_rest(bones[1]).origin.x - rig.get_bone_global_rest(bones[0]).origin.x})
	return []

func apply(gait: String) -> void:
	if chains.is_empty() or gait == "idle":
		return
	var frame := skeleton.get_bone_global_pose(body) * body_rest_inverse
	var inverse := frame.affine_inverse()
	for chain: Dictionary in chains:
		var bones: PackedInt32Array = chain.bones
		var lengths: PackedFloat32Array = chain.lengths
		var hip := inverse * skeleton.get_bone_global_pose(bones[0]).origin
		var stifle := inverse * skeleton.get_bone_global_pose(bones[1]).origin
		var fetlock := inverse * skeleton.get_bone_global_pose(bones[3]).origin
		var hoof_basis := skeleton.get_bone_global_pose(bones[3]).basis.orthonormalized()
		var femur := stifle - hip
		var angle := atan2(femur.z, -femur.y)
		# Smooth asymptotic limit has no hard stop at the top of each stride.
		var distance := (max_angle - angle) / soft_band
		if distance < 20.0:
			angle = max_angle - soft_band * log(1.0 + exp(distance))
		var side := float(chain.side)
		var sagittal_length := sqrt(maxf(0.0, lengths[0] * lengths[0] - side * side))
		stifle = hip + Vector3(side, -cos(angle) * sagittal_length, sin(angle) * sagittal_length)
		var delta := fetlock - stifle
		var direction := delta.normalized()
		var reach := clampf(delta.length(), absf(lengths[1] - lengths[2]) + .000001,
			lengths[1] + lengths[2] - .000001)
		var along := (lengths[1] * lengths[1] + reach * reach - lengths[2] * lengths[2]) / (2.0 * reach)
		var bend := Vector3.FORWARD - direction * Vector3.FORWARD.dot(direction)
		var hock := stifle + direction * along + bend.normalized() * sqrt(maxf(0.0, lengths[1] * lengths[1] - along * along))
		_aim(bones[0], bones[1], frame * stifle)
		_aim(bones[1], bones[2], frame * hock)
		_aim(bones[2], bones[3], frame * fetlock)
		# Restore the exact authored hoof orientation after solving its parents.
		_set_basis(bones[3], hoof_basis)
		skeleton.force_update_all_bone_transforms()

func _set_basis(bone: int, basis: Basis) -> void:
	var parent := skeleton.get_bone_parent(bone)
	var parent_basis := skeleton.get_bone_global_pose(parent).basis.orthonormalized() if parent >= 0 else Basis.IDENTITY
	skeleton.set_bone_pose_rotation(bone, (parent_basis.inverse() * basis).get_rotation_quaternion().normalized())

func _aim(bone: int, child: int, target: Vector3) -> void:
	var start := skeleton.get_bone_global_pose(bone)
	var before := skeleton.get_bone_global_pose(child).origin - start.origin
	var after := target - start.origin
	_set_basis(bone, Basis(Quaternion(before.normalized(), after.normalized())) * start.basis.orthonormalized())
	skeleton.force_update_all_bone_transforms()
