extends RefCounted
## Local presentation aliases for the current humanoid library. They never
## invoke the gameplay death action, alter health, or decide a rescue outcome.
const NAMESPACE := &"cinematic_injury"
const RECOIL_CLIP := &"Hit_Knockback"
const HOLD_SECONDS := 0.55
const ACTIONS := [&"injury_recoil", &"injury_pinned", &"injury_standing", &"injury_recover"]
const CLIPS := {&"injury_recoil":RECOIL_CLIP, &"injury_pinned":RECOIL_CLIP,
	&"injury_standing":&"Idle_Hurt", &"injury_recover":&"LayToIdle"}

var action: StringName = &""
var elapsed := 0.0
var held := false
var _player: AnimationPlayer
var _callback_mode := AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
var _speed := 1.0

static func accepts(value: StringName) -> bool:
	return value in ACTIONS

func play(actor: Node3D, value: StringName, restart := false) -> bool:
	if not accepts(value) or not actor.get("_cinematic_active") or actor.get("current_action") == &"death":
		return false
	var player := actor.get("animation_player") as AnimationPlayer
	if player == null or not _install(actor, player):
		return false
	if _player != player:
		clear()
		_player = player
	if action == value and not restart:
		return true # A repeated held cue must not resume/restart the knockdown.
	if action == &"":
		_callback_mode = player.callback_mode_process
		_speed = player.speed_scale
	action = value
	elapsed = 0.0
	held = false
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.speed_scale = 1.0
	var clip := StringName(str(NAMESPACE)+"/"+str(CLIPS[value]))
	if value == &"injury_pinned":
		elapsed = minf(HOLD_SECONDS, player.get_animation(clip).length - 0.001)
		_hold_exact(clip, elapsed)
	else:
		player.play(clip, 0.12)
		player.seek(0.0, true)
		player.advance(0.0)
	return true

func _hold_exact(clip: StringName, time: float) -> void:
	# A seek alone retains an unfinished idle-to-fall crossfade. Rapid text
	# progression could then pause a blended airborne pose forever. Drop that
	# playback history while preserving the displayed bones, and evaluate the
	# exact held clip synchronously before the next frame can be rendered.
	_player.stop(true)
	_player.play(clip, 0.0)
	_player.seek(time, true)
	_player.advance(0.0)
	_player.pause()
	held = true

func advance(delta: float) -> void:
	if not is_instance_valid(_player) or action == &"" or held:
		return
	var amount := maxf(0.0, delta)
	if action == &"injury_recoil":
		amount = minf(amount, maxf(0.0, HOLD_SECONDS - elapsed))
		elapsed += amount
		_player.advance(amount)
		if elapsed >= HOLD_SECONDS - 0.00001:
			_hold_exact(StringName(str(NAMESPACE)+"/"+str(RECOIL_CLIP)), HOLD_SECONDS)
	elif action == &"injury_recover":
		var length := _player.get_animation(StringName(str(NAMESPACE)+"/LayToIdle")).length
		amount = minf(amount, maxf(0.0, length - elapsed))
		elapsed += amount
		_player.advance(amount)
		if elapsed >= length - 0.00001:
			_player.pause()
			held = true
	else:
		elapsed += amount
		_player.advance(amount)

func clear() -> void:
	if is_instance_valid(_player) and action != &"":
		_player.callback_mode_process = _callback_mode
		_player.speed_scale = _speed
	# The caller starts the next normal action, retaining the current pose as
	# its crossfade source. No RESET/stop or gameplay-state transition occurs.
	action = &""
	elapsed = 0.0
	held = false
	_player = null

func _install(actor: Node3D, player: AnimationPlayer) -> bool:
	if player.has_animation_library(NAMESPACE):
		return true
	var config: Dictionary = actor.get("_model_config")
	var skeleton := actor.get("_native_skeleton") as Skeleton3D
	if skeleton == null or not config.has("culture"):
		return false
	var path: String = actor.call("_external_path", str(config.get("animationLibrary", "")))
	if not path.ends_with("Universal_Animation_Library.glb"):
		return false
	# Lazy import affects only a humanoid explicitly given an injury cue. The
	# approved source mesh/rig/clips and ordinary action maps remain unchanged.
	var result := NativeAnimationImporter.import_library(actor, path, skeleton,
		config.get("boneAliases", {}), PackedStringArray(["Hit_Knockback","Idle_Hurt","LayToIdle"]),
		PackedStringArray(["Idle_Hurt"]))
	var extra := result.get("player") as AnimationPlayer
	if extra == null:
		return false
	if not (result.get("errors", PackedStringArray()) as PackedStringArray).is_empty():
		extra.free()
		return false
	var library := extra.get_animation_library(&"")
	if library == null:
		extra.free()
		return false
	player.add_animation_library(NAMESPACE, library)
	extra.free()
	return true
