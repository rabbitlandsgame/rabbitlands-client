extends RefCounted
## Additive resource timings. Callers own each table (or guard it with their
## existing mutex). Spans may overlap: these totals are not a frame-time sum.
## Only single blocking API calls should be marked atomic. Snapshots copy plain
## data and never retain nodes, textures or meshes.

static func record(timings: Dictionary, operation: StringName, started_usec: int,
		atomic := false) -> void:
	var elapsed := maxi(0, Time.get_ticks_usec() - started_usec)
	record_elapsed(timings, operation, elapsed, atomic)

## Worker-facing callers capture elapsed before acquiring their mutex, so
## diagnostic lock contention is not mislabelled as an engine operation.
static func record_elapsed(timings: Dictionary, operation: StringName, elapsed_usec: int,
		atomic := false) -> void:
	var elapsed := maxi(0, elapsed_usec)
	var row: Dictionary = timings.get(operation, {})
	if row.is_empty():
		row = {"count": 0, "total_us": 0, "last_us": 0, "max_us": 0, "atomic": atomic}
		timings[operation] = row
	row.count = int(row.count) + 1
	row.total_us = int(row.total_us) + elapsed
	row.last_us = elapsed
	row.max_us = maxi(int(row.max_us), elapsed)

static func snapshot(timings: Dictionary) -> Dictionary:
	var largest := {"operation": "", "duration_us": 0}
	for operation: Variant in timings:
		var row: Dictionary = timings[operation]
		if bool(row.get("atomic", false)) and int(row.max_us) > int(largest.duration_us):
			largest.operation = str(operation)
			largest.duration_us = int(row.max_us)
	return {"operations": timings.duplicate(true), "largest_atomic": largest}
