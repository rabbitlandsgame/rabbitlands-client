class_name CreationBasePicker
extends Control
## A modal appearance library. Selection is local until Use this basis emits
## basis_selected; the creation controller owns all model/editor changes.
## Rows: id, portrait_id, label, race_id, race_label, sex, hair_tags, search_text, look.
## Context: optional portrait_manifest_path, filter_options and
## initial_filters {race_id, sex, hair_tag}. setup never opens the popup.

signal basis_selected(id: String)
signal dismissed
signal preview_requested(id: String)

const Portraits := preload("res://src/ui/creation_base_portraits.gd")
const Art := preload("res://src/ui/leaderboard_art.gd")
const EntryStyle := preload("res://src/ui/oldcraft_entry_style.gd")
const TEXT := Color("f0e8d8")
const MUTED := Color("b9b5aa")
const GOLD := Color("d7b574")
const GOLD_DARK := Color("897347")
const FIELD := Color("121419")
const CARD_FOOTER_HEIGHT := 40.0
const MIN_PORTRAIT_HEIGHT := 96.0

var panel: PanelContainer
var search: LineEdit
var race_filter: OptionButton
var sex_filter: OptionButton
var hair_filter: OptionButton
var clear_filters: Button
var scroll: ScrollContainer
var grid: GridContainer
var result_count: Label
var empty_message: Label
var selected_label: Label
var use_button: Button
var cancel_button: Button
var close_button: Button
var portraits := Portraits.new()

var _rows: Array[Dictionary] = []
var _visible_rows: Array[Dictionary] = []
var _by_id: Dictionary = {}
var _cards: Dictionary = {}
var _selected_id := ""
var _default_id := ""
var _return_focus: WeakRef
var _last_focus: WeakRef
var _built := false
var _updating := false
var _card_width := 210.0
var _portrait_height := 170.0
var _compact := false
var _title: Label
var _body: VBoxContainer
var _footer: HBoxContainer


func _init() -> void:
	hide()
	mouse_filter = Control.MOUSE_FILTER_STOP


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_ensure_ui()
	resized.connect(_layout)
	get_viewport().gui_focus_changed.connect(_on_focus_changed)
	_layout()


func setup(rows: Array, default_id: String = "", context: Dictionary = {}) -> void:
	_ensure_ui()
	_rows.clear()
	_by_id.clear()
	for raw: Variant in rows:
		if not raw is Dictionary:
			continue
		var row: Dictionary = raw.duplicate(true)
		var id := str(row.get("id", ""))
		if id.is_empty() or _by_id.has(id):
			continue
		_rows.append(row)
		_by_id[id] = row
	_default_id = default_id if _by_id.has(default_id) else ""
	_selected_id = _default_id
	portraits.configure(str(context.get("portrait_manifest_path", Portraits.MANIFEST_PATH)))
	_updating = true
	search.clear()
	_populate_filters(context.get("filter_options", {}))
	var initial: Dictionary = context.get("initial_filters", {})
	_select_filter(race_filter, str(initial.get("race_id", "")))
	_select_filter(sex_filter, str(initial.get("sex", "")))
	_select_filter(hair_filter, str(initial.get("hair_tag", "")))
	_updating = false
	_filter_rows()


func open() -> void:
	_ensure_ui()
	if is_open():
		return
	var focus := get_viewport().gui_get_focus_owner()
	_return_focus = weakref(focus) if focus != null else null
	show()
	move_to_front()
	_layout()
	search.grab_focus.call_deferred()


## Programmatic closing is silent. Cancel, X and Escape emit dismissed.
func close() -> void:
	if not _built:
		hide()
		return
	hide()
	var focus := get_viewport().gui_get_focus_owner()
	if focus != null and is_ancestor_of(focus):
		focus.release_focus()
	if _return_focus != null:
		var previous := _return_focus.get_ref() as Control
		if is_instance_valid(previous) and previous.is_visible_in_tree():
			previous.grab_focus.call_deferred()
	_return_focus = null
	_last_focus = null


func is_open() -> bool:
	return visible


func selected_id() -> String:
	return _selected_id


func filtered_ids() -> PackedStringArray:
	var result := PackedStringArray()
	for row: Dictionary in _visible_rows:
		result.append(str(row.id))
	return result


func _input(event: InputEvent) -> void:
	if not is_open() or not event.is_pressed() or event.is_echo():
		return
	# Let a native filter menu consume its own Escape and directional input.
	for option: OptionButton in [race_filter, sex_filter, hair_filter]:
		if option != null and option.get_popup().visible:
			return
	if event.is_action_pressed("ui_cancel"):
		_dismiss()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("ui_focus_next") or event.is_action_pressed("ui_focus_prev"):
		_cycle_focus(-1 if event.is_action_pressed("ui_focus_prev") else 1)
		get_viewport().set_input_as_handled()


func _dismiss() -> void:
	close()
	dismissed.emit()


func _use_basis() -> void:
	if not _selection_is_visible():
		return
	var chosen := _selected_id
	close()
	basis_selected.emit(chosen)


func _select_card(id: String) -> void:
	_selected_id = id
	_update_selection()
	preview_requested.emit(id)


func _selection_is_visible() -> bool:
	return _cards.has(_selected_id)


func _update_selection() -> void:
	for id: String in _cards:
		(_cards[id] as Button).set_pressed_no_signal(id == _selected_id)
	var selected: Dictionary = _by_id.get(_selected_id, {})
	selected_label.text = "Selected: " + str(selected.get("label", "")) if not selected.is_empty() else "Choose a starting look"
	selected_label.tooltip_text = selected_label.text
	use_button.disabled = not _selection_is_visible()
	if not selected.is_empty() and use_button.disabled:
		selected_label.text += " · hidden by filters"
	use_button.tooltip_text = "Choose a visible look to continue." if use_button.disabled else "Continue editing this starting look."
	_refresh_focus_links()


func _populate_filters(options: Dictionary) -> void:
	var races: Dictionary = {}
	var sexes: Dictionary = {}
	var hair: Dictionary = {}
	for row: Dictionary in _rows:
		races[str(row.get("race_id", ""))] = str(row.get("race_label", ""))
		var sex := str(row.get("sex", ""))
		sexes[sex] = sex.capitalize()
		for tag: Variant in row.get("hair_tags", []):
			hair[str(tag)] = str(tag).replace("_", " ").capitalize()
	_add_filter(race_filter, "Race: Any", options.get("races", []), races)
	_add_filter(sex_filter, "Sex: Any", options.get("sexes", []), sexes)
	_add_filter(hair_filter, "Hair: Any", options.get("hair_tags", []), hair)


func _add_filter(option: OptionButton, any_label: String, supplied: Array, fallback: Dictionary) -> void:
	option.clear()
	option.add_item(any_label)
	option.set_item_metadata(0, "")
	var entries: Array[Dictionary] = []
	if supplied.is_empty():
		for id: String in fallback:
			if not id.is_empty():
				entries.append({"id": id, "label": str(fallback[id])})
		entries.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.label).naturalnocasecmp_to(str(b.label)) < 0)
	else:
		for value: Variant in supplied:
			if value is Dictionary:
				entries.append(value)
			else:
				entries.append({"id": str(value), "label": str(value).replace("_", " ").capitalize()})
	for entry: Dictionary in entries:
		var id := str(entry.get("id", ""))
		if id.is_empty():
			continue
		option.add_item(str(entry.get("label", id)))
		option.set_item_metadata(option.item_count - 1, id)
	option.select(0)


func _select_filter(option: OptionButton, id: String) -> void:
	for index: int in option.item_count:
		if str(option.get_item_metadata(index)) == id:
			option.select(index)
			return


func _filter_value(option: OptionButton) -> String:
	return str(option.get_item_metadata(option.selected)) if option.selected >= 0 else ""


func _filter_rows(_value: Variant = null) -> void:
	if _updating:
		return
	_cards.clear()
	_visible_rows.clear()
	for child: Node in grid.get_children():
		grid.remove_child(child)
		child.queue_free()
	var query := search.text.strip_edges().to_lower()
	var race := _filter_value(race_filter)
	var sex := _filter_value(sex_filter)
	var hair := _filter_value(hair_filter)
	for row: Dictionary in _rows:
		if not race.is_empty() and str(row.get("race_id", "")) != race:
			continue
		if not sex.is_empty() and str(row.get("sex", "")) != sex:
			continue
		if not hair.is_empty() and not hair in row.get("hair_tags", []):
			continue
		var haystack := "%s %s %s %s %s" % [row.get("label", ""), row.get("race_label", ""), row.get("sex", ""), " ".join(row.get("hair_tags", [])), row.get("search_text", "")]
		var matches := true
		for word: String in query.split(" ", false):
			if not haystack.to_lower().contains(word):
				matches = false
				break
		if not matches:
			continue
		_visible_rows.append(row)
		grid.add_child(_make_card(row))
	result_count.text = "%d starting %s" % [_visible_rows.size(), "look" if _visible_rows.size() == 1 else "looks"]
	empty_message.visible = _visible_rows.is_empty()
	grid.visible = not _visible_rows.is_empty()
	clear_filters.disabled = query.is_empty() and race.is_empty() and sex.is_empty() and hair.is_empty()
	scroll.scroll_vertical = 0
	_update_selection()
	_layout()


func _reset_filters() -> void:
	_updating = true
	search.clear()
	for option: OptionButton in [race_filter, sex_filter, hair_filter]:
		option.select(0)
	_updating = false
	_filter_rows()
	search.grab_focus()


func _make_card(row: Dictionary) -> Button:
	var id := str(row.id)
	var button := Button.new()
	button.name = "Basis_" + id.validate_node_name()
	button.toggle_mode = true
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.custom_minimum_size.x = _card_width
	button.clip_contents = true
	button.tooltip_text = "%s · %s · %s" % [row.get("label", ""), row.get("race_label", ""), str(row.get("sex", "")).capitalize()]
	button.accessibility_name = button.tooltip_text
	button.pressed.connect(_select_card.bind(id))
	button.focus_entered.connect(func() -> void: scroll.ensure_control_visible(button))
	button.add_theme_stylebox_override("normal", _box(Color("202329"), Color("61543c"), 1, 4, 0))
	button.add_theme_stylebox_override("hover", _box(Color("2e3035"), GOLD, 2, 4, 0))
	button.add_theme_stylebox_override("pressed", _box(Color("3a3023"), GOLD, 3, 4, 0))
	button.add_theme_stylebox_override("hover_pressed", _box(Color("473a29"), GOLD.lightened(.15), 3, 4, 0))
	button.add_theme_stylebox_override("focus", _box(Color(0, 0, 0, 0), Color("fff0ba"), 2, 4, 0))
	var margin := MarginContainer.new()
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 8)
	button.add_child(margin)
	var body := VBoxContainer.new()
	body.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body.add_theme_constant_override("separation", 4)
	margin.add_child(body)
	var portrait_frame := PanelContainer.new()
	portrait_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	portrait_frame.add_theme_stylebox_override("panel", _box(Color("19212a"), Color("3e4144"), 1, 2, 0))
	body.add_child(portrait_frame)
	var portrait := TextureRect.new()
	portrait.name = "Portrait"
	portrait.custom_minimum_size.y = _portrait_height
	portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	portrait_frame.add_child(portrait)
	var placeholder := _label("—", 28, MUTED)
	placeholder.name = "Placeholder"
	placeholder.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	placeholder.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	portrait_frame.add_child(placeholder)
	var label := _label(str(row.get("label", "Starting look")), 15, TEXT)
	label.name = "Name"
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.add_child(label)
	button.set_meta("portrait", portrait)
	button.set_meta("caption", label)
	button.set_meta("placeholder", placeholder)
	button.custom_minimum_size.y = _portrait_height + CARD_FOOTER_HEIGHT
	_cards[id] = button
	portrait.texture = portraits.texture(str(row.get("portrait_id", id)), row.get("look", {}))
	placeholder.visible = portrait.texture == null
	return button


func _ensure_ui() -> void:
	if _built:
		return
	_built = true
	name = "CreationBasePicker"
	var shade := ColorRect.new()
	shade.name = "Backdrop"
	shade.color = Color(0.015, 0.018, 0.024, .38)
	shade.mouse_filter = Control.MOUSE_FILTER_STOP
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(shade)
	panel = PanelContainer.new()
	panel.name = "Library"
	var frame := _box(Color("1a1c22"), GOLD_DARK, 2, 5, 20)
	frame.shadow_color = Color(0, 0, 0, .7)
	frame.shadow_size = 14
	panel.add_theme_stylebox_override("panel", frame)
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(panel)
	panel.minimum_size_changed.connect(func() -> void: _layout.call_deferred())
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 10)
	panel.add_child(_body)
	var header := HBoxContainer.new()
	_body.add_child(header)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	titles.add_theme_constant_override("separation", 4)
	header.add_child(titles)
	_title = _label("Choose a starting look", 28, TEXT)
	_title.add_theme_font_override("font", Art.title_font())
	titles.add_child(_title)
	titles.add_child(_label("All traits remain editable.", 14, MUTED))
	close_button = _button("×", false)
	close_button.name = "Close"
	close_button.custom_minimum_size = Vector2(36, 36)
	close_button.add_theme_font_size_override("font_size", 24)
	close_button.tooltip_text = "Close starting looks [Esc]"
	close_button.accessibility_name = "Close starting looks"
	close_button.pressed.connect(_dismiss)
	header.add_child(close_button)
	_body.add_child(HSeparator.new())
	search = LineEdit.new()
	search.name = "Search"
	search.placeholder_text = "Search looks…"
	search.accessibility_name = "Search starting looks"
	search.clear_button_enabled = true
	search.custom_minimum_size.y = 36
	search.add_theme_stylebox_override("normal", _box(FIELD, GOLD_DARK, 1, 3, 8))
	search.add_theme_stylebox_override("focus", _box(FIELD, GOLD, 2, 3, 8))
	search.add_theme_color_override("font_color", TEXT)
	search.add_theme_color_override("font_placeholder_color", MUTED)
	search.text_changed.connect(_filter_rows)
	search.text_submitted.connect(func(_text: String) -> void:
		if not _visible_rows.is_empty():
			(_cards[str(_visible_rows[0].id)] as Button).grab_focus())
	_body.add_child(search)
	var filters := HBoxContainer.new()
	filters.add_theme_constant_override("separation", 8)
	_body.add_child(filters)
	race_filter = _option("Race")
	sex_filter = _option("Sex")
	hair_filter = _option("Hair")
	for option: OptionButton in [race_filter, sex_filter, hair_filter]:
		filters.add_child(option)
	clear_filters = _button("Clear filters", false)
	clear_filters.name = "ClearFilters"
	clear_filters.pressed.connect(_reset_filters)
	filters.add_child(clear_filters)
	result_count = _label("", 12, MUTED)
	result_count.accessibility_live = AccessibilityServer.LIVE_POLITE
	_body.add_child(result_count)
	scroll = ScrollContainer.new()
	scroll.name = "PortraitScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size.y = 80
	scroll.follow_focus = true
	scroll.resized.connect(func() -> void: _fit_card_height.call_deferred())
	_body.add_child(scroll)
	var results := VBoxContainer.new()
	results.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(results)
	grid = GridContainer.new()
	grid.name = "PortraitGrid"
	grid.columns = 4
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 12)
	results.add_child(grid)
	empty_message = _label("No looks match these filters.\nTry a different search, or clear the filters.", 16, MUTED)
	empty_message.name = "EmptyResults"
	empty_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	empty_message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	empty_message.custom_minimum_size.y = 90
	empty_message.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	results.add_child(empty_message)
	_body.add_child(HSeparator.new())
	_footer = HBoxContainer.new()
	_footer.add_theme_constant_override("separation", 10)
	_body.add_child(_footer)
	selected_label = _label("Choose a starting look", 14, GOLD)
	selected_label.name = "Selection"
	selected_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	selected_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_footer.add_child(selected_label)
	cancel_button = _button("Cancel", false)
	cancel_button.name = "Cancel"
	cancel_button.custom_minimum_size.x = 88
	cancel_button.pressed.connect(_dismiss)
	_footer.add_child(cancel_button)
	use_button = _button("Use this basis", true)
	use_button.name = "UseBasis"
	use_button.custom_minimum_size.x = 152
	use_button.disabled = true
	use_button.pressed.connect(_use_basis)
	_footer.add_child(use_button)
	_populate_filters({})


func _layout() -> void:
	if not _built:
		return
	var bounds := size if size.x > 0 and size.y > 0 else get_viewport_rect().size
	var margin := 18.0 if bounds.x < 800 else 38.0
	var start := ceilf(bounds.x * .32) + 12 if bounds.x >= 1100 else margin
	var region_width := bounds.x - start - margin
	var compact := bounds.y < 600
	if compact != _compact:
		_compact = compact
		_body.add_theme_constant_override("separation", 6 if compact else 10)
		(panel.get_theme_stylebox("panel") as StyleBoxFlat).set_content_margin_all(14 if compact else 20)
	var target_size := Vector2(minf(1080, region_width), minf(780, bounds.y - margin * 2))
	_title.add_theme_font_size_override("font_size", 24 if bounds.x < 800 else 28)
	var content_width := maxf(120, target_size.x - (44 if compact else 56))
	grid.columns = clampi(floori((content_width + 12) / 180), 1, 4)
	_card_width = floorf((content_width - (grid.columns - 1) * 12) / grid.columns)
	_portrait_height = minf(_card_width - 18, 144 if bounds.y < 760 else 176)
	panel.size = target_size
	panel.position = Vector2(start + (region_width - panel.size.x) * .5, (bounds.y - panel.size.y) * .5)
	_fit_card_height()
	_refresh_focus_links()


## Reserve room for the name as well as the face. The portrait area is the
## flexible part, so two full rows remain readable at ordinary UI scaling.
## Shorter windows retain a useful minimum face size and scroll normally.
func _fit_card_height() -> void:
	if not _built or scroll == null or grid == null:
		return
	var bounds := size if size.x > 0 and size.y > 0 else get_viewport_rect().size
	var maximum := minf(_card_width - 18, 144 if bounds.y < 760 else 176)
	if scroll.size.y > 0 and not _visible_rows.is_empty():
		var rows_to_show := mini(2, ceili(float(_visible_rows.size()) / grid.columns))
		var gaps := float(grid.get_theme_constant("v_separation") * (rows_to_show - 1))
		var fitting_height := floorf((scroll.size.y - gaps) / rows_to_show) - CARD_FOOTER_HEIGHT
		maximum = minf(maximum, maxf(MIN_PORTRAIT_HEIGHT, fitting_height))
	_portrait_height = maximum
	for id: String in _cards:
		var card := _cards[id] as Button
		card.custom_minimum_size = Vector2(_card_width, _portrait_height + CARD_FOOTER_HEIGHT)
		(card.get_meta("portrait") as TextureRect).custom_minimum_size.y = _portrait_height


func _focus_order() -> Array[Control]:
	var result: Array[Control] = [search, race_filter, sex_filter, hair_filter]
	if not clear_filters.disabled:
		result.append(clear_filters)
	for row: Dictionary in _visible_rows:
		result.append(_cards[str(row.id)])
	result.append(cancel_button)
	if not use_button.disabled:
		result.append(use_button)
	result.append(close_button)
	return result


func _cycle_focus(step: int) -> void:
	var order := _focus_order()
	var current := order.find(get_viewport().gui_get_focus_owner())
	order[posmod(current + step, order.size())].grab_focus()


func _on_focus_changed(control: Control) -> void:
	if not is_open() or control == null:
		return
	if is_ancestor_of(control):
		_last_focus = weakref(control)
	else:
		_restore_modal_focus.call_deferred()


func _restore_modal_focus() -> void:
	if not is_open():
		return
	var previous := _last_focus.get_ref() as Control if _last_focus != null else null
	if is_instance_valid(previous) and previous.is_visible_in_tree():
		previous.grab_focus()
	else:
		search.grab_focus()


func _refresh_focus_links() -> void:
	if not _built or grid == null or search == null or use_button == null:
		return
	var order := _focus_order()
	for index: int in order.size():
		var target := order[index]
		target.focus_next = target.get_path_to(order[(index + 1) % order.size()])
		target.focus_previous = target.get_path_to(order[posmod(index - 1, order.size())])
	for index: int in _visible_rows.size():
		var card := _cards[str(_visible_rows[index].id)] as Button
		card.focus_neighbor_left = card.get_path_to(_cards[str(_visible_rows[maxi(0, index - 1)].id)])
		card.focus_neighbor_right = card.get_path_to(_cards[str(_visible_rows[mini(_visible_rows.size() - 1, index + 1)].id)])
		card.focus_neighbor_top = card.get_path_to(_cards[str(_visible_rows[index - grid.columns].id)] if index >= grid.columns else search)
		card.focus_neighbor_bottom = card.get_path_to(_cards[str(_visible_rows[index + grid.columns].id)] if index + grid.columns < _visible_rows.size() else (use_button if not use_button.disabled else cancel_button))


func _option(label: String) -> OptionButton:
	var option := OptionButton.new()
	option.name = label + "Filter"
	option.accessibility_name = label + " filter"
	option.tooltip_text = "Filter by " + label.to_lower()
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	option.custom_minimum_size = Vector2(100, 36)
	option.fit_to_longest_item = false
	option.clip_text = true
	option.add_theme_color_override("font_color", TEXT)
	option.add_theme_stylebox_override("normal", _box(FIELD, GOLD_DARK, 1, 3, 7))
	option.add_theme_stylebox_override("hover", _box(Color("292b31"), GOLD, 1, 3, 7))
	option.add_theme_stylebox_override("focus", _box(FIELD, GOLD, 2, 3, 7))
	option.item_selected.connect(_filter_rows)
	return option


func _label(text: String, font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	return label


func _button(text: String, primary: bool) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 36
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", TEXT)
	button.add_theme_color_override("font_disabled_color", Color("79766f"))
	button.add_theme_stylebox_override("normal", _box(EntryStyle.BURGUNDY if primary else Color("24252b"), GOLD_DARK, 1, 3, 8))
	button.add_theme_stylebox_override("hover", _box(EntryStyle.BURGUNDY_HOVER if primary else Color("34343a"), GOLD, 2, 3, 8))
	button.add_theme_stylebox_override("pressed", _box(EntryStyle.BURGUNDY_PRESSED, GOLD, 2, 3, 8))
	button.add_theme_stylebox_override("focus", _box(Color(0, 0, 0, 0), Color("fff0ba"), 2, 3, 8))
	button.add_theme_stylebox_override("disabled", _box(Color("1c1d22"), Color("4a4539"), 1, 3, 8))
	return button


static func _box(background: Color, border: Color, width: int, radius: int, margin: float) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = background
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(radius)
	box.set_content_margin_all(margin)
	return box
