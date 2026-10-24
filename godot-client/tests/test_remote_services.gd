extends SceneTree

const Keys := preload("res://src/ui/key_bindings.gd")
var checks := 0
var failures := 0
var commands: Array[String] = []
var main: Control
var windows: Control
var fixtures: Dictionary
var state: Node
var network: Node

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func packet(name: String) -> void:
	var frame: PackedByteArray = str(fixtures[name]).hex_decode()
	state._on_packet(int(frame[0]), frame.slice(3))

func select_listing(party: bool) -> void:
	for index: int in state.marketplace.listings.size():
		if bool(state.marketplace.listings[index].party_owned) == party:
			windows.market_list.select(index)
			windows._on_market_selected(index)
			return

func run() -> void:
	state = root.get_node("AppState")
	network = root.get_node("Network")
	network.set_process(false)
	root.gui_embed_subwindows = true
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	state.authenticated = true
	windows = main.extension_windows
	windows.market_sender = func(command: String) -> Error: commands.append(command); return OK
	fixtures = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/remote_services.json"))
	var exchange: Button = main.get_node("%ExchangeButton")
	var storage: Button = main.get_node("%StoragePreviewButton")
	expect(exchange.icon != null and storage.icon != null and exchange.visible and storage.visible, "the menu contains visible exchange and storage icons")
	expect(main.settings_window.bindable_actions().has("toggle_exchange") and main.settings_window.bindable_actions().has("toggle_storage_preview"), "both service shortcuts appear in Controls")
	for action: String in ["toggle_exchange", "toggle_storage_preview"]:
		var defaults: Dictionary = ProjectSettings.get_setting("input/" + action)
		expect(Keys.describe(defaults.events[0]) == ("CTRL SHIFT E" if action == "toggle_exchange" else "CTRL SHIFT S"), "the shipped service shortcut has its intended default")
	exchange.pressed.emit()
	expect(commands.back() == "#auction ui browse", "the exchange menu icon requests the real exchange")
	packet("remote_browse")
	select_listing(true)
	expect(windows.market_buy.visible and windows.market_buy.disabled, "remote price browsing keeps the purchase action disabled")
	var before_buy := commands.size()
	windows._on_market_buy()
	expect(commands.size() == before_buy, "remote purchase activation cannot send a transfer request")
	packet("remote_mine")
	await process_frame
	await process_frame
	expect(windows.market_panel.visible and not state.marketplace.can_trade, "remote exchange snapshots open the normal price browser")
	expect(windows.market_list.item_count == 2 and state.marketplace.party_runs.size() == 1, "My listings includes both personal and original-party listings")
	expect(windows.market_tabs.sell.disabled and windows.market_collect.disabled, "remote access disables new listings and escrow collection")
	select_listing(false)
	expect(not windows.market_reprice.disabled and windows.market_cancel.disabled, "personal prices can be edited remotely while cancellation requires the NPC")
	windows.market_reprice.pressed.emit()
	await process_frame
	expect(windows.market_price_dialog.visible and windows.market_price_dialog.size.x < 550, "personal price editing uses a bounded dialog")
	windows.market_new_price.get_line_edit().text = "15"
	windows.market_new_price.apply()
	if OS.get_cmdline_user_args().has("--render"): await capture("remote-exchange-price.png")
	windows.market_price_dialog.confirmed.emit()
	windows.market_price_dialog.hide()
	expect(commands.back() == "#auction price %d 15" % int(fixtures.personal_id), "personal prices submit the selected listing and whole-coin value")
	packet("remote_mine")
	select_listing(true)
	expect(windows.market_reprice.text == "Propose price…" and windows.market_votes.visible, "party listings offer a price proposal and access to saved votes")
	windows.market_reprice.pressed.emit()
	await process_frame
	expect(windows.market_price_dialog.ok_button_text.contains("Vote Yes") and windows._market_price_hint.text.contains("14 days"), "party price proposals disclose their voting rules")
	windows.market_new_price.get_line_edit().text = "8"
	windows.market_new_price.apply()
	windows.market_price_dialog.confirmed.emit()
	windows.market_price_dialog.hide()
	expect(commands.back() == "#auction price %d 8" % int(fixtures.party_id), "party prices submit a proposal for the server to vote on")
	packet("remote_mine")
	select_listing(true)
	windows.market_votes.pressed.emit()
	var vote_request: Dictionary = JSON.parse_string(commands.back().trim_prefix("#gauntletloot "))
	expect(vote_request.action == "open" and vote_request.run_id == fixtures.party_run, "party voting opens the preserved original ledger")
	packet("near_mine")
	select_listing(false)
	expect(not windows.market_cancel.disabled and not windows.market_tabs.sell.disabled, "a fresh server permission enables physical exchange actions near its NPC")
	packet("remote_mine")
	windows._on_market_tab("browse")
	# Opening via a key shares the menu request; closing tells the server too.
	windows._close_marketplace()
	var event := Keys.parse("CTRL SHIFT E")
	event.pressed = true
	expect(main._handle_bound_action(event) and commands.back() == "#auction ui browse", "the default exchange key opens the same exchange as the menu")
	packet("remote_mine")
	expect(main._handle_bound_action(event) and not windows.market_panel.visible and commands.back() == "#auction close", "the exchange shortcut closes the view without leaving a remotely reopening session")
	storage.pressed.emit()
	expect(bool(state.storage.read_only), "the storage menu requests a view-only preview")
	for name: String in ["storage_categories", "storage_items", "storage_readonly"]: packet(name)
	await process_frame
	await process_frame
	main._sync_storage()
	expect(main.storage_panel.visible and bool(state.storage.read_only), "the negotiated storage mode opens the real storage preview")
	var classic: Node = main.classic_storage
	var all_disabled := true
	for button: Button in classic._transfer_buttons: all_disabled = all_disabled and button.disabled
	expect(all_disabled and main.storage_withdraw_button.disabled and main.storage_deposit_button.disabled and main.inventory_store_all.disabled, "classic, standard, bulk and favorite-list transfers are disabled in preview")
	classic._on_storage_cell_pressed(0)
	expect(main._storage_carried_position == -1, "preview items can be selected without lifting them for withdrawal")
	expect(network.withdraw_storage(0, 1) == ERR_UNAUTHORIZED and network.deposit_storage(0, 1) == ERR_UNAUTHORIZED, "all storage transfer send paths reject preview mode")
	if OS.get_cmdline_user_args().has("--render"): await capture("remote-storage-preview.png")
	var storage_event := Keys.parse("CTRL SHIFT S")
	storage_event.pressed = true
	get_root().gui_release_focus()
	expect(main._handle_bound_action(storage_event) and not bool(state.storage.open), "the default storage shortcut closes the preview")
	var backup := {}
	for action: String in ["toggle_exchange", "toggle_storage_preview"]:
		backup[action] = InputMap.action_get_events(action)
		InputMap.action_erase_events(action)
		InputMap.action_add_event(action, Keys.parse("CTRL SHIFT F9" if action == "toggle_exchange" else "CTRL SHIFT F10"))
	var actions: Array = ["toggle_exchange", "toggle_storage_preview"]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://test-artifacts"))
	expect(Keys.save(actions, "res://test-artifacts/remote-services-keys.ini") == OK, "custom service shortcuts save through the existing keys file system")
	for action: String in actions: InputMap.action_erase_events(action)
	expect(Keys.load_file(actions, "res://test-artifacts/remote-services-keys.ini") == 2, "custom service shortcuts survive reloading the key file")
	main._refresh_service_tooltips()
	expect(exchange.tooltip_text.contains("F9") and storage.tooltip_text.contains("F10"), "menu hints follow the user's rebound shortcuts")
	var rebound_storage := Keys.parse("CTRL SHIFT F10")
	rebound_storage.pressed = true
	expect(main._handle_bound_action(rebound_storage) and bool(state.storage.read_only), "the rebound storage shortcut requests the view-only preview")
	state.close_storage()
	var rebound := Keys.parse("CTRL SHIFT F9")
	rebound.pressed = true
	expect(main._handle_bound_action(rebound) and commands.back() == "#auction ui browse", "the rebound exchange shortcut is handled")
	main.chat_input.show()
	main.chat_input.grab_focus()
	expect(not main._handle_bound_action(rebound), "typing in chat owns its keys instead of opening service windows")
	get_root().gui_release_focus()
	main.settings_window.capturing = "toggle_exchange"
	expect(not main._handle_bound_action(rebound), "key capture does not fire the action being rebound")
	main.settings_window.capturing = ""
	for action: String in backup:
		InputMap.action_erase_events(action)
		for key: InputEvent in backup[action]: InputMap.action_add_event(action, key)
	main._refresh_service_tooltips()
	var frame: PackedByteArray = str(fixtures.storage_readonly).hex_decode()
	frame[-1] = 2
	expect(EloriaProtocol.decode_storage_state(frame.slice(3)).type == "invalid", "invalid storage access flags are rejected")
	packet("storage_normal")
	expect(not bool(state.storage.read_only), "a normal NPC storage packet clears preview mode")
	main.queue_free()
	await process_frame
	print("Remote services UI: %d checks, %d failures" % [checks, failures])
	quit(failures)

func capture(filename: String) -> void:
	for i: int in range(5): await process_frame
	await RenderingServer.frame_post_draw
	var directory := ProjectSettings.globalize_path("res://test-artifacts/remote-services")
	DirAccess.make_dir_recursive_absolute(directory)
	root.get_texture().get_image().save_png(directory.path_join(filename))
