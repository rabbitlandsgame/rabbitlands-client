extends Control
## The server owns offers, availability, rewards and all contract progress.
signal action_requested(action: String, identity: String, revision: int)
signal navigation_requested(entry: Dictionary)
const Surface := preload("res://src/ui/contracts_noticeboard_surface.gd")
const INK := Color("392b21")
const MUTED_INK := Color("65503b")
var panel: PanelContainer
var heading: Label
var account: Label
var weekly: Label
var tabs: TabContainer
var _discipline_buttons := {}
var columns := {}
var state := {}
var _pending := false
var _signature := ""
var _confirm: ConfirmationDialog
var _abandon := ""
var _abandon_skill := ""
var _discipline_row: HFlowContainer
var _offer_count: Label
var _skill_filter := ""
var _requested_skill := ""
var _nav_buttons: Array[Button] = []
var _title_font: SystemFont
var encounter_leave_button: Button

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_title_font = SystemFont.new(); _title_font.font_names = PackedStringArray(["Georgia","Liberation Serif","Noto Serif","serif"])
	panel = Surface.new(); panel.name = "LandfallContracts"; add_child(panel)
	panel.z_index = 26; panel.mouse_filter = Control.MOUSE_FILTER_STOP
	var body := VBoxContainer.new(); panel.add_child(body)
	body.add_theme_constant_override("separation",12)
	var rail := PanelContainer.new(); body.add_child(rail)
	var rail_style := _style(Color("173c3e"),Color("ac8850"),14,10)
	rail.add_theme_stylebox_override("panel",rail_style)
	var rail_body := VBoxContainer.new(); rail_body.add_theme_constant_override("separation",10); rail.add_child(rail_body)
	var header := HBoxContainer.new(); rail_body.add_child(header)
	heading = Label.new(); heading.text = "Daily Contracts"; heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_theme_font_override("font",_title_font); heading.add_theme_font_size_override("font_size",28)
	heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	heading.add_theme_color_override("font_color",Color("e5bd74")); header.add_child(heading)
	heading.tooltip_text = "Keep up to three contracts accepted and one tracked. Each discipline can be claimed once per UTC day; unfinished progress is retained."
	var close := Button.new(); close.text = "×"; close.tooltip_text = "Close the board"; header.add_child(close)
	_style_button(close,false); close.custom_minimum_size = Vector2(32,32)
	close.pressed.connect(panel.hide)
	WindowDrag.attach(panel,header)
	var toolbar := HFlowContainer.new(); toolbar.add_theme_constant_override("h_separation",18); rail_body.add_child(toolbar)
	var navigation := HBoxContainer.new(); toolbar.add_child(navigation)
	var selection := ButtonGroup.new()
	for title: String in ["Available","Accepted","Marks"]:
		var index := _nav_buttons.size()
		var button := Button.new(); button.text = title; button.toggle_mode = true; button.button_group = selection
		_style_button(button,false); navigation.add_child(button); _nav_buttons.append(button)
		button.pressed.connect(func() -> void: tabs.current_tab = index)
	_nav_buttons[0].button_pressed = true
	_offer_count = Label.new(); _offer_count.size_flags_vertical = Control.SIZE_SHRINK_CENTER; toolbar.add_child(_offer_count)
	_discipline_row = HFlowContainer.new(); _discipline_row.name = "ContractsDisciplineFilter"; rail_body.add_child(_discipline_row)
	_discipline_row.add_theme_constant_override("h_separation",12)
	_discipline_row.add_theme_constant_override("v_separation",4)
	var disciplines := ButtonGroup.new()
	for skill: String in EloriaProtocol.ContractsProtocol.SKILLS:
		var button := CheckBox.new(); button.name = skill.capitalize()+"Contracts"; button.text = skill.capitalize()
		button.button_group = disciplines; button.custom_minimum_size.y = 32
		button.add_theme_color_override("font_color",Color("fff0d4"))
		button.add_theme_color_override("font_pressed_color",Color("e5bd74"))
		button.add_theme_color_override("font_disabled_color",Color("a7b6b0"))
		button.add_theme_color_override("checkbox_checked_color",Color("e5bd74"))
		button.add_theme_color_override("checkbox_unchecked_color",Color("c4c6b1"))
		button.tooltip_text = "Browse "+skill+" offers. Your accepted assignments stay the same."
		_discipline_row.add_child(button); _discipline_buttons[skill] = button
		button.pressed.connect(_on_discipline_pressed.bind(skill))
	tabs = TabContainer.new(); tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL; body.add_child(tabs)
	tabs.tabs_visible = false; tabs.add_theme_stylebox_override("panel",StyleBoxEmpty.new())
	tabs.tab_changed.connect(func(index: int) -> void:
		_discipline_row.visible = index == 0
		_offer_count.visible = index == 0
		_nav_buttons[index].button_pressed = true; _fit())
	for title: String in ["Available","Accepted","Marks"]:
		var scroll := ScrollContainer.new(); scroll.name = title; scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		tabs.add_child(scroll)
		var column: Container = VBoxContainer.new() if title == "Marks" else GridContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		column.size_flags_vertical = Control.SIZE_EXPAND_FILL
		column.add_theme_constant_override("h_separation",16); column.add_theme_constant_override("v_separation",16)
		scroll.add_child(column); columns[title] = column
	var footer := HBoxContainer.new(); footer.add_theme_constant_override("separation",12); body.add_child(footer)
	account = Label.new(); account.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	account.size_flags_horizontal = Control.SIZE_EXPAND_FILL; account.add_theme_font_size_override("font_size",13); footer.add_child(account)
	weekly = Label.new(); weekly.add_theme_font_size_override("font_size",13); footer.add_child(weekly)
	encounter_leave_button = Button.new(); encounter_leave_button.name = "LeaveContractEncounter"
	_style_button(encounter_leave_button); footer.add_child(encounter_leave_button)
	encounter_leave_button.pressed.connect(_send.bind("leave","")); encounter_leave_button.hide()
	var refresh := Button.new(); refresh.text = "Refresh board"; _style_button(refresh,false); footer.add_child(refresh)
	refresh.pressed.connect(func() -> void: action_requested.emit("board",_requested_skill if not _requested_skill.is_empty() else _skill_filter if state.has("offer_skill") else "",-1))
	_confirm = ConfirmationDialog.new(); _confirm.title = "Abandon contract?"; add_child(_confirm)
	_confirm.dialog_text = "Abandon this contract and lose its current progress? Earned completed rewards are kept."
	_confirm.confirmed.connect(func() -> void: _send("abandon",_abandon))
	get_viewport().size_changed.connect(_fit)
	# Native descriptions arrive before their wrapping labels have a width.
	# Refit after that layout settles so the initial open fits too.
	panel.minimum_size_changed.connect(_fit.call_deferred)
	_fit(); panel.hide()

func _fit() -> void:
	if panel == null: return
	var available := get_viewport_rect().size
	panel.custom_minimum_size = Vector2.ZERO
	panel.size = Vector2(minf(900,available.x-24),minf(520 if _discipline_row.visible else 480,available.y-52))
	var paired := panel.size.x >= 740 and get_window().size.x >= 760
	for title: String in ["Available","Accepted"]:
		var grid: GridContainer = columns.get(title)
		if grid != null: grid.columns = 2 if paired and grid.get_child_count() > 1 else 1
	panel.position = ((available-panel.size)*0.5).max(Vector2(12,12))

func _sync_discipline_selection() -> void:
	for skill: String in _discipline_buttons:
		var button: CheckBox = _discipline_buttons[skill]
		button.set_pressed_no_signal(skill == _skill_filter)
		button.disabled = _pending

func _on_discipline_pressed(skill: String) -> void:
	if _pending or skill == _skill_filter:
		_sync_discipline_selection(); return
	if state.has("offer_skill"):
		_requested_skill = skill
		_sync_discipline_selection()
		_send("board",skill)
	else:
		# Older recorded packets contain every discipline in one snapshot.
		_skill_filter = skill; _sync_discipline_selection()
	_render_available(); _fit()

func _text(parent: Node, value: String, color := Color.WHITE) -> Label:
	var label := Label.new(); label.text = value; label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color",color); parent.add_child(label)
	return label

func _style(background: Color, border: Color, horizontal := 12, vertical := 6) -> StyleBoxFlat:
	var style := StyleBoxFlat.new(); style.bg_color = background; style.border_color = border
	style.set_border_width_all(1); style.set_corner_radius_all(3)
	style.content_margin_left = horizontal; style.content_margin_right = horizontal
	style.content_margin_top = vertical; style.content_margin_bottom = vertical
	return style

func _style_button(button: Button, primary := true) -> void:
	var base := Color("235955") if primary else Color("293a39")
	button.add_theme_stylebox_override("normal",_style(base,Color("b99659")))
	button.add_theme_stylebox_override("hover",_style(base.lightened(0.18),Color("efca7d")))
	button.add_theme_stylebox_override("pressed",_style(Color("586449"),Color("efca7d")))
	button.add_theme_stylebox_override("disabled",_style(Color("38403b"),Color("897b60")))
	button.add_theme_stylebox_override("focus",_style(Color(0,0,0,0),Color("ffe2a0")))
	button.add_theme_color_override("font_color",Color("fff0d4"))
	button.add_theme_color_override("font_hover_color",Color.WHITE)
	button.add_theme_color_override("font_pressed_color",Color("fff0d4"))
	button.add_theme_color_override("font_disabled_color",Color("c6bdab"))
	button.custom_minimum_size.y = 34

static func number_text(value: int) -> String:
	var digits := str(maxi(0,value)); var grouped := ""
	while digits.length() > 3:
		grouped = ","+digits.right(3)+grouped; digits = digits.left(digits.length()-3)
	return digits+grouped

static func reward_text(reward: Dictionary) -> String:
	var parts: PackedStringArray = []
	for skill: String in reward.get("xp",{}): parts.append("%s %s XP" % [number_text(int(reward.xp[skill])),skill.capitalize()])
	if int(reward.get("gold",0)): parts.append("%s gold" % number_text(int(reward.gold)))
	if int(reward.get("marks",0)): parts.append("%s marks" % number_text(int(reward.marks)))
	for item: Dictionary in reward.get("items",[]): parts.append("%s %s" % [number_text(int(item.count)),str(item.name)])
	return " · ".join(parts)

func _button(parent: Node, text: String, action: String, identity: String, enabled := true, reason := "") -> Button:
	var button := Button.new(); button.text = text; button.disabled = not enabled or _pending
	button.custom_minimum_size = Vector2(112,32)
	_style_button(button,action in ["accept","claim","join"])
	button.tooltip_text = reason; button.pressed.connect(_send.bind(action,identity)); parent.add_child(button)
	return button

func _send(action: String, identity: String) -> void:
	if _pending: return
	_pending = true
	encounter_leave_button.disabled = true
	_sync_discipline_selection()
	# No optimistic progress or reward update; the next snapshot settles it.
	for column: Container in columns.values():
		for button: Node in column.find_children("*","Button",true,false): button.disabled = true
	action_requested.emit(action,identity,int(state.get("revision",0)))

func _entry(column: Container, entry: Dictionary, accepted: bool) -> void:
	var box := Surface.new(); box.paper = true; column.add_child(box)
	box.mouse_filter = Control.MOUSE_FILTER_PASS
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.custom_minimum_size.y = 268
	box.set_meta("contract_skill",str(entry.skill))
	var body := VBoxContainer.new(); body.add_theme_constant_override("separation",14); box.add_child(body)
	var explanations: PackedStringArray = []
	if not str(entry.reason).is_empty(): explanations.append(str(entry.reason))
	var preparation: Dictionary = entry.get("preparation",{})
	if not bool(preparation.get("ready",true)):
		var reason := str(preparation.get("reason",""))
		if not reason.is_empty() and reason not in explanations: explanations.append(reason)
	box.tooltip_text = "\n".join(explanations)
	var title := _text(body,str(entry.title).trim_prefix("Daily: "),INK)
	title.add_theme_font_override("font",_title_font); title.add_theme_font_size_override("font_size",22)
	var divider := HSeparator.new(); divider.add_theme_stylebox_override("separator",_style(Color("b58c4d"),Color("b58c4d"),0,0))
	body.add_child(divider)
	var step: Dictionary = entry.get("next_step",{}) if accepted else {}
	var description := str(step.get("detail",""))
	if description.is_empty(): description = str(entry.description)
	_text(body,description,INK)
	_text(body,("Where · " if accepted else "Start · ") + str((step.get("location",entry.location) as Dictionary).label),MUTED_INK)
	# The tracker and Instructions retain detailed progress and preparation.
	# This list keeps only the description, destination and available actions.
	var space := Control.new(); space.size_flags_vertical = Control.SIZE_EXPAND_FILL; body.add_child(space)
	var actions := HFlowContainer.new(); actions.add_theme_constant_override("h_separation",8); actions.add_theme_constant_override("v_separation",6); body.add_child(actions)
	if accepted:
		var tracked := str(state.get("tracked_id","")) == str(entry.id)
		_button(actions,"Untrack" if tracked else "Track","untrack" if tracked else "track","" if tracked else str(entry.id))
		if tracked:
			var go := Button.new(); go.text = "Show on map"; actions.add_child(go)
			_style_button(go,false)
			go.pressed.connect(func() -> void: navigation_requested.emit(entry))
		if str(entry.status) == "ready":
			_button(actions,"Report contract","claim",str(entry.id),bool(entry.eligible),str(entry.reason))
			var donation: Dictionary = entry.get("donation",{})
			if not donation.is_empty():
				var detail := "Donate %d %s when reporting. The ordinary report keeps your goods." % [int(donation.count),str(donation.item)]
				if not str(donation.reason).is_empty(): detail += "\n"+str(donation.reason)
				_button(actions,"Report + donate","donate",str(entry.id),bool(donation.eligible),detail)
		var abandon := Button.new(); abandon.text = "Abandon"; actions.add_child(abandon)
		_style_button(abandon,false)
		abandon.pressed.connect(func() -> void: _abandon = str(entry.id); _abandon_skill = str(entry.skill); _confirm.popup_centered())
	else:
		_button(actions,"Accept","accept",str(entry.id),bool(entry.eligible),str(entry.reason))
		_button(actions,"Reroll","reroll",str(entry.skill),bool(entry.get("can_reroll",false)),str(entry.get("reroll_reason","")))

func reset_contracts(skills: Array) -> void:
	if _abandon_skill in skills:
		_confirm.hide(); _abandon = ""; _abandon_skill = ""
	# Rebuild from the next authoritative board, including any settled request.
	_signature = ""

func _render_available() -> void:
	var column: Container = columns.get("Available")
	if column == null: return
	for child: Node in column.get_children(): column.remove_child(child); child.queue_free()
	var count := 0
	if not _requested_skill.is_empty():
		_text(column,"Loading "+_requested_skill.capitalize()+" offers…",Color("b8c7cf"))
		_offer_count.text = "Loading…"
	else:
		for entry: Dictionary in state.get("offers",[]):
			if str(entry.skill) != _skill_filter: continue
			_entry(column,entry,false); count += 1
		_offer_count.text = "%d offers" % count
		if count == 0: _text(column,"No offers posted for this discipline.",Color("b8c7cf"))
	# Helping a party member is separate from accepting personal work.
	for join: Dictionary in state.get("joins",[]):
		var invitation := VBoxContainer.new(); column.add_child(invitation)
		_text(invitation,"Party · %s — %s" % [str(join.owner),str(join.title)],Color("e5bd74"))
		_button(invitation,"Join " + str(join.owner),"join",str(join.owner),bool(join.eligible),str(join.reason))
		if not str(join.reason).is_empty(): _text(invitation,str(join.reason),Color("dbb98d"))

func apply_state(value: Dictionary, allow_open := true) -> void:
	var signature := JSON.stringify(value)
	if is_node_ready() and signature == _signature and not _pending:
		if allow_open and bool(state.get("open",false)): panel.show(); panel.move_to_front()
		return
	_signature = signature
	state = value.duplicate(true); _pending = false; _requested_skill = ""
	if state.has("offer_skill"): _skill_filter = str(state.offer_skill)
	elif _skill_filter.is_empty():
		_skill_filter = str((state.get("current",{}) as Dictionary).get("skill","melee"))
	if not is_node_ready(): return
	encounter_leave_button.visible = bool(state.get("can_leave_encounter",false))
	encounter_leave_button.disabled = false
	var current: Dictionary = state.get("current",{})
	var completed := bool(state.get("encounter_complete",false))
	var report := completed and str(current.get("status","")) == "ready" and not str(current.get("reason","")).begins_with("Helping the party.")
	encounter_leave_button.text = "Leave and report" if report else "Leave encounter" if completed else "Pause and leave"
	encounter_leave_button.tooltip_text = "Return to the public map and report to Batu. Earned progress is kept." if report \
		else "Return to the public map. Earned progress is kept; unfinished objectives can be resumed later." if completed \
		else "Leave this private encounter. Completed progress is kept; your party can continue."
	_sync_discipline_selection()
	for column: Container in columns.values():
		for child: Node in column.get_children(): column.remove_child(child); child.queue_free()
	account.text = "Accepted %d / %d · %d marks" % [(state.get("accepted",[]) as Array).size(),int(state.get("accepted_limit",3)),int(state.get("marks",0))]
	account.tooltip_text = "UTC day %s · Resets 00:00 UTC" % str(state.get("day",""))
	var progress: Dictionary = state.get("weekly",{})
	weekly.text = "Weekly · %d / 5 completed" % int(progress.get("count",0))
	_render_available()
	for entry: Dictionary in state.get("accepted",[]): _entry(columns.Accepted,entry,true)
	if (state.get("accepted",[]) as Array).is_empty(): _text(columns.Accepted,"No accepted contracts. Unfinished contracts keep their progress across the UTC reset.")
	for entry: Dictionary in state.get("catalog",[]):
		_text(columns.Marks,str(entry.title),Color("e5bd74")); _text(columns.Marks,str(entry.description))
		_text(columns.Marks,reward_text(entry.reward))
		_button(columns.Marks,"Redeem · %d marks" % int(entry.cost),"redeem",str(entry.id),bool(entry.eligible),str(entry.reason))
		if not str(entry.reason).is_empty(): _text(columns.Marks,str(entry.reason),Color("dbb98d"))
	_fit()
	if allow_open and bool(state.get("open",false)): panel.show(); panel.move_to_front()
