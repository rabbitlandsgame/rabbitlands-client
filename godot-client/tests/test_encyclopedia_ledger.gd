extends SceneTree

var checks := 0
var failures := 0
var view: EncyclopediaView
var window: Control
var saved: Array = []

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _init() -> void:
	run.call_deferred()

func data(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary

func run() -> void:
	root.get_node("Network").set_process(false)
	root.content_scale_size = Vector2i.ZERO
	root.size = Vector2i(1280, 720)
	var background := TextureRect.new()
	background.texture = load("res://assets/ui/start_screen/02-amberwood-lantern-path-poster.jpg")
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.modulate = Color(0.28, 0.28, 0.28)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var script: GDScript = load("res://src/ui/reference_window.gd")
	if script == null or not script.can_instantiate():
		expect(false, "reference window compiles")
		quit(1)
		return
	window = script.new()
	root.add_child(window)
	view = window.get("encyclopedia") as EncyclopediaView
	var recipes := ManufacturingCatalog.new()
	recipes.configure(data("res://data/manufacturing/recipes.json"))
	var spells := SpellCatalog.new()
	spells.configure(data("res://data/spells/catalog.json"))
	var atlas := ItemAtlas.new()
	atlas.configure(data("res://data/items/atlases.json"))
	view.configure_catalogues({"manufacturing": recipes, "spells": spells, "items": atlas,
		"harvesting": data("res://data/harvesting/catalog.json").get("resources", []),
		"books": data("res://data/knowledge/catalog.json").get("entries", []),
		"regions": data("res://data/maps/cartography.json").get("regions", []),
		"skills": ["attack", "defense", "harvesting", "alchemy", "magic", "potion", "summoning",
			"manufacturing", "crafting", "engineering", "tailoring", "ranging", "overall"]})
	view.bookmarks_changed.connect(func(marks: Array): saved = marks.duplicate(true))
	window.call("toggle_encyclopedia")
	await settle()
	expect(view.filtered_entries().size() == view.entry_count(), "all entries appear without filters")
	expect(view.entry_count() > recipes.count(), "guides and generated pages share the ledger")
	expect(view.ledger.columns == 6, "ledger exposes name, topic, type, level, book and bookmark")
	expect(view.search_edit.is_visible_in_tree(), "search is persistent")
	await capture("01-all-entries")
	view.search_edit.text = "iron "
	await create_timer(0.25).timeout
	expect(view.search_edit.text.ends_with(" "), "debounced search preserves the space before a second word")
	view.search_edit.text += "ore"
	await create_timer(0.25).timeout
	expect(not view.filtered_entries().is_empty(), "typing searches without submitting")
	view.show_index()
	view.call("_filter_changed", "type", "recipe")
	expect(view.filtered_entries().size() == recipes.output_count(), "one indexed row per output, across all topics")
	view.call("_filter_changed", "sort", "level")
	var previous := -1
	for entry: Dictionary in view.filtered_entries():
		expect(int(entry.level) >= previous, "numeric level sorting precedes pagination")
		previous = int(entry.level)
	view.entries_per_page = 4
	view.call("_filter_changed", "query", "steel smelting")
	expect(not view.filtered_entries().is_empty(), "multiword search indexes required books")
	for entry: Dictionary in view.filtered_entries():
		expect(str(entry.search).contains("steel") and str(entry.search).contains("smelting"), "all query words match")
	view.show_index()
	view.call("_filter_changed", "type", "recipe")
	view.call("_filter_changed", "book_filter", 1)
	for entry: Dictionary in view.filtered_entries():
		expect(not str(entry.book).is_empty(), "book-required filter excludes missing books")
	view.call("_filter_changed", "book_filter", 2)
	for entry: Dictionary in view.filtered_entries():
		expect(str(entry.book).is_empty(), "no-book filter is explicit")
	view.call("_filter_changed", "book_filter", 0)
	view.call("_filter_changed", "limit_level", true)
	view.call("_filter_changed", "max_level", 8)
	for entry: Dictionary in view.filtered_entries():
		expect(int(entry.level) >= 0 and int(entry.level) <= 8, "max-level filter uses actual metadata")
	view.call("_filter_changed", "topic", "alchemy")
	for entry: Dictionary in view.filtered_entries():
		expect(entry.category == "alchemy", "topic intersects the other filters")
	view.entries_per_page = 24
	view.show_index()
	view.search("  iRoN   oRe  ")
	var iron := {}
	for entry: Dictionary in view.filtered_entries():
		if entry.title == "Iron Bar": iron = entry
	expect(not iron.is_empty(), "ingredient names are searchable without title matches")
	view.show_index()
	view.open_category("alchemy", 0)
	view.call("_filter_changed", "type", "recipe")
	view.call("_filter_changed", "sort", "level")
	await settle()
	# Selection previews without losing the list or filters.
	var row: TreeItem = view.ledger.get_root().get_first_child()
	while row != null and not str(row.get_metadata(0)).ends_with(":iron-bar"):
		row = row.get_next()
	expect(row != null, "Iron Bar is present in the sorted page")
	if row != null:
		row.select(0)
		view.ledger.item_selected.emit()
		expect(view.ledger_column.visible and view.preview_title.text.contains("Iron Bar"), "selection updates the lower preview")
		expect(page_text(view.entry_page).contains("Recommended Alchemy level"), "preview distinguishes recommended level")
		expect(page_text(view.entry_page).contains("Iron Ore"), "preview contains recipe ingredients")
		await capture("02-alchemy-ledger")
		view.bookmark_entry_button.pressed.emit()
		expect(saved.size() == 1 and str(saved[0].key).ends_with(":iron-bar"), "visible bookmark control emits persistent page key")
		var state_key := view.page_key()
		view.full_article_button.pressed.emit()
		expect(not view.ledger_column.visible and view.page_key().ends_with(":iron-bar"), "open full article uses the reading area")
		await settle()
		var anchors: Container = view.entry_page.find_child("ArticleSections", true, false)
		expect(anchors != null and anchors.get_child(0).size.x > 20, "section links have visible clickable width")
		await capture("03-full-article")
		view.go_back()
		expect(view.page_key() == state_key and view.sort_filter.selected == 2, "Back restores filters, selection, page and sorting")
		view.show_index()
		view.bookmarks_button.pressed.emit()
		expect(view.filtered_entries().size() == 1, "bookmarks are browsable in the ledger")
		view.bookmark_entry_button.pressed.emit()
		expect(saved.is_empty() and view.filtered_entries().is_empty(), "removing the last bookmark shows an empty ledger")
	view.show_index()
	view.entries_per_page = 4
	view.open_category("alchemy", 0)
	var first := str(view.ledger.get_root().get_first_child().get_metadata(0))
	view.next_button.pressed.emit()
	expect(view.page_label.text.begins_with("Page 2/"), "pagination advances")
	expect(str(view.ledger.get_root().get_first_child().get_metadata(0)) != first, "next page changes rows")
	view.previous_button.pressed.emit()
	expect(str(view.ledger.get_root().get_first_child().get_metadata(0)) == first, "previous page returns to original rows")
	view.call("_filter_changed", "query", "zzzx-no-results")
	expect(view.filtered_entries().is_empty() and view.next_button.disabled and view.previous_button.disabled, "empty results disable paging")
	expect(view.entry_body.visible and not view.entry_page.visible, "empty results remove stale article preview")
	await capture("04-empty-results")
	view.show_index()
	view.entries_per_page = 24
	view.open_category("gathering", 0)
	view.call("_filter_changed", "type", "resource")
	var resources: Array = data("res://data/harvesting/catalog.json").resources
	expect(view.filtered_entries().size() == resources.size(), "one harvesting row per installed resource")
	for resource: Dictionary in resources:
		var matched := false
		for entry: Dictionary in view.filtered_entries():
			if str(entry.title) != str(resource.name): continue
			matched = true
			expect(int(entry.level) == int(resource.level) and str(entry.book) == str(resource.knowledge),
				"harvesting metadata matches the installed resource: " + str(resource.name))
		expect(matched, "resource is reachable: " + str(resource.name))
	view.call("_filter_changed", "book_filter", 1)
	expect(view.filtered_entries().is_empty(), "harvesting does not invent research prerequisites")
	view.call("_filter_changed", "book_filter", 2)
	expect(view.filtered_entries().size() == resources.size(), "no-book filter includes harvesting resources")
	view.call("_filter_changed", "limit_level", true)
	view.call("_filter_changed", "max_level", 0)
	var level_zero_titles: Array[String] = []
	for entry: Dictionary in view.filtered_entries():
		level_zero_titles.append(str(entry.title))
	level_zero_titles.sort()
	expect(level_zero_titles == ["Berries", "Sage", "Sunleaf"],
		"level-zero resources remain available through the recommended-level filter")
	view.call("_filter_changed", "max_level", 18)
	view.call("_filter_changed", "sort", "level")
	view.call("_filter_changed", "query", "iron ore")
	var harvest_row := view.ledger.get_root().get_first_child()
	while harvest_row != null and str(harvest_row.get_metadata(0)) != "entry:gathering:iron-ore":
		harvest_row = harvest_row.get_next()
	if harvest_row != null:
		harvest_row.select(0)
		view.ledger.item_selected.emit()
	expect(harvest_row != null and harvest_row.get_text(3) == "18" and harvest_row.get_text(4) == "None",
		"harvesting ledger shows the recommended level and explicit no-book requirement")
	expect(page_text(view.entry_page).contains("Recommended Harvesting level")
		and page_text(view.entry_page).contains("Knowledge needed")
		and page_text(view.entry_page).contains("Pickaxe"), "resource preview shows level, knowledge and tool")
	await capture("06-harvesting-ledger")
	var harvesting_key := view.page_key()
	view.full_article_button.pressed.emit()
	expect(view.page_key() == "entry:gathering:iron-ore", "resource full articles have stable page keys")
	var harvest_text := page_text(view.entry_page)
	expect(harvest_text.contains("not a minimum level") and harvest_text.contains("Iron Bar"),
		"resource article explains recommended levels and links to recipe uses")
	await capture("07-harvesting-article")
	view.go_back()
	expect(view.page_key() == harvesting_key, "Back restores harvesting filters and selection")
	view.search("iron bar")
	view.open_entry("alchemy", "iron-bar")
	var materials_link := false
	for pair: Array in (view.call("_entry", "alchemy", "iron-bar") as Dictionary).facts:
		if str(pair[0]) == "Required materials":
			materials_link = str(pair[1]).contains("entry:gathering:iron-ore")
	expect(materials_link, "recipe ingredient links resolve to harvesting resources")
	view.show_index()
	view.open_entry("perks", "perk-standard-bearer")
	expect(page_text(view.entry_page).contains("Tier"), "authored structured perk sections are preserved")
	expect(not view.matches("Mortar and Pestle").is_empty(), "tools are searchable")
	view.open_page_key("entry:world:world-weather-todo")
	expect(page_text(view.entry_page).contains("Night reduces"), "old bookmark IDs reach corrected material")
	expect(view.entry_page.find_child("ArticleSections", true, false) != null, "full articles keep section navigation")
	view.search("zzzx-no-results")
	view.open_page_key("cat:alchemy:0")
	expect(view.page_key() == "cat:alchemy:0", "legacy category bookmarks still resolve")
	expect(not view.filtered_entries().is_empty() and view.search_edit.text.is_empty(), "legacy category bookmarks clear unrelated search filters")
	view.call("_filter_changed", "sort", "level_desc")
	var browse_key := view.page_key()
	view.show_index()
	view.open_page_key(browse_key)
	expect(view.sort_filter.selected == 3, "filtered-view bookmarks round trip")
	root.size = Vector2i(1024, 720)
	await settle()
	var panel: PanelContainer = window.get("panel")
	expect(panel.position.x >= 0 and panel.position.x + panel.size.x <= 1024 - 96,
		"the dense window fits at 1024 width without covering the resource rail")
	expect(view.ledger.get_global_rect().end.x <= panel.get_global_rect().end.x, "ledger stays inside the window")
	await capture("05-ledger-1024")
	var tabs: TabContainer = window.get("tabs")
	tabs.current_tab = 0
	await settle()
	expect(panel.size.x <= 650, "other reference tabs retain compact sizing")
	print("encyclopedia ledger: %d checks, %d failures" % [checks, failures])
	window.queue_free()
	await process_frame
	quit(1 if failures else 0)

func settle() -> void:
	for i: int in range(5): await process_frame

func capture(name: String) -> void:
	await settle()
	var folder := "res://test-artifacts/encyclopedia-ledger"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	root.get_texture().get_image().save_png(folder.path_join(name + ".png"))

func page_text(node: Node) -> String:
	var text := ""
	if node is Label: text += node.text
	if node is Button: text += node.text
	if node is RichTextLabel: text += node.get_parsed_text()
	for child: Node in node.get_children(): text += " " + page_text(child)
	return text

