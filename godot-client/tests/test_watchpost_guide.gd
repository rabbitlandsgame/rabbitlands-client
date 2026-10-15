extends SceneTree

class GuideHost extends Control:
	var inventory_slot_buttons: Array = []
	var manufacturing_mix_one: Button
	var manufacturing_detail: Control

var failures := 0

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)

func _init() -> void:
	call_deferred("run")

func run() -> void:
	check_medicine_catalog()
	var host := GuideHost.new()
	root.add_child(host)
	var panel := PanelContainer.new()
	panel.name = "ManufacturingPanel"
	host.add_child(panel)
	panel.owner = host
	panel.unique_name_in_owner = true
	var list := ItemList.new()
	list.name = "ManufacturingList"
	host.add_child(list)
	list.owner = host
	list.unique_name_in_owner = true
	list.add_item("Bandage")
	list.add_item("Torch")
	host.manufacturing_mix_one = Button.new()
	host.add_child(host.manufacturing_mix_one)
	var guide: Control = load("res://src/ui/lantern_guide.gd").new()
	host.add_child(guide)
	guide.configure(host)
	guide.set_process(false)
	var app_state := root.get_node("AppState")
	var authenticated: bool = app_state.authenticated
	app_state.authenticated = true
	var state := {"active":true, "tutorial":"watchpost", "stage":4, "total":6,
		"title":"Gather the ingredients", "hint":"Gather 2 Sage.",
		"key":"sage", "count":1, "required":2, "control":"world", "item":"Sage"}
	guide.apply_state(state)
	expect(guide.chapter.text == "HELP FOR THE WATCHPOST  ·  4 / 6", "quest uses its own chapter label")
	expect(guide.instruction.text.contains("Progress: 1 / 2"), "gathering progress is visible")
	expect(guide.help.visible and guide.help.text == "Quest help", "quest help is available")
	state.stage = 5
	state.key = "watchpost"
	state.required = 1
	state.control = "manufacture"
	state.item = "Bandage"
	guide.apply_state(state)
	list.select(0)
	expect(guide.control_for_step() == host.manufacturing_mix_one, "selected Bandage highlights Mix One")
	list.select(1)
	expect(guide.control_for_step() == list, "another recipe points back to the recipe list")
	guide.apply_state({"active":false})
	expect(not guide.visible, "completion hides the guide")
	app_state.authenticated = authenticated
	host.queue_free()
	print("Watchpost guide: %d failures" % failures)
	quit(failures)

func check_medicine_catalog() -> void:
	var catalog := ManufacturingCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/manufacturing/recipes.json")))
	var medicine_index := -1
	for index: int in range(catalog.count()):
		var recipe := catalog.recipe(index)
		if recipe.get("skill") == "potion" and recipe.get("output") == "Bandage":
			medicine_index = index
			break
	expect(medicine_index >= 0, "Potion tab contains the watchpost Bandage recipe")
	if medicine_index < 0:
		return
	var definition := catalog.recipe(medicine_index)
	expect(int(definition.get("id", -1)) == medicine_index, "medicine uses its server recipe index")
	expect(int(definition.get("level", -1)) == 0 and int(definition.get("knowledgeIndex", 0)) == -1,
		"new players can mix medicine without research")
	var ingredients := {}
	for ingredient: Dictionary in definition.get("ingredients", []):
		ingredients[ingredient.name] = int(ingredient.quantity)
	expect(ingredients == {"Sage":2, "Cloth Roll":1}, "medicine lists the quest's ingredients")
	var available := catalog.availability(medicine_index,
		{0:{"quantity":2}, 1:{"quantity":1}, 2:{"quantity":1}}, [],
		{"food":10, "ether":0}, {0:"Sage", 1:"Cloth Roll", 2:"Mortar and Pestle"})
	expect(available.reasons.is_empty(), "quest supplies make the real recipe ready")
	expect(available.selection == [{"slot":0, "quantity":2}, {"slot":1, "quantity":1}],
		"mixing spends Sage and cloth while keeping the mortar")
