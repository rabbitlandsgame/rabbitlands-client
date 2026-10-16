extends SceneTree

class TimedActor extends ReplicatedActor3D:
	var clock_msec := 100000

	func _movement_time_msec() -> int:
		return clock_msec

var failures := 0
var checks := 0
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func spawn_actor() -> TimedActor:
	var actor := TimedActor.new()
	root.add_child(actor)
	actor.apply_server_state(state(0, 0, 32, false), adapter, true)
	return actor

func state(x: int, y: int, command: int, haste: bool) -> Dictionary:
	return {"x": x, "y": y, "rotation": 0, "command": command,
		"buffs": EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED if haste else 0}

func advance(actor: TimedActor, seconds: float) -> void:
	actor.clock_msec += roundi(seconds * 1000.0)
	actor._physics_process(seconds)

func add_animation_fixture(actor: TimedActor) -> void:
	actor.resolver = AnimationResolver.new(JSON.parse_string(
		FileAccess.get_file_as_string("res://data/animations/luminous.json")))
	var player := AnimationPlayer.new()
	actor.add_child(player)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := AnimationLibrary.new()
	for clip: String in actor.resolver.required_clips():
		var animation := Animation.new()
		animation.length = 0.1
		if actor.resolver.looping_clips.has(clip):
			animation.loop_mode = Animation.LOOP_LINEAR
		library.add_animation(clip, animation)
	player.add_animation_library("", library)
	actor.animation_player = player
	player.animation_finished.connect(actor._on_animation_finished)

func check_post_combat_movement() -> void:
	for command: int in [22, 32]:
		var action: StringName = &"run" if command == 32 else &"walk"
		# Commands from one socket read are reduced before the actor is drawn.
		# A combat-end command behind the step must not hide its locomotion.
		var actor := spawn_actor()
		add_animation_fixture(actor)
		var dto := state(0, 0, 46, false)
		dto["in_combat"] = true
		dto = ActorReducer.apply_command(dto, command)
		dto = ActorReducer.apply_command(dto, 19)
		actor.apply_server_state(dto, adapter)
		expect(actor.current_action == action,
			"coalesced combat end keeps the %s to the bag" % action)
		var before := actor.global_position
		advance(actor, actor._segment_duration * 0.5)
		expect(actor.global_position.distance_to(before) > 0.1 and actor.current_action == action,
			"the body moves with the %s animation during bag approach" % action)
		actor.free()

		# The same transition can arrive after the first movement frame, or
		# be restated by a later health/equipment update during interpolation.
		actor = spawn_actor()
		add_animation_fixture(actor)
		dto = ActorReducer.apply_command(state(0, 0, 19, false), command)
		actor.apply_server_state(dto, adapter)
		advance(actor, actor._segment_duration * 0.25)
		dto = ActorReducer.apply_command(dto, 19)
		actor.apply_server_state(dto, adapter)
		expect(actor.current_action == action,
			"a later combat-end packet keeps the active %s" % action)
		actor.apply_server_state(dto, adapter)
		expect(actor.current_action == action,
			"a repeated combat-end state keeps the active %s" % action)
		actor.play_action(&"pain", true)
		actor.animation_player.advance(0.11)
		expect(actor.current_action == action,
			"a finished hit reaction resumes the %s while approaching the bag" % action)
		advance(actor, 2.0)
		actor.apply_server_state(dto, adapter)
		expect(actor.current_action == &"idle" and actor.global_position.is_equal_approx(actor.server_target),
			"arrival at the bag idles without restarting the %s" % action)
		actor.play_action(&"pain", true)
		actor.animation_player.advance(0.11)
		expect(actor.current_action == &"idle", "a stationary hit reaction still returns to idle")
		actor.free()

func run() -> void:
	check_post_combat_movement()
	for running: bool in [false, true]:
		var ordinary := spawn_actor()
		var pace := 0.2 if running else 0.6
		var lag := 0.0
		for tile: int in range(1, 61):
			ordinary.apply_server_state(state(tile, 0, 32 if running else 22, false), adapter)
			advance(ordinary, pace)
			lag = maxf(lag, ordinary.global_position.distance_to(ordinary.server_target))
		expect(lag < 0.5, "ordinary %s keeps a bounded movement buffer" % ("running" if running else "walking"))
		ordinary.free()

	# Current maps use one metre per tile. A hasted run sends ten tiles a
	# second, so the nominal nine-metre presentation limit must not accumulate
	# an ever-growing gap and trigger the eight-metre teleport safeguard.
	var actor := spawn_actor()
	actor._pace_histories[3] = PackedFloat32Array([0.1, 0.1, 0.1])
	var furthest_behind := 0.0
	var snaps := 0
	for tile: int in range(1, 301):
		var previous := actor.global_position
		actor.apply_server_state(state(tile, 0, 32, true), adapter)
		if actor.global_position.distance_to(previous) > 1.0:
			snaps += 1
		advance(actor, 0.1)
		furthest_behind = maxf(furthest_behind,
			actor.global_position.distance_to(actor.server_target))
	expect(snaps == 0, "a thirty-second hasted run never snaps to catch up")
	expect(furthest_behind < 1.5,
		"a hasted run stays within its small interpolation buffer (gap %.3f)" % furthest_behind)
	advance(actor, 1.5)
	expect(actor.global_position.is_equal_approx(actor.server_target),
		"stopping a hasted run settles on the authoritative destination")
	actor.free()

	# Once both gaits have observations, each keeps its own measured pace.
	actor = spawn_actor()
	actor._pace_histories[1] = PackedFloat32Array([0.22, 0.22, 0.22])
	actor._pace_histories[3] = PackedFloat32Array([0.105, 0.105, 0.105])
	actor.apply_server_state(state(1, 0, 32, true), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.105),
		"a measured hasted pace takes precedence over its estimated counterpart")
	advance(actor, 0.105)
	actor.apply_server_state(state(2, 0, 32, false), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.22),
		"an observed running history survives haste ending")
	actor.free()

	actor = spawn_actor()
	actor.apply_server_state(state(1, 0, 32, false), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.2),
		"the first running step starts at the running pace")
	actor.free()
	actor = spawn_actor()
	actor.apply_server_state(state(1, 0, 32, true), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.1),
		"the first hasted running step starts at half the running interval")
	actor.free()
	actor = spawn_actor()
	actor.apply_server_state(state(1, 0, 22, true), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.3),
		"a hasted walking start keeps its separate walking pace")
	actor.free()

	# Use a non-default measured pace: haste changes the known interval by
	# exactly half before its first packet gap has arrived to teach a history.
	actor = spawn_actor()
	actor._pace_histories[1] = PackedFloat32Array([0.24, 0.24, 0.24])
	actor.apply_server_state(state(1, 0, 32, false), adapter)
	advance(actor, 0.24)
	actor.apply_server_state(state(2, 0, 32, true), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.12),
		"activating haste immediately halves the measured running interval")
	actor.free()
	actor = spawn_actor()
	actor._pace_histories[3] = PackedFloat32Array([0.12, 0.12, 0.12])
	actor.apply_server_state(state(1, 0, 32, true), adapter)
	advance(actor, 0.12)
	actor.apply_server_state(state(2, 0, 32, false), adapter)
	expect(is_equal_approx(actor._smoothed_server_interval, 0.24),
		"expiring haste immediately restores the measured running interval")
	actor.free()

	# Alternating diagonal/straight steps must retain the same ground speed.
	actor = spawn_actor()
	actor._pace_histories[3] = PackedFloat32Array([0.1, 0.1, 0.1])
	var x := 0
	var y := 0
	var diagonal_gap := 0.0
	for step: int in range(200):
		x += 1
		var diagonal := step % 2 == 0
		if diagonal:
			y += 1
		actor.apply_server_state(state(x, y, 31 if diagonal else 32, true), adapter)
		advance(actor, 0.1 * (sqrt(2.0) if diagonal else 1.0))
		diagonal_gap = maxf(diagonal_gap, actor.global_position.distance_to(actor.server_target))
	expect(diagonal_gap < 1.5,
		"alternating hasted diagonal and straight steps keep a bounded gap (%.3f)" % diagonal_gap)
	actor.free()
	print("ACTOR MOVEMENT: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
