extends SceneTree

const Fixture := preload("res://tests/fixtures/mixing_window_fixture.gd")
var checks := 0
var failures := 0
var main: Control

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
func frames() -> void:
	for frame: int in 6: await process_frame
func capture(label: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await frames()
	await RenderingServer.frame_post_draw
	var folder := "res://test-artifacts/recipe-alternatives"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	root.get_texture().get_image().save_png(folder.path_join(label + ".png"))
func page_text(node: Node) -> String:
	var text := ""
	if node is Label: text += node.text
	if node is RichTextLabel: text += node.get_parsed_text()
	for child: Node in node.get_children(): text += " " + page_text(child)
	return text
func run() -> void:
	create_timer(120).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	main.set_script(load("res://tests/fixtures/offline_ui_main.gd"))
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/recipe-alternatives.cfg"
	root.add_child(main)
	await frames()
	Fixture.populate(main)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	main.chat_hud.hide()
	main.system_chat_hud.hide()
	main.inventory_panel.hide()
	main.mixing_workspace.choose_preset("workbench", true)
	main.manufacturing_filter.text = "Bandage"
	main._sync_manufacturing()
	await frames()
	expect(main.manufacturing_list.item_count == 1, "cross-skill alternatives share one mixing row")
	var catalog: ManufacturingCatalog = main.manufacturing_catalog
	var alternatives := catalog.alternatives(main.selected_manufacturing_recipe)
	expect(alternatives.size() == 2, "both real Bandage methods remain available")
	for index: int in alternatives:
		var picker: OptionButton = main.mixing_workspace.variant_selector
		expect(picker != null and picker.item_count == 2, "Mix offers both ingredient variants")
		for row: int in picker.item_count:
			if int(picker.get_item_metadata(row)) != index: continue
			expect(picker.get_item_text(row).contains(str(catalog.recipe(index).ingredients[0].name)), "variant names include ingredients")
			picker.select(row)
			picker.item_selected.emit(row)
			break
		await frames()
		expect(main.selected_manufacturing_recipe == index, "switching alternatives preserves the exact recipe identity")
		expect(main.manufacturing_list.item_count == 1, "switching alternatives keeps the item grouped")
		expect(page_text(main.mixing_workspace.details).contains(str(catalog.recipe(index).ingredients[0].name)), "selected variant renders its own ingredients")
		main._on_manufacturing_mix_all_pressed()
		expect(int(main.manufacturing_queue.back().recipe) == index, "queue stores the selected variant rather than the group representative")
		await capture("mixing-" + str(catalog.recipe(index).skill))
	# The group's position follows its lowest visible level while a higher
	# alternative remains the actual selected crafting recipe.
	main.manufacturing_filter.text = ""
	main.mixing_workspace.set_sort_mode("level")
	await frames()
	var previous := -1
	for row: int in main.manufacturing_list.item_count:
		var level: int = main.manufacturing_list.get_item_text(row).get_slice(" · ", 0).to_int()
		expect(level >= previous, "grouped level sorting remains ascending after choosing an alternative")
		previous = level
	main.manufacturing_filter.text = "Bandage"
	main.manufacturing_skill = "potion"
	main._sync_manufacturing()
	await frames()
	expect(main.manufacturing_list.item_count == 1, "skill filtering retains the matching alternative")
	main._on_manufacturing_selected(0)
	await frames()
	for row: int in main.mixing_workspace.variant_selector.item_count:
		var picker: OptionButton = main.mixing_workspace.variant_selector
		var index := int(picker.get_item_metadata(row))
		expect(picker.is_item_disabled(row) == (catalog.recipe(index).skill != "potion"), "alternative choices respect the active skill filter")
	main.manufacturing_skill = ""
	main.manufacturing_filter.text = "Sage"
	main.manufacturing_ready_only.button_pressed = true
	main._sync_manufacturing()
	expect(main.manufacturing_list.item_count == 1, "ingredient search and Available find the stocked Bandage alternative")
	var app := root.get_node("AppState")
	app.mix_state.near_storage = true
	app.mix_state.storage_known = true
	app.mix_state.storage_recipes = [alternatives[0]]
	main.manufacturing_filter.text = "Bandage"
	main.manufacturing_source.button_pressed = true
	main._sync_manufacturing()
	expect(main.manufacturing_list.item_count == 1 and int(main.manufacturing_list.get_item_metadata(0)) == alternatives[0], "storage availability selects the matching alternative")
	main.manufacturing_panel.hide()
	var window: Control = main.reference_window
	window.toggle_encyclopedia()
	var view: EncyclopediaView = window.encyclopedia
	view.show_index()
	view.call("_filter_changed", "type", "recipe")
	expect(view.filtered_entries().size() == catalog.output_count(), "encyclopedia has one entry per output")
	view.search("Bandage")
	view.call("_filter_changed", "type", "recipe")
	var entries := view.filtered_entries()
	expect(entries.size() == 1 and entries[0].title == "Bandage", "encyclopedia groups alternatives from different skills")
	var links: HFlowContainer = view.entry_page.get_node("AlternativeRecipes")
	expect(links.get_child_count() == 2, "encyclopedia preview offers direct jumps to both alternative recipes")
	await capture("encyclopedia-bandage-preview")
	links.get_child(1).pressed.emit()
	await frames()
	expect(view.content_scroll.scroll_vertical > 0, "alternative links scroll directly to the chosen recipe")
	for topic: String in ["tailoring", "potions"]:
		view.show_index()
		view.call("_filter_changed", "type", "recipe")
		view.call("_filter_changed", "query", "Bandage")
		view.call("_filter_changed", "topic", topic)
		expect(view.filtered_entries().size() == 1, "grouped Bandage is discoverable under " + topic)
	view.open_entry("tailoring", "bandage")
	var text := page_text(view.entry_page)
	expect(text.contains("Sage") and text.contains("Silverleaf") and text.contains("Tailoring") and text.contains("Potion"), "one article retains both sets of materials and skill requirements")
	await capture("encyclopedia-bandage-article")
	view.open_page_key("entry:potions:bandage-level-0")
	expect(page_text(view.entry_page).contains("Sage"), "saved links to former variant pages still open the item")
	view.set_bookmarks([
		{"key": "entry:potions:bandage-level-0", "label": "Bandage"},
		{"key": "entry:tailoring:bandage-level-4", "label": "Bandage"}])
	view.show_index()
	view.bookmarks_button.pressed.emit()
	expect(view.filtered_entries().size() == 1, "legacy variant bookmarks remain in the bookmarked ledger")
	view.bookmark_entry_button.pressed.emit()
	expect(view.bookmarks().is_empty() and view.filtered_entries().is_empty(), "removing a grouped bookmark removes saved aliases for all its former variant pages")
	view.show_index()
	view.open_entry("tailoring", "leather")
	root.size = Vector2i(1024, 720)
	await capture("encyclopedia-leather-1024")
	# Intersect level and book requirements on the same alternative.
	var synthetic := ManufacturingCatalog.new()
	synthetic.configure({"recipes": [
		{"output": "Test Material", "skill": "tailoring", "level": 0, "ingredients": []},
		{"output": "Test Material", "skill": "alchemy", "level": 40, "knowledge": "Test Book", "ingredients": []}]})
	view.configure_catalogues({"manufacturing": synthetic})
	view.call("_filter_changed", "type", "recipe")
	view.call("_filter_changed", "book_filter", 1)
	view.call("_filter_changed", "limit_level", true)
	view.call("_filter_changed", "max_level", 8)
	expect(view.filtered_entries().is_empty(), "level and book filters cannot combine requirements from different alternatives")
	view.call("_filter_changed", "book_filter", 2)
	expect(view.filtered_entries().size() == 1, "the low-level alternative remains discoverable without a book")
	main.queue_free()
	await frames()
	print("RECIPE ALTERNATIVES: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
