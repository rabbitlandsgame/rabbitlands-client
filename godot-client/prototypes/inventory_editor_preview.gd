extends SceneTree
## Offline interactive preview. No login, connection or item command can succeed.
var main: Control
var examples: Dictionary = {}

func _init() -> void: call_deferred("run")

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	root.title = "Rabbit Lands · inventory design sandbox · offline sample items"
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://inventory-preview.cfg"
	root.add_child(main)
	for frame: int in 10: await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var app := root.get_node("AppState")
	var contents := {}
	var names := {}
	for row: Array in [[0, 1, "Hearth Bread", "Food", 24], [1, 3, "Health Potion", "Potion", 9],
		[2, 31, "Iron Bar", "Material", 157], [3, 35, "Wood", "Material", 18],
		[4, 16, "Herbs", "Material", 12], [5, 34, "Log", "Material", 5],
		[6, 39, "Iron Sword", "Weapon", 1], [36, 45, "Leather Armor", "Armor", 1],
		[37, 46, "Leather Boots", "Armor", 1]]:
		contents[row[0]] = {"slot": row[0], "image_id": row[1], "quantity": row[4], "inventory_usable": row[0] in [0, 1]}
		names[row[0]] = row[2]
		examples[row[0]] = {"open": true, "image_id": row[1], "name": row[2], "category": row[3], "quantity": row[4],
			"equipped": row[0] >= 36, "equip_type": row[3] if row[3] in ["Weapon", "Armor"] else "",
			"description": "Baked before dawn at the Four Gates ovens." if row[0] == 0 else "An offline sample item for exploring the inventory designs.",
			"stats": "Restores 40 food. Weight 2." if row[0] == 0 else "Sample item · gameplay commands are disabled"}
	app.set("inventory", contents)
	app.set("inventory_names", names)
	app.set("stats", {"health": 120, "max_health": 150, "ether": 45, "max_ether": 60,
		"action_points": 28, "max_action_points": 30, "food": 42, "carried": 205, "capacity": 320})
	main.selected_inventory_slot = 0
	main._sync_stats()
	main._sync_inventory()
	main.inventory_panel.show()
	main.inventory_workspace.inspection_requested.connect(func(slot: int, full: bool) -> void:
		if examples.has(slot): main.inventory_workspace.present_detail.call_deferred(examples[slot].duplicate(true), full))
	var panel := PanelContainer.new()
	panel.position = Vector2(20, 24)
	panel.add_theme_stylebox_override("panel", preload("res://src/ui/compact_hud_style.gd").box())
	main.game_view.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	var label := Label.new()
	label.text = "Offline inventory sandbox\nSample items only · no server connection\nChoose a design in Inventory •••, then Edit inventory."
	column.add_child(label)
	var edit := Button.new()
	edit.text = "Edit inventory…"
	edit.pressed.connect(main.inventory_workspace.open_editor)
	column.add_child(edit)
	var hud := Button.new()
	hud.text = "Edit main HUD…"
	hud.pressed.connect(main.hud_workspace.open_editor)
	column.add_child(hud)
	main.window_stack.register(panel)
	main.inventory_workspace.request_inspection(0, true)
	if OS.get_cmdline_user_args().has("--inventory-preview-smoke"):
		for frame: int in 5: await process_frame
		main.inventory_workspace.open_editor()
		var valid: bool = root.get_node("Network").offline_hud_preview and main.inventory_workspace.is_editing() and main.inventory_workspace.inspection_title.text == "Hearth Bread"
		main.inventory_workspace.finish_edit(false)
		print("INVENTORY SANDBOX: ", "PASS" if valid else "FAIL")
		main.queue_free()
		for frame: int in 5: await process_frame
		quit(0 if valid else 1)
