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
