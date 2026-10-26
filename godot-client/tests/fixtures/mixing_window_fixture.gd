extends RefCounted

static func populate(main: Control) -> int:
	var app := main.get_node("/root/AppState")
	app.authenticated = true
	app.inventory = {0: {"image_id": 101, "quantity": 60}, 1: {"image_id": 36, "quantity": 40}, 2: {"image_id": 8, "quantity": 1}}
	app.inventory_names = {0: "Sage", 1: "Cloth Roll", 2: "Mortar and Pestle"}
	app.stats = {"health": 120, "max_health": 150, "ether": 45, "max_ether": 60, "food": 42, "carried": 205, "capacity": 320, "action_points": 28, "max_action_points": 30}
	app.mix_state = {"near_storage": true, "running": false}
	main.manufacturing_ready_only.button_pressed = false
	main.manufacturing_skill = ""
	main.manufacturing_filter.text = ""
	var bandage := -1
	var torch := -1
	for index: int in main.manufacturing_catalog.count():
		var recipe: Dictionary = main.manufacturing_catalog.recipe(index)
		if recipe.output == "Bandage" and recipe.skill == "potion": bandage = index
		if recipe.output == "Torch": torch = index
	main.selected_manufacturing_recipe = bandage
	main._set_manufacturing_quantity(20)
	main.manufacturing_queue.clear()
	main.manufacturing_queue.append({"recipe": bandage, "wanted": 20, "made": 0})
	main.manufacturing_queue.append({"recipe": torch, "wanted": 10, "made": 0})
	main.manufacturing_server_status = "Ready · inventory supplies available"
	main._sync_stats()
	main._sync_inventory()
	main._sync_manufacturing()
	# A representative browser for visual comparison, using real catalogue IDs.
	var iron := -1
	for index: int in main.manufacturing_catalog.count():
		if main.manufacturing_catalog.recipe(index).get("output") == "Iron Bar": iron = index
	main.manufacturing_list.clear()
	for index: int in [bandage, torch, iron]:
		main.manufacturing_list.add_item(str(main.manufacturing_catalog.recipe(index).output))
		main.manufacturing_list.set_item_metadata(main.manufacturing_list.item_count - 1, index)
	main.manufacturing_list.select(0)
	main._on_manufacturing_selected(0)
	main.manufacturing_panel.show()
	return bandage
