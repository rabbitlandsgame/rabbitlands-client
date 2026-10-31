extends SceneTree
## Layout, cursor coordinates and the complete map-click destination lifecycle.
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var network: Node = root.get_node("Network")
	network.set_script(load("res://tests/fixtures/map_movement_network_probe.gd"))
	network.set_process(false)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.exterior_stream.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	var state: Node = root.get_node("AppState")
	state.current_map = "landfall"
	state.local_actor_id = 9001
	var manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/landfall/client/world.json")
	main.adapter = manifest.coordinate_adapter()
	main.world_loader.manifest = manifest
	main.exterior_stream.active_map = "landfall"
	main.exterior_stream.active_manifest = manifest
	main.exterior_stream.active_root = main.world_root
	var actor := Node3D.new()
	main.world_root.add_child(actor)
	actor.position = main.adapter.tile_center(117, 216)
	main.actor_nodes[state.local_actor_id] = actor
	main._current_map_display_name = "Landfall"
	main._configure_full_map(manifest)
	main._install_map_picture(manifest)
	main._show_current_map_view()
	main.full_map.show()
	main._zoom_full_map(true)
	main._update_local_actor_follow()
	main.map_marker_list.text = "A very long marker description that wraps within the sidebar (12345, 67890)"
	main.map_marker_list.show()
	main.map_marker_title.show()
	for fixture: Dictionary in [
			{"size": Vector2i(1280, 720), "scale": 1.0},
			{"size": Vector2i(1908, 1164), "scale": 1.0},
			{"size": Vector2i(1280, 800), "scale": 1.5}]:
		root.size = fixture.size
		root.content_scale_factor = fixture.scale
		await process_frame
		await process_frame
		main._on_window_size_changed()
		await process_frame
		_check_layout_and_cursor(main)
	root.content_scale_factor = 1.0
	root.size = Vector2i(1280, 800)
	await process_frame
	main._on_window_size_changed()
	await process_frame
	var tile := Vector2i(120, 219)
	_click_tile(main, tile)
	_expect(not main._map_walk_target.is_empty() and main._map_walk_target.tile == tile,
		"a successful map click records its selected movement destination")
	var point: Variant = main.map_marker_overlay.walk_target_point()
	var projected: Vector2 = main.map_marker_overlay._texture_position(
		main.full_map_camera.unproject_position(main.adapter.tile_center(tile.x, tile.y)))
	_expect(point is Vector2 and (point as Vector2).distance_to(projected) < 0.01,
		"the red X projects to the selected tile")
	main._full_map_panned = true
	main._full_map_pan_position = main.full_map_camera.global_position + Vector3(5, 0, 3)
	main._apply_full_map_zoom()
	var shifted: Variant = main.map_marker_overlay.walk_target_point()
	_expect(shifted is Vector2 and (shifted as Vector2).distance_to(projected) > 1.0,
		"the destination X follows the map when it is panned")
	main._full_map_panned = false
	main._apply_full_map_zoom()
	main._update_map_viewports()
	main._update_full_map_cursor(main.map_image.size * 0.5 + Vector2(50, 25))
	if "--capture" in OS.get_cmdline_user_args():
		for i: int in range(5):
			await process_frame
		await RenderingServer.frame_post_draw
		var path := "res://test-artifacts/tab-map-workspace.png"
		_expect(root.get_texture().get_image().save_png(path) == OK, "workspace screenshot saved")
	_expect(network.move_to(Vector2i(121, 220)) == OK and main._map_walk_target.is_empty(),
		"a new movement order replaces the map destination")
	_click_tile(main, tile)
	actor.position = main.adapter.tile_center(tile.x, tile.y)
	main._update_map_walk_target()
	_expect(main._map_walk_target.is_empty() and main.map_marker_overlay.walk_target_point() == null,
		"arrival removes the X")
	actor.position = main.adapter.tile_center(117, 216)
	main._set_map_walk_target("landfall", tile)
	network.coordinate_route_cancelled.emit()
	_expect(main._map_walk_target.is_empty(), "route cancellation removes the destination")
	main._set_map_walk_target("landfall", tile)
	main._map_walk_target.last_progress_msec = Time.get_ticks_msec() - 3100
	main._update_map_walk_target()
	_expect(main._map_walk_target.is_empty(), "a blocked walk cannot leave a permanent X")
	var other_adapter := CoordinateAdapter.new(main.exterior_stream.region_coordinates("reedfall"))
	var other_tile := Vector2i(200, 200)
	var leg := Vector2i(121, 220)
	main.exterior_stream.pending_walk = {"map": "reedfall", "tile": other_tile, "leg_tile": leg}
	main._set_map_walk_target("reedfall", other_tile)
	var frame: Transform3D = main.exterior_stream.region_transform("reedfall")
	var expected: Vector3 = frame * other_adapter.tile_center(other_tile.x, other_tile.y)
	_expect(main.map_marker_overlay._walk_target.is_equal_approx(expected),
		"a cross-map route marks its final destination in the current world's coordinates")
	network.move_to(leg)
	_expect(not main._map_walk_target.is_empty(), "intermediate seam orders preserve the final destination")
	main.exterior_stream.pending_walk.clear()
	main._update_map_walk_target()
	_expect(main._map_walk_target.is_empty(), "an abandoned cross-map route clears the destination")
	network.begin_magic_selection({"op": "cast", "id": 1, "power": 1}, "location")
	_click_tile(main, tile)
	_expect(main._map_walk_target.is_empty() and network.magic_pending.is_empty(),
		"a map click used for a location spell does not create a movement X")
	network.send_error = ERR_UNCONFIGURED
	_click_tile(main, tile)
	_expect(main._map_walk_target.is_empty(), "a failed movement request does not add an X")
	main.actor_nodes.clear()
	main.queue_free()
	await process_frame
	print("Tab map workspace: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _check_layout_and_cursor(main: Control) -> void:
	var area: Rect2 = main.full_map.get_rect()
	_expect(area.position.is_zero_approx(), "the map starts at the client canvas's top-left edge")
	_expect(absf(area.end.x - main.game_view.size.x) < 0.01,
		"the map fills the client width independently of movable HUD rails")
	_expect(absf(area.end.y - main.game_view.size.y) < 0.01,
		"the map fills the client height independently of the selected HUD layout")
	var sidebar: Control = main.get_node("GameView/FullMap/MapLayout/Sidebar")
	var before := sidebar.get_global_rect()
	_expect(absf(before.position.x - main.game_view.global_position.x) < 0.01 and absf(sidebar.size.x - 216.0) < 0.01,
		"the fixed-width sidebar is aligned with the left side of the client")
	var at: Vector2 = main.map_image.size * 0.5
	var hover := InputEventMouseMotion.new()
	hover.position = at
	main._on_full_map_gui_input(hover)
	_expect(main.map_cursor_coordinates.visible and main.map_cursor_coordinates.text.contains("X:")
		and main.map_cursor_coordinates.text.contains("Y:"), "hover shows cursor X and Y beside the pointer")
	var cursor_rect: Rect2 = main.map_cursor_coordinates.get_global_rect()
	_expect(main.map_image.get_global_rect().encloses(cursor_rect), "cursor coordinates stay inside the map")
	var wheel := InputEventMouseButton.new()
	wheel.position = at + Vector2(85, 20)
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	wheel.pressed = true
	main._on_full_map_gui_input(wheel)
	var pixel: Variant = main._texture_to_viewport_position(wheel.position, main.map_image, main.full_map_viewport.size)
	var tile: Vector2i = main._map_target_tile(main.full_map_camera, pixel)
	_expect(main.map_cursor_coordinates.text == "X: %d, Y: %d" % [tile.x, tile.y],
		"scrolling updates cursor coordinates even without mouse motion")
	hover.position = Vector2(-10, -10)
	main._on_full_map_gui_input(hover)
	_expect(not main.map_cursor_coordinates.visible and sidebar.get_global_rect().is_equal_approx(before),
		"outside-map text neither moves nor resizes the sidebar")
	_expect(main.map_coordinates.autowrap_mode == TextServer.AUTOWRAP_OFF and main.map_coordinates.size.y <= 24.0,
		"the sidebar coordinate readout has a fixed single-line height")
	main._on_full_map_mouse_exited()

func _click_tile(main: Control, tile: Vector2i) -> void:
	var pixel: Vector2 = main.full_map_camera.unproject_position(main.adapter.tile_center(tile.x, tile.y))
	var at: Vector2 = main.map_marker_overlay._texture_position(pixel)
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = at
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		main._on_full_map_gui_input(event)

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
