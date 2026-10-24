extends SceneTree
## Actual Main ready/full-discard/exit, no authentication or map import.
const Remote = preload("res://src/runtime/remote_presentation.gd")
var failures := 0

func _init() -> void: call_deferred("_run")
func _expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)

func _run() -> void:
	var app_state: Variant = root.get_node("AppState")
	var old_runtime := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	var old_remote := OS.get_environment("RABBITLANDS_REMOTE_PRESENTATION")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "rust")
	OS.set_environment("RABBITLANDS_REMOTE_PRESENTATION", "rust")
	var old_authenticated: bool = app_state.authenticated
	var old_map: String = app_state.current_map
	var old_actors: Dictionary = app_state.actors
	app_state.authenticated = false
	app_state.current_map = ""
	app_state.actors = {}
	var unready: Variant = (load("res://src/app/main.gd") as Script).new()
	_expect(unready.remote_presentation == null, "unready Main allocates no orphan service Node")
	unready.free()
	var scene := load("res://src/app/main.tscn") as PackedScene
	var main := scene.instantiate()
	root.add_child(main)
	await process_frame
	var service := main.get("remote_presentation") as RemotePresentation
	var controller := main.get("client_runtime") as ClientRuntimeController
	_expect(service != null and Remote.current() == service, "actual Main publishes remote service")
	if "--expect-native" in OS.get_cmdline_user_args():
		_expect(service._ready_native, "actual Main enables verified native remote service")
	elif "--expect-native=absent" in OS.get_cmdline_user_args():
		_expect(not service._ready_native, "actual Main falls back with optional DLL physically absent")
	var old_epoch := controller.current_epoch()
	if service._ready_native:
		var actor := ReplicatedActor3D.new()
		(main.get("world_root") as Node).add_child(actor)
		actor.actor_id = 7001
		actor._remote_enrollment_ready = true
		(main.get("actor_nodes") as Dictionary)[7001] = actor
		_expect(service.consider(actor), "actual Main world owns a derived remote binding")
		var generation := actor._remote_generation
		main.call("_clear_world_presentation")
		_expect(controller.current_epoch() == old_epoch + 1 and service._epoch == controller.current_epoch(),
			"Main resets both native owners to the same new session epoch")
		_expect(service._rows.is_empty() and actor._remote_generation == 0 and not actor.is_physics_processing(),
			"Main full discard releases binding without reactivating departing physics")
		_expect(actor.is_queued_for_deletion(), "Main still owns actor deletion")
		var after := ReplicatedActor3D.new()
		(main.get("world_root") as Node).add_child(after)
		after.actor_id = 7001
		after._remote_enrollment_ready = true
		(main.get("actor_nodes") as Dictionary)[7001] = after
		_expect(service.consider(after) and after._remote_generation > generation,
			"reused actor ID binds a new generation after world clear")
	else:
		main.call("_clear_world_presentation")
		_expect(controller.current_epoch() == old_epoch + 1, "legacy Main world clear remains playable")
	main.call("_clear_world_presentation")
	await process_frame
	var retained := service
	main.queue_free()
	await process_frame
	await process_frame
	_expect(not is_instance_valid(main) and Remote.current() == null, "actual Main exit removes weak service")
	_expect(not is_instance_valid(retained), "Main owns remote manager Node lifetime")
	app_state.authenticated = old_authenticated
	app_state.current_map = old_map
	app_state.actors = old_actors
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", old_runtime)
	OS.set_environment("RABBITLANDS_REMOTE_PRESENTATION", old_remote)
	print("remote Main lifecycle: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
