extends SceneTree

var failures := 0
var checks := 0

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _init() -> void:
	run.call_deferred()

func run() -> void:
	root.size = Vector2i(1280, 720)
	var state: Node = root.get_node("AppState")
	var network: Node = root.get_node("Network")
	network.set_process(false)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.get_node("LoginLogo").hide()
	main.get_node("GameView").show()
	state.authenticated = true
	var server := TCPServer.new()
	expect(server.listen(0, "127.0.0.1") == OK, "loopback fixture listens")
	var peer := StreamPeerTCP.new()
	network.set("_peer", peer)
	network.set("_secure", false)
	expect(peer.connect_to_host("127.0.0.1", server.get_local_port()) == OK,
		"loopback fixture starts connecting")
	var deadline := Time.get_ticks_msec() + 2000
	while not server.is_connection_available() and Time.get_ticks_msec() < deadline:
		peer.poll()
		await process_frame
	if not server.is_connection_available():
		expect(false, "loopback fixture connects")
		quit(1)
		return
	var receiver: StreamPeerTCP = server.take_connection()
	peer.poll()

	state._on_packet(41, PackedByteArray([1]) + "Bob".to_ascii_buffer() + PackedByteArray([0]))
	state._on_packet(40, PackedByteArray([1, 1, 0, 5, 0, 0, 0, 3, 0]))
	state._on_packet(67, PackedByteArray([2, 4]) + "Materials".to_ascii_buffer()
		+ PackedByteArray([0, 5]) + "Equipment".to_ascii_buffer() + PackedByteArray([0]))
	state._on_packet(68, PackedByteArray([0, 4, 2, 0, 20, 0, 0, 0, 0x34, 0x12]))
	state.storage["described"] = {0x1234: {"name": "Wood Plank"}}
	await process_frame
	var source_type: OptionButton = main.get("trade_source_type")
	var category: OptionButton = main.get("trade_storage_category")
	var source: ItemList = main.get("trade_source")
	var trade_panel: Control = main.get("trade_panel")
	expect(trade_panel.visible, "storage snapshots keep the trade window visible")
	expect(not (main.get("storage_panel") as Control).visible
		and not (main.get("inventory_panel") as Control).visible,
		"the bank and backpack do not cover the trade")
	expect(not source_type.is_item_disabled(1), "storage source enabled when both players are in reach")
	expect(source.item_count == 1 and int(source.get_item_metadata(0)) == 3,
		"backpack source uses the trade inventory snapshot")
	source_type.select(1)
	source_type.item_selected.emit(1)
	expect(category.visible and category.item_count == 2, "storage source exposes categories")
	expect(source.item_count == 1 and int(source.get_item_metadata(0)) == 0x1234,
		"storage rows retain their full server positions")
	expect(source.get_item_text(0) == "Wood Plank ×20", "stored items show names and quantities")
	await process_frame
	expect(Rect2(Vector2.ZERO, Vector2(root.size)).encloses(trade_panel.get_global_rect()),
		"storage trading fits within the game window")
	var artifact_dir := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not artifact_dir.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		DirAccess.make_dir_recursive_absolute(artifact_dir)
		expect(root.get_texture().get_image().save_png(artifact_dir.path_join("trade-storage.png")) == OK,
			"storage trading screenshot saved")
	source.select(0)
	source.item_selected.emit(0)
	var quantity: SpinBox = main.get("trade_quantity")
	expect(int(quantity.max_value) == 20, "offer quantity follows the stored stack")
	quantity.value = 7
	main.call("_on_trade_offer_pressed")
	expect(take(receiver) == PackedByteArray([36, 8, 0, 2, 0x34, 0x12, 7, 0, 0, 0]),
		"offering storage sends source 2, two-byte position and requested quantity")
	state._on_packet(68, PackedByteArray([0, 4, 2, 0, 13, 0, 0, 0, 0x34, 0x12]))
	await process_frame
	expect(source.get_item_text(0).contains("×13") and source.get_selected_items().is_empty(),
		"storage refresh updates stock and clears a potentially shifted selection")

	category.select(1)
	category.item_selected.emit(1)
	expect(take(receiver) == EloriaProtocol.get_storage_category(5),
		"category selector requests the selected server category")
	expect(source.item_count == 0 and (main.get("trade_offer_button") as Button).disabled,
		"old category cannot be offered while a new category is loading")
	state._on_packet(68, PackedByteArray([0, 5, 3, 0, 1, 0, 0, 0, 0x35, 0x12]))
	await process_frame
	expect(source.item_count == 1 and int(source.get_item_metadata(0)) == 0x1235,
		"new category replaces old source positions")

	source_type.select(0)
	source_type.item_selected.emit(0)
	state._on_packet(19, PackedByteArray([1, 1, 0, 2, 0, 0, 0, 3, 0]))
	expect(source.item_count == 1 and source.get_item_text(0).contains("×2"),
		"ordinary inventory refresh updates the trade source after an offer")
	source.select(0)
	source.item_selected.emit(0)
	quantity.value = 1
	main.call("_on_trade_offer_pressed")
	expect(take(receiver) == EloriaProtocol.put_inventory_on_trade(3, 1),
		"switching back sends backpack source 1")

	state._on_packet(41, PackedByteArray([0]) + "Bob".to_ascii_buffer() + PackedByteArray([0]))
	expect(source_type.selected == 0 and source_type.is_item_disabled(1),
		"out-of-range trade disables storage and returns to backpack")
	state._on_packet(38, PackedByteArray())
	expect(not trade_panel.visible and source_type.selected == 0,
		"ending a trade resets the source for the next trade")
	peer.disconnect_from_host()
	receiver.disconnect_from_host()
	server.stop()
	main.queue_free()
	await process_frame
	print("Storage trading: %d checks, %d failures" % [checks, failures])
	quit(failures)

func take(receiver: StreamPeerTCP) -> PackedByteArray:
	for attempt: int in range(25):
		receiver.poll()
		if receiver.get_available_bytes() > 0:
			break
		OS.delay_usec(2000)
	var available: int = receiver.get_available_bytes()
	return receiver.get_data(available)[1] as PackedByteArray if available > 0 else PackedByteArray()
