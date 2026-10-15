class_name BiomeBlendMaterial
extends RefCounted

const SCHEMA := "eloria-biome-blend-v1"
const SHADER := preload("res://src/world/biome_blend.gdshader")
const CATALOG_PATH := "res://assets/world/biome_blend/catalog.json"

static var _white_texture: Texture2D
static var _base_only_mask: Texture2D
static var _zero_mask: Texture2D
static var _source_hash_cache := {}
static var _json_cache := {}
static var _json_generation := 0
static var _catalog_index := {}
static var _catalog_index_generation := -1


## A preview refresh is an explicit source-observation boundary. Clearing here
## catches rapid same-size edits even on filesystems whose modification time
## has coarse resolution; calls within that refresh still share each digest.
static func begin_source_verification() -> void:
	_source_hash_cache.clear()
	_json_cache.clear()
	_json_generation += 1
	_catalog_index.clear()
	_catalog_index_generation = -1


static func source_sha256(path: String) -> String:
	if path.is_empty():
		return ""
	var absolute := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(absolute):
		return ""
	var file := FileAccess.open(absolute, FileAccess.READ)
	if file == null:
		return ""
	var size := file.get_length()
	file.close()
	var modified := FileAccess.get_modified_time(absolute)
	var cached: Variant = _source_hash_cache.get(absolute)
	if cached is Dictionary and int(cached.get("size", -1)) == size and \
			int(cached.get("modified", -1)) == modified:
		return String(cached.get("sha256", ""))
	var digest := FileAccess.get_sha256(absolute)
	_source_hash_cache[absolute] = {
		"size": size, "modified": modified, "sha256": digest}
	return digest


## Parses portable JSON once per physical file revision. The virtual res://
## path remains the source of bytes so this works inside a PCK; a checkout's
## modification time and length provide cheap invalidation between refreshes.
static func cached_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	var stamp := _resource_stamp(path)
	var cached: Variant = _json_cache.get(path)
	if cached is Dictionary and cached.get("stamp") == stamp:
		return cached.get("document")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_json_generation += 1
	_json_cache[path] = {"stamp": stamp, "document": parsed,
		"generation": _json_generation}
	return parsed


static func _resource_stamp(path: String) -> Array:
	var absolute := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(absolute):
		return ["packed"]
	var file := FileAccess.open(absolute, FileAccess.READ)
	if file == null:
		return ["unreadable"]
	var size := file.get_length()
	file.close()
	return [FileAccess.get_modified_time(absolute), size]


static func create_runtime(config: Dictionary,
		continent_translation: Vector3) -> ShaderMaterial:
	if not _valid_config(config):
		return null
	var base_mask := _verified_texture(config.baseMask)
	var secondary_mask := _verified_texture(config.secondaryMask)
	if base_mask == null or secondary_mask == null or \
			not _verified_palette_textures(config.palettes):
		return null
	var material := _create(config.palettes, base_mask, secondary_mask,
		_array_vec2(config.origin), float(config.metresPerPixel),
		continent_translation)
	material.set_meta(&"biome_blend_config", config.duplicate(true))
	return material


static func catalog_config(manifest_data: Dictionary) -> Variant:
	var asset_id := String(manifest_data.get("asset", {}).get("id", ""))
	if "__chunk_" not in asset_id:
		return null
	var suffix := asset_id.get_slice("__chunk_", 1).split("_", false)
	if suffix.size() != 2 or not suffix[0].is_valid_int() or \
			not suffix[1].is_valid_int():
		return null
	var parsed: Variant = cached_json(CATALOG_PATH)
	if not parsed is Dictionary or String(parsed.get("schema", "")) != \
			"eloria-biome-blend-catalog-v1" or not parsed.get("chunks") is Array:
		return null
	var chunk_metres := float(parsed.get("chunkMetres", 0.0))
	if chunk_metres <= 0.0:
		return null
	var cache_generation := int((_json_cache.get(CATALOG_PATH, {}) as Dictionary).get(
		"generation", -1))
	if _catalog_index_generation != cache_generation:
		_catalog_index.clear()
		for raw in parsed.chunks:
			if not raw is Dictionary or not raw.get("origin") is Array or \
					raw.origin.size() != 2:
				continue
			var origin := _array_vec2(raw.origin)
			var key := Vector2i(roundi(origin.x / chunk_metres),
				roundi(origin.y / chunk_metres))
			_catalog_index[key] = raw
		_catalog_index_generation = cache_generation
	var expected := Vector2i(int(suffix[0]), int(suffix[1]))
	var config: Variant = _catalog_index.get(expected)
	return config.duplicate(true) if config is Dictionary else null


static func with_palette_overrides(config: Dictionary,
		overrides: Dictionary) -> Dictionary:
	var result: Dictionary = config.duplicate(true)
	for palette: Dictionary in result.get("palettes", []):
		var region_id := String(palette.get("id", "")).get_slice(":", 0)
		if not overrides.has(region_id):
			continue
		var replacement: Dictionary = overrides[region_id]
		palette["base"] = replacement.get("base", palette.get("base", {})).duplicate(true)
		var secondary: Variant = replacement.get("secondary", palette.get("secondary"))
		palette["secondary"] = secondary.duplicate(true) \
			if secondary is Dictionary else null
	return result


static func create_editor(base_surface: MapAuthoringSurface,
		base_uv_metres_inverse: float, continent_translation: Vector3,
		secondary_entry: Resource = null) -> ShaderMaterial:
	if base_surface == null or not base_surface.source_material is BaseMaterial3D:
		return null
	var base := surface_palette(base_surface, base_uv_metres_inverse)
	if base.is_empty():
		return null
	var palette := {"id": "editor:base", "base": base, "secondary": null}
	if secondary_entry != null and secondary_entry.get("surface") is MapAuthoringSurface:
		var secondary := surface_palette(secondary_entry.get("surface"),
			base_uv_metres_inverse)
		if not secondary.is_empty():
			secondary["id"] = "editor:%s" % String(secondary_entry.get("id"))
			secondary["role"] = String(secondary_entry.get("role"))
			palette.secondary = secondary
	return _create([palette], _solid_mask(Color(1.0, 0.0, 0.0, 0.0), true),
		_solid_mask(Color(0.0, 0.0, 0.0, 0.0), false), Vector2.ZERO,
		1.5, continent_translation)


static func _create(palettes: Array, base_mask: Texture2D,
		secondary_mask: Texture2D, mask_origin: Vector2, metres_per_pixel: float,
		continent_translation: Vector3) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.resource_name = "continent_biome_blend"
	material.shader = SHADER
	material.set_shader_parameter(&"base_mask", base_mask)
	material.set_shader_parameter(&"secondary_mask", secondary_mask)
	material.set_shader_parameter(&"mask_origin", mask_origin)
	material.set_shader_parameter(&"mask_metres_per_pixel", metres_per_pixel)
	material.set_shader_parameter(&"mask_size", 66.0)
	material.set_shader_parameter(&"terrain_to_continent",
		Transform3D(Basis.IDENTITY, continent_translation))
	var values := _default_uniforms()
	for index in mini(palettes.size(), 4):
		var palette: Dictionary = palettes[index]
		_apply_palette(material, values, index, palette.get("base", {}), false)
		var secondary: Variant = palette.get("secondary")
		_apply_palette(material, values, index,
			secondary if secondary is Dictionary else palette.get("base", {}), true)
	for key: StringName in values:
		material.set_shader_parameter(key, values[key])
	return material


static func set_terrain_to_continent(material: ShaderMaterial,
		transform: Transform3D) -> void:
	if material != null:
		material.set_shader_parameter(&"terrain_to_continent", transform)


static func _apply_palette(material: ShaderMaterial, values: Dictionary,
		index: int, record: Dictionary, secondary: bool) -> void:
	var prefix := "secondary" if secondary else "base"
	var texture := load(String(record.get("albedoTexture", ""))) as Texture2D
	if texture == null:
		texture = _white()
	material.set_shader_parameter("%s_albedo_%d" % [prefix, index], texture)
	var color := _array_color(record.get("albedoColor", [1.0, 1.0, 1.0, 1.0]))
	values["%s_tint_%d" % [prefix, index]] = color
	_set_vector_component(values, "%s_uv_metres_inverse" % prefix, index,
		float(record.get("baseUvMetresInverse", 1.0)))
	var scale := _array_vec2(record.get("uvScale", [1.0, 1.0]))
	var offset := _array_vec2(record.get("uvOffset", [0.0, 0.0]))
	_set_vector_component(values, "%s_uv_scale_x" % prefix, index, scale.x)
	_set_vector_component(values, "%s_uv_scale_y" % prefix, index, scale.y)
	_set_vector_component(values, "%s_uv_offset_x" % prefix, index, offset.x)
	_set_vector_component(values, "%s_uv_offset_y" % prefix, index, offset.y)
	_set_vector_component(values, "%s_rotation_radians" % prefix, index,
		deg_to_rad(float(record.get("rotationDegrees", 0.0))))
	_set_vector_component(values, "%s_roughness" % prefix, index,
		float(record.get("roughness", 1.0)))
	_set_vector_component(values, "%s_metallic" % prefix, index,
		float(record.get("metallic", 0.0)))


static func surface_palette(surface: MapAuthoringSurface,
		base_uv_metres_inverse: float) -> Dictionary:
	var base := surface.source_material as BaseMaterial3D
	if base == null or base.uv1_triplanar or base.uv1_world_triplanar:
		return {}
	var record := {
		"preset": surface.texture_preset,
		"albedoTexture": base.albedo_texture.resource_path if base.albedo_texture else "",
		"albedoColor": [base.albedo_color.r, base.albedo_color.g,
			base.albedo_color.b, base.albedo_color.a],
		"roughness": base.roughness, "metallic": base.metallic,
		"normalStrength": base.normal_scale,
		"baseUvMetresInverse": base_uv_metres_inverse,
		"uvScale": [base.uv1_scale.x, base.uv1_scale.y],
		"uvOffset": [base.uv1_offset.x, base.uv1_offset.y],
		"rotationDegrees": surface.rotation_degrees,
	}
	if base.albedo_texture != null and not base.albedo_texture.resource_path.is_empty():
		record["textureSha256"] = {"albedoTexture": source_sha256(
			base.albedo_texture.resource_path)}
	return record


static func _valid_config(config: Dictionary) -> bool:
	if String(config.get("schema", "")) != SCHEMA or \
			String(config.get("coordinateSpace", "")) != "continent-global-xz":
		return false
	var inner_size: Variant = config.get("innerSize")
	if not inner_size is Array or inner_size.size() != 2 or \
			not is_equal_approx(float(inner_size[0]), 64.0) or \
			not is_equal_approx(float(inner_size[1]), 64.0) or \
			int(config.get("gutter", -1)) != 1 or \
			not is_equal_approx(float(config.get("metresPerPixel", 0.0)), 1.5):
		return false
	var palettes: Variant = config.get("palettes")
	return palettes is Array and not palettes.is_empty() and palettes.size() <= 4 and \
		config.get("origin") is Array and config.origin.size() == 2 and \
		config.get("baseMask") is Dictionary and \
		config.get("secondaryMask") is Dictionary


static func _verified_texture(record: Dictionary) -> Texture2D:
	var path := String(record.get("path", ""))
	var expected := String(record.get("sha256", ""))
	if not path.begins_with("res://") or expected.length() != 64:
		return null
	var texture := load(path) as Texture2D
	if texture == null:
		push_warning("Biome blend mask is missing or changed: %s" % path)
		return null
	# Source PNG bytes exist in editor/dev layouts and are hash checked there.
	# Exported PCKs may contain only the imported Texture2D remap; the normal
	# build validates the same source hash before packaging, while runtime loads
	# the portable res:// resource through ResourceLoader.
	var absolute := ProjectSettings.globalize_path(path)
	if FileAccess.file_exists(absolute) and source_sha256(path) != expected:
		push_warning("Biome blend mask is missing or changed: %s" % path)
		return null
	return texture


static func _verified_palette_textures(palettes: Array) -> bool:
	for palette: Dictionary in palettes:
		if not _verified_palette_texture(palette.get("base", {})):
			return false
		var secondary: Variant = palette.get("secondary")
		if secondary is Dictionary and not _verified_palette_texture(secondary):
			return false
	return true


static func _verified_palette_texture(record: Dictionary) -> bool:
	var path := String(record.get("albedoTexture", ""))
	if path.is_empty():
		return true
	var hashes: Variant = record.get("textureSha256")
	var expected := String(hashes.get("albedoTexture", "")) \
		if hashes is Dictionary else ""
	if not path.begins_with("res://") or expected.length() != 64 or \
			(load(path) as Texture2D) == null:
		push_warning("Biome blend palette texture is missing or changed: %s" % path)
		return false
	var absolute := ProjectSettings.globalize_path(path)
	if FileAccess.file_exists(absolute) and source_sha256(path) != expected:
		push_warning("Biome blend palette texture is missing or changed: %s" % path)
		return false
	return true


static func _default_uniforms() -> Dictionary:
	var result := {}
	for prefix in ["base", "secondary"]:
		for index in 4:
			result["%s_tint_%d" % [prefix, index]] = Color.WHITE
		for name in ["uv_metres_inverse", "uv_scale_x", "uv_scale_y", "roughness"]:
			result["%s_%s" % [prefix, name]] = Vector4.ONE
		for name in ["uv_offset_x", "uv_offset_y", "rotation_radians", "metallic"]:
			result["%s_%s" % [prefix, name]] = Vector4.ZERO
	return result


static func _set_vector_component(values: Dictionary, key: String,
		index: int, value: float) -> void:
	var vector: Vector4 = values[key]
	vector[index] = value
	values[key] = vector


static func _solid_mask(color: Color, base: bool) -> Texture2D:
	if base and _base_only_mask != null:
		return _base_only_mask
	if not base and _zero_mask != null:
		return _zero_mask
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.set_pixel(0, 0, color)
	var texture := ImageTexture.create_from_image(image)
	if base:
		_base_only_mask = texture
	else:
		_zero_mask = texture
	return texture


static func _white() -> Texture2D:
	if _white_texture == null:
		var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
		image.fill(Color.WHITE)
		_white_texture = ImageTexture.create_from_image(image)
	return _white_texture


static func _array_vec2(value: Variant) -> Vector2:
	return Vector2(float(value[0]), float(value[1]))


static func _array_color(value: Variant) -> Color:
	return Color(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
