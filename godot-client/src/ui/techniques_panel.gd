extends VBoxContainer
## Inspecting a row never uses it. Rings and quick slots retain the use seam.
signal place_on_bar(key: String)
signal used(key: String)
signal close_requested
const REFRESH_MSEC := 200
const UI := preload("res://src/ui/action_book_ui.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const Icons := preload("res://src/ui/technique_icons.gd")
const Preview := preload("res://src/ui/technique_effect_preview.gd")

class TechniqueButton extends Button:
	var key := ""
	var draggable := false
	func _get_drag_data(_position: Vector2) -> Variant:
		if key.is_empty() or not draggable: return null
		var picture := TextureRect.new()
		picture.texture = icon
		picture.custom_minimum_size = Vector2(36, 36)
		picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		set_drag_preview(picture)
		return {"kind": "technique", "key": key}

var points_label: Label
var points_meter: ProgressBar
var status_label: Label
var hint_label: Label
var list: VBoxContainer
var buttons: Dictionary = {}
var rows: Dictionary = {}
var show_locked: CheckButton # Compatibility for tools; Learned is the visible filter.
var search: LineEdit
var selected_key := ""
var name_label: Label
var description_label: Label
var numbers_label: Label
var cooldown_label: Label
var requirements_rows: VBoxContainer
var use_button: Button
var assign_button: Button
var slot_picker: OptionButton
var favorite_button: Button
var preview
var selected_icon: TextureRect
var loadout
var request_sender: Callable
var creature_validator: Callable
var player_validator: Callable
var pending_key := ""
var _order: Array = []
var _row_controls: Dictionary = {}
var _group_controls: Array[Control] = []
var _filter_buttons: Dictionary = {}
var _filter := "all"
var _favorites: Array = []
var _profile := ""
var _next_refresh := 0
var _inspector: PanelContainer
var _scroll: ScrollContainer
var _info_scroll: ScrollContainer
var _headings: HBoxContainer
var _empty_label: Label
var _compact := false
var _short := false
var _hero: HBoxContainer
var _requirements_heading: Label
var _displayed_requirements: Array = []

func _ready() -> void:
	name = "TechniquesTab"
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 7)
	_build()
	AppState.state_changed.connect(_on_state_changed)
	sync()

func configure(sender: Callable, creature_check: Callable = Callable(), player_check: Callable = Callable()) -> void:
	request_sender = sender
	creature_validator = creature_check
	player_validator = player_check

func set_loadout(value) -> void:
	loadout = value
	loadout.changed.connect(_on_loadout_changed)
	_restore_preferences()

func _on_loadout_changed() -> void:
	if _profile != loadout.profile:
		selected_key = ""
		search.clear()
		_restore_preferences()

func _restore_preferences() -> void:
	if loadout == null: return
	_profile = loadout.profile
	var preferences: Dictionary = loadout.book_preferences.get("techniques", {})
	_favorites = preferences.get("favorites", []).duplicate()
	set_filter(str(preferences.get("filter", "all")), false)

func _save_preferences() -> void:
	if loadout == null: return
	loadout.book_preferences["techniques"] = {"filter": _filter, "favorites": _favorites.duplicate()}
	loadout.save_book_preferences()

static func action_points(state: Dictionary) -> Vector2i:
	if not state.has("action_points"): return Vector2i(-1, -1)
	return Vector2i(int(state.get("action_points", 0)), int(state.get("max_action_points", 0)))

static func offered(row: Dictionary) -> bool:
	var blocker := str(row.get("blocker", ""))
	return bool(row.get("known", false)) and (blocker.is_empty() or "action points" in blocker)

static func key_name(action: String) -> String:
	if not InputMap.has_action(action): return "?"
	for event in InputMap.action_get_events(action):
		if event is InputEventKey:
			return event.as_text_physical_keycode() if event.physical_keycode != 0 else event.as_text()
	return "an unbound key"

func _on_state_changed(path: StringName) -> void:
	if path == &"techniques": sync()

func _process(_delta: float) -> void:
	if not is_visible_in_tree() or Time.get_ticks_msec() < _next_refresh: return
	_next_refresh = Time.get_ticks_msec() + REFRESH_MSEC
	_refresh_buttons()

func sync() -> void:
	var incoming: Array = AppState.techniques.get("techniques", [])
	rows.clear()
	var order := []
	for raw in incoming:
		if raw is Dictionary and not str(raw.get("key", "")).is_empty():
			rows[str(raw.key)] = raw
			order.append(str(raw.key))
	if order != _order:
		_order = order
		_rebuild()
	if pending_key != "" and not rows.has(pending_key): cancel_pending()
	_refresh_buttons()

func ready_in(key: String) -> float:
	var row: Dictionary = rows.get(key, {})
	var elapsed := float(Time.get_ticks_msec() - int(AppState.techniques.get("received_msec", Time.get_ticks_msec()))) / 1000.0
	return maxf(0.0, float(row.get("ready_in", 0.0)) - elapsed)

func unavailable_reason(key: String) -> String:
	var row: Dictionary = rows.get(key, {})
	if row.is_empty(): return "Unknown technique."
	if not bool(row.get("known", false)): return "Read the %s to learn it." % str(row.get("manual", "manual"))
	if str(row.get("kind", "")) == "stance" and bool(row.get("active", false)): return ""
	var blocker := str(row.get("blocker", ""))
	if not blocker.is_empty(): return blocker
	if ready_in(key) > 0.05: return "Ready in %ds." % ceili(ready_in(key))
	var pool := action_points(AppState.techniques)
	if pool.x >= 0 and pool.x < int(row.get("ap", 0)): return "You need %d action points." % int(row.ap)
	return ""

func tooltip_for(key: String) -> String:
	var row: Dictionary = rows.get(key, {})
	var tip := "%s\n%s\n%s %d · %s · %d AP" % [row.get("name", key), row.get("description", ""), row.get("skill", ""), int(row.get("level", 0)), row.get("group", ""), int(row.get("ap", 0))]
	if float(row.get("cooldown", 0)) > 0: tip += " · cooldown %ss" % str(row.cooldown)
	var reason := unavailable_reason(key)
	if not reason.is_empty(): tip += "\n" + reason
	return tip

func set_filter(value: String, save := true) -> void:
	_filter = value if value in _filter_buttons else "all"
	for key in _filter_buttons: (_filter_buttons[key] as Button).set_pressed_no_signal(key == _filter)
	if save: _save_preferences()
	_refresh_buttons()

func _matches(key: String) -> bool:
	var row: Dictionary = rows[key]
	var query := search.text.strip_edges().to_lower()
	if not query.is_empty() and not query in ("%s %s %s" % [row.get("name", key), row.get("group", ""), row.get("description", "")]).to_lower(): return false
	if _filter == "ready" and not unavailable_reason(key).is_empty(): return false
	if _filter == "learned" and not bool(row.get("known", false)): return false
	if _filter == "favorites" and key not in _favorites: return false
	return true

func select_technique(key: String) -> void:
	if not rows.has(key): return
	selected_key = key
	for candidate in buttons: (buttons[candidate] as Button).set_pressed_no_signal(candidate == key)
	_info_scroll.scroll_vertical = 0
	_refresh_selected()

func edit_slot(index: int, key: String) -> void:
	slot_picker.select(clampi(index, 0, 11))
	search.clear()
	set_filter("all")
	select_technique(key)

func _toggle_favorite() -> void:
	if selected_key.is_empty(): return
	if selected_key in _favorites: _favorites.erase(selected_key)
	else: _favorites.append(selected_key)
	_save_preferences()
	_refresh_buttons()

func _rounds_text(rounds: float) -> String:
	return str(roundi(rounds)) if is_equal_approx(rounds, roundf(rounds)) else str(snappedf(rounds, 0.1))

func _refresh_buttons() -> void:
	if points_label == null: return
	var pool := action_points(AppState.techniques)
	points_label.text = "Action points %d / %d" % [pool.x, pool.y] if pool.x >= 0 else "Action points —"
	points_meter.max_value = maxi(1, pool.y)
	points_meter.value = maxi(0, pool.x)
	points_meter.visible = pool.x >= 0
	var any_matches := false
	for key: String in buttons:
		var row: Dictionary = rows[key]
		var button: TechniqueButton = buttons[key]
		button.draggable = bool(row.get("known", false))
		# Unavailable actions remain inspectable, including unread manuals.
		button.disabled = false
		UI.icon_availability(button, unavailable_reason(key).is_empty())
		button.tooltip_text = tooltip_for(key)
		var line: HBoxContainer = _row_controls[key]
		line.visible = _matches(key)
		any_matches = any_matches or line.visible
		(line.get_node("Name") as Label).text = str(row.get("name", key))
		(line.get_node("AP") as Label).text = str(int(row.get("ap", 0)))
		var waiting := ready_in(key)
		var cooldown := float(row.get("cooldown_rounds", float(row.get("cooldown", 0)) / maxf(0.1, float(AppState.techniques.get("round", 2.0)))))
		var cooldown_text := "%ds" % ceili(waiting) if waiting > 0.05 else _rounds_text(cooldown)
		if pending_key == key: cooldown_text = "Aim"
		elif bool(row.get("active", false)): cooldown_text = "Held" if row.get("kind") == "stance" else "Queued"
		(line.get_node("Cooldown") as Label).text = cooldown_text
		(line.get_node("Cooldown") as Label).tooltip_text = "Ready in %ds" % ceili(waiting) if waiting > 0.05 else "Cooldown: %s combat rounds" % _rounds_text(cooldown)
	for section in _group_controls:
		var occupied := false
		for child in section.get_children():
			if child is HBoxContainer: occupied = occupied or child.visible
		section.visible = occupied
	_empty_label.visible = not any_matches
	if not selected_key.is_empty() and (not _row_controls.has(selected_key) or not _row_controls[selected_key].visible):
		selected_key = ""
	if selected_key.is_empty():
		for key in _order:
			if _row_controls[key].visible:
				selected_key = key
				break
	for key in buttons: (buttons[key] as Button).set_pressed_no_signal(key == selected_key)
	_refresh_selected()

func _refresh_selected() -> void:
	if not rows.has(selected_key):
		_set_requirements([])
		name_label.text = "Select a technique"
		description_label.text = "Select an icon to inspect its cost and requirements."
		numbers_label.text = ""
		cooldown_label.text = ""
		status_label.text = ""
		selected_icon.texture = null
		preview.set_technique({})
		use_button.disabled = true
		assign_button.disabled = true
		favorite_button.disabled = true
		return
	var row: Dictionary = rows[selected_key]
	name_label.text = str(row.get("name", selected_key))
	selected_icon.texture = Icons.icon_for(selected_key)
	preview.set_technique(row)
	description_label.text = str(row.get("description", ""))
	description_label.tooltip_text = description_label.text
	var target := "Creature · Next melee swing"
	if row.get("kind") == "shot": target = "Creature · Next arrow"
	elif row.get("kind") == "stance": target = "Self · Stance"
	elif row.get("kind") == "charge": target = "Creature · Approach and strike"
	elif selected_key == "intercept": target = "Party member · Guard"
	elif not bool(row.get("targeted", false)): target = "Self / nearby allies · Instant"
	var pool := action_points(AppState.techniques)
	numbers_label.text = "%s\n%d AP · Available %s" % [target, int(row.get("ap", 0)), str(pool.x) if pool.x >= 0 else "—"]
	var rounds := float(row.get("cooldown_rounds", float(row.get("cooldown", 0)) / maxf(0.1, float(AppState.techniques.get("round", 2.0)))))
	cooldown_label.text = "%s-round cooldown · %s" % [_rounds_text(rounds), "Ready in %ds" % ceili(ready_in(selected_key)) if ready_in(selected_key) > 0.05 else "Ready"]
	var requirements: Array = row.get("requirements", [])
	if requirements.is_empty():
		# Older servers only provide a combined blocker. Never invent gear state.
		var skill := str(row.get("skill", "Attack"))
		var current := int(AppState.stats.get(skill.to_lower(), 0))
		requirements = [
			{"label": "%s %d" % [skill, int(row.get("level", 0))], "detail": "Current %d" % current, "met": current >= int(row.get("level", 0))},
			{"label": str(row.get("manual", "")) if not str(row.get("manual", "")).is_empty() else "Known from the start", "detail": "Known" if row.get("known", false) else "Not learned", "met": bool(row.get("known", false))}]
	_set_requirements(requirements)
	favorite_button.disabled = false
	favorite_button.text = "★" if selected_key in _favorites else "☆"
	favorite_button.set_pressed_no_signal(selected_key in _favorites)
	var reason := unavailable_reason(selected_key)
	status_label.text = "Click a creature for %s." % str(row.get("name", selected_key)) if pending_key == selected_key else ("✓ Ready" if reason.is_empty() else "× " + reason)
	TextColors.bind(status_label, "spell_ready" if reason.is_empty() else "spell_blocked")
	use_button.disabled = not reason.is_empty()
	var release := str(row.get("kind", "")) == "stance" and bool(row.get("active", false))
	use_button.text = ("Release " if release else "Use ") + str(row.get("name", selected_key))
	use_button.tooltip_text = use_button.text
	assign_button.disabled = not bool(row.get("known", false))

func _set_requirements(requirements: Array) -> void:
	# Cooldown ticks must not recreate labels and disturb wrapping/scroll position.
	if requirements == _displayed_requirements: return
	_displayed_requirements = requirements.duplicate(true)
	UI.clear(requirements_rows)
	for requirement: Dictionary in requirements:
		UI.requirement(requirements_rows, str(requirement.get("label", "")), str(requirement.get("detail", "")), requirement.get("met"))

func _use_selected() -> void:
	if selected_key.is_empty() or not unavailable_reason(selected_key).is_empty(): return
	use(selected_key)
	close_requested.emit()

func _assign_selected() -> void:
	if assign_button.disabled: return
	if loadout != null: loadout.assign_technique(slot_picker.selected, selected_key)
	else: place_on_bar.emit(selected_key)

func use(key: String) -> void:
	var row: Dictionary = rows.get(key, {})
	if row.is_empty():
		return
	if pending_key == key:
		cancel_pending()
		return
	var request := {"op": "use", "key": key}
	if bool(row.get("targeted", false)):
		var target := _selected(creature_validator)
		if target < 0 and bool(AppState.combat_state.get("active", false)):
			target = int(AppState.combat_state.get("target_id", -1))
		if target < 0:
			pending_key = key
			status_label.text = "Click a creature for %s." % str(row.get("name", key))
			_refresh_buttons()
			return
		request["target_id"] = target
	elif key == "intercept":
		var ally := _selected(player_validator)
		if ally >= 0:
			request["target_id"] = ally
	_send(request)

## The next creature clicked receives the armed technique. True when one was
## armed, so the click does nothing else.
func fire_at(actor_id: int) -> bool:
	if pending_key == "":
		return false
	if creature_validator.is_valid() and not bool(creature_validator.call(actor_id)):
		return false
	var key := pending_key
	cancel_pending()
	_send({"op": "use", "key": key, "target_id": actor_id})
	return true

func cancel_pending() -> void:
	pending_key = ""
	if status_label != null:
		status_label.text = ""
	if list != null:
		_refresh_buttons()

func _selected(validator: Callable) -> int:
	var actor_id := int(AppState.selected_actor_id)
	if actor_id < 0 or actor_id == AppState.local_actor_id:
		return -1
	if validator.is_valid() and not bool(validator.call(actor_id)):
		return -1
	return actor_id

func _send(request: Dictionary) -> void:
	if status_label != null:
		status_label.text = ""
	if request_sender.is_valid():
		request_sender.call(request)
	used.emit(str(request.get("key", "")))


func _rebuild() -> void:
	UI.clear(list)
	buttons.clear()
	_row_controls.clear()
	_group_controls.clear()
	var groups := {}
	for key: String in _order:
		var row: Dictionary = rows[key]
		var group := str(row.get("group", "Techniques"))
		if not groups.has(group):
			var section := VBoxContainer.new()
			section.add_theme_constant_override("separation", 2)
			var heading := UI.label(group, 13)
			TextColors.bind(heading, "book_heading")
			section.add_child(heading)
			list.add_child(section)
			groups[group] = section
			_group_controls.append(section)
		var line := HBoxContainer.new()
		line.name = "Row_" + key
		line.add_theme_constant_override("separation", 4)
		line.gui_input.connect(func(event: InputEvent):
			if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
				select_technique(key))
		(groups[group] as VBoxContainer).add_child(line)
		var button := TechniqueButton.new()
		button.key = key
		button.name = "Inspect_" + key
		button.toggle_mode = true
		button.icon = Icons.icon_for(key)
		UI.icon_button(button)
		button.pressed.connect(select_technique.bind(key))
		line.add_child(button)
		var title := UI.label(str(row.get("name", key)), 13)
		title.name = "Name"
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		title.tooltip_text = tooltip_for(key)
		line.add_child(title)
		for column: String in ["AP", "Cooldown"]:
			var number := UI.label("", 12)
			number.name = column
			number.custom_minimum_size.x = 32 if column == "AP" else 60
			number.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			line.add_child(number)
		buttons[key] = button
		_row_controls[key] = line

func set_compact(value: bool) -> void:
	_compact = value
	if _inspector != null: _inspector.custom_minimum_size.x = 244 if value else 288

func set_short(value: bool) -> void:
	_short = value
	if _hero == null: return
	_hero.visible = not value
	description_label.visible = not value
	numbers_label.visible = not value
	cooldown_label.visible = not value
	_requirements_heading.visible = not value

func _build() -> void:
	var toolbar := HBoxContainer.new()
	add_child(toolbar)
	search = LineEdit.new()
	search.name = "TechniqueSearch"
	search.placeholder_text = "Search techniques…"
	search.add_theme_font_size_override("font_size", 13)
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.text_changed.connect(func(_text: String): _refresh_buttons())
	toolbar.add_child(search)
	var filters := HBoxContainer.new()
	toolbar.add_child(filters)
	_filter_buttons = UI.filters(filters, set_filter)
	show_locked = CheckButton.new()
	show_locked.hide()
	show_locked.button_pressed = true
	show_locked.toggled.connect(func(value: bool): set_filter("all" if value else "learned"))
	add_child(show_locked)
	var resources := HBoxContainer.new()
	add_child(resources)
	points_label = UI.label("Action points —", 13)
	points_label.name = "ActionPoints"
	TextColors.bind(points_label, "book_points")
	resources.add_child(points_label)
	points_meter = ProgressBar.new()
	points_meter.custom_minimum_size = Vector2(100, 9)
	points_meter.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	points_meter.show_percentage = false
	points_meter.add_theme_stylebox_override("fill", UI.box(Color("a84cdb"), Color.TRANSPARENT, 0))
	resources.add_child(points_meter)
	var panes := HBoxContainer.new()
	panes.add_theme_constant_override("separation", 10)
	panes.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(panes)
	var browser := VBoxContainer.new()
	browser.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panes.add_child(browser)
	_headings = HBoxContainer.new()
	_headings.add_theme_constant_override("separation", 4)
	browser.add_child(_headings)
	var title := UI.label("Technique", 13)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_headings.add_child(title)
	for heading: String in ["AP", "Cooldown\nrounds"]:
		var label := UI.label(heading, 11)
		label.custom_minimum_size.x = 32 if heading == "AP" else 60
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_headings.add_child(label)
	_scroll = UI.scroll("TechniquesScroll")
	_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_ALWAYS
	browser.add_child(_scroll)
	_headings.add_theme_constant_override("separation", 4)
	var gutter := Control.new()
	gutter.custom_minimum_size.x = _scroll.get_v_scroll_bar().get_combined_minimum_size().x
	_headings.add_child(gutter)
	var rows_box := VBoxContainer.new()
	rows_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.add_child(rows_box)
	list = VBoxContainer.new()
	list.name = "TechniquesList"
	rows_box.add_child(list)
	_empty_label = UI.label("No techniques match. Clear search or choose All.", 13, true)
	rows_box.add_child(_empty_label)
	_inspector = PanelContainer.new()
	_inspector.name = "TechniqueDetails"
	_inspector.custom_minimum_size.x = 288
	_inspector.add_theme_stylebox_override("panel", UI.box(Color("130f0a"), Color("80623b"), 8))
	panes.add_child(_inspector)
	var details := VBoxContainer.new()
	details.add_theme_constant_override("separation", 6)
	_inspector.add_child(details)
	var header := HBoxContainer.new()
	details.add_child(header)
	name_label = UI.label("Select a technique", 18, true)
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(name_label)
	favorite_button = UI.button("☆")
	favorite_button.toggle_mode = true
	favorite_button.tooltip_text = "Toggle favorite"
	favorite_button.pressed.connect(_toggle_favorite)
	header.add_child(favorite_button)
	_info_scroll = UI.scroll("TechniqueInfoScroll")
	details.add_child(_info_scroll)
	var info := VBoxContainer.new()
	info.add_theme_constant_override("separation", 4)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_info_scroll.add_child(info)
	_hero = HBoxContainer.new()
	info.add_child(_hero)
	selected_icon = TextureRect.new()
	selected_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	selected_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	selected_icon.custom_minimum_size = Vector2(56, 56)
	_hero.add_child(selected_icon)
	preview = Preview.new()
	preview.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hero.add_child(preview)
	preview.custom_minimum_size = Vector2(120, 92)
	description_label = UI.label("", 13, true)
	description_label.max_lines_visible = 3
	info.add_child(description_label)
	numbers_label = UI.label("", 13, true)
	info.add_child(numbers_label)
	cooldown_label = UI.label("", 12, true)
	info.add_child(cooldown_label)
	_requirements_heading = UI.label("Requirements", 13)
	info.add_child(_requirements_heading)
	requirements_rows = VBoxContainer.new()
	requirements_rows.name = "TechniqueRequirements"
	info.add_child(requirements_rows)
	status_label = UI.label("", 13, true)
	status_label.name = "TechniquesStatus"
	details.add_child(status_label)
	use_button = UI.button("Use")
	use_button.name = "UseTechnique"
	use_button.clip_text = true
	use_button.pressed.connect(_use_selected)
	details.add_child(use_button)
	var assignment := HBoxContainer.new()
	details.add_child(assignment)
	slot_picker = UI.slot_picker()
	assignment.add_child(slot_picker)
	assign_button = UI.button("Assign")
	assign_button.name = "AssignTechnique"
	assign_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	assign_button.pressed.connect(_assign_selected)
	assignment.add_child(assign_button)
	hint_label = UI.label("Select to inspect · Drag to a quick slot", 12, true)
	TextColors.bind(hint_label, "book_muted")
	add_child(hint_label)
