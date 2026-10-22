extends RefCounted
## Remote movement timed by when the server took each step, rather than by
## when its packet happened to arrive.
##
## Arrival-time pacing (`ReplicatedActor3D.apply_server_state`) measures each
## actor's cadence from the gaps between arrivals and holds the body a margin
## of a quarter step, plus the worst recent lateness, behind the newest tile.
## Every hold on the link is read as a slower step and every burst behind it as
## a faster one, so the median and the margin are there to absorb jitter the
## timestamps never had.
##
## When the server stamps its frames with its own clock, `AppState` puts on
## each actor that moved the local time the server took the step at (through
## the shared `ServerClock`) and the playout delay the link needs, under the
## keys below. The actor then measures its cadence from those times - exact up
## to the frame the step went out in - and schedules the step to finish one
## cadence after it was taken, plus the playout delay, on the same continuing
## schedule it already keeps. One delay serves every actor, because it belongs
## to the link rather than to the actor.
##
## Several steps of one actor folded into one presentation pass keep the time
## of the first of them: that is when the body set off across the ground the
## fold covers, so `first step time + cadence of the whole fold` is when it
## arrives, on a steady walk exactly what the server's deadlines say.

## The local tick (msec) the server took this actor's first step since the
## last presentation pass, as `ServerClock.to_local_msec` maps it.
const STEP_KEY := "step_local_msec"
## The playout delay to hold the body behind that schedule, in seconds.
const PLAYOUT_KEY := "step_playout_s"
## Which presentation pass the stamp belongs to (`AppState` counts them).
const PASS_KEY := "step_pass"
## How fast a schedule that has run ahead is trimmed back, as a multiple of the
## pace. Arrival pacing trims at 1.25 because its "earliest" bound is noisy and
## mostly right; a stamped bound is only ever late by the frame a step waited
## for, so trimming fast would undo the envelope the schedule settles on and
## make the body speed up and slow down by that much every few steps.
const CATCH_UP := 1.03

## Whether an actor command moves its actor one tile (walk 20-27, run 30-37).
static func is_step_command(command: int) -> bool:
	return (command >= 20 and command <= 27) or (command >= 30 and command <= 37)

## Puts the step time on `actor` unless it already holds one from this pass.
static func stamp(actor: Dictionary, local_msec: int, playout_seconds: float,
		pass_id: int) -> void:
	if int(actor.get(PASS_KEY, -1)) == pass_id and actor.has(STEP_KEY):
		return
	actor[STEP_KEY] = local_msec
	actor[PLAYOUT_KEY] = playout_seconds
	actor[PASS_KEY] = pass_id

## Takes the stamp off, for a step whose frame carried no server time: an old
## stamp left on the dictionary would read as a step taken in the past.
static func unstamp(actor: Dictionary) -> void:
	actor.erase(STEP_KEY)
	actor.erase(PLAYOUT_KEY)
	actor.erase(PASS_KEY)

## Stamps every actor an ADD_ACTOR_COMMAND payload stepped (3-byte records:
## actor id u16 LE, command u8), for the native reducer's path, which applies
## the packet without handing the commands back. `skip_actor_id` (the player's
## own actor) is left on arrival pacing. A negative `local_msec` takes the
## stamps off instead. Returns how many actors it touched.
static func stamp_payload(actors: Dictionary, payload: PackedByteArray,
		local_msec: int, playout_seconds: float, pass_id: int,
		skip_actor_id: int) -> int:
	var touched := 0
	for offset: int in range(0, payload.size() - 2, 3):
		if not is_step_command(payload[offset + 2]):
			continue
		var actor_id: int = payload[offset] | (payload[offset + 1] << 8)
		if actor_id == skip_actor_id:
			continue
		var actor: Variant = actors.get(actor_id)
		if not actor is Dictionary:
			continue
		if local_msec < 0:
			unstamp(actor as Dictionary)
		else:
			stamp(actor as Dictionary, local_msec, playout_seconds, pass_id)
		touched += 1
	return touched

## When a stamped step should finish, in seconds on the local tick clock.
## `step_seconds` is the stamp; `last_due` when the previous step was due to
## finish (anything earlier with no schedule); `cadence` how long the server
## holds this step. The same continuing schedule as
## `ReplicatedActor3D.scheduled_arrival`, with the earliest bound one cadence
## plus the playout delay after the step was taken.
static func due_seconds(step_seconds: float, last_due: float, cadence: float,
		playout_seconds: float) -> float:
	var continued: float = last_due + cadence
	var earliest: float = step_seconds + cadence + playout_seconds
	if continued <= earliest:
		return earliest
	return maxf(earliest, last_due + cadence / CATCH_UP)
