@tool
class_name MapAuthoringBridgeControl
extends Node3D

## One saved bridge span. Move this node to move the whole bridge, or move its
## Start and End markers to place each bank landing independently.

## The slider covers footbridges; wider decks (the 10-12 m causeways of continent
## v2) are typed in, and the Inspector keeps them instead of clamping to 6 m.
@export_range(1.5, 6.0, 0.1, "or_greater") var width := 3.0
@export_range(0.0, 2.0, 0.05) var arch := 0.6
@export_range(0.85, 2.0, 0.05) var water_clearance := 0.9
@export_range(-360.0, 360.0, 1.0, "or_less", "or_greater") var deck_texture_rotation_degrees := 0.0
@export_group("Local surfaces")
@export var deck_surface: MapAuthoringSurface
@export var support_surface: MapAuthoringSurface

var _bound_deck_surface: MapAuthoringSurface
var _bound_support_surface: MapAuthoringSurface


func _ready() -> void:
	set_process(true)
	sync_surface_bindings()


func _process(_delta: float) -> void:
	if deck_surface != _bound_deck_surface or support_surface != _bound_support_surface:
		sync_surface_bindings()


func start_marker() -> Marker3D:
	return get_node_or_null("Start") as Marker3D


func end_marker() -> Marker3D:
	return get_node_or_null("End") as Marker3D


func authored_signature() -> Array:
	sync_surface_bindings()
	var start := start_marker()
	var end := end_marker()
	return [global_transform, width, arch, water_clearance,
		deck_texture_rotation_degrees, _surface_signature(deck_surface),
		_surface_signature(support_surface),
		start.transform if start else Transform3D.IDENTITY,
		end.transform if end else Transform3D.IDENTITY]


func sync_surface_bindings() -> void:
	if deck_surface != _bound_deck_surface:
		deck_surface = _local_surface_copy(deck_surface)
		_bound_deck_surface = deck_surface
	if support_surface != _bound_support_surface:
		support_surface = _local_surface_copy(support_surface)
		_bound_support_surface = support_surface


func _surface_signature(surface: MapAuthoringSurface) -> Array:
	return surface.signature() if surface != null else []


func _local_surface_copy(source: MapAuthoringSurface) -> MapAuthoringSurface:
	if source == null:
		return null
	var result := source.duplicate(true) as MapAuthoringSurface
	result.resource_local_to_scene = true
	return result
