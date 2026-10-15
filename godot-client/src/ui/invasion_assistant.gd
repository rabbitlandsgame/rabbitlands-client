class_name InvasionAssistantWindow
extends Window

signal command_requested(command: String)

const MapCanvasScript := preload("res://src/ui/invasion_map_canvas.gd")
const MAP_REFRESH_SECONDS := 5.0
const INDEX_REFRESH_SECONDS := 15.0
const VIEWPORT_MARGIN := Vector2i(32, 32)
const PREFERENCE_KEY := "invasion_assistant"
## The window is laid out at this size at every scale, and drawn at whatever
## scale the grip has been dragged to. It is half the footprint the assistant
## used to claim - 0.7 of each edge of the 1120x720 it opened at, which
## covered most of a 1280x720 client - and every font and column below is
## sized for it rather than for the old one.
const CONTENT_SIZE := Vector2i(784, 504)
## The bounds the inventory panel's grip already uses, so the two windows
## resize with the same reach and stop in the same places.
const MIN_SCALE := 0.65
const MAX_SCALE := 1.75
const COMPACT_FONT_SIZE := 12
const RESIZE_GRIP_SIZE := Vector2(22, 22)
## A drag changes the scale every frame; the preference is written once the
## player stops moving rather than once per frame.
const SIZE_SAVE_DELAY := 0.5

var map_registry: Dictionary = {}
var coordinate_context: RefCounted
var index_state: Dictionary = {}
var map_state: Dictionary = {}
var groups_state: Dictionary = {}
var monsters_state: Dictionary = {}
var selected_map_id := ""
var selected_group: Dictionary = {}
var selected_monster: Dictionary = {}

var tabs: TabContainer
var summary: Label
var god_storage_button: Button
var map_filter: LineEdit
var map_list: ItemList
var map_canvas
var map_title: Label
var map_roster: RichTextLabel
var location_picker: OptionButton
var coordinate_x: SpinBox
var coordinate_y: SpinBox
var teleport_button: Button
var map_status: Label
var group_filter: LineEdit
var group_list: ItemList
var group_detail: RichTextLabel
var group_open_map: Button
var group_create: Button
var group_duplicate: Button
var group_spawn: Button
var group_clear: Button
var group_delete: Button
var group_name: LineEdit
var group_description: LineEdit
var group_map: OptionButton
var group_minimum: SpinBox
var group_maximum: SpinBox
var group_health: SpinBox
var group_boss_type: LineEdit
var group_boss_name: LineEdit
var group_save: Button
var group_composition: ItemList
var group_remove_quantity: SpinBox
var group_remove_monster: Button
var monster_filter: LineEdit
var monster_updated_only: CheckBox
var monster_list: ItemList
var monster_detail: RichTextLabel
var monster_quantity: SpinBox
var monster_group: OptionButton
var monster_add_to_group: Button
var monster_create_group: Button
var monster_spawn_here: Button
var create_dialog: ConfirmationDialog
var create_name: LineEdit
var create_map: OptionButton
var create_description: LineEdit
var status: Label
var resize_grip: Button
## What the player chose, and what the viewport currently allows. They part
## company on a screen too small for the chosen scale, and the choice is the
## one that gets remembered.
var _preferred_scale := 1.0
var _window_scale := 1.0
var _resizing := false
var _resize_start_mouse := Vector2i.ZERO
var _resize_start_scale := 1.0
var _size_save_countdown := 0.0
var _map_refresh_elapsed := 0.0
var _index_refresh_elapsed := 0.0
var _pending_created_group := ""
var _pending_add_to_created := false
var _texture_cache: Dictionary = {}


func _ready() -> void:
	title = "Invasion Assistant"
	# The corner grip is the only way to resize this window. A border drag
	# would change the frame without changing the scale of what is inside it,
	# which is exactly how a narrowed window loses a column.
	unresizable = true
	_preferred_scale = WindowPreferences.stored_scale(PREFERENCE_KEY, 1.0,
		MIN_SCALE, MAX_SCALE)
	close_requested.connect(hide)
	visibility_changed.connect(_on_visibility_changed)
	_build_ui()
	get_tree().root.size_changed.connect(_fit_to_viewport)
	_fit_to_viewport()
	hide()
	set_process(true)


func _process(delta: float) -> void:
	if visible:
		_keep_on_screen()
	if _size_save_countdown > 0.0:
		_size_save_countdown -= delta
		if _size_save_countdown <= 0.0:
			_flush_size_preference()
	if not visible or tabs == null or tabs.current_tab != 0 or selected_map_id.is_empty():
		return
	_map_refresh_elapsed += delta
	_index_refresh_elapsed += delta
	if _map_refresh_elapsed >= MAP_REFRESH_SECONDS:
		_map_refresh_elapsed = 0.0
		command_requested.emit("#invasion_assistant map " + selected_map_id)
	if _index_refresh_elapsed >= INDEX_REFRESH_SECONDS:
		_index_refresh_elapsed = 0.0
		command_requested.emit("#invasion_assistant refresh")


func _available_size() -> Vector2i:
	var viewport_size := get_tree().root.size
	return Vector2i(maxi(240, viewport_size.x - VIEWPORT_MARGIN.x - int(WindowDrag.RESERVED_RIGHT_RAIL)),
		maxi(200, viewport_size.y - VIEWPORT_MARGIN.y - int(WindowDrag.RESERVED_BOTTOM_BAR)))


## Reopening the assistant restores the scale the player left it at rather
## than the shipped one. A viewport too small to hold that scale only draws it
## smaller - the preference itself is untouched, so the window comes back at
## its full remembered size on a screen that can hold it.
func _fit_to_viewport() -> void:
	_apply_window_scale(_preferred_scale)
	var viewport_size := get_tree().root.size
	position = Vector2i(maxi(0, (viewport_size.x - size.x) / 2),
		maxi(0, (viewport_size.y - size.y) / 2))
	_keep_on_screen()


## The window's pixel size and the scale its contents are drawn at move
## together, so the control tree is laid out across the same CONTENT_SIZE at
## every scale. Shrinking the window makes the type, the lists and the map
## smaller; it never takes a column away, which is the whole point of scaling
## the window rather than resizing its frame.
func _apply_window_scale(requested: float) -> void:
	var available := _available_size()
	var ceiling: float = maxf(MIN_SCALE, minf(MAX_SCALE, minf(
		float(available.x) / float(CONTENT_SIZE.x),
		float(available.y) / float(CONTENT_SIZE.y))))
	_window_scale = clampf(requested, MIN_SCALE, ceiling)
	content_scale_factor = _window_scale
	size = Vector2i(roundi(float(CONTENT_SIZE.x) * _window_scale),
		roundi(float(CONTENT_SIZE.y) * _window_scale))


## Applies a scale the player asked for from the corner grip, and records it
## as the new preference.
func resize_to_scale(requested: float) -> void:
	_apply_window_scale(requested)
	_preferred_scale = _window_scale
	_size_save_countdown = SIZE_SAVE_DELAY
	_keep_on_screen()


func _keep_on_screen() -> void:
	var viewport_size := get_tree().root.size
	position = Vector2i(
		clampi(position.x, 0, maxi(0, viewport_size.x - size.x - int(WindowDrag.RESERVED_RIGHT_RAIL))),
		clampi(position.y, 0, maxi(0, viewport_size.y - size.y - int(WindowDrag.RESERVED_BOTTOM_BAR))))


func _flush_size_preference() -> void:
	_size_save_countdown = 0.0
	WindowPreferences.store_scale(PREFERENCE_KEY, _preferred_scale)


func _on_resize_grip_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return
		_resizing = mouse.pressed
		if mouse.pressed:
			_resize_start_mouse = _pointer_position()
			_resize_start_scale = _window_scale
		else:
			_flush_size_preference()
		resize_grip.accept_event()
	elif event is InputEventMouseMotion and _resizing:
		# Measured against the unscaled layout and read off whichever axis the
		# player moved further, which is how the inventory panel's grip reads a
		# drag. The pointer is taken from outside the window because the grip
		# travels as the window grows, and a window-relative delta would chase
		# itself.
		var delta := Vector2(_pointer_position() - _resize_start_mouse)
		var normalized := Vector2(delta.x / float(CONTENT_SIZE.x),
			delta.y / float(CONTENT_SIZE.y))
		var scale_delta: float = (normalized.x if absf(normalized.x) >= absf(normalized.y)
			else normalized.y)
		resize_to_scale(_resize_start_scale + scale_delta)
		resize_grip.accept_event()


func _pointer_position() -> Vector2i:
	# An embedded subwindow is positioned and sized in the root viewport's
	# space, so the drag has to be measured there too - the screen pointer
	# would run ahead of the grip whenever the HUD scale is not 100%.
	if is_embedded():
		return Vector2i(get_tree().root.get_mouse_position())
	return DisplayServer.mouse_get_position()


func _on_visibility_changed() -> void:
	_map_refresh_elapsed = 0.0
	_index_refresh_elapsed = 0.0
	if visible:
		_fit_to_viewport()
	elif _size_save_countdown > 0.0:
		# Closing the window must not lose a resize that was still settling.
		_flush_size_preference()


func configure_registry(value: Dictionary) -> void:
	map_registry = value


func _is_last_page(update: Dictionary) -> bool:
	# A server that sends the state whole carries no page fields at all, so an
	# absent "pages" means this single message is the whole thing.
	var pages: int = int(update.get("pages", 1))
	return int(update.get("page", 0)) >= pages - 1


func _accumulate(previous: Dictionary, update: Dictionary, key: String) -> Dictionary:
	# The group and monster lists outgrew one packet - 600 invasion groups
	# against a 64KB ceiling - so the server sends them a page at a time. The
	# first page replaces what was held; the rest append to it. Rebuilding on
	# every page would make the list flicker through nine partial states and
	# lose the player's selection each time.
	var merged: Dictionary = update.duplicate(true)
	if int(update.get("page", 0)) > 0:
		var carried: Array = (previous.get(key, []) as Array).duplicate(true)
		carried.append_array(merged.get(key, []) as Array)
		merged[key] = carried
	return merged


func apply_update(update: Dictionary) -> void:
	var kind := str(update.get("kind", ""))
	match kind:
		"index":
			index_state = update.duplicate(true)
			if selected_map_id.is_empty():
				selected_map_id = str(update.get("selected_map", ""))
			_rebuild_maps()
			_update_summary()
		"map":
			var incoming: String = str(update.get("map", {}).get("id", ""))
			if not selected_map_id.is_empty() and incoming != selected_map_id:
				return # A response for the previous selection cannot change bounds.
			if int(update.get("page", 0)) > 0 and incoming != str(map_state.get("map", {}).get("id", "")):
				return
			map_state = _accumulate(map_state, update, "creatures")
			var map: Dictionary = map_state.get("map", {}) as Dictionary
			selected_map_id = str(map.get("id", selected_map_id))
			if _is_last_page(update):
				_show_map_state()
		"groups":
			groups_state = _accumulate(groups_state, update, "groups")
			if _is_last_page(update):
				_rebuild_groups()
		"monsters":
			monsters_state = _accumulate(monsters_state, update, "monsters")
			if _is_last_page(update):
				_rebuild_monsters()
	if not visible:
		_fit_to_viewport()
		popup()
		_fit_to_viewport()
		call_deferred("_fit_to_viewport")


func _build_ui() -> void:
	# One theme for the whole window instead of a font size on each control:
	# lists, buttons and spin boxes all shrink together, which is what buys
	# back the rows the halved window would otherwise lose.
	var compact := Theme.new()
	compact.default_font_size = COMPACT_FONT_SIZE
	theme = compact
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_top", 7)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_bottom", 7)
	add_child(margin)
	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 5)
	margin.add_child(root)

	var header := HBoxContainer.new()
	root.add_child(header)
	var heading := Label.new()
	heading.text = "INVASION ASSISTANT"
	heading.add_theme_font_size_override("font_size", 15)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(heading)
	summary = Label.new()
	summary.text = "Waiting for server snapshot…"
	header.add_child(summary)
	god_storage_button = Button.new()
	god_storage_button.text = "God storage"
	god_storage_button.tooltip_text = ("Open the god storage: 99999 of every item in the "
		+ "game, usable from anywhere. Deposits go to your own storage.")
	god_storage_button.pressed.connect(func() -> void: command_requested.emit("#god_storage"))
	header.add_child(god_storage_button)
	var refresh_all := Button.new()
	refresh_all.text = "Refresh"
	refresh_all.tooltip_text = "Refresh map counts and the current tab from the server"
	refresh_all.pressed.connect(_refresh_current)
	header.add_child(refresh_all)
	var close_button := Button.new()
	close_button.text = "×"
	close_button.tooltip_text = "Close invasion assistant"
	close_button.custom_minimum_size.x = 26
	close_button.pressed.connect(hide)
	header.add_child(close_button)

	tabs = TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tabs.tab_changed.connect(_on_tab_changed)
	root.add_child(tabs)
	_build_maps_tab()
	_build_groups_tab()
	_build_monsters_tab()
	_build_create_dialog()

	var status_row := HBoxContainer.new()
	root.add_child(status_row)
	status = Label.new()
	status.text = "Server-authorized invasion masters only. Click the map to stage a teleport."
	status.add_theme_color_override("font_color", Color("9fc0d4"))
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status.clip_text = true
	status_row.add_child(status)
	# Keeps the status line clear of the corner grip, which is anchored to the
	# window rather than to this row.
	var grip_gutter := Control.new()
	grip_gutter.custom_minimum_size.x = RESIZE_GRIP_SIZE.x
	status_row.add_child(grip_gutter)
	_build_resize_grip()


## The inventory panel resizes from a corner grip; the assistant gets the same
## handle so the two windows are dragged the same way, and it remembers where
## the drag left it.
func _build_resize_grip() -> void:
	resize_grip = Button.new()
	resize_grip.text = "◢"
	resize_grip.flat = true
	resize_grip.focus_mode = Control.FOCUS_NONE
	resize_grip.tooltip_text = "Drag to resize the invasion assistant"
	resize_grip.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	resize_grip.custom_minimum_size = RESIZE_GRIP_SIZE
	resize_grip.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	resize_grip.offset_left = -RESIZE_GRIP_SIZE.x
	resize_grip.offset_top = -RESIZE_GRIP_SIZE.y
	resize_grip.offset_right = 0.0
	resize_grip.offset_bottom = 0.0
	resize_grip.gui_input.connect(_on_resize_grip_gui_input)
	add_child(resize_grip)


func _build_maps_tab() -> void:
	var page := HSplitContainer.new()
	page.name = "Maps"
	tabs.add_child(page)
	var sidebar := VBoxContainer.new()
	sidebar.custom_minimum_size.x = 190
	page.add_child(sidebar)
	map_filter = LineEdit.new()
	map_filter.placeholder_text = "Filter server maps…"
	map_filter.text_changed.connect(func(_value: String) -> void: _rebuild_maps())
	sidebar.add_child(map_filter)
	map_list = ItemList.new()
	map_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map_list.item_selected.connect(_on_map_selected)
	map_list.item_activated.connect(_on_map_selected)
	sidebar.add_child(map_list)
	var legend := RichTextLabel.new()
	legend.bbcode_enabled = true
	legend.fit_content = true
	legend.custom_minimum_size.y = 58
	legend.text = ("[color=#68e7ff]●[/color] Player   "
		+ "[color=#ff6b63]◆[/color] Invader   "
		+ "[color=#ffc94f]◆[/color] Boss\n"
		+ "[color=#c8a8ff]■[/color] Spawn location   "
		+ "[color=#55cfee]■[/color] Portal\n"
		+ "Click anywhere to select exact coordinates.")
	sidebar.add_child(legend)

	var map_column := VBoxContainer.new()
	map_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page.add_child(map_column)
	map_title = Label.new()
	map_title.text = "Select a map"
	map_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	map_title.add_theme_font_size_override("font_size", 13)
	map_column.add_child(map_title)
	var map_split := HSplitContainer.new()
	map_split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map_column.add_child(map_split)
	map_canvas = MapCanvasScript.new()
	map_canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	map_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map_canvas.coordinate_selected.connect(_on_coordinate_selected)
	map_split.add_child(map_canvas)
	map_roster = RichTextLabel.new()
	map_roster.bbcode_enabled = true
	map_roster.custom_minimum_size.x = 150
	map_roster.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map_split.add_child(map_roster)

	var location_row := HBoxContainer.new()
	map_column.add_child(location_row)
	location_picker = OptionButton.new()
	location_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# An OptionButton is as wide as its longest item by default, and a
	# gauntlet's spawn points are named for their route, room and wave - 95
	# characters - which pushed Teleport off the window's right edge. The
	# picker takes the width the row leaves it; the open list still shows
	# every name whole.
	location_picker.fit_to_longest_item = false
	location_picker.clip_text = true
	location_picker.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	location_picker.item_selected.connect(_on_location_selected)
	location_row.add_child(location_picker)
	coordinate_x = SpinBox.new()
	coordinate_x.prefix = "X "
	coordinate_x.min_value = 0
	coordinate_x.max_value = 2047
	coordinate_x.custom_minimum_size.x = 84
	location_row.add_child(coordinate_x)
	coordinate_y = SpinBox.new()
	coordinate_y.prefix = "Y "
	coordinate_y.min_value = 0
	coordinate_y.max_value = 2047
	coordinate_y.custom_minimum_size.x = 84
	location_row.add_child(coordinate_y)
	teleport_button = Button.new()
	teleport_button.text = "Teleport"
	teleport_button.disabled = true
	teleport_button.tooltip_text = "Teleport your invasion-master character to the selected coordinates"
	teleport_button.pressed.connect(_teleport)
	location_row.add_child(teleport_button)
	map_status = Label.new()
	map_status.text = "Live markers are loaded on demand."
	map_status.add_theme_color_override("font_color", Color("a9bdc9"))
	map_column.add_child(map_status)


func _build_groups_tab() -> void:
	var page := HSplitContainer.new()
	page.name = "Spawn Groups"
	tabs.add_child(page)
	var list_column := VBoxContainer.new()
	list_column.custom_minimum_size.x = 228
	page.add_child(list_column)
	var list_actions := HBoxContainer.new()
	list_column.add_child(list_actions)
	group_create = Button.new()
	group_create.text = "Create group"
	group_create.pressed.connect(_show_create_group)
	list_actions.add_child(group_create)
	group_duplicate = Button.new()
	group_duplicate.text = "Duplicate"
	group_duplicate.disabled = true
	group_duplicate.pressed.connect(_duplicate_group)
	list_actions.add_child(group_duplicate)
	group_delete = Button.new()
	group_delete.text = "Delete"
	group_delete.disabled = true
	group_delete.pressed.connect(_delete_group)
	list_actions.add_child(group_delete)
	group_filter = LineEdit.new()
	group_filter.placeholder_text = "Filter by group, map, monster, or active…"
	group_filter.text_changed.connect(func(_value: String) -> void: _rebuild_groups())
	list_column.add_child(group_filter)
	group_list = ItemList.new()
	group_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	group_list.item_selected.connect(_on_group_selected)
	group_list.item_activated.connect(_on_group_selected)
	list_column.add_child(group_list)
	var detail_scroll := ScrollContainer.new()
	detail_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page.add_child(detail_scroll)
	var detail_column := VBoxContainer.new()
	detail_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_column.add_theme_constant_override("separation", 5)
	detail_scroll.add_child(detail_column)
	group_detail = RichTextLabel.new()
	group_detail.bbcode_enabled = true
	group_detail.fit_content = true
	group_detail.custom_minimum_size.y = 84
	group_detail.text = "Select a configured invasion spawn group."
	detail_column.add_child(group_detail)
	var runtime_actions := HBoxContainer.new()
	detail_column.add_child(runtime_actions)
	group_spawn = Button.new()
	group_spawn.text = "Spawn selected group"
	group_spawn.disabled = true
	group_spawn.tooltip_text = "Activate this defined group on its configured map"
	group_spawn.pressed.connect(_spawn_group)
	runtime_actions.add_child(group_spawn)
	group_clear = Button.new()
	group_clear.text = "Clear active group"
	group_clear.disabled = true
	group_clear.pressed.connect(_clear_group)
	runtime_actions.add_child(group_clear)
	group_open_map = Button.new()
	group_open_map.text = "Open group map"
	group_open_map.disabled = true
	group_open_map.pressed.connect(_open_group_map)
	runtime_actions.add_child(group_open_map)

	var editor_title := Label.new()
	editor_title.text = "LIVE GROUP BUILDER"
	editor_title.add_theme_font_size_override("font_size", 12)
	detail_column.add_child(editor_title)
	var editor := GridContainer.new()
	editor.columns = 2
	detail_column.add_child(editor)
	_add_form_label(editor, "Name")
	group_name = LineEdit.new()
	group_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	editor.add_child(group_name)
	_add_form_label(editor, "Description")
	group_description = LineEdit.new()
	editor.add_child(group_description)
	_add_form_label(editor, "Map")
	group_map = OptionButton.new()
	editor.add_child(group_map)
	_add_form_label(editor, "Population")
	var population := HBoxContainer.new()
	group_minimum = SpinBox.new()
	group_minimum.custom_minimum_size = Vector2(108, 0)
	group_minimum.prefix = "Min "
	group_minimum.min_value = 0
	group_minimum.max_value = 1000
	population.add_child(group_minimum)
	group_maximum = SpinBox.new()
	group_maximum.custom_minimum_size = Vector2(108, 0)
	group_maximum.prefix = "Max "
	group_maximum.min_value = 0
	group_maximum.max_value = 1000
	population.add_child(group_maximum)
	editor.add_child(population)
	_add_form_label(editor, "Health")
	group_health = SpinBox.new()
	group_health.prefix = "×"
	group_health.min_value = 0.1
	group_health.max_value = 100.0
	group_health.step = 0.1
	group_health.value = 1.0
	editor.add_child(group_health)
	_add_form_label(editor, "Boss type")
	group_boss_type = LineEdit.new()
	group_boss_type.placeholder_text = "Optional creature type"
	editor.add_child(group_boss_type)
	_add_form_label(editor, "Boss name")
	group_boss_name = LineEdit.new()
	group_boss_name.placeholder_text = "Optional display name"
	editor.add_child(group_boss_name)
	group_save = Button.new()
	group_save.text = "Save group settings"
	group_save.disabled = true
	group_save.tooltip_text = "Configured groups are read-only; duplicate one to edit it live"
	group_save.pressed.connect(_save_group)
	detail_column.add_child(group_save)

	var composition_title := Label.new()
	composition_title.text = "COMPOSITION"
	composition_title.add_theme_font_size_override("font_size", 12)
	detail_column.add_child(composition_title)
	group_composition = ItemList.new()
	group_composition.custom_minimum_size.y = 72
	group_composition.item_selected.connect(_on_composition_selected)
	detail_column.add_child(group_composition)
	var remove_row := HBoxContainer.new()
	detail_column.add_child(remove_row)
	group_remove_quantity = SpinBox.new()
	group_remove_quantity.prefix = "Remove "
	group_remove_quantity.min_value = 1
	group_remove_quantity.max_value = 100
	group_remove_quantity.value = 1
	group_remove_quantity.custom_minimum_size.x = 96
	remove_row.add_child(group_remove_quantity)
	group_remove_monster = Button.new()
	group_remove_monster.text = "Remove selected monster"
	group_remove_monster.disabled = true
	group_remove_monster.pressed.connect(_remove_group_monster)
	remove_row.add_child(group_remove_monster)


func _build_monsters_tab() -> void:
	var page := HSplitContainer.new()
	page.name = "Monsters"
	tabs.add_child(page)
	var list_column := VBoxContainer.new()
	list_column.custom_minimum_size.x = 300
	page.add_child(list_column)
	monster_filter = LineEdit.new()
	monster_filter.placeholder_text = "Filter type, name, tier, or configured…"
	monster_filter.text_changed.connect(func(_value: String) -> void: _rebuild_monsters())
	list_column.add_child(monster_filter)
	monster_updated_only = CheckBox.new()
	monster_updated_only.text = "Updated models only"
	monster_updated_only.tooltip_text = ("Hide creatures still wearing a stand-in "
		+ "model - the ones this list marks with a leading *. A creature loses the "
		+ "mark once the model it wears has been through review, so this is the "
		+ "list of what an invasion will actually look finished in.")
	monster_updated_only.toggled.connect(
		func(_pressed: bool) -> void: _rebuild_monsters())
	list_column.add_child(monster_updated_only)
	monster_list = ItemList.new()
	monster_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	monster_list.item_selected.connect(_on_monster_selected)
	list_column.add_child(monster_list)
	var detail_column := VBoxContainer.new()
	detail_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page.add_child(detail_column)
	monster_detail = RichTextLabel.new()
	monster_detail.bbcode_enabled = true
	monster_detail.size_flags_vertical = Control.SIZE_EXPAND_FILL
	monster_detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	monster_detail.text = "Select an invadable monster to inspect its strength."
	detail_column.add_child(monster_detail)
	var builder_title := Label.new()
	builder_title.text = "ADD TO LIVE SPAWN GROUP"
	builder_title.add_theme_font_size_override("font_size", 12)
	detail_column.add_child(builder_title)
	var builder_row := HBoxContainer.new()
	detail_column.add_child(builder_row)
	monster_quantity = SpinBox.new()
	monster_quantity.prefix = "Quantity "
	monster_quantity.min_value = 1
	monster_quantity.max_value = 100
	monster_quantity.value = 1
	monster_quantity.custom_minimum_size.x = 96
	monster_quantity.value_changed.connect(func(_value: float) -> void: _update_monster_actions())
	builder_row.add_child(monster_quantity)
	monster_group = OptionButton.new()
	monster_group.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	monster_group.item_selected.connect(func(_index: int) -> void: _update_monster_actions())
	builder_row.add_child(monster_group)
	monster_create_group = Button.new()
	monster_create_group.text = "Create group…"
	monster_create_group.tooltip_text = "Create a new live group, then add the selected monster"
	monster_create_group.pressed.connect(_show_create_group_for_monster)
	builder_row.add_child(monster_create_group)
	monster_add_to_group = Button.new()
	monster_add_to_group.text = "Add monster to group"
	monster_add_to_group.disabled = true
	monster_add_to_group.pressed.connect(_add_monster_to_group)
	detail_column.add_child(monster_add_to_group)
	monster_spawn_here = Button.new()
	monster_spawn_here.text = "Spawn X monsters at my location"
	monster_spawn_here.disabled = true
	monster_spawn_here.tooltip_text = "Create, activate, and track a quick group at your character's current server location"
	monster_spawn_here.pressed.connect(_spawn_monster_here)
	detail_column.add_child(monster_spawn_here)


func _build_create_dialog() -> void:
	create_dialog = ConfirmationDialog.new()
	create_dialog.title = "Create live spawn group"
	create_dialog.ok_button_text = "Create group"
	create_dialog.min_size = Vector2i(380, 180)
	create_dialog.confirmed.connect(_create_group_confirmed)
	add_child(create_dialog)
	var form := GridContainer.new()
	form.columns = 2
	form.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	form.offset_left = 18
	form.offset_top = 18
	form.offset_right = -18
	form.offset_bottom = -62
	create_dialog.add_child(form)
	_add_form_label(form, "Name")
	create_name = LineEdit.new()
	create_name.placeholder_text = "e.g. North Gate Wave"
	form.add_child(create_name)
	_add_form_label(form, "Map")
	create_map = OptionButton.new()
	form.add_child(create_map)
	_add_form_label(form, "Description")
	create_description = LineEdit.new()
	create_description.placeholder_text = "Optional operational note"
	form.add_child(create_description)


func _add_form_label(parent: Container, text: String) -> void:
	var label := Label.new()
	label.text = text
	parent.add_child(label)


func _update_summary() -> void:
	var totals: Dictionary = index_state.get("totals", {}) as Dictionary
	summary.text = "%d players  •  %d invaders  •  %d active groups" % [
		int(totals.get("players", 0)), int(totals.get("invasions", 0)),
		int(totals.get("active_groups", 0))]


func _rebuild_maps() -> void:
	if map_list == null:
		return
	map_list.clear()
	var query := map_filter.text.strip_edges().to_lower()
	var selected_index := -1
	for raw_map: Variant in index_state.get("maps", []):
		var map := raw_map as Dictionary
		var searchable := "%s %s %s" % [map.get("id", ""), map.get("name", ""), map.get("file", "")]
		if not query.is_empty() and not query in searchable.to_lower():
			continue
		var label := "%s  ·  %dP / %dI" % [str(map.get("name", map.get("id", "Map"))),
			int(map.get("players", 0)), int(map.get("invasions", 0))]
		if int(map.get("active_groups", 0)) > 0:
			label += " / %dG" % int(map.get("active_groups", 0))
		var item := map_list.add_item(label)
		map_list.set_item_metadata(item, map)
		map_list.set_item_tooltip(item, "%s\n%s" % [map.get("id", ""), map.get("file", "")])
		if str(map.get("id", "")) == selected_map_id:
			selected_index = item
	if selected_index >= 0:
		map_list.select(selected_index)
		map_list.ensure_current_is_visible()
	_populate_map_picker(group_map, str(selected_group.get("map_id", selected_map_id)))
	_populate_map_picker(create_map, selected_map_id)


func _on_map_selected(index: int) -> void:
	var map: Dictionary = map_list.get_item_metadata(index) as Dictionary
	selected_map_id = str(map.get("id", ""))
	teleport_button.disabled = true
	map_canvas.coordinates_supported = false
	map_status.text = "Refreshing live markers for %s…" % map.get("name", selected_map_id)
	command_requested.emit("#invasion_assistant map " + selected_map_id)


func _show_map_state() -> void:
	var map: Dictionary = map_state.get("map", {}) as Dictionary
	var bounds := _logical_bounds(str(map.get("id", "")))
	if not bounds.has_area() or not bool(map_state.get("coordinatesSupported", true)):
		teleport_button.disabled = true
		coordinate_x.editable = false
		coordinate_y.editable = false
		location_picker.disabled = true
		map_status.text = "Coordinates unavailable: this map has no verified bounds."
		map_canvas.set_map_state({"map": {"id": map.get("id", "")}, "coordinatesSupported": false})
		return
	var display_state: Dictionary = map_state.duplicate(true)
	display_state.map["serverTileMin"] = [bounds.position.x, bounds.position.y]
	display_state.map["width"] = bounds.size.x
	display_state.map["height"] = bounds.size.y
	var locations: Array = (display_state.get("locations", []) as Array).duplicate(true)
	for local: Dictionary in _local_landmarks(str(map.get("id", ""))):
		var duplicate := false
		for existing_raw: Variant in locations:
			var existing := existing_raw as Dictionary
			if str(existing.get("name", "")).to_lower() == str(local.get("name", "")).to_lower() \
					or Vector2i(int(existing.get("x", 0)), int(existing.get("y", 0))).distance_to(
						Vector2i(int(local.get("x", 0)), int(local.get("y", 0)))) < 3.0:
				duplicate = true
				break
		if not duplicate:
			locations.append(local)
	display_state["locations"] = locations
	map_title.text = "%s  —  %s" % [str(map.get("name", "Map")), str(map.get("id", ""))]
	coordinate_x.min_value = bounds.position.x
	coordinate_x.max_value = bounds.end.x - 1
	coordinate_y.min_value = bounds.position.y
	coordinate_y.max_value = bounds.end.y - 1
	coordinate_x.editable = true
	coordinate_y.editable = true
	location_picker.disabled = false
	teleport_button.disabled = false
	location_picker.clear()
	location_picker.add_item("Named locations…")
	location_picker.set_item_metadata(0, {})
	for raw_location: Variant in locations:
		var location := raw_location as Dictionary
		location_picker.add_item("%s  [%d, %d]" % [str(location.get("name", "Location")),
			int(location.get("x", 0)), int(location.get("y", 0))])
		location_picker.set_item_metadata(location_picker.item_count - 1, location)
	var map_id := str(map.get("id", ""))
	map_canvas.set_map_state(display_state, _map_texture(map_id), _map_projection(map_id))
	if not map_canvas.selected_tile is Vector2i:
		var players: Array = map_state.get("players", []) as Array
		if not players.is_empty():
			var player := players[0] as Dictionary
			coordinate_x.value = int(player.get("x", 0))
			coordinate_y.value = int(player.get("y", 0))
		else:
			coordinate_x.value = bounds.position.x + bounds.size.x / 2
			coordinate_y.value = bounds.position.y + bounds.size.y / 2
	_rebuild_roster()
	map_status.text = "%d named locations, %d players, %d invasion creatures. Live markers are server-authoritative." % [
		locations.size(),
		(map_state.get("players", []) as Array).size(),
		(map_state.get("creatures", []) as Array).size()]
	_rebuild_maps()


func _rebuild_roster() -> void:
	var lines: Array[String] = ["[b]LIVE PLAYERS[/b]"]
	var players: Array = map_state.get("players", []) as Array
	if players.is_empty():
		lines.append("[color=#8296a3]None[/color]")
	for raw_player: Variant in players:
		var player := raw_player as Dictionary
		lines.append("[color=#68e7ff]●[/color] %s  CL %d  [%d,%d]" % [
			player.get("name", "Player"), player.get("combat_level", 0),
			player.get("x", 0), player.get("y", 0)])
	lines.append("\n[b]INVASION CREATURES[/b]")
	var creatures: Array = map_state.get("creatures", []) as Array
	if creatures.is_empty():
		lines.append("[color=#8296a3]None[/color]")
	for raw_creature: Variant in creatures:
		var creature := raw_creature as Dictionary
		var marker := "[color=#ffc94f]◆[/color]" if bool(creature.get("boss", false)) else "[color=#ff6b63]◆[/color]"
		lines.append("%s %s\n   %s · %d/%d HP · [%d,%d]" % [marker,
			creature.get("name", "Invader"), creature.get("tier", "Unknown"),
			creature.get("health", 0), creature.get("max_health", 0),
			creature.get("x", 0), creature.get("y", 0)])
	map_roster.text = "\n".join(lines)


func _on_coordinate_selected(tile: Vector2i) -> void:
	if not _valid_logical_tile(selected_map_id, tile):
		return
	coordinate_x.value = tile.x
	coordinate_y.value = tile.y
	location_picker.select(0)
	location_picker.tooltip_text = ""
	map_status.text = "Selected %d, %d on %s." % [tile.x, tile.y, selected_map_id]


func _on_location_selected(index: int) -> void:
	var location: Dictionary = location_picker.get_item_metadata(index) as Dictionary
	# The closed picker trims a long name; hovering it reads the whole one.
	location_picker.tooltip_text = location_picker.get_item_text(index) if index > 0 else ""
	if location.is_empty():
		return
	if not _valid_logical_tile(selected_map_id, Vector2i(int(location.get("x", 0)), int(location.get("y", 0)))):
		return
	coordinate_x.value = int(location.get("x", 0))
	coordinate_y.value = int(location.get("y", 0))
	map_canvas.selected_tile = Vector2i(int(coordinate_x.value), int(coordinate_y.value))
	map_canvas.queue_redraw()


func _teleport() -> void:
	if selected_map_id.is_empty():
		return
	var x := int(coordinate_x.value)
	var y := int(coordinate_y.value)
	if teleport_button.disabled or not _valid_logical_tile(selected_map_id, Vector2i(x, y)):
		return
	status.text = "Teleporting to %s [%d, %d]…" % [selected_map_id, x, y]
	_map_refresh_elapsed = 0.0
	_index_refresh_elapsed = 0.0
	command_requested.emit("#invasion_assistant teleport %s %d %d" % [selected_map_id, x, y])


func _rebuild_groups() -> void:
	if group_list == null:
		return
	group_list.clear()
	var query := group_filter.text.strip_edges().to_lower()
	var selected_index := -1
	for raw_group: Variant in groups_state.get("groups", []):
		var group := raw_group as Dictionary
		var searchable := "%s %s %s %s %s" % [group.get("name", ""),
			group.get("description", ""), group.get("map_name", ""),
			" ".join(group.get("creatures", []) as Array),
			"active" if bool(group.get("active", false)) else "inactive"]
		if not query.is_empty() and not query in searchable.to_lower():
			continue
		var activity := "ACTIVE %d" % int(group.get("alive", 0)) if bool(group.get("active", false)) else "ready"
		var dynamic_marker := "LIVE · " if bool(group.get("dynamic", false)) else ""
		var item := group_list.add_item("%s%s  ·  %s  ·  %s" % [dynamic_marker,
			group.get("name", "Group"), group.get("map_name", "Map"), activity])
		group_list.set_item_metadata(item, group)
		if str(group.get("name", "")).to_lower() == str(selected_group.get("name", "")).to_lower() \
				or str(group.get("name", "")).to_lower() == _pending_created_group.to_lower():
			selected_index = item
	if selected_index >= 0:
		group_list.select(selected_index)
		_on_group_selected(selected_index)
		_pending_created_group = ""
	_rebuild_monster_group_picker()
	if selected_index >= 0 and _pending_add_to_created and not selected_monster.is_empty():
		_pending_add_to_created = false
		_add_monster_to_group()


func _on_group_selected(index: int) -> void:
	selected_group = (group_list.get_item_metadata(index) as Dictionary).duplicate(true)
	var dynamic := bool(selected_group.get("dynamic", false))
	group_open_map.disabled = str(selected_group.get("map_id", "")).is_empty()
	group_duplicate.disabled = false
	group_delete.disabled = not dynamic or bool(selected_group.get("active", false))
	group_spawn.disabled = bool(selected_group.get("active", false)) or int(selected_group.get("points", 0)) == 0
	group_clear.disabled = not bool(selected_group.get("active", false))
	group_save.disabled = not dynamic
	group_detail.text = ("[font_size=15][b]%s[/b][/font_size]  %s\n%s\n\n"
		+ "[b]Map[/b]  %s (%s)\n"
		+ "[b]Population[/b]  %d–%d across %d points\n"
		+ "[b]Current state[/b]  %s  ·  [b]Respawns[/b]  %s\n"
		+ "[b]Peak strength[/b]  %d  ·  [b]Health[/b] ×%.2f  ·  [b]Boss[/b] %s") % [
		selected_group.get("name", "Group"),
		("[color=#78dce8]LIVE BUILDER[/color]" if dynamic else "[color=#a9bdc9]CONFIGURED · READ-ONLY[/color]"),
		selected_group.get("description", ""),
		selected_group.get("map_name", ""), selected_group.get("map_id", ""),
		selected_group.get("minimum", 0), selected_group.get("maximum", 0),
		selected_group.get("points", 0),
		_active_summary(selected_group),
		_respawn_summary(selected_group),
		selected_group.get("strength", 0),
		float(selected_group.get("health_multiplier", 1.0)),
		selected_group.get("boss", "None") if not str(selected_group.get("boss", "")).is_empty() else "None"]
	group_name.text = str(selected_group.get("name", ""))
	group_description.text = str(selected_group.get("description", ""))
	_populate_map_picker(group_map, str(selected_group.get("map_id", "")))
	group_minimum.value = int(selected_group.get("minimum", 0))
	group_maximum.value = int(selected_group.get("maximum", 0))
	group_health.value = float(selected_group.get("health_multiplier", 1.0))
	group_boss_type.text = str(selected_group.get("boss_type", ""))
	group_boss_name.text = str(selected_group.get("boss_name", ""))
	group_name.editable = dynamic
	group_description.editable = dynamic
	group_map.disabled = not dynamic
	group_minimum.editable = dynamic
	group_maximum.editable = dynamic
	group_health.editable = dynamic
	group_boss_type.editable = dynamic
	group_boss_name.editable = dynamic
	group_composition.clear()
	for raw_entry: Variant in selected_group.get("composition", []):
		var entry := raw_entry as Dictionary
		var item := group_composition.add_item("%s  × %d" % [
			entry.get("name", entry.get("type", "Monster")), entry.get("quantity", 0)])
		group_composition.set_item_metadata(item, entry)
	group_remove_monster.disabled = true


## The server keeps a respawn window rather than an interval: a wiped group
## comes back until the window shuts. Groups the assistant builds ship with it
## already shut, so this line exists to say which of the three a group is
## before an invasion master activates it in front of players.
func _respawn_summary(group: Dictionary) -> String:
	var minutes := int(group.get("auto_respawn_minutes", 0))
	if minutes < 0:
		return "none — spawns once"
	if minutes == 0:
		return "every wipe, while active"
	return "every wipe for %d min" % minutes


func _active_summary(group: Dictionary) -> String:
	if not bool(group.get("active", false)):
		return "Ready"
	var result := "ACTIVE — %d alive" % int(group.get("alive", 0))
	if int(group.get("queued", 0)) > 0:
		result += " · %d queued" % int(group["queued"])
	return result


func _open_group_map() -> void:
	selected_map_id = str(selected_group.get("map_id", ""))
	teleport_button.disabled = true
	map_canvas.coordinates_supported = false
	tabs.current_tab = 0
	command_requested.emit("#invasion_assistant map " + selected_map_id)


func _show_create_group() -> void:
	_pending_add_to_created = false
	_open_create_dialog()


func _show_create_group_for_monster() -> void:
	_pending_add_to_created = not selected_monster.is_empty()
	_open_create_dialog()


func _open_create_dialog() -> void:
	_populate_map_picker(create_map, selected_map_id)
	create_name.text = ""
	create_description.text = ""
	create_dialog.popup_centered()
	create_name.grab_focus()


func _create_group_confirmed() -> void:
	var name := _clean_field(create_name.text)
	if name.is_empty() or create_map.selected < 0:
		status.text = "A live spawn group needs a name and map."
		_pending_add_to_created = false
		return
	var map_id := str(create_map.get_item_metadata(create_map.selected))
	_pending_created_group = name
	command_requested.emit("#invasion_assistant group create %s|%s|%s" % [
		name, map_id, _clean_field(create_description.text)])
	status.text = "Creating live spawn group %s…" % name


func _duplicate_group() -> void:
	if selected_group.is_empty():
		return
	var base := str(selected_group.get("name", "Group")) + " Copy"
	var candidate := base
	var suffix := 2
	while _group_name_exists(candidate):
		candidate = "%s %d" % [base, suffix]
		suffix += 1
	_pending_created_group = candidate
	command_requested.emit("#invasion_assistant group duplicate %s|%s" % [
		_clean_field(str(selected_group.get("name", ""))), _clean_field(candidate)])
	status.text = "Duplicating group as %s…" % candidate


func _delete_group() -> void:
	if selected_group.is_empty() or not bool(selected_group.get("dynamic", false)):
		return
	command_requested.emit("#invasion_assistant group delete "
		+ _clean_field(str(selected_group.get("name", ""))))
	status.text = "Deleting live spawn group…"


func _save_group() -> void:
	if selected_group.is_empty() or not bool(selected_group.get("dynamic", false)) \
			or group_map.selected < 0:
		return
	var old_name := _clean_field(str(selected_group.get("name", "")))
	var new_name := _clean_field(group_name.text)
	_pending_created_group = new_name
	var fields: Array[String] = [old_name, new_name,
		_clean_field(group_description.text),
		str(group_map.get_item_metadata(group_map.selected)),
		str(int(group_minimum.value)), str(int(group_maximum.value)),
		str(group_health.value), _clean_field(group_boss_type.text),
		_clean_field(group_boss_name.text)]
	command_requested.emit("#invasion_assistant group update " + "|".join(fields))
	status.text = "Saving %s…" % new_name


func _spawn_group() -> void:
	if selected_group.is_empty():
		return
	command_requested.emit("#invasion_assistant group activate "
		+ _clean_field(str(selected_group.get("name", ""))))
	status.text = "Spawning %s…" % selected_group.get("name", "group")


func _clear_group() -> void:
	if selected_group.is_empty():
		return
	command_requested.emit("#invasion_assistant group clear "
		+ _clean_field(str(selected_group.get("name", ""))))
	status.text = "Clearing %s…" % selected_group.get("name", "group")


func _on_composition_selected(_index: int) -> void:
	group_remove_monster.disabled = not bool(selected_group.get("dynamic", false))


func _remove_group_monster() -> void:
	var selected := group_composition.get_selected_items()
	if selected.is_empty() or selected_group.is_empty():
		return
	var entry := group_composition.get_item_metadata(selected[0]) as Dictionary
	command_requested.emit("#invasion_assistant group remove %s|%s|%d" % [
		_clean_field(str(selected_group.get("name", ""))),
		entry.get("type", ""), int(group_remove_quantity.value)])
	status.text = "Updating group composition…"


func _rebuild_monsters() -> void:
	if monster_list == null:
		return
	monster_list.clear()
	var query := monster_filter.text.strip_edges().to_lower()
	var updated_only := (monster_updated_only != null
		and monster_updated_only.button_pressed)
	for raw_monster: Variant in monsters_state.get("monsters", []):
		var monster := raw_monster as Dictionary
		if updated_only and has_placeholder_model(monster):
			continue
		var searchable := "%s %s %s %s %s" % [monster.get("type", ""),
			monster.get("name", ""), monster.get("tier", ""),
			"configured" if bool(monster.get("configured", false)) else "available",
			"placeholder model" if has_placeholder_model(monster) else "updated model"]
		if not query.is_empty() and not query in searchable.to_lower():
			continue
		var configured := "★ " if bool(monster.get("configured", false)) else ""
		var item := monster_list.add_item("%s%s  ·  %-10s  ·  rating %d" % [
			configured, monster.get("name", "Monster"), monster.get("tier", "Unknown"),
			monster.get("rating", 0)])
		monster_list.set_item_metadata(item, monster)


## Whether a creature is still wearing a stand-in model rather than one that
## has been through review. The server states it outright and also marks the
## name with a leading asterisk; the name is read as a fallback so the filter
## still works against a server that sends only the mark.
func has_placeholder_model(monster: Dictionary) -> bool:
	if monster.has("placeholder_model"):
		return bool(monster.get("placeholder_model", false))
	return str(monster.get("name", "")).begins_with("*")


func _on_monster_selected(index: int) -> void:
	selected_monster = (monster_list.get_item_metadata(index) as Dictionary).duplicate(true)
	monster_detail.text = ("[font_size=15][b]%s[/b][/font_size]\n[color=#9fc0d4]%s[/color]\n\n"
		+ "[b]General strength[/b]  %s (rating %d)\n"
		+ "[b]Combat level[/b]  %d\n[b]Native level[/b]  %d\n"
		+ "[b]Health / Ether[/b]  %d / %d\n"
		+ "[b]Attack / Defense[/b]  %d / %d\n"
		+ "[b]Damage[/b]  %d–%d\n[b]Armor[/b]  %d–%d\n\n"
		+ "%s") % [selected_monster.get("name", "Monster"),
		selected_monster.get("type", ""), selected_monster.get("tier", "Unknown"),
		selected_monster.get("rating", 0), selected_monster.get("combat_level", 0),
		selected_monster.get("level", 0), selected_monster.get("health", 0),
		selected_monster.get("ether", 0), selected_monster.get("attack", 0),
		selected_monster.get("defense", 0), selected_monster.get("damage_min", 0),
		selected_monster.get("damage_max", 0), selected_monster.get("armor_min", 0),
		selected_monster.get("armor_max", 0),
		("[color=#ffd36a]★ Used by a configured invasion spawn group[/color]"
		if bool(selected_monster.get("configured", false)) else
		"Available for ad-hoc invasion spawning")]
	_update_monster_actions()


func _rebuild_monster_group_picker() -> void:
	if monster_group == null:
		return
	var preferred := str(selected_group.get("name", ""))
	monster_group.clear()
	for raw_group: Variant in groups_state.get("groups", []):
		var group := raw_group as Dictionary
		if not bool(group.get("dynamic", false)):
			continue
		monster_group.add_item("%s — %s" % [group.get("name", "Group"),
			group.get("map_name", "Map")])
		monster_group.set_item_metadata(monster_group.item_count - 1, group)
		if str(group.get("name", "")).to_lower() == preferred.to_lower():
			monster_group.select(monster_group.item_count - 1)
	_update_monster_actions()


func _update_monster_actions() -> void:
	if monster_add_to_group == null:
		return
	var has_monster := not selected_monster.is_empty()
	monster_add_to_group.disabled = not has_monster or monster_group.item_count == 0
	monster_spawn_here.disabled = not has_monster
	if has_monster and monster_group.item_count > 0:
		var group := monster_group.get_item_metadata(monster_group.selected) as Dictionary
		monster_add_to_group.text = "Add %d %s to %s" % [int(monster_quantity.value),
			selected_monster.get("name", "monster"), group.get("name", "group")]
	else:
		monster_add_to_group.text = "Add monster to group"
	monster_spawn_here.text = "Spawn %d %s at my location" % [int(monster_quantity.value),
		selected_monster.get("name", "monsters") if has_monster else "monsters"]


func _add_monster_to_group() -> void:
	if selected_monster.is_empty() or monster_group.item_count == 0:
		return
	var group := monster_group.get_item_metadata(monster_group.selected) as Dictionary
	var location: Variant = _spawn_location_for_group(group)
	if not location is Vector2i:
		status.text = "Coordinates unavailable: this map has no verified spawn location."
		return
	command_requested.emit("#invasion_assistant group add %s|%s|%d|%d|%d" % [
		_clean_field(str(group.get("name", ""))), selected_monster.get("type", ""),
		int(monster_quantity.value), location.x, location.y])
	status.text = "Adding %d %s to %s at [%d, %d]…" % [int(monster_quantity.value),
		selected_monster.get("name", "monster"), group.get("name", "group"),
		location.x, location.y]


func _spawn_monster_here() -> void:
	if selected_monster.is_empty():
		return
	command_requested.emit("#invasion_assistant monster spawn %s|%d" % [
		selected_monster.get("type", ""), int(monster_quantity.value)])
	status.text = "Spawning %d %s at your live server location…" % [
		int(monster_quantity.value), selected_monster.get("name", "monster")]


func _spawn_location_for_group(group: Dictionary) -> Variant:
	if group.has("coordinatesSupported") and (not group.coordinatesSupported is bool or not group.coordinatesSupported):
		return null
	var map_id := str(group.get("map_id", ""))
	if map_id == selected_map_id and map_canvas.selected_tile is Vector2i:
		var tile := Vector2i(int(coordinate_x.value), int(coordinate_y.value))
		return tile if _valid_logical_tile(map_id, tile) else null
	var locations: Array = group.get("locations", []) as Array
	if not locations.is_empty():
		var first := locations[0] as Dictionary
		var tile := Vector2i(int(first.get("x", 0)), int(first.get("y", 0)))
		return tile if _valid_logical_tile(map_id, tile) else null
	if map_id == selected_map_id:
		var tile := Vector2i(int(coordinate_x.value), int(coordinate_y.value))
		return tile if _valid_logical_tile(map_id, tile) else null
	return Vector2i.ZERO if _valid_logical_tile(map_id, Vector2i.ZERO) else null

func _logical_bounds(map_id: String) -> Rect2i:
	var map: Dictionary = map_state.get("map", {})
	if str(map.get("id", "")) != map_id:
		map = {}
		for row: Dictionary in index_state.get("maps", []):
			if str(row.get("id", "")) == map_id:
				map = row
				break
	if coordinate_context != null and coordinate_context.selected:
		var bounds: Dictionary = coordinate_context.admin_bounds(map if not map.is_empty() else {"id": map_id})
		if not bounds.ok:
			return Rect2i()
		return Rect2i(Vector2i(bounds.minimum[0], bounds.minimum[1]), Vector2i(bounds.cells[0], bounds.cells[1]))
	# Existing legacy zero-based snapshots remain supported; an explicit
	# nonzero minimum is never silently admitted without the verified catalog.
	if map.is_empty() or map.get("serverTileMin", [0, 0]) != [0, 0]:
		return Rect2i()
	return Rect2i(0, 0, int(map.get("width", 2048)), int(map.get("height", 2048)))

func _valid_logical_tile(map_id: String, tile: Vector2i) -> bool:
	if str(map_state.get("map", {}).get("id", "")) == map_id and not bool(map_state.get("coordinatesSupported", true)):
		return false
	var bounds := _logical_bounds(map_id)
	return bounds.has_area() and bounds.has_point(tile)


func _on_tab_changed(tab: int) -> void:
	if tab == 1 and groups_state.is_empty():
		status.text = "Loading invasion spawn groups…"
		command_requested.emit("#invasion_assistant groups")
	elif tab == 2 and monsters_state.is_empty():
		status.text = "Loading invadable monsters…"
		command_requested.emit("#invasion_assistant monsters")


func _refresh_current() -> void:
	command_requested.emit("#invasion_assistant refresh")
	match tabs.current_tab:
		0:
			if not selected_map_id.is_empty():
				command_requested.emit("#invasion_assistant map " + selected_map_id)
		1:
			command_requested.emit("#invasion_assistant groups")
		2:
			command_requested.emit("#invasion_assistant monsters")
	status.text = "Refreshing server-authoritative data…"
	_map_refresh_elapsed = 0.0
	_index_refresh_elapsed = 0.0


func _populate_map_picker(picker: OptionButton, preferred: String) -> void:
	if picker == null:
		return
	picker.clear()
	for raw_map: Variant in index_state.get("maps", []):
		var map := raw_map as Dictionary
		var map_id := str(map.get("id", ""))
		picker.add_item(str(map.get("name", map_id)))
		picker.set_item_metadata(picker.item_count - 1, map_id)
		if map_id == preferred:
			picker.select(picker.item_count - 1)


func _group_name_exists(name: String) -> bool:
	for raw_group: Variant in groups_state.get("groups", []):
		if str((raw_group as Dictionary).get("name", "")).to_lower() == name.to_lower():
			return true
	return false


func _clean_field(value: String) -> String:
	return value.replace("|", "/").strip_edges()


func _map_projection(map_id: String) -> Dictionary:
	var entry: Dictionary = MapRegistry.resolve(map_registry, map_id)
	var path := str(entry.get("manifest", ""))
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var manifest: Variant = JSON.parse_string(file.get_as_text())
	if not manifest is Dictionary:
		return {}
	return {"minimap": manifest.get("minimap", {}),
		"coordinateTransform": entry.get("coordinateTransform",
			manifest.get("coordinateTransform", {}))}


func _map_texture(map_id: String) -> Texture2D:
	if _texture_cache.has(map_id):
		return _texture_cache[map_id] as Texture2D
	if map_registry.is_empty():
		return null
	var entry: Dictionary = MapRegistry.resolve(map_registry, map_id)
	var manifest_path := str(entry.get("manifest", ""))
	if manifest_path.is_empty():
		return null
	var minimap_file := "minimap.webp"
	if FileAccess.file_exists(manifest_path):
		var manifest_file := FileAccess.open(manifest_path, FileAccess.READ)
		if manifest_file != null:
			var parsed: Variant = JSON.parse_string(manifest_file.get_as_text())
			if parsed is Dictionary:
				var minimap: Variant = (parsed as Dictionary).get("minimap", {})
				if minimap is Dictionary:
					minimap_file = str((minimap as Dictionary).get("image", minimap_file))
	var minimap_path := manifest_path.get_base_dir().path_join(minimap_file)
	var texture: Texture2D = null
	if ResourceLoader.exists(minimap_path):
		texture = load(minimap_path) as Texture2D
	if texture == null:
		var image := Image.new()
		if image.load(ProjectSettings.globalize_path(minimap_path)) == OK:
			texture = ImageTexture.create_from_image(image)
	if texture != null:
		_texture_cache[map_id] = texture
	return texture


func _local_landmarks(map_id: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if map_registry.is_empty():
		return result
	var entry: Dictionary = MapRegistry.resolve(map_registry, map_id)
	var manifest_path := str(entry.get("manifest", ""))
	if manifest_path.is_empty() or not FileAccess.file_exists(manifest_path):
		return result
	var file := FileAccess.open(manifest_path, FileAccess.READ)
	if file == null:
		return result
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return result
	var manifest := parsed as Dictionary
	var transform: Dictionary = entry.get("coordinateTransform",
		manifest.get("coordinateTransform", {})) as Dictionary
	var adapter := CoordinateAdapter.new(transform)
	var seen: Dictionary = {}
	for section: String in ["landmarks", "pointsOfInterest", "spawnPoints"]:
		var raw_entries: Variant = manifest.get(section, [])
		if not raw_entries is Array:
			continue
		for raw_landmark: Variant in raw_entries as Array:
			if not raw_landmark is Dictionary:
				continue
			var landmark := raw_landmark as Dictionary
			var tile: Variant = null
			var server_tile: Variant = landmark.get("serverTile", [])
			if server_tile is Array and (server_tile as Array).size() >= 2:
				tile = Vector2i(int(server_tile[0]), int(server_tile[1]))
			else:
				var raw_position: Variant = landmark.get("position", [])
				if raw_position is Array and (raw_position as Array).size() >= 3:
					tile = adapter.godot_to_server(Vector3(
						float(raw_position[0]), float(raw_position[1]), float(raw_position[2])))
			if not tile is Vector2i:
				continue
			var name := str(landmark.get("name", landmark.get("id",
				landmark.get("kind", "Landmark")))).replace("_", " ").capitalize()
			var key := "%s:%d:%d" % [name, tile.x, tile.y]
			if seen.has(key):
				continue
			seen[key] = true
			result.append({"name": name, "kind": "landmark", "x": tile.x,
				"y": tile.y, "source": "client_map"})
	return result
