extends SceneTree
## Entrances remain discoverable before server objects arrive, in every map view.

const EXPECTED := {
	"landfall": ["Lantern Mine", 332, 86],
	"pinebrow": ["Pinebrow Deep Workings", 537, 490],
	"coilmere": ["Spindle Mineral Cavern", 230, 754],
	"boarsend": ["Boarsend Old Barrow", 825, 489],
}
var failures := 0
var captures := ""

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	root.size = Vector2i(1280, 800)
	var args := OS.get_cmdline_user_args()
	if args.size() == 2 and args[0] == "--captures":
		captures = args[1]
		DirAccess.make_dir_recursive_absolute(captures)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	main.game_view.show()
	main.get_node("LoginPanel").hide()
	main.full_map.show()
	var state: Node = root.get_node("AppState")
	var legend: RichTextLabel = main.find_child("MapLegend", true, false)
	expect(legend.text.contains("[color=#e8d09b]•[/color] Insides entrance"), "Legend describes the tan entrance dot")
	for mid: String in EXPECTED:
		state.current_map = mid
		state.map_objects = {}
		main._sync_map_objects()
		var records: Array = main._current_entrance_records()
		expect(records.size() == 1, mid+" has one entrance")
		if records.is_empty():
			continue
		var record: Dictionary = records[0]
		var label: String = EXPECTED[mid][0]
		var wanted := Vector2i(EXPECTED[mid][1], EXPECTED[mid][2])
		expect(record.label == label and Vector2i(record.serverTile[0], record.serverTile[1]) == wanted, mid+" entrance name and coordinates")
		var marks: Array[Dictionary] = main._collect_minimap_marks()
		var entrances := marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance")
		expect(entrances.size() == 1, "Entrance is on the minimap before server objects arrive")
		state.map_objects = {int(record.objectId): {"object_id":record.objectId,
			"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x":wanted.x, "y":wanted.y,
			"label":"Portal", "detail":"Beyond it lies "+label+"."}}
		main._sync_map_objects()
		marks = main._collect_minimap_marks()
		entrances = marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance")
		expect(entrances.size() == 1, "Server doorway does not duplicate the permanent entrance dot")
		expect(marks.filter(func(mark: Dictionary) -> bool: return str(mark.get("glyph", "")) == "P").is_empty(), "Cave entrance uses the tan dot instead of P")
		var waypoints: Array[Dictionary] = main._collect_map_waypoints()
		var entrance_waypoints := waypoints.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance")
		expect(entrance_waypoints.size() == 1 and entrance_waypoints[0].label == label, "Live Tab map has the permanent entrance name")
		main.map_marker_overlay.set_live_marks(marks)
		expect(main.map_marker_overlay._live_overlay._marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance").is_empty(), "Full map draws each entrance once")
		state.current_map = "ringholm"
		main._preview_region(main._region_index_for_map(mid))
		await process_frame
		var overlay: Control = main._entrance_preview_overlay
		expect(overlay._marks.size() == 1 and overlay._marks[0].label == label, "Region preview has the entrance name")
		var point: Variant = overlay.mark_point(overlay._marks[0])
		expect(point is Vector2, "Preview entrance lies on the image")
		if point is Vector2:
			expect(main._preview_tile_at(point) == wanted, "Preview dot projects to the real doorway tile")
		await capture(mid+"-entrance-map.png")
	state.current_map = "landfall"
	main._configure_continent_overlay(main._active_continent_data())
	expect(main._entrance_continent_overlay._marks.size() == 4, "Landfall overview labels all four entrances")
	main._show_continent_view()
	await capture("landfall-entrances-overview.png")
	print("Entrance map markers: ", failures, " failures")
	await ContinentChunkStream.drain_workers(self)
	main.queue_free()
	await process_frame
	await process_frame
	quit(1 if failures else 0)

func capture(name: String) -> void:
	if captures.is_empty():
		return
	for unused in range(5):
		await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(captures.path_join(name)) == OK, "Map preview capture saves")
