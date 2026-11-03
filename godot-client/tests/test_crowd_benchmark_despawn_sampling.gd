extends SceneTree
## Wave 2 MEM-M7b (perf audit GAP-06): the crowd benchmark samples
## `afterDespawn` after the park time, and waits for RL head prewarm work in
## flight before every cell, but not for publication the live gate holds back
## (which never starts while the game view is shown). Runs the harness's static
## helpers against the real CrowdPresentation constants and a real RL head
## worker parse; headless, no Main.
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
const CrowdPolicy := preload("res://src/world/crowd_presentation.gd")
const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const PARSE_LIMIT_MSEC := 30000
var failures := 0
var checks := 0


## Stands in for Main's live gate (main.gd _rl_head_render_warm_allowed) while
## the game view is shown: closed.
class ClosedGate:
	extends RefCounted
	func closed() -> bool:
		return false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_despawn_timing()
	_check_settled_rule()
	_check_memory_class_record()
	await _check_live_state()
	print("CROWD_BENCHMARK_DESPAWN_SAMPLING checks=%d failures=%d" % [checks, failures])
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)


func _check_despawn_timing() -> void:
	var wait := Benchmark.despawn_sample_msec()
	_check(wait == CrowdPolicy.PARK_MSEC + Benchmark.DESPAWN_SAMPLE_MARGIN_MSEC,
		"afterDespawn is sampled the margin past the park time (%d ms)" % wait)
	# A body parked at the removal is due at PARK_MSEC and freed by the gate's
	# next look, at most PARK_EXPIRY_PERIOD_MSEC later (MEM-M7a).
	_check(wait > CrowdPolicy.PARK_MSEC + CrowdPolicy.PARK_EXPIRY_PERIOD_MSEC,
		"the sample comes after the park time plus one gate expiry period")
	_check(Benchmark.DESPAWN_SETTLE_FRAMES == 12, "afterRemoval keeps the earlier 12-frame sample point")
	_check(Benchmark.RL_HEAD_WARM_WAIT_MSEC >= 10000, "the RL head wait is bounded but not short")


func _check_settled_rule() -> void:
	var idle := {"warming": false, "parsing": 0, "queued": 0, "surveying": false, "pipelineActive": false,
		"allowed": true}
	_check(Benchmark.rl_head_warm_settled(idle), "nothing warming: a cell may start")
	for key: String in ["parsing", "queued"]:
		var busy := idle.duplicate()
		busy["warming"] = true
		busy[key] = 1
		_check(not Benchmark.rl_head_warm_settled(busy), "a %s RL file holds the cell" % key)
		busy["allowed"] = false
		_check(not Benchmark.rl_head_warm_settled(busy), "a %s RL file holds the cell behind a closed gate too" % key)
	for key: String in ["surveying", "pipelineActive"]:
		var busy := idle.duplicate()
		busy["warming"] = true
		busy[key] = true
		busy["allowed"] = false
		_check(not Benchmark.rl_head_warm_settled(busy), "%s holds the cell" % key)
	var gated := idle.duplicate()
	gated["warming"] = true
	gated["allowed"] = false
	_check(Benchmark.rl_head_warm_settled(gated),
		"only publication behind a closed gate (maps, pipelines): the cell starts")
	gated["allowed"] = true
	_check(not Benchmark.rl_head_warm_settled(gated), "the same work with the gate open is waited for")
	_check(not Benchmark.rl_head_warm_settled({"warming": true}), "an incomplete state is never settled")


## The report's `memoryClass`: the class the park limit and budgets follow, and
## where it came from, so a run that inherited RABBITLANDS_MEMORY_CLASS says so.
func _check_memory_class_record() -> void:
	var probed := Benchmark.memory_class_record()
	_check(str(probed.get("class", "")) in MemoryBudgets.CLASSES and probed.has("source"),
		"the report records the session's memory class and its source: %s" % JSON.stringify(probed))
	_check(MemoryBudgets.override_for_tests(MemoryBudgets.SMALL), "a forced class for the record check")
	var forced := Benchmark.memory_class_record()
	_check(str(forced.get("class")) == MemoryBudgets.SMALL and str(forced.get("source")) == "test",
		"a forced class is recorded with its source: %s" % JSON.stringify(forced))
	forced["class"] = "changed"
	_check(MemoryBudgets.memory_class() == MemoryBudgets.SMALL, "the record is a copy")
	_check(CrowdPolicy.park_limit_for(str(Benchmark.memory_class_record().get("class"))) == 16,
		"the recorded class names the park limit (16 on small)")
	MemoryBudgets.reset()


func _check_live_state() -> void:
	var state := Benchmark.rl_head_warm_state()
	for key: String in ["warming", "parsing", "queued", "surveying", "pipelineActive", "pipelinePending",
			"texturesPending", "allowed", "settled"]:
		_check(state.has(key), "the warm state reports " + key)
	_check(not bool(state.warming) and bool(state.settled), "an idle library is settled")
	var path := RLHeadLibrary.head_path("male")
	if not _check(RLHeadLibrary.glb_exists(path), "the RL head GLB is on disk"):
		return
	var gate := ClosedGate.new()
	RLHeadLibrary.set_render_warm_context(gate, &"closed")
	RLHeadLibrary.prewarm(PackedStringArray([path]))
	state = Benchmark.rl_head_warm_state()
	_check(bool(state.warming) and int(state.parsing) + int(state.queued) > 0 and not bool(state.settled),
		"a worker parse in flight holds the cell: %s" % JSON.stringify(state))
	_check(not bool(state.allowed), "the stand-in gate is closed")
	var started := Time.get_ticks_msec()
	while not bool(state.settled) and Time.get_ticks_msec() - started < PARSE_LIMIT_MSEC:
		await process_frame
		state = Benchmark.rl_head_warm_state()
	_check(bool(state.settled) and int(state.parsing) == 0 and int(state.queued) == 0,
		"the parse lands and the cell may start: %s" % JSON.stringify(state))
	if int(state.texturesPending) > 0:
		_check(bool(state.warming), "the head maps wait behind the closed gate (warming stays true)")
	# Main's close path: the context goes, queued maps are dropped.
	RLHeadLibrary.clear_render_warm_context(gate)
	started = Time.get_ticks_msec()
	while RLHeadLibrary.warming() and Time.get_ticks_msec() - started < PARSE_LIMIT_MSEC:
		await process_frame
	_check(not RLHeadLibrary.warming(), "nothing is left warming after the context closes")


func _check(ok: bool, label: String) -> bool:
	checks += 1
	if ok:
		print("PASS: " + label)
	else:
		failures += 1
		push_error("FAIL: " + label)
	return ok
