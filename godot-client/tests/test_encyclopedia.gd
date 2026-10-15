extends SceneTree
## Guards the encyclopedia and the move icon's attack preview.
##
## The encyclopedia is half written and half built. The written half is checked
## for being reachable; the built half is checked against the catalogue it was
## built from, so a page can never quietly claim a level, a cost or a material
## the recipe table does not state.
##
## The move icon is checked for the one rule that is easy to get wrong: Alt is
## a preview and not a mode, so it must never disturb an attack mode the player
## chose from the HUD.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	await process_frame
	var window: Control = main.get("reference_window") as Control
	var panel: PanelContainer = window.get_node("ReferenceWindow") as PanelContainer
	var view: EncyclopediaView = window.get("encyclopedia") as EncyclopediaView
	# The document renderer sits in the middle pane now, so it is reached
	# through the view rather than by a path off the root.
	var body: RichTextLabel = view.get("entry_body") as RichTextLabel
	var buttons: String = "GameView/Quickbar/QuickRows/Buttons/"
	var icon: Button = main.get_node(buttons + "EncyclopediaButton") as Button
	var walk: Button = main.get_node(buttons + "WalkButton") as Button
	var attack: Button = main.get_node(buttons + "AttackButton") as Button

	# The icon on the lower HUD, and Ctrl+E, both open it on its own page.
	_expect(not panel.visible, "the window starts closed")
	icon.pressed.emit()
	await process_frame
	_expect(panel.visible, "the HUD icon opens the window")
	_expect(bool(window.call("is_encyclopedia_open")),
		"and opens it on the encyclopedia rather than whichever tab was last used")
	_expect(icon.button_pressed, "so the icon is lit while it is showing")
	icon.pressed.emit()
	await process_frame
	_expect(not panel.visible, "and the icon closes it again")
	main.call("_input", _key(KEY_E, true))
	await process_frame
	_expect(bool(window.call("is_encyclopedia_open")), "Ctrl+E opens it")
	# Turning right is a bare E. It must not open the encyclopedia as well.
	main.call("_input", _key(KEY_E, true))
	await process_frame
	_expect(not panel.visible, "and Ctrl+E closes it")
	main.call("_input", _key(KEY_E, false))
	await process_frame
	_expect(not panel.visible,
		"a bare E turns the player and leaves the encyclopedia alone")
	main.call("_input", _key(KEY_E, true))
	await process_frame

	# The index: every category, each one a link.
	_expect(view.category_count() >= 12,
		"the index carries its categories: %d" % view.category_count())
	_expect(body.text.contains("[url=cat:alchemy:0]")
		and body.text.contains("[url=cat:books:0]"),
		"and every one of them is a link off the index page")
	_expect(body.get_parsed_text().contains("The Rabbit Lands Encyclopedia"),
		"the index is titled")

	# The built half says what the recipe table says, and nothing else.
	var catalogue: ManufacturingCatalog = main.get(
		"manufacturing_catalog") as ManufacturingCatalog
	_expect(catalogue.count() > 0, "the client has a recipe table to build from")
	var alchemy := 0
	for index: int in range(catalogue.count()):
		if str(catalogue.recipe(index).get("skill", "")) == "alchemy":
			alchemy += 1
	# Every alchemy recipe has a page of its own, and each page carries the
	# numbers and the materials that recipe states. Two ways of making the same
	# thing are two recipes and get two pages.
	var recipe_pages: Array[String] = []
	for id: String in view.entry_ids_in("alchemy"):
		view.open_entry("alchemy", id)
		recipe_pages.append(_page_text(view))
		# A built page says where it sits rather than ending in a link back:
		# the trail is at the top, and the category is on screen the whole
		# time in the browse pane beside it.
		_expect(_crumb_text(view).contains("Alchemy"),
			"%s says which category it sits in" % id)
	_expect(alchemy > 0 and recipe_pages.size() == alchemy,
		"one page per alchemy recipe: %d pages for %d recipes"
			% [recipe_pages.size(), alchemy])
	for index: int in range(catalogue.count()):
		var recipe: Dictionary = catalogue.recipe(index)
		if str(recipe.get("skill", "")) != "alchemy":
			continue
		# A fact is a label cell and a value cell now rather than one line of
		# "label: value", so each half is looked for on its own.
		var needles: Array[String] = [
			str(recipe.get("output", "")),
			"Recommended Alchemy level", str(int(recipe.get("level", 0))),
			"Alchemy experience given", str(int(recipe.get("experience", 0))),
			"Food subtracted", str(int(recipe.get("food", 0)))]
		var ingredients: Variant = recipe.get("ingredients", [])
		if ingredients is Array:
			for raw: Variant in ingredients as Array:
				needles.append(str((raw as Dictionary).get("name", "")))
		var found := false
		for page: String in recipe_pages:
			var complete := true
			for needle: String in needles:
				complete = complete and page.contains(needle)
			found = found or complete
		_expect(found, "a page states %s exactly as the recipe table has it"
			% str(recipe.get("output", "")))

	# A recipe that needs a book links to the book, and the book links back.
	# Neither side is invented: with no such recipe in the table, the book page
	# says so rather than listing something the client cannot make.
	var with_book := -1
	for index: int in range(catalogue.count()):
		if not str(catalogue.recipe(index).get("knowledge", "")).is_empty():
			with_book = index
			break
	if with_book >= 0:
		var recipe: Dictionary = catalogue.recipe(with_book)
		var book: String = str(recipe.get("knowledge", ""))
		var made: String = str(recipe.get("output", ""))
		view.open_page_key("entry:%s:%s" % [_category_for(
			str(recipe.get("skill", ""))), _slug(made)])
		_expect(_page_text(view).contains(book),
			"%s names the book it needs" % made)
		view.open_entry("books", _slug(book))
		_expect(_page_text(view).contains(made),
			"and %s lists %s among what it opens" % [book, made])
	else:
		var books: Array[String] = _books(main)
		if _expect(not books.is_empty(), "the client has a book list"):
			view.open_entry("books", _slug(books[0]))
			_expect(_page_text(view).contains(
				"Nothing the client has a recipe for"),
				"a book no recipe names says so rather than inventing one")

	# A category shorter than a page has no paging controls at all.
	view.entries_per_page = 24
	var longest: String = _longest_category(view)
	view.open_page_key("cat:%s:0" % longest)
	if view.entry_count_in(longest) <= view.entries_per_page:
		_expect(not view.page_label.visible and not view.next_button.visible,
			"a category that fits one page shows no paging controls")
	# Long categories are paged rather than run off the bottom of the window.
	# The page size is what the window holds, so the suite states its own.
	view.entries_per_page = 4
	view.open_page_key("cat:%s:0" % longest)
	var pages: int = ceili(float(view.entry_count_in(longest))
		/ float(view.entries_per_page))
	_expect(pages > 1, "%s is long enough to need paging: %d pages"
		% [longest, pages])
	_expect(view.page_label.visible and view.page_label.text == "Page 1/%d" % pages,
		"the page count is stated: %s" % view.page_label.text)
	_expect(view.previous_button.disabled and not view.next_button.disabled,
		"there is nothing before the first page and something after it")
	var first_page: String = body.get_parsed_text()
	view.next_button.pressed.emit()
	_expect(view.page_label.text == "Page 2/%d" % pages
		and body.get_parsed_text() != first_page,
		"and the forward control turns the page")
	view.previous_button.pressed.emit()
	_expect(body.get_parsed_text() == first_page, "the back control turns it back")
	view.open_page_key("cat:%s:%d" % [longest, pages + 5])
	_expect(view.page_label.text == "Page %d/%d" % [pages, pages],
		"and a page past the end lands on the last one: %s" % view.page_label.text)
	view.entries_per_page = 24

	# The page gets the window's width, not what the side panes leave over. The
	# panes used to grow to their longest link, which left a 640 wide window a
	# 218 wide page and wrapped a fact's value a letter to a line.
	view.open_entry("gathering", "harvesting")
	await process_frame
	await process_frame
	var content: Control = view.content_scroll
	_expect(content.size.x >= panel.size.x * 0.5,
		"a page keeps at least half the window: %.0f of %.0f"
			% [content.size.x, panel.size.x])
	_expect(panel.size.x <= 640.0,
		"and a long related title does not widen the window: %.0f" % panel.size.x)
	var value: Control = view.entry_page.find_child("Value", true, false) as Control
	_expect(value != null and value.size.x >= 120.0,
		"a fact's value has room for words: %.0f" % (value.size.x if value else 0.0))
	view.open_category("gathering", 0)
	await process_frame
	_expect(not view.aside_pane.visible,
		"a list page has no sections, so the pane beside it gives its width back")

	# Back walks the trail, whatever the trail was made of.
	view.reset_to_index()
	_expect(view.back_button.disabled, "there is nothing behind the front page")
	view.open_category("world", 0)
	view.open_entry("world", "time")
	_expect(view.page_key() == "entry:world:time", "an entry page is where it says")
	view.go_back()
	_expect(view.page_key() == "cat:world:0", "Back returns to the category")
	view.go_back()
	_expect(view.page_key() == "index", "and again to the index")

	# Search reads the written half as well as the built half.
	view.search("harvesting")
	_expect(view.matches("harvesting").size() >= 2,
		"search finds the pages that say it: %d" % view.matches("harvesting").size())
	_expect(body.get_parsed_text().contains("Harvesting"),
		"and the results name them")
	_expect(view.matches("a phrase no page contains").is_empty(),
		"and finds nothing when there is nothing")

	# The right-click menu, which is what the status line points at.
	_expect(view.status_line.text.contains("Right-click"),
		"the window says where the search and the bookmarks are")
	_expect(view.search_edit != null and view.search_edit.visible,
		"and the search field is on screen rather than waiting to be summoned")
	_expect(view.browse_list != null and view.browse_list.get_child_count() > 0,
		"the categories are on screen the whole time, not only on the index")
	view.call("_on_menu_id_pressed", 0)
	_expect(view.search_row.visible, "the menu's search entry brings it up")
	view.call("_on_search_submitted", "sigils")
	_expect(view.page_key() == "search:sigils", "and submitting it searches")

	# A bookmark is the player's own, and is kept in the client's own file.
	view.open_category("alchemy", 0)
	view.call("_on_menu_id_pressed", 1)
	await process_frame
	_expect(view.bookmarks().size() == 1
		and str((view.bookmarks()[0] as Dictionary).get("key", "")) == "cat:alchemy:0",
		"the page is bookmarked: %s" % str(view.bookmarks()))
	var config := ConfigFile.new()
	_expect(config.load(str(main.get("SETTINGS_PATH"))) == OK
		and (config.get_value("encyclopedia", "bookmarks", []) as Array).size() == 1,
		"and written to the client's settings file, not sent anywhere")
	view.call("_on_menu_id_pressed", 2)
	await process_frame
	_expect(view.bookmarks().is_empty(),
		"and removing it leaves the settings file as this suite found it")
	window.call("close")
	await process_frame

	# The move icon while Alt is held.
	main.call("_on_walk_button_pressed")
	main.call("_sync_hud_button_states", true)
	var walk_icon: Rect2 = _region(walk)
	var attack_icon: Rect2 = _region(attack)
	_expect(walk_icon != attack_icon and walk_icon != Rect2(),
		"the move and attack icons are different pictures")
	main.call("_input", _modifier(true))
	_expect(_region(walk) == attack_icon,
		"holding Alt turns the move icon into the attack icon")
	main.call("_input", _modifier(false))
	_expect(_region(walk) == walk_icon, "letting Alt go turns it back")

	# An attack mode chosen from the HUD is the player's decision, and Alt is
	# not allowed to look like what put it there or what took it away.
	main.call("_on_attack_button_pressed")
	main.call("_sync_hud_button_states", true)
	_expect(attack.button_pressed and str(main.get("_interaction_mode")) == "attack",
		"clicking the attack icon latches attack mode")
	main.call("_input", _modifier(true))
	_expect(attack.button_pressed and _region(walk) == walk_icon,
		"pressing Alt leaves it alone and leaves the move icon alone")
	main.call("_input", _modifier(false))
	_expect(attack.button_pressed and str(main.get("_interaction_mode")) == "attack",
		"and letting Alt go does not drop the player back into walk mode")
	main.call("_on_walk_button_pressed")
	main.call("_sync_hud_button_states", true)
	_expect(str(main.get("_interaction_mode")) == "walk",
		"the move icon is still how attack mode is left")

	# The move icon does what it is showing: while Alt is held it is the
	# attack icon, so pressing it is pressing the attack icon.
	main.call("_input", _modifier(true))
	main.call("_on_walk_button_pressed")
	_expect(str(main.get("_interaction_mode")) == "attack",
		"pressing the move icon while it shows attack chooses attack")
	main.call("_input", _modifier(false))
	main.call("_on_walk_button_pressed")
	main.call("_sync_hud_button_states", true)

	print("encyclopedia tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

func _longest_category(view: EncyclopediaView) -> String:
	var longest := ""
	var most := 0
	for id: String in view.category_ids():
		if view.entry_count_in(id) > most:
			most = view.entry_count_in(id)
			longest = id
	return longest

func _books(main: Control) -> Array[String]:
	var books: Array[String] = []
	for raw: Variant in main.get("knowledge_catalog") as Array:
		books.append(str(raw))
	return books

func _category_for(skill: String) -> String:
	return "potions" if skill == "potion" else skill

static func _slug(text: String) -> String:
	var slug := ""
	for unit: int in text.to_lower().to_utf8_buffer():
		if (unit >= 97 and unit <= 122) or (unit >= 48 and unit <= 57):
			slug += char(unit)
		elif not slug.ends_with("-"):
			slug += "-"
	return slug.trim_suffix("-")

static func _region(button: Button) -> Rect2:
	var texture: AtlasTexture = button.icon as AtlasTexture
	return texture.region if texture != null else Rect2()

## Everything a built page reads, labels and values run together.
func _page_text(view) -> String:
	return _gather(view.get("entry_page") as Node)

## The breadcrumb trail at the top of a built page.
func _crumb_text(view) -> String:
	var page: Node = view.get("entry_page") as Node
	if page == null:
		return ""
	return _gather(page.get_node_or_null("Breadcrumbs"))

func _gather(host: Node) -> String:
	if host == null:
		return ""
	var text: String = ""
	if host is Label:
		text += " " + (host as Label).text
	elif host is Button:
		text += " " + (host as Button).text
	elif host is RichTextLabel:
		text += " " + (host as RichTextLabel).get_parsed_text()
	for child: Node in host.get_children():
		text += _gather(child)
	return text

static func _key(keycode: Key, with_control: bool) -> InputEventKey:
	var event := InputEventKey.new()
	event.pressed = true
	event.physical_keycode = keycode
	event.keycode = keycode
	event.ctrl_pressed = with_control
	return event

static func _modifier(held: bool) -> InputEventKey:
	var event := InputEventKey.new()
	event.pressed = held
	event.physical_keycode = KEY_ALT
	event.keycode = KEY_ALT
	event.alt_pressed = held
	return event

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
