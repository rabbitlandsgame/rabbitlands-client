extends CanvasLayer
## The quest's field checklist. Its controls request ordinary movement/use;
## only a new authoritative snapshot changes completion or available decisions.
signal target_requested(object_id: int, tile: Vector2i, nearby: bool)
signal action_requested(action: String)
signal decision_requested(action: String, run_id: String, revision: int)
signal companion_requested(command: String)
signal transcript_requested
signal reduced_motion_changed(value: bool)

var _panel: PanelContainer
var _body_scroll: ScrollContainer
var _title: Label
var _hint: Label
var _notice: Label
var _bank: Label
var _party: Label
var _adoption: Label
var _adoption_actions: HFlowContainer
var _record: Button
var _help_only: Button
var _join: Button
var _own: Button
var _companion: Label
var _companion_actions: HFlowContainer
var _companion_buttons: Dictionary = {}
var _scroll: ScrollContainer
var _targets: VBoxContainer
var _entry: Button
var _leave: Button
var _help: Button
var _account: Button
var _reduced: CheckButton
var _state: Dictionary = {}
var _local_tile := Vector2i.ZERO
var _target_signature := ""
var _current_map := ""

func _ready() -> void:
	layer = 85
	_build()
	hide()

func _build() -> void:
	if _panel != null:
		return
	_panel = PanelContainer.new()
	_panel.name = "CampaignFieldGuide"
	_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_panel.offset_left = -348
	_panel.offset_right = -16
	_panel.offset_top = 80
	add_child(_panel)
	_body_scroll = ScrollContainer.new()
	_body_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_body_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_panel.add_child(_body_scroll)
	var margin := MarginContainer.new()
	margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 12)
	_body_scroll.add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	margin.add_child(column)
	_title = Label.new()
	_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_title.add_theme_font_size_override("font_size", 20)
	column.add_child(_title)
	_hint = Label.new()
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_hint.add_theme_font_size_override("font_size", 16)
	column.add_child(_hint)
	_notice = Label.new()
	_notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_notice.add_theme_font_size_override("font_size", 14)
	column.add_child(_notice)
	_bank = Label.new()
	_bank.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bank.add_theme_font_size_override("font_size", 14)
	column.add_child(_bank)
	_party = Label.new()
	_party.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_party.add_theme_font_size_override("font_size", 14)
	column.add_child(_party)
	_adoption = Label.new()
	_adoption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_adoption)
	_adoption_actions = HFlowContainer.new()
	_adoption_actions.add_theme_constant_override("h_separation", 6)
	_adoption_actions.add_theme_constant_override("v_separation", 5)
	column.add_child(_adoption_actions)
	_record = Button.new()
	_record.text = "Record this outcome"
	_record.pressed.connect(_request_decision.bind("adopt"))
	_adoption_actions.add_child(_record)
	_help_only = Button.new()
	_help_only.text = "Help only"
	_help_only.pressed.connect(_request_decision.bind("help"))
	_adoption_actions.add_child(_help_only)
	_companion = Label.new()
	_companion.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_companion.add_theme_font_size_override("font_size", 14)
	column.add_child(_companion)
	_companion_actions = HFlowContainer.new()
	_companion_actions.add_theme_constant_override("h_separation", 5)
	_companion_actions.add_theme_constant_override("v_separation", 5)
	column.add_child(_companion_actions)
	for command: String in ["follow", "wait", "regroup", "help"]:
		var button := Button.new()
		button.text = command.capitalize()
		button.pressed.connect(_request_companion.bind(command))
		_companion_actions.add_child(button)
		_companion_buttons[command] = button
	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.custom_minimum_size.y = 108
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(_scroll)
	_targets = VBoxContainer.new()
	_targets.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_targets.add_theme_constant_override("separation", 5)
	_scroll.add_child(_targets)
	_entry = Button.new()
	_entry.text = "Begin The Missing Measure"
	_entry.pressed.connect(func() -> void: action_requested.emit("bank" if str(_state.get("kind", "")) == "bank" else "resume" if bool(_state.get("started", false)) else "start"))
	column.add_child(_entry)
	_join = Button.new()
	_join.text = "Join the party's expedition"
	_join.pressed.connect(func() -> void: action_requested.emit("join"))
	column.add_child(_join)
	_own = Button.new()
	_own.text = "Continue my story"
	_own.tooltip_text = "Continue your own unresolved choices. Helping this expedition does not commit its outcome for you."
	_own.pressed.connect(func() -> void: action_requested.emit("own"))
	column.add_child(_own)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	_help = Button.new()
	_help.text = "A hint"
	_help.pressed.connect(func() -> void: action_requested.emit("hint"))
	actions.add_child(_help)
	_account = Button.new()
	_account.text = "Scene account"
	_account.pressed.connect(func() -> void: transcript_requested.emit())
	actions.add_child(_account)
	_leave = Button.new()
	_leave.text = "Return"
	_leave.tooltip_text = "Return to the public road. Completed milestones are saved."
	_leave.pressed.connect(func() -> void: action_requested.emit("leave"))
	actions.add_child(_leave)
	_reduced = CheckButton.new()
	_reduced.text = "Reduced camera motion"
	_reduced.toggled.connect(func(value: bool) -> void: reduced_motion_changed.emit(value))
	column.add_child(_reduced)

func apply_state(snapshot: Dictionary, local_tile: Vector2i, current_map: String,
		reduced_motion := false, blocked := false) -> void:
	_build()
	_state = snapshot
	_local_tile = local_tile
	_current_map = EloriaProtocol.map_id_from_reference(current_map)
	var active := bool(snapshot.get("active", false))
	var matches := EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) == _current_map
	var party: Dictionary = snapshot.get("party", {})
	var can_join := bool(party.get("can_join", false))
	var can_own := bool(party.get("can_start_own", false)) and str(party.get("role", "")) != "owner"
	var travel: Dictionary = snapshot.get("travel", {})
	var travelling := not travel.is_empty()
	visible = not blocked and (active and matches or travelling or not active and (bool(snapshot.get("available", false)) or can_join or can_own))
	if not visible:
		return
	_title.text = str(travel.get("title", snapshot.get("title", "The Missing Measure")))
	_hint.text = str(snapshot.get("hint", "Explore the quay and speak with the field crew."))
	if travelling:
		_hint.text = str(travel.get("route", "Explore the public roads to " + str(travel.get("map", "Twinbrook")) + ".")) \
			+ "\nSpeak with " + str(travel.get("npc", "Odo Fenn")) + " there to continue."
	_notice.text = str(snapshot.get("party_notice", ""))
	_notice.visible = not _notice.text.is_empty()
	_apply_bank(snapshot.get("bank", {}))
	_apply_party(party, snapshot.get("adoption", {}))
	_apply_companion(snapshot.get("companion", {}))
	_entry.visible = (not active or travelling) and bool(snapshot.get("available", false)) and not can_own
	_join.visible = not active and can_join
	_own.visible = can_own
	_entry.text = ("Continue " if bool(snapshot.get("started", false)) else "Begin ") + str(snapshot.get("title", "The Missing Measure"))
	if travelling:
		_entry.text = "Continue at " + str(travel.get("npc", "Odo"))
	_leave.visible = active and not travelling
	_help.visible = active or travelling
	_account.visible = active
	_scroll.visible = active and not travelling
	_reduced.set_pressed_no_signal(reduced_motion)
	_layout()
	var rows: Array = []
	# Keep the server's clue order stable within each group, including legacy
	# encounters that have no navigation-only checkpoint.
	for navigation: bool in [true, false]:
		for target: Dictionary in snapshot.get("targets", []):
			if (int(target.get("object_id", -1)) == 0) == navigation:
				rows.append(target)
	var signature := str(snapshot.get("run_id", "")) + ":" + JSON.stringify(rows)
	for target: Dictionary in rows:
		signature += ":" + str(_nearby(target))
	if signature == _target_signature:
		return
	_target_signature = signature
	for child: Node in _targets.get_children():
		_targets.remove_child(child)
		child.queue_free()
	for target: Dictionary in rows:
		var button := Button.new()
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		button.custom_minimum_size.y = 38
		var completed := bool(target.get("completed", false))
		var enabled := bool(target.get("enabled", true)) and not completed
		var nearby := _nearby(target)
		var navigation := int(target.get("object_id", -1)) == 0
		button.text = ("✓ " if completed else "Walk to · " if navigation else "" if nearby else "Go to · ") + str(target.get("label", "Work site"))
		button.disabled = not enabled
		button.tooltip_text = str(target.get("detail", "Use the marked place in the world."))
		button.pressed.connect(_request_target.bind(str(target.get("id", "")), int(target.get("object_id", -1))))
		_targets.add_child(button)

func _apply_bank(bank: Dictionary) -> void:
	_bank.visible = not bank.is_empty()
	if bank.is_empty():
		return
	var lines: PackedStringArray = []
	var earlier := str(bank.get("inherited_disclosure", ""))
	if not earlier.is_empty():
		lines.append("Earlier account: " + {"public": "public inspection", "protected": "witness protected", "supervised": "witnessed cooperation"}.get(earlier, earlier) + ".")
	for text: String in [str(bank.get("cost", "")), str(bank.get("consequence", ""))]:
		if not text.is_empty():
			lines.append(text)
	if int(bank.get("route_total", 0)) > 0 and str(_state.get("key", "")) == "trail":
		lines.append("Route observations: %d/%d" % [int(bank.get("route_step", 0)), int(bank.route_total)])
	if str(bank.get("remedy", "")) == "maintenance" and not bool(bank.get("remedy_complete", false)):
		lines.append("Crew checks: %d/2. Then reset, reopen and test both valves." % int(bank.get("maintenance_step", 0)))
	if str(_state.get("key", "")) in ["reconstruction", "account", "complete"]:
		lines.append("Reconstruction: %d/%d verified markers." % [int(bank.get("sequence_step", 0)), int(bank.get("sequence_total", 3))])
	var error := str(bank.get("last_error", ""))
	if not error.is_empty():
		lines.append(error)
	if not str(bank.get("misplaced", "")).is_empty():
		lines.append("Lift the misplaced marker at its work site, then correct the route. Verified observations stay saved.")
	if bool(bank.get("tree_cared", false)):
		lines.append("The orchard channel is cleared for the existing tree.")
	if bool(bank.get("bypass_ready", false)):
		lines.append("The new maintenance bypass has been checked.")
	_bank.text = "\n".join(lines)

func _apply_party(party: Dictionary, adoption: Dictionary) -> void:
	var lines: PackedStringArray = []
	var role := str(party.get("role", ""))
	var owner := str(party.get("owner", ""))
	if not owner.is_empty():
		lines.append("Story owner: " + owner)
	if not role.is_empty():
		lines.append("Your role: " + {"owner": "story owner", "eligible": "story participant", "helper": "helper"}.get(role, role))
	for member: Dictionary in party.get("members", []):
		var status := "helping" if str(member.get("role", "")) == "helper" else "participating"
		if not bool(member.get("online", true)):
			status = "offline"
		elif not bool(member.get("present", true)):
			status = "away"
		elif str(member.get("adoption", "")) == "adopted":
			status = "outcome recorded"
		elif str(member.get("adoption", "")) == "help_only":
			status = "help only"
		lines.append("• " + str(member.get("name", "Adventurer")) + " · " + status)
	if bool(party.get("waiting_for_owner", false)):
		lines.append("Waiting for the story owner. Personal decisions remain theirs.")
	if bool(party.get("waiting_for_scene", false)):
		lines.append("Waiting for the other scene viewers. The work site is safe.")
	_party.text = "\n".join(lines)
	_party.visible = not lines.is_empty()
	var state := str(adoption.get("state", ""))
	var pending := state == "pending"
	_adoption_actions.visible = pending
	_help_only.visible = pending and role != "owner"
	_record.disabled = not bool(adoption.get("can_adopt", false))
	_record.tooltip_text = str(adoption.get("reason", ""))
	var summary := str(adoption.get("summary", ""))
	if pending:
		_adoption.text = summary + ("\n" if not summary.is_empty() else "") \
			+ ("Record this result for your own story and its earned milestone." if role == "owner" else \
			"Choose whether this becomes your own story. Helping does not change your saved decision.")
		if not _record.tooltip_text.is_empty():
			_adoption.text += "\n" + _record.tooltip_text
	elif role == "helper":
		_adoption.text = "You are helping this expedition. Your own story remains unchanged."
	elif state == "adopted":
		_adoption.text = "This outcome is recorded for your story."
	elif state == "help_only" or role == "helper":
		_adoption.text = "You are helping this expedition. Your own story remains unchanged."
	else:
		_adoption.text = ""
	_adoption.visible = not _adoption.text.is_empty()

func _apply_companion(companion: Dictionary) -> void:
	var present := not companion.is_empty()
	_companion.visible = present
	_companion_actions.visible = present
	if not present:
		return
	_companion.text = str(companion.get("name", "Companion")) + " · " + str(companion.get("mode", "wait")).capitalize() \
		+ "\n" + str(companion.get("status", ""))
	var allowed := bool(companion.get("can_command", false))
	if not allowed:
		_companion.text += "\nThe story owner gives field orders."
	for button: Button in _companion_buttons.values():
		button.disabled = not allowed

func _request_companion(command: String) -> void:
	var companion: Dictionary = _state.get("companion", {})
	if bool(companion.get("can_command", false)) and command in ["follow", "wait", "regroup", "help"]:
		companion_requested.emit(command)

func _request_decision(action: String) -> void:
	var adoption: Dictionary = _state.get("adoption", {})
	if action not in ["adopt", "help"] or str(adoption.get("state", "")) != "pending":
		return
	if action == "help" and str((_state.get("party", {}) as Dictionary).get("role", "")) == "owner":
		return
	if action == "adopt" and not bool(adoption.get("can_adopt", false)):
		return
	var revision := int(adoption.get("revision", -1))
	var run_id := str(adoption.get("run_id", _state.get("run_id", "")))
	if revision < 0 or run_id.is_empty():
		return
	decision_requested.emit(action, run_id, revision)

func _layout() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	var width := minf(332.0, maxf(240.0, viewport_size.x - 24.0))
	_panel.offset_left = -width - 12.0
	_panel.offset_right = -12.0
	_panel.offset_top = minf(80.0, viewport_size.y * 0.12)
	_panel.offset_bottom = minf(viewport_size.y - 22.0, _panel.offset_top + 440.0)
	_scroll.custom_minimum_size.y = clampf(viewport_size.y - 360.0, 56.0, 180.0)

func _nearby(target: Dictionary) -> bool:
	var raw: Array = target.get("tile", [0, 0])
	var tile := Vector2i(int(raw[0]), int(raw[1]))
	return maxi(absi(_local_tile.x - tile.x), absi(_local_tile.y - tile.y)) <= maxf(1.0, float(target.get("range", 3.0)))

func _request_target(identity: String, object_id: int) -> void:
	if not (_state.get("travel", {}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) != _current_map:
		return
	for target: Dictionary in _state.get("targets", []):
		if str(target.get("id", "")) != identity or int(target.get("object_id", -1)) != object_id:
			continue
		if not bool(target.get("enabled", true)) or bool(target.get("completed", false)):
			return
		var raw: Array = target.get("tile", [0, 0]) if _nearby(target) else target.get("approach", target.get("tile", [0, 0]))
		target_requested.emit(object_id, Vector2i(int(raw[0]), int(raw[1])), _nearby(target))
		return
