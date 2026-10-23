extends SceneTree

var checks := 0
var failures := 0
var sent: Array[Dictionary] = []

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func find_button(parent: Node, text: String) -> Button:
	if parent is Button and parent.text == text: return parent
	for child: Node in parent.get_children():
		var found := find_button(child, text)
		if found != null: return found
	return null

func contains_label(parent: Node, text: String) -> bool:
	if parent is Label and parent.text.contains(text): return true
	for child: Node in parent.get_children():
		if contains_label(child, text): return true
	return false

func run() -> void:
	root.get_node("Network").set_process(false)
	root.content_scale_size = Vector2i.ZERO
	root.gui_embed_subwindows = true
	root.size = Vector2i(1600, 1000)
	var background := TextureRect.new()
	background.texture = load("res://assets/ui/start_screen/02-amberwood-lantern-path-poster.jpg")
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.modulate = Color(0.3, 0.3, 0.3)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var script: GDScript = load("res://src/ui/gauntlet_loot_window.gd")
	if script == null or not script.can_instantiate():
		quit(1)
		return
	var ui: Control = script.new()
	root.add_child(ui)
	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	ui.configure(atlas)
	ui.configure_sender(func(message: String) -> Error:
		sent.append(JSON.parse_string(message.trim_prefix("#gauntletloot ")))
		return OK)
	var protocol := load("res://src/network/protocol.gd")
	var state: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/party_exchange.json"))
	expect(protocol.decode_gauntlet_loot(JSON.stringify(state).to_utf8_buffer()).type == "gauntlet_loot", "real server party-exchange snapshot decodes")
	var bad := state.duplicate(true)
	bad.exchange[0].votes[0].username = "outsider"
	expect(protocol.decode_gauntlet_loot(JSON.stringify(bad).to_utf8_buffer()).type == "invalid", "an unadmitted voter is rejected")
	bad = state.duplicate(true)
	bad.rows[0].exchange_quantity += 1
	expect(protocol.decode_gauntlet_loot(JSON.stringify(bad).to_utf8_buffer()).type == "invalid", "exchange escrow must conserve the original stack")
	ui.apply_snapshot(state)
	await process_frame
	await process_frame
	expect(ui._exchange_view.visible and ui._exchange_cards.get_child_count() == 2, "completed delivery opens the two durable party listings")
	expect(not ui.reopen.visible, "the loot shortcut does not overlap the open window")
	var no := find_button(ui._exchange_cards, "No")
	expect(no != null and not no.disabled, "eligible members can vote asynchronously")
	no.pressed.emit()
	expect(sent.back().action == "vote_withdrawal" and sent.back().vote == "no" and sent.back().request_id == state.exchange[0].request_id, "a vote names the exact persisted request")
	ui.apply_snapshot(state)
	var withdraw := find_button(ui._exchange_cards, "Request withdrawal")
	expect(withdraw != null, "an active listing without a vote offers a withdrawal request")
	withdraw.pressed.emit()
	expect(sent.back().action == "request_withdrawal", "requesting withdrawal does not send an ordinary auction cancellation")
	ui.apply_snapshot(state)
	if OS.get_cmdline_user_args().has("--render"):
		await capture("party-exchange.png")
		root.size = Vector2i(1024, 640)
		await capture("party-exchange-1024.png")
	var ready := state.duplicate(true)
	ready.exchange[0].vote_state = "ready"
	ready.exchange_can_withdraw = false
	for voter: Dictionary in ready.exchange[0].votes: voter.vote = "yes"
	ui.apply_snapshot(ready)
	var collect := find_button(ui._exchange_cards, "Collect approved withdrawal")
	expect(collect != null and collect.disabled and contains_label(ui._exchange_cards, "Awaiting collection"), "approved withdrawals wait for an Exchange NPC")
	ready.exchange_can_withdraw = true
	ui.apply_snapshot(ready)
	collect = find_button(ui._exchange_cards, "Collect approved withdrawal")
	expect(not collect.disabled, "the server's nearby NPC permission enables approved collection")
	collect.pressed.emit()
	expect(sent.back().action == "withdraw_approved" and sent.back().request_id == ready.exchange[0].request_id, "collection names the exact approved withdrawal")
	ui.apply_snapshot(state)
	root.size = Vector2i(1600, 1000)
	var propose := find_button(ui._exchange_cards, "Propose price…")
	expect(propose != null, "an active listing offers a party price proposal")
	propose.pressed.emit()
	await process_frame
	expect(ui.reprice_dialog.visible and ui.reprice_dialog.size.y < 430 and int(ui.reprice_amount.value) == 5, "price proposals show the current price in a bounded dialog")
	expect(ui.reprice_dialog.get_ok_button().disabled, "the unchanged current price cannot start a proposal")
	ui.reprice_amount.get_line_edit().text = "8"
	ui.reprice_amount.apply()
	if OS.get_cmdline_user_args().has("--render"):
		await capture("party-exchange-price-dialog.png")
	ui.reprice_dialog.confirmed.emit()
	ui.reprice_dialog.hide()
	expect(sent.back().action == "request_price_change" and sent.back().unit_price == 8 and sent.back().run_id == state.run_id and sent.back().listing_id == state.exchange[1].listing_id, "a proposal names the original ledger, listing and selected price")
	var reprice: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/party_exchange_reprice.json"))
	expect(protocol.decode_gauntlet_loot(JSON.stringify(reprice).to_utf8_buffer()).type == "gauntlet_loot", "real server price proposals decode")
	bad = reprice.duplicate(true)
	bad.exchange[1].vote_kind = "direct_edit"
	expect(protocol.decode_gauntlet_loot(JSON.stringify(bad).to_utf8_buffer()).type == "invalid", "unknown proposal kinds are rejected")
	bad = reprice.duplicate(true)
	bad.exchange[1].proposed_price = 0
	expect(protocol.decode_gauntlet_loot(JSON.stringify(bad).to_utf8_buffer()).type == "invalid", "price proposals require a positive price")
	ui.apply_snapshot(reprice)
	expect(contains_label(ui._exchange_cards, "Proposed price: 8 GC per item") and contains_label(ui._exchange_cards, "Current: 5 GC until approval"), "voters see both the proposed and current price")
	expect(find_button(ui._exchange_cards, "Propose price…") == null and find_button(ui._exchange_cards, "Request withdrawal") == null, "an open proposal blocks overlapping requests")
	var price_no := find_button(ui._exchange_cards.get_child(1), "No")
	price_no.pressed.emit()
	expect(sent.back().action == "vote_price_change" and sent.back().request_id == reprice.exchange[1].request_id and sent.back().vote == "no", "price votes name their purpose and exact persisted request")
	ui.apply_snapshot(reprice)
	if OS.get_cmdline_user_args().has("--render"):
		await capture("party-exchange-price-vote.png")
		root.size = Vector2i(1024, 640)
		await process_frame
		await process_frame
		ui._exchange_cards.get_parent().scroll_vertical = 100000
		await capture("party-exchange-price-vote-1024.png")
		root.size = Vector2i(1600, 1000)
	ui.call("_propose_price", state.exchange[1])
	ui.close()
	expect(not ui.reprice_dialog.visible, "closing the ledger closes its price proposal editor")
	expect(ui.reopen.visible, "party listings remain accessible after closing the distribution window")
	var stage: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/party_exchange_staged.json"))
	expect(protocol.decode_gauntlet_loot(JSON.stringify(stage).to_utf8_buffer()).type == "gauntlet_loot", "the real staged-listing response decodes")
	root.size = Vector2i(1600, 1000)
	ui.apply_snapshot(stage)
	var other := state.duplicate(true)
	other.open = false
	ui.apply_snapshot(other)
	expect(ui._state.run_id == stage.run_id, "an asynchronous update for another run preserves the selected ledger")
	ui.call("_edit_exchange", stage.rows[1])
	await process_frame
	expect(ui.exchange_dialog.visible and ui.exchange_dialog.size.y < 400, "listing quantity and price fit a bounded dialog")
	expect(int(ui.exchange_price.value) == 800, "editing a staged listing preserves its selected per-item price")
	ui.exchange_price.get_line_edit().text = "1200"
	ui.exchange_amount.get_line_edit().text = "1"
	if OS.get_cmdline_user_args().has("--render"):
		await capture("party-exchange-listing-dialog.png")
	ui.exchange_dialog.confirmed.emit()
	ui.exchange_dialog.hide()
	expect(sent.back().action == "exchange" and sent.back().unit_price == 1200 and sent.back().quantity == 1, "the chosen quantity and price are submitted for authoritative staging")
	ui.apply_snapshot(stage)
	ui.send_button.pressed.emit()
	expect(ui.confirmation.dialog_text.contains("Exchange:") and ui.confirmation.dialog_text.contains("Future sale proceeds"), "distribution confirmation discloses the party exchange listings")
	ui.confirmation.hide()
	ui.call("_edit_exchange", stage.rows[1])
	other.revision = stage.revision
	other.open = true
	ui.apply_snapshot(other)
	expect(not ui.exchange_dialog.visible and not ui.reprice_dialog.visible, "switching runs closes stale editors even when revisions match")
	ui.apply_snapshot(stage)
	if OS.get_cmdline_user_args().has("--render"):
		await capture("party-exchange-staging.png")
	ui.queue_free()
	background.queue_free()
	await process_frame
	print("Party exchange UI: %d checks, %d failures" % [checks, failures])
	quit(failures)

func capture(filename: String) -> void:
	for i: int in range(150):
		await process_frame
		if i > 3 and root.get_node("GauntletLootLayer").portraits.is_idle(): break
	await RenderingServer.frame_post_draw
	var directory := ProjectSettings.globalize_path("res://test-artifacts/gauntlet-loot")
	DirAccess.make_dir_recursive_absolute(directory)
	root.get_texture().get_image().save_png(directory.path_join(filename))
