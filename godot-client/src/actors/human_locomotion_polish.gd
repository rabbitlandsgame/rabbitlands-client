class_name HumanLocomotionPolish
extends RefCounted
## Human-only, immutable derivatives of the imported travel clips. The source
## library, body/skin/rest pose, root, torso and lower-body channels stay exact.
## Runtime playback uses ordinary cached Animation resources at every quality.

const SOURCE_META := &"human_locomotion_source"
const RESULT_META := &"human_locomotion_result"
const CACHE_LIMIT := 8
const CLIPS: Array[StringName] = [&"Walk", &"Run_Female"]
const ARM_BONES := ["clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
	"lowerarm_l", "lowerarm_r", "hand_l", "hand_r"]
static var _libraries: Dictionary = {}

static func supports(model: Dictionary) -> bool:
	return str(model.get("culture", "")) == "luminous" and str(model.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func clear() -> void:
	_libraries.clear()

static func install(player: AnimationPlayer, model: Dictionary) -> void:
	if player == null or not supports(model) or not player.has_animation_library(&""):
		return
	var current := player.get_animation_library(&"")
	var source := current
	if player.has_meta(RESULT_META) and current == player.get_meta(RESULT_META):
		source = player.get_meta(SOURCE_META) as AnimationLibrary
	var result := derive(source)
	if result == current:
		return
	player.set_meta(SOURCE_META, source)
	player.set_meta(RESULT_META, result)
	player.remove_animation_library(&"")
	player.add_animation_library(&"", result)

static func derive(source: AnimationLibrary) -> AnimationLibrary:
	if source == null:
		return null
	var key := source.get_instance_id()
	if _libraries.has(key):
		return _libraries[key].result as AnimationLibrary
	var result := AnimationLibrary.new()
	var walk: Animation = source.get_animation(&"Walk") if source.has_animation(&"Walk") else null
	var neutral := _walking_hands(walk)
	for name: StringName in source.get_animation_list():
		var animation := source.get_animation(name)
		# Sharing these resources is intentional: attacks, casts, RESET and all
		# remaining actions retain their exact original keys and hit timings.
		result.add_animation(name, _travel(animation, name == &"Run_Female", neutral) if name in CLIPS else animation)
	if _libraries.size() >= CACHE_LIMIT:
		_libraries.erase(_libraries.keys()[0])
	# Keep the source strongly referenced alongside its derivative so a freed
	# source's instance ID cannot be reused as a different library's cache key.
	_libraries[key] = {"source": source, "result": result}
	return result

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
