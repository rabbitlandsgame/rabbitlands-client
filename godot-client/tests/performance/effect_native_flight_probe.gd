extends SceneTree
## Isolated ImmediateMesh-versus-native-flight geometry submission probe.
## Timing is diagnostic and never asserted; windowed runs also require exact
## mesh-array and material parity before their timings are usable.

const Baseline = preload("res://tests/fixtures/spell_flight_3d_269c_baseline.gd")
const Candidate = preload("res://src/world/spell_flight_3d.gd")
const BASELINE_SHA256 := "0097916f9a7aca508918d088df479c5c6c7061ae0fcc02e950198faa32326d65"
const ITERATIONS := 180
const TRIALS := 8
const EFFECTS := [0, 1, 2, 10, 83, 84, 85, 86, 999]
const PATHS := [
	[Vector3.ZERO, Vector3(5, 0, 0)],
	[Vector3(2, -1, 3), Vector3(2, 6, 3)],
	[Vector3(-4, 2, 1), Vector3(-3.99, 2, 1)],
	[Vector3(12, -5, 9), Vector3(-58, 3, 29)],
	[Vector3(-2, 4, 7), Vector3(-2, 4, 7)],
]

var _camera: Camera3D
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var original_mode := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	if not ClassDB.class_exists(&"NativeSpellFlightGeometry"):
		var extension_path := "res://bin/native_crowd.gdextension"
		_expect(FileAccess.file_exists(extension_path),
			"native crowd extension descriptor exists")
		if FileAccess.file_exists(extension_path):
			GDExtensionManager.load_extension(extension_path)
	root.size = Vector2i(960, 540)
	_camera = Camera3D.new()
	root.add_child(_camera)
	_camera.current = true
	await process_frame
	_expect(FileAccess.get_sha256(
		"res://tests/fixtures/spell_flight_3d_269c_baseline.gd") == BASELINE_SHA256,
		"baseline bytes match b90e4238b production")
	_expect(ClassDB.class_exists("NativeSpellFlightGeometry"),
		"native flight geometry class is registered")
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "flight")
	var stats_before: Dictionary = Candidate.native_presentation_stats()
	_check_invalid_guards()
	var parity_executed := DisplayServer.get_name() != "headless"
	if parity_executed:
		_check_parity()
	_bench(Baseline, 8)
	_bench(Candidate, 8)
	var trials: Array[Dictionary] = []
	for trial: int in TRIALS:
		var order := ["baseline", "candidate"] if trial % 2 == 0 \
			else ["candidate", "baseline"]
		var row := {"trial": trial + 1, "order": order.duplicate(), "results": {}}
		for implementation: String in order:
			var script: Variant = Baseline if implementation == "baseline" else Candidate
			var started := Time.get_ticks_usec()
			_bench(script, ITERATIONS)
			var elapsed := Time.get_ticks_usec() - started
			(row.results as Dictionary)[implementation] = {
				"microseconds": elapsed,
				"iterations": ITERATIONS,
			}
		trials.append(row)
		await process_frame
	var stats_after: Dictionary = Candidate.native_presentation_stats()
	var attempt_delta := int(stats_after.buildAttempts) - int(stats_before.buildAttempts)
	var success_delta := int(stats_after.buildSuccesses) - int(stats_before.buildSuccesses)
	var fallback_delta := int(stats_after.buildFallbacks) - int(stats_before.buildFallbacks)
	_expect(attempt_delta > 0, "production native path records build attempts")
	_expect(success_delta == attempt_delta,
		"every production native attempt succeeds in the probe")
	_expect(fallback_delta == 0, "production probe does not fall back")
	var report := {
		"schemaVersion": 1,
		"failures": _failures,
		"parityExecuted": parity_executed,
		"parityAuthoritative": parity_executed and _failures == 0,
		"timingAssertions": false,
		"timingScope": ("CPU flight geometry construction and mesh submission; "
			+ "frame advance occurs outside timed regions; excludes GPU completion and frame rate"),
		"displayServer": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"videoAdapter": RenderingServer.get_video_adapter_name(),
		"sourceHashes": {
			"baseline": FileAccess.get_sha256(
				"res://tests/fixtures/spell_flight_3d_269c_baseline.gd"),
			"candidate": FileAccess.get_sha256(
				"res://src/world/spell_flight_3d.gd"),
			"isolatedPrototype": FileAccess.get_sha256(
				"res://tests/fixtures/spell_flight_3d_native_candidate.gd"),
			"nativeHeader": FileAccess.get_sha256(
				"res://native/native_crowd/src/native_spell_flight_geometry.h"),
			"nativeSource": FileAccess.get_sha256(
				"res://native/native_crowd/src/native_spell_flight_geometry.cpp"),
			"nativeDll": FileAccess.get_sha256(
				"res://bin/windows/native_crowd.windows.template_release.x86_64.dll"),
		},
		"workload": {
			"effect": 2, "power": 5, "iterations": ITERATIONS,
			"trials": TRIALS, "movingEndpointsEveryFrames": 17,
		},
		"summary": _summary(trials),
		"nativeStatsDelta": {
			"buildAttempts": attempt_delta,
			"buildSuccesses": success_delta,
			"buildFallbacks": fallback_delta,
		},
		"trials": trials,
	}
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", original_mode)
	var output := OS.get_environment("ELORIA_EFFECT_NATIVE_FLIGHT_REPORT")
	if output.is_empty():
		output = OS.get_environment("ELORIA_ARTIFACT_DIR").path_join(
			"effect-native-flight-probe.json")
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		_fail("report opens: " + output)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("effect native flight probe: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures,
		" report=", output)
	quit(_failures)


func _check_invalid_guards() -> void:
	var builder: RefCounted = ClassDB.instantiate(
		"NativeSpellFlightGeometry") as RefCounted
	if builder == null:
		return
	var invalid_duration: Array = builder.call("build", 2, Color.WHITE,
		Vector3.ZERO, Vector3.ONE, Vector3.RIGHT, Vector3.UP, 0.5, 0.2,
		0.4, 0.0, 0.1, Vector3.FORWARD, Vector3.RIGHT, Vector3.UP, 1.0, 18)
	_expect(invalid_duration.is_empty(), "zero duration is rejected")
	var invalid_count: Array = builder.call("build", 2, Color.WHITE,
		Vector3.ZERO, Vector3.ONE, Vector3.RIGHT, Vector3.UP, 0.5, 0.2,
		0.4, 0.4, 0.1, Vector3.FORWARD, Vector3.RIGHT, Vector3.UP, 1.0, 82)
	_expect(invalid_count.is_empty(), "unsupported particle count is rejected")


func _bench(script: Variant, iterations: int) -> void:
	var flight = script.new()
	root.add_child(flight)
	flight.configure(2, Color(1.0, 0.43, 0.16, 0.9),
		Vector3(-4, 1, 3), Vector3(13, 4, -8), 5)
	for frame: int in iterations:
		if frame % 17 == 0:
			var drift := float(frame % 51) * 0.013
			flight.set_endpoints(Vector3(-4 + drift, 1, 3),
				Vector3(13, 4 + drift * 0.2, -8 - drift))
		var time := fposmod(float(frame) / 57.0,
			float(flight.duration) + 0.24 + 0.05) - 0.03
		flight.draw_at(time)
	flight.free()


func _check_parity() -> void:
	for effect: int in EFFECTS:
		var power: int = [1, 5, 10][effect % 3]
		var path: Array = PATHS[effect % PATHS.size()]
		var baseline = Baseline.new()
		var candidate = Candidate.new()
		root.add_child(baseline)
		root.add_child(candidate)
		baseline.configure(effect, Color(0.2, 0.7, 0.9, 0.8), path[0], path[1], power)
		candidate.configure(effect, Color(0.2, 0.7, 0.9, 0.8), path[0], path[1], power)
		_expect(baseline.duration == candidate.duration,
			"effect%d duration" % effect)
		if effect % 2 == 0 and path[0] != path[1]:
			baseline.set_endpoints(path[0] + Vector3(0.2, 0.1, -0.3),
				path[1] + Vector3(-1.0, 0.4, 2.0))
			candidate.set_endpoints(path[0] + Vector3(0.2, 0.1, -0.3),
				path[1] + Vector3(-1.0, 0.4, 2.0))
		for rotation: Vector3 in [Vector3(-20, 15, 0), Vector3(-70, 130, 0)]:
			_camera.rotation_degrees = rotation
			for time: float in [-0.1, 0.0, baseline.duration * 0.43,
					baseline.duration, baseline.duration + 0.12,
					baseline.duration + 0.24, baseline.duration + 0.25]:
				baseline.draw_at(time)
				candidate.draw_at(time)
				_compare_meshes(
					(baseline.get_node("SpellEnergy") as MeshInstance3D).mesh,
					(candidate.get_node("SpellEnergy") as MeshInstance3D).mesh,
					"effect%d rotation%s time%.5f" % [effect, rotation, time],
					time < baseline.duration + 0.24)
		baseline.free()
		candidate.free()


func _compare_meshes(expected: Mesh, actual: Mesh, label: String,
		expect_nonempty: bool) -> void:
	_expect(expected.get_surface_count() == actual.get_surface_count(),
		label + " surface count")
	if expected.get_surface_count() != actual.get_surface_count():
		return
	_expect((expected.get_surface_count() > 0) == expect_nonempty,
		label + " expected surface state")
	for surface: int in expected.get_surface_count():
		var before := expected.surface_get_arrays(surface)
		var after := actual.surface_get_arrays(surface)
		_expect(before.size() == Mesh.ARRAY_MAX and after.size() == Mesh.ARRAY_MAX,
			label + " complete arrays")
		if before.size() != Mesh.ARRAY_MAX or after.size() != Mesh.ARRAY_MAX:
			continue
		_expect(not (before[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty(),
			label + " baseline vertices")
		_expect(not (after[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty(),
			label + " candidate vertices")
		for slot: int in Mesh.ARRAY_MAX:
			_expect(before[slot] == after[slot],
				label + " surface%d array%d exact value/order" % [surface, slot])
		_compare_materials(expected.surface_get_material(surface),
			actual.surface_get_material(surface), label + " material")


func _compare_materials(expected: Material, actual: Material, label: String) -> void:
	_expect(expected != null and actual != null, label + " exists")
	if expected == null or actual == null:
		return
	_expect(expected.get_class() == actual.get_class(), label + " type")
	if expected is ShaderMaterial and actual is ShaderMaterial:
		var left := expected as ShaderMaterial
		var right := actual as ShaderMaterial
		_expect(left.shader == right.shader, label + " shader")
		for parameter: String in ["radial", "intensity"]:
			_expect(left.get_shader_parameter(parameter)
				== right.get_shader_parameter(parameter), label + " " + parameter)
	_expect(expected.render_priority == actual.render_priority, label + " priority")
	_expect(expected.next_pass == actual.next_pass, label + " next pass")


func _summary(trials: Array[Dictionary]) -> Dictionary:
	var baseline: Array[float] = []
	var candidate: Array[float] = []
	for trial: Dictionary in trials:
		var results: Dictionary = trial["results"]
		baseline.append(float((results["baseline"] as Dictionary)["microseconds"]))
		candidate.append(float((results["candidate"] as Dictionary)["microseconds"]))
	baseline.sort()
	candidate.sort()
	var middle := floori(baseline.size() / 2.0)
	var baseline_median := (baseline[middle - 1] + baseline[middle]) * 0.5
	var candidate_median := (candidate[middle - 1] + candidate[middle]) * 0.5
	return {
		"baselineMedianMicroseconds": baseline_median,
		"candidateMedianMicroseconds": candidate_median,
		"candidateVsBaselineRatio": candidate_median / baseline_median,
		"reductionPercent": (1.0 - candidate_median / baseline_median) * 100.0,
	}


func _expect(value: bool, label: String) -> void:
	if not value:
		_fail(label)


func _fail(label: String) -> void:
	_failures += 1
	push_error("FAIL: " + label)
