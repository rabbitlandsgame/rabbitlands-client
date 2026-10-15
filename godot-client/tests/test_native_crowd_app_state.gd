extends SceneTree
## AppState integration parity for the opt-in native actor-command path.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _packet(rows: Array) -> PackedByteArray:
	var payload := PackedByteArray()
	for row: Array in rows:
		var actor_id := int(row[0])
		payload.append(actor_id & 0xff)
		payload.append((actor_id >> 8) & 0xff)
		payload.append(int(row[1]) & 0xff)
	return payload

func _actor(actor_id: int) -> Dictionary:
	return {
		"actor_id": actor_id,
		"x": 10,
		"y": 20,
		"command_sequence": (1 << 40) + actor_id,
		"health": 17,
		"alive": true,
		"in_combat": true,
		"map": "four_gates",
		"appearance": {"hair": actor_id},
		"equipment_visuals": {0: 64},
	}

func _expected_after(actor: Dictionary, commands: Array) -> Dictionary:
	var expected := actor
	for command: int in commands:
		expected = ActorReducer.apply_command(expected, command)
	return expected

func _run() -> void:
	var state: Node = root.get_node("AppState")
	_expect(bool(state.call("native_crowd_reducer_active")),
		"ELORIA_NATIVE_CROWD activates AppState's native reducer")

	var paths: Array[StringName] = []
	var snapshots: Array[Dictionary] = []
	state.state_changed.connect(func(path: StringName) -> void:
		paths.append(path)
		snapshots.append((state.actors as Dictionary).duplicate(true)))

	var first_original := _actor(7)
	var second_original := _actor(8)
	var outer := {7: first_original, 8: second_original}
	state.actors = outer
	state.local_actor_id = 7
	state.call("take_changed_actors")
	state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND,
		_packet([[8, 40], [8, 46], [999, 22]]))
	_expect(is_same(state.actors, outer),
		"native AppState reduction keeps the outer actors Dictionary")
	_expect((state.actors as Dictionary)[8] == _expected_after(
		second_original, [40, 46]),
		"native AppState output matches turn then attack reduction")
	_expect(is_same((state.actors as Dictionary)[7], first_original),
		"an untouched AppState actor keeps its record identity")
	_expect(paths == [&"actors"],
		"a native command packet emits the same single actors signal")
	var changed: Dictionary = state.call("take_changed_actors") as Dictionary
	_expect(changed.has(8) and changed.size() == 1,
		"native AppState marks only the touched actor dirty")

	# Local command 19 must take the complete packet through the original loop.
	# Its combat signal is synchronous between the preceding and following rows.
	paths.clear()
	snapshots.clear()
	first_original = _actor(7)
	second_original = _actor(8)
	outer = {7: first_original, 8: second_original}
	state.actors = outer
	state.combat_state = {"open": true}
	state.call("take_changed_actors")
	state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND,
		_packet([[7, 22], [7, 19], [8, 22]]))
	_expect(paths == [&"combat_state", &"actors"],
		"local command 19 preserves combat then actors signal order")
	_expect(snapshots.size() == 2
		and snapshots[0][7] == _expected_after(first_original, [22, 19])
		and snapshots[0][8] == second_original,
		"combat listeners see the original reducer's intermediate actor state")
	_expect(snapshots[1][8] == _expected_after(second_original, [22]),
		"the actors signal sees commands after local command 19")
	changed = state.call("take_changed_actors") as Dictionary
	_expect(changed.has(7) and changed.has(8) and changed.size() == 2,
		"fallback marks every changed actor dirty")

	print("Native crowd AppState: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
