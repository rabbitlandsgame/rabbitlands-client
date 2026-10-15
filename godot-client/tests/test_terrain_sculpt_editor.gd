extends SceneTree

const TOOL := preload("res://addons/map_authoring_workspace/terrain_sculpt_tool.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const PREVIEW := preload("res://addons/map_authoring_workspace/reference_preview.gd")
const FIXTURE_DIR := "res://test-artifacts/terrain-sculpt"
const HEIGHT_PATH := FIXTURE_DIR + "/editor-base.f32le"
const SCENE_PATH := FIXTURE_DIR + "/editor-saved.tscn"
# An isolated catalog, manifest and authoring spec for the fixture alone: the
# shared territory catalog never gains a test entry.
const CATALOG_PATH := FIXTURE_DIR + "/editor-catalog.json"
const MANIFEST_PATH := FIXTURE_DIR + "/editor-world.json"
const SPEC_PATH := FIXTURE_DIR + "/editor-region-authoring-spec.json"
const REGION_ID := "sculpt_editor_fixture"
const REGION_LABEL := "Sculpt Editor Fixture"
const SERVER_ORIGIN := Vector2i(100, 200)
const SERVER_CELLS := Vector2i(20, 20)
const GRID := Vector2i(11, 11)
const SETTINGS := {"mode": 0, "radius": 3.0, "strength": 1.0,
	"softness": 0.0, "flatten_target": 0.0}

var failures := 0
var _plugin: Object


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	if not Engine.is_editor_hint():
		push_error("Terrain sculpt editor harness requires --editor")
		quit(1)
		return
	var editor_interface: Object = Engine.get_singleton("EditorInterface")
	var base_control := editor_interface.call("get_base_control") as Control
	var plugin: Object = null
	# The editor initializes plugins after SceneTree._initialize during a fresh
	# QA project scan. Wait for the actual dock, with a bounded 30-second limit.
	for _attempt in 300:
		if bool(editor_interface.call("is_plugin_enabled",
				"map_authoring_workspace")) and base_control != null:
			plugin = base_control.get_meta(&"map_authoring_sculpt_plugin", null)
			if plugin != null and base_control.find_child(
					"MapAuthoringWorkspace", true, false) != null:
				break
		await create_timer(0.1).timeout
	_expect(bool(editor_interface.call("is_plugin_enabled",
		"map_authoring_workspace")) and base_control != null and
		base_control.find_child("MapAuthoringWorkspace", true, false) != null and
		plugin != null,
		"real Territories plugin and dock are active in the editor")
	if plugin == null:
		_finish(1)
		return
	_plugin = plugin
	for path: String in [HEIGHT_PATH, SCENE_PATH, CATALOG_PATH, MANIFEST_PATH, SPEC_PATH]:
		if not path.begins_with(FIXTURE_DIR + "/"):
			_abort("fixture path escapes the fixture directory: " + path)
			return
	var dir := ProjectSettings.globalize_path(HEIGHT_PATH).get_base_dir()
	DirAccess.make_dir_recursive_absolute(dir)
	var file := FileAccess.open(ProjectSettings.globalize_path(HEIGHT_PATH),
		FileAccess.WRITE)
	file.big_endian = false
	for _index in GRID.x * GRID.y:
		file.store_float(10.0)
	file.close()
	var original_bytes := FileAccess.get_file_as_bytes(
		ProjectSettings.globalize_path(HEIGHT_PATH))

	_write_fixture_catalog()
	var root: Variant = REGION.new()
	root.name = "SculptEditorFixture"
	root.region_id = REGION_ID
	root.continent_translation = Vector3.ZERO
	root.metres_per_tile = 1.0
	root.server_origin = SERVER_ORIGIN
	root.server_cells = SERVER_CELLS
	root.collision_origin_metres = Vector2(-SERVER_ORIGIN.x, SERVER_ORIGIN.y)
	var polygon := PackedVector2Array([
		Vector2(0, 0), Vector2(20, 0), Vector2(20, 20), Vector2(0, 20)])
	var polygon_rows := []
	for point in polygon:
		polygon_rows.append([point.x, point.y])
	root.ownership_polygon_sha256 = JSON.stringify(polygon_rows).sha256_text()
	root.authority_gameplay = false
	var terrain: Variant = TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = Vector2.ZERO
	terrain.grid_size = GRID
	terrain.cell_metres = 2.0
	terrain.base_heights_path = HEIGHT_PATH
	terrain.preview_enabled = false
	root.add_child(terrain)
	terrain.owner = root
	get_root().add_child(root)
	_expect(terrain.refresh_preview(), "fixture terrain loads")
	var initial_scene := PackedScene.new()
	_expect(initial_scene.pack(root) == OK and
		ResourceSaver.save(initial_scene, SCENE_PATH) == OK,
		"initial fixture scene saves")
	root.queue_free()
	await process_frame
	plugin.set("catalog_path", CATALOG_PATH)
	plugin.call("_reload_sources")
	editor_interface.call("open_scene_from_path", SCENE_PATH)
	# Nothing below may send input or save until the edited scene is provably
	# this fixture: the editor can still hold a scene reopened from its layout.
	root = null
	for _attempt in 120:
		await process_frame
		root = editor_interface.call("get_edited_scene_root")
		if _is_fixture_root(root):
			break
	if not _is_fixture_root(root):
		_abort("the edited scene is not the sculpt fixture (%s); nothing was sent or saved" % [
			root.scene_file_path if root != null else "no scene"])
		return
	_expect(true, "editor opens the saved sculpt fixture as the edited scene")
	terrain = root.get_node_or_null("Terrain")
	if terrain == null:
		_abort("the fixture scene has no Terrain")
		return
	var fixture_root: Node = root

	var catalog: Object = plugin.get("_catalog")
	var entry: Dictionary = catalog.call("find", plugin.get("_entries"),
		root.region_id)
	_expect(not entry.is_empty() and bool(entry.get("editable", false)) and
		String(entry.get("ownership_sha256", "")) == root.ownership_polygon_sha256 and
		(catalog.get("errors") as PackedStringArray).is_empty(),
		"the isolated fixture catalog enables only the matching saved authored scene: %s" %
			"; ".join(catalog.get("errors") as PackedStringArray))
	_expect(catalog.call("find", catalog.call("entries"), REGION_ID).is_empty(),
		"the shared territory catalog never lists the fixture")
	var fields: Dictionary = TOOL.boundary_fields(polygon, Vector3.ZERO,
		Vector2.ZERO, GRID, 2.0)
	_expect(fields.locked[5 * GRID.x + 2] == 1 and
		is_equal_approx(fields.weights[5 * GRID.x + 3], 0.5) and
		is_equal_approx(fields.weights[5 * GRID.x + 5], 1.0),
		"two-cell hard collar and two-cell inward fade")
	var diagonal := PackedVector2Array([
		Vector2(0, 0), Vector2(20, 0), Vector2(20, 20)])
	var diagonal_fields: Dictionary = TOOL.boundary_fields(diagonal,
		Vector3.ZERO, Vector2.ZERO, GRID, 2.0)
	_expect(diagonal_fields.locked[5 * GRID.x + 3] == 1,
		"diagonal polygon collar locks nearby samples")
	var preview = PREVIEW.new()
	root.add_child(preview)
	preview.configure(root, {"id": root.region_id})
	var active_source := MeshInstance3D.new()
	active_source.name = "__TerrainPreview"
	terrain.add_child(active_source)
	active_source.visible = false
	preview._source_visibility[active_source.get_instance_id()] = {
		"node": active_source, "visible": true}
	var active_clip := Node3D.new()
	active_clip.name = "ActiveOwnedTerrain"
	preview.add_child(active_clip)
	var owned_neighbor := Node3D.new()
	owned_neighbor.name = "Owned_Terrain_published"
	preview.add_child(owned_neighbor)
	var authored_neighbor := Node3D.new()
	authored_neighbor.name = "OwnedTerrain_saved"
	preview.add_child(authored_neighbor)
	var neighbor := Node3D.new()
	neighbor.name = "Reference_neighbor"
	preview.add_child(neighbor)
	preview.set_sculpt_preview_active(true)
	_expect(active_source.visible and not active_clip.visible and
		not owned_neighbor.visible and not authored_neighbor.visible and
		not neighbor.visible,
		"sculpt shows current source while all clipped references stand aside")
	preview.set_sculpt_preview_active(false)
	_expect(not active_source.visible and active_clip.visible and
		owned_neighbor.visible and authored_neighbor.visible and neighbor.visible,
		"reference visibility restores after a stroke")
	preview.clear()
	preview.queue_free()

	var undo := plugin.call("get_undo_redo") as EditorUndoRedoManager
	var tool = plugin.get("_sculpt")
	var wrong := entry.duplicate(true)
	wrong.ownership_sha256 = "b".repeat(64)
	_expect(not tool.bind(root, terrain, wrong, undo),
		"mismatched ownership boundary cannot arm the brush")
	_expect(tool.bind(root, terrain, entry, undo), "valid active scene binds")
	tool.set_enabled(true)
	var asset_plugin: Object = base_control.get_meta(&"map_asset_palette_plugin", null)
	_expect(asset_plugin != null, "asset placement plugin is active for the interlock")
	if asset_plugin != null:
		asset_plugin.set("_pending_entry", {"id": "armed-test-entry"})
		plugin.call("_on_sculpt_toggled", true)
		_expect((asset_plugin.get("_pending_entry") as Dictionary).is_empty() and
			tool.is_enabled(), "arming sculpt cancels pending asset placement")
	var dock: Object = plugin.get("_dock")
	(dock.get("_sculpt_radius") as SpinBox).value = 3.0
	(dock.get("_sculpt_strength") as SpinBox).value = 1.0
	(dock.get("_sculpt_softness") as SpinBox).value = 0.0
	var editor_viewport: SubViewport = editor_interface.call(
		"get_editor_viewport_3d", 0)
	var camera := editor_viewport.get_camera_3d() if editor_viewport != null else null
	_expect(camera != null, "the real editor 3D viewport supplies a camera")
	if camera == null:
		_finish(1)
		return
	camera.global_position = Vector3(10, 25, 18)
	camera.look_at(Vector3(10, 10, 10), Vector3.UP)
	var center := Vector3(10, 10, 10)
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = camera.unproject_position(center)
	_expect(plugin.call("_forward_3d_gui_input", camera, press) ==
		EditorPlugin.AFTER_GUI_INPUT_STOP and tool.is_dragging(),
		"real editor viewport left press hits and starts sculpt")
	var motion := InputEventMouseMotion.new()
	motion.position = camera.unproject_position(Vector3(12, 10, 10))
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	plugin.call("_forward_3d_gui_input", camera, motion)
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	release.pressed = false
	release.position = motion.position
	plugin.call("_forward_3d_gui_input", camera, release)
	var history_id := undo.get_object_history_id(root)
	var history := undo.get_history_undo_redo(history_id)
	_expect(history.has_undo() and terrain.sculpt_layer != null and
		terrain.sculpted_base_heights()[5 * GRID.x + 5] > 10.5,
		"one stroke commits one saved sparse layer")
	history.undo()
	_expect(terrain.sculpt_layer == null and
		is_equal_approx(terrain.sculpted_base_heights()[5 * GRID.x + 5], 10.0),
		"undo calls TerrainControl.apply_sculpt_layer")
	history.redo()
	_expect(terrain.sculpt_layer != null and
		terrain.sculpted_base_heights()[5 * GRID.x + 5] > 10.5,
		"redo restores the scene-specific layer")
	var idle_revision: int = terrain.preview_revision
	tool.tick(0.5)
	tool.tick(0.5)
	_expect(terrain.preview_revision == idle_revision,
		"idle preview does not rebuild after the completed stroke")
	var version_before := history.get_version()
	var protected_press := InputEventMouseButton.new()
	protected_press.button_index = MOUSE_BUTTON_LEFT
	protected_press.pressed = true
	protected_press.position = camera.unproject_position(Vector3(2, 10, 10))
	plugin.call("_forward_3d_gui_input", camera, protected_press)
	var missed_press := InputEventMouseButton.new()
	missed_press.button_index = MOUSE_BUTTON_LEFT
	missed_press.pressed = true
	missed_press.position = Vector2(-5000, -5000)
	plugin.call("_forward_3d_gui_input", camera, missed_press)
	_expect(not tool.is_dragging() and history.get_version() == version_before,
		"protected and missed terrain clicks cannot create undo actions")
	tool._start_stroke(Vector3(12, 10, 10), SETTINGS)
	var escape := InputEventKey.new()
	escape.pressed = true
	escape.keycode = KEY_ESCAPE
	_expect((plugin.call("_forward_3d_gui_input", camera, escape) if plugin != null
		else tool.handle_input(camera, escape, SETTINGS)) ==
		EditorPlugin.AFTER_GUI_INPUT_STOP and not tool.is_dragging(),
		"live plugin forwarding cancels Escape without adding history")
	var saved_after_undo: PackedFloat32Array = terrain.sculpted_base_heights()
	tool._start_stroke(Vector3(12, 10, 10), SETTINGS)
	var right := InputEventMouseButton.new()
	right.button_index = MOUSE_BUTTON_RIGHT
	right.pressed = true
	_expect(tool.handle_input(camera, right, SETTINGS) ==
		EditorPlugin.AFTER_GUI_INPUT_PASS and not tool.is_dragging(),
		"RMB navigation ends a stroke and passes camera input")
	var after_right: PackedFloat32Array = terrain.sculpted_base_heights()
	tool._start_stroke(Vector3(12, 10, 10), SETTINGS)
	tool.unbind()
	_expect(not tool.is_dragging() and terrain.sculpted_base_heights() == after_right,
		"scene switch cancels pending edits on the previous scene")
	_expect(after_right != saved_after_undo,
		"navigation finish recorded its own stroke")
	_expect(tool.bind(root, terrain, entry, undo),
		"active scene can rearm after a cancelled switch")
	tool.set_enabled(true)
	tool._start_stroke(Vector3(10, 10, 12), SETTINGS)
	tool.tick(0.2)
	_expect(not tool.is_dragging(),
		"release outside the viewport is finalized by the missing-button tick")
	tool._start_stroke(Vector3(10, 10, 10), SETTINGS)
	var save_key := InputEventKey.new()
	save_key.pressed = true
	save_key.ctrl_pressed = true
	save_key.keycode = KEY_S
	plugin.call("_input", save_key)
	_expect(not tool.is_dragging(),
		"global editor Ctrl+S flushes the in-flight stroke before saving")

	if editor_interface.call("get_edited_scene_root") != fixture_root or \
			not _is_fixture_root(fixture_root):
		_abort("the edited scene changed before saving; nothing was saved")
		return
	var save_result: Variant = editor_interface.call("save_scene")
	_expect(save_result == null or save_result == OK,
		"normal editor save writes the active sculpt scene")
	var reopened_scene := ResourceLoader.load(SCENE_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate() if reopened_scene != null else null
	var reopened_terrain: Variant = reopened.get_node_or_null("Terrain") \
		if reopened != null else null
	_expect(reopened_terrain != null and reopened_terrain.sculpt_layer != null,
		"saved sculpt layer survives scene reopen")
	_expect(FileAccess.get_file_as_bytes(ProjectSettings.globalize_path(
		HEIGHT_PATH)) == original_bytes, "sculpt never rewrites the base height grid")
	if reopened != null:
		reopened.free()
	# The editor owns the active scene; the process exit closes it.
	_cleanup()
	print("terrain sculpt editor: %d failures" % failures)
	call_deferred("_finish", 1 if failures else 0)


func _is_fixture_root(root: Variant) -> bool:
	return root is Node3D and root.get_script() == REGION and \
		String((root as Node).scene_file_path) == SCENE_PATH and \
		String(root.get("region_id")) == REGION_ID


## Stops before any further input or save, restores the shared catalog and
## removes the fixture files.
func _abort(reason: String) -> void:
	_expect(false, reason)
	_cleanup()
	print("terrain sculpt editor: aborted, %d failures" % failures)
	call_deferred("_finish", 1)


func _cleanup() -> void:
	if _plugin != null and is_instance_valid(_plugin):
		# Back to the catalog the editor reads (the shared one unless the project names another).
		_plugin.set("catalog_path",
			load("res://addons/map_authoring_workspace/territory_catalog.gd").configured_path())
		_plugin.call("_reload_sources")
	for path: String in [SCENE_PATH, HEIGHT_PATH, CATALOG_PATH, MANIFEST_PATH, SPEC_PATH]:
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))


func _write_fixture_catalog() -> void:
	var polygon := [[0, 0], [20, 0], [20, 20], [0, 20]]
	_write_json(MANIFEST_PATH, {"continentGeography": {"translation": [0, 0, 0],
		"ownershipPolygon": polygon, "revision": "sculpt-editor-fixture"},
		"asset": {"glb": "editor-world.glb"}})
	_write_json(SPEC_PATH, {"schema": "eloria-region-authoring-spec-v1",
		"regionId": REGION_ID, "label": REGION_LABEL,
		"paths": {"scene": _repository_path(SCENE_PATH), "manifest": _repository_path(MANIFEST_PATH)},
		"continentTranslation": [0, 0, 0],
		"server": {"origin": [SERVER_ORIGIN.x, SERVER_ORIGIN.y],
			"cells": [SERVER_CELLS.x, SERVER_CELLS.y],
			"collisionOriginMetres": [-SERVER_ORIGIN.x, SERVER_ORIGIN.y]},
		"terrain": {}})
	_write_json(CATALOG_PATH, {"schema": "eloria-map-authoring-territories-v1", "entries": [{
		"id": REGION_ID, "label": REGION_LABEL, "manifestPath": MANIFEST_PATH,
		"scenePath": SCENE_PATH, "authoringSpecPath": SPEC_PATH}]})


## The spec's repository-relative form of a res:// path (res:// is godot-client/).
func _repository_path(path: String) -> String:
	return "godot-client/" + path.trim_prefix("res://")


func _write_json(path: String, value: Dictionary) -> void:
	var file := FileAccess.open(ProjectSettings.globalize_path(path), FileAccess.WRITE)
	file.store_string(JSON.stringify(value, "  ") + "\n")
	file.close()


func _expect(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		push_error(description)


func _finish(code: int) -> void:
	quit(code)
