extends PanelContainer
## A single movable and resizable chat surface. Message updates never undo
## an explicit dismissal, and joined tabs are identified by channel number.
const STYLE = preload("res://src/ui/compact_hud_style.gd")
const MINIMUM := Vector2(320, 210)
const DEFAULT_SIZE := Vector2(430, 250)
signal tab_selected(key: String)
signal channel_selected(slot: int)
signal options_requested

var preferences_path := WindowPreferences.SETTINGS_PATH
var buttons: Dictionary = {}
var channel_buttons: Dictionary = {}
var user_closed := false
var _resizing := false
var _resize_mouse := Vector2.ZERO
var _resize_size := Vector2.ZERO
var dragger: WindowDrag
var bottom_hud: Control
@onready var tabs: HFlowContainer = $Frame/Layout/ChatTabs
@onready var options_button: Button = $Frame/Layout/Header/Options
@onready var input: LineEdit = $Frame/Layout/ChatInput
@onready var output: RichTextLabel = $Frame/Layout/ChatPanel/ChatOutput
@onready var grip: Label = $Frame/ResizeGrip

func _ready() -> void:
	custom_minimum_size = MINIMUM
	add_theme_stylebox_override("panel", STYLE.box())
	output.add_theme_font_size_override("normal_font_size", 13)
	output.add_theme_color_override("default_color", STYLE.TEXT)
	input.add_theme_font_size_override("font_size", 13)
	input.add_theme_stylebox_override("normal", STYLE.box(Color(0.035, 0.03, 0.025, 0.88), Color("6c583a"), 5))
	input.add_theme_stylebox_override("focus", STYLE.box(Color("211b14"), STYLE.BRASS, 5))
	input.add_theme_color_override("font_color", STYLE.TEXT)
	for spec: Array in [["all", "All"], ["general", "General"], ["party", "Party"],
			["system", "System"], ["guild", "Guild"], ["private", "Private"], ["history", "History"]]:
		var button := _make_tab(str(spec[0]), str(spec[1]))
		button.pressed.connect(func() -> void: tab_selected.emit(str(button.get_meta("key"))))
	STYLE.button(options_button)
	options_button.tooltip_text = "Chat and HUD settings"
	options_button.pressed.connect(func() -> void: options_requested.emit())
	var close: Button = $Frame/Layout/Header/Close
	STYLE.button(close)
	close.pressed.connect(dismiss)
	dragger = WindowDrag.attach(self, $Frame/Layout/Header)
	bottom_hud = get_parent().get_node_or_null("Quickbar") as Control
	dragger.bottom_hud = bottom_hud
	if bottom_hud != null:
		bottom_hud.resized.connect(_queue_layout_clamp)
	dragger.moved.connect(func(_to: Vector2) -> void: save_layout())
	grip.mouse_filter = Control.MOUSE_FILTER_STOP
	grip.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	grip.tooltip_text = "Drag to resize chat"
	grip.gui_input.connect(_on_resize_input)
	var fallback := Rect2(Vector2(12, maxf(12, _bottom_limit() - DEFAULT_SIZE.y - 12)), DEFAULT_SIZE)
	var saved := WindowPreferences.stored_rect("chat_hud", fallback, preferences_path)
	position = saved.position
	resize_window(saved.size)
	select_tab("all")
	get_viewport().size_changed.connect(_queue_layout_clamp)
	_queue_layout_clamp()

func _make_tab(key: String, title: String) -> Button:
	var button := Button.new()
	button.name = "Tab_" + key.replace(":", "_")
	button.text = title
	button.toggle_mode = true
	button.set_meta("key", key)
	STYLE.button(button)
	buttons[key] = button
	tabs.add_child(button)
	return button

func sync_channels(channels: Array, selected: String) -> String:
	var joined: Dictionary = {}
	for slot: int in range(channels.size()):
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
		tabs.move_child(button, 3 + joined.size() - 1)
	for number: Variant in channel_buttons.keys():
		if not joined.has(number):
			var button: Button = channel_buttons[number]
			tabs.remove_child(button)
			button.queue_free()
			channel_buttons.erase(number)
			buttons.erase("channel:%d" % int(number))
	if selected.begins_with("channel:") and not joined.has(int(selected.trim_prefix("channel:"))):
		selected = "all"
	select_tab(selected)
	return selected

func select_tab(key: String) -> void:
	for raw: Variant in buttons:
		(buttons[raw] as Button).set_pressed_no_signal(str(raw) == key)
	input.placeholder_text = ("Message your party…" if key == "party" else
		"Message your guild…" if key == "guild" else
		"Message %s…" % key.replace("channel:", "#") if key.begins_with("channel:") else
		"Chat, /name private message, or // reply")

func reveal_message() -> void:
	if not user_closed:
		show()

func open_chat() -> void:
	user_closed = false
	show()
	modulate.a = 1.0
	dragger.clamp_into_view()

func dismiss() -> void:
	user_closed = true
	input.release_focus()
	hide()

func resize_window(requested: Vector2) -> void:
	var bounds := get_viewport_rect().size
	var maximum := Vector2(maxf(MINIMUM.x, bounds.x - 108), maxf(MINIMUM.y, _bottom_limit() - 12))
	size = requested.clamp(MINIMUM, maximum)
	if dragger != null:
		dragger.clamp_into_view()

func _bottom_limit() -> float:
	var bottom := get_viewport_rect().size.y - WindowDrag.RESERVED_BOTTOM_BAR
	return minf(bottom, bottom_hud.global_position.y) if is_instance_valid(bottom_hud) else bottom

func _queue_layout_clamp() -> void:
	_clamp_layout.call_deferred()

func _clamp_layout() -> void:
	resize_window(size)

func _on_resize_input(event: InputEvent) -> void:
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
	WindowPreferences.store_layout("chat_hud", Rect2(position, size), false, preferences_path)
