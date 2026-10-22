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
##
## A whole table can be larger than one frame. The server then sends it as
## several frames in a row, and only the first says `full`. So a whole table
## does not empty the table when it starts: it upserts like any delta and
## remembers which rows it has not restated yet. Those go only when the table
## is complete (`close_full`), which AppState calls at the first packet that is
## not part of it. Emptying on the first frame dismounted, for a moment, every
## rider whose row came in a later frame, and re-bound every mount on the map.

## Delta-row fields that are times or rates, all integers.
const TIME_FIELDS: Array[String] = ["step_us", "summon_due", "combat_until",
	"endurance_ms", "endurance_at", "endurance_rate", "endurance_max_ms"]
## Fields a delta row shares with a complete table's row, all strings.
const STRING_FIELDS: Array[String] = ["mode", "gait", "mount_id", "selected_mount_id",
	"blocked_reason", "map", "owner"]
## The complete tables' bounds on the countdowns (mount_preview_state.gd).
## A delta row's own `endurance_max_ms` is the gallop's real maximum and is
## kept on the row; 8 s is only the maximum a row without one is taken to have,
## and the bound the complete tables' check is run against.
const ENDURANCE_LIMIT_MS := 8000
const SUMMON_LIMIT_MS := 1500
const COMBAT_LIMIT_MS := 10000

var map := ""
## Actor ids whose row the last update (or `close_full`) set or removed.
var changed_ids: Dictionary = {}
## Rows held before the whole table now arriving that it has not restated,
## while one is arriving.
var _unrestated: Dictionary = {}
var _full_open := false
var _full_opened_msec := 0
## actor id -> [summon local msec or -1, combat local msec or -1,
## endurance local msec, endurance ms, rate per second, maximum]
var _timing: Dictionary = {}

func reset() -> void:
	map = ""
	changed_ids.clear()
	_unrestated.clear()
	_full_open = false
	_timing.clear()

## Applies one decoded ELORIA_MOUNT_DELTAS to `table` (actor id -> row).
## `update` is {map, full, states: {id: delta row}, removed: [id]}. `clock` is
## the session's ServerClock. Returns false for another map's update, which
## leaves the table untouched. A `full` update opens a whole table (see the
## top of this file); one still open is closed first.
func apply(update: Dictionary, table: Dictionary, current_map: String,
		clock: RefCounted, now_msec: int) -> bool:
	var update_map: String = str(update.get("map", ""))
	if update_map != current_map:
		return false
	map = update_map
	if bool(update.get("full", false)):
		close_full(table)
		for actor_id: Variant in table:
			_unrestated[actor_id] = true
		_full_open = true
		_full_opened_msec = now_msec
	changed_ids.clear()
	var synced: bool = clock != null and bool(clock.get("synced"))
	var states: Dictionary = update.get("states", {}) as Dictionary
	for raw_id: Variant in states:
		var actor_id: int = int(raw_id)
		var row: Dictionary = states[raw_id] as Dictionary
		var timing: Array = [-1, -1, now_msec, int(row.get("endurance_ms", 0)), 0,
			maxi(0, int(row.get("endurance_max_ms", ENDURANCE_LIMIT_MS)))]
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
		_unrestated.erase(actor_id)
	for raw_removed: Variant in update.get("removed", []) as Array:
		table.erase(int(raw_removed))
		_timing.erase(int(raw_removed))
		_unrestated.erase(int(raw_removed))
		changed_ids[int(raw_removed)] = true
	return true

## Whether a whole table is arriving, and since when (local msec).
func full_open() -> bool:
	return _full_open

func full_opened_msec() -> int:
	return _full_opened_msec

## The whole table that was arriving is complete: the rows it did not restate
## go. Returns their ids, which are also left in `changed_ids`.
func close_full(table: Dictionary) -> Array:
	if not _full_open:
		return []
	_full_open = false
	var gone: Array = _unrestated.keys()
	_unrestated.clear()
	changed_ids.clear()
	for actor_id: Variant in gone:
		table.erase(actor_id)
		_timing.erase(actor_id)
		changed_ids[actor_id] = true
	return gone

## The actors whose mounts presentation should re-read after the last update.
## A whole table names its riders as a delta does, so this is the changed ones
## either way; `_every_actor` is kept for the caller's signature.
func presentation_ids(_every_actor: Dictionary) -> Array:
	return changed_ids.keys()

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
## stated (calling and combat lock at zero, endurance at its stated level,
## within the row's own maximum, which the row keeps as `endurance_max_ms`),
## or an empty dictionary when a field is missing or of the wrong type.
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
	for field: String in ["summon_due", "combat_until", "endurance_at", "endurance_rate"]:
		shaped.erase(field)
	shaped["schema_version"] = 1
	shaped["step_us"] = int(row.step_us)
	shaped["endurance_max_ms"] = maxi(0, int(row.endurance_max_ms))
	shaped["endurance_ms"] = clampi(int(row.endurance_ms), 0, int(shaped.endurance_max_ms))
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
	return clampi(roundi(level), 0, int(timing[5]))
