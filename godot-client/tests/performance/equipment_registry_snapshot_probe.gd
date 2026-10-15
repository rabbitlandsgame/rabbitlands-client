extends SceneTree
## Focused allocation/timing probe for explicit equipment registry snapshots.
## Timing is diagnostic and never asserted; it does not measure frame rate.

const Cache = preload("res://src/actors/equipment_registry_snapshot_cache.gd")
const ITERATIONS := 300
const TRIALS := 8

var _failures := 0
var _registry: Dictionary


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	_expect(parsed is Dictionary, "equipment registry parses")
	if parsed is not Dictionary:
		quit(_failures)
		return
	_registry = parsed as Dictionary
	_run_deep_copies(2)
	Cache.clear()
	var warm_snapshot := Cache.prepare(_registry)
	_run_acquires(warm_snapshot, 2)

	var trials: Array[Dictionary] = []
	for trial: int in range(TRIALS):
		var order := ["deep_copy", "prepared_acquire"] if trial % 2 == 0 \
			else ["prepared_acquire", "deep_copy"]
		var row := {"trial": trial + 1, "order": order.duplicate(), "results": {}}
		for implementation: String in order:
			Cache.clear()
			var prepared: Dictionary = {}
			var prepare_microseconds: Variant = null
			if implementation == "prepared_acquire":
				var prepare_started := Time.get_ticks_usec()
				prepared = Cache.prepare(_registry)
				prepare_microseconds = Time.get_ticks_usec() - prepare_started
			var before := _memory_snapshot()
			var started := Time.get_ticks_usec()
			var held: Array = (_run_deep_copies(ITERATIONS)
				if implementation == "deep_copy" else _run_acquires(prepared, ITERATIONS))
			var elapsed := Time.get_ticks_usec() - started
			var after := _memory_snapshot()
			(row.results as Dictionary)[implementation] = {
				"microseconds": elapsed,
				"oneTimePrepareMicroseconds": prepare_microseconds,
				"iterations": ITERATIONS,
				"retainedReferences": held.size(),
				"staticBytesBefore": before["staticBytes"],
				"staticBytesAfter": after["staticBytes"],
				"staticBytesDelta": _nullable_delta(before["staticBytes"], after["staticBytes"]),
				"objectCountBefore": before["objectCount"],
				"objectCountAfter": after["objectCount"],
				"objectCountDelta": _nullable_delta(before["objectCount"], after["objectCount"]),
				"cacheStats": Cache.stats() if implementation == "prepared_acquire" else null,
			}
			_expect(held.size() == ITERATIONS, implementation + " retains every requested value")
			if implementation == "prepared_acquire":
				_expect(_all_same(held), "prepared acquire reuses one frozen snapshot")
				_expect(int(Cache.stats()["hits"]) == ITERATIONS,
					"prepared acquire records every timed lookup")
			held.clear()
		trials.append(row)
		await process_frame

	var report := {
		"schemaVersion": 2,
		"failures": _failures,
		"timingAssertions": false,
		"timingScope": ("CPU identity acquisition of an explicitly prepared immutable catalogue; "
			+ "one-time recursive preparation is reported separately; excludes actor/model/equipment "
			+ "construction and frame rate"),
		"memoryScope": ("Godot static/object monitor deltas while 300 returned Dictionaries remain "
			+ "referenced; counters are diagnostic and are not process RSS"),
		"registry": {
			"fileBytes": FileAccess.get_file_as_bytes(
				"res://data/actors/equipment.json").size(),
			"sha256": FileAccess.get_sha256("res://data/actors/equipment.json"),
			"models": (_registry.get("models", {}) as Dictionary).size(),
		},
		"workload": {"iterations": ITERATIONS, "trials": TRIALS,
			"rotatedOrder": true, "cacheCapacity": Cache.CAPACITY},
		"summary": _summary(trials),
		"trials": trials,
	}
	var output := OS.get_environment("ELORIA_EQUIPMENT_REGISTRY_REPORT")
	if output.is_empty():
		output = OS.get_environment("ELORIA_ARTIFACT_DIR").path_join(
			"equipment-registry-snapshot-probe.json")
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		_fail("report opens: " + output)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("equipment registry snapshot probe: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures,
		" report=", output)
	quit(_failures)


func _run_deep_copies(iterations: int) -> Array:
	var held: Array = []
	held.resize(iterations)
	for index: int in range(iterations):
		held[index] = _registry.duplicate(true)
	return held


func _run_acquires(prepared: Dictionary, iterations: int) -> Array:
	var held: Array = []
	held.resize(iterations)
	for index: int in range(iterations):
		held[index] = Cache.acquire(prepared)
	return held


func _all_same(values: Array) -> bool:
	for index: int in range(1, values.size()):
		if not is_same(values[0], values[index]):
			return false
	return true


func _memory_snapshot() -> Dictionary:
	return {
		"staticBytes": Performance.get_monitor(Performance.MEMORY_STATIC),
		"objectCount": Performance.get_monitor(Performance.OBJECT_COUNT),
	}


func _nullable_delta(before: Variant, after: Variant) -> Variant:
	if before == null or after == null:
		return null
	return int(after) - int(before)


func _summary(trials: Array[Dictionary]) -> Dictionary:
	var result := {}
	for implementation: String in ["deep_copy", "prepared_acquire"]:
		var timings: Array[float] = []
		var memory: Array[float] = []
		var preparation: Array[float] = []
		for row: Dictionary in trials:
			var measured := (row.results as Dictionary)[implementation] as Dictionary
			timings.append(float(measured["microseconds"]))
			if measured["staticBytesDelta"] != null:
				memory.append(float(measured["staticBytesDelta"]))
			if measured["oneTimePrepareMicroseconds"] != null:
				preparation.append(float(measured["oneTimePrepareMicroseconds"]))
		result[implementation] = {
			"medianMicroseconds": _median(timings),
			"medianOneTimePrepareMicroseconds": (
				_median(preparation) if not preparation.is_empty() else null),
			"medianStaticBytesDelta": _median(memory) if not memory.is_empty() else null,
		}
	var baseline := float(result["deep_copy"]["medianMicroseconds"])
	var candidate := float(result["prepared_acquire"]["medianMicroseconds"])
	result["acquireVsDeepCopyTimePercent"] = (
		100.0 * (candidate - baseline) / baseline if baseline > 0.0 else null)
	return result


func _median(values: Array[float]) -> float:
	if values.is_empty():
		return 0.0
	values.sort()
	var middle := values.size() / 2
	return values[middle] if values.size() % 2 == 1 \
		else (values[middle - 1] + values[middle]) * 0.5


func _expect(value: bool, label: String) -> void:
	if not value:
		_fail(label)


func _fail(label: String) -> void:
	_failures += 1
	push_error("FAIL: " + label)
