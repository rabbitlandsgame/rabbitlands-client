extends RefCounted
## Samples the existing player clips above the pelvis. The seat solver remains
## the sole owner of the pelvis, thighs, knees and feet, even during recovery.
const ACTIONS := [&"ranged_draw", &"ranged_hold", &"ranged_attack", &"cast",
	&"cast_channel_enter", &"cast_channel", &"cast_aggressive", &"cast_defensive",
	&"heal", &"cast_exit"]
const BLEND_SECONDS := 0.12
const RETURN_SECONDS := 0.18
var actor: ReplicatedActor3D
var skeleton: Skeleton3D
var bones: Array[int] = []
var clips: Dictionary = {}
var tracks: Dictionary = {}
var action: StringName = &""
var ground_action: StringName = &"idle"
var time := 0.0
var weight := 0.0
var grip_weight := 0.0
var _blend_time := 0.0
var _return_time := 0.0
var _returning := false
var _return_grip := 0.0
var _from: Dictionary = {}
var _capture_revision := 0
var _clip_revision := 0
var _neutral_spine := Quaternion.IDENTITY
var _spine := -1
var _parent_chain: Array[int] = []
var _parent_tracks: Dictionary = {}
var _parent_rest_rotations: Dictionary = {}
var _reference_parent := Basis.IDENTITY

func configure(player: ReplicatedActor3D) -> void:
	actor = player
	skeleton = actor.get_skeleton()
	_spine = skeleton.find_bone("spine_01")
	_neutral_spine = skeleton.get_bone_pose_rotation(_spine)
	var parent := skeleton.get_bone_parent(_spine)
	while parent >= 0:
		_parent_chain.push_front(parent)
		_parent_rest_rotations[parent] = skeleton.get_bone_pose_rotation(parent)
		parent = skeleton.get_bone_parent(parent)
	for bone: int in _parent_chain:
		_reference_parent = (_reference_parent * skeleton.get_bone_rest(bone).basis \
			* Basis(_parent_rest_rotations[bone])).orthonormalized()
	for bone: int in skeleton.get_bone_count():
		var ancestor := bone
		while ancestor >= 0 and ancestor != _spine:
			ancestor = skeleton.get_bone_parent(ancestor)
		if ancestor == _spine:
			bones.append(bone)
	for key: StringName in ACTIONS:
		var name := actor.resolver.clip_for_action(key)
		if not actor.animation_player.has_animation(name):
			continue
		_cache_clip(key, actor.animation_player.get_animation(name))

func _cache_clip(key: StringName, clip: Animation) -> void:
	_clip_revision += 1
	clips[key] = clip
	var rotations: Array = []
	var parents := {}
	for track: int in clip.get_track_count():
		if clip.track_get_type(track) != Animation.TYPE_ROTATION_3D:
			continue
		var bone := skeleton.find_bone(str(clip.track_get_path(track).get_concatenated_subnames()))
		if bone in bones:
			rotations.append([bone, track])
		elif bone in _parent_chain:
			parents[bone] = track
	tracks[key] = rotations
	_parent_tracks[key] = parents

func request(next: StringName, restart := false) -> void:
	if next in ACTIONS:
		# Spell variants and ranged techniques select their clip immediately
		# before play_action. Use that current mapping, not the mounting-time one.
		var name := actor.resolver.clip_for_action(next)
		if actor.animation_player.has_animation(name):
			var clip := actor.animation_player.get_animation(name)
			if clips.get(next) != clip:
				_cache_clip(next, clip)
	if next not in ACTIONS or not clips.has(next):
		if next in [&"walk", &"run", &"idle", &"combat_idle"]:
			ground_action = next
		# Movement packets must not cancel a shot or spell halfway through.
		# Explicit idle ends a held aim/channel, as it does on foot.
		if next in [&"idle", &"combat_idle"] and action in [&"ranged_draw", &"ranged_hold", &"cast_channel_enter", &"cast_channel"]:
			begin_return()
		if action.is_empty():
			actor.current_action = next
		return
	if next == action and not restart and not _returning:
		return
	_capture()
	action = next
	actor.current_action = next
	time = 0.0
	_blend_time = 0.0
	_return_time = 0.0
	_returning = false

func _capture() -> void:
	_capture_revision += 1
	_from.clear()
	for bone: int in bones:
		_from[bone] = skeleton.get_bone_pose_rotation(bone)

func begin_return() -> void:
	if action.is_empty() or _returning:
		return
	_capture()
	_return_time = 0.0
	_returning = true
	_return_grip = grip_weight

func advance(delta: float) -> void:
	if action.is_empty():
		weight = 0.0
		grip_weight = 0.0
		return
	if _returning:
		_return_time += delta
		weight = 1.0 - smoothstep(0.0, RETURN_SECONDS, _return_time)
		grip_weight = _return_grip * weight
		if weight <= 0.0:
			action = &""
			_returning = false
			actor.current_action = ground_action
		return
	_blend_time += delta
	weight = smoothstep(0.0, BLEND_SECONDS, _blend_time)
	grip_weight = move_toward(grip_weight, 1.0, delta / BLEND_SECONDS)
	var clip: Animation = clips[action]
	# The server's aim packet leads release by 250 ms. Reach a full draw in
	# that window, while keeping the existing 80 ms release/recoil timing.
	var rate := clip.length / 0.25 if action == &"ranged_draw" else actor.resolver.playback_speed_for_action(action)
	time += delta * rate
	if clip.loop_mode != Animation.LOOP_NONE:
		time = fposmod(time, clip.length)
	elif time >= clip.length:
		time = clip.length
		if action == &"ranged_draw":
			request(&"ranged_hold")
		elif action == &"cast_channel_enter":
			request(&"cast_channel")
		else:
			begin_return()

func apply() -> void:
	if action.is_empty():
		return
	if _returning:
		for bone: int in bones:
			var base := skeleton.get_bone_pose_rotation(bone)
			skeleton.set_bone_pose_rotation(bone, base.slerp(_from.get(bone, base), weight))
	else:
		var clip: Animation = clips[action]
		var source_parent := Basis.IDENTITY
		var parents: Dictionary = _parent_tracks[action]
		for ancestor: int in _parent_chain:
			var rotation: Quaternion = clip.rotation_track_interpolate(parents[ancestor], time) \
				if parents.has(ancestor) else _parent_rest_rotations[ancestor]
			source_parent = (source_parent * skeleton.get_bone_rest(ancestor).basis * Basis(rotation)).orthonormalized()
		var facing := Basis(Vector3.UP, deg_to_rad(actor.resolver.facing_offset_for_action(action)))
		var parent_delta := _reference_parent.inverse() * facing * source_parent
		var spine_rest := skeleton.get_bone_rest(_spine).basis.orthonormalized()
		for entry: Array in tracks[action]:
			var bone: int = entry[0]
			var base := skeleton.get_bone_pose_rotation(bone)
			var target := clip.rotation_track_interpolate(int(entry[1]), time)
			if bone == _spine:
				# Transfer the donor's pelvis/root orientation into the torso,
				# never into the seated pelvis or legs. This retains the bow's
				# aiming direction while preserving saddle stabilization.
				target = (Basis(base * _neutral_spine.inverse()) * spine_rest.inverse() \
					* parent_delta * spine_rest * Basis(target)).get_rotation_quaternion()
			var from: Quaternion = _from.get(bone, base)
			skeleton.set_bone_pose_rotation(bone, from.slerp(target, weight).normalized())
	skeleton.force_update_all_bone_transforms()

func duration() -> float:
	return (clips[action] as Animation).length if clips.has(action) else 0.0
