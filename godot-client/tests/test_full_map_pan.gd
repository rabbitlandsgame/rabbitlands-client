extends SceneTree

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 800)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	main.set_script(load("res://tests/fixtures/full_map_pan_probe.gd"))
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.exterior_stream.set_process(false)
	root.get_node("Network").set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	main.full_map.show()
	main.map_image.show()
	main.map_image.custom_minimum_size = Vector2.ZERO
	var state: Node = root.get_node("AppState")
	state.local_actor_id = 9001
	var actor := Node3D.new()
	main.world_root.add_child(actor)
	main.actor_nodes[state.local_actor_id] = actor
	for map_id: String in ["landfall", "mirrorhold_interiors"]:
		state.current_map = map_id
		var entry: Dictionary = MapRegistry.resolve(main.map_registry, map_id)
		var manifest := WorldManifest.load_file(ProjectSettings.globalize_path(entry.manifest))
		main.adapter = manifest.coordinate_adapter()
		actor.global_position = main.MapViewScript.bounds_for(manifest).get_center()
		main._configure_full_map(manifest)
		for image_size: Vector2 in [Vector2(900, 300), Vector2(300, 900)]:
			main.map_image.size = image_size
			main.map_marker_overlay.size = main.map_image.size
			_check_gestures(main, actor, manifest)
	await _check_gui_capture(main)
	main.actor_nodes.clear()
	main.queue_free()
	await process_frame
	print("Full map pan: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _check_gestures(main: Control, actor: Node3D, manifest: WorldManifest) -> void:
	main._full_map_zoom = 1.0
	main._full_map_panned = false
	main._apply_full_map_zoom()
	_wheel(main, MOUSE_BUTTON_WHEEL_UP)
	var camera: Camera3D = main.full_map_camera
	var start: Vector2 = main.map_image.size * 0.5
	main.map_clicks.clear()
	_button(main, start, true, true)
	_expect(main.map_clicks.is_empty(), "press waits to distinguish a click from a drag")
	_motion(main, start + Vector2(2, -1))
	_button(main, start + Vector2(2, -1), false)
	_expect(main.map_clicks.size() == 1 and main.map_clicks[0].run,
		"a small hand movement remains one click and preserves Shift to run")
	main.map_clicks.clear()
	var grab: Vector3 = main._map_click_point(camera, Vector2(main.full_map_viewport.size) * 0.5)
	_button(main, start, true)
	_motion(main, start + Vector2(70, 45))
	var shown: Vector2 = main.map_marker_overlay._texture_position(camera.unproject_position(grab))
	_expect(shown.distance_to(start + Vector2(70, 45)) < 0.02,
		"the grabbed ground follows the pointer through rectangular letterboxing: got %s, expected %s"
		% [shown, start + Vector2(70, 45)])
	_expect(main._full_map_pan_dragging and main.map_clicks.is_empty(), "dragging pans without issuing a walk")
	_button(main, start + Vector2(70, 45), false)
	var panned_position := camera.global_position
	_expect(main.map_clicks.is_empty() and main._full_map_pan_press == null,
		"releasing a drag never sends a movement command")
	actor.position += Vector3(2, 0, -3)
	main._update_local_actor_follow()
	main._request_map_redraw()
	main._update_map_viewports()
	_expect(camera.global_position.is_equal_approx(panned_position), "manual pan stays put when the player moves")
	main._configure_full_map(manifest)
	_expect(camera.global_position.is_equal_approx(panned_position), "reframing the same map retains the manual view")
	var tile: Variant = main._map_target_tile(camera, Vector2(main.full_map_viewport.size) * 0.5)
	_button(main, start, true)
	_button(main, start, false)
	_expect(main.map_clicks.size() == 1 and main.map_clicks[0].tile == tile,
		"a click after panning targets the displayed tile")
	main.map_clicks.clear()
	# A second pan begins at the current view instead of jumping back to the player.
	_button(main, start, true)
	_motion(main, start + Vector2(-30, -20))
	_button(main, start + Vector2(-30, -20), false)
	_expect(not camera.global_position.is_equal_approx(panned_position), "successive drags continue from the manual view")
	_wheel(main, MOUSE_BUTTON_WHEEL_DOWN)
	_expect(main._full_map_zoom == 1.0 and camera.global_position.is_equal_approx(main._full_map_base_position),
		"zooming back to 100% clears the pan and restores region framing")
	var wide_position := camera.global_position
	_button(main, start, true)
	_motion(main, start + Vector2(70, 45))
	_button(main, start + Vector2(70, 45), false)
	_expect(main.map_clicks.size() == 1 and camera.global_position.is_equal_approx(wide_position),
		"the default view keeps its existing click behavior without panning")
	main.map_clicks.clear()
	_wheel(main, MOUSE_BUTTON_WHEEL_UP)
	_button(main, start, true)
	_motion(main, start + Vector2(70, 45))
	var scroll_at := start + Vector2(70, 45)
	var scroll_pixel: Vector2 = main._texture_to_viewport_position(scroll_at, main.map_image, main.full_map_viewport.size)
	var scroll_anchor: Vector3 = main._map_click_point(camera, scroll_pixel)
	_wheel(main, MOUSE_BUTTON_WHEEL_UP, scroll_at)
	_button(main, start + Vector2(70, 45), false)
	var scroll_shown: Vector2 = main.map_marker_overlay._texture_position(camera.unproject_position(scroll_anchor))
	_expect(main.map_clicks.is_empty() and main._full_map_pan_press == null
		and not main._full_map_pan_dragging and scroll_shown.distance_to(scroll_at) < 0.02,
		"scrolling during a drag cancels the gesture and zooms around the cursor")
	_button(main, start, true)
	_motion(main, start + Vector2(70, 45))
	main._notification(Control.NOTIFICATION_WM_WINDOW_FOCUS_OUT)
	_button(main, start + Vector2(70, 45), false)
	_expect(main.map_clicks.is_empty() and main._full_map_pan_press == null,
		"losing window focus cancels the drag without issuing a walk")
	_button(main, start, true)
	main.map_image.hide()
	_expect(main._full_map_pan_press == null, "hiding the map cancels a pending click")
	main._show_current_map_view()
	_expect(not main._full_map_panned and absf(camera.global_position.x - actor.global_position.x) < 0.01,
		"Current map restores player follow")
	# Presses in a letterbox margin must not start a pan.
	var margin := Vector2(1, 1)
	if main._texture_to_viewport_position(margin, main.map_image, main.full_map_viewport.size) == null:
		_button(main, margin, true)
		_expect(main._full_map_pan_press == null, "a letterbox margin cannot start a pan")
		_button(main, margin, false)

func _check_gui_capture(main: Control) -> void:
	# Use native GUI dispatch once to check capture beyond the map's edge.
	main.full_map.position = Vector2(20, 20)
	main.full_map.size = Vector2(900, 600)
	await process_frame
	main._show_current_map_view()
	main.map_clicks.clear()
	var start: Vector2 = main.map_image.get_global_rect().get_center()
	_gui_button(start, true)
	_expect(main._full_map_pan_press != null, "native GUI dispatch starts a map gesture")
	var outside := Vector2(1250, 780)
	var motion := InputEventMouseMotion.new()
	motion.position = outside
	motion.global_position = outside
	motion.relative = outside - start
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion, true)
	_gui_button(outside, false)
	_expect(main._full_map_panned and main._full_map_pan_press == null and main.map_clicks.is_empty(),
		"GUI capture continues and releases a drag outside the map without walking")

func _gui_button(at: Vector2, pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.position = at
	event.global_position = at
	event.button_index = MOUSE_BUTTON_LEFT
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
	event.pressed = pressed
	root.push_input(event, true)

func _button(main: Control, at: Vector2, pressed: bool, run := false) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.position = at
	event.pressed = pressed
	event.shift_pressed = run
	main.map_image.gui_input.emit(event)

func _motion(main: Control, at: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position = at
	event.button_mask = MOUSE_BUTTON_MASK_LEFT
	main.map_image.gui_input.emit(event)

func _wheel(main: Control, button: MouseButton, at := Vector2.INF) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = button
	event.pressed = true
	event.position = main.map_image.size * 0.5 if not at.is_finite() else at
	main.map_image.gui_input.emit(event)

func _expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
