@tool
class_name MapAuthoringObjectSurface
extends MeshInstance3D

## A saved mesh with its own editable surface. The resource is copied once
## when this node enters the scene, so a live Ctrl+D duplicate is independent.

@export var surface: MapAuthoringSurface

var _bound_surface: MapAuthoringSurface
var _last_signature: Array = []
var _signature_elapsed := 0.0
var _legacy_material: Material


func _ready() -> void:
	set_process(true)
	_legacy_material = material_override
	sync_surface_binding()


func _process(delta: float) -> void:
	if surface != _bound_surface:
		sync_surface_binding()
		return
	_signature_elapsed += delta
	if _signature_elapsed < 0.18 or surface == null:
		return
	_signature_elapsed = 0.0
	var current := surface.signature()
	if current != _last_signature:
		_last_signature = current
		_apply_surface()


func sync_surface_binding() -> void:
	if surface == _bound_surface:
		return
	if _bound_surface != null and _bound_surface.changed.is_connected(_apply_surface):
		_bound_surface.changed.disconnect(_apply_surface)
	if surface != null:
		surface = surface.duplicate(true) as MapAuthoringSurface
		surface.resource_local_to_scene = true
	_bound_surface = surface
	if _bound_surface != null:
		_bound_surface.changed.connect(_apply_surface)
		_last_signature = _bound_surface.signature()
	else:
		_last_signature = []
	_apply_surface()


func apply_legacy_style(style: MapAuthoringVisualStyle, slot: String) -> void:
	if surface != null:
		return
	material_override = style.get_material(slot) if style != null else null


func surface_signature() -> Array:
	sync_surface_binding()
	return surface.signature() if surface != null else []


func _apply_surface() -> void:
	if surface != null:
		_last_signature = surface.signature()
		material_override = surface.get_material()
	else:
		material_override = _legacy_material


func _validate_property(property: Dictionary) -> void:
	if StringName(property.name) == &"material_override" and surface != null:
		property.usage = int(property.usage) & ~PROPERTY_USAGE_STORAGE \
			& ~PROPERTY_USAGE_EDITOR
