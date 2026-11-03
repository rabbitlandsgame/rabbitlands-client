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
##   view radius, an actor on the server's cap boundary - is not rebuilt. The
##   pool's size follows the machine's memory class (`park_limit`), and its
##   bodies are freed on time from the gate pass, not only when the actor list
##   next changes (`expire_parked_due`).
## - **A body cap**, for machines that cannot draw every actor the server
##   sends (`body_cap`). It follows the graphics quality unless the player
##   chose a number (`body_cap_auto`): 60 at Low, the server's 160 otherwise.
## - **An overhead banner cap** at Low (`overhead_cap`): main.gd's declutter
##   pass shows at most that many banners besides the target, the selection
##   and the party.
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
## many are kept at most on medium and large machines: a small one (8 GB or an
## integrated GPU) keeps 16 (`park_limit`, memory_budgets.gd; owner decision
## 2026-11-02).
const PARK_MSEC := 5000
const PARK_LIMIT := 48
## How often the gate pass (main.gd `_update_animation_gate`) frees the parked
## bodies whose time is up (`expire_parked_due`). Before, only the next change
## to the actor list did (`_remove_stale_actor_nodes`), so the bodies a crowd
## left behind - about 17 nodes each for a creature and 47-52 for a High
## Human, 0.27-0.42 MB of static memory each (perf audit 2026-11, measured) -
## stayed parked however long that took (GAP-06).
const PARK_EXPIRY_PERIOD_MSEC := 500
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
## While the crowd setting follows the graphics quality the cap is
## ActorRenderQuality.body_cap_default instead: this at Medium and High, 60
## at Low (the Low actor tier, owner decision 2026-11-02).
const BODY_CAP_DEFAULT := 160
## What the 2026-11 first-run low tier (HardwareTier.TIER_SETTINGS[LOW])
## saved as the crowd setting before the setting could follow the quality.
const FIRST_RUN_LOW_BODIES := 60
## Overhead banner cap hysteresis: a banner shown on the previous declutter
## pass sorts as if this much nearer the camera focus, so the banners on the
## cap's boundary do not trade places as a crowd mills.
const OVERHEAD_CAP_HYSTERESIS_METRES := 2.0

const RenderQuality := preload("res://src/actors/actor_render_quality.gd")
const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")

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
## selection; 0 is no cap. The player's "Characters drawn in a crowd" setting:
## the graphics quality's value while it follows the quality (`body_cap_auto`,
## every profile until the player picks a number), else the number, unless
## RABBITLANDS_CROWD_BODY_CAP decides (0 there turns the cap off). The
## server's Phase 3C/4 caps decide what is sent; this decides what is drawn
## of it.
var body_cap := BODY_CAP_DEFAULT
## Whether the cap follows the graphics quality rather than a number.
var body_cap_auto := true
## The most overhead banners shown at once besides the target, the selection
## and the party (main.gd `_declutter_actor_overheads`); 0 is no cap. The
## quality's ActorRenderQuality.overhead_cap (24 at Low), unless
## RABBITLANDS_CROWD_TUNING's `banners=N` sets it for a measurement.
var overhead_cap := 0
## Whether the environment set the cap or the cloth budget for this session,
## in which case the player's settings are kept but not applied.
var body_cap_forced := false
var cloth_forced := false
var _full_rate_forced := false
var _half_rate_forced := false
var _overhead_cap_forced := false
## The graphics quality last applied (set_quality), and the player's own
## number for the body cap.
var _quality: int = RenderQuality.Quality.HIGH
var _player_body_cap := BODY_CAP_DEFAULT
## The banners counted against `overhead_cap` on the last declutter pass, and
## on the pass under way.
var _overheads_shown: Dictionary = {}
var _overheads_counted: Dictionary = {}

var _candidates: Array[int] = []
var _cursor := 0
var _far_since: Dictionary = {}
var _parked: Dictionary = {}
## The most bodies parked at once: this machine's memory class's
## (`park_limit_for`), read by `configure`; PARK_LIMIT until then.
var park_limit := PARK_LIMIT
## When `expire_parked_due` next looks at the parked bodies.
var _park_expiry_at := 0
var builds := 0
var releases := 0
var revivals := 0

func parked_actor_ids() -> Array:
	return _parked.keys()

## The policy the environment asks for: Main passes
## `RABBITLANDS_CROWD_PRESENTATION` and `RABBITLANDS_CROWD_BODY_CAP`. The first
## is empty or `all` for everything, `legacy` (or `0`/`off`) for none, or a
## comma list naming the features to keep (`lazy,gate`); `-name` drops one from
## the full set. The second sets `body_cap`. Benchmarks use both to compare a
## feature against the client without it. The third,
## RABBITLANDS_CROWD_TUNING, sets budgets: `full=24,half=16,cloth=8` and
## `banners=N` for the overhead banner cap (0 = none) at every quality.
## The park pool's size is the memory class's (RABBITLANDS_MEMORY_CLASS or
## `--memory-class=` force one for a measurement).
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
	park_limit = park_limit_for(MemoryBudgets.memory_class())
	# Both refine the gate and mean nothing without it.
	stagger = gate and bool(enabled.get("stagger", false))
	quarter = gate and bool(enabled.get("quarter", false))
	body_cap_forced = cap.strip_edges().is_valid_int()
	body_cap_auto = true
	_player_body_cap = BODY_CAP_DEFAULT
	if body_cap_forced:
		body_cap = maxi(0, int(cap))
	else:
		_apply_body_cap()
	full_rate_bodies = FULL_RATE_BODIES
	half_rate_bodies = HALF_RATE_BODIES
	cloth_bodies = CLOTH_BODIES
	cloth_forced = false
	_full_rate_forced = false
	_half_rate_forced = false
	_overhead_cap_forced = false
	overhead_cap = RenderQuality.overhead_cap(_quality)
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
			"banners":
				overhead_cap = maxi(0, int(pair[1]))
				_overhead_cap_forced = true
	_overheads_shown.clear()

## The graphics quality's budgets: the full- and half-rate bodies, the
## overhead banner cap and, while the crowd setting follows the quality, the
## body cap (so switching between Low and High in a session restores 160).
func set_quality(level: int) -> void:
	_quality = clampi(level, 0, 2)
	if not _full_rate_forced:
		full_rate_bodies = [8, 12, FULL_RATE_BODIES][_quality]
	if not _half_rate_forced:
		half_rate_bodies = [8, 12, HALF_RATE_BODIES][_quality]
	if not _overhead_cap_forced:
		overhead_cap = RenderQuality.overhead_cap(_quality)
	if overhead_cap <= 0:
		_overheads_shown.clear()
	_apply_body_cap()

## The player's two crowd settings (settings_window.gd, Graphics): the body
## count, or `follow_quality` for the quality's own, and the swaying capes.
## Either is ignored while the environment sets it for the session.
func set_player_budgets(bodies: int, capes: int, follow_quality := false) -> void:
	body_cap_auto = follow_quality
	_player_body_cap = maxi(0, bodies)
	_apply_body_cap()
	if not cloth_forced:
		cloth_bodies = maxi(0, capes)

## The body cap the graphics quality gives while the setting follows it.
func quality_body_cap() -> int:
	return RenderQuality.body_cap_default(_quality)

func _apply_body_cap() -> void:
	if not body_cap_forced:
		body_cap = quality_body_cap() if body_cap_auto else _player_body_cap

## Whether a saved profile's crowd setting follows the graphics quality.
## `saved_auto` is [graphics] crowd_bodies_auto, `saved_bodies` crowd_bodies
## and `tier` the first-run tier the file records (HardwareTier.seeded_tier).
## A saved switch decides. A profile from before the switch follows the
## quality when it kept the old default (160, nothing, or something that is
## not a number, which read as 160) or when the first-run low tier wrote its
## 60; any other number was the player's own choice and stays a number.
static func follows_quality(saved_auto: Variant, saved_bodies: Variant, tier: String) -> bool:
	if saved_auto is bool:
		return saved_auto
	if not (saved_bodies is int or saved_bodies is float):
		return true
	var bodies := int(saved_bodies)
	return bodies == BODY_CAP_DEFAULT or (bodies == FIRST_RUN_LOW_BODIES and tier == "low")

## The overhead banner cap, for main.gd's declutter pass. Without a cap none
## of this is called and the pass is as it always was.
##
## The pass's sort distance (squared, to the camera focus) for actor `id`: a
## banner shown on the previous pass sorts as if
## OVERHEAD_CAP_HYSTERESIS_METRES nearer.
func overhead_sort_distance(id: int, distance_squared: float) -> float:
	if overhead_cap <= 0 or not _overheads_shown.has(id):
		return distance_squared
	var nearer := maxf(0.0, sqrt(distance_squared) - OVERHEAD_CAP_HYSTERESIS_METRES)
	return nearer * nearer

func begin_overhead_pass() -> void:
	_overheads_counted = {}

## Whether the next candidate's banner is past the cap. An exempt one (the
## target, the selection, the party) never is and is never counted.
func overhead_capped(exempt: bool) -> bool:
	return overhead_cap > 0 and not exempt and _overheads_counted.size() >= overhead_cap

## A banner the pass showed, counted against the cap.
func count_overhead(id: int) -> void:
	_overheads_counted[id] = true

func end_overhead_pass() -> void:
	_overheads_shown = _overheads_counted
	_overheads_counted = {}

## How many banners the last pass counted against the cap.
func overheads_shown() -> int:
	return _overheads_shown.size()

func describe() -> Dictionary:
	return {"lazy": lazy, "gate": gate, "effects": effects, "park": park,
		"stagger": stagger, "quarter": quarter,
		"bodyCap": body_cap, "bodyCapAuto": body_cap_auto, "fullRateBodies": full_rate_bodies,
		"halfRateBodies": half_rate_bodies, "clothBodies": cloth_bodies,
		"overheadCap": overhead_cap, "overheadsShown": _overheads_shown.size(),
		"builds": builds, "releases": releases,
		"revivals": revivals, "parked": _parked.size(), "parkLimit": park_limit}

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

## The park pool's size for `memory_class` (memory_budgets.gd): 16 bodies on a
## small machine, PARK_LIMIT on medium and large ones (and for a class the
## table does not know, which reads medium's).
static func park_limit_for(memory_class: String) -> int:
	var limit: Variant = MemoryBudgets.value_for(memory_class, MemoryBudgets.CROWD_PARK_LIMIT)
	return maxi(0, int(limit)) if limit is int or limit is float else PARK_LIMIT

## Keeps a removed body for `PARK_MSEC`. False when parking is off or full
## (`park_limit`); the caller frees the node then, as it always did.
func park_node(id: int, node: Node3D, key: String, now: int) -> bool:
	if not park or _parked.size() >= park_limit or _parked.has(id):
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

## Frees the parked bodies whose `PARK_MSEC` is up at `now`; how many left
## the pool.
func expire_parked(now: int) -> int:
	if _parked.is_empty():
		return 0
	var expired := 0
	for id: Variant in _parked.keys():
		var entry: Dictionary = _parked[id]
		if now < int(entry.get("until", 0)):
			continue
		var node: Variant = entry.get("node")
		if is_instance_valid(node):
			(node as Node).queue_free()
		_parked.erase(id)
		expired += 1
	return expired

## `expire_parked`, at most once every PARK_EXPIRY_PERIOD_MSEC: main.gd's gate
## pass calls it every frame, so a parked body is freed at most that much
## after its time is up whether or not the actor list changes. `now` is
## Time.get_ticks_msec(), the clock `park_node` was given.
func expire_parked_due(now: int) -> int:
	if now < _park_expiry_at:
		return 0
	_park_expiry_at = now + PARK_EXPIRY_PERIOD_MSEC
	return expire_parked(now)

func clear_parked() -> void:
	for entry: Dictionary in _parked.values():
		var node: Variant = entry.get("node")
		if is_instance_valid(node):
			(node as Node).queue_free()
	_parked.clear()
	_park_expiry_at = 0

func parked_count() -> int:
	return _parked.size()

func clear() -> void:
	clear_parked()
	_candidates.clear()
	_cursor = 0
	_far_since.clear()
	_overheads_shown.clear()
