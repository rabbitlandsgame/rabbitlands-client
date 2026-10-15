@tool
class_name MapAuthoringTexturePresets
extends RefCounted

## Small, named material library for the map-authoring preview. Every call
## returns a new material so changing one style cannot edit another style.

const CUSTOM := "Custom"
const GRASS := "Grass"
const WORN_EARTH := "Worn earth"
const SOIL := "Soil"
const SAND := "Sand"
const DESERT := "Desert"
const TIMBER := "Timber"
const STONE := "Stone"
const THATCH := "Thatch"
const TEXTILE := "Textile"
const CANVAS := "Canvas"
const METAL := "Metal"
const LEATHER := "Leather"
const HIDE := "Hide"
const BONE := "Bone"
const CRYSTAL := "Crystal"
const CAVERN := "Cavern"
const SLATE := "Slate"
const MOOR_PEAT_HEATHER := "Moor peat heather"
const DELTA_SILT := "Delta silt"
const COASTAL_LIMESTONE_GRAVEL := "Coastal limestone gravel"
const ALPINE_SCREE_LICHEN := "Alpine scree lichen"
const FOREST_FLOOR_MOSS := "Forest floor moss"
const ALPINE_SNOW_CRUST := "Alpine snow crust"
const WEATHERED_LIMESTONE_MASONRY := "Weathered limestone masonry"
const JADE_MASONRY := "Jade masonry"
const MARINE_TIMBER := "Marine timber"
const REED_THATCH := "Reed thatch"

const PRESET_NAMES := [
	CUSTOM, GRASS, WORN_EARTH, SOIL, SAND, DESERT, TIMBER, STONE, THATCH, TEXTILE, CANVAS,
	METAL, LEATHER, HIDE, BONE, CRYSTAL, CAVERN, SLATE,
	MOOR_PEAT_HEATHER, DELTA_SILT, COASTAL_LIMESTONE_GRAVEL,
	ALPINE_SCREE_LICHEN, FOREST_FLOOR_MOSS, ALPINE_SNOW_CRUST,
	WEATHERED_LIMESTONE_MASONRY, JADE_MASONRY, MARINE_TIMBER, REED_THATCH,
]

const ROAD_MESH_UV_DENSITY := 0.24
const _TEXTURE_ROOT := "res://src/dev/map_authoring_pilot/style/textures/"
const _WORN_PATH_SHADER := preload("res://src/dev/map_authoring_pilot/style/worn_path.gdshader")
const _ORIENTED_PBR_SHADER := preload(
	"res://src/dev/map_authoring_pilot/style/oriented_pbr.gdshader")
static var _oriented_shader_variants := {}

# Values with a direct Last Lantern or Sunmane authoring equivalent keep its
# tint and scale. The other families use restrained neutral tints and scales
# based on their authored real-world repeat size.
const _PRESETS := {
	GRASS: {
		"family": "ground", "tint": Color(0.78, 0.86, 0.72, 1.0),
		"roughness": 1.0, "normal_strength": 0.75, "density": 0.24,
	},
	WORN_EARTH: {
		"family": "ground", "tint": Color(0.60, 0.48, 0.31, 1.0),
		"roughness": 1.0, "normal_strength": 0.72, "density": 0.24,
	},
	SOIL: {
		"family": "ground", "tint": Color(0.43, 0.30, 0.18, 1.0),
		"roughness": 1.0, "normal_strength": 0.72, "density": 0.24,
	},
	# The licensed ground pattern reads cleanly as sand with a warmer, lighter
	# tint; keeping the same maps avoids introducing an unlicensed asset.
	SAND: {
		"family": "ground", "tint": Color(0.86, 0.72, 0.47, 1.0),
		"roughness": 0.96, "normal_strength": 0.48, "density": 0.20,
	},
	# Sunmane's authored desert has its own painterly albedo, while the existing
	# ground micro-normal and ORM keep its PBR response subtle and consistent.
	DESERT: {
		"family": "desert", "detail_family": "ground",
		"tint": Color(0.90, 0.82, 0.68, 1.0),
		"roughness": 1.0, "normal_strength": 0.50, "density": 0.20,
	},
	TIMBER: {
		"family": "timber", "tint": Color(0.65, 0.64, 0.59, 1.0),
		"roughness": 0.86, "normal_strength": 0.8, "density": 0.5,
	},
	STONE: {
		"family": "stone", "tint": Color(0.48, 0.56, 0.56, 1.0),
		"roughness": 1.0, "normal_strength": 0.72, "density": 0.8,
	},
	THATCH: {
		"family": "thatch", "tint": Color(1.0, 0.94, 0.76, 1.0),
		"roughness": 0.92, "normal_strength": 0.7, "density": 0.56,
	},
	TEXTILE: {
		"family": "textile", "tint": Color(0.58, 0.45, 0.25, 1.0),
		"roughness": 0.86, "normal_strength": 0.65, "density": 2.0,
	},
	CANVAS: {
		"family": "canvas", "tint": Color(0.78, 0.77, 0.65, 1.0),
		"roughness": 0.88, "normal_strength": 0.65, "density": 1.2,
	},
	METAL: {
		"family": "metal", "tint": Color.WHITE,
		"roughness": 0.44, "normal_strength": 0.75, "density": 2.0,
		"metallic": 1.0,
	},
	LEATHER: {
		"family": "leather", "tint": Color(0.28, 0.25, 0.19, 1.0),
		"roughness": 0.70, "normal_strength": 0.7, "density": 1.0,
	},
	HIDE: {
		"family": "hide", "tint": Color(0.92, 0.88, 0.78, 1.0),
		"roughness": 0.86, "normal_strength": 0.6, "density": 1.1,
	},
	BONE: {
		"family": "bone", "tint": Color(0.90, 0.86, 0.72, 1.0),
		"roughness": 0.52, "normal_strength": 0.65, "density": 1.67,
	},
	CRYSTAL: {
		"family": "crystal", "tint": Color(0.72, 0.56, 0.86, 1.0),
		"roughness": 0.18, "normal_strength": 0.8, "density": 0.9,
	},
	CAVERN: {
		"family": "cavern", "tint": Color(0.66, 0.62, 0.56, 1.0),
		"roughness": 0.93, "normal_strength": 0.72, "density": 0.23,
	},
	MOOR_PEAT_HEATHER: {
		"family": "moor-peat-heather", "detail_family": "ground",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/moor-peat-heather/moor-peat-heather-v001.png",
		"tint": Color.WHITE, "roughness": 0.98, "normal_strength": 0.65,
		"density": 0.25, "world_density": 0.25,
	},
	DELTA_SILT: {
		"family": "delta-silt", "detail_family": "ground",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/delta-silt/delta-silt-v001.png",
		"tint": Color.WHITE, "roughness": 0.98, "normal_strength": 0.45,
		"density": 0.25, "world_density": 0.25,
	},
	COASTAL_LIMESTONE_GRAVEL: {
		"family": "coastal-limestone-gravel", "detail_family": "stone",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/coastal-limestone-gravel/coastal-limestone-gravel-v001.png",
		"tint": Color.WHITE, "roughness": 0.94, "normal_strength": 0.75,
		"density": 0.25, "world_density": 0.25,
	},
	ALPINE_SCREE_LICHEN: {
		"family": "alpine-scree-lichen", "detail_family": "stone",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/alpine-scree-lichen/alpine-scree-lichen-v001.png",
		"tint": Color.WHITE, "roughness": 0.97, "normal_strength": 0.80,
		"density": 0.25, "world_density": 0.25,
	},
	FOREST_FLOOR_MOSS: {
		"family": "forest-floor-moss", "detail_family": "ground",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/forest-floor-moss/forest-floor-moss-v001.png",
		"tint": Color.WHITE, "roughness": 0.96, "normal_strength": 0.65,
		"density": 0.25, "world_density": 0.25,
	},
	ALPINE_SNOW_CRUST: {
		"family": "alpine-snow-crust", "detail_family": "ground",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/alpine-snow-crust/alpine-snow-crust-v002.png",
		"tint": Color.WHITE, "roughness": 0.88, "normal_strength": 0.65,
		"density": 0.25, "world_density": 0.25,
	},
	WEATHERED_LIMESTONE_MASONRY: {
		"family": "weathered-limestone-masonry", "detail_family": "stone",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/weathered-limestone-masonry/weathered-limestone-masonry-v001.png",
		"tint": Color.WHITE, "roughness": 0.95, "normal_strength": 0.78,
		"density": 0.8,
	},
	JADE_MASONRY: {
		"family": "jade-masonry", "detail_family": "stone",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/jade-masonry/jade-masonry-v001.png",
		"tint": Color.WHITE, "roughness": 0.72, "normal_strength": 0.65,
		"density": 0.8,
	},
	MARINE_TIMBER: {
		"family": "marine-timber", "detail_family": "timber",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/marine-timber/marine-timber-v001.png",
		"tint": Color.WHITE, "roughness": 0.84, "normal_strength": 0.80,
		"density": 0.5,
	},
	REED_THATCH: {
		"family": "reed-thatch", "detail_family": "thatch",
		"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/reed-thatch/reed-thatch-v001.png",
		"tint": Color.WHITE, "roughness": 0.94, "normal_strength": 0.70,
		"density": 0.56,
	},
}


static func create_material(preset: String) -> Material:
	if preset == SLATE:
		var slate := StandardMaterial3D.new()
		slate.albedo_color = Color(0.095, 0.17, 0.20, 1.0)
		slate.roughness = 0.55
		slate.uv1_scale = Vector3(0.8, 0.8, 0.8)
		slate.uv1_triplanar = true
		slate.uv1_world_triplanar = true
		slate.cull_mode = BaseMaterial3D.CULL_DISABLED
		return slate
	if not _PRESETS.has(preset):
		return null
	var spec: Dictionary = _PRESETS[preset]
	var family: String = spec["family"]
	var detail_family: String = spec.get("detail_family", family)
	var material := ORMMaterial3D.new()
	material.albedo_color = spec["tint"]
	material.albedo_texture = _preset_texture(spec, family, "basecolor")
	material.roughness = spec["roughness"]
	material.metallic = spec.get("metallic", 0.0)
	material.normal_enabled = true
	material.normal_scale = spec["normal_strength"]
	material.normal_texture = _texture(detail_family, "normal")
	material.orm_texture = _texture(detail_family, "orm")
	material.uv1_scale = Vector3.ONE * float(spec["density"])
	material.uv1_triplanar = true
	material.uv1_world_triplanar = true
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material


static func create_road_material(preset: String) -> ShaderMaterial:
	if preset == CUSTOM or not _PRESETS.has(preset) and preset != SLATE:
		return null
	var material := ShaderMaterial.new()
	material.render_priority = 1
	material.shader = _WORN_PATH_SHADER
	if preset == SLATE:
		# The road shader always needs a complete texture triplet. Slate keeps its
		# established colour while borrowing unobtrusive stone surface detail.
		material.set_shader_parameter("ground_albedo", _texture("stone", "basecolor"))
		material.set_shader_parameter("ground_normal", _texture("stone", "normal"))
		material.set_shader_parameter("ground_orm", _texture("stone", "orm"))
		material.set_shader_parameter("worn_tint", Color(0.095, 0.17, 0.20, 1.0))
		material.set_shader_parameter("texture_scale", 0.8 / ROAD_MESH_UV_DENSITY)
		material.set_shader_parameter("roughness_multiplier", 0.55)
		material.set_shader_parameter("normal_strength", 0.72)
	else:
		var spec: Dictionary = _PRESETS[preset]
		var family: String = spec["family"]
		var detail_family: String = spec.get("detail_family", family)
		material.set_shader_parameter("ground_albedo",
			_preset_texture(spec, family, "basecolor"))
		material.set_shader_parameter("ground_normal", _texture(detail_family, "normal"))
		material.set_shader_parameter("ground_orm", _texture(detail_family, "orm"))
		material.set_shader_parameter("worn_tint", spec["tint"])
		material.set_shader_parameter(
			"texture_scale", float(spec["density"]) / ROAD_MESH_UV_DENSITY)
		material.set_shader_parameter("roughness_multiplier", 1.0)
		material.set_shader_parameter("normal_strength", spec["normal_strength"])
	material.set_shader_parameter("edge_feather", 0.16)
	return material


## Generated ground packs declare their intended repeat in world metres.
## Terrain already scales local XZ by its saved preview density, so a bound
## terrain Surface stores the compensating material scale. Other presets keep
## their established authored scale unchanged.
static func region_uv_scale(preset: String,
		base_uv_metres_inverse: float) -> float:
	if base_uv_metres_inverse <= 0.0 or not _PRESETS.has(preset):
		return 0.0
	var world_density := float((_PRESETS[preset] as Dictionary).get(
		"world_density", 0.0))
	return world_density / base_uv_metres_inverse if world_density > 0.0 else 0.0


static func create_oriented_material(source: Material,
		rotation_degrees: float, force_shader: bool = false) -> Material:
	if source == null or is_zero_approx(rotation_degrees) and not force_shader:
		return source
	if source is ShaderMaterial:
		var shader_material := source as ShaderMaterial
		if shader_material.shader != _WORN_PATH_SHADER:
			return null
		var oriented_road := shader_material.duplicate(true) as ShaderMaterial
		oriented_road.set_shader_parameter(
			"texture_rotation_radians", deg_to_rad(rotation_degrees))
		return oriented_road
	if not source is BaseMaterial3D:
		return null
	var base := source as BaseMaterial3D
	if not _has_only_supported_base_features(base):
		return null
	var oriented := ShaderMaterial.new()
	oriented.resource_name = base.resource_name
	oriented.render_priority = base.render_priority
	oriented.next_pass = base.next_pass
	oriented.shader = _oriented_shader_variant(base)
	oriented.set_shader_parameter("albedo_map", base.albedo_texture)
	oriented.set_shader_parameter("normal_map", base.normal_texture)
	oriented.set_shader_parameter("use_albedo_map", base.albedo_texture != null)
	oriented.set_shader_parameter("use_normal_map",
		base.normal_enabled and base.normal_texture != null)
	oriented.set_shader_parameter("albedo_tint", base.albedo_color)
	oriented.set_shader_parameter("roughness_value", base.roughness)
	oriented.set_shader_parameter("metallic_value", base.metallic)
	oriented.set_shader_parameter("normal_strength", base.normal_scale)
	oriented.set_shader_parameter("uv_scale", base.uv1_scale)
	oriented.set_shader_parameter("uv_offset", base.uv1_offset)
	oriented.set_shader_parameter("use_triplanar", base.uv1_triplanar)
	oriented.set_shader_parameter("use_world_triplanar", base.uv1_world_triplanar)
	oriented.set_shader_parameter("triplanar_sharpness", base.uv1_triplanar_sharpness)
	oriented.set_shader_parameter(
		"texture_rotation_radians", deg_to_rad(rotation_degrees))
	if base is ORMMaterial3D:
		var orm := base as ORMMaterial3D
		oriented.set_shader_parameter("orm_map", orm.orm_texture)
		oriented.set_shader_parameter("use_orm_map", orm.orm_texture != null)
	return oriented


static func _oriented_shader_variant(base: BaseMaterial3D) -> Shader:
	var variant_key := [base.cull_mode, base.texture_filter, base.texture_repeat]
	if _oriented_shader_variants.has(variant_key):
		return _oriented_shader_variants[variant_key]
	var cull_mode := "cull_disabled"
	match base.cull_mode:
		BaseMaterial3D.CULL_BACK:
			cull_mode = "cull_back"
		BaseMaterial3D.CULL_FRONT:
			cull_mode = "cull_front"
	var texture_filter := "filter_linear_mipmap_anisotropic"
	match base.texture_filter:
		BaseMaterial3D.TEXTURE_FILTER_NEAREST:
			texture_filter = "filter_nearest"
		BaseMaterial3D.TEXTURE_FILTER_LINEAR:
			texture_filter = "filter_linear"
		BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS:
			texture_filter = "filter_nearest_mipmap"
		BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS:
			texture_filter = "filter_linear_mipmap"
		BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS_ANISOTROPIC:
			texture_filter = "filter_nearest_mipmap_anisotropic"
	var repeat_mode := "repeat_enable" if base.texture_repeat else "repeat_disable"
	var shader := Shader.new()
	shader.code = _ORIENTED_PBR_SHADER.code.replace(
		"cull_disabled", cull_mode).replace(
		"filter_linear_mipmap_anisotropic", texture_filter).replace(
		"repeat_enable", repeat_mode)
	_oriented_shader_variants[variant_key] = shader
	return shader


static func _has_only_supported_base_features(base: BaseMaterial3D) -> bool:
	var baseline: BaseMaterial3D = (ORMMaterial3D.new()
		if base is ORMMaterial3D else StandardMaterial3D.new())
	var supported := {
		&"resource_local_to_scene": true, &"resource_name": true,
		&"next_pass": true, &"render_priority": true,
		&"albedo_color": true, &"albedo_texture": true,
		&"metallic": true, &"roughness": true,
		&"normal_enabled": true, &"normal_scale": true,
		&"normal_texture": true, &"orm_texture": true,
		&"uv1_scale": true, &"uv1_offset": true,
		&"uv1_triplanar": true, &"uv1_world_triplanar": true,
		&"uv1_triplanar_sharpness": true,
		&"texture_filter": true, &"texture_repeat": true,
		&"cull_mode": true,
	}
	for property: Dictionary in base.get_property_list():
		var property_name := StringName(property.name)
		if supported.has(property_name) or \
				(int(property.usage) & PROPERTY_USAGE_STORAGE) == 0:
			continue
		if base.get(property_name) != baseline.get(property_name):
			return false
	return true


static func _texture(family: String, map_name: String) -> Texture2D:
	return load(_TEXTURE_ROOT + family + "-" + map_name + ".png") as Texture2D


static func _preset_texture(spec: Dictionary, family: String,
		map_name: String) -> Texture2D:
	if map_name == "basecolor" and spec.has("albedo_path"):
		return load(String(spec.albedo_path)) as Texture2D
	return _texture(family, map_name)
