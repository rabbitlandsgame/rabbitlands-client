extends Node
## Same-frame flush after ordinary mount _process callbacks, before rendering.
## Owned by the optional runtime. No SceneTree callback, await, or delayed pose.
var _rows: Array = []
var batches := 0
var poses := 0
var fallbacks := 0
var flushes := 0
var submit_us := 0
var flush_total_us := 0
var packing_us := 0
var native_call_us := 0
var finish_us := 0

func _init() -> void:
	name = "RustRiderPoseBatch"
	process_priority = 1000000
	set_physics_process(false)

func submit(pose: RefCounted, seat: Transform3D, gait: String, seconds: float, cycle: float, finish: Callable) -> void:
	var began := Time.get_ticks_usec()
	_rows.append([weakref(pose), seat, gait, seconds, cycle, finish, int(pose._epoch), int(pose._frame), pose.frame_identity()])
	submit_us += Time.get_ticks_usec() - began

func _process(_delta: float) -> void:
	flush()

func flush() -> void:
	if _rows.is_empty():
		return
	var began := Time.get_ticks_usec()
	var packing_began := began
	flushes += 1
	var pending := _rows
	_rows = []
	var groups: Array = []
	for row: Array in pending:
		var pose = (row[0] as WeakRef).get_ref()
		if pose == null or not pose.still_valid(int(row[6])) or int(pose._frame) != int(row[7]) or not pose.matches_frame_identity(row[8]):
			continue
		var found := false
		for group: Array in groups:
			if group[0] == pose._native and int(group[1]) == int(row[6]):
				group[2].append(row)
				found = true
				break
		if not found:
			groups.append([pose._native, int(row[6]), [row]])
	packing_us += Time.get_ticks_usec() - packing_began
	for group: Array in groups:
		packing_began = Time.get_ticks_usec()
		var native = group[0]
		var epoch: int = group[1]
		var records := PackedInt64Array()
		var samples := PackedFloat64Array()
		var upper := PackedFloat64Array()
		var with_upper: bool = native.has_method("solve_mounted_presentation_batch")
		for row: Array in group[2]:
			var pose = (row[0] as WeakRef).get_ref()
			records.append_array(pose.record(str(row[2])))
			samples.append_array(pose.sample(row[1], float(row[3]), float(row[4])))
			if with_upper and pose.has_method("upper_sample"):
				upper.append_array(pose.upper_sample())
			else:
				with_upper = false
		packing_us += Time.get_ticks_usec() - packing_began
		var native_began := Time.get_ticks_usec()
		var ok: bool = native.solve_mounted_presentation_batch(records, samples, upper, epoch, true) \
			if with_upper else native.solve_mounted_batch(records, samples, epoch, true)
		native_call_us += Time.get_ticks_usec() - native_began
		batches += 1
		var finish_began := Time.get_ticks_usec()
		for row: Array in group[2]:
			var pose = (row[0] as WeakRef).get_ref()
			if pose == null or not pose.still_valid(epoch):
				continue
			if ok:
				if with_upper:
					pose.mark_native_upper_applied()
				pose.applications += 1
				poses += 1
			else:
				pose.fallback_fit(row[1], str(row[2]), float(row[3]), float(row[4]))
				fallbacks += 1
			var finish: Callable = row[5]
			if finish.is_valid():
				finish.call()
		finish_us += Time.get_ticks_usec() - finish_began
	flush_total_us += Time.get_ticks_usec() - began

func diagnostic_snapshot() -> Dictionary:
	return {"present": true, "pending": _rows.size(), "batches": batches, "poses": poses,
		"fallbacks": fallbacks, "flushes": flushes, "submit_us": submit_us,
		"flush_total_us": flush_total_us, "packing_us": packing_us,
		"native_call_us": native_call_us, "finish_us": finish_us,
		"counter_window": "cumulative_since_batch_creation",
		"timing_relationship": "submit and flush do not overlap; packing/native/finish are subsets of flush; C++ timings are subsets of native"}

func close() -> void:
	_rows.clear()
	set_process(false)
	queue_free()
