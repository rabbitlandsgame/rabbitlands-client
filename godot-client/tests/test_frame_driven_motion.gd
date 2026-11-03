extends SceneTree
## Low actor tier (LAT-L7): frame-driven remote motion. With the frame clock on
## (Low), an awake remote actor takes one presentation step per drawn frame
## from `ReplicatedActor3D.advance_frame_driven` (Main calls it first in
## `_process`) instead of one per 60 Hz physics tick.
##
## - Off by default: every actor presents on physics as before.
## - The same paced walk (walk and run, arrival-time and server-time pacing)
##   arrives and settles within one frame of the physics-driven walk over the
##   same frames, at a steady 30 FPS and at an irregular 25-45 ms stream, with
##   exactly one step per frame (physics: about two at 30 FPS), never moving
##   back and stalling no more often.
## - Roles: the player's own and actors nobody gave a render role keep physics.
## - Registry hygiene: settle, death and revival, charge leap, cinematic,
##   parking (process disabled), queue_free, free and reparenting.
## - The switch rehomes awake actors both ways, a settled body stays asleep.
## - The delta cap and the census fields.
## With the user argument `--bench` it only prints the headless cost of a
## walking crowd on each clock (`_bench`).

const Quality := ActorRenderQuality.Quality
const ServerTimePacing := preload("res://src/actors/server_time_pacing.gd")
const PHYSICS_STEP := 1.0 / 60.0
const WALK_STEPS := 12

class TimedActor extends ReplicatedActor3D:
	var clock_msec := 100000
	var steps := 0
	var last_delta := -1.0

	func _movement_time_msec() -> int:
		return clock_msec

	func advance_presentation(delta: float) -> void:
		steps += 1
		last_delta = delta
		super.advance_presentation(delta)

var failures := 0
var checks := 0
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	if "--bench" in OS.get_cmdline_user_args():
		_bench()
		quit(0)
		return
	_check_defaults()
	_check_walk_parity()
	_check_roles()
	_check_registry()
	_check_switch()
	_check_delta_cap_and_census()
	ReplicatedActor3D.set_frame_driven(false)
	print("frame driven motion tests: %d checks, %s" % [checks,
		"PASS" if failures == 0 else "FAIL (%d)" % failures])
	quit(failures)

func _state(x: int, y: int, command: int) -> Dictionary:
	return {"actor_id": 7, "x": x, "y": y, "rotation": 0, "command": command, "buffs": 0,
		"health": 100, "max_health": 100, "alive": true}

## A remote world actor as Main makes one: in the tree, given its render role,
## then placed by its first state. `role` "local" is the player's own, "none"
## an actor nobody gave a role (a portrait or preview).
func _spawn(role := "remote", animated := false) -> TimedActor:
	var actor := TimedActor.new()
	root.add_child(actor)
	if animated:
		_add_animation_fixture(actor)
	if role != "none":
		actor.apply_render_quality(Quality.LOW, role == "local")
	actor.apply_server_state(_state(0, 0, 7), adapter, true)
	return actor

func _add_animation_fixture(actor: TimedActor) -> void:
	actor.resolver = AnimationResolver.new({
		"actions": {"idle": "Idle", "walk": "Walk", "run": "Run", "death": "Death"},
		"serverCommands": {"3": "death", "7": "idle", "22": "walk", "32": "run"}})
	var player := AnimationPlayer.new()
	actor.add_child(player)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := AnimationLibrary.new()
	for clip: String in ["Idle", "Walk", "Run", "Death"]:
		var animation := Animation.new()
		animation.length = 0.1
		animation.loop_mode = Animation.LOOP_NONE if clip == "Death" else Animation.LOOP_LINEAR
		library.add_animation(clip, animation)
	player.add_animation_library("", library)
	actor.animation_player = player
	player.animation_finished.connect(actor._on_animation_finished)

## Steps an actor until it stops presenting, on whichever clock it is on.
func _settle(actor: TimedActor, frame := 1.0 / 30.0) -> int:
	var frames := 0
	while actor.is_presenting() and frames < 400:
		if actor.presents_on_frame_clock():
			ReplicatedActor3D.advance_frame_driven(frame)
		else:
			actor._physics_process(PHYSICS_STEP)
		frames += 1
	return frames

func _check_defaults() -> void:
	_expect(not ReplicatedActor3D.frame_driven(), "the frame clock is off by default")
	_expect(ReplicatedActor3D.FRAME_DRIVEN_MAX_DELTA == 0.25, "a frame step is capped at 0.25 s")
	_expect(ActorRenderQuality.frame_driven_motion(Quality.LOW)
		and not ActorRenderQuality.frame_driven_motion(Quality.MEDIUM)
		and not ActorRenderQuality.frame_driven_motion(Quality.HIGH),
		"only Low asks for frame-driven motion")
	var actor := _spawn()
	actor.apply_server_state(_state(1, 0, 22), adapter)
	_expect(actor.is_physics_processing() and not actor.presents_on_frame_clock()
		and actor.is_presenting() and ReplicatedActor3D.frame_driven_count() == 0,
		"with the clock off a woken remote actor presents on physics as before")
	var before := actor.steps
	_expect(ReplicatedActor3D.advance_frame_driven(1.0 / 30.0) == 0 and actor.steps == before,
		"with the clock off the frame step steps nothing")
	var census := actor.presentation_census()
	_expect(census == {"framePresenting": false, "physicsPresenting": true},
		"the census reports a physics-clock body")
	_settle(actor)
	_expect(not actor.is_presenting() and actor._settled
		and actor.global_position.is_equal_approx(actor.server_target),
		"a physics body still settles on its target")
	actor.free()

## Frame times in ms: `count` frames at a steady `msec`, or seeded random
## frames between `low` and `high`.
func _frames(count: int, msec: float, low := 0.0, high := 0.0, seed_value := 0) -> PackedFloat64Array:
	var frames := PackedFloat64Array()
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	for _index: int in count:
		frames.append(msec if high <= 0.0 else rng.randf_range(low, high))
	return frames

## A walk of WALK_STEPS tiles along +x: the server takes a step every
## `pace_msec`, each reaches the client 40 ms later and is applied after the
## steps of the frame it arrives in (Main's deferred world sync). Physics-driven
## runs the engine's 60 Hz ticks inside each frame (at most 8; every tick of a
## frame reads the same clock); frame-driven takes one advance_frame_driven per
## frame. Returns when the body reached the last tile and when it settled
## (frame end times, ms), steps per awake frame, moves back and stalled frames.
func _walk(frames: PackedFloat64Array, frame_driven: bool, command: int, pace_msec: int,
		stamped: bool) -> Dictionary:
	ReplicatedActor3D.set_frame_driven(frame_driven)
	var actor := _spawn()
	_settle(actor)
	var base := actor.clock_msec
	var start := 500.0
	var latency := 40.0
	var pending: Array[Dictionary] = []
	for step: int in range(1, WALK_STEPS + 1):
		var taken: float = start + float(pace_msec * (step - 1))
		pending.append({"x": step, "taken": taken, "arrival": taken + latency})
	# The last step's tile centre, as the actor places it.
	var final_target := adapter.footprint_center(WALK_STEPS, 0, actor.footprint)
	var now := 0.0
	var accumulator := 0.0
	var next := 0
	var arrival := -1.0
	var settle := -1.0
	var awake_frames := 0
	var steps_before := actor.steps
	var backsteps := 0
	var stalls := 0
	var first_applied := -1.0
	var previous_x := actor.global_position.x
	var max_delta := 0.0
	var on_frame_clock := true
	var positions := PackedFloat64Array()
	for index: int in frames.size():
		var delta_msec: float = frames[index]
		max_delta = maxf(max_delta, delta_msec)
		now += delta_msec
		actor.clock_msec = base + roundi(now)
		var was_presenting := actor.is_presenting()
		if frame_driven:
			on_frame_clock = on_frame_clock and (not was_presenting or actor.presents_on_frame_clock())
			ReplicatedActor3D.advance_frame_driven(delta_msec / 1000.0)
		else:
			accumulator += delta_msec / 1000.0
			var ticks := 0
			while accumulator >= PHYSICS_STEP - 1e-9 and ticks < 8:
				accumulator -= PHYSICS_STEP
				ticks += 1
				if actor.is_physics_processing():
					actor._physics_process(PHYSICS_STEP)
		if was_presenting:
			awake_frames += 1
		var x := actor.global_position.x
		positions.append(x)
		if x < previous_x - 1e-5:
			backsteps += 1
		if first_applied >= 0.0 and arrival < 0.0 and x <= previous_x + 1e-6:
			stalls += 1
		previous_x = x
		if next == pending.size() and arrival < 0.0 and Vector2(x, actor.global_position.z).distance_to(
				Vector2(final_target.x, final_target.z)) < 1e-4:
			arrival = now
		if next == pending.size() and arrival >= 0.0 and not actor.is_presenting():
			settle = now
			break
		var dto: Dictionary = {}
		while next < pending.size() and float(pending[next].arrival) <= now:
			dto = _state(int(pending[next].x), 0, command)
			if stamped:
				ServerTimePacing.stamp(dto, base + roundi(float(pending[next].taken)), 0.1, index)
			next += 1
		if not dto.is_empty():
			actor.apply_server_state(dto, adapter)
			if first_applied < 0.0:
				first_applied = now
	var result := {"arrival": arrival, "settle": settle,
		"steps_per_frame": float(actor.steps - steps_before) / maxf(1.0, float(awake_frames)),
		"backsteps": backsteps, "stalls": stalls, "max_delta": max_delta,
		"final": actor.global_position.is_equal_approx(actor.server_target)
			and is_equal_approx(actor.server_target.x, final_target.x)
			and is_equal_approx(actor.server_target.z, final_target.z),
		"on_frame_clock": on_frame_clock, "left": ReplicatedActor3D.frame_driven_count() == 0,
		"positions": positions}
	actor.free()
	ReplicatedActor3D.set_frame_driven(false)
	return result

func _check_walk_parity() -> void:
	var steady := _frames(240, 1000.0 / 30.0)
	var irregular := _frames(240, 0.0, 25.0, 45.0, 2026)
	for spec: Array in [["walk", 22, 400], ["run", 32, 200]]:
		for stamped: bool in [false, true]:
			for stream: Array in [["30 FPS", steady], ["25-45 ms", irregular]]:
				var label := "%s, %s pacing, %s frames" % [spec[0],
					"server-time" if stamped else "arrival-time", stream[0]]
				var physics := _walk(stream[1], false, spec[1], spec[2], stamped)
				var frame := _walk(stream[1], true, spec[1], spec[2], stamped)
				print("%s: physics arrives %.1f ms, settles %.1f ms, %.2f steps/frame, %d stalls; frame clock arrives %.1f ms, settles %.1f ms, %.2f steps/frame, %d stalls" % [
					label, physics.arrival, physics.settle, physics.steps_per_frame, physics.stalls,
					frame.arrival, frame.settle, frame.steps_per_frame, frame.stalls])
				var one_frame: float = maxf(physics.max_delta, frame.max_delta) + 0.01
				# Where the body is drawn on each frame: never more than one frame
				# of travel (a tile per pace) from the physics-driven body.
				var gap := 0.0
				var drawn_physics: PackedFloat64Array = physics.positions
				var drawn_frame: PackedFloat64Array = frame.positions
				for index: int in mini(drawn_physics.size(), drawn_frame.size()):
					gap = maxf(gap, absf(drawn_frame[index] - drawn_physics[index]))
				var travel: float = one_frame / float(spec[2])
				print("%s: largest per-frame position gap %.4f m (one frame of travel %.3f m)" % [label, gap, travel])
				_expect(gap <= travel, "%s: drawn within one frame of travel of the physics body every frame (%.4f m)" % [label, gap])
				_expect(physics.arrival > 0.0 and physics.settle > 0.0 and physics.final,
					"%s: the physics-driven reference walk completes" % label)
				_expect(frame.arrival > 0.0 and absf(frame.arrival - physics.arrival) <= one_frame,
					"%s: frame-driven arrival within one frame of physics (%.1f vs %.1f ms)" % [
						label, frame.arrival, physics.arrival])
				_expect(frame.settle > 0.0 and absf(frame.settle - physics.settle) <= one_frame,
					"%s: frame-driven settle within one frame of physics (%.1f vs %.1f ms)" % [
						label, frame.settle, physics.settle])
				_expect(frame.final and frame.left and frame.on_frame_clock,
					"%s: frame-driven body ends on its target and leaves the frame clock" % label)
				_expect(is_equal_approx(frame.steps_per_frame, 1.0),
					"%s: exactly one presentation step per drawn frame (%.2f)" % [label, frame.steps_per_frame])
				if stream[0] == "30 FPS":
					_expect(physics.steps_per_frame > 1.9,
						"%s: physics stepped about twice per frame (%.2f)" % [label, physics.steps_per_frame])
				_expect(frame.backsteps == 0 and physics.backsteps == 0,
					"%s: never moves back along the walk" % label)
				_expect(frame.stalls <= physics.stalls,
					"%s: stalls no more often than physics (%d vs %d)" % [label, frame.stalls, physics.stalls])

func _check_roles() -> void:
	ReplicatedActor3D.set_frame_driven(true)
	var remote := _spawn("remote")
	var local := _spawn("local")
	var plain := _spawn("none")
	for actor: TimedActor in [remote, local, plain]:
		actor.apply_server_state(_state(1, 0, 22), adapter)
	_expect(remote.presents_on_frame_clock() and not remote.is_physics_processing()
		and remote.is_presenting() and ReplicatedActor3D.frame_driven_count() == 1,
		"a woken remote actor joins the frame clock and leaves physics")
	_expect(not local.presents_on_frame_clock() and local.is_physics_processing(),
		"the player's own actor keeps physics")
	_expect(not plain.presents_on_frame_clock() and plain.is_physics_processing(),
		"an actor nobody gave a render role (portrait, preview) keeps physics")
	plain.set_physics_process(false)
	var plain_at := plain.global_position
	var plain_steps := plain.steps
	var local_steps := local.steps
	_expect(ReplicatedActor3D.advance_frame_driven(1.0 / 30.0) == 1 and remote.steps == 1,
		"the frame step steps the remote actor once")
	_expect(plain.steps == plain_steps and plain.global_position == plain_at
		and local.steps == local_steps,
		"the frame step leaves a frozen unassigned actor and the local player alone")
	remote.apply_render_quality(Quality.LOW, true)
	_expect(not remote.presents_on_frame_clock() and remote.is_physics_processing()
		and ReplicatedActor3D.frame_driven_count() == 0,
		"an awake actor made local moves to physics at once")
	remote.apply_render_quality(Quality.LOW, false)
	_expect(remote.presents_on_frame_clock() and not remote.is_physics_processing()
		and ReplicatedActor3D.frame_driven_count() == 1,
		"made remote again it returns to the frame clock")
	remote.apply_render_quality(Quality.HIGH, false)
	_expect(remote.presents_on_frame_clock(),
		"the actor's own quality does not pick the clock; Main's switch does")
	for actor: TimedActor in [remote, local, plain]:
		actor.free()
	_expect(ReplicatedActor3D.frame_driven_count() == 0, "freed actors leave the frame clock")
	ReplicatedActor3D.set_frame_driven(false)

func _check_registry() -> void:
	ReplicatedActor3D.set_frame_driven(true)
	# Settle: a finished step leaves the clock.
	var actor := _spawn("remote", true)
	actor.apply_server_state(_state(1, 0, 22), adapter)
	_expect(actor.presents_on_frame_clock() and actor.current_action == &"walk",
		"a walking body is on the frame clock")
	var frames := _settle(actor)
	_expect(not actor.is_presenting() and actor._settled and ReplicatedActor3D.frame_driven_count() == 0
		and actor.global_position.is_equal_approx(actor.server_target) and frames < 400,
		"a settled body leaves the frame clock on its target (%d frames)" % frames)
	_expect(actor.presentation_census() == {"framePresenting": false, "physicsPresenting": false},
		"the census reports a settled body on neither clock")
	# Death pauses, revival wakes.
	var dto := _state(2, 0, 22)
	actor.apply_server_state(dto, adapter)
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	dto = ActorReducer.apply_command(dto, 3)
	actor.apply_server_state(dto, adapter)
	_expect(actor.current_action == &"death", "the death command plays death")
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	_expect(not actor.is_presenting() and ReplicatedActor3D.frame_driven_count() == 0
		and actor.global_position.is_equal_approx(actor.server_target),
		"death puts the body on its tile and pauses it")
	actor.clock_msec += 10000
	dto = ActorReducer.apply_command(_state(2, 0, 7), 32)
	actor.apply_server_state(dto, adapter)
	_expect(actor.presents_on_frame_clock() and ReplicatedActor3D.frame_driven_count() == 1,
		"revival wakes the body on the frame clock")
	_settle(actor)
	# Parking: processing disabled keeps the place but takes no steps. (The
	# reducer's run command above already put the body on tile 3.)
	actor.apply_server_state(_state(5, 0, 22), adapter)
	_expect(actor.presents_on_frame_clock() and actor._segment_duration > 0.0,
		"a body walking two tiles is on the frame clock")
	actor.process_mode = Node.PROCESS_MODE_DISABLED
	var parked_at := actor.global_position
	var parked_steps := actor.steps
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	_expect(actor.steps == parked_steps and actor.global_position == parked_at
		and ReplicatedActor3D.frame_driven_count() == 1,
		"a parked (processing disabled) body is not stepped and keeps its place")
	actor.process_mode = Node.PROCESS_MODE_INHERIT
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	_expect(actor.steps == parked_steps + 1 and actor.global_position != parked_at,
		"a revived parked body steps again")
	# Reparenting: out of the tree nothing steps it; back in, it carries on.
	root.remove_child(actor)
	_expect(ReplicatedActor3D.frame_driven_count() == 0 and actor.presents_on_frame_clock(),
		"a body leaving the tree leaves the frame set but stays awake")
	root.add_child(actor)
	_expect(ReplicatedActor3D.frame_driven_count() == 1 and actor.presents_on_frame_clock(),
		"back in the tree it rejoins the frame clock")
	_settle(actor)
	# Cinematic: owns the pose, never settles, and hands back on end.
	actor.set_cinematic_presentation(Vector3(5, 0, 5), 1.0, &"idle")
	_expect(actor.presents_on_frame_clock(), "a cinematic presentation is on the frame clock")
	for _frame: int in 30:
		ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	_expect(actor.presents_on_frame_clock() and actor.global_position.is_equal_approx(Vector3(5, 0, 5)),
		"a cinematic stays on its point and does not settle")
	actor.end_cinematic_presentation()
	_settle(actor)
	_expect(not actor.is_presenting() and ReplicatedActor3D.frame_driven_count() == 0
		and actor.global_position.is_equal_approx(actor.server_target),
		"the cinematic's end hands the body back and it settles")
	# Free while in the tree: leaves at once.
	actor.apply_server_state(_state(4, 0, 22), adapter)
	actor.free()
	_expect(ReplicatedActor3D.frame_driven_count() == 0, "a body freed while awake leaves the frame set")
	# queue_free: not stepped again, gone from the set at the next frame step.
	var queued := _spawn("remote")
	queued.apply_server_state(_state(1, 0, 22), adapter)
	var queued_steps := queued.steps
	queued.queue_free()
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	_expect(queued.steps == queued_steps and ReplicatedActor3D.frame_driven_count() == 0,
		"a body queued for deletion is never stepped and leaves the frame set")
	# Charge leap: flown on the frame clock, lands and settles.
	var leaper := TimedActor.new()
	root.add_child(leaper)
	leaper.apply_render_quality(Quality.LOW, false)
	var route := PackedVector3Array([Vector3.ZERO, Vector3(1, 0.2, 0), Vector3(2, 0.4, 0)])
	leaper.server_target = route[-1]
	leaper.begin_charge_leap(route, 0.36)
	_expect(leaper.presents_on_frame_clock() and leaper._charge_leap != null,
		"a charge leap is flown on the frame clock")
	ReplicatedActor3D.advance_frame_driven(0.18)
	_expect(leaper.global_position.y > 0.6, "the leaper is airborne after half the flight")
	ReplicatedActor3D.advance_frame_driven(0.18)
	_expect(leaper._charge_leap == null and leaper.global_position.is_equal_approx(leaper.server_target),
		"the leap lands on the confirmed tile")
	_settle(leaper)
	_expect(not leaper.is_presenting() and ReplicatedActor3D.frame_driven_count() == 0,
		"the landed leaper settles and leaves the frame clock")
	leaper.free()
	ReplicatedActor3D.set_frame_driven(false)

func _check_switch() -> void:
	ReplicatedActor3D.set_frame_driven(true)
	var awake := _spawn("remote")
	awake.apply_server_state(_state(1, 0, 22), adapter)
	var asleep := _spawn("remote")
	_settle(asleep)
	_expect(awake.presents_on_frame_clock() and not asleep.is_presenting(), "one awake, one settled")
	ReplicatedActor3D.set_frame_driven(false)
	_expect(not ReplicatedActor3D.frame_driven() and awake.is_physics_processing()
		and not awake.presents_on_frame_clock() and ReplicatedActor3D.frame_driven_count() == 0,
		"turning the clock off puts every awake frame-clock body back on physics")
	_expect(not asleep.is_presenting(), "turning it off does not wake a settled body")
	ReplicatedActor3D.set_frame_driven(true)
	_expect(awake.is_physics_processing() and ReplicatedActor3D.frame_driven_count() == 0,
		"turning it on leaves physics bodies until their next tick or role pass")
	var at := awake.global_position
	var steps := awake.steps
	awake._physics_process(PHYSICS_STEP)
	_expect(awake.presents_on_frame_clock() and not awake.is_physics_processing()
		and awake.steps == steps and awake.global_position == at,
		"its next physics tick moves it to the frame clock without stepping it")
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	_expect(awake.steps == steps + 1 and awake.global_position != at,
		"the frame step then steps it")
	ReplicatedActor3D.set_frame_driven(false)
	ReplicatedActor3D.set_frame_driven(true)
	awake.apply_render_quality(Quality.LOW, false)
	_expect(awake.presents_on_frame_clock() and not awake.is_physics_processing(),
		"Main's role pass after turning it on moves an awake body at once")
	asleep.apply_render_quality(Quality.LOW, false)
	_expect(not asleep.is_presenting(), "the role pass does not wake a settled body")
	ReplicatedActor3D.set_frame_driven(true)
	_expect(ReplicatedActor3D.frame_driven_count() == 1, "turning it on twice changes nothing")
	awake.free()
	asleep.free()
	ReplicatedActor3D.set_frame_driven(false)

func _check_delta_cap_and_census() -> void:
	ReplicatedActor3D.set_frame_driven(true)
	var actor := _spawn("remote")
	actor.apply_server_state(_state(1, 0, 22), adapter)
	_expect(actor.presentation_census() == {"framePresenting": true, "physicsPresenting": false},
		"the census reports a frame-clock body")
	ReplicatedActor3D.advance_frame_driven(1.0)
	_expect(is_equal_approx(actor.last_delta, 0.25), "a one-second hitch is stepped as 0.25 s")
	if actor.presents_on_frame_clock():
		ReplicatedActor3D.advance_frame_driven(-0.5)
		_expect(actor.last_delta == 0.0, "a negative delta is stepped as zero")
	actor.free()
	ReplicatedActor3D.set_frame_driven(false)

## `--bench`: the headless cost of presenting a walking remote crowd under a
## 30 FPS cap, physics-driven (two 60 Hz ticks per frame, the actors' own
## `_physics_process`) against frame-driven (one `advance_frame_driven` per
## frame). Each actor takes a step every 400 ms, staggered; 300 frames, best of
## 5. Bodies have no model, so this is the GDScript presentation step and its
## dispatch only; a drawn body adds its surface tilt and ring work to each step.
func _bench() -> void:
	for count: int in [60, 160]:
		var physics := INF
		var frame := INF
		for _repeat: int in 5:
			physics = minf(physics, _bench_run(count, false))
			frame = minf(frame, _bench_run(count, true))
		print("bench %d walking remote actors, 30 FPS: physics %.1f us/frame, frame clock %.1f us/frame (%.2f vs %.2f us per actor per frame)" % [
			count, physics, frame, physics / count, frame / count])

func _bench_run(count: int, frame_driven: bool) -> float:
	ReplicatedActor3D.set_frame_driven(frame_driven)
	var actors: Array[TimedActor] = []
	var tiles := PackedInt32Array()
	for index: int in count:
		var actor := TimedActor.new()
		root.add_child(actor)
		actor.apply_render_quality(Quality.LOW, false)
		actor.apply_server_state(_state(0, index * 2, 7), adapter, true)
		actors.append(actor)
		tiles.append(0)
	var frames := 300
	var spent := 0
	for frame: int in frames:
		var now_msec := 100000 + roundi(float(frame) * 1000.0 / 30.0)
		for actor: TimedActor in actors:
			actor.clock_msec = now_msec
		var started := Time.get_ticks_usec()
		if frame_driven:
			ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
		else:
			for _tick: int in 2:
				for actor: TimedActor in actors:
					if actor.is_physics_processing():
						actor._physics_process(PHYSICS_STEP)
		spent += Time.get_ticks_usec() - started
		for index: int in count:
			if (frame + index) % 12 == 0:
				tiles[index] += 1
				actors[index].apply_server_state(_state(tiles[index], index * 2, 22), adapter)
	for actor: TimedActor in actors:
		actor.free()
	ReplicatedActor3D.set_frame_driven(false)
	return float(spent) / float(frames)
