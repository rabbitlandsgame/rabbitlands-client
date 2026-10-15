@tool
class_name MapAuthoringTerrainSculptBrush
extends RefCounted

const LAYER := preload("res://src/dev/map_authoring_region/terrain_sculpt_layer.gd")
const MAX_RADIUS_METRES := 4096.0
const MAX_RAISE_LOWER_METRES := 128.0

enum Mode { RAISE, LOWER, SMOOTH, FLATTEN }


## Returns a new independent sparse layer. The input layer is never mutated.
## Raise/Lower strength is metres per stamp; Smooth/Flatten strength is 0..1.
## A non-empty locked mask must have one byte per grid sample; nonzero is locked.
static func apply_stamp(base_heights: PackedFloat32Array, current_layer: Resource,
		base_sha256: String, origin: Vector2, grid_size: Vector2i,
		cell_metres: float, center: Vector2, mode: int, radius_metres: float,
		strength: float, softness: float, flatten_target_y: float = NAN,
		locked_mask: PackedByteArray = PackedByteArray(),
		boundary_weights: PackedFloat32Array = PackedFloat32Array()) -> Resource:
	var sample_count := grid_size.x * grid_size.y
	if sample_count <= 0 or base_heights.size() != sample_count or \
			not center.is_finite() or not is_finite(cell_metres) or cell_metres <= 0.0 or \
			not is_finite(radius_metres) or radius_metres <= 0.0 or \
			radius_metres > MAX_RADIUS_METRES or not is_finite(strength) or strength < 0.0 or \
			not is_finite(softness) or softness < 0.0 or softness > 1.0 or \
			(mode < Mode.RAISE or mode > Mode.FLATTEN) or \
			(not locked_mask.is_empty() and locked_mask.size() != sample_count) or \
			(not boundary_weights.is_empty() and boundary_weights.size() != sample_count):
		push_warning("Terrain sculpt brush parameters or lock mask are invalid.")
		return null
	if (mode == Mode.RAISE or mode == Mode.LOWER) and \
			strength > MAX_RAISE_LOWER_METRES:
		push_warning("Terrain sculpt Raise/Lower strength is out of range.")
		return null
	if (mode == Mode.SMOOTH or mode == Mode.FLATTEN) and strength > 1.0:
		push_warning("Terrain sculpt Smooth/Flatten strength must be between 0 and 1.")
		return null
	if mode == Mode.FLATTEN and not is_finite(flatten_target_y):
		push_warning("Terrain sculpt Flatten needs a finite target height.")
		return null
	var layer: Variant = current_layer
	if layer == null:
		layer = LAYER.new()
		layer.bind_base(base_sha256, origin, grid_size, cell_metres)
	elif layer.get_script() != LAYER or not layer.validation_error(base_sha256,
			origin, grid_size, cell_metres).is_empty():
		push_warning("Terrain sculpt layer does not match the current base terrain.")
		return null
	var source_sparse := {}
	for offset in layer.indices.size():
		source_sparse[layer.indices[offset]] = layer.deltas[offset]
	var sparse: Dictionary = source_sparse.duplicate()
	var x0 := clampi(floori((center.x - radius_metres - origin.x) /
		cell_metres), 0, grid_size.x - 1)
	var x1 := clampi(ceili((center.x + radius_metres - origin.x) /
		cell_metres), 0, grid_size.x - 1)
	var z0 := clampi(floori((center.y - radius_metres - origin.y) /
		cell_metres), 0, grid_size.y - 1)
	var z1 := clampi(ceili((center.y + radius_metres - origin.y) /
		cell_metres), 0, grid_size.y - 1)
	for z_index in range(z0, z1 + 1):
		for x_index in range(x0, x1 + 1):
			var index := z_index * grid_size.x + x_index
			if not locked_mask.is_empty() and locked_mask[index] != 0:
				continue
			var boundary_weight := 1.0 if boundary_weights.is_empty() else \
				boundary_weights[index]
			if not is_finite(boundary_weight) or boundary_weight < 0.0 or \
					boundary_weight > 1.0:
				push_warning("Terrain sculpt boundary weights must stay between 0 and 1.")
				return null
			var sample := Vector2(origin.x + float(x_index) * cell_metres,
				origin.y + float(z_index) * cell_metres)
			var distance := sample.distance_to(center)
			if distance > radius_metres:
				continue
			var weight := _falloff(distance / radius_metres, softness)
			weight *= boundary_weight
			if weight <= 0.0:
				continue
			var source_height := _source_height(base_heights, source_sparse, index)
			if not is_finite(source_height):
				push_warning("Terrain sculpt base contains a non-finite height.")
				return null
			var next_height := source_height
			match mode:
				Mode.RAISE:
					next_height += strength * weight
				Mode.LOWER:
					next_height -= strength * weight
				Mode.SMOOTH:
					var average := _neighbor_average(base_heights, source_sparse,
						x_index, z_index, grid_size)
					if not is_finite(average):
						push_warning("Terrain sculpt smoothing encountered a non-finite height.")
						return null
					next_height = lerpf(source_height, average, strength * weight)
				Mode.FLATTEN:
					next_height = lerpf(source_height, flatten_target_y,
						strength * weight)
			var delta := next_height - base_heights[index]
			if not is_finite(delta) or absf(delta) > LAYER.MAX_ABS_DELTA_METRES:
				push_warning("Terrain sculpt result exceeds the supported height range.")
				return null
			if absf(delta) <= 0.000001:
				sparse.erase(index)
			else:
				sparse[index] = delta
	var keys: Array = sparse.keys()
	keys.sort()
	var next_indices := PackedInt32Array()
	var next_deltas := PackedFloat32Array()
	for key in keys:
		next_indices.append(int(key))
		next_deltas.append(float(sparse[key]))
	if next_indices == layer.indices and next_deltas == layer.deltas:
		return null
	return layer.copy_with(next_indices, next_deltas)


static func _falloff(normalized_distance: float, softness: float) -> float:
	if softness <= 0.0:
		return 1.0
	var inner := 1.0 - softness
	if normalized_distance <= inner:
		return 1.0
	var amount := clampf(1.0 - (normalized_distance - inner) / softness,
		0.0, 1.0)
	return amount * amount * (3.0 - 2.0 * amount)


static func _source_height(base_heights: PackedFloat32Array, sparse: Dictionary,
		index: int) -> float:
	return base_heights[index] + float(sparse.get(index, 0.0))


static func _neighbor_average(base_heights: PackedFloat32Array, sparse: Dictionary,
		x_index: int, z_index: int, grid_size: Vector2i) -> float:
	var total := 0.0
	var count := 0
	for z in range(maxi(0, z_index - 1), mini(grid_size.y - 1, z_index + 1) + 1):
		for x in range(maxi(0, x_index - 1), mini(grid_size.x - 1, x_index + 1) + 1):
			total += _source_height(base_heights, sparse, z * grid_size.x + x)
			count += 1
	return total / float(count)
