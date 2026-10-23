extends SceneTree
## Synthetic scalar contracts only: no Main, assets, imports or rendered work.
const Census := preload("res://tests/integration/benchmark_mounted_census.gd")
var failures := 0

class PublicPony:
	extends RefCounted
	var level: Variant = 2
	var local_role: Variant = false
	# Decoy legacy values prove actual public accessors take precedence.
	var _render_quality := 0
	var _render_quality_local_actor := true
	func render_quality() -> Variant:
		return level
	func render_quality_is_local() -> Variant:
		return local_role

class LegacyPony:
	extends RefCounted
	var _render_quality := 1
	var _render_quality_local_actor := true

class ScheduledVisual:
	extends RefCounted
	var pony: Variant
	var stats: Variant = {}
	func scheduling_stats() -> Variant:
		return stats

class LegacyVisual:
	extends RefCounted
	var pony: Variant

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_test_aggregate_and_boundaries()
	_test_missing_and_legacy_quality()
	_test_invalid_and_bounded_values()
	_test_quality_failures()
	print("BENCHMARK_MOUNTED_CENSUS_CHECKS failures=", failures)
	quit(1 if failures else 0)

func _stats() -> Dictionary:
	return {"requestedTier": 2, "tier": 1, "parked": false, "cloth": true,
		"staggered": true, "poseSteps": 5, "steppedSeconds": 0.75, "pendingSeconds": 0.02}

func _test_aggregate_and_boundaries() -> void:
	var visual := ScheduledVisual.new()
	visual.pony = PublicPony.new()
	visual.stats = _stats()
	var original: Dictionary = visual.stats.duplicate(true)
	var before := Census.begin("afterSpawn")
	Census.include_visual(before, visual)
	var second := ScheduledVisual.new()
	second.pony = PublicPony.new()
	second.pony.level = 0
	second.pony.local_role = true
	second.stats = {"requestedTier": 3, "tier": 2, "parked": true, "cloth": false,
		"staggered": false, "poseSteps": 0, "steppedSeconds": 0.0, "pendingSeconds": 0.0}
	Census.include_visual(before, second)
	var scheduling: Dictionary = before.scheduling
	_check(before.visuals == 2 and scheduling.available == 2 and scheduling.unavailable == 0,
		"accepted visuals retain exact population accounting")
	_check(scheduling.requestedTiers.paused == 1 and scheduling.requestedTiers.quarter == 1
		and scheduling.effectiveTiers.half == 1 and scheduling.effectiveTiers.paused == 1,
		"requested and actual tiers are separate even for one-shot overrides")
	_check(scheduling.parked == 1 and scheduling.cloth == 1
		and scheduling.staggered.enabled == 1 and scheduling.staggered.disabled == 1,
		"park, cloth and stagger state are independent scalar counts")
	_check(scheduling.poseSteps == {"count": 2, "sum": 5, "minimum": 0, "maximum": 5}
		and is_equal_approx(float(scheduling.steppedSeconds.sum), 0.75)
		and is_equal_approx(float(scheduling.pendingSeconds.maximum), 0.02),
		"lifetime pose counts and clock sums retain measured zero and finite range")
	_check(before.ponyQuality.levels.high == 1 and before.ponyQuality.levels.low == 1
		and before.ponyQuality.local == 1 and before.ponyQuality.remote == 1
		and before.ponyQuality.sources.publicGetters == 2,
		"actual pony public getters win over decoy private values")
	_check(visual.stats == original, "capture never mutates the visual stats dictionary")
	visual.stats.poseSteps = 10
	var after := Census.begin("afterSample")
	Census.include_visual(after, visual)
	_check(before.boundary == "afterSpawn" and after.boundary == "afterSample"
		and before.scheduling.poseSteps.sum == 5 and after.scheduling.poseSteps.sum == 10,
		"boundaries are independent cumulative observations, not deltas")
	_check(after.counterWindow == "cumulative_since_each_visual_creation_at_boundary"
		and "warmup" in str(after.counterWindowDescription) and not after.timedFrameCallback,
		"metadata explicitly includes warmup and excludes sample-only interpretation")
	var decoded: Variant = JSON.parse_string(JSON.stringify(after))
	_check(decoded is Dictionary and int(decoded.scheduling.poseSteps.sum) == 10,
		"summary contains detached JSON-compatible scalars")

func _test_missing_and_legacy_quality() -> void:
	var visual := LegacyVisual.new()
	visual.pony = LegacyPony.new()
	var summary := Census.begin("afterSpawn")
	Census.include_visual(summary, visual)
	_check(summary.scheduling.available == 0 and summary.scheduling.unavailable == 1
		and summary.scheduling.unavailableReasons.scheduling_stats_method_missing == 1
		and summary.scheduling.poseSteps.sum == null,
		"P1 without scheduling_stats remains explicitly unavailable, never measured zero")
	_check(summary.ponyQuality.available == 1 and summary.ponyQuality.levels.medium == 1
		and summary.ponyQuality.local == 1 and summary.ponyQuality.sources.legacyProperties == 1,
		"P1 reads actual pony private quality and local role without rider substitution")
	var unstaggered := ScheduledVisual.new()
	unstaggered.pony = visual.pony
	unstaggered.stats = _stats()
	unstaggered.stats.erase("staggered")
	Census.include_visual(summary, unstaggered)
	_check(summary.scheduling.available == 1 and summary.scheduling.staggered.unavailable == 1,
		"optional missing stagger state does not invent an enabled flag")
	Census.include_visual(summary, null)
	_check(summary.visuals == 3 and summary.scheduling.unavailable == 2
		and summary.ponyQuality.unavailable == 1, "missing visuals are counted with explicit failures")

func _test_invalid_and_bounded_values() -> void:
	var invalid: Array[Dictionary] = [
		{"field": "requestedTier", "value": 99}, {"field": "tier", "value": "half"},
		{"field": "parked", "value": 1}, {"field": "cloth", "value": null},
		{"field": "staggered", "value": 1},
		{"field": "poseSteps", "value": -1}, {"field": "poseSteps", "value": 1.5},
		{"field": "poseSteps", "value": Census.MAX_POSE_STEPS + 1},
		{"field": "steppedSeconds", "value": NAN}, {"field": "steppedSeconds", "value": INF},
		{"field": "steppedSeconds", "value": true},
		{"field": "steppedSeconds", "value": Census.MAX_STEPPED_SECONDS + 1.0},
		{"field": "pendingSeconds", "value": -0.01},
		{"field": "pendingSeconds", "value": Census.MAX_PENDING_SECONDS + 1.0}]
	for change: Dictionary in invalid:
		var visual := ScheduledVisual.new()
		visual.pony = PublicPony.new()
		visual.stats = _stats()
		visual.stats[change.field] = change.value
		var summary := Census.begin("afterSample")
		Census.include_visual(summary, visual)
		_check(summary.scheduling.available == 0 and summary.scheduling.unavailable == 1
			and summary.scheduling.poseSteps.sum == null and summary.ponyQuality.available == 1,
			"invalid %s fails closed without invalid aggregates or losing independent quality" % str(change.field))
	var malformed := ScheduledVisual.new()
	malformed.stats = []
	var unavailable := Census.begin("afterSample")
	Census.include_visual(unavailable, malformed)
	_check(unavailable.scheduling.unavailableReasons.scheduling_stats_not_dictionary == 1,
		"a malformed stats API result is explicitly unavailable")
	var boundary := ScheduledVisual.new()
	boundary.pony = PublicPony.new()
	boundary.stats = _stats()
	boundary.stats.poseSteps = Census.MAX_POSE_STEPS
	boundary.stats.steppedSeconds = Census.MAX_STEPPED_SECONDS
	boundary.stats.pendingSeconds = Census.MAX_PENDING_SECONDS
	var accepted := Census.begin("afterSample")
	Census.include_visual(accepted, boundary)
	_check(accepted.scheduling.available == 1
		and accepted.scheduling.pendingSeconds.sum == Census.MAX_PENDING_SECONDS,
		"documented finite upper bounds are inclusive")

func _test_quality_failures() -> void:
	for change: Dictionary in [{"field": "level", "value": 3},
			{"field": "level", "value": "low"}, {"field": "local_role", "value": 1}]:
		var visual := ScheduledVisual.new()
		visual.stats = _stats()
		visual.pony = PublicPony.new()
		visual.pony.set(str(change.field), change.value)
		var summary := Census.begin("afterSpawn")
		Census.include_visual(summary, visual)
		_check(summary.ponyQuality.available == 0 and summary.ponyQuality.unavailable == 1
			and summary.scheduling.available == 1, "invalid pony state remains separate from scheduling")
	var missing := LegacyVisual.new()
	missing.pony = RefCounted.new()
	var summary := Census.begin("afterSpawn")
	Census.include_visual(summary, missing)
	_check(summary.ponyQuality.unavailableReasons.pony_quality_accessors_missing == 1,
		"missing pony quality access never falls back to requested settings")

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
