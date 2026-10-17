extends SceneTree
## Exercise cursor-anchored Tab-map zoom and picking through the real wheel handler.

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
	main.game_view.show()
	main.full_map.show()
	main.map_image.show()
	await process_frame
	var state: Node = root.get_node("AppState")
	state.local_actor_id = 9001
	var actor := Node3D.new()
	main.world_root.add_child(actor)
	main.actor_nodes[state.local_actor_id] = actor
	var camera: Camera3D = main.full_map_camera
	for map_id: String in ["landfall", "four_gates", "mirrorhold_interiors", "mirrorhold_secrets"]:
		state.current_map = map_id
		var entry: Dictionary = MapRegistry.resolve(main.map_registry, map_id)
		var manifest := WorldManifest.load_file(ProjectSettings.globalize_path(entry.manifest))
		_expect(manifest.is_valid(), map_id + " fixture loads")
		main.adapter = manifest.coordinate_adapter()
		var bounds: AABB = main.MapViewScript.bounds_for(manifest)
		var tile: Vector2i = main.adapter.godot_to_server(
			bounds.position + bounds.size * Vector3(0.15, 0.5, 0.8))
		actor.global_position = main.adapter.tile_center(tile.x, tile.y)
		main._configure_full_map(manifest)
		var default_position := camera.global_position
		var default_size := camera.size
		_expect(main._full_map_zoom == 1.0, map_id + " starts at 100% after a map change")
		_check_letterbox_zoom(main, map_id)
		var pixel := Vector2(main.full_map_viewport.size) * Vector2(0.7, 0.35)
		var at: Vector2 = main.map_marker_overlay._texture_position(pixel)
		var anchor := camera.project_ray_origin(pixel)
		_wheel(main, MOUSE_BUTTON_WHEEL_UP, at)
		_expect(camera.size < default_size, map_id + " wheel up magnifies past 100%")
		_check_cursor_anchor(main, anchor, at, map_id)
		_expect(camera.global_position.y == default_position.y,
			map_id + " zoom keeps the camera above the map")
		var retained_zoom: float = main._full_map_zoom
		main._configure_full_map(manifest)
		_expect(is_equal_approx(main._full_map_zoom, retained_zoom),
			map_id + " reframing the same map retains magnification")
		_check_cursor_anchor(main, anchor, at, map_id + " after reframing")
		var anchored_position := camera.global_position
		# Player movement must not pull the selected view away from the cursor.
		actor.position += Vector3(3.0, 0.0, -2.0) * main.adapter.metres_per_tile
		main._update_local_actor_follow()
		main._request_map_redraw()
		main._update_map_viewports()
		_check_cursor_anchor(main, anchor, at, map_id + " after movement")
		_expect(camera.global_position.is_equal_approx(anchored_position),
			map_id + " player movement preserves the cursor-focused view")
		var actor_pixel := camera.unproject_position(actor.global_position)
		_expect(main._map_target_tile(camera, actor_pixel) == main.adapter.godot_to_server(actor.global_position),
			map_id + " clicking the displayed player still selects their tile")
		var waypoint := {"position": actor.global_position, "label": "Player location"}
		var waypoints: Array[Dictionary] = [waypoint]
		main.map_marker_overlay.set_waypoints(waypoints)
		var image_point: Vector2 = main.map_marker_overlay._texture_position(actor_pixel)
		_expect(main.map_marker_overlay.label_at(image_point) == "Player location",
			map_id + " marker hover agrees with the magnified map")
		_expect(is_equal_approx(main.map_marker_overlay._live_overlay.mark_radius({"radius": 5.5}), 5.5),
			map_id + " player marker keeps its screen size")
		_wheel(main, MOUSE_BUTTON_WHEEL_DOWN)
		_expect(main._full_map_zoom == 1.0 and camera.global_position.is_equal_approx(default_position)
			and is_equal_approx(camera.size, default_size), map_id + " returning to 100% restores the region frame")
		for i: int in range(24):
			_wheel(main, MOUSE_BUTTON_WHEEL_UP, at)
		_expect(is_equal_approx(camera.size, default_size * 0.25), map_id + " magnification stops at 400%")
		_check_cursor_anchor(main, anchor, at, map_id + " at maximum magnification")
		var limit_position := camera.global_position
		_wheel(main, MOUSE_BUTTON_WHEEL_UP, main.map_image.size * 0.5)
		_expect(camera.global_position.is_equal_approx(limit_position),
			map_id + " scrolling at the zoom limit does not shift the view")
		var zoom_out_pixel := Vector2(main.full_map_viewport.size) * Vector2(0.3, 0.65)
		var zoom_out_at: Vector2 = main.map_marker_overlay._texture_position(zoom_out_pixel)
		var zoom_out_anchor := camera.project_ray_origin(zoom_out_pixel)
		_wheel(main, MOUSE_BUTTON_WHEEL_DOWN, zoom_out_at)
		_check_cursor_anchor(main, zoom_out_anchor, zoom_out_at, map_id + " when zooming out while magnified")
		# A clamped endpoint is off the regular wheel-step sequence: do not skip 100%.
		for i: int in range(24):
			_wheel(main, MOUSE_BUTTON_WHEEL_DOWN)
			if main._full_map_zoom == 1.0:
				break
		_expect(main._full_map_zoom == 1.0 and camera.global_position.is_equal_approx(default_position),
			map_id + " zooming out from the limit stops at the default frame")
		for i: int in range(24):
			_wheel(main, MOUSE_BUTTON_WHEEL_DOWN)
		var exterior: bool = manifest.data.has("continentGeography")
		_expect(is_equal_approx(main._full_map_zoom, 6.0 if exterior else 1.0),
			map_id + " retains its existing zoom-out limit")
		_expect(camera.global_position.is_equal_approx(default_position),
			map_id + " wide views remain centered on the region")
		if exterior:
			for i: int in range(24):
				_wheel(main, MOUSE_BUTTON_WHEEL_UP)
				if main._full_map_zoom == 1.0:
					break
			_expect(main._full_map_zoom == 1.0, map_id + " zooming in from the wide limit stops at 100%")
		_wheel(main, MOUSE_BUTTON_WHEEL_UP, at)
		var without_player_position := camera.global_position
		main.actor_nodes.erase(state.local_actor_id)
		main._update_full_map_focus()
		_expect(camera.global_position.is_equal_approx(without_player_position),
			map_id + " cursor focus does not depend on a player actor")
		main._show_current_map_view()
		_expect(camera.global_position.is_equal_approx(default_position),
			map_id + " missing player falls back to the region center")
		main.actor_nodes[state.local_actor_id] = actor
	main.actor_nodes.clear()
	actor.free()
	# Stale entries can remain briefly while actors are being replaced.
	main.actor_nodes[state.local_actor_id] = actor
	main._update_full_map_focus()
	_expect(camera.global_position.is_equal_approx(main._full_map_base_position),
		"a freed actor safely falls back to the region center")
	main.actor_nodes.clear()
	main.queue_free()
	await process_frame
	print("Full map zoom: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _wheel(main: Control, button: MouseButton, at := Vector2.INF) -> void:
	var event := InputEventMouseButton.new()
	event.pressed = true
	event.button_index = button
	event.position = main.map_image.size * 0.5 if not at.is_finite() else at
	main._on_full_map_gui_input(event)

func _check_cursor_anchor(main: Control, anchor: Vector3, at: Vector2, label: String) -> void:
	var camera: Camera3D = main.full_map_camera
	var shown: Vector2 = main.map_marker_overlay._texture_position(camera.unproject_position(anchor))
	_expect(shown.distance_to(at) < 0.02, label + " keeps the same map location under the cursor")

func _check_letterbox_zoom(main: Control, label: String) -> void:
	var original_size: Vector2 = main.map_image.size
	var original_overlay_size: Vector2 = main.map_marker_overlay.size
	for size: Vector2 in [Vector2(900, 300), Vector2(300, 900)]:
		main.map_image.size = size
		main.map_marker_overlay.size = size
		var pixel := Vector2(main.full_map_viewport.size) * Vector2(0.75, 0.25)
		var at: Vector2 = main.map_marker_overlay._texture_position(pixel)
		var anchor: Vector3 = main.full_map_camera.project_ray_origin(pixel)
		_wheel(main, MOUSE_BUTTON_WHEEL_UP, at)
		_check_cursor_anchor(main, anchor, at, label + " with a rectangular image")
		var magnification: float = main._full_map_zoom
		var position: Vector3 = main.full_map_camera.global_position
		_expect(main._texture_to_viewport_position(Vector2.ONE, main.map_image, main.full_map_viewport.size) == null,
			label + " fixture has a letterbox margin")
		_wheel(main, MOUSE_BUTTON_WHEEL_UP, Vector2.ONE)
		_expect(main._full_map_zoom == magnification and main.full_map_camera.global_position.is_equal_approx(position),
			label + " scrolling outside the map image does not jump the view")
		_wheel(main, MOUSE_BUTTON_WHEEL_DOWN, at)
	main.map_image.size = original_size
	main.map_marker_overlay.size = original_overlay_size

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
