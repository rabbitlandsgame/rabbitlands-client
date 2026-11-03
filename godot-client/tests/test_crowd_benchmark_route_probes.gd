extends SceneTree
## The crowd benchmark's route and long-frame probes (wave 2 AW-00), without
## Main, maps or assets: a traversal leg's player-visible times come from Main's
## arrival reports by their clock (the recorder keeps only its newest reports,
## so a list index taken before the transition can skip a new one), and a
## long-frame record reads the exterior stream without reaping finished orphan
## imports (ExteriorRegionStream.is_idle does that work).
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_leg_visible_times()
	_check_exterior_snapshot_is_read_only()
	print("CROWD_BENCHMARK_ROUTE_PROBES failures=", failures)
	quit(1 if failures else 0)


func _check_leg_visible_times() -> void:
	var probe := {"curtainShownUsec": 1_200_000, "curtainHiddenUsec": 2_000_000, "frames": 9}
	# Reports before the transition start (1 s) belong to earlier legs.
	var reports: Array = [{"ticksUsec": 400_000}, {"ticksUsec": 1_500_000}, {"ticksUsec": 2_600_000}]
	var times := Benchmark.leg_visible_times(reports, 1_000_000, probe)
	_check(is_equal_approx(float(times.visibleMs), 500.0) and int(times.arrivalReports) == 2
		and str(times.visibleBasis) == "arrival_reported", "visible time runs to the first report after the start: %s" % times)
	var curtain: Dictionary = times.curtain
	_check(bool(curtain.shown) and is_equal_approx(float(curtain.shownMs), 200.0)
		and is_equal_approx(float(curtain.hiddenMs), 1000.0) and int(curtain.probeFrames) == 9,
		"curtain times are relative to the transition start: %s" % curtain)
	# A full recorder dropped its oldest entry when the new report arrived: the
	# list kept its length, so the leg's report sits below the pre-transition size.
	var rotated: Array = []
	for index: int in 255:
		rotated.append({"ticksUsec": 100 + index})
	rotated.append({"ticksUsec": 1_300_000})
	times = Benchmark.leg_visible_times(rotated, 1_000_000, {})
	_check(times.visibleMs != null and is_equal_approx(float(times.visibleMs), 300.0) and int(times.arrivalReports) == 1,
		"a report recorded after the recorder was full still counts: %s" % times)
	var none := Benchmark.leg_visible_times([{"ticksUsec": 10}], 1_000_000, {})
	_check(none.visibleMs == null and int(none.arrivalReports) == 0 and not bool((none.curtain as Dictionary).shown)
		and (none.curtain as Dictionary).shownMs == null and (none.curtain as Dictionary).hiddenMs == null,
		"no report and no curtain: a kept traveller has no visible time: %s" % none)


func _check_exterior_snapshot_is_read_only() -> void:
	_check(Benchmark.exterior_snapshot(null).is_empty(), "no exterior stream, no fields")
	# A finished orphan import, as a re-primed or departed chunk stream leaves one.
	var thread := Thread.new()
	thread.start(func() -> Variant: return null)
	var deadline := Time.get_ticks_msec() + 10000
	while thread.is_alive() and Time.get_ticks_msec() < deadline:
		OS.delay_msec(1)
	var before := ContinentChunkStream.orphans_pending()
	ContinentChunkStream._orphan(thread, {})
	var exterior := ExteriorRegionStream.new()
	exterior.residents["whitehorn_range"] = {}
	var snapshot := Benchmark.exterior_snapshot(exterior)
	_check(ContinentChunkStream.orphans_pending() == before + 1,
		"the long-frame snapshot leaves finished orphan imports to the client")
	_check(snapshot == {"exteriorPreloadPending": false, "exteriorRetiring": 0, "exteriorResidents": ["whitehorn_range"]},
		"the snapshot reports preload, retirement and residents: %s" % snapshot)
	ContinentChunkStream.reap_orphans()
	_check(ContinentChunkStream.orphans_pending() == before, "the probe's orphan is reaped by the client's own path")
	exterior.free()


func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
