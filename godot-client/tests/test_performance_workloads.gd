extends SceneTree
## Data/selection contracts; no Main, imports, GPU work or network connection.
const Workloads := preload("res://tests/integration/performance_workloads.gd")
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check(Benchmark.cells_for("phase4").size() == 12, "legacy phase4 membership is unchanged")
	_check(Benchmark.cells_for("quick").size() == 2, "legacy quick membership is unchanged")
	var phase_one := Benchmark.cells_for("phase1")
	_check(phase_one.size() == 7, "phase1 selects its seven required workloads")
	_check(Benchmark.cells_for("mixed-mounted-160").size() == 1, "mounted cell selects directly")
	_check(Benchmark.cells_for("authored-herd").size() == 1, "herd support remains independently selectable")
	_check(Workloads.resolution("1920x1080") == Vector2i(1920, 1080), "resolution is parsed")
	_check(Workloads.resolution("bad") == Vector2i(1280, 720), "malformed resolution has a safe default")
	var records := {}
	for index: int in range(160):
		records[14000 + index] = {"actor_id": 14000 + index, "name": "Synthetic rider %d" % index}
	var mounts := Workloads.mount_rows(records, 80, "four_gates")
	_check(mounts.size() == 80 and mounts.has(14000), "exactly80 mounts include the local actor")
	var counts := Workloads.mount_profile_counts(mounts)
	_check(counts == {"crystalback_tortoise": 14, "giant_rat": 14,
		"golden_plains_horse": 13, "jadefeather_raptor": 13, "moor_pony": 13, "rabbit": 13},
		"original six-profile cohort includes five native profiles and the Giant Rat fallback")
	for id: int in mounts:
		var row := mounts[id] as Dictionary
		_check(row.owner == records[id].name and row.map == records[id].map,
			"mount ownership/map matches the synthetic actor")
		_check(Workloads.MountProfiles.supports(str(row.mount_id)), "mount comes from the supported profile catalog")
	var route := Workloads.southern_route()
	var kinds := {}
	var ids := {}
	for leg: Dictionary in route:
		_check(not ids.has(leg.id), "route leg ids are unique")
		ids[leg.id] = true
		kinds[leg.kind] = true
		_check((leg.start as Array).size() == 2 and (leg.arrival as Array).size() == 2,
			"route coordinates are explicit public fixture coordinates")
	_check(route.size() == 6 and kinds.has("border") and kinds.has("interior")
		and kinds.has("interior_return") and kinds.has("teleport") and kinds.has("teleport_return"),
		"route covers consecutive borders, interior, teleport and return")
	_check(route[0].map == route[-1].destination, "route returns to its starting territory")
	print("PERFORMANCE_WORKLOAD_CHECKS failures=", failures)
	quit(1 if failures else 0)

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
