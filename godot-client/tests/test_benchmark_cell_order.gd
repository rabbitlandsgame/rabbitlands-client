extends SceneTree
## Static workload planning only: never instantiate the benchmark SceneTree.
## Loading is deferred so its ordinary autoload dependencies already exist.
const BENCHMARK_PATH := "res://tests/integration/crowd_presentation_benchmark.gd"
const CROWD3 := ["s3-market-160", "combat-160", "mixed-mounted-160"]
const ROUTE2 := ["traversal-southern-cold", "traversal-southern-warm"]
const PHASE4 := ["s3-market-100", "s2-invasion-100", "s3-market-160", "s2-invasion-160",
	"s3-market-200", "s2-invasion-200", "s3-market-300", "s2-invasion-300",
	"combat-100", "combat-160", "aoi-160", "empty"]
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var benchmark: Script = load(BENCHMARK_PATH) as Script
	if benchmark == null:
		_check(false, "benchmark Script loads after autoload registration")
		quit(1)
		return
	var before_nodes := get_node_count()
	_assert_order(benchmark, "combat-heat-bolt-160," + ",".join(CROWD3) + "," + ",".join(ROUTE2),
		["combat-heat-bolt-160", "s3-market-160", "combat-160", "mixed-mounted-160",
			"traversal-southern-cold", "traversal-southern-warm"])
	_assert_order(benchmark, ",".join(CROWD3), CROWD3)
	_assert_order(benchmark, ",".join(ROUTE2), ROUTE2)
	_assert_order(benchmark, "traversal-southern-warm,empty,combat-heat-bolt-160,s3-market-100",
		["traversal-southern-warm", "empty", "combat-heat-bolt-160", "s3-market-100"])
	_assert_order(benchmark, "combat-heat-bolt-160", ["combat-heat-bolt-160"])
	_assert_order(benchmark, "mixed-mounted-160", ["mixed-mounted-160"])
	_assert_order(benchmark, "phase4", PHASE4)
	_assert_order(benchmark, "quick", ["s3-market-160", "s2-invasion-160"])
	_assert_order(benchmark, "phase1", ["s3-market-160", "s2-invasion-160", "mixed-mounted-160",
		"combat-160", "empty", "traversal-southern-cold", "traversal-southern-warm"])
	_assert_order(benchmark, "phase7", ["combat-heat-bolt-160"])
	_assert_order(benchmark, "all", PHASE4 + ["mixed-mounted-160", "authored-herd",
		"traversal-southern-cold", "traversal-southern-warm"])
	# Match the host parser: malformed CSV never silently drops a bad member.
	for invalid: String in ["", "unknown", "empty,unknown", "unknown,empty", "empty,empty",
		"s3-market-160,combat-160,s3-market-160", "empty,,combat-160", ",empty", "empty,",
		" empty", "empty, combat-160", "phase1,empty"]:
		var rejected: Array = benchmark.cells_for(invalid)
		_check(rejected.is_empty(), "reject entire malformed selector: " + invalid)
	var mutable: Array = benchmark.cells_for(",".join(CROWD3))
	mutable[0]["id"] = "caller-mutated"
	mutable.reverse()
	_assert_order(benchmark, ",".join(CROWD3), CROWD3)
	_assert_order(benchmark, "quick", ["s3-market-160", "s2-invasion-160"])
	_check(get_node_count() == before_nodes, "static planning creates no benchmark tree or scene nodes")
	print("BENCHMARK_CELL_ORDER_CHECKS checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

func _assert_order(benchmark: Script, selector: String, expected: Array) -> void:
	var cells: Array = benchmark.cells_for(selector)
	var actual: Array = []
	for cell: Dictionary in cells:
		actual.append(str(cell.get("id", "")))
	_check(actual == expected, "exact cell membership/order for " + selector + ": " + str(actual))

func _check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)
