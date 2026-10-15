extends SceneTree
## The map window's continent and its region previews are the client's own tab
## maps, and they work the way the legacy map window did: the small map in the
## sidebar swaps between the continent and the map you stand on, a click on a
## region of the continent opens that region's own top-down map, and the cursor
## names server tiles over a preview as it does over the live map.

var failures: int = 0
var checks: int = 0
var _landfall_checks_done := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		quit(1)
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var app_state: Node = root.get_node("AppState")
	(main.get_node("GameView") as Control).show()
	var full_map: Control = main.get_node("GameView/FullMap") as Control
	var map_image: TextureRect = main.get_node(
		"GameView/FullMap/MapLayout/MapImage") as TextureRect
	var region_preview: TextureRect = main.get_node(
		"GameView/FullMap/MapLayout/RegionPreview") as TextureRect
	var continent_view: Control = main.get_node(
		"GameView/FullMap/MapLayout/ContinentView") as Control
	var continent_image: TextureRect = main.get_node(
		"GameView/FullMap/MapLayout/ContinentView/ContinentImage") as TextureRect
	var continent_button: TextureButton = main.get_node(
		"GameView/FullMap/MapLayout/Sidebar/SidebarContent/ContinentButton") as TextureButton
	var map_title: Label = main.get_node("GameView/FullMap/MapLayout/MapTitle") as Label
	var map_coordinates: Label = main.get_node(
		"GameView/FullMap/MapLayout/Sidebar/SidebarContent/MapCoordinates") as Label
	var full_map_viewport: SubViewport = main.get_node("GameView/FullMapViewport") as SubViewport

	# The cartography: every exterior region, each drawn from its own tab map.
	var cartography: Dictionary = main.get("cartography") as Dictionary
	var regions: Array = main.get("cartography_regions") as Array
	_expect(int(cartography.get("schemaVersion", 0)) == 2, "cartography is the tab-map schema")
	var continent: Dictionary = cartography.get("continent", {}) as Dictionary
	var image_size: Array = continent.get("imageSize", []) as Array
	_expect(image_size.size() == 2 and int(image_size[0]) > 0 and int(image_size[1]) > 0,
		"the continent picture states its size")
	var continent_path: String = str(continent.get("texture", ""))
	_expect(continent_path.ends_with("continent-map.webp") and not continent_path.contains("concept"),
		"the continent is the composed tab maps, not the concept painting")
	# The rebuilt continent's isles have rows of their own frame, with no
	# rectangle on this picture, after every row that has one.
	var on_picture: int = 0
	for region_value: Variant in regions:
		if str((region_value as Dictionary).get("frame", "")).is_empty():
			on_picture += 1
	_expect(on_picture == 12, "every exterior region is on the continent")
	_expect(not main.has_node("GameView/FullMap/MapLayout/ContinentView/RegionButtons"),
		"the region button list is gone; the continent itself is the index")
	var overlay: Control = main.get_node(
		"GameView/FullMap/MapLayout/ContinentView/ContinentMap") as Control
	_expect(overlay != null and int(overlay.call("region_count")) == on_picture,
		"the continent overlay knows every region on its picture")
	var wrapped: PackedStringArray = overlay.call("_label_lines", overlay.get_theme_default_font(), "Amethyst Barrens", 90.0)
	_expect(wrapped.size() == 2 and wrapped[0] == "Amethyst" and wrapped[1] == "Barrens",
		"long adjacent-region labels wrap without truncation")
	_expect(region_preview.mouse_filter != Control.MOUSE_FILTER_IGNORE,
		"a preview takes the cursor, so it can name tiles")
	for region_value: Variant in regions:
		var region: Dictionary = region_value as Dictionary
		var name: String = str(region.get("name", ""))
		var tab_map: Dictionary = region.get("tabMap", {}) as Dictionary
		var texture_path: String = str(tab_map.get("texture", ""))
		_expect(not texture_path.contains("concept") and not region.has("preview"),
			name + " is drawn from its tab map, not concept art")
		_expect(FileAccess.file_exists(ProjectSettings.globalize_path(texture_path)),
			name + "'s tab map exists on disk")
		var rect: Array = region.get("continentRect", []) as Array
		if not str(region.get("frame", "")).is_empty():
			_expect(rect.is_empty(), name + " of another frame has no rectangle on this picture")
			continue
		_expect(rect.size() == 4 and int(rect[0]) >= 0 and int(rect[1]) >= 0
			and int(rect[0]) + int(rect[2]) <= int(image_size[0])
			and int(rect[1]) + int(rect[3]) <= int(image_size[1]),
			name + " has a rectangle on the continent picture")
	_expect(continent_image.texture == null and continent_button.texture_normal == null,
		"the continent picture is not decoded before the map window opens")

	app_state.set("current_map", "four_gates")
	main.call("_toggle_full_map")
	await process_frame
	_expect(full_map.visible and map_image.visible and not continent_view.visible,
		"the map window opens on the live map")
	var continent_texture: Texture2D = continent_button.texture_normal
	_expect(continent_texture != null and continent_texture.get_size()
		== Vector2(float(image_size[0]), float(image_size[1])),
		"the small map shows the composed continent at its stated size")
	_expect(continent_image.texture == continent_texture,
		"the big continent view holds the same picture")

	# The small map swaps the two views, as the legacy map window's did.
	main.call("_on_continent_button_pressed")
	_expect(continent_view.visible and not map_image.visible and not region_preview.visible,
		"the small map opens the continent")
	_expect(continent_button.texture_normal is ViewportTexture,
		"on the continent the small map shows the live current map")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"the continent view idles the world render")
	_expect(map_title.text == "NYMARA CONTINENT", "the title names the continent")
	main.call("_on_continent_button_pressed")
	_expect(map_image.visible and not continent_view.visible
		and continent_button.texture_normal == continent_texture,
		"pressing the small map again returns to the current map")

	# A click on a region of the continent opens that region's own tab map.
	main.call("_show_continent_view")
	await process_frame
	var mirrorhold_index: int = _index_of(regions, "mirrorhold")
	var display: Rect2 = overlay.call("region_rect", mirrorhold_index) as Rect2
	_expect(display.size.x > 0.0 and display.size.y > 0.0,
		"Mirrorhold has a rectangle on the drawn continent")
	var centre: Vector2 = display.get_center()
	_expect(int(overlay.call("region_at", centre)) == mirrorhold_index,
		"the middle of Mirrorhold's rectangle is Mirrorhold")
	_expect(int(overlay.call("region_at", Vector2(-50.0, -50.0))) == -1,
		"off the picture there is no region")
	var motion := InputEventMouseMotion.new()
	motion.position = centre
	overlay.call("_gui_input", motion)
	_expect(map_coordinates.text.contains("Mirrorhold"),
		"hovering a region names it in the sidebar")
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = centre
	overlay.call("_gui_input", click)
	_expect(region_preview.visible and not continent_view.visible and not map_image.visible,
		"clicking a region shows its tab map")
	var mirrorhold_crop: Vector2 = _tab_map_size(regions[mirrorhold_index] as Dictionary)
	_expect(region_preview.texture != null
		and region_preview.texture.get_size() == mirrorhold_crop,
		"Mirrorhold's preview is the pixels its cartography frames, one a metre, got "
			+ str(region_preview.texture.get_size() if region_preview.texture != null else Vector2.ZERO)
			+ " for " + str(mirrorhold_crop))
	_expect(map_title.text == "MIRRORHOLD", "the title is the region's name")
	_expect(continent_button.texture_normal == continent_texture,
		"over a preview the small map shows the continent again")
	_expect(full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"a preview idles the world render")

	# The cursor names server tiles over the preview, through the map's own
	# transform: the middle of the framing the cartography publishes for the
	# region, in that region's own metres, is the tile its adapter names. The
	# numbers are read from the publication rather than pinned here, so a
	# republished picture moves the expectation with it.
	await process_frame
	var mirrorhold_entry: Dictionary = MapRegistry.resolve(main.get("map_registry") as Dictionary,
		str((regions[mirrorhold_index] as Dictionary).get("serverMap", "")))
	var mirrorhold_adapter := CoordinateAdapter.new(mirrorhold_entry.get("coordinateTransform", {}) as Dictionary)
	var mirrorhold_middle: Vector2 = _tab_map_middle(regions[mirrorhold_index] as Dictionary)
	var expected_tile: Vector2i = mirrorhold_adapter.godot_to_server(
		Vector3(mirrorhold_middle.x, 0.0, mirrorhold_middle.y))
	var preview_centre: Vector2 = region_preview.size * 0.5
	var tile_value: Variant = main.call("_preview_tile_at", preview_centre)
	_expect(tile_value is Vector2i and (tile_value as Vector2i) == expected_tile,
		"the middle of Mirrorhold's map is server tile " + str(expected_tile) + ", got " + str(tile_value))
	var preview_motion := InputEventMouseMotion.new()
	preview_motion.position = preview_centre
	main.call("_on_region_preview_gui_input", preview_motion)
	_expect(map_coordinates.text == "Coordinates: %d, %d" % [expected_tile.x, expected_tile.y],
		"the sidebar reports the tile under the cursor, got " + map_coordinates.text)
	var off_picture := InputEventMouseMotion.new()
	off_picture.position = Vector2(-10.0, -10.0)
	main.call("_on_region_preview_gui_input", off_picture)
	_expect(map_coordinates.text == "Coordinates: outside map image",
		"off the picture there is no tile")
	main.call("_on_region_preview_mouse_exited")
	_expect(map_coordinates.text.begins_with("Coordinates:"),
		"leaving the preview clears the reading")

	# A preview is framed as the live Tab map frames the map: Sunmane to its
	# addressable tiles, Four Gates to its map bounds rather than its backdrop.
	main.call("_preview_region", _index_of(regions, "sunmane_steppe"))
	var sunmane_index: int = _index_of(regions, "sunmane_steppe")
	var sunmane_texture: Texture2D = region_preview.texture
	var sunmane_crop: Vector2 = _tab_map_size(regions[sunmane_index] as Dictionary)
	_expect(sunmane_texture != null and sunmane_texture.get_size() == sunmane_crop,
		"Sunmane's preview is the live map's framing, its whole " + str(sunmane_crop) + " minimap")
	var four_gates_index: int = _index_of(regions, "four_gates")
	main.call("_preview_region", four_gates_index)
	_expect(map_image.visible and not region_preview.visible,
		"asking for the map you are standing on returns to the live map")
	app_state.set("current_map", "mirrorhold")
	main.call("_preview_region", four_gates_index)
	var four_gates_texture: Texture2D = region_preview.texture
	var four_gates_crop: Vector2 = _tab_map_size(regions[four_gates_index] as Dictionary)
	_expect(four_gates_texture != null and four_gates_texture.get_size() == four_gates_crop,
		"Four Gates' preview frames its map bounds, " + str(four_gates_crop) + ", got "
			+ str(four_gates_texture.get_size() if four_gates_texture != null else Vector2.ZERO))
	_expect(main.call("_tab_map_texture", regions[four_gates_index]) == four_gates_texture,
		"a tab map is decoded once and kept")
	_expect(map_title.text == "FOUR GATES", "the preview is titled with the map's name")

	# Mirrorhold is where the player stands now.
	main.call("_show_continent_view")
	_expect(int(overlay.get("_current_index")) == mirrorhold_index,
		"the continent marks the map the player stands on")
	overlay.call("_gui_input", motion)
	_expect(map_coordinates.text.contains("where you are"),
		"hovering your own map says so")
	overlay.call("_gui_input", click)
	_expect(map_image.visible and not region_preview.visible and not continent_view.visible,
		"clicking your own map on the continent returns to the live map")

	main.call("_show_continent_view")
	main.call("_preview_region", 99)
	_expect(continent_view.visible, "an unknown region index changes nothing")
	main.call("_toggle_full_map")
	_expect(not full_map.visible and full_map_viewport.render_target_update_mode
		== SubViewport.UPDATE_DISABLED, "closing the map window idles its viewport")
	main.call("_toggle_full_map")
	_expect(full_map.visible and map_image.visible and not continent_view.visible,
		"reopening the map window shows the current map")
	await _test_landfall_group(main, app_state)
	_expect(_landfall_checks_done, "Landfall UI checks completed without script errors")
	_finish()

## The real main scene selects a group overview independently of live-map framing.
func _test_landfall_group(main: Control, app_state: Node) -> void:
	var overlay: Control = main.get("continent_map") as Control
	var registry: Dictionary = main.get("map_registry") as Dictionary
	var rows: Array = main.get("cartography_regions") as Array
	var overview: Dictionary = (main.get("_v2_cartography") as Dictionary)["overview"]
	var camera: Camera3D = main.get("full_map_camera") as Camera3D
	var viewport: SubViewport = main.get("full_map_viewport") as SubViewport
	var previous: String = ""
	for row: Dictionary in overview["regions"]:
		var id := str(row["serverMap"])
		app_state.set("current_map", id)
		main.set("_current_map_display_name", row["name"])
		var manifest := WorldManifest.load_file(ProjectSettings.globalize_path(
			str((registry[id] as Dictionary)["manifest"])))
		main.set("adapter", manifest.coordinate_adapter())
		main.call("_configure_full_map", manifest)
		main.call("_show_current_map_view")
		_expect(is_equal_approx(float(main.get("_full_map_zoom")), 1.0), id + " starts at individual map zoom")
		var bounds := preload("res://src/world/map_view.gd").bounds_for(manifest)
		_expect(camera.global_position.x == bounds.get_center().x and camera.global_position.z == bounds.get_center().z,
			id + " primary map centres its own bounds")
		var span := (camera.unproject_position(bounds.end) - camera.unproject_position(bounds.position)).abs() / Vector2(viewport.size)
		_expect(span.x > 0.50 and span.y > 0.50 and span.x < 1.0 and span.y < 1.0,
			id + " own section fills primary view with existing neighbour collar")
		_expect((main.get("continent_button") as TextureButton).tooltip_text == "Show the Landfall continent",
			id + " sidebar selects the Landfall group")
		main.call("_on_continent_button_pressed")
		_expect((main.get("continent_view") as Control).visible and int(overlay.call("region_count")) == 15,
			id + " overview contains all 15 areas")
		_expect((main.get("map_title") as Label).text == "LANDFALL CONTINENT", id + " overview is named Landfall")
		_expect((main.get("continent_image") as TextureRect).texture.get_size() == Vector2(overview["imageSize"][0], overview["imageSize"][1]),
			id + " overview uses the generated group picture")
		var local_index: int = (main.get("_continent_region_indices") as Array).find(_index_of(rows, id))
		_expect(int(overlay.get("_current_index")) == local_index, id + " highlight maps its overlay index")
		main.call("_preview_continent_region", local_index)
		_expect((main.get("map_image") as Control).visible and not (main.get("continent_view") as Control).visible,
			id + " clicking current group region restores its live map")
		main.call("_zoom_full_map", false)
		var zoom: float = main.get("_full_map_zoom")
		main.call("_configure_full_map", manifest)
		_expect(float(main.get("_full_map_zoom")) == zoom and zoom > 1.0, id + " redraw retains chosen zoom")
		previous = id
	_expect(not previous.is_empty(), "all published group rows were exercised")

	# Real Ravenhead geometry has two components: both select it, its hull gap does not.
	app_state.set("current_map", "landfall")
	main.call("_show_continent_view")
	var raven_index := -1
	for i: int in range(overview["regions"].size()):
		if str((overview["regions"][i] as Dictionary)["serverMap"]) == "ravenhead":
			raven_index = i
	var rings: Array = overlay.call("region_polygons", raven_index)
	_expect(rings.size() == 2, "Ravenhead overview retains both components")
	var all_points := PackedVector2Array()
	for ring: PackedVector2Array in rings:
		all_points.append_array(ring)
		var triangles := Geometry2D.triangulate_polygon(ring)
		_expect(triangles.size() >= 3, "Ravenhead component triangulates")
		var interior := (ring[triangles[0]] + ring[triangles[1]] + ring[triangles[2]]) / 3.0
		_expect(int(overlay.call("region_at", interior)) == raven_index, "each Ravenhead component is clickable")
	var hull := Geometry2D.convex_hull(all_points)
	var rect: Rect2 = overlay.call("region_rect", raven_index)
	var gap_found := false
	for x: int in range(1, 40):
		for y: int in range(1, 40):
			var point := rect.position + rect.size * Vector2(float(x) / 40.0, float(y) / 40.0)
			if Geometry2D.is_point_in_polygon(point, hull) and int(overlay.call("region_at", point)) != raven_index:
				gap_found = true
	_expect(gap_found, "Ravenhead separating gap inside hull does not select Ravenhead")
	main.call("_preview_continent_region", raven_index)
	_expect(int(main.get("_preview_region_index")) == _index_of(rows, "ravenhead")
		and (main.get("region_preview") as Control).visible and str(app_state.get("current_map")) == "landfall",
		"overview click maps to Ravenhead's own preview without changing server map")

	app_state.set("current_map", "four_gates")
	main.call("_show_current_map_view")
	main.call("_on_continent_button_pressed")
	_expect(int(overlay.call("region_count")) == 12 and (main.get("map_title") as Label).text == "NYMARA CONTINENT",
		"returning to Nymara restores its original 12-region overview")
	_landfall_checks_done = true

## The pixels a region's published cartography frames, one a metre: the crop
## the tab map declares, or the whole picture where it declares none.
func _tab_map_size(region: Dictionary) -> Vector2:
	var tab_map: Dictionary = region.get("tabMap", {}) as Dictionary
	var crop: Array = tab_map.get("region", []) as Array
	if crop.size() == 4:
		return Vector2(float(crop[2]), float(crop[3]))
	var low: Array = tab_map.get("worldMin", []) as Array
	var high: Array = tab_map.get("worldMax", []) as Array
	if low.size() < 2 or high.size() < 2:
		return Vector2.ZERO
	return Vector2(float(high[0]) - float(low[0]), float(high[1]) - float(low[1]))

## The middle of that framing in the region's own metres.
func _tab_map_middle(region: Dictionary) -> Vector2:
	var tab_map: Dictionary = region.get("tabMap", {}) as Dictionary
	var low: Array = tab_map.get("worldMin", []) as Array
	var high: Array = tab_map.get("worldMax", []) as Array
	if low.size() < 2 or high.size() < 2:
		return Vector2.ZERO
	return Vector2(float(low[0]) + float(high[0]), float(low[1]) + float(high[1])) * 0.5

func _index_of(regions: Array, server_map: String) -> int:
	for index: int in range(regions.size()):
		if str((regions[index] as Dictionary).get("serverMap", "")) == server_map:
			return index
	return -1

func _expect(value: bool, label: String) -> void:
	checks += 1
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)

func _finish() -> void:
	if failures == 0:
		print("continent map fixtures passed: ", checks, " checks")
	else:
		print("continent map fixtures failed: ", failures)
	quit(failures)
