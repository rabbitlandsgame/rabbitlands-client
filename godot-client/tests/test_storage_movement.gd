extends SceneTree
## Exercise production movement dispatch while classic and docked storage are open.

var failures := 0
var sent_moves: Array[Vector2i] = []
const SETTINGS := "user://eloria_hud.cfg"

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _run() -> void:
	var had_settings := FileAccess.file_exists(SETTINGS)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS) if had_settings else PackedByteArray()
	root.size = Vector2i(1280, 720)
	var network: Node = root.get_node("Network")
	network.set_script(load("res://tests/fixtures/map_movement_network_probe.gd"))
	network.set_process(false)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	main.exterior_stream.set_process(false)
	var state: Node = root.get_node("AppState")
	network.movement_requested.connect(func(tile: Vector2i) -> void: sent_moves.append(tile))
	main.game_view.show()
	main.login_panel.hide()
	state.authenticated = true
	state.current_map = "landfall"
	state.local_actor_id = 7
	state.actors = {7: {"actor_id": 7, "x": 117, "y": 216, "health": 20}}
	var actor := ReplicatedActor3D.new()
	main.world_root.add_child(actor)
	main.actor_nodes[7] = actor
	var manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/landfall/client/world.json")
	main.world_loader.manifest = manifest
	main.adapter = manifest.coordinate_adapter()
	actor.position = main.adapter.tile_center(117, 216)
	main._configure_full_map(manifest)
	main._update_local_actor_follow()
	var workspace: Node = main.classic_storage
	var was_docked: bool = workspace.docked

	for docked: bool in [false, true]:
		workspace.set_docked(docked)
		state.call("_on_packet", EloriaProtocol.ServerMessage.STORAGE_LIST,
			PackedByteArray([1, 0]) + "Food".to_utf8_buffer() + PackedByteArray([0]))
		main._sync_storage()
		await process_frame
		_expect(main.storage_panel.visible, "storage opens")
		var focus := root.gui_get_focus_owner()
		if focus != null:
			focus.release_focus()
		sent_moves.clear()
		Input.action_press("move_north")
		main._update_keyboard_movement()
		Input.action_release("move_north")
		_expect(sent_moves.size() == 1, "keyboard movement works with storage open")
		main._clear_keyboard_movement_tracking()

		sent_moves.clear()
		var click := InputEventMouseButton.new()
		click.button_index = MOUSE_BUTTON_LEFT
		click.pressed = true
		click.position = main.viewport_container.size * 0.5
		main._on_world_gui_input(click)
		_expect(sent_moves.size() == 1, "viewport click walks with storage open")
		_expect(main.storage_panel.visible, "starting a walk keeps storage open")

		main.minimap_frame.show()
		await process_frame
		sent_moves.clear()
		click.position = main.minimap.size * 0.5
		click.global_position = main.minimap.get_global_transform() * click.position
		main._on_minimap_gui_input(click)
		_expect(sent_moves.size() == 1, "minimap click walks with storage open")

		main._toggle_full_map()
		await process_frame
		sent_moves.clear()
		click.position = main.map_image.size * 0.5
		click.global_position = main.map_image.get_global_transform() * click.position
		main._on_full_map_gui_input(click)
		_expect(sent_moves.size() == 1, "Tab map click walks with storage open")
		main._sync_storage()
		_expect(main.full_map.visible, "storage refresh keeps the Tab map visible")
		main.full_map.hide()

		# The server's close must also release a carried storage item and docked pack.
		main._storage_carried_position = 3
		state.call("_on_packet", EloriaProtocol.ServerMessage.STORAGE_LIST, PackedByteArray([0]))
		main._sync_storage()
		_expect(not main.storage_panel.visible and not state.storage.open,
			"out-of-range storage close hides the window")
		_expect(main._storage_carried_position == -1 and not workspace.is_inventory_docked(),
			"out-of-range close cancels storage carry and releases the docked inventory")
	workspace.set_docked(was_docked)
	main.queue_free()
	await process_frame
	if had_settings:
		var settings := FileAccess.open(SETTINGS, FileAccess.WRITE)
		settings.store_buffer(saved_settings)
		settings.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS))
	print("Storage movement tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
