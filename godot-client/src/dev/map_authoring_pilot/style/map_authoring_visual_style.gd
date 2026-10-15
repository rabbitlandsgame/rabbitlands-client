@tool
class_name MapAuthoringVisualStyle
extends Resource

## Compact texture choices for the disposable preview builders. Selectors are
## declared before their saved materials so Resource loading applies the saved,
## possibly hand-adjusted material after a selector has initialized its preset.

var _terrain_choices := {}
var _road_choices := {}
var _woodwork_choices := {}
var _stonework_choices := {}
var _roof_choices := {}
var _oriented_material_cache := {}
var _observed_source_signatures := {}
var _source_revisions := {
	"terrain": 0, "road": 0, "woodwork": 0, "stonework": 0, "roof": 0,
	"water": 0,
}
var _warned_unsupported_sources := {}

@export_group("Texture rotation")
@export_range(-180.0, 180.0, 1.0, "degrees") var terrain_texture_rotation_degrees := 0.0:
	set(value):
		var bounded := clampf(value, -180.0, 180.0)
		if is_equal_approx(terrain_texture_rotation_degrees, bounded):
			return
		terrain_texture_rotation_degrees = bounded
		_rotation_changed("terrain")

@export_range(-180.0, 180.0, 1.0, "degrees") var road_texture_rotation_degrees := 0.0:
	set(value):
		var bounded := clampf(value, -180.0, 180.0)
		if is_equal_approx(road_texture_rotation_degrees, bounded):
			return
		road_texture_rotation_degrees = bounded
		_rotation_changed("road")

@export_range(-180.0, 180.0, 1.0, "degrees") var woodwork_texture_rotation_degrees := 0.0:
	set(value):
		var bounded := clampf(value, -180.0, 180.0)
		if is_equal_approx(woodwork_texture_rotation_degrees, bounded):
			return
		woodwork_texture_rotation_degrees = bounded
		_rotation_changed("woodwork")

@export_range(-180.0, 180.0, 1.0, "degrees") var stonework_texture_rotation_degrees := 0.0:
	set(value):
		var bounded := clampf(value, -180.0, 180.0)
		if is_equal_approx(stonework_texture_rotation_degrees, bounded):
			return
		stonework_texture_rotation_degrees = bounded
		_rotation_changed("stonework")

@export_range(-180.0, 180.0, 1.0, "degrees") var roof_texture_rotation_degrees := 0.0:
	set(value):
		var bounded := clampf(value, -180.0, 180.0)
		if is_equal_approx(roof_texture_rotation_degrees, bounded):
			return
		roof_texture_rotation_degrees = bounded
		_rotation_changed("roof")

@export_group("")

@export_enum("Custom", "Grass", "Worn earth", "Desert", "Timber", "Stone", "Thatch",
	"Textile", "Canvas", "Metal", "Leather", "Hide", "Bone", "Crystal",
	"Cavern", "Slate") var terrain_texture := MapAuthoringTexturePresets.CUSTOM:
	set(value):
		if terrain_texture == value:
			return
		_remember_choice(_terrain_choices, terrain_texture, terrain_material)
		terrain_texture = value
		terrain_material = _standard_choice(
			_terrain_choices, value, terrain_material)
		_finish_choice_change()

@export_enum("Custom", "Grass", "Worn earth", "Desert", "Timber", "Stone", "Thatch",
	"Textile", "Canvas", "Metal", "Leather", "Hide", "Bone", "Crystal",
	"Cavern", "Slate") var road_texture := MapAuthoringTexturePresets.CUSTOM:
	set(value):
		if road_texture == value:
			return
		_remember_choice(_road_choices, road_texture, worn_path_material)
		road_texture = value
		worn_path_material = _road_choice(_road_choices, value, worn_path_material)
		_finish_choice_change()

@export_enum("Custom", "Grass", "Worn earth", "Desert", "Timber", "Stone", "Thatch",
	"Textile", "Canvas", "Metal", "Leather", "Hide", "Bone", "Crystal",
	"Cavern", "Slate") var woodwork_texture := MapAuthoringTexturePresets.CUSTOM:
	set(value):
		if woodwork_texture == value:
			return
		_remember_choice(_woodwork_choices, woodwork_texture, timber_material)
		woodwork_texture = value
		timber_material = _standard_choice(
			_woodwork_choices, value, timber_material)
		_finish_choice_change()

@export_enum("Custom", "Grass", "Worn earth", "Desert", "Timber", "Stone", "Thatch",
	"Textile", "Canvas", "Metal", "Leather", "Hide", "Bone", "Crystal",
	"Cavern", "Slate") var stonework_texture := MapAuthoringTexturePresets.CUSTOM:
	set(value):
		if stonework_texture == value:
			return
		_remember_choice(_stonework_choices, stonework_texture, stone_material)
		stonework_texture = value
		stone_material = _standard_choice(
			_stonework_choices, value, stone_material)
		_finish_choice_change()

@export_enum("Custom", "Grass", "Worn earth", "Desert", "Timber", "Stone", "Thatch",
	"Textile", "Canvas", "Metal", "Leather", "Hide", "Bone", "Crystal",
	"Cavern", "Slate") var roof_texture := MapAuthoringTexturePresets.CUSTOM:
	set(value):
		if roof_texture == value:
			return
		_remember_choice(_roof_choices, roof_texture, slate_material)
		roof_texture = value
		slate_material = _standard_choice(_roof_choices, value, slate_material)
		_finish_choice_change()

@export var show_advanced_materials := false:
	set(value):
		if show_advanced_materials == value:
			return
		show_advanced_materials = value
		notify_property_list_changed()
		emit_changed()

## Saved material references remain the builder API and serialization format.
## They are hidden from the Inspector unless Custom or Advanced is selected.
@export var terrain_material: Material:
	set(value):
		terrain_material = _replace_source_material(
			"terrain", terrain_material, value)
@export var worn_path_material: Material:
	set(value):
		worn_path_material = _replace_source_material(
			"road", worn_path_material, value)
@export var timber_material: Material:
	set(value):
		timber_material = _replace_source_material(
			"woodwork", timber_material, value)
@export var stone_material: Material:
	set(value):
		stone_material = _replace_source_material(
			"stonework", stone_material, value)
@export var slate_material: Material:
	set(value):
		slate_material = _replace_source_material(
			"roof", slate_material, value)
@export var water_material: Material:
	set(value):
		water_material = _replace_source_material(
			"water", water_material, value)


func _validate_property(property: Dictionary) -> void:
	var property_name := StringName(property.name)
	var visible := show_advanced_materials
	match property_name:
		&"terrain_material":
			visible = visible or terrain_texture == MapAuthoringTexturePresets.CUSTOM
		&"worn_path_material":
			visible = visible or road_texture == MapAuthoringTexturePresets.CUSTOM
		&"timber_material":
			visible = visible or woodwork_texture == MapAuthoringTexturePresets.CUSTOM
		&"stone_material":
			visible = visible or stonework_texture == MapAuthoringTexturePresets.CUSTOM
		&"slate_material":
			visible = visible or roof_texture == MapAuthoringTexturePresets.CUSTOM
		&"water_material":
			pass
		_:
			return
	if not visible:
		property.usage = int(property.usage) & ~PROPERTY_USAGE_EDITOR


func _finish_choice_change() -> void:
	notify_property_list_changed()
	emit_changed()


func get_material(slot: String, extra_rotation_degrees: float = 0.0) -> Material:
	var source := _source_material(slot)
	if source == null:
		return null
	_refresh_source_signature(slot, source)
	var effective_rotation := wrapf(
		_rotation_degrees(slot) + extra_rotation_degrees, -180.0, 180.0)
	if is_zero_approx(effective_rotation):
		return source
	var slot_cache: Dictionary = _oriented_material_cache.get(slot, {})
	if slot_cache.has(effective_rotation):
		return slot_cache[effective_rotation]
	var oriented := MapAuthoringTexturePresets.create_oriented_material(
		source, effective_rotation)
	if oriented == null:
		_warn_unsupported_rotation(slot, source)
		return source
	# Bridge angle handles can produce many transient values while dragging.
	# Bound each slot independently so disposable previews cannot grow forever.
	if slot_cache.size() >= 32:
		slot_cache.erase(slot_cache.keys()[0])
	slot_cache[effective_rotation] = oriented
	_oriented_material_cache[slot] = slot_cache
	return oriented


func rotation_signature() -> Array:
	for slot: String in ["terrain", "road", "woodwork", "stonework", "roof", "water"]:
		var source := _source_material(slot)
		if source != null:
			_refresh_source_signature(slot, source)
	return [
		terrain_texture_rotation_degrees, road_texture_rotation_degrees,
		woodwork_texture_rotation_degrees, stonework_texture_rotation_degrees,
		roof_texture_rotation_degrees,
		_source_revisions.terrain, _source_revisions.road,
		_source_revisions.woodwork, _source_revisions.stonework,
		_source_revisions.roof, _source_revisions.water,
	]


func _rotation_degrees(slot: String) -> float:
	match slot:
		"terrain":
			return terrain_texture_rotation_degrees
		"road":
			return road_texture_rotation_degrees
		"woodwork":
			return woodwork_texture_rotation_degrees
		"stonework":
			return stonework_texture_rotation_degrees
		"roof":
			return roof_texture_rotation_degrees
	return 0.0


func _source_material(slot: String) -> Material:
	match slot:
		"terrain":
			return terrain_material
		"road":
			return worn_path_material
		"woodwork":
			return timber_material
		"stonework":
			return stone_material
		"roof":
			return slate_material
		"water":
			return water_material
	return null


func _replace_source_material(slot: String, previous: Material,
		replacement: Material) -> Material:
	if previous == replacement:
		return replacement
	if previous != null:
		var old_callback := _source_material_changed.bind(
			slot, previous.get_instance_id())
		if previous.changed.is_connected(old_callback):
			previous.changed.disconnect(old_callback)
	if replacement != null:
		var callback := _source_material_changed.bind(
			slot, replacement.get_instance_id())
		if not replacement.changed.is_connected(callback):
			replacement.changed.connect(callback)
		_observed_source_signatures[slot] = _material_content_signature(replacement)
	else:
		_observed_source_signatures.erase(slot)
	_invalidate_rotation_cache(slot)
	return replacement


func _source_material_changed(slot: String, source_id: int) -> void:
	var current := _source_material(slot)
	if current == null or current.get_instance_id() != source_id:
		return
	_observed_source_signatures[slot] = _material_content_signature(current)
	_invalidate_rotation_cache(slot)
	emit_changed()


func _rotation_changed(slot: String) -> void:
	_invalidate_rotation_cache(slot)
	emit_changed()


func _invalidate_rotation_cache(slot: String) -> void:
	_oriented_material_cache.erase(slot)
	_source_revisions[slot] = int(_source_revisions.get(slot, 0)) + 1


func _refresh_source_signature(slot: String, source: Material) -> void:
	var current_signature := _material_content_signature(source)
	if not _observed_source_signatures.has(slot):
		_observed_source_signatures[slot] = current_signature
		return
	if int(_observed_source_signatures[slot]) == current_signature:
		return
	_observed_source_signatures[slot] = current_signature
	_invalidate_rotation_cache(slot)


func _material_content_signature(material: Material) -> int:
	var values := []
	for property: Dictionary in material.get_property_list():
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0:
			continue
		var property_name := StringName(property.name)
		if property_name in [&"resource_name", &"resource_local_to_scene"]:
			continue
		var value: Variant = material.get(property_name)
		values.append([property_name, _signature_value(value)])
	return values.hash()


func _signature_value(value: Variant) -> Variant:
	if value is Resource:
		return (value as Resource).get_instance_id()
	return value


func _warn_unsupported_rotation(slot: String, source: Material) -> void:
	var warning_key := "%s:%d" % [slot, source.get_instance_id()]
	if _warned_unsupported_sources.has(warning_key):
		return
	_warned_unsupported_sources[warning_key] = true
	push_warning("Texture rotation for style slot '%s' cannot preserve %s; " % [
		slot, source.get_class()] + "using the original material without rotation.")


func _remember_choice(choices: Dictionary, preset: String, material: Material) -> void:
	if material != null:
		choices[preset] = material


func _standard_choice(choices: Dictionary, preset: String,
		current: Material) -> Material:
	if choices.has(preset):
		return choices[preset]
	if preset == MapAuthoringTexturePresets.CUSTOM:
		return current
	return MapAuthoringTexturePresets.create_material(preset)


func _road_choice(choices: Dictionary, preset: String,
		current: Material) -> Material:
	if choices.has(preset):
		return choices[preset]
	if preset == MapAuthoringTexturePresets.CUSTOM:
		return current
	return MapAuthoringTexturePresets.create_road_material(preset)
