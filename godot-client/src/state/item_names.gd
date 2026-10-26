extends RefCounted
## Presentation only. Names sent to the server and saved item identities stay canonical.
static var _names: Dictionary = {}
static var _loaded := false

static func aliases() -> Dictionary:
	if not _loaded:
		_loaded = true
		var document: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/items/display_names.json"))
		if document is Dictionary and document.get("names") is Dictionary:
			_names = document.names
	return _names

static func display(canonical: String) -> String:
	return str(aliases().get(canonical, canonical))

static func searchable(canonical: String) -> String:
	return canonical + " " + display(canonical)

static func tooltip(canonical: String) -> String:
	var label := display(canonical)
	return label if label == canonical else label + "\nAlso searchable as: " + canonical

static func in_text(value: String) -> String:
	var names: Array = aliases().keys()
	names.sort_custom(func(a: String, b: String) -> bool: return a.length() > b.length())
	for name: String in names: value = value.replace(name, display(name))
	return value
