extends SceneTree
## The crowd benchmark's generic per-actor census hook (wave 2 AW-00), without
## Main, maps or assets: actor `presentation_census()` sums per scope and a
## directory contributor, as later chunks (LAT-L6 hand/cue counts, ALOD-C8
## triangle census) add census fields without editing the harness.
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
const FIXTURES := "res://tests/fixtures/benchmark_census/"
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var scripts := Benchmark.census_contributor_scripts(FIXTURES)
	_check(Benchmark.census_contributor_names(scripts) == ["sample_counter"],
		"contributors load from their directory by file stem")
	_check(Benchmark.census_contributor_scripts("res://tests/fixtures/benchmark_census_absent/").is_empty(),
		"an absent contributor directory (a benchmark export) has none")
	_check(Benchmark.census_contributor_directory() == "res://tests/integration/census/",
		"the harness reads contributors from tests/integration/census")
	var reporting := GDScript.new()
	reporting.source_code = ("extends Node3D\nvar fields := {}\n"
		+ "func presentation_census() -> Dictionary:\n\treturn fields\n")
	reporting.reload()
	var near := Node3D.new()
	near.set_script(reporting)
	near.set("fields", {"handDetailFull": true, "cuesAllowed": 1, "weight": 0.5, "label": "text"})
	var off_screen := Node3D.new()
	off_screen.set_script(reporting)
	off_screen.set("fields", {"handDetailFull": false, "cuesAllowed": 2})
	var hidden := Node3D.new()
	hidden.set_script(reporting)
	hidden.set("fields", {"handDetailFull": true, "cuesAllowed": 4})
	var deferred := Node3D.new() # No presentation_census: counted by contributors only.
	var state := Benchmark.census_begin(scripts, "afterSpawn", {"boundary": "afterSpawn", "localId": 14000})
	Benchmark.census_include(state, near, {"id": 14000, "local": true, "built": true, "hidden": false,
		"inFrustum": true})
	Benchmark.census_include(state, off_screen, {"id": 14001, "built": true, "hidden": false, "inFrustum": false})
	Benchmark.census_include(state, hidden, {"id": 14002, "built": true, "hidden": true, "inFrustum": true})
	Benchmark.census_include(state, deferred, {"id": 14003, "built": false, "deferred": true})
	var out := Benchmark.census_finish(state)
	var fields: Dictionary = out.get("actorFields", {})
	_check(fields.get("all") == {"handDetailFull": 2, "cuesAllowed": 7, "weight": 0.5},
		"numeric and bool fields are summed over every reporting actor: %s" % fields.get("all"))
	_check(fields.get("builtBodies") == {"handDetailFull": 2, "cuesAllowed": 7, "weight": 0.5},
		"built bodies scope: %s" % fields.get("builtBodies"))
	_check(fields.get("inFrustumBuiltBodies") == {"handDetailFull": 1, "cuesAllowed": 1, "weight": 0.5},
		"in-frustum scope excludes off-screen and crowd-hidden bodies: %s" % fields.get("inFrustumBuiltBodies"))
	_check(int(fields.get("actorsReporting", -1)) == 3 and fields.get("ignoredFields") == ["label"],
		"reporting actors are counted and non-numeric fields named, not summed")
	_check(out.get("contributors") == {"sample_counter": {"actors": 4, "built": 3, "inFrustum": 2, "local": 1,
		"contextLocalId": 14000, "boundary": "afterSpawn"}},
		"a contributor sees every actor with its facts and the context: %s" % out.get("contributors"))
	var skipped := Benchmark.census_finish(Benchmark.census_begin(scripts, "skip", {}))
	_check(skipped.get("contributors") == {} and (skipped.actorFields as Dictionary).get("all") == {}
		and int((skipped.actorFields as Dictionary).get("actorsReporting", -1)) == 0
		and not (skipped.actorFields as Dictionary).has("ignoredFields"),
		"a contributor may decline a boundary; an empty pass adds empty sums")
	for node: Node in [near, off_screen, hidden, deferred]:
		node.free()
	print("CROWD_BENCHMARK_CENSUS_HOOK failures=", failures)
	quit(1 if failures else 0)


func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
