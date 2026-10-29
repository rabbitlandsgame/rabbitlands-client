extends RefCounted
## Opt-in existing-visible-ground-pass experiment. It creates no visual nodes,
## leaves base vertices at their authored height, and retains exact road physics.

const SCHEMA := "rabbitlands-road-terrain-blend-trial-v1"
const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
const BlendMaterial := preload("res://src/dev/road_texture_trial/terrain_blend_material.gd")
const Ground := preload("res://src/world/look/look_ground.gd")
const Profile := preload("res://src/world/look/look_profile.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")

static func apply(world_root: Node3D, trial_manifest_path: String, variant := "blend") -> Dictionary:
	var result: Dictionary = {"ok": false, "errors": [], "metrics": {"variant": variant,
		"production": false, "representation": "existing_visible_ground_pass",
		"added_visual_nodes": 0, "added_material_passes": 0, "vertex_geometry_changed": false,
		"overlaps": "max_raw_coverage_dominant_uv", "visual_road_lift_metres": 0.0,
		"uv_sampling": "level_zero_selected_triangle_affine_reconstruction",
		"visual_surface_above_terrain_metres": 0.006,
		"physical_road_lift_metres": 0.055, "visual_physics_offset_metres": 0.049,
		"full_painted_grass_supported": false}}
	if variant in ["baseline", "original", "consolidated"]:
		result.ok = true
		result.metrics["no_op"] = true
		return result
	if world_root == null or variant not in ["blend", "blend2", "blend4", "blend8"]:
		return _error(result, "invalid_blend_world_or_variant")
	if world_root.has_meta(&"terrain_blend_trial") or world_root.has_meta(&"road_texture_trial"):
		return _error(result, "road_trial_already_installed")
	if not Profile.enabled() or (Profile.full_painted() and Graphics.decorative_grass):
		return _error(result, "blend_requires_painted_ground_without_decorative_grass")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(trial_manifest_path))
	if not parsed is Dictionary or str(parsed.get("schema", "")) != SCHEMA:
		return _error(result, "invalid_blend_metadata")
	var chunks: Array[Dictionary] = []
	if parsed.get("chunks") is Array:
		for relative: Variant in parsed.chunks:
			var path: String = trial_manifest_path.get_base_dir().path_join(str(relative)).simplify_path()
			var child: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
			if not child is Dictionary or str(child.get("schema", "")) != SCHEMA:
				return _error(result, "invalid_blend_chunk_metadata")
			child["_directory"] = path.get_base_dir()
			chunks.append(child)
	else:
		parsed["_directory"] = trial_manifest_path.get_base_dir()
		chunks.append(parsed)
	var context: Dictionary = Trial._paint_context(world_root)
	var shader_cache: Dictionary = {}
	var prepared: Array[Dictionary] = []
	var began: int = Time.get_ticks_usec()
	for chunk: Dictionary in chunks:
		var part: Dictionary = _prepare(world_root, chunk, context, shader_cache)
		if not bool(part.get("ok", false)):
			_dispose(prepared)
			return _error(result, str(part.get("error", "blend_prepare_failed")))
		prepared.append(part)
	var bindings: Array[Dictionary] = []
	var field_bytes := 0
	var collision_bytes := 0
	var jacobian_bytes := 0
	for part: Dictionary in prepared:
		for item: Dictionary in part.colliders:
			var placeholder: Node3D = item.placeholder
			var compact: MeshInstance3D = item.node
			compact.transform = placeholder.transform
			placeholder.replace_by(compact)
			placeholder.free()
		var target: MeshInstance3D = part.target
		target.set_surface_override_material(0, part.material)
		Ownership.attach(target)
		bindings.append({"target": target, "original_material": part.original_material,
			"field_grid": part.grid, "coverage_image": part.coverage_image})
		field_bytes += int(part.field_bytes)
		collision_bytes += int(part.collision_bytes)
		jacobian_bytes += int(part.jacobian_bytes)
	Ownership.refresh(world_root)
	world_root.set_meta(&"terrain_blend_trial", {"bindings": bindings, "chunks": chunks})
	result.ok = true
	result.metrics.merge({"chunks": chunks.size(), "existing_ground_materials_replaced": bindings.size(),
		"field_texture_bytes": field_bytes, "compact_collision_source_bytes": collision_bytes,
		"jacobian_texture_bytes": jacobian_bytes,
		"apply_usec": Time.get_ticks_usec() - began}, true)
	return result

static func _prepare(root: Node3D, data: Dictionary, context: Dictionary, shader_cache: Dictionary) -> Dictionary:
	var layers: Variant = data.get("layers")
	var rows: Variant = data.get("nodes")
	if not layers is Array or layers.size() != 1 or not rows is Array or rows.is_empty():
		return {"ok": false, "error": "blend_requires_one_common_material_field"}
	var layer: Dictionary = layers[0]
	if not Trial._valid_matrix(layer.get("world_matrix")):
		return {"ok": false, "error": "invalid_blend_field_frame"}
	var names: Array = data.get("visible_ground_node_names", data.get("ground_node_names", []))
	if names.is_empty():
		names = ["AuthoredGround_%sBase_%s_%s" % [data.get("region", "suncoil"),
			data.get("region", "suncoil"), data.get("chunk", "")]]
	if names.size() != 1:
		return {"ok": false, "error": "blend_requires_one_visible_base_ground"}
	var matches: Array[Node] = root.find_children(str(names[0]), "MeshInstance3D", true, false)
	if matches.size() != 1:
		return {"ok": false, "error": "blend_base_ground_not_unique"}
	var target := matches[0] as MeshInstance3D
	if not target.is_visible_in_tree() or target.mesh == null or target.mesh.get_surface_count() != 1 \
			or target.material_override != null or not str(target.name).begins_with("AuthoredGround_"):
		return {"ok": false, "error": "blend_target_is_not_existing_visible_single_surface_ground"}
	var base := target.get_active_material(0) as ShaderMaterial
	if base == null:
		return {"ok": false, "error": "blend_target_has_no_painted_ground_material"}
	var directory: String = str(data.get("_directory", ""))
	var fields: Dictionary = Trial._fields(directory, layer)
	if not bool(fields.get("ok", false)):
		return fields
	var jacobian: Dictionary = _jacobian(directory, layer)
	if not bool(jacobian.get("ok", false)):
		return jacobian
	var source: Dictionary = Trial._source_material(layer)
	if not bool(source.get("ok", false)):
		return source
	var colliders: Array[Dictionary] = []
	var primary_placeholder: Node3D
	var source_area := Rect2()
	var collision_bytes := 0
	var seen: Dictionary = {}
	for row: Dictionary in rows:
		var name: String = str(row.get("road_node_name", ""))
		var found: Array[Node] = root.find_children(name, "Node3D", true, false)
		if found.size() != 1 or seen.has(name):
			return _prepare_error(colliders, "blend_road_placeholder_not_unique")
		seen[name] = true
		var placeholder := found[0] as Node3D
		if placeholder is MeshInstance3D and (placeholder as MeshInstance3D).mesh != null:
			return _prepare_error(colliders, "original_road_visual_geometry_present")
		var collider: Dictionary = Trial._collider(directory, row)
		if not bool(collider.get("ok", false)):
			return _prepare_error(colliders, str(collider.get("error", "blend_collision")))
		var compact: MeshInstance3D = collider.node
		colliders.append({"placeholder": placeholder, "node": compact})
		collision_bytes += int(collider.bytes)
		var box: AABB = compact.get_aabb()
		var area := Rect2(box.position.x, box.position.z, box.size.x, box.size.z)
		source_area = area if source_area.size == Vector2.ZERO else source_area.merge(area)
		if name == str(layer.get("road_node_name", "")):
			primary_placeholder = placeholder
	if primary_placeholder == null:
		return _prepare_error(colliders, "blend_field_has_no_source_placeholder")
	var road := Ground.painted_for(source.material, Ground.Kind.DECK, source.mesh, 0,
		str(data.get("region", "suncoil")), context.paving, source_area) as ShaderMaterial
	if road == null:
		return _prepare_error(colliders, "blend_source_road_paint")
	road.set_shader_parameter(&"look_sun_heading", context.sun_heading)
	var derived: Dictionary = BlendMaterial.build(base, road, shader_cache)
	if not bool(derived.get("ok", false)):
		return _prepare_error(colliders, str(derived.get("error", "blend_shader")))
	var source_frame: Transform3D = Trial._matrix(layer.world_matrix)
	var source_to_runtime: Transform3D = primary_placeholder.global_transform * source_frame.affine_inverse()
	var mesh_to_mask: Transform3D = source_to_runtime.affine_inverse() * target.global_transform
	var material: ShaderMaterial = derived.material
	material.set_shader_parameter(&"trial_mesh_to_mask", Projection(mesh_to_mask))
	material.set_shader_parameter(&"trial_mask_origin", fields.origin)
	material.set_shader_parameter(&"trial_mask_extent", fields.extent)
	material.set_shader_parameter(&"trial_coverage", fields.coverage)
	material.set_shader_parameter(&"trial_uv_field", fields.uv)
	material.set_shader_parameter(&"trial_uv_jacobian", jacobian.texture)
	var rgb: Array = layer.get("source_vertex_rgb", [1.0, 1.0, 1.0])
	if rgb.size() != 3:
		return _prepare_error(colliders, "blend_vertex_rgb")
	material.set_shader_parameter(&"trial_vertex_rgb", Vector3(float(rgb[0]), float(rgb[1]), float(rgb[2])))
	return {"ok": true, "target": target, "material": material, "original_material": base,
		"colliders": colliders, "field_bytes": int(fields.bytes) + int(jacobian.bytes),
		"jacobian_bytes": jacobian.bytes, "collision_bytes": collision_bytes,
		"coverage_image": fields.coverage_image, "grid": layer.grid}

static func _jacobian(directory: String, layer: Dictionary) -> Dictionary:
	var record: Variant = layer.get("uv_jacobian")
	var grid: Variant = layer.get("grid")
	if not record is Dictionary or not grid is Dictionary or str(record.get("format", "")) != "RGBA32F" \
			or str(record.get("byte_order", "")) != "little" or str(record.get("compression", "")) != "zstd" \
			or record.get("components") != ["dU_dX", "dU_dZ", "dV_dX", "dV_dZ"]:
		return {"ok": false, "error": "blend_jacobian_contract"}
	var width: int = int(grid.get("width", 0))
	var height: int = int(grid.get("height", 0))
	var expected: int = width * height * 16
	if width < 1 or height < 1 or width * height > Trial.MAX_PIXELS \
			or int(record.get("width", 0)) != width or int(record.get("height", 0)) != height \
			or int(record.get("uncompressed_bytes", -1)) != expected:
		return {"ok": false, "error": "blend_jacobian_layout"}
	var path: String = Trial._path(directory, str(record.get("file", "")))
	var stored: PackedByteArray = FileAccess.get_file_as_bytes(path)
	if str(record.get("file_sha256", "")).length() != 64 or BlendMaterial._sha(stored) != str(record.file_sha256):
		return {"ok": false, "error": "blend_jacobian_stored_hash"}
	var decoded: PackedByteArray = stored.decompress(expected, FileAccess.COMPRESSION_ZSTD)
	if decoded.size() != expected or str(record.get("sha256", "")).length() != 64 \
			or BlendMaterial._sha(decoded) != str(record.sha256):
		return {"ok": false, "error": "blend_jacobian_decoded_hash_or_size"}
	for value: float in decoded.to_float32_array():
		if not is_finite(value):
			return {"ok": false, "error": "blend_jacobian_nonfinite"}
	var image := Image.create_from_data(width, height, false, Image.FORMAT_RGBAF, decoded)
	if image == null:
		return {"ok": false, "error": "blend_jacobian_image_creation"}
	return {"ok": true, "texture": ImageTexture.create_from_image(image), "bytes": decoded.size()}

static func _prepare_error(colliders: Array, message: String) -> Dictionary:
	_dispose([{"colliders": colliders}])
	return {"ok": false, "error": message}

static func _dispose(parts: Array) -> void:
	for part: Dictionary in parts:
		for collider: Dictionary in part.get("colliders", []):
			(collider.node as Node).free()

static func _error(result: Dictionary, message: String) -> Dictionary:
	result.errors.append(message)
	return result
