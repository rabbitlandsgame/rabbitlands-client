extends SceneTree

const SESSION_TIMEOUT_SECONDS := 45.0
const SCREEN_SIZE := Vector2i(1280, 720)

var _failures := 0
var _artifact_directory := ""
var _app_state: Node
var _network: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path("res://test-artifacts")
	var directory_error: Error = DirAccess.make_dir_recursive_absolute(_artifact_directory)
	_expect(directory_error == OK, "artifact directory is writable")
	root.size = SCREEN_SIZE
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		_finish()
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	_app_state = root.get_node("AppState")
	_network = root.get_node("Network")

	var host: String = OS.get_environment("ELORIA_INTEGRATION_HOST")
	if host.is_empty():
		host = "127.0.0.1"
	var port_text: String = OS.get_environment("ELORIA_INTEGRATION_PORT")
	var port: int = int(port_text) if port_text.is_valid_int() else 2000
	var suffix: String = _random_hex(5)
	var username: String = "Render" + suffix
	var password: String = _random_hex(24)

	var host_edit: LineEdit = main.get_node("LoginPanel/Content/Host") as LineEdit
	var port_edit: SpinBox = main.get_node("LoginPanel/Content/Port") as SpinBox
	host_edit.text = host
	port_edit.value = port
	main.call("_on_connect_pressed")
	var connected: Callable = func() -> bool:
		return str(_app_state.get("connection_state")) == "connected"
	if not await _wait_for(connected, SESSION_TIMEOUT_SECONDS):
		_fail("development server connection timed out")
		_finish()
		return

	main.call("_on_new_character_pressed")
	var name_edit: LineEdit = main.get_node(
		"CreationPanel/Columns/FormPanel/Form/CreateName") as LineEdit
	var password_edit: LineEdit = main.get_node(
		"CreationPanel/Columns/FormPanel/Form/CreatePassword") as LineEdit
	var confirm_edit: LineEdit = main.get_node(
		"CreationPanel/Columns/FormPanel/Form/CreateConfirm") as LineEdit
	name_edit.text = username
	password_edit.text = password
	confirm_edit.text = password
	main.call("_on_create_pressed")
	var authenticated: Callable = func() -> bool:
		return bool(_app_state.get("authenticated"))
	if not await _wait_for(authenticated, SESSION_TIMEOUT_SECONDS):
		_fail("character creation/login timed out")
		_finish()
		return

	var world_loader: WorldLoader = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/WorldLoader") as WorldLoader
	var presentation_ready: Callable = func() -> bool:
		var local_id: int = int(_app_state.get("local_actor_id"))
		return (not str(_app_state.get("current_map")).is_empty() and local_id >= 0
			and (main.get("actor_nodes") as Dictionary).has(local_id)
			and world_loader.world_root != null)
	if not await _wait_for(presentation_ready, SESSION_TIMEOUT_SECONDS):
		_fail("authoritative map/local actor presentation timed out")
		_finish()
		return
	for unused_frame: int in range(8):
		await physics_frame
		await process_frame

	var actor_nodes: Dictionary = main.get("actor_nodes") as Dictionary
	var local_actor_id: int = int(_app_state.get("local_actor_id"))
	var actors: Dictionary = _app_state.get("actors") as Dictionary
	var actor: ReplicatedActor3D = actor_nodes.get(local_actor_id) as ReplicatedActor3D
	var local_dto: Dictionary = actors.get(local_actor_id, {}) as Dictionary
	var native_model: Node3D = actor.get_node_or_null("NativeModel") as Node3D
	var fallback: Node = actor.get_node_or_null("MissingModelFallback")
	var visible_native_meshes: int = _visible_native_mesh_count(native_model)
	_expect(native_model != null and fallback == null and visible_native_meshes >= 3,
		"local player uses the visible native luminous GLB")
	var camera: Camera3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig/Camera") as Camera3D

	# Keep a second real connection alive so the primary client must replicate,
	# render, move, select, and later remove a genuine remote player.
	var helper_username: String = "Remote" + _random_hex(5)
	var helper_password: String = _random_hex(24)
	var helper_state: Dictionary = {
		"connection": "disconnected", "created": false, "authenticated": false,
		"actor_id": -1, "map": "", "error": "", "chat": []}
	var helper_network: EloriaNetworkClient = EloriaNetworkClient.new()
	helper_network.name = "RemoteActorHelperNetwork"
	var helper_connection_handler: Callable = func(state: String) -> void:
		helper_state["connection"] = state
	helper_network.connection_state_changed.connect(helper_connection_handler)
	var helper_packet_handler: Callable = func(command: int,
			payload: PackedByteArray) -> void:
		var helper_event: Dictionary = EloriaProtocol.decode_server(command, payload)
		match str(helper_event.get("type", "")):
			"create_character_ok":
				helper_state["created"] = true
				var login_error: Error = helper_network.login(
					helper_username, helper_password)
				if login_error != OK:
					helper_state["error"] = "login_send_failed"
			"create_character_error":
				helper_state["error"] = "create_character_rejected"
			"login_ok":
				helper_state["authenticated"] = true
			"login_error":
				helper_state["error"] = "login_rejected"
			"you_are":
				helper_state["actor_id"] = int(helper_event.get("actor_id", -1))
			"change_map":
				helper_state["map"] = str(helper_event.get("map_name", ""))
			"chat":
				var helper_chat: Array = helper_state.get("chat", []) as Array
				helper_chat.append({"channel": int(helper_event.get("channel", 0)),
					"text": str(helper_event.get("text", ""))})
				helper_state["chat"] = helper_chat
			"ping_request":
				helper_network.send_frame(EloriaProtocol.encode(
					EloriaProtocol.ClientMessage.PING_RESPONSE))
	helper_network.packet_received.connect(helper_packet_handler)
	root.add_child(helper_network)
	var helper_connect_error: Error = helper_network.connect_to_server(host, port)
	_expect(helper_connect_error == OK, "remote-player helper begins a real TCP connection")
	var helper_connected: Callable = func() -> bool:
		return str(helper_state.get("connection", "")) == "connected"
	_expect(await _wait_for(helper_connected, SESSION_TIMEOUT_SECONDS),
		"remote-player helper connected to the development server")
	var helper_create_error: Error = helper_network.create_character(
		helper_username, helper_password, {
			"skin": 0, "hair": 0, "shirt": 0, "pants": 0, "boots": 0,
			"actor_type": 1, "head": 0, "eyes": 0})
	_expect(helper_create_error == OK,
		"remote-player helper sent a redacted character-creation request")
	var helper_ready: Callable = func() -> bool:
		var helper_id: int = int(helper_state.get("actor_id", -1))
		return (bool(helper_state.get("authenticated", false)) and helper_id >= 0
			and not str(helper_state.get("map", "")).is_empty()
			and (_app_state.get("actors") as Dictionary).has(helper_id)
			and (main.get("actor_nodes") as Dictionary).has(helper_id))
	var helper_became_ready: bool = await _wait_for(
		helper_ready, SESSION_TIMEOUT_SECONDS)
	_expect(helper_became_ready,
		"primary client received the real remote-player spawn")
	if not helper_became_ready:
		_fail("remote-player helper state=" + str(_json_safe(helper_state)))
		helper_network.disconnect_from_server()
		_finish()
		return
	for unused_remote_frame: int in range(8):
		await physics_frame
		await process_frame
	var remote_actor_id: int = int(helper_state.get("actor_id", -1))
	var remote_dto: Dictionary = (_app_state.get("actors") as Dictionary).get(
		remote_actor_id, {}) as Dictionary
	var remote_actor: ReplicatedActor3D = (main.get("actor_nodes") as Dictionary).get(
		remote_actor_id) as ReplicatedActor3D
	var remote_native_model: Node3D = remote_actor.get_node_or_null("NativeModel") as Node3D
	var remote_fallback: Node = remote_actor.get_node_or_null("MissingModelFallback")
	var remote_visible_native_meshes: int = _visible_native_mesh_count(remote_native_model)
	_expect(bool(remote_dto.get("enhanced", false))
		and int(remote_dto.get("kind", 0)) in [1, 4]
		and remote_native_model != null and remote_fallback == null
		and remote_visible_native_meshes >= 3,
		"remote player preserves its kind and visible native luminous model")
	var remote_initial_tile: Vector2i = Vector2i(int(remote_dto.get("x", -1)),
		int(remote_dto.get("y", -1)))
	var remote_moved: bool = await _move_remote_helper(
		helper_network, remote_actor_id, remote_initial_tile)
	_expect(remote_moved,
		"primary client applied a real authoritative remote-player movement update")
	for unused_remote_follow_frame: int in range(8):
		await physics_frame
		await process_frame
	remote_dto = (_app_state.get("actors") as Dictionary).get(
		remote_actor_id, {}) as Dictionary
	remote_actor = (main.get("actor_nodes") as Dictionary).get(
		remote_actor_id) as ReplicatedActor3D
	var remote_screen: Vector2 = camera.unproject_position(
		remote_actor.global_position + Vector3.UP)
	_expect(not camera.is_position_behind(remote_actor.global_position + Vector3.UP)
		and Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).has_point(remote_screen),
		"remote player is inside the gameplay camera frame")
	var remote_click: InputEventMouseButton = InputEventMouseButton.new()
	remote_click.button_index = MOUSE_BUTTON_LEFT
	remote_click.pressed = true
	remote_click.position = remote_screen
	main.call("_on_world_gui_input", remote_click)
	await process_frame
	var remote_selection_ring: Node3D = remote_actor.get_node_or_null(
		"SelectionRing") as Node3D
	_expect(int(_app_state.get("selected_actor_id")) == remote_actor_id
		and remote_selection_ring != null and remote_selection_ring.visible,
		"ray-based world click selects the rendered remote player")
	var primary_chat_marker: String = "primary-chat-" + _random_hex(4)
	main.call("_on_chat_submitted", primary_chat_marker)
	var helper_received_chat: Callable = func() -> bool:
		return _chat_contains(helper_state.get("chat", []) as Array,
			primary_chat_marker)
	_expect(await _wait_for(helper_received_chat, 8.0),
		"real local chat sent through the primary UI reaches the remote client")
	var remote_chat_marker: String = "remote-chat-" + _random_hex(4)
	var remote_chat_error: Error = helper_network.send_chat(remote_chat_marker)
	_expect(remote_chat_error == OK,
		"remote client sends a real legacy RAW_TEXT chat frame")
	var primary_received_chat: Callable = func() -> bool:
		return _chat_contains(_app_state.get("chat_lines") as Array,
			remote_chat_marker)
	_expect(await _wait_for(primary_received_chat, 8.0),
		"primary reducer receives real chat from the remote client")
	main.call("_sync_chat")
	var chat_output: RichTextLabel = main.get_node(
		"%ChatOutput") as RichTextLabel
	_expect(chat_output.get_parsed_text().contains(primary_chat_marker)
		and chat_output.get_parsed_text().contains(remote_chat_marker),
		"lower-left chat UI presents both real server-delivered messages")
	_write_json("chat.json", {
		"primary_to_remote": primary_chat_marker,
		"remote_to_primary": remote_chat_marker,
		"primary_chat_lines": _json_safe(_app_state.get("chat_lines")),
		"remote_chat_lines": _json_safe(helper_state.get("chat", [])),
		"credentials": "REDACTED",
	})
	await _capture("world-chat.png")

	var server_inventory: Dictionary = _app_state.get("inventory") as Dictionary
	var server_stats: Dictionary = _app_state.get("stats") as Dictionary
	_expect(not server_inventory.is_empty(),
		"development server supplied a non-empty authoritative inventory")
	_expect(not server_stats.is_empty()
		and int(server_stats.get("max_health", 0)) > 0
		and int(server_stats.get("capacity", 0)) > 0,
		"development server supplied health, resources, and carry statistics")
	main.call("_on_inventory_button_pressed")
	await process_frame
	var inventory_panel: Control = main.get_node("GameView/InventoryPanel") as Control
	var inventory_grid: GridContainer = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/BackpackColumn/Scroll/InventoryGrid") as GridContainer
	var equipment_grid: GridContainer = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/EquipmentColumn/EquipmentGrid") as GridContainer
	var populated_inventory_buttons: int = _populated_item_buttons(inventory_grid)
	var populated_equipment_buttons: int = _populated_item_buttons(equipment_grid)
	var expected_inventory_buttons: int = _inventory_item_count(server_inventory, 0, 36)
	var expected_equipment_buttons: int = _inventory_item_count(server_inventory, 36, 44)
	_expect(inventory_panel.visible
		and Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).encloses(
			inventory_panel.get_global_rect()),
		"real inventory window opens entirely within the rendered viewport")
	_expect(populated_inventory_buttons == expected_inventory_buttons,
		"every real backpack item has a visible icon and quantity")
	_expect(populated_equipment_buttons == expected_equipment_buttons,
		"every real equipped item has a visible icon and quantity")
	var inventory_inspections: Array[Dictionary] = []
	# A Move click only lifts the item, as in the reference client, and asks
	# the server nothing; the Inspect tool is the click that looks.
	main.call("_set_inventory_tool", "inspect")
	for inspection_slot: int in _inventory_slots(server_inventory, 0, 36):
		_app_state.set("inventory_text", "")
		main.call("_on_inventory_slot_pressed", inspection_slot)
		var received_inventory_text: Callable = func() -> bool:
			return not str(_app_state.get("inventory_text")).is_empty()
		_expect(await _wait_for(received_inventory_text, 8.0),
			"real LOOK_AT_INVENTORY_ITEM receives the authoritative description for slot %d"
			% inspection_slot)
		var inspected_item: Dictionary = server_inventory.get(inspection_slot, {}) as Dictionary
		inventory_inspections.append({
			"slot": inspection_slot,
			"image_id": int(inspected_item.get("image_id", -1)),
			"text": str(_app_state.get("inventory_text")),
		})
	_app_state.call("close_item_detail")
	main.call("_set_inventory_tool", "grab")
	main.call("_sync_inventory")
	var inventory_description: RichTextLabel = main.get_node(
		"GameView/InventoryPanel/Content/InventoryDescription") as RichTextLabel
	_expect(inventory_description.get_parsed_text() == str(
		_app_state.get("inventory_text")),
		"inventory window presents the real server item description")
	await _capture("world-inventory.png")
	main.call("_on_inventory_close_pressed")
	main.call("_on_stats_button_pressed")
	await process_frame
	var stats_panel: Control = main.get_node("GameView/StatsPanel") as Control
	var resource_hud: Control = main.get_node("GameView/ResourceHud") as Control
	var stats_text: RichTextLabel = main.get_node("GameView/StatsPanel/StatsText") as RichTextLabel
	_expect(stats_panel.visible
		and Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).encloses(
			stats_panel.get_global_rect())
		and not stats_panel.get_global_rect().intersects(resource_hud.get_global_rect()),
		"real statistics window fits the viewport without covering the resource rail")
	_expect(stats_text.get_parsed_text().contains("CHARACTER STATISTICS")
		and stats_text.get_parsed_text().contains("Attack:")
		and stats_text.get_parsed_text().contains("Overall:"),
		"statistics window presents the authoritative character values")
	await _capture("world-stats.png")
	main.call("_on_stats_button_pressed")
	var quick_item_grid: GridContainer = main.get_node(
		"GameView/ItemQuickbar/ItemSlots") as GridContainer
	var quick_spell_grid: GridContainer = main.get_node(
		"GameView/SpellQuickbar/SpellContent/SpellSlots") as GridContainer
	var populated_quick_items: int = _populated_item_buttons(quick_item_grid)
	var expected_quick_items: int = _inventory_item_count(server_inventory, 0, 8)
	var configured_spell_slots: int = _configured_spell_buttons(quick_spell_grid)
	_expect(populated_quick_items == expected_quick_items,
		"every server item in slots one through eight populates the visible quickbar")
	_expect(configured_spell_slots == 6,
		"all six spell quick slots expose their configured availability state")
	_write_json("inventory-stats.json", {
		"inventory": _json_safe(server_inventory),
		"stats": _json_safe(server_stats),
		"known_knowledge": _json_safe(_app_state.get("known_knowledge")),
		"populated_inventory_buttons": populated_inventory_buttons,
		"populated_equipment_buttons": populated_equipment_buttons,
		"populated_quick_items": populated_quick_items,
		"expected_inventory_buttons": expected_inventory_buttons,
		"expected_equipment_buttons": expected_equipment_buttons,
		"expected_quick_items": expected_quick_items,
		"inventory_inspections": inventory_inspections,
		"configured_spell_slots": configured_spell_slots,
		"credentials": "REDACTED",
	})
	var visible_npc_ids: Array[int] = []
	for actor_id_value: Variant in (_app_state.get("actors") as Dictionary):
		var actor_id: int = int(actor_id_value)
		var actor_dto: Dictionary = (_app_state.get("actors") as Dictionary).get(
			actor_id, {}) as Dictionary
		if int(actor_dto.get("kind", 0)) == 2:
			visible_npc_ids.append(actor_id)
	_write_json("remote-actor.json", {
		"server_map": str(_app_state.get("current_map")),
		"remote_actor_id": remote_actor_id,
		"spawn_dto": _json_safe(remote_dto),
		"initial_tile": [remote_initial_tile.x, remote_initial_tile.y],
		"resulting_tile": [int(remote_dto.get("x", -1)),
			int(remote_dto.get("y", -1))],
		"render": _json_safe(remote_actor.render_diagnostics()),
		"visible_native_meshes": remote_visible_native_meshes,
		"selected": int(_app_state.get("selected_actor_id")) == remote_actor_id,
		"visible_npc_ids": visible_npc_ids,
		"credentials": "REDACTED",
	})
	await _capture("world-remote-player-selected.png")

	var gameplay_world: World3D = main.get("gameplay_world") as World3D
	_expect(gameplay_world != null, "gameplay World3D is non-null")
	var surface_hit: Dictionary = _surface_hit(gameplay_world, actor.server_target)
	var surface_position_value: Variant = surface_hit.get("position")
	_expect(surface_position_value is Vector3, "navigation surface exists below server spawn")
	if surface_position_value is Vector3:
		var surface_position: Vector3 = surface_position_value as Vector3
		_expect(absf(actor.global_position.y - (surface_position.y + 0.02)) < 0.04,
			"actor foot is aligned to the sampled navigation surface")

	var actor_focus: Vector3 = actor.global_position + Vector3.UP
	var actor_screen: Vector2 = camera.unproject_position(actor_focus)
	var actor_feet_screen: Vector2 = camera.unproject_position(actor.global_position)
	var actor_head_screen: Vector2 = camera.unproject_position(
		actor.global_position + Vector3.UP * 1.78)
	var actor_pixel_height: float = absf(actor_head_screen.y - actor_feet_screen.y)
	_expect(not camera.is_position_behind(actor_focus)
		and Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).has_point(actor_screen),
		"local actor is inside the gameplay camera frame")
	_expect(actor_pixel_height >= 24.0,
		"native actor remains readable at the default camera framing")
	var marker: MeshInstance3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/PlayerMapMarker") as MeshInstance3D
	var marker_mesh: CylinderMesh = marker.mesh as CylinderMesh
	_expect(marker.visible and Vector2(marker.global_position.x, marker.global_position.z).distance_to(
		Vector2(actor.global_position.x, actor.global_position.z)) < 0.01,
		"white local-player marker follows the actor")
	_expect(marker_mesh != null and marker_mesh.top_radius >= 5.0,
		"white local-player marker is legible at the full-map scale")
	var map_camera: Camera3D = main.get_node("GameView/MapViewport/MapCamera") as Camera3D
	var full_map_camera: Camera3D = main.get_node(
		"GameView/FullMapViewport/FullMapCamera") as Camera3D
	var camera_rig: IsometricCameraController = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig") as IsometricCameraController
	_expect((map_camera.cull_mask & 4) != 0 and (full_map_camera.cull_mask & 4) != 0,
		"minimap and full-map cameras both render the player marker")

	var evidence: Dictionary = {
		"server_map": str(_app_state.get("current_map")),
		"local_actor_id": local_actor_id,
		"spawn_dto": _json_safe(local_dto),
		"server_tile": [int(local_dto.get("x", -1)), int(local_dto.get("y", -1))],
		"converted_godot_position": str(actor.server_target),
		"navigation_surface_hit": _json_safe(surface_hit),
		"final_actor_position": str(actor.global_position),
		"render": _json_safe(actor.render_diagnostics()),
		"native_visible_meshes": visible_native_meshes,
		"camera_focus_screen": str(actor_screen),
		"actor_projected_height_pixels": actor_pixel_height,
		"camera": _json_safe(camera_rig.camera_diagnostics()),
		"credentials": "REDACTED",
	}
	_write_json("session.json", evidence)
	await _capture("world-default.png")

	var default_yaw: float = camera_rig.yaw_degrees
	var default_pitch: float = camera_rig.pitch_degrees
	var default_distance: float = camera_rig.distance
	var default_pan: Vector3 = camera_rig.pan_offset
	var right_down: InputEventMouseButton = InputEventMouseButton.new()
	right_down.button_index = MOUSE_BUTTON_RIGHT
	right_down.pressed = true
	main.call("_on_world_gui_input", right_down)
	var rotate_motion: InputEventMouseMotion = InputEventMouseMotion.new()
	rotate_motion.relative = Vector2(120.0, -16.0)
	main.call("_on_world_gui_input", rotate_motion)
	var right_up: InputEventMouseButton = InputEventMouseButton.new()
	right_up.button_index = MOUSE_BUTTON_RIGHT
	right_up.pressed = false
	main.call("_on_world_gui_input", right_up)
	_expect(not is_equal_approx(camera_rig.yaw_degrees, default_yaw)
		and not is_equal_approx(camera_rig.pitch_degrees, default_pitch),
		"right drag changes camera yaw and pitch in the rendered session")
	_expect(_actor_is_in_frame(camera, actor.global_position),
		"rotated camera keeps the local actor in frame")
	var rotated_camera: Dictionary = _json_safe(camera_rig.camera_diagnostics()) as Dictionary
	await _capture("world-rotated.png")

	var middle_down: InputEventMouseButton = InputEventMouseButton.new()
	middle_down.button_index = MOUSE_BUTTON_MIDDLE
	middle_down.pressed = true
	main.call("_on_world_gui_input", middle_down)
	var pan_motion: InputEventMouseMotion = InputEventMouseMotion.new()
	pan_motion.relative = Vector2(-18.0, 6.0)
	main.call("_on_world_gui_input", pan_motion)
	var middle_up: InputEventMouseButton = InputEventMouseButton.new()
	middle_up.button_index = MOUSE_BUTTON_MIDDLE
	middle_up.pressed = false
	main.call("_on_world_gui_input", middle_up)
	_expect(camera_rig.pan_offset.distance_to(default_pan) > 0.1,
		"middle drag changes the intentional camera pan offset")
	_expect(_actor_is_in_frame(camera, actor.global_position),
		"panned camera keeps the local actor in frame")
	var panned_camera: Dictionary = _json_safe(camera_rig.camera_diagnostics()) as Dictionary
	await _capture("world-panned.png")

	for unused_zoom_step: int in range(3):
		var wheel_up: InputEventMouseButton = InputEventMouseButton.new()
		wheel_up.button_index = MOUSE_BUTTON_WHEEL_UP
		wheel_up.pressed = true
		main.call("_on_world_gui_input", wheel_up)
	_expect(camera_rig.distance < default_distance,
		"mouse wheel changes camera zoom in the rendered session")
	_expect(_actor_is_in_frame(camera, actor.global_position),
		"zoomed camera keeps the local actor in frame")
	var zoomed_camera: Dictionary = _json_safe(camera_rig.camera_diagnostics()) as Dictionary
	await _capture("world-zoomed.png")
	_write_json("camera-states.json", {
		"default": evidence.get("camera", {}),
		"rotated": rotated_camera,
		"panned": panned_camera,
		"zoomed": zoomed_camera,
		"credentials": "REDACTED",
	})

	# Restore the useful spawn framing before map and movement evidence. This also
	# proves camera input does not permanently detach follow from the actor.
	camera_rig.yaw_degrees = default_yaw
	camera_rig.pitch_degrees = default_pitch
	camera_rig.distance = default_distance
	camera_rig.reset_pan()
	camera_rig.set_focus(actor.global_position)
	_expect(camera_rig.pan_offset.is_equal_approx(default_pan)
		and camera_rig.focus.is_equal_approx(actor.global_position),
		"default camera framing restores without losing actor follow")

	var full_map: Control = main.get_node("GameView/FullMap") as Control
	main.call("_on_map_button_pressed")
	await process_frame
	await _capture("world-full-map.png")
	full_map.hide()

	var initial_tile := Vector2i(int(local_dto.get("x", 0)), int(local_dto.get("y", 0)))
	var click_sent: bool = await _send_real_world_click(main, camera, initial_tile)
	_expect(click_sent, "viewport click produced an authoritative actor tile update")
	if click_sent:
		for unused_frame: int in range(8):
			await physics_frame
			await process_frame
		actors = _app_state.get("actors") as Dictionary
		var resulting_dto: Dictionary = actors.get(local_actor_id, {}) as Dictionary
		var resulting_actor: ReplicatedActor3D = (
			main.get("actor_nodes") as Dictionary).get(
			local_actor_id) as ReplicatedActor3D
		var movement_evidence: Dictionary = {
			"initial_tile": [initial_tile.x, initial_tile.y],
			"resulting_tile": [int(resulting_dto.get("x", -1)),
				int(resulting_dto.get("y", -1))],
			"resulting_actor_position": str(resulting_actor.global_position),
			"actor_yaw_radians": resulting_actor.rotation.y,
			"camera": _json_safe(camera_rig.camera_diagnostics()),
			"credentials": "REDACTED",
		}
		_write_json("movement.json", movement_evidence)
		await _capture("world-after-move.png")

		main.call("_on_sit_button_pressed")
		var sitting_received: Callable = func() -> bool:
			var current_actors: Dictionary = _app_state.get("actors") as Dictionary
			var current_dto: Dictionary = current_actors.get(local_actor_id, {}) as Dictionary
			return bool(current_dto.get("sitting", false))
		var sat_down: bool = await _wait_for(sitting_received, 8.0)
		_expect(sat_down, "real server accepted the explicit sit request")
		var seated_idle_started: Callable = func() -> bool:
			var current_actor: ReplicatedActor3D = (
				main.get("actor_nodes") as Dictionary).get(
				local_actor_id) as ReplicatedActor3D
			return current_actor != null and current_actor.current_action == &"seated_idle"
		_expect(await _wait_for(seated_idle_started, 5.0),
			"native sit transition advances to the explicit seated idle")
		await _capture("world-seated.png")

		main.call("_on_sit_button_pressed")
		var standing_received: Callable = func() -> bool:
			var current_actors: Dictionary = _app_state.get("actors") as Dictionary
			var current_dto: Dictionary = current_actors.get(local_actor_id, {}) as Dictionary
			return not bool(current_dto.get("sitting", true))
		var stood_up: bool = await _wait_for(standing_received, 8.0)
		_expect(stood_up, "real server accepted the explicit stand request")
		var idle_after_stand: Callable = func() -> bool:
			var current_actor: ReplicatedActor3D = (
				main.get("actor_nodes") as Dictionary).get(
				local_actor_id) as ReplicatedActor3D
			return current_actor != null and current_actor.current_action == &"idle"
		_expect(await _wait_for(idle_after_stand, 5.0),
			"native stand transition returns to explicit idle")

		main.call("_on_sit_button_pressed")
		var sat_before_move: bool = await _wait_for(sitting_received, 8.0)
		_expect(sat_before_move,
			"actor can sit again before automatic-standing movement test")
		var actors_before_auto_stand: Dictionary = _app_state.get("actors") as Dictionary
		var dto_before_auto_stand: Dictionary = actors_before_auto_stand.get(
			local_actor_id, {}) as Dictionary
		var tile_before_auto_stand: Vector2i = Vector2i(
			int(dto_before_auto_stand.get("x", -1)),
			int(dto_before_auto_stand.get("y", -1)))
		var auto_stand_move: bool = await _send_real_world_click(
			main, camera, tile_before_auto_stand)
		_expect(auto_stand_move, "movement while seated receives an authoritative step")
		var automatically_stood: bool = await _wait_for(standing_received, 8.0)
		_expect(automatically_stood, "server automatically stands the actor before movement")
		var actors_after_auto_stand: Dictionary = _app_state.get("actors") as Dictionary
		var dto_after_auto_stand: Dictionary = actors_after_auto_stand.get(
			local_actor_id, {}) as Dictionary
		var actor_after_auto_stand: ReplicatedActor3D = (
			main.get("actor_nodes") as Dictionary).get(
			local_actor_id) as ReplicatedActor3D
		_write_json("sit-stand.json", {
			"sit_packet": "07 02 00 01",
			"stand_packet": "07 02 00 00",
			"server_sit": sat_down,
			"seated_action": "seated_idle",
			"server_stand": stood_up,
			"standing_action": "idle",
			"automatic_stand_on_move": automatically_stood,
			"tile_before_auto_stand": [tile_before_auto_stand.x,
				tile_before_auto_stand.y],
			"tile_after_auto_stand": [int(dto_after_auto_stand.get("x", -1)),
				int(dto_after_auto_stand.get("y", -1))],
			"resulting_actor_position": str(actor_after_auto_stand.global_position),
			"resulting_action": str(actor_after_auto_stand.current_action),
			"credentials": "REDACTED",
		})
		await _capture("world-standing-after-move.png")

	var guard_specs: Array[Dictionary] = [
		{
			"name": "spear",
			"part": 0,
			"source_slot": _inspection_slot_for(inventory_inspections,
				"Four Gates Guard Spear"),
			"wear_slot": 36,
			"allowed_visuals": [11, 112],
			"bone": "hand_r",
		},
		{
			"name": "shield",
			"part": 1,
			"source_slot": _inspection_slot_for(inventory_inspections,
				"Guard Shield"),
			"wear_slot": 37,
			"allowed_visuals": [5, 105],
			"bone": "hand_l",
		},
		{
			# Modified 2026-08-28 for Eloria Client: the cape is a skinned
			# garment now, so it binds to this actor's skeleton rather than
			# hanging off one bone.
			"name": "cape",
			"part": 2,
			"attach": "skinned",
			"source_slot": _inspection_slot_for(inventory_inspections,
				"Guard Cape"),
			"wear_slot": 38,
			"allowed_visuals": [11, 105],
			"bone": "spine_03",
		},
	]
	main.call("_on_inventory_button_pressed")
	var guard_server_visuals: Dictionary = {}
	for guard_spec: Dictionary in guard_specs:
		var source_slot: int = int(guard_spec.get("source_slot", -1))
		var wear_slot: int = int(guard_spec.get("wear_slot", -1))
		var part: int = int(guard_spec.get("part", -1))
		var guard_name: String = str(guard_spec.get("name", "guard item"))
		_expect(source_slot >= 0, "real inventory contains the Four Gates guard " + guard_name)
		if source_slot < 0:
			continue
		main.call("_on_inventory_slot_pressed", source_slot)
		main.call("_on_inventory_equip_pressed")
		var guard_equipped: Callable = func() -> bool:
			var current_inventory: Dictionary = _app_state.get("inventory") as Dictionary
			var current_actors: Dictionary = _app_state.get("actors") as Dictionary
			var current_dto: Dictionary = current_actors.get(local_actor_id, {}) as Dictionary
			var current_visuals: Dictionary = current_dto.get("equipment_visuals", {}) as Dictionary
			return current_inventory.has(wear_slot) and not current_inventory.has(source_slot) \
				and _equipment_visual_id(current_visuals, part) >= 0
		var equipped_ok: bool = await _wait_for(guard_equipped, 8.0)
		_expect(equipped_ok,
			"real MOVE_INVENTORY_ITEM equips guard %s into wear slot %d and broadcasts part %d"
			% [guard_name, wear_slot, part])
		if not equipped_ok:
			continue
		var equipped_actors: Dictionary = _app_state.get("actors") as Dictionary
		var equipped_dto: Dictionary = equipped_actors.get(local_actor_id, {}) as Dictionary
		var equipped_visuals: Dictionary = equipped_dto.get("equipment_visuals", {}) as Dictionary
		var server_visual_id: int = _equipment_visual_id(equipped_visuals, part)
		guard_server_visuals[part] = server_visual_id
		var allowed_visuals: Array = guard_spec.get("allowed_visuals", []) as Array
		_expect(allowed_visuals.has(server_visual_id),
			"server guard %s visual id %d is a supported legacy/native compatibility id"
			% [guard_name, server_visual_id])
	main.call("_sync_inventory")
	for guard_spec: Dictionary in guard_specs:
		var wear_slot: int = int(guard_spec.get("wear_slot", -1))
		var button_index: int = wear_slot - 36
		var equipped_button: Button = equipment_grid.get_child(button_index) as Button
		_expect(equipped_button != null and equipped_button.icon != null
			and equipped_button.text.contains("×1"),
			"authoritative guard %s appears in wear slot %d"
			% [str(guard_spec.get("name", "item")), wear_slot])
	var equipped_actor: ReplicatedActor3D = (
		main.get("actor_nodes") as Dictionary).get(local_actor_id) as ReplicatedActor3D
	var equipped_diagnostics: Dictionary = equipped_actor.equipment_diagnostics()
	_expect(int(equipped_diagnostics.get("native", 0)) == 3
		and int(equipped_diagnostics.get("fallback", 0)) == 0,
		"all three guard visuals resolve to native equipment with zero fallback")
	_expect(int(equipped_diagnostics.get("socket", 0)) == 2
		and int(equipped_diagnostics.get("skinned", 0)) >= 1,
		"guard loadout resolves two socketed props and a skinned cape")
	var native_attachments: Dictionary = _native_equipment_attachments(equipped_actor)
	for guard_spec: Dictionary in guard_specs:
		var part: int = int(guard_spec.get("part", -1))
		var attachment: Dictionary = native_attachments.get(part, {}) as Dictionary
		if str(guard_spec.get("attach", "socket")) == "skinned":
			_expect(int(attachment.get("visible_meshes", 0)) > 0
				and bool(attachment.get("under_skeleton", false))
				and bool(attachment.get("skinned", false)),
				"native guard %s binds to the actor skeleton with visible geometry"
				% str(guard_spec.get("name", "item")))
			continue
		_expect(str(attachment.get("bone", "")) == str(guard_spec.get("bone", ""))
			and int(attachment.get("visible_meshes", 0)) > 0
			and bool(attachment.get("under_skeleton", false)),
			"native guard %s attaches to %s with visible geometry under the actor skeleton"
			% [str(guard_spec.get("name", "item")), str(guard_spec.get("bone", ""))])
	var attachment_positions_before: Dictionary = _native_equipment_attachment_positions(
		equipped_actor)
	equipped_actor.play_action(&"walk")
	for unused_equipment_animation_frame: int in range(12):
		await process_frame
	var attachment_positions_after: Dictionary = _native_equipment_attachment_positions(
		equipped_actor)
	var animation_followed_parts: int = 0
	var socketed_parts: int = 0
	for guard_spec: Dictionary in guard_specs:
		if str(guard_spec.get("attach", "socket")) != "socket":
			continue
		socketed_parts += 1
		var part: int = int(guard_spec.get("part", -1))
		var before_value: Variant = attachment_positions_before.get(part)
		var after_value: Variant = attachment_positions_after.get(part)
		if before_value is Vector3 and after_value is Vector3 and (
				before_value as Vector3).distance_to(after_value as Vector3) > 0.0005:
			animation_followed_parts += 1
	_expect(animation_followed_parts == socketed_parts,
		"spear and shield sockets follow native actor animation")
	var skinned_bindings: Dictionary = _skinned_equipment_bindings(equipped_actor)
	for guard_spec: Dictionary in guard_specs:
		if str(guard_spec.get("attach", "socket")) != "skinned":
			continue
		var binding: Dictionary = skinned_bindings.get(
			int(guard_spec.get("part", -1)), {}) as Dictionary
		_expect(int(binding.get("binds", 0)) > 0
			and int(binding.get("resolved", 0)) == int(binding.get("binds", -1))
			and bool(binding.get("skeleton", false)),
			"native guard %s rebinds every joint onto the actor skeleton"
			% str(guard_spec.get("name", "item")))
	equipped_actor.play_action(&"idle")
	main.call("_on_inventory_close_pressed")
	var equipment_capture_distance: float = camera_rig.distance
	var equipment_capture_yaw: float = camera_rig.yaw_degrees
	var equipment_capture_pitch: float = camera_rig.pitch_degrees
	camera_rig.distance = 9.0
	camera_rig.pitch_degrees = -38.0
	camera_rig.set_focus(equipped_actor.global_position + Vector3.UP * 0.2)
	camera_rig.yaw_degrees = default_yaw - 38.0
	await _capture("world-equipment-native-spear.png")
	await _capture("world-equipment-fallback.png")
	camera_rig.yaw_degrees = default_yaw + 38.0
	await _capture("world-equipment-native-shield.png")
	camera_rig.yaw_degrees = default_yaw + 180.0
	await _capture("world-equipment-native-cape.png")
	camera_rig.distance = equipment_capture_distance
	camera_rig.yaw_degrees = equipment_capture_yaw
	camera_rig.pitch_degrees = equipment_capture_pitch
	camera_rig.set_focus(equipped_actor.global_position)
	main.call("_on_inventory_button_pressed")
	for guard_index: int in range(guard_specs.size() - 1, -1, -1):
		var guard_spec: Dictionary = guard_specs[guard_index]
		var wear_slot: int = int(guard_spec.get("wear_slot", -1))
		var part: int = int(guard_spec.get("part", -1))
		main.call("_on_equipment_slot_pressed", wear_slot)
		main.call("_on_inventory_unequip_pressed")
		var guard_unequipped: Callable = func() -> bool:
			var current_inventory: Dictionary = _app_state.get("inventory") as Dictionary
			var current_actors: Dictionary = _app_state.get("actors") as Dictionary
			var current_dto: Dictionary = current_actors.get(local_actor_id, {}) as Dictionary
			var current_visuals: Dictionary = current_dto.get("equipment_visuals", {}) as Dictionary
			return not current_inventory.has(wear_slot) \
				and _equipment_visual_id(current_visuals, part) < 0
		_expect(await _wait_for(guard_unequipped, 8.0),
			"real MOVE_INVENTORY_ITEM unequips guard %s from wear slot %d and clears part %d"
			% [str(guard_spec.get("name", "item")), wear_slot, part])
	main.call("_on_inventory_close_pressed")
	var unequipped_diagnostics: Dictionary = equipped_actor.equipment_diagnostics()
	var restored_inventory: Dictionary = _app_state.get("inventory") as Dictionary
	_expect(int(unequipped_diagnostics.get("native", 0)) == 0
		and int(unequipped_diagnostics.get("fallback", 0)) == 0,
		"authoritative unwear removes every native guard attachment cleanly")
	_expect(_inventory_item_count(restored_inventory, 0, 36) == expected_inventory_buttons,
		"all guard items return to the backpack after authoritative unwear")
	_write_json("equipment.json", {
		"wear_slots": [36, 37, 38],
		"server_visual_ids": _json_safe(guard_server_visuals),
		"supported_visual_ids": {
			"0": [11, 112],
			"1": [5, 105],
			"2": [11, 105],
		},
		"native_attachments": _json_safe(native_attachments),
		"animation_followed_parts": animation_followed_parts,
		"equipped_diagnostics": _json_safe(equipped_diagnostics),
		"unequipped_diagnostics": _json_safe(unequipped_diagnostics),
		"restored_inventory": _json_safe(restored_inventory),
		"credentials": "REDACTED",
	})


	helper_network.disconnect_from_server()
	var helper_removed: Callable = func() -> bool:
		return (not (_app_state.get("actors") as Dictionary).has(remote_actor_id)
			and not (main.get("actor_nodes") as Dictionary).has(remote_actor_id))
	_expect(await _wait_for(helper_removed, 8.0),
		"remote-player disconnect removes authoritative and rendered actor state")
	helper_network.queue_free()
	_network.call("disconnect_from_server")
	print("rendered server session: ", "PASS" if _failures == 0 else "FAIL")
	print("credentials: REDACTED")
	_finish()

func _send_real_world_click(main: Control, camera: Camera3D,
		initial_tile: Vector2i) -> bool:
	var adapter: CoordinateAdapter = main.get("adapter") as CoordinateAdapter
	var offsets: Array[Vector2i] = [Vector2i(4, 0), Vector2i(-4, 0),
		Vector2i(0, 4), Vector2i(0, -4)]
	for offset: Vector2i in offsets:
		var target_tile: Vector2i = initial_tile + offset
		var target_world: Vector3 = adapter.tile_center(target_tile.x, target_tile.y)
		var gameplay_world: World3D = main.get("gameplay_world") as World3D
		var hit: Dictionary = _surface_hit(gameplay_world, target_world)
		var hit_value: Variant = hit.get("position")
		if not hit_value is Vector3:
			continue
		target_world = hit_value as Vector3
		if camera.is_position_behind(target_world):
			continue
		var viewport_position: Vector2 = camera.unproject_position(target_world)
		if not Rect2(Vector2(8.0, 8.0), Vector2(SCREEN_SIZE) - Vector2(16.0, 16.0)).has_point(
				viewport_position):
			continue
		var click: InputEventMouseButton = InputEventMouseButton.new()
		click.button_index = MOUSE_BUTTON_LEFT
		click.pressed = true
		click.position = viewport_position
		main.call("_on_world_gui_input", click)
		var actor_tile_changed: Callable = func() -> bool:
			var local_id: int = int(_app_state.get("local_actor_id"))
			var actors: Dictionary = _app_state.get("actors") as Dictionary
			var dto: Dictionary = actors.get(local_id, {}) as Dictionary
			return Vector2i(int(dto.get("x", initial_tile.x)),
				int(dto.get("y", initial_tile.y))) != initial_tile
		var changed: bool = await _wait_for(actor_tile_changed, 8.0)
		if changed:
			return true
		# Restore focus before trying another reachable direction.
		main.call("_update_local_actor_follow")
	return false

func _move_remote_helper(helper_network: EloriaNetworkClient, remote_actor_id: int,
		initial_tile: Vector2i) -> bool:
	var offsets: Array[Vector2i] = [Vector2i(-4, 0), Vector2i(0, -4),
		Vector2i(4, 0), Vector2i(0, 4)]
	for offset: Vector2i in offsets:
		var send_error: Error = helper_network.move_to(initial_tile + offset)
		if send_error != OK:
			continue
		var remote_tile_changed: Callable = func() -> bool:
			var actors: Dictionary = _app_state.get("actors") as Dictionary
			var dto: Dictionary = actors.get(remote_actor_id, {}) as Dictionary
			return Vector2i(int(dto.get("x", initial_tile.x)),
				int(dto.get("y", initial_tile.y))) != initial_tile
		if await _wait_for(remote_tile_changed, 8.0):
			return true
	return false

func _chat_contains(lines: Array, marker: String) -> bool:
	for line_value: Variant in lines:
		if line_value is Dictionary and str(
				(line_value as Dictionary).get("text", "")).contains(marker):
			return true
	return false

func _inspection_slot_for(inspections: Array[Dictionary], marker: String) -> int:
	for inspection: Dictionary in inspections:
		if str(inspection.get("text", "")).contains(marker):
			return int(inspection.get("slot", -1))
	return -1

func _equipment_visual_id(visuals: Dictionary, part: int) -> int:
	if visuals.has(part):
		return int(visuals[part])
	if visuals.has(str(part)):
		return int(visuals[str(part)])
	return -1

func _equipment_attachment_part(attachment: BoneAttachment3D) -> int:
	var attachment_name: String = str(attachment.name)
	for part: int in range(8):
		if attachment_name.begins_with("EquipmentPart_%d_Visual_" % part):
			return part
	return -1

func _equipment_skin_part(mesh_node: MeshInstance3D) -> int:
	var mesh_name: String = str(mesh_node.name)
	for part: int in range(8):
		if mesh_name.begins_with("EquipmentSkin_%d_Visual_" % part):
			return part
	return -1

func _native_equipment_attachments(actor: ReplicatedActor3D) -> Dictionary:
	# Modified 2026-08-28 for Eloria Client: worn equipment is skinned to the
	# actor's skeleton, so a bone attachment is no longer the only shape a
	# native equipment node takes.
	var attachments: Dictionary = {}
	for node_value: Node in actor.find_children("*", "BoneAttachment3D", true, false):
		var attachment: BoneAttachment3D = node_value as BoneAttachment3D
		if not attachment.has_meta("native_equipment"):
			continue
		var part: int = _equipment_attachment_part(attachment)
		if part < 0:
			continue
		attachments[part] = {
			"bone": str(attachment.bone_name),
			"path": str(attachment.get_path()),
			"under_skeleton": attachment.get_parent() is Skeleton3D,
			"skinned": false,
			"visible_meshes": _visible_native_mesh_count(attachment),
		}
	for node_value: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if not mesh_node.has_meta("native_equipment"):
			continue
		var part: int = _equipment_skin_part(mesh_node)
		if part < 0:
			continue
		var entry: Dictionary = attachments.get(part, {
			"bone": "", "path": str(mesh_node.get_path()),
			"under_skeleton": mesh_node.get_parent() is Skeleton3D,
			"skinned": true, "visible_meshes": 0}) as Dictionary
		entry["skinned"] = true
		entry["visible_meshes"] = int(entry.get("visible_meshes", 0)) + (
			1 if mesh_node.mesh != null and mesh_node.is_visible_in_tree() else 0)
		attachments[part] = entry
	return attachments

func _native_equipment_attachment_positions(actor: ReplicatedActor3D) -> Dictionary:
	var positions: Dictionary = {}
	for node_value: Node in actor.find_children("*", "BoneAttachment3D", true, false):
		var attachment: BoneAttachment3D = node_value as BoneAttachment3D
		if not attachment.has_meta("native_equipment"):
			continue
		var part: int = _equipment_attachment_part(attachment)
		if part >= 0:
			positions[part] = attachment.global_transform.origin
	return positions

func _skinned_equipment_bindings(actor: ReplicatedActor3D) -> Dictionary:
	# A skinned garment's own node never moves - the skeleton deforms it - so it
	# is checked structurally: its skin must be bound to this actor's skeleton.
	var bindings: Dictionary = {}
	var skeleton: Skeleton3D = null
	for node_value: Node in actor.find_children("*", "Skeleton3D", true, false):
		skeleton = node_value as Skeleton3D
		break
	for node_value: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if not mesh_node.has_meta("native_equipment"):
			continue
		var part: int = _equipment_skin_part(mesh_node)
		if part < 0 or mesh_node.skin == null:
			continue
		var bound: int = 0
		for index: int in range(mesh_node.skin.get_bind_count()):
			var bone_name: String = mesh_node.skin.get_bind_name(index)
			if skeleton != null and not bone_name.is_empty() and (
					skeleton.find_bone(bone_name) >= 0):
				bound += 1
		bindings[part] = {
			"binds": mesh_node.skin.get_bind_count(),
			"resolved": bound,
			"skeleton": mesh_node.get_node_or_null(mesh_node.skeleton) == skeleton,
		}
	return bindings

func _populated_item_buttons(container: Container) -> int:
	var populated: int = 0
	for child: Node in container.get_children():
		if child is Button:
			var button: Button = child as Button
			if button.icon != null and button.text.contains("×"):
				populated += 1
	return populated

func _inventory_item_count(inventory: Dictionary, first_slot: int, end_slot: int) -> int:
	var count: int = 0
	for slot_value: Variant in inventory:
		var slot: int = int(slot_value)
		if slot >= first_slot and slot < end_slot:
			count += 1
	return count

func _inventory_slots(inventory: Dictionary, first_slot: int, end_slot: int) -> Array[int]:
	var slots: Array[int] = []
	for slot_value: Variant in inventory:
		var slot: int = int(slot_value)
		if slot >= first_slot and slot < end_slot:
			slots.append(slot)
	slots.sort()
	return slots

func _configured_spell_buttons(container: Container) -> int:
	var configured: int = 0
	for child: Node in container.get_children():
		if child is Button:
			var button: Button = child as Button
			if button.text.begins_with("S") and not button.tooltip_text.is_empty():
				configured += 1
	return configured

func _surface_hit(world: World3D, target: Vector3) -> Dictionary:
	if world == null:
		return {}
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(
		Vector3(target.x, 400.0, target.z), Vector3(target.x, -100.0, target.z),
		WorldLoader.NAVIGATION_SURFACE_LAYER)
	return world.direct_space_state.intersect_ray(query)

func _visible_native_mesh_count(native_model: Node3D) -> int:
	if native_model == null:
		return 0
	var count := 0
	for node_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		if mesh_node.mesh != null and mesh_node.is_visible_in_tree() and mesh_node.layers != 0:
			count += 1
	return count

func _actor_is_in_frame(camera: Camera3D, actor_position: Vector3) -> bool:
	var focus_position: Vector3 = actor_position + Vector3.UP
	if camera.is_position_behind(focus_position):
		return false
	return Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).has_point(
		camera.unproject_position(focus_position))

func _wait_for(predicate: Callable, timeout_seconds: float) -> bool:
	var deadline_msec: int = Time.get_ticks_msec() + roundi(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline_msec:
		if bool(predicate.call()):
			return true
		await process_frame
	return bool(predicate.call())

func _capture(file_name: String) -> void:
	await process_frame
	await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		"rendered screenshot has the reference dimensions")
	var sampled_colors: Dictionary = {}
	for y: int in range(0, image.get_height(), 24):
		for x: int in range(0, image.get_width(), 24):
			sampled_colors[image.get_pixel(x, y).to_html()] = true
	_expect(sampled_colors.size() >= 24, "rendered screenshot is not a blank/dummy frame")
	var result: Error = image.save_png(_artifact_directory.path_join(file_name))
	_expect(result == OK, "saved " + file_name)

func _write_json(file_name: String, value: Dictionary) -> void:
	var file: FileAccess = FileAccess.open(
		_artifact_directory.path_join(file_name), FileAccess.WRITE)
	if file == null:
		_fail("could not open " + file_name)
		return
	file.store_string(JSON.stringify(value, "  "))
	file.close()

func _json_safe(value: Variant) -> Variant:
	if value is Dictionary:
		var converted: Dictionary = {}
		for key_value: Variant in value:
			converted[str(key_value)] = _json_safe((value as Dictionary)[key_value])
		return converted
	if value is Array:
		var converted_array: Array = []
		for item: Variant in value as Array:
			converted_array.append(_json_safe(item))
		return converted_array
	if value is Vector2 or value is Vector2i or value is Vector3 or value is Vector3i:
		return str(value)
	if value is Transform3D or value is Basis or value is AABB:
		return str(value)
	return value

func _random_hex(byte_count: int) -> String:
	var crypto: Crypto = Crypto.new()
	return crypto.generate_random_bytes(byte_count).hex_encode()

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
	else:
		_fail(message)

func _fail(message: String) -> void:
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	quit(_failures)
