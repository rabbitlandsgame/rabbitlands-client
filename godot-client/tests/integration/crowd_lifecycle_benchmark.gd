extends SceneTree
## Packet/AppState actor arrival/departure cost; Main presentation stays out.
const COUNTS: Array[int] = [100, 200, 300, 500]
const REPEATS := 9
const FIRST_ACTOR_ID := 4000
var failures: Array[String] = []
func _init() -> void:
	call_deferred("_run")
func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)
func _u16(value: int) -> PackedByteArray:
	return PackedByteArray([value & 0xff, (value >> 8) & 0xff])
## Mirrors test_protocol.gd's minimal legacy/extended actor fixtures: id, x, y,
## unused z, rotation, actor type, frame, max health, health, kind, NUL name.
func _actor_payload(actor_id: int, index: int, extended: bool) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append_array(_u16(actor_id))
	payload.append_array(_u16(10 + index % 100))
	payload.append_array(_u16(12 + index / 100))
	payload.append_array(_u16(0))
	payload.append_array(_u16(0))
	if extended:
		payload.append_array(_u16(403))
	else:
		payload.append(3)
	payload.append(0)
	payload.append_array(_u16(20))
	payload.append_array(_u16(20))
	payload.append(3)
	payload.append_array(("Crowd %d" % index).to_ascii_buffer())
	payload.append(0)
	return payload
func _fixtures(count: int) -> Dictionary:
	var rows: Array[Dictionary] = []
	var expected: Dictionary = {}
	var remove := PackedByteArray()
	for index: int in range(count):
		var actor_id := FIRST_ACTOR_ID + index
		var extended := index % 2 == 1
		var command := EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED \
			if extended else EloriaProtocol.ServerMessage.ADD_NEW_ACTOR
		var payload := _actor_payload(actor_id, index, extended)
		rows.append({"command": command, "payload": payload})
		var actor: Dictionary = EloriaProtocol.decode_server(command, payload)
		actor["map"] = "four_gates"
		expected[actor_id] = actor
		remove.append_array(_u16(actor_id))
	return {"rows": rows, "expected": expected, "remove": remove}
func _commands(first_id: int) -> PackedByteArray:
	var payload := PackedByteArray()
	for row: Array in [[first_id, 22], [65500, 255]]:
		payload.append_array(_u16(row[0]))
		payload.append(row[1])
	return payload
func _summary(samples: Array[float]) -> Dictionary:
	var ordered := samples.duplicate()
	ordered.sort()
	return {"minimumMs": ordered[0], "medianMs": ordered[ordered.size() / 2],
		"p95Ms": ordered[ceili(ordered.size() * 0.95) - 1],
		"maximumMs": ordered[-1], "samplesMs": samples}
func _measure_count(state: Node, count: int) -> Dictionary:
	var fixture := _fixtures(count)
	var failures_before := failures.size()
	var add_samples: Array[float] = []
	var remove_samples: Array[float] = []
	var decode_error_count := 0
	for repeat: int in range(REPEATS):
		state.set("actors", {})
		state.set("current_map", "four_gates")
		state.set("adjacent_maps", {})
		state.call("take_changed_actors")
		(state.get("recent_protocol_errors") as Array).clear()
		var started := Time.get_ticks_usec()
		for row: Dictionary in fixture.rows:
			state.call("_on_packet", int(row.command), row.payload as PackedByteArray)
		add_samples.append(float(Time.get_ticks_usec() - started) / 1000.0)
		var actors: Dictionary = state.get("actors")
		_expect(actors == fixture.expected, "%d/%d add Dictionary parity" % [count, repeat])
		var dirty: Dictionary = state.call("take_changed_actors")
		_expect(dirty.size() == count, "%d/%d add dirty count" % [count, repeat])
		started = Time.get_ticks_usec()
		state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR,
			fixture.remove as PackedByteArray)
		remove_samples.append(float(Time.get_ticks_usec() - started) / 1000.0)
		_expect((state.get("actors") as Dictionary).is_empty(),
			"%d/%d removes every actor" % [count, repeat])
		_expect((state.call("take_changed_actors") as Dictionary).is_empty(),
			"%d/%d removal creates no stale dirty actor" % [count, repeat])
		state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND,
			_commands(FIRST_ACTOR_ID))
		_expect((state.get("actors") as Dictionary).is_empty()
			and (state.call("take_changed_actors") as Dictionary).is_empty(),
			"%d/%d removed and unknown commands are ignored" % [count, repeat])
		var reused_payload := _actor_payload(FIRST_ACTOR_ID, count + repeat, true)
		state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED,
			reused_payload)
		var reused_expected: Dictionary = EloriaProtocol.decode_server(
			EloriaProtocol.ServerMessage.ADD_NEW_ACTOR_EXTENDED, reused_payload)
		reused_expected["map"] = "four_gates"
		actors = state.get("actors")
		dirty = state.call("take_changed_actors")
		_expect(actors.size() == 1 and actors.get(FIRST_ACTOR_ID) == reused_expected
			and dirty.size() == 1 and dirty.has(FIRST_ACTOR_ID),
			"%d/%d reused id has only fresh state and is dirty" % [count, repeat])
		var decode_errors: int = (state.get("recent_protocol_errors") as Array).size()
		decode_error_count += decode_errors
		_expect(decode_errors == 0, "%d/%d has no protocol decode errors" % [count, repeat])
	return {"actors": count, "legacyActors": count / 2,
		"extendedActors": count / 2, "repeats": REPEATS,
		"packetShape": "%d add callbacks + 1 batched removal callback" % count,
		"dictionaryParityVerified": failures.size() == failures_before,
		"decodeErrorCount": decode_error_count, "add": _summary(add_samples),
		"remove": _summary(remove_samples)}
func _run() -> void:
	var expected_user := OS.get_environment("ELORIA_CROWD_EXPECT_USER_ROOT").replace("\\", "/").trim_suffix("/")
	var actual_user := OS.get_user_data_dir().replace("\\", "/").trim_suffix("/")
	if expected_user.is_empty() or (actual_user != expected_user
			and not actual_user.begins_with(expected_user + "/")):
		push_error("crowd lifecycle user data escaped its explicit root: " + actual_user)
		quit(1)
		return
	var artifacts := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		push_error("ELORIA_ARTIFACT_DIR is required")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(artifacts)
	var state: Node = root.get_node("AppState")
	var requested_native := OS.get_environment("ELORIA_NATIVE_CROWD") == "1"
	var native_active: bool = state.call("native_crowd_reducer_active")
	_expect(native_active == requested_native, "requested reducer mode is active")
	var report := {"scope": "protocol decode plus AppState actor add/remove; no Main",
		"backend": "native" if native_active else "gdscript", "nativeActive": native_active,
		"repeats": REPEATS, "counts": COUNTS, "userDataDir": actual_user,
		"commit": OS.get_environment("ELORIA_CROWD_COMMIT"),
		"sourceSha256": OS.get_environment("ELORIA_CROWD_SOURCE_HASH"),
		"sharedHostLabel": OS.get_environment("ELORIA_CROWD_INTERFERENCE"),
		"godot": "%d.%d.%d" % [Engine.get_version_info()["major"],
			Engine.get_version_info()["minor"], Engine.get_version_info()["patch"]],
		"unixTime": int(Time.get_unix_time_from_system()), "results": []}
	for count: int in COUNTS:
		report.results.append(_measure_count(state, count))
	var output := OS.get_environment("ELORIA_BENCH_OUTPUT")
	if output.is_empty():
		output = "crowd-lifecycle-%s.json" % report.backend
	var file := FileAccess.open(artifacts.path_join(output), FileAccess.WRITE)
	_expect(file != null, "lifecycle report is writable")
	report["failureCount"] = failures.size()
	report["failures"] = failures
	if file != null:
		file.store_string(JSON.stringify(report, "  "))
		file.close()
	print("Crowd lifecycle benchmark: ",
		"PASS" if failures.is_empty() else "FAIL (%d)" % failures.size())
	quit(failures.size())
