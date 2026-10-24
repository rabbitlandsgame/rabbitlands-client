extends SceneTree
const Lifetime := preload("res://tests/integration/benchmark_resource_admission.gd")
func _init() -> void:
	_run.call_deferred()
func _run() -> void:
	var fixture := Lifetime.new()
	var result: Dictionary = await fixture.run(self)
	fixture = null
	if bool(result.get("requiresRunnerTermination", false)):
		return # The strict owner must terminate this process and its worker.
	await physics_frame
	await process_frame
	await process_frame
	quit(0 if bool(result.get("ready", false)) else 1)
