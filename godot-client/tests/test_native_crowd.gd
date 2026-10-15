extends SceneTree
## Native reducer parity. A normal checkout has no extension artifact, so this
## suite skips unless the native benchmark was built. Setting the opt-in flag
## turns an absent class into a failure instead of silently measuring nothing.

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
		var actor_id: int = int(row[0])
		payload.append(actor_id & 0xff)
		payload.append((actor_id >> 8) & 0xff)
		payload.append(int(row[1]) & 0xff)
	return payload

func _packed_matches(values: PackedInt32Array, expected: Array[int]) -> bool:
	if values.size() != expected.size():
		return false
	for index: int in range(values.size()):
		if values[index] != expected[index]:
			return false
	return true

func _base_actor(actor_id: int = 7) -> Dictionary:
	return {
		"actor_id": actor_id, "x": 10, "y": 20,
		"command_sequence": (1 << 40) + 9,
		"health": 31, "max_health": 47, "alive": true,
		"sitting": false, "in_combat": true,
		"map": "four_gates",
		"appearance": {"hair": 2},
		"equipment_visuals": {0: 64},
		"equipment_fallback_parts": [0],
	}

func _apply_expected(actors: Dictionary, payload: PackedByteArray) -> void:
	for offset: int in range(0, payload.size(), 3):
		var actor_id: int = int(payload[offset]) | (int(payload[offset + 1]) << 8)
		if actors.has(actor_id):
			actors[actor_id] = ActorReducer.apply_command(
				actors[actor_id] as Dictionary, int(payload[offset + 2]))

func _reduce(reducer: Object, actors: Dictionary,
		payload: PackedByteArray, local_actor_id := -1) -> Dictionary:
	return reducer.call("reduce_packet", actors, payload, local_actor_id) as Dictionary

func _run() -> void:
	if not ClassDB.class_exists(&"NativeCrowdReducer"):
		if OS.get_environment("ELORIA_NATIVE_CROWD") == "1":
			_expect(false, "ELORIA_NATIVE_CROWD requested but the extension is unavailable")
		print("Native crowd reducer: SKIP (extension not built)")
		quit(failures)
		return

	var reducer: Object = ClassDB.instantiate(&"NativeCrowdReducer")
	var store: Object = ClassDB.instantiate(&"NativeCrowdStore")
	_expect(reducer != null and store != null, "native prototype classes instantiate")

	# Every command byte, including unrecognised bytes, must have exactly the
	# same state transition as ActorReducer. This also exercises a sequence well
	# above 32 bits and confirms that cold nested values stay shared.
	for command: int in range(256):
		var original: Dictionary = _base_actor()
		var appearance: Dictionary = original.appearance
		var visuals: Dictionary = original.equipment_visuals
		var actors: Dictionary = {7: original}
		var expected: Dictionary = ActorReducer.apply_command(original, command)
		var result: Dictionary = _reduce(reducer, actors, _packet([[7, command]]))
		_expect(result.status == "ok", "command %d reduces" % command)
		_expect(actors[7] == expected, "command %d matches GDScript" % command)
		_expect(not is_same(actors[7], original),
			"command %d replaces the actor record" % command)
		_expect(is_same((actors[7] as Dictionary).appearance, appearance)
			and is_same((actors[7] as Dictionary).equipment_visuals, visuals),
			"command %d keeps nested cold records shared" % command)
		_expect(int(original.command_sequence) == (1 << 40) + 9
			and not original.has("command"),
			"command %d leaves the old actor record immutable" % command)

	var coalesced_original: Dictionary = _base_actor()
	var coalesced: Dictionary = {7: coalesced_original}
	var coalesced_payload := _packet([[7, 40], [7, 18], [7, 46]])
	var coalesced_expected: Dictionary = coalesced_original
	for command: int in [40, 18, 46]:
		coalesced_expected = ActorReducer.apply_command(coalesced_expected, command)
	var coalesced_result := _reduce(reducer, coalesced, coalesced_payload)
	_expect(coalesced[7] == coalesced_expected
		and int((coalesced[7] as Dictionary).facing_command) == 40
		and int((coalesced[7] as Dictionary).command) == 46,
		"turn, enter-combat and attack coalesce without losing facing")
	_expect(coalesced_result.changed_ids == PackedInt32Array([7]),
		"a repeated actor is returned once in first-touch order")

	var sparse_original := {"actor_id": 11, "appearance": {"hair": 4}}
	var sparse := {11: sparse_original}
	_reduce(reducer, sparse, _packet([[11, 255]]))
	for required: String in [
		"actor_id", "appearance", "x", "y", "command", "command_sequence"]:
		_expect((sparse[11] as Dictionary).has(required),
			"an unknown command retains or adds required field " + required)
	for absent: String in ["facing_command", "sitting", "in_combat", "alive", "health"]:
		_expect(not (sparse[11] as Dictionary).has(absent),
			"an unknown command does not invent sparse field " + absent)

	var death_actor := _base_actor()
	death_actor.sitting = true
	var death := {7: death_actor}
	_reduce(reducer, death, _packet([[7, 3], [7, 22]]))
	_expect(not bool((death[7] as Dictionary).alive)
		and int((death[7] as Dictionary).health) == 0
		and bool((death[7] as Dictionary).sitting)
		and bool((death[7] as Dictionary).in_combat),
		"death persists through movement without clearing sitting or combat")

	var untouched := {7: _base_actor()}
	var untouched_record: Dictionary = untouched[7]
	var malformed_result := _reduce(reducer, untouched, PackedByteArray([7, 0]))
	_expect(malformed_result.status == "invalid" and is_same(untouched[7], untouched_record),
		"a partial row is rejected before mutation")
	var missing_result := _reduce(reducer, untouched, _packet([[999, 22]]))
	_expect(missing_result.status == "ok" and missing_result.changed_ids.is_empty()
		and is_same(untouched[7], untouched_record),
		"an unknown actor id is ignored")
	var corrupt := {7: _base_actor(), 8: "not an actor record"}
	var corrupt_record: Dictionary = corrupt[7]
	var corrupt_result := _reduce(reducer, corrupt,
		_packet([[7, 22], [8, 22]]))
	_expect(corrupt_result.status == "fallback"
		and is_same(corrupt[7], corrupt_record),
		"a corrupt targeted record falls back before earlier rows mutate")
	var local_result := _reduce(reducer, untouched, _packet([[7, 22], [7, 19]]), 7)
	_expect(local_result.status == "fallback" and is_same(untouched[7], untouched_record),
		"a local leave-combat packet falls back before any earlier row mutates")

	# Fixed random mixed bursts compare the complete Dictionary output and dirty
	# order, including missing ids and repeated ids inside a packet.
	var random := RandomNumberGenerator.new()
	random.seed = 0x5eedc0de
	for trial: int in range(64):
		var expected_actors := {7: _base_actor(7), 8: _base_actor(8)}
		var actual_actors := expected_actors.duplicate(true)
		var rows: Array = []
		var expected_changed: Array[int] = []
		for unused: int in range(1 + random.randi_range(0, 31)):
			var actor_id: int = [7, 8, 999][random.randi_range(0, 2)]
			rows.append([actor_id, random.randi_range(0, 255)])
			if actor_id != 999 and not expected_changed.has(actor_id):
				expected_changed.append(actor_id)
		var payload := _packet(rows)
		_apply_expected(expected_actors, payload)
		var result := _reduce(reducer, actual_actors, payload)
		_expect(actual_actors == expected_actors,
			"seeded trial %d matches complete actor output" % trial)
		_expect(_packed_matches(result.changed_ids as PackedInt32Array, expected_changed),
			"seeded trial %d preserves dirty-id order" % trial)

	# The compact prototype must include materialisation in a parity comparison.
	var store_actors := {7: _base_actor(7), 8: _base_actor(8)}
	var store_expected: Dictionary = store_actors.duplicate(true)
	var packets: Array[PackedByteArray] = []
	for packet_index: int in range(16):
		var payload := _packet([
			[7, (20 + packet_index) & 0xff],
			[8, (255 - packet_index) & 0xff],
			[7, 46],
		])
		packets.append(payload)
		_apply_expected(store_expected, payload)
	store.call("reset", store_actors)
	var store_result: Dictionary = store.call("reduce_packets", packets, -1)
	var materialized: PackedInt32Array = store.call("snapshot_dirty", store_actors)
	_expect(store_result.status == "ok" and store_actors == store_expected,
		"compact storage matches after its Dictionary output boundary")
	_expect(materialized == PackedInt32Array([7, 8]),
		"compact materialisation reports each dirty actor once")
	var sparse_store := {11: {"actor_id": 11, "appearance": {"hair": 4}}}
	store.call("reset", sparse_store)
	store.call("reduce_packets", [_packet([[11, 255]])], -1)
	store.call("snapshot_dirty", sparse_store)
	for absent: String in ["facing_command", "sitting", "in_combat", "alive", "health"]:
		_expect(not (sparse_store[11] as Dictionary).has(absent),
			"compact output does not invent sparse field " + absent)

	var reused := {23: {"actor_id": 23, "command_sequence": (1 << 40)}}
	store.call("reset", reused)
	store.call("reduce_packets", [_packet([[23, 22]])], -1)
	store.call("remove", PackedInt32Array([23]))
	_expect(not bool(store.call("has", 23)), "remove drops typed state")
	reused = {23: {"actor_id": 23, "command_sequence": 7}}
	store.call("reset", reused)
	store.call("reduce_packets", [_packet([[23, 22]])], -1)
	store.call("snapshot_dirty", reused)
	_expect(int((reused[23] as Dictionary).command_sequence) == 8,
		"a reused id starts from its replacement record")
	store.call("clear")
	_expect(int(store.call("size")) == 0 and not bool(store.call("has", 23)),
		"clear drops compact state and its id index")

	print("Native crowd reducer: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
