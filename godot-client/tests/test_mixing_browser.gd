extends SceneTree
const Fixture := preload("res://tests/fixtures/mixing_window_fixture.gd")
const Names := preload("res://src/state/item_names.gd")
var checks := 0
var failures := 0
var main: Control
var workspace: Control
var artifacts := "res://test-artifacts/mixing-browser"
func _init() -> void: call_deferred("run")
func frames(count := 6) -> void:
	for frame: int in count: await process_frame
func expect(ok: bool, label: String) -> void:
	checks += 1
	if ok: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
func listed(index: int) -> bool:
	for row: int in main.manufacturing_list.item_count:
		if int(main.manufacturing_list.get_item_metadata(row)) == index: return true
	return false
func select_output(output: String) -> void:
	for index: int in main.manufacturing_catalog.count():
		if main.manufacturing_catalog.recipe(index).get("output") == output:
			main.selected_manufacturing_recipe = index
			main._sync_manufacturing()
			return
	expect(false, "real recipe exists: " + output)
func screenshot(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(artifacts.path_join(name))
func run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(artifacts))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = artifacts.path_join("browser_%d.cfg" % Time.get_ticks_usec())
	root.add_child(main)
	await frames(10)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	main.chat_hud.hide()
	main.system_chat_hud.hide()
	Fixture.populate(main)
	workspace = main.mixing_workspace
	workspace.choose_preset("workbench", true)
	main.manufacturing_ready_only.button_pressed = false
	var fixed_size: Vector2 = main.manufacturing_panel.size
	for output: String in ["Militia Arming Sword", "Potion of Manufacturing", "Stormglass Shield Spear", "Sunmane Twin Crescent Glaive"]:
		select_output(output)
		await frames()
		expect(workspace.selector.get_item_text(0) == Names.display(output), "selected title uses the simple name: " + output)
		expect(main.manufacturing_panel.size == fixed_size and workspace.groups.details.get_global_rect().grow(1).encloses(workspace.selector.get_global_rect()), "long title stays within the fixed workbench: " + output)
		workspace.model.working.font_size = 20
		workspace._fit_selector()
		var font: Font = workspace.selector.get_theme_font("font")
		var size: int = workspace.selector.get_theme_font_size("font_size")
		expect(font.get_string_size(Names.display(output), HORIZONTAL_ALIGNMENT_LEFT, -1, size).x <= workspace._selector_text_width() + 1, "font fits the actual title width: " + output)
		if output == "Stormglass Shield Spear": expect(size < 20, "oversized title font shrinks to fit")
		workspace.model.working.font_size = 12
		workspace.apply_layout()
	select_output("Militia Arming Sword")
	await frames()
	await screenshot("01-iron-sword-fixed-workbench.png")
	expect(main.manufacturing_catalog.recipe(main.selected_manufacturing_recipe).output == "Militia Arming Sword", "display naming preserves the canonical recipe identity")
	var pack: Control = main.inventory_workspace
	pack._detail = {"name": "Militia Arming Sword", "image_id": 374}
	pack._render_detail()
	expect(pack.inspection_title.text == "Iron Sword" and pack.inspection_title.tooltip_text.contains("Militia Arming Sword"), "inspection uses the same simple name and retains the original search name")
	var selected: int = main.selected_manufacturing_recipe
	workspace.set_sort_mode("name")
	await frames()
	var names: Array[String] = []
	for row: int in main.manufacturing_list.item_count: names.append(main.manufacturing_list.get_item_text(row))
	var sorted := names.duplicate()
	sorted.sort_custom(func(a: String, b: String) -> bool: return a.naturalnocasecmp_to(b) < 0)
	expect(names == sorted, "A sorts by the player-facing names")
	workspace.sort_order.pressed.emit()
	await frames()
	var ascending := true
	var last_level := -1
	for row: int in main.manufacturing_list.item_count:
		var level := int(main.manufacturing_catalog.recipe(int(main.manufacturing_list.get_item_metadata(row))).get("level", 0))
		ascending = ascending and level >= last_level
		last_level = level
	expect(main.manufacturing_sort_mode == "level" and workspace.sort_order.text == "L" and ascending, "L sorts numeric required levels, low to high")
	expect(main.selected_manufacturing_recipe == selected, "changing sort keeps the selected recipe ID")
	for query: String in ["Iron Sword", "Militia Arming Sword"]:
		main.manufacturing_filter.text = query
		main._sync_manufacturing()
		expect(listed(selected), "search accepts " + query)
	main.manufacturing_filter.text = ""
	var app := root.get_node("AppState")
	var demanding := -1
	for index: int in main.manufacturing_catalog.count():
		var recipe: Dictionary = main.manufacturing_catalog.recipe(index)
		if int(recipe.get("level", 0)) >= 40 and not recipe.get("tools", []).is_empty() and not recipe.get("ingredients", []).is_empty():
			demanding = index
			break
	expect(demanding >= 0, "served catalogue includes a demanding tool-based recipe")
	if demanding >= 0:
		app.inventory.clear()
		app.inventory_names.clear()
		for ingredient: Dictionary in main.manufacturing_catalog.recipe(demanding).ingredients:
			var slot: int = app.inventory.size()
			app.inventory[slot] = {"image_id": int(ingredient.imageId), "quantity": int(ingredient.quantity)}
			app.inventory_names[slot] = str(ingredient.name)
		app.stats.food = 0
		app.stats.ether = 0
		app.stats.manufacturing = 0
		app.stats.alchemy = 0
		main._sync_stats()
		main._set_manufacturing_quantity(1)
		app.known_knowledge.clear()
		workspace.ingredients_only.pressed.emit()
		main.selected_manufacturing_recipe = demanding
		main._sync_manufacturing()
		await frames()
		expect(workspace.ingredients_only.button_pressed and listed(demanding), "I includes stocked recipes despite missing tools, food, mana, books and levels")
		expect(main.manufacturing_mix_one.disabled, "ingredient filtering keeps the actual mix requirements intact")
		await screenshot("03-ingredients-available-without-tools-or-food.png")
		app.inventory.clear()
		app.state_changed.emit(&"inventory")
		await frames()
		expect(not listed(demanding), "I excludes recipes after their ingredients are spent")
	app.mix_state.near_storage = true
	main.manufacturing_source.button_pressed = true
	main._sync_manufacturing()
	await frames()
	expect(workspace.ingredients_only.disabled and not workspace.ingredients_only.button_pressed and main.manufacturing_list.item_count == main.manufacturing_catalog.count(), "storage leaves unseen stock unfiltered and disables I")
	main.manufacturing_sort_mode = "name"
	main.manufacturing_ready_preference = false
	workspace._load_browser_preferences()
	expect(main.manufacturing_sort_mode == "level" and main.manufacturing_ready_preference, "browser preferences reload independently of HUD presets")
	Fixture.populate(main)
	workspace.set_sort_mode("level")
	main.manufacturing_panel.show()
	await frames()
	await screenshot("02-level-sort-and-ingredient-toggle.png")
	print("MIXING BROWSER: %d checks, %d failures" % [checks, failures])
	main.queue_free()
	await frames()
	quit(0 if failures == 0 else 1)
