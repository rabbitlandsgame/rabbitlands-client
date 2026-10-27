extends RefCounted
## Untimed effective-appearance/geometry/full-mip witness. GPU readbacks are
## intentional here and must never run in a measured process.
const FP := preload("res://tests/integration/interior_load_benchmark_values.gd")
const BASE_SKIP := ["name", "owner", "script", "scene_file_path", "editor_description",
    "unique_name_in_owner", "mesh", "multimesh", "material_override", "material_overlay"]

static func _context() -> Dictionary:
	return {"memo": {}, "active": {}, "bindings": {}, "containers": [],
		"warnings": [], "opaque_links": 0, "meshes": {}, "mesh_active": {}, "textures": {}}

static func _hash(value: Variant) -> String:
	return FP._bytes_digest(var_to_bytes(value))

static func _geometry(mesh: Mesh, context: Dictionary) -> String:
	if mesh == null: return ""
	var identity := mesh.get_instance_id()
	if (context.meshes as Dictionary).has(identity): return context.meshes[identity]
	if (context.mesh_active as Dictionary).has(identity): return "geometry_cycle"
	context.mesh_active[identity] = true
	var data := {"class": mesh.get_class(), "aabb": mesh.get_aabb(), "surfaces": []}
	for surface: int in mesh.get_surface_count():
		var native := RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
		native.erase("material")
		native.erase("material_rid")
		data.surfaces.append({"format": mesh.surface_get_format(surface),
			"primitive": mesh.surface_get_primitive_type(surface),
			"arrays": FP._value(mesh.surface_get_arrays(surface), context, "arrays", 0),
			"blend": FP._value(mesh.surface_get_blend_shape_arrays(surface), context, "blend", 0),
			"native": FP._value(native, context, "native", 0)})
	if mesh is ArrayMesh:
		var array_mesh := mesh as ArrayMesh
		data["blend_mode"] = array_mesh.blend_shape_mode
		data["custom_aabb"] = array_mesh.custom_aabb
		data["lightmap_hint"] = array_mesh.lightmap_size_hint
		data["shadow"] = _geometry(array_mesh.shadow_mesh, context)
		var names: Array = []
		for index: int in array_mesh.get_blend_shape_count(): names.append(str(array_mesh.get_blend_shape_name(index)))
		data["blend_names"] = names
	var digest := _hash(data)
	context.mesh_active.erase(identity)
	context.meshes[identity] = digest
	return digest

static func _segment(node: Node) -> String:
	var name := str(node.name)
	# Unnamed helper Nodes receive process-global allocation counters. Preserve
	# authored names; compare these helpers by class and exact sibling position.
	var parts := name.split("@", false)
	var generated := name.begins_with("@") and parts.size() == 2 \
		and parts[0] == node.get_class() and parts[1].is_valid_int()
	return "@%s[%d]" % [node.get_class(), node.get_index()] if generated else name

static func _path(root_node: Node, node: Node) -> String:
	if root_node == node: return "."
	var segments: Array[String] = []
	var cursor := node
	while cursor != null and cursor != root_node:
		segments.push_front(_segment(cursor))
		cursor = cursor.get_parent()
	return "/".join(segments)

static func scene(root_node: Node3D) -> Dictionary:
	var context := _context()
	var nodes: Array[Node] = [root_node]
	var paths := {}
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		paths[_path(root_node, node)] = node
		for child: Node in node.get_children(): nodes.append(child)
	var names: Array = paths.keys()
	names.sort()
	var rows: Array = []
	var counts := {"nodes": names.size(), "mesh_instances": 0, "batches": 0, "bodies": 0}
	for path: String in names:
		var node: Node = paths[path]
		var properties := {}
		var property_names: Array[String] = []
		for property: Dictionary in node.get_property_list():
			var name := str(property.name)
			if (int(property.get("usage", 0)) & PROPERTY_USAGE_STORAGE) == 0 or name in BASE_SKIP \
					or name.begins_with("metadata/") or name.begins_with("surface_material_override/"):
				continue
			property_names.append(name)
		property_names.sort()
		for name: String in property_names: properties[name] = FP._value(node.get(name), context, path + ":" + name, 0)
		var children: Array[String] = []
		for child: Node in node.get_children(): children.append(_segment(child))
		properties["children"] = children
		if node.has_meta("cutaway_outward"):
			properties["cutaway_outward"] = FP._value(node.get_meta("cutaway_outward"), context, path, 0)
		if node is Node3D:
			properties["transform"] = FP._value((node as Node3D).transform, context, path, 0)
			properties["visible"] = (node as Node3D).visible
		if node is VisualInstance3D: properties["layers"] = (node as VisualInstance3D).layers
		if node is MeshInstance3D:
			counts.mesh_instances += 1
			var instance := node as MeshInstance3D
			properties["geometry"] = _geometry(instance.mesh, context)
			var materials: Array = []
			if instance.mesh != null:
				for surface: int in instance.mesh.get_surface_count():
					materials.append(FP._value(instance.get_active_material(surface), context, path + ":effective_material", 0))
			properties["effective_materials"] = materials
		elif node is MultiMeshInstance3D:
			counts.batches += 1
			var batch := node as MultiMeshInstance3D
			if batch.multimesh != null:
				var multimesh := batch.multimesh
				properties["geometry"] = _geometry(multimesh.mesh, context)
				properties["multimesh"] = FP._value([multimesh.transform_format, multimesh.use_colors,
					multimesh.use_custom_data, multimesh.instance_count, multimesh.visible_instance_count,
					multimesh.custom_aabb, multimesh.buffer], context, path + ":multimesh", 0)
				var materials: Array = []
				if multimesh.mesh != null:
					for surface: int in multimesh.mesh.get_surface_count():
						materials.append(FP._value(batch.material_override if batch.material_override != null
							else multimesh.mesh.surface_get_material(surface), context, path + ":effective_material", 0))
				properties["effective_materials"] = materials
		if node is GeometryInstance3D:
			properties["material_overlay"] = FP._value((node as GeometryInstance3D).material_overlay, context, path + ":overlay", 0)
		if node is PhysicsBody3D: counts.bodies += 1
		rows.append({"path": path, "class": node.get_class(), "digest": _hash(properties), "properties": properties})
	var compact: Array = []
	for row: Dictionary in rows: compact.append([row.path, row.class, row.digest])
	var texture_contents := {}
	var texture_bytes := 0
	for image: Dictionary in context.textures.values():
		var identity := _hash(image)
		texture_contents[identity] = int(texture_contents.get(identity,0))+1
		texture_bytes += int(image.get("data_bytes",0))
	return {"digest": _hash(compact), "counts": counts, "rows": rows, "warnings": context.warnings,
		"textures":{"resources":context.textures.size(),"unique_full_mip_contents":texture_contents.size(),
			"decoded_full_mip_bytes":texture_bytes,"content_resource_counts":texture_contents}}

static func difference(a: Dictionary, b: Dictionary) -> Array:
	var left := {}
	var right := {}
	for row: Dictionary in a.get("rows", []): left[str(row.path)] = row
	for row: Dictionary in b.get("rows", []): right[str(row.path)] = row
	var changed: Array = []
	for path: String in left:
		if not right.has(path) or str(left[path].digest) != str(right[path].digest):
			changed.append({"path": path, "raw": left[path], "native": right.get(path)})
		if changed.size() >= 4: break
	for path: String in right:
		if not left.has(path): changed.append({"extra_native_path": path})
		if changed.size() >= 4: break
	return changed
