extends RefCounted
## Portable road surfaces live in existing ground passes. Source decode is
## Node-free; main publication binds private materials after ordinary styling.

const Data := preload("res://src/world/road_ground/field_data.gd")
const Pbr := preload("res://src/world/road_ground/source_material.gd")
const Composite := preload("res://src/world/road_ground/material.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")
const META := &"rl_road_ground"
const MATERIAL_META := &"rl_road_ground_source"

static func prepare(config: Dictionary, manifest_path: String) -> Dictionary:
	if config.is_empty():
		return {"ok": true, "absent": true}
	var began: int = Time.get_ticks_usec()
	var decoded: Dictionary = Data.read(config, manifest_path)
	if not bool(decoded.get("ok", false)):
		return decoded
	var data: Resource = decoded.data
	data.shader_sources = {"surface": FileAccess.get_file_as_string(Composite.SURFACE),
		"paint": FileAccess.get_file_as_string(Composite.PAINT)}
	for index: int in data.document.styles.size():
		var row: Dictionary = data.document.styles[index]
		if int(row.get("id", -1)) != index:
			return _error("road_style_ids_not_contiguous")
		var loaded: Dictionary = Pbr.read(row, str(data.metadata_path).get_base_dir())
		if not bool(loaded.get("ok", false)):
			return loaded
		data.styles.append(loaded.material)
		data.source_candidates.append(loaded)
	# Current authored road styles share image contents. Require this bounded
	# sampler contract rather than silently sampling the first style's pixels.
	var signatures: Array[String] = []
	for row: Dictionary in data.document.styles:
		signatures.append(_texture_signature(row))
	if signatures.size() > 1 and signatures[0] != signatures[1]:
		return _error("road_styles_do_not_share_texture_contents")
	return {"ok": true, "data": data, "metrics": {"decode_usec": Time.get_ticks_usec() - began,
		"decoded_field_bytes": data.decoded_bytes, "style_count": data.styles.size()}}

static func dependency_closure(config: Dictionary, manifest_path: String) -> Dictionary:
	return Data.dependency_closure(config, manifest_path)

static func revalidate(prepared: Dictionary) -> Dictionary:
	if not bool(prepared.get("ok", false)):
		return prepared
	if bool(prepared.get("absent", false)):
		return {"ok": true}
	var data: Resource = prepared.get("data") as Resource
	if data == null:
		return _error("road_prepared_resource_missing")
	for path: String in data.dependencies:
		if FileAccess.get_sha256(path) != str(data.dependencies[path]):
			return _error("road_prepared_dependency_changed: " + path)
	return {"ok": true}

static func bind(root: Node3D, manifest: WorldManifest, prepared: Dictionary) -> Dictionary:
	var verified: Dictionary = revalidate(prepared)
	if not bool(verified.get("ok", false)):
		return verified
	if bool(prepared.get("absent", false)):
		return {"ok": true, "absent": true}
	if root == null or manifest == null:
		return _error("road_bind_root_or_manifest")
	var data: Resource = prepared.data
	# Only publication adopts global weak texture identities. Worker-prepared
	# GLTFState carriers remain private until here, then release CPU images.
	for candidate: Dictionary in data.source_candidates:
		Pool.share(candidate.state, candidate.resources)
	data.source_candidates.clear()
	root.set_meta(META, {"data": data})
	return rebind(root, manifest)

## Re-style retained data after live look switches. Deliberately no file IO.
static func rebind(root: Node, manifest: WorldManifest) -> Dictionary:
	if root == null or not root.has_meta(META):
		return {"ok": true, "absent": true}
	if manifest == null or not root is Node3D:
		return _error("road_rebind_root_or_manifest")
	var binding: Dictionary = root.get_meta(META)
	var data: Resource = binding.get("data") as Resource
	if data == null:
		return _error("road_rebind_data")
	for removed: String in data.document.get("removed_road_node_names", []):
		for old: Node in root.find_children(removed, "Node3D", true, false):
			if old is MeshInstance3D and (old as MeshInstance3D).mesh != null:
				return _error("road_removed_geometry_still_present")
	var frame: Node3D = _unique(root, str(data.document.get("source_frame_node", "")))
	if frame == null or not valid_matrix(data.document.get("source_frame_matrix")):
		return _error("road_source_frame")
	var source_to_root: Transform3D = _local_to_root(frame, root) * matrix(data.document.source_frame_matrix).affine_inverse()
	var to_field: Transform3D = source_to_root.affine_inverse()
	var region: String = LookGround.region_of(manifest)
	var painted: bool = LookProfile.enabled()
	var heading: Vector2 = LookGround.sun_heading_of(manifest)
	var source_targets: Array[Dictionary] = []
	var meshes: Array[MeshInstance3D] = []
	for row: Dictionary in data.document.get("targets", []):
		var target := _unique(root, str(row.get("name", ""))) as MeshInstance3D
		if target == null or target.mesh == null or target.material_override != null:
			return _error("road_existing_ground_target_missing")
		meshes.append(target)
		for surface: int in target.mesh.get_surface_count():
			var source: Material = target.get_active_material(surface)
			if source != null and source.has_meta(MATERIAL_META):
				source = source.get_meta(MATERIAL_META) as Material
			var raw: Material = _source_of(source)
			var base: ShaderMaterial = source as ShaderMaterial
			if not painted and raw is BaseMaterial3D:
				base = _raw_base(raw as BaseMaterial3D, target, surface, region)
			elif base == null and raw is BaseMaterial3D:
				base = LookGround.painted_for(raw, LookGround.kind_of(str(target.name)), target.mesh, surface, region) as ShaderMaterial
			if base == null:
				return _error("road_ground_material_not_supported")
			source_targets.append({"target": target, "surface": surface, "source": source, "raw": raw, "base": base})
	if source_targets.is_empty():
		return _error("road_ground_targets_empty")
	var paving: PackedVector4Array = _paving_rects(meshes)
	var road: ShaderMaterial
	if painted:
		road = LookGround.painted_source_for(data.styles[0], LookGround.Kind.DECK, true, region,
			paving, Rect2(data.origin, data.extent)) as ShaderMaterial
	else:
		road = _pbr_adapter(data.styles[0], true)
	if road == null:
		return _error("road_painted_source")
	road.set_shader_parameter(&"look_sun_heading", heading)
	var cache: Dictionary = {}
	var ready: Array[Dictionary] = []
	for item: Dictionary in source_targets:
		var made: Dictionary = Composite.build(item.base, road, data.styles, painted, cache, data.shader_sources)
		if not bool(made.get("ok", false)):
			return made
		var material: ShaderMaterial = made.material
		material.set_meta(MATERIAL_META, item.source)
		# Painted wrappers participate in LookSwitch's ordinary source chain;
		# Original road materials are structural and survive look-off rebinds.
		if painted:
			material.set_meta(LookProfile.SOURCE_META, item.raw)
		data.upload()
		material.set_shader_parameter(&"trial_coverage", data.coverage_texture)
		material.set_shader_parameter(&"rg_triangle_ids", data.id_texture)
		material.set_shader_parameter(&"rg_affine_coefficients", data.coefficient_texture)
		material.set_shader_parameter(&"rg_records_per_row", data.records_per_row)
		material.set_shader_parameter(&"trial_mask_origin", data.origin)
		material.set_shader_parameter(&"trial_mask_extent", data.extent)
		material.set_shader_parameter(&"trial_mesh_to_mask", Projection(to_field * _local_to_root(item.target, root)))
		ready.append({"target": item.target, "surface": item.surface, "material": material})
	for item: Dictionary in ready:
		(item.target as MeshInstance3D).set_surface_override_material(int(item.surface), item.material)
		Ownership.attach(item.target)
	Ownership.refresh(root)
	binding["to_field"] = to_field
	binding["region"] = region
	root.set_meta(META, binding)
	return {"ok": true, "surfaces": ready.size(), "field_texture_bytes": data.decoded_bytes,
		"added_visual_nodes": 0, "added_material_passes": 0}

## Caller first confirms its physical ray hit terrain, so a road below an
## elevated bridge/prop never overrides that structural surface's semantics.
static func query(node: Node, world_point: Vector3) -> Dictionary:
	var owner: Node = node
	while owner != null and not owner.has_meta(META):
		owner = owner.get_parent()
	if not owner is Node3D:
		return {"present": false}
	var binding: Dictionary = owner.get_meta(META)
	if not binding.has("to_field"):
		return {"present": false}
	var local: Vector3 = (binding.to_field as Transform3D) * (owner as Node3D).global_transform.affine_inverse() * world_point
	var found: Dictionary = (binding.data as Resource).sample(Vector2(local.x, local.z))
	found["region"] = str(binding.get("region", ""))
	return found

static func is_terrain(node: Node) -> bool:
	if node == null:
		return false
	var name: String = str(node.name)
	if name.begins_with("StreamView_"):
		name = name.get_slice("__", 1)
	return name.begins_with("Terrain_") or name.begins_with("Walk_Terrain")

static func _raw_base(source: BaseMaterial3D, target: MeshInstance3D, surface: int, region: String) -> ShaderMaterial:
	var material: ShaderMaterial = _pbr_adapter(source,
		(target.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) != 0)
	if material == null:
		return null
	var shader := Shader.new()
	var code: String = material.shader.code
	code = code.replace("#include", "#define RG_ORIGINAL_BASE\nuniform sampler2D rg_base_orm : filter_linear_mipmap_anisotropic, repeat_enable;\nuniform bool rg_base_has_orm = false;\n#include")
	shader.code = code
	var saved: Dictionary = {}
	for uniform: Dictionary in material.shader.get_shader_uniform_list():
		var name: StringName = StringName(uniform.name)
		saved[name] = material.get_shader_parameter(name)
	material.shader = shader
	for name: StringName in saved:
		material.set_shader_parameter(name, saved[name])
	material.set_shader_parameter(&"rg_base_orm", source.roughness_texture)
	material.set_shader_parameter(&"rg_base_has_orm", source.roughness_texture != null)
	material.set_shader_parameter(&"use_vertex_alpha", source.vertex_color_use_as_albedo \
		and (target.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) != 0)
	return material

static func _pbr_adapter(source: BaseMaterial3D, has_colour: bool) -> ShaderMaterial:
	var shader: Shader
	match source.transparency:
		BaseMaterial3D.TRANSPARENCY_DISABLED:
			shader = LookGround.SHADER_OPAQUE if source.cull_mode == BaseMaterial3D.CULL_BACK else LookGround.SHADER_TWO_SIDED
		BaseMaterial3D.TRANSPARENCY_ALPHA:
			shader = LookGround.SHADER_BLEND
		BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS:
			shader = LookGround.SHADER_OVERLAY
		BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR, BaseMaterial3D.TRANSPARENCY_ALPHA_HASH:
			shader = LookGround.SHADER_CUTOUT
	if shader == null:
		return null
	var material := ShaderMaterial.new()
	material.shader = shader
	material.resource_name = source.resource_name
	material.render_priority = source.render_priority
	material.next_pass = source.next_pass
	material.set_shader_parameter(&"albedo_texture", source.albedo_texture)
	material.set_shader_parameter(&"albedo_color", source.albedo_color)
	material.set_shader_parameter(&"use_vertex_albedo", source.vertex_color_use_as_albedo and has_colour)
	material.set_shader_parameter(&"vertex_albedo_srgb", source.vertex_color_is_srgb)
	material.set_shader_parameter(&"use_vertex_alpha", source.vertex_color_use_as_albedo and has_colour)
	material.set_shader_parameter(&"normal_texture", source.normal_texture)
	material.set_shader_parameter(&"has_normal_texture", source.normal_enabled and source.normal_texture != null)
	material.set_shader_parameter(&"normal_scale", source.normal_scale)
	material.set_shader_parameter(&"roughness_value", source.roughness)
	material.set_shader_parameter(&"metallic_value", source.metallic)
	material.set_shader_parameter(&"specular_value", source.metallic_specular)
	material.set_shader_parameter(&"uv1_scale", source.uv1_scale)
	material.set_shader_parameter(&"uv1_offset", source.uv1_offset)
	return material

static func _source_of(material: Material) -> Material:
	var result: Material = material
	for _hop: int in 8:
		if result == null:
			break
		if result.has_meta(MATERIAL_META):
			result = result.get_meta(MATERIAL_META) as Material
		elif result.has_meta(LookProfile.SOURCE_META):
			result = result.get_meta(LookProfile.SOURCE_META) as Material
		else:
			break
	return result

static func _texture_signature(style: Dictionary) -> String:
	var document: Dictionary = style.material_document
	var material: Dictionary = document.materials[0]
	var signatures: Array = []
	for slot: Dictionary in [material.get("pbrMetallicRoughness", {}).get("baseColorTexture", {}),
		material.get("normalTexture", {}), material.get("pbrMetallicRoughness", {}).get("metallicRoughnessTexture", {})]:
		if not slot.has("index"):
			signatures.append(null)
			continue
		var texture: Dictionary = document.textures[int(slot.index)]
		var uri: String = str(document.images[int(texture.source)].uri)
		signatures.append([style.externalResources.get(uri),
			document.samplers[int(texture.sampler)] if texture.has("sampler") else {},
			slot.get("texCoord", 0), slot.get("extensions", {})])
	return JSON.stringify(signatures)

static func _paving_rects(meshes: Array[MeshInstance3D]) -> PackedVector4Array:
	# Same source-material classification as LookGround.paving_rects, without
	# allocating temporary proxy Nodes or changing live overrides.
	var rows: Array[Dictionary] = []
	for node: MeshInstance3D in meshes:
		for surface: int in node.mesh.get_surface_count():
			var raw: Material = _source_of(node.get_active_material(surface))
			if LookGround.is_paving(raw):
				var box: AABB = node.mesh.get_aabb()
				rows.append({"area": box.size.x * box.size.z, "rect": Vector4(box.position.x, box.position.z, box.end.x, box.end.z)})
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.area > b.area)
	var result := PackedVector4Array()
	for row: Dictionary in rows.slice(0, 8):
		result.append(row.rect)
	return result

static func _unique(root: Node, name: String) -> Node3D:
	if name.is_empty():
		return null
	var found: Array[Node] = root.find_children(name, "Node3D", true, false)
	return found[0] as Node3D if found.size() == 1 else null

static func _local_to_root(node: Node3D, root: Node) -> Transform3D:
	var result: Transform3D = node.transform
	var parent: Node = node.get_parent()
	while parent != null and parent != root:
		if parent is Node3D:
			result = (parent as Node3D).transform * result
		parent = parent.get_parent()
	return result

static func valid_matrix(value: Variant) -> bool:
	return Data.valid_matrix(value)

static func matrix(value: Array) -> Transform3D:
	return Transform3D(Basis(Vector3(value[0], value[1], value[2]), Vector3(value[4], value[5], value[6]),
		Vector3(value[8], value[9], value[10])), Vector3(value[12], value[13], value[14]))

static func _error(message: String) -> Dictionary:
	return {"ok": false, "error": message}
