extends RefCounted
## Shared Classic rows frame. Only viewport changes alter its outer size.
const Parts := preload("res://src/ui/crafting_window_parts.gd")
const SIZE := Vector2(510, 740)
static var _radio_icons: Dictionary = {}

static func build(window: PanelContainer, owner_main: Node, active: int,
		navigate: Callable, refresh: Callable, preview: Callable, review: Callable) -> Dictionary:
	window.theme = owner_main.theme.duplicate() as Theme if owner_main.theme != null else Theme.new()
	window.theme.default_font_size = 12
	window.theme.set_color("font_color", "Label", Parts.IVORY)
	for type: String in ["Button", "MenuButton", "OptionButton"]:
		window.theme.set_font_size("font_size", type, 12)
		window.theme.set_constant("h_separation", type, 4)
		window.theme.set_constant("icon_max_width", type, 20)
		for state: String in ["normal", "hover", "pressed", "focus", "disabled"]:
			window.theme.set_stylebox(state, type, Parts.style(Parts.BRONZE, Color("514026") if state == "pressed" else Color("1c1a15"), 4))
	for state: String in ["normal", "hover", "pressed", "focus", "disabled"]:
		window.theme.set_stylebox(state, "CheckBox", StyleBoxEmpty.new())
	window.theme.set_constant("h_separation", "CheckBox", 4)
	for icon: String in ["checked", "unchecked", "checked_disabled", "unchecked_disabled", "radio_checked", "radio_unchecked", "radio_checked_disabled", "radio_unchecked_disabled"]:
		window.theme.set_icon(icon, "CheckBox", ThemeDB.get_default_theme().get_icon(icon, "CheckBox"))
	window.theme.set_icon("radio_checked", "CheckBox", _radio_icon(true))
	window.theme.set_icon("radio_unchecked", "CheckBox", _radio_icon(false))
	window.theme.set_color("font_color", "CheckBox", Parts.IVORY)
	window.theme.set_color("font_pressed_color", "CheckBox", Parts.IVORY)
	window.theme.set_color("icon_normal_color", "CheckBox", Color.WHITE)
	window.add_theme_stylebox_override("panel", Parts.style(Parts.BRONZE, Color("12120f"), 8))
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 6)
	window.add_child(body)
	var header := HBoxContainer.new()
	body.add_child(header)
	var title := Parts.label(header, "RL Enchanting", 13)
	title.autowrap_mode = TextServer.AUTOWRAP_OFF
	title.clip_text = true
	title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	Parts.label(header, "Auto-update", 11).modulate = Color("b0c69a")
	var more := MenuButton.new()
	more.text = "•••"
	more.tooltip_text = "Connection and cost checks"
	more.custom_minimum_size = Vector2(28, 26)
	header.add_child(more)
	more.get_popup().add_item("Retry connection", 0)
	more.get_popup().add_item("Check costs", 1)
	more.get_popup().id_pressed.connect(func(id: int) -> void:
		if id == 0: refresh.call()
		else: preview.call())
	Parts.button(header, "×", window.hide).tooltip_text = "Close crafting window"
	var dragger := WindowDrag.attach(window, header)
	dragger.reserved_bottom = 88
	var tabs := Parts.navigation(body, active, navigate)
	var columns := HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 10)
	body.add_child(columns)
	var left := VBoxContainer.new()
	left.custom_minimum_size.x = 136
	left.add_theme_constant_override("separation", 5)
	columns.add_child(left)
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	columns.add_child(scroll)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 5)
	scroll.add_child(right)
	var totals := Parts.label(body, "Total cost", 11)
	totals.autowrap_mode = TextServer.AUTOWRAP_OFF
	totals.clip_text = true
	totals.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var cost_scroll := ScrollContainer.new()
	cost_scroll.custom_minimum_size.y = 64
	cost_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(cost_scroll)
	var costs := VBoxContainer.new()
	costs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	costs.add_theme_constant_override("separation", 2)
	cost_scroll.add_child(costs)
	var odds := HBoxContainer.new()
	odds.add_theme_constant_override("separation", 5)
	body.add_child(odds)
	var status := Parts.label(body, "", 11)
	status.custom_minimum_size.y = 28
	status.max_lines_visible = 2
	status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var confirm := Parts.button(body, "Review changes", review, true)
	return {"title":title, "tabs":tabs, "columns":columns, "left":left, "right":right,
		"scroll":scroll, "costs":costs, "odds":odds, "status":status,
		"totals":totals, "confirm":confirm, "more":more, "dragger":dragger}

static func fit(window: Control, placed: bool) -> void:
	if not window.is_inside_tree() or not window.visible: return
	var viewport := window.get_viewport_rect().size
	window.custom_minimum_size = Vector2.ZERO
	window.size = Vector2(minf(SIZE.x, maxf(360, viewport.x - 112)), minf(SIZE.y, maxf(350, viewport.y - 112)))
	var desired := window.position if placed else (viewport - window.size - Vector2(96, 88)) / 2
	window.position = Vector2(clampf(desired.x, 8, maxf(8, viewport.x - window.size.x - 104)),
		clampf(desired.y, 8, maxf(8, viewport.y - window.size.y - 96)))

static func _radio_icon(checked: bool) -> Texture2D:
	if not _radio_icons.has(checked):
		var dot := '<circle cx="8" cy="8" r="3" fill="#eee3c8"/>' if checked else ""
		var image := Image.new()
		image.load_svg_from_string('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><circle cx="8" cy="8" r="6" fill="none" stroke="#eee3c8" stroke-width="1.5"/>' + dot + '</svg>')
		_radio_icons[checked] = ImageTexture.create_from_image(image)
	return _radio_icons[checked]
