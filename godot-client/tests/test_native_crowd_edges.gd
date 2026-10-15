extends SceneTree
## Edge parity for the opt-in native actor-command reducer and compact store.
## A normal checkout skips: setting ELORIA_NATIVE_CROWD=1 makes a missing
## extension a failure, so CI cannot silently claim that native coverage ran.

var failures := 0
var observed_paths: Array[StringName] = []

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
		"x": 10 + actor_id,
		"y": 20 + actor_id,
		"command_sequence": (1 << 40) + actor_id,
		"health": 31,
		"max_health": 47,
		"alive": true,
		"sitting": false,
		"in_combat": true,
		"map": "four_gates",
		"appearance": {"hair": actor_id},
		"equipment_visuals": {0: 64},
	}

func _on_state_changed(path: StringName) -> void:
	observed_paths.append(path)

func _normalized_protocol_errors(state: Node) -> Array[Dictionary]:
	var normalized: Array[Dictionary] = []
	for raw_error: Variant in state.get("recent_protocol_errors"):
		var error := (raw_error as Dictionary).duplicate(true)
		# Arrival time is intentionally nondeterministic; the command, reason and
		# payload size are the parity boundary.
		error.erase("msec")
		normalized.append(error)
	return normalized

func _app_state_case(state: Node, native_reducer: Variant,
		payload: PackedByteArray, seed: Dictionary) -> Dictionary:
	state.set("_native_crowd_reducer", native_reducer)
	state.set("actors", seed.duplicate(true))
	state.set("local_actor_id", -1)
	state.call("take_changed_actors")
	(state.get("recent_protocol_errors") as Array).clear()
	observed_paths.clear()
	state.call("_on_packet",
		EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, payload)
	return {
		"actors": (state.get("actors") as Dictionary).duplicate(true),
		"changed": (state.call("take_changed_actors") as Dictionary).duplicate(),
		"paths": observed_paths.duplicate(),
		"protocol_errors": _normalized_protocol_errors(state),
	}

func _check_app_state_edges(state: Node, native_reducer: Object) -> void:
	var seed := {7: _actor(7), 8: _actor(8)}
	var cases: Array[Dictionary] = [
		{"name": "normal", "payload": _packet([[7, 22], [7, 46], [999, 20]])},
		{"name": "malformed", "payload": PackedByteArray([7, 0])},
		{"name": "empty", "payload": PackedByteArray()},
		{"name": "unknown_actor", "payload": _packet([[999, 22]])},
	]
	for row: Dictionary in cases:
		var native_result := _app_state_case(
			state, native_reducer, row.payload as PackedByteArray, seed)
		var gdscript_result := _app_state_case(
			state, null, row.payload as PackedByteArray, seed)
		_expect(native_result == gdscript_result,
			"%s packet has identical native and GDScript AppState output" % row.name)
		match str(row.name):
			"normal":
				_expect(native_result.paths == [&"actors"]
					and (native_result.changed as Dictionary).size() == 1
					and (native_result.changed as Dictionary).has(7)
					and (native_result.actors as Dictionary)[7]
						== ActorReducer.apply_command(
							ActorReducer.apply_command(seed[7] as Dictionary, 22), 46),
					"normal native packet emits once and marks only its known actor")
			"malformed":
				_expect(native_result.paths == [&"protocol_errors"]
					and (native_result.changed as Dictionary).is_empty()
					and native_result.actors == seed
					and native_result.protocol_errors == [{
						"command": EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND,
						"error": "actor_command_length", "size": 2}],
					"malformed native packet falls through to the same protocol error")
			"empty", "unknown_actor":
				_expect(native_result.paths == [&"actors"]
					and (native_result.changed as Dictionary).is_empty()
					and native_result.actors == seed
					and (native_result.protocol_errors as Array).is_empty(),
					"%s packet emits actors once without dirty ids" % row.name)

	# A corrupt targeted record must be detected before an earlier valid row is
	# changed. Calling the reducer directly avoids intentionally triggering the
	# GDScript typed-assignment error after fallback.
	var valid_original := _actor(7)
	var corrupt := {7: valid_original, 8: "not an actor record"}
	var corrupt_result: Dictionary = native_reducer.call(
		"reduce_packet", corrupt, _packet([[7, 22], [8, 22]]), -1) as Dictionary
	_expect(corrupt_result.status == "fallback"
		and is_same(corrupt[7], valid_original)
		and corrupt[7] == _actor(7),
		"a corrupt targeted record falls back before any valid row mutates")

func _check_swap_remove(store: Object) -> void:
	# Remove a non-last slot, then reduce the actor swapped into that slot. This
	# exercises id_to_slot repair rather than the trivial one-record removal.
	var actors := {7: _actor(7), 8: _actor(8), 9: _actor(9)}
	var nine_original: Dictionary = actors[9]
	store.call("reset", actors)
	store.call("remove", PackedInt32Array([7]))
	actors.erase(7)
	_expect(not bool(store.call("has", 7)) and bool(store.call("has", 8))
		and bool(store.call("has", 9)) and int(store.call("size")) == 2,
		"swap removal repairs the dense id index")
	store.call("reduce_packets", [_packet([[9, 22]])], -1)
	var moved_materialized: PackedInt32Array = store.call("snapshot_dirty", actors)
	_expect(moved_materialized == PackedInt32Array([9])
		and actors[9] == ActorReducer.apply_command(nine_original, 22)
		and actors[8] == _actor(8),
		"the actor moved by swap removal still reduces and materializes")

	# The swapped last actor may already be dirty. Moving its ActorState must not
	# lose either its dirty bit or its first-touch entry.
	actors = {7: _actor(7), 8: _actor(8), 9: _actor(9)}
	nine_original = actors[9]
	store.call("reset", actors)
	store.call("reduce_packets", [_packet([[9, 20]])], -1)
	store.call("remove", PackedInt32Array([7]))
	actors.erase(7)
	moved_materialized = store.call("snapshot_dirty", actors)
	_expect(moved_materialized == PackedInt32Array([9])
		and actors[9] == ActorReducer.apply_command(nine_original, 20),
		"swap removal preserves a moved actor's pending dirty state")

func _check_sparse_commands(reducer: Object, store: Object) -> void:
	# One representative of every semantic family: walk, run, turn, ordinary
	# action, death, sit/stand, combat enter/leave and an unknown command.
	for command: int in [20, 30, 38, 46, 3, 13, 14, 18, 19, 255]:
		var appearance := {"hair": 4}
		var original := {"actor_id": 11, "appearance": appearance}
		var expected := ActorReducer.apply_command(original, command)

		var dictionary_actors := {11: original}
		var dictionary_result: Dictionary = reducer.call(
			"reduce_packet", dictionary_actors,
			_packet([[11, command]]), -1) as Dictionary
		_expect(dictionary_result.status == "ok"
			and dictionary_actors[11] == expected
			and is_same((dictionary_actors[11] as Dictionary).appearance, appearance),
			"sparse dictionary command %d matches fields and aliases" % command)

		var store_appearance := {"hair": 4}
		var store_actors := {11: {"actor_id": 11, "appearance": store_appearance}}
		store.call("reset", store_actors)
		var store_result: Dictionary = store.call(
			"reduce_packets", [_packet([[11, command]])], -1) as Dictionary
		var materialized: PackedInt32Array = store.call(
			"snapshot_dirty", store_actors)
		_expect(store_result.status == "ok"
			and materialized == PackedInt32Array([11])
			and store_actors[11] == expected
			and is_same((store_actors[11] as Dictionary).appearance, store_appearance),
			"sparse compact command %d matches fields and aliases" % command)

func _check_export_drift(store: Object) -> void:
	# Materialization can race an outer Dictionary removal/replacement. A record
	# that cannot be exported now must remain dirty and export after repair.
	var actors := {7: _actor(7), 8: _actor(8)}
	var seven_original: Dictionary = actors[7]
	var eight_original: Dictionary = actors[8]
	store.call("reset", actors)
	store.call("reduce_packets", [_packet([[7, 22], [8, 20]])], -1)
	actors.erase(7)
	var first: PackedInt32Array = store.call("snapshot_dirty", actors)
	_expect(first == PackedInt32Array([8])
		and actors[8] == ActorReducer.apply_command(eight_original, 20),
		"a missing outer record does not block other dirty exports")
	actors[7] = seven_original
	var recovered: PackedInt32Array = store.call("snapshot_dirty", actors)
	_expect(recovered == PackedInt32Array([7])
		and actors[7] == ActorReducer.apply_command(seven_original, 22),
		"a missing outer record remains dirty until it can be exported")

	actors = {7: _actor(7), 8: _actor(8)}
	eight_original = actors[8]
	store.call("reset", actors)
	store.call("reduce_packets", [_packet([[8, 26]])], -1)
	actors[8] = "temporarily corrupt"
	first = store.call("snapshot_dirty", actors)
	_expect(first.is_empty(),
		"a non-Dictionary outer record is not reported as materialized")
	actors[8] = eight_original
	recovered = store.call("snapshot_dirty", actors)
	_expect(recovered == PackedInt32Array([8])
		and actors[8] == ActorReducer.apply_command(eight_original, 26),
		"a non-Dictionary outer record remains dirty until repaired")

func _run() -> void:
	if OS.get_environment("ELORIA_NATIVE_CROWD") != "1":
		print("Native crowd edges: SKIP (set ELORIA_NATIVE_CROWD=1 to opt in)")
		quit(0)
		return
	if not ClassDB.class_exists(&"NativeCrowdReducer") \
			or not ClassDB.class_exists(&"NativeCrowdStore"):
		_expect(false, "ELORIA_NATIVE_CROWD requested but the extension is unavailable")
		print("Native crowd edges: FAIL (extension not built)")
		quit(failures)
		return

	var reducer: Object = ClassDB.instantiate(&"NativeCrowdReducer")
	var store: Object = ClassDB.instantiate(&"NativeCrowdStore")
	_expect(reducer != null and store != null, "native edge-test classes instantiate")
	if reducer == null or store == null:
		quit(failures)
		return

	var state: Node = root.get_node("AppState")
	var active_reducer: Object = state.get("_native_crowd_reducer") as Object
	_expect(active_reducer != null,
		"ELORIA_NATIVE_CROWD activates AppState's native reducer")
	state.state_changed.connect(_on_state_changed)
	if active_reducer != null:
		_check_app_state_edges(state, active_reducer)
	state.set("_native_crowd_reducer", active_reducer)

	_check_swap_remove(store)
	_check_sparse_commands(reducer, store)
	_check_export_drift(store)

	print("Native crowd edges: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
