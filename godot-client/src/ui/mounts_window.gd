extends Control
## Selection is a local browse choice; riding and the saved default are confirmed
## only by the server snapshot. The same commands support the headless probe.
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const Portrait := preload("res://src/mounts/mount_portrait.gd")
const Hotkeys := preload("res://src/mounts/mount_hotkeys.gd")
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

func _ready() -> void:
	name = "MountsLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	get_viewport().size_changed.connect(func() -> void: _fit_panel.call_deferred())
	send_command = get_node("/root/Network").send_chat
	AppState.state_changed.connect(_changed)
	sync()

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "MountsWindow"
	panel.position = Vector2(65, 65)
	panel.custom_minimum_size = Vector2(minf(Profiles.PATHS.size() * 272.0 + 16.0,
		maxf(360.0, get_viewport_rect().size.x - 112.0)), 385)
	panel.size = Vector2(panel.custom_minimum_size.x, 445)
	panel.add_theme_stylebox_override("panel", _box(Color("121d24"), Color("937342"), 2, 14))
	panel.hide()
	add_child(panel)
	# Wrapped status text may briefly request extra height while its new width
	# settles. Shrink again after layout, including server call/riding updates.
	panel.minimum_size_changed.connect(func() -> void: _fit_panel.call_deferred())
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	panel.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.text = "Mounts"
	title.add_theme_font_size_override("font_size", 24)
	title.add_theme_color_override("font_color", Color("efdcb7"))
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_button := Button.new()
	close_button.text = "X"
	close_button.focus_mode = Control.FOCUS_NONE
	close_button.pressed.connect(close)
	header.add_child(close_button)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size.y = 300
	column.add_child(scroll)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	scroll.add_child(row)
	for id: String in Profiles.PATHS:
		var card := PanelContainer.new()
		card.custom_minimum_size = Vector2(260, 270)
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		card.gui_input.connect(func(event: InputEvent) -> void:
			if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
				choose(id)
				card.accept_event())
		row.add_child(card)
		cards[id] = card
		var body := VBoxContainer.new()
		body.mouse_filter = Control.MOUSE_FILTER_IGNORE
		card.add_child(body)
		var title_label := Label.new()
		title_label.text = Profiles.display_name(id)
		title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		title_label.add_theme_font_size_override("font_size", 18)
		title_label.add_theme_color_override("font_color", Color("efdcb7"))
		body.add_child(title_label)
		var image := Portrait.new()
		image.mouse_filter = Control.MOUSE_FILTER_IGNORE
		image.custom_minimum_size = Vector2(220, 215)
		body.add_child(image)
		portraits[id] = image
		var label := Button.new()
		label.focus_mode = Control.FOCUS_NONE
		label.pressed.connect(choose.bind(id))
		body.add_child(label)
		labels[id] = label
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.add_theme_font_size_override("font_size", 14)
	status.add_theme_color_override("font_color", Color("d8d1bf"))
	column.add_child(status)
	var actions := HBoxContainer.new()
	actions.alignment = BoxContainer.ALIGNMENT_CENTER
	actions.add_theme_constant_override("separation", 12)
	column.add_child(actions)
	for button: Button in [ride, dismount]:
		button.custom_minimum_size = Vector2(180, 36)
		button.focus_mode = Control.FOCUS_NONE
		button.add_theme_font_size_override("font_size", 16)
		button.add_theme_color_override("font_color", Color("f2e5c9"))
		button.add_theme_stylebox_override("normal", _box(Color("293e31"), Color("967d48"), 1, 7))
		button.add_theme_stylebox_override("hover", _box(Color("3a5140"), Color("d4b96e"), 1, 7))
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
	_fit_panel.call_deferred()

func _fit_panel() -> void:
	if not is_inside_tree() or not panel.visible:
		return
	panel.custom_minimum_size.x = minf(Profiles.PATHS.size() * 272.0 + 16.0,
		maxf(360.0, get_viewport_rect().size.x - 112.0))
	panel.reset_size()
	if _first_layout:
		var screen := get_viewport_rect().size
		panel.position = Vector2(maxf(6, (screen.x - 96 - panel.size.x) * .5),
			maxf(6, (screen.y - 40 - panel.size.y) * .5))
		_first_layout = false
	(panel.get_node("WindowDrag") as WindowDrag).clamp_into_view()

func close() -> void:
	panel.hide()
	if _portraits_built:
		for portrait: Variant in portraits.values():
			portrait.set_active(false)

func choose(id: String) -> void:
	if Profiles.supports(id):
		candidate = id
		sync()
		(cards[id].get_parent().get_parent() as ScrollContainer).ensure_control_visible(cards[id])

func _state() -> Dictionary:
	return AppState.actor_mounts.get(AppState.local_actor_id, {})

func _changed(section: StringName) -> void:
	if section in [&"mount_states", &"map", &"local_actor", &"authentication"]:
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
	for id: String in cards:
		var selected := candidate == id
		(cards[id] as PanelContainer).add_theme_stylebox_override("panel",
			_box(Color("1b262b"), Color("e1bd6b") if selected else Color("5d605a"), 2 if selected else 1, 8))
		(labels[id] as Button).text = "Selected" if selected else ("Available" if id in owned else "Unavailable")
		(labels[id] as Button).disabled = id not in owned
	var already_riding := mode != "on_foot" and str(state.get("mount_id", "")) == candidate
	ride.disabled = not AppState.authenticated or state.is_empty() or candidate not in owned \
		or already_riding or not str(state.get("blocked_reason", "")).is_empty()
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
			"restricted_area": status.text = "Mounts can be ridden outdoors."
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
