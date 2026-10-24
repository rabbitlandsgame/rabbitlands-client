class_name RabbitLandsCrowdBenchmarkLoop
extends "res://tests/integration/crowd_presentation_benchmark.gd"
## Only the disposable local benchmark export selects this custom SceneTree.
## The inherited constructor defers its virtual _run(), after autoload setup.

func _run() -> void:
	if OS.get_environment("RABBITLANDS_CROWD_BENCH_EXECUTION_MODE").strip_edges() == "exported":
		await super._run()
		return
	var error := change_scene_to_file("res://src/app/main.tscn")
	if error != OK:
		push_error("Local benchmark package could not open the ordinary game: %s" % error_string(error))
		quit(1)
