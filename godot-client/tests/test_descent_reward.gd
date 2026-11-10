extends SceneTree
## The boss reward of a descent (descent_v1, server message 188, kind
## "reward"): three cards with each item's icon, name, quantity and rare mark;
## a click answers `#descent pick <offer> <index>`; `open` false closes it.
## Also the descent's small status line.

var failures := 0
var checks := 0
var sent: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func _record(text: String) -> Error:
	sent.append(text)
	return OK

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _offer() -> Dictionary:
	return {"version": 1, "kind": "reward", "open": true, "offer": "5f3e",
		"title": "Choose your reward",
		"items": [{"index": 0, "item": "Gloam Focus", "quantity": 1, "image_id": 412, "rare": true},
			{"index": 1, "item": "Gold Coins", "quantity": 2400, "image_id": 3, "rare": false},
			{"index": 2, "item": "Cloth Roll", "quantity": 4, "image_id": 77, "rare": false}]}

func _packet(app: Node, state: Dictionary) -> void:
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, JSON.stringify(state).to_utf8_buffer())

func _card_text(card: Node, label: String) -> Label:
	return card.find_child(label, true, false) as Label

func _run() -> void:
	create_timer(60).timeout.connect(func() -> void:
		push_error("FAIL: descent reward test timed out")
		quit(1))
	root.size = Vector2i(1280, 800)
	var app: Node = root.get_node("AppState")
	root.get_node("Network").block_for_hud_preview()
	var surface := Control.new()
	root.add_child(surface)
	surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var windows: Control = load("res://src/ui/extension_windows.gd").new()
	surface.add_child(windows)
	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	windows.configure(atlas)
	var window: Control = windows.descent_reward_window
	window.configure(_record)
	var stack := WindowStack.new()
	root.add_child(stack)
	stack.configure(surface)
	stack.register(window.panel)
	await process_frame
	_expect(not window.panel.visible, "no offer, no window")
	var decoded := EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		JSON.stringify(_offer()).to_utf8_buffer())
	_expect(decoded.type == "descent_reward" and decoded.data.items.size() == 3, "the contract's offer decodes")
	var broken := _offer()
	broken.items[1].quantity = 0
	_expect(EloriaProtocol.decode_server(188, JSON.stringify(broken).to_utf8_buffer()).type == "invalid",
		"an offer of nothing is refused")
	broken = _offer()
	broken.erase("offer")
	_expect(EloriaProtocol.decode_server(188, JSON.stringify(broken).to_utf8_buffer()).type == "invalid",
		"an offer without its id is refused")
	_packet(app, _offer())
	await process_frame
	_expect(window.panel.visible and window.panel in stack._windows, "the offer opens the window in the window stack")
	_expect(window.title.text == "Choose your reward", "the server's title is shown")
	# _layout runs deferred: the panel is sized to its cards, hint and button.
	await process_frame
	await process_frame
	var tall: float = window.panel.size.y
	_expect(tall < root.size.y * 0.6 and tall >= window.cards.get_combined_minimum_size().y,
		"the window is as tall as its content, well under the screen (%d of %d px)" % [tall, root.size.y])
	var cards: Array[Node] = window.cards.get_children()
	_expect(cards.size() == 3, "three cards are offered")
	if cards.size() == 3:
		_expect(_card_text(cards[0], "Name").text == "Gloam Focus" and _card_text(cards[0], "Rare").visible
			and not _card_text(cards[0], "Quantity").visible,
			"a single rare item shows its name and the rare mark")
		_expect(_card_text(cards[1], "Name").text == "Gold Coins"
			and _card_text(cards[1], "Quantity").text == "× 2,400" and _card_text(cards[1], "Quantity").visible
			and not _card_text(cards[1], "Rare").visible,
			"a stack shows its quantity")
		var icon := cards[2].find_child("Icon", true, false) as TextureRect
		_expect(icon != null and icon.texture != null and icon.texture == atlas.icon_for(77),
			"each card shows its item's icon")
		(cards[1] as Button).pressed.emit()
		_expect(sent.size() == 1 and sent.back() == "#descent pick 5f3e 1", "a click answers the offer with that card's index")
		_expect((cards[0] as Button).disabled and (cards[2] as Button).disabled
			and window.hint.text.contains("Gold Coins"), "the cards wait for the server's answer")
		(cards[2] as Button).pressed.emit()
		_expect(sent.size() == 1, "a second click while waiting sends nothing")
		window._end_wait()
		_expect(not (cards[2] as Button).disabled, "the cards come back when the offer stays open")
		(cards[2] as Button).pressed.emit()
		_expect(sent.back() == "#descent pick 5f3e 2", "the item stated by its index is picked")
	_expect(windows.close_top(), "cancel closes the reward window")
	_expect(not window.panel.visible and not app.descent_reward.is_empty(),
		"closing the window keeps the server's offer")
	_packet(app, _offer())
	await process_frame
	_expect(window.panel.visible, "the dais offers it again")
	windows.toggle_quest_journal()
	_expect(window.panel.visible, "opening another window leaves the offer on screen")
	windows.quest_panel.hide()
	_packet(app, {"version": 1, "kind": "reward", "open": false})
	await process_frame
	_expect(not window.panel.visible and app.descent_reward.is_empty() and window.cards.get_child_count() == 0,
		"open false closes the window")
	await _check_status(app, windows)
	print("descent reward checks: %d, failures: %d" % [checks, failures])
	quit(failures)

func _check_status(app: Node, windows: Control) -> void:
	var hud: Control = windows.descent_status_hud
	app.authenticated = true
	_expect(not hud.panel.visible, "no descent, no status")
	_packet(app, {"version": 1, "kind": "state", "open": true,
		"run": "a91c", "dungeon": "serpent_deep", "name": "The Serpent Deep", "difficulty": "Hard",
		"floor": 3, "floors": 6, "floor_name": "The Buried Streets",
		"section": "serpent_deep_f3v2", "origin": [288, 160], "cell_tiles": 2, "width": 4, "height": 2,
		"explored": "AA==", "time_left": 2345, "boss": "fighting"})
	await process_frame
	_expect(hud.panel.visible and hud.heading.text == "The Serpent Deep · Hard"
		and hud.floor_line.text == "Floor 3 of 6 · The Buried Streets",
		"the status names the descent and the floor")
	_expect(hud.clock.text.begins_with("Time left 39:0") and hud.clock.text.contains("The boss is fighting"),
		"the status counts the time left (%s)" % hud.clock.text)
	_expect(hud.clock_text(3725) == "1:02:05" and hud.clock_text(65) == "1:05" and hud.clock_text(-3) == "0:00",
		"the clock reads minutes and seconds")
	_packet(app, {"version": 1, "kind": "state", "open": false})
	await process_frame
	_expect(not hud.panel.visible, "leaving the descent hides the status")
	app.authenticated = false
