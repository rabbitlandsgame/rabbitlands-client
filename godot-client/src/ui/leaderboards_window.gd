extends Control
const TextColors := preload("res://src/ui/text_colors.gd")
## The selected podium design. Category definitions, scores and the reader's
## rank are server snapshots; only presentation and filter choices live here.

const Medallion := preload("res://src/ui/leaderboard_medallion.gd")
const Art := preload("res://src/ui/leaderboard_art.gd")
const Portraits := preload("res://src/ui/leaderboard_portraits.gd")
const GOLD := Color("e1b862")
const TEXT := Color("f2e8d4")
const MUTED := Color("aaa99f")
const METALS := [Color("e1b862"), Color("bbc9d7"), Color("ca9167")]

var panel: PanelContainer
var search: LineEdit
var category_rows: VBoxContainer
var heading: Label
var category_icon: TextureRect
var unit_heading: Label
var status: Label
var podium: HBoxContainer
var rows: VBoxContainer
var personal: Label
var personal_value: Label
var period_buttons: Array[Button] = []
var refresh_button: Button
var selected_category := "invasion_kills"
var selected_days := 0
var categories: Array = []
var _send: Callable
var _serial := 0
var _pending_id := -1
var _pending_since := 0
var _groups: Dictionary = {}
var _category_buttons: Dictionary = {}
var _dragger: WindowDrag
var _title_font: Font
var _compact := false
var _ranked_rows: Array = []
var portraits: Node
var _content: VBoxContainer
var _sidebar: VBoxContainer
var _table_portrait_gap: Control

func _ready() -> void:
	name = "LeaderboardsLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	portraits = Portraits.new()
	add_child(portraits)
	_build()
	AppState.state_changed.connect(_on_state_changed)
	get_viewport().size_changed.connect(_layout)
	_layout()
	set_process(false)

func configure(send: Callable, registry: Dictionary = {}, equipment: Dictionary = {}) -> void:
	_send = send
	if not registry.is_empty():
		portraits.configure(registry, equipment)

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	if panel.visible:
		close()
		return
	panel.show()
	portraits.set_active(true)
	_activate()
	_request()

func close() -> void:
	panel.hide()
	portraits.set_active(false)
	_pending_id = -1
	set_process(false)
	if search.has_focus():
		search.release_focus()

func _process(_delta: float) -> void:
	if _pending_id >= 0 and Time.get_ticks_msec() - _pending_since >= 8000:
		_pending_id = -1
		status.text = "Rankings could not be loaded. Press Refresh to try again."
		refresh_button.disabled = false
		set_process(false)

func _request() -> void:
	_serial += 1
	_pending_id = _serial
	_pending_since = Time.get_ticks_msec()
	_clear_results()
	status.text = "Loading rankings…"
	refresh_button.disabled = true
	_update_selection()
	set_process(true)
	var result: Variant = ERR_UNCONFIGURED
	if _send.is_valid():
		result = _send.call("#leaderboards %s %s %d" % [selected_category,
			"30" if selected_days == 30 else "all", _serial])
	if result is int and result != OK:
		_pending_id = -1
		status.text = "Connect to the game to view the rankings."
		refresh_button.disabled = false
		set_process(false)

func _on_state_changed(path: StringName) -> void:
	if path == &"connection" and AppState.connection_state == "disconnected":
		close()
		portraits.clear()
		categories.clear()
		_build_categories()
		_clear_results()
	elif path == &"leaderboard":
		apply_snapshot(AppState.leaderboard)

func apply_snapshot(state: Dictionary) -> void:
	var request_id := int(state.get("request_id", 0))
	# A late response must neither replace a newer selection nor reopen a
	# dismissed window. Request zero is an explicit typed chat command.
	if request_id != 0 and (request_id != _pending_id or not panel.visible):
		return
	_pending_id = -1
	set_process(false)
	portraits.set_active(true)
	selected_category = str(state.get("category", "invasion_kills"))
	selected_days = int(state.get("days", 0))
	var next_categories: Array = state.get("categories", [])
	if categories != next_categories:
		categories = next_categories.duplicate(true)
		_build_categories()
	_update_selection()
	_clear_results()
	var ranked: Array = state.get("rows", [])
	_ranked_rows = ranked.duplicate(true)
	_draw_rankings()
	var own: Dictionary = state.get("self", {})
	personal.text = "Your rank: %s" % (str(int(own.rank)) if own.get("rank") != null else "Unranked")
	personal_value.text = _score(own.get("value", "0")) + " " + _unit().to_lower()
	if own.get("level") != null:
		personal_value.text += "  ·  Level %d" % int(own.level)
	status.text = "No ranked activity yet." if ranked.is_empty() else (
		"Ranked by XP gained in the last 30 days." if _unit() == "XP" and selected_days == 30
		else "Top 10 players · " + ("Last 30 days" if selected_days == 30 else "All time"))
	refresh_button.disabled = false
	if request_id == 0:
		panel.show()
		_activate()

func _activate() -> void:
	if panel.has_meta(WindowStack.STACK_META):
		WindowStack.activate(panel)
	else:
		panel.move_to_front()

func _choose_category(key: String) -> void:
	if key == selected_category:
		_update_selection()
		return
	selected_category = key
	_request()

func _choose_period(days: int) -> void:
	if days == selected_days:
		_update_selection()
		return
	selected_days = days
	_request()

func _update_selection() -> void:
	var info := _category()
	heading.text = str(info.get("label", "Invasion kills"))
	category_icon.texture = Art.subject(str(info.get("icon", "combat")))
	unit_heading.text = _unit()
	for key: String in _category_buttons:
		(_category_buttons[key] as Button).set_pressed_no_signal(key == selected_category)
	for index: int in period_buttons.size():
		period_buttons[index].set_pressed_no_signal(selected_days == (0 if index == 0 else 30))

func _category() -> Dictionary:
	for raw: Dictionary in categories:
		if raw.key == selected_category:
			return raw
	return {"label": "Invasion kills", "unit": "Kills", "icon": "combat"}

func _unit() -> String:
	return str(_category().get("unit", "Kills"))

static func _score(raw: Variant) -> String:
	var value := str(raw)
	var result := ""
	for index: int in value.length():
		if index > 0 and (value.length() - index) % 3 == 0:
			result += ","
		result += value[index]
	return result

func _clear_results() -> void:
	portraits.begin_batch()
	_ranked_rows.clear()
	_clear(podium)
	_clear(rows)
	personal.text = "Your rank: —"
	personal_value.text = ""

func _draw_rankings() -> void:
	portraits.begin_batch()
	_clear(podium)
	_clear(rows)
	# Silver, gold, bronze: the winner stands in the raised centre card.
	for index: int in [1, 0, 2]:
		var entry: Dictionary = _ranked_rows[index] if _ranked_rows.size() > index else {}
		podium.add_child(_champion(entry, index + 1))
	for index: int in range(3, _ranked_rows.size()):
		rows.add_child(_rank_row(_ranked_rows[index]))

static func _clear(node: Node) -> void:
	for child: Node in node.get_children():
		node.remove_child(child)
		child.queue_free()

func _build_categories() -> void:
	_clear(category_rows)
	_category_buttons.clear()
	var last_group := ""
	var group_body: VBoxContainer
	for entry: Dictionary in categories:
		var group_name := str(entry.group)
		if group_name != last_group:
			last_group = group_name
			if not _groups.has(group_name):
				_groups[group_name] = get_viewport_rect().size.y >= 760 or group_name == "Activity"
			var group_button := _button(group_name + "  ▾")
			group_button.name = "Group" + group_name.validate_node_name()
			group_button.alignment = HORIZONTAL_ALIGNMENT_LEFT
			group_button.add_theme_font_override("font", _title_font)
			TextColors.bind(group_button, "leaderboard_title")
			group_button.custom_minimum_size.y = 26
			for state: String in ["normal", "hover", "pressed", "focus"]:
				group_button.add_theme_stylebox_override(state, _box(Color("1c1e24"), Color("8b7046"), 1, 3, 3))
			category_rows.add_child(group_button)
			group_body = VBoxContainer.new()
			group_body.add_theme_constant_override("separation", 2)
			category_rows.add_child(group_body)
			group_body.visible = bool(_groups.get(group_name, true))
			group_button.text = group_name + ("  ▾" if group_body.visible else "  ▸")
			group_button.pressed.connect(_toggle_group.bind(group_name, group_body, group_button))
		var button := _button(str(entry.label))
		button.name = str(entry.key)
		button.toggle_mode = true
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.icon = Art.subject(str(entry.icon))
		button.add_theme_constant_override("icon_max_width", 18)
		button.add_theme_font_size_override("font_size", 13)
		button.custom_minimum_size.y = 22
		button.add_theme_stylebox_override("normal", _box(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 2, 2))
		button.add_theme_stylebox_override("hover", _box(Color("272c35"), GOLD.darkened(0.4), 1, 2, 2))
		button.add_theme_stylebox_override("pressed", _box(Color("54251d"), GOLD, 1, 2, 2))
		button.add_theme_stylebox_override("focus", _box(Color("272c35"), GOLD, 1, 2, 2))
		button.pressed.connect(_choose_category.bind(str(entry.key)))
		group_body.add_child(button)
		_category_buttons[str(entry.key)] = button
	_filter_categories(search.text)

func _toggle_group(key: String, body: VBoxContainer, button: Button) -> void:
	body.visible = not body.visible
	_groups[key] = body.visible
	button.text = key + ("  ▾" if body.visible else "  ▸")

func _filter_categories(query: String) -> void:
	var needle := query.strip_edges().to_lower()
	for key: String in _category_buttons:
		var button: Button = _category_buttons[key]
		button.visible = needle.is_empty() or button.text.to_lower().contains(needle)
	for index: int in range(0, category_rows.get_child_count(), 2):
		var header := category_rows.get_child(index) as Button
		var body := category_rows.get_child(index + 1) as VBoxContainer
		var found := false
		for button: Control in body.get_children():
			found = found or button.visible
		header.visible = found
		var key := header.text.trim_suffix("  ▾").trim_suffix("  ▸")
		body.visible = found and (not needle.is_empty() or bool(_groups.get(key, true)))

func _champion(entry: Dictionary, rank: int) -> Control:
	var column := VBoxContainer.new()
	column.name = "Place%d" % rank
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 0)
	if rank != 1:
		var space := Control.new()
		space.custom_minimum_size.y = 16 if _compact else 22
		column.add_child(space)
	var card := PanelContainer.new()
	card.name = "Card"
	card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var painted := StyleBoxTexture.new()
	painted.texture = Art.texture("champion-panel-v2")
	painted.modulate_color = METALS[rank - 1]
	painted.set_content_margin_all(8)
	painted.set_content_margin(SIDE_BOTTOM, 18)
	card.add_theme_stylebox_override("panel", painted)
	column.add_child(card)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 1)
	card.add_child(body)
	var emblem := Medallion.new()
	emblem.name = "Medallion"
	emblem.player_name = str(entry.get("name", ""))
	emblem.rank = rank
	emblem.metal = METALS[rank - 1]
	emblem.look = entry.get("portrait", {})
	emblem.portraits = portraits
	var portrait_size := (132 if rank == 1 else 116) if _compact else (174 if rank == 1 else 152)
	emblem.custom_minimum_size = Vector2.ONE * portrait_size
	emblem.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(emblem)
	var player := _label(str(entry.get("name", "Awaiting a challenger")), 17 if _compact else 22, TEXT)
	player.name = "Player"
	player.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	player.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	player.custom_minimum_size.x = 100
	player.tooltip_text = player.text
	player.add_theme_font_override("font", _title_font)
	body.add_child(player)
	if bool(entry.get("is_self", false)):
		player.text += " (You)"
	var amount := _label(_score(entry.value) if not entry.is_empty() else "—", 28 if _compact else 34, METALS[rank - 1])
	amount.add_theme_font_override("font", _title_font)
	amount.name = "Value"
	amount.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	amount.tooltip_text = amount.text
	if amount.text.length() > 13:
		amount.add_theme_font_size_override("font_size", 18)
	amount.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.add_child(amount)
	var detail := _unit().to_lower()
	if entry.get("level") != null:
		detail += "  ·  Level %d" % int(entry.level)
	var caption := _label(detail if not entry.is_empty() else "No ranked activity", 11 if _compact else 12, MUTED)
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.add_child(caption)
	return column

func _rank_row(entry: Dictionary) -> Control:
	var row := PanelContainer.new()
	row.name = "Rank%d" % int(entry.rank)
	var own := bool(entry.get("is_self", false))
	row.add_theme_stylebox_override("panel", _box(Color("3c301a") if own else Color("171a20"),
		GOLD if own else Color("373940"), 1, 3, 2))
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 10)
	row.add_child(line)
	var rank := _label(str(int(entry.rank)), 14, GOLD if own else TEXT)
	rank.custom_minimum_size.x = 46
	rank.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	line.add_child(rank)
	var avatar := Medallion.new()
	avatar.name = "Portrait"
	avatar.rank = 0
	avatar.player_name = str(entry.name)
	avatar.look = entry.get("portrait", {})
	avatar.portraits = portraits
	avatar.custom_minimum_size = Vector2(22, 22) if _compact else Vector2(29, 29)
	avatar.metal = GOLD.darkened(0.25)
	line.add_child(avatar)
	var player := _label(str(entry.name) + (" (You)" if own else ""), 15, GOLD if own else TEXT)
	player.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	player.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	line.add_child(player)
	if entry.get("level") != null:
		line.add_child(_label("Lv. %d" % int(entry.level), 12, MUTED))
	var amount := _label(_score(entry.value), 15, GOLD if own else TEXT)
	amount.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	line.add_child(amount)
	return row

func _build() -> void:
	_title_font = Art.title_font()
	panel = PanelContainer.new()
	panel.name = "LeaderboardsWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.add_theme_stylebox_override("panel", _box(Color("10141b"), Color("b58c47"), 2, 6, 14))
	panel.draw.connect(_draw_window_art)
	panel.resized.connect(panel.queue_redraw)
	panel.hide()
	add_child(panel)
	var body := VBoxContainer.new()
	body.name = "Body"
	body.add_theme_constant_override("separation", 10)
	panel.add_child(body)
	var header := HBoxContainer.new()
	header.name = "Header"
	header.add_theme_constant_override("separation", 15)
	body.add_child(header)
	_dragger = WindowDrag.attach(panel, header)
	_dragger.reserved_bottom = 88
	var brand := TextureRect.new()
	brand.texture = Art.texture("res://assets/branding/rabbitlands-mark-64.png")
	brand.custom_minimum_size = Vector2(38, 42)
	brand.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	brand.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	brand.mouse_filter = Control.MOUSE_FILTER_IGNORE
	header.add_child(brand)
	var wordmark := _label("Rabbit Lands", 24, GOLD)
	wordmark.add_theme_font_override("font", _title_font)
	header.add_child(wordmark)
	var title := _label("|  Leaderboards", 26, GOLD)
	title.add_theme_font_override("font", _title_font)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	for days: int in [0, 30]:
		var button := _button("All time" if days == 0 else "Last 30 days")
		button.toggle_mode = true
		button.custom_minimum_size.x = 126
		button.pressed.connect(_choose_period.bind(days))
		header.add_child(button)
		period_buttons.append(button)
	var close_button := _button("×")
	close_button.name = "Close"
	close_button.custom_minimum_size = Vector2(36, 36)
	close_button.add_theme_font_size_override("font_size", 23)
	close_button.tooltip_text = "Close leaderboards [Esc]"
	close_button.pressed.connect(close)
	header.add_child(close_button)
	body.add_child(HSeparator.new())
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 18)
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(columns)
	var sidebar := VBoxContainer.new()
	_sidebar = sidebar
	sidebar.name = "Sidebar"
	sidebar.custom_minimum_size.x = 218
	columns.add_child(sidebar)
	search = LineEdit.new()
	search.name = "Search"
	search.placeholder_text = "Search categories…"
	search.custom_minimum_size.y = 36
	search.add_theme_font_size_override("font_size", 14)
	search.add_theme_stylebox_override("normal", _box(Color("0d1118"), Color("9b7b46"), 1, 4, 7))
	search.add_theme_stylebox_override("focus", _box(Color("131a23"), GOLD, 2, 4, 7))
	search.text_changed.connect(_filter_categories)
	sidebar.add_child(search)
	var category_scroll := ScrollContainer.new()
	category_scroll.name = "CategoryScroll"
	category_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	category_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sidebar.add_child(category_scroll)
	category_rows = VBoxContainer.new()
	category_rows.name = "Categories"
	category_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	category_rows.add_theme_constant_override("separation", 5)
	category_scroll.add_child(category_rows)
	var content := VBoxContainer.new()
	_content = content
	content.resized.connect(panel.queue_redraw)
	content.name = "Content"
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_theme_constant_override("separation", 8)
	columns.add_child(content)
	var heading_row := HBoxContainer.new()
	content.add_child(heading_row)
	category_icon = TextureRect.new()
	category_icon.custom_minimum_size = Vector2(36, 36)
	category_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	category_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	heading_row.add_child(category_icon)
	heading = _label("Invasion kills", 25, TEXT)
	heading.add_theme_font_override("font", _title_font)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading_row.add_child(heading)
	refresh_button = _button("Refresh")
	refresh_button.name = "Refresh"
	refresh_button.pressed.connect(_request)
	heading_row.add_child(refresh_button)
	status = _label("", 12, MUTED)
	status.name = "Status"
	content.add_child(status)
	var scroll := ScrollContainer.new()
	scroll.name = "RankingsScroll"
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.add_child(scroll)
	var rankings := VBoxContainer.new()
	rankings.name = "Rankings"
	rankings.add_theme_constant_override("separation", 10)
	rankings.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(rankings)
	podium = HBoxContainer.new()
	podium.name = "Podium"
	podium.add_theme_constant_override("separation", 12)
	podium.custom_minimum_size.y = 0
	rankings.add_child(podium)
	var table_header := HBoxContainer.new()
	table_header.add_theme_constant_override("separation", 10)
	rankings.add_child(table_header)
	var rank_heading := _label("Rank", 13, MUTED)
	rank_heading.custom_minimum_size.x = 58
	table_header.add_child(rank_heading)
	_table_portrait_gap = Control.new()
	_table_portrait_gap.custom_minimum_size.x = 12
	table_header.add_child(_table_portrait_gap)
	var name_heading := _label("Player", 13, MUTED)
	name_heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	table_header.add_child(name_heading)
	unit_heading = _label("Kills", 13, MUTED)
	table_header.add_child(unit_heading)
	rows = VBoxContainer.new()
	rows.name = "Rows"
	rows.add_theme_constant_override("separation", 3)
	rankings.add_child(rows)
	var footer := PanelContainer.new()
	footer.name = "PersonalSummary"
	footer.add_theme_stylebox_override("panel", _box(Color("25231b"), GOLD, 1, 4, 10))
	content.add_child(footer)
	var summary := HBoxContainer.new()
	summary.add_theme_constant_override("separation", 18)
	footer.add_child(summary)
	var badge := TextureRect.new()
	badge.texture = Art.subject("overall")
	badge.custom_minimum_size = Vector2(30, 30)
	badge.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	badge.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	summary.add_child(badge)
	personal = _label("Your rank: —", 19, GOLD)
	personal.name = "Rank"
	personal.add_theme_font_override("font", _title_font)
	personal.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary.add_child(personal)
	personal_value = _label("", 18, GOLD)
	personal_value.name = "Value"
	summary.add_child(personal_value)
	_update_selection()

func _layout() -> void:
	# Keep filters and Close reachable; both lists scroll on shorter screens.
	var available := get_viewport_rect().size - Vector2(112, 104)
	var compact := available.y < 750
	if compact != _compact:
		_compact = compact
		if not _ranked_rows.is_empty():
			_draw_rankings()
	panel.custom_minimum_size = Vector2(minf(900, available.x), minf(470, available.y))
	panel.size = Vector2(minf(1460, available.x), minf(880, available.y))
	panel.position = Vector2(available.x - panel.size.x + 16, available.y - panel.size.y + 16) * 0.5
	if _dragger != null:
		_dragger.clamp_into_view()
	if _sidebar != null:
		_sidebar.custom_minimum_size.x = 250 if available.x > 1350 else 218
	if _table_portrait_gap != null:
		_table_portrait_gap.custom_minimum_size.x = 12 if _compact else 19
	panel.queue_redraw()

func _draw_window_art() -> void:
	if _content != null and _content.size.x > 0:
		var position := _content.global_position - panel.global_position
		var backdrop := Art.texture("hall-backdrop-v2")
		if backdrop != null:
			panel.draw_texture_rect(backdrop, Rect2(position, Vector2(_content.size.x, minf(400, _content.size.y * 0.68))), false, Color(1, 1, 1, 0.85))
	Art.frame(panel, GOLD)

func _label(text: String, font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", font_size)
	var role := "leaderboard_text"
	if color == GOLD: role = "leaderboard_title"
	elif color == MUTED: role = "leaderboard_muted"
	elif color == METALS[1]: role = "leaderboard_silver"
	elif color == METALS[2]: role = "leaderboard_bronze"
	TextColors.bind(label, role)
	return label

func _button(text: String) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 33
	button.add_theme_font_size_override("font_size", 14)
	TextColors.bind(button, "leaderboard_text")
	TextColors.bind(button, "leaderboard_title", "font_pressed_color")
	button.add_theme_stylebox_override("normal", _box(Color("1c1e24"), Color("8b7046"), 1, 3, 5))
	button.add_theme_stylebox_override("hover", _box(Color("303035"), GOLD, 1, 3, 6))
	button.add_theme_stylebox_override("pressed", _box(Color("54251d"), GOLD, 1, 3, 6))
	button.add_theme_stylebox_override("focus", _box(Color("303035"), GOLD, 1, 3, 5))
	return button

func _box(background: Color, border: Color, width: int, radius: int, margin: float) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = background
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(radius)
	box.set_content_margin_all(margin)
	return box
