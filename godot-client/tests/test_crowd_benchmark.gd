extends SceneTree
## Cheap contract checks for the crowd benchmark's curated matrix. This does
## not instantiate actor assets; the integration benchmark validates those.

const CrowdBenchmark = preload("res://tests/integration/crowd_benchmarks.gd")
const SkinCensusContract = preload("res://tests/fixtures/crowd_skin_census_contract.gd")
var _failures := 0


func _init() -> void:
	var skin_checks := SkinCensusContract.contract()
	_expect(bool(skin_checks.get("passed", false)),
		"equipment skin census separates identity and exact content: %s" % skin_checks)
	var primary: Array = CrowdBenchmark.profile_cells("primary")
	_expect(primary.size() == 1, "primary is one repeatable acceptance cell")
	var acceptance := primary[0] as Dictionary
	_expect(int(acceptance.get("count", 0)) == 300,
		"acceptance owns exactly 300 actors, including the local player")
	_expect(int(acceptance["count"]) / 2 == 150,
		"the half-frustum fixture targets exactly 150 visible actors")
	_expect(int(acceptance["count"]) / 3 == 100,
		"the one-third workload targets exactly 100 active actors")
	_expect(str(acceptance.get("population", "")) == "mixed"
		and str(acceptance.get("features", "")) == "full",
		"acceptance keeps creatures and fully equipped humanoids")

	var matrix: Array = CrowdBenchmark.profile_cells("matrix")
	_expect(matrix.size() == 16, "matrix is four counts by four activities")
	var counts: Dictionary = {}
	var activities: Dictionary = {}
	for raw: Variant in matrix:
		var cell := raw as Dictionary
		counts[int(cell["count"])] = true
		activities[str(cell["activity"])] = true
	_expect(counts.keys().size() == 4 and counts.has(100) and counts.has(200)
		and counts.has(300) and counts.has(500),
		"matrix covers 100, 200, 300 and 500 actors")
	_expect(activities.has("idle") and activities.has("third_active")
		and activities.has("all_move") and activities.has("all_combat"),
		"matrix covers idle, mixed-active, movement and combat")

	var features: Array = CrowdBenchmark.profile_cells("features")
	var feature_names: Dictionary = {}
	for raw: Variant in features:
		feature_names[str((raw as Dictionary)["features"])] = true
	_expect(feature_names.keys().size() == 7 and feature_names.has("full")
		and feature_names.has("bare") and feature_names.has("no_cape")
		and feature_names.has("no_effects") and feature_names.has("no_overhead")
		and feature_names.has("no_ground") and feature_names.has("no_animation"),
		"feature profile contains every declared ablation")

	var stress: Array = CrowdBenchmark.profile_cells("stress")
	_expect(stress.size() == 6, "stress covers six network and presentation shapes")
	var stress_names: Dictionary = {}
	for raw: Variant in stress:
		stress_names[str((raw as Dictionary)["network"])] = true
	_expect(stress_names.has("normal_burst") and stress_names.has("asynchronous")
		and stress_names.has("folded_turn_attack")
		and stress_names.has("protocol_health_buffs")
		and stress_names.has("protocol_unchanged_gear")
		and stress_names.has("protocol_changed_gear_lifecycle"),
		"stress includes commands, health/buffs and equipment lifecycle packets")
	_expect(CrowdBenchmark.expected_visible_count("lod_bands", 300) == 200,
		"the supplemental LOD fixture declares 200 camera-visible actors")
	_expect(CrowdBenchmark.expected_visible_count("range_bands", 300) == 150,
		"the existing range fixture retains its 150-visible contract")
	_expect(CrowdBenchmark.expected_visible_count("misspelled", 300) == -1,
		"an unknown visibility token is rejected instead of acting concentrated")
	print("crowd benchmark contract: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _expect(value: bool, label: String) -> void:
	if value:
		return
	_failures += 1
	push_error("FAIL: " + label)
