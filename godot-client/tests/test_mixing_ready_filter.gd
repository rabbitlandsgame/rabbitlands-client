extends SceneTree

var failures := 0
var checks := 0
var main: Control
var app_state: Node

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func _init() -> void:
	call_deferred("run")

func stock(recipe: Dictionary) -> void:
	app_state.inventory.clear()
	app_state.inventory_names.clear()
	for group: String in ["ingredients", "tools"]:
		for item: Dictionary in recipe.get(group, []):
			var slot: int = app_state.inventory.size()
			app_state.inventory[slot] = {"image_id":int(item.imageId), "quantity":int(item.quantity)}
			app_state.inventory_names[slot] = str(item.name)
	app_state.stats = {"food":45, "ether":1000, "animal_nexus":100}
	app_state.known_knowledge.clear()
	if int(recipe.get("knowledgeIndex", -1)) >= 0:
		app_state.known_knowledge.append(int(recipe.knowledgeIndex))
	app_state.state_changed.emit(&"inventory")

func listed(recipe_index: int) -> bool:
	var list: ItemList = main.get("manufacturing_list")
	for row: int in range(list.item_count):
		if int(list.get_item_metadata(row)) == recipe_index:
			return true
	return false

func run() -> void:
	app_state = root.get_node("AppState")
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("GameView").show()
	app_state.authenticated = true
	var catalog: ManufacturingCatalog = main.get("manufacturing_catalog")
	var medicine := -1
	var researched := -1
	var mana_recipe := -1
	var summon := -1
	for index: int in range(catalog.count()):
		var recipe := catalog.recipe(index)
		if recipe.skill == "potion" and recipe.output == "Bandage": medicine = index
		if int(recipe.knowledgeIndex) >= 0: researched = index
		if int(recipe.mana) > 0 and recipe.skill != "summoning": mana_recipe = index
		if recipe.skill == "summoning" and int(recipe.animalNexus) > 0: summon = index
	expect(medicine >= 0 and researched >= 0 and mana_recipe >= 0 and summon >= 0,
		"served catalog has medicine, research, mana and nexus examples")
	if medicine < 0 or researched < 0 or mana_recipe < 0 or summon < 0:
		quit(failures)
		return
	stock(catalog.recipe(medicine))
	main.call("_on_manufacturing_button_pressed")
	var ready: CheckButton = main.get("manufacturing_ready_only")
	var list: ItemList = main.get("manufacturing_list")
	expect(ready.button_pressed and listed(medicine) and list.item_count < catalog.count(),
		"mixing defaults to ready recipes, including the carried Bandage supplies")
	ready.button_pressed = false
	expect(list.item_count == catalog.count(), "turning off the option shows every recipe")
	ready.button_pressed = true
	main.set("manufacturing_skill", "potion")
	var search: LineEdit = main.get("manufacturing_filter")
	search.text = "bandage"
	main.call("_sync_manufacturing")
	expect(list.item_count == 1 and listed(medicine), "readiness combines with skill and search filters")
	main.call("_on_manufacturing_selected", 0)
	app_state.inventory[0].quantity = 1
	app_state.state_changed.emit(&"inventory")
	expect(not listed(medicine) and list.item_count == 0, "spending Sage immediately removes the recipe")
	expect(int(main.get("selected_manufacturing_recipe")) == -1
		and (main.get("manufacturing_mix_one") as Button).disabled,
		"a hidden recipe loses selection and cannot be mixed")
	expect((main.get("manufacturing_detail") as RichTextLabel).text.contains("No recipes match"),
		"an empty filtered list explains how to see recipes again")
	stock(catalog.recipe(medicine))
	expect(listed(medicine), "replenishing supplies restores the recipe")
	app_state.inventory.erase(2)
	app_state.inventory_names.erase(2)
	app_state.state_changed.emit(&"inventory")
	expect(not listed(medicine), "missing tools hide an otherwise stocked recipe")
	stock(catalog.recipe(medicine))
	app_state.stats.food = 0
	app_state.state_changed.emit(&"stats")
	expect(list.item_count == 0, "no food hides recipes until the player eats")
	main.set("manufacturing_skill", "")
	search.text = ""
	stock(catalog.recipe(researched))
	expect(listed(researched), "a researched recipe is ready with its supplies")
	app_state.known_knowledge.clear()
	app_state.state_changed.emit(&"knowledge")
	expect(not listed(researched), "unread research hides its recipe")
	stock(catalog.recipe(mana_recipe))
	expect(listed(mana_recipe), "sufficient mana allows a stocked potion recipe")
	app_state.stats.ether = 0
	app_state.state_changed.emit(&"stats")
	expect(not listed(mana_recipe), "insufficient mana hides a recipe")
	stock(catalog.recipe(summon))
	expect(listed(summon), "a stocked summon with its nexus is ready")
	app_state.stats.animal_nexus = 0
	app_state.state_changed.emit(&"stats")
	expect(not listed(summon), "insufficient Animal Nexus hides a summon")
	app_state.stats.animal_nexus = 100
	app_state.combat_state.active = true
	app_state.state_changed.emit(&"combat_state")
	expect(not listed(summon), "combat hides summons that the server would refuse")
	app_state.combat_state.active = false
	app_state.state_changed.emit(&"combat_state")
	expect(listed(summon), "leaving combat restores eligible summons")
	app_state.mix_state.near_storage = true
	app_state.state_changed.emit(&"mix_state")
	var source: CheckButton = main.get("manufacturing_source")
	source.button_pressed = true
	expect(ready.disabled and not ready.button_pressed and list.item_count == catalog.count(),
		"storage allows browsing recipes without assuming its unseen stock")
	app_state.mix_state.near_storage = false
	app_state.state_changed.emit(&"mix_state")
	expect(not ready.disabled and ready.button_pressed and not source.button_pressed,
		"leaving storage restores the player's readiness preference")
	ready.button_pressed = false
	main.call("_on_manufacturing_close_pressed")
	main.call("_on_manufacturing_button_pressed")
	expect(not ready.button_pressed and list.item_count == catalog.count(),
		"the selected option survives closing and reopening the window")
	main.queue_free()
	await process_frame
	print("Mixing readiness: %d checks, %d failures" % [checks, failures])
	quit(failures)
