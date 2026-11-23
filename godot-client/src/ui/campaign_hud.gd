extends Control
const Guidance := preload("res://src/world/campaign_guidance.gd")
const FieldReadout := preload("res://src/ui/campaign_field_readout.gd")
const AllyRecovery := preload("res://src/ui/campaign_ally_recovery.gd")
const TrackerSummary := preload("res://src/ui/quest_tracker_summary.gd")
## The quest's field checklist. Its controls request ordinary movement/use;
## only a new authoritative snapshot changes completion or available decisions.
signal target_requested(object_id: int, tile: Vector2i, nearby: bool)
signal actor_target_requested(actor_id: int, tile: Vector2i, nearby: bool)
signal action_requested(action: String)
signal decision_requested(action: String, run_id: String, revision: int)
signal companion_requested(command: String)
signal convoy_requested(command: String)
signal prediction_requested(run_id: String, revision: int, candidate: int)
signal rescue_action_requested(action: String, run_id: String)
signal rescue_reward_requested(choice: String, run_id: String)
signal patient_heal_requested(run_id: String, actor_id: int)
signal ally_heal_requested(run_id: String, actor_id: int)
signal transcript_requested
signal reduced_motion_changed(value: bool)
signal replay_requested
signal completion_dismissed

var _panel: PanelContainer
var _body_scroll: ScrollContainer
var _margin: MarginContainer
var _title: Label
var _hint: Label
var _guidance: Label
var _field_summary: Label
var _recovery_actions: HFlowContainer
var _recovery_signature := ""
var _notice: Label
var _opening_details: Label
var _bank: Label
var _road: Label
var _lamps: Label
var _rescue: Label
var _shelves: Label
var _rescue_actions: HFlowContainer
var _rescue_buttons: Dictionary = {}
var _rescue_rewards: HFlowContainer
var _rescue_reward_buttons: Dictionary = {}
var _patient_heal: Button
var _prediction_actions: HFlowContainer
var _prediction_buttons: Array[Button] = []
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
var _convoy: Label
var _convoy_actions: HFlowContainer
var _convoy_buttons: Dictionary = {}
var _scroll: ScrollContainer
var _targets: VBoxContainer
var _entry: Button
var _lesson_window: Button
var _leave: Button
var _help: Button
var _account: Button
var _reduced: CheckButton
var _replay: Button
var _state: Dictionary = {}
var _local_tile := Vector2i.ZERO
var _target_signature := ""
var _current_map := ""
var _embedded := false
var _available := false
var _replay_available := false
var _replay_retry := false
var _column: VBoxContainer
var _dismissed_completion := ""
var _tracker_recovery := false
var _tracker_details_open := true
var _tracker_recovery_host: Control
var _inline_content: VBoxContainer
var _inline_ledger: GridContainer
var _inline_guidance: Label
var _inline_note: Label
var _map_button: Button
var _inline_signature := ""
var _inline_fit_queued := false
var _instruction_height_limit := 240.0

func set_instruction_height_limit(value: float) -> void:
	_instruction_height_limit = maxf(32,value)
	_layout()

func embed_instruction(label: Label) -> void:
	if label.get_parent() != _column:
		label.reparent(_column)
		_column.move_child(label, 0)
	label.custom_minimum_size.x = 0

static func tracking_identity(snapshot: Dictionary) -> String:
	return str(snapshot.get("kind", "opening")) + ":" + str(snapshot.get("run_id", "lead"))

func embed() -> void:
	_build()
	_embedded = true
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	for side: String in ["left","right","top","bottom"]: _margin.add_theme_constant_override("margin_"+side,0)
	# The enclosing quest card already scrolls. Let action rows take their
	# natural height so a wrapped prerequisite never clips inside a second list.
	_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.size_flags_vertical = Control.SIZE_FILL
	_title.hide()
	_hint.hide()
	_layout()
	_queue_inline_fit()

func presentation_available() -> bool:
	return _available

func host_tracker_recovery(host: Control) -> void:
	_build()
	_tracker_recovery = true
	_tracker_recovery_host = host
	_recovery_actions.reparent(host)
	_fit_tracker_recovery()

func set_tracker_details_open(value: bool) -> void:
	if _tracker_details_open == value: return
	_tracker_details_open = value
	if _tracker_recovery:
		_recovery_actions.reparent(_column if value else _tracker_recovery_host)
		_order_instruction_actions()
	_fit_tracker_recovery()

func _fit_tracker_recovery() -> void:
	if not _tracker_recovery: return
	var count := _recovery_actions.get_child_count()
	for index: int in count:
		var button := _recovery_actions.get_child(index) as Button
		if not button.has_meta("tracker_tooltip"): button.set_meta("tracker_tooltip",button.tooltip_text)
		button.tooltip_text = str(button.get_meta("tracker_tooltip"))
		button.visible = _tracker_details_open or index == 0
		if count > 1 and not _tracker_details_open and index == 0:
			button.tooltip_text += "\n%d allies need healing. Open Instructions to choose another fallen ally." % count

func set_replay_available(value: bool, retry := false) -> void:
	_build()
	_replay_available = value
	_replay_retry = retry
	_replay.disabled = not value
	_replay.text = "Retry scene" if retry else "Replay scene"
	_replay.tooltip_text = "The scene was interrupted. Retry its dialogue and choices; your progress is saved." \
		if retry else "Watch the current scene again. Quest progress and rewards stay saved."

func request_replay() -> void:
	if _replay_available:
		replay_requested.emit()

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
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
	_margin = margin
	margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 12)
	_body_scroll.add_child(margin)
	var column := VBoxContainer.new()
	_column = column
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
	_inline_content = VBoxContainer.new(); _inline_content.name = "InlineInstructionFacts"
	_inline_content.add_theme_constant_override("separation",7); column.add_child(_inline_content)
	_inline_guidance = Label.new(); _inline_guidance.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_inline_guidance.add_theme_font_size_override("font_size",13); _inline_content.add_child(_inline_guidance)
	_inline_ledger = GridContainer.new(); _inline_ledger.name = "InstructionLedger"; _inline_ledger.columns = 2
	_inline_ledger.add_theme_constant_override("h_separation",12); _inline_ledger.add_theme_constant_override("v_separation",5)
	_inline_content.add_child(_inline_ledger)
	_inline_note = Label.new(); _inline_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_inline_note.add_theme_font_size_override("font_size",12); _inline_note.add_theme_color_override("font_color",Color("bac8c2"))
	_inline_content.add_child(_inline_note)
	_map_button = Button.new(); _map_button.name = "ShowQuestMap"; _map_button.text = "Show on map"
	_map_button.tooltip_text = "Open this area's map to see your party and marked work sites."
	_map_button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_map_button.add_theme_font_size_override("font_size",12); _map_button.pressed.connect(_request_map)
	column.add_child(_map_button); _map_button.hide(); _inline_content.hide()
	column.minimum_size_changed.connect(_queue_inline_fit)
	_field_summary = Label.new()
	_field_summary.name = "FieldReadout"
	_field_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_field_summary.add_theme_font_size_override("font_size", 14)
	column.add_child(_field_summary)
	_recovery_actions = HFlowContainer.new()
	_recovery_actions.name = "AllyRecoveryActions"
	_recovery_actions.add_theme_constant_override("h_separation", 5)
	_recovery_actions.add_theme_constant_override("v_separation", 5)
	column.add_child(_recovery_actions)
	_guidance = Label.new()
	_guidance.name = "WorkSiteInstructions"
	_guidance.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_guidance.add_theme_font_size_override("font_size", 14)
	column.add_child(_guidance)
	_notice = Label.new()
	_notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_notice.add_theme_font_size_override("font_size", 14)
	column.add_child(_notice)
	_opening_details = Label.new()
	_opening_details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_opening_details.add_theme_font_size_override("font_size", 14)
	column.add_child(_opening_details)
	_bank = Label.new()
	_bank.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bank.add_theme_font_size_override("font_size", 14)
	column.add_child(_bank)
	_road = Label.new()
	_road.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_road.add_theme_font_size_override("font_size", 14)
	column.add_child(_road)
	_lamps = Label.new()
	_lamps.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_lamps.add_theme_font_size_override("font_size", 14)
	column.add_child(_lamps)
	_rescue = Label.new()
	_rescue.name = "RescueCompanion"
	_rescue.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_rescue.add_theme_font_size_override("font_size", 14)
	column.add_child(_rescue)
	_shelves = Label.new()
	_shelves.name = "SupplyLedger"
	_shelves.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_shelves.add_theme_font_size_override("font_size", 14)
	column.add_child(_shelves)
	_rescue_actions = HFlowContainer.new()
	_rescue_actions.add_theme_constant_override("h_separation", 5)
	_rescue_actions.add_theme_constant_override("v_separation", 5)
	column.add_child(_rescue_actions)
	_patient_heal = Button.new()
	_patient_heal.name = "HealRescuePatient"
	_patient_heal.pressed.connect(_request_patient_heal)
	_rescue_actions.add_child(_patient_heal)
	for action: String in ["accept", "defer", "supplies"]:
		var button := Button.new()
		button.text = {"accept": "Help rescue her daughter", "defer": "Pause and return", "supplies": "Take the offered supplies"}[action]
		button.pressed.connect(_request_rescue_action.bind(action))
		_rescue_actions.add_child(button)
		_rescue_buttons[action] = button
	_rescue_rewards = HFlowContainer.new()
	_rescue_rewards.add_theme_constant_override("h_separation", 5)
	_rescue_rewards.add_theme_constant_override("v_separation", 5)
	column.add_child(_rescue_rewards)
	for choice: String in ["sword", "bow", "wand"]:
		var button := Button.new()
		button.text = "Choose " + choice
		button.tooltip_text = {"sword": "Militia Arming Sword, 10,000 Attack and 10,000 Defense experience",
			"bow": "Amberwood Yew Longbow and 20,000 Ranging experience",
			"wand": "Arcane Focus Wand and 20,000 Magic experience"}[choice] + ". Each choice also grants 10,000 gold. Choose once."
		button.pressed.connect(_request_rescue_reward.bind(choice))
		_rescue_rewards.add_child(button)
		_rescue_reward_buttons[choice] = button
	_prediction_actions = HFlowContainer.new()
	_prediction_actions.add_theme_constant_override("h_separation", 5)
	_prediction_actions.add_theme_constant_override("v_separation", 5)
	column.add_child(_prediction_actions)
	for candidate: int in range(4):
		var button := Button.new()
		button.text = "Interval " + ["I", "II", "III", "IV"][candidate]
		button.pressed.connect(_request_prediction.bind(candidate))
		_prediction_actions.add_child(button)
		_prediction_buttons.append(button)
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
	_convoy = Label.new()
	_convoy.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_convoy.add_theme_font_size_override("font_size", 14)
	column.add_child(_convoy)
	_convoy_actions = HFlowContainer.new()
	_convoy_actions.add_theme_constant_override("h_separation", 5)
	_convoy_actions.add_theme_constant_override("v_separation", 5)
	column.add_child(_convoy_actions)
	for command: String in ["follow", "wait", "regroup", "help"]:
		var button := Button.new()
		button.text = command.capitalize()
		button.pressed.connect(_request_convoy.bind(command))
		_convoy_actions.add_child(button)
		_convoy_buttons[command] = button
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
	_entry.pressed.connect(_request_entry)
	column.add_child(_entry)
	_lesson_window = Button.new()
	_lesson_window.name = "OpenLessonWindow"
	_lesson_window.pressed.connect(func() -> void: action_requested.emit("shelves_lesson_window"))
	column.add_child(_lesson_window)
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
	_replay = Button.new()
	_replay.text = "Replay scene"
	_replay.tooltip_text = "Watch the current scene again. Quest progress and rewards stay saved."
	_replay.disabled = true
	_replay.pressed.connect(request_replay)
	column.add_child(_replay)
	_leave = Button.new()
	_leave.text = "Return"
	_leave.tooltip_text = "Return to the public road. Completed milestones are saved."
	_leave.pressed.connect(_request_leave)
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
	var checkin := str(snapshot.get("key", "")) == "rescue_checkin"
	var complete := str(snapshot.get("kind", "")) == "rescue" and not checkin and bool(snapshot.get("completed", false))
	var matches := EloriaProtocol.map_id_from_reference(str(snapshot.get("map", ""))) == _current_map
	var party: Dictionary = snapshot.get("party", {})
	var can_join := bool(party.get("can_join", false))
	var can_own := bool(party.get("can_start_own", false)) and str(party.get("role", "")) != "owner"
	var travel: Dictionary = snapshot.get("travel", {})
	var travelling := not travel.is_empty()
	if checkin and matches and not (snapshot.get("targets", []) as Array).is_empty(): travelling = false
	_available = not blocked and not (complete and _dismissed_completion == tracking_identity(snapshot)) \
		and (active and matches or travelling or not active and (bool(snapshot.get("available", false)) or can_join or can_own))
	visible = _available
	if not _available:
		return
	_title.text = str(travel.get("title", snapshot.get("title", "The Missing Measure")))
	_hint.text = FieldReadout.instructions(snapshot)
	_notice.text = str(snapshot.get("party_notice", ""))
	_notice.visible = not _notice.text.is_empty()
	_opening_details.text = opening_details(snapshot)
	_opening_details.visible = not _opening_details.text.is_empty()
	_apply_bank(snapshot.get("bank", {}))
	_apply_road(snapshot.get("road", {}))
	_apply_lamps(snapshot.get("lamps", {}))
	_apply_rescue(snapshot.get("rescue", {}))
	_apply_shelves(snapshot.get("shelves", {}))
	var field_readout := FieldReadout.summary(snapshot)
	_field_summary.text = str(field_readout.get("text", ""))
	_field_summary.visible = not _field_summary.text.is_empty()
	_field_summary.add_theme_color_override("font_color", Color("ffb39c") if bool(field_readout.get("urgent", false)) else Color("e5cc90"))
	_apply_ally_recovery()
	_apply_party(party, snapshot.get("adoption", {}))
	_apply_companion(snapshot.get("companion", {}))
	_entry.visible = (not active or travelling) and bool(snapshot.get("available", false)) and not can_own
	_join.visible = not active and can_join
	_own.visible = can_own
	_entry.text = ("Continue " if bool(snapshot.get("started", false)) else "Begin ") + str(snapshot.get("title", "The Missing Measure"))
	_entry.tooltip_text="Continue the current assignment."
	if travelling:
		_entry.text = "Continue at " + str(travel.get("npc", "Odo"))
	if travelling and str(snapshot.get("kind", ""))=="shelves":
		_entry.show()
		var ledger:Dictionary=snapshot.get("shelves",{})
		_entry.text=str(ledger.get("start_label","Start work")) if bool(ledger.get("can_begin",false)) else "Do now · Show on map"
		_entry.tooltip_text="Start here when you are ready." if bool(ledger.get("can_begin",false)) else "Show the destination or the next door on your map. Walk there when you are ready; Untrack keeps the assignment in your quest log."
		if _can_report():
			var helper := str(party.get("role", "")) == "helper"
			_entry.text="Finish helping at Ilka" if helper else "Report to Ilka"
			_entry.tooltip_text="Finish helping this crew and return to your own assignment." if helper else "Tell Ilka what you secured and collect this assignment's reward."
	if checkin:
		_entry.visible = travelling
		_entry.text = "Show Liora on map"
		_entry.tooltip_text = "Visit Elen and Liora at Landfall's inn, near Hob Tennant."
	_leave.visible = active and not travelling
	if checkin: _leave.hide()
	if str(snapshot.get("kind", ""))=="shelves" and _current_map=="landfall_town":
		_leave.visible = bool((snapshot.get("shelves",{}) as Dictionary).get("private_practice",false))
	_leave.text = "Continue" if complete else "Return"
	_leave.tooltip_text = "Continue your journey. Your follow-up is in the quest log." if complete else "Return to the public road. Completed milestones are saved."
	_replay.visible = not complete and not _tracker_recovery
	_reduced.visible = not complete
	_help.visible = active or travelling
	_account.visible = active
	_scroll.visible = active and not travelling
	_reduced.set_pressed_no_signal(reduced_motion)
	_guidance.visible = active and matches and not travelling and Guidance.is_guided(snapshot) and not _field_summary.visible
	_guidance.text = Guidance.legend(snapshot) if _guidance.visible else ""
	if complete:
		_title.text = "Quest complete!"
		_hint.text = "But maybe you should check in on Liora later to see how she is feeling."
		for control: Control in [_notice, _field_summary, _recovery_actions, _opening_details, _rescue, _rescue_actions,
				_rescue_rewards, _scroll, _guidance, _help, _account, _entry, _join, _own,
				_bank, _road, _lamps, _prediction_actions, _party, _adoption, _adoption_actions,
				_companion, _companion_actions, _convoy, _convoy_actions]:
			control.hide()
		_lesson_window.hide()
	_title.visible = not _embedded
	_hint.visible = not _embedded
	_apply_inline_instructions(complete,matches,travelling)
	_order_instruction_actions()
	_layout()
	var rows: Array = []
	var source: Array = [] if complete else Guidance.card_targets(snapshot) if Guidance.is_guided(snapshot) else snapshot.get("targets", [])
	# Ready quest work precedes optional supplies, preserving the server's clue
	# order inside each group. Explicit required storage remains ordinary work.
	for support: bool in [false,true]:
		for navigation: bool in [true,false]:
			for target: Dictionary in source:
				if Guidance.is_support_target(snapshot,target) == support \
						and (int(target.get("object_id", -1)) == 0) == navigation:
					rows.append(target)
	if Guidance.is_guided(snapshot):
		_scroll.visible = _scroll.visible and not rows.is_empty()
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
		var navigation := int(target.get("object_id", -1)) == 0 and not target.has("actor_id")
		button.text = ("Optional · " if Guidance.is_support_target(snapshot,target) else "") \
			+ ("✓ " if completed else "Not ready · " if not enabled else "Walk to · " if navigation else "" if nearby else "Go to · ") + str(target.get("label", "Work site"))
		if not enabled and not completed and not str(target.get("detail", "")).strip_edges().is_empty():
			button.text += "\n" + str(target.detail)
			button.add_theme_color_override("font_disabled_color", Color("bcc2bc"))
		button.disabled = not enabled
		button.tooltip_text = str(target.get("detail", "Use the marked place in the world."))
		button.pressed.connect(_request_target.bind(str(target.get("id", "")), int(target.get("object_id", -1))))
		_targets.add_child(button)
	_queue_inline_fit()

func _order_instruction_actions() -> void:
	# Keep the existing dispatchers close to the instruction they act on. The
	# long supply/crew accounts follow them instead of pushing them off screen.
	var source: Array = Guidance.card_targets(_state) if Guidance.is_guided(_state) else _state.get("targets",[])
	var required := source.any(func(target: Dictionary) -> bool:
		return not Guidance.is_support_target(_state,target) and bool(target.get("enabled",true)) \
			and not bool(target.get("completed",false)))
	var controls: Array[Control] = [_entry,_lesson_window]
	if _recovery_actions.get_parent() == _column: controls.append(_recovery_actions)
	if not required: controls.append(_map_button)
	controls.append(_scroll)
	if required: controls.append(_map_button)
	controls.append(_inline_content)
	var index := _hint.get_index()+1
	for control: Control in controls:
		if control.get_index() != index: _column.move_child(control,index)
		index += 1

func _apply_inline_instructions(complete: bool, matches: bool, travelling: bool) -> void:
	if not _tracker_recovery or complete:
		_inline_content.hide()
		_map_button.hide()
		return
	var content := TrackerSummary.instructions(_state,_current_map)
	var covered := bool(content.get("replaces_supply_ledger",false))
	var rows: Array = content.get("ledger",[])
	var signature := JSON.stringify(rows)
	if signature != _inline_signature:
		_inline_signature = signature
		for child: Node in _inline_ledger.get_children():
			_inline_ledger.remove_child(child); child.queue_free()
		for row: Dictionary in rows:
			for key: String in ["label","value"]:
				var label := Label.new(); label.text = str(row.get(key,""))
				label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				label.add_theme_font_size_override("font_size",12)
				if key == "value": label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
				else: label.add_theme_color_override("font_color",Color("bac8c2"))
				_inline_ledger.add_child(label)
	_inline_ledger.visible = covered and not rows.is_empty()
	_inline_guidance.text = str(content.get("guidance",""))
	_inline_guidance.visible = covered and not _inline_guidance.text.is_empty()
	_inline_note.text = str(content.get("note",""))
	_inline_note.visible = covered and not _inline_note.text.is_empty() and not "heal target" in str(content.get("text","")).to_lower()
	_map_button.visible = bool(_state.get("active",false)) and matches and not travelling
	_inline_content.visible = _inline_ledger.visible or _inline_guidance.visible or _inline_note.visible
	if covered:
		_shelves.hide()
		_field_summary.hide()
	# The slim header already gives the route summary; actual work buttons and
	# specialized preparation/lesson/party requirements remain in the foldout.
	if covered: _guidance.hide()

func _request_map() -> void:
	if _available and _map_button.is_visible_in_tree() and bool(_state.get("active",false)) \
			and EloriaProtocol.map_id_from_reference(str(_state.get("map",""))) == _current_map \
			and (_state.get("travel",{}) as Dictionary).is_empty():
		action_requested.emit("quest_map")

func _queue_inline_fit() -> void:
	if not _embedded or _inline_fit_queued: return
	_inline_fit_queued = true
	_fit_inline.call_deferred()

func _fit_inline() -> void:
	_inline_fit_queued = false
	_layout()

func _request_leave() -> void:
	if not _available or not _leave.is_visible_in_tree(): return
	if str(_state.get("kind", "")) == "rescue" and bool(_state.get("completed", false)):
		# This is a local notice, not another quest decision. Dismiss now;
		# the ordinary leave request still returns us from the private map.
		_dismissed_completion = tracking_identity(_state)
		_available = false
		hide()
		completion_dismissed.emit()
	action_requested.emit("leave")

func _request_entry() -> void:
	if not _available or not _entry.is_visible_in_tree(): return
	var kind := str(_state.get("kind", ""))
	if str(_state.get("key", "")) == "rescue_checkin":
		action_requested.emit("rescue_checkin_destination")
		return
	if kind=="shelves" and not (_state.get("travel",{}) as Dictionary).is_empty() \
			and not bool((_state.get("shelves",{}) as Dictionary).get("can_begin",false)) and not _can_report():
		action_requested.emit("shelves_destination")
		return
	action_requested.emit(kind if kind in ["bank", "road", "lamps", "rescue", "shelves"] else "resume" if bool(_state.get("started", false)) else "start")

func _can_report() -> bool:
	return str(_state.get("kind", "")) == "shelves" and bool(_state.get("available", false)) \
		and str((_state.get("shelves", {}) as Dictionary).get("phase", "")) == "report" and _current_map == "landfall_town"

func _apply_shelves(ledger: Dictionary) -> void:
	_shelves.visible = not ledger.is_empty()
	_lesson_window.visible = str(ledger.get("lesson_window", "")) in ["spells", "mixing"]
	_lesson_window.text = "Open Magic" if str(ledger.get("lesson_window", "")) == "spells" else "Open Mixing"
	if ledger.is_empty(): return
	var local_work := bool(_state.get("active", false)) and str(ledger.get("phase", "")) == "work" \
		and (_state.get("travel", {}) as Dictionary).is_empty() \
		and EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) == _current_map
	var lines: PackedStringArray = ["NEXT STEP" if str(ledger.get("phase","")) in ["travel","report"] else "SUPPLY LEDGER"]
	if not str(ledger.get("current_supply","")).is_empty():
		lines[0] = "Current supply: " + str(ledger.current_supply) + " Essence"
	for row: Dictionary in ledger.get("objectives", []):
		lines.append(("✓ " if int(row.current)>=int(row.target) else "• ") + str(row.label)
			+ " · %d/%d" % [int(row.current),int(row.target)] + ("" if bool(row.get("personal",false)) else " · party"))
	lines.append("Restored stock: " + (", ".join(ledger.get("unlocked", [])) if not (ledger.get("unlocked", []) as Array).is_empty() else "None yet"))
	if str(ledger.get("chapter", "")) == "magic":lines.append("Spider specimens examined: %d/12" % int(ledger.get("samples",0)))
	if str(ledger.get("chapter", "")) == "earth":
		lines.append("Cart integrity: %d%%" % int(ledger.get("cart_integrity",100)) + (". Stay near the cart; clear each ambush before moving on." if local_work else ""))
	var growers: Dictionary=ledger.get("growers",{})
	if not growers.is_empty() and not bool(growers.get("raid",false)):
		var field:=str(growers.get("field","sage"))
		var crop:="Sage" if field=="sage" else "Hearthroot"
		var stored:=int((growers.get("stored",{}) as Dictionary).get(field,0))
		var carried:=int(growers.get("carried",0))
		lines.append("%s gathered: %s · In bags: %s · In crew storage: %s" % [crop,str(stored+carried),str(carried),str(stored)])
		if local_work:lines.append("Four level-%d harvesters · 250 per bag · Raiding waves: %d" % [int(growers.get("harvesting_level",10)),int(growers.get("wave",0))])
		for worker: Dictionary in growers.get("workers",[]) if local_work else []:
			lines.append("%s · %d/%d health · %d carried · %s" % [worker.name,int(worker.health),int(worker.max_health),int(worker.cargo),FieldReadout.worker_activity(worker)])
	var fire: Dictionary=ledger.get("fire",{})
	if not fire.is_empty():
		if str(fire.stage)!="fire_sapper":
			lines.append("Recovered stock secured: %d/%d · Newly mined secured: %d/%d\nCarried: %d · Total secured: %d" % [int(fire.recovered),int(fire.recovered_goal),int(fire.mined),int(fire.mined_goal),int(fire.carried),int(fire.recovered)+int(fire.mined)])
			if str(fire.stage)=="fire_coal":lines.append("Lift repairs: %d/3 · Passage supports: %d/3" % [int(fire.repair),int(fire.passages)])
		else:
			lines.append("Signal silenced: %s · Water channels open: %s · Powder ignited: %s" % ["Yes" if fire.signal else "No","Yes" if fire.water else "No","Yes" if fire.powder else "No"])
			if local_work and FieldReadout.has_warning(fire):lines.append("MOVE OUT OF THE MARKED BLAST AREA")
		for worker: Dictionary in fire.get("workers",[]) if local_work else []:
			lines.append("%s · %d/%d health · %d carried · %s" % [worker.name,int(worker.health),int(worker.max_health),int(worker.cargo),FieldReadout.worker_activity(worker,"Mining")])
	var water:Dictionary=ledger.get("water",{})
	if not water.is_empty():
		if str(water.stage)=="water":lines.append("Channel settings · Fresh %d/2 · Tide %d/2 · Drain %d/2\nKeeper’s marks: Fresh 2, Tide 1, Drain 0" % [int(water.flow[0]),int(water.flow[1]),int(water.flow[2])])
		elif str(water.stage)=="water_cutters":
			if local_work:lines.append("Crew: %s · Gathering beds %d/2" % [str(water.command).capitalize(),int(water.bed)+1])
			for crop:String in ["kelp","cress"]:
				var goal := FieldReadout.objective_target(ledger,crop,int(water.goals[crop]))
				lines.append("%s · Cut %d/%d · At loading point %d · Secured %d/%d" % ["Kelp" if crop=="kelp" else "Watercress",int(water.cut[crop]),goal,int(water.bins[crop]),int(water.stored[crop]),goal])
		elif str(water.stage)=="water_barge":
			lines.append("Barge hull: %d/100 · Landings: %d/3" % [int(water.hull),int(water.landing)])
			if local_work:lines.append(("Departure ordered" if water.sailing else "Waiting for your departure order") + "\nStay close and drive attackers away. Heal the crew; repair the boat with Wood Planks.")
		else:lines.append("North guards isolated: %s · South guards isolated: %s" % ["Yes" if water.north else "No","Yes" if water.south else "No"])
		if local_work and FieldReadout.has_warning(water):lines.append("MOVE OUT OF THE MARKED SURGE")
		for worker:Dictionary in water.workers if local_work else []:lines.append("%s · %d/%d health · %d carried · %s" % [worker.name,int(worker.health),int(worker.max_health),int(worker.cargo),FieldReadout.worker_activity(worker,"Cutting")])
	_shelves.text = "\n".join(lines)

func _rescue_local() -> bool:
	return str(_state.get("kind", "")) == "rescue" and bool(_state.get("active", false)) \
		and (_state.get("travel", {}) as Dictionary).is_empty() \
		and EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) == _current_map

func _apply_rescue(rescue: Dictionary) -> void:
	if rescue.has("checkin"): rescue = {}
	var present := not rescue.is_empty() and str(_state.get("kind", "")) == "rescue"
	_rescue.visible = present and _rescue_local()
	_rescue_actions.visible = present and _rescue_local()
	_rescue_rewards.visible = false
	_patient_heal.hide()
	for button: Button in _rescue_buttons.values():
		button.hide()
	if not present:
		return
	var mother: Dictionary = rescue.get("mother", {})
	var lines: PackedStringArray = []
	var name := "Injured woman" if not bool(mother.get("configured", false)) else "Elen Reed"
	lines.append("%s · level 10 companion\nHealth %d/%d · Mana %d/%d" % [name,
		int(mother.get("health", 0)), int(mother.get("max_health", 1)), int(mother.get("mana", 0)), int(mother.get("max_mana", 1))])
	lines.append("Her mana is finite. Revival casts used: %d." % int(mother.get("revives_spent", 0)))
	if bool(mother.get("downed", false)):
		lines.append("She is hurt. Use Heal Target on her before continuing.")
	elif bool(mother.get("following", false)):
		lines.append("Elen is following the rescue party.")
	var patient: Dictionary = rescue.get("patient", {})
	_patient_heal.visible = _rescue_local() and str(rescue.get("stage", "")) == "injured" \
		and int(patient.get("actor_id", 0)) > 0 and not AllyRecovery.contains(_state, _current_map, int(patient.get("actor_id", 0)))
	_patient_heal.disabled = not bool(patient.get("can_cast", false))
	_patient_heal.text = "Heal Target · first lesson" if int(patient.get("lesson_remaining", 0)) > 0 else "Heal Target"
	_patient_heal.tooltip_text = "Cast Heal Target on this patient. The first lesson supplies its cost." \
		if int(patient.get("lesson_remaining", 0)) > 0 else "Heal Target requires Magic 0: 5 mana, one Life Essence and one Water Essence."
	for action: String in ["accept", "defer", "supplies"]:
		var allowed := bool(rescue.get("can_" + action, false)) if action != "supplies" \
			else bool((rescue.get("supplies", {}) as Dictionary).get("can_claim", false))
		(_rescue_buttons[action] as Button).visible = _rescue_local() and allowed
	var reward: Dictionary = rescue.get("reward", {})
	_rescue_rewards.visible = _rescue_local() and bool(reward.get("can_choose", false))
	if _rescue_rewards.visible:
		lines.append("Your reward: choose one weapon and its skill experience, plus 10,000 gold.")
	elif bool(reward.get("claimed", false)):
		lines.append("Your " + str(reward.get("choice", "weapon")) + " reward is recorded.")
	if bool((rescue.get("daughter", {}) as Dictionary).get("rescued", false)):
		lines.append("The family has reached the mine exit." if bool((rescue.get("daughter", {}) as Dictionary).get("returned", false)) \
			else "Liora is free. Stay with the family until they reach safety.")
	_rescue.text = "\n".join(lines)

func _apply_ally_recovery() -> void:
	var patients := AllyRecovery.patients(_state, _current_map)
	_recovery_actions.visible = not patients.is_empty()
	var run_id := str(_state.get("run_id", ""))
	var signature := run_id + ":" + _current_map + ":" + JSON.stringify(patients)
	if signature == _recovery_signature: return
	_recovery_signature = signature
	for child: Node in _recovery_actions.get_children():
		_recovery_actions.remove_child(child)
		child.queue_free()
	for patient: Dictionary in patients:
		var button := Button.new()
		button.text = "Heal Target · " + str(patient.name)
		button.tooltip_text = "Cast Heal Target at Power 1 on this fallen ally. Requires Magic 0, 5 ether, 1 Life Essence and 1 Water Essence. Normal approach and casting time apply; moving cancels the cast."
		if bool(patient.get("assisted", false)):
			button.tooltip_text = "Cast Heal Target at Power 1 on Elen. Your unused first recovery lesson can supply this cast's cost. Normal approach and casting time apply; moving cancels the cast."
		button.pressed.connect(_request_ally_heal.bind(run_id, int(patient.actor_id)))
		_recovery_actions.add_child(button)
	_fit_tracker_recovery()

func _request_ally_heal(run_id: String, actor_id: int) -> void:
	if not _available or not _recovery_actions.is_visible_in_tree() or run_id != str(_state.get("run_id", "")) \
			or not AllyRecovery.contains(_state, _current_map, actor_id):
		return
	ally_heal_requested.emit(run_id, actor_id)

func _request_rescue_action(action: String) -> void:
	if not _rescue_local() or action not in ["accept", "defer", "supplies"]:
		return
	var rescue: Dictionary = _state.get("rescue", {})
	var allowed := bool(rescue.get("can_" + action, false)) if action != "supplies" \
		else bool((rescue.get("supplies", {}) as Dictionary).get("can_claim", false))
	if allowed:
		rescue_action_requested.emit(action, str(_state.get("run_id", "")))

func _request_rescue_reward(choice: String) -> void:
	if _rescue_local() and choice in ["sword", "bow", "wand"] \
			and bool(((_state.get("rescue", {}) as Dictionary).get("reward", {}) as Dictionary).get("can_choose", false)):
		rescue_reward_requested.emit(choice, str(_state.get("run_id", "")))

func _request_patient_heal() -> void:
	var patient: Dictionary = (_state.get("rescue", {}) as Dictionary).get("patient", {})
	if _rescue_local() and bool(patient.get("can_cast", false)):
		patient_heal_requested.emit(str(_state.get("run_id", "")), int(patient.get("actor_id", 0)))

static func opening_details(snapshot: Dictionary) -> String:
	if int(snapshot.get("content_revision", 1)) != 2:
		return ""
	var cart: Dictionary = snapshot.get("cart", {})
	var inquiry: Dictionary = snapshot.get("inquiry", {})
	var lines: PackedStringArray = []
	if not cart.is_empty():
		lines.append({"trapped": "The worker is pinned. Keep the cart held while preparing a release.",
			"prepared": "The release is prepared. Use the marked work site.",
			"released": "The cart is clear. Treat the worker before escorting them.",
			"treated": "The worker is treated. Walk with them to the shore muster.",
			"escorting": "Stay with the worker on the marked route to shore.",
			"safe": "The worker is safely ashore."}.get(str(cart.get("state", "")), "Follow the crew's instructions."))
		var route := str(cart.get("route", ""))
		if not route.is_empty() and not bool(cart.get("worker_safe", false)):
			lines.append("Rescue plan · " + {"unload": "lighten the cart", "lever": "brace and lift", "haul": "secure and haul"}.get(route, ""))
			if route == "unload": lines.append("Loads safely set down: %d of 2." % int(cart.get("unloaded", 0)))
			elif route == "lever": lines.append("Fulcrum ready." if bool(cart.get("fulcrum_ready", false)) else "Place the fulcrum before lifting.")
			elif route == "haul":
				var holder := str(cart.get("holder", ""))
				var held := "The cart is held." if holder.is_empty() else "Brake held by " \
					+ ("the dock foreman" if holder == "foreman" else holder) + "."
				lines.append("Rope anchors secured: %d of 2. " % int(cart.get("rope_ends", 0)) \
					+ (held if bool(cart.get("holder_active", false)) else "A crew member must hold the cart."))
	if not inquiry.is_empty() and (cart.is_empty() or bool(cart.get("worker_safe", false))):
		var lead := str(inquiry.get("lead", ""))
		if not lead.is_empty():
			lines.append("Inquiry · " + {"physical": "follow the physical work", "chronology": "reconstruct the sequence", "records": "compare the completion records"}.get(lead, ""))
		if str(inquiry.get("finding", "")) == "one_kit_two_completions":
			lines.append("Verified: one fitting kit was recorded as completing two jobs.")
		elif not (inquiry.get("claims", []) as Array).is_empty():
			lines.append("Claims to check: " + "; ".join(PackedStringArray(inquiry.claims)))
	return "\n".join(lines)

func _apply_road(road: Dictionary) -> void:
	_road.visible = not road.is_empty()
	var convoy: Dictionary = road.get("convoy", {})
	_convoy.visible = not convoy.is_empty()
	_convoy_actions.visible = not convoy.is_empty()
	if road.is_empty():
		return
	var lines: PackedStringArray = []
	var context := str(road.get("legacy_context", ""))
	if not context.is_empty():
		lines.append(context)
	if road.has("actual_workers") and road.has("permit_workers"):
		lines.append("Crew: %d counted; %d names on the permit." % [int(road.actual_workers), int(road.permit_workers)])
	var preparation := str(road.get("preparation", ""))
	if not preparation.is_empty():
		lines.append("Load plan · " + {"brace": "braced with one Wood Plank", "protect": "protected loading", "shared_load": "smaller shared loads"}.get(preparation, ""))
	for text: String in [str(road.get("cost", "")), str(road.get("consequence", ""))]:
		if not text.is_empty():
			lines.append(text)
	var stock: Dictionary = road.get("stock", {})
	if not stock.is_empty():
		lines.append("Field food: %d portions available; %d kept for late arrivals." % [int(stock.get("remaining", 0)), int(stock.get("reserved_last_bowl", 0))])
	var hazard: Dictionary = road.get("hazard", {})
	if not hazard.is_empty() and not str(hazard.get("kind", "")).is_empty():
		var situation: String = {"herd": "Herd crossing", "rear_cart": "Rear cart", "soft_ground": "Soft ground"}.get(str(hazard.kind), "Field interruption")
		var status: String = {"warning": "stop and inspect", "inspected": "choose the field work", "assigned": "complete the assigned work", "resolved": "stable"}.get(str(hazard.get("state", "")), "read the work site")
		lines.append(situation + " · " + status + ".")
		if str(hazard.get("kind", "")) == "herd":
			lines.append("The herd has cleared the cart lane." if bool(road.get("herd_cleared", false)) else "Keep the carts stopped until the animals physically clear the lane.")
	for cart: Dictionary in road.get("carts", []):
		lines.append({"lead": "Lead cart", "rear": "Rear cart", "consignment": "Current consignment"}.get(str(cart.id), "Work cart") \
			+ " · %d load units · " % int(cart.get("cargo_units", 0)) + str(cart.get("state", "waiting")).capitalize())
	var consignment: Dictionary = road.get("consignment", {})
	if bool(consignment.get("agreement", false)):
		lines.append("The carrier's agreement is witnessed for this current shipment.")
	var custody := str(consignment.get("custody", ""))
	if not custody.is_empty():
		lines.append({"witnessed_transfer": "This shipment transfers under witnessed terms.",
			"safe_hold": "This shipment stays in safe custody under the agreed terms.",
			"carrier_return": "The carrier takes this shipment back with the corrected account."}.get(custody, ""))
	var optional: Dictionary = road.get("optional", {})
	if not optional.is_empty():
		lines.append("Optional · late worker: " + {"unfound": "not yet found", "found": "stayed with an injured animal",
			"treated": "animal treated; walk back safely", "safe": "returned safely", "completed": "your account recorded"}.get(str(optional.get("supper", "unfound")), ""))
		lines.append("Optional · Last Bowl: " + {"unstarted": "keep food for late arrivals", "portioned": "portions kept; record the work",
			"completed": "your account recorded"}.get(str(optional.get("last_bowl", "unstarted")), ""))
	_road.text = "\n".join(lines)
	if not convoy.is_empty():
		_convoy.text = "Field convoy · " + str(convoy.get("mode", "wait")).capitalize() + "\n" + str(convoy.get("status", ""))
		var allowed := bool(convoy.get("can_command", false))
		if not allowed:
			_convoy.text += "\nThe story owner directs the carts. Odo's field orders are separate."
		for button: Button in _convoy_buttons.values():
			button.disabled = not allowed

func _apply_lamps(lamps: Dictionary) -> void:
	_lamps.visible = not lamps.is_empty()
	var local_work := bool(_state.get("active", false)) and (_state.get("travel", {}) as Dictionary).is_empty() \
		and EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) == _current_map
	var prediction: Dictionary = lamps.get("prediction", {})
	var at_lesson := str(_state.get("key", "")) == "calibration" or bool(prediction.get("can_choose", false))
	_prediction_actions.visible = bool(lamps.get("challenge", false)) and local_work and at_lesson
	if lamps.is_empty():
		return
	var settings: Dictionary = lamps.get("settings", {})
	var lines: PackedStringArray = []
	var worker := str(lamps.get("worker_status", ""))
	if not worker.is_empty():
		lines.append("Teren · " + worker.replace("_", " "))
	var problem := str(lamps.get("last_error", ""))
	if not problem.is_empty():
		lines.append(problem)
	var holder := str(lamps.get("holder", ""))
	if holder == "edda":
		holder = "Edda Tine"
	if not holder.is_empty():
		lines.append("Mechanism held by " + holder if bool(lamps.get("holder_active", false)) else holder + " is moving to the holding post.")
	lines.append("Settings · marker %d / lamp height %d / drain %d" % [int(settings.get("marker", 0)), int(settings.get("shutter", 0)), int(settings.get("bleed", 0))])
	lines.append("Interval %s · water %d\nTide %d + load %d − drain %d (minimum 0)" % [["I", "II", "III", "IV"][clampi(int(lamps.get("cycle", 0)), 0, 3)], int(lamps.get("water", 0)), int(lamps.get("tide", 0)), int(lamps.get("load", 0)), int(settings.get("bleed", 0))])
	lines.append("Marker %d / beam %d / clearance %d\nLamp: %s %s · pointer: %s" % [int(lamps.get("marker_number", 1)), int(lamps.get("beam_height", 1)), int(lamps.get("clearance", 0)), str(lamps.get("lamp_shape", "")), str(lamps.get("lamp_word", "")), str(lamps.get("indicator", ""))])
	var observations: Array = lamps.get("observations", [])
	if not observations.is_empty() and at_lesson:
		lines.append("Recorded tests:")
		for observation: Dictionary in observations.slice(maxi(0, observations.size() - 4)):
			lines.append("%s · water %d / clearance %d · %s %s" % [["I", "II", "III", "IV"][clampi(int(observation.get("cycle", 0)), 0, 3)], int(observation.get("water", 0)), int(observation.get("clearance", 0)), str(observation.get("lamp_shape", "")), str(observation.get("lamp_word", ""))])
	var allowed := bool(prediction.get("can_choose", false)) and bool(lamps.get("challenge", false)) \
		and bool(_state.get("active", false)) and (_state.get("travel", {}) as Dictionary).is_empty() \
		and EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) == _current_map
	for button: Button in _prediction_buttons:
		button.disabled = not allowed # Every candidate has the same eligibility.
	if bool(lamps.get("challenge", false)) and at_lesson:
		lines.append("The visible load changed. Choose an interval, then advance the cycle and take a fresh reading there.")
		if not allowed:
			lines.append("Approach the test station to choose an interval.")
	var candidate: Variant = prediction.get("candidate")
	if candidate != null and at_lesson:
		lines.append("Your prediction: interval " + ["I", "II", "III", "IV"][clampi(int(candidate), 0, 3)])
	var feedback := str(prediction.get("feedback", ""))
	if not feedback.is_empty() and at_lesson:
		lines.append(feedback)
	if bool(lamps.get("evidence_secure", false)):
		lines.append("The equipment and independent readings are secure.")
	var inheritance: Dictionary = lamps.get("inheritance", {})
	if bool(inheritance.get("worker_ally", false)):
		lines.append("Nessa's safe return is recorded in the crew account.")
	if bool(inheritance.get("refuge_provisions", false)):
		lines.append("The late arrivals' provisions remain recorded at Oyun's field kitchen.")
	for reading: Dictionary in lamps.get("evidence_readings", []):
		lines.append("%s · measured %d / claimed %d" % [str(reading.get("post", "Equipment")).replace("_", " ").capitalize(), int(reading.get("value", 0)), int(reading.get("claimed", 0))])
	for text: String in [str(lamps.get("context", "")), str(lamps.get("consequence", "")), str(lamps.get("legacy_advice", ""))]:
		if not text.is_empty():
			lines.append(text)
	var board_tile: Array = (_state.get("anchors", {}) as Dictionary).get("board", [])
	var near_board := board_tile.size() == 2 and _local_tile.distance_to(Vector2i(board_tile[0], board_tile[1])) <= 4
	if at_lesson or near_board or bool(lamps.get("board_done", false)):
		var instructions := str(lamps.get("board_text", ""))
		if not instructions.is_empty():
			lines.append(instructions)
	_lamps.text = "\n".join(lines)

func _request_prediction(candidate: int) -> void:
	var prediction: Dictionary = (_state.get("lamps", {}) as Dictionary).get("prediction", {})
	if not bool(prediction.get("can_choose", false)) or candidate < 0 or candidate > 3 \
			or not bool(_state.get("active", false)) or not (_state.get("travel", {}) as Dictionary).is_empty() \
			or EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) != _current_map:
		return
	prediction_requested.emit(str(_state.get("run_id", "")), int(prediction.get("revision", -1)), candidate)

func _request_convoy(command: String) -> void:
	var convoy: Dictionary = (_state.get("road", {}) as Dictionary).get("convoy", {})
	if bool(convoy.get("can_command", false)) and command in ["follow", "wait", "regroup", "help"]:
		convoy_requested.emit(command)

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
		elif str(member.get("role", "")) == "helper":
			status = "helping"
		elif str(member.get("adoption", "")) == "adopted" and str(_state.get("kind", "")) != "shelves":
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
	if _embedded:
		var complete := str(_state.get("kind","")) == "rescue" and str(_state.get("key","")) != "rescue_checkin" and bool(_state.get("completed",false))
		var limit := minf(_instruction_height_limit,clampf(viewport_size.y-230.0,32.0,240.0))
		custom_minimum_size = Vector2(0,100.0 if complete else minf(maxf(32,_column.get_combined_minimum_size().y),limit))
		_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_scroll.custom_minimum_size.y = 0.0
		return
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
	if not _available or not _scroll.is_visible_in_tree() or (not (_state.get("travel", {}) as Dictionary).is_empty() \
			and str(_state.get("key", "")) != "rescue_checkin") \
			or EloriaProtocol.map_id_from_reference(str(_state.get("map", ""))) != _current_map:
		return
	for target: Dictionary in _state.get("targets", []):
		if str(target.get("id", "")) != identity or int(target.get("object_id", -1)) != object_id:
			continue
		if not bool(target.get("enabled", true)) or bool(target.get("completed", false)):
			return
		var raw: Array = target.get("tile", [0, 0]) if _nearby(target) else target.get("approach", target.get("tile", [0, 0]))
		if target.has("actor_id"):
			actor_target_requested.emit(int(target.actor_id), Vector2i(int(raw[0]), int(raw[1])), _nearby(target))
		else:
			target_requested.emit(object_id, Vector2i(int(raw[0]), int(raw[1])), _nearby(target))
		return
