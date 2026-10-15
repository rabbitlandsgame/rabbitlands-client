extends SceneTree
## Exact frozen-GDS versus native world-detail geometry probe. Timings include
## output validation and mesh submission, but exclude setup, array readback, GPU
## completion, frame scheduling and every other part of WorldEffect3D._process.

const Baseline = preload("res://tests/fixtures/world_effect_3d_967744_baseline.gd")
const Candidate = preload("res://src/world/world_effect_3d.gd")
const BASELINE_SOURCE_SHA256 := "8586cceda29f07ce352bf4f33513f50d36e33c28e808847941699743558d9e2a"
const BASELINE_COMMIT := "ef6825b92a468ff275a847cc063eed115695b1b5"
const EFFECTS := [0, 1, 2, 3, 18, 19, 74, 75, 76, 77, 78, 79, 80, 81, 82,
	84, 85, 999]
const POWERS := [1, 3, 5, 7, 10]
const ALL_POWER_LEVELS := [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
const PROGRESSES := [0.0, 0.37, 1.0]
const TIMING_EFFECTS := [0, 1, 2, 3, 4, 5]
const TIMING_POWER := 10
const ITERATIONS := 360
const TRIALS := 7

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var original_mode := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "world")
	if not ClassDB.class_exists(&"NativeWorldEffectGeometry"):
		var extension_path := "res://bin/native_crowd.gdextension"
		_expect(FileAccess.file_exists(extension_path),
			"native crowd extension descriptor exists")
		if FileAccess.file_exists(extension_path):
			GDExtensionManager.load_extension(extension_path)
	if not ClassDB.class_exists(&"NativeWorldEffectGeometry"):
		_fail("native world effect geometry class is registered")
		_finish({
			"schemaVersion": 1,
			"failures": _failures,
			"parityExecuted": false,
			"parityAuthoritative": false,
			"timingAssertions": false,
			"error": "NativeWorldEffectGeometry is unavailable",
			"displayServer": DisplayServer.get_name(),
		}, original_mode)
		return
	var baseline_script := Baseline as Script
	var candidate_script := Candidate as Script
	if baseline_script == null or candidate_script == null \
			or not baseline_script.can_instantiate() \
			or not candidate_script.can_instantiate():
		_fail("baseline and candidate scripts instantiate")
		_finish({
			"schemaVersion": 1,
			"failures": _failures,
			"parityExecuted": false,
			"parityAuthoritative": false,
			"timingAssertions": false,
			"error": "A probe fixture failed to compile",
			"displayServer": DisplayServer.get_name(),
		}, original_mode)
		return
	_expect(_baseline_source_hash_matches(),
		"frozen baseline body matches 967744 production source")
	_check_invalid_guards()
	_check_power_count_contract()
	var parity_executed := DisplayServer.get_name() != "headless"
	if parity_executed:
		_check_parity()
	var baseline_bank := _make_bank(Baseline)
	var candidate_bank := _make_bank(Candidate)
	_bench(baseline_bank, 12)
	_bench(candidate_bank, 12)
	var stats_before := Candidate.native_presentation_stats()
	var trials: Array[Dictionary] = []
	for trial: int in TRIALS:
		var order := ["baseline", "candidate"] if trial % 2 == 0 \
			else ["candidate", "baseline"]
		var row := {"trial": trial + 1, "order": order.duplicate(), "results": {}}
		for implementation: String in order:
			var bank: Array = baseline_bank if implementation == "baseline" \
				else candidate_bank
			var started := Time.get_ticks_usec()
			_bench(bank, ITERATIONS)
			var elapsed_usec := Time.get_ticks_usec() - started
			(row.results as Dictionary)[implementation] = {
				"microseconds": elapsed_usec,
				"iterations": ITERATIONS,
				"microsecondsPerDraw": float(elapsed_usec) / ITERATIONS,
			}
		trials.append(row)
		await process_frame
	var stats_after := Candidate.native_presentation_stats()
	var stats_delta := {
		"buildAttempts": int(stats_after.buildAttempts) - int(stats_before.buildAttempts),
		"buildSuccesses": int(stats_after.buildSuccesses) - int(stats_before.buildSuccesses),
		"buildFallbacks": int(stats_after.buildFallbacks) - int(stats_before.buildFallbacks),
	}
	_expect(int(stats_delta.buildAttempts) > 0,
		"candidate records native build attempts")
	_expect(int(stats_delta.buildAttempts) == int(stats_delta.buildSuccesses),
		"every timed native build succeeds")
	_expect(int(stats_delta.buildFallbacks) == 0,
		"timed candidate never falls back")
	var report := {
		"schemaVersion": 1,
		"failures": _failures,
		"parityExecuted": parity_executed,
		"parityAuthoritative": parity_executed and _failures == 0,
		"timingAssertions": false,
		"timingScope": ("CPU detail geometry build, packed-output validation and "
			+ "ArrayMesh/ImmediateMesh submission; excludes setup, readback, GPU, "
			+ "ring, particles, flight geometry, anchors and frame rate"),
		"displayServer": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"videoAdapter": RenderingServer.get_video_adapter_name(),
		"sourceBasis": {
			"baselineCommit": BASELINE_COMMIT,
			"baselineProductionSha256": BASELINE_SOURCE_SHA256,
			"comparison": "frozen 967744 GDS detail path versus production world opt-in",
		},
		"sourceHashes": {
			"baseline": FileAccess.get_sha256(
				"res://tests/fixtures/world_effect_3d_967744_baseline.gd"),
			"candidate": FileAccess.get_sha256(
				"res://src/world/world_effect_3d.gd"),
			"nativeHeader": FileAccess.get_sha256(
				"res://native/native_crowd/src/native_world_effect_geometry.h"),
			"nativeSource": FileAccess.get_sha256(
				"res://native/native_crowd/src/native_world_effect_geometry.cpp"),
			"nativeDll": FileAccess.get_sha256(
				"res://bin/windows/native_crowd.windows.template_release.x86_64.dll"),
		},
		"coverage": {
			"effects": EFFECTS, "parityPowers": POWERS,
			"directCountPowers": ALL_POWER_LEVELS, "progresses": PROGRESSES,
			"areaRadii": [0.25, 3.5], "localAndFlightContact": true,
			"unknownEffect": 999, "degenerateProgressEndpoints": [0.0, 1.0],
		},
		"workload": {"iterations": ITERATIONS, "trials": TRIALS,
			"rotatedOrder": true, "meshReadbackInsideTimedRegion": false,
			"effectIds": TIMING_EFFECTS, "powerLevel": TIMING_POWER,
			"areaRadius": 0.0, "flightContact": false},
		"nativeStatsDelta": stats_delta,
		"summary": _summary(trials),
		"trials": trials,
	}
	_free_bank(baseline_bank)
	_free_bank(candidate_bank)
	_finish(report, original_mode)


func _finish(report: Dictionary, original_mode: String) -> void:
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", original_mode)
	var output := OS.get_environment("ELORIA_WORLD_EFFECT_NATIVE_REPORT")
	if output.is_empty():
		var artifact_dir := OS.get_environment("ELORIA_ARTIFACT_DIR")
		output = artifact_dir.path_join("world-effect-native-probe.json") \
			if not artifact_dir.is_empty() else ProjectSettings.globalize_path(
				"res://test-artifacts/native-crowd/world-effect-native-probe.json")
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		_fail("report opens: " + output)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("world effect native probe: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures,
		" report=", output)
	quit(_failures)


func _baseline_source_hash_matches() -> bool:
	var fixture := FileAccess.get_file_as_string(
		"res://tests/fixtures/world_effect_3d_967744_baseline.gd")
	var body_at := fixture.find("extends Node3D")
	if body_at < 0:
		return false
	var newline := "\r\n" if fixture.contains("\r\n") else "\n"
	var reconstructed := "class_name WorldEffect3D" + newline \
		+ fixture.substr(body_at)
	return reconstructed.sha256_text() == BASELINE_SOURCE_SHA256


func _check_invalid_guards() -> void:
	var builder := ClassDB.instantiate(&"NativeWorldEffectGeometry") as RefCounted
	if builder == null:
		return
	var valid_args := [2, 5, 0.4, 0.37, Vector3(1, 2, 3),
		Color(0.2, 0.7, 0.9, 0.5), 1.9, 1.63, 0.0, false, Vector3.ZERO]
	var invalid_cases := [
		["power zero", 1, 0], ["power eleven", 1, 11],
		["negative progress", 3, -0.01], ["progress above one", 3, 1.01],
		["negative area", 8, -0.01], ["nonfinite elapsed", 2, NAN],
		["huge finite elapsed", 2, 1.0e100],
		["nonfinite impact", 4, Vector3(INF, 0, 0)],
		["unbounded palette", 5, Color(1.0e30, 1, 1, 1)],
	]
	for row: Array in invalid_cases:
		var args := valid_args.duplicate()
		args[int(row[1])] = row[2]
		var result: Array = builder.callv("build", args) as Array
		_expect(result.is_empty(), "%s is rejected atomically" % str(row[0]))
	var valid: Array = builder.callv("build", valid_args) as Array
	_expect(_packed_output_valid_and_finite(valid),
		"bounded direct native call returns finite packed arrays")


func _check_power_count_contract() -> void:
	var builder := ClassDB.instantiate(&"NativeWorldEffectGeometry") as RefCounted
	if builder == null:
		_fail("power-count native builder instantiates")
		return
	for power: int in ALL_POWER_LEVELS:
		var common_vertices := 8 * 6
		var generic: Array = builder.call("build", 0, power, 0.4, 0.37,
			Vector3.ZERO, Color.WHITE, 1.0, 1.0, 0.0, false,
			Vector3.ZERO) as Array
		var blessing: Array = builder.call("build", 1, power, 0.4, 0.37,
			Vector3.ZERO, Color.WHITE, 1.0, 1.0, 0.0, false,
			Vector3.ZERO) as Array
		_expect(_packed_output_valid_and_finite(generic),
			"generic power%d direct output valid" % power)
		_expect(_packed_output_valid_and_finite(blessing),
			"blessing power%d direct output valid" % power)
		if _packed_output_valid_and_finite(generic):
			_expect((generic[0] as PackedVector3Array).size() == common_vertices
				+ SpellPresentation.power_count(14, power) * 6,
				"generic power%d nonlinear count" % power)
		if _packed_output_valid_and_finite(blessing):
			_expect((blessing[0] as PackedVector3Array).size() == common_vertices
				+ SpellPresentation.power_count(20, power) * 12,
				"blessing power%d nonlinear count" % power)


func _check_parity() -> void:
	for effect: int in EFFECTS:
		for power: int in POWERS:
			for progress: float in PROGRESSES:
				var elapsed := 0.0 if progress == 0.0 else (
					1.1 if progress == 1.0 else 0.407 + effect * 0.001)
				_compare_case(effect, power, elapsed, progress, 0.0,
					effect % 2 == 0, "effect%d power%d progress%.2f" % [
						effect, power, progress])
	for area: float in [0.25, 3.5]:
		for power: int in POWERS:
			_compare_case(3, power, 0.63, 0.57, area, false,
				"area%.2f power%d" % [area, power])


func _compare_case(effect: int, power: int, elapsed_value: float,
		progress: float, area: float, with_flight: bool, label: String) -> void:
	var target: Variant = Vector3(4.5, 1.2, -3.7) if with_flight else null
	var baseline = Baseline.new()
	var candidate = Candidate.new()
	baseline.set_process(false)
	candidate.set_process(false)
	baseline.visible = false
	candidate.visible = false
	get_root().add_child(baseline)
	get_root().add_child(candidate)
	baseline.configure(effect, Vector3(-2, 0.5, 3), target, power)
	candidate.configure(effect, Vector3(-2, 0.5, 3), target, power)
	if area > 0.0:
		baseline.configure_area(area, "probe")
		candidate.configure_area(area, "probe")
	baseline.elapsed = elapsed_value
	candidate.elapsed = elapsed_value
	baseline.set("_impact", Vector3(0.7, -0.2, 1.1))
	candidate.set("_impact", Vector3(0.7, -0.2, 1.1))
	if with_flight:
		baseline.flight.destination = Vector3(-0.6, 1.8, 2.7)
		candidate.flight.destination = Vector3(-0.6, 1.8, 2.7)
	baseline.call("_draw_details", progress)
	candidate.call("_draw_details", progress)
	_expect(candidate.native_presentation_active(), label + " native path active")
	var expected := (baseline.get_node("EffectRunes") as MeshInstance3D).mesh
	var actual := (candidate.get_node("EffectRunes") as MeshInstance3D).mesh
	_compare_meshes(expected, actual, label)
	baseline.free()
	candidate.free()


func _compare_meshes(expected: Mesh, actual: Mesh, label: String) -> void:
	_expect(expected != null and actual != null, label + " meshes exist")
	if expected == null or actual == null:
		return
	_expect(expected.get_surface_count() == 1 and actual.get_surface_count() == 1,
		label + " one triangle surface")
	if expected.get_surface_count() != 1 or actual.get_surface_count() != 1:
		return
	var before := expected.surface_get_arrays(0)
	var after := actual.surface_get_arrays(0)
	_expect(before.size() == Mesh.ARRAY_MAX and after.size() == Mesh.ARRAY_MAX,
		label + " complete mesh array slots")
	if before.size() != Mesh.ARRAY_MAX or after.size() != Mesh.ARRAY_MAX:
		return
	for slot: int in Mesh.ARRAY_MAX:
		_expect(before[slot] == after[slot], label + " exact array%d" % slot)
	_expect(_packed_output_valid_and_finite([
		after[Mesh.ARRAY_VERTEX], after[Mesh.ARRAY_COLOR]]),
		label + " finite native vertices and colors")
	_compare_materials(expected.surface_get_material(0),
		actual.surface_get_material(0), label + " material")


func _compare_materials(expected: Material, actual: Material, label: String) -> void:
	_expect(expected is StandardMaterial3D and actual is StandardMaterial3D,
		label + " StandardMaterial3D type")
	if not expected is StandardMaterial3D or not actual is StandardMaterial3D:
		return
	var left := expected as StandardMaterial3D
	var right := actual as StandardMaterial3D
	_expect(left.shading_mode == right.shading_mode, label + " shading")
	_expect(left.transparency == right.transparency, label + " transparency")
	_expect(left.blend_mode == right.blend_mode, label + " blend")
	_expect(left.vertex_color_use_as_albedo == right.vertex_color_use_as_albedo,
		label + " vertex color")
	_expect(left.cull_mode == right.cull_mode, label + " cull")
	_expect(left.no_depth_test == right.no_depth_test, label + " depth")
	_expect(left.albedo_color == right.albedo_color, label + " albedo")


func _packed_output_valid_and_finite(packed: Array) -> bool:
	if packed.size() != 2 \
			or typeof(packed[0]) != TYPE_PACKED_VECTOR3_ARRAY \
			or typeof(packed[1]) != TYPE_PACKED_COLOR_ARRAY:
		return false
	var vertices := packed[0] as PackedVector3Array
	var colors := packed[1] as PackedColorArray
	if vertices.is_empty() or vertices.size() % 3 != 0 \
			or colors.size() != vertices.size():
		return false
	for value: Vector3 in vertices:
		if not value.is_finite():
			return false
	for value: Color in colors:
		if not is_finite(value.r) or not is_finite(value.g) \
				or not is_finite(value.b) or not is_finite(value.a):
			return false
	return true


func _make_bank(script: Variant) -> Array:
	var result: Array = []
	for effect: int in TIMING_EFFECTS:
		var node = script.new()
		node.set_process(false)
		node.visible = false
		get_root().add_child(node)
		node.configure(effect, Vector3.ZERO, null, TIMING_POWER)
		# configure() starts the production lifetime. Freeze only after the real
		# setup path so the between-trial frame cannot expire benchmark nodes.
		node.set_process(false)
		result.append(node)
	return result


func _bench(bank: Array, iterations: int) -> void:
	if bank.is_empty():
		_fail("timing bank is nonempty")
		return
	for value: Variant in bank:
		if not is_instance_valid(value):
			_fail("timing bank nodes remain alive")
			return
	for iteration: int in iterations:
		var node: Node = bank[iteration % bank.size()]
		var progress := fposmod(float(iteration) / 79.0, 1.0)
		node.set("elapsed", float(iteration) / 61.0)
		node.call("_draw_details", progress)


func _free_bank(bank: Array) -> void:
	for value: Variant in bank:
		if is_instance_valid(value):
			(value as Node).free()


func _summary(trials: Array[Dictionary]) -> Dictionary:
	var baseline: Array[float] = []
	var candidate: Array[float] = []
	for trial: Dictionary in trials:
		var results := trial.results as Dictionary
		baseline.append(float((results.baseline as Dictionary).microsecondsPerDraw))
		candidate.append(float((results.candidate as Dictionary).microsecondsPerDraw))
	var baseline_median := _median(baseline)
	var candidate_median := _median(candidate)
	return {
		"baselineMedianMicrosecondsPerDraw": baseline_median,
		"candidateMedianMicrosecondsPerDraw": candidate_median,
		"candidateVsBaselineRatio": candidate_median / baseline_median,
		"reductionPercent": (1.0 - candidate_median / baseline_median) * 100.0,
	}


func _median(values: Array[float]) -> float:
	var sorted := values.duplicate()
	sorted.sort()
	return sorted[sorted.size() / 2]


func _expect(value: bool, label: String) -> void:
	if not value:
		_fail(label)


func _fail(label: String) -> void:
	_failures += 1
	push_error("FAIL: " + label)
