extends RefCounted
## Node ownership has a single main-thread owner. Worker completion records
## may hold native Resources, but never an instantiated prepared Node tree.
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
const Sharing := preload("res://src/world/prepared_material_sharing.gd")
const RAW_BATCH_OVERRIDE := &"rl_prepared_raw_batch_override"
const MaterialOwnership := preload("res://src/world/prepared_material_ownership.gd")

static func _data_value(value: Variant, visited: Dictionary, depth: int) -> bool:
	if depth > 64 or value is Script or value is Callable or value is Signal or value is Node:
		return false
	if value is Array:
		for child: Variant in value:
			if not _data_value(child, visited, depth + 1):
				return false
		return true
	if value is Dictionary:
		for key: Variant in value:
			if not _data_value(key, visited, depth + 1) or not _data_value(value[key], visited, depth + 1):
				return false
		return true
	if not value is Resource:
		return not value is Object
	var resource := value as Resource
	if resource.get_script() != null:
		return false
	if resource is PackedScene:
		return _data_only(resource as PackedScene, visited, depth + 1)
	var identity := resource.get_instance_id()
	if visited.has(identity):
		return true
	visited[identity] = true
	for key: StringName in resource.get_meta_list():
		if not _data_value(resource.get_meta(key), visited, depth + 1):
			return false
	# Do not enumerate serialization getters for GPU-backed resources: an
	# ImageTexture.image, ArrayMesh surface or MultiMesh buffer can read back
	# renderer data. Their resource edges have explicit CPU-side accessors.
	if resource is Mesh:
		var mesh := resource as Mesh
		for surface: int in mesh.get_surface_count():
			if not _data_value(mesh.surface_get_material(surface), visited, depth + 1):
				return false
		return true
	if resource is MultiMesh:
		return _data_value((resource as MultiMesh).mesh, visited, depth + 1)
	if resource is Texture or resource is Image or resource is Shape3D:
		return true
	for property: Dictionary in resource.get_property_list():
		if (int(property.get("usage", 0)) & PROPERTY_USAGE_STORAGE) == 0:
			continue
		var name: StringName = property.name
		if name == &"script":
			continue # get_script() was checked without invoking a stored getter.
		if not _data_value(resource.get(name), visited, depth + 1):
			return false
	return true

static func _data_only(packed: PackedScene, visited: Dictionary, depth := 0) -> bool:
	if depth > 64:
		return false
	if packed == null or packed.get_script() != null:
		return false
	var identity := packed.get_instance_id()
	if visited.has(identity):
		return true
	visited[identity] = true
	var state := packed.get_state()
	if state.get_connection_count() != 0:
		return false
	for index: int in state.get_node_count():
		if not state.get_node_instance_placeholder(index).is_empty():
			return false
		var nested := state.get_node_instance(index)
		if nested != null and not _data_only(nested, visited, depth + 1):
			return false
		for property: int in state.get_node_property_count(index):
			var value: Variant = state.get_node_property_value(index, property)
			if (state.get_node_property_name(index, property) == &"script" and value != null) \
					or not _data_value(value, visited, depth + 1):
				return false
	return true

static func instantiate(record: Dictionary) -> Node3D:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		push_error("prepared scene instantiation requires the main thread")
		return null
	var packed := record.get("resource") as PackedScene
	if str(record.get("status", "")) != "hit" or packed == null:
		return null
	# Node _init/_notification runs during instantiate(), so a post-check alone
	# would execute an unexpected script before rejecting it. Inspect state and
	# every nested/inherited scene first. Cooked resources come from a trusted,
	# script-rejecting producer; this is not a sandbox for arbitrary native data.
	var entry: Dictionary = record.get("entry", {})
	var inspected: Dictionary = {}
	if not _data_only(packed, inspected):
		return null
	# The trusted cooker externalizes every Resource into the verified payload
	# closure. Inspect these too, without traversing opaque GPU serialization
	# getters; a nested local-to-scene Resource must not hide behind such a leaf.
	for payload: Variant in entry.get("payloads", []):
		if not payload is Dictionary:
			return null
		var path := str(payload.get("path", ""))
		if path.is_empty():
			return null
		var resource: Resource = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REUSE)
		if resource == null or not _data_value(resource, inspected, 0):
			return null
	var instance_root := packed.instantiate()
	if not instance_root is Node3D:
		if instance_root != null:
			instance_root.free()
		return null
	var root := instance_root as Node3D
	var images: Dictionary = entry.get("shared_images", {})
	var meshes: Dictionary = entry.get("shared_meshes", {})
	var nodes: Array[Node] = [root]
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		for child: Node in node.get_children():
			nodes.append(child)
		# Import output is data-only. Reject an unexpected executable attachment
		# before exposing the root to the active scene.
		if node.get_script() != null:
			root.free()
			push_error("prepared imported scene unexpectedly contains a script")
			return null
		if node is MeshInstance3D:
			var instance := node as MeshInstance3D
			if instance.mesh != null and meshes.has(instance.mesh.resource_path):
				var mesh_key := str(meshes[instance.mesh.resource_path])
				instance.mesh = MeshPool._publish_or_adopt(mesh_key, Sharing.mesh_resource(
					{"status": "hit", "resource": instance.mesh, "entry": entry}))
			# Material templates and geometry are immutable shared resources.
			# Existing look/fade/season consumers receive per-instance overrides.
			if instance.mesh != null:
				for surface: int in instance.mesh.get_surface_count():
					var material := instance.get_surface_override_material(surface)
					if material == null:
						material = instance.mesh.surface_get_material(surface)
					if material != null:
						instance.set_surface_override_material(surface, Sharing.material(material, images))
		if node is MultiMeshInstance3D:
			var batch := node as MultiMeshInstance3D
			if batch.multimesh != null:
				# Fade/promotion changes individual transforms. Every instance
				# needs a private buffer, including non-pooled geometry.
				batch.multimesh = batch.multimesh.duplicate(false) as MultiMesh
				var mesh := batch.multimesh.mesh
				if mesh != null and meshes.has(mesh.resource_path):
					batch.multimesh.mesh = MeshPool._publish_or_adopt(str(meshes[mesh.resource_path]),
						Sharing.mesh_resource({"status": "hit", "resource": mesh, "entry": entry}))
				mesh = batch.multimesh.mesh
				if mesh != null and mesh.get_surface_count() == 1 and batch.material_override == null:
					var material := mesh.surface_get_material(0)
					if material != null:
						batch.material_override = Sharing.material(material, images)
						# A private raw replacement is not an authored override.
						# Existing look passes may replace this exact identity once.
						batch.set_meta(RAW_BATCH_OVERRIDE, weakref(batch.material_override))
		if node is GeometryInstance3D:
			var geometry := node as GeometryInstance3D
			if geometry.material_override != null:
				var generated := geometry.get_meta(RAW_BATCH_OVERRIDE) as WeakRef \
					if geometry.has_meta(RAW_BATCH_OVERRIDE) else null
				if generated == null or generated.get_ref() != geometry.material_override:
					geometry.material_override = Sharing.material(geometry.material_override, images)
			MaterialOwnership.attach(geometry)
	return root
