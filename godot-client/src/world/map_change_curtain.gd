extends RefCounted
## TR-01: a change of map that is not a seamless crossing happens behind the
## arrival curtain. Main (`_load_server_map`) used to wait for a drawn curtain
## only before building a whole map; a streamed territory, a resident neighbour
## reached without a seamless crossing (an exterior handoff that is not
## continuous) and the ground a respawn or gauntlet exit prewarmed were adopted
## on the frame CHANGE_MAP arrived, so the frames binding that world and
## building its actors were shown frozen before the curtain came up (about six
## frames of 230-556 ms per two route cells on the F+ LOW traversal). Each now
## waits until the curtain has been drawn, a frame or two later.
##
## This object is Main's bookkeeping for that wait: which map change is waiting
## and for what, the focus an exterior handoff is judged from, and counters.
## It also holds the one rule Main needs from ExteriorRegionStream before it
## takes anything (`handoff_continuous`), the grace after which a curtained
## arrival that found no ground asks for its neighbours (`grounding_due`), and
## whether the arrival behind a curtain this wait raised skips the
## Compatibility camera shader warm-up (`skips_warmup`).
## No class_name: preloaded by path.

## A whole map: built on the frame it loads (the wait develop already had).
const WHOLE_MAP := &"whole_map"
## A streamed territory loaded fresh: its manifest, the map binding and the
## actors already received happen on the frame it loads.
const STREAMED := &"streamed"
## A resident neighbour adopted without a seamless crossing (a non-continuous
## ExteriorRegionStream.take_ready handoff).
const EXTERIOR := &"exterior"
## A respawn's or gauntlet exit's prewarmed ground (ArrivalPrewarm.take).
const PREWARM := &"prewarm"
## The waits that are only for the curtain to be drawn and then build the
## arrival's actors on that same frame. The local RL head is not prewarmed on a
## worker for these: its build would parse the same files again beside it.
const SHORT_WAITS: Array[StringName] = [STREAMED, EXTERIOR, PREWARM]
## How long a character built behind the curtain may stand without ground
## before the exterior neighbours are updated from where it stands. An arrival
## whose own cells end short of a seam stands only on the neighbour's preview
## layer, and behind the curtain that neighbour was never asked for: the
## curtain waited out its 60 s limit (AW-00 finding 2). An ordinary arrival
## grounds within a few frames of its cells.
const GROUNDING_GRACE_MSEC := 1000

## Waits begun, by kind (String keys, for JSON snapshots).
var deferrals: Dictionary = {}
## The map change waiting now: {"map", "kind", "focus", "at_msec", "raised"};
## empty when none. It lives only while Main's `_deferred_map_load` is set: a
## wait that ends without a load is abandoned (`abandon`, `clear`).
var pending: Dictionary = {}
## The last wait that ended in a load: {"map", "kind", "msec"}.
var last_wait: Dictionary = {}
## Curtained arrivals that found no ground and asked for their neighbours.
var grounding_waits := 0
## Exterior updates made for them (one per frame while they wait).
var grounding_updates := 0
## True for the one `grounding_due` call that begins such a wait.
var grounding_first := false
## True while the curtain on screen is one this wait raised itself for ground
## already prepared (EXTERIOR or PREWARM): before TR-01 such an arrival had no
## curtain, so no Compatibility camera shader warm-up either, and it gets none
## now (`skips_warmup`). The plan's cost for TR-01 is a frame or two; the
## warm-up's sweep is seconds on the machines that run Compatibility. Main
## clears it when the arrival loads its own cells (that arrival was curtained,
## and warmed, before TR-01 too) and when the curtain is gone.
var warmup_exempt := false
## Arrivals whose Compatibility warm-up was skipped that way.
var warmups_skipped := 0
var _ungrounded_since := -1
var _grounding_counted := false
var _warmup_skip_counted := false

## Records that the change to `map_id` waits for the curtain. False when the
## same change was already waiting (it is not counted twice). `raised`: this
## wait began the curtain itself (see `warmup_exempt`).
func defer(map_id: String, kind: StringName, focus: Vector3, now: int, raised := false) -> bool:
	if not pending.is_empty() and str(pending.map) == map_id and pending.kind == kind:
		return false
	pending = {"map": map_id, "kind": kind, "focus": focus, "at_msec": now, "raised": raised}
	deferrals[String(kind)] = int(deferrals.get(String(kind), 0)) + 1
	return true

## The change to `map_id` goes ahead now (or none was waiting). Its wait is
## recorded when it was this change's own. `prepared`: the change adopts ground
## prepared ahead (a resident neighbour or a prewarm), not a fresh load;
## `raised_now`: it raised the curtain on this very call (a curtain still
## fading out counts as drawn, so nothing waited).
func resumed(now: int, map_id := "", prepared := false, raised_now := false) -> void:
	var raised := raised_now
	if not pending.is_empty() and (map_id.is_empty() or str(pending.map) == map_id):
		last_wait = {"map": str(pending.map), "kind": String(pending.kind),
			"msec": now - int(pending.at_msec)}
		raised = raised or (bool(pending.get("raised", false)) and pending.kind in [EXTERIOR, PREWARM])
	pending = {}
	_set_warmup_exempt(prepared and raised)

## Forgets a waiting change that will not go ahead (the map it was leaving
## came back before the curtain was drawn), keeping the arrival's state.
func abandon() -> void:
	pending = {}

## Forgets the waiting change (the arrival ended, or another kind of wait took
## over) and any grounding wait.
func clear() -> void:
	pending = {}
	_ungrounded_since = -1
	_grounding_counted = false
	grounding_first = false
	_set_warmup_exempt(false)

## The arrival on screen needs the curtain on its own account (it loads its
## cells), or the curtain is gone: the Compatibility warm-up runs as before.
func end_warmup_exemption() -> void:
	_set_warmup_exempt(false)

## Whether the arrival behind the curtain skips the Compatibility camera
## shader warm-up (`warmup_exempt`); counted once per arrival.
func skips_warmup() -> bool:
	if warmup_exempt and not _warmup_skip_counted:
		_warmup_skip_counted = true
		warmups_skipped += 1
	return warmup_exempt

func _set_warmup_exempt(exempt: bool) -> void:
	warmup_exempt = exempt
	_warmup_skip_counted = false

## Whether the waiting change is one of SHORT_WAITS.
func short_wait() -> bool:
	return not pending.is_empty() and SHORT_WAITS.has(pending.kind)

## Whether the waiting change is `kind` to `map_id`.
func waiting_for(kind: StringName, map_id: String) -> bool:
	return not pending.is_empty() and not map_id.is_empty() and pending.kind == kind \
		and str(pending.map) == map_id

## The position an exterior handoff to `map_id` is judged from: where the
## camera stood when CHANGE_MAP arrived, if that change waited for the curtain,
## so the handoff is the one that change would have made; else `fallback`.
func handoff_focus(map_id: String, fallback: Vector3) -> Vector3:
	if waiting_for(EXTERIOR, map_id):
		var focus: Vector3 = pending.focus
		if focus.is_finite():
			return focus
	return fallback

## True when a curtained arrival (`waiting`: built, its own cells in, still no
## ground) has waited GROUNDING_GRACE_MSEC; `grounding_first` marks the call
## that begins it. False, and the wait forgotten, when `waiting` is false.
func grounding_due(waiting: bool, now: int) -> bool:
	grounding_first = false
	if not waiting:
		_ungrounded_since = -1
		return false
	if _ungrounded_since < 0:
		_ungrounded_since = now
		_grounding_counted = false
	if now - _ungrounded_since < GROUNDING_GRACE_MSEC:
		return false
	grounding_updates += 1
	if not _grounding_counted:
		_grounding_counted = true
		grounding_waits += 1
		grounding_first = true
	return true

func snapshot(now: int) -> Dictionary:
	var waiting: Dictionary = {}
	if not pending.is_empty():
		waiting = {"map": str(pending.map), "kind": String(pending.kind),
			"waited_ms": now - int(pending.at_msec)}
	return {"deferrals": deferrals.duplicate(), "pending": waiting,
		"last_wait": last_wait.duplicate(), "grounding_waits": grounding_waits,
		"grounding_updates": grounding_updates, "warmup_exempt": warmup_exempt,
		"warmups_skipped": warmups_skipped}

## Whether ExteriorRegionStream.take_ready(destination, loader, position) would
## hand `destination` over as a seamless (continuous) crossing - the same
## judgement, made without taking the resident. False when it is not resident.
static func handoff_continuous(stream: ExteriorRegionStream, destination: String,
		position: Vector3) -> bool:
	if stream == null or not stream.residents.has(destination):
		return false
	var join: Dictionary = {}
	for candidate: Dictionary in stream._candidates(position):
		if str(candidate.map) == destination:
			join = candidate
			break
	var collar := float(join.get("here", {}).get("frame", {}).get("collarDepth", 42))
	return ExteriorRegionStream.continuous_crossing(bool(join.get("seamless", false)),
		float(join.get("handoff_distance", INF)), collar)
