extends MenuButton
## Nested, keyboard-searchable menus use only the server's admitted actions.
signal action_selected(action_id: String)
var selected_id := ""
var menus: Dictionary = {}
static var _catalog: SpellCatalog

func configure(actions: Array, current: String) -> void:
	selected_id = current
	flat = false
	clip_text = true
	alignment = HORIZONTAL_ALIGNMENT_LEFT
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	custom_minimum_size = Vector2(100, 28)
	get_popup().allow_search = true
	text = "Unavailable: " + current + " ▾"
	var ordered := actions.duplicate()
	ordered.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.name).naturalnocasecmp_to(str(b.name)) < 0)
	# Build top-level groups in a stable order, without empty role categories.
	for group: String in ["Standard actions", "Spells", "Techniques", "Items"]:
		for action: Dictionary in ordered:
			if _path(action)[0] == group: _menu([group]); break
	for category: String in SpellCatalog.GROUP_ORDER:
		for action: Dictionary in ordered:
			if _path(action) == ["Spells", category]: _menu(["Spells", category]); break
	for category: String in ["Healing", "Ether", "Cleansing", "Action points", "Buffs", "Food"]:
		for action: Dictionary in ordered:
			if _path(action) == ["Items", category]: _menu(["Items", category]); break
	for action: Dictionary in ordered:
		var popup := _menu(_path(action))
		var index := popup.item_count
		popup.add_radio_check_item(str(action.name), index)
		popup.set_item_metadata(index, str(action.id))
		popup.set_item_checked(index, action.id == current)
		var scope: String = {"self":"You", "target":"Selected target", "allies":"Party allies"}.get(action.get("scope", ""), "")
		popup.set_item_tooltip(index, str(action.name) + ("\nAffects: " + scope if not scope.is_empty() else ""))
		if action.id == current: text = str(action.name) + " ▾"
	tooltip_text = text.trim_suffix(" ▾") + "\nChoose Standard actions, Spells, Techniques or Items. Items use your inventory, including when a bot consumes them."
	disabled = actions.is_empty()

func _path(action: Dictionary) -> Array[String]:
	var id := str(action.id)
	if id.begins_with("item:"): return ["Items", str(action.get("item_group", "Consumables"))]
	if id.begins_with("spell:"):
		if _catalog == null:
			_catalog = SpellCatalog.new()
			_catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
		return ["Spells", _catalog.group_of(int(id.trim_prefix("spell:")))]
	if id.begins_with("technique:"):
		return ["Techniques", "Attacks" if action.get("hostile", false) else "Support & stances"]
	return ["Standard actions"]

func _menu(path: Array[String]) -> PopupMenu:
	var key := "/".join(path)
	if menus.has(key): return menus[key]
	var parent := get_popup()
	if path.size() > 1: parent = _menu(path.slice(0, path.size() - 1))
	var popup := PopupMenu.new()
	popup.name = path[-1].replace(" ", "").replace("&", "")
	popup.allow_search = true
	parent.add_child(popup)
	parent.add_submenu_item(path[-1], str(popup.name))
	popup.id_pressed.connect(func(id: int) -> void:
		var index := popup.get_item_index(id)
		var chosen: Variant = popup.get_item_metadata(index)
		if chosen is String and not chosen.is_empty(): action_selected.emit(chosen))
	menus[key] = popup
	return popup
