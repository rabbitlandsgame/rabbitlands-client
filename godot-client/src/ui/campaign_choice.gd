extends PanelContainer
## Presentation only: an emitted request is pending until authoritative state
## records a selection. Replays and party helpers cannot submit decisions.
signal option_selected(id: String, token: String)
signal continue_requested(token: String)

const Art := preload("res://src/ui/leaderboard_art.gd")
const GOLD := Color("f1cd78")
const TEXT := Color("fffaf0")

var option_buttons: Dictionary = {}
var title_label: Label
var status_label: Label
var continue_button: Button
var _column: VBoxContainer
var _grid: GridContainer
var _content: Dictionary = {}
var _payload: Dictionary = {}
var _options: Array[Dictionary] = []
var _replay := false
var _pending := ""
var _continue_pending := false
var _identity := ""
var _fingerprint := ""
var _options_fingerprint := ""
var _width := 1280.0
var _applied_width := -1.0
var _measure_revision := 0
var _continue_binding: Callable
var _error := ""
var _embedded := false
var _panel_style: StyleBoxFlat

func _init() -> void:
	name = "CampaignChoice"
	mouse_filter = Control.MOUSE_FILTER_STOP
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var panel := _box(Color(0.035, 0.05, 0.065, 0.96), Color("786341"), 1)
	panel.set_content_margin_all(10)
	_panel_style = panel
	add_theme_stylebox_override("panel", panel)
	_column = VBoxContainer.new()
	_column.add_theme_constant_override("separation", 7)
	add_child(_column)
	title_label = Label.new()
	title_label.name = "ChoiceTitle"
	title_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title_label.add_theme_font_override("font", Art.title_font())
	title_label.add_theme_color_override("font_color", GOLD)
	_column.add_child(title_label)
	_grid = GridContainer.new()
	_grid.name = "Approaches"
	_grid.columns = 3
	_grid.add_theme_constant_override("h_separation", 8)
	_grid.add_theme_constant_override("v_separation", 6)
	_column.add_child(_grid)
	status_label = Label.new()
	status_label.name = "ChoiceStatus"
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.add_theme_color_override("font_color", Color("ddd7ca"))
	_column.add_child(status_label)
	continue_button = Button.new()
	continue_button.name = "ContinueReplay"
	continue_button.text = "Continue"
	continue_button.size_flags_horizontal = Control.SIZE_SHRINK_END
	_column.add_child(continue_button)
	resized.connect(func() -> void: fit_width(size.x))
	fit_width(1280)
	reset()

func apply_choice(payload: Dictionary, replay: bool = false) -> void:
	if payload.is_empty() or not payload.get("options") is Array or (payload.options as Array).is_empty():
		reset()
		return
	var fingerprint := JSON.stringify([payload, replay])
	if visible and fingerprint == _fingerprint:
		return
	var identity := str(payload.get("token", "")) + ":" + str(payload.get("id", ""))
	var changed_context := identity != _identity or replay != _replay
	if changed_context:
		_pending = ""
		_continue_pending = false
	_identity = identity
	_fingerprint = fingerprint
	_payload = payload.duplicate(true)
	_error = str(payload.get("error", ""))
	_replay = replay
	if changed_context:
		if _continue_binding.is_valid() and continue_button.pressed.is_connected(_continue_binding):
			continue_button.pressed.disconnect(_continue_binding)
		_continue_binding = _continue.bind(str(_payload.get("token", "")))
		continue_button.pressed.connect(_continue_binding)
	_options.clear()
	var ids: Dictionary = {}
	for value: Variant in payload.options:
		if not value is Dictionary:
			continue
		var option: Dictionary = value
		var id := str(option.get("id", ""))
		if id.is_empty() or ids.has(id):
			continue
		ids[id] = true
		_options.append({"id":id, "label":str(option.get("label", id)), "detail":str(option.get("detail", ""))})
	if _options.is_empty():
		reset()
		return
	set_meta(&"dialogue_scroll_hint", "%d approaches · scroll to read all" % _options.size())
	var options_fingerprint := JSON.stringify(_options)
	var rebuilt := changed_context or options_fingerprint != _options_fingerprint
	if rebuilt:
		_options_fingerprint = options_fingerprint
		_rebuild()
	if _replay or not str(_payload.get("selected", "")).is_empty() or not bool(_payload.get("can_choose", false)):
		_pending = ""
	title_label.text = str(_payload.get("title", "Choose an approach"))
	title_label.visible = not _embedded and not title_label.text.is_empty()
	show()
	_refresh()
	_schedule_measure()
	if rebuilt or identity != str(get_meta(&"focused_choice", "")):
		_focus_choice.call_deferred(identity)

func reset() -> void:
	_payload.clear()
	_options.clear()
	_pending = ""
	_continue_pending = false
	_identity = ""
	_fingerprint = ""
	_options_fingerprint = ""
	_error = ""
	set_meta(&"dialogue_scroll_hint", "Scroll to read more.")
	set_meta(&"focused_choice", "")
	title_label.text = ""
	status_label.text = ""
	continue_button.hide()
	for button: Button in option_buttons.values():
		button.disabled = true
		button.queue_free()
	option_buttons.clear()
	_content.clear()
	_measure_revision += 1
	hide()

func release_pending(message: String = "") -> void:
	_pending = ""
	_error = message
	if not _payload.is_empty():
		_refresh()

func set_embedded(value: bool) -> void:
	if _embedded == value:
		return
	_embedded = value
	add_theme_stylebox_override("panel", StyleBoxEmpty.new() if value else _panel_style)
	title_label.visible = not value and not title_label.text.is_empty()
	_column.add_theme_constant_override("separation", 5 if value else 7)
	_grid.add_theme_constant_override("h_separation", 6 if value else 8)
	_schedule_measure()

func fit_width(width: float) -> void:
	if width <= 0 or is_equal_approx(width, _applied_width):
		return
	_width = width
	_applied_width = width
	_grid.columns = 1 if width < 620 else 3
	var compact := width < 950
	title_label.add_theme_font_size_override("font_size", 17 if compact else 20)
	status_label.add_theme_font_size_override("font_size", 13 if compact else 14)
	continue_button.add_theme_font_size_override("font_size", 15 if compact else 16)
	for row: Dictionary in _content.values():
		(row.heading as Label).add_theme_font_size_override("font_size", 16 if compact else 18)
		(row.detail as Label).add_theme_font_size_override("font_size", 13 if compact else 14)
	_schedule_measure()

func _box(fill: Color, border: Color, thickness: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = fill
	box.border_color = border
	box.set_border_width_all(thickness)
	box.set_corner_radius_all(3)
	return box

func _rebuild() -> void:
	for button: Button in option_buttons.values():
		button.disabled = true
		button.queue_free()
	option_buttons.clear()
	_content.clear()
	for option: Dictionary in _options:
		var id: String = option.id
		var button := Button.new()
		button.name = "Approach_" + id.validate_node_name()
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.custom_minimum_size = Vector2(0, 80)
		button.tooltip_text = str(option.label) + "\n" + str(option.detail)
		button.pressed.connect(_choose.bind(id, str(_payload.get("token", ""))))
		_grid.add_child(button)
		var margin := MarginContainer.new()
		margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
		margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		margin.offset_left = 10
		margin.offset_right = -10
		margin.offset_top = 8
		margin.offset_bottom = -8
		button.add_child(margin)
		var lines := VBoxContainer.new()
		lines.mouse_filter = Control.MOUSE_FILTER_IGNORE
		lines.add_theme_constant_override("separation", 4)
		margin.add_child(lines)
		var heading := Label.new()
		heading.name = "ApproachLabel"
		heading.mouse_filter = Control.MOUSE_FILTER_IGNORE
		heading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		heading.add_theme_font_override("font", Art.title_font())
		lines.add_child(heading)
		var detail := Label.new()
		detail.name = "ApproachDetail"
		detail.mouse_filter = Control.MOUSE_FILTER_IGNORE
		detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		detail.text = str(option.detail)
		lines.add_child(detail)
		option_buttons[id] = button
		_content[id] = {"heading":heading, "detail":detail, "lines":lines}
	_applied_width = -1.0
	fit_width(_width)

func _can_choose() -> bool:
	return not _replay and _pending.is_empty() and str(_payload.get("selected", "")).is_empty() \
		and not str(_payload.get("token", "")).is_empty() \
		and bool(_payload.get("can_choose", false)) and bool(_payload.get("owner_is_you", false))

func _refresh() -> void:
	var selected := str(_payload.get("selected", ""))
	var selected_label := ""
	for option: Dictionary in _options:
		var id: String = option.id
		var picked := id == selected
		if picked:
			selected_label = str(option.label)
		var button: Button = option_buttons[id]
		button.disabled = not _can_choose()
		button.focus_mode = Control.FOCUS_NONE if button.disabled else Control.FOCUS_ALL
		var normal := _box(Color("2c2617") if picked else Color("18212a"), GOLD if picked else Color("64615a"), 2 if picked else 1)
		button.add_theme_stylebox_override("normal", normal)
		button.add_theme_stylebox_override("disabled", normal)
		button.add_theme_stylebox_override("hover", _box(Color("333228"), GOLD, 2))
		button.add_theme_stylebox_override("pressed", _box(Color("40351e"), GOLD, 2))
		button.add_theme_stylebox_override("focus", _box(Color(0, 0, 0, 0), GOLD, 2))
		var row: Dictionary = _content[id]
		(row.heading as Label).text = ("✓ " if picked else "") + str(option.label)
		(row.heading as Label).add_theme_color_override("font_color", GOLD if picked else TEXT)
		(row.detail as Label).add_theme_color_override("font_color", Color("e7e0d4"))
	continue_button.visible = _replay
	continue_button.disabled = _continue_pending
	if _replay:
		status_label.text = ("Recorded choice: " + selected_label + ". Replay is read-only." if not selected_label.is_empty() else "No plan recorded yet. Replay is read-only.")
	elif not selected_label.is_empty():
		status_label.text = "Choice recorded: " + selected_label + "."
	elif not _pending.is_empty():
		status_label.text = "Waiting for your choice to be confirmed…"
	elif not _error.is_empty():
		status_label.text = _error
	elif not bool(_payload.get("owner_is_you", false)):
		var owner := str(_payload.get("owner", "")).strip_edges()
		status_label.text = "Waiting for " + (owner if not owner.is_empty() else "the story owner") + " to choose an approach."
	else:
		status_label.text = "Choose an approach to continue." if _can_choose() else "This choice is not available at this point."
	status_label.add_theme_color_override("font_color", GOLD if _replay and not selected_label.is_empty() else Color("ddd7ca"))

func _choose(id: String, token: String) -> void:
	if not visible or token != str(_payload.get("token", "")) or not option_buttons.has(id) or not _can_choose():
		return
	_pending = id
	_error = ""
	_refresh()
	option_selected.emit(id, token)

func _continue(token: String) -> void:
	if not visible or token != str(_payload.get("token", "")) or not _replay or _continue_pending:
		return
	_continue_pending = true
	continue_button.disabled = true
	continue_requested.emit(token)

func _focus_choice(identity: String) -> void:
	if not visible or identity != _identity:
		return
	set_meta(&"focused_choice", identity)
	if _replay:
		continue_button.grab_focus()
	elif _can_choose() and not _options.is_empty():
		(option_buttons[str(_options[0].id)] as Button).grab_focus()

func _schedule_measure() -> void:
	_measure_revision += 1
	if is_inside_tree():
		_measure_buttons.call_deferred(_measure_revision)

func _measure_buttons(revision: int) -> void:
	await get_tree().process_frame
	if revision != _measure_revision or not visible:
		return
	for id: String in option_buttons:
		var button: Button = option_buttons[id]
		var lines: VBoxContainer = _content[id].lines
		button.custom_minimum_size.y = maxf(64 if _grid.columns == 1 else 80, ceilf(lines.get_combined_minimum_size().y) + 16)
