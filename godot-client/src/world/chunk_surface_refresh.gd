extends RefCounted
## Coalesces arrivals without owning stream/cell lifetimes. A batch resolves
## only currently resident cells, in the stream's current coordinate frame.
const BOUNDARY_MARGIN_METRES := 0.25
var _regions: Dictionary = {}
var _full := false
var _notifications := 0
var _queued_usec := 0

func _note() -> void:
	if _notifications == 0:
		_queued_usec = Time.get_ticks_usec()
	_notifications += 1

func queue_full() -> void:
	_note()
	_full = true

func queue_chunk(identity: String, imported: Node3D) -> bool:
	if not is_instance_valid(imported) or imported.is_queued_for_deletion() \
			or imported.process_mode == Node.PROCESS_MODE_DISABLED:
		return false
	var stream := imported.get_parent() as ContinentChunkStream
	if stream == null:
		queue_full()
		return true
	if stream.process_mode == Node.PROCESS_MODE_DISABLED:
		return false
	var resident_value: Variant = stream.cells.get(identity)
	if not resident_value is Dictionary or (resident_value as Dictionary).get("root") != imported:
		# A previous listener may already have retired this cell.
		return false
	var entry: Dictionary = (resident_value as Dictionary).get("entry", {})
	var bounds_value: Variant = entry.get("bounds")
	if not _valid_bounds(bounds_value):
		queue_full()
		return true
	_note()
	var key := "%d:%s" % [stream.get_instance_id(), identity]
	_regions[key] = {"stream": weakref(stream), "imported": weakref(imported),
		"identity": identity, "bounds": (bounds_value as Dictionary).duplicate(true)}
	return true

static func _valid_bounds(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	var lower: Variant = (value as Dictionary).get("min")
	var upper: Variant = (value as Dictionary).get("max")
	if not lower is Array or not upper is Array or lower.size() < 3 or upper.size() < 3:
		return false
	for axis: int in [0, 2]:
		if typeof(lower[axis]) not in [TYPE_INT, TYPE_FLOAT] or typeof(upper[axis]) not in [TYPE_INT, TYPE_FLOAT]:
			return false
		if not is_finite(float(lower[axis])) or not is_finite(float(upper[axis])) \
				or float(lower[axis]) > float(upper[axis]):
			return false
	return true

static func live_region(region: Dictionary) -> Dictionary:
	var stream_ref := region.get("stream") as WeakRef
	var imported_ref := region.get("imported") as WeakRef
	var stream: ContinentChunkStream = stream_ref.get_ref() as ContinentChunkStream if stream_ref != null else null
	var imported: Node3D = imported_ref.get_ref() as Node3D if imported_ref != null else null
	if not is_instance_valid(stream) or not is_instance_valid(imported) \
			or stream.is_queued_for_deletion() or imported.is_queued_for_deletion() \
			or stream.process_mode == Node.PROCESS_MODE_DISABLED \
			or imported.process_mode == Node.PROCESS_MODE_DISABLED \
			or not stream.is_inside_tree() or imported.get_parent() != stream:
		return {}
	var resident_value: Variant = stream.cells.get(str(region.identity))
	if not resident_value is Dictionary or (resident_value as Dictionary).get("root") != imported:
		return {}
	return {"stream": stream, "imported": imported,
		"manifest": (resident_value as Dictionary).get("manifest") as WorldManifest}

func take() -> Dictionary:
	var regions: Array[Dictionary] = []
	for region: Dictionary in _regions.values():
		if not live_region(region).is_empty():
			regions.append(region)
	var batch := {"full": _full, "regions": regions, "notifications": _notifications,
		"queued_usec": _queued_usec, "invalidated_regions": _regions.size() - regions.size()}
	clear()
	return batch

static func has_live_changes(batch: Dictionary) -> bool:
	if bool(batch.get("full", false)):
		return true
	for region: Dictionary in batch.get("regions", []):
		if not live_region(region).is_empty():
			return true
	return false

static func should_refresh(batch: Dictionary, position: Vector3,
		priority := false, ungrounded := false) -> bool:
	if bool(batch.get("full", false)):
		return true
	for region: Dictionary in batch.get("regions", []):
		var live := live_region(region)
		if live.is_empty():
			continue
		if priority or ungrounded:
			return true
		var stream := live.stream as ContinentChunkStream
		var frame := stream.global_transform
		# Recompute only when the stream moved/rebased since the previous query.
		if not region.has("frame") or region.frame != frame:
			region["frame"] = frame
			region["unbounded"] = not frame.origin.is_finite() or not frame.basis.x.is_finite() \
				or not frame.basis.y.is_finite() or not frame.basis.z.is_finite() \
				or absf(frame.basis.determinant()) < 0.000001
			if not bool(region.unbounded):
				region["into_local"] = frame.affine_inverse()
		if bool(region.unbounded):
			return true
		var into_local: Transform3D = region.into_local
		var local := into_local * position
		var bounds: Dictionary = region.bounds
		var lower: Array = bounds.min
		var upper: Array = bounds.max
		if local.x >= float(lower[0]) - BOUNDARY_MARGIN_METRES \
				and local.x <= float(upper[0]) + BOUNDARY_MARGIN_METRES \
				and local.z >= float(lower[2]) - BOUNDARY_MARGIN_METRES \
				and local.z <= float(upper[2]) + BOUNDARY_MARGIN_METRES:
			return true
	return false

static func current_chunks(batch: Dictionary, active_stream: Node3D) -> Dictionary:
	var changed: Dictionary = {}
	for region: Dictionary in batch.get("regions", []):
		var live := live_region(region)
		if not live.is_empty() and live.stream == active_stream:
			changed[str(region.identity)] = true
	return changed

func pending_notifications() -> int:
	return _notifications

func snapshot() -> Dictionary:
	return {"notifications": _notifications, "regions": _regions.size(),
		"full": _full, "queued_usec": _queued_usec}

func clear() -> void:
	_regions.clear()
	_full = false
	_notifications = 0
	_queued_usec = 0
