class_name InvasionAssistantWindow
extends Window

signal command_requested(command: String)

const MapCanvasScript := preload("res://src/ui/invasion_map_canvas.gd")
const MAP_REFRESH_SECONDS := 5.0
const INDEX_REFRESH_SECONDS := 15.0
const VIEWPORT_MARGIN := Vector2i(32, 32)
const PREFERENCE_KEY := "invasion_assistant"
const MONITOR_PREFERENCE_KEY := "invasion_assistant_monitor"
const MONITOR_SIZE := Vector2i(390, 620)
## Frame sizing is independent of typography. Small viewports collapse the
## map sidebar instead of scaling every label and pointer target down.
const CONTENT_SIZE := Vector2i(1100, 620)
const MIN_SCALE := 0.65
const MAX_SCALE := 1.75
const COMPACT_FONT_SIZE := 14
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
var monster_miniboss: CheckBox
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
var monitor_mode := false
var monitor_docked := true
var monitor_preferences_path := WindowPreferences.SETTINGS_PATH
var monitor_dock_button: Button
var monitor_header: HBoxContainer
var _monitor_dock_bounds: Callable
var _floating_monitor_position := Vector2i.ZERO
var _has_floating_monitor_position := false
var _monitor_dragging := false
var _monitor_drag_offset := Vector2i.ZERO
var workspace: HBoxContainer
var workspace_scroll: ScrollContainer
var monitor_scroll: ScrollContainer
var inspector: VBoxContainer
var inspector_tabs: TabContainer
var map_sidebar: VBoxContainer
var map_selector: OptionButton
var map_tool: OptionButton
var mode_button: Button
var freshness: Label
var group_picker: OptionButton
var composition_total: Label
var settings_column: VBoxContainer
var monitor_panel: VBoxContainer
var monitor_canvas
var monitor_map: OptionButton
var monitor_groups: ItemList
var monitor_detail: Label
var monitor_location: OptionButton
var monitor_x: SpinBox
var monitor_y: SpinBox
var monitor_move: Button
var monitor_clear: Button
var anchor_enabled: CheckBox
var anchor_x: SpinBox
var anchor_y: SpinBox
var anchor_radius: SpinBox
var region_enabled: CheckBox
var region_x0: SpinBox
var region_y0: SpinBox
var region_x1: SpinBox
var region_y1: SpinBox
var movement_save: Button
var move_anchor_button: Button
var action_dialog: ConfirmationDialog
var _pending_action: Dictionary = {}
var _loading_group := false
var _draft_dirty := false
var _movement_dirty := false
var _drafts: Dictionary = {}
var _last_map_update := 0
var _last_groups_update := 0
var _groups_refresh_elapsed := 0.0
var _tab_maps: Dictionary = {}
var _setting_coordinates := false


func _ready() -> void:
	title = "Invasion Assistant"
	# The corner grip controls the frame and sidebar breakpoint together.
	# Typography stays at its readable logical size in both operating modes.
	unresizable = true
	_preferred_scale = WindowPreferences.stored_scale(PREFERENCE_KEY, 1.0,
		MIN_SCALE, MAX_SCALE)
	var monitor_options := WindowPreferences.stored_options(MONITOR_PREFERENCE_KEY,
		{}, monitor_preferences_path)
	monitor_docked = bool(monitor_options.get("docked", true))
	_has_floating_monitor_position = bool(monitor_options.get("has_floating_position", false))
	_floating_monitor_position = Vector2i(WindowPreferences.stored_rect(
		MONITOR_PREFERENCE_KEY, Rect2(Vector2.ZERO, Vector2(MONITOR_SIZE)),
		monitor_preferences_path).position)
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
	if not visible or tabs == null or selected_map_id.is_empty():
		return
	_update_freshness()
	_groups_refresh_elapsed += delta
	if _groups_refresh_elapsed >= MAP_REFRESH_SECONDS:
		_groups_refresh_elapsed = 0.0
		command_requested.emit("#invasion_assistant groups")
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
	if monitor_mode:
		return
	var viewport_size := get_tree().root.size
	position = Vector2i(maxi(0, (viewport_size.x - size.x) / 2),
		maxi(0, (viewport_size.y - size.y) / 2))
	_keep_on_screen()


## The compatibility scale setting controls frame size, never text size.
func _apply_window_scale(requested: float) -> void:
	var available := _available_size()
	_window_scale = clampf(requested, MIN_SCALE, MAX_SCALE)
	content_scale_factor = 1.0
	if monitor_mode:
		_layout_monitor()
	else:
		size = Vector2i(mini(available.x, maxi(730, roundi(CONTENT_SIZE.x * _window_scale))),
			mini(available.y, maxi(570, roundi(CONTENT_SIZE.y * _window_scale))))
	if map_sidebar != null:
		map_sidebar.visible = size.x >= 1000


## Applies a scale the player asked for from the corner grip, and records it
## as the new preference.
func resize_to_scale(requested: float) -> void:
	_apply_window_scale(requested)
	_preferred_scale = _window_scale
	_size_save_countdown = SIZE_SAVE_DELAY
	_keep_on_screen()


func _keep_on_screen() -> void:
	if monitor_mode:
		_layout_monitor()
		return
	var viewport_size := get_tree().root.size
	position = Vector2i(
		clampi(position.x, 0, maxi(0, viewport_size.x - size.x - int(WindowDrag.RESERVED_RIGHT_RAIL))),
		clampi(position.y, 0, maxi(0, viewport_size.y - size.y - int(WindowDrag.RESERVED_BOTTOM_BAR))))


## The game supplies the actual drawable area, shared with the player Tab map.
## Reading it while visible also follows later HUD size and scale changes.
func configure_monitor_dock(bounds: Callable) -> void:
	_monitor_dock_bounds = bounds
	if monitor_mode:
		_layout_monitor()


func _monitor_area() -> Rect2i:
	# Embedded windows and HUD controls share logical viewport coordinates.
	# Root Window.size is physical pixels when the game applies HUD scaling.
	var screen := get_tree().root.get_visible_rect()
	if _monitor_dock_bounds.is_valid():
		var value: Variant = _monitor_dock_bounds.call()
		if value is Rect2:
			var area: Rect2 = value
			if area.position.is_finite() and area.size.is_finite() and area.has_area():
				area = area.intersection(screen)
				if area.has_area():
					return Rect2i(area)
	return Rect2i(Vector2i.ZERO, Vector2i(
		maxi(1, int(screen.size.x) - int(WindowDrag.RESERVED_RIGHT_RAIL)),
		maxi(1, int(screen.size.y) - int(WindowDrag.RESERVED_BOTTOM_BAR))))


func _layout_monitor() -> void:
	var area := _monitor_area()
	size = Vector2i(mini(MONITOR_SIZE.x, area.size.x),
		area.size.y if monitor_docked else mini(MONITOR_SIZE.y, area.size.y))
	if monitor_docked:
		position = Vector2i(area.end.x - size.x, area.position.y)
	else:
		position = Vector2i(
			clampi(_floating_monitor_position.x, area.position.x, area.end.x - size.x),
			clampi(_floating_monitor_position.y, area.position.y, area.end.y - size.y))


func set_monitor_docked(docked: bool) -> void:
	if monitor_docked == docked:
		return
	_monitor_dragging = false
	if not docked and not _has_floating_monitor_position:
		_floating_monitor_position = position + Vector2i(-24, 24)
		_has_floating_monitor_position = true
	monitor_docked = docked
	_update_monitor_dock_controls()
	if monitor_mode:
		_layout_monitor()
	_save_monitor_layout()


func _update_monitor_dock_controls() -> void:
	monitor_dock_button.visible = monitor_mode
	monitor_dock_button.text = "Undock" if monitor_docked else "Dock right"
	monitor_dock_button.tooltip_text = ("Detach monitor; drag its title to move it"
		if monitor_docked else "Attach monitor to the right edge of the 3D view")
	monitor_header.mouse_default_cursor_shape = (Control.CURSOR_MOVE
		if monitor_mode and not monitor_docked else Control.CURSOR_ARROW)
	monitor_header.tooltip_text = "Drag to move monitor" if monitor_mode and not monitor_docked else ""


func _save_monitor_layout() -> void:
	WindowPreferences.store_layout(MONITOR_PREFERENCE_KEY,
		Rect2(Vector2(_floating_monitor_position), Vector2(MONITOR_SIZE)), false,
		monitor_preferences_path, {"docked": monitor_docked,
			"has_floating_position": _has_floating_monitor_position})


func _on_monitor_header_gui_input(event: InputEvent) -> void:
	if not monitor_mode or monitor_docked:
		return
	if event is InputEventMouseButton:
		var mouse := event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return
		_monitor_dragging = mouse.pressed
		if mouse.pressed:
			_monitor_drag_offset = _pointer_position() - position
		else:
			_save_monitor_layout()
		monitor_header.accept_event()
	elif event is InputEventMouseMotion and _monitor_dragging:
		_drag_monitor_to(_pointer_position())
		monitor_header.accept_event()


func _drag_monitor_to(pointer: Vector2i) -> void:
	_floating_monitor_position = pointer - _monitor_drag_offset
	_has_floating_monitor_position = true
	_layout_monitor()
	_floating_monitor_position = position


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
	else:
		if _monitor_dragging:
			_monitor_dragging = false
			_save_monitor_layout()
		if _size_save_countdown > 0.0:
			# Closing the window must not lose a resize that was still settling.
			_flush_size_preference()


func configure_registry(value: Dictionary) -> void:
	map_registry = value
	# Standalone previews get the same published tab-map sources as the game.
	var regions: Array = _read_json("res://data/maps/cartography.json").get("regions", [])
	regions.append_array(_read_json("res://data/maps/cartography-continent-v2.json").get("regions", []))
	configure_cartography(regions)


func _read_json(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(file.get_as_text()) if file != null else null
	return parsed if parsed is Dictionary else {}


func configure_cartography(regions: Array) -> void:
	_tab_maps.clear()
	_texture_cache.clear()
	var details: Dictionary = _read_json("res://data/maps/map-details.json").get("regions", {})
	for region: Dictionary in regions:
		var key := str(region.get("serverMap", ""))
		var tab_map: Dictionary = (region.get("tabMap", {}) as Dictionary).duplicate(true)
		var detail: Dictionary = details.get(key, {}) as Dictionary
		if not detail.is_empty() and detail.get("worldMin") == tab_map.get("worldMin") and detail.get("worldMax") == tab_map.get("worldMax"):
			tab_map["detail"] = detail
		_tab_maps[key] = tab_map


func set_monitor_mode(enabled: bool) -> void:
	if _monitor_dragging:
		_monitor_dragging = false
		_save_monitor_layout()
	monitor_mode = enabled
	# Monitor uses its own title/drag handle so it can join the HUD seamlessly.
	borderless = enabled
	workspace.visible = not enabled
	workspace_scroll.visible = not enabled
	monitor_panel.visible = enabled
	monitor_scroll.visible = enabled
	god_storage_button.visible = not enabled
	mode_button.text = "Full builder" if enabled else "Monitor view"
	resize_grip.visible = not enabled
	_update_monitor_dock_controls()
	map_tool.select(0)
	map_canvas.selection_mode = 0
	_fit_to_viewport()
	_sync_group_views()


func _update_freshness() -> void:
	var now := Time.get_ticks_msec()
	var map_age := "%ds" % ((now - _last_map_update) / 1000) if _last_map_update else "waiting"
	var group_age := "%ds" % ((now - _last_groups_update) / 1000) if _last_groups_update else "waiting"
	freshness.text = "Map: %s · Groups: %s%s" % [map_age, group_age, " · Unsaved changes" if _draft_dirty or _movement_dirty else ""]


func _select_map(map_id: String) -> void:
	if map_id.is_empty():
		return
	selected_map_id = map_id
	teleport_button.disabled = true
	map_canvas.coordinates_supported = false
	monitor_canvas.coordinates_supported = false
	_sync_group_views()
	command_requested.emit("#invasion_assistant map " + map_id)


func _select_group_name(name: String) -> void:
	for index: int in range(group_list.item_count):
		if str(group_list.get_item_metadata(index).get("name", "")) == name:
			group_list.select(index)
			_on_group_selected(index)
			if monitor_mode and str(selected_group.get("map_id", "")) != selected_map_id:
				_open_group_map()
			return
	if not group_filter.text.is_empty():
		group_filter.clear()
		_rebuild_groups()
		_select_group_name(name)


func _capture_settings() -> Dictionary:
	return {"name": group_name.text, "description": group_description.text,
		"map_id": str(group_map.get_item_metadata(group_map.selected)) if group_map.selected >= 0 else "",
		"minimum": int(group_minimum.value), "maximum": int(group_maximum.value),
		"health_multiplier": group_health.value, "boss_type": group_boss_type.text, "boss_name": group_boss_name.text}


func _mark_draft() -> void:
	if _loading_group or selected_group.is_empty():
		return
	_draft_dirty = true
	_stash_draft()


func _discard_draft() -> void:
	_drafts.erase(str(selected_group.get("name", "")))
	_draft_dirty = false
	_movement_dirty = false
	for index: int in range(group_list.item_count):
		if str(group_list.get_item_metadata(index).get("name", "")) == str(selected_group.get("name", "")):
			_on_group_selected(index)
			return


func _mark_movement() -> void:
	if _loading_group or selected_group.is_empty():
		return
	_movement_dirty = true
	_stash_draft()
	_preview_movement()


func _stash_draft() -> void:
	if _loading_group or selected_group.is_empty() or not (_draft_dirty or _movement_dirty):
		return
	_drafts[str(selected_group.get("name", ""))] = {"settings": _capture_settings(), "settings_dirty": _draft_dirty,
		"movement": _movement_from_controls(), "movement_dirty": _movement_dirty}


func _restore_draft(preserve_fields: bool = false, preserve_movement: bool = false) -> void:
	_draft_dirty = false
	_movement_dirty = false
	var key := str(selected_group.get("name", ""))
	var saved: Dictionary = _drafts.get(key, {})
	if saved.is_empty():
		return
	var fields: Dictionary = saved.settings
	for field_name: String in fields:
		if fields[field_name] != selected_group.get(field_name, ""):
			_draft_dirty = bool(saved.settings_dirty)
	if _draft_dirty and not preserve_fields:
		group_name.text = str(fields.name)
		group_description.text = str(fields.description)
		_populate_map_picker(group_map, str(fields.map_id))
		group_minimum.value = fields.minimum
		group_maximum.value = fields.maximum
		group_health.value = fields.health_multiplier
		group_boss_type.text = str(fields.boss_type)
		group_boss_name.text = str(fields.boss_name)
	_movement_dirty = bool(saved.movement_dirty) and saved.movement != selected_group.get("movement", {})
	if _movement_dirty and not preserve_movement:
		_load_movement(saved.movement)
	if not _draft_dirty and not _movement_dirty:
		_drafts.erase(key)


func _movement_from_controls() -> Dictionary:
	return {"anchor": {"x": int(anchor_x.value), "y": int(anchor_y.value)} if anchor_enabled.button_pressed else null,
		"radius": int(anchor_radius.value),
		"region": {"x0": int(region_x0.value), "y0": int(region_y0.value), "x1": int(region_x1.value), "y1": int(region_y1.value)} if region_enabled.button_pressed else null}


func _load_movement(value: Dictionary) -> void:
	var anchor: Variant = value.get("anchor")
	var region: Variant = value.get("region")
	anchor_enabled.button_pressed = anchor is Dictionary
	anchor_x.value = int(anchor.get("x", 0)) if anchor is Dictionary else 0
	anchor_y.value = int(anchor.get("y", 0)) if anchor is Dictionary else 0
	anchor_radius.value = int(value.get("radius", 18))
	region_enabled.button_pressed = region is Dictionary
	region_x0.value = int(region.get("x0", 0)) if region is Dictionary else 0
	region_y0.value = int(region.get("y0", 0)) if region is Dictionary else 0
	region_x1.value = int(region.get("x1", 0)) if region is Dictionary else 0
	region_y1.value = int(region.get("y1", 0)) if region is Dictionary else 0


func _preview_movement() -> void:
	var same_map := str(selected_group.get("map_id", "")) == selected_map_id
	var movement := _movement_from_controls() if same_map else {}
	map_canvas.set_movement(movement)
	monitor_canvas.set_movement(selected_group.get("movement", {}) if same_map else {})


func _sync_group_views() -> void:
	var present := not selected_group.is_empty()
	var active := bool(selected_group.get("active", false))
	var supported := bool(selected_group.get("coordinatesSupported", true))
	movement_save.disabled = not present or not supported or (not active and not bool(selected_group.get("dynamic", false)))
	var same_map := present and str(selected_group.get("map_id", "")) == selected_map_id
	move_anchor_button.disabled = movement_save.disabled or not same_map or not map_canvas.coordinates_supported
	monitor_move.disabled = movement_save.disabled or not same_map or not monitor_canvas.coordinates_supported
	monitor_clear.disabled = not active
	monitor_detail.text = "%s\n%s · Respawns: %s" % [selected_group.get("name", "Select a group"),
		_active_summary(selected_group), _respawn_summary(selected_group)] if present else "Select a group in the full builder."
	_preview_movement()
	for index: int in range(group_picker.item_count):
		if str(group_picker.get_item_metadata(index)) == str(selected_group.get("name", "")):
			group_picker.select(index)
	_update_monster_actions()


func _start_region_selection() -> void:
	if selected_group.is_empty():
		status.text = "Select a group first."
		return
	_open_group_map()
	map_tool.select(2)
	map_canvas.selection_mode = 2
	inspector_tabs.current_tab = 1
	status.text = "Drag two corners on the map, then Apply movement area."


func _on_region_selected(region: Rect2i) -> void:
	if str(selected_group.get("map_id", "")) != selected_map_id:
		status.text = "Open the selected group's map before defining its region."
		return
	_loading_group = true
	region_x0.value = region.position.x
	region_y0.value = region.position.y
	region_x1.value = region.end.x - 1
	region_y1.value = region.end.y - 1
	region_enabled.button_pressed = true
	_loading_group = false
	_mark_movement()
	status.text = "Region selected. Apply movement area to guide the group."


func _save_movement() -> void:
	if movement_save.disabled:
		return
	var value := _movement_from_controls()
	var fields: Array[String] = [_clean_field(str(selected_group.name)), "", "", str(value.radius), "", "", "", ""]
	if value.anchor is Dictionary:
		fields[1] = str(value.anchor.x)
		fields[2] = str(value.anchor.y)
	if value.region is Dictionary:
		for index: int in range(4):
			fields[4 + index] = str(value.region[["x0", "y0", "x1", "y1"][index]])
	command_requested.emit("#invasion_assistant group movement " + "|".join(fields))
	status.text = "Applying movement home; creatures walk there when free."


func _move_anchor_selection() -> void:
	_move_anchor_to(Vector2i(int(coordinate_x.value), int(coordinate_y.value)))


func _move_monitor_anchor() -> void:
	_move_anchor_to(Vector2i(int(monitor_x.value), int(monitor_y.value)))


func _move_anchor_to(tile: Vector2i) -> void:
	if selected_group.is_empty() or movement_save.disabled or str(selected_group.get("map_id", "")) != selected_map_id:
		return
	if not _valid_logical_tile(selected_map_id, tile):
		status.text = "Choose coordinates inside the selected group's map."
		return
	command_requested.emit("#invasion_assistant group anchor %s|%d|%d" % [_clean_field(str(selected_group.name)), tile.x, tile.y])
	status.text = "Moving anchor and region; creatures walk toward their new home."


func _on_monitor_coordinate(tile: Vector2i) -> void:
	monitor_x.value = tile.x
	monitor_y.value = tile.y
	map_tool.select(0)
	map_canvas.selection_mode = 0
	_on_coordinate_selected(tile)


func _on_monitor_location(index: int) -> void:
	var point: Dictionary = monitor_location.get_item_metadata(index) as Dictionary
	if point.is_empty():
		return
	_on_monitor_coordinate(Vector2i(int(point.x), int(point.y)))


func _review_action(title_text: String, action: String, body: String, command: String) -> void:
	_pending_action = {"command": command}
	action_dialog.title = title_text
	action_dialog.dialog_text = body
	action_dialog.ok_button_text = action
	action_dialog.popup_centered(Vector2i(mini(650, _available_size().x), 300))


func _confirm_action() -> void:
	var command := str(_pending_action.get("command", ""))
	_pending_action.clear()
	if not command.is_empty():
		command_requested.emit(command)
		status.text = "Request sent; waiting for the server."


func _review_clear_group() -> void:
	if selected_group.is_empty() or not bool(selected_group.get("active", false)):
		return
	_review_action("Clear selected invasion group", "Clear group", "%s on %s\nRemove its %d living creatures and cancel %d queued reinforcements.\nThis cannot be undone." % [
		selected_group.name, selected_group.get("map_name", ""), int(selected_group.get("alive", 0)), int(selected_group.get("queued", 0))],
		"#invasion_assistant group clear " + _clean_field(str(selected_group.name)))


func _review_delete_group() -> void:
	if selected_group.is_empty() or group_delete.disabled:
		return
	_review_action("Delete editable group", "Delete group", "Delete %s and its saved composition?" % selected_group.name,
		"#invasion_assistant group delete " + _clean_field(str(selected_group.name)))


func _review_quick_spawn() -> void:
	if selected_monster.is_empty():
		return
	_review_action("Quick spawn at your character", "Spawn creatures", "Spawn %d %s (%s) at your current server location?" % [int(monster_quantity.value), selected_monster.get("name", "creatures"), _monster_rank()],
		"#invasion_assistant monster spawn %s|%d|%s" % [selected_monster.get("type", ""), int(monster_quantity.value), _monster_rank()])


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
				_last_map_update = Time.get_ticks_msec()
				_show_map_state()
		"groups":
			groups_state = _accumulate(groups_state, update, "groups")
			if _is_last_page(update):
				_last_groups_update = Time.get_ticks_msec()
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
	_update_freshness()


func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 28
	button.pressed.connect(callback)
	parent.add_child(button)
	return button


func _label(parent: Node, text: String) -> Label:
	var label := Label.new()
	label.text = text
	parent.add_child(label)
	return label


func _spin(parent: Node, prefix: String, value: float = 0.0) -> SpinBox:
	var spin := SpinBox.new()
	spin.min_value = -2147483648
	spin.max_value = 2147483647
	spin.prefix = prefix
	spin.value = value
	spin.custom_minimum_size.x = 88
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(spin)
	return spin


func _picker(parent: Node) -> OptionButton:
	var picker := OptionButton.new()
	picker.fit_to_longest_item = false
	picker.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(picker)
	return picker


func _build_ui() -> void:
	var skin := Theme.new()
	skin.default_font_size = COMPACT_FONT_SIZE
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color("182124")
	panel.border_color = Color("817052")
	panel.set_border_width_all(1)
	panel.set_content_margin_all(8)
	skin.set_stylebox("panel", "TabContainer", panel)
	var field := panel.duplicate() as StyleBoxFlat
	field.bg_color = Color("101719")
	field.set_content_margin_all(5)
	skin.set_stylebox("normal", "LineEdit", field)
	skin.set_color("font_color", "Label", Color("efe7d6"))
	skin.set_color("font_color", "Button", Color("efe7d6"))
	theme = skin
	var surface := Panel.new()
	surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	surface.add_theme_stylebox_override("panel", panel)
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 8)
	add_child(margin)
	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 6)
	margin.add_child(root)
	monitor_header = HBoxContainer.new()
	monitor_header.mouse_filter = Control.MOUSE_FILTER_STOP
	monitor_header.gui_input.connect(_on_monitor_header_gui_input)
	root.add_child(monitor_header)
	var heading := _label(monitor_header, "Invasion Assistant")
	heading.mouse_filter = Control.MOUSE_FILTER_IGNORE
	heading.add_theme_font_size_override("font_size", 18)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mode_button = _button(monitor_header, "Monitor view", func() -> void: set_monitor_mode(not monitor_mode))
	_button(monitor_header, "×", hide).tooltip_text = "Close invasion assistant"
	var utilities := HBoxContainer.new()
	root.add_child(utilities)
	summary = _label(utilities, "Waiting for server…")
	summary.clip_text = true
	summary.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	god_storage_button = _button(utilities, "God storage", func() -> void: command_requested.emit("#god_storage"))
	monitor_dock_button = _button(utilities, "Undock", func() -> void: set_monitor_docked(not monitor_docked))
	_update_monitor_dock_controls()
	_button(utilities, "Refresh", _refresh_current)
	freshness = _label(root, "No live snapshot yet")
	freshness.add_theme_color_override("font_color", Color("a6b7bc"))
	workspace = HBoxContainer.new()
	workspace.custom_minimum_size.y = 430
	workspace.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	workspace.size_flags_vertical = Control.SIZE_EXPAND_FILL
	workspace_scroll = ScrollContainer.new()
	workspace_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	workspace_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(workspace_scroll)
	workspace_scroll.add_child(workspace)
	tabs = TabContainer.new()
	tabs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	workspace.add_child(tabs)
	tabs.tab_changed.connect(_on_tab_changed)
	_build_maps_tab()
	_build_groups_tab()
	_build_monsters_tab()
	_build_inspector()
	_build_monitor(root)
	_build_create_dialog()
	action_dialog = ConfirmationDialog.new()
	action_dialog.confirmed.connect(_confirm_action)
	add_child(action_dialog)
	var footer := HBoxContainer.new()
	root.add_child(footer)
	status = _label(footer, "Select a group to prepare or monitor an invasion.")
	status.clip_text = true
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_build_resize_grip()
	for field_control: LineEdit in [group_name, group_description, group_boss_type, group_boss_name]:
		field_control.text_changed.connect(func(_text: String) -> void: _mark_draft())
	for spin: SpinBox in [group_minimum, group_maximum, group_health]:
		spin.value_changed.connect(func(_value: float) -> void: _mark_draft())
	group_map.item_selected.connect(func(_index: int) -> void: _mark_draft())


func _build_resize_grip() -> void:
	resize_grip = Button.new()
	resize_grip.text = "◢"
	resize_grip.flat = true
	resize_grip.focus_mode = Control.FOCUS_NONE
	resize_grip.tooltip_text = "Resize frame; text stays readable"
	resize_grip.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	resize_grip.custom_minimum_size = RESIZE_GRIP_SIZE
	resize_grip.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	resize_grip.offset_left = -RESIZE_GRIP_SIZE.x
	resize_grip.offset_top = -RESIZE_GRIP_SIZE.y
	resize_grip.gui_input.connect(_on_resize_grip_gui_input)
	add_child(resize_grip)


func _build_maps_tab() -> void:
	var page := HBoxContainer.new()
	page.name = "Map"
	tabs.add_child(page)
	map_sidebar = VBoxContainer.new()
	map_sidebar.custom_minimum_size.x = 180
	page.add_child(map_sidebar)
	map_filter = LineEdit.new()
	map_filter.placeholder_text = "Search maps…"
	map_filter.text_changed.connect(func(_value: String) -> void: _rebuild_maps())
	map_sidebar.add_child(map_filter)
	map_list = ItemList.new()
	map_list.max_text_lines = 2
	map_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map_list.item_selected.connect(_on_map_selected)
	map_sidebar.add_child(map_list)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page.add_child(column)
	map_selector = _picker(column)
	map_selector.item_selected.connect(func(index: int) -> void: _select_map(str(map_selector.get_item_metadata(index))))
	map_title = _label(column, "Select a map")
	var tools := HBoxContainer.new()
	column.add_child(tools)
	map_tool = _picker(tools)
	for title: String in ["Select coordinates", "Set movement center", "Draw movement region"]:
		map_tool.add_item(title)
	map_tool.item_selected.connect(func(index: int) -> void: map_canvas.selection_mode = index)
	_button(tools, "−", func() -> void: map_canvas.zoom_by(0.8))
	_button(tools, "+", func() -> void: map_canvas.zoom_by(1.25))
	_button(tools, "Fit", func() -> void: map_canvas.reset_view())
	map_canvas = MapCanvasScript.new()
	map_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map_canvas.coordinate_selected.connect(_on_coordinate_selected)
	map_canvas.region_selected.connect(_on_region_selected)
	column.add_child(map_canvas)
	var legend := _label(column, "● Player   ◆ Invader   ♛ Boss   □ Spawn   ⊕ Anchor")
	legend.add_theme_font_size_override("font_size", 12)
	var location_row := HBoxContainer.new()
	column.add_child(location_row)
	location_picker = _picker(location_row)
	location_picker.item_selected.connect(_on_location_selected)
	var coordinate_row := HBoxContainer.new()
	column.add_child(coordinate_row)
	coordinate_x = _spin(coordinate_row, "X")
	coordinate_y = _spin(coordinate_row, "Y")
	for spin: SpinBox in [coordinate_x, coordinate_y]:
		spin.value_changed.connect(func(_value: float) -> void: _coordinate_fields_changed())
	teleport_button = _button(coordinate_row, "Teleport", _teleport)
	teleport_button.disabled = true
	teleport_button.tooltip_text = "Teleport your character to the selected map coordinates"
	map_status = _label(column, "Click to select exact coordinates. Middle-drag to pan.")
	map_status.clip_text = true
	map_status.add_theme_font_size_override("font_size", 12)
	map_roster = RichTextLabel.new()
	map_roster.bbcode_enabled = true
	map_roster.visible = false
	column.add_child(map_roster)


func _build_groups_tab() -> void:
	var page := VBoxContainer.new()
	page.name = "Groups"
	tabs.add_child(page)
	var actions := HBoxContainer.new()
	page.add_child(actions)
	group_create = _button(actions, "New group", _show_create_group)
	group_duplicate = _button(actions, "Duplicate to edit", _duplicate_group)
	group_filter = LineEdit.new()
	group_filter.placeholder_text = "Search group, map, creature or active…"
	group_filter.text_changed.connect(func(_value: String) -> void: _rebuild_groups())
	page.add_child(group_filter)
	group_list = ItemList.new()
	group_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	group_list.item_selected.connect(_on_group_selected)
	page.add_child(group_list)
	_label(page, "Configured groups are read-only. Duplicate one to prepare your own.").autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func _build_monsters_tab() -> void:
	var page := VBoxContainer.new()
	page.name = "Creatures"
	tabs.add_child(page)
	monster_filter = LineEdit.new()
	monster_filter.placeholder_text = "Search creature, tier or rating…"
	monster_filter.text_changed.connect(func(_value: String) -> void: _rebuild_monsters())
	page.add_child(monster_filter)
	monster_updated_only = CheckBox.new()
	monster_updated_only.text = "Reviewed models only"
	monster_updated_only.tooltip_text = "Hide creatures using placeholder models"
	monster_updated_only.toggled.connect(func(_pressed: bool) -> void: _rebuild_monsters())
	page.add_child(monster_updated_only)
	monster_list = ItemList.new()
	monster_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	monster_list.item_selected.connect(_on_monster_selected)
	page.add_child(monster_list)
	monster_detail = RichTextLabel.new()
	monster_detail.bbcode_enabled = true
	monster_detail.custom_minimum_size.y = 100
	page.add_child(monster_detail)
	var builder_row := HBoxContainer.new()
	page.add_child(builder_row)
	monster_quantity = _spin(builder_row, "Qty", 1)
	monster_quantity.min_value = 1
	monster_quantity.max_value = 100
	monster_quantity.value_changed.connect(func(_value: float) -> void: _update_monster_actions())
	monster_miniboss = CheckBox.new()
	monster_miniboss.text = "Miniboss (+10–30% stats)"
	monster_miniboss.tooltip_text = "Roll a stronger unnamed version of this creature. Boss species are excluded."
	monster_miniboss.toggled.connect(func(_pressed: bool) -> void: _update_monster_actions())
	page.add_child(monster_miniboss)
	monster_group = _picker(builder_row)
	monster_group.item_selected.connect(func(index: int) -> void:
		_select_group_name(str(monster_group.get_item_metadata(index).get("name", "")))
		_update_monster_actions())
	monster_create_group = _button(page, "New group…", _show_create_group_for_monster)
	monster_add_to_group = _button(page, "Add to selected group", _add_monster_to_group)
	monster_add_to_group.disabled = true
	monster_spawn_here = _button(page, "Quick spawn at my character…", _review_quick_spawn)
	monster_spawn_here.disabled = true


func _build_inspector() -> void:
	inspector = VBoxContainer.new()
	inspector.custom_minimum_size.x = 340
	workspace.add_child(inspector)
	var column := VBoxContainer.new()
	column.custom_minimum_size.x = 318
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 6)
	inspector.add_child(column)
	_label(column, "SELECTED GROUP").add_theme_color_override("font_color", Color("d8ba78"))
	group_picker = _picker(column)
	group_picker.item_selected.connect(func(index: int) -> void: _select_group_name(str(group_picker.get_item_metadata(index))))
	group_detail = RichTextLabel.new()
	group_detail.bbcode_enabled = true
	group_detail.custom_minimum_size.y = 96
	group_detail.text = "Choose a group, or create a new one."
	column.add_child(group_detail)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	group_spawn = _button(actions, "Review spawn…", _spawn_group)
	group_open_map = _button(actions, "Locate", _open_group_map)
	group_spawn.disabled = true
	group_open_map.disabled = true
	inspector_tabs = TabContainer.new()
	inspector_tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(inspector_tabs)
	var composition := VBoxContainer.new()
	composition.name = "Composition"
	inspector_tabs.add_child(composition)
	group_composition = ItemList.new()
	group_composition.custom_minimum_size.y = 84
	group_composition.size_flags_vertical = Control.SIZE_EXPAND_FILL
	group_composition.item_selected.connect(_on_composition_selected)
	composition.add_child(group_composition)
	composition_total = _label(composition, "0 creatures")
	_button(composition, "Add creatures", func() -> void: tabs.current_tab = 2; inspector_tabs.current_tab = 0)
	var removal := HBoxContainer.new()
	composition.add_child(removal)
	group_remove_quantity = _spin(removal, "Qty", 1)
	group_remove_quantity.min_value = 1
	group_remove_quantity.max_value = 100
	group_remove_monster = _button(removal, "Remove selected", _remove_group_monster)
	group_remove_monster.disabled = true
	var movement_page := VBoxContainer.new()
	movement_page.name = "Movement"
	inspector_tabs.add_child(movement_page)
	var movement_scroll := ScrollContainer.new()
	movement_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	movement_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	movement_page.add_child(movement_scroll)
	var movement_column := VBoxContainer.new()
	movement_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	movement_scroll.add_child(movement_column)
	_build_movement_editor(movement_column)
	# Keep apply/move reachable while the coordinate fields scroll.
	movement_save.reparent(movement_page)
	move_anchor_button.reparent(movement_page)
	var settings_scroll := ScrollContainer.new()
	settings_scroll.name = "Settings"
	settings_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	inspector_tabs.add_child(settings_scroll)
	settings_column = VBoxContainer.new()
	settings_scroll.add_child(settings_column)
	settings_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var editor := GridContainer.new()
	editor.columns = 2
	settings_column.add_child(editor)
	_add_form_label(editor, "Name")
	group_name = LineEdit.new()
	group_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	editor.add_child(group_name)
	_add_form_label(editor, "Description")
	group_description = LineEdit.new()
	editor.add_child(group_description)
	_add_form_label(editor, "Map")
	group_map = _picker(editor)
	_add_form_label(editor, "Minimum")
	group_minimum = _spin(editor, "", 1)
	group_minimum.min_value = 0
	group_minimum.max_value = 1000
	_add_form_label(editor, "Maximum")
	group_maximum = _spin(editor, "", 1)
	group_maximum.min_value = 0
	group_maximum.max_value = 1000
	_add_form_label(editor, "Health ×")
	group_health = _spin(editor, "", 1)
	group_health.min_value = 0.1
	group_health.max_value = 100
	group_health.step = 0.1
	_add_form_label(editor, "Boss type")
	group_boss_type = LineEdit.new()
	group_boss_type.placeholder_text = "Optional creature type"
	editor.add_child(group_boss_type)
	_add_form_label(editor, "Boss name")
	group_boss_name = LineEdit.new()
	editor.add_child(group_boss_name)
	group_save = _button(settings_column, "Save group settings", _save_group)
	group_save.disabled = true
	group_delete = _button(settings_column, "Delete editable group…", _review_delete_group)
	group_delete.disabled = true
	_button(settings_column, "Discard unsaved edits", _discard_draft)
	group_clear = _button(column, "Clear active group…", _review_clear_group)
	group_clear.add_theme_color_override("font_color", Color("ff9186"))
	group_clear.disabled = true


func _build_movement_editor(column: VBoxContainer) -> void:
	_label(column, "MOVEMENT HOME")
	anchor_enabled = CheckBox.new()
	anchor_enabled.text = "Use centerpoint + roam radius"
	column.add_child(anchor_enabled)
	var row := HBoxContainer.new()
	column.add_child(row)
	anchor_x = _spin(row, "X")
	anchor_y = _spin(row, "Y")
	anchor_radius = _spin(column, "Roam radius", 18)
	anchor_radius.min_value = 1
	anchor_radius.max_value = 1000
	region_enabled = CheckBox.new()
	region_enabled.text = "Use rectangular region"
	column.add_child(region_enabled)
	var corners := GridContainer.new()
	corners.columns = 2
	column.add_child(corners)
	region_x0 = _spin(corners, "Min X")
	region_y0 = _spin(corners, "Min Y")
	region_x1 = _spin(corners, "Max X")
	region_y1 = _spin(corners, "Max Y")
	_button(column, "Draw region on map", _start_region_selection)
	movement_save = _button(column, "Apply movement area", _save_movement)
	move_anchor_button = _button(column, "Move anchor + region to selection", _move_anchor_selection)
	move_anchor_button.tooltip_text = "The region moves with its anchor. With a region alone, this moves its center. Combat keeps normal priority."
	movement_save.tooltip_text = "Guide idle creatures to this area using normal walking. Combat and collision remain unchanged."
	for spin: SpinBox in [anchor_x, anchor_y, anchor_radius, region_x0, region_y0, region_x1, region_y1]:
		spin.value_changed.connect(func(_value: float) -> void: _mark_movement())
	anchor_enabled.toggled.connect(func(_value: bool) -> void: _mark_movement())
	region_enabled.toggled.connect(func(_value: bool) -> void: _mark_movement())


func _build_monitor(root: VBoxContainer) -> void:
	monitor_scroll = ScrollContainer.new()
	monitor_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	monitor_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(monitor_scroll)
	monitor_scroll.hide()
	monitor_panel = VBoxContainer.new()
	monitor_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	monitor_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	monitor_scroll.add_child(monitor_panel)
	monitor_panel.hide()
	monitor_map = _picker(monitor_panel)
	monitor_map.item_selected.connect(func(index: int) -> void: _select_map(str(monitor_map.get_item_metadata(index))))
	monitor_canvas = MapCanvasScript.new()
	monitor_canvas.custom_minimum_size = Vector2(220, 125)
	monitor_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	monitor_canvas.coordinate_selected.connect(_on_monitor_coordinate)
	monitor_panel.add_child(monitor_canvas)
	_label(monitor_panel, "ACTIVE GROUPS · alive / queued")
	monitor_groups = ItemList.new()
	monitor_groups.custom_minimum_size.y = 64
	monitor_groups.item_selected.connect(func(index: int) -> void: _select_group_name(str(monitor_groups.get_item_metadata(index))))
	monitor_panel.add_child(monitor_groups)
	monitor_detail = _label(monitor_panel, "Select an active group")
	monitor_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	monitor_location = _picker(monitor_panel)
	monitor_location.item_selected.connect(_on_monitor_location)
	var coordinates := HBoxContainer.new()
	monitor_panel.add_child(coordinates)
	monitor_x = _spin(coordinates, "X")
	monitor_y = _spin(coordinates, "Y")
	monitor_move = _button(monitor_panel, "Move anchor + region here", _move_monitor_anchor)
	monitor_clear = _button(monitor_panel, "Clear selected group…", _review_clear_group)
	monitor_clear.add_theme_color_override("font_color", Color("ff9186"))


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
		var label := str(map.get("name", map.get("id", "Map")))
		var item := map_list.add_item(label)
		map_list.set_item_metadata(item, map)
		map_list.set_item_tooltip(item, "%s\n%d players · %d invaders · %d active groups" % [label,
			int(map.get("players", 0)), int(map.get("invasions", 0)), int(map.get("active_groups", 0))])
		if str(map.get("id", "")) == selected_map_id:
			selected_index = item
	if selected_index >= 0:
		map_list.select(selected_index)
		map_list.ensure_current_is_visible()
	if not _draft_dirty:
		_populate_map_picker(group_map, str(selected_group.get("map_id", selected_map_id)))
	_populate_map_picker(create_map, selected_map_id)
	for picker: OptionButton in [map_selector, monitor_map]:
		_populate_map_picker(picker, selected_map_id)


func _on_map_selected(index: int) -> void:
	var map: Dictionary = map_list.get_item_metadata(index) as Dictionary
	_select_map(str(map.get("id", "")))


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
		monitor_canvas.set_map_state({"map": {"id": map.get("id", "")}, "coordinatesSupported": false})
		_sync_group_views()
		return
	var display_state: Dictionary = map_state.duplicate(true)
	_setting_coordinates = true
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
	map_title.text = "%d players · %d invaders" % [(map_state.get("players", []) as Array).size(), (map_state.get("creatures", []) as Array).size()]
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
	monitor_canvas.set_map_state(display_state, _map_texture(map_id), _map_projection(map_id))
	monitor_location.clear()
	for index: int in range(location_picker.item_count):
		monitor_location.add_item(location_picker.get_item_text(index))
		monitor_location.set_item_metadata(index, location_picker.get_item_metadata(index))
	for spin: SpinBox in [monitor_x, monitor_y]:
		spin.min_value = bounds.position.x if spin == monitor_x else bounds.position.y
		spin.max_value = bounds.end.x - 1 if spin == monitor_x else bounds.end.y - 1
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
	_setting_coordinates = false
	map_status.text = "%d named locations, %d players, %d invasion creatures. Live markers are server-authoritative." % [
		locations.size(),
		(map_state.get("players", []) as Array).size(),
		(map_state.get("creatures", []) as Array).size()]
	_rebuild_maps()
	_sync_group_views()


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
		var marker := "[color=#ffc94f]◆[/color]" if bool(creature.get("boss", false)) or bool(creature.get("miniboss", false)) else "[color=#ff6b63]◆[/color]"
		lines.append("%s %s\n   %s · %d/%d HP · [%d,%d]" % [marker,
			creature.get("name", "Invader"), creature.get("tier", "Unknown"),
			creature.get("health", 0), creature.get("max_health", 0),
			creature.get("x", 0), creature.get("y", 0)])
	map_roster.text = "\n".join(lines)


func _on_coordinate_selected(tile: Vector2i) -> void:
	if not _valid_logical_tile(selected_map_id, tile):
		return
	_setting_coordinates = true
	coordinate_x.value = tile.x
	coordinate_y.value = tile.y
	_setting_coordinates = false
	location_picker.select(0)
	location_picker.tooltip_text = ""
	map_status.text = "Selected %d, %d on %s." % [tile.x, tile.y, selected_map_id]
	map_canvas.selected_tile = tile
	monitor_x.value = tile.x
	monitor_y.value = tile.y
	if map_tool.selected == 1 and str(selected_group.get("map_id", "")) == selected_map_id:
		anchor_enabled.button_pressed = true
		anchor_x.value = tile.x
		anchor_y.value = tile.y
		_mark_movement()
	map_canvas.queue_redraw()
	_update_monster_actions()


func _on_location_selected(index: int) -> void:
	var location: Dictionary = location_picker.get_item_metadata(index) as Dictionary
	# The closed picker trims a long name; hovering it reads the whole one.
	location_picker.tooltip_text = location_picker.get_item_text(index) if index > 0 else ""
	if location.is_empty():
		return
	if not _valid_logical_tile(selected_map_id, Vector2i(int(location.get("x", 0)), int(location.get("y", 0)))):
		return
	_on_coordinate_selected(Vector2i(int(location.get("x", 0)), int(location.get("y", 0))))
	location_picker.select(index)
	location_picker.tooltip_text = location_picker.get_item_text(index)


func _coordinate_fields_changed() -> void:
	if not _setting_coordinates and not teleport_button.disabled:
		_on_coordinate_selected(Vector2i(int(coordinate_x.value), int(coordinate_y.value)))


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
	_stash_draft()
	group_list.clear()
	group_picker.clear()
	monitor_groups.clear()
	var query := group_filter.text.strip_edges().to_lower()
	var selected_name := _pending_created_group if not _pending_created_group.is_empty() else str(selected_group.get("name", ""))
	var selected_index := -1
	for raw_group: Variant in groups_state.get("groups", []):
		var group := raw_group as Dictionary
		var name := str(group.get("name", ""))
		group_picker.add_item(name + (" · Active" if bool(group.get("active", false)) else " · Ready"))
		group_picker.set_item_metadata(group_picker.item_count - 1, name)
		if name == selected_name:
			group_picker.select(group_picker.item_count - 1)
		if bool(group.get("active", false)) and str(group.get("map_id", "")) == selected_map_id:
			var row := monitor_groups.add_item("%s  ·  %d alive / %d queued" % [name, int(group.get("alive",0)), int(group.get("queued",0))])
			monitor_groups.set_item_metadata(row, name)
			if name == selected_name:
				monitor_groups.select(row)
		var searchable := "%s %s %s %s %s" % [name, group.get("description", ""), group.get("map_name", ""),
			" ".join(group.get("creatures", []) as Array), "active" if bool(group.get("active",false)) else "ready"]
		if not query.is_empty() and not query in searchable.to_lower():
			continue
		var row := group_list.add_item("%s · %s · %s" % [name, group.get("map_name", ""),
			"ACTIVE · %d alive / %d queued" % [int(group.get("alive",0)),int(group.get("queued",0))] if bool(group.get("active",false)) else "Ready"])
		group_list.set_item_metadata(row, group)
		group_list.set_item_tooltip(row, "%s\n%s" % [name, searchable])
		if name == selected_name:
			selected_index = row
	if selected_index < 0 and selected_group.is_empty() and group_list.item_count > 0:
		selected_index = 0
	if selected_index >= 0:
		group_list.select(selected_index)
		_on_group_selected(selected_index)
		_pending_created_group = ""
	_rebuild_monster_group_picker()
	if selected_index >= 0 and _pending_add_to_created and not selected_monster.is_empty():
		_pending_add_to_created = false
		_add_monster_to_group()


func _on_group_selected(index: int) -> void:
	_stash_draft()
	var next_group: Dictionary = group_list.get_item_metadata(index)
	var same_group := str(next_group.get("name", "")) == str(selected_group.get("name", ""))
	var focused := gui_get_focus_owner()
	var preserve_fields := same_group and (_draft_dirty or (focused != null and settings_column.is_ancestor_of(focused)))
	var editing_movement := false
	for spin: SpinBox in [anchor_x, anchor_y, anchor_radius, region_x0, region_y0, region_x1, region_y1]:
		editing_movement = editing_movement or spin.get_line_edit().has_focus()
	var preserve_movement := same_group and (_movement_dirty or editing_movement)
	var previous_type := ""
	var previous_rows := group_composition.get_selected_items()
	if same_group and not previous_rows.is_empty():
		previous_type = str(group_composition.get_item_metadata(previous_rows[0]).get("type", ""))
	selected_group = (group_list.get_item_metadata(index) as Dictionary).duplicate(true)
	_loading_group = true
	var dynamic := bool(selected_group.get("dynamic", false))
	var active := bool(selected_group.get("active", false))
	group_open_map.disabled = str(selected_group.get("map_id", "")).is_empty()
	group_duplicate.disabled = false
	group_delete.disabled = not dynamic or active
	group_spawn.disabled = active or int(selected_group.get("points",0)) == 0
	group_clear.disabled = not active
	group_save.disabled = not dynamic
	group_detail.text = "[b]%s[/b]\n%s · %s\n%s\nRespawns: %s\nHealth ×%.1f · Strongest rating %d" % [
		selected_group.get("name", "Group"), "Editable" if dynamic else "Configured · duplicate to edit",
		selected_group.get("map_name", ""), _active_summary(selected_group), _respawn_summary(selected_group),
		float(selected_group.get("health_multiplier",1)), int(selected_group.get("strength",0))]
	if not preserve_fields:
		group_name.text = str(selected_group.get("name", ""))
		group_description.text = str(selected_group.get("description", ""))
		_populate_map_picker(group_map, str(selected_group.get("map_id", "")))
		group_minimum.value = int(selected_group.get("minimum",0))
		group_maximum.value = int(selected_group.get("maximum",0))
		group_health.value = float(selected_group.get("health_multiplier",1))
		group_boss_type.text = str(selected_group.get("boss_type", ""))
		group_boss_name.text = str(selected_group.get("boss_name", ""))
	for field_control: LineEdit in [group_name, group_description, group_boss_type, group_boss_name]:
		field_control.editable = dynamic
	for spin: SpinBox in [group_minimum, group_maximum, group_health]:
		spin.editable = dynamic
	group_map.disabled = not dynamic
	group_composition.clear()
	var total := 0
	for entry: Dictionary in selected_group.get("composition", []):
		var row := group_composition.add_item("%s × %d" % [entry.get("name",entry.get("type","Creature")), int(entry.get("quantity",0))])
		group_composition.set_item_metadata(row, entry)
		total += int(entry.get("quantity",0))
	composition_total.text = "%d creatures · %d distinct locations" % [total, (selected_group.get("locations",[]) as Array).size()]
	group_remove_monster.disabled = true
	if not previous_type.is_empty():
		for row: int in range(group_composition.item_count):
			if str(group_composition.get_item_metadata(row).get("type", "")) == previous_type:
				group_composition.select(row)
				group_remove_monster.disabled = not dynamic
	if not preserve_movement:
		_load_movement(selected_group.get("movement", {}) as Dictionary)
	_restore_draft(preserve_fields, preserve_movement)
	_loading_group = false
	_sync_group_views()


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
	var target_map := str(selected_group.get("map_id", ""))
	tabs.current_tab = 0
	if target_map != selected_map_id or not map_canvas.coordinates_supported:
		_select_map(target_map)


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
	if selected_group.is_empty() or group_spawn.disabled:
		return
	if _draft_dirty or _movement_dirty:
		inspector_tabs.current_tab = 2
		status.text = "Save group settings and apply movement changes before reviewing a spawn."
		return
	var locations: Array[String] = []
	for location: Dictionary in selected_group.get("locations", []):
		locations.append("[%d, %d] × %d" % [int(location.get("x",0)),int(location.get("y",0)),int(location.get("quantity",0))])
	var body := "%s on %s\n%s\nLocations: %s\nHealth ×%.1f\nRespawns: %s" % [selected_group.get("name",""),
		selected_group.get("map_name",""),composition_total.text, ", ".join(locations),
		float(selected_group.get("health_multiplier",1)),_respawn_summary(selected_group)]
	_review_action("Review spawn", "Spawn group", body, "#invasion_assistant group activate " + _clean_field(str(selected_group.name)))


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
	command_requested.emit("#invasion_assistant group remove %s|%s|%d|%s" % [
		_clean_field(str(selected_group.get("name", ""))),
		entry.get("type", ""), int(group_remove_quantity.value), "miniboss" if bool(entry.get("miniboss", false)) else "normal"])
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
	monster_miniboss.disabled = not has_monster or not bool(selected_monster.get("can_be_miniboss", true))
	if monster_miniboss.disabled:
		monster_miniboss.set_pressed_no_signal(false)
	monster_spawn_here.disabled = not has_monster
	monster_add_to_group.disabled = true
	monster_add_to_group.text = "Select a group and spawn location"
	if has_monster and monster_group.item_count > 0:
		var group := monster_group.get_item_metadata(monster_group.selected) as Dictionary
		var location: Variant = _spawn_location_for_group(group)
		if location is Vector2i:
			monster_add_to_group.disabled = false
			monster_add_to_group.text = "Add %d at [%d, %d]" % [int(monster_quantity.value),location.x,location.y]
			monster_add_to_group.tooltip_text = "%s → %s on %s" % [selected_monster.get("name",""), group.get("name",""),group.get("map_name","")]
	var spawn_label := "minibosses" if _monster_rank() == "miniboss" else "creatures"
	monster_spawn_here.text = "Quick spawn %d %s at my character…" % [int(monster_quantity.value), spawn_label]


func _monster_rank() -> String:
	return "miniboss" if monster_miniboss != null and monster_miniboss.button_pressed else "normal"


func _add_monster_to_group() -> void:
	if selected_monster.is_empty() or monster_group.item_count == 0:
		return
	var group := monster_group.get_item_metadata(monster_group.selected) as Dictionary
	var location: Variant = _spawn_location_for_group(group)
	if not location is Vector2i:
		status.text = "Coordinates unavailable: this map has no verified spawn location."
		return
	command_requested.emit("#invasion_assistant group add %s|%s|%d|%d|%d|%s" % [
		_clean_field(str(group.get("name", ""))), selected_monster.get("type", ""),
		int(monster_quantity.value), location.x, location.y, _monster_rank()])
	status.text = "Adding %d %s to %s at [%d, %d]…" % [int(monster_quantity.value),
		selected_monster.get("name", "monster"), group.get("name", "group"),
		location.x, location.y]


func _spawn_monster_here() -> void:
	if selected_monster.is_empty():
		return
	command_requested.emit("#invasion_assistant monster spawn %s|%d|%s" % [
		selected_monster.get("type", ""), int(monster_quantity.value), _monster_rank()])
	status.text = "Spawning %d %s at your live server location…" % [
		int(monster_quantity.value), selected_monster.get("name", "monster")]


func _spawn_location_for_group(group: Dictionary) -> Variant:
	if group.has("coordinatesSupported") and not bool(group.coordinatesSupported):
		return null
	var map_id := str(group.get("map_id", ""))
	if map_id == selected_map_id and map_canvas.selected_tile is Vector2i:
		var tile := Vector2i(int(coordinate_x.value), int(coordinate_y.value))
		return tile if _valid_logical_tile(map_id, tile) else null
	var locations: Array = group.get("locations",[]) as Array
	if not locations.is_empty():
		var tile := Vector2i(int(locations[0].get("x",0)), int(locations[0].get("y",0)))
		return tile if _valid_logical_tile(map_id, tile) else null
	return null


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
	var manifest := _read_json(path)
	var result := {"minimap": manifest.get("minimap", {}),
		"coordinateTransform": entry.get("coordinateTransform", manifest.get("coordinateTransform", {}))}
	if _tab_maps.has(map_id):
		result.minimap = _tab_maps[map_id]
	return result


func _map_texture(map_id: String) -> Texture2D:
	if _texture_cache.has(map_id):
		return _texture_cache[map_id] as Texture2D
	var tab_map: Dictionary = _tab_maps.get(map_id, {}) as Dictionary
	var detail: Dictionary = tab_map.get("detail",{}) as Dictionary
	var path := str(detail.get("texture",tab_map.get("texture","")))
	if path.is_empty():
		var entry: Dictionary = MapRegistry.resolve(map_registry, map_id)
		var manifest_path := str(entry.get("manifest", ""))
		if manifest_path.is_empty():
			return null
		var manifest := _read_json(manifest_path)
		path = manifest_path.get_base_dir().path_join(str(manifest.get("minimap",{}).get("image","minimap.webp")))
	var pixels := Image.new()
	if pixels.load(ProjectSettings.globalize_path(path)) != OK:
		if detail.is_empty() or pixels.load(ProjectSettings.globalize_path(str(tab_map.get("texture", "")))) != OK:
			return null
		detail = {}
	if detail.is_empty():
		var crop: Array = tab_map.get("region",[]) as Array
		if crop.size() == 4:
			pixels = pixels.get_region(Rect2i(int(crop[0]),int(crop[1]),int(crop[2]),int(crop[3])))
	pixels.generate_mipmaps()
	var texture := ImageTexture.create_from_image(pixels)
	# The builder and monitor share these. Do not retain full detail for every
	# map an invasion master has inspected during a long session.
	if _texture_cache.size() >= 3:
		_texture_cache.erase(_texture_cache.keys()[0])
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
