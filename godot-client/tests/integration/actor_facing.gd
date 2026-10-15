extends SceneTree
## An actor faces the way it travels, on every one of the eight directions.
##
## The rendered actor is deliberately a fraction of a tile behind its
## authoritative position, so its facing is the chord from where it is to the
## tile it is crossing to - not the direction the server's command named. That
## chord is only the travel direction while the lag stays where the arrival
## margin puts it. When the client's idea of the server cadence was longer than
## the server's real one, every step covered less ground than the next one
## added, the lag grew without bound, and the body settled tens of degrees
## round from the way it was walking - which is what this pins.

const STEPS := 6

var _failures := 0
var _jitter_steps_sent := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(640, 400)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var stage: Node3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot") as Node3D
	var models: Dictionary = main.get("models") as Dictionary
	var model_config: Dictionary = models.get("luminous_female", {}) as Dictionary
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0,
		"serverOrigin": [0.0, 0.0], "invertServerY": true})
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var dto: Dictionary = {"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"actor_type": 1, "kind": 1, "name": "T", "appearance": {}, "command": 22}
	_expect(actor.configure(dto, adapter, model_config,
		main.call("_animation_for_model", model_config), {}).is_empty(),
		"the actor builds without errors")
	actor.apply_server_state(dto, adapter, true)

	# The server's walking pace, per tile. The client assumes it until it has
	# measured one, and its own default has to agree or the actor never catches
	# up. A diagonal step crosses 1.41 tiles and the server holds it for 1.41
	# paces, so each leg below is sent at the rate its own steps travel.
	var cadence: float = actor.initial_server_interval
	# What the body covers the ground at while it is crossing a step, on each
	# leg. A diagonal step is 1.41 tiles sent 1.41 paces apart, so it has to
	# render at the same metres per second as a straight one - handing every
	# step shape the one interval is what made the walk speed up and slow down
	# along a zigzagging path. A leg whose step has already finished when the
	# next one is due reads as zero here, which is the same fault seen from the
	# other end: the body arrives early and stands still until the server
	# catches up with it.
	var leg_speeds: Array[float] = []
	# Command, server dx, dy. Each leg turns off the last one, so the first
	# step of a leg is a real turn and the rest are straight.
	for leg: Array in [[22, 1, 0], [21, 1, 1], [20, 0, 1], [27, -1, 1],
			[26, -1, 0], [25, -1, -1], [24, 0, -1], [23, 1, -1]]:
		for step: int in range(STEPS):
			dto["x"] = int(dto["x"]) + int(leg[1])
			dto["y"] = int(dto["y"]) + int(leg[2])
			dto["command"] = int(leg[0])
			actor.apply_server_state(dto, adapter)
			await create_timer(cadence * Vector2(
				float(leg[1]), float(leg[2])).length()).timeout
		var want: float = adapter.direction_to_godot(
			Vector2i(int(leg[1]), int(leg[2])))
		var error_degrees: float = absf(rad_to_deg(
			wrapf(actor.rotation.y - want, -PI, PI)))
		_expect(error_degrees < 1.0,
			"facing settles on the travel direction for command %d (off by %.2f deg)"
				% [int(leg[0]), error_degrees])
		# A quarter tile is where the arrival margin puts it. Anything that
		# keeps growing is the failure this test exists for.
		_expect(actor.global_position.distance_to(actor.server_target) < 0.6,
			"command %d leaves the actor within a tile of its own position (%.2f m)"
				% [int(leg[0]), actor.global_position.distance_to(actor.server_target)])
		var crossing_speed: float = 0.0
		if actor._segment_duration > 0.0:
			crossing_speed = (actor._segment_start.distance_to(
				actor.server_target) / actor._segment_duration)
		leg_speeds.append(crossing_speed)

	var slowest: float = leg_speeds.min()
	var fastest: float = leg_speeds.max()
	_expect(fastest <= slowest * 1.05,
		"all eight directions are walked at one speed (%.2f - %.2f m/s)"
			% [slowest, fastest])

	# Packets do not arrive on the server's cadence over a real link: the
	# outbox held each step for up to an AI tick, and a wireless hop holds one
	# back and then delivers the next on time behind it. The body used to
	# tolerate a quarter of a step of that and then stop and restart, and every
	# early packet after a late one was crossed at a sprint. Run east with
	# every fourth step held 120 ms and the one behind it arriving on schedule;
	# once the schedule has seen two holds, the body must neither stand still
	# while steps are still coming nor lurch to catch up.
	actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"command": 32}, adapter, true)
	_jitter_steps_sent = 0
	_send_jittered_run(actor, adapter)
	var last_position: Vector3 = actor.global_position
	var last_msec: int = Time.get_ticks_msec()
	var stalled_msec := 0
	var speeds: Array[float] = []
	while _jitter_steps_sent < JITTER_STEPS:
		await physics_frame
		var now_msec: int = Time.get_ticks_msec()
		var moved: float = actor.global_position.distance_to(last_position)
		var elapsed: int = now_msec - last_msec
		if _jitter_steps_sent >= 12 and _jitter_steps_sent < JITTER_STEPS and elapsed > 0:
			if moved < 0.0005:
				stalled_msec += elapsed
			else:
				speeds.append(moved * 1000.0 / float(elapsed))
		last_position = actor.global_position
		last_msec = now_msec
	speeds.sort()
	var median_speed: float = speeds[speeds.size() / 2] if not speeds.is_empty() else 0.0
	var peak_speed: float = speeds[speeds.size() - 1] if not speeds.is_empty() else 0.0
	_expect(stalled_msec <= 80,
		"a jittery packet stream no longer stops the body between steps (stood %d ms)"
			% stalled_msec)
	_expect(median_speed > 0.0 and peak_speed <= median_speed * 1.6,
		"a late packet is absorbed by the buffer rather than sprinted after (%.2f vs median %.2f m/s)"
			% [peak_speed, median_speed])
	_expect(actor.global_position.distance_to(actor.server_target) < 3.0,
		"the buffer a jittery link earns stays within a few tiles (%.2f m)"
			% actor.global_position.distance_to(actor.server_target))
	for _drain: int in range(4):
		await create_timer(cadence).timeout

	# Walking from bag to bag after a fight: one running step, a second or so
	# stood looting, another step. Every one of those gaps is a player standing
	# still, not the server's cadence, and it was folded into the pace anyway -
	# a handful of them and the median said a tile took a second, so the run
	# that followed crawled for its first steps while the body fell tiles
	# behind the server. Measured just before each step lands, the way the
	# lag above is.
	await _run_east(actor, adapter, 12, 0.2, true)
	for pause: float in [0.8, 1.2, 0.9, 1.4, 1.0, 0.7, 1.3, 1.1]:
		await create_timer(pause).timeout
		await _run_east(actor, adapter, 1, 0.0, false)
	await create_timer(1.0).timeout
	var worst_lag := 0.0
	for _hop_step: int in range(6):
		await _run_east(actor, adapter, 1, 0.2, false)
		worst_lag = maxf(worst_lag, actor.global_position.distance_to(actor.server_target))
	_expect(worst_lag < 0.8,
		"standing between bags does not slow the run that follows (fell %.2f m behind)"
			% worst_lag)
	for _drain_hops: int in range(6):
		await create_timer(cadence).timeout

	# The other side of it: a pace that really does slow - a creature that
	# stops pursuing and goes back to its ordinary walk sends its steps a
	# second apart from then on - must still be taken up, and quickly, even
	# though each of those gaps on its own looks like a pause.
	actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"command": 22}, adapter, true)
	_run_x = 0
	await _run_east(actor, adapter, 12, 0.25, false, 22)
	var slow_speeds: Array[float] = []
	for _slow_step: int in range(8):
		await _run_east(actor, adapter, 1, 1.0, false, 22)
		if actor._segment_duration > 0.0:
			slow_speeds.append(actor._segment_start.distance_to(actor.server_target)
				/ actor._segment_duration)
		else:
			slow_speeds.append(0.0)
	_expect(not slow_speeds.is_empty() and slow_speeds[slow_speeds.size() - 1] < 1.5,
		"a pace that really slows is taken up within a few steps (%.2f m/s)"
			% slow_speeds[slow_speeds.size() - 1])
	for _drain_slow: int in range(3):
		await create_timer(1.0).timeout

	# A redirect mid-path - clicking a new spot while a path still runs - must turn
	# the body to the new heading at once, since the facing is taken fresh from
	# each step rather than averaged over a window that would drag the old one in.
	# Walk east, reverse west.
	actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"command": 22}, adapter, true)
	var rx := 0
	for _east: int in range(6):
		rx += 1
		actor.apply_server_state({"actor_id": 7, "x": rx, "y": 0, "rotation": 0,
			"command": 22}, adapter)
		await create_timer(cadence).timeout
	var west: float = adapter.direction_to_godot(Vector2i(-1, 0))
	var redirect_settle := -1
	for s: int in range(6):
		rx -= 1
		actor.apply_server_state({"actor_id": 7, "x": rx, "y": 0, "rotation": 0,
			"command": 26}, adapter)
		await create_timer(cadence).timeout
		if redirect_settle < 0 and absf(rad_to_deg(
				wrapf(actor.rotation.y - west, -PI, PI))) < 10.0:
			redirect_settle = s + 1
	_expect(redirect_settle >= 0 and redirect_settle <= 2,
		"a mid-path redirect faces the new heading at once (took %d steps)"
			% redirect_settle)

	# The walk clip turns the body ~23 deg off its travel; the model correction
	# eases in as the walk clip blends in and turns the visual root back, so the
	# body a player sees faces the way it walks. It rides on the NativeModel node,
	# and is absent for the resting idle, so the two must differ by the correction.
	var native_model: Node3D = actor.get_node_or_null("NativeModel") as Node3D
	actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"command": 22}, adapter, true)
	actor.play_action(&"idle")
	for _settle: int in range(3):
		await create_timer(cadence).timeout
	var idle_model_yaw: float = native_model.rotation.y
	var wx := 0
	for _w: int in range(5):
		wx += 1
		actor.apply_server_state({"actor_id": 7, "x": wx, "y": 0, "rotation": 0,
			"command": 22}, adapter)
		await create_timer(cadence).timeout
	var walk_correction: float = absf(rad_to_deg(
		wrapf(native_model.rotation.y - idle_model_yaw, -PI, PI)))
	_expect(walk_correction > 15.0,
		"walking turns the model back onto its travel (%.1f deg from idle)"
			% walk_correction)

	# A creature turned to face the player it is attacking must stay turned.
	# The turn is an actor command and carries no rotation field, so the
	# rotation on the packet is still the one the actor spawned with. Reading
	# it for the attack commands that follow snapped the body back to its
	# spawn facing on every swing - a wolf hitting a player it faced away from.
	actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"command": 22}, adapter, true)
	for _still: int in range(3):
		await create_timer(cadence).timeout
	# CMD_TURN_W, then enter combat and two swings from the same tile.
	for standing_command: int in [44, 18, 46, 46]:
		actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
			"command": standing_command}, adapter)
		await create_timer(cadence).timeout
	var faced_west: float = absf(rad_to_deg(wrapf(
		actor.rotation.y - adapter.direction_to_godot(Vector2i(-1, 0)), -PI, PI)))
	_expect(faced_west < 1.0,
		"an actor keeps the facing it was turned to while it attacks (off by %.1f deg)"
			% faced_west)

	# And the same round as it really arrives. The server queues a creature's
	# turn and the swing behind it into one flush, so the client decodes both
	# in one read and renders the single state they reduce to - the turn is
	# never a frame of its own. Every aggressor in a multi-combat swings on
	# this shape, which is why a crowd of them all faced away at once.
	# Reset it facing west, so the eastward turn in the burst has somewhere to
	# turn from and a dropped one leaves the body pointing the wrong way.
	actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"command": 26}, adapter, true)
	for _still_again: int in range(3):
		await create_timer(cadence).timeout
	var burst: Dictionary = {"actor_id": 7, "x": 0, "y": 0, "rotation": 0}
	for burst_command: int in [40, 18]:
		burst = ActorReducer.apply_command(burst, burst_command)
	actor.apply_server_state(burst, adapter)
	for _round: int in range(3):
		burst = ActorReducer.apply_command(burst, 46)
		actor.apply_server_state(burst, adapter)
		await create_timer(cadence).timeout
	var faced_east: float = absf(rad_to_deg(wrapf(
		actor.rotation.y - adapter.direction_to_godot(Vector2i(1, 0)), -PI, PI)))
	_expect(faced_east < 1.0,
		"a turn coalesced into one frame with the swing behind it still turns the actor (off by %.1f deg)"
			% faced_east)

	print("actor facing tests: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _expect(value: bool, label: String) -> void:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)

const JITTER_STEPS := 26

var _run_x := 0

## `steps` steps east from wherever the last call left off, each held for
## `wait` seconds after it is sent - the server's convention, where a step's
## own length follows it. `reset` teleports back to the origin first.
func _run_east(actor: ReplicatedActor3D, adapter: CoordinateAdapter, steps: int,
		wait: float, reset: bool, command: int = 32) -> void:
	if reset:
		_run_x = 0
		actor.apply_server_state({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
			"command": command}, adapter, true)
	for _step: int in range(steps):
		_run_x += 1
		actor.apply_server_state({"actor_id": 7, "x": _run_x, "y": 0, "rotation": 0,
			"command": command}, adapter)
		if wait > 0.0:
			await create_timer(wait).timeout

## Running steps east at a 200 ms cadence, with every fourth step from the
## seventh held back 120 ms and the step behind it arriving when it would have
## anyway - the shape a wireless hold takes on the wire. Started without being
## awaited, so the caller can watch the body while the steps land.
func _send_jittered_run(actor: ReplicatedActor3D, adapter: CoordinateAdapter) -> void:
	var x := 0
	for step: int in range(JITTER_STEPS):
		x += 1
		actor.apply_server_state({"actor_id": 7, "x": x, "y": 0, "rotation": 0,
			"command": 32}, adapter)
		_jitter_steps_sent = step + 1
		var wait := 0.2
		if step >= 6 and step % 4 == 2:
			wait = 0.32
		elif step >= 6 and step % 4 == 3:
			wait = 0.08
		await create_timer(wait).timeout
