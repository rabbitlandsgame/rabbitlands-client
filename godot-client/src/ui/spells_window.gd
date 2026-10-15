extends Control
## The spell book: effect rows and target columns, within the health,
## general, attack and defense groups, with reasons a cast would fail.
##
## Everything on it is a rendering of what the client honestly knows. The
## definitions are the client's own spell catalog; the tomes the player has
## read, their magic level, their mana and their reagents are the server's
## state as it last arrived in `AppState`. A spell the client can see no way
## to cast is dimmed and its first blocking reason is written beside its
## name, the way the legacy client dimmed and annotated its own - but the
## window never decides whether a cast succeeds. Pressing Cast only asks;
## the server answers, because the knowledge, the mana and the inventory are
## all its to judge.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

const PANEL_SIZE := Vector2(560.0, 600.0)
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0

## The four Eternal Lands groups, in the order the legacy window draws them.
const GROUP_ORDER: Array[String] = ["Health", "General", "Attack", "Defense"]
## Which group each catalogued effect belongs to. Anything the table does not
## name - Blinkstep and any other spell with no effect at all - is a General
## spell.
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
const BLOCKED_COLOR := Color(1.0, 0.36, 0.36)
const CASTABLE_COLOR := Color(0.85, 1.0, 0.85)
const ICON_SIZE := Vector2(28.0, 28.0)
const TARGET_COLUMNS: Array[String] = ["self", "target", "allies", "burst", "utility"]
const EFFECT_COLUMN_WIDTH := 164.0
const TARGET_COLUMN_WIDTH := 56.0
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
var selected_spell_id: int = -1

var panel: PanelContainer
var name_label: Label
var description_label: Label
var numbers_label: Label
var knowledge_label: Label
var reagents_label: Label
var cast_button: Button
var effect_preview

var _cast: Callable = Callable()
## Effect key to its row, and group name to its section.
var _rows: Dictionary = {}
var _groups: Dictionary = {}
var _empty_label: Label
## Spell id to its Button, for re-dimming without a rebuild.
var _buttons: Dictionary = {}
## Spell id to the Array[String] of everything blocking a cast, as the
## catalog last computed it from the server's state. Empty means castable
## as far as the client can see.
var _reasons: Dictionary = {}
var search: LineEdit
var scope_filter: OptionButton
var requested_power := 1
var _quote_request := ""
var _last_quote: Dictionary = {}
var loadout
var power_picker: SpinBox
var slot_picker: OptionButton
var browser_picker: OptionButton
var _family_groups: GridContainer
var _family_buttons: Dictionary = {}
var _variant_picker: OptionButton
var _prepare_controls: HBoxContainer
var _content_scroll: ScrollContainer
var _assign_button: Button
var _preparation_label: Label
var _dragger: WindowDrag
var _grid_headings: Control
var _grid_groups: Control

func set_loadout(value) -> void:
	loadout = value
	panel.position = Vector2(30, 35)
	(panel.find_child("SpellScroll", true, false) as ScrollContainer).custom_minimum_size.y = 160
	_prepare_controls.show()
	_preparation_label.show()
	_variant_picker.show()
	browser_picker.show()
	browser_picker.select(1)
	_filter_spells()
	loadout.changed.connect(_refresh_preparation)
	_fit_panel()

func reserve_bottom_hud(control: Control) -> void:
	_dragger.bottom_hud = control
	control.item_rect_changed.connect(func(): _fit_panel.call_deferred())
	_fit_panel()

func edit_prepared_slot(index: int) -> void:
	slot_picker.select(index)
	var entry: Dictionary = loadout.slots[index]
	if int(entry.id) >= 0:
		# Editing a saved variant must not inherit a filter that hides it.
		search.clear()
		scope_filter.select(0)
		_filter_spells()
		_on_spell_pressed(int(entry.id))
		power_picker.value = int(entry.power)
	panel.show()
	panel.move_to_front()
	sync()

func _quote_state(data: Dictionary) -> void:
	if data.get("kind") != "preview" or int(data.get("id", -1)) != selected_spell_id or int(data.get("requested", 0)) != requested_power:
		return
	_last_quote=data.duplicate(true)
	name_label.text = str(catalog.spell(selected_spell_id).get("name", "Spell"))
	name_label.add_theme_color_override("font_color",CASTABLE_COLOR if data.get("ready",false) else BLOCKED_COLOR)
	numbers_label.text = "Power %d / %d allowed · Ether %d" % [int(data.power), int(data.limit), int(data.mana)]
	var parts: Array[String] = []
	for reagent: Dictionary in data.get("reagents", []):
		parts.append("%s %d (have %d)" % [str(reagent.name), int(reagent.quantity), int(reagent.have)])
	reagents_label.text = ", ".join(parts)
	if not str(data.get("focus", "")).is_empty():
		reagents_label.text += "\n%s replaces the anchor with one charge." % str(data.focus)
	if not bool(data.get("ready", false)):
		name_label.text += " — " + str(data.get("reason", "Unavailable"))
	cast_button.disabled = not bool(data.get("ready", false))

func _ready() -> void:
	AppState.magic_state_received.connect(_quote_state)
	name = "SpellsLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	get_viewport().size_changed.connect(_fit_panel)
	AppState.state_changed.connect(_on_state_changed)
	sync()

func configure(spell_catalog: SpellCatalog, cast: Callable) -> void:
	catalog = spell_catalog
	_cast = cast
	_populate()
	sync()

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

## Which of the four groups a spell is drawn under, from its catalogued
## effect alone.
func group_of(spell_id: int) -> String:
	if catalog == null:
		return "General"
	var effect_value: Variant = catalog.spell(spell_id).get("effect", "")
	var effect: String = effect_value if effect_value is String else ""
	return str(EFFECT_GROUPS.get(effect, "General"))

func _on_state_changed(path: StringName) -> void:
	if path == &"spells" or path == &"stats" or path == &"inventory" or path == &"knowledge":
		sync()

## Re-asks the catalog what blocks every spell, dims accordingly and redraws
## the selected details. Everything it reads is the server's last word held
## in AppState; nothing here predicts what the server will actually allow.
func sync() -> void:
	_quote_request = ""
	if not panel.visible or catalog == null:
		return
	_reasons.clear()
	for spell_id: int in catalog.spell_ids():
		var reasons: Array[String] = catalog.unavailable_reasons(
			spell_id, AppState.known_knowledge, AppState.stats, AppState.inventory)
		_reasons[spell_id] = reasons
		var button: Button = _buttons.get(spell_id) as Button
		if button != null:
			button.modulate = Color(1.0, 1.0, 1.0,
				1.0 if reasons.is_empty() else BLOCKED_ALPHA)
	_refresh_details()

func _on_spell_pressed(spell_id: int) -> void:
	var replay_selection := selected_spell_id == spell_id
	selected_spell_id = spell_id
	(panel.find_child("SpellInfoScroll", true, false) as ScrollContainer).scroll_vertical = 0
	for id: int in _buttons:
		(_buttons[id] as Button).set_pressed_no_signal(id == spell_id)
	for effect: String in _family_buttons:
		(_family_buttons[effect] as Button).set_pressed_no_signal(effect == catalog.effect_for(spell_id))
	if loadout != null:
		requested_power = loadout.power_for(spell_id)
		_sync_variant_picker()
		power_picker.set_value_no_signal(requested_power)
	_refresh_details()
	if replay_selection:
		effect_preview.replay()
	_refresh_preparation()

func _sync_variant_picker() -> void:
	_variant_picker.clear()
	if selected_spell_id < 0 or catalog == null: return
	var effect := catalog.effect_for(selected_spell_id)
	for id: int in catalog.spell_ids():
		if catalog.effect_for(id) != effect or not (_buttons[id] as Button).visible: continue
		var definition := catalog.spell(id)
		_variant_picker.add_item("%s · %s" % [definition.name, str(definition.get("scope", "self")).capitalize()], id)
		if id == selected_spell_id: _variant_picker.select(_variant_picker.item_count - 1)

func _refresh_preparation() -> void:
	_assign_button.disabled = selected_spell_id < 0
	if selected_spell_id < 0 or catalog == null:
		_preparation_label.text = "Select a spell to assign to the quick bar."
		return
	var definition := catalog.spell(selected_spell_id)
	_preparation_label.text = "Slot %d: %s · %s · Power %d" % [slot_picker.selected + 1,
		definition.name, str(definition.get("scope", "self")).capitalize(), requested_power]
	_preparation_label.tooltip_text = _preparation_label.text
	_assign_button.tooltip_text = "Assign %s to quick slot %d" % [definition.name, slot_picker.selected + 1]

## The scrolling body absorbs text/list minimum sizes. The title and quick
## slot controls stay on screen even with a long quote or a larger UI scale.
func _fit_panel() -> void:
	if panel == null: return
	var bounds := get_viewport_rect().size
	var bottom := bounds.y - WindowDrag.RESERVED_BOTTOM_BAR
	if is_instance_valid(_dragger.bottom_hud):
		bottom = minf(bottom, _dragger.bottom_hud.global_position.y)
	var available := bounds - Vector2(RESERVED_RIGHT_RAIL + WindowDrag.EDGE_MARGIN * 2,
		bounds.y - bottom + WindowDrag.EDGE_MARGIN * 2)
	var preferred := Vector2(620, 600) if loadout != null else PANEL_SIZE
	panel.custom_minimum_size = preferred.min(available.max(Vector2.ONE))
	panel.size = panel.custom_minimum_size
	_dragger.clamp_into_view()

## Only asks. The server owns the knowledge, the mana and the reagents, so it
## alone decides whether the cast happens.
func _on_cast_pressed() -> void:
	if selected_spell_id >= 0 and _cast.is_valid():
		_cast.call(selected_spell_id)
		if loadout != null: close()

func _refresh_details() -> void:
	cast_button.disabled = selected_spell_id < 0
	if selected_spell_id < 0 or catalog == null:
		name_label.text = "Select a spell"
		name_label.remove_theme_color_override("font_color")
		description_label.text = "Click a spell to read what it does and preview its effect."
		numbers_label.text = ""
		knowledge_label.text = ""
		reagents_label.text = ""
		effect_preview.set_spell({}, requested_power)
		return
	var definition: Dictionary = catalog.spell(selected_spell_id)
	if loadout != null:
		var stated: Dictionary = AppState.spell_power.get(catalog.effect_for(selected_spell_id), {})
		power_picker.max_value = maxi(1, int(stated.get("limit", 10)))
	var title: String = str(definition.get("name", "Spell %d" % selected_spell_id))
	var reasons: Array = _reasons.get(selected_spell_id, []) as Array
	if reasons.is_empty():
		name_label.text = title
		name_label.add_theme_color_override("font_color", CASTABLE_COLOR)
	else:
		name_label.text = "%s (%s)" % [title, str(reasons[0])]
		name_label.add_theme_color_override("font_color", BLOCKED_COLOR)
	description_label.text = str(definition.get("description", ""))
	effect_preview.set_spell(definition, requested_power)
	numbers_label.text = "Magic %d   Base ether %d" % [
		int(definition.get("level", 0)), int(definition.get("mana", 0))]
	knowledge_label.text = _knowledge_line(selected_spell_id)
	reagents_label.text = _reagents_line(definition)
	if AppState.authenticated:
		var token := "%d:%d" % [selected_spell_id, requested_power]
		if token != _quote_request:
			_quote_request = token
			cast_button.disabled = true
			Network.magic_request({"op":"preview", "id":selected_spell_id, "power":requested_power})
		elif not _last_quote.is_empty():
			_quote_state(_last_quote)

## The tome the spell's family is learned from, marked with a leading "!"
## while it is unread - or that every mage already knows it. What has been
## read is the server's knowledge list in AppState.
func _knowledge_line(spell_id: int) -> String:
	var tome: String = catalog.knowledge_for(spell_id)
	if tome.is_empty():
		return "Knowledge: every mage knows this"
	return "Knowledge: %s%s" % [
		"" if catalog.knows(spell_id, AppState.known_knowledge) else "!", tome]

## The required reagents by the name the server gives the item, with a
## leading "!" on any the backpack is short of - the same mark the knowledge
## line uses, so both lines answer "what am I missing" the same way. What is
## carried is the server's inventory in AppState.
func _reagents_line(definition: Dictionary) -> String:
	var parts: Array[String] = []
	var reagents_value: Variant = definition.get("reagents", [])
	if reagents_value is Array:
		for raw_reagent: Variant in reagents_value as Array:
			if raw_reagent is Dictionary:
				var reagent: Dictionary = raw_reagent as Dictionary
				var required: int = int(reagent.get("quantity", 0))
				# An anchor the book lists at 0 is free until Power 4.
				var label: String = ("%s from Power 4" % SpellCatalog.reagent_name(reagent)
					if required == 0 else "%s x%d" % [SpellCatalog.reagent_name(reagent), required])
				if catalog.reagent_quantity(reagent, AppState.inventory) < required:
					label = "!" + label
				parts.append(label)
	return "Reagents: " + (", ".join(parts) if not parts.is_empty() else "none")

## Each effect owns a row. Target cells stay in place even when empty or
## filtered, so comparing variants never changes the meaning of a column.
func _populate() -> void:
	for group: String in GROUP_ORDER:
		var section: VBoxContainer = _groups[group] as VBoxContainer
		for child: Node in section.get_children():
			if child is Label:
				continue
			section.remove_child(child)
			child.free()
	_rows.clear()
	_buttons.clear()
	_family_buttons.clear()
	for child in _family_groups.get_children():
		_family_groups.remove_child(child)
		child.free()
	if catalog == null:
		return
	var grouped: Dictionary = {}
	for group: String in GROUP_ORDER:
		grouped[group] = []
	for spell_id: int in catalog.spell_ids():
		(grouped[group_of(spell_id)] as Array).append(spell_id)
	for group: String in GROUP_ORDER:
		var ids: Array = grouped[group] as Array
		ids.sort_custom(func(a: Variant, b: Variant) -> bool:
			var level_a: int = int(catalog.spell(int(a)).get("level", 0))
			var level_b: int = int(catalog.spell(int(b)).get("level", 0))
			return level_a < level_b if level_a != level_b else int(a) < int(b))
		for raw_id: Variant in ids:
			var spell_id: int = int(raw_id)
			var definition := catalog.spell(spell_id)
			var effect := str(definition.get("effect", ""))
			if effect.is_empty():
				effect = str(definition.get("name", "Spell %d" % spell_id))
			if not _rows.has(effect):
				var row := _make_effect_row(effect)
				(_groups[group] as VBoxContainer).add_child(row)
				_rows[effect] = row
				var family := Button.new()
				family.text = str(EFFECT_LABELS.get(effect, effect.capitalize()))
				family.icon = catalog.icon_for(spell_id)
				family.expand_icon = true
				family.add_theme_constant_override("icon_max_width", 24)
				family.custom_minimum_size.y = 32
				family.alignment = HORIZONTAL_ALIGNMENT_LEFT
				family.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				family.toggle_mode = true
				family.pressed.connect(_on_family_pressed.bind(effect))
				_family_groups.add_child(family)
				_family_buttons[effect] = family
			var scope := str(definition.get("scope", "self"))
			var target := scope if scope in TARGET_COLUMNS else "utility"
			var cell := (_rows[effect] as HBoxContainer).get_node(
				"%sCell" % target.capitalize()) as VBoxContainer
			(cell.get_node("Empty") as Label).hide()
			var button := SpellButton.new()
			button.spell_id = spell_id
			button.toggle_mode = true
			button.power_provider = func() -> int: return requested_power if selected_spell_id == spell_id else (loadout.power_for(spell_id) if loadout != null else 1)
			button.name = "SpellButton%d" % spell_id
			button.tooltip_text = str(definition.get("name", ""))
			if target == "utility":
				button.tooltip_text += "\nTarget: " + scope.capitalize()
			button.icon = catalog.icon_for(spell_id)
			button.expand_icon = true
			button.custom_minimum_size = ICON_SIZE
			button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
			button.pressed.connect(_on_spell_pressed.bind(spell_id))
			cell.add_child(button)
			_buttons[spell_id] = button
	_filter_spells()

func _on_family_pressed(effect: String) -> void:
	if selected_spell_id >= 0 and catalog.effect_for(selected_spell_id) == effect and (_buttons[selected_spell_id] as Button).visible:
		_on_spell_pressed(selected_spell_id)
		return
	for spell_id: int in catalog.spell_ids():
		if catalog.effect_for(spell_id) == effect and (_buttons[spell_id] as Button).visible:
			_on_spell_pressed(spell_id)
			return

func _make_effect_row(effect: String, heading := false) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.name = "TargetHeadings" if heading else "%sEffectRow" % effect.to_pascal_case()
	var label := Label.new()
	label.name = "EffectLabel"
	label.text = "Effect" if heading else str(EFFECT_LABELS.get(effect, effect.capitalize()))
	label.tooltip_text = label.text
	label.custom_minimum_size.x = EFFECT_COLUMN_WIDTH
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	row.add_child(label)
	for target: String in TARGET_COLUMNS:
		var cell := VBoxContainer.new()
		cell.name = "%sCell" % target.capitalize()
		cell.custom_minimum_size.x = TARGET_COLUMN_WIDTH
		cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		cell.alignment = BoxContainer.ALIGNMENT_CENTER
		row.add_child(cell)
		var placeholder := Label.new()
		placeholder.name = "Empty"
		placeholder.text = target.capitalize() if heading else "—"
		placeholder.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		if not heading:
			placeholder.modulate.a = BLOCKED_ALPHA
		cell.add_child(placeholder)
	return row

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "SpellsWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	# Left of centre, where the legacy client keeps its own spell window.
	panel.position = Vector2(
		(1280.0 - RESERVED_RIGHT_RAIL - PANEL_SIZE.x) * 0.5 - 110.0, 120.0)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)
	panel.minimum_size_changed.connect(func(): _fit_panel.call_deferred())

	var column := VBoxContainer.new()
	column.name = "SpellsBody"
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "SpellsHeader"
	column.add_child(header)
	_dragger = WindowDrag.attach(panel, header)
	var title := Label.new()
	title.name = "SpellsTitle"
	title.text = "Spells"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	header.add_child(title)
	var close_button := Button.new()
	close_button.name = "SpellsClose"
	close_button.text = "X"
	close_button.pressed.connect(close)
	header.add_child(close_button)
	_build_details(column)
	_variant_picker = OptionButton.new()
	_variant_picker.name = "SpellVariant"
	_variant_picker.tooltip_text = "Choose which target variant of this spell to prepare."
	_variant_picker.hide()
	_variant_picker.item_selected.connect(func(index: int): _on_spell_pressed(_variant_picker.get_item_id(index)))
	_variant_picker.clip_text = true
	column.add_child(_variant_picker)
	_content_scroll = ScrollContainer.new()
	_content_scroll.name = "SpellContentScroll"
	_content_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(_content_scroll)
	var content := VBoxContainer.new()
	content.name = "SpellContent"
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_content_scroll.add_child(content)

	search = LineEdit.new()
	search.name = "SpellSearch"
	search.placeholder_text = "Search spells, effects or damage types"
	content.add_child(search)
	scope_filter = OptionButton.new()
	for option: String in ["All targets", "Self", "Target", "Allies", "Burst", "Utility"]:
		scope_filter.add_item(option)
	content.add_child(scope_filter)
	search.text_changed.connect(func(_text: String) -> void: _filter_spells())
	scope_filter.item_selected.connect(func(_index: int) -> void: _filter_spells())
	browser_picker = OptionButton.new()
	browser_picker.name = "SpellBrowserMode"
	browser_picker.add_item("Compare grid")
	browser_picker.add_item("Spell families")
	browser_picker.hide()
	browser_picker.item_selected.connect(func(_index: int): _filter_spells())
	content.add_child(browser_picker)
	var headings := MarginContainer.new()
	headings.name = "SpellTargetHeadings"
	_grid_headings = headings
	content.add_child(headings)
	headings.add_child(_make_effect_row("", true))
	var scroll := ScrollContainer.new()
	scroll.name = "SpellScroll"
	scroll.custom_minimum_size.y = 230
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_ALWAYS
	content.add_child(scroll)
	# Reserve the same scrollbar gutter in the fixed headings as in the rows.
	headings.add_theme_constant_override("margin_right",
		int(scroll.get_v_scroll_bar().get_combined_minimum_size().x))
	var groups := VBoxContainer.new()
	groups.name = "SpellGroups"
	groups.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var browser_body := VBoxContainer.new()
	browser_body.name = "SpellBrowser"
	browser_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(browser_body)
	browser_body.add_child(groups)
	_grid_groups = groups
	_family_groups = GridContainer.new()
	_family_groups.columns = 2
	_family_groups.name = "SpellFamilies"
	_family_groups.hide()
	browser_body.add_child(_family_groups)
	for group: String in GROUP_ORDER:
		var section := VBoxContainer.new()
		section.name = "%sSpells" % group
		groups.add_child(section)
		var label := Label.new()
		label.name = "%sSpellsLabel" % group
		label.text = "%s Spells" % group
		section.add_child(label)
		_groups[group] = section
	_empty_label = Label.new()
	_empty_label.name = "NoMatchingSpells"
	_empty_label.text = "No spells match your search."
	_empty_label.hide()
	browser_body.add_child(_empty_label)
	_preparation_label = Label.new()
	_preparation_label.name = "PreparationSummary"
	_preparation_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_preparation_label.hide()
	column.add_child(_preparation_label)
	_prepare_controls = HBoxContainer.new()
	_prepare_controls.name = "PrepareSpell"
	_prepare_controls.hide()
	column.add_child(_prepare_controls)
	power_picker = SpinBox.new()
	power_picker.custom_minimum_size.x = 128
	power_picker.prefix = "Power "
	power_picker.min_value = 1
	power_picker.max_value = 10
	power_picker.value_changed.connect(func(value: float):
		requested_power = int(value)
		if selected_spell_id >= 0:
			loadout.remember_power(selected_spell_id, requested_power)
			_quote_request = ""
			_refresh_details()
		_refresh_preparation())
	_prepare_controls.add_child(power_picker)
	slot_picker = OptionButton.new()
	for index in range(12): slot_picker.add_item("Slot %d" % (index + 1))
	slot_picker.item_selected.connect(func(_index: int): _refresh_preparation())
	_prepare_controls.add_child(slot_picker)
	_assign_button = Button.new()
	_assign_button.name = "AssignSpell"
	_assign_button.text = "Assign to slot"
	_assign_button.disabled = true
	_assign_button.pressed.connect(func():
		if selected_spell_id >= 0:
			loadout.assign_slot(slot_picker.selected, selected_spell_id, requested_power)
			_preparation_label.text = "Assigned " + _preparation_label.text)
	_prepare_controls.add_child(_assign_button)

	cast_button = Button.new()
	cast_button.name = "CastButton"
	cast_button.text = "Cast"
	cast_button.disabled = true
	cast_button.size_flags_horizontal = Control.SIZE_SHRINK_END
	cast_button.pressed.connect(_on_cast_pressed)
	column.add_child(cast_button)
	_fit_panel()

## Keep the selected spell visible while its browser scrolls independently.
## Long requirements can scroll within the card without pushing it offscreen.
func _build_details(column: VBoxContainer) -> void:
	var details := HBoxContainer.new()
	details.name = "SpellDetails"
	details.add_theme_constant_override("separation", 12)
	column.add_child(details)
	var info_scroll := ScrollContainer.new()
	info_scroll.name = "SpellInfoScroll"
	info_scroll.custom_minimum_size.y = 180
	info_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	details.add_child(info_scroll)
	var info := VBoxContainer.new()
	info.name = "SpellInfo"
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_theme_constant_override("separation", 6)
	info_scroll.add_child(info)
	name_label = Label.new()
	name_label.name = "SpellName"
	name_label.add_theme_font_size_override("font_size", 18)
	description_label = Label.new()
	description_label.name = "SpellDescription"
	numbers_label = Label.new()
	numbers_label.name = "SpellNumbers"
	knowledge_label = Label.new()
	knowledge_label.name = "SpellKnowledge"
	reagents_label = Label.new()
	reagents_label.name = "SpellReagents"
	for label: Label in [name_label, description_label, numbers_label, knowledge_label, reagents_label]:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		info.add_child(label)
	effect_preview = EffectPreview.new()
	details.add_child(effect_preview)

func _filter_spells() -> void:
	if catalog == null: return
	var families := loadout != null and browser_picker.selected == 1
	_grid_headings.visible = not families
	_grid_groups.visible = not families
	_family_groups.visible = families
	var selected := "" if scope_filter.selected <= 0 else TARGET_COLUMNS[scope_filter.selected - 1]
	var query := search.text.strip_edges().to_lower()
	for spell_id: int in catalog.spell_ids():
		var spell := catalog.spell(spell_id)
		var scope := str(spell.get("scope", "self"))
		var target := scope if scope in TARGET_COLUMNS else "utility"
		var effect := str(spell.get("effect", ""))
		var scope_matches := selected.is_empty() or target == selected
		var haystack := "%s %s %s %s" % [spell.name, effect, spell.get("damage_type", ""), EFFECT_LABELS.get(effect, effect.capitalize())]
		(_buttons[spell_id] as Button).visible = scope_matches and (query.is_empty() or haystack.to_lower().contains(query))

	var any_matches := false
	for row: HBoxContainer in _rows.values():
		var any_visible := false
		for target: String in TARGET_COLUMNS:
			var cell := row.get_node("%sCell" % target.capitalize()) as VBoxContainer
			var cell_visible := false
			for child: Node in cell.get_children():
				if child is Button:
					cell_visible = cell_visible or (child as Button).visible
			(cell.get_node("Empty") as Label).visible = not cell_visible
			any_visible = any_visible or cell_visible
		row.visible = any_visible
		var effect_key: String = _rows.find_key(row)
		(_family_buttons[effect_key] as Button).visible = any_visible
		any_matches = any_matches or any_visible
	for group: String in GROUP_ORDER:
		var section: VBoxContainer = _groups[group]
		var any_visible := false
		for child: Node in section.get_children():
			if child is HBoxContainer:
				any_visible = any_visible or (child as Control).visible
		section.visible = any_visible
	_empty_label.visible = not any_matches
	# A Burst-only browser must never assign/cast the hidden Target variant.
	if selected_spell_id >= 0 and not (_buttons[selected_spell_id] as Button).visible:
		var effect := catalog.effect_for(selected_spell_id)
		selected_spell_id = -1
		for id: int in catalog.spell_ids():
			if catalog.effect_for(id) == effect and (_buttons[id] as Button).visible:
				_on_spell_pressed(id)
				break
		if selected_spell_id < 0:
			for button: Button in _buttons.values(): button.set_pressed_no_signal(false)
			for button: Button in _family_buttons.values(): button.set_pressed_no_signal(false)
			_refresh_details()
	if loadout != null: _sync_variant_picker()
	_refresh_preparation()
