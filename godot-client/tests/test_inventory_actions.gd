extends SceneTree
## The inventory window's two hand-driven actions: the pointer over a slot,
## and the double click that wears a piece of gear.
##
## The pointer is the promise - Eternal Lands swaps it so a click is never
## spent finding out what it does - so the three tools the right button steps
## through have to answer with the eye, the finger and the grasping hand. The
## double click is checked at the seam that can be asked offline: which wear
## position it asks for, and that the hand is emptied first, since the first
## of the two clicks may already have picked the stack up.

var failures := 0
## The autoload, reached through the tree: a `--script` run has no global
## identifier for it.
var app_state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	app_state = root.get_node("AppState")
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	_check_pointer(main)
	_check_wear_destination(main)
	_check_double_click(main)
	main.queue_free()
	await process_frame
	_inventory().clear()
	print("inventory actions tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## Slot 0 holds a usable stack, slot 1 an unusable one, position 36 a worn
## piece. Between them every branch of the promise has something to stand on.
func _inventory() -> Dictionary:
	return app_state.get("inventory") as Dictionary

func _fixture(main: Node) -> void:
	_inventory().clear()
	_inventory()[0] = {"image_id": 1, "quantity": 3,
		"inventory_usable": true}
	_inventory()[1] = {"image_id": 2, "quantity": 1,
		"inventory_usable": false}
	_inventory()[36] = {"image_id": 3, "quantity": 1,
		"inventory_usable": false}
	main.set("_carried_slot", -1)
	main.set("_interaction_mode", "walk")
	main.call("_sync_inventory")

func _check_pointer(main: Node) -> void:
	_fixture(main)
	var slots: Array = main.get("inventory_slot_buttons") as Array
	var worn: Array = main.get("equipment_slot_buttons") as Array
	_expect(slots.size() >= 3 and worn.size() >= 1,
		"the window built its slots")
	if slots.size() < 3 or worn.size() < 1:
		return
	var usable: Button = slots[0] as Button
	var unusable: Button = slots[1] as Button
	var empty: Button = slots[2] as Button
	var equipped: Button = worn[0] as Button

	main.set("_inventory_tool", "grab")
	_promise(main, usable, "item_grab", MouseCursors.GRAB,
		"the grab tool shows the hand over a stack it would pick up")
	_promise(main, equipped, "item_grab", MouseCursors.GRAB,
		"the grab tool shows the hand over worn gear too")
	_expect(str(main.call("_slot_cursor_target", empty)).is_empty(),
		"an empty slot promises nothing")

	main.set("_inventory_tool", "use")
	_promise(main, usable, "item_use", MouseCursors.USE,
		"the use tool shows the finger over a stack it would spend")
	_promise(main, unusable, "item_inspect", MouseCursors.EYE,
		"a stack the use tool cannot spend is only looked at")
	_promise(main, equipped, "item_inspect", MouseCursors.EYE,
		"worn gear is never used, so the use tool only looks at it")

	main.set("_inventory_tool", "inspect")
	_promise(main, usable, "item_inspect", MouseCursors.EYE,
		"the inspect tool shows the eye")
	_promise(main, equipped, "item_inspect", MouseCursors.EYE,
		"the inspect tool shows the eye over worn gear")

	# A carry in hand overrides every tool: the click puts it down.
	main.set("_inventory_tool", "inspect")
	main.set("_carried_slot", 0)
	_promise(main, empty, "item_grab", MouseCursors.GRAB,
		"an empty slot takes the carry, so it shows the hand")
	main.set("_carried_slot", -1)

	# Stepping through the tools with the right button lands on all three.
	var seen: Array[String] = []
	for _step: int in range(3):
		main.call("_cycle_inventory_tool", 0)
		seen.append(str(main.call("_slot_cursor_target", usable)))
	seen.sort()
	_expect(seen == ["item_grab", "item_inspect", "item_use"],
		"the right-button cycle visits the hand, the eye and the finger"
			+ " (saw %s)" % str(seen))
	main.set("_inventory_tool", "grab")

func _check_wear_destination(main: Node) -> void:
	_fixture(main)
	# Position 36 is worn in the fixture, so the first free one is 37.
	_expect(int(main.call("_wear_destination")) == 37,
		"a double click asks for the first free wear position")
	for slot: int in range(36, 44):
		_inventory()[slot] = {"image_id": 4, "quantity": 1}
	_expect(int(main.call("_wear_destination")) == 36,
		"with every position worn it asks for the first, which the server"
			+ " overrules with the position of the piece being replaced")
	_fixture(main)

func _check_double_click(main: Node) -> void:
	_fixture(main)
	main.set("_inventory_tool", "grab")
	main.call("_begin_carry", 0)
	_expect(int(main.get("_carried_slot")) == 0,
		"the first of the two clicks picked the stack up")
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	event.double_click = true
	main.call("_on_inventory_slot_gui_input", event, 0)
	_expect(int(main.get("_carried_slot")) == -1,
		"the second click empties the hand instead of placing the carry")
	var line: String = str((main.get("inventory_description")
		as RichTextLabel).text)
	_expect(line.contains("slot 1"),
		"the window says which slot is being worn (said %s)" % line)
	# A worn position double-clicks the other way: it comes off into the
	# backpack. Slots 0 and 1 are taken in the fixture, so the destination is
	# the first slot past them.
	main.call("_cancel_carry")
	_fixture(main)
	_expect(int(main.call("_unequip_destination")) == 2,
		"a double click on worn gear asks for the first free backpack slot")
	main.call("_on_inventory_slot_gui_input", event, 36)
	var unequip_line: String = str((main.get("inventory_description")
		as RichTextLabel).text)
	_expect(unequip_line.contains("position 1"),
		"the window says which equipped position is coming off (said %s)"
			% unequip_line)
	# The first of the two clicks may have picked something else up; that
	# is emptied before the unequip is sent, same as wearing.
	_fixture(main)
	main.call("_begin_carry", 1)
	main.call("_on_inventory_slot_gui_input", event, 36)
	_expect(int(main.get("_carried_slot")) == -1,
		"the unequip empties whatever the hand was carrying")
	# With every backpack slot full there is nowhere to send the piece, so
	# the double click is a no-op rather than guessing a destination.
	for slot: int in range(2, 36):
		_inventory()[slot] = {"image_id": 5, "quantity": 1}
	_expect(int(main.call("_unequip_destination")) == -1,
		"a full backpack has no destination to offer")
	_fixture(main)

func _promise(main: Node, button: Button, target: String, cursor: int,
		label: String) -> void:
	var got: String = str(main.call("_slot_cursor_target", button))
	_expect(got == target, "%s (wanted %s, got %s)" % [label, target, got])
	_expect(MouseCursors.choose({"target": target}) == cursor,
		"%s - and the table answers with cursor %d" % [label, cursor])

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
