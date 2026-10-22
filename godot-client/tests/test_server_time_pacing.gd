extends SceneTree
## Server-time pacing: the clock that maps server stamps onto the local tick
## clock, the stamping AppState does, and remote movement over a jittery link
## paced by server time against the same link paced by arrival time.

const ServerClock := preload("res://src/network/server_clock.gd")
const ServerTimePacing := preload("res://src/actors/server_time_pacing.gd")

class TimedActor extends ReplicatedActor3D:
	var clock_msec := 100000

	func _movement_time_msec() -> int:
		return clock_msec

var failures := 0
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_clock()
	_check_wrapping()
	_check_playout()
	_check_stamping()
	_check_due()
	# The actor reads the stamps through a small hook in apply_server_state
	# (it preloads ServerTimePacing); without it there is nothing to simulate.
	if not (ReplicatedActor3D as Script).get_script_constant_map().has("ServerTimePacing"):
		print("SKIP: replicated_actor_3d.gd does not read server-time stamps yet")
		print("server time pacing tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
		quit(failures)
		return
	for spec: Array in [["walk", 22, 600], ["run", 32, 200]]:
		var stamped: Dictionary = _simulate(spec[1], spec[2], true)
		var arrival: Dictionary = _simulate(spec[1], spec[2], false)
		print("%s, 50-ms frames, 40 ms + up to 150 ms jitter: server time stalls %d (%.0f ms), speed CV %.3f, lag %.0f ms; arrival time stalls %d (%.0f ms), speed CV %.3f, lag %.0f ms" % [
			spec[0], stamped.stalls, stamped.stall_msec, stamped.cv, stamped.lag_msec,
			arrival.stalls, arrival.stall_msec, arrival.cv, arrival.lag_msec])
		_expect(stamped.stalls == 0, "%s: server-time pacing never stops the body mid-walk" % spec[0])
		_expect(stamped.cv < 0.08, "%s: server-time pacing keeps the speed on the ground steady (CV %.3f)" % [spec[0], stamped.cv])
		_expect(stamped.cv < arrival.cv, "%s: steadier than arrival-time pacing over the same link" % spec[0])
	print("server time pacing tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_clock() -> void:
	var clock = ServerClock.new()
	_expect(not clock.synced, "a new clock is unsynced")
	clock.observe(1000, 5040)
	_expect(clock.synced and is_equal_approx(clock.offset_msec(), 4040.0),
		"the first stamp sets the offset")
	# A frame held 80 ms longer does not move the offset; a faster one does.
	clock.observe(1050, 5170)
	_expect(is_equal_approx(clock.offset_msec(), 4040.0), "a late frame leaves the minimum alone")
	clock.observe(1100, 5130)
	_expect(is_equal_approx(clock.offset_msec(), 4030.0), "a faster frame lowers the offset at once")
	_expect(clock.to_local_msec(1200) == 5230, "a stamp maps onto the local clock through the minimum")
	_expect(clock.server_now_msec(5230) == 1200, "and back")
	# A route that got slower: after the window has passed, the offset rises,
	# but no faster than OFFSET_RISE_PER_SECOND.
	var local := 5130
	var stamp := 1100
	for step: int in range(500):
		stamp += 50
		local += 50
		clock.observe(stamp, local + 100)
	_expect(is_equal_approx(clock.offset_msec(), 4130.0),
		"twenty seconds of a slower route raise the offset to it (%.1f)" % clock.offset_msec())
	var eased = ServerClock.new()
	var later: int = ServerClock.WINDOW_BUCKET_MSEC * (ServerClock.WINDOW_BUCKETS + 1)
	eased.observe(0, 1000)
	eased.observe(later, 1000 + later + 500)
	var expected_rise: float = ServerClock.OFFSET_RISE_PER_SECOND * float(later + 500) / 1000.0
	_expect(is_equal_approx(eased.offset_msec(), 1000.0 + minf(500.0, expected_rise)),
		"a rise is eased in rather than jumped (%.1f)" % eased.offset_msec())

func _check_wrapping() -> void:
	var clock = ServerClock.new()
	clock.stamp_modulus = 1 << 16
	clock.observe(65500, 1000)
	var unwrapped: int = clock.observe(30, 1066)
	_expect(unwrapped == 65536 + 30, "a stamp past the wrap continues the count (%d)" % unwrapped)
	_expect(clock.unwrap(65520) == 65520, "a stamp just before the wrap stays before it")
	_expect(clock.to_local_msec(40) - clock.to_local_msec(65530) == 46,
		"local times keep their order across the wrap")

func _check_playout() -> void:
	var clock = ServerClock.new()
	clock.observe(0, 0)
	_expect(is_equal_approx(clock.playout_delay_msec(0), ServerClock.STARTUP_PLAYOUT_MSEC),
		"until the link is known the playout delay starts conservative")
	var clean = ServerClock.new()
	for frame: int in range(ServerClock.WARM_SAMPLES):
		clean.observe(frame * 50, 1000 + frame * 50)
	_expect(is_equal_approx(clean.playout_delay_msec(5000), ServerClock.MINIMUM_PLAYOUT_MSEC),
		"a clean link gets the minimum playout delay")
	var steady = ServerClock.new()
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for frame: int in range(200):
		# Ninety in a hundred frames on time, ten held 60-120 ms.
		var held: int = rng.randi_range(60, 120) if frame % 10 == 3 else rng.randi_range(0, 5)
		steady.observe(frame * 50, 1000 + frame * 50 + held)
	var playout: float = steady.playout_delay_msec(20000)
	_expect(playout >= 60.0 and playout <= 140.0,
		"the playout delay covers the held frames (%.0f ms)" % playout)
	var awful = ServerClock.new()
	for frame: int in range(200):
		awful.observe(frame * 50, 1000 + frame * 50 + (900 if frame % 2 == 0 else 0))
	_expect(is_equal_approx(awful.playout_delay_msec(20000), ServerClock.MAXIMUM_PLAYOUT_MSEC),
		"and never more than the most arrival pacing ever buffered")

func _check_stamping() -> void:
	var actor := {"x": 1, "y": 1}
	ServerTimePacing.stamp(actor, 5000, 0.04, 1)
	ServerTimePacing.stamp(actor, 5050, 0.05, 1)
	_expect(int(actor[ServerTimePacing.STEP_KEY]) == 5000,
		"a second step in the same presentation pass keeps the first step's time")
	ServerTimePacing.stamp(actor, 5100, 0.05, 2)
	_expect(int(actor[ServerTimePacing.STEP_KEY]) == 5100
		and is_equal_approx(float(actor[ServerTimePacing.PLAYOUT_KEY]), 0.05),
		"the next pass takes its own")
	ServerTimePacing.unstamp(actor)
	_expect(not actor.has(ServerTimePacing.STEP_KEY), "an unstamped step clears the stamp")
	var actors := {7: {"x": 0}, 8: {"x": 0}, 9: {"x": 0}}
	# 7 walks, 8 turns (no step), 9 is the player's own actor and runs.
	var payload := PackedByteArray([7, 0, 22, 8, 0, 40, 9, 0, 32])
	var touched: int = ServerTimePacing.stamp_payload(actors, payload, 6000, 0.03, 3, 9)
	_expect(touched == 1 and (actors[7] as Dictionary).has(ServerTimePacing.STEP_KEY)
		and not (actors[8] as Dictionary).has(ServerTimePacing.STEP_KEY)
		and not (actors[9] as Dictionary).has(ServerTimePacing.STEP_KEY),
		"a packet stamps the actors it stepped, not a turn, not the player's own")
	ServerTimePacing.stamp_payload(actors, payload, -1, 0.0, 4, 9)
	_expect(not (actors[7] as Dictionary).has(ServerTimePacing.STEP_KEY),
		"a negative time takes the stamps off")
	for command: int in [19, 20, 27, 28, 29, 30, 37, 38]:
		_expect(ServerTimePacing.is_step_command(command) == (command in [20, 27, 30, 37]),
			"command %d is %s a step" % [command, "" if command in [20, 27, 30, 37] else "not"])

func _check_due() -> void:
	# Steady walking: the schedule continues by one cadence each step.
	var due: float = ServerTimePacing.due_seconds(10.0, -1.0, 0.6, 0.05)
	_expect(is_equal_approx(due, 10.65), "the first step ends a cadence and the playout after it was taken")
	var next: float = ServerTimePacing.due_seconds(10.6, due, 0.6, 0.05)
	_expect(is_equal_approx(next, 11.25), "a step on cadence continues the schedule")
	# A stamp that went out a frame late pushes the schedule out once...
	var late: float = ServerTimePacing.due_seconds(11.25, next, 0.6, 0.05)
	_expect(is_equal_approx(late, 11.9), "a late stamp pushes the schedule out")
	# ...and a schedule ahead of its bound is trimmed only gently.
	var trimmed: float = ServerTimePacing.due_seconds(11.8, late, 0.6, 0.05)
	_expect(is_equal_approx(trimmed, late + 0.6 / ServerTimePacing.CATCH_UP),
		"a schedule ahead of its bound is trimmed at the catch-up rate")

## One remote actor walking 40 steps along x, the server stepping it every
## `pace_msec` (with the first step 17 ms into a frame, so the steps fall
## across the 50-ms frames rather than on them), each frame delivered 40 ms
## plus up to 150 ms of jitter later and read on the client's next 60-Hz frame.
## The link runs for three seconds before the walk, as it would for a player
## who has been logged in a while.
## Returns stop-starts, how far the speed on the ground varies, and how far
## the body lags the server.
func _simulate(command: int, pace_msec: int, stamped: bool) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = 2026
	var clock = ServerClock.new()
	var actor := TimedActor.new()
	root.add_child(actor)
	actor.clock_msec = 0
	actor.apply_server_state({"x": 0, "y": 0, "rotation": 0, "command": command}, adapter, true)
	var steps := 40
	var frame_msec := 50
	var start: int = 3000 + 17
	var end_msec: int = start + pace_msec * steps + 2000
	# Every frame's stamp and arrival, in order; TCP keeps them in order.
	var arrivals: Array[int] = []
	var previous_arrival := 0
	for frame: int in range(end_msec / frame_msec + 1):
		var arrival: int = maxi(previous_arrival, frame * frame_msec + 40 + rng.randi_range(0, 150))
		# Read on the next 60-Hz client frame.
		arrival = ceili(float(arrival) / 16.0) * 16
		arrivals.append(arrival)
		previous_arrival = arrival
	var pending: Array[Dictionary] = []
	for step: int in range(1, steps + 1):
		var taken: int = start + pace_msec * (step - 1)
		var frame: int = ceili(float(taken) / float(frame_msec))
		pending.append({"x": step, "taken": taken, "stamp": frame * frame_msec,
			"arrival": arrivals[frame]})
	var next_frame := 0
	var next_step := 0
	var tick := 16
	var positions: Array[float] = []
	var stalls := 0
	var stall_msec := 0
	var stalled := false
	var lag_total := 0.0
	var lag_count := 0
	var dto: Dictionary = {"x": 0, "y": 0, "rotation": 0, "command": command}
	var pass_id := 0
	for now: int in range(0, end_msec, tick):
		actor.clock_msec = now
		while next_frame < arrivals.size() and arrivals[next_frame] <= now:
			clock.observe(next_frame * frame_msec, arrivals[next_frame])
			next_frame += 1
		var moved := false
		pass_id += 1
		while next_step < pending.size() and int(pending[next_step].arrival) <= now:
			var step: Dictionary = pending[next_step]
			dto = dto.duplicate()
			dto["x"] = int(step.x)
			dto["command"] = command
			if stamped:
				ServerTimePacing.stamp(dto, clock.to_local_msec(int(step.stamp)),
					clock.playout_delay_msec(now) / 1000.0, pass_id)
			moved = true
			next_step += 1
		if moved:
			actor.apply_server_state(dto, adapter)
		actor._physics_process(float(tick) / 1000.0)
		var x: float = actor.global_position.x
		positions.append(x)
		# Mid-walk is from the first step's arrival until the server's last step.
		var server_x: float = clampf(float(now - start) / float(pace_msec) + 1.0, 0.0, float(steps))
		if next_step > 0 and now < start + pace_msec * (steps - 1) and positions.size() > 1:
			var speed: float = absf(x - positions[positions.size() - 2]) / (float(tick) / 1000.0)
			var nominal: float = 1000.0 / float(pace_msec)
			if speed < nominal * 0.1:
				stall_msec += tick
				if not stalled:
					stalls += 1
					if OS.get_environment("PACING_DEBUG") == "1":
						print("stall at %d ms (stamped %s), x %.2f, server %.2f, playout %.0f" % [
							now, stamped, x, server_x, clock.playout_delay_msec(now)])
				stalled = true
			else:
				stalled = false
			lag_total += server_x - absf(x)
			lag_count += 1
	# Speed over 100-ms windows across the middle of the walk.
	var window: int = 6
	var speeds: Array[float] = []
	var first: int = (pending[0].arrival as int) / tick + 40
	var last: int = (start + pace_msec * (steps - 1)) / tick
	for index: int in range(first, last - window, window):
		speeds.append(absf(positions[index + window] - positions[index]) / (float(window * tick) / 1000.0))
	var mean := 0.0
	for speed: float in speeds:
		mean += speed
	mean /= maxf(1.0, float(speeds.size()))
	var spread := 0.0
	for speed: float in speeds:
		spread += (speed - mean) * (speed - mean)
	spread = sqrt(spread / maxf(1.0, float(speeds.size())))
	actor.queue_free()
	return {"stalls": stalls, "stall_msec": float(stall_msec), "cv": spread / maxf(mean, 0.001),
		"lag_msec": lag_total / maxf(1.0, float(lag_count)) * float(pace_msec)}

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
