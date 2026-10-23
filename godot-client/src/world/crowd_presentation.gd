extends RefCounted
## How a crowd is presented inside the client's frame budget. Main owns the
## actor nodes; this owns the policy and the bookkeeping behind three changes:
##
## - **Bodies only where they can be seen.** Every actor the server sends used
##   to become a fully built skinned body (about 29 nodes and 3-4 MB each), even
##   past the draw distance, where it was hidden but never unbuilt. Now an actor
##   beyond `BUILD_RADIUS_METRES` is a deferred node: identity, picking, overhead
##   block, map dot and protocol state, without a model. Main builds its body
##   when it comes within range, nearest first and within a per-frame budget,
##   and a body that has been far out of range for a while is given up again.
## - **Parking.** A body the server removes is kept hidden for a few seconds,
##   so an actor that steps out of view and back - a creature on the edge of the
##   view radius, an actor on the server's cap boundary - is not rebuilt.
## - **An optional body cap**, for machines that cannot draw every actor the
##   server sends (`body_cap`, off unless asked for).
##
## The constants are chosen against the 80 m draw distance: bodies are built a
## little before they can be seen and kept well after, so walking along the
## edge of view does not build and release the same actor over and over.

## Built inside this horizontal distance from the player.
const BUILD_RADIUS_METRES := 88.0
## Given up beyond this distance ...
const RELEASE_RADIUS_METRES := 120.0
## ... once it has stayed beyond it this long.
const RELEASE_AFTER_MSEC := 8000
## At most this many bodies are given up per gate pass (every 100 ms).
const RELEASES_PER_PASS := 4
## Bodies built per frame: the same four the spawn budget always allowed, and
## never more than this much frame time once one has been built.
const BUILDS_PER_FRAME := 4
const BUILD_BUDGET_USEC := 6000
## Deferred nodes are cheap, so a whole crowd arriving at once gets its map
## dots and its stand-ins on the frame it arrives.
const DEFERRED_SPAWNS_PER_PASS := 64
## How long a removed body is kept for the same actor to come back, and how
## many are kept at most.
const PARK_MSEC := 5000
const PARK_LIMIT := 48
## Body cap hysteresis: with more actors in range than the cap, the cap's
## distance is that of the cap-th nearest. Deferred actors inside it are built;
## a body is given up only once it is this much farther out than that, so an
## actor on the boundary does not flip between body and none as the crowd mills.
const BODY_CAP_HYSTERESIS_METRES := 8.0
## With the gate on, at most this many remote bodies animate at full rate: the
## nearest the camera. The rest of a crowd in view is stepped at half rate.
## Measured on the development laptop's 160-player market at High quality, 32
## of them cost about 2 ms a frame more than 16.
const FULL_RATE_BODIES := 16
## With the gate on, cape cloth is simulated for at most this many remote
## bodies, the nearest the camera; the solver is the largest per-body cost of
## an equipped crowd, about 0.2 ms a cape a frame on the development laptop. A
## body keeps its cloth until it is `CLOTH_HYSTERESIS` places past the limit,
## so capes on the boundary do not settle and swing.
const CLOTH_BODIES := 8
const CLOTH_HYSTERESIS := 4
## With the quarter tier on, the next this many bodies after the full-rate
## ones are stepped at half rate; every body ranked after them - the farthest
## of a crowd in view - is stepped every fourth frame, as is a clip that does
## not loop played out off screen.
const HALF_RATE_BODIES := 16
## The body cap a player has not changed: the Phase 4 server cap, so the
## client draws no fewer than the server will send once that cap is live.
const BODY_CAP_DEFAULT := 160

var lazy := true
var gate := true
var effects := true
var park := true
## The gate's stepped bodies take turns over the frames (AnimationGate.stagger)
## rather than all being stepped on the same one.
var stagger := true
## The quarter-rate tier for the far end of a crowd (`HALF_RATE_BODIES`).
var quarter := true
## The full-rate, half-rate and cloth budgets in use: the constants, the
## player's "Swaying capes in a crowd" setting for the cloth, unless
## RABBITLANDS_CROWD_TUNING (`full=24,half=16,cloth=8`) says otherwise for a
## measurement.
var full_rate_bodies := FULL_RATE_BODIES
var half_rate_bodies := HALF_RATE_BODIES
var cloth_bodies := CLOTH_BODIES
## The most bodies built at once, not counting the player, their target or
## selection; 0 is no cap. The player's "Characters drawn in a crowd" setting,
## 160 until they change it, unless RABBITLANDS_CROWD_BODY_CAP decides (0 there
## turns the cap off). The server's Phase 3C/4 caps decide what is sent; this
## decides what is drawn of it.
var body_cap := BODY_CAP_DEFAULT
## Whether the environment set the cap or the cloth budget for this session,
## in which case the player's settings are kept but not applied.
var body_cap_forced := false
var cloth_forced := false
var _full_rate_forced := false
var _half_rate_forced := false

var _candidates: Array[int] = []
var _cursor := 0
var _far_since: Dictionary = {}
var _parked: Dictionary = {}
var builds := 0
var releases := 0
var revivals := 0

## The policy the environment asks for: Main passes
## `RABBITLANDS_CROWD_PRESENTATION` and `RABBITLANDS_CROWD_BODY_CAP`. The first
## is empty or `all` for everything, `legacy` (or `0`/`off`) for none, or a
## comma list naming the features to keep (`lazy,gate`); `-name` drops one from
## the full set. The second sets `body_cap`. Benchmarks use both to compare a
## feature against the client without it.
func configure(features: String, cap: String = "", tuning: String = "") -> void:
	var raw := features.strip_edges().to_lower()
	var names := ["lazy", "gate", "effects", "park", "stagger", "quarter"]
	var enabled := {}
	if raw.is_empty() or raw == "all":
		for name: String in names:
			enabled[name] = true
	elif raw in ["legacy", "off", "0", "none"]:
		pass
	else:
		var only := false
		for part: String in raw.split(",", false):
			if not part.strip_edges().begins_with("-"):
				only = true
		for name: String in names:
			enabled[name] = not only
		for part: String in raw.split(",", false):
			var item := part.strip_edges()
			if item.begins_with("-"):
				enabled.erase(item.substr(1))
			elif item in names:
				enabled[item] = true
	lazy = bool(enabled.get("lazy", false))
	gate = bool(enabled.get("gate", false))
	effects = bool(enabled.get("effects", false))
	park = bool(enabled.get("park", false))
	# Both refine the gate and mean nothing without it.
	stagger = gate and bool(enabled.get("stagger", false))
	quarter = gate and bool(enabled.get("quarter", false))
	body_cap_forced = cap.strip_edges().is_valid_int()
	body_cap = maxi(0, int(cap)) if body_cap_forced else BODY_CAP_DEFAULT
	full_rate_bodies = FULL_RATE_BODIES
	half_rate_bodies = HALF_RATE_BODIES
	cloth_bodies = CLOTH_BODIES
	cloth_forced = false
	_full_rate_forced = false
	_half_rate_forced = false
	for part: String in tuning.split(",", false):
		var pair := part.split("=")
		if pair.size() != 2 or not pair[1].strip_edges().is_valid_int():
			continue
		match pair[0].strip_edges():
			"full":
				full_rate_bodies = maxi(0, int(pair[1]))
				_full_rate_forced = true
			"half":
				half_rate_bodies = maxi(0, int(pair[1]))
				_half_rate_forced = true
			"cloth":
				cloth_bodies = maxi(0, int(pair[1]))
				cloth_forced = true

func set_quality(level: int) -> void:
	if not _full_rate_forced:
		full_rate_bodies = [8, 12, FULL_RATE_BODIES][clampi(level, 0, 2)]
	if not _half_rate_forced:
		half_rate_bodies = [8, 12, HALF_RATE_BODIES][clampi(level, 0, 2)]

## The player's two crowd settings (settings_window.gd, Graphics). Either is
## ignored while the environment sets it for the session.
func set_player_budgets(bodies: int, capes: int) -> void:
	if not body_cap_forced:
		body_cap = maxi(0, bodies)
	if not cloth_forced:
		cloth_bodies = maxi(0, capes)

func describe() -> Dictionary:
	return {"lazy": lazy, "gate": gate, "effects": effects, "park": park,
		"stagger": stagger, "quarter": quarter,
		"bodyCap": body_cap, "fullRateBodies": full_rate_bodies,
		"halfRateBodies": half_rate_bodies, "clothBodies": cloth_bodies,
		"builds": builds, "releases": releases,
		"revivals": revivals, "parked": _parked.size()}

## Hands the gate pass's build candidates over, nearest first. `pairs` holds
## `[distance, id]` arrays.
func set_candidates(pairs: Array) -> void:
	pairs.sort_custom(func(a: Array, b: Array) -> bool:
		return a[0] < b[0] if a[0] != b[0] else a[1] < b[1])
	_candidates.clear()
	for pair: Array in pairs:
		_candidates.append(int(pair[1]))
	_cursor = 0

## The next actor whose body should be built, or -1.
func next_candidate() -> int:
	if _cursor >= _candidates.size():
		return -1
	_cursor += 1
	return _candidates[_cursor - 1]

func pending_candidates() -> int:
	return _candidates.size() - _cursor

## Whether a built body has been beyond the release radius long enough to be
## given up. `far` says whether it is beyond it now.
func release_due(id: int, far: bool, now: int) -> bool:
	if not far:
		_far_since.erase(id)
		return false
	if not _far_since.has(id):
		_far_since[id] = now
		return false
	return now - int(_far_since[id]) >= RELEASE_AFTER_MSEC

func forget(id: int) -> void:
	_far_since.erase(id)

## Who an actor is, as far as reusing its body goes: a recycled id carrying a
## different creature or person must not wear the old one's body. Include the
## name, its colour and the tag as they were when the body was built.
## Everything else a spawn packet carries is reapplied to a revived body.
static func identity_key(dto: Dictionary) -> String:
	return "%d|%d|%s|%s|%d" % [int(dto.get("actor_type", -1)), int(dto.get("kind", -1)),
		str(dto.get("name", "")), str(dto.get("guild_tag", "")),
		int(dto.get("name_colour", 0))]

## Keeps a removed body for `PARK_MSEC`. False when parking is off or full;
## the caller frees the node then, as it always did.
func park_node(id: int, node: Node3D, key: String, now: int) -> bool:
	if not park or _parked.size() >= PARK_LIMIT or _parked.has(id):
		return false
	node.visible = false
	node.process_mode = Node.PROCESS_MODE_DISABLED
	if node is CollisionObject3D:
		(node as CollisionObject3D).collision_layer = 0
	_parked[id] = {"node": node, "until": now + PARK_MSEC, "key": key}
	return true

## The parked body for this actor if it is the same actor, else null (and any
## body parked under the id is freed).
func take_parked(id: int, key: String) -> Node3D:
	if not _parked.has(id):
		return null
	var entry: Dictionary = _parked[id]
	_parked.erase(id)
	var node: Variant = entry.get("node")
	if not is_instance_valid(node):
		return null
	if str(entry.get("key", "")) != key:
		(node as Node).queue_free()
		return null
	(node as Node3D).visible = true
	(node as Node).process_mode = Node.PROCESS_MODE_INHERIT
	revivals += 1
	return node as Node3D

func expire_parked(now: int) -> void:
	if _parked.is_empty():
		return
	for id: Variant in _parked.keys():
		var entry: Dictionary = _parked[id]
		if now < int(entry.get("until", 0)):
			continue
		var node: Variant = entry.get("node")
		if is_instance_valid(node):
			(node as Node).queue_free()
		_parked.erase(id)

func clear_parked() -> void:
	for entry: Dictionary in _parked.values():
		var node: Variant = entry.get("node")
		if is_instance_valid(node):
			(node as Node).queue_free()
	_parked.clear()

func parked_count() -> int:
	return _parked.size()

func clear() -> void:
	clear_parked()
	_candidates.clear()
	_cursor = 0
	_far_since.clear()
