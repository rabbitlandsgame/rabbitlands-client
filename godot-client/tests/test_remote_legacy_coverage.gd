extends SceneTree
## Real autoload authority in legacy mode; no native service or imported models.
var failures := 0

class CoverageActor extends Node3D:
	var actor_id := 0
	var _cinematic_active := false
	var _charge_leap: Variant
	var _predicted_turn_pending := false
	var current_action := &"idle"
	var _mount_visual: Variant
	func view_radius() -> float: return 1.0
	func is_model_deferred() -> bool: return false

func _init() -> void: call_deferred("_run")

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)

func _run() -> void:
	var state: Variant = root.get_node("AppState")
	var script: Script = load("res://src/runtime/remote_presentation.gd")
	var old_local: int = state.local_actor_id
	var old_mode := OS.get_environment("RABBITLANDS_REMOTE_PRESENTATION")
	OS.set_environment("RABBITLANDS_REMOTE_PRESENTATION", "legacy")
	state.local_actor_id = 101
	var holder := Node3D.new()
	root.add_child(holder)
	var service: Variant = script.new()
	holder.add_child(service)
	var gate := AnimationGate.new()
	_check(service.initialize(null, gate) == gate, "legacy retains ordinary gate")
	var a := CoverageActor.new()
	a.actor_id = 101
	holder.add_child(a)
	var b := CoverageActor.new()
	b.actor_id = 202
	holder.add_child(b)
	var actors: Array = [a, b]
	var census: Dictionary = service.coverage(actors)
	_check(census.actorNodes == 2 and census.localLegacy == 1 and census.eligibleRemote == 1,
		"legacy census separates actual local player from remote actor")
	_check(census.nativeOwned == 0 and census.legacySupported == 1,
		"legacy remote stays under ordinary ownership")
	_check(service.is_local_actor(101) and not service.is_local_actor(202), "initial autoload local ID")
	state.local_actor_id = 202
	_check(not service.is_local_actor(101) and service.is_local_actor(202), "changed actual local ID is authoritative")
	census = service.coverage(actors)
	_check(census.localLegacy == 1 and census.eligibleRemote == 1 and census.nativeOwned == 0
		and census.legacySupported == 1, "dynamic local change keeps exact legacy census")
	var detached: Variant = script.new()
	_check(detached.initialize(null, gate) == gate and not detached.is_local_actor(202),
		"off-tree legacy initialization stays safe without cached authority")
	OS.set_environment("RABBITLANDS_REMOTE_PRESENTATION", "rust")
	_check(detached.initialize(null, gate) == gate and detached.snapshot().reason == "app_state_unavailable",
		"off-tree Rust still refuses missing autoload authority")
	detached.free()
	service.close()
	holder.free()
	state.local_actor_id = old_local
	OS.set_environment("RABBITLANDS_REMOTE_PRESENTATION", old_mode)
	await process_frame
	print("remote legacy coverage: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
