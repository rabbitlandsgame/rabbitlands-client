extends Control
## A complete server snapshot drives the roster and the leader's Start button.

var panel: PanelContainer
var selection: Label
var rows: VBoxContainer
var hint: Label
var ready_button: Button
var start_button: Button
var cancel_button: Button
var leave_button: Button
var add_bot: MenuButton
var _state: Dictionary = {}
var _send: Callable

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_send = func(text: String) -> Error: return Network.send_chat(text)
	panel = PanelContainer.new()
	panel.name = "GauntletReadyWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.z_index = 26
	var frame := StyleBoxFlat.new()
	frame.bg_color = Color("29251f")
	frame.border_color = Color("aa8a50")
	frame.set_border_width_all(2)
	frame.set_content_margin_all(16)
	panel.add_theme_stylebox_override("panel", frame)
	add_child(panel)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 12)
	panel.add_child(body)
	var title := Label.new()
	title.text = "Gauntlet · Ready check"
	title.add_theme_font_size_override("font_size", 22)
	title.add_theme_color_override("font_color", Color("edc981"))
	body.add_child(title)
	selection = Label.new()
	selection.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(selection)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.y = 100
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	rows = VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 8)
	scroll.add_child(rows)
	hint = Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(hint)
	var actions := HFlowContainer.new()
	actions.add_theme_constant_override("h_separation", 8)
	actions.add_theme_constant_override("v_separation", 8)
	body.add_child(actions)
	ready_button = _button(actions, "Ready", _toggle_ready)
	start_button = _button(actions, "Start", func() -> void: _request("start"))
	cancel_button = _button(actions, "Cancel", cancel)
	leave_button = _button(actions, "Leave party", func() -> void: _request("leave"))
	add_bot = preload("res://src/ui/bot_class_picker.gd").new()
	add_bot.name = "AddBot"
	add_bot.custom_minimum_size = Vector2(100, 36)
	add_bot.class_chosen.connect(func(class_id: int) -> void: _request("addbot", str(class_id)))
	actions.add_child(add_bot)
	# Wrapped labels settle after the first container pass. Reapply the bounds
	# when their minimum changes so a transient narrow layout cannot leave a
	# newly opened eight-member window taller than the viewport.
	panel.minimum_size_changed.connect(func() -> void: _layout.call_deferred())
	panel.hide()
	get_viewport().size_changed.connect(_layout)
	AppState.state_changed.connect(_on_state_changed)
	apply_snapshot(AppState.gauntlet_ready)

func configure(sender: Callable) -> void:
	_send = sender

func _button(parent: Control, text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(100, 36)
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _layout() -> void:
	var available := get_viewport_rect().size - Vector2(96, 88)
	var target := Vector2(minf(520, available.x - 24), minf(490, available.y - 24))
	panel.size = target
	panel.position = ((available - panel.size) * 0.5).max(Vector2.ZERO)

func _on_state_changed(path: StringName) -> void:
	if path == &"gauntlet_ready" or path == &"connection":
		apply_snapshot(AppState.gauntlet_ready)

func apply_snapshot(state: Dictionary) -> void:
	_state = state.duplicate(true)
	if not bool(state.get("open", false)):
		panel.hide()
		return
	selection.text = "%s\n%s · Level %d" % [state.route, state.difficulty, int(state.level)]
	for child: Node in rows.get_children():
		rows.remove_child(child)
		child.queue_free()
	var self_ready := false
	var count := 0
	for member: Dictionary in state.members:
		var row := HBoxContainer.new()
		var player_name := Label.new()
		player_name.text = str(member.name) + (" (you)" if member.self else "") + (" · Leader" if member.leader else "")
		player_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		player_name.clip_text = true
		player_name.tooltip_text = player_name.text
		row.add_child(player_name)
		var status := Label.new()
		status.text = str(member.status)
		status.add_theme_color_override("font_color", Color("a8d895") if member.ready else Color("e1bb80"))
		row.add_child(status)
		if bool(member.get("bot", false)) and bool(state.is_leader):
			var remove := _button(row, "×", func() -> void: _request("removebot", str(member.id)))
			remove.custom_minimum_size = Vector2(32, 32)
			remove.tooltip_text = "Remove " + str(member.name)
		rows.add_child(row)
		if member.ready: count += 1
		if member.self: self_ready = bool(member.ready)
	ready_button.text = "Not ready" if self_ready else "Ready"
	start_button.visible = bool(state.is_leader)
	start_button.disabled = not bool(state.can_start)
	leave_button.visible = bool(state.in_party)
	add_bot.visible = bool(state.is_leader)
	add_bot.disabled = state.members.size() >= 8
	hint.text = "%d / %d ready. " % [count, state.members.size()]
	if bool(state.can_start):
		hint.text += "Everyone is ready. " + ("Click Start to bring everyone in." if state.is_leader else "Waiting for the party leader to start.")
	else:
		hint.text += "Ready when you want to go. You can join from any map."
	panel.show()
	_layout.call_deferred()
	WindowStack.activate(panel)

func _toggle_ready() -> void:
	for member: Dictionary in _state.get("members", []):
		if member.self:
			_request("unready" if member.ready else "ready")
			return

func _request(action: String, value: String = "") -> void:
	if not bool(_state.get("open", false)): return
	var command := "#gauntlet %s %s" % [action, str(_state.check_id)]
	if not value.is_empty(): command += " " + value
	var error: Error = _send.call(command)
	if error != OK:
		hint.text = "Could not send your choice. Please try again."

func cancel() -> void:
	_request("cancel")
