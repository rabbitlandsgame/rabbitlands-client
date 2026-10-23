extends SceneTree

var checks := 0
var failures := 0
var sent: Array[Dictionary] = []

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _init() -> void:
	run.call_deferred()

func sample() -> Dictionary:
	var members: Array = []
	var names := ["Alder", "Mira", "Rook", "Tamsin"]
	var rows: Array = []
	var items := [["Gold Coins", 480, 0], ["Wolf Fur", 40, 13], ["Bones", 24, 11],
		["Raw Meat", 16, 10], ["Portal Shard", 1, 55], ["Slouch Boots", 1, 359]]
	for i: int in range(6):
		var allocations := {}
		if i < 4:
			for player_name: String in names: allocations[player_name.to_lower()] = int(items[i][1]) / 4
		else: allocations["mira" if i == 4 else "rook"] = 1
		rows.append({"id": str(i), "name": items[i][0], "quantity": items[i][1],
			"image_id": items[i][2], "rare": i >= 4, "owner": "", "allocations": allocations,
			"price_gold": 0, "locked": false, "source": "creature", "sell_quantity": 0,
			"available_quantity": items[i][1], "npc_gold": (0 if i == 0 else 2) if i < 4 else 25, "npc_bundle": 1, "sale_proceeds": 0})
	for i: int in range(4):
		var username: String = names[i].to_lower()
		var preview: Array = []
		for row: Dictionary in rows:
			if row.allocations.has(username): preview.append({"name": row.name, "quantity": row.allocations[username], "image_id": row.image_id})
		members.append({"username": username, "name": names[i], "online": true,
			"portrait": {"actor_type": i + 1, "appearance": {"skin": 1, "hair": i, "head": i, "shirt": i, "pants": 0, "boots": 0}, "equipment_visuals": {}},
			"preview": preview, "more": 0, "charge_gold": 0, "rebate_gold": 0, "sale_share_gold": 0, "payment_ready": true,
			"self": i == 0, "payment_approved": true})
	return {"version": 1, "open": true, "run_id": "fixture-resin-road", "revision": 3,
		"route": "The Resin Road", "phase": "complete", "reason": "", "leader": "alder",
		"is_leader": true, "can_send": true, "members": members, "rows": rows,
		"assigned": 6, "total": 6, "page": 0, "pages": 1,
		"announcement": "1 Portal Shard", "announcement_id": 1}

func run() -> void:
	root.get_node("Network").set_process(false)
	root.content_scale_size = Vector2i.ZERO
	root.size = Vector2i(1280, 720)
	var background := TextureRect.new()
	background.texture = load("res://assets/ui/start_screen/02-amberwood-lantern-path-poster.jpg")
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.modulate = Color(0.3, 0.3, 0.3)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var ui: Control = load("res://src/ui/gauntlet_loot_window.gd").new()
	root.add_child(ui)
	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	ui.configure(atlas)
	ui.configure_sender(func(text: String) -> Error:
		sent.append(JSON.parse_string(text.trim_prefix("#gauntletloot ")))
		return OK)
	var state := sample()
	var protocol := load("res://src/network/protocol.gd")
	var decoded: Dictionary = protocol.decode_gauntlet_loot(JSON.stringify(state).to_utf8_buffer())
	expect(decoded.type == "gauntlet_loot", "valid ledger packet decodes")
	var bad := state.duplicate(true)
	bad.rows[0].allocations["outsider"] = 2
	expect(protocol.decode_gauntlet_loot(JSON.stringify(bad).to_utf8_buffer()).type == "invalid", "unadmitted recipients are rejected")
	bad = state.duplicate(true)
	bad.rows[0].quantity = 1.5
	expect(protocol.decode_gauntlet_loot(JSON.stringify(bad).to_utf8_buffer()).type == "invalid", "fractional quantities are rejected")
	ui.apply_snapshot(state)
	await process_frame
	await process_frame
	expect(ui.panel.visible and ui.table.get_child_count() == 6, "complete run opens six ledger rows")
	expect(not ui.send_button.disabled, "complete allocations enable confirmation")
	ui.split_button.pressed.emit()
	expect(sent.back().action == "split" and sent.back().revision == 3, "split sends the server revision")
	expect(ui.send_button.disabled, "pending edits disable delivery")
	ui.apply_snapshot(state)
	ui.call("_edit_item", state.rows[0])
	expect(ui.editor.visible and ui.editor_fields.size() == 4, "custom split exposes all recipients")
	ui.editor_fields["alder"].value = 480
	ui.editor_fields["mira"].value = 480
	expect(ui.editor.get_ok_button().disabled, "custom split prevents overallocation")
	state.revision = 4
	ui.apply_snapshot(state)
	expect(not ui.editor.visible, "a new snapshot dismisses a stale allocation editor")
	ui.send_button.pressed.emit()
	expect(ui.confirmation.visible, "storage delivery requires an explicit final confirmation")
	ui.confirmation.hide()
	state.is_leader = false
	ui.apply_snapshot(state)
	expect(ui.split_button.disabled and ui.send_button.disabled, "members see a read-only allocation preview")
	state.is_leader = true
	ui.apply_snapshot(state)
	ui.call("_edit_price", state.rows[4])
	expect(ui.price_dialog.visible, "rare items expose the optional gold valuation")
	ui.price_amount.get_line_edit().text = "800"
	ui.price_dialog.confirmed.emit()
	expect(sent.back().action == "price" and sent.back().price_gold == 800, "gold value is submitted as a whole server-validated amount")
	state.revision += 1
	ui.apply_snapshot(state)
	ui.call("_edit_sale", state.rows[5])
	expect(ui.sale_dialog.visible and int(ui.sale_amount.max_value) == 1, "NPC sale quantity is bounded by the available drop")
	ui.sale_amount.get_line_edit().text = "1"
	ui.sale_dialog.confirmed.emit()
	expect(sent.back().action == "sell" and sent.back().quantity == 1 and not sent.back().has("npc_gold"), "the NPC request contains a quantity, never a client-selected sale price")
	state = paid_sample()
	expect(protocol.decode_gauntlet_loot(JSON.stringify(state).to_utf8_buffer()).type == "gauntlet_loot", "rare payments and NPC proceeds decode together")
	ui.apply_snapshot(state)
	ui.send_button.pressed.emit()
	expect(ui.confirmation.dialog_text.contains("Mira pays 800") and ui.confirmation.dialog_text.contains("NPC sales add 25"), "final confirmation discloses payments and NPC sales")
	ui.confirmation.hide()
	var no_funds := state.duplicate(true)
	no_funds.members[1].payment_ready = false
	no_funds.can_send = false
	ui.apply_snapshot(no_funds)
	expect(ui.send_button.disabled and ui.status.text.contains("Mira"), "an unfunded buyer blocks confirmation with a named explanation")
	ui.apply_snapshot(state)
	var buyer_view := state.duplicate(true)
	buyer_view.is_leader = false
	buyer_view.can_send = false
	buyer_view.members[0].self = false
	buyer_view.members[1].self = true
	buyer_view.members[1].payment_approved = false
	ui.apply_snapshot(buyer_view)
	expect(ui.approve_button.visible and not ui.approve_button.disabled, "the buyer can approve their own charge while allocations remain read-only")
	ui.approve_button.pressed.emit()
	expect(sent.back().action == "approve_payment", "payment approval is an explicit buyer action")
	ui.apply_snapshot(state)
	if OS.get_cmdline_user_args().has("--render"):
		for i: int in range(150):
			await process_frame
			if ui.portraits.is_idle(): break
		await capture("ledger-1280.png")
		root.size = Vector2i(1600, 900)
		await process_frame
		await process_frame
		await capture("ledger-1600.png")
		root.size = Vector2i(1600, 1000)
		await process_frame
		await process_frame
		await capture("ledger-final.png")
		root.size = Vector2i(1024, 640)
		await process_frame
		await process_frame
		await capture("ledger-1024.png")
	ui.close()
	expect(not ui.panel.visible and ui.reopen.visible, "closing preserves a way back to reserved loot")
	ui.queue_free()
	background.queue_free()
	await process_frame
	print("Gauntlet loot UI: %d checks, %d failures" % [checks, failures])
	quit(failures)

func paid_sample() -> Dictionary:
	var state := sample()
	state.revision = 8
	state.rows[4].price_gold = 800
	state.rows[5].sell_quantity = 1
	state.rows[5].available_quantity = 0
	state.rows[5].allocations = {}
	state.rows[5].sale_proceeds = 25
	for source: String in ["compensation", "npc_sales"]:
		var total := 800 if source == "compensation" else 25
		var allocations := {}
		for i: int in range(4):
			allocations[str(state.members[i].username)] = 200 if source == "compensation" else (7 if i == 0 else 6)
		state.rows.append({"id": source, "name": "Gold Coins", "quantity": total,
			"image_id": 0, "rare": false, "owner": "", "allocations": allocations,
			"price_gold": 0, "locked": true, "source": source, "sell_quantity": 0,
			"available_quantity": total, "npc_gold": 0, "npc_bundle": 1, "sale_proceeds": 0})
	for i: int in range(4):
		var member: Dictionary = state.members[i]
		member.charge_gold = 800 if i == 1 else 0
		member.rebate_gold = 200
		member.sale_share_gold = 7 if i == 0 else 6
		member.preview.clear()
		var stacks := {}
		for row: Dictionary in state.rows:
			var quantity := int(row.allocations.get(str(member.username), 0))
			if quantity > 0:
				if not stacks.has(str(row.name)): stacks[str(row.name)] = {"name": row.name, "quantity": 0, "image_id": row.image_id}
				stacks[str(row.name)].quantity += quantity
		member.preview = stacks.values()
	state.total = 8
	state.assigned = 8
	return state

func capture(filename: String) -> void:
	await RenderingServer.frame_post_draw
	var directory := ProjectSettings.globalize_path("res://test-artifacts/gauntlet-loot")
	DirAccess.make_dir_recursive_absolute(directory)
	root.get_texture().get_image().save_png(directory.path_join(filename))
