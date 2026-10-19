extends SceneTree
## Storage uses the legend's brown dot on live maps and static map previews.

var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var chest := MapObject3D.new()
	chest.kind = EloriaProtocol.MAP_OBJECT_INTERACTIVE
	chest.label = "Storage"
	expect(chest.map_glyph().is_empty(), "storage DTO uses a dot on live Tab and minimap overlays")
	expect(chest.map_dot_colour() == Color("d6bb7a"), "storage dot has the existing legend colour")
	chest.label = "Other interactive"
	expect(chest.map_glyph().is_empty(), "ordinary interactives retain their dot")
	chest.free()
	var overlay: Control = load("res://src/ui/storage_map_overlay.gd").new()
	root.add_child(overlay)
	overlay.size = Vector2(800, 600)
	var mark := {"label": "Quay storehouse", "position": [50, 25]}
	overlay.configure(Vector2.ZERO, Vector2(100, 50), Vector2(1000, 500), [mark])
	expect(overlay.mark_point(mark) == Vector2(400, 300), "preview dot follows centered keep-aspect image")
	expect(overlay.label_at(Vector2(400, 300)) == "Quay storehouse", "preview tooltip identifies the chest")
	expect(overlay.label_at(Vector2.ZERO).is_empty(), "distant preview positions have no chest tooltip")
	expect(overlay.mark_point({"position": [150, 25]}) == null, "out-of-frame storage is not drawn")
	overlay.queue_free()
	# Parse the real app and verify it binds a server storage object to both overlays.
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	var state: Node = root.get_node("AppState")
	state.current_map = "landfall"
	state.map_objects = {22: {"object_id": 22, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x": 130, "y": 229, "label": "Storage", "detail": "Shared storage"}}
	main._sync_map_objects()
	main.game_view.show()
	var legend: RichTextLabel = main.find_child("MapLegend", true, false) as RichTextLabel
	expect(legend != null and legend.text.contains("[color=#d6bb7a]•[/color] Storage"),
		"Storage legend uses the same brown dot")
	expect(legend != null and not legend.text.contains("Storage chest"), "legend has one storage entry")
	var minimap_marks: Array[Dictionary] = main._collect_minimap_marks()
	var minimap_chests := 0
	for mark_value: Dictionary in minimap_marks:
		if mark_value.get("colour", Color.WHITE) == MapObject3D.STORAGE_COLOUR:
			minimap_chests += 1
			expect(str(mark_value.get("glyph", "")).is_empty(), "minimap storage is a dot")
	expect(minimap_chests == 1, "minimap marks include the server's brown storage dot")
	main.map_marker_overlay.set_live_marks(minimap_marks)
	var live_dots: Array[Dictionary] = main.map_marker_overlay._live_overlay._marks
	var live_storage := 0
	for live_dot: Dictionary in live_dots:
		if live_dot.get("colour", Color.WHITE) == MapObject3D.STORAGE_COLOUR:
			live_storage += 1
	expect(live_storage == 1, "live Tab overlay retains the brown storage dot")
	var waypoints: Array[Dictionary] = main._collect_map_waypoints()
	var storage: Array[Dictionary] = []
	for waypoint: Dictionary in waypoints:
		if waypoint.get("label", "") == "Storage":
			storage.append(waypoint)
	expect(storage.size() == 1, "live storage dot retains one hover label")
	if storage.size() == 1:
		expect(str(storage[0].get("glyph", "")).is_empty(), "storage hover entry has no letter glyph")
	var storage_maps := ["landfall", "greenlight", "hearthcroft", "stagheath", "coilmere"]
	main._ensure_cartography_textures()
	for mid: String in storage_maps:
		# A different current area makes this the static region-preview path.
		state.current_map = "pinebrow"
		main._preview_region(main._region_index_for_map(mid))
		var preview: Control = main._storage_preview_overlay
		expect(preview._marks.size() == 1, mid + " Tab preview includes its storage")
	state.current_map = "landfall"
	main._configure_continent_overlay(main._active_continent_data())
	expect(main._storage_continent_overlay._marks.size() == 5, "continent overview includes all five storages")
	print("storage map markers: %d failures" % failures)
	quit(1 if failures else 0)
