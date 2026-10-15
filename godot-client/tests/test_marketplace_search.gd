extends SceneTree
## Fixtures are real server marketplace_state packets, including the v3 trailer.

var failures := 0
var windows: Control
var state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	state = root.get_node("/root/AppState")
	windows = (load("res://src/ui/extension_windows.gd") as GDScript).new() as Control
	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")) as Dictionary)
	windows.configure(atlas)
	root.add_child(windows)
	await process_frame
	var fixtures: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://tests/fixtures/marketplace_v3.json")) as Dictionary
	var browse: PackedByteArray = str(fixtures.browse).hex_decode()
	var decoded: Dictionary = EloriaProtocol.decode_marketplace(browse)
	_expect(decoded.type == "marketplace" and int(decoded.version) == 3,
		"the server's v3 search packet decodes")
	state.call("_on_packet", 222, browse)
	await _settle()
	_expect(windows.market_filters_box.visible and windows.market_tabs.history.visible,
		"advanced servers show filters and sales history")
	_expect(windows.market_category.item_count > 1 and windows.market_type.item_count > 1,
		"categories and classes come from the server's item catalog")
	windows.market_sort.select(windows.MARKET_SORTS.find("price"))
	windows.market_min_price.text = "1,000"
	windows.market_max_price.text = "2,000"
	windows.market_seller.text = "Alice"
	var command: String = windows._market_view_command("browse", 20, "Iron Ore")
	var request: Dictionary = JSON.parse_string(command.trim_prefix("#auction ui3 ")) as Dictionary
	_expect(int(request.offset) == 20 and str(request.query) == "Iron Ore"
		and str(request.filters.sort) == "price" and str(request.filters.seller) == "Alice"
		and str(request.filters.min_price) == "1000" and str(request.filters.max_price) == "2000",
		"price ranges, seller, sort, and page are sent together")
	windows.market_min_price.text = "20"
	windows.market_max_price.text = "10"
	windows._on_market_search()
	_expect(windows.market_status.text.contains("Minimum price"),
		"reversed ranges get a clear message before sending")
	windows._on_market_clear_search()
	_expect(windows.market_search.text == "" and windows.market_seller.text == ""
		and windows.market_min_price.text == "" and windows.market_max_price.text == ""
		and windows.market_category.selected == 0 and windows.market_type.selected == 0,
		"Clear filters resets every restriction")
	state.call("_on_packet", 222, browse)
	await _settle()
	await _capture("auction-browse.png")
	var history: PackedByteArray = str(fixtures.history).hex_decode()
	state.call("_on_packet", 222, history)
	await _settle()
	_expect(windows._market_tab == "history" and windows.market_history.visible
		and windows.market_history.get_root().get_child_count() > 1
		and windows.market_page_label.text.contains("of 26 sales"),
		"sales history has its own records and paging")
	var sale: TreeItem = windows.market_history.get_root().get_first_child()
	_expect(sale.get_text(0) == "Sunleaf" and sale.get_text(2) == "Rowan"
		and sale.get_text(3) == "96" and sale.get_text(4) == "2026-10-15 00:00",
		"a sale states the buyer, item, proceeds, and purchase time")
	var large: Dictionary = EloriaProtocol.decode_marketplace(str(fixtures.large_history).hex_decode())
	_expect(int(large.history[0].total) == 3999999996000000001,
		"large sales retain every coin through integer text")
	_expect(not windows.market_buy.visible and not windows.market_sell.visible
		and not windows.market_renew.visible and not windows.market_cancel.visible
		and windows._market_buy_command().is_empty() and windows.market_seller.placeholder_text == "Buyer name",
		"history searches buyers and only offers completed-sale details")
	await _capture("auction-sales-history.png")
	for fixture: PackedByteArray in [browse, history]:
		var truncated: PackedByteArray = fixture.slice(0, fixture.size() - 1)
		_expect(str(EloriaProtocol.decode_marketplace(truncated).type) == "invalid",
			"an incomplete v3 extension is refused")
	# Legacy compatibility is also covered by test_protocol and test_extension_windows.
	var legacy := PackedByteArray([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
	state.call("_on_packet", 222, legacy)
	await _settle()
	_expect(not windows.market_filters_box.visible and not windows.market_tabs.history.visible,
		"older servers do not advertise unsupported controls")
	windows.queue_free()
	await process_frame
	print("marketplace search and sales history: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _settle() -> void:
	for _frame: int in range(5):
		await process_frame

func _capture(filename: String) -> void:
	_expect(windows.market_panel.size.x <= 840 and windows.market_panel.size.y <= 600,
		"the Exchange keeps its intended size")
	var directory: String = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if directory.is_empty():
		return
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(directory)
	var picture: Image = root.get_texture().get_image()
	_expect(picture != null and picture.save_png(directory.path_join(filename)) == OK,
		"the rendered preview is saved")

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
