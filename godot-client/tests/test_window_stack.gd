extends SceneTree

const Stack = preload("res://src/ui/window_stack.gd")
var failures := 0
var clicks := {"front": 0, "back": 0}
var pointer_events := {"front": [], "back": []}

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	root.get_node("AppState").authenticated = true
	for window: Control in main.window_stack._windows:
		window.hide()
	await _check_quest_and_shop(main)
	await _check_docked_windows(main)
	await _check_overlap(main)
	await _check_confirmations(main)
	main.queue_free()
	await process_frame
	print("window stack tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_quest_and_shop(main: Control) -> void:
	var guide: Control = main.lantern_guide
	guide.set_process(false)
	var merchant: Control = main.extension_windows.merchant_panel
	root.get_node("AppState").merchant = {"open": true, "actor_id": 91,
		"npc_name": "Bettany Orl", "gold": 222, "items": []}
	main.extension_windows._sync_merchant()
	await process_frame
	guide.apply_state({"active": true, "tutorial": "watchpost", "stage": 3,
		"total": 4, "title": "Make the field dressing", "control": "merchant"})
	await process_frame
	var close: Button = merchant.get_node("Body/Header/Close")
	var point := close.get_global_rect().get_center()
	guide.card.global_position = point - Vector2(200, 90)
	_expect(guide.card.get_global_rect().has_point(point), "quest card overlaps the shop Close button")
	_expect(guide.card.z_index < merchant.z_index, "quest guide draws behind the shop even when refreshed later")
	_click(point)
	_expect(not merchant.visible, "the shop Close button works through an overlapping quest card")
	merchant.show()
	var tracker: Control = main.extension_windows.tracked_quest
	tracker.show()
	tracker.global_position = point - Vector2(120, 40)
	_expect(tracker.get_global_rect().has_point(point), "pinned quest overlaps the same Close button")
	guide.hide()
	_click(point)
	_expect(not merchant.visible, "the pinned quest also stays behind shop clicks")
	tracker.hide()

func _check_docked_windows(main: Control) -> void:
	var inventory: Control = main.inventory_panel
	var bank: Control = main.storage_panel
	inventory.show()
	bank.show()
	main.classic_storage._attach_inventory()
	await process_frame
	Stack.activate(inventory)
	_expect(bank.is_ancestor_of(inventory) and inventory.z_index == 0,
		"the real docked inventory shares storage's drawing group")
	_expect(main.inventory_quantity_edit.z_index == bank.z_index + 1,
		"the floating quantity editor follows the docked storage window")
	main.classic_storage._detach_inventory()
	await process_frame
	Stack.activate(inventory)
	_expect(inventory.get_parent() == main.game_view and inventory.z_index > bank.z_index,
		"undocking restores independent window activation")
	_expect(main.inventory_quantity_edit.z_index == inventory.z_index + 1,
		"the quantity editor follows the inventory after undocking")
	bank.hide()
	inventory.hide()
	var guide: Control = main.lantern_guide
	guide.apply_state({"active": true, "tutorial": "watchpost", "stage": 3,
		"total": 4, "title": "Make the field dressing", "control": "manufacture"})
	main.manufacturing_panel.show()
	guide._process(0.0)
	await process_frame
	_expect(guide.card.get_parent() == main.manufacturing_side
		and guide.card.z_as_relative and guide.card.z_index == 0,
		"a docked instruction card belongs to manufacturing's window")
	main.manufacturing_panel.hide()
	guide._process(0.0)
	_expect(guide.card.get_parent() == guide and not guide.card.z_as_relative
		and guide.card.z_index < main.manufacturing_panel.z_index,
		"undocking restores the reminder card's background priority")
	guide.hide()

func _check_overlap(main: Control) -> void:
	# Windows from different controller branches join the same native GUI list.
	var wrapper := Control.new()
	wrapper.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main.game_view.add_child(wrapper)
	var back := _window("Back", Vector2(100, 100), wrapper)
	var front := _window("Front", Vector2(240, 140), main.game_view)
	main.window_stack.register(back)
	main.window_stack.register(front)
	_expect(back.get_parent() == front.get_parent(), "controller windows share a stacking parent")
	var back_overlap := _button(back, Vector2(160, 80), "back")
	_button(front, Vector2(20, 40), "front")
	var exposed := _button(back, Vector2(10, 10), "back")
	back.show()
	front.show()
	await process_frame
	var overlap := back_overlap.get_global_rect().get_center()
	_click(overlap)
	_expect(clicks.front == 1 and clicks.back == 0, "only the visible front button receives an overlapping click")
	_click(exposed.get_global_rect().get_center())
	_expect(back.get_index() > front.get_index() and back.z_index > front.z_index,
		"clicking exposed contents activates and raises the whole window")
	_expect(clicks.back == 1, "the activation click reaches its original button exactly once")
	_click(overlap)
	_expect(clicks.back == 2 and clicks.front == 1, "subsequent overlapping clicks follow the newly active window")
	_click(overlap, MOUSE_BUTTON_RIGHT)
	_click(overlap, MOUSE_BUTTON_WHEEL_DOWN)
	_expect(MOUSE_BUTTON_RIGHT in pointer_events.back and MOUSE_BUTTON_WHEEL_DOWN in pointer_events.back,
		"the active window owns right clicks and scrolling")
	_expect(not MOUSE_BUTTON_RIGHT in pointer_events.front and not MOUSE_BUTTON_WHEEL_DOWN in pointer_events.front,
		"right clicks and scrolling never reach the covered window")
	back_overlap.hide()
	_click(overlap)
	_expect(clicks.front == 1, "empty window surfaces also block buttons behind them")
	var entry := LineEdit.new()
	front.add_child(entry)
	entry.grab_focus()
	_click(exposed.get_global_rect().get_center())
	_expect(not entry.has_focus(), "activating another window releases a covered text field")
	front.hide()
	front.show()
	_expect(front.z_index > back.z_index, "reopening a window raises it")
	front.hide()
	_click(exposed.get_global_rect().get_center())
	_expect(clicks.back == 4, "closing the front window exposes the window beneath it")
	# Docking must keep the inventory within its parent window's draw/input group.
	var dock := _window("Dock", Vector2.ZERO, main.game_view)
	main.window_stack.register(dock)
	dock.reparent(back)
	var dock_index := dock.get_index()
	Stack.activate(dock)
	_expect(dock.get_index() == dock_index and dock.z_as_relative and dock.z_index == 0,
		"activating a docked child raises its host without rearranging its contents")
	back.hide()

func _check_confirmations(main: Control) -> void:
	main.purchase_confirm.show()
	main.popup_panel.show()
	main.stats_panel.show()
	main.stats_panel.move_to_front()
	await process_frame
	_expect(not main._can_open_spell_wheel(), "the spell ring cannot take input away from a confirmation")
	_expect(main.popup_panel.get_index() > main.purchase_confirm.get_index()
		and main.purchase_confirm.get_index() > main.stats_panel.get_index(),
		"server prompts and purchase confirmations keep precedence in GUI order")
	_expect(main.popup_panel.z_index > main.purchase_confirm.z_index
		and main.purchase_confirm.z_index > main.stats_panel.z_index,
		"confirmation drawing order matches GUI order")
	main.popup_panel.hide()
	main.purchase_confirm.hide()
	main.stats_panel.hide()

func _window(title: String, at: Vector2, parent: Node) -> Control:
	var window := Control.new()
	window.name = title
	window.position = at
	window.size = Vector2(260, 180)
	window.hide()
	parent.add_child(window)
	return window

func _button(parent: Control, at: Vector2, key: String) -> Button:
	var button := Button.new()
	parent.add_child(button)
	button.position = at
	button.size = Vector2(60, 40)
	button.pressed.connect(func(): clicks[key] += 1)
	button.gui_input.connect(func(event: InputEvent):
		if event is InputEventMouseButton and event.pressed:
			pointer_events[key].append(event.button_index))
	return button

func _click(at: Vector2, which := MOUSE_BUTTON_LEFT) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = at
	motion.global_position = at
	root.push_input(motion)
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = at
		event.global_position = at
		event.button_index = which
		event.pressed = pressed
		root.push_input(event)

func _expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
