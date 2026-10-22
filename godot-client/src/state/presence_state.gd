extends RefCounted
## Where the players beyond this client's area of interest are, for the map
## dots, and how many actors near the player the server is holding back.
##
## A server that keeps players to an area of interest sends their bodies only
## within it, and once a second the positions of everyone else on the map as
## presence rows: no body, no name, no swing, just a dot. Each row moves its dot
## from where it was drawn to where the row puts it over one presence interval,
## so a distant rider glides across the map rather than jumping ten tiles a
## second. A row whose dot moved farther than SNAP_TILES was relocated, not
## walked, and is drawn at its new place at once.
##
## A player who walks out of the area of interest is removed as an actor before
## the next presence row names them. `hand_over` keeps their dot where the
## actor was last seen until then, so the dot does not blink out for up to a
## second at the edge of the area. A logout leaves the same dot for at most one
## interval, until the next rows leave it out.
##
## Nothing here is used until the server sends presence: a server without the
## capability sends players map-wide as actors, and this stays empty.
##
## The dots are kept as parallel packed arrays, and every dot of one update
## glides over the same interval from the same moment, so a minimap read is one
## lerp per dot with no allocation beyond the result.

## The most rows one map holds. A map's players fit many times over.
const MAXIMUM_DOTS := 2048
const SNAP_TILES := 24.0
## The interval assumed before two updates have been timed, and the range a
## timed one is kept in.
const DEFAULT_INTERVAL_MSEC := 1000.0
const MINIMUM_INTERVAL_MSEC := 250.0
const MAXIMUM_INTERVAL_MSEC := 3000.0

## True once this connection has received presence; the "+N nearby" count and
## the hand-over at the edge of the area mean nothing before that.
var active := false
var map := ""
## Actors within the area of interest the server is not sending because the
## actor cap is reached ("+N nearby").
var nearby_hidden := 0
var interval_msec := DEFAULT_INTERVAL_MSEC
## The actor cap the server says is in force for this client, 0 for none.
var cap := 0
## Bumped on every change, so a reader can tell whether to redraw.
var revision := 0
var _ids := PackedInt32Array()
var _from := PackedVector2Array()
var _to := PackedVector2Array()
## actor id -> index into the arrays.
var _index: Dictionary = {}
## When the dots set off from `_from`; -1 before the first update.
var _updated_msec := -1

func reset() -> void:
	active = false
	interval_msec = DEFAULT_INTERVAL_MSEC
	_updated_msec = -1
	clear_map("")

## A new map: no dot of the old one belongs on it. The server restates the
## rows (and the count) for the map the client now stands on.
func clear_map(map_name: String) -> void:
	map = map_name
	nearby_hidden = 0
	cap = 0
	_ids.clear()
	_from.clear()
	_to.clear()
	_index.clear()
	revision += 1

## One ELORIA_PRESENCE snapshot for `map_name`: the complete set of rows, as
## parallel actor ids and server tiles (interest_protocol.gd). Rows for actors
## the client shows in full are kept and simply not drawn (see `tiles`).
func apply_snapshot(map_name: String, ids: PackedInt32Array, at: PackedVector2Array,
		now_msec: int) -> void:
	active = true
	if map_name != map:
		clear_map(map_name)
	var progress: float = _progress(now_msec)
	if _updated_msec >= 0:
		interval_msec = clampf(float(now_msec - _updated_msec),
			MINIMUM_INTERVAL_MSEC, MAXIMUM_INTERVAL_MSEC)
	var count: int = mini(mini(ids.size(), at.size()), MAXIMUM_DOTS)
	var next_ids: PackedInt32Array = ids.slice(0, count)
	var to: PackedVector2Array = at.slice(0, count)
	var from: PackedVector2Array = to.duplicate()
	var index: Dictionary = {}
	for row: int in range(count):
		var actor_id: int = next_ids[row]
		index[actor_id] = row
		var previous: int = int(_index.get(actor_id, -1))
		if previous >= 0:
			var drawn: Vector2 = _from[previous].lerp(_to[previous], progress)
			if drawn.distance_squared_to(to[row]) <= SNAP_TILES * SNAP_TILES:
				from[row] = drawn
	_ids = next_ids
	_from = from
	_to = to
	_index = index
	_updated_msec = now_msec
	revision += 1

## The same from rows of {actor_id, x, y}, for tools and tests.
func apply_rows(map_name: String, rows: Array, now_msec: int) -> void:
	var ids := PackedInt32Array()
	var at := PackedVector2Array()
	for raw_row: Variant in rows:
		var row: Dictionary = raw_row as Dictionary
		ids.append(int(row.get("actor_id", -1)))
		at.append(Vector2(float(row.get("x", 0)), float(row.get("y", 0))))
	apply_snapshot(map_name, ids, at, now_msec)

## What the snapshot's header says: the cap in force (0 for none) and how many
## actors near the player it holds back ("+N nearby").
func set_header(cap_in_force: int, hidden_nearby: int) -> void:
	cap = maxi(0, cap_in_force)
	set_nearby_hidden(hidden_nearby)

## How many actors nearby are held back by the actor cap.
func set_nearby_hidden(count: int) -> void:
	active = true
	var clamped: int = maxi(0, count)
	if clamped != nearby_hidden:
		nearby_hidden = clamped
		revision += 1

## An actor removed from full replication: keep its dot where it stood until
## the next rows say where it is now, or that it is gone.
func hand_over(actor_id: int, tile: Vector2i, _now_msec: int) -> void:
	if not active or _ids.size() >= MAXIMUM_DOTS:
		return
	var at := Vector2(tile)
	var existing: int = int(_index.get(actor_id, -1))
	if existing >= 0:
		_from[existing] = at
		_to[existing] = at
	else:
		_index[actor_id] = _ids.size()
		_ids.append(actor_id)
		_from.append(at)
		_to.append(at)
	revision += 1

func dot_count() -> int:
	return _ids.size()

func has_dot(actor_id: int) -> bool:
	return _index.has(actor_id)

## Every dot's position in fractional server tiles at `now_msec`, appended to
## `into` as {actor_id: Vector2}. Actors in `shown` (the actor table) have a
## body and their own mark, and are skipped.
func positions(now_msec: int, shown: Dictionary, into: Dictionary) -> void:
	var progress: float = _progress(now_msec)
	for index: int in range(_ids.size()):
		var actor_id: int = _ids[index]
		if shown.has(actor_id):
			continue
		into[actor_id] = _from[index].lerp(_to[index], progress)

## The same positions as packed tiles, for a reader that needs no ids: the
## minimap marks. Only dots within `reach` tiles of `centre` on both axes are
## written (INF for all of them). Returns how many were written.
func tiles(now_msec: int, shown: Dictionary, into: PackedVector2Array,
		centre := Vector2.ZERO, reach := INF) -> int:
	var progress: float = _progress(now_msec)
	into.resize(_ids.size())
	var written := 0
	for index: int in range(_ids.size()):
		var at: Vector2 = _from[index].lerp(_to[index], progress)
		if absf(at.x - centre.x) > reach or absf(at.y - centre.y) > reach:
			continue
		if shown.has(_ids[index]):
			continue
		into[written] = at
		written += 1
	into.resize(written)
	return written

func _progress(now_msec: int) -> float:
	if _updated_msec < 0:
		return 1.0
	return clampf(float(now_msec - _updated_msec) / interval_msec, 0.0, 1.0)
