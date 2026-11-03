extends SceneTree
## The crowd benchmark's teardown waits for an RL head prewarm parse before it
## quits (wave 2 AW-00). A process that quits while that worker parses can hang
## (rl_head_library.gd prewarm; the 4-core proxy's 540 s exit hang, hypothesis
## H1 in the traversal gap audit). This starts a real worker parse, cancels the
## queued work the way the harness teardown does, waits (bounded) until the
## harness reports nothing pending, and quits. A hang shows as this process not
## exiting, so run it under a timeout (the AW-00 probe ran it 20 times).
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
const DRAIN_LIMIT_MSEC := 30000
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var path := RLHeadLibrary.head_path("male")
	_check(RLHeadLibrary.glb_exists(path), "the RL head GLB is on disk")
	_check(not Benchmark.rl_head_warm_pending(), "nothing is warming before the probe")
	RLHeadLibrary.prewarm(PackedStringArray([path, RLHeadLibrary.head_path("female")]))
	_check(Benchmark.rl_head_warm_pending(), "a worker parse is pending")
	var cancelled := Benchmark.cancel_rl_head_warm()
	_check(bool(cancelled.get("warming", false)) and cancelled.has("snapshot"),
		"cancel reports the work that was in flight")
	_check(RLHeadLibrary._warm_queue.is_empty() and RLHeadLibrary._texture_queue.is_empty(),
		"cancel drops the queued parse and maps")
	var started := Time.get_ticks_msec()
	var frames := 0
	while Benchmark.rl_head_warm_pending() and Time.get_ticks_msec() - started < DRAIN_LIMIT_MSEC:
		await process_frame
		frames += 1
	_check(not Benchmark.rl_head_warm_pending(), "the running parse finishes and nothing is pending")
	print("CROWD_BENCHMARK_TEARDOWN_DRAIN frames=%d ms=%d pendingAfterCancel=%s failures=%d" % [frames,
		Time.get_ticks_msec() - started, str(cancelled.get("pendingAfterCancel")), failures])
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)


func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
