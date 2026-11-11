extends SceneTree
const Protocol := preload("res://src/network/protocol.gd")
const Atlas := preload("res://src/ui/item_atlas.gd")
const Tiers := preload("res://src/state/item_instance_tiers.gd")
var failures := 0
var checks := 0
var main: Control
var window: PanelContainer
var state: Node

func _init() -> void: call_deferred("run")
func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)
func frames(count: int = 5) -> void:
	for _index: int in count: await process_frame

func sample() -> Dictionary:
	return {"version": 1, "enabled": true, "max_batch": 100, "shard_item": "Enchanting Shards", "shard_available": 45, "gold_available": 500,
		"items": [{"instance_id": 502, "slot": 4, "name": "Phoenix Helm", "image_id": 182, "tier": "rare", "quality": 110, "durability": 96, "max_durability": 100,
			"effects": ["Plated: +20 armor.", "Vital: +50 maximum health.", "Spellguard: +25% less incoming spell damage.", "Restorative: +10 mana per normal regeneration tick."],
			"outputs": [{"name": "Earth Essence", "quantity": 8, "image_id": 0}, {"name": "Life Essence", "quantity": 15, "image_id": 0}, {"name": "Magic Essence", "quantity": 7, "image_id": 0}, {"name": "Enchanting Shards", "quantity": 15, "image_id": 633}]},
			{"instance_id": 503, "slot": 5, "name": "Phoenix Helm", "image_id": 182, "tier": "magic", "quality": 100, "durability": 90, "max_durability": 100, "effects": ["Vital: +5 maximum health."], "outputs": [{"name": "Life Essence", "quantity": 5, "image_id": 0}, {"name": "Enchanting Shards", "quantity": 2, "image_id": 633}]}],
		"recipes": [{"normal": "Life Essence", "result": "Enriched Life Essence", "image_id": 617, "normal_cost": 100, "shard_cost": 20, "gold_fee": 100, "normal_available": 240, "result_available": 0}],
		"quote": null, "error": "", "message": ""}

## An item detail as each kind of server sends it: an older one ends at the
## last text, one that keeps enchanted copies adds the tier byte (0 = plain).
func item_detail(tier_byte: int = -1) -> PackedByteArray:
	var detail := PackedByteArray([182, 0, 1, 0, 0, 0, 0])
	for text: String in ["Phoenix Helm", "Armor", "head", "Plain helm", "Armor 5", "", ""]:
		detail.append_array(text.to_utf8_buffer())
		detail.append(0)
	if tier_byte >= 0:
		detail.append(tier_byte)
	return detail

func receive(value: Dictionary) -> void:
	value["request_id"] = window.get("_serial")
	state.call("_on_packet", 186, JSON.stringify(value).to_utf8_buffer())

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 800)
	state = root.get_node("AppState")
	expect(Protocol.CLIENT_CAPABILITIES.has("enchanting_recovery_v1"), "capability advertised")
	var encoded := Protocol.enchanting_recovery_request({"op": "quote", "action": "disenchant", "instance_id": 502, "request_id": 1})
	var command: Dictionary = JSON.parse_string(encoded.slice(3).get_string_from_utf8())
	expect(encoded[0] == 186 and command.version == 1 and command.instance_id == 502, "request identifies exact copy")
	expect(Protocol.decode_enchanting_recovery(JSON.stringify(sample()).to_utf8_buffer()).type == "enchanting_recovery", "snapshot decodes")
	var fixture := OS.get_environment("RL_RECOVERY_WIRE_FIXTURE")
	if not fixture.is_empty():
		var packets: Array = JSON.parse_string(FileAccess.get_file_as_string(fixture))
		for packet: String in packets:
			expect(Protocol.decode_server(186, packet.to_utf8_buffer()).type == "enchanting_recovery", "real server recovery packet decodes")
	var invalid := sample()
	invalid.items[0].effects.append("fifth")
	expect(Protocol.decode_enchanting_recovery(JSON.stringify(invalid).to_utf8_buffer()).type == "invalid", "overfull effects refused")
	var atlas := Atlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	expect(atlas.supports(633) and not atlas.uses_substitute(633), "shards have a registered icon")
	expect(atlas.icon_for(633) != null and atlas.icon_source(633).path.ends_with("attuned.png"), "painted shard gem loads")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/enchanting-recovery/test.cfg"
	root.add_child(main)
	await frames(10)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	state.set("authenticated", true)
	# A server that predates enchanted copies never answers the window, so
	# nothing offers it until the server shows it keeps them.
	var more_menu: PopupMenu = main.inventory_workspace.more.get_popup()
	var refine: Button = main.mixing_workspace.refine
	more_menu.about_to_popup.emit()
	expect(not state.enchanting_recovery_available and more_menu.get_item_index(23) < 0 and not refine.visible,
		"no Disenchant & refine entries before the server shows it can answer")
	main.inventory_workspace.recovery_window.open(0)
	expect(not main.inventory_workspace.recovery_window.visible, "the window itself will not ask a server that cannot answer")
	state.call("_on_packet", 225, item_detail())
	more_menu.about_to_popup.emit()
	expect(not state.enchanting_recovery_available and more_menu.get_item_index(23) < 0 and not refine.visible,
		"an item detail without the tier byte offers nothing")
	state.call("_on_packet", 225, item_detail(0))
	more_menu.about_to_popup.emit()
	expect(state.enchanting_recovery_available and more_menu.get_item_index(23) == more_menu.get_item_index(21) + 1
		and refine.visible, "a plain item's tier byte offers both entries, the menu one under Customize")
	var offered_count := more_menu.item_count
	more_menu.about_to_popup.emit()
	expect(more_menu.get_item_index(23) == more_menu.get_item_index(21) + 1 and more_menu.item_count == offered_count,
		"reopening the menu does not add the entry twice")
	window = main.inventory_workspace.recovery_window
	window.open(0, 4)
	receive(sample())
	await frames()
	expect(window.selected_id == 502 and window.copies.item_count == 2, "inspection preselects the exact backpack copy")
	expect(window.selected_title.text == "Phoenix Helm", "tier labels stay out of item names")
	expect(window.selected_title.get_theme_color("font_color") == Tiers.color("rare"), "yellow name conveys tier")
	expect(window.details.get_child_count() == 7, "four effects, returns and condition shown")
	expect(window.confirm_button.disabled, "confirmation requires authoritative preview")
	var data := sample()
	data.quote = {"token": "one-use-token", "action": "disenchant", "name": data.items[0].name, "effects": data.items[0].effects, "inputs": [{"name": "Phoenix Helm", "quantity": 1}], "outputs": data.items[0].outputs, "gold_fee": 0}
	receive(data)
	expect(not window.confirm_button.disabled, "valid server quote enables confirmation")
	window.call("_ask_confirmation")
	expect(window.confirmation.visible and window.confirmation.dialog_text.contains("Permanently") and window.confirmation.dialog_text.contains("15 Enchanting Shards"), "destructive confirmation shows effects and exact returns")
	window.confirmation.hide()
	if OS.get_cmdline_user_args().has("--capture"):
		await capture("disenchant")
	window.copies.select(1)
	window.copies.item_selected.emit(1)
	expect(window.selected_id == 503 and window.confirm_button.disabled, "changing exact copy invalidates quote")
	data.request_id = int(window.get("_serial")) - 1
	state.call("_on_packet", 186, JSON.stringify(data).to_utf8_buffer())
	expect(window.confirm_button.disabled and window.selected_id == 503, "stale quote response is ignored")
	window.tabs.current_tab = 1
	expect(window.confirm_button.disabled and window.refining_text.text.contains("20 Enchanting Shards") and window.refining_text.text.contains("100 Life Essence") and window.refining_text.text.contains("100 gold fee"), "refining shows all configured per-unit costs")
	window.quantity.value = 2
	expect(window.refining_text.text.contains("40 Enchanting Shards") and window.refining_text.text.contains("200 gold fee"), "batch costs scale exactly")
	data = sample()
	data.quote = {"token": "refine-token", "action": "refine", "name": "Enriched Life Essence", "inputs": [{"name": "Life Essence", "quantity": 200}, {"name": "Enchanting Shards", "quantity": 40}], "outputs": [{"name": "Enriched Life Essence", "quantity": 2}], "gold_fee": 200}
	receive(data)
	if OS.get_cmdline_user_args().has("--capture"):
		await capture("refine")
	window.quantity.value = 3
	expect(window.confirm_button.disabled, "batch change invalidates quote")
	receive(data)
	var inventory_before: Dictionary = state.inventory.duplicate(true)
	window.call("_confirm")
	expect(state.inventory == inventory_before and window.quote.is_empty(), "confirmation never mutates materials optimistically")
	window.set("_pending_op", "confirm")
	var serial: int = window.get("_serial")
	state.state_changed.emit(&"inventory")
	expect(int(window.get("_serial")) == serial, "inventory notification preserves pending confirmation receipt")
	data = sample()
	data.message = "Enriched essence refined."
	receive(data)
	expect(window.status.text == data.message, "committed receipt is displayed")
	receive(sample())
	# A server whose copies predate recovery, or a practice world, never answers.
	# The preview has no link, so stand in for one that sends but never hears back.
	var real_send: Callable = window.send_request
	window.send_request = func(_request: Dictionary) -> Error: return OK
	window.reply_seconds = 0.2
	window.snapshot = {}
	window.call("_refresh")
	var asked: int = window.get("_serial")
	await create_timer(0.5).timeout
	expect(not bool(window.get("_busy")) and window.status.text.contains("not available here"),
		"a request nothing ever answered stops waiting and says the feature is not here")
	var late := sample()
	late.request_id = asked
	state.call("_on_packet", 186, JSON.stringify(late).to_utf8_buffer())
	await frames()
	expect(int(window.get("_serial")) == asked and window.copies.item_count == 2, "a late answer to that request still lands")
	window.call("_send", {"op": "quote", "action": "disenchant", "instance_id": window.selected_id})
	await create_timer(0.5).timeout
	expect(window.status.text.contains("has not answered yet") and not window.preview_button.disabled,
		"a slow quote on a server that has answered asks for a retry and unlocks Preview")
	window.call("_send", {"op": "confirm", "token": "slow-token"})
	asked = window.get("_serial")
	await create_timer(0.5).timeout
	expect(window.status.text.contains("Refresh to see") and str(window.get("_pending_op")) == "confirm",
		"a slow confirmation says to refresh and stays pending")
	state.state_changed.emit(&"inventory")
	var receipt := sample()
	receipt.request_id = asked
	receipt.message = "Copy disenchanted."
	state.call("_on_packet", 186, JSON.stringify(receipt).to_utf8_buffer())
	expect(int(window.get("_serial")) == asked and window.status.text == receipt.message,
		"the inventory sent ahead of a late receipt does not cancel it")
	window.send_request = real_send
	window.reply_seconds = 10.0
	root.size = Vector2i(900, 680)
	root.content_scale_size = Vector2i(900, 680)
	await frames()
	print("Recovery narrow refine bounds: ", window.get_global_rect(), " minimum: ", window.get_combined_minimum_size())
	expect(Rect2(Vector2.ZERO, Vector2(804, 592)).encloses(window.get_global_rect()), "window fits narrow viewport outside HUD")
	window.tabs.current_tab = 0
	await frames()
	print("Recovery narrow salvage bounds: ", window.get_global_rect(), " minimum: ", window.get_combined_minimum_size())
	expect(Rect2(Vector2.ZERO, Vector2(804, 592)).encloses(window.get_global_rect()), "salvage fits narrow viewport outside HUD")
	state.set("authenticated", false)
	state.state_changed.emit(&"connection")
	expect(not window.visible and window.quote.is_empty(), "disconnect closes destructive flow")
	state.call("_on_connection_state_changed", "disconnected")
	more_menu.about_to_popup.emit()
	expect(not state.enchanting_recovery_available and more_menu.get_item_index(23) < 0 and not refine.visible,
		"a dropped connection forgets the offer: the next server may be an older one")
	state.call("_on_packet", 186, JSON.stringify(sample()).to_utf8_buffer())
	expect(state.enchanting_recovery_available and refine.visible, "a recovery reply itself also shows the server can answer")
	print("Enchanting recovery: %d checks, %d failures" % [checks, failures])
	main.queue_free()
	await frames(2)
	quit(failures)

func capture(label: String) -> void:
	await frames(8)
	await RenderingServer.frame_post_draw
	var folder := "res://test-artifacts/enchanting-recovery"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	root.get_texture().get_image().save_png(folder + "/" + label + ".png")
