@tool
class_name MapAuthoringBiomePaletteEntry
extends Resource

const VALID_ROLES := [
	"woodland", "heath", "wetland", "rock", "snow", "sand", "limestone",
	"grassland", "steppe", "badland", "tree_density",
]

@export var id := ""
@export_enum("woodland", "heath", "wetland", "rock", "snow", "sand", "limestone",
	"grassland", "steppe", "badland", "tree_density") \
	var role := "woodland"
@export var surface: MapAuthoringSurface

var _bound_surface: MapAuthoringSurface


func _init() -> void:
	resource_local_to_scene = true


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
	return [id, role, surface.signature() if surface != null else []]
