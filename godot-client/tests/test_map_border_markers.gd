extends SceneTree
## Walking borders lose their old X; ferries and real interior exits retain it.

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	main.game_view.show()
	var state: Node = root.get_node("AppState")
	var walking := 0
	var ferries := 0
	for link: Dictionary in main.exterior_stream.links:
		if not bool(link.get("seamless", false)):
			continue
		var visual_only := bool(link.get("visualOnly", false))
		for index: int in 2:
			var source := str(link.ends[index].map)
			var destination := str(link.ends[1 - index].map)
			var entry: Dictionary = main.map_registry.get(destination, {})
			var label := str(entry.get("label", destination.replace("_", " ").capitalize()))
			state.current_map = source
			state.map_objects = {}
			main._sync_map_objects()
			state.map_objects = {60000: {"object_id": 60000,
				"kind": EloriaProtocol.MAP_OBJECT_EXIT, "x": 5, "y": 5,
				"label": label, "detail": "The way to "+label+"."}}
			main._sync_map_objects()
			var marks: Array[Dictionary] = main._collect_minimap_marks()
			var exits := marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"exit")
			var waypoints: Array[Dictionary] = main._collect_map_waypoints()
			var crosses := waypoints.filter(func(mark: Dictionary) -> bool: return mark.get("glyph") == "X")
			expect(exits.size() == (1 if visual_only else 0), source+" to "+destination+" minimap exit visibility")
			expect(crosses.size() == (1 if visual_only else 0), source+" to "+destination+" Tab map exit visibility")
			if visual_only:
				ferries += 1
			else:
				walking += 1
			if source in ["landfall", "pinebrow", "spindle_hill", "boarsend"]:
				expect(marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance").size() == 1,
					"Tan entrance remains visible alongside the walking border")
	expect(walking > 0 and ferries > 0, "Both walking borders and coastlines were checked")
	# A doorway exit on the shared interior is still a specific place to leave.
	state.current_map = "landfall_insides"
	state.map_objects = {}
	main._sync_map_objects()
	state.map_objects = {60000: {"object_id": 60000,
		"kind": EloriaProtocol.MAP_OBJECT_EXIT, "x": 5, "y": 5,
		"label": "Landfall", "detail": "The way to Landfall."}}
	main._sync_map_objects()
	var interior_marks: Array[Dictionary] = main._collect_minimap_marks()
	var interior_waypoints: Array[Dictionary] = main._collect_map_waypoints()
	expect(interior_marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"exit").size() == 1,
		"A real interior exit retains its minimap marker")
	expect(interior_waypoints.size() == 1 and interior_waypoints[0].glyph == "X",
		"A real interior exit retains its Tab map marker")
	print("Map border markers: ", checks, " checks, ", failures, " failures")
	await ContinentChunkStream.drain_workers(self)
	main.queue_free()
	await process_frame
	await process_frame
	quit(1 if failures else 0)
