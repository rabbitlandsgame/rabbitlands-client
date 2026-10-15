@tool
class_name MapAuthoringWidthPath
extends Path3D

## Full path width in metres. A point override of 0 inherits the surrounding
## width profile; newly inserted curve points therefore keep the old taper.
## MAX_WIDTH allows the rivers of the 8 km continent v2, whose creek mouths are
## 26-58 m wide (it was 16 m, which drew them as narrow ribbons in carved beds).

const HISTORY_LIMIT := 24
const MIN_WIDTH := 0.5
const MAX_WIDTH := 64.0

@export_range(0.5, 64.0, 0.1) var default_width := 2.5:
	set(value):
		default_width = clampf(value, MIN_WIDTH, MAX_WIDTH)
		_update_current_history()

@export var point_widths := PackedFloat32Array():
	set(value):
		point_widths = value.duplicate()
		for index in point_widths.size():
			point_widths[index] = clampf(point_widths[index], MIN_WIDTH, MAX_WIDTH) \
				if point_widths[index] > 0.0 else 0.0
		_normalize_width_count()
		_update_current_history()

@export_group("Local surface")
@export var surface: MapAuthoringSurface

var _tracked_curve: Curve3D
var _point_snapshot: Array[Vector3] = []
var _topology_history: Array[Dictionary] = []
var _current_history_index := -1
var _handling_change := false
var _stations_dirty := true
var _stations := PackedFloat32Array()
var _resolved_widths_dirty := true
var _resolved_widths := PackedFloat32Array()
var _bound_surface: MapAuthoringSurface


func _ready() -> void:
	set_process(true)
	sync_curve_binding()
	sync_surface_binding()


func _process(_delta: float) -> void:
	if curve != _tracked_curve:
		sync_curve_binding()
	if surface != _bound_surface:
		sync_surface_binding()


func sync_curve_binding() -> void:
	if curve == _tracked_curve:
		return
	if _tracked_curve != null and _tracked_curve.changed.is_connected(_on_curve_changed):
		_tracked_curve.changed.disconnect(_on_curve_changed)
	# Every authored control owns its Curve3D. This also makes an in-scene
	# duplicate safe to edit before the scene is saved and reopened.
	if curve != null:
		curve = curve.duplicate(true) as Curve3D
	_tracked_curve = curve
	_point_snapshot.clear()
	_topology_history.clear()
	_current_history_index = -1
	_stations_dirty = true
	_resolved_widths_dirty = true
	if _tracked_curve == null:
		point_widths = PackedFloat32Array()
		return
	_tracked_curve.resource_local_to_scene = true
	_tracked_curve.changed.connect(_on_curve_changed)
	_point_snapshot = _curve_positions()
	_normalize_width_count()
	_current_history_index = _remember_state(_point_snapshot, point_widths)


func width_at_offset(baked_distance: float) -> float:
	sync_curve_binding()
	if _tracked_curve == null or _tracked_curve.point_count == 0:
		return default_width
	_ensure_stations()
	_ensure_resolved_widths()
	if _tracked_curve.point_count == 1 or _stations.size() < 2:
		return _resolved_widths[0]
	var total := _tracked_curve.get_baked_length()
	if total <= 0.000001:
		return _resolved_widths[0]
	var offset := clampf(baked_distance, 0.0, total)
	for index in _stations.size() - 1:
		if offset <= _stations[index + 1] + 0.000001:
			var span := maxf(_stations[index + 1] - _stations[index], 0.000001)
			return lerpf(_resolved_widths[index], _resolved_widths[index + 1],
				clampf((offset - _stations[index]) / span, 0.0, 1.0))
	if _tracked_curve.closed:
		var span := maxf(total - _stations[_stations.size() - 1], 0.000001)
		return lerpf(_resolved_widths[_resolved_widths.size() - 1], _resolved_widths[0],
			clampf((offset - _stations[_stations.size() - 1]) / span, 0.0, 1.0))
	return _resolved_widths[_resolved_widths.size() - 1]


func width_signature() -> Array:
	sync_curve_binding()
	sync_surface_binding()
	return [default_width, point_widths.duplicate(),
		surface.signature() if surface != null else []]


func sync_surface_binding() -> void:
	if surface == _bound_surface:
		return
	if surface != null:
		surface = surface.duplicate(true) as MapAuthoringSurface
		surface.resource_local_to_scene = true
	_bound_surface = surface


func width_sample_offsets() -> PackedFloat32Array:
	sync_curve_binding()
	_ensure_stations()
	return _stations.duplicate()


func _on_curve_changed() -> void:
	if _handling_change or _tracked_curve == null:
		return
	_handling_change = true
	var current := _curve_positions()
	_stations_dirty = true
	_resolved_widths_dirty = true
	# Coordinate edits keep index ownership. This deliberately precedes history
	# lookup so moving a point back never revives an obsolete width array.
	if current.size() == _point_snapshot.size():
		_point_snapshot = current
		_normalize_width_count()
		_replace_current_history()
		_handling_change = false
		return
	var restored := _history_entry(current)
	if not restored.is_empty():
		point_widths = restored.widths
		_current_history_index = int(restored.index)
	else:
		point_widths = _aligned_widths(_point_snapshot, point_widths, current)
		_current_history_index = -1
	_point_snapshot = current
	if _current_history_index < 0:
		_current_history_index = _remember_state(_point_snapshot, point_widths)
	else:
		_replace_current_history()
	_handling_change = false


func _aligned_widths(old_positions: Array[Vector3], old_widths: PackedFloat32Array,
		new_positions: Array[Vector3]) -> PackedFloat32Array:
	var result := PackedFloat32Array()
	result.resize(new_positions.size())
	var prefix := 0
	while prefix < mini(old_positions.size(), new_positions.size()) \
			and old_positions[prefix] == new_positions[prefix]:
		result[prefix] = old_widths[prefix] if prefix < old_widths.size() else 0.0
		prefix += 1
	var old_suffix := old_positions.size() - 1
	var new_suffix := new_positions.size() - 1
	while old_suffix >= prefix and new_suffix >= prefix \
			and old_positions[old_suffix] == new_positions[new_suffix]:
		result[new_suffix] = old_widths[old_suffix] if old_suffix < old_widths.size() else 0.0
		old_suffix -= 1
		new_suffix -= 1
	var search_from := prefix
	for new_index in range(prefix, new_suffix + 1):
		for old_index in range(search_from, old_suffix + 1):
			if new_positions[new_index] == old_positions[old_index]:
				result[new_index] = old_widths[old_index] if old_index < old_widths.size() else 0.0
				search_from = old_index + 1
				break
	return result


func _normalize_width_count() -> void:
	if _tracked_curve == null:
		return
	var wanted := _tracked_curve.point_count
	if point_widths.size() == wanted:
		return
	var resized := point_widths.duplicate()
	resized.resize(wanted)
	point_widths = resized


func _curve_positions() -> Array[Vector3]:
	var result: Array[Vector3] = []
	if _tracked_curve != null:
		for index in _tracked_curve.point_count:
			result.append(_tracked_curve.get_point_position(index))
	return result


func _remember_state(positions: Array[Vector3], widths: PackedFloat32Array) -> int:
	if positions.is_empty() and widths.is_empty() and _topology_history.is_empty():
		_topology_history.append({"positions": [], "widths": PackedFloat32Array()})
		return 0
	for index in _topology_history.size():
		if _topology_history[index].positions == positions:
			_topology_history[index] = {"positions": positions.duplicate(),
				"widths": widths.duplicate()}
			return index
	_topology_history.append({"positions": positions.duplicate(), "widths": widths.duplicate()})
	if _topology_history.size() > HISTORY_LIMIT:
		_topology_history.pop_front()
		_current_history_index -= 1
	return _topology_history.size() - 1


func _history_entry(positions: Array[Vector3]) -> Dictionary:
	for index in range(_topology_history.size() - 1, -1, -1):
		if _topology_history[index].positions == positions:
			var stored: PackedFloat32Array = _topology_history[index].widths
			return {"index": index, "widths": stored.duplicate()}
	return {}


func _update_current_history() -> void:
	_stations_dirty = true
	_resolved_widths_dirty = true
	if _handling_change or _tracked_curve == null:
		return
	_replace_current_history()


func _replace_current_history() -> void:
	if _current_history_index >= 0 and _current_history_index < _topology_history.size():
		_topology_history[_current_history_index] = {
			"positions": _point_snapshot.duplicate(), "widths": point_widths.duplicate()}
	else:
		_current_history_index = _remember_state(_point_snapshot, point_widths)


func _ensure_stations() -> void:
	if not _stations_dirty:
		return
	_stations_dirty = false
	_stations.clear()
	if _tracked_curve == null or _tracked_curve.point_count == 0:
		return
	_stations.append(0.0)
	var cumulative := 0.0
	for index in _tracked_curve.point_count - 1:
		cumulative += _segment_baked_length(index, index + 1)
		_stations.append(cumulative)
	var unscaled_total := cumulative
	if _tracked_curve.closed and _tracked_curve.point_count > 1:
		unscaled_total += _segment_baked_length(_tracked_curve.point_count - 1, 0)
	var baked_total := _tracked_curve.get_baked_length()
	if unscaled_total > 0.000001 and baked_total > 0.000001:
		var scale := baked_total / unscaled_total
		for index in _stations.size():
			_stations[index] *= scale


func _segment_baked_length(from_index: int, to_index: int) -> float:
	var segment := Curve3D.new()
	segment.bake_interval = _tracked_curve.bake_interval
	segment.add_point(_tracked_curve.get_point_position(from_index), Vector3.ZERO,
		_tracked_curve.get_point_out(from_index))
	segment.add_point(_tracked_curve.get_point_position(to_index),
		_tracked_curve.get_point_in(to_index), Vector3.ZERO)
	return segment.get_baked_length()


func _resolved_point_widths() -> PackedFloat32Array:
	var result := PackedFloat32Array()
	var count := _tracked_curve.point_count if _tracked_curve != null else 0
	result.resize(count)
	if count == 0:
		return result
	_ensure_stations()
	var anchors: Array[Vector2] = []
	for index in count:
		var override := point_widths[index] if index < point_widths.size() else 0.0
		if override > 0.0:
			anchors.append(Vector2(_stations[index], clampf(override, MIN_WIDTH, MAX_WIDTH)))
	if anchors.is_empty():
		result.fill(default_width)
		return result
	var total := _tracked_curve.get_baked_length()
	if not _tracked_curve.closed:
		if anchors[0].x > 0.000001:
			anchors.push_front(Vector2(0.0, default_width))
		if anchors[anchors.size() - 1].x < total - 0.000001:
			anchors.append(Vector2(total, default_width))
		for index in count:
			result[index] = _interpolate_anchors(anchors, _stations[index])
		return result
	# Closed paths interpolate cyclically between explicit stations. A single
	# explicit station applies around the loop without a seam.
	if anchors.size() == 1:
		result.fill(anchors[0].y)
		return result
	var cyclic := anchors.duplicate()
	cyclic.push_front(Vector2(anchors[anchors.size() - 1].x - total,
		anchors[anchors.size() - 1].y))
	cyclic.append(Vector2(anchors[0].x + total, anchors[0].y))
	for index in count:
		result[index] = _interpolate_anchors(cyclic, _stations[index])
	return result


func _interpolate_anchors(anchors: Array[Vector2], station: float) -> float:
	for index in anchors.size() - 1:
		if station <= anchors[index + 1].x + 0.000001:
			var span := maxf(anchors[index + 1].x - anchors[index].x, 0.000001)
			return lerpf(anchors[index].y, anchors[index + 1].y,
				clampf((station - anchors[index].x) / span, 0.0, 1.0))
	return anchors[anchors.size() - 1].y


func _ensure_resolved_widths() -> void:
	if not _resolved_widths_dirty:
		return
	_resolved_widths_dirty = false
	_resolved_widths = _resolved_point_widths()
