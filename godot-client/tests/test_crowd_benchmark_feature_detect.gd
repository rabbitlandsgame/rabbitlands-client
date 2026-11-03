extends SceneTree
## Wave-2 stage-A measurement harness, engine side: the same harness files run on
## the stage-A client and on the wave-1 baseline. Feature records say what the
## client has (memory classes, HardwareTier.switches(), ContentDigest, the LAT-L7
## frame-motion step); the frame-motion override repeats Main's step only while
## its source is attested; per-leg memory points, dwell ranges and route peaks;
## the first-arrival record. Headless, no Main instance, no map.
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
## Loaded once autoloads exist (Main's script names them).
const BENCHMARK_MAIN_PATH := "res://tests/integration/crowd_benchmark_main.gd"
const Phases := preload("res://tests/integration/map_load_phases.gd")
const Park := preload("res://tests/integration/landfall_town_park.gd")
var failures := 0
var checks := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	await process_frame
	_check_feature_records()
	_check_frame_motion_attestation()
	_check_leg_frame_ranges()
	_check_route_memory_peak()
	_check_first_arrival()
	print("CROWD_BENCHMARK_FEATURE_DETECT checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)


func _has_function(path: String, name: String) -> bool:
	var script := load(path) as Script
	for method: Dictionary in script.get_script_method_list():
		if str(method.get("name", "")) == name:
			return true
	return false


func _check_feature_records() -> void:
	var stage_a := ResourceLoader.exists(Benchmark.MEMORY_BUDGETS_PATH)
	print("NOTE: client has memory classes: ", stage_a)
	var record := Benchmark.memory_class_record()
	_check(record.get("available") == stage_a and (record.get("class") == null) == (not stage_a),
		"memoryClass says whether the client has memory classes: %s" % JSON.stringify(record))
	_check(Park.memory_class_record().get("available") == stage_a, "the park script's record agrees")
	var switches := Benchmark.hardware_switches_record()
	var has_switches := _has_function(Benchmark.HARDWARE_TIER_PATH, "switches")
	_check(switches.get("available") == has_switches
		and (not has_switches or switches.get("switches") is Dictionary),
		"hardwareSwitches says whether HardwareTier.switches() exists: %s" % JSON.stringify(switches))
	var digest := Phases.content_digest_record()
	var has_digest := ResourceLoader.exists(Phases.CONTENT_DIGEST_PATH)
	_check(digest.get("available") == has_digest and digest.get("requestedBy") is Dictionary
		and (not has_digest or str(digest.get("backend", "")) in ["gdscript", "sequential"]),
		"map_load_phases records the content-digest backend in force: %s" % JSON.stringify(digest))
	var estimate := Park.package_estimate("res://does/not/exist/world.json")
	_check(estimate == -1 or estimate >= 0, "the park script's package estimate is read by name (%d)" % estimate)


func _check_frame_motion_attestation() -> void:
	var benchmark_main := load(BENCHMARK_MAIN_PATH) as Script
	if not _check(benchmark_main != null and benchmark_main.can_instantiate(), "the benchmark Main compiles"):
		return
	var constants := benchmark_main.get_script_constant_map()
	var expected: Array = constants.FRAME_MOTION_MAIN_BODY
	var main_path := str(constants.FRAME_MOTION_MAIN_SOURCE)
	var source := "func _ready() -> void:\n\tpass\n\n## doc\nfunc _advance_remote_motion(delta: float) -> void:\n" \
		+ "\t# a comment\n\tReplicatedActor3D.advance_frame_driven(delta)\n\n## next\nfunc other() -> void:\n\tpass\n"
	_check(benchmark_main.call("frame_motion_body", source) == expected,
		"the attested body is Main's one statement, comments and blanks aside")
	var changed := source.replace("advance_frame_driven(delta)", "advance_frame_driven(delta)\n\tother()")
	_check(benchmark_main.call("frame_motion_body", changed) != expected,
		"a changed step is not attested")
	_check(benchmark_main.call("frame_motion_body", "func _process(d):\n\tpass\n").is_empty(), "no step, no body")
	var main_source := FileAccess.get_file_as_string(main_path)
	var has_step := _has_function(main_path, str(constants.FRAME_MOTION_FUNCTION))
	print("NOTE: Main has the LAT-L7 frame-motion step: ", has_step)
	_check(not has_step or benchmark_main.call("frame_motion_body", main_source) == expected,
		"this client's Main step is the body the benchmark override repeats: %s"
			% str(benchmark_main.call("frame_motion_body", main_source)))
	_check(has_step or benchmark_main.call("frame_motion_body", main_source).is_empty(),
		"a client without the step has nothing to attest")


func _check_leg_frame_ranges() -> void:
	var plain := Benchmark.leg_frame_ranges(0, 2, 4, 7, 9, 9, false)
	_check(plain == {"start": [0, 2], "walk": [2, 4], "transition": [4, 7], "capture": [7, 9]},
		"a leg without a dwell keeps the four ranges: %s" % str(plain))
	var dwell := Benchmark.leg_frame_ranges(0, 2, 4, 7, 8, 30, true)
	_check(dwell.capture == [7, 8] and dwell.dwell == [8, 30], "a dwell follows the capture: %s" % str(dwell))


func _check_route_memory_peak() -> void:
	var legs := [
		{"memory": {"beforeTransition": {"staticBytes": 10, "videoBytes": 5,
			"actorScenes": {"bytes": 100, "bytes_by_domain": {"creature": 60, "equipment": 40},
				"strong_scene_entries": 3, "evictions": 0, "evicted_main_rebuilds": 0},
			"worldPark": {"keptBytes": 7}},
			"arrival": {"staticBytes": 30, "videoBytes": 4, "actorScenes": {"bytes": null, "strong_scene_entries": 5}}},
			"dwell": {"points": [{"staticBytes": 20, "actorScenes": {"bytes": 300,
				"bytes_by_domain": {"creature": 250}, "evicted_main_rebuilds": 2}, "worldPark": {"keptBytes": 1}}]}},
		{"id": "failed-start-without-memory"},
	]
	var peak := Benchmark.route_memory_peak(legs)
	_check(peak.points == 3 and peak.staticBytes == 30 and peak.videoBytes == 5 and peak.actorSceneBytes == 300
		and peak.actorSceneEntries == 5 and peak.evictedMainRebuilds == 2 and peak.worldParkKeptBytes == 7
		and peak.actorSceneBytesByDomain == {"creature": 250, "equipment": 40},
		"the route peak takes each field's maximum over legs and dwells: %s" % JSON.stringify(peak))
	var empty := Benchmark.route_memory_peak([])
	_check(empty.points == 0 and empty.actorSceneBytes == null, "no points: nothing claimed")


func _check_first_arrival() -> void:
	var reports := [{"ticksUsec": 500}, {"ticksUsec": 4000}, {"ticksUsec": 9000}]
	var arrival := Benchmark.first_arrival_record(1000, 2500, 7000, reports)
	_check(arrival.loadedMs == 1.5 and arrival.arrivalReportMs == 3.0 and arrival.readyMs == 6.0
		and arrival.arrivalReports == 2, "the first arrival counts from the map request: %s" % JSON.stringify(arrival))
	var none := Benchmark.first_arrival_record(1000, -1, 2000, [])
	_check(none.loadedMs == null and none.arrivalReportMs == null, "no map root or report: null, not zero")


func _check(ok: bool, label: String) -> bool:
	checks += 1
	if ok:
		print("PASS: " + label)
	else:
		failures += 1
		push_error("FAIL: " + label)
	return ok
