extends Control
## Selection is a local browse choice; riding and the saved default are confirmed
## only by the server snapshot. The same commands support the headless probe.
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const Portrait := preload("res://src/mounts/mount_portrait.gd")
const Hotkeys := preload("res://src/mounts/mount_hotkeys.gd")
const Coats := preload("res://src/mounts/mount_coats.gd")
var panel: PanelContainer
var cards := {}
var portraits := {}
var labels := {}
var ride := Button.new()
var dismount := Button.new()
var status := Label.new()
var hints := Label.new()
var candidate := ""
var send_command: Callable
var _portraits_built := false
var _first_layout := true
const CARD_HEIGHT := 162.0
const CARD_WIDTH := 186.0
const CARD_GAP := 8
var grid: GridContainer
var scroll: ScrollContainer
var search: LineEdit
var collection_count: Label
var empty_label: Label
var _fit_queued := false
var _reveal_candidate := false
var coat_choice: OptionButton
var apply_coat: Button
var coat_drafts := {}

func _ready() -> void:
	name = "MountsLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	get_viewport().size_changed.connect(_queue_fit)
	send_command = get_node("/root/Network").send_chat
	AppState.state_changed.connect(_changed)
	sync()

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "MountsWindow"
	panel.position = Vector2(65, 65)
	panel.add_theme_stylebox_override("panel", _box(Color("121d24"), Color("937342"), 2, 12))
	panel.hide()
	add_child(panel)
	# Wrapped status text may briefly request extra height while its new width
	# settles. Shrink again after layout, including server call/riding updates.
	panel.minimum_size_changed.connect(_queue_fit)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 6)
	panel.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.text = "Mounts"
	title.add_theme_font_size_override("font_size", 22)
	title.add_theme_color_override("font_color", Color("efdcb7"))
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	collection_count = Label.new()
	collection_count.add_theme_font_size_override("font_size", 12)
	collection_count.add_theme_color_override("font_color", Color("b7af9d"))
	header.add_child(collection_count)
	var close_button := Button.new()
	close_button.text = "X"
	close_button.focus_mode = Control.FOCUS_NONE
	close_button.pressed.connect(close)
	header.add_child(close_button)
	search = LineEdit.new()
	search.placeholder_text = "Find a mount…"
	search.clear_button_enabled = true
	search.custom_minimum_size.y = 28
	search.text_changed.connect(func(_text: String) -> void: _filter_cards())
	column.add_child(search)
	scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_child(scroll)
	grid = GridContainer.new()
	grid.columns = 3
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", CARD_GAP)
	grid.add_theme_constant_override("v_separation", CARD_GAP)
	scroll.add_child(grid)
	for id: String in Profiles.PATHS:
		var card := PanelContainer.new()
		card.custom_minimum_size = Vector2(CARD_WIDTH, CARD_HEIGHT)
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		card.gui_input.connect(func(event: InputEvent) -> void:
			if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
				choose(id)
				card.accept_event())
		grid.add_child(card)
		cards[id] = card
		var body := VBoxContainer.new()
		body.add_theme_constant_override("separation", 2)
		body.mouse_filter = Control.MOUSE_FILTER_IGNORE
		card.add_child(body)
		var title_label := Label.new()
		title_label.text = Profiles.display_name(id)
		title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		title_label.add_theme_font_size_override("font_size", 14)
		title_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		title_label.custom_minimum_size.y = 32
		title_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		title_label.max_lines_visible = 2
		title_label.add_theme_color_override("font_color", Color("efdcb7"))
		body.add_child(title_label)
		var image := Portrait.new()
		image.mouse_filter = Control.MOUSE_FILTER_IGNORE
		image.custom_minimum_size = Vector2(136, 82)
		image.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		body.add_child(image)
		portraits[id] = image
		var label := Button.new()
		label.add_theme_font_size_override("font_size", 12)
		label.focus_mode = Control.FOCUS_NONE
		label.pressed.connect(choose.bind(id))
		body.add_child(label)
		labels[id] = label
	empty_label = Label.new()
	empty_label.text = "No mounts match your search."
	empty_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	empty_label.hide()
	column.add_child(empty_label)
	var coat_row := HBoxContainer.new()
	column.add_child(coat_row)
	var coat_label := Label.new()
	coat_label.text = "Coat"
	coat_row.add_child(coat_label)
	coat_choice = OptionButton.new()
	coat_choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for id: String in Coats.IDS:
		coat_choice.add_item(Coats.LABELS[id])
	coat_choice.item_selected.connect(_choose_coat)
	coat_row.add_child(coat_choice)
	apply_coat = Button.new()
	apply_coat.text = "Apply coat"
	apply_coat.pressed.connect(_apply_coat)
	coat_row.add_child(apply_coat)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.add_theme_font_size_override("font_size", 13)
	status.add_theme_color_override("font_color", Color("d8d1bf"))
	column.add_child(status)
	var actions := HBoxContainer.new()
	actions.alignment = BoxContainer.ALIGNMENT_CENTER
	actions.add_theme_constant_override("separation", 12)
	column.add_child(actions)
	for button: Button in [ride, dismount]:
		button.custom_minimum_size = Vector2(150, 32)
		button.focus_mode = Control.FOCUS_NONE
		button.add_theme_font_size_override("font_size", 15)
		button.add_theme_color_override("font_color", Color("f2e5c9"))
		button.add_theme_stylebox_override("normal", _box(Color("293e31"), Color("967d48"), 1, 5))
		button.add_theme_stylebox_override("hover", _box(Color("3a5140"), Color("d4b96e"), 1, 5))
		actions.add_child(button)
	ride.text = "Ride"
	ride.pressed.connect(_ride)
	dismount.pressed.connect(_dismount)
	hints.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hints.add_theme_font_size_override("font_size", 12)
	hints.add_theme_color_override("font_color", Color("b7af9d"))
	column.add_child(hints)

static func _box(background: Color, border: Color, width: int, margin: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(width)
	style.set_corner_radius_all(4)
	style.content_margin_left = margin
	style.content_margin_right = margin
	style.content_margin_top = margin
	style.content_margin_bottom = margin
	return style

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	if is_open():
		close()
	else:
		open()

func open() -> void:
	var state := _state()
	candidate = str(state.get("selected_mount_id", "moor_pony"))
	coat_drafts.clear()
	_reveal_candidate = true
	search.text = ""
	_filter_cards()
	panel.show()
	if panel.has_meta(WindowStack.STACK_META):
		WindowStack.activate(panel)
	else:
		panel.move_to_front()
	# Keep the entire panel on screen, clear of the fixed resource rail.
	var screen := get_viewport_rect().size
	panel.position = Vector2(clampf(panel.position.x, 4, maxf(4, screen.x - panel.size.x - 96)),
		clampf(panel.position.y, 4, maxf(4, screen.y - panel.size.y - 40)))
	if not _portraits_built:
		_portraits_built = true
		for id: String in portraits:
			portraits[id].configure(id)
	for portrait: Variant in portraits.values():
		portrait.set_active(true)
	sync()
	_queue_fit()
	if _first_layout:
		_first_layout = false
		_center_first_layout()

func _center_first_layout() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	if not is_open(): return
	var screen := get_viewport_rect().size
	panel.position = Vector2(maxf(6, (screen.x - 96 - panel.size.x) * .5),
		maxf(6, (screen.y - 86 - panel.size.y) * .5))
	(panel.get_node("WindowDrag") as WindowDrag).clamp_into_view()

func _queue_fit() -> void:
	if _fit_queued:
		return
	_fit_queued = true
	_fit_panel.call_deferred()

func _filter_cards() -> void:
	var query := search.text.strip_edges().to_lower()
	var matches := 0
	for id: String in cards:
		cards[id].visible = query.is_empty() or Profiles.display_name(id).to_lower().contains(query)
		if _portraits_built:
			portraits[id].set_active(is_open() and cards[id].visible)
		if cards[id].visible:
			matches += 1
	collection_count.text = "%d mounts" % cards.size() if query.is_empty() else "%d / %d mounts" % [matches, cards.size()]
	empty_label.visible = matches == 0
	if matches > 0 and cards.has(candidate) and not cards[candidate].visible:
		for id: String in cards:
			if cards[id].visible:
				candidate = id
				break
	scroll.scroll_vertical = 0
	sync()
	_queue_fit()

func _fit_panel() -> void:
	_fit_queued = false
	if not is_inside_tree() or not panel.visible:
		return
	var screen := get_viewport_rect().size
	var width := minf(760.0, maxf(320.0, screen.x - 112.0))
	grid.columns = clampi(int((width - 24.0 + CARD_GAP) / (CARD_WIDTH + CARD_GAP)), 1, 3)
	panel.custom_minimum_size.x = width
	var visible_count := 0
	for card: Variant in cards.values():
		if card.visible: visible_count += 1
	var rows := maxi(1, ceili(float(visible_count) / grid.columns))
	scroll.custom_minimum_size.y = minf(rows * (CARD_HEIGHT + CARD_GAP) - CARD_GAP,
		maxf(80.0, screen.y - 308.0))
	panel.reset_size()
	var excess := panel.size.y - (screen.y - 86.0)
	if excess > 0:
		scroll.custom_minimum_size.y = maxf(70.0, scroll.custom_minimum_size.y - excess)
		panel.reset_size()
	(panel.get_node("WindowDrag") as WindowDrag).clamp_into_view()
	if _reveal_candidate and cards.has(candidate) and cards[candidate].visible:
		scroll.ensure_control_visible(cards[candidate])
		_reveal_candidate = false

func close() -> void:
	panel.hide()
	if _portraits_built:
		for portrait: Variant in portraits.values():
			portrait.set_active(false)

func choose(id: String) -> void:
	if Profiles.supports(id):
		candidate = id
		sync()
		scroll.ensure_control_visible(cards[id])

func _saved_coat(id: String) -> String:
	return str(_state().get("mount_coats", {}).get(id, "original"))

func _choose_coat(index: int) -> void:
	coat_drafts[candidate] = Coats.IDS[index]
	sync()

func _apply_coat() -> void:
	if not apply_coat.disabled and send_command.is_valid():
		send_command.call("#mount coat %s %s" % [candidate, coat_drafts.get(candidate,_saved_coat(candidate))])

func _state() -> Dictionary:
	return AppState.actor_mounts.get(AppState.local_actor_id, {})

func _changed(section: StringName) -> void:
	if section in [&"mount_states", &"mount_deltas", &"mount_countdowns", &"map", &"local_actor", &"authentication"]:
		if not AppState.authenticated:
			close()
		sync()

func sync() -> void:
	if panel == null:
		return
	var state := _state()
	var owned: Array = state.get("owned_mount_ids", [state.get("selected_mount_id", "")])
	if candidate.is_empty():
		candidate = str(state.get("selected_mount_id", "moor_pony"))
	var mode := str(state.get("mode", "on_foot"))
	var chosen := str(coat_drafts.get(candidate,_saved_coat(candidate)))
	coat_choice.select(maxi(0,Coats.IDS.find(chosen)))
	coat_choice.tooltip_text = "Preview a colour or pattern, then apply it to this mount."
	apply_coat.disabled = not AppState.authenticated or candidate not in owned \
		or not state.has("mount_coats") or chosen == _saved_coat(candidate)
	apply_coat.tooltip_text = "Saved for this mount and visible to other players."
	for id: String in cards:
		var selected := candidate == id
		(cards[id] as PanelContainer).add_theme_stylebox_override("panel",
			_box(Color("1b262b"), Color("e1bd6b") if selected else Color("5d605a"), 2 if selected else 1, 6))
		(labels[id] as Button).text = "Riding" if mode == "mounted" and str(state.get("mount_id", "")) == id else ("Selected" if selected else ("Available" if id in owned else "Unavailable"))
		(labels[id] as Button).disabled = id not in owned
		if _portraits_built:
			portraits[id].set_coat(str(coat_drafts.get(id,_saved_coat(id))))
	var already_riding := mode != "on_foot" and str(state.get("mount_id", "")) == candidate
	ride.disabled = not AppState.authenticated or state.is_empty() or candidate not in owned \
		or already_riding or not cards.get(candidate, panel).visible or not str(state.get("blocked_reason", "")).is_empty()
	dismount.text = "Cancel call" if mode == "summoning" else "Dismount"
	dismount.disabled = mode == "on_foot" or not AppState.authenticated
	if mode == "mounted":
		status.text = "Riding " + Profiles.display_name(str(state.mount_id))
	elif mode == "summoning":
		status.text = "Calling %s… %.1fs" % [Profiles.display_name(str(state.mount_id)), float(state.get("summon_remaining_ms", 0)) / 1000.0]
	elif state.is_empty():
		status.text = "Waiting for your mount collection."
	else:
		match str(state.get("blocked_reason", "")):
			"restricted_area": status.text = "Mounts can be ridden outdoors and in gauntlets."
			"combat": status.text = "Finish melee combat before mounting."
			"dead": status.text = "Revive before calling a mount."
			"immobilized": status.text = "Stand up and finish your current activity before mounting."
			_: status.text = "Choose a mount, then Ride."
	hints.text = "Mount / Dismount" + Hotkeys.key_hint("toggle_mount") + "     Gallop" + Hotkeys.key_hint("toggle_gallop")

func _ride() -> void:
	if not ride.disabled and Profiles.supports(candidate) and send_command.is_valid():
		send_command.call("#mount ride " + candidate)

func _dismount() -> void:
	if not dismount.disabled and send_command.is_valid():
		send_command.call("#mount")
