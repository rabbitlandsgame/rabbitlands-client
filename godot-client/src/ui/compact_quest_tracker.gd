extends PanelContainer
## Shared quest chrome. It changes presentation only; owners dispatch actions.
const TextColors := preload("res://src/ui/text_colors.gd")
const MENU_MARKS := {
	"instructions": '<path d="M10 5C7 3 4 3 2 4v12c3-1 5-1 8 1m0-12c3-2 6-2 8-1v12c-3-1-5-1-8 1V5z"/>',
	"replay": '<path d="M4 8a6.5 6.5 0 1 1 0 5M4 3v5h5"/>',
	"hide": '<path d="M2 2l16 16M8 4c5-1 8 3 10 6-1 2-2 3-4 4M5 5c-1 1-2 3-3 5 2 3 5 6 8 6l2-.2"/><path d="M8 8a3 3 0 0 0 4 4"/>',
	"untrack": '<path d="M5 8V3h10v14l-5-3-5 3v-5M2 10h7"/>'}
static var _menu_icons: Dictionary = {}
signal compact_toggled(value: bool)
signal instructions_toggled(value: bool)
signal replay_requested()
signal hide_requested()
signal untrack_requested()

var heading: Label
var objective: Label
var collapse: Button
var more: Button
var counter: Label
var secondary: Label
var progress: ProgressBar
var details: VBoxContainer
var recovery_slot: VBoxContainer
var instructions_button: Button
var replay_button: Button
var hide_button: Button
var untrack_button: Button
var alert_label: Label
var _column: VBoxContainer
var _meta: HBoxContainer
var _ribbon_counter: Label
var _menu: PanelContainer
var _compact := false
var _details_open := false
var _complete := false
var _replay_ready := false
var _replay_retry := false
var _signature := ""
var _fit_queued := false

func configure() -> void:
	if heading != null: return
	mouse_filter = Control.MOUSE_FILTER_STOP
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var style := StyleBoxFlat.new()
	style.bg_color = Color("13282cf5")
	style.border_color = Color("9f8a53")
	style.set_border_width_all(1); style.set_corner_radius_all(6)
	style.content_margin_left = 11; style.content_margin_right = 11
	style.content_margin_top = 8; style.content_margin_bottom = 8
	add_theme_stylebox_override("panel",style)
	_column = VBoxContainer.new(); _column.add_theme_constant_override("separation",5)
	add_child(_column)
	var header := HBoxContainer.new(); header.add_theme_constant_override("separation",5)
	_column.add_child(header)
	collapse = Button.new(); collapse.name = "CollapseQuest"
	collapse.text = "▾"; collapse.flat = true
	collapse.custom_minimum_size = Vector2(22,24)
	collapse.pressed.connect(func() -> void: compact_toggled.emit(not _compact))
	header.add_child(collapse)
	heading = Label.new(); heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	heading.add_theme_font_size_override("font_size",13)
	TextColors.bind(heading,"guide_heading"); header.add_child(heading)
	_ribbon_counter = Label.new(); _ribbon_counter.add_theme_font_size_override("font_size",12)
	_ribbon_counter.add_theme_color_override("font_color",Color("e9c36f")); header.add_child(_ribbon_counter)
	more = Button.new(); more.name = "QuestMore"; more.text = "More"; more.flat = true
	more.add_theme_font_size_override("font_size",12)
	more.custom_minimum_size.y = 24
	more.tooltip_text = "Instructions, Replay scene, Hide and Untrack"
	more.pressed.connect(func() -> void: close_more() if _menu.visible else open_more())
	header.add_child(more)
	objective = Label.new(); objective.name = "QuestNextAction"
	objective.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	objective.max_lines_visible = 2; objective.text_overrun_behavior = TextServer.OVERRUN_TRIM_WORD_ELLIPSIS
	objective.add_theme_font_size_override("font_size",14); _column.add_child(objective)
	progress = ProgressBar.new(); progress.name = "QuestProgress"
	progress.show_percentage = false; progress.custom_minimum_size.y = 4
	var track := StyleBoxFlat.new(); track.bg_color = Color("34504a"); track.set_corner_radius_all(2)
	var fill := StyleBoxFlat.new(); fill.bg_color = Color("81b894"); fill.set_corner_radius_all(2)
	progress.add_theme_stylebox_override("background",track); progress.add_theme_stylebox_override("fill",fill)
	_column.add_child(progress)
	_meta = HBoxContainer.new(); _meta.add_theme_constant_override("separation",8); _column.add_child(_meta)
	counter = Label.new(); counter.name = "QuestCounter"; counter.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	counter.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; counter.add_theme_font_size_override("font_size",12)
	_meta.add_child(counter)
	secondary = Label.new(); secondary.add_theme_font_size_override("font_size",12)
	secondary.add_theme_color_override("font_color",Color("bac8c2")); _meta.add_child(secondary)
	alert_label = Label.new(); alert_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	alert_label.add_theme_font_size_override("font_size",12)
	alert_label.add_theme_color_override("font_color",Color("ffb39c")); _column.add_child(alert_label)
	recovery_slot = VBoxContainer.new(); recovery_slot.name = "QuestRecovery"; _column.add_child(recovery_slot)
	details = VBoxContainer.new(); details.name = "QuestInstructions"
	details.add_theme_constant_override("separation",6); _column.add_child(details)
	_menu = PanelContainer.new(); _menu.name = "QuestMoreMenu"; _menu.set_as_top_level(true)
	_menu.z_as_relative = false; _menu.z_index = 245; _menu.hide()
	var menu_style := StyleBoxFlat.new(); menu_style.bg_color = Color("193237")
	menu_style.border_color = Color("89916b"); menu_style.set_border_width_all(1)
	menu_style.set_corner_radius_all(5); menu_style.set_content_margin_all(5)
	_menu.add_theme_stylebox_override("panel",menu_style); add_child(_menu)
	var actions := VBoxContainer.new(); actions.add_theme_constant_override("separation",2); _menu.add_child(actions)
	instructions_button = _menu_button(actions,"Instructions","Read the full objective and use its work controls.","instructions")
	replay_button = _menu_button(actions,"Replay scene","Replay the current cinematic without changing quest progress.","replay")
	var divider := HSeparator.new()
	var line := StyleBoxLine.new(); line.color = Color("53665e"); line.thickness = 1
	divider.add_theme_stylebox_override("separator",line); actions.add_child(divider)
	hide_button = _menu_button(actions,"Hide","Hide this card while keeping the quest tracked. Reopen it from Quests.","hide")
	untrack_button = _menu_button(actions,"Untrack","Stop following this quest. Your progress stays saved in Quests.","untrack")
	instructions_button.name = "QuestInstructions"; replay_button.name = "QuestReplay"
	hide_button.name = "HideQuest"; untrack_button.name = "UntrackQuest"
	instructions_button.toggle_mode = true
	instructions_button.pressed.connect(func() -> void: close_more(); instructions_toggled.emit(not _details_open))
	replay_button.pressed.connect(func() -> void:
		if _replay_ready: close_more(); replay_requested.emit())
	hide_button.pressed.connect(func() -> void: close_more(); hide_requested.emit())
	untrack_button.pressed.connect(func() -> void: close_more(); untrack_requested.emit())
	visibility_changed.connect(func() -> void:
		if not is_visible_in_tree(): close_more())
	resized.connect(func() -> void:
		if _menu.visible: _place_more())
	minimum_size_changed.connect(_queue_fit)
	set_process(false)

static func _menu_icon(identity: String) -> Texture2D:
	if not _menu_icons.has(identity):
		var svg := '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 20 20"><g fill="none" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">%s</g></svg>' % MENU_MARKS[identity]
		var image := Image.new()
		if image.load_svg_from_string(svg) != OK: return null
		_menu_icons[identity] = ImageTexture.create_from_image(image)
	return _menu_icons[identity]

func _menu_button(parent: VBoxContainer, label: String, hint: String, mark: String) -> Button:
	var button := Button.new(); button.text = label; button.tooltip_text = hint
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT; button.flat = true
	button.icon = _menu_icon(mark)
	button.add_theme_constant_override("h_separation",10)
	button.add_theme_constant_override("icon_max_width",16)
	for state: String in ["icon_normal_color","icon_hover_color","icon_pressed_color","icon_hover_pressed_color"]:
		button.add_theme_color_override(state,Color("e9c36f"))
	button.add_theme_color_override("icon_disabled_color",Color("80948d"))
	button.add_theme_font_size_override("font_size",14)
	button.custom_minimum_size.y = 34; parent.add_child(button)
	return button

func apply_presentation(title: String, summary: Dictionary, compact: bool, details_open: bool,
		replay_ready := false, replay_retry := false, complete := false) -> void:
	configure()
	_compact = compact and not complete; _details_open = details_open or complete; _complete = complete
	_replay_ready = replay_ready; _replay_retry = replay_retry
	var action := str(summary.get("objective",title))
	var amount := str(summary.get("counter",""))
	var ribbon_action := str(summary.get("ribbon_objective",""))
	if ribbon_action.is_empty(): ribbon_action = action
	heading.text = ribbon_action if _compact else title
	heading.tooltip_text = title + "\n" + str(summary.get("full_objective",action))
	heading.add_theme_font_size_override("font_size",18 if complete else 13)
	objective.text = action; objective.tooltip_text = str(summary.get("full_objective",action))
	objective.visible = not _compact and not complete and not action.is_empty()
	counter.text = amount; counter.tooltip_text = amount; counter.visible = not amount.is_empty()
	secondary.text = str(summary.get("secondary","")); secondary.visible = not secondary.text.is_empty()
	_meta.visible = not _compact and not complete and (counter.visible or secondary.visible)
	_ribbon_counter.text = str(summary.get("ribbon_counter",amount)); _ribbon_counter.tooltip_text = amount
	_ribbon_counter.visible = _compact and not amount.is_empty()
	# Allow a useful objective to keep room even with a long resource counter.
	_ribbon_counter.custom_minimum_size.x = 108 if _ribbon_counter.visible else 0
	_ribbon_counter.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_ribbon_counter.size_flags_horizontal = Control.SIZE_SHRINK_END
	progress.visible = not _compact and not complete and float(summary.get("progress",-1)) >= 0
	progress.value = clampf(float(summary.get("progress",0)),0,1) * 100
	progress.tooltip_text = amount
	alert_label.text = str(summary.get("alert","")); alert_label.visible = not complete and not alert_label.text.is_empty()
	details.visible = _details_open
	collapse.visible = not complete; more.visible = not complete
	for button: Button in [instructions_button,replay_button,hide_button,untrack_button]: button.visible = not complete
	collapse.text = "▸" if _compact else "▾"
	collapse.tooltip_text = "Expand quest card" if _compact else "Collapse to quest ribbon"
	more.text = "⋯" if _compact else "More"
	instructions_button.set_pressed_no_signal(_details_open)
	replay_button.disabled = not replay_ready
	replay_button.text = "Retry scene" if replay_retry else "Replay scene"
	replay_button.tooltip_text = "Retry the interrupted cinematic. Your progress is saved." if replay_retry \
		else "Replay the current cinematic without changing quest progress." if replay_ready else "No scene is ready to replay yet."
	if complete: close_more()
	var signature := title + JSON.stringify(summary) + str([_compact,_details_open,complete])
	if signature != _signature:
		_signature = signature; reset_size(); _queue_fit()
	if _menu.visible: _place_more()

func _queue_fit() -> void:
	if _fit_queued: return
	_fit_queued = true
	_finish_fit.call_deferred()

func _finish_fit() -> void:
	_fit_queued = false
	reset_size()

func open_more() -> void:
	if _complete or not is_visible_in_tree(): return
	_menu.show(); _place_more(); instructions_button.grab_focus()
	set_process(true)

func close_more() -> void:
	if _menu == null or not _menu.visible: return
	var focused := get_viewport().gui_get_focus_owner()
	var held := focused != null and _menu.is_ancestor_of(focused)
	_menu.hide()
	set_process(false)
	if held and is_visible_in_tree() and more.visible: more.grab_focus()

func more_is_open() -> bool:
	return _menu != null and _menu.visible

func _process(_delta: float) -> void:
	if more_is_open(): _place_more()

func _place_more() -> void:
	var area := get_viewport().get_visible_rect().grow(-8)
	_menu.custom_minimum_size.x = minf(184,area.size.x)
	_menu.reset_size()
	var button := more.get_global_rect()
	var target := Vector2(button.end.x - _menu.size.x,button.end.y + 5)
	if target.y + _menu.size.y > area.end.y: target.y = button.position.y - _menu.size.y - 5
	_menu.global_position = target.clamp(area.position,(area.end - _menu.size).max(area.position))

func _input(event: InputEvent) -> void:
	if not more_is_open(): return
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_ESCAPE:
			close_more(); get_viewport().set_input_as_handled()
		elif event.keycode in [KEY_UP,KEY_DOWN]:
			var enabled: Array[Button] = []
			for button: Button in [instructions_button,replay_button,hide_button,untrack_button]:
				if not button.disabled: enabled.append(button)
			var index := enabled.find(get_viewport().gui_get_focus_owner())
			enabled[posmod(index + (1 if event.keycode == KEY_DOWN else -1),enabled.size())].grab_focus()
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.pressed \
			and not _menu.get_global_rect().has_point(event.position) and not more.get_global_rect().has_point(event.position):
		close_more()
