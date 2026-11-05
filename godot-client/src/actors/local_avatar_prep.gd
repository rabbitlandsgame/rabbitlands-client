extends RefCounted
## The player's own body waits behind the arrival curtain for its asset
## closure (AW-04d, wave-2 avatar-worker plan section 3.2, "Local avatar").
##
## Before, Main built the player's own body the moment its ADD was presented,
## and that one atomic `configure()` parsed on the main thread every race,
## hair and equipment glTF of it the session had not parsed yet (the first
## local build of a session: 622-669 ms of parses on the 4c/8t Xeon proxy,
## plan section 1). Now, while the arrival curtain is up, Main asks the actor
## preparer (actor_resource_warmup.gd) for the body's closure
## (actor_asset_closure.gd) at PRIORITY_LOCAL as soon as the record is known -
## the map change's or the arrival's held world sync - so the parses overlap
## the world build, and builds the body once the preparer holds every file
## (main.gd `_local_body_ready`, `_prepare_local_closure`).
##
## The wait can never strand an arrival:
## - it lasts at most `timeout_msec` (TIMEOUT_MSEC) from its first not-ready
##   ask; then, and every ask after, the answer is "build now", and the body
##   is built as before (main parses whatever the worker has not finished);
## - a file the worker could not prepare counts as ready already (the
##   preparer leaves it to main: its fallback);
## - with the curtain down nothing waits (the player would stand without a
##   body in view): the body is built at once, as before.
## Main gates nothing on the web build, with closures off
## (ELORIA_ACTOR_PREPARER=off and the other preparer-off states) or for a
## body held across the map change that the ADD wears again (AW-02).
##
## Main owns every call; this owns the one wait, its deadline and its
## counters. Main thread.

## How long the player's body waits for its closure behind the curtain.
const TIMEOUT_MSEC := 6000

## TIMEOUT_MSEC; tests lower it.
var timeout_msec := TIMEOUT_MSEC
var _id := -1
## When the current wait began (its first not-ready ask), or -1.
var _since := -1
## When it ended (the first "build now" after it began), or -1: what the wait
## lasted, not counting the build that follows.
var _released_at := -1
## The last answer for the current wait: "ready", "uncurtained", "waiting" or
## "timeout" (what `built` reports; `abandon` counts "abandoned").
var _answer := ""
var _early_key := ""
## Local bodies built at once (nothing to wait for or no curtain), built after
## a wait for each outcome, early requests made, waits begun.
var built_at_once := 0
var built_uncurtained := 0
var waits := 0
var outcomes: Dictionary = {}
var early_requests := 0
var last_wait_msec := -1
var maximum_wait_msec := 0

## Whether the player's body (actor `id`) may be built now: its closure is
## `ready`, or the arrival curtain is not `curtained`, or its wait has lasted
## `timeout_msec`. Asked again every frame while it waits, and once more by
## `_spawn_actor` for the build itself: an answer stays "build now" once the
## deadline has passed, until `built` or `clear`.
func admit(id: int, ready: bool, curtained: bool, now: int) -> bool:
	if id != _id:
		_begin(id)
	if ready:
		return _release("ready", now)
	if not curtained:
		return _release("uncurtained", now)
	if _since < 0:
		_since = now
		waits += 1
	if now - _since >= timeout_msec:
		return _release("timeout", now)
	_answer = "waiting"
	_released_at = -1
	return false

func _release(answer: String, now: int) -> bool:
	_answer = answer
	if _since >= 0 and _released_at < 0:
		_released_at = now
	return true

## Whether a wait for the player's body has begun and the body is not built
## yet (also once the answer is "build now", until `built`).
func waiting() -> bool:
	return _since >= 0

## The player's body was built: its wait ends. Returns {outcome, wait_ms}
## when it had waited (from its first ask to the answer "build now"; {} when
## built at once), for Main's diagnostics record.
func built(id: int, now: int) -> Dictionary:
	var result := {}
	if id == _id and _since >= 0:
		var wait := maxi(0, (_released_at if _released_at >= 0 else now) - _since)
		result = {"outcome": _answer if _answer != "waiting" else "ready", "wait_ms": wait}
		outcomes[result.outcome] = int(outcomes.get(result.outcome, 0)) + 1
		last_wait_msec = wait
		maximum_wait_msec = maxi(maximum_wait_msec, wait)
	elif id == _id and _answer == "uncurtained":
		built_uncurtained += 1
	else:
		built_at_once += 1
	_begin(-1)
	return result

## An early request for the closure named `key` (counted once per closure).
func note_early(id: int, key: String) -> void:
	if id != _id:
		_begin(id)
	var named := "%d#%s" % [id, key]
	if named != _early_key:
		_early_key = named
		early_requests += 1

## Session end: no wait carries over.
func clear() -> void:
	_begin(-1)

## A change of map that is not a seamless crossing (main.gd
## `_clear_actor_nodes_for_map_change`): a wait whose body was never built -
## its record went with KILL_ALL_ACTORS ahead of the CHANGE_MAP - ends unbuilt
## (outcome "abandoned"), so its deadline is not handed to the next arrival's
## wait, which begins at its own first ask. Early requests stay counted once
## for the closure they named.
func abandon() -> void:
	if _since >= 0:
		outcomes["abandoned"] = int(outcomes.get("abandoned", 0)) + 1
	_since = -1
	_released_at = -1
	_answer = ""

func _begin(id: int) -> void:
	_id = id
	_since = -1
	_released_at = -1
	_answer = ""
	_early_key = ""

## Diagnostics (main.gd `client_diagnostic_snapshot`, `local_avatar_prep`).
## Counts and times only.
func snapshot(now: int = -1) -> Dictionary:
	var at := Time.get_ticks_msec() if now < 0 else now
	return {"waiting": _since >= 0, "waitingForMsec": (at - _since) if _since >= 0 else 0,
		"timeoutMsec": timeout_msec, "waits": waits, "outcomes": outcomes.duplicate(),
		"builtAtOnce": built_at_once, "builtUncurtained": built_uncurtained,
		"earlyRequests": early_requests, "lastWaitMsec": last_wait_msec,
		"maximumWaitMsec": maximum_wait_msec}
