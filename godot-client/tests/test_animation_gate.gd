extends SceneTree
## The animation gate: bodies the camera cannot see are paused, far ones step
## every other frame at the same speed, near ones are untouched, and an actor
## caught in a one-shot clip is left to finish it.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.current = true
	camera.look_at_from_position(Vector3(0.0, 20.0, 26.0), Vector3.ZERO, Vector3.UP)
	await process_frame

	var gate := AnimationGate.new()
	gate.begin(camera)
	_expect(gate.classify(Vector3(0.0, 1.0, 0.0), 2.0) == AnimationGate.Tier.FULL,
		"a body in front of the camera animates at full rate")
	_expect(gate.classify(Vector3(0.0, 1.0, -40.0), 2.0) == AnimationGate.Tier.HALF,
		"a body in view but far from the camera animates at half rate")
	_expect(gate.classify(Vector3(0.0, 1.0, 60.0), 2.0) == AnimationGate.Tier.PAUSED,
		"a body behind the camera is paused")
	_expect(gate.classify(Vector3(200.0, 1.0, 0.0), 2.0) == AnimationGate.Tier.PAUSED,
		"a body off to the side is paused")
	var blind := AnimationGate.new()
	blind.begin(null)
	_expect(blind.classify(Vector3(0.0, 1.0, 60.0), 2.0) == AnimationGate.Tier.FULL,
		"without a camera nothing is gated")

	var holder := Node3D.new()
	root.add_child(holder)
	var player := _player_with_clip(holder, "slide", 2.0, Animation.LOOP_LINEAR)
	player.play("slide")
	gate.apply(player, AnimationGate.Tier.HALF)
	_expect(player.active
		and player.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL,
		"half rate takes the player manual and leaves it running")
	_expect(gate.half_rate_count() == 1, "the half-rate player is tracked")
	var before: float = player.current_animation_position
	gate.advance(0.1)
	_expect(is_equal_approx(player.current_animation_position, before),
		"the first of two frames only accumulates")
	gate.advance(0.1)
	_expect(is_equal_approx(player.current_animation_position, before + 0.2),
		"the second frame advances by the time both frames covered")
	gate.apply(player, AnimationGate.Tier.PAUSED)
	_expect(not player.active and gate.half_rate_count() == 0, "paused stops the player")
	gate.apply(player, AnimationGate.Tier.FULL)
	_expect(player.active
		and player.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE,
		"full rate hands the player back to idle processing")
	gate.apply(player, AnimationGate.Tier.HALF)
	holder.queue_free()
	await process_frame
	gate.advance(0.1)
	gate.advance(0.1)
	_expect(gate.half_rate_count() == 0, "a freed player drops out of the half-rate set")

	# An actor mid-way through a clip that does not loop keeps playing it.
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var one_shot := _player_with_clip(actor, "sit", 1.0, Animation.LOOP_NONE)
	one_shot.play("sit")
	actor.animation_player = one_shot
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_expect(one_shot.active and actor.animation_tier() == AnimationGate.Tier.FULL,
		"a one-shot clip is played out rather than paused")
	one_shot.get_animation("sit").loop_mode = Animation.LOOP_LINEAR
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_expect(not one_shot.active and actor.animation_tier() == AnimationGate.Tier.PAUSED,
		"a looping clip pauses")
	actor.set_animation_tier(AnimationGate.Tier.FULL, gate)
	_expect(one_shot.active, "coming back into view resumes the actor")
	actor.queue_free()

	print("animation gate tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	await process_frame
	quit(failures)

func _player_with_clip(parent: Node, clip_name: String, length: float,
		loop_mode: Animation.LoopMode) -> AnimationPlayer:
	var player := AnimationPlayer.new()
	parent.add_child(player)
	var animation := Animation.new()
	animation.length = length
	animation.loop_mode = loop_mode
	var track: int = animation.add_track(Animation.TYPE_VALUE)
	animation.track_set_path(track, NodePath("..:position"))
	animation.track_insert_key(track, 0.0, Vector3.ZERO)
	animation.track_insert_key(track, length, Vector3(length, 0.0, 0.0))
	var library := AnimationLibrary.new()
	library.add_animation(clip_name, animation)
	player.add_animation_library("", library)
	return player

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
