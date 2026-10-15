extends SceneTree

const PILOT_PATH := "res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn"
const RELOAD_PATH := "res://src/dev/map_authoring_pilot/.asset-placement-reload.tscn"
const Catalog := preload("res://addons/map_asset_palette/asset_catalog.gd")
const Placement := preload("res://addons/map_asset_palette/placement.gd")
const Dock := preload("res://addons/map_asset_palette/map_asset_dock.gd")
const Plugin := preload("res://addons/map_asset_palette/plugin.gd")
const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	if not Engine.is_editor_hint():
		push_error("map asset placement test requires --editor")
		quit(1)
		return
	var editor_interface: Object = Engine.get_singleton("EditorInterface")
	editor_interface.call("open_scene_from_path", PILOT_PATH)
	await process_frame
	await process_frame
	var editor_base := editor_interface.call("get_base_control") as Control
	_expect(bool(editor_interface.call("is_plugin_enabled", "map_asset_palette")) and
		editor_base.find_child("MapAssets", true, false) != null,
		"project plugin configuration loads the Map Assets EditorDock")
	var pilot := editor_interface.call("get_edited_scene_root") as Node3D
	_expect(pilot != null and pilot.has_node("AuthoredAssets"),
		"pilot opens with the saved AuthoredAssets container")
	if pilot == null:
		_finish()
		return
	var baseline_grid: PackedByteArray = pilot.call("server_grid")
	var ground_hit: Variant = _test_exact_terrain_ray(pilot)
	if ground_hit == null:
		_finish()
		return
	var entries := Catalog.entries()
	var native_entry := _entry(entries, "mirror_reed")
	var starter_entry := _entry(entries, "starter:shore_rock_west")
	var undo_manager := editor_interface.call("get_editor_undo_redo") as EditorUndoRedoManager
	var original_assets := pilot.get_node("AuthoredAssets")
	pilot.remove_child(original_assets)
	original_assets.free()
	var native := _place(undo_manager, pilot, native_entry, ground_hit as Vector3)
	_test_native_placement(pilot, native_entry, native, ground_hit as Vector3)
	_test_native_undo_redo(undo_manager, pilot, native)
	var second_hit: Variant = pilot.call("authoring_ground_intersection",
		Vector3(11.5, 30.0, -8.5), Vector3.DOWN, 60.0)
	_expect(second_hit != null, "second placement ray reaches the terrain")
	if second_hit == null:
		_finish()
		return
	var starter := _place(undo_manager, pilot, starter_entry, second_hit as Vector3)
	_test_starter_placement(pilot, starter_entry, starter, second_hit as Vector3)
	await _test_plugin_forwarding(pilot, native_entry, ground_hit as Vector3)
	var native_id := native.get_instance_id()
	var starter_id := starter.get_instance_id()
	pilot.call("refresh_all")
	_expect(native.get_instance_id() == native_id and starter.get_instance_id() == starter_id and
		pilot.get_node("AuthoredAssets").is_ancestor_of(native) and
		pilot.get_node("AuthoredAssets").is_ancestor_of(starter),
		"preview regeneration leaves authored library instances untouched")
	_expect((pilot.call("server_grid") as PackedByteArray) == baseline_grid,
		"placed visual assets do not change walking or export collision")
	await _test_save_reload(pilot, native_entry, starter_entry)
	await _test_dock_ui()
	_finish()


func _test_exact_terrain_ray(pilot: Node3D) -> Variant:
	var terrain := pilot.get_node("GeneratedPreview/Terrain/TerrainMesh") as MeshInstance3D
	var faces := terrain.mesh.get_faces()
	var steep_index := -1
	var steep_delta := -1.0
	for index in range(0, faces.size() - 2, 3):
		var low := minf(faces[index].y, minf(faces[index + 1].y, faces[index + 2].y))
		var high := maxf(faces[index].y, maxf(faces[index + 1].y, faces[index + 2].y))
		if high - low > steep_delta:
			steep_delta = high - low
			steep_index = index
	var local_center := (faces[steep_index] + faces[steep_index + 1] +
		faces[steep_index + 2]) / 3.0
	var expected := terrain.global_transform * local_center
	var hit: Variant = pilot.call("authoring_ground_intersection",
		expected + Vector3.UP * 20.0, Vector3.DOWN, 40.0)
	_expect(steep_delta >= 0.19 and hit != null and
		(hit as Vector3).distance_to(expected) < 0.002,
		"terrain rays hit the actual quantized triangle on a steep bank")
	_expect(pilot.call("authoring_ground_intersection", expected, Vector3.RIGHT, 5.0) == null,
		"terrain rays reject a segment that never meets a triangle")
	return hit


func _place(undo_manager: EditorUndoRedoManager, pilot: Node3D,
		entry: Dictionary, ground_hit: Vector3) -> Node3D:
	var created := Placement.instantiate_entry(entry)
	var node := created.get("node") as Node3D
	if node == null:
		_expect(false, "catalog entry instantiates: %s" % entry.id)
		return null
	var transform := Placement.ground_transform(node, entry, ground_hit)
	return Placement.commit_with_undo(undo_manager, pilot, entry, node,
		bool(created.get("starter", false)), transform)


func _test_native_placement(pilot: Node3D, entry: Dictionary, node: Node3D,
		ground_hit: Vector3) -> void:
	if node == null:
		_expect(false, "native scene is placed")
		return
	var bounds_result := Placement.mesh_bounds(node)
	var world_bounds := Transform3D(node.global_transform.basis, Vector3.ZERO) * \
		(bounds_result.bounds as AABB)
	var linked_descendants := node.find_children("*", "Node", true, false)
	_expect(node.get_parent() == pilot.get_node("AuthoredAssets") and node.owner == pilot and
		node.scene_file_path == entry.scene_path and
		linked_descendants.all(func(child: Node) -> bool: return child.owner != pilot),
		"native GLB stays a linked scene instance instead of being flattened")
	_expect(absf(world_bounds.size.y - float(entry.height)) < 0.002 and
		absf(node.global_position.y + world_bounds.position.y - ground_hit.y) < 0.002,
		"catalog height sets native scale and the visible bounds sit on terrain")


func _test_native_undo_redo(undo_manager: EditorUndoRedoManager,
		pilot: Node3D, node: Node3D) -> void:
	var history_id := undo_manager.get_object_history_id(pilot)
	var history := undo_manager.get_history_undo_redo(history_id)
	var saved_transform := node.global_transform
	history.undo()
	var removed := not node.is_inside_tree() and not pilot.has_node("AuthoredAssets")
	history.redo()
	_expect(removed and node.is_inside_tree() and node.global_transform == saved_transform and
		node.owner == pilot and pilot.has_node("AuthoredAssets"),
		"native undo removes an old pilot's new container and redo restores it with the asset")


func _test_starter_placement(pilot: Node3D, entry: Dictionary, node: Node3D,
		ground_hit: Vector3) -> void:
	if node == null:
		_expect(false, "starter scene is placed")
		return
	var bounds_result := Placement.mesh_bounds(node)
	var world_bounds := Transform3D(node.global_transform.basis, Vector3.ZERO) * \
		(bounds_result.bounds as AABB)
	var original := pilot.get_node("AuthoredScenery/ShoreRockWest")
	_expect(node.scene_file_path.is_empty() and node.owner == pilot and
		node.find_children("*", "Node", true, false).all(
			func(child: Node) -> bool: return child.owner == pilot) and
		node.get("surface") != original.get("surface"),
		"starter is an editable saved subtree with an independent local Surface")
	_expect(absf(node.global_position.y + world_bounds.position.y - ground_hit.y) < 0.002,
		"starter keeps its authored scale and rests its visible bounds on terrain")
	var preview_scene := Placement.preview_scene(entry)
	var preview_root := preview_scene.instantiate()
	_expect(preview_root.name == node.name and preview_root.find_child("ShoreRockEast") == null,
		"starter preview packs only the selected subtree")
	preview_root.free()


func _test_save_reload(pilot: Node3D, native_entry: Dictionary,
		starter_entry: Dictionary) -> void:
	var packed := PackedScene.new()
	_expect(packed.pack(pilot) == OK and ResourceSaver.save(packed, RELOAD_PATH) == OK,
		"scene with placed assets saves")
	var reopened := (load(RELOAD_PATH) as PackedScene).instantiate()
	root.add_child(reopened)
	await process_frame
	var assets := reopened.get_node("AuthoredAssets")
	var native := _child_with_meta(assets, "map_asset_id", native_entry.id) as Node3D
	var starter := _child_with_meta(assets, "map_asset_id", starter_entry.id) as Node3D
	_expect(native != null and starter != null and native.scene_file_path == native_entry.scene_path and
		starter.scene_file_path.is_empty() and native.owner == reopened and starter.owner == reopened,
		"save and reopen preserves linked native identity and the local starter")
	reopened.queue_free()
	await process_frame


func _test_plugin_forwarding(pilot: Node3D, entry: Dictionary,
		ground_hit: Vector3) -> void:
	var plugin := Plugin.new()
	root.add_child(plugin)
	await process_frame
	plugin.call("_arm_placement", entry)
	var camera := Camera3D.new()
	pilot.add_child(camera)
	camera.global_position = ground_hit + Vector3.UP * 30.0
	camera.look_at(ground_hit, Vector3.FORWARD)
	var screen_center := camera.get_viewport().get_visible_rect().size * 0.5
	var escape := InputEventKey.new()
	escape.keycode = KEY_ESCAPE
	escape.pressed = true
	var escape_result: int = plugin.call("_forward_3d_gui_input", camera, escape)
	var escaped: bool = escape_result == EditorPlugin.AFTER_GUI_INPUT_STOP and \
		(plugin.get("_pending_entry") as Dictionary).is_empty()
	plugin.call("_arm_placement", entry)
	var alt_click := InputEventMouseButton.new()
	alt_click.button_index = MOUSE_BUTTON_LEFT
	alt_click.pressed = true
	alt_click.alt_pressed = true
	alt_click.position = screen_center
	var before_count := pilot.get_node("AuthoredAssets").get_child_count()
	var alt_result: int = plugin.call("_forward_3d_gui_input", camera, alt_click)
	var alt_passed: bool = alt_result == EditorPlugin.AFTER_GUI_INPUT_PASS and \
		not (plugin.get("_pending_entry") as Dictionary).is_empty() and \
		pilot.get_node("AuthoredAssets").get_child_count() == before_count
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = screen_center
	var click_result: int = plugin.call("_forward_3d_gui_input", camera, click)
	var plugin_dock: Object = plugin.get("_dock")
	# "Keep placing" (on by default) leaves placement armed after a click.
	var keep_placing := bool(Settings.value("placement/keep_placing"))
	_expect(escaped and alt_passed and click_result == EditorPlugin.AFTER_GUI_INPUT_STOP and
		(plugin.get("_pending_entry") as Dictionary).is_empty() != keep_placing and
		pilot.get_node("AuthoredAssets").get_child_count() == before_count + 1 and
		String(plugin_dock.call("status_text")).begins_with("Placed"),
		"real plugin forwarding cancels Escape, passes Alt orbit, and places on left-click")
	plugin.call("_cancel_placement")
	camera.queue_free()
	plugin.queue_free()
	await process_frame


func _test_dock_ui() -> void:
	var dock := Dock.new()
	root.add_child(dock)
	dock.size = Vector2(360.0, 720.0)
	dock.configure(null)
	dock.set_scene_available(true)
	dock.select_category("Starter scenery")
	dock.set_search_query("shore rock west")
	var ids := dock.visible_entry_ids()
	var selected := dock.select_entry_by_id("starter:shore_rock_west")
	var state := {"cancel_count": 0}
	dock.placement_cancel_requested.connect(func() -> void: state.cancel_count += 1)
	dock.set_placement_armed(true, "Shore Rock West")
	dock.set_search_query("shore rock")
	var changed_selection_cancelled: bool = state.cancel_count == 1
	dock.set_placement_armed(true, "Shore Rock West")
	dock.cancel_placement()
	dock.call("_reload_entries", true)
	var refreshed_selected := dock.select_entry_by_id("starter:shore_rock_west")
	dock.set_placement_armed(true, "Shore Rock West")
	await process_frame
	_expect(ids == PackedStringArray(["starter:shore_rock_west"]) and selected and
		refreshed_selected and String(dock.selected_entry().id) == "starter:shore_rock_west" and
		changed_selection_cancelled and state.cancel_count == 2,
		"search changes and Cancel disarm placement without leaving a stale asset")
	_expect(dock.has_usable_layout(),
		"native EditorDock keeps every visible control, including Cancel, inside a normal sidebar")
	dock.cancel_placement()
	dock.queue_free()
	await process_frame


func _entry(entries: Array[Dictionary], id: String) -> Dictionary:
	for entry in entries:
		if entry.id == id:
			return entry
	return {}


func _child_with_meta(parent: Node, key: StringName, value: Variant) -> Node:
	for child in parent.get_children():
		if child.get_meta(key, null) == value:
			return child
	return null


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false


func _finish() -> void:
	for path in [RELOAD_PATH, RELOAD_PATH + ".uid"]:
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	print("map asset placement editor: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)
