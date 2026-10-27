class_name HumanLocomotionPolish
extends RefCounted
## Human-only, immutable derivatives of the imported stance/travel clips. The source
## library, body/skin/rest pose, root and lower-body channels stay exact. The
## accepted travel arms stay exact; finger poses and standing arms are separate.
## Runtime playback uses ordinary cached Animation resources at every quality.

const SOURCE_META := &"human_locomotion_source"
const RESULT_META := &"human_locomotion_result"
const CACHE_LIMIT := 8
const CLIPS: Array[StringName] = [&"Walk", &"Run_Female"]
const IDLE_CLIPS: Array[StringName] = [&"Idle_Subtle", &"Idle_A"]
const HELD_RUN_CLIPS: Array[StringName] = [&"Human_Run_Hold_L", &"Human_Run_Hold_R", &"Human_Run_Hold_Both"]
const HANDS := preload("res://src/actors/human_hand_pose.gd")
const ATTACKS := preload("res://src/actors/human_attack_library.gd")
const ARM_BONES := ["clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
	"lowerarm_l", "lowerarm_r", "hand_l", "hand_r"]
const RUN_TORSO := {"spine_01": 4.0, "spine_02": 2.0, "neck_01": -2.0}
static var _libraries: Dictionary = {}

static func supports(model: Dictionary) -> bool:
	return str(model.get("culture", "")) == "luminous" and str(model.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func clear() -> void:
	_libraries.clear()
	ATTACKS.clear()

## Bits describe the actual held hands, including the separate left-hand bow.
static func run_clip_for_hands(mask: int) -> StringName:
	return HELD_RUN_CLIPS[clampi(mask, 1, 3)-1] if mask != 0 else &"Run_Female"

static func install(player: AnimationPlayer, model: Dictionary) -> void:
	if player == null or not supports(model) or not player.has_animation_library(&""):
		return
	var current := player.get_animation_library(&"")
	var source := current
	if player.has_meta(RESULT_META) and current == player.get_meta(RESULT_META):
		source = player.get_meta(SOURCE_META) as AnimationLibrary
	var profile := "male" if str(model.get("bodyTemplate", "")) == "luminous_male" else "female"
	var result := derive(source, profile, _target_skeleton(player, source))
	if result == current:
		return
	player.set_meta(SOURCE_META, source)
	player.set_meta(RESULT_META, result)
	player.remove_animation_library(&"")
	player.add_animation_library(&"", result)

static func derive(source: AnimationLibrary, profile := "female", skeleton: Skeleton3D = null) -> AnimationLibrary:
	if source == null:
		return null
	# Accepted female travel arms stay exact. Male silhouettes use their own
	# baked arm placement, never a mutation of that shared source clip.
	if profile != "male" or skeleton == null:
		profile = "female"
	var key := "%s:%s" % [source.get_instance_id(), profile]
	if _libraries.has(key):
		return _libraries[key].result as AnimationLibrary
	var result := AnimationLibrary.new()
	var walk: Animation = source.get_animation(&"Walk") if source.has_animation(&"Walk") else null
	var neutral := _walking_hands(walk)
	var held_run: Animation
	for name: StringName in source.get_animation_list():
		var animation := source.get_animation(name)
		# Sharing these resources is intentional: attacks, casts, RESET and all
		# remaining actions retain their exact original keys and hit timings.
		var clip := _travel(animation, name == &"Run_Female", neutral) if name in CLIPS else animation
		if name in CLIPS and profile == "male":
			_male_placement(clip, skeleton, name == &"Run_Female")
			if name == &"Run_Female" and source.has_animation(&"Fighting_Idle"):
				_male_running_hands(clip, source.get_animation(&"Fighting_Idle"), skeleton)
		if name == &"Run_Female":
			held_run = _copy_animation(clip)
			HANDS.apply_to_clip(clip, profile)
		result.add_animation(name, clip)
	if result.has_animation(&"Walk"):
		for idle_name: StringName in IDLE_CLIPS:
			if source.has_animation(idle_name):
				result.remove_animation(idle_name)
				result.add_animation(idle_name, _idle_arms(source.get_animation(idle_name), result.get_animation(&"Walk"), profile, skeleton))
	if held_run != null:
		for mask: int in range(1, 4):
			var variant := held_run if mask == 3 else _copy_animation(result.get_animation(&"Run_Female"))
			if mask != 3:
				_restore_held_fingers(variant, held_run, "l" if mask == 1 else "r")
			result.add_animation(run_clip_for_hands(mask), variant)
	ATTACKS.append(result, source, {"culture":"luminous", "bodyTemplate":"luminous_"+profile}, skeleton)
	if _libraries.size() >= CACHE_LIMIT:
		_libraries.erase(_libraries.keys()[0])
	# Keep the source strongly referenced alongside its derivative so a freed
	# source's instance ID cannot be reused as a different library's cache key.
	_libraries[key] = {"source": source, "result": result}
	return result

static func _copy_animation(source: Animation) -> Animation:
	var result := Animation.new()
	result.length = source.length
	result.loop_mode = source.loop_mode
	result.step = source.step
	for track: int in source.get_track_count(): source.copy_track(track, result)
	for marker: StringName in source.get_marker_names():
		result.add_marker(marker, source.get_marker_time(marker))
		result.set_marker_color(marker, source.get_marker_color(marker))
	return result

## Held hands retain their pre-refinement travel grip; the other hand can use
## the relaxed fist. All four variants share the exact accepted body motion.
static func _restore_held_fingers(result: Animation, held: Animation, side: String) -> void:
	for track: int in result.get_track_count():
		if result.track_get_type(track) != Animation.TYPE_ROTATION_3D: continue
		var bone := str(result.track_get_path(track).get_concatenated_subnames())
		if not bone.ends_with("_"+side) or bone.get_slice("_",0) not in ["thumb","index","middle","ring","pinky"]: continue
		for key: int in result.track_get_key_count(track):
			result.track_set_key_value(track, key, held.track_get_key_value(track,key))

## Keep authored breathing/feet/head, settling the arms toward the two accepted
## mid-walk poses with a small amount of the original standing movement.
static func _idle_arms(source: Animation, walk: Animation, profile := "female", skeleton: Skeleton3D = null) -> Animation:
	var result := _copy_animation(source)
	var walking := _rotations(walk)
	for track: int in source.get_track_count():
		if source.track_get_type(track) != Animation.TYPE_ROTATION_3D: continue
		var bone := str(source.track_get_path(track).get_concatenated_subnames()).get_slice(":",0)
		if bone not in ARM_BONES or not walking.has(bone): continue
		var neutral := _sample(walk, walking[bone], walk.length*0.25).slerp(_sample(walk, walking[bone], walk.length*0.75),0.5).normalized()
		for key: int in result.track_get_key_count(track):
			var original: Quaternion = source.track_get_key_value(track,key)
			result.track_set_key_value(track,key,original.slerp(neutral,0.92).normalized())
	if profile == "male" and skeleton != null:
		# A small shoulder extension lets the whole relaxed arm hang farther
		# back in side view. Keep the accepted elbow bend, wrist and fingers;
		# equipped grips still aim afterwards through WeaponCarryPose.
		var channels := {}
		for track: int in result.get_track_count():
			var bone := str(result.track_get_path(track).get_concatenated_subnames()).get_slice(":",0)
			if not channels.has(bone): channels[bone] = {}
			channels[bone][result.track_get_type(track)] = track
		for name: String in ["upperarm_l", "upperarm_r"]:
			var bone := skeleton.find_bone(name)
			if bone < 0 or not channels.get(name,{}).has(Animation.TYPE_ROTATION_3D): continue
			var track: int = channels[name][Animation.TYPE_ROTATION_3D]
			var values: Array[Quaternion] = []
			for key: int in result.track_get_key_count(track):
				var pose := _pose_at(result,skeleton,channels,result.track_get_key_time(track,key))
				var parent := skeleton.get_bone_parent(bone)
				var aimed: Basis = Basis(Vector3.RIGHT,deg_to_rad(7.0))*pose.global[bone].basis
				values.append((pose.global[parent].basis.inverse()*aimed).orthonormalized().get_rotation_quaternion().normalized())
			for key: int in values.size(): result.track_set_key_value(track,key,values[key])
	return result

static func _target_skeleton(player: AnimationPlayer, library: AnimationLibrary) -> Skeleton3D:
	if not library.has_animation(&"Walk"):
		return null
	var root := player.get_node_or_null(player.root_node)
	var animation := library.get_animation(&"Walk")
	if root == null:
		return null
	for track: int in animation.get_track_count():
		var path := str(animation.track_get_path(track)).get_slice(":", 0)
		var skeleton := root.get_node_or_null(NodePath(path)) as Skeleton3D
		if skeleton != null:
			return skeleton
	return null

## Evaluate the existing v1 arm pose in canonical rig space, then bake a
## male-specific elbow/forearm plane. This runs once per shared clip variant;
## no Skeleton3D pose is written and no per-frame modifier is installed.
static func _male_placement(animation: Animation, skeleton: Skeleton3D, running: bool) -> void:
	var channels := {}
	for track: int in animation.get_track_count():
		var bone := str(animation.track_get_path(track).get_concatenated_subnames()).get_slice(":", 0)
		if not channels.has(bone): channels[bone] = {}
		channels[bone][animation.track_get_type(track)] = track
	if running:
		_male_running_torso(animation, skeleton, channels)
	var frames := {}
	var pending := {}
	# Read every source pose before replacing any keys, so a later sample
	# cannot accidentally include an earlier sample's correction.
	for bone: String in ["upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r"]:
		if not channels.has(bone) or not channels[bone].has(Animation.TYPE_ROTATION_3D): continue
		var track: int = channels[bone][Animation.TYPE_ROTATION_3D]
		var values: Array[Quaternion] = []
		for index: int in animation.track_get_key_count(track):
			var time := animation.track_get_key_time(track, index)
			if not frames.has(time):
				frames[time] = _male_pose(animation, skeleton, channels, time, running)
			values.append(frames[time][bone])
		pending[track] = values
	for track: int in pending:
		var values: Array = pending[track]
		for index: int in values.size():
			animation.track_set_key_value(track, index, values[index])

static func _pose_at(animation: Animation, skeleton: Skeleton3D, channels: Dictionary, time: float) -> Dictionary:
	var local: Array[Transform3D] = []
	var global: Array[Transform3D] = []
	var t := fposmod(time, animation.length) if animation.length > 0 else 0.0
	for bone: int in skeleton.get_bone_count():
		var rest := skeleton.get_bone_rest(bone)
		var tracks: Dictionary = channels.get(str(skeleton.get_bone_name(bone)), {})
		var origin := animation.position_track_interpolate(tracks[Animation.TYPE_POSITION_3D], t) if tracks.has(Animation.TYPE_POSITION_3D) else rest.origin
		var rotation := animation.rotation_track_interpolate(tracks[Animation.TYPE_ROTATION_3D], t) if tracks.has(Animation.TYPE_ROTATION_3D) else rest.basis.get_rotation_quaternion()
		var scale := animation.scale_track_interpolate(tracks[Animation.TYPE_SCALE_3D], t) if tracks.has(Animation.TYPE_SCALE_3D) else rest.basis.get_scale()
		var transform := Transform3D(Basis(rotation).scaled(scale), origin)
		local.append(transform)
		var parent := skeleton.get_bone_parent(bone)
		global.append(global[parent] * transform if parent >= 0 else transform)
	return {"local": local, "global": global}

static func _male_running_torso(animation: Animation, skeleton: Skeleton3D, channels: Dictionary) -> void:
	# The frontal references establish forward running intent, not a measured
	# 3D pitch. This modest native-length spine lean is an authored depth
	# interpretation; the pelvis, legs and support surfaces remain untouched.
	for name: String in RUN_TORSO:
		var bone := skeleton.find_bone(name)
		if bone < 0 or not channels.get(name, {}).has(Animation.TYPE_ROTATION_3D): continue
		var track: int = channels[name][Animation.TYPE_ROTATION_3D]
		var values: Array[Quaternion] = []
		for key: int in animation.track_get_key_count(track):
			var pose := _pose_at(animation, skeleton, channels, animation.track_get_key_time(track, key))
			var global: Array = pose.global
			var parent := skeleton.get_bone_parent(bone)
			var aimed: Basis = Basis(Vector3.RIGHT, deg_to_rad(RUN_TORSO[name])) * global[bone].basis
			values.append((global[parent].basis.inverse() * aimed).orthonormalized().get_rotation_quaternion().normalized())
		for key: int in values.size(): animation.track_set_key_value(track, key, values[key])

static func _male_running_hands(animation: Animation, fist: Animation, skeleton: Skeleton3D) -> void:
	var targets := {}
	for track: int in fist.get_track_count():
		if fist.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			targets[str(fist.track_get_path(track).get_concatenated_subnames())] = track
	for track: int in animation.get_track_count():
		if animation.track_get_type(track) != Animation.TYPE_ROTATION_3D: continue
		var bone := str(animation.track_get_path(track).get_concatenated_subnames())
		if not targets.has(bone) or bone.get_slice("_", 0) not in ["thumb", "index", "middle", "ring", "pinky"]: continue
		var joint := skeleton.find_bone(bone)
		# The shared library also carries terminal finger channels absent from
		# these body rigs. Leave those original tracks alone.
		if joint < 0 or int(bone.get_slice("_",1)) not in [1,2,3]: continue
		var closed := fist.rotation_track_interpolate(targets[bone], 0.0)
		# Keep the accepted native grip as the held-hand baseline. The free-hand
		# refinement below fits physical fingertip and palm surface landmarks.
		for key: int in animation.track_get_key_count(track):
			var original: Quaternion = animation.track_get_key_value(track, key)
			animation.track_set_key_value(track, key, original.slerp(closed,0.8 if bone.begins_with("thumb_") else 0.95).normalized())
	# Held Run variants keep this seed; free hands receive HumanHandPose.

static func _male_pose(animation: Animation, skeleton: Skeleton3D, channels: Dictionary,
		time: float, running: bool) -> Dictionary:
	var pose := _pose_at(animation, skeleton, channels, time)
	var local: Array = pose.local
	var global: Array = pose.global
	var center: float = global[skeleton.find_bone("pelvis")].origin.x
	var result := {}
	for side: String in ["l", "r"]:
		var sign := 1.0 if side == "l" else -1.0
		var upper := skeleton.find_bone("upperarm_" + side)
		var lower := skeleton.find_bone("lowerarm_" + side)
		var hand := skeleton.find_bone("hand_" + side)
		var thumb := skeleton.find_bone("thumb_01_" + side)
		var parent := skeleton.get_bone_parent(upper)
		var shoulder: Transform3D = global[upper]
		var upper_vector: Vector3 = shoulder.basis * local[lower].origin
		# Reviewed frontal video shows continuous alternating pumps. The source
		# run holds an upper arm behind the torso for half its cycle. Replace
		# that plateau with a periodic guide at the original contralateral leg
		# phase; neither video establishes a new physical forward stride speed.
		var phase := fposmod(time / animation.length, 1.0)
		var swing := cos(phase * TAU + (0.0 if side == "l" else PI)) * (1.0 if running else -1.0)
		var forward := (swing + 1.0) * 0.5
		var arm_angle := deg_to_rad(3.0 + 26.0 * swing if running else -3.0 + 20.0 * swing)
		# The frontal references abduct the upper arm; the old fixed 3/4 cm
		# outset made both elbows hang almost vertically beside the torso.
		# Transfer the angle with native segment length, allowing the forward
		# arm to open slightly instead of keeping an elbow on a fixed rail.
		var spread := 0.370 + 0.055 * forward if running else 0.255 + 0.085 * forward
		var width := sign * upper_vector.length() * spread
		var radius := sqrt(maxf(upper_vector.length_squared() - width * width, 0.000001))
		var desired := Vector3(width, -radius * cos(arm_angle), radius * sin(arm_angle))
		shoulder.basis = Basis(Quaternion(upper_vector.normalized(), desired.normalized())) * shoulder.basis
		var elbow: Transform3D = shoulder * local[lower]
		var forearm: Vector3 = elbow.basis * local[hand].origin
		var wrist_x := center + sign * (0.250 - 0.130 * forward if running else 0.245 + 0.010 * forward)
		# Rising hands travel inward toward the chest, then release beside the
		# hip. Keep the rear elbow bent and let the front bend tighten gently.
		var upper_direction: Vector3 = (shoulder.basis * local[lower].origin).normalized()
		# The wider running elbow needs more forward flexion to keep the hand
		# at the observed sternum height. The rear running bend stays unchanged.
		var flex_degrees := 86.0 + 6.0 * swing + 10.0 * forward * forward if running else 28.0 + 10.0 * forward
		var flex := deg_to_rad(flex_degrees)
		desired = _bent_forearm(upper_direction, forearm.length(), wrist_x - elbow.origin.x, flex)
		# A direction-only aim retains the source upperarm's axial roll. Align
		# the native rest-X elbow hinge with the intended bend plane first;
		# forearm pronation and wrist aiming remain independent of this roll.
		var native_plane := shoulder.basis * skeleton.get_bone_rest(lower).basis.x
		native_plane -= upper_direction * native_plane.dot(upper_direction)
		var target_plane := upper_direction.cross(desired.normalized())
		if native_plane.length_squared() > 0.00001 and target_plane.length_squared() > 0.00001:
			native_plane = native_plane.normalized()
			target_plane = target_plane.normalized()
			var roll := atan2(upper_direction.dot(native_plane.cross(target_plane)), native_plane.dot(target_plane))
			shoulder.basis = Basis(upper_direction, roll) * shoulder.basis
			elbow = shoulder * local[lower]
			forearm = elbow.basis * local[hand].origin
		result["upperarm_" + side] = (global[parent].basis.inverse() * shoulder.basis).orthonormalized().get_rotation_quaternion().normalized()
		elbow.basis = Basis(Quaternion(forearm.normalized(), desired.normalized())) * elbow.basis
		result["lowerarm_" + side] = (shoulder.basis.inverse() * elbow.basis).orthonormalized().get_rotation_quaternion().normalized()
		var wrist: Transform3D = elbow * local[hand]
		# Relaxed palms face the torso while walking; a running forearm keeps
		# its thumb uppermost. Aim by the actual canonical thumb rest vector,
		# preserving finger channels and allowing weapon carry to aim last.
		if thumb >= 0:
			var axis := wrist.basis.y.normalized()
			var thumb_local := skeleton.get_bone_global_rest(hand).affine_inverse() * skeleton.get_bone_global_rest(thumb).origin
			var across := wrist.basis * thumb_local
			if running:
				# The thumb's proximal joint sits off the palm plane. Aiming that
				# wrist-to-thumb vector rolls the actual palm upwards. Use the
				# true MCP row and wrist-to-middle-finger plane instead.
				var middle := skeleton.find_bone("middle_01_" + side)
				var index := skeleton.find_bone("index_01_" + side)
				var pinky := skeleton.find_bone("pinky_01_" + side)
				if middle >= 0 and index >= 0 and pinky >= 0:
					var to_hand := skeleton.get_bone_global_rest(hand).affine_inverse()
					var palm_forward := (to_hand * skeleton.get_bone_global_rest(middle).origin).normalized()
					var palm_across := to_hand.basis * (skeleton.get_bone_global_rest(index).origin - skeleton.get_bone_global_rest(pinky).origin)
					axis = (wrist.basis * palm_forward).normalized()
					across = wrist.basis * palm_across
			across = (across - axis * across.dot(axis)).normalized()
			var aim := Vector3.UP if running else Vector3.BACK
			aim = aim - axis * aim.dot(axis)
			if across.length_squared() > 0.5 and aim.length_squared() > 0.01:
				aim = aim.normalized()
				var angle := atan2(axis.dot(across.cross(aim)), across.dot(aim))
				if not running: angle = clampf(angle, -deg_to_rad(50), deg_to_rad(50))
				wrist.basis = Basis(axis, angle) * wrist.basis
				if running:
					# A small native wrist flexion softens the open palm silhouette;
					# equipped wrist aiming still runs afterwards in WeaponCarryPose.
					wrist.basis = Basis(aim, -sign*deg_to_rad(10.0))*wrist.basis
		result["hand_" + side] = (elbow.basis.inverse() * wrist.basis).orthonormalized().get_rotation_quaternion().normalized()
	return result

static func _with_width(vector: Vector3, width: float) -> Vector3:
	var length_squared := vector.length_squared()
	var x := clampf(width, -sqrt(length_squared) * 0.8, sqrt(length_squared) * 0.8)
	var factor := sqrt(maxf(length_squared - x * x, 0.000001) / maxf(vector.y * vector.y + vector.z * vector.z, 0.000001))
	return Vector3(x, vector.y * factor, vector.z * factor)

static func _bent_forearm(upper: Vector3, length: float, width: float, flexion: float) -> Vector3:
	var x := clampf(width / length, -0.8, 0.8)
	var radius := sqrt(1.0 - x * x)
	var plane := Vector2(upper.y, upper.z)
	var axis := plane.normalized()
	var along := clampf((cos(flexion) - upper.x * x) / maxf(plane.length() * radius, 0.00001), -1.0, 1.0)
	var perpendicular := Vector2(-axis.y, axis.x) * sqrt(maxf(1.0 - along * along, 0.0))
	var first := axis * along + perpendicular
	var second := axis * along - perpendicular
	var yz := first if first.y >= second.y else second
	return Vector3(x, yz.x * radius, yz.y * radius) * length

static func _rotations(animation: Animation) -> Dictionary:
	var result := {}
	if animation == null:
		return result
	for track: int in animation.get_track_count():
		if animation.track_get_type(track) != Animation.TYPE_ROTATION_3D:
			continue
		var bone := str(animation.track_get_path(track).get_concatenated_subnames()).get_slice(":", 0)
		if bone in ARM_BONES:
			result[bone] = track
	return result

static func _mirror(value: Quaternion) -> Quaternion:
	# The actual canonical arm axes mirror across the body's X midplane.
	return Quaternion(value.x, -value.y, -value.z, value.w).normalized()

static func _sample(animation: Animation, track: int, time: float) -> Quaternion:
	var wrapped := fposmod(time, animation.length) if animation.length > 0.0 else 0.0
	return animation.rotation_track_interpolate(track, wrapped).normalized()

static func _walking_hands(walk: Animation) -> Dictionary:
	var tracks := _rotations(walk)
	if not tracks.has("hand_l") or not tracks.has("hand_r"):
		return {}
	var left := _sample(walk, tracks.hand_l, 0.0).slerp(_mirror(_sample(walk, tracks.hand_r, 0.0)), 0.5).normalized()
	return {"hand_l": left, "hand_r": _mirror(left)}

static func _travel(source: Animation, running: bool, neutral: Dictionary) -> Animation:
	var tracks := _rotations(source)
	# Resource.duplicate() round-trips track properties through packed float
	# times and can quantize unrelated key timestamps. Engine track copying
	# preserves the exact original channel data before touching arm rotations.
	var result := Animation.new()
	result.length = source.length
	result.loop_mode = source.loop_mode
	result.step = source.step
	for track: int in source.get_track_count():
		source.copy_track(track, result)
	for marker: StringName in source.get_marker_names():
		result.add_marker(marker, source.get_marker_time(marker))
		result.set_marker_color(marker, source.get_marker_color(marker))
	for bone: String in ARM_BONES:
		var other := bone.trim_suffix("_l") + "_r" if bone.ends_with("_l") else bone.trim_suffix("_r") + "_l"
		if not tracks.has(bone) or not tracks.has(other):
			continue
		var track: int = tracks[bone]
		for index: int in result.track_get_key_count(track):
			var time := result.track_get_key_time(track, index)
			var phase := time / source.length if source.length > 0.0 else 0.0
			# Retain the authored arm/leg phase and broad swing. Balance paired
			# shoulders/arms using the other side half a cycle later, correcting
			# the source run's conspicuously uneven left/right wrist heights.
			var value := _sample(source, track, time).slerp(
				_mirror(_sample(source, tracks[other], time + source.length * 0.5)), 0.5).normalized()
			if not running and bone.begins_with("lowerarm_"):
				# The source walk almost locks its elbows (~12 degrees). A small
				# relaxed bend follows its existing swing without changing reach,
				# skeleton length, foot contact or any translation track.
				var flex := deg_to_rad(8.0 + 1.5 * cos(phase * TAU * 2.0))
				value = (value * Quaternion(Vector3.RIGHT, flex)).normalized()
			elif running and bone.begins_with("hand_") and neutral.has(bone):
				# Dampen the source's wrist flap. The held-weapon modifier still
				# aims equipped wrists after this ordinary animation is evaluated.
				value = value.slerp(neutral[bone], 0.7).normalized()
			result.track_set_key_value(track, index, value)
	return result
