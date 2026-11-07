extends SceneTree
## Production merchant interaction checks; set ELORIA_ARTIFACT_DIR for screenshots.

const SHOP := "5b00fa00000014000000500000000a0042657474616e79204f726c000000050000000200000003000000010042726561640001000a00000006000000020000000900436f6f6b6564204d65617400020005000000030000000c00000065005361676500030005000000010000000000000055005265656400040004000000010000000000000052024f6c6976650005000a000000040000000000000053024c656d6f6e000600050000000100000004000000f901456d707479205669616c0007001e0000000a000000000000000a00526177204d6561740008000a0000000300000002000000da01506f74696f6e206f66204d696e6f72204865616c696e6700090032000000140000000000000008004d6f7274617220616e6420506573746c65000a00010000000100000001000000010000000100000001000000010000000100000001000000010000000a004120726f756e64206c6f6166207769746820612073616c7465642063727573742c2062616b65642066726f6d2067726f756e642077686561742e204974206b6565707320666f72206461797320696e2061207061636b20616e6420612074726176656c6c6572206f6e20746865697220666565742e00416e20696e646570656e64656e746c7920646566696e656420456c6f726961206974656d20666f7220746865207465737420656e7669726f6e6d656e742e004120636f6d6d6f6e204e796d6172612068657262207265736f757263652e004120636f6d6d6f6e204e796d617261206669627265207265736f757263652e00477265656e20616e6420626c61636b2066726f6d207468652073616d65206272616e63682c2073616c74656420696e2061207477697374206f6620636c6f74682e205468652069736c652065617473207468656d206279207468652068616e6466756c2e00546869636b2d736b696e6e656420616e6420736861727020656e6f75676820746f2077616b652061207361696c6f722e205468652067617264656e20746f776e2073656e647320637261746573206f66207468656d206163726f7373207468652077617465722e00436c65616e20676c6173732c20726561647920666f7220776861746576657220697320627265776564206e6578742e00416e20696e646570656e64656e746c7920646566696e656420456c6f726961206974656d20666f7220746865207465737420656e7669726f6e6d656e742e0041207377616c6c6f77206f662072656420746f6e6963207468617420636c6f73657320736d616c6c20776f756e64732e20546865207669616c20697320776f727468206b656570696e672e00416e20696e646570656e64656e746c7920646566696e656420456c6f726961206974656d20666f7220746865207465737420656e7669726f6e6d656e742e00"

var failures := 0
var windows: Control

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	root.gui_embed_subwindows = true
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await _settle()
	for name: String in ["LoginPanel", "LoginBackground", "CreationPanel", "ConnectionBanner"]:
		var panel := main.get_node_or_null("%" + name) as Control
		if panel != null:
			panel.hide()
	(main.get_node("GameView") as Control).show()
	var state := root.get_node("/root/AppState")
	state.set("authenticated", true)
	windows = main.get("extension_windows") as Control
	windows.preferences_path = "user://merchant-presets-integration.cfg"
	var preset_config := ConfigFile.new()
	preset_config.set_value("unrelated", "sentinel", 37)
	preset_config.save(windows.preferences_path)
	windows._merchant_quantities.load_file(windows.preferences_path)
	windows._sync_merchant_quantity_presets()
	# Exact output of the server merchant_state builder using Bettany's stock.
	state.call("_on_packet", 223, SHOP.hex_decode())
	await _settle()
	_select(0)
	_expect(windows.merchant_buy_list.item_count == 10, "all shop goods are visible")
	_expect(windows.merchant_sell_list.item_count == 5, "only owned goods the merchant buys appear in the backpack")
	_expect(windows.merchant_description.text.begins_with("A round loaf with a salted crust"),
		"opening the shop describes the initially selected item")
	_select(8)
	_expect(windows.merchant_description.text == "A swallow of red tonic that closes small wounds. The vial is worth keeping.",
		"selecting shop goods shows their server description inside the shop")
	_expect(not windows.detail_panel.visible, "shop selection does not open a separate inspection window")
	windows.merchant_quantity.text = "3"
	windows._sync_merchant_summary()
	_expect(windows._merchant_trade_command() == "#shop buy 91 8 3", "buy retains the server item id")
	_expect(windows.merchant_totals.text.contains("Cost: 30 gc")
		and windows.merchant_totals.text.contains("Gold after: 220 gc")
		and windows.merchant_totals.text.contains("Carry after: 23/80"), "purchase previews cost, gold and load")
	_expect(not windows.merchant_trade.disabled, "an affordable purchase is enabled")
	windows.merchant_panel.find_child("MerchantQuantity5", true, false).pressed.emit()
	_expect(windows.merchant_quantity.text == "5" and windows.merchant_totals.text.contains("Cost: 50 gc"),
		"quantity presets update the amount and cost without submitting a trade")
	windows.merchant_panel.find_child("MerchantQuantity100", true, false).pressed.emit()
	_expect(windows.merchant_quantity.text == "100" and windows.merchant_trade.disabled,
		"unaffordable presets retain the normal transaction limits")
	windows.merchant_panel.find_child("MerchantQuantity1", true, false).pressed.emit()
	_expect(windows.merchant_quantity.text == "1" and not windows.merchant_trade.disabled,
		"the one-item preset restores an affordable transaction")
	var fifth := windows.merchant_panel.find_child("MerchantQuantity1000", true, false) as Button
	fifth.pressed.emit()
	_expect(windows.merchant_quantity.text == "1000" and windows.merchant_trade.disabled,
		"the fifth preset selects 1000 and respects trade limits")
	windows._merchant_set_quantity(3)
	await _capture("merchant-default-presets.png")
	var right_click := InputEventMouseButton.new()
	right_click.button_index = MOUSE_BUTTON_RIGHT
	right_click.pressed = true
	fifth.gui_input.emit(right_click)
	_expect(windows._merchant_preset_dialog.visible and windows._merchant_preset_input.text == "1000",
		"right-click opens the preset editor with the current value")
	await _capture("merchant-preset-editor.png")
	windows._merchant_preset_input.text = "0"
	windows._merchant_preset_dialog.confirmed.emit()
	_expect(windows._merchant_preset_dialog.visible and fifth.text == "1000",
		"invalid edits keep the previous preset and the editor open")
	windows._merchant_preset_input.text = "1000000"
	windows._merchant_preset_dialog.confirmed.emit()
	_expect(fifth.text == "1000000", "the maximum valid preset can be saved")
	await _capture("merchant-large-preset.png")
	fifth.gui_input.emit(right_click)
	windows._merchant_preset_input.text = "2500"
	windows._merchant_preset_input.text_submitted.emit("2500")
	_expect(not windows._merchant_preset_dialog.visible and fifth.text == "2500",
		"saving an edit updates the preset label")
	var reloaded := preload("res://src/ui/merchant_quantities.gd").new()
	reloaded.load_file(windows.preferences_path)
	_expect(reloaded.values[4] == 2500, "a new settings instance restores the saved value")
	preset_config.load(windows.preferences_path)
	_expect(preset_config.get_value("unrelated", "sentinel", 0) == 37,
		"preset saves preserve unrelated settings")
	state.get("merchant")["actor_id"] = 92
	state.get("merchant")["npc_name"] = "Another merchant"
	windows._sync_merchant()
	fifth.pressed.emit()
	_expect(fifth.text == "2500" and windows.merchant_quantity.text == "2500",
		"the edited preset is used at another NPC")
	_expect(windows._merchant_trade_command().begins_with("#shop buy 92 "),
		"changing NPC retains the new merchant's identity")
	fifth.gui_input.emit(right_click)
	windows._merchant_preset_input.text = "42"
	windows._merchant_preset_dialog.canceled.emit()
	windows._merchant_preset_dialog.hide()
	_expect(fifth.text == "2500", "canceling an edit preserves its saved value")
	state.get("merchant")["actor_id"] = 91
	state.get("merchant")["npc_name"] = "Bettany Orl"
	windows._sync_merchant()
	_select(8)
	windows._merchant_set_quantity(3)
	await _capture("merchant-buy.png")
	var full_grid_height: float = windows.merchant_buy_list.size.y
	windows._merchant_set_maximum()
	_expect(windows.merchant_quantity.text == "25", "buy Max is limited by gold")
	state.get("merchant")["capacity"] = 22
	windows._merchant_set_maximum()
	_expect(windows.merchant_quantity.text == "2", "buy Max also respects carrying space")
	windows.merchant_quantity.text = "3"
	windows._sync_merchant_summary()
	_expect(windows.merchant_trade.disabled, "an overweight purchase is disabled")
	state.get("merchant")["capacity"] = 80
	_select(2, true)
	_expect(windows.merchant_description.text == "A common Nymara herb resource.",
		"selecting a backpack item replaces the previous description")
	windows.merchant_quantity.text = "4"
	windows._sync_merchant_summary()
	_expect(windows._merchant_trade_command() == "#shop sell 91 2 4", "filtered backpack rows retain their server ids")
	_expect(windows.merchant_buy_list.get_selected_items().is_empty(), "the active sale clears the buy selection")
	_expect(windows.merchant_totals.text.contains("Receive: 12 gc")
		and windows.merchant_totals.text.contains("Gold after: 262 gc")
		and windows.merchant_totals.text.contains("Carry after: 16/80"), "sale previews proceeds, gold and load")
	await _capture("merchant-sell.png")
	windows._merchant_set_maximum()
	_expect(windows.merchant_quantity.text == "12", "sell Max uses the owned quantity")
	windows.merchant_quantity.text = "13"
	windows._sync_merchant_summary()
	_expect(windows.merchant_trade.disabled, "overselling is disabled")
	# Reordering a refreshed packet must keep the same server item selected.
	(state.get("merchant")["items"] as Array).reverse()
	windows._sync_merchant()
	_expect(windows._merchant_entry().name == "Sage", "refresh preserves selection by server id")
	_expect(windows.merchant_description.text == "A common Nymara herb resource.",
		"refresh keeps the description attached to the selected server item")
	var selected: Dictionary = windows._merchant_entry()
	selected["description"] = "Long description [b]plain text[/b]. ".repeat(120)
	windows._sync_merchant_summary()
	await _capture("merchant-long-description.png")
	_expect(not windows.merchant_description.bbcode_enabled,
		"item descriptions display as plain text")
	_expect(windows.merchant_description.get_v_scroll_bar().max_value > windows.merchant_description.size.y,
		"long descriptions scroll within their card")
	selected.erase("description")
	windows._sync_merchant_summary()
	_expect(windows.merchant_description.text == "No description available.",
		"older server packets do not leave a previous item's description on screen")
	# Filtering, search and sorting never change server IDs or acknowledge trades.
	windows._on_merchant_mode("buy")
	_select(0)
	windows.merchant_sort.select(1)
	windows._merchant_browse_changed(1)
	_expect(windows._merchant_entry().index == 0, "sorting preserves the selected server item")
	windows._merchant_filter_changed("Food")
	_expect(windows.merchant_buy_list.item_count == 4, "Food shows only food items")
	_expect(windows._merchant_entry().index == 0, "type filtering preserves a matching selection")
	_search("Lemon")
	_expect(windows.merchant_buy_list.item_count == 1 and windows.merchant_trade.disabled,
		"search narrows the type and clears a hidden selection")
	_expect(windows.merchant_buy_list.get_item_metadata(0) == 5, "search keeps Lemon's server ID")
	await _settle()
	_expect(windows.merchant_buy_list.size.y < full_grid_height,
		"a one-item search does not reserve empty item rows")
	await _capture("merchant-single-result.png")
	_select(5)
	windows.merchant_quantity.text = "2"
	_expect(windows._merchant_trade_command() == "#shop buy 91 5 2", "filtered purchase sends the exact server ID")
	windows._merchant_request_pending = true
	windows.merchant_sort.select(2)
	windows._merchant_browse_changed(2)
	windows.merchant_panel.find_child("MerchantQuantity10", true, false).pressed.emit()
	_expect(windows._merchant_request_pending and windows.merchant_trade.disabled,
		"browsing cannot release an in-flight request")
	windows._merchant_request_pending = false
	_search("zz-no-match")
	_expect(windows.merchant_empty_pack.visible and windows.merchant_trade.disabled,
		"empty search results explain why trading is unavailable")
	await _capture("merchant-empty-search.png")
	_search("")
	windows._merchant_filter_changed("All")
	windows._on_merchant_mode("sell")
	_expect(not windows.merchant_buy_list.visible and windows.merchant_sell_list.visible,
		"tabs show one grid at a time")
	_select(2, true)
	windows.merchant_quantity.text = "4"
	await _capture("merchant-sell-filtered.png")
	var bundle: Dictionary = windows._merchant_entry()
	bundle["sell_quantity"] = 2
	bundle["sell_price"] = 1
	windows._sync_merchant()
	_select(2, true)
	_expect(windows.merchant_quantity.text == "2", "selecting a bundle starts with one complete lot")
	windows.merchant_panel.find_child("MerchantQuantity5", true, false).pressed.emit()
	_expect(windows.merchant_trade.disabled, "a preset cannot sell a partial bundle")
	windows._merchant_set_maximum()
	_expect(windows.merchant_quantity.text == "12" and windows.merchant_totals.text.contains("Receive: 6 gc"),
		"Max and totals respect sale bundles")
	_expect(windows._merchant_trade_command() == "#shop sell 91 2 12", "bundle sale retains the exact quantity and ID")
	await _capture("merchant-sale-bundle.png")
	# Large stock scrolls without pushing the trade controls out of the window.
	var original: Array = state.get("merchant")["items"].duplicate(true)
	var large_stock: Array = []
	for number: int in range(60):
		var item: Dictionary = original[0].duplicate(true)
		item["index"] = 100 + number
		item["name"] = "Demo %02d" % number
		item["category"] = "Food"
		large_stock.append(item)
	state.get("merchant")["items"] = large_stock
	windows._on_merchant_mode("buy")
	windows._sync_merchant()
	_select(159)
	await _settle()
	var large_height: float = windows.merchant_buy_list.size.y
	_expect(large_height <= 200 and windows.merchant_buy_list.get_v_scroll_bar().visible,
		"large stock uses a bounded scrolling grid")
	windows._sync_merchant()
	await _capture("merchant-large-stock.png")
	_expect(windows._merchant_entry().index == 159, "a scrolled selection survives refreshed stock")
	_search("Demo 59")
	await _settle()
	_expect(windows.merchant_buy_list.size.y < large_height,
		"filtering a scrolled list removes unused rows")
	await _capture("merchant-large-stock-filtered.png")
	_search("")
	state.get("merchant")["items"] = original
	windows._on_merchant_mode("sell")
	windows._sync_merchant()
	for entry: Dictionary in state.get("merchant")["items"]:
		entry["owned"] = 0
	windows._sync_merchant()
	_expect(windows.merchant_empty_pack.visible and windows.merchant_trade.disabled,
		"an empty sellable backpack explains why trading is unavailable")
	_expect(windows.merchant_description.text == "Select an item to read its description.",
		"clearing the selection clears its description")
	state.set("authenticated", false)
	main.queue_free()
	await process_frame
	print("merchant shop/backpack checks: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _settle() -> void:
	for unused: int in range(5):
		await process_frame

func _capture(filename: String) -> void:
	await _settle()
	var bounds: Rect2 = windows.merchant_panel.get_global_rect()
	_expect(bounds.end.x <= 1184 and bounds.end.y <= 636, "the merchant panel clears the HUD rail and toolbar")
	var action: Rect2 = windows.merchant_trade.get_global_rect()
	_expect(bounds.encloses(action), "the transaction button stays inside the panel")
	var presets := windows.merchant_panel.find_child("MerchantQuantityPresets", true, false) as Control
	_expect(presets.get_global_rect().position.x > windows.merchant_quantity.get_global_rect().end.x,
		"quantity presets sit to the right of the amount field")
	_expect(action.position.y > presets.get_global_rect().end.y and action.end.x >= bounds.end.x - 12,
		"the transaction button sits at the bottom right")
	var description: Rect2 = windows.merchant_description.get_global_rect()
	_expect(bounds.encloses(description) and description.size.y >= 48,
		"the description stays readable inside the merchant panel")
	var grid: Control = windows.merchant_list if windows.merchant_list.visible else windows.merchant_empty_pack
	_expect(grid.get_global_rect().end.y <= description.position.y and description.end.y <= action.position.y,
		"the description does not overlap the visible stock or transaction controls")
	_expect(bounds.size.x <= 440, "the shop keeps its narrower footprint")
	if windows.merchant_list.visible:
		_expect(windows.merchant_list.size.y <= 200, "item rows do not stretch into unused space")
	print("SHOP SIZE ", filename, " ", bounds.size)
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty():
		return
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(output)
	var image := root.get_texture().get_image()
	_expect(image != null and image.get_size() == Vector2i(1280, 720), "a full rendered frame is captured")
	if image != null:
		_expect(image.save_png(output.path_join(filename)) == OK, "the screenshot is saved")

func _expect(value: bool, description: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + description)

func _select(server_id: int, selling := false) -> void:
	var list: ItemList = windows.merchant_sell_list if selling else windows.merchant_buy_list
	for row: int in range(list.item_count):
		if int(list.get_item_metadata(row)) == server_id:
			list.select(row)
			list.item_selected.emit(row)
			return
	_expect(false, "fixture item is visible: %d" % server_id)

func _search(query: String) -> void:
	windows.merchant_search.text = query
	windows.merchant_search.text_changed.emit(query)
