extends SceneTree
## Compile the actual harness after autoload initialization and check its plan.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)

func _run() -> void:
	var harness := load("res://tests/integration/crowd_presentation_benchmark.gd") as Script
	_expect(harness != null, "actual benchmark harness compiles")
	if harness == null:
		quit(1)
		return
	for count: int in [2, 16, 32]:
		var cells: Array = harness.call("cells_for", "route-soak-%d" % count)
		_expect(cells.size() == count, "exact planned iteration count")
		var seen: Dictionary = {}
		for index: int in cells.size():
			var cell: Dictionary = cells[index]
			var suffix := String.chr(97 + index / 26) + String.chr(97 + index % 26)
			_expect(cell.id == "traversal-southern-soak-" + suffix, "canonical ordered identity")
			_expect(not seen.has(cell.id), "unique iteration identity")
			seen[cell.id] = true
			_expect(cell.soakIndex == index and cell.soakIterations == count, "complete iteration witness")
			_expect(cell.visit == ("cold" if index == 0 else "warm"), "one application-first route")
			_expect(cell.activity == "route" and cell.shape == "traversal" and cell.count == 1,
				"real traversal workload")
	for selector: String in ["route-soak-1", "route-soak-33", "route-soak-no", "route-soak-"]:
		var cells: Array = harness.call("cells_for", selector)
		_expect(cells.is_empty(), "invalid iteration bounds are rejected")
	var route := load("res://tests/integration/benchmark_route_content.gd") as Script
	var before: Dictionary = route.call("clock")
	await process_frame
	var after: Dictionary = route.call("clock")
	_expect(before.ticksUsec is int and after.ticksUsec > before.ticksUsec, "real monotonic clock")
	_expect(is_finite(float(before.unixTime)) and after.unixTime >= before.unixTime,
		"wall clock for memory alignment")
	print("benchmark soak selector: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
