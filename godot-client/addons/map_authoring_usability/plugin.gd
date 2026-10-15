@tool
extends EditorPlugin
## Viewport quality-of-life for map authoring scenes:
## - a cursor readout (territory metres, server tile, ground height),
## - the "smart grid" that drapes over the terrain under the cursor,
## - a Map tools menu with undoable batch edits for selected placements,
## - a time-of-day lighting preview and a top-down map capture,
## - readable gameplay markers, a walkability overlay, and road/river drawing,
## - groups (Ctrl+G), Alt+drag copies, a selection bar with editable fields,
## - a play-test walker, a live minimap dock and a low-spec view,
## - one-click toolbar toggles,
## - rebindable shortcuts and preferences in Editor Settings > Map Authoring.
## Nothing here is saved into scenes except group tags on grouped objects; every
## helper node is ownerless.

const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")
const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const CursorGrid := preload("res://addons/map_authoring_usability/cursor_grid.gd")
const Tools := preload("res://addons/map_authoring_usability/selection_tools.gd")
const PalettePlugin := preload("res://addons/map_asset_palette/plugin.gd")
const TimeOfDay := preload("res://addons/map_authoring_usability/time_of_day_preview.gd")
const TopDown := preload("res://addons/map_authoring_usability/top_down_capture.gd")
const MarkerOverlay := preload("res://addons/map_authoring_usability/marker_overlay.gd")
const Walkability := preload("res://addons/map_authoring_usability/walkability_overlay.gd")
const PathDraw := preload("res://addons/map_authoring_usability/path_draw_tool.gd")
const GroupTools := preload("res://addons/map_authoring_usability/group_tools.gd")
const Walker := preload("res://addons/map_authoring_usability/playtest_walker.gd")
const MinimapDock := preload("res://addons/map_authoring_usability/minimap_dock.gd")
const SelectionBar := preload("res://addons/map_authoring_usability/selection_bar.gd")
const PerformanceMode := preload("res://addons/map_authoring_usability/performance_mode.gd")
const ViewToolbar := preload("res://addons/map_authoring_usability/view_toolbar.gd")
const Markers := preload("res://addons/map_asset_palette/marker_library.gd")
const AreaTool := preload("res://addons/map_authoring_usability/area_tool.gd")
const AreaPanel := preload("res://addons/map_authoring_usability/area_panel.gd")
const PlanWater := preload("res://addons/map_authoring_usability/plan_water.gd")
const Scatter := preload("res://addons/map_authoring_usability/scatter_tool.gd")
const ReviewNotes := preload("res://addons/map_authoring_usability/review_notes.gd")
const ReviewNotesDock := preload("res://addons/map_authoring_usability/review_notes_dock.gd")
const ConceptMaster := preload("res://addons/map_authoring_usability/concept_master.gd")
const FOCUS_HELPER := "__MapAuthoringFocus"
const UI_REFRESH_SECONDS := 0.25
const MINIMAP_TARGET_LUMINANCE := 0.4
const POLL_SECONDS := 0.5
const ASSET_PLUGIN_META := &"map_asset_palette_plugin"
const SCULPT_PLUGIN_META := &"map_authoring_sculpt_plugin"
const USABILITY_PLUGIN_META := &"map_authoring_usability_plugin"
const RAY_LENGTH := 2048.0

enum MenuId {
	DROP_TO_GROUND,
	ROTATE_EACH,
	RANDOM_TURN,
	RANDOM_SIZE,
	SAVE_PREFAB,
	GRID_OFF,
	GRID_WHILE_PLACING,
	GRID_ALWAYS,
	READOUT,
	TIME_OF_DAY,
	CAPTURE_TOP_DOWN,
	SHOW_MARKERS,
	MARKER_LABELS,
	WALK_OFF,
	WALK_PUBLISHED,
	WALK_LIVE,
	WALK_CHANGES,
	DRAW_ROAD,
	DRAW_RIVER,
	GROUP,
	UNGROUP,
	DUPLICATE,
	PLAY_TEST,
	LOW_SPEC,
	FIX_DUPLICATE_IDS,
	PAINT_GROUND,
	STAMP_PLATEAU,
	PLAN_WATER,
	SCATTER,
	CONCEPT,
}

var _menu: MenuButton
var _grid := CursorGrid.new()
var _rng := RandomNumberGenerator.new()
var _hover_camera: Camera3D
var _hover_position := Vector2.ZERO
var _hover_dirty := false
var _hover_hit: Variant = null
var _hover_info: Dictionary = {}
var _hover_inside := false
var _time := TimeOfDay.new()
var _time_button: Button
var _time_panel: PopupPanel
var _time_toggle: CheckButton
var _time_slider: HSlider
var _time_label: Label
var _time_status: Label
var _capture_dialog: ConfirmationDialog
var _capture_path: LineEdit
var _capture_ppm: SpinBox
var _capture_references: CheckBox
var _capture_clip: CheckBox
var _capture_estimate: Label
var _capture_file_dialog: EditorFileDialog
var _capturing := false
var _markers := MarkerOverlay.new()
var _walk := Walkability.new()
var _draw := PathDraw.new()
var _walk_mode := Walkability.Mode.OFF
var _poll_elapsed := 0.0
var _copy := GroupTools.new()
var _walker := Walker.new()
var _performance := PerformanceMode.new()
var _minimap: MinimapDock
var _selection_bar: SelectionBar
var _toolbar: ViewToolbar
var _open_group := ""
var _opening_group_click := false
var _selection_guard := false
var _ui_elapsed := 0.0
var _minimap_countdown := -1.0
var _minimap_rendering := false
var _focusing := false
var _pending_focus: Array = []
## Placed objects sharing an id (Godot's Ctrl+D copies ids), refreshed by the poll.
var _duplicate_groups: Array[Dictionary] = []
var _area := AreaTool.new()
var _plan_water := PlanWater.new()
var _scatter := Scatter.new()
var _notes := ReviewNotes.new()
var _concept := ConceptMaster.new()
var _concept_on := false
var _notes_dock: ReviewNotesDock
var _plan_water_on := false
var _area_panel: AreaPanel
var _duplicate_signature := ""
## Instance ids of objects that already shared an id when the scene opened
## (such as Manymouth's retained stelae-court pair): never flagged or changed.
var _baseline_duplicates := {}
var _baseline_root_id := 0


func _enter_tree() -> void:
	Settings.register()
	_rng.randomize()
	get_editor_interface().get_base_control().set_meta(USABILITY_PLUGIN_META, self)
	_menu = MenuButton.new()
	_menu.text = "Map tools"
	_menu.flat = true
	_menu.tooltip_text = "Batch tools for selected placements and map editor view options."
	_menu.switch_on_hover = true
	_build_menu(_menu.get_popup())
	_menu.about_to_popup.connect(_sync_menu)
	add_control_to_container(EditorPlugin.CONTAINER_SPATIAL_EDITOR_MENU, _menu)
	_build_time_controls()
	add_control_to_container(EditorPlugin.CONTAINER_SPATIAL_EDITOR_MENU, _time_button)
	_toolbar = ViewToolbar.new()
	_toolbar.option_toggled.connect(_on_toolbar_toggled)
	_toolbar.walk_mode_selected.connect(func(mode: int) -> void: set_walkability_mode(mode))
	_toolbar.tool_requested.connect(func(tool: String) -> void: open_area_panel(tool))
	_area_panel = AreaPanel.new()
	_area_panel.start_requested.connect(func(kind: String, options: Dictionary) -> void:
		if kind == "scatter":
			start_scatter(options)
		else:
			start_area_tool(kind, options))
	get_editor_interface().get_base_control().add_child(_area_panel)
	add_control_to_container(EditorPlugin.CONTAINER_SPATIAL_EDITOR_MENU, _toolbar)
	_selection_bar = SelectionBar.new()
	_selection_bar.visible = false
	_selection_bar.field_edited.connect(_on_bar_field_edited)
	_selection_bar.tool_pressed.connect(_on_bar_tool)
	add_control_to_container(EditorPlugin.CONTAINER_SPATIAL_EDITOR_BOTTOM, _selection_bar)
	_minimap = MinimapDock.new()
	_minimap.jump_requested.connect(_on_minimap_jump)
	_minimap.refresh_requested.connect(func() -> void: refresh_minimap())
	add_dock(_minimap)
	_notes_dock = ReviewNotesDock.new()
	_notes_dock.add_requested.connect(func(text: String) -> void: start_review_note(text))
	_notes_dock.text_saved.connect(func(identity: String, text: String) -> void:
		_notes.set_text(identity, text)
		_sync_notes_dock())
	_notes_dock.status_toggled.connect(func(identity: String) -> void:
		var note := _notes.find(identity)
		if not note.is_empty():
			_notes.set_status(identity, "open" if String(note.status) == "resolved" else "resolved")
		_sync_notes_dock())
	_notes_dock.delete_requested.connect(func(identity: String) -> void:
		_notes.remove(identity)
		_sync_notes_dock())
	_notes_dock.filter_changed.connect(func() -> void: _sync_notes_dock())
	_notes_dock.focus_requested.connect(func(identity: String) -> void:
		var note := _notes.find(identity)
		var root := _authoring_root()
		if not note.is_empty() and root != null:
			focus_camera_at(root.global_transform * (note.position as Vector3)))
	add_dock(_notes_dock)
	_build_capture_dialog()
	set_input_event_forwarding_always_enabled()
	set_force_draw_over_forwarding_enabled()
	scene_changed.connect(_on_scene_changed)
	get_editor_interface().get_selection().selection_changed.connect(_on_selection_changed)
	_sync_toolbar()


func _exit_tree() -> void:
	_grid.release()
	_time.disable()
	_markers.release()
	_walk.release()
	_draw.cancel()
	_walker.stop()
	_copy.cancel_drag()
	_area.cancel()
	_scatter.cancel()
	_plan_water.release()
	_concept.release()
	if is_instance_valid(_area_panel):
		_area_panel.queue_free()
	_area_panel = null
	if _performance.active:
		_performance.set_active(get_editor_interface().get_base_control(), null, false,
			_performance.distance)
	var selection := get_editor_interface().get_selection()
	if selection.selection_changed.is_connected(_on_selection_changed):
		selection.selection_changed.disconnect(_on_selection_changed)
	for pair: Array in [[_toolbar, EditorPlugin.CONTAINER_SPATIAL_EDITOR_MENU],
			[_selection_bar, EditorPlugin.CONTAINER_SPATIAL_EDITOR_BOTTOM]]:
		if pair[0] != null and is_instance_valid(pair[0]):
			remove_control_from_container(int(pair[1]), pair[0] as Control)
			(pair[0] as Control).queue_free()
	_toolbar = null
	_selection_bar = null
	if _minimap != null:
		remove_dock(_minimap)
		_minimap.queue_free()
		_minimap = null
	_notes.release()
	if _notes_dock != null:
		remove_dock(_notes_dock)
		_notes_dock.queue_free()
		_notes_dock = null
	if _time_button != null:
		remove_control_from_container(EditorPlugin.CONTAINER_SPATIAL_EDITOR_MENU, _time_button)
		_time_button.queue_free()
		_time_button = null
	for dialog: Node in [_capture_dialog, _capture_file_dialog]:
		if is_instance_valid(dialog):
			dialog.queue_free()
	_capture_dialog = null
	_capture_file_dialog = null
	var base := get_editor_interface().get_base_control()
	if base.has_meta(USABILITY_PLUGIN_META) and base.get_meta(USABILITY_PLUGIN_META) == self:
		base.remove_meta(USABILITY_PLUGIN_META)
	if _menu != null:
		remove_control_from_container(EditorPlugin.CONTAINER_SPATIAL_EDITOR_MENU, _menu)
		_menu.queue_free()
		_menu = null


func _handles(_object: Object) -> bool:
	return false


func _process(delta: float) -> void:
	if _hover_dirty:
		_hover_dirty = false
		_refresh_hover()
	var was_walking := _walker.is_walking()
	_walker.advance(delta)
	if was_walking and not _walker.is_walking():
		_status(_walker.last_message)
		update_overlays()
	_poll_elapsed += delta
	if _poll_elapsed >= POLL_SECONDS:
		_poll_elapsed = 0.0
		poll_overlays()
	_ui_elapsed += delta
	if _ui_elapsed >= UI_REFRESH_SECONDS:
		_ui_elapsed = 0.0
		_refresh_selection_bar()
		_update_minimap_state()
	if _minimap_countdown >= 0.0:
		_minimap_countdown -= delta
		if _minimap_countdown < 0.0:
			refresh_minimap()


## Refreshes the marker pins and the live walkability after edits settle.
func poll_overlays() -> void:
	var root := _authoring_root()
	if root == null:
		_markers.release()
		return
	if bool(Settings.value("markers/show")):
		_markers.refresh(root, bool(Settings.value("markers/labels")))
	else:
		_markers.release()
	var sculpt := _sculpt_plugin()
	var dragging := false
	if sculpt != null and sculpt.get("_sculpt") != null:
		dragging = bool(sculpt.get("_sculpt").call("is_dragging"))
	_walk.poll(dragging)
	_concept.sync()
	var notice := _walk.take_notice()
	if not notice.is_empty():
		_status(notice)
		update_overlays()
	_performance.refresh()
	_check_duplicate_ids(root)
	_sync_toolbar()


func _forward_3d_gui_input(camera: Camera3D, event: InputEvent) -> int:
	var result := _viewport_input(camera, event)
	if result == EditorPlugin.AFTER_GUI_INPUT_STOP and event is InputEventKey and is_inside_tree():
		# The 3D viewport returns on STOP without accepting a key, so Godot's own
		# shortcut for it (Ctrl+G grouping, F focus, Q/E tool modes) would run too.
		get_viewport().set_input_as_handled()
	return result


func _viewport_input(camera: Camera3D, event: InputEvent) -> int:
	if _authoring_root() == null:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if _notes.is_adding():
		var note_result := _notes.handle_input(camera, event)
		if note_result == EditorPlugin.AFTER_GUI_INPUT_STOP:
			_status(_notes.last_message)
			_sync_notes_dock()
		return note_result
	if _walker.active:
		if Settings.matches("focus_walker", event) and _walker.is_placed():
			focus_camera_at(_authoring_root().global_transform * _walker.position())
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if _walker.handle_input(camera, event):
			_status(_walker.last_message)
			_sync_toolbar()
			update_overlays()
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if event is InputEventMouseMotion:
			_note_hover(camera, (event as InputEventMouseMotion).position)
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if _scatter.is_active():
		var scatter_result := _scatter.handle_input(camera, event, get_undo_redo())
		if not _scatter.last_message.is_empty() and not event is InputEventMouseMotion:
			_status(_scatter.last_message)
		if event is InputEventMouseMotion:
			_note_hover(camera, (event as InputEventMouseMotion).position)
		update_overlays()
		return scatter_result
	if _area.is_active():
		var area_result := _area.handle_input(camera, event, get_undo_redo())
		if not _area.last_message.is_empty() and not event is InputEventMouseMotion:
			_status(_area.last_message)
		if event is InputEventMouseMotion:
			_note_hover(camera, (event as InputEventMouseMotion).position)
		update_overlays()
		return area_result
	if _copy.is_dragging() or _starts_copy_drag(camera, event):
		return _handle_copy_drag(camera, event)
	if event is InputEventKey and event.pressed and not event.echo and \
			_is_godot_duplicate(event as InputEventKey):
		# Godot's Ctrl+D keeps asset and record ids, which the snapshot rejects:
		# in the 3D view it duplicates placements in place with fresh ids instead.
		var root := _authoring_root()
		var selected := get_editor_interface().get_selection().get_selected_nodes()
		var placed := Tools.placements(root, selected)
		if not placed.is_empty() and placed.size() == selected.size():
			duplicate_selection(Vector3.ZERO)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
	if event is InputEventKey and event.pressed and not event.echo:
		for action: String in ["ungroup", "group", "duplicate_fresh", "play_test"]:
			if Settings.matches(action, event) and \
					(action != "group" or not (event as InputEventKey).shift_pressed):
				match action:
					"ungroup":
						ungroup_selection()
					"group":
						group_selection()
					"duplicate_fresh":
						duplicate_selection()
					"play_test":
						start_play_test()
				return EditorPlugin.AFTER_GUI_INPUT_STOP
	if event is InputEventMouseButton and event.pressed and \
			(event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT and \
			(event as InputEventMouseButton).double_click:
		# The editor's click that follows picks one object; the selection handler
		# then opens its group instead of expanding to all members.
		_opening_group_click = true
	if _draw.is_active():
		var drawn_before := _draw.points.size()
		var result := _draw.handle_input(camera, event, get_undo_redo())
		if not _draw.is_active() and drawn_before >= 2 and _draw.last_message.begins_with("Added"):
			_select_last_path()
		if _draw.last_message != "":
			_status(_draw.last_message)
		update_overlays()
		if event is InputEventMouseMotion:
			_hover_camera = camera
			_hover_position = (event as InputEventMouseMotion).position
			_hover_inside = true
			_hover_dirty = true
		return result
	if event is InputEventMouseMotion:
		_note_hover(camera, (event as InputEventMouseMotion).position)
	elif event is InputEventMouseButton or event is InputEventKey:
		# Placement adjustments (turn, lift, snap) change what the grid shows.
		_hover_dirty = true
	return EditorPlugin.AFTER_GUI_INPUT_PASS


func _note_hover(camera: Camera3D, position: Vector2) -> void:
	_hover_camera = camera
	_hover_position = position
	_hover_inside = true
	_hover_dirty = true


func _forward_3d_force_draw_over_viewport(overlay: Control) -> void:
	if _authoring_root() == null:
		return
	var font := overlay.get_theme_default_font()
	var font_size := overlay.get_theme_default_font_size()
	var line_height := font.get_height(font_size) + 6.0
	var bottom := overlay.size.y - line_height * 0.5
	var text := readout_text() if bool(Settings.value("viewport/show_cursor_readout")) else ""
	if not text.is_empty():
		var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
		var top := bottom - line_height
		overlay.draw_rect(Rect2(8.0, top, width + 16.0, line_height), Color(0.0, 0.0, 0.0, 0.55))
		overlay.draw_string(font, Vector2(16.0, top + line_height - 8.0), text,
			HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(0.72, 0.95, 0.86))
		bottom = top
	_draw_walkability_legend(overlay, font, font_size)
	_draw_duplicate_warning(overlay, font, font_size)
	# Drawing, placement and sculpt hints sit above the readout. Drawing them here
	# (this plugin force-draws) keeps them visible when nothing is selected.
	if _walker.active:
		PalettePlugin.draw_overlay_lines(overlay, _walker.hint_lines(), bottom)
		return
	if _area.is_active():
		PalettePlugin.draw_overlay_lines(overlay, _area.hint_lines(), bottom)
		return
	if _scatter.is_active():
		PalettePlugin.draw_overlay_lines(overlay, _scatter.hint_lines(), bottom)
		return
	if _copy.is_dragging():
		PalettePlugin.draw_overlay_lines(overlay, PackedStringArray([
			"Copying %d object%s: release to place, Esc cancels" % [_copy_count(),
				"" if _copy_count() == 1 else "s"]]), bottom)
		return
	if _draw.is_active():
		PalettePlugin.draw_overlay_lines(overlay, _draw.hint_lines(), bottom)
		return
	for plugin: Object in [_palette_plugin(), _sculpt_plugin()]:
		if plugin != null and plugin.has_method("overlay_lines"):
			var hints: PackedStringArray = plugin.call("overlay_lines")
			if not hints.is_empty():
				PalettePlugin.draw_overlay_lines(overlay, hints, bottom)
				return


func _draw_walkability_legend(overlay: Control, font: Font, font_size: int) -> void:
	var items: Array = _walk.legend() if _walk.is_active() else []
	if items.is_empty():
		return
	var title := "Walkability: %s" % ["", "published grid (exact)", "live suggestion",
		"changes since publish"][int(_walk_mode)]
	var line_height := font.get_height(font_size) + 4.0
	var width := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	for item: Array in items:
		width = maxf(width, font.get_string_size(String(item[0]), HORIZONTAL_ALIGNMENT_LEFT,
			-1, font_size).x + 22.0)
	var origin := Vector2(overlay.size.x - width - 28.0, 44.0)
	overlay.draw_rect(Rect2(origin, Vector2(width + 20.0, line_height * float(items.size() + 1) +
		8.0)), Color(0.0, 0.0, 0.0, 0.6))
	overlay.draw_string(font, origin + Vector2(10.0, line_height - 2.0), title,
		HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(0.95, 0.95, 0.95))
	for index in items.size():
		var item: Array = items[index]
		var top := origin.y + line_height * float(index + 1) + 4.0
		overlay.draw_rect(Rect2(origin.x + 10.0, top + 3.0, 12.0, 12.0), item[1] as Color)
		overlay.draw_string(font, Vector2(origin.x + 30.0, top + line_height - 6.0),
			String(item[0]), HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(0.9, 0.9, 0.9))


## The one-line status shown at the bottom-left of the 3D view.
func readout_text() -> String:
	if _hover_hit == null or _hover_info.is_empty():
		return ""
	var local: Vector3 = _hover_info.local
	var parts := PackedStringArray()
	parts.append("X %.2f  Z %.2f m" % [local.x, local.z])
	if bool(_hover_info.get("has_tile", false)):
		var tile: Vector2i = _hover_info.tile
		parts.append("tile %d, %d" % [tile.x, tile.y])
	parts.append("height %.2f m" % local.y)
	var walk := _walk.describe(local)
	if not walk.is_empty():
		parts.append(walk)
	var root := _authoring_root()
	if root != null:
		var count := Tools.placements(root,
			get_editor_interface().get_selection().get_selected_nodes()).size()
		if count > 0:
			parts.append("%d selected" % count)
	if _performance.active:
		parts.append("%d fps" % roundi(Engine.get_frames_per_second()))
	return "  ·  ".join(parts)


func hover_state() -> Dictionary:
	return {"hit": _hover_hit, "info": _hover_info.duplicate(true),
		"grid": _grid.node()}


## Runs a Map tools action on the current selection; returns how many changed.
func run_tool(id: int) -> int:
	var root := _authoring_root()
	if root == null:
		_toast("Open a map authoring scene first.")
		return 0
	var selection := get_editor_interface().get_selection().get_selected_nodes()
	match id:
		MenuId.GROUP:
			return 1 if not group_selection().is_empty() else 0
		MenuId.UNGROUP:
			return ungroup_selection()
		MenuId.DUPLICATE:
			return duplicate_selection().size()
		MenuId.FIX_DUPLICATE_IDS:
			return fix_duplicate_ids()
	if id == MenuId.SAVE_PREFAB:
		var palette := _palette_plugin()
		if palette == null:
			_toast("Enable the Map Asset Palette plugin to save prefabs.")
			return 0
		var result: Dictionary = palette.call("save_selection_as_prefab", "")
		if result.has("error"):
			_toast(String(result.error))
			return 0
		_toast("Saved prefab %s. Rename or delete it in %s." % [
			String(result.get("path", "")).get_file(), String(result.get("path", "")).get_base_dir()])
		return int(result.get("members", 0))
	var nodes := Tools.placements(root, selection)
	if nodes.is_empty():
		_toast("Select placed assets, scenery or gameplay markers first.")
		return 0
	var undo := get_undo_redo()
	var changed := 0
	match id:
		MenuId.DROP_TO_GROUND:
			changed = Tools.drop_to_ground(undo, root, nodes)
		MenuId.ROTATE_EACH:
			changed = Tools.rotate_each(undo, root, nodes, 90.0)
		MenuId.RANDOM_TURN:
			changed = Tools.randomize_turn(undo, root, nodes, _rng)
		MenuId.RANDOM_SIZE:
			var variation := float(Settings.value("placement/size_variation"))
			changed = Tools.randomize_size(undo, root, nodes,
				variation if variation > 0.0 else 0.15, _rng)
	if changed == 0 and id == MenuId.DROP_TO_GROUND:
		_toast("The selection already rests on the ground.")
	return changed


func _build_menu(popup: PopupMenu) -> void:
	popup.clear()
	var settings := Settings.editor_settings()
	_add_tool_item(popup, "Drop selection to ground", MenuId.DROP_TO_GROUND, "drop_to_ground",
		settings)
	_add_tool_item(popup, "Rotate each 90° (own pivot)", MenuId.ROTATE_EACH, "rotate_each",
		settings)
	popup.add_item("Random turn for each", MenuId.RANDOM_TURN)
	popup.add_item("Random size for each", MenuId.RANDOM_SIZE)
	popup.add_separator()
	_add_tool_item(popup, "Save selection as prefab", MenuId.SAVE_PREFAB, "save_prefab", settings)
	popup.add_item("Group selection (Ctrl+G in the 3D view)", MenuId.GROUP)
	popup.add_item("Ungroup (Ctrl+Shift+G)", MenuId.UNGROUP)
	_add_tool_item(popup, "Duplicate with fresh ids (or Alt+drag)", MenuId.DUPLICATE,
		"duplicate_fresh", settings)
	popup.add_item("Give duplicated copies fresh ids", MenuId.FIX_DUPLICATE_IDS)
	popup.add_separator("Cursor grid")
	popup.add_radio_check_item("Off", MenuId.GRID_OFF)
	popup.add_radio_check_item("While placing", MenuId.GRID_WHILE_PLACING)
	popup.add_radio_check_item("Always", MenuId.GRID_ALWAYS)
	popup.add_separator()
	popup.add_check_item("Cursor readout (metres, tile, height)", MenuId.READOUT)
	popup.add_separator("Gameplay markers")
	popup.add_check_item("Show markers (coloured pins)", MenuId.SHOW_MARKERS)
	popup.add_check_item("Marker labels", MenuId.MARKER_LABELS)
	popup.add_separator("Walkability overlay")
	popup.add_radio_check_item("Off", MenuId.WALK_OFF)
	popup.add_radio_check_item("Published grid (exact)", MenuId.WALK_PUBLISHED)
	popup.add_radio_check_item("Live suggestion from authoring", MenuId.WALK_LIVE)
	popup.add_radio_check_item("Changes since publish", MenuId.WALK_CHANGES)
	popup.add_separator("Paths")
	_add_tool_item(popup, "Draw road", MenuId.DRAW_ROAD, "draw_road", settings)
	_add_tool_item(popup, "Draw river", MenuId.DRAW_RIVER, "draw_river", settings)
	popup.add_check_item("Show the continent plan's water (read-only)", MenuId.PLAN_WATER)
	popup.add_check_item("Show the concept master on the terrain (reference)", MenuId.CONCEPT)
	popup.add_separator("Terrain and ground")
	popup.add_item("Paint ground regions…", MenuId.PAINT_GROUND)
	popup.add_item("Stamp plateaus…", MenuId.STAMP_PLATEAU)
	popup.add_item("Scatter the selected asset…", MenuId.SCATTER)
	popup.add_separator("Play and view")
	popup.add_check_item("Play test: walk the territory", MenuId.PLAY_TEST)
	popup.add_check_item("Low spec view (half resolution, far assets hidden)", MenuId.LOW_SPEC)
	popup.add_separator()
	popup.add_item("Time of day preview…", MenuId.TIME_OF_DAY)
	popup.add_item("Capture top-down image…", MenuId.CAPTURE_TOP_DOWN)
	popup.id_pressed.connect(_on_menu_id)


func _add_tool_item(popup: PopupMenu, text: String, id: int, shortcut_key: String,
		settings: EditorSettings) -> void:
	popup.add_item(text, id)
	var path := Settings.PREFIX + shortcut_key
	if settings != null and settings.has_shortcut(path):
		popup.set_item_shortcut(popup.get_item_index(id), settings.get_shortcut(path), true)


func _sync_menu() -> void:
	var popup := _menu.get_popup()
	var mode := int(Settings.value("grid/cursor_grid"))
	popup.set_item_checked(popup.get_item_index(MenuId.GRID_OFF), mode == Settings.CursorGrid.OFF)
	popup.set_item_checked(popup.get_item_index(MenuId.GRID_WHILE_PLACING),
		mode == Settings.CursorGrid.WHILE_PLACING)
	popup.set_item_checked(popup.get_item_index(MenuId.GRID_ALWAYS),
		mode == Settings.CursorGrid.ALWAYS)
	popup.set_item_checked(popup.get_item_index(MenuId.READOUT),
		bool(Settings.value("viewport/show_cursor_readout")))
	popup.set_item_checked(popup.get_item_index(MenuId.SHOW_MARKERS),
		bool(Settings.value("markers/show")))
	popup.set_item_checked(popup.get_item_index(MenuId.MARKER_LABELS),
		bool(Settings.value("markers/labels")))
	for pair: Array in [[MenuId.WALK_OFF, Walkability.Mode.OFF],
			[MenuId.WALK_PUBLISHED, Walkability.Mode.PUBLISHED],
			[MenuId.WALK_LIVE, Walkability.Mode.LIVE], [MenuId.WALK_CHANGES, Walkability.Mode.CHANGES]]:
		popup.set_item_checked(popup.get_item_index(int(pair[0])), _walk_mode == int(pair[1]))
	popup.set_item_checked(popup.get_item_index(MenuId.PLAY_TEST), _walker.active)
	popup.set_item_checked(popup.get_item_index(MenuId.LOW_SPEC), _performance.active)
	popup.set_item_checked(popup.get_item_index(MenuId.PLAN_WATER), _plan_water_on)
	popup.set_item_checked(popup.get_item_index(MenuId.CONCEPT), _concept_on)


func _on_menu_id(id: int) -> void:
	match id:
		MenuId.GRID_OFF:
			Settings.set_value("grid/cursor_grid", Settings.CursorGrid.OFF)
		MenuId.GRID_WHILE_PLACING:
			Settings.set_value("grid/cursor_grid", Settings.CursorGrid.WHILE_PLACING)
		MenuId.GRID_ALWAYS:
			Settings.set_value("grid/cursor_grid", Settings.CursorGrid.ALWAYS)
		MenuId.READOUT:
			Settings.set_value("viewport/show_cursor_readout",
				not bool(Settings.value("viewport/show_cursor_readout")))
		MenuId.SHOW_MARKERS:
			Settings.set_value("markers/show", not bool(Settings.value("markers/show")))
			poll_overlays()
		MenuId.MARKER_LABELS:
			Settings.set_value("markers/labels", not bool(Settings.value("markers/labels")))
			poll_overlays()
		MenuId.WALK_OFF:
			set_walkability_mode(Walkability.Mode.OFF)
		MenuId.WALK_PUBLISHED:
			set_walkability_mode(Walkability.Mode.PUBLISHED)
		MenuId.WALK_LIVE:
			set_walkability_mode(Walkability.Mode.LIVE)
		MenuId.WALK_CHANGES:
			set_walkability_mode(Walkability.Mode.CHANGES)
		MenuId.DRAW_ROAD:
			start_path_drawing("road")
		MenuId.DRAW_RIVER:
			start_path_drawing("river")
		MenuId.PLAY_TEST:
			if _walker.active:
				stop_play_test()
			else:
				start_play_test()
		MenuId.LOW_SPEC:
			set_low_spec(not _performance.active)
		MenuId.PLAN_WATER:
			set_plan_water(not _plan_water_on)
		MenuId.CONCEPT:
			set_concept_overlay(not _concept_on)
		MenuId.PAINT_GROUND:
			open_area_panel("ground")
		MenuId.STAMP_PLATEAU:
			open_area_panel("plateau")
		MenuId.SCATTER:
			open_area_panel("scatter")
		MenuId.TIME_OF_DAY:
			_show_time_panel()
		MenuId.CAPTURE_TOP_DOWN:
			_show_capture_dialog()
		_:
			run_tool(id)
	_refresh_hover()


func _refresh_hover() -> void:
	var root := _authoring_root()
	if root == null or _hover_camera == null or not is_instance_valid(_hover_camera) or \
			not _hover_inside:
		_clear_hover()
		return
	var origin := _hover_camera.project_ray_origin(_hover_position)
	var direction := _hover_camera.project_ray_normal(_hover_position)
	_hover_hit = Probe.ray_hit(root, origin, direction, RAY_LENGTH)
	if _hover_hit is Vector3:
		_hover_info = Probe.describe_point(root, _hover_hit as Vector3)
	else:
		_hover_info = {}
	_update_grid(root)
	update_overlays()


func _update_grid(root: Node3D) -> void:
	var mode := int(Settings.value("grid/cursor_grid"))
	var placing := false
	var palette := _palette_plugin()
	if palette != null:
		placing = bool((palette.call("placement_state") as Dictionary).get("armed", false))
	var show := _hover_hit is Vector3 and (mode == Settings.CursorGrid.ALWAYS or
		(mode == Settings.CursorGrid.WHILE_PLACING and placing))
	if not show:
		_grid.hide()
		return
	var snap_on := bool(Settings.value("placement/snap_to_grid"))
	_grid.show_at(root, _hover_hit as Vector3, float(Settings.value("grid/step")),
		int(Settings.value("grid/radius_cells")),
		Color(1.0, 0.86, 0.45, 0.9) if snap_on else Color(0.92, 0.96, 1.0, 0.85),
		snap_on and placing)


func _clear_hover() -> void:
	_hover_hit = null
	_hover_info = {}
	_hover_inside = false
	_grid.hide()
	if is_inside_tree():
		update_overlays()


func _sculpt_plugin() -> Object:
	var base := get_editor_interface().get_base_control()
	if not base.has_meta(SCULPT_PLUGIN_META):
		return null
	var value: Variant = base.get_meta(SCULPT_PLUGIN_META)
	return value if value is Object and is_instance_valid(value) else null


func _palette_plugin() -> Object:
	var base := get_editor_interface().get_base_control()
	if not base.has_meta(ASSET_PLUGIN_META):
		return null
	var value: Variant = base.get_meta(ASSET_PLUGIN_META)
	return value if value is Object and is_instance_valid(value) else null


func _authoring_root() -> Node3D:
	if not is_inside_tree():
		return null
	var root := get_editor_interface().get_edited_scene_root()
	if root is Node3D and root.has_method("authoring_ground_intersection"):
		return root as Node3D
	return null


func _toast(message: String) -> void:
	var toaster := get_editor_interface().get_editor_toaster()
	if toaster != null:
		toaster.push_toast(message)
	else:
		print(message)


func _on_scene_changed(root: Node) -> void:
	_clear_hover()
	_draw.cancel()
	_walker.stop()
	_copy.cancel_drag()
	_area.cancel()
	_scatter.cancel()
	_open_group = ""
	_remember_duplicate_baseline(_authoring_root())
	_markers.release()
	if bool(Settings.value("performance/low_spec")) or _performance.active:
		_performance.set_active(get_editor_interface().get_base_control(), _authoring_root(),
			bool(Settings.value("performance/low_spec")),
			float(Settings.value("performance/far_asset_metres")))
	if _minimap != null:
		_minimap.clear("Rendering…" if _authoring_root() != null else
			"Open a territory to see its minimap.")
		_minimap_countdown = 1.0 if _authoring_root() != null else -1.0
	var mode := _walk_mode
	_walk.release()
	if mode != Walkability.Mode.OFF:
		set_walkability_mode(mode)
	if _plan_water_on:
		set_plan_water(true)
	if _concept_on:
		set_concept_overlay(true)
	var opened := _authoring_root()
	if opened != null:
		_notes.open(opened)
	else:
		_notes.release()
	_sync_notes_dock()
	poll_overlays()
	# The preview follows the open scene; a scene with saved lighting turns it off.
	if _time.is_active() or (_time_toggle != null and _time_toggle.button_pressed):
		set_time_preview(true)


# Time of day ---------------------------------------------------------------

## Turns the lighting preview on or off, optionally at a game minute (0-360,
## noon 180). Returns whether the preview is showing afterwards.
func set_time_preview(enabled: bool, game_minute: float = NAN) -> bool:
	if not is_nan(game_minute):
		Settings.set_value("time_of_day/minute", fposmod(game_minute, 360.0))
	var minute := float(Settings.value("time_of_day/minute"))
	var active := false
	if enabled:
		var root := _authoring_root()
		if _time.is_active() and root != null and _time.nodes().get_parent() == root:
			_time.set_minute(minute)
			active = true
		else:
			active = _time.enable(root, minute)
	else:
		_time.disable()
		_time.last_message = "Preview off: the editor's own lighting is shown."
	_sync_time_controls()
	return active


func time_preview_state() -> Dictionary:
	return {"active": _time.is_active(), "minute": _time.minute(), "nodes": _time.nodes(),
		"manifest": _time.manifest_path, "message": _time.last_message}


func _build_time_controls() -> void:
	_time_button = Button.new()
	_time_button.flat = true
	_time_button.tooltip_text = ("Preview this territory's in-game lighting at any hour. " +
		"Editor only: nothing is saved or baked.")
	_time_button.pressed.connect(_show_time_panel)
	_time_panel = PopupPanel.new()
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(360, 0)
	column.add_theme_constant_override("separation", 6)
	_time_panel.add_child(column)
	_time_toggle = CheckButton.new()
	_time_toggle.text = "Preview time of day"
	_time_toggle.toggled.connect(func(on: bool) -> void: set_time_preview(on))
	column.add_child(_time_toggle)
	var row := HBoxContainer.new()
	_time_slider = HSlider.new()
	_time_slider.min_value = 0.0
	_time_slider.max_value = 359.75
	_time_slider.step = 0.25
	_time_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_time_slider.value_changed.connect(func(value: float) -> void:
		set_time_preview(_time_toggle.button_pressed or _time.is_active(), value))
	row.add_child(_time_slider)
	_time_label = Label.new()
	_time_label.custom_minimum_size = Vector2(110, 0)
	row.add_child(_time_label)
	column.add_child(row)
	var presets := HBoxContainer.new()
	for preset: String in TimeOfDay.PRESETS:
		var button := Button.new()
		button.text = preset
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.pressed.connect(func() -> void:
			set_time_preview(true, float(TimeOfDay.PRESETS[preset])))
		presets.add_child(button)
	column.add_child(presets)
	_time_status = Label.new()
	_time_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_time_status.custom_minimum_size = Vector2(340, 0)
	column.add_child(_time_status)
	get_editor_interface().get_base_control().add_child(_time_panel)
	_sync_time_controls()


func _show_time_panel() -> void:
	_sync_time_controls()
	var anchor := _time_button.get_screen_position() + Vector2(0.0, _time_button.size.y)
	_time_panel.popup(Rect2i(Vector2i(anchor), Vector2i(360, 0)))


func _sync_time_controls() -> void:
	if _time_button == null:
		return
	var minute := float(Settings.value("time_of_day/minute"))
	var active := _time.is_active()
	_time_button.text = "Time: %s" % TimeOfDay.describe(minute) if active else "Time: editor light"
	_time_toggle.set_pressed_no_signal(active)
	_time_slider.set_value_no_signal(minute)
	_time_label.text = TimeOfDay.describe(minute)
	var source := _time.manifest_path.get_file() if not _time.manifest_path.is_empty() \
		else "a plain clear-day fallback"
	_time_status.text = _time.last_message if not active else \
		"%s\nLighting from %s (%s)." % [_time.last_message,
			_time.manifest_path.get_base_dir().get_file() + "/" + source \
				if not _time.manifest_path.is_empty() else source,
			"same curve as the game's day/night cycle"]


# Top-down capture ----------------------------------------------------------

## Captures the open territory from above; see top_down_capture.gd. While no
## time preview is on, the territory is lit at noon from its manifest for the
## shot and the preview is switched off again afterwards.
func capture_top_down(path: String, pixels_per_metre: float,
		include_references: bool, clip_to_ownership: bool = true) -> Dictionary:
	var root := _authoring_root()
	if root == null:
		return {"error": "Open a map authoring scene first."}
	if _capturing:
		return {"error": "A capture is already running."}
	_capturing = true
	var temporary_light := not _time.is_active() and TimeOfDay.saved_lighting(root).is_empty()
	if temporary_light:
		_time.enable(root, 180.0)
	var label := ("manifest %s" % TimeOfDay.describe(_time.minute())) if _time.is_active() \
		else "scene lighting"
	var result: Dictionary = await TopDown.capture(root, path, pixels_per_metre,
		include_references, label, clip_to_ownership)
	if temporary_light:
		_time.disable()
	_capturing = false
	_sync_time_controls()
	return result


func _build_capture_dialog() -> void:
	_capture_dialog = ConfirmationDialog.new()
	_capture_dialog.title = "Capture top-down image"
	_capture_dialog.ok_button_text = "Capture"
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(460, 0)
	_capture_dialog.add_child(column)
	var path_row := HBoxContainer.new()
	_capture_path = LineEdit.new()
	_capture_path.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	path_row.add_child(_capture_path)
	var browse := Button.new()
	browse.text = "Browse…"
	browse.pressed.connect(func() -> void:
		_capture_file_dialog.current_path = _capture_path.text
		_capture_file_dialog.popup_file_dialog())
	path_row.add_child(browse)
	column.add_child(_labelled("Save PNG to", path_row))
	var options := HBoxContainer.new()
	_capture_ppm = SpinBox.new()
	_capture_ppm.min_value = 0.25
	_capture_ppm.max_value = 8.0
	_capture_ppm.step = 0.25
	_capture_ppm.suffix = "px/m"
	_capture_ppm.value_changed.connect(func(_value: float) -> void: _update_capture_estimate())
	options.add_child(_capture_ppm)
	_capture_references = CheckBox.new()
	_capture_references.text = "Include neighbour references"
	options.add_child(_capture_references)
	column.add_child(_labelled("Resolution", options))
	_capture_clip = CheckBox.new()
	_capture_clip.text = "Only the land this territory owns (clip to its ownership polygon)"
	_capture_clip.toggled.connect(func(_on: bool) -> void: _update_capture_estimate())
	column.add_child(_capture_clip)
	_capture_estimate = Label.new()
	_capture_estimate.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_capture_estimate)
	_capture_dialog.confirmed.connect(_run_capture_from_dialog)
	_capture_file_dialog = EditorFileDialog.new()
	_capture_file_dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	_capture_file_dialog.access = EditorFileDialog.ACCESS_FILESYSTEM
	_capture_file_dialog.filters = PackedStringArray(["*.png ; PNG image"])
	_capture_file_dialog.file_selected.connect(func(chosen: String) -> void:
		_capture_path.text = chosen)
	var base := get_editor_interface().get_base_control()
	base.add_child(_capture_dialog)
	base.add_child(_capture_file_dialog)


func _labelled(text: String, control: Control) -> Control:
	var row := VBoxContainer.new()
	var label := Label.new()
	label.text = text
	row.add_child(label)
	row.add_child(control)
	return row


func _show_capture_dialog() -> void:
	var root := _authoring_root()
	if root == null:
		_toast("Open a map authoring scene first.")
		return
	var region := String(root.get("region_id")) if root.get("region_id") != null \
		else String(root.name).to_snake_case()
	var folder := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES).path_join("Eloria map captures")
	_capture_path.text = folder.path_join("%s-top-down.png" % region)
	_capture_ppm.set_value_no_signal(float(Settings.value("capture/pixels_per_metre")))
	_capture_references.button_pressed = bool(Settings.value("capture/include_references"))
	_capture_clip.set_pressed_no_signal(bool(Settings.value("capture/clip_to_ownership")))
	_update_capture_estimate()
	_capture_dialog.popup_centered()


func _update_capture_estimate() -> void:
	var root := _authoring_root()
	if root == null or _capture_estimate == null:
		return
	var polygon := TopDown.ownership_polygons_local(root) if _capture_clip.button_pressed \
		else []
	var framing := TopDown.plan(root, _capture_ppm.value, polygon)
	if framing.has("error"):
		_capture_estimate.text = String(framing.error)
		return
	if _capture_clip.button_pressed and polygon.is_empty():
		_capture_estimate.text = "No ownership polygon for this scene; the whole terrain grid is captured. "
	else:
		_capture_estimate.text = ""
	var rect: Rect2 = framing.rect
	_capture_estimate.text += ("%d × %d px covering %.0f × %.0f m, north up. A JSON sidecar " +
		"records the bounds and metres per pixel. Lighting: %s.") % [framing.size.x,
		framing.size.y, rect.size.x, rect.size.y,
		TimeOfDay.describe(_time.minute()) + " preview" if _time.is_active() \
			else "noon from the territory manifest"]


func _run_capture_from_dialog() -> void:
	Settings.set_value("capture/pixels_per_metre", _capture_ppm.value)
	Settings.set_value("capture/include_references", _capture_references.button_pressed)
	Settings.set_value("capture/clip_to_ownership", _capture_clip.button_pressed)
	var result: Dictionary = await capture_top_down(_capture_path.text, _capture_ppm.value,
		_capture_references.button_pressed, _capture_clip.button_pressed)
	if result.has("error"):
		_toast("Top-down capture failed: %s" % String(result.error))
	else:
		_toast("Saved %s (%d × %d) and its .json sidecar." % [String(result.path),
			result.size.x, result.size.y])


# Markers, walkability and paths --------------------------------------------

## Shows a walkability mode (see walkability_overlay.gd) on the open territory.
func set_walkability_mode(mode: int) -> bool:
	_walk_mode = mode
	var shown := _walk.set_mode(_authoring_root(), mode)
	if mode != Walkability.Mode.OFF and not shown:
		_walk_mode = Walkability.Mode.OFF
	if not _walk.last_message.is_empty() and mode != Walkability.Mode.OFF:
		_status(_walk.last_message)
	update_overlays()
	return shown


## Shows or hides the continent plan's rivers and lakes over the open territory
## (see plan_water.gd). Returns whether they are showing.
func set_plan_water(visible: bool) -> bool:
	_plan_water_on = visible
	_plan_water.release()
	var root := _authoring_root()
	if not visible or root == null:
		return false
	var shown := _plan_water.show_on(root)
	_status(_plan_water.last_message)
	return shown


func plan_water() -> RefCounted:
	return _plan_water


## Shows or hides the concept master on the terrain (see concept_master.gd).
## Returns whether it is showing.
func set_concept_overlay(visible: bool) -> bool:
	_concept_on = visible
	_concept.release()
	var root := _authoring_root()
	if not visible or root == null:
		return false
	var shown := _concept.show_on(root)
	_status(_concept.last_message)
	if not shown:
		# Nothing to show here: switch off rather than retry on every scene.
		_concept_on = false
		_toast(_concept.last_message)
	return shown


func concept_overlay() -> RefCounted:
	return _concept


## Waits for a click in the 3D view to pin a review note with `text` (see
## review_notes.gd). Returns whether it is waiting.
func start_review_note(text: String) -> bool:
	if _notes.path.is_empty() and _authoring_root() != null:
		_notes.open(_authoring_root())
	var armed := _notes.arm_add(text)
	_status(_notes.last_message)
	if armed:
		get_editor_interface().set_main_screen_editor("3D")
	_sync_notes_dock()
	return armed


func review_notes() -> RefCounted:
	return _notes


func review_notes_dock() -> Control:
	return _notes_dock


func _sync_notes_dock() -> void:
	if _notes_dock != null:
		_notes_dock.show_notes(_notes.notes, _notes.last_message, _notes.can_write())
	_notes.set_shown(_notes_dock.showing() if _notes_dock != null else "all")
	_update_minimap_state()


func rebuild_walkability() -> void:
	_walk.rebuild()
	update_overlays()


func walkability_state() -> Dictionary:
	return {"mode": _walk_mode, "active": _walk.is_active(), "node": _walk.node(),
		"live": _walk.live_data(), "published": _walk.published_data(),
		"message": _walk.last_message}


func walkability_describe(local: Vector3) -> String:
	return _walk.describe(local)


func marker_overlay_state() -> Dictionary:
	return {"node": _markers.node(), "labels": _markers.label_count()}


## Starts click-to-draw for a "road" or "river"; placement and sculpting stop.
func start_path_drawing(kind: String) -> bool:
	var root := _authoring_root()
	var palette := _palette_plugin()
	if palette != null and palette.has_method("cancel_placement_for_terrain_sculpt"):
		palette.call("cancel_placement_for_terrain_sculpt")
	var sculpt := _sculpt_plugin()
	if sculpt != null and sculpt.has_method("deactivate_terrain_sculpt"):
		sculpt.call("deactivate_terrain_sculpt")
	_walker.stop()
	_area.cancel()
	_scatter.cancel()
	var started := _draw.start(root, kind, _ownership_polygon(root))
	_status(_draw.last_message)
	if started:
		get_editor_interface().set_main_screen_editor("3D")
	update_overlays()
	return started


## Called by placement and sculpting when they take the viewport: stops this
## plugin's click tools (path drawing and the play-test walker).
func cancel_path_drawing() -> void:
	if _draw.is_active():
		_draw.cancel()
		update_overlays()
	if _walker.active:
		stop_play_test()
	if _area.is_active():
		_area.cancel()
		update_overlays()
	if _scatter.is_active():
		_scatter.cancel()
		update_overlays()


func path_draw_tool() -> RefCounted:
	return _draw


func _select_last_path() -> void:
	var root := _authoring_root()
	if root == null:
		return
	var newest: Node = null
	for container_name in ["Roads", "Rivers"]:
		var container := root.get_node_or_null(container_name)
		if container != null and container.get_child_count() > 0:
			var candidate := container.get_child(container.get_child_count() - 1)
			if String(candidate.name) in _draw.last_message:
				newest = candidate
	if newest == null:
		return
	var selection := get_editor_interface().get_selection()
	selection.clear()
	selection.add_node(newest)
	get_editor_interface().edit_node(newest)


func _status(message: String) -> void:
	var palette := _palette_plugin()
	var dock: Object = palette.get("_dock") if palette != null else null
	if dock != null and dock.has_method("show_message"):
		dock.call("show_message", message)


# Groups and copies ---------------------------------------------------------

## Groups the selected placements (see group_tools.gd); returns the group id.
func group_selection() -> String:
	var root := _authoring_root()
	if root == null:
		return ""
	var nodes := Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes())
	if nodes.size() < 2:
		_toast("Select two or more placed objects to group them.")
		return ""
	var identity := GroupTools.group(get_undo_redo(), root, nodes)
	_open_group = ""
	_status("Grouped %d objects as %s. Clicking one selects all; double-click to pick one." % [
		nodes.size(), identity])
	_refresh_selection_bar()
	return identity


## Ungroups every group the selection touches; returns how many objects changed.
func ungroup_selection() -> int:
	var root := _authoring_root()
	if root == null:
		return 0
	var changed := GroupTools.ungroup(get_undo_redo(), root,
		Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes()))
	if changed == 0:
		_toast("The selection is not grouped.")
	else:
		_open_group = ""
		_status("Ungrouped %d objects." % changed)
	_refresh_selection_bar()
	return changed


## Copies the selection with fresh ids `offset` away (default: one grid step
## east and south) as one undo step, and selects the copies.
func duplicate_selection(offset: Vector3 = Vector3.INF) -> Array[Node3D]:
	var root := _authoring_root()
	var copies: Array[Node3D] = []
	if root == null:
		return copies
	var nodes := Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes())
	if nodes.is_empty():
		_toast("Select placed assets, scenery or gameplay markers first.")
		return copies
	if not offset.is_finite():
		var step := maxf(float(Settings.value("grid/step")), 1.0)
		offset = root.global_transform.basis * Vector3(step, 0.0, step)
	copies = GroupTools.commit_copies(get_undo_redo(), root, nodes, offset)
	_select(copies)
	_status(_copied_message(copies))
	return copies


## Gives the copies among objects that share an id fresh ids (see
## group_tools.gd fix_duplicate_ids); originals keep theirs.
func fix_duplicate_ids() -> int:
	var root := _authoring_root()
	if root == null:
		return 0
	var fixed := GroupTools.fix_duplicate_ids(get_undo_redo(), root,
		get_editor_interface().get_selection().get_selected_nodes(), _baseline_duplicates)
	_check_duplicate_ids(root)
	if fixed == 0:
		_toast("No placed objects share an id.")
	else:
		_status("Gave %d duplicated object%s fresh ids; the originals kept theirs." % [fixed,
			"" if fixed == 1 else "s"])
	update_overlays()
	return fixed


func duplicate_id_groups() -> Array[Dictionary]:
	return _duplicate_groups


## Records the ids a scene already shares when it opens, so only duplicates
## made in this session are reported.
func _remember_duplicate_baseline(root: Node3D) -> void:
	_baseline_duplicates = {}
	_duplicate_signature = ""
	_baseline_root_id = root.get_instance_id() if root != null else 0
	for group: Dictionary in GroupTools.duplicate_ids(root):
		for node: Node in group.nodes:
			_baseline_duplicates[node.get_instance_id()] = true


func _check_duplicate_ids(root: Node3D) -> void:
	if root != null and root.get_instance_id() != _baseline_root_id:
		_remember_duplicate_baseline(root)
	_duplicate_groups = []
	for group: Dictionary in GroupTools.duplicate_ids(root):
		if (group.nodes as Array).any(func(node: Node) -> bool:
				return not _baseline_duplicates.has(node.get_instance_id())):
			_duplicate_groups.append(group)
	var signature := ",".join(PackedStringArray(_duplicate_groups.map(func(group: Dictionary) -> String:
		return "%s:%s:%d" % [group.kind, group.id, (group.nodes as Array).size()])))
	if signature == _duplicate_signature:
		return
	_duplicate_signature = signature
	if not _duplicate_groups.is_empty():
		var plural := _duplicate_groups.size() != 1
		_toast(("%d placed object id%s now appear%s more than once (Godot's Ctrl+D copies ids, " +
			"and the bake rejects that). Use Map tools > Give duplicated copies fresh ids, or undo.") % [
			_duplicate_groups.size(), "s" if plural else "", "" if plural else "s"])
	update_overlays()


func _draw_duplicate_warning(overlay: Control, font: Font, font_size: int) -> void:
	if _duplicate_groups.is_empty():
		return
	var names := PackedStringArray()
	for group: Dictionary in _duplicate_groups.slice(0, 3):
		names.append(String(group.id))
	var text := "%d shared id%s (%s%s): Map tools > Give duplicated copies fresh ids" % [
		_duplicate_groups.size(), "" if _duplicate_groups.size() == 1 else "s", ", ".join(names),
		"…" if _duplicate_groups.size() > 3 else ""]
	var line_height := font.get_height(font_size) + 6.0
	var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	overlay.draw_rect(Rect2(8.0, 40.0, width + 16.0, line_height), Color(0.25, 0.12, 0.0, 0.8))
	overlay.draw_string(font, Vector2(16.0, 40.0 + line_height - 8.0), text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(1.0, 0.78, 0.35))


func _is_godot_duplicate(event: InputEventKey) -> bool:
	var settings := Settings.editor_settings()
	for path: String in ["scene_tree/duplicate", "editor/duplicate"]:
		if settings != null and settings.has_shortcut(path):
			return settings.is_shortcut(path, event)
	return event.keycode == KEY_D and event.ctrl_pressed and not event.shift_pressed and \
		not event.alt_pressed


func _copied_message(copies: Array) -> String:
	var note := GroupTools.copy_review_note(copies)
	return "Copied %d object%s with fresh ids.%s" % [copies.size(),
		"" if copies.size() == 1 else "s", (" " + note + ".") if not note.is_empty() else ""]


func copy_drag_tool() -> RefCounted:
	return _copy


func open_group() -> String:
	return _open_group


## Lets single members of `group_id` be picked until the selection leaves it.
func set_open_group(group_id: String) -> void:
	_open_group = group_id
	_refresh_selection_bar()


func _copy_count() -> int:
	var ghost := _copy.ghost()
	return ghost.get_child_count() if ghost != null else 0


## Alt+press on a selected object starts a copy-drag (not while placing).
func _starts_copy_drag(camera: Camera3D, event: InputEvent) -> bool:
	if not event is InputEventMouseButton:
		return false
	var button := event as InputEventMouseButton
	if not button.pressed or button.button_index != MOUSE_BUTTON_LEFT or not button.alt_pressed or \
			button.ctrl_pressed or button.shift_pressed or button.meta_pressed:
		return false
	var palette := _palette_plugin()
	if palette != null and bool((palette.call("placement_state") as Dictionary).get("armed", false)):
		return false
	var root := _authoring_root()
	var nodes := Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes())
	if nodes.is_empty():
		return false
	var hit: Variant = Probe.ray_hit(root, camera.project_ray_origin(button.position),
		camera.project_ray_normal(button.position), RAY_LENGTH)
	if not hit is Vector3 or not GroupTools.hits_selection(nodes, hit as Vector3):
		return false
	_copy.begin_drag(root, nodes, hit as Vector3)
	return true


func _handle_copy_drag(camera: Camera3D, event: InputEvent) -> int:
	var root := _authoring_root()
	if event is InputEventKey and event.pressed and (event as InputEventKey).keycode == KEY_ESCAPE:
		_copy.cancel_drag()
		update_overlays()
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	var position := Vector2.INF
	if event is InputEventMouse:
		position = (event as InputEventMouse).position
	if position.is_finite() and not (event is InputEventMouseButton and event.pressed):
		var hit: Variant = Probe.ray_hit(root, camera.project_ray_origin(position),
			camera.project_ray_normal(position), RAY_LENGTH)
		if hit is Vector3:
			var ground := hit as Vector3
			if bool(Settings.value("placement/snap_to_grid")):
				ground = _snap_offset_target(ground)
			_copy.update_drag(ground)
	if event is InputEventMouseButton and not event.pressed and \
			(event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		var copies := _copy.finish_drag(get_undo_redo())
		if not copies.is_empty():
			_select(copies)
			_status(_copied_message(copies))
	update_overlays()
	return EditorPlugin.AFTER_GUI_INPUT_STOP if event is InputEventMouse else \
		EditorPlugin.AFTER_GUI_INPUT_PASS


## With grid snap on, the drag moves in whole grid steps from where it began.
func _snap_offset_target(ground: Vector3) -> Vector3:
	var step := float(Settings.value("grid/step"))
	var start: Vector3 = _copy.get("_drag_start")
	if not start.is_finite() or step <= 0.0:
		return ground
	return Vector3(start.x + roundf((ground.x - start.x) / step) * step, ground.y,
		start.z + roundf((ground.z - start.z) / step) * step)


func _select(nodes: Array[Node3D]) -> void:
	var selection := get_editor_interface().get_selection()
	_selection_guard = true
	selection.clear()
	for node in nodes:
		selection.add_node(node)
	_selection_guard = false


## Completes groups in the selection, or opens one after a double-click.
func _on_selection_changed() -> void:
	var root := _authoring_root()
	if root == null or _selection_guard or _focusing:
		return
	var selection := get_editor_interface().get_selection()
	var nodes := selection.get_selected_nodes()
	if _opening_group_click:
		_opening_group_click = false
		var picked := Tools.placements(root, nodes)
		if picked.size() == 1 and not GroupTools.group_of(picked[0]).is_empty():
			_open_group = GroupTools.group_of(picked[0])
			_status("Editing group %s member by member; select outside it to close it." % _open_group)
			_refresh_selection_bar()
			return
	if not _open_group.is_empty():
		var inside := false
		for node in nodes:
			if node is Node and GroupTools.group_of(node as Node) == _open_group:
				inside = true
				break
		if not inside:
			_open_group = ""
	var expanded := GroupTools.expand(root, nodes, _open_group)
	if expanded.size() > nodes.size():
		_selection_guard = true
		for node in expanded:
			if not node in nodes:
				selection.add_node(node)
		_selection_guard = false
	_refresh_selection_bar()


# Selection bar and toolbar -------------------------------------------------

func selection_bar() -> Control:
	return _selection_bar


func toolbar() -> Control:
	return _toolbar


func _refresh_selection_bar() -> void:
	if _selection_bar == null:
		return
	var root := _authoring_root()
	if root == null:
		_selection_bar.show_summary({}, false, "")
		return
	var nodes := Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes())
	var grouped := false
	for node in nodes:
		if not GroupTools.group_of(node).is_empty():
			grouped = true
			break
	_selection_bar.show_summary(Tools.summary(root, nodes), grouped, _open_group)


func _on_bar_field_edited(field: String, value: float) -> void:
	var root := _authoring_root()
	if root == null:
		return
	var nodes := Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes())
	Tools.apply_field(get_undo_redo(), root, nodes, field, value)
	_refresh_selection_bar()


func _on_bar_tool(tool: String) -> void:
	match tool:
		"drop":
			run_tool(MenuId.DROP_TO_GROUND)
		"rotate":
			run_tool(MenuId.ROTATE_EACH)
		"copy":
			duplicate_selection()
		"group":
			group_selection()
		"ungroup":
			ungroup_selection()
		"open_group":
			var root := _authoring_root()
			if root != null:
				for node in Tools.placements(root,
						get_editor_interface().get_selection().get_selected_nodes()):
					if not GroupTools.group_of(node).is_empty():
						set_open_group(GroupTools.group_of(node))
						_status("Editing group %s: click single members; select outside it to close." %
							_open_group)
						break
		"prefab":
			run_tool(MenuId.SAVE_PREFAB)
	_refresh_selection_bar()


func _on_toolbar_toggled(option: String, on: bool) -> void:
	match option:
		"grid":
			Settings.set_value("grid/cursor_grid",
				Settings.CursorGrid.ALWAYS if on else Settings.CursorGrid.WHILE_PLACING)
		"snap":
			Settings.set_value("placement/snap_to_grid", on)
		"pins":
			Settings.set_value("markers/show", on)
			poll_overlays()
		"play":
			if on:
				start_play_test()
			else:
				stop_play_test()
		"low_spec":
			set_low_spec(on)
	_sync_toolbar()
	_refresh_hover()


func _sync_toolbar() -> void:
	if _toolbar == null:
		return
	_toolbar.sync({
		"grid": int(Settings.value("grid/cursor_grid")) == Settings.CursorGrid.ALWAYS,
		"snap": bool(Settings.value("placement/snap_to_grid")),
		"pins": bool(Settings.value("markers/show")),
		"play": _walker.active,
		"low_spec": _performance.active,
		"walk_mode": _walk_mode,
	})


# Play test -----------------------------------------------------------------

## Starts the play-test walker on the open territory (placement, sculpting and
## drawing stop). Returns whether it started.
func start_play_test() -> bool:
	var root := _authoring_root()
	var palette := _palette_plugin()
	if palette != null and palette.has_method("cancel_placement_for_terrain_sculpt"):
		palette.call("cancel_placement_for_terrain_sculpt")
	var sculpt := _sculpt_plugin()
	if sculpt != null and sculpt.has_method("deactivate_terrain_sculpt"):
		sculpt.call("deactivate_terrain_sculpt")
	_draw.cancel()
	_area.cancel()
	_scatter.cancel()
	var started := _walker.start(root)
	_status(_walker.last_message)
	if not started:
		_toast(_walker.last_message)
	else:
		get_editor_interface().set_main_screen_editor("3D")
	_sync_toolbar()
	update_overlays()
	return started


func stop_play_test() -> void:
	_walker.stop()
	_sync_toolbar()
	update_overlays()


func play_test_walker() -> RefCounted:
	return _walker


# Ground regions and plateaus ----------------------------------------------

## Opens the options for "ground" (paint ground regions) or "plateau".
func open_area_panel(kind: String) -> void:
	var root := _authoring_root()
	if root == null:
		_toast("Open a map authoring scene first.")
		return
	var anchor := Rect2i(Vector2i(get_editor_interface().get_base_control().get_global_mouse_position()),
		Vector2i(360, 0))
	_area_panel.open_for(kind, root, anchor, _selected_palette_entry())


## Arms the ground-region or plateau tool (see area_tool.gd); placement,
## sculpting, path drawing and the play test stop. Returns whether it started.
func start_area_tool(kind: String, options: Dictionary) -> bool:
	var root := _authoring_root()
	var palette := _palette_plugin()
	if palette != null and palette.has_method("cancel_placement_for_terrain_sculpt"):
		palette.call("cancel_placement_for_terrain_sculpt")
	var sculpt := _sculpt_plugin()
	if sculpt != null and sculpt.has_method("deactivate_terrain_sculpt"):
		sculpt.call("deactivate_terrain_sculpt")
	_draw.cancel()
	_walker.stop()
	_scatter.cancel()
	var started := _area.start(root, kind, options, _ownership_polygon(root), _protection())
	_status(_area.last_message)
	if not started:
		_toast(_area.last_message)
	else:
		get_editor_interface().set_main_screen_editor("3D")
	_sync_toolbar()
	update_overlays()
	return started


func area_tool() -> RefCounted:
	return _area


## Arms the scatter tool (see scatter_tool.gd) for `asset`, or the asset
## selected in the Map Assets dock; placement, drawing and the play test stop.
func start_scatter(options: Dictionary, asset: Dictionary = {}) -> bool:
	var root := _authoring_root()
	var palette := _palette_plugin()
	var entry := asset if not asset.is_empty() else _selected_palette_entry()
	if palette != null and palette.has_method("cancel_placement_for_terrain_sculpt"):
		palette.call("cancel_placement_for_terrain_sculpt")
	var sculpt := _sculpt_plugin()
	if sculpt != null and sculpt.has_method("deactivate_terrain_sculpt"):
		sculpt.call("deactivate_terrain_sculpt")
	_draw.cancel()
	_walker.stop()
	_area.cancel()
	var started := _scatter.start(root, entry, options, _ownership_polygon(root))
	_status(_scatter.last_message)
	if not started:
		_toast(_scatter.last_message)
	else:
		get_editor_interface().set_main_screen_editor("3D")
	_sync_toolbar()
	update_overlays()
	return started


func scatter_tool() -> RefCounted:
	return _scatter


func _selected_palette_entry() -> Dictionary:
	var palette := _palette_plugin()
	var dock: Variant = palette.get("_dock") if palette != null else null
	if dock == null or not (dock as Object).has_method("selected_entry"):
		return {}
	return (dock as Object).call("selected_entry")


func area_panel() -> Window:
	return _area_panel


## The owned land in territory-local X/Z: from the Territories reference host,
## else from the bound sculpt tool.
func _ownership_polygon(root: Node3D) -> Variant:
	var polygon := TopDown.ownership_polygons_local(root) if root != null else []
	if not polygon.is_empty():
		return polygon
	var fields := _protection()
	return fields.get("polygons", fields.get("polygon", PackedVector2Array()))


## The bound sculpt tool's border protection (see terrain_sculpt_tool.gd).
func _protection() -> Dictionary:
	var sculpt := _sculpt_plugin()
	var tool: Variant = sculpt.get("_sculpt") if sculpt != null else null
	if tool == null or not (tool as Object).has_method("protection_fields"):
		return {}
	return (tool as Object).call("protection_fields")


# Low spec ------------------------------------------------------------------

## Half resolution, far assets hidden and frame time shown (see
## performance_mode.gd). Returns the number of culled meshes.
func set_low_spec(on: bool) -> int:
	Settings.set_value("performance/low_spec", on)
	var culled := _performance.set_active(get_editor_interface().get_base_control(),
		_authoring_root(), on, float(Settings.value("performance/far_asset_metres")))
	_status("Low spec view on: half resolution, %d meshes beyond %.0f m hidden." % [culled,
		_performance.distance] if on else "Low spec view off.")
	_sync_toolbar()
	update_overlays()
	return culled


func performance_state() -> Dictionary:
	return {"active": _performance.active, "culled": _performance.culled_count(),
		"distance": _performance.distance,
		"half_resolution": PerformanceMode.view_option(get_editor_interface().get_base_control(),
			PerformanceMode.HALF_RESOLUTION_ID)}


# Minimap and camera jumps --------------------------------------------------

func minimap_dock() -> Control:
	return _minimap


## Renders the minimap picture again (see top_down_capture.gd render). Lighting
## is the noon preview unless a time preview is on.
func refresh_minimap() -> Dictionary:
	var root := _authoring_root()
	if _minimap == null:
		return {"error": "No minimap dock."}
	if root == null:
		_minimap.clear("Open a territory to see its minimap.")
		return {"error": "Open a map authoring scene first."}
	if _minimap_rendering or _capturing:
		return {"error": "A render is already running."}
	_minimap_rendering = true
	var ppm := float(Settings.value("minimap/pixels_per_metre"))
	var temporary_light := not _time.is_active() and TimeOfDay.saved_lighting(root).is_empty()
	if temporary_light and DisplayServer.get_name() != "headless":
		_time.enable(root, 180.0)
	else:
		temporary_light = false
	var rendered: Dictionary = await TopDown.render(root, ppm, false, true)
	if temporary_light:
		_time.disable()
	_minimap_rendering = false
	if _minimap == null or root != _authoring_root():
		return rendered
	if rendered.has("error"):
		var framing := TopDown.plan(root, ppm, TopDown.ownership_polygons_local(root))
		_minimap.set_image(null, framing if not framing.has("error") else {})
		_minimap.set_status(String(rendered.error))
	else:
		var framing: Dictionary = rendered.framing
		_minimap.set_image(levelled_minimap(rendered.image), framing)
		var published := published_minimap(root, framing)
		_minimap.set_published(published.get("image"), framing, String(published.get("note", "")))
		var concept := ConceptMaster.minimap_picture(root, framing)
		_minimap.set_concept(concept.get("image"), framing, String(concept.get("note", "")))
		_minimap.set_status("%.0f × %.0f m, north up. Click to jump." % [
			(framing.rect as Rect2).size.x, (framing.rect as Rect2).size.y])
	_update_minimap_state()
	return rendered


## The package's published minimap (world.json "minimap": worldMin/worldMax in
## territory-local X/Z, pixelsPerMetre, imageSize; north up, top-left at
## worldMin) resampled to the live picture's `framing`, so the two line up.
## Pixels the published image does not cover are transparent. Returns
## {"image", "note"} or {"note"} when there is nothing to show.
static func published_minimap(root: Node3D, framing: Dictionary) -> Dictionary:
	var manifest_path := TimeOfDay.published_manifest_path_for(String(root.get("region_id")))
	if manifest_path.is_empty():
		return {"note": "No published package for this territory."}
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	var minimap: Variant = (manifest as Dictionary).get("minimap") if manifest is Dictionary else null
	if not minimap is Dictionary:
		return {"note": "The published package has no minimap."}
	var data: Dictionary = minimap
	var file_name := String(data.get("image", data.get("file", "")))
	var low: Array = data.get("worldMin", [])
	var high: Array = data.get("worldMax", [])
	var size: Array = data.get("imageSize", [])
	var ppm := float(data.get("pixelsPerMetre", 0.0))
	if file_name.is_empty() or low.size() != 2 or high.size() != 2 or size.size() != 2 or ppm <= 0.0:
		return {"note": "The published minimap record is incomplete."}
	var image_path := manifest_path.get_base_dir().path_join(file_name)
	var source := Image.load_from_file(ProjectSettings.globalize_path(image_path)) \
		if FileAccess.file_exists(image_path) else null
	if source == null or source.is_empty():
		return {"note": "The published minimap image %s is missing." % file_name}
	if source.get_width() != int(size[0]) or source.get_height() != int(size[1]):
		return {"note": "The published minimap is %d x %d px, not the %d x %d its manifest states." % [
			source.get_width(), source.get_height(), int(size[0]), int(size[1])]}
	source.convert(Image.FORMAT_RGBA8)
	var picture := resample_published(source, Vector2(float(low[0]), float(low[1])), ppm, framing)
	return {"image": picture, "note": "Last published minimap (%s)." % image_path.get_file()}


## Nearest-pixel resample of a published minimap (top-left at `origin`, `ppm`
## pixels per metre) onto `framing` (top_down_capture.plan: rect, size).
static func resample_published(source: Image, origin: Vector2, ppm: float,
		framing: Dictionary) -> Image:
	var target_size: Vector2i = framing.size
	var rect: Rect2 = framing.rect
	var picture := Image.create_empty(maxi(target_size.x, 1), maxi(target_size.y, 1), false,
		Image.FORMAT_RGBA8)
	for y in picture.get_height():
		var z := rect.position.y + (float(y) + 0.5) * rect.size.y / float(picture.get_height())
		var v := floori((z - origin.y) * ppm)
		if v < 0 or v >= source.get_height():
			continue
		for x in picture.get_width():
			var along := rect.position.x + (float(x) + 0.5) * rect.size.x / float(picture.get_width())
			var u := floori((along - origin.x) * ppm)
			if u >= 0 and u < source.get_width():
				picture.set_pixel(x, y, source.get_pixel(u, v))
	return picture


## The minimap picture brightened so its owned land averages a readable level.
## This is for reading the map, not a correction: under the same light the
## terrain preview matches the game wherever the game applies the biome blend
## (measured on Amberwood). A map seen from straight above at a territory's own
## light can still be dim (forest lighting, low sun), so the dock levels its
## copy. Top-down captures stay as rendered.
static func levelled_minimap(image: Image) -> Image:
	var levelled := image.duplicate() as Image
	var total := 0.0
	var count := 0
	for y in range(0, levelled.get_height(), 3):
		for x in range(0, levelled.get_width(), 3):
			var pixel := levelled.get_pixel(x, y)
			if pixel.a > 0.5:
				total += pixel.get_luminance()
				count += 1
	if count == 0 or total <= 0.0:
		return levelled
	var factor := clampf(MINIMAP_TARGET_LUMINANCE / (total / float(count)), 1.0, 6.0)
	if factor > 1.01:
		levelled.adjust_bcs(factor, 1.0, 1.0)
	return levelled


func _update_minimap_state() -> void:
	if _minimap == null or _minimap.framing().is_empty():
		return
	var root := _authoring_root()
	if root == null:
		return
	var inverse := root.global_transform.affine_inverse()
	var state := {}
	var viewport := get_editor_interface().get_editor_viewport_3d(0)
	var camera := viewport.get_camera_3d() if viewport != null else null
	if camera != null:
		state.camera = inverse * camera.global_position
		state.camera_forward = inverse.basis * -camera.global_transform.basis.z
	var selected: Array[Vector3] = []
	for node in Tools.placements(root, get_editor_interface().get_selection().get_selected_nodes()):
		selected.append(inverse * node.global_position)
	state.selection = selected
	if bool(Settings.value("markers/show")):
		var markers: Array = []
		for marker in Markers.markers(root):
			markers.append([inverse * (marker as Node3D).global_position,
				Markers.color_for(String(marker.get("kind")))])
		state.markers = markers
	if _walker.active and _walker.is_placed():
		state.walker = _walker.position()
		state.route = _walker.route()
	var notes: Array = []
	var shown := _notes_dock.showing() if _notes_dock != null else "all"
	for note: Dictionary in _notes.notes:
		if shown == "all" or String(note.status) == shown:
			notes.append([note.position, String(note.status) == "resolved"])
	state.notes = notes
	_minimap.set_state(state)


func _on_minimap_jump(local: Vector3) -> void:
	var root := _authoring_root()
	if root == null:
		return
	var world := root.global_transform * local
	var ground := Probe.height_at(root, world)
	world.y = ground if not is_nan(ground) else world.y
	focus_camera_at(world)


## Centres the 3D view on `world`, keeping its angle and zoom (the viewport's
## Focus Selection only moves the orbit pivot). Godot has no public call for
## that, so a hidden, unsaved helper is selected, Focus Selection runs on it,
## and the previous selection is restored. Returns whether focus ran.
func focus_camera_at(world: Vector3) -> bool:
	var root := _authoring_root()
	if root == null:
		return false
	if _focusing:
		_pending_focus = [world]
		return false
	_focusing = true
	var selection := get_editor_interface().get_selection()
	var previous := selection.get_selected_nodes()
	var helper := MeshInstance3D.new()
	helper.name = FOCUS_HELPER
	helper.mesh = BoxMesh.new()
	helper.visible = false
	root.add_child(helper)
	helper.global_position = world
	selection.clear()
	selection.add_node(helper)
	var tree := root.get_tree()
	for _frame in 3:
		await tree.process_frame
	var pressed := _press_view_item("Focus Selection")
	for _frame in 2:
		await tree.process_frame
	selection.clear()
	for node in previous:
		if is_instance_valid(node) and node.is_inside_tree():
			selection.add_node(node)
	if is_instance_valid(helper):
		if helper.get_parent() != null:
			helper.get_parent().remove_child(helper)
		helper.queue_free()
	for _frame in 2:
		await tree.process_frame
	_focusing = false
	if not _pending_focus.is_empty():
		var next: Array = _pending_focus
		_pending_focus = []
		focus_camera_at(next[0] as Vector3)
	return pressed


func _press_view_item(text: String) -> bool:
	for popup_node in get_editor_interface().get_base_control().find_children("*", "PopupMenu",
			true, false):
		var popup := popup_node as PopupMenu
		for index in popup.item_count:
			if popup.get_item_text(index) == text:
				popup.id_pressed.emit(popup.get_item_id(index))
				return true
	return false
