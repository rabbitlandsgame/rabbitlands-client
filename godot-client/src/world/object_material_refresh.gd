class_name ObjectMaterialRefresh
extends RefCounted

const SCHEMA := "eloria-object-material-overrides-v1"
const CATALOG_PATH := "res://assets/world/biome_blend/object-materials.json"
const ORIENTED_SHADER := preload(
	"res://src/dev/map_authoring_pilot/style/oriented_pbr.gdshader")
const BiomeBlendMaterial := preload("res://src/world/biome_blend_material.gd")


static func apply_catalog(manifest_data: Dictionary,
		mesh_instances: Array) -> int:
	if manifest_data.has("objectMaterialOverrides"):
		var inline: Variant = _records_for_manifest(manifest_data, {})
		if not inline is Array:
			push_warning("Child object material overrides are invalid; imported materials remain active.")
			return 0
		return apply_overrides(inline, mesh_instances)
	var parsed: Variant = BiomeBlendMaterial.cached_json(CATALOG_PATH)
	if not parsed is Dictionary or String(parsed.get("schema", "")) != SCHEMA or \
			not parsed.get("assets") is Dictionary:
		push_warning("Object material catalog is invalid; imported materials remain active.")
		return 0
	var overrides: Variant = _records_for_manifest(manifest_data, parsed)
	if not overrides is Array:
		return 0
	return apply_overrides(overrides, mesh_instances)


static func _records_for_manifest(manifest_data: Dictionary,
		catalog: Dictionary) -> Variant:
	# Presence is authority. A normal export can deliberately emit an empty
	# list, which must not fall through to a stale color-refresh catalog.
	if manifest_data.has("objectMaterialOverrides"):
		var inline: Variant = manifest_data.get("objectMaterialOverrides")
		if not inline is Dictionary or String(inline.get("schema", "")) != SCHEMA or \
				not inline.get("entries") is Array:
			return null
		return inline.entries
	if String(catalog.get("schema", "")) != SCHEMA or \
			not catalog.get("assets") is Dictionary:
		return null
	var asset_id := String(manifest_data.get("asset", {}).get("id", ""))
	return catalog.assets.get(asset_id)


static func apply_overrides(overrides: Array, mesh_instances: Array) -> int:
	var by_name := {}
	for value: Variant in mesh_instances:
		var node := value as MeshInstance3D
		if node == null:
			continue
		var key := String(node.name)
		if not by_name.has(key):
			by_name[key] = []
		(by_name[key] as Array).append(node)
	var applied := 0
	for raw in overrides:
		if not raw is Dictionary:
			continue
		var node_name := String(raw.get("nodeName", ""))
		var matches: Array = by_name.get(node_name, [])
		if matches.size() != 1:
			push_warning("Object material target must resolve once: %s" % node_name)
			continue
		var node := matches[0] as MeshInstance3D
		var surface_index := int(raw.get("surfaceIndex", -1))
		if node.mesh == null or surface_index < 0 or \
				surface_index >= node.mesh.get_surface_count():
			push_warning("Object material surface is invalid: %s[%d]" % [
				node_name, surface_index])
			continue
		var material := create_material(raw.get("material", {}))
		if material == null:
			continue
		node.set_surface_override_material(surface_index, material)
		applied += 1
	return applied


static func create_material(record: Dictionary) -> ShaderMaterial:
	var albedo: Texture2D = _verified_texture(record, "albedoTexture")
	if albedo == null:
		return null
	var normal: Texture2D = _verified_texture(record, "normalTexture", true)
	var orm: Texture2D = _verified_texture(record, "ormTexture", true)
	var normal_path := _string_or_empty(record.get("normalTexture"))
	var orm_path := _string_or_empty(record.get("ormTexture"))
	if (not normal_path.is_empty() and normal == null) or \
			(not orm_path.is_empty() and orm == null):
		return null
	var material := ShaderMaterial.new()
	material.resource_name = "authored_object_%s" % String(record.get("preset", "surface"))
	material.shader = ORIENTED_SHADER
	material.set_shader_parameter(&"albedo_map", albedo)
	material.set_shader_parameter(&"use_albedo_map", true)
	material.set_shader_parameter(&"normal_map", normal)
	material.set_shader_parameter(&"use_normal_map", normal != null)
	material.set_shader_parameter(&"orm_map", orm)
	material.set_shader_parameter(&"use_orm_map", orm != null)
	material.set_shader_parameter(&"albedo_tint", _color(record.get(
		"albedoColor", [1.0, 1.0, 1.0, 1.0])))
	material.set_shader_parameter(&"roughness_value", float(record.get("roughness", 1.0)))
	material.set_shader_parameter(&"metallic_value", float(record.get("metallic", 0.0)))
	material.set_shader_parameter(&"normal_strength", float(record.get(
		"normalStrength", 1.0)))
	var scale := _vec2(record.get("uvScale", [1.0, 1.0]))
	var offset := _vec2(record.get("uvOffset", [0.0, 0.0]))
	material.set_shader_parameter(&"uv_scale", Vector3(scale.x, scale.y, 1.0))
	material.set_shader_parameter(&"uv_offset", Vector3(offset.x, offset.y, 0.0))
	material.set_shader_parameter(&"use_triplanar", false)
	material.set_shader_parameter(&"use_world_triplanar", false)
	material.set_shader_parameter(&"texture_rotation_radians", deg_to_rad(float(
		record.get("rotationDegrees", 0.0))))
	return material


static func _verified_texture(record: Dictionary, key: String,
		optional: bool = false) -> Texture2D:
	var path := _string_or_empty(record.get(key))
	if path.is_empty():
		return null if optional else _warn_texture(path)
	var hashes: Variant = record.get("textureSha256")
	var expected := _string_or_empty(hashes.get(key)) if hashes is Dictionary else ""
	var texture := load(path) as Texture2D
	if not path.begins_with("res://") or expected.length() != 64 or texture == null:
		return _warn_texture(path)
	var absolute := ProjectSettings.globalize_path(path)
	if FileAccess.file_exists(absolute) and \
			BiomeBlendMaterial.source_sha256(path) != expected:
		return _warn_texture(path)
	return texture


static func _string_or_empty(value: Variant) -> String:
	return value if value is String else ""


static func _warn_texture(path: String) -> Texture2D:
	push_warning("Object material texture is missing or changed: %s" % path)
	return null


static func _vec2(value: Variant) -> Vector2:
	return Vector2(float(value[0]), float(value[1]))


static func _color(value: Variant) -> Color:
	return Color(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
