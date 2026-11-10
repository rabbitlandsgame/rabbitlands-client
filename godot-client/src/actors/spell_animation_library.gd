class_name SpellAnimationLibrary
extends RefCounted
## Sculpt variants from each rig's own casting clips, preserving its rest pose,
## foot placement and hand release timing. Installed once per actor instance.
const PROFILES := {
	"fire": [2, 0.18, -0.10], "frost": [84, -0.12, 0.16],
	"magic": [83, 0.08, 0.08], "radiation": [85, 0.20, 0.20],
	"poison": [0, -0.20, 0.10], "drain": [86, -0.14, -0.18],
	"ether": [10, -0.12, -0.22], "dispel": [79, 0.16, 0.16],
	"transmute": [19, -0.24, 0.24], "recall": [18, 0.26, 0.26],
	"ward": [75, 0.12, 0.12]}

## `source_library` is the actor's full-hands library (LAT-L1,
## CrowdAnimationLibrary.full_library): a body that currently plays the
## fingerless crowd variant still sculpts from the full clip, so its variants
## keep their finger tracks for when it comes close. Without it, or for a clip
## it does not hold, the player's own clip is read, exactly as before.
static func install(player: AnimationPlayer, resolver: RefCounted,
		source_library: AnimationLibrary = null) -> Dictionary:
	var result: Dictionary = {}
	var library := AnimationLibrary.new()
	for profile: String in PROFILES:
		var values: Array = PROFILES[profile]
		var action := SpellPresentation.action_for_effect(int(values[0]))
		var base_name: String = resolver.clip_for_action(action)
		var base := _base_clip(player, base_name, source_library)
		if base == null: continue
		var clip := base.duplicate(true) as Animation
		for track: int in clip.get_track_count():
			if clip.track_get_type(track) != Animation.TYPE_ROTATION_3D: continue
			var bone := str(clip.track_get_path(track)).to_lower()
			var left := bone.ends_with("arm_l") or bone.ends_with("forearm_l") or bone.ends_with("hand_l")
			var right := bone.ends_with("arm_r") or bone.ends_with("forearm_r") or bone.ends_with("hand_r")
			if not left and not right: continue
			for key: int in clip.track_get_key_count(track):
				var phase := clip.track_get_key_time(track, key) / maxf(clip.length, 0.01)
				var envelope := sin(clampf(phase, 0.0, 1.0) * PI)
				var twist := float(values[1 if left else 2]) * envelope
				var rotation: Quaternion = clip.track_get_key_value(track, key)
				clip.track_set_key_value(track, key, rotation * Quaternion(Vector3.UP, twist))
		library.add_animation(profile, clip)
		result[int(values[0])] = "spell_variants/" + profile
	if not player.has_animation_library("spell_variants"):
		player.add_animation_library("spell_variants", library)
	return result

static func _base_clip(player: AnimationPlayer, base_name: String,
		source_library: AnimationLibrary) -> Animation:
	if base_name.is_empty():
		return null
	if source_library != null and source_library.has_animation(base_name):
		return source_library.get_animation(base_name)
	return player.get_animation(base_name) if player.has_animation(base_name) else null

## Instance-local variants: retain the seated support pose and the donor's
## release clock. No mesh, bind, source clip or shared library is modified.
static func presentation_clip(player: AnimationPlayer, skeleton: Skeleton3D,
		base_name: String, seat_name: String, high: bool) -> String:
	if seat_name.is_empty() and not high:
		return base_name
	# Actors without a skeleton (or a missing source clip) keep the plain clip.
	if skeleton == null or not player.has_animation(base_name):
		return base_name
	var key := base_name.replace("/", "_") + ("_seated" if not seat_name.is_empty() else "") + ("_high" if high else "")
	if not player.has_animation_library("spell_poses"):
		player.add_animation_library("spell_poses", AnimationLibrary.new())
	var library := player.get_animation_library("spell_poses")
	if library.has_animation(key):
		return "spell_poses/" + key
	var source := player.get_animation(base_name)
	var clip := source.duplicate(true) as Animation
	var spine := skeleton.find_bone("spine_01")
	if spine < 0: return base_name
	var upper: Array[String] = []
	for bone: int in skeleton.get_bone_count():
		var ancestor := bone
		while ancestor >= 0 and ancestor != spine:
			ancestor = skeleton.get_bone_parent(ancestor)
		if ancestor == spine: upper.append(skeleton.get_bone_name(bone))
	if not seat_name.is_empty() and player.has_animation(seat_name):
		var seat := player.get_animation(seat_name)
		# Replace all support channels, including root translation and scale.
		for track: int in range(clip.get_track_count() - 1, -1, -1):
			if clip.track_get_type(track) in [Animation.TYPE_ROTATION_3D, Animation.TYPE_POSITION_3D, Animation.TYPE_SCALE_3D] and str(clip.track_get_path(track).get_concatenated_subnames()) not in upper:
				clip.remove_track(track)
		for track: int in seat.get_track_count():
			if seat.track_get_type(track) not in [Animation.TYPE_ROTATION_3D, Animation.TYPE_POSITION_3D, Animation.TYPE_SCALE_3D]: continue
			if str(seat.track_get_path(track).get_concatenated_subnames()) in upper: continue
			seat.copy_track(track, clip)
			var added := clip.get_track_count() - 1
			# Meditate is a loop. Keep its breathing over a one-shot's duration.
			var keys := clip.track_get_key_count(added)
			for key_index: int in range(keys - 1, -1, -1):
				clip.track_remove_key(added, key_index)
			var samples := ceili(clip.length * 30.0)
			for sample: int in range(samples + 1):
				var time := minf(sample / 30.0, clip.length)
				var phase := time * seat.length / clip.length if clip.loop_mode != Animation.LOOP_NONE else fposmod(time, seat.length)
				match seat.track_get_type(track):
					Animation.TYPE_ROTATION_3D: clip.rotation_track_insert_key(added, time, seat.rotation_track_interpolate(track, phase))
					Animation.TYPE_POSITION_3D: clip.position_track_insert_key(added, time, seat.position_track_interpolate(track, phase))
					Animation.TYPE_SCALE_3D: clip.scale_track_insert_key(added, time, seat.scale_track_interpolate(track, phase))
					_: pass
	if high:
		for track: int in clip.get_track_count():
			if clip.track_get_type(track) != Animation.TYPE_ROTATION_3D: continue
			var bone := str(clip.track_get_path(track).get_concatenated_subnames())
			if bone not in ["arm_l", "arm_r", "forearm_l", "forearm_r"]: continue
			for key_index: int in clip.track_get_key_count(track):
				var rotation: Quaternion = clip.track_get_key_value(track, key_index)
				# Broader gestures retain endpoints and release timing.
				var phase := clip.track_get_key_time(track, key_index) / maxf(clip.length, 0.01)
				var envelope := pow(sin(phase * PI), 2.0)
				var side := 1.0 if bone.ends_with("_l") else -1.0
				clip.track_set_key_value(track, key_index, rotation * Quaternion(Vector3.FORWARD, side * 0.16 * envelope))
	library.add_animation(key, clip)
	return "spell_poses/" + key
