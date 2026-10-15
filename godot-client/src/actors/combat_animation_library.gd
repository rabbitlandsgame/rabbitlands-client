class_name CombatAnimationLibrary
extends RefCounted
## Authored timing curves over the shared rig's poses. Keeping these recipes
## separate preserves the source GLB and lets every race share immutable clips.
## Each segment is [source clip, seconds, source start fraction, end fraction].
const RECIPES := {
	"Combat_Channel_Enter": [["Spell_Simple_Enter", 0.48, 0.0, 1.0]],
	"Combat_Channel": [["Spell_Simple_Idle", 2.4, 0.0, 1.0]],
	"Combat_Cast_Aggressive": [["Spell_Simple_Enter", 0.25, 0.35, 1.0],
		["Two-hand_Blast", 0.20, 0.0, 0.28], ["Two-hand_Blast", 0.12, 0.28, 0.72],
		["Two-hand_Blast", 0.32, 0.72, 1.0], ["Spell_Simple_Exit", 0.34, 0.0, 1.0]],
	"Combat_Cast_Defensive": [["Defend", 0.24, 0.0, 0.36],
		["Defend", 0.50, 0.36, 0.64], ["Defend", 0.38, 0.64, 1.0]],
	"Combat_Heal": [["Spell_Simple_Enter", 0.48, 0.0, 1.0],
		["Spell_Simple_Idle", 0.85, 0.0, 0.5], ["Spell_Simple_Exit", 0.45, 0.0, 1.0]],
	"Combat_Slash_A": [["Sword_Regular_A", 0.22, 0.0, 0.40],
		["Sword_Regular_A", 0.12, 0.40, 0.82], ["Sword_Regular_A", 0.10, 0.82, 1.0],
		["Sword_Regular_A_Rec", 0.38, 0.0, 1.0]],
	"Combat_Slash_B": [["Sword_Regular_B", 0.24, 0.0, 0.42],
		["Sword_Regular_B", 0.14, 0.42, 0.82], ["Sword_Regular_B", 0.10, 0.82, 1.0],
		["Sword_Regular_B_Rec", 0.38, 0.0, 1.0]],
	"Combat_Bow_Draw": [["Bow_Pull_Back", 0.18, 0.0, 0.24],
		["Bow_Pull_Back", 0.42, 0.24, 1.0]],
	"Combat_Bow_Hold": [["Bow_Pull_Hold", 0.8, 0.0, 1.0]],
	"Combat_Bow_Release": [["Bow_Release", 0.08, 0.0, 0.32],
		["Bow_Release", 0.36, 0.32, 1.0]]}
const LOOPS := ["Combat_Channel", "Combat_Bow_Hold"]

static func source_clips(wanted: PackedStringArray) -> PackedStringArray:
	var sources := wanted.duplicate()
	for name: String in RECIPES:
		if not wanted.is_empty() and not wanted.has(name):
			continue
		for segment: Array in RECIPES[name]:
			if not sources.has(segment[0]):
				sources.append(segment[0])
	return sources

static func install(library: AnimationLibrary, wanted: PackedStringArray) -> void:
	for name: String in RECIPES:
		if not wanted.is_empty() and not wanted.has(name):
			continue
		var recipe: Array = RECIPES[name]
		var complete := true
		for segment: Array in recipe:
			complete = complete and library.has_animation(segment[0])
		if not complete:
			continue
		var first: Animation = library.get_animation(recipe[0][0])
		var clip := Animation.new()
		clip.length = 0.0
		for segment: Array in recipe:
			clip.length += float(segment[1])
		clip.loop_mode = Animation.LOOP_LINEAR if name in LOOPS else Animation.LOOP_NONE
		for track: int in first.get_track_count():
			var type: Animation.TrackType = first.track_get_type(track)
			if type not in [Animation.TYPE_POSITION_3D, Animation.TYPE_ROTATION_3D, Animation.TYPE_SCALE_3D]:
				continue
			var path: NodePath = first.track_get_path(track)
			var output: int = clip.add_track(type)
			clip.track_set_path(output, path)
			var cursor := 0.0
			var previous: Variant = null
			for segment: Array in recipe:
				var source: Animation = library.get_animation(segment[0])
				var source_track: int = source.find_track(path, type)
				if source_track < 0:
					continue
				var duration: float = segment[1]
				var frames: int = maxi(2, ceili(duration * 60.0))
				var start_value: Variant = previous
				for frame: int in range(frames + 1):
					var fraction: float = float(frame) / frames
					var sample_time: float = lerpf(segment[2], segment[3], fraction) * source.length
					var value: Variant
					match type:
						Animation.TYPE_ROTATION_3D: value = source.rotation_track_interpolate(source_track, sample_time)
						Animation.TYPE_POSITION_3D: value = source.position_track_interpolate(source_track, sample_time)
						_: value = source.scale_track_interpolate(source_track, sample_time)
					# Brief continuity blend when adjacent source clips have different poses.
					if start_value != null and fraction * duration < 0.08:
						var weight: float = smoothstep(0.0, 0.08, fraction * duration)
						value = start_value.slerp(value, weight) if type == Animation.TYPE_ROTATION_3D else start_value.lerp(value, weight)
					clip.track_insert_key(output, cursor + fraction * duration, value)
					previous = value
				cursor += duration
		library.add_animation(name, clip)
