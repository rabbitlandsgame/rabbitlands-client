extends Control
## The tabbed settings window, and the key-rebinding UI.
##
## One window owns the HUD, minimap, banner, graphics, camera, audio, inventory,
## spell and gameplay preferences and every client key binding. Main mounts
## the existing scene controls here and applies/persists their values.
##
## Every setting here is about this machine and this screen. None of it is sent
## to the server, and none of it changes what the server decides - the gameplay
## tab's entries are commands the server owns, sent as the player's own words
## rather than applied locally.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

const AudioMix := preload("res://src/audio/audio_mix.gd")
const PANEL_SIZE := Vector2(960.0, 520.0)
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0
const FPS_LIMITS: Array[int] = [0, 30, 60, 75, 90, 120, 144, 165, 240, 360]
## How far away other actors' names still show, in metres. The top of the range
## is main.gd's ACTOR_DRAW_DISTANCE_METRES: past it there is no body to hang a
## name over.
const NAME_DISTANCE_MIN := 10.0
const NAME_DISTANCE_MAX := 80.0
const NAME_DISTANCE_DEFAULT := 30.0

## Preloaded rather than reached by its global class name, for the same reason
## this script declares none: the global class cache is a build artifact, and
## this window is built before anything has forced it to be up to date.
const MapCache := preload("res://src/world/map_scene_cache.gd")
## The look pass's switch and quality names; preloaded for the same reason.
const LookProfileScript := preload("res://src/world/look/look_profile.gd")

## The actions a player may rebind, grouped the way they are used. Actions the
## client does not own - text editing inside a LineEdit, for instance - are not
## offered, because rebinding them would break the box they are typed in.
const BINDABLE := {
	"Movement": ["move_north", "move_south", "move_west", "move_east",
		"turn_left", "turn_right", "recenter_viewport"],
	"Windows": ["toggle_inventory", "toggle_map", "toggle_minimap",
		"toggle_console", "toggle_encyclopedia", "chat_focus",
		"toggle_spells", "toggle_summoning", "toggle_manufacture",
		"toggle_emotes", "toggle_quest_journal", "toggle_buddy", "toggle_stats",
		"toggle_ranging", "toggle_help", "toggle_notepad", "toggle_options",
		"toggle_mail", "toggle_party", "toggle_guild", "toggle_achievements"],
	"Actions": ["attack_selected", "combat_target", "summon_behavior",
		"toggle_sit", "toggle_show_through_obstacles", "screenshot", "cancel",
		"connect", "disconnect", "open_last_url"],
	"Items": ["quick_item_1", "quick_item_2", "quick_item_3", "quick_item_4",
		"quick_item_5", "quick_item_6", "quick_item_7", "quick_item_8"],
	"Spells": ["quick_spell_1", "quick_spell_2", "quick_spell_3",
		"quick_spell_4", "quick_spell_5", "quick_spell_6", "quick_spell_7",
		"quick_spell_8", "quick_spell_9", "quick_spell_10", "quick_spell_11",
		"quick_spell_12"],
}

signal setting_changed(section: String, key: String, value: Variant)
signal binding_changed(action: String)
signal refresh_requested
var pages: Dictionary = {}

var panel: PanelContainer
var tabs: TabContainer
var binding_rows: Dictionary = {}
var capture_label: Label
## What the map cache is costing on disk, refreshed when the window opens.
var map_cache_size: Label
var fps_limit_option: OptionButton
var look_toggle: CheckBox
var quality_option: OptionButton
var name_distance_slider: HSlider
var name_distance_value: Label

## The action waiting for a key. While this is set the window swallows every
## key press, so a rebind cannot fire the action it is rebinding.
var capturing := ""

func _ready() -> void:
	name = "SettingsLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	if panel.visible:
		close()
	else:
		open_tab()

## Context shortcuts open the same window at a particular tab; they never
## toggle it closed or create another settings popup.
func open_tab(section := "") -> void:
	if pages.has(section):
		tabs.current_tab = tabs.get_tab_idx_from_control(
			(pages[section] as Control).get_parent() as Control)
	panel.show()
	panel.move_to_front()
	_fit_to_view()
	_refresh_bindings()
	_refresh_map_cache()
	refresh_requested.emit()

func page_body(section: String) -> VBoxContainer:
	return pages[section] as VBoxContainer

func tab_index_for(control: Control) -> int:
	var page: Node = control
	while page != null and page.get_parent() != tabs:
		page = page.get_parent()
	return tabs.get_tab_idx_from_control(page as Control) if page != null else -1

func close() -> void:
	capturing = ""
	capture_label.hide()
	panel.hide()

## The tab titles, in order. Used by the tests and by nothing else.
func tab_titles() -> Array[String]:
	var titles: Array[String] = []
	for index: int in range(tabs.get_tab_count()):
		titles.append(tabs.get_tab_title(index))
	return titles

func begin_capture(action: String) -> void:
	capturing = action
	capture_label.text = tr("ELORIA_SETTINGS_CAPTURE").format({"action": action})
	capture_label.show()

## Applies a captured key to an action. Returns false when the event is not a
## key, or when the player pressed Escape to keep what they had.
func apply_capture(event: InputEvent) -> bool:
	if capturing.is_empty() or not event is InputEventKey:
		return false
	var key: InputEventKey = event as InputEventKey
	var action: String = capturing
	capturing = ""
	capture_label.hide()
	if key.physical_keycode == KEY_ESCAPE:
		return false
	var binding := InputEventKey.new()
	binding.physical_keycode = key.physical_keycode
	binding.shift_pressed = key.shift_pressed
	binding.ctrl_pressed = key.ctrl_pressed
	binding.alt_pressed = key.alt_pressed
	InputMap.action_erase_events(action)
	InputMap.action_add_event(action, binding)
	_refresh_bindings()
	binding_changed.emit(action)
	return true

## Every rebound action, as text this client can store and read back. An
## action whose binding cannot be written as text is left out rather than
## stored as an empty string, which would read back as "unbind this".
func stored_bindings() -> Dictionary:
	var stored: Dictionary = {}
	for group: Variant in BINDABLE:
		for action: Variant in BINDABLE[group]:
			var name: String = str(action)
			if not InputMap.has_action(name):
				continue
			var events: Array[InputEvent] = InputMap.action_get_events(name)
			if events.is_empty():
				continue
			var described: String = _describe(events[0])
			if not described.is_empty():
				stored[name] = described
	return stored

## Defaults this client used to ship and has since replaced. The settings
## file records every bound action, not only the ones a player chose, so a
## stored value equal to the superseded default is somebody who never touched
## it: the current default applies instead. Anything else is a real choice
## and is restored, including a player who picked the old key deliberately
## after the change, because by then it is no longer what this map says.
##
## The spell quick slots were Shift+number until they moved to Alt+number,
## where Eternal Lands has kept K_SPELL1..12 all along.
const SUPERSEDED_DEFAULTS := {
	"quick_spell_1": "Shift+1", "quick_spell_2": "Shift+2",
	"quick_spell_3": "Shift+3", "quick_spell_4": "Shift+4",
	"quick_spell_5": "Shift+5", "quick_spell_6": "Shift+6",
	"quick_spell_7": "Shift+7", "quick_spell_8": "Shift+8",
	"quick_spell_9": "Shift+9", "quick_spell_10": "Shift+0",
}

## Restores bindings saved by a previous session.
##
## A stored value that cannot be read back leaves the action exactly as it is.
## Erasing first and then failing to parse would silently unbind the action,
## which is how a settings file written by an older build could take the map
## key away and leave nothing to press.
func restore_bindings(stored: Dictionary) -> int:
	var restored := 0
	for action: Variant in stored:
		var name: String = str(action)
		if not InputMap.has_action(name):
			continue
		if str(stored[action]) == str(SUPERSEDED_DEFAULTS.get(name, "")):
			continue
		var event: InputEventKey = _parse(str(stored[action]))
		if event == null:
			continue
		InputMap.action_erase_events(name)
		# Settings store the first shortcut. Restore every shipped shortcut
		# when that value is the default, so saving cannot discard its aliases.
		var defaults: Dictionary = ProjectSettings.get_setting("input/" + name, {})
		var default_events: Array = defaults.get("events", [])
		if not default_events.is_empty() and str(stored[action]) == _describe(default_events[0]):
			for default_event: InputEvent in default_events:
				InputMap.action_add_event(name, default_event)
		else:
			InputMap.action_add_event(name, event)
		restored += 1
	_refresh_bindings()
	return restored

func _describe(event: InputEvent) -> String:
	if not event is InputEventKey:
		return ""
	var key: InputEventKey = event as InputEventKey
	var parts: Array[String] = []
	if key.ctrl_pressed:
		parts.append("Ctrl")
	if key.shift_pressed:
		parts.append("Shift")
	if key.alt_pressed:
		parts.append("Alt")
	parts.append(OS.get_keycode_string(key.physical_keycode))
	return "+".join(parts)

func _parse(described: String) -> InputEventKey:
	if described.is_empty():
		return null
	var parts: PackedStringArray = described.split("+", false)
	var event := InputEventKey.new()
	for part: String in parts:
		match part:
			"Ctrl":
				event.ctrl_pressed = true
			"Shift":
				event.shift_pressed = true
			"Alt":
				event.alt_pressed = true
			_:
				event.physical_keycode = OS.find_keycode_from_string(part)
	return event if event.physical_keycode != 0 else null

func binding_text(action: String) -> String:
	var descriptions: Array[String] = []
	if InputMap.has_action(action):
		for event: InputEvent in InputMap.action_get_events(action):
			var described := _describe(event)
			if not described.is_empty():
				descriptions.append(described)
	return " / ".join(descriptions) if not descriptions.is_empty() else tr("ELORIA_SETTINGS_UNBOUND")

func _refresh_bindings() -> void:
	for action: Variant in binding_rows:
		var button: Button = binding_rows[action] as Button
		button.text = binding_text(str(action))

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "SettingsWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.position = Vector2(
		(1280.0 - RESERVED_RIGHT_RAIL - PANEL_SIZE.x) * 0.5, 90.0)
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)

	var column := VBoxContainer.new()
	column.name = "SettingsBody"
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "SettingsHeader"
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.name = "SettingsTitle"
	title.text = tr("ELORIA_SETTINGS_TITLE")
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_button := Button.new()
	close_button.name = "SettingsWindowClose"
	close_button.text = tr("ELORIA_SETTINGS_CLOSE")
	close_button.pressed.connect(close)
	header.add_child(close_button)

	tabs = TabContainer.new()
	tabs.name = "SettingsTabs"
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(tabs)
	_build_hud()
	_build_chat()
	_new_page("Minimap", "Minimap")
	_new_page("Banners", "Banners")
	_build_graphics()
	_build_camera()
	_new_page("Audio", "Audio")
	_new_page("Inventory", "Inventory")
	_new_page("Spells", "Spells")
	_build_gameplay()
	_build_controls()
	tabs.tab_changed.connect(func(_index: int) -> void:
		capturing = ""
		capture_label.hide()
		refresh_requested.emit())

	capture_label = Label.new()
	capture_label.name = "SettingsCapture"
	capture_label.hide()
	column.add_child(capture_label)
	get_viewport().size_changed.connect(_fit_to_view)

## Every page scrolls independently. A growing list of preferences must not
## enlarge the window past the screen or cover the fixed resource rail.
func _new_page(section: String, title: String) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = section
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	tabs.set_tab_title(tabs.get_tab_idx_from_control(scroll), title)
	var body := VBoxContainer.new()
	body.name = section
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 8)
	scroll.add_child(body)
	pages[section] = body
	return body

func _fit_to_view() -> void:
	if panel == null:
		return
	var available := get_viewport_rect().size - Vector2(
		RESERVED_RIGHT_RAIL + 12.0, WindowDrag.RESERVED_BOTTOM_BAR + 12.0)
	panel.size = PANEL_SIZE.min(available.max(Vector2(500.0, 240.0)))
	(panel.get_node("WindowDrag") as WindowDrag).clamp_into_view()

## The HUD switches, worded the way Eternal Lands' HUD options tab words them.
## Each one shows or hides a piece of the fixed HUD; main.gd applies and
## persists them.
func _build_hud() -> void:
	var page := _new_page("HUD", "HUD")
	_add_toggle(page, "show_fps", "Show FPS", true)
	_add_toggle(page, "analog_clock", "Analog Clock", true)
	_add_toggle(page, "digital_clock", "Digital Clock", true)
	_add_toggle(page, "show_game_seconds", "Show Game Seconds", true)
	_add_toggle(page, "knowledge_bar", "Knowledge Bar", true)
	_add_toggle(page, "hud_timer", "Countdown/Stopwatch Timer", true)
	_add_toggle(page, "side_stats", "Stats In HUD", true)
	_add_toggle(page, "indicators", "Show Status Indicators in HUD", true)
	_add_toggle(page, "chat_timestamps", "Show Time Stamps", true)
	_add_toggle(page, "combat_hud", tr("ELORIA_SETTINGS_COMBAT_HUD"), true)
	_add_toggle(page, "combat_hud_pinned", "Keep combat HUD visible", false)
	_add_toggle(page, "timer_stopwatch", "Timer: stopwatch mode", false)
	_add_number(page, "timer_start_seconds", "Countdown start (seconds)", 0, 599, 90)
	# Two columns on wider screens; one on smaller screens or a larger UI
	# scale. This keeps common switches in view without imposing a wide
	# minimum on the window.
	var switches := GridContainer.new()
	switches.name = "HudSwitches"
	switches.add_theme_constant_override("h_separation", 16)
	switches.add_theme_constant_override("v_separation", 6)
	page.add_child(switches)
	page.move_child(switches, 0)
	for row: Node in page.get_children():
		if row is HBoxContainer and row.get_child_count() == 1 and row.get_child(0) is CheckBox:
			row.reparent(switches, false)
	page.resized.connect(func() -> void:
		switches.columns = 2 if page.size.x >= 700.0 else 1)

func _build_chat() -> void:
	var page := _new_page("Chat", "Chat")
	_add_toggle(page, "chat_combined", "Combine system messages and conversations", false)
	for prefix: String in ["chat_", "system_chat_"]:
		var caption := Label.new()
		caption.text = "Conversation window" if prefix == "chat_" else "System window"
		caption.add_theme_font_size_override("font_size", 18)
		page.add_child(caption)
		_add_toggle(page, prefix + "visible", "Show this window", true)
		_add_toggle(page, prefix + "locked", "Lock position and size", false)
		_add_number(page, prefix + "font_size", "Text size", 10, 28, 16 if prefix == "chat_" else 14)
		_add_number(page, prefix + "background_opacity", "Soft-fade opacity (0 = transparent)", 0, 0.8, 0.30 if prefix == "chat_" else 0.25, 0.05)
		_add_number(page, prefix + "line_spacing", "Line spacing", 0, 12, 2)
		_add_number(page, prefix + "idle_fade", "Dim after idle seconds (0 = never)", 0, 120, 0)
		_add_button(page, prefix + "reset_layout", "Reset position and size")
	var hint := Label.new()
	hint.text = "Drag either header to move it; drag its corner to resize. Each layout is saved.\nThe system window returns to its saved position when you separate the feeds."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(hint)

func _build_graphics() -> void:
	var page := _new_page("Graphics", tr("ELORIA_SETTINGS_GRAPHICS"))
	_add_fps_limit_row(page)
	# The look above the quality: whether it is on decides most of what the
	# quality changes.
	_add_look_row(page)
	_add_quality_row(page)
	_add_toggle(page, "shadows", tr("ELORIA_SETTINGS_SHADOWS"), true)
	_add_toggle(page, "particles", tr("ELORIA_SETTINGS_PARTICLES"), true)
	_add_toggle(page, "nameplates", tr("ELORIA_SETTINGS_NAMEPLATES"), true)
	_add_name_distance_row(page)
	# The combat box can also be dismissed from its own right-click menu, so
	# this is the way back once a player has done that.
	_add_map_cache_row(page)

func _add_fps_limit_row(page: VBoxContainer) -> void:
	var row := HBoxContainer.new()
	page.add_child(row)
	var caption := Label.new()
	caption.text = tr("ELORIA_SETTINGS_FPS_LIMIT")
	caption.custom_minimum_size = Vector2(200.0, 0.0)
	row.add_child(caption)
	fps_limit_option = OptionButton.new()
	fps_limit_option.name = "fps_limit"
	fps_limit_option.custom_minimum_size = Vector2(220.0, 0.0)
	fps_limit_option.tooltip_text = tr("ELORIA_SETTINGS_FPS_LIMIT_HINT")
	for limit: int in FPS_LIMITS:
		fps_limit_option.add_item(tr("ELORIA_SETTINGS_FPS_UNLIMITED")
			if limit == 0 else "%d FPS" % limit, limit)
	fps_limit_option.item_selected.connect(func(index: int) -> void:
		setting_changed.emit(page.name, "fps_limit",
			fps_limit_option.get_item_id(index)))
	row.add_child(fps_limit_option)

func restore_fps_limit(value: int) -> void:
	# Selecting an item programmatically does not emit item_selected.
	fps_limit_option.select(fps_limit_option.get_item_index(value))

## Graphics quality: Low, Medium or High, each item's id its
## LookProfile.Quality. It takes effect at once, and its hint says what it
## changes: the shadows always, the look's costlier layers while it is on.
func _add_quality_row(page: VBoxContainer) -> void:
	var row := HBoxContainer.new()
	row.name = "QualityRow"
	page.add_child(row)
	var caption := Label.new()
	caption.text = tr("ELORIA_SETTINGS_QUALITY")
	caption.custom_minimum_size = Vector2(200.0, 0.0)
	row.add_child(caption)
	quality_option = OptionButton.new()
	quality_option.name = "quality"
	quality_option.custom_minimum_size = Vector2(220.0, 0.0)
	quality_option.tooltip_text = tr("ELORIA_SETTINGS_QUALITY_HINT")
	# By Quality, spelled out so the translation test can see every key.
	var labels: Array[String] = [tr("ELORIA_SETTINGS_QUALITY_LOW"),
		tr("ELORIA_SETTINGS_QUALITY_MEDIUM"), tr("ELORIA_SETTINGS_QUALITY_HIGH")]
	for level: int in labels.size():
		quality_option.add_item(labels[level], level)
	quality_option.select(quality_option.get_item_index(LookProfileScript.QUALITY_DEFAULT))
	quality_option.item_selected.connect(func(index: int) -> void:
		setting_changed.emit(page.name, "quality", quality_option.get_item_id(index)))
	row.add_child(quality_option)

## The painted look's switch: a checkbox like the window's other switches,
## with a hint that says what Off draws and that it takes effect at once.
func _add_look_row(page: VBoxContainer) -> void:
	_add_toggle(page, "look", tr("ELORIA_SETTINGS_LOOK"), LookProfileScript.LOOK_DEFAULT)
	look_toggle = page.find_child("look", true, false) as CheckBox
	look_toggle.tooltip_text = tr("ELORIA_SETTINGS_LOOK_HINT")

## Shows the player's switch without re-emitting it. While ELORIA_LOOK
## decides for this session (`forced`), the box is greyed out and says so,
## still showing the player's own choice, which is what the file keeps.
func restore_look(value: bool, forced := false) -> void:
	look_toggle.set_pressed_no_signal(value)
	look_toggle.disabled = forced
	look_toggle.tooltip_text = tr("ELORIA_SETTINGS_FORCED_HINT").format(
		{"variable": LookProfileScript.ENABLE_VARIABLE}) if forced \
		else tr("ELORIA_SETTINGS_LOOK_HINT")

## Shows the player's quality without re-emitting it, greyed out while
## ELORIA_LOOK_QUALITY decides (`forced`).
func restore_quality(level: int, forced := false) -> void:
	quality_option.select(quality_option.get_item_index(level))
	quality_option.disabled = forced
	quality_option.tooltip_text = tr("ELORIA_SETTINGS_FORCED_HINT").format(
		{"variable": LookProfileScript.QUALITY_VARIABLE}) if forced \
		else tr("ELORIA_SETTINGS_QUALITY_HINT")

## A slider with its reading beside it: unlike the camera's sensitivities, a
## distance is a number the player can check against the world.
func _add_name_distance_row(page: VBoxContainer) -> void:
	var row := HBoxContainer.new()
	page.add_child(row)
	var caption := Label.new()
	caption.text = tr("ELORIA_SETTINGS_NAME_DISTANCE")
	caption.custom_minimum_size = Vector2(200.0, 0.0)
	row.add_child(caption)
	name_distance_slider = HSlider.new()
	name_distance_slider.name = "name_distance"
	name_distance_slider.min_value = NAME_DISTANCE_MIN
	name_distance_slider.max_value = NAME_DISTANCE_MAX
	name_distance_slider.step = 5.0
	name_distance_slider.value = NAME_DISTANCE_DEFAULT
	name_distance_slider.custom_minimum_size = Vector2(220.0, 0.0)
	name_distance_slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	name_distance_slider.tooltip_text = tr("ELORIA_SETTINGS_NAME_DISTANCE_HINT")
	name_distance_slider.value_changed.connect(func(moved: float) -> void:
		_show_name_distance(moved)
		setting_changed.emit(page.name, "name_distance", moved))
	row.add_child(name_distance_slider)
	name_distance_value = Label.new()
	name_distance_value.name = "NameDistanceValue"
	row.add_child(name_distance_value)
	_show_name_distance(NAME_DISTANCE_DEFAULT)

func restore_name_distance(metres: float) -> void:
	name_distance_slider.set_value_no_signal(metres)
	_show_name_distance(metres)

func _show_name_distance(metres: float) -> void:
	name_distance_value.text = "%d m" % roundi(metres)

## The map cache: a switch, what it is costing, and a way to be rid of it.
##
## It earns a row of its own rather than a plain toggle because it is the only
## setting in this window that spends the player's disk - 30-40 MB a region,
## about 400 MB if they walk the whole world - and a switch that quietly does
## that with no way to see it or undo it would be the wrong shape. The size is
## read when the window opens rather than every frame; it changes only when a
## region is visited for the first time.
##
## The row also carries the answer to "the server says my map is not the one it
## expects", which is the only thing the server's map digest is for. It cannot
## affect the cache - that is keyed on the package this machine actually has -
## so it has nowhere else to be seen.
func _add_map_cache_row(page: VBoxContainer) -> void:
	var row := HBoxContainer.new()
	row.name = "MapCacheRow"
	page.add_child(row)
	var toggle := CheckBox.new()
	toggle.name = "map_cache"
	toggle.text = tr("ELORIA_SETTINGS_MAP_CACHE")
	toggle.button_pressed = MapCache.is_enabled()
	toggle.toggled.connect(func(pressed: bool) -> void:
		MapCache.set_enabled(pressed)
		_refresh_map_cache()
		setting_changed.emit(page.name, "map_cache", pressed))
	row.add_child(toggle)
	map_cache_size = Label.new()
	map_cache_size.name = "MapCacheSize"
	map_cache_size.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	map_cache_size.clip_text = true
	map_cache_size.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(map_cache_size)
	var clear := Button.new()
	clear.name = "map_cache_clear"
	clear.text = tr("ELORIA_SETTINGS_MAP_CACHE_CLEAR")
	clear.pressed.connect(func() -> void:
		var removed: int = MapCache.clear_disk()
		_refresh_map_cache()
		setting_changed.emit(page.name, "map_cache_clear", removed))
	row.add_child(clear)
	_refresh_map_cache()

## What the row says: the size on disk, and whatever the server's digest had to
## say about this install.
func _refresh_map_cache() -> void:
	if map_cache_size == null:
		return
	var text: String = MapCache.describe_size(MapCache.total_bytes())
	var digests: String = MapCache.digest_summary()
	if not digests.is_empty():
		text += " - " + digests
	map_cache_size.text = text
	map_cache_size.tooltip_text = text

func _build_camera() -> void:
	var page := _new_page("Camera", tr("ELORIA_SETTINGS_CAMERA"))
	_add_slider(page, "rotation_sensitivity", tr("ELORIA_SETTINGS_ROTATION"), 0.05, 1.0, 0.25)

func _build_gameplay() -> void:
	var page := _new_page("Gameplay", tr("ELORIA_SETTINGS_GAMEPLAY"))
	var hint := Label.new()
	hint.text = tr("ELORIA_SETTINGS_SERVER_HINT")
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(hint)
	_add_button(page, "target_mode_strong", tr("ELORIA_SETTINGS_TARGET_STRONG"))
	_add_button(page, "target_mode_weak", tr("ELORIA_SETTINGS_TARGET_WEAK"))
	_add_button(page, "autogather", tr("ELORIA_SETTINGS_AUTOGATHER"))

func _build_controls() -> void:
	var list := _new_page("Controls", tr("ELORIA_SETTINGS_CONTROLS"))
	for group: Variant in BINDABLE:
		var heading := Label.new()
		heading.text = str(group)
		list.add_child(heading)
		for action: Variant in BINDABLE[group]:
			var name: String = str(action)
			var row := HBoxContainer.new()
			row.name = "Bind_" + name
			list.add_child(row)
			var label := Label.new()
			label.text = name.replace("_", " ")
			label.custom_minimum_size = Vector2(220.0, 0.0)
			row.add_child(label)
			var button := Button.new()
			button.name = "Binding"
			button.custom_minimum_size = Vector2(150.0, 0.0)
			button.pressed.connect(begin_capture.bind(name))
			row.add_child(button)
			binding_rows[name] = button

## Pushes a stored value back onto a toggle without re-emitting it, so the
## panel opens showing what the client actually has rather than the default it
## was built with.
func restore_toggle(key: String, value: bool) -> bool:
	var toggle: CheckBox = panel.find_child(key, true, false) as CheckBox
	if toggle == null:
		return false
	toggle.set_pressed_no_signal(value)
	return true

## A square CheckBox rather than a pill switch: Eternal Lands' options are
## checkboxes, and the whole window is meant to read like its Options window.
func _add_toggle(page: VBoxContainer, key: String, label: String,
		value: bool) -> void:
	var row := HBoxContainer.new()
	page.add_child(row)
	var toggle := CheckBox.new()
	toggle.name = key
	toggle.text = label
	toggle.button_pressed = value
	toggle.toggled.connect(func(pressed: bool) -> void:
		setting_changed.emit(page.name, key, pressed))
	row.add_child(toggle)

func _add_slider(page: VBoxContainer, key: String, label: String,
		minimum: float, maximum: float, value: float) -> void:
	var row := HBoxContainer.new()
	page.add_child(row)
	var caption := Label.new()
	caption.text = label
	caption.custom_minimum_size = Vector2(200.0, 0.0)
	row.add_child(caption)
	var slider := HSlider.new()
	slider.name = key
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = 0.01
	slider.value = value
	slider.custom_minimum_size = Vector2(220.0, 0.0)
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var reading := Label.new()
	reading.name = key + "_value"
	reading.custom_minimum_size.x = 60.0
	reading.text = "%.3f" % value
	slider.value_changed.connect(func(moved: float) -> void:
		reading.text = "%.3f" % moved
		setting_changed.emit(page.name, key, moved))
	row.add_child(slider)
	row.add_child(reading)

func _add_number(page: VBoxContainer, key: String, label: String,
		minimum: float, maximum: float, value: float, step := 1.0) -> void:
	var row := HBoxContainer.new()
	page.add_child(row)
	var caption := Label.new()
	caption.text = label
	caption.custom_minimum_size.x = 240.0
	row.add_child(caption)
	var number := SpinBox.new()
	number.name = key
	number.min_value = minimum
	number.max_value = maximum
	number.step = step
	number.value = value
	number.custom_minimum_size.x = 160.0
	number.value_changed.connect(func(changed: float) -> void:
		setting_changed.emit(page.name, key, changed))
	row.add_child(number)

func add_choice(section: String, key: String, label: String,
		labels: Array, values: Array) -> void:
	var page := page_body(section)
	var row := HBoxContainer.new()
	page.add_child(row)
	var caption := Label.new()
	caption.text = label
	caption.custom_minimum_size.x = 240.0
	row.add_child(caption)
	var option := OptionButton.new()
	option.name = key
	option.custom_minimum_size.x = 220.0
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for index: int in labels.size():
		option.add_item(str(labels[index]))
		option.set_item_metadata(index, values[index])
	option.item_selected.connect(func(index: int) -> void:
		setting_changed.emit(section, key, option.get_item_metadata(index)))
	row.add_child(option)

func add_audio_controls() -> void:
	var page := page_body("Audio")
	for category: String in AudioMix.CATEGORIES:
		var info: Dictionary = AudioMix.CATEGORIES[category]
		var key := "audio_" + category
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		page.add_child(row)
		var caption := Label.new()
		caption.text = str(info.label)
		caption.custom_minimum_size.x = 200.0
		row.add_child(caption)
		var slider := HSlider.new()
		slider.name = key
		slider.max_value = 1.0
		slider.step = 0.01
		slider.value = float(info.volume)
		slider.custom_minimum_size.x = 200.0
		slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		slider.tooltip_text = "Adjust %s independently. 0%% mutes this category." % str(info.label).to_lower()
		row.add_child(slider)
		var reading := Label.new()
		reading.name = key + "_value"
		reading.custom_minimum_size.x = 52.0
		reading.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		reading.text = "%d%%" % roundi(slider.value * 100.0)
		row.add_child(reading)
		slider.value_changed.connect(func(value: float) -> void:
			reading.text = "%d%%" % roundi(value * 100.0)
			setting_changed.emit("Audio", key, value))
	# Credits stay at the end, below the controls they describe.
	page.move_child(page.get_node("AudioCreditsButton"), page.get_child_count() - 1)

## Refreshing controls never saves or emits a change. This also covers values
## changed by a HUD shortcut while the settings window was closed.
func restore_value(key: String, value: Variant) -> void:
	var control := panel.find_child(key, true, false)
	if control is OptionButton:
		var option := control as OptionButton
		for index: int in option.item_count:
			if option.get_item_metadata(index) == value:
				option.select(index)
				break
	elif control is BaseButton:
		(control as BaseButton).set_pressed_no_signal(bool(value))
	elif control is Range:
		(control as Range).set_value_no_signal(float(value))
		var reading := panel.find_child(key + "_value", true, false) as Label
		if reading != null:
			reading.text = "%d%%" % roundi(float(value) * 100.0) if key.begins_with("audio_") else "%.3f" % float(value)

func _add_button(page: VBoxContainer, key: String, label: String) -> void:
	var button := Button.new()
	button.name = key
	button.text = label
	button.pressed.connect(func() -> void:
		setting_changed.emit(page.name, key, true))
	page.add_child(button)
