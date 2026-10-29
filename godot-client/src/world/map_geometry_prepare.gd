extends SceneTree
## Explicit maintenance entry point for the installer/update tool and local
## builds. It uses the installed runtime's own engine and renderer.
const Preparer := preload("res://src/world/map_geometry_preparer.gd")
const Cache := preload("res://src/world/map_geometry_cache.gd")

func _init() -> void:
	call_deferred("run")

func run() -> void:
	var job := {}
	var path := OS.get_environment("ELORIA_GEOMETRY_JOB")
	if not path.is_empty():
		job = Cache._read(path)
		if int(job.get("schema",0)) != 1:
			push_error("Invalid world geometry preparation job")
			quit(2)
			return
	var preparer := Preparer.new()
	root.add_child(preparer)
	var release_output := bool(job.get("release_preparation",false))
	if release_output: Cache.set_release_output(true)
	preparer.progress.connect(func(done: int,total: int,label: String) -> void:
		print("MAP_GEOMETRY_PROGRESS ",JSON.stringify({"done":done,"total":total,"id":label})))
	var report := await preparer.run(job)
	if release_output: Cache.set_release_output(false)
	if job.get("output_report") is String and not str(job.output_report).is_empty():
		Cache.write_json(str(job.output_report),report)
	print("MAP_GEOMETRY_PREPARE ",JSON.stringify(report))
	preparer.queue_free()
	for frame in range(4): await process_frame
	quit(0 if bool(report.get("ok",false)) else 1)
