extends PanelContainer
signal choose_mount_requested
const Hotkeys := preload("res://src/mounts/mount_hotkeys.gd")
const OPTION_LABELS := {
	"show_banner": "Show mount banner",
	"pin_banner": "Keep mount controls at the top of the screen",
	"mount_button": "Show mount / dismount button",
	"choose_button": "Show mount selection button",
	"gallop_button": "Show gallop button",
	"status": "Show gait and calling status",
	"endurance": "Show gallop endurance",
	"key_hints": "Show mount key hints",
}
var options: Dictionary = default_options()
var toggle := Button.new()
var gallop := Button.new()
var choose := Button.new()
var status := Label.new()
var _banner: Control
var _has_mount_state := false

func _ready() -> void:
	name = "MountControls"
	# main.gd positions the character's overhead banner every frame. Follow it
	# afterwards, in the same screen-space parent, rather than projecting a
	# second world anchor that can drift from the name and resource bars.
	process_priority = 1
	_banner = get_parent().get_node_or_null("ActorResourceOverlay") as Control
	z_index = 1
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	var row := VBoxContainer.new()
	row.add_theme_constant_override("separation", 1)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(row)
	row.add_child(toggle)
	row.add_child(gallop)
	row.add_child(choose)
	row.add_child(status)
	for button: Button in [toggle, gallop, choose]:
		_style_button(button)
		button.focus_mode = Control.FOCUS_NONE
	status.add_theme_font_size_override("font_size", 11)
	status.add_theme_color_override("font_color", Color.WHITE)
	status.add_theme_color_override("font_outline_color", Color.BLACK)
	status.add_theme_constant_override("outline_size", 4)
	status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toggle.focus_mode = Control.FOCUS_NONE
	gallop.focus_mode = Control.FOCUS_NONE
	toggle.tooltip_text = "Call your selected mount while standing or moving, or dismount."
	choose.text = "Mounts"
	choose.tooltip_text = "Choose between your mounts."
	choose.pressed.connect(func() -> void: choose_mount_requested.emit())
	gallop.tooltip_text = "Toggle gallop while running (hold Shift for keyboard running). Eight seconds of endurance."
	toggle.pressed.connect(func() -> void: Network.send_chat("#mount"))
	gallop.pressed.connect(func() -> void: Network.send_chat("#gallop"))
	AppState.state_changed.connect(_changed)
	_refresh()

func _process(_delta: float) -> void:
	_follow_banner()

func _follow_banner() -> void:
	var pinned := bool(options.pin_banner)
	visible = wants_banner() and (pinned or (is_instance_valid(_banner) and _banner.is_visible_in_tree()))
	if not visible:
		return
	var view := get_parent() as Control
	var desired := Vector2(view.size.x * 0.5 + 140, 34) if pinned else _banner.position + Vector2(_banner.size.x + 6.0, 0.0)
	position = Vector2(
		clampf(desired.x, 4.0, maxf(4.0, view.size.x - size.x - 90.0)),
		clampf(desired.y, 34.0, maxf(34.0, view.size.y - size.y - 86.0)))

static func default_options() -> Dictionary:
	var defaults := {}
	for key: String in OPTION_LABELS:
		defaults[key] = true
	return defaults

func set_options(values: Dictionary) -> void:
	for key: String in OPTION_LABELS:
		options[key] = bool(values.get(key, true))
	_refresh()

func wants_banner() -> bool:
	return _has_mount_state and AppState.authenticated and bool(options.show_banner) \
		and (toggle.visible or gallop.visible or choose.visible or status.visible)

static func _style_button(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 11)
	button.add_theme_color_override("font_color", Color.WHITE)
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color.WHITE)
	button.add_theme_color_override("font_disabled_color", Color(0.7, 0.7, 0.7, 0.7))
	button.add_theme_color_override("font_outline_color", Color.BLACK)
	button.add_theme_constant_override("outline_size", 2)
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.0, 0.0, 0.0, 0.22)
	normal.border_color = Color(0.0, 0.0, 0.0, 0.9)
	normal.set_border_width_all(1)
	normal.content_margin_left = 4.0
	normal.content_margin_right = 4.0
	normal.content_margin_top = 1.0
	normal.content_margin_bottom = 1.0
	for state: String in ["normal", "disabled", "focus"]:
		button.add_theme_stylebox_override(state, normal)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.12, 0.12, 0.12, 0.8)
	for state: String in ["hover", "pressed", "hover_pressed"]:
		button.add_theme_stylebox_override(state, hover)

func _changed(_section: StringName) -> void:
	if _section in [&"mount_states", &"map", &"authentication", &"local_actor"]:
		_refresh()

func _refresh() -> void:
	var state: Dictionary = AppState.actor_mounts.get(AppState.local_actor_id, {})
	_has_mount_state = not state.is_empty()
	var mode: String = state.get("mode", "on_foot")
	var selected := str(state.get("selected_mount_id", "moor_pony"))
	var mount_label: String = {"golden_plains_horse":"Mount horse", "crystalback_tortoise":"Mount tortoise"}.get(selected, "Mount pony")
	toggle.text = "Dismount" if mode == "mounted" else ("Cancel" if mode == "summoning" else mount_label)
	toggle.visible = bool(options.mount_button)
	choose.visible = bool(options.choose_button)
	gallop.visible = bool(options.gallop_button)
	if options.key_hints:
		toggle.text += Hotkeys.key_hint("toggle_mount")
	gallop.disabled = mode != "mounted" or state.get("gait") == "walk"
	gallop.text = "Stop gallop" if state.get("gait") == "burst" else "Gallop"
	if options.key_hints:
		gallop.text += Hotkeys.key_hint("toggle_gallop")
	var details: Array[String] = []
	if mode == "summoning":
		if options.status:
			details.append("Calling… %.1fs" % (float(state.get("summon_remaining_ms", 0)) / 1000.0))
	elif mode == "mounted":
		if options.status:
			details.append(str(state.get("gait", "cruise")).capitalize().replace("Cruise", "Trot").replace("Burst", "Gallop"))
		if options.endurance:
			var seconds := float(state.get("endurance_ms", 0)) / 1000.0
			details.append("Gallop ready" if seconds >= 8.0 else ("Gallop %.1fs" % seconds))
	else:
		if options.status:
			details.append(str(state.get("blocked_reason", "")).replace("_", " ").capitalize())
	status.text = " · ".join(details)
	status.visible = not status.text.is_empty()
	reset_size()
	_follow_banner()
