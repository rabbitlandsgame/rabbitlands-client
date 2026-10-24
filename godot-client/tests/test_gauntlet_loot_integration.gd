extends SceneTree

var failures := 0

class PrewarmSpy extends "res://src/world/arrival_prewarm.gd":
	var requests: Array[Dictionary] = []
	func prewarm(entry: Dictionary, destination_map: String, destination_tile: Vector2i, _parent: Node3D) -> void:
		requests.append({"entry": entry, "map": destination_map, "tile": destination_tile})

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func dying_creature(elapsed: float) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.set("_is_creature", true)
	var body := MeshInstance3D.new()
	body.mesh = BoxMesh.new()
	actor.add_child(body)
	actor.apply_server_state({"x": 0, "y": 0, "rotation": 0, "health": 0, "alive": false,
		"command": 3, "death_presentation": {"temporary": true, "animation_seconds": 3.0,
			"fade_seconds": 4.0, "elapsed": elapsed, "received_msec": Time.get_ticks_msec()}},
		CoordinateAdapter.new({"metresPerTile": 1.0}))
	actor.set_process(false)
	return actor

func run() -> void:
	root.size = Vector2i(1280, 720)
	root.get_node("Network").set_process(false)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.set_physics_process(false)
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.authenticated = true
	var prewarm := PrewarmSpy.new()
	main.gauntlet_prewarm = prewarm
	var snapshot := {"version": 1, "open": true, "run_id": "integration", "revision": 1,
		"route": "The Resin Road", "phase": "complete", "reason": "", "leader": "alder",
		"is_leader": true, "can_send": true, "page": 0, "pages": 1, "assigned": 1, "total": 1,
		"announcement": "", "announcement_id": 0,
		"exit_destination": {"map": "four_gates", "x": 309, "y": 162}, "exited": false,
		"rows": [{"id": "0", "name": "Gold Coins", "image_id": 0, "quantity": 10,
			"rare": false, "owner": "", "locked": false, "source": "creature",
			"allocations": {"alder": 10}, "price_gold": 0, "sell_quantity": 0,
			"available_quantity": 10, "npc_gold": 0, "npc_bundle": 1, "sale_proceeds": 0}],
		"members": [{"username": "alder", "name": "Alder", "online": true, "self": true,
			"portrait": {}, "preview": [{"name": "Gold Coins", "image_id": 0, "quantity": 10}],
			"more": 0, "charge_gold": 0, "rebate_gold": 0, "sale_share_gold": 0,
			"payment_ready": true, "payment_approved": true}]}
	snapshot.phase = "active"
	snapshot.open = false
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	expect(prewarm.requests.is_empty(), "the beam is not loaded during an active instance")
	var first := dying_creature(8.0)
	var last := dying_creature(7.0)
	main.actor_nodes = {1001: first, 1002: last}
	snapshot.phase = "complete"
	snapshot.open = true
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	await process_frame
	var ledger: Control = main.extension_windows.gauntlet_loot_window
	expect(not ledger.panel.visible, "completion does not interrupt the remaining creature dissolves")
	first._process(1.1)
	await create_timer(2.1).timeout
	expect(not ledger.panel.visible, "the pause waits for the last dissolve even after an earlier corpse disappears")
	last._process(2.1)
	var dissolved_at := Time.get_ticks_msec()
	await create_timer(1.0).timeout
	snapshot.revision += 1
	snapshot.open = false
	snapshot.rows[0].quantity = 12
	snapshot.rows[0].available_quantity = 12
	snapshot.rows[0].allocations.alder = 12
	snapshot.members[0].preview[0].quantity = 12
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	expect(not ledger.panel.visible, "loot updates preserve the pending completion pause")
	var completion_deadline := dissolved_at + 4000
	while not ledger.panel.visible and Time.get_ticks_msec() < completion_deadline:
		await process_frame
	expect(Time.get_ticks_msec() - dissolved_at >= 2000, "the ledger opens at least two seconds after the last dissolve")
	expect(ledger.panel.visible, "the real packet dispatch opens the ledger in the game")
	expect(ledger._state.rows[0].quantity == 12, "the delayed ledger shows the latest loot snapshot")
	main.actor_nodes.clear()
	first.free()
	last.free()
	expect(ledger.panel.get_parent() == main.game_view, "the ledger joins the shared native window surface")
	expect(ledger.panel in main.window_stack._windows, "the ledger is registered for stacking and pointer handling")
	expect(main.extension_windows.has_open_window(), "the open ledger blocks world input")
	expect(prewarm.requests.size() == 2 and prewarm.requests[0].map == "four_gates"
		and prewarm.requests[0].tile == Vector2i(309, 162), "completed loot quietly preloads the server's beam destination")
	expect(not main.arrival_curtain.is_showing(), "background beam loading does not show a loading screen while loot is split")
	var inspected: Array[Dictionary] = []
	ledger.configure_sender(func(text: String) -> Error:
		inspected.append(JSON.parse_string(text.trim_prefix("#gauntletloot ")))
		return OK)
	main.extension_windows.detail_popup_allowed = false
	var inspect_button: Button = ledger.table.get_child(0).find_child("InspectItem", true, false)
	expect(main._slot_cursor_target(inspect_button) == "item_inspect", "loot icons show the inspect eye cursor")
	inspect_button.pressed.emit()
	expect(inspected.size() == 1 and inspected[0].action == "inspect", "the real loot icon sends an inspection request")
	expect(main.extension_windows.detail_popup_allowed, "loot inspection re-enables the detail card after using inventory tools")
	var detail := PackedByteArray()
	detail.resize(7)
	detail.encode_u16(0, 0)
	detail.encode_u32(2, 10)
	for field: String in ["Gold Coins", "currency", "", "Used to buy goods and services.", "Weight 0 EMU", "", ""]:
		detail.append_array(field.to_utf8_buffer())
		detail.append(0)
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_ITEM_DETAIL, detail)
	await process_frame
	expect(main.extension_windows.detail_panel.visible and main.extension_windows.detail_text.text.contains("Used to buy goods and services.")
		and main.extension_windows.detail_text.text.contains("Weight 0 EMU"), "the server reply opens the existing description and stats card")
	state.close_item_detail()
	snapshot.phase = "sent"
	snapshot.exited = true
	snapshot.open = false
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	expect(not ledger.panel.visible, "the server's completed exit closes the loot window for every member")
	snapshot.phase = "complete"
	snapshot.exited = false
	snapshot.open = true
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	main.extension_windows.close_top()
	expect(not ledger.panel.visible and ledger.reopen.visible, "Escape closes the ledger while preserving the loot shortcut")
	expect(not ledger.announcement.visible, "closing the window also dismisses its notification banner")
	snapshot.run_id = "disconnect-during-completion"
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	expect(not ledger.panel.visible and ledger.is_processing(), "a new run schedules its own completion pause")
	state._on_connection_state_changed("disconnected")
	await create_timer(2.1).timeout
	expect(not ledger.panel.visible and not ledger.is_processing(), "disconnect cancels the pending popup")
	if OS.get_cmdline_user_args().has("--prewarm"):
		var real_prewarm := preload("res://src/world/arrival_prewarm.gd").new()
		real_prewarm.prewarm(MapRegistry.resolve(main.map_registry, "four_gates"),
			"four_gates", Vector2i(309, 162), main.world_root)
		expect(real_prewarm.pending(), "the real beam map starts loading in a hidden stream")
		var deadline := Time.get_ticks_msec() + 20000
		while real_prewarm.pending() and not real_prewarm.is_ready() and Time.get_ticks_msec() < deadline:
			await process_frame
		expect(real_prewarm.is_ready(), "the beam's actual terrain becomes resident in the background")
		var resident: Dictionary = real_prewarm.take("four_gates")
		expect(not resident.is_empty(), "the loaded beam terrain is available for arrival")
		if not resident.is_empty():
			var adopter := WorldLoader.new()
			main.world_root.add_child(adopter)
			adopter.adopt_world(resident)
			expect(adopter.loaded_by_adoption and adopter.world_root is ContinentChunkStream,
				"the arrival adopts the loaded beam instead of rebuilding it")
			expect(await ContinentChunkStream.drain_workers(self), "background map workers finish before the test exits")
			adopter.queue_free()
		expect(not main.arrival_curtain.is_showing(), "real background loading stays silent")
	main.queue_free()
	await process_frame
	print("Gauntlet loot game integration: %s" % ("PASS" if failures == 0 else "FAIL"))
	quit(failures)
