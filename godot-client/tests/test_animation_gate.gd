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

	# Half-rate bodies take turns: two players are stepped on alternate
	# frames, each by the time its two frames covered.
	var turns := AnimationGate.new()
	var pair := Node3D.new()
	root.add_child(pair)
	var first := _player_with_clip(pair, "slide", 2.0, Animation.LOOP_LINEAR)
	var second := _player_with_clip(pair, "slide", 2.0, Animation.LOOP_LINEAR)
	first.play("slide")
	second.play("slide")
	turns.apply(first, AnimationGate.Tier.HALF)
	turns.apply(second, AnimationGate.Tier.HALF)
	_expect(turns.group_sizes(AnimationGate.Tier.HALF) == [1, 1],
		"two half-rate players go to different groups")
	var start_first: float = first.current_animation_position
	var start_second: float = second.current_animation_position
	turns.advance(0.1)
	_expect(is_equal_approx(first.current_animation_position, start_first)
		and is_equal_approx(second.current_animation_position, start_second + 0.1),
		"on the first frame only the second group is stepped")
	turns.advance(0.1)
	_expect(is_equal_approx(first.current_animation_position, start_first + 0.2)
		and is_equal_approx(second.current_animation_position, start_second + 0.1),
		"on the next frame only the first, by both frames")
	turns.advance(0.1)
	_expect(is_equal_approx(second.current_animation_position, start_second + 0.3),
		"each group keeps its own clock")
	turns.apply(second, AnimationGate.Tier.HALF)
	_expect(turns.group_sizes(AnimationGate.Tier.HALF) == [1, 1],
		"re-applying the tier keeps a player in its group")
	turns.apply(second, AnimationGate.Tier.QUARTER)
	_expect(turns.half_rate_count() == 1 and turns.quarter_rate_count() == 1,
		"a player moves between the stepped tiers")
	turns.reset()
	_expect(turns.half_rate_count() == 0 and turns.quarter_rate_count() == 0
		and first.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE,
		"reset hands every stepped player back to idle processing")

	# Quarter rate: four groups, each stepped every fourth frame by all four.
	var quarters: Array[AnimationPlayer] = []
	for index: int in 4:
		var player_q := _player_with_clip(pair, "slide", 2.0, Animation.LOOP_LINEAR)
		player_q.play("slide")
		turns.apply(player_q, AnimationGate.Tier.QUARTER)
		quarters.append(player_q)
	_expect(turns.group_sizes(AnimationGate.Tier.QUARTER) == [1, 1, 1, 1],
		"four quarter-rate players fill the four groups")
	var stepped := 0
	for frame: int in 4:
		var before_q: Array[float] = []
		for player_q: AnimationPlayer in quarters:
			before_q.append(player_q.current_animation_position)
		turns.advance(0.05)
		for index: int in 4:
			if not is_equal_approx(quarters[index].current_animation_position, before_q[index]):
				stepped += 1
	_expect(stepped == 4, "one quarter-rate group is stepped a frame (%d steps in 4 frames)" % stepped)
	var settled: Array[float] = []
	for player_q: AnimationPlayer in quarters:
		settled.append(player_q.current_animation_position)
	for frame: int in 4:
		turns.advance(0.05)
	var whole_steps := true
	for index: int in 4:
		whole_steps = whole_steps and is_equal_approx(
			quarters[index].current_animation_position - settled[index], 0.2)
	_expect(whole_steps, "each quarter-rate player is stepped by the time its four frames covered")
	turns.reset()

	# Without the stagger every half-rate player is stepped on the same frame.
	var together := AnimationGate.new()
	together.stagger = false
	together.apply(first, AnimationGate.Tier.HALF)
	together.apply(second, AnimationGate.Tier.HALF)
	_expect(together.group_sizes(AnimationGate.Tier.HALF) == [2, 0],
		"unstaggered, the half-rate players share one group")
	together.reset()
	pair.queue_free()

	# An actor mid-way through a clip that does not loop keeps playing it.
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var one_shot := _player_with_clip(actor, "sit", 1.0, Animation.LOOP_NONE)
	one_shot.play("sit")
	actor.animation_player = one_shot
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_expect(one_shot.active and actor.animation_tier() == gate.one_shot_tier,
		"a one-shot clip is played out rather than paused, at the gate's one-shot rate")
	actor.set_animation_tier(AnimationGate.Tier.FULL, gate)
	gate.gate_skeletons = false
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_expect(one_shot.active and actor.animation_tier() == AnimationGate.Tier.FULL,
		"without the crowd's skeleton gating it is played out at full rate")
	gate.gate_skeletons = true
	actor.set_animation_tier(AnimationGate.Tier.FULL, gate)
	gate.one_shot_tier = AnimationGate.Tier.QUARTER
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_expect(actor.animation_tier() == AnimationGate.Tier.QUARTER,
		"with the quarter tier a one-shot out of view is played out at quarter rate")
	gate.one_shot_tier = AnimationGate.Tier.HALF
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
