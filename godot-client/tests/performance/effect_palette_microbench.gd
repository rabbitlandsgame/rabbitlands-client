extends SceneTree
## Baseline/current proof for replacing WorldEffect3D._palette's per-call table.
## Run surface parity windowed; headless timings are CPU attribution only.

const Baseline = preload("res://tests/fixtures/world_effect_3d_palette_baseline.gd")
const Current = preload("res://src/world/world_effect_3d.gd")
const BASELINE_PATH := "res://tests/fixtures/world_effect_3d_palette_baseline.gd"
const BASELINE_COMMIT := "22ebcd1cd220fa52444034cf3931cf115bd882f7"
const BASELINE_BODY_SHA256 := "28dbe874de014e1ad6653d9b2b9d37636d812e6f57e12f1dfb523ddfc33488b7"
const EFFECTS := [0, 1, 2, 3, 4, 5]
const PHASES := [0.05, 0.25, 0.5, 0.75, 0.95]
const PALETTE_ID_MIN := -32
const PALETTE_ID_MAX := 255
const PALETTE_CYCLES := 64
const DETAIL_CYCLES := 6
const TRIALS := 8

var _stage: Node3D
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	await process_frame
	_check_baseline_provenance()
	var baseline_palette: Node = Baseline.new()
	var current_palette: Node = Current.new()
	_check_all_palette_ids(baseline_palette, current_palette)
	var surface_parity := DisplayServer.get_name() != "headless"
	if surface_parity:
		_check_detail_surfaces()
	_palette_workload(baseline_palette, 1)
	_palette_workload(current_palette, 1)
	var baseline_details := _detail_nodes(Baseline)
	var current_details := _detail_nodes(Current)
	_detail_workload(baseline_details, 1)
	_detail_workload(current_details, 1)
	var trials: Array[Dictionary] = []
	for trial: int in TRIALS:
		var order := ["baseline", "current"] if trial % 2 == 0 \
			else ["current", "baseline"]
		var results := {}
		for implementation: String in order:
			var palette_node := baseline_palette if implementation == "baseline" \
				else current_palette
			var details := baseline_details if implementation == "baseline" \
				else current_details
			var started := Time.get_ticks_usec()
			var checksum := _palette_workload(palette_node, PALETTE_CYCLES)
			var palette_usec := Time.get_ticks_usec() - started
			started = Time.get_ticks_usec()
			_detail_workload(details, DETAIL_CYCLES)
			var detail_usec := Time.get_ticks_usec() - started
			results[implementation] = {
				"paletteMicroseconds": palette_usec,
				"detailMicroseconds": detail_usec,
				"paletteChecksum": checksum,
			}
		trials.append({"trial": trial + 1, "order": order, "results": results})
	var report := {
		"schemaVersion": 1,
		"timingAssertions": false,
		"surfaceParityExecuted": surface_parity,
		"failures": _failures,
		"displayServer": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"sourceBasis": {
			"baselineCommit": BASELINE_COMMIT,
			"baselineBodySha256": BASELINE_BODY_SHA256,
			"currentCommit": OS.get_environment("ELORIA_EFFECT_SOURCE_COMMIT"),
		},
		"sourceHashes": {
			"baseline": FileAccess.get_sha256(BASELINE_PATH),
			"current": FileAccess.get_sha256("res://src/world/world_effect_3d.gd"),
		},
		"workload": {
			"paletteIdRangeInclusive": [PALETTE_ID_MIN, PALETTE_ID_MAX],
			"paletteCycles": PALETTE_CYCLES,
			"paletteCallsPerTrial": (PALETTE_ID_MAX - PALETTE_ID_MIN + 1) \
				* PALETTE_CYCLES,
			"detailEffectIds": EFFECTS,
			"detailPower": 10,
			"detailPhases": PHASES,
			"detailCycles": DETAIL_CYCLES,
			"detailCallsPerTrial": EFFECTS.size() * PHASES.size() * DETAIL_CYCLES,
		},
		"summary": _summarize(trials),
		"trials": trials,
	}
	var output := OS.get_environment("ELORIA_EFFECT_PALETTE_REPORT")
	if output.is_empty():
		output = ProjectSettings.globalize_path(
			"res://test-artifacts/native-crowd/effect-palette-current.json")
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		_fail("report opens: " + output)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	for node: Node in baseline_details + current_details:
		node.free()
	baseline_palette.free()
	current_palette.free()
	_stage.free()
	print("effect palette current: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures,
		" report=", output)
	quit(_failures)


func _check_all_palette_ids(baseline: Node, current: Node) -> void:
	for effect: int in range(PALETTE_ID_MIN, PALETTE_ID_MAX + 1):
		baseline.set("effect_id", effect)
		current.set("effect_id", effect)
		_expect(baseline.call("_palette") == current.call("_palette"),
			"palette id %d exact color" % effect)


func _check_baseline_provenance() -> void:
	var source := FileAccess.get_file_as_string(BASELINE_PATH)
	var body_at := source.find("extends Node3D")
	_expect(body_at >= 0, "frozen palette baseline contains the source body")
	if body_at < 0:
		return
	var normalized := source.substr(body_at).replace("\r\n", "\n")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(normalized.to_utf8_buffer())
	_expect(context.finish().hex_encode() == BASELINE_BODY_SHA256,
		"frozen palette baseline matches the reviewed source SHA-256")


func _check_detail_surfaces() -> void:
	for effect: int in EFFECTS:
		var baseline := _configured(Baseline, effect)
		var current := _configured(Current, effect)
		for phase: float in PHASES:
			baseline.set("elapsed", phase * 1.1)
			current.set("elapsed", phase * 1.1)
			baseline.call("_draw_details", phase)
			current.call("_draw_details", phase)
			_compare_meshes(baseline.get("_details") as Mesh,
				current.get("_details") as Mesh,
				"effect%d phase%.2f" % [effect, phase])
		baseline.free()
		current.free()


func _detail_nodes(script: Variant) -> Array[Node]:
	var nodes: Array[Node] = []
	for effect: int in EFFECTS:
		nodes.append(_configured(script, effect))
	return nodes


func _configured(script: Variant, effect: int) -> Node:
	var node: Node = script.new()
	node.set_process(false)
	_stage.add_child(node)
	node.call("configure", effect, Vector3.ZERO, null, 10)
	return node


func _palette_workload(node: Node, cycles: int) -> float:
	var checksum := 0.0
	for cycle: int in cycles:
		for effect: int in range(PALETTE_ID_MIN, PALETTE_ID_MAX + 1):
			node.set("effect_id", effect)
			var color: Color = node.call("_palette")
			checksum += color.r + color.g + color.b + color.a
	return checksum


func _detail_workload(nodes: Array[Node], cycles: int) -> void:
	for cycle: int in cycles:
		for node: Node in nodes:
			for phase: float in PHASES:
				node.set("elapsed", phase * 1.1 + cycle * 0.001)
				node.call("_draw_details", phase)


func _compare_meshes(baseline: Mesh, current: Mesh, label: String) -> void:
	_expect(baseline.get_surface_count() == current.get_surface_count(),
		label + " surface count")
	_expect(baseline.get_surface_count() > 0, label + " real surface")
	if baseline.get_surface_count() != current.get_surface_count():
		return
	for surface: int in baseline.get_surface_count():
		var expected := baseline.surface_get_arrays(surface)
		var actual := current.surface_get_arrays(surface)
		_expect(expected.size() == Mesh.ARRAY_MAX and actual.size() == Mesh.ARRAY_MAX,
			label + " all array slots")
		if expected.size() != Mesh.ARRAY_MAX or actual.size() != Mesh.ARRAY_MAX:
			continue
		_expect(not (expected[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty(),
			label + " baseline vertices")
		for slot: int in Mesh.ARRAY_MAX:
			_expect(expected[slot] == actual[slot],
				label + " array%d exact" % slot)


func _summarize(trials: Array[Dictionary]) -> Dictionary:
	var result := {}
	for field: String in ["paletteMicroseconds", "detailMicroseconds"]:
		var baseline: Array[float] = []
		var current: Array[float] = []
		for trial: Dictionary in trials:
			var rows: Dictionary = trial["results"]
			baseline.append(float((rows["baseline"] as Dictionary)[field]))
			current.append(float((rows["current"] as Dictionary)[field]))
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


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	_failures += 1
	push_error("FAIL: " + message)
