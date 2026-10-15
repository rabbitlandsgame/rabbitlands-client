extends SceneTree
## Exact frozen/current presentation parity plus focused full-callback timings.
## Timing is diagnostic only. Mesh readback and snapshot hashing stay outside
## timed regions.

const FrozenPresentation = preload(
	"res://tests/fixtures/combat_presentation_967744_baseline.gd")
const FrozenBow = preload(
	"res://tests/fixtures/ranger_bow_pose_967744_baseline.gd")
const CandidateBow = preload(
	"res://tests/fixtures/ranger_bow_pose_cache_candidate.gd")
const BASELINE_COMMIT := "ef6825b92a468ff275a847cc063eed115695b1b5"
const BASELINE_BODY_SHA256 := "27484eab2c764c01154ee38d7edc46410bd2aebf13b56979e4e768bc40688a4f"
const BASELINE_BOW_FILE_SHA256 := "89d5a919f5e4ed9dfbf2089537912d44afda15927510c7dbf73b5b88347d9aef"
const MELEE_WEAPON := 114
const RANGED_WEAPON := 164
const RANGED_SHIELD := 111
const LEGACY_RANGED_WEAPON := 64
const RANGED_BOW := "res://assets/actors/native/equipment/amberwood_ranger_bow.glb"
const TRIALS := 8
const DEFAULT_ITERATIONS := 600
const TIMED_SCENARIOS := ["idle_no_cue", "idle_bow", "melee",
	"ranged_hold", "casting"]
const PARITY_SCENARIOS := [
	"idle_no_cue", "idle_bow", "cast", "cast_channel_enter", "cast_channel",
	"cast_aggressive", "cast_defensive", "heal", "attack_primary",
	"attack_secondary", "ranged_draw", "ranged_hold", "ranged_attack",
	"effects_disabled_casting", "hidden_casting", "melee_rewind",
	"transition_cast_to_idle", "transition_ranged_to_idle",
	"equipment_bow_to_sword", "legacy_ranged_hold",
]

class TraceActor extends ReplicatedActor3D:
	var trace_enabled := false
	var skeleton_gets := 0
	var equipment_model_lookups := 0
	var hand_prop_calls := 0
	var hand_prop_nodes_visited := 0
	var hand_prop_visibility_changes := 0

	func reset_trace() -> void:
		skeleton_gets = 0
		equipment_model_lookups = 0
		hand_prop_calls = 0
		hand_prop_nodes_visited = 0
		hand_prop_visibility_changes = 0

	func get_skeleton() -> Skeleton3D:
		if trace_enabled:
			skeleton_gets += 1
		return super.get_skeleton()

	func _equipment_model_config(part: int, visual_id: int) -> Dictionary:
		if trace_enabled:
			equipment_model_lookups += 1
		return super._equipment_model_config(part, visual_id)

	func set_hand_props_visible(enabled: bool) -> void:
		var before: Array[bool] = []
		if trace_enabled:
			hand_prop_calls += 1
			for part: int in [0, 1]:
				for prop: Node in _equipment_nodes.get(part, []):
					if is_instance_valid(prop) and prop is Node3D:
						hand_prop_nodes_visited += 1
						before.append((prop as Node3D).visible)
		super.set_hand_props_visible(enabled)
		if trace_enabled:
			var index := 0
			for part: int in [0, 1]:
				for prop: Node in _equipment_nodes.get(part, []):
					if is_instance_valid(prop) and prop is Node3D:
						hand_prop_visibility_changes += int(
							before[index] != (prop as Node3D).visible)
						index += 1

	func trace_snapshot() -> Dictionary:
		return {"skeletonGets": skeleton_gets,
			"equipmentModelLookups": equipment_model_lookups,
			"handPropCalls": hand_prop_calls,
			"handPropNodesVisited": hand_prop_nodes_visited,
			"handPropVisibilityChanges": hand_prop_visibility_changes}

class FrozenHelperActor extends ReplicatedActor3D:
	# Exact 967744 helper body. This keeps a later actor-side cleanup out of the
	# frozen side of the presentation comparison.
	func set_hand_props_visible(enabled: bool) -> void:
		for part: int in [0, 1]:
			for prop: Node in _equipment_nodes.get(part, []):
				if is_instance_valid(prop) and prop is Node3D:
					var weapon := _equipment_model_config(0,
						int(_equipment_visuals.get(0, 0)))
					(prop as Node3D).visible = enabled and not (
						part == 0 and weapon.has("rangedAnimationScene"))

var _failures := 0
var _detached_presentations: Array[Node] = []
var _models: Dictionary
var _animation_config: Dictionary
var _equipment: Dictionary
var _adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
var _candidate_enabled := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(960, 540)
	_candidate_enabled = OS.get_environment("ELORIA_COMBAT_POSE_CANDIDATE") == "1"
	_check_baseline_provenance()
	_models = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))
	_animation_config = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/animations/luminous.json"))
	_equipment = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	var current_melee := _spawn(false, MELEE_WEAPON, 97001)
	var frozen_melee := _spawn(true, MELEE_WEAPON, 97002)
	var current_ranged := _spawn(false, RANGED_WEAPON, 97003)
	var frozen_ranged := _spawn(true, RANGED_WEAPON, 97004)
	var trace_melee := _spawn(false, MELEE_WEAPON, 97005, true)
	var trace_ranged := _spawn(false, RANGED_WEAPON, 97006, true)
	var current_legacy := _spawn(false, LEGACY_RANGED_WEAPON, 97007)
	var frozen_legacy := _spawn(true, LEGACY_RANGED_WEAPON, 97008)
	await process_frame
	var dynamic_bow := _check_dynamic_bow_sequence()
	var timed_pairs := {
		"idle_no_cue": [frozen_melee, current_melee],
		"idle_bow": [frozen_ranged, current_ranged],
		"melee": [frozen_melee, current_melee],
		"casting": [frozen_melee, current_melee],
		"ranged_hold": [frozen_ranged, current_ranged],
	}
	var parity_pairs: Dictionary = {}
	for scenario: String in PARITY_SCENARIOS:
		parity_pairs[scenario] = [frozen_legacy, current_legacy] \
			if scenario == "legacy_ranged_hold" else (
			[frozen_ranged, current_ranged] \
			if scenario.begins_with("ranged_") \
			or scenario == "transition_ranged_to_idle" \
			or scenario == "equipment_bow_to_sword" \
			else [frozen_melee, current_melee])
	var snapshots: Dictionary = {}
	for scenario: String in parity_pairs:
		var pair: Array = parity_pairs[scenario]
		_prepare_scenario(pair[0], scenario)
		_prepare_scenario(pair[1], scenario)
		var expected := _snapshot(pair[0], scenario)
		var actual := _snapshot(pair[1], scenario)
		_compare_snapshot(expected, actual, scenario)
		_validate_scenario_output(actual, scenario)
		snapshots[scenario] = {
			"frozenSha256": _variant_sha256(expected),
			"currentSha256": _variant_sha256(actual),
			"actionSurfaceVertices": _surface_vertex_count(
				(actual as Dictionary)["actionSurfaces"] as Array),
			"bowStringVertices": _surface_vertex_count(
				(actual as Dictionary)["bowStringSurfaces"] as Array),
			"trailPoints": ((actual as Dictionary)["trail"] as Array).size(),
		}
	var trace_counts: Dictionary = {}
	for scenario: String in TIMED_SCENARIOS:
		var fixture: Dictionary = trace_ranged \
			if scenario in ["idle_bow", "ranged_hold"] \
			else trace_melee
		_prepare_scenario(fixture, scenario)
		var trace_actor := fixture.actor as TraceActor
		trace_actor.reset_trace()
		trace_actor.trace_enabled = true
		(fixture.presentation as Node).call("update_pose")
		trace_actor.trace_enabled = false
		trace_counts[scenario] = trace_actor.trace_snapshot()
	var iterations := maxi(1, int(OS.get_environment(
		"ELORIA_COMBAT_POSE_ITERATIONS"))) if not OS.get_environment(
		"ELORIA_COMBAT_POSE_ITERATIONS").is_empty() else DEFAULT_ITERATIONS
	# Warm script compilation and resource paths without including them in trials.
	for scenario: String in timed_pairs:
		for fixture: Dictionary in timed_pairs[scenario]:
			_prepare_scenario(fixture, scenario)
			_bench(fixture, 12)
	var trials: Array[Dictionary] = []
	for trial: int in TRIALS:
		var order := ["frozen", "current"] if trial % 2 == 0 \
			else ["current", "frozen"]
		var row: Dictionary = {"trial": trial + 1,
			"order": order.duplicate(), "states": {}}
		for scenario: String in timed_pairs:
			var pair: Array = timed_pairs[scenario]
			var state_results: Dictionary = {}
			for implementation: String in order:
				var fixture: Dictionary = pair[0] if implementation == "frozen" \
					else pair[1]
				_prepare_scenario(fixture, scenario)
				var started := Time.get_ticks_usec()
				_bench(fixture, iterations)
				var elapsed := Time.get_ticks_usec() - started
				state_results[implementation] = {
					"totalMicroseconds": elapsed,
					"iterations": iterations,
					"microsecondsPerCallback": float(elapsed) / iterations,
				}
			(row.states as Dictionary)[scenario] = state_results
		trials.append(row)
	var report := {
		"schemaVersion": 1,
		"status": "PASS" if _failures == 0 else "FAIL",
		"failures": _failures,
		"timingAssertions": false,
		"candidateEnabled": _candidate_enabled,
		"rotatedOrder": true,
		"timingScope": "direct complete CombatPresentation3D.update_pose callback; includes its Godot engine API calls and mesh submission, excludes upstream skeleton evaluation/signal dispatch and all mesh readback",
		"displayServer": DisplayServer.get_name(),
		"renderingMethod": RenderingServer.get_current_rendering_method(),
		"videoAdapter": RenderingServer.get_video_adapter_name(),
		"sourceBasis": {
			"baselineCommit": BASELINE_COMMIT,
			"baselineBodySha256": BASELINE_BODY_SHA256,
			"baselineBowFileSha256": BASELINE_BOW_FILE_SHA256,
			"comparison": "frozen 967744 callback versus current production",
		},
		"sourceHashes": {
			"frozen": FileAccess.get_sha256(
				"res://tests/fixtures/combat_presentation_967744_baseline.gd"),
			"frozenBow": FileAccess.get_sha256(
				"res://tests/fixtures/ranger_bow_pose_967744_baseline.gd"),
			"current": FileAccess.get_sha256(
				"res://src/actors/combat_presentation_3d.gd"),
			"rangerBow": FileAccess.get_sha256(
				"res://src/actors/ranger_bow_3d.gd"),
			"candidateBow": FileAccess.get_sha256(
				"res://tests/fixtures/ranger_bow_pose_cache_candidate.gd"),
			"probe": FileAccess.get_sha256(
				"res://tests/performance/combat_pose_probe.gd"),
		},
		"workload": {
			"trials": TRIALS,
			"iterationsPerStatePerImplementation": iterations,
			"timedStates": timed_pairs.keys(),
			"parityStates": parity_pairs.keys(),
			"meleeSampleTimes": [0.20, 0.26, 0.32, 0.38],
			"castingAction": "cast_aggressive",
			"castingTime": 0.43,
			"castingPower": 7,
			"rangedHoldTime": 0.55,
			"rangedAttackTime": 0.08,
		},
		"callbackCallTrace": trace_counts,
		"dynamicBowSequence": dynamic_bow,
		"snapshots": snapshots,
		"summary": _summarize(trials),
		"trials": trials,
	}
	var path := OS.get_environment("ELORIA_COMBAT_POSE_REPORT")
	if path.is_empty():
		var artifact_dir := OS.get_environment("ELORIA_ARTIFACT_DIR")
		path = artifact_dir.path_join("combat-pose-probe.json") \
			if not artifact_dir.is_empty() else ProjectSettings.globalize_path(
				"res://test-artifacts/native-crowd/combat-pose-probe.json")
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("report file opens: " + path)
	else:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	for fixture: Dictionary in [current_melee, frozen_melee,
			current_ranged, frozen_ranged, trace_melee, trace_ranged,
			current_legacy, frozen_legacy]:
		(fixture.actor as ReplicatedActor3D).free()
	for detached: Node in _detached_presentations:
		if is_instance_valid(detached):
			detached.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("combat pose probe: ", "PASS" if _failures == 0 \
		else "FAIL (%d)" % _failures, " report=", path)
	quit(_failures)


func _spawn(frozen: bool, weapon: int, actor_id: int,
		traced := false) -> Dictionary:
	var actor: ReplicatedActor3D
	if traced:
		actor = TraceActor.new()
	elif frozen:
		actor = FrozenHelperActor.new()
	else:
		actor = ReplicatedActor3D.new()
	root.add_child(actor)
	var visuals := {0: weapon, 5: 184}
	if weapon == MELEE_WEAPON:
		visuals[1] = 106
	elif weapon == RANGED_WEAPON:
		visuals[1] = RANGED_SHIELD
	var dto := {"actor_id": actor_id, "x": 0, "y": 0, "rotation": 0,
		"appearance": {}, "equipment_visuals": visuals, "in_combat": true}
	var model: Dictionary = _models.models["luminous_male"]
	var errors := actor.configure(dto, _adapter, model, _animation_config,
		_equipment)
	_check(errors.is_empty(), "actor %d configures: %s" % [actor_id, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	var skeleton := actor.get_skeleton()
	var production := actor.combat_presentation
	_disconnect_pose(skeleton, production)
	var presentation: Node = production
	if frozen:
		actor.remove_child(production)
		_detached_presentations.append(production)
		presentation = FrozenPresentation.new()
		actor.add_child(presentation)
		presentation.call("configure", actor)
		_disconnect_pose(skeleton, presentation)
		if weapon in [RANGED_WEAPON, LEGACY_RANGED_WEAPON]:
			var frozen_bow := FrozenBow.new()
			presentation.add_child(frozen_bow)
			presentation.set("bow", frozen_bow)
			presentation.call("set_equipped_bow", RANGED_BOW)
	elif _candidate_enabled and weapon in [RANGED_WEAPON, LEGACY_RANGED_WEAPON]:
		var old_bow := presentation.get("bow") as RangerBow3D
		if old_bow != null:
			presentation.remove_child(old_bow)
			old_bow.free()
		var candidate_bow := CandidateBow.new()
		presentation.add_child(candidate_bow)
		presentation.set("bow", candidate_bow)
		presentation.call("set_equipped_bow", RANGED_BOW)
	return {"actor": actor, "presentation": presentation,
		"detached": production if frozen else null,
		"implementation": "frozen" if frozen else "current"}


func _disconnect_pose(skeleton: Skeleton3D, presentation: Node) -> void:
	var callback := Callable(presentation, "update_pose")
	if skeleton.skeleton_updated.is_connected(callback):
		skeleton.skeleton_updated.disconnect(callback)


func _prepare_scenario(fixture: Dictionary, scenario: String) -> void:
	var actor := fixture.actor as ReplicatedActor3D
	var presentation: Node = fixture.presentation
	actor.show()
	presentation.set("effects_enabled", true)
	var ranged_fixture := scenario.begins_with("ranged_") \
		or scenario == "idle_bow" \
		or scenario == "transition_ranged_to_idle" \
		or scenario == "equipment_bow_to_sword"
	_ensure_equipment(fixture, LEGACY_RANGED_WEAPON if scenario == \
		"legacy_ranged_hold" else (RANGED_WEAPON if ranged_fixture \
		else MELEE_WEAPON))
	_reset_presentation(fixture)
	match scenario:
		"idle_no_cue":
			_seek(actor, &"idle", 0.20)
			presentation.call("update_pose")
		"idle_bow":
			_seek(actor, &"idle", 0.20)
			presentation.call("update_pose")
		"melee", "attack_primary", "attack_secondary":
			var action: StringName = &"attack_secondary" \
				if scenario == "attack_secondary" else &"attack_primary"
			_seek(actor, action, 0.20)
			presentation.call("update_pose")
			for time: float in [0.26, 0.32, 0.38]:
				actor.animation_player.seek(time, true)
				presentation.call("update_pose")
		"casting", "cast", "cast_channel_enter", "cast_channel", \
				"cast_aggressive", "cast_defensive", "heal":
			var action: StringName = StringName(scenario) \
				if scenario != "casting" else &"cast_aggressive"
			_seek(actor, action, 0.43)
			presentation.call("set_spell_palette",
				Color(0.22, 0.71, 0.94, 0.85), 7)
			presentation.call("update_pose")
		"ranged_draw", "ranged_hold":
			_seek(actor, StringName(scenario), 0.55)
			presentation.call("update_pose")
		"legacy_ranged_hold":
			_seek(actor, &"ranged_hold", 0.55)
			presentation.call("update_pose")
		"ranged_attack":
			_seek(actor, &"ranged_attack", 0.08)
			presentation.call("update_pose")
		"effects_disabled_casting":
			_seek(actor, &"cast_aggressive", 0.43)
			presentation.set("effects_enabled", false)
			presentation.call("update_pose")
		"hidden_casting":
			_seek(actor, &"cast_aggressive", 0.43)
			actor.hide()
			presentation.call("update_pose")
		"melee_rewind":
			_seek(actor, &"attack_primary", 0.20)
			for time: float in [0.26, 0.32, 0.38]:
				actor.animation_player.seek(time, true)
				presentation.call("update_pose")
			actor.animation_player.seek(0.22, true)
			presentation.call("update_pose")
		"transition_cast_to_idle":
			_seek(actor, &"cast_defensive", 0.43)
			presentation.call("update_pose")
			_seek(actor, &"idle", 0.10)
			presentation.call("update_pose")
		"transition_ranged_to_idle":
			_seek(actor, &"ranged_hold", 0.55)
			presentation.call("update_pose")
			_seek(actor, &"idle", 0.10)
			presentation.call("update_pose")
		"equipment_bow_to_sword":
			_seek(actor, &"ranged_hold", 0.55)
			presentation.call("update_pose")
			_apply_equipment(fixture, {0: MELEE_WEAPON, 1: 106, 5: 184})
			presentation.call("set_equipped_bow", "")
			_seek(actor, &"idle", 0.10)
			presentation.call("update_pose")
		_:
			_fail("unknown scenario " + scenario)


func _ensure_equipment(fixture: Dictionary, weapon: int) -> void:
	var actor := fixture.actor as ReplicatedActor3D
	var presentation: Node = fixture.presentation
	var wanted := {0: weapon, 5: 184}
	if weapon == MELEE_WEAPON:
		wanted[1] = 106
	elif weapon == RANGED_WEAPON:
		wanted[1] = RANGED_SHIELD
	var current := actor.get("_equipment_visuals") as Dictionary
	var matches := current.size() == wanted.size()
	for part: int in wanted:
		matches = matches and int(current.get(part, -1)) == int(wanted[part])
	if not matches:
		_apply_equipment(fixture, wanted)
	presentation.call("set_equipped_bow", RANGED_BOW \
		if weapon in [RANGED_WEAPON, LEGACY_RANGED_WEAPON] else "")


func _apply_equipment(fixture: Dictionary, visuals: Dictionary) -> void:
	var actor := fixture.actor as ReplicatedActor3D
	var detached: Node = fixture.get("detached") as Node
	if detached != null and not detached.is_inside_tree():
		actor.add_child(detached)
		actor.apply_equipment_visuals(visuals)
		actor.remove_child(detached)
	else:
		actor.apply_equipment_visuals(visuals)


func _reset_presentation(fixture: Dictionary) -> void:
	var presentation: Node = fixture.presentation
	(presentation.get("_mesh") as ImmediateMesh).clear_surfaces()
	(presentation.get("_trail") as Array).clear()
	presentation.set("_last_action", StringName())
	presentation.set("_last_time", -1.0)
	presentation.set("_spell_color", Color.TRANSPARENT)
	presentation.set("_spell_action", StringName())
	presentation.set("spell_power", 1)
	presentation.set("_power_action", StringName())
	var material := presentation.get("_material") as StandardMaterial3D
	material.albedo_color = Color.WHITE
	var bow: RangerBow3D = presentation.get("bow") as RangerBow3D
	if bow != null:
		bow.transform = Transform3D.IDENTITY
		bow.set("_aim_back", Vector3.ZERO)
		(bow.get("_string") as ImmediateMesh).clear_surfaces()
		bow.set("_local_geometry_valid", false)
		if bow.get_script() == CandidateBow:
			bow.set("_candidate_valid", false)


func _seek(actor: ReplicatedActor3D, action: StringName, time: float) -> void:
	actor.play_action(action, true)
	actor.animation_player.advance(0.0)
	actor._advance_facing_offset(1.0)
	actor.animation_player.seek(time, true)
	actor.animation_player.pause()


func _bench(fixture: Dictionary, iterations: int) -> void:
	var presentation: Node = fixture.presentation
	for iteration: int in iterations:
		presentation.call("update_pose")


func _check_dynamic_bow_sequence() -> Dictionary:
	var frozen := FrozenBow.new() as RangerBow3D
	var candidate: RangerBow3D = CandidateBow.new() as RangerBow3D \
		if _candidate_enabled else RangerBow3D.new()
	root.add_child(frozen)
	root.add_child(candidate)
	var candidate_typed: Node = candidate
	var up := Vector3.UP
	var forward := Vector3(0.12, 0.0, -0.9927739).normalized()
	var grip := Vector3(1.2, 1.1, -0.7)
	var hand := Vector3(1.2, 1.1, -1.2)
	var rows: Array[Dictionary] = []
	var steps := [
		{"id": "idle_initial", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": false,
			"release": -1.0, "size": 1.04, "arrow": 0.98},
		{"id": "idle_world_motion", "grip": grip + Vector3(2.0, 0.4, -1.0),
			"hand": hand + Vector3(2.0, 0.4, -1.0), "up": up,
			"forward": Vector3(-0.4, 0.0, -0.916515).normalized(),
			"drawing": false, "release": -1.0, "size": 1.04, "arrow": 0.98},
		{"id": "hold_initial", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": true,
			"release": -1.0, "size": 1.04, "arrow": 0.98},
		{"id": "hold_repeat", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": true,
			"release": -1.0, "size": 1.04, "arrow": 0.98},
		{"id": "hold_drawpoint_change", "grip": grip,
			"hand": hand + Vector3(0.0, 0.06, -0.17), "up": up,
			"forward": forward, "drawing": true, "release": -1.0,
			"size": 0.87, "arrow": 1.16},
		{"id": "release_0", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": false,
			"release": 0.0, "size": 1.04, "arrow": 0.98},
		{"id": "release_001", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": false,
			"release": 0.01, "size": 1.04, "arrow": 0.98},
		{"id": "release_008", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": false,
			"release": 0.08, "size": 1.04, "arrow": 0.98},
		{"id": "release_016", "grip": grip, "hand": hand,
			"up": up, "forward": forward, "drawing": false,
			"release": 0.16, "size": 1.04, "arrow": 0.98},
		{"id": "return_idle", "grip": grip + Vector3(-1.0, 0.0, 1.5),
			"hand": hand, "up": up, "forward": forward, "drawing": false,
			"release": -1.0, "size": 1.04, "arrow": 0.98},
	]
	var prior_transform := Transform3D.IDENTITY
	var idle_rebuilds := -1
	var hold_rebuilds := -1
	for step: Dictionary in steps:
		for bow: RangerBow3D in [frozen, candidate]:
			bow.pose(step.grip, step.hand, step.up, step.forward,
				step.drawing, step.release, step.size, step.arrow)
		var expected := _bow_snapshot(frozen)
		var actual := _bow_snapshot(candidate)
		if expected != actual:
			_fail("dynamic bow %s exact pose/geometry" % step.id)
		var rebuilds := int(candidate_typed.get("candidate_geometry_rebuilds")) \
			if _candidate_enabled else -1
		rows.append({"step": step.id, "snapshotSha256": _variant_sha256(actual),
			"candidateGeometryRebuilds": rebuilds})
		if step.id == "idle_initial":
			idle_rebuilds = rebuilds
			prior_transform = candidate.global_transform
		elif step.id == "idle_world_motion" and _candidate_enabled:
			_check(rebuilds == idle_rebuilds,
				"idle world motion retains identical local bow geometry")
			_check(candidate.global_transform != prior_transform,
				"idle world motion still updates bow world pose")
		elif step.id == "hold_initial":
			hold_rebuilds = rebuilds
		elif step.id == "hold_repeat" and _candidate_enabled:
			_check(rebuilds == hold_rebuilds,
				"identical ranged hold retains local bow geometry")
	var before_asset := int(candidate_typed.get("candidate_geometry_rebuilds")) \
		if _candidate_enabled else -1
	for bow: RangerBow3D in [frozen, candidate]:
		bow.set_asset("res://assets/actors/native/equipment/sunmane_ranger_bow.glb")
		bow.pose(grip, hand, up, forward, false, -1.0, 1.0, 1.0)
	var frozen_asset := _bow_snapshot(frozen)
	var candidate_asset := _bow_snapshot(candidate)
	_check(frozen_asset == candidate_asset,
		"asset change preserves exact bow pose/geometry")
	var after_asset := int(candidate_typed.get("candidate_geometry_rebuilds")) \
		if _candidate_enabled else -1
	if _candidate_enabled:
		_check(after_asset == before_asset + 1,
			"asset change invalidates retained local geometry")
	rows.append({"step": "sunmane_asset_change",
		"snapshotSha256": _variant_sha256(candidate_asset),
		"candidateGeometryRebuilds": after_asset})
	var final_vertices := _surface_vertex_count(
		candidate_asset.stringSurfaces as Array)
	_check(final_vertices > 0, "dynamic candidate bow has real string vertices")
	frozen.free()
	candidate.free()
	return {"steps": rows, "finalStringVertices": final_vertices,
		"geometryRebuilds": after_asset,
		"poseCalls": steps.size() + 1}


func _snapshot(fixture: Dictionary, scenario: String) -> Dictionary:
	var actor := fixture.actor as ReplicatedActor3D
	var presentation: Node = fixture.presentation
	var material := presentation.get("_material") as StandardMaterial3D
	var left: Vector3 = presentation.call("hand_position",
		int(presentation.get("_hand_l")))
	var right: Vector3 = presentation.call("hand_position",
		int(presentation.get("_hand_r")))
	var bow_snapshot := _bow_snapshot(presentation.get("bow"))
	return {
		"scenario": scenario,
		"action": str(actor.current_action),
		"animation": str(actor.animation_player.current_animation),
		"animationPosition": actor.animation_player.current_animation_position,
		"hands": [left, right],
		"actionSurfaces": _mesh_surfaces(presentation.get("_mesh") as Mesh),
		"actionMaterial": _material_snapshot(material),
		"trail": Array(presentation.get("_trail")).duplicate(),
		"lastAction": str(presentation.get("_last_action")),
		"lastTime": float(presentation.get("_last_time")),
		"spellPower": int(presentation.get("spell_power")),
		"handProps": _hand_prop_snapshot(actor),
		"bowVisible": bow_snapshot.visible,
		"bowTransform": bow_snapshot.transform,
		"bowAimBack": bow_snapshot.aimBack,
		"bowLimbs": bow_snapshot.limbs,
		"bowStringSurfaces": bow_snapshot.stringSurfaces,
		"arrowVisible": bow_snapshot.arrowVisible,
		"arrowTransform": bow_snapshot.arrowTransform,
	}


func _bow_snapshot(value: Variant) -> Dictionary:
	if value == null:
		return {"visible": false, "transform": Transform3D.IDENTITY,
			"aimBack": Vector3.ZERO, "limbs": [], "stringSurfaces": [],
			"arrowVisible": false, "arrowTransform": Transform3D.IDENTITY}
	var bow := value as RangerBow3D
	var limbs: Array = []
	var visual := bow.get("bow") as Node3D
	if visual != null:
		for child: Node in visual.get_children():
			if child is Node3D:
				limbs.append({"name": str(child.name),
					"transform": (child as Node3D).transform})
	limbs.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return str(a.name) < str(b.name))
	var arrow := bow.get("arrow") as Node3D
	return {
		"visible": bow.visible,
		"transform": bow.global_transform,
		"aimBack": bow.get("_aim_back") as Vector3,
		"limbs": limbs,
		"stringSurfaces": _mesh_surfaces(bow.get("_string") as Mesh),
		"arrowVisible": arrow.visible if arrow != null else false,
		"arrowTransform": arrow.transform if arrow != null \
			else Transform3D.IDENTITY,
	}


func _mesh_surfaces(mesh: Mesh) -> Array:
	var surfaces: Array = []
	if mesh == null:
		return surfaces
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		if arrays.size() != Mesh.ARRAY_MAX:
			_fail("surface %d exposes every array slot" % surface)
		surfaces.append({"arrays": arrays})
	return surfaces


func _material_snapshot(material: StandardMaterial3D) -> Dictionary:
	if material == null:
		return {}
	return {
		"albedoColor": material.albedo_color,
		"transparency": material.transparency,
		"shadingMode": material.shading_mode,
		"billboardMode": material.billboard_mode,
		"noDepthTest": material.no_depth_test,
		"blendMode": material.blend_mode,
		"vertexColorUseAsAlbedo": material.vertex_color_use_as_albedo,
		"renderPriority": material.render_priority,
	}


func _hand_prop_snapshot(actor: ReplicatedActor3D) -> Array:
	var rows: Array = []
	var nodes := actor.get("_equipment_nodes") as Dictionary
	for part: int in [0, 1]:
		for value: Variant in nodes.get(part, []):
			if value is Node3D and is_instance_valid(value):
				var node := value as Node3D
				rows.append({"part": part, "visible": node.visible})
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return int(a.part) < int(b.part))
	return rows


func _compare_snapshot(expected: Dictionary, actual: Dictionary,
		label: String) -> void:
	if expected != actual:
		_fail(label + " exact pose/geometry snapshot differs: frozen=%s current=%s" % [
			_variant_sha256(expected), _variant_sha256(actual)])
		for key: Variant in expected:
			if expected[key] != actual.get(key):
				push_error("  differing snapshot field %s: frozen=%s current=%s" % [
					key, _variant_sha256(expected[key]),
					_variant_sha256(actual.get(key))])
				if key == "handProps":
					push_error("  frozen hand props=" + JSON.stringify(expected[key]) +
						" current=" + JSON.stringify(actual.get(key)))


func _validate_scenario_output(snapshot: Dictionary, scenario: String) -> void:
	var action_vertices := _surface_vertex_count(snapshot.actionSurfaces as Array)
	var string_vertices := _surface_vertex_count(snapshot.bowStringSurfaces as Array)
	match scenario:
		"idle_no_cue":
			_check(action_vertices == 0, "idle/no-cue has no action geometry")
			_check(not bool(snapshot.bowVisible), "idle sword fixture has no bow")
		"idle_bow":
			_check(action_vertices == 0, "idle equipped bow has no action geometry")
			_check(bool(snapshot.bowVisible) and not bool(snapshot.arrowVisible),
				"idle equipped bow stays visible without a nocked arrow")
			_check(string_vertices > 0, "idle equipped bow has bowstring geometry")
		"melee", "attack_primary", "attack_secondary":
			_check(action_vertices > 0, "melee has a populated weapon trail")
			_check((snapshot.trail as Array).size() >= 2,
				"melee retained at least two trail points")
		"casting", "cast", "cast_channel_enter", "cast_channel", \
				"cast_aggressive", "cast_defensive", "heal":
			_check(action_vertices > 0, "casting has populated cue geometry")
		"ranged_draw", "ranged_hold", "legacy_ranged_hold":
			_check(action_vertices == 0,
				"ranged hold has no action-effect surface")
			_check(bool(snapshot.bowVisible) and bool(snapshot.arrowVisible),
				"ranged hold shows bow and nocked arrow")
			_check(string_vertices > 0, "ranged hold has bowstring geometry")
		"ranged_attack":
			_check(action_vertices > 0, "early ranged attack has release spark")
			_check(bool(snapshot.bowVisible) and not bool(snapshot.arrowVisible),
				"ranged attack shows bow without nocked arrow")
			_check(string_vertices > 0, "ranged attack has bowstring geometry")
		"effects_disabled_casting", "hidden_casting", \
				"transition_cast_to_idle":
			_check(action_vertices == 0, scenario + " clears action geometry")
		"melee_rewind":
			_check(action_vertices == 0 and (snapshot.trail as Array).size() == 1,
				"melee rewind clears the old trail before its new point")
		"transition_ranged_to_idle":
			_check(action_vertices == 0 and bool(snapshot.bowVisible) \
				and not bool(snapshot.arrowVisible),
				"equipped bow remains braced after ranged-to-idle transition")
		"equipment_bow_to_sword":
			_check(action_vertices == 0 and not bool(snapshot.bowVisible),
				"equipment transition hides the presentation bow")


func _surface_vertex_count(surfaces: Array) -> int:
	var total := 0
	for surface: Dictionary in surfaces:
		var arrays := surface.arrays as Array
		if arrays.size() == Mesh.ARRAY_MAX and arrays[Mesh.ARRAY_VERTEX] != null:
			total += (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	return total


func _variant_sha256(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(value))
	return context.finish().hex_encode()


func _check_baseline_provenance() -> void:
	var source := FileAccess.get_file_as_string(
		"res://tests/fixtures/combat_presentation_967744_baseline.gd")
	var body_at := source.find("extends Node3D")
	_check(body_at >= 0, "frozen baseline contains original script body")
	if body_at < 0:
		return
	var normalized := source.substr(body_at).replace("\r\n", "\n")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(normalized.to_utf8_buffer())
	_check(context.finish().hex_encode() == BASELINE_BODY_SHA256,
		"frozen baseline body matches reviewed 967744 SHA-256")
	_check(FileAccess.get_sha256(
		"res://tests/fixtures/ranger_bow_pose_967744_baseline.gd") ==
		BASELINE_BOW_FILE_SHA256,
		"frozen RangerBow3D pose matches reviewed 967744 fixture SHA-256")


func _summarize(trials: Array[Dictionary]) -> Dictionary:
	var result: Dictionary = {}
	for scenario: String in TIMED_SCENARIOS:
		var row: Dictionary = {}
		for implementation: String in ["frozen", "current"]:
			var values: Array[float] = []
			for trial: Dictionary in trials:
				values.append(float(trial.states[scenario][implementation][
					"microsecondsPerCallback"]))
			values.sort()
			row[implementation] = {
				"medianMicrosecondsPerCallback": _percentile(values, 0.5),
				"minimumMicrosecondsPerCallback": values[0],
				"maximumMicrosecondsPerCallback": values[-1],
			}
		row["currentVersusFrozenMedianPercent"] = (
			float(row.current.medianMicrosecondsPerCallback) /
			maxf(0.000001, float(row.frozen.medianMicrosecondsPerCallback)) - 1.0
		) * 100.0
		result[scenario] = row
	return result


func _percentile(sorted: Array[float], fraction: float) -> float:
	if sorted.is_empty():
		return NAN
	var position := fraction * (sorted.size() - 1)
	var lower := floori(position)
	var upper := ceili(position)
	return lerpf(sorted[lower], sorted[upper], position - lower)


func _check(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	_failures += 1
	push_error(message)
