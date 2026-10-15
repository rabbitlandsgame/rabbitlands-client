extends SceneTree
## Marker lifecycle and tutorial instructions through the real packet/UI path.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var state: Node = root.get_node("AppState")
	state.set("authenticated", true)
	state.set("current_map", "four_gates")
	main.set("loaded_server_map", "four_gates")
	main.set("adapter", CoordinateAdapter.new())
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var console: ConsoleCommands = main.get("console_commands")
	console.marks.clear()
	console.current_map = "four_gates"
	var slope := StaticBody3D.new()
	slope.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	slope.collision_mask = 0
	slope.position.y = 2.0
	slope.rotation.z = deg_to_rad(10.0)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(30, 0.1, 30)
	collision.shape = shape
	slope.add_child(collision)
	(main.get("world_root") as Node3D).add_child(slope)
	await physics_frame

	state.call("_on_packet", 90, _marker(520, 2, 3, "four_gates", "The central plaza"))
	state.call("_on_packet", 90, _marker(521, 2, 3, "mirrorhold", "Elsewhere"))
	var nodes: Dictionary = main.get("map_marker_nodes")
	_expect(nodes.size() == 1, "only current-map markers have world visuals")
	var marker: MapMarker3D = nodes[520]
	var label: Label3D = marker.get_node("WorldLabel")
	_expect(label.text == "The central plaza" and label.layers == 2,
		"the gameplay label uses the server's text")
	_expect((marker.get_node("Pin") as MeshInstance3D).layers == 4,
		"the large map pin remains separate from the gameplay effect")
	_expect((marker.get_node("GroundGlow") as MeshInstance3D).layers == 2
		and (marker.get_node("RisingSparks") as GPUParticles3D).layers == 2,
		"the glow and sparks render only in gameplay")
	var glow: MeshInstance3D = marker.get_node("GroundGlow")
	var vertices: PackedVector3Array = glow.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var lowest := INF
	var highest := -INF
	for vertex: Vector3 in vertices:
		lowest = minf(lowest, vertex.y)
		highest = maxf(highest, vertex.y)
	_expect(marker.position.y > 2.0 and highest - lowest > 0.1,
		"the marker is grounded and its glow follows the slope")
	_expect(marker.find_children("*", "CollisionObject3D", true, false).is_empty(),
		"markers cannot intercept clicks or block walking")
	state.call("_on_packet", 90, _marker(520, 5, 6, "four_gates", "Reed bank"))
	_expect(nodes[520] == marker and marker.server_tile == Vector2i(5, 6)
		and label.text == "Reed bank" and marker.position.x == 5.5,
		"restating an id updates its position and label without duplicate effects")
	var marker_instance: int = marker.get_instance_id()
	var sparks_instance: int = marker.get_node("RisingSparks").get_instance_id()
	var grounded_mesh: ArrayMesh = glow.mesh
	# Let the fixture's first gameplay frame finish loading before timing
	# the network gap; startup can take longer than the refresh grace.
	await create_timer(0.3).timeout
	# Refresh packets can straddle rendered frames. Neither the pin, its
	# grounded mesh nor the live particle simulation should be replaced.
	for refresh: int in range(3):
		state.call("_on_packet", 91, PackedByteArray([8, 2]))
		await create_timer(0.06).timeout
		_expect(nodes.has(520), "refresh %d keeps the marker visible between packets" % refresh)
		state.call("_on_packet", 90, _marker(520, 5, 6, "four_gates", "Reed bank"))
		var refreshed: MapMarker3D = nodes[520]
		_expect(refreshed.get_instance_id() == marker_instance
			and refreshed.get_node("RisingSparks").get_instance_id() == sparks_instance
			and (refreshed.get_node("GroundGlow") as MeshInstance3D).mesh == grounded_mesh,
			"refresh %d preserves the animation and grounded glow" % refresh)
	await create_timer(0.3).timeout
	_expect(nodes.has(520), "cancelled removals cannot erase a refreshed marker")
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	await create_timer(0.3).timeout
	await process_frame
	_expect(nodes.is_empty() and not is_instance_valid(marker),
		"removing a server marker removes its entire world effect")

	console.run("#markpos 3 4 Camp")
	main.call("_sync_map_markers")
	var mine: Dictionary = main.get("player_mark_nodes")
	var personal: MapMarker3D = mine["Camp"]
	_expect(personal.server_tile == Vector2i(3, 4)
		and (personal.get_node("WorldLabel") as Label3D).text == "Camp"
		and not personal.has_node("Pin"), "personal marks have world effects")
	console.run("#markpos 7 8 Camp")
	main.call("_sync_map_markers")
	_expect(mine.size() == 1 and mine["Camp"] == personal
		and personal.server_tile == Vector2i(7, 8), "moving a personal mark updates it")
	state.set("current_map", "mirrorhold")
	main.call("_sync_map_markers")
	await process_frame
	_expect(mine.is_empty() and nodes.has(521) and not nodes.has(520),
		"changing map hides old markers and shows markers belonging here")
	state.set("current_map", "four_gates")
	main.call("_sync_map_markers")
	_expect(mine.has("Camp"), "returning restores a personal mark")
	console.run("#unmark Camp")
	main.call("_sync_map_markers")
	_expect(mine.is_empty(), "unmark removes the world effect")

	# The actual tutorial handoff: the next lesson is RAW_TEXT channel 255,
	# followed by removing the completed plaza marker. No DISPLAY_POPUP.
	state.call("_on_packet", 90, _marker(520, 2, 3, "four_gates", "The central plaza"))
	var message := "The Gate Warden\n\nWalk close and click Gate Warden Ilyon to talk."
	state.call("_on_packet", 0, _notice(message))
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	await create_timer(0.3).timeout
	await process_frame
	var panel: Control = main.get("popup_panel")
	_expect(panel.visible and (main.get("popup_title") as Label).text == "The Gate Warden"
		and (main.get("popup_text") as RichTextLabel).text.contains("Ilyon")
		and nodes.is_empty(), "reaching the plaza visibly opens the next instructions")
	_expect(not (main.get("popup_confirm") as Button).visible,
		"an instruction requires no server reply")
	var history: Array = state.get("chat_lines")
	_expect(str((history.back() as Dictionary).get("text")) == message,
		"instructions are also retained in chat history")
	main.call("_on_popup_dismiss_pressed")
	state.call("append_local_message", "Local diagnostics")
	_expect(not panel.visible, "local channel-255 diagnostics do not become popups")
	state.call("_on_packet", 0, PackedByteArray([3]) + _nul("Ordinary system text"))
	_expect(not panel.visible, "ordinary server chat stays in chat")
	state.call("_on_packet", 0, _notice("Walking\n\nWalk to the plaza."))
	state.call("_on_packet", 0, _notice(message))
	_expect((main.get("popup_title") as Label).text == "The Gate Warden",
		"a new instruction replaces the previous lesson")
	state.set("popup", {"open": true, "popup_id": 4001, "title": "Halfway",
		"text": "Keep going?", "options": []})
	state.call("_on_packet", 0, _notice(message))
	_expect(int((state.get("popup") as Dictionary).get("popup_id")) == 4001,
		"a notification does not discard an unanswered question")
	state.call("close_popup")
	_expect(panel.visible and (main.get("popup_title") as Label).text == "The Gate Warden",
		"queued instructions appear after the question closes")
	state.call("close_popup")

	console.run("#markpos 3 4 Camp")
	main.call("_sync_map_markers")
	main.call("_clear_world_presentation")
	_expect(nodes.is_empty() and mine.is_empty(), "disconnect clears all marker visuals")
	state.set("authenticated", false)
	main.queue_free()
	await process_frame
	await _check_removal_deadlines(state)
	print("navigation guidance: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_removal_deadlines(state: Node) -> void:
	state.call("_on_connection_state_changed", "disconnected")
	var markers: Dictionary = state.get("map_markers")
	var pending: Dictionary = state.get("_pending_map_marker_removals")
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	_expect(pending.is_empty(), "removing an unknown id creates no pending work")
	state.call("_on_packet", 90, _marker(520, 2, 3, "four_gates", "Old target"))
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	await create_timer(0.1).timeout
	state.call("_on_packet", 90, _marker(520, 7, 8, "mirrorhold", "New target"))
	_expect(markers[520].label == "New target" and markers[520].map_id == "mirrorhold",
		"a refresh can change the destination and label immediately")
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	await create_timer(0.17).timeout
	_expect(markers.has(520), "an older cancelled timer cannot remove a newer marker")
	# A duplicate REMOVE must not postpone the active removal indefinitely.
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	await create_timer(0.13).timeout
	_expect(markers.is_empty() and pending.is_empty(), "repeated removes keep the original deadline")
	state.call("_on_packet", 90, _marker(520, 2, 3, "four_gates", "Before disconnect"))
	state.call("_on_packet", 91, PackedByteArray([8, 2]))
	state.call("_on_connection_state_changed", "disconnected")
	_expect(markers.is_empty() and pending.is_empty(), "disconnect clears pending removals immediately")
	state.call("_on_packet", 90, _marker(520, 2, 3, "four_gates", "After reconnect"))
	await create_timer(0.3).timeout
	_expect(markers.has(520), "an old session's timer cannot erase a new session's marker")
	state.call("_on_connection_state_changed", "disconnected")

func _marker(id: int, x: int, y: int, map: String, label: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(6)
	bytes.encode_u16(0, id)
	bytes.encode_u16(2, x)
	bytes.encode_u16(4, y)
	return bytes + _nul(map) + _nul(label)

func _notice(message: String) -> PackedByteArray:
	# The tutorial server's colour 6 is encoded as 127 + 6.
	return PackedByteArray([255, 133]) + _nul(message)

func _nul(value: String) -> PackedByteArray:
	return value.to_utf8_buffer() + PackedByteArray([0])

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
