extends SceneTree
## Approved runtime content only. Checks the mounted clock/quality contract,
## not frame-rate claims; root runs this serially after the Phase2 patch applies.
const Quality := preload("res://src/actors/actor_render_quality.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var config := models.luminous_male as Dictionary
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 42, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "Mounted policy fixture", "appearance": {"hair": 0},
		"equipment_visuals": {0: 164, ReplicatedActor3D.CAPE_PART: 1}}, CoordinateAdapter.new({"walkingHeight": 0.0}), config,
		JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)),
		JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json")))
	_check(errors.is_empty(), "approved rider configures")
	_check(actor.wears_cape_cloth() and not actor._worn_skinned_scene(ReplicatedActor3D.CAPE_PART).is_empty(),
		"approved cape fixture is actually worn before checking mounted cloth policy")
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.apply_render_quality(Quality.Quality.LOW, false)
	actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "cruise"}, models)
	var visual := actor._mount_visual
	if not _check(is_instance_valid(visual), "approved Moor Pony configures"):
		actor.process_mode = Node.PROCESS_MODE_DISABLED
		await _drain()
		actor.queue_free()
		await _drain()
		quit(1)
		return
	visual.set_process(false)
	var pony := visual.get("pony") as ReplicatedActor3D
	var native_model := pony.get_node("NativeModel") as Node3D
	var mount_bounds: AABB = (pony.transform * native_model.transform) * pony._native_body_bounds
	for corner: int in 8:
		_check(actor.view_radius() >= mount_bounds.get_endpoint(corner).distance_to(Vector3.UP),
			"the shared frustum sphere includes the mount's scaled imported bounds")
	_check(actor.view_radius() >= float(visual.get("banner_head_height")) + 0.6,
		"the shared frustum sphere includes the mounted rider's raised banner")
	_check(pony.render_quality() == Quality.Quality.LOW and not pony.render_quality_is_local(),
		"new mount inherits its rider's resolved quality and local role")
	var mesh := pony.get_node("NativeModel").find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	_check(mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"LOW removes mount shadows")
	_check(not actor.cape_cloth_active() and not actor._cape_cloth.active,
		"remote LOW mounted cloth is asleep and automatic cloth stays off")
	actor.apply_render_quality(Quality.Quality.HIGH, false)
	_check(pony.render_quality() == Quality.Quality.HIGH and actor.cape_cloth_active(),
		"live HIGH change reaches mount and manual cape")
	_check(not actor._cape_cloth.active, "manual mounted cloth never activates the automatic modifier")
	actor.set_cape_cloth_allowed(false)
	_check(not actor.cape_cloth_active(), "mounted cape respects crowd allowance")
	actor.set_cape_cloth_allowed(true)
	actor.apply_render_quality(Quality.Quality.MEDIUM, false)
	_check(not actor.cape_cloth_active(), "remote MEDIUM cloth is asleep")
	actor.apply_render_quality(Quality.Quality.LOW, true)
	_check(pony.render_quality_is_local() and actor.cape_cloth_active(),
		"local riding cape remains available at LOW")
	var gate := AnimationGate.new()
	gate.one_shot_tier = AnimationGate.Tier.QUARTER
	actor.set_animation_tier(AnimationGate.Tier.QUARTER, gate)
	_check(actor.animation_tier() == AnimationGate.Tier.FULL, "local rider retains full-rate presentation")
	actor.apply_render_quality(Quality.Quality.HIGH, false)
	actor.set_selected(true)
	actor.set_animation_tier(AnimationGate.Tier.QUARTER, gate)
	_check(actor.animation_tier() == AnimationGate.Tier.FULL, "selected rider retains priority presentation")
	actor.set_selected(false)
	for tier: int in [AnimationGate.Tier.HALF, AnimationGate.Tier.QUARTER]:
		actor.set_animation_tier(tier, gate)
		visual.set_process(false)
		var before := visual.call("scheduling_stats") as Dictionary
		for tick: int in 8:
			visual.call("_process", 1.0 / 60.0)
		var after := visual.call("scheduling_stats") as Dictionary
		var expected := 4 if tier == AnimationGate.Tier.HALF else 2
		_check(int(after.poseSteps) - int(before.poseSteps) == expected,
			"mount and rider step together at their requested tier")
		var accounted := float(after.steppedSeconds) - float(before.steppedSeconds) \
			+ float(after.pendingSeconds) - float(before.pendingSeconds)
		_check(absf(accounted - 8.0 / 60.0) < 0.000001, "stepped tiers accumulate all elapsed time")
		_check(gate.half_rate_count() == 0 and gate.quarter_rate_count() == 0,
			"ordinary animation gate cannot independently advance the mounted rider")
	# The diagnostic flag must affect mounted and ordinary clocks alike.
	for staggered: bool in [false, true]:
		gate.stagger = staggered
		for identity: int in [42, 43]:
			actor.actor_id = identity
			actor.set_animation_tier(AnimationGate.Tier.HALF, gate)
			visual.set_process(false)
			visual.set("_sample_tick", 0)
			visual.set("_pending_delta", 0.0)
			var prior_steps := int((visual.call("scheduling_stats") as Dictionary).poseSteps)
			visual.call("_process", 1.0 / 60.0)
			var new_steps := int((visual.call("scheduling_stats") as Dictionary).poseSteps) - prior_steps
			_check(new_steps == (1 if staggered and identity % 2 == 1 else 0),
				"mounted phase follows the gate's actual stagger flag and actor identity")
	actor.actor_id = 42
	gate.stagger = true
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_check(not actor.model_processing() and not pony.model_processing(),
		"frustum-paused rider and mount skeleton subtrees sleep together")
	var asleep := visual.call("scheduling_stats") as Dictionary
	visual.call("_process", 1.0)
	_check((visual.call("scheduling_stats") as Dictionary).poseSteps == asleep.poseSteps,
		"paused mounted loop does no pose work")
	var offscreen_pose_steps := int((visual.call("scheduling_stats") as Dictionary).poseSteps)
	actor.play_action(&"cast_aggressive", true)
	_check(actor.animation_tier() == AnimationGate.Tier.QUARTER,
		"an offscreen one-shot wakes only at the established one-shot tier")
	var upper := visual.get("upper") as RefCounted
	var action_rate := actor.resolver.playback_speed_for_action(&"cast_aggressive")
	var action_duration := float(upper.call("duration")) / maxf(action_rate, 0.001)
	if _check(action_duration > 0.0, "approved rider supplies a mounted one-shot clip"):
		var tick_seconds := action_duration / 40.0
		for tick: int in 4:
			visual.call("_process", tick_seconds)
		var elapsed_action := float(upper.get("time")) / maxf(action_rate, 0.001)
		var queued_action := float((visual.call("scheduling_stats") as Dictionary).pendingSeconds)
		_check(absf(elapsed_action + queued_action - tick_seconds * 4.0) < 0.000001,
			"a paused-tier one-shot consumes skipped-frame elapsed time at normal speed")
	for tick: int in 200:
		visual.call("_process", 0.05)
	_check(actor.animation_tier() == AnimationGate.Tier.PAUSED,
		"completed offscreen upper-body action returns to sleep")
	_check(str(upper.get("action")).is_empty() and not bool(upper.get("_returning"))
		and is_zero_approx(float(upper.get("weight"))) and is_zero_approx(float(upper.get("grip_weight"))),
		"completed mounted recovery publishes a fully finished upper-body state")
	_check(int((visual.call("scheduling_stats") as Dictionary).poseSteps) == offscreen_pose_steps,
		"offscreen one-shots advance their clock without mount, seat, reins, or cloth poses")
	actor.set_animation_tier(AnimationGate.Tier.FULL, gate)
	actor.play_action(&"cast_aggressive", true)
	actor.pause_for_parking(gate)
	var parked := visual.call("scheduling_stats") as Dictionary
	visual.call("_process", 1.0)
	_check(bool(parked.parked) and actor.animation_tier() == AnimationGate.Tier.PAUSED
		and (visual.call("scheduling_stats") as Dictionary).poseSteps == parked.poseSteps,
		"parking sleeps even an active mounted one-shot")
	actor.set_animation_tier(AnimationGate.Tier.HALF, gate)
	_check(not bool((visual.call("scheduling_stats") as Dictionary).parked)
		and actor.model_processing() and pony.model_processing(), "revival wakes both model subtrees")
	actor.set_mount_state({}, models)
	_check(not is_instance_valid(actor._mount_visual) and gate.half_rate_count() == 1,
		"dismount returns the rider to the ordinary animation gate exactly once")
	actor.process_mode = Node.PROCESS_MODE_DISABLED
	gate.reset(false)
	await _drain()
	actor.queue_free()
	await _drain()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("MOUNT_QUALITY_SCHEDULING failures=", failures)
	quit(1 if failures else 0)

func _drain() -> void:
	await physics_frame
	await process_frame
	await process_frame

func _check(ok: bool, label: String) -> bool:
	if not ok:
		failures += 1
		push_error(label)
	return ok
