extends RefCounted
## Deterministic review pose on the existing canonical player skeleton.
## No mesh, bind, bone length or shared animation resource is rewritten.

var skeleton: Skeleton3D
var actor: Node3D
var profile: Dictionary
var neutral: Array[Transform3D] = []
var end_bases: Dictionary = {}
var pelvis := -1
var baseline_pelvis := Vector3.ZERO
var last_targets: Dictionary = {}
var last_errors: Dictionary = {}
var finger_grips: Array = []
var last_motion: Dictionary = {}
var curl_axes: Dictionary = {}
var palm_normals: Dictionary = {}
var hand_directions: Dictionary = {}
var visual_root: Node3D
var visual_rest := Transform3D.IDENTITY

func configure(body: Node3D, rig: Skeleton3D, settings: Dictionary, grip: Animation,
		visual: Node3D = null) -> Array[String]:
	actor = body
	visual_root = visual
	if visual_root != null:
		visual_rest = visual_root.transform
	skeleton = rig
	profile = settings
	var errors: Array[String] = []
	for required: String in ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "clavicle_l", "clavicle_r", "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r"]:
		if skeleton.find_bone(required) < 0:
			errors.append("rider bone missing: " + required)
	if not errors.is_empty():
		return errors
	for bone: int in skeleton.get_bone_count():
		neutral.append(skeleton.get_bone_pose(bone))
	pelvis = skeleton.find_bone("pelvis")
	skeleton.force_update_all_bone_transforms()
	baseline_pelvis = actor.to_local(skeleton.to_global(skeleton.get_bone_global_pose(pelvis).origin))
	for endpoint: String in ["foot_l", "foot_r", "hand_l", "hand_r"]:
		end_bases[endpoint] = skeleton.get_bone_global_pose(skeleton.find_bone(endpoint)).basis.orthonormalized()
	for side: String in ["l", "r"]:
		var sign_value := 1.0 if side == "l" else -1.0
		var hand := skeleton.get_bone_global_pose(skeleton.find_bone("hand_" + side))
		var middle := skeleton.get_bone_global_pose(skeleton.find_bone("middle_01_" + side)).origin
		var index := skeleton.get_bone_global_pose(skeleton.find_bone("index_01_" + side)).origin
		var pinky := skeleton.get_bone_global_pose(skeleton.find_bone("pinky_01_" + side)).origin
		var forward := (middle - hand.origin).normalized()
		var palm := forward.cross(index - pinky).normalized() * sign_value
		palm_normals[side] = hand.basis.inverse() * palm
		hand_directions[side] = hand.basis.inverse() * forward
		for finger: String in ["index", "middle", "ring", "pinky"]:
			var first := skeleton.get_bone_global_pose(skeleton.find_bone(finger + "_01_" + side)).origin
			var second := skeleton.get_bone_global_pose(skeleton.find_bone(finger + "_02_" + side)).origin
			curl_axes[finger + "_" + side] = hand.basis.inverse() * (second - first).normalized().cross(palm).normalized()
	for track: int in grip.get_track_count():
		if grip.track_get_type(track) != Animation.TYPE_ROTATION_3D:
			continue
		var bone_name := str(grip.track_get_path(track).get_concatenated_subnames())
		if not (bone_name.begins_with("thumb_") or bone_name.begins_with("index_") or bone_name.begins_with("middle_") or bone_name.begins_with("ring_") or bone_name.begins_with("pinky_")):
			continue
		var index := skeleton.find_bone(bone_name)
		if index >= 0:
			finger_grips.append([index, grip.rotation_track_interpolate(track, 0.0)])
	return errors

func fit(seat: Transform3D, gait: String, seconds: float, cycle_length: float) -> void:
	# The imported player already has its one native-to-game facing adapter.
	# Cancel the saddle's native +Z facing in the actor frame, not its mesh.
	var actor_basis := seat.basis.orthonormalized() * Basis(Vector3.UP, PI)
	var rider_frame := Transform3D(actor_basis, seat.origin - actor_basis * baseline_pelvis)
	if visual_root == null:
		actor.global_transform = rider_frame
	else:
		# Move only the existing character visual. Network position, picking,
		# camera follow, map dot and identity stay on the authoritative actor.
		visual_root.global_transform = rider_frame * visual_rest
	for bone: int in neutral.size():
		var pose := neutral[bone]
		skeleton.set_bone_pose_position(bone, pose.origin)
		skeleton.set_bone_pose_rotation(bone, pose.basis.get_rotation_quaternion())
		skeleton.set_bone_pose_scale(bone, pose.basis.get_scale())
	skeleton.force_update_all_bone_transforms()
	var lean := Basis(Vector3.RIGHT, deg_to_rad(float(profile.get("pelvisLeanDegrees", 3.0))))
	_set_basis(pelvis, lean * skeleton.get_bone_global_pose(pelvis).basis.orthonormalized())
	skeleton.force_update_all_bone_transforms()
	# The seat follows the saddle exactly; the torso counters part of its
	# pitch/roll around the existing spine joint. No stretching or world bob.
	var spine := skeleton.find_bone("spine_01")
	var current := skeleton.global_basis.orthonormalized() * skeleton.get_bone_global_pose(spine).basis.orthonormalized()
	var upright := Basis(Vector3.UP, atan2(actor_basis.z.x, actor_basis.z.z))
	var stabilized := (upright * actor_basis.inverse()) * current
	var target := current.slerp(stabilized, float(profile.get("torsoStabilization", .55)))
	_set_basis(spine, skeleton.global_basis.orthonormalized().inverse() * target)
	for finger: Array in finger_grips:
		var bone: int = finger[0]
		if skeleton.get_bone_name(bone).begins_with("thumb_"):
			skeleton.set_bone_pose_rotation(bone, skeleton.get_bone_pose_rotation(bone).slerp(finger[1], float(profile.get("fingerGripWeight", .7))))
	skeleton.force_update_all_bone_transforms()
	# Establish the grip before the arm response. This is
	# recomputed from rest on every sample so scrubbing never carries pose history.
	var grip_bases: Dictionary = {}
	for side: String in ["l", "r"]:
		var sign_value := 1.0 if side == "l" else -1.0
		_solve("upperarm_" + side, "lowerarm_" + side, "hand_" + side,
			skeleton.to_local(_world_target(seat, "handOffsetMetres", sign_value)),
			skeleton.to_local(_world_target(seat, "elbowPoleOffsetMetres", sign_value)))
		grip_bases[side] = skeleton.global_basis.orthonormalized() * skeleton.get_bone_global_pose(skeleton.find_bone("hand_" + side)).basis.orthonormalized()
	var motion := _arm_motion(gait, seconds, cycle_length)
	last_targets.clear()
	last_errors.clear()
	for side: String in ["l", "r"]:
		var sign_value := 1.0 if side == "l" else -1.0
		var foot := _world_target(seat, "footOffsetMetres", sign_value)
		var knee := _world_target(seat, "kneePoleOffsetMetres", sign_value)
		var hand := _world_target(seat, "handOffsetMetres", sign_value)
		var elbow := _world_target(seat, "elbowPoleOffsetMetres", sign_value)
		var frame := seat.basis.orthonormalized()
		hand += frame * Vector3(sign_value * motion.hand_sway, motion.hand_lift, motion.hand_follow)
		elbow += frame * Vector3(sign_value * motion.elbow_open, motion.elbow_lift, motion.elbow_follow)
		_solve("thigh_" + side, "calf_" + side, "foot_" + side, skeleton.to_local(foot), skeleton.to_local(knee))
		_solve("upperarm_" + side, "lowerarm_" + side, "hand_" + side, skeleton.to_local(hand), skeleton.to_local(elbow))
		var foot_basis: Basis = end_bases["foot_" + side]
		foot_basis = Basis(Vector3.UP, sign_value * deg_to_rad(float(profile.get("footToeOutDegrees", 8)))) * foot_basis
		_set_basis(skeleton.find_bone("foot_" + side), foot_basis)
		# Most of the motion is taken up at the shoulder and elbow. Keep the
		# wrist quiet rather than inheriting every change in forearm rotation.
		var wrist: Basis = grip_bases[side]
		var direction := (wrist * (hand_directions[side] as Vector3)).normalized()
		var palm := (wrist * (palm_normals[side] as Vector3)).normalized()
		var inward := -frame.x * sign_value
		inward = (inward - direction * inward.dot(direction)).normalized()
		wrist = Basis(direction, palm.signed_angle_to(inward, direction)) * wrist
		_set_basis(skeleton.find_bone("hand_" + side), skeleton.global_basis.orthonormalized().inverse() * wrist)
		skeleton.force_update_all_bone_transforms()
		_close_grip(side)
		last_targets["foot_" + side] = foot
		last_targets["hand_" + side] = hand
	skeleton.force_update_all_bone_transforms()
	for key: String in last_targets:
		var point := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone(key)).origin)
		last_errors[key] = point.distance_to(last_targets[key])
	last_errors["seat"] = skeleton.to_global(skeleton.get_bone_global_pose(pelvis).origin).distance_to(seat.origin)

func restore() -> void:
	if is_instance_valid(visual_root):
		visual_root.transform = visual_rest
	for bone: int in neutral.size():
		var rest := neutral[bone]
		skeleton.set_bone_pose_position(bone, rest.origin)
		skeleton.set_bone_pose_rotation(bone, rest.basis.get_rotation_quaternion())
		skeleton.set_bone_pose_scale(bone, rest.basis.get_scale())
	skeleton.force_update_all_bone_transforms()

func _close_grip(side: String) -> void:
	var hand := skeleton.get_bone_global_pose(skeleton.find_bone("hand_" + side)).basis.orthonormalized()
	var angles: Array = profile.fingerCurlDegrees
	for finger: String in ["index", "middle", "ring", "pinky"]:
		var axis := (hand * (curl_axes[finger + "_" + side] as Vector3)).normalized()
		for joint: int in range(3):
			var bone := skeleton.find_bone("%s_%02d_%s" % [finger, joint + 1, side])
			var basis := skeleton.get_bone_global_pose(bone).basis.orthonormalized()
			_set_basis(bone, Basis(axis, deg_to_rad(float(angles[joint]))) * basis)
			skeleton.force_update_all_bone_transforms()

func _arm_motion(gait: String, seconds: float, cycle_length: float) -> Dictionary:
	var settings: Dictionary = profile.get("armMotion", {})
	var tuning: Dictionary = settings.get(gait, {})
	var weight := float(settings.get("weight", 1.0))
	var phase := TAU * fposmod(seconds, cycle_length) / cycle_length
	# Only the arms follow the stride. The accepted v1 spine, neck and
	# clavicle poses above are preserved exactly.
	var beat := phase * float(tuning.get("beatsPerCycle", 1.0))
	var hand_range := float(tuning.get("handFollowMetres", 0.0)) * weight
	var elbow_range := float(tuning.get("elbowGiveMetres", 0.0)) * weight
	last_motion = {
		"hand_follow": hand_range * sin(beat - .95),
		"hand_lift": hand_range * .35 * sin(beat - .65),
		"hand_sway": hand_range * .12 * sin(phase),
		"elbow_open": elbow_range * .30 * sin(beat - .9),
		"elbow_lift": elbow_range * .35 * sin(beat - .75),
		"elbow_follow": elbow_range * sin(beat - .8)}
	return last_motion

func _world_target(seat: Transform3D, key: String, sign_value: float) -> Vector3:
	var values: Array = profile[key]
	return seat.origin + seat.basis.orthonormalized() * Vector3(float(values[0]) * sign_value, float(values[1]), float(values[2]))

func _set_basis(bone: int, global_basis: Basis) -> void:
	var parent := skeleton.get_bone_parent(bone)
	var parent_basis := skeleton.get_bone_global_pose(parent).basis.orthonormalized() if parent >= 0 else Basis.IDENTITY
	skeleton.set_bone_pose_rotation(bone, (parent_basis.inverse() * global_basis).get_rotation_quaternion().normalized())

func _aim(bone: int, child: int, target: Vector3) -> void:
	var start := skeleton.get_bone_global_pose(bone)
	var before := skeleton.get_bone_global_pose(child).origin - start.origin
	var after := target - start.origin
	if before.length_squared() < 1e-10 or after.length_squared() < 1e-10:
		return
	var turn := Quaternion(before.normalized(), after.normalized())
	_set_basis(bone, Basis(turn) * start.basis.orthonormalized())
	skeleton.force_update_all_bone_transforms()

func _solve(upper_name: String, lower_name: String, end_name: String, target: Vector3, pole: Vector3) -> void:
	var upper := skeleton.find_bone(upper_name)
	var lower := skeleton.find_bone(lower_name)
	var end := skeleton.find_bone(end_name)
	var a := skeleton.get_bone_global_pose(upper).origin
	var b := skeleton.get_bone_global_pose(lower).origin
	var c := skeleton.get_bone_global_pose(end).origin
	var first := a.distance_to(b)
	var second := b.distance_to(c)
	var direction := (target - a).normalized()
	var reach := clampf(a.distance_to(target), absf(first - second) + .0001, first + second - .0001)
	var along := (first * first + reach * reach - second * second) / (2.0 * reach)
	var bend := (pole - a) - direction * direction.dot(pole - a)
	if bend.length_squared() < 1e-8:
		bend = direction.cross(Vector3.RIGHT)
	var elbow := a + direction * along + bend.normalized() * sqrt(maxf(0.0, first * first - along * along))
	_aim(upper, lower, elbow)
	_aim(lower, end, a + direction * reach)
