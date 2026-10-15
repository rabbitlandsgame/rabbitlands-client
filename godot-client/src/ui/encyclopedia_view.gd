class_name EncyclopediaView
extends VBoxContainer
## The Eloria encyclopedia, laid out the way Eternal Lands lays its own out:
## an index of categories, a page of links per category, and a page per entry
## with a Back To Index link at the foot of it.
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
## The window is 640 wide and holds three panes, so its type is set smaller
## than the rest of the HUD: at the HUD's own size the two side panes grew to
## fit their longest link and left the page itself a column a few words wide.
const FONT_SIZE := 13
const TITLE_FONT_SIZE := 18
## The side panes are fixed rather than sized by what is in them. A link too
## long for its pane is cut short with its whole name in the tooltip, because
## a pane that widens for one long title narrows the page for every title.
const BROWSE_WIDTH := 138
const ASIDE_WIDTH := 132
const PANE_GAP := 6
const BROWSE_ICON_SIZE := 18
## The label column of a fact table. Labels wrap inside it rather than push
## the values over: a value squeezed to nothing wraps a letter to a line.
const FACT_LABEL_WIDTH := 104
const FACT_ICON_WIDTH := 16

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
var page_contents: VBoxContainer
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
	_navigate({"kind": "category", "id": category_id, "page": page})

func open_entry(category_id: String, entry_id: String) -> void:
	_navigate({"kind": "entry", "category": category_id, "id": entry_id})

## Every entry whose title, summary or text contains the words asked for.
func search(query: String) -> void:
	_navigate({"kind": "search", "query": query})

func matches(query: String) -> Array[Dictionary]:
	var needle: String = query.strip_edges().to_lower()
	var found: Array[Dictionary] = []
	if needle.is_empty():
		return found
	for entry: Dictionary in _flat:
		if str(entry.get("search", "")).contains(needle):
			found.append(entry)
	return found

func page_key() -> String:
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
	if key.begins_with("cat:"):
		var parts: PackedStringArray = key.substr(4).split(":")
		open_category(parts[0], int(parts[1]) if parts.size() > 1 else 0)
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

func _written_entry(raw: Dictionary, category_id: String) -> Dictionary:
	var body: String = str(raw.get("body", ""))
	var facts: Array[Array] = []
	var raw_facts: Variant = raw.get("facts", [])
	if raw_facts is Array:
		for fact_value: Variant in raw_facts as Array:
			if fact_value is Array and (fact_value as Array).size() >= 2:
				facts.append([str((fact_value as Array)[0]),
					_escape(str((fact_value as Array)[1]))])
	return _entry_record(str(raw.get("id", "")), str(raw.get("title", "")),
		str(raw.get("summary", "")), body, facts, {}, category_id)

func _entry_record(id: String, title: String, summary: String, body: String,
		facts: Array[Array], image: Dictionary, category_id: String) -> Dictionary:
	return {"id": id, "title": title, "summary": summary, "body": body,
		"facts": facts, "image": image, "category": category_id,
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
		facts.append(["Recommended %s level" % readable_skill,
			str(int(recipe.get("level", 0)))])
		facts.append(["%s experience given" % readable_skill,
			str(int(recipe.get("experience", 0)))])
		facts.append(["Food subtracted", str(int(recipe.get("food", 0)))])
		var mana: int = int(recipe.get("mana", 0))
		if mana > 0:
			facts.append(["Ether required", str(mana)])
		var body: String = ("Mixed with the %s skill. The server checks every"
			+ " line below before it lets the mix start, and refuses the mix"
			+ " rather than half-making it.") % readable_skill
		var image: Dictionary = _item_image(int(recipe.get("outputImageId", -1)))
		var entry: Dictionary = _entry_record(entry_id, title, "", body, facts,
			image, category_id)
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
		facts.append(["Ether", str(int(spell.get("mana", 0)))])
		facts.append(["Magic level", str(int(spell.get("level", 0)))])
		var effect: String = str(spell.get("effect", ""))
		if not effect.is_empty():
			facts.append(["Targeting", str(spell.get("scope", "self")).capitalize()])
			facts.append(["Power", "1–10; increases strength, duration and reagent costs"])
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
		entries.append(_entry_record(_slug(title), title, "", body, facts,
			catalogue.icon_source(spell_id), category_id))
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
		var body: String = ("A book the server can teach you from. Reading it"
			+ " takes time and it is read once; until the server records that"
			+ " you have read it, what it teaches is refused however high your"
			+ " level is.")
		entries.append(_entry_record(_slug(title), title, "", body, facts, {},
			category_id))
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
		var facts: Array[Array] = [["The server's map file",
			str(region.get("serverMap", "unstated"))]]
		var body: String = ("A region of Nymara. It is its own map on the"
			+ " server, so arriving here is a change of map rather than a walk"
			+ " across a seam, and the world around you is rebuilt as you"
			+ " arrive.")
		entries.append(_entry_record(_slug(title), title, "", body, facts, {},
			category_id))
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
		var facts: Array[Array] = [["Reported as", skill]]
		entries.append(_entry_record(_slug(skill), skill.capitalize(), "", body,
			facts, {}, category_id))
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
		lines.append("%s%d %s" % [_image_tag(image, 22),
			maxi(1, int(ingredient.get("quantity", 1))),
			_escape(str(ingredient.get("name", "")))])
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
	var kind: String = str(_page.get("kind", PAGE_INDEX))
	var pages := 1
	var page_number := 0
	match kind:
		"category":
			var category: Dictionary = _category(str(_page.get("id", "")))
			var entries: Array = category.get("entries", []) as Array
			pages = maxi(1, ceili(float(entries.size()) / float(entries_per_page)))
			page_number = clampi(int(_page.get("page", 0)), 0, pages - 1)
			_page["page"] = page_number
			entry_body.text = _render_category(category, page_number, pages)
		"entry":
			_render_entry_page(str(_page.get("category", "")),
				str(_page.get("id", "")))
		"search":
			entry_body.text = _render_search(str(_page.get("query", "")))
		"bookmarks":
			entry_body.text = _render_bookmarks()
		_:
			entry_body.text = _render_index()
	# One of the two shows at a time: a page is built from controls, and the
	# lists are a document the renderer already knows how to draw.
	var built: bool = kind == "entry"
	entry_page.visible = built
	entry_body.visible = not built
	# A list has no sections and nothing beside it, and an empty pane's width
	# is better spent on the list.
	aside_pane.visible = built
	if not built:
		_clear(entry_page)
		_clear(page_contents)
		_clear(related_list)
		_anchors.clear()
	_sync_browse()
	if content_scroll != null:
		content_scroll.scroll_vertical = 0
	back_button.disabled = _history.is_empty()
	bookmarks_button.disabled = _bookmarks.is_empty()
	index_button.disabled = kind == PAGE_INDEX
	page_label.text = "Page %d/%d" % [page_number + 1, pages] if pages > 1 else ""
	page_label.visible = pages > 1
	previous_button.visible = pages > 1
	next_button.visible = pages > 1
	previous_button.disabled = page_number <= 0
	next_button.disabled = page_number >= pages - 1

func _render_index() -> String:
	var lines: Array[String] = [_title_block("")]
	lines.append("[color=%s]%s[/color]\n" % [NOTE_COLOUR,
		_escape(str(_document.get("note", "")))])
	var cells: Array[String] = []
	for category: Dictionary in _categories:
		cells.append("[cell]%s[/cell][cell]  -  %s[/cell]" % [
			_link("cat:%s:0" % str(category.get("id", "")),
				str(category.get("title", ""))),
			_escape(str(category.get("summary", "")))])
	lines.append("[table=2]%s[/table]" % "".join(cells))
	return "\n".join(lines)

func _render_category(category: Dictionary, page_number: int, pages: int) -> String:
	var lines: Array[String] = [_title_block(str(category.get("title", "")).to_upper())]
	var intro: String = str(category.get("intro", ""))
	if not intro.is_empty():
		lines.append("[color=%s]%s[/color]\n" % [NOTE_COLOUR, _escape(intro)])
	var entries: Array = category.get("entries", []) as Array
	if entries.is_empty():
		lines.append("[i]Nothing here yet. This category is filled from a"
			+ " catalogue the client has not loaded.[/i]")
		return "\n".join(lines)
	var first: int = page_number * entries_per_page
	var last: int = mini(first + entries_per_page, entries.size())
	var cells: Array[String] = []
	for index: int in range(first, last):
		var entry: Dictionary = entries[index] as Dictionary
		cells.append("[cell]%s[/cell]" % _link("entry:%s:%s" % [
			str(category.get("id", "")), str(entry.get("id", ""))],
			str(entry.get("title", ""))))
	if cells.size() % 2 == 1:
		cells.append("[cell] [/cell]")
	lines.append("[table=2]%s[/table]" % "".join(cells))
	if pages > 1:
		lines.append("\n[color=%s]%d entries over %d pages.[/color]" % [
			NOTE_COLOUR, entries.size(), pages])
	return "\n".join(lines)

func _render_entry(category_id: String, entry_id: String) -> String:
	var entry: Dictionary = _entry(category_id, entry_id)
	if entry.is_empty():
		return "[i]That page is not in the encyclopedia.[/i]"
	var category: Dictionary = _category(category_id)
	var lines: Array[String] = [_title_block(str(category.get("title", "")).to_upper())]
	var image: Dictionary = entry.get("image", {}) as Dictionary
	lines.append("[center]%s[color=%s][b]%s[/b][/color][/center]\n" % [
		_image_tag(image, 40), HEADING_COLOUR, _escape(str(entry.get("title", "")))])
	var summary: String = str(entry.get("summary", ""))
	if not summary.is_empty():
		lines.append("[color=%s][i]%s[/i][/color]\n" % [NOTE_COLOUR, _escape(summary)])
	for paragraph: String in str(entry.get("body", "")).split("\n\n", false):
		lines.append(_escape(paragraph) + "\n")
	var facts: Array = entry.get("facts", []) as Array
	for fact_value: Variant in facts:
		var fact: Array = fact_value as Array
		var label: String = "[color=%s]%s:[/color]" % [FACT_COLOUR,
			_escape(str(fact[0]))]
		var text: String = str(fact[1])
		if text.contains("\n"):
			lines.append(label)
			for line: String in text.split("\n", false):
				lines.append("    " + line)
		else:
			lines.append("%s %s" % [label, text])
	lines.append("\n[center]%s[/center]" % _link("cat:%s:0" % category_id,
		"Back To %s Index" % str(category.get("title", ""))))
	return "\n".join(lines)

## The pages that have been kept, as a page of their own so that Back works
## out of it like anywhere else.
func _render_bookmarks() -> String:
	var lines: Array[String] = [_title_block("BOOKMARKS")]
	if _bookmarks.is_empty():
		lines.append("[color=%s]Nothing kept yet. Right-click a page to keep it.[/color]"
			% NOTE_COLOUR)
		return "\n".join(lines)
	for raw: Variant in _bookmarks:
		var mark: Dictionary = raw as Dictionary
		lines.append(_link(str(mark.get("key", "")), str(mark.get("title", ""))))
	return "\n".join(lines)

func _render_search(query: String) -> String:
	var lines: Array[String] = [_title_block("SEARCH")]
	var found: Array[Dictionary] = matches(query)
	lines.append("[color=%s]%d %s for \"%s\".[/color]\n" % [NOTE_COLOUR, found.size(),
		"page" if found.size() == 1 else "pages", _escape(query)])
	for entry: Dictionary in found:
		var category: Dictionary = _category(str(entry.get("category", "")))
		lines.append("%s  [color=%s]- in %s[/color]" % [
			_link("entry:%s:%s" % [str(entry.get("category", "")),
				str(entry.get("id", ""))], str(entry.get("title", ""))),
			NOTE_COLOUR, _escape(str(category.get("title", "")))])
	if found.is_empty():
		lines.append("[i]Nothing here says that.[/i]")
	return "\n".join(lines)

func _title_block(subtitle: String) -> String:
	var block: String = "[center][color=%s]%s[/color]" % [HEADING_COLOUR,
		_escape(str(_document.get("title", "The Rabbit Lands Encyclopedia")))]
	if not subtitle.is_empty():
		block += "\n[color=%s]%s[/color]" % [HEADING_COLOUR, _escape(subtitle)]
	return block + "[/center]\n"

func _link(meta: String, text: String) -> String:
	return "[url=%s][color=%s]%s[/color][/url]" % [meta, LINK_COLOUR, _escape(text)]

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

## Three panes: what there is to read, what is being read, and where to go
## from here.
##
## The window was one scrolling document with a row of navigation buttons over
## it, which meant the only way to find anything was to walk the index and the
## only way back was the Back button. The categories are always on screen now,
## a page says what is on it, and a page says what it is next to.
##
## The document model underneath is unchanged - the same categories, the same
## generated halves, the same search and the same bookmarks. What changed is
## that an entry is built from controls rather than written as bbcode, because
## a fact table with an icon in every row is a table and not a paragraph.
func _build() -> void:
	var compact := Theme.new()
	compact.default_font_size = FONT_SIZE
	theme = compact
	add_theme_constant_override("separation", 2)
	var shell := VBoxContainer.new()
	shell.name = "Shell"
	shell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	shell.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(shell)

	navigation = HBoxContainer.new()
	navigation.name = "EncyclopediaNavigation"
	shell.add_child(navigation)
	search_row = navigation
	search_edit = LineEdit.new()
	search_edit.name = "EncyclopediaSearch"
	search_edit.placeholder_text = "Search the encyclopedia…"
	search_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search_edit.text_submitted.connect(_on_search_submitted)
	navigation.add_child(search_edit)
	var search_button := Button.new()
	search_button.name = "EncyclopediaSearchGo"
	search_button.text = "Find"
	search_button.focus_mode = Control.FOCUS_NONE
	search_button.pressed.connect(_on_search_pressed)
	navigation.add_child(search_button)
	back_button = _navigation_button("EncyclopediaBack", "← Back",
		"Back to the page before this one")
	back_button.pressed.connect(go_back)
	index_button = _navigation_button("EncyclopediaIndex", "Index",
		"Back to the list of categories")
	index_button.pressed.connect(show_index)
	bookmarks_button = _navigation_button("EncyclopediaBookmarks", "☆ Bookmarks",
		"Pages you have kept")
	bookmarks_button.pressed.connect(_on_bookmarks_pressed)
	# Paging survives inside a category, which can hold a hundred recipes.
	previous_button = _navigation_button("EncyclopediaPrevious", "<<<",
		"The page before this one")
	previous_button.pressed.connect(_on_previous_pressed)
	next_button = _navigation_button("EncyclopediaNext", ">>>",
		"The page after this one")
	next_button.pressed.connect(_on_next_pressed)
	page_label = Label.new()
	page_label.name = "EncyclopediaPage"
	navigation.add_child(page_label)

	var panes := HBoxContainer.new()
	panes.name = "Panes"
	panes.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panes.add_theme_constant_override("separation", PANE_GAP)
	shell.add_child(panes)

	# Left: everything there is to read, always on screen.
	var browse_column := VBoxContainer.new()
	browse_column.name = "Browse"
	browse_column.custom_minimum_size = Vector2(BROWSE_WIDTH, 0)
	browse_column.add_theme_constant_override("separation", 2)
	panes.add_child(browse_column)
	browse_column.add_child(_shell_heading("BROWSE"))
	var browse_scroll := ScrollContainer.new()
	browse_scroll.name = "BrowseScroll"
	browse_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	browse_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	browse_column.add_child(browse_scroll)
	browse_list = VBoxContainer.new()
	browse_list.name = "BrowseList"
	browse_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	browse_list.add_theme_constant_override("separation", 2)
	browse_scroll.add_child(browse_list)

	# Middle: either a built page or, for the lists, the document renderer
	# that already knows how to draw them.
	var middle := ScrollContainer.new()
	middle.name = "Content"
	middle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	middle.size_flags_vertical = Control.SIZE_EXPAND_FILL
	middle.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	panes.add_child(middle)
	content_scroll = middle
	var middle_column := VBoxContainer.new()
	middle_column.name = "ContentColumn"
	middle_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	middle.add_child(middle_column)
	entry_page = VBoxContainer.new()
	entry_page.name = "EntryPage"
	entry_page.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	middle_column.add_child(entry_page)
	entry_body = RichTextLabel.new()
	entry_body.name = "EntryBody"
	entry_body.bbcode_enabled = true
	entry_body.fit_content = true
	entry_body.selection_enabled = true
	entry_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	entry_body.meta_clicked.connect(_on_meta_clicked)
	entry_body.gui_input.connect(_on_body_gui_input)
	middle_column.add_child(entry_body)

	# Right: what is on this page, and what sits beside it.
	var aside := VBoxContainer.new()
	aside.name = "Aside"
	aside.custom_minimum_size = Vector2(ASIDE_WIDTH, 0)
	aside.add_theme_constant_override("separation", 0)
	panes.add_child(aside)
	aside_pane = aside
	aside.add_child(_shell_heading("ON THIS PAGE"))
	page_contents = VBoxContainer.new()
	page_contents.name = "OnThisPage"
	aside.add_child(page_contents)
	aside.add_child(_shell_heading("RELATED"))
	related_list = VBoxContainer.new()
	related_list.name = "Related"
	aside.add_child(related_list)

	status_line = Label.new()
	status_line.name = "EncyclopediaStatus"
	status_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	status_line.text = "Right-click for search and bookmark options"
	status_line.modulate = Color(1, 1, 1, 0.55)
	shell.add_child(status_line)

	menu = PopupMenu.new()
	menu.name = "EncyclopediaMenu"
	menu.id_pressed.connect(_on_menu_id_pressed)
	add_child(menu)

static func _shell_heading(text: String) -> Label:
	var label := Label.new()
	label.name = "Heading"
	label.text = text
	label.add_theme_color_override("font_color", Color(0.91, 0.71, 0.32))
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
	_navigate({"kind": "bookmarks"})

## The category list, rebuilt whenever the document is. A category the
## document does not have is not drawn, so an empty shelf shows as an empty
## shelf rather than as a link that goes nowhere.
func _sync_browse() -> void:
	if browse_list == null:
		return
	for child: Node in browse_list.get_children():
		browse_list.remove_child(child)
		child.queue_free()
	var here: String = str(_page.get("category", _page.get("id", "")))
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
		row.pressed.connect(open_category.bind(id, 0))
		browse_list.add_child(row)

## One page, built from controls: its title, where it sits, what it says, and
## the sections it is made of.
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
	title.add_theme_color_override("font_color", Color(0.91, 0.71, 0.32))
	entry_page.add_child(title)
	entry_page.add_child(_breadcrumbs(category, entry))
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
		_add_anchor(str(section.get("title", "")))

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
		related_list.add_child(link)

func _add_anchor(title: String) -> void:
	if title.is_empty():
		return
	var link := Button.new()
	link.name = "Anchor%s" % _slug(title)
	link.text = title
	link.tooltip_text = title
	_fit_to_pane(link)
	link.focus_mode = Control.FOCUS_NONE
	link.flat = true
	link.pressed.connect(_scroll_to_section.bind(title))
	page_contents.add_child(link)

## A button in a side pane: left-aligned, and cut short with an ellipsis rather
## than widening the pane it sits in.
static func _fit_to_pane(button: Button) -> void:
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
	here.text = str(category.get("title", ""))
	here.flat = true
	here.focus_mode = Control.FOCUS_NONE
	here.pressed.connect(open_category.bind(str(category.get("id", "")), 0))
	row.add_child(here)
	return row

## A section's rows, each a label and a value. The icon column is drawn and
## left empty: the art for it does not exist yet, and a row that shifted
## sideways the day it arrives would move every page at once.
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
		var icon := Control.new()
		icon.name = "Icon"
		icon.custom_minimum_size = Vector2(FACT_ICON_WIDTH, 0)
		line.add_child(icon)
		var label := Label.new()
		label.name = "Label"
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
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return label

static func _shell_note(text: String) -> Label:
	var label := _shell_body(text)
	label.name = "Note"
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
	if str(_page.get("kind", "")) == "category":
		open_category(str(_page.get("id", "")), int(_page.get("page", 0)) - 1)

func _on_next_pressed() -> void:
	if str(_page.get("kind", "")) == "category":
		open_category(str(_page.get("id", "")), int(_page.get("page", 0)) + 1)

func _on_meta_clicked(meta: Variant) -> void:
	open_page_key(str(meta))

func _on_search_pressed() -> void:
	_on_search_submitted(search_edit.text)

func _on_search_submitted(query: String) -> void:
	if not query.strip_edges().is_empty():
		search(query.strip_edges())

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

func add_bookmark() -> void:
	var key: String = page_key()
	if _bookmark_index(key) >= 0:
		return
	_bookmarks.append({"key": key, "label": page_title()})
	bookmarks_changed.emit(bookmarks())

func remove_bookmark(key: String) -> void:
	var index: int = _bookmark_index(key)
	if index < 0:
		return
	_bookmarks.remove_at(index)
	bookmarks_changed.emit(bookmarks())
