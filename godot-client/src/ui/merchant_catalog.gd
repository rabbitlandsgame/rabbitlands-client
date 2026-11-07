extends RefCounted
## Presentation metadata only; prices, quantities and trade IDs remain server-owned.
const ItemNames := preload("res://src/state/item_names.gd")
static var _categories: Dictionary = {}
static var _loaded := false

static func category(entry: Dictionary) -> String:
	if not _loaded:
		_loaded = true
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/items/categories.json"))
		if data is Dictionary:
			_categories = data.get("categories", {})
	var value := str(entry.get("category", _categories.get(str(entry.get("name", "")), "Other"))).strip_edges()
	return value if not value.is_empty() else "Other"

static func browse(items: Array, selling: bool, item_type: String, query: String, order: int) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	query = query.strip_edges().to_lower()
	for entry: Dictionary in items:
		if int(entry.get("sell_price" if selling else "buy_price", 0)) <= 0:
			continue
		if selling and int(entry.get("owned", 0)) <= 0:
			continue
		if item_type != "All" and category(entry) != item_type:
			continue
		if not query.is_empty() and not (ItemNames.searchable(str(entry.get("name", ""))) + " " + category(entry)).to_lower().contains(query):
			continue
		result.append(entry)
	result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if order in [2, 3]:
			# Compare per-item prices, including fractional sale bundles.
			var left := int(a.get("sell_price" if selling else "buy_price", 0)) * (maxi(1, int(b.get("sell_quantity", 1))) if selling else 1)
			var right := int(b.get("sell_price" if selling else "buy_price", 0)) * (maxi(1, int(a.get("sell_quantity", 1))) if selling else 1)
			if left != right: return left < right if order == 2 else left > right
		elif order == 4 and category(a) != category(b):
			return category(a).naturalnocasecmp_to(category(b)) < 0
		var comparison := ItemNames.display(str(a.get("name", ""))).naturalnocasecmp_to(ItemNames.display(str(b.get("name", ""))))
		if comparison != 0: return comparison > 0 if order == 1 else comparison < 0
		return int(a.get("index", 0)) < int(b.get("index", 0)))
	return result
