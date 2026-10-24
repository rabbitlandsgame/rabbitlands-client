extends Control
## Shared live controls, editable presentation. The editor never replaces a
## chat feed, slot button, command handler or spell loadout with a preview copy.
const Presets := preload("res://src/ui/hud_presets.gd")
const Medallion := preload("res://src/ui/hud_medallion.gd")
const Compass := preload("res://src/ui/hud_compass.gd")
const ResourceStrip := preload("res://src/ui/hud_resource_strip.gd")
const UnitCard := preload("res://src/ui/hud_unit_card.gd")
const HudGrid := preload("res://src/ui/hud_grid_layout.gd")
const SlotStyle := preload("res://src/ui/hud_quick_slot_style.gd")
const HudChrome := preload("res://src/ui/compact_hud_style.gd")
const PanelChrome := preload("res://src/ui/hud_panel_chrome.gd")
const ResizeSnap := preload("res://src/ui/hud_resize_snap.gd")
const MinimapLabels := preload("res://src/ui/hud_minimap_labels.gd")
const ClockFace := preload("res://src/ui/hud_clock_face.gd")
const FrameOverlay := preload("res://src/ui/hud_frame_overlay.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const SWITCHES := {"skills": "side_stats", "clock": "analog_clock", "status": "indicators",
	"timer": "hud_timer", "research": "knowledge_bar", "fps": "show_fps"}
var model := Presets.new()
var preferences_path := WindowPreferences.SETTINGS_PATH
var main: Control
var parts: Dictionary = {}
var original: Dictionary = {}
var containers: Dictionary = {}
var icon_buttons: Array[Button] = []
var utility_grid: GridContainer
var panel: PanelContainer
var preset_picker: OptionButton
var settings_picker: OptionButton
var component_picker: OptionButton
var details: VBoxContainer
var preset_name: LineEdit
var message: Label
var selected := "spells"
var ready_to_layout := false
var _applying := false
var _refreshing := false
var _before: Dictionary = {}
var _custom_before: Dictionary = {}
var _builtins_before: Dictionary = {}
var _active_before := Presets.DEFAULT_PRESET
var _drag_part := ""
var _drag_mouse := Vector2.ZERO
var _drag_position := Vector2.ZERO
var _initial_size := Vector2(1280, 720)
var _layout_queued := false
var _layout_running := false
var modern_compass: Control
var modern_resources: Control
var minimap_labels: Control
var editor_dragger: WindowDrag
var _editor_placed := false
var _resizing := false
var _resize_size := Vector2.ZERO
var _resize_scale := 1.0
var _resize_axis_scale := Vector2.ONE
var _resize_axis := Vector2.ONE
var _resize_rect := Rect2()
var _resize_runtime_scale := Vector2.ONE
var _resize_targets: Array[Dictionary] = []
var _resize_guides: Array[Dictionary] = []
var _resize_snap_enabled := true
var _original_colors: Dictionary = {}
var _button_styles: Dictionary = {}
var _button_flags: Dictionary = {}
var _quest_tags := RegEx.create_from_string("\\[/?(?:color|font_size)(?:=[^\\]]+)?\\]")
var _detail_tabs: TabBar
var _detail_group := "Layout"
var _selected_arc := -1
var _undo: Array[Dictionary] = []
var _redo: Array[Dictionary] = []
var _restoring := false
var _last_edit_tag := ""
var _last_edit_time := 0
var undo_button: Button
var redo_button: Button
var reset_button: Button
var settings_reset: Button
var save_new_button: Button
var update_custom_button: Button
var delete_custom_button: Button
var custom_count_label: Label
var reset_component_button: Button
var selection_summary: Label
var _show_grid := false
var _hover: Dictionary = {}
var _drag_root := ""
var _drag_started := false
var _drag_arc_offset := 0.0
var _drag_center := Vector2.ZERO
var _snap_candidate: Dictionary = {}
var _snap_enabled := true
var target_card: Control
var input_exclusions: Array[Control] = []
var _intrinsic_sizes: Array = []
var _chrome: Dictionary = {}
var party_summary: Control
var clock_art: Node2D
var frame_overlay: Node2D
var _logo_texture: Texture2D
var _centered_logo_texture: AtlasTexture

func configure(owner_main: Control) -> void:
	main = owner_main
	_logo_texture = main.hud_logo.texture
	if _logo_texture != null:
		var image := _logo_texture.get_image()
		if image != null and not image.is_empty():
			_centered_logo_texture = AtlasTexture.new()
			_centered_logo_texture.atlas = _logo_texture
			_centered_logo_texture.region = _logo_ink_rect(image)
	name = "HudWorkspace"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	z_index = 280
	preferences_path = main.chat_hud.preferences_path
	_initial_size = main.game_view.size.max(Vector2.ONE)
	parts = {"utilities": main.get_node("GameView/Quickbar"), "resources": main.bottom_meters,
		"spells": main.casting_bar.panel, "items": main.get_node("GameView/ItemQuickbar"),
		"chat": main.chat_hud, "system_chat": main.system_chat_hud,
		"party": main.extension_windows.party_panel, "minimap": main.minimap_frame,
		"skills": main.skill_rows, "clock": main.get_node("GameView/ClockFrame"),
		"compass": main.get_node("GameView/CompassFrame"), "status": main.hud_indicators,
		"timer": main.hud_timer_label, "research": main.knowledge_bar,
		"logo": main.get_node("GameView/EloriaLogoFrame"), "fps": main.fps_label,
		"objectives": main.extension_windows.get("tracked_quest"), "target": main.selected_target,
		"nameplate": main.actor_resource_overlay,
		"gauntlet_loot": main.extension_windows.gauntlet_loot_window.reopen,
		"rare_drops": main.extension_windows.gauntlet_loot_window.announcement}
	for key: String in ["gauntlet_loot", "rare_drops"]:
		parts[key].reparent(main.game_view, false)
	for key: String in parts:
		var control: Control = parts[key]
		original[key] = {"node": control, "parent": control.get_parent(), "index": control.get_index(),
			"rect": Rect2(main.game_view.get_global_transform().affine_inverse() * control.global_position, control.size),
			"anchors": [control.anchor_left, control.anchor_top, control.anchor_right, control.anchor_bottom],
			"offsets": [control.offset_left, control.offset_top, control.offset_right, control.offset_bottom],
			"minimum": control.custom_minimum_size, "scale": control.scale,
			"visible": control.visible,
			"panel_style": control.get_theme_stylebox("panel")}
		if key in ["chat", "system_chat"]: original[key].bottom_hud = control.bottom_hud
		elif key == "party": original[key].bottom_hud = (control.get_node("WindowDrag") as WindowDrag).bottom_hud
	for child: Node in main.get_node("GameView/Quickbar/QuickRows/Buttons").get_children():
		if child is Button: icon_buttons.append(child)
	for button: Button in icon_buttons + main.quick_slot_buttons:
		_button_styles[button] = button.get_theme_stylebox("normal")
		_button_flags[button] = Vector2i(button.size_flags_horizontal, button.size_flags_vertical)
	utility_grid = GridContainer.new()
	utility_grid.name = "PresetMenuIcons"
	utility_grid.add_theme_constant_override("h_separation", 3)
	utility_grid.add_theme_constant_override("v_separation", 3)
	main.get_node("GameView/Quickbar/QuickRows").add_child(utility_grid)
	utility_grid.hide()
	var medallion := Medallion.new()
	medallion.name = "HealthMedallion"
	main.game_view.add_child(medallion)
	parts.medallion = medallion
	medallion.hide()
	var rail := Control.new()
	rail.name = "BlankHudPanel"
	rail.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main.game_view.add_child(rail)
	main.game_view.move_child(rail, main.viewport_container.get_index() + 1)
	parts.rail_panel = rail
	rail.hide()
	minimap_labels = MinimapLabels.new()
	minimap_labels.name = "HudMinimapLabels"
	main.minimap_frame.add_child(minimap_labels)
	minimap_labels.z_index = 10
	minimap_labels.hide()
	for key: String in ["food_meter", "load_meter", "xp_meter"]:
		var strip := ResourceStrip.new()
		strip.name = key.to_pascal_case()
		main.game_view.add_child(strip)
		parts[key] = strip
		strip.hide()
	var player_card := UnitCard.new()
	player_card.name = "PlayerCard"
	main.game_view.add_child(player_card)
	parts.player_card = player_card
	player_card.hide()
	target_card = UnitCard.new()
	target_card.name = "TargetCard"
	target_card.role = "target"
	main.game_view.add_child(target_card)
	target_card.hide()
	party_summary = UnitCard.new()
	party_summary.name = "PartyPlayerSummary"
	var party_body: VBoxContainer = parts.party.get_node("Body")
	party_body.add_child(party_summary)
	party_body.move_child(party_summary, main.extension_windows.party_scroll.get_index())
	party_summary.hide()
	modern_compass = Compass.new()
	modern_compass.name = "HeadingCompass"
	main.game_view.add_child(modern_compass)
	modern_compass.gui_input.connect(main._on_compass_gui_input.bind(modern_compass))
	modern_compass.hide()
	clock_art = ClockFace.new()
	clock_art.name = "BrassClockFace"
	main.clock_face.add_child(clock_art)
	frame_overlay = FrameOverlay.new()
	frame_overlay.name = "ConnectedHudFrames"
	frame_overlay.z_index = 21
	main.game_view.add_child(frame_overlay)
	modern_resources = ResourceStrip.new()
	modern_resources.name = "ResourceStrip"
	main.game_view.add_child(modern_resources)
	modern_resources.hide()
	for key: String in ["resources", "skills", "clock", "status", "timer", "research", "target"]:
		var wrapper := PanelContainer.new()
		wrapper.name = "HudComponent_" + key
		wrapper.z_index = 7
		main.game_view.add_child(wrapper)
		wrapper.hide()
		containers[key] = wrapper
	model.load_file(preferences_path)
	_build_editor()
	panel.visibility_changed.connect(_sync_gauntlet_hud)
	main.extension_windows.gauntlet_loot_window.hud_layout_requested.connect(queue_layout)
	main.window_stack.register(panel, true)
	_build_settings()
	ready_to_layout = true
	apply_layout()
	get_viewport().size_changed.connect(queue_layout)
	main.game_view.visibility_changed.connect(func() -> void:
		if is_open() and not main.game_view.visible: cancel_edit())
	main.casting_bar.layout_changed.connect(_casting_changed)
	for key: String in ["party", "minimap", "objectives"]:
		var dragger := parts[key].get_node_or_null("WindowDrag") as WindowDrag
		if dragger != null: dragger.moved.connect(func(_where: Vector2) -> void: _remember_moved(key))
	parts.party.resized.connect(func() -> void:
		if not _layout_running: queue_layout())
	main.extension_windows.party_layout_saved.connect(func() -> void:
		if _applying: return
		model.working.parts.party.dimensions = main.extension_windows._party_expanded_size if main.extension_windows._party_custom_size else Vector2.ZERO
		queue_layout()
		if not is_open(): _store())
	for key: String in ["chat", "system_chat"]:
		var surface: PanelContainer = parts[key]
		surface.dragger.moved.connect(func(_where: Vector2) -> void: _remember_moved(key))
		surface.configuration_changed.connect(func(option: String, _value: Variant) -> void:
			if not _applying and not is_open():
				_capture_live(model.working)
				if option == "background_opacity":
					if surface.options.background_opacity > 0:
						model.working.parts[key].show_background = true
						model.working.parts[key].frame_style = "panel"
					apply_layout()
				_store())
	_refresh_pickers()

func is_open() -> bool:
	return panel != null and panel.visible

func manages_layout() -> bool:
	return ready_to_layout and not bool(model.working.legacy)

func _sync_gauntlet_hud() -> void:
	main.extension_windows.gauntlet_loot_window.configure_hud(
		model.working.parts.gauntlet_loot.enabled, model.working.parts.rare_drops.enabled, is_open())
	queue_layout()

func _process(_delta: float) -> void:
	if not ready_to_layout: return
	# Server updates may show these again; a presentation switch stays in force.
	for key: String in Presets.PARTS:
		if not model.working.parts[key].enabled:
			if key == "chat" and parts.chat.is_temporarily_open(): continue
			# The roster preference must not suppress an invitation's answer buttons.
			if key == "party" and not str(AppState.party.get("invited_by", "")).is_empty(): continue
			_root(key).hide()
	if not bool(model.working.legacy):
		parts.rail_panel.visible = model.working.parts.rail_panel.enabled and not (model.working.parts.rail_panel.hide_with_stats and _root("skills").is_visible_in_tree())
		var sizes: Array = []
		for key: String in ["clock", "skills", "status", "timer", "research", "logo", "fps"]: sizes.append(_root(key).get_combined_minimum_size() if _root(key).visible else Vector2.ZERO)
		if sizes != _intrinsic_sizes:
			_intrinsic_sizes = sizes
			queue_layout()
		_root("target").visible = bool(model.working.parts.target.enabled) and not AppState.actors.get(AppState.selected_actor_id, {}).is_empty()
		for key: String in ["chat", "system_chat"]:
			parts[key]._header.visible = not model.working.parts[key].compact or parts[key].get_global_rect().has_point(get_global_mouse_position())
		var tracker_text: RichTextLabel = main.extension_windows.tracked_quest_text
		if tracker_text.text.contains("[color="):
			tracker_text.text = _quest_tags.sub(tracker_text.text, "", true)
		if model.working.parts.objectives.compact and tracker_text.text.contains("QUEST TRACKER"):
			tracker_text.text = tracker_text.text.substr(tracker_text.text.find("\n") + 1)
		var party_changed := false
		var actions: Control = parts.party.get_node("Body/PartyActions")
		var collapsed: bool = main.extension_windows._party_collapsed
		var show_controls: bool = collapsed or not model.working.parts.party.compact \
			or parts.party.get_global_rect().has_point(get_global_mouse_position()) \
			or main.extension_windows.party_add_bot.get_popup().visible or main.extension_windows.party_options.get_popup().visible
		var header: Control = parts.party.get_node("Body/Header")
		main.extension_windows._party_controls_visible = show_controls
		if actions.visible != (show_controls and not collapsed) or header.visible != show_controls:
			actions.visible = show_controls and not collapsed
			header.visible = show_controls
			party_changed = true
		var self_name := ""
		for member: Dictionary in AppState.party.get("members", []):
			if member.get("is_self", false): self_name = str(member.get("name", ""))
		for row: Node in main.extension_windows.party_rows.get_children():
			if row is Control:
				var show_row: bool = (model.working.parts.party.show_self and not model.working.parts.party.show_player_details) or str(row.name) != "Member" + self_name
				if row.visible != show_row:
					row.visible = show_row
					party_changed = true
		var show_summary: bool = model.working.parts.party.show_player_details and model.working.parts.party.show_self and not collapsed
		if party_summary.visible != show_summary:
			party_summary.visible = show_summary
			party_changed = true
		if party_changed:
			main.extension_windows._queue_party_layout()
			queue_layout()

static func _logo_ink_rect(image: Image) -> Rect2i:
	# Ignore nearly invisible export residue around the mark when centering it.
	# The source texture remains unchanged; the atlas only adjusts its framing.
	var pixels := image.duplicate() as Image
	pixels.convert(Image.FORMAT_RGBA8)
	var bytes := pixels.get_data()
	var dimensions := pixels.get_size()
	var first := dimensions
	var last := Vector2i.ZERO
	for y: int in dimensions.y:
		for x: int in dimensions.x:
			if bytes[(y * dimensions.x + x) * 4 + 3] < 8: continue
			first = first.min(Vector2i(x, y))
			last = last.max(Vector2i(x + 1, y + 1))
	if last.x <= first.x or last.y <= first.y: return Rect2i(Vector2i.ZERO, dimensions)
	return Rect2i(first, last - first).grow(2).intersection(Rect2i(Vector2i.ZERO, dimensions))

func _root(key: String) -> Control:
	if key == "target" and not bool(model.working.legacy): return target_card
	if key == "compass" and not bool(model.working.legacy): return modern_compass
	if key == "resources" and not bool(model.working.legacy): return modern_resources
	if containers.has(key) and not bool(model.working.legacy): return containers[key]
	return parts.get(key) as Control

func _build_settings() -> void:
	var body: VBoxContainer = main.settings_window.page_body("HUD")
	var row := HBoxContainer.new()
	row.name = "HudPresets"
	row.add_theme_constant_override("separation", 10)
	body.add_child(row)
	body.move_child(row, 0)
	settings_picker = OptionButton.new()
	settings_picker.name = "HudPresetPicker"
	settings_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(settings_picker)
	settings_picker.item_selected.connect(func(index: int) -> void:
		if _refreshing: return
		choose_preset(str(settings_picker.get_item_metadata(index)))
		commit())
	var edit := _button("Edit HUD…", open_editor)
	edit.name = "HudEditorButton"
	row.add_child(edit)
	settings_reset = _button("Restore default", func() -> void:
		reset_builtin()
		commit())
	settings_reset.name = "HudResetDefault"
	row.add_child(settings_reset)
	var hint := Label.new()
	hint.text = "Choose a preset, edit its components, or save up to five custom designs."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(hint)
	body.move_child(hint, 1)

func _button(text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.focus_mode = Control.FOCUS_NONE
	HudChrome.button(button)
	button.pressed.connect(callback)
	return button

func _build_editor() -> void:
	panel = PanelContainer.new()
	panel.name = "HudEditorPanel"
	panel.custom_minimum_size = Vector2(370, 0)
	panel.add_theme_stylebox_override("panel", HudChrome.box(Color("171b18"), Color("ac915f"), 14))
	add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 6)
	panel.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var title := Label.new()
	title.text = "HUD editor"
	title.add_theme_font_size_override("font_size", 20)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	header.add_child(_button("Cancel", cancel_edit))
	header.add_child(_button("Done & save", commit_and_close))
	editor_dragger = WindowDrag.attach(panel, header)
	editor_dragger.reserved_right = 6.0
	editor_dragger.reserved_bottom = 6.0
	# Option rows briefly grow the minimum while being rebuilt. Clamp only
	# after filtering them, so a transient height never moves the editor.
	panel.resized.disconnect(editor_dragger._clamp_when_visible)
	panel.visibility_changed.disconnect(editor_dragger._clamp_when_visible)
	get_viewport().size_changed.disconnect(editor_dragger._clamp_when_visible)
	editor_dragger.moved.connect(func(where: Vector2) -> void:
		model.editor_position = where / main.game_view.size.max(Vector2.ONE))
	var hint := Label.new()
	hint.text = "Click a HUD part, then drag or resize. Drag this title to move the editor."
	hint.add_theme_font_size_override("font_size", 12)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(hint)
	var aids := HBoxContainer.new()
	column.add_child(aids)
	var grid := CheckBox.new()
	grid.name = "HudEditorGrid"
	grid.text = "Grid"
	grid.tooltip_text = "Show a 20-pixel alignment grid and screen center guides."
	grid.toggled.connect(func(value: bool) -> void: _show_grid = value; queue_redraw())
	aids.add_child(grid)
	var snap := CheckBox.new()
	snap.name = "HudEditorSnap"
	snap.text = "Snap edges"
	snap.button_pressed = true
	snap.tooltip_text = "Snap while docking or resizing. Hold Shift to bypass; Alt-drag detaches."
	snap.toggled.connect(func(value: bool) -> void:
		_snap_enabled = value
		_resize_snap_enabled = value)
	aids.add_child(snap)
	preset_picker = OptionButton.new()
	preset_picker.name = "EditorPresetPicker"
	column.add_child(preset_picker)
	preset_picker.item_selected.connect(func(index: int) -> void:
		if not _refreshing: choose_preset(str(preset_picker.get_item_metadata(index))))
	var actions := HBoxContainer.new()
	column.add_child(actions)
	undo_button = _button("Undo", undo_edit)
	redo_button = _button("Redo", redo_edit)
	reset_button = _button("Restore default", reset_builtin)
	reset_button.name = "EditorResetDefault"
	reset_button.tooltip_text = "Restore this built-in preset. Undo or Cancel can recover your edits."
	for button: Button in [undo_button, redo_button, reset_button]: actions.add_child(button)
	actions.add_child(_button("Move aside", _move_editor_aside))
	var save_row := HBoxContainer.new()
	column.add_child(save_row)
	preset_name = LineEdit.new()
	preset_name.name = "CustomPresetName"
	preset_name.placeholder_text = "Name your custom preset"
	preset_name.max_length = 48
	preset_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	save_row.add_child(preset_name)
	save_new_button = _button("Save as new", func() -> void: save_custom(false))
	save_new_button.name = "SaveCustomHud"
	save_row.add_child(save_new_button)
	update_custom_button = _button("Update", func() -> void: save_custom(true))
	update_custom_button.name = "UpdateCustomHud"
	save_row.add_child(update_custom_button)
	var custom_row := HBoxContainer.new()
	column.add_child(custom_row)
	custom_count_label = Label.new()
	custom_count_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	custom_count_label.add_theme_font_size_override("font_size", 12)
	custom_row.add_child(custom_count_label)
	delete_custom_button = _button("Delete custom", delete_custom)
	delete_custom_button.name = "DeleteCustomHud"
	delete_custom_button.tooltip_text = "Delete the selected custom design. Undo or Cancel can recover it."
	custom_row.add_child(delete_custom_button)
	component_picker = OptionButton.new()
	component_picker.name = "HudComponentPicker"
	component_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	component_picker.fit_to_longest_item = false
	for key: String in Presets.PARTS:
		component_picker.add_item(Presets.PARTS[key])
		component_picker.set_item_metadata(component_picker.item_count - 1, key)
	for index: int in 8:
		component_picker.add_item("  " + _arc_name(index))
		component_picker.set_item_metadata(component_picker.item_count - 1, "arc_%d" % index)
	var selection_row := HBoxContainer.new()
	column.add_child(selection_row)
	selection_row.add_child(component_picker)
	reset_component_button = _button("Reset part", reset_component)
	reset_component_button.name = "ResetHudComponent"
	reset_component_button.tooltip_text = "Restore only this part (or selected curve) to its built-in appearance and position. Undo recovers it."
	selection_row.add_child(reset_component_button)
	selection_summary = Label.new()
	selection_summary.add_theme_font_size_override("font_size", 12)
	selection_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(selection_summary)
	component_picker.item_selected.connect(func(index: int) -> void:
		var key := str(component_picker.get_item_metadata(index))
		if key.begins_with("arc_"): select_component("medallion", int(key.trim_prefix("arc_")))
		else: select_component(key))
	_detail_tabs = TabBar.new()
	for caption: String in ["Layout", "Look", "Options", "Dock"]: _detail_tabs.add_tab(caption)
	_detail_tabs.tab_changed.connect(func(index: int) -> void:
		_detail_group = _detail_tabs.get_tab_title(index)
		_filter_details())
	column.add_child(_detail_tabs)
	var scroll := ScrollContainer.new()
	scroll.name = "ComponentOptionsScroll"
	scroll.custom_minimum_size = Vector2(0, 210)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	details = VBoxContainer.new()
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	details.add_theme_constant_override("separation", 7)
	scroll.add_child(details)
	message = Label.new()
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message.add_theme_font_size_override("font_size", 12)
	column.add_child(message)
	panel.hide()

func _refresh_pickers() -> void:
	_refreshing = true
	for picker: OptionButton in [preset_picker, settings_picker]:
		picker.clear()
		for id: String in Presets.BUILT_INS:
			picker.add_item(Presets.BUILT_INS[id])
			picker.set_item_metadata(picker.item_count - 1, id)
		for id: String in model.custom:
			picker.add_item("Custom · " + str(model.custom[id].name))
			picker.set_item_metadata(picker.item_count - 1, id)
		for index: int in picker.item_count:
			if picker.get_item_metadata(index) == model.active: picker.select(index)
	preset_name.text = str(model.custom[model.active].name) if model.custom.has(model.active) else ""
	_refreshing = false
	_refresh_actions()

func open_editor() -> void:
	if not ready_to_layout or is_open(): return
	if main.inventory_workspace != null and main.inventory_workspace.is_editing():
		main.inventory_workspace.finish_edit(false)
	_capture_live(model.working)
	_before = model.working.duplicate(true)
	_custom_before = model.custom.duplicate(true)
	_builtins_before = model.builtin_overrides.duplicate(true)
	_active_before = model.active
	_undo.clear()
	_redo.clear()
	_last_edit_tag = ""
	main.settings_window.close()
	main.spell_wheel.reset()
	main.technique_ring.hide()
	panel.show()
	panel.move_to_front()
	select_component(selected)
	_center_editor()
	message.text = "Preview only · Done & save keeps edits; Cancel discards them.\nClick a HUD part, then use arrows for 1px moves (Shift: 10px)."
	queue_redraw()

func _center_editor() -> void:
	if not is_open(): return
	panel.custom_minimum_size.x = minf(370, maxf(300, size.x - 24))
	panel.size.x = minf(400, size.x - 24)
	var scroll: ScrollContainer = panel.find_child("ComponentOptionsScroll", true, false)
	if scroll != null:
		var fixed_height := panel.get_combined_minimum_size().y - scroll.custom_minimum_size.y
		scroll.custom_minimum_size.y = clampf(size.y - fixed_height - 24, 80, 210)
	panel.size.y = panel.get_combined_minimum_size().y
	if not _editor_placed:
		panel.reset_size()
		panel.position = model.editor_position * main.game_view.size if model.editor_position.x >= 0 else (size - panel.size) * 0.5
		_editor_placed = true
	panel.position = panel.position.clamp(Vector2(6, 6), (size - panel.size - Vector2(6, 6)).max(Vector2(6, 6)))
	model.editor_position = panel.position / main.game_view.size.max(Vector2.ONE)

func choose_preset(id: String, factory_default := false) -> void:
	_checkpoint("preset")
	# Switching while editing keeps each option's pending changes. Cancel and
	# Undo include this cache, and Done saves it with the active layout.
	if not factory_default and Presets.BUILT_INS.has(model.active):
		_capture_live(model.working)
		model.builtin_overrides[model.active] = model.working.duplicate(true)
	model.select(id, factory_default)
	apply_layout()
	_refresh_pickers()
	if is_open():
		select_component(selected)
		message.text = "Preset previewed. Chat, messages, shortcuts and spell assignments stay available."

func _snapshot() -> Dictionary:
	var value: Dictionary = model.working.duplicate(true)
	# Presets specify only their chat differences. Capture the complete live
	# appearance so Undo can also reverse an explicit default reset.
	for key: String in ["chat", "system_chat"]: _capture_chat(value, key)
	return {"working":value, "active":model.active, "custom":model.custom.duplicate(true), "builtins":model.builtin_overrides.duplicate(true)}

func _checkpoint(tag: String) -> void:
	if not is_open() or _restoring: return
	var now := Time.get_ticks_msec()
	if tag not in ["preset", "save_custom", "delete_custom", "reset_component", "restore_default"] and tag == _last_edit_tag and now - _last_edit_time < 400:
		_last_edit_time = now
		return
	_undo.append(_snapshot())
	if _undo.size() > 40: _undo.pop_front()
	_redo.clear()
	_last_edit_tag = tag
	_last_edit_time = now
	_refresh_actions()

func _restore_snapshot(value: Dictionary) -> void:
	_restoring = true
	model.working = value.working.duplicate(true)
	model.active = value.active
	model.custom = value.custom.duplicate(true)
	model.builtin_overrides = value.get("builtins", {}).duplicate(true)
	apply_layout()
	_refresh_pickers()
	select_component(selected, _selected_arc)
	_last_edit_tag = ""
	_restoring = false
	_refresh_actions()

func undo_edit() -> void:
	if _undo.is_empty(): return
	_redo.append(_snapshot())
	_restore_snapshot(_undo.pop_back())
	message.text = "Undone · your previous layout is restored."

func redo_edit() -> void:
	if _redo.is_empty(): return
	_undo.append(_snapshot())
	_restore_snapshot(_redo.pop_back())
	message.text = "Redone · preview updated."

func reset_builtin() -> void:
	if not Presets.BUILT_INS.has(model.active): return
	_checkpoint("restore_default")
	model.builtin_overrides.erase(model.active)
	model.select(model.active, true)
	for key: String in ["chat", "system_chat"]:
		var defaults: Dictionary = parts[key].DEFAULT_OPTIONS.duplicate()
		if key == "system_chat": defaults.font_size = 14
		defaults.merge(model.working.chat_windows.get(key, {}).get("options", {}), true)
		model.working.chat_windows[key] = {"options":defaults}
	apply_layout()
	_refresh_pickers()
	if is_open():
		select_component(selected)
		message.text = "Built-in default restored. Undo or Cancel recovers your edits."

func _refresh_actions() -> void:
	if undo_button != null: undo_button.disabled = _undo.is_empty()
	if redo_button != null: redo_button.disabled = _redo.is_empty()
	if reset_button != null: reset_button.disabled = not Presets.BUILT_INS.has(model.active)
	if settings_reset != null: settings_reset.disabled = not Presets.BUILT_INS.has(model.active)
	if save_new_button != null:
		save_new_button.disabled = model.custom.size() >= Presets.MAX_CUSTOM
		save_new_button.tooltip_text = "Five designs saved. Update or delete a custom design to make room." if save_new_button.disabled else "Save this layout as a separate custom design."
	if update_custom_button != null: update_custom_button.disabled = not model.custom.has(model.active)
	if delete_custom_button != null: delete_custom_button.disabled = not model.custom.has(model.active)
	if custom_count_label != null: custom_count_label.text = "Custom designs: %d / %d" % [model.custom.size(), Presets.MAX_CUSTOM]
	_refresh_selection()

func _refresh_selection() -> void:
	if component_picker == null: return
	for index: int in component_picker.item_count:
		var key := str(component_picker.get_item_metadata(index))
		var hidden: bool
		var caption: String
		if key.begins_with("arc_"):
			var arc_index := int(key.trim_prefix("arc_"))
			hidden = not model.working.parts.medallion.arcs[arc_index].enabled
			caption = "  " + _arc_name(arc_index)
		else:
			hidden = not model.working.parts[key].enabled
			caption = Presets.PARTS[key]
		component_picker.set_item_text(index, caption + (" · hidden" if hidden else ""))
	if selection_summary == null: return
	var config: Dictionary = model.working.parts[selected]
	var visible_part: bool = config.enabled
	var caption: String = Presets.PARTS[selected]
	if _selected_arc >= 0:
		visible_part = visible_part and config.arcs[_selected_arc].enabled
		caption = _arc_name(_selected_arc)
	var dock := "Free position"
	if config.dock_target != "none": dock = "Docked to " + str(Presets.PARTS[config.dock_target])
	elif config.edge_dock != "none": dock = "Screen edge: " + str(config.edge_dock).replace("_", " ")
	selection_summary.text = caption + (" · visible" if visible_part else " · hidden") + "\n" + dock

func reset_component() -> void:
	if not Presets.PARTS.has(selected): return
	_checkpoint("reset_component")
	var source: String = model.active if Presets.BUILT_INS.has(model.active) else model.working.parts[selected].style
	var defaults := Presets.preset(source)
	if selected == "medallion" and _selected_arc >= 0:
		model.working.parts.medallion.arcs[_selected_arc] = defaults.parts.medallion.arcs[_selected_arc].duplicate(true)
	else:
		model.working.parts[selected] = defaults.parts[selected].duplicate(true)
		if selected == "nameplate": model.working.banner_colors = defaults.banner_colors.duplicate(true)
		if selected in ["chat", "system_chat"]:
			var options: Dictionary = parts[selected].DEFAULT_OPTIONS.duplicate()
			if selected == "system_chat": options.font_size = 14
			options.merge(defaults.chat_windows.get(selected, {}).get("options", {}), true)
			model.working.chat_windows[selected] = {"options":options}
	apply_layout()
	select_component(selected, _selected_arc)
	message.text = "Selected part restored. Other components stay as you arranged them. Undo recovers your edit."

func _move_editor_aside() -> void:
	var rect := _selection_rect(selected)
	var best := panel.position
	var overlap := INF
	for point: Vector2 in [Vector2(8, 8), Vector2(size.x - panel.size.x - 8, 8), Vector2(8, size.y - panel.size.y - 8), size - panel.size - Vector2(8, 8)]:
		point = point.max(Vector2(6, 6))
		var area := Rect2(point, panel.size).intersection(rect.grow(16)).get_area()
		if area < overlap:
			best = point
			overlap = area
	panel.position = best
	model.editor_position = best / main.game_view.size.max(Vector2.ONE)

func select_component(key: String, arc_index := -1) -> void:
	if not Presets.PARTS.has(key): return
	selected = key
	_selected_arc = arc_index if key == "medallion" else -1
	_refresh_selection()
	if _selected_arc >= 0:
		_detail_tabs.current_tab = 2
		_detail_group = "Options"
	for index: int in component_picker.item_count:
		var expected := "arc_%d" % _selected_arc if _selected_arc >= 0 else key
		if component_picker.get_item_metadata(index) == expected: component_picker.select(index)
	for child: Node in details.get_children():
		details.remove_child(child)
		child.queue_free()
	var config: Dictionary = model.working.parts[key]
	if _selected_arc < 0:
		_toggle("Show " + Presets.PARTS[key], bool(config.enabled), func(value: bool) -> void: change_part(key, "enabled", value))
		_choice("Position", Presets.ANCHORS, str(config.anchor), func(value: String) -> void: change_part(key, "anchor", value))
		_choice("Appearance", Presets.STYLES, str(config.style), func(value: String) -> void: change_part(key, "style", value))
		_number("Scale", float(config.scale), 0.5, 2.0, 0.05, func(value: float) -> void: change_part(key, "scale", value))
		if key in ["skills", "clock", "status", "timer", "research", "logo", "fps"]:
			for axis: String in ["x", "y"]:
				_number("Width scale" if axis == "x" else "Height scale", config.axis_scale.x if axis == "x" else config.axis_scale.y, 0.25, 4, 0.05, func(value: float) -> void:
					var axes: Vector2 = model.working.parts[key].axis_scale
					if axis == "x": axes.x = value
					else: axes.y = value
					change_part(key, "axis_scale", axes))
		_color("Window color", config.background_color, func(value: Color) -> void: change_frame_color(key, "background_color", value))
		_color("Border color", config.border_color, func(value: Color) -> void: change_frame_color(key, "border_color", value))
		if key != "nameplate":
			_color("Text color", config.text_color, func(value: Color) -> void: change_part(key, "text_color", value))
		_number("Background opacity", config.background_color.a * 100, 0, 100, 1, func(value: float) -> void:
			var color: Color = model.working.parts[key].background_color
			color.a = value / 100
			change_part(key, "background_color", color))
		_number("Border opacity", config.border_color.a * 100, 0, 100, 1, func(value: float) -> void:
			var color: Color = model.working.parts[key].border_color
			color.a = value / 100
			change_part(key, "border_color", color))
		if key in ["spells", "items"]:
			_toggle("Flush slot edges", config.flush_slots, func(value: bool) -> void: change_part(key, "flush_slots", value))
			_number("Slot spacing", config.slot_gap, 0, 12, 1, func(value: float) -> void: change_part(key, "slot_gap", value))
			_choice("Slot border", ["match_hud", "none", "beveled", "ornate"], config.slot_border_style, func(value: String) -> void: change_part(key, "slot_border_style", value))
			_color("Slot border color", config.slot_border_color, func(value: Color) -> void: change_part(key, "slot_border_color", value))
			_number("Icon opacity", config.icon_opacity * 100, 0, 100, 1, func(value: float) -> void: change_part(key, "icon_opacity", value / 100))
			if key == "spells":
				_number("Unavailable icon opacity", config.unavailable_icon_opacity * 100, 0, 100, 1, func(value: float) -> void: change_part(key, "unavailable_icon_opacity", value / 100))
		if key != "medallion":
			_toggle("HUD background", config.show_background, func(value: bool) -> void: change_part(key, "show_background", value))
			_toggle("HUD border", config.show_border, func(value: bool) -> void: change_part(key, "show_border", value))
			if key != "nameplate": _choice("HUD border design", Presets.HUD_BORDERS, config.hud_border_style, func(value: String) -> void: change_part(key, "hud_border_style", value))
		var targets: Array = ["none"]
		for other: String in Presets.PARTS:
			if other != key and other != "nameplate" and (_root(other).is_visible_in_tree() or config.dock_target == other): targets.append(other)
		_choice("Dock to", targets, config.dock_target, func(value: String) -> void:
			change_part(key, "dock_target", value)
			select_component(key)
			message.text = "Drag to move the connected group. Alt-drag detaches this window.")
		_choice("Dock edge", ["left", "right", "top", "bottom"], config.dock_side, func(value: String) -> void: change_part(key, "dock_side", value))
		_choice("Dock alignment", ["start", "center", "end", "stretch"], config.dock_align, func(value: String) -> void: change_part(key, "dock_align", value))
		_toggle("Dock extend to screen edge", config.extend_to_edge, func(value: bool) -> void: change_part(key, "extend_to_edge", value))
		_choice("Dock to screen", ["none", "left", "right", "top", "bottom", "top_left", "top_right", "bottom_left", "bottom_right"], config.edge_dock, func(value: String) -> void:
			if value == "none": change_part(key, "edge_dock", "none")
			else: dock_component(key, "screen", value))
		_number("Dock spacing", config.dock_gap, -16, 100, 1, func(value: float) -> void: change_part(key, "dock_gap", value))
		if config.dock_target != "none":
			var status := HBoxContainer.new()
			status.set_meta("option_caption", "Dock status")
			status.add_child(_button("Detach", func() -> void: dock_component(key, "none", "right")))
			status.add_child(_button("Select group", func() -> void: select_component(_dock_root(key))))
			details.add_child(status)
	if key == "medallion":
		_arc_selector()
		if _selected_arc < 0:
			_choice("Center resource", Presets.RESOURCES, config.center_resource, func(value: String) -> void:
				change_part(key, "center_resource", value)
				select_component(key))
			_color("Center fill", config.center_color, func(value: Color) -> void: change_part(key, "center_color", value))
			_choice("Circle border", Presets.BORDERS, config.border_design, func(value: String) -> void: change_part(key, "border_design", value))
			_toggle("Show center value", config.show_values, func(value: bool) -> void: change_part(key, "show_values", value))
			_toggle("Show center label", config.show_labels, func(value: bool) -> void: change_part(key, "show_labels", value))
			_number("Circle diameter", parts.medallion.frame_radius() * 2 * parts.medallion.scale.x, 50, 400, 1, func(value: float) -> void:
				change_part(key, "scale", value / maxf(1, parts.medallion.frame_radius() * 2)))
			var attach_spells := _button("Attach spells on left", func() -> void: dock_component("spells", "medallion", "left"))
			var attach_items := _button("Attach items on right", func() -> void: dock_component("items", "medallion", "right"))
			for button: Button in [attach_spells, attach_items]:
				button.set_meta("option_caption", "Dock quick attach")
				details.add_child(button)
		else:
			var arc: Dictionary = config.arcs[_selected_arc]
			_toggle("Show curve", arc.enabled, func(value: bool) -> void: change_arc(_selected_arc, "enabled", value))
			_choice("Resource", Presets.RESOURCES, arc.resource, func(value: String) -> void:
				change_arc(_selected_arc, "resource", value)
				select_component(key, _selected_arc))
			_color("Curve color", arc.color, func(value: Color) -> void: change_arc(_selected_arc, "color", value))
			for field: String in ["radius_offset", "thickness", "start_angle", "sweep_angle"]:
				var labels := {"radius_offset":"Distance from circle", "thickness":"Curve thickness", "start_angle":"Start angle", "sweep_angle":"Curve length (degrees)"}
				var lows := {"radius_offset":-30, "thickness":2, "start_angle":-360, "sweep_angle":10}
				var highs := {"radius_offset":96, "thickness":16, "start_angle":360, "sweep_angle":180}
				_number(labels[field], arc[field], lows[field], highs[field], 1, func(value: float) -> void: change_arc(_selected_arc, field, value))
	if key == "compass":
		_choice("Compass display", ["round", "ribbon"], config.compass_mode, func(value: String) -> void: change_part(key, "compass_mode", value))
		_choice("Outside compass circle", ["transparent", "fill_when_docked", "filled"], config.compass_corners, func(value: String) -> void: change_part(key, "compass_corners", value))
		_toggle("Show area name", config.show_labels, func(value: bool) -> void: change_part(key, "show_labels", value))
	if key == "clock":
		_choice("Clock display", ["dial", "digital", "both"], config.clock_mode, func(value: String) -> void: change_part(key, "clock_mode", value))
	if key == "rail_panel":
		_toggle("Fill screen height", config.full_height, func(value: bool) -> void: change_part(key, "full_height", value))
		_toggle("Hide while skill statistics visible", config.hide_with_stats, func(value: bool) -> void: change_part(key, "hide_with_stats", value))
	if key == "minimap":
		_choice("Map shape", ["square", "round"], config.map_shape, func(value: String) -> void: change_part(key, "map_shape", value))
		_choice("Minimap frame", ["match_map", "circle", "rectangle"], config.frame_shape, func(value: String) -> void: change_part(key, "frame_shape", value))
		_choice("Map colors", ["natural", "parchment", "muted"], config.map_palette, func(value: String) -> void: change_part(key, "map_palette", value))
		_toggle("Map name above minimap", config.map_title, func(value: bool) -> void: change_part(key, "map_title", value))
		_choice("Map directions", ["all", "north", "none"], config.map_directions, func(value: String) -> void: change_part(key, "map_directions", value))
		_choice("North marker", ["letter", "arrow"], config.north_marker, func(value: String) -> void: change_part(key, "north_marker", value))
		_number("Direction distance from radius", config.direction_offset, -48, 120, 1, func(value: float) -> void: change_part(key, "direction_offset", value))
		_toggle("Map label HUD background / border", config.map_label_frame, func(value: bool) -> void: change_part(key, "map_label_frame", value))
	if key == "objectives":
		_toggle("Compact objectives", config.compact, func(value: bool) -> void: change_part(key, "compact", value))
	if key == "party":
		_toggle("Compact roster (actions appear on hover)", config.compact, func(value: bool) -> void: change_part(key, "compact", value))
		_toggle("Include yourself in roster", config.show_self, func(value: bool) -> void: change_part(key, "show_self", value))
		_toggle("Detailed player summary", config.show_player_details, func(value: bool) -> void: change_part(key, "show_player_details", value))
	if key in ["chat", "system_chat"]:
		_toggle("Compact header (controls appear on hover)", config.compact, func(value: bool) -> void: change_part(key, "compact", value))
	if key == "player_card":
		_toggle("Show food, load and action", config.show_secondary, func(value: bool) -> void: change_part(key, "show_secondary", value))
	if key == "nameplate":
		var hint := Label.new()
		hint.text = "This banner follows your character in the world."
		hint.add_theme_font_size_override("font_size", 12)
		details.add_child(hint)
		for field: String in model.working.banner_options:
			_toggle(field.replace("_", " ").capitalize(), model.working.banner_options[field], func(value: bool) -> void:
				_checkpoint("banner:" + field)
				model.working.banner_options[field] = value
				apply_layout())
		var colors := preload("res://src/ui/banner_color_controls.gd").new()
		colors.name = "BannerColors"
		colors.set_meta("option_caption", "Banner colors")
		details.add_child(colors)
		colors.sync_colors(model.working.banner_colors, model.working.resource_colors)
		colors.color_changed.connect(change_banner_color)
		colors.sync_changed.connect(set_banner_color_sync)
		colors.sync_all_changed.connect(func(enabled: bool) -> void: set_banner_color_sync("all", enabled))
		colors.reset_requested.connect(reset_banner_colors)
	if key in ["spells", "items", "utilities", "resources"]:
		_choice("Orientation", ["horizontal", "vertical"], str(config.orientation), func(value: String) -> void: change_part(key, "orientation", value))
		if key == "resources":
			_number("Rows", int(config.rows), 1, 6, 1, func(value: float) -> void: change_part(key, "rows", int(value)))
		else:
			var count := _grid_count(key)
			var columns := _grid_columns(key)
			_number("Rows", ceili(float(count) / columns), 1, count, 1, func(value: float) -> void: set_grid_rows(key, int(value)))
			_number("Columns", columns, 1, count, 1, func(value: float) -> void: set_grid_columns(key, int(value)))
			_toggle("Reflow grid when resized", config.grid_mode == "aspect", func(value: bool) -> void: change_part(key, "grid_mode", "aspect" if value else "fixed"))
	if key in ["spells", "items"]:
		_number("Quick spell count" if key == "spells" else "Quick item count", int(config.slots), 1, 12 if key == "spells" else 8, 1,
			func(value: float) -> void: change_part(key, "slots", int(value)))
	if key == "spells":
		_toggle("Show target and power badges", config.show_badges, func(value: bool) -> void: change_part(key, "show_badges", value))
	for axis: String in ["x", "y"]:
		var offset_key := "dock_offset" if config.dock_target != "none" else "offset"
		_number("Horizontal offset" if axis == "x" else "Vertical offset", config[offset_key].x if axis == "x" else config[offset_key].y,
			-4096, 4096, 4, func(value: float) -> void:
				var offset: Vector2 = model.working.parts[key][offset_key]
				if axis == "x": offset.x = value
				else: offset.y = value
				change_part(key, offset_key, offset))
	if key == "utilities":
		for button: Button in icon_buttons:
			var label := button.tooltip_text.split("\n")[0]
			_toggle(label if not label.is_empty() else str(button.name).trim_suffix("Button"),
				bool(model.working.icons.get(str(button.name), model.working.icons.get("__default", true))), func(value: bool) -> void:
					_checkpoint("icon:" + str(button.name))
					model.working.icons[str(button.name)] = value
					apply_layout())
	if key in ["resources", "food_meter", "load_meter", "xp_meter"]:
		_toggle("Show resource labels", config.show_labels, func(value: bool) -> void: change_part(key, "show_labels", value))
		_toggle("Show resource values", config.show_values, func(value: bool) -> void: change_part(key, "show_values", value))
		_toggle("Show resource icons", config.show_icons, func(value: bool) -> void: change_part(key, "show_icons", value))
		_choice("Load display", ["carried", "free"], config.load_display, func(value: String) -> void: change_part(key, "load_display", value))
		if key != "resources":
			var resource: String = str(config.meter_keys[0]) if not config.meter_keys.is_empty() else {"food_meter":"food", "load_meter":"load", "xp_meter":"experience"}[key]
			_choice("Meter resource", ["health", "mana", "food", "load", "action", "experience"], resource, func(value: String) -> void: change_part(key, "meter_keys", [value]))
	if key == "resources":
		_resource_options()
	elif key in ["food_meter", "load_meter", "xp_meter"]:
		var meter: String = str(config.meter_keys[0])
		_color("Resource color", model.working.resource_colors[meter], func(value: Color) -> void: change_resource_color(meter, value))
	if key in ["chat", "system_chat"]:
		var surface: PanelContainer = parts[key]
		_number("Text size", surface.options.font_size, 10, 28, 1, func(value: float) -> void:
				_checkpoint("chat_font:" + key)
				surface.options.font_size = int(value)
				surface.apply_options()
				_capture_chat(model.working, key))
		_toggle("Lock window", bool(surface.options.locked), func(value: bool) -> void:
				_checkpoint("chat_lock:" + key)
				surface.options.locked = value
				surface.apply_options()
				_capture_chat(model.working, key))
		if key == "chat":
			_toggle("Combine system and conversation feeds", bool(surface.options.combined), func(value: bool) -> void:
				_checkpoint("combine_chat")
				surface.options.combined = value
				surface.apply_options()
				main._on_chat_configuration_changed("combined", value)
				_capture_chat(model.working, key))
	if key in ["rail_panel", "utilities", "spells", "items", "chat", "system_chat", "party", "minimap", "compass", "clock", "resources", "food_meter", "load_meter", "xp_meter", "player_card", "target", "gauntlet_loot", "rare_drops"]:
		for axis: String in ["x", "y"]:
			var dimensions: Vector2 = _root(key).size
			var minimum: Vector2 = _root(key).get_combined_minimum_size()
			if key in ["utilities", "spells", "items"]: minimum = Vector2(32, 32)
			_number("Window width" if axis == "x" else "Window height", dimensions.x if axis == "x" else dimensions.y,
				maxf(16, minimum.x if axis == "x" else minimum.y), 1600 if axis == "x" else 900, 1, func(value: float) -> void:
					_checkpoint("dimensions:" + key + axis)
					var requested: Vector2 = _root(key).size
					if axis == "x": requested.x = value
					else: requested.y = value
					model.working.parts[key].dimensions = requested
					if key == "rail_panel" and axis == "y": model.working.parts[key].full_height = false
					if key in ["utilities", "spells", "items"]:
						model.working.parts[key].grid_mode = "aspect"
					if key != "party": model.working.chat_windows.erase(key)
					apply_layout())
	# Keep the controls players look for first near the top of each tab.
	var first: Array[String] = ["Show " + Presets.PARTS[key], "Quick spell count", "Quick item count", "Snap resize edges"]
	if key == "minimap": first.append_array(["Minimap frame", "Map shape", "Map colors", "Map name above minimap", "Map directions", "North marker", "Direction distance from radius", "Map label HUD background / border"])
	if key == "compass": first.append_array(["Compass display", "Outside compass circle"])
	if key == "clock": first.append("Clock display")
	if key == "nameplate": first.append("Banner colors")
	first.append_array(["HUD background", "HUD border", "HUD border design"])
	var insertion := 0
	for caption: String in first:
		for child: Control in details.get_children():
			if child.get_meta("option_caption", "") == caption:
				details.move_child(child, insertion)
				insertion += 1
	_filter_details()
	_center_editor.call_deferred()
	queue_redraw()

func _filter_details() -> void:
	for child: Control in details.get_children():
		var caption: String = child.get_meta("option_caption", "")
		var group := "Options"
		if caption in ["Position", "Scale", "Width scale", "Height scale", "Orientation", "Rows", "Columns", "Reflow grid when resized", "Visible slots", "Horizontal offset", "Vertical offset", "Window width", "Window height", "Snap resize edges"]: group = "Layout"
		elif caption in ["Appearance", "Window frame", "HUD background", "HUD border", "HUD border design", "Window color", "Border color", "Text color", "Resource color", "Map shape", "Minimap frame", "Map colors", "Load display", "Compass display", "Outside compass circle", "Show area name", "Show resource labels", "Show resource values", "Show resource icons"]: group = "Look"
		elif caption.begins_with("Dock"): group = "Dock"
		if caption in ["Map name above minimap", "Map directions", "North marker", "Direction distance from radius", "Map label HUD background / border"]: group = "Look"
		if caption in ["Background opacity", "Border opacity", "Slot border", "Slot border color", "Icon opacity", "Unavailable icon opacity", "Flush slot edges", "Slot spacing"]: group = "Look"
		if caption == "Fill screen height": group = "Layout"
		if caption == "Banner colors": group = "Look"
		child.visible = group == _detail_group or caption in ["Circle parts", "Dock status", "Show curve"] or caption == "Show " + Presets.PARTS[selected]
		if caption in ["Quick spell count", "Quick item count"]: child.show()
		# This surface follows a world actor rather than a screen anchor.
		if selected == "nameplate" and group in ["Layout", "Dock"] and caption != "Scale": child.hide()
		if selected == "medallion" and _selected_arc >= 0 and group in ["Layout", "Dock"]: child.hide()

func _toggle(caption: String, value: bool, callback: Callable) -> void:
	var box := CheckBox.new()
	box.text = caption
	box.clip_text = true
	box.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	box.tooltip_text = caption
	box.set_meta("option_caption", caption)
	box.button_pressed = value
	box.add_theme_font_size_override("font_size", 12)
	box.toggled.connect(callback)
	details.add_child(box)

func _arc_name(index: int) -> String:
	return ("Left" if index < 4 else "Right") + " curve %d" % (index % 4 + 1)

func _arc_selector() -> void:
	var center_row := HBoxContainer.new()
	center_row.set_meta("option_caption", "Circle parts")
	center_row.add_child(_button("Center", func() -> void: select_component("medallion")))
	for side: int in 2:
		var row := HBoxContainer.new()
		row.set_meta("option_caption", "Circle parts")
		var label := Label.new()
		label.text = "Left" if side == 0 else "Right"
		label.custom_minimum_size.x = 42
		row.add_child(label)
		for slot: int in 4:
			var index := side * 4 + slot
			var button := _button(str(slot + 1), func() -> void: select_component("medallion", index))
			button.custom_minimum_size.x = 38
			button.tooltip_text = _arc_name(index) + (" · visible" if model.working.parts.medallion.arcs[index].enabled else " · hidden; click to enable or edit")
			button.add_theme_color_override("font_color", model.working.parts.medallion.arcs[index].color)
			if _selected_arc == index: button.add_theme_stylebox_override("normal", HudChrome.box(Color("42341e"), Color("e6bf73"), 5))
			row.add_child(button)
		if side == 0:
			for child: Node in row.get_children(): child.reparent(center_row)
			row.free()
			details.add_child(center_row)
		else: details.add_child(row)

func dock_component(key: String, target: String, side: String) -> void:
	_checkpoint("dock:" + key)
	var config: Dictionary = model.working.parts[key]
	if target == "screen":
		config.dock_target = "none"
		config.edge_dock = side
		config.anchor = "free"
		config.position = _root(key).position / main.game_view.size
		config.offset = Vector2.ZERO
		model.working.legacy = false
		apply_layout()
		if is_open(): select_component(selected, _selected_arc)
		return
	config.edge_dock = "none"
	if target == "none":
		if config.extend_to_edge or config.dock_align == "stretch": config.dimensions = _root(key).size
		config.extend_to_edge = false
		config.anchor = "free"
		config.position = _root(key).position / main.game_view.size
		config.offset = Vector2.ZERO
	else:
		config.enabled = true
		if target == "medallion" and key in ["spells", "items"]: config.orientation = "horizontal"
	config.dock_target = target
	config.dock_side = side
	config.dock_gap = 0
	model.working.legacy = false
	model.working = Presets.normalise(model.working)
	apply_layout()
	if is_open(): select_component(selected, _selected_arc)

func _dock_root(key: String) -> String:
	var seen: Array[String] = []
	while key not in seen:
		seen.append(key)
		var target: String = model.working.parts[key].dock_target
		if target == "none" or not _root(target).is_visible_in_tree(): return key
		key = target
	return key

func _color(caption: String, value: Color, callback: Callable) -> void:
	var row := _option_row(caption)
	var picker := ColorPickerButton.new()
	picker.color = value
	picker.custom_minimum_size = Vector2(100, 26)
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.color_changed.connect(callback)
	row.add_child(picker)

func change_arc(index: int, field: String, value: Variant) -> void:
	if index < 0 or index >= 8: return
	_checkpoint("arc:%d:%s" % [index, field])
	model.working.parts.medallion.arcs[index][field] = value
	if field == "resource": model.working.parts.medallion.arcs[index].color = Presets.RESOURCE_COLORS[value]
	model.working.legacy = false
	model.working = Presets.normalise(model.working)
	apply_layout()

func _choice(caption: String, values: Array, current: String, callback: Callable) -> void:
	var row := _option_row(caption)
	var choice := OptionButton.new()
	choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	choice.add_theme_font_size_override("font_size", 12)
	for value: String in values:
		var label := value.replace("_", " ").capitalize()
		if caption == "Dock to": label = str(Presets.PARTS.get(value, label))
		elif caption == "Appearance": label = Presets.BUILT_INS.get(value, label)
		choice.add_item(label)
	choice.select(maxi(0, values.find(current)))
	choice.item_selected.connect(func(index: int) -> void: callback.call(values[index]))
	row.add_child(choice)

func _number(caption: String, value: float, low: float, high: float, step: float, callback: Callable) -> void:
	var row := _option_row(caption)
	var spin := SpinBox.new()
	spin.min_value = low
	spin.max_value = high
	spin.step = step
	spin.value = value
	if caption.ends_with("opacity"): spin.suffix = "%"
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spin.value_changed.connect(callback)
	row.add_child(spin)

func _option_row(caption: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.set_meta("option_caption", caption)
	var label := Label.new()
	label.text = caption
	label.custom_minimum_size.x = 145
	label.add_theme_font_size_override("font_size", 12)
	row.add_child(label)
	details.add_child(row)
	return row

func change_part(key: String, field: String, value: Variant) -> void:
	if not model.working.parts.has(key): return
	_checkpoint("part:%s:%s" % [key, field])
	if key in ["utilities", "spells", "items"] and field in ["orientation", "rows", "columns"]:
		model.working.parts[key].dimensions = Vector2.ZERO
		model.working.parts[key].grid_mode = "fixed"
		if field != "columns": model.working.parts[key].columns = 0
	_capture_positions()
	model.working.parts[key][field] = value
	if field == "text_color":
		model.working.parts[key].text_color_custom = true
	if field == "frame_style":
		model.working.parts[key].show_background = value != "floating"
		model.working.parts[key].show_border = value != "floating"
	elif field in ["show_background", "show_border"]:
		var config: Dictionary = model.working.parts[key]
		config.frame_style = "panel" if config.show_background or config.show_border else "floating"
	if field in ["frame_style", "show_background", "show_border"]:
		var config: Dictionary = model.working.parts[key]
		if config.show_background and config.background_color.a == 0 and key not in ["chat", "system_chat"]: config.background_color.a = 0.93
		if config.show_border and config.border_color.a == 0: config.border_color.a = 1.0
	if key in ["chat", "system_chat"] and field == "background_color":
		Presets.set_chat_opacity(model.working, key, model.working.parts[key].background_color.a)
		if model.working.parts[key].background_color.a > 0:
			model.working.parts[key].show_background = true
			model.working.parts[key].frame_style = "panel"
	if field == "center_resource": model.working.parts.medallion.center_color = Presets.RESOURCE_COLORS[value]
	if field != "enabled" or key in ["medallion", "player_card", "food_meter", "load_meter", "xp_meter"] and value == true: model.working.legacy = false
	model.working = Presets.normalise(model.working)
	apply_layout()
	_refresh_actions()
	if key in ["chat", "system_chat"]: _refresh_chat_opacity_controls(key)
	if is_open(): message.text = "Done & save keeps changes for this option. Save as new creates a separate preset."

func _refresh_chat_opacity_controls(key: String) -> void:
	if selected != key or not is_open(): return
	for row: Control in details.get_children():
		var caption: String = row.get_meta("option_caption", "")
		if caption == "Background opacity":
			(row.get_child(1) as SpinBox).set_value_no_signal(model.working.parts[key].background_color.a * 100)
		elif caption == "Window color":
			var picker: ColorPickerButton = row.get_child(1)
			picker.set_block_signals(true)
			picker.color = model.working.parts[key].background_color
			picker.set_block_signals(false)

func _resource_options() -> void:
	var hint := Label.new()
	hint.text = "Order · visibility · color (shared by resource icons)"
	hint.add_theme_font_size_override("font_size", 11)
	details.add_child(hint)
	for index: int in main._hud_meter_order.size():
		var meter: String = main._hud_meter_order[index]
		var row := HBoxContainer.new()
		row.name = "ResourceOption_" + meter
		row.set_meta("option_caption", "Resource " + meter)
		var visible_box := CheckBox.new()
		visible_box.text = "Ether" if meter == "mana" else meter.capitalize()
		visible_box.set_pressed_no_signal(bool(main._hud_meter_visible.get(meter, true)))
		visible_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		visible_box.toggled.connect(func(value: bool) -> void:
			_checkpoint("meter:" + meter)
			model.working.meters[meter] = value
			apply_layout())
		row.add_child(visible_box)
		for delta: int in [-1, 1]:
			var arrow := _button("↑" if delta < 0 else "↓", func() -> void: move_resource(meter, delta))
			arrow.custom_minimum_size = Vector2(28, 26)
			arrow.add_theme_font_size_override("font_size", 16)
			arrow.disabled = index + delta < 0 or index + delta >= main._hud_meter_order.size()
			arrow.tooltip_text = "Move earlier" if delta < 0 else "Move later"
			row.add_child(arrow)
		var picker := ColorPickerButton.new()
		picker.color = model.working.resource_colors[meter]
		picker.custom_minimum_size = Vector2(44, 24)
		picker.tooltip_text = "Bar and icon color"
		picker.color_changed.connect(func(value: Color) -> void: change_resource_color(meter, value))
		row.add_child(picker)
		details.add_child(row)

func move_resource(meter: String, delta: int) -> void:
	var order: Array = main._hud_meter_order.duplicate()
	var index := order.find(meter)
	if index < 0 or index + delta < 0 or index + delta >= order.size(): return
	_checkpoint("resource_order")
	order.remove_at(index)
	order.insert(index + delta, meter)
	model.working.meter_order = order
	model.working.legacy = false
	apply_layout()
	select_component(selected)

func change_resource_color(meter: String, color: Color) -> void:
	if not Presets.RESOURCE_COLORS.has(meter): return
	_checkpoint("resource_color:" + meter)
	model.working.resource_colors[meter] = color
	model.working.legacy = false
	apply_layout()

func change_banner_color(item: String, color: Color) -> void:
	if not Presets.BannerColors.LABELS.has(item): return
	_checkpoint("banner_color:" + item)
	model.working.banner_colors.colors[item] = color
	model.working.banner_colors.synced[item] = false
	_banner_colors_changed()

func set_banner_color_sync(item: String, enabled: bool) -> void:
	if item != "all" and not Presets.BannerColors.RESOURCES.has(item): return
	_checkpoint("banner_color_sync:" + item)
	for resource: String in Presets.BannerColors.RESOURCES:
		if item == "all" or resource == item:
			model.working.banner_colors.synced[resource] = enabled
	_banner_colors_changed()

func reset_banner_colors() -> void:
	_checkpoint("banner_colors_reset")
	model.working.banner_colors = Presets.BannerColors.normalise({})
	_banner_colors_changed()

func _banner_colors_changed() -> void:
	model.working.banner_colors = Presets.BannerColors.normalise(model.working.banner_colors)
	apply_layout()
	sync_settings()

func change_frame_color(key: String, field: String, color: Color) -> void:
	var config: Dictionary = model.working.parts[key]
	var enabled: bool = config.show_background if field == "background_color" else config.show_border
	# Old floating XP strips saved a zero-alpha color. Selecting a new RGB
	# color on an enabled frame should produce a visible change. Opacity has
	# its own explicit control, including zero for intentional transparency.
	if enabled and color.a == 0 and config[field].a == 0 and key not in ["chat", "system_chat"]:
		color.a = 0.93 if field == "background_color" else 1.0
	change_part(key, field, color)

func _grid_count(key: String) -> int:
	if key != "utilities": return int(model.working.parts[key].slots)
	var count := 0
	for button: Button in icon_buttons:
		if button.visible: count += 1
	return maxi(1, count)

func _grid_columns(key: String) -> int:
	if key == "spells": return main.casting_bar._column.columns
	if key == "items": return main.quick_slot_container.columns
	return utility_grid.columns

func set_grid_rows(key: String, rows: int) -> void:
	_checkpoint("grid:" + key)
	var config: Dictionary = model.working.parts[key]
	config.orientation = "horizontal"
	config.rows = rows
	config.columns = 0
	config.dimensions = Vector2.ZERO
	config.grid_mode = "fixed"
	model.working.legacy = false
	model.working = Presets.normalise(model.working)
	apply_layout()
	if is_open(): select_component(key)

func set_grid_columns(key: String, columns: int) -> void:
	_checkpoint("grid:" + key)
	var config: Dictionary = model.working.parts[key]
	config.orientation = "horizontal"
	config.columns = columns
	config.dimensions = Vector2.ZERO
	config.grid_mode = "fixed"
	model.working.legacy = false
	model.working = Presets.normalise(model.working)
	apply_layout()
	if is_open(): select_component(key)

func _capture_chat(value: Dictionary, key: String) -> void:
	var surface: PanelContainer = parts[key]
	value.chat_windows[key] = {"size": surface.size, "options": surface.options.duplicate(true)}
	value.parts[key].dimensions = surface.size
	Presets.set_chat_opacity(value, key, surface.options.background_opacity)

func _capture_live(value: Dictionary) -> void:
	for key: String in ["chat", "system_chat"]:
		_capture_chat(value, key)
		value.parts[key].enabled = bool(parts[key].options.visible)
	value.parts.minimap.enabled = bool(main._minimap_visible)
	value.parts.minimap.map_shape = main._minimap_shape
	for field: String in Presets.BANNER_FIELDS: value.banner_options[field] = main._banner_option(field)
	value.parts.party.dimensions = main.extension_windows._party_expanded_size if main.extension_windows._party_custom_size else Vector2.ZERO
	for key: String in SWITCHES:
		value.parts[key].enabled = bool(main._hud_element_options[SWITCHES[key]])
	var analog: bool = main._hud_element_options.get("analog_clock", true)
	var digital: bool = main._hud_element_options.get("digital_clock", true)
	value.parts.clock.enabled = analog or digital
	if analog or digital: value.parts.clock.clock_mode = "both" if analog and digital else ("dial" if analog else "digital")
	value.meters = main._hud_meter_visible.duplicate()
	value.meter_order = main._hud_meter_order.duplicate()
	for button: Button in icon_buttons: value.icons[str(button.name)] = button.visible
	value.parts.spells.slots = main.casting_bar.visible_slot_count
	value.parts.spells.orientation = "horizontal" if main.casting_bar.horizontal else "vertical"
	if main.casting_bar.workspace_layout.is_empty():
		value.parts.spells.enabled = main.casting_bar.panel.visible or main.casting_bar.launcher.visible
		value.native_spell_bar = main.casting_bar.hud_layout()

func _capture_positions() -> void:
	# Chat remains independently draggable outside this editor. Snapshot actual
	# positions when saving; do not recreate windows or their input destinations.
	for key: String in ["chat", "system_chat", "party"]:
		if model.working.parts[key].anchor == "free":
			model.working.parts[key].position = _normal_position(_root(key))

func _normal_position(control: Control) -> Vector2:
	return ((main.game_view.get_global_transform().affine_inverse() * control.global_position) / main.game_view.size.max(Vector2.ONE)).clamp(Vector2.ZERO, Vector2.ONE)

func _remember_moved(key: String, persist := true) -> void:
	if _applying or not model.loaded and bool(model.working.legacy): return
	model.working.parts[key].anchor = "free"
	model.working.parts[key].dock_target = "none"
	model.working.parts[key].edge_dock = "none"
	model.working.parts[key].position = _normal_position(parts[key])
	model.working.parts[key].offset = Vector2.ZERO
	if key in ["chat", "system_chat"]: _capture_chat(model.working, key)
	elif key == "party": model.working.parts.party.dimensions = main.extension_windows._party_expanded_size if main.extension_windows._party_custom_size else Vector2.ZERO
	elif key == "minimap": model.working.parts[key].dimensions = parts[key].size
	if not persist:
		_update_chrome()
		return
	queue_layout()
	if not is_open(): _store()

func _casting_changed() -> void:
	if _applying or not ready_to_layout: return
	model.working.parts.spells.orientation = "horizontal" if main.casting_bar.horizontal else "vertical"
	model.working.parts.spells.slots = main.casting_bar.visible_slot_count
	model.working.parts.spells.enabled = main.casting_bar.panel.visible
	if not main.casting_bar.workspace_layout.is_empty():
		model.working.parts.spells.dock_target = main.casting_bar.workspace_layout.get("dock_target", "none")
		model.working.parts.spells.anchor = main.casting_bar.workspace_layout.get("anchor", "free")
		for field: String in ["columns", "grid_mode"]:
			model.working.parts.spells[field] = main.casting_bar.workspace_layout[field]
		if main.casting_bar.workspace_layout.dimensions == Vector2.ZERO: model.working.parts.spells.dimensions = Vector2.ZERO
		if model.working.parts.spells.anchor == "free":
			model.working.parts.spells.position = _normal_position(parts.spells)
			model.working.parts.spells.offset = Vector2.ZERO
		queue_layout()
	if not is_open(): _store()

func save_custom(replace: bool) -> void:
	if replace and not model.custom.has(model.active):
		message.text = "Done & save keeps this option's changes. Enter a name and choose Save as new for a separate preset."
		return
	_checkpoint("save_custom")
	_capture_positions()
	_capture_live(model.working)
	var id := model.save_custom(preset_name.text, model.active if replace else "")
	if id.is_empty():
		message.text = "Five custom designs are saved. Update one, or delete a custom design to make room."
		return
	_refresh_pickers()
	message.text = "Custom preset prepared. Choose Done & save to keep it."

func delete_custom() -> void:
	if not model.custom.has(model.active): return
	_checkpoint("delete_custom")
	model.delete_custom(model.active)
	apply_layout()
	_refresh_pickers()
	select_component(selected)
	message.text = "Custom design deleted. Undo or Cancel recovers it; Done & save keeps the change."

func _store() -> Error:
	var error := model.save_file(preferences_path)
	if error == OK: model.loaded = true
	if error != OK:
		push_warning("Could not save HUD presets: " + error_string(error))
		if message != null: message.text = "Could not save your HUD: " + error_string(error)
	return error

func sync_settings() -> void:
	# Existing settings pages and shortcuts remain valid after selecting a
	# preset. Their choices must not be replaced by an older workspace snapshot
	# at the next launch. Preview changes are committed only by the editor.
	if not ready_to_layout or _applying or is_open(): return
	if not model.loaded and bool(model.working.legacy): return
	_capture_live(model.working)
	_store()

func commit() -> Error:
	_capture_positions()
	_capture_live(model.working)
	for key: String in ["chat", "system_chat"]: parts[key].save_layout()
	main._save_hud_settings()
	main._save_hud_layout()
	return _store()

func commit_and_close() -> void:
	if commit() != OK: return
	panel.hide()
	_drag_part = ""
	_drag_root = ""
	_snap_candidate = {}
	_resizing = false
	queue_redraw()

func cancel_edit() -> void:
	if _before.is_empty(): return
	model.working = _before.duplicate(true)
	model.custom = _custom_before.duplicate(true)
	model.builtin_overrides = _builtins_before.duplicate(true)
	model.active = _active_before
	apply_layout()
	_refresh_pickers()
	panel.hide()
	_drag_part = ""
	_drag_root = ""
	_snap_candidate = {}
	_resizing = false
	queue_redraw()

## Canvas-drawn components receive resolved colors without writing the runtime
## projection into the player's saved component preferences.
func _text_config(key: String, role: String) -> Dictionary:
	var config: Dictionary = model.working.parts[key].duplicate(true)
	if not bool(config.get("text_color_custom", false)):
		config.text_color = TextColors.color(role)
	return config

func apply_layout() -> void:
	if not ready_to_layout: return
	_applying = true
	var legacy := bool(model.working.legacy)
	frame_overlay.visible = not legacy
	main.hud_logo.texture = _centered_logo_texture if not legacy and model.working.parts.logo.style == "heritage" and _centered_logo_texture != null else _logo_texture
	for key: String in ["chat", "system_chat", "party", "minimap", "objectives"]:
		var dragger := parts[key].get_node_or_null("WindowDrag") as WindowDrag
		if dragger != null:
			dragger.reserved_right = WindowDrag.RESERVED_RIGHT_RAIL if legacy else 6.0
			dragger.reserved_bottom = WindowDrag.RESERVED_BOTTOM_BAR if legacy else 6.0
			dragger.edge_margin = WindowDrag.EDGE_MARGIN if legacy else 0.0
			if not legacy and model.working.parts[key].edge_dock != "none":
				dragger.reserved_right = 0
				dragger.reserved_bottom = 0
			if key in ["chat", "system_chat"]:
				dragger.bottom_hud = original[key].bottom_hud if legacy else null
				parts[key].bottom_hud = original[key].bottom_hud if legacy else null
			elif key == "party": dragger.bottom_hud = original[key].bottom_hud if legacy else null
	var row: Control = main.get_node("GameView/Quickbar/QuickRows/Buttons")
	for button: Button in icon_buttons:
		var parent: Node = row if legacy else utility_grid
		if button.get_parent() != parent: button.reparent(parent, false)
		button.visible = bool(model.working.icons.get(str(button.name), model.working.icons.get("__default", true)))
	if legacy:
		for index: int in icon_buttons.size(): row.move_child(icon_buttons[index], index)
	row.visible = legacy
	utility_grid.visible = not legacy
	main.right_rail.visible = legacy
	for key: String in containers:
		var source: Control = original[key].node
		var parent: Node = original[key].parent if legacy else containers[key]
		if source.get_parent() != parent:
			source.reparent(parent, false)
			if legacy: parent.move_child(source, mini(int(original[key].index), parent.get_child_count() - 1))
		parts[key] = source
		if key == "clock": source.show() # The wrapper owns visibility; the two live children own the clock mode.
		(containers[key] as Control).visible = not legacy and bool(model.working.parts[key].enabled)
	main.get_node("GameView/ResourceHud").visible = legacy
	main.get_node("GameView/RailMeters").visible = legacy
	main.get_node("%ExperienceMeter/ExperienceSkillLabel").visible = legacy
	for key: String in SWITCHES:
		main._hud_element_options[SWITCHES[key]] = bool(model.working.parts[key].enabled)
	var clock: Dictionary = model.working.parts.clock
	main._hud_element_options.analog_clock = clock.enabled and clock.clock_mode != "digital"
	main._hud_element_options.digital_clock = clock.enabled and clock.clock_mode != "dial"
	main._apply_hud_element_options()
	clock_art.configure(main, _text_config("clock", "hud_detail"), legacy)
	for field: String in model.working.banner_options:
		if main._banner_option_boxes.has(field): main._banner_option_boxes[field].set_pressed_no_signal(model.working.banner_options[field])
	main._apply_banner_options()
	for key: String in model.working.meters:
		if main._hud_meter_visible.has(key): main._hud_meter_visible[key] = model.working.meters[key]
	if model.working.meter_order.size() == 6: main._hud_meter_order.assign(model.working.meter_order)
	main._apply_hud_meter_layout()
	main.bottom_meters.visible = bool(model.working.parts.resources.enabled)
	modern_resources.visible = not legacy and bool(model.working.parts.resources.enabled)
	(containers.resources as Control).hide()
	if not legacy: modern_resources.configure(main, _text_config("resources", "hud_meter"), model.working.resource_colors)
	for key: String in ["food_meter", "load_meter", "xp_meter", "player_card"]:
		parts[key].configure(main, _text_config(key, "hud_detail" if key == "player_card" else "hud_meter"), model.working.resource_colors)
	target_card.configure(main, _text_config("target", "hud_detail"), model.working.resource_colors)
	var summary_config: Dictionary = _text_config("party", "hud_detail")
	summary_config.show_background = false
	summary_config.show_border = false
	party_summary.configure(main, summary_config, model.working.resource_colors)
	party_summary.visible = not legacy and summary_config.show_self and summary_config.show_player_details and not main.extension_windows._party_collapsed
	target_card.visible = not legacy and bool(model.working.parts.target.enabled)
	(containers.target as Control).hide()
	for key: String in ["chat", "system_chat"]:
		var surface: PanelContainer = parts[key]
		var saved: Dictionary = model.working.chat_windows.get(key, {})
		if saved.has("options"): surface.options.merge(saved.options, true)
		surface.options.visible = bool(model.working.parts[key].enabled)
		surface.apply_options()
		Presets.set_chat_opacity(model.working, key, surface.options.background_opacity)
		if saved.has("size"): surface.resize_window(saved.size)
		elif model.working.parts[key].dimensions != Vector2.ZERO: surface.resize_window(model.working.parts[key].dimensions)
	var party_size: Vector2 = model.working.parts.party.dimensions
	if party_size != Vector2.ZERO: main.extension_windows.resize_party_window(party_size)
	else:
		main.extension_windows._party_custom_size = false
		main.extension_windows._layout_party()
	main._on_chat_configuration_changed("", null)
	main._minimap_visible = bool(model.working.parts.minimap.enabled)
	main.minimap_frame.visible = main._minimap_visible
	minimap_labels.visible = not legacy
	minimap_labels.configure(main, model.working.parts.minimap)
	modern_compass.visible = not legacy and bool(model.working.parts.compass.enabled)
	(parts.compass as Control).visible = legacy and bool(model.working.parts.compass.enabled)
	if not legacy:
		main._minimap_shape = "round" if model.working.parts.minimap.frame_shape == "circle" else model.working.parts.minimap.map_shape
		main._apply_minimap_shape()
		modern_compass.configure(main, _text_config("compass", "hud_detail"))
		(parts.medallion as Control).configure(_text_config("medallion", "hud_detail"))
	main._request_map_redraw()
	for key: String in Presets.PARTS:
		if key in ["chat", "system_chat", "spells", "resources", "compass", "objectives", "gauntlet_loot", "rare_drops"]: continue
		_root(key).visible = bool(model.working.parts[key].enabled) \
			or (key == "party" and not str(AppState.party.get("invited_by", "")).is_empty())
	main.extension_windows._sync_tracked_quest()
	_sync_gauntlet_hud()
	if not model.working.parts.objectives.enabled: parts.objectives.hide()
	if legacy:
		for chrome: Node2D in _chrome.values(): chrome.hide()
		main.extension_windows._party_controls_visible = true
		for key: String in ["chat", "system_chat"]: parts[key]._header.show()
		(parts.party.get_node("Body/PartyActions") as Control).visible = not main.extension_windows._party_collapsed
		(parts.party.get_node("Body/Header") as Control).show()
		for child: Control in main.extension_windows.party_rows.get_children(): child.show()
		var parchment: PanelContainer = parts.objectives.get_node("TrackerParchment")
		main.extension_windows._style_quest_tracker(parchment, parchment.get_node("ParchmentTexture"))
		for button: Button in _button_styles:
			SlotStyle.clear(button)
			button.add_theme_stylebox_override("normal", _button_styles[button])
			button.size_flags_horizontal = _button_flags[button].x
			button.size_flags_vertical = _button_flags[button].y
		for key: String in ["chat", "system_chat"]:
			(parts[key]._fade.material as ShaderMaterial).set_shader_parameter("backdrop_color", Color(0.015, 0.018, 0.016, 1))
		main._minimap_shape = model.working.parts.minimap.map_shape
		main._apply_minimap_shape()
		main.casting_bar.workspace_layout = {}
		main.casting_bar.panel.scale = Vector2.ONE
		main.quick_slot_container.columns = 1
		for button: Button in main.quick_slot_buttons: button.show()
		for key: String in original:
			if key in ["chat", "system_chat", "party", "spells"]: continue
			_restore_original(key)
		var native: Dictionary = model.working.native_spell_bar
		main.casting_bar.restore_hud_layout(native if not native.is_empty() else {
			"docked": true, "horizontal": false, "slot_count": 6, "expanded": model.working.parts.spells.enabled})
		main._fit_hud_action_buttons()
		for key: String in ["chat", "system_chat"]: _tint_text(parts[key], Color.WHITE, true)
		for node: Control in _original_colors:
			if is_instance_valid(node):
				node.remove_meta("hud_text_color_override")
				var field: String = _original_colors[node].field
				var roles: Dictionary = node.get_meta("text_color_roles", {})
				if roles.has(field): TextColors.bind(node, str(roles[field]), field)
				else: _restore_text(node)
	else:
		main.casting_bar.workspace_layout = model.working.parts.spells.duplicate(true)
		main.casting_bar.horizontal = model.working.parts.spells.orientation == "horizontal"
		main.casting_bar.visible_slot_count = int(model.working.parts.spells.slots)
		for key: String in Presets.PARTS:
			if key in ["spells", "medallion"]: continue
			_style_part(key)
		_layout_menu_icons()
		_layout_items()
		main.bottom_meters.custom_minimum_size = Vector2.ZERO
		(parts.utilities as Control).reset_size()
		for key: String in ["skills", "clock", "status", "timer", "research"]: _root(key).reset_size()
	if main._minimap_mask_material != null:
		var palette: String = "natural" if legacy else model.working.parts.minimap.map_palette
		main._minimap_mask_material.set_shader_parameter("hud_palette", ["natural", "parchment", "muted"].find(palette))
	_applying = false
	# Per-item colors take precedence over the banner's general text tint.
	main._apply_banner_colors()
	main._sync_banner_color_controls()
	var banner_controls := details.get_node_or_null("BannerColors")
	if banner_controls != null:
		banner_controls.sync_colors(model.working.banner_colors, model.working.resource_colors)
	layout_hud()
	main.extension_windows._queue_party_layout()
	queue_layout()

func _restore_original(key: String) -> void:
	var saved: Dictionary = original[key]
	var control: Control = saved.node
	control.scale = saved.scale
	control.custom_minimum_size = saved.minimum
	control.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	control.anchor_left = saved.anchors[0]
	control.anchor_top = saved.anchors[1]
	control.anchor_right = saved.anchors[2]
	control.anchor_bottom = saved.anchors[3]
	control.offset_left = saved.offsets[0]
	control.offset_top = saved.offsets[1]
	control.offset_right = saved.offsets[2]
	control.offset_bottom = saved.offsets[3]
	control.add_theme_stylebox_override("panel", saved.panel_style)

func _style_part(key: String) -> void:
	var control := _root(key)
	var config: Dictionary = model.working.parts[key]
	var box := HudChrome.box(config.background_color, config.border_color, 5)
	box.set_corner_radius_all(7 if config.style == "adventure" else 2)
	if key in ["spells", "items"] and config.flush_slots: box.set_content_margin_all(0)
	if key == "clock" and config.style == "heritage": box.set_content_margin_all(3)
	if not config.show_background: box.bg_color.a = 0
	if not config.show_border: box.set_border_width_all(0)
	if key != "nameplate":
		_ensure_chrome(key)
		box.bg_color.a = 0
		box.set_border_width_all(0)
	if key == "minimap" and config.map_shape == "round": box.set_corner_radius_all(int(control.size.x / 2))
	if key in ["chat", "system_chat"]:
		var surface: PanelContainer = parts[key]
		var backdrop: Color = config.background_color
		backdrop.a = 1.0 if config.show_background else 0.0
		(surface._fade.material as ShaderMaterial).set_shader_parameter("backdrop_color", backdrop)
		box.bg_color.a = 0
		surface.add_theme_stylebox_override("panel", box)
	elif key == "gauntlet_loot":
		control.add_theme_stylebox_override("normal", box)
	else:
		control.add_theme_stylebox_override("panel", box)
	if key == "nameplate" and not main._banner_option("banner_background"): main._apply_banner_background()
	if key == "objectives":
		var parchment: PanelContainer = control.get_node("TrackerParchment")
		parchment.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
		(parchment.get_node("ParchmentTexture") as PanelContainer).add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	_tint_text(control, config.text_color, not bool(config.get("text_color_custom", false)))

func _tint_text(control: Control, color: Color, restore := false) -> void:
	if control is Label or control is RichTextLabel or control is LineEdit or control is Button:
		var field := "default_color" if control is RichTextLabel else "font_color"
		if not _original_colors.has(control):
			_original_colors[control] = {"field":field, "override":control.has_theme_color_override(field), "color":control.get_theme_color(field)}
		if restore:
			control.remove_meta("hud_text_color_override")
			var roles: Dictionary = control.get_meta("text_color_roles", {})
			if roles.has(field):
				TextColors.bind(control, str(roles[field]), field)
			else:
				_restore_text(control)
		else:
			control.set_meta("hud_text_color_override", color)
			control.add_theme_color_override(field, color)
	for child: Node in control.get_children():
		if child is Control: _tint_text(child, color, restore)

func _restore_text(control: Control) -> void:
	if not _original_colors.has(control): return
	var saved: Dictionary = _original_colors[control]
	if saved.override: control.add_theme_color_override(saved.field, saved.color)
	else: control.remove_theme_color_override(saved.field)

func _layout_menu_icons(override_size := Vector2.ZERO) -> void:
	var config: Dictionary = model.working.parts.utilities.duplicate(true)
	if override_size != Vector2.ZERO: config.dimensions = override_size / float(config.scale)
	var count := 0
	for button: Button in icon_buttons:
		if button.visible: count += 1
	var geometry := HudGrid.measure(config, count, Vector2(32, 32), _root("utilities").get_theme_stylebox("panel").get_minimum_size(), main.game_view.size / float(config.scale))
	for button: Button in icon_buttons:
		button.custom_minimum_size = Vector2(geometry.cell).floor()
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.size_flags_vertical = Control.SIZE_EXPAND_FILL
		button.add_theme_constant_override("icon_max_width", int(maxf(12, minf(geometry.cell.x, geometry.cell.y) - 6)))
		var box := HudChrome.box(config.background_color, config.border_color, 2)
		box.set_corner_radius_all(3)
		if not config.show_background: box.bg_color.a = 0
		if not config.show_border: box.set_border_width_all(0)
		button.add_theme_stylebox_override("normal", box)
	utility_grid.add_theme_constant_override("h_separation", 2)
	utility_grid.add_theme_constant_override("v_separation", 2)
	utility_grid.columns = geometry.columns
	utility_grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	utility_grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	utility_grid.reset_size()
	_root("utilities").size = geometry.size

func _layout_items(override_size := Vector2.ZERO) -> void:
	var config: Dictionary = model.working.parts.items.duplicate(true)
	if override_size != Vector2.ZERO: config.dimensions = override_size / float(config.scale)
	var grid: GridContainer = main.quick_slot_container
	var count := int(config.slots)
	grid.add_theme_constant_override("h_separation", roundi(config.slot_gap))
	grid.add_theme_constant_override("v_separation", roundi(config.slot_gap))
	var scroll: ScrollContainer = parts.items
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	# The grid already fits every slot to this area. An automatic scrollbar
	# reserves a hidden gutter and widens the panel after docking is resolved.
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER
	var index := 0
	var slot_height := 44 if config.style == "minimal" else (56 if config.style == "adventure" else 46)
	var geometry := HudGrid.measure(config, count, Vector2(42, slot_height), scroll.get_theme_stylebox("panel").get_minimum_size(), main.game_view.size / float(config.scale))
	grid.columns = geometry.columns
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	for button: Button in main.quick_slot_buttons:
		button.visible = index < count
		button.custom_minimum_size = Vector2(geometry.cell).floor()
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.size_flags_vertical = Control.SIZE_EXPAND_FILL
		button.add_theme_constant_override("icon_max_width", int(maxf(12, minf(geometry.cell.x, geometry.cell.y) - 6)))
		var box := HudChrome.box(config.background_color, config.border_color, 2)
		box.set_corner_radius_all(3 if config.style == "adventure" else 1)
		if not config.show_background: box.bg_color.a = 0
		if not SlotStyle.native_border_visible(config): box.set_border_width_all(0)
		button.add_theme_stylebox_override("normal", box)
		button.self_modulate.a = config.icon_opacity
		SlotStyle.apply(button, config)
		index += 1
	grid.reset_size()
	scroll.custom_minimum_size = Vector2.ZERO
	scroll.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	scroll.size = geometry.size

func queue_layout() -> void:
	if _layout_queued or not ready_to_layout: return
	_layout_queued = true
	layout_hud.call_deferred()

func layout_hud() -> void:
	_layout_queued = false
	if not ready_to_layout: return
	if bool(model.working.legacy):
		_center_editor()
		queue_redraw()
		return
	_layout_running = true
	_layout_menu_icons()
	_layout_items()
	for key: String in Presets.PARTS:
		var control := _root(key)
		var config: Dictionary = model.working.parts[key]
		if key == "nameplate":
			control.scale = Vector2.ONE * float(config.scale)
			continue
		if key == "spells":
			main.casting_bar.workspace_layout = config.duplicate(true)
			main.casting_bar.workspace_layout.position = _position_for(key, main.casting_bar.workspace_size(config))
			main.casting_bar._layout()
			continue
		control.scale = config.axis_scale * float(config.scale)
		if key not in ["utilities", "chat", "system_chat", "party", "items", "minimap", "compass", "medallion", "resources", "food_meter", "load_meter", "xp_meter", "player_card", "target"]: control.reset_size()
		var dimensions := control.size
		if key in ["gauntlet_loot", "rare_drops"]:
			dimensions = main.extension_windows.gauntlet_loot_window.default_hud_rect(key, main.game_view.size).size
		if config.dimensions != Vector2.ZERO and key in ["chat", "system_chat", "minimap", "compass", "clock", "research", "logo", "medallion", "resources", "food_meter", "load_meter", "xp_meter", "player_card", "target", "gauntlet_loot", "rare_drops"]:
			dimensions = config.dimensions
		elif key == "medallion": dimensions = Vector2(240, 200)
		if key == "rail_panel":
			dimensions = config.dimensions.max(Vector2(24, 24))
			if config.full_height: dimensions.y = main.game_view.size.y / control.scale.y
		if key == "minimap" and main._minimap_shape == "round":
			dimensions = Vector2.ONE * minf(dimensions.x, dimensions.y)
			control.scale = Vector2.ONE * float(config.scale)
		if key in ["resources", "food_meter", "load_meter", "xp_meter"]: dimensions = control.fitted_size(dimensions)
		control.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
		control.size = dimensions
		control.position = _position_for(key, control.size * control.scale)
		if key == "medallion" and config.anchor != "free":
			var visible_rect: Rect2 = parts.medallion.core_rect()
			control.position = _position_for(key, visible_rect.size * control.scale) - visible_rect.position * control.scale
	_avoid_bar_overlaps()
	_apply_docking()
	_fit_rail_statistics()
	_pack_chat()
	_update_chrome()
	main._layout_minimap_cardinals()
	_center_editor()
	_layout_running = false
	if main.inventory_workspace != null: main.inventory_workspace.queue_layout()
	queue_redraw()

func _fit_rail_statistics() -> void:
	var config: Dictionary = model.working.parts.skills
	var stats := _root("skills")
	if not stats.is_visible_in_tree() or config.dock_target != "research" or config.dock_side != "top": return
	if model.working.parts.research.dock_target != "clock": return
	var rect := Rect2(stats.position, stats.size * stats.scale)
	var top := 0.0
	for key: String in ["logo", "spells", "items"]:
		var other := _visual_rect(key)
		if _root(key).is_visible_in_tree() and other.position.x < rect.end.x and other.end.x > rect.position.x:
			top = maxf(top, other.end.y)
	var bottom := rect.end.y
	var available := maxf(32, bottom - top)
	if config.dock_align == "stretch" or stats.size.y * stats.scale.y > available:
		stats.scale.y = available / maxf(1, stats.size.y)
		stats.position.y = bottom - available

func _ensure_chrome(key: String) -> void:
	if _chrome.has(key):
		_chrome[key].show()
		return
	var chrome := PanelChrome.new()
	chrome.name = "_HudChrome"
	_root(key).add_child(chrome)
	# Shared borders live outside the panel, so they must follow its visibility.
	# Rebuild neighbour edges too when a connected panel opens or closes.
	_root(key).visibility_changed.connect(queue_layout)
	_chrome[key] = chrome
	_root(key).queue_redraw()

func _update_chrome() -> void:
	_ensure_chrome("spells")
	frame_overlay.panels.clear()
	var canvas_inverse: Transform2D = main.game_view.get_global_transform().affine_inverse()
	for key: String in _chrome:
		var chrome: PanelChrome = _chrome[key]
		var config: Dictionary = model.working.parts[key]
		chrome.config = config.duplicate(true)
		chrome.neighbours.clear()
		chrome.background_exclusions.clear()
		chrome.show()
		chrome.shape = _frame_shape_for(key)
		chrome.external_border = chrome.shape == "rectangle"
		chrome.circle_inset = minf(_root(key).size.x, _root(key).size.y) * 0.04 if key == "compass" else 1.5
		if key in ["chat", "system_chat"]: chrome.config.show_background = false # Native chat owns its idle fade.
		if key == "rail_panel":
			# The rail fills unoccupied space. Do not double-paint the backgrounds
			# of controls in front of it, especially with translucent HUD colors.
			for other: String in _chrome:
				if other == key or not _root(other).is_visible_in_tree(): continue
				if model.working.parts[other].show_background and _frame_shape_for(other) == "rectangle":
					chrome.background_exclusions.append(_root(other).get_global_rect())
		if config.show_background and config.show_border and chrome.shape == "rectangle":
			for other: String in _chrome:
				if other == key or _frame_group(other) != _frame_group(key) or not _root(other).is_visible_in_tree(): continue
				var adjacent: Dictionary = model.working.parts[other]
				if adjacent.show_background and adjacent.show_border and _frame_shape_for(other) == "rectangle": chrome.neighbours.append(_root(other).get_global_rect())
			for link: Dictionary in _medallion_links():
				var linked: Dictionary = model.working.parts[link.key]
				if _dock_root(link.key) == _dock_root(key) and linked.show_background and linked.show_border:
					chrome.neighbours.append(main.game_view.get_global_transform() * link.rect)
		chrome.queue_redraw()
		if chrome.external_border and config.show_border and _root(key).is_visible_in_tree():
			var adjacent: Array[Rect2] = []
			for rect: Rect2 in chrome.neighbours: adjacent.append(canvas_inverse * rect)
			frame_overlay.panels.append({"rect":canvas_inverse * _root(key).get_global_rect(), "neighbours":adjacent, "config":config.duplicate(true)})
		if key == "compass": _root(key).queue_redraw()
	frame_overlay.queue_redraw()

func _frame_group(key: String) -> String:
	var rail := _root("rail_panel")
	var appearance: Dictionary = model.working.parts.rail_panel
	if rail.is_visible_in_tree() and appearance.show_background and appearance.show_border:
		if rail.get_global_rect().grow(0.5).encloses(_root(key).get_global_rect()): return _dock_root("rail_panel")
	return _dock_root(key)

func _frame_shape_for(key: String) -> String:
	var config: Dictionary = model.working.parts[key]
	if key == "minimap":
		if config.frame_shape == "circle" or config.frame_shape == "match_map" and config.map_shape == "round": return "circle"
	if key == "compass" and config.compass_mode == "round":
		var connected: bool = config.edge_dock != "none" or config.dock_target != "none" and _root(config.dock_target).is_visible_in_tree()
		for other: String in Presets.PARTS:
			if model.working.parts[other].dock_target == key and _root(other).is_visible_in_tree(): connected = true
		if config.compass_corners == "transparent" or config.compass_corners == "fill_when_docked" and not connected: return "circle"
	return "rectangle"

func _pack_chat() -> void:
	# Anchored chat avoids the center dock as its row count/scale changes.
	# A deliberately free-positioned window stays where the player put it.
	var chat: Control = parts.chat
	if model.working.parts.chat.anchor == "bottom_left":
		for key: String in ["spells", "items", "medallion", "food_meter", "load_meter"]:
			if not _root(key).is_visible_in_tree(): continue
			var rect := _visual_rect(key)
			if Rect2(chat.position, chat.size * chat.scale).intersects(rect):
				chat.position.y = maxf(6, rect.position.y - chat.size.y * chat.scale.y - 8)
	var system: Control = parts.system_chat
	if system.is_visible_in_tree() and model.working.parts.system_chat.anchor == "bottom_left" and system.get_global_rect().intersects(chat.get_global_rect()):
		system.position.y = maxf(6, chat.position.y - system.size.y * system.scale.y - 8)


func _apply_docking() -> void:
	var resolved: Dictionary = {}
	for key: String in Presets.PARTS: _dock_part(key, resolved)
	# Clamp connected groups together; never separate a seam at screen edges.
	for key: String in Presets.PARTS:
		if key == "nameplate": continue
		if model.working.parts[key].dock_target != "none": continue
		var group: Array[String] = []
		_gather_docked(key, group)
		var bounds := _visual_rect(key)
		for member: String in group:
			var control := _root(member)
			if control.is_visible_in_tree(): bounds = bounds.merge(_visual_rect(member))
		var delta := Vector2.ZERO
		var viewport_size: Vector2 = main.game_view.size
		var margin := 6.0
		for member: String in group:
			if model.working.parts[member].edge_dock != "none" or model.working.parts[member].extend_to_edge: margin = 0
		var fit := minf(1, minf((viewport_size.x - margin * 2) / maxf(1, bounds.size.x), (viewport_size.y - margin * 2) / maxf(1, bounds.size.y)))
		if bounds.size.x <= viewport_size.x - margin * 2 + 0.5 and bounds.size.y <= viewport_size.y - margin * 2 + 0.5: fit = 1
		if fit < 1:
			for member: String in group:
				var control := _root(member)
				control.position = bounds.position + (control.position - bounds.position) * fit
				control.scale *= fit
			bounds.size *= fit
		if bounds.end.x > viewport_size.x - margin: delta.x = viewport_size.x - margin - bounds.end.x
		if bounds.position.x + delta.x < margin: delta.x = margin - bounds.position.x
		if bounds.end.y > viewport_size.y - margin: delta.y = viewport_size.y - margin - bounds.end.y
		if bounds.position.y + delta.y < margin: delta.y = margin - bounds.position.y
		if delta != Vector2.ZERO:
			for member: String in group: _root(member).position += delta
	main.casting_bar.workspace_layout.position = parts.spells.position
	main.casting_bar.workspace_layout.scale = parts.spells.scale.x
	main.casting_bar.workspace_layout.fit_columns = main.casting_bar._column.columns
	main.casting_bar.workspace_layout.dimensions = parts.spells.size
	var connections: Array = []
	var orb: Control = parts.medallion
	orb.connection_panels.clear()
	orb.dock_clearance = {"left":0.0, "right":0.0, "top":0.0, "bottom":0.0}
	for link: Dictionary in _medallion_links():
		var config: Dictionary = model.working.parts[link.key]
		var rect: Rect2 = link.rect
		var neck: Rect2 = link.neck
		if link.horizontal:
			orb.dock_clearance[link.side] = maxf(float(orb.dock_clearance[link.side]), neck.size.y / (2 * orb.scale.y))
		else:
			orb.dock_clearance[link.side] = maxf(float(orb.dock_clearance[link.side]), neck.size.x / (2 * orb.scale.x))
		rect.position = (rect.position - orb.position) / orb.scale
		rect.size /= orb.scale
		var panel_rect: Rect2 = link.panel_rect
		panel_rect.position = (panel_rect.position - orb.position) / orb.scale
		panel_rect.size /= orb.scale
		var background: Color = config.background_color
		var border: Color = config.border_color
		if not config.show_background: background.a = 0
		if not config.show_border: border.a = 0
		if background.a > 0 and border.a > 0: orb.connection_panels.append(panel_rect)
		connections.append({"rect":rect, "background":background, "border":border, "horizontal":link.horizontal})
	orb.connections = connections
	orb.queue_redraw()

func _medallion_links() -> Array[Dictionary]:
	var links: Array[Dictionary] = []
	var orb := _root("medallion")
	if not orb.is_visible_in_tree(): return links
	var socket: Rect2 = parts.medallion.dock_rect()
	var core := Rect2(orb.position + socket.position * orb.scale, socket.size * orb.scale)
	var orb_config: Dictionary = model.working.parts.medallion
	var opposite := {"left":"right", "right":"left", "top":"bottom", "bottom":"top"}
	for key: String in Presets.PARTS:
		if key in ["medallion", "nameplate"] or not _root(key).is_visible_in_tree(): continue
		var config: Dictionary = model.working.parts[key]
		var side := ""
		if config.dock_target == "medallion" and config.dock_gap <= 0: side = config.dock_side
		elif orb_config.dock_target == key and orb_config.dock_gap <= 0: side = opposite[orb_config.dock_side]
		if side.is_empty() or _frame_shape_for(key) != "rectangle": continue
		var control := _root(key)
		var panel_rect := Rect2(control.position, control.size * control.scale)
		var horizontal := side in ["left", "right"]
		var rect: Rect2
		# A wide meter connects through a neck the width of the circle, leaving
		# the rest of the meter's border intact. Both docking directions agree.
		if horizontal:
			var low := maxf(panel_rect.position.y, core.position.y + core.size.y * 0.15)
			var high := minf(panel_rect.end.y, core.end.y - core.size.y * 0.15)
			var edge := panel_rect.end.x if side == "left" else panel_rect.position.x
			rect = Rect2(Vector2(minf(edge, core.get_center().x), low), Vector2(absf(edge - core.get_center().x), high - low))
		else:
			var low := maxf(panel_rect.position.x, core.position.x + core.size.x * 0.15)
			var high := minf(panel_rect.end.x, core.end.x - core.size.x * 0.15)
			var edge := panel_rect.end.y if side == "top" else panel_rect.position.y
			rect = Rect2(Vector2(low, minf(edge, core.get_center().y)), Vector2(high - low, absf(edge - core.get_center().y)))
		if rect.size.x > 0 and rect.size.y > 0:
			links.append({"key":key, "side":side, "rect":rect, "neck":rect, "panel_rect":panel_rect, "horizontal":horizontal})
	# When perpendicular panels meet, back their shared corner all the way to
	# that meeting edge. A lone bar retains its narrow neck and round shoulder.
	for link: Dictionary in links:
		var config: Dictionary = model.working.parts[link.key]
		if not config.show_background or config.background_color.a <= 0: continue
		var rect: Rect2 = link.rect
		var panel: Rect2 = link.panel_rect
		for other: Dictionary in links:
			if link.horizontal == other.horizontal: continue
			var adjacent: Dictionary = model.working.parts[other.key]
			if not adjacent.show_background or adjacent.background_color.a <= 0: continue
			var support: Rect2 = other.panel_rect
			if link.horizontal and support.position.x <= rect.position.x + 1.1 and support.end.x >= rect.end.x - 1.1:
				if other.side == "bottom" and absf(panel.end.y - support.position.y) < 1.1: rect.end.y = panel.end.y
				elif other.side == "top" and absf(panel.position.y - support.end.y) < 1.1:
					var end := rect.end
					rect.position.y = panel.position.y
					rect.end = end
			elif not link.horizontal and support.position.y <= rect.position.y + 1.1 and support.end.y >= rect.end.y - 1.1:
				if other.side == "right" and absf(panel.end.x - support.position.x) < 1.1: rect.end.x = panel.end.x
				elif other.side == "left" and absf(panel.position.x - support.end.x) < 1.1:
					var end := rect.end
					rect.position.x = panel.position.x
					rect.end = end
		link.rect = rect
	return links

func _gather_docked(key: String, members: Array[String]) -> void:
	if key in members: return
	members.append(key)
	for other: String in Presets.PARTS:
		if model.working.parts[other].dock_target == key: _gather_docked(other, members)

func _dock_part(key: String, resolved: Dictionary) -> void:
	if resolved.has(key): return
	resolved[key] = true
	var config: Dictionary = model.working.parts[key]
	var target: String = config.dock_target
	if target == "none" or not _root(target).is_visible_in_tree() and not (target == "rail_panel" and model.working.parts.rail_panel.enabled):
		_apply_screen_dock(key)
		return
	_dock_part(target, resolved)
	var control := _root(key)
	var parent := _root(target)
	var rect := Rect2(parent.position, parent.size * parent.scale)
	if target == "medallion":
		var socket: Rect2 = parts.medallion.dock_rect()
		rect = Rect2(parent.position + socket.position * parent.scale, socket.size * parent.scale)
	var source_socket := Rect2(Vector2.ZERO, control.size)
	if key == "medallion": source_socket = parts.medallion.dock_rect()
	var source_offset := source_socket.position * control.scale
	var dimensions := source_socket.size * control.scale
	var gap := float(config.dock_gap)
	var vertical: bool = config.dock_side in ["left", "right"]
	if config.dock_align == "stretch" and key != "medallion":
		if vertical: dimensions.y = rect.size.y
		else: dimensions.x = rect.size.x
	if config.extend_to_edge and key != "medallion":
		match config.dock_side:
			"left": dimensions.x = maxf(32, rect.position.x - gap)
			"right": dimensions.x = maxf(32, main.game_view.size.x - rect.end.x - gap)
			"top": dimensions.y = maxf(32, rect.position.y - gap)
			"bottom": dimensions.y = maxf(32, main.game_view.size.y - rect.end.y - gap)
	if key != "medallion" and dimensions.distance_to(control.size * control.scale) > 0.5:
		_resize_layout_part(key, dimensions)
		dimensions = control.size * control.scale
	var alignment: float = {"start":0.0, "center":0.5, "end":1.0, "stretch":0.0}[config.dock_align]
	if key == "medallion" and config.dock_align == "stretch": alignment = 0.5
	var cross := rect.position.y + (rect.size.y - dimensions.y) * alignment if vertical else rect.position.x + (rect.size.x - dimensions.x) * alignment
	match config.dock_side:
		"left": control.position = Vector2(rect.position.x - dimensions.x - gap, cross)
		"right": control.position = Vector2(rect.end.x + gap, cross)
		"top": control.position = Vector2(cross, rect.position.y - dimensions.y - gap)
		"bottom": control.position = Vector2(cross, rect.end.y + gap)
	control.position += config.dock_offset - source_offset

func _resize_layout_part(key: String, screen_size: Vector2) -> void:
	match key:
		"resources", "food_meter", "load_meter", "xp_meter": _root(key).size = _root(key).fitted_size(screen_size / _root(key).scale)
		"utilities": _layout_menu_icons(screen_size)
		"items": _layout_items(screen_size)
		"spells":
			main.casting_bar.workspace_layout = model.working.parts.spells.duplicate(true)
			main.casting_bar.workspace_layout.dimensions = screen_size / float(model.working.parts.spells.scale)
			main.casting_bar.workspace_layout.position = parts.spells.position
			main.casting_bar._layout()
		_:
			if key == "minimap" and main._minimap_shape == "round":
				var vertical: bool = model.working.parts[key].dock_side in ["left", "right"]
				var diameter := screen_size.y if vertical else screen_size.x
				_root(key).size = Vector2.ONE * diameter / _root(key).scale
			else:
				var control := _root(key)
				control.size = screen_size / control.scale
				# Native panels can impose a minimum size. Fit their rendered extent
				# as well, so a narrow dock never pushes the entire group sideways.
				control.scale = screen_size / control.size.max(Vector2.ONE)

func _apply_screen_dock(key: String) -> void:
	var edge: String = model.working.parts[key].edge_dock
	if edge == "none" or key == "nameplate": return
	var rect := _visual_rect(key)
	var delta := Vector2.ZERO
	if "left" in edge: delta.x = -rect.position.x
	elif "right" in edge: delta.x = main.game_view.size.x - rect.end.x
	if "top" in edge: delta.y = -rect.position.y
	elif "bottom" in edge: delta.y = main.game_view.size.y - rect.end.y
	_root(key).position += delta

func _avoid_bar_overlaps() -> void:
	var spells: Control = parts.spells
	var items: Control = parts.items
	var spell_config: Dictionary = model.working.parts.spells
	var item_config: Dictionary = model.working.parts.items
	if spell_config.anchor == item_config.anchor and spell_config.anchor in ["right", "bottom_right"] \
			and spells.visible and items.visible and spells.get_global_rect().intersects(items.get_global_rect()):
		if spell_config.orientation == "vertical" and item_config.orientation == "vertical":
			spells.position.x = maxf(6, items.position.x - spells.size.x * spells.scale.x - 10)
		else:
			items.position.y = minf(main.game_view.size.y - items.size.y * items.scale.y - 6, spells.position.y + spells.size.y * spells.scale.y + 10)
	var resources := _root("resources")
	if model.working.parts.resources.anchor == "bottom_center":
		for key: String in ["spells", "items", "medallion"]:
			var rect := _visual_rect(key)
			if _root(key).visible and _visual_rect("resources").intersects(rect):
				resources.position.y = maxf(6, rect.position.y - resources.size.y * resources.scale.y - 10)

func _position_for(key: String, dimensions: Vector2) -> Vector2:
	var config: Dictionary = model.working.parts[key]
	var bounds: Vector2 = main.game_view.size
	var where := Vector2.ZERO
	match str(config.anchor):
		"top_left": where = Vector2(8, 8)
		"top_center": where = Vector2((bounds.x - dimensions.x) / 2, 8)
		"top_right": where = Vector2(bounds.x - dimensions.x - 8, 8)
		"left": where = Vector2(8, (bounds.y - dimensions.y) / 2)
		"right": where = Vector2(bounds.x - dimensions.x - 8, (bounds.y - dimensions.y) / 2)
		"bottom_left": where = Vector2(8, bounds.y - dimensions.y - 8)
		"bottom_center": where = Vector2((bounds.x - dimensions.x) / 2, bounds.y - dimensions.y - 8)
		"bottom_right": where = bounds - dimensions - Vector2(8, 8)
		"free": where = config.position * bounds
		_:
			if key in ["gauntlet_loot", "rare_drops"]:
				where = main.extension_windows.gauntlet_loot_window.default_hud_rect(key, bounds).position
			elif original.has(key): where = original[key].rect.position / _initial_size * bounds
	where += config.offset
	return where.clamp(Vector2(6, 6), (bounds - dimensions - Vector2(6, 6)).max(Vector2(6, 6)))

func _visual_rect(key: String) -> Rect2:
	var control := _root(key)
	var local: Rect2 = parts.medallion.visual_rect() if key == "medallion" else _content_rect(key)
	return Rect2(control.position + local.position * control.scale, local.size * control.scale)

func _content_rect(key: String) -> Rect2:
	var control := _root(key)
	if key == "medallion": return parts.medallion.core_rect()
	if key == "party" and not model.working.legacy and model.working.parts.party.frame_style == "floating" and not parts.party.get_node("Body/Header").visible:
		var rows: Control = main.extension_windows.party_rows
		var origin := control.get_global_transform().affine_inverse() * rows.global_position
		var rect := Rect2(origin, Vector2(rows.size.x, minf(rows.get_combined_minimum_size().y, main.extension_windows.party_scroll.size.y)))
		if party_summary.visible:
			var summary_origin := control.get_global_transform().affine_inverse() * party_summary.global_position
			rect = rect.merge(Rect2(summary_origin, party_summary.size))
		return rect
	return Rect2(Vector2.ZERO, control.size)

func _selection_rect(key: String) -> Rect2:
	var control := _root(key)
	var local := _content_rect(key)
	return Rect2(control.get_global_transform() * local.position, local.size * control.get_global_transform().get_scale())

func _pick(point: Vector2) -> Dictionary:
	var orb: Control = parts.medallion
	if orb.is_visible_in_tree():
		var local := orb.get_global_transform().affine_inverse() * point
		var arc: int = orb.arc_at(local, 4 / maxf(0.1, orb.scale.x))
		if arc >= 0: return {"key":"medallion", "arc":arc}
		if local.distance_to(orb.center_point()) <= orb.frame_radius(): return {"key":"medallion", "arc":-1}
	var picked := ""
	var area := INF
	for key: String in Presets.PARTS:
		if key == "medallion": continue
		var control := _root(key)
		if not control.is_visible_in_tree(): continue
		var rect := _selection_rect(key)
		if _frame_shape_for(key) == "circle":
			var radius := minf(rect.size.x, rect.size.y) * (0.46 if key == "compass" else 0.5)
			if point.distance_to(rect.get_center()) > radius + 3: continue
		if rect.has_point(point) and rect.get_area() < area:
			picked = key
			area = rect.get_area()
	return {} if picked.is_empty() else {"key":picked, "arc":-1}

func _resize_handle(key: String) -> Rect2:
	if key == "medallion" and _selected_arc >= 0:
		var points: PackedVector2Array = parts.medallion.arc_points(_selected_arc)
		var where: Vector2 = parts.medallion.get_global_transform() * points[-1]
		return Rect2(where - Vector2(6, 6), Vector2(12, 12))
	return Rect2(_selection_rect(key).end - Vector2(6, 6), Vector2(12, 12))

func _resize_handles(key: String) -> Dictionary:
	var handles := {"corner":_resize_handle(key)}
	if key in ["medallion", "nameplate"]: return handles
	var rect := _selection_rect(key)
	for side: String in ["left", "right", "top", "bottom"]:
		var point := rect.get_center()
		match side:
			"left": point.x = rect.position.x
			"right": point.x = rect.end.x
			"top": point.y = rect.position.y
			"bottom": point.y = rect.end.y
		handles[side] = Rect2(point - Vector2(5, 5), Vector2(10, 10))
	return handles

func _snap_for(key: String) -> Dictionary:
	var descendants: Array[String] = []
	_gather_docked(key, descendants)
	var source := _visual_rect(key)
	var best: Dictionary = {}
	var distance := 18.0
	for target: String in Presets.PARTS:
		if target in descendants or target == "nameplate" or not _root(target).is_visible_in_tree(): continue
		var parent := _visual_rect(target)
		if target == "medallion":
			var socket: Rect2 = parts.medallion.dock_rect()
			parent = Rect2(parts.medallion.position + socket.position * parts.medallion.scale, socket.size * parts.medallion.scale)
		for side: String in ["left", "right", "top", "bottom"]:
			var where := Vector2.ZERO
			match side:
				"left": where = Vector2(parent.position.x - source.size.x, parent.get_center().y - source.size.y / 2)
				"right": where = Vector2(parent.end.x, parent.get_center().y - source.size.y / 2)
				"top": where = Vector2(parent.get_center().x - source.size.x / 2, parent.position.y - source.size.y)
				"bottom": where = Vector2(parent.get_center().x - source.size.x / 2, parent.end.y)
			var delta := source.position.distance_to(where)
			if delta < distance:
				distance = delta
				best = {"target":target, "side":side, "rect":Rect2(where, source.size)}
	var edges: Array[String] = []
	var snapped := source
	var edge_distance := 0.0
	var viewport_size: Vector2 = main.game_view.size
	if absf(source.position.y) < 18:
		edges.append("top")
		snapped.position.y = 0
		edge_distance = maxf(edge_distance, absf(source.position.y))
	elif absf(viewport_size.y - source.end.y) < 18:
		edges.append("bottom")
		snapped.position.y = viewport_size.y - source.size.y
		edge_distance = maxf(edge_distance, absf(viewport_size.y - source.end.y))
	if absf(source.position.x) < 18:
		edges.append("left")
		snapped.position.x = 0
		edge_distance = maxf(edge_distance, absf(source.position.x))
	elif absf(viewport_size.x - source.end.x) < 18:
		edges.append("right")
		snapped.position.x = viewport_size.x - source.size.x
		edge_distance = maxf(edge_distance, absf(viewport_size.x - source.end.x))
	if not edges.is_empty() and edge_distance < distance:
		best = {"target":"screen", "side":"_".join(edges), "rect":snapped}
	return best

func _nudge(event: InputEventKey) -> void:
	_checkpoint("nudge:" + selected)
	var step := 10.0 if event.shift_pressed else 1.0
	var delta := Vector2.ZERO
	match event.keycode:
		KEY_LEFT: delta.x = -step
		KEY_RIGHT: delta.x = step
		KEY_UP: delta.y = -step
		KEY_DOWN: delta.y = step
	if selected == "medallion" and _selected_arc >= 0:
		var arc: Dictionary = model.working.parts.medallion.arcs[_selected_arc]
		arc.radius_offset = clampf(arc.radius_offset - delta.y, -30, 96)
		arc.start_angle = clampf(arc.start_angle + delta.x, -360, 360)
	elif selected != "nameplate":
		var key := _dock_root(selected)
		model.working.parts[key].anchor = "free"
		model.working.parts[key].edge_dock = "none"
		model.working.parts[key].offset = Vector2.ZERO
		model.working.parts[key].position = (_root(key).position + delta) / main.game_view.size
		model.working.legacy = false
	apply_layout()
	_refresh_selection()

func _resize_window(key: String, delta: Vector2, bypass_snap: bool) -> void:
	var config: Dictionary = model.working.parts[key]
	var rect := _resize_rect
	for axis: int in 2:
		if _resize_axis[axis] == 0: continue
		if _resize_axis[axis] < 0:
			rect.position[axis] += delta[axis]
			rect.size[axis] -= delta[axis]
		else: rect.size[axis] += delta[axis]
		if rect.size[axis] < 32:
			if _resize_axis[axis] < 0: rect.position[axis] = _resize_rect.end[axis] - 32
			rect.size[axis] = 32
	_resize_guides.clear()
	if _resize_snap_enabled and not bypass_snap:
		var scale: Vector2 = main.game_view.get_global_transform().get_scale().abs().max(Vector2.ONE * 0.01)
		var snapped := ResizeSnap.snap(rect, _resize_axis, _resize_targets, Rect2(Vector2.ZERO, main.game_view.size), Vector2.ONE * 10 / scale)
		rect = snapped.rect
		_resize_guides.assign(snapped.guides)
	if key == "minimap" and main._minimap_shape == "round":
		var diameter := rect.size.x if _resize_axis.x != 0 else rect.size.y
		rect.size = Vector2.ONE * diameter
		if _resize_axis.x < 0: rect.position.x = _resize_rect.end.x - diameter
		if _resize_axis.y < 0: rect.position.y = _resize_rect.end.y - diameter
	var dimensions := rect.size / _resize_runtime_scale.max(Vector2.ONE * 0.01)
	var direct := key in ["rail_panel", "utilities", "spells", "items", "chat", "system_chat", "party", "minimap", "compass", "clock", "resources", "food_meter", "load_meter", "xp_meter", "player_card", "target", "gauntlet_loot", "rare_drops"]
	if direct:
		if key == "rail_panel" and _resize_axis.y != 0: config.full_height = false
		if config.extend_to_edge and (config.dock_side in ["left", "right"] and _resize_axis.x != 0 or config.dock_side in ["top", "bottom"] and _resize_axis.y != 0): config.extend_to_edge = false
		if config.dock_align == "stretch" and (config.dock_side in ["left", "right"] and _resize_axis.y != 0 or config.dock_side in ["top", "bottom"] and _resize_axis.x != 0): config.dock_align = "start"
		config.dimensions = dimensions.clamp(Vector2(32, 16), Vector2(4096, 2048))
		if key in ["utilities", "spells", "items"]: config.grid_mode = "aspect"
		if key in ["chat", "system_chat"]: model.working.chat_windows.erase(key)
	else:
		config.axis_scale = (_resize_axis_scale * rect.size / _resize_rect.size.max(Vector2.ONE)).clamp(Vector2.ONE * 0.25, Vector2.ONE * 4)
	if config.dock_target == "none":
		# Release only the screen edge actually being pulled away from its pin.
		var pins: Array[String] = []
		if config.edge_dock != "none": pins.assign(str(config.edge_dock).split("_"))
		for edge: String in ["left", "right", "top", "bottom"]:
			if edge == "left" and _resize_axis.x < 0 or edge == "right" and _resize_axis.x > 0 or edge == "top" and _resize_axis.y < 0 or edge == "bottom" and _resize_axis.y > 0: pins.erase(edge)
		config.edge_dock = "_".join(pins) if not pins.is_empty() else "none"
		config.anchor = "free"
		config.offset = Vector2.ZERO
		config.position = rect.position / main.game_view.size
	model.working.legacy = false
	apply_layout()
	if config.dock_target != "none":
		var correction := rect.position - _root(key).position
		for axis: int in 2:
			if _resize_axis[axis] != 0: config.dock_offset[axis] += correction[axis]
		if correction.length() > 0.1: apply_layout()
	# A control's content minimum can prevent a proposed alignment. Never show
	# a guide that the actual rendered edge did not reach.
	var actual := Rect2(_root(key).position, _root(key).size * _root(key).scale)
	var confirmed: Array[Dictionary] = []
	for guide: Dictionary in _resize_guides:
		var edge: float = actual.position[guide.axis] if _resize_axis[guide.axis] < 0 else actual.end[guide.axis]
		if absf(edge - guide.value) <= 1: confirmed.append(guide)
	_resize_guides = confirmed

func handle_input(event: InputEvent) -> bool:
	if not is_open(): return false
	if event is InputEventMouse:
		for control: Control in input_exclusions:
			if is_instance_valid(control) and control.is_visible_in_tree() and control.get_global_rect().has_point(event.position): return false
	if event is InputEventKey and event.pressed:
		var focus := get_viewport().gui_get_focus_owner()
		if event.ctrl_pressed and event.keycode in [KEY_Z, KEY_Y] and not focus is LineEdit:
			if event.keycode == KEY_Y or event.shift_pressed: redo_edit()
			else: undo_edit()
			get_viewport().set_input_as_handled()
			return true
		if event.keycode in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN] and focus == null:
			_nudge(event)
			get_viewport().set_input_as_handled()
			return true
	if event.is_action_pressed("cancel"):
		cancel_edit()
		get_viewport().set_input_as_handled()
		return true
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE] and not panel.get_global_rect().has_point(event.position):
		get_viewport().set_input_as_handled()
		return true
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if not event.pressed:
			var handled := not _drag_part.is_empty()
			if _drag_started and not _resizing and not _snap_candidate.is_empty():
				dock_component(_drag_root, _snap_candidate.target, _snap_candidate.side)
			_drag_part = ""
			_drag_root = ""
			_drag_started = false
			_snap_candidate = {}
			_resize_guides.clear()
			if _resizing: select_component(selected, _selected_arc)
			_resizing = false
			_last_edit_tag = ""
			_refresh_selection()
			if handled: get_viewport().set_input_as_handled()
			queue_redraw()
			return handled
		if panel.get_global_rect().has_point(event.position): return false
		var focus := get_viewport().gui_get_focus_owner()
		if focus != null: focus.release_focus()
		_resizing = false
		_resize_axis = Vector2.ONE
		if _root(selected).is_visible_in_tree():
			var handles := _resize_handles(selected)
			for handle: String in handles:
				if handles[handle].grow(3).has_point(event.position):
					_resizing = true
					_resize_axis = {"corner":Vector2.ONE, "left":Vector2.LEFT, "right":Vector2.RIGHT, "top":Vector2.UP, "bottom":Vector2.DOWN}[handle]
					break
		var picked := {"key":selected, "arc":_selected_arc} if _resizing else _pick(event.position)
		if not picked.is_empty():
			select_component(picked.key, picked.arc)
			_drag_part = selected if selected != "nameplate" else ""
			_drag_root = selected if event.alt_pressed or _resizing else _dock_root(selected)
			_drag_mouse = event.position
			_drag_position = _root(_drag_root).position
			_drag_started = false
			_resize_size = _root(selected).size
			_resize_scale = float(model.working.parts[selected].scale)
			_resize_axis_scale = model.working.parts[selected].axis_scale
			_resize_runtime_scale = _root(selected).scale
			_resize_rect = Rect2(_root(selected).position, _root(selected).size * _resize_runtime_scale)
			_resize_targets.clear()
			for other: String in Presets.PARTS:
				if other != selected and other != "nameplate" and _root(other).is_visible_in_tree(): _resize_targets.append({"key":other, "rect":_visual_rect(other)})
			_drag_center = parts.medallion.get_global_transform() * parts.medallion.center_point()
			if selected == "medallion" and _selected_arc >= 0:
				_drag_arc_offset = model.working.parts.medallion.arcs[_selected_arc].thickness if _resizing else model.working.parts.medallion.arcs[_selected_arc].radius_offset
		get_viewport().set_input_as_handled()
		return true
	if event is InputEventMouseMotion and not _drag_part.is_empty():
		if not event.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_drag_part = ""
			return false
		if event.position.distance_to(_drag_mouse) > 3:
			if not _drag_started:
				_checkpoint("gesture:" + _drag_part)
				_drag_started = true
			var config: Dictionary = model.working.parts[_drag_part]
			var did_layout := false
			var inverse: Transform2D = main.game_view.get_global_transform().affine_inverse()
			var delta: Vector2 = inverse * event.position - inverse * _drag_mouse
			if _drag_part == "medallion" and _selected_arc >= 0:
				var arc: Dictionary = config.arcs[_selected_arc]
				var factor: float = parts.medallion.unit_scale() * parts.medallion.scale.x
				if _resizing: arc.thickness = clampf(_drag_arc_offset + delta.y / factor, 2, 16)
				else: arc.radius_offset = clampf(_drag_arc_offset + (event.position.distance_to(_drag_center) - _drag_mouse.distance_to(_drag_center)) / factor, -30, 96)
			elif _resizing:
				if _drag_part == "medallion":
					var factor: float = event.position.distance_to(_drag_center) / maxf(1, _drag_mouse.distance_to(_drag_center))
					config.scale = clampf(_resize_scale * factor, 0.5, 2)
					config.anchor = "free"
					config.offset = Vector2.ZERO
					config.position = (_drag_center - parts.medallion.center_point() * float(config.scale)) / main.game_view.size
				else:
					_resize_window(_drag_part, delta, event.shift_pressed)
					did_layout = true
			else:
				var root_config: Dictionary = model.working.parts[_drag_root]
				root_config.dock_target = "none"
				root_config.edge_dock = "none"
				root_config.extend_to_edge = false
				root_config.anchor = "free"
				root_config.offset = Vector2.ZERO
				root_config.position = (_drag_position + delta) / main.game_view.size
			model.working.legacy = false
			if not did_layout: apply_layout()
			_snap_candidate = _snap_for(_drag_root) if _snap_enabled and not _resizing and not event.alt_pressed and not event.shift_pressed and not (_drag_part == "medallion" and _selected_arc >= 0) else {}
		get_viewport().set_input_as_handled()
		return true
	if event is InputEventMouseMotion:
		var hover := {} if panel.get_global_rect().has_point(event.position) else _pick(event.position)
		if hover != _hover:
			_hover = hover
			queue_redraw()
	return false

func _draw() -> void:
	if not is_open(): return
	var transform := get_global_transform().affine_inverse()
	var gold := Color("e6bf73")
	if _show_grid:
		for x: int in range(0, ceili(size.x), 20): draw_line(Vector2(x, 0), Vector2(x, size.y), Color(0.75, 0.83, 0.88, 0.12))
		for y: int in range(0, ceili(size.y), 20): draw_line(Vector2(0, y), Vector2(size.x, y), Color(0.75, 0.83, 0.88, 0.12))
		draw_line(Vector2(size.x / 2, 0), Vector2(size.x / 2, size.y), Color(0.9, 0.75, 0.4, 0.5))
		draw_line(Vector2(0, size.y / 2), Vector2(size.x, size.y / 2), Color(0.9, 0.75, 0.4, 0.5))
	for key: String in Presets.PARTS:
		var control := _root(key)
		if control == null or not control.is_visible_in_tree(): continue
		var hovered: bool = _hover.get("key") == key
		var active := key == selected
		if key == "medallion":
			var center: Vector2 = transform * (control.get_global_transform() * control.center_point())
			var radius: float = control.frame_radius() * control.scale.x
			if active and _selected_arc < 0 or hovered and int(_hover.get("arc", -1)) < 0:
				draw_arc(center, radius + 3, 0, TAU, 96, gold if active else Color(0.7, 0.8, 0.8, 0.6), 2, true)
			for index: int in 8:
				if not model.working.parts.medallion.arcs[index].enabled and not (active and _selected_arc == index): continue
				var points: PackedVector2Array = control.arc_points(index)
				for point: int in points.size(): points[point] = transform * (control.get_global_transform() * points[point])
				var highlighted: bool = active and _selected_arc == index or hovered and int(_hover.get("arc", -1)) == index
				if highlighted: draw_polyline(points, gold, 2, true)
		elif active or hovered:
			var rect := _selection_rect(key)
			rect.position = transform * rect.position
			var highlight := gold if active else Color(0.7, 0.8, 0.8, 0.6)
			if _frame_shape_for(key) == "circle":
				var radius := minf(rect.size.x, rect.size.y) * (0.46 if key == "compass" else 0.5)
				draw_arc(rect.get_center(), radius + 2, 0, TAU, 128, highlight, 2, true)
			else: draw_rect(rect.grow(2), highlight, false, 2)
		if active:
			for handle: Rect2 in _resize_handles(key).values():
				handle.position = transform * handle.position
				draw_rect(handle, gold)
	if not _snap_candidate.is_empty():
		var rect: Rect2 = _snap_candidate.rect
		draw_rect(rect, Color(0.9, 0.75, 0.4, 0.15))
		draw_rect(rect, gold, false, 2)
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(0, -8), "Dock to " + str(Presets.PARTS.get(_snap_candidate.target, "screen")) + " · " + str(_snap_candidate.side), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, gold)
	var to_editor: Transform2D = transform * main.game_view.get_global_transform()
	for guide: Dictionary in _resize_guides:
		var rect := _visual_rect(selected).merge(guide.target_rect)
		var a := Vector2(guide.value, rect.position.y - 8) if guide.axis == 0 else Vector2(rect.position.x - 8, guide.value)
		var b := Vector2(guide.value, rect.end.y + 8) if guide.axis == 0 else Vector2(rect.end.x + 8, guide.value)
		draw_line(to_editor * a, to_editor * b, Color("73ded3"), 1.5, true)
		var label := to_editor * a + Vector2(4, -6)
		label = label.max(Vector2(8, 16))
		draw_string(ThemeDB.fallback_font, label, "Align with " + str(Presets.PARTS.get(guide.target, "screen")) + " · Shift to bypass", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("73ded3"))
	if not _hover.is_empty():
		var caption: String = _arc_name(_hover.arc) if int(_hover.arc) >= 0 else Presets.PARTS[_hover.key]
		var point := get_local_mouse_position() + Vector2(12, -12)
		draw_string(ThemeDB.fallback_font, point, caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, gold)
