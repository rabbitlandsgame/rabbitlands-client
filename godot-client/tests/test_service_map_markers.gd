extends SceneTree
## Service locations remain visible before their NPCs arrive, in every map view,
## in their category's colour; an interior's shopkeepers are drawn inside it,
## those of the section the player stands in only.

const ServiceOverlay := preload("res://src/ui/service_map_overlay.gd")
const EntranceOverlay := preload("res://src/ui/entrance_map_overlay.gd")
## Landfall's plaza shops (scene NPC markers with a mapCategory): name -> [category, post tile].
const LANDFALL := {
	"Bettany Orl": ["tavern", Vector2i(112, 202)],
	"Mara Vell": ["general_store", Vector2i(117, 212)],
	"Rowan Hale": ["general_store", Vector2i(117, 216)],
}
var failures := 0
var captures := ""

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

## Shop dots of one colour; a building door in a shop's colour is an entrance, not one of these.
func service_dots(marks: Array[Dictionary], colour: Color) -> int:
	var count := 0
	for mark: Dictionary in marks:
		if mark.get("type") == &"npc" and mark.get("colour") == colour:
			count += 1
	return count

func run() -> void:
	root.size = Vector2i(1280, 800)
	var args := OS.get_cmdline_user_args()
	if args.size() == 2 and args[0] == "--captures":
		captures = args[1]
		DirAccess.make_dir_recursive_absolute(captures)
	# One table: every category a dot is drawn in, and the doors of the shops.
	expect(ServiceOverlay.CATEGORY_COLOURS.size() == 6, "Six shop categories have a colour")
	expect(ServiceOverlay.CATEGORY_COLOURS.tavern == ServiceOverlay.TAVERN_COLOUR
		and ServiceOverlay.CATEGORY_COLOURS.general_store == ServiceOverlay.SHOP_COLOUR,
		"The tavern and general store keep their colours")
	expect(ServiceOverlay.dot_colour({"category": "flower_shop"}) == Color("e687da"), "A flower shop dot is pink")
	expect(ServiceOverlay.dot_colour({"category": "magic_shop"}) == Color("e2cf48"), "A magic shop dot is yellow")
	expect(ServiceOverlay.dot_colour({"category": "blacksmith"}) == Color("9d73d8"), "A blacksmith dot is purple")
	expect(ServiceOverlay.door_colour({"category": "blacksmith"}) == Color("9d73d8"), "A smithy's door is purple")
	expect(ServiceOverlay.dot_colour({"category": "bookshop"}) == Color("e75252")
		and ServiceOverlay.door_colour({"category": "bookshop"}) == Color("e75252"),
		"A bookshop and its door take the legend's red Books dot")
	expect(ServiceOverlay.door_colour({}) == EntranceOverlay.DOT_COLOUR, "A door into no shop is the tan entrance dot")
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	main.game_view.show()
	main.get_node("LoginPanel").hide()
	main.full_map.show()
	var legend: RichTextLabel = main.find_child("MapLegend", true, false) as RichTextLabel
	for category: String in ServiceOverlay.CATEGORY_COLOURS:
		var colour: Color = ServiceOverlay.CATEGORY_COLOURS[category]
		expect(legend != null and legend.text.contains("[color=#%s]●[/color]" % colour.to_html(false))
			and not legend.text.contains("[color=#%s]◆[/color]" % colour.to_html(false)),
			"The legend has a round %s dot" % category)
	var state: Node = root.get_node("AppState")
	state.current_map = "landfall"
	state.map_objects = {}
	var records: Array = main._current_service_records()
	expect(records.size() == LANDFALL.size(), "Landfall has the tavern and both general stores: %d" % records.size())
	for record: Dictionary in records:
		var wanted: Array = LANDFALL.get(str(record.name), ["", Vector2i(-1, -1)])
		expect(record.category == wanted[0], "%s keeps its category" % str(record.name))
		expect(Vector2i(record.serverTile[0], record.serverTile[1]) == wanted[1], "Service dot uses the NPC's real post")
	var marks: Array[Dictionary] = main._collect_minimap_marks()
	expect(service_dots(marks, ServiceOverlay.SHOP_COLOUR) == 2,
		"Minimap has both green general stores without a replicated NPC")
	expect(service_dots(marks, ServiceOverlay.TAVERN_COLOUR) == 1,
		"Minimap has an orange tavern without a replicated NPC")
	# A nearby server NPC must not add a second generic blue dot at the same shop.
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	main.actor_nodes[999] = actor
	state.actors[999] = {"name": "Rowan Hale", "kind": 2, "actor_type": 302}
	expect(main._collect_minimap_marks().size() == marks.size(), "Merchant arrival does not duplicate its service dot")
	state.actors[999]["kind"] = 1
	expect(main._collect_minimap_marks().size() == marks.size() + 1, "A player sharing the merchant name retains their dot")
	state.actors[999]["kind"] = 2
	main.map_marker_overlay.set_live_marks(marks)
	var dots: Array[Dictionary] = main.map_marker_overlay._live_overlay._marks
	expect(service_dots(dots, ServiceOverlay.SHOP_COLOUR) == 2, "Live Tab map retains the green general stores")
	var waypoints: Array[Dictionary] = main._collect_map_waypoints()
	expect(waypoints.any(func(mark: Dictionary) -> bool: return mark.get("label") == "Rowan's Tools"), "Live Tab shop has a hover label")
	expect(waypoints.any(func(mark: Dictionary) -> bool: return mark.get("label") == "Bettany Orl's Tavern"), "Live Tab tavern has a hover label")
	state.current_map = "ringholm"
	main._preview_region(main._region_index_for_map("landfall"))
	await process_frame
	var overlay: Control = main._service_preview_overlay
	expect(overlay._marks.size() == LANDFALL.size(), "Landfall preview retains every service dot")
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
	expect(main._service_continent_overlay._marks.size() == LANDFALL.size(), "Landfall overview retains every service dot")
	expect(main._current_service_marks().size() == LANDFALL.size(), "Returning to Landfall restores its service dots")
	# The published interiors' shopkeepers all have a category the client draws, and a section.
	var published: Dictionary = main._v2_cartography.get("interiors", {}) as Dictionary
	for map_id: String in published:
		for record: Dictionary in (published[map_id] as Dictionary).get("serviceMarkers", []):
			expect(ServiceOverlay.CATEGORY_COLOURS.has(str(record.get("category", "")))
				and not str(record.get("section", "")).is_empty(),
				"%s shopkeeper %s has a drawn category and a section" % [map_id, str(record.get("name", ""))])
	await check_interior(main, state)
	state.current_map = "pinebrow"
	expect(main._current_service_marks().is_empty(), "Landfall service dots do not leak to other maps")
	main.actor_nodes.erase(999)
	state.actors.erase(999)
	actor.queue_free()
	print("Service map markers: ", failures, " failures")
	await ContinentChunkStream.drain_workers(self)
	main.queue_free()
	await process_frame
	await process_frame
	quit(1 if failures else 0)

## An interior has no tab map row: its shopkeepers come from cartography's
## `interiors` block, and the section the player stands in decides which draw.
## Two stand-in shopkeepers in two sections, so the rule is checked whatever
## the town's published cast is.
func check_interior(main: Control, state: Node) -> void:
	var smith := {"label": "The forge", "name": "Test Smith", "category": "blacksmith",
		"position": [60.5, 263.5], "height": 0.0, "serverTile": [60, 60], "section": "smithy"}
	var florist := {"label": "The flower shop", "name": "Test Florist", "category": "flower_shop",
		"position": [160.5, 263.5], "height": 0.0, "serverTile": [160, 60], "section": "market"}
	var saved: Variant = main._v2_cartography.get("interiors")
	main._v2_cartography["interiors"] = {"landfall_town": {"serviceMarkers": [smith, florist]}}
	state.current_map = "landfall_town"
	expect(main._region_index_for_map("landfall_town") < 0, "An interior has no tab map row")
	# Stand the player in a section without loading the map: the sections'
	# own list and current id, as configure() and update() would leave them.
	var sections: Variant = main.secret_sections
	sections.reset()
	expect(main._current_service_records().size() == 2, "Before its sections are known, every shopkeeper of the interior is drawn")
	sections._sections.append({"id": "smithy", "min": Vector2(40, 240), "max": Vector2(80, 280)})
	sections._sections.append({"id": "market", "min": Vector2(140, 240), "max": Vector2(180, 280)})
	sections._current = "smithy"
	var marks: Array[Dictionary] = main._current_service_marks()
	expect(marks.size() == 1 and marks[0].colour == ServiceOverlay.CATEGORY_COLOURS.blacksmith
		and marks[0].label == "The forge" and marks[0].type == &"npc",
		"The smithy draws its purple blacksmith only")
	expect(marks.size() == 1 and (marks[0].position as Vector3).is_equal_approx(Vector3(60.5, 0.0, 263.5)),
		"The shopkeeper's dot stands on its post")
	# The blacksmith's own blue NPC dot is hidden under the shop dot, by name.
	state.actors[999] = {"name": "Test Smith", "kind": 2, "actor_type": 302}
	var with_smith: int = main._collect_minimap_marks().size()
	state.actors[999]["kind"] = 1
	expect(main._collect_minimap_marks().size() == with_smith + 1, "The interior shopkeeper's blue dot is hidden by name")
	state.actors[999]["kind"] = 2
	expect(main._collect_map_waypoints().any(func(mark: Dictionary) -> bool: return mark.get("label") == "The forge"),
		"The interior shop is named on hover on the Tab map")
	sections._current = "market"
	marks = main._current_service_marks()
	expect(marks.size() == 1 and marks[0].colour == ServiceOverlay.CATEGORY_COLOURS.flower_shop,
		"Walking into the market draws its pink flower shop instead")
	state.current_map = "landfall"
	expect(main._current_service_marks().size() == LANDFALL.size(), "Leaving the interior restores Landfall's shops")
	sections.reset()
	if saved == null:
		main._v2_cartography.erase("interiors")
	else:
		main._v2_cartography["interiors"] = saved
	await process_frame

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
