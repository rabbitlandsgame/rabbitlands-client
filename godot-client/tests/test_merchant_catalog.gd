extends SceneTree
const Catalog := preload("res://src/ui/merchant_catalog.gd")
var failures := 0

func _init() -> void:
	var items: Array = [
		{"index": 7, "name": "Bread", "buy_price": 5, "sell_price": 3, "owned": 4},
		{"index": 42, "name": "Sage", "buy_price": 1, "sell_price": 1, "sell_quantity": 2, "owned": 10},
		{"index": 99, "name": "New item", "buy_price": 4, "sell_price": 2, "owned": 0},
		{"index": 18, "name": "Bundle", "category": "Tools", "buy_price": 0, "sell_price": 2, "sell_quantity": 8, "owned": 8}]
	_expect(Catalog.category(items[0]) == "Food", "uses the served item category")
	_expect(Catalog.category(items[2]) == "Other", "unknown goods remain browsable")
	var rows := Catalog.browse(items, false, "All", "", 0)
	_expect(rows.size() == 3 and rows[0].index == 7, "buy view omits goods not for sale")
	rows = Catalog.browse(items, false, "Food", "food", 0)
	_expect(rows.size() == 1 and rows[0].index == 7, "search combines with category filtering")
	_expect(Catalog.browse(items, false, "Tools", "", 0).is_empty(), "empty category is safe")
	rows = Catalog.browse([{"index": 1, "name": "Militia Arming Sword", "buy_price": 1}], false, "All", "iron sword", 0)
	_expect(rows.size() == 1, "search accepts a display alias for the canonical name")
	rows = Catalog.browse(items, false, "All", "", 4)
	_expect(rows[0].index == 42, "type sorting uses the actual category")
	rows = Catalog.browse(items, true, "All", "", 2)
	_expect(rows.size() == 3 and rows[0].index == 18 and rows[1].index == 42,
		"sale prices sort per item rather than per bundle; unowned goods are excluded")
	rows = Catalog.browse(items, true, "All", "", 3)
	_expect(rows[0].index == 7 and rows[2].index == 18, "descending sale price reverses price order")
	rows = Catalog.browse(items, false, "All", "", 1)
	_expect(rows[0].index == 42 and rows[2].index == 7, "descending display names")
	_expect(items[0].index == 7 and items[1].index == 42, "browsing leaves the server snapshot unchanged")
	var books: Array = [
		{"index": 101, "name": "Manual of Charge", "image_id": 640, "buy_price": 20, "sell_price": 5, "owned": 1},
		{"index": 205, "name": "Manual of Aimed Shot", "image_id": 641, "buy_price": 10, "sell_price": 3, "owned": 0},
		{"index": 309, "name": "Tome of Blink", "image_id": 642, "buy_price": 30, "sell_price": 8, "owned": 2}]
	_expect(Catalog.category(books[0]) == "Melee Books", "combat manuals have a subject filter")
	_expect(Catalog.category({"name": "Book of Beginnings"}) == "General Books", "introductory book is included")
	_expect(Catalog.category({"name": "Book of Bowyery"}) == "Engineering Books", "book subject follows the skill taught")
	_expect(Catalog.category({"name": "Book of Fine Brewing"}) == "Potion Books", "brewing books have their own subject")
	rows = Catalog.browse(books, false, "Ranging Books", "ranging", 0)
	_expect(rows.size() == 1 and rows[0].index == 205, "subject filters and search preserve the trade ID")
	_expect(Catalog.browse(books, true, "Ranging Books", "", 0).is_empty(), "subject sell view excludes unowned books")
	rows = Catalog.browse(books, true, "Magic Books", "blink", 0)
	_expect(rows.size() == 1 and rows[0].index == 309, "subject filtering works when selling owned tomes")
	print("merchant catalog checks: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)
