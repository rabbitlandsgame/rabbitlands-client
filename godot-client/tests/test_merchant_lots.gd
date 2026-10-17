extends SceneTree
## Fractional sale prices stay exact in the wire decoder and the real shop UI.

var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var protocol := load("res://src/network/protocol.gd")
	var payload := PackedByteArray()
	payload.resize(16)
	payload.encode_u16(0, 42)
	payload.encode_u32(2, 10)
	payload.encode_u32(6, 5)
	payload.encode_u32(10, 80)
	payload.encode_u16(14, 1)
	payload.append_array("Mara".to_utf8_buffer())
	payload.append(0)
	var row := PackedByteArray()
	row.resize(16)
	row.encode_u16(0, 500)
	row.encode_u32(2, 0)
	row.encode_u32(6, 1)
	row.encode_u32(10, 5)
	row.encode_u16(14, 16)
	payload.append_array(row)
	payload.append_array("Sunleaf".to_utf8_buffer())
	payload.append(0)
	# Weight, description and negotiated sale-bundle trailers.
	payload.append_array(PackedByteArray([1, 0, 1, 0, 0, 0, 1, 0]))
	payload.append_array("A leaf.".to_utf8_buffer())
	payload.append_array(PackedByteArray([0, 1, 0, 2, 0]))
	var decoded: Dictionary = protocol.decode_merchant(payload)
	_expect(decoded.type == "merchant" and decoded.items[0].sell_quantity == 2,
		"the server's sale bundle is decoded")
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	var state: Node = root.get_node("AppState")
	state.authenticated = true
	state.call("_on_packet", 223, payload)
	await process_frame
	var windows: Control = main.extension_windows
	_expect(windows.merchant_buy_list.item_count == 0, "buyback-only goods are not offered free")
	_expect(windows.merchant_sell_list.item_count == 1, "owned loot beyond the original stock is sellable")
	windows.merchant_sell_list.select(0)
	windows._on_merchant_selected(0, "sell")
	_expect(windows.merchant_quantity.text == "2", "selection starts with a complete bundle")
	_expect(windows.merchant_selection.text.contains("0.5 gc each"), "the half-gold unit price is shown")
	windows._merchant_set_maximum()
	_expect(windows.merchant_quantity.text == "4", "Max leaves an odd item in the pack")
	_expect(windows.merchant_totals.text.contains("Receive: 2 gc"), "the total is exactly two gold")
	_expect(windows._merchant_trade_command() == "#shop sell 42 500 4", "the trade retains the original server index")
	windows.merchant_quantity.text = "3"
	windows._sync_merchant_summary()
	_expect(windows.merchant_trade.disabled, "an incomplete bundle cannot be sold")
	_expect(windows.merchant_totals.text.contains("multiples of 2"), "the bundle requirement is explained")
	main.queue_free()
	await process_frame
	print("merchant lot tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
