extends "res://tests/test_cape_cloth_native_constraint.gd"
## Strict current-policy comparison. The frozen historical references remain
## separate: their old walking damping cannot qualify today's native wrapper.
## Run directly; this fixture requests native cape only in its own process.
const CURRENT_SCRIPT_REFERENCE := "res://tests/fixtures/cape_cloth_current_script_reference.gd"
var _current_checks := 0

func _init() -> void:
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "cape")
	call_deferred("_run")

func _baseline_path() -> String:
	return CURRENT_SCRIPT_REFERENCE

func _check_baseline_provenance() -> void:
	var reference := load(CURRENT_SCRIPT_REFERENCE) as Script
	_check(reference != null and reference.get_base_script() == load("res://src/actors/cape_cloth.gd"),
		"Script reference inherits the exact current production solver")
	_check(EPSILON == 0.000001, "current comparison retains the strict historical tolerance")

func _comparison_label() -> String:
	return "current-policy GDScript solver vs shared native constraint kernel"

func _run() -> void:
	_check_baseline_provenance()
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	_equipment_config = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	_model_config = models["luminous_male"]
	_animation_config = JSON.parse_string(FileAccess.get_file_as_string(str(_model_config.animationMap)))
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})
	_stage = Node3D.new()
	root.add_child(_stage)
	var actors: Array[ReplicatedActor3D] = []
	for index: int in 2:
		var actor := _spawn_current_actor(9100 + index)
		if actor != null:
			actors.append(actor)
	if actors.size() == 2:
		var optimized_actor := actors[0]
		var baseline_actor := actors[1]
		var optimized_skeleton := optimized_actor.get_skeleton()
		var baseline_skeleton := baseline_actor.get_skeleton()
		var optimized_cloth: SkeletonModifier3D = optimized_skeleton.get_node("CapeCloth")
		var baseline_cloth := _replace_with_baseline(baseline_actor, baseline_skeleton)
		optimized_cloth.active = false
		baseline_cloth.active = false
		var fabric: Array = optimized_cloth.get("_fabric_rest")
		_check(fabric.size() == 3 and fabric == baseline_cloth.get("_fabric_rest"),
			"both actual equipped rigs retain all measured fabric chains")
		for key: String in ["_section_knots", "_section_halves", "_section_folds", "_section_blend", "_shin_reaches", "_surface_samples"]:
			_check(optimized_cloth.get(key) == baseline_cloth.get(key), "paired current input " + key)
		_check_rig_ownership(optimized_skeleton)
		var optimized_player := optimized_actor.animation_player
		var baseline_player := baseline_actor.animation_player
		for clip: StringName in [&"Walk", &"Combat_Slash_A"]:
			_check(optimized_player != null and optimized_player.has_animation(clip), "native real clip " + str(clip))
			_check(baseline_player != null and baseline_player.has_animation(clip), "Script real clip " + str(clip))
		if _failures == 0:
			# Inherited sequence includes negative/zero/hitch deltas, 72 moving
			# Walk frames, 42 attack frames, live torso capsule replacement,
			# teleport and explicit reset, now with measured fabric on both.
			_run_real_sequence(optimized_actor, baseline_actor, optimized_skeleton, baseline_skeleton,
				optimized_cloth, baseline_cloth, optimized_player, baseline_player)
			_run_material_line_sequence(actors, optimized_cloth, baseline_cloth)
	# Minimal rigs deliberately omit all optional body capsules; inherited
	# native rejection checks separately prove atomicity and Script fallback.
	_run_missing_optional_sequence()
	await _cleanup_current_fixtures(actors)
	print("CURRENT_CAPE_NATIVE_CHECKS ", _current_checks, " failures=", _failures)
	quit(1 if _failures else 0)

func _spawn_current_actor(id: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	var errors := actor.configure({"actor_id": id, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "current-cape-fixture", "appearance": {},
		"equipment_visuals": {str(2): CAPE_VISUAL, str(5): 184}},
		_adapter, _model_config, _animation_config, _equipment_config)
	_check(errors.is_empty(), "actual current equipped actor loads: " + str(errors))
	if not errors.is_empty():
		actor.queue_free()
		return null
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.server_target = Vector3.ZERO
	actor.global_position = Vector3.ZERO
	actor.rotation.y = 0.0
	var skeleton := actor.get_skeleton()
	_check(skeleton != null and skeleton.get_node_or_null("CapeCloth") != null,
		"actual equipped actor has its cape modifier")
	if skeleton == null or skeleton.get_node_or_null("CapeCloth") == null:
		actor.queue_free()
		return null
	return actor

func _replace_with_baseline(actor: ReplicatedActor3D, skeleton: Skeleton3D) -> SkeletonModifier3D:
	var original: SkeletonModifier3D = skeleton.get_node("CapeCloth")
	original.active = false
	var torso: PackedFloat32Array = original.get("_torso_reach")
	var lumbar: PackedFloat32Array = original.get("_lumbar_reach")
	var fabric: Array = (original.get("_fabric_rest") as Array).duplicate(true)
	var section: Array = []
	for key: String in ["_section_knots", "_section_halves", "_section_folds", "_section_blend"]:
		section.append((original.get(key) as PackedFloat32Array).duplicate())
	var shins: Array = (original.get("_shin_reaches") as Array).duplicate(true)
	var samples: Array = (original.get("_surface_samples") as Array).duplicate(true)
	skeleton.remove_child(original)
	original.free()
	var replacement: SkeletonModifier3D = (load(CURRENT_SCRIPT_REFERENCE) as Script).new()
	replacement.name = "CapeCloth"
	skeleton.add_child(replacement)
	replacement.call("set_torso_reach", torso, lumbar)
	replacement.call("set_fabric_line", fabric, section)
	replacement.call("set_shin_reach", shins)
	replacement.call("set_surface_samples", samples)
	replacement.active = false
	actor.set("_cape_cloth", replacement)
	return replacement

func _run_material_line_sequence(actors: Array[ReplicatedActor3D], optimized: SkeletonModifier3D,
		baseline: SkeletonModifier3D) -> void:
	for cloth: SkeletonModifier3D in [optimized, baseline]:
		cloth.call("set_fabric_line", [])
		cloth.call("set_surface_samples", [])
		cloth.call("set_shin_reach", [])
		cloth.call("set_torso_reach", PackedFloat32Array(), PackedFloat32Array())
		cloth.call("reset")
	for actor: ReplicatedActor3D in actors:
		actor.animation_player.play(&"Walk")
	for frame: int in 24:
		for actor: ReplicatedActor3D in actors:
			actor.position += Vector3(0.006, 0.0, -0.018)
			actor.rotation.y = sin(frame * 0.09) * 0.35
			actor.animation_player.advance(STEP)
		_step_pair(actors[0].get_skeleton(), actors[1].get_skeleton(), optimized, baseline,
			STEP, "current material line walk frame %d" % frame)

func _step_pair(optimized_skeleton: Skeleton3D, baseline_skeleton: Skeleton3D,
		optimized: SkeletonModifier3D, baseline: SkeletonModifier3D, delta: float, label: String) -> void:
	var before: Dictionary = optimized.call("native_presentation_stats")
	super._step_pair(optimized_skeleton, baseline_skeleton, optimized, baseline, delta, label)
	var after: Dictionary = optimized.call("native_presentation_stats")
	var reference: Dictionary = baseline.call("native_presentation_stats")
	_check(int(after.get("nativeCalls", 0)) == int(before.get("nativeCalls", 0)) + 1,
		label + " executes exactly one successful native point step")
	_check(int(after.get("fallbackCalls", -1)) == 0, label + " has no fallback")
	_check(not bool(reference.get("active", true)) and int(reference.get("nativeCalls", -1)) == 0
		and int(reference.get("fallbackCalls", -1)) == 0, label + " reference executes only current Script")

func _cleanup_current_fixtures(actors: Array[ReplicatedActor3D]) -> void:
	for actor: ReplicatedActor3D in actors:
		actor.process_mode = Node.PROCESS_MODE_DISABLED
	_stage.process_mode = Node.PROCESS_MODE_DISABLED
	await _drain_current()
	_stage.queue_free()
	_stage = null
	actors.clear()
	await _drain_current()
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await _drain_current()

func _drain_current() -> void:
	await physics_frame
	await process_frame
	await process_frame

func _check(ok: bool, label: String) -> void:
	_current_checks += 1
	super._check(ok, label)
