extends Control
## One in-game popover: changes stay visible and apply immediately, without
## crossing hover submenus or opening a separate operating-system window.
signal option_changed(group: String, key: String, value: bool)
signal mounts_requested
signal settings_requested

const Style := preload("res://src/ui/compact_hud_style.gd")
const MountOptions := preload("res://src/mounts/mount_controls.gd")
var panel: PanelContainer
var tabs: TabContainer
var character_boxes: Dictionary = {}
var mount_boxes: Dictionary = {}

func _ready() -> void:
	name = "BannerDisplayMenu"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 350
	panel = PanelContainer.new()
	panel.custom_minimum_size.x = 380
	panel.add_theme_stylebox_override("panel", Style.box(Color("171b1d"), Color("a98a51"), 10))
	add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	panel.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var title := Label.new()
	title.text = "Banner display"
	title.add_theme_font_size_override("font_size", 17)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var dismiss := Button.new()
	dismiss.text = "×"
	dismiss.tooltip_text = "Close [Esc]"
	dismiss.focus_mode = Control.FOCUS_NONE
	dismiss.pressed.connect(close)
	header.add_child(dismiss)
	tabs = TabContainer.new()
	tabs.add_theme_font_size_override("font_size", 14)
	column.add_child(tabs)
	var character := _page("Character")
	_add_toggle(character, "character", "show_names", "Show names")
	var resources := GridContainer.new()
	resources.columns = 3
	resources.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	resources.add_theme_constant_override("h_separation", 20)
	resources.add_theme_constant_override("v_separation", 2)
	character.add_child(resources)
	for heading: String in ["Resource", "Bar", "Values"]:
		var label := Label.new()
		label.text = heading
		label.add_theme_font_size_override("font_size", 12)
		resources.add_child(label)
	for resource: Array in [["Health", "health"], ["Ether", "ether"], ["Food", "food"], ["Action", "action"]]:
		var label := Label.new()
		label.text = resource[0]
		label.add_theme_font_size_override("font_size", 13)
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		resources.add_child(label)
		for part: String in ["bar", "numbers"]:
			var key: String = resource[1] + "_" + part
			var box := _add_toggle(resources, "character", key, "")
			box.tooltip_text = resource[0] + (" bar" if part == "bar" else " values")
	var other := GridContainer.new()
	other.columns = 2
	other.add_theme_constant_override("h_separation", 12)
	character.add_child(other)
	for entry: Array in [["banner_background", "Background"], ["speech_bubbles", "Speech bubbles"],
			["instance_mode", "Instance display"], ["sit_lock", "Sit lock"], ["ranging_lock", "Ranging lock"]]:
		_add_toggle(other, "character", entry[0], entry[1])
	var mounts := _page("Mount")
	for key: String in MountOptions.OPTION_LABELS:
		_add_toggle(mounts, "mount", key, MountOptions.OPTION_LABELS[key])
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 8)
	column.add_child(footer)
	for caption: String in ["Choose mount…", "All banner settings…"]:
		var button := Button.new()
		button.text = caption
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		Style.button(button)
		footer.add_child(button)
		button.pressed.connect(func() -> void:
			close()
			if caption == "Choose mount…": mounts_requested.emit()
			else: settings_requested.emit())
	get_viewport().size_changed.connect(func() -> void:
		if visible: _fit.call_deferred())
	hide()

func _page(caption: String) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = caption
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size.y = 256
	tabs.add_child(scroll)
	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 3)
	scroll.add_child(body)
	return body

func _add_toggle(parent: Node, group: String, key: String, caption: String) -> CheckBox:
	var box := CheckBox.new()
	box.text = caption
	box.name = group + "_" + key
	box.add_theme_font_size_override("font_size", 13)
	box.toggled.connect(func(value: bool) -> void: option_changed.emit(group, key, value))
	parent.add_child(box)
	(character_boxes if group == "character" else mount_boxes)[key] = box
	return box

func sync_options(character: Dictionary, mounts: Dictionary) -> void:
	for key: String in character_boxes:
		(character_boxes[key] as CheckBox).set_pressed_no_signal(bool(character.get(key, false)))
	for key: String in mount_boxes:
		(mount_boxes[key] as CheckBox).set_pressed_no_signal(bool(mounts.get(key, true)))

func open_at(screen_position: Vector2, section := "Character") -> void:
	tabs.current_tab = 1 if section == "Mount" else 0
	panel.position = get_global_transform().affine_inverse() * screen_position + Vector2(8, 8)
	show()
	move_to_front()
	_fit()
	_fit.call_deferred()

func _fit() -> void:
	var available := (size - Vector2(96, 86)).max(Vector2(280, 260))
	panel.custom_minimum_size.x = minf(380, available.x - 8)
	for page: Node in tabs.get_children():
		(page as Control).custom_minimum_size.y = minf(256, maxf(100, available.y - 120))
	panel.reset_size()
	panel.position = Vector2(clampf(panel.position.x, 4, maxf(4, available.x - panel.size.x - 4)),
		clampf(panel.position.y, 4, maxf(4, available.y - panel.size.y - 4)))

func close() -> void:
	hide()
	var focus := get_viewport().gui_get_focus_owner()
	if focus != null and is_ancestor_of(focus): focus.release_focus()

## The first click outside dismisses the popover without moving the player.
func handle_event(event: InputEvent) -> bool:
	if not visible:
		return false
	if event.is_action_pressed("cancel"):
		close()
		return true
	if event is InputEventMouseButton and event.pressed and not panel.get_global_rect().has_point(event.position):
		close()
		return true
	return false

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.pressed: close()
		accept_event()
