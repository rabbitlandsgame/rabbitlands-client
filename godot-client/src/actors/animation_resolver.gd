class_name AnimationResolver
extends RefCounted

var action_to_clip: Dictionary
var command_to_action: Dictionary
var playback_speeds: Dictionary
## Metres of ground each locomotion clip covers per second when it plays at
## speed 1.0, measured from its planted foot. The clips animate in place, so
## this is what tells an actor how fast to run one for its own travel speed.
var stride_speeds: Dictionary
## The clips that are cycles - travel, idles, dances - rather than one-shot
## transitions. glTF has no way to say a clip loops, so a runtime import
## leaves every clip one-shot; this list is where looping is stated. A walk
## left one-shot plays through once and freezes mid-stride until the next
## step packet restarts it.
var looping_clips: PackedStringArray
## Degrees of yaw to turn the body while an action plays, cancelling a clip
## whose authored pose faces off the rig's forward. The locomotion clips carry
## the pelvis about 23 degrees round, so a walk or run faces that far off its
## travel; this puts it back. Absent for poses meant to face off (a bladed
## combat idle, a lunge), which are left as authored.
var facing_offsets: Dictionary
## The actions a held weapon is carried at ease through rather than in the
## fist: the standing idle and the turn on the spot that plays it, and the
## idles and emotes that keep the hand hanging open where the idle has it - a
## nod, a reel, a yes. In those the fist's grip pointed the blade ahead like a
## lance (WeaponCarryPose). Absent from the map, the actions that play the
## fallback action's own clip.
var at_ease_actions: PackedStringArray
var fallback_action: StringName

func _init(config: Dictionary) -> void:
	action_to_clip = config.get("actions", {}).duplicate(true)
	command_to_action = config.get("serverCommands", {}).duplicate(true)
	playback_speeds = config.get("playbackSpeeds", {}).duplicate(true)
	stride_speeds = config.get("strideMetresPerSecond", {}).duplicate(true)
	looping_clips = PackedStringArray(config.get("loopingClips", []))
	facing_offsets = config.get("facingOffsets", {}).duplicate(true)
	fallback_action = StringName(config.get("fallbackAction", "idle"))
	if config.has("atEaseActions"):
		at_ease_actions = PackedStringArray(config.get("atEaseActions", []))
	else:
		var resting := clip_for_action(fallback_action)
		for action: Variant in action_to_clip:
			if StringName(str(action_to_clip[action])) == resting:
				at_ease_actions.append(str(action))

func action_for_command(command: int, combat_mode := false) -> StringName:
	var key := str(command)
	if command_to_action.has(key):
		return StringName(command_to_action[key])
	return &"combat_idle" if combat_mode and action_to_clip.has("combat_idle") else fallback_action

func clip_for_action(action: StringName) -> StringName:
	var value = action_to_clip.get(String(action), action_to_clip.get(String(fallback_action), ""))
	return StringName(value)

func playback_speed_for_action(action: StringName) -> float:
	return maxf(0.01, float(playback_speeds.get(String(action), 1.0)))

## Zero for actions that are not travel, which is the caller's signal to use
## the fixed playback speed instead.
func stride_speed_for_action(action: StringName) -> float:
	return maxf(0.0, float(stride_speeds.get(String(action), 0.0)))

func is_at_ease(action: StringName) -> bool:
	return at_ease_actions.has(String(action))

## Degrees to turn the body while this action plays, zero unless the action map
## names a correction for it.
func facing_offset_for_action(action: StringName) -> float:
	return float(facing_offsets.get(String(action), 0.0))

## Every clip this resolver can ever ask an AnimationPlayer to play. The native
## animation importer uses it to rebuild only the clips an actor needs instead
## of the whole shared library.
func required_clips() -> PackedStringArray:
	var clips := PackedStringArray()
	for action in action_to_clip:
		var clip := str(action_to_clip[action])
		if not clip.is_empty() and not clips.has(clip):
			clips.append(clip)
	return clips

func validate(available_clips: PackedStringArray) -> Array[String]:
	var missing: Array[String] = []
	for action in action_to_clip:
		var clip := str(action_to_clip[action])
		if clip.is_empty() or not available_clips.has(clip):
			missing.append(str(action) + " -> " + clip)
	return missing
