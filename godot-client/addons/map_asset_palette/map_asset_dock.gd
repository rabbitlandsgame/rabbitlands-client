@tool
extends EditorDock

signal place_requested(entry: Dictionary)
signal add_at_center_requested(entry: Dictionary)
signal placement_cancel_requested
signal save_prefab_requested(prefab_name: String)

const Catalog := preload("res://addons/map_asset_palette/asset_catalog.gd")
const Placement := preload("res://addons/map_asset_palette/placement.gd")
const Prefabs := preload("res://addons/map_asset_palette/prefab_library.gd")
const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")
const Thumbnails := preload("res://addons/map_asset_palette/thumbnail_renderer.gd")
const THUMBNAIL_SIZE := Vector2i(64, 64)

var _editor_interface: EditorInterface
var _entries: Array[Dictionary] = []
var _visible_entries: Array[Dictionary] = []
var _selected_entry: Dictionary = {}
var _thumbnails: Dictionary = {}
var _renderer: Node
var _marker_entries: Array[Dictionary] = []
var _territory_entries: Array[Dictionary] = []
var _search: LineEdit
var _category: OptionButton
var _thumbnail_toggle: CheckButton
var _items: ItemList
var _preview: TextureRect
var _details: Label
var _place: Button
var _center: Button
var _cancel: Button
var _refresh: Button
var _status: Label
var _options: FoldableContainer
var _keep_placing: CheckBox
var _random_rotation: CheckBox
var _size_variation: SpinBox
var _align_to_surface: CheckBox
var _snap_to_grid: CheckBox
var _grid_step: SpinBox
var _prefab_name: LineEdit
var _save_prefab: Button
var _scene_available := false
var _syncing_options := false
var _library_category: LineEdit
var _import_dialog: EditorFileDialog
var _pending_library_selection := ""
const LIBRARY_ID_PREFIX := "library:"


func configure(editor_interface: EditorInterface) -> void:
	_editor_interface = editor_interface
	if _search == null:
		_build_ui()
	var settings := Settings.editor_settings()
	if settings != null and not settings.settings_changed.is_connected(sync_options):
		settings.settings_changed.connect(sync_options)
	if _editor_interface != null and _renderer == null:
		_renderer = Thumbnails.new()
		_renderer.set("cache_directory", _editor_interface.get_editor_paths().get_cache_dir())
		_renderer.connect(&"thumbnail_ready", _set_thumbnail)
		add_child(_renderer, false, Node.INTERNAL_MODE_BACK)
	_reload_entries(false)


## True once every requested thumbnail has been rendered or read from cache.
func thumbnails_idle() -> bool:
	return _renderer == null or _renderer.call("is_idle")


func set_scene_available(available: bool) -> void:
	_scene_available = available
	_update_buttons()
	if not available:
		set_placement_armed(false)
		_status.text = "Open a map authoring scene to place assets."
	elif _selected_entry.is_empty():
		_status.text = "Choose an asset from the library."


func set_placement_armed(armed: bool, label: String = "") -> void:
	_cancel.visible = armed
	_place.disabled = armed or not _can_place()
	_center.disabled = armed or not _can_place()
	if armed:
		_status.text = ("Placing %s: click the terrain. Q/E turn, PgUp/PgDn raise, " +
			"Home/End size, Shift for fine steps. Right-click or Escape stops.") % label
	elif _scene_available and not _selected_entry.is_empty():
		_status.text = "Ready to place %s." % String(_selected_entry.label)


func show_message(message: String) -> void:
	_status.text = message


func status_text() -> String:
	return _status.text


func selected_entry() -> Dictionary:
	return _selected_entry.duplicate(true)


func visible_entry_ids() -> PackedStringArray:
	var result := PackedStringArray()
	for entry in _visible_entries:
		result.append(String(entry.id))
	return result


func has_usable_layout() -> bool:
	if _search == null or size.x <= 0.0 or size.y <= 0.0:
		return false
	var dock_rect := get_global_rect()
	for control: Control in [_search, _category, _refresh, _items, _preview,
			_place, _center, _cancel]:
		if not control.visible:
			continue
		var rect := control.get_global_rect()
		if rect.size.x <= 0.0 or rect.size.y <= 0.0 or \
				rect.position.x < dock_rect.position.x - 0.01 or \
				rect.position.y < dock_rect.position.y - 0.01 or \
				rect.end.x > dock_rect.end.x + 0.01 or \
				rect.end.y > dock_rect.end.y + 0.01:
			return false
	return true


func set_search_query(query: String) -> void:
	_search.text = query
	_apply_filter()


func select_category(category: String) -> void:
	for index in _category.item_count:
		if _category.get_item_text(index) == category:
			_category.select(index)
			_apply_filter()
			return


func select_entry_by_id(entry_id: String) -> bool:
	for index in _visible_entries.size():
		if String(_visible_entries[index].id) == entry_id:
			_items.select(index)
			_select_index(index)
			return true
	return false


func cancel_placement() -> void:
	placement_cancel_requested.emit()
	set_placement_armed(false)


## Reloads the library and prefabs, keeping the current selection when possible.
func reload_library() -> void:
	var previous := String(_selected_entry.get("id", ""))
	_reload_entries(true)
	if not previous.is_empty():
		select_entry_by_id(previous)


## Gameplay marker entries for the open scene (see marker_library.gd); they are
## listed after the library and prefabs under "Gameplay markers".
func set_marker_entries(entries: Array[Dictionary]) -> void:
	_marker_entries = entries.duplicate(true)
	var previous := String(_selected_entry.get("id", ""))
	_reload_entries(false)
	if not previous.is_empty():
		select_entry_by_id(previous)


## The open territory's own kit (asset_catalog.territory_entries), listed after
## the library under "Territory kit: scenery" and "Territory kit: structures".
func set_territory_entries(entries: Array[Dictionary]) -> void:
	_territory_entries = entries.duplicate(true)
	var previous := String(_selected_entry.get("id", ""))
	_reload_entries(false)
	if not previous.is_empty():
		select_entry_by_id(previous)


func thumbnails_enabled() -> bool:
	return _thumbnail_toggle != null and _thumbnail_toggle.button_pressed


func set_thumbnails_enabled(enabled: bool) -> void:
	_thumbnail_toggle.button_pressed = enabled


func thumbnail_for(entry_id: String) -> Texture2D:
	return _thumbnails.get(entry_id) as Texture2D


## Mirrors the saved preferences into the option controls (e.g. after G toggles snap).
func sync_options() -> void:
	if _keep_placing == null:
		return
	_syncing_options = true
	_keep_placing.button_pressed = bool(Settings.value("placement/keep_placing"))
	_random_rotation.button_pressed = bool(Settings.value("placement/random_rotation"))
	_size_variation.value = float(Settings.value("placement/size_variation")) * 100.0
	_align_to_surface.button_pressed = bool(Settings.value("placement/align_to_surface"))
	_snap_to_grid.button_pressed = bool(Settings.value("placement/snap_to_grid"))
	_grid_step.value = float(Settings.value("grid/step"))
	_syncing_options = false


func _build_ui() -> void:
	title = "Map Assets"
	layout_key = "MapAssetPalette"
	default_slot = EditorDock.DOCK_SLOT_RIGHT_BL
	icon_name = &"MeshInstance3D"
	name = "MapAssets"
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_top", 8)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_bottom", 8)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 6)
	margin.add_child(column)
	_search = LineEdit.new()
	_search.placeholder_text = "Search assets and prefabs…"
	_search.clear_button_enabled = true
	_search.text_changed.connect(func(_text: String) -> void: _apply_filter())
	column.add_child(_search)
	var filters := HBoxContainer.new()
	_category = OptionButton.new()
	_category.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_category.item_selected.connect(func(_index: int) -> void: _apply_filter())
	filters.add_child(_category)
	_thumbnail_toggle = CheckButton.new()
	_thumbnail_toggle.text = "Grid"
	_thumbnail_toggle.tooltip_text = "Show the library as a thumbnail grid instead of a list."
	_thumbnail_toggle.button_pressed = true
	_thumbnail_toggle.toggled.connect(func(_on: bool) -> void: _apply_view_mode())
	filters.add_child(_thumbnail_toggle)
	_refresh = Button.new()
	_refresh.text = "Refresh"
	_refresh.tooltip_text = "Reload objects.json, starter-scene entries, and saved prefabs."
	_refresh.pressed.connect(reload_library)
	filters.add_child(_refresh)
	column.add_child(filters)
	_items = ItemList.new()
	_items.custom_minimum_size = Vector2(260, 190)
	_items.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_items.item_selected.connect(_select_index)
	_items.item_activated.connect(func(index: int) -> void:
		_select_index(index)
		_request_place())
	column.add_child(_items)
	var detail_row := HBoxContainer.new()
	_preview = TextureRect.new()
	_preview.custom_minimum_size = Vector2(96, 96)
	_preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	detail_row.add_child(_preview)
	_details = Label.new()
	_details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_details.custom_minimum_size = Vector2(120, 0)
	detail_row.add_child(_details)
	column.add_child(detail_row)
	var actions := HBoxContainer.new()
	_place = Button.new()
	_place.text = "Place on terrain"
	_place.tooltip_text = ("Arm placement, then click the terrain in the 3D view. A see-through " +
		"ghost follows the cursor; keep clicking to place more.")
	_place.pressed.connect(_request_place)
	actions.add_child(_place)
	_center = Button.new()
	_center.text = "Add at view center"
	_center.tooltip_text = "Place where the center of the 3D view meets the terrain."
	_center.pressed.connect(func() -> void:
		if _can_place(): add_at_center_requested.emit(selected_entry()))
	actions.add_child(_center)
	_cancel = Button.new()
	_cancel.text = "Stop placing"
	_cancel.visible = false
	_cancel.pressed.connect(cancel_placement)
	column.add_child(actions)
	column.add_child(_cancel)
	_build_options(column)
	_build_prefab_row(column)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_status)
	sync_options()
	_apply_view_mode()


func _build_options(column: VBoxContainer) -> void:
	_options = FoldableContainer.new()
	_options.title = "Placement options"
	_options.tooltip_text = ("Saved per user in Editor Settings > Map Authoring. Keys are " +
		"rebindable under Editor Settings > Shortcuts > Map Authoring.")
	column.add_child(_options)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	_options.add_child(grid)
	_keep_placing = _option_check(grid, "Keep placing",
		"Stay in placement after each click; right-click or Escape stops.",
		"placement/keep_placing")
	_random_rotation = _option_check(grid, "Random turn",
		"Give every placed asset a random turn about its up axis.",
		"placement/random_rotation")
	_align_to_surface = _option_check(grid, "Align to slope",
		"Tilt assets so they follow the terrain slope under them.",
		"placement/align_to_surface")
	var size_row := HBoxContainer.new()
	var size_label := Label.new()
	size_label.text = "Size ±"
	size_row.add_child(size_label)
	_size_variation = SpinBox.new()
	_size_variation.min_value = 0.0
	_size_variation.max_value = 90.0
	_size_variation.step = 1.0
	_size_variation.suffix = "%"
	_size_variation.tooltip_text = "Random size variation for each placed asset (0 = off)."
	_size_variation.value_changed.connect(func(value: float) -> void:
		if not _syncing_options: Settings.set_value("placement/size_variation", value / 100.0))
	size_row.add_child(_size_variation)
	grid.add_child(size_row)
	_snap_to_grid = _option_check(grid, "Snap to grid",
		"Snap placement to the territory grid (G toggles while placing).",
		"placement/snap_to_grid")
	var step_row := HBoxContainer.new()
	var step_label := Label.new()
	step_label.text = "Grid"
	step_row.add_child(step_label)
	_grid_step = SpinBox.new()
	_grid_step.min_value = 0.125
	_grid_step.max_value = 16.0
	_grid_step.step = 0.125
	_grid_step.suffix = "m"
	_grid_step.tooltip_text = ("Grid spacing in territory metres for snapping and for the " +
		"cursor grid. 1 m matches one server tile in the production regions.")
	_grid_step.value_changed.connect(func(value: float) -> void:
		if not _syncing_options: Settings.set_value("grid/step", value))
	step_row.add_child(_grid_step)
	grid.add_child(step_row)


func _option_check(parent: Control, text: String, tooltip: String, key: String) -> CheckBox:
	var check := CheckBox.new()
	check.text = text
	check.tooltip_text = tooltip
	check.toggled.connect(func(pressed: bool) -> void:
		if not _syncing_options: Settings.set_value(key, pressed))
	parent.add_child(check)
	return check


func _build_prefab_row(column: VBoxContainer) -> void:
	var row := HBoxContainer.new()
	_prefab_name = LineEdit.new()
	_prefab_name.placeholder_text = "Prefab name"
	_prefab_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_prefab_name.text_submitted.connect(func(_text: String) -> void: _request_save_prefab())
	row.add_child(_prefab_name)
	_save_prefab = Button.new()
	_save_prefab.text = "Save selection"
	_save_prefab.tooltip_text = ("Save the selected placed assets as a reusable prefab in " +
		"%s. Placing it later creates ordinary assets with fresh ids." % Prefabs.directory)
	_save_prefab.pressed.connect(_request_save_prefab)
	row.add_child(_save_prefab)
	var folder := Button.new()
	folder.text = "Folder"
	folder.tooltip_text = "Show the prefab folder in the FileSystem dock."
	folder.pressed.connect(_show_prefab_folder)
	row.add_child(folder)
	column.add_child(row)
	_build_intake_row(column)


## "Import models…" copies .glb/.gltf files into the drop-in library folder,
## where the catalog lists them by subfolder. No JSON to edit.
func _build_intake_row(column: VBoxContainer) -> void:
	var row := HBoxContainer.new()
	_library_category = LineEdit.new()
	_library_category.placeholder_text = "Library category"
	_library_category.tooltip_text = ("Subfolder of %s for imported models; it becomes the " +
		"palette category \"Library: <name>\".") % Catalog.library_directory
	_library_category.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(_library_category)
	var import_button := Button.new()
	import_button.text = "Import models…"
	import_button.tooltip_text = ("Copy .glb models into the library folder (a .gltf is " +
		"converted to .glb, which the bake requires) and list them here. Files you drop into " +
		"that folder yourself appear after Refresh.")
	import_button.pressed.connect(_show_import_dialog)
	row.add_child(import_button)
	var folder := Button.new()
	folder.text = "Folder"
	folder.tooltip_text = "Show the model library folder in the FileSystem dock."
	folder.pressed.connect(_show_library_folder)
	row.add_child(folder)
	column.add_child(row)


## Imports model files into the library (see asset_catalog.gd import_models)
## and refreshes the palette once the editor has imported them.
func import_models(paths: PackedStringArray, category: String = "") -> Dictionary:
	if category.is_empty() and _library_category != null:
		category = _library_category.text
	var result := Catalog.import_models(paths, category)
	var copied: Array = result.copied
	var message := "Imported %d model%s into %s." % [copied.size(),
		"" if copied.size() == 1 else "s",
		(copied[0] as String).get_base_dir() if not copied.is_empty() else Catalog.library_directory]
	if not (result.skipped as Array).is_empty():
		message += " Skipped: %s." % "; ".join(PackedStringArray(result.skipped))
	_status.text = message
	if not copied.is_empty():
		_pending_library_selection = LIBRARY_ID_PREFIX + String(copied[0]).trim_prefix(
			Catalog.library_directory.trim_suffix("/") + "/").get_basename()
		if _editor_interface != null:
			var filesystem := _editor_interface.get_resource_filesystem()
			if not filesystem.filesystem_changed.is_connected(_on_library_scanned):
				filesystem.filesystem_changed.connect(_on_library_scanned, CONNECT_ONE_SHOT)
			filesystem.scan()
		else:
			_on_library_scanned()
	return result


func _show_import_dialog() -> void:
	if _import_dialog == null:
		_import_dialog = EditorFileDialog.new()
		_import_dialog.file_mode = EditorFileDialog.FILE_MODE_OPEN_FILES
		_import_dialog.access = EditorFileDialog.ACCESS_FILESYSTEM
		_import_dialog.filters = PackedStringArray(["*.glb, *.gltf ; glTF models"])
		_import_dialog.title = "Import models into the map asset library"
		_import_dialog.files_selected.connect(func(paths: PackedStringArray) -> void:
			import_models(paths))
		add_child(_import_dialog)
	_import_dialog.popup_file_dialog()


func _on_library_scanned() -> void:
	reload_library()
	if not _pending_library_selection.is_empty():
		select_entry_by_id(_pending_library_selection)
		_pending_library_selection = ""


func _show_library_folder() -> void:
	if _editor_interface == null:
		return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(Catalog.library_directory))
	_editor_interface.get_resource_filesystem().scan()
	_editor_interface.get_file_system_dock().navigate_to_path(Catalog.library_directory)


func _request_save_prefab() -> void:
	save_prefab_requested.emit(_prefab_name.text)


func clear_prefab_name() -> void:
	_prefab_name.text = ""


func _show_prefab_folder() -> void:
	if _editor_interface == null:
		return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(Prefabs.directory))
	_editor_interface.get_resource_filesystem().scan()
	_editor_interface.get_file_system_dock().navigate_to_path(Prefabs.directory)


func _apply_view_mode() -> void:
	if _items == null:
		return
	if thumbnails_enabled():
		_items.icon_mode = ItemList.ICON_MODE_TOP
		_items.max_columns = 0
		_items.same_column_width = true
		_items.fixed_column_width = THUMBNAIL_SIZE.x + 20
		_items.fixed_icon_size = THUMBNAIL_SIZE
		_items.max_text_lines = 2
		_items.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	else:
		_items.icon_mode = ItemList.ICON_MODE_LEFT
		_items.max_columns = 1
		_items.same_column_width = false
		_items.fixed_column_width = 0
		_items.fixed_icon_size = Vector2i(24, 24)
		_items.max_text_lines = 1
	_apply_filter(false)


func _reload_entries(refresh_cache: bool) -> void:
	_cancel_if_armed()
	_entries = Catalog.entries(refresh_cache)
	_entries.append_array(_territory_entries)
	_entries.append_array(Prefabs.entries())
	_entries.append_array(_marker_entries)
	if refresh_cache:
		_thumbnails.clear()
		if _renderer != null:
			_renderer.call("clear")
	var previous_category := _category.get_item_text(_category.selected) \
		if _category.item_count > 0 else "All"
	_category.clear()
	_category.add_item("All")
	for category in Catalog.categories(_entries):
		_category.add_item(category)
	select_category(previous_category)
	if _category.selected < 0:
		_category.select(0)
	_apply_filter()
	_status.text = "Library refreshed: %d assets and prefabs." % _entries.size()
	if not Catalog.skipped_library_files.is_empty():
		_status.text += (" %d .gltf file%s in the library are not listed: the bake needs .glb. " +
			"Import models... converts them.") % [Catalog.skipped_library_files.size(),
			"" if Catalog.skipped_library_files.size() == 1 else "s"]


func _apply_filter(reset_selection: bool = true) -> void:
	if _items == null:
		return
	if reset_selection:
		_cancel_if_armed()
	var category := _category.get_item_text(_category.selected) \
		if _category.selected >= 0 else "All"
	var selected_id := String(_selected_entry.get("id", ""))
	_visible_entries = Catalog.filter_entries(_entries, _search.text, category)
	_items.clear()
	for entry in _visible_entries:
		var index := _items.add_item(String(entry.label), _thumbnails.get(String(entry.id)))
		_items.set_item_tooltip(index, "%s\n%s\n%s" % [String(entry.label),
			String(entry.category), String(entry.scene_path)])
		_queue_thumbnail(entry)
	if reset_selection:
		_selected_entry = {}
		_preview.texture = null
		_details.text = "%d assets" % _visible_entries.size()
	else:
		for index in _visible_entries.size():
			if String(_visible_entries[index].id) == selected_id:
				_items.select(index)
	_update_buttons()


func _select_index(index: int) -> void:
	if index < 0 or index >= _visible_entries.size():
		return
	_cancel_if_armed()
	_selected_entry = _visible_entries[index].duplicate(true)
	_details.text = "%s\n%s%s" % [String(_selected_entry.label),
		String(_selected_entry.category),
		"\n%.2f m tall" % float(_selected_entry.height) \
			if float(_selected_entry.height) > 0.0 else ""]
	if String(_selected_entry.id).begins_with(LIBRARY_ID_PREFIX):
		var notes := Catalog.admission_notes(String(_selected_entry.scene_path))
		_selected_entry["admission_notes"] = notes
		if not notes.is_empty():
			_details.text += "\nCheck before use:\n• " + "\n• ".join(notes)
	_preview.texture = _thumbnails.get(String(_selected_entry.id))
	_queue_selected_preview()
	_update_buttons()
	if _scene_available:
		_status.text = "Ready to place %s." % String(_selected_entry.label)


func _queue_selected_preview() -> void:
	if _renderer == null or _selected_entry.is_empty() or \
			_thumbnails.has(String(_selected_entry.id)):
		return
	# Jump the queue so the chosen asset's preview appears first.
	_renderer.call("request", _selected_entry, true)


func _queue_thumbnail(entry: Dictionary) -> void:
	if _renderer == null or _thumbnails.has(String(entry.id)):
		return
	_renderer.call("request", entry, false)


func _set_thumbnail(entry_id: String, texture: Texture2D) -> void:
	# A null texture is remembered too, so filtering never re-queues a miss.
	_thumbnails[entry_id] = texture
	for index in _visible_entries.size():
		if String(_visible_entries[index].id) == entry_id and index < _items.item_count:
			_items.set_item_icon(index, texture)
	if not _selected_entry.is_empty() and String(_selected_entry.id) == entry_id:
		_preview.texture = texture


func _request_place() -> void:
	if _can_place():
		place_requested.emit(selected_entry())


func _can_place() -> bool:
	return _scene_available and not _selected_entry.is_empty()


func _update_buttons() -> void:
	var armed := _cancel != null and _cancel.visible
	_place.disabled = armed or not _can_place()
	_center.disabled = armed or not _can_place()


func _cancel_if_armed() -> void:
	if _cancel != null and _cancel.visible:
		cancel_placement()
