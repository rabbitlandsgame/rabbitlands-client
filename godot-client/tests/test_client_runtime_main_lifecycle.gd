extends SceneTree
## Exercise the actual Main scene hooks, without authentication or a map load.
const Controller := preload("res://src/runtime/client_runtime.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	var previous := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	var selected := "rust" if OS.get_cmdline_user_args().has("--runtime=rust") else "compare"
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", selected)
	var app := root.get_node("/root/AppState")
	var previous_authenticated: bool = app.get("authenticated")
	var previous_map: String = app.get("current_map")
	var previous_actors: Dictionary = app.get("actors")
	app.set("authenticated", false)
	app.set("current_map", "")
	app.set("actors", {})
	var scene := load("res://src/app/main.tscn") as PackedScene
	if scene == null:
		_expect(false, "Main scene loads")
		OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", previous)
		quit(failures)
		return
	var main := scene.instantiate()
	root.add_child(main)
	await process_frame
	var controller := main.get("client_runtime") as ClientRuntimeController
	_expect(controller != null and Controller.current() == controller,
		"Main ready initializes and publishes its controller")
	if controller != null:
		var before := controller.snapshot()
		var args := OS.get_cmdline_user_args()
		if args.has("--expect-native") or args.has("--expect-native=present"):
			_expect(before.native_available and before.mode == selected, "Main uses the verified selected native profile")
		elif args.has("--expect-native=absent"):
			_expect(not before.native_available and before.mode == "legacy", "Main remains available with the native payload absent")
		var first := controller.allocate_instance_generation()
		var second := controller.allocate_instance_generation()
		_expect(second > first, "instance generation tokens are monotonic")
		var epoch := controller.current_epoch()
		main.call("_clear_world_presentation")
		_expect(controller.current_epoch() == epoch + 1 and Controller.current() == controller,
			"actual Main world-clear resets the epoch without closing its service")
		main.call("_clear_world_presentation")
		_expect(controller.current_epoch() == epoch + 2 and controller.wants_rust_pose() == (before.mode == "rust"),
			"repeated world clear preserves the selected pose owner and advances the epoch")
		_expect(controller.allocate_instance_generation() > second,
			"world clear does not reuse instance generations")
		var after := controller.snapshot()
		_expect(after.presentation_backend == before.presentation_backend and after.mode == before.mode,
			"map/session resets leave the selected service and presentation backend intact")
	main.queue_free()
	await process_frame
	await process_frame
	_expect(not is_instance_valid(main) and Controller.current() == null,
		"actual Main exit closes its service and removes the weak current reference")
	if controller != null:
		_expect(controller.native_runtime() == null and controller.snapshot().mode == "legacy",
			"a retained controller handle owns no native service after Main exit")
	app.set("authenticated", previous_authenticated)
	app.set("current_map", previous_map)
	app.set("actors", previous_actors)
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", previous)
	print("client runtime Main lifecycle: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
