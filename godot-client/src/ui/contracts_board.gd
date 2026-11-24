extends Control
## The server owns offers, availability, rewards and all contract progress.
signal action_requested(action: String, identity: String, revision: int)
signal navigation_requested(entry: Dictionary)
var panel: PanelContainer
var heading: Label
var account: Label
var weekly: Label
var tabs: TabContainer
var discipline: OptionButton
var columns := {}
var state := {}
var _pending := false
var _signature := ""
var _confirm: ConfirmationDialog
var _abandon := ""
var _abandon_skill := ""
var _discipline_row: HBoxContainer
var _offer_count: Label
var _skill_filter := ""

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel = PanelContainer.new(); panel.name = "LandfallContracts"; add_child(panel)
	panel.z_index = 26; panel.mouse_filter = Control.MOUSE_FILTER_STOP
	var style := StyleBoxFlat.new(); style.bg_color = Color("17272ff5"); style.border_color = Color("a88b53")
	style.set_border_width_all(1); style.set_corner_radius_all(6)
	for edge: int in [SIDE_LEFT,SIDE_TOP,SIDE_RIGHT,SIDE_BOTTOM]: style.set_content_margin(edge,12)
	panel.add_theme_stylebox_override("panel",style)
	var body := VBoxContainer.new(); panel.add_child(body)
	var header := HBoxContainer.new(); body.add_child(header); WindowDrag.attach(panel,header)
	heading = Label.new(); heading.text = "Landfall Contracts"; heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_theme_color_override("font_color",Color("e5bd74")); header.add_child(heading)
	var close := Button.new(); close.text = "×"; close.tooltip_text = "Close the board"; header.add_child(close)
	close.pressed.connect(panel.hide)
	account = Label.new(); account.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; body.add_child(account)
	weekly = Label.new(); weekly.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; body.add_child(weekly)
	_text(body,"Keep up to three contracts accepted and one tracked. Each discipline can be claimed once per UTC day; unfinished progress is retained.",Color("b8c7cf"))
	_discipline_row = HBoxContainer.new(); _discipline_row.name = "ContractsDisciplineFilter"; body.add_child(_discipline_row)
	var filter_label := Label.new(); filter_label.text = "Discipline"
	filter_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER; _discipline_row.add_child(filter_label)
	discipline = OptionButton.new(); discipline.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	discipline.size_flags_vertical = Control.SIZE_SHRINK_CENTER; discipline.custom_minimum_size.y = 32
	discipline.add_item("All disciplines")
	for skill: String in EloriaProtocol.ContractsProtocol.SKILLS: discipline.add_item(skill.capitalize())
	discipline.tooltip_text = "Browse offers by discipline. Your accepted assignments stay the same."
	_discipline_row.add_child(discipline)
	_offer_count = Label.new(); _offer_count.size_flags_vertical = Control.SIZE_SHRINK_CENTER; _discipline_row.add_child(_offer_count)
	discipline.item_selected.connect(func(index: int) -> void:
		_skill_filter = "" if index == 0 else str(EloriaProtocol.ContractsProtocol.SKILLS[index-1])
		_render_available(); _fit())
	tabs = TabContainer.new(); tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL; body.add_child(tabs)
	tabs.tab_changed.connect(func(index: int) -> void: _discipline_row.visible = index == 0; _fit())
	for title: String in ["Available","Accepted","Marks"]:
		var scroll := ScrollContainer.new(); scroll.name = title; scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		tabs.add_child(scroll)
		var column := VBoxContainer.new(); column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		scroll.add_child(column); columns[title] = column
	var refresh := Button.new(); refresh.text = "Refresh board"; body.add_child(refresh)
	refresh.pressed.connect(func() -> void: action_requested.emit("board","",-1))
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
	panel.size = Vector2(minf(640,available.x-24),minf(560,available.y-32))
	panel.position = ((available-panel.size)*0.5).max(Vector2(12,12))

func _text(parent: Node, value: String, color := Color.WHITE) -> void:
	var label := Label.new(); label.text = value; label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color",color); parent.add_child(label)

static func reward_text(reward: Dictionary) -> String:
	var parts: PackedStringArray = []
	for skill: String in reward.get("xp",{}): parts.append("%d %s XP" % [int(reward.xp[skill]),skill.capitalize()])
	if int(reward.get("gold",0)): parts.append("%d gold" % int(reward.gold))
	if int(reward.get("marks",0)): parts.append("%d marks" % int(reward.marks))
	for item: Dictionary in reward.get("items",[]): parts.append("%d %s" % [int(item.count),str(item.name)])
	return " · ".join(parts)

func _button(parent: Node, text: String, action: String, identity: String, enabled := true, reason := "") -> Button:
	var button := Button.new(); button.text = text; button.disabled = not enabled or _pending
	button.custom_minimum_size = Vector2(112,32)
	button.tooltip_text = reason; button.pressed.connect(_send.bind(action,identity)); parent.add_child(button)
	return button

func _send(action: String, identity: String) -> void:
	if _pending: return
	_pending = true
	action_requested.emit(action,identity,int(state.get("revision",0)))
	# No optimistic progress or reward update; the next snapshot settles it.
	for column: VBoxContainer in columns.values():
		for button: Node in column.find_children("*","Button",true,false): button.disabled = true

func _entry(column: VBoxContainer, entry: Dictionary, accepted: bool) -> void:
	var box := VBoxContainer.new(); column.add_child(box)
	box.set_meta("contract_skill",str(entry.skill))
	_text(box,str(entry.title),Color("e5bd74"))
	var route := str(entry.get("route_label",""))
	if route.is_empty(): route = str(entry.route).replace("_"," ").capitalize()+" route"
	_text(box,"%s · %s · %s" % [str(entry.skill).capitalize(),str(entry.tier),route],Color("b8c7cf"))
	_text(box,str(entry.description))
	_text(box,"Rewards · " + reward_text(entry.reward),Color("bdd2bc"))
	_text(box,"Where · " + str(entry.location.label),Color("b8c7cf"))
	for objective: Dictionary in entry.objectives:
		_text(box,"%s · %d / %d" % [str(objective.label),int(objective.current),int(objective.target)])
	if not str(entry.reason).is_empty(): _text(box,str(entry.reason),Color("dbb98d"))
	var actions := HFlowContainer.new(); box.add_child(actions)
	if accepted:
		var tracked := str(state.get("tracked_id","")) == str(entry.id)
		_button(actions,"Untrack" if tracked else "Track","untrack" if tracked else "track","" if tracked else str(entry.id))
		if tracked:
			var go := Button.new(); go.text = "Show on map"; actions.add_child(go)
			go.pressed.connect(func() -> void: navigation_requested.emit(entry))
		if str(entry.status) == "ready":
			_button(actions,"Report contract","claim",str(entry.id),bool(entry.eligible),str(entry.reason))
			var donation: Dictionary = entry.get("donation",{})
			if not donation.is_empty():
				_text(box,"Optional donation · %d %s for %d extra gold. The ordinary report keeps your goods." % [int(donation.count),str(donation.item),int(donation.gold)],Color("b8c7cf"))
				_button(actions,"Report + donate","donate",str(entry.id),bool(donation.eligible),str(donation.reason))
		var abandon := Button.new(); abandon.text = "Abandon"; actions.add_child(abandon)
		abandon.pressed.connect(func() -> void: _abandon = str(entry.id); _abandon_skill = str(entry.skill); _confirm.popup_centered())
	else:
		_button(actions,"Accept","accept",str(entry.id),bool(entry.eligible),str(entry.reason))
		_button(actions,"Reroll","reroll",str(entry.skill),bool(entry.get("can_reroll",false)),str(entry.get("reroll_reason","")))
	box.add_child(HSeparator.new())

func reset_contracts(skills: Array) -> void:
	if _abandon_skill in skills:
		_confirm.hide(); _abandon = ""; _abandon_skill = ""
	# Rebuild from the next authoritative board, including any settled request.
	_signature = ""

func _render_available() -> void:
	var column: VBoxContainer = columns.get("Available")
	if column == null: return
	for child: Node in column.get_children(): column.remove_child(child); child.queue_free()
	var count := 0
	for entry: Dictionary in state.get("offers",[]):
		if not _skill_filter.is_empty() and str(entry.skill) != _skill_filter: continue
		_entry(column,entry,false); count += 1
	_offer_count.text = "%d offers" % count
	if count == 0: _text(column,"No offers posted for this discipline.",Color("b8c7cf"))
	# Helping a party member is separate from accepting personal work.
	for join: Dictionary in state.get("joins",[]):
		_text(column,"Party · %s — %s" % [str(join.owner),str(join.title)],Color("e5bd74"))
		_button(column,"Join " + str(join.owner),"join",str(join.owner),bool(join.eligible),str(join.reason))
		if not str(join.reason).is_empty(): _text(column,str(join.reason),Color("dbb98d"))

func apply_state(value: Dictionary, allow_open := true) -> void:
	var signature := JSON.stringify(value)
	if is_node_ready() and signature == _signature and not _pending:
		if allow_open and bool(state.get("open",false)): panel.show(); panel.move_to_front()
		return
	_signature = signature
	state = value.duplicate(true); _pending = false
	if not is_node_ready(): return
	for column: VBoxContainer in columns.values():
		for child: Node in column.get_children(): column.remove_child(child); child.queue_free()
	account.text = "Accepted %d / %d · %d marks · UTC day %s · Resets 00:00 UTC" % [(state.get("accepted",[]) as Array).size(),int(state.get("accepted_limit",3)),int(state.get("marks",0)),str(state.get("day",""))]
	var progress: Dictionary = state.get("weekly",{})
	weekly.text = "Weekly · %d / 5 completed · %s" % [int(progress.get("count",0)),"3 bonus marks awarded" if bool(progress.get("awarded",false)) else "+3 marks on your fifth completion"]
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
