extends SceneTree

var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	root.size = Vector2i(1280, 720)
	root.get_node("Network").set_process(false)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.authenticated = true
	var snapshot := {"version": 1, "open": true, "run_id": "integration", "revision": 1,
		"route": "The Resin Road", "phase": "complete", "reason": "", "leader": "alder",
		"is_leader": true, "can_send": true, "page": 0, "pages": 1, "assigned": 1, "total": 1,
		"announcement": "", "announcement_id": 0,
		"rows": [{"id": "0", "name": "Gold Coins", "image_id": 0, "quantity": 10,
			"rare": false, "owner": "", "locked": false, "source": "creature",
			"allocations": {"alder": 10}, "price_gold": 0, "sell_quantity": 0,
			"available_quantity": 10, "npc_gold": 0, "npc_bundle": 1, "sale_proceeds": 0}],
		"members": [{"username": "alder", "name": "Alder", "online": true, "self": true,
			"portrait": {}, "preview": [{"name": "Gold Coins", "image_id": 0, "quantity": 10}],
			"more": 0, "charge_gold": 0, "rebate_gold": 0, "sale_share_gold": 0,
			"payment_ready": true, "payment_approved": true}]}
	state._on_packet(EloriaProtocol.ServerMessage.ELORIA_GAUNTLET_LOOT_STATE,
		JSON.stringify(snapshot).to_utf8_buffer())
	await process_frame
	var ledger: Control = main.extension_windows.gauntlet_loot_window
	expect(ledger.panel.visible, "the real packet dispatch opens the ledger in the game")
	expect(ledger.panel.get_parent() == main.game_view, "the ledger joins the shared native window surface")
	expect(ledger.panel in main.window_stack._windows, "the ledger is registered for stacking and pointer handling")
	expect(main.extension_windows.has_open_window(), "the open ledger blocks world input")
	main.extension_windows.close_top()
	expect(not ledger.panel.visible and ledger.reopen.visible, "Escape closes the ledger while preserving the loot shortcut")
	expect(not ledger.announcement.visible, "closing the window also dismisses its notification banner")
	main.queue_free()
	await process_frame
	print("Gauntlet loot game integration: %s" % ("PASS" if failures == 0 else "FAIL"))
	quit(failures)
