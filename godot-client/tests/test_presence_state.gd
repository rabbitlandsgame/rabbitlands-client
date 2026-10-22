extends SceneTree
## Presence dots for players beyond the area of interest, the "+N nearby"
## count, and the riding table kept by deltas.

const PresenceState := preload("res://src/state/presence_state.gd")
const MountDeltaState := preload("res://src/mounts/mount_delta_state.gd")
const ServerClock := preload("res://src/network/server_clock.gd")
const NearbyIndicator := preload("res://src/ui/nearby_indicator.gd")
const InterestProtocol := preload("res://src/network/interest_protocol.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_presence()
	_check_hand_over()
	_check_mount_deltas()
	_check_mount_deadlines()
	_check_indicator()
	_check_actor_cap()
	_measure()
	print("presence state tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_presence() -> void:
	var presence = PresenceState.new()
	_expect(not presence.active and presence.dot_count() == 0, "nothing until the server sends presence")
	presence.apply_rows("isle", [{"actor_id": 5, "x": 10, "y": 20},
		{"actor_id": 6, "x": 100, "y": 100}], 1000)
	_expect(presence.active and presence.map == "isle" and presence.dot_count() == 2,
		"a presence update places a dot per row")
	var at: Dictionary = {}
	presence.positions(1000, {}, at)
	_expect(at[5] == Vector2(10, 20), "a new dot is drawn where its row puts it")
	presence.apply_rows("isle", [{"actor_id": 5, "x": 12, "y": 20},
		{"actor_id": 6, "x": 140, "y": 100}], 2000)
	_expect(is_equal_approx(presence.interval_msec, 1000.0), "the interval is timed between updates")
	at.clear()
	presence.positions(2500, {}, at)
	_expect(at[5].is_equal_approx(Vector2(11, 20)),
		"a dot glides to its new tile over one interval (%s)" % str(at[5]))
	_expect(at[6] == Vector2(140, 100), "a dot that moved farther than walking is placed at once")
	at.clear()
	presence.positions(3500, {}, at)
	_expect(at[5] == Vector2(12, 20), "and rests there once the interval is over")
	at.clear()
	presence.positions(2500, {6: {}}, at)
	_expect(not at.has(6) and at.has(5), "a player with a body is not also a dot")
	presence.apply_rows("isle", [{"actor_id": 6, "x": 140, "y": 100}], 3000)
	_expect(presence.dot_count() == 1 and not presence.has_dot(5),
		"a player the rows leave out is gone")
	presence.set_nearby_hidden(14)
	_expect(presence.nearby_hidden == 14, "the nearby count is kept")
	presence.clear_map("cove")
	_expect(presence.dot_count() == 0 and presence.nearby_hidden == 0 and presence.active,
		"a change of map clears the old map's dots and count")
	presence.apply_rows("cove", [{"actor_id": 9, "x": 1, "y": 1}], 4000)
	presence.reset()
	_expect(not presence.active and presence.dot_count() == 0, "a new connection starts empty")

func _check_hand_over() -> void:
	var presence = PresenceState.new()
	presence.hand_over(5, Vector2i(3, 3), 1000)
	_expect(presence.dot_count() == 0, "no hand-over before the server sends presence")
	presence.apply_rows("isle", [], 1000)
	presence.hand_over(5, Vector2i(80, 3), 1200)
	var at: Dictionary = {}
	presence.positions(1300, {}, at)
	_expect(at.get(5) == Vector2(80, 3), "a player walking out of the area keeps a dot where they were")
	presence.apply_rows("isle", [{"actor_id": 5, "x": 82, "y": 3}], 2000)
	at.clear()
	presence.positions(2000, {}, at)
	_expect(at.get(5) == Vector2(80, 3), "and the next rows carry it on from there")

func _delta_row(actor_id: int, mode: String) -> Dictionary:
	return {"actor_id": actor_id, "mode": mode, "gait": "cruise" if mode == "mounted" else "on_foot",
		"mount_id": "moor_pony" if mode != "on_foot" else "", "selected_mount_id": "moor_pony",
		"step_us": 133333, "can_summon": false, "blocked_reason": "", "map": "isle", "owner": "p%d" % actor_id,
		"summon_due": 0, "combat_until": 0, "endurance_ms": 8000, "endurance_at": 0,
		"endurance_rate": 0, "endurance_max_ms": 8000}

func _check_mount_deltas() -> void:
	var deltas = MountDeltaState.new()
	var table: Dictionary = {}
	_expect(deltas.apply({"map": "isle", "full": true,
		"states": {1: _delta_row(1, "mounted"), 2: _delta_row(2, "on_foot")}}, table, "isle", null, 0),
		"a whole table is taken")
	_expect(table.size() == 2 and deltas.full_open(), "and stays open for any frames that follow it")
	_expect(int(table[1].endurance_ms) == 8000 and int(table[1].summon_remaining_ms) == 0
		and not table[1].has("summon_due") and not table[1].has("endurance_rate"),
		"a row is kept in the complete tables' shape")
	var named: Array = deltas.presentation_ids({1: 0, 2: 0, 3: 0})
	named.sort()
	_expect(named == [1, 2], "a whole table re-binds the riders it names, not every actor (%s)" % str(named))
	_expect(deltas.close_full(table).is_empty() and not deltas.full_open(), "it closes with nothing to drop")
	_expect(deltas.apply({"map": "isle", "full": false, "states": {2: _delta_row(2, "mounted")},
		"removed": [1]}, table, "isle", null, 0), "a delta applies")
	_expect(not table.has(1) and str(table[2].mode) == "mounted",
		"a delta changes its rows and removes its removed")
	var ids: Array = deltas.presentation_ids({1: 0, 2: 0, 3: 0})
	ids.sort()
	_expect(ids == [1, 2], "only the actors a delta touched are re-read (%s)" % str(ids))
	_expect(not deltas.apply({"map": "cove", "full": true, "states": {}}, table, "isle", null, 0)
		and table.has(2), "another map's update is refused")
	_expect(deltas.apply({"map": "cove", "full": false, "states": {5: _delta_row(5, "mounted")}},
		table, "cove", null, 0) and table.has(2) and table.has(5),
		"across a seam the rows carried over stay and the new map's deltas add to them")
	deltas.apply({"map": "cove", "full": true, "states": {}}, table, "cove", null, 0)
	_expect(table.has(2) and table.has(5), "an empty whole table empties nothing until it is complete")
	var gone: Array = deltas.close_full(table)
	gone.sort()
	_expect(table.is_empty() and gone == [2, 5], "and then drops every row it did not restate")
	_check_split_whole_table()

## A whole table too big for one frame: three frames, only the first `full`.
## Nobody the table names is ever without a row between its frames, and only
## the row it never restates goes, once it is complete.
func _check_split_whole_table() -> void:
	var deltas = MountDeltaState.new()
	var table: Dictionary = {}
	deltas.apply({"map": "isle", "full": true, "states": {7: _delta_row(7, "on_foot"),
		8: _delta_row(8, "on_foot"), 9: _delta_row(9, "mounted")}}, table, "isle", null, 0)
	deltas.close_full(table)
	deltas.apply({"map": "isle", "full": true, "states": {7: _delta_row(7, "mounted")}}, table, "isle", null, 0)
	_expect(table.has(8) and table.has(9) and str(table[7].mode) == "mounted",
		"after the first frame the riders of the later frames keep their rows")
	deltas.apply({"map": "isle", "full": false, "states": {8: _delta_row(8, "mounted")}}, table, "isle", null, 0)
	_expect(deltas.full_open() and table.has(9) and str(table[8].mode) == "mounted",
		"a following frame without `full` continues the table")
	deltas.apply({"map": "isle", "full": false, "states": {10: _delta_row(10, "mounted")}}, table, "isle", null, 0)
	var gone: Array = deltas.close_full(table)
	_expect(gone == [9] and table.has(7) and table.has(8) and table.has(10) and not table.has(9),
		"once complete, only the row the table left out is dropped (%s)" % str(gone))
	_expect(deltas.presentation_ids({}) == [9], "and only that rider's mount is re-read")

func _check_mount_deadlines() -> void:
	var clock = ServerClock.new()
	clock.observe(10000, 50000)
	var deltas = MountDeltaState.new()
	var table: Dictionary = {}
	var row := _delta_row(4, "summoning")
	row["summon_due"] = 11200
	row["combat_until"] = 10300
	row["endurance_ms"] = 4000
	row["endurance_at"] = 10000
	row["endurance_rate"] = -1000
	deltas.apply({"map": "isle", "full": true, "states": {4: row}}, table, "isle", clock, 50200)
	var shaped: Dictionary = table[4]
	_expect(int(shaped.summon_remaining_ms) == 1000 and int(shaped.combat_remaining_ms) == 100
		and int(shaped.endurance_ms) == 3800,
		"deadlines are stated as what remains when they arrive (%d, %d, %d)" % [
			int(shaped.summon_remaining_ms), int(shaped.combat_remaining_ms), int(shaped.endurance_ms)])
	_expect(deltas.refresh(table, 4, 51000), "and restated later")
	_expect(int(shaped.summon_remaining_ms) == 200 and int(shaped.combat_remaining_ms) == 0
		and int(shaped.endurance_ms) == 3000, "counting down on the local clock")
	_expect(deltas.counting_down(4, 51000), "while a countdown runs it says so")
	deltas.refresh(table, 4, 60000)
	_expect(int(shaped.summon_remaining_ms) == 0 and int(shaped.endurance_ms) == 0,
		"to zero, and no lower")
	_expect(not deltas.refresh(table, 4, 61000) and not deltas.counting_down(4, 61000),
		"once everything has run out nothing changes")
	var refill := _delta_row(6, "mounted")
	refill["endurance_ms"] = 7500
	refill["endurance_at"] = 10000
	refill["endurance_rate"] = 500
	deltas.apply({"map": "isle", "full": false, "states": {6: refill}}, table, "isle", clock, 50000)
	deltas.refresh(table, 6, 53000)
	_expect(int(table[6].endurance_ms) == 8000, "a refill stops at the most the gallop holds")
	table.erase(6)
	_expect(not deltas.refresh(table, 6, 53100), "a row gone from the table is no longer counted")

func _check_indicator() -> void:
	var indicator: Label = NearbyIndicator.new()
	root.add_child(indicator)
	_expect(not indicator.visible, "the nearby indicator is hidden at zero")
	indicator.show_count(23)
	_expect(indicator.visible and indicator.text.contains("23"), "and says how many when there are some (%s)" % indicator.text)
	indicator.show_count(0)
	_expect(not indicator.visible, "and hides again")
	indicator.queue_free()

func _check_actor_cap() -> void:
	_expect(InterestProtocol.clamp_actor_cap(160) == 160, "a cap is at most 160")
	_expect(InterestProtocol.clamp_actor_cap(500) == 160, "a larger one is brought down")
	_expect(InterestProtocol.clamp_actor_cap(3) == InterestProtocol.ACTOR_CAP_MINIMUM,
		"and a tiny one up to the server's floor")
	_expect(InterestProtocol.clamp_actor_cap("lots") == InterestProtocol.ACTOR_CAP_DEFAULT,
		"a value that is not a number is the default")
	_expect(InterestProtocol.declared_actor_cap(160) == 160,
		"the crowd setting's default declares 160, as declaring nothing would")
	_expect(InterestProtocol.declared_actor_cap(300) == 160 and InterestProtocol.declared_actor_cap(90) == 90
		and InterestProtocol.declared_actor_cap(40) == 40,
		"the declared cap follows the crowd setting up to 160")

## What a presence update and a minimap read cost with 500 players beyond the
## area, the most one shard holds. Printed, not gated: the numbers are for the
## Phase 4 page.
func _measure() -> void:
	var presence = PresenceState.new()
	var rows: Array = []
	for index: int in range(500):
		rows.append({"actor_id": 1000 + index, "x": index % 400, "y": index / 2})
	var started := Time.get_ticks_usec()
	for second: int in range(20):
		presence.apply_rows("isle", rows, second * 1000)
	var apply_usec: float = float(Time.get_ticks_usec() - started) / 20.0
	var at: Dictionary = {}
	started = Time.get_ticks_usec()
	for read: int in range(60):
		at.clear()
		presence.positions(19000 + read * 16, {}, at)
	var read_usec: float = float(Time.get_ticks_usec() - started) / 60.0
	# What main.gd's `_presence_marks` adds per minimap refresh on top: the
	# tiles, a world position and a mark each.
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true})
	var tiles := PackedVector2Array()
	started = Time.get_ticks_usec()
	for read: int in range(60):
		var marks: Array[Dictionary] = []
		presence.tiles(19000 + read * 16, {}, tiles)
		for tile: Vector2 in tiles:
			marks.append({"position": adapter.server_to_godot(tile.x + 0.5, tile.y + 0.5),
				"type": &"player", "colour": Color.WHITE, "radius": 3.0})
	var marks_usec: float = float(Time.get_ticks_usec() - started) / 60.0
	# The same with main's culling to the default minimap's corner (135 tiles
	# around a player in the middle of the dots) and its reused marks.
	var pool: Array[Dictionary] = []
	started = Time.get_ticks_usec()
	var drawn := 0
	for read: int in range(60):
		var marks: Array[Dictionary] = []
		drawn = presence.tiles(19000 + read * 16, {}, tiles, Vector2(200, 125), 135.0)
		while pool.size() < drawn:
			pool.append({"position": Vector3.ZERO, "type": &"player", "colour": Color.WHITE, "radius": 3.0})
		var origin: Vector3 = adapter.server_to_godot(0.5, 0.5)
		var step_x: Vector3 = adapter.server_to_godot(1.5, 0.5) - origin
		var step_y: Vector3 = adapter.server_to_godot(0.5, 1.5) - origin
		for index: int in range(drawn):
			var tile: Vector2 = tiles[index]
			var mark: Dictionary = pool[index]
			mark["position"] = origin + step_x * tile.x + step_y * tile.y
			marks.append(mark)
	var culled_usec: float = float(Time.get_ticks_usec() - started) / 60.0
	var misplaced := 0
	for index: int in range(drawn):
		var tile: Vector2 = tiles[index]
		if not (pool[index].position as Vector3).is_equal_approx(
				adapter.server_to_godot(tile.x + 0.5, tile.y + 0.5)):
			misplaced += 1
	_expect(drawn > 0 and misplaced == 0,
		"every dot placed by the affine shortcut stands where the adapter puts it")
	print("presence, 500 dots: update %.0f us, one read %.0f us, all marks %.0f us, minimap marks (%d in view, reused) %.0f us" % [
		apply_usec, read_usec, marks_usec, drawn, culled_usec])
	var deltas = MountDeltaState.new()
	var table: Dictionary = {}
	var states: Dictionary = {}
	for index: int in range(200):
		states[index] = _delta_row(index, "mounted")
	started = Time.get_ticks_usec()
	deltas.apply({"map": "isle", "full": true, "states": states}, table, "isle", null, 0)
	var baseline_usec: int = Time.get_ticks_usec() - started
	started = Time.get_ticks_usec()
	for update: int in range(100):
		deltas.apply({"map": "isle", "full": false, "states": {update % 200: states[update % 200]}},
			table, "isle", null, 0)
	var delta_usec: float = float(Time.get_ticks_usec() - started) / 100.0
	started = Time.get_ticks_usec()
	for tick: int in range(100):
		deltas.refresh(table, 7, tick * 100)
	var refresh_usec: float = float(Time.get_ticks_usec() - started) / 100.0
	# The packets themselves: today's complete table of 200 riders, which a
	# crowded map sent every second, against a delta naming one rider.
	var legacy_rows: Array = []
	for index: int in range(200):
		var legacy: Dictionary = MountDeltaState.v1_row(states[index])
		legacy["schema_version"] = 1
		legacy_rows.append(legacy)
	var legacy_payload: PackedByteArray = JSON.stringify({"schema_version": 1, "map": "isle",
		"states": legacy_rows}).to_utf8_buffer()
	var delta_payload: PackedByteArray = JSON.stringify({"schema_version": 2, "map": "isle",
		"full": false, "states": [states[7]], "removed": []}).to_utf8_buffer()
	started = Time.get_ticks_usec()
	for repeat: int in range(10):
		EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_MOUNT_STATES, legacy_payload)
	var legacy_decode_usec: float = float(Time.get_ticks_usec() - started) / 10.0
	started = Time.get_ticks_usec()
	for repeat: int in range(100):
		EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_MOUNT_DELTAS, delta_payload)
	var delta_decode_usec: float = float(Time.get_ticks_usec() - started) / 100.0
	print("mount table, 200 riders: whole table %d us, one-rider delta %.1f us, own countdown restated %.1f us; decode: complete table (%d bytes) %.0f us, one-rider delta (%d bytes) %.0f us" % [
		baseline_usec, delta_usec, refresh_usec, legacy_payload.size(), legacy_decode_usec,
		delta_payload.size(), delta_decode_usec])

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
