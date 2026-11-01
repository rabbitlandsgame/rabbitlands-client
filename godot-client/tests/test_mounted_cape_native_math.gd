extends "res://tests/test_mounted_approved_cape.gd"
## Manual optional-native regression. This checks exact arithmetic, not timing
## or physical clearance; those remain in test_mounted_approved_cape.gd.
## RL_MOUNT_REQUIRE_NATIVE=1 turns an unavailable capability into a failure.

const NativeRuntime := preload("res://src/runtime/client_runtime.gd")
const ParityFixture := preload("res://tests/fixtures/mounted_cape_native_parity.gd")
var _native_runtime: RefCounted
var _old_native_mode := ""
var _had_native_mode := false

func _run() -> void:
	_had_native_mode = OS.has_environment("RABBITLANDS_CLIENT_RUNTIME")
	_old_native_mode = OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "services")
	_native_runtime = NativeRuntime.new()
	_native_runtime.call("initialize", ProjectSettings.globalize_path("res://bin/client_runtime"))
	var ready := bool((_native_runtime.call("snapshot") as Dictionary).get("native_available", false))
	var capabilities: Dictionary = {}
	if ready and ClassDB.class_exists("RabbitLandsCapeProjector") and ClassDB.class_exists("RabbitLandsCapeBodySurface"):
		var projector: RefCounted = ClassDB.instantiate("RabbitLandsCapeProjector")
		capabilities = projector.call("runtime_info")
	for key: String in ["exact_memo", "trusted_body", "parallel_contacts", "parallel_residuals", "refresh_clear_contacts", "edge_priority"]:
		ready = ready and bool(capabilities.get(key, false))
	if not ready:
		var reason := "compatible optional mounted-native arithmetic is unavailable"
		if OS.get_environment("RL_MOUNT_REQUIRE_NATIVE") == "1":
			_check(false, reason)
			_complete_native("FAIL", reason, {})
		else:
			_complete_native("SKIP", reason, {})
		return
	RLHeadLibrary.retain_seconds = 0.0
	_models = _json("res://data/actors/models.json").get("models", {})
	_equipment = _json("res://data/actors/equipment.json")
	var actor := _spawn("luminous_male", 184, {"rl_head": {"sex": "male", "hair": "none", "beard": "none"}})
	actor.rotation.y = .47
	_sample(actor, &"idle", .4)
	actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "idle", "step_us": 200000}, _models)
	var visual := actor._mount_visual as Node3D
	_check(visual != null, "actual armoured Moor rider configures")
	if visual == null:
		actor.queue_free(); await process_frame
		await _shutdown_fixture()
		_complete_native("FAIL", "mounted visual unavailable", {})
		return
	visual.call("set_animation_tier", AnimationGate.Tier.FULL, AnimationGate.Tier.HALF, false, false)
	visual.set_process(false)
	visual.call("_process", STEP)
	var old := actor._cape_cloth.get("_mounted_fit") as RefCounted
	_check(old != null, "actual mounted fitter is available")
	if old == null:
		actor.queue_free(); await process_frame
		await _shutdown_fixture()
		_complete_native("FAIL", "mounted fitter unavailable", {})
		return
	var fixture := ParityFixture.new()
	fixture.adopt_actual_state(old)
	actor._cape_cloth.set("_mounted_fit", fixture)
	old = null
	var rests := _body_poses(actor.get_skeleton(), true)
	for gait: String in ["idle", "walk", "cruise", "burst"]:
		var speed := _select_motion(actor, gait)
		_advance_native(actor, visual, fixture, speed, 60, "gait/" + gait)
	var upper := visual.get("upper") as RefCounted
	for moving: bool in [false, true]:
		var speed := _select_motion(actor, "cruise" if moving else "idle")
		for action: StringName in [&"cast_aggressive", &"ranged_attack", &"cast_channel_enter"]:
			var label := ("travel/" if moving else "standing/") + str(action)
			upper.call("begin_return")
			actor.play_action(&"run" if moving else &"idle")
			_advance_native(actor, visual, fixture, speed, 15, label + "/settle")
			if action == &"ranged_attack":
				actor.play_action(&"ranged_draw", true)
				_advance_native(actor, visual, fixture, speed, 30, label + "/draw")
			if action == &"cast_aggressive":
				actor.set_spell_variant(2)
			actor.play_action(action, true)
			_advance_native(actor, visual, fixture, speed, 60, label)
			upper.call("begin_return")
			actor.play_action(&"run" if moving else &"idle")
			_advance_native(actor, visual, fixture, speed, 15, label + "/return")
	var summary: Dictionary = fixture.parity_summary()
	_check(int(summary.calls) >= 600, "gaits and standing/travel upper actions exercise the numeric mirrors")
	_check(int(summary.error_count) == 0, "reference and optimized arithmetic match: " + str(summary.failures))
	_check(bool(summary.rejection_guards_exercised), "optional flag and foreign-owner rejection checks ran")
	_check(_transform_error(rests, _body_poses(actor.get_skeleton(), true)) == 0.0, "numeric regression preserves Body65 rests")
	fixture.release_parity_mirrors()
	actor.queue_free(); await process_frame
	fixture = null
	await _shutdown_fixture()
	_complete_native("PASS" if _failures.is_empty() else "FAIL", "", summary)

func _select_motion(actor: ReplicatedActor3D, gait: String) -> float:
	var speed: float = {"idle": 0.0, "walk": 1.67, "cruise": 5.0, "burst": 7.5}[gait]
	actor.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": gait, "step_us": 200000}, _models)
	actor.current_action = &"idle" if speed == 0.0 else &"run"
	actor._presentation_speed = speed
	actor._segment_start = actor.global_position
	actor._segment_duration = 100.0 if speed > 0.0 else 0.0
	actor.server_target = actor.global_position + actor.global_basis * Vector3(0, 0, -speed * 100.0)
	return speed

func _advance_native(actor: ReplicatedActor3D, visual: Node3D, fixture: RefCounted,
		speed: float, frames: int, label: String) -> void:
	fixture.call("begin_context", label)
	for frame: int in frames:
		actor.global_position += actor.global_basis * Vector3(0, 0, -speed * STEP)
		visual.call("_process", STEP)

func _complete_native(status: String, reason: String, summary: Dictionary) -> void:
	_native_runtime.call("close")
	_native_runtime = null
	if _had_native_mode:
		OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", _old_native_mode)
	else:
		OS.unset_environment("RABBITLANDS_CLIENT_RUNTIME")
	var folder := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if folder.is_empty():
		folder = ProjectSettings.globalize_path("res://test-artifacts/mounted-cape-native-math")
	DirAccess.make_dir_recursive_absolute(folder)
	var file := FileAccess.open(folder.path_join("native-math.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"status": status, "reason": reason, "checks": _checks,
		"failures": _failures, "numeric": summary}, "\t"))
	print("MOUNTED_CAPE_NATIVE_MATH ", status, " checks=", _checks, " ", reason)
	quit(0 if _failures.is_empty() else 1)
