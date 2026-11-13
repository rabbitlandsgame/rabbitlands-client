extends SceneTree
const Catalog := preload("res://src/state/manufacturing_catalog.gd")
var failures := 0

class FoodBench extends Control:
	var manufacturing_catalog := Catalog.new()
	var selected_manufacturing_recipe := -1
	var manufacturing_quantity := LineEdit.new()
	var manufacturing_list := ItemList.new()
	var manufacturing_detail := RichTextLabel.new()
	var manufacturing_queue: Array[Dictionary] = []
	var manufacturing_queue_running := false
	var manufacturing_queue_index := 0
	func _slot_icon(_image: int, _fallback: int) -> Texture2D: return null
	func _manufacturing_from_storage() -> bool: return false
	func _manufacturing_quantity_value() -> int: return 2
	func _carried_count(_name: String) -> int: return 10
	func _manufacturing_availability(_index: int) -> Dictionary: return {"reasons": []}
	func _on_manufacturing_queue_remove_pressed(_index: int) -> void: pass
	func _on_manufacturing_queue_clear_pressed() -> void: pass

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _init() -> void: call_deferred("run")

func run() -> void:
	var bench := FoodBench.new()
	root.add_child(bench)
	for control: Control in [bench.manufacturing_quantity, bench.manufacturing_list, bench.manufacturing_detail]: bench.add_child(control)
	bench.manufacturing_catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/manufacturing/recipes.json")))
	var bread := -1
	for index: int in bench.manufacturing_catalog.count():
		var recipe := bench.manufacturing_catalog.recipe(index)
		if recipe.output == "Cooked Meat": bench.selected_manufacturing_recipe = index
		if recipe.output == "Bread": bread = index
	var cooked := bench.manufacturing_catalog.recipe(bench.selected_manufacturing_recipe)
	expect(int(cooked.get("outputQuantity", 1)) == 5, "Cooking yields five items")
	expect(int(cooked.get("mana", -1)) == 0 and int(bench.manufacturing_catalog.recipe(bread).get("mana", -1)) == 0, "Both food recipes need no ether")
	var held: Dictionary = {}
	var names: Dictionary = {}
	for ingredient: Dictionary in cooked.ingredients:
		var slot := held.size()
		held[slot] = {"image_id": int(ingredient.imageId), "quantity": int(ingredient.quantity)}
		names[slot] = str(ingredient.name)
	expect(bench.manufacturing_catalog.availability(bench.selected_manufacturing_recipe, held, [], {"food": 40, "ether": 0}, names).reasons.is_empty(), "Cooking is available with the exact ingredients and zero ether")
	var workspace: Control = load("res://src/ui/mixing_workspace.gd").new()
	bench.add_child(workspace)
	workspace.main = bench
	workspace.details = VBoxContainer.new()
	workspace.queue_body = VBoxContainer.new()
	workspace.queue_toggle = Button.new()
	workspace.queue_start = Button.new()
	for control: Control in [workspace.details, workspace.queue_body, workspace.queue_toggle, workspace.queue_start]: workspace.add_child(control)
	workspace._render_detail()
	expect(workspace.selector.get_item_text(0).ends_with("×5"), "The selected recipe shows five results")
	expect(bench.manufacturing_quantity.tooltip_text.contains("batch makes 5"), "Quantity counts batches")
	bench.manufacturing_queue.append({"recipe": bench.selected_manufacturing_recipe, "wanted": 2, "made": 1})
	workspace._render_queue()
	var row: HBoxContainer = workspace.queue_body.get_child(0)
	expect(row.get_child(1).text.ends_with("×10"), "Two queued batches show ten meat")
	expect(row.get_child(2).text == "5/10", "Queue progress shows actual item counts")
	bench.queue_free()
	await process_frame
	print("PASS food mixing" if failures == 0 else "FAIL food mixing: %d" % failures)
	quit(failures)
