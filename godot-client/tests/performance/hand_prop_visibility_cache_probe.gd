extends SceneTree
## Exact hand-prop visibility parity and complete combat-pose callback timing for
## the fitted-weapon classification cache. Timing remains diagnostic.

const FrozenActor = preload(
	"res://tests/fixtures/replicated_actor_hand_props_90b0_baseline.gd")
const TraceFrozenActor = preload(
	"res://tests/fixtures/replicated_actor_hand_props_90b0_trace.gd")
const BASELINE_COMMIT := "66f575ffe14f23153caa4920b2bfb47ccbc4f219"
const BASELINE_METHOD_SHA256 := \
	"f94a9c970d26c257853df0bf4766281654dc04d3bf48c4d469774f027c22e6fd"
const MELEE_WEAPON := 114
const MELEE_SHIELD := 106
const RANGED_WEAPON := 164
const RANGED_SHIELD := 111
const LEGACY_RANGED_WEAPON := 64
const TRIALS := 7
const DEFAULT_ITERATIONS := 600
const TIMED_SCENARIOS := [
	"idle_bow", "ranged_hold", "casting", "melee",
	"effects_disabled_casting",
]

class TraceCandidateActor extends ReplicatedActor3D:
	var trace_enabled := false
	var equipment_model_lookups := 0

	func reset_hand_prop_trace() -> void:
		equipment_model_lookups = 0

	func hand_prop_trace() -> Dictionary:
		return {"equipmentModelLookups": equipment_model_lookups}

	func _equipment_model_config(part: int, visual_id: int) -> Dictionary:
		if trace_enabled:
			equipment_model_lookups += 1
		return super._equipment_model_config(part, visual_id)

var _failures := 0
var _models: Dictionary
var _animations: Dictionary
var _equipment: Dictionary
var _adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
var _next_actor_id := 90100


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(960, 540)
	_models = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))
	_animations = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/animations/luminous.json"))
	_equipment = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	_check(_models is Dictionary and _animations is Dictionary \
		and _equipment is Dictionary, "configuration files parse")
	_check_baseline_provenance()

	var fixtures: Array[Dictionary] = []
	var melee_pair := _spawn_pair(MELEE_WEAPON, MELEE_SHIELD)
	var ranged_pair := _spawn_pair(RANGED_WEAPON, RANGED_SHIELD)
	var legacy_pair := _spawn_pair(LEGACY_RANGED_WEAPON, 0)
	var shield_pair := _spawn_pair(0, MELEE_SHIELD)
	var trace_melee_pair := _spawn_pair(MELEE_WEAPON, MELEE_SHIELD, true)
	var trace_ranged_pair := _spawn_pair(RANGED_WEAPON, RANGED_SHIELD, true)
	var trace_legacy_pair := _spawn_pair(LEGACY_RANGED_WEAPON, 0, true)
	var trace_shield_pair := _spawn_pair(0, MELEE_SHIELD, true)
	fixtures.append_array(melee_pair)
	fixtures.append_array(ranged_pair)
	fixtures.append_array(legacy_pair)
	fixtures.append_array(shield_pair)
	fixtures.append_array(trace_melee_pair)
	fixtures.append_array(trace_ranged_pair)
	fixtures.append_array(trace_legacy_pair)
	fixtures.append_array(trace_shield_pair)
	await process_frame

	var parity: Dictionary = {}
	_check_direct_visibility_pair(melee_pair, "melee", false, parity)
	_check_direct_visibility_pair(ranged_pair, "ranged", true, parity)
	_check_direct_visibility_pair(legacy_pair, "legacy_attach_bow", false, parity)
	_check_direct_visibility_pair(shield_pair, "shield_only", false, parity)
	_check_empty_and_shield_fast_paths(trace_legacy_pair, trace_shield_pair,
		parity)
	_check_new_node_reset(melee_pair, false, "melee new prop", parity)
	_check_new_node_reset(ranged_pair, true, "ranged new prop", parity)
	_check_swap_clear_equivalent(ranged_pair, parity)

	var reconfigure_pair := _spawn_pair(MELEE_WEAPON, MELEE_SHIELD)
	fixtures.append_array(reconfigure_pair)
	await process_frame
	await _check_reconfigure(reconfigure_pair, parity)

	var timed_pairs := {
		"idle_bow": ranged_pair,
		"ranged_hold": ranged_pair,
		"casting": melee_pair,
		"melee": melee_pair,
		"effects_disabled_casting": melee_pair,
	}
	var trace_pairs := {
		"idle_bow": trace_ranged_pair,
		"ranged_hold": trace_ranged_pair,
		"casting": trace_melee_pair,
		"melee": trace_melee_pair,
		"effects_disabled_casting": trace_melee_pair,
	}
	var timed_snapshots: Dictionary = {}
	for scenario: String in TIMED_SCENARIOS:
		var pair: Array = timed_pairs[scenario]
		_prepare_scenario(pair[0], scenario)
		_prepare_scenario(pair[1], scenario)
		var expected := _snapshot(pair[0])
		var actual := _snapshot(pair[1])
		_check(expected == actual, scenario + " warm callback output matches frozen")
		timed_snapshots[scenario] = {
			"frozen": expected,
			"candidate": actual,
			"sha256": _variant_sha256(actual),
		}

	var iterations := DEFAULT_ITERATIONS
	var requested := OS.get_environment("ELORIA_HAND_PROP_ITERATIONS")
	if not requested.is_empty():
		iterations = maxi(1, int(requested))
	for scenario: String in TIMED_SCENARIOS:
		for fixture: Dictionary in timed_pairs[scenario]:
			_prepare_scenario(fixture, scenario)
			_bench(fixture, 12)
	var trials: Array[Dictionary] = []
	for trial: int in TRIALS:
		var order := ["frozen", "candidate"] if trial % 2 == 0 \
			else ["candidate", "frozen"]
		var row: Dictionary = {"trial": trial + 1,
			"order": order.duplicate(), "scenarios": {}}
		for scenario: String in TIMED_SCENARIOS:
			var pair: Array = timed_pairs[scenario]
			var scenario_row: Dictionary = {}
			for implementation: String in order:
				var fixture: Dictionary = pair[0] if implementation == "frozen" \
					else pair[1]
				_prepare_scenario(fixture, scenario)
				var started := Time.get_ticks_usec()
				_bench(fixture, iterations)
				var elapsed := Time.get_ticks_usec() - started
				scenario_row[implementation] = {
					"totalMicroseconds": elapsed,
					"iterations": iterations,
					"microsecondsPerCallback": float(elapsed) / iterations,
				}
			(row.scenarios as Dictionary)[scenario] = scenario_row
		trials.append(row)

	var trace_counts: Dictionary = {}
	for scenario: String in TIMED_SCENARIOS:
		var pair: Array = trace_pairs[scenario]
		var row: Dictionary = {}
		for implementation: String in ["frozen", "candidate"]:
			var fixture: Dictionary = pair[0] if implementation == "frozen" \
				else pair[1]
			_prepare_scenario(fixture, scenario)
			_reset_trace(fixture)
			_set_trace(fixture, true)
			_bench(fixture, 1)
			_set_trace(fixture, false)
			row[implementation] = _trace(fixture)
		trace_counts[scenario] = row
		var candidate_trace := row.candidate as Dictionary
		_check(int(candidate_trace.equipmentModelLookups) == 0,
			scenario + " warm candidate callback performs no fitted model lookup")
	var summary := _summarize(trials)
	var report := {
		"schemaVersion": 1,
		"status": "PASS" if _failures == 0 else "FAIL",
		"failures": _failures,
		"timingAssertions": false,
		"rotatedOrder": true,
		"timingScope": ("complete CombatPresentation3D.update_pose callback; "
			+ "includes hand-prop visibility assignment and all presentation work, "
			+ "excludes skeleton evaluation and signal dispatch"),
		"sourceBasis": {
			"baselineCommit": BASELINE_COMMIT,
			"baselineMethodSha256": BASELINE_METHOD_SHA256,
			"comparison": "frozen 90b0 hand-prop accessor versus cached production accessor",
			"frozenLookupEvidence": ("exact frozen source resolves one fitted "
				+ "main-hand model per valid hand prop; tracing is kept out of both "
				+ "timed implementations"),
		},
		"sourceHashes": {
			"actor": FileAccess.get_sha256(
				"res://src/actors/replicated_actor_3d.gd"),
			"frozenAccessor": FileAccess.get_sha256(
				"res://tests/fixtures/replicated_actor_hand_props_90b0_baseline.gd"),
			"frozenTraceAccessor": FileAccess.get_sha256(
				"res://tests/fixtures/replicated_actor_hand_props_90b0_trace.gd"),
			"probe": FileAccess.get_sha256(
				"res://tests/performance/hand_prop_visibility_cache_probe.gd"),
		},
		"workload": {"trials": TRIALS,
			"iterationsPerScenarioPerImplementation": iterations,
			"scenarios": TIMED_SCENARIOS.duplicate()},
		"parity": parity,
		"timedSnapshots": timed_snapshots,
		"untimedLookupTrace": trace_counts,
		"summary": summary,
		"trials": trials,
	}
	var path := OS.get_environment("ELORIA_HAND_PROP_REPORT")
	if path.is_empty():
		var artifact_dir := OS.get_environment("ELORIA_ARTIFACT_DIR")
		path = artifact_dir.path_join("hand-prop-visibility-cache-probe.json") \
			if not artifact_dir.is_empty() else ProjectSettings.globalize_path(
				"res://test-artifacts/native-crowd/hand-prop-visibility-cache-probe.json")
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("report file opens: " + path)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	for fixture: Dictionary in fixtures:
		var actor := fixture.actor as ReplicatedActor3D
		if is_instance_valid(actor):
			actor.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("hand prop visibility cache probe: ", "PASS" if _failures == 0 \
		else "FAIL (%d)" % _failures, " report=", path)
	quit(_failures)


func _spawn_pair(weapon: int, off_hand: int,
		traced := false) -> Array[Dictionary]:
	return [_spawn(true, weapon, off_hand, traced),
		_spawn(false, weapon, off_hand, traced)]


func _spawn(frozen: bool, weapon: int, off_hand: int,
		traced: bool) -> Dictionary:
	var actor: ReplicatedActor3D
	if frozen:
		actor = TraceFrozenActor.new() if traced else FrozenActor.new()
	else:
		actor = TraceCandidateActor.new() if traced else ReplicatedActor3D.new()
	root.add_child(actor)
	_next_actor_id += 1
	var visuals := {0: weapon, 5: 184}
	if off_hand > 0:
		visuals[1] = off_hand
	var dto := {"actor_id": _next_actor_id, "x": 0, "y": 0, "rotation": 0,
		"appearance": {}, "equipment_visuals": visuals, "in_combat": true}
	var model: Dictionary = _models.models["luminous_male"]
	var errors := actor.configure(dto, _adapter, model, _animations, _equipment)
	_check(errors.is_empty(), "actor %d configures: %s" % [_next_actor_id, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	var presentation := actor.combat_presentation
	_check(presentation != null, "actor %d has combat presentation" % _next_actor_id)
	var skeleton := actor.get_skeleton()
	if skeleton != null and presentation != null:
		var callback := Callable(presentation, "update_pose")
		if skeleton.skeleton_updated.is_connected(callback):
			skeleton.skeleton_updated.disconnect(callback)
	return {"actor": actor, "presentation": presentation,
		"implementation": "frozen" if frozen else "candidate"}


func _check_direct_visibility_pair(pair: Array, label: String,
		ranged_main_hand: bool, rows: Dictionary) -> void:
	var states: Array[Dictionary] = []
	for enabled: bool in [false, true, true]:
		if enabled and states.size() == 2:
			# Repeating the same public value must repair external node changes.
			_force_prop_visibility(pair[0], false)
			_force_prop_visibility(pair[1], false)
		for fixture: Dictionary in pair:
			(fixture.actor as ReplicatedActor3D).set_hand_props_visible(enabled)
		var expected := _hand_prop_snapshot(pair[0].actor)
		var actual := _hand_prop_snapshot(pair[1].actor)
		_check(expected == actual, label + " direct visibility parity")
		states.append({"enabled": enabled, "snapshot": actual})
	var final_snapshot := states[-1].snapshot as Array
	for prop: Dictionary in final_snapshot:
		var expected_visible := not (ranged_main_hand and int(prop.part) == 0)
		_check(bool(prop.visible) == expected_visible,
			label + " part %d visibility is correct" % int(prop.part))
	rows[label] = states


func _check_new_node_reset(pair: Array, ranged: bool, label: String,
		rows: Dictionary) -> void:
	var snapshots: Array = []
	for fixture: Dictionary in pair:
		var actor := fixture.actor as ReplicatedActor3D
		actor.set_hand_props_visible(true)
		var prop := Node3D.new()
		prop.name = "SyntheticLateMainHandProp"
		prop.visible = not ranged
		actor.add_child(prop)
		var nodes := actor.get("_equipment_nodes") as Dictionary
		var main_hand := (nodes.get(0, []) as Array).duplicate()
		main_hand.append(prop)
		nodes[0] = main_hand
		# Use the same requested value again: the new node must still be assigned.
		prop.visible = ranged
		actor.set_hand_props_visible(true)
		snapshots.append(_hand_prop_snapshot(actor))
	_check(snapshots[0] == snapshots[1], label + " output matches frozen")
	var late: Dictionary = {}
	for row: Dictionary in snapshots[1]:
		if str(row.name) == "SyntheticLateMainHandProp":
			late = row
			break
	_check(str(late.get("name", "")) == "SyntheticLateMainHandProp" \
		and bool(late.visible) == not ranged,
		label + " is reset on repeated public visibility call")
	rows[label] = snapshots[1]


func _check_empty_and_shield_fast_paths(legacy_pair: Array,
		shield_pair: Array, rows: Dictionary) -> void:
	var result: Dictionary = {}
	for entry: Dictionary in [
		{"id": "legacy_no_props", "fixture": legacy_pair[1]},
		{"id": "shield_only", "fixture": shield_pair[1]},
	]:
		var fixture := entry.fixture as Dictionary
		_reset_trace(fixture)
		_set_trace(fixture, true)
		(fixture.actor as ReplicatedActor3D).set_hand_props_visible(true)
		_set_trace(fixture, false)
		var trace := _trace(fixture)
		_check(int(trace.equipmentModelLookups) == 0,
			str(entry.id) + " performs no main-hand model lookup")
		result[entry.id] = {"trace": trace,
			"snapshot": _hand_prop_snapshot(fixture.actor)}
	rows["emptyAndShieldFastPaths"] = result


func _check_swap_clear_equivalent(pair: Array, rows: Dictionary) -> void:
	var sequence: Array[Dictionary] = []
	for step: Dictionary in [
		{"id": "ranged", "visuals": {0: RANGED_WEAPON, 1: RANGED_SHIELD, 5: 184}},
		{"id": "equivalent_ranged", "visuals": {0: RANGED_WEAPON, 1: RANGED_SHIELD, 5: 184}},
		{"id": "melee", "visuals": {0: MELEE_WEAPON, 1: MELEE_SHIELD, 5: 184}},
		{"id": "clear", "visuals": {}},
		{"id": "legacy", "visuals": {0: LEGACY_RANGED_WEAPON, 5: 184}},
	]:
		for fixture: Dictionary in pair:
			(fixture.actor as ReplicatedActor3D).apply_equipment_visuals(
				step.visuals as Dictionary)
			(fixture.actor as ReplicatedActor3D).set_hand_props_visible(true)
		var expected := _hand_prop_snapshot(pair[0].actor)
		var actual := _hand_prop_snapshot(pair[1].actor)
		_check(expected == actual, "swap sequence " + str(step.id) + " parity")
		sequence.append({"id": step.id, "snapshot": actual})
	rows["swapClearEquivalent"] = sequence


func _check_reconfigure(pair: Array, rows: Dictionary) -> void:
	var altered_equipment := _equipment.duplicate(true)
	var models := altered_equipment.models as Dictionary
	var melee := (models["0:114"] as Dictionary).duplicate(true)
	var variants := (melee.get("variants", {}) as Dictionary).duplicate(true)
	variants["canonical_human_female"] = {
		"rangedAnimationScene":
			"res://assets/actors/native/equipment/amberwood_ranger_bow.glb",
	}
	melee["variants"] = variants
	models["0:114"] = melee
	var snapshots: Array = []
	for fixture: Dictionary in pair:
		var actor := fixture.actor as ReplicatedActor3D
		_next_actor_id += 1
		var dto := {"actor_id": _next_actor_id, "x": 0, "y": 0,
			"rotation": 0, "appearance": {},
			"equipment_visuals": {0: MELEE_WEAPON, 1: MELEE_SHIELD, 5: 184},
			"in_combat": true}
		var errors := actor.configure(dto, _adapter,
			_models.models["luminous_female"] as Dictionary,
			_animations, altered_equipment)
		_check(errors.is_empty(), "reconfigured actor loads: %s" % [errors])
		actor.set_hand_props_visible(true)
		snapshots.append(_hand_prop_snapshot(actor))
	_check(snapshots[0] == snapshots[1], "registry/rig reconfigure parity")
	var main_hand_seen := false
	for prop: Dictionary in snapshots[1]:
		if int(prop.part) == 0:
			main_hand_seen = true
			_check(not bool(prop.visible),
				"reconfigured fitted ranged variant hides main hand prop")
	_check(main_hand_seen, "reconfigure retains a main hand prop to classify")
	rows["reconfigureFittedVariant"] = snapshots[1]
	await process_frame


func _prepare_scenario(fixture: Dictionary, scenario: String) -> void:
	var actor := fixture.actor as ReplicatedActor3D
	var presentation: Node = fixture.presentation
	actor.show()
	presentation.set("effects_enabled", scenario != "effects_disabled_casting")
	match scenario:
		"idle_bow":
			_ensure_equipment(actor, RANGED_WEAPON, RANGED_SHIELD)
			_seek(actor, &"idle", 0.20)
		"ranged_hold":
			_ensure_equipment(actor, RANGED_WEAPON, RANGED_SHIELD)
			_seek(actor, &"ranged_hold", 0.55)
		"casting", "effects_disabled_casting":
			_ensure_equipment(actor, MELEE_WEAPON, MELEE_SHIELD)
			_seek(actor, &"cast_aggressive", 0.43)
		"melee":
			_ensure_equipment(actor, MELEE_WEAPON, MELEE_SHIELD)
			_seek(actor, &"attack_primary", 0.30)
		_:
			_fail("unknown timing scenario " + scenario)
	presentation.set("_last_action", StringName())
	presentation.set("_last_time", -1.0)
	presentation.call("update_pose")


func _ensure_equipment(actor: ReplicatedActor3D, weapon: int,
		off_hand: int) -> void:
	var visuals := {0: weapon, 5: 184}
	if off_hand > 0:
		visuals[1] = off_hand
	actor.apply_equipment_visuals(visuals)


func _seek(actor: ReplicatedActor3D, action: StringName, time: float) -> void:
	actor.play_action(action, true)
	actor.animation_player.advance(0.0)
	actor.animation_player.seek(time, true)
	actor.animation_player.pause()


func _bench(fixture: Dictionary, iterations: int) -> void:
	var presentation: Node = fixture.presentation
	for iteration: int in iterations:
		presentation.call("update_pose")


func _snapshot(fixture: Dictionary) -> Dictionary:
	var presentation: Node = fixture.presentation
	var bow := presentation.get("bow") as Node3D
	return {
		"handProps": _hand_prop_snapshot(fixture.actor),
		"bowVisible": bow != null and bow.visible,
		"effectsEnabled": bool(presentation.get("effects_enabled")),
	}


func _hand_prop_snapshot(actor_value: Variant) -> Array:
	var actor := actor_value as ReplicatedActor3D
	var rows: Array = []
	var nodes := actor.get("_equipment_nodes") as Dictionary
	for part: int in [0, 1]:
		for value: Variant in nodes.get(part, []):
			if value is Node3D and is_instance_valid(value):
				var node := value as Node3D
				rows.append({"part": part, "name": str(node.name),
					"visible": node.visible})
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return (str(a.part) + ":" + str(a.name)) < \
			(str(b.part) + ":" + str(b.name)))
	return rows


func _force_prop_visibility(fixture: Dictionary, visible: bool) -> void:
	var actor := fixture.actor as ReplicatedActor3D
	var nodes := actor.get("_equipment_nodes") as Dictionary
	for part: int in [0, 1]:
		for value: Variant in nodes.get(part, []):
			if value is Node3D and is_instance_valid(value):
				(value as Node3D).visible = visible


func _reset_trace(fixture: Dictionary) -> void:
	var actor := fixture.actor as Node
	if actor.has_method("reset_hand_prop_trace"):
		actor.call("reset_hand_prop_trace")


func _set_trace(fixture: Dictionary, enabled: bool) -> void:
	var actor := fixture.actor as Node
	if "trace_enabled" in actor:
		actor.set("trace_enabled", enabled)


func _trace(fixture: Dictionary) -> Dictionary:
	var actor := fixture.actor as Node
	return actor.call("hand_prop_trace") as Dictionary \
		if actor.has_method("hand_prop_trace") else {
			"equipmentModelLookups": null}


func _summarize(trials: Array[Dictionary]) -> Dictionary:
	var result: Dictionary = {}
	for scenario: String in TIMED_SCENARIOS:
		var row: Dictionary = {}
		for implementation: String in ["frozen", "candidate"]:
			var values: Array[float] = []
			for trial: Dictionary in trials:
				values.append(float(((trial.scenarios as Dictionary)[scenario]
					as Dictionary)[implementation].microsecondsPerCallback))
			values.sort()
			row[implementation] = {
				"medianMicrosecondsPerCallback": _percentile(values, 0.5),
				"p95MicrosecondsPerCallback": _percentile(values, 0.95),
				"minimumMicrosecondsPerCallback": values[0],
				"maximumMicrosecondsPerCallback": values[-1],
			}
		row["candidateVersusFrozenMedianPercent"] = (
			float(row.candidate.medianMicrosecondsPerCallback) /
			maxf(0.000001, float(row.frozen.medianMicrosecondsPerCallback)) - 1.0
		) * 100.0
		result[scenario] = row
	return result


func _percentile(sorted: Array[float], fraction: float) -> float:
	var position := fraction * (sorted.size() - 1)
	var lower := floori(position)
	var upper := ceili(position)
	return lerpf(sorted[lower], sorted[upper], position - lower)


func _check_baseline_provenance() -> void:
	var source := FileAccess.get_file_as_string(
		"res://tests/fixtures/replicated_actor_hand_props_90b0_baseline.gd")
	var body_at := source.find("func set_hand_props_visible")
	var body_end := source.find("# END FROZEN METHOD", body_at)
	_check(body_at >= 0, "frozen accessor contains baseline method")
	_check(body_end > body_at, "frozen accessor marks baseline method end")
	if body_at < 0 or body_end <= body_at:
		return
	var digest := _text_sha256(source.substr(
		body_at, body_end - body_at).replace("\r\n", "\n"))
	_check(digest == BASELINE_METHOD_SHA256,
		"frozen 90b0 hand-prop method matches reviewed SHA-256")


func _variant_sha256(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(value))
	return context.finish().hex_encode()


func _text_sha256(value: String) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(value.to_utf8_buffer())
	return context.finish().hex_encode()


func _check(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	_failures += 1
	push_error("FAIL: " + message)
