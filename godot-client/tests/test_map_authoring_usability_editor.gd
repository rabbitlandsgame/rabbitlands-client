extends SceneTree
## Editor-mode checks for the map authoring usability layer on a tiny disposable
## region fixture: the fast terrain probe, the cursor readout and grid, ghost
## placement with its hotkeys and keep-placing, batch selection tools, prefabs,
## sculpt keys, time of day, top-down capture, markers, walkability, path
## drawing and extension, groups and copies, the selection bar, the play-test
## walker, the minimap, the territory picker, asset intake, the low-spec view,
## the toolbar, undo/redo, and that no helper node is ever saved.
##
## Godot_v4.7.2-stable_win64_console.exe --editor --headless --path . \
##     --script res://tests/test_map_authoring_usability_editor.gd

const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const OVERRIDE := preload("res://src/dev/map_authoring_region/asset_surface_override.gd")
const Catalog := preload("res://addons/map_asset_palette/asset_catalog.gd")
const Placement := preload("res://addons/map_asset_palette/placement.gd")
const Prefabs := preload("res://addons/map_asset_palette/prefab_library.gd")
const Thumbnails := preload("res://addons/map_asset_palette/thumbnail_renderer.gd")
const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")
const Tools := preload("res://addons/map_authoring_usability/selection_tools.gd")
const UsabilityPlugin := preload("res://addons/map_authoring_usability/plugin.gd")
const TimeOfDay := preload("res://addons/map_authoring_usability/time_of_day_preview.gd")
const TopDown := preload("res://addons/map_authoring_usability/top_down_capture.gd")
const Markers := preload("res://addons/map_asset_palette/marker_library.gd")
const Walkability := preload("res://addons/map_authoring_usability/walkability_overlay.gd")
const MARKER := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const WATER := preload("res://src/dev/map_authoring_region/water_region_control.gd")
const GroupTools := preload("res://addons/map_authoring_usability/group_tools.gd")
const Walker := preload("res://addons/map_authoring_usability/playtest_walker.gd")
const Structures := preload("res://addons/map_authoring_usability/structure_raster.gd")
const PathDraw := preload("res://addons/map_authoring_usability/path_draw_tool.gd")
const PlanWater := preload("res://addons/map_authoring_usability/plan_water.gd")
const Scatter := preload("res://addons/map_authoring_usability/scatter_tool.gd")
const ReviewNotes := preload("res://addons/map_authoring_usability/review_notes.gd")
const Published := preload("res://addons/map_authoring_usability/published_context.gd")
const ConceptMaster := preload("res://addons/map_authoring_usability/concept_master.gd")
## Heights in 0.2 m units on a 24 x 24 grid with walls and a steep band, and
## what eloria-server's sync_authored_collision.choose_stage makes of them: the
## largest reachable area at each stage factor, and the factor it picks.
const STAGE_REFERENCE := {
	"units": [
		2, 1, 1, 1, 5, 5, 5, 6, 9, 9, 9, 9, 13, 13, 14, 13, 17, 17, 17, 17, 21, 22, 21, 21,
		1, 1, 1, 1, 6, 5, 5, 5, 9, 9, 9, 10, 13, 13, 13, 13, 17, 17, 18, 17, 21, 21, 21, 21,
		1, 2, 1, 1, 5, 5, 5, 5, 10, 9, 9, 9, 13, 13, 13, 14, 17, 17, 17, 17, 21, 21, 22, 21,
		1, 1, 1, 1, 5, 6, 5, 5, 9, 9, 9, 9, 14, 13, 13, 13, 17, 17, 17, 18, 21, 21, 21, 21,
		1, 1, 2, 1, 5, 5, 5, 5, 9, 10, 9, 9, 13, 13, 13, 13, 18, 17, 17, 17, 21, 21, 21, 22,
		1, 1, 1, 1, 5, 5, 6, 5, 9, 9, 0, 9, 13, 14, 13, 13, 17, 17, 17, 17, 22, 21, 21, 21,
		1, 1, 1, 2, 5, 5, 5, 5, 9, 9, 0, 9, 13, 13, 13, 13, 17, 18, 17, 17, 21, 21, 21, 21,
		2, 1, 1, 1, 5, 5, 5, 6, 9, 9, 0, 9, 13, 13, 14, 13, 17, 17, 17, 17, 21, 22, 21, 21,
		1, 1, 1, 1, 6, 5, 5, 5, 9, 9, 9, 10, 13, 13, 13, 13, 17, 17, 18, 17, 21, 21, 21, 21,
		1, 2, 1, 1, 5, 5, 5, 5, 10, 9, 9, 9, 13, 13, 13, 14, 17, 17, 17, 17, 21, 21, 22, 21,
		1, 1, 1, 1, 5, 6, 5, 5, 9, 9, 9, 9, 14, 13, 13, 13, 17, 17, 17, 18, 21, 21, 21, 21,
		1, 1, 2, 1, 5, 5, 5, 5, 9, 10, 9, 9, 13, 13, 13, 13, 18, 17, 17, 17, 21, 21, 21, 22,
		1, 1, 1, 1, 5, 5, 6, 5, 9, 9, 9, 9, 13, 14, 13, 13, 17, 17, 17, 17, 22, 21, 21, 21,
		1, 1, 1, 2, 5, 5, 5, 5, 9, 9, 10, 9, 13, 13, 13, 13, 17, 18, 17, 17, 21, 21, 21, 21,
		2, 1, 1, 1, 5, 5, 5, 6, 9, 9, 9, 9, 13, 13, 14, 13, 17, 17, 17, 17, 21, 22, 21, 21,
		1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 21, 21, 21, 21,
		1, 2, 1, 1, 5, 5, 5, 5, 10, 9, 9, 9, 13, 13, 13, 14, 17, 17, 17, 17, 21, 21, 22, 21,
		1, 1, 1, 1, 5, 6, 5, 5, 9, 9, 9, 9, 14, 13, 13, 13, 17, 17, 17, 18, 21, 21, 21, 21,
		1, 1, 2, 1, 5, 5, 5, 5, 9, 10, 9, 9, 13, 13, 13, 13, 18, 17, 17, 17, 21, 21, 21, 22,
		1, 1, 1, 1, 5, 5, 6, 5, 9, 9, 9, 9, 13, 14, 13, 13, 17, 17, 17, 17, 22, 21, 21, 21,
		1, 1, 1, 2, 5, 5, 5, 5, 9, 9, 10, 9, 13, 13, 13, 13, 17, 18, 17, 17, 21, 21, 21, 21,
		2, 1, 1, 1, 5, 5, 5, 6, 9, 9, 9, 9, 13, 13, 14, 13, 17, 17, 17, 17, 21, 22, 21, 21,
		1, 1, 1, 1, 6, 5, 5, 5, 9, 9, 9, 10, 13, 13, 13, 13, 17, 17, 18, 17, 21, 21, 21, 21,
		1, 2, 1, 1, 5, 5, 5, 5, 10, 9, 9, 9, 13, 13, 13, 14, 17, 17, 17, 17, 21, 21, 22, 21,
	],
	"scores": {1: 96, 2: 555, 3: 555, 4: 555},
	"factor": 2,
}
const ASSET := preload("res://src/dev/map_authoring_region/asset_control.gd")
## Expected results computed with eloria-server's own fold functions
## (tools/collision_sources.requantise, sync_authored_collision stage rules) and a
## line-by-line replica of World.find_path; see the play-test walker parity check.
const WALKER_REFERENCE := {
	"fold_half": [
		10, 10, 12, 12, 40, 41, 90, 90, 200, 200, 250, 249,
		10, 11, 12, 13, 40, 42, 90, 91, 200, 201, 250, 250,
		0, 20, 30, 30, 60, 60, 120, 0, 180, 180, 220, 220,
		20, 20, 30, 31, 60, 61, 120, 121, 180, 181, 220, 221,
		5, 5, 7, 7, 9, 9, 11, 11, 13, 13, 15, 15,
		5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
		100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100,
		100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 0, 100,
		3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
		3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
		77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88,
		77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88,
	],
	"fold_factor": 6,
	"fold_codes": [
		3, 3, 10, 23, 50, 62,
		0, 8, 15, 0, 45, 55,
		1, 2, 2, 3, 3, 4,
		25, 25, 25, 25, 25, 0,
		1, 1, 1, 1, 1, 1,
		19, 20, 20, 21, 21, 22,
	],
	"grid": [
		5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
		5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
		5, 5, 9, 9, 9, 9, 9, 9, 5, 5,
		5, 5, 9, 0, 0, 0, 0, 9, 5, 5,
		5, 5, 9, 0, 6, 6, 0, 9, 5, 5,
		5, 5, 9, 0, 6, 6, 0, 9, 5, 5,
		5, 5, 7, 7, 7, 0, 0, 9, 5, 5,
		5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
		5, 0, 5, 0, 5, 3, 3, 2, 5, 5,
		5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
	],
	"searches": [
		{"start": [0, 0], "target": [9, 9], "path": [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [2, 6], [3, 6], [4, 7], [5, 7], [6, 8], [7, 9], [8, 9], [9, 9]]},
		{"start": [4, 4], "target": [0, 0], "path": [[4, 5], [4, 6], [3, 6], [2, 6], [1, 5], [1, 4], [1, 3], [1, 2], [1, 1], [0, 0]]},
		{"start": [0, 9], "target": [9, 0], "path": [[1, 9], [2, 9], [3, 9], [4, 9], [5, 8], [6, 7], [7, 7], [8, 7], [8, 6], [8, 5], [8, 4], [8, 3], [8, 2], [8, 1], [9, 0]]},
		{"start": [8, 9], "target": [6, 8], "path": [[7, 9], [6, 9], [6, 8]]},
		{"start": [0, 0], "target": [5, 4], "path": [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [2, 6], [3, 6], [4, 6], [4, 5], [5, 4]]},
	],
}
const DIR := "res://test-artifacts/map-usability"
const HEIGHT_PATH := DIR + "/fixture-heights.f32le"
const SCENE_PATH := DIR + "/fixture.tscn"
const RELOAD_PATH := DIR + "/fixture-saved.tscn"
const PREFAB_DIR := DIR + "/prefabs"
const GRID := Vector2i(41, 41)
const SETTING_KEYS := ["placement/keep_placing", "placement/snap_to_grid", "grid/step",
	"grid/cursor_grid", "placement/random_rotation", "placement/size_variation",
	"placement/align_to_surface", "viewport/show_cursor_readout", "time_of_day/minute",
	"markers/show", "markers/labels", "performance/low_spec", "concept/masters_folder",
	"concept/opacity"]

var failures := 0
var _saved_settings := {}
var _editor: Object
var _undo: EditorUndoRedoManager


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	if not Engine.is_editor_hint():
		push_error("map authoring usability test requires --editor")
		quit(1)
		return
	_editor = Engine.get_singleton("EditorInterface")
	var base := _editor.call("get_base_control") as Control
	var palette: Object = null
	var usability: Object = null
	for _attempt in 300:
		if base != null and base.has_meta(&"map_asset_palette_plugin") and \
				base.has_meta(&"map_authoring_usability_plugin"):
			palette = base.get_meta(&"map_asset_palette_plugin")
			usability = base.get_meta(&"map_authoring_usability_plugin")
			break
		await create_timer(0.1).timeout
	_expect(palette != null and usability != null and
		bool(_editor.call("is_plugin_enabled", "map_authoring_usability")),
		"project enables the Map Assets and Map Authoring Usability plugins")
	if palette == null or usability == null:
		_finish()
		return
	# Let the editor finish its first scan and layout load, as it has before a
	# person opens a scene; loading the layout mid-test is not a real situation.
	var filesystem := _editor.call("get_resource_filesystem") as EditorFileSystem
	for _attempt in 1200:
		if not filesystem.is_scanning():
			break
		await create_timer(0.1).timeout
	await create_timer(1.5).timeout
	var settings := _editor.call("get_editor_settings") as EditorSettings
	_expect(settings.has_setting("map_authoring/grid/step") and
		settings.has_shortcut("map_authoring/rotate_left") and
		settings.has_shortcut("map_authoring/drop_to_ground"),
		"preferences and rebindable shortcuts are registered in Editor Settings")
	for key: String in SETTING_KEYS:
		_saved_settings[key] = Settings.value(key)
	Settings.set_value("placement/keep_placing", true)
	Settings.set_value("placement/snap_to_grid", false)
	Settings.set_value("grid/step", 1.0)
	Settings.set_value("grid/cursor_grid", Settings.CursorGrid.ALWAYS)
	Settings.set_value("placement/random_rotation", false)
	Settings.set_value("placement/size_variation", 0.0)
	Settings.set_value("placement/align_to_surface", false)
	Settings.set_value("viewport/show_cursor_readout", true)
	Prefabs.directory = PREFAB_DIR
	_remove_tree(PREFAB_DIR)
	_undo = _editor.call("get_editor_undo_redo") as EditorUndoRedoManager

	var root := await _open_fixture()
	if root == null:
		_finish()
		return
	var entry := _entry(Catalog.entries(), "mirror_reed")
	_expect(not entry.is_empty(), "the native catalog still offers mirror_reed")
	var thumbnail_mesh := Thumbnails.merged_mesh(entry)
	_expect(thumbnail_mesh != null and thumbnail_mesh.get_surface_count() > 0 and
		thumbnail_mesh.surface_get_material(0) != null,
		"library thumbnails merge an asset's visible meshes with their materials")
	_test_probe(root)
	_test_describe_point(root)
	_test_adjusted_transform(root, entry)
	var camera := Camera3D.new()
	root.add_child(camera)
	_aim(camera, root, Vector2(20.0, 20.0))
	var placed := _test_ghost_placement(palette, root, entry, camera)
	_test_cursor_readout_and_grid(usability, root, camera)
	if placed.size() == 2:
		_test_selection_tools(usability, root, placed)
		_test_prefab(palette, root, placed, camera)
	var sculpt: Object = (_editor.call("get_base_control") as Control).get_meta(
		&"map_authoring_sculpt_plugin") \
		if (_editor.call("get_base_control") as Control).has_meta(&"map_authoring_sculpt_plugin") \
		else null
	_expect(sculpt != null, "the Territories plugin is active for the sculpt keys")
	if sculpt != null:
		_test_sculpt_keys(sculpt, usability, root, camera)
	_test_time_of_day(usability, root)
	await _test_top_down(usability, root)
	_test_marker_palette(palette, usability, root, camera)
	_test_walkability(usability, root)
	_test_structure_rules()
	await _test_structure_background(root)
	_test_plan_water(usability, root)
	_test_published_minimap(usability)
	_test_half_cell_water()
	_test_published_context()
	_test_concept_master(usability, root)
	_test_path_drawing(palette, usability, root, camera, entry)
	_test_road_extension(usability, root, camera)
	await _test_groups_and_copies(usability, root, camera)
	_test_selection_bar(usability, root)
	_test_walker_parity()
	_test_walker_stages_and_reach()
	_test_play_test(usability, root, camera)
	await _test_minimap(usability, root)
	_test_territory_picker()
	await _test_asset_intake(palette)
	_test_contract_guards(palette, usability, root, camera)
	_test_ground_and_plateaus(usability, root, camera)
	_test_heightmap_import(root)
	_test_scatter(palette, usability, root, camera, entry)
	_test_scatter_avoid_and_erase(usability, root, camera, entry)
	_test_review_notes(usability, root, camera)
	_test_notes_filter_and_dock(usability, root, camera)
	_test_low_spec(usability, root)
	_test_toolbar(usability)
	usability.call("set_time_preview", true, 90.0)
	usability.call("set_walkability_mode", Walkability.Mode.LIVE)
	usability.call("start_path_drawing", "road")
	_aim(camera, root, Vector2(12.0, 30.0))
	usability.call("_forward_3d_gui_input", camera,
		_click(camera.get_viewport().get_visible_rect().size * 0.5))
	await _test_save_excludes_helpers(palette, usability, root, entry, camera)
	usability.call("cancel_path_drawing")
	usability.call("set_walkability_mode", Walkability.Mode.OFF)
	usability.call("set_time_preview", false)
	if sculpt != null:
		sculpt.get("_sculpt").call("unbind")
	palette.call("_cancel_placement")
	camera.queue_free()
	_finish()


func _test_sculpt_keys(sculpt: Object, usability: Object, root: Node3D,
		camera: Camera3D) -> void:
	# The fixture is not in the territory catalog, so bind the brush the way
	# test_terrain_sculpt_editor.gd does, then drive the real plugin's input.
	var tool: Object = sculpt.get("_sculpt")
	var dock: Object = sculpt.get("_dock")
	var terrain := root.get_node("Terrain")
	var entry := {"ownership_polygon": PackedVector2Array([Vector2(0, 0), Vector2(40, 0),
		Vector2(40, 40), Vector2(0, 40)]), "translation": Vector3.ZERO,
		"ownership_sha256": String(root.get("ownership_polygon_sha256")), "editable": true}
	var bound: bool = tool.call("bind", root, terrain, entry, _undo)
	dock.call("set_sculpt_available", true)
	dock.call("set_sculpt_active", true)
	tool.call("set_enabled", true)
	_expect(bound and bool(tool.call("is_enabled")), "the sculpt brush binds to the fixture")
	if not bound:
		return
	dock.call("set_sculpt_mode", 0)
	var start: Dictionary = dock.call("sculpt_settings")
	var results := [
		sculpt.call("_forward_3d_gui_input", camera, _key(KEY_2)),
		sculpt.call("_forward_3d_gui_input", camera, _key(KEY_BRACKETRIGHT)),
		sculpt.call("_forward_3d_gui_input", camera, _key(KEY_BRACKETRIGHT, true)),
		sculpt.call("_forward_3d_gui_input", camera, _wheel(true)),
	]
	var changed: Dictionary = dock.call("sculpt_settings")
	var ring: StandardMaterial3D = tool.get("_ring_material")
	_expect(results.all(func(value: int) -> bool: return value == EditorPlugin.AFTER_GUI_INPUT_STOP) and
		int(changed.mode) == 1 and
		is_equal_approx(float(changed.radius), snappedf(snappedf(float(start.radius) * 1.25,
			0.5) * 1.25, 0.5)) and float(changed.strength) > float(start.strength) and
		ring.albedo_color.is_equal_approx(Color(1.0, 0.55, 0.25)),
		"2 picks Lower, ] and Shift+wheel grow the brush, Shift+] strengthens it, ring turns orange")
	var hints: PackedStringArray = sculpt.call("overlay_lines")
	_expect(hints.size() == 2 and "Sculpt Lower" in hints[0] and "radius" in hints[0],
		"sculpt hint lines describe the active brush")
	dock.call("set_sculpt_mode", 0)
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var hit: Vector3 = Probe.ray_hit(root, camera.project_ray_origin(centre),
		camera.project_ray_normal(centre)) as Vector3
	var before := Probe.height_at(root, hit)
	var press := _click(centre)
	press.ctrl_pressed = true
	sculpt.call("_forward_3d_gui_input", camera, press)
	var drag := InputEventMouseMotion.new()
	drag.position = centre
	drag.button_mask = MOUSE_BUTTON_MASK_LEFT
	drag.ctrl_pressed = true
	sculpt.call("_forward_3d_gui_input", camera, drag)
	var release := _click(centre)
	release.pressed = false
	sculpt.call("_forward_3d_gui_input", camera, release)
	var after := Probe.height_at(root, hit)
	_expect(after < before - 0.05,
		"Ctrl+drag with Raise lowers the ground (%.3f -> %.3f m)" % [before, after])
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	history.undo()
	_expect(absf(Probe.height_at(root, hit) - before) < 0.0001,
		"the inverted stroke is one ordinary sculpt undo step")
	dock.call("set_sculpt_mode", 3)
	var pick := _click(centre)
	pick.ctrl_pressed = true
	sculpt.call("_forward_3d_gui_input", camera, pick)
	var target := float((dock.call("sculpt_settings") as Dictionary).flatten_target)
	_expect(absf(target - before) < 0.06,
		"Ctrl+click with Flatten samples the height under the brush (%.2f m)" % target)
	usability.call("_refresh_hover")
	dock.call("set_sculpt_mode", 0)
	tool.call("set_enabled", false)
	dock.call("set_sculpt_active", false)


func _test_time_of_day(usability: Object, root: Node3D) -> void:
	_expect(TimeOfDay.describe(180.0) == "3:00 noon" and TimeOfDay.describe(0.0) == "0:00 midnight" and
		TimeOfDay.describe(90.0) == "1:30 dawn",
		"time labels use the game clock (360-minute day, noon at 3:00)")
	var on: bool = usability.call("set_time_preview", true, 180.0)
	var state := usability.call("time_preview_state") as Dictionary
	var holder := state.nodes as Node3D
	var sun := holder.get_node("Sun") as DirectionalLight3D if holder != null else null
	var noon_energy := sun.light_energy if sun != null else 0.0
	_expect(on and holder != null and holder.owner == null and
		not root.get_children().has(holder) and root.get_children(true).has(holder) and
		String(state.manifest).is_empty(),
		"the preview adds internal, unsaved sun/moon/environment (fallback daylight here)")
	usability.call("set_time_preview", true, 0.0)
	var moon := holder.get_node("Moon") as DirectionalLight3D if holder != null else null
	_expect(sun != null and sun.light_energy < noon_energy and moon != null and moon.visible,
		"midnight dims the sun and raises the moon, as DayNightBinder does in game")
	# A real territory manifest: Sunmane's published world.json is the noon reference.
	var region := String(root.get("region_id"))
	root.set("region_id", "sunmane_steppe")
	usability.call("set_time_preview", false)
	usability.call("set_time_preview", true, 180.0)
	state = usability.call("time_preview_state") as Dictionary
	var real_sun := (state.nodes as Node3D).get_node("Sun") as DirectionalLight3D \
		if state.nodes != null else null
	var manifest := WorldManifest.load_file(TimeOfDay.manifest_path_for("sunmane_steppe"))
	var declared := float(((manifest.data.environment as Dictionary).sun as Dictionary).energy)
	_expect(String(state.manifest).ends_with("sunmane_steppe/world.json") and real_sun != null and
		is_equal_approx(real_sun.light_energy, declared),
		"a catalogued territory previews its own manifest sun (noon energy %.2f)" % declared)
	usability.call("set_time_preview", false)
	root.set("region_id", region)
	_expect(not bool((usability.call("time_preview_state") as Dictionary).active) and
		root.get_children(true).all(func(node: Node) -> bool:
			return not String(node.name).begins_with("__MapAuthoringTimeOfDay")),
		"switching the preview off removes every preview node")
	var authored := Node3D.new()
	var saved_sun := DirectionalLight3D.new()
	authored.add_child(saved_sun)
	saved_sun.owner = authored
	var refused := TimeOfDay.new()
	_expect(not refused.enable(authored, 180.0) and "Sun" in refused.last_message,
		"scenes that save their own Sun (the pilot) keep their authored lighting")
	authored.free()


func _test_top_down(usability: Object, root: Node3D) -> void:
	var framing := TopDown.plan(root, 2.0)
	var camera_transform: Transform3D = framing.camera_transform
	_expect(framing.size == Vector2i(80, 80) and
		(framing.rect as Rect2).is_equal_approx(Rect2(0, 0, 40, 40)) and
		TopDown.pixel_for(framing, Vector3(10.0, 0.0, 30.0)).is_equal_approx(Vector2(20, 60)) and
		(-camera_transform.basis.z).is_equal_approx(Vector3.DOWN) and
		camera_transform.basis.y.is_equal_approx(Vector3.FORWARD) and
		camera_transform.basis.x.is_equal_approx(Vector3.RIGHT),
		"top-down framing covers the terrain grid north-up, east right, 2 px per metre")
	var polygon := PackedVector2Array([Vector2(5, 5), Vector2(30, 5), Vector2(30, 35),
		Vector2(5, 20)])
	var clipped := TopDown.plan(root, 2.0, polygon)
	var mask := TopDown.ownership_mask(clipped, polygon)
	_expect((clipped.rect as Rect2).is_equal_approx(Rect2(5, 5, 25, 30)) and
		clipped.size == Vector2i(50, 60) and
		is_equal_approx(mask.get_pixelv(Vector2i(TopDown.pixel_for(clipped,
			Vector3(20, 0, 15)))).a, 1.0) and
		is_zero_approx(mask.get_pixelv(Vector2i(TopDown.pixel_for(clipped,
			Vector3(7, 0, 32)))).a),
		"ownership clipping frames the polygon and masks out land the territory does not own")
	var huge := TopDown.plan(root, 1000.0)
	_expect((huge.size as Vector2i).x <= TopDown.MAX_SIDE and
		absf(float(huge.pixels_per_metre) - float(TopDown.MAX_SIDE) / 40.0) < 0.001,
		"very high resolutions are clamped to %d px per side" % TopDown.MAX_SIDE)
	var result: Dictionary = await usability.call("capture_top_down",
		DIR + "/capture.png", 2.0, false)
	_expect(result.has("error") and not bool((usability.call("time_preview_state") as Dictionary).active) and
		root.get_children(true).all(func(node: Node) -> bool:
			return not String(node.name).begins_with("__MapAuthoringTopDownCapture")),
		"a capture without a renderer fails cleanly and leaves no lights or viewport behind")


func _open_fixture() -> Node3D:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(DIR))
	var file := FileAccess.open(ProjectSettings.globalize_path(HEIGHT_PATH), FileAccess.WRITE)
	file.big_endian = false
	for z in GRID.y:
		for x in GRID.x:
			file.store_float(5.0 + 2.0 * sin(float(x) * 0.35) + 1.5 * cos(float(z) * 0.27) +
				0.002 * float(x * z))
	file.close()
	var fixture: Variant = REGION.new()
	fixture.name = "UsabilityFixture"
	fixture.region_id = "usability_fixture"
	fixture.metres_per_tile = 1.0
	fixture.server_origin = Vector2i(100, 200)
	fixture.server_cells = GRID
	var polygon_rows := [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]]
	fixture.ownership_polygon_sha256 = JSON.stringify(polygon_rows).sha256_text()
	fixture.authority_gameplay = false
	var terrain: Variant = TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = Vector2.ZERO
	terrain.grid_size = GRID
	terrain.cell_metres = 1.0
	terrain.base_heights_path = HEIGHT_PATH
	terrain.preview_enabled = true
	terrain.base_surface = MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.GRASS)
	fixture.add_child(terrain)
	terrain.owner = fixture
	for container in ["Roads", "Rivers", "Bridges", "AuthoredAssets", "Gameplay",
			"GeneratedPreview"]:
		var node := Node3D.new()
		node.name = container
		fixture.add_child(node)
		node.owner = fixture
	var harvestables := Node3D.new()
	harvestables.name = "Harvestables"
	fixture.get_node("Gameplay").add_child(harvestables)
	harvestables.owner = fixture
	var crystal: Node3D = MARKER.new()
	crystal.name = "crystal-01"
	crystal.set("record_id", "crystal-01")
	crystal.set("kind", "harvestable")
	crystal.set("label", "Crystal")
	crystal.set("extras", {"extent": [4, 4], "harvestHook": "harvest.test", "kind": "mineral",
		"propPosition": [1, 2, 3]})
	crystal.position = Vector3(6.0, 6.0, 34.0)
	harvestables.add_child(crystal)
	crystal.owner = fixture
	var lakes := Node3D.new()
	lakes.name = "WaterRegions"
	fixture.add_child(lakes)
	lakes.owner = fixture
	var lake: Node3D = WATER.new()
	lake.name = "test-lake"
	lake.set("water_id", "test-lake")
	lake.set("radii", Vector2(4.0, 4.0))
	lakes.add_child(lake)
	lake.owner = fixture
	var packed := PackedScene.new()
	var saved: bool = packed.pack(fixture) == OK and ResourceSaver.save(packed, SCENE_PATH) == OK
	fixture.free()
	_expect(saved, "disposable region fixture saves")
	_editor.call("open_scene_from_path", SCENE_PATH)
	await process_frame
	await process_frame
	var root := _editor.call("get_edited_scene_root") as Node3D
	_expect(root != null and root.get_script() == REGION and root.has_node("Terrain"),
		"editor opens the region fixture as the edited scene")
	return root if root != null and root.get_script() == REGION else null


func _test_probe(root: Node3D) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var mismatches := 0
	var max_error := 0.0
	var probe_usec := 0
	var reference_usec := 0
	for _index in 40:
		var origin := Vector3(rng.randf_range(-10.0, 50.0), rng.randf_range(15.0, 60.0),
			rng.randf_range(-10.0, 50.0))
		var target := Vector3(rng.randf_range(0.0, 40.0), 0.0, rng.randf_range(0.0, 40.0))
		var direction := (target - origin).normalized()
		var started := Time.get_ticks_usec()
		var fast: Variant = Probe.ray_hit(root, origin, direction, 2048.0)
		probe_usec += Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		var exact: Variant = root.call("authoring_ground_intersection", origin, direction, 2048.0)
		reference_usec += Time.get_ticks_usec() - started
		if (fast == null) != (exact == null):
			mismatches += 1
		elif fast != null:
			max_error = maxf(max_error, (fast as Vector3).distance_to(exact as Vector3))
	_expect(mismatches == 0 and max_error < 0.001,
		"fast probe agrees with the region's exact triangle test (max error %.6f m)" % max_error)
	print("  probe %d µs vs whole-grid test %d µs for 40 oblique rays" % [probe_usec,
		reference_usec])
	_expect(probe_usec < reference_usec,
		"fast probe walks only the cells a ray crosses (%d µs vs %d µs)" % [probe_usec,
			reference_usec])
	var height_error := 0.0
	for _index in 20:
		var point := Vector3(rng.randf_range(0.5, 39.5), 0.0, rng.randf_range(0.5, 39.5))
		var vertical: Variant = root.call("authoring_ground_intersection",
			point + Vector3.UP * 100.0, Vector3.DOWN, 200.0)
		height_error = maxf(height_error, absf(Probe.height_at(root, point) -
			(vertical as Vector3).y))
	_expect(height_error < 0.0001 and is_nan(Probe.height_at(root, Vector3(-5, 0, -5))) and
		Probe.ray_hit(root, Vector3(20, 30, 20), Vector3.UP) == null,
		"height lookups match vertical rays and stay empty off the terrain")


func _test_describe_point(root: Node3D) -> void:
	var info := Probe.describe_point(root, root.global_transform * Vector3(3.4, 7.0, 5.6))
	_expect(bool(info.has_tile) and info.tile == Vector2i(103, 194) and
		(info.local as Vector3).is_equal_approx(Vector3(3.4, 7.0, 5.6)),
		"cursor readout uses the snapshot tile conversion (floor(x+ox), floor(oy-z))")


func _test_adjusted_transform(root: Node3D, entry: Dictionary) -> void:
	var created := Placement.instantiate_entry(entry)
	var wrapper := root.call("prepare_palette_asset", entry, created.node) as Node3D
	var ground := Probe.ray_hit(root, Vector3(20.0, 60.0, 20.0), Vector3.DOWN) as Vector3
	var legacy := Placement.ground_transform(wrapper, entry, ground)
	_expect(Placement.adjusted_ground_transform(wrapper, entry, ground).is_equal_approx(legacy),
		"adjusted placement with no adjustments equals the existing ground transform")
	var turned := Placement.adjusted_ground_transform(wrapper, entry, ground, 90.0)
	var lifted := Placement.adjusted_ground_transform(wrapper, entry, ground, 0.0, 0.5)
	var grown := Placement.adjusted_ground_transform(wrapper, entry, ground, 0.0, 0.0, 1.5)
	var normal := Vector3(0.3, 1.0, -0.2).normalized()
	var tilted := Placement.adjusted_ground_transform(wrapper, entry, ground, 0.0, 0.0, 1.0,
		normal)
	_expect(turned.basis.x.is_equal_approx(Basis(Vector3.UP, PI * 0.5) * legacy.basis.x) and
		absf(_bottom(wrapper, turned) - ground.y) < 0.001,
		"a turn rotates about world up and keeps the visible base on the ground")
	_expect(absf(_bottom(wrapper, lifted) - ground.y - 0.5) < 0.001,
		"lift raises the grounded asset by exactly that many metres")
	_expect(absf(_height(wrapper, grown) - 1.5 * _height(wrapper, legacy)) < 0.001 and
		absf(_bottom(wrapper, grown) - ground.y) < 0.001,
		"size scales on top of the catalog height and stays grounded")
	_expect(tilted.basis.y.normalized().is_equal_approx(normal),
		"align to slope points the asset's up along the surface normal")
	wrapper.free()


func _test_ghost_placement(palette: Object, root: Node3D, entry: Dictionary,
		camera: Camera3D) -> Array[Node3D]:
	var placed: Array[Node3D] = []
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	palette.call("_arm_placement", entry)
	var motion := InputEventMouseMotion.new()
	motion.position = centre
	var motion_result: int = palette.call("_forward_3d_gui_input", camera, motion)
	palette.call("_refresh_hover")
	var ghost := (palette.call("placement_state") as Dictionary).ghost as Node3D
	# Compatibility ignores GeometryInstance3D.transparency, so the ghost must carry
	# its own alpha-blended surface materials.
	var see_through := ghost != null and ghost.find_children("*", "MeshInstance3D", true,
		false).any(func(node: Node) -> bool:
			var material := (node as MeshInstance3D).get_surface_override_material(0)
			return material is BaseMaterial3D and \
				(material as BaseMaterial3D).transparency != BaseMaterial3D.TRANSPARENCY_DISABLED and \
				(material as BaseMaterial3D).albedo_color.a < 1.0)
	_expect(motion_result == EditorPlugin.AFTER_GUI_INPUT_PASS and ghost != null and
		ghost.get_parent() == root and ghost.owner == null and
		not root.get_children().has(ghost) and root.get_children(true).has(ghost) and see_through,
		"a see-through ghost follows the cursor as an internal, ownerless node")
	var results := [
		palette.call("_forward_3d_gui_input", camera, _key(KEY_Q)),
		palette.call("_forward_3d_gui_input", camera, _key(KEY_E, true)),
		palette.call("_forward_3d_gui_input", camera, _key(KEY_PAGEUP)),
		palette.call("_forward_3d_gui_input", camera, _key(KEY_PAGEDOWN, true)),
		palette.call("_forward_3d_gui_input", camera, _key(KEY_HOME)),
		palette.call("_forward_3d_gui_input", camera, _wheel(true)),
	]
	var state := palette.call("placement_state") as Dictionary
	_expect(results.all(func(value: int) -> bool: return value == EditorPlugin.AFTER_GUI_INPUT_STOP) and
		is_equal_approx(float(state.yaw), 29.0) and is_equal_approx(float(state.lift), 0.2) and
		is_equal_approx(float(state.size), 1.1),
		"Q/E and Shift+wheel turn, PgUp/PgDn raise, Home grows, Shift gives fine steps")
	var assets := root.get_node("AuthoredAssets")
	var before := assets.get_child_count()
	var ghost_transform := ghost.global_transform
	var click_result: int = palette.call("_forward_3d_gui_input", camera, _click(centre))
	state = palette.call("placement_state") as Dictionary
	var first := assets.get_child(assets.get_child_count() - 1) as Node3D \
		if assets.get_child_count() > before else null
	_expect(click_result == EditorPlugin.AFTER_GUI_INPUT_STOP and bool(state.armed) and
		first != null and first.global_transform.is_equal_approx(ghost_transform) and
		not String(first.get("asset_id")).is_empty(),
		"a click places exactly what the ghost showed and keep-placing stays armed")
	palette.call("_forward_3d_gui_input", camera, _key(KEY_BACKSPACE))
	state = palette.call("placement_state") as Dictionary
	var reset := is_zero_approx(float(state.yaw)) and is_zero_approx(float(state.lift)) and \
		is_equal_approx(float(state.size), 1.0)
	palette.call("_forward_3d_gui_input", camera, _key(KEY_G))
	var snapped_on := bool(Settings.value("placement/snap_to_grid"))
	# The headless editor viewport is tiny, so aim the camera rather than the cursor.
	_aim(camera, root, Vector2(12.3, 27.7))
	palette.call("_forward_3d_gui_input", camera, _click(centre))
	var second := assets.get_child(assets.get_child_count() - 1) as Node3D \
		if assets.get_child_count() > before + 1 else null
	var local := root.global_transform.affine_inverse() * second.global_position \
		if second != null else Vector3(0.5, 0, 0.5)
	palette.call("_forward_3d_gui_input", camera, _key(KEY_G))
	_expect(reset and snapped_on and not bool(Settings.value("placement/snap_to_grid")) and
		second != null and absf(local.x - roundf(local.x)) < 0.0001 and
		absf(local.z - roundf(local.z)) < 0.0001,
		"Backspace resets adjustments and G toggles snapping to the 1 m territory grid")
	var ids := {}
	for child in assets.get_children():
		ids[String(child.get("asset_id"))] = true
	_expect(ids.size() == assets.get_child_count(),
		"consecutive placements receive distinct asset ids")
	palette.call("_forward_3d_gui_input", camera, _click(centre, MOUSE_BUTTON_RIGHT))
	state = palette.call("placement_state") as Dictionary
	_expect(not bool(state.armed) and state.ghost == null and
		root.get_children(true).all(func(node: Node) -> bool:
			return not String(node.name).begins_with("__MapAssetGhost")),
		"right-click stops placing and removes the ghost")
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	history.undo()
	var undone := assets.get_child_count() == before + 1
	history.redo()
	_expect(undone and assets.get_child_count() == before + 2,
		"each placement is its own undo step")
	if first != null:
		placed.append(first)
	if second != null:
		placed.append(second)
	return placed


func _test_cursor_readout_and_grid(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = camera.get_viewport().get_visible_rect().size * 0.5
	usability.call("_forward_3d_gui_input", camera, motion)
	usability.call("_refresh_hover")
	var state := usability.call("hover_state") as Dictionary
	var text := String(usability.call("readout_text"))
	var expected := Probe.describe_point(root, state.hit as Vector3) \
		if state.hit is Vector3 else {}
	var tile_text := "tile %d, %d" % [expected.tile.x, expected.tile.y] \
		if not expected.is_empty() else "?"
	_expect(tile_text in text and "height" in text and "X " in text,
		"cursor readout shows territory metres, server tile and height (%s)" % text)
	var grid := state.grid as MeshInstance3D
	var vertices := 0
	if grid != null and grid.mesh != null and grid.mesh.get_surface_count() > 0:
		vertices = (grid.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	_expect(grid != null and grid.visible and grid.owner == null and
		not root.get_children().has(grid) and vertices > 200,
		"the cursor grid drapes an internal, unsaved line mesh over the terrain (%d vertices)" %
			vertices)
	Settings.set_value("grid/cursor_grid", Settings.CursorGrid.OFF)
	usability.call("_refresh_hover")
	_expect(not grid.visible, "the cursor grid can be switched off")
	Settings.set_value("grid/cursor_grid", Settings.CursorGrid.ALWAYS)


func _test_selection_tools(usability: Object, root: Node3D, placed: Array[Node3D]) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	_expect(Tools.placements(root, [root.get_node("Terrain"), root.get_node("AuthoredAssets"),
		root]).is_empty() and Tools.placements(root, placed).size() == 2,
		"batch tools only accept placements, never terrain, containers or the root")
	# The first placement was lifted 0.2 m with PgUp; raise it further, then drop.
	var first := placed[0]
	first.global_position += Vector3.UP * 3.0
	var raised_transform := first.global_transform
	var ground := Probe.height_at(root, first.global_position)
	selection.clear()
	for node in placed:
		selection.add_node(node)
	var dropped: int = usability.call("run_tool", UsabilityPlugin.MenuId.DROP_TO_GROUND)
	var landed_transform := first.global_transform
	var landed := absf(_bottom(first, landed_transform) - ground) < 0.001 and \
		landed_transform.basis.is_equal_approx(raised_transform.basis)
	history.undo()
	var raised := first.global_transform.is_equal_approx(raised_transform)
	history.redo()
	_expect(dropped == 1 and landed and raised and
		first.global_transform.is_equal_approx(landed_transform),
		"Drop to ground re-seats a lifted asset on the terrain as one undo step")
	var before: Array[Transform3D] = []
	for node in placed:
		before.append(node.global_transform)
	usability.call("run_tool", UsabilityPlugin.MenuId.ROTATE_EACH)
	var rotated := true
	for index in placed.size():
		var node := placed[index]
		rotated = rotated and node.global_position.is_equal_approx(before[index].origin) and \
			node.global_transform.basis.x.is_equal_approx(
				Basis(Vector3.UP, PI * 0.5) * before[index].basis.x)
	_expect(rotated, "Rotate each turns every asset 90° about its own pivot")
	var bases: Array[float] = []
	for node in placed:
		bases.append(_bottom(node, node.global_transform))
	usability.call("run_tool", UsabilityPlugin.MenuId.RANDOM_SIZE)
	var kept := true
	for index in placed.size():
		kept = kept and absf(_bottom(placed[index], placed[index].global_transform) -
			bases[index]) < 0.001
	_expect(kept, "Random size keeps each asset's visible base where it was")
	selection.clear()


func _test_prefab(palette: Object, root: Node3D, placed: Array[Node3D], camera: Camera3D) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	var assets := root.get_node("AuthoredAssets")
	var mesh_path := _first_mesh_path(placed[0])
	var override: Resource = OVERRIDE.new()
	override.mesh_node_path = mesh_path
	override.surface = MapAuthoringSurface.new()
	var overrides: Array[Resource] = [override]
	placed[0].set("material_overrides", overrides)
	_expect((placed[0].get("material_overrides") as Array).size() == 1,
		"fixture asset carries a local material override before it is saved as a prefab")
	selection.clear()
	for node in placed:
		selection.add_node(node)
	var result := palette.call("save_selection_as_prefab", "Test Pair") as Dictionary
	var path := PREFAB_DIR + "/test_pair.tscn"
	_expect(String(result.get("path", "")) == path and FileAccess.file_exists(path) and
		int(result.get("members", 0)) == 2 and
		Prefabs.entries().any(func(entry: Dictionary) -> bool:
			return String(entry.id) == "prefab:test_pair"),
		"Save selection writes a prefab that the library lists")
	var prefab_entry := _entry(Prefabs.entries(), "prefab:test_pair")
	var old_ids := {}
	for child in assets.get_children():
		old_ids[String(child.get("asset_id"))] = true
	var before := assets.get_child_count()
	palette.call("_arm_placement", prefab_entry)
	var point := camera.get_viewport().get_visible_rect().size * 0.5
	_aim(camera, root, Vector2(28.0, 10.0))
	var motion := InputEventMouseMotion.new()
	motion.position = point
	palette.call("_forward_3d_gui_input", camera, motion)
	palette.call("_refresh_hover")
	var ghost := (palette.call("placement_state") as Dictionary).ghost as Node3D
	_expect(ghost != null and ghost.get_child_count() == 2 and ghost.owner == null,
		"a prefab ghost previews every member")
	palette.call("_forward_3d_gui_input", camera, _click(point))
	_aim(camera, root, Vector2(9.0, 12.0))
	palette.call("_forward_3d_gui_input", camera, _click(point))
	palette.call("_cancel_placement")
	var fresh: Array[Node] = []
	for index in range(before, assets.get_child_count()):
		fresh.append(assets.get_child(index))
	var fresh_ids := {}
	for node in fresh:
		fresh_ids[String(node.get("asset_id"))] = true
	var linked := fresh.all(func(node: Node) -> bool:
		var content: Node = node.call("content_root")
		return content != null and not content.scene_file_path.is_empty() and \
			node.owner == root and content.owner == root)
	_expect(fresh.size() == 4 and fresh_ids.size() == 4 and
		fresh_ids.keys().all(func(id: String) -> bool: return not old_ids.has(id)) and linked,
		"placing a prefab twice creates linked assets with fresh, unique ids")
	var surfaces := {}
	for node in fresh:
		for item: Resource in node.get("material_overrides"):
			surfaces[item.get_instance_id()] = true
			if item.get("surface") != null:
				surfaces[(item.get("surface") as Resource).get_instance_id()] = true
	var override_counts := fresh.map(func(node: Node) -> int:
		return (node.get("material_overrides") as Array).size())
	_expect(surfaces.size() == 4 and not surfaces.has(override.get_instance_id()),
		"every placed prefab copy owns an independent material override (%d ids, %s)" % [
			surfaces.size(), override_counts])
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	history.undo()
	var one_step := assets.get_child_count() == before + 2
	history.redo()
	_expect(one_step and assets.get_child_count() == before + 4,
		"each prefab placement is a single undo step")
	selection.clear()


func _test_save_excludes_helpers(palette: Object, usability: Object, root: Node3D,
		entry: Dictionary, camera: Camera3D) -> void:
	palette.call("_arm_placement", entry)
	var motion := InputEventMouseMotion.new()
	motion.position = camera.get_viewport().get_visible_rect().size * 0.5
	palette.call("_forward_3d_gui_input", camera, motion)
	palette.call("_refresh_hover")
	usability.call("_forward_3d_gui_input", camera, motion)
	usability.call("_refresh_hover")
	var packed := PackedScene.new()
	var saved: bool = packed.pack(root) == OK and ResourceSaver.save(packed, RELOAD_PATH) == OK
	var text := FileAccess.get_file_as_string(RELOAD_PATH)
	var reopened := (load(RELOAD_PATH) as PackedScene).instantiate()
	get_root().add_child(reopened)
	await process_frame
	var helpers := reopened.find_children("__Map*", "", true, false)
	_expect(saved and not "__MapAuthoringMarkerOverlay" in text and
		not "__MapAuthoringWalkability" in text and not "__MapAuthoringPathDraft" in text and
		'path_id = "road-01"' in text and 'record_id = "crystal-02"' in text,
		"new markers and roads are saved; marker pins, walkability tint and path drafts never are")
	_expect(saved and 'metadata/map_authoring_group = "group-01"' in text and
		not "__MapAuthoringCopyDrag" in text and not "__MapAuthoringPlaytest" in text and
		not "__MapAuthoringFocus" in text,
		"group tags are saved with their objects; copy ghosts, the walker and focus helpers never are")
	_expect(saved and not "__MapAssetGhost" in text and not "__MapAuthoringCursorGrid" in text and
		not "__MapAuthoringTimeOfDay" in text and not "DirectionalLight3D" in text and
		helpers.is_empty() and reopened.get_node("AuthoredAssets").get_child_count() ==
		root.get_node("AuthoredAssets").get_child_count(),
		"save/reopen keeps every placed asset and never the ghost or cursor grid")
	reopened.queue_free()
	await process_frame


func _test_marker_palette(palette: Object, usability: Object, root: Node3D,
		camera: Camera3D) -> void:
	var entries := Markers.entries(root)
	var template := {}
	for candidate in entries:
		if String(candidate.label) == "Harvestable: Crystal (mineral)":
			template = candidate
	var kinds := {}
	for candidate in entries:
		kinds[String(candidate.marker_kind)] = true
	_expect(kinds.size() == Markers.KINDS.size() and not kinds.has("runtime_point") and
		not template.is_empty() and String(template.marker_label) == "Crystal" and
		(template.marker_extras as Dictionary).has("harvestHook") and
		not (template.marker_extras as Dictionary).has("propPosition"),
		"marker palette offers every exported kind plus templates from the territory's own markers")
	var dock: Object = palette.get("_dock")
	dock.call("select_category", Markers.CATEGORY)
	_expect(String(template.id) in (dock.call("visible_entry_ids") as PackedStringArray),
		"the Map Assets dock lists gameplay markers under their own category")
	palette.call("_arm_placement", template)
	_aim(camera, root, Vector2(16.0, 26.0))
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var motion := InputEventMouseMotion.new()
	motion.position = centre
	palette.call("_forward_3d_gui_input", camera, motion)
	palette.call("_refresh_hover")
	var ghost := (palette.call("placement_state") as Dictionary).ghost as Node3D
	_expect(ghost != null and ghost.owner == null and
		not ghost.find_children("*", "MeshInstance3D", true, false).is_empty(),
		"a marker ghost is a see-through pin in the kind's colour")
	palette.call("_forward_3d_gui_input", camera, _click(centre))
	var created := root.get_node_or_null("Gameplay/Harvestables/crystal-02") as Node3D
	var ground := Probe.height_at(root, created.global_position) if created != null else NAN
	_expect(created != null and created.get_script() == MARKER and
		String(created.get("record_id")) == "crystal-02" and String(created.get("label")) == "Crystal" and
		(created.get("extras") as Dictionary).get("harvestHook") == "harvest.test" and
		not (created.get("extras") as Dictionary).has("propPosition") and
		absf(created.global_position.y - ground) < 0.001 and created.owner == root,
		"a click places a harvestable with a fresh id, copied conventions and no copied position")
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	history.undo()
	var removed := root.get_node_or_null("Gameplay/Harvestables/crystal-02") == null
	history.redo()
	_expect(removed and root.get_node_or_null("Gameplay/Harvestables/crystal-02") != null,
		"each marker placement is one undo step")
	var spawn := {}
	for candidate in entries:
		if String(candidate.marker_kind) == "spawn":
			spawn = candidate
	palette.call("_arm_placement", spawn)
	palette.call("_forward_3d_gui_input", camera, _key(KEY_Q))
	palette.call("_forward_3d_gui_input", camera, _key(KEY_Q))
	_aim(camera, root, Vector2(24.0, 30.0))
	palette.call("_forward_3d_gui_input", camera, _click(centre))
	palette.call("_cancel_placement")
	var spawns := root.get_node_or_null("Gameplay/Spawns")
	var spawn_marker := spawns.get_child(0) as Node3D if spawns != null and \
		spawns.get_child_count() > 0 else null
	_expect(spawn_marker != null and String(spawn_marker.get("kind")) == "spawn" and
		(spawn_marker.get("facing") as Vector3).is_equal_approx(
			Basis(Vector3.UP, deg_to_rad(30.0)) * Vector3.FORWARD),
		"a spawn creates its container and Q/E turn its facing (30° here)")
	usability.call("poll_overlays")
	var overlay := usability.call("marker_overlay_state") as Dictionary
	var pins := overlay.node as Node3D
	var mesh := (pins.get_node("Pins") as MeshInstance3D).mesh if pins != null else null
	_expect(pins != null and pins.owner == null and not root.get_children().has(pins) and
		int(overlay.labels) == Markers.markers(root).size() and mesh != null and
		mesh.get_surface_count() > 0,
		"every marker gets a coloured pin and a name label in an internal overlay")
	Settings.set_value("markers/show", false)
	usability.call("poll_overlays")
	_expect((usability.call("marker_overlay_state") as Dictionary).node == null,
		"marker pins can be switched off")
	Settings.set_value("markers/show", true)
	usability.call("poll_overlays")


func _test_walkability(usability: Object, root: Node3D) -> void:
	var shown: bool = usability.call("set_walkability_mode", Walkability.Mode.PUBLISHED)
	var state := usability.call("walkability_state") as Dictionary
	_expect(not shown and int(state.mode) == Walkability.Mode.OFF and
		"published" in String(state.message).to_lower(),
		"a territory without a published grid says so instead of tinting nothing")
	# The fast path (terrain cells twice the tile size, as in production's 2 m / 1 m)
	# must equal the pipeline rule tile by tile; here 1 m cells over 0.5 m tiles.
	var terrain := root.get_node("Terrain")
	var heights: PackedFloat32Array = terrain.call("effective_heights")
	var grid: Vector2i = terrain.get("grid_size")
	var width := (grid.x - 1) * 2
	var rows := (grid.y - 1) * 2
	var classes := PackedByteArray()
	classes.resize(width * rows)
	classes.fill(Walkability.Tile.WALKABLE)
	var data := {"heights": heights, "grid": grid, "cell": 1.0, "tile": 0.5,
		"width": width, "rows": rows, "classes": classes}
	Walkability._grade_pass(data)
	var mismatches := 0
	var steep_tiles := 0
	for row in rows:
		for column in width:
			var worst := 0.0
			for half: Vector2 in [Vector2(0.25, 0.25), Vector2(0.75, 0.25), Vector2(0.25, 0.75),
					Vector2(0.75, 0.75)]:
				var fx := (float(column) + half.x) / 2.0
				var fz := (float(row) + half.y) / 2.0
				var ix := mini(floori(fx), grid.x - 2)
				var iz := mini(floori(fz), grid.y - 2)
				var u := fx - float(ix)
				var v := fz - float(iz)
				var a := heights[iz * grid.x + ix]
				var b := heights[iz * grid.x + ix + 1]
				var c := heights[(iz + 1) * grid.x + ix]
				var d := heights[(iz + 1) * grid.x + ix + 1]
				var dx := b - a if u + v <= 1.0 else d - c
				var dz := c - a if u + v <= 1.0 else d - b
				worst = maxf(worst, sqrt(dx * dx + dz * dz))
			var expected := worst > Walkability.MAX_GRADE
			steep_tiles += 1 if expected else 0
			if expected != ((data.classes as PackedByteArray)[row * width + column] ==
					Walkability.Tile.STEEP):
				mismatches += 1
	_expect(mismatches == 0 and steep_tiles > 0,
		"the fast grade pass marks exactly the tiles whose half-cells exceed grade 0.65 (%d steep)" %
			steep_tiles)
	# Live mode on the fixture itself (1 m cells take the general path).
	var lake := root.get_node("WaterRegions/test-lake") as Node3D
	var lake_ground := Probe.height_at(root, Vector3(30.0, 0.0, 30.0))
	lake.global_position = Vector3(30.0, lake_ground + 1.2, 30.0)
	var asset := root.get_node("AuthoredAssets").get_child(0) as Node3D
	asset.set("collision_role", "solid")
	shown = usability.call("set_walkability_mode", Walkability.Mode.LIVE)
	usability.call("rebuild_walkability")
	state = usability.call("walkability_state") as Dictionary
	var overlay := state.node as MeshInstance3D
	var walk := Walkability.new()
	walk.set_mode(root, Walkability.Mode.LIVE)
	var lake_tile := walk.live_tile(Vector3(30.5, 0.0, 30.5))
	var dry_tile := walk.live_tile(Vector3(30.5, 0.0, 20.5))
	var asset_tile := walk.live_tile(asset.global_position)
	var steep_sample := -1
	for row in range(0, 40, 3):
		for column in range(0, 40, 3):
			var point := Vector3(float(column) + 0.5, 0.0, float(row) + 0.5)
			var tile := walk.live_tile(point)
			if tile == Walkability.Tile.STEEP:
				steep_sample = int(walk.grade_at(point) > Walkability.MAX_GRADE)
	var description := String(usability.call("walkability_describe", asset.global_position))
	_expect(shown and overlay != null and overlay.owner == null and overlay.visible and
		overlay.mesh == (terrain.get_node("__TerrainPreview") as MeshInstance3D).mesh and
		lake_tile == Walkability.Tile.WATER and dry_tile != Walkability.Tile.WATER and
		asset_tile == Walkability.Tile.BLOCKED and steep_sample == 1 and
		String(asset.name) in description,
		"live walkability marks steep ground, deep water and solid assets (%s)" % description)
	walk.release()
	asset.set("collision_role", "none")
	shown = usability.call("set_walkability_mode", Walkability.Mode.CHANGES)
	_expect(not shown, "changes since publish needs a published grid to compare with")
	# A real published grid: Sunmane's collision.bin, as the server walks it.
	var region := String(root.get("region_id"))
	root.set("region_id", "sunmane_steppe")
	var published := Walkability.published_grid(root)
	root.set("region_id", region)
	var fraction := 0.0
	if not published.has("error"):
		var bytes: PackedByteArray = published.bytes
		fraction = float(bytes.size() - bytes.count(0)) / float(bytes.size())
	_expect(not published.has("error") and int(published.width) == 1584 and
		int(published.rows) == 1584 and is_equal_approx(float(published.cell), 0.5) and
		absf(fraction - float(published.walkable_fraction)) < 0.000001,
		"the published grid loads Sunmane's EWCG exactly (%.4f walkable, as its manifest records)" %
			fraction)
	usability.call("set_walkability_mode", Walkability.Mode.OFF)
	_expect((usability.call("walkability_state") as Dictionary).node == null,
		"switching the overlay off removes its tint")


## The bake's own collision fixtures (_continent/tests/test_collision_export.py),
## rebuilt as editor assets on flat ground: the live port must block and carry
## the same half-cells. Coordinates are the fixtures' territory-local ones.
func _test_structure_rules() -> void:
	var fixture := Node3D.new()
	fixture.name = "StructureFixture"
	get_root().add_child(fixture)
	var assets := Node3D.new()
	assets.name = "AuthoredAssets"
	fixture.add_child(assets)
	var heights := PackedFloat32Array()
	heights.resize(49)
	heights.fill(0.0)
	var ground := Structures.ground_frame({"heights": heights, "grid": Vector2i(7, 7),
		"cell": 2.0, "terrain_x0": -6.0, "terrain_z0": -6.0, "x0": -6.0, "z0": -6.0,
		"tile": 1.0, "width": 12, "rows": 12})
	var door := _half_cell(-0.25, 0.25)
	# An arch: posts block, the doorway under a roof lintel stays open.
	_fixture_asset(assets, "GateArch", "solid", [_fixture_group("GateArch", [
		_fixture_mesh("LeftPost", _box(-2.5, 0, -1, -1.5, 4, 1)),
		_fixture_mesh("RightPost", _box(1.5, 0, -1, 2.5, 4, 1)),
		_fixture_mesh("RoofLintel", _box(-2.5, 3, -1, 2.5, 4, 1))])])
	var arch := _structure_result(fixture, ground)
	_fixture_asset(assets, "LowLintel", "solid", [_fixture_mesh("LowLintel",
		_box(-2.5, 1.8, -1, 2.5, 2.5, 1))])
	var low := _structure_result(fixture, ground)
	_expect(not arch.blocked.has(door) and arch.blocked.has(_half_cell(-2.25, 0.25)) and
		low.blocked.has(door),
		"an arch blocks at its posts but not under a roof above head height; a low lintel blocks")
	# A closed solid blocks inside itself; the same shape left open does not.
	var rock := _box(-2, -1, -2, 2, 8, 2)
	_fixture_asset(assets, "SolidRock", "solid", [_fixture_mesh("SolidRock", rock)])
	var closed := _structure_result(fixture, ground)
	var open_rock: Array[Vector3] = []
	open_rock.append_array(rock.slice(0, 6))
	open_rock.append_array(rock.slice(12))
	_fixture_asset(assets, "OpenRock", "solid", [_fixture_mesh("OpenRock", open_rock)])
	var open := _structure_result(fixture, ground)
	_expect(closed.blocked.has(door) and not open.blocked.has(door) and
		open.blocked.has(_half_cell(-1.75, 0.25)),
		"a tall closed solid blocks its interior; an open one only its walls")
	var wall: Array[Vector3] = [Vector3(0, 0, -2), Vector3(0, 3, -2), Vector3(0, 3, 2),
		Vector3(0, 0, -2), Vector3(0, 3, 2), Vector3(0, 0, 2)]
	_fixture_asset(assets, "ThinWall", "solid", [_fixture_mesh("ThinWall", wall)])
	var thin := _structure_result(fixture, ground)
	_expect(thin.blocked.has(door) and not thin.blocked.has(_half_cell(-1.25, 0.25)),
		"a thin edge-on wall blocks the cells its plane touches and no others")
	# Decks come from Walk_ names, whatever the role, and never from a ceiling.
	_fixture_asset(assets, "Bridge01", "walk_surface", [_fixture_group("Bridge01", [
		_fixture_mesh("Walk_Bridge", _quad(-2, -2, 2, 2, 1.5))])])
	var bridge := _structure_result(fixture, ground)
	_fixture_asset(assets, "Bridge02", "walk_surface", [_fixture_group("Bridge02", [
		_fixture_mesh("Walk_Ceiling", _quad(-2, -2, 2, 2, 1.5))])])
	var ceiling := _structure_result(fixture, ground)
	_fixture_asset(assets, "Dock01", "walk_surface", [_fixture_group("Dock01", [
		_fixture_mesh("Planks", _quad(-2, -2, 2, 2, 0.5))])])
	var unnamed := _structure_result(fixture, ground)
	_fixture_asset(assets, "Walk_Dock", "none", [_fixture_mesh("Planks", _quad(-2, -2, 2, 2, 0.5))])
	var named := _structure_result(fixture, ground)
	_expect(is_equal_approx(float(bridge.decks.get(door, -1.0)), 1.5) and
		not bridge.decks.has(_half_cell(-3.25, 0.25)) and ceiling.decks.is_empty() and
		unnamed.decks.is_empty() and is_equal_approx(float(named.decks.get(door, -1.0)), 0.5),
		"only a Walk_ ancestor makes a deck (the placement's node name counts), never a ceiling")
	# The exporter keeps only an asset's first scene root under its solid node
	# name; a Walk_ roof inside a solid is a ceiling, so it blocks and carries nothing.
	_fixture_asset(assets, "Hut", "solid", [_fixture_mesh("Body", _box(-2, 0, -2, -1, 3, 2)),
		_fixture_mesh("Porch", _box(1, 0, -2, 2, 3, 2))])
	var hut := _structure_result(fixture, ground)
	_fixture_asset(assets, "Tower", "solid", [_fixture_group("Tower", [
		_fixture_mesh("Walk_Roof", _quad(-2, -2, 2, 2, 1.0))])])
	var tower := _structure_result(fixture, ground)
	_expect(hut.blocked.has(_half_cell(-1.25, 0.25)) and not hut.blocked.has(_half_cell(1.25, 0.25)) and
		tower.blocked.has(door) and tower.decks.is_empty(),
		"companion scene roots are not solid, and a Walk_ roof inside a solid blocks")
	fixture.free()


func _structure_result(fixture: Node3D, ground: Dictionary) -> Dictionary:
	var shapes := Structures.gather(fixture)
	var blocked := {}
	for solid: Dictionary in shapes.solids:
		for index in Structures.blocked_cells(solid.parts, ground):
			blocked[index] = true
	var decks: Dictionary = Structures.deck_cells(ground, shapes.decks).cells
	for asset in fixture.get_node("AuthoredAssets").get_children():
		asset.free()
	return {"blocked": blocked, "decks": decks}


func _half_cell(x: float, z: float) -> int:
	return floori((z + 6.0) / 0.5) * 24 + floori((x + 6.0) / 0.5)


func _fixture_asset(parent: Node3D, node_name: String, role: String, roots: Array) -> void:
	var asset: Node3D = ASSET.new()
	asset.name = node_name
	asset.set("node_name", node_name)
	asset.set("collision_role", role)
	var content := Node3D.new()
	content.name = "fixture-scene"
	asset.add_child(content)
	for scene_root: Node in roots:
		content.add_child(scene_root)
	parent.add_child(asset)


func _fixture_group(label: String, children: Array) -> Node3D:
	var group := Node3D.new()
	group.name = label
	for child: Node in children:
		group.add_child(child)
	return group


## A mesh from triangles in glTF (counter-clockwise) order, stored clockwise as
## Godot's glTF importer stores them.
func _fixture_mesh(label: String, triangles: Array[Vector3]) -> MeshInstance3D:
	var vertices := PackedVector3Array()
	for index in range(0, triangles.size(), 3):
		vertices.append_array([triangles[index], triangles[index + 2], triangles[index + 1]])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var node := MeshInstance3D.new()
	node.name = label
	node.mesh = mesh
	return node


func _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> Array[Vector3]:
	var v := [Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x0, y0, z1),
		Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x0, y1, z1)]
	var result: Array[Vector3] = []
	for face: Array in [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 3, 7], [0, 7, 4],
			[1, 5, 6], [1, 6, 2], [0, 4, 5], [0, 5, 1], [3, 2, 6], [3, 6, 7]]:
		for corner: int in face:
			result.append(v[corner])
	return result


func _quad(x0: float, z0: float, x1: float, z1: float, y: float) -> Array[Vector3]:
	var result: Array[Vector3] = [Vector3(x0, y, z0), Vector3(x1, y, z1), Vector3(x1, y, z0),
		Vector3(x0, y, z0), Vector3(x0, y, z1), Vector3(x1, y, z1)]
	return result


## Opening LIVE shows box estimates at once and swaps in the exact result when
## the background check finishes, with a status notice; nothing is left running.
func _test_structure_background(root: Node3D) -> void:
	var asset := root.get_node("AuthoredAssets").get_child(0) as Node3D
	asset.set("collision_role", "solid")
	var walk := Walkability.new()
	walk.set_mode(root, Walkability.Mode.LIVE)
	var pending_at_start := walk.structures_pending()
	var legend_text := str(walk.legend())
	var notice := ""
	for _attempt in 300:
		walk.poll(false)
		notice += walk.take_notice()
		if walk.structures_pending() == 0:
			break
		await process_frame
	var live := walk.live_data()
	_expect(pending_at_start > 0 and "box estimates" in legend_text and
		walk.structures_pending() == 0 and "exactly" in notice and
		(live.pending as Array).is_empty() and int(live.solids) == pending_at_start,
		"live structures start as box estimates and turn exact in the background (%s)" % notice)
	walk.release()
	asset.set("collision_role", "none")


## The continent plan's water: features near the territory in its frame, the
## claimed ones marked, plan-only water in the live walkability, and the
## read-only display.
func _test_plan_water(usability: Object, root: Node3D) -> void:
	var plan := {"rivers": [
		{"id": "test_river", "name": "Test River", "width": 3.0,
			"points": [[5.0, 20.0, 100.0], [35.0, 20.0, 100.0]]},
		{"id": "far_river", "name": "Far River", "width": 3.0,
			"points": [[900.0, 900.0, 1.0], [950.0, 900.0, 1.0]]}],
		"lakes": [{"name": "Mirror Lake", "center": [20.0, 32.0], "radii": [4.0, 3.0],
			"level": 100.0, "depth": 2.0}]}
	var saved_owned: PackedStringArray = root.get("owned_plan_feature_ids")
	var saved_translation: Vector3 = root.get("continent_translation")
	root.set("continent_translation", Vector3.ZERO)
	root.set("owned_plan_feature_ids", PackedStringArray(["mirror_lake"]))
	var found := PlanWater.features(root, plan)
	var river := {}
	var lake := {}
	for feature in found:
		if String(feature.kind) == "river":
			river = feature
		else:
			lake = feature
	_expect(found.size() == 2 and not bool(river.get("claimed", true)) and
		(river.get("points", PackedVector3Array()) as PackedVector3Array)[0].is_equal_approx(
			Vector3(5.0, 100.0, 20.0)) and String(lake.get("id", "")) == "mirror_lake" and
		bool(lake.get("claimed", false)),
		"plan water near the territory is found in its frame; an owned lake counts as claimed")
	var live := Walkability.compute_live(root)
	var before: PackedByteArray = (live.classes as PackedByteArray).duplicate()
	Walkability._water_pass(root, live, live.ground, plan)
	var after: PackedByteArray = live.classes
	var width := int(live.width)
	var at := func(classes: PackedByteArray, x: float, z: float) -> int:
		return classes[floori(z - float(live.z0)) * width + floori(x - float(live.x0))]
	_expect(at.call(after, 20.5, 20.5) == Walkability.Tile.WATER and
		at.call(after, 20.5, 26.5) == at.call(before, 20.5, 26.5) and
		at.call(after, 20.5, 32.5) == at.call(before, 20.5, 32.5),
		"live walkability floods under plan-only rivers but not under water the territory claims")
	var plan_file := DIR + "/plan.json"
	var file := FileAccess.open(plan_file, FileAccess.WRITE)
	file.store_string(JSON.stringify(plan))
	file.close()
	var display: RefCounted = usability.call("plan_water")
	display.set("plan_path", plan_file)
	var shown: bool = usability.call("set_plan_water", true)
	var node: Node3D = display.call("node")
	var labels := node.find_children("*", "Label3D", true, false).size() if node != null else 0
	var message := String(display.get("last_message"))
	usability.call("set_plan_water", false)
	_expect(shown and node != null and node.owner == null and labels == 2 and
		"1 plan-only" in message and "1 claimed" in message and display.call("node") == null,
		"the plan's water is drawn read-only, plan-only and claimed told apart (%s)" % message)
	display.set("plan_path", PlanWater.PLAN_PATH)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(plan_file))
	root.set("owned_plan_feature_ids", saved_owned)
	root.set("continent_translation", saved_translation)


## The published minimap is cut to the live picture's frame from its manifest
## corners, and the dock can show both.
func _test_published_minimap(usability: Object) -> void:
	var source := Image.create_empty(372, 576, false, Image.FORMAT_RGBA8)
	source.fill(Color(0.0, 0.0, 1.0, 1.0))
	source.set_pixel(170, 336, Color(1.0, 0.0, 0.0, 1.0))
	source.set_pixel(175, 341, Color(0.0, 1.0, 0.0, 1.0))
	var picture: Image = UsabilityPlugin.resample_published(source, Vector2(-170.0, -336.0), 1.0,
		{"rect": Rect2(0.0, 0.0, 10.0, 10.0), "size": Vector2i(10, 10)})
	var edge: Image = UsabilityPlugin.resample_published(source, Vector2(-170.0, -336.0), 1.0,
		{"rect": Rect2(195.0, 0.0, 10.0, 10.0), "size": Vector2i(10, 10)})
	var westhaven: Node3D = REGION.new()
	westhaven.set("region_id", "westhaven")
	var published: Dictionary = UsabilityPlugin.published_minimap(westhaven,
		{"rect": Rect2(-50.0, -50.0, 100.0, 100.0), "size": Vector2i(50, 50)})
	westhaven.free()
	var dock: Object = usability.get("_minimap")
	dock.call("set_show", 2)
	var both := (dock.call("view") as Control).visible and (dock.call("published_view") as Control).visible
	dock.call("set_show", 0)
	_expect(picture.get_pixel(0, 0).is_equal_approx(Color(1.0, 0.0, 0.0, 1.0)) and
		picture.get_pixel(5, 5).is_equal_approx(Color(0.0, 1.0, 0.0, 1.0)) and
		is_equal_approx(edge.get_pixel(0, 0).b, 1.0) and is_zero_approx(edge.get_pixel(9, 0).a) and
		published.get("image") is Image and "published" in String(published.get("note", "")).to_lower() and
		both and not (dock.call("published_view") as Control).visible,
		"the last published minimap lines up with the live one (Westhaven's pixel edge 170, 336 is local 0, 0)")


## Scatter: seeded, spaced points and one undo step per stroke.
func _test_scatter(palette: Object, usability: Object, root: Node3D, camera: Camera3D,
		entry: Dictionary) -> void:
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var tool := _bind_fixture_sculpt(root)
	var polygon := PackedVector2Array([Vector2(0, 0), Vector2(40, 0), Vector2(40, 40), Vector2(0, 40)])
	var first_rng := RandomNumberGenerator.new()
	first_rng.seed = 7
	var second_rng := RandomNumberGenerator.new()
	second_rng.seed = 7
	var first := Scatter.stamp_points(first_rng, Vector2(20.0, 20.0), 5.0, 20.0, 1.5,
		PackedVector2Array(), polygon)
	var second := Scatter.stamp_points(second_rng, Vector2(20.0, 20.0), 5.0, 20.0, 1.5,
		PackedVector2Array(), polygon)
	var spaced := true
	for a in first.size():
		spaced = spaced and first[a].distance_to(Vector2(20.0, 20.0)) <= 5.0
		for b in range(a + 1, first.size()):
			spaced = spaced and first[a].distance_to(first[b]) >= 1.5
	_expect(first == second and first.size() >= 5 and spaced,
		"scatter points repeat for a seed and keep their spacing inside the brush (%d)" % first.size())
	var dock: Object = palette.get("_dock")
	dock.call("select_entry_by_id", String(entry.id))
	var assets := root.get_node("AuthoredAssets")
	var before := assets.get_child_count()
	var started: bool = usability.call("start_scatter", {"radius": 4.0, "density": 15.0,
		"spacing": 2.0, "random_turn": true, "size_variation": 0.1, "seed": 3}, entry)
	_stroke(usability, camera, root, [Vector2(12.0, 12.0), Vector2(16.0, 12.0), Vector2(20.5, 12.0)])
	var added: Array[Node3D] = []
	for index in range(before, assets.get_child_count()):
		added.append(assets.get_child(index) as Node3D)
	var others := {}
	for index in before:
		others[String(assets.get_child(index).get("asset_id"))] = true
	var fresh := {}
	for node in added:
		if not others.has(String(node.get("asset_id"))):
			fresh[String(node.get("asset_id"))] = true
	var apart := true
	for a in added.size():
		for b in range(a + 1, added.size()):
			apart = apart and Vector2(added[a].global_position.x - added[b].global_position.x,
				added[a].global_position.z - added[b].global_position.z).length() >= 1.99
	var owned := true
	for node in added:
		owned = owned and node.owner == root and String(node.get("catalog_asset_id")) == String(entry.id)
	history.undo()
	var undone := assets.get_child_count() == before
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	var scatter: RefCounted = usability.call("scatter_tool")
	_expect(started and added.size() >= 3 and fresh.size() == added.size() and
		apart and owned and undone and not bool(scatter.call("is_active")),
		"a scatter stroke places spaced copies of the chosen asset with fresh ids in one undo step (%d; %s; started %s, fresh %d, apart %s, owned %s, undone %s)" %
			[added.size(), String(scatter.get("last_message")), started, fresh.size(), apart, owned, undone])
	if tool != null:
		tool.call("unbind")


## Review notes: the sidecar beside the scene, its validation, and pins.
func _test_review_notes(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var notes: RefCounted = usability.call("review_notes")
	var path := ReviewNotes.path_for(root)
	var region := String(root.get("region_id"))
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	notes.call("open", root)
	var armed: bool = usability.call("start_review_note", "Check the ford")
	_aim(camera, root, Vector2(20.0, 20.0))
	var consumed: int = usability.call("_forward_3d_gui_input", camera, _click(centre))
	var loaded := ReviewNotes.read(path, region)
	var first: Dictionary = (loaded.notes as Array)[0] if not (loaded.notes as Array).is_empty() else {}
	_expect(armed and consumed == EditorPlugin.AFTER_GUI_INPUT_STOP and path.ends_with(".editor-notes.json") and
		(loaded.errors as PackedStringArray).is_empty() and (loaded.notes as Array).size() == 1 and
		String(first.get("id", "")) == "review-001" and String(first.get("status", "")) == "open" and
		String(first.get("text", "")) == "Check the ford" and
		Vector2((first.get("position", Vector3.INF) as Vector3).x - 20.0,
			(first.get("position", Vector3.INF) as Vector3).z - 20.0).length() < 0.1,
		"a click pins a review note into <region>.editor-notes.json beside the scene")
	notes.call("set_status", "review-001", "resolved")
	notes.call("set_text", "review-001", "Ford checked")
	notes.call("add", Vector3(5.0, 1.0, 5.0), "Second look")
	var reread := ReviewNotes.read(path, region)
	var pins: Node3D = notes.call("pins")
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	var notes_dock: Object = usability.call("review_notes_dock")
	usability.call("_sync_notes_dock")
	_expect((reread.notes as Array).size() == 2 and String((reread.notes as Array)[0].status) == "resolved" and
		String((reread.notes as Array)[0].text) == "Ford checked" and
		String((reread.notes as Array)[1].id) == "review-002" and document is Dictionary and
		String(document.schema) == "eloria-editor-notes-v1" and String(document.regionId) == region and
		pins != null and pins.owner == null and
		pins.find_children("*", "Label3D", true, false).size() == 2 and
		bool(notes_dock.call("select_id", "review-002")),
		"notes resolve, change text and number themselves; pins are internal and never saved (%s; pins %s; dock %s)" % [
			str(reread.notes), str(pins), str(notes_dock.call("selected_id"))])
	notes.call("remove", "review-002")
	var bad := {"schema": "eloria-editor-notes-v1", "regionId": "elsewhere", "notes": [
		{"id": "a", "position": [1, 2, 3], "text": "x", "status": "open"},
		{"id": "a", "position": [1, 2, 3], "text": "y", "status": "open"},
		{"id": "b", "position": [1, "x", 3], "text": "z", "status": "open"},
		{"id": "c", "position": [1, 2, 3], "text": "w", "status": "done"}]}
	var bad_file := FileAccess.open(path, FileAccess.WRITE)
	bad_file.store_string(JSON.stringify(bad))
	bad_file.close()
	var bad_bytes := FileAccess.get_file_as_bytes(path)
	notes.call("open", root)
	var problems := " ".join(notes.get("errors") as PackedStringArray)
	var refused: Dictionary = notes.call("add", Vector3.ZERO, "Should not be written")
	_expect(not bool(notes.call("can_write")) and (notes.get("notes") as Array).size() == 1 and
		"elsewhere" in problems and "twice" in problems and "three finite numbers" in problems and
		"open or resolved" in problems and refused.is_empty() and
		FileAccess.get_file_as_bytes(path) == bad_bytes,
		"a notes file with problems is read for what is valid and never rewritten (%s)" % problems)
	var packaging := FileAccess.get_file_as_string("res://tools/package_client.py")
	_expect(packaging.count("*.editor-notes.json") == 2,
		"both client export presets leave review notes out of the package")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	notes.call("open", root)


## Water is tested per half-metre cell against where the actor stands: a
## tile whose centre is dry but one half-cell is deep is water; a deck above
## the water keeps the cells it carries dry.
func _test_half_cell_water() -> void:
	var heights := PackedFloat32Array()
	heights.resize(36)
	heights.fill(0.0)
	var classes := PackedByteArray()
	classes.resize(100)
	classes.fill(Walkability.Tile.WALKABLE)
	var data := {"heights": heights, "grid": Vector2i(6, 6), "cell": 2.0, "tile": 1.0,
		"terrain_x0": 0.0, "terrain_z0": 0.0, "x0": 0.0, "z0": 0.0, "width": 10, "rows": 10,
		"classes": classes}
	var ground := Structures.ground_frame(data)
	var carried := {}
	for cell in [5 * 2 * 20 + 5 * 2, 5 * 2 * 20 + 5 * 2 + 1, (5 * 2 + 1) * 20 + 5 * 2,
			(5 * 2 + 1) * 20 + 5 * 2 + 1, 4 * 2 * 20 + 5 * 2, 4 * 2 * 20 + 5 * 2 + 1]:
		carried[cell] = 1.2
	ground.decks = carried
	var wet := PackedByteArray()
	wet.resize(100)
	Walkability._ellipse_cells(data, ground, {"centre": Vector3(5.0, 1.0, 5.0),
		"radii": Vector2(2.3, 2.3)}, wet)
	_expect(wet[5 * 10 + 7] == 1 and wet[5 * 10 + 5] == 0 and wet[4 * 10 + 5] == 1 and
		wet[5 * 10 + 8] == 0,
		"water is judged per half-cell against the deck or ground each stands on")


## The published package's composer-only decks and solids, read from a GLB,
## leaving out what the scene carries; and Sunmane's real package.
func _test_published_context() -> void:
	var scene := Node3D.new()
	scene.name = "PackageRoot"
	var parent := Node3D.new()
	parent.name = "Thresholds"
	parent.position = Vector3(10.0, 0.0, 0.0)
	scene.add_child(parent)
	parent.owner = scene
	for pair: Array in [["Walk_Threshold", parent], ["Gatehouse", scene], ["Authored_Carried", scene]]:
		var mesh_node := MeshInstance3D.new()
		mesh_node.name = pair[0]
		if pair[0] == "Walk_Threshold":
			var plane := PlaneMesh.new()
			plane.size = Vector2(4.0, 4.0)
			mesh_node.mesh = plane
		else:
			mesh_node.mesh = BoxMesh.new()
		(pair[1] as Node).add_child(mesh_node)
		mesh_node.owner = scene
	var path := ProjectSettings.globalize_path(DIR + "/published-context.glb")
	var state := GLTFState.new()
	var written := GLTFDocument.new().append_from_scene(scene, state) == OK and \
		GLTFDocument.new().write_to_filesystem(state, path) == OK
	scene.free()
	var read := Published.read_package(path, {"Gatehouse": true, "Authored_Carried": true},
		["Terrain_", "Walk_"], {"assets": {"Authored_Carried": true}, "bridges": PackedStringArray()})
	var deck_box := AABB()
	var decks: Array = read.get("decks", [])
	if not decks.is_empty():
		var corners: PackedVector3Array = decks[0].triangles
		deck_box = AABB(corners[0], Vector3.ZERO)
		for point in corners:
			deck_box = deck_box.expand(point)
	var heights := PackedFloat32Array()
	heights.resize(100)
	heights.fill(-1.0)
	var ground := Structures.ground_frame({"heights": heights, "grid": Vector2i(10, 10), "cell": 2.0,
		"terrain_x0": 0.0, "terrain_z0": -9.0, "x0": 0.0, "z0": -9.0, "tile": 1.0, "width": 18,
		"rows": 18})
	var carried: Dictionary = Structures.deck_cells(ground, decks).cells
	var sunmane: Node3D = REGION.new()
	sunmane.set("region_id", "sunmane_steppe")
	var real := Published.context_for(sunmane)
	sunmane.free()
	DirAccess.remove_absolute(path)
	_expect(written and decks.size() == 1 and String(decks[0].name) == "Walk_Threshold" and
		(read.get("solids", []) as Array).size() == 1 and
		String((read.solids as Array)[0].name) == "Gatehouse" and
		deck_box.position.is_equal_approx(Vector3(8.0, 0.0, -2.0)) and carried.size() == 64 and
		(real.get("decks", []) as Array).size() > 10,
		"published composer decks and solids are read in place, upward, without what the scene carries (%d Sunmane decks)" %
			(real.get("decks", []) as Array).size())


## The coordinate-locked concept master: placed by its contract in the
## territory frame, cut to the minimap frame, drawn on the terrain with both
## boundaries; and Sunmane's real package.
func _test_concept_master(usability: Object, root: Node3D) -> void:
	var package := ProjectSettings.globalize_path(DIR + "/concept")
	var region := String(root.get("region_id"))
	var slug := region.replace("_", "-")
	var folder := package.path_join("regions").path_join(slug)
	DirAccess.make_dir_recursive_absolute(folder)
	var translation: Vector3 = root.get("continent_translation")
	var master := Image.create_empty(40, 30, false, Image.FORMAT_RGBA8)
	master.fill(Color(0.0, 0.0, 1.0, 1.0))
	master.set_pixel(12, 7, Color(1.0, 0.0, 0.0, 1.0))
	master.save_png(folder.path_join("%s-master.png" % slug))
	var contract := {"id": region, "cropRectWorld": [translation.x - 2.0, translation.z - 3.0,
		translation.x + 38.0, translation.z + 27.0], "master": "%s-master.png" % slug,
		"developOwnershipPolygon": [[translation.x, translation.z], [translation.x + 40.0, translation.z],
			[translation.x + 40.0, translation.z + 40.0], [translation.x, translation.z + 40.0]],
		"ownershipPolygon": [[translation.x + 2.0, translation.z], [translation.x + 40.0, translation.z],
			[translation.x + 40.0, translation.z + 40.0], [translation.x + 2.0, translation.z + 40.0]]}
	var file := FileAccess.open(folder.path_join("contract.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(contract))
	file.close()
	var loaded := ConceptMaster.load_for(root, package)
	var picture: Dictionary = ConceptMaster.minimap_picture(root, {"rect": Rect2(10.0, 4.0, 4.0, 4.0),
		"size": Vector2i(4, 4)}, package)
	Settings.set_value("concept/masters_folder", package)
	var shown: bool = usability.call("set_concept_overlay", true)
	var overlay: Object = usability.call("concept_overlay")
	var node: MeshInstance3D = overlay.call("node")
	var message := String(overlay.get("last_message"))
	usability.call("set_concept_overlay", false)
	var sunmane: Node3D = REGION.new()
	sunmane.set("region_id", "sunmane_steppe")
	sunmane.set("continent_translation", Vector3(1200.0, 0.0, 720.0))
	Settings.set_value("concept/masters_folder", "")
	var real := ConceptMaster.load_for(sunmane)
	sunmane.free()
	_remove_tree_recursive(DIR + "/concept")
	_expect(not loaded.has("error") and (loaded.rect as Rect2).is_equal_approx(Rect2(-2.0, -3.0, 40.0, 30.0)) and
		(loaded.proposed as PackedVector2Array)[0].is_equal_approx(Vector2(2.0, 0.0)) and
		picture.get("image") is Image and
		(picture.image as Image).get_pixel(0, 0).is_equal_approx(Color(1.0, 0.0, 0.0, 1.0)) and
		shown and node != null and node.owner == null and "proposed" in message and
		overlay.call("node") == null and not real.has("error") and
		(real.rect as Rect2).is_equal_approx(Rect2(-286.0, -588.0, 626.0, 972.0)),
		"the concept master lines up by its contract, on the minimap and the terrain, with both boundaries (%s)" %
			[real.get("error", "Sunmane found")])


## Scatter avoids water, steep ground, roads and structures, still repeats for
## a seed, and erases only copies of its own asset in one undo step.
func _test_scatter_avoid_and_erase(usability: Object, root: Node3D, camera: Camera3D,
		entry: Dictionary) -> void:
	var flat := PackedFloat32Array()
	flat.resize(36)
	flat.fill(0.0)
	var slope := PackedFloat32Array()
	for row in 6:
		for column in 6:
			slope.append(float(column) * 2.0)
	var terrain := {"heights": flat, "grid": Vector2i(6, 6), "cell": 2.0, "terrain_x0": 0.0,
		"terrain_z0": 0.0}
	var steep := terrain.duplicate()
	steep.heights = slope
	var box := Walkability._footprint(Transform3D.IDENTITY, AABB(Vector3(6.0, 0.0, 6.0),
		Vector3(2.0, 3.0, 2.0)))
	var avoid := {"terrain": terrain, "roads": [[Vector2(0.0, 2.0), Vector2(10.0, 2.0), 1.5]],
		"structures": [box], "water": [{"kind": "ellipse", "centre": Vector3(2.0, 1.0, 8.0),
			"radii": Vector2(1.5, 1.5)}], "sea": null}
	var reasons := [Scatter.spot_problem(avoid, Vector2(5.0, 2.5)),
		Scatter.spot_problem(avoid, Vector2(7.0, 7.0)), Scatter.spot_problem(avoid, Vector2(2.0, 8.0)),
		Scatter.spot_problem({"terrain": steep, "max_grade": 0.65}, Vector2(5.0, 5.0)),
		Scatter.spot_problem(avoid, Vector2(8.5, 5.0))]
	var first_rng := RandomNumberGenerator.new()
	first_rng.seed = 5
	var second_rng := RandomNumberGenerator.new()
	second_rng.seed = 5
	var first := Scatter.stamp_points(first_rng, Vector2(5.0, 5.0), 5.0, 40.0, 0.8,
		PackedVector2Array(), PackedVector2Array(), avoid)
	var second := Scatter.stamp_points(second_rng, Vector2(5.0, 5.0), 5.0, 40.0, 0.8,
		PackedVector2Array(), PackedVector2Array(), avoid)
	var clean := first.size() > 0
	for point in first:
		clean = clean and Scatter.spot_problem(avoid, point).is_empty()
	_expect(reasons == ["road", "structure", "water", "steep", ""] and first == second and clean,
		"scatter avoids roads, structures, water and steep ground, and still repeats for a seed")
	# Paint, then erase over the same ground: only this asset's copies go.
	var tool := _bind_fixture_sculpt(root)
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var assets := root.get_node("AuthoredAssets")
	var before := assets.get_child_count()
	usability.call("start_scatter", {"radius": 4.0, "density": 15.0, "spacing": 2.0,
		"random_turn": true, "size_variation": 0.0, "seed": 9, "avoid_roads": false,
		"avoid_structures": false, "avoid_water": false, "avoid_steep": false}, entry)
	_stroke(usability, camera, root, [Vector2(12.0, 30.0), Vector2(16.0, 30.0), Vector2(20.5, 30.0)])
	var painted := assets.get_child_count() - before
	var other: Node3D = null
	for child in assets.get_children():
		if String(child.get("catalog_asset_id")) != String(entry.id):
			other = child as Node3D
			break
	var other_place := other.global_position if other != null else Vector3.ZERO
	if other != null:
		other.global_position = root.global_transform * Vector3(16.0, 0.0, 30.0)
	usability.call("_forward_3d_gui_input", camera, _key(KEY_X))
	var scatter: RefCounted = usability.call("scatter_tool")
	var erasing := bool(scatter.call("erasing"))
	# The same path gives the same stamp centres, so every painted copy is under it.
	_stroke(usability, camera, root, [Vector2(12.0, 30.0), Vector2(16.0, 30.0), Vector2(20.5, 30.0)])
	var erase_message := String(scatter.get("last_message"))
	# Every copy of the asset under the stroke is gone (placed earlier or just
	# now); anything else, like `other`, stays.
	var left_under := 0
	var centres := [Vector2(12.0, 30.0), Vector2(16.0, 30.0), Vector2(20.0, 30.0)]
	for child in assets.get_children():
		if String(child.get("catalog_asset_id")) != String(entry.id):
			continue
		var local: Vector3 = root.global_transform.affine_inverse() * (child as Node3D).global_position
		for centre: Vector2 in centres:
			if Vector2(local.x, local.z).distance_to(centre) < 3.9:
				left_under += 1
	var erased := left_under == 0 and "Erased" in erase_message and 		(other == null or other.get_parent() == assets)
	history.undo()
	var restored := assets.get_child_count() == before + painted
	history.undo()
	if other != null:
		other.global_position = other_place
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	if tool != null:
		tool.call("unbind")
	_expect(painted >= 3 and erasing and erased and restored and assets.get_child_count() == before,
		"erase removes every copy of the chosen asset under the stroke and nothing else, in one undo step (%d painted; %s)" % [
			painted, erase_message])


## The review notes filter: the list, the pins and the minimap follow it; the
## dock's buttons edit the chosen note.
func _test_notes_filter_and_dock(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var notes: RefCounted = usability.call("review_notes")
	var path := ReviewNotes.path_for(root)
	notes.call("open", root)
	notes.call("add", Vector3(10.0, 1.0, 10.0), "First")
	notes.call("add", Vector3(20.0, 1.0, 20.0), "Second")
	notes.call("set_status", "review-001", "resolved")
	usability.call("_sync_notes_dock")
	var dock: Object = usability.call("review_notes_dock")
	dock.call("set_filter", "open")
	var listed: PackedStringArray = dock.call("listed_ids")
	var pins: Node3D = notes.call("pins")
	var pin_labels := pins.find_children("*", "Label3D", true, false).size() if pins != null else -1
	var minimap: Object = usability.get("_minimap")
	var view: Object = minimap.call("view")
	var shown_notes := (view.get("state") as Dictionary).get("notes", []) as Array
	dock.call("set_filter", "all")
	dock.call("select_id", "review-002")
	(dock.call("text_field") as LineEdit).text = "Second, checked"
	((dock.get("_buttons") as Dictionary).save as Button).pressed.emit()
	((dock.get("_buttons") as Dictionary).resolve as Button).pressed.emit()
	var middle := ReviewNotes.read(path, String(root.get("region_id")))
	(dock.get("_confirm") as ConfirmationDialog).confirmed.emit()
	var left := ReviewNotes.read(path, String(root.get("region_id")))
	_expect(listed == PackedStringArray(["review-002"]) and pin_labels == 1 and
		((minimap.call("framing") as Dictionary).is_empty() or shown_notes.size() == 1),
		"the notes filter narrows the list, the pins and the minimap to open notes")
	var edited: Dictionary = (middle.notes as Array)[1] if (middle.notes as Array).size() == 2 else {}
	_expect(String(edited.get("text", "")) == "Second, checked" and
		String(edited.get("status", "")) == "resolved" and (left.notes as Array).size() == 1 and
		String((left.notes as Array)[0].id) == "review-001",
		"the dock's buttons save text, resolve and delete the chosen note")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	notes.call("open", root)
	usability.call("_sync_notes_dock")


func _test_path_drawing(palette: Object, usability: Object, root: Node3D, camera: Camera3D,
		entry: Dictionary) -> void:
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	palette.call("_arm_placement", entry)
	var started: bool = usability.call("start_path_drawing", "road")
	var tool: RefCounted = usability.call("path_draw_tool")
	_expect(started and bool(tool.call("is_active")) and
		not bool((palette.call("placement_state") as Dictionary).armed),
		"drawing a road stops asset placement")
	var clicked: Array[Vector3] = []
	for xz in [Vector2(10.0, 10.0), Vector2(20.0, 15.0), Vector2(33.0, 8.0)]:
		_aim(camera, root, xz)
		usability.call("_forward_3d_gui_input", camera, _click(centre))
		clicked.append(Probe.ray_hit(root, Vector3(xz.x, 60.0, xz.y), Vector3.DOWN) as Vector3)
	usability.call("_forward_3d_gui_input", camera, _key(KEY_BACKSPACE))
	clicked.pop_back()
	_aim(camera, root, Vector2(28.0, 25.0))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	clicked.append(Probe.ray_hit(root, Vector3(28.0, 60.0, 25.0), Vector3.DOWN) as Vector3)
	usability.call("_forward_3d_gui_input", camera, _key(KEY_BRACKETRIGHT))
	var draft := root.get_children(true).filter(func(node: Node) -> bool:
		return String(node.name).begins_with("__MapAuthoringPathDraft"))
	_expect(draft.size() == 1 and (draft[0] as Node).owner == null and
		(tool.get("points") as Array).size() == 3 and is_equal_approx(float(tool.get("width")), 5.0),
		"clicks add draped points, Backspace removes the last, ] widens the draft")
	var result: int = usability.call("_forward_3d_gui_input", camera, _key(KEY_ENTER))
	var road := root.get_node_or_null("Roads/road-01") as Path3D
	var matches := road != null and road.curve != null and road.curve.point_count == 3
	if matches:
		for index in 3:
			var world: Vector3 = road.global_transform * road.curve.get_point_position(index)
			matches = matches and world.distance_to(clicked[index]) < 0.05
	_expect(result == EditorPlugin.AFTER_GUI_INPUT_STOP and matches and road.owner == root and
		String(road.get("path_id")) == "road-01" and String(road.get("kind")) == "road" and
		String(road.get("routing_role")) == "required" and
		bool((road.get("properties") as Dictionary).get("terrainConform", false)) and
		is_equal_approx(float(road.get("default_width")), 5.0) and
		(road.call("snapshot_points") as Array).size() >= 3 and
		not bool(tool.call("is_active")) and road.get("surface") is MapAuthoringSurface and
		(road.get("surface") as MapAuthoringSurface).material_mode ==
			MapAuthoringSurface.MaterialMode.ROAD_SHADER,
		"Enter creates road-01 through the clicked ground points, terrain-shaped, with a road surface")
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	history.undo()
	var gone := root.get_node_or_null("Roads/road-01") == null
	history.redo()
	_expect(gone and root.get_node_or_null("Roads/road-01") != null,
		"a drawn road is one undo step")
	usability.call("start_path_drawing", "river")
	for xz in [Vector2(5.0, 30.0), Vector2(15.0, 36.0)]:
		_aim(camera, root, xz)
		usability.call("_forward_3d_gui_input", camera, _click(centre))
	usability.call("_forward_3d_gui_input", camera, _click(centre, MOUSE_BUTTON_RIGHT))
	var river := root.get_node_or_null("Rivers/river-01")
	_expect(river != null and String(river.get("kind")) == "river" and
		String(river.get("routing_role")) == "decorative",
		"right-click finishes a decorative river-01")
	var channel: Dictionary = river.get("properties") if river != null else {}
	var wider := PathDraw.river_properties(root, "river-02", float(river.get("default_width")) * 2.0) \
		if river != null else {}
	_expect(float(channel.get("channelDepth", 0.0)) > 0.0 and
		float(channel.get("bankHeight", 0.0)) > 0.0 and
		float(channel.get("valleyWidth", 0.0)) >= 30.0 and
		String(channel.get("name", "")) == "river-01" and
		not bool(channel.get("terrainConform", true)) and
		is_equal_approx(float(wider.get("valleyWidth", 0.0)),
			maxf(30.0, float(channel.get("valleyWidth", 0.0)) * 2.0)) and
		is_equal_approx(float(wider.get("channelDepth", 0.0)), float(channel.get("channelDepth", -1.0))),
		"a drawn river carries the channel depth, valley width and bank height the composer needs, " +
			"in proportion to a river the territory has")
	# A click beside an existing road point joins it exactly.
	usability.call("start_path_drawing", "road")
	var first: Vector3 = road.global_transform * road.curve.get_point_position(0)
	_aim(camera, root, Vector2(first.x + 1.2, first.z - 0.8))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	var joined := (tool.get("points") as Array)
	_expect(joined.size() == 1 and (joined[0] as Vector3).is_equal_approx(first),
		"a click within 2.5 m of a path point snaps onto it")
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	_expect(not bool(tool.call("is_active")) and root.get_node_or_null("Roads/road-02") == null and
		root.get_children(true).all(func(node: Node) -> bool:
			return not String(node.name).begins_with("__MapAuthoringPathDraft")),
		"Escape discards a draft without adding anything")


func _test_road_extension(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var tool: RefCounted = usability.call("path_draw_tool")
	var road := root.get_node("Roads/road-01") as Path3D
	var original: Array[Vector3] = []
	for index in road.curve.point_count:
		original.append(road.curve.get_point_position(index))
	var last: Vector3 = road.global_transform * original[original.size() - 1]
	usability.call("start_path_drawing", "road")
	_aim(camera, root, Vector2(last.x + 0.8, last.z + 0.6))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	var extending: Node3D = tool.call("extending")
	var added: Array[Vector3] = []
	for xz in [Vector2(34.0, 30.0), Vector2(36.0, 36.0)]:
		_aim(camera, root, xz)
		usability.call("_forward_3d_gui_input", camera, _click(centre))
		added.append(Probe.ray_hit(root, Vector3(xz.x, 60.0, xz.y), Vector3.DOWN) as Vector3)
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ENTER))
	var count := road.curve.point_count
	var at_end := count == original.size() + 2 and \
		(road.global_transform * road.curve.get_point_position(count - 1)).distance_to(added[1]) < 0.05 and \
		road.curve.get_point_position(original.size() - 1).is_equal_approx(original[original.size() - 1])
	_expect(extending == road and at_end and root.get_node_or_null("Roads/road-02") == null,
		"starting on a road's end extends that road instead of drawing a new one")
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	history.undo()
	var undone := road.curve.point_count == original.size()
	history.redo()
	_expect(undone and road.curve.point_count == original.size() + 2,
		"extending a road is one undo step")
	var first: Vector3 = road.global_transform * original[0]
	var anchored := PackedFloat32Array()
	anchored.resize(road.curve.point_count)
	anchored[0] = 6.0
	road.set("point_widths", anchored)
	usability.call("start_path_drawing", "road")
	_aim(camera, root, Vector2(first.x, first.z))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	_aim(camera, root, Vector2(4.0, 4.0))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	var front := Probe.ray_hit(root, Vector3(4.0, 60.0, 4.0), Vector3.DOWN) as Vector3
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ENTER))
	_expect(road.curve.point_count == original.size() + 3 and
		(road.global_transform * road.curve.get_point_position(0)).distance_to(front) < 0.05 and
		road.curve.get_point_position(1).is_equal_approx(original[0]),
		"starting on a road's first point extends it at the start")
	var widths_after: PackedFloat32Array = road.get("point_widths")
	history.undo()
	var widths_undone: PackedFloat32Array = road.get("point_widths")
	_expect(widths_after.size() == road.curve.point_count + 1 and is_equal_approx(widths_after[1], 6.0) and
		is_zero_approx(widths_after[0]) and widths_undone.size() == road.curve.point_count and
		is_equal_approx(widths_undone[0], 6.0),
		"extending a road at its start keeps its width anchors on their points, through undo (%s, %s)" % [
			widths_after, widths_undone])
	usability.call("start_path_drawing", "road")
	_aim(camera, root, Vector2(first.x, first.z))
	var ctrl_click := _click(centre)
	ctrl_click.ctrl_pressed = true
	usability.call("_forward_3d_gui_input", camera, ctrl_click)
	_expect(tool.call("extending") == null and (tool.get("points") as Array).size() == 1,
		"Ctrl+click on a road's end starts a separate road there")
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	var points_before := road.curve.point_count
	var tail: Vector3 = road.global_transform * road.curve.get_point_position(0)
	road.set("replaces_route_id", "route-17")
	usability.call("start_path_drawing", "road")
	_aim(camera, root, Vector2(tail.x, tail.z))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	var refused := tool.call("extending") == null and (tool.get("points") as Array).is_empty() and \
		"route-17" in String(tool.get("last_message"))
	road.set("replaces_route_id", "")
	var properties: Dictionary = (road.get("properties") as Dictionary).duplicate()
	road.set("properties", properties.merged({"joins": "river-01"}, true))
	var joined_reason := String(tool.call("ownership_reason", road, tail))
	road.set("properties", properties)
	var free_reason := String(tool.call("ownership_reason", road, tail))
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	_expect(refused and road.curve.point_count == points_before and "joins" in joined_reason and
		free_reason.is_empty(),
		"a road that replaces a composer route or joins shared water is not extended")


func _test_groups_and_copies(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var assets := root.get_node("AuthoredAssets")
	var a := assets.get_child(0) as Node3D
	var b := assets.get_child(1) as Node3D
	_select([a, b])
	var identity: String = usability.call("group_selection")
	var tagged := GroupTools.group_of(a) == identity and GroupTools.group_of(b) == identity
	history.undo()
	var untagged := GroupTools.group_of(a).is_empty() and GroupTools.group_of(b).is_empty()
	history.redo()
	_expect(identity == "group-01" and tagged and untagged and GroupTools.group_of(b) == identity,
		"Group tags the selection as group-01 in one undo step")
	_select([a])
	await _frames(2)
	var expanded := selection.get_selected_nodes()
	_expect(expanded.size() == 2 and b in expanded,
		"selecting one group member selects the whole group")
	var double := _click(centre)
	double.double_click = true
	usability.call("_forward_3d_gui_input", camera, double)
	_select([a])
	await _frames(2)
	_expect(selection.get_selected_nodes().size() == 1 and
		String(usability.call("open_group")) == identity,
		"a double-click opens the group so a single member can be picked")
	var crystal := root.get_node("Gameplay/Harvestables/crystal-01") as Node3D
	_select([crystal])
	await _frames(2)
	_expect(String(usability.call("open_group")).is_empty(),
		"selecting outside an open group closes it")
	_select([a])
	await _frames(2)
	usability.call("_forward_3d_gui_input", camera, _ctrl_key(KEY_G, true))
	var ungrouped := GroupTools.group_of(a).is_empty() and GroupTools.group_of(b).is_empty()
	_select([a, b])
	usability.call("_forward_3d_gui_input", camera, _ctrl_key(KEY_G, false))
	_expect(ungrouped and GroupTools.group_of(a) == "group-01" and
		GroupTools.group_of(b) == "group-01",
		"Ctrl+Shift+G ungroups and Ctrl+G groups in the 3D view")
	var ids := {}
	for child in assets.get_children():
		ids[String(child.get("asset_id"))] = true
	var before := assets.get_child_count()
	_select([a, b])
	var copies: Array = usability.call("duplicate_selection", Vector3(3.0, 0.0, 3.0))
	var fresh := copies.size() == 2
	for index in copies.size():
		var copy := copies[index] as Node3D
		var source: Node3D = [a, b][index]
		var clearance := source.global_position.y - Probe.height_at(root, source.global_position)
		var copied_clearance := copy.global_position.y - Probe.height_at(root, copy.global_position)
		var content: Node = copy.call("content_root")
		fresh = fresh and not ids.has(String(copy.get("asset_id"))) and copy.owner == root and \
			content != null and content.owner == root and not content.scene_file_path.is_empty() and \
			Vector2(copy.global_position.x - source.global_position.x - 3.0,
				copy.global_position.z - source.global_position.z - 3.0).length() < 0.001 and \
			absf(copied_clearance - clearance) < 0.001 and GroupTools.group_of(copy) == "group-02"
	_expect(fresh and assets.get_child_count() == before + 2 and
		String(copies[0].get("asset_id")) != String(copies[1].get("asset_id")) and
		selection.get_selected_nodes().size() == 2 and copies[0] in selection.get_selected_nodes(),
		"Duplicate makes linked copies with fresh ids, a new group and the same ground clearance")
	history.undo()
	var one_step := assets.get_child_count() == before
	history.redo()
	_expect(one_step and assets.get_child_count() == before + 2, "a duplicate is one undo step")
	_select([crystal])
	var marker_copies: Array = usability.call("duplicate_selection", Vector3(2.0, 0.0, 0.0))
	var records := {}
	for marker in Markers.markers(root):
		records[String(marker.get("record_id"))] = true
	_expect(marker_copies.size() == 1 and (marker_copies[0] as Node).get_parent() == crystal.get_parent() and
		String(marker_copies[0].get("record_id")) != "crystal-01" and
		records.size() == Markers.markers(root).size(),
		"a copied marker gets a fresh record id in its kind's container")
	# What a copy must not keep: server bindings, the default spawn, placement
	# extras, and a follow or link to an asset that was not copied with it.
	var saved := {}
	for field: String in ["runtime_bindings", "default_spawn", "extras", "follow_asset_id",
			"linked_node_name"]:
		saved[field] = crystal.get(field)
	var bound: Array[Dictionary] = [{"recordId": "crystal-01", "service": "harvest"}]
	crystal.set("runtime_bindings", bound)
	crystal.set("default_spawn", true)
	crystal.set("extras", {"propPosition": [1, 2, 3], "reachable": true, "tier": 2})
	crystal.set("follow_asset_id", String(a.get("asset_id")))
	crystal.set("linked_node_name", String(a.get("node_name")))
	_select([crystal])
	var alone := (usability.call("duplicate_selection", Vector3(0.0, 0.0, 2.0)) as Array)[0] as Node
	var reset := (alone.get("runtime_bindings") as Array).is_empty() and \
		not bool(alone.get("default_spawn")) and (alone.get("extras") as Dictionary) == {"tier": 2} and \
		String(alone.get("follow_asset_id")).is_empty() and String(alone.get("linked_node_name")).is_empty()
	_select([a, crystal])
	await _frames(2)
	var together: Array = usability.call("duplicate_selection", Vector3(0.0, 0.0, 4.0))
	var marker_copy: Node = null
	var followed: Node = null
	for copy: Node in together:
		if copy.get_script() == MARKER:
			marker_copy = copy
	for copy: Node in together:
		if marker_copy != null and copy.get_script() != MARKER and \
				String(copy.get("asset_id")) == String(marker_copy.get("follow_asset_id")):
			followed = copy
	history.undo()
	history.undo()
	for field: String in saved:
		crystal.set(field, saved[field])
	var portal: Node = MARKER.new()
	portal.set("kind", "portal")
	portal.set("destination_map", "amberwood")
	var note := GroupTools.copy_review_note([portal])
	portal.free()
	_expect(reset and followed != null and
		String(marker_copy.get("linked_node_name")) == String(followed.get("node_name")) and
		"still leads to the original's destination" in note,
		"copies drop bindings, the default spawn and placement extras, follow the copied asset, " +
			"and flag a copied portal's destination")
	# Alt+drag on a selected object copies it to where the drag ends.
	_select([a])
	await _frames(2)
	before = assets.get_child_count()
	_aim(camera, root, Vector2(a.global_position.x, a.global_position.z))
	var press := _click(centre)
	press.alt_pressed = true
	var consumed: int = usability.call("_forward_3d_gui_input", camera, press)
	var drag: RefCounted = usability.call("copy_drag_tool")
	var ghost: Node3D = drag.call("ghost")
	var ghost_ok := ghost != null and ghost.owner == null and ghost.get_child_count() == 2
	_aim(camera, root, Vector2(a.global_position.x + 5.0, a.global_position.z + 2.0))
	var motion := InputEventMouseMotion.new()
	motion.position = centre
	usability.call("_forward_3d_gui_input", camera, motion)
	var release := _click(centre)
	release.pressed = false
	release.alt_pressed = true
	usability.call("_forward_3d_gui_input", camera, release)
	var dragged := selection.get_selected_nodes()
	var moved := dragged.size() == 2
	for node in dragged:
		moved = moved and not node in [a, b] and (node as Node).owner == root
	var offset := Vector2.INF
	for node in dragged:
		if String(node.get("catalog_asset_id")) == String(a.get("catalog_asset_id")) and \
				GroupTools.group_of(node as Node) != "group-01":
			offset = Vector2((node as Node3D).global_position.x - a.global_position.x,
				(node as Node3D).global_position.z - a.global_position.z)
	_expect(consumed == EditorPlugin.AFTER_GUI_INPUT_STOP and ghost_ok and moved and
		assets.get_child_count() == before + 2 and drag.call("ghost") == null and
		offset.is_finite(),
		"Alt+drag on a selected group shows a ghost and drops copies where the drag ends")
	history.undo()
	var drag_undone := assets.get_child_count() == before
	history.redo()
	_expect(drag_undone and assets.get_child_count() == before + 2, "an Alt+drag copy is one undo step")
	selection.clear()


func _test_selection_bar(usability: Object, root: Node3D) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var bar: Control = usability.call("selection_bar")
	var loose: Array[Node3D] = []
	for child in root.get_node("AuthoredAssets").get_children():
		if GroupTools.group_of(child).is_empty():
			loose.append(child as Node3D)
	if not _expect(loose.size() >= 2, "the fixture has ungrouped assets for the selection bar"):
		return
	var c := loose[0]
	_select([c])
	usability.call("_refresh_selection_bar")
	var local: Vector3 = root.global_transform.affine_inverse() * c.global_position
	var x_spin := bar.call("spin", "x") as SpinBox
	_expect(bar.visible and String(bar.call("name_text")).begins_with(String(c.name)) and
		absf(x_spin.value - local.x) < 0.01,
		"the selection bar shows the selected object's name and territory position")
	x_spin.value = snappedf(local.x + 2.0, 0.01)
	var moved := absf((root.global_transform.affine_inverse() * c.global_position).x -
		(local.x + 2.0)) < 0.011
	(bar.call("spin", "turn") as SpinBox).value = 45.0
	var turned := absf(float(Tools.summary(root, [c]).turn) - 45.0) < 0.01
	(bar.call("spin", "size") as SpinBox).value = 1.5
	var sized := absf(float(Tools.summary(root, [c]).size) - 1.5) < 0.01
	history.undo()
	history.undo()
	history.undo()
	_expect(moved and turned and sized and
		(root.global_transform.affine_inverse() * c.global_position).distance_to(local) < 0.001,
		"typing X, Turn and Size moves, turns and resizes the object, each one undo step")
	var d := loose[1]
	_select([c, d])
	usability.call("_refresh_selection_bar")
	var centre: Vector3 = Tools.summary(root, [c, d]).position
	var d_before: Vector3 = root.global_transform.affine_inverse() * d.global_position
	(bar.call("spin", "turn") as SpinBox).value = 90.0
	usability.call("_refresh_selection_bar")
	var d_after: Vector3 = root.global_transform.affine_inverse() * d.global_position
	var expected := centre + Basis(Vector3.UP, deg_to_rad(90.0)) * (d_before - centre)
	_expect(String(bar.call("name_text")).begins_with("2 objects") and
		(Tools.summary(root, [c, d]).position as Vector3).distance_to(centre) < 0.001 and
		d_after.distance_to(expected) < 0.01 and
		is_zero_approx((bar.call("spin", "turn") as SpinBox).value),
		"with several objects, Turn by rotates the selection about its centre and resets to 0")
	history.undo()
	(bar.call("button", "group") as Button).pressed.emit()
	var grouped := not GroupTools.group_of(c).is_empty() and \
		GroupTools.group_of(c) == GroupTools.group_of(d)
	(bar.call("button", "ungroup") as Button).pressed.emit()
	_expect(grouped and GroupTools.group_of(c).is_empty(), "the bar's Group and Ungroup buttons work")
	selection.clear()
	usability.call("_refresh_selection_bar")
	_expect(not bar.visible, "the selection bar hides when nothing placed is selected")


func _test_walker_parity() -> void:
	var folded := Walker.fold_published({"bytes": PackedByteArray(WALKER_REFERENCE.fold_half),
		"width": 12, "rows": 12, "x0": -100.0, "z1": 200.0, "height_step": 0.3,
		"height_origin": -1.0}, Vector2i(100, 200))
	_expect(int(folded.get("stage_factor", 0)) == int(WALKER_REFERENCE.fold_factor) and
		Array(folded.get("codes", PackedByteArray())) == WALKER_REFERENCE.fold_codes,
		"the published grid folds onto server tiles exactly as the server's sync does")
	var walker := Walker.new()
	walker.set("_grid", {"codes": PackedByteArray(WALKER_REFERENCE.grid), "width": 10,
		"rows": 10, "origin": Vector2i.ZERO})
	var matching := 0
	for case: Dictionary in WALKER_REFERENCE.searches:
		var found: Array[Vector2i] = walker.search(Vector2i(case.start[0], case.start[1]),
			Vector2i(case.target[0], case.target[1]))
		var expected: Array[Vector2i] = []
		for point: Array in case.path:
			expected.append(Vector2i(point[0], point[1]))
		if found == expected:
			matching += 1
	_expect(matching == WALKER_REFERENCE.searches.size(),
		"routes match the server's A* tile for tile (%d of %d)" % [matching,
			WALKER_REFERENCE.searches.size()])
	var sunmane: Node3D = REGION.new()
	sunmane.set("region_id", "sunmane_steppe")
	sunmane.set("server_origin", Vector2i(194, 292))
	var started := Time.get_ticks_msec()
	var published := Walker.load_grid(sunmane)
	var elapsed := Time.get_ticks_msec() - started
	sunmane.free()
	_expect(String(published.get("source", "")) == "published" and int(published.width) == 792 and
		int(published.rows) == 792 and float(published.stage_metres) > 0.0,
		"Sunmane's published package folds to its 792 x 792 server tiles (stage %.1f m, %d ms)" % [
			float(published.get("stage_metres", 0.0)), elapsed])


## The stage ladder on a low-relief grid, the reachable-area flood and the
## published crossings, against the server's rules.
func _test_walker_stages_and_reach() -> void:
	var units := PackedInt32Array(STAGE_REFERENCE.units)
	var codes_for := func(factor: int) -> PackedByteArray:
		var result := PackedByteArray()
		result.resize(units.size())
		for index in units.size():
			if units[index] > 0:
				result[index] = Walker._coarsen(units[index], factor)
		return result
	var scores := {}
	for factor in [1, 2, 3, 4]:
		scores[factor] = Walker.largest_component(codes_for.call(factor), 24, 24)
	var lowest := 255
	var highest := 0
	for value in units:
		if value > 0:
			lowest = mini(lowest, value)
			highest = maxi(highest, value)
	var factor := Walker.choose_factor(highest - lowest, codes_for, 24, 24)
	_expect(scores == STAGE_REFERENCE.scores and factor == int(STAGE_REFERENCE.factor),
		"on a low-relief map the walker tries the server's stage ladder and picks factor %d as it does" %
			factor)
	# A 5 x 5 grid: an island walled in by blocked tiles and a step too high.
	var walker := Walker.new()
	walker.set("_grid", {"codes": PackedByteArray([
		5, 5, 5, 5, 5,
		5, 0, 0, 0, 5,
		5, 0, 5, 0, 5,
		5, 0, 0, 0, 5,
		5, 5, 5, 5, 20]), "width": 5, "rows": 5, "origin": Vector2i.ZERO,
		"crossings": {Vector2i(2, 0): "the portal Gate"}})
	var shown: bool = walker.show_reachable(true, Vector2i(0, 0))
	var classes: PackedByteArray = walker.grid().get("reach_classes", PackedByteArray())
	_expect(shown and walker.is_reachable(Vector2i(4, 0)) and not walker.is_reachable(Vector2i(2, 2)) and
		not walker.is_reachable(Vector2i(4, 4)) and classes.size() == 25 and classes[12] == 2 and
		classes[24] == 2 and classes[6] == 0 and classes[0] == 1,
		"the reachable-area flood separates ground the walker can reach from ground cut off from it")
	var through: Array[Vector2i] = [Vector2i(0, 0), Vector2i(1, 0), Vector2i(2, 0), Vector2i(3, 0)]
	var onto: Array[Vector2i] = [Vector2i(0, 0), Vector2i(1, 0), Vector2i(2, 0)]
	var crossings := Walker.published_crossings({
		"portals": [{"serverTile": [5, 6], "label": "Gate"}],
		"streamingBorders": [{"anchor": [10.0, 0.0, -20.0], "outward": [1.0, 0.0],
			"halfWidthTiles": 1, "destination": "east"}]}, Vector2i(100, 200))
	_expect("the portal Gate at tile 2, 0" in walker.crossing_on(through) and
		walker.crossing_on(onto).is_empty() and crossings.size() == 4 and
		crossings.has(Vector2i(5, 6)) and crossings.has(Vector2i(110, 219)) and
		crossings.has(Vector2i(110, 221)),
		"a route over a portal or border lane it was not sent to is flagged; one ending there is not")


func _test_play_test(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var started: bool = usability.call("start_play_test")
	var walker: RefCounted = usability.call("play_test_walker")
	_expect(started and String(walker.get("source")) == "live" and
		walker.call("node") != null and (walker.call("node") as Node).owner == null,
		"Play test starts on the live grid for an unpublished territory, as an unsaved helper")
	_expect(walker.call("cell_of", Vector3(12.3, 0.0, 20.7)) == Vector2i(112, 179),
		"the walker uses the snapshot's server tiles, floor(x + ox) and floor(oy - z)")
	_aim(camera, root, Vector2(12.0, 20.0))
	var placed_result: int = usability.call("_forward_3d_gui_input", camera, _click(centre))
	var placed: Vector3 = walker.call("position")
	# Earlier sections sculpt, grade roads and carve a river, so the reachable
	# area is worked out here with the server's step rule instead of assuming
	# fixed points.
	var start: Vector2i = walker.call("cell_of", placed)
	var reachable := _walk_component(walker, start)
	var goal := start
	var outside := Vector2i(-1, -1)
	var blocked := Vector2i(-1, -1)
	var grid: Dictionary = walker.call("grid")
	for ty in int(grid.rows):
		for tx in int(grid.width):
			var tile := Vector2i(tx, ty)
			if reachable.has(tile):
				if Vector2(tile - start).length() > Vector2(goal - start).length():
					goal = tile
			elif bool(walker.call("is_walkable", tile)):
				if outside.x < 0:
					outside = tile
			elif blocked.x < 0 and reachable.has(walker.call("free_tile", tile)) and \
					walker.call("free_tile", tile) != start:
				blocked = tile
	var goal_point: Vector3 = walker.call("cell_point", goal)
	_aim(camera, root, Vector2(goal_point.x, goal_point.z))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	var route: PackedVector3Array = walker.call("route")
	var legal := route.size() >= 2
	var grounded := true
	for index in route.size():
		grounded = grounded and absf(route[index].y - Probe.height_at(root,
			root.global_transform * route[index])) < 0.01
		if index > 0:
			legal = legal and bool(walker.call("step_allowed", walker.call("cell_of", route[index - 1]),
				walker.call("cell_of", route[index])))
	_expect(placed_result == EditorPlugin.AFTER_GUI_INPUT_STOP and placed.is_finite() and
		legal and grounded and route[0].is_equal_approx(placed) and
		route[route.size() - 1].is_equal_approx(goal_point) and
		int(walker.get("steps")) == route.size() - 1,
		"clicks place the walker and route it by legal server steps to the goal (%s; %d points)" % [
			String(walker.get("last_message")), route.size()])
	var first_step: float = walker.call("step_duration", 0)
	walker.call("advance", first_step + 0.001)
	var stepped: Vector3 = walker.call("position")
	walker.call("advance", 10000.0)
	_expect(route.size() >= 2 and stepped.distance_to(route[1]) < 0.05 and
		(is_equal_approx(first_step, 0.6) or is_equal_approx(first_step, 0.6 * sqrt(2.0))) and
		not bool(walker.call("is_walking")) and
		(walker.call("position") as Vector3).is_equal_approx(route[route.size() - 1]),
		"the walker takes 600 ms a metre (x sqrt 2 on diagonals) and stops at the goal")
	usability.call("_forward_3d_gui_input", camera, _key(KEY_R))
	var run_step: float = walker.call("step_duration", 0)
	_expect(bool(walker.get("running")) and
		(is_equal_approx(run_step, 0.2) or is_equal_approx(run_step, 0.2 * sqrt(2.0))),
		"R switches to the 200 ms running pace")
	usability.call("_forward_3d_gui_input", camera, _key(KEY_R))
	var across := outside.x >= 0 and bool(walker.call("walk_to", walker.call("cell_point", outside)))
	_expect(outside.x >= 0 and not across and
		"cannot reach" in String(walker.get("last_message")),
		"a walkable goal cut off by steep ground, water or a climb is reported unreachable")
	var redirected := PackedVector3Array()
	if blocked.x >= 0:
		redirected = walker.call("find_route", walker.call("position"),
			walker.call("cell_point", blocked))
	_expect(blocked.x >= 0 and redirected.size() >= 2 and
		walker.call("cell_of", redirected[redirected.size() - 1]) == walker.call("free_tile", blocked) and
		"nearest walkable" in String(walker.get("last_message")),
		"a click on a blocked tile routes to the nearest walkable tile, as the server does")
	var packed := PackedScene.new()
	var text := ""
	if packed.pack(root) == OK:
		var state := packed.get_state()
		for index in state.get_node_count():
			text += String(state.get_node_name(index)) + "\n"
	_expect(not text.is_empty() and not "__MapAuthoringPlaytest" in text,
		"the walker is never packed into the scene")
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	_expect(not bool(walker.get("active")) and root.get_children(true).all(
		func(node: Node) -> bool: return not String(node.name).begins_with("__MapAuthoringPlaytest")),
		"Escape ends the play test and removes the walker")
	var sunmane: Node3D = REGION.new()
	sunmane.set("region_id", "sunmane_steppe")
	var published := Walkability.published_grid(sunmane)
	sunmane.free()
	_expect(not published.has("error") and float(published.height_step) > 0.0 and
		is_finite(float(published.height_origin)),
		"the published grid carries the height encoding the fold needs")


func _test_minimap(usability: Object, root: Node3D) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	var result: Dictionary = await usability.call("refresh_minimap")
	var dock: Object = usability.call("minimap_dock")
	var framing: Dictionary = dock.call("framing")
	_expect(result.has("error") and not framing.is_empty() and
		(framing.rect as Rect2).has_point(Vector2(20.0, 20.0)),
		"without a renderer the minimap still frames the territory for jumps and overlays")
	var dark := Image.create_empty(8, 8, false, Image.FORMAT_RGBA8)
	dark.fill(Color(0.1, 0.08, 0.05, 1.0))
	dark.set_pixel(0, 0, Color(0.0, 0.0, 0.0, 0.0))
	var levelled: Image = UsabilityPlugin.levelled_minimap(dark)
	_expect(levelled.get_pixel(4, 4).get_luminance() > 0.3 and
		is_zero_approx(levelled.get_pixel(0, 0).a) and
		absf(dark.get_pixel(4, 4).r - 0.1) < 0.01,
		"the minimap brightens a dark render of the owned land, leaving transparency alone")
	var view: Control = dock.call("view")
	view.size = Vector2(200.0, 100.0)
	var rect: Rect2 = framing.rect
	var point := Vector3(10.0, 0.0, 30.0)
	var back: Vector3 = view.call("to_territory", view.call("to_view", point))
	var shown: Rect2 = view.call("image_rect")
	_expect(back.distance_to(point) < 0.001 and is_equal_approx(shown.size.x / shown.size.y,
		rect.size.x / rect.size.y) and (view.call("to_view",
		Vector3(rect.position.x, 0.0, rect.position.y)) as Vector2).is_equal_approx(shown.position),
		"minimap pixels map to territory metres and back, north up")
	var crystal := root.get_node("Gameplay/Harvestables/crystal-01") as Node3D
	_select([crystal])
	usability.call("_update_minimap_state")
	var state: Dictionary = view.get("state")
	_expect(state.has("camera") and (state.get("selection", []) as Array).size() == 1 and
		(state.get("markers", []) as Array).size() == Markers.markers(root).size(),
		"the minimap shows the camera, the selection and every marker")
	var editor_camera := (_editor.call("get_editor_viewport_3d", 0) as SubViewport).get_camera_3d()
	var target := Probe.ray_hit(root, Vector3(30.0, 60.0, 8.0), Vector3.DOWN) as Vector3
	var pressed: bool = await usability.call("focus_camera_at", target)
	# The editor camera eases towards its new target over time, not frames.
	var miss := INF
	for _attempt in 60:
		await create_timer(0.05).timeout
		var forward := -editor_camera.global_transform.basis.z
		var to_target := target - editor_camera.global_position
		miss = (to_target - forward * to_target.dot(forward)).length()
		if miss < 0.5:
			break
	var helpers := root.get_children(true).filter(func(node: Node) -> bool:
		return String(node.name).begins_with("__MapAuthoringFocus"))
	_expect(pressed and miss < 1.0 and helpers.is_empty() and
		selection.get_selected_nodes() == [crystal],
		"a minimap jump points the 3D view at the spot and restores the selection (miss %.2f m)" % miss)
	selection.clear()


func _test_territory_picker() -> void:
	var base := _editor.call("get_base_control") as Control
	var workspace: Object = base.get_meta(&"map_authoring_sculpt_plugin") \
		if base.has_meta(&"map_authoring_sculpt_plugin") else null
	if not _expect(workspace != null, "the Territories plugin is active for the map picker"):
		return
	var dock: Object = workspace.get("_dock")
	# The picker test is about the shared twelve-territory catalog. A branch can point the editor at another
	# catalog (project setting map_authoring/territory_catalog_path), so the shared one is pinned here and the
	# configured one put back afterwards.
	var configured := String(workspace.get("catalog_path"))
	var shared := "res://world_authoring/territories.json"
	if configured != shared:
		workspace.set("catalog_path", shared)
		workspace.call("_reload_sources")
	var items: Array = dock.call("picker_items")
	var thumbnails := items.filter(func(item: Dictionary) -> bool:
		return item.thumbnail is Texture2D).size()
	_expect(items.size() >= 12 and thumbnails == items.size(),
		"Browse… lists every territory with its published minimap (%d of %d)" % [thumbnails,
			items.size()])
	var index := -1
	for position in items.size():
		if bool(items[position].editable):
			index = position
			break
	var opened: Array[String] = []
	var spy := func(path: String) -> void: opened.append(path)
	var handler := Callable(workspace, "_open_scene")
	var connected: bool = dock.is_connected("open_requested", handler)
	if connected:
		dock.disconnect("open_requested", handler)
	dock.connect("open_requested", spy)
	if index >= 0:
		dock.call("pick", index)
	dock.disconnect("open_requested", spy)
	if connected:
		dock.connect("open_requested", handler)
	_expect(index >= 0 and opened.size() == 1 and opened[0].ends_with(".tscn"),
		"clicking a territory thumbnail asks to open its authored scene")
	if configured != shared:
		workspace.set("catalog_path", configured)
		workspace.call("_reload_sources")


func _test_asset_intake(palette: Object) -> void:
	var library := DIR + "/library"
	_remove_tree_recursive(library)
	Catalog.library_directory = library
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(library + "/Rocks"))
	var rock := Node3D.new()
	rock.name = "TinyRock"
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	rock.add_child(mesh)
	mesh.owner = rock
	var packed := PackedScene.new()
	packed.pack(rock)
	ResourceSaver.save(packed, library + "/Rocks/tiny_rock.tscn")
	rock.free()
	var entry := _entry(Catalog.entries(true), "library:Rocks/tiny_rock")
	var created := Placement.instantiate_entry(entry) if not entry.is_empty() else {}
	var node: Node = created.get("node")
	_expect(String(entry.get("category", "")) == "Library: Rocks" and
		String(entry.get("label", "")) == "Tiny Rock" and node != null,
		"a scene dropped into the library folder is a palette asset, no JSON needed")
	if node != null:
		node.free()
	var outside := OS.get_user_data_dir().path_join("map-usability-import")
	DirAccess.make_dir_recursive_absolute(outside)
	var source := outside.path_join("Test Crate.glb")
	var crate := Node3D.new()
	var crate_mesh := MeshInstance3D.new()
	crate_mesh.mesh = BoxMesh.new()
	crate.add_child(crate_mesh)
	crate_mesh.owner = crate
	var document := GLTFDocument.new()
	var gltf := GLTFState.new()
	var exported := document.append_from_scene(crate, gltf) == OK and \
		document.write_to_filesystem(gltf, source) == OK
	crate.free()
	# A text glTF with its own .bin, which the bake cannot take directly.
	var barrel_source := outside.path_join("Test Barrel.gltf")
	var barrel := Node3D.new()
	var barrel_mesh := MeshInstance3D.new()
	barrel_mesh.mesh = CylinderMesh.new()
	barrel.add_child(barrel_mesh)
	barrel_mesh.owner = barrel
	var barrel_state := GLTFState.new()
	var barrel_written := GLTFDocument.new().append_from_scene(barrel, barrel_state) == OK and \
		GLTFDocument.new().write_to_filesystem(barrel_state, barrel_source) == OK
	barrel.free()
	var dock: Object = palette.get("_dock")
	var result: Dictionary = dock.call("import_models",
		PackedStringArray([source, source, outside.path_join("notes.txt"), barrel_source]),
		"Imported Stuff")
	var copied: Array = result.copied
	var ids := Catalog.library_entries().map(func(item: Dictionary) -> String: return String(item.id))
	_expect(exported and copied.slice(0, 2) == [library + "/Imported_Stuff/Test_Crate.glb",
		library + "/Imported_Stuff/Test_Crate_2.glb"] and (result.skipped as Array).size() == 1 and
		"library:Imported_Stuff/Test_Crate" in ids and "library:Imported_Stuff/Test_Crate_2" in ids,
		"Import models copies .glb files into a library category without overwriting (%s)" % [copied])
	var converted := library + "/Imported_Stuff/Test_Barrel.glb"
	var glb_bytes := FileAccess.get_file_as_bytes(converted) if FileAccess.file_exists(converted) \
		else PackedByteArray()
	_expect(barrel_written and converted in copied and glb_bytes.size() > 12 and
		glb_bytes.slice(0, 4).get_string_from_ascii() == "glTF" and
		not FileAccess.file_exists(library + "/Imported_Stuff/Test_Barrel.gltf"),
		"a .gltf is imported as a self-contained .glb, the only glTF form the bake accepts")
	# A .gltf dropped into the library by hand is reported, not listed.
	var loose_file := FileAccess.open(ProjectSettings.globalize_path(library + "/Rocks/loose.gltf"),
		FileAccess.WRITE)
	loose_file.store_string('{"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": []}]}')
	loose_file.close()
	var listed := Catalog.library_entries().map(func(item: Dictionary) -> String: return String(item.id))
	_expect(not "library:Rocks/loose" in listed and
		Array(Catalog.skipped_library_files).any(func(path: String) -> bool:
			return path.ends_with("Rocks/loose.gltf")),
		"a loose .gltf in the library is left out and reported")
	var filesystem := _editor.call("get_resource_filesystem") as EditorFileSystem
	for _attempt in 600:
		if not filesystem.is_scanning():
			break
		await process_frame
	await _frames(3)
	_remove_tree_recursive(outside)
	# Admission notes name what the bake or the game will not carry as it looks.
	var checks := DIR + "/admission"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(checks))
	var clean_notes := Catalog.admission_notes(library + "/Rocks/tiny_rock.tscn")
	var scripted := _admission_scene(Node3D.new(), BoxMesh.new())
	var script := GDScript.new()
	script.source_code = "extends Node3D\n"
	script.reload()
	scripted.set_script(script)
	var shaded := _admission_scene(Node3D.new(), BoxMesh.new())
	var shader := ShaderMaterial.new()
	shader.shader = Shader.new()
	shader.shader.code = "shader_type spatial;\n"
	(shaded.get_child(0) as MeshInstance3D).material_override = shader
	var huge_mesh := BoxMesh.new()
	huge_mesh.size = Vector3(120.0, 2.0, 2.0)
	var huge := _admission_scene(Node3D.new(), huge_mesh)
	var flat := _admission_scene(Node2D.new(), null)
	var notes := {}
	for pair: Array in [["scripted", scripted], ["shaded", shaded], ["huge", huge], ["flat", flat]]:
		var packed_check := PackedScene.new()
		packed_check.pack(pair[1])
		var check_path := checks + "/%s.tscn" % pair[0]
		ResourceSaver.save(packed_check, check_path)
		(pair[1] as Node).free()
		notes[pair[0]] = " ".join(Catalog.admission_notes(check_path))
	_expect(clean_notes.is_empty() and "script" in String(notes.scripted) and
		"custom shader" in String(notes.shaded) and "120 x 2 x 2 m" in String(notes.huge) and
		"Node2D" in String(notes.flat) and "no mesh" in String(notes.flat),
		"library admission notes flag scripts, custom shaders, oversize models and non-3D scenes (%s)" %
			[notes])
	_remove_tree_recursive(checks)


func _admission_scene(root_node: Node, mesh: Mesh) -> Node:
	root_node.name = "Check"
	if mesh != null:
		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		root_node.add_child(instance)
		instance.owner = root_node
	return root_node


func _stroke(usability: Object, camera: Camera3D, root: Node3D, points: Array) -> void:
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	for index in points.size():
		_aim(camera, root, points[index])
		if index == 0:
			usability.call("_forward_3d_gui_input", camera, _click(centre))
			continue
		var motion := InputEventMouseMotion.new()
		motion.position = centre
		motion.button_mask = MOUSE_BUTTON_MASK_LEFT
		usability.call("_forward_3d_gui_input", camera, motion)
		if index == points.size() - 1:
			var release := _click(centre)
			release.pressed = false
			usability.call("_forward_3d_gui_input", camera, release)


func _test_contract_guards(palette: Object, usability: Object, root: Node3D,
		camera: Camera3D) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var assets := root.get_node("AuthoredAssets")
	# A copied spawn is never a second default spawn.
	var spawns := Node3D.new()
	spawns.name = "Spawns"
	root.get_node("Gameplay").add_child(spawns)
	spawns.owner = root
	var spawn: Node3D = MARKER.new()
	spawn.name = "arrival"
	spawn.set("record_id", "arrival")
	spawn.set("kind", "spawn")
	spawn.set("default_spawn", true)
	spawns.add_child(spawn)
	spawn.owner = root
	spawn.global_position = Probe.ray_hit(root, Vector3(20.0, 60.0, 30.0), Vector3.DOWN) as Vector3
	_select([spawn])
	var spawn_copies: Array = usability.call("duplicate_selection", Vector3(2.0, 0.0, 0.0))
	_expect(spawn_copies.size() == 1 and not bool(spawn_copies[0].get("default_spawn")) and
		bool(spawn.get("default_spawn")),
		"a copied default spawn is not a default spawn; the original stays one")
	# Ctrl+D in the 3D view duplicates placements in place with fresh ids.
	var loose: Array[Node3D] = []
	for child in assets.get_children():
		if GroupTools.group_of(child).is_empty():
			loose.append(child as Node3D)
	var source := loose[0]
	_select([source])
	var before := assets.get_child_count()
	var ctrl_d := _ctrl_key(KEY_D, false)
	var redirected: int = usability.call("_forward_3d_gui_input", camera, ctrl_d)
	var copy := assets.get_child(assets.get_child_count() - 1) as Node3D
	_expect(redirected == EditorPlugin.AFTER_GUI_INPUT_STOP and assets.get_child_count() == before + 1 and
		String(copy.get("asset_id")) != String(source.get("asset_id")) and
		copy.global_transform.is_equal_approx(source.global_transform),
		"Ctrl+D in the 3D view duplicates placements in place with fresh ids")
	# Godot's own duplicate (from the Scene dock) is caught and can be fixed.
	usability.call("poll_overlays")
	var clone := source.duplicate() as Node3D
	assets.add_child(clone, true)
	clone.owner = root
	for descendant in clone.find_children("*", "", true, false):
		if descendant.get_parent() == clone:
			descendant.owner = root
	usability.call("poll_overlays")
	var flagged: Array = usability.call("duplicate_id_groups")
	_select([clone])
	var fixed: int = usability.call("fix_duplicate_ids")
	var fresh := String(clone.get("asset_id")) != String(source.get("asset_id"))
	history.undo()
	var restored := String(clone.get("asset_id")) == String(source.get("asset_id"))
	history.redo()
	usability.call("poll_overlays")
	_expect(flagged.size() == 1 and String(flagged[0].kind) == "asset" and fixed == 1 and fresh and
		restored and (usability.call("duplicate_id_groups") as Array).is_empty(),
		"a shared asset id is flagged, and the fix gives only the copy a fresh id in one undo step")
	# Duplicates a scene already had when opened are left alone, and marker ids
	# only have to be unique within their own section.
	var legacy := source.duplicate() as Node3D
	assets.add_child(legacy, true)
	legacy.owner = root
	usability.call("_remember_duplicate_baseline", root)
	var twin: Node3D = MARKER.new()
	twin.name = "crystal-twin"
	twin.set("record_id", "crystal-01")
	twin.set("kind", "landmark")
	var landmarks := Node3D.new()
	landmarks.name = "Landmarks"
	root.get_node("Gameplay").add_child(landmarks)
	landmarks.owner = root
	landmarks.add_child(twin)
	twin.owner = root
	usability.call("poll_overlays")
	_expect((usability.call("duplicate_id_groups") as Array).is_empty(),
		"pre-existing shared ids and equal ids in different gameplay sections are not flagged")
	for node: Node in [legacy, twin, landmarks]:
		node.get_parent().remove_child(node)
		node.free()
	usability.call("_remember_duplicate_baseline", root)
	# Prefabs keep assets and gameplay markers; placed, a marker takes a fresh
	# id in its kind's container, drops what a copy must not keep, and follows
	# the placed copy of the asset it followed.
	var crystal := root.get_node("Gameplay/Harvestables/crystal-01") as Node3D
	var saved_follow := String(crystal.get("follow_asset_id"))
	var saved_bindings: Array[Dictionary] = []
	saved_bindings.assign(crystal.get("runtime_bindings"))
	crystal.set("follow_asset_id", String(source.get("asset_id")))
	var bound: Array[Dictionary] = [{"recordId": "crystal-01", "service": "harvest"}]
	crystal.set("runtime_bindings", bound)
	_select([source, crystal])
	var mixed: Dictionary = palette.call("save_selection_as_prefab", "Mixed Pick")
	_select([crystal])
	var markers_only: Dictionary = palette.call("save_selection_as_prefab", "Only Markers")
	crystal.set("follow_asset_id", saved_follow)
	crystal.set("runtime_bindings", saved_bindings)
	var harvestables := root.get_node("Gameplay/Harvestables")
	var markers_before := harvestables.get_child_count()
	var created := Prefabs.instantiate(_entry(Prefabs.entries(), "prefab:mixed_pick"))
	var placed_members: Array[Node3D] = []
	if created.get("node") != null:
		placed_members = Prefabs.commit_with_undo(_undo, root, created.node, Transform3D(
			Basis(Vector3.UP, PI / 2.0), Probe.ray_hit(root, Vector3(28.0, 60.0, 28.0),
			Vector3.DOWN) as Vector3), true, 0.0, "Mixed Pick")
	var marker_copy: Node = null
	var asset_copy: Node = null
	for member in placed_members:
		if member.get_script() == MARKER:
			marker_copy = member
		else:
			asset_copy = member
	_expect(int(mixed.get("members", 0)) == 2 and int(mixed.get("markers", 0)) == 1 and
		int(mixed.get("left_out_markers", 0)) == 0 and int(markers_only.get("members", 0)) == 1 and
		marker_copy != null and marker_copy.get_parent() == harvestables and
		String(marker_copy.get("record_id")) != "crystal-01" and
		(marker_copy.get("runtime_bindings") as Array).is_empty() and asset_copy != null and
		asset_copy.get_parent() == root.get_node("AuthoredAssets") and
		String(marker_copy.get("follow_asset_id")) == String(asset_copy.get("asset_id")),
		"a prefab keeps assets and markers; a placed marker gets a fresh id in its container, no bindings, and follows the placed asset")
	history.undo()
	_expect(harvestables.get_child_count() == markers_before,
		"placing a prefab with markers is one undo step")
	selection.clear()


func _bind_fixture_sculpt(root: Node3D) -> Object:
	var base := _editor.call("get_base_control") as Control
	var sculpt: Object = base.get_meta(&"map_authoring_sculpt_plugin") \
		if base.has_meta(&"map_authoring_sculpt_plugin") else null
	if sculpt == null:
		return null
	var tool: Object = sculpt.get("_sculpt")
	var entry := {"ownership_polygon": PackedVector2Array([Vector2(0, 0), Vector2(40, 0),
		Vector2(40, 40), Vector2(0, 40)]), "translation": Vector3.ZERO,
		"ownership_sha256": String(root.get("ownership_polygon_sha256")), "editable": true}
	return tool if bool(tool.call("bind", root, root.get_node("Terrain"), entry, _undo)) else null


func _test_ground_and_plateaus(usability: Object, root: Node3D, camera: Camera3D) -> void:
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var centre := camera.get_viewport().get_visible_rect().size * 0.5
	var tool := _bind_fixture_sculpt(root)
	if not _expect(tool != null, "the sculpt tool binds the fixture for border protection"):
		return
	var area: RefCounted = usability.call("area_tool")
	var started: bool = usability.call("start_area_tool", "ground", {"preset": "Grass",
		"surface_label": "Preset: Grass", "shape": 0, "blend_width": 2.0, "opacity": 0.8,
		"priority": 5})
	var had_ground := root.get_node_or_null("Ground") != null
	_aim(camera, root, Vector2(20.0, 20.0))
	usability.call("_forward_3d_gui_input", camera, _click(centre))
	_aim(camera, root, Vector2(26.0, 23.0))
	var release := _click(centre)
	release.pressed = false
	usability.call("_forward_3d_gui_input", camera, release)
	var region := root.get_node_or_null("Ground/Regions/ground-01") as Node3D
	var ground_at := Probe.height_at(root, region.global_position) if region != null else NAN
	_expect(started and region != null and region.owner == root and
		String(region.get("region_id")) == "ground-01" and
		(region.get("size") as Vector2).is_equal_approx(Vector2(12.0, 6.0)) and
		is_equal_approx(float(region.get("blend_width")), 2.0) and
		is_equal_approx(float(region.get("opacity")), 0.8) and int(region.get("priority")) == 5 and
		region.get("surface") is MapAuthoringSurface and
		String((region.get("surface") as MapAuthoringSurface).texture_preset) == "Grass" and
		Vector2(region.global_position.x - 20.0, region.global_position.z - 20.0).length() < 0.05 and
		absf(region.global_position.y - ground_at) < 0.01,
		"dragging on the terrain adds a ground region control of the chosen surface and size")
	history.undo()
	var undone := root.get_node_or_null("Ground/Regions/ground-01") == null and \
		(had_ground or root.get_node_or_null("Ground") == null)
	history.redo()
	_expect(undone and root.get_node_or_null("Ground/Regions/ground-01") != null,
		"a ground region is one undo step")
	var outside: Node3D = area.call("create", _undo, root.global_transform * Vector3(38.0, 0.0, 20.0),
		root.global_transform * Vector3(43.0, 0.0, 23.0))
	_expect(outside == null and "inside the land" in String(area.get("last_message")),
		"a ground region reaching past the owned land is refused")
	var regions := root.get_node("Ground/Regions")
	var fillers: Array[Node] = []
	for index in 126:
		var filler: Node3D = load("res://src/dev/map_authoring_region/ground_region_control.gd").new()
		regions.add_child(filler)
		fillers.append(filler)
	var full: String = area.call("ground_error", Vector3(20.0, 0.0, 20.0), Vector2(4.0, 4.0))
	for filler in fillers:
		regions.remove_child(filler)
		filler.free()
	_expect("127" in full, "a territory never exceeds the 127 ground regions the preview draws")
	# Q turns the next shape 15 degrees; its size is measured in the turned frame.
	for _turn in 3:
		usability.call("_forward_3d_gui_input", camera, _key(KEY_Q))
	var turned: Node3D = area.call("create", _undo, root.global_transform * Vector3(20.0, 0.0, 30.0),
		root.global_transform * Vector3(24.0, 0.0, 30.0))
	var expected_axis := Vector3(cos(PI / 4.0), 0.0, -sin(PI / 4.0))
	_expect(turned != null and is_equal_approx(float(area.call("yaw")), PI / 4.0) and
		turned.global_basis.x.normalized().is_equal_approx(expected_axis) and
		(turned.get("size") as Vector2).is_equal_approx(Vector2.ONE * 4.0 * sqrt(2.0)),
		"Q/E turn a ground region; the dragged corner sets its size in the turned frame")
	if turned != null:
		history.undo()
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	# A stroke paints a region every 60% of the brush along the drag, in one step.
	usability.call("start_area_tool", "ground", {"preset": "Grass", "surface_label": "Preset: Grass",
		"shape": 0, "blend_width": 1.0, "opacity": 0.8, "priority": 5, "stroke": true,
		"brush": 4.0})
	var counted := func() -> int:
		return root.get_node("Ground/Regions").get_children().filter(func(node: Node) -> bool:
			return node.get_script() == load("res://src/dev/map_authoring_region/ground_region_control.gd")).size()
	var regions_before: int = counted.call()
	_stroke(usability, camera, root, [Vector2(10.0, 30.0), Vector2(13.0, 30.0), Vector2(17.0, 30.0),
		Vector2(21.5, 30.0)])
	var painted: int = counted.call() - regions_before
	history.undo()
	var stroke_undone: int = counted.call() - regions_before
	for index in 125 - regions_before:
		var filler: Node3D = load("res://src/dev/map_authoring_region/ground_region_control.gd").new()
		regions.add_child(filler)
		fillers.append(filler)
	_stroke(usability, camera, root, [Vector2(10.0, 30.0), Vector2(21.5, 30.0)])
	var capped_message := String(area.get("last_message"))
	var capped: int = counted.call() - 125
	history.undo()
	for filler in fillers:
		if is_instance_valid(filler):
			regions.remove_child(filler)
			filler.free()
	_expect(painted == 5 and stroke_undone == 0 and capped == 2 and "127" in capped_message,
		"a ground stroke paints a brush-sized region every 60%% of the brush in one undo step, up to the cap (%d, %s)" %
			[painted, capped_message])
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	usability.call("start_area_tool", "ground", {"preset": "Grass", "surface_label": "Preset: Grass",
		"shape": 0, "blend_width": 2.0, "opacity": 0.8, "priority": 5})
	usability.call("_forward_3d_gui_input", camera, _key(KEY_ESCAPE))
	_expect(not bool(area.call("is_active")), "Escape stops the ground tool")
	# Plateaus: terrain patches, refused where they would touch the protected border.
	started = usability.call("start_area_tool", "plateau", {"operation": "set", "shape": 1,
		"height": 2.0, "feather": 2.0})
	var terrain := root.get_node("Terrain")
	var before_centre := float(terrain.call("height_at_local", 12.0, 22.0))
	var patch: Node3D = area.call("create", _undo, root.global_transform * Vector3(12.0, 0.0, 22.0),
		root.global_transform * Vector3(18.0, 0.0, 28.0))
	terrain.call("refresh_preview")
	var levelled := float(terrain.call("height_at_local", 12.0, 22.0))
	_expect(started and patch != null and patch.get_parent().name == "Patches" and
		patch.owner == root and String(patch.get("patch_id")) == "stamp-01" and
		int(patch.get("operation")) == 1 and
		absf(patch.global_position.y - (before_centre + 2.0)) < 0.01 and
		absf(levelled - (before_centre + 2.0)) < 0.01,
		"a plateau stamp adds a Set terrain patch that levels the ground 2 m above the click")
	history.undo()
	terrain.call("refresh_preview")
	var restored := absf(float(terrain.call("height_at_local", 12.0, 22.0)) - before_centre) < 0.01
	history.redo()
	_expect(restored and root.get_node_or_null("Terrain/Patches/stamp-01") != null,
		"a plateau is one undo step")
	var border: Node3D = area.call("create", _undo, root.global_transform * Vector3(3.0, 0.0, 20.0),
		root.global_transform * Vector3(7.0, 0.0, 24.0))
	_expect(border == null and "protected border" in String(area.get("last_message")),
		"a plateau touching the protected border band is refused")
	usability.call("_forward_3d_gui_input", camera, _key(KEY_E))
	usability.call("_forward_3d_gui_input", camera, _key(KEY_E))
	var tilted: Node3D = area.call("create", _undo, root.global_transform * Vector3(26.0, 0.0, 14.0),
		root.global_transform * Vector3(30.0, 0.0, 14.0))
	var tilted_axis := Vector3(cos(-PI / 6.0), 0.0, -sin(-PI / 6.0))
	_expect(tilted != null and tilted.global_basis.x.normalized().is_equal_approx(tilted_axis) and
		(tilted.get("size") as Vector2).is_equal_approx(Vector2(8.0 * cos(PI / 6.0), 8.0 * sin(PI / 6.0))),
		"a plateau turns with Q/E as well")
	if tilted != null:
		history.undo()
	usability.call("_forward_3d_gui_input", camera, _click(centre, MOUSE_BUTTON_RIGHT))
	_expect(not bool(area.call("is_active")), "right-click stops the plateau tool")
	tool.call("unbind")
	var unbound: bool = usability.call("start_area_tool", "plateau", {"operation": "add",
		"height": 1.0})
	_expect(not unbound and "Border protection" in String(area.get("last_message")),
		"without the Territories binding the plateau tool refuses to start")


func _test_heightmap_import(root: Node3D) -> void:
	var tool := _bind_fixture_sculpt(root)
	if not _expect(tool != null, "the sculpt tool binds the fixture for the heightmap import"):
		return
	var terrain := root.get_node("Terrain")
	var history := _undo.get_history_undo_redo(_undo.get_object_history_id(root))
	var base_bytes := FileAccess.get_file_as_bytes(ProjectSettings.globalize_path(HEIGHT_PATH))
	var base: PackedFloat32Array = terrain.call("base_heights")
	var before: PackedFloat32Array = terrain.call("sculpted_base_heights")
	var image := Image.create_empty(2, 2, false, Image.FORMAT_RF)
	image.set_pixel(0, 0, Color(0.0, 0.0, 0.0))
	image.set_pixel(1, 0, Color(1.0, 0.0, 0.0))
	image.set_pixel(0, 1, Color(0.5, 0.0, 0.0))
	image.set_pixel(1, 1, Color(0.25, 0.0, 0.0))
	var result: Dictionary = tool.call("import_heightmap", image, Rect2(10.0, 10.0, 20.0, 20.0),
		0.0, 10.0, true)
	var after: PackedFloat32Array = terrain.call("sculpted_base_heights")
	var width := GRID.x
	_expect(not result.has("error") and absf(after[10 * width + 10] - 0.0) < 0.001 and
		absf(after[10 * width + 30] - 10.0) < 0.001 and absf(after[30 * width + 10] - 5.0) < 0.001 and
		absf(after[30 * width + 30] - 2.5) < 0.001 and after[5 * width + 5] == before[5 * width + 5],
		"Replace writes black-to-white heights with the image's top row north, and leaves ground outside the area alone")
	history.undo()
	var undone: PackedFloat32Array = terrain.call("sculpted_base_heights")
	history.redo()
	_expect(undone == before, "a heightmap import is one undo step")
	var offset: Dictionary = tool.call("import_heightmap", Image.create_empty(1, 1, false,
		Image.FORMAT_RF), Rect2(0.0, 0.0, 40.0, 40.0), 5.0, 5.0, false)
	var offset_heights: PackedFloat32Array = terrain.call("sculpted_base_heights")
	var fields: Dictionary = tool.call("protection_fields")
	var locked: PackedByteArray = fields.locked
	var weights: PackedFloat32Array = fields.weights
	var protected_kept := true
	var fade_blended := false
	for index in locked.size():
		if locked[index] != 0:
			protected_kept = protected_kept and offset_heights[index] == after[index]
		elif weights[index] > 0.0 and weights[index] < 1.0:
			fade_blended = fade_blended or absf(offset_heights[index] - after[index] -
				5.0 * weights[index]) < 0.001
	_expect(not offset.has("error") and int(offset.get("protected", 0)) > 0 and protected_kept and
		fade_blended and absf(offset_heights[20 * width + 20] - after[20 * width + 20] - 5.0) < 0.001,
		"Offset adds its height, blends the fade band and never changes locked border samples")
	var stale: Resource = load("res://src/dev/map_authoring_region/terrain_sculpt_layer.gd").new()
	stale.bind_base("0".repeat(64), terrain.get("origin"), terrain.get("grid_size"),
		terrain.get("cell_metres"))
	_expect(not bool(terrain.call("apply_sculpt_layer", stale)) and
		FileAccess.get_file_as_bytes(ProjectSettings.globalize_path(HEIGHT_PATH)) == base_bytes and
		base == terrain.call("base_heights"),
		"a layer bound to another base is rejected and the base height file is never rewritten")
	history.undo()
	history.undo()
	# Preview shows the import without an undo step; cancel puts the ground back;
	# importing after a preview is still one step back to the original ground.
	var steps := history.get_history_count()
	var previewed: Dictionary = tool.call("preview_heightmap", image, Rect2(10.0, 10.0, 20.0, 20.0),
		0.0, 10.0, true)
	var shown: PackedFloat32Array = terrain.call("sculpted_base_heights")
	var no_step := history.get_history_count() == steps
	tool.call("cancel_heightmap_preview")
	var put_back: PackedFloat32Array = terrain.call("sculpted_base_heights")
	tool.call("preview_heightmap", image, Rect2(10.0, 10.0, 20.0, 20.0), 0.0, 10.0, true)
	var kept: Dictionary = tool.call("import_heightmap", image, Rect2(10.0, 10.0, 20.0, 20.0),
		0.0, 10.0, true)
	var imported: PackedFloat32Array = terrain.call("sculpted_base_heights")
	history.undo()
	var reverted: PackedFloat32Array = terrain.call("sculpted_base_heights")
	_expect(not previewed.has("error") and absf(shown[10 * width + 30] - 10.0) < 0.001 and no_step and
		put_back == before and not kept.has("error") and imported == shown and reverted == before and
		not bool(tool.call("is_previewing_heightmap")),
		"a heightmap preview changes the terrain without an undo step; cancel restores, import keeps it as one step")
	var base_control := _editor.call("get_base_control") as Control
	var workspace: Object = base_control.get_meta(&"map_authoring_sculpt_plugin")
	var picked: Rect2 = workspace.call("finish_heightmap_area_pick", Vector3(25.0, 3.0, 16.0),
		Vector3(5.0, 1.0, 6.0))
	var dock: Object = workspace.get("_dock")
	var dialog := dock.get("_heightmap_dialog") as Window
	var shown_again := dialog != null and dialog.visible
	if dialog != null:
		dialog.hide()
	_expect(picked == Rect2(5.0, 6.0, 20.0, 10.0) and dock.call("heightmap_area") == picked and
		shown_again, "dragging out the area on the map fills the import dialog's area and reopens it")
	tool.call("unbind")


func _test_low_spec(usability: Object, root: Node3D) -> void:
	var meshes: Array[GeometryInstance3D] = []
	for container in ["AuthoredAssets", "AuthoredScenery", "GeneratedPreview"]:
		var holder := root.get_node_or_null(container)
		if holder != null:
			for node in holder.find_children("*", "GeometryInstance3D", true, false):
				meshes.append(node as GeometryInstance3D)
	var culled: int = usability.call("set_low_spec", true)
	var on: Dictionary = usability.call("performance_state")
	var untouched := meshes.all(func(mesh: GeometryInstance3D) -> bool:
		return is_zero_approx(mesh.visibility_range_end))
	var off_count: int = usability.call("set_low_spec", false)
	var off: Dictionary = usability.call("performance_state")
	_expect(culled == meshes.size() and meshes.size() > 0 and bool(on.active) and
		bool(on.half_resolution) and untouched and off_count == 0 and not bool(off.active) and
		not bool(off.half_resolution) and int(off.culled) == 0,
		"Low spec halves the 3D view and hides far meshes through the renderer, then restores both")


func _test_toolbar(usability: Object) -> void:
	var toolbar: Object = usability.call("toolbar")
	var snap := toolbar.call("button", "snap") as Button
	snap.button_pressed = true
	var snapped_on := bool(Settings.value("placement/snap_to_grid"))
	snap.button_pressed = false
	var pins := toolbar.call("button", "pins") as Button
	pins.button_pressed = false
	var hidden := not bool(Settings.value("markers/show"))
	pins.button_pressed = true
	var walk := toolbar.call("walk_menu") as MenuButton
	walk.get_popup().id_pressed.emit(Walkability.Mode.LIVE)
	var live := int((usability.call("walkability_state") as Dictionary).mode) == Walkability.Mode.LIVE
	walk.get_popup().id_pressed.emit(Walkability.Mode.OFF)
	var play := toolbar.call("button", "play") as Button
	play.button_pressed = true
	var playing := bool((usability.call("play_test_walker") as RefCounted).get("active"))
	play.button_pressed = false
	_expect(snapped_on and not bool(Settings.value("placement/snap_to_grid")) and hidden and
		bool(Settings.value("markers/show")) and live and playing and
		not bool((usability.call("play_test_walker") as RefCounted).get("active")),
		"toolbar toggles switch snap, pins, the walkability mode and the play test in one click")


func _aim(camera: Camera3D, root: Node3D, xz: Vector2) -> void:
	var target := Probe.ray_hit(root, Vector3(xz.x, 60.0, xz.y), Vector3.DOWN) as Vector3
	camera.global_position = target + Vector3(0.0, 30.0, 0.01)
	camera.look_at(target, Vector3.FORWARD)


func _bottom(node: Node3D, transform: Transform3D) -> float:
	var bounds := Placement.mesh_bounds(node)
	return transform.origin.y + (Transform3D(transform.basis, Vector3.ZERO) *
		(bounds.bounds as AABB)).position.y


func _height(node: Node3D, transform: Transform3D) -> float:
	var bounds := Placement.mesh_bounds(node)
	return (Transform3D(transform.basis, Vector3.ZERO) * (bounds.bounds as AABB)).size.y


func _first_mesh_path(asset: Node3D) -> String:
	var content: Node = asset.call("content_root")
	for node in content.find_children("*", "MeshInstance3D", true, false):
		return String(content.get_path_to(node))
	return ""


func _key(keycode: Key, shift: bool = false) -> InputEventKey:
	var event := InputEventKey.new()
	event.keycode = keycode
	event.pressed = true
	event.shift_pressed = shift
	return event


func _wheel(up: bool) -> InputEventMouseButton:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_WHEEL_UP if up else MOUSE_BUTTON_WHEEL_DOWN
	event.pressed = true
	event.shift_pressed = true
	return event


func _click(position: Vector2, button: MouseButton = MOUSE_BUTTON_LEFT) -> InputEventMouseButton:
	var event := InputEventMouseButton.new()
	event.button_index = button
	event.pressed = true
	event.position = position
	return event


func _entry(entries: Array[Dictionary], id: String) -> Dictionary:
	for entry in entries:
		if String(entry.id) == id:
			return entry
	return {}


func _remove_tree(path: String) -> void:
	var absolute := ProjectSettings.globalize_path(path)
	var folder := DirAccess.open(absolute)
	if folder == null:
		return
	for file_name in folder.get_files():
		DirAccess.remove_absolute(absolute.path_join(file_name))
	DirAccess.remove_absolute(absolute)


func _walk_component(walker: RefCounted, start: Vector2i) -> Dictionary:
	var seen := {start: true}
	var queue: Array[Vector2i] = [start]
	while not queue.is_empty():
		var cell: Vector2i = queue.pop_back()
		for dy in [-1, 0, 1]:
			for dx in [-1, 0, 1]:
				var next := cell + Vector2i(dx, dy)
				if (dx == 0 and dy == 0) or seen.has(next):
					continue
				if not bool(walker.call("step_allowed", cell, next)):
					continue
				seen[next] = true
				queue.append(next)
	return seen


func _select(nodes: Array) -> void:
	var selection := _editor.call("get_selection") as EditorSelection
	selection.clear()
	for node in nodes:
		selection.add_node(node)


func _frames(count: int) -> void:
	for _frame in count:
		await process_frame


func _ctrl_key(keycode: Key, shift: bool) -> InputEventKey:
	var event := _key(keycode, shift)
	event.ctrl_pressed = true
	return event


func _remove_tree_recursive(path: String) -> void:
	var absolute := ProjectSettings.globalize_path(path)
	if not DirAccess.dir_exists_absolute(absolute):
		return
	for folder in DirAccess.get_directories_at(absolute):
		_remove_tree_recursive(absolute.path_join(folder))
	for file_name in DirAccess.get_files_at(absolute):
		DirAccess.remove_absolute(absolute.path_join(file_name))
	DirAccess.remove_absolute(absolute)


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	failures += 1
	push_error("FAIL: " + message)
	return false


func _finish() -> void:
	for key: String in _saved_settings:
		Settings.set_value(key, _saved_settings[key])
	Prefabs.directory = Prefabs.PREFAB_DIRECTORY
	_remove_tree(PREFAB_DIR)
	Catalog.library_directory = Catalog.LIBRARY_DIRECTORY
	Catalog.entries(true)
	_remove_tree_recursive(DIR + "/library")
	for path in [HEIGHT_PATH, SCENE_PATH, RELOAD_PATH]:
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	print("map authoring usability editor: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
