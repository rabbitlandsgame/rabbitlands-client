extends RefCounted
## The riding table kept current by deltas (mount_deltas_v1), for a server
## that sends only the riders whose row changed.
##
## Without the capability every ELORIA_MOUNT_STATES packet is the whole table
## for the map, and `AppState` replaces its table with it - which made the
## packet the largest thing a crowded map sent, and resent every rider's
## countdowns once a second. With it, ELORIA_MOUNT_DELTAS carries the whole
## table (`full`) after a teleport, a resync or the capability starting, and
## otherwise only the rows that changed and the actors whose rows went away,
## in order on top of the last whole table.
##
## A delta row states its countdowns as times on the server's clock instead of
## time remaining: when a calling completes (`summon_due`), when the riding
## combat lock ends (`combat_until`), and the gallop endurance at a moment
## (`endurance_ms` at `endurance_at`) with the rate it is changing at. The
## server sends a row again only when one of those changes course, never for a
## countdown alone. Here each row is turned into the shape the complete tables
## have, with the countdowns as remaining milliseconds, so everything that
## reads `AppState.actor_mounts` keeps working unchanged; `refresh` restates
## them at any moment, which is how the player's own calling and endurance
## keep counting between packets (`AppState._process`).

## Delta-row fields that are times or rates, all integers.
const TIME_FIELDS: Array[String] = ["step_us", "summon_due", "combat_until",
	"endurance_ms", "endurance_at", "endurance_rate", "endurance_max_ms"]
## Fields a delta row shares with a complete table's row, all strings.
const STRING_FIELDS: Array[String] = ["mode", "gait", "mount_id", "selected_mount_id",
	"blocked_reason", "map", "owner"]
## The complete tables' bounds on the countdowns (mount_preview_state.gd).
const ENDURANCE_LIMIT_MS := 8000
const SUMMON_LIMIT_MS := 1500
const COMBAT_LIMIT_MS := 10000

var map := ""
## Actor ids whose row the last update set or removed; empty after a whole
## table, which sets `whole_table` instead.
var changed_ids: Dictionary = {}
var whole_table := false
## actor id -> [summon local msec or -1, combat local msec or -1,
## endurance local msec, endurance ms, rate per second, maximum]
var _timing: Dictionary = {}

func reset() -> void:
	map = ""
	changed_ids.clear()
	whole_table = false
	_timing.clear()

## Applies one decoded ELORIA_MOUNT_DELTAS to `table` (actor id -> row).
## `update` is {map, full, states: {id: delta row}, removed: [id]}. `clock` is
## the session's ServerClock. Returns false for another map's update, which
## leaves the table untouched.
func apply(update: Dictionary, table: Dictionary, current_map: String,
		clock: RefCounted, now_msec: int) -> bool:
	var update_map: String = str(update.get("map", ""))
	if update_map != current_map:
		return false
	map = update_map
	changed_ids.clear()
	whole_table = bool(update.get("full", false))
	if whole_table:
		table.clear()
		_timing.clear()
	var synced: bool = clock != null and bool(clock.get("synced"))
	var states: Dictionary = update.get("states", {}) as Dictionary
	for raw_id: Variant in states:
		var actor_id: int = int(raw_id)
		var row: Dictionary = states[raw_id] as Dictionary
		var timing: Array = [-1, -1, now_msec, int(row.get("endurance_ms", 0)), 0,
			int(row.get("endurance_max_ms", ENDURANCE_LIMIT_MS))]
		if synced:
			if int(row.get("summon_due", 0)) != 0:
				timing[0] = int(clock.call("to_local_msec", int(row.summon_due)))
			if int(row.get("combat_until", 0)) != 0:
				timing[1] = int(clock.call("to_local_msec", int(row.combat_until)))
			timing[2] = int(clock.call("to_local_msec", int(row.get("endurance_at", 0))))
			timing[4] = int(row.get("endurance_rate", 0))
		_timing[actor_id] = timing
		var shaped: Dictionary = v1_row(row)
		_restate(shaped, timing, now_msec)
		table[actor_id] = shaped
		changed_ids[actor_id] = true
	for raw_removed: Variant in update.get("removed", []) as Array:
		table.erase(int(raw_removed))
		_timing.erase(int(raw_removed))
		changed_ids[int(raw_removed)] = true
	return true

## What the riding table's presentation should re-read after the last update:
## every actor after a whole table, the changed ones after a delta.
func presentation_ids(every_actor: Dictionary) -> Array:
	return every_actor.keys() if whole_table else changed_ids.keys()

## Whether any of `actor_id`'s countdowns is still running at `now_msec`.
func counting_down(actor_id: int, now_msec: int) -> bool:
	var timing: Variant = _timing.get(actor_id)
	if not timing is Array:
		return false
	var times: Array = timing as Array
	if int(times[0]) > now_msec or int(times[1]) > now_msec:
		return true
	if int(times[4]) == 0:
		return false
	var level: int = _endurance(times, now_msec)
	return level > 0 and level < int(times[5])

## Restates `actor_id`'s countdowns in `table` as of `now_msec`. Returns true
## when one of them changed.
func refresh(table: Dictionary, actor_id: int, now_msec: int) -> bool:
	var timing: Variant = _timing.get(actor_id)
	var row: Variant = table.get(actor_id)
	if not timing is Array or not row is Dictionary:
		_timing.erase(actor_id)
		return false
	var before: Array = [row.get("summon_remaining_ms"), row.get("combat_remaining_ms"),
		row.get("endurance_ms")]
	_restate(row as Dictionary, timing as Array, now_msec)
	return before != [row.get("summon_remaining_ms"), row.get("combat_remaining_ms"),
		row.get("endurance_ms")]

## A delta row in the shape of a complete table's row, its countdowns as
## stated (calling and combat lock at zero, endurance at its stated level), or
## an empty dictionary when a field is missing or of the wrong type.
static func v1_row(row: Dictionary) -> Dictionary:
	for field: String in STRING_FIELDS:
		if not row.get(field) is String:
			return {}
	for field: String in TIME_FIELDS:
		var value: Variant = row.get(field)
		if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or float(value) != floorf(float(value)):
			return {}
	if typeof(row.get("can_summon")) != TYPE_BOOL:
		return {}
	var shaped: Dictionary = row.duplicate(true)
	for field: String in ["summon_due", "combat_until", "endurance_at", "endurance_rate",
			"endurance_max_ms"]:
		shaped.erase(field)
	shaped["schema_version"] = 1
	shaped["step_us"] = int(row.step_us)
	shaped["endurance_ms"] = clampi(int(row.endurance_ms), 0,
		mini(int(row.endurance_max_ms), ENDURANCE_LIMIT_MS))
	shaped["summon_remaining_ms"] = 0
	shaped["combat_remaining_ms"] = 0
	return shaped

static func _restate(row: Dictionary, timing: Array, now_msec: int) -> void:
	var summon: int = int(timing[0])
	var combat: int = int(timing[1])
	# A calling is only counted while the row says one is under way.
	row["summon_remaining_ms"] = clampi(summon - now_msec, 0, SUMMON_LIMIT_MS) \
		if summon >= 0 and str(row.get("mode", "")) == "summoning" else 0
	row["combat_remaining_ms"] = clampi(combat - now_msec, 0, COMBAT_LIMIT_MS) if combat >= 0 else 0
	row["endurance_ms"] = _endurance(timing, now_msec)

static func _endurance(timing: Array, now_msec: int) -> int:
	var level: float = float(timing[3]) + float(timing[4]) * float(now_msec - int(timing[2])) / 1000.0
	return clampi(roundi(level), 0, mini(int(timing[5]), ENDURANCE_LIMIT_MS))
