extends RefCounted
## What WorldPark decides, kept apart from nodes, threads and files so that the
## rules can be tested on their own (tests/test_world_park.gd).
##
## The owner's rules (2026-10-27, SPEC section 8):
## - Entering an interior from the map it belongs to (its parent region) keeps
##   that map's world in memory, detached and paused, and re-attaches it on the
##   way back out. Leaving an interior for its parent keeps the interior the
##   same way, so going back and forth is instant both ways.
## - At most one world is parked: the map just left. Travel anywhere else
##   evicts it, and so do ~10 minutes away and the memory budget. A parent
##   stays parked for as long as the player is inside one of its interiors.
## - Near a door of an interior flagged for it (registry preloadOnApproach),
##   that interior is built in the background, ready for the map change;
##   wandering more than 48 tiles away for a minute drops it. Standing by
##   without going in does not (final review 2026-10-27: the Town is ~120 MiB
##   against the 1.5 GiB budget, and its ten doors ring the town centre where
##   players linger): a built interior - preloaded, or parked after a visit -
##   is let go while the player stays in its area only under memory-budget
##   pressure (the kept worlds' estimates over BUDGET_BYTES). One let go while
##   the player stood by is built again once they come within
##   PRELOAD_REARM_TILES of one of its doors (or after they have walked away).

## How long a parked world is kept while the player stays away from it (a
## parked interior's clock only runs while the player is outside its area,
## PRELOAD_DROP_TILES from its doors).
const PARK_TTL_MSEC := 600000
## A flagged interior starts loading when the player is this close (tiles) to
## one of its doors...
const PRELOAD_RADIUS_TILES := 24.0
## ...and is dropped once the player has been farther than this...
const PRELOAD_DROP_TILES := 48.0
## ...for this long.
const PRELOAD_DROP_MSEC := 60000
## A build let go while the player stood by (budget pressure) is started again
## when the player comes this close (tiles) to one of its doors.
const PRELOAD_REARM_TILES := 8.0
## A preload that failed is not tried again for this long.
const PRELOAD_RETRY_MSEC := 30000
## How long a map change waits behind the curtain for a preload whose worker
## is still running, before it gives up and loads the map itself.
const PRELOAD_WAIT_LIMIT_MSEC := 15000
## The estimated bytes parked and preloaded worlds may hold together. An
## interior is estimated from its textures' pixels (texture_footprint.gd), a
## streamed territory by its own budget; the measured figures belong to the
## integration run (tests/integration/landfall_town_park.gd).
const BUDGET_BYTES := 1536 * 1048576
## What an interior holds beyond its textures: its geometry, collision and
## nodes (the Town's 1,771 nodes and 818 KB shell measured ~26 MiB of RAM).
const INTERIOR_FLOOR_BYTES := 32 * 1048576
## All declared parent/interior pairs use parking, including Landfall's
## underground. The shared byte budget still bounds retained worlds. A caller
## may supply individual holds for diagnostics.
const HELD_INTERIORS := {}

## How `to` relates to `from`: "enter" when `to` is an interior of `from`,
## "leave" when `from` is an interior of `to`, else "". `parents` maps an
## interior's id to its parent map's id.
static func relation(from: String, to: String, parents: Dictionary) -> String:
	if from.is_empty() or to.is_empty() or from == to:
		return ""
	if str(parents.get(to, "")) == from:
		return "enter"
	if str(parents.get(from, "")) == to:
		return "leave"
	return ""

## Whether the world of `from` is kept when the player travels to `to`.
static func should_park(from: String, to: String, parents: Dictionary,
		held: Dictionary = HELD_INTERIORS) -> bool:
	var kind := relation(from, to, parents)
	if kind.is_empty():
		return false
	var interior := to if kind == "enter" else from
	return not held.has(interior)

## Which of the parked map ids are evicted by travel from `from` to `to`:
## every one except the destination (it is about to be re-attached).
## `from` itself is not parked yet at this point, so it never appears.
static func evicted_by_travel(parked: Array, to: String) -> Array:
	var result: Array = []
	for map_id: Variant in parked:
		if str(map_id) != to:
			result.append(str(map_id))
	return result

## The parked map ids (`parked`: id -> {"at_msec": int}) that have been kept
## longer than `ttl_msec` at `now_msec`.
static func expired(parked: Dictionary, now_msec: int, ttl_msec: int = PARK_TTL_MSEC) -> Array:
	var result: Array = []
	for map_id: Variant in parked:
		var row: Dictionary = parked[map_id]
		if now_msec - int(row.get("at_msec", now_msec)) > ttl_msec:
			result.append(str(map_id))
	return result

## The ids to evict, oldest first, so that the kept worlds' estimates fit
## `budget` together with `incoming` more bytes. `parked`: id ->
## {"at_msec": int, "bytes": int}.
static func over_budget(parked: Dictionary, incoming: int, budget: int = BUDGET_BYTES) -> Array:
	var total := incoming
	var order: Array = parked.keys()
	for map_id: Variant in order:
		total += int((parked[map_id] as Dictionary).get("bytes", 0))
	order.sort_custom(func(a: Variant, b: Variant) -> bool:
		return int((parked[a] as Dictionary).get("at_msec", 0)) < int((parked[b] as Dictionary).get("at_msec", 0)))
	var result: Array = []
	for map_id: Variant in order:
		if total <= budget:
			break
		total -= int((parked[map_id] as Dictionary).get("bytes", 0))
		result.append(str(map_id))
	return result

## What to do about a preload this frame, given the player's distance in
## tiles to the nearest door of the interior (INF for no door in sight) and
## the preload's state: {"active": bool (started, running or ready),
## "far_since_msec": int (-1 while near), "retry_at_msec": int, "stale": bool
## (a build of it was let go while the player stood by), "settled": bool (the
## map the player stands on has finished loading their arrival, and nothing
## else holds the start; default true)}. Returns "start", "drop", "keep" or
## "none", and updates `state.far_since_msec` and `state.stale` (cleared once
## the player is farther than the start radius from every door, or re-armed
## within PRELOAD_REARM_TILES of one).
static func preload_action(state: Dictionary, distance_tiles: float, now_msec: int) -> String:
	var active := bool(state.get("active", false))
	if not active:
		if bool(state.get("stale", false)):
			if distance_tiles > PRELOAD_RADIUS_TILES:
				state["stale"] = false
				return "none"
			if distance_tiles > PRELOAD_REARM_TILES:
				return "none"
			state["stale"] = false # At a door again: re-armed.
		if distance_tiles <= PRELOAD_RADIUS_TILES and now_msec >= int(state.get("retry_at_msec", 0)) \
				and bool(state.get("settled", true)):
			return "start"
		return "none"
	if distance_tiles <= PRELOAD_DROP_TILES:
		state["far_since_msec"] = -1
		return "keep"
	var since := int(state.get("far_since_msec", -1))
	if since < 0:
		state["far_since_msec"] = now_msec
		return "keep"
	return "drop" if now_msec - since > PRELOAD_DROP_MSEC else "keep"

## Whether the kept worlds (`kept`: id -> {"bytes": int}, the parked worlds
## and a preload) are over `budget` together: memory-budget pressure, the one
## reason a built interior is let go while the player stays in its area.
static func under_pressure(kept: Dictionary, budget: int = BUDGET_BYTES) -> bool:
	var total := 0
	for map_id: Variant in kept:
		total += int((kept[map_id] as Dictionary).get("bytes", 0))
	return total > budget

## Straight-line distance in tiles between two server tiles.
static func tile_distance(a: Vector2i, b: Vector2i) -> float:
	return Vector2(a).distance_to(Vector2(b))

## A coarse estimate of what a whole-map world holds once loaded: its GLB's
## size on disk, decoded about threefold, plus a floor for its nodes and
## scenery. Used only when an interior's textures could not be read; a
## streamed territory reports its own estimate instead.
static func whole_map_estimate(glb_bytes: int) -> int:
	return maxi(0, glb_bytes) * 3 + 32 * 1048576

## An interior's estimate: its textures (shell and scenery, from their image
## headers: texture_footprint.gd) plus its shell GLB's bytes (geometry) and a
## floor for nodes and collision.
static func interior_estimate(texture_bytes: int, glb_bytes: int) -> int:
	return maxi(0, texture_bytes) + maxi(0, glb_bytes) + INTERIOR_FLOOR_BYTES
