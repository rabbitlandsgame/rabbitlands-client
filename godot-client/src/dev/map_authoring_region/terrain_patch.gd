@tool
class_name MapAuthoringTerrainPatch
extends Marker3D

enum Shape { ELLIPSE, RECTANGLE }
enum Operation { ADD, SET }

@export var patch_id := ""
@export_enum("Ellipse", "Rectangle") var shape: int = Shape.ELLIPSE
@export_enum("Add", "Set") var operation: int = Operation.ADD
@export var size := Vector2(24.0, 24.0):
	set(value):
		size = Vector2(maxf(value.x, 0.1), maxf(value.y, 0.1))
@export_range(0.0, 64.0, 0.1, "or_greater") var feather := 6.0
## The patch height is its normal Node3D Y position. Drag vertically in the 3D
## view, or edit this proxy in the Inspector; the transform remains the only
## saved source of truth.
@export_range(-256.0, 512.0, 0.05, "or_less", "or_greater") var height_value: float:
	get: return position.y
	set(value): position.y = value
@export var enabled := true


func _validate_property(property: Dictionary) -> void:
	if StringName(property.name) == &"height_value":
		property.usage = int(property.usage) & ~PROPERTY_USAGE_STORAGE


func weight_at_transform(terrain_xz: Vector2,
		patch_to_terrain: Transform3D) -> float:
	if not enabled:
		return 0.0
	var projected := Transform2D(
		Vector2(patch_to_terrain.basis.x.x, patch_to_terrain.basis.x.z),
		Vector2(patch_to_terrain.basis.z.x, patch_to_terrain.basis.z.z),
		Vector2(patch_to_terrain.origin.x, patch_to_terrain.origin.z))
	if not projected.x.is_finite() or not projected.y.is_finite() or \
			absf(projected.determinant()) <= 0.000001:
		return 0.0
	var half := size * 0.5
	var offset := projected.affine_inverse() * terrain_xz
	var edge_distance: float
	if shape == Shape.RECTANGLE:
		edge_distance = minf(half.x - absf(offset.x), half.y - absf(offset.y))
	else:
		var normalized := Vector2(offset.x / half.x, offset.y / half.y)
		edge_distance = (1.0 - normalized.length()) * minf(half.x, half.y)
	if edge_distance <= 0.0:
		return 0.0
	if feather <= 0.000001:
		return 1.0
	var amount := clampf(edge_distance / feather, 0.0, 1.0)
	return amount * amount * (3.0 - 2.0 * amount)


func snapshot_record(patch_to_region: Transform3D) -> Dictionary:
	return {
		"id": patch_id,
		"shape": "ellipse" if shape == Shape.ELLIPSE else "rectangle",
		"operation": "add" if operation == Operation.ADD else "set",
		"matrix": _matrix_array(patch_to_region),
		"size": [size.x, size.y],
		"feather": feather,
		"height": patch_to_region.origin.y,
		"enabled": enabled,
	}


func _matrix_array(value: Transform3D) -> Array:
	return [value.basis.x.x, value.basis.x.y, value.basis.x.z, 0.0,
		value.basis.y.x, value.basis.y.y, value.basis.y.z, 0.0,
		value.basis.z.x, value.basis.z.y, value.basis.z.z, 0.0,
		value.origin.x, value.origin.y, value.origin.z, 1.0]


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if patch_id.strip_edges().is_empty():
		warnings.append("Terrain patches need a stable Patch Id before export.")
	var projected := Transform2D(Vector2(global_basis.x.x, global_basis.x.z),
		Vector2(global_basis.z.x, global_basis.z.z), Vector2.ZERO)
	if absf(projected.determinant()) <= 0.000001:
		warnings.append("Terrain patch X/Z projection is singular.")
	if absf(global_basis.x.y) > 0.0001 or absf(global_basis.z.y) > 0.0001 or \
			absf(global_basis.y.x) > 0.0001 or absf(global_basis.y.z) > 0.0001:
		warnings.append("Terrain patches support X/Z move, vertical height, yaw, and X/Z scale; X/Z tilt is not exported.")
	return warnings
