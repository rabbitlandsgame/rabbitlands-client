extends SceneTree

var failures: int = 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		quit(failures)
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var game_view: Control = main.get_node("GameView") as Control
	var login_panel: Control = main.get_node("LoginPanel") as Control
	var new_character: Button = main.get_node("LoginPanel/Content/NewCharacter") as Button
	var status: Label = main.get_node("LoginPanel/Content/Status") as Label
	var container: TextureRect = main.get_node("GameView/ViewportContainer") as TextureRect
	var world_viewport: SubViewport = main.get_node("GameView/ViewportContainer/Viewport") as SubViewport
	var minimap_viewport: SubViewport = main.get_node("GameView/MapViewport") as SubViewport
	var full_map_viewport: SubViewport = main.get_node("GameView/FullMapViewport") as SubViewport
	var map_camera: Camera3D = main.get_node("GameView/MapViewport/MapCamera") as Camera3D
	var full_map_camera: Camera3D = main.get_node(
		"GameView/FullMapViewport/FullMapCamera") as Camera3D
	var minimap_image: TextureRect = main.get_node("GameView/MinimapFrame/Minimap") as TextureRect
	var full_map_image: TextureRect = main.get_node(
		"GameView/FullMap/MapLayout/MapImage") as TextureRect
	var camera_rig: IsometricCameraController = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig") as IsometricCameraController
	var compass_overlay: TextureRect = main.get_node(
		"GameView/MinimapFrame/CompassOverlay") as TextureRect
	var player_marker: MeshInstance3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/PlayerMapMarker") as MeshInstance3D
	game_view.show()
	var original_window_size: Vector2i = root.size
	root.size = Vector2i(1100, 720)
	await process_frame
	main.call("_on_window_size_changed")
	_expect(world_viewport.size.x != roundi(float(world_viewport.size.y) * 16.0 / 9.0),
		"resizing changes the gameplay viewport aspect without stretching 16:9")
	_expect(world_viewport.size == Vector2i(1100, 720),
		"the world renders at the window pixel size, not the 1280x720 design canvas")
	root.size = original_window_size
	await process_frame
	_expect(container.mouse_filter == Control.MOUSE_FILTER_STOP,
		"world viewport receives gameplay mouse input")
	_expect(container.gui_input.is_connected(Callable(main, "_on_world_gui_input")),
		"world viewport input handler is connected")
	_expect(minimap_image.gui_input.is_connected(Callable(main, "_on_minimap_gui_input")),
		"minimap click-to-walk input handler is connected")
	_expect(full_map_image.gui_input.is_connected(Callable(main, "_on_full_map_gui_input")),
		"Tab map click-to-walk input handler is connected")
	_expect(not compass_overlay.visible and compass_overlay.texture == null,
		"minimap render is not covered by decorative artwork")
	var minimap_frame: Control = main.get_node("GameView/MinimapFrame") as Control
	_expect(not minimap_frame.visible and minimap_frame.anchor_left == 0.0
		and InputMap.has_action("toggle_minimap"),
		"Alt+M controls a floating minimap outside the right HUD rail")
	_expect(minimap_frame.gui_input.is_connected(Callable(main, "_on_minimap_frame_gui_input"))
		and main.get_node("GameView/MinimapFrame/North") is Label
		and main.get_node("GameView/MinimapFrame/East") is Label
		and main.get_node("GameView/MinimapFrame/South") is Label
		and main.get_node("GameView/MinimapFrame/West") is Label,
		"minimap compass border exposes cardinal labels and drag/context input")
	var minimap_menu: PopupMenu = main.get("_minimap_menu") as PopupMenu
	var minimap_border_style: StyleBoxFlat = minimap_frame.get_theme_stylebox(
		"panel") as StyleBoxFlat
	_check_minimap_menu(main, minimap_menu)
	_expect(minimap_border_style != null
		and minimap_border_style.get_border_width(SIDE_LEFT) == 6
		and is_equal_approx(minimap_image.offset_left,
			float(main.get("_minimap_border"))),
		"minimap keeps its thick compass ring over a margin the render fills")
	# Scroll wheel over the minimap frames more or less ground. The camera is
	# orthographic, so its size is that width in metres.
	var minimap_camera: Camera3D = map_camera
	var zoom_out := InputEventMouseButton.new()
	zoom_out.button_index = MOUSE_BUTTON_WHEEL_DOWN
	zoom_out.pressed = true
	var zoom_in := InputEventMouseButton.new()
	zoom_in.button_index = MOUSE_BUTTON_WHEEL_UP
	zoom_in.pressed = true
	var zoom_start: float = minimap_camera.size
	main.call("_on_minimap_gui_input", zoom_out)
	_expect(minimap_camera.size > zoom_start,
		"scrolling down over the minimap shows more ground")
	main.call("_on_minimap_gui_input", zoom_in)
	_expect(is_equal_approx(minimap_camera.size, zoom_start),
		"scrolling back up returns the minimap to the width it had")
	for _step: int in range(40):
		main.call("_on_minimap_gui_input", zoom_in)
	_expect(is_equal_approx(minimap_camera.size,
		float(main.get("MINIMAP_ZOOM_MIN"))),
		"minimap zoom stops at its closest bound instead of inverting")
	for _step: int in range(80):
		main.call("_on_minimap_gui_input", zoom_out)
	_expect(is_equal_approx(minimap_camera.size,
		float(main.get("MINIMAP_ZOOM_MAX"))),
		"minimap zoom stops at its widest bound")
	main.set("_minimap_zoom", float(main.get("MINIMAP_ZOOM_DEFAULT")))
	main.call("_apply_minimap_zoom")
	# The world camera zooms in to a portrait at a metre and a half and stops
	# there instead of inverting. The near plane follows the zoom - a quarter
	# of the orbit distance, capped at the authored 1 m - which is what lets
	# the floor sit inside the old fixed plane without clipping the actor,
	# while a zoomed-out camera keeps the full metre the fixed-point depth
	# buffer needs over long vistas (see the rig's own comment). Interiors
	# override the floor through their manifests' camera blocks.
	var rig_start_distance: float = float(camera_rig.get("distance"))
	var rig_camera: Camera3D = camera_rig.get("camera") as Camera3D
	_expect(rig_camera != null and is_equal_approx(rig_camera.near, 1.0),
		"zoomed out, the camera keeps the authored one-metre near plane")
	for _step: int in range(80):
		camera_rig.handle_mouse_button(zoom_in)
	_expect(is_equal_approx(float(camera_rig.get("distance")), 1.5),
		"the world camera zooms in to the metre-and-a-half floor")
	_expect(rig_camera != null and is_equal_approx(rig_camera.near, 0.375),
		"the near plane narrows with the zoom, so the close camera clips nothing")
	camera_rig.set("distance", rig_start_distance)
	camera_rig.call("_update_camera")
	_expect(rig_camera != null and is_equal_approx(rig_camera.near, 1.0),
		"zooming back out restores the full near plane and its depth precision")
	main.call("_on_minimap_orientation_selected", 1)
	_expect(str(main.get("_minimap_orientation")) == "player_up",
		"minimap can rotate with the player")
	main.call("_on_minimap_orientation_selected", 2)
	_expect(str(main.get("_minimap_orientation")) == "viewport_up",
		"minimap can rotate with the viewport")
	main.call("_on_minimap_orientation_selected", 0)
	var resolved_world: World3D = world_viewport.find_world_3d()
	_expect(resolved_world != null, "gameplay World3D resolves from the world viewport")
	_expect(minimap_viewport.world_3d != null and minimap_viewport.world_3d == resolved_world,
		"minimap shares the gameplay World3D")
	_expect(full_map_viewport.world_3d != null and full_map_viewport.world_3d == resolved_world,
		"Tab map shares the gameplay World3D")
	_expect(minimap_image.texture == minimap_viewport.get_texture(),
		"minimap displays its live viewport texture")
	_expect(full_map_image.texture == full_map_viewport.get_texture(),
		"Tab map displays its live viewport texture")
	var minimap_center: Vector2 = main.call("_control_to_viewport_position",
		minimap_image.size * 0.5, minimap_image.size, minimap_viewport.size) as Vector2
	var full_map_center: Vector2 = main.call("_control_to_viewport_position",
		full_map_image.size * 0.5, full_map_image.size, full_map_viewport.size) as Vector2
	_expect(minimap_center.is_equal_approx(Vector2(minimap_viewport.size) * 0.5),
		"minimap controls convert local clicks into minimap viewport pixels")
	_expect(full_map_center.is_equal_approx(Vector2(full_map_viewport.size) * 0.5),
		"Tab map controls convert local clicks into full-map viewport pixels")
	_expect(main.call("_map_target_tile", map_camera, minimap_center) is Vector2i,
		"minimap camera ray resolves a server walking target")
	_expect(main.call("_map_target_tile", full_map_camera, full_map_center) is Vector2i,
		"Tab map camera ray resolves a server walking target")
	# Both maps draw marks in pixels so zoom and playable-area framing
	# cannot change their size.
	_expect((full_map_camera.cull_mask & 4) == 0
		and (map_camera.cull_mask & 4) == 0,
		"both map cameras exclude the modelled marker layer")
	var marker_material: StandardMaterial3D = player_marker.material_override as StandardMaterial3D
	if marker_material == null and player_marker.mesh != null:
		marker_material = player_marker.mesh.material as StandardMaterial3D
	_expect(marker_material != null and marker_material.albedo_color == Color.WHITE,
		"local-player map marker is white")
	_expect(marker_material != null and marker_material.no_depth_test,
		"local-player map marker remains visible above map geometry")
	var marker_mesh: CylinderMesh = player_marker.mesh as CylinderMesh
	_expect(marker_mesh != null and marker_mesh.top_radius >= 5.0,
		"local-player white dot remains legible on the full-map scale")
	var pick_result: int = int(main.call("_pick_actor", Vector2(640.0, 360.0)))
	_expect(pick_result >= -1, "world click actor ray executes against a non-null World3D")
	_expect(WorldLoader.NAVIGATION_SURFACE_LAYER != WorldLoader.WORLD_COLLISION_LAYER,
		"actor grounding is isolated from structural collision")
	var full_map_panel: Control = main.get_node("GameView/FullMap") as Control
	_expect(not full_map_panel.visible, "Tab map starts closed")
	main.call("_on_map_button_pressed")
	_expect(full_map_panel.visible, "Tab map control opens the populated map viewport")
	var displayed_map_center: Variant = main.call("_texture_to_viewport_position",
		full_map_image.size * 0.5, full_map_image, full_map_viewport.size)
	_expect(displayed_map_center is Vector2 and (displayed_map_center as Vector2).is_equal_approx(
		Vector2(full_map_viewport.size) * 0.5),
		"full-map hover mapping accounts for keep-aspect centering")
	if full_map_image.size.x > full_map_image.size.y:
		_expect(main.call("_texture_to_viewport_position",
			Vector2(1.0, full_map_image.size.y * 0.5), full_map_image,
			full_map_viewport.size) == null,
			"full-map letterbox margins do not report false coordinates")
	_expect(InputMap.has_action("toggle_map")
		and main.get_node("GameView/FullMap/MapLayout/Sidebar/SidebarLayout/SidebarScroll/SidebarContent/ContinentButton") is TextureButton
		and main.get_node("GameView/FullMap/MapLayout/Sidebar/SidebarLayout/SidebarScroll/SidebarContent/MapLegend") is RichTextLabel
		and main.get_node("GameView/FullMap/MapLayout/Sidebar/SidebarLayout/MapCoordinates") is Label,
		"Tab map exposes continent navigation, a legend, and hover coordinates")
	var map_motion: InputEventMouseMotion = InputEventMouseMotion.new()
	map_motion.position = full_map_image.size * 0.5
	main.call("_on_full_map_gui_input", map_motion)
	_expect((main.get_node(
		"GameView/FullMap/MapLayout/Sidebar/SidebarLayout/MapCoordinates") as Label).text.contains(","),
		"map hover reports the same server tile used by click-to-walk")
	main.call("_on_map_button_pressed")
	var gameplay_camera: Camera3D = camera_rig.get_node("Camera") as Camera3D
	_expect(camera_rig.distance >= 24.0 and camera_rig.distance <= 28.0
		and camera_rig.pitch_degrees <= -58.0 and gameplay_camera.fov <= 52.0,
		"default camera keeps the actor readable from a steep isometric angle")
	var actor_height_fixture: ReplicatedActor3D = ReplicatedActor3D.new()
	root.add_child(actor_height_fixture)
	var imported_visual := Node3D.new()
	imported_visual.name = "NativeModel"
	actor_height_fixture.add_child(imported_visual)
	actor_height_fixture.call("_apply_import_adapter", {})
	_expect(is_equal_approx(absf(imported_visual.rotation.y), PI),
		"native visual forward is corrected from glTF +Z to Godot -Z")
	actor_height_fixture.server_target = Vector3(2.0, 31.15, 3.0)
	actor_height_fixture.global_position = actor_height_fixture.server_target
	actor_height_fixture.set_surface_height(42.08)
	_expect(is_equal_approx(actor_height_fixture.server_target.y, 42.08),
		"actor target follows sampled terrain height")
	_expect(is_equal_approx(actor_height_fixture.global_position.y, 42.08),
		"actor presentation snaps out of terrain")
	actor_height_fixture.actor_id = 77
	actor_height_fixture.apply_server_state({
		"x": 3, "y": 3, "rotation": 0, "command": 22}, CoordinateAdapter.new(), false)
	_expect(is_equal_approx(actor_height_fixture.server_target.y, 42.08),
		"movement packets preserve the rendered terrain sample")
	_expect(is_equal_approx(float(actor_height_fixture.get("_target_yaw")), -PI / 2.0),
		"actor faces the authoritative movement direction")
	_expect(float(actor_height_fixture.get("_presentation_speed")) >= 6.0,
		"walk presentation closes authoritative steps promptly")
	# A predicted turn holds the facing only until the server answers it.
	actor_height_fixture.predict_turn(PI / 4.0)
	var held_facing: float = actor_height_fixture.desired_facing_yaw()
	actor_height_fixture.apply_server_state({
		"x": 4, "y": 3, "rotation": 0, "command": 22}, CoordinateAdapter.new(), false)
	_expect(is_equal_approx(actor_height_fixture.desired_facing_yaw(), held_facing),
		"a predicted turn holds the facing until the server answers it")
	# CMD_TURN_E. The authoritative turn confirms the prediction and replaces
	# it, so a rejected or differently-resolved turn cannot stick locally.
	actor_height_fixture.apply_server_state({
		"x": 4, "y": 3, "rotation": 16384, "command": 40},
		CoordinateAdapter.new(), false)
	_expect(is_equal_approx(actor_height_fixture.desired_facing_yaw(), -PI / 2.0)
		and not bool(actor_height_fixture.get("_predicted_turn_pending")),
		"an authoritative turn command clears the local turn prediction")
	actor_height_fixture.apply_server_state({
		"x": 4, "y": 3, "rotation": 0, "command": 22}, CoordinateAdapter.new(), false)
	_expect(is_equal_approx(actor_height_fixture.desired_facing_yaw(), -PI / 2.0),
		"movement after a confirmed turn follows authoritative facing again")
	actor_height_fixture.predict_turn(PI / 4.0)
	actor_height_fixture.clear_turn_prediction()
	actor_height_fixture.apply_server_state({
		"x": 5, "y": 3, "rotation": 0, "command": 22}, CoordinateAdapter.new(), false)
	_expect(is_equal_approx(actor_height_fixture.desired_facing_yaw(), -PI / 2.0),
		"an abandoned turn prediction hands the facing back to the server")
	# Nothing but an unanswered turn holds a player off its own step. A route
	# whose steps leave the heading it was ordered from - a keyboard diagonal,
	# or a path that bends round an obstacle - turns the actor onto each step it
	# takes instead of leaving it pointed at the tile it was sent to. CMD_MOVE_NE.
	actor_height_fixture.apply_server_state({
		"x": 6, "y": 4, "rotation": 0, "command": 21}, CoordinateAdapter.new(), false)
	_expect(is_equal_approx(actor_height_fixture.desired_facing_yaw(),
			CoordinateAdapter.new().direction_to_godot(Vector2i(1, 1))),
		"a step off the ordered heading turns the actor onto the step")
	actor_height_fixture.free()
	# Main samples the ground under the tile a step is heading for, so the
	# height arrives while the step is still being walked. Writing it onto the
	# body as well as onto the target put the actor at the far tile's height
	# until the next physics tick recomputed the interpolation and pulled it
	# back - on terraced ground every creature crossing a terrace popped a
	# whole ledge-height and returned, over and over.
	var terrace_fixture: ReplicatedActor3D = ReplicatedActor3D.new()
	root.add_child(terrace_fixture)
	terrace_fixture.actor_id = 78
	terrace_fixture.server_target = Vector3(2.0, 20.0, 3.0)
	terrace_fixture.global_position = terrace_fixture.server_target
	terrace_fixture.set("_snap_pending", false)
	terrace_fixture.set("_segment_start", terrace_fixture.server_target)
	terrace_fixture.apply_server_state({
		"x": 3, "y": 3, "rotation": 0, "command": 22},
		CoordinateAdapter.new(), false)
	var step_duration: float = float(terrace_fixture.get("_segment_duration"))
	_expect(step_duration > 0.0, "a movement packet opens an interpolated step")
	terrace_fixture.set_surface_height(23.0)
	_expect(is_equal_approx(terrace_fixture.server_target.y, 23.0)
		and is_equal_approx(terrace_fixture.global_position.y, 20.0),
		"a ledge sampled mid-step moves the step's target, not the body")
	terrace_fixture.call("_physics_process", step_duration)
	_expect(is_equal_approx(terrace_fixture.global_position.y, 23.0),
		"the step still finishes on the height the ground was sampled at")
	# Nothing is interpolating a standing actor, so a correction that never
	# reached the body would leave it embedded in the ground it was measured
	# against.
	terrace_fixture.set_surface_height(26.0)
	_expect(is_equal_approx(terrace_fixture.global_position.y, 26.0),
		"a standing actor still snaps out of terrain")
	terrace_fixture.free()
	_check_travel_facing()
	_check_map_dot()
	_check_camera_relative_movement(main)
	var lower_hud: Control = main.get_node("GameView/Quickbar") as Control
	var chat_panel: Control = main.get_node("%ChatPanel") as Control
	var right_stats: Control = main.get_node("GameView/ResourceHud") as Control
	var right_quickbar: Control = main.get_node("GameView/ItemQuickbar") as Control
	var spell_quickbar: Control = main.get_node("GameView/SpellQuickbar") as Control
	var stats_panel: Control = main.get_node("GameView/StatsPanel") as Control
	var inventory_panel: Control = main.get_node("GameView/InventoryPanel") as Control
	var stats_tabs: TabContainer = main.get_node(
		"GameView/StatsPanel/Content/StatsTabs") as TabContainer
	var inventory_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/InventoryButton") as Button
	var walk_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/WalkButton") as Button
	var attack_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/AttackButton") as Button
	var trade_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/TradeButton") as Button
	var trade_panel: Control = main.get_node("GameView/TradePanel") as Control
	var app_state_inventory: Node = root.get_node("AppState")
	var chat_output: RichTextLabel = main.get_node("%ChatOutput") as RichTextLabel
	var chat_input: LineEdit = main.get_node("%ChatInput") as LineEdit
	_expect(chat_input.visible and not chat_input.has_focus(),
		"entering the world leaves the chat footer available without taking keyboard focus")
	app_state_inventory.call("_on_packet", 0,
		PackedByteArray([1, 128, 91, 80, 77, 32, 102, 114, 111, 109, 32, 65, 108,
			105, 99, 101, 58, 32, 104, 105, 93, 0]))
	main.call("_sync_chat")
	_expect(chat_output.get_parsed_text().contains("[Private] Alice: hi"),
		"private chat receives its personal-channel label")
	_expect(not chat_output.bbcode_enabled and chat_input.tooltip_text.contains("/name"),
		"chat remains markup-safe and exposes legacy addressing syntax")
	app_state_inventory.call("_on_packet", 71,
		PackedByteArray([1, 1, 0, 0, 0, 4, 0, 0, 0, 12, 0, 0, 0]))
	main.call("_sync_channel_tabs")
	var numeric_channel: Button = main.chat_hud.channel_buttons[4]
	_expect(numeric_channel.visible and numeric_channel.text == "#4",
		"server active channels appear as numeric chat tabs")
	main.call("_hide_chat_input")
	_expect(not chat_input.has_focus(), "Esc behavior can release chat entry focus")
	main.call("_show_chat_input")
	_expect(chat_input.visible and chat_input.has_focus(), "T behavior restores chat entry focus")
	main.call("_on_chat_submitted", "")
	_expect(chat_input.visible and not chat_input.has_focus(),
		"submitting an empty line releases focus and keeps the chat footer")
	main.call("_show_chat_input")
	chat_input.release_focus()
	_expect(chat_input.visible,
		"leaving chat focus keeps the inactive footer available")
	main.call("_show_chat_input")
	main.call("_reveal_chat_messages")
	_expect(chat_panel.visible, "the movable chat remains available until the player closes it")
	main.call("_on_chat_tab_pressed", "all")
	_expect(chat_panel.visible and is_equal_approx(chat_panel.modulate.a, 1.0),
		"chat tab selection shows messages at full opacity")
	_expect(lower_hud.anchor_bottom == 1.0 and lower_hud.anchor_right == 1.0,
		"lower HUD border spans the bottom edge")
	main.call("_sync_hud_button_states", true)
	# Colour now means "you can use this", not "this is open": walk mode is on
	# and the inventory is shut, yet both are available so both are drawn from
	# the coloured atlas. Which one is active is carried by the pressed state,
	# and the greyed atlas is kept for what the client will not let you do.
	_expect(walk_button.button_pressed and not inventory_button.button_pressed
		and (walk_button.icon as AtlasTexture).atlas ==
			(inventory_button.icon as AtlasTexture).atlas,
		"an available HUD action is coloured whether or not its window is open")
	_expect(attack_button.disabled
		and (attack_button.icon as AtlasTexture).atlas !=
			(walk_button.icon as AtlasTexture).atlas,
		"an unavailable HUD action is drawn from the greyed atlas")
	_expect(inventory_button.flat and inventory_button.focus_mode == Control.FOCUS_NONE,
		"bottom HUD icons have no individual box and cannot steal Tab focus")
	# Each icon is painted with its own frame out to the edge of its cell, so
	# without padding the frames touched and the end ones read as cut off.
	var icon_padding: float = float(main.get("HUD_ICON_PADDING"))
	var icon_box: StyleBox = inventory_button.get_theme_stylebox("normal")
	_expect(icon_padding > 0.0
		and is_equal_approx(icon_box.content_margin_left, icon_padding)
		and is_equal_approx(icon_box.content_margin_top, icon_padding)
		and is_equal_approx(inventory_button.custom_minimum_size.x,
			40.0 + icon_padding * 2.0)
		and inventory_button.vertical_icon_alignment == VERTICAL_ALIGNMENT_CENTER,
		"bottom HUD icons are padded off their neighbours and centred in their box")
	var chat_tabs: Control = main.get_node("%ChatTabs") as Control
	var chat_window: Control = main.get_node("%ChatWindow") as Control
	_expect(chat_window.get_global_rect().encloses(chat_tabs.get_global_rect())
		and chat_window.get_global_rect().encloses(chat_input.get_global_rect())
		and chat_window.get_global_rect().end.y <= lower_hud.global_position.y,
		"tabs, messages and input share one movable window above the lower rail")
	# One rail, two columns: spells down its left half and items down its
	# right, with the rail itself owning the only border so its left edge is a
	# single line rather than one per box.
	var right_rail: Panel = main.get_node("GameView/RightRail") as Panel
	var rail_children: Array[Control] = [right_stats, right_quickbar,
		spell_quickbar,
		main.get_node("GameView/EloriaLogoFrame") as Control,
		main.get_node("GameView/ClockFrame") as Control,
		main.get_node("GameView/CompassFrame") as Control]
	var strays := 0
	for railed: Control in rail_children:
		if railed.anchor_left != 1.0 or railed.anchor_right != 1.0:
			strays += 1
		elif railed.offset_left < right_rail.offset_left 				or railed.offset_right > right_rail.offset_right:
			strays += 1
		elif railed.get_theme_stylebox("panel") is not StyleBoxEmpty:
			strays += 1
	_expect(strays == 0 and right_rail.anchor_left == 1.0
		and right_rail.anchor_bottom == 1.0 and right_rail.offset_top == 0.0
		and right_rail.get_theme_stylebox("panel") is StyleBoxFlat,
		"the right rail is one bordered bar from the top of the client down"
			+ " and everything in it is drawn without a box of its own")
	# Offsets are only a request: a container whose contents need more room
	# grows past them, which is how the spell column ended up outside the rail
	# and the stats panel ended up under the clock. Assert the resolved rects.
	var rail_rect := Rect2(right_rail.global_position, right_rail.size)
	var stacked: Array[Control] = [
		main.get_node("GameView/EloriaLogoFrame") as Control, spell_quickbar,
		right_stats, main.get_node("GameView/ClockFrame") as Control,
		main.get_node("GameView/CompassFrame") as Control]
	var spilled := 0
	var collided := 0
	var previous_bottom: float = rail_rect.position.y
	for boxed: Control in stacked + [right_quickbar] as Array[Control]:
		var box := Rect2(boxed.global_position, boxed.size)
		if not rail_rect.encloses(box):
			spilled += 1
	for boxed: Control in stacked:
		if boxed.global_position.y < previous_bottom:
			collided += 1
		previous_bottom = boxed.global_position.y + boxed.size.y
	_expect(spilled == 0 and collided == 0,
		"the rail's contents all fit inside it and none sits on top of another")
	var spell_middle: float = (spell_quickbar.offset_left
		+ spell_quickbar.offset_right) * 0.5
	_expect(right_quickbar.offset_left >= spell_middle
		and right_quickbar.offset_right <= spell_quickbar.offset_right
		and spell_quickbar.offset_left <= spell_middle,
		"spells run down the left of the rail and items down its right")
	var item_slots: GridContainer = main.get_node("%ItemSlots") as GridContainer
	var spell_slots: GridContainer = main.get_node("%SpellSlots") as GridContainer
	_expect(item_slots.columns == 1 and spell_slots.columns == 1
		and item_slots.visible and spell_slots.visible,
		"both quick slot columns stay visible without a mode toggle")
	var clock_face: TextureRect = main.get_node("GameView/ClockFrame/ClockFace") as TextureRect
	var compass_face: TextureRect = main.get_node("GameView/CompassFrame/CompassFace") as TextureRect
	_expect(clock_face.texture != null and compass_face.texture != null,
		"legacy clock and compass use the existing Eloria HUD atlas")
	_expect(clock_face.gui_input.is_connected(Callable(main, "_on_clock_gui_input"))
		and compass_face.gui_input.is_connected(Callable(main, "_on_compass_gui_input"))
		and (main.get_node("%HudLogo") as TextureRect).texture != null,
		"clock, compass, and top-right Rabbit Lands crest are interactive/present")
	_expect(InputMap.has_action("toggle_console")
		and InputMap.has_action("toggle_inventory")
		and InputMap.has_action("recenter_viewport")
		and InputMap.has_action("move_north") and InputMap.has_action("move_south")
		and InputMap.has_action("move_west") and InputMap.has_action("move_east")
		and InputMap.has_action("turn_left") and InputMap.has_action("turn_right")
		and main.get_node("GameView/ConsolePanel/Content/ConsoleOutput") is RichTextLabel
		and chat_input.get_parent().get_parent().get_parent() == chat_window,
		"console, Ctrl+I inventory, WASD/QE/Space, and movable chat controls are available")
	_expect(main.call("_movement_axes_for_actions", true, false, false, false)
		== Vector2i(1, 0)
		and main.call("_movement_axes_for_actions", false, true, false, false)
		== Vector2i(-1, 0)
		and main.call("_movement_axes_for_actions", false, false, true, false)
		== Vector2i(0, -1)
		and main.call("_movement_axes_for_actions", false, false, false, true)
		== Vector2i(0, 1)
		and main.call("_movement_axes_for_actions", true, true, true, true)
		== Vector2i.ZERO,
		"W/S move forward/backward, A/D move left/right, and opposing keys cancel")
	# The chat entry above kept keyboard focus. Release it: bound printable keys
	# are deliberately inert while a text field is focused.
	main.call("_hide_chat_input")
	await process_frame
	# Every keyboard binding is resolved through the InputMap. Raw keycode
	# comparisons used to shadow toggle_inventory, turn_left and turn_right, so
	# rebinding them appeared to work and changed nothing. Rebinding an action
	# and pressing both the old and the new key is what proves that is gone.
	for rebindable: String in ["turn_left", "turn_right", "toggle_inventory",
			"toggle_map", "toggle_minimap", "toggle_console",
			"recenter_viewport", "connect", "disconnect"]:
		_expect(InputMap.has_action(rebindable)
			and InputMap.action_get_events(rebindable).size() > 0,
			"%s is a declared action with at least one real event" % rebindable)
	# Every binding also has to name a key this engine has. `toggle_map` held
	# ASCII 9 - Godot 3's tab - which matches nothing in 4.x, so Tab fell
	# through to the built-in ui_focus_next and walked the focus ring around
	# the HUD buttons instead of opening the map.
	for bound: String in ["turn_left", "turn_right", "toggle_inventory",
			"toggle_map", "toggle_minimap", "toggle_console",
			"recenter_viewport", "connect", "disconnect", "cancel"]:
		for bound_event: InputEvent in InputMap.action_get_events(bound):
			var bound_key: InputEventKey = bound_event as InputEventKey
			if bound_key == null:
				continue
			var code: int = bound_key.physical_keycode
			_expect(code != 0 and OS.find_keycode_from_string(
				OS.get_keycode_string(code)) == code,
				"%s is bound to a keycode this engine recognises" % bound)
	# Pressed from a focused HUD button, because that is where the focus ring
	# lived once the map stopped opening.
	var map_hud_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/MapButton") as Button
	var map_hud_focus: int = map_hud_button.focus_mode
	map_hud_button.focus_mode = Control.FOCUS_ALL
	map_hud_button.grab_focus()
	await process_frame
	var map_was_open: bool = full_map_panel.visible
	var tab_press: InputEventKey = (InputMap.action_get_events(
		"toggle_map")[0].duplicate() as InputEventKey)
	tab_press.pressed = true
	root.push_input(tab_press)
	await process_frame
	_expect(full_map_panel.visible != map_was_open
		and root.gui_get_focus_owner() == map_hud_button,
		"Tab opens the map instead of moving focus, even from a focused button")
	root.push_input(tab_press)
	await process_frame
	# Z is the technique ring's hold key: it opens the ring and moves no
	# focus either, and letting go closes it.
	var ring: Control = main.get("technique_ring") as Control
	# Rings stay shut over the map; close it whatever the map key did above.
	(main.get("full_map") as Control).hide()
	var ring_press: InputEventKey = (InputMap.action_get_events(
		"technique_ring")[0].duplicate() as InputEventKey)
	ring_press.pressed = true
	var focus_before: Control = root.gui_get_focus_owner()
	root.push_input(ring_press)
	await process_frame
	_expect(root.gui_get_focus_owner() == focus_before, "holding Z never moves focus")
	# Rings stay shut while a modal, the console or a text box is up; when
	# nothing blocks them, Z opens the technique ring.
	_expect(ring != null and (ring.visible or not bool(main.call("_ring_allowed"))),
		"holding Z opens the technique ring whenever rings are allowed")
	var ring_release := ring_press.duplicate() as InputEventKey
	ring_release.pressed = false
	root.push_input(ring_release)
	await process_frame
	_expect(ring != null and not ring.visible, "releasing Z closes the technique ring")
	map_hud_button.focus_mode = map_hud_focus as Control.FocusMode
	map_hud_button.release_focus()
	for rebindable: String in ["turn_left", "turn_right", "toggle_map",
			"toggle_minimap", "toggle_console"]:
		var defaults: Array[InputEvent] = InputMap.action_get_events(rebindable)
		var original_key: InputEventKey = defaults[0].duplicate() as InputEventKey
		original_key.pressed = true
		var moved := InputEventKey.new()
		moved.physical_keycode = KEY_F9
		moved.pressed = true
		InputMap.action_erase_events(rebindable)
		InputMap.action_add_event(rebindable, moved)
		_expect(not bool(main.call("_handle_bound_action", original_key)),
			"rebinding %s releases its previous key" % rebindable)
		_expect(bool(main.call("_handle_bound_action", moved)),
			"rebinding %s moves the behaviour onto the new key" % rebindable)
		InputMap.action_erase_events(rebindable)
		for restored: InputEvent in defaults:
			InputMap.action_add_event(rebindable, restored)
		_expect(bool(main.call("_handle_bound_action", original_key)),
			"restoring the %s binding restores its default key" % rebindable)
	# Both connection actions reach a handler. connect() is driven from the
	# already-connected branch so the assertion opens no socket.
	app_state_inventory.set("connection_state", "connected")
	var connect_key: InputEventKey = InputMap.action_get_events(
		"connect")[0].duplicate() as InputEventKey
	connect_key.pressed = true
	_expect(bool(main.call("_handle_bound_action", connect_key)),
		"the connect binding reaches a handler")
	var disconnect_key: InputEventKey = InputMap.action_get_events(
		"disconnect")[0].duplicate() as InputEventKey
	disconnect_key.pressed = true
	_expect(bool(main.call("_handle_bound_action", disconnect_key)),
		"the disconnect binding reaches a handler")
	app_state_inventory.set("connection_state", "disconnected")
	# A focused text field keeps its own characters and clipboard shortcuts.
	chat_input.show()
	chat_input.grab_focus()
	await process_frame
	var console_key: InputEventKey = InputMap.action_get_events(
		"toggle_console")[0].duplicate() as InputEventKey
	console_key.pressed = true
	_expect(not bool(main.call("_handle_bound_action", console_key)),
		"a bound printable key typed into chat does not also toggle a window")
	chat_input.release_focus()
	await process_frame
	# Four Eternal Lands-style tabs, and a fifth this client adds: the perks
	# the server offers, which Eternal Lands only ever sells through an NPC.
	_expect(stats_tabs.get_tab_count() == 5
		and stats_tabs.get_tab_title(0) == "Statistics"
		and stats_tabs.get_tab_title(1) == "Knowledge"
		and stats_tabs.get_tab_title(2) == "Counters"
		and stats_tabs.get_tab_title(3) == "Session"
		and stats_tabs.get_tab_title(4) == "Perks",
		"statistics frame provides the Eternal Lands tabs and the perks tab")
	_expect(main.get_node("GameView/StatsPanel/Content/Header/StatsClose") is Button
		and main.get_node("GameView/StatsPanel/Content/StatsTabs/Counters/CounterColumns/CounterCategories") is ItemList
		and main.get_node("GameView/StatsPanel/Content/StatsTabs/Session/SessionContent/SessionXpText") is RichTextLabel,
		"statistics has close, counters, session XP, and perks-ready content")
	for meter_path: String in [
		"GameView/Quickbar/QuickRows/BottomMeters/ManaMeter/EtherBottom",
		"GameView/Quickbar/QuickRows/BottomMeters/FoodMeter/FoodBottom",
		"GameView/Quickbar/QuickRows/BottomMeters/HealthMeter/HealthBottom",
		"GameView/Quickbar/QuickRows/BottomMeters/LoadMeter/LoadBottom",
		"GameView/Quickbar/QuickRows/BottomMeters/ActionMeter/ActionBottom",
		"GameView/Quickbar/QuickRows/BottomMeters/ExperienceMeter/ExperienceBottom"]:
		_expect(main.get_node_or_null(meter_path) is ProgressBar,
			"bottom HUD exposes %s" % meter_path.get_file())
	var actor_menu: Control = main.get("_actor_hud_menu") as Control
	main.call("_open_actor_hud_menu", Vector2(640.0, 360.0))
	var banner_menu_entries: Array[String] = ["ShowNames",
		"ShowHealthBar", "ShowHealthNumbers", "ShowEtherBar", "ShowEtherNumbers",
		"ShowFoodBar", "ShowFoodNumbers", "ShowActionBar", "ShowActionNumbers",
		"InstanceMode", "SpeechBubbles", "BannerBackground", "SitLock",
		"RangingLock", "DisableMenu"]
	var banner_menu_complete: bool = actor_menu.visible
	for entry_name: String in banner_menu_entries:
		if not (main.get_node_or_null(
				"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/" + entry_name) is CheckBox):
			banner_menu_complete = false
	_expect(banner_menu_complete,
		"banner context menu carries the Eternal Lands option set")
	app_state_inventory.set("stats", {"health": 72, "max_health": 100,
		"ether": 33, "max_ether": 50, "action_points": 18,
		"max_action_points": 30, "food": 42, "carried": 205, "capacity": 320,
		"attack": 24, "overall": 22, "harvesting": 8,
		"harvesting_base": 8, "harvesting_exp": 1480,
		"harvesting_exp_next": 2066})
	main.call("_sync_stats")
	var overhead_health_bar: ProgressBar = main.get_node(
		"GameView/ActorResourceOverlay/Rows/HealthRow/Bar") as ProgressBar
	var overhead_health_label: Label = main.get_node(
		"GameView/ActorResourceOverlay/Rows/HealthRow/Number") as Label
	var overhead_fill: StyleBoxFlat = overhead_health_bar.get_theme_stylebox("fill") as StyleBoxFlat
	var overhead_background: StyleBoxFlat = overhead_health_bar.get_theme_stylebox(
		"background") as StyleBoxFlat
	# 72/100 health sits in the green half of the EL ramp; the bar keeps only a
	# black frame so the world shows through whatever health is missing.
	_expect(overhead_fill != null and overhead_fill.bg_color.g > overhead_fill.bg_color.r
		and overhead_health_label.get_theme_color("font_color").g
			> overhead_health_label.get_theme_color("font_color").r
		and overhead_background != null and overhead_background.bg_color.a == 0.0,
		"overhead health bar follows the Eternal Lands drain colour")
	var drained: Color = main.call("_banner_colour", "health", 0.15)
	_expect(drained.r > drained.g,
		"the health ramp turns red as it empties")
	_expect(is_equal_approx((main.get_node(
		"GameView/Quickbar/QuickRows/BottomMeters/HealthMeter/HealthBottom") as ProgressBar).value, 72.0)
		and is_equal_approx((main.get_node(
		"GameView/Quickbar/QuickRows/BottomMeters/ManaMeter/EtherBottom") as ProgressBar).value, 33.0)
		and is_equal_approx((main.get_node(
		"GameView/Quickbar/QuickRows/BottomMeters/ActionMeter/ActionBottom") as ProgressBar).value, 18.0),
		"health, ethereality, and action-point meters synchronize live values")
	var floating_feedback: Array[Dictionary] = []
	app_state_inventory.floating_feedback_requested.connect(
		func(feedback: Dictionary) -> void: floating_feedback.append(feedback))
	app_state_inventory.call("_on_packet", 49, PackedByteArray([
		51, 0xd4, 0x05, 0, 0, 27, 9, 0, 0, 0]))
	_expect(floating_feedback.size() == 2
		and floating_feedback[0].kind == "experience"
		and int(floating_feedback[0].amount) == 12
		and floating_feedback[1].kind == "level",
		"partial experience and level updates request EL-style floating feedback")
	var ether_row: Control = main.get_node(
		"GameView/ActorResourceOverlay/Rows/EtherRow") as Control
	var ether_bar_box: CheckBox = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/ShowEtherBar") as CheckBox
	var ether_numbers_box: CheckBox = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/ShowEtherNumbers") as CheckBox
	var banner_overlay: Control = main.get_node("GameView/ActorResourceOverlay") as Control
	var full_banner_height: float = banner_overlay.size.y
	ether_bar_box.set_pressed_no_signal(false)
	main.call("_apply_banner_options")
	_expect(ether_row.visible
		and not (ether_row.get_node("Bar") as Control).visible
		and (ether_row.get_node("Number") as Control).visible,
		"the ether bar switch leaves the ether numbers behind")
	ether_numbers_box.set_pressed_no_signal(false)
	main.call("_apply_banner_options")
	_expect(not ether_row.visible and banner_overlay.size.y < full_banner_height,
		"a row that is fully switched off shrinks the banner")
	ether_bar_box.set_pressed_no_signal(true)
	ether_numbers_box.set_pressed_no_signal(true)
	main.call("_apply_banner_options")
	_expect(is_equal_approx(banner_overlay.size.y, full_banner_height),
		"restoring the row grows the banner back")
	var banner_background_box: CheckBox = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/BannerBackground") as CheckBox
	banner_background_box.set_pressed_no_signal(true)
	main.call("_apply_banner_options")
	var banner_panel: StyleBoxFlat = banner_overlay.get_theme_stylebox("panel") as StyleBoxFlat
	banner_background_box.set_pressed_no_signal(false)
	main.call("_apply_banner_options")
	_expect(banner_panel != null and banner_panel.bg_color.a > 0.0
		and banner_overlay.get_theme_stylebox("panel") is StyleBoxEmpty,
		"the banner background switch swaps the panel behind the banner")
	var disable_menu_box: CheckBox = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/DisableMenu") as CheckBox
	disable_menu_box.set_pressed_no_signal(true)
	main.call("_apply_banner_options")
	main.call("_close_settings")
	main.call("_open_actor_hud_menu", Vector2(640.0, 360.0))
	var stayed_closed: bool = not actor_menu.visible
	main.call("_on_banner_menu_enabled_toggled", true)
	main.call("_open_actor_hud_menu", Vector2(640.0, 360.0))
	_expect(stayed_closed and not disable_menu_box.button_pressed and actor_menu.visible,
		"Disable This Menu is honoured and reversible from HUD settings")
	actor_menu.hide()
	var sit_lock_box: CheckBox = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/SitLock") as CheckBox
	var ranging_lock_box: CheckBox = main.get_node(
		"GameView/SettingsLayer/SettingsWindow/SettingsBody/SettingsTabs/Banners/Banners/Options/RangingLock") as CheckBox
	var previous_actors: Dictionary = app_state_inventory.get("actors") as Dictionary
	var previous_local_id: int = int(app_state_inventory.get("local_actor_id"))
	app_state_inventory.set("local_actor_id", 91)
	app_state_inventory.set("actors", {91: {"actor_id": 91, "x": 10, "y": 20,
		"sitting": true, "appearance": {"weapon": 0}}})
	sit_lock_box.set_pressed_no_signal(true)
	var sit_locked: bool = bool(main.call("_movement_locked", false))
	var ctrl_overrides: bool = not bool(main.call("_movement_locked", true))
	sit_lock_box.set_pressed_no_signal(false)
	_expect(sit_locked and ctrl_overrides,
		"Sit Lock holds a seated character in place until Ctrl is held")
	ranging_lock_box.set_pressed_no_signal(true)
	var unarmed_free: bool = not bool(main.call("_movement_locked", false))
	# client_serv.h BOW_RECURVE, inside the ranged span Ranging Lock covers.
	app_state_inventory.set("actors", {91: {"actor_id": 91, "x": 10, "y": 20,
		"sitting": false, "appearance": {"weapon": 66}}})
	var bow_locked: bool = bool(main.call("_movement_locked", false))
	ranging_lock_box.set_pressed_no_signal(false)
	_expect(unarmed_free and bow_locked,
		"Ranging Lock only holds a character carrying a ranged weapon")
	app_state_inventory.set("actors", previous_actors)
	app_state_inventory.set("local_actor_id", previous_local_id)
	_expect(not stats_panel.visible, "statistics window starts closed")
	main.call("_on_stats_button_pressed")
	_expect(stats_panel.visible and not stats_panel.get_global_rect().intersects(
		right_stats.get_global_rect()),
		"statistics window opens without covering the fixed resource rail")
	_expect(stats_panel.z_index > (main.get_node("GameView/ActorResourceOverlay") as Control).z_index,
		"popup windows render above the player resource overlay")
	main.call("_on_stats_button_pressed")
	_expect(not inventory_panel.visible and not inventory_button.disabled,
		"real inventory window starts closed with its HUD action enabled")
	var inventory_hotkey := InputEventKey.new()
	inventory_hotkey.pressed = true
	inventory_hotkey.ctrl_pressed = true
	inventory_hotkey.physical_keycode = KEY_I
	main.call("_input", inventory_hotkey)
	_expect(inventory_panel.visible, "Ctrl+I opens inventory")
	main.call("_input", inventory_hotkey)
	_expect(not inventory_panel.visible, "Ctrl+I closes inventory")
	_expect(main.get_node("GameView/InventoryPanel/Content/Header/InventoryClose") is Button
		and main.get_node("GameView/InventoryPanel/Content/InventoryBody/SideActions/InventoryStoreAll") is Button
		and main.get_node("GameView/InventoryPanel/Content/InventoryBody/SideActions/InventoryGetAll") is Button
		and main.get_node("GameView/InventoryPanel/Content/InventoryBody/SideActions/InventoryDropAll") is Button
		and main.get_node("GameView/InventoryPanel/Content/InventoryBody/SideActions/InventoryMixAll") is Button
		and main.get_node("GameView/InventoryPanel/Content/InventoryBody/SideActions/InventoryItemLists") is Button
		and main.get_node("GameView/InventoryPanel/Content/InventoryFooter/InventoryResizeGrip") is Button,
		"inventory exposes close, all EL-style side actions, and a resize grip")
	main.call("_apply_inventory_scale", 0.75)
	_expect(is_equal_approx(inventory_panel.scale.x, 0.75)
		and is_equal_approx(inventory_panel.scale.y, 0.75),
		"inventory resizing uniformly scales boxes, icons, and text without changing aspect")
	main.call("_apply_inventory_scale", 1.0)
	# Command 226 enriches the inventory; it never replaces it. The two
	# fixtures below deliberately disagree about the quantity in slot 0, and
	# the tooltip has to keep the authoritative one.
	app_state_inventory.call("_on_packet", 19, PackedByteArray([
		1, 20, 0, 12, 0, 0, 0, 0, 4]))
	app_state_inventory.call("_on_packet", 226, _hex_bytes(
		"fa00000014000000500000000100001400990000000100000000"
		+ "53756e6c65616600466c6f7765727300"))
	var enriched_tooltip: String = str(main.call("_inventory_tooltip",
		app_state_inventory.get("inventory").get(0, {}), 0))
	_expect(enriched_tooltip.contains("Sunleaf")
		and enriched_tooltip.contains("Flowers")
		and enriched_tooltip.contains("1 EMU"),
		"the inventory tooltip names the item the server described: "
			+ enriched_tooltip)
	_expect(enriched_tooltip.contains("quantity 12")
		and not enriched_tooltip.contains("quantity 153"),
		"the enriched tooltip keeps the authoritative quantity, not the"
			+ " enrichment packet's: " + enriched_tooltip)
	app_state_inventory.call("_on_packet", 226, _hex_bytes(
		"fa000000140000005000000000 00".replace(" ", "")))
	_expect(str(main.call("_inventory_tooltip", app_state_inventory.get("inventory").get(0, {}), 0))
		.contains("Item image #20"),
		"without an enrichment entry the tooltip falls back to the image id")

	_expect((main.call("_parse_item_list", "1158:20\n189:1") as Array).size() == 2,
		"custom storage item lists parse image IDs and quantities")
	var inventory_body: HBoxContainer = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody") as HBoxContainer
	var equipment_column: VBoxContainer = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/EquipmentColumn") as VBoxContainer
	main.call("_on_equipment_side_selected", 1)
	_expect(equipment_column.get_index() == inventory_body.get_child_count() - 1,
		"settings can place equipment on the right side")
	main.call("_on_equipment_side_selected", 0)
	_expect(equipment_column.get_index() == 0,
		"settings can independently restore equipment to the left side")
	main.call("_on_bulk_option_selected", 0, "drop")
	_expect(bool(main.call("_inventory_slot_is_protected", 0, "drop"))
		and not bool(main.call("_inventory_slot_is_protected", 6, "drop")),
		"drop-all row and column protections are independently selectable")
	main.call("_on_bulk_option_selected", 0, "drop")
	_expect(attack_button.disabled, "attack action starts disabled without a selected target")
	_expect(not trade_button.disabled and not trade_panel.visible,
		"the trade icon is usable with nobody selected, and the trade window starts closed")
	var attackable_actor: Dictionary = {
		"actor_id": 77, "name": "Rat", "kind": 3, "health": 12,
		"max_health": 12, "alive": true}
	_expect(str(main.call("_model_for_actor", {
		"enhanced": true, "kind": 2, "actor_type": 1})).is_empty(),
		"enhanced NPC wire packets never select a luminous player model")
	_expect(str(main.call("_model_for_actor", {
		"enhanced": true, "kind": 1, "actor_type": 1})) == "luminous_male",
		"enhanced player wire packets retain the native luminous model")
	var invasion_models: Dictionary = {
		400: "river_otter", 401: "crown_antler_stag", 402: "desert_tortoise",
		403: "sunscale_drake", 404: "snow_hare", 405: "whitehorn_ice_ram",
		406: "crystal_polar_bear", 407: "ice_snow_leopard", 408: "crystal_carapace_beetle",
		409: "crystal_dire_wolf", 410: "cobalt_ibex", 411: "emerald_canopy_dragon",
		412: "golden_plains_horse", 413: "golden_bison", 414: "stormmane_lion",
		415: "fire_salamander", 416: "autumn_antler_stag", 417: "mossback_boar",
		418: "mossbound_hound", 419: "porcupine", 420: "leafwing_owl",
		421: "miretoad", 422: "emerald_canopy_dragon", 423: "emerald_canopy_dragon",
		424: "delta_mud_crab", 425: "miretoad", 426: "saltmarsh_crocodile",
		427: "saltmarsh_crocodile",
	}
	for actor_type_value: Variant in invasion_models:
		var invasion_actor_type: int = int(actor_type_value)
		var expected_model: String = str(invasion_models[actor_type_value])
		_expect(str(main.call("_model_for_actor", {
			"enhanced": true, "kind": 3,
			"actor_type": invasion_actor_type})) == expected_model,
			"invasion actor type %d resolves to native model %s" % [
				invasion_actor_type, expected_model])
	var lakeglass_model_id: String = str(main.call("_model_for_actor", {
		"enhanced": true, "kind": 3, "actor_type": 403}))
	var lakeglass_model_config: Dictionary = (main.get("models") as Dictionary).get(
		lakeglass_model_id, {}) as Dictionary
	var lakeglass_actor: ReplicatedActor3D = ReplicatedActor3D.new()
	main.add_child(lakeglass_actor)
	var lakeglass_errors: Array[String] = lakeglass_actor.configure({
		"actor_id": 4030, "x": 0, "y": 0, "rotation": 0,
		"actor_type": 403, "kind": 3, "name": "Lakeglass Drake",
	}, CoordinateAdapter.new({"walkingHeight": 0.0}), lakeglass_model_config,
		main.call("_animation_for_model", lakeglass_model_config) as Dictionary,
		main.get("equipment_config") as Dictionary)
	_expect(lakeglass_errors.is_empty()
		and lakeglass_actor.get_node_or_null("NativeModel") != null
		and lakeglass_actor.get_node_or_null("MissingModelFallback") == null,
		"Lakeglass Drake actor type 403 loads its animated native GLB without fallback")
	lakeglass_actor.queue_free()
	app_state_inventory.set("actors", {77: attackable_actor})
	app_state_inventory.set("selected_actor_id", 77)
	main.call("_sync_selection")
	_expect(not attack_button.disabled and attack_button.tooltip_text.contains("server"),
		"living creature selection enables the server-authoritative attack action")
	app_state_inventory.call("_on_packet", 47, PackedByteArray([77, 0, 5, 0]))
	var damaged_value: Variant = (app_state_inventory.get("actors") as Dictionary).get(77, {})
	var damaged_actor: Dictionary = damaged_value as Dictionary
	_expect(int(damaged_actor.get("health", -1)) == 7,
		"authoritative combat damage updates replicated actor health")
	app_state_inventory.call("_on_packet", 48, PackedByteArray([77, 0, 3, 0]))
	var healed_value: Variant = (app_state_inventory.get("actors") as Dictionary).get(77, {})
	var healed_actor: Dictionary = healed_value as Dictionary
	_expect(int(healed_actor.get("health", -1)) == 10,
		"authoritative combat heal updates replicated actor health")
	attackable_actor["alive"] = false
	attackable_actor["health"] = 0
	app_state_inventory.set("actors", {77: attackable_actor})
	main.call("_sync_selection")
	_expect(attack_button.disabled, "dead target disables the attack action")
	_check_actor_click_actions(main)
	var tradeable_actor: Dictionary = {
		"actor_id": 88, "name": "Alice", "kind": 1, "health": 20,
		"max_health": 20, "alive": true}
	app_state_inventory.set("actors", {88: tradeable_actor})
	app_state_inventory.set("selected_actor_id", 88)
	main.call("_sync_selection")
	_expect(not trade_button.disabled and trade_button.tooltip_text.contains("four tiles"),
		"living player selection enables the real trade request")
	app_state_inventory.call("_on_packet", 41,
		PackedByteArray([1, 65, 108, 105, 99, 101, 0]))
	app_state_inventory.call("_on_packet", 40,
		PackedByteArray([1, 3, 0, 9, 0, 0, 0, 7, 12]))
	app_state_inventory.call("_on_packet", 35,
		PackedByteArray([3, 0, 4, 0, 0, 0, 1, 2, 0]))
	app_state_inventory.call("_on_packet", 35,
		PackedByteArray([3, 0, 2, 0, 0, 0, 1, 2, 0]))
	app_state_inventory.call("_on_packet", 35,
		PackedByteArray([3, 0, 1, 0, 0, 0, 1, 2, 1]))
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0, 1]))
	app_state_inventory.call("_on_packet", 36, PackedByteArray([1, 1]))
	main.call("_sync_trade")
	var trade_state: Dictionary = app_state_inventory.get("trade") as Dictionary
	var own_offers: Dictionary = trade_state.get("own_offers", {}) as Dictionary
	var accumulated_offer: Dictionary = own_offers.get(2, {}) as Dictionary
	_expect(trade_panel.visible and str(trade_state.get("partner", "")) == "Alice",
		"server partner and trade inventory open the real trade window")
	_expect(root.get_visible_rect().encloses(trade_panel.get_global_rect()),
		"trade window fits the reference viewport")
	var trade_source: ItemList = main.get_node(
		"GameView/TradePanel/Content/Columns/Source/TradeSource") as ItemList
	var trade_own_list: ItemList = main.get_node(
		"GameView/TradePanel/Content/Columns/Own/TradeOwnOffers") as ItemList
	var trade_other_list: ItemList = main.get_node(
		"GameView/TradePanel/Content/Columns/Other/TradeOtherOffers") as ItemList
	var trade_accept_button: Button = main.get_node(
		"GameView/TradePanel/Content/Actions/TradeAccept") as Button
	var trade_storage_destination: CheckBox = main.get_node(
		"GameView/TradePanel/Content/QuantityRow/TradeStorageDestination") as CheckBox
	_expect(trade_source.item_count == 1 and trade_own_list.item_count == 1
		and trade_other_list.item_count == 1,
		"trade source and own-offer columns render authoritative items")
	_expect(not trade_accept_button.disabled and trade_accept_button.text.contains("Confirm"),
		"mutual first acceptance enables the explicit confirmation phase")
	trade_other_list.select(0)
	main.call("_on_trade_other_selected", 0)
	main.call("_on_trade_storage_destination_toggled", true)
	var trade_destinations: PackedByteArray = main.get("trade_destinations") as PackedByteArray
	_expect(not trade_storage_destination.disabled and int(trade_destinations[2]) == 2,
		"storage-adjacent trade records a per-offer storage destination")
	_expect(int(accumulated_offer.get("quantity", 0)) == 6,
		"incremental trade offers accumulate in their authoritative slot")
	_expect(int(trade_state.get("own_accepts", 0)) == 1
		and int(trade_state.get("other_accepts", 0)) == 1,
		"two-sided trade acceptance state is tracked independently")
	app_state_inventory.call("_on_packet", 39, PackedByteArray([5, 0, 0, 0, 2, 0]))
	trade_state = app_state_inventory.get("trade") as Dictionary
	own_offers = trade_state.get("own_offers", {}) as Dictionary
	accumulated_offer = own_offers.get(2, {}) as Dictionary
	_expect(int(accumulated_offer.get("quantity", 0)) == 1,
		"partial offer removal preserves the remaining quantity")
	# The acceptance phase is read off the wire, not counted. A duplicate accept
	# must not advance the state machine, and a reordered pair must leave the
	# client agreeing with the last phase the server actually reported.
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0, 1]))
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0, 1]))
	_expect(int((app_state_inventory.get("trade") as Dictionary).get("own_accepts", -1)) == 1,
		"a duplicated accept packet does not advance the acceptance phase")
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0, 2]))
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0, 1]))
	_expect(int((app_state_inventory.get("trade") as Dictionary).get("own_accepts", -1)) == 1,
		"an out-of-order accept leaves the client on the phase the server last reported")
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0, 2]))
	_expect(int((app_state_inventory.get("trade") as Dictionary).get("own_accepts", -1)) == 2,
		"the second acceptance phase is taken from the packet")
	app_state_inventory.call("_on_packet", 37, PackedByteArray([0]))
	_expect(int((app_state_inventory.get("trade") as Dictionary).get("own_accepts", -1)) == 0,
		"trade rejection resets the correct acceptance side")
	app_state_inventory.call("_on_packet", 38, PackedByteArray())
	main.call("_sync_trade")
	_expect(not trade_panel.visible
		and not bool((app_state_inventory.get("trade") as Dictionary).get("open", true)),
		"trade exit clears offers and closes the window")
	app_state_inventory.call("_on_packet", 67,
		PackedByteArray([1, 4, 70, 108, 111, 119, 101, 114, 115, 0]))
	app_state_inventory.call("_on_packet", 68,
		PackedByteArray([0, 4, 3, 0, 5, 0, 0, 0, 2, 0]))
	app_state_inventory.call("_on_packet", 69,
		PackedByteArray([132, 83, 116, 111, 114, 101, 100, 32, 115, 97, 102, 101, 108, 121, 0]))
	main.call("_sync_storage")
	var storage_panel: Control = main.get_node("GameView/StoragePanel") as Control
	# The classic storage workspace moves these controls out of the panel's
	# original layout, so they are read from main rather than by node path.
	var storage_categories: ItemList = main.get("storage_categories") as ItemList
	var storage_items: ItemList = main.get("storage_items") as ItemList
	var storage_status: Label = main.get("storage_status") as Label
	_expect(storage_panel.visible and root.get_visible_rect().encloses(
		storage_panel.get_global_rect()), "server storage opens within the reference viewport")
	_expect(storage_categories.item_count == 1 and storage_items.item_count == 1
		and storage_status.text == "Stored safely",
		"storage categories, items, and inspection text render from server state")
	app_state_inventory.call("_on_packet", 68,
		PackedByteArray([255, 4, 3, 0, 7, 0, 0, 0, 2, 0]))
	var storage_state: Dictionary = app_state_inventory.get("storage") as Dictionary
	var stored_items: Dictionary = storage_state.get("items", {}) as Dictionary
	_expect(int((stored_items.get(2, {}) as Dictionary).get("quantity", 0)) == 7,
		"incremental storage updates replace the authoritative position")
	app_state_inventory.call("close_storage")
	main.call("_sync_storage")
	_expect(not storage_panel.visible, "storage close clears its local session window")
	var knowledge_panel: Control = main.get_node("GameView/StatsPanel") as Control
	var knowledge_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/KnowledgeButton") as Button
	_expect(not knowledge_panel.visible and not knowledge_button.disabled,
		"knowledge window starts closed with its real HUD action enabled")
	app_state_inventory.call("_on_packet", 55, PackedByteArray([0x09]))
	main.call("_on_knowledge_button_pressed")
	var knowledge_list: ItemList = main.get_node(
		"GameView/StatsPanel/Content/StatsTabs/Knowledge/KnowledgeContent/Columns/KnowledgeList") as ItemList
	# The catalog is compiled from the profile this server runs: sixteen books,
	# the one it started with and the fifteen the crafting ladder gates its
	# higher tiers behind. It used to be compiled from the unmodified Eternal
	# Lands data the fork was built on, and listed 385 the server has never
	# heard of.
	_expect(knowledge_panel.visible and knowledge_list.item_count == 16
		and (main.get_node("GameView/StatsPanel/Content/StatsTabs") as TabContainer).current_tab == 1
		and root.get_visible_rect().encloses(knowledge_panel.get_global_rect()),
		"knowledge tab opens the served catalog within the statistics frame: %d"
			% knowledge_list.item_count)
	app_state_inventory.call("select_knowledge", 0)
	app_state_inventory.call("_on_packet", 57,
		PackedByteArray([77, 101, 116, 97, 108, 108, 117, 114, 103, 121, 0]))
	main.call("_sync_knowledge")
	var knowledge_detail: RichTextLabel = main.get_node(
		"GameView/StatsPanel/Content/StatsTabs/Knowledge/KnowledgeContent/Columns/KnowledgeDetail") as RichTextLabel
	_expect(knowledge_detail.text.contains("Metallurgy")
		and knowledge_detail.text.contains("Status: Read"),
		"selected knowledge renders server text and owned status")
	app_state_inventory.call("_on_packet", 56, PackedByteArray([2, 0]))
	var known_knowledge: Array = app_state_inventory.get("known_knowledge") as Array
	_expect(known_knowledge.has(2), "incremental knowledge acquisition updates ownership")
	main.call("_on_knowledge_close_pressed")
	var manufacturing_panel: Control = main.get_node("GameView/ManufacturingPanel") as Control
	var manufacturing_button: Button = main.get_node(
		"GameView/Quickbar/QuickRows/Buttons/ManufacturingButton") as Button
	_expect(not manufacturing_panel.visible and not manufacturing_button.disabled,
		"manufacturing window starts closed with its real HUD action enabled")
	# Recipe 0 on this profile is a Torch: two reagents held with a tool, which
	# is checked but never consumed. Stocked from the catalog rather than from
	# image ids written out here - the server renumbered 43 of them once, and
	# every fixture that spelled them out went on passing against artwork
	# nobody used. The slots are named too, as the server names them.
	var torch: Dictionary = (main.get("manufacturing_catalog")
		as ManufacturingCatalog).recipe(0)
	var torch_inventory: Dictionary = {}
	var torch_names: Dictionary = {}
	for group: String in ["ingredients", "tools"]:
		for entry_value: Variant in torch.get(group, []) as Array:
			var entry: Dictionary = entry_value as Dictionary
			var slot: int = 4 + torch_inventory.size()
			torch_inventory[slot] = {
				"image_id": int(entry.get("imageId", -1)),
				"quantity": maxi(1, int(entry.get("quantity", 1))),
				"slot": slot, "flags": 6}
			torch_names[slot] = str(entry.get("name", ""))
	app_state_inventory.set("inventory", torch_inventory)
	app_state_inventory.set("inventory_names", torch_names)
	app_state_inventory.set("stats", {"food": 45, "ether": 0})
	main.call("_on_manufacturing_button_pressed")
	var manufacturing_list: ItemList = main.get_node(
		"GameView/ManufacturingPanel/Content/Columns/ManufacturingList") as ItemList
	var manufacturing_detail: RichTextLabel = main.get_node(
		"%ManufacturingDetail") as RichTextLabel
	var manufacturing_mix_one: Button = main.get_node(
		"%ManufacturingMixOne") as Button
	var ready_only: CheckButton = main.get("manufacturing_ready_only") as CheckButton
	_expect(ready_only.button_pressed and manufacturing_list.item_count > 0
		and manufacturing_list.item_count < (main.get("manufacturing_catalog") as ManufacturingCatalog).count(),
		"mixing starts with only currently available recipes")
	ready_only.button_pressed = false
	_expect(manufacturing_panel.visible and manufacturing_list.item_count == (main.get("manufacturing_catalog") as ManufacturingCatalog).count()
		and root.get_visible_rect().encloses(manufacturing_panel.get_global_rect()),
		"the served recipe catalog opens within the reference viewport: %d"
			% manufacturing_list.item_count)
	main.call("_on_manufacturing_selected", 0)
	_expect(not manufacturing_mix_one.disabled
		and manufacturing_detail.text.contains("Torch")
		and manufacturing_detail.text.contains("%s ×%d" % [
			str((torch.get("ingredients", []) as Array)[0].get("name", "")),
			int((torch.get("ingredients", []) as Array)[0].get("quantity", 0))]),
		"available recipe resolves ingredients and enables the real server"
			+ " action: " + manufacturing_detail.text)
	app_state_inventory.set("inventory", {})
	app_state_inventory.set("inventory_names", {})
	main.call("_sync_manufacturing")
	_expect(manufacturing_mix_one.disabled
		and manufacturing_detail.text.contains("Missing Wood Plank ×1"),
		"inventory reconciliation disables a recipe with explicit missing"
			+ " ingredients: " + manufacturing_detail.text)
	# The tabs are however many mixing skills the served recipes mention, plus
	# an All that is not a skill. A local table here would be drawing last
	# week's window the day a profile adds a skill.
	var manufacturing_tabs: HBoxContainer = main.get_node(
		"GameView/ManufacturingPanel/Content/ManufacturingTabs") as HBoxContainer
	_expect(manufacturing_tabs.get_child_count() == 8,
		"a tab for All and one per mixing skill the profile serves: %d"
			% manufacturing_tabs.get_child_count())
	# A tab carries the same picture the encyclopedia shelves that skill
	# under, so the two windows cannot end up naming it differently.
	var tailoring_tab: Button = manufacturing_tabs.get_node_or_null(
		"TabTailoring") as Button
	_expect(tailoring_tab != null and tailoring_tab.icon != null
		and tailoring_tab.icon == SubjectIcons.icon_for("tailoring"),
		"a skill tab draws the shared subject icon for its skill")
	# All is not a skill, so it asks the sheet for "everything" rather than
	# for a skill that does not exist.
	_expect((manufacturing_tabs.get_node("TabAll") as Button).icon
			== SubjectIcons.icon_for("all"),
		"the All tab draws the sheet's own picture for everything")
	main.set("manufacturing_skill", "tailoring")
	main.call("_sync_manufacturing")
	_expect(manufacturing_list.item_count == 188,
		"a skill tab narrows the list to that skill: %d"
			% manufacturing_list.item_count)
	main.set("manufacturing_skill", "")
	# Searching finds what a tool is for, not only the tool.
	var manufacturing_filter: LineEdit = main.get("manufacturing_filter") as LineEdit
	manufacturing_filter.text = "hatchet"
	main.call("_sync_manufacturing")
	_expect(manufacturing_list.item_count == 24,
		"the search box matches tools as well as results and ingredients: %d"
			% manufacturing_list.item_count)
	manufacturing_filter.text = ""
	main.call("_sync_manufacturing")
	main.call("_on_manufacturing_selected", 0)

	# The quantity box is typed into as well as stepped, so it holds digits
	# and nothing else, and never leaves the range the server would refuse.
	var manufacturing_quantity: LineEdit = main.get(
		"manufacturing_quantity") as LineEdit
	manufacturing_quantity.text = "12x"
	main.call("_on_manufacturing_quantity_changed", "12x")
	_expect(manufacturing_quantity.text == "12",
		"the quantity box keeps the digits and drops the rest: "
			+ manufacturing_quantity.text)
	main.call("_set_manufacturing_quantity", 0)
	_expect(manufacturing_quantity.text == "1",
		"the quantity box will not go below one")
	main.call("_set_manufacturing_quantity", 99999)
	_expect(manufacturing_quantity.text == "1000",
		"the quantity box stops at the cap: " + manufacturing_quantity.text)

	# Mixing from storage, and fetching a worn-out tool out of it, are both the
	# server's to allow: how far away a storage keeper is, is a distance to an
	# actor this client is never told the role of.
	var manufacturing_source: CheckButton = main.get(
		"manufacturing_source") as CheckButton
	var manufacturing_tools: VBoxContainer = main.get(
		"manufacturing_tool_rows") as VBoxContainer
	_expect(manufacturing_source.disabled,
		"mixing from storage waits to be told storage is in reach")
	_expect(manufacturing_tools.get_node_or_null("ToolHatchet/Take") != null,
		"a missing tool offers to be fetched")
	_expect((manufacturing_tools.get_node("ToolHatchet/Take") as Button).disabled,
		"and the offer is refused away from storage")
	app_state_inventory.set("mix_state", {"served": true, "near_storage": true,
		"running": false, "remaining": 0, "made": 0, "output": ""})
	main.call("_sync_manufacturing")
	_expect(not manufacturing_source.disabled
		and not (manufacturing_tools.get_node("ToolHatchet/Take") as Button).disabled,
		"the server saying storage is near enables both")
	manufacturing_source.button_pressed = true
	app_state_inventory.set("mix_state", {"served": true, "near_storage": false,
		"running": false, "remaining": 0, "made": 0, "output": ""})
	main.call("_sync_manufacturing")
	_expect(manufacturing_source.disabled and not manufacturing_source.button_pressed,
		"walking away from storage stops the window pointing at a box it"
			+ " can no longer reach")

	# The queue is worked from the top, one batch at a time, and each batch is
	# credited with what the server says came out of it.
	main.set("selected_manufacturing_recipe", 0)
	main.call("_set_manufacturing_quantity", 3)
	main.call("_enqueue_selected")
	main.call("_enqueue_selected")
	main.set("manufacturing_queue_running", true)
	main.set("manufacturing_queue_index", 0)
	main.call("_settle_mix_run", {"output": "Torch", "entry": 0}, 3)
	var manufacturing_queue: Array = main.get("manufacturing_queue") as Array
	_expect(manufacturing_queue.size() == 2
		and int((manufacturing_queue[0] as Dictionary).get("made", 0)) == 3
		and int(main.get("manufacturing_queue_index")) == 1,
		"a finished batch is credited to its entry and the queue moves on")
	# Mix Now cuts a queued batch short. That is not the same as running out,
	# so the entry keeps its place and is asked for again.
	main.set("manufacturing_queue_index", 0)
	(manufacturing_queue[0] as Dictionary)["made"] = 0
	(main.get("_mix_pending") as Array).append({"output": "Torch", "entry": -1})
	main.call("_settle_mix_run", {"output": "Torch", "entry": 0}, 1)
	_expect(int(main.get("manufacturing_queue_index")) == 0
		and int((manufacturing_queue[0] as Dictionary).get("made", 0)) == 1,
		"a batch cut short by Mix Now keeps its place, crediting what it made")
	(main.get("_mix_pending") as Array).clear()
	main.call("_on_manufacturing_queue_clear_pressed")
	_expect((main.get("manufacturing_queue") as Array).is_empty()
		and not bool(main.get("manufacturing_queue_running")),
		"clearing the queue stops it")

	main.call("_on_manufacturing_close_pressed")
	app_state_inventory.call("_on_packet", 28,
		PackedByteArray([1, 10, 0, 20, 0, 7]))
	app_state_inventory.set("local_actor_id", 77)
	app_state_inventory.set("actors", {77: {"actor_id": 77, "x": 10, "y": 20}})
	_expect(int(main.call("_ground_bag_below_player")) == 7,
		"Get All resolves only the ground bag on the player's exact tile")
	app_state_inventory.set("actors", {77: {"actor_id": 77, "x": 10, "y": 21}})
	_expect(int(main.call("_ground_bag_below_player")) == -1,
		"Get All does not take items from a nearby but non-overlapping bag")
	app_state_inventory.set("actors", {77: {"actor_id": 77, "x": 10, "y": 20}})
	main.call("_sync_ground_bags")
	var ground_bag_nodes: Dictionary = main.get("ground_bag_nodes") as Dictionary
	_expect(ground_bag_nodes.has(7) and ground_bag_nodes.get(7) is GroundBag3D,
		"server bag snapshot creates a pickable world marker")
	var bag_node: GroundBag3D = ground_bag_nodes.get(7) as GroundBag3D
	_expect(bag_node.collision_layer == GroundBag3D.PICK_LAYER
		and bag_node.server_tile == Vector2i(10, 20),
		"ground bag marker preserves its authoritative tile and pick layer")
	var bag_map_camera: Camera3D = main.get_node("GameView/MapViewport/MapCamera")
	var bag_tab_camera: Camera3D = main.get_node("GameView/FullMapViewport/FullMapCamera")
	var bag_world_camera: Camera3D = main.get_node("GameView/ViewportContainer/Viewport/WorldRoot/CameraRig/Camera")
	for mesh: MeshInstance3D in bag_node.find_children("*", "MeshInstance3D", true, false):
		_expect((mesh.layers & bag_map_camera.cull_mask) == 0
			and (mesh.layers & bag_tab_camera.cull_mask) == 0
			and (mesh.layers & bag_world_camera.cull_mask) != 0,
			"bags remain visible in the world and are excluded from both map cameras")
	var bag_map_marks: Array = main.call("_collect_minimap_marks")
	_expect(bag_map_marks.all(func(mark: Dictionary) -> bool: return mark.get("type") != &"bag"),
		"the shared minimap and Tab map overlay contains no bag markers")
	_expect(not (main.get("MINIMAP_MARKER_TYPES") as Array).has(&"bag"),
		"the minimap menu cannot re-enable bag markers")
	app_state_inventory.call("begin_ground_bag_inspection", 7)
	app_state_inventory.call("_on_packet", 23,
		PackedByteArray([1, 3, 0, 5, 0, 0, 0, 2]))
	main.call("_sync_ground_bag")
	var ground_bag_panel: Control = main.get_node("GameView/GroundBagPanel") as Control
	var ground_bag_slots: Array = main.get("ground_bag_slot_buttons") as Array
	var filled_bag_slots: int = 0
	for raw_slot_button: Variant in ground_bag_slots:
		if int((raw_slot_button as Button).get_meta("bag_position", -1)) >= 0:
			filled_bag_slots += 1
	var bag_inventory_panel: Control = main.get_node("GameView/InventoryPanel") as Control
	_expect(ground_bag_panel.visible and filled_bag_slots == 1
		and bag_inventory_panel.visible
		and not ground_bag_panel.get_global_rect().intersects(
			bag_inventory_panel.get_global_rect())
		and root.get_visible_rect().encloses(ground_bag_panel.get_global_rect())
		and root.get_visible_rect().encloses(bag_inventory_panel.get_global_rect()),
		"the bag opens beside the inventory, both inside the reference viewport")
	# Asking what is on the ground. The bag slot carries an image id and a
	# quantity, so a right click is the only way to learn what it is.
	_expect(int((ground_bag_slots[0] as Button).get_meta("bag_position", -1)) == 2
		and not (ground_bag_slots[0] as Button).disabled
		and int((ground_bag_slots[1] as Button).get_meta("bag_position", -1)) == -1
		and (ground_bag_slots[1] as Button).disabled,
		"filled bag slots carry their authoritative position and empty ones stay inert")
	_expect(int(main.call("_ground_bag_slot_position", 0)) == 2
		and int(main.call("_ground_bag_slot_position", 1)) == -1
		and int(main.call("_ground_bag_slot_position", 99)) == -1,
		"the ground Look target resolves only for a filled slot")
	app_state_inventory.call("_on_packet", 24,
		PackedByteArray([4, 0, 9, 0, 0, 0, 5]))
	var ground_bag_state: Dictionary = app_state_inventory.get("ground_bag") as Dictionary
	var ground_items_state: Dictionary = ground_bag_state.get("items", {}) as Dictionary
	_expect(ground_items_state.size() == 2
		and int((ground_items_state.get(5, {}) as Dictionary).get("quantity", 0)) == 9,
		"incremental ground item updates the open bag")
	app_state_inventory.call("_on_packet", 25, PackedByteArray([2]))
	ground_bag_state = app_state_inventory.get("ground_bag") as Dictionary
	ground_items_state = ground_bag_state.get("items", {}) as Dictionary
	_expect(not ground_items_state.has(2),
		"ground item removal clears the authoritative slot")
	app_state_inventory.call("_on_packet", 29, PackedByteArray([7]))
	main.call("_sync_ground_bags")
	main.call("_sync_ground_bag")
	_expect(not (app_state_inventory.get("ground_bags") as Dictionary).has(7)
		and not bool((app_state_inventory.get("ground_bag") as Dictionary).get("open", true)),
		"destroyed bag removes its world marker and closes its matching window")
	app_state_inventory.set("actors", {})
	app_state_inventory.set("selected_actor_id", -1)
	inventory_panel.hide()
	main.call("_on_inventory_button_pressed")
	_expect(inventory_panel.visible and not stats_panel.visible,
		"inventory action opens the window and centrally closes statistics")
	app_state_inventory.set("inventory", {0: {
		"image_id": 3, "quantity": 9, "slot": 0, "flags": 12,
		"inventory_usable": true, "stackable": true}, 36: {
		"image_id": 8, "quantity": 1, "slot": 36, "flags": 0,
		"inventory_usable": false, "stackable": false}})
	main.call("_sync_inventory")
	var first_inventory_slot: Button = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/BackpackColumn/Scroll/InventoryGrid").get_child(0) as Button
	var first_quick_slot: Button = main.get_node(
		"GameView/ItemQuickbar/ItemSlots/Slot1") as Button
	var first_equipment_slot: Button = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/EquipmentColumn/EquipmentGrid").get_child(0) as Button
	var first_quantity: Label = first_inventory_slot.get_node("Quantity") as Label
	_expect(first_inventory_slot.text.is_empty() and first_quantity.text == "9"
		and first_quantity.anchor_top == 1.0 and first_quantity.anchor_bottom == 1.0
		and first_quantity.horizontal_alignment == HORIZONTAL_ALIGNMENT_RIGHT
		and first_inventory_slot.icon != null and not first_inventory_slot.disabled
		and first_inventory_slot.custom_minimum_size.x >= 40.0,
		"large inventory icon uses an overlaid bottom-right quantity")
	# The count runs the width of the slot and steps down in size, so seven
	# digits are read whole rather than cut off part way through the number.
	_expect(first_quantity.anchor_left == 0.0 and first_quantity.anchor_right == 1.0,
		"the count has the whole width of the slot to be read in")
	_expect(first_quick_slot.text.is_empty() and first_quick_slot.icon != null
		and first_quick_slot.tooltip_text.contains("Quantity: 9")
		and not first_quick_slot.disabled,
		"usable inventory slot populates the icon-only vertical quick slot")
	_expect(first_equipment_slot.text.is_empty() and first_equipment_slot.icon != null
		and not first_equipment_slot.disabled
		and first_equipment_slot.custom_minimum_size.x >= 40.0,
		"large equipment icon renders without a slot or quantity number")
	main.set("selected_inventory_slot", 0)
	main.call("_sync_inventory")
	var empty_inventory_slot: Button = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/BackpackColumn/Scroll/InventoryGrid").get_child(1) as Button
	var empty_equipment_slot: Button = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/EquipmentColumn/EquipmentGrid").get_child(1) as Button
	# A selection is not a carry: as in the reference client, only an item
	# in hand goes anywhere, so an empty slot promises nothing for it.
	_expect(not empty_inventory_slot.disabled
		and empty_inventory_slot.tooltip_text.contains("Empty inventory slot"),
		"a selected backpack item does not make an empty slot a move target")
	_expect(not empty_equipment_slot.disabled
		and empty_equipment_slot.tooltip_text.contains("Empty generic"),
		"nor an empty wear slot an equip target")
	main.set("selected_inventory_slot", 36)
	main.call("_sync_inventory")
	_expect(not empty_inventory_slot.disabled,
		"empty slots stay drawn with worn gear selected")
	# Carrying an item on the cursor, the way the legacy client moves things.
	# The placing click is an authoritative move, so these assertions read the
	# client-side state machine rather than the wire.
	main.set("selected_inventory_slot", -1)
	main.set("_interaction_mode", "walk")
	app_state_inventory.set("inventory", {0: {
		"image_id": 3, "quantity": 9, "slot": 0, "flags": 12,
		"inventory_usable": true, "stackable": true}, 36: {
		"image_id": 8, "quantity": 1, "slot": 36, "flags": 0,
		"inventory_usable": false, "stackable": false}})
	main.call("_sync_inventory")
	var carried: TextureRect = main.get_node("GameView/CarriedItem") as TextureRect
	var carried_quantity: Label = carried.get_node("Quantity") as Label
	main.call("_on_inventory_slot_pressed", 0)
	_expect(int(main.get("_carried_slot")) == 0 and carried.visible
		and carried.texture != null and carried_quantity.text == "9",
		"walk mode lifts a clicked backpack item onto the cursor")
	main.call("_sync_inventory")
	_expect(not empty_inventory_slot.disabled and not empty_equipment_slot.disabled
		and empty_inventory_slot.tooltip_text.contains("Put the carried item")
		and empty_equipment_slot.tooltip_text.contains("Equip the carried item"),
		"a carried item makes every empty inventory and wear slot a target")
	main.call("_on_inventory_slot_pressed", 0)
	_expect(int(main.get("_carried_slot")) == -1 and not carried.visible,
		"clicking the slot it came from puts a carried item back")
	main.call("_on_inventory_slot_pressed", 0)
	main.call("_on_equipment_slot_pressed", 37)
	_expect(int(main.get("_carried_slot")) == -1 and not carried.visible,
		"placing a carried backpack item on a wear slot equips and clears the cursor")
	main.call("_on_equipment_slot_pressed", 36)
	_expect(int(main.get("_carried_slot")) == 36 and carried.visible
		and carried_quantity.text.is_empty(),
		"equipped items lift too, and a single item shows no quantity")
	main.call("_on_inventory_slot_pressed", 1)
	_expect(int(main.get("_carried_slot")) == -1 and not carried.visible,
		"placing a carried equipped item in the backpack unequips it")
	main.call("_on_inventory_slot_pressed", 0)
	_expect(int(main.get("_carried_slot")) == 0, "item back on the cursor to be dropped")
	main.call("_drop_carry")
	_expect(int(main.get("_carried_slot")) == 0 and carried.visible,
		"a drop keeps the stack in hand while any of it remains to drop - and "
		+ "always when the request could not be sent, as here, offline")
	main.call("_on_inventory_slot_pressed", 0)
	main.call("_cancel_carry")
	_expect(int(main.get("_carried_slot")) == -1 and not carried.visible,
		"cancelling returns a carried item without moving it")
	# A stack the server empties underneath the cursor must not stay attached.
	main.call("_on_inventory_slot_pressed", 0)
	app_state_inventory.set("inventory", {36: {
		"image_id": 8, "quantity": 1, "slot": 36, "flags": 0}})
	main.call("_update_carried_item")
	_expect(int(main.get("_carried_slot")) == -1 and not carried.visible,
		"a carried slot the server empties drops off the cursor")
	app_state_inventory.set("inventory", {0: {
		"image_id": 3, "quantity": 9, "slot": 0, "flags": 12,
		"inventory_usable": true, "stackable": true}, 36: {
		"image_id": 8, "quantity": 1, "slot": 36, "flags": 0}})
	main.set("_interaction_mode", "attack")
	main.set("selected_inventory_slot", -1)
	main.call("_on_inventory_slot_pressed", 0)
	_expect(int(main.get("_carried_slot")) == -1 and not carried.visible
		and int(main.get("selected_inventory_slot")) == 0,
		"outside walk mode a click still only selects the item")
	main.set("_interaction_mode", "walk")
	main.call("_cancel_carry")
	await _check_item_clicks(main)
	await _check_trade_mode(main)
	app_state_inventory.set("inventory", {0: {
		"image_id": 3, "quantity": 9, "slot": 0, "flags": 12,
		"inventory_usable": true, "stackable": true}, 36: {
		"image_id": 8, "quantity": 1, "slot": 36, "flags": 0}})
	main.call("_sync_inventory")

	# The slots are the shape of the window: they are drawn whether or not
	# anything is selected or carried, because a disabled button has no frame.
	main.set("selected_inventory_slot", -1)
	main.call("_sync_inventory")
	_expect(not empty_inventory_slot.disabled and not empty_equipment_slot.disabled
		and empty_inventory_slot.tooltip_text.contains("Empty inventory slot")
		and empty_equipment_slot.tooltip_text.contains("Empty generic"),
		"empty inventory and wear slots stay drawn with nothing selected")

	# Right click steps through the tools, and the buttons choose the same ones.
	var inventory_description: RichTextLabel = main.get_node(
		"GameView/InventoryPanel/Content/InventoryBody/BackpackColumn/InventoryDescription"
		) as RichTextLabel
	var use_button: Button = main.get("inventory_use_button") as Button
	var inspect_button: Button = main.get("inventory_inspect_button") as Button
	main.call("_set_inventory_tool", "grab")
	main.call("_cycle_inventory_tool", 0)
	_expect(str(main.get("_inventory_tool")) == "use" and use_button.button_pressed,
		"right clicking an item takes the next tool and the button says so")
	main.call("_cycle_inventory_tool", 0)
	_expect(str(main.get("_inventory_tool")) == "inspect"
		and inspect_button.button_pressed and not use_button.button_pressed,
		"right clicking again takes the one after it")
	main.call("_cycle_inventory_tool", 0)
	_expect(str(main.get("_inventory_tool")) == "grab",
		"and a third right click comes back round to move")
	main.call("_on_inventory_unequip_pressed")
	_expect(str(main.get("_inventory_tool")) == "unequip"
		and (main.get("inventory_unequip_button") as Button).button_pressed,
		"the action buttons choose a tool the same way the right click does")

	# The description line is written whichever tool asked for the item; only
	# Inspect is allowed to open the card over the top of it.
	var extension_windows: Control = main.get("extension_windows") as Control
	var detail_panel: PanelContainer = extension_windows.get(
		"detail_panel") as PanelContainer
	var bread_detail := {"open": true, "name": "Hearth Bread", "category": "Food",
		"quantity": 4, "description": "Baked before dawn.", "equipped": false}
	# The client ignores state changes before login, as it should; these
	# assertions are about a session in progress. The flag is put back below,
	# because a later case checks the diagnostics path without one.
	var was_authenticated: bool = bool(app_state_inventory.get("authenticated"))
	app_state_inventory.set("authenticated", true)
	main.call("_set_inventory_tool", "grab")
	main.call("_describe_slot", 0, false)
	app_state_inventory.set("item_detail", bread_detail)
	app_state_inventory.emit_signal("state_changed", &"item_detail")
	await process_frame
	_expect(not detail_panel.visible
		and inventory_description.text.contains("Hearth Bread")
		and inventory_description.text.contains("Food")
		and inventory_description.text.contains("Move"),
		"a move click writes the short line and opens nothing: "
			+ inventory_description.text)
	main.set("selected_inventory_slot", 0)
	main.call("_on_inventory_inspect_pressed")
	app_state_inventory.set("item_detail", bread_detail)
	app_state_inventory.emit_signal("state_changed", &"item_detail")
	await process_frame
	_expect(detail_panel.visible
		and inventory_description.text.contains("Hearth Bread"),
		"Inspect opens the card and still writes the short line")
	app_state_inventory.call("close_item_detail")
	await process_frame
	main.call("_set_inventory_tool", "grab")
	main.set("selected_inventory_slot", -1)
	app_state_inventory.set("authenticated", was_authenticated)

	# The bag window resizes by the same drag as the inventory, and separately.
	var bag_panel: Control = main.get_node("GameView/GroundBagPanel") as Control
	var bag_grip: Button = main.get_node(
		"GameView/GroundBagPanel/Content/GroundBagFooter/GroundBagResizeGrip"
		) as Button
	_expect(bag_grip != null and bag_grip.tooltip_text.contains("resize"),
		"the bag carries its own resize grip")
	var inventory_scale_before: float = inventory_panel.scale.x
	main.call("_apply_ground_bag_scale", 1.4)
	_expect(is_equal_approx(bag_panel.scale.x, 1.4)
		and is_equal_approx(bag_panel.scale.y, 1.4)
		and is_equal_approx(inventory_panel.scale.x, inventory_scale_before),
		"dragging the bag grip scales the bag and leaves the inventory alone: "
			+ "%f, %f" % [bag_panel.scale.x, inventory_panel.scale.x])
	main.call("_apply_ground_bag_scale", 0.05)
	_expect(is_equal_approx(bag_panel.scale.x, 0.65),
		"and the bag cannot be shrunk past legibility: %f" % bag_panel.scale.x)
	main.call("_apply_ground_bag_scale", 1.0)
	_expect(root.get_visible_rect().encloses(bag_panel.get_global_rect())
		and root.get_visible_rect().encloses(inventory_panel.get_global_rect()),
		"both windows stay on a 1280x720 screen: %s, %s"
			% [bag_panel.get_global_rect(), inventory_panel.get_global_rect()])

	# The six quantity boxes along the bottom, as the legacy client has them.
	var quantity_bar: HBoxContainer = main.get_node(
		"GameView/InventoryPanel/Content/InventoryQuantityBar") as HBoxContainer
	var quantity_boxes: Array = main.get("inventory_quantity_buttons") as Array
	_expect(quantity_bar.get_child_count() == 6 and quantity_boxes.size() == 6
		and (quantity_boxes[0] as Button).text == "1"
		and (quantity_boxes[1] as Button).text == "5"
		and (quantity_boxes[5] as Button).text == "100",
		"the inventory carries six quantity boxes with the legacy defaults")
	_expect((quantity_boxes[0] as Button).button_pressed
		and int(main.call("_selected_quantity")) == 1,
		"the first quantity box starts selected")
	main.call("_on_quantity_box_pressed", 2)
	_expect(int(main.call("_selected_quantity")) == 10
		and (quantity_boxes[2] as Button).button_pressed
		and not (quantity_boxes[0] as Button).button_pressed,
		"clicking a quantity box selects it for every later drop and pick-up")
	var quantity_edit: LineEdit = main.get_node(
		"GameView/InventoryPanel/Content/InventoryQuantityEdit") as LineEdit
	main.call("_begin_quantity_edit", 3)
	_expect(quantity_edit.visible and quantity_edit.text == "20",
		"right clicking a quantity box opens it for editing")
	quantity_edit.text = "42"
	main.call("_commit_quantity_edit")
	_expect(int(main.call("_selected_quantity")) == 42
		and (quantity_boxes[3] as Button).text == "42"
		and not quantity_edit.visible,
		"an edited quantity is kept and becomes the selected one")
	main.call("_begin_quantity_edit", 3)
	quantity_edit.text = ""
	main.call("_commit_quantity_edit")
	_expect(int(main.call("_selected_quantity")) == 20
		and (quantity_boxes[3] as Button).text == "20",
		"clearing a quantity box restores its default rather than leaving zero")
	# Seven digits: a stack runs into the millions on a long-lived character,
	# in the box that moves it and in the count drawn over the slot.
	var big_stack: Dictionary = (app_state_inventory.get("inventory") as Dictionary).duplicate(true)
	big_stack[0] = {"image_id": 3, "quantity": 1234567, "slot": 0,
		"inventory_usable": true, "stackable": true}
	app_state_inventory.set("inventory", big_stack)
	main.call("_sync_inventory")
	_expect(first_quantity.text == "1234567"
		and first_quantity.get_theme_font_size("font_size")
			* first_quantity.text.length() <= first_quantity.size.x * 1.6,
		"a seven-digit stack count is drawn whole over its slot: %s at %d px in %f"
			% [first_quantity.text,
				first_quantity.get_theme_font_size("font_size"),
				first_quantity.size.x])
	_expect(quantity_edit.max_length == 7,
		"the quantity box takes seven digits: %d" % quantity_edit.max_length)
	main.call("_begin_quantity_edit", 4)
	quantity_edit.text = "1234567"
	main.call("_commit_quantity_edit")
	_expect(int(main.call("_selected_quantity")) == 1234567
		and (quantity_boxes[4] as Button).text == "1234567",
		"a seven-digit quantity is kept whole: %s" % (quantity_boxes[4] as Button).text)
	main.call("_begin_quantity_edit", 4)
	quantity_edit.text = "88888888"
	main.call("_commit_quantity_edit")
	_expect(int(main.call("_selected_quantity")) == 8888888,
		"an eighth digit does not fit in the box rather than being taken and"
			+ " silently altered: %d" % int(main.call("_selected_quantity")))
	# Put the box back, since these suites share one settings file.
	main.call("_begin_quantity_edit", 4)
	quantity_edit.text = ""
	main.call("_commit_quantity_edit")
	# Pick-ups and drops clamp to what is actually there.
	main.call("_on_quantity_box_pressed", 5)
	app_state_inventory.set("inventory", {0: {
		"image_id": 3, "quantity": 9, "slot": 0, "flags": 12,
		"inventory_usable": true, "stackable": true}})
	main.set("selected_inventory_slot", 0)
	main.call("_sync_ground_bag_actions")
	var bag_drop_button: Button = main.get_node(
		"GameView/GroundBagPanel/Content/Actions/GroundBagDrop") as Button
	_expect(bag_drop_button.tooltip_text.contains("Drop 9 of the 9"),
		"a quantity larger than the stack drops only what is there: "
		+ bag_drop_button.tooltip_text)
	main.call("_on_quantity_box_pressed", 1)
	main.call("_sync_ground_bag_actions")
	_expect(bag_drop_button.tooltip_text.contains("Drop 5 of the 9"),
		"a quantity smaller than the stack drops exactly that many: "
		+ bag_drop_button.tooltip_text)
	main.call("_on_quantity_box_pressed", 0)
	app_state_inventory.set("inventory_cooldowns", {0: {
		"maximum_msec": 30000, "end_msec": Time.get_ticks_msec() + 12000}})
	main.call("_sync_quick_slots")
	_expect(first_quick_slot.disabled and first_quick_slot.tooltip_text.contains("12 seconds"),
		"server cooldown disables the usable quick slot with remaining time")
	app_state_inventory.set("inventory_cooldowns", {})
	for quick_index: int in range(1, 9):
		_expect(InputMap.has_action("quick_item_%d" % quick_index),
			"item quick slot %d has a centralized input action" % quick_index)
	# What the first quick slot holds is Heal, which every mage knows, and
	# the fixture states everything else it asks for: its mana, and its two
	# reagents by the image id the inventory packet reports for each.
	app_state_inventory.set("pending_spell_target", "")
	app_state_inventory.set("stats", {"magic": 0, "ether": 5})
	app_state_inventory.set("inventory", {
		0: {"image_id": 584, "quantity": 1, "slot": 0, "flags": 6},
		1: {"image_id": 67, "quantity": 1, "slot": 1, "flags": 6}})
	main.call("_sync_spells")
	var prepared_bar: Control = main.get("casting_bar") as Control
	var first_spell_slot: Button = (prepared_bar.get("buttons") as Array)[0] as Button
	_expect(not first_spell_slot.disabled,
		"owned castable spell is enabled; tooltip=" + first_spell_slot.tooltip_text)
	_expect(first_spell_slot.icon != null, "owned castable spell has its legacy icon")
	_expect(first_spell_slot.tooltip_text.contains("Heal"),
		"owned castable spell tooltip names the spell: "
			+ first_spell_slot.tooltip_text)
	# Missing reagents retain full icon opacity and name what is missing.
	app_state_inventory.set("inventory", {
		1: {"image_id": 67, "quantity": 1, "slot": 1, "flags": 6}})
	main.call("_sync_spells")
	_expect(first_spell_slot.self_modulate.a == 1.0
			and first_spell_slot.tooltip_text.contains("Life Essence"),
		"a missing reagent keeps the editable icon fully visible and is named: "
			+ first_spell_slot.tooltip_text)
	app_state_inventory.set("inventory", {
		0: {"image_id": 584, "quantity": 1, "slot": 0, "flags": 6},
		1: {"image_id": 67, "quantity": 1, "slot": 1, "flags": 6}})
	main.call("_sync_spells")
	app_state_inventory.set("stats", {"magic": 0, "ether": 0})
	main.call("_sync_spells")
	_expect(first_spell_slot.self_modulate.a == 1.0 and first_spell_slot.tooltip_text.contains("Requires 5 mana"),
		"an unaffordable spell stays fully visible with the exact availability reason")
	for spell_index: int in range(1, 7):
		_expect(InputMap.has_action("quick_spell_%d" % spell_index),
			"spell quick slot %d has a centralized input action" % spell_index)
	_expect(InputMap.has_action("attack_selected"),
		"combat attack has a centralized input action")
	app_state_inventory.set("inventory", {})
	app_state_inventory.set("stats", {})
	main.call("_on_inventory_close_pressed")
	var viewport_rect: Rect2 = root.get_visible_rect()
	_expect(viewport_rect.encloses(login_panel.get_global_rect()),
		"login panel fits the reference viewport")
	_expect(viewport_rect.encloses(new_character.get_global_rect()),
		"create-character action is visible")
	_expect(viewport_rect.encloses(status.get_global_rect()), "login status is visible")
	var host: LineEdit = main.get_node("LoginPanel/Content/Host") as LineEdit
	_expect(host.text == "game.rabbitlandsgame.com", "canonical Rabbit Lands hostname is the default endpoint")
	var creation_panel: Control = main.get_node("CreationPanel") as Control
	var create_button: Button = main.get_node(
		"CreationPanel/Columns/FormPanel/Form/Actions/Create") as Button
	var back_button: Button = main.get_node(
		"CreationPanel/Columns/FormPanel/Form/Actions/Back") as Button
	login_panel.hide()
	creation_panel.show()
	await process_frame
	_expect(viewport_rect.encloses(creation_panel.get_global_rect()),
		"character-creation panel fits the reference viewport")
	# The preview renders one character, not the map furniture bolted to it.
	# Its camera had no cull mask, so it drew every layer, and the dot an actor
	# carries for the two map cameras - three and a half metres across, three
	# metres up - hung over the model as a pale blue band.
	var preview_camera: Camera3D = main.get_node(
		"CreationPanel/Columns/CharacterPreview/Viewport/PreviewRoot/PreviewCamera"
		) as Camera3D
	var preview_ground: MeshInstance3D = main.get_node(
		"CreationPanel/Columns/CharacterPreview/Viewport/PreviewRoot/PreviewGround"
		) as MeshInstance3D
	var world_camera: Camera3D = camera_rig.get_node("Camera") as Camera3D
	_expect(preview_camera.cull_mask == world_camera.cull_mask
		and (preview_camera.cull_mask & ReplicatedActor3D.MAP_MARKER_LAYER) == 0,
		"the creation preview renders what the gameplay camera renders,"
			+ " and not the map layer")
	_expect(preview_ground.mesh != null
		and (preview_ground.layers & preview_camera.cull_mask) != 0
		and preview_ground.position.y < 0.0,
		"the creation preview stands its character on a piece of ground")
	_expect(viewport_rect.encloses(create_button.get_global_rect()),
		"create-character submit action is visible")
	_expect(viewport_rect.encloses(back_button.get_global_rect()),
		"character-creation back action is visible")
	creation_panel.hide()
	game_view.show()

	var right_down: InputEventMouseButton = InputEventMouseButton.new()
	right_down.button_index = MOUSE_BUTTON_RIGHT
	right_down.pressed = true
	main.set("_interaction_mode", "walk")
	main.call("_on_world_gui_input", right_down)
	_expect(str(main.get("_interaction_mode")) == "walk",
		"right click over empty ground keeps the Move action")
	var motion: InputEventMouseMotion = InputEventMouseMotion.new()
	motion.relative = Vector2(40.0, 12.0)
	var initial_yaw: float = camera_rig.yaw_degrees
	main.call("_on_world_gui_input", motion)
	_expect(is_equal_approx(camera_rig.yaw_degrees, initial_yaw),
		"right drag never rotates or pans the camera")
	var right_up: InputEventMouseButton = InputEventMouseButton.new()
	right_up.button_index = MOUSE_BUTTON_RIGHT
	right_up.pressed = false
	main.call("_on_world_gui_input", right_up)
	_expect(str(main.get("_interaction_mode")) == "walk",
		"right release does not cycle a second time")
	main.set("_interaction_mode", "walk")

	var wheel: InputEventMouseButton = InputEventMouseButton.new()
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	wheel.pressed = true
	var initial_distance: float = camera_rig.distance
	main.call("_on_world_gui_input", wheel)
	_expect(camera_rig.distance < initial_distance, "mouse wheel zooms camera")

	var middle_down: InputEventMouseButton = InputEventMouseButton.new()
	middle_down.button_index = MOUSE_BUTTON_MIDDLE
	middle_down.pressed = true
	main.call("_on_world_gui_input", middle_down)
	var rotate_motion: InputEventMouseMotion = InputEventMouseMotion.new()
	rotate_motion.relative = Vector2(25.0, -10.0)
	main.call("_on_world_gui_input", rotate_motion)
	_expect(not is_equal_approx(camera_rig.yaw_degrees, initial_yaw)
		and camera_rig.global_position.is_equal_approx(camera_rig.focus),
		"middle drag rotates around the focus without panning")
	var middle_up: InputEventMouseButton = middle_down.duplicate() as InputEventMouseButton
	middle_up.pressed = false
	main.call("_input", middle_up)
	var released_yaw: float = camera_rig.yaw_degrees
	main.call("_on_world_gui_input", rotate_motion)
	_expect(is_equal_approx(camera_rig.yaw_degrees, released_yaw),
		"middle release outside the world ends rotation")
	var follow_actor: Node3D = Node3D.new()
	world_viewport.get_node("WorldRoot").add_child(follow_actor)
	follow_actor.global_position = Vector3(18.0, 47.0, -9.0)
	var app_state: Node = root.get_node("AppState")
	var previous_local_actor_id: int = int(app_state.get("local_actor_id"))
	app_state.set("local_actor_id", 9001)
	var fixture_actors: Dictionary = {9001: follow_actor}
	main.set("actor_nodes", fixture_actors)
	main.call("_update_local_actor_follow")
	_expect(camera_rig.focus.is_equal_approx(follow_actor.global_position),
		"camera continuously follows the rendered local actor")
	_expect(camera_rig.global_position.is_equal_approx(follow_actor.global_position),
		"camera focus never gains a pan offset")
	main.set("_minimap_orientation", "viewport_up")
	camera_rig.yaw_degrees = 37.0
	main.call("_update_local_actor_follow")
	_expect(is_equal_approx(map_camera.rotation.y, deg_to_rad(37.0)),
		"viewport-up minimap tracks camera yaw independently of actor facing")
	chat_input.release_focus()
	var recenter_key: InputEventKey = InputEventKey.new()
	recenter_key.pressed = true
	recenter_key.physical_keycode = KEY_SPACE
	main.call("_input", recenter_key)
	_expect(camera_rig.global_position.is_equal_approx(follow_actor.global_position),
		"Space recenters the viewport on the local player when chat is inactive")
	main.set("_minimap_orientation", "north_up")
	app_state.set("local_actor_id", previous_local_actor_id)
	follow_actor.queue_free()

	# The minimap frame holds absolutely positioned children: the map inset by the
	# compass border, and four cardinal labels that main.gd places on a ring.
	# A Container parent re-sorts those children over that layout the moment the
	# frame is shown, so the frame must not be one.
	_expect(not (minimap_frame is Container),
		"the minimap frame does not re-sort its absolutely positioned children")
	minimap_frame.show()
	for _frame: int in range(3):
		await process_frame
	var minimap_border: float = roundf(
		float(main.get("_minimap_border")) * float(main.get("_minimap_scale")))
	_expect(minimap_image.position.is_equal_approx(Vector2.ONE * minimap_border)
		and minimap_image.size.is_equal_approx(
			minimap_frame.size - Vector2.ONE * minimap_border * 2.0),
		"showing the minimap keeps the map inset inside the compass border")
	var north_label: Control = main.get_node("GameView/MinimapFrame/North") as Control
	var east_label: Control = main.get_node("GameView/MinimapFrame/East") as Control
	_expect(north_label.size.x < minimap_frame.size.x * 0.5
		and not north_label.position.is_equal_approx(east_label.position),
		"showing the minimap keeps the cardinal labels on the compass ring")
	var shown_centre: Vector2 = main.call("_control_to_viewport_position",
		minimap_image.size * 0.5, minimap_image.size, minimap_viewport.size) as Vector2
	_expect(shown_centre.is_equal_approx(Vector2(minimap_viewport.size) * 0.5),
		"a visible minimap still converts clicks into minimap viewport pixels")
	# The marks are only measurable once the frame has been laid out, so the
	# overlay is checked here rather than beside the menu it is configured by.
	_check_minimap_markers(main, minimap_image, map_camera)
	minimap_frame.hide()
	await process_frame

	_expect(container.texture == world_viewport.get_texture(),
		"the gameplay view draws the world render target")
	root.size = Vector2i(2560, 1440)
	await process_frame
	main.call("_on_window_size_changed")
	_expect(world_viewport.size == Vector2i(2560, 1440),
		"enlarging the window raises the world render resolution instead of upscaling")
	main.call("_on_ui_scale_changed", 0.5)
	await process_frame
	_expect(is_equal_approx(root.content_scale_factor, 0.5)
		and container.size.is_equal_approx(Vector2(2560, 1440)),
		"UI scale trades HUD size for canvas space")
	_expect(world_viewport.size == Vector2i(2560, 1440),
		"UI scale leaves the world render resolution at the window pixel size")
	main.call("_on_ui_scale_changed", 1.0)
	await process_frame
	root.size = original_window_size
	await process_frame

	# Perks and lifetime counters are authoritative server state. The client
	# keeps no perk name table and no counter of its own.
	var counter_categories: ItemList = main.get_node(
		"GameView/StatsPanel/Content/StatsTabs/Counters/CounterColumns/CounterCategories") as ItemList
	var counter_text: RichTextLabel = main.get_node(
		"GameView/StatsPanel/Content/StatsTabs/Counters/CounterColumns/CounterText") as RichTextLabel
	_expect(counter_categories.item_count == 0,
		"the counter window ships with no locally invented categories")
	var stats_text: RichTextLabel = main.get_node(
		"GameView/StatsPanel/Content/StatsTabs/Statistics/StatsText") as RichTextLabel
	# Drive the real signal path rather than calling the sync helpers directly,
	# so a missing state_changed case would fail here. The window is built only
	# while it is on screen, so it is opened the way a player would open it.
	(main.get_node("GameView/StatsPanel") as Control).show()
	var previously_authenticated: bool = bool(app_state_inventory.get("authenticated"))
	app_state_inventory.set("authenticated", true)
	app_state_inventory.set("stats", {"health": 10, "max_health": 10})
	var perks_payload: PackedByteArray = PackedByteArray([1, 0, 1, 0xfb, 0xff])
	perks_payload.append_array(_nul_bytes("Power Hungry"))
	perks_payload.append_array(_nul_bytes("Lose 3 food per minute."))
	app_state_inventory.call("_on_packet", 234, perks_payload)
	var reduced_perks: Array = app_state_inventory.get("perks") as Array
	_expect(reduced_perks.size() == 1
		and str((reduced_perks[0] as Dictionary).get("name", "")) == "Power Hungry"
		and bool((reduced_perks[0] as Dictionary).get("from_gear", false)),
		"a perk the client has never heard of is still reduced and flagged")
	# The statistics tab is built from controls now, so the perks are a label
	# of their own rather than a run of bbcode inside the document.
	var perk_line: Label = main.get("stats_perk_line") as Label
	_expect(perk_line != null and perk_line.text.contains("Power Hungry")
		and perk_line.text.contains("from equipment"),
		"the statistics window presents the server's perks, not a scraped list")
	app_state_inventory.call("_on_packet", 234, PackedByteArray([0, 0]))
	_expect((app_state_inventory.get("perks") as Array).is_empty()
		and not perk_line.text.contains("Power Hungry"),
		"an empty perk packet clears the presented perks")

	var counters_snapshot: PackedByteArray = PackedByteArray([1, 2, 4, 0, 0, 0])
	counters_snapshot.append_array(_nul_bytes("Kills"))
	counters_snapshot.append_array(PackedByteArray([7, 0, 0, 0]))
	counters_snapshot.append_array(_nul_bytes("Harvests"))
	app_state_inventory.call("_on_packet", 235, counters_snapshot)
	_expect(int(app_state_inventory.get("activity_counters").get("Kills", 0)) == 4
		and int(app_state_inventory.get("activity_counters").get("Harvests", 0)) == 7,
		"the totals are the server's snapshot, in the server's numbers")
	# The pages the window shows come from the layout packet rather than from
	# the totals: which page a counter sits on is a thing the server says, and
	# a client grouping the snapshot itself would be guessing.
	var layout: PackedByteArray = PackedByteArray([1, 0, 0, 1])
	layout.append_array(_nul_bytes("Combat"))
	layout.append_array(_nul_bytes("Kills"))
	app_state_inventory.call("_on_packet", 217, layout)
	var tabs: HBoxContainer = main.get("counter_tabs") as HBoxContainer
	_expect(tabs != null and tabs.get_child_count() == 1
		and (tabs.get_child(0) as Button).text == "Combat",
		"the counter pages are built from the layout the server sent")
	_expect(_counter_row_text(main, "Kills").contains("4"),
		"the page presents the server total")
	var counter_delta: PackedByteArray = PackedByteArray([0, 1, 9, 0, 0, 0])
	counter_delta.append_array(_nul_bytes("Harvests"))
	app_state_inventory.call("_on_packet", 235, counter_delta)
	_expect(int((app_state_inventory.get("activity_counters") as Dictionary).get(
		"Harvests", -1)) == 9 and tabs.get_child_count() == 1,
		"a delta updates one total without disturbing the pages")
	main.call("_reset_session_tracking")
	var after_reset: PackedByteArray = PackedByteArray([0, 1, 11, 0, 0, 0])
	after_reset.append_array(_nul_bytes("Kills"))
	app_state_inventory.call("_on_packet", 235, after_reset)
	# The session column is a difference against the server's total rather
	# than a second count kept here, so a reset moves the baseline and the
	# lifetime figure is untouched.
	_expect(_counter_row_text(main, "Kills").contains("11"),
		"resetting the session keeps the authoritative lifetime total")
	app_state_inventory.set("authenticated", previously_authenticated)
	(main.get_node("GameView/StatsPanel") as Control).hide()

	# Protocol diagnostics. Every undecoded packet and decode error used to be
	# reduced into AppState and emitted with no listener at all, which is how
	# most of the gaps in this client went unnoticed.
	var console_panel: Control = main.get_node("GameView/ConsolePanel") as Control
	var console_output: RichTextLabel = main.get_node(
		"GameView/ConsolePanel/Content/ConsoleOutput") as RichTextLabel
	var diagnostics_button: Button = main.get_node(
		"GameView/ConsolePanel/Content/Header/ConsoleDiagnostics") as Button
	var diagnostics_output: RichTextLabel = main.get_node(
		"GameView/ConsolePanel/Content/DiagnosticsOutput") as RichTextLabel
	_expect(diagnostics_button.toggle_mode and not diagnostics_output.visible
		and console_output.visible,
		"the console opens on its message history with diagnostics one click away")
	main.call("_toggle_console")
	diagnostics_button.button_pressed = true
	await process_frame
	_expect(diagnostics_output.visible and not console_output.visible,
		"the diagnostics view replaces the message history in the console panel")
	_expect(diagnostics_output.text.contains("none"),
		"a clean session reports no undecoded opcodes and no decode errors")
	# 199 is not a server opcode this client knows; 36 with a one-byte payload
	# is the pre-0.6 trade accept, which must now fail to decode.
	app_state_inventory.call("_on_packet", 199, PackedByteArray([1, 2, 3]))
	app_state_inventory.call("_on_packet", 199, PackedByteArray([4]))
	app_state_inventory.call("_on_packet", 36, PackedByteArray([0]))
	await process_frame
	_expect(diagnostics_output.text.contains("199")
		and diagnostics_output.text.contains("x2"),
		"an undecoded opcode is listed once with the number of times it arrived")
	_expect(diagnostics_output.text.contains("trade_accept_length"),
		"a decode error names the packet and the failure")
	_expect(int(app_state_inventory.get("unknown_packet_count")) == 2
		and (app_state_inventory.get("unknown_packets") as Dictionary).size() == 1,
		"the same unknown opcode is counted, not re-listed")
	# The panel has to work before login: a handshake decode failure is exactly
	# what it exists to show, and the state-changed handler gates everything else on
	# an authenticated session.
	_expect(not bool(app_state_inventory.get("authenticated")),
		"the diagnostics assertions above ran on an unauthenticated session")
	root.size = Vector2i(1280, 720)
	await process_frame
	main.call("_on_window_size_changed")
	await process_frame
	var console_rect: Rect2 = console_panel.get_global_rect()
	_expect(console_rect.position.x >= 0.0 and console_rect.position.y >= 0.0
		and console_rect.end.x <= 1280.0 and console_rect.end.y <= 720.0,
		"the console panel with diagnostics still fits within 1280x720")
	_expect(not console_rect.intersects(right_stats.get_global_rect()),
		"the console panel with diagnostics does not cover the fixed resource rail")
	var console_escape: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	console_escape.pressed = true
	main.call("_input", console_escape)
	_expect(not console_panel.visible,
		"the console panel with diagnostics open still answers the cancel cascade")
	diagnostics_button.button_pressed = false
	await process_frame

	# The map digest, which is the one thing the server can say about content
	# it cannot send. A package that matches is silent; one that does not says
	# so in the console, because the symptoms of a stale map - a door in the
	# wrong place, a portal that goes nowhere - look like anything but a stale
	# install, and nothing else in the client will ever mention it.
	MapSceneCache.forget_digests()
	var agreeing: String = "b".repeat(64)
	MapSceneCache.note_local_digest("amberwood", agreeing)
	var lines_before: int = (app_state_inventory.get("chat_lines") as Array).size()
	app_state_inventory.call("_on_packet",
		EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST,
		_hex_bytes("616d626572776f6f6400" + "62".repeat(64) + "00"))
	await process_frame
	_expect((app_state_inventory.get("chat_lines") as Array).size() == lines_before
		and not MapSceneCache.has_mismatch("amberwood"),
		"a map package that matches the server's digest is not mentioned")

	MapSceneCache.forget_digests()
	MapSceneCache.note_local_digest("amberwood", "c".repeat(64))
	app_state_inventory.call("_on_packet",
		EloriaProtocol.ServerMessage.ELORIA_MAP_DIGEST,
		_hex_bytes("616d626572776f6f6400" + "62".repeat(64) + "00"))
	await process_frame
	var digest_lines: Array = app_state_inventory.get("chat_lines") as Array
	var digest_line: String = "" if digest_lines.is_empty() \
		else str((digest_lines[digest_lines.size() - 1] as Dictionary).get("text", ""))
	_expect(MapSceneCache.has_mismatch("amberwood"),
		"a map package the server does not expect is recorded as a mismatch")
	_expect(digest_line.contains("amberwood") and digest_line.contains("bbbb")
		and digest_line.contains("cccc"),
		"and named in the console with both digests: %s" % digest_line)
	_expect(MapSceneCache.digest_summary().contains("amberwood"),
		"so the settings row can say which map disagrees")
	MapSceneCache.forget_digests()

	# Decoded fields with a consumer: research progress and cooldown art.
	(main.get_node("GameView/StatsPanel") as Control).show()
	app_state_inventory.set("stats", {"health": 10, "max_health": 10,
		"researching": 1024, "research_completed": 0, "research_total": 0})
	main.call("_sync_stats")
	_expect(_character_column_text(main).contains("Researching")
		and _character_column_text(main).contains("nothing"),
		"a character reading nothing says so instead of hiding the field")
	app_state_inventory.set("stats", {"health": 10, "max_health": 10,
		"researching": 0, "research_completed": 30, "research_total": 120})
	main.call("_sync_stats")
	var reading: String = _character_column_text(main)
	_expect(reading.contains("30/120") and reading.contains("25%"),
		"reading progress is presented from the authoritative research statistics")
	(main.get_node("GameView/StatsPanel") as Control).hide()

	var cooldown_slot: Button = (main.get("quick_slot_buttons") as Array)[0] as Button
	var cooldown_slot_two: Button = (main.get("quick_slot_buttons") as Array)[1] as Button
	var inventory_cooldown_slot: Button = (main.get("inventory_slot_buttons") as Array)[10] as Button
	var cooldowns: Dictionary = app_state_inventory.get("inventory_cooldowns") as Dictionary
	cooldowns.clear()
	main.call("_update_cooldown_overlays")
	var cooldown_shade: Control = cooldown_slot.get_node_or_null("Cooldown") as Control
	_expect(cooldown_shade != null and not cooldown_shade.visible,
		"a slot with no cooldown draws no cooldown art")
	var cooldown_seconds: Label = cooldown_slot.get_node_or_null("Seconds") as Label
	_expect(cooldown_seconds != null and cooldown_seconds.get_parent() == cooldown_slot,
		"the countdown label sits directly on the slot instead of inside the"
		+ " shade that drains, so it cannot drift down the icon as the shade does")
	cooldowns[0] = {"maximum_msec": 10000,
		"end_msec": Time.get_ticks_msec() + 10000}
	main.call("_update_cooldown_overlays")
	_expect(cooldown_shade.visible
		and is_equal_approx(snappedf(cooldown_shade.anchor_top, 0.05), 0.0),
		"a cooldown at its full duration covers the whole slot")
	cooldowns[0] = {"maximum_msec": 10000,
		"end_msec": Time.get_ticks_msec() + 2500}
	main.call("_update_cooldown_overlays")
	_expect(is_equal_approx(snappedf(cooldown_shade.anchor_top, 0.05), 0.75),
		"a quarter-remaining cooldown draws a quarter of the slot")
	_expect(cooldown_seconds.text == "3",
		"the cooldown art also states the seconds remaining")
	_expect(is_equal_approx(cooldown_seconds.anchor_top, 0.0)
		and is_equal_approx(cooldown_seconds.anchor_bottom, 1.0),
		"the countdown label still spans the whole slot rather than the"
		+ " shrunken shade, so it stays centered as the cooldown runs out")

	# The quick bar and the inventory grid share the same slot numbers, so a
	# second and third slot going on cooldown must not blank the first: every
	# slot on cooldown draws its own countdown at once, in both places.
	cooldowns[1] = {"maximum_msec": 8000, "end_msec": Time.get_ticks_msec() + 8000}
	cooldowns[10] = {"maximum_msec": 6000, "end_msec": Time.get_ticks_msec() + 6000}
	main.call("_update_cooldown_overlays")
	_expect(cooldown_shade.visible
		and (cooldown_slot_two.get_node("Cooldown") as Control).visible
		and (cooldown_slot_two.get_node("Seconds") as Label).text == "8",
		"two quick-bar slots on cooldown at once both show their own countdown")
	_expect((inventory_cooldown_slot.get_node_or_null("Cooldown") as Control) != null
		and (inventory_cooldown_slot.get_node("Cooldown") as Control).visible
		and (inventory_cooldown_slot.get_node("Seconds") as Label).text == "6",
		"the inventory grid draws the same cooldown art as the quick bar")

	# The server announces one slot's cooldown per packet and never resends
	# the full active set. A second slot's packet used to wipe the first
	# slot's still-running countdown; it must merge instead.
	cooldowns.clear()
	app_state_inventory.call("_on_packet", 77, PackedByteArray([0, 10, 0, 10, 0]))
	app_state_inventory.call("_on_packet", 77, PackedByteArray([1, 8, 0, 8, 0]))
	_expect(cooldowns.has(0) and cooldowns.has(1),
		"a second slot's cooldown packet merges instead of replacing the first")

	cooldowns[0] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() - 1}
	cooldowns[1] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() - 1}
	cooldowns[10] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() - 1}
	main.call("_update_cooldown_overlays")
	_expect(not cooldown_shade.visible, "an expired cooldown clears its art")
	cooldowns.clear()

	# Server popups. The server had no way to ask the player anything: the
	# packet fell through to "unknown" and the reply had no encoder.
	var popup_panel: PanelContainer = main.get_node(
		"GameView/PopupPanel") as PanelContainer
	var popup_options: VBoxContainer = main.get_node(
		"GameView/PopupPanel/PopupContent/PopupOptions") as VBoxContainer
	var popup_confirm: Button = main.get_node(
		"GameView/PopupPanel/PopupContent/PopupActions/PopupConfirm") as Button
	var full_map: Control = main.get_node("GameView/FullMap") as Control
	_expect(not popup_panel.visible, "the popup window starts closed")
	var radio_popup: PackedByteArray = PackedByteArray([0, 0, 0])
	radio_popup.append_array(_sized_bytes("Summon Behavior"))
	radio_popup.append_array(PackedByteArray([0x68, 0x01]))
	radio_popup.append_array(_sized_bytes("Choose how your summons pick targets."))
	radio_popup.append_array(PackedByteArray([9, 1]))
	radio_popup.append_array(_sized_bytes("Weakest first"))
	radio_popup.append(0)
	radio_popup.append_array(PackedByteArray([9, 1]))
	radio_popup.append_array(_sized_bytes("Strongest first"))
	radio_popup.append(1)
	app_state_inventory.set("authenticated", true)
	console_panel.show()
	full_map.show()
	app_state_inventory.call("_on_packet", 83, radio_popup)
	await process_frame
	_expect(popup_panel.visible and not console_panel.visible and not full_map.visible,
		"a popup is modal: it opens and closes the panels underneath it")
	_expect(popup_confirm.visible,
		"a popup with radio options gets a send button, as the legacy contract requires")
	var checkboxes: Array[CheckBox] = []
	for child: Node in popup_options.get_children():
		if child is CheckBox:
			checkboxes.append(child as CheckBox)
	_expect(checkboxes.size() == 2
		and checkboxes[0].text == "Weakest first"
		and checkboxes[1].text == "Strongest first",
		"both radio options are presented with their server labels")
	checkboxes[0].button_pressed = true
	checkboxes[1].button_pressed = true
	await process_frame
	_expect(not checkboxes[0].button_pressed and checkboxes[1].button_pressed,
		"one selection per group: the wire carries exactly one answer per group")
	_expect(int((main.get("_popup_radio_groups") as Dictionary).get(1, -1)) == 1,
		"the selected radio value is the server's value, not the button index")
	var popup_rect: Rect2 = popup_panel.get_global_rect()
	_expect(popup_rect.position.x >= 0.0 and popup_rect.position.y >= 0.0
		and popup_rect.end.x <= 1280.0 and popup_rect.end.y <= 720.0,
		"the popup fits within 1280x720")
	_expect(not popup_rect.intersects(right_stats.get_global_rect()),
		"the popup does not cover the fixed resource rail")
	# The cancel cascade: a modal popup answers Escape before anything under it.
	var popup_escape: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	popup_escape.pressed = true
	main.call("_unhandled_input", popup_escape)
	await process_frame
	_expect(not popup_panel.visible
		and not bool((app_state_inventory.get("popup") as Dictionary).get("open", true)),
		"cancel dismisses the popup")

	# A popup built only from text options answers on the click itself.
	var action_popup: PackedByteArray = PackedByteArray([5, 0, 0])
	action_popup.append_array(_sized_bytes("Confirm"))
	action_popup.append_array(PackedByteArray([0x2c, 0x01]))
	action_popup.append_array(_sized_bytes("Really?"))
	action_popup.append_array(PackedByteArray([8, 3]))
	action_popup.append_array(_sized_bytes("Yes"))
	action_popup.append(1)
	app_state_inventory.call("_on_packet", 83, action_popup)
	await process_frame
	_expect(popup_panel.visible and not popup_confirm.visible,
		"a popup of text options only needs no send button")
	# The same popup arriving twice must not reopen or duplicate its options.
	var option_count: int = popup_options.get_child_count()
	app_state_inventory.call("_on_packet", 83, action_popup)
	await process_frame
	_expect(popup_options.get_child_count() == option_count,
		"a repeated popup for an id already on screen is ignored")
	for child: Node in popup_options.get_children():
		if child is Button:
			(child as Button).pressed.emit()
			break
	await process_frame
	# There is no connection in this suite, so the reply could not be sent. The
	# popup must stay open rather than pretending the server was answered; the
	# close-on-success path is proved against a real server in
	# tests/integration/popup_local.py.
	_expect(popup_panel.visible
		and bool((app_state_inventory.get("popup") as Dictionary).get("open", false)),
		"an answer that could not be sent leaves the popup open")
	app_state_inventory.call("close_popup")
	await process_frame
	_expect(not popup_panel.visible, "closing the popup state closes the window")
	app_state_inventory.set("authenticated", false)
	console_panel.hide()
	full_map.hide()

	# Harvesting and world-object interaction. The world click handler tried
	# actors, then ground bags, then the navigation surface, and stopped: no
	# rendered prop was ever clickable, so the whole harvestable layer and
	# every interactive were unreachable.
	var harvest_banner: Label = main.get_node("GameView/HarvestBanner") as Label
	_expect(not harvest_banner.visible, "the harvesting indicator starts hidden")
	var objects_payload: PackedByteArray = PackedByteArray([1, 2, 0])
	objects_payload.append_array(PackedByteArray([
		0xf0, 0x01, EloriaProtocol.MAP_OBJECT_HARVEST, 0x02, 0x03, 0xe1, 0x01]))
	objects_payload.append_array(_nul_bytes("Reed"))
	objects_payload.append_array(_nul_bytes("Harvesting level 0"))
	objects_payload.append_array(PackedByteArray([
		0x0e, 0x00, EloriaProtocol.MAP_OBJECT_INTERACTIVE, 0x00, 0x03, 0x90, 0x05]))
	objects_payload.append_array(_nul_bytes("Storage"))
	objects_payload.append_array(_nul_bytes("A wayfarer's cache."))
	# Four entries: the count byte pair above says two, so it is rewritten.
	objects_payload[1] = 4
	objects_payload.append_array(PackedByteArray([
		0x14, 0x00, EloriaProtocol.MAP_OBJECT_INTERACTIVE, 0x48, 0x01, 0x0e, 0x00]))
	objects_payload.append_array(_nul_bytes("Portal"))
	objects_payload.append_array(_nul_bytes("The waygate hums. Beyond it lies Grey Moors."))
	objects_payload.append_array(PackedByteArray([
		0x60, 0xea, EloriaProtocol.MAP_OBJECT_EXIT, 0xf6, 0x00, 0x2c, 0x02]))
	objects_payload.append_array(_nul_bytes("Amberwood Estate"))
	objects_payload.append_array(_nul_bytes("The way to Amberwood Estate."))
	app_state_inventory.set("authenticated", true)
	app_state_inventory.call("_on_packet", 236, objects_payload)
	await process_frame
	var object_nodes: Dictionary = main.get("map_object_nodes") as Dictionary
	_expect(object_nodes.size() == 4,
		"every server world object becomes a node in the scene")
	# The exits and the waygates: a way off the map is not clickable and has
	# nothing standing on it, and both maps draw it as the legend's red X
	# with its destination; a waygate is the cyan P, named from its own text.
	var exit_node: MapObject3D = object_nodes.get(60000) as MapObject3D
	var portal_node: MapObject3D = object_nodes.get(20) as MapObject3D
	_expect(exit_node != null and exit_node.is_exit() and exit_node.get_child_count() == 0
		and exit_node.destination() == "Amberwood Estate"
		and exit_node.map_glyph() == MapObject3D.EXIT_GLYPH
		and exit_node.map_dot_colour().is_equal_approx(MapObject3D.EXIT_COLOUR),
		"a map exit stands for nothing, takes no click, and is the legend's red X")
	_expect(portal_node != null and portal_node.is_portal()
		and portal_node.get_node_or_null("PickShape") != null
		and portal_node.get_node_or_null("MapMarker") == null
		and portal_node.destination() == "Grey Moors"
		and portal_node.map_glyph() == MapObject3D.PORTAL_GLYPH
		and portal_node.map_dot_colour().is_equal_approx(MapObject3D.PORTAL_COLOUR),
		"a waygate keeps its click target and is drawn as the legend's cyan P")
	var minimap_marks: Array = main.call("_collect_minimap_marks")
	var exit_marks: Array = minimap_marks.filter(
		func(mark: Dictionary) -> bool: return mark.get("type") == &"exit")
	var portal_marks: Array = minimap_marks.filter(
		func(mark: Dictionary) -> bool: return mark.get("type") == &"portal")
	_expect(exit_marks.size() == 1 and str((exit_marks[0] as Dictionary).get("glyph")) == "X"
		and portal_marks.size() == 1
		and str((portal_marks[0] as Dictionary).get("glyph")) == "P",
		"the minimap marks an exit as X and a waygate as P, each on its own switch")
	var full_map_overlay: Control = main.get("map_marker_overlay") as Control
	_expect(full_map_overlay != null and int(full_map_overlay.call("waypoint_count")) == 2,
		"the full map draws both glyphs with their destinations")
	_expect((main.get("MINIMAP_MARKER_TYPES") as Array).has(&"exit")
		and (main.get("MINIMAP_MARKER_TYPES") as Array).has(&"portal"),
		"portals and exits are marker types a player can switch off")
	var harvest_node: MapObject3D = object_nodes.get(496) as MapObject3D
	var interactive_node: MapObject3D = object_nodes.get(14) as MapObject3D
	_expect(harvest_node != null and harvest_node.is_harvestable()
		and interactive_node != null and not interactive_node.is_harvestable(),
		"harvest nodes and interactives are told apart by the server's kind")
	_expect(harvest_node != null
		and harvest_node.collision_layer == MapObject3D.PICK_LAYER
		and harvest_node.collision_layer != GroundBag3D.PICK_LAYER,
		"world objects pick on their own layer, not the ground-bag layer")
	_expect(harvest_node != null
		and harvest_node.get_node_or_null("MapMarker") != null,
		"a world object is visible on both map cameras")
	# The prop, not a ring: the reed bed and the wayfarer's cache stand on the
	# tile, and the ring is left for the node being harvested.
	_expect(harvest_node != null and harvest_node.get_node_or_null("Model") != null
		and harvest_node.model_id == "mirror_reed"
		and interactive_node != null and interactive_node.get_node_or_null("Model") != null
		and interactive_node.model_id == "storage",
		"a world object stands as the resource or the service it is")
	var harvest_ring: MeshInstance3D = (harvest_node.get_node_or_null("Ring")
		as MeshInstance3D) if harvest_node != null else null
	_expect(harvest_ring != null and not harvest_ring.visible,
		"the placeholder ring is not drawn under a node that has a model")
	var interactive_marker: MeshInstance3D = (
		interactive_node.get_node_or_null("MapMarker") as MeshInstance3D
	) if interactive_node != null else null
	var interactive_material: StandardMaterial3D = (
		interactive_marker.mesh.surface_get_material(0) as StandardMaterial3D
	) if interactive_marker != null else null
	_expect(interactive_material != null
		and interactive_material.albedo_color.is_equal_approx(
			MapObject3D.INTERACTIVE_COLOUR),
		"an interactive is orange on the map, as the legend says")
	var map_legend: RichTextLabel = main.get_node(
		"GameView/FullMap/MapLayout/Sidebar/SidebarLayout/SidebarScroll/SidebarContent/MapLegend") as RichTextLabel
	_expect(map_legend != null and map_legend.text.contains("Harvest node")
		and map_legend.text.contains("Interactive")
		and map_legend.text.contains("Player / NPC")
		and map_legend.text.contains("Invasion creature"),
		"the legend names every colour the map draws")
	# Each of the five is the colour the legend's own swatch is written in, so
	# a reader comparing the sidebar to the map is comparing like with like.
	_expect(map_legend != null
		and map_legend.text.contains("[color=#%s]●[/color] Player / NPC" % (
			ReplicatedActor3D.MAP_DOT_COLOUR.to_html(false)))
		and map_legend.text.contains("[color=#%s]●[/color] Invasion creature" % (
			ReplicatedActor3D.INVASION_MAP_DOT_COLOUR.to_html(false)))
		and map_legend.text.contains("[color=#%s]●[/color] Creature" % (
			ReplicatedActor3D.CREATURE_MAP_DOT_COLOUR.to_html(false)))
		and map_legend.text.contains("[color=#%s]●[/color] Harvest node" % (
			MapObject3D.HARVEST_COLOUR.to_html(false)))
		and map_legend.text.contains("[color=#%s]●[/color] Interactive" % (
			MapObject3D.INTERACTIVE_COLOUR.to_html(false)))
		and map_legend.text.contains("[color=#%s]P[/color] Portal" % (
			MapObject3D.PORTAL_COLOUR.to_html(false)))
		and map_legend.text.contains("[color=#%s]X[/color] Map exit" % (
			MapObject3D.EXIT_COLOUR.to_html(false))),
		"every legend swatch is the colour the map actually draws")
	_expect(harvest_node != null and harvest_node.server_tile == Vector2i(770, 481),
		"the pick target sits on the tile the server named")

	# The harvest indicator follows the authoritative state, not a chat phrase.
	var started: PackedByteArray = PackedByteArray([1, 0xf0, 0x01])
	started.append_array(_nul_bytes("Reed"))
	app_state_inventory.call("_on_packet", 237, started)
	await process_frame
	_expect(harvest_banner.visible and harvest_banner.text.contains("Reed"),
		"the harvesting indicator names the resource the server reported")
	_expect(harvest_ring != null and harvest_ring.visible
		and (harvest_ring.material_override as StandardMaterial3D
			).albedo_color.is_equal_approx(
				Color(MapObject3D.ACTIVE_COLOUR, 0.75)),
		"the ring marks the node the player is harvesting")
	_expect(harvest_banner.get_global_rect().end.y <= 720.0
		and harvest_banner.get_global_rect().position.y >= 0.0,
		"the harvesting indicator fits within 1280x720")
	_expect(not harvest_banner.get_global_rect().intersects(
		right_stats.get_global_rect()),
		"the harvesting indicator does not cover the fixed resource rail")
	app_state_inventory.call("_on_packet", 237, PackedByteArray([0, 0, 0, 0]))
	await process_frame
	_expect(harvest_ring != null and not harvest_ring.visible,
		"the ring goes away again when the harvest stops")
	_expect(not harvest_banner.visible,
		"a server stop - moving, a full backpack, combat - clears the indicator")

	# Effects the server announced. They are events, not state: each draws
	# itself where the actor stands and frees itself when it finishes.
	app_state_inventory.call("_on_packet", 51, _hex_bytes(
		"5b000203e1010000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	app_state_inventory.call("_on_packet", 79, PackedByteArray([17, 0x5b, 0]))
	await process_frame
	var effects: Array = main.get("world_effects") as Array
	_expect(effects.size() == 1
		and (effects[0] as WorldEffect3D).effect_id == 17,
		"the effect the server announced is drawn")
	_expect((effects[0] as WorldEffect3D).get_node_or_null("EffectBeam") == null,
		"an effect with no second actor draws no beam")
	var effect_burst: GPUParticles3D = (effects[0] as WorldEffect3D
		).get_node_or_null("EffectBurst") as GPUParticles3D
	_expect(effect_burst != null and effect_burst.amount > 0
		and effect_burst.one_shot and effect_burst.process_material != null
		and effect_burst.draw_pass_1 != null,
		"the effect is a particle burst, not a bare ring")
	# A harmful effect falls and a beneficial one rises: the one distinction
	# the server's own grouping supports.
	app_state_inventory.call("_on_packet", 79, PackedByteArray([1, 0x5b, 0]))
	await process_frame
	var blessing: Array = main.get("world_effects") as Array
	var blessing_burst: GPUParticles3D = (blessing[blessing.size() - 1]
		as WorldEffect3D).get_node_or_null("EffectBurst") as GPUParticles3D
	var harm_material: ParticleProcessMaterial = (effect_burst.process_material
		as ParticleProcessMaterial)
	var blessing_material: ParticleProcessMaterial = (
		blessing_burst.process_material as ParticleProcessMaterial)
	_expect(harm_material.gravity.y < 0.0 and blessing_material.gravity.y > 0.0,
		"the two classes move differently rather than sharing one burst")
	_expect(not harm_material.color_ramp.gradient.get_color(0).is_equal_approx(blessing_material.color_ramp.gradient.get_color(0)),
		"and they are told apart by colour")
	# An actor the client has never been told about has no position.
	var known_effects: int = (main.get("world_effects") as Array).size()
	app_state_inventory.call("_on_packet", 79, PackedByteArray([2, 0xff, 0x7f]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() == known_effects,
		"an effect at an unknown actor is not guessed at a position")
	app_state_inventory.call("_on_packet", 6, PackedByteArray([0x5b, 0]))
	await process_frame

	# Ranged combat: the aim the server states, and the arrow it looses.
	app_state_inventory.call("_on_packet", 51, _hex_bytes(
		"5b00020004000000000001000001020304050b001e14071400120001416c696365"
		+ "000040ff0600"))
	app_state_inventory.call("_on_packet", 51, _hex_bytes(
		"4d00060004000000000001000001020304050b001e1407140012000142657373"
		+ "000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var missiles_before: int = (main.get("world_effects") as Array).size()
	app_state_inventory.call("_on_packet", 84, PackedByteArray([0x5b, 0, 0x4d, 0]))
	await process_frame
	var shooter: Dictionary = (app_state_inventory.get("actors")
		as Dictionary).get(91, {}) as Dictionary
	_expect(int(shooter.get("aiming_at", -1)) == 77,
		"an aim is kept on the actor it describes")
	_expect((main.get("world_effects") as Array).size() == missiles_before,
		"aiming draws no arrow: nothing has been loosed yet")
	app_state_inventory.call("_on_packet", 86, PackedByteArray([0x5b, 0, 0x4d, 0]))
	await process_frame
	var after_shot: Array = main.get("world_effects") as Array
	_expect(after_shot.size() == missiles_before + 1
		and after_shot[after_shot.size() - 1] is MissileFlight3D,
		"loosing draws an arrow between the two actors")
	var arrow: MissileFlight3D = after_shot[after_shot.size() - 1] as MissileFlight3D
	_expect(arrow.origin.distance_to(arrow.destination) > 1.0
		and arrow.get_node_or_null("Shaft") != null,
		"the arrow flies from one actor to the other")
	shooter = (app_state_inventory.get("actors") as Dictionary).get(91, {}) as Dictionary
	_expect(int(shooter.get("aiming_at", -1)) == -1,
		"loosing ends the aim the server stated before it")
	# Objects the server puts into a map that is already being played in.
	# Everything the client knew about a map used to arrive with the map.
	var placed_before: int = (main.get("placed_object_nodes") as Dictionary).size()
	var totem := PackedByteArray([7, 0, 0x00, 0x03, 0xe6, 0x01, 0, 0])
	totem.append_array(_nul_bytes("boss_totem"))
	app_state_inventory.call("_on_packet", 75, totem)
	await process_frame
	var placed_nodes: Dictionary = main.get("placed_object_nodes") as Dictionary
	_expect(placed_nodes.size() == placed_before + 1 and placed_nodes.has(7)
		and placed_nodes[7] is PlacedObject3D,
		"an object raised mid-game is drawn: %d" % placed_nodes.size())
	_expect(str((placed_nodes[7] as PlacedObject3D).model) == "boss_totem"
		and PlacedObject3D.shape_name_for("boss_totem") == "totem",
		"and a name that says what it is gets the shape it names")
	_expect(PlacedObject3D.shape_name_for("3dobjects/misc/unknowable.e3d")
			== "marker",
		"a name this client has no shape for is still something visible")
	app_state_inventory.call("_on_packet", 76, PackedByteArray([7, 0]))
	await process_frame
	_expect(not (main.get("placed_object_nodes") as Dictionary).has(7),
		"and an object the server takes away goes")

	# A list is the whole truth about a map, so it replaces rather than adds.
	var listed := PackedByteArray([2, 0, 1, 0, 0x00, 0x03, 0xe6, 0x01, 0, 0])
	listed.append_array(_nul_bytes("totem"))
	listed.append_array(PackedByteArray([2, 0, 0x04, 0x03, 0xe6, 0x01, 0, 0]))
	listed.append_array(_nul_bytes("banner"))
	app_state_inventory.call("_on_packet", 74, listed)
	await process_frame
	_expect((app_state_inventory.get("world_objects") as Dictionary).size() == 2,
		"a list states everything already standing on the map")
	var single := PackedByteArray([9, 0, 0x00, 0x03, 0xe6, 0x01, 0, 0])
	single.append_array(_nul_bytes("stone"))
	app_state_inventory.call("_on_packet", 74, PackedByteArray([1, 0])
		+ single)
	await process_frame
	_expect((app_state_inventory.get("world_objects") as Dictionary).size() == 1
		and (app_state_inventory.get("world_objects") as Dictionary).has(9),
		"and a later list replaces it rather than adding to it")
	app_state_inventory.call("_on_packet", 74, PackedByteArray([0, 0]))
	await process_frame
	_expect((main.get("placed_object_nodes") as Dictionary).is_empty(),
		"an empty list clears the map")
	_expect(EloriaProtocol.decode_server(74, PackedByteArray([9, 0])).type
			== "invalid",
		"a list that promises more objects than it carries is rejected")

	# Where the ways off this map are, and both ends of a teleport.
	var ways := PackedByteArray([2, 0, 0x00, 0x03, 0xe6, 0x01,
		0x04, 0x03, 0xe6, 0x01])
	app_state_inventory.call("_on_packet", 10, ways)
	await process_frame
	_expect((app_state_inventory.get("teleporters") as Array).size() == 2,
		"the map says where its portals are")
	app_state_inventory.call("_on_packet", 10, PackedByteArray([0, 0]))
	await process_frame
	_expect((app_state_inventory.get("teleporters") as Array).is_empty(),
		"and a map with none says that too")
	_expect(EloriaProtocol.decode_server(10, PackedByteArray([1, 0, 2, 0])).type
			== "invalid",
		"a teleporter list of the wrong length is rejected")
	var before_teleport: int = (main.get("world_effects") as Array).size()
	app_state_inventory.call("_on_packet", 12,
		PackedByteArray([0x00, 0x03, 0xe6, 0x01]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() == before_teleport + 1,
		"an arrival is drawn where it happened")
	app_state_inventory.call("_on_packet", 13,
		PackedByteArray([0x00, 0x03, 0xe6, 0x01]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() == before_teleport + 2,
		"and so is a departure")

	# Which quest a piece of NPC dialogue belongs to. Before this the client
	# could not tell a quest line from small talk, so neither could a player.
	var dialogue_panel: Control = main.get("dialogue_panel") as Control
	var dialogue_name: Label = main.get("dialogue_name") as Label
	app_state_inventory.call("_on_packet", 30, _nul_bytes("Just passing through."))
	await process_frame
	_expect(dialogue_panel.visible
		and not bool((app_state_inventory.get("npc_dialogue") as Dictionary).get(
			"quest", true))
		and not dialogue_name.text.contains("Quest"),
		"unflagged dialogue is small talk: " + dialogue_name.text)
	app_state_inventory.call("_on_packet", 92, PackedByteArray([]))
	app_state_inventory.call("_on_packet", 93, PackedByteArray([2, 0]))
	app_state_inventory.call("_on_packet", 30, _nul_bytes("Find the reed bank."))
	await process_frame
	var flagged: Dictionary = app_state_inventory.get("npc_dialogue") as Dictionary
	_expect(bool(flagged.get("quest", false)) and int(flagged.get("quest_id", 0)) == 2
		and dialogue_name.text.contains("Quest 2"),
		"flagged dialogue names the quest it belongs to: " + dialogue_name.text)
	app_state_inventory.call("_on_packet", 30, _nul_bytes("Anyway, good day."))
	await process_frame
	_expect(not bool((app_state_inventory.get("npc_dialogue") as Dictionary).get(
			"quest", true)),
		"the flag describes one line, so the next line is small talk again")
	app_state_inventory.call("_on_packet", 94, PackedByteArray([2, 0]))
	await process_frame
	_expect((app_state_inventory.get("finished_quests") as Array).has(2)
		and int(app_state_inventory.get("current_quest_id")) == 0,
		"a finished quest is recorded and stops being the current one")
	app_state_inventory.call("_on_packet", 94, PackedByteArray([2, 0]))
	await process_frame
	_expect((app_state_inventory.get("finished_quests") as Array).size() == 1,
		"and finishing it twice records it once")

	# An arrow going to a place rather than into somebody: a practice shot, or
	# a miss. Where it lands is the server's decision arriving on the wire, so
	# two clients watching one shot draw the same arrow.
	var before_ground: int = (main.get("world_effects") as Array).size()
	app_state_inventory.call("_on_packet", 85,
		PackedByteArray([0x5b, 0, 0x3c, 0, 0x3c, 0]))
	await process_frame
	shooter = (app_state_inventory.get("actors") as Dictionary).get(91, {}) as Dictionary
	_expect(int(shooter.get("aiming_at", 0)) == -1
		and (shooter.get("aiming_at_tile", Vector2i.ZERO) as Vector2i)
			== Vector2i(60, 60),
		"aiming at a place is kept on the shooter and names the tile: %s"
			% str(shooter.get("aiming_at_tile")))
	_expect((main.get("world_effects") as Array).size() == before_ground,
		"and draws no arrow, because nothing has been loosed")
	app_state_inventory.call("_on_packet", 87,
		PackedByteArray([0x5b, 0, 0x3c, 0, 0x3c, 0]))
	await process_frame
	var ground_effects: Array = main.get("world_effects") as Array
	_expect(ground_effects.size() == before_ground + 1
		and ground_effects[ground_effects.size() - 1] is MissileFlight3D,
		"loosing at a place draws an arrow to it")
	shooter = (app_state_inventory.get("actors") as Dictionary).get(91, {}) as Dictionary
	_expect(int(shooter.get("aiming_at", 0)) == -1 and not shooter.has("aiming_at_tile"),
		"and the aim at that place ends with it")
	# A shot from an actor the client has never been told about draws nothing.
	app_state_inventory.call("_on_packet", 87,
		PackedByteArray([0xff, 0x7f, 0x3c, 0, 0x3c, 0]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() == before_ground + 1,
		"a ground shot from an unknown actor draws nothing")

	# An arrow at an actor the client has never been told about is not guessed.
	var before_unknown: int = (main.get("world_effects") as Array).size()
	app_state_inventory.call("_on_packet", 86, PackedByteArray([0x5b, 0, 0xff, 0x7f]))
	await process_frame
	_expect((main.get("world_effects") as Array).size() == before_unknown,
		"a shot at an unknown actor draws nothing")
	app_state_inventory.call("_on_packet", 6, PackedByteArray([0x5b, 0]))
	app_state_inventory.call("_on_packet", 6, PackedByteArray([0x4d, 0]))
	await process_frame

	# Guild tags. The tag arrives inside the actor's display name, so a client
	# that takes the whole string as a name shows the tag as part of it.
	app_state_inventory.call("_on_packet", 51, _hex_bytes(
		"5b000203e1010000000001000001020304050b001e14071400120001416c6963652083"
		+ "454c4f000040ff0600"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var tagged_actor: Dictionary = (app_state_inventory.get("actors")
		as Dictionary).get(91, {}) as Dictionary
	_expect(str(tagged_actor.get("name", "")) == "Alice"
		and str(tagged_actor.get("guild_tag", "")) == "ELO",
		"the reducer keeps the name and the tag apart")
	var tagged_node: Node3D = (main.get("actor_nodes")
		as Dictionary).get(91) as Node3D
	var plate: Label3D = (tagged_node.get_node_or_null("Nameplate")
		as Label3D) if tagged_node != null else null
	_expect(plate != null and plate.text.contains("Alice")
		and plate.text.contains("[ELO]"),
		"the nameplate draws the tag as a tag: "
			+ (plate.text if plate != null else "no nameplate"))
	# The server coloured Alice's tag but not her name, so the plate is left
	# white rather than taking the palette's index 0.
	_expect(plate != null and plate.modulate.is_equal_approx(Color.WHITE),
		"a name the server did not colour stays white")
	app_state_inventory.call("_on_packet", 6, PackedByteArray([91, 0]))
	await process_frame

	# Name colours. The server puts them in front of the name as `127 + index`
	# and they are the only thing that says, without a click, that a player is
	# a demigod (c_green3) or that a creature belongs to an invasion (c_red3).
	app_state_inventory.call("_on_packet", 51, _hex_bytes(
		"5c000203e1010000000001000001020304050b001e14071400"
		+ "12000190426f62000040ff0600"))
	app_state_inventory.call("_on_packet", 1, _hex_bytes(
		"5d000203e10100000000cc0720002000018d456d626572666f7800"))
	await process_frame
	main.call("_sync_world")
	await process_frame
	var demigod_plate: Label3D = _nameplate_of(main, 92)
	_expect(demigod_plate != null and demigod_plate.text == "Bob"
		and demigod_plate.modulate.is_equal_approx(EloriaProtocol.EL_TEXT_COLOURS[17]),
		"a demigod's nameplate is green, and the colour byte is not in the name")
	var invasion_plate: Label3D = _nameplate_of(main, 93)
	_expect(invasion_plate != null and invasion_plate.text == "Emberfox"
		and invasion_plate.modulate.is_equal_approx(EloriaProtocol.EL_TEXT_COLOURS[14]),
		"an invasion creature's nameplate is red")
	# You are given no nameplate of your own, so your own name colour has only
	# the overhead banner to show in.
	var before_colour_local: int = int(app_state_inventory.get("local_actor_id"))
	app_state_inventory.set("local_actor_id", 92)
	main.call("_sync_world")
	await process_frame
	var banner_name: Label = main.get("overhead_player_name") as Label
	_expect(banner_name != null and banner_name.text == "Bob"
		and banner_name.get_theme_color("font_color").is_equal_approx(
			EloriaProtocol.EL_TEXT_COLOURS[17]),
		"your own demigod name is green on the overhead banner")
	app_state_inventory.set("local_actor_id", before_colour_local)
	main.call("_sync_world")
	await process_frame
	app_state_inventory.call("_on_packet", 6, PackedByteArray([92, 0]))
	app_state_inventory.call("_on_packet", 6, PackedByteArray([93, 0]))
	await process_frame

	# Twelve spell quick slots.
	_expect((main.get("spell_slot_buttons") as Array).size() == 12,
		"the quickbar has twelve spell slots, not six")
	# Eternal Lands binds K_SPELL1..12 to Alt with the number row, ending on
	# the two keys right of zero (keys.c). Every slot carries that modifier,
	# and slot 12 is checked by name because it is the odd one.
	var spell_keys: Array[int] = [KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6,
		KEY_7, KEY_8, KEY_9, KEY_0, KEY_MINUS, KEY_EQUAL]
	for slot: int in range(1, 13):
		_expect(InputMap.has_action("quick_spell_%d" % slot),
			"quick_spell_%d is a rebindable action" % slot)
		var bound: Array[InputEvent] = InputMap.action_get_events(
			"quick_spell_%d" % slot)
		var key_event: InputEventKey = (bound[0] if not bound.is_empty()
			else null) as InputEventKey
		_expect(key_event != null and key_event.alt_pressed
				and not key_event.shift_pressed
				and key_event.physical_keycode == spell_keys[slot - 1],
			"quick_spell_%d is Alt+%s" % [slot, OS.get_keycode_string(
				spell_keys[slot - 1])])
	_expect(main.call("_spell_slot_shortcut", 11) == "Alt+=",
		"the twelfth slot's tooltip names the key it is on: %s"
			% str(main.call("_spell_slot_shortcut", 11)))
	# Pick points are spent from the statistics window. Everything it offers
	# is the server's word: the points come from the stats packet, the perks
	# and their prices from the catalogue, and a perk it refuses carries the
	# server's own refusal rather than a Take button. Both rows carry the two
	# tier bytes the catalogue has sent since perk_catalog_v2 - held tier
	# and tiers in all - and the category perk_catalog_v3 added, so this is
	# the layout the decoder accepts today.
	app_state_inventory.set("stats", {"physique": 4, "physique_base": 4,
		"magic_nexus": 0, "magic_nexus_base": 0, "overall": 10,
		"pickpoints_earned": 10, "pickpoints_spent": 0})
	app_state_inventory.call("_on_packet", 215, ("02000500c80000000001457863617661746f72005477696365206173206d616e79206974656d732e00005574696c69747900fdff000000000001506f7765722048756e677279004c6f7365203320666f6f6420706572206d696e7574652e00596f7520616c726561647920686176652074686174207065726b2e00436f6d62617400").hex_decode())
	await process_frame
	var perk_rows: VBoxContainer = main.get("perk_rows") as VBoxContainer
	# A row is a framed panel now rather than a bare box, and the filter tabs
	# live above the list, so the count here is still one child per perk.
	_expect(perk_rows != null and perk_rows.get_child_count() == 2,
		"the perks tab lists every perk the server offers: %d"
			% (perk_rows.get_child_count() if perk_rows != null else -1))
	# Every row is looked up with get_node_or_null: a catalogue that failed to
	# draw is one reported failure, not a crash that takes the rest of the run
	# down with it.
	# A row is a framed panel holding one line: the name and what it does on
	# the left, the tier boxes, the price, then the button. Every lookup is
	# get_node_or_null, so a catalogue that failed to draw is one reported
	# failure rather than a crash that takes the rest of the run with it.
	var excavator_take: Button = _perk_part(perk_rows, "PerkExcavator",
		"Take") as Button
	var excavator_price: Label = _perk_part(perk_rows, "PerkExcavator",
		"Price") as Label
	var excavator_text: String = (excavator_price.text
		if excavator_price != null else "<no row>")
	_expect(excavator_take != null and not excavator_take.disabled,
		"a perk the server does not refuse can be taken")
	_expect(excavator_text.contains("5 PP") and excavator_text.contains("200"),
		"a perk states what it costs in points and gold: " + excavator_text)
	var hungry_take: Button = _perk_part(perk_rows, "PerkPowerHungry",
		"Take") as Button
	var hungry_price: Label = _perk_part(perk_rows, "PerkPowerHungry",
		"Price") as Label
	_expect(hungry_take != null and hungry_take.disabled
			and hungry_take.tooltip_text == "You already have that perk.",
		"a refused perk is disabled and quotes the server: "
			+ (hungry_take.tooltip_text if hungry_take != null else "<no row>"))
	var hungry_text: String = (hungry_price.text
		if hungry_price != null else "<no row>")
	_expect(hungry_text.contains("+3 PP"),
		"a perk with a negative cost is shown as paying points out: "
			+ hungry_text)
	var perk_summary: Label = main.get("perk_summary") as Label
	_expect(perk_summary != null and perk_summary.text.contains("10"),
		"the tab says how many pick points are unspent: "
			+ (perk_summary.text if perk_summary != null else "<no label>"))

	# Plus previews a point within the server's budget and ceilings.
	(main.get_node("GameView/StatsPanel") as Control).show()
	main.call("_sync_stats")
	# The control is a button on the row now rather than a link in a
	# document, and it is always drawn - what changes is whether it is live.
	_expect(_spend_live(main, "physique") and _spend_live(main, "magic_nexus"),
		"an attribute and a nexus below their ceilings can be raised")
	app_state_inventory.set("stats", {"magic_nexus": 0, "magic_nexus_base": 0,
		"overall": 10, "pickpoints_earned": 10, "pickpoints_spent": 10})
	main.call("_sync_stats")
	_expect(not _spend_live(main, "physique")
			and not _spend_live(main, "magic_nexus"),
		"with nothing left to spend, nothing offers to spend it")
	app_state_inventory.set("stats", {"magic_nexus": 10, "magic_nexus_base": 10,
		"overall": 10, "pickpoints_earned": 10, "pickpoints_spent": 0})
	main.call("_sync_stats")
	_expect(not _spend_live(main, "magic_nexus"),
		"a nexus at the server's ceiling is not offered again")
	(main.get_node("GameView/StatsPanel") as Control).hide()
	main.call("_ask_to_spend", "attribute", "physique")
	var confirm: PanelContainer = main.get("purchase_confirm") as PanelContainer
	_expect(not confirm.visible and int((main.get("_pickpoint_draft") as Dictionary).get("attribute:physique", 0)) == 1,
		"plus previews the purchase without a popup")
	main.call("_adjust_pickpoint", "attribute", "physique", -1)
	_expect((main.get("_pickpoint_draft") as Dictionary).is_empty(),
		"minus removes the unconfirmed purchase")

	# Spell power. Both the preferred power and the ceiling are the server's;
	# the client asks for a power and never works a limit out from a level.
	var power_value: Label = main.get_node(
		"GameView/SpellQuickbar/SpellContent/SpellControls/SpellPowerValue") as Label
	var power_up: Button = main.get_node(
		"GameView/SpellQuickbar/SpellContent/SpellControls/SpellPowerUp") as Button
	var power_down: Button = main.get_node(
		"GameView/SpellQuickbar/SpellContent/SpellControls/SpellPowerDown") as Button
	main.call("_sync_spells")
	await process_frame
	_expect(power_value.text == "P1" and power_up.disabled and power_down.disabled,
		"with no stated limit the stepper offers nothing to choose")
	_expect(int(main.call("_cast_power_for", 3)) == 0,
		"a cast with no stated limit sends the legacy frame, with no power byte")
	# shield: preferred 1 of 4; heal: preferred 3 of 3.
	var power_payload := PackedByteArray([2, 0, 1, 4])
	power_payload.append_array(_nul_bytes("shield"))
	power_payload.append_array(PackedByteArray([3, 3]))
	power_payload.append_array(_nul_bytes("heal"))
	app_state_inventory.call("_on_packet", 231, power_payload)
	await process_frame
	_expect(not power_up.disabled and power_down.disabled,
		"the stepper opens up to the highest limit the server stated")
	main.call("_on_spell_power_up_pressed")
	main.call("_on_spell_power_up_pressed")
	main.call("_on_spell_power_up_pressed")
	main.call("_on_spell_power_up_pressed")
	await process_frame
	_expect(power_value.text == "P4" and power_up.disabled,
		"the stepper stops at the server's ceiling: " + power_value.text)
	_expect(int(main.call("_cast_power_for", 3)) == 4
		and int(main.call("_cast_power_for", 0)) == 3,
		"each cast is clamped to the limit the server stated for its effect")
	var shield_tooltip: String = str(main.call("_spell_tooltip",
		main.get("spell_catalog").call("spell", 3), [] as Array[String], 0))
	_expect(shield_tooltip.contains("Power 4 of 4"),
		"the spell tooltip states the power and the ceiling: " + shield_tooltip)
	main.call("_on_spell_power_down_pressed")
	main.call("_on_spell_power_down_pressed")
	main.call("_on_spell_power_down_pressed")
	await process_frame
	_expect(power_value.text == "P1" and power_down.disabled,
		"the stepper stops at one")

	# Active effects. The server states which buffs are on and for how long;
	# the strip counts down to the moment it stated and shows nothing else.
	var buff_bar: Control = main.get("active_buff_bar") as Control
	var buff_row: HBoxContainer = buff_bar.get_node("ActiveBuffRow") as HBoxContainer
	_expect(buff_row.get_child_count() == 0, "the effect strip starts empty")
	# Buff 0 for 128 seconds, then buff 22 for 90.
	app_state_inventory.call("_on_packet", 44, PackedByteArray([0, 128]))
	app_state_inventory.call("_on_packet", 44, PackedByteArray([22, 90]))
	await process_frame
	_expect((buff_bar.call("shown_buff_ids") as Array) == [0, 22],
		"both effects the server reported are on the strip")
	var first: Control = buff_row.get_child(0) as Control
	_expect((first.get_node("BuffName") as Label).text == "Shield"
		and (first.get_node("BuffRemaining") as Label).text == "128s"
		and (first.get_node("BuffIcon") as TextureRect).texture != null,
		"an effect is named, iconned and counted down from the server's duration")
	var strip_rect: Rect2 = buff_row.get_global_rect()
	_expect(strip_rect.position.x >= 0.0 and strip_rect.position.y >= 0.0
		and strip_rect.end.x <= 1280.0 and strip_rect.end.y <= 720.0
		and not strip_rect.intersects(right_stats.get_global_rect()),
		"the effect strip fits 1280x720 clear of the resource rail: %s" % strip_rect)
	app_state_inventory.call("_on_packet", 46, PackedByteArray([0]))
	await process_frame
	_expect((buff_bar.call("shown_buff_ids") as Array) == [22],
		"the server removing an effect takes it off the strip")
	# A resync list restates the whole set without durations.
	app_state_inventory.call("_on_packet", 45, PackedByteArray([
		1, 3, 255, 255, 255, 255, 255, 255, 255, 255]))
	await process_frame
	_expect((buff_bar.call("shown_buff_ids") as Array) == [1, 3]
		and (buff_row.get_child(0).get_node("BuffRemaining") as Label).text.is_empty(),
		"a resync replaces the set, and states no time to count down")
	# An effect whose stated time has run out leaves without another packet.
	app_state_inventory.call("_on_packet", 46, PackedByteArray([1]))
	app_state_inventory.call("_on_packet", 46, PackedByteArray([3]))
	app_state_inventory.call("_on_packet", 44, PackedByteArray([0, 0]))
	await process_frame
	await process_frame
	_expect((buff_bar.call("shown_buff_ids") as Array).is_empty(),
		"an effect the server said would last no time is not shown as active")

	# Looking at another player. The reply is one packet that names the actor,
	# so the window is the server's answer rather than a request the client
	# remembered making.
	var info_layer: Control = main.get("player_info_panel") as Control
	var info_panel: PanelContainer = info_layer.get_node("PlayerInfo") as PanelContainer
	_expect(not info_panel.visible, "the player-info window starts closed")
	var described := PackedByteArray([0x5b, 0x00, 0x01, 0x00])
	described.append_array(_nul_bytes("Alice"))
	described.append_array(_nul_bytes("Beginner Tutorial"))
	app_state_inventory.call("_on_packet", 228, described)
	await process_frame
	_expect(info_panel.visible
		and (info_layer.get("title") as Label).text == "Alice"
		and (info_layer.get("body") as RichTextLabel).text.contains(
			"Beginner Tutorial"),
		"the window names the player the server described and what they earned")
	var info_rect: Rect2 = info_panel.get_global_rect()
	_expect(info_rect.position.x >= 0.0 and info_rect.position.y >= 0.0
		and info_rect.end.x <= 1280.0 and info_rect.end.y <= 720.0
		and not info_rect.intersects(right_stats.get_global_rect()),
		"the player-info window fits 1280x720 clear of the resource rail: %s"
			% info_rect)
	var cancel_event: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	cancel_event.pressed = true
	main.call("_unhandled_input", cancel_event)
	await process_frame
	_expect(not info_panel.visible,
		"cancel closes the player-info window like every other panel")
	var empty := PackedByteArray([0x5b, 0x00, 0x00, 0x00])
	empty.append_array(_nul_bytes("Alice"))
	app_state_inventory.call("_on_packet", 228, empty)
	await process_frame
	_expect(info_panel.visible
		and not (info_layer.get("body") as RichTextLabel).text.contains(
			"Beginner Tutorial"),
		"a player with nothing earned is described as such, not left stale")
	app_state_inventory.call("close_player_info")
	await process_frame

	# The console's own commands, routed through the real chat submit path.
	var chat_input_line: LineEdit = main.get_node("%ChatInput") as LineEdit
	var chat_lines_before: int = (app_state_inventory.get("chat_lines") as Array).size()
	main.call("_show_chat_input")
	main.call("_on_chat_submitted", "#help")
	await process_frame
	_expect((app_state_inventory.get("chat_lines") as Array).size()
			> chat_lines_before
		and chat_input_line.text.is_empty(),
		"a command the client answers writes its reply locally and clears the box")
	_expect(chat_input_line.visible and not chat_input_line.has_focus(),
		"submitting a local command keeps the footer and releases keyboard input")
	main.call("_on_chat_submitted", "#markpos 770 481 Reed bank")
	await process_frame
	var console: ConsoleCommands = main.get("console_commands") as ConsoleCommands
	_expect(console.marks.size() == 1,
		"the mark the player made is kept by the client")
	var overlay_marks: Array = (main.get("map_marker_overlay")
		as Control).get("_player_marks") as Array
	_expect(overlay_marks.size() <= 1,
		"the player's marks reach the map overlay, filtered by map")
	# History and completion.
	chat_input_line.text = "#mar"
	main.call("_complete_console_command")
	_expect(chat_input_line.text == "#mark",
		"tab completes as far as the commands agree: " + chat_input_line.text)
	main.call("_recall_console_history", -1)
	_expect(chat_input_line.text == "#markpos 770 481 Reed bank",
		"up recalls the last line sent: " + chat_input_line.text)
	main.call("_recall_console_history", 1)
	_expect(chat_input_line.text.is_empty(),
		"and down returns to an empty box")
	main.call("_on_chat_submitted", "#unmark Reed bank")
	await process_frame

	# Map markers. The server places every one of them and takes every one of
	# them away; nothing here decides a marker has been reached.
	var here: String = EloriaProtocol.map_id_from_reference(
		str(app_state_inventory.get("current_map")))
	var marker_payload := PackedByteArray([0xea, 0x01, 0x0c, 0x03, 0xe1, 0x01])
	marker_payload.append_array(_nul_bytes("./maps/%s.elm" % here))
	marker_payload.append_array(_nul_bytes("Reed bank"))
	app_state_inventory.call("_on_packet", 90, marker_payload)
	var elsewhere := PackedByteArray([0xeb, 0x01, 0x10, 0x00, 0x20, 0x00])
	elsewhere.append_array(_nul_bytes("./maps/somewhere_else.elm"))
	elsewhere.append_array(_nul_bytes("Another map"))
	app_state_inventory.call("_on_packet", 90, elsewhere)
	await process_frame
	var marker_nodes: Dictionary = main.get("map_marker_nodes") as Dictionary
	_expect((app_state_inventory.get("map_markers") as Dictionary).size() == 2
		and marker_nodes.size() == 1 and marker_nodes.has(490),
		"a marker for another map is held but not drawn here")
	var placed: MapMarker3D = marker_nodes.get(490) as MapMarker3D
	_expect(placed != null and placed.server_tile == Vector2i(780, 481)
		and placed.label == "Reed bank",
		"the marker sits on the tile the server named, with its label")
	var pin: MeshInstance3D = (placed.get_node_or_null("Pin")
		as MeshInstance3D) if placed != null else null
	_expect(pin != null and pin.layers == MapMarker3D.MAP_MARKER_LAYER,
		"the large pin stays on the full map")
	var world_label: Label3D = placed.get_node_or_null("WorldLabel") as Label3D
	_expect(world_label != null and world_label.layers == MapMarker3D.GAMEPLAY_LAYER
		and world_label.text == "Reed bank", "the marker also labels the gameplay view")
	var marker_sidebar: RichTextLabel = main.get_node(
		"GameView/FullMap/MapLayout/Sidebar/SidebarLayout/SidebarScroll/SidebarContent/MapMarkerList") as RichTextLabel
	_expect(marker_sidebar.visible and marker_sidebar.text.contains("Reed bank")
		and marker_sidebar.text.contains("780") and marker_sidebar.text.contains("481"),
		"the map sidebar names the marker and its tile, which no pin drawn at"
			+ " full-map scale could: " + marker_sidebar.text)
	var overlay: Control = main.get("map_marker_overlay") as Control
	_expect((overlay.get("_markers") as Array).size() == 1,
		"the full-map overlay is given the markers for this map and no others")
	app_state_inventory.call("_on_packet", 91, PackedByteArray([0xea, 0x01]))
	await create_timer(0.3).timeout
	await process_frame
	_expect((app_state_inventory.get("map_markers") as Dictionary).size() == 1
		and (main.get("map_marker_nodes") as Dictionary).is_empty()
		and not marker_sidebar.visible
		and (overlay.get("_markers") as Array).is_empty(),
		"the server takes a marker away and the pin, the list and the overlay"
			+ " entry all go with it")

	# A map change discards the previous map's objects rather than leaving
	# pick targets from somewhere else standing in the new world.
	app_state_inventory.call("_on_packet", 7, _nul_bytes("maps/nymara/mirrorhold.elm"))
	await process_frame
	_expect((app_state_inventory.get("map_objects") as Dictionary).is_empty()
		and not bool((app_state_inventory.get("harvest") as Dictionary).get("active", true)),
		"a map change clears the world objects and the harvesting state")
	# GLTFDocument builds runtime textures with no mip chain, which is what made
	# distant roofs and ground swim as the camera moved.
	var fixture_loader := main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/WorldLoader") as WorldLoader
	var load_deadline := Time.get_ticks_msec() + 30000
	while (fixture_loader.world_root == null or fixture_loader.manifest == null
			or fixture_loader.manifest.asset_id() != "mirrorhold") and Time.get_ticks_msec() < load_deadline:
		await process_frame
	_expect(fixture_loader.world_root != null and fixture_loader.manifest != null
		and fixture_loader.manifest.asset_id() == "mirrorhold", "material fixture loads the actual expected map")
	var loaded_world: Node3D = fixture_loader.world_root
	if loaded_world is ContinentChunkStream:
		# CHANGE_MAP alone has no arrival actor packet. Prime the real published
		# spawn so the streamed map actually contains geometry before inspecting it.
		var spawn: Array = fixture_loader.manifest.data["spawnPoints"][0]["position"]
		var arrival := Vector3(float(spawn[0]), float(spawn[1]), float(spawn[2]))
		(loaded_world as ContinentChunkStream).prime(arrival)
		while not (loaded_world as ContinentChunkStream).arrival_resident(arrival) and Time.get_ticks_msec() < load_deadline:
			await process_frame
		_expect((loaded_world as ContinentChunkStream).arrival_resident(arrival), "material fixture has actual arrival chunks")
	var mipped_textures := 0
	var flat_textures := 0
	var anisotropic := 0
	var plain_filter := 0
	if loaded_world != null:
		for node_value: Node in loaded_world.find_children(
				"*", "MeshInstance3D", true, false):
			var world_mesh: Mesh = (node_value as MeshInstance3D).mesh
			if world_mesh == null:
				continue
			for surface: int in range(world_mesh.get_surface_count()):
				var surface_material: BaseMaterial3D = world_mesh.surface_get_material(
					surface) as BaseMaterial3D
				if surface_material == null:
					continue
				if surface_material.texture_filter == 						BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC:
					anisotropic += 1
				else:
					plain_filter += 1
				var albedo: Texture2D = surface_material.albedo_texture
				if albedo == null:
					continue
				var albedo_image: Image = albedo.get_image()
				if albedo_image == null:
					continue
				if albedo_image.has_mipmaps():
					mipped_textures += 1
				else:
					flat_textures += 1
	_expect(anisotropic > 0 and plain_filter == 0,
		"every imported world material samples its textures anisotropically")
	_expect(mipped_textures > 0 and flat_textures == 0,
		"every imported world texture carries a mip chain")
	app_state_inventory.set("authenticated", false)

	# Books. Reading is the other half of the knowledge loop: the catalog, the
	# ownership bitset and the detail pane all worked, but a player could not
	# see that they were reading anything, and the manufacturing resolver
	# reported "unread knowledge" as a blocking reason it had no way to clear.
	var reading_panel: PanelContainer = main.get_node(
		"GameView/ReadingPanel") as PanelContainer
	var reading_title: Label = main.get_node(
		"GameView/ReadingPanel/ReadingContent/ReadingHeader/ReadingTitle") as Label
	var reading_progress: ProgressBar = main.get_node(
		"GameView/ReadingPanel/ReadingContent/ReadingProgress") as ProgressBar
	var reading_detail: RichTextLabel = main.get_node(
		"GameView/ReadingPanel/ReadingContent/ReadingDetail") as RichTextLabel
	app_state_inventory.set("authenticated", true)
	_expect(not reading_panel.visible, "the reading window starts closed")
	# Partial statistics 47/65/66: the book being read, pages done, pages total.
	app_state_inventory.call("_on_packet", 49, PackedByteArray([
		47, 0, 0, 0, 0, 65, 150, 0, 0, 0, 66, 88, 2, 0, 0]))
	await process_frame
	var reading_state: Dictionary = app_state_inventory.get("reading") as Dictionary
	_expect(bool(reading_state.get("active", false))
		and int(reading_state.get("index", -1)) == 0
		and int(reading_state.get("pages_read", 0)) == 150
		and int(reading_state.get("pages_total", 0)) == 600,
		"reading progress is reduced from the authoritative research statistics")
	_expect(reading_panel.visible and reading_title.text.begins_with("Reading ")
		and reading_detail.text.contains("150 of 600")
		and reading_detail.text.contains("25%"),
		"the reading window names the book and its progress: " + reading_title.text)
	_expect(is_equal_approx(reading_progress.value, 150.0)
		and is_equal_approx(reading_progress.max_value, 600.0),
		"the progress bar is driven by the server's page counts")
	var reading_rect: Rect2 = reading_panel.get_global_rect()
	_expect(reading_rect.position.x >= 0.0 and reading_rect.position.y >= 0.0
		and reading_rect.end.x <= 1280.0 and reading_rect.end.y <= 720.0,
		"the reading window fits within 1280x720: %s" % reading_rect)
	_expect(not reading_rect.intersects(right_stats.get_global_rect()),
		"the reading window does not cover the fixed resource rail")

	# A recipe gated on that knowledge is blocked until the bit arrives.
	var manufacturing: RefCounted = main.get("manufacturing_catalog") as RefCounted
	var gated_index: int = -1
	for recipe_index: int in range(200):
		var definition: Dictionary = manufacturing.call("recipe", recipe_index) as Dictionary
		if definition.is_empty():
			break
		if int(definition.get("knowledgeIndex", -1)) == 0:
			gated_index = recipe_index
			break
	if gated_index >= 0:
		var known: Array[int] = []
		var blocked: Dictionary = manufacturing.call("availability", gated_index,
			{}, known, {"food": 10, "ether": 10}) as Dictionary
		var unblocked_known: Array[int] = [0]
		var unblocked: Dictionary = manufacturing.call("availability", gated_index,
			{}, unblocked_known, {"food": 10, "ether": 10}) as Dictionary
		var blocked_reasons: Array = blocked.get("reasons", []) as Array
		var unblocked_reasons: Array = unblocked.get("reasons", []) as Array
		var had_knowledge_reason := false
		for reason: Variant in blocked_reasons:
			if str(reason).begins_with("Unread knowledge"):
				had_knowledge_reason = true
		var still_has_knowledge_reason := false
		for reason: Variant in unblocked_reasons:
			if str(reason).begins_with("Unread knowledge"):
				still_has_knowledge_reason = true
		_expect(had_knowledge_reason and not still_has_knowledge_reason,
			"the knowledge that finishing a book grants clears the recipe's block")

	# Finishing: the server reports reading nothing, and the knowledge bit
	# arrives as its own packet rather than being assumed from completion.
	app_state_inventory.call("_on_packet", 56, PackedByteArray([0, 0]))
	app_state_inventory.call("_on_packet", 49, PackedByteArray([
		47, 0, 4, 0, 0, 65, 0, 0, 0, 0, 66, 0, 0, 0, 0]))
	await process_frame
	_expect(not bool((app_state_inventory.get("reading") as Dictionary).get("active", true)),
		"the reading state clears when the server reports reading nothing")
	_expect(reading_panel.visible and reading_title.text.begins_with("Finished ")
		and reading_detail.text.contains("Knowledge gained"),
		"finishing a book reports the knowledge it granted")
	_expect((app_state_inventory.get("known_knowledge") as Array).has(0),
		"the knowledge bit is set from the server packet, not inferred")
	main.call("_on_reading_close_pressed")
	_expect(not reading_panel.visible, "the reading window can be dismissed")
	app_state_inventory.set("authenticated", false)

	# The world-load path is safe while actors are being torn down. Anything
	# that frees an actor node outside the actor map leaves a dangling entry,
	# and calling queue_free() on that crashed the engine rather than raising -
	# which is what made a late _on_world_loaded call in this suite segfault.
	var dangling_actor := ReplicatedActor3D.new()
	dangling_actor.actor_id = 5150
	main.get_node("GameView/ViewportContainer/Viewport/WorldRoot").add_child(
		dangling_actor)
	var actor_nodes: Dictionary = main.get("actor_nodes") as Dictionary
	actor_nodes[5150] = dangling_actor
	dangling_actor.free()
	(app_state_inventory.get("actors") as Dictionary).clear()
	main.call("_sync_world")
	_expect(not actor_nodes.has(5150),
		"a dangling actor entry is dropped rather than freed a second time")
	main.call("_load_server_map")
	_expect(true, "the world-load path survives a dangling actor entry")

	_expect(await ContinentChunkStream.drain_workers(self), "world fixture drains actual chunk import workers before exit")
	print("world input tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

func _sized_bytes(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	var sized: PackedByteArray = PackedByteArray([bytes.size()])
	sized.append_array(bytes)
	return sized

## What one counter row of the rebuilt window reads, labels and numbers run
## together. The row is built from controls now, so there is no document to
## search - the text has to be gathered from the labels themselves.
func _counter_row_text(main: Node, counter: String) -> String:
	var body: VBoxContainer = main.get("counter_body") as VBoxContainer
	if body == null:
		return ""
	var wanted: String = "Counter%s" % counter.replace(" ", "")
	for table: Node in body.get_children():
		for row: Node in table.get_children():
			if row.name != wanted:
				continue
			var text: String = ""
			for cell: Node in row.get_children():
				if cell is Label:
					text += " " + (cell as Label).text
			return text
	return ""

## Everything the character column reads, labels and values run together.
## It is built from controls now, so there is no document to search.
func _character_column_text(main: Node) -> String:
	var body: VBoxContainer = main.get("stats_character") as VBoxContainer
	if body == null:
		return ""
	var text: String = ""
	for row: Node in body.get_children():
		if row is Label:
			text += " " + (row as Label).text
			continue
		for cell: Node in row.get_children():
			if cell is Label:
				text += " " + (cell as Label).text
	return text

## One part of a perk row. The row is a framed panel holding a single line,
## so the parts sit one level further in than they did.
func _perk_part(rows: VBoxContainer, row_name: String, part: String) -> Node:
	if rows == null:
		return null
	var frame: Node = rows.get_node_or_null(row_name)
	if frame == null:
		return null
	return frame.get_node_or_null("Row/%s" % part)

## Whether the control beside an attribute or nexus line is live. It is always
## drawn - a button that vanished when it stopped being usable would make the
## column jump about - so what is asked is whether it can be pressed.
func _spend_live(main: Node, key: String) -> bool:
	var body: VBoxContainer = main.get("stats_character") as VBoxContainer
	if body == null:
		return false
	var row: Node = body.get_node_or_null("Row%s" % key)
	if row == null:
		return false
	var button: Button = row.get_node_or_null("Spend") as Button
	return button != null and not button.disabled

func _nul_bytes(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	bytes.append(0)
	return bytes

## What a left click on an actor does, held against what the pointer over it
## promised. They disagreed on the case this file exists to cover: the sword
## was drawn over every live creature, and only attack mode or a held Alt
## actually swung, so a player already fighting one creature could click
## another of the crowd on them all day and nothing happened - no attack, no
## refusal from the server, no way to change target.
func _check_actor_click_actions(main: Control) -> void:
	var previous_mode: String = str(main.get("_interaction_mode"))
	var creature := {"actor_id": 77, "name": "Moss Bear", "kind": 3,
		"health": 330, "max_health": 330, "alive": true}
	var dead_creature := {"actor_id": 78, "name": "Moss Bear", "kind": 3,
		"health": 0, "max_health": 330, "alive": false}
	var player := {"actor_id": 88, "name": "Alice", "kind": 1, "health": 20,
		"max_health": 20, "alive": true}
	var npc := {"actor_id": 99, "name": "Tanner", "kind": 2, "health": 20,
		"max_health": 20, "alive": true}
	var summon := {"actor_id": 66, "name": "Bear", "kind": 5, "health": 40,
		"max_health": 40, "alive": true,
		"name_colour": ReplicatedActor3D.SUMMON_NAME_COLOUR}
	main.set("_interaction_mode", "walk")
	_expect(str(main.call("_actor_click_action", 77, creature, false)) == "attack",
		"a plain click on a live creature attacks it, as the pointer promises")
	_expect(str(main.call("_actor_click_action", 78, dead_creature, false)) == "none",
		"a dead creature is scenery, and a click on it starts no fight")
	_expect(str(main.call("_actor_click_action", 88, player, false)) == "none",
		"a plain click on a player does not attack them")
	_expect(str(main.call("_actor_click_action", 88, player, true)) == "attack",
		"Alt is still what turns a click on a player into a blow")
	_expect(str(main.call("_actor_click_action", 99, npc, false)) == "talk",
		"a plain click greets an NPC")
	_expect(str(main.call("_actor_click_action", 66, summon, false)) == "talk",
		"a plain click orders your own summon rather than attacking it")
	main.set("_interaction_mode", "attack")
	_expect(str(main.call("_actor_click_action", 66, summon, false)) == "attack"
		and str(main.call("_actor_click_action", 88, player, false)) == "attack",
		"attack mode still reaches everything that can be attacked")
	_expect(str(main.call("_actor_click_action", 99, npc, false)) == "none",
		"the selected attack tool does not greet an NPC")
	main.set("_interaction_mode", "walk")
	# The promise and the delivery, side by side, for the same actor: the
	# pointer may only draw the sword where the click sends ATTACK_SOMEONE.
	for case: Array in [["creature", 77, creature], ["creature", 78, dead_creature],
			["player", 88, player], ["npc", 99, npc], ["summon", 66, summon]]:
		for alt: bool in [false, true]:
			var dto: Dictionary = case[2] as Dictionary
			var cursor: int = MouseCursors.choose({"over_world": true,
				"target": str(case[0]), "mode": "walk", "alt": alt,
				"alive": bool(dto.get("alive", true))})
			var action: String = str(main.call(
				"_actor_click_action", int(case[1]), dto, alt))
			_expect((cursor == MouseCursors.ATTACK) == (action == "attack"),
				"the %s pointer%s matches what the click does" % [
					str(case[0]), " with Alt" if alt else ""])
	# Armed trade: the trade glyph only where the click sends TRADE_WITH, and
	# the sword still only where it attacks.
	var dead_player := {"actor_id": 89, "name": "Bess", "kind": 1, "health": 0,
		"max_health": 20, "alive": false}
	main.set("_interaction_mode", "trade")
	_expect(str(main.call("_actor_click_action", 88, player, false)) == "trade",
		"armed trade turns a click on a player into a trade request")
	for case: Array in [["creature", 77, creature], ["creature", 78, dead_creature],
			["player", 88, player], ["player", 89, dead_player], ["npc", 99, npc],
			["summon", 66, summon]]:
		for alt: bool in [false, true]:
			var dto: Dictionary = case[2] as Dictionary
			var cursor: int = MouseCursors.choose({"over_world": true,
				"target": str(case[0]), "mode": "trade", "alt": alt,
				"alive": bool(dto.get("alive", true))})
			var action: String = str(main.call(
				"_actor_click_action", int(case[1]), dto, alt))
			_expect((cursor == MouseCursors.TRADE) == (action == "trade")
				and (cursor == MouseCursors.ATTACK) == (action == "attack"),
				"in trade mode the %s pointer%s matches what the click does (%d, %s)" % [
					str(case[0]) + ("" if bool(dto.get("alive", true)) else " (dead)"),
					" with Alt" if alt else "", cursor, action])
	main.set("_interaction_mode", previous_mode)

## The backpack answers clicks the way Eternal Lands does: at the press, so a
## release that slides onto the next slot loses nothing; a pick-up asks the
## server nothing; an empty slot with nothing in hand does nothing; and a right
## click puts back whatever is in hand before it does anything else. Real mouse
## events go through the viewport, and the packets are read off a local socket.
func _check_item_clicks(main: Control) -> void:
	var state: Node = root.get_node("AppState")
	# Pushed coordinates are window coordinates, so the window has to be the
	# size the interface was laid out for.
	var window_size: Vector2i = root.size
	root.size = Vector2i(1280, 720)
	var inventory_panel: Control = main.get("inventory_panel") as Control
	var was_visible: bool = inventory_panel.visible
	inventory_panel.show()
	inventory_panel.move_to_front()
	main.set("_interaction_mode", "walk")
	main.call("_set_inventory_tool", "grab")
	main.call("_cancel_carry")
	main.set("selected_inventory_slot", -1)
	state.set("inventory", {0: {"image_id": 3, "quantity": 5, "slot": 0, "inventory_usable": true},
		1: {"image_id": 8, "quantity": 2, "slot": 1}})
	main.call("_sync_inventory")
	for frame: int in range(3):
		await process_frame
	var slots: Array = main.get("inventory_slot_buttons") as Array
	var worn: Array = main.get("equipment_slot_buttons") as Array
	var press_mode := true
	for button: Button in slots + worn + (main.get("quick_slot_buttons") as Array) \
			+ (main.get("ground_bag_slot_buttons") as Array):
		press_mode = press_mode and button.action_mode == BaseButton.ACTION_MODE_BUTTON_PRESS
	_expect(press_mode, "backpack, equipment, quickbar and bag slots act on the press")
	var fixture: Dictionary = await _open_fixture()
	if fixture.is_empty():
		return
	var receiver: StreamPeerTCP = fixture["receiver"] as StreamPeerTCP

	var first: Button = slots[0] as Button
	_click(first.get_global_rect().get_center(), true)
	var hovered: Control = root.gui_get_hovered_control()
	_expect(hovered == first, "the press lands on the first backpack slot, not %s"
		% (str(hovered.get_path()) if hovered != null else "nothing"))
	_expect(int(main.get("_carried_slot")) == 0,
		"a backpack item is on the cursor at the press, before any release")
	_click((slots[1] as Button).get_global_rect().get_center(), false)
	_expect(int(main.get("_carried_slot")) == 0 and _take(receiver).is_empty(),
		"a release over the next slot neither places the item nor asks about it")
	main.call("_cancel_carry")
	var edge: Vector2 = Vector2(first.get_global_rect().end.x - 2.0, first.get_global_rect().get_center().y)
	_click(edge, true)
	_click(edge + Vector2(4.0, 0.0), false)
	_expect(int(main.get("_carried_slot")) == 0, "a click whose release jitters over the slot edge still picks up")
	_expect(_take(receiver).is_empty(), "a plain pick-up sends no LOOK_AT_INVENTORY_ITEM")
	_press(slots[4] as Button)
	_expect(_take(receiver) == EloriaProtocol.move_inventory_item(0, 4)
		and int(main.get("_carried_slot")) == -1,
		"the second press places the carried item")
	var second: Button = slots[1] as Button
	_press(second)
	_press(second, true)
	_expect(_take(receiver) == EloriaProtocol.move_inventory_item(1, 36)
		and int(main.get("_carried_slot")) == -1,
		"a double click still wears the item, with nothing left in hand")

	# Nothing in hand and nothing in the slot: nothing happens, whatever was
	# selected before.
	for tool: String in ["inspect", "use", "grab"]:
		main.call("_set_inventory_tool", tool)
		_press(first)
		main.call("_cancel_carry")
		_take(receiver)
		_press(slots[7] as Button)
		_press(worn[2] as Button)
		_expect(_take(receiver).is_empty(),
			"with the %s tool, clicking empty slots afterwards moves nothing" % tool)
	main.call("_set_inventory_tool", "grab")
	main.call("_sync_inventory")
	_expect((slots[7] as Button).tooltip_text.contains("Empty inventory slot")
		and (worn[2] as Button).tooltip_text.contains("Empty generic"),
		"an empty slot promises nothing while nothing is in hand")

	# A right click puts the carry back first; only an empty hand cycles.
	_press(first)
	_button(slots[3] as Button, MOUSE_BUTTON_RIGHT)
	_expect(int(main.get("_carried_slot")) == -1 and str(main.get("_inventory_tool")) == "grab",
		"a right click with an item in hand puts it back and keeps the tool")
	_button(slots[3] as Button, MOUSE_BUTTON_RIGHT)
	_expect(str(main.get("_inventory_tool")) == "use", "with nothing in hand a right click cycles the tool")
	main.call("_set_inventory_tool", "grab")
	_take(receiver)
	main.call("_begin_carry", 0)
	var right := InputEventMouseButton.new()
	right.button_index = MOUSE_BUTTON_RIGHT
	right.pressed = true
	main.call("_on_ground_bag_slot_gui_input", right, 0)
	_expect(int(main.get("_carried_slot")) == -1 and _take(receiver).is_empty(),
		"a right click on a bag slot with an item in hand puts it back without looking")
	main.call("_begin_carry", 0)
	main.call("_on_world_gui_input", right)
	var right_release := InputEventMouseButton.new()
	right_release.button_index = MOUSE_BUTTON_RIGHT
	right_release.pressed = false
	main.call("_on_world_gui_input", right_release)
	_expect(int(main.get("_carried_slot")) == -1, "a right click on the world puts the carried item back")

	_close_fixture(fixture)
	main.call("_cancel_carry")
	main.set("selected_inventory_slot", -1)
	inventory_panel.visible = was_visible
	root.size = window_size
	await process_frame

## The trade icon arms a mode, the way Eternal Lands' does, so it works with
## nobody selected: the pointer then turns to the trade glyph over a player,
## and a click on that player sends TRADE_WITH. Esc, a right click and the walk
## icon put the mode down again. The player stands in the world and is found by
## the production pick ray, the clicks are real mouse events, and the packets
## are read off a local socket.
func _check_trade_mode(main: Control) -> void:
	var state: Node = root.get_node("AppState")
	var window_size: Vector2i = root.size
	root.size = Vector2i(1280, 720)
	var previous_actors: Dictionary = (state.get("actors") as Dictionary).duplicate(true)
	var previous_local: int = int(state.get("local_actor_id"))
	var previous_selected: int = int(state.get("selected_actor_id"))
	var trade_button: Button = main.get("trade_button") as Button
	var container: TextureRect = main.get_node("GameView/ViewportContainer") as TextureRect
	var world_viewport: SubViewport = main.get_node(
		"GameView/ViewportContainer/Viewport") as SubViewport
	var cursors: MouseCursors = main.get("mouse_cursors") as MouseCursors
	# The backpack the item checks left open would take the click.
	var inventory_panel: Control = main.get("inventory_panel") as Control
	var inventory_was_visible: bool = inventory_panel.visible
	inventory_panel.hide()
	state.set("actors", {
		190: {"actor_id": 190, "x": 58, "y": 58, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Ari", "health": 72, "max_health": 100,
			"alive": true, "sitting": false},
		188: {"actor_id": 188, "x": 58, "y": 54, "rotation": 0, "actor_type": 1,
			"kind": 1, "name": "Alice", "health": 90, "max_health": 100,
			"alive": true, "sitting": false}})
	state.set("local_actor_id", 190)
	state.set("selected_actor_id", -1)
	main.set("_interaction_mode", "walk")
	main.call("_on_window_size_changed")
	main.call("_sync_world")
	main.call("_sync_selection")
	for frame: int in range(8):
		await physics_frame
		await process_frame
	var fixture: Dictionary = await _open_fixture()
	if fixture.is_empty():
		return
	var receiver: StreamPeerTCP = fixture["receiver"] as StreamPeerTCP

	_expect(not trade_button.disabled and trade_button.tooltip_text.contains("click a player"),
		"with nobody selected the trade icon is enabled and says to click a player")
	_click(trade_button.get_global_rect().get_center(), true)
	_expect(root.gui_get_hovered_control() == trade_button,
		"the press lands on the trade icon")
	_click(trade_button.get_global_rect().get_center(), false)
	_expect(str(main.get("_interaction_mode")) == "trade" and _take(receiver).is_empty(),
		"pressing the trade icon with nobody selected arms trade and asks nobody")

	# Alice's chest on screen, in the world viewport's pixels and the window's.
	var alice: Node3D = (main.get("actor_nodes") as Dictionary).get(188) as Node3D
	var camera: Camera3D = world_viewport.get_camera_3d()
	var chest: Vector3 = (alice.global_position if alice != null else Vector3.ZERO) + Vector3.UP
	_expect(alice != null and camera != null and not camera.is_position_behind(chest),
		"the player to trade with stands in front of the camera")
	if alice == null or camera == null:
		_close_fixture(fixture)
		return
	var viewport_position: Vector2 = camera.unproject_position(chest)
	var at: Vector2 = container.get_global_transform() * (
		viewport_position * container.size / Vector2(world_viewport.size))
	var context: Dictionary = main.call("_cursor_context_at", viewport_position)
	_expect(str(context.get("target", "")) == "player"
		and MouseCursors.choose(context) == MouseCursors.TRADE,
		"armed, the pointer over the player is the trade glyph (got %s)" % str(context))
	cursors.apply(MouseCursors.choose(context))
	_expect(cursors.current() == MouseCursors.TRADE
		and cursors.name_of(cursors.current()) == "trade",
		"and the cursor set shows cursor_trade.png")
	_expect(str(main.call("_actor_click_action", 188,
		(state.get("actors") as Dictionary).get(188, {}), false)) == "trade",
		"the click handler resolves a click on that player to the trade action")
	_click(at, true)
	_expect(root.gui_get_hovered_control() == container,
		"the click lands on the world, not on the interface")
	_click(at, false)
	_expect(_take(receiver) == EloriaProtocol.trade_with(188),
		"the click on the player sends TRADE_WITH for that player")
	_expect(int(state.get("selected_actor_id")) == 188
		and str(main.get("_interaction_mode")) == "trade",
		"the click selects the player and, as in Eternal Lands, trade stays armed")

	# Pressed with a player already selected, the icon asks them at once.
	main.set("_interaction_mode", "walk")
	trade_button.pressed.emit()
	_expect(_take(receiver) == EloriaProtocol.trade_with(188)
		and str(main.get("_interaction_mode")) == "trade",
		"with a player selected the icon sends TRADE_WITH straight away")

	# Escape puts the tool down; right-click advances to the next tool.
	var escape: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	escape.pressed = true
	main.call("_unhandled_input", escape)
	_expect(str(main.get("_interaction_mode")) == "walk",
		"Esc puts an armed trade down")
	main.call("_on_trade_button_pressed")
	_take(receiver)
	state.set("selected_actor_id", -1)
	_click(at, true, false, MOUSE_BUTTON_RIGHT)
	_click(at, false, false, MOUSE_BUTTON_RIGHT)
	_expect(str(main.get("_interaction_mode")) == "attack" and _take(receiver).is_empty(),
		"a right click cycles trade to attack without issuing a command")
	main.set("_interaction_mode", "walk")
	var player_actions: Array[String] = ["trade", "attack", "look", "walk"]
	for wanted: String in player_actions:
		_click(at, true, false, MOUSE_BUTTON_RIGHT)
		_click(at, false, false, MOUSE_BUTTON_RIGHT)
		_expect(str(main.get("_interaction_mode")) == wanted and _take(receiver).is_empty(),
			"right-click selects %s without activating the selected player" % wanted)
		if wanted == "look":
			_expect(str(main.get("_inventory_tool")) == "inspect",
				"the look mode also arms the inventory inspect tool")
	_expect(str(main.get("_inventory_tool")) == "grab",
		"cycling back to Move restores the item grab tool")
	main.call("_on_trade_button_pressed")
	main.call("_on_walk_button_pressed")
	_expect(str(main.get("_interaction_mode")) == "walk",
		"the walk icon puts an armed trade down")
	main.call("_on_trade_button_pressed")
	main.call("_on_attack_button_pressed")
	_expect(str(main.get("_interaction_mode")) == "attack",
		"so does the attack icon")
	main.set("_interaction_mode", "walk")
	context = main.call("_cursor_context_at", viewport_position)
	_click(at, true)
	_click(at, false)
	_expect(MouseCursors.choose(context) == MouseCursors.EYE and _take(receiver).is_empty(),
		"disarmed, the player offers a look again and a click sends no trade")

	_close_fixture(fixture)
	state.set("actors", previous_actors)
	state.set("local_actor_id", previous_local)
	state.set("selected_actor_id", previous_selected)
	main.call("_sync_world")
	main.call("_sync_selection")
	inventory_panel.visible = inventory_was_visible
	root.size = window_size
	await process_frame

func _press(control: Control, double: bool = false) -> void:
	var at: Vector2 = control.get_global_rect().get_center()
	_click(at, true, double)
	_click(at, false)

func _button(control: Control, index: MouseButton) -> void:
	var at: Vector2 = control.get_global_rect().get_center()
	_click(at, true, false, index)
	_click(at, false, false, index)

func _click(at: Vector2, pressed: bool, double: bool = false,
		index: MouseButton = MOUSE_BUTTON_LEFT) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = at
	motion.global_position = at
	root.push_input(motion)
	var event := InputEventMouseButton.new()
	event.button_index = index
	event.pressed = pressed
	event.double_click = double
	event.position = at
	event.global_position = at
	if pressed:
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if index == MOUSE_BUTTON_LEFT else MOUSE_BUTTON_MASK_RIGHT
	root.push_input(event)

## Everything the client has sent since the last call. Loopback delivery is
## quick but not instant, so an empty read waits briefly before believing it.
func _take(receiver: StreamPeerTCP) -> PackedByteArray:
	for attempt: int in range(25):
		receiver.poll()
		if receiver.get_available_bytes() > 0:
			break
		OS.delay_usec(2000)
	var available: int = receiver.get_available_bytes()
	if available <= 0:
		return PackedByteArray()
	return receiver.get_data(available)[1] as PackedByteArray

## Points the Network singleton at a local socket so sent frames can be read.
func _open_fixture() -> Dictionary:
	var network: Node = root.get_node("Network")
	var old_peer: StreamPeerTCP = network.get("_peer") as StreamPeerTCP
	var peer := StreamPeerTCP.new()
	var server := TCPServer.new()
	if server.listen(0, "127.0.0.1") != OK:
		_expect(false, "local packet fixture listens")
		return {}
	network.set_process(false)
	network.set("_peer", peer)
	peer.connect_to_host("127.0.0.1", server.get_local_port())
	for attempt: int in range(20):
		peer.poll()
		if server.is_connection_available():
			break
		await process_frame
	var receiver: StreamPeerTCP = server.take_connection()
	var fixture: Dictionary = {"server": server, "peer": peer, "receiver": receiver, "old_peer": old_peer}
	if receiver == null:
		_expect(false, "local packet fixture connects")
		_close_fixture(fixture)
		return {}
	peer.poll()
	return fixture

func _close_fixture(fixture: Dictionary) -> void:
	var network: Node = root.get_node("Network")
	(fixture["peer"] as StreamPeerTCP).disconnect_from_host()
	if fixture["receiver"] != null:
		(fixture["receiver"] as StreamPeerTCP).disconnect_from_host()
	(fixture["server"] as TCPServer).stop()
	network.set("_peer", fixture["old_peer"])
	network.set_process(true)

func _check_camera_relative_movement(main: Control) -> void:
	var rig: IsometricCameraController = main.get("camera_rig") as IsometricCameraController
	var original_adapter: CoordinateAdapter = main.get("adapter") as CoordinateAdapter
	var original_yaw: float = rig.yaw_degrees
	var original_pitch: float = rig.pitch_degrees
	var original_distance: float = rig.distance
	# Each row gives camera yaw, W, and D on a map whose server Y is inverted.
	var views: Array = [
		[0.0, Vector2i(0, 1), Vector2i(1, 0)],
		[45.0, Vector2i(-1, 1), Vector2i(1, 1)],
		[90.0, Vector2i(-1, 0), Vector2i(0, 1)],
		[135.0, Vector2i(-1, -1), Vector2i(-1, 1)],
		[180.0, Vector2i(0, -1), Vector2i(-1, 0)],
		[225.0, Vector2i(1, -1), Vector2i(-1, -1)],
		[270.0, Vector2i(1, 0), Vector2i(0, -1)],
		[315.0, Vector2i(1, 1), Vector2i(1, -1)]]
	for inverted: bool in [true, false]:
		main.set("adapter", CoordinateAdapter.new({"invertServerY": inverted}))
		for view: Array in views:
			rig.yaw_degrees = float(view[0])
			rig.call("_update_camera")
			var forward: Vector2i = view[1]
			var right: Vector2i = view[2]
			if not inverted:
				forward.y = -forward.y
				right.y = -right.y
			_expect(main.call("_camera_relative_tile_direction", 1, 0) == forward
				and main.call("_camera_relative_tile_direction", -1, 0) == -forward
				and main.call("_camera_relative_tile_direction", 0, 1) == right
				and main.call("_camera_relative_tile_direction", 0, -1) == -right,
				"WASD follows camera yaw %s with inverted server Y %s" % [view[0], inverted])
	main.set("adapter", CoordinateAdapter.new())
	for pose: Vector3 in [Vector3(0.0, -80.0, 3.0), Vector3(0.0, -15.0, 90.0),
			Vector3(20.0, -60.0, 26.0), Vector3(30.0, -60.0, 26.0)]:
		rig.yaw_degrees = pose.x
		rig.pitch_degrees = pose.y
		rig.distance = pose.z
		rig.call("_update_camera")
		_expect(main.call("_camera_relative_tile_direction", 1, 1)
			== (Vector2i(0, 1) if pose.x == 30.0 else Vector2i(1, 1)),
			"diagonal input combines before snapping and is independent of pitch and zoom: %s" % pose)
	_expect(main.call("_camera_relative_tile_direction", 0, 0) == Vector2i.ZERO,
		"no movement input stays still")
	main.set("adapter", original_adapter)
	rig.yaw_degrees = original_yaw
	rig.pitch_degrees = original_pitch
	rig.distance = original_distance
	rig.call("_update_camera")

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)

func _nameplate_of(main: Node, actor_id: int) -> Label3D:
	var node: Node3D = (main.get("actor_nodes") as Dictionary).get(actor_id) as Node3D
	if node == null:
		return null
	return node.get_node_or_null("Nameplate") as Label3D

func _hex_bytes(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

## The rendered facing has to be the direction the body crosses the ground in,
## not the tile direction that arrived with the packet. The two differ by
## design: the presentation runs a fraction of a tile behind the authoritative
## position, and every step that lands in the same frame as another is folded
## into a single segment before the actor node ever sees it.
func _check_travel_facing() -> void:
	var adapter := CoordinateAdapter.new()
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.apply_server_state({"actor_id": 1, "x": 10, "y": 10, "rotation": 0,
		"command": -1}, adapter, true)
	actor._physics_process(1.0 / 60.0)
	_expect(is_equal_approx(actor.call("_rendered_target_yaw"),
		actor.desired_facing_yaw()),
		"a resting actor is drawn facing exactly where the server says it does")

	# CMD_MOVE_E, taken only part way before the next packet arrives.
	actor.apply_server_state({"actor_id": 1, "x": 11, "y": 10, "rotation": 0,
		"command": 22}, adapter, false)
	for frame: int in range(9):
		actor._physics_process(1.0 / 60.0)
	# CMD_MOVE_N from a body that has not finished travelling east yet, so the
	# ground it is about to cross runs north-east and it must face north-east.
	actor.apply_server_state({"actor_id": 1, "x": 11, "y": 11, "rotation": 0,
		"command": 20}, adapter, false)
	var lagging_travel: float = ReplicatedActor3D.travel_yaw(
		actor.get("_segment_start") as Vector3, actor.server_target, 0.0)
	_expect(is_equal_approx(actor.call("_rendered_target_yaw"), lagging_travel)
		and not is_equal_approx(lagging_travel, actor.desired_facing_yaw()),
		"a step taken before the last one finished is faced along the ground crossed")

	# Four steps folded into one world sync, as happens on any frame slower
	# than the server's movement cadence. The straight slide covers all four.
	actor.apply_server_state({"actor_id": 1, "x": 11, "y": 10, "rotation": 0,
		"command": 24}, adapter, true)
	actor._physics_process(1.0 / 60.0)
	actor.apply_server_state({"actor_id": 1, "x": 15, "y": 14, "rotation": 0,
		"command": 20}, adapter, false)
	var folded_travel: float = ReplicatedActor3D.travel_yaw(
		actor.get("_segment_start") as Vector3, actor.server_target, 0.0)
	_expect(is_equal_approx(actor.call("_rendered_target_yaw"), folded_travel)
		and is_equal_approx(folded_travel, adapter.direction_to_godot(Vector2i(1, 1))),
		"a burst folded into one segment is faced along the whole slide")

	# Authority is untouched: the facing the server named is still what the
	# actor settles on once it stops, and a turn shown while its answer is in
	# flight still outranks travel, because that actor is turning, not walking.
	_expect(is_equal_approx(actor.desired_facing_yaw(),
		adapter.direction_to_godot(Vector2i(0, 1))),
		"the authoritative facing survives a segment travelled in another direction")
	actor.predict_turn(PI / 4.0)
	_expect(is_equal_approx(actor.call("_rendered_target_yaw"),
		actor.desired_facing_yaw()),
		"a predicted turn still outranks the direction of travel")
	actor.clear_turn_prediction()
	for frame: int in range(240):
		actor._physics_process(1.0 / 60.0)
	_expect(is_equal_approx(actor.rotation.y, actor.desired_facing_yaw()),
		"the actor comes to rest on the authoritative facing")
	actor.free()

## The minimap's right-click menu. It used to be three orientation radio items
## and nothing else; there are now enough choices that a flat list would bury
## the orientation among twenty siblings, so the menu is three submenus and
## this asserts that shape rather than a count that any regrouping satisfies.
func _check_minimap_menu(main: Node, menu: PopupMenu) -> void:
	_expect(menu != null and menu.item_count == 3,
		"the minimap menu opens as three groups rather than a flat list")
	if menu == null or menu.item_count != 3:
		return
	var groups: Dictionary = {}
	for index: int in range(menu.item_count):
		groups[menu.get_item_text(index)] = menu.get_item_submenu_node(index)
	_expect(groups.has("Orientation") and groups.has("Marker types")
		and groups.has("Visualization"),
		"the minimap menu names orientation, marker types and visualization")
	var orientation: PopupMenu = groups.get("Orientation") as PopupMenu
	_expect(orientation != null and orientation.item_count == 3
		and orientation.is_item_radio_checkable(0),
		"the three rotation options moved under Orientation")
	var types: PopupMenu = groups.get("Marker types") as PopupMenu
	var declared: Array = main.get("MINIMAP_MARKER_TYPES") as Array
	_expect(types != null and types.item_count == declared.size()
		and types.is_item_checkable(0) and not types.is_item_radio_checkable(0),
		"every marker type is its own switch under Marker types")
	var visualization: PopupMenu = groups.get("Visualization") as PopupMenu
	_expect(visualization != null and visualization.item_count == 4,
		"Visualization holds marker size, shape, minimap size and border")
	if visualization == null:
		return
	var appearance: Dictionary = {}
	for index: int in range(visualization.item_count):
		appearance[visualization.get_item_text(index)] = (
			visualization.get_item_submenu_node(index))
	_expect(appearance.has("Marker size") and appearance.has("Minimap shape")
		and appearance.has("Minimap size") and appearance.has("Border width"),
		"Visualization names each of the four things it changes")
	var shape: PopupMenu = appearance.get("Minimap shape") as PopupMenu
	_expect(shape != null and shape.item_count == 2
		and shape.get_item_text(0) == "Square" and shape.get_item_text(1) == "Round",
		"the minimap can be squared off or rounded")

## The marks the minimap draws over its render, and the settings that change
## them.
##
## The size of a mark is the point of the overlay: the marks were discs
## modelled in the world, so zooming the minimap out shrank them to specks and
## zooming in swelled them into saucers. A mark's radius owes nothing to the
## camera now, which is asserted here at both ends of the zoom range - against
## the projected positions, which do move, so that a zoom that did nothing
## cannot pass this by holding everything still.
func _check_minimap_markers(main: Node, minimap_image: Control,
		minimap_camera: Camera3D) -> void:
	var overlay: Control = main.get("minimap_marker_overlay") as Control
	_expect(overlay != null and overlay.get_parent() == minimap_image
		and overlay.mouse_filter == Control.MOUSE_FILTER_IGNORE,
		"the minimap's marks are drawn over its render and swallow no clicks")
	if overlay == null:
		return
	var near_mark := {"position": minimap_camera.global_position
		+ Vector3(24.0, -220.0, 0.0), "type": &"player", "colour": Color.WHITE}
	var restore_zoom: float = float(main.get("_minimap_zoom"))
	main.set("_minimap_zoom", float(main.get("MINIMAP_ZOOM_MIN")))
	main.call("_apply_minimap_zoom")
	var close_radius: float = float(overlay.call("mark_radius", near_mark))
	var close_point: Variant = overlay.call("mark_point", near_mark)
	main.set("_minimap_zoom", float(main.get("MINIMAP_ZOOM_MAX")))
	main.call("_apply_minimap_zoom")
	var far_radius: float = float(overlay.call("mark_radius", near_mark))
	var far_point: Variant = overlay.call("mark_point", near_mark)
	_expect(close_point is Vector2 and far_point is Vector2
		and not (close_point as Vector2).is_equal_approx(far_point as Vector2),
		"zooming the minimap moves a mark over the ground it names")
	_expect(is_equal_approx(close_radius, far_radius) and close_radius > 0.0,
		"a mark is the same size on screen at both ends of the zoom range")
	main.set("_minimap_zoom", restore_zoom)
	main.call("_apply_minimap_zoom")

	# Marker size is the only thing that changes it.
	main.call("_on_minimap_marker_scale_selected", 0)
	var smallest: float = float(overlay.call("mark_radius", near_mark))
	main.call("_on_minimap_marker_scale_selected", 4)
	var largest: float = float(overlay.call("mark_radius", near_mark))
	_expect(largest > smallest,
		"the marker size option is what changes how big a mark is drawn")
	main.call("_on_minimap_marker_scale_selected", 2)

	# Each type is a switch of its own, and the overlay reads the same switch
	# main.gd wrote rather than a copy of it.
	var types: Array = main.get("MINIMAP_MARKER_TYPES") as Array
	var creature_index: int = types.find(&"creature")
	main.call("_on_minimap_marker_type_toggled", creature_index)
	_expect(not bool(overlay.call("type_enabled", &"creature"))
		and bool(overlay.call("type_enabled", &"player")),
		"switching creature marks off leaves every other type drawn")
	main.call("_on_minimap_marker_type_toggled", creature_index)
	_expect(bool(overlay.call("type_enabled", &"creature")),
		"switching a marker type back on draws it again")

	main.call("_on_minimap_shape_selected", 1)
	var mask: ShaderMaterial = minimap_image.material as ShaderMaterial
	_expect(str(main.get("_minimap_shape")) == "round" and mask != null
		and bool(mask.get_shader_parameter("rounded"))
		and bool(overlay.get("_round")),
		"a round minimap masks both the render and the marks over it")
	main.call("_on_minimap_shape_selected", 0)
	_expect(mask != null and not bool(mask.get_shader_parameter("rounded")),
		"squaring the minimap up again unmasks the corners")

	# The border is the black margin and the drag band at once, so the
	# narrowest step is still a band a mouse can find.
	var border_steps: Array = main.get("MINIMAP_BORDER_STEPS") as Array
	main.call("_on_minimap_border_selected", 0)
	_expect(float(border_steps[0]) > 0.0
		and is_equal_approx(minimap_image.offset_left,
			roundf(float(border_steps[0]) * float(main.get("_minimap_scale")))),
		"the narrowest border still leaves a band the window is dragged by")
	main.call("_on_minimap_border_selected", 2)

	# One value, two controls: the menu step and the settings window's slider.
	var size_steps: Array = main.get("MINIMAP_SIZE_STEPS") as Array
	main.call("_on_minimap_size_step_selected", size_steps.size() - 1)
	var size_slider: Range = main.get_node(
		"%MinimapSize") as Range
	_expect(is_equal_approx(float(main.get("_minimap_scale")),
			float(size_steps[-1]))
		and is_equal_approx(size_slider.value, float(size_steps[-1])),
		"setting the minimap size from the menu moves the settings slider with it")
	main.call("_on_minimap_size_step_selected", 1)

## Everyone the server replicates carries the light blue dot the full map's
## legend calls Player / NPC. The local player draws its own white mark over
## the top of its dot; nobody else has one, so without this an NPC standing in
## a town is on the map only for as long as somebody is looking at the world.
##
## Creatures are the exception, and the reason the dot has a colour at all: a
## player reading the map during an invasion is reading it to find out where
## the invasion is, so an invasion creature is red and wildlife is yellow.
func _check_map_dot() -> void:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	# Gate Warden Ilyon's wire record: an Eloria NPC actor type, kind 20.
	actor.configure({"actor_id": 30014, "x": 704, "y": 816, "rotation": 0,
		"actor_type": 308, "kind": 20, "name": "Gate Warden Ilyon"},
		CoordinateAdapter.new(), {}, {})
	var dot: MeshInstance3D = actor.get_node_or_null("MapDot") as MeshInstance3D
	_expect(dot != null and dot.layers == ReplicatedActor3D.MAP_MARKER_LAYER,
		"a replicated actor carries a dot only the map cameras render")
	var material: StandardMaterial3D = (dot.mesh.surface_get_material(0)
		as StandardMaterial3D) if dot != null else null
	_expect(material != null
		and material.albedo_color.is_equal_approx(ReplicatedActor3D.MAP_DOT_COLOUR),
		"the dot is the light blue the legend names")
	actor.free()

	# The creature dots are read off the wire rather than out of a fixture,
	# because the only thing on the wire that says "invasion" is the colour
	# marker the server prefixes the creature's name with.
	var wildlife: Dictionary = EloriaProtocol.decode_actor(
		_creature_packet(0, "Mirrorfin Otter"), false)
	_expect(str(wildlife.get("name", "")) == "Mirrorfin Otter"
		and int(wildlife.get("name_colour", 0)) == 0,
		"a natural spawn reaches the client uncoloured and whole")
	_expect(_map_dot_colour(wildlife).is_equal_approx(
			ReplicatedActor3D.CREATURE_MAP_DOT_COLOUR),
		"a natural spawn is a yellow dot on the map")
	var invader: Dictionary = EloriaProtocol.decode_actor(_creature_packet(
		ReplicatedActor3D.INVASION_NAME_COLOUR, "Armed Goblin"), false)
	_expect(str(invader.get("name", "")) == "Armed Goblin",
		"the colour marker is read as a colour rather than left in the name")
	_expect(_map_dot_colour(invader).is_equal_approx(
			ReplicatedActor3D.INVASION_MAP_DOT_COLOUR),
		"an invasion creature is a red dot on the map")
	# EL blue1 is a summon: neither an invasion nor wildlife, and a player's
	# own summon standing next to them must not read as something to run from.
	var summon: Dictionary = EloriaProtocol.decode_actor(
		_creature_packet(4, "Brown Rabbit"), false)
	_expect(_map_dot_colour(summon).is_equal_approx(
			ReplicatedActor3D.MAP_DOT_COLOUR),
		"a summoned creature keeps the ordinary actor dot")
	_expect(not ReplicatedActor3D.INVASION_MAP_DOT_COLOUR.is_equal_approx(
			ReplicatedActor3D.CREATURE_MAP_DOT_COLOUR)
		and not ReplicatedActor3D.INVASION_MAP_DOT_COLOUR.is_equal_approx(
			ReplicatedActor3D.MAP_DOT_COLOUR)
		and not ReplicatedActor3D.CREATURE_MAP_DOT_COLOUR.is_equal_approx(
			ReplicatedActor3D.MAP_DOT_COLOUR),
		"the three dots are three colours")

## One plain ADD_NEW_ACTOR payload for a creature, laid out the way the server
## writes it: the creature's fields, then its name behind an optional colour
## marker byte.
func _creature_packet(name_colour: int, creature_name: String) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(17)
	payload.encode_u16(0, 4242)
	payload.encode_u16(2, 704)
	payload.encode_u16(4, 816)
	payload.encode_u16(6, 0)
	payload.encode_s16(8, 0)
	payload.encode_u8(10, 6)
	payload.encode_u8(11, 7)
	payload.encode_u16(12, 40)
	payload.encode_u16(14, 40)
	# PKABLE_COMPUTER_CONTROLLED: the kind the server gives every creature.
	payload.encode_u8(16, 5)
	if name_colour > 0:
		payload.append(127 + name_colour)
	payload.append_array(creature_name.to_ascii_buffer())
	payload.append(0)
	return payload

## The colour the dot a spawn packet actually builds is painted in, rather than
## the colour the rule says it should be: the two only agree while the spawn
## path keeps handing the packet to the dot.
func _map_dot_colour(dto: Dictionary) -> Color:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.configure(dto, CoordinateAdapter.new(), {}, {})
	var dot: MeshInstance3D = actor.get_node_or_null("MapDot") as MeshInstance3D
	var material: StandardMaterial3D = (dot.mesh.surface_get_material(0)
		as StandardMaterial3D) if dot != null else null
	var colour: Color = material.albedo_color if material != null else Color.BLACK
	actor.free()
	return colour
