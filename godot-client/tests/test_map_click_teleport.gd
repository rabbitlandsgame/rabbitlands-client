extends SceneTree
## Map gestures reach the production handlers; only the final socket write is
## replaced, so the captured frames retain the server's normal #tp command.

var failures := 0
var checks := 0
var main: Control
var network: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	network = root.get_node("Network")
	network.set_script(load("res://tests/fixtures/minimap_drag_network_probe.gd"))
	network.block_for_hud_preview()
	root.size = Vector2i(1280, 800)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.exterior_stream.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	main.full_map.show()
	main.map_image.show()
	main.chat_input.release_focus()
	for panel_name: String in ["dialogue_panel", "trade_panel", "storage_panel", "manufacturing_panel"]:
		(main.get(panel_name) as Control).hide()
	var state: Node = root.get_node("AppState")
	state.current_map = "four_gates"
	state.local_actor_id = 9001
	state.actors = {9001: {"health": 50, "sitting": false, "appearance": {"weapon": 0}}}
	main._banner_option_boxes.ranging_lock.set_pressed_no_signal(false)
	main._banner_option_boxes.sit_lock.set_pressed_no_signal(false)
	main.adapter = CoordinateAdapter.new({"metresPerTile": 1.0,
		"origin": [0.0, 31.15, 0.0], "walkingHeight": 31.15, "invertServerY": false})
	var manifest := WorldManifest.new()
	manifest.data = {"coordinateTransform": {"serverCells": [128, 128]}}
	main.world_loader.manifest = manifest
	main.cartography = {"continent": {"originMetres": [0.0, 0.0], "metresPerPixel": 1.0}}
	main.cartography_regions = [
		{"serverMap": "four_gates", "globalTranslation": [0.0, 0.0, 0.0],
			"continentPolygon": [[0.0, 0.0], [50.0, 0.0], [50.0, 100.0], [0.0, 100.0]]},
		{"serverMap": "grey_moors", "globalTranslation": [50.0, 0.0, 0.0],
			"continentPolygon": [[50.0, 0.0], [100.0, 0.0], [100.0, 100.0], [50.0, 100.0]]}]
	main.exterior_stream.active_map = "four_gates"
	main.exterior_stream.links = []
	main.exterior_stream.registry = {
		"four_gates": {"continentGeography": {"translation": [0, 0, 0]},
			"coordinateTransform": {"serverCells": [128, 128]}},
		"grey_moors": {"continentGeography": {"translation": [50, 0, 0]},
			"coordinateTransform": {"metresPerTile": 2.0, "serverOrigin": [100, -40],
				"origin": [0.0, 31.15, 0.0], "invertServerY": true,
				"serverTileMin": [100, -100], "serverCells": [128, 128]}}}
	await process_frame
	main._full_map_base_size = 160.0
	main._full_map_zoom = 1.0
	main._minimap_shape = "square"
	main._minimap_border = 10.0
	main._minimap_scale = 1.0
	main.minimap_frame.size = Vector2(400, 200)
	main.minimap_frame.scale = Vector2.ONE
	for spec: Array in [[main.map_image, main.full_map_viewport, main.full_map_camera],
			[main.minimap, main.map_viewport, main.map_camera]]:
		var control: TextureRect = spec[0]
		var viewport: SubViewport = spec[1]
		var camera: Camera3D = spec[2]
		control.custom_minimum_size = Vector2.ZERO
		control.size = Vector2(400, 200)
		control.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		viewport.size = Vector2i(200, 200)
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 160.0
		camera.global_position = Vector3(50.0, 220.0, 50.0)
		camera.rotation = Vector3(-PI * 0.5, 0.0, 0.0)
		_check_map(control, viewport, camera)
	_check_unmapped_interior()
	_check_rotated_minimap()
	_check_zoomed_tab_map()
	main.queue_free()
	await process_frame
	print("Map click teleport: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _check_map(control: TextureRect, viewport: SubViewport, camera: Camera3D) -> void:
	var label := "Tab map" if control == main.map_image else "minimap"
	var target := Vector2i(20, 40)
	var at := _texture_position(camera.unproject_position(main.adapter.tile_center(target.x, target.y)), control, viewport.size)
	var teleport := EloriaProtocol.chat("#tp 20 40 four_gates")
	network.outgoing.clear()
	_button(control, at, true, true, true)
	_expect_frame(teleport, label + " Ctrl+Shift+left press sends exactly one #tp with the clicked tile and map")
	_button(control, at, false, true, true)
	_expect(network.outgoing.is_empty(), label + " left release does not repeat the teleport")
	_button(control, at, true, true, true, MOUSE_BUTTON_RIGHT)
	_expect(network.outgoing.is_empty(), label + " Ctrl+Shift+right click cannot teleport")
	for modifiers: Array in [[false, false], [true, false], [false, true]]:
		_button(control, at, true, modifiers[0], modifiers[1])
		_expect_frame(EloriaProtocol.move_to(target.x, target.y, modifiers[1]),
			label + " ordinary, Ctrl-only and Shift-only clicks retain walking/running")
		_button(control, at, false, modifiers[0], modifiers[1])
	# The picture is centered in a 400 x 200 control: x=80 is inside the
	# control and away from the draggable rim, but outside its 200px image.
	_button(control, Vector2(80, 100), true, true, true)
	_button(control, Vector2(80, 100), false, true, true)
	_expect(network.outgoing.is_empty(), label + " letterbox margins do not teleport")
	main.exterior_stream.pending_walk = {"map": "grey_moors", "tile": Vector2i(105, -61)}
	main._map_walk_target = {"map": "four_gates", "tile": target}
	main._keyboard_moving = true
	_button(control, at, true, true, true)
	_expect_frame(teleport, label + " teleport replaces an outstanding movement destination")
	_expect(main.exterior_stream.pending_walk.is_empty() and main._map_walk_target.is_empty()
		and not main._keyboard_moving, label + " teleport clears route, map marker and keyboard tracking")
	_button(control, at, false, true, true)
	var state: Node = root.get_node("AppState")
	state.actors[9001].appearance.weapon = 66
	main._banner_option_boxes.ranging_lock.set_pressed_no_signal(true)
	_button(control, at, true, true, true)
	_expect_frame(teleport, label + " range lock does not consume the explicit teleport gesture")
	_button(control, at, false, true, true)
	main._banner_option_boxes.ranging_lock.set_pressed_no_signal(false)
	state.actors[9001].appearance.weapon = 0
	network.magic_pending = {"op": "cast", "id": 1, "power": 1}
	network.magic_scope = "location"
	_button(control, at, true, true, true)
	_expect_frame(teleport, label + " an armed location spell does not replace teleport with casting")
	_button(control, at, false, true, true)
	network.clear_coordinate_intents()
	# This ground remains within the current map's served rectangle, but its
	# owner uses a shifted frame, two metres per tile and signed logical Y.
	var elsewhere := Vector3(60.5, 31.15, 40.5)
	_expect(main._tile_inside_current_map(main.adapter.godot_to_server(elsewhere)),
		label + " neighbor test lies inside the overlapping source rectangle")
	at = _texture_position(camera.unproject_position(elsewhere), control, viewport.size)
	_button(control, at, true, true, true)
	_expect_frame(EloriaProtocol.chat("#tp 105 -61 grey_moors"),
		label + " neighbor teleport uses its owning map's logical coordinates")
	_button(control, at, false, true, true)
	main.exterior_stream.registry.grey_moors.coordinateTransform.serverCells = [1, 1]
	_button(control, at, true, true, true)
	_button(control, at, false, true, true)
	_expect(network.outgoing.is_empty(), label + " invalid owner coordinates cannot fall back to another map")
	main.exterior_stream.registry.grey_moors.coordinateTransform.serverCells = [128, 128]
	var ocean := Vector3(110.5, 31.15, 40.5)
	var ocean_at := _texture_position(camera.unproject_position(ocean), control, viewport.size)
	_button(control, ocean_at, true, true, true)
	_button(control, ocean_at, false, true, true)
	_expect(network.outgoing.is_empty(), label + " unowned ground inside a served rectangle cannot teleport")
	main.trade_panel.show()
	_button(control, at, true, true, true)
	_button(control, at, false, true, true)
	_expect(network.outgoing.is_empty(), label + " a modal trade window still blocks map input")
	main.trade_panel.hide()

func _check_unmapped_interior() -> void:
	var state: Node = root.get_node("AppState")
	var original_map: String = state.current_map
	var original_regions: Array = main.cartography_regions
	var original_adapter: CoordinateAdapter = main.adapter
	var original_manifest: WorldManifest = main.world_loader.manifest
	state.current_map = "mirrorhold_interiors"
	main.cartography_regions = []
	main.adapter = CoordinateAdapter.new({"metresPerTile": 0.5,
		"origin": [0.0, 31.15, 0.0], "walkingHeight": 31.15,
		"serverOrigin": [-200, -100], "invertServerY": true})
	var manifest := WorldManifest.new()
	manifest.data = {"coordinateTransform": {"serverTileMin": [-200, -200], "serverCells": [128, 128]}}
	main.world_loader.manifest = manifest
	for spec: Array in [[main.map_image, main.full_map_viewport, main.full_map_camera],
			[main.minimap, main.map_viewport, main.map_camera]]:
		var control: TextureRect = spec[0]
		var viewport: SubViewport = spec[1]
		var camera: Camera3D = spec[2]
		var point: Vector3 = main.adapter.tile_center(-150, -150)
		var at := _texture_position(camera.unproject_position(point), control, viewport.size)
		_button(control, at, true, true, true)
		_expect_frame(EloriaProtocol.chat("#tp -150 -150 mirrorhold_interiors"),
			"an interior without territory polygons uses signed current-map tiles")
		_button(control, at, false, true, true)
		point = main.adapter.tile_center(-201, -150)
		at = _texture_position(camera.unproject_position(point), control, viewport.size)
		_button(control, at, true, true, true)
		_button(control, at, false, true, true)
		_expect(network.outgoing.is_empty(), "an interior rejects tiles below its signed logical minimum")
	state.current_map = original_map
	main.cartography_regions = original_regions
	main.adapter = original_adapter
	main.world_loader.manifest = original_manifest

func _check_rotated_minimap() -> void:
	var camera: Camera3D = main.map_camera
	var original_rotation := camera.rotation
	camera.rotation = Vector3(-PI * 0.5, PI / 3.0, 0.0)
	var point: Vector3 = main.adapter.tile_center(20, 40)
	var at := _texture_position(camera.unproject_position(point), main.minimap, main.map_viewport.size)
	_button(main.minimap, at, true, true, true)
	_expect_frame(EloriaProtocol.chat("#tp 20 40 four_gates"),
		"a rotated minimap teleports to the displayed tile through its live camera")
	_button(main.minimap, at, false, true, true)
	camera.rotation = original_rotation

func _check_zoomed_tab_map() -> void:
	main._full_map_zoom = 0.5
	main._full_map_base_position = main.full_map_camera.global_position
	var at := _texture_position(main.full_map_camera.unproject_position(main.adapter.tile_center(20, 40)),
		main.map_image, main.full_map_viewport.size)
	network.outgoing.clear()
	_button(main.map_image, at, true, true, true)
	_expect(network.outgoing.is_empty(), "zoomed Tab map waits to distinguish a teleport click from a pan")
	_button(main.map_image, at, false)
	_expect_frame(EloriaProtocol.chat("#tp 20 40 four_gates"),
		"zoomed Tab map preserves modifiers from the press even when released first")
	_button(main.map_image, at, true, true, true)
	var motion := InputEventMouseMotion.new()
	motion.position = at + Vector2(40, 25)
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	main.map_image.gui_input.emit(motion)
	_button(main.map_image, motion.position, false, true, true)
	_expect(network.outgoing.is_empty() and not main._full_map_pan_dragging,
		"Ctrl+Shift dragging a zoomed Tab map pans without teleporting")

func _texture_position(pixel: Vector2, control: TextureRect, viewport_size: Vector2i) -> Vector2:
	var target := Vector2(viewport_size)
	var displayed := target * minf(control.size.x / target.x, control.size.y / target.y)
	return (control.size - displayed) * 0.5 + pixel * displayed / target

func _button(control: TextureRect, at: Vector2, pressed: bool, ctrl := false,
		shift := false, button := MOUSE_BUTTON_LEFT) -> void:
	var event := InputEventMouseButton.new()
	event.position = at
	event.global_position = control.get_global_transform() * at
	event.button_index = button
	event.pressed = pressed
	event.ctrl_pressed = ctrl
	event.shift_pressed = shift
	control.gui_input.emit(event)

func _expect_frame(frame: PackedByteArray, label: String) -> void:
	_expect(network.outgoing.size() == 1 and network.outgoing[0] == frame,
		label + " (received %s)" % str(network.outgoing))
	network.outgoing.clear()

func _expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("FAIL: " + label)
