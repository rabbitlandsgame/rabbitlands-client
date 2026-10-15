extends SceneTree
## Reducer-only comparison with identical input and final Dictionary output.
## The full 300-actor scene benchmark remains the acceptance instrument; this
## script answers only whether the native state boundary itself buys enough to
## justify integration.

const ACTOR_COUNT := 300
const ACTIVE_ACTORS := 100
const CROWD_PACKET_COUNT := 120
const LEGACY_ACTOR_COUNT := 24
const LEGACY_PACKET_COUNT := 300
const LEGACY_COMMANDS_PER_PACKET := 8
const TRIALS := 9
const FIRST_ACTOR_ID := 4000

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _seed_actors(count := ACTOR_COUNT) -> Dictionary:
	var actors: Dictionary = {}
	for index: int in range(count):
		var actor_id := FIRST_ACTOR_ID + index
		actors[actor_id] = {
			"actor_id": actor_id,
			"x": 100 + index % 30,
			"y": 200 + index / 30,
			"rotation": 0,
			"actor_type": 1,
			"kind": 1,
			"name": "Crowd %d" % index,
			"health": 100,
			"max_health": 100,
			"alive": true,
			"appearance": {"hair": index % 8},
			"equipment_visuals": {0: 64 + index % 4},
			"equipment_fallback_parts": [0],
			"map": "four_gates",
		}
	return actors

func _packets() -> Array[PackedByteArray]:
	var packets: Array[PackedByteArray] = []
	var commands: PackedInt32Array = PackedInt32Array([
		20, 21, 22, 23, 24, 25, 26, 27,
		30, 31, 32, 33, 34, 35, 36, 37,
		38, 40, 44, 46, 5, 18, 13, 14, 255,
	])
	for packet_index: int in range(CROWD_PACKET_COUNT):
		var payload := PackedByteArray()
		for active_index: int in range(ACTIVE_ACTORS):
			var actor_id := FIRST_ACTOR_ID + active_index
			payload.append(actor_id & 0xff)
			payload.append((actor_id >> 8) & 0xff)
			payload.append(commands[(packet_index + active_index) % commands.size()])
		packets.append(payload)
	return packets

## The actor-command portion of client_benchmarks.gd's legacy 500-packet mix:
## 300 command-2 packets, eight walk commands each, rotating over 24 actors.
func _legacy_packets() -> Array[PackedByteArray]:
	var packets: Array[PackedByteArray] = []
	for packet_index: int in range(LEGACY_PACKET_COUNT):
		var payload := PackedByteArray()
		for slot: int in range(LEGACY_COMMANDS_PER_PACKET):
			var actor_id := FIRST_ACTOR_ID + (
				(packet_index + slot) % LEGACY_ACTOR_COUNT)
			payload.append(actor_id & 0xff)
			payload.append((actor_id >> 8) & 0xff)
			payload.append(20 + slot)
		packets.append(payload)
	return packets

func _reduce_gdscript(actors: Dictionary,
		payload: PackedByteArray, changed: Dictionary) -> void:
	var event: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, payload)
	for raw_command: Variant in event.commands:
		var command: Dictionary = raw_command as Dictionary
		var actor_id := int(command.actor_id)
		if not actors.has(actor_id):
			continue
		actors[actor_id] = ActorReducer.apply_command(
			actors[actor_id] as Dictionary, int(command.command))
		changed[actor_id] = true

func _time_gdscript(seed: Dictionary,
		packets: Array[PackedByteArray]) -> Dictionary:
	var actors: Dictionary = seed.duplicate(true)
	var changed: Dictionary = {}
	var started := Time.get_ticks_usec()
	for payload: PackedByteArray in packets:
		_reduce_gdscript(actors, payload, changed)
	return {"microseconds": Time.get_ticks_usec() - started,
		"actors": actors, "changed": changed}

func _time_native_dictionary(reducer: Object, seed: Dictionary,
		packets: Array[PackedByteArray]) -> Dictionary:
	var actors: Dictionary = seed.duplicate(true)
	var changed: Dictionary = {}
	var started := Time.get_ticks_usec()
	for payload: PackedByteArray in packets:
		var result: Dictionary = reducer.call(
			"reduce_packet", actors, payload, -1) as Dictionary
		if result.status != "ok":
			failures += 1
			break
		for actor_id: int in result.changed_ids:
			changed[actor_id] = true
	return {"microseconds": Time.get_ticks_usec() - started,
		"actors": actors, "changed": changed}

func _time_compact_per_packet(store: Object, seed: Dictionary,
		packets: Array[PackedByteArray]) -> Dictionary:
	var actors: Dictionary = seed.duplicate(true)
	var changed: Dictionary = {}
	var started := Time.get_ticks_usec()
	store.call("reset", actors)
	for payload: PackedByteArray in packets:
		var result: Dictionary = store.call(
			"reduce_packets", [payload], -1) as Dictionary
		if result.status != "ok":
			failures += 1
			break
		var materialized: PackedInt32Array = store.call("snapshot_dirty", actors)
		for actor_id: int in materialized:
			changed[actor_id] = true
	return {"microseconds": Time.get_ticks_usec() - started,
		"actors": actors, "changed": changed}

func _time_compact_deferred(store: Object, seed: Dictionary,
		packets: Array[PackedByteArray]) -> Dictionary:
	var actors: Dictionary = seed.duplicate(true)
	var changed: Dictionary = {}
	var packet_array: Array = []
	packet_array.assign(packets)
	var started := Time.get_ticks_usec()
	store.call("reset", actors)
	var result: Dictionary = store.call(
		"reduce_packets", packet_array, -1) as Dictionary
	if result.status != "ok":
		failures += 1
	var materialized: PackedInt32Array = store.call("snapshot_dirty", actors)
	for actor_id: int in materialized:
		changed[actor_id] = true
	return {"microseconds": Time.get_ticks_usec() - started,
		"actors": actors, "changed": changed}

func _time_compact_components(store: Object, seed: Dictionary,
		packets: Array[PackedByteArray], deferred: bool) -> Dictionary:
	# Measured separately so per-phase clock reads do not inflate the total mode.
	var actors: Dictionary = seed.duplicate(true)
	var reset_started := Time.get_ticks_usec()
	store.call("reset", actors)
	var reset_usec := Time.get_ticks_usec() - reset_started
	var reduce_usec := 0
	var materialize_usec := 0
	if deferred:
		var packet_array: Array = []
		packet_array.assign(packets)
		var reduce_started := Time.get_ticks_usec()
		store.call("reduce_packets", packet_array, -1)
		reduce_usec = Time.get_ticks_usec() - reduce_started
		var materialize_started := Time.get_ticks_usec()
		store.call("snapshot_dirty", actors)
		materialize_usec = Time.get_ticks_usec() - materialize_started
	else:
		for payload: PackedByteArray in packets:
			var reduce_started := Time.get_ticks_usec()
			store.call("reduce_packets", [payload], -1)
			reduce_usec += Time.get_ticks_usec() - reduce_started
			var materialize_started := Time.get_ticks_usec()
			store.call("snapshot_dirty", actors)
			materialize_usec += Time.get_ticks_usec() - materialize_started
	return {"resetMicroseconds": reset_usec,
		"reduceMicroseconds": reduce_usec,
		"materializeMicroseconds": materialize_usec}

func _median(samples: Array[float]) -> float:
	var ordered := samples.duplicate()
	ordered.sort()
	return ordered[ordered.size() / 2]

func _duration_summary(samples: Array[float]) -> Dictionary:
	var ordered := samples.duplicate()
	ordered.sort()
	var median_usec := _median(samples)
	var deviations: Array[float] = []
	for sample: float in samples:
		deviations.append(absf(sample - median_usec))
	return {
		"medianMilliseconds": snappedf(median_usec / 1000.0, 0.001),
		"minimumMilliseconds": snappedf(ordered[0] / 1000.0, 0.001),
		"maximumMilliseconds": snappedf(ordered[-1] / 1000.0, 0.001),
		"medianAbsoluteDeviationMilliseconds": snappedf(
			_median(deviations) / 1000.0, 0.001),
	}

func _summarize(samples: Array[float], packet_count: int,
		command_count: int) -> Dictionary:
	var median_usec := _median(samples)
	var summary := _duration_summary(samples)
	summary.merge({
		"trials": samples.size(),
		"microseconds": samples,
		"medianMicrosecondsPerPacket": snappedf(
			median_usec / float(packet_count), 0.01),
		"medianMicrosecondsPerCommand": snappedf(
			median_usec / float(command_count), 0.001),
	})
	return summary

func _measure_scenario(reducer: Object, store: Object, seed: Dictionary,
		packets: Array[PackedByteArray], command_count: int) -> Dictionary:
	# Untimed reference and warmup keep class registration and first-call setup
	# out of the samples.
	var expected := _time_gdscript(seed, packets)
	_time_native_dictionary(reducer, seed, packets)
	_time_compact_per_packet(store, seed, packets)
	_time_compact_deferred(store, seed, packets)

	var samples: Dictionary = {
		"gdscript": [] as Array[float],
		"nativeDictionary": [] as Array[float],
		"nativeCompactPerPacket": [] as Array[float],
		"nativeCompactDeferred": [] as Array[float],
	}
	var component_samples: Dictionary = {
		"nativeCompactPerPacket": {
			"reset": [] as Array[float], "reduce": [] as Array[float],
			"materialize": [] as Array[float]},
		"nativeCompactDeferred": {
			"reset": [] as Array[float], "reduce": [] as Array[float],
			"materialize": [] as Array[float]},
	}
	var mode_order: Array[String] = ["gdscript", "nativeDictionary",
		"nativeCompactPerPacket", "nativeCompactDeferred"]
	for trial: int in range(TRIALS):
		var measured_by_mode: Dictionary = {}
		for offset: int in range(mode_order.size()):
			var mode := mode_order[(trial + offset) % mode_order.size()]
			var measured: Dictionary
			match mode:
				"gdscript": measured = _time_gdscript(seed, packets)
				"nativeDictionary": measured = _time_native_dictionary(
					reducer, seed, packets)
				"nativeCompactPerPacket": measured = _time_compact_per_packet(
					store, seed, packets)
				_: measured = _time_compact_deferred(store, seed, packets)
			measured_by_mode[mode] = measured
			(samples[mode] as Array[float]).append(float(measured.microseconds))
		for measured: Dictionary in measured_by_mode.values():
			_expect(measured.actors == expected.actors,
				"each reducer produces the same final actor Dictionaries")
			_expect(measured.changed == expected.changed,
				"each reducer produces the same dirty actor set")
		for component_mode: String in [
			"nativeCompactPerPacket", "nativeCompactDeferred"]:
			var component_result := _time_compact_components(store, seed, packets,
				component_mode == "nativeCompactDeferred")
			for component: String in ["reset", "reduce", "materialize"]:
				(component_samples[component_mode][component] as Array[float]).append(
					float(component_result[component + "Microseconds"]))

	var modes: Dictionary = {}
	for mode: String in samples:
		modes[mode] = _summarize(samples[mode] as Array[float],
			packets.size(), command_count)
		if component_samples.has(mode):
			var component_report: Dictionary = {}
			for component: String in component_samples[mode]:
				component_report[component] = _duration_summary(
					component_samples[mode][component] as Array[float])
			modes[mode]["components"] = component_report
	return modes

func _run() -> void:
	var expected_user_root := OS.get_environment(
		"ELORIA_CROWD_EXPECT_USER_ROOT").replace("\\", "/")
	while expected_user_root.ends_with("/"):
		expected_user_root = expected_user_root.left(-1)
	var actual_user_dir := OS.get_user_data_dir().replace("\\", "/")
	if not expected_user_root.is_empty() \
			and actual_user_dir != expected_user_root \
			and not actual_user_dir.begins_with(expected_user_root + "/"):
		push_error("native benchmark user data escaped its isolated root: "
			+ actual_user_dir)
		quit(1)
		return
	if not ClassDB.class_exists(&"NativeCrowdReducer"):
		push_error("NativeCrowdReducer is unavailable; build the opt-in extension first")
		quit(1)
		return
	OS.low_processor_usage_mode_sleep_usec = 1
	var app_state: Node = root.get_node("AppState")
	_expect(bool(app_state.call("native_crowd_reducer_active")),
		"ELORIA_NATIVE_CROWD activates the integrated AppState path")
	var reducer: Object = ClassDB.instantiate(&"NativeCrowdReducer")
	var store: Object = ClassDB.instantiate(&"NativeCrowdStore")
	var report: Dictionary = {
		"scope": "protocol decode plus reducer and Dictionary output; no actor presentation",
		"nativeCompactDeferredEquivalent": false,
		"environment": {
			"expectedUserRoot": expected_user_root,
			"userDataDir": actual_user_dir,
			"appData": OS.get_environment("APPDATA").replace("\\", "/"),
			"localAppData": OS.get_environment("LOCALAPPDATA").replace("\\", "/"),
			"temp": OS.get_environment("TEMP").replace("\\", "/"),
			"userProfile": OS.get_environment("USERPROFILE").replace("\\", "/"),
		},
		"scenarios": {},
	}
	var legacy_packets := _legacy_packets()
	report.scenarios["legacyActorPackets"] = {
		"actors": LEGACY_ACTOR_COUNT,
		"activeActorsPerPacket": LEGACY_COMMANDS_PER_PACKET,
		"packets": LEGACY_PACKET_COUNT,
		"commands": LEGACY_PACKET_COUNT * LEGACY_COMMANDS_PER_PACKET,
		"modes": _measure_scenario(reducer, store,
			_seed_actors(LEGACY_ACTOR_COUNT), legacy_packets,
			LEGACY_PACKET_COUNT * LEGACY_COMMANDS_PER_PACKET),
	}
	var crowd_packets := _packets()
	report.scenarios["crowd100Commands"] = {
		"actors": ACTOR_COUNT,
		"activeActorsPerPacket": ACTIVE_ACTORS,
		"packets": CROWD_PACKET_COUNT,
		"commands": CROWD_PACKET_COUNT * ACTIVE_ACTORS,
		"modes": _measure_scenario(reducer, store, _seed_actors(),
			crowd_packets, CROWD_PACKET_COUNT * ACTIVE_ACTORS),
	}

	var artifacts := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/native-crowd")
	DirAccess.make_dir_recursive_absolute(artifacts)
	var report_path := artifacts.path_join("native-crowd-reducer.json")
	var report_file := FileAccess.open(report_path, FileAccess.WRITE)
	_expect(report_file != null, "benchmark report is writable")
	if report_file != null:
		report_file.store_string(JSON.stringify(report, "  "))
		report_file.close()
	print("NATIVE_CROWD_REDUCER_REPORT ", JSON.stringify(report))
	print("Native crowd reducer benchmark: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
