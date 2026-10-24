extends SceneTree

const Parity := preload("res://tests/integration/prepared_content_parity.gd")


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var plan := OS.get_environment("RABBITLANDS_PREPARED_PARITY_PLAN").strip_edges()
	if plan.is_empty():
		push_error("RABBITLANDS_PREPARED_PARITY_PLAN must name an exact describe-pilot plan")
		quit(1)
		return
	var parity := Parity.new()
	var result: Dictionary = await parity.run(self, plan)
	parity = null
	await physics_frame
	await process_frame
	await process_frame
	quit(0 if bool(result.get("ready", false)) else 1)
