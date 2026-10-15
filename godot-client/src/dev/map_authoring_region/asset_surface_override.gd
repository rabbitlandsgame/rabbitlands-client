@tool
class_name MapAuthoringAssetSurfaceOverride
extends Resource

@export var mesh_node_path := ""
@export_range(0, 255, 1, "or_greater") var surface_index := 0
@export var surface: MapAuthoringSurface

var _bound_surface: MapAuthoringSurface


func bind_local_surface() -> void:
	if surface == _bound_surface:
		return
	if surface != null:
		surface = surface.duplicate(true) as MapAuthoringSurface
		surface.resource_local_to_scene = true
		surface.enable_region_uv_projection()
	_bound_surface = surface


func signature() -> Array:
	bind_local_surface()
	return [mesh_node_path, surface_index,
		surface.signature() if surface != null else []]
