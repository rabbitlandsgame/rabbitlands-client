@tool
class_name MapAuthoringBuildingControl
extends Node3D

@export var wall_surface: MapAuthoringSurface
@export var roof_surface: MapAuthoringSurface

var _bound_wall_surface: MapAuthoringSurface
var _bound_roof_surface: MapAuthoringSurface


func _ready() -> void:
	set_process(true)
	sync_surface_bindings()


func _process(_delta: float) -> void:
	if wall_surface != _bound_wall_surface or roof_surface != _bound_roof_surface:
		sync_surface_bindings()


func sync_surface_bindings() -> void:
	if wall_surface != _bound_wall_surface:
		wall_surface = _local_surface_copy(wall_surface)
		_bound_wall_surface = wall_surface
	if roof_surface != _bound_roof_surface:
		roof_surface = _local_surface_copy(roof_surface)
		_bound_roof_surface = roof_surface


func surface_signature() -> Array:
	sync_surface_bindings()
	return [wall_surface.signature() if wall_surface != null else [],
		roof_surface.signature() if roof_surface != null else []]


func _local_surface_copy(source: MapAuthoringSurface) -> MapAuthoringSurface:
	if source == null:
		return null
	var result := source.duplicate(true) as MapAuthoringSurface
	result.resource_local_to_scene = true
	return result
