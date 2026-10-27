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
##   wandering more than 48 tiles away for a minute drops it, and so does five
##   minutes of standing by without going in (it is not built again until the
##   player has walked away from its doors and come back).

## How long a parked world is kept while the player stays away from it.
const PARK_TTL_MSEC := 600000
## A flagged interior starts loading when the player is this close (tiles) to
## one of its doors...
const PRELOAD_RADIUS_TILES := 24.0
## ...and is dropped once the player has been farther than this...
const PRELOAD_DROP_TILES := 48.0
## ...for this long.
const PRELOAD_DROP_MSEC := 60000
## A finished preload nobody entered is dropped after this long, however near
## the player stays: a town's interiors hold ~424 MiB of textures.
const PRELOAD_READY_TTL_MSEC := 300000
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
## Interiors whose parking stays off until it is measured: the Landfall
## underground loads ~1.2 GB at its peak (docs/client-interior-preparation-
## performance.md), and keeping Landfall beside it, or it beside Landfall, has
## not been measured. Enter `{}` in a test or an experiment to lift this.
const HELD_INTERIORS := {"landfall_insides": "measure memory before parking (SPEC 8)"}

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
## (a build of it expired while the player stood by), "settled": bool (the
## map the player stands on has finished loading their arrival; default
## true)}. Returns "start", "drop", "keep" or "none", and updates
## `state.far_since_msec` and `state.stale` (cleared once the player is
## farther than the start radius from every door).
static func preload_action(state: Dictionary, distance_tiles: float, now_msec: int) -> String:
	var active := bool(state.get("active", false))
	if not active:
		if bool(state.get("stale", false)):
			if distance_tiles > PRELOAD_RADIUS_TILES:
				state["stale"] = false
			return "none"
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

## Whether a preload that finished at `ready_msec` (-1: not finished) has
## been kept too long unentered at `now_msec`.
static func preload_expired(ready_msec: int, now_msec: int, ttl_msec: int = PRELOAD_READY_TTL_MSEC) -> bool:
	return ready_msec >= 0 and now_msec - ready_msec > ttl_msec

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
