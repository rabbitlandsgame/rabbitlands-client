extends SceneTree
## Live-control integration: presets must retain chat and quick-slot identity,
## round-trip custom layouts and restore a canceled editing transaction.
const Presets := preload("res://src/ui/hud_presets.gd")
const PATH := "res://test-artifacts/hud-presets/presets.cfg"
var failures := 0
var main: Control

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)
	else: print("PASS: ", label)

func _frames(count := 4) -> void:
	for index: int in count: await process_frame

func _create() -> void:
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = PATH
	root.add_child(main)
	await _frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	await _frames()

func _gesture(workspace: Control, origin: Vector2, destination: Vector2, detach := false) -> void:
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.alt_pressed = detach
	click.position = origin
	workspace.handle_input(click)
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.alt_pressed = detach
	motion.position = destination
	workspace.handle_input(motion)
	click.pressed = false
	click.position = destination
	workspace.handle_input(click)
	await _frames()

func _editor_usability(workspace: Control, chat: PanelContainer, system: PanelContainer) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("adventure", true)
	workspace.panel.position = Vector2(24, 24)
	await _frames()
	var orb: Control = workspace.parts.medallion
	var selection: Rect2 = workspace._selection_rect("medallion")
	_expect(selection.size.x < orb.size.x * orb.scale.x * 0.65,
		"circle selection fits its visible ornament instead of transparent canvas")
	var empty_corner: Vector2 = orb.global_position + Vector2(2, 2)
	_expect(not orb._has_point(Vector2(2, 2)) and workspace._pick(empty_corner).get("key") != "medallion",
		"transparent circle corners do not intercept nearby windows")
	for index: int in 8: workspace.change_arc(index, "enabled", true)
	await _frames()
	for index: int in 8:
		var points: PackedVector2Array = orb.arc_points(index)
		var point: Vector2 = orb.get_global_transform() * points[points.size() / 2]
		var picked: Dictionary = workspace._pick(point)
		_expect(picked.get("key") == "medallion" and picked.get("arc") == index,
			"direct picking distinguishes curve %d from circle and docked buttons" % (index + 1))
	workspace.select_component("medallion", 0)
	var points: PackedVector2Array = orb.arc_points(0)
	var point: Vector2 = orb.get_global_transform() * points[points.size() / 2]
	var center: Vector2 = orb.get_global_transform() * orb.center_point()
	var old_position: Vector2 = orb.position
	var old_offset: float = workspace.model.working.parts.medallion.arcs[0].radius_offset
	await _gesture(workspace, point, point + (point - center).normalized() * 16)
	_expect(workspace._selected_arc == 0 and workspace._detail_tabs.current_tab == 2,
		"clicking a curve opens its individual options")
	_expect(workspace.model.working.parts.medallion.arcs[0].radius_offset > old_offset + 10 and orb.position.distance_to(old_position) < 1,
		"dragging a curve adjusts its radius without moving the circle")
	workspace.undo_edit()
	_expect(workspace.model.working.parts.medallion.arcs[0].radius_offset == old_offset,
		"Undo reverses an entire curve drag in one step")
	workspace.redo_edit()
	_expect(workspace.model.working.parts.medallion.arcs[0].radius_offset > old_offset,
		"Redo restores the curve drag")
	workspace.choose_preset("adventure", true)
	await _frames()
	var items: Control = workspace._root("items")
	var origin: Vector2 = items.get_global_rect().get_center()
	old_position = orb.position
	await _gesture(workspace, origin, origin + Vector2(-30, -30))
	_expect(workspace.model.working.parts.items.dock_target == "medallion" and orb.position.distance_to(old_position) > 25,
		"dragging a docked bar moves its connected group and keeps the join")
	origin = items.get_global_rect().get_center()
	old_position = orb.position
	await _gesture(workspace, origin, origin + Vector2(10, -85), true)
	_expect(workspace.model.working.parts.items.dock_target == "none" and orb.position.distance_to(old_position) < 1,
		"Alt-drag detaches only the selected bar")
	workspace.undo_edit()
	_expect(workspace.model.working.parts.items.dock_target == "medallion", "Undo reconnects a detached bar")
	workspace.dock_component("items", "none", "right")
	await _frames()
	var socket: Rect2 = orb.core_rect()
	var desired := Vector2(orb.position.x + socket.end.x * orb.scale.x, orb.position.y + socket.get_center().y * orb.scale.y - items.size.y * items.scale.y / 2)
	workspace.change_part("items", "position", (desired + Vector2(7, 3)) / main.game_view.size)
	await _frames()
	var candidate: Dictionary = workspace._snap_for("items")
	_expect(candidate.get("target") == "medallion" and candidate.get("side") == "right",
		"dock preview finds the visible circle edge")
	origin = items.get_global_rect().get_center()
	await _gesture(workspace, origin, origin + Vector2(-4, 0))
	_expect(workspace.model.working.parts.items.dock_target == "medallion",
		"dropping near the circle docks the actual bar")
	for design: String in ["plain", "laurel", "runic", "crystal"]:
		workspace.change_part("medallion", "border_design", design)
		await _frames()
		socket = orb.core_rect()
		_expect(absf(items.position.x - (orb.position.x + socket.end.x * orb.scale.x)) < 1,
			"docking follows the visible %s border" % design)
	workspace.dock_component("medallion", "none", "right")
	workspace.change_part("medallion", "position", Vector2(0.4, 0.45))
	workspace.change_part("medallion", "offset", Vector2.ZERO)
	await _frames()
	workspace.select_component("medallion")
	center = orb.get_global_transform() * orb.center_point()
	var old_scale: float = workspace.model.working.parts.medallion.scale
	origin = workspace._resize_handle("medallion").get_center()
	await _gesture(workspace, origin, center + (origin - center) * 1.12)
	_expect(workspace.model.working.parts.medallion.scale > old_scale and (orb.get_global_transform() * orb.center_point()).distance_to(center) < 2,
		"circle resizing preserves its visual center and connected bars")
	workspace.preset_name.text = "Keep this custom HUD"
	workspace.save_custom(false)
	var custom_id: String = workspace.model.active
	var custom_snapshot: Dictionary = workspace.model.working.duplicate(true)
	workspace.reset_builtin()
	_expect(workspace.reset_button.disabled and workspace.settings_reset.disabled and workspace.model.working == custom_snapshot,
		"custom presets cannot be overwritten by Restore default")
	var custom_count: int = workspace.model.custom.size()
	for id: String in ["heritage", "classic", "modular", "adventure", "minimal"]:
		workspace.choose_preset(id, true)
		workspace.change_part("items", "scale", 1.7)
		workspace.change_part("items", "enabled", false)
		workspace.change_arc(0, "thickness", 12)
		workspace.model.working.icons.InventoryButton = false
		workspace.reset_builtin()
		var defaults := Presets.preset(id)
		_expect(workspace.model.working.parts.items == defaults.parts.items
			and workspace.model.working.parts.medallion.arcs == defaults.parts.medallion.arcs
			and workspace.model.working.icons == defaults.icons,
			"Restore default restores geometry, curves and icons for " + id)
		_expect(chat.input.text == "unfinished private draft" and chat.destination_key == "pm:mira"
			and system.output.get_parsed_text().contains("Entered Four Gates") and workspace.model.custom.size() == custom_count,
			"Restore default preserves drafts, recipients, feeds and custom presets for " + id)
		workspace.undo_edit()
		_expect(workspace.model.working.parts.items.scale == 1.7 and not workspace.model.working.parts.items.enabled,
			"Restore default can be undone for " + id)
		workspace.redo_edit()
		_expect(workspace.model.working.parts.items == defaults.parts.items, "Restore default can be redone for " + id)
		var reset_path := "res://test-artifacts/hud-presets/reset-default.cfg"
		workspace.model.save_file(reset_path)
		var reloaded := Presets.new()
		reloaded.load_file(reset_path)
		_expect(reloaded.active == id and reloaded.working.parts.items == defaults.parts.items and reloaded.custom.has(custom_id),
			"restored defaults and existing customs survive saving for " + id)
	workspace._restore_snapshot(snapshot)
	await _frames()
	_expect(chat.options.font_size == 19, "Undo restores chat appearance as well as layout")

func _grid_and_edge_docks(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("classic", true)
	workspace.panel.position = Vector2(24, 24)
	await _frames()
	var items: Control = workspace._root("items")
	var menu: Control = workspace._root("utilities")
	var resources: Control = workspace._root("resources")
	_expect(workspace.modern_compass.visible and not main.clock_face.visible and main.clock_text.visible,
		"option 2 uses a separate compass and digital clock without a duplicate compass")
	_expect(main.quick_slot_container.columns == 3 and main.casting_bar._column.columns == 3
		and ceili(float(workspace.model.working.parts.items.slots) / main.quick_slot_container.columns) == 2,
		"option 2 defaults to two rows by three columns for both quick bars")
	var item_rect: Rect2 = workspace._visual_rect("items")
	var spell_rect: Rect2 = workspace._visual_rect("spells")
	var menu_rect: Rect2 = workspace._visual_rect("utilities")
	var resource_rect: Rect2 = workspace._visual_rect("resources")
	_expect(absf(item_rect.end.x - workspace._visual_rect("clock").position.x) < 1 and absf(item_rect.end.y - main.game_view.size.y) < 1,
		"option 2 items meet the clock column and the bottom game edge")
	_expect(absf(spell_rect.end.x - item_rect.position.x) < 1 and absf(spell_rect.end.y - item_rect.end.y) < 1,
		"option 2 quick spells dock to the left of quick items with bottom edges aligned")
	_expect(absf(menu_rect.position.x) < 1 and absf(menu_rect.end.x - spell_rect.position.x) < 1 and absf(menu_rect.end.y - item_rect.end.y) < 1,
		"option 2 menu spans to the spell grid with all bottom edges aligned")
	_expect(absf(resource_rect.end.y - menu_rect.position.y) < 1 and absf(resource_rect.size.x - menu_rect.size.x) < 1,
		"option 2 resource strip docks above and stretches to the menu width")
	_expect(workspace.model.working.parts.resources.show_icons and workspace.modern_resources.Icons.icon_for("health") != null,
		"resource icons are available and enabled in option 2")
	var clock_scale: Vector2 = workspace._root("clock").scale
	workspace.change_part("clock", "axis_scale", Vector2(1.25, 1))
	_expect(workspace._root("clock").scale.x > clock_scale.x and is_equal_approx(workspace._root("clock").scale.y, clock_scale.y),
		"fixed HUD widgets also support independent width and height scales")
	workspace.undo_edit()
	_expect(workspace._root("clock").scale == clock_scale, "Undo restores independent widget scaling")
	workspace.select_component("utilities")
	var handles: Dictionary = workspace._resize_handles("utilities")
	var origin: Vector2 = handles.left.get_center()
	var old_size: Vector2 = menu.size
	await _gesture(workspace, origin, origin + Vector2(110, 0))
	_expect(menu.size.x < old_size.x - 90 and absf(menu.size.y - old_size.y) < 1,
		"left resize handle changes menu width independently of height")
	_expect(workspace.model.working.parts.utilities.dock_target == "spells" and not workspace.model.working.parts.utilities.extend_to_edge,
		"manual width resizing keeps the menu join and releases its edge extension")
	handles = workspace._resize_handles("utilities")
	origin = handles.top.get_center()
	old_size = menu.size
	await _gesture(workspace, origin, origin + Vector2(0, -60))
	_expect(menu.size.y > old_size.y + 40 and absf(menu.size.x - old_size.x) < 1,
		"top resize handle changes menu height independently of width")
	_expect(workspace.utility_grid.columns < workspace._grid_count("utilities"),
		"taller menu aspect ratios reflow icons into multiple rows")
	workspace.dock_component("items", "none", "right")
	workspace.change_part("items", "grid_mode", "aspect")
	workspace.change_part("items", "dimensions", Vector2(300, 70))
	await _frames()
	_expect(main.quick_slot_container.columns == 6, "a wide item area reflows six slots into one row")
	workspace.change_part("items", "dimensions", Vector2(100, 190))
	await _frames()
	_expect(main.quick_slot_container.columns == 2, "a tall item area reflows the same slots into three by two")
	for button: Button in main.quick_slot_buttons:
		if button.visible:
			_expect(items.get_global_rect().grow(2).encloses(button.get_global_rect()), "reflowed item slot remains reachable: " + str(button.name))
	workspace.dock_component("spells", "none", "right")
	workspace.change_part("spells", "grid_mode", "aspect")
	workspace.change_part("spells", "dimensions", Vector2(100, 190))
	await _frames()
	_expect(main.casting_bar._column.columns == 2, "spell areas use the same three-by-two aspect reflow")
	workspace.set_grid_columns("spells", 3)
	await _frames()
	_expect(main.casting_bar._column.columns == 3 and workspace.model.working.parts.spells.grid_mode == "fixed", "explicit column selection overrides aspect reflow")
	workspace.set_grid_rows("spells", 3)
	await _frames()
	_expect(main.casting_bar._column.columns == 2, "explicit row selection supports three rows")
	workspace.dock_component("items", "screen", "bottom_right")
	await _frames()
	item_rect = workspace._visual_rect("items")
	_expect(item_rect.end.distance_to(main.game_view.size) < 1, "screen docking has no forced six-pixel margin")
	var snap: Dictionary = workspace._snap_for("items")
	_expect(snap.get("target") == "screen" and snap.get("side") == "bottom_right", "screen corners offer a dock preview")
	var path := "res://test-artifacts/hud-presets/grid-edges.cfg"
	workspace.model.save_file(path)
	var reloaded := Presets.new()
	reloaded.load_file(path)
	_expect(reloaded.working.parts.items.edge_dock == "bottom_right" and reloaded.working.parts.items.grid_mode == "aspect"
		and reloaded.working.parts.utilities.dock_align == "end", "grid areas, edge docks and alignment survive saving")
	workspace.choose_preset("classic", true)
	root.size = Vector2i(900, 700)
	await _frames(12)
	item_rect = workspace._visual_rect("items")
	menu_rect = workspace._visual_rect("utilities")
	spell_rect = workspace._visual_rect("spells")
	_expect(workspace._visual_rect("clock").end.distance_to(main.game_view.size) < 1 and absf(menu_rect.position.x) < 1 and absf(menu_rect.end.x - spell_rect.position.x) < 1,
		"option 2 connected bottom dock adapts to a resized game window")
	root.size = Vector2i(1440, 900)
	await _frames(12)
	workspace._restore_snapshot(snapshot)
	await _frames()

func _resource_and_frame_controls(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("classic", true)
	workspace.change_part("party", "enabled", true)
	await _frames()
	_expect(workspace.party_summary.visible and workspace.party_summary.get_combined_minimum_size().y >= 156,
		"option 2 party roster includes a detailed live player summary")
	workspace.change_part("party", "show_self", false)
	await _frames()
	_expect(not workspace.party_summary.visible, "hiding yourself also hides the detailed player summary")
	workspace.change_part("party", "show_self", true)
	_expect(workspace.model.working.banner_options.banner_background, "option 2 frames the character banner as in the concept")
	var chrome_script := preload("res://src/ui/hud_panel_chrome.gd")
	var resources: Control = workspace._root("resources")
	var menu: Control = workspace._root("utilities")
	var chrome: Node2D = resources.get_node("_HudChrome")
	_expect(chrome.config.show_background and chrome.config.show_border, "option 2 resource frame is enabled by default")
	_expect(chrome_script.edge_segments(resources.get_global_rect(), SIDE_BOTTOM, chrome.neighbours).is_empty(),
		"resource and menu panels remove their shared border on both sides")
	var menu_chrome: Node2D = menu.get_node("_HudChrome")
	_expect(chrome_script.edge_segments(menu.get_global_rect(), SIDE_TOP, menu_chrome.neighbours).is_empty(),
		"menu frame has no internal seam against its resource strip")
	var neighbours: Array[Rect2] = [Rect2(40, 20, 60, 30)]
	_expect(chrome_script.edge_segments(Rect2(0, 0, 100, 20), SIDE_BOTTOM, neighbours) == [Vector2(0, 40)],
		"partial joins keep the exposed part of a wider panel border")
	workspace.change_part("resources", "show_background", false)
	_expect(not chrome.config.show_background and chrome.config.show_border, "border-only resource panels are supported")
	_expect(not chrome_script.edge_segments(menu.get_global_rect(), SIDE_TOP, menu_chrome.neighbours).is_empty(),
		"a neighbour keeps its own border when the other panel background is disabled")
	workspace.change_part("resources", "show_border", false)
	_expect(not chrome.config.show_background and not chrome.config.show_border, "resource background and border can both be disabled")
	workspace.change_part("resources", "show_background", true)
	_expect(chrome.config.show_background and not chrome.config.show_border, "background-only resource panels are supported")
	workspace.move_resource("mana", -1)
	_expect(workspace.modern_resources.keys[0] == "mana", "resource order changes the live meter layout")
	workspace.change_resource_color("mana", Color("e55f9c"))
	_expect(workspace.modern_resources.palette.mana == Color("e55f9c") and workspace.party_summary.palette.mana == Color("e55f9c"),
		"resource color reaches the strip and detailed player visualization")
	var icon: Texture2D = workspace.modern_resources.Icons.tinted_icon("mana", Color("e55f9c"))
	var image := icon.get_image()
	var tinted := false
	for y: int in image.get_height():
		for x: int in image.get_width():
			var pixel := image.get_pixel(x, y)
			if pixel.a > 0.5 and pixel.r > pixel.b * 1.2 and pixel.b > pixel.g: tinted = true
	_expect(tinted, "changing Ether to pink recolors its blue source emblem to the chosen hue")
	for mode: String in ["dial", "digital", "both"]:
		workspace.change_part("clock", "clock_mode", mode)
		await _frames()
		_expect(main.clock_face.visible == (mode != "digital") and main.clock_text.visible == (mode != "dial"),
			"clock mode uses the original live widgets: " + mode)
		var capture: Dictionary = workspace.model.working.duplicate(true)
		workspace._capture_live(capture)
		_expect(capture.parts.clock.enabled and capture.parts.clock.clock_mode == mode, "clock mode remains enabled when captured: " + mode)
	workspace.change_part("clock", "enabled", false)
	var hidden_clock: Dictionary = workspace.model.working.duplicate(true)
	workspace._capture_live(hidden_clock)
	_expect(not hidden_clock.parts.clock.enabled and hidden_clock.parts.clock.clock_mode == "both", "hiding a clock retains its selected display mode for later")
	workspace.change_part("clock", "enabled", true)
	workspace.change_part("clock", "show_background", false)
	workspace.change_part("clock", "show_border", false)
	workspace.change_part("compass", "show_background", false)
	workspace.change_part("compass", "show_border", false)
	workspace.change_part("spells", "slots", 12)
	workspace.change_part("items", "slots", 8)
	await _frames()
	_expect(main.casting_bar.visible_slot_count == 12 and main.quick_slot_buttons[7].visible, "HUD editor changes the real quick spell and quick item counts")
	workspace.select_component("resources")
	_expect(workspace.details.has_node("ResourceOption_mana"), "resource editor provides ordered visibility and color controls")
	workspace.change_part("clock", "clock_mode", "digital")
	var path := "res://test-artifacts/hud-presets/resource-frames.cfg"
	workspace.model.save_file(path)
	var saved := Presets.new()
	saved.load_file(path)
	_expect(saved.working.meter_order[0] == "mana" and saved.working.resource_colors.mana == Color("e55f9c")
		and not saved.working.parts.resources.show_border and not saved.working.parts.clock.show_background and saved.working.parts.clock.clock_mode == "digital"
		and saved.working.parts.party.show_player_details and saved.working.parts.spells.slots == 12 and saved.working.parts.items.slots == 8,
		"resource order, colors, frames, detailed player and quick counts survive saving")
	var old: Dictionary = Presets.preset("classic")
	old.parts.clock.erase("show_background")
	old.parts.clock.erase("show_border")
	old.parts.clock.frame_style = "floating"
	_expect(not Presets.normalise(old).parts.clock.show_background and not Presets.normalise(old).parts.clock.show_border,
		"older floating-window settings migrate without gaining a frame")
	workspace._restore_snapshot(snapshot)
	await _frames()

func _resize_edge(workspace: Control, key: String, side: String, destination: Vector2, bypass := false) -> Array:
	workspace.select_component(key)
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.shift_pressed = bypass
	click.position = workspace._resize_handles(key)[side].get_center()
	workspace.handle_input(click)
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.position = destination
	motion.shift_pressed = bypass
	workspace.handle_input(motion)
	var guides: Array = workspace._resize_guides.duplicate(true)
	click.pressed = false
	click.position = destination
	workspace.handle_input(click)
	await _frames()
	return guides

func _resize_and_round_frames(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("classic", true)
	workspace.panel.position = Vector2(24, 24)
	await _frames()
	var resource_rect: Rect2 = workspace._visual_rect("resources")
	for key: String in ["spells", "items", "compass"]:
		_expect(absf(workspace._visual_rect(key).position.y - resource_rect.position.y) < 1,
			"option 2 aligns the top of " + key + " with its resource strip")
	_expect(workspace.model.working.parts.party.enabled and workspace.model.working.parts.party.dimensions == Vector2(220, 271)
		and workspace.model.working.parts.party.offset == Vector2(6, 6) and workspace.model.working.parts.party.show_player_details,
		"option 2 party defaults use the tester's top-left geometry and detailed self view")
	var chrome := preload("res://src/ui/hud_panel_chrome.gd")
	var clock: Control = workspace._root("clock")
	var compass: Control = workspace._root("compass")
	var clock_frame: Node2D = clock.get_node("_HudChrome")
	var compass_frame: Node2D = compass.get_node("_HudChrome")
	_expect(compass_frame.shape == "rectangle" and chrome.edge_segments(clock.get_global_rect(), SIDE_TOP, clock_frame.neighbours).is_empty()
		and chrome.edge_segments(compass.get_global_rect(), SIDE_BOTTOM, compass_frame.neighbours).is_empty(),
		"docked compass and digital clock share their background and outside border")
	workspace.change_part("compass", "compass_corners", "transparent")
	_expect(compass_frame.shape == "circle" and not chrome.edge_segments(clock.get_global_rect(), SIDE_TOP, clock_frame.neighbours).is_empty(),
		"transparent compass corners retain its circular frame and restore the clock's exposed border")
	workspace.change_part("compass", "compass_corners", "filled")
	workspace.dock_component("compass", "none", "right")
	_expect(compass_frame.shape == "rectangle", "filled compass corners work while undocked")
	workspace.change_part("compass", "compass_corners", "fill_when_docked")
	workspace.change_part("skills", "enabled", true)
	_expect(compass_frame.shape == "rectangle", "automatic compass fill also recognizes windows docked to it")
	workspace.change_part("skills", "enabled", false)
	_expect(compass_frame.shape == "circle", "automatic compass corner fill is transparent while undocked")
	workspace.choose_preset("classic", true)
	workspace.change_part("spells", "dimensions", Vector2(144, 80))
	await _frames()
	workspace.select_component("spells")
	var origin: Vector2 = workspace._resize_handles("spells").top.get_center()
	var resource_top: float = workspace._selection_rect("resources").position.y
	var width: float = workspace._selection_rect("spells").size.x
	var guides := await _resize_edge(workspace, "spells", "top", Vector2(origin.x, resource_top + 5))
	_expect(absf(workspace._selection_rect("spells").position.y - resource_top) < 1 and not guides.is_empty(),
		"dragging a height handle near another window snaps to its edge and displays a guide")
	_expect(absf(workspace._selection_rect("spells").size.x - width) < 1, "height snapping retains the independent window width")
	_expect(workspace.model.working.parts.spells.dock_target == "items", "height snapping keeps its existing dock")
	_expect(main.casting_bar._column.columns == 3, "height snapping preserves a complete three-column grid")
	workspace.undo_edit()
	_expect(absf(workspace.model.working.parts.spells.dimensions.y - 80) < 1, "Undo reverses a snapped resize as one gesture")
	workspace.redo_edit()
	_expect(absf(workspace._selection_rect("spells").position.y - resource_top) < 1, "Redo restores the snapped edge")
	workspace.choose_preset("classic", true)
	workspace.change_part("spells", "dimensions", Vector2(144, 80))
	await _frames()
	origin = workspace._resize_handles("spells").top.get_center()
	resource_top = workspace._selection_rect("resources").position.y
	guides = await _resize_edge(workspace, "spells", "top", Vector2(origin.x, resource_top + 5), true)
	_expect(guides.is_empty() and absf(workspace._selection_rect("spells").position.y - resource_top - 5) < 1,
		"Shift bypasses resize snapping for precise placement")
	var snap := preload("res://src/ui/hud_resize_snap.gd")
	var targets: Array[Dictionary] = [{"key":"other", "rect":Rect2(95, 95, 20, 20)}]
	var result := snap.snap(Rect2(10, 10, 80, 80), Vector2.ONE, targets, Rect2(0, 0, 500, 500), Vector2(10, 10))
	_expect(result.rect == Rect2(10, 10, 85, 85) and result.guides.size() == 2, "corner resizing snaps both dimensions independently")
	workspace.choose_preset("classic", true)
	workspace.change_part("minimap", "frame_shape", "circle")
	workspace.change_part("minimap", "dimensions", Vector2(300, 240))
	workspace.change_part("minimap", "axis_scale", Vector2(1.4, 0.7))
	await _frames()
	var map: Control = workspace._root("minimap")
	var map_frame: Node2D = map.get_node("_HudChrome")
	_expect(map_frame.shape == "circle" and absf(map.get_global_rect().size.x - map.get_global_rect().size.y) < 1
		and main._minimap_shape == "round", "circular minimap frames clip the map and remain round with unequal saved dimensions and scales")
	workspace.select_component("minimap")
	origin = workspace._resize_handles("minimap").left.get_center()
	await _resize_edge(workspace, "minimap", "left", origin + Vector2(-32, 0), true)
	_expect(absf(map.get_global_rect().size.x - map.get_global_rect().size.y) < 1, "resizing a minimap side preserves its circular border")
	workspace.change_part("minimap", "frame_shape", "rectangle")
	_expect(map_frame.shape == "rectangle" and main._minimap_shape == "round", "a round map may also use a filled rectangular HUD frame")
	workspace.change_part("minimap", "frame_shape", "match_map")
	main._on_minimap_shape_selected(0)
	_expect(map_frame.shape == "rectangle", "native minimap shape controls update the HUD frame to square")
	main._on_minimap_shape_selected(1)
	_expect(map_frame.shape == "circle", "native minimap shape controls also update the HUD frame to circle")
	for design: String in Presets.HUD_BORDERS:
		workspace.change_part("minimap", "hud_border_style", design)
		_expect(map_frame.config.hud_border_style == design, "live map frame supports border design " + design)
	workspace.change_part("minimap", "frame_shape", "circle")
	workspace.change_part("compass", "compass_corners", "filled")
	workspace.change_part("compass", "hud_border_style", "ornate")
	var path := "res://test-artifacts/hud-presets/resize-frame-options.cfg"
	workspace.model.save_file(path)
	var saved := Presets.new()
	saved.load_file(path)
	_expect(saved.working.parts.minimap.frame_shape == "circle" and saved.working.parts.minimap.hud_border_style == "ornate"
		and saved.working.parts.compass.compass_corners == "filled", "map shape, decorative borders and compass corner mode survive saving")
	workspace._restore_snapshot(snapshot)
	await _frames()

func _revised_defaults_and_minimap(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("heritage", true)
	await _frames()
	_expect(main.casting_bar._column.columns == 1 and main.quick_slot_container.columns == 1
		and main.clock_face.visible and main.clock_text.visible and workspace.modern_compass.visible,
		"option 1 retains the player's dial/digital clock and separate compass stack")
	var heritage: Dictionary = workspace.model.working.parts
	_expect(heritage.spells.dimensions.is_equal_approx(heritage.items.dimensions)
		and heritage.spells.flush_slots and heritage.items.flush_slots
		and heritage.spells.slot_gap == 0 and heritage.items.slot_gap == 0,
		"option 1 uses matching flush six-slot quick columns")
	_expect(heritage.clock.dock_target == "compass" and heritage.research.dock_target == "clock"
		and heritage.research.dimensions == Vector2(84, 28) and heritage.status.enabled
		and heritage.resources.show_icons and heritage.resources.show_labels,
		"saved Heritage research, indicators and resource labels use responsive dock connections")
	var spell: Button = main.casting_bar.buttons[0]
	var item: Button = main.quick_slot_buttons[0]
	_expect(spell.get_global_rect().size.distance_to(item.get_global_rect().size) < 1
		and absf(spell.get_global_rect().size.x - 42) < 1,
		"Heritage spell and item buttons are equal 42-pixel squares")
	_expect(workspace.clock_art.visible and main.clock_face.self_modulate.a == 0
		and not main.clock_hand.visible and main.clock_face.get_global_rect().size.y >= 62,
		"Heritage uses a brass dial at least as large as the original legacy clock")
	var face: Rect2 = main.clock_face.get_global_rect()
	var compass: Rect2 = workspace.modern_compass.get_global_rect()
	var dial_diameter: float = minf(face.size.x, face.size.y) - 4 * main.clock_face.get_global_transform().get_scale().x
	_expect(absf(dial_diameter / (minf(compass.size.x, compass.size.y) * 0.92) - 1) < 0.1,
		"Heritage clock dial and compass have matching visible diameters")
	_expect(workspace._root("skills").visible and not workspace.model.working.parts.party.enabled,
		"Heritage shows side statistics by default while keeping the party roster hidden")
	var default_stats: Rect2 = workspace._visual_rect("skills")
	var research_rect: Rect2 = workspace._visual_rect("research")
	_expect(absf(default_stats.position.x - research_rect.position.x) < 1
		and absf(default_stats.end.x - research_rect.end.x) < 1
		and absf(default_stats.position.y - maxf(workspace._visual_rect("items").end.y, workspace._visual_rect("spells").end.y)) < 1
		and absf(default_stats.end.y - research_rect.position.y) < 1,
		"default Heritage statistics fill the aligned column between quick bars and lower instruments")
	workspace.change_part("skills", "enabled", true)
	root.size = Vector2i(1440, 810)
	await _frames(8)
	var stat_rect: Rect2 = workspace._visual_rect("skills")
	_expect(absf(stat_rect.position.y - workspace._visual_rect("items").end.y) < 1
		and stat_rect.end.y <= workspace._visual_rect("research").position.y + 1,
		"optional Heritage statistics fit between quick bars and the lower instruments on a short viewport")
	root.size = Vector2i(1440, 900)
	await _frames(8)
	workspace.choose_preset("classic", true)
	await _frames()
	var map_config: Dictionary = workspace.model.working.parts.minimap
	_expect(map_config.enabled and map_config.map_shape == "round" and map_config.frame_shape == "circle"
		and map_config.hud_border_style == "ornate" and map_config.show_border,
		"option 2 defaults to the selected round brass minimap")
	_expect(not workspace._root("skills").visible and workspace.party_summary.visible,
		"option 2 retains the detailed tester party layout and hides side statistics")
	var extension: Control = main.extension_windows
	extension.close_all()
	extension.party_panel.show()
	extension.quest_panel.show()
	_expect(extension.close_top() and not extension.quest_panel.visible and extension.party_panel.visible,
		"Escape's window cascade closes ordinary windows while retaining the party roster")
	_expect(not extension.close_top() and extension.party_panel.visible,
		"Escape leaves the roster open when it is the only extension window")
	extension.toggle_party()
	_expect(not extension.party_panel.visible, "the explicit party toggle still closes the roster")
	workspace.apply_layout()
	main._layout_minimap_cardinals()
	_expect(not main.minimap_north.visible and not main.minimap_east.visible,
		"modern map annotations replace native cardinals without duplicate directions")
	var labels: Control = workspace.minimap_labels
	var heading: float = main.map_camera.rotation.y
	main.map_camera.rotation.y = 0
	var markers: Array = labels.markers()
	_expect(markers.size() == 1 and markers[0].arrow and markers[0].label == "N"
		and markers[0].position.y < 0 and absf(markers[0].position.x - labels.size.x / 2) < 1,
		"north-only arrowhead can sit outside the map radius")
	main.map_camera.rotation.y = PI / 2
	markers = labels.markers()
	_expect(markers[0].position.x < 0 and absf(markers[0].position.y - labels.size.y / 2) < 1,
		"the north arrow follows the live map's rotation")
	workspace.change_part("minimap", "map_directions", "all")
	workspace.change_part("minimap", "north_marker", "letter")
	workspace.change_part("minimap", "direction_offset", 30)
	workspace.change_part("minimap", "map_label_frame", true)
	workspace.change_part("minimap", "map_title", true)
	markers = labels.markers()
	_expect(markers.size() == 4 and not markers[0].arrow and labels.config.map_title and labels.config.map_label_frame,
		"all four letters, map title and optional HUD label plaques are selectable")
	_expect(absf(markers[0].position.distance_to(labels.size / 2) - (minf(labels.size.x, labels.size.y) / 2 - 1.5 + 30)) < 0.1,
		"direction spacing is measured from the minimap radius")
	var path := "res://test-artifacts/hud-presets/minimap-labels.cfg"
	workspace.model.save_file(path)
	var saved := Presets.new()
	saved.load_file(path)
	var restored: Dictionary = saved.working.parts.minimap
	_expect(restored.map_title and restored.map_directions == "all" and restored.north_marker == "letter"
		and restored.direction_offset == 30 and restored.map_label_frame,
		"map title, directions, marker, spacing and label frames survive saving")
	workspace.change_part("minimap", "map_directions", "none")
	workspace.change_part("minimap", "show_border", false)
	_expect(labels.markers().is_empty() and not workspace._root("minimap").get_node("_HudChrome").config.show_border,
		"directions and the minimap HUD border can be disabled independently")
	main.map_camera.rotation.y = heading
	workspace.choose_preset("current", true)
	main._layout_minimap_cardinals()
	_expect(main.minimap_north.visible and main.minimap_east.visible and not labels.visible,
		"Current HUD restores its native direction labels")
	workspace._restore_snapshot(snapshot)
	await _frames()

func _reciprocal_circle_docks(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	var chrome := preload("res://src/ui/hud_panel_chrome.gd")
	for side: String in ["left", "right", "top", "bottom"]:
		workspace.choose_preset("adventure", true)
		for key: String in ["spells", "items"]: workspace.dock_component(key, "none", "right")
		workspace.change_part("resources", "enabled", true)
		workspace.change_part("resources", "dimensions", Vector2(360, 44))
		workspace.change_part("resources", "show_background", true)
		workspace.change_part("resources", "show_border", true)
		workspace.change_part("resources", "edge_dock", "none")
		workspace.change_part("resources", "anchor", "free")
		workspace.change_part("resources", "position", Vector2(0.5, 0.45))
		workspace.change_part("resources", "offset", Vector2.ZERO)
		workspace.dock_component("medallion", "resources", side)
		await _frames()
		var orb: Control = workspace.parts.medallion
		var core: Rect2 = orb.dock_rect()
		core = Rect2(orb.position + core.position * orb.scale, core.size * orb.scale)
		var meter: Control = workspace._root("resources")
		var rect := Rect2(meter.position, meter.size * meter.scale)
		var gap: float = {"left":core.end.x - rect.position.x, "right":core.position.x - rect.end.x,
			"top":core.end.y - rect.position.y, "bottom":core.position.y - rect.end.y}[side]
		_expect(absf(gap) < 1, "circle docks by its visible ornament when moved to a meter's " + side)
		_expect(orb.connections.size() == 1 and orb.connections[0].horizontal == (side in ["left", "right"]),
			"reverse circle-to-meter docking draws a seamless " + side + " connector")
		var meter_frame: Node2D = meter.get_node("_HudChrome")
		var seam: int = {"left":SIDE_LEFT, "right":SIDE_RIGHT, "top":SIDE_TOP, "bottom":SIDE_BOTTOM}[side]
		var segments := chrome.edge_segments(meter.get_global_rect(), seam, meter_frame.neighbours)
		var length := 0.0
		for segment: Vector2 in segments: length += segment.y - segment.x
		var edge_length := meter.get_global_rect().size.y if side in ["left", "right"] else meter.get_global_rect().size.x
		_expect(length < edge_length - 1 and (side in ["left", "right"] or length > 1),
			"circle connection removes only the shared segment of the meter's " + side + " border")
	workspace._restore_snapshot(snapshot)
	await _frames()

func _joined_circle_backgrounds(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("adventure", true)
	await _frames()
	var defaults: Dictionary = workspace.model.working.parts
	_expect(defaults.resources.show_background and defaults.resources.show_border and defaults.resources.show_icons
		and defaults.resources.show_labels and defaults.resources.show_values and defaults.resources.dimensions == Vector2(686.3817, 40)
		and defaults.medallion.arcs[1].enabled and defaults.medallion.arcs[5].enabled
		and defaults.medallion.arcs[0].sweep_angle == 100 and defaults.medallion.arcs[5].sweep_angle == 68,
		"option 4 restores the saved framed XP strip and four customized curved meters")
	_expect(defaults.minimap.map_shape == "round" and defaults.minimap.map_palette == "natural"
		and defaults.minimap.map_title and defaults.minimap.north_marker == "arrow" and defaults.minimap.direction_offset == 21,
		"option 4 restores the saved round minimap with its title and offset north arrow")
	var orb: Control = workspace.parts.medallion
	var core: Rect2 = orb.core_rect()
	var probes: Array[Vector2] = [core.position + core.size * Vector2(0.08, 0.94), core.position + core.size * Vector2(0.92, 0.94)]
	var patches: Array[Dictionary] = orb.connection_background_patches()
	for point: Vector2 in probes:
		var count := 0
		for patch: Dictionary in patches:
			if patch.rect.has_point(point): count += 1
		_expect(count == 1, "the saved circle-to-quick-bar corner has one complete background layer")
	var chrome := preload("res://src/ui/hud_panel_chrome.gd")
	var meter: Control = workspace._root("resources")
	var segments := chrome.edge_segments(meter.get_global_rect(), SIDE_TOP, meter.get_node("_HudChrome").neighbours)
	var exposed := false
	for point: Vector2 in probes:
		var global_point: Vector2 = orb.get_global_transform() * point
		for segment: Vector2 in segments:
			if global_point.x > segment.x and global_point.x < segment.y: exposed = true
	_expect(not exposed, "the XP strip has no internal border through the filled circle corners")
	for side: String in ["bottom", "top", "left", "right"]:
		workspace.choose_preset("adventure", true)
		workspace.dock_component("medallion", "none", "right")
		workspace.change_part("medallion", "anchor", "free")
		workspace.change_part("medallion", "position", Vector2(0.4, 0.4))
		workspace.change_part("medallion", "offset", Vector2.ZERO)
		workspace.change_part("medallion", "border_design", {"bottom":"laurel", "top":"runic", "left":"plain", "right":"crystal"}[side])
		workspace.change_part("resources", "extend_to_edge", false)
		workspace.change_part("resources", "dimensions", Vector2(700, 44) if side in ["top", "bottom"] else Vector2(44, 700))
		workspace.dock_component("resources", "medallion", side)
		workspace.dock_component("spells", "medallion", "left" if side in ["top", "bottom"] else "top")
		workspace.dock_component("items", "medallion", "right" if side in ["top", "bottom"] else "bottom")
		for key: String in ["spells", "items"]:
			workspace.change_part(key, "dock_align", "end" if side in ["bottom", "right"] else "start")
		for key: String in ["resources", "spells", "items"]: workspace.change_part(key, "background_color", Color(0.1, 0.3, 0.4, 0.4))
		await _frames()
		core = orb.core_rect()
		var corners: Array = [Vector2(0.06, 0.06), Vector2(0.94, 0.06)] if side == "top" else (
			[Vector2(0.06, 0.94), Vector2(0.94, 0.94)] if side == "bottom" else (
			[Vector2(0.06, 0.06), Vector2(0.06, 0.94)] if side == "left" else [Vector2(0.94, 0.06), Vector2(0.94, 0.94)]))
		patches = orb.connection_background_patches()
		var covered := true
		for corner: Vector2 in corners:
			var point := core.position + core.size * corner
			var count := 0
			for patch: Dictionary in patches:
				if patch.rect.has_point(point) and is_equal_approx(patch.color.a, 0.4): count += 1
			covered = covered and count == 1
		_expect(covered, "perpendicular " + side + " joins fill their corners once across ornament designs")
		var overlap := false
		for first: int in patches.size():
			for second: int in range(first + 1, patches.size()):
				if patches[first].rect.intersection(patches[second].rect).get_area() > 0.01: overlap = true
		_expect(not overlap, "translucent " + side + " joins do not multiply their background opacity")
		workspace.change_part("resources", "show_background", false)
		await _frames()
		patches = orb.connection_background_patches()
		var open := true
		for corner: Vector2 in corners:
			for patch: Dictionary in patches:
				if patch.rect.has_point(core.position + core.size * corner): open = false
		_expect(open, "disabling the supporting " + side + " background restores open shoulders")
	workspace._restore_snapshot(snapshot)
	await _frames()

func _heritage_rail_continuity(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	var window_size := root.size
	for viewport: Vector2i in [Vector2i(1440, 900), Vector2i(1280, 720), Vector2i(1920, 1080)]:
		root.size = viewport
		workspace.choose_preset("heritage", true)
		await _frames(10)
		var rail: Control = workspace.parts.rail_panel
		var rail_rect := rail.get_global_rect()
		_expect(rail.visible and workspace._root("skills").visible
			and not workspace.model.working.parts.rail_panel.hide_with_stats,
			"Heritage keeps a continuous backdrop behind visible statistics at " + str(viewport))
		var logo: Rect2 = workspace._root("logo").get_global_rect()
		var spells: Rect2 = workspace._root("spells").get_global_rect()
		var items: Rect2 = workspace._root("items").get_global_rect()
		var stats: Rect2 = workspace._root("skills").get_global_rect()
		_expect(absf(logo.position.x - rail_rect.position.x) < 1 and absf(logo.end.x - rail_rect.end.x) < 1
			and absf(spells.position.x - rail_rect.position.x) < 1 and absf(items.end.x - rail_rect.end.x) < 1
			and absf(items.position.x - spells.end.x) < 1 and absf(stats.position.x - rail_rect.position.x) < 1
			and absf(stats.end.x - rail_rect.end.x) < 1,
			"logo, both quick columns and statistics share the rail width at " + str(viewport))
		_expect(absf(logo.end.y - items.position.y) < 1 and absf(stats.position.y - items.end.y) < 1
			and absf(stats.end.y - workspace._root("research").get_global_rect().position.y) < 1,
			"the upper rail has no gaps between logo, quick access and statistics at " + str(viewport))
		var clock_chrome: Node2D = workspace._root("clock").get_node("_HudChrome")
		_expect(clock_chrome.external_border and not clock_chrome.neighbours.is_empty()
			and workspace._frame_group("skills") == workspace._frame_group("rail_panel"),
			"rail instruments and statistics share a uniform connected border at " + str(viewport))
		var layers: Array[Rect2] = []
		for key: String in ["logo", "spells", "items", "skills", "research", "clock", "compass"]:
			layers.append(workspace._root(key).get_global_rect())
		var chrome: Node2D = rail.get_node("_HudChrome")
		for patch: Rect2 in chrome.background_patches(): layers.append(rail.get_global_transform() * patch)
		var continuous := true
		for column: float in [0.01, 0.5, 0.99]:
			for row: int in 80:
				var point := rail_rect.position + rail_rect.size * Vector2(column, (row + 0.37) / 80.0)
				var owners := 0
				for layer: Rect2 in layers:
					if layer.has_point(point): owners += 1
				continuous = continuous and owners == 1
		_expect(continuous, "the full right rail has complete single-layer background coverage at " + str(viewport))
	workspace.change_part("skills", "enabled", false)
	await _frames()
	_expect(workspace.parts.rail_panel.visible and not workspace._root("skills").visible,
		"hiding Heritage statistics retains the continuous right-hand backdrop")
	root.size = window_size
	workspace._restore_snapshot(snapshot)
	await _frames(8)

func _minimal_saved_layout_and_slots(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("minimal", true)
	await _frames()
	var parts: Dictionary = workspace.model.working.parts
	_expect(parts.spells.slots == 8 and parts.items.slots == 8 and parts.spells.dock_target == "items"
		and parts.spells.dock_side == "top" and parts.items.edge_dock == "bottom"
		and parts.spells.grid_mode == "aspect" and parts.spells.dimensions.is_equal_approx(Vector2(366.798, 52)),
		"option 5 restores the saved eight-spell row above eight bottom-docked items")
	_expect(not parts.resources.enabled and not parts.food_meter.enabled and not parts.load_meter.enabled and not parts.xp_meter.enabled
		and parts.party.show_player_details and parts.party.dimensions == Vector2(244, 239),
		"option 5 restores the detailed party view and hidden standalone resource strips")
	_expect(parts.minimap.map_shape == "round" and parts.minimap.map_palette == "natural"
		and parts.minimap.north_marker == "arrow" and parts.minimap.direction_offset == 18
		and parts.compass.dimensions.is_equal_approx(Vector2(380, 25.33334)) and parts.objectives.show_border,
		"option 5 restores the saved round minimap, slim compass and framed objectives")
	var trim: Node2D = main.quick_slot_buttons[0].get_node_or_null("_HudSlotTrim")
	_expect(trim != null and trim.visible and trim.config.hud_border_style == "beveled"
		and trim.config.border_color == Color("aa8d50") and not trim.show_behind_parent and not parts.items.show_border,
		"item icons receive brass bevels even while their outer HUD frame stays floating")
	var app := root.get_node("AppState")
	var saved_stats: Dictionary = app.stats.duplicate(true)
	var saved_inventory: Dictionary = app.inventory.duplicate(true)
	var saved_techniques: Dictionary = app.techniques.duplicate(true)
	var saved_knowledge: Array = app.known_knowledge.duplicate()
	var loadout = main.spell_loadout
	var saved_slots: Array = loadout.slots.duplicate(true)
	app.stats = {"magic":0, "ether":0}
	app.inventory = {}
	app.known_knowledge.clear()
	app.techniques = {"received_msec":Time.get_ticks_msec(), "techniques":[{
		"key":"heavy_blow", "name":"Heavy Blow", "known":true, "ready_in":10.0, "ap":5, "blocker":"Weapon unavailable"}]}
	loadout.slots[0] = {"id":0, "power":1}
	loadout.slots[1] = {"id":-1, "power":1, "technique":"heavy_blow"}
	main.casting_bar.refresh()
	main._sync_quick_slots()
	var spell: Button = main.casting_bar.buttons[0]
	var technique: Button = main.casting_bar.buttons[1]
	var reasons: Array = loadout.catalog.unavailable_reasons(0, app.known_knowledge, app.stats, app.inventory)
	_expect(not reasons.is_empty() and spell.self_modulate.a == 1 and spell.tooltip_text.contains(reasons[0]),
		"unavailable magic icons default to full opacity while retaining their blocker tooltip")
	_expect(technique.self_modulate.a == 1 and technique.tooltip_text.contains("Weapon unavailable") and main.casting_bar._technique_cooling,
		"unavailable skill icons default to full opacity while retaining their blocker and cooldown")
	_expect(main.quick_slot_buttons[0].disabled and trim.visible,
		"an empty or unavailable item retains its new border without becoming usable")
	workspace.change_part("spells", "icon_opacity", 0.8)
	workspace.change_part("spells", "unavailable_icon_opacity", 0.5)
	await _frames()
	_expect(is_equal_approx(spell.self_modulate.a, 0.4) and is_equal_approx(technique.self_modulate.a, 0.4),
		"editor opacity controls immediately affect both magic and skills")
	workspace.undo_edit()
	await _frames()
	_expect(is_equal_approx(spell.self_modulate.a, 0.8), "Undo restores the previous unavailable-icon opacity")
	workspace.redo_edit()
	workspace.change_part("items", "slot_border_style", "ornate")
	workspace.change_part("items", "slot_border_color", Color("82b8df"))
	await _frames()
	_expect(trim.config.hud_border_style == "ornate" and trim.config.border_color == Color("82b8df"),
		"slot trim style and color update independently of the outer frame")
	var path := "res://test-artifacts/hud-presets/minimal-slot-appearance.cfg"
	workspace.model.save_file(path)
	var saved := Presets.new()
	saved.load_file(path)
	_expect(saved.working.parts.items.slot_border_style == "ornate" and saved.working.parts.items.slot_border_color == Color("82b8df")
		and is_equal_approx(saved.working.parts.spells.icon_opacity, 0.8) and is_equal_approx(saved.working.parts.spells.unavailable_icon_opacity, 0.5),
		"slot borders and both icon opacity settings survive a saved layout")
	workspace.reset_builtin()
	await _frames()
	_expect(spell.self_modulate.a == 1 and technique.self_modulate.a == 1 and trim.config.hud_border_style == "beveled",
		"restoring option 5 restores full icon opacity and brass item trim")
	workspace.change_part("spells", "slot_border_style", "ornate")
	workspace.choose_preset("current", true)
	await _frames()
	_expect(not trim.visible and not spell.get_node("_HudSlotTrim").visible and spell.self_modulate.a == 1,
		"Current HUD clears custom slot trims and retains full default icon visibility")
	app.stats = saved_stats
	app.inventory = saved_inventory
	app.techniques = saved_techniques
	app.known_knowledge.assign(saved_knowledge)
	loadout.slots.assign(saved_slots)
	workspace._restore_snapshot(snapshot)
	main.casting_bar.refresh()
	main._sync_quick_slots()
	await _frames()

func _rail_and_resource_fit(workspace: Control) -> void:
	var snapshot: Dictionary = workspace._snapshot()
	workspace.choose_preset("heritage", true)
	workspace.change_part("skills", "enabled", false)
	await _frames()
	var rail: Control = workspace.parts.rail_panel
	_expect(rail.visible and rail.mouse_filter == Control.MOUSE_FILTER_IGNORE
		and absf(rail.size.y * rail.scale.y - main.game_view.size.y) < 1,
		"Heritage has an editable full-height blank rail without intercepting gameplay clicks")
	var point: Vector2 = rail.get_global_rect().position + rail.get_global_rect().size * Vector2(0.5, 0.65)
	_expect(workspace._pick(point).get("key") == "rail_panel", "blank rail space can be selected directly in the HUD editor")
	workspace.change_part("rail_panel", "hide_with_stats", true)
	workspace.change_part("skills", "enabled", true)
	await _frames()
	_expect(not rail.visible, "the filler can hide automatically while skill statistics are visible")
	workspace.change_part("skills", "enabled", false)
	await _frames()
	_expect(rail.visible, "the filler returns when side statistics are hidden")
	workspace.select_component("rail_panel")
	var height_before := rail.size.y
	var handle: Vector2 = workspace._resize_handles("rail_panel").bottom.get_center()
	await _resize_edge(workspace, "rail_panel", "bottom", handle - Vector2(0, 100), true)
	_expect(not workspace.model.working.parts.rail_panel.full_height and rail.size.y < height_before - 50,
		"resizing the blank panel's height releases full-screen fill and saves its dimensions")
	workspace.choose_preset("adventure", true)
	for key: String in Presets.RESOURCE_COLORS: workspace.model.working.meters[key] = true
	for field: String in ["show_labels", "show_values", "show_icons"]: workspace.model.working.parts.resources[field] = true
	workspace.model.working.parts.resources.dimensions = Vector2(700, 22)
	workspace.apply_layout()
	await _frames()
	var strip: Control = workspace.modern_resources
	_expect(strip.keys.size() == 6 and strip.size.y > 22, "all six enabled resources grow out of the saved thin XP-strip height")
	var grid: Dictionary = strip.geometry(strip.size)
	var inside := true
	for rect: Rect2 in strip.meter_rects():
		inside = inside and Rect2(Vector2.ZERO, strip.size).encloses(rect)
		inside = inside and rect.position.y + grid.bar_y + 7 <= strip.size.y
	_expect(inside and absf(workspace._visual_rect("resources").end.y - main.game_view.size.y) < 1,
		"bottom docking keeps every resource, value and bar inside the screen")
	workspace.change_part("resources", "dimensions", Vector2(240, 22))
	await _frames()
	_expect(strip.geometry(strip.size).rows >= 3 and strip.keys.size() == 6,
		"narrow resource strips reflow instead of losing enabled entries")
	workspace.change_part("resources", "background_color", Color(0.2, 0.1, 0.1, 0))
	workspace.change_part("resources", "show_background", false)
	workspace.change_part("resources", "show_background", true)
	_expect(strip.config.background_color.a > 0.9 and strip.get_node("_HudChrome").config.background_color.a > 0.9,
		"enabling an old transparent HUD backdrop restores visible opacity")
	workspace.change_part("resources", "border_color", Color(0.5, 0.2, 0.1, 0))
	workspace.change_part("resources", "show_border", true)
	_expect(strip.config.border_color.a == 1, "enabling a zero-opacity border makes it visible")
	workspace.change_part("resources", "background_color", Color(0.2, 0.1, 0.1, 0))
	workspace.change_frame_color("resources", "background_color", Color(0.1, 0.3, 0.4, 0))
	_expect(strip.config.background_color.a > 0.9 and is_equal_approx(strip.config.background_color.b, 0.4),
		"choosing a new frame color works on an inherited zero-alpha panel")
	workspace.change_part("resources", "background_color", Color(0.1, 0.3, 0.4, 0))
	_expect(strip.config.background_color.a == 0, "explicit opacity changes still allow an intentionally transparent frame")
	var old: Dictionary = workspace.model.working.duplicate(true)
	old.erase("frame_alpha_version")
	var migrated := Presets.normalise(old)
	_expect(migrated.parts.resources.background_color.a > 0.9,
		"older saved enabled panels migrate out of invisible inherited XP-strip colors")
	migrated.parts.resources.background_color.a = 0
	_expect(Presets.normalise(migrated).parts.resources.background_color.a == 0,
		"current explicitly transparent panels retain their opacity on reload")
	workspace.choose_preset("heritage", true)
	workspace.change_part("items", "scale", 0.72)
	workspace.choose_preset("adventure")
	workspace.change_part("items", "dock_align", "end")
	var path := "res://test-artifacts/hud-presets/remembered-options.cfg"
	workspace.model.save_file(path)
	var saved := Presets.new()
	saved.load_file(path)
	saved.select("heritage")
	_expect(is_equal_approx(saved.working.parts.items.scale, 0.72), "option 1 changes survive switching to option 4 and restarting")
	saved.select("adventure")
	_expect(saved.working.parts.medallion.dock_target == "resources" and saved.working.parts.items.dock_align == "end",
		"option 4 retains its separate saved center-dock arrangement")
	workspace.choose_preset("heritage")
	workspace.reset_builtin()
	_expect(workspace.model.working.parts.items.scale == Presets.preset("heritage").parts.items.scale,
		"Restore default discards only the selected built-in's saved changes")
	workspace.undo_edit()
	_expect(is_equal_approx(workspace.model.working.parts.items.scale, 0.72), "Undo recovers a built-in's saved changes after resetting it")
	workspace._restore_snapshot(snapshot)
	await _frames()

func _run() -> void:
	create_timer(120).timeout.connect(func() -> void:
		push_error("HUD preset test timed out")
		quit(99))
	root.size = Vector2i(1440, 900)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(PATH.get_base_dir()))
	var config := ConfigFile.new()
	config.set_value("unrelated", "keep", "untouched")
	config.save(PATH)
	var invalid := Presets.preset("classic")
	invalid.parts.spells.scale = NAN
	invalid.parts.items.offset = Vector2(INF, INF)
	invalid.parts.spells.rows = 500
	var safe := Presets.normalise(invalid)
	_expect(safe.parts.spells.scale == 1.0 and safe.parts.items.offset.is_finite() and safe.parts.spells.rows == 12,
		"invalid saved geometry is rejected or clamped")
	var cyclic := Presets.preset("adventure")
	cyclic.parts.medallion.dock_target = "spells"
	var acyclic := Presets.normalise(cyclic)
	_expect(acyclic.parts.medallion.dock_target == "none" or acyclic.parts.spells.dock_target == "none", "indirect docking cycles are rejected")
	_expect(Presets.BUILT_INS.size() == 6 and Presets.BUILT_INS.has("heritage") and Presets.BUILT_INS.has("minimal"), "all five concepts and the current HUD have presets")
	await _create()
	var workspace: Control = main.hud_workspace
	_expect(workspace.ready_to_layout and not workspace.manages_layout(), "first launch preserves the exact current HUD")
	_expect(main.settings_window.panel.find_child("HudEditorButton", true, false) != null, "HUD settings expose the editor")
	var chat: PanelContainer = main.chat_hud
	var system: PanelContainer = main.system_chat_hud
	var item_button: Button = main.quick_slot_buttons[0]
	var spell_button: Button = main.casting_bar.buttons[0]
	chat.set_destination("pm:mira")
	chat.input.text = "unfinished private draft"
	chat.options.font_size = 19
	chat.options.idle_fade = 12
	chat.apply_options()
	var app := root.get_node("AppState")
	app.append_local_message("Entered Four Gates.")
	app.chat_lines.append({"channel": 0, "text": "Tavi: Meet at the bridge."})
	main._sync_chat()
	workspace.open_editor()
	_expect(workspace.is_open() and main._world_input_blocked(), "editor blocks gameplay while its live controls remain selectable")
	for id: String in ["heritage", "classic", "modular", "adventure", "minimal"]:
		workspace.choose_preset(id, true)
		await _frames()
		_expect(chat == main.chat_hud and system == main.system_chat_hud and item_button == main.quick_slot_buttons[0]
			and spell_button == main.casting_bar.buttons[0], id + " reuses real chat, item and spell controls")
		_expect(chat.input.text == "unfinished private draft" and chat.destination_key == "pm:mira"
			and chat.options.font_size == 19 and chat.options.idle_fade == 12, id + " preserves chat draft, private recipient and appearance")
		_expect(system.output.get_parsed_text().contains("Entered Four Gates")
			and chat.output.get_parsed_text().contains("Tavi:"), id + " preserves both message feeds")
	await _grid_and_edge_docks(workspace)
	await _resource_and_frame_controls(workspace)
	await _resize_and_round_frames(workspace)
	await _revised_defaults_and_minimap(workspace)
	await _reciprocal_circle_docks(workspace)
	await _joined_circle_backgrounds(workspace)
	await _heritage_rail_continuity(workspace)
	await _minimal_saved_layout_and_slots(workspace)
	await _rail_and_resource_fit(workspace)
	workspace.panel.position = Vector2(24, 24)
	workspace.model.editor_position = Vector2(24, 24) / main.game_view.size
	workspace.select_component("medallion")
	workspace.change_part("medallion", "scale", 1.1)
	await _frames()
	_expect(workspace.panel.position.distance_to(Vector2(24, 24)) < 2, "selecting and editing HUD parts does not recenter the movable editor")
	workspace.choose_preset("minimal", true)
	_expect(workspace.modern_compass.config.compass_mode == "ribbon", "option 5 uses a live heading ribbon")
	_expect(main._minimap_mask_material.get_shader_parameter("hud_palette") == 0, "option 5 applies the saved natural minimap palette")
	_expect(not main.overhead_health_row.visible and main.overhead_player_name.visible, "option 5 can show names without overhead resource bars")
	_expect(not workspace.parts.objectives.visible, "an untracked objective never creates an empty HUD frame")
	workspace.choose_preset("classic", true)
	_expect(workspace.modern_compass.config.compass_mode == "round", "option 2 uses a round compass instrument")
	await _frames()
	_expect(main.casting_bar.panel.position.x > 800 and main.get_node("GameView/ItemQuickbar").position.x > 800,
		"option 2 places spells and items together at bottom right")
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = main.get_node("GameView/ItemQuickbar").get_global_rect().get_center()
	main._input(click)
	_expect(workspace.selected == "items", "clicking a live HUD component selects its editor options")
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.position = click.position + Vector2(-60, -40)
	main._input(motion)
	click.pressed = false
	main._input(click)
	await _frames()
	_expect(workspace.model.working.parts[workspace._dock_root("items")].anchor == "free",
		"dragging a live component saves the connected group's free position")
	workspace.choose_preset("modular", true)
	workspace.change_part("spells", "anchor", "right")
	workspace.change_part("spells", "orientation", "vertical")
	workspace.change_part("items", "anchor", "right")
	workspace.change_part("items", "orientation", "horizontal")
	await _frames()
	_expect(main.casting_bar._column.columns == 1 and main.quick_slot_container.columns == 8,
		"option 3 independently rotates spell and item bars on the right")
	main.casting_bar.set_expanded(false)
	await _frames()
	_expect(not main.casting_bar.panel.visible, "existing hide control works with a workspace layout")
	main.casting_bar.set_expanded(true)
	main.casting_bar.set_visible_slot_count(10)
	main.casting_bar.set_horizontal(true)
	await _frames()
	_expect(main.casting_bar.visible_slot_count == 10 and main.casting_bar.horizontal,
		"existing spell orientation and slot-count controls remain functional")
	workspace.choose_preset("adventure", true)
	await _editor_usability(workspace, chat, system)
	workspace.choose_preset("adventure", true)
	_expect(main._minimap_mask_material.get_shader_parameter("hud_palette") == 0, "option 4 applies the saved natural minimap palette")
	workspace.change_part("spells", "slots", 12)
	workspace.change_part("spells", "rows", 2)
	workspace.change_part("items", "rows", 2)
	workspace.change_part("items", "slots", 8)
	await _frames()
	_expect(main.casting_bar._column.columns == 6 and main.quick_slot_container.columns == 4,
		"option 4 shows two rows of actual spells and items")
	_expect(main.get_node("GameView/ItemQuickbar").size.y >= 90, "two item rows have enough visible height")
	_expect(workspace.parts.medallion.visible, "option 4 includes the live health medallion")
	for index: int in 8:
		workspace.change_arc(index, "enabled", true)
		workspace.change_arc(index, "resource", Presets.RESOURCES[index % 6])
		workspace.change_arc(index, "color", Color("88ccee"))
	workspace.change_part("medallion", "center_resource", "mana")
	workspace.change_part("medallion", "center_color", Color("2299dd"))
	workspace.change_part("medallion", "border_design", "crystal")
	workspace.change_part("items", "background_color", Color("123456ab"))
	workspace.change_part("chat", "text_color", Color("ffeedd"))
	workspace.change_part("medallion", "dimensions", Vector2(270, 225))
	await _frames()
	var arc_count := 0
	for arc: Dictionary in workspace.parts.medallion.config.arcs:
		if arc.enabled: arc_count += 1
	_expect(arc_count == 8 and workspace.parts.medallion.config.center_resource == "mana", "eight curved meters and the center independently select live resources")
	_expect(workspace.parts.medallion.config.border_design == "crystal" and workspace.parts.medallion._textures.size() >= 2, "generated circle borders are available in client")
	_expect(main.quick_slot_buttons[0].get_theme_stylebox("normal").bg_color == Color("123456ab"), "window color reaches the real item controls")
	_expect(chat.output.get_theme_color("default_color") == Color("ffeedd"), "chat text color remains independently editable")
	var values_script: GDScript = load("res://src/ui/hud_resource_values.gd")
	app.stats = {"health":120,"max_health":150,"ether":45,"max_ether":60,"food":42,"carried":115,"capacity":320}
	var load_strip: Control = workspace.parts.load_meter
	_expect(load_strip._values("load", load_strip._bar("load")).x == 115 and load_strip._caption("load") == "Load",
		"concept load meters display carried weight from live stats")
	workspace.change_part("load_meter", "load_display", "free")
	_expect(load_strip._values("load", load_strip._bar("load")).x == load_strip._bar("load").value and load_strip._caption("load") == "Free load",
		"players can retain the native free-load display")
	app.techniques = {"action_points":17,"max_action_points":30}
	_expect(values_script.read("mana").value == 45 and values_script.read("load").value == 115 and values_script.read("action").value == 17, "curved meters use live stats and the authoritative technique action pool")
	_expect(not values_script.read("mount_stamina").available, "mount stamina shows unavailable when unmounted")
	app.local_actor_id = 99
	app.actors[99] = {"name":"Kellan", "map":"four_gates"}
	app.actor_mounts[99] = {"owner":"Kellan", "map":"four_gates", "mode":"mounted", "endurance_ms":4500}
	_expect(values_script.read("mount_stamina").value == 4.5 and values_script.read("mount_stamina").available, "mounted stamina reads the live mount state")
	app.actor_mounts.clear()
	var spell_rect: Rect2 = main.casting_bar.panel.get_global_rect()
	var item_rect: Rect2 = workspace.parts.items.get_global_rect()
	var socket: Rect2 = workspace.parts.medallion.dock_rect()
	var orb: Control = workspace.parts.medallion
	_expect(absf(spell_rect.end.x - (orb.global_position.x + socket.position.x * orb.scale.x)) < 2
		and absf(item_rect.position.x - (orb.global_position.x + socket.end.x * orb.scale.x)) < 2, "both action bars attach directly to the circle sockets")
	workspace.change_part("medallion", "anchor", "free")
	workspace.change_part("medallion", "position", Vector2(0.4, 0.55))
	await _frames()
	main.casting_bar._layout()
	_expect(absf(main.casting_bar.panel.get_global_rect().end.x - (orb.global_position.x + socket.position.x * orb.scale.x)) < 2, "docked bars follow a moved and resized circle even after native spell relayout")
	main.casting_bar.set_docked(false)
	await _frames()
	_expect(workspace.model.working.parts.spells.dock_target == "none", "the native spell detach control releases a connected HUD bar")
	workspace.change_part("spells", "dock_target", "medallion")
	workspace.panel.position = Vector2(24, 24)
	workspace.select_component("items")
	var resize_click := InputEventMouseButton.new()
	resize_click.button_index = MOUSE_BUTTON_LEFT
	resize_click.pressed = true
	resize_click.position = workspace._resize_handle("items").get_center()
	var old_size: Vector2 = workspace._root("items").size
	workspace.handle_input(resize_click)
	var resize_motion := InputEventMouseMotion.new()
	resize_motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	resize_motion.position = resize_click.position + Vector2(60, 30)
	workspace.handle_input(resize_motion)
	resize_click.pressed = false
	workspace.handle_input(resize_click)
	_expect(workspace.model.working.parts.items.dimensions.x > old_size.x and workspace.model.working.parts.items.dimensions.y > old_size.y and workspace.model.working.parts.items.dock_target == "medallion", "dragging a resize handle independently enlarges a HUD area without detaching it")
	workspace.model.working.icons["InventoryButton"] = false
	workspace.apply_layout()
	_expect(not main.get_node("%InventoryButton").visible, "individual menu icon can be hidden without removing its control")
	workspace.preset_name.text = "My two-row HUD"
	workspace.save_custom(false)
	var saved_id: String = workspace.model.active
	_expect(workspace.commit() == OK, "custom layout saves successfully")
	config.load(PATH)
	_expect(config.get_value("unrelated", "keep") == "untouched", "saving presets preserves unrelated settings")
	workspace.commit_and_close()
	main._on_client_setting_changed("HUD", "show_fps", true)
	var outside := Presets.new()
	outside.load_file(PATH)
	_expect(outside.working.parts.fps.enabled, "settings changes outside the editor update the saved preset workspace")
	workspace.open_editor()
	workspace.choose_preset("classic", true)
	workspace.change_part("items", "enabled", false)
	workspace.reset_builtin()
	workspace.cancel_edit()
	await _frames()
	_expect(workspace.model.active == saved_id and workspace.model.working.parts.items.enabled,
		"cancel restores the layout and custom preset from before editing")
	main.queue_free()
	await _frames()
	await _create()
	workspace = main.hud_workspace
	_expect(workspace.model.active == saved_id and workspace.model.working.parts.spells.rows == 2
		and workspace.model.working.parts.items.rows == 2, "custom preset and rows survive a fresh scene")
	_expect(workspace.model.working.parts.medallion.arcs[7].enabled
		and workspace.model.working.parts.medallion.center_resource == "mana"
		and workspace.model.working.parts.items.dock_target == "medallion"
		and workspace.model.working.parts.medallion.border_design == "crystal"
		and workspace.model.working.parts.items.background_color == Color("123456ab"), "arc assignments, center, generated border, colors and docking survive a fresh scene")
	_expect(not main.get_node("%InventoryButton").visible and main.chat_hud.options.font_size == 19,
		"icon visibility and chat settings survive a fresh scene")
	root.size = Vector2i(800, 600)
	await _frames(8)
	for key: String in ["spells", "items", "utilities", "resources", "medallion"]:
		var control: Control = workspace._root(key)
		var rect: Rect2 = workspace._visual_rect(key)
		var bounds: Rect2 = main.game_view.get_global_rect()
		print("BOUNDS: ", key, " ", rect, " viewport=", bounds)
		_expect(rect.position.x >= 0 and rect.position.y >= 0 and rect.end.x <= bounds.end.x + 1 and rect.end.y <= bounds.end.y + 1,
			key + " remains reachable after shrinking the viewport")
	workspace.choose_preset("adventure", true)
	workspace.change_part("spells", "slots", 12)
	workspace.change_part("spells", "scale", 2.0)
	workspace.change_part("items", "slots", 8)
	workspace.change_part("items", "scale", 2.0)
	workspace.change_part("medallion", "scale", 1.5)
	await _frames()
	main.casting_bar._layout()
	await _frames()
	for key: String in ["spells", "items", "medallion"]:
		var rect: Rect2 = workspace._visual_rect(key)
		var bounds: Rect2 = main.game_view.get_global_rect()
		_expect(rect.position.x >= 0 and rect.end.x <= bounds.end.x + 1,
			"oversized dock group fits the viewport: " + key)
	workspace.open_editor()
	_expect(workspace.panel.position.distance_to(workspace.model.editor_position * main.game_view.size) < 2, "editor position survives reopening the client")
	workspace.choose_preset("current", true)
	await _frames()
	_expect(main.bottom_meters.get_parent() == main.get_node("GameView/Quickbar/QuickRows")
		and main.quick_slot_container.columns == 1 and main.right_rail.visible,
		"Current HUD restores the original bottom row and right rail")
	_expect(main.overhead_health_row.visible and main.ether_bottom_text.visible and main.food_bottom_text.visible,
		"Current HUD restores overhead bars and original meter numbers")
	_expect(main._minimap_mask_material.get_shader_parameter("hud_palette") == 0
		and main.chat_hud.dragger.reserved_right == WindowDrag.RESERVED_RIGHT_RAIL,
		"Current HUD restores native map colors and window boundaries")
	workspace.change_part("items", "enabled", false)
	workspace.reset_builtin()
	_expect(workspace.model.working.legacy and main.get_node("GameView/ItemQuickbar").visible,
		"Restore default also resets the original Current HUD")
	workspace.cancel_edit()
	main.queue_free()
	await _frames()
	print("HUD preset integration: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)
