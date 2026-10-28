extends SceneTree
var failures := 0

func _init() -> void: call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func run() -> void:
	var state := root.get_node("AppState")
	state.inventory = {0: {"image_id": 1, "quantity": 2}, 133: {"image_id": 584, "quantity": 10000000}, 127: {"image_id": 0, "quantity": 1500000}}
	state.inventory_names = {0: "Bread", 133: "Life Distillate"}
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	check(catalog.inventory_quantity(584, state.inventory) == 10000000, "spell costs see large pouch reserves")
	var crafting := ManufacturingCatalog.new()
	check(crafting._inventory_slot_for_name(state.inventory, state.inventory_names, "Life Distillate", 1, false) == 133, "crafting resolves supplies from the pouch")
	var market = load("res://src/ui/extension_windows.gd").new()
	var listed := false
	for entry: Dictionary in market._market_sell_entries():
		if entry.name == "Life Distillate" and entry.slot == 133: listed = true
	check(listed, "the Exchange can list pouch supplies for sale")
	market.free()
	var pouch = load("res://src/ui/reagent_pouch.gd").new()
	root.add_child(pouch)
	await process_frame
	check(pouch.references.size() == 1 and pouch.slots.size() == 8, "pouch has exactly eight type slots and excludes backpack items")
	check(pouch.counts[0].text == "10,000,000", "large balances use commas")
	check(pouch.grouped(4294967295) == "4,294,967,295", "maximum reserve uses commas without rounding")
	pouch._select_index(0)
	pouch._sync_actions()
	check(pouch.selected_reference() == 133 and not pouch.drop_button.disabled, "pouch actions retain authoritative item identity")
	check(pouch.gold.text.contains("1,500,000") and pouch.heading.text.contains("1/8"), "gold has a dedicated slot outside the type allowance")
	check(pouch.store_button.disabled, "deposit requires an open storage session")
	state.inventory.erase(133)
	state.state_changed.emit(&"inventory")
	check(pouch.references.size() == 0 and pouch.drop_button.disabled, "consumption and transfer updates clear exhausted supplies")
	pouch.queue_free()
	await process_frame
	print("reagent pouch: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
