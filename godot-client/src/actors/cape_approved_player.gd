extends RefCounted
## Cape-only playback after the body AnimationPlayer. The source episode's
## run-to-attack carry is replaced by carry from this actor's outgoing pose.
const Data := preload("res://src/actors/cape_approved_data.gd")
const COUNT := 12
var _actor: WeakRef
var _profile := ""
var _motion_profile := ""
var _bones := PackedInt32Array()
var _parents := PackedInt32Array()
var _binds: Array[Transform3D] = []
var _inverse_binds: Array[Transform3D] = []
var _spine := -1
var _spine_bind := Transform3D.IDENTITY
var _key := ""
var _clip := ""
var _last_time := 0.0
var _entry_time := 0.0
var _value := PackedVector3Array()
var _before_step := PackedVector3Array()
var _velocity := PackedVector3Array()
var _from := PackedVector3Array()
var _from_velocity := PackedVector3Array()
var _difference := PackedVector3Array()
var _velocity_difference := PackedVector3Array()
var _elapsed := 0.0
var _duration := 0.0
var _spring := false
var _snap_next := false
var _capture_next := false
var _fallback := true

func configure(actor: Node, skeleton: Skeleton3D, profile: String) -> bool:
	if not Data.compatible(skeleton):
		return false
	_actor = weakref(actor)
	_profile = profile
	_binds = Data.binds(profile)
	var names := Data.bone_names()
	if names.size() != _binds.size() or names.size() < COUNT:
		return false
	_bones.clear()
	_parents.clear()
	_inverse_binds.clear()
	for i: int in COUNT:
		var bone := skeleton.find_bone(names[i])
		_bones.append(bone)
		_parents.append(skeleton.get_bone_parent(bone))
		_inverse_binds.append(_binds[i].affine_inverse())
	var at := names.find("spine_03")
	if at < 0:
		return false
	_spine = skeleton.find_bone("spine_03")
	_spine_bind = _binds[at]
	_value = Data.idle(profile)
	_velocity.resize(COUNT)
	_velocity.fill(Vector3.ZERO)
	return _value.size() == COUNT

func reset() -> void:
	_key = ""
	_snap_next = true
	_capture_next = false
	_velocity.fill(Vector3.ZERO)

func _canonical_clip(actor: Node, player: AnimationPlayer) -> String:
	var assigned := String(player.assigned_animation)
	var resolver: Variant = actor.get("resolver")
	if resolver != null:
		var expected := String(resolver.call("clip_for_action", actor.get("current_action")))
		if not assigned.is_empty() and player.has_animation(assigned) and player.has_animation(expected) \
				and player.get_animation(assigned) == player.get_animation(expected):
			return expected
	return assigned.get_slice("/", assigned.get_slice_count("/") - 1)

func _capture(skeleton: Skeleton3D) -> PackedVector3Array:
	var result := PackedVector3Array()
	var inverse := (skeleton.get_bone_global_pose(_spine) * _spine_bind).affine_inverse()
	for i: int in COUNT:
		result.append((inverse * skeleton.get_bone_global_pose(_bones[i]) * _binds[i]).origin)
	return result

func step(skeleton: Skeleton3D, delta: float) -> PackedVector3Array:
	var actor := _actor.get_ref() as Node
	if actor == null or bool(actor.get("_cinematic_active")):
		return _unsupported()
	var player := actor.get("animation_player") as AnimationPlayer
	if player == null or player.assigned_animation.is_empty():
		return _unsupported()
	_clip = _canonical_clip(actor, player)
	var entry := Data.motion_clip(_profile, _clip)
	_motion_profile = str(entry.get("source_profile", _profile))
	var target := Data.idle(_profile) if _clip == "Idle_Subtle" else Data.sample(entry, player.current_animation_position)
	if target.size() != COUNT:
		return _unsupported()
	_fallback = false
	var key := _clip + "|" + String(player.assigned_animation)
	var time := player.current_animation_position
	var restarted := not bool(entry.get("loop", false)) and time + 0.00001 < _last_time
	if key != _key or restarted:
		_entry_time = time
		if _capture_next:
			_value = _capture(skeleton)
			_capture_next = false
		_from = _value.duplicate()
		_from_velocity = _velocity.duplicate()
		_difference.resize(COUNT)
		_velocity_difference.resize(COUNT)
		var before := Data.sample(entry, time - 0.001)
		var after := Data.sample(entry, time + 0.001)
		for i: int in COUNT:
			_difference[i] = _from[i] - target[i]
			var target_velocity := Vector3.ZERO
			if before.size() == COUNT and after.size() == COUNT:
				target_velocity = (after[i] - before[i]) * (player.speed_scale / 0.002)
			_velocity_difference[i] = (_from_velocity[i] - target_velocity).limit_length(2.5)
		_elapsed = 0.0
		_spring = _clip != "Idle_Subtle" and _clip != "Walk" and not _clip.begins_with("Run") and not _clip.begins_with("Human_Run")
		_duration = 0.60 if _clip == "Idle_Subtle" else (0.12 if _spring else 11.0 / 30.0)
		if _snap_next:
			_duration = 0.0
			_snap_next = false
		_key = key
	else:
		# Follow the body clock even when the animation gate skips a tick or
		# pauses playback. First-step clearance must not replay every loop.
		var advance := time - _last_time
		if bool(entry.get("loop", false)) and advance < 0.0:
			advance += float(entry.get("duration", 0.0))
		_entry_time += maxf(advance, 0.0)
	_last_time = time
	_before_step = _value.duplicate()
	_elapsed += maxf(delta, 0.0)
	_value = target.duplicate()
	if _duration > 0.0:
		if _spring:
			var decay := exp(-_elapsed / _duration)
			for i: int in COUNT:
				_value[i] += (_difference[i] + (_velocity_difference[i] + _difference[i] / _duration) * _elapsed) * decay
		else:
			var blend := clampf(_elapsed / _duration, 0.0, 1.0)
			blend = blend * blend * blend * (blend * (blend * 6.0 - 15.0) + 10.0)
			for i: int in COUNT:
				_value[i] += (_difference[i] + _velocity_difference[i] * _elapsed) * (1.0 - blend)
	var start: Dictionary = entry.get("entry", {})
	if not start.is_empty() and _entry_time < float(start.get("duration", 0.0)):
		var correction := Data.sample(start, _entry_time)
		if correction.size() == COUNT:
			for i: int in COUNT:
				_value[i] += correction[i]
	commit(_value, delta)
	return _value.duplicate()

func _unsupported() -> PackedVector3Array:
	_fallback = true
	_key = ""
	_capture_next = true
	return PackedVector3Array()

func commit(value: PackedVector3Array, delta: float) -> void:
	if delta > 0.000001 and _before_step.size() == COUNT:
		for i: int in COUNT:
			_velocity[i] = (value[i] - _before_step[i]) / delta
	_value = value.duplicate()

func skin_frame(skeleton: Skeleton3D) -> Transform3D:
	return skeleton.get_bone_global_pose(_spine) * _spine_bind

func neutral_bone_pose(skeleton: Skeleton3D, index: int) -> Transform3D:
	return skin_frame(skeleton) * _inverse_binds[index]

func observe_fallback(skeleton: Skeleton3D, delta: float) -> void:
	_before_step = _value.duplicate()
	commit(_capture(skeleton), delta)
	_capture_next = false

func write_pose(skeleton: Skeleton3D, translations: PackedVector3Array) -> void:
	if translations.size() != COUNT:
		return
	var frame := skin_frame(skeleton)
	var desired: Dictionary = {}
	for i: int in COUNT:
		var pose := frame * Transform3D(Basis.IDENTITY, translations[i]) * _inverse_binds[i]
		var parent: Transform3D = desired.get(_parents[i], skeleton.get_bone_global_pose(_parents[i]))
		var local := parent.affine_inverse() * pose
		skeleton.set_bone_pose_position(_bones[i], local.origin)
		skeleton.set_bone_pose_rotation(_bones[i], local.basis.get_rotation_quaternion())
		skeleton.set_bone_pose_scale(_bones[i], local.basis.get_scale())
		desired[_bones[i]] = pose

func hold_idle(skeleton: Skeleton3D) -> void:
	var idle := Data.idle(_profile)
	if idle.size() == COUNT:
		write_pose(skeleton, idle)
		_value = idle
		_velocity.fill(Vector3.ZERO)

func stats() -> Dictionary:
	return {"enabled": not _profile.is_empty(), "profile": _profile, "clip": _clip,
		"motion_profile": _motion_profile,
		"fallback": _fallback, "transition_seconds": _elapsed,
		"duration_seconds": _duration, "controls": _value}

func needs_geometry_guard() -> bool:
	return _motion_profile != _profile
