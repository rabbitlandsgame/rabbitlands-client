@tool
extends RefCounted

const CONTAINER_NAME := "AuthoredAssets"
const MIN_AUTO_SCALE := 0.05
const MAX_AUTO_SCALE := 20.0


static func instantiate_entry(entry: Dictionary) -> Dictionary:
	var scene_path := String(entry.get("scene_path", ""))
	var source_node := String(entry.get("source_node", ""))
	var packed := load(scene_path) as PackedScene
	if packed == null:
		return {"error": "Could not load %s." % scene_path}
	var result: Node3D
	var is_starter := not source_node.is_empty()
	if is_starter:
		var template := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
		if template == null:
			return {"error": "Could not open starter scene %s." % scene_path}
		var source := template.get_node_or_null(NodePath(source_node))
		if source is Node3D:
			result = source.duplicate() as Node3D
		template.free()
		if result == null:
			return {"error": "Starter node %s is missing." % source_node}
	else:
		result = packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
		if result == null:
			return {"error": "%s does not have a Node3D root." % scene_path}
	result.name = _safe_node_name(String(entry.get("label", result.name)))
	result.set_meta(&"map_asset_id", String(entry.get("id", "")))
	result.set_meta(&"map_asset_scene", scene_path)
	if is_starter:
		result.set_meta(&"map_asset_source_node", source_node)
	return {"node": result, "starter": is_starter}


static func ground_transform(node: Node3D, entry: Dictionary,
		ground_position: Vector3) -> Transform3D:
	var transform := Transform3D(node.transform.basis, ground_position)
	var bounds_result := mesh_bounds(node)
	if not bool(bounds_result.get("valid", false)):
		return transform
	var local_bounds: AABB = bounds_result.bounds
	var oriented := Transform3D(transform.basis, Vector3.ZERO) * local_bounds
	var desired_height := float(entry.get("height", 0.0))
	if String(entry.get("source_node", "")).is_empty() and desired_height > 0.0 and \
			oriented.size.y > 0.0001:
		var factor := desired_height / oriented.size.y
		if is_finite(factor) and factor >= MIN_AUTO_SCALE and factor <= MAX_AUTO_SCALE:
			transform.basis = transform.basis.scaled(Vector3.ONE * factor)
		else:
			push_warning(("Map asset '%s' kept its authored scale because the catalog height " +
				"would require an unsafe scale factor.") % String(entry.get("label", node.name)))
		oriented = Transform3D(transform.basis, Vector3.ZERO) * local_bounds
	transform.origin.y = ground_position.y - oriented.position.y
	return transform


## ground_transform plus the interactive placement adjustments: an extra turn
## about world up, a lift above the ground, a size multiplier on top of the
## catalog height, and an optional tilt so the asset's up follows `surface_normal`.
## With the defaults it matches ground_transform.
static func adjusted_ground_transform(node: Node3D, entry: Dictionary,
		ground_position: Vector3, yaw_degrees: float = 0.0, lift: float = 0.0,
		size: float = 1.0, surface_normal: Vector3 = Vector3.UP) -> Transform3D:
	var grounded := ground_transform(node, entry, ground_position)
	var basis := grounded.basis
	if absf(yaw_degrees) > 0.0:
		basis = Basis(Vector3.UP, deg_to_rad(yaw_degrees)) * basis
	if is_finite(size) and size > 0.0 and absf(size - 1.0) > 0.0:
		basis = basis.scaled(Vector3.ONE * size)
	var up := surface_normal.normalized()
	if up.is_finite() and up.y > 0.0 and up.dot(Vector3.UP) < 0.99999:
		basis = Basis(Quaternion(Vector3.UP, up)) * basis
	var transform := Transform3D(basis, ground_position)
	var bounds_result := mesh_bounds(node)
	if bool(bounds_result.get("valid", false)):
		var oriented := Transform3D(basis, Vector3.ZERO) * (bounds_result.bounds as AABB)
		transform.origin.y = ground_position.y - oriented.position.y
	else:
		transform.origin.y = grounded.origin.y
	transform.origin.y += lift
	return transform


## Makes an unsaved stand-in look like a ghost: see-through with a faint blue
## tint, no shadows, and no lights or physics, so previews never mutate anything.
## Materials are per-ghost copies on surface overrides (GeometryInstance3D
## transparency alone does nothing in the Compatibility renderer).
static func make_ghost(node: Node3D, opacity: float = 0.5) -> void:
	var nodes: Array[Node] = [node]
	nodes.append_array(_descendants(node))
	var fallback := StandardMaterial3D.new()
	fallback.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	fallback.albedo_color = Color(0.7, 0.88, 1.0, opacity)
	fallback.cull_mode = BaseMaterial3D.CULL_DISABLED
	for descendant in nodes:
		if descendant is MeshInstance3D and (descendant as MeshInstance3D).mesh != null:
			var mesh_node := descendant as MeshInstance3D
			for index in mesh_node.mesh.get_surface_count():
				mesh_node.set_surface_override_material(index,
					_ghost_material(mesh_node.get_active_material(index), opacity, fallback))
		elif descendant is GeometryInstance3D:
			(descendant as GeometryInstance3D).material_override = fallback
		if descendant is GeometryInstance3D:
			var geometry := descendant as GeometryInstance3D
			geometry.transparency = clampf(1.0 - opacity, 0.0, 1.0)
			geometry.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if descendant is Light3D:
			(descendant as Light3D).visible = false
		if descendant is CollisionObject3D:
			(descendant as CollisionObject3D).process_mode = Node.PROCESS_MODE_DISABLED


static func _ghost_material(source: Material, opacity: float,
		fallback: StandardMaterial3D) -> Material:
	if not source is BaseMaterial3D:
		return fallback
	var copy := (source as BaseMaterial3D).duplicate() as BaseMaterial3D
	copy.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	var tinted := copy.albedo_color.lerp(Color(0.7, 0.88, 1.0), 0.3)
	tinted.a = copy.albedo_color.a * opacity
	copy.albedo_color = tinted
	return copy


static func mesh_bounds(root: Node3D) -> Dictionary:
	var state := {"valid": false, "bounds": AABB()}
	_collect_mesh_bounds(root, Transform3D.IDENTITY, true, state)
	return state


static func commit_with_undo(undo_redo: EditorUndoRedoManager, scene_root: Node,
		entry: Dictionary, node: Node3D, starter: bool,
		world_transform: Transform3D) -> Node3D:
	if undo_redo == null or scene_root == null or node == null:
		return null
	var container := scene_root.get_node_or_null(NodePath(CONTAINER_NAME)) as Node3D
	var new_container := false
	if container == null:
		if scene_root.has_node(NodePath(CONTAINER_NAME)):
			push_warning("Map Assets needs '%s' to be a Node3D." % CONTAINER_NAME)
			return null
		container = Node3D.new()
		container.name = CONTAINER_NAME
		new_container = true
	var label := String(entry.get("label", node.name))
	undo_redo.create_action("Place %s" % label, UndoRedo.MERGE_DISABLE, scene_root)
	if new_container:
		undo_redo.add_do_method(scene_root, &"add_child", container, true)
		undo_redo.add_do_method(container, &"set_owner", scene_root)
		undo_redo.add_do_reference(container)
	undo_redo.add_do_method(container, &"add_child", node, true)
	undo_redo.add_do_method(node, &"set_owner", scene_root)
	if node.has_meta(&"map_authoring_asset_wrapper"):
		for child in node.get_children():
			# Save the PackedScene root as an instance. Its descendants retain the
			# external scene's ownership, preserving native materials and hierarchy.
			undo_redo.add_do_method(child, &"set_owner", scene_root)
	if starter:
		for descendant in _descendants(node):
			undo_redo.add_do_method(descendant, &"set_owner", scene_root)
	undo_redo.add_do_property(node, &"global_transform", world_transform)
	undo_redo.add_do_reference(node)
	undo_redo.add_undo_method(container, &"remove_child", node)
	if new_container:
		undo_redo.add_undo_method(scene_root, &"remove_child", container)
	undo_redo.commit_action()
	return node


static func preview_scene(entry: Dictionary) -> PackedScene:
	var created := instantiate_entry(entry)
	var node := created.get("node") as Node3D
	if node == null:
		return null
	for descendant in _descendants(node):
		descendant.owner = node
	var packed := PackedScene.new()
	var error := packed.pack(node)
	node.free()
	return packed if error == OK else null


static func _collect_mesh_bounds(node: Node, relative: Transform3D,
		ancestors_visible: bool, state: Dictionary) -> void:
	var here := relative
	var visible := ancestors_visible
	if node is Node3D:
		visible = visible and (node as Node3D).visible
	if node is MeshInstance3D and visible:
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh != null:
			var current := here * mesh_node.get_aabb()
			if bool(state.valid):
				state.bounds = (state.bounds as AABB).merge(current)
			else:
				state.bounds = current
				state.valid = true
	for child in node.get_children():
		var child_relative := here
		if child is Node3D:
			child_relative = here * (child as Node3D).transform
		_collect_mesh_bounds(child, child_relative, visible, state)


static func _descendants(root: Node) -> Array[Node]:
	var result: Array[Node] = []
	for child in root.get_children():
		result.append(child)
		result.append_array(_descendants(child))
	return result


static func _safe_node_name(label: String) -> String:
	var result := label.strip_edges()
	for invalid in [".", ":", "@", "/", "\"", "%"]:
		result = result.replace(invalid, "")
	return result if not result.is_empty() else "MapAsset"
