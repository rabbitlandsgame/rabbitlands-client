extends SceneTree
## Service locations remain visible before their NPCs arrive, in every map view.

const ServiceOverlay := preload("res://src/ui/service_map_overlay.gd")
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
	state.current_map = "landfall"
	state.map_objects = {}
	var records: Array = main._current_service_records()
	expect(records.size() == 2, "Landfall has the tool shop and tavern")
	for record: Dictionary in records:
		var wanted: Vector2i = Vector2i(117, 216) if record.category == "general_store" else Vector2i(112, 202)
		expect(Vector2i(record.serverTile[0], record.serverTile[1]) == wanted, "Service dot uses the NPC's real post")
	var marks: Array[Dictionary] = main._collect_minimap_marks()
	expect(marks.filter(func(mark: Dictionary) -> bool: return mark.get("colour") == ServiceOverlay.SHOP_COLOUR).size() == 1,
		"Minimap has a green tool shop without a replicated NPC")
	expect(marks.filter(func(mark: Dictionary) -> bool: return mark.get("colour") == ServiceOverlay.TAVERN_COLOUR).size() == 1,
		"Minimap has an orange tavern without a replicated NPC")
	# A nearby server NPC must not add a second generic blue dot at the same shop.
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	main.actor_nodes[999] = actor
	state.actors[999] = {"name": "Rowan Hale", "kind": 2, "actor_type": 302}
	expect(main._collect_minimap_marks().size() == marks.size(), "Merchant arrival does not duplicate its service dot")
	state.actors[999]["kind"] = 1
	expect(main._collect_minimap_marks().size() == marks.size() + 1, "A player sharing the merchant name retains their dot")
	main.actor_nodes.erase(999)
	state.actors.erase(999)
	actor.queue_free()
	main.map_marker_overlay.set_live_marks(marks)
	var dots: Array[Dictionary] = main.map_marker_overlay._live_overlay._marks
	expect(dots.filter(func(mark: Dictionary) -> bool: return mark.get("colour") == ServiceOverlay.SHOP_COLOUR).size() == 1,
		"Live Tab map retains the green tool shop")
	var waypoints: Array[Dictionary] = main._collect_map_waypoints()
	expect(waypoints.any(func(mark: Dictionary) -> bool: return mark.get("label") == "Rowan's Tools"), "Live Tab shop has a hover label")
	expect(waypoints.any(func(mark: Dictionary) -> bool: return mark.get("label") == "Bettany Orl's Tavern"), "Live Tab tavern has a hover label")
	state.current_map = "ringholm"
	main._preview_region(main._region_index_for_map("landfall"))
	await process_frame
	var overlay: Control = main._service_preview_overlay
	expect(overlay._marks.size() == 2, "Landfall preview retains both service dots")
	for record: Dictionary in overlay._marks:
		var point: Variant = overlay.mark_point(record)
		expect(point is Vector2, "Service dot lies on the preview image")
		if point is Vector2:
			expect(main._preview_tile_at(point) == Vector2i(record.serverTile[0], record.serverTile[1]),
				"Preview service dot projects to the real merchant tile")
			expect(overlay.label_at(point) == record.label, "Preview service identifies its merchant")
	await capture("landfall-services-map.png", overlay)
	state.current_map = "landfall"
	main._configure_continent_overlay(main._active_continent_data())
	expect(main._service_continent_overlay._marks.size() == 2, "Landfall overview retains both service dots")
	expect(main._current_service_marks().size() == 2, "Returning to Landfall restores its service dots")
	state.current_map = "pinebrow"
	expect(main._current_service_marks().is_empty(), "Landfall service dots do not leak to other maps")
	print("Service map markers: ", failures, " failures")
	await ContinentChunkStream.drain_workers(self)
	main.queue_free()
	await process_frame
	await process_frame
	quit(1 if failures else 0)

func capture(name: String, overlay: Control) -> void:
	if captures.is_empty():
		return
	for unused in range(5):
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	expect(image.save_png(captures.path_join(name)) == OK, "Map preview capture saves")
	for record: Dictionary in overlay._marks:
		var point: Vector2 = overlay.get_global_transform() * (overlay.mark_point(record) as Vector2)
		var actual := image.get_pixelv(Vector2i(point))
		var wanted := ServiceOverlay.dot_colour(record)
		expect(Vector3(actual.r, actual.g, actual.b).distance_to(Vector3(wanted.r, wanted.g, wanted.b)) < 0.1,
			"Rendered service dot has its legend color")
