extends RefCounted
## Source identity for the real loader's atomic dependency completion. This
## graph does not launch jobs or destroy anything. All allocation is unknown;
## weak Resource carriers deliberately retain a conservative closure lifetime.
const Archived := preload("res://src/actors/archived_model_policy.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const MAX_RESOURCES := 131072

static func _digest(value: Variant) -> bool:
	return value is String and value.length() == 64 and value.is_valid_hex_number(false) and value == value.to_lower()

static func _key(kind: String, source_sha: String, policy: String) -> String:
	return ("rl-loader-source-dag-v1|%s|%s|%s" % [kind, source_sha, policy]).sha256_text()

static func _path(base: String, uri: String) -> String:
	if uri.is_absolute_path() or ":" in uri or "\\" in uri:
		return ""
	var actual := ProjectSettings.globalize_path(base.path_join(uri)).replace("\\", "/").simplify_path()
	var scope := ProjectSettings.globalize_path("res://../eloria-assets").replace("\\", "/").simplify_path()
	var user_scope := ProjectSettings.globalize_path("user://").replace("\\", "/").simplify_path().trim_suffix("/")
	if not actual.to_lower().begins_with(scope.to_lower() + "/"):
		scope = user_scope
	return actual if actual.to_lower().begins_with(scope.to_lower() + "/") else ""

static func describe(manifest: WorldManifest) -> Dictionary:
	var began := Time.get_ticks_usec()
	if manifest == null or not manifest.is_valid():
		return {"complete": false, "reason": "invalid_joined_manifest"}
	var manifest_text := FileAccess.get_file_as_string(manifest.source_path)
	var present: Variant = JSON.parse_string(manifest_text)
	if not present is Dictionary or JSON.stringify(present, "", true, true) != JSON.stringify(manifest.data, "", true, true):
		return {"complete": false, "reason": "joined_manifest_identity_changed"}
	var policy := "skip=%d|formats=%d|mode=%s|retired=%s" % [Graphics.active_texture_skip(),
		Vram.usable_formats(), Vram.mode_name(), Archived.cache_token()]
	var nodes: Dictionary = {}
	var direct: Array[String] = []
	var base := manifest.source_path.get_base_dir()
	var inputs: Array[Dictionary] = []
	for field: String in ["externalResources", "externalMeshes"]:
		var declared: Variant = manifest.data.get(field, {})
		if not declared is Dictionary:
			return {"complete": false, "reason": "invalid_dependency_declarations"}
		var uris: Array = declared.keys()
		uris.sort()
		for uri: String in uris:
			var is_mesh := field == "externalMeshes"
			var prototype := uri.get_file().get_basename()
			if is_mesh and Archived.is_retired_prototype(prototype):
				# Retired placeholders do not acquire a mesh in the real loader.
				continue
			var sha := str(declared[uri])
			var path := _path(base, uri)
			if not _digest(sha) or path.is_empty() or FileAccess.get_sha256(path) != sha:
				return {"complete": false, "reason": "source_dependency_digest_mismatch", "path": path}
			var key := _key("prototype" if is_mesh else "image", sha, policy)
			var dependencies: Array[String] = []
			if is_mesh:
				# Read the present index rather than trusting the pool's session
				# memoization. Its image declarations are verified again here.
				var text := FileAccess.get_file_as_string(path.get_base_dir().path_join("index.json"))
				var parsed: Variant = JSON.parse_string(text)
				if not parsed is Dictionary or not parsed.get("prototypes") is Dictionary:
					return {"complete": false, "reason": "prototype_index_missing"}
				var entry: Variant = parsed.prototypes.get(prototype)
				if not entry is Dictionary or str(entry.get("sha256", "")) != sha or not entry.get("images", {}) is Dictionary:
					return {"complete": false, "reason": "prototype_index_identity_mismatch"}
				var images: Dictionary = entry.get("images", {})
				var image_uris: Array = images.keys()
				image_uris.sort()
				for image_uri: String in image_uris:
					var image_sha := str(images[image_uri])
					var image_path := _path(path.get_base_dir(), image_uri)
					if not _digest(image_sha) or image_path.is_empty() or FileAccess.get_sha256(image_path) != image_sha:
						return {"complete": false, "reason": "prototype_image_digest_mismatch", "path": image_path}
					var image_key := _key("image", image_sha, policy)
					nodes[image_key] = {"key": image_key, "kind": "image", "source_sha256": image_sha,
						"dependencies": [], "policy": policy}
					if image_key not in dependencies:
						dependencies.append(image_key)
			dependencies.sort()
			nodes[key] = {"key": key, "kind": "prototype" if is_mesh else "image", "source_sha256": sha,
				"dependencies": dependencies, "policy": policy}
			if key not in direct:
				direct.append(key)
			inputs.append({"path": path, "sha256": sha})
	direct.sort()
	# Root identity includes the manifest plus actual consumed GLB. Embedded
	# images are covered by its bytes, not falsely reported as external images.
	var manifest_sha := FileAccess.get_sha256(manifest.source_path)
	var glb_sha := FileAccess.get_sha256(manifest.glb_path()) if not manifest.has_streaming_chunks() else ""
	if not _digest(manifest_sha) or (not manifest.has_streaming_chunks() and not _digest(glb_sha)):
		return {"complete": false, "reason": "root_source_digest_missing"}
	var root_source := (manifest_sha + "|" + glb_sha).sha256_text()
	var root_key := _key("world", root_source, policy)
	nodes[root_key] = {"key": root_key, "kind": "world", "source_sha256": root_source,
		"manifest_sha256": manifest_sha, "glb_sha256": glb_sha, "dependencies": direct, "policy": policy}
	var keys: Array = nodes.keys()
	keys.sort()
	var ordered: Array[Dictionary] = []
	for key: String in keys:
		ordered.append(nodes[key])
	return {"complete": true, "root": root_key, "nodes": ordered, "elapsed_us": Time.get_ticks_usec() - began,
		"coverage": "world-glb-embedded-images-and-transitive-external-prototype-images",
		"allocation_kind": "unknown_cpu_gpu_allocation", "verification_reuse": false}

static func _resources(value: Variant, resources: Dictionary, seen: Dictionary, depth: int) -> bool:
	if depth > 64 or resources.size() > MAX_RESOURCES:
		return false
	if value is Resource:
		var resource := value as Resource
		if resource is Script or resource.get_script() != null:
			return false # Incomplete retention must never invoke a scripted stored getter.
		var identity := resource.get_instance_id()
		if seen.has(identity):
			return true
		seen[identity] = true
		resources[identity] = weakref(resource)
		for name: StringName in resource.get_meta_list():
			if not _resources(resource.get_meta(name), resources, seen, depth + 1):
				return false
		# Keep the real renderer/physics carrier itself, without invoking its
		# serialization getter (ImageTexture.image/ArrayMesh surfaces/MultiMesh
		# buffer may read back renderer data). Traverse safe Resource edges only.
		if resource is Mesh:
			var mesh := resource as Mesh
			for surface: int in mesh.get_surface_count():
				if not _resources(mesh.surface_get_material(surface), resources, seen, depth + 1):
					return false
			return true
		if resource is MultiMesh:
			return _resources((resource as MultiMesh).mesh, resources, seen, depth + 1)
		if resource is Texture or resource is Image or resource is Shape3D:
			return true
		for property: Dictionary in resource.get_property_list():
			if (int(property.usage) & PROPERTY_USAGE_STORAGE) != 0 and str(property.name) != "script":
				if not _resources(resource.get(property.name), resources, seen, depth + 1):
					return false
	elif value is Array:
		for item: Variant in value:
			if not _resources(item, resources, seen, depth + 1):
				return false
	elif value is Dictionary:
		for key: Variant in value:
			if not _resources(key, resources, seen, depth + 1) or not _resources(value[key], resources, seen, depth + 1):
				return false
	return true

static func resource_carriers(imported: Resource) -> Dictionary:
	var began := Time.get_ticks_usec()
	var resources: Dictionary = {}
	var complete := imported != null and _resources(imported, resources, {}, 0)
	return {"complete": complete, "references": resources.values(),
		"reason": "" if complete else "prepared_resource_carrier_recursion_limit",
		"elapsed_us": Time.get_ticks_usec() - began,
		"lifetime_policy": "conservative_prepared_resource_graph_weak_carriers"}

static func carriers(imported: Node) -> Dictionary:
	var began := Time.get_ticks_usec()
	var resources: Dictionary = {}
	var seen: Dictionary = {}
	var pending: Array[Node] = [imported]
	var visited := 0
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		visited += 1
		if visited > MAX_RESOURCES:
			return {"complete": false, "reason": "resource_carrier_node_limit", "references": resources.values()}
		for property: Dictionary in node.get_property_list():
			var usage := int(property.usage)
			if (usage & PROPERTY_USAGE_STORAGE) != 0 and (usage & PROPERTY_USAGE_SCRIPT_VARIABLE) == 0 and str(property.name) != "script":
				if not _resources(node.get(property.name), resources, seen, 0):
					return {"complete": false, "reason": "resource_carrier_recursion_limit", "references": resources.values()}
		for child: Node in node.get_children():
			pending.append(child)
	return {"complete": true, "references": resources.values(), "nodes": visited,
		"elapsed_us": Time.get_ticks_usec() - began,
		"lifetime_policy": "conservative_whole_resident_resource_graph_weak_carriers"}
