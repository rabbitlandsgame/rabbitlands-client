extends SceneTree
## Focused baseline/current attribution harness. Timing is reported, never asserted.

const BaselineMesh = preload("res://tests/fixtures/combat_effect_mesh_baseline.gd")
const CurrentMesh = preload("res://src/world/combat_effect_mesh.gd")
const BaselineFlight = preload("res://tests/fixtures/spell_flight_3d_baseline.gd")
const CurrentFlight = preload("res://src/world/spell_flight_3d.gd")
const MESH_ITERATIONS := 240
const FLIGHT_ITERATIONS := 180
const TRIALS := 8
const FLIGHT_AFTERGLOW := 0.24
const FLIGHT_SEGMENTS := 28
const BASELINE_COMMIT := "4c42ab09f12844d5b9e370619c9be93b4f48033f"
const BASELINE_MESH_BODY_SHA256 := "71628e85617c03a6949a74fe500ef29c0cd1860191f0f4fe83c740f33112d3a6"
const BASELINE_FLIGHT_BODY_SHA256 := "c333f8afe62e6387cfcf286fba0a275951abc790cc780c9d3702cc594f930f5e"

var _failures := 0
var _camera: Camera3D


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(960, 540)
	_camera = Camera3D.new()
	root.add_child(_camera)
	_camera.current = true
	_camera.rotation_degrees = Vector3(-37, 28, 0)
	await process_frame
	var parity_executed := DisplayServer.get_name() != "headless"
	if parity_executed:
		_check_exact_parity()
	# Untimed warm-up keeps script compilation/material initialization out of the
	# rotated trials.
	_bench_mesh(BaselineMesh, 8)
	_bench_mesh(CurrentMesh, 8)
	_bench_flight(BaselineFlight, 8)
	_bench_flight(CurrentFlight, 8)
	var trials: Array[Dictionary] = []
	for trial: int in TRIALS:
		var order := ["baseline", "current"] if trial % 2 == 0 \
			else ["current", "baseline"]
		var row := {"trial": trial + 1, "order": order.duplicate(), "results": {}}
		for implementation: String in order:
			var mesh_script: Variant = BaselineMesh if implementation == "baseline" else CurrentMesh
			var flight_script: Variant = BaselineFlight if implementation == "baseline" else CurrentFlight
			var mesh_started := Time.get_ticks_usec()
			var mesh_vertices := _bench_mesh(mesh_script, MESH_ITERATIONS)
			var mesh_usec := Time.get_ticks_usec() - mesh_started
			var flight_started := Time.get_ticks_usec()
			var flight_vertices := _bench_flight(flight_script, FLIGHT_ITERATIONS)
			var flight_usec := Time.get_ticks_usec() - flight_started
			(row.results as Dictionary)[implementation] = {
				"meshMicroseconds": mesh_usec,
				"meshIterations": MESH_ITERATIONS,
				"meshExpectedLastVertices": mesh_vertices,
				"flightMicroseconds": flight_usec,
				"flightIterations": FLIGHT_ITERATIONS,
				"flightExpectedLastVertices": flight_vertices,
			}
		trials.append(row)
	var report := {
		"schemaVersion": 1,
		"parityFailures": _failures,
		"parityExecuted": parity_executed,
		"parityAuthoritative": parity_executed,
		"timingAssertions": false,
		"timingScope": "CPU GDScript geometry emission; excludes GPU and presentation frame rate",
		"rotatedOrder": true,
		"displayServer": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"videoAdapter": RenderingServer.get_video_adapter_name(),
		"sourceBasis": {
			"baselineCommit": BASELINE_COMMIT,
			"baselineMeshBodySha256": BASELINE_MESH_BODY_SHA256,
			"baselineFlightBodySha256": BASELINE_FLIGHT_BODY_SHA256,
			"currentCommit": OS.get_environment("ELORIA_EFFECT_SOURCE_COMMIT"),
			"comparison": "frozen reviewed scripts versus current production",
		},
		"sourceHashes": {
			"baselineMesh": FileAccess.get_sha256(
				"res://tests/fixtures/combat_effect_mesh_baseline.gd"),
			"currentMesh": FileAccess.get_sha256(
				"res://src/world/combat_effect_mesh.gd"),
			"baselineFlight": FileAccess.get_sha256(
				"res://tests/fixtures/spell_flight_3d_baseline.gd"),
			"currentFlight": FileAccess.get_sha256(
				"res://src/world/spell_flight_3d.gd"),
		},
		"workload": {
			"geometryCountBasis": "analytic workload count; actual arrays verified by windowed parity",
			"meshIterations": MESH_ITERATIONS,
			"flightIterations": FLIGHT_ITERATIONS,
			"trials": TRIALS,
			"meshPerIteration": {"lines": 8, "arcs": 5, "sparks": 20},
			"flightEffect": 2,
			"flightPower": 5,
			"movingEndpointsEveryFrames": 17,
		},
		"summary": _summarize(trials),
		"trials": trials,
	}
	var path := OS.get_environment("ELORIA_EFFECT_MICROBENCH_REPORT")
	if path.is_empty():
		var artifact_dir := OS.get_environment("ELORIA_ARTIFACT_DIR")
		path = artifact_dir.path_join("effect-geometry-microbench.json") \
			if not artifact_dir.is_empty() else ProjectSettings.globalize_path(
				"res://test-artifacts/native-crowd/effect-geometry-microbench.json")
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("report file opens: " + path)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("effect geometry microbench: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures,
		" report=", path)
	quit(_failures)


func _bench_mesh(helper: Variant, iterations: int) -> int:
	var mesh := ImmediateMesh.new()
	var material: Material = helper.material()
	var emitted_vertices := 8 * 6 + 20 * 12
	for ring: int in 5:
		var sweep := TAU * (0.6 + ring * 0.05)
		emitted_vertices += maxi(3, ceili(absf(sweep) * 12.0)) * 6
	for frame: int in iterations:
		mesh.clear_surfaces()
		mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, material)
		var elapsed := float(frame) / 60.0
		var progress := fposmod(float(frame) / 73.0, 1.0)
		var color := Color(0.42, 0.76, 1.0, sin(progress * PI) * 0.7)
		for i: int in 8:
			var angle := i * TAU / 8.0 + elapsed * 0.3
			var direction := Vector3(cos(angle), 0, sin(angle))
			helper.line(mesh, direction * 0.56, direction * 0.66, 0.022, color)
		for ring: int in 5:
			helper.arc(mesh, Vector3.UP * (0.45 + ring * 0.23),
				0.4 + ring * 0.05, 0.018, color, elapsed + ring,
				TAU * (0.6 + ring * 0.05),
				Basis(Vector3.RIGHT, ring * PI / 9.0))
		for spark: int in 20:
			var angle := spark * 2.399 + elapsed * 2.0
			helper.spark(mesh, Vector3(cos(angle) * 0.45,
				float(spark) / 20.0 * 1.9, sin(angle) * 0.45),
				0.047, color)
		mesh.surface_end()
	return emitted_vertices


func _bench_flight(script: Variant, iterations: int) -> int:
	var flight = script.new()
	root.add_child(flight)
	flight.configure(2, Color(1.0, 0.43, 0.16, 0.9),
		Vector3(-4, 1, 3), Vector3(13, 4, -8), 5)
	var last_vertices := 0
	for frame: int in iterations:
		if frame % 17 == 0:
			var drift := float(frame % 51) * 0.013
			flight.set_endpoints(Vector3(-4 + drift, 1, 3),
				Vector3(13, 4 + drift * 0.2, -8 - drift))
		var time := fposmod(float(frame) / 57.0,
			float(flight.duration) + FLIGHT_AFTERGLOW + 0.05) - 0.03
		flight.draw_at(time)
		last_vertices = _expected_flight_vertices(time, float(flight.duration))
	flight.free()
	return last_vertices


func _check_exact_parity() -> void:
	var baseline_mesh := _bench_parity_mesh(BaselineMesh)
	var current_mesh := _bench_parity_mesh(CurrentMesh)
	_compare_meshes(baseline_mesh, current_mesh, "primitive workload", true)
	var paths := [
		[Vector3.ZERO, Vector3(5, 0, 0)],
		[Vector3(2, -1, 3), Vector3(2, 6, 3)],
		[Vector3(-4, 2, 1), Vector3(-3.99, 2, 1)],
		[Vector3(12, -5, 9), Vector3(-58, 3, 29)],
		[Vector3(-2, 4, 7), Vector3(-2, 4, 7)],
	]
	for effect: int in [0, 1, 2, 10, 83, 84, 85, 86, 999]:
		var power: int = [1, 5, 10][effect % 3]
		var path: Array = paths[effect % paths.size()]
		var baseline = BaselineFlight.new()
		var current = CurrentFlight.new()
		root.add_child(baseline)
		root.add_child(current)
		baseline.configure(effect, Color(0.2, 0.7, 0.9, 0.8), path[0], path[1], power)
		current.configure(effect, Color(0.2, 0.7, 0.9, 0.8), path[0], path[1], power)
		if baseline.duration != current.duration:
			_fail("flight effect%d power%d duration" % [effect, power])
		if effect % 2 == 0:
			baseline.set_endpoints(path[0] + Vector3(0.2, 0.1, -0.3),
				path[1] + Vector3(-1.0, 0.4, 2.0))
			current.set_endpoints(path[0] + Vector3(0.2, 0.1, -0.3),
				path[1] + Vector3(-1.0, 0.4, 2.0))
		for rotation: Vector3 in [Vector3(-20, 15, 0), Vector3(-70, 130, 0)]:
			_camera.rotation_degrees = rotation
			for time: float in [-0.1, 0.0, baseline.duration * 0.43,
					baseline.duration, baseline.duration + 0.12,
					baseline.duration + 0.25]:
				baseline.draw_at(time)
				current.draw_at(time)
				_compare_meshes(
					(baseline.get_node("SpellEnergy") as MeshInstance3D).mesh,
					(current.get_node("SpellEnergy") as MeshInstance3D).mesh,
					"flight effect%d power%d rotation%s time%.4f" % [
						effect, power, rotation, time],
					time < baseline.duration + FLIGHT_AFTERGLOW)
		baseline.free()
		current.free()


func _bench_parity_mesh(helper: Variant) -> ImmediateMesh:
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, helper.material())
	helper.line(mesh, Vector3.ONE, Vector3.ONE, 0.2, Color.WHITE)
	helper.line(mesh, Vector3(-2, 1, 4), Vector3(5, -3, 0), -0.04,
		Color(0.3, 0.4, 0.5, 0.6), Vector3(0.2, 0.9, -0.1).normalized())
	helper.arc(mesh, Vector3(2, 1, -3), 1.6, 0.08,
		Color(1.0, 0.4, 0.1, 0.5), 1.37, -TAU * 0.85,
		Basis(Vector3(1, 2, -1).normalized(), 0.73))
	helper.arc(mesh, Vector3.ZERO, 0.0, 0.0, Color.TRANSPARENT, -4.2, 0.0)
	helper.spark(mesh, Vector3(0.7, -1.1, 2.4), 0.0,
		Color(0.9, 0.6, 0.2, 0.37))
	mesh.surface_end()
	return mesh


func _compare_meshes(expected: Mesh, actual: Mesh, label: String,
		expect_nonempty: bool) -> void:
	if expected.get_surface_count() != actual.get_surface_count():
		_fail(label + " surface count")
		return
	if expect_nonempty and expected.get_surface_count() == 0:
		_fail(label + " has no rendered surface")
		return
	if not expect_nonempty and expected.get_surface_count() != 0:
		_fail(label + " expired baseline retained a surface")
	for surface: int in expected.get_surface_count():
		var before := expected.surface_get_arrays(surface)
		var after := actual.surface_get_arrays(surface)
		if before.size() != Mesh.ARRAY_MAX or after.size() != Mesh.ARRAY_MAX:
			_fail(label + " does not expose every mesh array slot")
			continue
		if (before[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty() \
				or (after[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty():
			_fail(label + " has no vertices")
		for slot: int in Mesh.ARRAY_MAX:
			if before[slot] != after[slot]:
				_fail(label + " surface%d array%d exact value/order" % [surface, slot])


func _expected_flight_vertices(time: float, flight_duration: float) -> int:
	if time >= flight_duration + FLIGHT_AFTERGLOW:
		return 0
	var vertices := 3 * 6
	if time < 0.0:
		return vertices
	vertices += 2 * FLIGHT_SEGMENTS * 6
	var progress := clampf(time / flight_duration, 0.0, 1.0)
	var count := SpellPresentation.power_count(18, 5)
	for i: int in count:
		var age := float(i) / count
		if progress - age * 0.42 > 0.0:
			vertices += 6
	return vertices


func _summarize(trials: Array[Dictionary]) -> Dictionary:
	var result := {}
	for field: String in ["meshMicroseconds", "flightMicroseconds"]:
		var baseline: Array[float] = []
		var current: Array[float] = []
		for trial: Dictionary in trials:
			var rows: Dictionary = trial["results"]
			var baseline_row: Dictionary = rows["baseline"]
			var current_row: Dictionary = rows["current"]
			baseline.append(float(baseline_row[field]))
			current.append(float(current_row[field]))
		var baseline_median := _median(baseline)
		var current_median := _median(current)
		result[field] = {
			"baselineMedian": baseline_median,
			"currentMedian": current_median,
			"currentVsBaselineRatio": current_median / baseline_median,
			"reductionPercent": (1.0 - current_median / baseline_median) * 100.0,
		}
	return result


func _median(values: Array[float]) -> float:
	var sorted := values.duplicate()
	sorted.sort()
	var middle := floori(sorted.size() / 2.0)
	return (sorted[middle - 1] + sorted[middle]) * 0.5 \
		if sorted.size() % 2 == 0 else sorted[middle]


func _fail(label: String) -> void:
	_failures += 1
	push_error("FAIL: " + label)
