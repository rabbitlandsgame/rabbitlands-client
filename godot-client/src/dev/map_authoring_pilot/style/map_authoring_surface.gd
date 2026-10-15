@tool
class_name MapAuthoringSurface
extends Resource

## One object's saved surface choice. The source material is the authored data;
## rotated derivatives live only in the private runtime backend.

enum MaterialMode {
	SURFACE,
	ROAD_SHADER,
}

var _material_choices := {}
var _backend := MapAuthoringVisualStyle.new()
var _region_uv_projection := false
var _region_uv_metres_inverse := 0.0

# Keep this order: loading must establish the factory mode and preset before it
# restores a hand-edited source material from the resource file.
@export_storage var material_mode := MaterialMode.SURFACE:
	set(value):
		var bounded := clampi(value, MaterialMode.SURFACE, MaterialMode.ROAD_SHADER)
		if material_mode == bounded:
			return
		_remember_current_choice()
		material_mode = bounded
		source_material = _material_for_choice(texture_preset, source_material)
		_sync_backend()
		_finish_editor_change()

@export_enum("Custom", "Grass", "Worn earth", "Soil", "Sand", "Desert", "Timber",
	"Stone", "Thatch", "Textile", "Canvas", "Metal", "Leather", "Hide",
	"Bone", "Crystal", "Cavern", "Slate", "Moor peat heather", "Delta silt",
	"Coastal limestone gravel", "Alpine scree lichen", "Forest floor moss",
	"Alpine snow crust", "Weathered limestone masonry", "Jade masonry",
	"Marine timber", "Reed thatch") var texture_preset := \
	MapAuthoringTexturePresets.CUSTOM:
	set(value):
		if texture_preset == value:
			return
		_remember_current_choice()
		texture_preset = value
		source_material = _material_for_choice(value, source_material)
		_finish_editor_change()

@export_range(-180.0, 180.0, 1.0, "degrees") var rotation_degrees := 0.0:
	set(value):
		var bounded := clampf(value, -180.0, 180.0)
		if is_equal_approx(rotation_degrees, bounded):
			return
		rotation_degrees = bounded
		_sync_backend_rotation()
		emit_changed()

@export var show_advanced_materials := false:
	set(value):
		if show_advanced_materials == value:
			return
		show_advanced_materials = value
		notify_property_list_changed()
		emit_changed()

@export var source_material: Material:
	set(value):
		if source_material == value:
			return
		source_material = value
		_sync_backend_source()
		emit_changed()

## Terrain base surfaces opt in explicitly. Existing Custom surfaces retain
## their exact single-material appearance until an author enables blending.
@export var biome_blend_enabled := false:
	set(value):
		if biome_blend_enabled == value:
			return
		biome_blend_enabled = value
		emit_changed()


func _init() -> void:
	resource_local_to_scene = true
	_sync_backend()


static func from_preset(preset: String,
		road_shader: bool = false) -> MapAuthoringSurface:
	var surface := MapAuthoringSurface.new()
	surface.material_mode = (MaterialMode.ROAD_SHADER
		if road_shader else MaterialMode.SURFACE)
	surface.texture_preset = preset
	return surface


static func from_material(source: Material,
		preset: String = MapAuthoringTexturePresets.CUSTOM,
		road_shader: bool = false) -> MapAuthoringSurface:
	var surface := MapAuthoringSurface.new()
	surface.material_mode = (MaterialMode.ROAD_SHADER
		if road_shader else MaterialMode.SURFACE)
	surface.texture_preset = preset
	surface.source_material = source.duplicate(true) as Material if source != null else null
	return surface


func get_material(extra_rotation_degrees: float = 0.0) -> Material:
	return _backend.get_material(_backend_slot(), extra_rotation_degrees)


## Region terrain and authored meshes provide stable metre-based UVs. Keep
## ordinary named preset choices on that explicit projection so preview and
## production export cannot silently depend on editor-only triplanar mapping.
## Custom materials retain their authored settings and are validated at bake.
func enable_region_uv_projection(base_uv_metres_inverse: float = 0.0) -> void:
	_region_uv_projection = true
	if base_uv_metres_inverse > 0.0:
		_region_uv_metres_inverse = base_uv_metres_inverse
	if texture_preset == MapAuthoringTexturePresets.CUSTOM or \
			not source_material is BaseMaterial3D:
		return
	var base := source_material as BaseMaterial3D
	# A triplanar preset has not yet been converted to the region's explicit UV
	# projection. Once converted, its UV scale is authored data: refreshes and
	# save/reopen must not replace a user's later Inspector edit merely because
	# the material still carries a named preset.
	var first_projection := base.uv1_triplanar or base.uv1_world_triplanar
	var changed := false
	var region_scale := MapAuthoringTexturePresets.region_uv_scale(texture_preset,
		_region_uv_metres_inverse)
	if first_projection and region_scale > 0.0 and \
			(not is_equal_approx(base.uv1_scale.x, region_scale) or
			not is_equal_approx(base.uv1_scale.y, region_scale)):
		base.uv1_scale = Vector3(region_scale, region_scale, base.uv1_scale.z)
		changed = true
	if base.uv1_triplanar or base.uv1_world_triplanar:
		base.uv1_triplanar = false
		base.uv1_world_triplanar = false
		changed = true
	if not changed:
		return
	_sync_backend_source()
	emit_changed()


func signature() -> Array:
	return [get_instance_id(), material_mode, texture_preset, rotation_degrees,
		biome_blend_enabled] + \
		_backend.rotation_signature()


func _validate_property(property: Dictionary) -> void:
	if StringName(property.name) != &"source_material":
		return
	if not show_advanced_materials and \
			texture_preset != MapAuthoringTexturePresets.CUSTOM:
		property.usage = int(property.usage) & ~PROPERTY_USAGE_EDITOR


func _backend_slot() -> String:
	return "road" if material_mode == MaterialMode.ROAD_SHADER else "terrain"


func _sync_backend() -> void:
	_backend.terrain_material = (source_material
		if material_mode == MaterialMode.SURFACE else null)
	_backend.worn_path_material = (source_material
		if material_mode == MaterialMode.ROAD_SHADER else null)
	_sync_backend_rotation()


func _sync_backend_source() -> void:
	if material_mode == MaterialMode.ROAD_SHADER:
		_backend.worn_path_material = source_material
	else:
		_backend.terrain_material = source_material


func _sync_backend_rotation() -> void:
	if material_mode == MaterialMode.ROAD_SHADER:
		_backend.road_texture_rotation_degrees = rotation_degrees
	else:
		_backend.terrain_texture_rotation_degrees = rotation_degrees


func _choice_key(preset: String = texture_preset) -> String:
	return "%d:%s" % [material_mode, preset]


func _remember_current_choice() -> void:
	if source_material != null:
		_material_choices[_choice_key()] = source_material


func _material_for_choice(preset: String, current: Material) -> Material:
	var key := _choice_key(preset)
	if _material_choices.has(key):
		return _region_uv_material(_material_choices[key], preset)
	if preset == MapAuthoringTexturePresets.CUSTOM:
		return current
	if material_mode == MaterialMode.ROAD_SHADER:
		return MapAuthoringTexturePresets.create_road_material(preset)
	return _region_uv_material(MapAuthoringTexturePresets.create_material(preset),
		preset)


func _region_uv_material(material: Material, preset: String) -> Material:
	if not _region_uv_projection or preset == MapAuthoringTexturePresets.CUSTOM or \
			not material is BaseMaterial3D:
		return material
	var base := material as BaseMaterial3D
	var first_projection := base.uv1_triplanar or base.uv1_world_triplanar
	var region_scale := MapAuthoringTexturePresets.region_uv_scale(preset,
		_region_uv_metres_inverse)
	if first_projection and region_scale > 0.0:
		base.uv1_scale = Vector3(region_scale, region_scale, base.uv1_scale.z)
	base.uv1_triplanar = false
	base.uv1_world_triplanar = false
	return material


func _finish_editor_change() -> void:
	notify_property_list_changed()
	emit_changed()
