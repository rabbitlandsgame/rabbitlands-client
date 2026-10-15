extends SceneTree
## Attribution-only probe for a possible WorldEffect resource-cache phase.
## It measures current instantiate/configure costs and live resource identity;
## it neither asserts timings nor changes the production cache policy.

const Effect = preload("res://src/world/world_effect_3d.gd")
const DEFAULT_SAMPLES := 32
const EFFECTS := [0, 1, 2, 3, 4, 5]
const POWERS := [1, 5, 10]
const DRAW_PHASES := [0.05, 0.25, 0.5, 0.75, 0.95]
const FLIGHT_PHASES := [-0.1, 0.0, 0.2, 0.5, 0.8, 1.0]
const DRAW_CYCLES := 8
const DRAW_TRIALS := 8

var _stage: Node3D
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	await process_frame
	var sample_count := maxi(4, int(OS.get_environment(
		"ELORIA_EFFECT_RESOURCE_SAMPLES")) if not OS.get_environment(
			"ELORIA_EFFECT_RESOURCE_SAMPLES").is_empty() else DEFAULT_SAMPLES)
	var cases: Array[Dictionary] = []
	for effect: int in EFFECTS:
		for power: int in POWERS:
			cases.append(await _measure_case(effect, power, "local", sample_count))
			cases.append(await _measure_case(effect, power, "flight", sample_count))
	for power: int in POWERS:
		cases.append(await _measure_case(3, power, "area", sample_count))
	var draw_attribution := _measure_draw_workloads()
	var report := {
		"schemaVersion": 1,
		"timingAssertions": false,
		"timingScope": "CPU instantiate/configure attribution; excludes rendering and frame rate",
		"displayServer": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"sourceCommit": OS.get_environment("ELORIA_EFFECT_SOURCE_COMMIT"),
		"sourceHashes": {
			"worldEffect": FileAccess.get_sha256("res://src/world/world_effect_3d.gd"),
			"spellFlight": FileAccess.get_sha256("res://src/world/spell_flight_3d.gd"),
			"combatEffectMesh": FileAccess.get_sha256(
				"res://src/world/combat_effect_mesh.gd"),
		},
		"samplesPerCase": sample_count,
		"cases": cases,
		"drawAttribution": draw_attribution,
		"failures": _failures,
	}
	var output := OS.get_environment("ELORIA_EFFECT_RESOURCE_REPORT")
	if output.is_empty():
		output = ProjectSettings.globalize_path(
			"res://test-artifacts/native-crowd/effect-resource-allocation.json")
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		_fail("report opens: " + output)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("effect resource allocation probe: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures,
		" report=", output)
	_stage.free()
	quit(_failures)


func _measure_case(effect: int, power: int, variant: String,
		sample_count: int) -> Dictionary:
	# Capture first-use separately. The held population below represents steady
	# burst creation and makes per-instance versus shared resource identity clear.
	var cold := _spawn_one(effect, power, variant)
	var cold_node: Node = cold["node"]
	cold_node.free()
	await process_frame
	await process_frame
	var instantiate_samples: Array[float] = []
	var attach_samples: Array[float] = []
	var configure_samples: Array[float] = []
	var area_samples: Array[float] = []
	var nodes: Array[Node] = []
	var identities := {}
	var before := _snapshot()
	for sample: int in sample_count:
		var result := _spawn_one(effect, power, variant)
		instantiate_samples.append(float(result["instantiateMicroseconds"]))
		attach_samples.append(float(result["attachMicroseconds"]))
		configure_samples.append(float(result["configureMicroseconds"]))
		area_samples.append(float(result["areaMicroseconds"]))
		var node: Node = result["node"]
		nodes.append(node)
		_collect_identities(node, identities)
	await process_frame
	var live := _snapshot()
	var live_node_count := nodes.size()
	for node: Node in nodes:
		node.free()
	nodes.clear()
	await process_frame
	await process_frame
	var after_free := _snapshot()
	return {
		"effect": effect,
		"power": power,
		"variant": variant,
		"samples": sample_count,
		"coldFirst": cold["timing"],
		"steady": {
			"instantiateMicroseconds": _distribution(instantiate_samples),
			"attachMicroseconds": _distribution(attach_samples),
			"configureMicroseconds": _distribution(configure_samples),
			"configureAreaMicroseconds": _distribution(area_samples),
		},
		"population": {
			"heldNodes": live_node_count,
			"before": before,
			"live": live,
			"afterFree": after_free,
			"liveMinusBefore": _subtract_snapshot(live, before),
			"afterFreeMinusBefore": _subtract_snapshot(after_free, before),
		},
		"uniqueResourceIdentities": _identity_counts(identities),
	}


func _spawn_one(effect: int, power: int, variant: String) -> Dictionary:
	var started := Time.get_ticks_usec()
	var node: Node3D = Effect.new()
	var instantiate_usec := Time.get_ticks_usec() - started
	node.set_process(false)
	started = Time.get_ticks_usec()
	_stage.add_child(node)
	var attach_usec := Time.get_ticks_usec() - started
	var target: Variant = Vector3(11.0, 1.5, -7.0) if variant == "flight" else null
	started = Time.get_ticks_usec()
	node.call("configure", effect, Vector3.ZERO, target, power)
	var configure_usec := Time.get_ticks_usec() - started
	var area_usec := 0
	if variant == "area":
		started = Time.get_ticks_usec()
		node.call("configure_area", 5.75, "burst")
		area_usec = Time.get_ticks_usec() - started
	return {
		"node": node,
		"instantiateMicroseconds": instantiate_usec,
		"attachMicroseconds": attach_usec,
		"configureMicroseconds": configure_usec,
		"areaMicroseconds": area_usec,
		"timing": {
			"instantiateMicroseconds": instantiate_usec,
			"attachMicroseconds": attach_usec,
			"configureMicroseconds": configure_usec,
			"configureAreaMicroseconds": area_usec,
		},
	}


func _measure_draw_workloads() -> Dictionary:
	var effects: Array[Node] = []
	for effect: int in EFFECTS:
		var row := _spawn_one(effect, 10, "flight")
		effects.append(row["node"] as Node)
	_draw_details_workload(effects, 1)
	_draw_flight_workload(effects, 1)
	var detail_samples: Array[float] = []
	var flight_samples: Array[float] = []
	var orders: Array[Array] = []
	for trial: int in DRAW_TRIALS:
		var order: Array = ["details", "flight"] if trial % 2 == 0 \
			else ["flight", "details"]
		orders.append(order.duplicate())
		for workload: String in order:
			var started := Time.get_ticks_usec()
			if workload == "details":
				_draw_details_workload(effects, DRAW_CYCLES)
				detail_samples.append(float(Time.get_ticks_usec() - started))
			else:
				_draw_flight_workload(effects, DRAW_CYCLES)
				flight_samples.append(float(Time.get_ticks_usec() - started))
	for node: Node in effects:
		node.free()
	return {
		"effectIds": EFFECTS,
		"power": 10,
		"detailPhases": DRAW_PHASES,
		"flightProgressPhases": FLIGHT_PHASES,
		"cyclesPerTrial": DRAW_CYCLES,
		"trials": DRAW_TRIALS,
		"orders": orders,
		"detailCallsPerTrial": EFFECTS.size() * DRAW_PHASES.size() * DRAW_CYCLES,
		"flightCallsPerTrial": EFFECTS.size() * FLIGHT_PHASES.size() * DRAW_CYCLES,
		"detailsMicroseconds": _distribution(detail_samples),
		"flightMicroseconds": _distribution(flight_samples),
	}


func _draw_details_workload(effects: Array[Node], cycles: int) -> void:
	for cycle: int in cycles:
		for node: Node in effects:
			for phase: float in DRAW_PHASES:
				node.set("elapsed", phase * 1.1 + cycle * 0.001)
				node.call("_draw_details", phase)


func _draw_flight_workload(effects: Array[Node], cycles: int) -> void:
	for cycle: int in cycles:
		for node: Node in effects:
			var flight: Node = node.get("flight")
			var duration := float(flight.get("duration"))
			for phase: float in FLIGHT_PHASES:
				var time := phase if phase < 0.0 else duration * phase
				flight.call("draw_at", time + cycle * 0.00001)


func _collect_identities(node: Node, identities: Dictionary) -> void:
	var ring: MeshInstance3D = node.get("_ring")
	var details: Resource = node.get("_detail_material")
	var burst: GPUParticles3D = node.get("_burst")
	var ring_mesh := ring.mesh as TorusMesh
	var ring_surface_material: Material = ring_mesh.material
	var ring_effective_material: Material = ring.material_override \
		if ring.material_override != null else ring_surface_material
	_add_identity(identities, "ringMesh", ring_mesh)
	_add_identity(identities, "ringSurfaceMaterial", ring_surface_material)
	_add_identity(identities, "ringOverrideMaterial", ring.material_override)
	_add_identity(identities, "ringEffectiveMaterial", ring_effective_material)
	_add_identity(identities, "ringInstanceMaterial", node.get("_material"))
	_add_identity(identities, "detailMaterial", details)
	var process := burst.process_material as ParticleProcessMaterial
	_add_identity(identities, "particleProcessMaterial", process)
	_add_identity(identities, "particleColorRamp", process.color_ramp)
	var quad := burst.draw_pass_1 as QuadMesh
	_add_identity(identities, "particleQuad", quad)
	var dot := quad.material as StandardMaterial3D
	_add_identity(identities, "particleDrawMaterial", dot)
	_add_identity(identities, "particleDotTexture", dot.albedo_texture)
	var flight: Node = node.get("flight")
	if flight != null:
		_add_identity(identities, "flightRibbonMaterial", flight.get("_ribbon_material"))
		_add_identity(identities, "flightGlowMaterial", flight.get("_glow_material"))


func _add_identity(identities: Dictionary, label: String, value: Variant) -> void:
	if value == null or not value is Object:
		return
	if not identities.has(label):
		identities[label] = {}
	(identities[label] as Dictionary)[(value as Object).get_instance_id()] = true


func _identity_counts(identities: Dictionary) -> Dictionary:
	var result := {}
	for label: String in identities:
		result[label] = (identities[label] as Dictionary).size()
	return result


func _snapshot() -> Dictionary:
	return {
		"objectCount": int(Performance.get_monitor(Performance.OBJECT_COUNT)),
		"nodeCount": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
		"resourceCount": int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT)),
		"orphanNodeCount": int(Performance.get_monitor(
			Performance.OBJECT_ORPHAN_NODE_COUNT)),
		"staticMemoryBytes": int(Performance.get_monitor(Performance.MEMORY_STATIC)),
	}


func _subtract_snapshot(left: Dictionary, right: Dictionary) -> Dictionary:
	var result := {}
	for key: String in left:
		result[key] = int(left[key]) - int(right.get(key, 0))
	return result


func _distribution(values: Array[float]) -> Dictionary:
	var sorted := values.duplicate()
	sorted.sort()
	var total := 0.0
	for value: float in sorted:
		total += value
	return {
		"count": sorted.size(),
		"mean": total / sorted.size(),
		"median": _percentile(sorted, 0.5),
		"p95": _percentile(sorted, 0.95),
		"max": sorted[-1],
		"raw": values,
	}


func _percentile(sorted: Array[float], fraction: float) -> float:
	var index := clampi(ceili(sorted.size() * fraction) - 1, 0, sorted.size() - 1)
	return sorted[index]


func _fail(message: String) -> void:
	_failures += 1
	push_error("FAIL: " + message)
