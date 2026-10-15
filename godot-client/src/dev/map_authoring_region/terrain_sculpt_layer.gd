@tool
class_name MapAuthoringTerrainSculptLayer
extends Resource

const MAX_ABS_DELTA_METRES := 4096.0

var _revision := 0
var _content_hash := 0

@export var base_sha256 := "":
	set(value):
		base_sha256 = value
		_touch()
@export var origin := Vector2.ZERO:
	set(value):
		origin = value
		_touch()
@export var grid_size := Vector2i.ZERO:
	set(value):
		grid_size = value
		_touch()
@export var cell_metres := 0.0:
	set(value):
		cell_metres = value
		_touch()
@export var indices := PackedInt32Array():
	set(value):
		indices = value
		_touch()
@export var deltas := PackedFloat32Array():
	set(value):
		deltas = value
		_touch()
func _init() -> void:
	resource_local_to_scene = true


func bind_base(sha256: String, terrain_origin: Vector2,
		terrain_grid_size: Vector2i, terrain_cell_metres: float) -> void:
	base_sha256 = sha256
	origin = terrain_origin
	grid_size = terrain_grid_size
	cell_metres = terrain_cell_metres


func validation_error(expected_sha256: String, expected_origin: Vector2,
		expected_grid_size: Vector2i, expected_cell_metres: float) -> String:
	if base_sha256 != expected_sha256 or not _is_sha256(base_sha256):
		return "Sculpt Layer belongs to a different base height file."
	if origin != expected_origin or grid_size != expected_grid_size or \
			not is_equal_approx(cell_metres, expected_cell_metres):
		return "Sculpt Layer terrain grid binding is stale."
	if grid_size.x < 2 or grid_size.y < 2 or not is_finite(cell_metres) or \
			cell_metres <= 0.0:
		return "Sculpt Layer grid binding is invalid."
	if indices.size() != deltas.size():
		return "Sculpt Layer indices and deltas have different lengths."
	var previous := -1
	var sample_count := grid_size.x * grid_size.y
	for offset in indices.size():
		var index := indices[offset]
		var delta := deltas[offset]
		if index <= previous or index < 0 or index >= sample_count:
			return "Sculpt Layer indices must be unique, sorted, and inside the terrain grid."
		if not is_finite(delta) or absf(delta) > MAX_ABS_DELTA_METRES:
			return "Sculpt Layer contains an invalid height delta."
		previous = index
	return ""


func apply_to(base_heights: PackedFloat32Array, expected_sha256: String,
		expected_origin: Vector2, expected_grid_size: Vector2i,
		expected_cell_metres: float) -> PackedFloat32Array:
	if base_heights.size() != expected_grid_size.x * expected_grid_size.y or \
			not validation_error(expected_sha256, expected_origin,
			expected_grid_size, expected_cell_metres).is_empty():
		return PackedFloat32Array()
	var result := base_heights.duplicate()
	for offset in indices.size():
		result[indices[offset]] += deltas[offset]
	return result


func copy_with(new_indices: PackedInt32Array,
		new_deltas: PackedFloat32Array) -> Resource:
	var result: Resource = get_script().new()
	result.bind_base(base_sha256, origin, grid_size, cell_metres)
	result.indices = new_indices
	result.deltas = new_deltas
	return result


func signature() -> Array:
	return [get_instance_id(), _revision, _content_hash, base_sha256, origin,
		grid_size, cell_metres]


func _touch() -> void:
	_revision += 1
	_content_hash = hash([indices, deltas])
	emit_changed()


func _is_sha256(value: String) -> bool:
	if value.length() != 64:
		return false
	for index in value.length():
		var character := value.substr(index, 1)
		if character not in "0123456789abcdef":
			return false
	return true
