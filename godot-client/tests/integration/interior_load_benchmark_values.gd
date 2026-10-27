extends RefCounted
## Offline equivalence witnesses only. These routines read back GPU resources;
## never include them in a timed benchmark sample or call them from a worker.
## Content excludes resource identities/paths/names and all object metadata.
## Sharing is reported separately, so identical pixels in separately allocated
## resources do not make the content digest depend on allocation identities.

const MAX_DEPTH := 80
const OMIT_PROPERTIES := [
	"resource_name", "resource_path", "resource_scene_unique_id", "resource_uid",
	"script", "owner", "name", "scene_file_path",
	"unique_name_in_owner", "editor_description", "_import_path",
]

static func texture(value: Texture2D) -> Dictionary:
	if value == null:
		return {"null": true}
	var image: Image = value.get_image()
	if image == null or image.is_empty():
		return {"width": value.get_width(), "height": value.get_height(),
			"image_unavailable": true}
	# get_data() contains the entire mip chain, including compressed blocks.
	return {"width": image.get_width(), "height": image.get_height(),
		"format": image.get_format(), "mips": image.get_mipmap_count(),
		"has_mipmaps": image.has_mipmaps(), "data_bytes": image.get_data().size(),
		"data_sha256": _bytes_digest(image.get_data())}

static func scene(root: Node3D, include_rows := true) -> Dictionary:
	if root == null:
		return {"digest": "", "counts": {}, "warnings": ["null root"]}
	var context: Dictionary = {"memo": {}, "active": {}, "bindings": {},
		"containers": [], "warnings": [], "opaque_links": 0}
	var counts: Dictionary = {"nodes": 0, "mesh_instances": 0,
		"multimesh_instances": 0, "collision_objects": 0, "collision_shapes": 0,
		"batches": 0, "bodies": 0}
	var nodes: Array[Node] = [root]
	var by_path: Dictionary = {}
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		var path: String = "." if node == root else str(root.get_path_to(node))
		by_path[path] = node
		for child: Node in node.get_children():
			nodes.append(child)
	var paths: Array = by_path.keys()
	paths.sort()
	var rows: Array = []
	for path: String in paths:
		var node: Node = by_path[path]
		counts.nodes += 1
		if node is MeshInstance3D:
			counts.mesh_instances += 1
		if node is MultiMeshInstance3D:
			counts.multimesh_instances += 1
			counts.batches += 1
		if node is CollisionObject3D:
			counts.collision_objects += 1
		if node is PhysicsBody3D:
			counts.bodies += 1
		if node is CollisionShape3D:
			counts.collision_shapes += 1
		var properties: Array = _stored_properties(node, context, path, 0)
		var child_order: Array[String] = []
		for child: Node in node.get_children():
			child_order.append(str(child.name))
		properties.append(["@child_order", child_order])
		# Node3D's property list can expose decomposed editor values rather than
		# its exact transform. Capture these authoritative values explicitly.
		if node is Node3D:
			properties.append(["@transform", _value((node as Node3D).transform,
				context, path + ":@transform", 0)])
			properties.append(["@visible", (node as Node3D).visible])
		if node is VisualInstance3D:
			properties.append(["@layers", (node as VisualInstance3D).layers])
		if node is MeshInstance3D:
			var instance := node as MeshInstance3D
			var overrides: Array = []
			for index: int in instance.get_surface_override_material_count():
				overrides.append(_value(instance.get_surface_override_material(index),
					context, "%s:@surface_override[%d]" % [path, index], 0))
			properties.append(["@surface_overrides", overrides])
		var row := {"path": path, "type": node.get_class(), "properties": properties}
		rows.append({"path": path, "type": node.get_class(), "digest": _digest(row),
			"properties": properties} if include_rows else
			{"path": path, "type": node.get_class(), "digest": _digest(row)})
	var groups: Array = []
	var unique_by_class: Dictionary = {}
	var references := 0
	for binding: Dictionary in (context.bindings as Dictionary).values():
		var binding_paths: Array = binding.paths
		binding_paths.sort()
		var class_name_text: String = binding.type
		unique_by_class[class_name_text] = int(unique_by_class.get(class_name_text, 0)) + 1
		references += binding_paths.size()
		groups.append({"type": class_name_text, "digest": binding.get("digest", ""),
			"paths": binding_paths})
	groups.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return _digest(a) < _digest(b))
	# Hash only per-node content, regardless of whether diagnostic properties
	# were requested. Child order is retained as an explicit property;
	# paths and per-node state are independent of traversal order.
	var content: Array = []
	for row: Dictionary in rows:
		content.append([row.path, row.type, row.digest])
	var result := {"digest": _digest(content), "counts": counts,
		"sharing": {"digest": _digest(groups), "unique_by_class": unique_by_class,
			"unique_resources": groups.size(), "references": references,
			"opaque_object_links": context.opaque_links},
		"warnings": context.warnings}
	if include_rows:
		result["rows"] = rows
	return result

static func _stored_properties(object: Object, context: Dictionary,
		path: String, depth: int) -> Array:
	var names: Array[String] = []
	for property: Dictionary in object.get_property_list():
		var property_name := str(property.name)
		if (int(property.get("usage", 0)) & PROPERTY_USAGE_STORAGE) == 0 \
				or property_name in OMIT_PROPERTIES or property_name.begins_with("metadata/"):
			continue
		names.append(property_name)
	names.sort()
	var properties: Array = []
	for property_name: String in names:
		properties.append([property_name, _value(object.get(property_name), context,
			path + ":" + property_name, depth + 1)])
	return properties

static func _resource(resource: Resource, context: Dictionary,
		path: String, depth: int) -> Dictionary:
	var identity := resource.get_instance_id()
	var bindings: Dictionary = context.bindings
	if not bindings.has(identity):
		bindings[identity] = {"type": resource.get_class(), "paths": []}
	(bindings[identity].paths as Array).append(path)
	if (context.memo as Dictionary).has(identity):
		return (context.memo as Dictionary)[identity]
	if (context.active as Dictionary).has(identity):
		_warn(context, "resource cycle at " + path)
		return {"cycle": resource.get_class()}
	(context.active as Dictionary)[identity] = true
	var data: Dictionary = {"type": resource.get_class()}
	if resource is Texture2D:
		# Match texture content across native ImageTexture and imported texture
		# wrappers. Wrapper classes and allocation identity are not pixel content.
		data = {"type": "Texture2D", "image": texture(resource as Texture2D)}
		if context.has("textures"): context.textures[identity] = data.image
		if bool((data.image as Dictionary).get("image_unavailable", false)):
			_warn(context, "texture image unavailable at " + path)
	elif resource is Image:
		var image := resource as Image
		data["image"] = {"width": image.get_width(), "height": image.get_height(),
			"format": image.get_format(), "mips": image.get_mipmap_count(),
			"data_sha256": _bytes_digest(image.get_data())}
	elif resource is Mesh:
		var mesh := resource as Mesh
		data["aabb"] = _value(mesh.get_aabb(), context, path + ":aabb", depth + 1)
		var surfaces: Array = []
		for index: int in mesh.get_surface_count():
			var raw_surface: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), index)
			raw_surface.erase("material")
			raw_surface.erase("material_rid")
			surfaces.append({"format": mesh.surface_get_format(index),
				"primitive": mesh.surface_get_primitive_type(index),
				"arrays": _value(mesh.surface_get_arrays(index), context,
					"%s:surface[%d].arrays" % [path, index], depth + 1),
				"blend_shapes": _value(mesh.surface_get_blend_shape_arrays(index), context,
					"%s:surface[%d].blend_shapes" % [path, index], depth + 1),
				"gpu_geometry": _value(raw_surface, context,
					"%s:surface[%d].gpu_geometry" % [path, index], depth + 1),
				"material": _value(mesh.surface_get_material(index), context,
					"%s:surface[%d].material" % [path, index], depth + 1)})
		data["surfaces"] = surfaces
		if mesh is ArrayMesh:
			var array_mesh := mesh as ArrayMesh
			data["blend_shape_mode"] = array_mesh.blend_shape_mode
			data["lightmap_size_hint"] = _value(array_mesh.lightmap_size_hint,
				context, path + ":lightmap_size_hint", depth + 1)
			data["custom_aabb"] = _value(array_mesh.custom_aabb,
				context, path + ":custom_aabb", depth + 1)
			data["shadow_mesh"] = _value(array_mesh.shadow_mesh,
				context, path + ":shadow_mesh", depth + 1)
			var blend_names: Array = []
			for index: int in array_mesh.get_blend_shape_count():
				blend_names.append(str(array_mesh.get_blend_shape_name(index)))
			data["blend_shape_names"] = blend_names
	elif resource is MultiMesh:
		var multimesh := resource as MultiMesh
		data["transform_format"] = multimesh.transform_format
		data["use_colors"] = multimesh.use_colors
		data["use_custom_data"] = multimesh.use_custom_data
		data["instance_count"] = multimesh.instance_count
		data["visible_instance_count"] = multimesh.visible_instance_count
		data["buffer"] = _value(multimesh.buffer, context, path + ":buffer", depth + 1)
		data["custom_aabb"] = _value(multimesh.custom_aabb,
			context, path + ":custom_aabb", depth + 1)
		data["mesh"] = _value(multimesh.mesh, context, path + ":mesh", depth + 1)
	elif resource is Shader:
		data["code_sha256"] = _bytes_digest((resource as Shader).code.to_utf8_buffer())
	else:
		# Material (including ShaderMaterial uniforms/next_pass), Shape3D and
		# other serializable Resources are covered by their stored properties.
		data["properties"] = _stored_properties(resource, context, path, depth + 1)
	var result := {"resource_type": str(data.type), "digest": _digest(data)}
	(context.active as Dictionary).erase(identity)
	(context.memo as Dictionary)[identity] = result
	(bindings[identity] as Dictionary)["digest"] = result.digest
	return result

static func _value(value: Variant, context: Dictionary,
		path: String, depth: int) -> Variant:
	if depth > MAX_DEPTH:
		_warn(context, "depth limit at " + path)
		return {"depth_limit": true}
	if value is Resource:
		return _resource(value as Resource, context, path, depth)
	if value is Array or value is Dictionary:
		for active: Variant in context.containers:
			if is_same(active, value):
				_warn(context, "container cycle at " + path)
				return {"container_cycle": typeof(value)}
		(context.containers as Array).append(value)
		var result: Array = []
		if value is Array:
			for index: int in (value as Array).size():
				result.append(_value(value[index], context, "%s[%d]" % [path, index], depth + 1))
		else:
			var entries: Array = []
			for key: Variant in (value as Dictionary).keys():
				var canonical_key: Variant = _value(key, context, path + ":key", depth + 1)
				entries.append({"key": canonical_key, "sort": var_to_bytes(canonical_key).hex_encode(),
					"value": value[key]})
			entries.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.sort) < str(b.sort))
			for entry: Dictionary in entries:
				result.append([entry.key, _value(entry.value, context,
					path + "[" + str(entry.key) + "]", depth + 1)])
		(context.containers as Array).pop_back()
		return {"variant_type": typeof(value), "items": result}
	if value is Object:
		context.opaque_links = int(context.opaque_links) + 1
		return {"ignored_object_type": (value as Object).get_class()}
	var kind := typeof(value)
	if kind in [TYPE_CALLABLE, TYPE_SIGNAL, TYPE_RID]:
		context.opaque_links = int(context.opaque_links) + 1
		return {"ignored_runtime_type": kind}
	if kind == TYPE_STRING:
		return _normalise_path_text(str(value))
	if kind == TYPE_STRING_NAME:
		return {"string_name": str(value)}
	if kind == TYPE_NODE_PATH:
		return {"node_path": str(value)}
	if kind in [TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT]:
		return value
	# Typed vectors/transforms/packed arrays retain their exact serialization;
	# store its hash to avoid dumping entire vertex/physics arrays into JSON.
	var bytes: PackedByteArray = var_to_bytes(value)
	return {"variant_type": kind, "bytes": bytes.size(), "sha256": _bytes_digest(bytes)}

static func _normalise_path_text(value: String) -> String:
	var normalised := value.replace("\\", "/")
	if normalised.contains("/eloria-assets/"):
		return "asset://" + normalised.split("/eloria-assets/", true, 1)[1]
	if normalised.contains("/godot-client/"):
		return "res://" + normalised.split("/godot-client/", true, 1)[1]
	return value

static func _warn(context: Dictionary, message: String) -> void:
	if not (context.warnings as Array).has(message):
		(context.warnings as Array).append(message)

static func _digest(value: Variant) -> String:
	return _bytes_digest(var_to_bytes(value))

static func _bytes_digest(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()
