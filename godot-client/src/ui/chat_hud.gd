extends PanelContainer
## Independently movable conversation/system surfaces with a feathered backdrop.
const FADE_SHADER := preload("res://src/ui/chat_soft_fade.gdshader")
const PreviewScript := preload("res://src/ui/chat_preview.gd")
const MINIMUM := Vector2(320, 165)
const DEFAULT_SIZE := Vector2(490, 240)
const DEFAULT_OPTIONS := {"font_size": 16, "background_opacity": 0.30,
	"line_spacing": 2, "idle_fade": 0, "locked": false, "visible": true, "combined": false}
signal tab_selected(key: String)
signal channel_selected(slot: int)
signal options_requested
signal log_requested
signal urls_requested
signal configuration_changed(key: String, value: Variant)
var preferences_path := WindowPreferences.SETTINGS_PATH
var feed_role := "chat"
var options: Dictionary = DEFAULT_OPTIONS.duplicate()
var buttons: Dictionary = {}
var channel_buttons: Dictionary = {}
var user_closed := false
var destination_key := "local"
var _channels: Array = []
var _peers: Dictionary = {}
var _resizing := false
var _resize_mouse := Vector2.ZERO
var _resize_size := Vector2.ZERO
var _last_message_msec := 0
var _refresh_seconds := 0.0
var dragger: WindowDrag
var bottom_hud: Control
var tabs: HFlowContainer
var options_button: Button
var input: LineEdit
var output: RichTextLabel
var grip: Label
var destination: OptionButton
var composer: HBoxContainer
var _fade: ColorRect
var _header: HBoxContainer
var _frame: Control
var preview_feed: Control
var _feed_suppressed := false

func _ready() -> void:
	if not has_node("Frame"):
		_build_surface()
	_frame = $Frame
	tabs = $Frame/Layout/ChatTabs
	options_button = $Frame/Layout/Header/Options
	input = $Frame/Layout/ChatInput
	output = $Frame/Layout/ChatPanel/ChatOutput
	grip = $Frame/ResizeGrip
	_header = $Frame/Layout/Header
	_frame.custom_minimum_size = Vector2.ZERO
	var empty := StyleBoxEmpty.new()
	empty.set_content_margin_all(6)
	add_theme_stylebox_override("panel", empty)
	($Frame/Layout/ChatPanel as PanelContainer).add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	_fade = ColorRect.new()
	_fade.name = "SoftFade"
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var material := ShaderMaterial.new()
	material.shader = FADE_SHADER
	_fade.material = material
	_frame.add_child(_fade)
	_frame.move_child(_fade, 0)
	# The backdrop and its feathered edges stay inside the resize bounds.
	_fade.offset_left = -6
	_fade.offset_top = -6
	_fade.offset_right = 6
	_fade.offset_bottom = 6
	resized.connect(_sync_backdrop)
	_sync_backdrop()
	preview_feed = PreviewScript.new()
	preview_feed.name = name + "Preview"
	preview_feed.source = self
	# A sibling remains drawable while this window and its controls are hidden.
	get_parent().add_child.call_deferred(preview_feed)
	($Frame/Layout/Header/Title as Label).text = "System" if feed_role == "system" else "Chat"
	($Frame/Layout/Header/Title as Label).add_theme_font_size_override("font_size", 13)
	_header.tooltip_text = "Drag to move. Configure or lock this window in Chat settings."
	if feed_role == "chat":
		for spec: Array in [["all", "All"], ["general", "Local"], ["party", "Party"],
				["guild", "Guild"], ["private", "Private"]]:
			var button := _make_tab(str(spec[0]), str(spec[1]))
			button.pressed.connect(func() -> void: tab_selected.emit(str(button.get_meta("key"))))
		composer = HBoxContainer.new()
		composer.name = "Composer"
		$Frame/Layout.add_child(composer)
		destination = OptionButton.new()
		destination.name = "Destination"
		destination.fit_to_longest_item = false
		destination.tooltip_text = "Who receives your message; reading a log never changes this."
		_style_control(destination)
		composer.add_child(destination)
		input.reparent(composer)
		input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		destination.item_selected.connect(func(index: int) -> void:
			set_destination(str(destination.get_item_metadata(index))))
		_sync_destinations()
	else:
		tabs.hide()
		input.hide()
	var log_button := Button.new()
	log_button.name = "Log"
	log_button.text = "Log"
	log_button.tooltip_text = "Full chat log (~)"
	_style_control(log_button)
	_header.add_child(log_button)
	_header.move_child(log_button, 1)
	log_button.pressed.connect(func() -> void: log_requested.emit())
	var urls_button := Button.new()
	urls_button.name = "URLs"
	urls_button.text = "URLs"
	urls_button.tooltip_text = "Links seen this session; F2 opens the latest"
	_style_control(urls_button)
	_header.add_child(urls_button)
	_header.move_child(urls_button, 2)
	urls_button.pressed.connect(func() -> void: urls_requested.emit())
	_style_control(options_button)
	options_button.tooltip_text = "Configure chat and system windows"
	options_button.pressed.connect(func() -> void: options_requested.emit())
	var close: Button = $Frame/Layout/Header/Close
	_style_control(close)
	close.pressed.connect(dismiss)
	_style_input()
	output.selection_enabled = true
	output.focus_mode = Control.FOCUS_ALL
	output.mouse_default_cursor_shape = Control.CURSOR_IBEAM
	output.context_menu_enabled = true
	output.shortcut_keys_enabled = true
	output.tooltip_text = "Drag to select text. Ctrl+C or right-click → Copy."
	output.add_theme_color_override("default_color", Color("eee3c8"))
	output.add_theme_constant_override("outline_size", 2)
	output.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.9))
	bottom_hud = get_parent().get_node_or_null("Quickbar") as Control
	dragger = WindowDrag.attach(self, _header)
	dragger.bottom_hud = bottom_hud
	if bottom_hud != null:
		bottom_hud.resized.connect(_queue_layout_clamp)
	dragger.moved.connect(func(_to: Vector2) -> void: save_layout())
	grip.mouse_filter = Control.MOUSE_FILTER_STOP
	grip.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	grip.tooltip_text = "Drag to resize"
	grip.gui_input.connect(_on_resize_input)
	var defaults := DEFAULT_OPTIONS.duplicate()
	if feed_role == "system":
		defaults.font_size = 14
		defaults.background_opacity = 0.25
	options = defaults
	options.merge(WindowPreferences.stored_options(_layout_key(), defaults, preferences_path), true)
	var saved := WindowPreferences.stored_rect(_layout_key(), _default_rect(), preferences_path)
	position = saved.position
	apply_options()
	resize_window(saved.size)
	select_tab("all")
	_last_message_msec = Time.get_ticks_msec()
	get_viewport().size_changed.connect(_queue_layout_clamp)
	_queue_layout_clamp()

func _build_surface() -> void:
	var frame := Control.new()
	frame.name = "Frame"
	add_child(frame)
	var layout := VBoxContainer.new()
	layout.name = "Layout"
	frame.add_child(layout)
	layout.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layout.add_theme_constant_override("separation", 4)
	var header := HBoxContainer.new()
	header.name = "Header"
	layout.add_child(header)
	var title := Label.new()
	title.name = "Title"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	for spec: Array in [["Options", "…"], ["Close", "×"]]:
		var button := Button.new()
		button.name = str(spec[0])
		button.text = str(spec[1])
		header.add_child(button)
	var flow := HFlowContainer.new()
	flow.name = "ChatTabs"
	layout.add_child(flow)
	var panel := PanelContainer.new()
	panel.name = "ChatPanel"
	panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layout.add_child(panel)
	var label := RichTextLabel.new()
	label.name = "ChatOutput"
	label.scroll_following = true
	panel.add_child(label)
	var edit := LineEdit.new()
	edit.name = "ChatInput"
	layout.add_child(edit)
	var handle := Label.new()
	handle.name = "ResizeGrip"
	handle.text = "◢"
	frame.add_child(handle)
	handle.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	handle.position -= Vector2(14, 16)

func _style_control(control: Button) -> void:
	control.focus_mode = Control.FOCUS_NONE
	control.add_theme_font_size_override("font_size", 13)
	control.add_theme_color_override("font_color", Color("d9d3bd"))
	control.add_theme_color_override("font_hover_color", Color("fff4d5"))
	control.add_theme_color_override("font_pressed_color", Color("e9cd8a"))
	for state: String in ["normal", "hover", "pressed", "focus"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color.TRANSPARENT
		style.set_content_margin_all(4)
		if state == "pressed":
			style.border_color = Color("d4b779")
			style.border_width_bottom = 1
		control.add_theme_stylebox_override(state, style)

func _style_input() -> void:
	input.placeholder_text = "Type a message…"
	input.selecting_enabled = true
	input.context_menu_enabled = true
	input.shortcut_keys_enabled = true
	for state: String in ["normal", "focus"]:
		var underline := StyleBoxFlat.new()
		underline.bg_color = Color.TRANSPARENT
		underline.border_width_bottom = 1
		underline.border_color = Color(0.85, 0.80, 0.64, 0.7 if state == "focus" else 0.25)
		underline.set_content_margin_all(4)
		input.add_theme_stylebox_override(state, underline)
	input.add_theme_color_override("font_color", Color("eee3c8"))
	input.add_theme_color_override("font_outline_color", Color.BLACK)
	input.add_theme_constant_override("outline_size", 1)
	input.tooltip_text = "Enter sends to the displayed destination; /name sends privately; // replies."

func _make_tab(key: String, title: String) -> Button:
	var button := Button.new()
	button.name = "Tab_" + key.replace(":", "_")
	button.text = title
	button.toggle_mode = true
	button.set_meta("key", key)
	_style_control(button)
	buttons[key] = button
	tabs.add_child(button)
	return button

func sync_channels(channels: Array, selected: String) -> String:
	_channels = channels.duplicate()
	var joined: Dictionary = {}
	for slot: int in channels.size():
		var number := int(channels[slot])
		if number <= 0 or joined.has(number):
			continue
		joined[number] = slot
		var button: Button
		if channel_buttons.has(number):
			button = channel_buttons[number]
		else:
			button = _make_tab("channel:%d" % number, "#%d" % number)
			button.pressed.connect(func() -> void: channel_selected.emit(int(button.get_meta("slot"))))
			channel_buttons[number] = button
		button.set_meta("slot", slot)
		button.tooltip_text = "Joined channel #%d" % number
	for number: Variant in channel_buttons.keys():
		if not joined.has(number):
			var button: Button = channel_buttons[number]
			tabs.remove_child(button)
			button.queue_free()
			channel_buttons.erase(number)
			buttons.erase("channel:%d" % int(number))
	if selected.begins_with("channel:") and not joined.has(int(selected.trim_prefix("channel:"))):
		selected = "all"
	_sync_destinations()
	select_tab(selected)
	return selected

func remember_peer(person: String) -> void:
	if person.is_empty() or _peers.has(person.to_lower()):
		return
	_peers[person.to_lower()] = person
	_sync_destinations()

func reset_destinations() -> void:
	_peers.clear()
	destination_key = "local"
	sync_channels([], "all")

func _sync_destinations() -> void:
	if destination == null:
		return
	destination.clear()
	var choices: Dictionary = {"local": "To: Local · Nearby", "party": "To: Party",
		"guild": "To: Guild", "private": "To: Private · Choose player"}
	for raw: Variant in _channels:
		if int(raw) > 0:
			choices["channel:%d" % int(raw)] = "To: #%d" % int(raw)
	for key: String in _peers:
		choices["pm:" + key] = "To: %s · Private" % _peers[key]
	# Never silently fall back to Local after the selected channel disappears.
	if not choices.has(destination_key):
		choices[destination_key] = "To: unavailable"
	for key: String in choices:
		var index := destination.item_count
		destination.add_item(str(choices[key]))
		destination.set_item_metadata(index, key)
		if key == destination_key:
			destination.select(index)

func set_destination(key: String) -> void:
	destination_key = key
	_sync_destinations()
	input.placeholder_text = "Choose a player or type /name message…" if key == "private" else "Type a message…"

func select_tab(key: String) -> void:
	for raw: Variant in buttons:
		(buttons[raw] as Button).set_pressed_no_signal(str(raw) == key)

func _layout_key() -> String:
	return "system_chat_soft" if feed_role == "system" else "chat_soft"

func _sync_backdrop() -> void:
	var material := _fade.material as ShaderMaterial
	material.set_shader_parameter("panel_width", size.x)
	material.set_shader_parameter("panel_height", size.y)

func _default_rect() -> Rect2:
	var requested := Vector2(440, 160) if feed_role == "system" else DEFAULT_SIZE
	var where := Vector2(18, maxf(12, _bottom_limit() - requested.y - 12)) if feed_role == "system" else Vector2(18, 48)
	return Rect2(where, requested)

func apply_options() -> void:
	($Frame/Layout/Header/Title as Label).text = "System" if feed_role == "system" else ("Chat + System" if bool(options.get("combined", false)) else "Chat")
	options.font_size = clampi(int(options.get("font_size", 16)), 10, 28)
	options.background_opacity = clampf(float(options.get("background_opacity", 0.30)), 0.0, 0.8)
	options.line_spacing = clampi(int(options.get("line_spacing", 2)), 0, 12)
	options.idle_fade = clampi(int(options.get("idle_fade", 0)), 0, 120)
	output.add_theme_font_size_override("normal_font_size", int(options.font_size))
	output.add_theme_constant_override("line_separation", int(options.line_spacing))
	input.add_theme_font_size_override("font_size", int(options.font_size))
	(_fade.material as ShaderMaterial).set_shader_parameter("opacity", float(options.background_opacity))
	dragger.enabled = not bool(options.get("locked", false))
	_header.mouse_default_cursor_shape = Control.CURSOR_ARROW if not dragger.enabled else Control.CURSOR_MOVE
	grip.visible = dragger.enabled
	custom_minimum_size = Vector2(280, 95) if feed_role == "system" else MINIMUM
	user_closed = not bool(options.get("visible", true))
	visible = not user_closed and not _feed_suppressed
	if not user_closed:
		preview_feed.clear_messages()
	preview_feed.refresh_style()

func set_feed_suppressed(suppressed: bool) -> void:
	_feed_suppressed = suppressed
	visible = not user_closed and not suppressed
	if suppressed:
		preview_feed.clear_messages()

func set_option(key: String, value: Variant) -> void:
	if not options.has(key):
		return
	options[key] = value
	apply_options()
	resize_window(size)
	save_layout()
	configuration_changed.emit(key, options[key])

func reset_layout() -> void:
	var fallback := _default_rect()
	position = fallback.position
	resize_window(fallback.size)
	save_layout()

func reveal_message(text: String = "", colour: Color = Color("eee3c8")) -> void:
	_last_message_msec = Time.get_ticks_msec()
	if _feed_suppressed:
		return
	if user_closed:
		preview_feed.add_message(text, colour)
	elif bool(options.get("visible", true)):
		show()

func open_chat() -> void:
	user_closed = false
	options.visible = true
	preview_feed.clear_messages()
	visible = not _feed_suppressed
	output.modulate.a = 1.0
	_last_message_msec = Time.get_ticks_msec()
	dragger.clamp_into_view()
	save_layout()

func dismiss() -> void:
	set_option("visible", false)
	input.release_focus()

func _process(delta: float) -> void:
	_refresh_seconds += delta
	if _refresh_seconds < 0.1:
		return
	_refresh_seconds = 0.0
	var engaged := get_global_rect().has_point(get_global_mouse_position()) or input.has_focus()
	var delay := int(options.idle_fade)
	var faded := delay > 0 and Time.get_ticks_msec() - _last_message_msec > delay * 1000
	output.modulate.a = 0.35 if faded and not engaged else 1.0
	options_button.modulate.a = 1.0 if engaged else 0.55
	grip.modulate.a = 0.9 if engaged else 0.25

func resize_window(requested: Vector2) -> void:
	var bounds := get_viewport_rect().size
	var minimum := custom_minimum_size
	var maximum := Vector2(maxf(minimum.x, bounds.x - 108), maxf(minimum.y, _bottom_limit() - 12))
	size = requested.clamp(minimum, maximum)
	if dragger != null:
		dragger.clamp_into_view()

func _bottom_limit() -> float:
	var bottom := get_viewport_rect().size.y - WindowDrag.RESERVED_BOTTOM_BAR
	return minf(bottom, bottom_hud.global_position.y) if is_instance_valid(bottom_hud) else bottom

func _queue_layout_clamp() -> void:
	_clamp_layout.call_deferred()

func _clamp_layout() -> void:
	resize_window(size)
	_sync_backdrop()

func _on_resize_input(event: InputEvent) -> void:
	if bool(options.get("locked", false)):
		return
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		var click := event as InputEventMouseButton
		_resizing = click.pressed
		if click.pressed:
			_resize_mouse = click.global_position
			_resize_size = size
		else:
			save_layout()
		grip.accept_event()
	elif event is InputEventMouseMotion and _resizing:
		resize_window(_resize_size + (event as InputEventMouseMotion).global_position - _resize_mouse)
		grip.accept_event()

func save_layout() -> void:
	WindowPreferences.store_layout(_layout_key(), Rect2(position, size), false, preferences_path, options)

func _exit_tree() -> void:
	if is_instance_valid(preview_feed):
		preview_feed.queue_free()
