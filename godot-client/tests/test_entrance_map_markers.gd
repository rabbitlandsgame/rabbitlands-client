extends SceneTree
## Entrances remain discoverable before server objects arrive, in every map view.

## Every cave door, from the underground's one source: map -> [[name, x, y, object], ...]. A section has
## several doors (`entrances`) or the old single `entrance` (underground_source.py), so a map may have several.
const SOURCE := "res://../eloria-assets/maps/continent-v2/_continent_v2/content/underground.json"
var EXPECTED := {}
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
	var plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
	var doors := 0
	for section: Dictionary in plan.sections:
		var listed: Array = section.get("entrances", [section.entrance] if section.has("entrance") else [])
		for door: Dictionary in listed:
			if not EXPECTED.has(str(door.map)):
				EXPECTED[str(door.map)] = []
			(EXPECTED[str(door.map)] as Array).append([str(section.name), int(door.tile[0]), int(door.tile[1]),
				int(door.object)])
			doors += 1
	expect(doors >= (plan.sections as Array).size() / 2 and EXPECTED.size() >= 4,
		"The caves' doors stand on the exterior maps: %d doors on %d maps" % [doors, EXPECTED.size()])
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
		var wanted_doors: Array = EXPECTED[mid]
		var count := wanted_doors.size()
		var records: Array = main._current_entrance_records()
		expect(records.size() == count, "%s has its %d entrances: %d" % [mid, count, records.size()])
		if records.size() != count:
			continue
		var by_object := {}
		for record: Dictionary in records:
			by_object[int(record.objectId)] = record
		var objects := {}
		for door: Array in wanted_doors:
			var record: Dictionary = by_object.get(int(door[3]), {})
			var wanted := Vector2i(int(door[1]), int(door[2]))
			expect(not record.is_empty() and record.label == door[0]
				and Vector2i(record.serverTile[0], record.serverTile[1]) == wanted,
				"%s entrance %d name and coordinates" % [mid, int(door[3])])
			objects[int(door[3])] = {"object_id": door[3], "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
				"x": wanted.x, "y": wanted.y, "label": "Portal", "detail": "Beyond it lies " + str(door[0]) + "."}
		var marks: Array[Dictionary] = main._collect_minimap_marks()
		var entrances := marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance")
		expect(entrances.size() == count, "Every entrance is on the minimap before server objects arrive")
		state.map_objects = objects
		main._sync_map_objects()
		marks = main._collect_minimap_marks()
		entrances = marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance")
		expect(entrances.size() == count, "Server doorways do not duplicate the permanent entrance dots")
		expect(marks.filter(func(mark: Dictionary) -> bool: return str(mark.get("glyph", "")) == "P").is_empty(), "Cave entrances use the tan dot instead of P")
		var waypoints: Array[Dictionary] = main._collect_map_waypoints()
		var entrance_waypoints := waypoints.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance")
		var names := wanted_doors.map(func(door: Array) -> String: return str(door[0]))
		expect(entrance_waypoints.size() == count and entrance_waypoints.all(
			func(mark: Dictionary) -> bool: return names.has(str(mark.label))),
			"Live Tab map has the permanent entrance names")
		main.map_marker_overlay.set_live_marks(marks)
		expect(main.map_marker_overlay._live_overlay._marks.filter(func(mark: Dictionary) -> bool: return mark.get("type") == &"entrance").is_empty(), "Full map draws each entrance once")
		# Preview the door's region while standing on another map (Ringholm has a cave of its own).
		state.current_map = "ringholm" if mid != "ringholm" else "landfall"
		main._preview_region(main._region_index_for_map(mid))
		await process_frame
		var overlay: Control = main._entrance_preview_overlay
		expect(overlay._marks.size() == count, "Region preview has every entrance of " + mid)
		for mark: Dictionary in overlay._marks:
			var door_index := wanted_doors.find_custom(func(door: Array) -> bool: return int(door[3]) == int(mark.objectId))
			expect(door_index >= 0 and mark.label == wanted_doors[door_index][0], "Region preview has the entrance name")
			var point: Variant = overlay.mark_point(mark)
			expect(point is Vector2, "Preview entrance lies on the image")
			if point is Vector2 and door_index >= 0:
				expect(main._preview_tile_at(point) == Vector2i(int(wanted_doors[door_index][1]),
					int(wanted_doors[door_index][2])), "Preview dot projects to the real doorway tile")
		await capture(mid+"-entrance-map.png")
	state.current_map = "landfall"
	main._configure_continent_overlay(main._active_continent_data())
	expect(main._entrance_continent_overlay._marks.size() == doors,
		"Landfall overview labels every entrance: %d of %d" % [main._entrance_continent_overlay._marks.size(), doors])
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
