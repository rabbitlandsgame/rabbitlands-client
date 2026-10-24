extends Control
## Compact action library. The server remains authoritative for costs and use.
const UI := preload("res://src/ui/action_book_ui.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const TechniquesPanel := preload("res://src/ui/techniques_panel.gd")
const PANEL_SIZE := Vector2(716, 636)
const RESERVED_RIGHT_RAIL := 96.0
const GROUP_ORDER: Array[String] = ["Healing", "Defense", "Offense", "Support", "Utility"]
const EFFECT_GROUPS := {
	"heal": "Health", "regeneration": "Health", "dispel": "Health",
	"mana_restore": "Health",
	"heat_bolt": "Attack", "cold_bolt": "Attack", "radiation_bolt": "Attack",
	"disrupt": "Attack", "cripple": "Attack", "expose_magic": "Attack",
	"expose_heat": "Attack", "expose_cold": "Attack", "expose_radiation": "Attack",
	"poison": "Attack",
	"harm": "Attack",
	"life_drain": "Attack",
	"mana_drain": "Attack",
	"shield": "Defense",
	"magic_protection": "Defense",
	"magic_immunity": "Defense",
	"heat_protection": "Defense",
	"cold_protection": "Defense",
	"radiation_protection": "Defense",
	"element_ward": "Defense",
}

## EL dims what you cannot cast rather than hiding it, so it can still be
## clicked and read.
const BLOCKED_ALPHA := 0.45
const ICON_SIZE := Vector2(36.0, 36.0)
const TARGET_COLUMNS: Array[String] = ["self", "target", "allies", "burst"]
const EFFECT_COLUMN_WIDTH := 148.0
const TARGET_COLUMN_WIDTH := 44.0
const SpellButton := preload("res://src/ui/prepared_spell_button.gd")
const EffectPreview := preload("res://src/ui/spell_effect_preview.gd")
const EFFECT_LABELS := {
	"harm": "Magic Damage", "heat_bolt": "Fire Damage", "cold_bolt": "Frost Damage",
	"radiation_bolt": "Radiation Damage", "mana_drain": "Ether Drain",
	"mana_restore": "Restore Ether",
	"invisibility": "Conceal", "magic_protection": "Magic Ward",
	"heat_protection": "Heat Ward", "cold_protection": "Cold Ward",
	"radiation_protection": "Radiation Ward", "element_ward": "Elemental Ward",
	"expose_magic": "Weaken Magic", "expose_heat": "Weaken Heat",
	"expose_cold": "Weaken Cold", "expose_radiation": "Weaken Radiation",
}


var catalog: SpellCatalog
var selected_spell_id := -1
var panel: PanelContainer
var name_label: Label
var description_label: Label
var numbers_label: Label
var knowledge_label: Label
var reagents_label: Label
var reagents_rows: VBoxContainer
var requirements_rows: VBoxContainer
var cast_button: Button
var status_label: Label
var effect_preview
var selected_icon: TextureRect
var favorite_button: Button
var search: LineEdit
var scope_filter: OptionButton
var browser_picker: OptionButton
var power_picker: SpinBox
var slot_picker: OptionButton
var loadout
var requested_power := 1
var current_tab := "magic"
var techniques_panel: VBoxContainer
var _cast: Callable
var _rows: Dictionary = {}
var _groups: Dictionary = {}
var _buttons: Dictionary = {}
var _reasons: Dictionary = {}
var _tab_buttons: Dictionary = {}
var _filter_buttons: Dictionary = {}
var _favorites: Array = []
var _filter := "all"
var _profile := ""
var _empty_label: Label
var _quote_request := ""
var _last_quote: Dictionary = {}
var _assign_button: Button
var _preparation_label: Label
var _prepare_controls: HBoxContainer
var _content_scroll: ScrollContainer
var _info_scroll: ScrollContainer
var _grid_headings: MarginContainer
var _grid_groups: VBoxContainer
var _magic_page: VBoxContainer
var _body: HBoxContainer
var _browser: VBoxContainer
var _inspector: PanelContainer
var _dragger: WindowDrag
var _item_atlas := ItemAtlas.new()
var _compact := false
var _short := false
var _hero: HBoxContainer
var _details_column: VBoxContainer
var _power_row: HBoxContainer

func _ready() -> void:
	name = "SpellsLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_item_atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	_build()
	AppState.magic_state_received.connect(_quote_state)
	AppState.state_changed.connect(_on_state_changed)
	get_viewport().size_changed.connect(_fit_panel)

func configure(value: SpellCatalog, cast: Callable) -> void:
	catalog = value
	_cast = cast
	_populate()
	sync()

func set_loadout(value) -> void:
	loadout = value
	techniques_panel.set_loadout(value)
	loadout.changed.connect(_on_loadout_changed)
	_restore_preferences()
	_refresh_preparation()

func _on_loadout_changed() -> void:
	if _profile != loadout.profile:
		_restore_preferences()
		search.clear()
		_last_quote.clear()
		selected_spell_id = -1
		_filter_spells()
	_refresh_preparation()

func _restore_preferences() -> void:
	if loadout == null: return
	_profile = loadout.profile
	var preferences: Dictionary = loadout.book_preferences.get("magic", {})
	_favorites = preferences.get("favorites", []).duplicate()
	set_filter(str(preferences.get("filter", "all")), false)

func _save_preferences() -> void:
	if loadout == null: return
	loadout.book_preferences["magic"] = {"filter": _filter, "favorites": _favorites.duplicate()}
	loadout.save_book_preferences()

func reserve_bottom_hud(control: Control) -> void:
	_dragger.bottom_hud = control
	control.item_rect_changed.connect(_fit_panel)
	_fit_panel()

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	panel.visible = not panel.visible
	if panel.visible:
		panel.move_to_front()
		sync()
		_fit_panel()

func close() -> void:
	panel.hide()

func toggle_techniques() -> void:
	if panel.visible and current_tab == "techniques": close()
	else: open_tab("techniques")

func open_tab(tab: String) -> void:
	set_tab(tab)
	if not panel.visible: toggle()
	else: panel.move_to_front()

func set_tab(tab: String) -> void:
	current_tab = "techniques" if tab == "techniques" else "magic"
	_magic_page.visible = current_tab == "magic"
	techniques_panel.visible = current_tab == "techniques"
	for key in _tab_buttons:
		(_tab_buttons[key] as Button).set_pressed_no_signal(key == current_tab)
	if current_tab == "techniques": techniques_panel.sync()
	else: sync()

func edit_prepared_slot(index: int) -> void:
	if loadout == null or index < 0 or index >= loadout.slots.size(): return
	var entry: Dictionary = loadout.slots[index]
	if not str(entry.get("technique", "")).is_empty():
		open_tab("techniques")
		techniques_panel.edit_slot(index, str(entry.technique))
		return
	open_tab("magic")
	slot_picker.select(index)
	search.clear()
	scope_filter.select(0)
	set_filter("all")
	_filter_spells()
	if int(entry.id) >= 0:
		_on_spell_pressed(int(entry.id))
		requested_power = int(entry.power)
		power_picker.set_value_no_signal(requested_power)
		_quote_request = ""
		_last_quote.clear()
		_refresh_details()

func group_of(spell_id: int) -> String:
	if catalog == null: return "Utility"
	var effect := catalog.effect_for(spell_id)
	if effect in ["blink", "transmute", "recall"]: return "Utility"
	return str({"Health": "Healing", "Defense": "Defense", "Attack": "Offense"}.get(EFFECT_GROUPS.get(effect, "General"), "Support"))

## Library placement never changes the spell's real scope or targeting.
func column_for(spell_id: int) -> String:
	var scope := str(catalog.spell(spell_id).get("scope", "self"))
	return scope if scope in TARGET_COLUMNS else "self"

func _on_state_changed(path: StringName) -> void:
	if path in [&"spells", &"stats", &"inventory", &"knowledge", &"spell_power"]:
		_quote_request = ""
		_last_quote.clear()
		sync()

func sync() -> void:
	if catalog == null: return
	_reasons.clear()
	for id: int in catalog.spell_ids():
		var reasons := catalog.unavailable_reasons(id, AppState.known_knowledge, AppState.stats, AppState.inventory)
		_reasons[id] = reasons
		var button: Button = _buttons.get(id)
		if button != null:
			UI.icon_availability(button, reasons.is_empty())
			button.tooltip_text = "%s\n%s" % [catalog.spell(id).name, str(catalog.spell(id).get("scope", "self")).capitalize()]
			if not reasons.is_empty(): button.tooltip_text += "\n" + "\n".join(reasons)
	if panel.visible and current_tab == "magic":
		_filter_spells()
		_refresh_details()

func set_filter(value: String, save := true) -> void:
	_filter = value if value in _filter_buttons else "all"
	for key in _filter_buttons:
		(_filter_buttons[key] as Button).set_pressed_no_signal(key == _filter)
	if save: _save_preferences()
	_filter_spells()

func _toggle_favorite() -> void:
	if selected_spell_id < 0: return
	if selected_spell_id in _favorites: _favorites.erase(selected_spell_id)
	else: _favorites.append(selected_spell_id)
	_save_preferences()
	_filter_spells()
	_refresh_details()

func _matches(id: int) -> bool:
	var spell := catalog.spell(id)
	var scope := str(spell.get("scope", "self"))
	var scopes := ["", "self", "target", "allies", "burst", "utility"]
	var wanted: String = scopes[clampi(scope_filter.selected, 0, 5)]
	if not wanted.is_empty():
		if wanted == "utility" and scope in TARGET_COLUMNS: return false
		if wanted != "utility" and scope != wanted: return false
	var query := search.text.strip_edges().to_lower()
	var effect := catalog.effect_for(id)
	var haystack := "%s %s %s %s" % [spell.name, effect, spell.get("damage_type", ""), EFFECT_LABELS.get(effect, effect.capitalize())]
	if not query.is_empty() and not query in haystack.to_lower(): return false
	if _filter == "ready" and not (_reasons.get(id, []) as Array).is_empty(): return false
	if _filter == "learned" and not catalog.knows(id, AppState.known_knowledge): return false
	if _filter == "favorites" and id not in _favorites: return false
	return true

func _filter_spells() -> void:
	if catalog == null: return
	for id: int in _buttons:
		(_buttons[id] as Button).visible = _matches(id)
	var any_matches := false
	for row: HBoxContainer in _rows.values():
		var row_visible := false
		for target: String in TARGET_COLUMNS:
			var cell := row.get_node("%sCell" % target.capitalize()) as VBoxContainer
			var occupied := false
			for child in cell.get_children():
				if child is Button: occupied = occupied or child.visible
			(cell.get_node("Empty") as Label).visible = not occupied
			row_visible = row_visible or occupied
		row.visible = row_visible
		any_matches = any_matches or row_visible
	for section: VBoxContainer in _groups.values():
		var occupied := false
		for child in section.get_children():
			if child is HBoxContainer: occupied = occupied or child.visible
		section.visible = occupied
	_empty_label.visible = not any_matches
	# Preserve the family when a scope/search changes its visible variant.
	if selected_spell_id >= 0 and not (_buttons[selected_spell_id] as Button).visible:
		var family := catalog.effect_for(selected_spell_id)
		selected_spell_id = -1
		for id: int in _buttons:
			if (_buttons[id] as Button).visible and catalog.effect_for(id) == family:
				_on_spell_pressed(id)
				break
	if selected_spell_id < 0:
		for id: int in _buttons:
			if (_buttons[id] as Button).visible:
				_on_spell_pressed(id)
				break
	for id: int in _buttons:
		(_buttons[id] as Button).set_pressed_no_signal(id == selected_spell_id)
	if selected_spell_id < 0: _refresh_details()
	_refresh_preparation()

func _on_family_pressed(effect: String) -> void:
	for id: int in _buttons:
		if catalog.effect_for(id) == effect and (_buttons[id] as Button).visible:
			_on_spell_pressed(selected_spell_id if selected_spell_id >= 0 and catalog.effect_for(selected_spell_id) == effect and (_buttons[selected_spell_id] as Button).visible else id)
			return

func _on_spell_pressed(id: int) -> void:
	var replay := selected_spell_id == id
	if not _buttons.has(id): return
	selected_spell_id = id
	_quote_request = ""
	_last_quote.clear()
	if loadout != null: requested_power = loadout.power_for(id)
	power_picker.set_value_no_signal(requested_power)
	for key in _buttons: (_buttons[key] as Button).set_pressed_no_signal(key == id)
	_info_scroll.scroll_vertical = 0
	_refresh_details()
	if replay: effect_preview.replay()
	_refresh_preparation()

func _set_status(text: String, ready: bool) -> void:
	status_label.text = ("✓ " if ready else "× ") + text
	TextColors.bind(status_label, "spell_ready" if ready else "spell_blocked")
	cast_button.disabled = not ready

func _refresh_details() -> void:
	UI.clear(reagents_rows)
	UI.clear(requirements_rows)
	if selected_spell_id < 0 or catalog == null:
		name_label.text = "Select a spell"
		description_label.text = "Select an icon to inspect its target, cost and requirements."
		numbers_label.text = ""
		knowledge_label.text = ""
		reagents_label.text = ""
		selected_icon.texture = null
		favorite_button.disabled = true
		status_label.text = ""
		cast_button.disabled = true
		effect_preview.set_spell({}, requested_power)
		return
	var definition := catalog.spell(selected_spell_id)
	name_label.text = str(definition.name)
	TextColors.bind(name_label, "spell_text")
	selected_icon.texture = catalog.icon_for(selected_spell_id)
	description_label.text = str(definition.get("description", ""))
	description_label.tooltip_text = description_label.text
	favorite_button.disabled = false
	favorite_button.set_pressed_no_signal(selected_spell_id in _favorites)
	favorite_button.text = "★" if selected_spell_id in _favorites else "☆"
	favorite_button.tooltip_text = "Remove favorite" if selected_spell_id in _favorites else "Add favorite"
	effect_preview.set_spell(definition, requested_power)
	var limit: Dictionary = AppState.spell_power.get(catalog.effect_for(selected_spell_id), {})
	power_picker.max_value = maxi(requested_power, maxi(1, int(limit.get("limit", 10))))
	numbers_label.text = "%s · Base ether %d" % [str(definition.get("scope", "self")).capitalize(), int(definition.get("mana", 0))]
	var magic := int(AppState.stats.get("magic", 0))
	var level := int(definition.get("level", 0))
	UI.requirement(requirements_rows, "Magic %d" % level, "Current %d" % magic, magic >= level)
	var tome := catalog.knowledge_for(selected_spell_id)
	var known := catalog.knows(selected_spell_id, AppState.known_knowledge)
	knowledge_label.text = tome if not tome.is_empty() else "Every mage knows this"
	TextColors.bind(knowledge_label, "spell_ready" if known else "spell_blocked")
	knowledge_label.tooltip_text = "Known" if known else "Read this tome to learn the spell."
	# Passed level/knowledge checks stay available in the tooltip; the chosen
	# design prioritizes consumables over repeating satisfied prerequisites.
	requirements_rows.visible = magic < level and not _short
	knowledge_label.visible = not known and not _short
	name_label.tooltip_text = "Magic %d (current %d)\n%s" % [level, magic, knowledge_label.text]
	reagents_label.text = "Reagents required"
	for reagent: Dictionary in definition.get("reagents", []):
		var quantity := int(reagent.get("quantity", 0))
		if quantity <= 0: continue # Power-dependent anchors come from the quote.
		_add_reagent(reagent, quantity, catalog.reagent_quantity(reagent, AppState.inventory))
	if reagents_rows.get_child_count() == 0: UI.requirement(reagents_rows, "None", "", true)
	var reasons: Array = _reasons.get(selected_spell_id, [])
	_set_status("Ready" if reasons.is_empty() else str(reasons[0]), reasons.is_empty())
	cast_button.text = "Cast" if _short else "Cast " + str(definition.name)
	cast_button.tooltip_text = "Cast " + str(definition.name)
	if AppState.authenticated:
		var token := "%d:%d" % [selected_spell_id, requested_power]
		if token != _quote_request:
			_quote_request = token
			status_label.text = "Checking cost and requirements…"
			TextColors.bind(status_label, "spell_muted")
			cast_button.disabled = true
			Network.magic_request({"op": "preview", "id": selected_spell_id, "power": requested_power})
		elif not _last_quote.is_empty():
			_quote_state(_last_quote)

func _add_reagent(reagent: Dictionary, required: int, have: int) -> void:
	var title := str(reagent.get("name", SpellCatalog.reagent_name(reagent)))
	var image := int(reagent.get("image_id", -1))
	if image < 0 and selected_spell_id >= 0:
		for candidate: Dictionary in catalog.spell(selected_spell_id).get("reagents", []):
			if str(candidate.get("name", "")) == title:
				image = int(candidate.get("image_id", -1))
	var row := UI.requirement(reagents_rows, "%s ×%d" % [title, required], "Have %d" % have, have >= required, _item_atlas.icon_for(image))
	row.set_meta("reagent", {"name": title, "required": required, "have": have})

func _quote_state(data: Dictionary) -> void:
	if data.get("kind") != "preview" or int(data.get("id", -1)) != selected_spell_id or int(data.get("requested", 0)) != requested_power: return
	_last_quote = data.duplicate(true)
	effect_preview.set_spell(catalog.spell(selected_spell_id), int(data.get("power", 1)))
	numbers_label.text = "%s · Power %d / %d · Ether %d" % [str(catalog.spell(selected_spell_id).get("scope", "self")).capitalize(), int(data.get("power", 1)), int(data.get("limit", 1)), int(data.get("mana", 0))]
	UI.clear(reagents_rows)
	for reagent: Dictionary in data.get("reagents", []):
		if int(reagent.get("quantity", 0)) > 0:
			_add_reagent(reagent, int(reagent.quantity), int(reagent.get("have", 0)))
	if reagents_rows.get_child_count() == 0: UI.requirement(reagents_rows, "None", "", true)
	if not str(data.get("focus", "")).is_empty():
		UI.requirement(reagents_rows, str(data.focus), "Focus", true)
	var ready := bool(data.get("ready", false))
	_set_status("Ready" if ready else str(data.get("reason", "Unavailable")), ready)

func _on_cast_pressed() -> void:
	if cast_button.disabled or selected_spell_id < 0 or not _cast.is_valid(): return
	_cast.call(selected_spell_id)
	if loadout != null: close()

func _refresh_preparation() -> void:
	if _assign_button == null: return
	_assign_button.disabled = selected_spell_id < 0 or loadout == null
	_prepare_controls.visible = loadout != null
	if selected_spell_id < 0 or catalog == null:
		_preparation_label.text = ""
		return
	_preparation_label.text = "Slot %d · %s · Power %d" % [slot_picker.selected + 1, catalog.spell(selected_spell_id).name, requested_power]
	_preparation_label.tooltip_text = _preparation_label.text

func _make_effect_row(effect: String, heading := false) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.name = "TargetHeadings" if heading else effect.to_pascal_case() + "EffectRow"
	row.add_theme_constant_override("separation", 0)
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var title := UI.label("Effect" if heading else str(EFFECT_LABELS.get(effect, effect.capitalize())), 13)
	title.name = "EffectLabel"
	title.custom_minimum_size.x = EFFECT_COLUMN_WIDTH
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title.tooltip_text = title.text
	row.add_child(title)
	for target: String in TARGET_COLUMNS:
		var cell := VBoxContainer.new()
		cell.name = target.capitalize() + "Cell"
		cell.custom_minimum_size.x = TARGET_COLUMN_WIDTH
		cell.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		cell.alignment = BoxContainer.ALIGNMENT_CENTER
		row.add_child(cell)
		var placeholder := UI.label(target.capitalize() if heading else "—", 12)
		placeholder.name = "Empty"
		placeholder.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		if not heading: placeholder.modulate.a = BLOCKED_ALPHA
		cell.add_child(placeholder)
	return row

func _populate() -> void:
	UI.clear(_grid_groups)
	_groups.clear()
	_rows.clear()
	_buttons.clear()
	for group: String in GROUP_ORDER:
		var section := VBoxContainer.new()
		section.name = group + "Spells"
		section.add_theme_constant_override("separation", 2)
		var title := UI.label(group, 13)
		TextColors.bind(title, "book_heading")
		section.add_child(title)
		_grid_groups.add_child(section)
		_groups[group] = section
	if catalog == null: return
	for id: int in catalog.spell_ids():
		var definition := catalog.spell(id)
		var effect := catalog.effect_for(id)
		if effect.is_empty(): effect = str(definition.name)
		if not _rows.has(effect):
			var row := _make_effect_row(effect)
			(_groups[group_of(id)] as VBoxContainer).add_child(row)
			_rows[effect] = row
		var cell := (_rows[effect] as HBoxContainer).get_node(column_for(id).capitalize() + "Cell")
		var button := SpellButton.new()
		button.name = "SpellButton%d" % id
		button.spell_id = id
		button.toggle_mode = true
		button.icon = catalog.icon_for(id)
		UI.icon_button(button)
		button.power_provider = func() -> int: return requested_power if selected_spell_id == id else loadout.power_for(id) if loadout != null else 1
		button.pressed.connect(_on_spell_pressed.bind(id))
		cell.add_child(button)
		_buttons[id] = button
	_filter_spells()

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "SpellsWindow"
	panel.position = Vector2(30, 30)
	panel.add_theme_stylebox_override("panel", UI.box(UI.SURFACE, Color("987542"), 10))
	panel.hide()
	add_child(panel)
	# Wrapped requirements can briefly raise the minimum during a tab switch;
	# refit after the containers have their final width, not just on resize.
	panel.minimum_size_changed.connect(func(): _fit_panel.call_deferred())
	panel.resized.connect(func(): _fit_panel.call_deferred())
	var column := VBoxContainer.new()
	column.name = "SpellsBody"
	column.add_theme_constant_override("separation", 7)
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "SpellsHeader"
	column.add_child(header)
	var title := UI.label("Spells & Techniques", 18)
	title.name = "SpellsTitle"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_button := UI.button("×")
	close_button.name = "SpellsClose"
	close_button.pressed.connect(close)
	header.add_child(close_button)
	_dragger = WindowDrag.attach(panel, header)
	var tabs := HBoxContainer.new()
	column.add_child(tabs)
	for key: String in ["magic", "techniques"]:
		var button := UI.button(key.capitalize())
		button.name = key.capitalize() + "Tab"
		button.toggle_mode = true
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.pressed.connect(set_tab.bind(key))
		tabs.add_child(button)
		_tab_buttons[key] = button
	_magic_page = VBoxContainer.new()
	_magic_page.name = "MagicPage"
	_magic_page.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(_magic_page)
	var toolbar := HBoxContainer.new()
	_magic_page.add_child(toolbar)
	search = LineEdit.new()
	search.name = "SpellSearch"
	search.placeholder_text = "Search spells, effects or damage types…"
	search.add_theme_font_size_override("font_size", 13)
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.text_changed.connect(func(_text: String): _filter_spells())
	toolbar.add_child(search)
	var filters := HBoxContainer.new()
	toolbar.add_child(filters)
	_filter_buttons = UI.filters(filters, set_filter)
	# Kept as a programmatic scope filter for the practice tools; the grid
	# itself chooses variants directly and needs no extra target dropdown.
	scope_filter = OptionButton.new()
	for text: String in ["All targets", "Self", "Target", "Allies", "Burst", "Utility"]: scope_filter.add_item(text)
	scope_filter.hide()
	scope_filter.item_selected.connect(func(_index: int): _filter_spells())
	_magic_page.add_child(scope_filter)
	browser_picker = OptionButton.new()
	browser_picker.add_item("Compare grid")
	browser_picker.hide()
	_magic_page.add_child(browser_picker)
	_body = HBoxContainer.new()
	_body.name = "MagicPanes"
	_body.add_theme_constant_override("separation", 10)
	_body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_magic_page.add_child(_body)
	_browser = VBoxContainer.new()
	_browser.name = "SpellBrowser"
	_browser.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_child(_browser)
	_grid_headings = MarginContainer.new()
	_grid_headings.name = "SpellTargetHeadings"
	_grid_headings.add_child(_make_effect_row("", true))
	_browser.add_child(_grid_headings)
	_content_scroll = UI.scroll("SpellContentScroll")
	_content_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_ALWAYS
	_browser.add_child(_content_scroll)
	var rows := VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_content_scroll.add_child(rows)
	_grid_groups = VBoxContainer.new()
	_grid_groups.name = "SpellGroups"
	_grid_groups.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_child(_grid_groups)
	_empty_label = UI.label("No spells match. Clear search or choose All.", 13, true)
	_empty_label.name = "NoMatchingSpells"
	rows.add_child(_empty_label)
	_grid_headings.add_theme_constant_override("margin_right", int(_content_scroll.get_v_scroll_bar().get_combined_minimum_size().x))
	_build_details()
	var hint := UI.label("Select to inspect · Drag to a quick slot", 12, true)
	TextColors.bind(hint, "book_muted")
	_magic_page.add_child(hint)
	techniques_panel = TechniquesPanel.new()
	techniques_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(techniques_panel)
	techniques_panel.close_requested.connect(close)
	set_tab("magic")
	_fit_panel()

func _build_details() -> void:
	_inspector = PanelContainer.new()
	_inspector.name = "SpellDetails"
	_inspector.add_theme_stylebox_override("panel", UI.box(Color("130f0a"), Color("80623b"), 8))
	_body.add_child(_inspector)
	var column := VBoxContainer.new()
	_details_column = column
	column.add_theme_constant_override("separation", 6)
	_inspector.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	name_label = UI.label("Select a spell", 18, true)
	name_label.name = "SpellName"
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(name_label)
	favorite_button = UI.button("☆")
	favorite_button.toggle_mode = true
	favorite_button.pressed.connect(_toggle_favorite)
	header.add_child(favorite_button)
	_info_scroll = UI.scroll("SpellInfoScroll")
	column.add_child(_info_scroll)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_theme_constant_override("separation", 4)
	_info_scroll.add_child(info)
	_hero = HBoxContainer.new()
	info.add_child(_hero)
	selected_icon = TextureRect.new()
	selected_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	selected_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	selected_icon.custom_minimum_size = Vector2(56, 56)
	_hero.add_child(selected_icon)
	effect_preview = EffectPreview.new()
	effect_preview.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hero.add_child(effect_preview)
	effect_preview.custom_minimum_size = Vector2(120, 72)
	effect_preview.get("_caption").hide()
	description_label = UI.label("", 13, true)
	description_label.max_lines_visible = 3
	description_label.name = "SpellDescription"
	TextColors.bind(description_label, "spell_text")
	info.add_child(description_label)
	numbers_label = UI.label("", 13, true)
	numbers_label.name = "SpellNumbers"
	TextColors.bind(numbers_label, "spell_cost")
	info.add_child(numbers_label)
	requirements_rows = VBoxContainer.new()
	info.add_child(requirements_rows)
	knowledge_label = UI.label("", 12, true)
	knowledge_label.name = "SpellKnowledge"
	info.add_child(knowledge_label)
	reagents_label = UI.label("Reagents required", 13)
	reagents_label.name = "SpellReagents"
	info.add_child(reagents_label)
	reagents_rows = VBoxContainer.new()
	reagents_rows.name = "ReagentRows"
	info.add_child(reagents_rows)
	status_label = UI.label("", 13, true)
	status_label.name = "SpellStatus"
	column.add_child(status_label)
	var power_row := HBoxContainer.new()
	_power_row = power_row
	column.add_child(power_row)
	power_row.add_child(UI.label("Power", 13))
	power_picker = SpinBox.new()
	power_picker.min_value = 1
	power_picker.max_value = 10
	power_picker.custom_minimum_size.x = 100
	power_picker.add_theme_font_size_override("font_size", 13)
	power_picker.value_changed.connect(func(value: float):
		requested_power = int(value)
		if loadout != null and selected_spell_id >= 0: loadout.remember_power(selected_spell_id, requested_power)
		_quote_request = ""
		_last_quote.clear()
		_refresh_details()
		_refresh_preparation())
	power_row.add_child(power_picker)
	cast_button = UI.button("Cast")
	cast_button.name = "CastButton"
	cast_button.clip_text = true
	cast_button.pressed.connect(_on_cast_pressed)
	column.add_child(cast_button)
	_prepare_controls = HBoxContainer.new()
	_prepare_controls.name = "PrepareSpell"
	column.add_child(_prepare_controls)
	slot_picker = UI.slot_picker()
	slot_picker.item_selected.connect(func(_index: int): _refresh_preparation())
	_prepare_controls.add_child(slot_picker)
	_assign_button = UI.button("Assign")
	_assign_button.name = "AssignSpell"
	_assign_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_assign_button.pressed.connect(func():
		if selected_spell_id >= 0 and loadout != null:
			loadout.assign_slot(slot_picker.selected, selected_spell_id, requested_power)
			_preparation_label.text = "Assigned to slot %d" % (slot_picker.selected + 1))
	_prepare_controls.add_child(_assign_button)
	_preparation_label = UI.label("", 11)
	_preparation_label.name = "PreparationSummary"
	_preparation_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	column.add_child(_preparation_label)

func _fit_panel() -> void:
	if panel == null or _dragger == null: return
	var bounds := get_viewport_rect().size
	var bottom := bounds.y - WindowDrag.RESERVED_BOTTOM_BAR
	if is_instance_valid(_dragger.bottom_hud): bottom = minf(bottom, _dragger.bottom_hud.global_position.y)
	var available := Vector2(bounds.x - RESERVED_RIGHT_RAIL - 12, bottom - 12).max(Vector2.ONE)
	_compact = available.x < 700
	var short := available.y < 500
	if short != _short:
		_short = short
		cast_button.reparent(_power_row if short else _details_column)
		if not short: _details_column.move_child(cast_button, _power_row.get_index() + 1)
		cast_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hero.visible = not short
	description_label.visible = not short
	_preparation_label.visible = not short
	if short:
		requirements_rows.hide()
		knowledge_label.hide()
		cast_button.text = "Cast"
	_inspector.custom_minimum_size.x = 244 if _compact else 288
	for row: HBoxContainer in _rows.values():
		(row.get_node("EffectLabel") as Label).custom_minimum_size.x = 110 if _compact else EFFECT_COLUMN_WIDTH
	var headings := _grid_headings.get_child(0) as HBoxContainer
	(headings.get_node("EffectLabel") as Label).custom_minimum_size.x = 110 if _compact else EFFECT_COLUMN_WIDTH
	techniques_panel.set_compact(_compact)
	techniques_panel.set_short(short)
	panel.custom_minimum_size = PANEL_SIZE.min(available)
	panel.size = panel.custom_minimum_size
	_dragger.clamp_into_view()
