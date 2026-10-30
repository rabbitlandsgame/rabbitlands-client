extends SceneTree

const Lists = preload("res://src/ui/saved_item_lists.gd")
const Protocol = preload("res://src/network/protocol.gd")
const SETTINGS := "user://eloria_hud.cfg"
var failures := 0
var original_settings: PackedByteArray
var had_settings := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	had_settings = FileAccess.file_exists(SETTINGS)
	if had_settings:
		original_settings = FileAccess.get_file_as_bytes(SETTINGS)
	var clean := ConfigFile.new()
	clean.set_value("hud", "combat_hud_position", Vector2.ZERO)
	clean.set_value("inventory", "item_lists", {"Legacy": "3:20\n8:1"})
	clean.save(SETTINGS)
	_check_identity()
	var state: Node = root.get_node("AppState")
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	var workspace: Node = main.get("classic_storage") as Node
	_expect(workspace != null, "classic workspace is built")
	_check_icon_frames(workspace)
	_expect(not bool(workspace.get("docked")), "classic layout is the default")
	_expect((main.get("_item_lists") as Dictionary)["Legacy"] is Array,
		"existing text lists migrate to editable favorite entries")
	await _check_inventory_size(main, state)
	var storage: Dictionary = {"open": true, "category_id": 1,
		"categories": [{"id": 1, "name": "Food"}, {"id": 2, "name": "Tools"}],
		"items": {7: {"image_id": 3, "quantity": 40}},
		"described": {7: {"name": "Hearth Bread", "subtype": "Food"}}}
	state.set("storage", storage)
	state.set("inventory", {0: {"image_id": 3, "quantity": 8, "slot": 0}})
	state.set("inventory_names", {0: "Hearth Bread"})
	main.call("_sync_storage")
	await process_frame
	var inventory: Control = main.get("inventory_panel") as Control
	_expect(inventory.visible, "opening storage shows the separate inventory")
	_expect(inventory.get_parent() == main.get_node("GameView"), "classic windows remain independent")
	# A bank opens with separate category, contents and description packets.
	# Its second refresh used to run the old mutually-exclusive-window handler.
	for update_path: StringName in [&"storage", &"inventory", &"storage"]:
		state.set("authenticated", true)
		state.emit_signal("state_changed", update_path)
		await process_frame
		_expect(inventory.visible, "storage and inventory updates keep the backpack visible")
	state.set("authenticated", false)
	workspace.call("create_list")
	var name_field: LineEdit = workspace.get("list_name") as LineEdit
	name_field.text = "Foraging"
	workspace.call("rename_list")
	main.set("selected_inventory_slot", 0)
	workspace.call("add_inventory_slot", 0, true)
	var entries: Array = workspace.call("entries") as Array
	_expect(entries.size() == 1 and str(entries[0].name) == "Hearth Bread"
		and int(entries[0].quantity) == 8, "backpack capture saves the named item and quantity")
	workspace.call("_change_entry_quantity", 12)
	_expect(int((workspace.call("entries") as Array)[0].quantity) == 12, "favorite quantities are editable")
	workspace.call("create_list")
	name_field.text = "Crafting"
	workspace.call("rename_list")
	workspace.call("activate_list", "Foraging")
	_expect(str(workspace.get("active_list")) == "Foraging"
		and (workspace.call("entries") as Array).size() == 1,
		"selecting a named list hot swaps its favorite grid")
	_expect(int((state.get("inventory") as Dictionary)[0].quantity) == 8
		and int((state.get("storage") as Dictionary).items[7].quantity) == 40,
		"switching favorites does not transfer items")
	name_field.text = "Crafting"
	workspace.call("rename_list")
	_expect(str(workspace.get("active_list")) == "Foraging"
		and (main.get("_item_lists") as Dictionary).size() == 3,
		"duplicate names do not replace another saved list")
	await _check_transfers(workspace, state)
	await _check_el_clicks(main, workspace, state)
	workspace.call("set_docked", true)
	await process_frame
	_expect(bool(workspace.call("is_inventory_docked"))
		and inventory.get_parent() == workspace.get("body"), "docked bank groups the real inventory")
	main.call("_sync_storage")
	await process_frame
	_expect(inventory.visible, "a docked bank keeps its backpack visible on refresh")
	var bank: Control = workspace.get("bank") as Control
	var old_position: Vector2 = inventory.global_position
	bank.position += Vector2(12, 7)
	_expect(inventory.global_position == old_position + Vector2(12, 7), "moving the dock moves both windows")
	workspace.call("set_docked", false)
	await process_frame
	_expect(inventory.get_parent() == main.get_node("GameView"), "undocking restores the inventory's parent")
	workspace.call("set_docked", true)
	state.call("close_storage")
	main.call("_sync_storage")
	await process_frame
	_expect(not bool(workspace.call("is_inventory_docked")), "closing storage releases the inventory")
	inventory.show()
	state.set("storage", storage.duplicate(true))
	main.call("_sync_storage")
	main.call("_sync_storage")
	_expect(inventory.visible, "opening storage preserves an already-open backpack")
	state.call("close_storage")
	main.call("_sync_storage")
	_expect(inventory.visible, "closing storage preserves a backpack the player had opened")
	workspace.call("persist")
	main.queue_free()
	await process_frame
	var second: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(second)
	await process_frame
	var restored: Node = second.get("classic_storage") as Node
	_expect(bool(restored.get("docked")) and str(restored.get("active_list")) == "Foraging",
		"layout and active favorites survive a fresh scene")
	_expect(int((restored.call("entries") as Array)[0].quantity) == 12, "list quantities survive a fresh scene")
	second.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS, FileAccess.WRITE)
		file.store_buffer(original_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS))
	print("classic storage tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_identity() -> void:
	var items: Dictionary = {3: {"image_id": 8, "quantity": 10},
		7: {"image_id": 8, "quantity": 20}, 11: {"image_id": 8, "quantity": 4}}
	var described: Dictionary = {3: {"name": "Iron Sword"},
		7: {"name": "Bronze Sword"}, 11: {"name": "Iron Sword"}}
	var wanted: Dictionary = {"image_id": 8, "name": "Iron Sword", "quantity": 6}
	_expect(Lists.matching_positions(wanted, items, described) == [3, 11],
		"same-icon items are matched by name and retain server positions")
	_expect(Lists.matching_positions({"image_id": 8}, items, described).is_empty(),
		"ambiguous legacy icons cannot withdraw a different item")
	_expect(Lists.matching_positions({"image_id": 8}, items, {}).is_empty(),
		"unknown duplicate icons cannot establish identity")
	_expect(Lists.carried_quantity(wanted, {0: {"image_id": 8, "quantity": 2},
		1: {"image_id": 8, "quantity": 8}, 36: {"image_id": 8, "quantity": 1}},
		{0: "Iron Sword", 1: "Bronze Sword", 36: "Iron Sword"}) == 2,
		"top-up quantities count only matching backpack items")
	var normalized: Dictionary = Lists.normalize({"Invalid": "-1:4\n3:0\nbad",
		"Valid": [{"image_id": 3, "quantity": 99999999, "name": "Bread"}]})
	_expect((normalized.Invalid as Array).is_empty()
		and int(normalized.Valid[0].quantity) == 9999999, "invalid entries are rejected and quantities bounded")

func _check_inventory_size(main: Node, state: Node) -> void:
	var inventory: Control = main.get("inventory_panel") as Control
	var description: RichTextLabel = main.get("inventory_description") as RichTextLabel
	var was_visible: bool = inventory.visible
	inventory.show()
	state.set("inventory", {0: {"image_id": 3, "quantity": 1, "inventory_usable": true},
		36: {"image_id": 35, "quantity": 1}})
	main.call("_sync_inventory")
	for frame: int in range(4):
		await process_frame
	var fixed_size: Vector2 = inventory.size
	var fixed_scale: Vector2 = inventory.scale
	var tools: Array[String] = ["grab", "use", "equip", "unequip", "inspect"]
	for tool: String in tools:
		main.call("_set_inventory_tool", tool)
		main.call("_sync_inventory")
		for action: Button in [main.get("inventory_use_button"), main.get("inventory_equip_button"),
				main.get("inventory_unequip_button"), main.get("inventory_inspect_button")]:
			action.disabled = not action.disabled
		await process_frame
		_expect(inventory.size.is_equal_approx(fixed_size)
			and inventory.scale.is_equal_approx(fixed_scale), "tool and availability changes keep inventory size stable")
	main.call("_set_inventory_tool", "grab")
	for slot: int in [0, 36]:
		main.call("_on_inventory_slot_pressed" if slot == 0 else "_on_equipment_slot_pressed", slot)
		main.call("_cancel_carry")
		await process_frame
		_expect(inventory.size.is_equal_approx(fixed_size), "clicking carried and worn items keeps inventory size stable")
	for equipped: bool in [true, false, true]:
		state.set("inventory", {36 if equipped else 0: {"image_id": 3, "quantity": 1}})
		main.call("_sync_inventory")
		await process_frame
		_expect(inventory.size.is_equal_approx(fixed_size), "equipment snapshots keep inventory size stable")
	description.text = "An item with a long description and equipment information.\n".repeat(30)
	for frame: int in range(4):
		await process_frame
	_expect(inventory.size.is_equal_approx(fixed_size)
		and inventory.scale.is_equal_approx(fixed_scale), "long item descriptions scroll without resizing inventory")
	main.call("_apply_inventory_scale", 1.25)
	_expect(inventory.scale.x > fixed_scale.x and inventory.scale.x <= 1.25,
		"manual resizing enlarges inventory while allowing it to fit the viewport")
	main.call("_begin_quantity_edit", 0)
	for frame: int in range(3):
		await process_frame
	_expect(inventory.size.is_equal_approx(fixed_size), "editing a quantity floats over its shortcut without resizing inventory")
	var quantity_edit: Control = main.get("inventory_quantity_edit") as Control
	_expect(quantity_edit.scale.is_equal_approx(inventory.get_global_transform().get_scale()),
		"quantity editing follows the user's chosen window scale")
	main.call("_commit_quantity_edit")
	main.call("_apply_inventory_scale", fixed_scale.x)
	description.text = "Select an item to inspect it."
	state.set("inventory", {})
	main.set("selected_inventory_slot", -1)
	main.call("_sync_inventory")
	inventory.visible = was_visible

func _check_icon_frames(workspace: Node) -> void:
	var image := Image.create(100, 50, false, Image.FORMAT_RGBA8)
	image.fill(Color.BLACK)
	# The second cell verifies the atlas offset. A detail near its edge must
	# survive: unframed art no longer has eight disposable pixels per side.
	image.set_pixel(75, 25, Color.BLUE)
	image.set_pixel(51, 1, Color.RED)
	var atlas := AtlasTexture.new()
	atlas.atlas = ImageTexture.create_from_image(image)
	atlas.region = Rect2(50, 0, 50, 50)
	var displayed: Texture2D = workspace.call("crop_icon", atlas) as Texture2D
	var pixels: Image = displayed.get_image()
	_expect(pixels.get_size() == Vector2i(50, 50)
		and pixels.get_pixel(25, 25) == Color.BLUE
		and pixels.get_pixel(1, 1) == Color.RED,
		"unframed icons preserve the complete correct atlas cell")
	var worn_image: Image = image.get_region(Rect2i(50, 0, 50, 50))
	var item_atlas := ItemAtlas.new()
	item_atlas.call("_stamp_worn_mark", worn_image)
	var worn: Texture2D = workspace.call("crop_icon", ImageTexture.create_from_image(worn_image)) as Texture2D
	var worn_pixels: Image = worn.get_image()
	var mark: Dictionary = ItemAtlas.worn_mark_metrics(50, 50)
	var mark_pixel: Color = worn_pixels.get_pixel(int(mark.left), int(mark.top))
	_expect(worn_pixels.get_size() == Vector2i(50, 50)
		and absf(mark_pixel.r - ItemAtlas.WORN_MARK_COLOUR.r) < 0.004
		and absf(mark_pixel.g - ItemAtlas.WORN_MARK_COLOUR.g) < 0.004
		and absf(mark_pixel.b - ItemAtlas.WORN_MARK_COLOUR.b) < 0.004,
		"the complete worn-item warning remains visible")

func _check_transfers(workspace: Node, state: Node) -> void:
	var fixture: Dictionary = await _open_fixture()
	if not fixture.is_empty():
		var receiver: StreamPeerTCP = fixture["receiver"] as StreamPeerTCP
		workspace.call("activate_list", "Crafting")
		workspace.call("activate_list", "Foraging")
		await process_frame
		receiver.poll()
		_expect(receiver.get_available_bytes() == 0, "hot swapping lists sends no transfer packets")
		workspace.call("collect_list")
		await process_frame
		var bytes := _take(receiver)
		_expect(bytes == Protocol.withdraw_storage(7, 4), "Get list sends only the missing quantity to the server position")
		workspace.call("collect_list")
		await process_frame
		receiver.poll()
		_expect(receiver.get_available_bytes() == 0, "repeated Get list does not duplicate an unacknowledged withdrawal")
		var storage: Dictionary = state.get("storage") as Dictionary
		storage["items_category_id"] = 2
		workspace.call("collect_list")
		await process_frame
		receiver.poll()
		_expect(receiver.get_available_bytes() == 0, "a partially loaded category cannot send stale transfers")
		storage.erase("items_category_id")
		_close_fixture(fixture)

## The storage window answers clicks the way Eternal Lands does: at the press,
## with a sticky carry between the stored grid and the backpack, and without
## rebuilding itself for every reply. Real mouse events go through the viewport
## and the packets are read off a local socket, so these are the clicks the
## player makes and the requests the server would see.
func _check_el_clicks(main: Node, workspace: Node, state: Node) -> void:
	var saved_storage: Dictionary = (state.get("storage") as Dictionary).duplicate(true)
	var saved_inventory: Dictionary = (state.get("inventory") as Dictionary).duplicate(true)
	var saved_quantities: Array[int] = (main.get("_inventory_quantities") as Array[int]).duplicate()
	var saved_box: int = int(main.get("_selected_quantity_box"))
	var lists_panel: Control = main.get("item_lists_panel") as Control
	var lists_were_visible: bool = lists_panel.visible
	lists_panel.hide()
	var items: Dictionary = {}
	var described: Dictionary = {}
	for position: int in range(200):
		items[position] = {"image_id": 3 + position % 40, "quantity": 10 + position}
		described[position] = {"name": "Item %03d" % position, "subtype": "Food"}
	state.set("storage", {"open": true, "category_id": 1,
		"categories": [{"id": 1, "name": "Food"}, {"id": 2, "name": "Tools"}],
		"items": items, "described": described})
	state.set("inventory", {0: {"image_id": 3, "quantity": 5, "slot": 0},
		1: {"image_id": 8, "quantity": 2, "slot": 1}})
	main.set("_interaction_mode", "walk")
	main.set("_selected_quantity_box", 0)
	_set_quantity(main, 1)
	main.call("_set_inventory_tool", "grab")
	main.call("_cancel_carry")
	main.call("_sync_storage")
	main.call("_sync_inventory")
	for frame: int in range(4):
		await process_frame
	var grid: GridContainer = workspace.get("storage_grid") as GridContainer
	(grid.get_parent() as ScrollContainer).scroll_vertical = 0
	var slots: Array = main.get("inventory_slot_buttons") as Array
	var worn: Array = main.get("equipment_slot_buttons") as Array
	var carried: Control = main.get("carried_item") as Control
	var fixture: Dictionary = await _open_fixture()
	if fixture.is_empty():
		return
	var receiver: StreamPeerTCP = fixture["receiver"] as StreamPeerTCP

	var press_mode := true
	for cell: Node in grid.get_children() + (workspace.get("favorite_grid") as Node).get_children():
		press_mode = press_mode and (cell as Button).action_mode == BaseButton.ACTION_MODE_BUTTON_PRESS
	_expect(press_mode, "storage and favourite cells act on the press")

	# One deposit's replies: the inventory, the category's stock and its
	# descriptions, then the 226 the client asks for and a text line.
	var cells_before: Array = grid.get_children()
	var created: Array[int] = [0]
	var count_created := func(_node: Node) -> void: created[0] += 1
	grid.child_entered_tree.connect(count_created)
	state.set("authenticated", true)
	for path: StringName in [&"inventory", &"storage", &"storage", &"inventory_state", &"inventory_text"]:
		state.emit_signal("state_changed", path)
	await process_frame
	state.set("authenticated", false)
	grid.child_entered_tree.disconnect(count_created)
	_expect(created[0] == 0 and grid.get_children() == cells_before,
		"a deposit's replies refill the storage cells in place instead of rebuilding them")
	var timings: Array[float] = []
	for repeat: int in range(7):
		var started: int = Time.get_ticks_usec()
		main.call("_sync_storage")
		timings.append((Time.get_ticks_usec() - started) / 1000.0)
	timings.sort()
	print("classic storage: a 200-item storage refresh takes %.2f ms (median of 7)" % timings[3])
	_expect(timings[3] < 25.0,
		"a 200-item storage refresh stays far below the 100 ms rebuild it replaced")

	# Command 226 and text lines say nothing about what is stored.
	var first_count: Label = (grid.get_child(0) as Button).get_child(0) as Label
	(items[0] as Dictionary)["quantity"] = 77
	state.set("authenticated", true)
	state.emit_signal("state_changed", &"inventory_state")
	state.emit_signal("state_changed", &"inventory_text")
	_expect(first_count.text == "10", "command 226 and inventory text lines leave the stored items alone")
	state.emit_signal("state_changed", &"storage")
	await process_frame
	state.set("authenticated", false)
	_expect(first_count.text == "77", "a storage reply refreshes the stored items, once per frame")
	(items[0] as Dictionary)["quantity"] = 10
	main.call("_sync_storage")

	# A selection is made at the press and restyles two cells.
	var lit: StyleBox = workspace.get("_lit_cell") as StyleBox
	var third: Button = grid.get_child(2) as Button
	_click(third.get_global_rect().get_center(), true)
	_expect(root.gui_get_hovered_control() == third, "the press lands on the third storage cell")
	_expect(int(workspace.get("_selected_position")) == 2
		and third.get_theme_stylebox("normal") == lit
		and (grid.get_child(0) as Button).get_theme_stylebox("normal") != lit,
		"a stored item is selected and lit at the press, before any release")
	_expect(int(main.get("_storage_carried_position")) == 2 and carried.visible,
		"pressing a stored item lifts it onto the cursor")
	_click(third.get_global_rect().get_center(), false)
	_expect(grid.get_children() == cells_before, "a selection click rebuilds nothing")

	# A reply landing between press and release used to free the pressed cell.
	main.call("_cancel_carry")
	var second: Button = grid.get_child(1) as Button
	_click(second.get_global_rect().get_center(), true)
	state.set("authenticated", true)
	state.emit_signal("state_changed", &"storage")
	state.emit_signal("state_changed", &"inventory")
	await process_frame
	state.set("authenticated", false)
	_click(second.get_global_rect().get_center(), false)
	_expect(int(workspace.get("_selected_position")) == 1
		and int(main.get("_storage_carried_position")) == 1 and grid.get_child(1) == second,
		"a reply that lands between press and release keeps the click")

	# Each click on the backpack withdraws the selected quantity; the server
	# chooses the slot, so a full slot works as well as an empty one.
	_take(receiver)
	_press(slots[5] as Button)
	_expect(_take(receiver) == Protocol.withdraw_storage(1, 1),
		"with a stored item in hand, a click on the backpack withdraws the selected quantity")
	_expect(int(main.get("_storage_carried_position")) == 1 and carried.visible,
		"the stored item stays in hand while more of it remains")
	_press(slots[0] as Button)
	_expect(_take(receiver) == Protocol.withdraw_storage(1, 1),
		"a click on a full backpack slot withdraws as well")
	_press(slots[0] as Button, true)
	_expect(_take(receiver) == Protocol.withdraw_storage(1, 1)
		and int(main.get("_storage_carried_position")) == 1,
		"a quick second click on the backpack is another withdrawal, not a double-click wear")
	_press(worn[0] as Button)
	_expect(_take(receiver).is_empty() and int(main.get("_storage_carried_position")) == 1,
		"the equipment grid does not take a stored item")
	_button(slots[3] as Button, MOUSE_BUTTON_RIGHT)
	_expect(int(main.get("_storage_carried_position")) == -1 and not carried.visible
		and str(main.get("_inventory_tool")) == "grab",
		"a right click on the backpack puts the stored item back and keeps the tool")
	_press(second)
	_set_quantity(main, 20)
	_press(slots[5] as Button)
	_expect(_take(receiver) == Protocol.withdraw_storage(1, 11)
		and int(main.get("_storage_carried_position")) == -1 and not carried.visible,
		"a withdrawal that takes the rest of the stack empties the hand")
	_set_quantity(main, 1)

	# Carrying a backpack item onto the storage grid deposits it.
	_press(slots[0] as Button)
	_expect(int(main.get("_carried_slot")) == 0 and _take(receiver).is_empty(),
		"lifting a backpack item onto the cursor sends nothing")
	_press(grid.get_child(4) as Button)
	_expect(_take(receiver) == Protocol.deposit_storage(0, 1)
		and int(main.get("_carried_slot")) == 0 and int(main.get("_storage_carried_position")) == -1,
		"a click on the storage grid deposits the selected quantity and keeps the item in hand")
	var filter: LineEdit = workspace.get("filter") as LineEdit
	filter.text = "Item 01"
	workspace.call("_refresh_grid")
	await process_frame
	var empty_cell: Button = grid.get_child(20) as Button
	_expect(empty_cell.icon == null and empty_cell.visible, "a filtered category leaves empty cells on the grid")
	_press(empty_cell)
	_expect(_take(receiver) == Protocol.deposit_storage(0, 1),
		"an empty storage cell takes a deposit as well")
	_set_quantity(main, 20)
	_press(empty_cell)
	_expect(_take(receiver) == Protocol.deposit_storage(0, 5) and int(main.get("_carried_slot")) == -1,
		"a deposit of the rest of the stack empties the hand")
	_set_quantity(main, 1)
	filter.text = ""
	workspace.call("_refresh_grid")
	await process_frame

	# Alt+click stores a whole stack, and a double click withdraws at once.
	_press(slots[1] as Button, false, true)
	_expect(_take(receiver) == Protocol.deposit_storage(1, 2)
		and int(main.get("_carried_slot")) == -1,
		"Alt+click on a backpack item stores the whole stack while storage is open")
	var fourth: Button = grid.get_child(3) as Button
	_press(fourth)
	_press(fourth, true)
	_expect(_take(receiver) == Protocol.withdraw_storage(3, 1)
		and int(main.get("_storage_carried_position")) == -1,
		"double-clicking a stored item withdraws it and leaves the hand empty")

	# A right click puts the carry back before it does anything else.
	var add_menu: PopupMenu = workspace.get("add_menu") as PopupMenu
	_press(slots[0] as Button)
	_button(grid.get_child(2) as Button, MOUSE_BUTTON_RIGHT)
	_expect(int(main.get("_carried_slot")) == -1 and not add_menu.visible,
		"a right click on storage with an item in hand only puts it back")
	_press(grid.get_child(5) as Button)
	var right := InputEventMouseButton.new()
	right.button_index = MOUSE_BUTTON_RIGHT
	right.pressed = true
	main.call("_on_world_gui_input", right)
	_expect(int(main.get("_storage_carried_position")) == -1,
		"a right click on the world behind the storage window puts the stored item back")

	# All must follow the source stack, not the last inventory selection.
	var inventory_ui: Control = main.get("inventory_workspace") as Control
	main.set("selected_inventory_slot", -1)
	inventory_ui.call("_quantity_all")
	_expect(str(main.call("_slot_cursor_target", second)) == "item_grab", "stored stacks show the grab cursor")
	_press(second)
	_press(slots[5] as Button)
	_expect(_take(receiver) == Protocol.withdraw_storage(1, 11)
		and not bool(main.call("_has_carry")), "All withdraws a complete storage stack without a selected inventory item")
	_press(slots[0] as Button)
	_press(grid.get_child(4) as Button)
	_expect(_take(receiver) == Protocol.deposit_storage(0, 5)
		and not bool(main.call("_has_carry")), "All deposits the complete backpack stack after withdrawing a different amount")
	# Pouch stacks use their authoritative special slot, too.
	(state.get("inventory") as Dictionary)[128] = {"image_id": 3, "quantity": 23}
	main.call("_sync_inventory")
	var pouch: Control = inventory_ui.get("reagent_pouch") as Control
	pouch.call("_select", 128)
	_expect(int(main.get("_carried_slot")) == 128, "Grab lifts a pouch stack onto the cursor")
	_press(grid.get_child(4) as Button)
	_expect(_take(receiver) == Protocol.deposit_storage(128, 23)
		and not bool(main.call("_has_carry")), "All deposits the complete pouch stack through the grab cursor")
	(state.get("inventory") as Dictionary).erase(128)
	main.call("_on_quantity_box_pressed", 0)
	main.call("_sync_inventory")

	# The stored item in hand is followed by name when positions shift, and
	# dropped with the window or the category.
	_press(grid.get_child(5) as Button)
	var shifted_items: Dictionary = {0: {"image_id": 90, "quantity": 1}}
	var shifted_described: Dictionary = {0: {"name": "Aardvark Hide", "subtype": "Food"}}
	for position: int in range(200):
		shifted_items[position + 1] = items[position]
		shifted_described[position + 1] = described[position]
	var storage_state: Dictionary = state.get("storage") as Dictionary
	storage_state["items"] = shifted_items
	storage_state["described"] = shifted_described
	main.call("_sync_storage")
	_press(slots[5] as Button)
	_expect(_take(receiver) == Protocol.withdraw_storage(6, 1),
		"a stored item in hand follows its stack when a new kind of item shifts the positions")
	storage_state["category_id"] = 2
	main.call("_update_carried_item")
	_expect(int(main.get("_storage_carried_position")) == -1, "opening another category puts the stored item back")
	storage_state["category_id"] = 1
	main.call("_sync_storage")
	_press(grid.get_child(5) as Button)
	state.call("close_storage")
	main.call("_sync_storage")
	_expect(int(main.get("_storage_carried_position")) == -1 and not carried.visible,
		"closing storage puts the stored item back")

	# The bag icon opens the bag on our tile and takes every stack on reply.
	var saved_actors: Dictionary = state.get("actors")
	var saved_bags: Dictionary = state.get("ground_bags")
	var saved_bag: Dictionary = state.get("ground_bag")
	var saved_actor_id: int = int(state.get("local_actor_id"))
	state.set("local_actor_id", 99)
	state.set("actors", {99: {"x": 10, "y": 20}})
	state.set("ground_bags", {7: {"x": 10, "y": 20}})
	state.set("ground_bag", {"open": false, "items": {}})
	pouch.call("sync")
	var bag_button: Button = pouch.get("drop_button") as Button
	_expect(not bag_button.disabled, "the bag icon is available for a bag at our feet without a selected pouch item")
	bag_button.pressed.emit()
	_expect(_take(receiver) == Protocol.inspect_bag(7), "left-clicking the bag icon asks to open the bag at our feet")
	state.call("_on_packet", 23, PackedByteArray([1, 3, 0, 17, 0, 0, 0, 2]))
	main.call("_sync_ground_bag")
	_expect(str(main.call("_slot_cursor_target", (main.get("ground_bag_slot_buttons") as Array)[0])) == "item_grab", "bag stacks show the grab cursor")
	_expect(_take(receiver) == Protocol.pick_up_ground_item(2, 17)
		and (main.get("ground_bag_panel") as Control).visible, "the bag reply opens its window and requests all of its stack")
	(main.get("ground_bag_panel") as Control).hide()
	bag_button.pressed.emit()
	_expect(_take(receiver) == Protocol.pick_up_ground_item(2, 17)
		and (main.get("ground_bag_panel") as Control).visible, "an already-open bag is shown again and gets all without another inspect request")
	inventory_ui.call("_quantity_all")
	main.call("_on_ground_bag_slot_pressed", 0)
	_expect(_take(receiver) == Protocol.pick_up_ground_item(2, 17), "All also takes a full bag stack with one item click")
	main.call("_begin_carry", 0)
	main.call("_on_ground_bag_slot_pressed", 0)
	_expect(_take(receiver) == Protocol.drop_inventory_item(0, 5)
		and not bool(main.call("_has_carry")), "clicking the bag with a carried item drops All of that stack")
	main.call("_on_quantity_box_pressed", 0)
	state.set("actors", {99: {"x": 11, "y": 20}})
	pouch.call("sync")
	_expect(bag_button.disabled, "the bag icon cannot take from a neighboring tile")
	state.set("actors", saved_actors)
	state.set("ground_bags", saved_bags)
	state.set("ground_bag", saved_bag)
	state.set("local_actor_id", saved_actor_id)
	main.call("_sync_ground_bag")
	_close_fixture(fixture)
	main.set("_inventory_quantities", saved_quantities)
	main.set("_selected_quantity_box", saved_box)
	main.call("_cancel_carry")
	state.set("inventory", saved_inventory)
	state.set("storage", saved_storage)
	main.call("_sync_storage")
	main.call("_sync_inventory")
	lists_panel.visible = lists_were_visible
	await process_frame

func _set_quantity(main: Node, quantity: int) -> void:
	var quantities: Array[int] = main.get("_inventory_quantities") as Array[int]
	quantities[int(main.get("_selected_quantity_box"))] = quantity

## A left press and release on a control, with the modifiers a player would hold.
func _press(control: Control, double: bool = false, alt: bool = false) -> void:
	var at: Vector2 = control.get_global_rect().get_center()
	_click(at, true, double, alt)
	_click(at, false)

func _button(control: Control, index: MouseButton) -> void:
	var at: Vector2 = control.get_global_rect().get_center()
	_click(at, true, false, false, index)
	_click(at, false, false, false, index)

func _click(at: Vector2, pressed: bool, double: bool = false, alt: bool = false,
		index: MouseButton = MOUSE_BUTTON_LEFT) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = at
	motion.global_position = at
	root.push_input(motion)
	var event := InputEventMouseButton.new()
	event.button_index = index
	event.pressed = pressed
	event.double_click = double
	event.alt_pressed = alt
	event.position = at
	event.global_position = at
	if pressed:
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if index == MOUSE_BUTTON_LEFT else MOUSE_BUTTON_MASK_RIGHT
	root.push_input(event)

## Everything the client has sent since the last call. Loopback delivery is
## quick but not instant, so an empty read waits briefly before believing it.
func _take(receiver: StreamPeerTCP) -> PackedByteArray:
	for attempt: int in range(25):
		receiver.poll()
		if receiver.get_available_bytes() > 0:
			break
		OS.delay_usec(2000)
	var available: int = receiver.get_available_bytes()
	if available <= 0:
		return PackedByteArray()
	return receiver.get_data(available)[1] as PackedByteArray

## Points the Network singleton at a local socket so sent frames can be read.
func _open_fixture() -> Dictionary:
	var network: Node = root.get_node("Network")
	var old_peer: StreamPeerTCP = network.get("_peer") as StreamPeerTCP
	var old_secure: bool = network.get("_secure")
	var was_processing := network.is_processing()
	var peer := StreamPeerTCP.new()
	var server := TCPServer.new()
	if not _expect(server.listen(0, "127.0.0.1") == OK, "local transfer fixture listens"):
		return {}
	network.set_process(false)
	network.set("_peer", peer)
	# This fixture exchanges raw protocol frames over loopback. Production
	# connections still default to verified TLS; restore that mode afterwards.
	network.set("_secure", false)
	var fixture := {"server": server, "peer": peer, "receiver": null,
		"old_peer": old_peer, "old_secure": old_secure, "was_processing": was_processing}
	if not _expect(peer.connect_to_host("127.0.0.1", server.get_local_port()) == OK,
			"local transfer fixture starts connecting"):
		_close_fixture(fixture)
		return {}
	var deadline := Time.get_ticks_msec() + 2000
	while Time.get_ticks_msec() < deadline:
		peer.poll()
		if peer.get_status() == StreamPeerTCP.STATUS_CONNECTED and server.is_connection_available():
			fixture.receiver = server.take_connection()
			break
		await process_frame
	if not _expect(fixture.receiver != null and bool(network.call("_link_ready")),
			"local transfer fixture connects with a usable protocol transport"):
		_close_fixture(fixture)
		return {}
	peer.poll()
	return fixture

func _close_fixture(fixture: Dictionary) -> void:
	var network: Node = root.get_node("Network")
	(fixture["peer"] as StreamPeerTCP).disconnect_from_host()
	if fixture["receiver"] != null:
		(fixture["receiver"] as StreamPeerTCP).disconnect_from_host()
	(fixture["server"] as TCPServer).stop()
	network.set("_peer", fixture["old_peer"])
	network.set("_secure", fixture["old_secure"])
	network.set_process(bool(fixture["was_processing"]))

func _expect(condition: bool, label: String) -> bool:
	if not condition:
		failures += 1
		push_error("FAIL: " + label)
	return condition
