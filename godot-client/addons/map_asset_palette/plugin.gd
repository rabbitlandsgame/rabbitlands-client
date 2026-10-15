@tool
extends EditorPlugin

const Catalog := preload("res://addons/map_asset_palette/asset_catalog.gd")
const Dock := preload("res://addons/map_asset_palette/map_asset_dock.gd")
const Placement := preload("res://addons/map_asset_palette/placement.gd")
const Prefabs := preload("res://addons/map_asset_palette/prefab_library.gd")
const Markers := preload("res://addons/map_asset_palette/marker_library.gd")
const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")
const RAY_LENGTH := 2048.0
const SCULPT_PLUGIN_META := &"map_authoring_sculpt_plugin"
const ASSET_PLUGIN_META := &"map_asset_palette_plugin"
const USABILITY_PLUGIN_META := &"map_authoring_usability_plugin"
const GHOST_NAME := "__MapAssetGhost"
const GHOST_OPACITY := 0.55

var _dock: EditorDock
var _pending_entry: Dictionary = {}
var _edited_root: Node
var _ghost: Node3D
var _ghost_entry_id := ""
## Interactive adjustments while placing: turn (degrees), lift (m), size factor.
var _yaw := 0.0
var _lift := 0.0
var _size := 1.0
## Per-placement random rolls, re-rolled after each placement so the ghost
## always shows exactly what the next click will create.
var _random_yaw := 0.0
var _random_size := 1.0
var _hover_camera: Camera3D
var _hover_position := Vector2.ZERO
var _hover_dirty := false
var _hover_hit: Variant = null
var _rng := RandomNumberGenerator.new()


func _enter_tree() -> void:
	Settings.register()
	_rng.randomize()
	get_editor_interface().get_base_control().set_meta(ASSET_PLUGIN_META, self)
	_dock = Dock.new()
	_dock.configure(get_editor_interface())
	_dock.place_requested.connect(_arm_placement)
	_dock.add_at_center_requested.connect(_add_at_view_center)
	_dock.placement_cancel_requested.connect(_cancel_placement)
	_dock.save_prefab_requested.connect(save_selection_as_prefab)
	add_dock(_dock)
	set_input_event_forwarding_always_enabled()
	scene_changed.connect(_on_scene_changed)
	_on_scene_changed(get_editor_interface().get_edited_scene_root())


func _exit_tree() -> void:
	_pending_entry.clear()
	_free_ghost()
	var base := get_editor_interface().get_base_control()
	if base.has_meta(ASSET_PLUGIN_META) and base.get_meta(ASSET_PLUGIN_META) == self:
		base.remove_meta(ASSET_PLUGIN_META)
	if _dock != null:
		remove_dock(_dock)
		_dock.queue_free()
		_dock = null


func _handles(_object: Object) -> bool:
	return _pilot_root() != null


func _process(_delta: float) -> void:
	if _hover_dirty:
		_hover_dirty = false
		_refresh_hover()


func _forward_3d_gui_input(camera: Camera3D, event: InputEvent) -> int:
	var result := _viewport_input(camera, event)
	if result == EditorPlugin.AFTER_GUI_INPUT_STOP and event is InputEventKey and is_inside_tree():
		# The 3D viewport returns on STOP without accepting a key, so Godot's own
		# shortcut for it (Ctrl+G grouping, F focus, Q/E tool modes) would run too.
		get_viewport().set_input_as_handled()
	return result


func _viewport_input(camera: Camera3D, event: InputEvent) -> int:
	if _pending_entry.is_empty() or _pilot_root() == null:
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventMouseMotion:
		_hover_camera = camera
		_hover_position = (event as InputEventMouseMotion).position
		_hover_dirty = true
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventKey and event.pressed and not event.echo and \
			event.keycode == KEY_ESCAPE:
		_cancel_placement()
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	if event is InputEventKey and event.pressed:
		if _handle_adjustment_key(event as InputEventKey):
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventMouseButton and event.pressed:
		var button := event as InputEventMouseButton
		if button.shift_pressed and button.button_index in [MOUSE_BUTTON_WHEEL_UP,
				MOUSE_BUTTON_WHEEL_DOWN]:
			var step := float(Settings.value("placement/rotate_step_degrees"))
			adjust_placement(step if button.button_index == MOUSE_BUTTON_WHEEL_UP else -step)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if button.button_index == MOUSE_BUTTON_RIGHT:
			_cancel_placement()
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if button.button_index == MOUSE_BUTTON_LEFT:
			if button.alt_pressed:
				return EditorPlugin.AFTER_GUI_INPUT_PASS
			var hit := _terrain_hit(camera, button.position)
			if hit != null:
				var entry := _pending_entry.duplicate(true)
				var keep := bool(Settings.value("placement/keep_placing"))
				if not keep:
					_cancel_placement()
				_place_entry(entry, hit as Vector3, keep)
				if keep and not _pending_entry.is_empty():
					_reroll()
					_hover_camera = camera
					_hover_position = button.position
					_refresh_hover()
			else:
				_dock.show_message("That ray did not hit the authored terrain. Choose another point.")
			return EditorPlugin.AFTER_GUI_INPUT_STOP
	return EditorPlugin.AFTER_GUI_INPUT_PASS


## The placement hint lines, top first; empty when not placing. The Map
## Authoring Usability plugin draws these on every 3D view (it force-draws, so
## they show with nothing selected); this plugin only draws them itself when that
## plugin is disabled.
func overlay_lines() -> PackedStringArray:
	if _pending_entry.is_empty() or _pilot_root() == null:
		return PackedStringArray()
	return PackedStringArray([
		"Placing %s  ·  turn %s°  ·  lift %+.2f m  ·  size %d%%%s%s" % [
			String(_pending_entry.get("label", "asset")), _format_degrees(_total_yaw()),
			_lift, roundi(_total_size() * 100.0),
			"  ·  snap %s m" % _format_metres(float(Settings.value("grid/step"))) \
				if bool(Settings.value("placement/snap_to_grid")) else "",
			"  ·  off terrain" if _hover_hit == null else ""],
		"Click: place  ·  Right-click / Esc: stop  ·  %s/%s or Shift+wheel: turn  ·  %s/%s: raise  ·  %s/%s: size  ·  Shift: fine  ·  %s: reset  ·  %s: snap" % [
			Settings.shortcut_text("rotate_left"), Settings.shortcut_text("rotate_right"),
			Settings.shortcut_text("raise"), Settings.shortcut_text("lower"),
			Settings.shortcut_text("scale_up"), Settings.shortcut_text("scale_down"),
			Settings.shortcut_text("reset"), Settings.shortcut_text("toggle_snap")],
	])


func _forward_3d_draw_over_viewport(overlay: Control) -> void:
	if get_editor_interface().get_base_control().has_meta(USABILITY_PLUGIN_META):
		return
	draw_overlay_lines(overlay, overlay_lines(), overlay.size.y)


## Draws hint lines as dark strips stacked upwards from `bottom`, the first line
## highlighted. Shared with the Map Authoring Usability plugin.
static func draw_overlay_lines(overlay: Control, lines: PackedStringArray, bottom: float) -> void:
	var font := overlay.get_theme_default_font()
	var font_size := overlay.get_theme_default_font_size()
	var line_height := font.get_height(font_size) + 6.0
	for index in lines.size():
		var text: String = lines[lines.size() - 1 - index]
		var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
		var top := bottom - line_height * float(index + 1)
		overlay.draw_rect(Rect2(8.0, top, width + 16.0, line_height), Color(0, 0, 0, 0.55))
		overlay.draw_string(font, Vector2(16.0, top + line_height - 8.0), text,
			HORIZONTAL_ALIGNMENT_LEFT, -1, font_size,
			Color(1.0, 0.86, 0.45) if index == lines.size() - 1 else Color(0.92, 0.94, 0.97))


## Adds to the interactive turn (degrees), lift (metres) and size (factor delta).
func adjust_placement(yaw_degrees: float = 0.0, lift: float = 0.0, size_delta: float = 0.0) -> void:
	_yaw = wrapf(_yaw + yaw_degrees, -180.0, 180.0)
	_lift += lift
	_size = clampf(_size + size_delta, 0.05, 20.0)
	_refresh_hover()


func reset_placement_adjustments() -> void:
	_yaw = 0.0
	_lift = 0.0
	_size = 1.0
	_refresh_hover()


func placement_state() -> Dictionary:
	return {"yaw": _yaw, "lift": _lift, "size": _size, "random_yaw": _random_yaw,
		"random_size": _random_size, "armed": not _pending_entry.is_empty(),
		"ghost": _ghost if is_instance_valid(_ghost) else null, "hover": _hover_hit}


## Saves the current selection as a prefab and refreshes the library.
func save_selection_as_prefab(prefab_name: String) -> Dictionary:
	var root := _pilot_root()
	if root == null:
		_dock.show_message("Open a map authoring scene before saving a prefab.")
		return {}
	var name := prefab_name.strip_edges()
	var selection := get_editor_interface().get_selection().get_selected_nodes()
	if name.is_empty():
		var members := Prefabs.capturable(root, selection)
		name = "%s group" % String(members[0].name) if not members.is_empty() else ""
	var result := Prefabs.save_selection(root, selection, name)
	if result.has("error"):
		_dock.show_message(String(result.error))
		return result
	get_editor_interface().get_resource_filesystem().update_file(String(result.path))
	_dock.clear_prefab_name()
	_dock.reload_library()
	_dock.select_entry_by_id(String(result.id))
	var note := ""
	var left_markers := int(result.get("left_out_markers", 0))
	var left_other := int(result.get("left_out_other", 0))
	if left_markers + left_other > 0:
		note = " Left out %s (prefabs hold placed assets and gameplay markers)." % ", ".join(PackedStringArray(
			(["%d gameplay marker%s" % [left_markers, "" if left_markers == 1 else "s"]]
				if left_markers > 0 else []) +
			(["%d other object%s" % [left_other, "" if left_other == 1 else "s"]]
				if left_other > 0 else [])))
	var marker_count := int(result.get("markers", 0))
	_dock.show_message("Saved prefab %s with %d assets%s.%s Select it and click Place on terrain." % [
		String(result.path).get_file(), int(result.members) - marker_count,
		" and %d marker%s" % [marker_count, "" if marker_count == 1 else "s"] if marker_count > 0 else "",
		note])
	return result


func _handle_adjustment_key(event: InputEventKey) -> bool:
	var fine := event.shift_pressed
	if Settings.matches("rotate_left", event) or Settings.matches("rotate_right", event):
		var step := float(Settings.value("placement/fine_rotate_step_degrees" if fine \
			else "placement/rotate_step_degrees"))
		adjust_placement(step if Settings.matches("rotate_left", event) else -step)
		return true
	if Settings.matches("raise", event) or Settings.matches("lower", event):
		var step := float(Settings.value("placement/fine_lift_step" if fine \
			else "placement/lift_step"))
		adjust_placement(0.0, step if Settings.matches("raise", event) else -step)
		return true
	if Settings.matches("scale_up", event) or Settings.matches("scale_down", event):
		var step := float(Settings.value("placement/fine_scale_step" if fine \
			else "placement/scale_step"))
		adjust_placement(0.0, 0.0, step if Settings.matches("scale_up", event) else -step)
		return true
	if Settings.matches("reset", event):
		reset_placement_adjustments()
		return true
	if Settings.matches("toggle_snap", event) and not event.echo:
		Settings.set_value("placement/snap_to_grid",
			not bool(Settings.value("placement/snap_to_grid")))
		_dock.sync_options()
		_refresh_hover()
		return true
	return false


func _arm_placement(entry: Dictionary) -> void:
	if _pilot_root() == null:
		_dock.show_message("Open a map authoring scene before placing assets.")
		return
	var base := get_editor_interface().get_base_control()
	var sculpt_plugin: Variant = null
	if base.has_meta(SCULPT_PLUGIN_META):
		sculpt_plugin = base.get_meta(SCULPT_PLUGIN_META)
	if sculpt_plugin is Object and is_instance_valid(sculpt_plugin) and \
			sculpt_plugin.has_method("deactivate_terrain_sculpt"):
		sculpt_plugin.call("deactivate_terrain_sculpt")
	if base.has_meta(USABILITY_PLUGIN_META):
		var usability: Variant = base.get_meta(USABILITY_PLUGIN_META)
		if usability is Object and is_instance_valid(usability) and \
				usability.has_method("cancel_path_drawing"):
			usability.call("cancel_path_drawing")
	_pending_entry = entry.duplicate(true)
	_hover_hit = null
	_yaw = 0.0
	_lift = 0.0
	_size = 1.0
	_reroll()
	_dock.set_placement_armed(true, String(entry.label))
	get_editor_interface().set_main_screen_editor("3D")
	update_overlays()


func _cancel_placement() -> void:
	_pending_entry.clear()
	_hover_hit = null
	_free_ghost()
	if _dock != null:
		_dock.set_placement_armed(false)
	if is_inside_tree():
		update_overlays()


func cancel_placement_for_terrain_sculpt() -> void:
	_cancel_placement()


func _add_at_view_center(entry: Dictionary) -> void:
	_cancel_placement()
	_yaw = 0.0
	_lift = 0.0
	_size = 1.0
	_reroll()
	var viewport := get_editor_interface().get_editor_viewport_3d(0)
	var camera := viewport.get_camera_3d() if viewport != null else null
	if camera == null:
		_dock.show_message("Open the 3D view before adding an asset at its center.")
		return
	var hit := _terrain_hit(camera, viewport.get_visible_rect().size * 0.5)
	if hit == null:
		_dock.show_message("The center of the 3D view does not hit the authored terrain.")
		return
	_place_entry(entry, hit as Vector3)


func _terrain_hit(camera: Camera3D, screen_position: Vector2) -> Variant:
	var pilot := _pilot_root()
	if pilot == null:
		return null
	var origin := camera.project_ray_origin(screen_position)
	var direction := camera.project_ray_normal(screen_position)
	return Probe.ray_hit(pilot, origin, direction, RAY_LENGTH)


## Applies grid snapping in territory-local metres and re-reads the ground there.
func _snapped_ground(root: Node3D, hit: Vector3) -> Vector3:
	if not bool(Settings.value("placement/snap_to_grid")):
		return hit
	var step := float(Settings.value("grid/step"))
	if step <= 0.0:
		return hit
	var local: Vector3 = root.global_transform.affine_inverse() * hit
	local.x = roundf(local.x / step) * step
	local.z = roundf(local.z / step) * step
	var world: Vector3 = root.global_transform * local
	var height := Probe.height_at(root, world)
	return Vector3(world.x, height if not is_nan(height) else hit.y, world.z)


func _surface_normal(root: Node3D, ground: Vector3) -> Vector3:
	if not bool(Settings.value("placement/align_to_surface")):
		return Vector3.UP
	return Probe.normal_at(root, ground)


func _total_yaw() -> float:
	return wrapf(_yaw + _random_yaw, -180.0, 180.0)


func _total_size() -> float:
	return _size * _random_size


func _reroll() -> void:
	_random_yaw = _rng.randf_range(-180.0, 180.0) \
		if bool(Settings.value("placement/random_rotation")) else 0.0
	var variation := clampf(float(Settings.value("placement/size_variation")), 0.0, 0.9)
	_random_size = _rng.randf_range(1.0 - variation, 1.0 + variation) if variation > 0.0 else 1.0


func _refresh_hover() -> void:
	var root := _pilot_root()
	if _pending_entry.is_empty() or root == null:
		return
	if _hover_camera == null or not is_instance_valid(_hover_camera):
		update_overlays()
		return
	var hit: Variant = _terrain_hit(_hover_camera, _hover_position)
	_hover_hit = hit
	if hit == null:
		if is_instance_valid(_ghost):
			_ghost.visible = false
		update_overlays()
		return
	var ghost := _ensure_ghost(root)
	if ghost != null:
		ghost.visible = true
		var ground := _snapped_ground(root, hit as Vector3)
		if Markers.is_marker_entry(_pending_entry):
			ghost.global_transform = Transform3D(Basis(Vector3.UP, deg_to_rad(_total_yaw())),
				ground + Vector3.UP * _lift)
		elif Prefabs.is_prefab_entry(_pending_entry):
			var pivot := _prefab_pivot(ground)
			for member_value in ghost.get_children():
				var member := member_value as Node3D
				if member != null and member.has_meta(&"ghost_rest"):
					member.transform = member.get_meta(&"ghost_rest")
					var world := Prefabs.member_world_transform(root, member, pivot, true, _lift)
					member.transform = pivot.affine_inverse() * world
			ghost.global_transform = pivot
		else:
			# Recompute from the rest pose every time so turns and sizes never compound.
			ghost.transform = Transform3D(ghost.get_meta(&"ghost_rest_basis", Basis.IDENTITY),
				Vector3.ZERO)
			ghost.global_transform = Placement.adjusted_ground_transform(ghost, _pending_entry,
				ground, _total_yaw(), _lift, _total_size(), _surface_normal(root, ground))
	update_overlays()


func _ensure_ghost(root: Node3D) -> Node3D:
	var entry_id := String(_pending_entry.get("id", ""))
	if is_instance_valid(_ghost) and _ghost_entry_id == entry_id and _ghost.get_parent() == root:
		return _ghost
	_free_ghost()
	var node: Node3D
	if Markers.is_marker_entry(_pending_entry):
		node = Markers.pin_node(String(_pending_entry.get("marker_kind", "")))
	elif Prefabs.is_prefab_entry(_pending_entry):
		var created := Prefabs.instantiate(_pending_entry)
		node = created.get("node") as Node3D
		if node != null:
			for member_value in node.get_children():
				if member_value is Node3D:
					(member_value as Node3D).set_meta(&"ghost_rest", (member_value as Node3D).transform)
	else:
		var created := Placement.instantiate_entry(_pending_entry)
		node = created.get("node") as Node3D
		if node != null and root.has_method("prepare_palette_asset"):
			# Mirror the wrapper a region commit creates (identity holder + Content)
			# without the asset script, so the ghost lands exactly where the click will.
			var holder := Node3D.new()
			holder.add_child(node)
			node.name = "Content"
			node = holder
	if node == null:
		return null
	node.set_meta(&"ghost_rest_basis", node.transform.basis)
	node.name = GHOST_NAME
	Placement.make_ghost(node, GHOST_OPACITY)
	# Internal and ownerless: never saved, never listed in the Scene dock.
	root.add_child(node, false, Node.INTERNAL_MODE_BACK)
	_ghost = node
	_ghost_entry_id = entry_id
	return _ghost


func _free_ghost() -> void:
	if is_instance_valid(_ghost):
		if _ghost.get_parent() != null:
			_ghost.get_parent().remove_child(_ghost)
		_ghost.queue_free()
	_ghost = null
	_ghost_entry_id = ""


func _prefab_pivot(ground: Vector3) -> Transform3D:
	var basis := Basis(Vector3.UP, deg_to_rad(_total_yaw())).scaled(Vector3.ONE * _total_size())
	return Transform3D(basis, ground + Vector3.UP * _lift)


func _place_entry(entry: Dictionary, ground_position: Vector3, keep_armed: bool = false) -> Node3D:
	var pilot := _pilot_root()
	if pilot == null:
		return null
	var ground := _snapped_ground(pilot, ground_position)
	if Markers.is_marker_entry(entry):
		return _place_marker(pilot, entry, ground, keep_armed)
	if Prefabs.is_prefab_entry(entry):
		return _place_prefab(pilot, entry, ground, keep_armed)
	var created := Placement.instantiate_entry(entry)
	var node := created.get("node") as Node3D
	if node == null:
		_dock.show_message(String(created.get("error", "The selected asset could not be loaded.")))
		return null
	if pilot.has_method("prepare_palette_asset"):
		node = pilot.call("prepare_palette_asset", entry, node) as Node3D
		if node == null:
			_dock.show_message("The authoring region could not prepare this asset.")
			return null
	var transform := Placement.adjusted_ground_transform(node, entry, ground, _total_yaw(), _lift,
		_total_size(), _surface_normal(pilot, ground))
	var placed := Placement.commit_with_undo(get_undo_redo(), pilot, entry, node,
		bool(created.get("starter", false)), transform)
	if placed == null:
		node.free()
		_dock.show_message("Could not create the saved AuthoredAssets container.")
		return null
	_select_placed([placed])
	_dock.show_message(("Placed %s. Keep clicking to place more; right-click or Escape stops." \
		if keep_armed else "Placed %s. Use the normal move, rotate, and scale tools.") %
		String(entry.label))
	return placed


func _place_prefab(pilot: Node3D, entry: Dictionary, ground: Vector3, keep_armed: bool) -> Node3D:
	var created := Prefabs.instantiate(entry)
	var prefab := created.get("node") as Node3D
	if prefab == null:
		_dock.show_message(String(created.get("error", "The prefab could not be loaded.")))
		return null
	var placed := Prefabs.commit_with_undo(get_undo_redo(), pilot, prefab, _prefab_pivot(ground),
		true, _lift, String(entry.label))
	if placed.is_empty():
		_dock.show_message("The prefab %s has no assets to place." % String(entry.label))
		return null
	_select_placed(placed)
	var review := Markers.copy_review_note(placed)
	_dock.show_message("Placed prefab %s (%d members)%s%s" % [String(entry.label), placed.size(),
		". Keep clicking to place more." if keep_armed else ".",
		" " + review + "." if not review.is_empty() else ""])
	return placed[0]


## Gameplay markers stand at the ground (plus any lift); Q/E turn their facing.
func _place_marker(root: Node3D, entry: Dictionary, ground: Vector3, keep_armed: bool) -> Node3D:
	if root.get_node_or_null(Markers.GAMEPLAY) == null:
		_dock.show_message("This scene has no Gameplay container for markers.")
		return null
	var facing := Basis(Vector3.UP, deg_to_rad(_total_yaw())) * Vector3.FORWARD
	var marker := Markers.create_marker(root, entry, ground + Vector3.UP * _lift, facing)
	Markers.commit_with_undo(get_undo_redo(), root, marker)
	_select_placed([marker])
	var kind := String(entry.get("marker_kind", ""))
	var reminder := " Set its Destination Map and Destination Spawn in the Inspector." \
		if kind == "portal" else " Name it in the Inspector." if kind == "npc_marker" else ""
	_dock.show_message("Placed %s marker %s.%s%s" % [kind, String(marker.get("record_id")),
		reminder, " Keep clicking to place more." if keep_armed else ""])
	return marker


func _select_placed(nodes: Array[Node3D]) -> void:
	var selection := get_editor_interface().get_selection()
	selection.clear()
	for node in nodes:
		selection.add_node(node)
	if nodes.size() == 1:
		get_editor_interface().edit_node(nodes[0])
	get_editor_interface().set_main_screen_editor("3D")


func _on_scene_changed(scene_root: Node) -> void:
	_edited_root = scene_root
	_cancel_placement()
	if _dock != null:
		_dock.set_scene_available(_pilot_root() != null)
		_dock.set_territory_entries(Catalog.territory_entries(_pilot_root()))
		_dock.set_marker_entries(Markers.entries(_pilot_root()))


func _pilot_root() -> Node3D:
	var root := get_editor_interface().get_edited_scene_root() if is_inside_tree() else _edited_root
	if root is Node3D and root.has_method("authoring_ground_intersection"):
		return root as Node3D
	return null


static func _format_degrees(value: float) -> String:
	return str(roundi(value)) if absf(value - roundf(value)) < 0.05 else "%.1f" % value


static func _format_metres(value: float) -> String:
	return str(snappedf(value, 0.001)).trim_suffix(".0")
