extends RefCounted
## Read-only, boundary-only benchmark diagnostics. Accepts pre-scheduling
## visuals explicitly; it never substitutes requested settings for actual
## pony state, changes a tier, or steps a visual to obtain a measurement.
const TIER_NAMES := {0: "full", 1: "half", 2: "paused", 3: "quarter"}
const QUALITY_NAMES := {0: "low", 1: "medium", 2: "high"}
const MAX_POSE_STEPS := 1000000000
const MAX_STEPPED_SECONDS := 315576000.0
const MAX_PENDING_SECONDS := 86400.0

static func begin(boundary: String) -> Dictionary:
	return {"schemaVersion": 1, "boundary": boundary,
		"counterWindow": "cumulative_since_each_visual_creation_at_boundary",
		"counterWindowDescription": "Lifetime counters, not sample-only or a delta. afterSpawn follows spawn/readiness; afterSample also follows priming, warmup and sampling. Retained visuals can include earlier cells. Route final census follows final readiness.",
		"timedFrameCallback": false, "visuals": 0,
		"scheduling": {"available": 0, "unavailable": 0, "unavailableReasons": {},
			"requestedTiers": _tier_counts(), "effectiveTiers": _tier_counts(),
			"parked": 0, "cloth": 0,
			"staggered": {"enabled": 0, "disabled": 0, "unavailable": 0},
			"poseSteps": _metric(), "steppedSeconds": _metric(), "pendingSeconds": _metric(),
			"acceptedBounds": {"poseSteps": [0, MAX_POSE_STEPS],
				"steppedSeconds": [0.0, MAX_STEPPED_SECONDS],
				"pendingSeconds": [0.0, MAX_PENDING_SECONDS]}},
		"rustPose": {"available": 0, "supported": 0, "eligible": 0, "registered": 0, "appliedVisuals": 0,
			"activeVisuals": 0, "appliedActiveVisuals": 0, "applications": 0, "comparisons": 0,
			"eligibleActiveVisuals": 0, "appliedEligibleActiveVisuals": 0,
			"failures": 0, "disabled": 0, "profiles": {}, "requestedModes": {},
			"maxPositionError": 0.0, "maxAngleError": 0.0, "maxScaleError": 0.0, "maxVisualError": 0.0,
			"freshness": {"available": 0, "currentSubmissionVisuals": 0, "activeEligibleCurrentVisuals": 0, "applicationAgeFrames": _metric()},
			"secondary": {"available": 0, "upperApplications": 0, "reinApplications": 0,
				"clothAvailable": 0, "clothCalls": 0, "clothFallbacks": 0,
				"reinAvailable": 0, "reinCalls": 0}},
		"ponyQuality": {"available": 0, "unavailable": 0, "unavailableReasons": {},
			"levels": {"low": 0, "medium": 0, "high": 0}, "local": 0, "remote": 0,
			"sources": {"publicGetters": 0, "legacyProperties": 0}}}

static func include_visual(summary: Dictionary, visual: Object) -> void:
	summary["visuals"] = int(summary["visuals"]) + 1
	var scheduling: Dictionary = summary["scheduling"]
	if not is_instance_valid(visual):
		_unavailable(scheduling, "invalid_visual")
	elif not visual.has_method("scheduling_stats"):
		_unavailable(scheduling, "scheduling_stats_method_missing")
	else:
		var raw: Variant = visual.call("scheduling_stats")
		var error := _stats_error(raw)
		if not error.is_empty():
			_unavailable(scheduling, error)
		else:
			var stats: Dictionary = raw
			scheduling["available"] = int(scheduling["available"]) + 1
			_increment(scheduling["requestedTiers"], TIER_NAMES[int(stats["requestedTier"])])
			_increment(scheduling["effectiveTiers"], TIER_NAMES[int(stats["tier"])])
			scheduling["parked"] = int(scheduling["parked"]) + int(stats["parked"])
			scheduling["cloth"] = int(scheduling["cloth"]) + int(stats["cloth"])
			var staggered := "unavailable"
			if stats.has("staggered"):
				staggered = "enabled" if bool(stats["staggered"]) else "disabled"
			_increment(scheduling["staggered"], staggered)
			for field: String in ["poseSteps", "steppedSeconds", "pendingSeconds"]:
				_add_metric(scheduling[field], stats[field])
	_include_pony_quality(summary["ponyQuality"], visual)
	_include_rust_pose(summary["rustPose"], visual)

static func _include_rust_pose(out: Dictionary, visual: Object) -> void:
	if not is_instance_valid(visual) or not _has_property(visual, "rust_pose") or not visual.has_method("scheduling_stats"):
		return
	var solver: Variant = visual.get("rust_pose")
	if not is_instance_valid(solver) or not solver.has_method("snapshot"):
		return
	var stats: Dictionary = solver.snapshot()
	out.available += 1
	out.supported += int(bool(stats.supported))
	out.eligible += int(not bool(stats.disabled))
	out.registered += int(bool(stats.registered))
	out.disabled += int(bool(stats.disabled))
	out.appliedVisuals += int(int(stats.applications) > 0)
	var scheduling: Dictionary = visual.scheduling_stats()
	var active := not bool(scheduling.parked) and int(scheduling.tier) != 2
	out.activeVisuals += int(active)
	out.appliedActiveVisuals += int(active and int(stats.applications) > 0)
	out.eligibleActiveVisuals += int(active and bool(stats.supported))
	out.appliedEligibleActiveVisuals += int(active and bool(stats.supported) and int(stats.applications) > 0)
	if stats.has("appliedCurrentSubmission") and stats.has("applicationAgeFrames"):
		var fresh: Dictionary = out.freshness
		fresh.available += 1
		fresh.currentSubmissionVisuals += int(bool(stats.appliedCurrentSubmission))
		fresh.activeEligibleCurrentVisuals += int(active and bool(stats.supported) and bool(stats.appliedCurrentSubmission))
		if int(stats.applicationAgeFrames) >= 0:
			_add_metric(fresh.applicationAgeFrames, int(stats.applicationAgeFrames))
	if stats.has("upperApplications") and stats.has("reinApplications"):
		var secondary: Dictionary = out.secondary
		secondary.available += 1
		secondary.upperApplications += int(stats.upperApplications)
		secondary.reinApplications += int(stats.reinApplications)
		var actor: Variant = visual.get("actor") if _has_property(visual, "actor") else null
		var cloth: Variant = actor.get("_cape_cloth") if is_instance_valid(actor) else null
		if is_instance_valid(cloth) and cloth.has_method("native_presentation_stats"):
			var cloth_stats: Dictionary = cloth.native_presentation_stats()
			if cloth_stats.has("mountedCalls"):
				secondary.clothAvailable += 1
				secondary.clothCalls += int(cloth_stats.mountedCalls)
				secondary.clothFallbacks += int(cloth_stats.mountedFallbackCalls)
		var reins: Variant = visual.get("reins") if _has_property(visual, "reins") else null
		if is_instance_valid(reins) and reins.has_method("native_presentation_stats"):
			var rein_stats: Dictionary = reins.native_presentation_stats()
			if bool(rein_stats.get("available", false)):
				secondary.reinAvailable += 1
				secondary.reinCalls += int(rein_stats.get("calls", 0))
	for field: String in ["applications", "comparisons", "failures"]:
		out[field] = int(out[field]) + int(stats[field])
	for field: String in ["maxPositionError", "maxAngleError", "maxScaleError", "maxVisualError"]:
		out[field] = maxf(float(out[field]), float(stats[field]))
	_increment(out.profiles, str(stats.profile))
	_increment(out.requestedModes, str(stats.requested))

static func _tier_counts() -> Dictionary:
	return {"full": 0, "half": 0, "paused": 0, "quarter": 0}

static func _metric() -> Dictionary:
	# Null aggregates mean no accepted measurement, rather than a measured zero.
	return {"count": 0, "sum": null, "minimum": null, "maximum": null}

static func _add_metric(out: Dictionary, value: Variant) -> void:
	out["sum"] = value if int(out["count"]) == 0 else out["sum"] + value
	out["minimum"] = value if int(out["count"]) == 0 else min(out["minimum"], value)
	out["maximum"] = value if int(out["count"]) == 0 else max(out["maximum"], value)
	out["count"] = int(out["count"]) + 1

static func _increment(out: Dictionary, key: String) -> void:
	out[key] = int(out.get(key, 0)) + 1

static func _unavailable(out: Dictionary, reason: String) -> void:
	out["unavailable"] = int(out["unavailable"]) + 1
	_increment(out["unavailableReasons"], reason)

static func _stats_error(raw: Variant) -> String:
	if not raw is Dictionary:
		return "scheduling_stats_not_dictionary"
	var stats: Dictionary = raw
	for field: String in ["requestedTier", "tier"]:
		if typeof(stats.get(field)) != TYPE_INT or not TIER_NAMES.has(stats[field]):
			return "invalid_" + field
	for field: String in ["parked", "cloth"]:
		if typeof(stats.get(field)) != TYPE_BOOL:
			return "invalid_" + field
	if stats.has("staggered") and typeof(stats["staggered"]) != TYPE_BOOL:
		return "invalid_staggered"
	var steps: Variant = stats.get("poseSteps")
	if typeof(steps) != TYPE_INT or int(steps) < 0 or int(steps) > MAX_POSE_STEPS:
		return "invalid_poseSteps"
	if not _bounded_seconds(stats.get("steppedSeconds"), MAX_STEPPED_SECONDS):
		return "invalid_steppedSeconds"
	if not _bounded_seconds(stats.get("pendingSeconds"), MAX_PENDING_SECONDS):
		return "invalid_pendingSeconds"
	return ""

static func _bounded_seconds(value: Variant, maximum: float) -> bool:
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT]:
		return false
	var seconds := float(value)
	return is_finite(seconds) and seconds >= 0.0 and seconds <= maximum

static func _has_property(value: Object, name: String) -> bool:
	for property: Dictionary in value.get_property_list():
		if str(property.get("name", "")) == name:
			return true
	return false

static func _include_pony_quality(out: Dictionary, visual: Object) -> void:
	if not is_instance_valid(visual) or not _has_property(visual, "pony"):
		_unavailable(out, "pony_property_missing")
		return
	var pony_value: Variant = visual.get("pony")
	if not pony_value is Object or not is_instance_valid(pony_value):
		_unavailable(out, "pony_missing_or_invalid")
		return
	var pony: Object = pony_value
	var level: Variant
	var local_role: Variant
	var source := ""
	if pony.has_method("render_quality") and pony.has_method("render_quality_is_local"):
		level = pony.call("render_quality")
		local_role = pony.call("render_quality_is_local")
		source = "publicGetters"
	elif _has_property(pony, "_render_quality") and _has_property(pony, "_render_quality_local_actor"):
		# P1 has these stored values, before public getters were introduced.
		level = pony.get("_render_quality")
		local_role = pony.get("_render_quality_local_actor")
		source = "legacyProperties"
	else:
		_unavailable(out, "pony_quality_accessors_missing")
		return
	if typeof(level) != TYPE_INT or not QUALITY_NAMES.has(level):
		_unavailable(out, "invalid_pony_quality")
		return
	if typeof(local_role) != TYPE_BOOL:
		_unavailable(out, "invalid_pony_local_role")
		return
	out["available"] = int(out["available"]) + 1
	_increment(out["levels"], QUALITY_NAMES[int(level)])
	_increment(out, "local" if bool(local_role) else "remote")
	_increment(out["sources"], source)
