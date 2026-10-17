extends SceneTree
## The server's conversation-to-shop packets must leave only one window open.

var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	var state: Node = root.get_node("AppState")
	state.authenticated = true
	var windows: Control = main.extension_windows
	var dialogue: Control = main.get_node("%DialoguePanel")

	# Exact payloads from the server's NPC greeting and option builders.
	state.call("_on_packet", 33, _hex("42657474616e79204f726c00000000000000000000"))
	state.call("_on_packet", 30, "Bread and broth. What can I do for you?".to_utf8_buffer())
	state.call("_on_packet", 31, _hex("050053686f7000ba0b5b000800476f6f646279650084035b00"))
	await process_frame
	_expect(dialogue.visible and not windows.merchant_panel.visible,
		"Bettany's greeting shows chat before the player chooses Shop")
	_expect(state.npc_dialogue.options[0].label == "Shop"
		and state.npc_dialogue.options[1].label == "Goodbye",
		"the greeting carries the Shop and Goodbye choices")

	# Selecting Shop closes the conversation before the merchant state arrives.
	state.call("_on_packet", 32, PackedByteArray())
	state.call("_on_packet", 223, _hex(
		"5b00fa0000001400000050000000010042657474616e79204f726c000000280000000c00000005"
		+ "000000140053756e6c65616600"))
	await process_frame
	_expect(windows.merchant_panel.visible
		and windows.merchant_header.text.contains("Bettany Orl"),
		"choosing Shop opens Bettany's merchant window")
	_expect(not dialogue.visible and not state.npc_dialogue.open
		and state.npc_dialogue.options.is_empty(),
		"opening the shop closes chat and clears its choices")

	(windows.merchant_panel.get_node("Body/Header/Close") as Button).pressed.emit()
	await process_frame
	_expect(not windows.merchant_panel.visible and not dialogue.visible,
		"finishing shopping leaves both the shop and chat closed")
	_expect(not state.merchant.open and not state.npc_dialogue.open,
		"neither window retains an open state after shopping")
	main.queue_free()
	await process_frame
	print("merchant conversation tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
