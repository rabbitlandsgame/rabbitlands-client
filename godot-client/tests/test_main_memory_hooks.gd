extends SceneTree
## Wave 2 stage A hook commit (group A2), MEM-M3: Main's diagnostics carry the
## memory census. On a real main.tscn:
## - client_diagnostic_snapshot() has a "memory" row (MemoryCensus.snapshot)
##   whose class is this session's memory class, whose retention caches are the
##   rows Main already collected (not asked twice), and whose WorldPark and
##   crowd park rows read Main's own nodes;
## - _start_client_diagnostics() records one "memory_class" diagnostic right
##   after "main_scene_ready" (the runner also finds it in the log:
##   `client_diagnostic {"event":"memory_class", ...}`).
## The census itself is tested in test_memory_census.gd.

const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	for frame: int in 4:
		await process_frame
	var row: Dictionary = main.client_diagnostic_snapshot()
	var memory: Dictionary = row.get("memory", {})
	_expect(not memory.is_empty() and memory.get("available", true) != false, "the snapshot carries the memory census")
	_expect(str(memory.get("class", "")) == MemoryBudgets.memory_class()
		and str(memory.get("class", "")) in ["small", "medium", "large"], "its class is this session's memory class")
	var caches: Dictionary = memory.get("caches", {})
	for name: String in ["actor_scenes", "animations", "world_meshes", "world_textures", "rl_identity_bake",
			"rl_heads", "world_park", "crowd_park"]:
		_expect(caches.has(name), "the census has a %s row" % name)
	var retention: Dictionary = row.get("resource_retention", {})
	for name: String in ["actor_scenes", "animations", "world_meshes", "world_textures"]:
		var given: Dictionary = retention.get(name, {})
		var census: Dictionary = caches.get(name, {})
		_expect(int(census.get("entries", -2)) == int(given.get("entries", -1))
			and int(census.get("bytes", -2)) == int(given.get("bytes", -1)),
			"%s is read from the retention row Main already collected" % name)
	var park: Dictionary = caches.get("world_park", {})
	_expect(int(park.get("budget", -1)) == int(main.world_park.budget_bytes) and int(park.get("budget", -1)) > 0
		and bool(park.get("preload_enabled", not main.world_park.preload_enabled)) == bool(main.world_park.preload_enabled),
		"the WorldPark row reads Main's park (budget %d)" % int(park.get("budget", -1)))
	var crowd_row: Dictionary = caches.get("crowd_park", {})
	_expect(int(crowd_row.get("budget", -1)) == int(main.crowd.park_limit)
		and int(crowd_row.get("entries", -1)) == int(main.crowd.parked_count()),
		"the crowd park row reads Main's crowd (limit %d)" % int(crowd_row.get("budget", -1)))
	_expect(int(memory.get("census_usec", -1)) >= 0, "the census reports its own cost")
	# The one-per-session class record, right after main_scene_ready.
	var source := FileAccess.get_file_as_string("res://src/app/main.gd")
	var start := source.get_slice("func _start_client_diagnostics()", 1).get_slice("\nfunc ", 0)
	_expect(start.find("Diagnostics.record(\"memory_class\", MemoryCensus.class_record())")
		> start.find("Diagnostics.record(\"main_scene_ready\")") and start.find("main_scene_ready") >= 0,
		"_start_client_diagnostics records memory_class after main_scene_ready")
	var record: Dictionary = preload("res://src/runtime/memory_census.gd").class_record()
	_expect(str(record.get("class", "")) == MemoryBudgets.memory_class() and record.has("budgets")
		and record.has("physical_bytes"), "the class record names the class, its budgets and the physical memory")
	main.queue_free()
	await process_frame
	await process_frame
	print("main memory hooks: %d checks, %s" % [checks, "PASS" if failures == 0 else "FAIL (%d)" % failures])
	quit(failures)
