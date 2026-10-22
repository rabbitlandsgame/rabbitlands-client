extends SceneTree
## Phase 4 interest state through AppState and Main: remote steps timed by the
## server's frame stamps, presence dots handed over at the edge of the area of
## interest and drawn on the maps, the riding table kept by deltas, the
## "+N nearby" indicator and the declared actor cap. Everything here is idle on
## a server that sends none of it, which the first checks pin down.

const Op := EloriaProtocol.ServerMessage
const ServerTimePacing := preload("res://src/actors/server_time_pacing.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

static func _u16(value: int) -> PackedByteArray:
	return PackedByteArray([value & 0xff, (value >> 8) & 0xff])

## A stock ADD_NEW_ACTOR payload.
static func _actor_payload(actor_id: int, x: int, y: int, kind: int, actor_name: String) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append_array(_u16(actor_id))
	payload.append_array(_u16(x))
	payload.append_array(_u16(y))
	payload.append_array(_u16(0))
	payload.append_array(_u16(0))
	payload.append(6)
	payload.append(0)
	payload.append_array(_u16(50))
	payload.append_array(_u16(50))
	payload.append(kind)
	payload.append_array(actor_name.to_ascii_buffer())
	payload.append(0)
	return payload

static func _step(actor_id: int, command := 22) -> PackedByteArray:
	return _u16(actor_id) + PackedByteArray([command])

static func _stamp(server_ms: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u32(0, server_ms)
	return payload

## ELORIA_PRESENCE: `rows` of [actor id, x, y], `hidden` near actors held back.
static func _presence(rows: Array, hidden := 0, cap := 160) -> PackedByteArray:
	var payload := PackedByteArray([1, 1, 80, 88])
	payload.append_array(_u16(cap))
	payload.append_array(_u16(hidden))
	payload.append_array(_u16(0))
	payload.append_array(_u16(rows.size()))
	for row: Array in rows:
		payload.append_array(_u16(row[0]) + _u16(row[1]) + _u16(row[2]))
		payload.append(0)
	return payload

static func _mount_deltas(map_name: String, full: bool, rows: Array, removed := []) -> PackedByteArray:
	return JSON.stringify({"schema_version": 2, "map": map_name, "full": full,
		"states": rows, "removed": removed}).to_utf8_buffer()

static func _rider(actor_id: int, mode: String, map_name: String, owner: String) -> Dictionary:
	return {"actor_id": actor_id, "mode": mode, "gait": "cruise" if mode == "mounted" else "on_foot",
		"mount_id": "moor_pony" if mode != "on_foot" else "", "selected_mount_id": "moor_pony",
		"step_us": 133333, "can_summon": false, "blocked_reason": "", "map": map_name, "owner": owner,
		"summon_due": 0, "combat_until": 0, "endurance_ms": 8000, "endurance_at": 0,
		"endurance_rate": 0, "endurance_max_ms": 8000}

func _run() -> void:
	var state: Node = root.get_node("AppState")
	_state_checks(state)
	await _main_checks(state)
	print("interest state tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _state_checks(state: Node) -> void:
	state.call("_on_packet", Op.CHANGE_MAP, "isle".to_ascii_buffer() + PackedByteArray([0]))
	state.set("local_actor_id", 77)
	state.call("_on_packet", Op.ADD_NEW_ACTOR, _actor_payload(1000, 50, 60, 1, "Wren"))
	state.call("_on_packet", Op.ADD_NEW_ACTOR, _actor_payload(1001, 52, 60, 5, "Hound"))
	state.call("_on_packet", Op.ADD_NEW_ACTOR, _actor_payload(77, 40, 40, 1, "Me"))
	var actors: Dictionary = state.get("actors")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	_expect(not (actors[1000] as Dictionary).has(ServerTimePacing.STEP_KEY),
		"without stamped frames a step carries no server time")
	_expect(not state.get("server_clock").synced, "and the clock stays unsynced")

	state.call("_on_packet", Op.ELORIA_SERVER_TIME, _stamp(5000))
	var clock = state.get("server_clock")
	_expect(clock.synced, "the first ELORIA_SERVER_TIME starts the clock")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	var first: Dictionary = actors[1000]
	var first_time: int = int(first.get(ServerTimePacing.STEP_KEY, -1))
	_expect(first_time == clock.to_local_msec(5000),
		"a step in a stamped frame carries the frame's time on the local clock")
	_expect(float(first.get(ServerTimePacing.PLAYOUT_KEY, 0.0)) > 0.0, "and the playout delay")
	_expect(int((actors[1000] as Dictionary).x) == 52, "the step itself still moves the actor")
	state.call("_on_packet", Op.ELORIA_SERVER_TIME, _stamp(5050))
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	_expect(int((actors[1000] as Dictionary)[ServerTimePacing.STEP_KEY]) == first_time,
		"a second step before the next presentation pass keeps the first one's time")
	state.call("take_changed_actors")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	_expect(int((actors[1000] as Dictionary)[ServerTimePacing.STEP_KEY]) == clock.to_local_msec(5050),
		"the next pass takes the newest frame's time")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(77))
	_expect(not (actors[77] as Dictionary).has(ServerTimePacing.STEP_KEY),
		"the player's own steps stay on arrival pacing")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1001, 40))
	_expect(not (actors[1001] as Dictionary).has(ServerTimePacing.STEP_KEY), "a turn is not a step")
	# A stamped step, then a step that comes without a current stamp: the
	# row keeps its keys from packet to packet, so the old stamp must go.
	state.call("take_changed_actors")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	_expect((actors[1000] as Dictionary).has(ServerTimePacing.STEP_KEY), "a stamped step")
	state.set("_frame_stamp_read_msec", Time.get_ticks_msec() - 1000)
	state.call("take_changed_actors")
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	_expect(not (actors[1000] as Dictionary).has(ServerTimePacing.STEP_KEY)
		and not (actors[1000] as Dictionary).has(ServerTimePacing.PLAYOUT_KEY),
		"then a step long after the last stamp carries no server time at all")
	var stamped_before: Dictionary = (actors[1000] as Dictionary).duplicate()
	stamped_before[ServerTimePacing.STEP_KEY] = 1
	stamped_before[ServerTimePacing.PLAYOUT_KEY] = 0.05
	actors[1000] = stamped_before
	state.set("_frame_stamps_seen", false)
	state.call("_on_packet", Op.ADD_ACTOR_COMMAND, _step(1000))
	_expect(not (actors[1000] as Dictionary).has(ServerTimePacing.STEP_KEY),
		"and a stamp on a row is taken off by any unstamped step, stamps or not")
	state.set("_frame_stamps_seen", true)

	var presence = state.get("presence")
	state.call("_on_packet", Op.REMOVE_ACTOR, _u16(1001))
	_expect(presence.dot_count() == 0, "before the server sends presence, a removed actor leaves no dot")
	state.call("_on_packet", Op.ADD_NEW_ACTOR, _actor_payload(1001, 52, 60, 5, "Hound"))
	state.call("_on_packet", Op.ELORIA_PRESENCE, _presence([[2000, 300, 300]], 4))
	_expect(presence.active and presence.has_dot(2000) and presence.nearby_hidden == 4
		and presence.cap == 160, "ELORIA_PRESENCE places its dots and the nearby count")
	state.call("_on_packet", Op.REMOVE_ACTOR, _u16(1000) + _u16(1001))
	_expect(presence.has_dot(1000) and not presence.has_dot(1001),
		"with presence, a player leaving the area keeps a dot and a creature does not")
	state.call("_on_packet", Op.CHANGE_MAP, "cove".to_ascii_buffer() + PackedByteArray([0]))
	_expect(presence.dot_count() == 0 and presence.map == "cove", "a change of map clears the dots")

	var emitted: Array[StringName] = []
	var record := func(path: StringName) -> void: emitted.append(path)
	state.connect("state_changed", record)
	state.call("_on_packet", Op.ELORIA_MOUNT_DELTAS, _mount_deltas("cove", true,
		[_rider(77, "mounted", "cove", "Me")]))
	_expect((state.get("actor_mounts") as Dictionary).has(77) and emitted.has(&"mount_deltas"),
		"a whole riding table by delta fills the table and asks for the changed mounts only")
	var summoning := _rider(77, "summoning", "cove", "Me")
	summoning["summon_due"] = 6000
	state.call("_on_packet", Op.ELORIA_MOUNT_DELTAS, _mount_deltas("cove", false, [summoning]))
	var own: Dictionary = (state.get("actor_mounts") as Dictionary)[77]
	_expect(str(own.mode) == "summoning" and int(own.summon_remaining_ms) > 0,
		"the own calling is counted from its deadline (%d ms)" % int(own.summon_remaining_ms))
	state.set("_mount_countdown_msec", 0)
	own["summon_remaining_ms"] = 1499
	state.call("_process", 0.0)
	_expect(emitted.has(&"mount_countdowns") and int(own.summon_remaining_ms) != 1499,
		"and restated between packets for the banner and the mounts window")
	state.call("_on_packet", Op.ELORIA_MOUNT_DELTAS, _mount_deltas("cove", false, [], [77]))
	_expect(not (state.get("actor_mounts") as Dictionary).has(77), "a removal takes the row away")
	state.disconnect("state_changed", record)

	_measure_stamping(state)
	state.call("_on_connection_state_changed", "disconnected")
	_expect(not clock.synced and not presence.active and not bool(state.get("_frame_stamps_seen"))
		and str(state.get("mount_deltas").map).is_empty(), "a dropped connection forgets all of it")

## What stamping costs on the packet path: 100 actors each taking a step in
## one ADD_ACTOR_COMMAND, applied with and without a stamped frame before it.
## Printed for the Phase 4 page, not gated.
func _measure_stamping(state: Node) -> void:
	for actor_id: int in range(4000, 4100):
		state.call("_on_packet", Op.ADD_NEW_ACTOR, _actor_payload(actor_id, 10, 10, 1, "P%d" % actor_id))
	var packet := PackedByteArray()
	for actor_id: int in range(4000, 4100):
		packet.append_array(_step(actor_id))
	var timings: Array[float] = []
	for stamped: bool in [false, true]:
		state.set("_frame_stamps_seen", false)
		var started := Time.get_ticks_usec()
		for round_index: int in range(50):
			if stamped:
				state.call("_on_packet", Op.ELORIA_SERVER_TIME, _stamp(9000 + round_index * 50))
			state.call("_on_packet", Op.ADD_ACTOR_COMMAND, packet)
			state.call("take_changed_actors")
		timings.append(float(Time.get_ticks_usec() - started) / 50.0)
	print("100 steps in one packet: %.0f us unstamped, %.0f us with the stamp (+%.1f us a step)" % [
		timings[0], timings[1], (timings[1] - timings[0]) / 100.0])
	var removed := PackedByteArray()
	for actor_id: int in range(4000, 4100):
		removed.append_array(_u16(actor_id))
	state.call("_on_packet", Op.REMOVE_ACTOR, removed)

func _main_checks(state: Node) -> void:
	var scene: Resource = load("res://src/app/main.tscn")
	_expect(scene is PackedScene, "main scene loads")
	if not scene is PackedScene:
		return
	var main: Control = (scene as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.set_process(false)
	state.set("current_map", "isle")
	state.set("local_actor_id", 77)
	(state.get("actors") as Dictionary)[77] = {"actor_id": 77, "x": 100, "y": 100, "kind": 1, "map": "isle"}
	var presence = state.get("presence")
	state.call("_on_packet", Op.ELORIA_PRESENCE, _presence([[3000, 190, 100], [3001, 600, 600]]))
	var full_map: Control = main.get("full_map")
	full_map.visible = false
	var marks: Array = main.call("_presence_marks")
	_expect(marks.size() == 1, "with only the minimap open, dots beyond its view are not marked (%d)" % marks.size())
	full_map.visible = true
	marks = main.call("_presence_marks")
	_expect(marks.size() == 2, "the full map marks every dot")
	full_map.visible = false
	var collected: Array = main.call("_collect_minimap_marks")
	var presence_marks := 0
	for mark: Dictionary in collected:
		if mark.get("type") == &"player" and is_equal_approx(float(mark.get("radius", 0.0)), main.PRESENCE_DOT_RADIUS):
			presence_marks += 1
			var expected: Vector3 = (main.get("adapter") as CoordinateAdapter).tile_center(190, 100)
			_expect((mark.position as Vector3).is_equal_approx(expected),
				"a dot is marked at the centre of its tile")
	_expect(presence_marks == 1, "the minimap's marks include the dot in view")

	var indicator: Label = main.get("nearby_indicator")
	_expect(indicator != null and not indicator.visible, "the nearby indicator starts hidden")
	# Main follows state changes only for a logged-in session.
	state.set("authenticated", true)
	state.call("_on_packet", Op.ELORIA_PRESENCE, _presence([[3000, 190, 100]], 12))
	state.set("authenticated", false)
	_expect(indicator.visible and indicator.text.contains("12"), "and shows the count the server sends (%s)" % indicator.text)
	_expect(indicator.get_parent() == main.get("minimap"), "on the minimap")

	main.call("_on_state_changed", &"mount_deltas")
	_expect(true, "re-binding the changed mounts with no bodies built is harmless")

	var settings: Node = main.get("settings_window")
	var spin: Node = (settings.get("panel") as Node).find_child("actor_cap", true, false)
	_expect(spin is SpinBox and is_equal_approx((spin as SpinBox).max_value, 160.0),
		"the graphics settings offer the actor cap up to 160")
	main.call("_on_client_setting_changed", "Graphics", "actor_cap", 87.0)
	_expect(int(main.get("_actor_cap")) == 90 and int(root.get_node("Network").get("declared_actor_cap")) == 90,
		"a chosen cap is kept on its step and announced through the network client")
	var saved := ConfigFile.new()
	saved.load(main.SETTINGS_PATH)
	_expect(int(saved.get_value("graphics", "actor_cap", -1)) == 90, "and saved with the graphics settings")
	main.queue_free()
	await process_frame

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
