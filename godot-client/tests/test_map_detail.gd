extends SceneTree
## Detailed regional pixels retain world framing and do not warm a continent's
## worth of large textures. The cache pins the active region while previewing.
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 800)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.exterior_stream.set_process(false)
	root.get_node("Network").set_process(false)
	var expected_maps := {}
	for path: String in ["res://data/maps/cartography.json", "res://data/maps/cartography-continent-v2.json"]:
		var published: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
		for row: Dictionary in published.get("regions", []):
			expected_maps[str(row.serverMap)] = true
	var actual_maps := {}
	for row: Dictionary in main.cartography_regions:
		actual_maps[str(row.serverMap)] = true
	_expect(actual_maps == expected_maps and main.cartography_regions.size() == expected_maps.size(),
		"every published exterior region is present exactly once")
	for region: Dictionary in main.cartography_regions:
		var tab: Dictionary = region.tabMap
		var detail: Dictionary = tab.get("detail", {})
		_expect(not detail.is_empty(), str(region.serverMap) + " has detailed cartography")
		if detail.is_empty():
			continue
		var extent := Vector2(float(tab.worldMax[0]) - float(tab.worldMin[0]),
			float(tab.worldMax[1]) - float(tab.worldMin[1]))
		_expect(Vector2(detail.imageSize[0], detail.imageSize[1]).is_equal_approx(extent * 4.0),
			str(region.serverMap) + " has four actual pixels per metre")
		_expect(FileAccess.get_sha256(ProjectSettings.globalize_path(detail.texture)) == detail.sha256,
			str(region.serverMap) + " detail pixels match their published hash")
	_expect(main._tab_map_detail_textures.is_empty(), "startup does not decode all detailed images")
	var state: Node = root.get_node("AppState")
	state.current_map = "landfall"
	var region: Dictionary = main.cartography_regions[main._region_index_for_map("landfall")]
	var texture: Texture2D = main._tab_map_detail_texture(region)
	_expect(texture.get_size() == Vector2(2224, 1952), "Landfall loads the detailed 2224 x 1952 image")
	_expect(texture.get_image().has_mipmaps(), "detailed maps have filtered mip levels for the minimap")
	for map_id: String in ["four_gates", "mirrorhold", "crownwater"]:
		main._tab_map_detail_texture(main.cartography_regions[main._region_index_for_map(map_id)])
		_expect(main._tab_map_detail_textures.size() <= 2, "browsing keeps at most two detailed textures cached")
		_expect(main._tab_map_detail_textures.has("landfall"), "browsing keeps the active region cached")
	var manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/landfall/client/world.json")
	main.adapter = manifest.coordinate_adapter()
	main.exterior_stream.active_map = "landfall"
	main.exterior_stream.active_root = main.world_root
	main.exterior_stream.active_manifest = manifest
	main._install_map_picture(manifest)
	_expect(main._map_picture.texture == texture, "both map backgrounds use detailed pixels on the active picture")
	var expected := MapPicture.extent(manifest.data.minimap, region.tabMap)
	var actual: Rect2 = main._map_picture.extent
	_expect(actual.is_equal_approx(expected),
		"the higher-resolution picture retains its exact world extent")
	var neighbour: Dictionary = main._neighbour_pictures["reedfall"]
	var neighbour_row: Dictionary = main.cartography_regions[main._region_index_for_map("reedfall")]
	_expect(neighbour.texture == main._tab_map_texture(neighbour_row),
		"continental neighbours keep the smaller cached pictures")
	main._configure_full_map(manifest)
	_expect(maxi(main.full_map_viewport.size.x, main.full_map_viewport.size.y) == 2048,
		"Tab-map logical projection resolution supports the detailed source image")
	_expect(main.full_map_viewport.disable_3d
		and main.full_map_viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"detailed pixels never allocate a map render pass")
	main.game_view.show()
	main.full_map.show()
	main._show_current_map_view()
	main.minimap_frame.hide()
	var reedfall_center := Vector3.INF
	for boundary: Dictionary in main._map_boundaries():
		if boundary.name == "Reedfall" and boundary.label != Vector3.INF:
			reedfall_center = boundary.label
	_expect(reedfall_center != Vector3.INF and main._map_owning_point(reedfall_center) == "reedfall",
		"the panned view has a point inside the neighbouring region")
	main._full_map_zoom = 0.25
	main.full_map_camera.size = 64.0
	main.full_map_camera.global_position.x = reedfall_center.x
	main.full_map_camera.global_position.z = reedfall_center.z
	main._update_map_detail_levels()
	_expect(main._map_detail_visible.has("reedfall"), "panning a magnified map requests neighbour detail")
	_expect(neighbour.texture == main._tab_map_detail_texture(neighbour_row),
		"a magnified neighbour uses its detailed pixels")
	_expect(main._map_detail_visible.size() <= 5 and main._tab_map_detail_textures.size() <= 6,
		"visible map details and one preview have a bounded cache")
	main._neighbour_pictures.erase("reedfall")
	main._install_neighbour_pictures()
	main._update_map_detail_levels()
	neighbour = main._neighbour_pictures["reedfall"]
	_expect(neighbour.texture == main._tab_map_detail_texture(neighbour_row),
		"rebuilding a neighbour picture preserves its visible detail")
	main._full_map_zoom = 1.0
	main._update_map_detail_levels()
	_expect(neighbour.texture == main._tab_map_texture(neighbour_row),
		"pulling back returns neighbours to the smaller overview pictures")
	_expect(not main._tab_map_detail_textures.has("reedfall"), "leaving the detailed view releases its cached image")
	main.queue_free()
	await process_frame
	print("Map detail: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
