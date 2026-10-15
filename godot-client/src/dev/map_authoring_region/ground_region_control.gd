@tool
class_name MapAuthoringRegionGround
extends "res://src/dev/map_authoring_pilot/ground_region.gd"

@export var region_id := ""


func sync_surface_binding() -> void:
	super.sync_surface_binding()
	if surface != null:
		surface.enable_region_uv_projection()


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := super._get_configuration_warnings()
	if region_id.strip_edges().is_empty():
		warnings.append("Ground regions need a stable Region Id before export.")
	return warnings
