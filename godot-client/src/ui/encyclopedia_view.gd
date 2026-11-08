class_name EncyclopediaView
extends VBoxContainer
const TextColors := preload("res://src/ui/text_colors.gd")
## Searchable reference ledger. Filter and sort the entire catalogue before
## paging; select a row for a preview or open its full article. Existing page
## keys remain valid for bookmarks and links.
##
## Half of it is written and half of it is built. The written half is original
## Eloria reference text in `data/reference/encyclopedia.json`. The built half
## comes from the catalogues the client already loads to play the game - the
## recipe table, the spell catalogue, the book list, the region list and the
## skill table - so a recipe that changes in the data changes on its page too,
## and a page can never claim a recipe the client does not have.
##
## It is the Encyclopedia tab of the reference window, and it is also what the
## HUD's encyclopedia icon and Ctrl+E open.

const LINK_COLOUR := "#7fb4ff"
const HEADING_COLOUR := "#e8b552"
const NOTE_COLOUR := "#9fb3c8"
const FACT_COLOUR := "#8fd0c8"

## A page the player can be looking at. Bookmarks are these, written down.
const PAGE_INDEX := "index"

#: A glyph per category for the browse list. A category with none gets a dot,
#: which is a plainer answer than an icon that means something else.
## The glyphs below are what the shelf used to be labelled with, and four
## pairs of them collided: crafting and manufacturing were both a hammer,
## alchemy and potions both a still, skills and books both a ruled page, the
## world and its maps both a disc. Half the shelf named two things at once.
## They are kept as the fallback for a category `SubjectIcons` has nothing
## drawn for, which is better than borrowing another category's picture.
const CATEGORY_GLYPHS := {
	"world": "\u25c9", "skills": "\u25a4", "combat": "\u2694",
	"perks": "\u2606", "gathering": "\u2740", "commerce": "\u2696",
	"crafting": "\u2692", "manufacturing": "\u2692", "engineering": "\u2699",
	"tailoring": "\u2702", "alchemy": "\u2697", "potions": "\u2697",
	"summoning": "\u2728", "spells": "\u2726", "books": "\u25a4",
	"maps": "\u25c9", "commands": ">_",
}
## How far Back can walk. Long enough for any real trail through the pages,
## short enough that a session cannot grow it without bound.
const HISTORY_LIMIT := 64
## Compact type keeps the ledger readable beside the category rail.
const FONT_SIZE := 14
const TITLE_FONT_SIZE := 18
## The side panes are fixed rather than sized by what is in them. A link too
## long for its pane is cut short with its whole name in the tooltip, because
## a pane that widens for one long title narrows the page for every title.
const BROWSE_WIDTH := 132
const PANE_GAP := 6
const BROWSE_ICON_SIZE := 18
## The label column of a fact table. Labels wrap inside it rather than push
## the values over: a value squeezed to nothing wraps a letter to a line.
const FACT_LABEL_WIDTH := 164

signal bookmarks_changed(bookmarks: Array)

var navigation: HBoxContainer
var back_button: Button
var page_label: Label
var previous_button: Button
var next_button: Button
var index_button: Button
var search_row: HBoxContainer
var search_edit: LineEdit
var entry_body: RichTextLabel
var bookmarks_button: Button
var browse_list: VBoxContainer
var entry_page: VBoxContainer
var page_contents: Container
var related_list: VBoxContainer
var aside_pane: VBoxContainer
var content_scroll: ScrollContainer
#: Section heading by title, so "On this page" can scroll to one.
var _anchors: Dictionary = {}
var status_line: Label
var menu: PopupMenu

## How many links a category page holds before it is split in two. Two
## columns of twelve is what the panel shows without scrolling; it is a
## variable rather than a constant so a window of another size, and the suite
## that exercises the paging controls, can say otherwise.
var entries_per_page := 24

const ENTRY_TYPES := ["All types", "Guides", "Recipes", "Spells", "Books", "Maps", "Skills", "Perks"]
const TYPE_IDS := ["", "guide", "recipe", "spell", "book", "map", "skill", "perk"]
const SORT_IDS := ["name", "name_desc", "level", "level_desc", "topic", "book"]
var type_filter: OptionButton
var sort_filter: OptionButton
var book_filter: OptionButton
var level_filter: SpinBox
var level_enabled: CheckBox
var ledger: Tree
var result_label: Label
var ledger_column: VBoxContainer
var preview_header: HBoxContainer
var preview_title: Label
var full_article_button: Button
var bookmark_entry_button: Button
var split: VSplitContainer
var _syncing := false
var _result_entries: Array[Dictionary] = []
var _search_timer: Timer

var _document: Dictionary = {}
var _categories: Array[Dictionary] = []
var _by_id: Dictionary = {}
var _flat: Array[Dictionary] = []
var _catalogues: Dictionary = {}
var _bookmarks: Array[Dictionary] = []
var _books_category := ""
## Book name to the recipe pages it opens, filled while the recipe pages are
## built so both sides of the link agree on what a page is called.
var _recipes_by_book: Dictionary = {}
var _page: Dictionary = {"kind": PAGE_INDEX}
var _history: Array[Dictionary] = []

const SOURCE := "res://data/reference/encyclopedia.json"

func _ready() -> void:
	name = "Encyclopedia"
	_build()
	_load_document()
	_rebuild_content()
	reset_to_index()
	TextColors.events().changed.connect(_on_text_colors_changed)

## The catalogues the generated half is built from. They are configured after
## this window exists, so the content is built twice: once from the written
## half alone, and again the moment the client has read its data files.
func configure_catalogues(catalogues: Dictionary) -> void:
	_catalogues = catalogues
	_rebuild_content()
	reset_to_index()

func category_count() -> int:
	return _categories.size()

func category_titles() -> Array[String]:
	var titles: Array[String] = []
	for category: Dictionary in _categories:
		titles.append(str(category.get("title", "")))
	return titles

func category_ids() -> Array[String]:
	var ids: Array[String] = []
	for category: Dictionary in _categories:
		ids.append(str(category.get("id", "")))
	return ids

func entry_count_in(category_id: String) -> int:
	return (_category(category_id).get("entries", []) as Array).size()

func entry_ids_in(category_id: String) -> Array[String]:
	var ids: Array[String] = []
	for entry_value: Variant in _category(category_id).get("entries", []) as Array:
		ids.append(str((entry_value as Dictionary).get("id", "")))
	return ids

func entry_count() -> int:
	return _flat.size()

## Opens the nth entry across every category, in the order the index lists
## them. The reference window's flat list used to be the whole encyclopedia,
## and this is what is left of that view of it.
func show_entry_at(index: int) -> void:
	if index < 0 or index >= _flat.size():
		return
	var entry: Dictionary = _flat[index]
	open_entry(str(entry.get("category", "")), str(entry.get("id", "")))

func show_index() -> void:
	_navigate({"kind": PAGE_INDEX})

## Back to the front page with nothing behind it. Opening the window does this
## rather than show_index(), so Back is not lit on a page nobody came from.
func reset_to_index() -> void:
	_history.clear()
	_navigate({"kind": PAGE_INDEX}, false)

func open_category(category_id: String, page := 0) -> void:
	var state := _browse_state()
	state.merge({"kind": "category", "id": category_id, "topic": category_id,
		"page": page, "selected": ""}, true)
	_navigate(state)

func open_entry(category_id: String, entry_id: String) -> void:
	var state := _browse_state()
	state.merge({"kind": "entry", "category": category_id, "id": entry_id,
		"selected": "entry:%s:%s" % [category_id, entry_id]}, true)
	_navigate(state)

## Every entry whose title, summary or text contains the words asked for.
func search(query: String) -> void:
	_navigate({"kind": "search", "query": query, "topic": "", "page": 0})

func matches(query: String) -> Array[Dictionary]:
	var needle: String = query.strip_edges().to_lower()
	var found: Array[Dictionary] = []
	if needle.is_empty():
		return found
	for entry: Dictionary in _flat:
		if _matches_words(entry, needle):
			found.append(entry)
	return found

func page_key() -> String:
	if str(_page.get("kind", "")) == "browse":
		return "browse:" + JSON.stringify(_page)
	if str(_page.get("kind", "")) == "bookmarks":
		return "bookmarks"
	match str(_page.get("kind", PAGE_INDEX)):
		"category":
			return "cat:%s:%d" % [str(_page.get("id", "")), int(_page.get("page", 0))]
		"entry":
			return "entry:%s:%s" % [str(_page.get("category", "")),
				str(_page.get("id", ""))]
		"search":
			return "search:%s" % str(_page.get("query", ""))
	return PAGE_INDEX

func page_title() -> String:
	if str(_page.get("kind", "")) == "browse":
		return "Browse: %s" % str(_category(str(_page.get("topic", ""))).get("title", "All topics"))
	if str(_page.get("kind", "")) == "bookmarks": return "Bookmarks"
	match str(_page.get("kind", PAGE_INDEX)):
		"category":
			return str(_category(str(_page.get("id", ""))).get("title", "Index"))
		"entry":
			return str(_entry(str(_page.get("category", "")),
				str(_page.get("id", ""))).get("title", "Index"))
		"search":
			return "Search: %s" % str(_page.get("query", ""))
	return "Index"

func open_page_key(key: String) -> void:
	if key.begins_with("browse:"):
		var state: Variant = JSON.parse_string(key.substr(7))
		if state is Dictionary:
			_navigate(state)
	elif key == "bookmarks":
		_navigate({"kind": "bookmarks"})
	elif key.begins_with("cat:"):
		var parts: PackedStringArray = key.substr(4).split(":")
		_navigate({"kind": "category", "id": parts[0], "topic": parts[0],
			"page": int(parts[1]) if parts.size() > 1 else 0})
	elif key.begins_with("entry:"):
		var parts: PackedStringArray = key.substr(6).split(":")
		if parts.size() > 1:
			open_entry(parts[0], parts[1])
	elif key.begins_with("search:"):
		search(key.substr(7))
	else:
		show_index()

func bookmarks() -> Array:
	return _bookmarks.duplicate(true)

func set_bookmarks(stored: Array) -> void:
	_bookmarks.clear()
	for raw: Variant in stored:
		if raw is Dictionary:
			var bookmark: Dictionary = raw as Dictionary
			_bookmarks.append({"key": str(bookmark.get("key", PAGE_INDEX)),
				"label": str(bookmark.get("label", "Index"))})
	if ledger != null: _render()

func go_back() -> void:
	if _history.is_empty():
		return
	_page = _history.pop_back()
	_render()

func _navigate(page: Dictionary, remember := true) -> void:
	if remember:
		_history.append(_page.duplicate())
		if _history.size() > HISTORY_LIMIT:
			_history.remove_at(0)
	_page = page
	_render()

func _category(category_id: String) -> Dictionary:
	for category: Dictionary in _categories:
		if str(category.get("id", "")) == category_id:
			return category
	return {}

func _entry(category_id: String, entry_id: String) -> Dictionary:
	var value: Variant = _by_id.get("%s/%s" % [category_id, entry_id])
	return value as Dictionary if value is Dictionary else {}

# --- content -----------------------------------------------------------------

func _load_document() -> void:
	var file: FileAccess = FileAccess.open(SOURCE, FileAccess.READ)
	if file == null:
		push_warning("Encyclopedia source missing: " + SOURCE)
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if parsed is Dictionary:
		_document = parsed as Dictionary

func _rebuild_content() -> void:
	_categories.clear()
	_by_id.clear()
	_flat.clear()
	var raw_categories: Variant = _document.get("categories", [])
	if not raw_categories is Array:
		return
	# Which category a skill's recipes land in, and where the books live, both
	# have to be known before any page is built: a recipe page links to the
	# book it needs, and a book page links back to every recipe it opens.
	var skill_categories: Dictionary = {}
	_books_category = ""
	for raw_value: Variant in raw_categories as Array:
		if not raw_value is Dictionary:
			continue
		var generate: String = str((raw_value as Dictionary).get("generate", ""))
		if generate.begins_with("recipes:"):
			skill_categories[generate.substr(8)] = str(
				(raw_value as Dictionary).get("id", ""))
		elif generate == "books":
			_books_category = str((raw_value as Dictionary).get("id", ""))
	var recipes_by_skill: Dictionary = _recipe_entries(skill_categories)
	for raw_value: Variant in raw_categories as Array:
		if not raw_value is Dictionary:
			continue
		var raw: Dictionary = raw_value as Dictionary
		var category_id: String = str(raw.get("id", ""))
		var entries: Array[Dictionary] = []
		var authored: Variant = raw.get("entries", [])
		if authored is Array:
			for entry_value: Variant in authored as Array:
				if entry_value is Dictionary:
					entries.append(_written_entry(entry_value as Dictionary, category_id))
		var generate: String = str(raw.get("generate", ""))
		if generate.begins_with("recipes:"):
			var generated: Variant = recipes_by_skill.get(generate.substr(8), [])
			if generated is Array:
				for entry_value: Variant in generated as Array:
					entries.append(entry_value as Dictionary)
		elif generate == "spells":
			entries.append_array(_spell_entries(category_id))
		elif generate == "books":
			entries.append_array(_book_entries(category_id))
		elif generate == "maps":
			entries.append_array(_map_entries(category_id))
		elif generate == "skills":
			entries.append_array(_skill_entries(category_id))
		_categories.append({"id": category_id, "title": str(raw.get("title", "")),
			"summary": str(raw.get("summary", "")), "intro": str(raw.get("intro", "")),
			"entries": entries})
		for entry: Dictionary in entries:
			_by_id["%s/%s" % [category_id, str(entry.get("id", ""))]] = entry
			_flat.append(entry)

	for entry: Dictionary in _flat:
		if str(entry.get("type", "")) == "recipe":
			for pair: Array in entry.get("facts", []) as Array:
				if str(pair[0]) == "Required materials":
					pair[1] = _ingredient_lines(entry.get("materials", []))
				elif str(pair[0]) == "Tools required to have":
					pair[1] = _ingredient_lines(entry.get("tools", []))
		var searchable := "%s %s %s %s %s" % [entry.get("title", ""),
			entry.get("summary", ""), entry.get("body", ""),
			_category(str(entry.get("category", ""))).get("title", ""), entry.get("book", "")]
		for pair: Array in entry.get("facts", []) as Array:
			searchable += " %s %s" % [pair[0], _plain_text(str(pair[1]))]
		for section: Dictionary in entry.get("sections", []) as Array:
			searchable += " %s %s" % [section.get("title", ""), section.get("text", "")]
			for pair: Array in section.get("rows", []) as Array:
				searchable += " %s %s" % [pair[0], _plain_text(str(pair[1]))]
		entry["search"] = searchable.to_lower()

func _written_entry(raw: Dictionary, category_id: String) -> Dictionary:
	var body: String = str(raw.get("body", ""))
	var facts: Array[Array] = []
	var raw_facts: Variant = raw.get("facts", [])
	if raw_facts is Array:
		for fact_value: Variant in raw_facts as Array:
			if fact_value is Array and (fact_value as Array).size() >= 2:
				facts.append([str((fact_value as Array)[0]),
					_escape(str((fact_value as Array)[1]))])
	var entry := _entry_record(str(raw.get("id", "")), str(raw.get("title", "")),
		str(raw.get("summary", "")), body, facts, {}, category_id)
	entry["type"] = "perk" if category_id == "perks" else "guide"
	entry["related"] = (raw.get("related", []) as Array).duplicate(true)
	var sections: Array[Dictionary] = []
	for raw_section: Variant in raw.get("sections", []) as Array:
		var section: Dictionary = (raw_section as Dictionary).duplicate(true)
		if str(section.get("kind", "")) == "facts":
			var rows: Array = []
			for pair: Variant in section.get("rows", []) as Array:
				if pair is Array and pair.size() >= 2:
					rows.append([str(pair[0]), _escape(str(pair[1]))])
			section["rows"] = rows
		sections.append(section)
	entry["sections"] = sections
	return entry

func _entry_record(id: String, title: String, summary: String, body: String,
		facts: Array[Array], image: Dictionary, category_id: String) -> Dictionary:
	return {"id": id, "title": title, "summary": summary, "body": body,
		"facts": facts, "image": image, "category": category_id,
		"type": "guide", "level": -1, "book": "",
		"search": ("%s %s %s" % [title, summary, body]).to_lower()}

## One entry per recipe, grouped by the skill that mixes it. The fields are the
## recipe's own: what it takes, what it wants you to have read, and what it
## gives back.
func _recipe_entries(skill_categories: Dictionary) -> Dictionary:
	var by_skill: Dictionary = {}
	_recipes_by_book.clear()
	var catalogue: ManufacturingCatalog = _catalogues.get("manufacturing") as ManufacturingCatalog
	if catalogue == null:
		return by_skill
	# The table can hold two ways of making the same thing. Both are real
	# recipes and both get a page, so a name used twice is qualified by what
	# actually differs: the level, then the first material, then the recipe's
	# own place in the table. Two pages may not answer to one name.
	var repeated: Dictionary = {}
	for index: int in range(catalogue.count()):
		for key: String in _naming_keys(catalogue.recipe(index)):
			repeated[key] = int(repeated.get(key, 0)) + 1
	var used: Dictionary = {}
	for index: int in range(catalogue.count()):
		var recipe: Dictionary = catalogue.recipe(index)
		var skill: String = str(recipe.get("skill", ""))
		var category_id: String = str(skill_categories.get(skill, ""))
		if category_id.is_empty():
			continue
		var output: String = str(recipe.get("output", ""))
		var readable_skill: String = skill.capitalize()
		var title: String = _recipe_title(recipe, repeated)
		var entry_id: String = _slug(title)
		if used.has("%s/%s" % [category_id, entry_id]):
			entry_id = "%s-%d" % [entry_id, int(recipe.get("id", index))]
		used["%s/%s" % [category_id, entry_id]] = true
		var facts: Array[Array] = []
		var materials: String = _ingredient_lines(recipe.get("ingredients", []))
		facts.append(["Required materials",
			materials if not materials.is_empty() else "None"])
		var tools: String = _ingredient_lines(recipe.get("tools", []))
		if not tools.is_empty():
			facts.append(["Tools required to have", tools])
		var book: String = str(recipe.get("knowledge", ""))
		if not book.is_empty():
			facts.append(["Knowledge needed", _link("entry:%s:%s" % [
				_books_category, _slug(book)], book)])
		var animal_nexus := int(recipe.get("animalNexus", 0))
		if animal_nexus > 0:
			facts.append(["Animal nexus required", str(animal_nexus)])
		facts.append(["Recommended %s level" % readable_skill,
			str(int(recipe.get("level", 0)))])
		facts.append(["%s experience given" % readable_skill,
			str(int(recipe.get("experience", 0)))])
		facts.append(["Food subtracted", str(int(recipe.get("food", 0)))])
		var mana: int = int(recipe.get("mana", 0))
		if mana > 0:
			facts.append(["Ether required", str(mana)])
		var body: String = ("Mixed with the %s skill. The listed level is recommended,"
			+ " not a guaranteed success threshold. Attempts can fail; a critical"
			+ " failure can consume materials. A rare result stops a running batch."
			+ " Required knowledge, tools, food and"
			+ " any nexus requirements are checked by the server. Near a storage"
			+ " keeper, the mixing window can draw materials from storage; tools"
			+ " still need to be carried or equipped.") % readable_skill
		var image: Dictionary = _item_image(int(recipe.get("outputImageId", -1)))
		var entry: Dictionary = _entry_record(entry_id, title, "", body, facts,
			image, category_id)
		entry.merge({"type": "recipe", "level": int(recipe.get("level", 0)),
			"book": book, "output": output, "materials": recipe.get("ingredients", []),
			"tools": recipe.get("tools", [])}, true)
		if not by_skill.has(skill):
			by_skill[skill] = []
		(by_skill[skill] as Array).append(entry)
		if not book.is_empty():
			if not _recipes_by_book.has(book):
				_recipes_by_book[book] = []
			(_recipes_by_book[book] as Array).append({"category": category_id,
				"id": entry_id, "title": title})
	for skill: Variant in by_skill:
		(by_skill[skill] as Array).sort_custom(_title_before)
	return by_skill

## The three names a recipe could be filed under, narrowest last. Counting all
## three in one pass is what lets the next pass tell which of them is enough.
func _naming_keys(recipe: Dictionary) -> Array[String]:
	var output: String = str(recipe.get("output", ""))
	var with_level: String = "%s|%d" % [output, int(recipe.get("level", 0))]
	return [output, with_level,
		"%s|%s" % [with_level, _first_ingredient(recipe)]]

func _recipe_title(recipe: Dictionary, repeated: Dictionary) -> String:
	var keys: Array[String] = _naming_keys(recipe)
	if int(repeated.get(keys[0], 0)) <= 1:
		return keys[0]
	var qualifiers: Array[String] = ["level %d" % int(recipe.get("level", 0))]
	if int(repeated.get(keys[1], 0)) > 1:
		var first: String = _first_ingredient(recipe)
		qualifiers.append("from %s" % first if not first.is_empty()
			else "recipe %d" % int(recipe.get("id", 0)))
		if int(repeated.get(keys[2], 0)) > 1:
			qualifiers.append("recipe %d" % int(recipe.get("id", 0)))
	return "%s (%s)" % [keys[0], ", ".join(qualifiers)]

func _first_ingredient(recipe: Dictionary) -> String:
	var ingredients: Variant = recipe.get("ingredients", [])
	if ingredients is Array and not (ingredients as Array).is_empty():
		var first: Variant = (ingredients as Array)[0]
		if first is Dictionary:
			return str((first as Dictionary).get("name", ""))
	return ""

func _spell_entries(category_id: String) -> Array[Dictionary]:
	var entries: Array[Dictionary] = []
	var catalogue: SpellCatalog = _catalogues.get("spells") as SpellCatalog
	if catalogue == null:
		return entries
	for spell_id: int in catalogue.spell_ids():
		var spell: Dictionary = catalogue.spell(spell_id)
		var title: String = str(spell.get("name", ""))
		if title.is_empty():
			continue
		var facts: Array[Array] = []
		var tome: String = catalogue.knowledge_for(spell_id)
		facts.append(["Learned from", tome if not tome.is_empty()
			else "Known to every mage"])
		facts.append(["Ether at Power 1", str(int(spell.get("mana", 0)))])
		facts.append(["Magic nexus required", str(int(spell.get("nexus", 0)))])
		facts.append(["Unlock Magic level", str(int(spell.get("level", 0)))])
		facts.append(["Recommended Magic level", str(int(spell.get("recommended_level", spell.get("level", 0))))])
		var effect: String = str(spell.get("effect", ""))
		if not effect.is_empty():
			facts.append(["Targeting", str(spell.get("scope", "self")).capitalize()])
			facts.append(["Power", "1–10; increases strength, duration and reagent costs"])
			facts.append(["Potency", "No random fizzles. Average reaches 100% at the recommended level and 200% at twice it; utility outcomes stay fixed."])
			var damage_type := str(spell.get("damage_type", ""))
			if not damage_type.is_empty(): facts.append(["Damage type", damage_type.capitalize()])
			if spell.get("scope") == "allies": facts.append(["Recipients", "You and party or guild members within four tiles"])
			if spell.get("scope") == "burst": facts.append(["Area", "Four-tile radius; select a location within 15 tiles"])
		var reagents: String = _reagent_lines(spell.get("reagents", []))
		facts.append(["Reagents", reagents if not reagents.is_empty() else "None"])
		var body: String = ("%s\n\nYou must have read this family's tome before"
			+ " it can be cast; Heal, Fire Bolt and Restore Ether need none. The"
			+ " server checks the knowledge, the level and the reagents, in that"
			+ " order.") % str(spell.get("description", ""))
		var entry := _entry_record(_slug(title), title, "", body, facts,
			catalogue.icon_source(spell_id), category_id)
		entry.merge({"type": "spell", "level": int(spell.get("level", 0)), "book": tome}, true)
		entries.append(entry)
	entries.sort_custom(_title_before)
	return entries

## A book is a name and a lock. What makes its page worth reading is the list
## of recipes the lock opens, which is read back out of the recipe table.
func _book_entries(category_id: String) -> Array[Dictionary]:
	var entries: Array[Dictionary] = []
	var books_value: Variant = _catalogues.get("books", [])
	if not books_value is Array:
		return entries
	for raw_name: Variant in books_value as Array:
		var title: String = str(raw_name)
		if title.is_empty():
			continue
		var facts: Array[Array] = []
		var links: Array[String] = []
		var rows_value: Variant = _recipes_by_book.get(title, [])
		if rows_value is Array:
			for row_value: Variant in rows_value as Array:
				var row: Dictionary = row_value as Dictionary
				links.append(_link("entry:%s:%s" % [str(row.get("category", "")),
					str(row.get("id", ""))], str(row.get("title", ""))))
		facts.append(["Opens", "\n".join(links) if not links.is_empty()
			else "Nothing the client has a recipe for"])
		var spell_catalogue: SpellCatalog = _catalogues.get("spells") as SpellCatalog
		if spell_catalogue != null:
			for spell_id: int in spell_catalogue.spell_ids():
				if spell_catalogue.knowledge_for(spell_id) == title:
					var spell_name := str(spell_catalogue.spell(spell_id).get("name", ""))
					links.append(_link("entry:spells:%s" % _slug(spell_name), spell_name))
		facts[0][1] = "\n".join(links) if not links.is_empty() else "No recipe or spell in the loaded catalogues names this knowledge."
		var body: String = ("Knowledge is recorded by the server after research completes."
			+ " The Knowledge window shows what you have learned and current research."
			+ " Spell tomes unlock their spell family. Repeatable experience books"
			+ " are a separate kind of book; they are not permanent recipe unlocks.")
		var entry := _entry_record(_slug(title), title, "", body, facts, {}, category_id)
		entry["type"] = "book"
		entries.append(entry)
	return entries

func _map_entries(category_id: String) -> Array[Dictionary]:
	var entries: Array[Dictionary] = []
	var regions_value: Variant = _catalogues.get("regions", [])
	if not regions_value is Array:
		return entries
	for region_value: Variant in regions_value as Array:
		if not region_value is Dictionary:
			continue
		var region: Dictionary = region_value as Dictionary
		var title: String = str(region.get("name", ""))
		if title.is_empty():
			continue
		var facts: Array[Array] = [["Region", title]]
		var body: String = "A region of Nymara. Use the map window to browse its terrain and map connections. Accessible destinations depend on the current server world."
		var entry := _entry_record(_slug(title), title, "", body, facts, {}, category_id)
		entry["type"] = "map"
		entries.append(entry)
	return entries

func _skill_entries(category_id: String) -> Array[Dictionary]:
	var entries: Array[Dictionary] = []
	var skills_value: Variant = _catalogues.get("skills", [])
	if not skills_value is Array:
		return entries
	var notes_value: Variant = _document.get("skillNotes", {})
	var notes: Dictionary = notes_value as Dictionary if notes_value is Dictionary else {}
	for raw_skill: Variant in skills_value as Array:
		var skill: String = str(raw_skill)
		if skill.is_empty():
			continue
		var body: String = str(notes.get(skill, ""))
		if body.is_empty():
			body = "The server keeps a level and an experience total for this."
		var facts: Array[Array] = [["Skill", skill.capitalize()]]
		var entry := _entry_record(_slug(skill), skill.capitalize(), "", body, facts, {}, category_id)
		entry["type"] = "skill"
		entries.append(entry)
	return entries

func _ingredient_lines(value: Variant) -> String:
	if not value is Array:
		return ""
	var lines: Array[String] = []
	for raw: Variant in value as Array:
		if not raw is Dictionary:
			continue
		var ingredient: Dictionary = raw as Dictionary
		var image: Dictionary = _item_image(int(ingredient.get("imageId", -1)))
		var title := str(ingredient.get("name", ""))
		var label := _escape(title)
		for target: Dictionary in _flat:
			if str(target.get("output", "")) == title:
				label = _link("entry:%s:%s" % [target.category, target.id], title)
				break
		lines.append("%s%d %s" % [_image_tag(image, 22),
			maxi(1, int(ingredient.get("quantity", 1))), label])
	return "\n".join(lines)

func _reagent_lines(value: Variant) -> String:
	if not value is Array:
		return ""
	var lines: Array[String] = []
	for raw: Variant in value as Array:
		if not raw is Dictionary:
			continue
		var reagent: Dictionary = raw as Dictionary
		var icon: String = _image_tag(_item_image(int(reagent.get("image_id", -1))), 22)
		var reagent_label: String = _escape(SpellCatalog.reagent_name(reagent))
		var quantity: int = int(reagent.get("quantity", 1))
		# The page states a Power 1 cast; an anchor listed at 0 starts at Power 4.
		lines.append("%s%s from Power 4" % [icon, reagent_label] if quantity == 0
			else "%s%d %s" % [icon, quantity, reagent_label])
	return "\n".join(lines)

func _item_image(image_id: int) -> Dictionary:
	var atlas: ItemAtlas = _catalogues.get("items") as ItemAtlas
	if atlas == null:
		return {}
	return atlas.icon_source(image_id)

func _title_before(first: Dictionary, second: Dictionary) -> bool:
	return str(first.get("title", "")).naturalnocasecmp_to(
		str(second.get("title", ""))) < 0

## A page name that survives being written into a link and into the settings
## file: lower case, letters and digits, everything else a single dash.
static func _slug(text: String) -> String:
	var slug := ""
	for unit: int in text.to_lower().to_utf8_buffer():
		if (unit >= 97 and unit <= 122) or (unit >= 48 and unit <= 57):
			slug += char(unit)
		elif not slug.ends_with("-"):
			slug += "-"
	return slug.trim_suffix("-")

# --- rendering ---------------------------------------------------------------

func _render() -> void:
	if ledger == null:
		return
	_syncing = true
	var state := _browse_state()
	var kind := str(_page.get("kind", PAGE_INDEX))
	var full := kind == "entry"
	search_edit.text = str(state.get("query", ""))
	type_filter.select(maxi(0, TYPE_IDS.find(str(state.get("type", "")))))
	sort_filter.select(maxi(0, SORT_IDS.find(str(state.get("sort", "name")))))
	book_filter.select(int(state.get("book_filter", 0)))
	level_enabled.button_pressed = bool(state.get("limit_level", false))
	level_filter.value = int(state.get("max_level", 100))
	level_filter.editable = level_enabled.button_pressed
	ledger_column.visible = not full
	_sync_browse()
	_result_entries = filtered_entries()
	var pages := maxi(1, ceili(float(_result_entries.size()) / maxi(1, entries_per_page)))
	var page_number := clampi(int(state.get("page", 0)), 0, pages - 1)
	_page["page"] = page_number
	var first := page_number * maxi(1, entries_per_page)
	var last := mini(first + maxi(1, entries_per_page), _result_entries.size())
	result_label.text = "%d results · %d–%d shown · %d total entries" % [
		_result_entries.size(), first + 1 if last > first else 0, last, _flat.size()]
	ledger.clear()
	var root_item := ledger.create_item()
	var selected := str(_page.get("selected", ""))
	var visible_entries := _result_entries.slice(first, last)
	var has_selected := false
	for entry: Dictionary in visible_entries:
		if _key_for(entry) == selected:
			has_selected = true
	if not full and not has_selected:
		selected = _key_for(visible_entries[0]) if not visible_entries.is_empty() else ""
		_page["selected"] = selected
	for entry: Dictionary in visible_entries:
		var row := ledger.create_item(root_item)
		var key := _key_for(entry)
		row.set_metadata(0, key)
		row.set_text(0, str(entry.title))
		row.set_text(1, str(_category(str(entry.category)).get("title", "")))
		row.set_text(2, str(entry.get("type", "guide")).capitalize())
		row.set_text(3, str(entry.level) if int(entry.get("level", -1)) >= 0 else "—")
		var book := str(entry.get("book", ""))
		row.set_text(4, book if not book.is_empty() else ("None" if str(entry.get("type", "")) in ["recipe", "spell"] else "—"))
		row.set_cell_mode(5, TreeItem.CELL_MODE_CHECK)
		row.set_editable(5, true)
		row.set_checked(5, _bookmark_index(key) >= 0)
		row.set_tooltip_text(5, "Keep this article in bookmarks")
		for column: int in range(5):
			row.set_tooltip_text(column, row.get_text(column))
			row.set_custom_color(column, TextColors.color("encyclopedia_text"))
		var source: Dictionary = entry.get("image", {})
		if not source.is_empty():
			var texture := AtlasTexture.new()
			texture.atlas = load(str(source.get("path", ""))) as Texture2D
			texture.region = source.get("region", Rect2())
			row.set_icon(0, texture)
			row.set_icon_max_width(0, 20)
		if key == selected:
			row.select(0)
	page_label.text = "Page %d/%d" % [page_number + 1, pages]
	page_label.visible = not full
	previous_button.visible = not full
	next_button.visible = not full
	previous_button.disabled = page_number == 0
	next_button.disabled = page_number >= pages - 1
	back_button.disabled = _history.is_empty()
	bookmarks_button.button_pressed = kind == "bookmarks"
	index_button.disabled = kind == PAGE_INDEX and state.get("query", "") == "" and state.get("topic", "") == ""
	status_line.text = "Search and filters cover all entries · Select to preview · Double-click to read"
	_render_selection(selected, full)
	_syncing = false

func _render_selection(key: String, full := false) -> void:
	var parts := key.split(":")
	var entry := _entry(parts[1], parts[2]) if parts.size() >= 3 else {}
	entry_page.visible = not entry.is_empty()
	entry_body.visible = entry.is_empty()
	preview_header.visible = not entry.is_empty()
	full_article_button.visible = not full
	aside_pane.hide()
	if entry.is_empty():
		_clear(entry_page)
		entry_body.text = "[b]No matching entries.[/b]\nClear filters or try fewer search words."
		return
	preview_title.text = "%s · %s" % [entry.title, str(entry.get("type", "guide")).capitalize()]
	bookmark_entry_button.text = "★ Saved" if _bookmark_index(key) >= 0 else "☆ Bookmark"
	if full:
		_render_entry_page(str(entry.category), str(entry.id))
	else:
		_render_entry_preview(entry)
	content_scroll.scroll_vertical = 0

func _render_entry_preview(entry: Dictionary) -> void:
	_clear(entry_page)
	var rows: Array = []
	for pair: Array in entry.get("facts", []) as Array:
		var label := str(pair[0])
		if label in ["Required materials", "Tools required to have", "Knowledge needed",
				"Learned from", "Reagents", "Magic nexus required", "Animal nexus required"] or label.begins_with("Recommended "):
			rows.append(pair)
	if not rows.is_empty():
		entry_page.add_child(_fact_table(rows))
	else:
		var body := str(entry.get("body", entry.get("summary", "")))
		entry_page.add_child(_shell_body(body.get_slice("\n\n", 0)))
	var related := HFlowContainer.new()
	related.name = "RelatedPreview"
	related.add_child(_shell_heading("Related:"))
	for target: Dictionary in _related_to(str(entry.category), entry):
		var link := Button.new()
		link.text = str(target.title)
		link.flat = true
		TextColors.bind(link, "encyclopedia_link")
		link.pressed.connect(open_entry.bind(str(target.category), str(target.id)))
		related.add_child(link)
	entry_page.add_child(related)


func _link(meta: String, text: String) -> String:
	return "[url=%s][color=%s]%s[/color][/url]" % [meta, _text_color("encyclopedia_link"), _escape(text)]

## bbcode takes an atlas as a path and a rectangle, never as a texture, which
## is why ItemAtlas and SpellCatalog hand out their sources as well as their
## AtlasTextures.
static func _image_tag(source: Dictionary, size: int) -> String:
	if source.is_empty():
		return ""
	var region: Rect2 = source.get("region", Rect2()) as Rect2
	return "[img region=%d,%d,%d,%d width=%d height=%d]%s[/img] " % [
		int(region.position.x), int(region.position.y),
		int(region.size.x), int(region.size.y), size, size,
		str(source.get("path", ""))]

static func _escape(text: String) -> String:
	return text.replace("[", "[lb]")

# --- the window --------------------------------------------------------------

## Dense catalogue above a resizable preview, with topic navigation beside it.
func _build() -> void:
	var compact := Theme.new()
	compact.default_font_size = FONT_SIZE
	compact.set_stylebox("panel", "Tree", _ledger_style(Color("345052"), Color("081314")))
	compact.set_stylebox("selected", "Tree", _ledger_style(Color("83ced9"), Color("143137")))
	compact.set_stylebox("selected_focus", "Tree", _ledger_style(Color("83ced9"), Color("143137")))
	compact.set_constant("v_separation", "Tree", 3)
	compact.set_constant("h_separation", "Tree", 4)
	for kind: String in ["Button", "OptionButton"]:
		compact.set_stylebox("normal", kind, _ledger_style(Color("655331"), Color("0b191b")))
		compact.set_stylebox("hover", kind, _ledger_style(Color("83ced9"), Color("173039")))
		compact.set_stylebox("pressed", kind, _ledger_style(Color("83ced9"), Color("143137")))
		compact.set_stylebox("focus", kind, _ledger_style(Color("83ced9"), Color(0, 0, 0, 0)))
	compact.set_stylebox("normal", "LineEdit", _ledger_style(Color("655331"), Color("030d10")))
	compact.set_stylebox("focus", "LineEdit", _ledger_style(Color("83ced9"), Color("030d10")))
	theme = compact
	add_theme_constant_override("separation", 4)
	navigation = HBoxContainer.new()
	navigation.name = "EncyclopediaNavigation"
	add_child(navigation)
	search_row = navigation
	back_button = _navigation_button("EncyclopediaBack", "← Back", "Return to the previous view")
	back_button.pressed.connect(go_back)
	search_edit = LineEdit.new()
	search_edit.name = "EncyclopediaSearch"
	search_edit.placeholder_text = "Search the entire encyclopedia…"
	search_edit.tooltip_text = "Search titles, descriptions, materials, tools, books and facts across all entries"
	search_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search_edit.clear_button_enabled = true
	navigation.add_child(search_edit)
	_search_timer = Timer.new()
	_search_timer.one_shot = true
	_search_timer.wait_time = 0.18
	add_child(_search_timer)
	_search_timer.timeout.connect(_apply_search_text)
	search_edit.text_changed.connect(func(_text: String):
		if not _syncing: _search_timer.start())
	search_edit.text_submitted.connect(_on_search_submitted)
	index_button = _navigation_button("EncyclopediaIndex", "All entries", "Clear filters and browse everything")
	index_button.pressed.connect(show_index)
	bookmarks_button = _navigation_button("EncyclopediaBookmarks", "☆ Bookmarks", "Browse saved articles; right-click for all saved pages")
	bookmarks_button.toggle_mode = true
	bookmarks_button.pressed.connect(_on_bookmarks_pressed)
	bookmarks_button.gui_input.connect(func(event: InputEvent):
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			open_menu(get_global_mouse_position()))
	var filters := HBoxContainer.new()
	filters.name = "Filters"
	add_child(filters)
	type_filter = _option(filters, "TypeFilter", ENTRY_TYPES)
	type_filter.item_selected.connect(func(index: int): _filter_changed("type", TYPE_IDS[index]))
	sort_filter = _option(filters, "SortFilter", ["Name A–Z", "Name Z–A", "Level ↑", "Level ↓", "Topic", "Book"])
	sort_filter.item_selected.connect(func(index: int): _filter_changed("sort", SORT_IDS[index]))
	book_filter = _option(filters, "BookFilter", ["Any book requirement", "Book required", "No book required"])
	book_filter.tooltip_text = "Applies to recipes and spells with explicit knowledge requirements"
	book_filter.item_selected.connect(func(index: int): _filter_changed("book_filter", index))
	level_enabled = CheckBox.new()
	level_enabled.name = "LimitLevel"
	level_enabled.text = "Max level"
	level_enabled.tooltip_text = "Recipe recommended level or spell unlock level; entries without levels are excluded"
	filters.add_child(level_enabled)
	level_enabled.toggled.connect(func(enabled: bool): _filter_changed("limit_level", enabled))
	level_filter = SpinBox.new()
	level_filter.name = "MaxLevel"
	level_filter.min_value = 0
	level_filter.max_value = 1000
	level_filter.value = 100
	level_filter.custom_minimum_size.x = 76
	filters.add_child(level_filter)
	level_filter.value_changed.connect(func(value: float): _filter_changed("max_level", int(value)))
	var clear := Button.new()
	clear.name = "ClearFilters"
	clear.text = "Clear filters"
	clear.pressed.connect(show_index)
	filters.add_child(clear)
	var panes := HBoxContainer.new()
	panes.name = "Panes"
	panes.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(panes)
	var browse_column := VBoxContainer.new()
	browse_column.name = "Browse"
	browse_column.custom_minimum_size.x = BROWSE_WIDTH
	panes.add_child(browse_column)
	var browse_scroll := ScrollContainer.new()
	browse_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	browse_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	browse_column.add_child(browse_scroll)
	browse_list = VBoxContainer.new()
	browse_list.name = "BrowseList"
	browse_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	browse_scroll.add_child(browse_list)
	split = VSplitContainer.new()
	split.name = "LedgerAndPreview"
	split.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panes.add_child(split)
	ledger_column = VBoxContainer.new()
	ledger_column.name = "Ledger"
	ledger_column.custom_minimum_size.y = 170
	ledger_column.size_flags_vertical = Control.SIZE_EXPAND_FILL
	ledger_column.size_flags_stretch_ratio = 1.8
	split.add_child(ledger_column)
	ledger = Tree.new()
	ledger.name = "EntryLedger"
	ledger.columns = 6
	ledger.hide_root = true
	ledger.select_mode = Tree.SELECT_ROW
	ledger.column_titles_visible = true
	ledger.size_flags_vertical = Control.SIZE_EXPAND_FILL
	ledger.custom_minimum_size.y = 140
	ledger.set_column_title(0, "Entry")
	ledger.set_column_title(1, "Topic")
	ledger.set_column_title(2, "Type")
	ledger.set_column_title(3, "Level")
	ledger.set_column_title_tooltip_text(3, "Recipe recommended level or spell unlock level")
	ledger.set_column_title(4, "Book required")
	ledger.set_column_title(5, "☆")
	var widths := [190, 100, 64, 48, 160, 30]
	for column: int in range(6):
		ledger.set_column_custom_minimum_width(column, widths[column])
		ledger.set_column_expand(column, column == 0 or column == 4)
	ledger_column.add_child(ledger)
	ledger.item_selected.connect(_on_ledger_selected)
	ledger.item_activated.connect(_open_selected_article)
	ledger.item_edited.connect(_on_ledger_bookmark)
	ledger.column_title_clicked.connect(func(column: int, _button: int):
		var key: String = {0: "name", 1: "topic", 3: "level", 4: "book"}.get(column, "")
		if not key.is_empty():
			if str(_page.get("sort", "name")) == key and key in ["name", "level"]:
				key += "_desc"
			_filter_changed("sort", key))
	var paging := HBoxContainer.new()
	ledger_column.add_child(paging)
	result_label = Label.new()
	result_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	paging.add_child(result_label)
	previous_button = Button.new()
	previous_button.text = "‹"
	previous_button.pressed.connect(_on_previous_pressed)
	paging.add_child(previous_button)
	page_label = Label.new()
	paging.add_child(page_label)
	next_button = Button.new()
	next_button.text = "›"
	next_button.pressed.connect(_on_next_pressed)
	paging.add_child(next_button)
	var preview := VBoxContainer.new()
	preview.name = "Preview"
	preview.custom_minimum_size.y = 170
	preview.size_flags_vertical = Control.SIZE_EXPAND_FILL
	split.add_child(preview)
	preview_header = HBoxContainer.new()
	preview.add_child(preview_header)
	preview_title = Label.new()
	preview_title.clip_text = true
	preview_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	TextColors.bind(preview_title, "encyclopedia_heading")
	preview_header.add_child(preview_title)
	bookmark_entry_button = Button.new()
	bookmark_entry_button.pressed.connect(_toggle_selected_bookmark)
	preview_header.add_child(bookmark_entry_button)
	full_article_button = Button.new()
	full_article_button.text = "Open full article ↗"
	full_article_button.pressed.connect(_open_selected_article)
	preview_header.add_child(full_article_button)
	content_scroll = ScrollContainer.new()
	content_scroll.name = "Content"
	content_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	preview.add_child(content_scroll)
	var middle := VBoxContainer.new()
	middle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_scroll.add_child(middle)
	entry_page = VBoxContainer.new()
	entry_page.name = "EntryPage"
	entry_page.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	middle.add_child(entry_page)
	entry_body = RichTextLabel.new()
	entry_body.name = "EntryBody"
	entry_body.bbcode_enabled = true
	entry_body.fit_content = true
	entry_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	entry_body.meta_clicked.connect(_on_meta_clicked)
	entry_body.gui_input.connect(_on_body_gui_input)
	middle.add_child(entry_body)
	# Anchors and related links live in the article now, rather than a third pane.
	aside_pane = VBoxContainer.new()
	aside_pane.hide()
	add_child(aside_pane)
	page_contents = VBoxContainer.new()
	aside_pane.add_child(page_contents)
	related_list = VBoxContainer.new()
	aside_pane.add_child(related_list)
	status_line = Label.new()
	status_line.name = "EncyclopediaStatus"
	TextColors.bind(status_line, "encyclopedia_note")
	add_child(status_line)
	menu = PopupMenu.new()
	menu.id_pressed.connect(_on_menu_id_pressed)
	add_child(menu)

func _option(host: Node, node_name: String, labels: Array) -> OptionButton:
	var picker := OptionButton.new()
	picker.name = node_name
	for label: String in labels:
		picker.add_item(label)
	host.add_child(picker)
	return picker

static func _shell_heading(text: String) -> Label:
	var label := Label.new()
	label.name = "Heading"
	label.text = text
	TextColors.bind(label, "encyclopedia_heading")
	return label

func _navigation_button(node_name: String, label: String, tooltip: String) -> Button:
	var button := Button.new()
	button.name = node_name
	button.text = label
	button.tooltip_text = tooltip
	button.focus_mode = Control.FOCUS_NONE
	navigation.add_child(button)
	return button

func _on_bookmarks_pressed() -> void:
	# Bookmarks are a search over what has been kept, so they arrive as a page
	# like any other and Back works out of them.
	var state := _browse_state()
	state["kind"] = PAGE_INDEX if str(_page.get("kind", "")) == "bookmarks" else "bookmarks"
	state["page"] = 0
	_navigate(state)

## The category list, rebuilt whenever the document is. A category the
## document does not have is not drawn, so an empty shelf shows as an empty
## shelf rather than as a link that goes nowhere.
func _sync_browse() -> void:
	if browse_list == null:
		return
	for child: Node in browse_list.get_children():
		browse_list.remove_child(child)
		child.queue_free()
	var here: String = str(_page.get("topic", ""))
	var all := Button.new()
	all.text = "All topics"
	all.toggle_mode = true
	all.button_pressed = here.is_empty()
	all.pressed.connect(_filter_changed.bind("topic", ""))
	browse_list.add_child(all)
	for category: Dictionary in _categories:
		var id: String = str(category.get("id", ""))
		var row := Button.new()
		row.name = "Browse%s" % _slug(id)
		var icon: Texture2D = SubjectIcons.icon_for(id)
		if icon != null:
			row.icon = icon
			row.text = str(category.get("title", id))
			row.add_theme_constant_override("h_separation", 5)
			row.add_theme_constant_override("icon_max_width", BROWSE_ICON_SIZE)
		else:
			row.text = "%s  %s" % [CATEGORY_GLYPHS.get(id, "•"),
				str(category.get("title", id))]
		_fit_to_pane(row)
		row.focus_mode = Control.FOCUS_NONE
		row.toggle_mode = true
		row.button_pressed = id == here
		var count: int = (category.get("entries", []) as Array).size()
		row.tooltip_text = ("%s - nothing written yet" % str(category.get("title", id))
			if count == 0 else "%s - %d pages" % [str(category.get("title", id)), count])
		row.disabled = count == 0
		row.pressed.connect(_filter_changed.bind("topic", id))
		browse_list.add_child(row)

## Full reading mode retains breadcrumbs, section jumps, links and related pages.
func _render_entry_page(category_id: String, entry_id: String) -> void:
	var entry: Dictionary = _entry(category_id, entry_id)
	var category: Dictionary = _category(category_id)
	_clear(entry_page)
	_clear(page_contents)
	_clear(related_list)
	_anchors.clear()
	if entry.is_empty():
		entry_page.add_child(_shell_note("That page is not in the encyclopedia."))
		return

	var title := Label.new()
	title.name = "Title"
	title.text = str(entry.get("title", ""))
	title.add_theme_font_size_override("font_size", TITLE_FONT_SIZE)
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	TextColors.bind(title, "encyclopedia_heading")
	entry_page.add_child(title)
	entry_page.add_child(_breadcrumbs(category, entry))
	var anchors := HFlowContainer.new()
	anchors.name = "ArticleSections"
	entry_page.add_child(anchors)
	var summary: String = str(entry.get("summary", ""))
	if not summary.is_empty():
		entry_page.add_child(_shell_note(summary))

	for section: Dictionary in _entry_sections(entry):
		var heading: Label = _shell_heading(str(section.get("title", "")).to_upper())
		entry_page.add_child(heading)
		_anchors[str(section.get("title", ""))] = heading
		var kind: String = str(section.get("kind", "prose"))
		if kind == "facts":
			entry_page.add_child(_fact_table(section.get("rows", []) as Array))
		else:
			entry_page.add_child(_shell_body(str(section.get("text", ""))))
		_add_anchor(str(section.get("title", "")), anchors)

	entry_page.add_child(_shell_heading("RELATED"))
	for related: Dictionary in _related_to(category_id, entry):
		var link := Button.new()
		link.name = "Related%s" % _slug(str(related.get("id", "")))
		link.text = str(related.get("title", ""))
		link.tooltip_text = link.text
		_fit_to_pane(link)
		link.focus_mode = Control.FOCUS_NONE
		link.flat = true
		link.pressed.connect(open_entry.bind(str(related.get("category", "")),
			str(related.get("id", ""))))
		entry_page.add_child(link)

func _add_anchor(title: String, host: Container) -> void:
	if title.is_empty():
		return
	var link := Button.new()
	link.name = "Anchor%s" % _slug(title)
	link.text = title
	link.tooltip_text = title
	TextColors.bind(link, "encyclopedia_link")
	link.focus_mode = Control.FOCUS_NONE
	link.flat = true
	link.pressed.connect(_scroll_to_section.bind(title))
	host.add_child(link)

## A button in a side pane: left-aligned, and cut short with an ellipsis rather
## than widening the pane it sits in.
static func _fit_to_pane(button: Button) -> void:
	TextColors.bind(button, "encyclopedia_link")
	TextColors.bind(button, "encyclopedia_link_hover", "font_hover_color")
	TextColors.bind(button, "encyclopedia_link_hover", "font_hover_pressed_color")
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.clip_text = true
	button.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS

func _scroll_to_section(title: String) -> void:
	var target: Variant = _anchors.get(title)
	if target is Control and content_scroll != null:
		content_scroll.ensure_control_visible(target as Control)

## Where this page sits, as the trail that leads to it.
func _breadcrumbs(category: Dictionary, entry: Dictionary) -> Control:
	var row := HBoxContainer.new()
	row.name = "Breadcrumbs"
	var root := Button.new()
	root.name = "CrumbIndex"
	TextColors.bind(root, "encyclopedia_link")
	TextColors.bind(root, "encyclopedia_link_hover", "font_hover_color")
	root.text = "Encyclopedia"
	root.flat = true
	root.focus_mode = Control.FOCUS_NONE
	root.pressed.connect(show_index)
	row.add_child(root)
	var separator: Label = _shell_note("/")
	separator.size_flags_horizontal = Control.SIZE_FILL
	separator.autowrap_mode = TextServer.AUTOWRAP_OFF
	row.add_child(separator)
	var here := Button.new()
	here.name = "CrumbCategory"
	TextColors.bind(here, "encyclopedia_link")
	TextColors.bind(here, "encyclopedia_link_hover", "font_hover_color")
	here.text = str(category.get("title", ""))
	here.flat = true
	here.focus_mode = Control.FOCUS_NONE
	here.pressed.connect(open_category.bind(str(category.get("id", "")), 0))
	row.add_child(here)
	return row

## A section's rows, with a fixed label width and wrapping linked values.
func _fact_table(rows: Array) -> Control:
	var table := VBoxContainer.new()
	table.name = "Facts"
	table.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for raw: Variant in rows:
		var pair: Array = raw as Array
		if pair.size() < 2:
			continue
		var line := HBoxContainer.new()
		line.name = "Fact"
		var label := Label.new()
		label.name = "Label"
		TextColors.bind(label, "encyclopedia_fact")
		label.text = str(pair[0])
		label.custom_minimum_size = Vector2(FACT_LABEL_WIDTH, 0)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
		line.add_child(label)
		# A value is bbcode: a recipe's materials carry their item icons and a
		# recipe's book is a link to the book's page.
		var value := RichTextLabel.new()
		value.name = "Value"
		value.bbcode_enabled = true
		TextColors.bind(value, "encyclopedia_text", "default_color")
		value.fit_content = true
		value.scroll_active = false
		value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		value.meta_clicked.connect(_on_meta_clicked)
		value.text = str(pair[1])
		line.add_child(value)
		table.add_child(line)
	return table

static func _shell_body(text: String) -> Label:
	var label := Label.new()
	label.name = "Body"
	TextColors.bind(label, "encyclopedia_text")
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return label

static func _shell_note(text: String) -> Label:
	var label := _shell_body(text)
	label.name = "Note"
	TextColors.bind(label, "encyclopedia_note")
	label.modulate = Color(1, 1, 1, 0.72)
	return label

static func _clear(host: Node) -> void:
	if host == null:
		return
	for child: Node in host.get_children():
		host.remove_child(child)
		child.queue_free()

## The sections a page is made of.
##
## An entry may state them, which is how the generated pages carry a table of
## tiers or of ingredients. One that does not is folded into two: what it says
## and what is true of it, which is the shape every written page already has.
func _entry_sections(entry: Dictionary) -> Array[Dictionary]:
	var stated: Array = entry.get("sections", []) as Array
	if not stated.is_empty():
		var out: Array[Dictionary] = []
		for raw: Variant in stated:
			out.append(raw as Dictionary)
		return out
	var sections: Array[Dictionary] = []
	var body: String = str(entry.get("body", ""))
	if not body.is_empty():
		sections.append({"title": "Overview", "kind": "prose", "text": body})
	var facts: Array = entry.get("facts", []) as Array
	if not facts.is_empty():
		sections.append({"title": "At a glance", "kind": "facts", "rows": facts})
	return sections

## What sits beside this page: whatever it names, then its neighbours in the
## same category. Named first because a page that says what it relates to
## knows better than the order it happens to sit in.
func _related_to(category_id: String, entry: Dictionary) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	var seen := {str(entry.get("id", "")): true}
	for raw: Variant in entry.get("related", []) as Array:
		var found: Dictionary = _find_anywhere(str(raw))
		if not found.is_empty() and not seen.has(str(found.get("id", ""))):
			seen[str(found.get("id", ""))] = true
			out.append(found)
	if out.size() >= 3:
		return out
	for sibling: Variant in _category(category_id).get("entries", []) as Array:
		if out.size() >= 3:
			break
		var page: Dictionary = sibling as Dictionary
		if seen.has(str(page.get("id", ""))):
			continue
		seen[str(page.get("id", ""))] = true
		out.append(page)
	return out

func _find_anywhere(entry_id: String) -> Dictionary:
	for page: Dictionary in _flat:
		if str(page.get("id", "")) == entry_id:
			return page
	return {}

func _on_previous_pressed() -> void:
	_change_page(-1)

func _on_next_pressed() -> void:
	_change_page(1)

func _change_page(delta: int) -> void:
	_page["page"] = maxi(0, int(_page.get("page", 0)) + delta)
	_render()

func _on_meta_clicked(meta: Variant) -> void:
	open_page_key(str(meta))

func _on_search_pressed() -> void:
	_on_search_submitted(search_edit.text)

func _on_search_submitted(query: String) -> void:
	_search_timer.stop()
	_filter_changed("query", query.strip_edges())

func _apply_search_text() -> void:
	# Preserve trailing spaces while typing a multiword query.
	_filter_changed("query", search_edit.text)

func _on_body_gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse: InputEventMouseButton = event as InputEventMouseButton
	if mouse.button_index != MOUSE_BUTTON_RIGHT or not mouse.pressed:
		return
	entry_body.accept_event()
	open_menu(entry_body.get_screen_position() + mouse.position)

func open_menu(where: Vector2) -> void:
	menu.clear()
	menu.add_item("Search...", 0)
	var key: String = page_key()
	if _bookmark_index(key) >= 0:
		menu.add_item("Remove this bookmark", 2)
	else:
		menu.add_item("Bookmark this page", 1)
	if not _bookmarks.is_empty():
		menu.add_separator("Bookmarks")
		for index: int in range(_bookmarks.size()):
			menu.add_item(str(_bookmarks[index].get("label", "")), 100 + index)
		menu.add_separator()
		menu.add_item("Clear every bookmark", 3)
	menu.position = Vector2i(where)
	menu.reset_size()
	menu.popup()

func _bookmark_index(key: String) -> int:
	for index: int in range(_bookmarks.size()):
		if str(_bookmarks[index].get("key", "")) == key:
			return index
	return -1

func _on_menu_id_pressed(id: int) -> void:
	if id >= 100:
		var index: int = id - 100
		if index < _bookmarks.size():
			open_page_key(str(_bookmarks[index].get("key", PAGE_INDEX)))
		return
	match id:
		0:
			search_row.show()
			search_edit.grab_focus()
		1:
			add_bookmark()
		2:
			remove_bookmark(page_key())
		3:
			_bookmarks.clear()
			bookmarks_changed.emit(bookmarks())
			_render()

func add_bookmark() -> void:
	var key: String = page_key()
	if _bookmark_index(key) >= 0:
		return
	_bookmarks.append({"key": key, "label": page_title()})
	bookmarks_changed.emit(bookmarks())
	_render()

func remove_bookmark(key: String) -> void:
	var index: int = _bookmark_index(key)
	if index < 0:
		return
	_bookmarks.remove_at(index)
	bookmarks_changed.emit(bookmarks())
	_render()

static func _text_color(role: String) -> String:
	return "#" + TextColors.color(role).to_html(false)

func _on_text_colors_changed(role: String) -> void:
	if role.is_empty() or role.begins_with("encyclopedia_"):
		var scroll := content_scroll.scroll_vertical if content_scroll != null else 0
		_render()
		if content_scroll != null:
			content_scroll.scroll_vertical = scroll

# --- whole-catalogue browsing -------------------------------------------------

func _browse_state() -> Dictionary:
	return _page.duplicate(true)

static func _key_for(entry: Dictionary) -> String:
	return "entry:%s:%s" % [entry.category, entry.id]

static func _plain_text(text: String) -> String:
	var images := RegEx.new()
	images.compile("\\[img[^\\]]*\\].*?\\[/img\\]")
	var tags := RegEx.new()
	tags.compile("\\[[^\\]]*\\]")
	return tags.sub(images.sub(text, "", true), "", true)

static func _matches_words(entry: Dictionary, query: String) -> bool:
	for word: String in query.to_lower().replace("\t", " ").replace("\n", " ").split(" ", false):
		if not str(entry.get("search", "")).contains(word):
			return false
	return true

## The filters and sort always run before slicing a page.
func filtered_entries() -> Array[Dictionary]:
	var found: Array[Dictionary] = []
	var state := _browse_state()
	for entry: Dictionary in _flat:
		if not str(state.get("topic", "")).is_empty() and str(entry.category) != str(state.topic):
			continue
		if not str(state.get("type", "")).is_empty() and str(entry.get("type", "")) != str(state.type):
			continue
		if not _matches_words(entry, str(state.get("query", ""))):
			continue
		if str(state.get("kind", "")) == "bookmarks" and _bookmark_index(_key_for(entry)) < 0:
			continue
		var requirement := int(state.get("book_filter", 0))
		if requirement > 0:
			if str(entry.get("type", "")) not in ["recipe", "spell"]:
				continue
			if (not str(entry.get("book", "")).is_empty()) != (requirement == 1):
				continue
		if bool(state.get("limit_level", false)):
			var level := int(entry.get("level", -1))
			if level < 0 or level > int(state.get("max_level", 100)):
				continue
		found.append(entry)
	found.sort_custom(_ledger_before)
	return found

func _ledger_before(a: Dictionary, b: Dictionary) -> bool:
	var sort_key := str(_page.get("sort", "name"))
	if sort_key in ["level", "level_desc"]:
		var la := int(a.get("level", -1))
		var lb := int(b.get("level", -1))
		if la != lb:
			if la < 0: return false
			if lb < 0: return true
			return la > lb if sort_key == "level_desc" else la < lb
	elif sort_key in ["topic", "book"]:
		var av := str(_category(str(a.category)).get("title", "")) if sort_key == "topic" else str(a.get("book", ""))
		var bv := str(_category(str(b.category)).get("title", "")) if sort_key == "topic" else str(b.get("book", ""))
		var diff := av.naturalnocasecmp_to(bv)
		if diff != 0: return diff < 0
	var diff := str(a.title).naturalnocasecmp_to(str(b.title))
	if diff != 0: return diff > 0 if sort_key == "name_desc" else diff < 0
	return _key_for(a) < _key_for(b)

func _filter_changed(field: String, value: Variant) -> void:
	if _syncing or _page.get(field) == value:
		return
	var state := _browse_state()
	if str(state.get("kind", "")) != "bookmarks":
		state["kind"] = "browse"
	state[field] = value
	state["page"] = 0
	state["selected"] = ""
	_navigate(state)

func _on_ledger_selected() -> void:
	if _syncing or ledger.get_selected() == null:
		return
	var key := str(ledger.get_selected().get_metadata(0))
	_page["selected"] = key
	_render_selection(key)

func _open_selected_article() -> void:
	var parts := str(_page.get("selected", "")).split(":")
	if parts.size() >= 3:
		open_entry(parts[1], parts[2])

func _toggle_selected_bookmark() -> void:
	_toggle_bookmark(str(_page.get("selected", "")))

func _on_ledger_bookmark() -> void:
	if _syncing or ledger.get_edited() == null:
		return
	_toggle_bookmark(str(ledger.get_edited().get_metadata(0)))

func _toggle_bookmark(key: String) -> void:
	var parts := key.split(":")
	if parts.size() < 3:
		return
	var at := _bookmark_index(key)
	if at >= 0:
		_bookmarks.remove_at(at)
	else:
		var entry := _entry(parts[1], parts[2])
		if entry.is_empty(): return
		_bookmarks.append({"key": key, "label": str(entry.title)})
	bookmarks_changed.emit(bookmarks())
	_render()

static func _ledger_style(border: Color, fill: Color) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = fill
	box.border_color = border
	box.set_border_width_all(1)
	box.set_content_margin_all(4)
	return box
