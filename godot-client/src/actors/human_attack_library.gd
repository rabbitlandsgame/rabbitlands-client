class_name HumanAttackLibrary
extends RefCounted
## Human-only single cuts built from one coherent interval of the imported
## sword stroke. The old complete combinations remain exact flurry aliases.
## No damage is scheduled here: contact markers describe presentation only.

const CACHE_LIMIT := 8
const DURATION := 1.06
const WINDUP_END := 0.24
const CONTACT := 0.35
const STRIKE_END := 0.44
const FOLLOWTHROUGH_END := 0.52
const SOURCE_BEGIN := 0.12
const SOURCE_CONTACT := 0.44
const SOURCE_END := 0.64
const SOURCE_FOLLOW := 0.68
const SAMPLE_RATE := 60.0
const SOURCE_STROKE := &"Sword_Regular_B"
const GUARD := &"Fighting_Idle"
const COMBAT_GUARD := &"Human_Combat_Guard"
const SHIELD_CLEARANCE_DEGREES := 12.0
const TRANSFER_CLEARANCE_DEGREES := 20.0
const TORSO := ["spine_01", "spine_02", "spine_03"]
const ARM := ["clavicle_r", "upperarm_r", "lowerarm_r", "hand_r"]
const RIGHT: Array[StringName] = [&"Human_Cut_R_Forehand", &"Human_Cut_R_Backhand"]
const LEFT: Array[StringName] = [&"Human_Cut_L_Forehand", &"Human_Cut_L_Backhand"]
const FLURRIES: Array[StringName] = [&"Human_Flurry_A", &"Human_Flurry_B"]
static var _cache: Dictionary = {}

static func supports(model: Dictionary) -> bool:
	return str(model.get("culture", "")) == "luminous" and str(model.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func normal_clips(hand := "r") -> PackedStringArray:
	return PackedStringArray(LEFT if hand == "l" else RIGHT)

static func flurry_clips() -> PackedStringArray:
	return PackedStringArray(FLURRIES)

static func guard_clip() -> StringName:
	return COMBAT_GUARD

static func clear() -> void:
	_cache.clear()

static func append(result: AnimationLibrary, source: AnimationLibrary,
		model: Dictionary, skeleton: Skeleton3D) -> void:
	if result == null or source == null or skeleton == null or not supports(model):
		return
	if not source.has_animation(SOURCE_STROKE) or not result.has_animation(GUARD):
		return
	var guard := result.get_animation(GUARD)
	var key := "%s:%s:%s" % [source.get_instance_id(), guard.get_instance_id(), str(model.get("bodyTemplate", ""))]
	if not _cache.has(key):
		var clips: Dictionary = {}
		var fitted_guard := _guard(guard, skeleton)
		clips[COMBAT_GUARD] = fitted_guard
		for side: String in ["r", "l"]:
			for backhand: bool in [false, true]:
				var name: StringName = normal_clips(side)[1 if backhand else 0]
				clips[name] = _cut(fitted_guard, source.get_animation(SOURCE_STROKE), skeleton, side, backhand)
		if _cache.size() >= CACHE_LIMIT:
			_cache.erase(_cache.keys()[0])
		# Retain source/guard so instance IDs cannot alias a later library.
		_cache[key] = {"source": source, "guard": guard, "clips": clips}
	for name: StringName in _cache[key].clips:
		if result.has_animation(name):
			result.remove_animation(name)
		result.add_animation(name, _cache[key].clips[name])
	for index: int in 2:
		var old: StringName = &"Combat_Slash_A" if index == 0 else &"Combat_Slash_B"
		if source.has_animation(old):
			if result.has_animation(FLURRIES[index]):
				result.remove_animation(FLURRIES[index])
			result.add_animation(FLURRIES[index], source.get_animation(old))

static func _rotation_tracks(animation: Animation) -> Dictionary:
	var tracks: Dictionary = {}
	for track: int in animation.get_track_count():
		if animation.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			tracks[str(animation.track_get_path(track).get_concatenated_subnames())] = track
	return tracks

static func _guard(source: Animation, skeleton: Skeleton3D) -> Animation:
	var rotations := _rotation_tracks(source)
	var globals: Array[Transform3D] = []
	for bone: int in skeleton.get_bone_count():
		var name := str(skeleton.get_bone_name(bone))
		var rest := skeleton.get_bone_rest(bone)
		var rotation := _sample(source, rotations, name, 0.0, rest.basis.get_rotation_quaternion())
		var path := NodePath(str(source.track_get_path(0)).get_slice(":", 0) + ":" + name)
		var position_track := source.find_track(path, Animation.TYPE_POSITION_3D)
		var scale_track := source.find_track(path, Animation.TYPE_SCALE_3D)
		var position := source.position_track_interpolate(position_track, 0.0) if position_track >= 0 else rest.origin
		var size := source.scale_track_interpolate(scale_track, 0.0) if scale_track >= 0 else rest.basis.get_scale()
		var local := Transform3D(Basis(rotation).scaled(size), position)
		var parent := skeleton.get_bone_parent(bone)
		globals.append(globals[parent] * local if parent >= 0 else local)
	var upper := skeleton.find_bone("upperarm_l")
	var hand := skeleton.find_bone("hand_l")
	var across := skeleton.find_bone("upperarm_r")
	var out := globals[upper].origin - globals[across].origin
	out.y = 0.0
	var axis := (globals[hand].origin - globals[upper].origin).cross(out).normalized()
	var parent := skeleton.get_bone_parent(upper)
	var parent_basis := globals[parent].basis.orthonormalized()
	var delta := (parent_basis.inverse() * Basis(axis, deg_to_rad(SHIELD_CLEARANCE_DEGREES)) * parent_basis).get_rotation_quaternion()
	var result := Animation.new()
	result.length = source.length
	result.loop_mode = source.loop_mode
	result.step = source.step
	for track: int in source.get_track_count():
		source.copy_track(track, result)
		if track == int(rotations.get("upperarm_l", -1)):
			for key: int in result.track_get_key_count(track):
				var value: Quaternion = source.track_get_key_value(track, key)
				result.track_set_key_value(track, key, (delta * value).normalized())
	for marker: StringName in source.get_marker_names():
		result.add_marker(marker, source.get_marker_time(marker))
		result.set_marker_color(marker, source.get_marker_color(marker))
	result.set_meta(&"human_combat_guard", true)
	result.set_meta(&"shield_clearance_degrees", SHIELD_CLEARANCE_DEGREES)
	return result

static func _sample(animation: Animation, tracks: Dictionary, name: String,
		time: float, fallback: Quaternion) -> Quaternion:
	return animation.rotation_track_interpolate(tracks[name], time).normalized() if tracks.has(name) else fallback

static func _opposite(name: String) -> String:
	return name.trim_suffix("_r") + "_l" if name.ends_with("_r") else name

static func _mirror(basis: Basis) -> Basis:
	var reflection := Basis(Vector3(-1, 0, 0), Vector3.UP, Vector3.BACK)
	return reflection * basis * reflection

static func _source_fraction(time: float, backhand: bool) -> float:
	var begin := SOURCE_END if backhand else SOURCE_BEGIN
	var end := SOURCE_BEGIN if backhand else SOURCE_END
	if time <= CONTACT:
		return lerpf(begin, SOURCE_CONTACT, clampf((time - WINDUP_END) / (CONTACT - WINDUP_END), 0.0, 1.0))
	if time <= STRIKE_END:
		return lerpf(SOURCE_CONTACT, end, (time - CONTACT) / (STRIKE_END - CONTACT))
	return lerpf(end, SOURCE_BEGIN if backhand else SOURCE_FOLLOW,
		clampf((time - STRIKE_END) / (FOLLOWTHROUGH_END - STRIKE_END), 0.0, 1.0))

static func _transfer_weight(time: float, backhand: bool) -> float:
	# Route the blade past the shield while changing sides. The short active
	# stroke still passes through the original contact pose at CONTACT.
	if backhand:
		return smoothstep(CONTACT, 0.385, time) * (1.0 - smoothstep(0.8, DURATION, time))
	return smoothstep(0.0, 0.08, time) * (1.0 - smoothstep(0.315, CONTACT, time))

static func _cut(guard: Animation, stroke: Animation, skeleton: Skeleton3D,
		side: String, backhand: bool) -> Animation:
	var guard_tracks := _rotation_tracks(guard)
	var stroke_tracks := _rotation_tracks(stroke)
	var base: Array[Quaternion] = []
	var base_global: Array[Basis] = []
	var rest_global: Array[Basis] = []
	for bone: int in skeleton.get_bone_count():
		var name := str(skeleton.get_bone_name(bone))
		var rotation := _sample(guard, guard_tracks, name, 0.0,
			skeleton.get_bone_rest(bone).basis.get_rotation_quaternion())
		base.append(rotation)
		var parent := skeleton.get_bone_parent(bone)
		base_global.append(base_global[parent] * Basis(rotation) if parent >= 0 else Basis(rotation))
		rest_global.append(skeleton.get_bone_global_rest(bone).basis.orthonormalized())
	var frames: Array[Array] = []
	var count := ceili(DURATION * SAMPLE_RATE)
	var times := PackedFloat64Array()
	for frame: int in range(count + 1):
		times.append(DURATION * frame / count)
	# Keep the unchanged contact pose on an exact key, including when the
	# uniform sample cadence would otherwise interpolate a transfer offset.
	times.append(CONTACT)
	times.sort()
	for time: float in times:
		var sample_time := _source_fraction(time, backhand) * stroke.length
		var envelope := smoothstep(0.0, WINDUP_END, time) if time < WINDUP_END else (1.0 - smoothstep(FOLLOWTHROUGH_END, DURATION, time))
		var rotations := base.duplicate()
		for name: String in ARM + TORSO:
			var bone := skeleton.find_bone(name)
			if bone < 0:
				continue
			var target := _sample(stroke, stroke_tracks, name, sample_time, base[bone])
			if name in TORSO:
				# The cut turns above a stable pelvis and planted feet. Preserve the
				# guard and use only a restrained source torso rotation delta.
				var reference := _sample(stroke, stroke_tracks, name, SOURCE_BEGIN * stroke.length, base[bone])
				target = (base[bone] * Quaternion.IDENTITY.slerp(reference.inverse() * target, 0.45)).normalized()
			rotations[bone] = base[bone].slerp(target, envelope).normalized()
		var transfer := _transfer_weight(time, backhand)
		if transfer > 0.0:
			var upper := skeleton.find_bone("upperarm_r")
			var ancestor := skeleton.get_bone_parent(upper)
			var parent_basis := Basis.IDENTITY
			while ancestor >= 0:
				parent_basis = Basis(rotations[ancestor]) * parent_basis
				ancestor = skeleton.get_bone_parent(ancestor)
			# Native +Z is the player's forward axis. Conjugating into the
			# posed parent's axes gives a bounded shoulder swing without
			# changing rests, limb lengths, wrist grip or the shield arm.
			var swing := Basis(Vector3.BACK, deg_to_rad(TRANSFER_CLEARANCE_DEGREES) * transfer)
			var delta := (parent_basis.inverse() * swing * parent_basis).get_rotation_quaternion()
			rotations[upper] = (delta * rotations[upper]).normalized()
		if side == "l":
			var right_global: Array[Basis] = []
			for bone: int in skeleton.get_bone_count():
				var parent := skeleton.get_bone_parent(bone)
				right_global.append(right_global[parent] * Basis(rotations[bone]) if parent >= 0 else Basis(rotations[bone]))
			rotations = base.duplicate()
			var left_global: Array[Basis] = []
			for bone: int in skeleton.get_bone_count():
				var name := str(skeleton.get_bone_name(bone))
				var parent := skeleton.get_bone_parent(bone)
				var from := skeleton.find_bone(name.trim_suffix("_l") + "_r") if name.ends_with("_l") else bone
				if name in TORSO or (name.ends_with("_l") and name.trim_suffix("_l") + "_r" in ARM):
					# The combat guard's wrists are asymmetric. Mirror the arm's
					# world-space motion relative to the actual native rest axes,
					# rather than retaining the opposite wrist's unrelated roll.
					var torso: bool = name in TORSO
					var reference: Basis = base_global[from] if torso else rest_global[from]
					var target_reference: Basis = base_global[bone] if torso else rest_global[bone]
					var wanted := _mirror(right_global[from] * reference.inverse()) * target_reference
					var local := ((left_global[parent].inverse() * wanted) if parent >= 0 else wanted).get_rotation_quaternion().normalized()
					rotations[bone] = local if torso else base[bone].slerp(local, envelope).normalized()
				left_global.append(left_global[parent] * Basis(rotations[bone]) if parent >= 0 else Basis(rotations[bone]))
		frames.append(rotations)
	var clip := Animation.new()
	clip.length = DURATION
	clip.loop_mode = Animation.LOOP_NONE
	clip.step = 1.0 / SAMPLE_RATE
	for track: int in guard.get_track_count():
		var type := guard.track_get_type(track)
		var name := str(guard.track_get_path(track).get_concatenated_subnames())
		var bone := skeleton.find_bone(name)
		var output := clip.add_track(type)
		clip.track_set_path(output, guard.track_get_path(track))
		clip.track_set_interpolation_type(output, Animation.INTERPOLATION_LINEAR)
		clip.track_set_interpolation_loop_wrap(output, false)
		var moving := type == Animation.TYPE_ROTATION_3D and bone >= 0 and (name in TORSO or name in (ARM if side == "r" else ARM.map(_opposite)))
		if moving:
			for frame: int in times.size():
				clip.rotation_track_insert_key(output, times[frame], frames[frame][bone])
		else:
			var value: Variant
			match type:
				Animation.TYPE_ROTATION_3D: value = guard.rotation_track_interpolate(track, 0.0)
				Animation.TYPE_POSITION_3D: value = guard.position_track_interpolate(track, 0.0)
				Animation.TYPE_SCALE_3D: value = guard.scale_track_interpolate(track, 0.0)
				Animation.TYPE_BLEND_SHAPE: value = guard.blend_shape_track_interpolate(track, 0.0)
				_: value = guard.track_get_key_value(track, 0) if guard.track_get_key_count(track) > 0 else 0.0
			clip.track_insert_key(output, 0.0, value)
			clip.track_insert_key(output, DURATION, value)
	for marker: StringName in [&"windup_end", &"contact", &"strike_end", &"recovery_end"]:
		clip.add_marker(marker, {&"windup_end": WINDUP_END, &"contact": CONTACT, &"strike_end": STRIKE_END, &"recovery_end": DURATION}[marker])
	clip.set_meta(&"human_single_cut", true)
	clip.set_meta(&"attack_hand", side)
	clip.set_meta(&"contact_seconds", CONTACT)
	clip.set_meta(&"active_window", Vector2(WINDUP_END, STRIKE_END))
	clip.set_meta(&"transfer_clearance_degrees", TRANSFER_CLEARANCE_DEGREES)
	return clip
