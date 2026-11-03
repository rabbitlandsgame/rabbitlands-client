extends RefCounted
## Public, synthetic fixtures only. These coordinates come from the maintained
## southern-streaming-walk and southern-region-routes fixtures. The client driver
## exercises presentation/streaming; it does not certify server pathfinding.
const MountProfiles := preload("res://src/mounts/mount_profiles.gd")
## Keep the measured Phase 1/5/6 cohort stable as the product catalog expands.
## Giant Rat deliberately exercises the ordinary fallback beside five native profiles.
const MIXED_MOUNT_PROFILE_IDS := ["crystalback_tortoise", "giant_rat",
	"golden_plains_horse", "jadefeather_raptor", "moor_pony", "rabbit"]

static func resolution(value: String) -> Vector2i:
	var parts := value.to_lower().split("x")
	if parts.size() != 2 or not parts[0].is_valid_int() or not parts[1].is_valid_int():
		return Vector2i(1280, 720)
	return Vector2i(clampi(int(parts[0]), 320, 7680), clampi(int(parts[1]), 240, 4320))

static func mount_rows(records: Dictionary, count: int, map_id: String) -> Dictionary:
	var rows := {}
	var ids := records.keys()
	ids.sort()
	var profiles: Array = MIXED_MOUNT_PROFILE_IDS
	# Include the local player. Product catalog additions belong to separate
	# coverage fixtures, rather than silently changing this historical workload.
	for index: int in mini(count, ids.size()):
		var id := int(ids[index])
		var record := records[id] as Dictionary
		record["map"] = map_id
		var profile := str(profiles[index % profiles.size()])
		rows[id] = {"schema_version": 1, "actor_id": id, "owner": str(record.name),
			"map": map_id, "mode": "mounted", "gait": "cruise", "mount_id": profile,
			"selected_mount_id": profile, "step_us": 133333, "endurance_ms": 60000,
			"summon_remaining_ms": 0, "combat_remaining_ms": 0,
			"can_summon": false, "blocked_reason": ""}
	return rows

static func mount_profile_counts(rows: Dictionary) -> Dictionary:
	var counts := {}
	for row: Dictionary in rows.values():
		var id := str(row.mount_id)
		counts[id] = int(counts.get(id, 0)) + 1
	return counts

## Route fixture version, reported with every traversal cell. Version 1 placed
## the route's start and return on whitehorn [118,19] (151.8 m from any streamed
## cell: an uncovered arrival that re-primed every world sync and never
## grounded) and jumped the actor 87-330 m across the same map between legs.
## Version 2 (wave 2 AW-00) starts and returns on covered ground beside the
## Whitehorn/Amethyst road seam, starts every leg but one where the previous
## one arrived, walks up to the interior door, and adds the walking seam route. Compare
## traversal numbers only between reports of the same version.
const ROUTE_VERSION := 2
## Milliseconds between the synthetic local player's step commands on a walk.
const WALK_STEP_MSEC := 600
## A mounted cruise (7.5 tiles/s, the 133 ms server step): the seam walk.
const CRUISE_STEP_MSEC := 133

## The six-leg southern route. Each leg starts where the previous one arrived,
## except the one `relocateStart` leg, and the last arrives where the first
## starts, so a warm repeat begins without a load. Every territory tile is
## inside a streamed chunk, and no border approach is within the continuous
## crossing slack of its destination's seam (tests/test_performance_workloads.gd),
## so border legs stay curtain map changes as in version 1.
static func southern_route() -> Array[Dictionary]:
	return [
		{"id": "first-southern-border", "kind": "border", "map": "whitehorn_range",
			"start": [601, 241], "approach": [589, 241],
			"destination": "mirrorhold", "arrival": [130, 370]},
		{"id": "consecutive-southern-border", "kind": "border", "map": "mirrorhold",
			"start": [130, 370], "approach": [130, 378],
			"destination": "amethyst_barrens", "arrival": [10, 308]},
		# The door sits 7.6 m from the Mirrorhold seam, where Amethyst Barrens has
		# no ground of its own: an actor there stands only on Mirrorhold's preview
		# layer. Arriving there behind a curtain never grounds, because Main
		# requests no neighbour while the curtain is up, so the curtain waits for
		# its 60 s limit (measured headless, AW-00; traversal audit M1). The leg
		# therefore keeps version 1's same-map relocation to the door's
		# surroundings (its frames are in `frameRanges.start`) and walks up.
		# amethyst_barrens_secrets is not flagged preloadOnApproach in the
		# registry, so WorldPark builds it on arrival whatever the walk-up: the
		# cold whole-map build here is what players get, not a fixture artifact.
		{"id": "interior-entry", "kind": "interior", "map": "amethyst_barrens",
			"start": [198, 40], "approach": [198, 34], "relocateStart": true,
			"destination": "amethyst_barrens_secrets", "arrival": [298, 26]},
		{"id": "interior-return", "kind": "interior_return", "map": "amethyst_barrens_secrets",
			"start": [298, 26], "approach": [297, 26],
			"destination": "amethyst_barrens", "arrival": [198, 34]},
		{"id": "teleport", "kind": "teleport", "map": "amethyst_barrens",
			"start": [198, 34], "approach": [198, 34],
			"destination": "sunmane_steppe", "arrival": [137, 95]},
		{"id": "return", "kind": "teleport_return", "map": "sunmane_steppe",
			"start": [137, 95], "approach": [137, 95],
			"destination": "whitehorn_range", "arrival": [601, 241]},
	]

## One real walking seam crossing (wave 2 AW-00): the player cruises 190 tiles
## west along Amethyst Barrens (169 m from the seam, beyond the 160 m low-tier
## preload distance TR-03 proposes) to the road seam and steps across into
## Whitehorn Range, arriving on the southern route's start tile. The client
## judges the change continuous when Whitehorn is a resident neighbour and the
## camera focus is within the crossing slack of the seam
## (ExteriorRegionStream.take_ready); the leg reports what it got.
static func seam_route() -> Array[Dictionary]:
	return [
		{"id": "walking-seam", "kind": "seam", "map": "amethyst_barrens",
			"start": [212, 227], "approach": [22, 227], "stepMsec": CRUISE_STEP_MSEC,
			"expectContinuous": true,
			"destination": "whitehorn_range", "arrival": [601, 241]},
	]

## Landfall and its underground, in and out twice (wave-2 memory measurement,
## MEM-M2: "private bytes after leaving the underground are ~1.4 GB lower on
## small"). The door is The Old Warren (object 59016): Landfall's exterior door
## tile [56, 303], its return tile [56, 298] and the underground's portal tile
## [142, 492] (landfall_insides world.json portals). The first entry walks up
## from 30 tiles out, through the 24-tile preload radius, as a player would;
## each exit holds the player on the return tile for `dwellMsec` while the
## refused (small) or parked (medium, large) underground is freed or kept.
const UNDERGROUND_DWELL_MSEC := 20000

static func underground_route() -> Array[Dictionary]:
	return [
		{"id": "underground-entry", "kind": "interior", "map": "landfall",
			"start": [56, 268], "approach": [56, 300],
			"destination": "landfall_insides", "arrival": [142, 492]},
		{"id": "underground-exit", "kind": "interior_return", "map": "landfall_insides",
			"start": [142, 492], "approach": [142, 492], "dwellMsec": UNDERGROUND_DWELL_MSEC,
			"destination": "landfall", "arrival": [56, 298]},
		{"id": "underground-reentry", "kind": "interior", "map": "landfall",
			"start": [56, 298], "approach": [56, 300],
			"destination": "landfall_insides", "arrival": [142, 492]},
		{"id": "underground-reexit", "kind": "interior_return", "map": "landfall_insides",
			"start": [142, 492], "approach": [142, 492], "dwellMsec": UNDERGROUND_DWELL_MSEC,
			"destination": "landfall", "arrival": [56, 298]},
	]

## The route a traversal cell drives: `southern` (default), `seam` or `underground`.
static func route(route_id: String) -> Array[Dictionary]:
	if route_id == "underground":
		return underground_route()
	return seam_route() if route_id == "seam" else southern_route()

## Milliseconds between a leg's walking steps.
static func step_msec(leg: Dictionary) -> int:
	return maxi(16, int(leg.get("stepMsec", WALK_STEP_MSEC)))

static func tile(value: Array) -> Vector2i:
	return Vector2i(int(value[0]), int(value[1]))
